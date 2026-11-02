"""Level 0 of the map redraw: the truth about the land → tools/map/spec/city.json v0 + layer files.

    python3 -I tools/map/geo/fetch_overture.py     # once: open map data → OUT/osm/
    python3 -I tools/map/geo/build_city.py         # everything else: genplan layers, proof, spec, pictures, comparison

Reads (read-only): the twin's data (frames.asset: buildings.csv, layer_infrastructure.bytes, roads.json, lrt_routes.json,
construction.json, risk.json, terrain), the maket geojson, OUT/osm/*.geojson. Writes OUT/genplan/, OUT/derived/,
OUT/transform_proof.json, OUT/README.md, tools/map/spec/city.json; then runs render_maps.py and compare_twin.py.
Flags: --no-render, --no-compare."""
import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, MultiLineString, Point, Polygon, mapping  # noqa: E402
from shapely.ops import linemerge, polylabel, split, substring, unary_union  # noqa: E402

import city_l1  # noqa: E402
import frames  # noqa: E402
import layers  # noqa: E402
import terrain  # noqa: E402
import twin  # noqa: E402

# Level 1 (w42): the open data of level 0 (osm/, overture_raw/) stays where w34 wrote it and is only read; every layer this
# script makes is written to its own folder. A layer asked for by name is read from OUT when it is there, else from L0_SRC.
L0_SRC = os.environ.get("ALATAU_L0_SRC", "/mnt/project-files/alatau_stage7/level0/w34")
frames.OUT = os.environ.get("ALATAU_CITY_OUT", "/mnt/project-files/alatau_stage7/level0/w42")
_layer_path_out = layers.path


def _layer_path(name):
    p = _layer_path_out(name)
    if os.path.exists(p):
        return p
    return os.path.join(L0_SRC, os.path.relpath(p, frames.OUT))


layers.path = _layer_path


def src_path(*parts):
    """A level-0 input file (osm/…, overture_raw/…): OUT if this script wrote it, else L0_SRC."""
    p = os.path.join(frames.OUT, *parts)
    return p if os.path.exists(p) else os.path.join(L0_SRC, *parts)

OVT = f"Overture Maps {frames.OVERTURE_RELEASE} (© OpenStreetMap contributors, Overture Maps Foundation)"
ICONIC = (-3170.0, -19080.0)          # LandmarkData.cs:97 (Id "iconic"), used by IconicDistrict / FilmLook / FilmReel / TwinPitch
ICONIC_FIRST_SITE = (-2567.0, -20654.0)
SPEC_AREAS = ["gate", "golden", "growing_w", "growing_e", "green"]
AREA_NAMES = {"gate": "Gate", "golden": "Golden", "growing_w": "Growing-запад", "growing_e": "Growing-восток", "green": "Green", "outside": "вне города"}


def _flat(v):
    return isinstance(v, (int, float, str, bool)) or v is None or (isinstance(v, list) and all(_flat(x) for x in v))


def dump_compact(o, ind=0):
    """JSON with structure indented but coordinate lists and small records on one line (human-editable, small)."""
    sp = " " * ind
    if isinstance(o, dict):
        if not o:
            return "{}"
        items = [f'{sp} {json.dumps(k, ensure_ascii=False)}: {dump_compact(v, ind + 1)}' for k, v in o.items()]
        return "{\n" + ",\n".join(items) + "\n" + sp + "}"
    if isinstance(o, list):
        if _flat(o):
            j = json.dumps(o, ensure_ascii=False, separators=(",", ":"))
            if len(j) > 400 and all(isinstance(x, list) for x in o):        # coordinate lists: 10 points per line
                rows = [",".join(json.dumps(x, separators=(",", ":")) for x in o[i:i + 10]) for i in range(0, len(o), 10)]
                return "[\n" + ",\n".join(sp + "  " + r for r in rows) + "\n" + sp + "]"
            return j
        one = [json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in o]
        if all(len(x) <= 360 for x in one):
            return "[\n" + ",\n".join(sp + "  " + x for x in one) + "\n" + sp + "]"
        return "[\n" + ",\n".join(sp + "  " + dump_compact(x, ind + 1) for x in o) + "\n" + sp + "]"
    return json.dumps(o, ensure_ascii=False)


def rnd(v, nd=1):
    return round(float(v), nd)


def ring_coords(poly, nd=0, tol=None):
    p = poly.simplify(tol, preserve_topology=True) if tol else poly
    c = np.asarray(p.exterior.coords)
    return [[int(round(x)) if nd == 0 else round(x, nd), int(round(z)) if nd == 0 else round(z, nd)] for x, z in c]


def line_coords(line, nd=0, tol=None):
    g = line.simplify(tol) if tol else line
    parts = list(getattr(g, "geoms", [g]))
    res = []
    for p in parts:
        res.append([[int(round(x)), int(round(z))] if nd == 0 else [round(x, nd), round(z, nd)] for x, z in np.asarray(p.coords)])
    return res if len(res) > 1 else res[0]


def densify_pts(line, step=20.0):
    d = np.arange(0, line.length, step)
    return np.array([line.interpolate(t).coords[0] for t in d])


def outline_of(g):
    return g.exterior if g.geom_type == "Polygon" else MultiLineString([p.exterior for p in g.geoms])


def nn_dist(a_pts, b_line, step=10.0):
    from scipy.spatial import cKDTree
    kd = cKDTree(densify_pts(b_line, step))
    d, _ = kd.query(a_pts)
    return d


def stats(d):
    return {"median_m": rnd(np.median(d)), "p90_m": rnd(np.percentile(d, 90)), "p95_m": rnd(np.percentile(d, 95)), "max_m": rnd(d.max())}


def icp(src, tgt_line, init, iters=60):
    """Similarity fit (scale, rotation, translation) of points src onto a line, starting from translation init."""
    from scipy.spatial import cKDTree
    tgt = densify_pts(tgt_line, 10.0)
    kd = cKDTree(tgt)
    A = np.eye(2); s = 1.0; t = np.array(init, float)
    for _ in range(iters):
        P = (src @ A.T) * s + t
        d, idx = kd.query(P)
        m = d < max(50.0, np.percentile(d, 80))
        X = src[m]; Y = tgt[idx[m]]
        mx = X.mean(0); my = Y.mean(0); Xc = X - mx; Yc = Y - my
        U, S, Vt = np.linalg.svd(Xc.T @ Yc)
        R = (U @ Vt).T
        if np.linalg.det(R) < 0:
            Vt[-1] *= -1; R = (U @ Vt).T
        s = S.sum() / (Xc ** 2).sum(); A = R; t = my - s * (mx @ R.T)
    P = (src @ A.T) * s + t
    d, _ = kd.query(P)
    return {"scale": round(float(s), 6), "rotation_deg": round(float(np.degrees(np.arctan2(A[1, 0], A[0, 0]))), 4),
            "dx": rnd(t[0], 2), "dz": rnd(t[1], 2), "residual": stats(d)}


# ====================================================================== 1. genplan geojson → Unity frame
def convert_genplan():
    gp = twin.genplan_unity()
    out = {}
    allg, allp = [], []
    for name, (g, p) in gp.items():
        props = {"name": name, "kind": p.get("kind"), "source": "alatau_plan_utm43n_rel.geojson (макет, rel → Unity: X = x − 517.314, Z = y + 7350.528)"}
        if g.area > 0:
            props["area_ha"] = rnd(g.area / 1e4)
        if g.length > 0 and g.area == 0:
            props["len_km"] = rnd(g.length / 1000, 2)
        safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name)
        path, size = layers.write("genplan/" + safe, [g], [props])
        out[name] = {"file": os.path.relpath(path, frames.OUT), "kind": p.get("kind"), "geom": g.geom_type, "bytes": size,
                     **({"area_ha": props["area_ha"]} if "area_ha" in props else {}), **({"len_km": props["len_km"]} if "len_km" in props else {})}
        allg.append(g); allp.append(props)
    path, size = layers.write("genplan/genplan_unity", allg, allp)
    print(f"[genplan] {len(allg)} layers → {path} ({size / 1e6:.2f} MB)")
    return gp, out


# ====================================================================== 2. proof of the transform
def proof(gp, D, raw):
    B = twin.buildings()
    origin = frames.maket_origin()
    off = frames.rel_offset()
    res = {"transform": {"rel_to_unity": f"X = x_rel + ({origin[0]:.3f} − 663000) = x_rel {off[0]:+.3f}; Z = y_rel + ({origin[1]:.3f} − 4830000) = y_rel {off[1]:+.3f}",
                         "origin_utm43n": list(origin), "dx": round(off[0], 3), "dz": round(off[1], 3),
                         "why": "geojson хранит свой origin_utm43n (центроид контура города в UTM 43N); Unity = UTM − (663000, 4830000). "
                                "Это чистый сдвиг: без поворота и масштаба (см. ICP ниже)."}}
    # areas and building shares
    rows = []
    for k in twin.DISTRICTS:
        g = gp[k.lower()][0]; t = D[k]; r = raw[k]
        sub = B[B.district == k]
        in_t = shapely.contains_xy(t, sub.x.values, sub.z.values)
        in_g = shapely.contains_xy(g, sub.x.values, sub.z.values)
        code = twin.DISTRICT_AREA_HA_CODE[k]
        rows.append({"district": k, "area_code_ha": code,
                     "area_genplan_geojson_ha": rnd(g.area / 1e4), "diff_geojson_pct": rnd((g.area / 1e4 / code - 1) * 100, 2),
                     "area_twin_outline_ha": rnd(t.area / 1e4), "diff_twin_pct": rnd((t.area / 1e4 / code - 1) * 100, 2),
                     "area_twin_outline_raw_ha": rnd(r.area / 1e4),
                     "symdiff_geojson_vs_twin_ha": rnd(g.symmetric_difference(t).area / 1e4),
                     "buildings": int(len(sub)),
                     "share_in_geojson_pct": rnd(in_g.mean() * 100, 2), "share_in_twin_outline_pct": rnd(in_t.mean() * 100, 2),
                     "outside_twin_outline": int((~in_t).sum()), "outside_geojson": int((~in_g).sum())})
    res["districts"] = rows
    # outer outline: twin (QTwin layer) vs genplan geojson city, and the real OSM boundary (Overture) vs both
    city_t = twin.city_outline(D)
    city_g = gp["city"][0]
    d1 = nn_dist(densify_pts(city_g.exterior, 20), city_t.exterior)
    d2 = nn_dist(densify_pts(city_t.exterior, 20), city_g.exterior)
    raw_city = twin.genplan_raw()["city"][0]
    res["city_outline"] = {
        "area_twin_ha": rnd(city_t.area / 1e4), "area_geojson_ha": rnd(city_g.area / 1e4), "symdiff_ha": rnd(city_t.symmetric_difference(city_g).area / 1e4),
        "geojson_to_twin": stats(d1), "twin_to_geojson": stats(d2),
        "icp_geojson_rel_onto_twin": icp(densify_pts(raw_city.exterior, 20), city_t.exterior, off),
        "note": "ICP: свободная подгонка (масштаб, поворот, сдвиг) контура города из geojson к контуру районов двойника; стартует со сдвига origin."}
    try:
        gd, pd_ = layers.load("divisions")
        alatau = [g for g, p in zip(gd, pd_) if p.get("subtype") == "county" and p.get("name") == "Алатау"]
        if alatau:
            a = max(alatau, key=lambda g: g.area)
            if a.geom_type == "MultiPolygon":
                a = max(a.geoms, key=lambda q: q.area)
            d3 = nn_dist(densify_pts(a.exterior, 20), city_g.exterior)
            d4 = nn_dist(densify_pts(a.exterior, 20), city_t.exterior)
            res["osm_boundary"] = {"what": "граница г. Алатау из OSM (Overture divisions, county «Алатау»), lon/lat → UTM 43N (pyproj) → Unity",
                                   "source": OVT, "area_ha": rnd(a.area / 1e4),
                                   "centroid": [rnd(a.centroid.x), rnd(a.centroid.y)],
                                   "osm_to_geojson": stats(d3), "osm_to_twin": stats(d4),
                                   "icp_geojson_rel_onto_osm": icp(densify_pts(raw_city.exterior, 20), a.exterior, off)}
    except FileNotFoundError:
        res["osm_boundary"] = "not found (run fetch_overture.py first)"
    # Gate alone
    gg, gt = gp["gate"][0], D["Gate"]
    res["gate"] = {"hausdorff_m": rnd(gg.exterior.hausdorff_distance(gt.exterior)),
                   "median_m": rnd(np.median(nn_dist(densify_pts(gg.exterior, 20), gt.exterior))),
                   "symdiff_ha": rnd(gg.symmetric_difference(gt).area / 1e4)}
    # where the twin's existing buildings of Gate sit relative to the unshifted file (the "7.4 km" of the brief)
    gate_b = B[(B.district == "Gate")]
    graw = twin.genplan_raw()["gate"][0]
    res["unshifted_check"] = {"share_of_gate_buildings_in_unshifted_gate_pct": rnd(shapely.contains_xy(graw, gate_b.x.values, gate_b.z.values).mean() * 100, 2),
                              "share_after_shift_pct": rnd(shapely.contains_xy(gg, gate_b.x.values, gate_b.z.values).mean() * 100, 2)}
    res["verdict"] = ("Сдвиг доказан: внешний контур города из geojson ложится на контур районов двойника (медиана 12–14 м, это шаг оцифровки) и на "
                      "границу Алатау из OSM; ICP без ограничений даёт масштаб ≈ 1 и поворот ≈ 0. Площади районов geojson совпадают с кодом "
                      "(Gate, Golden, Green точно, Growing +1,0 %). Но внутренние границы Golden/Growing/Green в geojson — прямые разрезы "
                      "«approx., areas matched to alatau.city» (подпись Alatau_districts_map.png), а двойник раскладывает здания по своим "
                      "границам из модели QTwin (layer_infrastructure.bytes, «… District boundary»). Поэтому в city.json районы взяты из "
                      "двойника (площади в пределах 0,35 % от кода, 99,98–100 % зданий внутри), а полигоны geojson лежат рядом как альтернатива.")
    return res


