# Factories out of the city fabric (feedback 12.10.2026):
#  1. industrial estates enclosed by the city (Growing core, Gate, Golden core, Green) become city buildings in place:
#     the factory box is replaced by one or two mid-rise blocks (kind "public": offices, services, technoparks) on its plot;
#  2. the same factories are rebuilt in two industrial belts on the sides of the city (east, along the railway; west, by the
#     airport and the BAKAD ring road), next to the estates that already stand there — new building ids appended at the end;
#  3. the real plants (PepsiCo, Mars Petcare, Sunny Paper, DanaFlex, G-Trans, Griffin Logopark, the Doosan power plant) get plots
#     in those belts (printed for LandmarkData.cs; the belts keep clear of them);
#  4. hide list: the master plan's old airport terminal (superseded by the airport landmark) and, of every two buildings whose
#     footprints overlap, the smaller one;
#  5. bid_bounds is rebuilt from the new geometry.
# In:  CityData/layer_buildings.bytes, buildings.csv, terrain_heights.bytes; Resources/Map/map_city.png, map_nature.png;
#      StreamingAssets/twin/roads.json; CityData/layer_infrastructure.bytes (railways, rivers).
# Out: CityData/layer_buildings.bytes, buildings.csv; Resources/Landmarks/bid_bounds.bytes, hide_extra.bytes; landmark plots (stdout, json).
import sys, struct, json, math, csv, io
import numpy as np
from shapely.geometry import MultiPoint, Polygon, LineString, box, Point
from shapely import STRtree
from shapely.ops import unary_union
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

SRC = sys.argv[1]          # source project root (UnityProject) with the original CityData
OUT = sys.argv[2]          # output root (UnityProject layout)
CD, RS = SRC + '/Assets/CityData/', SRC + '/Assets/Resources/'

# ------------------------------------------------------------------ io
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

objs = read_aql(CD + 'layer_buildings.bytes')
rows = list(csv.DictReader(open(CD + 'buildings.csv', encoding='utf-8')))
cols = list(rows[0].keys())
info = {int(r['bid']): r for r in rows}; N0 = len(rows)
assert all(int(r['bid']) == i for i, r in enumerate(rows))

# triangles of every building: (object index, triangle indices)
tri_of = {}
for oi, o in enumerate(objs):
    bid = o[6]
    order = np.argsort(bid, kind='stable'); u, idx = np.unique(bid[order], return_index=True)
    for i, b in enumerate(u):
        s = idx[i]; e = idx[i + 1] if i + 1 < len(idx) else len(order)
        tri_of.setdefault(int(b), []).append((oi, order[s:e]))

def verts_of(b):
    return np.vstack([objs[oi][2][objs[oi][3][t].ravel()] for oi, t in tri_of.get(b, [])]) if b in tri_of else np.zeros((0, 3), np.float32)

foot = {}
for b in tri_of:
    P = verts_of(b); foot[b] = MultiPoint(P[:, [0, 2]]).convex_hull

# terrain
tm = json.load(open(CD + 'city_meta.json'))['terrain']
TH = np.frombuffer(open(CD + 'terrain_heights.bytes', 'rb').read(), np.float32).reshape(tm['ny'], tm['nx'])
def height(x, z):
    c = (x - tm['x0']) / tm['step']; r = (z - tm['z0']) / tm['step']
    c0 = int(np.clip(np.floor(c), 0, tm['nx'] - 2)); r0 = int(np.clip(np.floor(r), 0, tm['ny'] - 2)); fc = c - c0; fr = r - r0
    h = TH[r0:r0 + 2, c0:c0 + 2]
    return float((h[0, 0] * (1 - fc) + h[0, 1] * fc) * (1 - fr) + (h[1, 0] * (1 - fc) + h[1, 1] * fc) * fr)

# masks
def img(p):
    a = np.asarray(Image.open(p)); return a
city = img(RS + 'Map/map_city.png').astype(np.float32); city = city[..., 0] if city.ndim == 3 else city
nat = img(RS + 'Map/map_nature.png').astype(np.float32) / 255.0
def uv(x, z): return 2.29357798e-5 * x + 0.5, 1.62074554e-5 * z + 0.491085899
def inside_m(x, z):
    u, v = uv(x, z); H, W = city.shape
    return (city[int(np.clip((1 - v) * (H - 1), 0, H - 1)), int(np.clip(u * (W - 1), 0, W - 1))] - 128.0) * 25.0
