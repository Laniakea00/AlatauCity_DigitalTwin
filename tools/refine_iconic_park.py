# Refines the grounds around Iconic Complex (Resources/Landmarks/iconic_park.json, made by build_iconic_park.py), feedback 14.10.2026:
# the strip between the north-east side of the plot and the avenue was a bare forecourt with a gap where a short street end had been cut
# out (no road is drawn there, so the old base map showed through). The strip is rebuilt as a finished boulevard: the gap is closed,
# a walk along the edge, a double alley of trees along the plot, lawns with a path and cross paths, a round pool at the widest point.
# Usage: python3 refine_iconic_park.py <iconic_park.json in> <iconic_park.json out>
import sys, json, math
import numpy as np
import shapely
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union
from shapely.affinity import rotate

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC))
CX, CZ, YAW = d['cx'], d['cz'], 105.2
a = math.radians(YAW); ca, sa = math.cos(a), math.sin(a)
def to_loc(x, z): dx, dz = x - CX, z - CZ; return (dx * ca - dz * sa, dx * sa + dz * ca)     # (u along the long side, v across)
def to_world(u, v): return (CX + u * ca + v * sa, CZ - u * sa + v * ca)

T = np.array(d['tris'], float).reshape(-1, 8)
tri_loc = [Polygon([to_loc(r[0], r[1]), to_loc(r[2], r[3]), to_loc(r[4], r[5])]) for r in T]
U = unary_union([t.buffer(0.05) for t in tri_loc if t.area > 0.01])

# the strip: everything of the grounds next to the north-east side of the plot (v > 100), up to the avenue
win = box(-140, 100.5, 136, 185)
Z = U.intersection(win)
parts = [g for g in (Z.geoms if hasattr(Z, 'geoms') else [Z]) if g.area > 200 and g.distance(LineString([(-140, 103), (136, 103)])) < 3]
Z = unary_union(parts)
Zc = Z.buffer(9, join_style=2).buffer(-9, join_style=2).intersection(win).union(Z)            # close the gap of the street end
Zc = Zc.buffer(0)
print('strip area', round(Zc.area), 'parts', len(parts))

keep = [i for i, t in enumerate(tri_loc) if not Zc.contains(t.representative_point())]
trees = np.array(d['trees'], float).reshape(-1, 4)
keep_trees = [t for t in trees if not Zc.buffer(1).contains(Point(*to_loc(t[0], t[1])))]

PAVE, PLANT, WATER = 4, 6, 7
st = 0.05
polys, new_trees = [], []
walk = Zc.difference(Zc.buffer(-5, join_style=2))
inner = Zc.buffer(-5, join_style=2)
alley = inner.intersection(box(-200, 100, 200, 118))                    # the boulevard along the plot: paving with two rows of trees
rest = inner.difference(box(-200, 100, 200, 118.5))
vmin, vmax = 118.5, rest.bounds[3] if not rest.is_empty else 130
# a path through the lawns along the boulevard, cross paths every 45 m, a round pool where the lawns are widest
paths = []
if not rest.is_empty:
    vm = (rest.bounds[1] + rest.bounds[3]) * 0.5
    paths.append(LineString([(-200, vm), (200, vm)]).buffer(2.2, cap_style=2))
    for u in np.arange(-135, 136, 45): paths.append(LineString([(u, 100), (u, 200)]).buffer(1.8, cap_style=2))
pathU = unary_union(paths) if paths else Polygon()
pool = Polygon()
if not rest.is_empty:
    best = None
    for u in np.arange(-110, 111, 5):
        c = Point(u, (rest.bounds[1] + rest.bounds[3]) * 0.5); circ = c.buffer(9, 32)
        if rest.buffer(-4).contains(circ) and (best is None or abs(u) < abs(best[0])): best = (u, circ)
    if best: pool = best[1]
lawn = rest.difference(pathU).difference(pool.buffer(3))
polys += [(walk, PAVE), (alley, PAVE), (rest.intersection(pathU).difference(pool.buffer(3)), PAVE), (lawn, PLANT)]
if not pool.is_empty: polys += [(pool.buffer(3).difference(pool), PAVE), (pool, WATER)]
# trees: two rows along the boulevard, rows along the lawn path, the walk's edge row; all in line, evenly spaced
keep_off = pathU.buffer(1.5).union(pool.buffer(6))
def row(v, step, h, lo=-140, hi=140):
    for u in np.arange(lo, hi + 0.1, step):
        p = Point(u, v)
        if inner.buffer(-1).contains(p) and not keep_off.contains(p): new_trees.append((u, v, h))
row(104.5, 9.0, 11.0); row(113.5, 9.0, 11.0)
if not rest.is_empty:
    vm = (rest.bounds[1] + rest.bounds[3]) * 0.5
    row(vm - 5.5, 10.0, 9.5); row(vm + 5.5, 10.0, 9.5)

def tris_of(g, cell=36.0):
    out = []
    g = g.simplify(0.25)
    if g.is_empty: return out
    x0, z0, x1, z1 = g.bounds; pieces = []
    for x in np.arange(math.floor(x0 / cell) * cell, x1, cell):
        for z in np.arange(math.floor(z0 / cell) * cell, z1, cell):
            q = g.intersection(box(x, z, x + cell, z + cell))
            if not q.is_empty: pieces += list(q.geoms) if hasattr(q, 'geoms') else [q]
    for p in pieces:
        if p.geom_type != 'Polygon' or p.area < 0.5: continue
        for t in shapely.constrained_delaunay_triangles(p).geoms: out.append(np.array(t.exterior.coords)[:3])
    return out

out = [float(v) for i in keep for v in T[i]]
n_new = 0
for g, mat in polys:
    for t in tris_of(g):
        w = [to_world(u, v) for u, v in t]
        out += [round(c, 2) for p in w for c in p] + [mat, st]; n_new += 1
tr_out = [round(float(v), 2) for t in keep_trees for v in t]
for u, v, h in new_trees:
    x, z = to_world(u, v); tr_out += [round(x, 2), round(z, 2), h, st]
json.dump({'cx': CX, 'cz': CZ, 'tris': out, 'trees': tr_out}, open(OUT, 'w'), separators=(',', ':'))
print('triangles', len(T), '->', len(out) // 8, '(new', n_new, ') trees', len(trees), '->', len(tr_out) // 4)
