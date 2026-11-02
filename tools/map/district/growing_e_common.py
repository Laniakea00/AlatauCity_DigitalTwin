"""Growing-East cartographer helpers (w53, level 2): paths, the frozen level-0 scheme, open-data readers, year and
geometry helpers shared by growing_e_zones.py, growing_e_net.py, growing_e_build.py and growing_e_check.py.

Read-only inputs: tools/map/spec/{city,norms,registry}.json, district/growing_e_v0.json (the approved level-0 scheme, frozen
next to the builders because spec/growing_e.json is v1 now), the level-0 layers (Overture/OSM in the Unity frame) and the twin
(TWIN). Nothing here writes anywhere. Unity frame: X east, Z north.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.abspath(os.path.join(HERE, ".."))
for _p in (os.path.join(MAP, "geo"), os.path.join(MAP, "gen")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import numpy as np  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402

import frames  # noqa: E402
import layers  # noqa: E402
import terrain  # noqa: E402

D = "growing_e"
SPEC_DIR = os.path.join(MAP, "spec")
OUT = os.environ.get("ALATAU_MAP_OUT", "/mnt/project-files/alatau_stage7/out")
TWIN = os.environ.get("ALATAU_TWIN", "/mnt/user-data/uploads/AlatauCity_DigitalTwin/UnityProject/Assets")
ATTRIBUTION = frames.ATTRIBUTION
MODEL = "модель qTwin"
EXISTING = [2025, 2025, 2025, 2025]


def spec(name):
    with open(os.path.join(SPEC_DIR, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def spec_v0():
    """The approved level-0 scheme of Growing-East (spec/growing_e.json v0 as of integ 5cf9839), frozen next to the builders."""
    with open(os.path.join(HERE, "growing_e_v0.json"), encoding="utf-8") as f:
        return json.load(f)


CITY = spec("city")
NORMS = spec("norms")
REG = {r["id"]: r for r in spec("registry")["rows"]}
V0 = spec_v0()
DIST = Polygon(CITY["districts"][D]["polygon"]).buffer(0)

# ----------------------------------------------------------------------------------------------------- years (4 values)
Y0, Y1, AFTER = 2025, 2050, 2099


def eff_year(year, use, scen):
    """Port of twin_common.effective_year (UnityProject/Tools/twin_gen/twin_common.py), as gate_trial_build.eff_year."""
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
    return [eff_year(int(base), use, s) for s in ("base", "fast", "slow", "infra")]


# ----------------------------------------------------------------------------------------------------- geometry helpers
def fillet(pts, R, step_deg=6.0):
    """Polyline with every inner corner replaced by a circular arc of radius R (shortened where segments are short)."""
    P = [np.array(p, float) for p in pts]
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
        d = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        n = max(2, int(abs(math.degrees(d)) / step_deg) + 1)
        for k in range(n + 1):
            t = a1 + d * k / n
            out.append(cen + r * np.array([math.cos(t), math.sin(t)]))
    out.append(P[-1])
    res = [tuple(out[0])]
    for p in out[1:]:
        if math.hypot(p[0] - res[-1][0], p[1] - res[-1][1]) > 0.3:
            res.append(tuple(p))
    return res


def poly_pts(p, nd=1):
    p = p.buffer(0)
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda q: q.area)
    return [[round(x, nd), round(z, nd)] for x, z in list(p.exterior.coords)[:-1]]


def simple_parts(g, min_area=300.0):
    """Polygons without holes (the spec polygon format has no holes): split by a vertical line through each hole."""
    out = []
    stack = [g]
    while stack:
        q = stack.pop().buffer(0)
        if q.is_empty:
            continue
        if q.geom_type in ("MultiPolygon", "GeometryCollection"):
            stack += [p for p in q.geoms if p.geom_type == "Polygon"]
            continue
        if q.area < min_area:
            continue
        if not q.interiors:
            out.append(q)
            continue
        hx = Polygon(q.interiors[0]).representative_point().x
        x0, z0, x1, z1 = q.bounds
        stack += [q.intersection(box(x0 - 1, z0 - 1, hx, z1 + 1)), q.intersection(box(hx, z0 - 1, x1 + 1, z1 + 1))]
    return sorted(out, key=lambda p: -p.area)


def rules(floors, cap, far, block, split, park_type, homes, jobs, setback=6.0, per_home=1.0, office=None, retail=None):
    """v1 zone rules (CONTRACT §3). parking.per_home 1.0: residential.parking_per_apartment, class III min (С08-11); office and
    retail parking None while malls.parking_office / parking_mall are not_verified (CONTRACT §8 defaults)."""
    return {"floors": floors, "height_cap_m": cap, "far": far, "block_side_m": block, "setback_m": setback,
            "lot_split": split, "parking": {"per_home": per_home, "per_100m2_office": office, "per_100m2_retail": retail,
                                            "type": park_type}, "homes_per_ha": homes, "jobs_per_ha": jobs}


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


def P1(p):
    return [round(float(p[0]), 1), round(float(p[1]), 1)]


def pts(line):
    return [[r1(x), r1(z)] for x, z in line]


def lines_of(g):
    """LineStrings of a (multi)line geometry or a collection."""
    if g.is_empty:
        return []
    if g.geom_type == "LineString":
        return [g]
    return [q for q in getattr(g, "geoms", []) if q.geom_type == "LineString"]


def polys_of(g):
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [q for q in getattr(g, "geoms", []) if q.geom_type == "Polygon"]