def water(x, z):
    u, v = uv(x, z); H, W = nat.shape[:2]
    p = nat[int(np.clip((1 - v) * (H - 1), 0, H - 1)), int(np.clip(u * (W - 1), 0, W - 1))]
    return (p[2] - p[0]) > 0.12 and p[2] > 0.3

# obstacles: roads (by class), railways and rivers
roads = json.load(open(SRC + '/Assets/StreamingAssets/twin/roads.json'))['edges']
HALF = {'highway': 11 + 10, 'ring': 9 + 9, 'main': 7.5 + 3.5 + 6, 'street': 4 + 2.4 + 5}
road_geoms = []
for e in roads:
    g = np.array(e['g'], float).reshape(-1, 2)
    if len(g) >= 2: road_geoms.append(LineString(g).buffer(HALF[e['c']], cap_style=2))
infra = {o[0]: o for o in read_aql(CD + 'layer_infrastructure.bytes')}
for nm, w in (('Railways', 18.0), ('Railways on the plan', 18.0), ('Rivers', 25.0), ('Highways', 14.0)):
    V, T = infra[nm][2], infra[nm][3]
    for t in T[::1]:
        p = V[t][:, [0, 2]]
        road_geoms.append(Polygon(p).buffer(w))
road_tree = STRtree(road_geoms)
def hits_road(g):
    for j in road_tree.query(g):
        if road_geoms[j].intersects(g): return True
    return False

# ------------------------------------------------------------------ 1. which estates are inside the city
urban_k = {'house', 'res_mid', 'res_high', 'residential', 'public', 'education', 'health', 'podium', 'tower', 'mixed', 'business', 'retail', 'hotel', 'culture'}
ind = [b for b in range(N0) if info[b]['kind'] == 'industry']
P = np.array([[float(info[b]['x']), float(info[b]['z'])] for b in ind])
from scipy.spatial import cKDTree
par = list(range(len(ind)))
def fnd(i):
    while par[i] != i: par[i] = par[par[i]]; i = par[i]
    return i
for i, j in cKDTree(P).query_pairs(260): par[fnd(i)] = fnd(j)
clusters = {}
for i in range(len(ind)): clusters.setdefault(fnd(i), []).append(i)
allXY = np.array([[float(r['x']), float(r['z'])] for r in rows]); allT = cKDTree(allXY)
isurb = np.array([r['kind'] in urban_k for r in rows])
convert = []
for c, mem in clusters.items():
    pts = P[mem]; cx, cz = pts.mean(0); R = np.hypot(*(pts - [cx, cz]).T).max() + 50
    ring = [i for i in allT.query_ball_point([cx, cz], R + 1200) if np.hypot(*(allXY[i] - [cx, cz])) > R + 150]
    urb = isurb[ring].mean() if ring else 0.0
    dist = max(set(info[ind[i]]['district'] for i in mem), key=lambda d: sum(info[ind[i]]['district'] == d for i in mem))
    if dist in ('Gate', 'Green'): conv = urb >= 0.40
    elif dist == 'Golden': conv = cx > -4500 and urb >= 0.50
    else: conv = (-4300 < cx < 6600 and urb >= 0.30)
    if conv: convert += [ind[i] for i in mem]
convert = sorted(convert)
print('estates inside the city: %d factories, %.2f mln m2' % (len(convert), sum(float(info[b]['gfa_m2']) for b in convert) / 1e6))

# ------------------------------------------------------------------ 4a. hide list (old airport, overlaps)
hide = {}
hb = open(RS + 'Landmarks/hide_extra.bytes', 'rb').read(); hn = struct.unpack('<i', hb[4:8])[0]
for i in range(hn):
    k, v = struct.unpack_from('<iI', hb, 8 + i * 8); hide[k] = v
old_air = [b for b in range(N0) if info[b]['source'] == 'master_plan' and info[b]['kind'] == 'other'
           and -7600 < float(info[b]['x']) < -4600 and 2600 < float(info[b]['z']) < 6600]
for b in old_air: hide[b] = 1
print('old airport complex hidden:', len(old_air), old_air[:12])
# the grounds of Iconic Complex (tools/build_iconic_park.py): the existing sheds in that area go when the works start (2027)
_a = math.radians(105.2); _w, _d = 270 + 720, 200 + 720
_reg = Polygon([(-2567 + u * math.cos(_a) + v * math.sin(_a), -20654 - u * math.sin(_a) + v * math.cos(_a)) for u, v in ((-_w / 2, -_d / 2), (_w / 2, -_d / 2), (_w / 2, _d / 2), (-_w / 2, _d / 2))])
for b in range(N0):
    if info[b]['source'] == 'existing_osm' and _reg.contains(Point(float(info[b]['x']), float(info[b]['z']))):
        if b not in hide or hide[b] > 27: hide[b] = 27
