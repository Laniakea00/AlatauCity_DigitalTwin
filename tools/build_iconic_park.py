# The grounds around Iconic Complex (feedback 12.10.2026): while the tower rises, the steppe around it turns into a finished city
# centre — pavements along every street, paved forecourts at the buildings, lawns with paths, tree rows and groves, a pool.
# The blocks are cut by the streets of roads.json (the carriageways and pavements of the film roads stay on top), the plot of the
# landmark itself is left out (it has its own square). Every block has a stage (0 near the tower … 1 at the edge): the works spread
# outwards. Trees keep off building footprints (the city of 2050) and off the paths.
# Out: Resources/Landmarks/iconic_park.json  {cx, cz, tris:[x0,z0,x1,z1,x2,z2,mat,stage]*, trees:[x,z,h,stage]*}
import sys, json, math, pickle
import numpy as np, pandas as pd
import shapely
from shapely.geometry import Polygon, LineString, Point, MultiPolygon, box
from shapely.ops import unary_union
from shapely.affinity import rotate, translate

SRC = sys.argv[1]; OUT = sys.argv[2]
CX, CZ, YAW, PW, PD = -2567.0, -20654.0, 105.2, 270.0, 200.0
R = 360.0
def rect(cx, cz, w, d, yaw):
    a = math.radians(yaw); ca, sa = math.cos(a), math.sin(a)
    return Polygon([(cx + u * ca + v * sa, cz - u * sa + v * ca) for u, v in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))])
pad = rect(CX, CZ, PW + 6, PD + 6, YAW)
region = rect(CX, CZ, PW + 2 * R, PD + 2 * R, YAW).buffer(-60).buffer(60)

roads = json.load(open(SRC + '/Assets/StreamingAssets/twin/roads.json'))['edges']
HALF = {'highway': 11.5, 'ring': 9.5, 'main': 7.5 + 3.5, 'street': 4 + 2.4}
cut = []
for e in roads:
    g = np.array(e['g'], float).reshape(-1, 2)
    if np.hypot(g[:, 0] - CX, g[:, 1] - CZ).min() > R * 2: continue
    cut.append(LineString(g).buffer(HALF[e['c']] + 0.5, cap_style=2, join_style=2))
cut = unary_union(cut)
# the LRT viaduct crosses the area: under it a paved strip, no lawns or trees (the piers stand there)
lrt = []
for r in json.load(open(SRC + '/Assets/Resources/Landmarks/lrt_routes.json'))['routes']:
    P2 = np.array(r['pts'], float).reshape(-1, 2)
    if len(P2) >= 2 and np.hypot(P2[:, 0] - CX, P2[:, 1] - CZ).min() < R * 2: lrt.append(LineString(P2).buffer(18.0, cap_style=2))
lrt = unary_union(lrt) if lrt else Polygon()
under_lrt = region.intersection(lrt).difference(cut).difference(pad)
blocks = region.difference(cut).difference(pad).difference(lrt)
blocks = [p for p in (blocks.geoms if hasattr(blocks, 'geoms') else [blocks]) if p.area > 300]

foot = pickle.load(open(sys.argv[3] if len(sys.argv) > 3 else 'foot_new.pkl', 'rb'))   # footprints near Iconic (shapely polygons) from the new layer_buildings
fps = [g for g in foot if g.distance(Point(CX, CZ)) < R * 2]
fp_u = unary_union(fps) if fps else Polygon()
apron = fp_u.buffer(9, join_style=2)

