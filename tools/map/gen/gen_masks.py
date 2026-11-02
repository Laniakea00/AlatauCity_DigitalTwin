"""Parking, stops, greens, plazas and no-plant masks of a district (w44, CONTRACT §4):
python3 tools/map/gen/gen_masks.py <district> [--out OUT] [--spec S]

Reads   spec (zones' parking rules, centres, views, corridors, keep), OUT/<d>/network.json, lrt.json, lots.json, buildings.json.
Writes  OUT/<d>/features.json {schema:"qtwin.features/1", parking:[…], stops:[…], greens:[…], plazas:[…], noplant:[…], log}

Parking   cars per lot = new homes × zone parking.per_home (+ office / retail norms when the spec gives them; level 0 leaves them
          null: offices then take malls.parking_office per 100 workers at its lower bound (модель qTwin), retail stays logged:
          parking_mall is not_verified with an unclear unit) + school places × parking.school_2000_places / typical
          capacity. Type from the zone: underground under the lot (levels by parking.area_m2_per_space multilevel_underground),
          multi-storey in the free land of the lot (floors by parking.garage_area_by_floors_m2), surface in the free land
          (parking.area_m2_per_space open). Rule 17 is kept here: no surface field over parking.ground_lot_max_in_centre places
          in a district centre, nothing above ground in a landmark view sector — the rest goes underground.
Stops     bus stops on the sidewalk of streets of the transit classes, first where most homes lie within stops.walk_max_m on foot
          (≥ stops.spacing_m bus min apart along one street), then by density (≥ that from every stop); LRT stations from lrt.json; rail stations = registry lots
          of use transit.
Greens    park / square / playground / sport lots; no-build park lots are buffers; yards = residential lots minus buildings and
          parking (split so no polygon has holes).
Plazas    free land of transit lots (station forecourts).
No-plant  overhead power corridors, the LRT ground corridor, water, parking above ground, plazas, sport grounds, keep land.
Years     every object carries the years of what it serves (lot / buildings / street / line)."""
import heapq
import math
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import land_models as M  # noqa: E402
import land_transit as LT  # noqa: E402
import land_util as U  # noqa: E402


VILLAGE_BUS = {"village_main", "village_secondary"}    # village streets a bus runs on (model: the lanes are too narrow)
STOP_PAD_W = 2.0          # width of a stop pad where the street has no sidewalk (m): a model parameter
STOP_STEP_M = 25.0        # candidate stop points along a bus street this far apart (m): модель qTwin
STREET_ON_DEG = 35.0      # a bus street goes on through a junction into the segment within this many degrees of straight
#                           ahead (its stops.spacing_m run on along it): модель qTwin


