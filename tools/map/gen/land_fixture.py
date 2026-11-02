"""Level-1 proof fixture of the land tools (w44): the trial quarter at Iconic's new place, built from today's twin data.

    python3 tools/map/gen/land_fixture.py [--out OUT]

Writes
  tools/map/tests/fixture_gate_trial.json      spec v1 (CONTRACT §3) for district id gate_trial: area = box x −4200…−1700,
                                               z −20600…−18300; zones of spec/gate.json clipped to it with zone rules; the Gate
                                               District quarter as a `keep` polygon (gate_district.bytes mask, shifted by Δ = (−330, −420),
                                               CONTRACT §7); objects of the registry inside the box; one view sector; power-line corridors.
  OUT/_fixtures/gate_trial/network.json        CONTRACT §4 network built from the twin's roads.json edges inside the box (classes
                                               highway → expressway, ring → expressway, main → arterial_regulated, street → local;
                                               profiles from norms.street_profiles) plus the existing village streets of Overture inside
                                               village zones. It stands in for w43's gen_network until that exists.
  OUT/_fixtures/gate_trial/lrt.json            CONTRACT §4 lrt from spec/gate.json lrt (ground, elevated across the expressways).

Everything new here is «модель qTwin» (a fixture), not a design."""
import gzip
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box  # noqa: E402
from shapely.ops import linemerge, substring, unary_union  # noqa: E402

import land_util as U  # noqa: E402

BOX = (-4200.0, -20600.0, -1700.0, -18300.0)
ICONIC_NEW, ICONIC_YAW, DELTA = (-3500.0, -19500.0), 270.0, (-330.0, -420.0)
FIXTURE_SPEC = os.path.join(U.MAP, "tests", "fixture_gate_trial.json")
TWIN_CLASS = {"highway": "expressway", "ring": "expressway", "main": "arterial_regulated", "street": "local"}
OSM_VILLAGE = {"tertiary": "village_main", "unclassified": "village_main", "residential": "village_secondary",
               "living_street": "village_secondary", "service": "village_lane", "track": "village_lane"}

# Zone rules of the fixture (the cartographer's part of a v1 spec). Numbers of norms are read from norms.json by key below;
# the typology choices (lot_split, parking type) follow the plan: centres underground/multi-storey, surface only at edges.
USE_RULES = {
    "mixed_centre": ("perimeter", "underground"), "business": ("towers", "underground"), "residential_high": ("towers", "underground"),
    "residential_mid": ("perimeter", "multi"), "residential_low": ("rows", "surface"), "village_existing": ("houses", "surface"),
    "logistics": ("industrial", "surface"), "industry": ("industrial", "surface"), "medical": ("campus", "multi"),
    "campus": ("campus", "multi"), "park": ("none", None), "utility": ("none", None), "reserve": ("none", None),
    "waterfront": ("perimeter", "multi"), "sport": ("campus", "surface")}


def to_world(lx, lz, cx, cz, yaw):
    """IconicDistrict: world = org + Euler(0, yaw, 0) · (lx, 0, lz) (as tools/map/scheme/gate_scheme.py)."""
    a = math.radians(yaw)
    return cx + lx * math.cos(a) + lz * math.sin(a), cz - lx * math.sin(a) + lz * math.cos(a)