PAVE, PLANT, WATER = 4, 6, 7
polys = []          # (polygon, mat, stage)
trees = []
if not under_lrt.is_empty: polys.append((under_lrt, PAVE, 0.4))
rng = np.random.default_rng(7)
for P in blocks:
    c = P.centroid; st = float(np.clip((c.distance(Point(CX, CZ)) - 170) / 330, 0, 1))
    walk = P.difference(P.buffer(-6.5, join_style=2))
    inner = P.buffer(-6.5, join_style=2)
    polys.append((walk, PAVE, st))
    if inner.is_empty or inner.area < 250:
        if not inner.is_empty: polys.append((inner, PAVE, st))
        continue
    fore = inner.intersection(apron)                     # forecourts at the buildings
    lawn = inner.difference(apron)
    # paths: the block's two axes (from its minimum rectangle) and, in big blocks, a diagonal
    mr = inner.minimum_rotated_rectangle; cs = list(mr.exterior.coords)[:4]
    e0 = np.subtract(cs[1], cs[0]); e1 = np.subtract(cs[2], cs[1])
    paths = []
    for ev in (e0, e1):
        L = np.linalg.norm(ev)
        if L > 70:
            u = ev / L; paths.append(LineString([(c.x - u[0] * 600, c.y - u[1] * 600), (c.x + u[0] * 600, c.y + u[1] * 600)]).buffer(2.4, cap_style=2))
    if inner.area > 14000:
        d = (e0 + e1) / np.linalg.norm(e0 + e1); paths.append(LineString([(c.x - d[0] * 600, c.y - d[1] * 600), (c.x + d[0] * 600, c.y + d[1] * 600)]).buffer(1.8, cap_style=2))
    pathU = unary_union(paths) if paths else Polygon()
    pool = Polygon()
    if lawn.area > 9000:
        pc = lawn.representative_point() if not lawn.contains(c) else c
        cand = Point(pc.x, pc.y).buffer(1).envelope
        ang = math.degrees(math.atan2(e0[1], e0[0]))
        pr = rotate(box(pc.x - 24, pc.y - 8, pc.x + 24, pc.y + 8), ang, origin=(pc.x, pc.y))
        if lawn.buffer(-6).contains(pr) and not pr.intersects(apron): pool = pr
    paved_lawn = lawn.intersection(pathU)
    green = lawn.difference(pathU).difference(pool.buffer(3))
    polys += [(fore, PAVE, st), (paved_lawn, PAVE, st), (green, PLANT, st)]
    if not pool.is_empty:
        polys += [(pool.buffer(3).difference(pool), PAVE, st), (pool, WATER, st)]
    # trees: a row along the pavement, groves in the lawns
    keep_off = fp_u.buffer(7).union(pathU.buffer(2)).union(pool.buffer(5))
    ring = P.buffer(-4.2, join_style=2).exterior if not P.buffer(-4.2).is_empty and P.buffer(-4.2).geom_type == 'Polygon' else None
    if ring is not None:
        L = ring.length; n = int(L / 10)
        for k in range(n):
            q = ring.interpolate(k * 10.0)
            if not keep_off.contains(q): trees.append((q.x, q.y, float(rng.uniform(9, 13)), st))
    g2 = green.buffer(-5)
    if not g2.is_empty:
        x0, z0, x1, z1 = g2.bounds
        for x in np.arange(x0, x1, 15.0):
            for z in np.arange(z0, z1, 15.0):
                q = Point(x + rng.uniform(-4, 4), z + rng.uniform(-4, 4))
                if rng.random() < 0.45 and g2.contains(q) and not keep_off.contains(q): trees.append((q.x, q.y, float(rng.uniform(8, 14)), st))

def tris_of(g, cell=36.0):
    out = []
    g = g.simplify(0.25)
    x0, z0, x1, z1 = g.bounds; pieces = []
    for x in np.arange(math.floor(x0 / cell) * cell, x1, cell):           # cut into terrain-sized cells: the ground follows the terrain
        for z in np.arange(math.floor(z0 / cell) * cell, z1, cell):
            q = g.intersection(box(x, z, x + cell, z + cell))
            if not q.is_empty: pieces += list(q.geoms) if hasattr(q, 'geoms') else [q]
    for p in pieces:
        if p.geom_type != 'Polygon' or p.area < 0.5: continue
        tr = shapely.constrained_delaunay_triangles(p)
        for t in tr.geoms:
            out.append(np.array(t.exterior.coords)[:3])
    return out
def subdiv(t, m=11.0):
    a, b_, c = t; L = max(np.linalg.norm(a - b_), np.linalg.norm(b_ - c), np.linalg.norm(c - a))
    if L <= m: return [t]
    ab, bc, ca = (a + b_) / 2, (b_ + c) / 2, (c + a) / 2
    return subdiv(np.array([a, ab, ca]), m) + subdiv(np.array([ab, b_, bc]), m) + subdiv(np.array([ca, bc, c]), m) + subdiv(np.array([ab, bc, ca]), m)
out = []
for g, mat, st in polys:
    if g.is_empty: continue
    for t in tris_of(g):
        for s in [t]:
            out += [round(float(v), 2) for v in s.ravel()] + [mat, round(st, 3)]
json.dump({'cx': CX, 'cz': CZ, 'tris': out, 'trees': [round(float(v), 2) for t in trees for v in t]}, open(OUT, 'w'), separators=(',', ':'))
print('blocks', len(blocks), 'triangles', len(out) // 8, 'trees', len(trees))
# (the existing sheds inside the area are added to hide_extra with code 27 — gone from 2027, when the works start; see relocate_industry run log)
