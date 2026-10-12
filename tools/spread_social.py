# Social infrastructure spread over the quarters (feedback 12.10.2026: "why so much in one place?"):
# the master plan's generator filled whole zones with identical rows of schools, clinics and offices (Golden's south-east:
# 300+ small education boxes and a hospital block of 15 identical buildings side by side). A city has a university campus
# and hospital campuses, but schools, kindergartens and clinics stand inside the residential quarters.
#  1. education clusters (>= 10 buildings within 120 m of each other) -> a university campus: the large buildings and the
#     core next to them stay (id tag "_campus_"); the rest become student housing (res_mid) and offices (business);
#  2. health clusters -> a hospital campus of up to 5 central buildings, the rest housing/offices;
#  3. public clusters (technoparks) -> at most 30 buildings stay a technopark (id tag "_tech_"), the rest offices (business);
#  4. schools and clinics in the quarters: residential buildings far from any school (> 650 m) / clinic (> 1400 m) become one
#     (mid-size housing blocks, spaced apart), so every quarter has its own.
# Geometry is unchanged (only kind/use/colour of the boxes), building ids stay contiguous; bounds and hide list untouched.
# In/out (in place): <UnityProject>/Assets/CityData/layer_buildings.bytes, buildings.csv
import sys, csv, struct, io, json
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix

ROOT = sys.argv[1]; CD = ROOT + '/Assets/CityData/'
COL = {'res_mid': 0, 'public': 3, 'education': 5, 'health': 6, 'business': 12}

def read_aql(path):
    f = open(path, 'rb').read(); assert f[:4] == b'AQL1'; n = struct.unpack_from('<i', f, 4)[0]; o = 8; out = []
    for _ in range(n):
        L = struct.unpack_from('<H', f, o)[0]; o += 2; name = f[o:o + L].decode(); o += L
        kind = f[o]; o += 1; nv, nt = struct.unpack_from('<ii', f, o); o += 8
        V = np.frombuffer(f, np.float32, nv * 3, o).reshape(-1, 3).copy(); o += nv * 12
        T = np.frombuffer(f, np.uint32, nt * 3, o).reshape(-1, 3).copy(); o += nt * 12
        col = np.frombuffer(f, np.uint8, nt, o).copy(); o += nt
        yr = np.frombuffer(f, np.uint16, nt, o).copy(); o += nt * 2
        bid = np.frombuffer(f, np.int32, nt, o).copy(); o += nt * 4
        out.append([name, kind, V, T, col, yr, bid])
    return out
def write_aql(path, objs):
    bb = io.BytesIO(); bb.write(b'AQL1'); bb.write(struct.pack('<i', len(objs)))
    for name, kind, V, T, col, yr, bid in objs:
        nb = name.encode(); bb.write(struct.pack('<H', len(nb))); bb.write(nb); bb.write(struct.pack('<B', kind))
        bb.write(struct.pack('<ii', len(V), len(T)))
        bb.write(np.asarray(V, np.float32).tobytes()); bb.write(np.asarray(T, np.uint32).tobytes())
        bb.write(np.asarray(col, np.uint8).tobytes()); bb.write(np.asarray(yr, np.uint16).tobytes()); bb.write(np.asarray(bid, np.int32).tobytes())
    open(path, 'wb').write(bb.getvalue())

rows = list(csv.DictReader(open(CD + 'buildings.csv', encoding='utf-8'))); cols = list(rows[0].keys())
assert all(int(r['bid']) == i for i, r in enumerate(rows))
hidden = set()
try:
    f = open(ROOT + '/Assets/Resources/Landmarks/hide_extra.bytes', 'rb').read(); n = struct.unpack_from('<i', f, 4)[0]
    for i in range(n):
        b, c = struct.unpack_from('<iI', f, 8 + 8 * i)
        if c <= 50: hidden.add(b)            # never shown, or gone by 2050 (code = year - 2000)
except FileNotFoundError: pass
XY = np.array([[float(r['x']), float(r['z'])] for r in rows])
K = np.array([r['kind'] for r in rows]); D = np.array([r['district'] for r in rows]); G = np.array([float(r['gfa_m2'] or 0) for r in rows])
SRC = np.array([r['source'] for r in rows])
live = np.array([i not in hidden for i in range(len(rows))])
rng = np.random.default_rng(21)
change = {}                                    # bid -> (kind, use, tag)