def quarter_keep():
    """Gate District quarter: the mask of Resources/Landmarks/gate_district.bytes (QGD1) placed on Iconic's new centre.
    The quarter moves rigidly with Iconic (Δ = (−330, −420), yaw 270 kept), so the mask is laid around (−3500, −19500)."""
    import frames
    b = gzip.open(frames.asset("Resources/Landmarks/gate_district.bytes")).read()
    assert b[:4] == b"QGD1"
    o = 4
    nv, ni = struct.unpack_from("<ii", b, o); o += 8
    o += nv * 12 + nv * 3 + nv * 4 + nv + ni * 4
    nt = struct.unpack_from("<i", b, o)[0]; o += 4 + nt * 20
    W = struct.unpack_from("<i", b, o)[0]; o += 4
    half = struct.unpack_from("<f", b, o)[0]; o += 4
    M = np.frombuffer(b, dtype=np.uint8, count=W * W, offset=o).reshape(W, W) > 127
    cell = 2 * half / W
    iz, ix = np.nonzero(M)
    sq = []
    for a, c in zip(ix, iz):
        lx0, lz0 = a * cell - half, c * cell - half
        corners = [to_world(lx0 + dx, lz0 + dz, ICONIC_NEW[0], ICONIC_NEW[1], ICONIC_YAW) for dx, dz in ((0, 0), (cell, 0), (cell, cell), (0, cell))]
        sq.append(Polygon(corners))
    poly = U.clean(unary_union(sq)).buffer(0.5).buffer(-0.5).simplify(1.5)
    poly = max(U.polys(poly), key=lambda q: q.area)
    poly = Polygon(poly.exterior)
    # attach points: ends of the quarter's own streets (Resources/Film/Traffic/gate_roads.json, local frame) on its rim
    gr = U.read_json(frames.asset("Resources/Film/Traffic/gate_roads.json"))
    ends = []
    for r in gr["roads"]:
        p = r["p"]
        pts = [(p[i], p[i + 2]) for i in range(0, len(p), 3)]
        for q in (pts[0], pts[-1]):
            if math.hypot(*q) > 300:
                w = to_world(q[0], q[1], ICONIC_NEW[0], ICONIC_NEW[1], ICONIC_YAW)
                if all(math.hypot(w[0] - e[0], w[1] - e[1]) > 25 for e in ends):
                    ends.append(w)
    return poly, ends, float(M.sum() * cell * cell)


def zones_in(gate, work, norms, fh):
    zones = []
    keep_ids = set()
    for z in gate["zones"]:
        p = U.clean(Polygon(z["polygon"]))
        q = U.clean(p.intersection(work))
        parts = U.polys(q, 50.0)
        if not parts:
            continue
        for k, part in enumerate(sorted(parts, key=lambda t: -t.area)):
            zid = z["id"] if k == 0 else f"{z['id']}~{k}"
            zz = {"id": zid, "use": z["use"], "name_ru": z.get("name_ru"), "polygon": U.coords(part), "density": z.get("density", {}),
                  "years": z.get("years"), "why": "spec/gate.json v0, обрезано по area (фикстура w44)"}
            zz["rules"] = rules_for(zz, norms, fh)
            zones.append(zz)
            keep_ids.add(zid)
    return zones


def rules_for(z, norms, fh):
    use = z["use"]
    d = z.get("density") or {}
    split, ptype = USE_RULES.get(use, ("none", None))
    ft = d.get("floors_typical")
    r = {"lot_split": split}
    if ft:
        lo = 1 if ft <= 2 else max(2, int(round(ft * 0.6)))
        hi = ft if ft <= 2 else int(round(ft * 1.5))
        if use == "residential_low":
            lo, hi = 2, min(ft, 4)
        r["floors"] = [lo, hi]
        kind = {"business": "tower" if ft >= 16 else "business", "residential_high": "res_high", "mixed_centre": "res_high",
                "residential_mid": "res_mid", "residential_low": "res_mid", "logistics": "industry", "industry": "industry",
                "medical": "health"}.get(use, "res_mid")
        r["height_cap_m"] = round(hi * fh.get(kind, 3.6) + 6.0, 1)
    if d.get("far") is not None:
        r["far"] = d["far"]
    for k in ("homes_per_ha", "jobs_per_ha"):
        if d.get(k) is not None:
            r[k] = d[k]
    if use in ("mixed_centre", "business"):
        bs = norms.v("quarters.block_side_m")
    else:
        bs = norms.v("quarters.r2_grid_synthesis", "local_streets_m")
    r["block_side_m"] = [bs["min"], bs["max"]]
    r["setback_m"] = norms.v("setbacks.red_line_m", "residential_streets")
    if ptype:
        pa = norms.v("residential.parking_per_apartment", "III")
        r["parking"] = {"per_home": pa["min"], "per_100m2_office": None, "per_100m2_retail": None, "type": ptype,
                        "why": "per_home = residential.parking_per_apartment III min; офисы и торговля — нормы не проверены "
                               "(malls.parking_office / malls.parking_mall: not_verified), не задаём"}
    return r


