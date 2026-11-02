"""Gate cartographer helpers (w47): paths, the moved Gate District quarter, open-data and twin readers.

Read-only inputs: tools/map/spec/{city,gate,norms,registry}.json, the level-0 layers (frames.OUT, Overture/OSM in the Unity
frame), the twin (TWIN: StreamingAssets/twin/roads.json, Resources/Landmarks/gate_district.bytes,
Resources/Film/Traffic/gate_roads.json). Nothing here writes anywhere.
"""
import gzip
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(MAP, "geo"))
import numpy as np  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402

import frames  # noqa: E402
import layers  # noqa: E402
import terrain  # noqa: E402

SPEC_DIR = os.path.join(MAP, "spec")
OUT = os.environ.get("ALATAU_MAP_OUT", "/mnt/project-files/alatau_stage7/out")
TWIN = os.environ.get("ALATAU_TWIN", "/mnt/user-data/uploads/AlatauCity_DigitalTwin/UnityProject/Assets")
ATTRIBUTION = frames.ATTRIBUTION

# CONTRACT §7: Iconic and the whole Gate District quarter move rigidly from (−3170, −19080) to (−3500, −19500), yaw 270.
ICONIC_OLD = (-3170.0, -19080.0)
ICONIC = (-3500.0, -19500.0)
DELTA = (ICONIC[0] - ICONIC_OLD[0], ICONIC[1] - ICONIC_OLD[1])
YAW = 270.0
EXISTING = [2025, 2025, 2025, 2025]


