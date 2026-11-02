"""Readers for the twin's own data (read-only): AQL1 layers, district outlines, buildings, roads, LRT, genplan geojson.

Everything is returned in the Unity frame (X east, Z north, metres). See frames.py for the paths."""
import json
import struct

import numpy as np

import frames

DISTRICTS = ["Gate", "Golden", "Growing", "Green"]
DISTRICT_AREA_HA_CODE = {"Gate": 3988, "Golden": 15660, "Growing": 36622, "Green": 31730}   # CityStats.cs:12


def read_aql(path):
    """AQL1 layer (AlatauCityBuilder.ReadLayer): u16 nameLen, name, u8 kind, i32 nv, i32 nt, f32 verts[nv*3], u32 tris[nt*3],
    u8 col[nt], u16 year[nt], i32 bid[nt]. Vertices are (x, y, z) Unity."""
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] != b"AQL1":
        raise ValueError(path + ": not AQL1")
    n = struct.unpack_from("<i", b, 4)[0]
    o = 8
    out = []
    for _ in range(n):
        ln = struct.unpack_from("<H", b, o)[0]; o += 2
        name = b[o:o + ln].decode("utf8"); o += ln
        kind = b[o]; o += 1
        nv, nt = struct.unpack_from("<ii", b, o); o += 8
        V = np.frombuffer(b, dtype="<f4", count=nv * 3, offset=o).reshape(-1, 3); o += nv * 12
        T = np.frombuffer(b, dtype="<u4", count=nt * 3, offset=o).reshape(-1, 3); o += nt * 12
        col = np.frombuffer(b, dtype="u1", count=nt, offset=o); o += nt
        yr = np.frombuffer(b, dtype="<u2", count=nt, offset=o); o += nt * 2
        bid = np.frombuffer(b, dtype="<i4", count=nt, offset=o); o += nt * 4
        out.append({"name": name, "kind": kind, "V": V, "T": T, "col": col, "year": yr, "bid": bid})
    return out


_infra = None


def infra_layers():
    global _infra
    if _infra is None:
        _infra = {l["name"]: l for l in read_aql(frames.asset("CityData/layer_infrastructure.bytes"))}
    return _infra


def district_outlines_raw():
    """The «<District> District boundary» curtains of layer_infrastructure.bytes. Each is a vertical wall: the first half of the
    vertices is the outline at the ground, the second half the same points lifted. Returns {name: Polygon} (Unity frame)."""
    from shapely.geometry import Polygon
    L = infra_layers()
    res = {}
    for k in DISTRICTS:
        V = L[k + " District boundary"]["V"]
        n = len(V) // 2
        p = Polygon(V[:n][:, [0, 2]].astype(float))
        res[k] = p if p.is_valid else p.buffer(0)
    return res


def district_polygons():
    """Twin district outlines made into a clean partition: the slivers (≤ 5 m wide, 4.6 ha in all) left between neighbouring
    outlines are given to the neighbour with the longest shared edge. Returns ({name: Polygon}, report)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    raw = district_outlines_raw()
    U = unary_union(list(raw.values()))
    closed = U.buffer(5, join_style="mitre").buffer(-5, join_style="mitre")
    filled = Polygon(closed.exterior) if closed.geom_type == "Polygon" else closed
    gaps = filled.difference(U)
    pieces = [g for g in getattr(gaps, "geoms", [gaps]) if g.area > 0.5]
    add = {k: [] for k in raw}
    rep = []
    for g in pieces:
        shared = {k: g.boundary.intersection(raw[k].buffer(0.5)).length for k in raw}
        k = max(shared, key=shared.get)
        if shared[k] <= 0:
            continue
        add[k].append(g)
        rep.append({"area_ha": round(g.area / 1e4, 2), "to": k, "at": [round(c) for c in g.centroid.coords[0]]})
    res = {}
    for k in raw:
        p = unary_union([raw[k]] + add[k]) if add[k] else raw[k]
        if p.geom_type == "MultiPolygon":            # keep the main body, the rest are hair-thin crumbs
            p = max(p.geoms, key=lambda q: q.area)
        res[k] = Polygon(p.exterior) if p.geom_type == "Polygon" else p
    return res, rep


def city_outline(dist=None):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if dist is None:
        dist, _ = district_polygons()
    u = unary_union(list(dist.values())).buffer(0.5, join_style="mitre").buffer(-0.5, join_style="mitre")
    return Polygon(u.exterior) if u.geom_type == "Polygon" else u


def genplan_raw():
    """The maket geojson as {name: (shapely geometry in its rel frame, properties)}."""
    from shapely.geometry import shape
    g = json.load(open(frames.PLAN_GEOJSON, encoding="utf-8"))
    return {f["properties"]["name"]: (shape(f["geometry"]), f["properties"]) for f in g["features"]}


def genplan_unity():
    return {k: (frames.geom_rel_to_unity(g), p) for k, (g, p) in genplan_raw().items()}


def clip_region(buffer_m=5000.0):
    """City (twin outline ∪ genplan city outline) + buffer, Unity frame. Used to clip the open map data."""
    from shapely.ops import unary_union
    gp = genplan_unity()
    return unary_union([city_outline(), gp["city"][0]]).buffer(buffer_m)


def buildings():
    import pandas as pd
    return pd.read_csv(frames.asset("CityData/buildings.csv"))


def roads():
    return json.load(open(frames.asset("StreamingAssets/twin/roads.json"), encoding="utf-8"))


def lrt_routes():
    return json.load(open(frames.asset("Resources/Landmarks/lrt_routes.json"), encoding="utf-8"))


def construction_lrt():
    return json.load(open(frames.asset("StreamingAssets/twin/construction.json"), encoding="utf-8"))["lrt"]


def road_lines(classes=None, max_year=None, scen=0):
    """roads.json edges as [(LineString, edge_index, class, years)]."""
    from shapely.geometry import LineString
    r = roads()
    res = []
    for i, e in enumerate(r["edges"]):
        if classes and e["c"] not in classes:
            continue
        if max_year is not None and e["y"][scen] > max_year:
            continue
        g = e["g"]
        pts = list(zip(g[0::2], g[1::2]))
        if len(pts) < 2:
            continue
        res.append((LineString(pts), i, e["c"], e["y"]))
    return res


def footprints(bids=None):
    """Convex footprints of buildings from layer_buildings.bytes (the twin's meshes), {bid: Polygon} (Unity frame).
    bids: iterable of bids to keep (None = all)."""
    import shapely
    want = None if bids is None else np.zeros(70000, bool)
    if want is not None:
        want[np.asarray(list(bids), int)] = True
    P, Bb = [], []
    for L in read_aql(frames.asset("CityData/layer_buildings.bytes")):
        if len(L["T"]) == 0:
            continue
        b = np.repeat(L["bid"], 3)
        idx = L["T"].reshape(-1)
        m = (b >= 0) if want is None else (b >= 0) & want[np.clip(b, 0, 69999)]
        if not m.any():
            continue
        P.append(L["V"][idx[m]][:, [0, 2]].astype(float))
        Bb.append(b[m])
    if not P:
        return {}
    P = np.vstack(P); Bb = np.concatenate(Bb)
    o = np.argsort(Bb, kind="stable")
    P, Bb = P[o], Bb[o]
    ub, start = np.unique(Bb, return_index=True)
    inv = np.repeat(np.arange(len(ub)), np.diff(np.append(start, len(Bb))))
    mp = shapely.multipoints(P, indices=inv)
    hull = shapely.convex_hull(mp)
    return {int(b): h for b, h in zip(ub, hull)}
