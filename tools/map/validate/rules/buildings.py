"""Rules 12–18 (w44): access, social plots, services (rule 14 as a service table per residential block), sanitary gaps,
heights, parking in centres and view sectors, identical models and the size of one warehouse. Interface: CONTRACT §5."""
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import Point  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import land_models as LM  # noqa: E402
import land_rulekit as K  # noqa: E402
import land_util as U  # noqa: E402



BAND_TOL = 0.05     # metres: rounding of the drawn carriageway edges when a distance band is checked (a model parameter)


def _over_m(key_name):
    m = re.search(r"over_(\d+)m", key_name)
    return float(m.group(1)) if m else None


def _range_m(key_name):
    """(10.0, 28.0) from «building_10_28m»; None for a key without a height range."""
    m = re.search(r"(\d+)_(\d+)m", key_name)
    return (float(m.group(1)), float(m.group(2))) if m else None


# ------------------------------------------------------------------------------------------------------------ rule 12
def check_12(ctx):
    """Every building reached by a carriageway (street or driveway of ctx.driveways), measured from the footprints and the
    carriageway polygons alone (driveways.json's own list of unserved buildings is not read): within the building-line
    limit; 10–28 m high and with no street carriageway within that limit, some drive with its edge in the 5–8 m band of
    fire_access.distance_to_wall_m; over 28 m some carriageway in the 8–10 m band, and two such buildings at least two near
    band edges and a fire lane apart (fire_access.width_min_m: 2 × 8 + 6 = 22 m); ring access all round where
    fire_access.ring_required asks; dead ends with a turnaround and not longer than fire_access.dead_end_max_m; every drive
    tied to a street; every block entered from a street."""
    m = K.missing(ctx, 12, "buildings", "network", "lots")
    if m:
        return m
    out = []
    lim = K.nv(ctx, "setbacks.building_line_max_m", "max_from_carriageway")
    dw = K.nv(ctx, "fire_access.distance_to_wall_m")
    hi_key = next(k for k in dw if _over_m(k))
    hi_h, hi_min, hi_max = _over_m(hi_key), dw[hi_key]["min"], dw[hi_key]["max"]
    mid_key = next((k for k in dw if k != hi_key and isinstance(dw[k], dict) and _range_m(k)), None)
    mid_h = _range_m(mid_key) if mid_key else None
    mid_min, mid_max = (dw[mid_key]["min"], dw[mid_key]["max"]) if mid_key else (None, None)
    lane_w = K.nv(ctx, "fire_access.width_min_m", "default")
    dead_max = K.nv(ctx, "fire_access.dead_end_max_m")
    turn = K.nv(ctx, "fire_access.turnaround_min_m")
    dv = K.driveways(ctx)
    if dv is None:
        c = ctx.area.representative_point()
        out.append(K.issue(ctx, 12, c.x, c.y, "нет файла driveways.json: проезды внутри кварталов не проверены, только улицы", [], sev="warning"))
    car_s = [(s, p) for s, p, lv in K.road_polys(ctx, "carriage") if s["class"] in U.DRIVABLE and s["class"] not in U.NO_ACCESS and lv == 0]
    n_street = len(car_s)
    car_s += K.drive_polys(ctx, "carriage")
    car = [p for _, p in car_s]
    st_tree = shapely.STRtree(car[:n_street]) if n_street else None
    dr_tree = shapely.STRtree(car[n_street:]) if len(car) > n_street else None
    if not car:
        return out + [K.issue(ctx, 12, ctx.area.representative_point().x, ctx.area.representative_point().y, "нет проезжих частей", [])]
    tree = shapely.STRtree(car)
    red = _red_by_id(ctx)
    segs = K.segs(ctx)
    # the red lines of the drivable streets in a tree: a plot touches one when some red line is nearer than 2 m (the
    # distance to their union, without building the union of a whole district)
    red_drv = [red[sid] for sid, s in segs.items() if s["class"] in U.DRIVABLE and s["class"] not in U.NO_ACCESS and sid in red]
    red_tree = shapely.STRtree(red_drv) if red_drv else None

    def on_street(lp):
        return red_tree is not None and any(red_drv[int(j)].distance(lp) < 2.0 for j in red_tree.query(lp, predicate="dwithin", distance=2.0))
    N = K.norms(ctx)
    lbi = K.lot_by_id(ctx)
    for b in K.buildings(ctx):
        p = b["_p"]
        d = car[int(tree.nearest(p))].distance(p)
        c = p.centroid
        lot = lbi.get(b.get("lot"))
        if b["source"] == "existing_osm" or b.get("keep"):
            # existing houses: served while their plot touches a drivable street (village lanes, the old roads)
            if d > lim and not (lot and on_street(lot["_p"])):
                sev = "wait_neighbour" if p.distance(ctx.area.exterior) < lim else "warning"
                out.append(K.issue(ctx, 12, c.x, c.y, f"существующий дом {b['id']}: проезжая часть в {d:.0f} м, участок не выходит на улицу",
                                   [b["id"]], sev=sev))
            continue
        tall = b["height_m"] > hi_h
        dmax = hi_max if tall else lim
        if d > dmax:
            sev = "wait_neighbour" if p.distance(ctx.area.exterior) < lim else None
            what = (f"здание {b['id']} выше {hi_h:.0f} м: проезд в {d:.0f} м от стены (норма ≤ {hi_max} м)" if tall else
                    f"здание {b['id']}: до проезжей части {d:.0f} м > {lim} м (ни улицы, ни проезда)")
            out.append(K.issue(ctx, 12, c.x, c.y, what, [b["id"]], sev=sev))
            continue
        # the same in the year the building opens (base scenario): a street or drive within reach must stand by then
        y0 = b["years"][0]
        reach = [int(i) for i in tree.query(p, predicate="dwithin", distance=dmax)]
        if not any((car_s[i][0].get("years") or [0])[0] <= y0 for i in reach):
            i1 = min(reach, key=lambda i: (car_s[i][0].get("years") or [0])[0])
            sev = "wait_neighbour" if p.distance(ctx.area.exterior) < lim else None
            out.append(K.issue(ctx, 12, c.x, c.y, f"здание {b['id']} ({y0}): в год открытия ни улицы, ни проезда в {dmax:.0f} м — "
                               f"ближайшая в этом радиусе {car_s[i1][0]['id']} с {car_s[i1][0]['years'][0]}", [b["id"], car_s[i1][0]["id"]],
                               sev=sev))
        if tall:
            # the fire lane of a tall building: some carriageway (a street, a drive or its pad) with its edge in the band
            # hi_min..hi_max of the wall; one nearer only does not do (fire_access.distance_to_wall_m)
            near = sorted((car[int(i)].distance(p), car_s[int(i)][0]["id"]) for i in tree.query(p, predicate="dwithin", distance=hi_max + BAND_TOL))
            if not any(hi_min - BAND_TOL <= x <= hi_max + BAND_TOL for x, _ in near):
                sev = "wait_neighbour" if p.distance(ctx.area.exterior) < lim else None
                out.append(K.issue(ctx, 12, c.x, c.y, f"здание {b['id']} выше {hi_h:.0f} м без пожарного проезда: нет проезжей части в {hi_min}–{hi_max} м "
                                   f"от стены, ближайшая {near[0][1]} в {near[0][0]:.1f} м (ближе нормы)", [b["id"], near[0][1]], sev=sev))
                continue
        elif mid_h and mid_h[0] <= b["height_m"] <= mid_h[1]:
            # 10–28 m: a street carriageway within the building-line limit serves the building on its own; else its fire
            # drive must come to the wall with its edge in the band mid_min..mid_max (a nearer drive only does not do)
            d_st = car[int(st_tree.nearest(p))].distance(p) if st_tree is not None else math.inf
            if d_st > lim:
                near = sorted((car[n_street + int(i)].distance(p), car_s[n_street + int(i)][0]["id"]) for i in
                              dr_tree.query(p, predicate="dwithin", distance=lim)) if dr_tree is not None else []
                if not any(mid_min - BAND_TOL <= x <= mid_max + BAND_TOL for x, _ in near):
                    sev = "wait_neighbour" if p.distance(ctx.area.exterior) < lim else None
                    x0, i0 = near[0] if near else (d, car_s[int(tree.nearest(p))][0]["id"])
                    how = "ближе нормы" if x0 < mid_min - BAND_TOL else "дальше нормы"
                    out.append(K.issue(ctx, 12, c.x, c.y, f"здание {b['id']} {b['height_m']:.0f} м: улицы в {lim:.0f} м нет, проезд {i0} в {x0:.1f} м "
                                       f"от стены ({how}: {mid_min}–{mid_max} м, fire_access.distance_to_wall_m {mid_key})",
                                       [b["id"], i0], sev=sev))
        if lot and U.ring_required(N, lot["use"], b["use"], b["height_m"]):
            ring = p.exterior
            k = max(8, int(ring.length / 4.0))
            wp = shapely.line_interpolate_point(ring, np.arange(k) * ring.length / k)
            # a wall point is far when no carriageway lies within dmax + 1 m (the distance to their union)
            far = np.ones(len(wp), bool)
            far[np.unique(tree.query(wp, predicate="dwithin", distance=dmax + 1.0)[0])] = False
            if far.mean() > 0.0:
                q = wp[int(np.flatnonzero(far)[0])]
                out.append(K.issue(ctx, 12, q.x, q.y, f"здание {b['id']}: кольцевой пожарный проезд нужен (fire_access.ring_required), "
                                   f"{far.mean() * 100:.0f}% периметра дальше {dmax:.0f} м от проезда", [b["id"]]))
    out += _tall_gaps(ctx, hi_h, 2 * hi_min + lane_w, f"2 × {hi_min:g} м + {lane_w:g} м")
    # driveways: tied to streets, dead ends with turnarounds
    if dv is not None and dv.get("segments"):
        import networkx as nx
        G = nx.MultiGraph()
        for s in dv["segments"]:
            G.add_edge(s["a"], s["b"], s=s)
        nodes = {n["id"]: n for n in dv.get("nodes", [])}
        pads = {pd["node"]: K.poly(pd["polygon"]) for pd in dv.get("pads", [])}
        for n in nodes.values():
            a = n.get("attach")
            if a and a.get("segment") not in segs:
                out.append(K.issue(ctx, 12, n["x"], n["z"], f"проезд {n['id']} примыкает к отрезку {a.get('segment')}, которого нет в сети", [n["id"]]))
        for comp in nx.connected_components(G):
            if not any(nodes.get(x, {}).get("attach") for x in comp):
                n = nodes[next(iter(comp))]
                out.append(K.issue(ctx, 12, n["x"], n["z"], f"проезд у узла {n['id']} не связан с улицей", sorted(comp)[:5]))
        tw, tl = sorted(turn)
        for x in G.nodes:
            n = nodes.get(x)
            if n is None or G.degree(x) != 1 or n.get("attach"):
                continue
            (_, _, dd), = G.edges(x, data=True)
            L = U.seg_line(dd["s"]).length
            pad = pads.get(x)
            if pad is None:
                out.append(K.issue(ctx, 12, n["x"], n["z"], f"тупик проезда {n['id']} ({L:.0f} м) без разворотной площадки {tw:.0f}×{tl:.0f} м",
                                   [n["id"], dd["s"]["id"]]))
            else:
                r = pad.minimum_rotated_rectangle
                e = sorted({round(math.dist(r.exterior.coords[i], r.exterior.coords[i + 1]), 1) for i in range(2)})
                if e[0] < tw - 0.1 or e[-1] < tl - 0.1:
                    out.append(K.issue(ctx, 12, n["x"], n["z"], f"разворотная площадка у {n['id']} {e[0]:.0f}×{e[-1]:.0f} м < {tw:.0f}×{tl:.0f} м", [n["id"]]))
            if L > dead_max:
                out.append(K.issue(ctx, 12, n["x"], n["z"], f"тупиковый проезд {dd['s']['id']} {L:.0f} м > {dead_max} м", [dd["s"]["id"]]))
    # every block with buildings has an entry from a street
    lots_by_block = {}
    for l in K.lots(ctx):
        lots_by_block.setdefault(l["block"], []).append(l)
    has_b = {b.get("lot") for b in K.buildings(ctx)}
    new_b = {b.get("lot") for b in K.buildings(ctx) if b["source"] != "existing_osm" and not b.get("keep")}
    for blk in K.blocks(ctx):
        ls = lots_by_block.get(blk["id"], [])
        if not any(l["id"] in has_b for l in ls):
            continue
        ok = False
        for l in ls:
            s = segs.get(l.get("access"))
            if s and s["class"] in U.DRIVABLE and s["class"] not in U.NO_ACCESS and red.get(s["id"]) is not None and red[s["id"]].distance(l["_p"]) < 2.0:
                ok = True
                break
        if not ok:
            c = blk["_p"].representative_point()
            sev = "wait_neighbour" if blk["_p"].distance(ctx.area.exterior) < 2.0 else None
            txt = f"квартал {blk['id']} без въезда с улицы"
            if sev is None and not any(l["id"] in new_b for l in ls):
                # only existing 2025 houses (farmsteads, zimovkas): kept as OSM has them, owner decision 31.10
                sev, txt = "warning", txt + " (существующие дома 2025: как в OSM)"
            out.append(K.issue(ctx, 12, c.x, c.y, txt, [blk["id"]], sev=sev))
    return out


