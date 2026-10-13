# Clean road geometry for the film look (FilmRoads). The plan's graph draws motorways as broken, doubled, offset pieces and
# interchanges as scribbles (ramps of every class drawn on top of each other). Here:
#   1. motorways are rebuilt as one smooth centreline per corridor (raster + skeleton of the straight carriageway pieces) and drawn
#      as a dual carriageway with a constant median;
#   2. every interchange is cleared (all roads inside its disk) and rebuilt as a standard cloverleaf / trumpet tangent to the
#      carriageways; the crossing road passes straight through;
#   3. plan lines that duplicate a motorway (service ramps drawn along it) and tiny orphan pieces are dropped.
# Run: python Tools/film_roads/build_film_roads.py Assets/StreamingAssets/twin/roads.json Assets/Resources/Landmarks/film_roads.json
# (numpy, scipy, scikit-image, networkx, shapely). FilmRoads.cs uses the file instead of the plan graph when it exists.
# Output Resources/Landmarks/film_roads.json: {"s": [{"c": class, "k": 0 two-way | 1 one carriageway | 2 ramp, "a","b": node ids
#   (-1 = no junction patch), "y": [4 years], "g": [x, z, ...]}], "zones": [[x, z, r, year]], "drop": [graph edges not drawn]}
import json, math, sys, numpy as np
from collections import defaultdict
from scipy.spatial import cKDTree
from scipy import ndimage
from skimage.morphology import skeletonize
import networkx as nx
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strokes as SP, zones as ZN

ROADS = sys.argv[1]; OUT = sys.argv[2]
E = json.load(open(ROADS))['edges']
G = [np.array(e['g'], float).reshape(-1, 2) for e in E]
FAST = ('highway', 'ring')
def Yv(e): return [SP.Y(e, s) for s in range(4)]

MED = 11.0          # axis -> centre of a motorway carriageway
CW_HALF = 6.0       # half width of one motorway carriageway (FilmRoads one-way highway)
RAMP_HALF = 4.0
RL = 55.0           # loop radius

def resample(P, step=8.0): return np.array(SP.resample([np.array(p) for p in P], step))
def smooth(P, n): return SP.smooth(P, n)
def offset(P, d):
    t = np.gradient(P, axis=0); l = np.hypot(*t.T); l[l < 1e-6] = 1; t = (t.T / l).T
    return P + np.c_[-t[:, 1], t[:, 0]] * d
def plen(P): return float(np.hypot(*np.diff(P, axis=0).T).sum()) if len(P) > 1 else 0.0

# ------------------------------------------------------------------ interchanges (picked by hand from the plan: real cloverleafs)
# centre, radius, motorway direction (deg), crossing road direction (deg), crossing class
SPEC = [((130, 3960), 260, 78, -18, 'main'), ((-11140, -20500), 360, 34, -31, 'main'), ((-1800, -12140), 300, 80, -10, 'main'),
        ((-2290, -20310), 420, 80, -20, 'highway'), ((410, 19010), 260, 80, -3, 'main'), ((1430, -15130), 300, 40, -78, 'main'),
        ((7240, -25390), 320, -55, 45, 'main'), ((-860, -3290), 330, 88, -23, 'main'), ((1000, 26490), 300, 85, -3, 'main')]
IC = [dict(C=np.array(c, float), R=float(r), tm=tm, tc=tc, cc=cc) for c, r, tm, tc, cc in SPEC]
_mids = np.array([g.mean(0) for g in G])
for z in IC:
    near = np.nonzero(np.hypot(*(_mids - z['C']).T) < z['R'])[0]
    z['y'] = [int(min([SP.Y(E[k], i) for k in near] or [2025])) for i in range(4)]
ICtr = cKDTree(np.array([z['C'] for z in IC]))
def in_disk(p, pad=0.0):
    d, i = ICtr.query(p)
    return int(i) if d < IC[i]['R'] + pad else -1
