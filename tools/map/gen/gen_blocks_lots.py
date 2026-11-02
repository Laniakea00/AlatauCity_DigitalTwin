"""Blocks and lots of a district (w44, CONTRACT §4): python3 tools/map/gen/gen_blocks_lots.py <district> [--out OUT] [--spec S]

Reads   spec (zones, objects, keep, corridors), OUT/<d>/network.json (red lines), OUT/<d>/lrt.json (ground corridor, optional),
        level-0 water (Overture), terrain, the twin's existing houses (buildings.csv existing_osm + Overture not in the twin).
Writes  OUT/<d>/blocks.json  {schema:"qtwin.blocks/1", blocks:[{id, zone, use, polygon, area_m2}]}
        OUT/<d>/lots.json    {schema:"qtwin.lots/1", lots:[{id, block, use, polygon, grade_y, years, registry_id, source, capacity,
                              access, terraces?}], log:[…]}

Steps
 1. work = area ∩ boundary; minus red lines of every segment (network profiles), the LRT ground corridor, water, keep polygons.
 2. Each remaining piece is cut by the zones; each part is a block with the zone's id and use; parts outside every zone are
    «reserve» blocks with a label; slivers become green buffers (rule 2: no nameless land).
 3. Lots, in this order: keep polygons (source keep, use landmark); registry objects with lot_m2 (source registry); existing houses
    (source existing; villages split between houses); water-protection strips, flood land and overhead power corridors (green
    buffers, no buildings); the rest by the zone's lot_split (source rule).
 4. Service lots carved from the block rests before they are split (place_services): school, kindergarten, polyclinic,
    pharmacy/shop, fire station, playground; walking coverage on the network (fire station: straight line), capacity from places
    per 1000 residents within the norms' smallest band and typical capacity, plots from the plot norms, school and kindergarten
    plots away from arterial carriageways and on the side with land clear of the red-line setback; one-group built-in
    kindergartens (kindergartens.placement) for multi-storey homes no standalone site reaches. Then the rests are split.
 5. Grade per lot (mid-range of the terrain); buildable lots whose cut or fill exceeds validator.grading.cut_fill_max_m are split
    across the slope (repeatedly); lots that must stay whole (social, registry) get terraces; parks, gardens, corridors and
    existing plots stay at the terrain (natural: true). Every polygon is hole-free (CONTRACT polygons are exterior rings).
 6. Years: the lot is formed when its access street opens and not before its zone's first year (per scenario)."""
import math
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon  # noqa: E402
from shapely.ops import unary_union, voronoi_diagram  # noqa: E402

import land_models as LM  # noqa: E402
import land_transit as LT  # noqa: E402
import land_util as U  # noqa: E402


# ----------------------------------------------------------------------------------------------------------- inputs
SHED_MAX_M2 = 25.0     # Overture footprints under this are sheds, not houses (orchestrator decision for Stage 7, 31.10)


def existing_houses(work, keep_union, log=None):
    """Existing houses inside the work polygon: the twin's existing_osm rows (mesh footprints) and every Overture building
    that the twin does not have (machine-detected footprints included), each of at least SHED_MAX_M2 (CONTRACT §8: a house is
    25 m² or more); smaller ones are sheds, left out with a log line (they may be removed). Returns [{fp, bid|None, src}]."""
    import layers
    import twin
    df = twin.buildings()
    x0, z0, x1, z1 = work.bounds
    m = (df.source == "existing_osm") & (df.x > x0 - 50) & (df.x < x1 + 50) & (df.z > z0 - 50) & (df.z < z1 + 50)
    rows = df[m]
    fps = twin.footprints(rows.bid.values)
    fl_by_bid = dict(zip(rows.bid.values.tolist(), rows.floors.values.tolist()))
    out = []
    sheds = []
    tw_all = []           # every twin footprint (sheds too): an Overture copy of a twin shed is the same shed
    for b in rows.bid.values:
        p = fps.get(int(b))
        if p is None or p.geom_type != "Polygon" or not work.contains(p.centroid):
            continue
        tw_all.append(p)
        if p.area < SHED_MAX_M2:
            sheds.append(f"twin:{int(b)}")
            continue
        out.append({"fp": p, "bid": int(b), "src": "twin", "floors": int(max(1, fl_by_bid.get(int(b), 1) or 1))})
    tw_t = shapely.STRtree(tw_all) if tw_all else None
    ov = []
    g, pp = layers.load("buildings")
    sel = np.flatnonzero(shapely.intersects(g, work))
    for i in sel:
        q = U.clean(g[i])
        if q.is_empty or not work.contains(q.centroid):
            continue
        if tw_t is not None:
            hit = tw_t.query(q, predicate="intersects")
            if len(hit) and max(tw_all[j].intersection(q).area for j in hit) > 0.3 * q.area:
                continue
            if len(hit):
                # it keeps off the twin's houses it touches (their meshes stay as they are; tester item 67: gable houses cut
                # into a flat Overture building)
                q = U.clean(q.difference(unary_union([tw_all[j] for j in hit])))
                if q.is_empty:
                    continue
        if q.area < SHED_MAX_M2:
            sheds.append(pp[i].get("id", str(i)))
            continue
        for part in U.polys(q, 4.0):
            ov.append({"fp": part, "bid": None, "src": "overture:" + pp[i].get("id", str(i)), "floors": int(pp[i].get("floors") or 1)})
    # Overture buildings over one another (tester items 3, 67): the larger keeps its footprint, the smaller is cut off it
    ov.sort(key=lambda h: -h["fp"].area)
    ov_t = shapely.STRtree([h["fp"] for h in ov]) if ov else None
    kept_ov = [True] * len(ov)
    for k, h in enumerate(ov):
        hit = [int(j) for j in ov_t.query(h["fp"], predicate="intersects") if int(j) < k and kept_ov[int(j)]]
        if hit:
            rest = U.clean(h["fp"].difference(unary_union([ov[j]["fp"] for j in hit])))
            big = max(U.polys(rest, 4.0), key=lambda g: g.area, default=None)
            if big is None or big.area < SHED_MAX_M2:
                kept_ov[k] = False
                continue
            h["fp"] = big
    out += [h for k, h in enumerate(ov) if kept_ov[k]]
    if sheds and log is not None:
        log(f"сараи (здания двойника и Overture меньше {SHED_MAX_M2:.0f} м²) не считаются домами и могут быть убраны", sheds[:50], n=len(sheds))
    return out


def lrt_ground(lrt, norms):
    if not lrt:
        return U.Polygon()
    w = norms.num("lrt.corridor_width_m", "double_track")
    parts = []
    for L in lrt.get("lines", []):
        ls = LineString([(p[0], p[1]) for p in L["pts"]])
        for s in L.get("sections", []):
            if s["kind"] == "ground":
                a, b = max(0, s["from_m"]), min(ls.length, s["to_m"])
                if b - a > 1:
                    parts.append(shapely.ops.substring(ls, a, b).buffer(w / 2, cap_style="flat"))
    return U.clean(unary_union(parts)) if parts else U.Polygon()


HUB_EXTRA_MIN_M2 = 200.0   # a transit object's plot part in another block of its zone (a street crosses it) joins the hub from this size
STRIP_MAX_M = 20.0         # a neighbouring zone's strip up to this deep (area / shared edge) between a registry block and its street joins it
STRIP_SHARE = 0.6          # … when the block takes at least this share of the strip's long side
ENTRY_MAX_M = 100.0        # m: farthest street a block cut off from the streets gets an entry lane to (model qTwin)
ENTRY_EXTRA_M = 4.0        # m: the lane is the drive's red line plus two router cells wide (model qTwin)
ENTRY_THROUGH = ("park", "reserve", "utility")   # block uses such a lane may cross (no buildings by rule there; model qTwin)
FOOT_ONLY_USES = ("park", "square", "playground")   # lot uses entered on foot only: no drive, a street only for the years (model qTwin)
GROW_TOL = 0.05            # a block not much bigger than lot_m2 (this share) is the registry plot as a whole
REG_AREA_TOL_M2 = 1.0      # a registry plot short of the spec's lot_m2 by more than this grows inside its block round the spec point
#                            (tester items 41, 64: the generated object has the spec's area) — m², the rounding of the plot
HUB_LABEL = {"tracks": "пути и платформа ж/д (резерв до трассы линии)", "hall": "вокзал", "forecourt": "привокзальная площадь",
             "taxi": "такси и высадка пассажиров", "park": "сквер ТПУ", "green": "зелень ТПУ", "terminal": "автовокзал",
             "bays": "посадка и стоянки автобусов под навесом", "bus_terminal": "автостанция ТПУ", "bus_bays": "посадка автобусов",
             "park_ride": "перехватывающая стоянка"}


def landmark_models():
    """registry_id → Unity landmark model id (gen/landmark_models.json): those lots carry the model, no buildings by rule."""
    return (U.read_json(os.path.join(os.path.dirname(os.path.abspath(__file__)), "landmark_models.json")) or {}).get("models", {})


def grow_about(rest, fpo, pt, target):
    """rest ∩ the cartographer's plot scaled about the spec point, at the scale that gives `target` m² (the whole rest when it is
    not much bigger): a plot that a street or the block edge cuts grows inside its block, centred where the spec put it."""
    from shapely import affinity
    if rest.area <= target * (1 + GROW_TOL):
        return rest

    def at(s):
        return U.clean(rest.intersection(affinity.scale(fpo, s, s, origin=pt)))
    lo, hi = 1.0, 2.0
    while at(hi).area < target and hi < 64.0:
        lo, hi = hi, hi * 2.0
    for _ in range(24):
        m = (lo + hi) / 2.0
        if at(m).area < target:
            lo = m
        else:
            hi = m
    return at(hi)


def registry_capacity(o, area_m2, norms):
    """Capacity of a registry lot: the spec's objects[].capacity, else the norm plot read backwards from the lot area."""
    cap = dict(o.get("capacity") or {})
    if cap:
        return cap
    k = o.get("kind")
    if k == "school":
        per = norms.num("schools.plot_2000_places_ha") * 1e4 / norms.num("schools.typical_capacity")
        return {"places": int(round(area_m2 / per / 10.0) * 10)}
    if k == "kindergarten":
        hi = max(U._band(q)[0] for q in norms.v("kindergartens.plot_m2_per_place") if U._band(q)[0] > 0)
        return {"places": int(area_m2 / norms.band("kindergartens.plot_m2_per_place", hi))}
    if k == "polyclinic":
        pp = norms.v("clinics.polyclinic_plot")
        return {"visits_per_shift": int(round(area_m2 / 1e4 / pp["ha_per_100_visits"] * 100))}
    return cap


# ------------------------------------------------------------------------------------------------------ lot targets
def split_params(split, rules, norms, home_m2, m2_res):
    """(target lot m², max depth m, min lot m²) by the zone's lot_split. Sizes from the zone's block sides and C08 tables."""
    bs = rules.get("block_side_m") or [norms.v("quarters.block_side_m", "min"), norms.v("quarters.block_side_m", "max")]
    lo, hi = float(bs[0]), float(bs[1])
    if split == "perimeter":
        t = min(norms.num("residential.courtyard_group_max_ha") * 1e4, hi * hi)
        return t, hi / 2, lo * lo / 4
    if split == "towers":
        return lo * lo, hi / 2, lo * lo / 4
    if split == "rows":
        return lo * lo / 2, lo / 2, lo * lo / 8
    if split == "houses":
        # C08 (quarters.residential_zone_ha_per_1000 «up_to_3_with_plots», min) → m² per house of home_m2 / m2_res residents
        ha = norms.v("quarters.residential_zone_ha_per_1000", "up_to_3_with_plots")["min"]
        per_house = ha * 1e4 / 1000.0 * (home_m2 / m2_res)
        return per_house, math.sqrt(per_house) * 2, per_house / 3
    if split == "industrial":
        t = norms.num("residential.non_residential_in_district", "object_max_ha") * 1e4
        return t, math.sqrt(t), t / 6
    return 1e12, 1e9, 0.0          # campus / none: the whole block


# ---------------------------------------------------------------------------------------------------- social lots
class Social:
    def __init__(self, norms, home_m2, m2_res):
        self.N = norms
        self.home_m2, self.m2_res = home_m2, m2_res
        kg = norms.v("kindergartens.new_places_genplan")
        self.kg_builtin_share = kg["of_2050_built_in"] / float(kg["additional_by_2050"])

    def radius(self, kind, low, village=False):
        """Service radius; village homes take the village / rural columns of the norms (schools.rural_access walk to a
        primary school, kindergartens low_rise_and_village, daily shops village, pharmacy low_rise)."""
        N = self.N
        if kind == "school":
            return N.v("schools.rural_access", "walk_primary_km") * 1000.0 if village else N.num("schools.radius_m")
        if kind == "kindergarten":
            return N.v("kindergartens.radius_m", "low_rise_and_village" if (low or village) else "multi_storey")
        if kind == "polyclinic":
            return N.num("clinics.polyclinic_radius_m")
        if kind == "pharmacy_shop":
            lr = "low_rise" if (low or village) else "multi_storey"
            return min(N.v("pharmacy_shops.pharmacy_radius_m", lr), N.v("pharmacy_shops.daily_shops_radius_m", "village" if village else lr))
        if kind == "fire_station":
            return N.num("fire.depot_radius_km") * 1000.0
        if kind in ("square", "playground"):
            return N.v("parks.square_or_playground", "max_distance_m")
        raise KeyError(kind)

    def per_resident(self, kind, multi):
        N = self.N
        if kind == "school":
            return N.num("schools.places_per_1000_genplan") / 1000.0
        if kind == "kindergarten":
            k = N.num("kindergartens.places_per_1000_genplan") / 1000.0
            return k * (1 - self.kg_builtin_share) if multi else k
        if kind == "polyclinic":
            return N.num("clinics.polyclinic_visits_per_1000") / 1000.0
        return 0.0

    def plot(self, kind, cap):
        """Plot m² for a capacity (places / visits per shift) and the norm key it comes from."""
        N = self.N
        if kind == "school":
            if cap <= 1200:
                return cap * N.band("schools.plot_m2_per_pupil", cap), "schools.plot_m2_per_pupil"
            return N.num("schools.plot_2000_places_ha") * 1e4 * cap / N.num("schools.typical_capacity"), "schools.plot_2000_places_ha"
        if kind == "kindergarten":
            return cap * N.band("kindergartens.plot_m2_per_place", cap), "kindergartens.plot_m2_per_place"
        if kind == "polyclinic":
            pp = N.v("clinics.polyclinic_plot")
            return max(pp["min_ha"], pp["ha_per_100_visits"] * cap / 100.0) * 1e4, "clinics.polyclinic_plot"
        if kind == "pharmacy_shop":
            return N.v("pharmacy_shops.pharmacy_plot_ha", "min") * 1e4, "pharmacy_shops.pharmacy_plot_ha"
        if kind == "square":
            return N.v("parks.min_area_ha", "square") * 1e4, "parks.min_area_ha"
        if kind == "fire_station":
            return None, "не найдено в norms.json"
        raise KeyError(kind)

    def cap_limits(self, kind):
        """Smallest and largest capacity of one facility: the lowest plot band and the typical capacity of the norms tables
        (polyclinic: visits per shift of the genplan's 2050 polyclinics / their count)."""
        N = self.N
        if kind == "school":
            # the smallest city school (schools.min_places_city), not below the lowest band of the plot table; the largest
            # the genplan's typical school (schools.typical_capacity). Over the table's top (1,200) the plot is the
            # analogue's (schools.plot_2000_places_ha, 16 m² a pupil): capping schools at 1,200 to stay on the table (tester
            # item 41) took the Gate 88 ha more school land and 10 % of its homes, so the table needs its 1,200–2,000 band
            lo = max(min(U._band(k)[0] for k in N.v("schools.plot_m2_per_pupil")), N.num("schools.min_places_city"))
            return lo, N.num("schools.typical_capacity")
        if kind == "kindergarten":
            hi = max(U._band(k)[0] for k in N.v("kindergartens.plot_m2_per_place") if U._band(k)[0] > 0)
            # the smallest city kindergarten (kindergartens.min_places_city), at least one full group
            return max(N.v("kindergartens.group_size_max", "3-7_years"), N.num("kindergartens.min_places_city")), math.floor(hi)
        if kind == "polyclinic":
            p = N.v("clinics.polyclinics_2050")
            return self.phc_min(), p["visits_per_shift"] / float(p["count"])
        return 0, 0

    def phc_min(self):
        """Visits per shift of the smallest primary care organisation, as rule 14 takes it (clinics.phc_min_visits_per_shift;
        without it, clinics.phc_attached_population's minimum at clinics.polyclinic_visits_per_1000): a smaller «polyclinic»
        is no polyclinic (tester item 74)."""
        try:
            return int(math.ceil(self.N.num("clinics.phc_min_visits_per_shift")))
        except (KeyError, TypeError):
            pass
        pop = self.N.v("clinics.phc_attached_population")
        rate = self.N.num("clinics.polyclinic_visits_per_1000")
        return int(math.ceil(min(v["min"] if isinstance(v, dict) else v for v in pop.values()) * rate / 1000.0))

    def typical_min(self, kind):
        """Capacity from which a facility is of the norms' typical size, not a micro one (tester item 79): school and
        kindergarten — the top of the smallest band of their plot tables (schools.plot_m2_per_pupil, kindergartens.
        plot_m2_per_place); polyclinic — the genplan's average polyclinic (clinics.polyclinics_2050 visits / count)."""
        N = self.N
        if kind == "school":
            return min(U._band(k)[1] for k in N.v("schools.plot_m2_per_pupil"))
        if kind == "kindergarten":
            return min(U._band(k)[1] for k in N.v("kindergartens.plot_m2_per_place") if U._band(k)[1] < 1e17)
        if kind == "polyclinic":
            return self.cap_limits(kind)[1]
        return 0

    def cap_round(self, kind, cap):
        """Kindergartens in whole groups (group_size_max 3-7 years); others to whole places."""
        if kind == "kindergarten":
            g = self.N.v("kindergartens.group_size_max", "3-7_years")
            return int(max(g, math.ceil(cap / g) * g))
        return int(math.ceil(cap))

    def feasible(self, kind, area):
        """Capacities (in steps of the smallest band / one group) whose plot fits area."""
        tab = self.__dict__.setdefault("_feas", {}).get(kind)
        if tab is None:             # (capacity, plot m²) in steps, once per kind
            lo, hi = self.cap_limits(kind)
            step = self.N.v("kindergartens.group_size_max", "3-7_years") if kind == "kindergarten" else lo
            tab, c = [], lo
            while c <= hi:
                tab.append((c, self.plot(kind, c)[0]))
                c += step
            self._feas[kind] = tab
        return [c for c, pl in tab if pl <= area]

    def choose_cap(self, kind, target, area):
        """Capacity nearest above target whose plot fits area (else the largest that fits); polyclinic: target within the plot."""
        if kind == "polyclinic":
            lo, hi = self.cap_limits(kind)
            pp = self.N.v("clinics.polyclinic_plot")
            return int(max(lo, min(math.ceil(target), hi, area / (pp["ha_per_100_visits"] * 1e4 / 100.0))))
        f = self.feasible(kind, area)
        t = self.cap_round(kind, target)
        up = [c for c in f if c >= t]
        if up:
            return int(up[0])
        below = [c for c in f if c <= t]
        return int(max(below) if below else (min(f) if f else t))

    def fit(self, kind, area, rest, split_params_fn, home_m2, m2_res):
        """Largest capacity whose plot fits `area` (None if not even the smallest); service-only kinds: 1 if the plot fits."""
        if kind in ("school", "kindergarten", "polyclinic"):
            lo, hi = self.cap_limits(kind)
            if kind == "polyclinic":
                pp = self.N.v("clinics.polyclinic_plot")
                if area < pp["min_ha"] * 1e4:
                    return None
                v = min(hi, area / (pp["ha_per_100_visits"] * 1e4 / 100.0))
                return v if v >= lo else None
            f = self.feasible(kind, area)
            return max(f) if f else None
        need, _ = self.site_plot(kind, rest, split_params_fn, home_m2, m2_res)
        return 1 if need and area >= need else None

    def site_plot(self, kind, rest, split_params_fn, home_m2, m2_res):
        if kind == "fire_station":
            # norms.json has no depot plot: the smallest lot of the zone's lot split (model qTwin)
            if rest["village"] or rest["split"] not in ("perimeter", "towers", "industrial"):
                return None, "-"
            _, _, mn = split_params_fn(rest["split"], rest["rules"], self.N, home_m2, m2_res)
            return (mn if mn > 0 else None), "не найдено в norms.json (участок депо): минимальный участок зоны, модель qTwin"
        if kind == "playground":
            return self.N.v("parks.square_or_playground", "min_area_m2"), "parks.square_or_playground"
        return self.plot(kind, 0)


