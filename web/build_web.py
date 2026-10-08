"""Pack the film-look city into one HTML file that opens offline in a browser.

    blender -b --factory-startup --python build_web.py -- <UnityProject> <three.min.js> <out.html>

(Blender is only used to read, resize and write pictures; everything else is plain Python.)
What goes in, all from the Unity project so the page shows the same models and textures:
  buildings   Assets/CityData/layer_buildings.bytes (the model's geometry, as it is) + a table from buildings.csv
  terrain     Assets/CityData/terrain_heights.bytes (every second sample) and how the base map lies on it (city_meta.json)
  base map    Assets/Resources/Map/map_plan / map_nature / map_dev / map_blocks
  roads       Assets/StreamingAssets/twin/roads.json (geometry, class, opening year in the four scenarios)
  analytics   buildings.csv (per-building facts) and Assets/StreamingAssets/twin/*.json (synthetic city data, four scenarios)
  materials   Assets/Textures/Materials (the CC0 Poly Haven photo textures, at 512 px)
The page (page.html) rebuilds roofs, roads and trees from these by the same rules as the Unity scripts and draws the facades
with the same generator, ported to WebGL. Binary data is gzip-compressed and embedded as base64.
"""
import base64
import csv
import gzip
import json
import os
import struct
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
project, three_js, out_html = sys.argv[sys.argv.index('--') + 1:][:3]
A = os.path.join(project, 'Assets')
tmp = os.path.join(HERE, '_tmp')
os.makedirs(tmp, exist_ok=True)
KINDS = ['other', 'house', 'res_mid', 'res_high', 'residential', 'tower', 'business', 'mixed', 'hotel', 'public', 'education', 'health', 'culture', 'industry',
         'utility', 'podium', 'retail', 'solar', 'resort', 'existing']


def b64(data):
    return base64.b64encode(data).decode('ascii')


def gz(data):
    return b64(gzip.compress(data, 9, mtime=0))          # no time stamp inside: the same input gives the same page, byte for byte


def picture(src, width, fmt, quality=86):
    """Resize a picture to `width` and return its file bytes (JPEG or PNG)."""
    im = bpy.data.images.load(src)
    w, h = im.size
    if w != width:
        im.scale(width, max(1, round(h * width / w)))
    path = os.path.join(tmp, 'p.' + ('jpg' if fmt == 'JPEG' else 'png'))
    im.file_format = fmt
    im.save(filepath=path, quality=quality)
    size = tuple(im.size)
    bpy.data.images.remove(im)
    return open(path, 'rb').read(), size


def pixels(src, width):
    im = bpy.data.images.load(src)
    im.colorspace_settings.name = 'Non-Color'
    if im.size[0] != width:
        im.scale(width, width)
    a = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
    bpy.data.images.remove(im)
    return a


D = {}
# ---- buildings
D['bld'] = gz(open(os.path.join(A, 'CityData', 'layer_buildings.bytes'), 'rb').read())
rows = list(csv.DictReader(open(os.path.join(A, 'CityData', 'buildings.csv'), encoding='utf-8')))
n = max(int(r['bid']) for r in rows) + 1
kind, floors, year, height, ground = np.zeros(n, np.uint8), np.ones(n, np.uint8), np.zeros(n, np.uint8), np.zeros(n, np.uint16), np.zeros(n, np.float32)
for r in rows:
    b = int(r['bid'])
    kind[b] = KINDS.index(r['kind']) if r['kind'] in KINDS else 0
    floors[b] = min(max(int(float(r['floors'] or 1)), 1), 255)
    year[b] = min(max(int(r['year']) - 2000, 0), 255)
    height[b] = min(int(round(float(r['height_m']) * 10)), 65535)
    ground[b] = float(r['ground_m'])
D['tab'] = gz(struct.pack('<I', n) + kind.tobytes() + floors.tobytes() + year.tobytes() + height.tobytes() + ground.tobytes())
# ---- analytics: what the twin's panels are computed from. Per-building facts (district, use, source, floor area, place, how long it is built,
#      delay, contractor, flood depth) and the synthetic city data of all four scenarios (balances, social, traffic, money, plan and fact).
TW = os.path.join(A, 'StreamingAssets', 'twin')


def twin(name):
    return json.load(open(os.path.join(TW, name + '.json'), encoding='utf-8'))