def osm_power(work):
    import layers
    g, p = layers.load("infrastructure")
    out = []
    for gg, pp in zip(g, p):
        if pp.get("class") != "power_line" or not gg.intersects(work):
            continue
        q = gg.intersection(work)
        for part in getattr(q, "geoms", [q]):
            if part.geom_type == "LineString" and part.length > 50:
                out.append((part, pp))
    return out


def build_spec(norms):
    gate = U.load_spec("gate")
    work_box = box(*BOX)
    work = U.clean(U.boundary_poly(gate).intersection(work_box))
    fh = U.floor_heights()
    keep_poly, attach, mask_m2 = quarter_keep()
    zones = zones_in(gate, work, norms, fh)
    # targets of the trial area: the level-0 zone densities over the zone land inside area ∩ boundary (keep land included —
    # the quarter's homes and jobs are counted on its keep lot by the zone density)
    m2_res, m2_job, _, _ = U.twin_m2()
    homes = jobs = 0.0
    for z in zones:
        a = U.from_coords(z["polygon"]).area / 1e4
        homes += a * (z["rules"].get("homes_per_ha") or 0)
        jobs += a * (z["rules"].get("jobs_per_ha") or 0)
    targets = {"homes_2050": int(round(homes)), "population_2050": int(round(homes * U.LEVEL0_HOME_M2 / m2_res)),
               "jobs_2050": int(round(jobs)), "home_m2": U.LEVEL0_HOME_M2,
               "source": "фикстура w44: плотности зон spec/gate.json v0 (homes_per_ha, jobs_per_ha) × площадь зон в area ∩ boundary; "
                         "жители = квартиры × 75 м² / 30 м² (жилая GFA / 30, CityStats); модель qTwin"}
    # LRT v1
    lr = gate["lrt"]
    line = LineString(lr["line"])
    clip = work_box.buffer(300)
    lpart = line.intersection(clip)
    lpart = max(getattr(lpart, "geoms", [lpart]), key=lambda q: q.length)
    sts = [s for s in lr["stations"] if clip.contains(Point(s["x"], s["z"]))]
    lrt = {"lines": [{"id": "lrt_gate_trunk", "line": [[round(x), round(z)] for x, z in lpart.coords], "sections": [],
                      "stations": sts, "ends": [{"kind": "terminus", "id": "trial_edge_n"}, {"kind": "terminus", "id": "trial_edge_s"}],
                      "years": [2031, 2030, 2034, 2029]}], "depots": [],
           "why": "spec/gate.json lrt (ствол Gate–Golden) в пределах area + 300 м; годы — 1-я очередь ЛРТ (city.json lrt_v0 phases); "
                  "концы — края пробной зоны, не депо (фикстура)"}
    objects = []
    wanted = {"iconic_complex": None, "gate_district_ring": None,
              "l7_lotte": {"kind": "landmark", "lot_m2": 90 * 70, "why_lot": "площадка LandmarkData lotte_l7 90 × 70 м"},
              "griffin_logopark": {"kind": "landmark", "lot_m2": 380 * 420, "why_lot": "площадка LandmarkData griffin 380 × 420 м"},
              "agglo_rail_station_1": {"kind": "transit", "lot_m2": None, "why_lot": "размер не найден — участок по правилу зоны"}}
    for o in gate["objects"]:
        if o["registry_id"] in wanted and o.get("to") and work.contains(Point(o["to"])):
            oo = dict(o)
            if wanted[o["registry_id"]]:
                oo.update(wanted[o["registry_id"]])
            objects.append(oo)
    corridors = []
    for i, (ln, pp) in enumerate(osm_power(work)):
        cable = ln.distance(keep_poly) < 400 or ln.intersects(keep_poly)
        corridors.append({"id": f"pl_{i + 1}", "kind": "power_line", "line": [[round(x, 1), round(z, 1)] for x, z in ln.coords],
                          "state": "cable" if cable else "overhead", "width_m": None, "source": "osm:" + pp["id"],
                          "why": ("решение владельца 31.10: ВЛ 220 кВ через центр Gate уходит в кабель (в красных линиях улиц)" if cable else
                                  "существующая ВЛ; ширина охранной зоны в norms.json не задана (utilities.power_line_protection_zone_m: not_verified)")})
    spec = {"district": "gate_trial", "version": 1, "fixture": True,
            "made_by": "w44 tools/map/gen/land_fixture.py (фикстура уровня 1; настоящий gate_trial.json пишет w47)",
            "boundary": "city.json#districts/gate", "area": [[BOX[0], BOX[1]], [BOX[2], BOX[1]], [BOX[2], BOX[3]], [BOX[0], BOX[3]]],
            "targets": targets, "centres": [c for c in gate["centres"] if work.contains(Point(c["x"], c["z"]))],
            "axes": [], "zones": zones, "lrt": lrt, "objects": objects, "phases": gate.get("phases", []), "joints": [], "edge_joints": [],
            "streets": [], "nodes": [],
            "keep": [{"id": "keep_gate_district", "what_ru": "Квартал Gate District с Iconic Complex (QTwin), сдвинут на Δ = (−330, −420)",
                      "polygon": U.coords(keep_poly), "registry_id": "gate_district_ring", "attach": [{"street_id": None, "x": round(x, 1), "z": round(z, 1)} for x, z in attach],
                      "mask_m2": round(mask_m2), "years": [2026, 2032]}],
            "views": [{"id": "view_iconic_east", "registry_id": "iconic_complex", "apex": list(ICONIC_NEW), "dir_deg": 90.0, "fov_deg": 50.0,
                       "len_m": 700.0, "why": "фасад Iconic со стороны ЛРТ и Проспекта Ворот (модель qTwin, фикстура)"}],
            "corridors": corridors}
    return spec, work, keep_poly