# scribble clusters of the plan (ramps drawn as pieces): short plan pieces inside them are dropped
SCR = [(z['cen'], float(np.clip(np.percentile(np.hypot(*(z['pts'] - z['cen']).T), 90) + 30, 120, 400))) for z in ZN.zones(E) if len(z['members']) >= 6]
SCRtr = cKDTree(np.array([c for c, _ in SCR]))
def in_scr(p):
    d, i = SCRtr.query(p); return d < SCR[i][1]

# ------------------------------------------------------------------ motorway centrelines
def turn(g):
    if len(g) < 3: return 0.0
    d = np.diff(g, axis=0); a = np.arctan2(d[:, 1], d[:, 0]); return float(np.degrees(np.abs(np.angle(np.exp(1j * np.diff(a))))).sum())
fastk = [k for k, e in enumerate(E) if e['c'] in FAST and len(G[k]) >= 2]
carr = [k for k in fastk if turn(G[k]) / max(plen(G[k]), 1) < 0.06 and plen(G[k]) >= 25]    # straight carriageway pieces
CELL = 5.0
carr_set = set(carr)
allp = np.concatenate([G[k] for k in fastk]); lo = allp.min(0) - 300; hi = allp.max(0) + 300
W_, H_ = int((hi[0] - lo[0]) / CELL) + 1, int((hi[1] - lo[1]) / CELL) + 1
img = np.zeros((H_, W_), bool)
def px(p): return ((p[:, 1] - lo[1]) / CELL).astype(int), ((p[:, 0] - lo[0]) / CELL).astype(int)
for k in carr:
    P = resample(G[k], 2.0); r, c = px(P); img[r, c] = True
for k in fastk:                                   # long straight segments of curvy / scribbled edges are carriageway too
    if k in carr_set: continue
    g = G[k]
    for a_, b_ in zip(g[:-1], g[1:]):
        if np.hypot(*(b_ - a_)) >= 40 and not in_scr((a_ + b_) / 2): P = resample(np.array([a_, b_]), 2.0); r, c = px(P); img[r, c] = True
img = ndimage.binary_dilation(img, structure=np.ones((3, 3)), iterations=4)        # ~20 m: the two carriageways merge
img = ndimage.binary_closing(img, structure=np.ones((3, 3)), iterations=6)         # bridge small gaps
for z in IC:                                                                      # interchanges are drawn separately
    r0, c0 = int((z['C'][1] - lo[1]) / CELL), int((z['C'][0] - lo[0]) / CELL); rr = int(z['R'] / CELL)
    yy, xx = np.ogrid[-rr:rr + 1, -rr:rr + 1]; m = yy * yy + xx * xx <= rr * rr
    ys, xs = slice(max(r0 - rr, 0), r0 + rr + 1), slice(max(c0 - rr, 0), c0 + rr + 1)
    sub = img[ys, xs]; mm = m[(ys.start - (r0 - rr)):(ys.start - (r0 - rr)) + sub.shape[0], (xs.start - (c0 - rr)):(xs.start - (c0 - rr)) + sub.shape[1]]
    sub[mm] = False
sk = skeletonize(img)
print('skeleton px', int(sk.sum()))
# skeleton -> graph
rs, cs = np.nonzero(sk); idx = {(r, c): i for i, (r, c) in enumerate(zip(rs, cs))}
SG = nx.Graph()
for i, (r, c) in enumerate(zip(rs, cs)):
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if (dr or dc) and (r + dr, c + dc) in idx: SG.add_edge(i, idx[(r + dr, c + dc)], w=math.hypot(dr, dc) * CELL)
def world(i): return np.array([lo[0] + (cs[i] + 0.5) * CELL, lo[1] + (rs[i] + 0.5) * CELL])
# prune spurs (ramps that dead-end) repeatedly
for _ in range(6):
    ends = [n for n in SG.nodes if SG.degree(n) == 1]; removed = 0
    for e0 in ends:
        if e0 not in SG: continue
        path = [e0]; cur = e0; prev = None; L = 0
        while True:
            nb = [n for n in SG.neighbors(cur) if n != prev]
            if SG.degree(cur) > 2 or not nb or L > 500: break
            prev, cur = cur, nb[0]; L += SG[prev][cur]['w']; path.append(cur)
        if SG.degree(cur) > 2 and L < 500:
            SG.remove_nodes_from(path[:-1]); removed += 1
    if not removed: break