def spec(name):
    with open(os.path.join(SPEC_DIR, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def spec_v0():
    """The approved level-0 Gate scheme (spec/gate.json v0 as of 913c1c6), frozen next to the builders: spec/gate.json is v1 now."""
    with open(os.path.join(HERE, "gate_v0.json"), encoding="utf-8") as f:
        return json.load(f)


def twin_path(rel):
    return os.path.join(TWIN, rel)


def local_to_world(lx, lz):
    """Quarter local frame (gate_district.bytes, gate_roads.json) → Unity world at the moved Iconic, yaw 270:
    world = (X0 − z_local, Z0 + x_local) (checked against the quarter mask and the road stubs)."""
    return ICONIC[0] - np.asarray(lz, float), ICONIC[1] + np.asarray(lx, float)


def gate_district_bytes():
    """Parse gate_district.bytes (gzip 'QGD1'): mesh, tags, trees and the ground mask (code_map.md §2)."""
    b = gzip.decompress(open(twin_path("Resources/Landmarks/gate_district.bytes"), "rb").read())
    if b[:4] != b"QGD1":
        raise ValueError("gate_district.bytes: bad magic")
    o = 4
    nv, ni = struct.unpack_from("<ii", b, o); o += 8
    p = np.frombuffer(b, "<f4", nv * 3, o).reshape(-1, 3); o += nv * 12
    o += nv * 3                                  # normals i8×3
    o += nv * 4                                  # u f32
    tg = np.frombuffer(b, "u1", nv, o); o += nv
    idx = np.frombuffer(b, "<u4", ni, o).reshape(-1, 3); o += ni * 4
    nt = struct.unpack_from("<i", b, o)[0]; o += 4
    trees = np.frombuffer(b, "<f4", nt * 5, o).reshape(-1, 5); o += nt * 20
    W, HALF = struct.unpack_from("<if", b, o); o += 8
    mask = np.frombuffer(b, "u1", W * W, o).reshape(W, W)
    return dict(p=p, tg=tg, idx=idx, trees=trees, W=W, HALF=HALF, mask=mask)


def keep_radius():
    """Radius of the quarter's ground (metres, local frame centred on Iconic): the outermost cell of its mask (> 127) and half
    a cell, as IconicDistrict.AreaRadius cuts the model's ground in Unity (w46, integ 9864a4f: 335.7 m); and the mask's area."""
    d = gate_district_bytes()
    cell = 2 * d["HALF"] / d["W"]
    ys, xs = np.nonzero(d["mask"] > 127)
    lx = (xs + 0.5) * cell - d["HALF"]; lz = (ys + 0.5) * cell - d["HALF"]
    r = float(np.hypot(lx, lz).max()) + cell * 0.5
    return r, len(xs) * cell * cell


KEEP_SEGS = 256          # IconicDistrict clips on a 512-gon; every second vertex of it: sides ≤ 2 cm inside its edge


def keep_outline(r, margin=0.5):
    """The quarter's keep: the round of its ground (radius r) and, where a model building stands past it, that building's own
    outline (walls, roofs and coping projected on the ground) + margin. Returns (shapely polygon, [bulge polygons])."""
    from shapely.geometry import Polygon as _P
    from shapely.ops import unary_union as _U
    d = gate_district_bytes()
    tri = d["p"][d["idx"]]
    tall = tri[:, :, 1].max(1) >= 1.0                       # IconicDistrict: a triangle under 1 m is ground
    far = np.hypot(tri[:, :, 0], tri[:, :, 2]).max(1) > r - 60.0
    parts = []
    for t in np.nonzero(tall & far)[0]:
        x, z = local_to_world(tri[t][:, 0], tri[t][:, 2])
        parts.append(_P(list(zip(x, z))).buffer(0.05, join_style=2))
    rnd = _P(circle(ICONIC[0], ICONIC[1], r, KEEP_SEGS))
    if not parts:
        return rnd, []
    out = _U(parts).buffer(margin - 0.05, join_style=2).simplify(0.05).difference(rnd)
    bulges = [g.simplify(0.05) for g in getattr(out, "geoms", [out]) if g.area > 1.0]
    if not bulges:
        return rnd, []
    keep = _U([rnd] + [g.buffer(0.01) for g in bulges]).buffer(0)
    return keep, bulges


def circle(cx, cz, r, n=72):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return [[round(cx + r * math.cos(t), 1), round(cz + r * math.sin(t), 1)] for t in a]


def gate_roads_world():
    """Centrelines of the quarter's own streets (Resources/Film/Traffic/gate_roads.json), moved: [(oneway, Nx2 array)]."""
    with open(twin_path("Resources/Film/Traffic/gate_roads.json"), encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for r in d["roads"]:
        p = np.array(r["p"], float).reshape(-1, 3)
        x, z = local_to_world(p[:, 0], p[:, 2])
        out.append((int(r.get("o", 0)), np.stack([x, z], 1)))
    return out


def twin_roads():
    with open(twin_path("StreamingAssets/twin/roads.json"), encoding="utf-8") as f:
        return json.load(f)


def twin_edges_in(poly_or_box, roads=None):
    """[(index, edge dict, LineString)] of current twin road edges touching the given geometry."""
    roads = roads or twin_roads()
    out = []
    bx = poly_or_box.bounds
    for i, e in enumerate(roads["edges"]):
        g = np.array(e["g"], float).reshape(-1, 2)
        if g[:, 0].max() < bx[0] or g[:, 0].min() > bx[2] or g[:, 1].max() < bx[1] or g[:, 1].min() > bx[3]:
            continue
        ls = LineString(g)
        if ls.intersects(poly_or_box):
            out.append((i, e, ls))
    return out


def layer_in(name, geom):
    """[(shapely geometry, props)] of a level-0 layer touching geom (Unity frame)."""
    gs, ps = layers.load(name)
    bx = geom.bounds
    out = []
    for g, p in zip(gs, ps):
        b = g.bounds
        if b[2] < bx[0] or b[0] > bx[2] or b[3] < bx[1] or b[1] > bx[3]:
            continue
        if g.intersects(geom):
            out.append((g, p))
    return out


def height(x, z):
    return terrain.height(x, z)


def polyline_len(pts):
    P = np.asarray(pts, float)
    return float(np.hypot(*np.diff(P, axis=0).T).sum())


def r1(v):
    return round(float(v), 1)


def pts(line):
    """Round a sequence of (x, z) to 0.1 m lists."""
    return [[r1(x), r1(z)] for x, z in line]
