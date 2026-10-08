"""Export QTwin Alatau_City_3D.blend -> compact binaries for procedural meshing in Unity (no FBX/OBJ import).
Unity frame: X = blender X (east), Y = blender Z (elevation, m a.s.l.), Z = blender Y (north). Same origin as the blend.
Run:  python3 -I blend_export.py <blend> <out CityData dir> <qtwin manifest csv>"""
import bpy, sys, os, struct, json, csv
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

BLEND, OUT, MANIFEST = sys.argv[1:4]
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=BLEND)
deps = bpy.context.evaluated_depsgraph_get()

def lin2srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)

# ---------- palette (material -> sRGB colour) ----------
PAL = []; PALIDX = {}
def mat_color(m):
    if m is None: return (0.8, 0.8, 0.8)
    for n in (m.node_tree.nodes if m.node_tree else []):
        if n.type == 'BSDF_PRINCIPLED': return tuple(n.inputs['Base Color'].default_value[:3])
    return tuple(m.diffuse_color[:3])
def pal(m):
    key = m.name if m else '_none'
    if key not in PALIDX:
        PALIDX[key] = len(PAL); PAL.append({'name': key, 'rgb': [round(float(x), 4) for x in lin2srgb(mat_color(m))]})
    return PALIDX[key]

# ---------- visibility ----------
vis = set()
def walk(lc):
    if lc.exclude or lc.collection.hide_render: return
    for o in lc.collection.objects: vis.add(o.name)
    for c in lc.children: walk(c)
walk(bpy.context.view_layer.layer_collection)

