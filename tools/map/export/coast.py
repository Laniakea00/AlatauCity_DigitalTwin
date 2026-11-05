"""The beaches of Green on the Kapchagay shore (модель qTwin, owner 03.11.2026: «пляж, зоны отдыха и всё для туристов» at the
marina): along the water's edge inside the shore parks of the spec (zones wf_n_* — the marina, beaches and the spit — and
wf_c_* — the Green-City embankment) a sand beach, behind it a promenade, beach pavilions with cafés, lifeguard towers, piers
into the water, beach volleyball courts. The shore band below the reservoir's design flood takes parks, embankments, beaches
and piers without capital buildings (norms.json flood.floodplain_allowed): the pavilions are light seasonal ones.
Writes UnityProject/Assets/Resources/Landmarks/coast.json (drawn by Layers/CoastLayer.cs on the terrain):
  beaches   [{t: [x0,z0,x1,z1,x2,z2, ...] triangles of the sand, y: open year}]
  walks     [{p: [x,z, ...] promenade centre line, w: width m, y}]
  pavilions [{x, z, yaw, y}]   (yaw: Unity yaw facing the water)
  towers    [{x, z, yaw, y}]
  piers     [{x0, z0, x1, z1, y}]
  courts    [{x, z, yaw, y}]
usage: python tools/map/export/coast.py [spec/green.json] [out coast.json]"""
import json
import math
import os
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SPEC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "tools", "map", "spec", "green.json")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(REPO, "UnityProject", "Assets", "Resources", "Landmarks", "coast.json")

SHORE_ZONES = ("wf_n_", "wf_c_", "wf_e_")   # the shore parks that get beaches (wf_e_: the east shore, owner 05.11.2026: «Green — зона, где
#                                                реально будут много туристов … добавь туда пляж»)
BEACH_W = 42.0                        # m of sand from the water's edge
WALK_OFF, WALK_W = 50.0, 9.0          # promenade: its centre line off the water, its width
MIN_SHORE = 160.0                     # shore pieces shorter than this get no beach
PAVILION_STEP, TOWER_STEP, PIER_STEP, COURT_STEP = 260.0, 170.0, 650.0, 520.0
PIER_LEN = 90.0


