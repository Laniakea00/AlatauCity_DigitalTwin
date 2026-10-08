"""Snapshot of the web version: the page, the textures it is built from, the model data and the page's source.

    python make_zip.py <out.zip>
"""
import os
import sys
import zipfile

ROOT = 'C:/Work/AlatauCity_DigitalTwin'
A = ROOT + '/UnityProject/Assets'
out = sys.argv[1]
items = []                                              # (file on disk, name in the archive)
items.append((ROOT + '/web/AlatauCity_Film_3D.html', 'AlatauCity_Film_3D.html'))
for f in sorted(os.listdir(A + '/Textures/Materials')):
    if not f.endswith('.meta'):
        items.append((A + '/Textures/Materials/' + f, 'textures/materials/' + f))
for f in ('map_plan.png', 'map_nature.png', 'map_dev.png', 'map_blocks.png'):
    items.append((A + '/Resources/Map/' + f, 'textures/maps/' + f))
for f in ('layer_buildings.bytes', 'layer_infrastructure.bytes', 'buildings.csv', 'terrain_heights.bytes', 'city_meta.json'):
    items.append((A + '/CityData/' + f, 'models/' + f))
for f in sorted(os.listdir(A + '/StreamingAssets/twin')):
    if f.endswith('.json'):
        items.append((A + '/StreamingAssets/twin/' + f, 'data/' + f))
for f in sorted(os.listdir(ROOT + '/web')):
    if f.endswith(('.js', '.py', '.sh', '.html')) and not f.startswith(('AlatauCity_', 'dbg_')):
        items.append((ROOT + '/web/' + f, 'source/' + f))
readme = """Alatau City, web version: snapshot

AlatauCity_Film_3D.html   the page: open it in Edge or Chrome, no server and no internet needed
textures/materials        the twelve CC0 photo texture sets from Poly Haven (colour, normal, AO-roughness-metal) and SOURCES.txt
textures/maps             base maps of the twin: master plan, land before development, year of development, distance to the road corridors
models                    the city model as the twin stores it: buildings (geometry and table), terrain heights, palette and cameras
data                      the twin's synthetic city data (four scenarios): roads, networks, loads, construction, money, traffic, flood risk
source                    how the page is built: build.sh runs build_web.py (in Blender) and the browser test

Demo scenario on simulated data, not official data. Model and build-out scenario: the QTwin set; master plan: Government Resolution
No. 388 of 17.05.2024; existing buildings (c) OpenStreetMap contributors (ODbL); textures: Poly Haven (CC0).
"""
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    z.writestr('README.txt', readme)
    for src, name in items:
        z.write(src, name)
print(f'{out}: {os.path.getsize(out) / 1e6:.1f} MB, {len(items) + 1} files')
with zipfile.ZipFile(out) as z:
    bad = z.testzip()
    print('archive check:', 'ok' if bad is None else 'broken: ' + bad)