def mesh_arrays(o):
    ev = o.evaluated_get(deps); me = ev.to_mesh()
    me.calc_loop_triangles()
    nv = len(me.vertices); co = np.empty(nv * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    M = np.array(o.matrix_world, np.float64); co = (co @ M[:3, :3].T + M[:3, 3]).astype(np.float64)
    nt = len(me.loop_triangles)
    tv = np.empty(nt * 3, np.int64); me.loop_triangles.foreach_get('vertices', tv); tv = tv.reshape(-1, 3)
    tp = np.empty(nt, np.int64); me.loop_triangles.foreach_get('polygon_index', tp)
    npoly = len(me.polygons)
    pm = np.empty(npoly, np.int64); me.polygons.foreach_get('material_index', pm)
    pn = np.empty(npoly * 3, np.float32); me.polygons.foreach_get('normal', pn); pn = pn.reshape(-1, 3) @ M[:3, :3].T
    attrs = {}
    for name in ('year', 'parcel'):
        a = me.attributes.get(name)
        if a is not None and a.domain == 'FACE':
            v = np.empty(len(a.data), np.int64); a.data.foreach_get('value', v); attrs[name] = v
    slots = [pal(s.material) for s in o.material_slots] or [pal(None)]
    tri_col = np.array(slots, np.int64)[np.clip(pm[tp], 0, len(slots) - 1)]
    ev.to_mesh_clear()
    # Unity frame + winding: Unity front face = Cross(b-a, c-a) (left-handed); orient each triangle along the Blender polygon normal
    U = co[:, [0, 2, 1]]
    nU = pn[tp][:, [0, 2, 1]]
    a, b, c = U[tv[:, 0]], U[tv[:, 1]], U[tv[:, 2]]
    cr = np.cross(b - a, c - a)
    flip = np.einsum('ij,ij->i', cr, nU) < 0
    tv[flip] = tv[flip][:, ::-1]
    return U, tv, tri_col, tp, attrs

# ---------- terrain as a height grid ----------
T = bpy.data.objects['Terrain']; me = T.data
nv = len(me.vertices); co = np.empty(nv * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3).astype(np.float64)
xs = np.unique(np.round(co[:, 0], 3)); ys = np.unique(np.round(co[:, 1], 3))
nx, ny = len(xs), len(ys); step = float(xs[1] - xs[0])
assert nx * ny == nv, (nx, ny, nv)
ix = np.rint((co[:, 0] - xs[0]) / step).astype(int); iy = np.rint((co[:, 1] - ys[0]) / step).astype(int)
H = np.zeros((ny, nx), np.float32); H[iy, ix] = co[:, 2]          # row 0 = south
# UV fit (per loop)
nl = len(me.loops); lv = np.empty(nl, np.int64); me.loops.foreach_get('vertex_index', lv)
uv = np.empty(nl * 2, np.float32); me.uv_layers[0].data.foreach_get('uv', uv); uv = uv.reshape(-1, 2)
A = np.c_[co[lv, 0], np.ones(nl)]; ku = np.linalg.lstsq(A, uv[:, 0], rcond=None)[0]
B = np.c_[co[lv, 1], np.ones(nl)]; kv = np.linalg.lstsq(B, uv[:, 1], rcond=None)[0]
res = max(np.abs(A @ ku - uv[:, 0]).max(), np.abs(B @ kv - uv[:, 1]).max())
print('terrain grid', nx, ny, 'step', step, 'x0', xs[0], 'y0', ys[0], 'z', H.min(), H.max(), 'uv fit', ku, kv, 'max residual', res)
H.astype('<f4').tofile(os.path.join(OUT, 'terrain_heights.bytes'))
img = bpy.data.images['Alatau master plan zoning']
open(os.path.join(OUT, '..', 'Textures', 'master_plan_zoning.png'), 'wb').write(img.packed_file.data)
terrain_meta = {'nx': nx, 'ny': ny, 'step': step, 'x0': float(xs[0]), 'z0': float(ys[0]), 'u_a': float(ku[0]), 'u_b': float(ku[1]), 'v_a': float(kv[0]), 'v_b': float(kv[1]),
                'zmin': float(H.min()), 'zmax': float(H.max()), 'texture': 'master_plan_zoning.png', 'texture_size': list(img.size)}

# ---------- manifest (QTwin page data) for passports ----------
man = list(csv.DictReader(open(MANIFEST)))
SRC_OF = {'existing_osm': 'existing', 'master_plan': 'plan', 'generated': 'generated'}
trees = {}
for s in ('existing', 'plan', 'generated'):
    rows = [r for r in man if SRC_OF[r['source']] == s]
    pts = np.array([[float(r['x']), float(r['z_north']) + 550.0] for r in rows])   # blend Y = page north + 550
    trees[s] = (cKDTree(pts), rows)

# ---------- layers ----------
BUILD = []; INFRA = []; LABELS = []
for o in bpy.data.objects:
    if o.name not in vis or o.hide_render: continue
    n = o.name
    if o.type == 'MESH':
        if n.startswith('Terrain') or n.startswith('Red lines'): continue
        if n == 'Existing buildings': BUILD.append((o, 'existing', 2023))
        elif ' generated ' in n or ' master plan buildings' in n:
            yr = int(n.split()[0]); BUILD.append((o, 'plan' if 'master plan' in n else 'generated', yr))
        elif n.startswith('Legend'): LABELS.append(o)
        else: INFRA.append(o)
    elif o.type == 'FONT' and not n.startswith('Year '):
        LABELS.append(o)
print('buildings objs', len(BUILD), 'infra', [o.name for o in INFRA], 'labels', len(LABELS))

class Writer:
    def __init__(self, path): self.f = open(path, 'wb'); self.f.write(b'AQL1'); self.count_pos = self.f.tell(); self.f.write(struct.pack('<i', 0)); self.n = 0
    def add(self, name, kind, U, tv, col, year, bid):
        nb = name.encode('utf8')
        self.f.write(struct.pack('<H', len(nb)) + nb + struct.pack('<Bii', kind, len(U), len(tv)))
        self.f.write(U.astype('<f4').tobytes()); self.f.write(tv.astype('<u4').tobytes())
        self.f.write(col.astype('u1').tobytes()); self.f.write(year.astype('<u2').tobytes()); self.f.write(bid.astype('<i4').tobytes())
        self.n += 1
    def close(self): self.f.seek(self.count_pos); self.f.write(struct.pack('<i', self.n)); self.f.close()

# buildings: one record per object, building id per triangle via connected components
wb = Writer(os.path.join(OUT, 'layer_buildings.bytes'))
btable = []; matched = 0
KIND_FROM_MAT = lambda name: name.replace('Generated ', '').replace('Plan ', '').replace('Existing building', 'existing').replace(' roof', '').strip()
for o, src, yr in BUILD:
    U, tv, col, tp, attrs = mesh_arrays(o)
    nvx = len(U); m = len(tv)
    rows = np.repeat(np.arange(m), 3); g = coo_matrix((np.ones(m * 3), (rows, tv.ravel())), shape=(m, nvx)).tocsr()
    # triangles connected through shared vertices -> components
    vt = coo_matrix((np.ones(m * 3), (tv.ravel(), rows)), shape=(nvx, m)).tocsr()
    adj = (g @ vt)
    ncomp, lab = connected_components(adj, directed=False)
    base = len(btable)
    ty = attrs['year'][tp] if 'year' in attrs else np.full(m, yr)
    tpar = attrs['parcel'][tp] if 'parcel' in attrs else np.full(m, -1)
    # per-component stats
    order = np.argsort(lab, kind='stable'); bounds = np.searchsorted(lab[order], np.arange(ncomp + 1))
    cent = np.zeros((ncomp, 2)); zmin = np.zeros(ncomp); zmax = np.zeros(ncomp); kinds = []; years = np.zeros(ncomp, int); parcels = np.zeros(ncomp, int)
    for k in range(ncomp):
        tri = order[bounds[k]:bounds[k + 1]]; vv = np.unique(tv[tri].ravel()); P = U[vv]
        cent[k] = [P[:, 0].mean(), P[:, 2].mean()]; zmin[k] = P[:, 1].min(); zmax[k] = P[:, 1].max()
        cc = np.bincount(col[tri]).argmax(); kinds.append(KIND_FROM_MAT(PAL[cc]['name']))
        years[k] = int(np.bincount(ty[tri] - 2000).argmax()) + 2000; parcels[k] = int(np.bincount(tpar[tri] + 1).argmax()) - 1
    tree, mrows = trees[src]; d, idx = tree.query(cent, distance_upper_bound=15.0)
    for k in range(ncomp):
        r = mrows[idx[k]] if np.isfinite(d[k]) else None
        if r is not None: matched += 1
        east = 663000.0 + cent[k, 0]; north = 4830000.0 + cent[k, 1]
        h = round(float(zmax[k] - zmin[k]), 1)
        btable.append({'bid': base + k, 'id': r['id'] if r else f'{src.upper()}_{kinds[k]}_{years[k]}_{base + k:06d}', 'district': r['district'] if r else '', 'kind': r['kind'] if r else kinds[k],
                       'use': r['use'] if r else '', 'source': {'existing': 'existing_osm', 'plan': 'master_plan', 'generated': 'generated'}[src], 'year': years[k],
                       'floors': r['floors'] if r else max(1, int(h // 3.2)), 'height_m': h, 'gfa_m2': r['gfa_m2'] if r else '', 'parcel': parcels[k] if parcels[k] >= 0 else '',
                       'x': round(float(cent[k, 0]), 1), 'z': round(float(cent[k, 1]), 1), 'ground_m': round(float(zmin[k]), 1), 'easting': round(east, 1), 'northing': round(north, 1)})
    wb.add(o.name, 0, U, tv, col, ty, base + lab)
    print(f'{o.name:32s} tris {m:7d} buildings {ncomp:6d}', flush=True)
wb.close()
print('building records', len(btable), 'matched to QTwin manifest', matched)
with open(os.path.join(OUT, 'buildings.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(btable[0].keys())); w.writeheader(); w.writerows(btable)

wi = Writer(os.path.join(OUT, 'layer_infrastructure.bytes'))
for o in INFRA:
    U, tv, col, tp, attrs = mesh_arrays(o); wi.add(o.name, 1, U, tv, col, np.zeros(len(tv)), np.full(len(tv), -1)); print('infra', o.name, len(tv))
wi.close()
wl = Writer(os.path.join(OUT, 'layer_labels.bytes'))
for o in LABELS:
    U, tv, col, tp, attrs = mesh_arrays(o)
    if len(tv) == 0: continue
    wl.add(o.name, 2, U, tv, col, np.zeros(len(tv)), np.full(len(tv), -1))
print('labels', wl.n); wl.close()

cams = []
for o in bpy.data.objects:
    if o.type == 'CAMERA':
        M = np.array(o.matrix_world); fwd = -M[:3, 2]; p = M[:3, 3]
        cams.append({'name': o.name, 'pos': [float(p[0]), float(p[2]), float(p[1])], 'fwd': [float(fwd[0]), float(fwd[2]), float(fwd[1])], 'lens': o.data.lens})
json.dump({'terrain': terrain_meta, 'palette': PAL, 'cameras': cams, 'utm': {'easting_offset': 663000.0, 'northing_offset': 4830000.0, 'epsg': 32643},
           'source': os.path.basename(BLEND)}, open(os.path.join(OUT, 'city_meta.json'), 'w'), indent=1, ensure_ascii=False)
for fn in sorted(os.listdir(OUT)): print(fn, round(os.path.getsize(os.path.join(OUT, fn)) / 1e6, 2), 'MB')