def bus_streets(net, classes):
    """Street of every segment of the bus classes, as stops.spacing_m takes it (the distance between the stops of one route,
    not between stops of two streets): {segment id: street key}. Segments of one network street id are one street, and at a
    node a segment goes on into the one most nearly straight ahead (within STREET_ON_DEG) — two bus streets crossing or
    meeting at a T stay two streets."""
    segs = [s for s in net["segments"] if s["class"] in classes and len(s.get("pts") or []) >= 2]
    par = {s["id"]: s["id"] for s in segs}

    def root(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    def join(a, b):
        ra, rb = root(a), root(b)
        if ra != rb:
            par[ra] = rb
    by_street = {}
    ends = defaultdict(list)
    for s in segs:
        if s.get("street"):
            if s["street"] in by_street:
                join(s["id"], by_street[s["street"]])
            else:
                by_street[s["street"]] = s["id"]
        P = s["pts"]
        for nd, p0, p1 in ((s["a"], P[0], P[1]), (s["b"], P[-1], P[-2])):
            ends[nd].append((math.atan2(p1[1] - p0[1], p1[0] - p0[0]), s["id"]))
    for nd, es in ends.items():
        pairs = []
        for i in range(len(es)):
            for j in range(i + 1, len(es)):
                dev = abs((es[i][0] - es[j][0]) % (2 * math.pi) - math.pi)      # 0: straight on
                if dev <= math.radians(STREET_ON_DEG) and es[i][1] != es[j][1]:
                    pairs.append((dev, i, j))
        used = set()
        for _, i, j in sorted(pairs):
            if i not in used and j not in used:
                used |= {i, j}
                join(es[i][1], es[j][1])
    return {k: root(k) for k in par}
HARD_GAP_M = 0.1          # a green keeps this far off hard ground (m), past the overlap tolerance at the edge: модель qTwin
NOPLANT_MIN_M2 = 0.5      # m²: no-plant parts kept down to this, under rule 19's tolerance (a 2 m² end of an HV zone was lost at 5) — модель qTwin


def no_holes(poly, min_area=1.0):
    return U.no_holes(poly, min_area)


def sector(apex, dir_deg, fov_deg, length):
    """View sector; dir_deg is a compass bearing clockwise from north (+Z): 0 = north, 90 = east (spec views_convention)."""
    a0, a1 = math.radians(dir_deg - fov_deg / 2), math.radians(dir_deg + fov_deg / 2)
    pts = [tuple(apex)] + [(apex[0] + length * math.sin(a), apex[1] + length * math.cos(a)) for a in np.linspace(a0, a1, 16)]
    return Polygon(pts)


def centre_polys(spec, norms):
    """District centres: zones of use mixed_centre / business that hold a spec centre point; a centre point in no such zone
    gets a circle of stops.near_destinations_max_m centres (the contract has no centre polygon)."""
    out = []
    for c in spec.get("centres", []):
        p = Point(c["x"], c["z"])
        hit = [U.from_coords(z["polygon"]) for z in spec["zones"] if z["use"] in ("mixed_centre", "business") and U.from_coords(z["polygon"]).buffer(1).contains(p)]
        out.append(unary_union(hit) if hit else p.buffer(norms.v("stops.near_destinations_max_m", "centres")))
    return U.clean(unary_union(out)) if out else Polygon()


def run(d, out, spec_path=None):
    t0 = time.time()
    spec = U.load_spec(d, spec_path)
    norms = U.Norms()
    log = U.Log()
    od = U.out_dir(out, d)
    net = U.read_json(os.path.join(od, "network.json"))
    lots_doc = U.read_json(os.path.join(od, "lots.json"))
    bdoc = U.read_json(os.path.join(od, "buildings.json"))
    lrt = U.read_json(os.path.join(od, "lrt.json"))
    if not (net and lots_doc and bdoc):
        raise SystemExit("run gen_blocks_lots and gen_buildings first")
    work = U.work_polygon(spec)
    blocks = {b["id"]: b for b in (U.read_json(os.path.join(od, "blocks.json")) or {}).get("blocks", [])}
    zones = {z["id"]: (z, U.zone_rules(z)) for z in spec["zones"]}
    lots = lots_doc["lots"]
    for L in lots:
        L["_p"] = U.geom(L)
    by_lot = defaultdict(list)
    for b in bdoc["buildings"]:
        b["_p"] = U.from_coords(b["footprint"])
        if b["lot"]:
            by_lot[b["lot"]].append(b)
    segs = {s["id"]: s for s in net["segments"]}
    # driveways (land_driveways.py) take land: parking and yards keep off their sidewalks and turnaround pads
    drv = U.read_json(os.path.join(od, "driveways.json")) or {"segments": [], "pads": []}
    drive_land = U.clean(unary_union([p for _, p, _ in U.network_polys(drv, norms, "walk")] +
                                     [U.from_coords(pd["polygon"]) for pd in drv.get("pads", [])]))
    drive_car = U.clean(unary_union([p for _, p, _ in U.network_polys(drv, norms, "carriage")]))
    centre = centre_polys(spec, norms)
    views = U.clean(unary_union([sector(v["apex"], v["dir_deg"], v["fov_deg"], v["len_m"]) for v in spec.get("views", [])])) \
        if spec.get("views") else Polygon()
    sp_open = norms.v("parking.area_m2_per_space", "open")["min"]
    sp_ml = norms.v("parking.area_m2_per_space", "multilevel_underground")["min"]
    garage = norms.v("parking.garage_area_by_floors_m2")
    max_centre = norms.num("parking.ground_lot_max_in_centre")
    school_pk = norms.v("parking.school_2000_places")
    # offices: malls.parking_office «9–17» (С08-22, прил. 8; not_verified, unit ambiguous in the extract) read as spaces per
    # 100 workers, as the appendix gives it for offices (модель qTwin), at its lower bound
    office_per_100 = U._band(str(norms.v("malls.parking_office")["as_printed"]).replace("–", "-").replace("—", "-"))[0]
    office_cnt = Counter()
    typ_school = norms.num("schools.typical_capacity")
    sb_res = norms.v("setbacks.red_line_m", "residential_streets")
    passage = norms.v("fire_access.width_min_m", "default")

    def years_of(L):
        bs = by_lot.get(L["id"]) or []
        new = [b for b in bs if b["source"] != "existing_osm"]
        if new:
            return [min(b["years"][i] for b in new) for i in range(4)]
        return list(L["years"])

    # ------------------------------------------------------------------ parking
    parking, pid = [], 0
    short = Counter()

    def add_pk(typ, cap, lv, poly, L, why=None):
        nonlocal pid
        for part in no_holes(poly):
            c = int(round(cap * part.area / poly.area)) if poly.area > 0 else cap
            parking.append({"id": f"pk{pid:04d}", "type": typ, "cap": c, "levels": int(lv), "polygon": U.coords(part), "lot": L["id"],
                            "years": years_of(L), **({"why": why} if why else {})})
            pid += 1

    for L in lots:
        hub = L.get("hub") or {}
        if L["use"] == "parking" and hub:
            # a transit hub's parking (land_transit, модель qTwin): the P+R deck, or the taxi and kiss-and-ride bays
            cars = int(L["capacity"].get("cars") or 0)
            lp = L["_p"]
            if cars <= 0:
                continue
            free = U.clean(lp.difference(drive_land))
            if hub["part"] == "park_ride":
                in_view = not views.is_empty and lp.intersects(views)
                fp = None
                # the deck's floors from the lot's (parking.garage_area_by_floors_m2): one floor more while its footprint
                # does not fit the lot within the setback, up to the table's top row
                for lv in range(int(hub.get("floors") or LT.PR_FLOORS), LT.PR_FLOORS_MAX + 1):
                    fp_car = LT.garage_row(norms, lv)[0]
                    fp = None if in_view else M.place_rect(U.clean(free.buffer(-sb_res)), cars * fp_car, U.axis(lp)[0], 1.6,
                                                           min_area=cars * fp_car * 0.98)
                    if fp is not None or in_view:
                        break
                if fp is None and not in_view:
                    fp = M.place_rect(U.clean(free.buffer(-sb_res)), cars * fp_car, U.axis(lp)[0], 1.6, min_area=cars * fp_car * 0.5)
                if fp is not None:
                    got = int(min(cars, fp.area // fp_car))
                    add_pk("multi", got, lv, fp, L)
                    cars -= got
                if cars > 0:
                    under = U.clean(lp.buffer(-sb_res))
                    under = lp if under.is_empty else under
                    add_pk("underground", cars, max(1, int(math.ceil(cars * sp_ml / max(under.area, 1.0)))), under, L,
                           "под землёй: " + ("сектор обзора знакового фасада" if in_view else "палуба не помещается на участке"))
            elif not free.is_empty:
                add_pk("surface", cars, 1, free, L)
            continue
        b = blocks.get(L["block"], {})
        z, rules = zones.get(b.get("zone"), (None, {}))
        pk = rules.get("parking") or {}
        bs = by_lot.get(L["id"]) or []
        homes = sum(x["homes"] for x in bs if x["source"] != "existing_osm")
        cars = homes * (pk.get("per_home") or 0)
        office = sum(x["gfa_m2"] for x in bs if x["use"] == "business" and x["kind"] != "retail")
        retail = sum(x["gfa_m2"] for x in bs if x["kind"] == "retail")
        if pk.get("per_100m2_office"):
            cars += office / 100.0 * pk["per_100m2_office"]
        elif office:
            # no zone norm per 100 m²: malls.parking_office per 100 workers (tester item 80), its lower bound
            o_jobs = sum(x["jobs"] for x in bs if x["use"] == "business" and x["kind"] != "retail")
            cars += o_jobs / 100.0 * office_per_100
            office_cnt["jobs"] += o_jobs
            office_cnt["m2"] += office
            office_cnt["cars"] += o_jobs / 100.0 * office_per_100
        if pk.get("per_100m2_retail"):
            cars += retail / 100.0 * pk["per_100m2_retail"]
        elif retail:
            short["retail_m2_without_norm"] += retail
        if L["use"] == "school":
            cars += school_pk["spaces"] * L["capacity"].get("places", 0) / typ_school
        cars = int(math.ceil(cars))
        if cars <= 0:
            continue
        typ = pk.get("type") or ("surface" if L["use"] in U.SOCIAL_USES else "underground")
        lp = L["_p"]
        in_centre = not centre.is_empty and lp.intersects(centre)
        in_view = not views.is_empty and lp.intersects(views)
        bu = unary_union([x["_p"] for x in bs]) if bs else Polygon()
        free = U.clean(lp.buffer(-sb_res).difference(bu.buffer(passage)).difference(views).difference(drive_land))
        if typ in ("surface", "multi") and not free.is_empty:
            fparts = sorted(U.polys(free, 50.0), key=lambda q: -q.area)
        else:
            fparts = []
        rest = cars
        if typ == "multi" and fparts and not in_view:
            for fl_key in sorted(garage, key=lambda k: U._band(k)[0] if "-" in k else float(k)):
                per = U.num(garage[fl_key], ("min", "value")) if not isinstance(garage[fl_key], list) else garage[fl_key][0]
                need = rest * per
                if need <= fparts[0].area * 0.9:
                    ang = U.axis(lp)[0]
                    fp = M.place_rect(fparts[0], need, ang, 1.6, min_area=need * 0.7)
                    if fp is not None:
                        lv = int(str(fl_key).split("-")[-1]) if "-" in str(fl_key) else int(fl_key)
                        got = int(min(rest, fp.area / per))
                        add_pk("multi", got, lv, fp, L)
                        rest -= got
                        break
        if typ == "surface" and fparts and not in_view:
            allow = rest if not in_centre else min(rest, int(max_centre))
            if allow > 0:
                fp = M.place_rect(fparts[0], allow * sp_open, U.axis(lp)[0], 2.0, min_area=sp_open * 4)
                if fp is not None:
                    got = int(min(allow, fp.area // sp_open))
                    add_pk("surface", got, 1, fp, L)
                    rest -= got
        if rest > 0:
            under = U.clean(lp.buffer(-sb_res))
            if under.is_empty:
                under = lp
            lv = max(1, int(math.ceil(rest * sp_ml / max(under.area, 1.0))))
            why = None
            if typ != "underground":
                why = "под землёй: " + ("сектор обзора знакового фасада" if in_view else "центр района" if in_centre and typ == "surface" else "нет свободной земли на участке")
            add_pk("underground", rest, lv, under, L, why)
    if office_cnt:
        log(f"парковки офисов: {office_per_100:g} машино-мест на 100 работающих (malls.parking_office «9–17», нижняя граница; "
            "единица «на 100 работающих» — модель qTwin, норма not_verified)", [], office_m2=round(office_cnt["m2"]),
            office_jobs=round(office_cnt["jobs"]), cars=round(office_cnt["cars"]))
    if short:
        log("парковки торговли не посчитаны: норма не проверена и единица неясна (malls.parking_mall: not_verified)", [],
            **{k: round(v) for k, v in short.items()}, warn=True)

    # ------------------------------------------------------------------ stops
    stops = []
    spacing = norms.v("stops.spacing_m", "bus_trolley_tram")["min"]
    walk = norms.v("stops.walk_max_m", "default")
    # demand weight: residents of new homes and of existing (village) houses alike (GFA / the twin's m² per resident)
    m2_res = U.twin_m2()[0]
    homes_pts = np.array([[x["_p"].centroid.x, x["_p"].centroid.y, x["gfa_m2"] / m2_res] for x in bdoc["buildings"]
                          if x["homes"] > 0 or (x["source"] == "existing_osm" and x["use"] in ("existing", "housing"))] or np.zeros((0, 3)))
    carr = U.clean(unary_union([p for _, p, lv in U.network_polys(net, norms, "carriage") if lv == 0]))
    # carriageways, drives and buildings, each indexed: «within 0.5 m of any» (no union of the whole district buffered)
    occ_tree = U.strtree([g for g in [carr, drive_car] + [b["_p"] for b in bdoc["buildings"]] if not g.is_empty])
    # every house within stops.walk_max_m of a stop on foot, as rule 14 walks it (WalkNet from the house centre): the stops
    # that reach the most residents no stop reaches yet first (greedy cover, lazy: the straight-line weight bounds the
    # walking one), then the rest of the street by density as before, each at least stops.spacing_m from the others
    # (Gate G7: houses 10–100 m from a bus street and 100–400 m from a stop by straight line walked 500–900 m to it)
    wnet = U.WalkNet(net)
    hP = wnet.points([(float(q[0]), float(q[1])) for q in homes_pts]) if len(homes_pts) else None
    from scipy.spatial import cKDTree
    h_tree = cKDTree(homes_pts[:, :2]) if len(homes_pts) else None
    cand = []
    for s in net["segments"]:
        if s["class"] not in U.TRANSIT_CLASSES and s["class"] not in VILLAGE_BUS:
            continue
        pr = U.seg_profile(net, s, norms)
        ls = U.seg_line(s)
        if ls.length < 40:
            continue
        # on the sidewalk of the right-hand side (profile side 1; a divided road's carriageway has its sidewalk there); a village
        # street without one gets the stop pad at the carriageway edge
        off = U.carriage_half(pr) + pr["verge_w"][1] + (pr["sidewalk_w"][1] / 2.0 if pr["sidewalk_w"][1] > 0 else STOP_PAD_W / 2.0)
        for t in np.arange(20.0, ls.length - 20.0, STOP_STEP_M):
            p = ls.interpolate(t)
            q = ls.interpolate(min(ls.length, t + 1.0))
            dx, dz = q.x - p.x, q.y - p.y
            n = math.hypot(dx, dz) or 1.0
            x, z = p.x + dz / n * off, p.y - dx / n * off          # right-hand side of the direction a → b
            if not work.contains(Point(x, z)) or len(occ_tree.query(Point(x, z), predicate="dwithin", distance=0.5)):
                continue           # off the area, or the sidewalk point falls on another carriageway / into a building
            ii = np.array(sorted(h_tree.query_ball_point((x, z), walk)), dtype=np.int64) if h_tree is not None else np.zeros(0, np.int64)
            w = float(homes_pts[ii, 2].sum()) if len(ii) else 0.0
            cand.append((w, x, z, s, ii))
    wt = homes_pts[:, 2] if len(homes_pts) else np.zeros(0)

    def walk_cover(k):
        """The houses within walk of candidate k on foot (indices into homes_pts)."""
        _, x, z, _, ii = cand[k]
        if not len(ii):
            return ii
        A, B, al, rest, pe, by_seg = hP
        d = wnet.dist_many((A[ii], B[ii], al[ii], rest[ii], pe[ii], by_seg.subset(ii)), wnet.dist_from([(x, z)], walk + 1.0))
        return ii[d <= walk]

    chosen = []
    # the stops that bring houses within the walk keep stops.spacing_m between the stops of one street (bus_streets), not
    # across streets: a stop on a parallel street 300 m off barred the one that brought the houses of the next street within
    # the walk (Gate r4: 13,651 residents not reached, 43 blocks of rule 14, houses 11–300 m from a bus street and
    # 500–1,300 m from a stop); the fill by density keeps it from every stop, as before (per street it put 813 stops on
    # Gate's streets, five times as many)
    street = bus_streets(net, U.TRANSIT_CLASSES | VILLAGE_BUS)

    def spaced(x, z, s, own_street=False):
        k = street.get(s["id"], s["id"])
        return not any((not own_street or street.get(t["id"], t["id"]) == k) and math.hypot(x - a, z - b) < spacing
                       for a, b, t in chosen)
    covered = np.zeros(len(wt), dtype=bool)
    exact = {}
    taken = set()
    heap = [(-c[0], c[1], c[2], k) for k, c in enumerate(cand) if c[0] > 0]
    heapq.heapify(heap)
    while heap:
        nw, x, z, k = heapq.heappop(heap)
        if not spaced(x, z, cand[k][3], own_street=True):
            continue                # the stops chosen only grow: this point stays too near one
        if k not in exact:
            exact[k] = walk_cover(k)
        jj = exact[k]
        cur = float(wt[jj[~covered[jj]]].sum())
        if cur <= 1e-9:
            continue
        if cur < -nw - 1e-9:
            heapq.heappush(heap, (-cur, x, z, k))
            continue
        chosen.append((x, z, cand[k][3]))
        taken.add(k)
        covered[jj] = True
    n_cover = len(chosen)
    for k in sorted(range(len(cand)), key=lambda k: (-cand[k][0], cand[k][1], cand[k][2])):
        w, x, z, s, _ = cand[k]
        if w <= 0:
            break
        if k not in taken and spaced(x, z, s):
            chosen.append((x, z, s))
    log(f"остановки: сначала те, что приводят пешком в {walk:g} м (stops.walk_max_m, по сети, как правило 14) больше жителей без "
        f"остановки (на одной улице не ближе {spacing:g} м друг к другу, stops.spacing_m), затем остальная улица по плотности, "
        f"не ближе {spacing:g} м от любой остановки", [],
        cover=n_cover, total=len(chosen), residents=round(float(wt.sum())), residents_not_reached=round(float(wt[~covered].sum())))
    for i, (x, z, s) in enumerate(chosen):
        stops.append({"id": f"st{i:03d}", "kind": "bus", "x": round(x, 1), "z": round(z, 1), "segment": s["id"], "years": list(s["years"])})
    for Ln in (lrt or {}).get("lines", []):
        for stn in Ln.get("stations", []):
            if work.contains(Point(stn["x"], stn["z"])):
                stops.append({"id": stn["id"], "kind": "lrt", "x": stn["x"], "z": stn["z"], "segment": None, "years": list(Ln.get("years") or U.EXISTING_YEARS)})
    for L in lots:
        hub = L.get("hub") or {}
        if hub.get("stop"):
            # a hub's stop: the rail station at its platform (hall part), the bus station at its boarding island
            kind = "rail" if hub.get("kind") == "rail" and hub["part"] == "hall" else "bus"
            stops.append({"id": f"{kind}_{hub['of']}", "kind": kind, "x": hub["stop"][0], "z": hub["stop"][1], "segment": L.get("access"),
                          "years": list(L["years"])})
        elif L["use"] == "transit" and L["source"] == "registry" and not hub:
            c = L["_p"].representative_point()
            stops.append({"id": "rail_" + str(L.get("registry_id") or L["id"]), "kind": "rail", "x": round(c.x, 1), "z": round(c.y, 1),
                          "segment": L.get("access"), "years": list(L["years"])})

    # ------------------------------------------------------------------ greens, plazas
    greens, gid = [], 0
    pk_by_lot = defaultdict(list)
    for p_ in parking:
        if p_["type"] != "underground":
            pk_by_lot[p_["lot"]].append(U.from_coords(p_["polygon"]))

    # hard ground a green keeps off (rule 19's set: walk bands of level-0 streets, every building — existing houses on no lot
    # and the twin's own included — and ground LRT): a park, square or buffer green took its lot polygon as it is, so a house
    # left standing on park land or a street crossing the lot came out under trees (Gate: g0416, g0556, g0557, g1165, g0597)
    w_lrt_g = norms.num("lrt.corridor_width_m", "double_track")
    hard = [p for _, p, lv in U.network_polys(net, norms, "walk") if lv == 0] + [b["_p"] for b in bdoc["buildings"]]
    for Ln in (lrt or {}).get("lines", []):
        ls_ = LineString([(q[0], q[1]) for q in Ln["pts"]])
        hard += [shapely.ops.substring(ls_, max(0, s_["from_m"]), min(ls_.length, s_["to_m"])).buffer(w_lrt_g / 2, cap_style="flat")
                 for s_ in Ln.get("sections", []) if s_["kind"] == "ground" and s_["to_m"] - s_["from_m"] > 1]
    hard = [g for g in hard if not g.is_empty]
    hard_tree = U.strtree(hard) if hard else None

    def add_green(kind, poly, years, lot=None):
        nonlocal gid
        poly = U.clean(poly)
        hit = hard_tree.query(poly, predicate="intersects") if hard_tree is not None and not poly.is_empty else []
        if len(hit):
            poly = U.clean(poly.difference(U.clean(unary_union([hard[int(j)] for j in hit]).buffer(HARD_GAP_M, join_style="mitre"))))
        for part in U.polys(poly, 20.0):        # holes kept (courtyards around buildings): `holes` field
            greens.append({"id": f"g{gid:04d}", "kind": kind, **U.poly_fields(part), "years": list(years), "lot": lot})
            gid += 1

    plazas = []
    for L in lots:
        u, lp = L["use"], L["_p"]
        if u in ("park", "reserve"):
            lab = L.get("label_ru") or ""
            kind = "buffer" if (L.get("nobuild") or lab.startswith("клин")) else "park"
            if u == "reserve":
                continue
            add_green(kind, lp, L["years"] if kind != "buffer" else U.EXISTING_YEARS, L["id"])
        elif u in ("square", "playground"):
            add_green("square", lp, L["years"], L["id"])
        elif u in ("sport_ground", "sport"):
            add_green("sport", lp, L["years"], L["id"])
        elif u in U.RESIDENTIAL_USES and L["source"] == "rule" and by_lot.get(L["id"]):
            occ = unary_union([x["_p"] for x in by_lot[L["id"]]] + pk_by_lot.get(L["id"], []))
            yard = U.clean(lp.buffer(-sb_res).difference(occ.buffer(passage)).difference(drive_land))
            add_green("yard", yard, years_of(L), L["id"])
        elif u == "transit" and (L.get("hub") or {}).get("part") == "tracks":
            pl = (L.get("hub") or {}).get("platform")
            if pl:
                plazas.append({"id": f"pl{len(plazas):03d}", "polygon": pl, "lot": L["id"], "years": list(L["years"])})
        elif u == "transit":
            occ = unary_union([x["_p"] for x in by_lot.get(L["id"], [])]) if by_lot.get(L["id"]) else Polygon()
            for part in no_holes(U.clean(lp.difference(occ.buffer(passage))), 100.0):
                plazas.append({"id": f"pl{len(plazas):03d}", "polygon": U.coords(part), "lot": L["id"], "years": list(L["years"])})

    # ------------------------------------------------------------------ no-plant
    noplant = []

    def add_np(poly, why, years):
        for part in no_holes(U.clean(poly.intersection(work)), NOPLANT_MIN_M2):
            noplant.append({"polygon": U.coords(part), "why": why, "years": list(years)})

    for c in U.corridors(spec):
        if c.get("state") == "cable":
            continue
        w = U.power_zone_m(norms, c)[0] if c["kind"] == "power_line" else c.get("width_m")
        add_np(LineString(c["line"]).buffer(w if w else 1.0, cap_style="flat"),
               "охранная зона ЛЭП" + ("" if w else " (ширина не задана в norms.json — только ось ± 1 м)"), U.EXISTING_YEARS)
    w_lrt = norms.num("lrt.corridor_width_m", "double_track")
    for Ln in (lrt or {}).get("lines", []):
        ls = LineString([(p[0], p[1]) for p in Ln["pts"]])
        for s in Ln.get("sections", []):
            if s["kind"] == "ground" and s["to_m"] - s["from_m"] > 1:
                add_np(shapely.ops.substring(ls, max(0, s["from_m"]), min(ls.length, s["to_m"])).buffer(w_lrt / 2, cap_style="flat"),
                       "пути ЛРТ на земле", Ln.get("years") or U.EXISTING_YEARS)
    for L in lots:
        if (L.get("hub") or {}).get("part") == "tracks":
            add_np(L["_p"], "пути ж/д (резерв до трассы линии)", L["years"])
    wpol, wlin = U.water_geoms(work)
    for g in wpol:
        add_np(g, "вода", U.EXISTING_YEARS)
    for p_ in parking:
        if p_["type"] != "underground":
            add_np(U.from_coords(p_["polygon"]), "стоянка", p_["years"])
    for p_ in plazas:
        add_np(U.from_coords(p_["polygon"]), "площадь у станции", p_["years"])
    for g in greens:
        if g["kind"] == "sport":
            add_np(U.from_coords(g["polygon"]), "спортплощадка", g["years"])
    for k in spec.get("keep", []):
        add_np(U.from_coords(k["polygon"]), "земля keep: своё благоустройство (" + k["id"] + ")", U.EXISTING_YEARS)

    T = {"parking": dict(Counter(p_["type"] for p_ in parking)),
         "parking_cap": {t: sum(p_["cap"] for p_ in parking if p_["type"] == t) for t in ("surface", "multi", "underground")},
         "stops": dict(Counter(s["kind"] for s in stops)), "greens": dict(Counter(g["kind"] for g in greens)),
         "plazas": len(plazas), "noplant": len(noplant)}
    doc = {"schema": "qtwin.features/1", "district": d, "parking": parking, "stops": stops, "greens": greens, "plazas": plazas,
           "noplant": noplant, "log": log.rows, "totals": T, "made_by": "w44 gen_masks.py"}
    U.write_json(os.path.join(od, "features.json"), doc)
    print(f"{d}: parking {T['parking_cap']}, stops {T['stops']}, greens {T['greens']}, plazas {len(plazas)}, noplant {len(noplant)}; "
          f"{time.time() - t0:.1f} s")
    return doc


if __name__ == "__main__":
    a = U.cli(__doc__).parse_args()
    run(a.district, a.out, a.spec)