# ------------------------------------------------------------------------------------------------------------- main
def run(d, out, spec_path=None):
    t0 = time.time()
    spec = U.load_spec(d, spec_path)
    norms = U.Norms()
    log = U.Log()
    od = U.out_dir(out, d)
    net = U.read_json(os.path.join(od, "network.json"))
    if net is None:
        raise SystemExit(f"{od}/network.json missing: run gen_network first")
    lrt = U.read_json(os.path.join(od, "lrt.json"))
    m2_res, m2_job, _, _ = U.twin_m2()
    home_m2 = float((spec.get("targets") or {}).get("home_m2") or U.LEVEL0_HOME_M2)
    work = U.work_polygon(spec)

    # 1. corridors and the land they leave
    red = U.network_polys(net, norms, "red")
    street = U.clean(unary_union([p for _, p, _ in red]).intersection(work))
    lrt_poly = U.clean(lrt_ground(lrt, norms).difference(street).intersection(work))
    wpol, wlin = U.water_geoms(work)
    water = U.clean(unary_union(wpol).intersection(work)) if wpol else U.Polygon()
    strip_w = norms.num("flood.water_protection_strip_min_m")
    strip = U.clean(unary_union([g.buffer(strip_w) for g in wpol] + [g.buffer(strip_w) for g, _ in wlin]).intersection(work).difference(water)) \
        if (wpol or wlin) else U.Polygon()
    flood, flood_lvl = U.flood_poly(work, norms)
    corr_land = []
    for c in U.corridors(spec):
        ln = LineString(c["line"])
        key = {"power_line": "utilities.power_line_protection_zone_m", "gas": "utilities.gas_pipeline_protection_zone_m"}.get(c["kind"])
        w = U.power_zone_m(norms, c)[0] if c["kind"] == "power_line" else (c.get("width_m") or (norms.v(key) if key else None))
        if c.get("state") == "cable":
            log("кабельная линия: земля под коридор не резервируется (кабель в красных линиях улиц)", [c["id"]])
            continue
        if w is None:
            log("ширина охранной зоны не задана (norms: not_verified): под проводами только запрет зданий", [c["id"]], warn=True)
            corr_land.append(ln.buffer(1.0))
        else:
            corr_land.append(ln.buffer(w))
    corr = U.clean(unary_union(corr_land).intersection(work)) if corr_land else U.Polygon()
    keeps = U.keep_polys(spec)
    keep_union = U.clean(unary_union([p for _, p in keeps])) if keeps else U.Polygon()
    land = U.clean(work.difference(street).difference(lrt_poly).difference(water).difference(keep_union))

    # 2. blocks: pieces × zones
    zones = []
    for z in spec["zones"]:
        zp = U.from_coords(z["polygon"])
        if zp.intersects(work):
            zones.append((z, zp, U.zone_rules(z)))
    ztree = U.strtree([zp for _, zp, _ in zones])
    min_lot = 300.0
    blocks = []
    zov = defaultdict(float)     # spec zones that overlap: the land goes to the zone met first (blocks stay disjoint)
    for piece in U.polys(land, 1.0):
        covered = []
        for j in ztree.query(piece, predicate="intersects"):
            z, zp, r = zones[j]
            q = U.clean(piece.intersection(zp))
            if covered and not q.is_empty:
                cu = unary_union(covered)
                if q.intersects(cu) and q.intersection(cu).area > DISJOINT_MIN_M2:
                    zov[z["id"]] += q.intersection(cu).area
                    q = U.clean(q.difference(cu))
            for part in U.polys(q, 1.0):
                blocks.append({"zone": z["id"], "use": z["use"], "poly": part})
                covered.append(part)
        rest = U.clean(piece.difference(unary_union(covered))) if covered else piece
        for part in U.polys(rest, 1.0):
            blocks.append({"zone": None, "use": "reserve", "poly": part, "label_ru": "резерв: земля вне зон спецификации"})
    if zov:
        log("зоны спецификации перекрываются: земля перекрытия отдана зоне, встреченной первой — кварталы не перекрываются "
            "(спецификация, w47)", sorted(zov), m2={k: round(v, 1) for k, v in sorted(zov.items())}, warn=True)
    for k, kp in keeps:
        kp = U.clean(kp.intersection(work))
        zid = None
        best = 0
        for z, zp, r in zones:
            a = zp.intersection(kp).area
            if a > best:
                best, zid = a, z["id"]
        for part in U.polys(kp, 1.0):
            blocks.append({"zone": zid, "use": "landmark", "poly": part, "keep": k})
    # a registry object's block cut off from every street by thin strips of other zones (zones drawn short of the red lines)
    # takes those strips, so its plot fronts a street (rule 12: every block with buildings is entered from a street)
    acc_red = U.clean(unary_union([p for s, p, lv in red if s["class"] in U.DRIVABLE and s["class"] not in U.NO_ACCESS
                                   and not s["class"].startswith("driveway") and lv == 0]))
    reg_pts = [(o["registry_id"], Point(o["to"])) for o in spec.get("objects", [])
               if o.get("to") and o.get("kind") and o.get("kind") != "landmark_keep" and not o.get("parent")]
    btree_ = U.strtree([b["poly"] for b in blocks])
    # a thin strip of a utility / reserve zone between a street and a block (the zone drawn to a wider red line than the street
    # has, e.g. a motorway corridor zone along a divided road) joins the block behind it, which keeps its street frontage —
    # not a spec zone kept whole (lot_split none) or one an elevated span crosses (join_strips)
    zrules = {z["id"]: r for z, zp, r in zones}
    spans = U.span_bands(net, lrt, norms, spec)
    n_strip, m2_strip, kept_strips = join_strips(blocks, zrules, acc_red, spans)
    if kept_strips:
        log("полосы зон между улицей и кварталом оставлены своими кварталами (зона спецификации без раздела на участки или под "
            "эстакадой): въезд к кварталу за ними — проездом через полосу", kept_strips[:40], n=len(kept_strips))
    if n_strip:
        log("полосы зон инженерного / резервного назначения между улицей и кварталом присоединены к кварталу (зона нарисована шире "
            "красной линии)", [], strips=n_strip, m2=round(m2_strip))
    blocks = [b for b in blocks if not b.get("_gone")]
    btree_ = U.strtree([b["poly"] for b in blocks])
    holders = [b for b in blocks if b["use"] != "landmark" and any(b["poly"].contains(p) for _, p in reg_pts)]
    for H in holders:
        if acc_red.is_empty or H["poly"].distance(acc_red) <= 0.5:
            continue
        took = []
        for j in btree_.query(H["poly"].buffer(0.5), predicate="intersects"):
            N = blocks[int(j)]
            if N is H or N.get("_gone") or N in holders or N["use"] == "landmark" or N["poly"].distance(acc_red) > 0.5 \
                    or not strip_joins(N, zrules, spans):
                continue
            sh = N["poly"].buffer(0.5).intersection(H["poly"].boundary).length
            if sh > 0 and N["poly"].area / sh <= STRIP_MAX_M:
                took.append(N)
        if took:
            sp_ = U.clean(unary_union([N["poly"] for N in took]))
            H["poly"] = U.merge([H["poly"], sp_])
            H["strip_poly"] = sp_
            for N in took:
                N["_gone"] = True
            log("квартал объекта реестра без выхода на улицу: взял полосы соседних зон до красной линии (зоны спецификации не доходят "
                "до улицы)", [r for r, p in reg_pts if H["poly"].contains(p)] + sorted({N["zone"] or "вне зон" for N in took}),
                m2=round(sp_.area), warn=True)
    blocks = [b for b in blocks if not b.get("_gone")]
    # a block that will hold buildings (a village with its houses too) cut off from every access street by pieces of park,
    # reserve or utility zones (golden: B0193, B1413, B1671, B2338, B2527 got lots with an access street 8–470 m away, rule 12
    # «квартал без въезда с улицы») takes an entry lane through them: a strip of the drive's red line and two router cells
    # along the shortest way to the nearest access street, up to ENTRY_MAX_M; a block with none that near, or whose way would
    # cross a built block, water or the LRT, stays without an entry (logged)
    if not acc_red.is_empty:
        ent_w = U.profile_from_norms(norms, "driveway_main")["red_line_w"] + ENTRY_EXTRA_M
        btree_ = U.strtree([b["poly"] for b in blocks])
        acc_parts = [p for s, p, lv in red if s["class"] in U.DRIVABLE and s["class"] not in U.NO_ACCESS
                     and not s["class"].startswith("driveway") and lv == 0]
        acc_pt = U.strtree(acc_parts)

        def acc_dist(g):
            """Distance from g to the nearest access street's red line (an index, not the district's union)."""
            if len(acc_pt.query(g, predicate="dwithin", distance=0.5)):
                return 0.0
            j_ = acc_pt.query_nearest(g)
            return min(acc_parts[int(k)].distance(g) for k in j_) if len(j_) else math.inf
        n_ent, m2_ent, no_ent = 0, 0.0, []
        for H in sorted(blocks, key=lambda b: (-b["poly"].area, b["poly"].centroid.x)):
            if H["use"] in ENTRY_THROUGH or H["use"] == "landmark" or H["poly"].area < min_lot:
                continue
            d_ = acc_dist(H["poly"])
            if d_ <= 0.5:
                continue
            c_ = H["poly"].representative_point()
            if d_ > ENTRY_MAX_M:
                no_ent.append(f"{c_.x:.0f},{c_.y:.0f} ({d_:.0f} м)")
                continue
            a_, b_ = shapely.ops.nearest_points(H["poly"], unary_union([acc_parts[int(k)] for k in acc_pt.query(H["poly"].buffer(d_ + 1.0))]))
            v_ = np.array([b_.x - a_.x, b_.y - a_.y]) / max(d_, 1e-9)
            ln_ = LineString([(a_.x - v_[0], a_.y - v_[1]), (b_.x + v_[0], b_.y + v_[1])])        # 1 m into the block and the street
            corr_ = ln_.buffer(ent_w / 2.0, cap_style="flat")
            near_ = [blocks[int(j)] for j in btree_.query(corr_, predicate="intersects")]
            thru = [N for N in near_ if N is not H and N["use"] in ENTRY_THROUGH]
            other = [N for N in near_ if N is not H and N["use"] not in ENTRY_THROUGH and N["poly"].intersection(corr_).area > 1.0]
            take = U.clean(corr_.intersection(unary_union([N["poly"] for N in thru]))) if thru else Polygon()
            grown = U.merge([H["poly"], take]) if not take.is_empty else H["poly"]
            if other or take.is_empty or grown.geom_type != "Polygon" or acc_dist(grown) > 0.5:
                no_ent.append(f"{c_.x:.0f},{c_.y:.0f} ({d_:.0f} м)")
                continue
            H["poly"] = grown
            for N in thru:
                N["poly"] = U.clean(N["poly"].difference(take))
            n_ent += 1
            m2_ent += take.area
        if n_ent:
            log("квартал без улицы для въезда (между ним и улицей зелень, резерв или инженерная зона): проезд к ближайшей улице "
                "полосой через них (модель qTwin)", [], blocks=n_ent, m2=round(m2_ent), width_m=ent_w)
        if no_ent:
            log("квартал без улицы для въезда: ближайшая улица дальше ENTRY_MAX_M или путь к ней через застроенный квартал, воду, "
                "ЛРТ — въезда нет (сеть, w43 / спецификация, w47)", no_ent, warn=True)
    # tiny pieces → green buffers
    for b in blocks:
        if b["use"] not in ("landmark",) and b["poly"].area < min_lot:
            b["use"], b["label_ru"] = "park", "клин между красными линиями: зелёный буфер"
    blocks = [dict(b, poly=q) for b in blocks for q in U.polys(b["poly"], 0.5)]
    blocks.sort(key=lambda b: (-b["poly"].centroid.y, b["poly"].centroid.x))
    for i, b in enumerate(blocks):
        b["id"] = f"B{i:04d}"
        b["frame"] = U.frame_angle(b["poly"])      # lots are cut square to the block's frame (its street frontage)
    zone_by_id = {z["id"]: (z, zp, r) for z, zp, r in zones}

    # 3. lots
    houses = existing_houses(work, keep_union, log)
    htree = U.strtree([h_["fp"] for h_ in houses]) if houses else None
    street_new = U.clean(unary_union([p for s, p, lv in red if s["years"][0] > 2025])) if red else U.Polygon()
    shapely.prepare(street_new)
    # one lot per registry object; parts of a group (objects[].parent, e.g. Iconic's towers and podium) live on the parent's lot
    objs = [o for o in spec.get("objects", []) if o.get("to") and o.get("kind") and o.get("kind") != "landmark_keep" and not o.get("parent")]
    lots = []
    rests = []     # buildable land left in each block after keep, registry, existing and no-build lots
    lmod = landmark_models()
    spec_objs = [o for o in spec.get("objects", []) if o.get("to") and o.get("kind")]
    # a transit object's plot crossed by a street: its parts in the other blocks of the same zone are the hub's greens
    hub_extra = defaultdict(list)
    for o in objs:
        if o.get("kind") != "transit" or not (o.get("footprint") and len(o["footprint"]) >= 3):
            continue
        fpo = U.clean(Polygon(o["footprint"]))
        home = next((b for b in blocks if b["use"] != "landmark" and b["poly"].contains(Point(o["to"]))), None)
        if home is None:
            continue
        for b in blocks:
            if b is home or b.get("zone") != home.get("zone") or b["use"] == "landmark" or not b["poly"].intersects(fpo):
                continue
            a = b["poly"].intersection(fpo).area
            if a >= HUB_EXTRA_MIN_M2:
                hub_extra[b["id"]].append(o)
                o["_extra_m2"] = o.get("_extra_m2", 0.0) + a

    def add_lot(block, use, poly, source, registry_id=None, capacity=None, **kw):
        if use == "reserve" and not kw.get("label_ru"):
            # reserve land is labelled whatever its source (a zone of use reserve, or land outside the zones)
            z_ = (zone_by_id.get(block.get("zone")) or (None,))[0] or {}
            kw["label_ru"] = "резерв: " + (z_.get("name_ru") or z_.get("id") or "земля вне зон спецификации")
        for part in U.polys(U.clean(poly), 1.0):
            lots.append({"block": block["id"], "block_zone": block.get("zone"), "use": use, "poly": part, "source": source,
                         "registry_id": registry_id, "capacity": dict(capacity or {}), **kw})

    for b in blocks:
        rest = b["poly"]
        z, zp, rules = zone_by_id.get(b["zone"], (None, None, {}))
        if b["use"] == "landmark":
            add_lot(b, "landmark", rest, "keep", b["keep"].get("registry_id"))
            continue
        if b["use"] in ("park", "reserve") and z is None:
            add_lot(b, "park" if b["use"] == "park" else "reserve", rest, "rule", label_ru=b.get("label_ru"))
            continue
        # parts of a transit hub's plot beyond a street (greens of the hub)
        for o in hub_extra.get(b["id"], []):
            q = U.clean(U.clean(Polygon(o["footprint"])).intersection(rest))
            if q.area >= HUB_EXTRA_MIN_M2:
                add_lot(b, "park", q, "registry", None, spec_years=o.get("years"), label_ru=HUB_LABEL["green"] + " (модель qTwin)",
                        hub={"of": o["registry_id"], "kind": LT.hub_kind(o), "part": "green"})
                rest = U.clean(rest.difference(q))
                log("часть контура объекта ТПУ за улицей: зелень ТПУ", [o["registry_id"], b["id"]], m2=round(q.area))
        # registry objects first
        for o in objs:
            pt = Point(o["to"])
            if not rest.contains(pt) or o.get("_done"):
                continue
            rid = o["registry_id"]
            want = o.get("lot_m2")
            use = o["kind"]
            fpo = U.clean(Polygon(o["footprint"])) if o.get("footprint") and len(o["footprint"]) >= 3 else None
            if fpo is not None and fpo.intersection(rest).area >= 0.5 * (want or fpo.area):
                piece = U.clean(fpo.intersection(rest))       # the cartographer's plot (spec objects[].footprint)
                need = (want or 0.0) - o.get("_extra_m2", 0.0)
                if want and piece.area < need - REG_AREA_TOL_M2 and rest.area > piece.area + 1.0:
                    fp_m2 = piece.area
                    piece = grow_about(rest, fpo, pt, need)
                    log("участок объекта реестра меньше lot_m2 (контур режет улица или край квартала): доращён в квартале вокруг точки "
                        "спецификации", [rid], plot_in_block_m2=round(fp_m2), m2=round(piece.area), lot_m2=want,
                        warn=piece.area < need - REG_AREA_TOL_M2)
                if want and piece.area < need - REG_AREA_TOL_M2:
                    # the block cannot hold the spec's plot: the spec's contour crosses a street of the spec (w47's numbers)
                    cross = sorted({s_["id"] + (f" ({s_['street']})" if s_.get("street") else "") for s_, p_, _ in red
                                    if p_.intersects(fpo) and p_.intersection(fpo).area > 1.0})
                    log("участок объекта реестра меньше lot_m2 спецификации: квартал меньше — контур спецификации пересекает улицы "
                        "(спецификация, w47)", [rid] + cross, m2=round(piece.area), lot_m2=want, hub_green_m2=round(o.get("_extra_m2", 0.0)),
                        short_m2=round(need - piece.area), warn=True)
                if b.get("strip_poly") is not None:       # its way to the street: the strips it touches
                    sq = [q for q in U.polys(U.clean(b["strip_poly"].intersection(rest)), 1.0) if q.distance(piece) < 0.5]
                    if sq:
                        piece = U.merge([piece] + sq)
            elif want and rest.area > want * 1.3:
                ang = U.frame_axis(rest, b["frame"])[0]
                a1, a2 = U.cut_at_area(rest, ang, want, True)
                piece = a1 if a1.distance(pt) <= a2.distance(pt) else U.cut_at_area(rest, ang, want, False)[0]
            else:
                piece = rest
            kw = {}
            if rid in lmod:
                use = "landmark"          # Unity stands its own model here (LandmarkData): no buildings by rule on the lot
                kw["landmark_model"] = lmod[rid]
            elif use == "landmark":
                use = b["use"]            # a landmark with no Unity model is built by its zone's rule
                kw["label_ru"] = "модель qTwin: " + (o.get("name_ru") or rid)
            parts = LT.plan(piece, o, spec_objs, net, norms, b["frame"]) if use == "transit" else None
            if use == "transit" and not parts:
                log("участок ТПУ мал для схемы ТПУ (пути, вокзал, площадь): одним участком", [rid], m2=round(piece.area), warn=True)
            if parts:
                for p_ in parts:
                    if p_["use"] is None:
                        log(p_["why"], [rid], warn=True)
                        continue
                    hub = {"of": rid, "kind": LT.hub_kind(o), "part": p_["part"]}
                    for k_ in ("build", "stop", "platform", "bays"):
                        if p_.get(k_) is not None:
                            hub[k_] = p_[k_]
                    cap = {"cars": p_["cars"]} if p_.get("cars") else (registry_capacity(o, piece.area, norms) if p_.get("main") else {})
                    add_lot(b, p_["use"], p_["poly"], "registry", rid if p_.get("main") else None, capacity=cap, spec_years=o.get("years"),
                            hub=hub, label_ru=HUB_LABEL.get(p_["part"], p_["part"]) + " (модель qTwin)")
                log("ТПУ: участок разбит на части (модель qTwin)", [rid], m2=round(piece.area),
                    parts={k_: round(sum(q["poly"].area for q in parts if q["part"] == k_)) for k_ in dict.fromkeys(q["part"] for q in parts if q["use"])})
            elif use == "parking":
                add_lot(b, use, piece, "registry", rid, capacity={"cars": LT.pr_cars(piece.area, norms)}, spec_years=o.get("years"),
                        hub={"of": rid, "kind": "park_ride", "part": "park_ride", "floors": LT.PR_FLOORS},
                        label_ru=HUB_LABEL["park_ride"] + " (модель qTwin)")
            else:
                add_lot(b, use, piece, "registry", rid, capacity=registry_capacity(o, piece.area, norms), spec_years=o.get("years"), **kw)
            rest = U.clean(rest.difference(piece))
            o["_done"] = True
            log("участок объекта реестра", [rid], m2=round(piece.area))
        if rest.is_empty:
            continue
        # existing houses (not under a new street)
        inside = []
        if htree is not None:
            shapely.prepare(rest)               # prepared predicates: the same answers, without rebuilding the block per house
            for j in htree.query(rest, predicate="intersects"):
                hh = houses[j]
                if rest.contains(hh["fp"].centroid) and not street_new.intersects(hh["fp"]):
                    inside.append(hh)
        if b["use"] == "village_existing" and inside:
            pts = MultiPoint([hh["fp"].centroid for hh in inside])
            tgt, _, _ = split_params("houses", rules, norms, home_m2, m2_res)
            cap_r = math.sqrt(tgt) * 0.75
            cells = voronoi_diagram(pts, envelope=rest.envelope.buffer(50))
            ctree = U.strtree([hh["fp"].centroid for hh in inside])
            used = []
            for cell in cells.geoms:
                # the house of the cell: its seed is the centroid nearest to any point inside the cell (index, not a scan)
                hh = inside[int(ctree.nearest(cell.representative_point()))]
                c = U.clean(cell.intersection(rest).intersection(hh["fp"].buffer(cap_r).union(hh["fp"].envelope.buffer(3))))
                if c.area > 1:
                    add_lot(b, "village_existing", c, "existing", houses_in=[hh.get("bid") or hh["src"]])
                    used.append(c)
            rest = U.clean(rest.difference(unary_union(used))) if used else rest
        elif inside:
            gap = norms.v("building_gaps.estate_m", "house_to_plot_boundary")
            ex = U.clean(unary_union([hh["fp"].buffer(gap, join_style="mitre") for hh in inside]).intersection(rest))
            for part in U.polys(ex, 1.0):
                add_lot(b, "residential_low", part, "existing", houses_in=[hh.get("bid") or hh["src"] for hh in inside if hh["fp"].intersects(part)])
            rest = U.clean(rest.difference(ex))
        # no-build land inside the block
        for nb, why in ((strip, "водоохранная полоса"), (flood, "ниже паводка"), (corr, "охранная зона ЛЭП / газопровода")):
            if nb.is_empty or not rest.intersects(nb):
                continue
            q = U.clean(rest.intersection(nb))
            for part in U.polys(q, 1.0):
                add_lot(b, "park", part, "rule", label_ru=why, nobuild=True)
            rest = U.clean(rest.difference(nb))
        if rest.is_empty:
            continue
        split = rules.get("lot_split", "none")
        use = b["use"]
        for part in U.polys(rest, 1.0):
            rests.append({"b": b, "poly": part, "use": use, "rules": rules, "split": split, "zone": b["zone"],
                          "village": use == "village_existing"})

    # 4. social and service lots carved from the rests, then the rests split into lots
    walk = U.WalkNet(net)
    soc = Social(norms, home_m2, m2_res)
    arterial = U.clean(unary_union([p for s, p, lv in U.network_polys(net, norms, "carriage") if s["class"] in U.ARTERIAL_ROADS]))
    zone_net = defaultdict(float)          # net block area per zone (as gen_buildings calibrates the densities), keep excluded
    for b in blocks:
        if b["use"] != "landmark":
            zone_net[b["zone"]] += b["poly"].area
    sb_art_, sb_res_ = norms.v("setbacks.red_line_m", "arterial_streets"), norms.v("setbacks.red_line_m", "residential_streets")
    rl_tree_c = U.strtree([p for _, p, _ in red])

    def lot_setback(q, rules):
        """Building line inside a lot: the setback gen_buildings applies (street classes around the lot, zone setback_m)."""
        near = [red[int(j)][0] for j in rl_tree_c.query(q.buffer(2.0), predicate="intersects")]
        return max([sb_art_ if s_["class"] in U.ARTERIAL_STREETS | U.ARTERIAL_ROADS else sb_res_ for s_ in near] + [rules.get("setback_m") or sb_res_])
    # blocks a drive can enter: an access street (drivable, lot entries allowed, at level 0) within 1 m, as land_driveways
    # roots its drives — a service site in a block with none got no drive (Gate G1: kindergartens b09359, b09361, b10784)
    # (the access streets' parts at grade, as land_driveways takes them: off every off-grade piece, bridges and tunnels)
    og_by = defaultdict(list)
    for p_ in U.offgrade(net, norms):
        og_by[p_["seg"]["id"]].append(p_)
    acc_l = []
    for s_ in net["segments"]:
        if s_["class"] not in U.DRIVABLE or s_["class"] in U.NO_ACCESS or s_["class"].startswith("driveway"):
            continue
        rw_ = U.red_half(U.seg_profile(net, s_, norms))
        if rw_ <= 0:
            continue
        own_ = unary_union([p_["poly"] for p_ in og_by[s_["id"]]]) if og_by.get(s_["id"]) else None
        for part in U.at_grade_parts(s_, og_by.get(s_["id"], [])):
            q_ = part.buffer(rw_, quad_segs=4)
            if own_ is not None:
                q_ = U.clean(q_.difference(own_))
            if not q_.is_empty:
                acc_l.append(q_)
    acc_t = U.strtree(acc_l) if acc_l else None
    acc_blocks = {b["id"] for b in blocks if acc_t is not None and len(acc_t.query(b["poly"], predicate="dwithin", distance=SITE_ACC_M))}

    def fronts(q):
        """The plot q has a street to enter from: an access street's part at grade within SITE_ACC_M (a kindergarten plot
        inside a block, a pharmacy on an embankment's side got no drive, Gate G4: b04169, b04421)."""
        return street_front(acc_t, q)
    # a village building stands within the building-line limit of a street carriageway (gen_buildings: the village lane is its
    # fire access all round; a drive rarely gets through the gardens — growing_w: social buildings 88–397 m from a carriageway
    # in vil_farms_*, rule 12, w52): such a site is good only when the building fits in that band
    line_max = norms.v("setbacks.building_line_max_m", "max_from_carriageway")
    car_l = [p_ for s_, p_, lv_ in U.network_polys(net, norms, "carriage")
             if s_["class"] in U.DRIVABLE and s_["class"] not in U.NO_ACCESS and lv_ == 0]
    car_t = U.strtree(car_l) if car_l else None

    def near_street(region):
        """The part of region within the building-line limit of a street carriageway (as gen_buildings places a village
        service building)."""
        if car_t is None or region.is_empty:
            return U.Polygon()
        cs_ = [car_l[int(j)] for j in car_t.query(region, predicate="dwithin", distance=line_max)]
        return U.clean(region.intersection(unary_union(cs_).buffer(line_max - VILLAGE_NEAR_TOL_M))) if cs_ else U.Polygon()
    hosts = place_services(rests, lots, zone_by_id, walk, soc, norms, spec, home_m2, m2_res, log, arterial, add_lot, split_params, street,
                           houses, zone_net, lot_setback, acc_blocks, fronts, near_street)
    host_pts = [Point(x, y) for x, y in hosts]
    host_tree = U.strtree(host_pts) if host_pts else None        # the built-in kindergarten hosts, found by an index
    g_kg = norms.v("kindergartens.group_size_max", "3-7_years")
    for r in rests:
        b = r["b"]
        if r["village"]:
            for part in U.polys(r["poly"], 1.0):
                add_lot(b, "village_existing", part, "rule", label_ru="сады и огороды села (без новых домов)")
            continue
        for q, res in r_pieces(r, norms, home_m2, m2_res):
            cap = {}
            if res > 0 and not r["low"]:
                cap["kindergarten_builtin_places"] = int(round(res * soc.per_resident("kindergarten", False) * soc.kg_builtin_share))
                if host_tree is not None and len(host_tree.query(q.buffer(1.0), predicate="contains")):
                    cap["kindergarten_builtin_places"] = max(cap["kindergarten_builtin_places"], g_kg)
            add_lot(b, r["use"], q, "rule", capacity=cap)

    lots = [dict(L, poly=q) if k == 0 else dict(L, poly=q, capacity={}) for L in lots for k, q in
            enumerate(sorted(U.polys(L["poly"], 0.5), key=lambda q: -q.area))]

    # 5. grading
    cut_max = norms.v("validator.grading", "cut_fill_max_m")
    natural_uses = {"park", "reserve", "square", "landmark", "utility", "playground"}
    out_lots = []
    blk_frame = {b["id"]: b.get("frame") for b in blocks}

    def slope_angle(p, frame=None):
        """Direction of the terrain slope at p; with the block's frame, the frame direction nearer to it (terraces are cut
        square to the frontage, not along the contour lines)."""
        gx, gz = U.terrain().gradient(p.centroid.x, p.centroid.y, 50.0)
        a = math.atan2(gz, gx)
        if frame is None:
            return a
        return min((frame, frame + math.pi / 2), key=lambda f: abs(math.sin(a - f)))

    grade_c = {}        # U.grade of the pieces just cut, kept for the next level of split_to_grade (the same pieces)

    def grade_of(q):
        hit = grade_c.get(id(q))
        if hit is None or hit[0] is not q:
            if len(grade_c) > GRADE_KEEP_MAX:
                grade_c.clear()
            hit = grade_c[id(q)] = (q, U.grade(q))
        return hit[1]

    def split_to_grade(p, depth=0, frame=None):
        """Pieces of p each within the cut/fill limit. With the block's frame the cuts run along one of its two directions —
        the one that leaves the smaller cut/fill (a slope across the frame is cut in both, a grid of terraces)."""
        g, dev = grade_of(p)
        if dev <= cut_max or depth > 4 or p.area < 400.0:
            return [(p, g, dev)]
        n = max(2, int(math.ceil(dev / cut_max)))
        best = None
        for a in ([slope_angle(p)] if frame is None else [slope_angle(p, frame), slope_angle(p, frame) + math.pi / 2]):
            parts = [q for s_ in U.strips(p, a, n) for q in U.polys(s_, 1.0)]
            worst = max([grade_of(q)[1] for q in parts] or [dev])
            if best is None or worst < best[0] - 0.05:
                best = (worst, parts)
        res = []
        for part in best[1]:
            res += split_to_grade(part, depth + 1, frame)
        if depth == 0 and frame is not None and max(d_ for _, _, d_ in res) > cut_max:
            # the frame's two directions do not bring every piece within the limit: the terrain forces cuts along its slope
            free = split_to_grade(p, 0, None)
            if max(d_ for _, _, d_ in free) < max(d_ for _, _, d_ in res):
                return free
        return res
    blk_by_id = {b["id"]: b for b in blocks}

    def good_lots(L, pcs):
        """Every piece a lot of the zone's shape: perimeter² / area within SHAPE_FAR × the norm, not below the smallest lot."""
        b = blk_by_id[L["block"]]
        rules = (zone_by_id.get(b["zone"]) or (None, None, {}))[2]
        norm = shape_norm(L["use"], b["use"], rules, norms, home_m2, m2_res)
        split = rules.get("lot_split", "none")
        mn = split_params(split, rules, norms, home_m2, m2_res)[2] if L["use"] == b["use"] and split not in ("none", "campus") else 0.0
        return all(q.length ** 2 / q.area <= SHAPE_FAR * norm and q.area >= mn for q in pcs)
    for L in lots:
        g, dev = U.grade(L["poly"])
        L["grade_y"], L["_dev"] = g, dev
        garden = L["use"] == "village_existing" and L["source"] == "rule"
        if L["use"] in natural_uses or garden or L["source"] in ("existing", "keep") or L.get("nobuild"):
            L["natural"] = True           # land left at its terrain (no grading): parks, gardens, corridors, existing plots
            out_lots.append(L)
            continue
        if dev <= cut_max:
            out_lots.append(L)
            continue
        if L["source"] == "rule" and L["use"] not in U.SOCIAL_USES:
            pcs = sorted(split_to_grade(L["poly"], 0, blk_frame.get(L["block"])), key=lambda t: -t[0].area)
            if len(pcs) > 1 and not good_lots(L, [q for q, _, _ in pcs]) and all(d2 <= cut_max for _, _, d2 in pcs):
                # the pieces would be strips or below the zone's smallest lot: the lot stays whole on terraces
                L["terraces"] = [{"polygon": U.coords(part), "grade_y": g2, "cut_fill_m": d2} for part, g2, d2 in pcs]
                out_lots.append(L)
                continue
            for k, (part, g2, d2) in enumerate(pcs):
                M = dict(L)
                M["poly"], M["grade_y"], M["_dev"] = part, g2, d2
                M["capacity"] = dict(L["capacity"] or {}) if k == 0 else {}     # built-in places stay on the main part
                out_lots.append(M)
            continue
        # terraces for lots that stay whole (services, registry objects)
        ter = [{"polygon": U.coords(part), "grade_y": g2, "cut_fill_m": d2} for part, g2, d2 in split_to_grade(L["poly"], 0, blk_frame.get(L["block"]))]
        L["terraces"] = ter
        out_lots.append(L)
    lots = out_lots

    # 5b. slivers: a buildable rule lot below its zone's smallest lot (split_params: grading strips, leftovers of service
    # plots) joins the lot of the same use it shares most boundary with: one grade when the whole stays within the cut/fill
    # limit, else as a terrace of that lot (each terrace within the limit); one that cannot becomes a green wedge at its terrain

    def lot_min(L):
        b = blk_by_id[L["block"]]
        z, zp, rules = zone_by_id.get(b["zone"], (None, None, {}))
        if (z is None or L["source"] != "rule" or L.get("natural") or L.get("nobuild") or L["use"] != b["use"]
                or L["use"] in natural_uses or L["use"] in U.SOCIAL_USES):
            return 0.0
        return split_params(rules.get("lot_split", "none"), rules, norms, home_m2, m2_res)[2]
    n_merged, greened = 0, []
    changed = True
    while changed:
        changed = False
        by_blk = defaultdict(list)
        for L in lots:
            by_blk[L["block"]].append(L)
        for L in sorted(lots, key=lambda L: L["poly"].area):
            if L.get("_gone") or L["poly"].area >= lot_min(L):
                continue
            best = None
            gb = L["poly"].buffer(0.05)
            for M in by_blk[L["block"]]:
                if M is L or M.get("_gone") or M["use"] != L["use"] or M["source"] != "rule" or M.get("natural"):
                    continue
                sh = _shared(gb, M)
                if sh >= 2.0 and (best is None or sh > best[0]):
                    best = (sh, M)
            done = False
            if best is not None:
                M = best[1]
                u = U.merge([M["poly"], L["poly"]])
                if u.geom_type == "Polygon":
                    g, dev = U.grade(u)
                    if dev <= cut_max and not M.get("terraces"):
                        M["poly"], M["grade_y"], M["_dev"] = u, g, dev
                        done = True
                    else:
                        ter = M.get("terraces") or [{"polygon": U.coords(M["poly"]), "grade_y": M["grade_y"], "cut_fill_m": M["_dev"]}]
                        if L["_dev"] <= cut_max and all(t["cut_fill_m"] <= cut_max for t in ter):
                            M["terraces"] = ter + [{"polygon": U.coords(L["poly"]), "grade_y": L["grade_y"], "cut_fill_m": L["_dev"]}]
                            M["poly"] = u
                            done = True
                if done:
                    for k_, v_ in (L.get("capacity") or {}).items():
                        M.setdefault("capacity", {})[k_] = (M["capacity"].get(k_) or 0) + v_
                    L["_gone"] = True
                    n_merged += 1
                    changed = True
            if not done:
                L.update(use="park", natural=True, capacity={}, label_ru="зелёный клин: участок меньше наименьшего для зоны, у рельефа")
                greened.append(f"{L['poly'].centroid.x:.0f},{L['poly'].centroid.y:.0f}")
        lots = [L for L in lots if not L.get("_gone")]
    if n_merged or greened:
        log("участки меньше наименьшего для зоны: присоединены к соседнему участку той же зоны (общая планировка или терраса) "
            "или оставлены зелёным клином", greened, merged=n_merged, green=len(greened))

    # 5c. shapes: no part of a lot narrower than its minimum width (lot_min_width) where the block itself is wider — such a
    # strip, spike or needle goes to the neighbour that takes it without a narrow part of its own (same use first; land of a
    # protection zone only to greens; a strip no neighbour takes stays green); then a funnel or strip lot (perimeter² / area
    # over SHAPE_FAR × its zone's norm) is merged with its neighbour of the same use, or the two are cut again square to the
    # block's frame, and a green strip joins the green of its kind next to it; last, hair-line needles are cut off
    n_moved, n_funnel, n_green = shape_pass(lots, blk_by_id, zone_by_id, norms, home_m2, m2_res, cut_max)
    if n_moved or n_funnel or n_green:
        log("форма участков: узкие полосы, шипы и иглы отданы соседним участкам (или оставлены зелёной полосой); воронки слиты "
            "с соседом или перерезаны по сетке квартала (модель qTwin)", [], strips=n_moved, funnels=n_funnel, green=n_green)
    lots = [L for L in lots if not L.get("_gone")]
    # the lots tile their blocks in the written precision: in the block, apart, no land left over (rules 1, 2)
    n_bg, n_cl, m2_cl = to_grid(blocks, lots, blk_by_id)
    lots = [L for L in lots if not L.get("_gone")]
    if n_bg or n_cl:
        log("участки вне своего квартала (после формы, планировки и округления): обрезаны по кварталу в точности записи; "
            "кварталы без перекрытий (модель qTwin)", [], blocks_cut=n_bg, lots=n_cl, m2=round(m2_cl, 1))
    n_dj, m2_dj, both_fixed = make_disjoint(lots, blk_by_id, WRITE_GRID)
    n_gp, m2_gp = fill_gaps(lots, blk_by_id, WRITE_GRID, cut_max)
    clip_lots(lots, blk_by_id)
    lots = [L for L in lots if not L.get("_gone")]
    # terraces over the cut/fill limit after the merges and cuts above (a terrace clipped, a strip taken in): cut again to grade
    # (Gate G4: a school of 35 terraces up to 1.9 m, a kindergarten 1.6 m, rule 3)
    n_rt = 0
    for L in lots:
        ter = L.get("terraces")
        if not ter or all(t["cut_fill_m"] <= cut_max for t in ter):
            continue
        new_t = []
        for t in ter:
            if t["cut_fill_m"] <= cut_max:
                new_t.append(t)
                continue
            new_t += [{"polygon": U.coords(q), "grade_y": g2, "cut_fill_m": d2}
                      for q, g2, d2 in split_to_grade(U.from_coords(t["polygon"]), 0, blk_frame.get(L["block"]))]
        L["terraces"] = new_t
        n_rt += 1
    if n_rt:
        log("террасы сверх срезки/подсыпки после слияний и срезок участков: разрезаны по рельефу ещё раз", [], lots=n_rt,
            left_over=sum(1 for L in lots if L.get("terraces") and max(t["cut_fill_m"] for t in L["terraces"]) > cut_max))
    if n_gp:
        log("земля квартала вне участков (трещины между существующими участками после снятия игл): присоединена к соседнему "
            "участку (модель qTwin)", [], pieces=n_gp, m2=round(m2_gp, 1))
    if n_dj:
        log("участки перекрывались (игла снята у соседа, который её сохранил; щель закрыта слиянием через границу): земля оставлена "
            "постоянному участку, иначе участку своего квартала (модель qTwin)", [], pairs=n_dj, m2=round(m2_dj, 1))
    if both_fixed:
        log("перекрываются два постоянных участка (существующие / реестр / keep): оставлены как в исходных данных",
            sorted(f"{L.get('registry_id') or L['source']}@{L['block']} × {M.get('registry_id') or M['source']}@{M['block']} {a:.1f} м²"
                   for L, M, a in both_fixed), warn=True)

    # 6. years, access, ids
    acc_tree = []
    acc_segs = []
    for s, p, lv in red:
        if s["class"] in U.DRIVABLE and s["class"] not in U.NO_ACCESS:
            acc_tree.append(p)
            acc_segs.append(s)
    T = U.strtree(acc_tree) if acc_tree else None
    for i, L in enumerate(sorted(lots, key=lambda L: (L["block"], -L["poly"].centroid.y, L["poly"].centroid.x))):
        L["id"] = f"L{i:05d}"
    lots.sort(key=lambda L: L["id"])
    late_reg = []
    # access: the street whose red line the lot touches (within 2 m, as rule 12 takes it); a lot inside its block is entered
    # through the block, from the street a lot of the block touches; else (no entry: a park, a corridor or a cut-off block)
    # a street of any class the lot or its block touches, for the years — never a distant one (golden: lots named a street
    # 8–470 m away, rule 12); a block to be built with no entry is listed as unserved
    all_tree = U.strtree([p for _, p, _ in red]) if red else None
    all_segs = [s_ for s_, _, _ in red]
    T_all_near = all_tree

    def touching(g, tree, segs_):
        near = tree.query(g.buffer(2.0), predicate="intersects") if tree is not None else []
        if not len(near):
            return None
        j = min((int(j) for j in near), key=lambda j: (segs_[j]["years"][0], tree.geometries[j].distance(g), segs_[j]["id"]))
        return segs_[j]
    touch, touch_any = {}, {}
    for L in lots:
        a_ = touching(L["poly"], T, acc_segs)
        if a_ is not None:
            touch[L["id"]] = a_
        else:
            b_ = touching(L["poly"], all_tree, all_segs)
            if b_ is not None:
                touch_any[L["id"]] = b_
    blk_entry, blk_any = defaultdict(dict), defaultdict(dict)       # block → {street id: street} its lots touch
    for L in lots:
        for src_, dst_ in ((touch, blk_entry), (touch_any, blk_any)):
            if src_.get(L["id"]) is not None:
                dst_[L["block"]][src_[L["id"]]["id"]] = src_[L["id"]]
    seg_poly = defaultdict(list)
    for s_, p_, _ in red:
        seg_poly[s_["id"]].append(p_)

    def nearest_of(L, cands):
        """Of the streets a block's lots touch, the one nearest the lot (it comes in from there, through the block)."""
        if not cands:
            return None
        return min(cands.values(), key=lambda s_: (round(min(q.distance(L["poly"]) for q in seg_poly[s_["id"]]), 1), s_["years"][0], s_["id"]))
    no_entry = sorted({L["block"] for L in lots if L["block"] not in blk_entry and blk_by_id[L["block"]]["use"] not in ENTRY_THROUGH
                       and blk_by_id[L["block"]]["use"] != "landmark"})
    if no_entry:
        log("квартал без улицы для въезда: ни один его участок не касается проезжей улицы с въездом (2 м) — не обслужен, улица-въезд "
            "участков — та, которой они касаются (для лет), без дальней", no_entry, warn=True)
    for L in lots:
        b = blk_by_id[L["block"]]
        z, zp, rules = zone_by_id.get(b["zone"], (None, None, {}))
        sy = None
        acc = touch.get(L["id"]) or nearest_of(L, blk_entry.get(L["block"])) or touch_any.get(L["id"]) or nearest_of(L, blk_any.get(L["block"]))
        on_foot = L["use"] in FOOT_ONLY_USES
        if acc is None and (b["use"] in ENTRY_THROUGH or on_foot) and T_all_near is not None:
            # a green wedge or corridor piece no street touches (no buildings, no entry needed): the nearest street within
            # ENTRY_MAX_M for its years, else none; a park entered on foot takes its nearest street at any distance for its
            # years (green v1: 326 park lots deep in large park blocks had none, rule 23)
            j_ = T_all_near.query_nearest(L["poly"], max_distance=None if on_foot else ENTRY_MAX_M)
            acc = all_segs[int(j_[0])] if len(j_) else None
        if acc is not None:
            sy = acc["years"]
        if L["source"] in ("existing", "keep") and L["use"] != "landmark":
            yrs = list(U.EXISTING_YEARS)
        else:
            y0 = U.zone_years(z)[0] if z else 2030
            if L["source"] == "keep":
                y0 = int((b.get("keep") or {}).get("years", [y0])[0])
            ey = U.effective_years(max(y0, 2026), "housing")
            if L.get("spec_years") and len(L["spec_years"]) == 4:
                ey = list(L["spec_years"])          # a registry object opens in its own years (its buildings take them too)
                if sy and any(a < c for a, c in zip(ey, sy)):
                    late_reg.append(f"{L.get('registry_id') or (L.get('hub') or {}).get('of')} {ey} < {acc['id']} {list(sy)}")
            yrs = [max(a, c) for a, c in zip(ey, sy)] if sy else ey
        L["years"] = yrs
        L["access"] = acc["id"] if acc is not None else None
    if late_reg:
        log("объекты реестра раньше своей улицы-въезда: годы участка подняты до улицы (спецификация, w47)", sorted(set(late_reg)), warn=True)

    # write: a ring that folds when written with WRITE_ND decimals (a zone overlap cut off a block, a lot clipped or grown above) is
    # snapped to that grid first, its largest part kept (T6 gate_trial: four lots read back as two parts, gen_buildings failed)
    n_snap, m2_snap = 0, 0.0
    for X in blocks + lots:
        q = X["poly"]
        if q.geom_type == "Polygon" and not Polygon(U.coords(q, WRITE_ND), U.holes(q, WRITE_ND) or None).is_valid:
            parts = sorted(U.polys(U.clean(shapely.set_precision(q, WRITE_GRID)), 0.0), key=lambda g: -g.area)
            if parts:
                X["poly"] = parts[0]
                n_snap += 1
                m2_snap += q.area - parts[0].area
    if n_snap:
        log("контуры, складывавшиеся при записи с WRITE_ND знаками: привязаны к сетке записи", [], n=n_snap, m2_lost=round(m2_snap, 2))
    # graded lots on their outline as written (cut, clipped, grown by a gap above): graded again, on terraces where one grade
    # would cut or fill over cut_max (Gate G5: 28 lots written with the grade of an earlier outline, rule 3)
    n_rg, over = 0, []
    for L in lots:
        if L.get("natural") or L.get("nobuild") or L["source"] in ("existing", "keep") or L.get("terraces"):
            continue
        L["grade_y"], L["_dev"] = U.grade(L["poly"])
        if L["_dev"] > cut_max:
            pcs = split_to_grade(L["poly"], 0, blk_frame.get(L["block"]))
            if len(pcs) > 1:
                L["terraces"] = [{"polygon": U.coords(q), "grade_y": g2, "cut_fill_m": d2} for q, g2, d2 in pcs]
                n_rg += 1
            if max(d2 for _, _, d2 in pcs) > cut_max:
                over.append(f"{L['id']} {L['use']} {L['_dev']:.1f} м")
    if n_rg or over:
        log("участки, у которых после срезок и добавок одна планировка выходит за срезку/подсыпку: на террасы", over, lots=n_rg,
            warn=bool(over))
    bl = [{"id": b["id"], "zone": b["zone"], "use": b["use"], **U.poly_fields(b["poly"], WRITE_ND), "area_m2": round(b["poly"].area, 1),
           **({"label_ru": b["label_ru"]} if b.get("label_ru") else {}),
           **({"keep": b["keep"]["id"]} if b.get("keep") else {})} for b in blocks]
    lo = []
    for L in lots:
        r = {"id": L["id"], "block": L["block"], "use": L["use"], **U.poly_fields(L["poly"], WRITE_ND), "area_m2": round(L["poly"].area, 1),
             "grade_y": L["grade_y"], "cut_fill_m": L["_dev"], "years": L["years"], "registry_id": L.get("registry_id"),
             "source": L["source"], "capacity": L.get("capacity") or {}, "access": L.get("access")}
        for k in ("terraces", "label_ru", "nobuild", "natural", "houses_in", "norm_key", "plot_norm_m2", "hub", "landmark_model"):
            if L.get(k) is not None:
                r[k] = L[k]
        lo.append(r)
    U.write_json(os.path.join(od, "blocks.json"), {"schema": "qtwin.blocks/1", "district": d, "blocks": bl})
    U.write_json(os.path.join(od, "lots.json"), {"schema": "qtwin.lots/1", "district": d, "lots": lo, "log": log.rows,
                                                 "flood_level_m": flood_lvl, "made_by": "w44 gen_blocks_lots.py"})
    from collections import Counter
    c = Counter(L["use"] for L in lo)
    print(f"{d}: {len(bl)} blocks, {len(lo)} lots {dict(c)}; {time.time() - t0:.1f} s")
    return bl, lo