def _red_by_id(ctx):
    """Red lines of each street as one polygon: road_polys gives one piece per struct range (ground, embankment, cut,
    bridge), so a dict keyed by id alone would keep only the last piece of a split street."""
    c = K.cache(ctx)
    if "red_by_id" not in c:
        parts = {}
        for s, p, lv in K.road_polys(ctx, "red"):
            parts.setdefault(s["id"], []).append(p)
        c["red_by_id"] = {sid: (ps[0] if len(ps) == 1 else unary_union(ps)) for sid, ps in parts.items()}
    return c["red_by_id"]

def _tall_gaps(ctx, hi_h, gap, how):
    """Two buildings over hi_h (28 m) closer than `gap` (two near edges of their fire band and a fire lane), one of them
    new: no fire lane fits between their walls. The other may be as-is: an existing or kept building, a landmark whose
    Unity model stands over hi_h (its registry footprint, _landmarks_tall) or a block of a kept model quarter
    (_keep_models_tall: the Gate District model round Iconic). Two as-is buildings are left out (the model and the
    source data are as they are)."""
    new = [b for b in K.buildings(ctx) if b["height_m"] > hi_h and b["source"] != "existing_osm" and not b.get("keep")]
    if not new:
        return []
    fixed = [dict(b, _fixed=True) for b in K.buildings(ctx) if b["height_m"] > hi_h and (b["source"] == "existing_osm" or b.get("keep"))]
    fixed += [dict(b, _fixed=True) for b in _landmarks_tall(ctx, hi_h) + _keep_models_tall(ctx, hi_h)]
    tall = new + fixed
    if len(tall) < 2:
        return []
    tr = shapely.STRtree([b["_p"] for b in tall])
    out = []
    for i, j in zip(*tr.query([b["_p"] for b in tall], predicate="dwithin", distance=gap - BAND_TOL)):
        if i >= j:
            continue
        a, b = tall[int(i)], tall[int(j)]
        if a.get("_fixed") and b.get("_fixed"):
            continue                    # two as-is buildings (models, registry, source data): not placed by the land tools
        dd = a["_p"].distance(b["_p"])
        if dd >= gap - BAND_TOL:
            continue
        q = shapely.shortest_line(a["_p"], b["_p"]).interpolate(0.5, normalized=True)
        out.append(K.issue(ctx, 12, q.x, q.y, f"здания {a['id']} и {b['id']} выше {hi_h:.0f} м в {dd:.1f} м друг от друга < {gap:g} м "
                           f"({how}: пожарный проезд между ними не помещается)", [a["id"], b["id"]]))
    return out


LANDMARK_CS = os.path.join(U.REPO, "UnityProject", "Assets", "Scripts", "DigitalTwin", "Landmarks", "LandmarkData.cs")
GATE_MODEL = "gate_district.bytes"
_KEEP_MODEL = {}


