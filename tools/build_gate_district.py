"""Iconic Complex and the Gate District round it, taken from the QTwin page of the complex (QTwin_IconicComplex_AlatauCity.html):
its BIM model of the complex (5 buildings) and its 3 x 3 km model of the district by the master plan (blocks, towers, streets,
courtyards, the park, trees), of which only the round of the complex is kept: the oval square, the ring road and the first blocks
round it (the twin's own city goes on outside). Writes, in the local frame of the Iconic landmark of the twin (its yaw is the
bearing of the page's north + 180: x = -x_page, z = -z_page):
  Resources/Landmarks/iconic_bim.bytes      the complex (positions, normals, facade u, building, surface tag)
  Resources/Landmarks/gate_district.bytes   the district (gzip): mesh, trees, mask of the area it replaces
The ground of the district is cut into pieces of at most 32 m so it can be laid on the terrain; the blocks the LRT viaduct of the
twin would cut through are taken out and grassed (a green corridor under the line).
usage: python3 build_gate_district.py page.html lrt_routes.json out_dir [x z yaw keep_radius area_radius]
(x, z, yaw: LandmarkData's Iconic; defaults: the heart of Gate, next to its central roundabout, the square facing it)"""
import sys, re, gzip, base64, struct, json, math
import numpy as np

page, lrt_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
a = [float(v) for v in sys.argv[4:9]] + [None] * 5
X0, Z0 = a[0] or -3034.0, a[1] or -19059.0                   # the centre of the complex in the twin
GATE_YAW = (a[2] if a[2] is not None else 270.0) - 180.0     # the bearing of the page's north
R_KEEP, R_AREA = a[3] or 330.0, a[4] or 420.0                # blocks whose centre is nearer are kept; the area the district replaces

s = open(page, encoding='utf-8', errors='replace').read()
i = s.find('id="geo"'); j = s.find('>', i) + 1; k = s.find('<', j)
buf = gzip.decompress(base64.b64decode(s[j:k].strip()))
o = 0
def i32():
    global o; v = struct.unpack_from('<i', buf, o)[0]; o += 4; return v
def take(dt, n):
    global o; a = np.frombuffer(buf, dtype=dt, count=n, offset=o).copy(); o += n * np.dtype(dt).itemsize; return a
def mesh():
    n = i32(); ni = i32()
    pos = take('<f4', n * 3).reshape(-1, 3); nrm = take('i1', n * 3).reshape(-1, 3).astype(np.float32) / 127.0
    u = take('<f4', n); part = take('u1', n); tag = take('u1', n)
    nw = i32(); take('<f4', nw * 4); take('<u2', n); idx = take('<u4', ni).reshape(-1, 3)
    return dict(pos=pos, nrm=nrm, u=u, part=part, tag=tag, idx=idx)
ms = [mesh() for _ in range(4)]
ns = i32(); take('<f4', ns * 3)
assert buf[o:o + 4] == b'GATE'; o += 4
city = mesh(); nt = i32(); trees = take('<f4', nt * 5).reshape(-1, 5)
bim = ms[0]

def to_local(p):                     # page (raw, left-handed, +z north) -> landmark local (rotated half a turn)
    q = p.copy(); q[..., 0] *= -1; q[..., 2] *= -1; return q

# ---------------------------------------------------------------- triangles as flat lists (unshared), ground cut to 24 m
def flat(m):
    t = m['idx']
    return dict(p=m['pos'][t], n=m['nrm'][t], u=m['u'][t], part=m['part'][t[:, 0]], tag=m['tag'][t[:, 0]])
def subdivide(T, sel, maxe=32.0):
    keep = {k: v[~sel] for k, v in T.items()}
    P, N, U, PA, TG = [], [], [], [], []
    stack = [(T['p'][i], T['n'][i], T['u'][i], T['part'][i], T['tag'][i]) for i in np.nonzero(sel)[0]]
    while stack:
        p, n, u, pa, tg = stack.pop()
        e = [np.linalg.norm(p[(a + 1) % 3] - p[a]) for a in range(3)]
        a = int(np.argmax(e))
        if e[a] <= maxe: P.append(p); N.append(n); U.append(u); PA.append(pa); TG.append(tg); continue
        b, c = (a + 1) % 3, (a + 2) % 3
        mp = (p[a] + p[b]) * 0.5; mn = (n[a] + n[b]) * 0.5; mu = (u[a] + u[b]) * 0.5
        for (q0, q1, q2, v0, v1, v2, w0, w1, w2) in ((p[a], mp, p[c], n[a], mn, n[c], u[a], mu, u[c]), (mp, p[b], p[c], mn, n[b], n[c], mu, u[b], u[c])):
            stack.append((np.array([q0, q1, q2]), np.array([v0, v1, v2]), np.array([w0, w1, w2]), pa, tg))
    if P:
        keep['p'] = np.concatenate([keep['p'], np.array(P)]); keep['n'] = np.concatenate([keep['n'], np.array(N)])
        keep['u'] = np.concatenate([keep['u'], np.array(U)]); keep['part'] = np.concatenate([keep['part'], np.array(PA, np.uint8)])
        keep['tag'] = np.concatenate([keep['tag'], np.array(TG, np.uint8)])
    return keep