# ---------------------------------------------------------------------------------------------------- lot shapes
NARROW_TOL = (10.0, 0.01)   # a lot's narrow land counts from this much: max(m², share of the lot) — a model parameter
SHAPE_FAR = 1.6             # a lot whose perimeter² / area is over this × its zone's norm is a funnel or a strip: model parameter
WRITE_ND = 4                # decimals of the block and lot rings written, and the grid of the overlays that clip and part
                            # them: a lot clipped to its block stays in it as written. The grid overlay is exact only to
                            # half a step along a shared line, so the step is kept well under the 0.1 m² a lot may lie
                            # out of its block (2 decimals: lot corners up to 7 mm over the block line, 0.1–0.3 m² per lot,
                            # growing_w, w52; 3: 0.4 mm slivers along edges of hundreds of metres, up to 0.22 m², Gate G5)
WRITE_GRID = 10.0 ** -WRITE_ND  # m: that grid
HAIRLINE_LOT = 0.5          # m: a part of a plot thinner than this is a hair-line spike, not land (validator rule 2 reads
                            # gaps under 1 m as hair-lines) — a model parameter
SHAPE_PASSES = 3            # rounds of the shape pass per district (a moved strip can leave the next lot narrow)
FIXED_SOURCES = ("existing", "keep", "registry")
DISJOINT_MIN_M2 = 1e-4      # m²: an overlap of two lots below this is the noise of a shared edge (model qTwin)
GAP_MIN_M2 = 0.25          # m²: block land in no lot from this much joins a neighbouring lot (rule 2 counts 1 m²) — модель qTwin
NEW_SITE_MIN_SHARE = 0.5   # places short in reach under this share of the smallest facility go to a neighbour that holds them,
                           # not to a new micro facility (tester item 79) — модель qTwin