def _gate_model_blocks():
    """[(polygon, top_m)] of the Gate District model (Resources/Landmarks/gate_district.bytes, QGD1) in the world frame
    (moved with Iconic, CONTRACT §7, district/gate_common.local_to_world): its triangles of 1 m and higher (IconicDistrict:
    a triangle under 1 m is ground) projected on the ground and joined, each block's top the highest of its triangles;
    blocks under a house's 25 m² (masts, lamps) are left out. [] when the model file is not there."""
    if "gate" in _KEEP_MODEL:
        return _KEEP_MODEL["gate"]
    out = []
    try:
        sys.path.insert(0, os.path.join(U.MAP, "district"))
        import gate_common as GC
        from gen_blocks_lots import SHED_MAX_M2
        d = GC.gate_district_bytes()
    except (OSError, ValueError, ImportError):
        d = None
    if d is not None:
        tri = d["p"][d["idx"]]
        top = tri[:, :, 1].max(1)
        up = top >= 1.0
        x, z = GC.local_to_world(tri[up][:, :, 0], tri[up][:, :, 2])
        polys = shapely.buffer(shapely.polygons(np.stack([x, z], -1)), 0.05, join_style=2)
        u = shapely.union_all(polys)
        tree = shapely.STRtree(polys)
        for g in getattr(u, "geoms", [u]):
            if g.area < SHED_MAX_M2:
                continue
            out.append((g.buffer(-0.05, join_style=2) if g.area > 1.0 else g, float(top[up][tree.query(g, predicate="intersects")].max())))
    _KEEP_MODEL["gate"] = out
    return out


def _keep_models_tall(ctx, hi_h):
    """Blocks over hi_h of the kept model quarters of the spec (`keep` whose source is gate_district.bytes) that stand in
    the keep polygon, as pseudo-buildings {id, _p, height_m}; the ids are <keep id>:m<k>."""
    out = []
    for kp in ctx.spec.get("keep") or []:
        if GATE_MODEL not in str(kp.get("source") or "") or len(kp.get("polygon") or []) < 3:
            continue
        kz = shapely.Polygon(kp["polygon"]).buffer(1.0)
        for k, (g, h) in enumerate(_gate_model_blocks()):
            if h > hi_h and kz.intersects(g.representative_point()):
                out.append({"id": f"{kp['id']}:m{k}", "_p": g, "height_m": round(h, 1), "_keep_model": True})
    return out


def _model_heights():
    """{Unity landmark model id: Height} from LandmarkData.cs (the top of the model); {} when the file is not there."""
    try:
        src = open(LANDMARK_CS, encoding="utf-8").read()
    except OSError:
        return {}
    out = {}
    for m in re.finditer(r"new Landmark\s*\{(.*?)\n\s*\}", src, re.S):
        i = re.search(r'\bId = "([^"]+)"', m.group(1))
        h = re.search(r"\bHeight = ([\d.]+)f", m.group(1))
        if i and h:
            out[i.group(1)] = float(h.group(1))
    return out


def _landmarks_tall(ctx, hi_h):
    """Landmarks with a Unity model (gen/landmark_models.json) over hi_h as pseudo-buildings {id, _p, _landmark}: the footprint
    of the spec's registry object, else the landmark's lot; a model whose height is not found counts as tall."""
    models = (U.read_json(os.path.join(U.MAP, "gen", "landmark_models.json")) or {}).get("models", {})
    hh = _model_heights()
    lots = {l.get("registry_id"): l for l in K.lots(ctx) if l.get("registry_id")}
    out = []
    for o in ctx.spec.get("objects") or []:
        rid = o.get("registry_id")
        if rid not in models or o.get("parent"):
            continue
        h = hh.get(models[rid])
        if h is not None and h <= hi_h:
            continue
        if o.get("footprint"):
            p = shapely.Polygon(o["footprint"]).buffer(0)
        elif rid in lots:
            p = lots[rid]["_p"]
        else:
            continue
        out.append({"id": f"{rid} (модель {models[rid]}, {h:.0f} м)" if h is not None else f"{rid} (модель {models[rid]})",
                    "_p": p, "_landmark": True})
    return out


# ------------------------------------------------------------------------------------------------------------ rule 13
def plot_norm(ctx, use, cap):
    """(m², key) of the plot norm for a social lot, None if the kind has no plot norm here."""
    N = K.norms(ctx)
    if use == "school" and cap:
        if cap <= max(U._band(k)[1] for k in N.v("schools.plot_m2_per_pupil")):
            return cap * N.band("schools.plot_m2_per_pupil", cap), "schools.plot_m2_per_pupil"
        return N.num("schools.plot_2000_places_ha") * 1e4 * cap / N.num("schools.typical_capacity"), "schools.plot_2000_places_ha"
    if use == "kindergarten" and cap:
        return cap * N.band("kindergartens.plot_m2_per_place", cap), "kindergartens.plot_m2_per_place"
    if use == "polyclinic" and cap:
        pp = N.v("clinics.polyclinic_plot")
        return max(pp["min_ha"], pp["ha_per_100_visits"] * cap / 100.0) * 1e4, "clinics.polyclinic_plot"
    return None, None


def check_13(ctx):
    m = K.missing(ctx, 13, "lots", "buildings", "network")
    if m:
        return m
    out = []
    by_lot = {}
    for b in K.buildings(ctx):
        by_lot.setdefault(b.get("lot"), []).append(b)
    red = unary_union([p for _, p, _ in K.road_polys(ctx, "red")])
    art = unary_union([p for s, p, lv in K.road_polys(ctx, "carriage") if s["class"] in U.ARTERIAL_ROADS])
    sb_art = K.nv(ctx, "setbacks.housing_from_arterial_carriageway_m", "default")
    for l in K.lots(ctx):
        u = l["use"]
        if u not in ("school", "kindergarten", "polyclinic", "hospital", "college", "university", "clinic"):
            continue
        c = l["_p"].representative_point()
        cap = l["capacity"].get("places") or l["capacity"].get("visits_per_shift") or l["capacity"].get("beds")
        need, key = plot_norm(ctx, u, cap)
        if need and l["_p"].area < need * 0.995:
            sev = "warning" if K.weak(ctx, key) else None
            out.append(K.issue(ctx, 13, c.x, c.y, f"{u} {l['id']}: участок {l['_p'].area:.0f} м² меньше нормы {need:.0f} м² ({key}, {cap})", [l["id"]], sev=sev))
        elif need and key and K.weak(ctx, key):
            out.append(K.issue(ctx, 13, c.x, c.y, f"{u} {l['id']}: участок на {cap} мест по аналогу ({key}: {K.norms(ctx).status(key)})", [l["id"]], sev="warning"))
        bs = by_lot.get(l["id"], [])
        if not bs:
            out.append(K.issue(ctx, 13, c.x, c.y, f"{u} {l['id']}: на участке нет здания", [l["id"]]))
        if u in ("school", "kindergarten"):
            z = K.lot_zone(ctx, l)
            village = bool(z and z[0]["use"] == "village_existing")
            rl = K.nv(ctx, ("schools" if u == "school" else "kindergartens") + ".building_from_red_line_m", "village" if village else "city")
            for b in bs:
                d = b["_p"].distance(red)
                if d < rl - 0.05:
                    bc = b["_p"].centroid
                    out.append(K.issue(ctx, 13, bc.x, bc.y, f"здание {u} {b['id']} в {d:.0f} м от красной линии (норма ≥ {rl} м)", [b["id"], l["id"]]))
            if not art.is_empty and l["_p"].distance(art) < sb_art:
                out.append(K.issue(ctx, 13, c.x, c.y, f"{u} {l['id']} вплотную к магистрали: {l['_p'].distance(art):.0f} м до проезжей части (норма ≥ {sb_art} м)", [l["id"]]))
    lot_ids = {l["id"] for l in K.lots(ctx)}
    for b in K.buildings(ctx):
        if b["use"] == "social" and (not b.get("lot") or b["lot"] not in lot_ids):
            c = b["_p"].centroid
            out.append(K.issue(ctx, 13, c.x, c.y, f"социальное здание {b['id']} без участка", [b["id"]]))
    return out


# ------------------------------------------------------------------------------------------------------------ rule 14
SERVICES = ["kindergarten", "school", "polyclinic", "pharmacy_shop", "square_or_park", "stop", "fire_station"]