C = flat(city)
# ---------------------------------------------------------------- the LRT of the twin in the page's frame
th = math.radians(GATE_YAW); c, sn = math.cos(th), math.sin(th)
def raw(x, z):
    dx, dz = x - X0, z - Z0; return dx * c - dz * sn, dx * sn + dz * c
lrt = []
for r in json.load(open(lrt_path))['routes']:
    g = r['pts']; lrt.append(np.array([raw(g[i], g[i + 1]) for i in range(0, len(g), 2)]))
def dist_lrt(px, pz):
    best = np.full(px.shape, 1e9)
    for L in lrt:
        for a, b in zip(L[:-1], L[1:]):
            ab = b - a; l2 = max(ab @ ab, 1e-9)
            t = np.clip(((px - a[0]) * ab[0] + (pz - a[1]) * ab[1]) / l2, 0, 1)
            best = np.minimum(best, np.hypot(px - (a[0] + ab[0] * t), pz - (a[1] + ab[1] * t)))
    return best

# buildings (walls, roofs, copings, plant, courtyards) as connected pieces: a block the viaduct would cut is taken out
bt = np.isin(C['tag'], [20, 21, 22, 23, 24, 25, 26, 27, 32, 33]) & (C['p'][:, :, 1].max(1) > 0.8) | np.isin(C['tag'], [20, 21, 22, 23, 24])
ids = np.nonzero(bt)[0]
key = {}; parent = list(range(len(ids)))
def find(a):
    while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
    return a
for li, ti in enumerate(ids):
    for q in C['p'][ti]:
        kk = (round(q[0] * 5), round(q[2] * 5))
        if kk in key: ra, rb = find(li), find(key[kk]); parent[ra] = rb
        else: key[kk] = li
comp = np.array([find(a) for a in range(len(ids))])
cen = C['p'][ids].mean(1)
drop = np.zeros(len(C['tag']), bool); lawns = []
for cid in np.unique(comp):
    m = comp == cid; pts = C['p'][ids[m]].reshape(-1, 3)
    x0, x1, z0, z1 = pts[:, 0].min(), pts[:, 0].max(), pts[:, 2].min(), pts[:, 2].max()
    gx, gz = np.meshgrid(np.linspace(x0, x1, 8), np.linspace(z0, z1, 8))
    if dist_lrt(gx.ravel(), gz.ravel()).min() < 26.0:
        drop[ids[m]] = True; lawns.append((x0, z0, x1, z1))
# courtyard gardens on the ground of a dropped block go too
if lawns:
    cc = C['p'].mean(1)
    for (x0, z0, x1, z1) in lawns:
        inb = (cc[:, 0] > x0) & (cc[:, 0] < x1) & (cc[:, 2] > z0) & (cc[:, 2] < z1) & np.isin(C['tag'], [26, 27, 28, 32, 33])
        drop |= inb
print('blocks taken out under the LRT:', len(lawns), 'triangles', drop.sum())
C = {k: v[~drop] for k, v in C.items()}
if lawns:
    P = []; 
    for (x0, z0, x1, z1) in lawns:
        a, b, cq, d = [x0, 0.3, z0], [x1, 0.3, z0], [x1, 0.3, z1], [x0, 0.3, z1]
        P += [[a, cq, b], [a, d, cq]]
    P = np.array(P, np.float32); n = len(P)
    C = {'p': np.concatenate([C['p'], P]), 'n': np.concatenate([C['n'], np.tile([0, 1, 0], (n, 3, 1)).astype(np.float32)]),
         'u': np.concatenate([C['u'], np.zeros((n, 3), np.float32)]), 'part': np.concatenate([C['part'], np.zeros(n, np.uint8)]),
         'tag': np.concatenate([C['tag'], np.full(n, 29, np.uint8)])}

# ---------------------------------------------------------------- only the round of the complex: blocks far out go with their courtyards
bt = np.isin(C['tag'], [20, 21, 22, 23, 24, 25, 26, 27, 32, 33]) & (C['p'][:, :, 1].max(1) > 0.8) | np.isin(C['tag'], [20, 21, 22, 23, 24])
ids = np.nonzero(bt)[0]; key = {}; parent = list(range(len(ids)))
for li, ti in enumerate(ids):
    for q in C['p'][ti]:
        kk = (round(q[0] * 5), round(q[2] * 5))
        if kk in key: ra, rb = find(li), find(key[kk]); parent[ra] = rb
        else: key[kk] = li