VILLAGE_NEAR_TOL_M = 1.0   # m inside the building-line limit for a village service building (gen_buildings.NEAR_TOL) — модель qTwin
SITE_ACC_M = 1.0           # m: a service plot fronts an access street when its red line is this near (as the drives root) — модель qTwin
TILE_SLIVER_M2 = 0.5       # m²: a part of a lot under this left by a clip or a cut is dropped, not written — модель qTwin
GAP_GREEN = "зелёный клин: земля квартала между участками, соседи не берут её в своей планировке (модель qTwin)"
GREEN_STRIP = "зелёная полоса: уже наименьшей ширины участка зоны, соседи её не берут (модель qTwin)"


def lot_min_width(use, rules, norms, plot_norm_m2=None):
    """The narrowest a part of a lot may be (m) — «модель qTwin»: room for the zone's narrowest building with its setback on
    both sides (perimeter and tower sections, slab rows, the smallest house, a class-A shed row, business sections); a
    service plot holds a square of half the side of its norm plot (chunky); greens and utility land the norm width of a
    one-side boulevard (parks.boulevard_min_width_m)."""
    if use in U.SOCIAL_USES:
        return 0.5 * math.sqrt(plot_norm_m2) if plot_norm_m2 else 0.0
    if use in U.GREEN_USES or use in ("utility", "parking", "transit"):
        return norms.v("parks.boulevard_min_width_m", "one_side_between_carriageway_and_buildings")
    split = rules.get("lot_split", "none")
    sb = rules.get("setback_m") or norms.v("setbacks.red_line_m", "residential_streets")
    if split in ("perimeter", "towers"):
        return LM.SECTION_DEPTH["housing"] + 2 * sb
    if split == "rows":
        return LM.SLAB_DEPTH + 2 * sb
    if split == "houses":
        return math.sqrt(LM.HOUSE_MIN_M2) + 2 * norms.v("building_gaps.estate_m", "house_to_plot_boundary")
    if split == "industrial":
        return LM.WAREHOUSE_DEPTH_MIN + 2 * sb
    return LM.SECTION_DEPTH["business"] + 2 * sb


def opening(p, w):
    """p without its parts narrower than w (an erosion and dilation by w / 2, square corners kept). GEOS can return a
    self-intersecting mitre dilation (seen on a 151-vertex lot of green, w 25: side location conflict in the intersection):
    it is made valid before the overlay."""
    return U.clean(U.clean(p.buffer(-w / 2, join_style="mitre").buffer(w / 2, join_style="mitre")).intersection(p))


def shape_norm(use, block_use, rules, norms, home_m2, m2_res):
    """perimeter² / area of the zone's typical lot: a 1 : 2 rectangle, or the target lot of the zone's split (its area at its
    depth) when that is longer."""
    norm = 18.0
    split = rules.get("lot_split", "none")
    if use == block_use and split not in ("none", "campus") and use not in U.SOCIAL_USES:
        t, dmax, _ = split_params(split, rules, norms, home_m2, m2_res)
        dd = min(dmax, math.sqrt(t))
        ww = t / dd
        norm = max(norm, 4 * (ww + dd) ** 2 / (ww * dd))
    return norm


def deneedle(p, block):
    """p without the tips of its needles: a vertex whose triangle with its two neighbours is thinner than HAIRLINE_LOT at its
    base (a buffer does not always see such a sliver of a degree), unless the block has the same tip."""
    if p.geom_type != "Polygon":
        return p
    c = [tuple(v) for v in p.exterior.coords[:-1]]
    bv = None           # the block's vertices, read at the first tip (an array: one distance test for all of them)
    done = False
    k = 0
    while len(c) > 3 and k < len(c):
        a, b, d = np.array(c[k - 1]), np.array(c[k]), np.array(c[(k + 1) % len(c)])
        u, v = a - b, d - b
        side = max(np.hypot(*u), np.hypot(*v))
        if side > HAIRLINE_LOT and abs(u[0] * v[1] - u[1] * v[0]) / side < HAIRLINE_LOT and u @ v > 0:
            if bv is None:
                bv = np.array([v_[:2] for q in U.polys(block, 0.0) for v_ in q.exterior.coords[:-1]]).reshape(-1, 2)
            if len(bv) and bool((np.hypot(bv[:, 0] - b[0], bv[:, 1] - b[1]) < 0.5).any()):
                k += 1
                continue
            # (otherwise as before: the tip goes when the polygon stays valid and loses less than a hair-line strip)
            q = Polygon(c[:k] + c[k + 1:], [h.coords for h in p.interiors])
            if q.is_valid and abs(q.area - p.area) < HAIRLINE_LOT * side:
                del c[k]
                done = True
                k = max(0, k - 1)
                continue
        k += 1
    return Polygon(c, [h.coords for h in p.interiors]) if done else p


def _shared(gb, M):
    """Length of M's boundary inside gb (a lot or strip buffered by 0.05 m): 0 at once when their boxes are apart (an empty
    intersection), else the intersection as before."""
    bb, mb = gb.bounds, M["poly"].bounds
    if mb[0] > bb[2] or mb[2] < bb[0] or mb[1] > bb[3] or mb[3] < bb[1]:
        return 0.0
    return gb.intersection(M["poly"].boundary).length


def _union(a, b):
    # U.merge: the plain union when GEOS's mitre inset collapses a ring with near-twin vertices (a lot of 3035 m² became 0 m²
    # and its land was left without a lot, rule 2)
    u = U.merge([a, b])
    return u if u.geom_type == "Polygon" and not u.is_empty else None      # (an empty result has no grade: no union)