def polys(g):
    return [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon" and not q.is_empty]


def lines(g):
    out = []
    for q in getattr(g, "geoms", [g]):
        if q.geom_type == "LineString" and q.length > 0:
            out.append(q)
        elif q.geom_type == "MultiLineString":
            out += list(q.geoms)
    return out


spec = json.load(open(SPEC, encoding="utf-8"))
zones = spec["zones"]
water = unary_union([Polygon(z["polygon"]).buffer(0) for z in zones if z["id"].startswith("water_")]).buffer(0)
shore_z = [z for z in zones if z["id"].startswith(SHORE_ZONES)]
land = unary_union([Polygon(z["polygon"]).buffer(0) for z in shore_z]).buffer(0)
# no beach on the marina's pad, on village land, nor on another zone's land
blocked = unary_union([Polygon(z["polygon"]).buffer(0) for z in zones
                       if z["id"] == "z_marina" or z["use"] == "village_existing"]).buffer(15.0)
ok = land.difference(water).difference(blocked).buffer(0)
year = {}
for z in shore_z:
    year[z["id"]] = int((z.get("years") or [2034])[0])
Y0 = min(year.values()) if year else 2034
Y0 = max(Y0, 2034)

# the water's edge within the shore parks, merged and smoothed (5 m)
edge = unary_union(lines(water.boundary.intersection(ok.buffer(3.0))))
edge = shapely.line_merge(edge) if edge.geom_type == "MultiLineString" else edge
pieces = [q.simplify(4.0) for q in lines(edge) if q.length >= MIN_SHORE]
total = sum(q.length for q in pieces)

# sand: the land within BEACH_W of the water, inside the parks; triangulated with its edges densified every 10 m (draped on the terrain)
band = water.buffer(BEACH_W, quad_segs=4).difference(water).intersection(ok).buffer(-0.5).buffer(0.5)
band = unary_union([q for q in polys(band) if q.area > 1500.0 and q.intersects(unary_union(pieces).buffer(2.0))]) if pieces else Polygon()
beaches = []
for q in polys(band):
    q = shapely.segmentize(q.simplify(2.0), 10.0)
    tris = shapely.constrained_delaunay_triangles(q)
    flat = []
    for t in getattr(tris, "geoms", []):
        if not q.buffer(0.05).contains(t.centroid):
            continue
        for x, z in list(t.exterior.coords)[:3]:
            flat += [round(x, 2), round(z, 2)]
    if flat:
        beaches.append({"t": flat, "y": Y0})

# promenade: the line WALK_OFF m off the water, inside the parks
walk_g = water.buffer(WALK_OFF, quad_segs=6).exterior if water.geom_type == "Polygon" else unary_union(
    [p.exterior for p in polys(water.buffer(WALK_OFF, quad_segs=6))])
walk = []
for q in lines(walk_g.intersection(ok.buffer(-WALK_W * 0.5 - 1.0))):
    if q.length < 120.0:
        continue
    q = q.simplify(3.0)
    walk.append({"p": [round(v, 2) for c in q.coords for v in c], "w": WALK_W, "y": Y0})


def along(L, step, off0):
    """Points every step along L (from off0), with the land-side normal (away from the water) and its yaw facing the water."""
    out = []
    s = off0
    while s < L.length - off0 * 0.5:
        p = L.interpolate(s)
        a, b = L.interpolate(max(s - 3.0, 0.0)), L.interpolate(min(s + 3.0, L.length))
        t = np.array([b.x - a.x, b.y - a.y]); t /= max(np.linalg.norm(t), 1e-9)
        n = np.array([-t[1], t[0]])
        if water.contains(Point(p.x + n[0] * 6.0, p.y + n[1] * 6.0)):
            n = -n                                  # n points to the land
        yaw = math.degrees(math.atan2(-n[0], -n[1]))   # local +z toward the water
        out.append((p, n, yaw))
        s += step
    return out


pav, tow, pier, court = [], [], [], []
occupied = []
for L in pieces:
    for p, n, yaw in along(L, PAVILION_STEP, PAVILION_STEP * 0.5):
        q = Point(p.x + n[0] * 30.0, p.y + n[1] * 30.0)
        if ok.buffer(-8.0).contains(q):
            pav.append({"x": round(q.x, 1), "z": round(q.y, 1), "yaw": round(yaw, 1), "y": Y0}); occupied.append(q)
    for p, n, yaw in along(L, TOWER_STEP, TOWER_STEP * 0.33):
        q = Point(p.x + n[0] * 11.0, p.y + n[1] * 11.0)
        if ok.contains(q) and all(q.distance(o) > 25.0 for o in occupied):
            tow.append({"x": round(q.x, 1), "z": round(q.y, 1), "yaw": round(yaw, 1), "y": Y0})
    for p, n, yaw in along(L, PIER_STEP, PIER_STEP * 0.4):
        a = (p.x - n[0] * 2.0, p.y - n[1] * 2.0); b = (p.x - n[0] * PIER_LEN, p.y - n[1] * PIER_LEN)
        if water.buffer(-3.0).contains(LineString([(p.x - n[0] * 8.0, p.y - n[1] * 8.0), b])):
            pier.append({"x0": round(a[0], 1), "z0": round(a[1], 1), "x1": round(b[0], 1), "z1": round(b[1], 1), "y": Y0})
    for p, n, yaw in along(L, COURT_STEP, COURT_STEP * 0.7):
        q = Point(p.x + n[0] * 24.0, p.y + n[1] * 24.0)
        if ok.buffer(-10.0).contains(q) and all(q.distance(o) > 30.0 for o in occupied):
            court.append({"x": round(q.x, 1), "z": round(q.y, 1), "yaw": round(yaw, 1), "y": Y0}); occupied.append(q)

doc = {"v": 1, "made_by": "tools/map/export/coast.py (модель qTwin)", "shore_km": round(total / 1000.0, 2),
       "beach_ha": round(band.area / 1e4, 1), "beaches": beaches, "walks": walk, "pavilions": pav, "towers": tow,
       "piers": pier, "courts": court}
open(OUT, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
print(f"coast: shore {total / 1000:.1f} km, sand {band.area / 1e4:.1f} ha in {len(beaches)} beaches, promenade "
      f"{sum(LineString(np.array(w['p']).reshape(-1, 2)).length for w in walk) / 1000:.1f} km, {len(pav)} pavilions, "
      f"{len(tow)} towers, {len(pier)} piers, {len(court)} courts → {OUT}")