ids = [b for b in range(N0) if info[b]['source'] != 'existing_osm' and info[b]['kind'] not in ('house', 'solar') and b in foot and b not in convert]
geoms = [foot[b] for b in ids]; t = STRtree(geoms); nov = 0
for k, g in enumerate(geoms):
    a = ids[k]
    if a in hide: continue
    for j in t.query(g):
        c = ids[j]
        if c == a or c in hide: continue
        gc = geoms[j]; small = min(g.area, gc.area)
        if small <= 0: continue
        inter = g.intersection(gc).area
        if inter / small > 0.9: continue                 # podium + tower on one plot
        if inter / small > 0.05:
            lose = a if g.area < gc.area else c
            hide[lose] = 1; nov += 1
            if lose == a: break
print('overlapping buildings hidden:', nov)

# ------------------------------------------------------------------ 3. plots of the real plants in the belts
zones = {'east': (box(6400, -1800, 9900, 6600), (8000, 2400)), 'west': (box(-8400, -1600, -4300, 6400), (-5600, 3200))}
def long_axis(g):
    cs = list(g.minimum_rotated_rectangle.exterior.coords)[:4]
    e0 = np.subtract(cs[1], cs[0]); e1 = np.subtract(cs[2], cs[1])
    e = e0 if np.linalg.norm(e0) >= np.linalg.norm(e1) else e1
    return math.atan2(e[1], e[0]) % math.pi
# the belts are laid out on the grid of the estate that already stands there: every rebuilt factory is turned to its axis
theta = {}
for zn, (poly, _) in zones.items():
    angs = [long_axis(foot[b]) for b in ind if b not in convert and b in foot and poly.contains(foot[b].centroid)]
    a = np.array(angs); theta[zn] = float(np.angle(np.mean(np.exp(2j * a))) / 2 % math.pi) if len(a) else 0.0
    print('belt', zn, 'axis %.1f deg from %d plants' % (math.degrees(theta[zn]), len(a)))
LM = [('pepsico', 430, 300, (8350, 400)), ('mars', 430, 300, (8300, 1250)), ('sunny_paper', 440, 280, (7350, 650)),
      ('gtes', 340, 240, (9050, -600)), ('danaflex', 300, 200, (7400, -350)), ('gtrans', 290, 220, (8200, -500)),
      ('griffin', 380, 420, (-5200, 1500))]
def rect(cx, cz, w, d, yaw):
    a = math.radians(yaw); ca, sa = math.cos(a), math.sin(a)
    return Polygon([(cx + u * ca + v * sa, cz - u * sa + v * ca) for u, v in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))])
def road_yaw(x, z):
    best = None
    for e in roads:
        pass
        g = np.array(e['g'], float).reshape(-1, 2)
        d = np.hypot(g[:, 0] - x, g[:, 1] - z).min()
        if d < 1500 and (best is None or d < best[0]):
            k = int(np.argmin(np.hypot(g[:, 0] - x, g[:, 1] - z))); k = min(k, len(g) - 2); dv = g[k + 1] - g[k]
            best = (d, dv)
    if best is None: return 0.0
    dv = best[1]; return -math.degrees(math.atan2(dv[1], dv[0]))      # local x axis along the road