# cycles (ramp loops beside the carriageway): keep the straightest — MST by length drops the long way round
SG = nx.minimum_spanning_tree(SG, weight='w')
for _ in range(6):
    ends = [n for n in SG.nodes if SG.degree(n) == 1]; removed = 0
    for e0 in ends:
        if e0 not in SG: continue
        path = [e0]; cur = e0; prev = None; L = 0
        while True:
            nb = [n for n in SG.neighbors(cur) if n != prev]
            if SG.degree(cur) > 2 or not nb or L > 500: break
            prev, cur = cur, nb[0]; L += SG[prev][cur]['w']; path.append(cur)
        if SG.degree(cur) > 2 and L < 500:
            SG.remove_nodes_from(path[:-1]); removed += 1
    if not removed: break
# trace paths between junction / end pixels
paths = []; seen = set()
key = lambda a, b: (a, b) if a < b else (b, a)
for n in SG.nodes:
    if SG.degree(n) == 2: continue
    for nb in SG.neighbors(n):
        if key(n, nb) in seen: continue
        p = [n, nb]; seen.add(key(n, nb)); prev, cur = n, nb
        while SG.degree(cur) == 2:
            nx_ = [m for m in SG.neighbors(cur) if m != prev][0]; seen.add(key(cur, nx_)); prev, cur = cur, nx_; p.append(cur)
        paths.append(np.array([world(i) for i in p]))
