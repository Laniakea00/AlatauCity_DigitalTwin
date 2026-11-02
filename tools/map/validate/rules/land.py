"""Rules 1–4 (w44): one land, one purpose. Interface: CONTRACT §5 (RULES list, check(ctx) -> [issue])."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import land_rulekit as K  # noqa: E402
import land_util as U  # noqa: E402


def _occupancy(ctx):
    """[(kind, id, polygon, level, years)] of everything that takes land (CONTRACT: levels −1, 0, +1)."""
    occ = []
    for s, p, lv in K.road_polys(ctx, "walk"):
        occ.append(("road", s["id"], p, lv, s["years"]))
    for s, p in K.drive_polys(ctx, "carriage"):          # driveways and turnaround pads take land inside the lots
        occ.append(("drive", s["id"], p, 0, s["years"]))
    for b in K.buildings(ctx):
        occ.append(("building", b["id"], b["_p"], 0, b["years"]))
    f = ctx.features or {}
    for p_ in f.get("parking", []):
        occ.append(("parking", p_["id"], K.poly(p_["polygon"]), -1 if p_["type"] == "underground" else 0, p_["years"]))
    w_lrt = K.nv(ctx, "lrt.corridor_width_m", "double_track")
    for Ln in (ctx.lrt or {}).get("lines", []):
        ls = LineString([(q[0], q[1]) for q in Ln["pts"]])
        for sec in Ln.get("sections", []):
            if sec["kind"] == "ground" and sec["to_m"] - sec["from_m"] > 1:
                part = shapely.ops.substring(ls, max(0, sec["from_m"]), min(ls.length, sec["to_m"]))
                occ.append(("lrt", Ln["id"], part.buffer(w_lrt / 2, cap_style="flat"), 0, Ln.get("years") or U.EXISTING_YEARS))
    return occ


ALLOWED = {("road", "road"), ("parking", "road"),    # roads meet at junctions; a driveway into a lot crosses the sidewalk
           ("drive", "road"), ("drive", "drive")}     # a driveway is a T on its street; drives meet each other and their pads


def check_1(ctx):
    m = K.missing(ctx, 1, "network", "buildings", "features")
    if m:
        return m
    tol = K.nv(ctx, "validator.occupancy_overlap_max_m2")
    occ = _occupancy(ctx)
    out = []
    tree = shapely.STRtree([o[2] for o in occ])
    nodes = [Point(n["x"], n["z"]) for n in (ctx.network or {}).get("nodes", [])]
    ntree = shapely.STRtree(nodes) if nodes else None
    seen = set()
    keeps = U.keep_polys(ctx.spec)
    keep_u = unary_union([p for _, p in keeps]) if keeps else None
    seg_cls = {s["id"]: s["class"] for s in (ctx.network or {}).get("segments", [])}
    for i, (k1, id1, p1, lv1, y1) in enumerate(occ):
        for j in tree.query(p1, predicate="intersects"):
            j = int(j)
            if j <= i:
                continue
            k2, id2, p2, lv2, y2 = occ[j]
            if lv1 != lv2 or tuple(sorted((k1, k2))) in ALLOWED or (k1 == k2 == "lrt"):
                continue
            # both must stand in the same year at some stage (base scenario)
            if max(y1[0], y2[0]) > 2050:
                continue
            a = p1.intersection(p2).area
            if a <= tol:
                continue
            if {k1, k2} == {"road", "building"} and keep_u is not None and (p1 if k1 == "building" else p2).centroid.within(keep_u):
                continue           # streets may enter a keep polygon up to their attach point (the keep's own layout)
            if {k1, k2} == {"lrt", "road"} and not ctx.N.lrt_crossing_allowed(seg_cls.get(id1 if k1 == "road" else id2)):
                continue           # a road the LRT may not cross at grade: rule 6 reports the crossing
            if {k1, k2} == {"lrt", "road"} and ntree is not None:
                q = p1.intersection(p2)
                if len(ntree.query(q.buffer(30.0), predicate="intersects")):
                    continue       # level crossing at a node (traffic light): allowed by the rule
            key = (min(id1, id2), max(id1, id2))
            if key in seen:
                continue
            seen.add(key)
            c = p1.intersection(p2).representative_point()
            # two existing objects (2025 in every scenario: OSM roads, Overture / twin houses) overlap as the source data do:
            # nothing on the map put them there
            both_old = list(y1) == list(U.EXISTING_YEARS) and list(y2) == list(U.EXISTING_YEARS)
            out.append(K.issue(ctx, 1, c.x, c.y, f"{k1} {id1} и {k2} {id2} на одной земле (уровень {lv1}): {a:.0f} м²"
                               + (" — оба существующие, как в исходных данных" if both_old else ""), [id1, id2], lv=lv1,
                               sev="warning" if both_old else None))
    # lots overlap each other
    L = K.lots(ctx)
    lt = shapely.STRtree([l["_p"] for l in L])
    for i, l in enumerate(L):
        for j in lt.query(l["_p"], predicate="intersects"):
            j = int(j)
            if j <= i:
                continue
            a = l["_p"].intersection(L[j]["_p"]).area
            if a > tol:
                c = l["_p"].intersection(L[j]["_p"]).representative_point()
                out.append(K.issue(ctx, 1, c.x, c.y, f"участки {l['id']} и {L[j]['id']} перекрываются на {a:.0f} м²", [l["id"], L[j]["id"]]))
    return out


def check_2(ctx):
    m = K.missing(ctx, 2, "lots", "network")
    if m:
        return m
    tol = K.nv(ctx, "validator.occupancy_overlap_max_m2")
    parts = [l["_p"] for l in K.lots(ctx)] + [p for _, p, _ in K.road_polys(ctx, "red")]
    if getattr(ctx, "water", None) is not None and not ctx.water.is_empty:
        parts.append(ctx.water)
    w_lrt = K.nv(ctx, "lrt.corridor_width_m", "double_track")
    for Ln in (ctx.lrt or {}).get("lines", []):
        parts.append(LineString([(q[0], q[1]) for q in Ln["pts"]]).buffer(w_lrt / 2, cap_style="flat"))
    for c in U.corridors(ctx.spec):
        parts.append(LineString(c["line"]).buffer(max(1.0, c.get("width_m") or 1.0)))
    covered = unary_union(parts)
    left = U.clean(ctx.area.difference(covered))
    out = []
    for q in U.polys(left, tol):
        if q.buffer(-0.5).is_empty:           # a hair-line between two contours, not land
            continue
        c = q.representative_point()
        out.append(K.issue(ctx, 2, c.x, c.y, f"безымянная земля {q.area:.0f} м² (нет ни участка, ни улицы, ни воды, ни коридора)", []))
    for l in K.lots(ctx):
        if l["use"] == "reserve" and not l.get("label_ru"):
            c = l["_p"].representative_point()
            out.append(K.issue(ctx, 2, c.x, c.y, f"резерв {l['id']} без подписи", [l["id"]]))
    return out


def check_3(ctx):
    m = K.missing(ctx, 3, "lots", "buildings")
    if m:
        return m
    g = K.nv(ctx, "validator.grading")
    cut, base_d, slope_pct = g["cut_fill_max_m"], g["building_base_max_diff_m"], g["plinth_or_terrace_if_slope_over_pct"]
    out = []
    lot = K.lot_by_id(ctx)
    for l in K.lots(ctx):
        if l["source"] in ("existing", "keep") or l.get("natural") or l.get("nobuild"):
            continue          # land left at its terrain: nothing is graded there
        gy, dev = U.grade(l["_p"])
        if l.get("terraces"):
            worst = max(abs(t["cut_fill_m"]) for t in l["terraces"])
            if worst > cut:
                c = l["_p"].representative_point()
                out.append(K.issue(ctx, 3, c.x, c.y, f"терраса участка {l['id']}: срезка/подсыпка {worst:.1f} м > {cut} м", [l["id"]]))
            continue
        if abs(gy - l["grade_y"]) + dev > cut + 1e-6:
            c = l["_p"].representative_point()
            out.append(K.issue(ctx, 3, c.x, c.y, f"участок {l['id']}: срезка/подсыпка до {abs(gy - l['grade_y']) + dev:.1f} м > {cut} м", [l["id"]]))
    for b in K.buildings(ctx):
        if b["source"] == "existing_osm" or not b.get("lot"):
            continue
        l = lot.get(b["lot"])
        if l is None:
            continue
        ref = l["grade_y"]
        if l.get("terraces"):
            cc = b["_p"].centroid
            ref = min(zip(l["terraces"], _terrace_polys(ctx, l)), key=lambda tp: tp[1].distance(cc))[0]["grade_y"]
        if abs(b["base_y"] - ref) > base_d:
            c = b["_p"].centroid
            out.append(K.issue(ctx, 3, c.x, c.y, f"здание {b['id']}: низ {b['base_y']:.2f} м против планировки {ref:.2f} м (> {base_d} м)", [b["id"]]))
        pts = U.poly_samples(b["_p"], 10.0, 200)
        if len(pts) >= 2:
            hs = np.asarray(ctx.h(pts[:, 0], pts[:, 1]), float)       # one call for all points (the same heights)
            span = max(1.0, max(b["_p"].bounds[2] - b["_p"].bounds[0], b["_p"].bounds[3] - b["_p"].bounds[1]))
            if (hs.max() - hs.min()) / span * 100 > slope_pct and not l.get("terraces") and not b.get("plinth"):
                c = b["_p"].centroid
                out.append(K.issue(ctx, 3, c.x, c.y, f"здание {b['id']} на уклоне > {slope_pct} % без цоколя или террасы", [b["id"]], sev="warning"))
        # the ground under the footprint (as merge draws the walls: down to the lowest terrain under it) falls more than the
        # grading limit: without a `plinth` the walls stand on a raw slope (terraced lot or not)
        if not b.get("plinth") and not b.get("keep"):
            lo, hi = _relief(ctx, b["_p"])
            if hi - lo > cut + 1e-6:
                c = b["_p"].centroid
                out.append(K.issue(ctx, 3, c.x, c.y, f"здание {b['id']}: земля под ним падает на {hi - lo:.1f} м (> {cut} м) — нет цоколя (plinth)", [b["id"]]))
    return out


RELIEF_STEP_M = 4.0         # as merge's footprint_relief: vertices, edges every 4 m and a 4 m grid inside (sampling, not a norm)


def _terrace_polys(ctx, l):
    """Polygons of a lot's terraces, built once per lot (rule 3 asks per building)."""
    c = K.cache(ctx).setdefault("terrace_polys", {})
    if l["id"] not in c:
        c[l["id"]] = [K.poly(t["polygon"]) for t in l["terraces"]]
    return c[l["id"]]