def per(a, dtype, top):
    v = np.zeros(n, dtype)
    m = min(n, len(a))
    v[:m] = np.clip(np.asarray(a[:m]), 0, top)
    return v


con, risk, loads, fin, net, tr, scn = (twin(x) for x in ('construction', 'risk', 'loads', 'finance', 'networks', 'traffic', 'scenarios'))
DIST, USES, SRC = ['Gate', 'Golden', 'Growing', 'Green'], ['housing', 'business', 'social', 'industry', 'leisure', 'energy', 'existing'], ['generated', 'master_plan', 'existing_osm']
dist, use, srcb = np.full(n, 255, np.uint8), np.full(n, 255, np.uint8), np.zeros(n, np.uint8)
gfa, bx, bz = np.zeros(n, np.float32), np.zeros(n, np.int16), np.zeros(n, np.int16)
for r in rows:
    b = int(r['bid'])
    dist[b] = DIST.index(r['district']) if r['district'] in DIST else 255
    use[b] = USES.index(r['use']) if r['use'] in USES else 255
    srcb[b] = SRC.index(r['source']) if r['source'] in SRC else 0
    gfa[b] = float(r['gfa_m2'] or 0)
    bx[b], bz[b] = int(np.clip(round(float(r['x']) / 2), -32767, 32767)), int(np.clip(round(float(r['z']) / 2), -32767, 32767))
pb = con['per_building']
D['tab2'] = gz(dist.tobytes() + use.tobytes() + srcb.tobytes() + per(pb['duration_years'], np.uint8, 255).tobytes() + per(pb['delay_months'], np.uint8, 255).tobytes()
               + per(pb['contractor'], np.uint8, 255).tobytes() + gfa.tobytes() + bx.tobytes() + bz.tobytes()
               + per(risk['scenarios']['flood_1pct']['depth_cm'], np.uint16, 65535).tobytes() + per(risk['scenarios']['flood_ext']['depth_cm'], np.uint16, 65535).tobytes())
SK = ['base', 'fast', 'slow', 'infra']
D['twin'] = dict(
    version=loads['version'], scen=[dict(name=x['name'], desc=x['desc']) for x in scn['scenarios']],
    bal={res: [[loads['balance'][s][res]['city']] + list(loads['balance'][s][res]['districts']) for s in SK] for res in loads['balance']['base']},
    loads={k: [loads['loads'][s][k] for s in SK] for k in loads['loads']['base'] if k != 'gfa'},
    soc=dict(keys=loads['social_keys'], need=[loads['social'][s]['need'] for s in SK], cap=[loads['social'][s]['cap'] for s in SK]),
    fac=[dict(name=f['name'], res=f['res'], kind=f['kind'], district=f['district'], x=f['x'], z=f['z'], unit=f.get('unit'), note=f.get('note') or '', synthetic=bool(f.get('synthetic')),
              stages=f['stages'], delayed=f.get('delayed_stages') or [], cap=f.get('cap'), demand=f.get('demand')) for f in net['facilities']],
    units=net['units'],
    lrt=dict(km=con['lrt']['phase_km'], names=con['lrt']['phase_names'], year=[con['lrt']['phase_year'][s] for s in SK], stations=con['lrt']['stations']),
    sc={k: [con['s_curves'][s][k] for s in SK] for k in ('plan', 'fact')},
    fin=dict(bld=[fin['by_scenario'][s]['buildings'] for s in SK], src=[fin['by_scenario'][s]['sources'] for s in SK],
             fact=[fin['by_scenario'][s]['fact'] for s in SK], infra=[fin['by_scenario'][s]['infra'] for s in SK]),
    tr=dict(years=tr['years'], kpi=[[tr['by_scenario'][s][str(y)]['kpi'] for y in tr['years']] for s in SK]),
    contractors=[c['name'] for c in con['contractors']])