# ------------------------------------------------------------------------------------------------------------- network
STITCH_M = 80.0     # fixture only: a loose street end this close to another street is joined to it (twin streets were drawn
                    # against the twin's own arterials, which the fixture replaces by Overture geometry, and were cut at villages)


def stitch(raw, work, log, forbid=None):
    """Join loose ends of streets to the nearest other street (not to expressways or ramps) with a short connector of class
    local; the target line is split at the joint so the graph has a node there."""
    def key(c):
        return (round(c[0] * 2) / 2, round(c[1] * 2) / 2)
    ends = {}
    for k, (ls, cls, ys, src, oc, lv) in enumerate(raw):
        for c in (ls.coords[0], ls.coords[-1]):
            ends.setdefault(key(c), []).append(k)
    ok = [k for k, r in enumerate(raw) if r[1] not in ("expressway", "ramp") and r[5] == 0]
    tree = shapely.STRtree([raw[k][0] for k in ok])
    splits = {}
    extra = []
    for k, (ls, cls, ys, src, oc, lv) in enumerate(raw):
        if cls in ("expressway", "ramp") or lv:
            continue
        for c in (ls.coords[0], ls.coords[-1]):
            if len(ends[key(c)]) > 1 or work.exterior.distance(Point(c)) < 2:
                continue
            p = Point(c)
            best = None
            for j in tree.query(p.buffer(STITCH_M)):
                t = ok[int(j)]
                if t == k:
                    continue
                d = raw[t][0].distance(p)
                if d > 0.5 and d <= STITCH_M and (best is None or d < best[0]):
                    best = (d, t)
            if best is None:
                continue
            t = best[1]
            tl = raw[t][0]
            s = tl.project(p)
            q = tl.interpolate(s)
            if s < 2.0:
                q = Point(tl.coords[0])
            elif s > tl.length - 2.0:
                q = Point(tl.coords[-1])
            else:
                splits.setdefault(t, set()).add(round(s, 2))
            conn_ls = LineString([c, (q.x, q.y)])
            if forbid is not None and conn_ls.intersects(forbid):
                continue
            yy = [max(a, b) for a, b in zip(ys, raw[t][2])]
            extra.append((conn_ls, "local", yy, "fixture_stitch:" + src, "stitch", 0))
    out = []
    for k, r in enumerate(raw):
        if k not in splits:
            out.append(r)
            continue
        cuts = sorted(splits[k] | {0.0, r[0].length})
        for s0, s1 in zip(cuts[:-1], cuts[1:]):
            if s1 - s0 > 0.5:
                out.append((substring(r[0], s0, s1),) + r[1:])
    if extra:
        log(f"фикстура: {len(extra)} свободных концов улиц соединены с ближайшей улицей (≤ {STITCH_M:.0f} м, класс local)",
            [e[3] for e in extra])
    return out + extra