def _radius(ctx, svc, low, village=False):
    """Radius by the norms; homes of existing villages take the village / rural columns."""
    if svc == "kindergarten":
        return K.nv(ctx, "kindergartens.radius_m", "low_rise_and_village" if (low or village) else "multi_storey"), "kindergartens.radius_m"
    if svc == "school":
        if village:
            return K.nv(ctx, "schools.rural_access", "walk_primary_km") * 1000.0, "schools.rural_access"
        return K.nv(ctx, "schools.radius_m"), "schools.radius_m"
    if svc == "polyclinic":
        return K.nv(ctx, "clinics.polyclinic_radius_m"), "clinics.polyclinic_radius_m"
    if svc == "pharmacy_shop":
        k = "low_rise" if (low or village) else "multi_storey"
        return min(K.nv(ctx, "pharmacy_shops.pharmacy_radius_m", k),
                   K.nv(ctx, "pharmacy_shops.daily_shops_radius_m", "village" if village else k)), "pharmacy_shops.pharmacy_radius_m"
    if svc == "square_or_park":
        return K.nv(ctx, "parks.square_or_playground", "max_distance_m"), "parks.square_or_playground"
    if svc == "stop":
        w = K.nv(ctx, "stops.walk_max_m")
        return (w["low_rise"]["min"] if (low or village) else w["default"]), "stops.walk_max_m"
    if svc == "fire_station":
        return K.nv(ctx, "fire.depot_radius_km") * 1000.0, "fire.depot_radius_km"


def phc_min_visits(ctx):
    """Visits per shift of the smallest primary care organisation of a city (clinics.phc_attached_population: the medical
    ambulatory from its minimum attached population, at clinics.polyclinic_visits_per_1000); None when the norm is missing.
    A smaller «polyclinic» is no polyclinic of rule 14."""
    try:
        return float(K.nv(ctx, "clinics.phc_min_visits_per_shift"))      # the same product, worked out in the registry
    except (KeyError, TypeError):
        pass
    try:
        pop = K.nv(ctx, "clinics.phc_attached_population")
        rate = K.nv(ctx, "clinics.polyclinic_visits_per_1000")
    except (KeyError, TypeError):
        return None
    return min(v["min"] if isinstance(v, dict) else v for v in pop.values()) * rate / 1000.0


# service: (capacity field of the lot, norm of the demand per 1000 residents, unit)
CAPACITY = {"kindergarten": ("places", "kindergartens.places_per_1000_genplan", "мест"),
            "school": ("places", "schools.places_per_1000_genplan", "мест"),
            "polyclinic": ("visits_per_shift", "clinics.polyclinic_visits_per_1000", "посещений в смену")}


def _capacity(ctx, s, i):
    """Capacity of a provider id of service s (None: not given, not limited)."""
    lid, _, tag = i.partition(":")
    l = K.lot_by_id(ctx).get(lid)
    if l is None:
        return None
    cap = l["capacity"] or {}
    if s == "kindergarten" and tag == "встроенный":
        return cap.get("kindergarten_builtin_places")
    return cap.get(CAPACITY[s][0])


def _adj(ctx):
    c = K.cache(ctx)
    if "walk_adj" not in c:
        c["walk_adj"] = {u: [(v, d["w"]) for v, d in nb.items()] for u, nb in K.walknet(ctx).G.adj.items()}
    return c["walk_adj"]


def _dijkstra(adj, inits, cutoff):
    import heapq
    dist, heap, n = {}, [], 0
    for d0, v in inits:
        if d0 <= cutoff and d0 < dist.get(v, math.inf):
            dist[v] = d0
            heap.append((d0, n, v))
            n += 1
    heapq.heapify(heap)
    while heap:
        d, _, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for v, w in adj.get(u, ()):
            nd = d + w
            if nd <= cutoff and nd < dist.get(v, math.inf):
                dist[v] = nd
                heapq.heappush(heap, (nd, n, v))
                n += 1
    return dist


def capacity_gaps(ctx, Y):
    """Houses within the radius of a kindergarten, school or polyclinic whose demand (residents × the norm per 1000) the
    providers within their radius cannot seat: a maximum flow of every house's demand to the capacities of the providers within
    its walking radius. {(block, service): [(house, unmet, demand, R, key, x, z, [(provider, capacity)])]}."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import maximum_flow
    from scipy.spatial import cKDTree
    c = K.cache(ctx)
    if ("capgap", Y) in c:
        return c[("capgap", Y)]
    W = K.walknet(ctx)
    adj = _adj(ctx)
    lotb = K.lot_by_id(ctx)
    lowmax = U.low_rise_max(K.norms(ctx))
    m2_res = U.twin_m2()[0]
    homes = [b for b in K.buildings(ctx) if b["years"][0] <= Y and _residential(ctx, b)]
    P = _providers(ctx, Y)
    out = {}
    if not homes:
        c[("capgap", Y)] = out
        return out
    cc = [b["_p"].centroid for b in homes]
    kd = cKDTree([(q.x, q.y) for q in cc])
    for s, (_, key, unit) in CAPACITY.items():
        rate = K.nv(ctx, key) / 1000.0
        Rs = [_radius(ctx, s, b["floors"] <= lowmax, _village(ctx, b))[0] for b in homes]
        dem = [_residents(ctx, b) * rate for b in homes]
        prov = [(x, z, i, _capacity(ctx, s, i)) for x, z, i in P[s]]
        edges = []          # (house, provider)
        for k, (x, z, i, cap) in enumerate(prov):
            Rmax = max(Rs)
            near = kd.query_ball_point((x, z), Rmax)
            if not near:
                continue
            sn = W.snap(x, z)
            D = {}
            if sn is not None:
                sg, along, perp, L = sn
                D = _dijkstra(adj, ([(perp + along, sg["a"])] if sg["a"] != sg["b"] else []) + [(perp + (L - along), sg["b"])], Rmax)
                D["__same__"] = {sg["id"]: [(along, perp)]}
            own = _own_lot(ctx, i)
            for h in near:
                b = homes[h]
                d = W.dist_to(cc[h].x, cc[h].y, D) if sn is not None else math.inf
                if own is not None and own == b.get("lot"):
                    d = min(d, math.hypot(cc[h].x - x, cc[h].y - z))
                if d <= Rs[h]:
                    edges.append((h, k))
        if not edges:
            continue
        # flow network: 0 source, 1..H houses, H+1..H+P providers, sink; capacities in hundredths
        H, Pn = len(homes), len(prov)
        sink = H + Pn + 1
        big = int(round(sum(dem) * 100)) + 1
        rows, cols, caps = [], [], []
        reach = sorted({h for h, _ in edges})
        for h in reach:
            rows.append(0); cols.append(1 + h); caps.append(int(math.ceil(dem[h] * 100)))
        for h, k in edges:
            rows.append(1 + h); cols.append(1 + H + k); caps.append(big)
        for k, (_, _, _, cap) in enumerate(prov):
            rows.append(1 + H + k); cols.append(sink); caps.append(big if cap is None else int(math.floor(cap * 100)))
        G = csr_matrix((np.asarray(caps, np.int32), (rows, cols)), shape=(sink + 1, sink + 1))
        F = maximum_flow(G, 0, sink).flow
        got = np.asarray(F[0, 1:H + 1].todense()).ravel() / 100.0
        by_h = {}
        for h, k in edges:
            by_h.setdefault(h, []).append(k)
        for h in reach:
            unmet = dem[h] - got[h]
            if unmet <= 0.01:
                continue
            b = homes[h]
            R, key_r = _radius(ctx, s, b["floors"] <= lowmax, _village(ctx, b))
            out.setdefault((_block(ctx, b), s), []).append(
                (b, unmet, dem[h], R, key_r, cc[h].x, cc[h].y, [(prov[k][2], prov[k][3]) for k in by_h[h]]))
    c[("capgap", Y)] = out
    return out


def small_social(ctx):
    """Lots of polyclinics smaller than the smallest primary care organisation: [(lot, visits, minimum)]."""
    vmin = phc_min_visits(ctx)
    if not vmin:
        return []
    return [(l, l["capacity"]["visits_per_shift"], vmin) for l in K.lots(ctx) if l["use"] in ("polyclinic", "hospital", "clinic")
            and (l["capacity"] or {}).get("visits_per_shift") is not None and l["capacity"]["visits_per_shift"] < vmin]


MIN_PLACES = {"kindergarten": ("kindergartens.min_places_city", ("kindergartens.rural_min_children",)),
              "school": ("schools.min_places_city", ("schools.rural_min_pupils", "primary"))}
M2_PER_PLACE = {"kindergarten": "kindergartens.building_m2_per_place", "school": "schools.building_m2_per_seat"}


def _village_lot(ctx, l):
    z = K.lot_zone(ctx, l)
    return bool(z) and z[0].get("use") == "village_existing"


def small_places(ctx):
    """Kindergarten and school lots below the smallest facility: in a village the guaranteed network's contingent
    (kindergartens.rural_min_children, schools.rural_min_pupils primary), in the city the model's smallest one
    (kindergartens.min_places_city, schools.min_places_city). [(lot, use, places, minimum, key)]."""
    out = []
    for l in K.lots(ctx):
        if l["use"] not in MIN_PLACES or (l["capacity"] or {}).get("places") is None:
            continue
        city_key, (vk, *vs) = MIN_PLACES[l["use"]]
        key, sub = (vk, vs) if _village_lot(ctx, l) else (city_key, [])
        try:
            vmin = float(K.nv(ctx, key, *sub))
        except (KeyError, TypeError):
            continue
        if l["capacity"]["places"] < vmin:
            out.append((l, l["use"], l["capacity"]["places"], vmin, key))
    return out


def short_floor_area(ctx):
    """Kindergarten and school lots whose buildings hold fewer places than the lot's capacity at the floor area per place
    (kindergartens.building_m2_per_place, schools.building_m2_per_seat). [(lot, use, places, gfa, holds, m2, key)]."""
    gfa = {}
    for b in K.buildings(ctx):
        if b.get("lot"):
            gfa[b["lot"]] = gfa.get(b["lot"], 0.0) + b["gfa_m2"]
    out = []
    for l in K.lots(ctx):
        key = M2_PER_PLACE.get(l["use"])
        cap = (l["capacity"] or {}).get("places")
        if key is None or not cap or l["id"] not in gfa:
            continue
        try:
            m2 = float(K.nv(ctx, key))
        except (KeyError, TypeError):
            continue
        holds = gfa[l["id"]] / m2
        if holds < cap - 0.5:
            out.append((l, l["use"], cap, gfa[l["id"]], holds, m2, key))
    return out


def _residents(ctx, b):
    """Residents of a house: its floor area over the twin's m² per resident, when it has homes (as places_check counts them)."""
    return b["gfa_m2"] / U.twin_m2()[0] if has_homes(b) else 0.0