# ====================================================================== 3. Growing split
def growing_split(D):
    import networkx as nx
    R = twin.roads()
    nodes = np.array(R["nodes"], float)
    Gr = D["Growing"]
    south = Gr.boundary.intersection(D["Golden"].buffer(3))
    north = Gr.boundary.intersection(D["Green"].buffer(3))
    G = nx.Graph()
    geo = {}
    zone = Gr.buffer(800)
    for i, e in enumerate(R["edges"]):
        if e["c"] not in ("highway", "main", "ring"):
            continue
        g = e["g"]; ls = LineString(list(zip(g[0::2], g[1::2])))
        if not ls.intersects(zone):
            continue
        xm = abs(ls.interpolate(0.5, normalized=True).x)
        w = ls.length * (1.0 + xm / 2000.0)
        if G.has_edge(e["a"], e["b"]) and G[e["a"]][e["b"]]["w"] <= w:
            continue
        G.add_edge(e["a"], e["b"], w=w, i=i, c=e["c"])
        geo[i] = ls
    # an arterial reaches a boundary where one of its edges crosses it: take the end of that edge outside Growing
    srcs, tgts = [], set()
    inner = Gr.buffer(-1)
    for a_, b_, d_ in G.edges(data=True):
        ls = geo[d_["i"]]
        for bnd, acc in ((south, "s"), (north, "n")):
            if ls.intersects(bnd):
                for n_ in (a_, b_):
                    if not inner.contains(Point(nodes[n_])):
                        (srcs.append(n_) if acc == "s" else tgts.add(n_))
    if not srcs or not tgts:
        raise RuntimeError("Growing split: no arterial reaches both the south and the north boundary")
    best = None
    for s in srcs:
        try:
            dist, paths = nx.single_source_dijkstra(G, s, weight="w")
        except nx.NetworkXNoPath:
            continue
        for t in tgts:
            if t in dist and (best is None or dist[t] < best[0]):
                best = (dist[t], paths[t])
    path = best[1]
    pts = []
    eids = []
    classes = Counter()
    for a, b in zip(path[:-1], path[1:]):
        i = G[a][b]["i"]; eids.append(i); classes[G[a][b]["c"]] += geo[i].length
        c = list(geo[i].coords)
        if np.hypot(*(np.array(c[0]) - nodes[a])) > np.hypot(*(np.array(c[-1]) - nodes[a])):
            c = c[::-1]
        pts.extend(c if not pts else c[1:])
    line = LineString(pts)
    inside = line.intersection(Gr)
    xs = np.array([p[0] for p in pts]); zs = np.array([p[1] for p in pts])
    m = shapely.contains_xy(Gr, xs, zs)
    # extend both ends 3 km so the line cuts the polygon cleanly
    P = np.array(pts)
    d0 = P[0] - P[min(5, len(P) - 1)]; d0 /= np.linalg.norm(d0)
    d1 = P[-1] - P[max(-6, -len(P))]; d1 /= np.linalg.norm(d1)
    cut = LineString([tuple(P[0] + d0 * 3000)] + [tuple(p) for p in P] + [tuple(P[-1] + d1 * 3000)])
    pieces = list(split(Gr, cut).geoms)
    W, E = [], []
    for pc in pieces:
        rp = pc.representative_point()
        s = cut.project(rp)
        a = cut.interpolate(max(0, s - 5)); b = cut.interpolate(min(cut.length, s + 5))
        cross = (b.x - a.x) * (rp.y - a.y) - (b.y - a.y) * (rp.x - a.x)     # > 0: left of the line going north = west
        (W if cross > 0 else E).append(pc)
    gw = unary_union(W); ge = unary_union(E)
    # the Overture name of the road under the line
    refs = Counter(); names = Counter()
    try:
        rg, rp_ = layers.load("roads")
        buf = inside.buffer(40)
        shapely.prepare(buf)
        hit = shapely.intersects(buf, rg)
        for g, p in zip(rg[hit], [rp_[i] for i in np.flatnonzero(hit)]):
            if p.get("class") in ("motorway", "trunk", "primary"):
                L = g.intersection(buf).length
                for r in p.get("ref") or []:
                    refs[r] += L
                if p.get("name"):
                    names[p["name"]] += L
    except FileNotFoundError:
        pass
    xin = np.array([c[0] for c in densify_pts(inside if inside.geom_type == "LineString" else linemerge(inside), 50)]) if not inside.is_empty else xs
    return {
        "line": line, "inside": inside, "growing_w": gw, "growing_e": ge, "edges": eids,
        "classes_km": {k: rnd(v / 1000, 2) for k, v in classes.items()},
        "refs": [r for r, _ in refs.most_common(4)], "names": [n for n, _ in names.most_common(3)],
        "mean_abs_x": rnd(np.mean(np.abs(xin))), "x_range": [rnd(xin.min()), rnd(xin.max())],
        "len_in_growing_km": rnd(inside.length / 1000, 2), "share_points_inside": rnd(m.mean(), 3),
    }


# ====================================================================== 4. water
WATER_GROUPS = [
    ("kapchagay", "Капшагайское водохранилище", "reservoir", ["Қапшағай су қоймасы"], "kapchagay"),
    ("ili", "р. Или (Іле)", "river", ["Іле", "Или"], "Ili_river_Kazakhstan"),
    ("kaskelen", "р. Каскелен (Қаскелең)", "river", ["Қаскелең", "Каскелен"], "kaskelen"),
    ("malaya_almatinka", "р. Малая Алматинка (Кіші Алматы)", "river", ["Кіші Алматы", "Малая Алматинка"], "malaya_almatinka"),
    ("bak", "Большой Алматинский канал (БАК)", "canal", ["Үлкен Алматы каналы", "Большой Алматинский канал", "БАК", "Большой Алматинский Канал имени Д.А.Кунаева"], "Большой_Алматинский_канал"),
    ("yesentai", "р. Есентай", "river", ["Есентай", "Правый Есентай"], "Есентай"),
    ("bolshaya_almatinka", "р. Большая Алматинка (Үлкен Алматы)", "river", ["Үлкен Алматы"], None),
    ("sorbulak_canal", "Сорбулакский канал", "canal", ["Оң жағалау Сорбұлақ каналы", "Сорбулакский канал"], None),
    ("terenkara", "р. Теренкара", "river", ["Тереңқара", "Теренкара", "Төменгі Тереңқара"], None),
    ("kurozek", "р. Курозек", "river", ["Курозек", "р.Курозек"], None),
    ("kutentai", "р. Кутентай", "river", ["Кутентай", "р.Кутентай"], None),
    ("saztalgar", "р. Сазталгар", "river", ["Сазталғар", "Сазталғар тоғандары"], None),
    ("karasu", "Карасу (несколько русел)", "river", ["Карасу", "Қарасу", "Карасу-Байсерке", "Қарасу-Түрксіб", "Сұлтанқарасу", "Басқарасу", "Бестерек-Карасу"], None),
]


def kapchagay_levels(D):
    """Wet area of the reservoir rising to a real mark L (FloodModel: priority flood from the 475 m twin water cells, real = twin + 2 m)."""
    import heapq
    T = terrain.terrain()
    h = T.h
    ny, nx = h.shape
    F = np.full(h.shape, np.inf)
    seed = np.abs(h - 475.0) < 0.02
    cap = 492.0
    heap = [(float(h[r, c]), int(r), int(c)) for r, c in zip(*np.nonzero(seed))]
    for v, r, c in heap:
        F[r, c] = v
    heapq.heapify(heap)
    while heap:
        k, r, c = heapq.heappop(heap)
        if k > F[r, c]:
            continue
        for rr, cc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if 0 <= rr < ny and 0 <= cc < nx:
                hh = h[rr, cc]
                if hh >= cap:
                    continue
                nk = max(k, hh)
                if nk < F[rr, cc]:
                    F[rr, cc] = nk
                    heapq.heappush(heap, (nk, rr, cc))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    xs = T.x0 + np.arange(nx) * T.step
    zs = T.z0 + np.arange(ny) * T.step
    Fv = np.where(np.isfinite(F), F, 999.0)
    city = twin.city_outline(D)
    levels = [477.0, 479.0, 481.0, 483.0, 485.0]
    out = []
    for L in levels:
        cs = plt.contourf(xs, zs, Fv, levels=[0, L - 2.0 + 1e-3])
        polys = []
        for path in cs.get_paths():
            for poly in path.to_polygons():
                if len(poly) >= 4:
                    polys.append(Polygon(poly))
        plt.close("all")
        # even-odd: holes come as separate rings → build by symmetric difference
        g = Polygon()
        for p in sorted(polys, key=lambda p: -abs(p.area)):
            p = p.buffer(0)
            g = g.symmetric_difference(p)
        g = g.buffer(0)
        out.append((L, g))
    base = out[0][1]
    res = []
    for L, g in out:
        land = g.difference(base).intersection(city)
        res.append({"real_m": L, "twin_m": L - 2.0, "wet_km2_total": rnd(g.area / 1e6, 1), "city_land_flooded_ha": rnd(land.area / 1e4),
                    "by_district_ha": {k: rnd(land.intersection(D[k]).area / 1e4) for k in twin.DISTRICTS if land.intersects(D[k])}, "geom": g})
    return res