def build_network(spec, work, keep_poly, norms, log):
    import twin
    import layers
    r = twin.roads()
    village = unary_union([U.from_coords(z["polygon"]) for z in spec["zones"] if z["use"] == "village_existing"]).buffer(15)
    keep_cut = keep_poly.buffer(-2)
    raw = []   # (LineString, class, years, source, original class, level)
    dropped = {}
    for i, e in enumerate(r["edges"]):
        g = e["g"]
        ls = LineString(list(zip(g[0::2], g[1::2])))
        if not ls.intersects(work):
            continue
        if e["c"] != "street":
            dropped.setdefault(e["c"], []).append(f"twin_edge:{i}")
            continue
        q = ls.intersection(work)
        if e["y"][0] > 2025 and q.intersects(village):
            log("фикстура: новая улица двойника не идёт через существующее село (обрезана)", [f"twin_edge:{i}"])
            q = q.difference(village)
        if q.intersects(keep_cut):
            log("фикстура: улица двойника внутри квартала Gate District убрана (полигон keep)", [f"twin_edge:{i}"])
            q = q.difference(keep_cut)
        for part in getattr(q, "geoms", [q]):
            if part.geom_type == "LineString" and part.length > 1.0:
                raw.append((part, TWIN_CLASS[e["c"]], list(e["y"]), f"twin_edge:{i}", e["c"], 0))
    for c, ids in dropped.items():
        log(f"фикстура: рёбра двойника класса {c} заменены дорогами Overture (настоящая геометрия трасс, съездов и путепроводов)", ids)
    # existing roads of Overture: motorways and their links everywhere, the rest inside village zones (split at connectors)
    g, p = layers.load("roads")
    cg, cp = layers.load("connectors")
    conn = {q["i"]: pt for pt, q in zip(cg, cp)}
    sel = np.flatnonzero(shapely.intersects(g, work))
    skipped = []
    for i in sel:
        oc = p[i].get("class")
        if oc == "motorway":
            cls = "ramp" if p[i].get("sub") == "link" else "expressway"
            region = work
        elif oc in ("trunk", "primary"):
            cls, region = "arterial_road_regulated", work
        elif oc == "secondary":
            cls, region = "district_transport", work
        elif oc in OSM_VILLAGE and g[i].intersects(village):
            cls, region = OSM_VILLAGE[oc], village.intersection(work)
        else:
            skipped.append("osm:" + p[i]["id"])
            continue
        lv = int(p[i].get("level") or 0) if p[i].get("bridge") else 0
        line = g[i]
        cuts = sorted({line.project(conn[c]) for c in p[i].get("conn", []) if c in conn} | {0.0, line.length})
        for s0, s1 in zip(cuts[:-1], cuts[1:]):
            if s1 - s0 < 0.5:
                continue
            piece = substring(line, s0, s1).intersection(region)
            for part in getattr(piece, "geoms", [piece]):
                if part.geom_type == "LineString" and part.length > 2:
                    raw.append((part, cls, list(U.EXISTING_YEARS), "keep_existing:osm:" + p[i]["id"], oc, lv))
    if skipped:
        log("фикстура: полевые и служебные дороги Overture вне сёл не взяты", skipped)
    raw = stitch(raw, work, log, keep_cut)
    # nodes by snapped end coordinates; merge chains of equal class and years through degree-2 nodes
    import networkx as nx
    G = nx.MultiGraph()

    def nk(c):
        return (round(c[0] * 2) / 2, round(c[1] * 2) / 2)
    for k, (ls, cls, ys, src, oc, lv) in enumerate(raw):
        a, b = nk(ls.coords[0]), nk(ls.coords[-1])
        if a == b and ls.length < 5:
            continue
        G.add_edge(a, b, key=k, ls=ls, cls=cls, ys=tuple(ys), src=src, lv=lv)
    changed = True
    while changed:
        changed = False
        for n in list(G.nodes):
            if G.degree(n) != 2 or n not in G:
                continue
            es = list(G.edges(n, keys=True, data=True))
            if len(es) != 2:
                continue
            (u1, v1, k1, d1), (u2, v2, k2, d2) = es
            if d1["cls"] != d2["cls"] or d1["ys"] != d2["ys"] or d1["lv"] != d2["lv"] or (u1 == v1) or (u2 == v2):
                continue
            o1 = v1 if u1 == n else u1
            o2 = v2 if u2 == n else u2
            if o1 == n or o2 == n:
                continue
            m = linemerge([d1["ls"], d2["ls"]])
            if m.geom_type != "LineString":
                continue
            G.remove_edge(u1, v1, k1)
            G.remove_edge(u2, v2, k2)
            src = d1["src"] if d1["src"] == d2["src"] else d1["src"].split(",")[0] + "," + d2["src"].split(",")[-1]
            G.add_edge(o1, o2, ls=m, cls=d1["cls"], ys=d1["ys"], src=src, lv=d1["lv"])
            G.remove_node(n)
            changed = True
    T = U.terrain()
    nid = {}
    nodes = []
    for n in G.nodes:
        deg = G.degree(n)
        on_edge = work.exterior.distance(Point(n)) < 2
        kind = "joint" if on_edge else ("end" if deg == 1 else "crossing")
        nid[n] = f"n{len(nodes)}"
        nodes.append({"id": nid[n], "x": n[0], "z": n[1], "y": round(float(T.height(n[0], n[1])), 2), "kind": kind, "ic": None, "r": None})
    profiles, segs = {}, []
    lanes_hint = {"highway": 2 * r["classes"]["highway"]["lanes"]}
    for u, v, d in G.edges(data=True):
        cls = d["cls"]
        pid = cls
        if pid not in profiles:
            profiles[pid] = U.profile_from_norms(norms, cls, lanes_hint.get("highway") if cls == "expressway" else None)
        ls = d["ls"]
        if nk(ls.coords[0]) != u:
            ls = LineString(list(ls.coords)[::-1])
        P = np.asarray(ls.coords)
        y = T.height(P[:, 0], P[:, 1])
        kind = "ground"
        if d["lv"] > 0:
            kind = "overpass"
            y = y + norms.num("bridges.road_clearance_m") + 1.0
        segs.append({"id": f"s{len(segs)}", "a": nid[u], "b": nid[v], "class": cls, "pid": pid, "oneway": False,
                     "pts": [[round(float(x), 1), round(float(z), 1), round(float(yy), 2)] for (x, z), yy in zip(P, y)],
                     "struct": [{"from_m": 0.0, "to_m": round(ls.length, 1), "kind": kind}], "years": list(d["ys"]),
                     "name_ru": None, "street": None, "ic": None, "source": d["src"]})
    net = {"schema": "qtwin.network/1", "district": "gate_trial", "area": spec["area"], "fixture": True,
           "made_by": "w44 land_fixture.py: рёбра roads.json двойника внутри area (классы по таблице, профили из norms.street_profiles) "
                      "+ улицы сёл Overture; без развязок и мостов (двойник плоский)",
           "profiles": profiles, "nodes": nodes, "segments": segs, "interchanges": [],
           "joints": [{"id": f"j{i}", "node": n["id"]} for i, n in enumerate(nodes) if n["kind"] == "joint"], "log": log.rows}
    return net