# drop short pieces that touch nothing (bits of a crossing road the plan drew as motorway)
endcnt = defaultdict(int)
for p in paths:
    for q in (p[0], p[-1]): endcnt[(int(q[0] // 15), int(q[1] // 15))] += 1
def touches(q):
    kx, kz = int(q[0] // 15), int(q[1] // 15)
    return sum(endcnt.get((kx + i, kz + j), 0) for i in (-1, 0, 1) for j in (-1, 0, 1)) > 1
paths = [p for p in paths if plen(p) > 25 and (plen(p) > 400 or touches(p[0]) or touches(p[-1]))]
print('motorway paths', len(paths), int(sum(plen(p) for p in paths) / 1000), 'km')

# ------------------------------------------------------------------ helpers: class / years of the plan near a point
mid_k = [k for k in fastk]; mtr = cKDTree(np.array([G[k].mean(0) for k in mid_k]))
seg_p = []; seg_k = []
for k, e in enumerate(E):
    g = G[k]
    for a, b in zip(g[:-1], g[1:]):
        n_ = max(1, int(np.hypot(*(b - a)) / 10))
        for t in np.linspace(0, 1, n_ + 1)[:-1] + 0.5 / n_: seg_p.append(a + (b - a) * t); seg_k.append(k)
seg_p = np.array(seg_p); seg_k = np.array(seg_k); segtr = cKDTree(seg_p)
fast_mask = np.array([E[k]['c'] in FAST for k in seg_k])
ftr = cKDTree(seg_p[fast_mask]); fk = seg_k[fast_mask]
def near_fast(p):
    d, i = ftr.query(p); return fk[i], d
def ytuple(k): return tuple(Yv(E[k]))

OUTS = []          # (cls, kind, a, b, years, P)
def add(cls, kind, P, years, a=-1, b=-1):
    if len(P) >= 2 and plen(P) > 1: OUTS.append(dict(c=cls, k=kind, a=a, b=b, y=[int(v) for v in years], P=np.asarray(P)))

def clip_disk(P):
    keep = np.array([in_disk(q, 110) < 0 for q in P])
    if keep.all(): return P
    best = (0, 0); s_ = None
    for i, k in enumerate(list(keep) + [False]):
        if k and s_ is None: s_ = i
        if not k and s_ is not None:
            if i - s_ > best[1] - best[0]: best = (s_, i)
            s_ = None
    return P[best[0]:best[1]]
# snap motorway path ends to the interchange axis they enter
def snap_end(P, at_end):
    q = P[-1] if at_end else P[0]
    i = in_disk(q, 60)
    if i < 0: return P
    z = IC[i]; C = z['C']; v = q - C
    best = max(z['arms'], key=lambda a: v @ a['d'] / max(np.hypot(*v), 1))
    if best['cls'] not in FAST: return P
    tgt = C + best['d'] * z['R']
    # replace the part closer than R+40 by a straight run to the target, blending over 80 m
    dist = np.hypot(*(P - C).T); keep = dist > z['R'] + 30
    P2 = P[keep] if at_end else P[keep]
    if len(P2) < 2: return P
    if at_end: P2 = np.r_[P2, [tgt]]
    else: P2 = np.r_[[tgt], P2]
    return P2

mot_center = []
for p in paths:
    from shapely.geometry import LineString
    p = np.array(LineString(p).simplify(30.0).coords)
    p = resample(p, 8.0); p = smooth(p, 24)
    p = clip_disk(p)
    if len(p) < 3: continue
    p = smooth(resample(p, 8.0), 4)
    if len(p) < 3: continue
    # split where the plan's years change (district by district)
    ks = [near_fast(q)[0] for q in p]; yt = [ytuple(k) for k in ks]; cl = [E[k]['c'] for k in ks]
    # majority filter over 15 samples
    def maj(arr, i):
        w = arr[max(0, i - 7):i + 8]; return max(set(w), key=w.count)
    yt = [maj(yt, i) for i in range(len(yt))]; cl = [maj(cl, i) for i in range(len(cl))]
    s = 0
    for i in range(1, len(p) + 1):
        if i == len(p) or yt[i] != yt[s] or cl[i] != cl[s]:
            seg = p[max(s - 1, 0):i + 1] if i < len(p) else p[max(s - 1, 0):]
            if len(seg) >= 2:
                mot_center.append((cl[s], yt[s], seg))
            s = i
mot_center = [[c, y, P] for c, y, P in mot_center]

# ------------------------------------------------------------------ the rest of the plan
R0 = SP.strokes(E, None)

mot_pts = np.concatenate([P for _, _, P in mot_center]) if mot_center else np.zeros((1, 2))
mtr2 = cKDTree(resample(mot_pts, 6.0) if len(mot_pts) > 1 else mot_pts)
kept = 0; dropped_strokes = 0
for st in R0:
    if st['cls'] in FAST: continue                                   # motorways are rebuilt
    P = st['P']
    # clip by interchange disks
    inside = np.array([in_disk(q) >= 0 for q in P])
    # the plan's ramps drawn as short street / main pieces around a motorway
    if st['L'] < 350 and np.mean([in_scr(q) for q in P]) > 0.5: dropped_strokes += 1; continue
    pieces = []; cur = []
    for q, ins in zip(P, inside):
        if ins:
            if len(cur) >= 2: pieces.append(np.array(cur))
            cur = []
        else: cur.append(q)
    if len(cur) >= 2: pieces.append(np.array(cur))
    for pc in pieces:
        whole = len(pc) == len(P)
        # a plan line that runs along the motorway (service ramp, doubled carriageway)
        d, _ = mtr2.query(pc)
        if (d < MED + CW_HALF + 14).mean() > 0.5: dropped_strokes += 1; continue
        L = plen(pc)
        if not whole and L < 160: dropped_strokes += 1; continue
        kind = 2 if False else (1 if st['oneway'] else 0)
        a = st['A'] if whole or np.allclose(pc[0], P[0]) else -1
        b = st['B'] if whole or np.allclose(pc[-1], P[-1]) else -1
        # a street cut by an interchange: run it to the crossing road if that is close
        add(st['cls'], kind, pc, st['y'], a, b); kept += 1
print('plan strokes kept', kept, 'dropped', dropped_strokes)
# ------------------------------------------------------------------ interchanges: through roads + cloverleaf ramps
def bez(p0, p1, p2, n=60):
    t = np.linspace(0, 1, n)[:, None]; return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2
def cross_pt(p, d, q, e):
    A = np.array([[d[0], -e[0]], [d[1], -e[1]]])
    if abs(np.linalg.det(A)) < 1e-6: return None
    t, _ = np.linalg.solve(A, q - p); return p + d * t
def unit(v): return v / max(np.hypot(*v), 1e-9)
def snap_path(mi, end, X):
    P = mot_center[mi][2].copy()
    if end == -1: P = P[::-1].copy()
    dv = X - P[0]; n = min(len(P), 16)
    for k in range(n): P[k] = P[k] + dv * (0.5 + 0.5 * math.cos(math.pi * k / n))
    mot_center[mi][2] = P if end == 0 else P[::-1]
zone_out = []
EXT = []
def edge_off(cls): return MED + CW_HALF if cls in FAST else (11.0 if cls == 'main' else 6.5)
for zi, z in enumerate(IC):
    C = z['C']; R = z['R']; y = z['y']
    axes = []
    for ang, cls in ((z['tm'], 'highway'), (z['tc'], z['cc'])):
        u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))]); side = {}
        if cls in FAST:
            for mi, (c2, yy, P) in enumerate(mot_center):
                for end in (0, -1):
                    X = P[end]
                    if in_disk(X, 260) != zi: continue
                    v = unit(X - C); sg = 1 if v @ u > 0 else -1
                    if abs(v @ u) < math.cos(math.radians(30)): continue
                    if sg not in side or abs(v @ u) > side[sg][1]: side[sg] = (X.copy(), abs(v @ u), [(mi, end)], c2)
        else:
            for i, o in enumerate(OUTS):
                if o['c'] in FAST or o['k'] == 2: continue
                for end, nid in ((0, o['a']), (-1, o['b'])):
                    X = o['P'][end]
                    if nid >= 0 or abs(np.hypot(*(X - C)) - R) > 30: continue
                    v = unit(X - C); sg = 1 if v @ u > 0 else -1
                    if abs(v @ u) < math.cos(math.radians(30)): continue
                    if sg in side and np.hypot(*(side[sg][0] - X)) < 60: side[sg][2].append((i, end)); continue
                    if sg not in side or abs(v @ u) > side[sg][1]: side[sg] = (X.copy(), abs(v @ u), [(i, end)], o['c'])
        for sg in (1, -1):
            if sg in side: continue
            X0 = C + u * sg * R; best = None
            if cls not in FAST:
                # the plan road resumes further out: run the crossing road on to its nearest end along the axis
                for i, o in enumerate(OUTS):
                    if o['c'] in FAST or o['k'] == 2: continue
                    for end in (0, -1):
                        X = o['P'][end]; v = X - C; dd = v @ (u * sg)
                        if dd < R - 40 or dd > R + 360: continue
                        off_ = abs(v @ np.array([-u[1], u[0]]))
                        if off_ > 30 + 0.3 * (dd - R): continue
                        Pq = o['P']; tv = unit(Pq[min(4, len(Pq) - 1)] - Pq[0]) if end == 0 else unit(Pq[-1] - Pq[max(-5, -len(Pq))])
                        if abs(tv @ u) < 0.8: continue
                        sc = dd + 3 * off_
                        if best is None or sc < best[0]: best = (sc, i, end, X.copy())
            if best is not None:
                X = best[3]; Xa = C + u * sg * float((X - C) @ (u * sg))
                side[sg] = (X0, 1.0, [], cls); EXT.append((cls, X0, Xa, X, best[1], best[2]))
            else: side[sg] = (X0, 1.0, [], cls)
        if cls in FAST: cls = side[1][3] if side[1][2] else side[-1][3]
        axes.append(dict(u=u, cls=cls, Xp=side[1][0], Xm=side[-1][0], refp=side[1][2], refm=side[-1][2]))
    m, c = axes
    Cc = cross_pt(m['Xm'], unit(m['Xp'] - m['Xm']), c['Xm'], unit(c['Xp'] - c['Xm']))
    if Cc is None or np.hypot(*(Cc - C)) > R * 0.5: Cc = C
    for ax in axes:
        line = resample(np.array([ax['Xm'], ax['Xp']]), 8.0)
        if ax['cls'] in FAST: add(ax['cls'], 1, offset(line, MED), y); add(ax['cls'], 1, offset(line, -MED)[::-1], y)
        else: add(ax['cls'], 0, line, y)
        for X, refs in ((ax['Xp'], ax['refp']), (ax['Xm'], ax['refm'])):
            for j, e in refs:
                if ax['cls'] in FAST: snap_path(j, e, X)
                else: OUTS[j]['P'][e] = X
    zone_out.append([round(float(Cc[0]), 1), round(float(Cc[1]), 1), round(R * 0.9, 1), int(y[0])])
    rays = []
    for ax in axes:
        for X in (ax['Xp'], ax['Xm']): rays.append(dict(d=unit(X - Cc), len=float(np.hypot(*(X - Cc))), cls=ax['cls']))
    order = sorted(rays, key=lambda a: math.atan2(a['d'][1], a['d'][0]))
    for i in range(4):
        a = order[i]; b = order[(i + 1) % 4]
        phi = (math.atan2(b['d'][1], b['d'][0]) - math.atan2(a['d'][1], a['d'][0])) % (2 * math.pi)
        bis = unit(a['d'] + b['d'])
        ea, eb = edge_off(a['cls']), edge_off(b['cls']); e = max(ea, eb) + RAMP_HALF + 3
        na = np.array([-a['d'][1], a['d'][0]]); na *= np.sign(na @ bis); nb = np.array([-b['d'][1], b['d'][0]]); nb *= np.sign(nb @ bis)
        rl = RL if math.radians(70) < phi < math.radians(110) else RL * 0.85
        dc = (rl + e) / math.sin(phi / 2); tang = dc * math.cos(phi / 2)
        Lc = Cc + bis * dc
        ta = Cc + a['d'] * tang + na * e; tb = Cc + b['d'] * tang + nb * e
        sa = math.atan2(*(ta - Lc)[::-1]); sb = math.atan2(*(tb - Lc)[::-1]); dd = (sb - sa) % (2 * math.pi)
        if dd < math.pi: dd -= 2 * math.pi
        th = sa + np.linspace(0, dd, 120); loop = Lc + rl * np.c_[np.cos(th), np.sin(th)]
        run = min(110.0, min(a['len'], b['len']) - tang - 20)
        if run > 30:
            ma = Cc + a['d'] * (tang + run) + na * (ea - 2); mb = Cc + b['d'] * (tang + run) + nb * (eb - 2)
            ra = Cc + a['d'] * (tang + run * 0.45) + na * e; rb = Cc + b['d'] * (tang + run * 0.45) + nb * e
            P = np.r_[np.linspace(ma, ra, 10)[:-1], np.linspace(ra, ta, 8)[:-1], loop, np.linspace(tb, rb, 8)[1:], np.linspace(rb, mb, 10)[1:]]
            add('highway', 2, smooth(resample(P, 6.0), 3), y)
        # outer connector: outside the loop, from arm a to arm b
        r_o = min(min(a['len'], b['len']) - 35, tang + max(run, 0) + 70)
        if r_o < tang + run + 30: continue
        pa = Cc + a['d'] * r_o + na * e; pb = Cc + b['d'] * r_o + nb * e
        far = dc + rl + 22
        proj = 0.5 * ((pa - Cc) @ bis + (pb - Cc) @ bis); ctrl = Cc + bis * max(2 * far - proj, proj + 30)
        curve = bez(pa, ctrl, pb, 80)
        ma = Cc + a['d'] * (r_o + 30) + na * (ea - 2); mb = Cc + b['d'] * (r_o + 30) + nb * (eb - 2)
        P = np.r_[[ma], curve, [mb]]
        add('highway', 2, smooth(resample(P, 6.0), 4), y)