def _absorb(M, piece, cut_max, src_terraces=None):
    """Add piece to lot M (one grade when M stays within the cut/fill limit, else as more terraces: the piece's own, or its
    parts on the terraces of the lot it comes from). True when done."""
    u = _union(M["poly"], piece)
    if u is None:
        return False
    g, dev = U.grade(u)
    pt = [piece]
    if src_terraces:
        pt = [q for t in src_terraces for q in U.polys(U.clean(U.from_coords(t["polygon"]).intersection(piece)), 1.0)] or [piece]
    pt = [{"polygon": U.coords(q), "grade_y": gp, "cut_fill_m": dp} for q in pt for gp, dp in [U.grade(q)]]
    if M.get("natural") or (dev <= cut_max and not M.get("terraces")):
        M["poly"], M["grade_y"], M["_dev"] = u, g, dev
        if M.get("terraces"):
            M["terraces"] = M["terraces"] + pt
        return True
    ter = M.get("terraces") or [{"polygon": U.coords(M["poly"]), "grade_y": M["grade_y"], "cut_fill_m": M["_dev"]}]
    if all(t["cut_fill_m"] <= cut_max for t in ter + pt):
        M["terraces"] = ter + pt
        M["poly"] = u
        return True
    return False


def _set_poly(L, q):
    """L keeps q (part of its land): terraces clipped to it, grade recomputed when it has none."""
    L["poly"] = q
    if L.get("terraces"):
        ter = []
        for t in L["terraces"]:
            tp = U.clean(U.from_coords(t["polygon"]).intersection(q))
            for part in U.polys(tp, 1.0):
                g, dev = U.grade(part)
                ter.append({"polygon": U.coords(part), "grade_y": g, "cut_fill_m": dev})
        L["terraces"] = ter if len(ter) > 1 else None
        if not L["terraces"]:
            L.pop("terraces", None)
            L["grade_y"], L["_dev"] = U.grade(q)
    else:
        L["grade_y"], L["_dev"] = U.grade(q)


def street_front(acc_t, q, d=SITE_ACC_M):
    """True when plot q fronts an access street: a red-line polygon of acc_t (an STRtree of the access streets' parts at
    grade) within d. A service plot is carved only where this holds (place_services: a garden 300 m from every road takes
    no school — growing_w, w52)."""
    return acc_t is not None and len(acc_t.query(q, predicate="dwithin", distance=d)) > 0


def strip_joins(N, zrules, spans):
    """A strip block N may join the block behind it: not a spec zone kept whole (lot_split none) or marked no-build, and no
    elevated span over it (golden: u_lrt_viaduct_1, 17 m wide under the LRT span, joined B2127 and took three offices, rule
    25 — w50, w52)."""
    if N["zone"] is not None:
        r = zrules.get(N["zone"]) or {}
        if r.get("lot_split", "none") == "none" or r.get("nobuild") or r.get("no_build"):
            return False
    tree = spans if hasattr(spans, "query") else (U.strtree(spans) if spans else None)
    if tree is not None:
        P = N["poly"]
        for j in tree.query(P, predicate="intersects"):
            if tree.geometries[int(j)].intersection(P).area > 1.0:
                return False
    return True


def join_strips(blocks, zrules, acc_red, spans):
    """Step 2: a utility / reserve strip (up to STRIP_MAX_M deep) on an access street joins the block behind it that takes
    at least STRIP_SHARE of its long side — when strip_joins lets it. Returns (strips, m², [strips kept: zone@x,z])."""
    btree_ = U.strtree([b["poly"] for b in blocks])
    stree = U.strtree(spans) if spans else None
    n_strip, m2_strip, kept = 0, 0.0, []
    for N in sorted(blocks, key=lambda b: b["poly"].area):
        P = N["poly"]
        if N["use"] not in ("utility", "reserve") or N.get("_gone") or P.length <= 0 or 2 * P.area / P.length > STRIP_MAX_M \
                or acc_red.is_empty or P.distance(acc_red) > 0.5:
            continue
        best, best_l = None, 0.0
        for j in btree_.query(P.buffer(0.5), predicate="intersects"):
            R_ = blocks[int(j)]
            if R_ is N or R_.get("_gone") or R_["use"] in ("landmark", "utility", "reserve"):
                continue
            sh = R_["poly"].buffer(0.5).intersection(P.boundary).length
            if sh > best_l:
                best, best_l = R_, sh
        if best is not None and best_l >= STRIP_SHARE * P.length / 2.0:
            if not strip_joins(N, zrules, stree):
                c = P.representative_point()
                kept.append(f"{N['zone'] or 'вне зон'}@{c.x:.0f},{c.y:.0f}")
                continue
            best["poly"] = U.merge([best["poly"], P])
            N["_gone"] = True
            n_strip += 1
            m2_strip += P.area
    return n_strip, m2_strip, kept


def to_grid(blocks, lots, blk_by_id, grid=WRITE_GRID):
    """Blocks and lots in the written precision (WRITE_ND decimals), every lot inside its block. The shape pass, the grading cuts and
    the rounding on write reshaped lots without clipping them back (growing_w: 20 lots 1–6 m² into the next block, rule 1;
    Gate G4: 141 lots over 0.1 m² out of their block): the blocks are snapped to the grid and made disjoint (the larger keeps
    an overlap, a landmark's always), each lot is snapped and clipped to its block with the grid overlay, slivers under
    TILE_SLIVER_M2 dropped, other parts of 1 m² and more made lots of their own. Returns (blocks cut, lots clipped, m²)."""
    for b in blocks:
        parts = sorted(U.polys(U.clean(shapely.set_precision(b["poly"], grid)), 0.0), key=lambda g: -g.area)
        if parts:
            b["poly"] = parts[0]
    nb = 0
    bt = U.strtree([b["poly"] for b in blocks])
    for i, b in enumerate(blocks):
        for j in sorted(int(j) for j in bt.query(b["poly"], predicate="intersects")):
            c = blocks[j]
            if j <= i:
                continue
            ov = shapely.intersection(b["poly"], c["poly"], grid_size=grid)
            if ov.area < DISJOINT_MIN_M2:
                continue
            give = c if (b["use"] == "landmark" or (c["use"] != "landmark" and b["poly"].area >= c["poly"].area)) else b
            keep = b if give is c else c
            parts = sorted(U.polys(U.clean(shapely.difference(give["poly"], keep["poly"], grid_size=grid)), 0.0), key=lambda g: -g.area)
            if parts:
                give["poly"] = parts[0]
                nb += 1
    n, m2 = clip_lots(lots, blk_by_id, grid)
    return nb, n, m2


def clip_lots(lots, blk_by_id, grid=WRITE_GRID):
    """Each lot snapped to the grid and clipped to its block with the grid overlay (to_grid; again after make_disjoint and
    fill_gaps, whose new edges come from a neighbour or a gap and need not follow the block line). Returns (lots, m²)."""
    n, m2, new = 0, 0.0, []
    for L in lots:
        if L.get("_gone"):
            continue
        B = blk_by_id[L["block"]]["poly"]
        q = U.clean(shapely.intersection(shapely.set_precision(L["poly"], grid), B, grid_size=grid))
        parts = sorted(U.polys(q, TILE_SLIVER_M2), key=lambda g: -g.area)
        if not parts:
            L["_gone"] = True
            n += 1
            m2 += L["poly"].area
            continue
        lost = L["poly"].area - sum(g.area for g in parts)
        if len(parts) > 1 or abs(lost) > 1.0:
            _set_poly(L, parts[0])
        else:
            L["poly"] = parts[0]
        for q2 in parts[1:]:
            if q2.area >= 1.0:
                N_ = {k: v for k, v in L.items() if k not in ("poly", "terraces", "capacity")}
                N_["capacity"] = {}
                _set_poly(N_, q2)
                new.append(N_)
        if abs(lost) > 0.1:
            n += 1
            m2 += lost
    lots += new
    return n, m2


def lot_fixed(L):
    """A plot the shape passes do not change: existing, keep and registry plots, landmarks."""
    return L["source"] in FIXED_SOURCES or L["use"] in ("landmark",) or (L["use"] == "village_existing" and L["source"] != "rule")


def make_disjoint(lots, blk_by_id, grid=None):
    """Lots stay disjoint. A lot that grew onto its neighbour's land gives it back: a needle's notch filled (deneedle) against an
    existing plot that keeps its tip, a hair-line slit closed by U.merge across a plot boundary (Gate G1: 22 overlaps of 1–5 m²,
    rule 1). The land stays with the fixed plot, else with the lot whose own block holds more of it, else with the larger lot;
    two fixed plots stay as they are (logged). grid: the overlays in that precision (the written one). Returns (pairs, m²,
    fixed pairs)."""
    live = [L for L in lots if not L.get("_gone")]
    tree = U.strtree([L["poly"] for L in live])
    n, m2, both = 0, 0.0, []
    for i, L in enumerate(live):
        for j in sorted(int(j) for j in tree.query(L["poly"], predicate="intersects")):
            M = live[j]
            if j <= i or L.get("_gone") or M.get("_gone"):
                continue
            ov = U.clean(shapely.intersection(L["poly"], M["poly"], grid_size=grid))
            if ov.is_empty or ov.area < DISJOINT_MIN_M2:
                continue
            fl, fm = lot_fixed(L), lot_fixed(M)
            if fl and fm:
                both.append((L, M, ov.area))
                continue
            if fl != fm:
                give = M if fl else L
            else:
                al = blk_by_id[L["block"]]["poly"].intersection(ov).area
                am = blk_by_id[M["block"]]["poly"].intersection(ov).area
                give = (M if al > am else L) if abs(al - am) > DISJOINT_MIN_M2 else (M if L["poly"].area >= M["poly"].area else L)
            keep = L if give is M else M
            parts = sorted(U.polys(U.clean(shapely.difference(give["poly"], keep["poly"], grid_size=grid)), TILE_SLIVER_M2),
                           key=lambda q: -q.area)
            if not parts:
                continue                       # (a lot wholly inside another: left to the validator, not dropped here)
            _set_poly(give, parts[0])
            for q in parts[1:]:
                N_ = {k: v for k, v in give.items() if k not in ("poly", "terraces", "capacity")}
                N_["capacity"] = {}
                _set_poly(N_, q)
                lots.append(N_)
            n += 1
            m2 += ov.area
    return n, m2, both


def fill_gaps(lots, blk_by_id, grid=None, cut_max=None):
    """Every piece of a block's land in some lot: a crack between existing plots left when the hair-line pass dropped the
    sliver lot of village gardens in it (Gate G1/G4: 3 pieces of 1–2 m² of unnamed land, rule 2) joins the neighbouring lot
    it shares most boundary with — a lot made here first, an existing plot only when no other touches it (registry and keep
    plots, and lots in terraces, keep their outline). A graded lot takes it only when its new outline stays within cut_max
    on one grade, and is graded again (Gate G5: 28 lots written with the grade of their outline before the gap, up to 1.4 m
    off, rule 3); a piece of 1 m² and more no neighbour can take is a green wedge at its terrain. Returns (pieces, m²)."""
    by_blk = defaultdict(list)
    for L in lots:
        if not L.get("_gone"):
            by_blk[L["block"]].append(L)
    n, m2, new = 0, 0.0, []
    for bid, ls in sorted(by_blk.items()):
        B = blk_by_id[bid]["poly"]
        gap = U.clean(shapely.difference(B, unary_union([L["poly"] for L in ls]), grid_size=grid))
        for g in U.polys(gap, GAP_MIN_M2):
            gb = g.buffer(0.05)
            cands = []
            for L in ls:
                if L["use"] == "landmark" or L["source"] in ("registry", "keep") or L.get("terraces") or L["use"] in U.SOCIAL_USES:
                    continue        # (a service plot keeps its norm outline and its distance from the arterials: T6, a school)
                sh = _shared(gb, L)
                if sh >= 0.1:
                    cands.append(((0 if not lot_fixed(L) else 1, -sh), L))
            done = False
            for _, L in sorted(cands, key=lambda t: t[0]):
                u = U.clean(shapely.union(L["poly"], g, grid_size=grid))
                if u.geom_type != "Polygon":
                    continue
                if L.get("natural") or L["source"] in ("existing", "keep") or cut_max is None:
                    L["poly"] = u
                else:
                    g2, d2 = U.grade(u)
                    if d2 > cut_max:
                        continue
                    L["poly"], L["grade_y"], L["_dev"] = u, g2, d2
                done = True
                break
            if not done:
                if g.area < 1.0 or not cands or g.buffer(-HAIRLINE_LOT / 2).is_empty:
                    continue        # (under rule 2's tolerance, or a hair-line: not land)
                N_ = {k: v for k, v in cands[0][1].items() if k not in ("poly", "terraces", "capacity", "norm_key", "plot_norm_m2",
                                                                        "registry_id", "hub", "landmark_model", "houses_in", "nobuild")}
                N_.update(use="park", natural=True, source="rule", capacity={}, label_ru=GAP_GREEN, poly=g)
                N_["grade_y"], N_["_dev"] = U.grade(g)
                new.append(N_)
            n += 1
            m2 += g.area
    lots += new
    return n, m2


def shape_pass(lots, blk_by_id, zone_by_id, norms, home_m2, m2_res, cut_max):
    """Step 5c of run(): strips and needles to the neighbours (or green strips), funnels merged or cut again. Returns
    (strips moved, funnels, green strips)."""
    def rules_of(L):
        return (zone_by_id.get(blk_by_id[L["block"]]["zone"]) or (None, None, {}))[2]

    def width(L):
        return lot_min_width(L["use"], rules_of(L), norms, L.get("plot_norm_m2"))

    forced_cache = {}

    def forced(bid, w):
        k = (bid, round(w, 2))
        if k not in forced_cache:
            bp = blk_by_id[bid]["poly"]
            forced_cache[k] = U.clean(bp.difference(opening(bp, w))).buffer(0.5)
        return forced_cache[k]

    def narrow(L, poly=None):
        p = L["poly"] if poly is None else poly
        w = width(L)
        if w <= 0:
            return U.Polygon()
        hit = L.get("_nar")
        if poly is None and hit is not None and hit[0] is p and hit[1] == w:
            return hit[2]           # the lot's own narrow parts, kept until its polygon or width changes
        nar = U.clean(p.difference(opening(p, w)))
        nar = U.clean(nar.difference(forced(L["block"], w))) if not nar.is_empty else nar
        if poly is None:
            L["_nar"] = (p, w, nar)
        return nar

    def tol(L):
        return max(NARROW_TOL[0], NARROW_TOL[1] * L["poly"].area)

    def fixed(L):
        return lot_fixed(L)

    def green(L):
        return L["use"] in U.GREEN_USES or bool(L.get("natural"))

    def receiver_class(L, M):
        """Order of the neighbours that may take a strip of L (lower first); None: not this one."""
        if M is L or M.get("_gone") or M["use"] in U.SOCIAL_USES or fixed(M) and not (M["source"] == "registry" and M["use"] == L["use"]):
            return None                             # service and kept plots stay as they are; a registry plot takes its own use
        if L.get("nobuild"):
            return 0 if green(M) else None          # protection-zone land stays unbuilt
        if M["use"] == L["use"] and bool(M.get("natural")) == bool(L.get("natural")):
            return 0
        return 1 if green(M) == green(L) else 2

    def split_off(L, keep):
        """L keeps the largest part of keep; the other parts become lots of their own (no capacity)."""
        parts = sorted(U.polys(keep, 1.0), key=lambda q: -q.area)
        if not parts:
            L["_gone"] = True
            return
        _set_poly(L, parts[0])
        for q in parts[1:]:
            N_ = {k: v for k, v in L.items() if k not in ("poly", "terraces", "capacity")}
            N_["capacity"] = {}
            _set_poly(N_, q)
            lots.append(N_)

    n_moved = n_funnel = n_green = 0
    for _ in range(SHAPE_PASSES):
        changed = False
        by_blk = defaultdict(list)
        for L in lots:
            if not L.get("_gone"):
                by_blk[L["block"]].append(L)
        for L in sorted([L for L in lots if not L.get("_gone")], key=lambda L: L["poly"].area):
            if L.get("_gone") or fixed(L) or L["use"] in U.SOCIAL_USES:
                continue
            crumb = L["poly"].area < width(L) ** 2 and L["poly"].area < 0.95 * blk_by_id[L["block"]]["poly"].area
            nar = L["poly"] if crumb else narrow(L)
            if not crumb and nar.area <= tol(L):
                continue
            moved = []
            for c in sorted(U.polys(nar, 0.5), key=lambda q: -q.area):
                cands = []
                gb = c.buffer(0.05)
                for M in by_blk[L["block"]]:
                    k = receiver_class(L, M)
                    if k is None:
                        continue
                    sh = _shared(gb, M)
                    if sh >= 1.0:
                        cands.append((k, -sh, id(M), M))
                # a crumb (no room for a square of its minimum width) goes whole: to a neighbour that stays wide, else to the
                # one it shares most boundary with
                tries = [(M, True) for _, _, _, M in sorted(cands, key=lambda t: t[:3])]
                if crumb:
                    tries += [(M, False) for _, _, _, M in sorted(cands, key=lambda t: t[1:3])]
                for M, check in tries:
                    u = _union(M["poly"], c)
                    if u is None or (check and narrow(M, u).area > narrow(M).area + tol(M)):
                        continue
                    if _absorb(M, c, cut_max, L.get("terraces")):
                        for k_, v_ in (L.get("capacity") or {}).items() if L["poly"].area - c.area < 1.0 else ():
                            M.setdefault("capacity", {})[k_] = (M["capacity"].get(k_) or 0) + v_
                        moved.append(c)
                        n_moved += 1
                        break
                else:
                    if not green(L) and not crumb and L["poly"].area - c.area <= tol(L) and \
                            L["poly"].length ** 2 / L["poly"].area > SHAPE_FAR * shape_norm(L["use"], blk_by_id[L["block"]]["use"],
                                                                                          rules_of(L), norms, home_m2, m2_res):
                        # a strip lot no neighbour takes, too narrow for any building of its zone: a green strip as a whole
                        L.update(use="park", natural=True, capacity={}, label_ru=GREEN_STRIP)
                        L.pop("terraces", None)
                        L["grade_y"], L["_dev"] = U.grade(L["poly"])
                        n_green += 1
                        changed = True
                    elif not green(L) and not crumb and c.area > tol(L) and L["poly"].area - c.area > tol(L):
                        # no neighbour takes it (a service plot's setback band, a strip along a kept plot): a green strip
                        N_ = {k: v for k, v in L.items() if k not in ("poly", "terraces", "capacity", "_dev", "grade_y")}
                        N_.update(use="park", natural=True, capacity={}, label_ru=GREEN_STRIP)
                        N_["poly"], (N_["grade_y"], N_["_dev"]) = c, U.grade(c)
                        lots.append(N_)
                        by_blk[L["block"]].append(N_)
                        moved.append(c)
                        n_green += 1
            if moved:
                split_off(L, U.clean(L["poly"].difference(unary_union(moved).buffer(0.01, join_style="mitre"))))
                changed = True
        # funnels and strips: merged with the same-use neighbour, or the pair cut again square to the block's frame
        for L in sorted([L for L in lots if not L.get("_gone")], key=lambda L: L["poly"].area):
            if L.get("_gone") or fixed(L) or L["use"] in U.SOCIAL_USES or green(L) or L.get("nobuild"):
                continue
            b = blk_by_id[L["block"]]
            if L["poly"].area >= 0.95 * b["poly"].area:
                continue
            rules = rules_of(L)
            norm = shape_norm(L["use"], b["use"], rules, norms, home_m2, m2_res)
            si = L["poly"].length ** 2 / L["poly"].area
            if si <= SHAPE_FAR * norm:
                continue
            best = None
            gb = L["poly"].buffer(0.05)
            for M in by_blk[L["block"]]:
                if M is L or M.get("_gone") or M["use"] != L["use"] or M["source"] != "rule" or M.get("natural") or M.get("terraces"):
                    continue
                sh = _shared(gb, M)
                if sh >= 2.0 and (best is None or sh > best[0]):
                    best = (sh, M)
            if best is None or L.get("terraces"):
                continue
            M = best[1]
            u = _union(L["poly"], M["poly"])
            if u is None:
                continue
            split = rules.get("lot_split", "none")
            t, dmax, mn = split_params(split, rules, norms, home_m2, m2_res)
            pcs = [u] if u.area <= t * 1.35 else U.split_lots(u, max(u.area / 2, mn), dmax, mn, b.get("frame"))
            if any(q.geom_type != "Polygon" for q in pcs) or abs(sum(q.area for q in pcs) - u.area) > 1.0:
                continue        # a cut that leaves land without a lot (a piece apart, a multi-part sliver) is no better shape
            si_new = max(q.length ** 2 / q.area for q in pcs)
            nar_new = sum(narrow(L, q).area for q in pcs)
            grades = [U.grade(q) for q in pcs]
            if si_new >= si or nar_new > narrow(L).area + narrow(M).area + tol(L) or any(dv > cut_max for _, dv in grades):
                continue
            cap = defaultdict(float)
            for X in (L, M):
                for k_, v_ in (X.get("capacity") or {}).items():
                    cap[k_] += v_
            L["poly"], (L["grade_y"], L["_dev"]) = pcs[0], grades[0]
            L["capacity"] = {k_: int(round(v_)) for k_, v_ in cap.items()}
            if len(pcs) > 1:
                M["poly"], (M["grade_y"], M["_dev"]) = pcs[1], grades[1]
                M["capacity"] = {}
                for q, gd in zip(pcs[2:], grades[2:]):
                    N_ = {k: v for k, v in M.items() if k not in ("poly",)}
                    N_["poly"], (N_["grade_y"], N_["_dev"]) = q, gd
                    lots.append(N_)
            else:
                M["_gone"] = True
            n_funnel += 1
            changed = True
        # green strips: a strip of green (or utility) land joins the neighbouring one of the same kind (use, label, protection)
        for L in sorted([L for L in lots if not L.get("_gone")], key=lambda L: L["poly"].area):
            if L.get("_gone") or fixed(L) or not (L["use"] in U.GREEN_USES or L["use"] == "utility"):
                continue
            si = L["poly"].length ** 2 / L["poly"].area
            if si <= SHAPE_FAR * shape_norm(L["use"], None, {}, norms, home_m2, m2_res) or L["poly"].area >= 0.95 * blk_by_id[L["block"]]["poly"].area:
                continue
            best = None
            gb = L["poly"].buffer(0.05)
            for M in by_blk[L["block"]]:
                if (M is L or M.get("_gone") or fixed(M) or M["use"] != L["use"] or M.get("label_ru") != L.get("label_ru")
                        or bool(M.get("nobuild")) != bool(L.get("nobuild")) or bool(M.get("natural")) != bool(L.get("natural"))):
                    continue
                sh = _shared(gb, M)
                if sh >= 2.0 and (best is None or sh > best[0]):
                    best = (sh, M)
            if best is None:
                continue
            M = best[1]
            u = _union(L["poly"], M["poly"])
            if u is None or u.length ** 2 / u.area >= si:
                continue
            if not _absorb(M, L["poly"], cut_max, L.get("terraces")):
                continue
            L["_gone"] = True
            n_funnel += 1
            changed = True
        if not changed:
            break
    # hair-line spikes (thinner than HAIRLINE_LOT, not the block's own tip) cut off every plot made here, needle tips taken off,
    # and a plot whose ring would fold when written with WRITE_ND decimals snapped to that grid (a zero-width needle collapses); a
    # plot that falls apart at a hair-line bridge keeps every part (the others become plots of their own)
    for L in list(lots):
        if L.get("_gone") or fixed(L):
            continue
        p = L["poly"]
        body = opening(p, HAIRLINE_LOT)
        sp = U.clean(p.difference(body))
        fb = forced(L["block"], HAIRLINE_LOT) if not sp.is_empty else None
        # a needle (not the noise of the opening) that is mostly not the block's own
        sp = [c for c in U.polys(sp, 0.0) if c.length > 4 * HAIRLINE_LOT and c.boundary.difference(fb).length > 0.5 * c.length]
        q = U.clean(p.difference(U.clean(U.clean(unary_union(sp).buffer(HAIRLINE_LOT / 2, join_style="mitre")).difference(body)))) if sp else p
        parts = []
        for x in U.polys(q, 1.0):
            x = deneedle(x, blk_by_id[L["block"]]["poly"])
            if Polygon(U.coords(x, WRITE_ND), U.holes(x, WRITE_ND) or None).is_valid:
                parts.append(x)
            else:
                parts += U.polys(U.clean(shapely.set_precision(x, WRITE_GRID)), 1.0)
        if len(parts) != 1 or not parts[0].equals(p):
            split_off(L, MultiPolygon(parts) if parts else Polygon())
    return n_moved, n_funnel, n_green