existing_geoms = [foot[b] for b in range(N0) if info[b]['source'] == 'existing_osm' and b in foot]
ex_tree = STRtree(existing_geoms)
all_geoms = [foot[b] for b in range(N0) if b in foot and b not in hide and b not in convert]; all_tree = STRtree(all_geoms)
pads = []
plot_out = {}
for lid, w, d, (ax_, az_) in LM:
    zn = 'east' if ax_ > 0 else 'west'; yaw = round(((-math.degrees(theta[zn]) + 90) % 180) - 90, 1); found = None   # on the belt's grid
    for rr in range(0, 2600, 40):
        n = max(1, int(2 * math.pi * rr / 40))
        for k in range(n):
            a = 2 * math.pi * k / n; x, z = ax_ + rr * math.cos(a), az_ + rr * math.sin(a)
            g = rect(x, z, w, d, yaw)
            if inside_m(x, z) < max(w, d) * 0.5 + 40: continue
            if any(water(px, pz) for px, pz in list(g.exterior.coords)[:4] + [(x, z)]): continue
            gb = g.buffer(12)
            if hits_road(gb) or any(gb.intersects(p) for p in pads): continue
            if any(existing_geoms[j].intersects(gb) for j in ex_tree.query(gb)): continue
            if any(all_geoms[j].intersects(gb) for j in all_tree.query(gb)): continue          # free land: no building of the plan under the plot
            found = (round(x), round(z)); break
        if found: break
    if not found: print('NO PLOT for', lid); continue
    pads.append(rect(found[0], found[1], w, d, yaw).buffer(25))
    plot_out[lid] = dict(X=found[0], Z=found[1], Yaw=yaw)
    print('plot %-12s X=%6d Z=%6d yaw %6.1f  (%d m from the anchor)' % (lid, found[0], found[1], yaw, rr))
json.dump(plot_out, open(OUT + '/plots.json', 'w'), indent=1)
# the airport landmark and the other plots keep clear too
pads.append(rect(-5900, 8300, 1600, 3800, 30).buffer(80))
for lid, x, z, w, d, yaw in (('tlc', 7870, 9941, 520, 220, -29.0), ('ps_arna', 1721, 620, 180, 140, 10.9)):
    pads.append(rect(x, z, w, d, yaw).buffer(25))

# ------------------------------------------------------------------ 2. rebuild the factories in the belts
occupied = [foot[b] for b in range(N0) if b in foot and b not in convert and b not in hide]
occ_tree = STRtree(occupied); new_occ = []
def free(g):
    gb = g.buffer(14)
    if any(gb.intersects(p) for p in pads): return False
    for j in occ_tree.query(gb):
        if occupied[j].intersects(gb): return False
    for q in new_occ:
        if q.intersects(gb): return False
    return not hits_road(g.buffer(6))
def cands(zone):
    poly, (axx, azz) = zones[zone]; th = theta[zone]; ux, uz = math.cos(th), math.sin(th)
    R = 6000; I, J = np.meshgrid(np.arange(-R, R, 30.0), np.arange(-R, R, 30.0)); I = I.ravel(); J = J.ravel()
    X = axx + I * ux - J * uz; Z = azz + I * uz + J * ux
    x0, z0, x1, z1 = poly.bounds; m = (X > x0) & (X < x1) & (Z > z0) & (Z < z1); X, Z = X[m], Z[m]
    d = np.hypot(X - axx, Z - azz); o = np.argsort(d); return list(zip(X[o], Z[o]))
cand = {z: cands(z) for z in zones}
def rot(P, c, dl):
    cd, sd = math.cos(dl), math.sin(dl); q = np.asarray(P, float).copy(); x = q[..., 0] - c[0]; z = q[..., 1] - c[1]
    q[..., 0] = c[0] + x * cd - z * sd; q[..., 1] = c[1] + x * sd + z * cd; return q
placed = {}                               # old bid -> (dx, dz, dy, zone)
order = sorted(convert, key=lambda b: -foot[b].area)
zone_cycle = ['east', 'east', 'west']; zi = 0
for b in order:
    g0 = foot[b]; c0 = g0.centroid; base0 = float(verts_of(b)[:, 1].min()); phi = long_axis(g0)
    done = False
    for attempt in range(2):
        zone = zone_cycle[(zi + attempt) % len(zone_cycle)]
        lst = cand[zone]; dl = (theta[zone] - phi + math.pi / 2) % math.pi - math.pi / 2
        ring0 = rot(np.array(g0.exterior.coords), (c0.x, c0.y), dl)
        for k, (x, z) in enumerate(lst):
            if inside_m(x, z) < 60 or water(x, z): continue
            g = Polygon([(px - c0.x + x, pz - c0.y + z) for px, pz in ring0])
            if not free(g): continue
            hs = [height(px, pz) for px, pz in list(g.exterior.coords)] + [height(x, z)]
            if max(hs) - min(hs) > 6.0: continue          # no factories on slopes
            new_occ.append(g); placed[b] = (x - c0.x, z - c0.y, min(hs) - 0.3 - base0, zone, dl, (c0.x, c0.y))
            del lst[:k + 1]; done = True; break
        if done: break
    zi += 1
    if not done: print('no room for factory', b)