comp = np.array([find(a) for a in range(len(ids))]); far = np.zeros(len(C['tag']), bool); kept = np.zeros(len(C['tag']), bool)
for cid in np.unique(comp):
    m = comp == cid; pts = C['p'][ids[m]].reshape(-1, 3)
    if np.hypot(pts[:, 0].mean(), pts[:, 2].mean()) > R_KEEP: far[ids[m]] = True
    else: kept[ids[m]] = True
print('blocks kept round the complex:', len(np.unique(comp[kept[ids]])), 'of', len(np.unique(comp)))
C = {k: v[~far] for k, v in C.items()}
# the area the district replaces: a round of R_AREA (the twin's roads, buildings and line layers give way inside it)
W = 512; HALF = R_AREA + 40.0; cell = 2 * HALF / W
gx, gz = np.meshgrid((np.arange(W) + 0.5) * cell - HALF, (np.arange(W) + 0.5) * cell - HALF)
mask = np.hypot(gx, gz) < R_AREA
# the ground (paving, streets, lawns, gardens) is cut to 32 m and kept only inside the round; the blocks kept stand whole
low = C['p'][:, :, 1].max(1) < 1.0
C = subdivide(C, low, 32.0)
cc = C['p'].mean(1); rr = np.hypot(cc[:, 0], cc[:, 2]); high = C['p'][:, :, 1].max(1) >= 1.0
C = {k: v[(rr < R_AREA) | high & (rr < R_KEEP + 120.0)] for k, v in C.items()}
trees_in = trees[mask[np.clip(((trees[:, 2] + HALF) / cell).astype(int), 0, W - 1), np.clip(((trees[:, 0] + HALF) / cell).astype(int), 0, W - 1)]]
trees_in = trees_in[dist_lrt(trees_in[:, 0], trees_in[:, 2]) > 8.0]
on_plot = (np.abs(trees_in[:, 0]) < 134) & (np.abs(trees_in[:, 2]) < 98)
print('district triangles', len(C['tag']), 'trees', len(trees_in), 'on the plot', on_plot.sum(), 'mask share %.2f' % mask.mean())

# ---------------------------------------------------------------- write
def pack_mesh(T, with_part):
    """Welded vertices (position, normal, facade u, tag, building) and an index list; positions in the local frame."""
    P3 = to_local(T['p']); N3 = to_local(T['n'])
    # Unity's front faces: cross(b - a, c - a) along the normal
    fl = np.einsum('ij,ij->i', np.cross(P3[:, 1] - P3[:, 0], P3[:, 2] - P3[:, 0]), N3.sum(1)) < 0
    T = dict(T); T['u'] = T['u'].copy()
    for A in (P3, N3, T['u']): A[fl, 1], A[fl, 2] = A[fl, 2].copy(), A[fl, 1].copy()
    print('  turned', fl.sum(), 'of', len(fl))
    p = P3.reshape(-1, 3).astype(np.float32); n = N3.reshape(-1, 3)
    n = np.clip(np.round(n * 127), -127, 127).astype(np.int8)
    u = T['u'].reshape(-1).astype(np.float32)
    tg = np.repeat(T['tag'], 3).astype(np.uint8); pa = np.repeat(T['part'], 3).astype(np.uint8)
    keyv = np.concatenate([np.round(p * 100).astype(np.int64), n.astype(np.int64), np.round(u * 100).astype(np.int64)[:, None],
                           tg.astype(np.int64)[:, None], pa.astype(np.int64)[:, None]], 1)
    _, first, inv = np.unique(keyv, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1).astype(np.uint32); nv = len(first)
    b = struct.pack('<ii', nv, len(inv)) + p[first].tobytes() + n[first].tobytes() + u[first].tobytes() + tg[first].tobytes()
    if with_part: b += pa[first].tobytes()
    return b + inv.tobytes()
B = flat(bim)
open(out + '/iconic_bim.bytes', 'wb').write(b'QTB1' + pack_mesh(B, True))
tl = trees_in.copy(); tl[:, 0] *= -1; tl[:, 2] *= -1               # x, y, z, size, kind in the local frame
ml = mask[::-1, ::-1]                                                # the mask in the local frame (both axes reversed)
body = b'QGD1' + pack_mesh(C, False) + struct.pack('<i', len(tl)) + tl.astype(np.float32).tobytes() + struct.pack('<if', W, HALF) + (ml.astype(np.uint8) * 255).tobytes()
open(out + '/gate_district.bytes', 'wb').write(gzip.compress(body, 9))
np.save(out + '/mask.npy', mask)
print('bim triangles', len(B['tag']), 'sizes', len(open(out + '/iconic_bim.bytes', 'rb').read()), len(open(out + '/gate_district.bytes', 'rb').read()))