# ---- rivers of the model (plan positions; the page lays them on its own ground) and the site of one planned bridge with what the twin knows
#      about it: the street it carries, the networks laid along that street, the river under it
def layer(path):
    d = open(path, 'rb').read()
    cnt, off, objs = struct.unpack_from('<i', d, 4)[0], 8, {}
    for _ in range(cnt):
        nl = struct.unpack_from('<H', d, off)[0]
        name = d[off + 2:off + 2 + nl].decode('utf-8')
        off += 2 + nl + 1
        nv, nt = struct.unpack_from('<ii', d, off)
        off += 8
        V = np.frombuffer(d, '<f4', nv * 3, off).reshape(nv, 3)
        off += nv * 12
        Tr = np.frombuffer(d, '<u4', nt * 3, off).reshape(nt, 3)
        off += nt * 12 + nt + nt * 2 + nt * 4
        objs[name] = (V, Tr)
    return objs


infra = layer(os.path.join(A, 'CityData', 'layer_infrastructure.bytes'))
RV, RT = infra['Rivers']
assert len(RV) < 65536
D['rivers'] = gz(struct.pack('<II', len(RV), len(RT)) + np.round(RV[:, [0, 2]] * 10).astype('<i4').tobytes() + RT.astype('<u2').tobytes())
BV, BT = infra['Planned bridges']
SITE_AT = np.array([317.0, -8113.0])                    # the planned bridge chosen for the site scenario (Golden District)
ids = {}
vid = np.array([ids.setdefault((round(float(q[0]), 1), round(float(q[1]), 1), round(float(q[2]), 1)), len(ids)) for q in BV])
par = list(range(len(ids)))


def root(a):
    while par[a] != a:
        par[a] = par[par[a]]
        a = par[a]
    return a


for tr3 in BT:
    r0 = root(int(vid[tr3[0]]))
    par[root(int(vid[tr3[1]]))] = r0
    par[root(int(vid[tr3[2]]))] = r0
grp = {}
for i, q in enumerate(BV):
    grp.setdefault(root(int(vid[i])), []).append(q)
box8 = min(grp.values(), key=lambda P: float(np.hypot(np.mean([q[0] for q in P]) - SITE_AT[0], np.mean([q[2] for q in P]) - SITE_AT[1])))
box8 = np.array(box8)
low = box8[box8[:, 1] < box8[:, 1].mean()]
cen = low[:, [0, 2]].mean(axis=0)
assert len(low) == 4 and np.hypot(*(cen - SITE_AT)) < 30, 'the bridge of the site scenario was not found in the model'
ang = np.arctan2(low[:, 2] - cen[1], low[:, 0] - cen[0])
low = low[np.argsort(ang)]                             # corners in order round the deck
edges = roads_all = json.load(open(os.path.join(TW, 'roads.json'), encoding='utf-8'))['edges']
ei = min(range(len(edges)), key=lambda i: float(np.hypot(np.mean(edges[i]['g'][0::2]) - cen[0], np.mean(edges[i]['g'][1::2]) - cen[1])))
near_roads = []
for i, e in enumerate(edges):
    gg = np.array(e['g']).reshape(-1, 2)
    if i != ei and float(np.hypot(gg[:, 0] - cen[0], gg[:, 1] - cen[1]).min()) < 130:
        near_roads.append(dict(edge=i, cls=e['c'], years=e['y'], g=[round(float(v), 1) for v in e['g']]))
D['twin']['site'] = dict(
    corners=[[round(float(q[0]), 1), round(float(q[2]), 1)] for q in low], y0=round(float(box8[:, 1].min()), 1), y1=round(float(box8[:, 1].max()), 1),
    edge=ei, cls=edges[ei]['c'], years=edges[ei]['y'], len=edges[ei]['len'],
    nets=[dict(res=k, size=sg[1], years=sg[2:6]) for k, v in net['networks'].items() for sg in v if sg[0] == ei], roads=near_roads)
print('site bridge:', D['twin']['site']['corners'], 'edge', ei, edges[ei]['c'], edges[ei]['y'], 'networks', [(q['res'], q['size'], q['years'][0]) for q in D['twin']['site']['nets']], 'roads near', len(near_roads))
meta = json.load(open(os.path.join(A, 'CityData', 'city_meta.json'), encoding='utf-8'))
# ---- terrain: every second height sample, 16 bits
t = meta['terrain']
h = np.frombuffer(open(os.path.join(A, 'CityData', 'terrain_heights.bytes'), 'rb').read(), '<f4')[:t['nx'] * t['ny']].reshape(t['ny'], t['nx'])[::2, ::2]
lo, hi = float(h.min()), float(h.max())
D['ter'] = gz(np.round((h - lo) / (hi - lo) * 65535).astype('<u2').tobytes())
D['meta'] = dict(nx=int(h.shape[1]), ny=int(h.shape[0]), step=t['step'] * 2, x0=t['x0'], z0=t['z0'], lo=lo, hi=hi, ua=t['u_a'], ub=t['u_b'], va=t['v_a'], vb=t['v_b'],
                 kinds=KINDS, palette=[p['rgb'] for p in meta['palette']], cameras=meta.get('cameras', []), buildings=len(rows))