SITE_USES = {"residential_high", "residential_mid", "residential_low", "mixed_centre", "business", "waterfront", "village_existing"}
SERVICE_ORDER = ["school", "kindergarten", "polyclinic", "pharmacy_shop", "fire_station", "playground"]
LABEL = {"school": "школа", "kindergarten": "детский сад", "polyclinic": "поликлиника", "pharmacy_shop": "аптека и магазины",
         "fire_station": "пожарное депо", "playground": "сквер-площадка у домов"}
RL_KEY = {"school": "schools.building_from_red_line_m", "kindergarten": "kindergartens.building_from_red_line_m"}
SITE_STOP_MARGIN = 3.0   # the greedy loop of a kind stops after this × (land with homes / π r²) sites, one per block with homes
                         # and the places short over the smallest facility — far more than a cover of the district needs (model qTwin)
SITE_SAFETY_CAP = 5000   # sites of one kind per district: a pure safety cap of the loop, far above the stop above
SITE_EDGE_USES = {"reserve"}   # land next to a village that may take a site its houses reach no other way (model qTwin)
SITE_BATCH = 30          # candidate sites checked on foot per batch after the first 30 (model qTwin)
GROUP_LINK = 100.0       # m: homes outside the radius closer than this to each other are one group in the log (model qTwin)


def r_pieces(r, norms, home_m2, m2_res):
    """Provisional (cached) lots of a rest: [(polygon, residents)]. Residents = zone homes/ha × lot ha × k × home m² / m² per
    resident, k spreading the zone's homes over its residential land (CityStats: residents = housing GFA / 30)."""
    if r.get("_pieces") is not None:
        return r["_pieces"]
    tgt, depth, mn = split_params(r["split"], r["rules"], norms, home_m2, m2_res)
    out = []
    for part in U.polys(r["poly"], 1.0):
        pcs = U.split_lots(part, tgt, depth, mn, r["b"].get("frame")) if part.area > tgt * 1.35 else [part]
        for q in pcs:
            res = (r["rules"].get("homes_per_ha") or 0) * q.area / 1e4 * r.get("k", 1.0) * home_m2 / m2_res if not r["village"] else 0.0
            out.append((q, res))
    r["_pieces"] = out
    return out