def _provider_years(ctx):
    """{service: [(x, z, id, year)]}: every provider of the base scenario with the first year it stands. A service on a lot
    stands once the lot and a building on it stand; the shop on a centre's ground floor once a business building stands."""
    c = K.cache(ctx)
    if "svc_years" in c:
        return c["svc_years"]
    first, first_bus = {}, {}
    for b in K.buildings(ctx):
        lid, y = b.get("lot"), b["years"][0]
        first[lid] = min(first.get(lid, y), y)
        if b["use"] == "business":
            first_bus[lid] = min(first_bus.get(lid, y), y)
    g = K.nv(ctx, "kindergartens.group_size_max", "3-7_years")
    sq_min = K.nv(ctx, "parks.square_or_playground", "min_area_m2")
    vmin = phc_min_visits(ctx)
    P = {s: [] for s in SERVICES}
    for l in K.lots(ctx):
        c0 = l["_p"].centroid
        u, y0 = l["use"], l["years"][0]
        if l["id"] in first:
            y = max(y0, first[l["id"]])
            small = u in ("polyclinic", "hospital", "clinic") and vmin and (l["capacity"] or {}).get("visits_per_shift") is not None \
                and l["capacity"]["visits_per_shift"] < vmin
            if u in ("kindergarten", "school", "polyclinic", "pharmacy_shop", "fire_station") and not small:
                P[u].append((c0.x, c0.y, l["id"], y))
            if u in ("hospital", "clinic") and not small:
                P["polyclinic"].append((c0.x, c0.y, l["id"], y))
            if (l["capacity"] or {}).get("kindergarten_builtin_places", 0) >= g:
                P["kindergarten"].append((c0.x, c0.y, l["id"] + ":встроенный", y))
        if u in ("mixed_centre", "business") and l["id"] in first_bus:
            P["pharmacy_shop"].append((c0.x, c0.y, l["id"] + ":1-й этаж", max(y0, first_bus[l["id"]])))
    for b in K.buildings(ctx):
        if b["kind"] == "retail":
            c0 = b["_p"].centroid
            P["pharmacy_shop"].append((c0.x, c0.y, b["id"], b["years"][0]))
    f = ctx.features or {}
    for gr in f.get("greens", []):
        if gr["kind"] in ("park", "square", "yard") and K.geom(gr).area >= sq_min:
            # a green is reached at its edge (entrances every land_util.GREEN_ENTRY_STEP m), not at its middle
            P["square_or_park"] += [(x, z, gr["id"], gr["years"][0]) for x, z in U.entrances(K.geom(gr))]
    for st in f.get("stops", []):
        P["stop"].append((st["x"], st["z"], st["id"], (st.get("years") or U.EXISTING_YEARS)[0]))
    c["svc_years"] = P
    return P


def _providers(ctx, Y):
    """{service: [(x, z, id)]} standing in year Y (base scenario)."""
    return {s: [(x, z, i) for x, z, i, y in v if y <= Y] for s, v in _provider_years(ctx).items()}


def _own_lot(ctx, i):
    """Lot of a provider id (a lot, a lot with a «:» suffix, or a building), None for greens and stops."""
    lid = i.split(":")[0]
    if lid in K.lot_by_id(ctx):
        return lid
    c = K.cache(ctx)
    if "b_lot" not in c:
        c["b_lot"] = {b["id"]: b.get("lot") for b in K.buildings(ctx)}
    return c["b_lot"].get(lid)


def _residential(ctx, b):
    """A house of rule 14's demand: any building with homes (has_homes), new housing and existing houses alike, whatever
    its lot: the same buildings as buildings.json totals.residents, so the demand is one number (tester item 75)."""
    return has_homes(b)


def _block(ctx, b):
    """Block of a house: its lot's block, else the block its footprint lies in (an existing house without a lot)."""
    l = K.lot_by_id(ctx).get(b.get("lot"))
    if l is not None:
        return l["block"]
    c = K.cache(ctx)
    if "blk_tree" not in c:
        bl = K.blocks(ctx)
        c["blk_tree"] = (shapely.STRtree([x["_p"] for x in bl]), bl)
    tr, bl = c["blk_tree"]
    q = b["_p"].representative_point()
    hit = [bl[int(i)] for i in tr.query(q, predicate="intersects")]
    return hit[0]["id"] if hit else NO_BLOCK


NO_BLOCK = "—"


def _blk_ru(blk):
    return "дома вне кварталов (без участка)" if blk == NO_BLOCK else f"квартал {blk}"


def _village(ctx, b):
    return (K.lot_by_id(ctx).get(b.get("lot")) or {}).get("use") == "village_existing"


def service_table(ctx, Y=2050):
    """Per residential block: homes, residents, worst walking distance to each service and whether it is within the norm."""
    c = K.cache(ctx)
    if ("svc", Y) in c:
        return c[("svc", Y)]
    m2_res = U.twin_m2()[0]
    lowmax = U.low_rise_max(K.norms(ctx))
    W = K.walknet(ctx)
    P = _providers(ctx, Y)
    D = {s: (W.dist_from([(x, z) for x, z, _ in P[s]]) if P[s] and s != "fire_station" else {}) for s in SERVICES}
    lotb = K.lot_by_id(ctx)
    # a provider on the house's own lot (a built-in kindergarten, a shop on the ground floor) is reached across the yard,
    # not along the streets the two points snap to
    own = {s: {} for s in SERVICES}
    for s in SERVICES:
        for x, z, i in P[s]:
            lid = _own_lot(ctx, i)
            if lid is not None:
                own[s].setdefault(lid, []).append((x, z))
    homes_by_block = {}
    for b in K.buildings(ctx):
        if b["years"][0] <= Y and _residential(ctx, b):
            homes_by_block.setdefault(_block(ctx, b), []).append(b)
    rows = []
    for blk_id, bs in sorted(homes_by_block.items()):
        vil = all((lotb.get(b.get("lot")) or {}).get("use") == "village_existing" for b in bs)
        row = {"block": blk_id, "homes": sum(b["homes"] for b in bs), "houses": len(bs),
               "residents": round(sum(_residents(ctx, b) for b in bs)),
               "low_rise": all(b["floors"] <= lowmax for b in bs), "village": vil, "services": {}}
        for s in SERVICES:
            worst, wb = -1.0, None
            for b in bs:
                cc = b["_p"].centroid
                low = b["floors"] <= lowmax
                if s == "fire_station":
                    d = min((math.hypot(cc.x - x, cc.y - z) for x, z, _ in P[s]), default=float("inf"))
                else:
                    d = W.dist_to(cc.x, cc.y, D[s]) if D[s] else float("inf")
                    d = min([d] + [math.hypot(cc.x - x, cc.y - z) for x, z in own[s].get(b.get("lot"), [])])
                R, key = _radius(ctx, s, low, (lotb.get(b.get("lot")) or {}).get("use") == "village_existing")
                over = d - R
                if wb is None or over > worst:
                    worst, wb = over, (b, d, R, key, cc)
            b, d, R, key, cc = wb
            row["services"][s] = {"dist_m": None if math.isinf(d) else round(d), "norm_m": R, "ok": d <= R, "norm_key": key,
                                  "worst": b["id"], "x": round(cc.x, 1), "z": round(cc.y, 1)}
        rows.append(row)
    c[("svc", Y)] = rows
    return rows