for cls, X0, Xa, X, j, end in EXT:                      # extensions of crossing roads to where the plan road resumes
    P = resample(np.array([X0, X]), 8.0)
    if len(P) >= 2: add(cls, 0, smooth(P, 3), OUTS[j]['y'])
for cls, y, P in mot_center:
    add(cls, 1, offset(P, MED), y); add(cls, 1, offset(P, -MED)[::-1], y)
# duplicates: a plan line drawn twice (or in overlapping pieces). Longer / wider strokes win; the covered stretches of the
# others are cut away, short uncovered rests dropped. U-turn hairpins (short, end directions opposite) are dropped too.
RANK = {'highway': 3, 'ring': 2, 'main': 1, 'street': 0}
def hairpin(P):
    L = plen(P)
    if L > 1200 or len(P) < 4: return False
    ch = np.hypot(*(P[-1] - P[0]))
    if ch < 20:                                                   # a thin closed loop (a U-turn drawn as a ring)
        x, z = P[:, 0], P[:, 1]; area = 0.5 * abs(np.dot(x, np.roll(z, 1)) - np.dot(z, np.roll(x, 1)))
        return area / (L * L) < 0.03 and L < 1200
    d0 = unit(P[min(3, len(P) - 1)] - P[0]); d1 = unit(P[-1] - P[max(-4, -len(P))])
    return d0 @ d1 < -0.6 and ch < max(45.0, 0.2 * L) and L < 500
