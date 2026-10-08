"""City blocks for the film look: a distance map of the road corridors.

    python gen_blocks.py <Assets/StreamingAssets/twin/roads.json> <Assets/CityData/city_meta.json> <Assets/Resources/Map/map_blocks.png>

The base map is painted at about 5 m per pixel with soft edges, so up close a block has no edge at all. This raster stores,
for every place, the distance in metres to the edge of the nearest road corridor (the carriageway, its pavements and a verge,
by road class: the same cross-sections as FilmRoads.cs). A distance interpolates smoothly, so the ground shader can draw the
block edge as a sharp line at any zoom from a small picture (4096 pixels wide, about 10.6 m per pixel).

Pixel value: 128 = the corridor edge, +2 per metre into the block, -2 per metre into the corridor (clamped at 64 m).
Needs numpy only. The corridor widths are assumed typical cross-sections, not survey data.
"""
import json
import struct
import sys
import zlib

import numpy as np

roads_path, meta_path, out_path = sys.argv[1:4]
W = 4096
RANGE = 64.0
# half width of the corridor by class: carriageway + pavement + verge (FilmRoads.Dims plus the verge)
CORRIDOR = dict(highway=11.0 + 2.0, ring=9.0 + 2.0, main=7.5 + 3.5 + 1.5, street=4.0 + 2.4 + 1.2)

meta = json.load(open(meta_path, encoding='utf-8'))['terrain']
ua, ub, va, vb = meta['u_a'], meta['u_b'], meta['v_a'], meta['v_b']
H = int(round(W * ua / va))
px = 1.0 / (ua * W)                                            # metres per pixel
roads = json.load(open(roads_path, encoding='utf-8'))
sd = np.full((H, W), RANGE, dtype=np.float32)                 # row 0 = south (v = 0)
xs = ((np.arange(W) + 0.5) / W - ub) / ua
zs = ((np.arange(H) + 0.5) / H - vb) / va
n = 0
for e in roads['edges']:
    half = CORRIDOR.get(e['c'], CORRIDOR['street'])
    g = np.asarray(e['g'], dtype=np.float64).reshape(-1, 2)
    for a, b in zip(g[:-1], g[1:]):
        r = RANGE + half
        i0, i1 = int(((min(a[0], b[0]) - r) * ua + ub) * W), int(((max(a[0], b[0]) + r) * ua + ub) * W) + 1
        j0, j1 = int(((min(a[1], b[1]) - r) * va + vb) * H), int(((max(a[1], b[1]) + r) * va + vb) * H) + 1
        i0, i1, j0, j1 = max(i0, 0), min(i1, W), max(j0, 0), min(j1, H)
        if i0 >= i1 or j0 >= j1:
            continue
        X, Z = np.meshgrid(xs[i0:i1], zs[j0:j1])
        ab = b - a
        t = np.clip(((X - a[0]) * ab[0] + (Z - a[1]) * ab[1]) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
        d = np.hypot(X - (a[0] + ab[0] * t), Z - (a[1] + ab[1] * t)) - half
        np.minimum(sd[j0:j1, i0:i1], d, out=sd[j0:j1, i0:i1])
        n += 1
img = np.clip(np.round(128.0 + 2.0 * sd), 0, 255).astype(np.uint8)[::-1]            # PNG rows run from the top


def chunk(tag, data):
    c = struct.pack('>I', len(data)) + tag + data
    return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)


raw = np.concatenate([np.zeros((H, 1), np.uint8), img], axis=1).tobytes()         # filter byte 0 per row
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 0, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b'')
open(out_path, 'wb').write(png)
print(f'{n:,} road segments -> {out_path}: {W} x {H} px, {px:.2f} m per pixel, {len(png) / 1e6:.1f} MB; in a corridor {100 * float((sd < 0).mean()):.1f} % of the map, within 64 m of one {100 * float((sd < RANGE - 0.01).mean()):.1f} %')