def has_homes(b):
    """A building whose floor area counts as residents: new housing, or any building with homes (an existing house once the
    land tools give it homes). The same selection as buildings.json totals.residents (gen_buildings), so one number."""
    return b["use"] == "housing" or (b.get("homes") or 0) > 0


def places_check(ctx, Y=2050):
    m2_res = U.twin_m2()[0]
    res = sum(b["gfa_m2"] for b in K.buildings(ctx) if b["years"][0] <= Y and has_homes(b)) / m2_res
    res += sum(l["capacity"].get("homes", 0) for l in K.lots(ctx) if l["use"] == "landmark" and l["years"][0] <= Y) * \
        float((ctx.spec.get("targets") or {}).get("home_m2") or U.LEVEL0_HOME_M2) / m2_res
    sch = sum(l["capacity"].get("places", 0) for l in K.lots(ctx) if l["use"] == "school" and l["years"][0] <= Y)
    kg = sum(l["capacity"].get("places", 0) for l in K.lots(ctx) if l["use"] == "kindergarten" and l["years"][0] <= Y)
    kg_b = sum(l["capacity"].get("kindergarten_builtin_places", 0) for l in K.lots(ctx) if l["years"][0] <= Y)
    return {"year": Y, "residents": round(res),
            "school": {"places": sch, "norm": round(res * K.nv(ctx, "schools.places_per_1000_genplan") / 1000), "key": "schools.places_per_1000_genplan"},
            "kindergarten": {"places": kg + kg_b, "standalone": kg, "built_in": kg_b,
                             "norm": round(res * K.nv(ctx, "kindergartens.places_per_1000_genplan") / 1000), "key": "kindergartens.places_per_1000_genplan"}}


def late_services(ctx, final):
    """New houses out of a service's norm in the years after they are settled. {(block, service): [(from, to, d, R, key, house,
    x, z)]}: the house is out of the norm R from its settlement year `from` until the year `to` its service comes within R
    (None: not before the final year either); d is the distance in the settlement year. Providers only add up over the years,
    so one Dijkstra per service grows by the providers of each year (the same distances as WalkNet.dist_from of that year)."""
    import heapq
    c = K.cache(ctx)
    if ("late", final) in c:
        return c[("late", final)]
    W = K.walknet(ctx)
    adj = {u: [(v, d["w"]) for v, d in nb.items()] for u, nb in W.G.adj.items()}
    lowmax = U.low_rise_max(K.norms(ctx))
    lotb = K.lot_by_id(ctx)
    houses = [b for b in K.buildings(ctx) if _residential(ctx, b) and b["source"] != "existing_osm" and not b.get("keep")
              and b["years"][0] < final]
    out = {}
    for s, prov in _provider_years(ctx).items():
        prov = sorted((p for p in prov if p[3] <= final), key=lambda p: p[3])
        settle = {}
        for b in houses:
            settle.setdefault(b["years"][0], []).append(b)
        dist, same, heap, own, k, n = {}, {}, [], {}, 0, 0
        dist["__same__"] = same
        waiting = []
        for Y in sorted(set(settle) | {p[3] for p in prov}):
            k0 = k
            while k < len(prov) and prov[k][3] <= Y:
                x, z, i, _ = prov[k]
                k += 1
                lid = _own_lot(ctx, i)
                if lid is not None:
                    own.setdefault(lid, []).append((x, z))
                sn = W.snap(x, z) if s != "fire_station" else None
                if sn is None:
                    continue
                sg, along, perp, L = sn
                same.setdefault(sg["id"], []).append((along, perp))
                # as dist_from: the source joins both ends of its segment (one edge when the segment is a loop)
                for d0, v in ([(perp + along, sg["a"])] if sg["a"] != sg["b"] else []) + [(perp + (L - along), sg["b"])]:
                    if d0 < dist.get(v, math.inf):
                        dist[v] = d0
                        heapq.heappush(heap, (d0, n, v))
                        n += 1
            while heap:
                d, _, u = heapq.heappop(heap)
                if d > dist[u]:
                    continue
                for v, w in adj.get(u, ()):
                    nd = d + w
                    if nd < dist.get(v, math.inf):
                        dist[v] = nd
                        heapq.heappush(heap, (nd, n, v))
                        n += 1

            def walk(b):
                cc = b["_p"].centroid
                if s == "fire_station":
                    return min((math.hypot(cc.x - x, cc.y - z) for x, z, _, _ in prov[:k]), default=math.inf), cc
                d = W.dist_to(cc.x, cc.y, dist) if k else math.inf
                return min([d] + [math.hypot(cc.x - x, cc.y - z) for x, z in own.get(b.get("lot"), [])]), cc

            if k > k0:
                still = []
                for w8 in waiting:
                    if walk(w8[5])[0] <= w8[3]:
                        w8[1] = Y
                    else:
                        still.append(w8)
                waiting = still
            for b in settle.get(Y, ()):
                R, key = _radius(ctx, s, b["floors"] <= lowmax, _village(ctx, b))
                d, cc = walk(b)
                if d > R:
                    w8 = [Y, None, d, R, key, b, cc.x, cc.y]
                    waiting.append(w8)
                    out.setdefault((_block(ctx, b), s), []).append(w8)
    c[("late", final)] = out
    return out


def _spans(ys):
    """«2036–2039, 2041» from [(from, to)] year intervals (to exclusive)."""
    ys = sorted(ys)
    m = []
    for a, b in ys:
        if m and a <= m[-1][1]:
            m[-1][1] = max(m[-1][1], b)
        else:
            m.append([a, b])
    return ", ".join(f"{a}" if b - 1 <= a else f"{a}–{b - 1}" for a, b in m)


