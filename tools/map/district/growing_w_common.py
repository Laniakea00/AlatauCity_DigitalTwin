"""Growing-West cartographer helpers (w52): paths, the level-0 scheme, open-data readers, years and geometry helpers.

Read-only inputs: tools/map/spec/{city,norms,registry}.json, the frozen level-0 scheme district/growing_w_v0.json, the level-0
layers (Overture/OSM in the Unity frame), the twin (buildings.csv through gen_blocks_lots.existing_houses). Nothing here writes.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.abspath(os.path.join(HERE, ".."))
for _p in (HERE, os.path.join(MAP, "geo"), os.path.join(MAP, "gen")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import layers  # noqa: E402
import terrain  # noqa: E402

D = "growing_w"
SPEC_DIR = os.path.join(MAP, "spec")
OUT = os.environ.get("ALATAU_MAP_OUT", "/mnt/project-files/alatau_stage7/out")
MODEL = "модель qTwin"
ATTRIBUTION = "© OpenStreetMap contributors, Overture Maps Foundation"
EXISTING = [2025, 2025, 2025, 2025]
W35_INFRA = "/mnt/project-files/alatau_stage7/level0/w35/overture/infrastructure.parquet"


def spec(name):
    with open(os.path.join(SPEC_DIR, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def spec_v0():
    """The approved level-0 scheme (spec/growing_w.json v0 as of integ 5cf9839), frozen next to the builders: spec/growing_w.json
    is v1 now."""
    with open(os.path.join(HERE, "growing_w_v0.json"), encoding="utf-8") as f:
        return json.load(f)


CITY = spec("city")
REG = {r["id"]: r for r in spec("registry")["rows"]}
POLY = Polygon(CITY["districts"][D]["polygon"]).buffer(0)
NEIGH = {k: Polygon(v["polygon"]).buffer(0) for k, v in CITY["districts"].items()
         if k not in (D, "growing") and isinstance(v, dict) and v.get("polygon")}

# ----------------------------------------------------------------------------------------------------- years (4 values)
Y0, Y1, AFTER = 2025, 2050, 2099


def eff_year(year, use, scen):
    """Port of twin_common.effective_year (UnityProject/Tools/twin_gen/twin_common.py), as lib/years.py."""
    if year <= Y0:
        return year
    dy = year - Y0
    if scen == "fast":
        return Y0 + max(1, int(round(dy * 0.75)))
    if scen == "slow":
        e = Y0 + int(round(dy * 1.3))
        return AFTER if e > Y1 else e
    if scen == "infra":
        return year + 2 if use == "housing" and year <= 2036 else year
    return year


def Y4(base, use="road"):
    base = int(base)
    if base <= Y0:
        return list(EXISTING)
    return [eff_year(base, use, s) for s in ("base", "fast", "slow", "infra")]


# ----------------------------------------------------------------------------------------------------- open data
def layer_in(name, geom):
    """[(shapely geometry, props)] of a level-0 layer touching geom (Unity frame)."""
    gs, ps = layers.load(name)
    idx = np.flatnonzero(shapely.intersects(gs, geom))
    return [(gs[i], ps[i]) for i in idx]


def height(x, z):
    return float(terrain.height(x, z))


def osm_voltage(ids8):
    """{id8: (kv, source_tags)} from the raw Overture infrastructure of level 0 (w35)."""
    import pyarrow.parquet as pq
    t = pq.read_table(W35_INFRA, columns=["id", "class", "source_tags"]).to_pylist()
    out = {}
    for r in t:
        k = r["id"][:8]
        if k in ids8:
            tags = dict(r.get("source_tags") or [])
            v = tags.get("voltage")
            kv = None
            if v:
                try:
                    kv = max(int(x) for x in str(v).replace("_", ";").split(";") if x.strip().isdigit()) / 1000.0
                except ValueError:
                    kv = None
            out[k] = (kv, tags)
    return out


_HOUSES = None


def houses():
    """Existing houses of the district (+80 m): the land tool's own reader (twin existing_osm rows + Overture-only)."""
    global _HOUSES
    if _HOUSES is None:
        from gen_blocks_lots import existing_houses
        _HOUSES = existing_houses(POLY.buffer(80), Polygon())
    return _HOUSES