def water(D, gp):
    wg, wp = layers.load("water")
    city = twin.city_outline(D)
    region = twin.clip_region(5000)
    feats, fprops, rows = [], [], []
    used = set()
    raw = None
    for wid, title, kind, names, gname in WATER_GROUPS:
        idx = [i for i, p in enumerate(wp) if (p.get("name") or "") in names]
        geo_note = None
        src_g, src_p = wg, wp
        if not idx:
            # not within city + 5 km: look in the whole Overture box (raw download) and say how far it is
            if raw is None:
                import pyarrow.parquet as pq
                t = pq.read_table(src_path("overture_raw", "water.parquet")).to_pandas()
                rg_ = frames.geom_lonlat_to_unity(shapely.from_wkb(t.geometry.values))
                raw = (rg_, [{"id": t.id[i], "name": t.name[i] if isinstance(t.name[i], str) else None, "subtype": t.subtype[i]} for i in range(len(t))])
            ridx = [i for i, p in enumerate(raw[1]) if (p.get("name") or "") in names]
            if ridx:
                src_g, src_p = raw
                idx = ridx
                far = unary_union([raw[0][i] for i in ridx])
                geo_note = f"вне области город + 5 км: ближайшая точка в {far.distance(city) / 1000:.1f} км от границы города; взят из всей выборки Overture (bbox)"
        if src_g is wg:
            for i in idx:
                used.add(i)
        if not idx:
            rows.append({"id": wid, "name": title, "kind": kind, "found": False,
                         "note": "не найден в Overture в пределах город + 5 км" + ("; есть линия в geojson генплана" if gname else "")})
            continue
        geoms = [src_g[i] for i in idx]
        lines = [g for g in geoms if g.geom_type in ("LineString", "MultiLineString")]
        polys = [g for g in geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        L = unary_union(lines) if lines else None
        A = unary_union(polys) if polys else None
        row = {"id": wid, "name": title, "kind": kind, "found": True, "osm_names": sorted(set(src_p[i].get("name") or "—" for i in idx)),
               "features": len(idx), "source": OVT, "layer": ("osm/water.geojson" if src_g is wg else "overture_raw/water.parquet") + " (id в derived/water_main.geojson)"}
        if geo_note:
            row["note"] = geo_note
        tag = "city5km" if src_g is wg else "bbox"
        if L is not None:
            row["len_km_" + tag] = rnd(L.length / 1000, 1)
            row["len_km_in_city"] = rnd(L.intersection(city).length / 1000, 1)
            row["districts"] = [k for k in twin.DISTRICTS if L.intersects(D[k])]
        if A is not None:
            row["area_ha_" + tag] = rnd(A.area / 1e4)
            row["area_ha_in_city"] = rnd(A.intersection(city).area / 1e4)
            row.setdefault("districts", [k for k in twin.DISTRICTS if A.intersects(D[k])])
        if gname and gname in gp:
            gl = gp[gname][0]
            ref = L if L is not None else (A.boundary if A is not None else None)
            cmp_region = region if src_g is wg else ref.envelope.buffer(100)
            gl_c = (gl.boundary if gl.area > 0 else gl).intersection(cmp_region)
            if ref is not None and not gl_c.is_empty:
                pts = np.vstack([densify_pts(q, 50) for q in getattr(gl_c, "geoms", [gl_c]) if q.length > 100])
                d = shapely.distance(shapely.points(pts), ref)
                row["genplan_vs_osm"] = {"genplan_layer": gname, "what": "расстояние от линии генплана (после сдвига) до объекта OSM", **stats(d)}
        rows.append(row)
        g = unary_union([x for x in (L, A) if x is not None])
        if A is not None:
            row["shore_km_city5km"] = rnd(A.boundary.intersection(region).length / 1000, 1)
        feats.append(g); fprops.append({"id": wid, "name": title, "kind": kind, "source": OVT, "osm_ids": [src_p[i]["id"] for i in idx]})
    # other named water ≥ 3 km or ≥ 10 ha
    agg = defaultdict(list)
    for i, p in enumerate(wp):
        if i in used or not p.get("name"):
            continue
        agg[p["name"]].append(i)
    others = []
    for n, idx in agg.items():
        g = unary_union([wg[i] for i in idx])
        Lk = g.length / 1000 if g.geom_type.endswith("LineString") else 0
        Ah = g.area / 1e4
        if Lk >= 3 or Ah >= 10:
            others.append({"name": n, "subtypes": sorted(set(wp[i].get("subtype") or "" for i in idx)), "len_km": rnd(Lk, 1), "area_ha": rnd(Ah),
                           "in_city": bool(g.intersects(city)), "c": [rnd(g.centroid.x, 0), rnd(g.centroid.y, 0)]})
    others.sort(key=lambda r: -(r["len_km"] + r["area_ha"] / 50))
    layers.write("derived/water_main", feats, fprops, {"source": OVT})
    return rows, others


# ====================================================================== 5. existing (2025) network, settlements
def existing(D):
    city = twin.city_outline(D)
    shapely.prepare(city)
    res = {}
    rg, rp = layers.load("roads")
    inside = shapely.intersects(city, rg)
    km = Counter(); kmd = defaultdict(Counter); bridges = 0; tunnels = 0; refs = Counter()
    for g, p in zip(rg[inside], [rp[i] for i in np.flatnonzero(inside)]):
        gi = g.intersection(city)
        c = p.get("class", "unknown")
        km[c] += gi.length / 1000
        for k in twin.DISTRICTS:
            if gi.intersects(D[k]):
                kmd[k][c] += gi.intersection(D[k]).length / 1000
        bridges += bool(p.get("bridge")); tunnels += bool(p.get("tunnel"))
        for r in p.get("ref") or []:
            refs[r] += gi.length / 1000
    res["roads"] = {"source": OVT, "layer": "osm/roads.geojson", "connectors": "osm/connectors.geojson", "year": 2025,
                    "km_in_city_by_class": {k: rnd(v, 1) for k, v in km.most_common()},
                    "km_by_district": {k: {c: rnd(v, 1) for c, v in kmd[k].most_common()} for k in twin.DISTRICTS},
                    "bridge_segments": int(bridges), "tunnel_segments": int(tunnels),
                    "routes_km_in_city": {k: rnd(v, 1) for k, v in refs.most_common(12)},
                    "note": "KAZ08 = трасса А-3 Алматы – Капшагай (E40/AH60); BAKAD = БАКАД; KZ05-10, KZ05-03 — областные дороги"}
    # rail
    rl, rlp = layers.load("rail")
    rin = shapely.intersects(city, rl)
    rkm = sum(g.intersection(city).length for g in rl[rin]) / 1000
    ig, ip = layers.load("infrastructure")
    stations = [{"name": p.get("name"), "x": rnd(g.x, 0), "z": rnd(g.y, 0), "in_city": bool(city.contains(g))}
                for g, p in zip(ig, ip) if p.get("class") == "railway_station" and g.geom_type == "Point"]
    res["rail"] = {"source": OVT, "layer": "osm/rail.geojson", "km_in_city": rnd(rkm, 1), "segments_in_city": int(rin.sum()),
                   "bridge_segments": int(sum(1 for i in np.flatnonzero(rin) if rlp[i].get("bridge"))),
                   "stations": stations}
    # power
    pl = [(g, p) for g, p in zip(ig, ip) if p.get("subtype") == "power"]
    lines_km = Counter(); towers = Counter(); subs = []
    for g, p in pl:
        c = p.get("class")
        if c in ("power_line", "minor_line", "cable"):
            lines_km[c] += g.intersection(city).length / 1000
        elif c in ("power_tower", "power_pole"):
            towers[c] += int(city.contains(g))
        elif c in ("substation", "plant", "generator") and g.geom_type != "Point":
            subs.append({"class": c, "name": p.get("name"), "x": rnd(g.centroid.x, 0), "z": rnd(g.centroid.y, 0),
                         "area_m2": rnd(g.area, 0), "in_city": bool(city.intersects(g))})
    res["power"] = {"source": OVT, "layer": "osm/infrastructure.geojson (subtype power)", "lines_km_in_city": {k: rnd(v, 1) for k, v in lines_km.items()},
                    "towers_poles_in_city": dict(towers), "substations_plants": sorted(subs, key=lambda s: (not s["in_city"], -(s["area_m2"] or 0)))}
    bridges_l = [(g, p) for g, p in zip(ig, ip) if p.get("subtype") == "bridge"]
    res["bridges"] = {"source": OVT, "layer": "osm/infrastructure.geojson (subtype bridge) + bridge=true в osm/roads.geojson",
                      "infra_bridges_in_city": int(sum(1 for g, p in bridges_l if city.intersects(g)))}
    return res


def settlements(D):
    city = twin.city_outline(D)
    region = twin.clip_region(5000)
    dg, dp = layers.load("divisions")
    pg, pp = layers.load("division_points")
    bg, bp = layers.load("buildings")
    bc = shapely.centroid(bg)
    bx, bz = shapely.get_x(bc), shapely.get_y(bc)
    B = twin.buildings()
    ex = B[B.source == "existing_osm"]
    keep = []
    loc = [(g, p) for g, p in zip(dg, dp) if p.get("subtype") == "locality"]
    small = [(g, p) for g, p in zip(dg, dp) if p.get("subtype") in ("neighborhood", "macrohood", "microhood")]
    cand = list(loc)
    for g, p in small:
        if not any(g.representative_point().within(l) for l, _ in loc):
            cand.append((g, p))
    have = set(p.get("name") for _, p in cand)
    # localities that Overture has only as points: outline from the cluster of buildings round the point (model)
    from shapely import STRtree
    tree = STRtree(bg)
    for g, p in zip(pg, pp):
        if p.get("subtype") not in ("locality", "microhood", "neighborhood", "macrohood") or p.get("name") in have or not region.contains(g):
            continue
        if any(g.within(a) for a, _ in cand if a.area >= 1e4):
            continue
        idx = tree.query(g.buffer(1500))
        if len(idx) < 10:
            continue
        u = unary_union([bg[i].buffer(40) for i in idx])
        parts = list(getattr(u, "geoms", [u]))
        part = min(parts, key=lambda q: q.distance(g))
        if part.distance(g) > 400:
            continue
        hull = part.buffer(-25).simplify(10)
        if hull.is_empty:
            continue
        if hull.geom_type == "MultiPolygon":
            hull = max(hull.geoms, key=lambda q: q.area)
        cand.append((hull, {**p, "_model": True}))
        have.add(p.get("name"))
    for g, p in cand:
        if not g.intersects(region) or g.area < 1e4:
            continue
        shapely.prepare(g)
        nb = int(shapely.contains_xy(g, bx, bz).sum())
        nt = int(shapely.contains_xy(g, ex.x.values, ex.z.values).sum())
        share = g.intersection(city).area / g.area if g.area else 0
        dist = max(twin.DISTRICTS, key=lambda k: g.intersection(D[k]).area)
        pop = None
        for q, qp in zip(pg, pp):
            if qp.get("name") == p.get("name") and qp.get("population"):
                pop = qp["population"]
        keep.append({"name": p.get("name"), "subtype": p.get("subtype"), "area_ha": rnd(g.area / 1e4),
                     "share_in_city": rnd(share, 2), "district": dist if share > 0.05 else None,
                     "overture_buildings": nb, "twin_existing_buildings": nt, "population_osm": pop,
                     "polygon_source": "модель qTwin: контур по зданиям вокруг точки OSM (буфер 40 м, −25 м)" if p.get("_model") else OVT + ", divisions/division_area",
                     "id": p.get("id"), "_g": g})
    keep.sort(key=lambda r: (-r["share_in_city"], -r["overture_buildings"]))
    feats = [r.pop("_g") for r in keep]
    for r, g in zip(keep, feats):
        r["c"] = [rnd(g.representative_point().x, 0), rnd(g.representative_point().y, 0)]
    layers.write("derived/settlements", feats, [dict(r) for r in keep], {"source": OVT})
    return keep, feats


# ====================================================================== 6. trunk v0 and LRT v0 from the twin
# pieces of the twin's trunk that draw a road twice (level 1, w42): the joints on them move to the real road
TRUNK_DUPLICATES = {"T-R002": "БАКАД (Overture «ҮАААЖ», ref KZ02-01): двойник рисует кольцо второй раз в 0,2–2,2 км от настоящей трассы; "
                              "настоящая БАКАД в двойнике — куски T-H030/T-H031 и др. (класс highway)"}
BAKAD_REF = "KZ02-01"
def trunk_v0():
    R = twin.roads()
    groups = defaultdict(list)
    for i, e in enumerate(R["edges"]):
        if e["c"] in ("highway", "ring", "main"):
            groups[(e["c"], tuple(e["y"]))].append(i)
    feats, props = [], []
    order = {"highway": 0, "ring": 1, "main": 2}
    n = Counter()
    for (c, y), ids in sorted(groups.items(), key=lambda kv: (order[kv[0][0]], kv[0][1])):
        lines = [LineString(list(zip(R["edges"][i]["g"][0::2], R["edges"][i]["g"][1::2]))) for i in ids]
        m = linemerge(lines)
        parts = list(getattr(m, "geoms", [m]))
        parts.sort(key=lambda q: -q.length)
        tree = shapely.STRtree(parts)
        mids = shapely.points([l.interpolate(0.5, normalized=True).coords[0] for l in lines])
        near = tree.query_nearest(mids, all_matches=False)
        owner = defaultdict(list)
        for li, pi in zip(near[0], near[1]):
            owner[int(pi)].append(ids[int(li)])
        for pi, q in enumerate(parts):
            n[c] += 1
            fid = f"T-{c[0].upper()}{n[c]:03d}"
            eids = sorted(owner[pi])
            feats.append(q)
            props.append({"id": fid, "class": c, "years": list(y), "len_km": rnd(q.length / 1000, 2), "edges": eids,
                          "draft": True, "source": "двойник: StreamingAssets/twin/roads.json (оси генплана QTwin + трассы OSM), годы по сценариям base/fast/slow/infra"})
            if fid in TRUNK_DUPLICATES:
                props[-1]["duplicate_of"] = TRUNK_DUPLICATES[fid]
    layers.write("derived/trunk_v0", feats, props, {"draft": True})
    km = Counter(); kmy = Counter()
    for p in props:
        km[p["class"]] += p["len_km"]; kmy[(p["class"], p["years"][0])] += p["len_km"]
    return feats, props, {"km_by_class": {k: rnd(v, 1) for k, v in km.items()},
                          "km_by_class_year_base": {f"{c} {y}": rnd(v, 1) for (c, y), v in sorted(kmy.items())}}


def lrt_v0():
    lr = twin.lrt_routes()
    cl = twin.construction_lrt()
    feats, props = [], []
    routes = []
    for r in lr["routes"]:
        p = r["pts"]
        ls = LineString(list(zip(p[0::2], p[1::2])))
        feats.append(ls)
        props.append({"id": "LRT-" + r["name"], "name": r["name"], "kind": "route", "len_km": rnd(ls.length / 1000, 2), "draft": True,
                      "source": "двойник: Resources/Landmarks/lrt_routes.json"})
        routes.append((r["name"], ls))
    stations = []
    for k, s in enumerate(cl["stations"]):
        x, z, ph = s
        pt = Point(x, z)
        rn, d = min(((n, l.distance(pt)) for n, l in routes), key=lambda t: t[1])
        stations.append({"id": f"S{k + 1:02d}", "x": x, "z": z, "phase": ph, "phase_name": cl["phase_names"][ph], "route": rn, "dist_to_route_m": rnd(d),
                         "name": None})
        feats.append(pt); props.append({"id": f"S{k + 1:02d}", "kind": "station", "phase": ph, "route": rn, "draft": True,
                                        "source": "двойник: construction.json → lrt.stations (через ~1,6 км, gen_twin.py)"})
    for s in lr.get("stations", []):
        pt = Point(s["x"], s["z"])
        rn, d = min(((n, l.distance(pt)) for n, l in routes), key=lambda t: t[1])
        stations.append({"id": "S-" + s["name"], "x": s["x"], "z": s["z"], "phase": s["phase"], "phase_name": cl["phase_names"][s["phase"]],
                         "route": rn, "dist_to_route_m": rnd(d), "name": s["name"]})
        feats.append(pt); props.append({"id": "S-" + s["name"], "kind": "station", "name": s["name"], "phase": s["phase"], "route": rn, "draft": True,
                                        "source": "двойник: lrt_routes.json → stations"})
    layers.write("derived/lrt_v0", feats, props, {"draft": True})
    return routes, stations, cl


# ====================================================================== 7. joints
def joints(areas, lines):
    """areas: {name: Polygon}; lines: [(kind, id, class, years, LineString)]. Crossing points of the lines with area boundaries."""
    names = list(areas)
    city = unary_union(list(areas.values()))
    def where(x, z):
        for n in names:
            if shapely.contains_xy(areas[n], x, z):
                return n
        return "outside"
    bnd = unary_union([outline_of(a) for a in areas.values()])
    bnd_buf = bnd.buffer(4)
    out = []
    for kind, lid, cls, years, ln in lines:
        X = ln.intersection(bnd)
        pts = []
        for g in getattr(X, "geoms", [X]):
            if g.is_empty:
                continue
            if g.geom_type == "Point":
                pts.append(g)
            elif g.geom_type in ("LineString", "MultiLineString"):
                for q in getattr(g, "geoms", [g]):
                    pts.extend([Point(q.coords[0]), Point(q.coords[-1])])
        for p in pts:
            s = ln.project(p)
            local = substring(ln, max(0.0, s - 40), min(ln.length, s + 40))
            if local.intersection(bnd_buf).length > 30:      # the line runs along the boundary here (the split line is the A-3 itself)
                continue
            a = ln.interpolate(max(0.0, s - 12)); b = ln.interpolate(min(ln.length, s + 12))
            wa, wb = where(a.x, a.y), where(b.x, b.y)
            if wa == wb:
                continue
            pair = sorted([wa, wb])
            out.append({"x": rnd(p.x, 1), "z": rnd(p.y, 1), "kind": kind, "line": lid, "class": cls, "between": pair, "years": years})
    # dedupe (the same crossing lies on two outlines)
    ded = []
    for j in out:
        if any(abs(j["x"] - k["x"]) < 15 and abs(j["z"] - k["z"]) < 15 and j["line"] == k["line"] for k in ded):
            continue
        ded.append(j)
    ded.sort(key=lambda j: (j["between"], j["kind"], -j["z"], j["x"]))
    for i, j in enumerate(ded):
        j["id"] = f"J{i + 1:03d}"
    return ded


def rebuild_joints(J0, lines, areas, city, notches):
    """Level 1 (w42). J0: the level-0 joints (ids). Returns (joints, report): crossings of the twin trunk (without the duplicate
    ring) and the OSM rail with the level-1 borders, robust (a real district or the outside on each side), the level-0 id kept
    where the same line still crosses within 30 m; joints of the duplicate ring moved to the Overture BAKAD; LRT joints from the
    five schemes' LRT lines (lrt_v0 is superseded); then every scheme axis crossing meets a joint within 150 m or makes one."""
    city_ext = city.exterior
    specs = city_l1.load_specs()
    old_by = {j["id"]: j for j in J0}
    lines1 = [l for l in lines if l[1] not in TRUNK_DUPLICATES]
    cross, dropped = city_l1.crossings_of_lines(lines1, areas, city_ext)
    n2o, dup = city_l1.match_old(cross, [j for j in J0 if j["kind"] != "lrt" and j["line"] not in TRUNK_DUPLICATES])
    out = []
    for i, c in enumerate(cross):
        j = {"id": n2o.get(i), "x": rnd(c["p"].x), "z": rnd(c["p"].y), "kind": c["kind"], "line": c["lines"][0], "class": c["class"],
             "between": c["between"], "years": c["years"], "source": "trunk_v0" if c["kind"] == "road" else "osm_rail"}
        if len(c["lines"]) > 1:
            j["lines"] = c["lines"]
        out.append(j)
    # the duplicate BAKAD ring of the twin: its joints move to where the Overture BAKAD (both carriageways) crosses the border
    rg, rp = layers.load("roads")
    bk = [("road", p["id"], "ring", [2025] * 4, q) for g, p in zip(rg, rp) if BAKAD_REF in (p.get("ref") or []) for q in getattr(g, "geoms", [g])]
    bk_cross, _ = city_l1.crossings_of_lines(bk, areas, city_ext)
    moved = []
    for o in J0:
        if o["line"] not in TRUNK_DUPLICATES:
            continue
        cands = [c for c in bk_cross if c["between"] == o["between"]]
        if not cands:
            continue
        c = min(cands, key=lambda c: c["p"].distance(Point(o["x"], o["z"])))
        grp = [d for d in cands if d["p"].distance(c["p"]) <= 80.0]
        x = float(np.mean([d["p"].x for d in grp])); z = float(np.mean([d["p"].y for d in grp]))
        dm = math.hypot(x - o["x"], z - o["z"])
        out.append({"id": o["id"], "x": rnd(x), "z": rnd(z), "kind": "road", "line": "osm:" + c["lines"][0],
                    "lines": sorted(set("osm:" + l for d in grp for l in d["lines"])), "class": "ring", "between": o["between"],
                    "years": [2025] * 4, "source": "osm_bakad",
                    "level0": {"x": o["x"], "z": o["z"], "line": o["line"], "between": o["between"], "moved_m": rnd(dm)},
                    "note_ru": "перенесён с дубля кольца двойника %s на настоящую БАКАД (Overture «ҮАААЖ», %s): середина %d пересечений проезжих частей с границей"
                               % (o["line"], BAKAD_REF, len(grp))})
        moved.append({"id": o["id"], "from": [o["x"], o["z"]], "to": [rnd(x), rnd(z)], "moved_m": rnd(dm), "carriageways": len(grp)})
    for j in out:
        if j["id"] and j["source"] != "osm_bakad":
            o = old_by[j["id"]]
            if math.hypot(o["x"] - j["x"], o["z"] - j["z"]) > 1.0 or o["between"] != j["between"]:
                j["level0"] = {"x": o["x"], "z": o["z"], "between": o["between"]}
    # LRT: the level-0 LRT joints keep their id where a scheme LRT line crosses the same border within 150 m
    ev, wiggles = city_l1.scheme_events(specs, areas, city_ext)
    for e in ev:
        e["years"] = e["years"] or [None] * 4
    lrt_ev = [e for e in ev if e["kind"] == "lrt"]
    road_ev = [e for e in ev if e["kind"] == "road"]
    lrt_j = [{**{k: v for k, v in o.items()}, "source": "lrt_v0"} for o in J0 if o["kind"] == "lrt"]
    rails = [j for j in out if j["kind"] == "rail"]
    pool, rep_l = city_l1.attach_scheme(lrt_j + rails, lrt_ev, None)
    lrt_j = [j for j in pool if j["kind"] != "rail"]
    ev_years = {(e["spec"], e["axis"]): e["years"] for e in ev}
    keep_lrt = []
    for j in lrt_j:
        ax = j.get("axes") or []
        if j.get("id") and not ax:
            continue                                   # level-0 LRT joint no scheme line reaches: retired below
        ys = [ev_years.get((a["spec"], a["axis"])) for a in ax]
        ys = [y for y in ys if y and y[0] is not None]
        j["years"] = [max(y[i] for y in ys) for i in range(4)] if ys else None
        if j.get("id"):
            x = float(np.mean([a["_p"][0] for a in ax])); z = float(np.mean([a["_p"][1] for a in ax]))
            j["level0"] = {"x": j["x"], "z": j["z"], "between": old_by[j["id"]]["between"], "line": j["line"]}
            j.update({"x": rnd(x), "z": rnd(z), "line": "lrt_schemes", "source": "scheme_lrt"})
        else:
            j["source"] = "scheme_lrt"
        keep_lrt.append(j)
    allj = out + keep_lrt
    allj, rep_r = city_l1.attach_scheme(allj, road_ev, None)
    for j in allj:
        if j.get("source") == "scheme_axis" and j.get("axes"):
            ys = [ev_years.get((a["spec"], a["axis"])) for a in j["axes"]]
            ys = [y for y in ys if y and y[0] is not None]
            if ys:
                j["years"] = [max(y[i] for y in ys) for i in range(4)]
    # new ids, after the highest level-0 id
    nxt = max(int(j["id"][1:]) for j in J0) + 1
    for j in sorted([j for j in allj if not j.get("id")], key=lambda j: (j["between"], j["kind"], -j["z"], j["x"])):
        j["id"] = f"J{nxt:03d}"
        nxt += 1
    for j in allj:
        for a in j.get("axes", []):
            a.pop("_p", None)
        j.pop("new_l1", None)
    final_ids = {j["id"] for j in allj}
    # retired level-0 ids with the reason
    inner = city.buffer(-30)
    retired = []
    for o in J0:
        if o["id"] in final_ids:
            continue
        p = Point(o["x"], o["z"])
        r = {"id": o["id"], "x": o["x"], "z": o["z"], "kind": o["kind"], "line": o["line"], "between": o["between"]}
        if o["kind"] == "lrt" and "outside" in o["between"] and inner.contains(p):
            r["reason_ru"] = "артефакт выемки у Әли: точка внутри города; выемка отдана Golden, ЛРТ схемы Golden идёт по ней внутри района"
        elif o["kind"] == "lrt":
            r["reason_ru"] = "lrt_v0 заменена линиями схем (lrt_schemes): здесь ни одна линия ЛРТ схем не пересекает границу"
        elif o["id"] in dup:
            r["reason_ru"] = "дубль того же пересечения той же линии"
        elif "outside" in o["between"] and inner.contains(p):
            r["reason_ru"] = ("точка внутри города: «вне районов» получалось из-за щели между районами или потому, что кусок трассы "
                              "кончается на линии раздела Growing (сама А-3) — это не пересечение")
        elif any(d["p"].distance(p) <= 30 and o["line"] in d["lines"] for d in dropped):
            r["reason_ru"] = "кусок трассы кончается на границе, по другую сторону продолжения нет — не пересечение"
        else:
            r["reason_ru"] = "после правки границ эта линия здесь границу не пересекает"
        near = [(math.hypot(j["x"] - o["x"], j["z"] - o["z"]), j["id"]) for j in allj if j["kind"] == o["kind"]]
        near = [t for t in near if t[0] <= city_l1.JOINT_TOL_M]
        if near:
            r["replaced_by"] = min(near)[1]
        retired.append(r)
    allj.sort(key=lambda j: int(j["id"][1:]))
    # spec references to joints
    refs = []
    by = {j["id"]: j for j in allj}
    ret = {r["id"]: r for r in retired}
    for d, s in specs.items():
        for x in s.get("joints", []):
            jid = x.get("joint_id")
            if jid in ret:
                refs.append({"spec": d, "joint": jid, "axis": x.get("axis"), "status": "retired", "reason_ru": ret[jid]["reason_ru"],
                             "replaced_by": ret[jid].get("replaced_by")})
            elif jid in by and d not in by[jid]["between"]:
                refs.append({"spec": d, "joint": jid, "axis": x.get("axis"), "status": "not_on_border_of_district", "between": by[jid]["between"]})
    per_spec = defaultdict(lambda: {"events": 0, "met_existing": 0, "new": 0})
    for j in allj:
        for a in j.get("axes", []):
            ps = per_spec[a["spec"]]
            ps["events"] += 1
            if j.get("source") in ("scheme_axis", "scheme_lrt") and a["dist_m"] == 0.0 and not j["id"] in old_by:
                ps["new"] += 1
            else:
                ps["met_existing"] += 1
    rep = {"specs": specs, "moved_bakad": moved, "retired": retired, "spec_refs": refs,
           "scheme": {"events": len(ev), "events_without_joint": 0, "lrt": rep_l, "roads": rep_r, "per_spec": dict(per_spec),
                      "new_ids": [j["id"] for j in allj if j["id"] not in old_by]},
           "touch_not_crossing": len(dropped),
           "wiggles": [{"spec": e["spec"], "axis": e["axis"], "x": rnd(e["p"].x), "z": rnd(e["p"].y), "between": e["between"],
                        "why": "идёт по границе" if e.get("follows_border") else "выход и возврат"} for e in wiggles]}
    # proof: every scheme event has a joint of its pair within the tolerance
    missing = 0
    for e in ev:
        if not any(j["between"] == e["between"] and city_l1.kind_ok(j["kind"], e["kind"])
                   and math.hypot(j["x"] - e["p"].x, j["z"] - e["p"].y) <= city_l1.JOINT_TOL_M + 1e-6 for j in allj):
            missing += 1
    rep["scheme"]["events_without_joint"] = missing
    return allj, rep


# ====================================================================== 8. bid ranges
def bid_ranges(D, areas):
    B = twin.buildings()
    n = len(B); bmax = int(B.bid.max())
    def area_of(x, z):
        for k, g in areas.items():
            if shapely.contains_xy(g, x, z):
                return k
        return "outside"
    xs, zs = B.x.values, B.z.values
    who = np.array(["outside"] * n, dtype=object)
    for k, g in areas.items():
        who[shapely.contains_xy(g, xs, zs)] = k
    B = B.assign(area=who)
    ex = B[B.source == "existing_osm"]
    ex_lo, ex_hi = int(ex.bid.min()), int(ex.bid.max())
    contiguous = (ex_hi - ex_lo + 1) == len(ex)
    solar = (B.kind == "solar")
    new_now = B[(B.source != "existing_osm") & ~solar]
    now = new_now.groupby("area").size().to_dict()
    ex_by = ex.groupby("area").size().to_dict()
    # all free numbers are shared out: Green takes the upper block (the only district that fits there), the lower block goes to
    # Gate / Golden / Growing-W / Growing-E in proportion to today's new (non-solar) buildings, Gate at least 4 000; ranges are
    # rounded down to 250 and what is left is the city reserve
    order = ["gate", "golden", "growing_w", "growing_e"]
    A_len = ex_lo                       # 0 … ex_lo − 1
    Bsp = (ex_hi + 1, 65535)            # above the existing block, up to the shader table limit (256 × 256)
    B_len = Bsp[1] - Bsp[0] + 1
    resA_len, resB_len = 745, 346
    gate_min = 4000
    poolA = A_len - resA_len
    rest = [k for k in order if k != "gate"]
    n_rest = sum(now.get(k, 0) for k in rest)
    size = {"gate": max(gate_min, int(poolA * now.get("gate", 0) / max(1, n_rest + now.get("gate", 0))) // 250 * 250)}
    for k in rest:
        size[k] = int((poolA - size["gate"]) * now.get(k, 0) / n_rest) // 250 * 250
    size["green"] = (B_len - resB_len) // 250 * 250
    ranges = {}
    cur = 0
    for k in order:
        ranges[k] = [cur, cur + size[k] - 1]; cur += size[k]
    resA = [cur, A_len - 1]
    ranges["green"] = [Bsp[0], Bsp[0] + size["green"] - 1]
    resB = [ranges["green"][1] + 1, 65535]
    total_new = sum(r[1] - r[0] + 1 for r in ranges.values())
    nres = (resA[1] - resA[0] + 1) + (resB[1] - resB[0] + 1)
    f = lambda v: f"{v:,}".replace(",", " ")  # noqa: E731
    arith = [f"сейчас в buildings.csv {f(n)} зданий, bid 0…{bmax}; существующие дома (existing_osm) — сплошной блок {ex_lo}…{ex_hi} = {f(ex_hi - ex_lo + 1)} номеров"
             + ("" if contiguous else " (с пропусками)") + "; их номера не меняются",
             f"свободно: нижний блок 0…{ex_lo - 1} = {f(A_len)} и верхний {ex_hi + 1}…65535 = {f(B_len)}; всего {f(A_len + B_len)}",
             f"верхний блок целиком получает Green (больше туда никто не помещается): {f(B_len)} − резерв {resB_len} = {f(B_len - resB_len)} → вниз до 250 = {f(size['green'])}",
             f"нижний блок: {f(A_len)} − резерв {resA_len} = {f(poolA)}; Gate = max(4 000, доля по сегодняшним зданиям) = {f(size['gate'])}; "
             f"остаток {f(poolA - size['gate'])} делится между Golden / Growing-запад / Growing-восток пропорционально {now.get('golden', 0)} / {now.get('growing_w', 0)} / {now.get('growing_e', 0)} (сегодняшние новые здания без СЭС), вниз до 250",
             *[f"{AREA_NAMES[k]}: сегодня {f(now.get(k, 0))} новых зданий → диапазон {ranges[k][0]}…{ranges[k][1]} = {f(size[k])} (×{size[k] / max(1, now.get(k, 0)):.2f})" for k in order + ["green"]],
             f"резерв города: {resA[0]}…{resA[1]} ({f(resA[1] - resA[0] + 1)}) и {resB[0]}…{resB[1]} ({f(resB[1] - resB[0] + 1)})",
             f"проверка первой половины: зданий не больше {f(ex_hi - ex_lo + 1)} существующих + {f(total_new)} новых = {f(ex_hi - ex_lo + 1 + total_new)} < 65 536; "
             f"с резервом {f(nres)} = {f(ex_hi - ex_lo + 1 + total_new + nres)} — это вся нижняя половина таблицы шейдера (номера 0…65535), диапазоны не пересекаются"]
    assert ex_hi - ex_lo + 1 + total_new < HALF and ex_hi - ex_lo + 1 + total_new + nres == HALF
    l2 = bid_ranges_l2(areas, f, size)
    arith += l2.pop("arithmetic")
    return {
        "rule": "Номера сохраняют существующие дома (existing_osm) и знаковые объекты списка «сохранить»; все новые и сгенерированные здания получают номера заново: сначала из первого диапазона своего района, потом из второго (ranges2). Существующие дома, которых нет в двойнике, но есть в Overture (gen_buildings: source existing_osm, bid null), получают номера из своего диапазона района (existing_overture.by_district) по порядку: район, затем округлённый центр (z, x). Панели СЭС (kind solar, 11 743 шт.) уходят из зданий в отдельный слой и номеров не получают.",
        "limit": BID_LIMIT,
        "table": "256 × 512 текселей (BidTable.cs, AlatauLit.shader tuv): номера 0…131071; в двоичных слоях bid — int32 (AQL1, HID1), ограничение только у таблицы",
        "total_buildings_max": int(ex_hi - ex_lo + 1 + total_new) + l2["total_max"],
        "keep": {"existing_osm": [ex_lo, ex_hi], "count": int(len(ex)), "by_area": {k: int(v) for k, v in ex_by.items()},
                 "landmarks": "знаковые объекты (Iconic, QAIST, L7, PepsiCo …) — отдельные модели LandmarkData, не строки buildings.csv: номеров у них нет, сохранять нечего"},
        "retired": {"note": "номера сгенерированных зданий, объектов генплана (master_plan) и 530 заводов relocate_industry (57690…58219) освобождаются; снесённые существующие дома оставляют дыры в блоке existing",
                    "generated": int((B.source == "generated").sum()), "master_plan": int((B.source == "master_plan").sum()), "solar": int(solar.sum())},
        "today_new_buildings_no_solar": {k: int(v) for k, v in now.items()},
        "ranges": {k: {"from": r[0], "to": r[1], "size": r[1] - r[0] + 1} for k, r in ranges.items()},
        "ranges2": l2["ranges2"],
        "existing_overture": l2["existing_overture"],
        "reserve": [{"from": resA[0], "to": resA[1], "use": "город: сшивка районов, уровень 3"}, {"from": resB[0], "to": resB[1], "use": "город: резерв"},
                    *l2["reserve"]],
        "arithmetic": arith,
    }


HALF = 65536                      # the old 256 × 256 table: first ranges and the existing block live here
BID_LIMIT = 256 * 512             # the per-building tables of Unity (BidTable.cs): bids 0 … 131 071
L2_ORDER = ["gate", "golden", "growing_w", "growing_e", "green"]
OV_MARGIN = 1.25                  # existing_overture: room for Overture updates and houses split into parts (модель qTwin)
L2_RES_MIN = 1024                 # city reserve at the top of the table, at least


def overture_only_counts(areas):
    """Existing houses that only Overture has, per district: gen_blocks_lots.existing_houses() over the district outline, rows with
    bid null (a house of ≥ 25 m² that no twin existing_osm footprint covers by more than 30 %; a building split into parts counts
    each part, as gen_buildings writes it)."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gen"))
    import gen_blocks_lots as GBL
    out = {}
    for k in L2_ORDER:
        g = areas[k]
        g = g if g.geom_type == "Polygon" else max(g.geoms, key=lambda q: q.area)
        out[k] = sum(1 for h in GBL.existing_houses(Polygon(g.exterior.coords).buffer(0), None) if h["bid"] is None)
    return out


def bid_ranges_l2(areas, f, first):
    """Second half of the table (65 536 … 131 071, w49): per district a block of its own Overture-only existing houses
    (count × OV_MARGIN, up to 250) and a second range for new buildings; the rest is the city reserve. The second ranges share the
    pool by weight = ½ area share + ½ share of the 2050 population target (spec/<d>.json targets.population_2050), down to 250."""
    cnt = overture_only_counts(areas)
    pop = {k: int(json.load(open(os.path.join(frames.SPEC_DIR, k + ".json"), encoding="utf-8"))["targets"]["population_2050"]) for k in L2_ORDER}
    area = {k: float(areas[k].area) / 1e4 for k in L2_ORDER}
    ov = {k: int(math.ceil(cnt[k] * OV_MARGIN / 250.0)) * 250 for k in L2_ORDER}
    pool = BID_LIMIT - HALF - sum(ov.values()) - L2_RES_MIN
    sa, sp = sum(area.values()), sum(pop.values())
    w = {k: 0.5 * area[k] / sa + 0.5 * pop[k] / sp for k in L2_ORDER}
    sec = {k: int(pool * w[k]) // 250 * 250 for k in L2_ORDER}
    cur, ovr, r2 = HALF, {}, {}
    for k in L2_ORDER:
        ovr[k] = [cur, cur + ov[k] - 1]; cur += ov[k]
        r2[k] = [cur, cur + sec[k] - 1]; cur += sec[k]
    res = [cur, BID_LIMIT - 1]
    n_ov, n_sec, n_res = sum(ov.values()), sum(sec.values()), res[1] - res[0] + 1
    assert n_ov + n_sec + n_res == BID_LIMIT - HALF and n_res >= L2_RES_MIN
    assert all(cnt[k] <= ov[k] for k in L2_ORDER)
    rg = lambda r: f"{r[0]}…{r[1]} = {f(r[1] - r[0] + 1)}"  # noqa: E731
    arith = [f"вторая половина таблицы (уровень 2, w49): таблица шейдера стала 256 × 512 = {f(BID_LIMIT)} номеров; новые номера {HALF}…{BID_LIMIT - 1} = {f(BID_LIMIT - HALF)}",
             "дома, которых нет в двойнике, но есть в Overture (gen_blocks_lots.existing_houses() по контуру района, строки с bid null): "
             + ", ".join(f"{AREA_NAMES[k]} {f(cnt[k])}" for k in L2_ORDER) + f"; всего {f(sum(cnt.values()))}",
             f"их диапазоны: число × {OV_MARGIN} (запас на обновления Overture и дома из нескольких частей, модель qTwin), вверх до 250: "
             + ", ".join(f"{AREA_NAMES[k]} {f(ov[k])}" for k in L2_ORDER) + f"; всего {f(n_ov)}",
             f"на вторые диапазоны новых зданий: {f(BID_LIMIT - HALF)} − {f(n_ov)} − резерв не меньше {f(L2_RES_MIN)} = {f(pool)}; доля района = ½ доли площади + ½ доли жителей 2050 "
             "(spec/<район>.json targets.population_2050), вниз до 250 (модель qTwin)",
             *[f"{AREA_NAMES[k]}: {f(round(area[k]))} га, {f(pop[k])} жителей 2050 → доля {w[k]:.4f} → {f(pool)} × {w[k]:.4f} = {f(int(pool * w[k]))} → {f(sec[k])}; "
               f"дома Overture {rg(ovr[k])}, второй диапазон {rg(r2[k])}" for k in L2_ORDER],
             f"резерв города: {rg(res)}",
             "номеров для новых зданий у района (первый + второй диапазон): "
             + ", ".join(f"{AREA_NAMES[k]} {f(first[k])} + {f(sec[k])} = {f(first[k] + sec[k])}" for k in L2_ORDER),
             f"проверка второй половины: {f(n_ov)} + {f(n_sec)} + {f(n_res)} = {f(BID_LIMIT - HALF)} (номера {HALF}…{BID_LIMIT - 1}); диапазоны не пересекаются"]
    return {"ranges2": {k: {"from": r[0], "to": r[1], "size": r[1] - r[0] + 1, "weight": round(w[k], 4)} for k, r in r2.items()},
            "existing_overture": {"what": "существующие дома, которых нет в двойнике, но есть в Overture (gen_buildings: source existing_osm, bid null); merge нумерует их по порядку: район, затем округлённый центр (z, затем x), затем id",
                                  "size": n_ov, "margin": OV_MARGIN, "layout": "у каждого района в 65536…131071 подряд: его дома Overture, затем его второй диапазон",
                                  "by_district": {k: {"from": r[0], "to": r[1], "size": r[1] - r[0] + 1, "count": cnt[k]} for k, r in ovr.items()}},
            "reserve": [{"from": res[0], "to": res[1], "use": "город: резерв второй половины"}],
            "total_max": n_ov + n_sec, "arithmetic": arith}


# ====================================================================== 9. height-limit zones
def airfields():
    T = terrain.terrain()
    res = []
    def add(id_, name, x, z, elev, src, named_by, status, note=None, alt=None):
        if any(q["id"] == id_ for q in res):
            return
        r = {"id": id_, "name": name, "x": rnd(x), "z": rnd(z), "elev_m": elev, "status": status, "named_by": named_by, "source": src,
             "twin_ground_m": rnd(T.height(x, z) + 0.0, 1) if T.inside(x, z) else None}
        lon, lat = frames.unity_to_lonlat(x, z)
        r["lat"], r["lon"] = round(float(lat), 5), round(float(lon), 5)
        if note:
            r["note"] = note
        if alt:
            r["alt"] = alt
        res.append(r)
    x, z = frames.lonlat_to_unity(77.1206, 43.7317)
    xa, za = frames.lonlat_to_unity(77.1167, 43.7331)
    add("zhetygen_mil", "Военный аэродром Жетыген (Николаевка), 600-я гв. авиабаза", float(x), float(z), 499,
        "dic.academic.ru (копия ru.wikipedia «Жетыген (аэродром)»): КТА 43°43′54″ N 77°07′14″ E, превышение 499 м, ВПП 01/19 2 500 × 40 м; research/transport_site.md §1.1",
        "research", "действующий", alt={"lat": 43.7331, "lon": 77.1167, "x": rnd(float(xa)), "z": rnd(float(za)),
                                       "source": "wiki.riteme.site/wiki/Zhetygen (зеркало en.wikipedia), точка «аэродром 600-й авиабазы»",
                                       "why_not_used": "у первого источника это контрольная точка аэродрома (КТА) с превышением; ВПП в OSM: центр 43.7322 N 77.1199 E, ≈ 80 м от КТА"})
    # from Overture (real) – international airport of Almaty, named in the research as a reference
    try:
        ig, ip = None, None
        import pyarrow.parquet as pq
        t = pq.read_table(src_path("overture_raw", "infrastructure.parquet")).to_pandas()
        def rw(cls, pred):
            m = t[(t.subtype == "airport") & (t["class"] == cls)]
            for _, r in m.iterrows():
                g = frames.geom_lonlat_to_unity(shapely.from_wkb(r.geometry))
                if pred(g, r):
                    yield g, r
        rws = [(g, r) for g, r in rw("runway", lambda g, r: True)]
        def runway_centre(near, rad):
            rr = [g for g, _ in rws if g.distance(near) < rad and g.geom_type == "LineString"]
            if not rr:
                return None
            longest = max(rr, key=lambda g: g.length)
            c = longest.interpolate(0.5, normalized=True)
            return c, longest.length, len(rr)
        for _, r in t[(t.subtype == "airport") & t["class"].isin(["international_airport", "airport", "military_airport"])].iterrows():
            g = frames.geom_lonlat_to_unity(shapely.from_wkb(r.geometry))
            nm = r["name"] if isinstance(r["name"], str) else None
            c = runway_centre(g.centroid, 3000)
            if nm and "Алматы" in nm and r["class"] == "international_airport":
                add("almaty_intl", "Международный аэропорт Алматы (ALA)", c[0].x, c[0].y, None,
                    f"{OVT}: аэропорт «{nm}», центр самой длинной ВПП ({c[1]:.0f} м); КТА в открытых данных не найдена",
                    "research", "действующий", note="research/alatau_objects.md называет его ориентиром (13,5 км от Griffin Logopark); превышение не найдено, взята высота рельефа у ВПП")
            elif nm == "Baiserke Airport":
                add("baiserke", "Аэродром Байсерке (Baiserke Airport)", c[0].x, c[0].y, None, f"{OVT}: «{nm}», центр ВПП {c[1]:.0f} м", "overture", "действующий (малая авиация)",
                    note="research его не называет; найден в Overture, лежит внутри города")
            elif nm and "Боралдай" in nm:
                add("boraldai", "Аэродром Боралдай (Бурундай)", c[0].x, c[0].y, None, f"{OVT}: «{nm}», центр ВПП {c[1]:.0f} м", "overture", "действующий (малая авиация)",
                    note="research его не называет; найден в Overture")
            elif nm == "Iliysk North Airport":
                add("iliysk_north", "Аэродром Iliysk North (к северу от Конаева)", c[0].x, c[0].y, None, f"{OVT}: «{nm}», центр ВПП {c[1]:.0f} м", "overture", "по OSM",
                    note="research его не называет; найден в Overture")
            elif nm == "North Almaty Air":
                add("north_almaty", "Площадка North Almaty Air", c[0].x, c[0].y, None, f"{OVT}: military_airport «{nm}», ВПП {c[1]:.0f} м", "overture", "по OSM",
                    note="research её не называет; короткие ВПП ≈ 540 м")
    except Exception as e:  # noqa: BLE001
        print("[airfields] overture lookup failed:", e)
    ap = city_l1.AIRPORT_NEW
    add(ap["id"], "Международный аэропорт «Алатау» (план, 15 млн пасс./год)", ap["centre"][0], ap["centre"][1], None,
        "место утверждено владельцем 31.10.2026 по схеме Growing-запад (tools/map/spec/growing_w.json, objects «airport_alatau»): "
        "контрольная точка = центр ВПП 4 000 м, курс 095°, (−16000, 1500); модель qTwin — источники дают только «полигон у с. Жанаарна "
        "на западной границе» (liter.kz 03.03.2025, research S65), 15 млн пасс./год и «после 2040» — генплан (research S03)",
        "research", "план: строится после 2040 (ВПП и терминал 2041–2045)",
        note="было: модель двойника (LandmarkData «airport», −5900, 8300), до 31.10.2026")
    a_ = res[-1]
    a_.update({"runway": {"line": city_l1.airport_runway(), "bearing_deg": ap["bearing_deg"], "length_m": ap["length_m"], "width_m": ap["width_m"]},
               "pax_m_per_year": ap["pax_m_per_year"], "build_years": ap["build_years"], "years": city_l1.years4(ap["build_years"][-1], not_before=ap["build_years"][0]),
               "before": {"x": -5900.0, "z": 8300.0, "source": "модель двойника (LandmarkData «airport»), city.json v0"}})
    for r in res:
        if r["elev_m"] is None and r["twin_ground_m"] is not None:
            r["elev_m"] = rnd(r["twin_ground_m"] + 2.0, 0)
            r["elev_note"] = "рельеф двойника у точки + 2 м (FloodModel.Datum)"
    return res


def height_zones(D):
    city = twin.city_outline(D)
    B = twin.buildings()
    T = terrain.terrain()
    af = airfields()
    feats, props = [], []
    for a in af:
        c = Point(a["x"], a["z"])
        z30 = c.buffer(30000, 128)
        z10 = c.buffer(10000, 128)
        a["r30_city_share"] = rnd(z30.intersection(city).area / city.area, 3)
        a["r30_districts"] = [k for k in twin.DISTRICTS if z30.intersects(D[k])]
        a["r10_districts"] = [k for k in twin.DISTRICTS if z10.intersects(D[k])]
        d = np.hypot(B.x.values - a["x"], B.z.values - a["z"])
        top = B.ground_m.values + B.height_m.values
        a["twin_buildings_50m_plus_in_30km"] = int(((d <= 30000) & (B.height_m.values >= 50)).sum())
        if a["elev_m"] is not None:
            a["twin_buildings_top_50m_above_aerodrome_in_30km"] = int(((d <= 30000) & (top - a["elev_m"] >= 50)).sum())
        feats += [z30, z10]
        props += [{"id": a["id"] + "_r30", "airfield": a["name"], "radius_m": 30000, "rule": "здания ≥ 50 м высотой или ≥ 50 м над уровнем аэродрома: «нужно согласование»"},
                  {"id": a["id"] + "_r10", "airfield": a["name"], "radius_m": 10000, "rule": "все объекты: согласование; свалки и бойни не ближе 15 км"}]
    layers.write("derived/height_zones", feats, props)
    union = unary_union([Point(a["x"], a["z"]).buffer(30000, 128) for a in af if a["named_by"] == "research"])
    return af, rnd(union.intersection(city).area / city.area, 3)


# ====================================================================== 10. centres
def centres(areas):
    res = {}
    for k, g in areas.items():
        c = g.centroid
        pl = polylabel(g if g.geom_type == "Polygon" else max(g.geoms, key=lambda q: q.area), tolerance=5)
        res[k] = {"centroid": [rnd(c.x, 0), rnd(c.y, 0)], "pole_of_inaccessibility": [rnd(pl.x, 0), rnd(pl.y, 0)],
                  "pole_radius_m": rnd(g.boundary.distance(pl), 0), "centroid_inside": bool(g.contains(c))}
    return res


# ====================================================================== main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-compare", action="store_true")
    ap.add_argument("--bids-only", action="store_true", help="recompute only city.json#bids from the district outlines already in city.json")
    a = ap.parse_args()
    if a.bids_only:
        return bids_only()

    gp, gp_files = convert_genplan()
    raw = twin.district_outlines_raw()
    D0, slivers = twin.district_polygons()
    print("[districts L0]", {k: rnd(v.area / 1e4) for k, v in D0.items()})

    # ---- level 1 (w42): one exact partition. Bays and gaps no district covered go to the neighbour (twin outline rule), twin
    # buildings a metre outside their own district are taken in, the halves of Growing cover it exactly, 1 m grid, all valid.
    D1, notches = city_l1.partition_fixes(D0, gp["city"][0], gp)
    D1, bpatch = city_l1.building_patches(D1, twin.buildings())
    sp = growing_split(D1)
    W, E, crumbs = city_l1.halves_single(sp["growing_w"], sp["growing_e"])
    areas, cov_rep = city_l1.make_coverage({"gate": D1["Gate"], "golden": D1["Golden"], "growing_w": W, "growing_e": E, "green": D1["Green"]})
    D = {"Gate": areas["gate"], "Golden": areas["golden"], "Growing": city_l1.one_polygon(unary_union([areas["growing_w"], areas["growing_e"]]))[0],
         "Green": areas["green"]}
    city = twin.city_outline(D)
    code_ha = {k.lower(): v for k, v in twin.DISTRICT_AREA_HA_CODE.items()}
    cov_check = city_l1.coverage_checks({**areas}, code_ha)
    cov_check["growing"] = {"area_ha": rnd(D["Growing"].area / 1e4), "area_code_ha": code_ha["growing"],
                            "diff_pct": rnd((D["Growing"].area / 1e4 / code_ha["growing"] - 1) * 100, 2),
                            "halves_symdiff_m2": rnd(D["Growing"].symmetric_difference(unary_union([areas["growing_w"], areas["growing_e"]])).area, 2),
                            "valid": bool(D["Growing"].is_valid)}
    cov_check["twin_buildings_outside_own_district"] = {}
    B_ = twin.buildings()
    for k in twin.DISTRICTS:
        sub = B_[B_.district == k]
        cov_check["twin_buildings_outside_own_district"][k] = int((~shapely.contains_xy(D[k], sub.x.values, sub.z.values)).sum())
    hx = B_[B_.bid == 56596]
    cov_check["bid_56596"] = {k: bool(areas[k].contains(Point(float(hx.x.iloc[0]), float(hx.z.iloc[0])))) for k in ("growing_w", "growing_e")} if len(hx) else None
    print("[districts L1]", {k: rnd(v.area / 1e4) for k, v in D.items()}, "city", rnd(city.area / 1e4), "notches", notches, "patches", len(bpatch))
    print("[coverage]", json.dumps(cov_rep, ensure_ascii=False), json.dumps({k: v for k, v in cov_check.items() if k != "districts"}, ensure_ascii=False))

    pr = proof(gp, D, raw)
    with open(frames.out("transform_proof.json"), "w", encoding="utf-8") as f:
        json.dump(pr, f, ensure_ascii=False, indent=1)
    print("[proof]", json.dumps(pr["districts"], ensure_ascii=False)[:600])
    print("[split]", sp["refs"], sp["names"], sp["mean_abs_x"], sp["len_in_growing_km"], {k: rnd(v.area / 1e4) for k, v in areas.items()})

    # districts layer (partition of level 1 + growing halves + genplan alternatives + the notches given away)
    dfe, dpr = [], []
    for k in twin.DISTRICTS:
        dfe.append(D[k]); dpr.append({"id": k.lower(), "name": k, "area_ha": rnd(D[k].area / 1e4),
                                      "source": "двойник: layer_infrastructure.bytes «%s District boundary» (модель QTwin), щели ≤ 5 м и выемки отданы соседу, сетка 1 м (w42)" % k})
    for k in ("growing_w", "growing_e"):
        dfe.append(areas[k]); dpr.append({"id": k, "name": AREA_NAMES[k], "area_ha": rnd(areas[k].area / 1e4), "source": "Growing, разрезанный осью деления (см. growing_split)"})
    for k in twin.DISTRICTS:
        g = gp[k.lower()][0]
        dfe.append(g); dpr.append({"id": k.lower() + "_geojson", "name": k + " (geojson генплана)", "area_ha": rnd(g.area / 1e4), "alt": True,
                                   "source": "alatau_plan_utm43n_rel.geojson, сдвиг rel → Unity"})
    dfe.append(city); dpr.append({"id": "city", "name": "Алатау (объединение районов двойника)", "area_ha": rnd(city.area / 1e4)})
    dfe.append(sp["line"]); dpr.append({"id": "growing_split", "name": "ось деления Growing", "edges": sp["edges"]})
    layers.write("derived/districts", dfe, dpr)

    water_rows, water_other = water(D, gp)
    lev = kapchagay_levels(D)
    layers.write("derived/kapchagay_levels", [r.pop("geom") for r in lev], [{"real_m": r["real_m"], "twin_m": r["twin_m"]} for r in lev])
    ex = existing(D)
    sett, sett_g = settlements(D)
    tf, tp, tsum = trunk_v0()
    lrt_routes, lrt_st, lrt_c = lrt_v0()

    # ---- joints. Level-0 ids first (same algorithm, same areas as level 0), then the rebuilt crossings on the level-1 areas.
    lines = [("road", p["id"], p["class"], p["years"], g) for g, p in zip(tf, tp)]
    rl, rlp = layers.load("rail")
    for g, p in zip(rl, rlp):
        for q in getattr(g, "geoms", [g]):
            lines.append(("rail", p["id"], "rail_existing", city_l1.years4(2025, existing=True), q))   # existing OSM rail: 2025 in all 4 years
    sp0 = growing_split(D0)
    areas0 = {"gate": D0["Gate"], "golden": D0["Golden"], "growing_w": sp0["growing_w"], "growing_e": sp0["growing_e"], "green": D0["Green"]}
    J0 = joints(areas0, lines + [("lrt", "LRT-" + n, "lrt", None, ls) for n, ls in lrt_routes])
    J, jrep = rebuild_joints(J0, lines, areas, city, notches)
    layers.write("derived/joints", [Point(j["x"], j["z"]) for j in J], J)
    print("[joints]", len(J), Counter(j["kind"] for j in J), json.dumps(jrep["scheme"], ensure_ascii=False))
    lrts = city_l1.lrt_schemes(jrep["specs"], J, areas, "derived/lrt_schemes")

    bids = bid_ranges(D, areas)
    af, af_share = height_zones(D)
    cen = centres(areas)
    gc = cen["gate"]
    iconic0 = {"x": ICONIC[0], "z": ICONIC[1], "yaw": 270,
               "source": "UnityProject/Assets/Scripts/DigitalTwin/Landmarks/LandmarkData.cs:97 (Id «iconic», X −3170, Z −19080, Yaw 270)",
               "used_by": ["IconicDistrict.Frame() (центр Gate District, маска _AlatauGateTex)", "LandmarkSystem (площадка, скрытие зданий)",
                           "FilmLook.cs:112", "FilmReel.cs:195, 237", "TwinPitch.cs:95", "ShotRig: локальная система Iconic"],
               "stale": {"x": ICONIC_FIRST_SITE[0], "z": ICONIC_FIRST_SITE[1], "yaw": 105.2,
                         "where": "tools/build_iconic_district.py:14, tools/build_iconic_park.py:15, tools/relocate_industry.py:151, Resources/Landmarks/iconic_district.json cx/cz",
                         "why_stale": "первое место комплекса; IconicPark.Boot() пуст («the grounds were laid round the first site … the complex now stands in the heart of Gate»), iconic_district.json не читает ни один скрипт; базовый коммит d772ff8 (29.10) уже содержит −3170, −19080",
                         "distance_m": rnd(math.dist(ICONIC, ICONIC_FIRST_SITE), 0)}}
    iconic = city_l1.iconic_block(iconic0)
    iconic["dist_to_gate_centroid_m"] = rnd(math.dist(city_l1.ICONIC_NEW, gc["centroid"]), 0)
    iconic["dist_to_gate_pole_m"] = rnd(math.dist(city_l1.ICONIC_NEW, gc["pole_of_inaccessibility"]), 0)
    iconic["in_gate"] = bool(areas["gate"].contains(Point(*city_l1.ICONIC_NEW)))
    iconic["before"]["twin_ground_m"] = rnd(terrain.height(*ICONIC), 1)

    # the duplicate ring: how far it runs from the real BAKAD (Overture) and from the twin's own BAKAD pieces
    rg_, rp_ = layers.load("roads")
    bk_u = unary_union([g for g, p in zip(rg_, rp_) if BAKAD_REF in (p.get("ref") or [])])
    dup_check = []
    for g, p in zip(tf, tp):
        if p["id"] in TRUNK_DUPLICATES:
            d_ = np.array([bk_u.distance(g.interpolate(t, normalized=True)) for t in np.linspace(0, 1, 101)])
            dup_check.append({"id": p["id"], "len_km": p["len_km"], "dist_to_osm_bakad_m": {"median": rnd(np.median(d_)), "mean": rnd(d_.mean()), "max": rnd(d_.max())},
                              "share_within_50m_pct": rnd((d_ <= 50).mean() * 100), "duplicate_of": TRUNK_DUPLICATES[p["id"]],
                              "joints_moved": [m["id"] for m in jrep["moved_bakad"]]})

    # ---------------------------------------------------------------- city.json
    rel = src_path
    half_of = lambda x, z: next((k for k in ("growing_w", "growing_e") if areas[k].contains(Point(x, z))), None)  # noqa: E731
    sett_pt = {s_["name"]: s_["c"] for s_ in sett}
    key_places = {"аэропорт «Алатау» (центр ВПП)": city_l1.AIRPORT_NEW["centre"], "Жанаарна (посёлок)": tuple(sett_pt.get("Жанаарна", (None, None))),
                  "OIZ TULIP (схема growing_e)": next((tuple(o["to"]) for o in jrep["specs"]["growing_e"]["objects"] if o["registry_id"] == "oiz_tulip" and o.get("to")), (None, None)),
                  "Жетыген (посёлок, точка схемы growing_e: в Overture нет)": tuple(sett_pt.get("Жетыген") or next((o["to"] for o in jrep["specs"]["growing_e"]["objects"] if o["registry_id"] == "settlement_zhetygen" and o.get("to")), (None, None))),
                  "Mars Petcare (схема growing_e)": next((tuple(o["to"]) for o in jrep["specs"]["growing_e"]["objects"] if o["registry_id"] == "mars_petcare" and o.get("to")), (None, None)),
                  "сухой порт (схема growing_w)": next((tuple(o["to"]) for o in jrep["specs"]["growing_w"]["objects"] if o["registry_id"] == "dry_port" and o.get("to")), (None, None))}
    split_check = {n: (half_of(*xz) if xz[0] is not None else "нет точки") for n, xz in key_places.items()}
    spec = {
        "version": "city.json v1 · level 1 (w42) · 31.10.2026",
        "changes_l1": ["полигоны районов: выемка у Әли и щель Growing/Green отданы соседям, 4 здания двойника взяты в свой район, одно точное покрытие на сетке 1 м (Golden без самопересечения)",
                       "growing_split: списки west/east исправлены, половины покрывают Growing точно",
                       "joints: пересобраны (концы кусков трасс на границе — не стыки), J015/J018 перенесены на настоящую БАКАД, T-R002 помечен дублем, стыки на каждом пересечении осей схем",
                       "lrt_v0 заменена (superseded) на lrt_schemes; новый аэропорт: height_limits и airport_new; iconic → (−3500, −19500)"],
        "what": "Общая спецификация города для перерисовки карты: рамка, границы, вода, существующая сеть, черновик магистралей и ЛРТ, стыки, номера зданий, высотные зоны, центры. Районные спецификации ссылаются на этот файл.",
        "built_by": "tools/map/geo/build_city.py (данные Overture: tools/map/geo/fetch_overture.py)",
        "layers_root": L0_SRC,
        "layers_root_note": "открытые данные уровня 0 (osm/, overture_raw/) остаются у w34; слои, пересобранные на уровне 1 (derived/, genplan/, transform_proof.json), лежат в layers_root_l1; поля layer ниже — полные пути",
        "layers_root_l1": frames.OUT,
        "attribution": frames.ATTRIBUTION,
        "frame": frames.frame_spec(),
        "transform_proof": {"file": rel("transform_proof.json"), "summary": pr["verdict"],
                            "districts": [{k: r[k] for k in ("district", "area_code_ha", "area_genplan_geojson_ha", "diff_geojson_pct", "area_twin_outline_ha",
                                                              "diff_twin_pct", "share_in_geojson_pct", "share_in_twin_outline_pct")} for r in pr["districts"]],
                            "icp_geojson_onto_twin": pr["city_outline"]["icp_geojson_rel_onto_twin"],
                            "osm_boundary": {k: pr["osm_boundary"][k] for k in ("area_ha", "osm_to_geojson", "osm_to_twin")} if isinstance(pr.get("osm_boundary"), dict) else pr.get("osm_boundary")},
        "city": {"boundary": "объединение четырёх районов ниже (контур двойника)", "area_ha": rnd(city.area / 1e4),
                 "area_code_ha": 88000, "layer": rel("derived/districts.geojson") + " (id city)",
                 "osm_boundary": {"area_ha": pr["osm_boundary"]["area_ha"] if isinstance(pr.get("osm_boundary"), dict) else None,
                                  "layer": rel("osm/divisions.geojson") + " (county «Алатау»)", "source": OVT}},
        "districts": {},
        "growing_split": {
            "rule": "магистраль, ближайшая к x = 0, которая пересекает Growing с юга (граница Golden) на север (граница Green), по roads.json (классы highway/ring/main)",
            "result": f"трасса {'/'.join(sp['refs'][:3]) or '—'} (в двойнике класс {', '.join(sp['classes_km'])}), средний |x| = {sp['mean_abs_x']:.0f} м, x {sp['x_range'][0]:.0f}…{sp['x_range'][1]:.0f}",
            "osm_refs": sp["refs"], "osm_names": sp["names"], "classes_km": sp["classes_km"],
            "len_in_growing_km": sp["len_in_growing_km"], "roads_json_edges": sp["edges"],
            "line": line_coords(sp["line"], 0, 2.0),
            "west": "growing_w: новый аэропорт «Алатау» (ВПП 4 000 м, после 2040), аэросити и вокзал, сухой порт, сортировочная станция, центр «Каскелен», дачи и зимовки",
            "east": "growing_e: Жанаарна, OIZ TULIP, Жетыген, Енбек, Mars Petcare, ТЛЦ «Жетыген», промпояс, ГТЭС",
            "check_points": split_check,
            "halves_cover_growing": {"growing_ha": rnd(D["Growing"].area / 1e4), "growing_w_ha": rnd(areas["growing_w"].area / 1e4),
                                     "growing_e_ha": rnd(areas["growing_e"].area / 1e4), "symdiff_m2": cov_check["growing"]["halves_symdiff_m2"],
                                     "overlap_m2": rnd(areas["growing_w"].intersection(areas["growing_e"]).area, 2), "crumbs_moved": crumbs,
                                     "bid_56596": cov_check["bid_56596"]}},
        "water": {"features": water_rows, "other_named": water_other[:40], "layer": rel("derived/water_main.geojson"),
                  "kapchagay_levels": {"what": "вода Капшагая по рельефу двойника при отметке L (ванна со связностью, как FloodModel): реальная отметка = высота двойника + 2 м",
                                       "source": "FloodModel.cs: сейчас 477 м (Tengrinews 16.07.2026), верхний предел 479, проектная 485; рельеф Copernicus GLO-30 через сетку двойника",
                                       "layer": rel("derived/kapchagay_levels.geojson"), "levels": lev},
                  "river_floods": {"source": "risk.json / Tools/twin_gen/gen_risk.py (модель qTwin)",
                                   "scenarios": [{"id": "flood_1pct", "name": "Паводок 1 % (раз в 100 лет)", "stage_m": 1.6},
                                                 {"id": "flood_ext", "name": "Экстремальный паводок 0,1 % + сброс Капшагайской ГЭС", "stage_m": 3.0}],
                                   "rule": "уровень над урезом русел шириной ≥ 20 м, затухание 2,5 м на км, дальше 1,2 км не считается; не заменяет гидрологический расчёт"}},
        "existing_2025": {**ex, "settlements": [{k: v for k, v in s.items() if k != "id"} | {"polygon": ring_coords(g if g.geom_type == "Polygon" else max(g.geoms, key=lambda q: q.area), 0, 40)}
                                                for s, g in zip(sett, sett_g) if s["share_in_city"] > 0 or s["overture_buildings"] >= 50],
                          "settlements_layer": rel("derived/settlements.geojson")},
        "trunk_v0": {"draft": True, "note": "черновик: магистрали двойника (highway / ring / main) с годами по сценариям [base, fast, slow, infra]; картографы районов перепроектируют",
                     "layer": rel("derived/trunk_v0.geojson"), "source": "StreamingAssets/twin/roads.json", **tsum,
                     "routes": [{k: p[k] for k in ("id", "class", "years", "len_km")} | {"from": [rnd(g.coords[0][0], 0), rnd(g.coords[0][1], 0)], "to": [rnd(g.coords[-1][0], 0), rnd(g.coords[-1][1], 0)], "edges": len(p["edges"])}
                                | ({"duplicate_of": p["duplicate_of"]} if p.get("duplicate_of") else {})
                                for g, p in zip(tf, tp) if p["len_km"] >= 2.0],
                     "duplicates": dup_check,
                     "routes_listed": "здесь только куски ≥ 2 км; все куски (с номерами рёбер roads.json) — в слое",
                     "pieces_total": len(tp), "pieces_shorter_than_2km": sum(1 for p in tp if p["len_km"] < 2.0)},
        "lrt_v0": {"draft": True, "superseded": True, "superseded_by": "lrt_schemes",
                   "note": "устарело: трасса и станции ЛРТ двойника (черновик уровня 0); утверждённые линии и станции — в lrt_schemes (схемы пяти районов)",
                   "layer": rel("derived/lrt_v0.geojson"), "source": "Resources/Landmarks/lrt_routes.json + StreamingAssets/twin/construction.json → lrt",
                   "phases": {"names": lrt_c["phase_names"], "km": lrt_c["phase_km"], "years": lrt_c["phase_year"]},
                   "routes": [{"id": "LRT-" + n, "name": n, "len_km": rnd(ls.length / 1000, 2), "line": line_coords(ls, 0, 3.0)} for n, ls in lrt_routes],
                   "stations": lrt_st},
        "lrt_schemes": {"what": "ЛРТ пяти утверждённых схем районов: линии и станции (указатели в спецификации районов) и проверка, что линии соседей сходятся в стыках",
                        "layer": rel("derived/lrt_schemes.geojson"), **lrts},
        "joints": {"what": "точки, где магистраль черновика (без дублей), железная дорога (OSM), ЛРТ схем или ось схемы района (классы expressway, trunk, arterial, lrt_corridor) пересекает границу района/половины Growing или города",
                   "rules": ["пересечение = по обе стороны настоящий район или «вне города»; кусок трассы, который только кончается на границе, — не стык (если с другой стороны в той же точке начинается кусок, это один стык)",
                             "id уровня 0 сохраняются там, где та же линия пересекает границу в пределах %d м; пропавшие — в retired с причиной" % city_l1.MATCH_OLD_M,
                             "ось схемы встречает стык той же пары районов в пределах %d м (axes — какие оси встречены и на каком расстоянии), иначе получает новый стык (source scheme_axis)" % city_l1.JOINT_TOL_M,
                             "years = [base, fast, slow, infra] по правилу двойника (twin_common.effective_year) от года окончания оси; для стыка нескольких осей — поздний"],
                   "layer": rel("derived/joints.geojson"), "count": len(J), "by_kind": dict(Counter(j["kind"] for j in J)),
                   "by_source": dict(Counter(j["source"] for j in J)),
                   "by_pair": {" | ".join(k): v for k, v in Counter(tuple(j["between"]) for j in J).most_common()},
                   "check": {**jrep["scheme"], "touch_not_crossing": jrep["touch_not_crossing"], "bakad_moved": jrep["moved_bakad"],
                             "axis_wiggles_skipped": {"rule": "ось схемы, которая сама идёт по границе (≥ %d %% длины в %d м от неё: А-3 на разделе Growing, дорога вдоль края города) или выходит за границу и возвращается в пределах %d м, эту границу не пересекает"
                                                              % (round(city_l1.FOLLOW_SHARE * 100), city_l1.FOLLOW_BUF_M, city_l1.WIGGLE_M),
                                                      "items": jrep["wiggles"]}},
                   "items": J, "retired": jrep["retired"], "spec_refs_to_fix": jrep["spec_refs"]},
        "bids": bids,
        "height_limits": {"norm": "СНиП РК 3.01-01-2008 (research/norms.md, С08-6, п. 8.30): в радиусе 30 км от КТА — согласование объектов ≥ 50 м над уровнем аэродрома и любых ≥ 50 м высотой; в 10 км — согласование всех объектов",
                          "check": "здание в 30 км от аэродрома высотой ≥ 50 м → «нужно согласование» (правило валидатора 25)",
                          "check_strict": "буква нормы ещё и «≥ 50 м над уровнем аэродрома»: земля + высота − превышение ≥ 50 м. На склоне к югу (Golden/Gate на 560–650 м, Жетыген 499 м) это ловит почти любое здание, поэтому в валидатор идёт первое правило, а второе — предупреждением",
                          "layer": rel("derived/height_zones.geojson"), "airfields": af, "city_share_in_30km_of_research_airfields": af_share},
        "airport_new": {"id": city_l1.AIRPORT_NEW["id"], "what": "ВПП нового аэропорта «Алатау»: 4 000 × 45 м, курс 095°/275°, центр (−16000, 1500); 15 млн пасс./год",
                        "line": city_l1.airport_runway(), "width_m": city_l1.AIRPORT_NEW["width_m"], "bearing_deg": city_l1.AIRPORT_NEW["bearing_deg"],
                        "build_years": city_l1.AIRPORT_NEW["build_years"], "years": city_l1.years4(city_l1.AIRPORT_NEW["build_years"][-1], not_before=city_l1.AIRPORT_NEW["build_years"][0]),
                        "district": half_of(*city_l1.AIRPORT_NEW["centre"]),
                        "ends_in_district": [half_of(*e) for e in city_l1.airport_runway()],
                        "elev_m_ends": [rnd(terrain.height(*e), 1) for e in city_l1.airport_runway()],
                        "source": "решение владельца 31.10.2026 (схема Growing-запад, growing_w.json objects «airport_alatau», checks.airport); модель qTwin; 15 млн и «после 2040» — генплан № 727 (research S03)"},
        "centres": cen,
        "iconic": iconic,
        "slivers_fixed": slivers,
        "partition_l1": {"what": "уровень 1 (w42): куски внутри города, которых не было ни в одном районе, и здания двойника за границей своего района",
                         "notches": notches, "building_patches": bpatch, "coverage": cov_rep, "checks": cov_check,
                         "golden_level0": "полигон Golden в city.json v0 самопересекался у (468, −11867) после округления до метра; теперь все полигоны строятся одним покрытием на сетке 1 м"},
        "genplan_layers": {k: {**v, "file": rel(v["file"])} for k, v in gp_files.items()},
        "not_found": [],
    }
    for k in twin.DISTRICTS:
        spec["districts"][k.lower()] = {"name": k, "area_ha": rnd(D[k].area / 1e4), "area_code_ha": twin.DISTRICT_AREA_HA_CODE[k],
                                        "source": f"двойник: CityData/layer_infrastructure.bytes «{k} District boundary» (модель QTwin генплана)",
                                        "alt_genplan_geojson": {"area_ha": rnd(gp[k.lower()][0].area / 1e4), "layer": rel("genplan/" + k.lower() + ".geojson")},
                                        "polygon": ring_coords(D[k], 0, None), "valid": bool(D[k].is_valid)}
    for k in ("growing_w", "growing_e"):
        g = areas[k]
        g1 = g if g.geom_type == "Polygon" else max(g.geoms, key=lambda q: q.area)
        spec["districts"][k] = {"name": AREA_NAMES[k], "area_ha": rnd(g.area / 1e4), "part_of": "growing", "polygon": ring_coords(g1, 0, None), "valid": bool(g1.is_valid),
                                **({"extra_parts_ha": [rnd(q.area / 1e4, 2) for q in g.geoms if q is not g1]} if g.geom_type == "MultiPolygon" else {})}
    nf = spec["not_found"]
    for r in water_rows:
        if not r.get("found"):
            nf.append(f"вода: {r['name']} — {r.get('note')}")
    nf.append("КТА международного аэропорта Алматы и его превышение: взят центр самой длинной ВПП из OSM и рельеф двойника + 2 м")
    nf.append("место нового аэропорта «Алатау»: в источниках только «у с. Жанаарна, западная граница»; точка — модель qTwin, утверждена владельцем 31.10 (центр ВПП −16000, 1500)")
    nf.append("имена станций ЛРТ (кроме «Аэропорт»): в данных двойника их нет")
    nf.append("официальные полигоны районов генплана: нет ни в открытых данных, ни в репо; есть контуры модели QTwin (взяты) и приблизительные разрезы geojson (альтернатива)")
    p = os.path.join(frames.SPEC_DIR, "city.json")
    os.makedirs(frames.SPEC_DIR, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(dump_compact(spec) + "\n")
    json.load(open(p, encoding="utf-8"))
    print(f"[spec] {p}: {os.path.getsize(p) / 1e3:.0f} kB")

    if not a.no_render:
        import render_maps
        render_maps.main()
    if not a.no_compare:
        import compare_twin
        compare_twin.main()
    write_readme()


def bids_only():
    """city.json#bids again, everything else of city.json untouched (w49: the 256 × 512 table). The districts are the outlines
    city.json already holds (one polygon each)."""
    p = os.path.join(frames.SPEC_DIR, "city.json")
    spec = json.load(open(p, encoding="utf-8"))
    areas = {k: Polygon(spec["districts"][k]["polygon"]).buffer(0) for k in L2_ORDER}
    D = {k: Polygon(spec["districts"][k.lower()]["polygon"]).buffer(0) for k in twin.DISTRICTS}
    old = spec["bids"]; new = bid_ranges(D, areas)
    for k in ("ranges", "keep", "today_new_buildings_no_solar"):
        if old.get(k) != new.get(k):
            print(f"[bids] note: {k} differs from the city.json of the full build (outlines rounded to 1 m): keeping the old one")
            new[k] = old[k]
    spec["bids"] = new
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(dump_compact(spec) + "\n")
    print(f"[bids] {p}: ranges2 {new['ranges2']}, existing_overture {new['existing_overture']['by_district']}")


def write_readme():
    rows = []
    for root, _, files in os.walk(frames.OUT):
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            if fn.startswith(".") or fn.endswith(".tmp"):
                continue
            relp = os.path.relpath(fp, frames.OUT)
            n = ""
            if fn.endswith(".geojson"):
                with open(fp, encoding="utf-8") as f:
                    n = sum(1 for line in f if line.startswith('{"type":"Feature"'))
            rows.append((relp, n, os.path.getsize(fp)))
    rows.sort()
    with open(frames.out("README.md"), "w", encoding="utf-8") as f:
        f.write("# Уровень 0 (w34): правда о земле — файлы\n\n")
        f.write("Все координаты — система Unity двойника: X = E − 663000, Z = N − 4830000 (UTM 43N), метры. "
                "Пересобрать: `python3 -I tools/map/geo/fetch_overture.py` (открытые данные), затем `python3 -I tools/map/geo/build_city.py` "
                "(всё остальное и `tools/map/spec/city.json`). Подпись для данных Overture/OSM: «© OpenStreetMap contributors, Overture Maps Foundation».\n\n")
        f.write("- `osm/` — слои Overture (см. `osm/README.md`); `overture_raw/` — сырые выборки (lon/lat WKB, parquet).\n"
                "- `genplan/` — все слои `alatau_plan_utm43n_rel.geojson`, пересчитанные в Unity (сдвиг X − 517.314, Z + 7350.528).\n"
                "- `derived/` — районы (двойник + половины Growing + альтернатива geojson), вода, уровни Капшагая, посёлки, черновик магистралей и ЛРТ, стыки, высотные зоны.\n"
                "- `transform_proof.json` — доказательство пересчёта; `compare.md` — сравнение OSM и двойника; `city_overview.png`, `gate_overview.png` — проверочные картинки.\n\n")
        f.write("| Файл | Объектов | Размер |\n|---|---:|---:|\n")
        for relp, n, s in rows:
            if relp == "README.md":
                continue
            f.write(f"| `{relp}` | {n if n != '' else ''} | {s / 1e6:.2f} МБ |\n")


if __name__ == "__main__":
    main()