def check_14(ctx):
    """The service table of the final year per residential block, and every new house within each norm from the year it is
    settled: a block that waits for a service is flagged with its years even when the service comes later."""
    m = K.missing(ctx, 14, "lots", "buildings", "network", "features")
    if m:
        return m
    out = []
    final = max(K.stage_years(ctx))
    late = late_services(ctx, final)

    def sev_of(x, z, R, key):
        sev = None
        if K.edge_dist(ctx, x, z) < R:
            sev = "wait_neighbour"      # a provider across the district edge could still serve it (none here, or too far)
        if K.weak(ctx, key):
            sev = "warning"
        return sev

    bad = set()
    for row in service_table(ctx, final):
        for s, v in row["services"].items():
            if v["ok"]:
                continue
            bad.add((row["block"], s))
            dist = "нет на сети" if v["dist_m"] is None else f"{v['dist_m']} м"
            ws = [w8 for w8 in late.get((row["block"], s), ())]
            since = f"; не в норме с {min(w8[0] for w8 in ws)}" if ws else ""
            out.append(K.issue(ctx, 14, v["x"], v["z"], f"{_blk_ru(row['block'])}: {s} — {dist} (норма {v['norm_m']:.0f} м), дом {v['worst']}{since}",
                               [row["block"], v["worst"]], sev=sev_of(v["x"], v["z"], v["norm_m"], v["norm_key"])))
    for (blk, s), ws in sorted(late.items()):
        if (blk, s) in bad:
            continue
        y0, y1, d, R, key, b, x, z = max(ws, key=lambda w8: w8[2] - w8[3])
        dist = "нет ни одного" if math.isinf(d) else f"до {d:.0f} м"
        to = max(w8[1] or final for w8 in ws)
        out.append(K.issue(ctx, 14, x, z, f"{_blk_ru(blk)}: {s} в {_spans([(w8[0], w8[1] or final) for w8 in ws])} — {dist} (норма {R:.0f} м), "
                           f"дом {b['id']} (заселён в {y0}); в норме с {to}", [blk, b["id"]], sev="info"))   # plan: intermediate years are a coverage report, an error only in 2050
    # capacities: the providers within the radius must seat the demand of the houses by the norms per 1000 residents
    for (blk, s), ws in sorted(capacity_gaps(ctx, final).items()):
        if (blk, s) in bad:
            continue
        b, unmet, dem, R, key, x, z, pr = max(ws, key=lambda w8: w8[1])
        _, rkey, unit = CAPACITY[s]
        tot_u, tot_d = sum(w8[1] for w8 in ws), sum(w8[2] for w8 in ws)
        if tot_u < 0.5:
            continue        # less than half a place short: rounding of the shares
        seen = sorted({p_ for w8 in ws for p_ in w8[7]}, key=lambda t: str(t[0]))
        pl = ", ".join(f"{i} ({'—' if cap is None else f'{cap:g}'})" for i, cap in seen[:4]) + (" …" if len(seen) > 4 else "")
        sev = sev_of(x, z, R, key)
        if K.weak(ctx, rkey):
            sev = "warning"
        out.append(K.issue(ctx, 14, x, z, f"{_blk_ru(blk)}: {s} в радиусе {R:.0f} м не вмещает: не хватает {tot_u:.0f} из {tot_d:.0f} {unit} по норме "
                           f"({rkey}: {K.nv(ctx, rkey):g} на 1000 жителей), дом {b['id']}; в радиусе {pl}", [blk, b["id"]] + [i for i, _ in seen[:4]], sev=sev))
    for l, v, vmin in small_social(ctx):
        q = l["_p"].representative_point()
        pop = K.nv(ctx, "clinics.phc_attached_population")
        out.append(K.issue(ctx, 14, q.x, q.y, f"{l['use']} {l['id']} на {v:g} посещений в смену меньше наименьшей организации ПМСП "
                           f"(врачебная амбулатория от {min(x['min'] if isinstance(x, dict) else x for x in pop.values())} прикреплённых жителей ≈ "
                           f"{vmin:.0f} посещений по clinics.polyclinic_visits_per_1000): в радиус поликлиники не засчитана", [l["id"]]))
    for l, use, v, vmin, key in small_places(ctx):
        q = l["_p"].representative_point()
        out.append(K.issue(ctx, 14, q.x, q.y, f"{use} {l['id']} на {v:g} мест меньше наименьшей вместимости {vmin:g} ({key})", [l["id"]],
                           sev="warning" if K.weak(ctx, key) else None))
    for l, use, cap, g, holds, m2, key in short_floor_area(ctx):
        q = l["_p"].representative_point()
        out.append(K.issue(ctx, 14, q.x, q.y, f"{use} {l['id']}: {cap:g} мест, в зданиях {g:.0f} м² — на {holds:.0f} мест ({m2:g} м² на место, {key})",
                           [l["id"]], sev="warning" if K.weak(ctx, key) else None))
    pc = places_check(ctx, final)
    c = ctx.area.centroid
    out += _demand_one_number(ctx, final, pc)
    for k in ("school", "kindergarten"):
        if pc[k]["places"] < pc[k]["norm"]:
            out.append(K.issue(ctx, 14, c.x, c.y, f"{k}: {pc[k]['places']} мест на {pc['residents']} жителей, минимум генплана {pc[k]['norm']} ({pc[k]['key']})", []))
    return out


def _demand_one_number(ctx, Y, pc):
    """The residents rule 14 serves (every house with homes standing in Y, plus the homes of landmark lots, which count in
    the district places) against buildings.json totals.residents: one number (validator.panel_vs_data_tolerance)."""
    houses = [b for b in K.buildings(ctx) if b["years"][0] <= Y and _residential(ctx, b)]
    r_h = sum(_residents(ctx, b) for b in houses)
    ex = [b for b in houses if b["source"] == "existing_osm"]
    r_ex = sum(_residents(ctx, b) for b in ex)
    r_l = pc["residents"] - r_h
    c = ctx.area.centroid
    tot = ((ctx.buildings or {}).get("totals") or {}).get("residents")
    what = (f"спрос правила 14 в {Y}: {pc['residents']} жителей — {len(houses)} домов с квартирами {r_h:.0f} (из них существующих "
            f"{len(ex)}: {r_ex:.0f}), квартиры участков-ориентиров {r_l:.0f}")
    if tot is None:
        return [K.issue(ctx, 14, c.x, c.y, what + "; в buildings.json нет totals.residents", [], sev="info")]
    if abs(float(tot) - pc["residents"]) > K.nv(ctx, "validator.panel_vs_data_tolerance"):
        return [K.issue(ctx, 14, c.x, c.y, what + f" ≠ buildings.json totals.residents {tot}", [])]
    return [K.issue(ctx, 14, c.x, c.y, what + f" = buildings.json totals.residents {tot}", [], sev="info")]


# ------------------------------------------------------------------------------------------------------------ rule 15
def _rail_housing(ctx):
    """Houses with homes nearer than szz.rail_m (housing from the outer track's axis) to a railway track (lib.rail:
    operating tracks, on the ground or on a bridge; no tunnels, metro or abandoned lines): a new house is an error, an
    existing one (2025) a warning. The nearest track is the outer one on the house's side."""
    from lib import rail
    lim = float(K.nv(ctx, "szz.rail_m")["housing_from_outer_track_axis"])
    tr = rail.tracks(ctx.area, lim)
    homes = [b for b in K.buildings(ctx) if has_homes(b)]
    if not tr or not homes:
        return []
    lines = [shapely.LineString(t["P"]) for t in tr]
    tree = shapely.STRtree(lines)
    out = []
    for b in homes:
        near = [(lines[int(j)].distance(b["_p"]), tr[int(j)]) for j in tree.query(b["_p"].buffer(lim), predicate="intersects")]
        if not near:
            continue
        d, t = min(near, key=lambda q: q[0])
        if d >= lim:
            continue
        old = b["source"] == "existing_osm" or int(b["years"][0]) <= U.EXISTING_YEARS[0]
        c = b["_p"].centroid
        out.append(K.issue(ctx, 15, c.x, c.y, f"дом {b['id']} в {d:.0f} м от пути ж/д {t['name'] or t['id'][:8]} (szz.rail_m: жильё ≥ {lim:.0f} м от оси крайнего пути)"
                           + (" — существующий дом 2025" if old else ""), [b["id"], t["id"]], sev="warning" if old else None))
    return out


def check_15(ctx):
    m = K.missing(ctx, 15, "buildings")
    if m:
        return m
    out = _rail_housing(ctx)
    ws = K.nv(ctx, "szz.wind_sector_deg")
    widths = K.nv(ctx, "szz.class_width_m")
    lotb = K.lot_by_id(ctx)
    ind = [b for b in K.buildings(ctx) if b["use"] == "industry"]
    sens = [b for b in K.buildings(ctx) if b["use"] in ("housing", "existing", "social")]
    if not ind or not sens:
        return out
    st = shapely.STRtree([b["_p"] for b in sens])
    no_class = set()
    green = ctx.d.lower().startswith("green")

    def in_sector(a, s):
        a0, a1 = s
        return (a0 <= a <= a1) if a0 <= a1 else (a >= a0 or a <= a1)
    for b in ind:
        l = lotb.get(b.get("lot"))
        z = K.lot_zone(ctx, l) if l else None
        cls = (z[1].get("szz_class") if z else None)
        if cls is None:
            cls = sorted(widths, key=lambda k: widths[k]["min"])[0]
            no_class.add(z[0]["id"] if z else b["id"])
        w = widths[cls]["min"]
        reach = w * ws["zone_factor"]
        bc = b["_p"].centroid
        for j in st.query(b["_p"].buffer(reach), predicate="intersects"):
            q = sens[int(j)]
            d = q["_p"].distance(b["_p"])
            qc = q["_p"].centroid
            ang = math.degrees(math.atan2(qc.x - bc.x, qc.y - bc.y)) % 360
            if d < w and q["use"] != "existing":
                out.append(K.issue(ctx, 15, qc.x, qc.y, f"{q['use']} {q['id']} внутри СЗЗ {w} м класса {cls} от {b['id']} ({d:.0f} м)", [q["id"], b["id"]]))
            elif in_sector(ang, ws["default_sector"]):
                out.append(K.issue(ctx, 15, qc.x, qc.y, f"{q['use']} {q['id']} с подветренной стороны {b['id']} ({ang:.0f}°, {d:.0f} м < {reach:.0f} м)",
                                   [q["id"], b["id"]], sev="warning" if q["use"] == "existing" else None))
            elif green and in_sector(ang, ws["green_warning_sector"]):
                out.append(K.issue(ctx, 15, qc.x, qc.y, f"{q['id']} в секторе {ws['green_warning_sector']} от {b['id']}", [q["id"], b["id"]], sev="warning"))
    if no_class:
        c = ind[0]["_p"].centroid
        out.append(K.issue(ctx, 15, c.x, c.y, f"класс СЗЗ не задан в спецификации ({', '.join(sorted(no_class))}): взят наименьший", sorted(no_class), sev="warning"))
    return out