print('factories rebuilt in the belts:', len(placed), {z: sum(1 for v in placed.values() if v[3] == z) for z in zones})

# ------------------------------------------------------------------ geometry edits
def box_tris(cx, cz, w, d, yaw, y0, h, col, yr, bid):
    a = math.radians(yaw); ca, sa = math.cos(a), math.sin(a)
    def W(u, v): return (cx + u * ca + v * sa, cz - u * sa + v * ca)
    c = [W(-w / 2, -d / 2), W(w / 2, -d / 2), W(w / 2, d / 2), W(-w / 2, d / 2)]
    V = []; T = []
    def quad(p0, p1, p2, p3):
        k = len(V); V.extend([p0, p1, p2, p3]); T.extend([(k, k + 1, k + 2), (k, k + 2, k + 3)])
    for i in range(4):
        (x0, z0), (x1, z1) = c[i], c[(i + 1) % 4]
        quad((x0, y0, z0), (x0, y0 + h, z0), (x1, y0 + h, z1), (x1, y0, z1))
    quad(*[(x, y0 + h, z) for x, z in c])
    V = np.array(V, np.float32); T = np.array(T, np.uint32)
    # outward normals: cross(b - a, c - a) must point out of the box / up
    for i, (p, q, r) in enumerate(T):
        n = np.cross(V[q] - V[p], V[r] - V[p]); m = (V[p] + V[q] + V[r]) / 3
        out = np.array([m[0] - cx, 0, m[2] - cz]) if abs(n[1]) < 0.5 * np.linalg.norm(n) else np.array([0, 1, 0])
        if np.dot(n, out) < 0: T[i] = (p, r, q)
    return V, T, np.full(len(T), col, np.uint8), np.full(len(T), yr, np.uint16), np.full(len(T), bid, np.int32)

add = {}                                  # object name -> list of (V, T, col, yr, bid)
def chunk_of(b):
    return objs[tri_of[b][0][0]][0]
remove = set(convert)
rng = np.random.default_rng(12)
newrows = []
orig = {b: dict(info[b]) for b in convert}          # the factory as it was (rebuilt in a belt below)
for b in convert:
    r = info[b]; g = foot[b].minimum_rotated_rectangle; cs = list(g.exterior.coords)[:4]
    e0 = np.subtract(cs[1], cs[0]); e1 = np.subtract(cs[2], cs[1]); L0, L1 = np.linalg.norm(e0), np.linalg.norm(e1)
    if L0 < L1: e0, e1, L0, L1 = e1, e0, L1, L0
    yaw = -math.degrees(math.atan2(e0[1], e0[0])); cc = g.centroid; u = e0 / L0; vv = e1 / L1
    base = float(verts_of(b)[:, 1].min()); yr = int(r['year']); name = chunk_of(b)
    target = 1.2 * float(r['gfa_m2'])                # about the floor area of the plant: the city around keeps its scale
    housing = rng.random() < 0.6
    blocks = []
    if housing:
        # housing bars 15 m deep along the long side, two in parallel on a wide plot (a courtyard between)
        bl = max(L0 - 14, 16)
        if L1 >= 46:
            off = L1 / 2 - 6 - 7.5
            for sg in (-1, 1): blocks.append((cc.x + vv[0] * off * sg, cc.y + vv[1] * off * sg, bl, 15.0))
        else: blocks.append((cc.x, cc.y, bl, 15.0))
        fp = sum(w * d for _, _, w, d in blocks); fl = int(np.clip(round(target / fp), 3, 7))
        kind, use, col = 'res_mid', 'housing', 0
    else:
        blocks.append((cc.x, cc.y, max(L0 - 16, 16), min(max(L1 - 12, 12), 24.0)))
        fp = blocks[0][2] * blocks[0][3]; fl = int(np.clip(round(target / fp), 3, 6))
        kind, use, col = 'public', 'business', 3
    h = fl * (3.1 if housing else 3.6) + 1.0; gfa = 0.0
    for (x, z, w, d) in blocks:
        add.setdefault(name, []).append(box_tris(x, z, w, d, yaw, base, h, col, yr, b)); gfa += w * d * fl
    r.update({'kind': kind, 'use': use, 'floors': str(fl), 'height_m': '%.1f' % h, 'gfa_m2': '%.1f' % gfa,
              'id': r['id'].replace('industry', kind)})