def build_lrt(spec, net, norms):
    L = spec["lrt"]["lines"][0]
    line = LineString(L["line"])
    expr = unary_union([U.seg_line(s).buffer(U.red_half(U.seg_profile(net, s, norms))) for s in net["segments"] if s["class"] == "expressway"])
    T = U.terrain()
    # sections: elevated where the line crosses the expressway corridors (±150 m), ground elsewhere
    step = 10.0
    n = int(line.length // step) + 1
    ch = np.linspace(0, line.length, n)
    ex2 = expr.buffer(100)
    el = np.array([ex2.contains(line.interpolate(c)) for c in ch])
    secs = []
    cur, start = el[0], 0.0
    for c, e in zip(ch[1:], el[1:]):
        if e != cur:
            secs.append({"from_m": round(start, 1), "to_m": round(c, 1), "kind": "elevated" if cur else "ground"})
            cur, start = e, c
    secs.append({"from_m": round(start, 1), "to_m": round(line.length, 1), "kind": "elevated" if cur else "ground"})
    L["sections"] = [{"from": [round(line.interpolate(s["from_m"]).x), round(line.interpolate(s["from_m"]).y)],
                      "to": [round(line.interpolate(s["to_m"]).x), round(line.interpolate(s["to_m"]).y)], "kind": s["kind"]} for s in secs]
    P = np.asarray(line.coords)
    pts = []
    for x, z in P:
        c = line.project(Point(x, z))
        lift = 0.0
        for s in secs:
            if s["from_m"] <= c <= s["to_m"] and s["kind"] == "elevated":
                lift = norms.num("lrt.viaduct_clearance_over_road_m") + 2.0
        pts.append([round(float(x), 1), round(float(z), 1), round(float(T.height(x, z)) + lift, 2)])
    plat = norms.v("lrt.platform_length_m", "min")
    sts = [{"id": s["id"], "name_ru": s["name_ru"], "x": s["x"], "z": s["z"], "chain_m": round(line.project(Point(s["x"], s["z"])), 1),
            "platform_m": plat, "kind": "ground"} for s in L["stations"]]
    for s in sts:
        for q in secs:
            if q["from_m"] <= s["chain_m"] <= q["to_m"]:
                s["kind"] = q["kind"]
    return {"schema": "qtwin.lrt/1", "fixture": True, "lines": [{"id": L["id"], "pts": pts, "sections": secs, "stations": sts,
                                                                    "ends": L["ends"], "years": L["years"]}], "depots": []}


def main():
    ap = U.argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(U.OUT, "_fixtures"))
    a = ap.parse_args()
    norms = U.Norms()
    log = U.Log()
    spec, work, keep_poly = build_spec(norms)
    os.makedirs(os.path.dirname(FIXTURE_SPEC), exist_ok=True)
    with open(FIXTURE_SPEC, "w", encoding="utf-8", newline="\n") as f:
        U.json.dump(spec, f, ensure_ascii=False, indent=1)
        f.write("\n")
    od = U.out_dir(a.out, "gate_trial")
    net = build_network(spec, work, keep_poly, norms, log)
    U.write_json(os.path.join(od, "network.json"), net)
    lrt = build_lrt(spec, net, norms)
    U.write_json(os.path.join(od, "lrt.json"), lrt)
    print(f"fixture spec {FIXTURE_SPEC}: {len(spec['zones'])} zones, {len(spec['objects'])} objects, keep {len(spec['keep'])}, "
          f"targets {spec['targets']['homes_2050']} homes / {spec['targets']['jobs_2050']} jobs")
    print(f"network {len(net['nodes'])} nodes, {len(net['segments'])} segments, log {len(net['log'])}; lrt {len(lrt['lines'][0]['stations'])} stations")


if __name__ == "__main__":
    main()