# ------------------------------------------------------------------------------------------------------------ rule 16
def _airfields(ctx):
    reg = U.read_json(os.path.join(U.SPEC_DIR, "registry.json")) or {}
    pts = []
    rows = {r.get("id"): r for r in reg.get("rows", [])}
    for key, txt in K.nv(ctx, "heights.airfield_points").items():
        mm = re.search(r"registry\.json:\s*([A-Za-z0-9_]+)", str(txt))
        r = rows.get(mm.group(1)) if mm else None
        if r is None:
            continue
        g = r.get("geom") or {}
        cp = (r.get("points") or {}).get("control_point")
        if isinstance(cp, dict) and cp.get("coordinates"):
            cp = cp["coordinates"]
        if cp:
            pts.append((cp[0], cp[1], r["id"]))
        elif g.get("type") == "Point":
            pts.append((g["coordinates"][0], g["coordinates"][1], r["id"]))
        elif g.get("type") == "Polygon":
            c = shapely.geometry.Polygon(g["coordinates"][0]).centroid
            pts.append((c.x, c.y, r["id"]))
    return pts


def check_16(ctx):
    m = K.missing(ctx, 16, "buildings", "lots")
    if m:
        return m
    out = []
    thr = K.nv(ctx, "heights.airfield_height_threshold_m")
    rad = K.nv(ctx, "heights.airfield_approval_radius_km") * 1000.0
    hr = K.nv(ctx, "heights.high_rise_floors")
    lowmax = U.low_rise_max(K.norms(ctx))
    afs = _airfields(ctx)
    lotb = K.lot_by_id(ctx)
    for b in K.buildings(ctx):
        if b["source"] == "existing_osm":
            continue
        c = b["_p"].centroid
        l = lotb.get(b.get("lot"))
        z = K.lot_zone(ctx, l) if l else None
        if z:
            cap = z[1].get("height_cap_m")
            if cap and b["height_m"] > cap + 0.05 and b.get("kind") not in ("education", "health"):
                out.append(K.issue(ctx, 16, c.x, c.y, f"здание {b['id']} {b['height_m']:.0f} м выше потолка зоны {z[0]['id']} {cap} м", [b["id"]]))
            fl = z[1].get("floors") or [1, 1]
            if b["floors"] > hr and fl[1] <= lowmax:
                out.append(K.issue(ctx, 16, c.x, c.y, f"высотка {b['id']} ({b['floors']} эт.) в малоэтажной зоне {z[0]['id']}", [b["id"]]))
        if b["height_m"] >= thr:
            near = [a for a in afs if math.hypot(c.x - a[0], c.y - a[1]) <= rad]
            if near and not b.get("aviation"):
                out.append(K.issue(ctx, 16, c.x, c.y, f"здание {b['id']} {b['height_m']:.0f} м в {rad / 1000:.0f} км от {near[0][2]} без пометки «нужно согласование»", [b["id"]]))
    return out


# ------------------------------------------------------------------------------------------------------------ rule 17
def check_17(ctx):
    m = K.missing(ctx, 17, "features")
    if m:
        return m
    import gen_masks
    out = []
    centre = gen_masks.centre_polys(ctx.spec, K.norms(ctx))
    views = [(v, gen_masks.sector(v["apex"], v["dir_deg"], v["fov_deg"], v["len_m"])) for v in ctx.spec.get("views", [])]
    mx = K.nv(ctx, "parking.ground_lot_max_in_centre")
    for p_ in (ctx.features or {}).get("parking", []):
        if p_["type"] == "underground":
            continue
        pp = K.poly(p_["polygon"])
        c = pp.representative_point()
        if p_["type"] == "surface" and p_["cap"] > mx and not centre.is_empty and pp.intersects(centre):
            out.append(K.issue(ctx, 17, c.x, c.y, f"наземная стоянка {p_['id']} на {p_['cap']} мест в центре района (норма ≤ {mx})", [p_["id"]]))
        for v, sec in views:
            if pp.intersects(sec):
                out.append(K.issue(ctx, 17, c.x, c.y, f"стоянка {p_['id']} в секторе обзора фасада {v['registry_id']}", [p_["id"], v["id"]]))
    return out


# ------------------------------------------------------------------------------------------------------------ rule 18
def check_18(ctx):
    m = K.missing(ctx, 18, "buildings")
    if m:
        return m
    idm = K.nv(ctx, "validator.identical_models")
    R, mx = idm["radius_m"], idm["max_same_model"]
    out = []
    cand = [b for b in K.buildings(ctx) if b["use"] in ("housing", "business") and b["source"] != "existing_osm"
            and b["kind"] not in ("solar", "industry") and not str(b.get("model") or "").endswith("_typical")]
    by_model = {}
    for b in cand:
        by_model.setdefault(b["model"], []).append(b)
    seen = set()
    for mdl, bs in by_model.items():
        if len(bs) <= mx:
            continue
        P = np.array([[b["_p"].centroid.x, b["_p"].centroid.y] for b in bs])
        for i, b in enumerate(bs):
            near = np.flatnonzero(np.hypot(P[:, 0] - P[i, 0], P[:, 1] - P[i, 1]) <= R)
            if len(near) > mx:
                key = (mdl, tuple(sorted(int(k) for k in near)))
                if key in seen:
                    continue
                seen.add(key)
                out.append(K.issue(ctx, 18, P[i, 0], P[i, 1], f"модель {mdl}: {len(near)} зданий в круге {R} м (норма ≤ {mx})", [bs[k]["id"] for k in near]))
    # a warehouse is one class-A shed at most (модель qTwin, land_models.WAREHOUSE_*): no single logistics box
    a_max, l_max = LM.WAREHOUSE_M2[1], LM.WAREHOUSE_LEN_MAX
    for b in K.buildings(ctx):
        if b["source"] == "existing_osm" or (b["kind"] != "industry" and b["use"] != "industry"):
            continue
        _, ln, wd = U.axis(b["_p"])
        if b["_p"].area > a_max * 1.01 or ln > l_max * 1.01:
            c = b["_p"].centroid
            out.append(K.issue(ctx, 18, c.x, c.y, f"склад {b['id']}: {b['_p'].area:.0f} м², {ln:.0f}×{wd:.0f} м — больше корпуса класса А "
                               f"(модель qTwin: ≤ {a_max:.0f} м², длина ≤ {l_max:.0f} м)", [b["id"]]))
    return out


RULES = [
    {"no": 12, "key": "access", "fn": check_12, "needs": ["buildings", "network", "lots", "blocks"]},
    {"no": 13, "key": "social_plots", "fn": check_13, "needs": ["lots", "buildings", "network"]},
    {"no": 14, "key": "services", "fn": check_14, "needs": ["lots", "buildings", "network", "features"]},
    {"no": 15, "key": "sanitary_gaps", "fn": check_15, "needs": ["buildings"]},
    {"no": 16, "key": "heights", "fn": check_16, "needs": ["buildings", "lots"]},
    {"no": 17, "key": "parking_centre_views", "fn": check_17, "needs": ["features"]},
    {"no": 18, "key": "identical_models", "fn": check_18, "needs": ["buildings"]},
]