def clusters(idx, eps):
    if len(idx) == 0: return []
    t = cKDTree(XY[idx]); pr = t.query_pairs(eps, output_type='ndarray')
    m = coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(idx), len(idx)))
    n, lab = connected_components(m, directed=False)
    return [idx[lab == k] for k in range(n)]

def to_city(b):                               # a surplus box: student housing or offices
    change[b] = ('res_mid', 'housing', 'res_mid') if rng.random() < 0.55 else ('business', 'business', 'business')

stat = {}
for dist in ('Gate', 'Golden', 'Green', 'Growing'):
    sel = lambda k: np.where((K == k) & (D == dist) & live)[0]
    # 1. campuses
    for c in clusters(sel('education'), 220.0):
        if len(c) < 10: continue
        big = c[G[c] >= 12000]
        ctr = XY[big].mean(0) if len(big) else XY[c].mean(0)
        order = c[np.argsort(np.hypot(*(XY[c] - ctr).T))]
        keep = set(big.tolist()) | set(order[:max(8, int(len(c) * 0.25))].tolist())
        for b in c:
            if b in keep: change[b] = ('education', 'social', 'campus')
            else: to_city(b)
        stat.setdefault(dist, {}).setdefault('campus', []).append((len(c), len(keep)))
    # 2. hospital campuses
    for c in clusters(sel('health'), 220.0):
        if len(c) < 6: continue
        ctr = XY[c].mean(0); order = c[np.argsort(np.hypot(*(XY[c] - ctr).T))]
        for b in order[5:]: to_city(b)
        stat.setdefault(dist, {}).setdefault('hospital', []).append((len(c), 5))
    # 3. technoparks
    for c in clusters(sel('public'), 220.0):
        if len(c) < 10: continue
        ctr = XY[c].mean(0); order = c[np.argsort(np.hypot(*(XY[c] - ctr).T))]
        for b in order[:15]: change[b] = ('public', 'business', 'tech')
        for b in order[15:]: change[b] = ('business', 'business', 'business')
        stat.setdefault(dist, {}).setdefault('tech', []).append((len(c), min(15, len(c))))

    # 4. schools and clinics in the quarters (after the clusters: their surplus no longer counts)
    def now_kind(b): return change[b][0] if b in change else K[b]
    def now_tag(b): return change[b][2] if b in change else ''
    home = np.array([b for b in np.where((D == dist) & live)[0] if now_kind(b) in ('res_mid', 'res_high', 'residential') and SRC[b] != 'existing_osm' and b not in change])
    if len(home) == 0: continue
    for kind, gap, lo, hi in (('education', 650.0, 2500, 9000), ('health', 1400.0, 3000, 12000)):
        have = [b for b in np.where((D == dist) & live)[0] if now_kind(b) == kind and now_tag(b) != 'campus']
        P = [tuple(XY[b]) for b in have]; added = 0
        # densest housing first: a quarter with many homes and no school gets one in its middle
        th = cKDTree(XY[home]); dens = np.array([len(v) for v in th.query_ball_point(XY[home], 350.0)])
        for b in home[np.argsort(-dens)]:
            if b in change or not (lo <= G[b] <= hi) or K[b] != 'res_mid': continue
            if P and cKDTree(np.array(P)).query(XY[b])[0] < gap: continue
            if dens[np.where(home == b)[0][0]] < 12: break
            change[b] = (kind, 'social', kind); P.append(tuple(XY[b])); added += 1
        stat.setdefault(dist, {})['+' + kind] = added

# ------------------------------------------------------------------ write
for b, (kind, use, tag) in change.items():
    r = rows[b]; r['kind'] = kind; r['use'] = use
    r['id'] = '%s_%s_%s_b%d' % (r['district'].upper(), tag, r['year'], b)
ids = [rows[b]['id'] for b in change]; assert len(set(ids)) == len(ids)
newcol = np.full(len(rows), 255, np.int16)
for b, (kind, _, _) in change.items(): newcol[b] = COL[kind]
objs = read_aql(CD + 'layer_buildings.bytes')
for o in objs:
    nc = newcol[o[6]]; m = nc >= 0
    m &= nc != 255
    o[4][m] = nc[m].astype(np.uint8)
write_aql(CD + 'layer_buildings.bytes', objs)
with open(CD + 'buildings.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols, lineterminator='\n'); w.writeheader(); w.writerows(rows)
from collections import Counter
print(json.dumps(stat))
print('changed', len(change), Counter((K[b], v[2]) for b, v in change.items()).most_common())