def place_services(rests, lots, zone_by_id, walk, soc, norms, spec, home_m2, m2_res, log, arterial, add_lot, split_params_fn, street_rl,
                   houses=(), zone_net=None, lot_setback=None, acc_blocks=None, fronts=None, near_street=None):
    """Service lots by greedy coverage of the homes (rule 14) and by places per 1000 residents (genplan minimum).

    Demand: provisional lots of every rest in a zone with homes (residents by zone density) and every existing house lot
    (coverage only). Distance: walking on the network (fire station: straight line, rules.json rule 14). Each step either
    covers homes that no facility of the kind reaches (the site that reaches most of them) or, when every home is reached
    but places are short within the radius (flow_unmet: the maximum flow rule 14 measures), adds a facility where the site
    reaches most of the places short. Capacity = the places short within the site's radius, within the norms' smallest
    band and typical capacity; the loop ends when no home is short of places in its radius; plot from the plot norms;
    school and kindergarten plots keep setbacks.housing_from_arterial_carriageway_m from arterial carriageways."""
    work = U.work_polygon(spec)
    m2_seat, m2_kg = U.social_m2(norms)
    # residents spread over the zone's net block area (gen_buildings calibrates homes the same way: density × net block ha)
    zone_area = dict(zone_net) if zone_net is not None else {zid: zp.intersection(work).area for zid, (z, zp, r) in zone_by_id.items()}
    carrier = {}
    for r in rests:
        r["low"] = U.low_rise(r["rules"], norms) if r["rules"].get("floors") else True
        if not r["village"] and (r["rules"].get("homes_per_ha") or 0) > 0:
            carrier[r["zone"]] = carrier.get(r["zone"], 0.0) + r["poly"].area
    for r in rests:
        r["k"] = zone_area.get(r["zone"], 0.0) / carrier[r["zone"]] if carrier.get(r["zone"]) else 1.0
    existing = [L for L in lots if L["source"] == "existing" and L["use"] in U.RESIDENTIAL_USES]
    # residents of existing houses: their floor area / m² per resident (the twin's CityStats formula), village norms in villages
    htree = U.strtree([h_["fp"] for h_ in houses]) if houses else None
    for L in existing:
        hs = [houses[int(j)] for j in htree.query(L["poly"], predicate="intersects")] if htree is not None else []
        L["_res"] = sum(g_ for g_ in (h_["fp"].area * h_.get("floors", 1) for h_ in hs if L["poly"].contains(h_["fp"].centroid))
                        if g_ <= U.EXISTING_HOME_M2) / m2_res
        L["_vil"] = L["use"] == "village_existing"
    log(f"жители существующих домов: площадь дома × этажи / м² на жителя (CityStats), дома до {U.EXISTING_HOME_M2:.0f} м² "
        "(больше — рабочие места, как в модели трафика); в сёлах — сельские радиусы", [],
        residents=round(sum(L["_res"] for L in existing)), houses_lots=len(existing))

    # keep quarters and landmark lots hold homes by their zone's density (gen_buildings writes them as lot capacity and the
    # validator counts them in places per 1000): they need places, not coverage (no house of theirs is in the service table)
    keep_dem = []
    for L in lots:
        if L["use"] == "landmark":
            zr = (zone_by_id.get(L["block_zone"]) or (None, None, {}))[2] if L.get("block_zone") else {}
            res = (zr.get("homes_per_ha") or 0) * L["poly"].area / 1e4 * home_m2 / m2_res
            if res > 0:
                c = L["poly"].centroid
                keep_dem.append({"x": c.x, "y": c.y, "res": res, "w": 0.0, "low": False, "ri": None, "vil": False})
    if keep_dem:
        log("жители ключевых кварталов и ориентиров по плотности зоны: только места, не радиусы", [], residents=round(sum(q["res"] for q in keep_dem)))

    def rest_area(r):
        """Area of a rest, kept until the rest changes."""
        hit = r.get("_area")
        if hit is None or hit[0] is not r["poly"]:
            hit = r["_area"] = (r["poly"], r["poly"].area)
        return hit[1]

    def demand():
        out = list(keep_dem)
        parts = [None]          # the demand list in parts (keep quarters, each rest, existing houses) for pool_points
        # a zone keeps its homes while service plots take its land (gen_buildings calibrates homes to density × net block
        # area, and the validator counts the homes built): the residents of a zone spread over the land left
        car = defaultdict(float)
        for r in rests:
            if not r["village"] and (r["rules"].get("homes_per_ha") or 0) > 0:
                car[r["zone"]] += rest_area(r)
        for ri, r in enumerate(rests):
            if r["village"] or not (r["rules"].get("homes_per_ha") or 0) > 0:
                continue
            f = zone_area.get(r["zone"], 0.0) / car[r["zone"]] / r["k"] if car[r["zone"]] > 0 and r["k"] > 0 else 1.0
            pcs = r_pieces(r, norms, home_m2, m2_res)
            if r.get("_cent") is None or r["_cent"][0] is not pcs:      # piece centres, kept until the rest changes
                r["_cent"] = [pcs, [(q.centroid.x, q.centroid.y) for q, _ in pcs], None]
            for (cx, cy), (q, res) in zip(r["_cent"][1], pcs):
                out.append({"x": cx, "y": cy, "res": res * f, "w": res * f, "low": r["low"], "ri": ri, "vil": False})
            if pcs:
                parts.append(r["_cent"])
        out = out + dem_ex
        dem_parts[:] = [out, parts]
        return out
    dem_parts = []      # [the last demand list, its parts]
    dem_ex = []         # existing houses: the same in every round
    for L in existing:
        c = L["poly"].centroid
        dem_ex.append({"x": c.x, "y": c.y, "res": L["_res"], "w": L["_res"], "low": True, "ri": None, "vil": L["_vil"]})
    dem = demand()
    total_res = sum(q["res"] for q in dem)
    log("жители по плотностям зон (оценка для соцобъектов)", [], residents=round(total_res))
    sq_min = norms.v("parks.square_or_playground", "min_area_m2")
    sb_art = norms.v("setbacks.housing_from_arterial_carriageway_m", "default")
    art_zone = arterial.buffer(sb_art + ART_TOL_M) if not arterial.is_empty else U.Polygon()

    builtin_hosts = []    # one-group built-in kindergartens added for multi-storey homes no standalone site reaches
    small_soc = []        # facilities below the typical capacity: the demand within their radius is that small (logged)
    m2_visit = U.twin_norms().M2_PER_CLINIC_VISIT
    ring_w = norms.v("fire_access.width_min_m", "default") + norms.v("fire_access.distance_to_wall_m", "building_10_28m")["min"]

    def building_fit(kind, cap, r, keep_free, kf_loc=None):
        """fit(q) → True when gen_buildings will place this kind's building on plot q (same setbacks, same placer). kf_loc:
        keep_free clipped round the site the plots are cut from (the same difference inside it, without the district)."""
        gfa_of = {"school": lambda q: cap * m2_seat, "kindergarten": lambda q: cap * m2_kg, "polyclinic": lambda q: cap * m2_visit,
                  "pharmacy_shop": lambda q: q.area * 0.35, "fire_station": lambda q: q.area * 0.25}.get(kind)
        if gfa_of is None or lot_setback is None:
            return None

        def f(q):
            region = U.clean(q.buffer(-lot_setback(q, r["rules"]), join_style="mitre"))
            if keep_free is not None and not keep_free.is_empty:
                kf_ = keep_free if kf_loc is None else kf_loc
                if not kf_.is_empty:
                    region = U.clean(region.difference(kf_))
            if near_street is not None and (r["village"] or r["use"] in SITE_EDGE_USES):
                # a village plot: the building within the building-line limit of a street carriageway, as gen_buildings
                # places it there first; else, as any plot, with the fire ring inside it — the plot fronts an access
                # street (carve's front), so the drive and the ring run inside the plot from that street. A garden no
                # carriageway reaches has no front and takes no service: the next site in the radius does (w52). The band
                # alone took 66 of Gate's 152 village kindergartens and doubled the village houses out of their radius
                if LM.social_place(near_street(region), gfa_of(q), LM.SOCIAL_FLOORS[kind][1], U.axis(q)[0], None) is not None:
                    return True
            # a plot is chosen so that the fire ring fits inside it round the whole building (fire_access.ring_required:
            # schools, kindergartens); gen_buildings still falls back to a placement without it on a registry plot
            return LM.social_place(region, gfa_of(q), LM.SOCIAL_FLOORS[kind][1], U.axis(q)[0],
                                   ring_w if kind in LM.SOCIAL_RING_LOT else None, ring_only=RING_ONLY) is not None
        return f

    def kept(d_, key, poly, fn):
        """fn(poly), kept in d_[key] until d_'s polygon changes."""
        hit = d_.get(key)
        if hit is None or hit[0] is not poly:
            hit = d_[key] = (poly, fn(poly))
        return hit[1]

    def lot_c(L):
        return kept(L, "_c", L["poly"], lambda p: (p.centroid.x, p.centroid.y))

    def piece_c(r):
        """Centres of a rest's provisional lots [(x, z)], with their pieces [(polygon, residents)]."""
        pcs = r_pieces(r, norms, home_m2, m2_res)
        return zip(pcs, kept(r, "_pc", pcs, lambda pcs: [(q.centroid.x, q.centroid.y) for q, _ in pcs]))

    def providers(kind):
        # (centres and entrances kept per polygon: the same points every round until a lot or rest changes)
        pts = [lot_c(L) for L in lots if L["use"] == kind]
        if kind == "kindergarten":        # built-in kindergartens (kindergartens.placement) in multi-storey lots of ≥ one group
            g = norms.v("kindergartens.group_size_max", "3-7_years")
            pk = soc.per_resident("kindergarten", False) * soc.kg_builtin_share
            pts += [c for r in rests if not r["low"] and not r["village"] for (q, res), c in piece_c(r) if res * pk >= g]
            pts += [(x, y) for x, y in builtin_hosts]
        if kind == "pharmacy_shop":       # ground floors of mixed and business land carry shops and pharmacies
            pts += [c for r in rests if r["use"] in ("mixed_centre", "business") for _, c in piece_c(r)]
        if kind == "playground":          # parks ≥ the minimum area (entered at their edge, as rule 14 measures) and courtyards
            pts += [xy for L in lots if L["use"] in ("park", "square", "playground") and L["poly"].area >= sq_min
                    and not (L.get("label_ru") or "").startswith(("клин", "зелёный клин")) for xy in kept(L, "_ent", L["poly"], U.entrances)]
            pts += [c for r in rests if r["split"] in ("perimeter", "towers") for (q, _), c in piece_c(r) if q.area >= 4 * sq_min]
        return pts

    rad_ = {}

    def radii(kind, pool):
        """Service radius of every demand point (once per kind, rise and village)."""
        out = np.empty(len(pool))
        for i, q in enumerate(pool):
            k = (kind, q["low"], q["vil"])
            r_ = rad_.get(k)
            if r_ is None:
                r_ = rad_[k] = soc.radius(kind, q["low"], q["vil"])
            out[i] = r_
        return out

    def dists(kind, pts, pool, cutoff=None, P=None):
        """Distance from the nearest of pts to every point of pool (walking; fire station: straight line). With cutoff the
        distances up to it are exact and the farther ones inf or more — enough for «within the radius» with cutoff over it."""
        if not pts:
            return np.full(len(pool), np.inf)
        if kind == "fire_station":
            XY = np.array([[q["x"], q["y"]] for q in pool]).reshape(-1, 2)
            d = np.full(len(pool), np.inf)
            for x, y in pts:
                d = np.minimum(d, np.hypot(x - XY[:, 0], y - XY[:, 1]))
            return d
        D = walk.dist_from(pts, cutoff)
        return walk.dist_many(P if P is not None else pool_points(pool), D)

    prov_st = {}

    def prov_dists(kind, pts, pool, cutoff):
        """dists from the providers of the greedy loop: the walking run of the providers kept between rounds, only the new
        ones walked and merged by np.minimum (exactly the multi-source run: its distance is the minimum of its sources'); a
        provider gone (a rest cut) or another cutoff: walked again from all of them."""
        if kind == "fire_station" or not pts:
            return dists(kind, pts, pool, cutoff)
        st = prov_st.get(kind)
        S = set(pts)
        if st is None or st["cut"] != cutoff or not st["set"] <= S:
            arr = walk.dist_arr(pts, cutoff)
            st = prov_st[kind] = {"cut": cutoff, "set": S, "Dn": walk.dense(arr), "same": {k: list(v) for k, v in arr[2].items()}}
        else:
            new = [p for p in pts if p not in st["set"]]
            if new:
                arr = walk.dist_arr(new, cutoff)
                np.minimum(st["Dn"], walk.dense(arr), out=st["Dn"])
                for sid, srcs in arr[2].items():
                    st["same"].setdefault(sid, []).extend(srcs)
                st["set"] = S
        P = pool_points(pool)
        last_P[:] = [pool, P]
        return walk.dist_dense(P, st["Dn"], st["same"])

    last_P = []             # [pool, its walk.points] of the last prov_dists

    def sub_points(pool, idx):
        """walk.points of pool[i] for i in idx: taken from the snapped pool of the round (the same snaps), else snapped."""
        if not last_P or last_P[0] is not pool:
            return walk.points([(pool[i]["x"], pool[i]["y"]) for i in idx])
        P = last_P[1]
        idx = np.asarray(idx, dtype=np.int64)
        return tuple(a[idx] for a in P[:5]) + (P[5].subset(idx),)

    cand_D = {}                 # walking runs from candidate sites (x, z, cutoff): a site unchanged between rounds is not walked again
    CAND_D_MAX = 40000          # runs kept at most (memory); the store starts again when full

    def cand_dist(x, y, cut, P, buf):
        k = (x, y, cut)
        arr = cand_D.get(k)
        if arr is None:
            if len(cand_D) >= CAND_D_MAX:
                cand_D.clear()
            arr = cand_D[k] = walk.dist_arr([(x, y)], cut)
        return walk.dist_dense(P, walk.dense(arr, buf), arr[2])

    ex_P, kd_P = [], []

    def pool_points(pool):
        """walk.points of a demand list. The last list of demand() is put together from its parts, each snapped once: the
        keep quarters, the piece centres of each rest (until the rest changes) and the existing houses (the same every round);
        the points are snapped in the order of the list as before."""
        if not dem_parts or pool is not dem_parts[0]:
            n = len(dem_ex)
            if not n or len(pool) < n or pool[len(pool) - n] is not dem_ex[0]:
                return walk.points([(q["x"], q["y"]) for q in pool])
            h = walk.points([(q["x"], q["y"]) for q in pool[:len(pool) - n]])
            if not ex_P:
                ex_P.append(walk.points([(q["x"], q["y"]) for q in dem_ex]))
            segs = [h, ex_P[0]]
        else:
            segs = []
            for part in dem_parts[1]:
                if part is None:            # keep quarters
                    if not kd_P:
                        kd_P.append(walk.points([(q["x"], q["y"]) for q in keep_dem]))
                    segs.append(kd_P[0])
                else:
                    if part[2] is None:
                        part[2] = walk.points(part[1])
                    segs.append(part[2])
            if dem_ex:
                if not ex_P:
                    ex_P.append(walk.points([(q["x"], q["y"]) for q in dem_ex]))
                segs.append(ex_P[0])
        return tuple(np.concatenate([P_[j] for P_ in segs]) for j in range(5)) + (U.SegIndex.concat([P_[5] for P_ in segs]),)

    if not art_zone.is_empty:
        shapely.prepare(art_zone)
    site_c, fit_c, kf_cache = {}, {}, {}

    def rest_site(ri, r, art):
        """(site, its point): the largest usable part of a rest (outside the arterial band for school and kindergarten),
        kept until the rest changes."""
        hit = site_c.get((ri, art))
        if hit is None or hit[0] is not r["poly"]:
            usable = r["poly"]
            if art and not art_zone.is_empty and usable.intersects(art_zone):
                usable = U.clean(usable.difference(art_zone))
            parts = U.polys(usable, 1.0)
            site = max(parts, key=lambda q: q.area) if parts else None
            hit = site_c[(ri, art)] = (r["poly"], site, site.representative_point() if site is not None else None)
        return hit[1], hit[2]

    def site_ok(kind, ri, r, art, placed, cap_lo):
        """(site, point, fit) of a rest that holds the smallest plot of the kind as a usable shape, else None."""
        site, c = rest_site(ri, r, art)
        if site is None:
            return None
        k = (kind, ri, art)
        hit = fit_c.get(k)
        if hit is None or hit[0] is not site:
            fit = soc.fit(kind, site.area, r, split_params_fn, home_m2, m2_res)
            if fit is not None:
                need_lo = soc.plot(kind, cap_lo)[0] if placed else soc.site_plot(kind, r, split_params_fn, home_m2, m2_res)[0]
                if need_lo and not chunky(site, need_lo):
                    fit = None          # a strip too narrow for the smallest plot of the kind is not a usable plot
            hit = fit_c[k] = (site, fit)
        return (site, c, hit[1]) if hit[1] is not None else None

    def flow_unmet(kind, cap_key, dem_pl, R, buf):
        """Places short at each demand point as rule 14 measures them: a maximum flow of every point's places (dem_pl) to the
        capacities of the facilities of the kind on the map within its walking radius R (validator capacity_gaps; the
        facility at its lot's centre). A point no facility reaches is short of all its places (green o5, w51: 166 % of the
        genplan's school places in the district and 164 schools short in their radius — the sites were sized to the
        district total, not to what rule 14 counts)."""
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import maximum_flow
        from scipy.spatial import cKDTree
        provs = [(lot_c(L), float((L.get("capacity") or {}).get(cap_key, 0) or 0)) for L in lots if L["use"] == kind]
        provs = [(c_, cp) for c_, cp in provs if cp > 0]
        H = len(dem)
        if not provs or not H or float(dem_pl.sum()) <= 0:
            return dem_pl.copy()
        XY = np.array([[q["x"], q["y"]] for q in dem])
        kd = cKDTree(XY)
        cut = float(R.max()) + 1.0
        eh, ek = [], []
        for k, ((cx, cy), cp) in enumerate(provs):
            ii = np.array(sorted(kd.query_ball_point([cx, cy], cut)), dtype=np.int64)
            if len(ii):
                ii = ii[(dem_pl[ii] > 0) & (np.hypot(XY[ii, 0] - cx, XY[ii, 1] - cy) <= R[ii])]
            if not len(ii):
                continue
            d = cand_dist(cx, cy, cut, sub_points(dem, ii), buf)
            ok = ii[d <= R[ii]]
            eh.append(ok)
            ek.append(np.full(len(ok), k, dtype=np.int64))
        if not eh or not sum(len(e) for e in eh):
            return dem_pl.copy()
        eh, ek = np.concatenate(eh), np.concatenate(ek)
        Pn = len(provs)
        sink = H + Pn + 1
        big = int(round(float(dem_pl.sum()) * 100)) + 1
        reach = np.unique(eh)
        rows = np.concatenate([np.zeros(len(reach), np.int64), 1 + eh, 1 + H + np.arange(Pn)])
        cols = np.concatenate([1 + reach, 1 + H + ek, np.full(Pn, sink)])
        caps = np.concatenate([np.ceil(dem_pl[reach] * 100), np.full(len(eh), big), np.floor(np.array([cp for _, cp in provs]) * 100)])
        G = csr_matrix((caps.astype(np.int32), (rows, cols)), shape=(sink + 1, sink + 1))
        G.sum_duplicates()
        F = maximum_flow(G, 0, sink).flow
        got = np.asarray(F[0, 1:H + 1].todense()).ravel() / 100.0
        return np.maximum(dem_pl - got, 0.0)

    def grow_existing(kind, cap_key, unmet, R, buf, cap_hi):
        """Places short that no new facility of the smallest size is worth (under NEW_SITE_MIN_SHARE of it in reach) go to the
        facilities of the kind made here that reach them on foot, while their plot holds the larger capacity by the plot norms
        (tester item 79: no 25-place school beside a full one for 11 places short). Returns the places added."""
        from scipy.spatial import cKDTree
        mi = np.flatnonzero(unmet > 0.01)
        if not len(mi):
            return 0.0
        XY = np.array([[dem[i]["x"], dem[i]["y"]] for i in mi])
        kd = cKDTree(XY)
        cut = float(R.max()) + 1.0
        left = unmet.copy()
        added = 0.0
        for L in lots:
            if L["use"] != kind or L["source"] != "rule" or not (L.get("capacity") or {}).get(cap_key):
                continue
            cx, cy = lot_c(L)
            jj = np.array(sorted(kd.query_ball_point([cx, cy], cut)), dtype=np.int64)
            if not len(jj):
                continue
            ii = mi[jj]
            d = cand_dist(cx, cy, cut, sub_points(dem, ii), buf)
            ii = ii[(d <= R[ii]) & (left[ii] > 0.01)]
            u = float(left[ii].sum())
            if u < 0.5:
                continue
            c0 = L["capacity"][cap_key]
            c1 = soc.cap_round(kind, c0 + u) if kind != "polyclinic" else int(math.ceil(c0 + u))
            c1 = min(c1, int(cap_hi))
            if c1 <= c0:
                continue
            need_m2, nkey = soc.plot(kind, c1)
            if need_m2 is None or need_m2 > L["poly"].area:
                continue
            L["capacity"][cap_key] = int(c1)
            L["plot_norm_m2"], L["norm_key"] = round(need_m2), nkey
            left[ii] = 0.0
            added += c1 - c0
        return added

    home_rests = [r for r in rests if r["village"] or (r["rules"].get("homes_per_ha") or 0) > 0]
    land_dem = sum(r["poly"].area for r in home_rests) + sum(L["poly"].area for L in existing)
    blocks_dem = len({r["b"]["id"] for r in home_rests} | {L["block"] for L in existing})

    def site_stop(kind, need):
        """Sites of a kind after which the greedy loop stops: SITE_STOP_MARGIN covers of the land with homes by the smallest
        radius of the kind, one more per block with homes (scattered villages), and the places short over the smallest
        facility; under the pure safety cap."""
        r_min = min(soc.radius(kind, lo, v) for lo in (True, False) for v in (False, True))
        n = SITE_STOP_MARGIN * land_dem / (math.pi * r_min ** 2) + blocks_dem
        if kind in ("school", "kindergarten", "polyclinic"):
            n += need / max(soc.cap_limits(kind)[0], 1)
        return int(min(SITE_SAFETY_CAP, math.ceil(n)))

    def why_groups(kind, idx, R, placed, cap_lo, art, unusable, hint=None):
        """Groups of the demand points idx (homes outside the radius), each with where it is and why no site serves it."""
        from scipy.spatial import cKDTree
        P = np.array([[dem[i]["x"], dem[i]["y"]] for i in idx])
        par = list(range(len(idx)))

        def root(a):
            while par[a] != a:
                par[a] = par[par[a]]
                a = par[a]
            return a
        for a, b in cKDTree(P).query_pairs(GROUP_LINK):
            par[root(a)] = root(b)
        groups = defaultdict(list)
        for k in range(len(idx)):
            groups[root(k)].append(idx[k])
        land = [(ri, r) for ri, r in enumerate(rests) if (r["use"] in SITE_USES or r["use"] in SITE_EDGE_USES) and r["poly"].area >= 1.0]
        ltree = U.strtree([r["poly"] for _, r in land]) if land else None
        out = []
        for ii in sorted(groups.values(), key=lambda ii: (-sum(dem[i]["w"] for i in ii), ii[0])):
            Rg = float(max(R[i] for i in ii))
            mp = MultiPoint([(dem[i]["x"], dem[i]["y"]) for i in ii])
            near = [land[int(j)] for j in ltree.query(mp, predicate="dwithin", distance=Rg)] if ltree is not None else []
            ok, unus = [], False
            for ri, r in near:
                s_ = site_ok(kind, ri, r, art, placed, cap_lo)
                if s_ is None:
                    continue
                if (ri, kind) in unusable:
                    unus = True
                    continue
                ok.append((s_[1].x, s_[1].y))
            if not near:
                why = "в радиусе нет свободной земли: вокруг участки домов и объектов, улицы, вода или граница района"
            elif not ok:
                why = "участок в радиусе не вмещает здание с отступами" if unus else "свободная земля в радиусе меньше или уже участка нормы"
            else:
                d = dists(kind, ok, [dem[i] for i in ii], Rg + 1.0)
                if not (d <= np.array([R[i] for i in ii])).any():
                    why = "свободная земля в радиусе по прямой, но середина участка пешком по сети дальше радиуса"
                else:
                    why = hint or "жителей группы меньше самого малого объекта таблицы норм (нужен встроенный объект или сосед)"
            c = mp.centroid
            out.append({"at": [round(c.x), round(c.y)], "points": len(ii), "existing_lots": sum(1 for i in ii if dem[i]["ri"] is None),
                        "residents": round(sum(dem[i]["w"] for i in ii)), "reason": why})
        return out

    for kind in SERVICE_ORDER:
        per_res = {lo: (soc.per_resident(kind, not lo) if kind in ("school", "kindergarten", "polyclinic") else 0.0) for lo in (True, False)}
        placed = kind in ("school", "kindergarten", "polyclinic")
        need = sum(q["res"] * per_res[q["low"]] for q in dem)
        # supply already on the map: spec / registry lots and lots placed before (validator: places of every lot of the kind)
        cap_key = "visits_per_shift" if kind == "polyclinic" else "places"
        have = float(sum((L.get("capacity") or {}).get(cap_key, 0) for L in lots if L["use"] == kind)) if placed else 0.0
        if have:
            log(f"{kind}: места на карте до размещения (спецификация и реестр)", [], have=round(have), need=round(need))
        cap_lo, cap_hi = soc.cap_limits(kind)
        art = kind in ("school", "kindergarten")
        n_new = 0
        unusable = set()
        stop = site_stop(kind, need)
        flow_buf = np.empty(walk.G.number_of_nodes() + 1) if placed else None
        last_pick = None        # (rest, places short before) of the facility placed last
        n_grow = 0              # rounds that gave the places short to the facilities near them
        edge = False        # village edges: reserve land next to the houses, once no site of the residential land reaches them
        hint = None
        while True:
            pts = providers(kind)
            R = radii(kind, dem)
            Wd = np.array([q["w"] for q in dem])
            dd = prov_dists(kind, pts, dem, float(R.max()) + 1.0 if len(R) else None)
            unc = np.flatnonzero((dd > R) & (Wd > 0))
            # places short where rule 14 counts them: the flow of each home's places to the facilities within its radius
            if placed:
                dem_pl = np.array([q["res"] * per_res[q["low"]] for q in dem])
                unmet = flow_unmet(kind, cap_key, dem_pl, R, flow_buf)
                short = float(unmet.sum())
            else:
                dem_pl = unmet = None
                short = 0.0
            if placed and last_pick is not None and short > last_pick[1] - 0.5:
                unusable.add((last_pick[0], kind))     # the facility just placed seats nothing more: not that site again
            last_pick = None
            # a new facility while the district is short of the genplan's places too (not for the places short in a radius
            # alone: the provisional homes sit at their lots' centres, farther from the streets than the houses will, and the
            # gate_trial school plots then took a quarter of r_high_ne's homes, rule 24); the places short in a radius once
            # the district has its places go to the facilities that reach them (grow_existing)
            short_d = need - have if placed else 0.0
            want_places = placed and short > 0.5 and short_d > 0.5
            if len(unc) == 0 and not want_places:
                if placed and short > 0.5:
                    g_ = grow_existing(kind, cap_key, unmet, R, flow_buf, cap_hi)
                    if g_ > 0:
                        n_grow += 1
                        have += g_
                        log(f"{kind}: недостающие в радиусе места отданы объектам рядом, участок которых их вмещает (замечание 79)",
                            [], places=round(g_), short_before=round(short, 1))
                        continue
                    log(f"{kind}: места района по генплану есть, в радиусе части домов их не хватает, и объекты рядом их не вмещают "
                        f"(спрос не размещён)", [f"{dem[i]['x']:.0f},{dem[i]['y']:.0f}" for i in np.argsort(-unmet)[:40] if unmet[i] > 0.01],
                        short_places=round(short, 1), warn=True)
                break
            if n_new >= stop:
                hint = f"достигнут предел числа участков вида ({stop}: SITE_STOP_MARGIN × земля с домами / πr² + кварталы с домами + недостающие места)"
                log(f"{kind}: {hint}", [], sites=n_new, uncovered=int(len(unc)), short_places=round(short), warn=True)
                break
            U_pts = np.array([[dem[i]["x"], dem[i]["y"]] for i in unc]) if len(unc) else np.zeros((0, 2))
            U_w = np.array([dem[i]["w"] for i in unc])
            U_pl = np.array([dem[i]["res"] * per_res[dem[i]["low"]] for i in unc])
            U_R = R[unc]
            U_vil = np.array([dem[i]["vil"] for i in unc], dtype=bool)
            U_ex = np.array([dem[i]["ri"] is None for i in unc], dtype=bool)
            UP = sub_points(dem, unc) if len(unc) and kind != "fire_station" else None
            dn_buf = np.empty(len(walk._nidx) + 1) if UP is not None else None
            cut = float(U_R.max()) + 1.0 if len(unc) else None
            utree = None
            if len(unc):
                from scipy.spatial import cKDTree
                utree = cKDTree(U_pts)

            def reach(cx, cy, near):
                """(weight, village weight, existing weight) of the uncovered homes within the radius of (cx, cy) by straight line
                (near: the index's points within cut of it; in ascending order, so the sums are those of a mask over all)."""
                if utree is None:
                    return 0.0, 0.0, 0.0
                ii = np.array(sorted(near), dtype=np.int64)
                if not len(ii):
                    return 0.0, 0.0, 0.0
                ii = ii[np.hypot(U_pts[ii, 0] - cx, U_pts[ii, 1] - cy) <= U_R[ii]]
                return float(U_w[ii].sum()), float(U_w[ii[U_vil[ii]]].sum()), float(U_w[ii[U_ex[ii]]].sum())

            # candidate sites: usable part of each rest, with the largest capacity it holds
            pre = []
            for ri, r in enumerate(rests):
                is_edge = r["use"] in SITE_EDGE_USES
                if (r["use"] not in SITE_USES and not (edge and is_edge)) or rest_area(r) < 1.0 or (ri, kind) in unusable:
                    continue
                if acc_blocks is not None and kind != "playground" and r["b"]["id"] not in acc_blocks:
                    continue        # no street to enter its block from: no drive reaches the building (rule 12)
                s_ = site_ok(kind, ri, r, art, placed, cap_lo)
                if s_ is not None:
                    pre.append((ri, is_edge, s_))
            # the index asked once for every candidate centre (the same points per centre as one query each)
            near_all = utree.query_ball_point(np.array([[s_[1].x, s_[1].y] for _, _, s_ in pre]), cut) \
                if utree is not None and pre else None
            cands = []
            for j, (ri, is_edge, s_) in enumerate(pre):
                site, c, fit = s_
                cov_s, cov_v, cov_e = reach(c.x, c.y, near_all[j] if near_all is not None else ())
                if is_edge and cov_e <= 0:
                    continue        # village-edge land only for the existing homes no other site reaches
                cands.append({"ri": ri, "site": site, "fit": fit, "c": c, "cov_s": cov_s, "cov_v": cov_v, "edge": is_edge})
            if not cands:
                if not edge and U_ex.any():
                    edge = True
                    continue
                log(f"{kind}: нет участка нужной площади", [], uncovered=int(len(unc)), short_places=round(short), warn=True)
                hint = "нет участка нужной площади в районе"
                break
            mode = "cover" if len(unc) and max(c["cov_s"] for c in cands) >= 1.0 else ("places" if want_places else None)
            if mode is None:
                if not edge and U_ex.any():
                    edge = True
                    continue
                log(f"{kind}: дома вне радиуса, до которых не дотягивается ни один участок района (группы — в строке «группы домов»)",
                    [], uncovered=int(len(unc)), warn=True)
                break
            if mode == "cover":
                cands.sort(key=lambda c: -c["cov_s"])
                by_v = sorted([c for c in cands[20:] if c["cov_v"] > 0], key=lambda c: -c["cov_v"])[:10]   # village sites too
                best = None
                # the 20 sites that reach most homes by straight line and the 10 best for villages first; when none of them
                # serves on foot, the next ones in batches of SITE_BATCH while a site still reaches homes by straight line
                first = cands[:20] + by_v
                later = [c for c in cands[20:] if c["cov_s"] >= 1.0 and not any(c is v for v in by_v)]
                # (the bonus for a site that holds a larger facility while the district is short of places: the genplan total,
                # not the places short in radius — those size the facility once its site is chosen)
                want = min(need - have, cap_hi) if placed and need - have > 0.5 else 0.0
                for bt in [first] + [later[i:i + SITE_BATCH] for i in range(0, len(later), SITE_BATCH)]:
                    for c in bt:
                        if kind == "fire_station":
                            d_c = np.hypot(U_pts[:, 0] - c["c"].x, U_pts[:, 1] - c["c"].y)
                        else:
                            d_c = cand_dist(c["c"].x, c["c"].y, cut, UP, dn_buf)
                        m = d_c <= U_R
                        c["cov"], c["pl"] = float(U_w[m].sum()), float(U_pl[m].sum())
                        c["vil"] = float(U_w[m & U_vil].sum())
                        c["ex"] = float(U_w[m & U_ex].sum())
                        # while places are short a site that also holds a large facility wins over a slightly better-placed one
                        key = (c["cov"] * (0.5 + 0.5 * min(1.0, c["fit"] / want)) if want else c["cov"], c["fit"] if placed else 0.0)
                        # a facility needs at least the smallest capacity of the norms tables to fill — except in villages,
                        # where the radius decides: a one-group kindergarten or a small school for the village's own children
                        worth = (c["pl"] >= cap_lo or c["vil"] >= 1.0) if placed else c["cov"] >= 1.0
                        if c["edge"] and c["ex"] < 1.0:
                            worth = False       # village-edge land serves the existing homes only
                        if worth and (best is None or key > best[0]):
                            best = (key, c)
                    if best is not None:
                        break
                if best is None:
                    if not want_places:
                        if not edge and U_ex.any():
                            edge = True
                            continue
                        log(f"{kind}: дома вне радиуса: ни один участок района не дотягивается до них по сети или их жителей меньше "
                            f"самого малого объекта таблицы норм (группы — в строке «группы домов»)", [], uncovered=int(len(unc)), warn=True)
                        break
                    mode = "places"
                else:
                    pick = best[1]
            if mode == "places":
                inner = [c for c in cands if not c["edge"]]
                if not inner:
                    log(f"{kind}: нет участка нужной площади", [], uncovered=int(len(unc)), short_places=round(short), warn=True)
                    hint = "нет участка нужной площади в районе"
                    break
                # the site that reaches most of the places short on foot (straight-line reach first, walked in batches)
                from scipy.spatial import cKDTree
                mi = np.flatnonzero(unmet > 0.01)
                M_xy = np.array([[dem[i]["x"], dem[i]["y"]] for i in mi])
                M_u, M_R = unmet[mi], R[mi]
                mk = cKDTree(M_xy)
                for c in inner:
                    ii = np.array(sorted(mk.query_ball_point([c["c"].x, c["c"].y], float(M_R.max()))), dtype=np.int64)
                    c["u_s"] = float(M_u[ii[np.hypot(M_xy[ii, 0] - c["c"].x, M_xy[ii, 1] - c["c"].y) <= M_R[ii]]].sum()) if len(ii) else 0.0
                inner = sorted([c for c in inner if c["u_s"] >= 0.5], key=lambda c: -c["u_s"])
                Pm = sub_points(dem, mi) if len(inner) else None
                best = None
                for k0 in range(0, len(inner), SITE_BATCH):
                    for c in inner[k0:k0 + SITE_BATCH]:
                        d_c = cand_dist(c["c"].x, c["c"].y, float(R.max()) + 1.0, Pm, flow_buf)
                        c["u"] = float(M_u[d_c <= M_R].sum())
                        key = (min(c["u"], cap_hi), min(c["fit"], c["u"]), c["u_s"])
                        if c["u"] >= 0.5 and (best is None or key > best[0]):
                            best = (key, c)
                    if best is not None:
                        break
                if best is None or best[1]["u"] < NEW_SITE_MIN_SHARE * cap_lo:
                    g_ = grow_existing(kind, cap_key, unmet, R, flow_buf, cap_hi)
                    if g_ > 0:
                        n_grow += 1
                        have += g_
                        log(f"{kind}: недостающие в радиусе места отданы объектам рядом, участок которых их вмещает (замечание 79)", [],
                            places=round(g_), short_before=round(short, 1))
                        continue
                if best is None:
                    log(f"{kind}: места в радиусе не хватает, но ни один участок района не достаёт пешком до этих домов в радиусе "
                        f"или не вмещает объект (спрос не размещён)", [f"{dem[i]['x']:.0f},{dem[i]['y']:.0f}" for i in mi[np.argsort(-M_u)][:40]],
                        short_places=round(short, 1), points=int(len(mi)), warn=True)
                    break
                pick = best[1]
                pick["pl"] = 0.0
            rad_pl = rad_net = 0.0
            if placed:
                # a facility seats the demand of every home within its radius of the site (not only the homes no other one
                # reaches: tester items 30, 48, 49, 79 — micro facilities beside full neighbours), up to the typical capacity
                d_all = dists(kind, [(pick["c"].x, pick["c"].y)], dem, float(R.max()) + 1.0, pool_points(dem))
                rad_pl = float(sum(q["res"] * per_res[q["low"]] for q, d_, r_ in zip(dem, d_all, R) if d_ <= r_))
                # less what the facilities already there seat of it (the flow above): a site beside a full-size school is not
                # sized for that school's homes too, and one where the radius is short is sized to all that is short there
                rad_net = float(sum(u_ for u_, d_, r_ in zip(unmet, d_all, R) if d_ <= r_))
                target = max(pick["pl"], min(rad_net, cap_hi))
                cap = soc.choose_cap(kind, max(target, cap_lo), pick["site"].area)
                need_m2, nkey = soc.plot(kind, cap)
            else:
                cap = None
                need_m2, nkey = soc.site_plot(kind, rests[pick["ri"]], split_params_fn, home_m2, m2_res)
            r = rests[pick["ri"]]
            keep_free = None
            if kind in RL_KEY:
                kd = norms.v(RL_KEY[kind], "village" if r["village"] else "city")
                if kd not in kf_cache:
                    kf_cache[kd] = street_rl.buffer(kd)
                keep_free = kf_cache[kd]
            kf_loc = None
            if keep_free is not None and not keep_free.is_empty:
                # the band clipped round the site once: every plot and its building region lie inside the site, so the
                # differences below see the same band without walking the whole district's (w51, green: 35 thousand
                # differences with it, 6 ms each)
                x0_, y0_, x1_, y1_ = pick["site"].bounds
                kf_loc = U.clean(keep_free.intersection(shapely.box(x0_ - KF_WIN_M, y0_ - KF_WIN_M, x1_ + KF_WIN_M, y1_ + KF_WIN_M)))
            fit = building_fit(kind, cap, r, keep_free, kf_loc)
            rank = None
            if mode == "cover":
                def rank(q):
                    """Weight of the uncovered homes the plot q reaches (the site was chosen by its centre; the plot is one end)."""
                    cq = q.centroid
                    if kind == "fire_station":
                        d_q = np.hypot(U_pts[:, 0] - cq.x, U_pts[:, 1] - cq.y)
                    else:
                        d_q = walk.dist_many(UP, walk.dist_from([(cq.x, cq.y)], cut))
                    return round(float(U_w[d_q <= U_R].sum()), 1)
            piece = None
            for grow_ in PLOT_GROW:          # the norm plot first; a larger one when the building does not fit on it
                piece = carve(pick["site"], need_m2 * grow_ * (1.0 + PLOT_MARGIN), arterial if art else None, keep_free, fit, rank,
                              r["b"].get("frame"), kf_loc, fronts if kind != "playground" else None)
                if piece is not None:
                    break
            if piece is not None and rank is not None and rank(piece) < 1.0:
                unusable.add((pick["ri"], kind))       # the plot that fits reaches none of the homes it was placed for
                log(f"{kind}: участок с местом для здания не достаёт до домов вне радиуса — место пропущено", [f"{pick['c'].x:.0f},{pick['c'].y:.0f}"], cap=cap)
                continue
            if piece is None:
                unusable.add((pick["ri"], kind))       # no end of this site holds the plot and its building: try the next site
                log(f"{kind}: участок не вмещает здание с отступами — место пропущено", [f"{pick['c'].x:.0f},{pick['c'].y:.0f}"], cap=cap)
                continue
            r["poly"] = U.clean(r["poly"].difference(piece.buffer(0.01)))
            r["_pieces"] = None
            capd = {}
            if kind in ("school", "kindergarten"):
                capd["places"] = int(cap)
            elif kind == "polyclinic":
                capd["visits_per_shift"] = int(cap)
            label = LABEL[kind] + (" села на свободной земле (модель qTwin)" if r["village"] else "")
            if pick["edge"]:
                label = LABEL[kind] + " у края села на резервной земле: дома села не достают ни до одного другого участка (модель qTwin)"
            add_lot(r["b"], kind, piece, "rule", capacity=capd, norm_key=nkey, plot_norm_m2=round(need_m2), label_ru=label)
            have += cap or 0
            n_new += 1
            log(f"соцучасток: {kind}", [], mode=mode, cap=cap, plot_m2=round(piece.area), plot_norm_m2=round(need_m2),
                uncovered_before=int(len(unc)), short_before=round(short), at=[round(piece.centroid.x), round(piece.centroid.y)],
                **({"demand_in_radius": round(rad_pl, 1), "unserved_in_radius": round(rad_net, 1)} if placed else {}),
                **({"edge": True} if pick["edge"] else {}))
            if placed and cap < soc.typical_min(kind):
                small_soc.append({"kind": kind, "at": [round(piece.centroid.x), round(piece.centroid.y)], "cap": int(cap),
                                  "demand_in_radius": round(rad_pl, 1), "unserved_in_radius": round(rad_net, 1),
                                  "typical_from": soc.typical_min(kind),
                                  "why": "земля: свободный участок в радиусе меньше" if cap + 0.5 < target else "спрос"})
            last_pick = (pick["ri"], short) if placed else None
            dem = demand()
            need = sum(q["res"] * per_res[q["low"]] for q in dem)
        if len(unc):
            gr = why_groups(kind, list(unc), R, placed, cap_lo, art, unusable, hint)
            log(f"{kind}: группы домов вне радиуса, которым не нашлось участка: где они и почему", [f"{g_['at'][0]},{g_['at'][1]}" for g_ in gr][:40],
                groups=gr[:40], n_groups=len(gr), reasons=dict(Counter(g_["reason"] for g_ in gr)),
                existing_lots=sum(g_["existing_lots"] for g_ in gr), uncovered=int(len(unc)), sites=n_new, stop=stop, warn=True)
        if kind == "kindergarten":
            g = norms.v("kindergartens.group_size_max", "3-7_years")
            Rm = soc.radius(kind, False)
            Pd = pool_points(dem)
            dd = dists(kind, providers(kind), dem, Rm + 1.0, Pd)
            while True:
                unc_m = [i for i, q in enumerate(dem) if q["w"] > 0 and not q["low"] and dd[i] > Rm]
                if not unc_m:
                    break
                i = max(unc_m, key=lambda i: dem[i]["res"])
                builtin_hosts.append((dem[i]["x"], dem[i]["y"]))
                dd = np.minimum(dd, dists(kind, [builtin_hosts[-1]], dem, Rm + 1.0, Pd))
                dd[i] = 0.0
            if builtin_hosts:
                log("kindergarten: встроенные детсады на одну группу в многоэтажных домах, до которых не дотянулся отдельный сад "
                    "(kindergartens.placement)", [f"{x:.0f},{y:.0f}" for x, y in builtin_hosts], n=len(builtin_hosts), group=g)
        ex = [i for i, q in enumerate(dem) if q["ri"] is None]
        if ex:
            pool = [dem[i] for i in ex]
            dd = dists(kind, providers(kind), pool, float(radii(kind, pool).max()) + 1.0)
            far = [dem[i] for i, d_ in zip(ex, dd) if d_ > soc.radius(kind, True, dem[i]["vil"])]
            if far:
                log(f"{kind}: существующие дома вне радиуса после размещения",
                    [f"{q['x']:.0f},{q['y']:.0f}" for q in far][:40], uncovered=len(far), of=len(ex), warn=True)
        if placed:
            dem_pl = np.array([q["res"] * per_res[q["low"]] for q in dem])
            prov_dists(kind, providers(kind), dem, float(radii(kind, dem).max()) + 1.0)
            left = float(flow_unmet(kind, cap_key, dem_pl, radii(kind, dem), np.empty(walk.G.number_of_nodes() + 1)).sum())
            log(f"{kind}: места против числа генплана и недостающие в радиусе (поток правила 14)", [], need=round(need), have=round(have),
                share=round(have / need, 2) if need else None, short_in_radius=round(left, 1), sites=n_new)
        sm = [q for q in small_soc if q["kind"] == kind]
        if sm:
            log(f"{kind}: объекты меньше типовой вместимости — спрос домов в радиусе участка, которым не хватает мест соседних "
                "объектов, так мал (why «спрос»: вместимость = этот спрос, не меньше наименьшей по нормам), или свободной земли "
                "в радиусе меньше участка на него (why «земля»)", [f"{q['at'][0]},{q['at'][1]}" for q in sm], objects=sm, n=len(sm))
    return builtin_hosts