# ---- roads
roads = json.load(open(os.path.join(A, 'StreamingAssets', 'twin', 'roads.json'), encoding='utf-8'))
cls = dict(highway=0, ring=1, main=2, street=3)
buf = [struct.pack('<I', len(roads['edges']))]
for e in roads['edges']:
    g = e['g']
    ys = [min(max(int(e['y'][min(k, len(e['y']) - 1)]) - 2000, 0), 255) for k in range(4)]      # opening year in the four scenarios
    buf.append(struct.pack('<B4BH', cls.get(e['c'], 3), *ys, len(g) // 2))
    buf.append(np.round(np.asarray(g, dtype=np.float64) * 10).astype('<i4').tobytes())
D['roads'] = gz(b''.join(buf))
# ---- base map
M = os.path.join(A, 'Resources', 'Map')
plan, plan_size = picture(os.path.join(M, 'map_plan.png'), 4096, 'JPEG', 88)
nat, _ = picture(os.path.join(M, 'map_nature.png'), 2048, 'JPEG', 84)
D['plan'], D['nat'] = b64(plan), b64(nat)
D['dev'] = b64(open(os.path.join(M, 'map_dev.png'), 'rb').read())
D['blocks'] = b64(open(os.path.join(M, 'map_blocks.png'), 'rb').read())
# ---- material photo textures: colour, and (normal x, normal y, occlusion) packed in one picture
mats = []
src = os.path.join(A, 'Textures', 'Materials')
for f in sorted(x for x in os.listdir(src) if x.endswith('_diff.jpg')):
    stem = os.path.join(src, f[:-len('_diff.jpg')])
    a, _ = picture(stem + '_diff.jpg', 512, 'JPEG', 84)
    nor, arm = pixels(stem + '_nor.jpg', 512), pixels(stem + '_arm.jpg', 512)
    packed = np.concatenate([nor[:, :, :2], arm[:, :, :1], np.ones_like(arm[:, :, :1])], axis=2)
    im = bpy.data.images.new('pack', 512, 512, alpha=False)
    im.colorspace_settings.name = 'Non-Color'
    im.pixels = packed.ravel()
    p = os.path.join(tmp, 'd.jpg')
    im.file_format = 'JPEG'
    im.save(filepath=p, quality=88)
    bpy.data.images.remove(im)
    mats.append(dict(name=f[3:-len('_diff.jpg')], a=b64(a), d=b64(open(p, 'rb').read())))
D['mat'] = mats

page = open(os.path.join(HERE, 'page.html'), encoding='utf-8').read()
three = open(three_js, encoding='utf-8').read()
assert all(k in page for k in ('/*THREE*/', '/*DATA*/', '/*GLSL*/', '/*APP*/'))
glsl = open(os.path.join(HERE, 'glsl_film.js'), encoding='utf-8').read() + open(os.path.join(HERE, 'glsl_parts.js'), encoding='utf-8').read()
app = '\n'.join(open(os.path.join(HERE, x), encoding='utf-8').read() for x in ('analytics_text.js', 'analytics.js', 'objects_text.js', 'objects.js', 'site.js', 'app.js'))
html = page.replace('/*THREE*/', three.replace('</script', '<\\/script')).replace('/*DATA*/', 'const DATA = ' + json.dumps(D, separators=(',', ':')) + ';')
html = html.replace('/*GLSL*/', glsl).replace('/*APP*/', app)
open(out_html, 'w', encoding='utf-8').write(html)
sizes = {k: round(len(v) / 1e6, 2) for k, v in D.items() if isinstance(v, str)}
print('embedded MB:', sizes, 'materials', round(sum(len(m['a']) + len(m['d']) for m in mats) / 1e6, 2))
print(f'{out_html}: {os.path.getsize(out_html) / 1e6:.1f} MB')