nb = N0
for b in sorted(placed, key=lambda q: q):
    dx, dz, dy, zone, dl, c0 = placed[b]; r = dict(orig[b]); bnew = nb; nb += 1
    for oi, tt in tri_of[b]:
        o = objs[oi]; V = o[2][o[3][tt].ravel()].copy()
        V[:, [0, 2]] = rot(V[:, [0, 2]], c0, dl).astype(np.float32); V[:, 0] += dx; V[:, 2] += dz; V[:, 1] += dy
        T = np.arange(len(V), dtype=np.uint32).reshape(-1, 3)
        add.setdefault(o[0], []).append((V, T, o[4][tt].copy(), o[5][tt].copy(), np.full(len(tt), bnew, np.int32)))
    x, z = float(r['x']) + dx, float(r['z']) + dz
    near = [i for i in allT.query(np.array([x, z]), 30)[1] if rows[i]['source'] != 'existing_osm']
    dist = max(set(rows[i]['district'] for i in near), key=lambda dd: sum(rows[i]['district'] == dd for i in near)) if near else 'Growing'
    r.update({'bid': str(bnew), 'id': '%s_industry_%s_%05d' % (dist.upper(), r['year'], bnew), 'district': dist, 'x': '%.1f' % x, 'z': '%.1f' % z,
              'ground_m': '%.1f' % (float(r['ground_m']) + dy), 'easting': '%.1f' % (float(r['easting']) + dx), 'northing': '%.1f' % (float(r['northing']) + dz),
              'parcel': str(900000 + bnew)})
    newrows.append(r)

out_objs = []
for name, kind, V, T, col, yr, bid in objs:
    keep = ~np.isin(bid, list(remove))
    if keep.all() and name not in add: out_objs.append([name, kind, V, T, col, yr, bid]); continue
    tv = V[T[keep].ravel()]; Vs = [tv]; Ts = [np.arange(len(tv), dtype=np.uint32).reshape(-1, 3)]; Cs = [col[keep]]; Ys = [yr[keep]]; Bs = [bid[keep]]; off = len(tv)
    for (v2, t2, c2, y2, b2) in add.get(name, []):
        Vs.append(v2); Ts.append(t2 + off); Cs.append(c2); Ys.append(y2); Bs.append(b2); off += len(v2)
    out_objs.append([name, kind, np.vstack(Vs), np.vstack(Ts), np.concatenate(Cs), np.concatenate(Ys), np.concatenate(Bs)])
write_aql(OUT + '/Assets/CityData/layer_buildings.bytes', out_objs)

allrows = rows + newrows
with open(OUT + '/Assets/CityData/buildings.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols, lineterminator='\n'); w.writeheader(); w.writerows(allrows)

# ------------------------------------------------------------------ 5. bounds, hide list
NB = len(allrows); B = np.zeros((NB, 4), np.float32)
for name, kind, V, T, col, yr, bid in out_objs:
    tv = V[T.ravel()]; bb = np.repeat(bid, 3)
    o = np.argsort(bb, kind='stable'); bb = bb[o]; tv = tv[o]; u, idx = np.unique(bb, return_index=True)
    for i, b in enumerate(u):
        s = idx[i]; e = idx[i + 1] if i + 1 < len(idx) else len(bb); p = tv[s:e]
        x0, z0, x1, z1 = p[:, 0].min(), p[:, 2].min(), p[:, 0].max(), p[:, 2].max()
        if B[b, 2] > B[b, 0]: x0, z0, x1, z1 = min(x0, B[b, 0]), min(z0, B[b, 1]), max(x1, B[b, 2]), max(z1, B[b, 3])
        B[b] = (x0, z0, x1, z1)
with open(OUT + '/Assets/Resources/Landmarks/bid_bounds.bytes', 'wb') as f:
    f.write(b'ABB1'); f.write(struct.pack('<i', NB)); f.write(B.astype('<f4').tobytes())
with open(OUT + '/Assets/Resources/Landmarks/hide_extra.bytes', 'wb') as f:
    f.write(b'HID1'); f.write(struct.pack('<i', len(hide)))
    for k, v in sorted(hide.items()): f.write(struct.pack('<iI', k, v))
print('buildings: %d -> %d; hidden %d' % (N0, NB, len(hide)))
json.dump({'converted': convert, 'placed': {str(k): [float(v[0]), float(v[1]), float(v[2]), v[3], float(v[4])] for k, v in placed.items()}, 'old_airport': old_air},
          open(OUT + '/relocation.json', 'w'))