def _relief(ctx, P):
    """(lowest, highest) terrain under a footprint polygon, sampled as merge samples it."""
    pts = []
    for g in getattr(P, "geoms", [P]):
        for ring in [g.exterior] + list(g.interiors):
            L = LineString(ring.coords)
            pts += [tuple(q) for q in shapely.get_coordinates(shapely.line_interpolate_point(L, np.arange(0.0, L.length, RELIEF_STEP_M)))]
    x0, z0, x1, z1 = P.bounds
    gx, gz = np.meshgrid(np.arange(x0 + RELIEF_STEP_M / 2, x1, RELIEF_STEP_M), np.arange(z0 + RELIEF_STEP_M / 2, z1, RELIEF_STEP_M))
    gx, gz = gx.ravel(), gz.ravel()
    if len(gx):
        m = shapely.contains_xy(P, gx, gz)
        pts += list(zip(gx[m], gz[m]))
    a = np.array(pts, float)
    h = np.asarray(ctx.h(a[:, 0], a[:, 1]), float)
    return float(np.min(h)), float(np.max(h))


def check_4(ctx):
    m = K.missing(ctx, 4, "buildings", "network")
    if m:
        return m
    out = []
    strip_w = K.nv(ctx, "flood.water_protection_strip_min_m")
    water = ctx.water if getattr(ctx, "water", None) is not None else U.Polygon()
    strip = water.buffer(strip_w) if not water.is_empty else U.Polygon()
    flood = getattr(ctx, "flood_485", None)
    flood = flood if flood is not None else U.Polygon()
    for g in (water, strip, flood):
        shapely.prepare(g)              # many small footprints against a few large polygons: prepared predicates (g first)
    exc = set(K.nv(ctx, "validator.water_building_exceptions"))
    B = K.buildings(ctx)
    btree = shapely.STRtree([b["_p"] for b in B])
    seg_l = [(s, U.seg_line(s)) for s in (ctx.network or {}).get("segments", [])]
    stree = shapely.STRtree([sl for _, sl in seg_l]) if seg_l else None
    for b in B:
        if b.get("kind") in exc or b["source"] == "existing_osm":
            continue
        p = b["_p"]
        for g, why in ((water, "в воде"), (strip, f"в водоохранной полосе {strip_w} м"), (flood, "ниже паводка (НПУ + запас)")):
            if not g.is_empty and g.intersects(p) and p.intersection(g).area > 1.0:
                c = p.centroid
                out.append(K.issue(ctx, 4, c.x, c.y, f"здание {b['id']} {why}", [b["id"]]))
                break
    # roads in water: only as a bridge / dam
    for s, p, lv in K.road_polys(ctx, "carriage"):
        if lv > 0 or water.is_empty:
            continue
        if water.intersects(p) and p.intersection(water).area > 1.0:
            c = p.intersection(water).representative_point()
            # an existing road (2025, from OSM) is checked against its source, not redesigned: a warning, as for houses
            ex = _existing_road(s)
            out.append(K.issue(ctx, 4, c.x, c.y, f"{_road_ru(ex)} {s['id']} в воде не мостом{_as_osm(ex)}", [s["id"]],
                               sev="warning" if ex else None))
    # protected zones of power lines / gas pipes
    w_cable = K.nv(ctx, "utilities.to_foundations_m", "cables")
    for c_ in U.corridors(ctx.spec):
        if c_.get("state") == "cable":
            # a cable (e.g. the 220 kV line put underground): its strip instead of the overhead corridor it replaces
            strip = LineString(c_["line"]).buffer(w_cable)
            for j in sorted(btree.query(strip, predicate="intersects")):     # building order, as a loop over all
                b = B[int(j)]
                c = b["_p"].centroid
                ex = b["source"] == "existing_osm"
                out.append(K.issue(ctx, 4, c.x, c.y, f"{'существующий дом' if ex else 'здание'} {b['id']} на кабеле {c_['id']} "
                                   f"(ближе {w_cable} м к фундаменту){': трасса кабеля через дом' if ex else ''}",
                                   [b["id"], c_["id"]], sev="warning" if ex else None))
            continue
        key = {"power_line": "utilities.power_line_protection_zone_m", "gas": "utilities.gas_pipeline_protection_zone_m"}.get(c_["kind"])
        if c_["kind"] == "power_line":
            # RK rules of protected zones of electric networks (utilities.power_line_protection_zone_m, by voltage)
            w, kv, assumed = U.power_zone_m(K.norms(ctx), c_)
        else:
            w, kv, assumed = c_.get("width_m") or (K.nv(ctx, key) if key else None), None, False
        ln = LineString(c_["line"])
        zone = ln.buffer(w if w else 1.0)
        sev = None if w else "warning"
        why = (f" ({w:.0f} м от оси, ВЛ {kv:g} кВ{' — напряжение не задано, взят наименьший класс' if assumed else ''})" if w and kv else "") if w else \
            " (ширина охранной зоны не задана: norms not_verified, проверена ось ± 1 м)"
        for j in sorted(btree.query(zone, predicate="intersects")):
            b = B[int(j)]
            if b["_p"].intersection(zone).area > K.nv(ctx, "validator.occupancy_overlap_max_m2"):
                c = b["_p"].centroid
                ex = b["source"] == "existing_osm" or b.get("keep")
                # a real house the line already crosses stays as its source draws it: a warning, not the design's error
                out.append(K.issue(ctx, 4, c.x, c.y, f"{'существующий дом' if ex else 'здание'} {b['id']} в охранной зоне {c_['id']}{why}",
                                   [b["id"], c_["id"]], sev="warning" if ex else sev))
        if not w:
            c = ln.interpolate(0.5, normalized=True)
            out.append(K.issue(ctx, 4, c.x, c.y, f"{c_['id']}: ширина охранной зоны не задана (norms.json not_verified)", [c_["id"]], sev="warning"))
        elif assumed:
            c = ln.interpolate(0.5, normalized=True)
            out.append(K.issue(ctx, 4, c.x, c.y, f"{c_['id']}: напряжение ВЛ не задано (OSM без voltage), охранная зона {w:.0f} м по наименьшему классу "
                               f"{kv:g} кВ; задайте kv в спецификации", [c_["id"]], sev="warning"))
        for j in (sorted(stree.query(zone, predicate="intersects")) if stree is not None else []):
            s, sl = seg_l[int(j)]
            inside = sl.intersection(zone).length
            if inside > 4 * 2 * (w or 1.0):     # longer inside than a crossing at ~15° to the line: runs along it
                c = sl.intersection(zone).representative_point()
                ex = _existing_road(s)
                out.append(K.issue(ctx, 4, c.x, c.y, f"{_road_ru(ex)} {s['id']} идёт вдоль коридора {c_['id']} "
                                   f"внутри охранной зоны{_as_osm(ex)}", [s["id"], c_["id"]],
                                   sev="warning" if ex else sev))
    return out


def _existing_road(s):
    """A road that stands already in 2025 (OSM / Overture, kept as its source draws it)."""
    return int((s.get("years") or [9999])[0]) <= U.EXISTING_YEARS[0]


def _road_ru(existing):
    return "существующая дорога" if existing else "дорога"


def _as_osm(existing):
    return " (как в OSM)" if existing else ""


RULES = [
    {"no": 1, "key": "occupancy", "fn": check_1, "needs": ["network", "buildings", "features", "lots"]},
    {"no": 2, "key": "nameless_land", "fn": check_2, "needs": ["lots", "network"]},
    {"no": 3, "key": "grading", "fn": check_3, "needs": ["lots", "buildings"]},
    {"no": 4, "key": "water_flood_corridors", "fn": check_4, "needs": ["buildings", "network"]},
]