def chunky(p, need_m2):
    """A plot is usable when a square of half the side of a square plot of need_m2 fits inside (no thin strips)."""
    return p is not None and not U.clean(p.buffer(-0.25 * math.sqrt(need_m2))).is_empty


PLOT_GROW = (1.0, 1.3, 1.7, 2.2)   # plot sizes tried (× the norm plot) until the building fits with its setbacks: model parameter
ART_TOL_M = 0.5                     # school and kindergarten plots keep this much over the arterial setback: the buffer's chords
#                                     cut its circles short (a plot at 49.98 m of the 50, rule 13) — m, модель qTwin
PLOT_MARGIN = 0.02                  # a social plot is cut this share over its norm plot: the hair-line and needle cuts of the lot
#                                     shaping take up to ~1 % off it later (tester item 29: 3576 of 3600 m²) — модель qTwin
GRADE_KEEP_MAX = 20000              # pieces whose grade split_to_grade keeps for its next level (memory; a pure speed-up)
KF_WIN_M = 1.0                      # m: margin of the window round a site its keep_free band is clipped to (a pure speed-up)
RING_ONLY = False                   # a new social plot need not hold the fire ring inside it (the drives ring the building):
#                                     True left 25 of 196 Gate kindergarten sites (25 m from the red line + an 11 m ring)


def carve(site, need_m2, avoid=None, keep_free=None, fit=None, rank=None, frame=None, kf_loc=None, front=None):
    """A piece of need_m2 cut from one end of the site (either axis, square to the block's frame when given): usable shape
    whose building fits (`fit`, the placer of gen_buildings), then the end that serves most (`rank`, when given), then the end
    with more land outside `keep_free` (building setback from red lines), then the end farther from `avoid`. None if no end
    gives such a plot. kf_loc: keep_free clipped round the site (the same land outside it inside the site). front: the plot
    must have a street to enter from (front(q) true)."""
    def body(g):
        """The largest part of g once hair-line bridges are opened (the shape pass would cut the plot there later)."""
        return max(U.polys(opening(g, HAIRLINE_LOT), 1.0), key=lambda x: x.area, default=None)
    if site.area <= need_m2 * 1.3:
        # the whole site, as one piece of at least the norm plot (a site in parts round other plots gave a social lot
        # under the norm plus a sliver without capacity, rule 13)
        q = body(site)
        return q if q is not None and q.area >= need_m2 - 1.0 and chunky(q, need_m2) and (front is None or front(q)) \
            and (fit is None or fit(q)) else None
    ang = U.axis(site)[0] if frame is None else frame
    opts = []
    for a in (ang, ang + math.pi / 2):
        for low in (True, False):
            q, _ = U.cut_at_area(site, a, need_m2, low)
            q = body(q)
            if q is not None and q.area >= 0.995 * need_m2 and chunky(q, need_m2) and (front is None or front(q)) \
                    and (fit is None or fit(q)):      # rule 13 tolerance
                opts.append(q)
    if not opts:
        return None

    def score(q):
        if keep_free is not None and not keep_free.is_empty:
            kf_ = keep_free if kf_loc is None else kf_loc
            free = q.difference(kf_).area if not kf_.is_empty else q.area
        else:
            free = 0.0
        far = q.distance(avoid) if avoid is not None and not avoid.is_empty else 0.0
        return (rank(q) if rank is not None else 0.0, round(free), far, q.area)
    return max(opts, key=score)


if __name__ == "__main__":
    a = U.cli(__doc__).parse_args()
    run(a.district, a.out, a.spec)