order = sorted(range(len(OUTS)), key=lambda i: (OUTS[i]['k'] == 2, -RANK.get(OUTS[i]['c'], 0), -plen(OUTS[i]['P'])))
def hw(o): return {'main': 7.5, 'street': 4.0}.get(o['c'], 9.0) if o['k'] == 0 else {'main': 3.8, 'street': 3.2}.get(o['c'], 6.0)
acc_p = []; acc_d = []; acc_w = []; acc_tree = None; acc_n = 0; NEW = []; cut = 0
def rebuild():
    global acc_tree, acc_n
    acc_tree = cKDTree(np.array(acc_p)) if acc_p else None; acc_n = len(acc_p)
pend_p = []; pend_d = []; pend_w = []
for cnt, i in enumerate(order):
    o = OUTS[i]; P = o['P']
    if o['k'] != 2 and o['c'] not in FAST and hairpin(P):
        cut += 1
        if np.hypot(*(P[-1] - P[0])) >= 20 or plen(P) < 160: continue
        # a road drawn out and back as one thin loop: keep one leg, as a two-way road
        fi = int(np.argmax(np.hypot(*(P - P[0]).T))); P = P[:fi + 1] if fi >= len(P) - fi else P[fi:]
        o = dict(o); o['P'] = P; o['k'] = 0; o['a'] = -1; o['b'] = -1
    if cnt % 200 == 0 and pend_p: acc_p.extend(pend_p); acc_d.extend(pend_d); acc_w.extend(pend_w); pend_p = []; pend_d = []; pend_w = []; rebuild()
    if o['k'] == 2 or o['c'] in FAST or (acc_tree is None and not pend_p):
        keep_runs = [P]
    else:
        T = np.gradient(P, axis=0); T = (T.T / np.maximum(np.hypot(*T.T), 1e-6)).T
        cov = np.zeros(len(P), bool)
        cand = [(acc_tree, acc_d, acc_w, acc_p)] if acc_tree is not None else []
        if pend_p: cand.append((cKDTree(np.array(pend_p)), pend_d, pend_w, pend_p))
        w0 = hw(o)
        for tr_, dd_, ww_, pp_ in cand:
            res = tr_.query_ball_point(P, 10.0)
            for j, lst in enumerate(res):
                for q in lst:
                    if abs(T[j] @ dd_[q]) > 0.9 and np.hypot(*(pp_[q] - P[j])) <= max(4.5, 0.6 * (w0 + ww_[q])): cov[j] = True; break
        # short covered stretches are crossings or touching ends, not duplicates; keep a little overlap at the cut ends
        j = 0
        while j < len(P):
            if cov[j]:
                k2 = j
                while k2 < len(P) and cov[k2]: k2 += 1
                if plen(P[j:k2 + 1]) < 30: cov[j:k2] = False
                else: cov[j:min(j + 2, k2)] = False; cov[max(k2 - 2, j):k2] = False
                j = k2
            else: j += 1
        if not cov.any(): keep_runs = [P]
        else:
            keep_runs = []; s_ = None
            for j, c_ in enumerate(list(cov) + [True]):
                if not c_ and s_ is None: s_ = j
                if c_ and s_ is not None:
                    seg = P[max(s_ - 1, 0):j + 1]
                    if plen(seg) > 40: keep_runs.append(seg)
                    s_ = None
            cut += 1
    for k_, R_ in enumerate(keep_runs):
        whole = len(R_) == len(P)
        o2 = dict(o); o2['P'] = R_
        if not whole:
            o2['a'] = o['a'] if np.allclose(R_[0], P[0]) else -1; o2['b'] = o['b'] if np.allclose(R_[-1], P[-1]) else -1
        NEW.append(o2)
        if o['k'] != 2:
            T = np.gradient(R_, axis=0); T = (T.T / np.maximum(np.hypot(*T.T), 1e-6)).T
            pend_p.extend(R_); pend_d.extend(T); pend_w.extend([hw(o)] * len(R_))
