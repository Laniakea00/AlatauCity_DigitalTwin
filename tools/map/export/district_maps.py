"""The district map and the city outline of the ground shader, redrawn from the district outlines (owner 05.11.2026: «часть
города не влезла в границы, увеличь границу»).

Resources/Map/map_districts.png (district id per 20 m pixel: 30 Gate, 90 Golden, 150 Growing, 210 Green, 0 outside) and
Resources/Map/map_city.png (signed distance to the city boundary: 128 = the edge, 1 unit = 25 m, > 128 inside) were drawn from the
old twin's outlines, so land the districts own in Resources/Landmarks/districts.json (from city.json; CityStats, the labels and the
statistics use it) showed grey and muted: the quarter at (1000, −4600) between Golden and Growing, the shore of Green, and a wedge
of Golden that the old picture gave to Growing. Both pictures are rasterised again from districts.json, in the frame of the base
map (x −21800…21800, z −30300…31400, row 0 = north).
usage: python tools/map/export/district_maps.py [Assets dir]"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt as edt

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "UnityProject", "Assets")
X0, Z0, SX, SZ = -21800.0, -30300.0, 43600.0, 61700.0
VAL = {"Gate": 30, "Golden": 90, "Growing": 150, "Green": 210}
Image.MAX_IMAGE_PIXELS = None

dist_png = os.path.join(ASSETS, "Resources", "Map", "map_districts.png")
city_png = os.path.join(ASSETS, "Resources", "Map", "map_city.png")
W, H = Image.open(dist_png).size
d = json.load(open(os.path.join(ASSETS, "Resources", "Landmarks", "districts.json"), encoding="utf-8"))


def ring(p):
    return [((x - X0) / SX * W, H - (z - Z0) / SZ * H) for x, z in zip(p[0::2], p[1::2])]


ids = Image.new("L", (W, H), 0)
dr = ImageDraw.Draw(ids)
for e in d["d"]:
    dr.polygon(ring(e["p"]), fill=VAL[e["name"]])
ids.save(dist_png)
mask = np.asarray(ids) > 0
px = SX / W
sd = edt(mask) * px - edt(~mask) * px
Image.fromarray(np.clip(np.round(128 + sd / 25.0), 0, 255).astype(np.uint8), "L").save(city_png)
print(f"district_maps: {W}x{H} px, {mask.sum() * px * px / 1e4:,.0f} ha inside the city -> {dist_png}, {city_png}")