_HT = None


def houses_hit(geom):
    global _HT
    hs = houses()
    if _HT is None:
        _HT = shapely.STRtree([h["fp"] for h in hs])
    return [hs[i]["fp"] for i in _HT.query(geom, predicate="intersects")]


def water():
    """(polygons, lines) of the water layer near the district (swimming pools left out)."""
    W = layer_in("water", POLY.buffer(300))
    pol = unary_union([g for g, p in W if g.geom_type in ("Polygon", "MultiPolygon") and p.get("class") != "swimming_pool"])
    lin = unary_union([g for g, p in W if g.geom_type in ("LineString", "MultiLineString")])
    return pol, lin, W


# ----------------------------------------------------------------------------------------------------- geometry
def r1(v):
    return round(float(v), 1)


def pts(line):
    return [[r1(x), r1(z)] for x, z in (line.coords if hasattr(line, "coords") else line)]


def poly_pts(g):
    g = g.buffer(0)
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda q: q.area)
    return [[r1(x), r1(z)] for x, z in list(g.exterior.coords)[:-1]]


def polyline_len(P):
    P = np.asarray(P, float)
    return float(np.hypot(*np.diff(P, axis=0).T).sum())


def fillet(pts_, R, step_deg=6.0):
    """Polyline with every inner corner replaced by a circular arc of radius R (shortened where segments are short)."""
    P = [np.array(p, float) for p in pts_]
    Q = [P[0]]
    for i in range(1, len(P) - 1):
        u = P[i] - Q[-1]
        v = P[i + 1] - P[i]
        if np.linalg.norm(u) < 1e-6:
            continue
        cr = abs(u[0] * v[1] - u[1] * v[0]) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9)
        if cr > math.sin(math.radians(0.5)) or np.dot(u, v) < 0:
            Q.append(P[i])
    Q.append(P[-1])
    P = Q
    if len(P) < 3:
        return [tuple(p) for p in P]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        u = (a - b) / np.linalg.norm(a - b)
        v = (c - b) / np.linalg.norm(c - b)
        th = math.acos(float(np.clip(np.dot(u, v), -1, 1)))
        if abs(math.pi - th) < 1e-3:
            out.append(b)
            continue
        defl = math.pi - th
        T = R * math.tan(defl / 2)
        T = min(T, 0.45 * np.linalg.norm(a - b), 0.45 * np.linalg.norm(c - b))
        r = T / math.tan(defl / 2)
        p1 = b + u * T
        p2 = b + v * T
        bis = (u + v) / np.linalg.norm(u + v)
        cen = b + bis * (r / math.sin(th / 2))
        a1 = math.atan2(*(p1 - cen)[::-1])
        a2 = math.atan2(*(p2 - cen)[::-1])
        da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        n = max(2, int(abs(math.degrees(da)) / step_deg) + 1)
        for k in range(n + 1):
            t = a1 + da * k / n
            out.append(cen + r * np.array([math.cos(t), math.sin(t)]))
    out.append(P[-1])
    q = [out[0]]
    for p in out[1:]:
        if np.linalg.norm(np.asarray(p) - np.asarray(q[-1])) > 0.5:
            q.append(p)
    return [(float(p[0]), float(p[1])) for p in q]


def on_line(L, x=None, z=None):
    """Point of polyline L at the given x (or z): the first crossing of a vertical (horizontal) line."""
    L = L if isinstance(L, LineString) else LineString(L)
    b = L.bounds
    if x is not None:
        cut = LineString([(x, b[1] - 1e4), (x, b[3] + 1e4)])
    else:
        cut = LineString([(b[0] - 1e4, z), (b[2] + 1e4, z)])
    h = L.intersection(cut)
    if h.is_empty:
        return None
    q = h if h.geom_type == "Point" else min(h.geoms, key=lambda g: L.project(g))
    return (q.x, q.y)