print('duplicates / hairpins cut', cut, 'strokes', len(OUTS), '->', len(NEW))
OUTS = NEW
# orphans: connected pieces with little total length
endtr = defaultdict(list)
def ek(p): return (int(p[0] // 6), int(p[1] // 6))
for i, o in enumerate(OUTS):
    for p in (o['P'][0], o['P'][-1]): endtr[ek(p)].append(i)
for i, o in enumerate(OUTS):
    if o['a'] >= 0: endtr[('n', o['a'])].append(i)
    if o['b'] >= 0: endtr[('n', o['b'])].append(i)
UG = nx.Graph(); UG.add_nodes_from(range(len(OUTS)))
for l in endtr.values():
    for i in l[1:]: UG.add_edge(l[0], i)
# an end that lies on another road (a T-junction, or a piece cut from a duplicate that goes on along it) is connected too
_ap = np.concatenate([o['P'] for o in OUTS]); _ao = np.concatenate([[i] * len(o['P']) for i, o in enumerate(OUTS)]); _at = cKDTree(_ap)
for i, o in enumerate(OUTS):
    for p in (o['P'][0], o['P'][-1]):
        for q in _at.query_ball_point(p, 12.0):
            if _ao[q] != i: UG.add_edge(i, int(_ao[q]))
drop = set()
for comp in nx.connected_components(UG):
    if sum(plen(OUTS[i]['P']) for i in comp) < 250 and all(OUTS[i]['c'] not in FAST for i in comp): drop |= comp
OUTS = [o for i, o in enumerate(OUTS) if i not in drop]
print('orphans dropped', len(drop), 'strokes out', len(OUTS))
# plan edges no longer drawn (for trees along roads)
dropE = []
for k, e in enumerate(E):
    m = G[k].mean(0)
    if e['c'] in FAST or in_disk(m) >= 0: dropE.append(k)
json.dump({'s': [dict(c=o['c'], k=o['k'], a=int(o['a']), b=int(o['b']), y=o['y'], g=[round(float(v), 1) for v in o['P'].reshape(-1)]) for o in OUTS],
           'zones': zone_out, 'drop': dropE}, open(OUT, 'w'), separators=(',', ':'))
if os.environ.get('FILM_ROADS_DEBUG'): import pickle; pickle.dump(dict(OUTS=OUTS, IC=IC, MC=mot_center, PATHS=paths), open(os.environ['FILM_ROADS_DEBUG'], 'wb'))
