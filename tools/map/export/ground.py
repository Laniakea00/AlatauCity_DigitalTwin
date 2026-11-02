"""Ground of the redrawn map for Unity (w48): what lies between the buildings of the merged districts, from the data.

    python3 tools/map/export/ground.py --run <run> --districts a,b [--out OUT] [--base TWIN] [--blocks-base PNG] [--nature-base PNG]
                                       [--picture PNG]

Runs after merge_districts.py (the orchestrator chains it). Reads OUT/<d>/{blocks,lots,features,network,driveways}.json of each
district and the run's merged roads OUT/_merged/<run>/Assets/StreamingAssets/twin/roads.json, and writes into
OUT/_merged/<run>/Assets/Resources/Map/ (same paths as in the Unity project):

  map_ground.bytes  NEW. The yard type of every piece of ground inside the districts' areas, as triangles (GRD1, below). Unity
                    (Layers/GroundTypes.cs) draws them into two small render textures round the camera; AlatauGround.shader then
                    draws each lot's own yard (TYPES) instead of the random yards it paints from the old plan colours.
  map_blocks.png    distance to the road corridors (format of UnityProject/Tools/twin_gen/gen_blocks.py): inside the areas
                    from the merged roads, half width = red line of the street profile (roads.json `profiles`) or the class width;
                    outside the areas the pixels of the project's own map_blocks.png, byte for byte (the twin upload has none: it is
                    looked for in --blocks-base, <base>, $ALATAU_MAP_BLOCKS, the checkout and the build machine's project copy;
                    --blocks-regen rebuilds a base from the base roads.json with gen_blocks.py's algorithm instead).
  map_plan.png      zoning colours (gen_map.py palette, relief shading, 0.55 px blur) repainted inside the areas from lot use, street
                    corridors light, corridors of expressways and their ramps dark (as gen_map.py draws the motorways); water of the base plan
                    and keep land stay as they are; outside the areas the base pixels unchanged.
  map_dev.png       development year (value + 2000, 0 = always, 255 = never) repainted inside the areas: street corridors by their
                    street's first year, lots by the year of their ground (ground_years: the first building; a lot of a use that needs
                    a building and has none: never), the rest from the nearest; outside the areas the base pixels unchanged. The shader
                    derives the other scenarios with _AlatauDevK.
  map_nature.png    the ground before development (gen_map.py: steppe with a faint ghost of the old plan) with the ghost taken out inside
                    the areas: plain steppe with the relief shading (base from --nature-base …, written only when found).

  map_walks.json    NEW. The walks of the parks (made by rule: the spec has none) and where the benches and every playground's equipment
                    stand, in the parks and in the yards: {"v":1, "walks":[{"y":[4 years], "w":width m, "k":0 alley | 1 loop,
                    "p":[x,z,…]}], "benches":[{"y":[4], "k":0 park | 1 yard, "b":[x,z,yaw°,…]}], "play":[{"y":[4], "k":0 park |
                    1 yard | 2 playground lot, "a":yaw°, "p":[x,z,…]}]} (yaw = the way a bench faces / the long side of a playground,
                    degrees from +x towards +z). A walk runs from the kerb of a pavement into the park. People walk the walks (FilmLife),
                    GroundProps.cs draws the benches and the equipment.

and adds the files to OUT/_merged/<run>/manifest.json (`files`, plus a `ground` block with the counts).

GRD1 (little-endian):
  'GRD1', i32 version = 1, f32 x0, z0, x1, z1 (bounds of all triangles, Unity metres), i32 nChunks;
  per chunk: f32 ox, oz (origin), i32 nv, i32 ni, i32 nr, then u16 (qx, qz)[nv] (x = ox + qx / 32, z = oz + qz / 32),
             nr runs of (i32 first vertex, u8 type, u8 angle, u8 hash, u8 year) — a run's vertices go up to the next run's first —,
             u16 idx[ni] (triangles, in drawing order: later triangles lie on top).
  Chunks are tiles of 2000 m (a tile with more than 65 535 vertices continues in another chunk of the same origin).
  Over the part limit (util.PART_LIMIT, 24 MB) the chunks go on in map_ground_1.bytes, map_ground_2.bytes …, each a whole GRD1
  file with the same bounds; Unity reads them in that order until one is missing.
  type: TYPES below; angle: direction of the lot's long side, 0–255 = 0–90°; hash: 0–255 per lot (variety of its yard cells; Unity keeps
  its top 3 bits); year (ybyte): 0 = the map's own year (map_dev), 1 = always, 26..254 = 2000 + v (base scenario), 255 = never. A piece
  is drawn from 2.5 years before its year (earthworks) and its yard from its year; before that the pieces under it show.
"""
import argparse
import collections
import io
import json
import math
import os
import struct
import sys
import time
import zlib

import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points, polylabel, unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import util as U  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
F_GROUND = "Resources/Map/map_ground.bytes"
F_BLOCKS = "Resources/Map/map_blocks.png"
F_PLAN = "Resources/Map/map_plan.png"
F_DEV = "Resources/Map/map_dev.png"
F_WALKS = "Resources/Map/map_walks.json"
F_NATURE = "Resources/Map/map_nature.png"
PICTURE = os.environ.get("ALATAU_GROUND_TYPES", "/mnt/project-files/alatau_stage7/out/_fixtures/w48/ground_types.png")

# ------------------------------------------------------------------ yard types (the shader's switch, AlatauGround.shader)
TYPES = {
    0: "прежний вид (нет данных или земля keep)",
    1: "двор жилого квартала: газон, детские площадки",
    2: "участок школы или детсада: газон, спортплощадка",
    3: "площадь, мощение",
    4: "наземная парковка (только из parking)",
    5: "сад и огород села, участки малоэтажек",
    6: "парк, зелёный буфер",
    7: "двор промышленности и логистики: бетон, доки",
    8: "резерв, поле: степь",
    9: "проезд и разворотная площадка: асфальт",
    10: "общественный участок: мощение и газон",
    11: "инженерный участок: бетон и гравий",
    12: "спортивная площадка",
    13: "детская площадка",
    14: "тротуар проезда",
    15: "земля района без участка: газон",
    16: "участок многоэтажек вокруг домов: мощение и газон",
    17: "аллея парка: мощение (люди ходят, деревьев нет)",
    18: "беговая дорожка вокруг поля школы: резина",
}
HARD = (3, 4, 7, 9, 11, 12, 13, 14, 17, 18)                          # types with no tree anywhere on them (FilmTrees, GroundTypes.HardAt)
LOT_TYPE = {
    "residential_high": 16, "residential_mid": 16, "mixed_centre": 16,
    "residential_low": 5, "village_existing": 5,
    "school": 2, "kindergarten": 2,
    "business": 10, "campus": 10, "college": 10, "university": 10, "medical": 10, "polyclinic": 10, "hospital": 10, "clinic": 10,
    "pharmacy_shop": 10, "police": 10, "fire_station": 10, "culture": 10, "worship": 10, "landmark": 10, "parking": 10,
    "transit": 10, "square": 3, "playground": 13, "sport_ground": 12, "sport": 12, "park": 6, "waterfront": 6,
    "industry": 7, "logistics": 7, "utility": 11, "substation": 11, "reserve": 8,
}
GREEN_TYPE = {"park": 6, "buffer": 6, "boulevard": 6, "sport": 12, "square": 3}
# uses whose ground is made with their buildings: such a lot without a building of the data never gets its yard (plain ground)
NEEDS_BUILDING = {"residential_high", "residential_mid", "mixed_centre", "residential_low", "school", "kindergarten", "business", "campus",
                  "college", "university", "medical", "polyclinic", "hospital", "clinic", "pharmacy_shop", "police", "fire_station", "culture",
                  "worship", "landmark", "industry", "logistics"}
NEVER = 9999                                                        # a year that never comes (the year byte 255)
GAP_CLOSE_M = 300.0                                                 # strips between districts up to twice this wide get the plain lawn
WHOLE_CITY = {"gate", "golden", "green", "growing_w", "growing_e"}  # all of them merged: the old plan outside them is shown as nature
EDGE_PX = 2                                                         # map_dev px round the districts that keep the district's year


def ybyte(y):
    """The year byte of a piece (GRD1 run, 4th byte): 0 = the map's own year (map_dev), 1 = always (2025 or earlier), 26..254 = 2000 + v
    (base scenario; the shader derives the other scenarios with _AlatauDevK, as for map_dev), 255 = never."""
    if y is None:
        return 0
    y = int(y)
    if y >= NEVER:
        return 255
    return 1 if y <= 2025 else min(y - 2000, 254)
# colours of the picture (sRGB), one per type
PIC = {0: (60, 60, 60), 1: (126, 170, 96), 2: (214, 140, 96), 3: (205, 198, 182), 4: (96, 96, 104), 5: (170, 196, 110),
       6: (72, 132, 72), 7: (150, 140, 170), 8: (196, 182, 140), 9: (52, 52, 56), 10: (196, 164, 150), 11: (140, 150, 164),
       12: (190, 92, 70), 13: (230, 190, 60), 14: (232, 228, 218), 15: (150, 176, 128), 16: (176, 150, 120),
       17: (236, 214, 160), 18: (168, 70, 52)}

# ------------------------------------------------------------------ map_blocks (UnityProject/Tools/twin_gen/gen_blocks.py, same numbers)
BW = 4096
RANGE = 64.0
CORRIDOR = dict(highway=11.0 + 2.0, ring=9.0 + 2.0, main=7.5 + 3.5 + 1.5, street=4.0 + 2.4 + 1.2)

# ------------------------------------------------------------------ map_plan palette (UnityProject/Tools/twin_gen/gen_map.py PAL)
PAL = {
    "steppe": (86, 84, 78), "res_low": (198, 186, 150), "res_mid": (205, 178, 124), "res_high": (203, 150, 112), "public": (194, 122, 120),
    "health": (194, 144, 162), "industry": (142, 131, 166), "utility": (130, 140, 154), "transport": (132, 132, 136), "green": (116, 140, 106),
    "park": (100, 134, 94), "road": (218, 214, 206), "reserve": (122, 118, 108), "dark": (60, 58, 54),
}
MAJOR = ("highway", "ring", "main")                                 # classes of the base roads that gen_map.py's plan draws dark
MAJOR_T = ("expressway", "ramp")                                   # profile types drawn dark (a district's arterials stay light streets)


def is_major(e, profiles):
    p = e.get("p")
    if p is not None and 0 <= p < len(profiles):
        return profiles[p].get("t") in MAJOR_T
    return e.get("c") in MAJOR
LOT_PLAN = {
    "residential_high": "res_high", "mixed_centre": "res_high", "residential_mid": "res_mid", "residential_low": "res_low",
    "village_existing": "res_low", "school": "public", "kindergarten": "public", "business": "public", "campus": "public",
    "college": "public", "university": "public", "culture": "public", "worship": "public", "police": "public", "fire_station": "public",
    "landmark": "public", "medical": "health", "polyclinic": "health", "hospital": "health", "clinic": "health", "pharmacy_shop": "public",
    "transit": "transport", "parking": "transport", "square": "road", "playground": "green", "sport_ground": "green", "sport": "green",
    "park": "park", "waterfront": "green", "industry": "industry", "logistics": "industry", "utility": "utility", "substation": "utility",
    "reserve": "reserve",
}


class Log:
    def __init__(self):
        self.lines = []; self.t0 = self.t1 = time.time()

    def __call__(self, s):
        s = f"[{time.time() - self.t0:6.1f} s] {s}"; print(s, flush=True); self.lines.append(s)

    def stage(self, name):
        """A timing line: the seconds since the last stage ended."""
        t = time.time(); self(f"stage {name}: {t - self.t1:.1f} s"); self.t1 = t


def poly_of(p, holes=None):
    g = Polygon(p, holes or [])
    return g if g.is_valid else g.buffer(0)


def lot_angle(g):
    """Direction of the long side of the polygon's smallest rotated rectangle, 0..90° (yard cells and parking rows follow it)."""
    try:
        r = g.minimum_rotated_rectangle
        c = list(r.exterior.coords)
    except Exception:
        return 0.0
    if len(c) < 4:
        return 0.0
    a, b, d = np.array(c[0]), np.array(c[1]), np.array(c[2])
    v = b - a if np.hypot(*(b - a)) >= np.hypot(*(d - b)) else d - b
    return math.degrees(math.atan2(v[1], v[0])) % 90.0


def hash8(s):
    return zlib.crc32(s.encode("utf-8")) & 255


# ================================================================== inputs
def load_district(d, out_root, log):
    folder = os.path.join(out_root, d); D = {"id": d}
    for k in ("network", "blocks", "lots", "features", "driveways", "buildings"):
        p = os.path.join(folder, k + ".json"); D[k] = U.load_json(p) if os.path.exists(p) else None
    spec = None
    for p in (os.path.join(U.SPEC, d + ".json"), os.path.join(folder, "spec.json")):
        if os.path.exists(p):
            spec = U.load_json(p); break
    area = (D["network"] or {}).get("area") or (spec or {}).get("area")
    if not area:
        raise SystemExit(f"{d}: no work area (network.json `area` or spec `area`)")
    D["area"] = Polygon(area).buffer(0)
    if D["lots"] is None:
        raise SystemExit(f"{d}: no lots.json — the ground of a district comes from its lots")
    log(f"{d}: area {D['area'].area / 1e4:.0f} ha; " + ", ".join(f"{k} {'yes' if D[k] is not None else 'MISSING'}"
                                                         for k in ("blocks", "lots", "features", "driveways", "buildings")))
    return D


class Grid:
    """UV of the Resources/Map rasters (city_meta.json terrain: u = u_a·x + u_b, v = v_a·z + v_b; PNG row 0 = north)."""

    def __init__(self, meta):
        self.ua, self.ub, self.va, self.vb = meta["u_a"], meta["u_b"], meta["v_a"], meta["v_b"]

    def centres(self, W, H, i0, i1, j0, j1):
        """World x of columns i0..i1 and z of PNG rows j0..j1 (rows from the top)."""
        xs = ((np.arange(i0, i1) + 0.5) / W - self.ub) / self.ua
        zs = ((1.0 - (np.arange(j0, j1) + 0.5) / H) - self.vb) / self.va
        return xs, zs

    def box(self, W, H, bounds, pad=0):
        x0, z0, x1, z1 = bounds
        i0 = int(math.floor((x0 * self.ua + self.ub) * W)) - pad; i1 = int(math.ceil((x1 * self.ua + self.ub) * W)) + pad
        j0 = int(math.floor((1.0 - (z1 * self.va + self.vb)) * H)) - pad; j1 = int(math.ceil((1.0 - (z0 * self.va + self.vb)) * H)) + pad
        return max(i0, 0), min(i1, W), max(j0, 0), min(j1, H)


def mask_in(geom, xs, zs):
    X, Z = np.meshgrid(xs, zs)
    return shapely.contains_xy(geom, X, Z)


# ================================================================== map_blocks
def corridor_half(e, profiles):
    """Half width of an edge's corridor up to its red line: the street profile (as FilmRoads.Corridor: max(red line / 2, outer edge
    of pavements and verges); one carriageway of a divided road: red line / 2 minus the carriageway's offset from the road axis) or,
    without a profile, the class width of gen_blocks.py."""
    p = e.get("p")
    if p is None or not (0 <= p < len(profiles)):
        return CORRIDOR.get(e["c"], CORRIDOR["street"])
    pr = profiles[p]; lw = float(pr.get("lane_w") or 3.0); ln = pr.get("lanes") or [1, 1]
    sw, vg, bk, pk = (pr.get(k) or [0, 0] for k in ("sidewalk_w", "verge_w", "bike_w", "parking_w"))
    med = float(pr.get("median_w") or 0.0)
    car = (max(0, ln[0]) + max(0, ln[1])) * lw * 0.5 + med * 0.5 + (pk[0] + pk[1]) * 0.5
    side = max(sw[0] + vg[0] + bk[0], sw[1] + vg[1] + bk[1])
    outer = car + side
    red = float(pr.get("red_line_w") or 0.0) * 0.5
    if e.get("k") == 1:                                          # one carriageway of a divided road: its axis is `car` off the road axis
        red = red - car
    return max(red, outer, 1.0)


def blocks_sd(edges, half_of, grid, W, H, win=None):
    """gen_blocks.py, restricted to the pixel window win = (i0, i1, j0, j1) in PNG-row terms (None = the whole map). Returns the
    window of the image (uint8, PNG rows from the top)."""
    ua, ub, va, vb = grid.ua, grid.ub, grid.va, grid.vb
    if win is None:
        win = (0, W, 0, H)
    wi0, wi1, wj0, wj1 = win
    # gen_blocks works with row 0 = south; window rows from the top j → south rows H-1-j
    s0, s1 = H - wj1, H - wj0
    sd = np.full((s1 - s0, wi1 - wi0), RANGE, dtype=np.float32)
    xs = ((np.arange(W) + 0.5) / W - ub) / ua
    zs = ((np.arange(H) + 0.5) / H - vb) / va
    n = 0
    for e in edges:
        half = half_of(e)
        g = np.asarray(e["g"], dtype=np.float64).reshape(-1, 2)
        for a, b in zip(g[:-1], g[1:]):
            r = RANGE + half
            i0, i1 = int(((min(a[0], b[0]) - r) * ua + ub) * W), int(((max(a[0], b[0]) + r) * ua + ub) * W) + 1
            j0, j1 = int(((min(a[1], b[1]) - r) * va + vb) * H), int(((max(a[1], b[1]) + r) * va + vb) * H) + 1
            i0, i1, j0, j1 = max(i0, 0, wi0), min(i1, W, wi1), max(j0, 0, s0), min(j1, H, s1)
            if i0 >= i1 or j0 >= j1:
                continue
            X, Z = np.meshgrid(xs[i0:i1], zs[j0:j1])
            ab = b - a
            t = np.clip(((X - a[0]) * ab[0] + (Z - a[1]) * ab[1]) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
            d = np.hypot(X - (a[0] + ab[0] * t), Z - (a[1] + ab[1] * t)) - half
            np.minimum(sd[j0 - s0:j1 - s0, i0 - wi0:i1 - wi0], d, out=sd[j0 - s0:j1 - s0, i0 - wi0:i1 - wi0])
            n += 1
    return np.clip(np.round(128.0 + 2.0 * sd), 0, 255).astype(np.uint8)[::-1], n


def png_gray(img):
    """The PNG writer of gen_blocks.py (8-bit grey, zlib 6), so a regenerated base is byte-equal to the generator's own file."""
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    H, W = img.shape
    raw = np.concatenate([np.zeros((H, 1), np.uint8), img], axis=1).tobytes()
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
# where the project's own map_blocks.png lies when the twin upload has none (it is not in the upload): the Unity project of a full
# checkout, then the copy of the project on the build machine
BLOCKS_CANDIDATES = (os.path.join(REPO, "UnityProject", "Assets", F_BLOCKS), "/tmp/claude-0/repo/UnityProject/Assets/" + F_BLOCKS)
NATURE_CANDIDATES = (os.path.join(REPO, "UnityProject", "Assets", F_NATURE), "/tmp/claude-0/repo/UnityProject/Assets/" + F_NATURE)


def blocks_base_path(base_dir, blocks_base):
    if blocks_base:
        return blocks_base
    for c in (os.path.join(base_dir, F_BLOCKS), os.environ.get("ALATAU_MAP_BLOCKS") or "") + BLOCKS_CANDIDATES:
        if c and os.path.exists(c):
            return c
    return None


def make_blocks(base_dir, blocks_base, base_roads, roads, area, grid, log, regen=False):
    W = BW; H = int(round(W * grid.ua / grid.va))
    src = blocks_base_path(base_dir, blocks_base)
    if src:
        img = np.asarray(Image.open(src).convert("L")).copy(); how = f"base {src} (outside the areas byte for byte)"
        if img.shape != (H, W):
            raise SystemExit(f"map_blocks base {src} is {img.shape[1]} x {img.shape[0]}, expected {W} x {H}")
    elif regen:
        img, n = blocks_sd(base_roads["edges"], lambda e: CORRIDOR.get(e["c"], CORRIDOR["street"]), grid, W, H)
        how = f"base REGENERATED from the base roads.json ({n:,} segments): NOT the project's file outside the areas (--blocks-regen)"
    else:
        raise SystemExit("ground: no base map_blocks.png (not in the twin upload, the checkout or $ALATAU_MAP_BLOCKS): pass --blocks-base "
                         "<the project's Resources/Map/map_blocks.png>; --blocks-regen rebuilds it from roads.json, which is not byte-equal "
                         "to the project's file outside the areas")
    base_img = img.copy()
    log(f"map_blocks: {how}")
    profiles = roads.get("profiles") or []
    win = grid.box(W, H, area.bounds, pad=2)
    near = box(*area.buffer(RANGE + 60.0).bounds)
    edges = [e for e in roads["edges"] if LineString(np.asarray(e["g"], float).reshape(-1, 2)).intersects(near)]
    new, n = blocks_sd(edges, lambda e: corridor_half(e, profiles), grid, W, H, win)
    i0, i1, j0, j1 = win
    xs, zs = grid.centres(W, H, i0, i1, j0, j1)
    m = mask_in(area, xs, zs)
    sub = img[j0:j1, i0:i1]; sub[m] = new[m]
    outside = np.ones(img.shape, bool); outside[j0:j1, i0:i1] = ~m
    assert np.array_equal(img[outside], base_img[outside]), "map_blocks changed outside the areas"
    nprof = sum(1 for e in edges if e.get("p") is not None)
    log(f"map_blocks: {m.sum():,} px inside the areas from {len(edges):,} merged edges ({nprof} with a street profile, {n:,} segments)")
    return img, int(m.sum())


# ================================================================== map_plan, map_dev
def relief_shade(base_dir, grid, xs, zs):
    """gen_map.py relief shading (×1 ± 0.075 σ, clipped 0.8–1.18) at the pixel centres xs × zs."""
    meta = U.load_json(os.path.join(base_dir, "CityData/city_meta.json"))["terrain"]
    dem = np.fromfile(os.path.join(base_dir, "CityData/terrain_heights.bytes"), np.float32).reshape(meta["ny"], meta["nx"])
    gy, gx = np.gradient(ndimage.gaussian_filter(dem, 2.2), meta["step"])
    az, alt = np.radians(315), np.radians(42); ex = 2.5
    slope = np.arctan(ex * np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    hs = (hs - hs.mean()) / (hs.std() + 1e-6)
    ci = (xs - meta["x0"]) / meta["step"]; ri = (zs - meta["z0"]) / meta["step"]
    RI, CI = np.meshgrid(ri, ci, indexing="ij")
    shade = ndimage.map_coordinates(hs, [RI, CI], order=1, mode="nearest").astype(np.float32)
    return np.clip(1 + 0.075 * shade, 0.8, 1.18)


def water_of(rgb):
    c = rgb.astype(np.float32) / 255.0
    return np.clip((c[..., 2] - c[..., 0] - 0.10) * 8.0, 0, 1) * np.clip((c[..., 2] - c[..., 1] - 0.03) * 25.0, 0, 1)


def paint_lots(lots, xs, zs, value_of, out, skip=None):
    """Writes value_of(lot) at the pixel centres inside each lot (bigger lots first, smaller ones on top); returns a mask of the
    painted pixels. skip(lot) → the lot's pixels are only marked in the returned keep mask."""
    painted = np.zeros(out.shape[:2], bool); keep = np.zeros(out.shape[:2], bool)
    x0, dx = xs[0], xs[1] - xs[0]; z0, dz = zs[0], zs[1] - zs[0]
    for L, g in sorted(lots, key=lambda t: -t[1].area):
        bx0, bz0, bx1, bz1 = g.bounds
        ia, ib = sorted((int(math.floor((bx0 - x0) / dx)), int(math.ceil((bx1 - x0) / dx)) + 1))
        ja, jb = sorted((int(math.floor((bz0 - z0) / dz)), int(math.ceil((bz1 - z0) / dz)) + 1))
        ia, ib, ja, jb = max(ia, 0), min(ib, len(xs)), max(ja, 0), min(jb, len(zs))
        if ia >= ib or ja >= jb:
            continue
        m = mask_in(g, xs[ia:ib], zs[ja:jb])
        if not m.any():
            continue
        if skip is not None and skip(L):
            keep[ja:jb, ia:ib] |= m; continue
        sub = out[ja:jb, ia:ib]; sub[m] = value_of(L)
        painted[ja:jb, ia:ib] |= m
    return painted & ~keep, keep


def make_plan(base_dir, Ds, area, grid, roads, log):
    base = np.asarray(Image.open(os.path.join(base_dir, F_PLAN)).convert("RGB"))
    H, W, _ = base.shape
    i0, i1, j0, j1 = grid.box(W, H, area.bounds, pad=6)
    xs, zs = grid.centres(W, H, i0, i1, j0, j1)
    crop = base[j0:j1, i0:i1].astype(np.float32)
    inside = mask_in(area, xs, zs)
    new = np.empty_like(crop); new[:] = PAL["road"]                 # land of the area outside every block: street corridors
    # corridors of the major roads in the plan's dark tone, as gen_map.py has them (its "dark" class: always there, open land in the shader)
    profiles = roads.get("profiles") or []
    near = box(*area.buffer(200.0).bounds)
    major = [e for e in roads["edges"] if is_major(e, profiles) and LineString(np.asarray(e["g"], float).reshape(-1, 2)).intersects(near)]
    if major:
        msd, _ = blocks_sd(major, lambda e: corridor_half(e, profiles), grid, W, H, (i0, i1, j0, j1))
        new[msd <= 128] = PAL["dark"]
    blocks = [(B, poly_of(B["polygon"], B.get("holes"))) for D in Ds for B in (D["blocks"] or {}).get("blocks") or []]
    paint_lots(blocks, xs, zs, lambda B: PAL["green"] if B["use"] == "utility" else PAL[LOT_PLAN.get(B["use"], "public")], new)   # gaps between lots
    lots = [(L, poly_of(L["polygon"], L.get("holes"))) for D in Ds for L in D["lots"]["lots"]]
    built = {B.get("lot") for D in Ds for B in (D["buildings"] or {}).get("buildings") or [] if B.get("lot")}
    plazas = [({"use": "square"}, poly_of(p["polygon"])) for D in Ds for p in ((D["features"] or {}).get("plazas") or [])]

    def colour(L):                                                 # utility land with nothing on it is the green of a verge (as in map_ground)
        return PAL["green"] if lot_type(L, built) == 15 else PAL[LOT_PLAN.get(L["use"], "public")]
    painted, keep = paint_lots(lots, xs, zs, colour, new, skip=lambda L: L.get("source") == "keep")
    paint_lots(plazas, xs, zs, lambda L: PAL["road"], new)
    water = water_of(crop) > 0.3
    shade = relief_shade(base_dir, grid, xs, zs)
    new = np.clip(new * np.where(water[..., None], 1.0, shade[..., None]), 0, 255)
    repaint = inside & ~water & ~keep
    mixed = np.where(repaint[..., None], new, crop)
    blurred = np.asarray(Image.fromarray(np.round(mixed).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.55))).astype(np.uint8)
    out = base.copy(); sub = out[j0:j1, i0:i1]; sub[repaint] = blurred[repaint]
    log(f"map_plan: {repaint.sum():,} px repainted inside the areas ({painted.sum():,} on lots, {(water & inside).sum():,} water and "
        f"{(keep & inside).sum():,} keep px left as they were)")
    return out, int(repaint.sum())


def dev_value(y):
    """map_dev value of a year: 0 = always (2025 or earlier), year − 2000, 255 = never."""
    return 0 if y <= 2025 else min(int(y) - 2000, 255)


def make_dev(base_dir, Ds, area, grid, roads, gys, log):
    base = np.asarray(Image.open(os.path.join(base_dir, F_DEV)).convert("L"))
    H, W = base.shape
    plan = np.asarray(Image.open(os.path.join(base_dir, F_PLAN)).convert("RGB"))
    i0, i1, j0, j1 = grid.box(W, H, area.bounds, pad=2)
    xs, zs = grid.centres(W, H, i0, i1, j0, j1)
    inside = mask_in(area, xs, zs)
    lots = [((D["id"], L), poly_of(L["polygon"], L.get("holes"))) for D in Ds for L in D["lots"]["lots"]]
    val = np.zeros((j1 - j0, i1 - i0), np.uint8)
    # street corridors with the year of their street, then the lots with the year of their ground (first building; NEVER = 255)
    streets, _ = paint_lots([(y, g) for y, g in street_corridors(roads, area)], xs, zs, dev_value, val)
    painted, keep = paint_lots(lots, xs, zs, lambda dl: dev_value(gys[dl[0]].get(dl[1]["id"], 2025)), val,
                               skip=lambda dl: dl[1].get("source") == "keep")
    painted |= streets & ~keep
    if painted.any():                                                  # the rest of the land: the year of the nearest painted pixel
        _, idx = ndimage.distance_transform_edt(~painted, return_indices=True)
        val = val[idx[0], idx[1]]
    # water of the plan (sampled at the dev pixel centres) keeps its base value
    pw, ph = plan.shape[1], plan.shape[0]
    pi = np.clip(((xs * grid.ua + grid.ub) * pw).astype(int), 0, pw - 1); pj = np.clip(((1.0 - (zs * grid.va + grid.vb)) * ph).astype(int), 0, ph - 1)
    water = water_of(plan[np.ix_(pj, pi)]) > 0.3
    repaint = inside & ~keep & ~water
    out = base.copy(); sub = out[j0:j1, i0:i1]; sub[repaint] = val[repaint]
    # the whole city merged: outside its districts the twin's old plan is gone as well, so its planned years there become never and the
    # ground shows its nature (the old plan's random yards with parked cars showed in the notches of the city's edge, e.g. by the А-3
    # in Golden, right beside the new map); what exists there (always) and the water stay
    if WHOLE_CITY <= {D["id"] for D in Ds}:
        xa, za = grid.centres(W, H, 0, W, 0, H)
        ina = mask_in(area, xa, za)
        # a band of EDGE_PX px round the districts takes the year of the nearest district pixel: the edge of the city is then where its
        # ground pieces end, not the staircase of these 21 m pixels (the shader reads the year of a piece of the map's own year here)
        _, idx = ndimage.distance_transform_edt(~ina, return_indices=True)
        dist = np.hypot(idx[0] - np.arange(H)[:, None], idx[1] - np.arange(W)[None, :])
        band = ~ina & (dist <= EDGE_PX)
        out[band] = out[idx[0][band], idx[1][band]]
        old = ~ina & ~band & (out > dev_value(2025)) & (out < 255)
        out[old] = 255
        log(f"map_dev: the whole city is merged — {int(old.sum()):,} px of the old plan outside the districts set to never (nature)")
    ys = val[repaint]
    yy = ys[(ys > 0) & (ys < 255)]
    log(f"map_dev: {repaint.sum():,} px repainted (always {int((ys == 0).sum())}, never {int((ys == 255).sum())}, years "
        f"{int(yy.min()) + 2000 if yy.size else '-'}–{int(yy.max()) + 2000 if yy.size else '-'}; street corridors by their street's year, "
        f"lots by their first building)")
    return out, int(repaint.sum())


def make_nature(base_dir, nature_base, Ds, area, grid, log):
    """map_nature.png (the ground before development, gen_map.py: steppe with a faint ghost of the OLD plan's streets and zones) with the
    ghost taken out inside the areas: plain steppe with the relief shading (gen_map.py's numbers), so no street grid of the old plan shows
    through the land before its year (item 83). Water and keep land stay as they are; outside the areas the base pixels unchanged.
    The base is not in the twin upload: --nature-base, <base>, $ALATAU_MAP_NATURE, the checkout, the build machine's project copy.
    Returns (image or None, pixels)."""
    src = nature_base
    if not src:
        for c in (os.path.join(base_dir, F_NATURE), os.environ.get("ALATAU_MAP_NATURE") or "") + NATURE_CANDIDATES:
            if c and os.path.exists(c):
                src = c; break
    if not src or not os.path.exists(src):
        log("map_nature: NO BASE (not in the twin upload, the checkout or $ALATAU_MAP_NATURE; pass --nature-base): not written, the "
            "old plan's ghost stays under the new districts")
        return None, 0
    base = np.asarray(Image.open(src).convert("RGB"))
    H, W, _ = base.shape
    i0, i1, j0, j1 = grid.box(W, H, area.bounds, pad=6)
    xs, zs = grid.centres(W, H, i0, i1, j0, j1)
    crop = base[j0:j1, i0:i1].astype(np.float32)
    inside = mask_in(area, xs, zs)
    lots = [(L, poly_of(L["polygon"], L.get("holes"))) for D in Ds for L in D["lots"]["lots"] if L.get("source") == "keep"]
    keep = np.zeros(inside.shape, bool)
    if lots:
        _, keep = paint_lots(lots, xs, zs, lambda L: 0, np.zeros(inside.shape, np.uint8), skip=lambda L: True)
    water = water_of(crop) > 0.3
    shade = relief_shade(base_dir, grid, xs, zs)
    new = np.clip(np.array(PAL["steppe"], np.float32)[None, None, :] * shade[..., None], 0, 255)
    repaint = inside & ~water & ~keep
    mixed = np.where(repaint[..., None], new, crop)
    blurred = np.asarray(Image.fromarray(np.round(mixed).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.55))).astype(np.uint8)
    out = base.copy(); sub = out[j0:j1, i0:i1]; sub[repaint] = blurred[repaint]
    log(f"map_nature: base {src}; {repaint.sum():,} px inside the areas made plain steppe (the old plan's ghost taken out; "
        f"{(water & inside).sum():,} water and {(keep & inside).sum():,} keep px left as they were)")
    return out, int(repaint.sum())


# ================================================================== map_ground.bytes
def lot_type(L, built):
    t = LOT_TYPE.get(L["use"], 10)
    if t == 11 and L["id"] not in built:                              # utility land with nothing on it (motorway land, line corridors): a mown verge
        t = 15
    return t


def ground_years(D):
    """The year (base scenario) the ground of each lot is made: its first building's opening year (a yard comes with its house, item 104);
    a lot of a use that needs a building (NEEDS_BUILDING) and has none in the data: NEVER (plain ground: it is not built); any other lot
    (parks, squares, transit, utility land, existing villages …): the lot's own year."""
    first = {}
    for B in (D["buildings"] or {}).get("buildings") or []:
        if B.get("lot"):
            first[B["lot"]] = min(first.get(B["lot"], NEVER), int((B.get("years") or [NEVER])[0]))
    out = {}
    for L in D["lots"]["lots"]:
        y0 = int((L.get("years") or [2025])[0])
        if L["id"] in first:
            out[L["id"]] = first[L["id"]]
        elif L.get("use") in NEEDS_BUILDING and y0 > 2025 and L.get("source") != "keep":
            out[L["id"]] = NEVER
        else:
            out[L["id"]] = y0
    return out


def street_corridors(roads, area):
    """[(year, polygon)] of the street corridors in the areas (red line of the profile, corridor_half), one per first year: the verge and
    the pavement the ground draws along a street appear with the street (item 83)."""
    profiles = roads.get("profiles") or []
    near = box(*area.buffer(60.0).bounds); by = collections.defaultdict(list)
    for e in roads["edges"]:
        g = np.asarray(e["g"], float).reshape(-1, 2)
        if len(g) < 2:
            continue
        ln = LineString(g)
        if not ln.intersects(near):
            continue
        by[int((e.get("y") or [2025])[0])].append(ln.buffer(corridor_half(e, profiles), quad_segs=4))
    return [(y, unary_union(gs)) for y, gs in sorted(by.items())]


def ground_pieces(Ds, area, roads, gys, log, parks=None, yards=None):
    """(type, angle 0..90, hash, polygon, year byte) in drawing order: later pieces lie on top. Lots of one type and one year in one block
    are drawn as one piece (one direction and one draw of yard cells per block: a village block is one garden, not 40 outlines); a green
    that only repeats its lot's type is left out; drives are their merged centre lines buffered to the carriageway, with flat ends (pads
    close the dead ends). Order: the areas' land, the street corridors (the latest first, so a junction takes its earliest street's year),
    lots, greens, surface parking, the yards' aprons, paths, playgrounds and fields (yard_layout), drives and pads, squares, the parks'
    walks and playgrounds (park_layout); keep lots last, as plain lawn of the map's own year (type 15, byte 0)."""
    P = []; cnt = collections.Counter()

    def add(t, g, ang, h, y, what, tol=0.25):
        if g is None or g.is_empty:
            return
        g = g.intersection(area)
        if tol:
            g = g.simplify(tol)
        if g.is_empty or g.area < 0.5:
            return
        P.append((t, ang, h, g, y)); cnt[what] += 1
    add(15, area, 0.0, 0, 0, "area", tol=0.5)
    # the strips between two districts (their areas follow the twin's boundaries and leave strips up to GAP_CLOSE_M × 2 wide along
    # the А-3 and at the joints: 280 ha in 34 pieces on the stage-7 map): no district draws them, so the ground there painted its old
    # random yards with parked cars right beside the new ones. The same plain lawn of the map's own year; the outer edge of the
    # city stays as it is (a strip is taken only where it touches two districts)
    if len(Ds) > 1:
        closed = area.buffer(GAP_CLOSE_M, join_style="mitre").buffer(-GAP_CLOSE_M, join_style="mitre")
        for gp in getattr(closed.difference(area), "geoms", [closed.difference(area)]):
            if gp.geom_type == "Polygon" and gp.area >= 1.0 and sum(1 for D in Ds if D["area"].distance(gp) < 1.0) >= 2:
                P.append((15, 0.0, 0, gp.simplify(0.5), 0)); cnt["strips between districts"] += 1
    for y, g in sorted(street_corridors(roads, area), key=lambda c: -c[0]):
        add(15, g, 0.0, 0, ybyte(y), "street corridors (by year)", tol=0.5)
    for D in Ds:
        lots = D["lots"]["lots"]; byid = {L["id"]: L for L in lots}; gy = gys[D["id"]]
        built = {B.get("lot") for B in (D["buildings"] or {}).get("buildings") or [] if B.get("lot")}

        def yof(own, lot_id):
            """A thing of a lot appears with its own year, not before the lot's ground (its first building)."""
            y = int(own) if own is not None else 2025
            return max(y, gy.get(lot_id, 0)) if lot_id in gy else y
        groups = collections.OrderedDict()
        for L in sorted(lots, key=lambda L: -float(L.get("area_m2") or 0)):
            groups.setdefault((L.get("block"), lot_type(L, built), ybyte(gy.get(L["id"]))), []).append(L)
        for (blk, t, yb), Ls in groups.items():
            g = unary_union([poly_of(L["polygon"], L.get("holes")) for L in Ls])
            add(t, g, lot_angle(g), hash8(Ls[0]["id"]), yb, f"lot type {t}")
        F = D["features"] or {}
        for G in F.get("greens") or []:
            lot = byid.get(G.get("lot")) or {}
            if G["kind"] == "yard":
                t = 5 if lot.get("use") in ("residential_low", "village_existing") else 1
            elif G["kind"] == "square" and lot.get("use") == "playground":
                t = 13
            else:
                t = GREEN_TYPE.get(G["kind"], 6)
            if lot and lot_type(lot, built) == t:
                cnt["green same as its lot (left out)"] += 1; continue
            g = poly_of(G["polygon"], G.get("holes"))
            add(t, g, lot_angle(g), hash8(G["id"]), ybyte(yof((G.get("years") or [None])[0], G.get("lot"))), "green " + G["kind"])
        for K in F.get("parking") or []:
            if K.get("type") == "surface":
                g = poly_of(K["polygon"])
                add(4, g, lot_angle(g), hash8(K["id"]), ybyte(yof((K.get("years") or [None])[0], K.get("lot"))), "parking surface", tol=0.1)
        # the yards: aprons and paths, playgrounds, sports grounds and tracks, rest squares, the house lawns of the gardens (yard_layout)
        for t, ang, h, g, y, what in (yards or {}).get(D["id"], {}).get("pieces", []):
            add(t, g, ang, h, ybyte(y), what, tol=0.1)
        dw = D["driveways"]
        if dw:
            prof = dw.get("profiles") or {}
            by_w = collections.defaultdict(list)
            for s in dw.get("segments") or []:
                pts = [(p[0], p[1]) for p in s.get("pts") or []]
                if len(pts) < 2:
                    continue
                pr = prof.get(s.get("pid")) or prof.get(s.get("class")) or {}
                ln = pr.get("lanes") or [1, 1]; lw = float(pr.get("lane_w") or 3.0); sw = pr.get("sidewalk_w") or [1.0, 1.0]
                half = max(1.5, (max(0, ln[0]) + max(0, ln[1])) * lw * 0.5)
                by_w[(round(half, 2), round(max(sw), 2), ybyte((s.get("years") or [None])[0]))].append(LineString(pts))
            walk, car = collections.defaultdict(list), collections.defaultdict(list)
            for (half, side, yb), lines in by_w.items():
                merged = shapely.line_merge(unary_union(lines))
                car[yb].append(merged.buffer(half, cap_style="flat", join_style="mitre", mitre_limit=2.0))
                if side > 0:
                    walk[yb].append(merged.buffer(half + side, cap_style="flat", join_style="mitre", mitre_limit=2.0))
            for pad in dw.get("pads") or []:
                car[ybyte((pad.get("years") or [None])[0])].append(poly_of(pad["polygon"]))
            # the latest first: where drives of two years meet, the earlier one lies on top
            for yb in sorted(walk, key=lambda v: -(v if v != 1 else 0)):
                add(14, unary_union(walk[yb]), 0.0, 0, yb, "driveway pavements (by year)")
            for yb in sorted(car, key=lambda v: -(v if v != 1 else 0)):
                add(9, unary_union(car[yb]), 0.0, 0, yb, "driveway carriageways and turnaround pads (by year)")
        # squares over the drives: a fire drive or a pad that crosses a square is in the square's paving
        for Q in F.get("plazas") or []:
            g = poly_of(Q["polygon"], Q.get("holes"))
            add(3, g, lot_angle(g), hash8(Q["id"]), ybyte(yof((Q.get("years") or [None])[0], Q.get("lot"))), "plaza")
        # the parks: walks from the pavements to a round, a loop, playgrounds touching the walks (park_layout)
        for t, ang, h, g, y, what in (parks or {}).get(D["id"], {}).get("pieces", []):
            add(t, g, ang, h, ybyte(y), what, tol=0.1)
        # keep land (an existing place the district keeps as it is, e.g. the Gate District that IconicDistrict draws with the model's own
        # ground): plain lawn of the map's own year on top of everything, so no yard, drive or court of the map shows at the edge of the
        # model's ground (item 82); map_plan and map_dev keep their base pixels there
        kp = [poly_of(L["polygon"], L.get("holes")) for L in lots if L.get("source") == "keep"]
        if kp:
            add(15, unary_union(kp), 0.0, 0, 0, "keep land (plain lawn)", tol=0.1)
    log("ground pieces: " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items())))
    return P


# ================================================================== parks: alleys, a central round, playgrounds, benches (rule)
PARK_MIN_M2 = 1500.0           # smaller park lots are green strips (verges, leftovers between lots): lawn and trees, nothing to walk to
PARK_BIG_M2 = 15000.0          # a park from here (5 m alleys, a round, a loop from 3 ha, playgrounds by size); below it a square
ALLEY_W, LOOP_W = 5.0, 3.5     # main alleys of a park (and their links to the street pavement), the loop
SQUARE_W = 3.5                 # the walks of a square and of a strip of green
ENTRANCE_GAP = 140.0           # metres of park edge between two entrances along the streets (squares: SQUARE_GAP)
SQUARE_GAP = 70.0
STREET_REACH = 45.0            # an entrance faces a pavement at most this far from the park edge (street at grade, pavement on that side)
PLAY_L, PLAY_W = 26.0, 18.0    # a playground of a park: rubber surface with its equipment (GroundProps: one set per 26 m)
BENCH_STEP = 28.0
BENCH_PAD = (3.0, 2.2)         # a bench stands on a paved bay at the edge of its walk (length along the walk, depth)


def _street_kerbs(roads):
    """Pavements a park, a square or a yard may open onto: (line, carriageway half width, pavement width left, right, structure
    `st` or None). No expressways, ramps or roads without pavements; an entrance is only taken where the street is at grade (st code 0)
    and has its pavement on the side of the entrance (_kerb_ok)."""
    profiles = roads.get("profiles") or []
    out = []
    for e in roads["edges"]:
        p = e.get("p")
        if p is not None and 0 <= p < len(profiles):
            pr = profiles[p]
            sw = pr.get("sidewalk_w") or [0, 0]
            if pr.get("t") in MAJOR_T or max(sw) <= 0.0 or max(pr.get("lanes") or [0, 0]) <= 0:
                continue
            lw = float(pr.get("lane_w") or 3.0); ln = pr.get("lanes") or [1, 1]; pk = pr.get("parking_w") or [0, 0]
            car = (max(0, ln[0]) + max(0, ln[1])) * lw * 0.5 + float(pr.get("median_w") or 0.0) * 0.5 + (pk[0] + pk[1]) * 0.5
            if e.get("k") == 1:                                            # one carriageway of a divided road: its own half
                car = (max(0, ln[0]) + max(0, ln[1])) * lw * 0.5
            sl, sr = float(sw[0]), float(sw[1])
        elif e.get("c") in ("street", "main"):
            car = CORRIDOR[e["c"]] - 3.6; sl = sr = 2.0
        else:
            continue
        g = np.asarray(e["g"], float).reshape(-1, 2)
        if len(g) >= 2:
            out.append((LineString(g), car, sl, sr, e.get("st")))
    return out


def _drive_kerbs(D):
    """The pavements of the district's drives (gen_buildings driveways): a square or a park inside a block opens onto them."""
    dw = D.get("driveways") or {}; prof = dw.get("profiles") or {}; out = []
    for s in dw.get("segments") or []:
        pts = [(p[0], p[1]) for p in s.get("pts") or []]
        if len(pts) < 2:
            continue
        pr = prof.get(s.get("pid")) or prof.get(s.get("class")) or {}
        ln = pr.get("lanes") or [1, 1]; lw = float(pr.get("lane_w") or 3.0); sw = pr.get("sidewalk_w") or [1.0, 1.0]
        if max(sw) <= 0:
            continue
        out.append((LineString(pts), max(1.5, (max(0, ln[0]) + max(0, ln[1])) * lw * 0.5), float(sw[0]), float(sw[1]), None))
    return out


def _kerb_ok(k, s, b, q):
    """An entrance at b may join the pavement of kerb k at chainage s (q = b's foot on the axis): the street is at grade there and has
    its pavement on b's side."""
    ln, car, sl, sr, st = k
    if st:
        code = 0
        for i in range(0, len(st) - 2, 3):
            if st[i] - 0.01 <= s <= st[i + 1] + 0.01:
                code = int(st[i + 2]); break
        if code != 0:
            return False
    a = ln.interpolate(max(s - 0.5, 0.0)); c = ln.interpolate(min(s + 0.5, ln.length))
    t = np.array([c.x - a.x, c.y - a.y]); v = np.array([b.x - q.x, b.y - q.y])
    left = t[0] * v[1] - t[1] * v[0] > 0.0
    return (sl if left else sr) > 0.0


def _entrances(P, kerbs, gap):
    """Points of the park edge facing a pavement, `gap` metres apart along the edge, each with its link across the verge to the
    pavement (a LineString from the pavement to the edge, or None when the edge touches the pavement)."""
    ring = P.exterior
    near = [k for k in kerbs if k[0].distance(P) < STREET_REACH + 40.0]
    cands = []
    for d in np.arange(0.0, ring.length, 8.0):
        b = ring.interpolate(d); best = None
        for k in near:
            s = k[0].project(b); q = k[0].interpolate(s)
            dd = q.distance(b) - k[1]
            if dd >= STREET_REACH or (best is not None and dd >= best[0]):
                continue
            if not _kerb_ok(k, s, b, q):
                continue
            best = (dd, k, q)
        if best:
            cands.append((d, b, best))
    ents = []
    if cands:
        start = min(cands, key=lambda c: c[2][0])[0]
        for d, b, best in sorted(cands, key=lambda c: (c[0] - start) % ring.length):
            arc = (d - start) % ring.length
            if all(min(abs(arc - a), ring.length - abs(arc - a)) >= gap for a, _, _ in ents):
                ents.append((arc, b, best))
    out = []
    for arc, b, (dd, k, q) in ents:
        v = np.array([b.x - q.x, b.y - q.y]); nv = np.hypot(*v); link = None
        if nv > 1e-3:
            kp = np.array([q.x, q.y]) + v / nv * (k[1] + 0.5)              # the kerb: the link crosses the verge and the pavement
            if 0.5 < np.hypot(b.x - kp[0], b.y - kp[1]) < STREET_REACH + 10.0:
                link = LineString([(kp[0], kp[1]), (b.x, b.y)])
        out.append((b, link))
    return out


def _along(line, step, start=0.0):
    """Points along a line every 'step' metres with the unit tangent there."""
    L = line.length; d = start
    while d <= L:
        a = line.interpolate(max(d - 0.5, 0.0)); b = line.interpolate(min(d + 0.5, L))
        t = np.array([b.x - a.x, b.y - a.y]); n = np.hypot(*t)
        if n > 1e-6:
            p = line.interpolate(d)
            yield np.array([p.x, p.y]), t / n
        d += step


def _rect(c, t, hl, hw):
    n = np.array([-t[1], t[0]])
    return Polygon([tuple(c + t * hl + n * hw), tuple(c - t * hl + n * hw), tuple(c - t * hl - n * hw), tuple(c + t * hl - n * hw)])


def _yaw(t):
    return round(float(np.degrees(np.arctan2(t[1], t[0]))), 1)


def _ring(g):
    return [round(float(v), 1) for xy in list(g.exterior.coords)[:-1] for v in xy]


def _largest(g):
    if g.is_empty:
        return g
    if g.geom_type in ("MultiPolygon", "GeometryCollection"):
        ps = [p for p in g.geoms if p.geom_type == "Polygon"]
        return max(ps, key=lambda p: p.area) if ps else Polygon()
    return g


def _benches_along(line, half, step, start, region, avoid, bs, pads, hub=None):
    """Benches along a walk every `step` m, sides alternating, each on a paved bay at the walk's edge (BENCH_PAD) facing the walk."""
    k = 0
    for c, t in _along(line, step, start):
        side = 1.0 if k % 2 == 0 else -1.0; k += 1
        nrm = np.array([-t[1], t[0]]) * side
        pad = _rect(c + nrm * (half - 0.2 + BENCH_PAD[1] * 0.5), t, BENCH_PAD[0] * 0.5, BENCH_PAD[1] * 0.5)
        q = c + nrm * (half + 0.9)
        if not pad.within(region) or (avoid is not None and not avoid.is_empty and pad.intersects(avoid)):
            continue
        if hub is not None and Point(q).distance(hub) < 5.0:
            continue
        bs.append((q, -nrm)); pads.append(pad)


def _play_beside(lines, region, avoid_of, hl, hw, prefer, want, apart):
    """Playgrounds touching a walk (0.2 m over its edge, so the walk leads onto the rubber), nearest to `prefer` first, `apart` m apart.
    lines: [(line, half)]; avoid_of(i): what playground i of line i must not touch (the other walks, the round, buildings)."""
    cand = []
    for i, (line, half) in enumerate(lines):
        av = avoid_of(i)
        for c, t in _along(line, 6.0, 8.0):
            for side in (-1.0, 1.0):
                nrm = np.array([-t[1], t[0]]) * side
                cc = c + nrm * (half - 0.2 + hw)
                r = _rect(cc, t, hl, hw)
                if r.within(region) and (av.is_empty or not r.intersects(av)):
                    cand.append((float(np.hypot(*(cc - prefer))), cc, t, r))
    plays = []
    for dist, cc, t, r in sorted(cand, key=lambda c: c[0]):
        if len(plays) >= want:
            break
        if all(np.hypot(*(cc - p[0])) >= apart and not r.intersects(p[2]) for p in plays):
            plays.append((cc, t, r))
    return plays


def park_layout(Ds, roads, gys, log):
    """The parks of the data have only their outline: lay out by rule what a park of an Almaty district has (CONTRACT §8, w48).
    Every park lot of PARK_MIN_M2 or more is equipped:
      park (≥ PARK_BIG_M2): entrances where it faces a pavement at grade (one per ~140 m of edge), each joined by a link across the verge
        to the pavement and by a straight 5 m alley to a paved round in the middle; a 3.5 m loop from 3 ha; playgrounds touching the
        alleys (1 per < 6 ha, 2 per < 12 ha, else 3, 90 m apart); benches every 28 m on paved bays, round the round;
      square: the same with 3.5 m walks, a round of 6 m, entrances 70 m apart (also from the drives' pavements), a playground from 5000 m²;
      strip (too narrow for a round): one 3.5 m walk along it, joined to the pavements at its ends, benches on bays.
    Smaller park lots (verges, leftovers) stay lawn. All of it from the park's own year. Returns {district: {"pieces": [(type, angle,
    hash, geom, year, what)], "walks": [...], "benches": [...], "play": [...]}}."""
    kerbs = _street_kerbs(roads)
    out = {}; tot = collections.Counter()
    for D in Ds:
        R = out.setdefault(D["id"], {"pieces": [], "walks": [], "benches": [], "play": []})
        lots = D["lots"]["lots"]; dk = _drive_kerbs(D); gy = gys[D["id"]]
        bld = collections.defaultdict(list)
        for B in (D["buildings"] or {}).get("buildings") or []:
            fp = B.get("footprint") or B.get("polygon")
            if B.get("lot") and fp and len(fp) >= 3:
                bld[B["lot"]].append(Polygon(fp).buffer(0))
        for L in lots:
            if L.get("use") not in ("park", "waterfront") or L.get("source") == "keep":
                continue
            P = _largest(poly_of(L["polygon"], L.get("holes")).buffer(0))
            if P.is_empty:
                continue
            if P.area < PARK_MIN_M2:
                tot["green strips"] += 1; tot["green strips ha"] += P.area / 1e4; continue
            yrs = L.get("years") or [2030, 2030, 2030, 2030]; yb = gy.get(L["id"], yrs[0]); h = hash8(L["id"])
            obst = unary_union(bld.get(L["id"], [])) if bld.get(L["id"]) else Polygon()
            big = P.area >= PARK_BIG_M2
            aw = ALLEY_W if big else SQUARE_W
            ents = _entrances(P, kerbs + dk, ENTRANCE_GAP if big else SQUARE_GAP)
            hub_r = (12.0 if P.area < 50000.0 else 16.0) if big else 6.0
            core = _largest(P.buffer(-(hub_r + 4.0)))
            walks, pads, bs, plays = [], [], [], []
            if core.is_empty or core.area < 50.0:
                # ---- a strip: one walk along its long axis, joined to the pavements at its ends
                rr = list(P.minimum_rotated_rectangle.exterior.coords)
                e1, e2 = np.array(rr[1]) - np.array(rr[0]), np.array(rr[2]) - np.array(rr[1])
                ax = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2; Lm = np.hypot(*ax); ax = ax / max(Lm, 1e-6)
                cen = np.array(P.minimum_rotated_rectangle.centroid.coords[0])
                cut = LineString([tuple(cen - ax * Lm), tuple(cen + ax * Lm)]).intersection(P.buffer(-SQUARE_W * 0.5 - 0.5))
                parts = [g for g in getattr(cut, "geoms", [cut]) if g.geom_type == "LineString" and not g.is_empty]
                if not parts or max(p.length for p in parts) < 25.0 or (not obst.is_empty and max(parts, key=lambda p: p.length).intersects(obst)):
                    tot["green strips"] += 1; tot["green strips ha"] += P.area / 1e4; continue
                main = max(parts, key=lambda p: p.length)
                links = []
                for end in (Point(main.coords[0]), Point(main.coords[-1])):
                    best = None
                    for k in kerbs + dk:
                        if k[0].distance(end) > STREET_REACH + 30.0:
                            continue
                        s = k[0].project(end); q = k[0].interpolate(s)
                        if not _kerb_ok(k, s, end, q):
                            continue
                        dd = q.distance(end) - k[1]
                        if dd < 30.0 and (best is None or dd < best[0]):
                            best = (dd, k, q)
                    if best:
                        dd, k, q = best; v = np.array([end.x - q.x, end.y - q.y]); nv = np.hypot(*v)
                        if nv > k[1] + 0.6:
                            kp = np.array([q.x, q.y]) + v / nv * (k[1] + 0.5); links.append(LineString([tuple(kp), (end.x, end.y)]))
                walks = [(main, SQUARE_W * 0.5)]
                paved = unary_union([main.buffer(SQUARE_W * 0.5, cap_style="flat")] + [l.buffer(SQUARE_W * 0.5, cap_style="flat") for l in links])
                _benches_along(main, SQUARE_W * 0.5, 24.0, 8.0, P.buffer(-0.3), obst.buffer(1.0) if not obst.is_empty else None, bs, pads)
                R["pieces"].append((17, 0.0, h, unary_union([paved] + pads), yb, "strip walks"))
                pts = []
                if links and Point(links[0].coords[-1]).distance(Point(main.coords[0])) < 0.1:
                    pts += list(links[0].coords)[:-1]
                pts += list(main.coords)
                for l in links:
                    if Point(l.coords[-1]).distance(Point(main.coords[-1])) < 0.1:
                        pts += list(l.coords)[::-1][1:]
                R["walks"].append({"y": yrs, "w": SQUARE_W, "k": 0, "p": [round(float(v), 1) for xy in pts for v in xy]})
                R["benches"].append({"y": yrs, "k": 0, "b": [round(float(v), 1) for q, f in bs for v in (q[0], q[1], float(np.degrees(np.arctan2(f[1], f[0]))))]})
                tot["strips"] += 1; tot["benches"] += len(bs); tot["ha"] += P.area / 1e4
                continue
            hubc = polylabel(core, tolerance=1.0)
            hub = hubc.buffer(hub_r, quad_segs=12)
            if not hub.within(P.buffer(-3.0)) or hub.intersects(obst):
                hub_r = max(5.0, hub_r * 0.6); hub = hubc.buffer(hub_r, quad_segs=12)
            loop = None
            if big and P.area >= 30000.0:
                inner = _largest(P.buffer(-28.0))
                if not inner.is_empty:
                    lp = _largest(inner.buffer(12.0).buffer(-12.0))
                    if not lp.is_empty and lp.area >= 4000.0:
                        loop = LineString(lp.exterior.coords).simplify(1.5)
            # ---- walks: entrance → round (straight, inside the park), else entrance → the loop
            mains, links = [], []
            for b, link in ents:
                line = LineString([(b.x, b.y), (hubc.x, hubc.y)])
                if not line.within(P.buffer(0.5)) or line.intersects(obst):
                    line = None
                    if loop is not None:
                        q = loop.interpolate(loop.project(b))
                        l2 = LineString([(b.x, b.y), (q.x, q.y)])
                        if l2.within(P.buffer(0.5)) and not l2.intersects(obst):
                            line = l2
                if line is None:
                    continue
                mains.append(line)
                if link is not None:
                    links.append(link)
            if not mains:
                # no pavement to open onto (a square inside a block with no drive near): still a walk across it, end to end
                tot["closed squares"] += 1
                if loop is None:
                    rr = list(P.minimum_rotated_rectangle.exterior.coords)
                    e1, e2 = np.array(rr[1]) - np.array(rr[0]), np.array(rr[2]) - np.array(rr[1])
                    ax = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2; ax = ax / max(np.hypot(*ax), 1e-6)
                    c0 = np.array([hubc.x, hubc.y])
                    cut = LineString([tuple(c0 - ax * 1000.0), tuple(c0 + ax * 1000.0)]).intersection(P.buffer(-1.0))
                    parts = [g for g in getattr(cut, "geoms", [cut]) if g.geom_type == "LineString" and not g.is_empty and g.distance(hubc) < 1.0]
                    if parts and not parts[0].intersects(obst):
                        mains.append(parts[0])
            lines = [(m, aw * 0.5) for m in mains] + ([(loop, LOOP_W * 0.5)] if loop is not None else [])
            if not lines:
                tot["green strips"] += 1; tot["green strips ha"] += P.area / 1e4; continue
            walk_geoms = [ln.buffer(hw, quad_segs=4) for ln, hw in lines] + [l.buffer(aw * 0.5, cap_style="flat") for l in links]
            alleys = unary_union(walk_geoms + [hub]).difference(obst) if not obst.is_empty else unary_union(walk_geoms + [hub])
            # ---- playgrounds touching the walks, near the round first
            want = 0 if (not big and P.area < 5000.0) else 1 if P.area < 60000.0 else 2 if P.area < 120000.0 else 3
            pl, pw = (PLAY_L, PLAY_W) if big else (20.0, 14.0)
            inside = P.buffer(-3.0)
            others = [unary_union([g for j, g in enumerate(walk_geoms) if j != i] + [hub.buffer(3.0)] +
                                  ([obst.buffer(4.0)] if not obst.is_empty else [])).buffer(0.6) for i in range(len(lines))]
            if want:
                plays = _play_beside(lines, inside, lambda i: others[i], pl * 0.5, pw * 0.5, np.array([hubc.x, hubc.y]), want, 90.0 if big else 30.0)
            for cc, t, r in plays:
                R["pieces"].append((13, float(np.degrees(np.arctan2(t[1], t[0])) % 90.0), hash8(L["id"] + f"{cc[0]:.0f}"), r, yb, "park playground"))
                R["play"].append({"y": yrs, "k": 0, "a": _yaw(t), "p": _ring(r)})
            # ---- benches on paved bays along the walks every BENCH_STEP m (squares 22 m), inside the round round its rim
            busy = unary_union([p[2].buffer(1.0) for p in plays] + ([obst.buffer(1.0)] if not obst.is_empty else []))
            region = P.buffer(-0.5)
            for i, (ln, hw) in enumerate(lines):
                av = unary_union([busy] + [g for j, g in enumerate(walk_geoms) if j != i]) if len(walk_geoms) > 1 else busy
                _benches_along(ln, hw, BENCH_STEP if big else 22.0, 10.0 if big else 6.0, region, av, bs, pads, hub)
            mouths = unary_union([ln for ln, _ in lines])
            for a in np.arange(0.0, 2 * np.pi, 6.0 / max(hub_r - 1.3, 2.0)):
                q = np.array([hubc.x + np.cos(a) * (hub_r - 1.3), hubc.y + np.sin(a) * (hub_r - 1.3)])
                if hub_r >= 8.0 and Point(q).distance(mouths) > aw * 0.5 + 1.5:
                    bs.append((q, -np.array([np.cos(a), np.sin(a)])))
            R["pieces"].append((17, 0.0, h, unary_union([alleys] + pads), yb, "park walks and round"))
            R["benches"].append({"y": yrs, "k": 0, "b": [round(float(v), 1) for q, f in bs for v in (q[0], q[1], float(np.degrees(np.arctan2(f[1], f[0]))))]})
            # ---- walks for people: link + walk as one line from the kerb to the round, the loop closed
            for m in mains:
                lk = [l for l in links if Point(l.coords[-1]).distance(Point(m.coords[0])) < 0.1]
                pts = (list(lk[0].coords)[:-1] if lk else []) + list(m.coords)
                R["walks"].append({"y": yrs, "w": aw, "k": 0, "p": [round(float(v), 1) for xy in pts for v in xy]})
            if loop is not None:
                R["walks"].append({"y": yrs, "w": LOOP_W, "k": 1, "p": [round(float(v), 1) for xy in loop.coords for v in xy]})
            tot["parks" if big else "squares"] += 1; tot["entrances"] += len(ents); tot["walks"] += len(mains); tot["loops"] += loop is not None
            tot["playgrounds"] += len(plays); tot["benches"] += len(bs); tot["ha"] += P.area / 1e4
        # playground lots of the data get their equipment too
        for L in lots:
            if L.get("use") == "playground" and L.get("source") != "keep":
                g = _largest(poly_of(L["polygon"], L.get("holes")).buffer(0))
                if g.is_empty:
                    continue
                R["play"].append({"y": L.get("years") or [2030] * 4, "k": 2, "a": round(lot_angle(g), 1), "p": _ring(g)})
                tot["playground lots"] += 1
    log("parks: " + ", ".join(f"{k} {v:.1f}" if isinstance(v, float) else f"{k} {v}" for k, v in sorted(tot.items())))
    return out, tot


# ================================================================== yards: what lies round the buildings of a lot (rule)
APRON = 3.0                    # a paved band round every building: its entrances, a dry edge, the walk along the fire band
YARD_PATH_W = 2.5              # yard paths: from a building's apron to the drive or the street pavement, to the playground
YARD_USES = (16, 10, 2, 5)     # lot types laid out: apartment blocks, public and business lots, schools and kindergartens, gardens


class _Near:
    """Geometries of a district in an STRtree: near(g, d) is the union of those whose boxes come within d of g's box, the same ground
    as the union of all of them anywhere within d of g, at the cost of a lot's neighbourhood instead of the whole district."""

    def __init__(self, geoms):
        self.geoms = [g for g in geoms if g is not None and not g.is_empty]
        self.tree = shapely.STRtree(self.geoms) if self.geoms else None

    def near(self, g, d):
        if self.tree is None or g.is_empty:
            return Polygon()
        x0, z0, x1, z1 = g.bounds
        idx = np.sort(self.tree.query(box(x0 - d, z0 - d, x1 + d, z1 + d)))
        return unary_union([self.geoms[i] for i in idx]) if len(idx) else Polygon()


def _place_rect(region, hl, hw, t, prefer, clear=None, clear_d=0.0, step=3.0):
    """A rectangle (half sizes hl along t, hw across) inside `region`, at least clear_d from `clear`, as near `prefer` as the grid of
    `step` m allows; None when nothing fits."""
    if region.is_empty:
        return None
    inner = region.buffer(-min(hl, hw) * 0.95)
    if inner.is_empty:
        return None
    x0, z0, x1, z1 = inner.bounds
    X, Z = np.meshgrid(np.arange(x0, x1 + step, step), np.arange(z0, z1 + step, step))
    ok = shapely.contains_xy(inner, X, Z)
    if not ok.any():
        return None
    xs, zs = X[ok], Z[ok]
    order = np.argsort(np.hypot(xs - prefer[0], zs - prefer[1]))
    shapely.prepare(region)
    for i in order[:400]:
        c = np.array([xs[i], zs[i]]); r = _rect(c, t, hl, hw)
        if not region.contains(r):
            continue
        if clear is not None and not clear.is_empty and r.distance(clear) < clear_d:
            continue
        return c, r
    return None


def _path_to(r, targets, bl, width):
    """A straight yard path from rectangle r to the nearest target (apron, drive pavement): None when they touch or a building is in
    the way."""
    if targets.is_empty:
        return None
    p1, p2 = nearest_points(r, targets)
    d = p1.distance(p2)
    if d < 0.3 or d > 60.0:
        return None
    v = np.array([p2.x - p1.x, p2.y - p1.y]) / d                       # 0.15 m under the playground or field (its edge is drawn exact)
    a = np.array([p1.x, p1.y]) - v * 0.15; b = np.array([p2.x, p2.y]) + v * 0.6
    ln = LineString([tuple(a), tuple(b)])
    if not bl.is_empty and ln.buffer(width * 0.5).intersects(bl):
        return None
    return ln.buffer(width * 0.5, cap_style="flat")


def yard_layout(Ds, roads, gys, log):
    """The lots of the data have buildings and drives but nothing between them: lay out by rule what an Almaty yard has
    (CONTRACT §8, w48). Every lot with buildings of the types YARD_USES:
      apron: a paved band of APRON m round each building, joined by a yard path to the nearest drive pavement or street pavement;
      homes on the lot: a playground (0.7 m² per resident, 20 × 14 to 30 × 20 m) at least 12 m from the walls (8 when no room), a path
        to it, its equipment and benches (GroundProps); two when the lot has more than 350 homes and room;
      business and public lots without homes: a paved rest square of 14 × 8 m at the apron with four benches;
      schools: a sports ground (turf with a running track round it when there is room) and a junior playground; kindergartens: one
        group playground per 60 places (at most 4) and a small sports ground; each 10 m from the walls, each with a path;
      gardens (village and low-rise plots): a lawn of 6 m round each house, the beds behind it.
    The rest of the lot is lawn. Everything from the lot's ground year (its first building). Returns {district: {"pieces": [...],
    "benches": [...], "play": [...]}}."""
    kerbs = _street_kerbs(roads)
    out = {}; tot = collections.Counter()
    for D in Ds:
        R = out.setdefault(D["id"], {"pieces": [], "benches": [], "play": []})
        lots = D["lots"]["lots"]; gy = gys[D["id"]]
        first = {}                                                     # per lot: the year of its first building in each scenario
        for B in (D["buildings"] or {}).get("buildings") or []:
            if B.get("lot"):
                by = B.get("years") or [NEVER] * 4
                first[B["lot"]] = [min(a, int(b)) for a, b in zip(first.get(B["lot"], [NEVER] * 4), by)]
        bl_of = collections.defaultdict(list); homes = collections.Counter()
        for B in (D["buildings"] or {}).get("buildings") or []:
            fp = B.get("footprint") or B.get("polygon")
            if B.get("lot") and fp and len(fp) >= 3:
                bl_of[B["lot"]].append(Polygon(fp).buffer(0)); homes[B["lot"]] += int(B.get("homes") or 0)
        built = set(bl_of)
        # the drives (carriageway and pavements) and pads, surface parking and squares: the yard keeps off them
        drv = []
        dw = D.get("driveways") or {}; prof = dw.get("profiles") or {}
        for s in dw.get("segments") or []:
            pts = [(p[0], p[1]) for p in s.get("pts") or []]
            if len(pts) < 2:
                continue
            pr = prof.get(s.get("pid")) or prof.get(s.get("class")) or {}
            ln = pr.get("lanes") or [1, 1]; lw = float(pr.get("lane_w") or 3.0); sw = pr.get("sidewalk_w") or [1.0, 1.0]
            drv.append(LineString(pts).buffer(max(1.5, (max(0, ln[0]) + max(0, ln[1])) * lw * 0.5) + max(sw), cap_style="flat"))
        drv += [poly_of(p["polygon"]) for p in dw.get("pads") or []]
        F = D["features"] or {}
        oth = ([poly_of(K["polygon"]) for K in F.get("parking") or [] if K.get("type") == "surface"] +
               [poly_of(Q["polygon"], Q.get("holes")) for Q in F.get("plazas") or []])
        stp = [k[0].buffer(k[1] + max(k[2], k[3]) * 0.5) for k in kerbs if k[0].distance(D["area"]) < 50.0]
        # each lot takes only the drives, pavements and squares near it (a union of the whole district per lot made Gate quadratic)
        drives, other, streets = _Near(drv), _Near(oth), _Near(stp)
        for L in lots:
            lid = L["id"]
            if lid not in built or L.get("source") == "keep":
                continue
            t = lot_type(L, built)
            if t not in YARD_USES:
                continue
            P = poly_of(L["polygon"], L.get("holes")).buffer(0)
            if P.is_empty:
                continue
            bl = unary_union(bl_of[lid]).buffer(0)
            yb = gy.get(lid); yrs = L.get("years") or [2030] * 4
            ys = first.get(lid, yrs)                                    # the years the yard's things appear: its first building's
            if t == 5:
                ring = bl.buffer(6.0).intersection(P).difference(bl)
                if not ring.is_empty:
                    R["pieces"].append((15, 0.0, hash8(lid), ring, yb, "house lawns of the gardens")); tot["gardens"] += 1
                continue
            h = hash8(lid); ang = lot_angle(P); a = math.radians(ang); tv = np.array([math.cos(a), math.sin(a)])
            apron = bl.buffer(APRON, join_style="mitre", mitre_limit=2.0).intersection(P).difference(bl)
            paths = []
            # a path reaches at most 60 m from the apron (a mitred apron's box is at most 2 APRON wider than the buildings')
            reach = unary_union([drives.near(bl, 61.0 + 2.0 * APRON), streets.near(bl, 61.0 + 2.0 * APRON)])
            for b in bl_of[lid]:
                p = _path_to(b.buffer(APRON, join_style="mitre", mitre_limit=2.0), reach, bl, YARD_PATH_W)
                if p is not None:
                    paths.append(p)
            paved = unary_union([apron] + paths)
            free = P.difference(bl.buffer(APRON + 0.5)).difference(drives.near(P, 1.5).buffer(1.0)).difference(other.near(P, 1.5).buffer(1.0)).difference(unary_union(paths).buffer(0.8) if paths else Polygon())
            free = free.buffer(-0.01).buffer(0.01)
            prefer = np.array(bl.centroid.coords[0]) if not bl.is_empty else np.array(P.centroid.coords[0])
            targets = unary_union([apron, drives.near(P, 20.5).intersection(P.buffer(20.0))] + paths)
            cap = L.get("capacity") or {}
            nh = int(cap.get("homes") or homes[lid] or 0)
            places = int(cap.get("places") or 0)
            items = []                    # (type, rect, centre, tangent, what, kind of props: 'play' | 'rest' | None)
            if L.get("use") in ("school", "kindergarten"):
                kg = L.get("use") == "kindergarten"
                sizes = [(20.0, 12.0)] if kg else [(44.0, 26.0), (36.0, 20.0), (26.0, 15.0)]
                for (fl, fw) in sizes:
                    track = 0.0 if kg else 3.0
                    got = _place_rect(free, fl * 0.5 + track, fw * 0.5 + track, tv, prefer, bl, 10.0) or _place_rect(free, fl * 0.5 + track, fw * 0.5 + track, tv, prefer, bl, 6.0)
                    if got:
                        c, r = got
                        if track:
                            items.append((18, r, c, tv, "running track", None))
                        items.append((12, _rect(c, tv, fl * 0.5, fw * 0.5), c, tv, "sports ground", None))
                        free = free.difference(r.buffer(2.0)); break
                n = max(1, min(4, int(math.ceil(places / 60.0)))) if kg else 1
                for _ in range(n):
                    got = _place_rect(free, 10.0, 7.0, tv, prefer, bl, 10.0) or _place_rect(free, 10.0, 7.0, tv, prefer, bl, 6.0)
                    if not got:
                        break
                    c, r = got; items.append((13, r, c, tv, "school playground", "play")); free = free.difference(r.buffer(4.0))
            elif nh > 0:
                area = min(max(nh * 2.5 * 0.7, 280.0), 600.0); pl = max(20.0, min(30.0, math.sqrt(area * 1.5))); pw = max(14.0, min(20.0, area / pl))
                for _ in range(2 if nh > 350 else 1):
                    got = _place_rect(free, pl * 0.5, pw * 0.5, tv, prefer, bl, 12.0) or _place_rect(free, pl * 0.5, pw * 0.5, tv, prefer, bl, 8.0)
                    if not got:
                        break
                    c, r = got; items.append((13, r, c, tv, "yard playground", "play")); free = free.difference(r.buffer(6.0))
            elif free.area >= 600.0:
                # a rest square at the apron: 14 × 8 m of paving with four benches
                band = bl.buffer(APRON + 8.6, join_style="mitre", mitre_limit=2.0).difference(bl.buffer(APRON - 0.4, join_style="mitre", mitre_limit=2.0))
                got = _place_rect(free.union(apron).intersection(P.buffer(-0.5)).intersection(band), 7.0, 4.0, tv, prefer, step=1.5)
                if got:
                    c, r = got; items.append((14, r, c, tv, "rest square", "rest"))
            for typ, r, c, t2, what, props in items:
                R["pieces"].append((typ, ang, h, r, yb, what)); tot[what] += 1
                if typ in (13, 12, 18):
                    p = _path_to(r, targets, bl, YARD_PATH_W)
                    if p is not None:
                        paths.append(p); targets = targets.union(p)
                if props == "play":
                    R["play"].append({"y": ys, "k": 1, "a": _yaw(t2), "p": _ring(r)})
                elif props == "rest":
                    n2 = np.array([-t2[1], t2[0]])
                    R["benches"].append({"y": ys, "k": 1, "b": [round(float(v), 1) for s1 in (-1.0, 1.0) for s2 in (-2.5, 2.5)
                                                                for v in (c[0] + t2[0] * s2 + n2[0] * s1 * 2.6, c[1] + t2[1] * s2 + n2[1] * s1 * 2.6,
                                                                          float(np.degrees(np.arctan2(-n2[1] * s1, -n2[0] * s1))))]})
            # the paths and aprons under the playgrounds and fields (drawn first: the rubber and turf lie on them)
            R["pieces"].insert(len(R["pieces"]) - len(items), (14, 0.0, h, unary_union([paved] + paths), yb, "aprons and yard paths"))
            tot["yards"] += 1
    log("yards: " + ", ".join(f"{k} {v}" for k, v in sorted(tot.items())))
    return out, tot




TILE = 2000.0
QS = 32.0


def ground_bytes(pieces, log, limit=None):
    """GRD1: the pieces cut into 2 km tiles, triangulated (constrained Delaunay), quantised to 1/32 m; one run of vertices per piece."""
    tiles = collections.OrderedDict()
    for t, ang, h, g, yb in pieces:
        x0, z0, x1, z1 = g.bounds
        for tx in range(int(math.floor(x0 / TILE)), int(math.floor(x1 / TILE)) + 1):
            for tz in range(int(math.floor(z0 / TILE)), int(math.floor(z1 / TILE)) + 1):
                cell = box(tx * TILE, tz * TILE, (tx + 1) * TILE, (tz + 1) * TILE)
                part = g.intersection(cell) if not cell.contains(g) else g
                if part.is_empty or part.area < 0.5:
                    continue
                tiles.setdefault((tx, tz), []).append((t, ang, h, part, yb))
    limit = limit or U.PART_LIMIT
    chunks = []; ntri = 0; bounds = [1e18, 1e18, -1e18, -1e18]
    for (tx, tz), items in tiles.items():
        ox, oz = tx * TILE, tz * TILE
        V, R, I = [], [], []
        for t, ang, h, part, yb in items:
            tris = shapely.constrained_delaunay_triangles(part)
            tri = [g for g in shapely.get_parts(tris) if g.geom_type == "Polygon" and g.area > 1e-4]
            if not tri:
                continue
            if len(V) + 3 * len(tri) > 65535:                         # this chunk is full: the tile continues in another one
                chunks.append((ox, oz, V, R, I)); V, R, I = [], [], []
            local = {}
            R.append((len(V), int(t), int(round(ang / 90.0 * 255.0)) & 255, int(h), int(yb)))
            for g in tri:
                for x, z in np.asarray(g.exterior.coords)[:3]:
                    q = (min(max(int(round((x - ox) * QS)), 0), 65535), min(max(int(round((z - oz) * QS)), 0), 65535))
                    k = local.get(q)
                    if k is None:
                        k = local[q] = len(V); V.append(q)
                        bounds[0] = min(bounds[0], ox + q[0] / QS); bounds[1] = min(bounds[1], oz + q[1] / QS)
                        bounds[2] = max(bounds[2], ox + q[0] / QS); bounds[3] = max(bounds[3], oz + q[1] / QS)
                    I.append(k)
                ntri += 1
        if V:
            chunks.append((ox, oz, V, R, I))
    def blob(part):
        bb = io.BytesIO()
        bb.write(b"GRD1"); bb.write(struct.pack("<i4fi", 1, *bounds, len(part)))
        for ox, oz, V, R, I in part:
            bb.write(struct.pack("<2f3i", ox, oz, len(V), len(I), len(R)))
            bb.write(np.asarray(V, "<u2").tobytes())
            for first, t, a, h, yb in R:
                bb.write(struct.pack("<i4B", first, t, a, h, yb))
            bb.write(np.asarray(I, "<u2").tobytes())
        return bb.getvalue()
    # one file while it fits in a part (U.PART_LIMIT), else map_ground_1.bytes, _2 … each a whole GRD1 file; the chunks keep their order
    parts, cur, size = [], [], 28
    for c in chunks:
        cs = 20 + len(c[2]) * 4 + len(c[3]) * 8 + len(c[4]) * 2
        if cur and size + cs > limit:
            parts.append(cur); cur, size = [], 28
        cur.append(c); size += cs
    parts.append(cur)
    datas = [blob(p) for p in parts]
    nv = sum(len(c[2]) for c in chunks); nr = sum(len(c[3]) for c in chunks); total = sum(len(d) for d in datas)
    log(f"map_ground: {len(chunks)} chunks, {nr:,} pieces, {nv:,} vertices, {ntri:,} triangles, {total / 1e3:.0f} kB in {len(datas)} file(s)")
    return datas, {"chunks": len(chunks), "pieces": nr, "vertices": nv, "triangles": ntri, "bytes": total, "files": len(datas),
                   "bounds": [round(v, 1) for v in bounds]}


def ground_names(n):
    """Resources paths of the n parts: map_ground.bytes, map_ground_1.bytes, map_ground_2.bytes …"""
    return [F_GROUND if k == 0 else F_GROUND.replace(".bytes", f"_{k}.bytes") for k in range(n)]


def read_ground(data):
    """Decoder of GRD1 (the same reading as GroundTypes.cs): per chunk (xz[n,2] float, attr[n,4] per vertex, idx[m]), and the bounds."""
    assert data[:4] == b"GRD1"
    ver, x0, z0, x1, z1, n = struct.unpack_from("<i4fi", data, 4); o = 4 + 24; out = []
    for _ in range(n):
        ox, oz, nv, ni, nr = struct.unpack_from("<2f3i", data, o); o += 20
        q = np.frombuffer(data, "<u2", nv * 2, o).reshape(-1, 2).astype(np.float64); o += nv * 4
        a = np.zeros((nv, 4), np.uint8); runs = []
        for k in range(nr):
            runs.append(struct.unpack_from("<i4B", data, o)); o += 8
        for k, (first, t, ang, h, w) in enumerate(runs):
            end = runs[k + 1][0] if k + 1 < nr else nv
            a[first:end] = (t, ang, h, w)
        idx = np.frombuffer(data, "<u2", ni, o); o += ni * 2
        out.append((np.c_[ox + q[:, 0] / QS, oz + q[:, 1] / QS], a, idx))
    assert o == len(data), (o, len(data))
    return out, (x0, z0, x1, z1)


# ================================================================== the picture for the orchestrator
def picture(datas, Ds, roads, path, log, mpp=1.0, walks=None):
    chunks = []
    for d in datas:
        ch, (x0, z0, x1, z1) = read_ground(d); chunks += ch
    x0 -= 20; z0 -= 20; x1 += 20; z1 += 20
    W, H = int((x1 - x0) / mpp), int((z1 - z0) / mpp)
    S = 4                                                               # supersampled outlines
    im = Image.new("RGB", (W, H), (34, 36, 40)); dr = ImageDraw.Draw(im)

    def P(xz):
        return [((x - x0) / mpp, (z1 - z) / mpp) for x, z in xz]
    for xz, a, idx in chunks:                                            # the triangles in their order, as the render texture gets them
        for k in range(0, len(idx), 3):
            tri = xz[idx[k:k + 3]]; t = int(a[idx[k], 0])
            dr.polygon(P(tri), fill=PIC.get(t, (255, 0, 255)))
    big = im.resize((W * 2, H * 2), Image.NEAREST); dr = ImageDraw.Draw(big)

    def P2(xz):
        return [((x - x0) / mpp * 2, (z1 - z) / mpp * 2) for x, z in xz]
    for e in roads["edges"]:                                             # merged roads: their axis, thin
        g = np.asarray(e["g"], float).reshape(-1, 2)
        if g[:, 0].max() < x0 or g[:, 0].min() > x1 or g[:, 1].max() < z0 or g[:, 1].min() > z1:
            continue
        dr.line(P2(g), fill=(250, 250, 250) if e.get("t") else (150, 150, 150), width=2)
    for D in Ds:
        for L in D["lots"]["lots"]:
            dr.line(P2(L["polygon"] + [L["polygon"][0]]), fill=(20, 20, 20), width=1)
        for B in (D["buildings"] or {}).get("buildings") or []:
            fp = B.get("footprint")
            if fp and len(fp) >= 3:
                dr.polygon(P2(fp), fill=(245, 245, 240), outline=(0, 0, 0))
    for w in (walks or {}).get("walks", []):                             # walks of the parks: blue lines; benches: red dots
        v = w["p"]; dr.line(P2([(v[i], v[i + 1]) for i in range(0, len(v), 2)]), fill=(40, 110, 230), width=1)
    for b in (walks or {}).get("benches", []):
        v = b["b"]
        for i in range(0, len(v), 3):
            (bx, by), = P2([(v[i], v[i + 1])]); dr.ellipse([bx - 1.5, by - 1.5, bx + 1.5, by + 1.5], fill=(220, 30, 30))
    _ = S
    # legend
    used = collections.Counter()
    for xz, a, idx in chunks:
        used.update(int(v) for v in a[idx[::3], 0])
    rows = [t for t in sorted(TYPES) if used.get(t)]
    lw, lh = 900, 26 * len(rows) + 46
    leg = Image.new("RGB", (lw, lh), (24, 26, 30)); ld = ImageDraw.Draw(leg)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except Exception:
        font = None
    ld.text((12, 10), "Тип земли (map_ground.bytes), белое — здания, чёрное — участки, синее — дорожки парков, красное — скамейки",
            fill=(235, 235, 235), font=font)
    for k, t in enumerate(rows):
        y = 40 + 26 * k
        ld.rectangle([12, y, 40, y + 18], fill=PIC[t]); ld.text((50, y), f"{t:2d}  {TYPES[t]}", fill=(225, 225, 225), font=font)
    big.paste(leg, (16, 16))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    big.save(path, optimize=True)
    log(f"picture: {path} ({big.size[0]} x {big.size[1]} px, {mpp / 2:.1f} m per px)")


# ================================================================== manifest
def update_manifest(run_dir, base_dir, written, info, dropped=()):
    path = os.path.join(run_dir, "manifest.json")
    man = U.load_json(path) if os.path.exists(path) else {"files": {}}       # re-read right before changing it
    man.setdefault("files", {})
    for rel, what in written.items():
        p = os.path.join(run_dir, "Assets", rel); bp = os.path.join(base_dir, rel)
        same = os.path.exists(bp) and os.path.getsize(bp) == os.path.getsize(p) and U.md5(bp) == U.md5(p)
        man["files"][rel] = {"md5": U.md5(p), "size": os.path.getsize(p), "same_as_base": same,
                             "what": "unchanged (byte-equal to the base)" if same else what}
    for rel in dropped:
        man["files"].pop(rel, None)
    man["files"] = dict(sorted(man["files"].items()))
    man["ground"] = info
    U.write_json(path, man)


# ================================================================== main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--districts", required=True)
    ap.add_argument("--out", default=U.OUT)
    ap.add_argument("--base", default=U.TWIN)
    ap.add_argument("--blocks-base", default=None, help="map_blocks.png to keep outside the areas (default: <base>/Resources/Map/map_blocks.png, "
                    "$ALATAU_MAP_BLOCKS, the checkout's UnityProject, the build machine's project copy)")
    ap.add_argument("--blocks-regen", action="store_true", help="no base map_blocks.png anywhere: rebuild it from the base roads.json "
                    "(not byte-equal to the project's file outside the areas)")
    ap.add_argument("--nature-base", default=None, help="map_nature.png to take the old plan's ghost out of inside the areas (default: "
                    "<base>/Resources/Map/map_nature.png, $ALATAU_MAP_NATURE, the checkout's UnityProject, the build machine's project copy)")
    ap.add_argument("--picture", default=None, help="draw the yard types to this PNG (the fixture picture)")
    a = ap.parse_args(argv)
    log = Log()
    dists = [d for d in a.districts.split(",") if d]
    if not dists:
        log("ground: no districts given, nothing written"); return None
    run_dir = os.path.join(a.out, "_merged", a.run); assets = os.path.join(run_dir, "Assets")
    roads_path = os.path.join(assets, U.F_ROADS)
    if not os.path.exists(roads_path):
        raise SystemExit(f"{roads_path} is missing: run merge_districts.py --run {a.run} first")
    Ds = [load_district(d, a.out, log) for d in dists]
    area = unary_union([D["area"] for D in Ds])
    roads = U.load_json(roads_path); base_roads = U.load_json(os.path.join(a.base, U.F_ROADS))
    grid = Grid(U.load_json(os.path.join(a.base, "CityData/city_meta.json"))["terrain"])
    written, dropped = {}, []
    log.stage("load")

    def put(rel, data, what):
        if len(data) > U.PART_LIMIT:
            raise SystemExit(f"ground: REFUSED to write {rel}: {len(data) / 1e6:.2f} MB is over the {U.PART_LIMIT / 1e6:.0f} MB limit")
        size = U.write_bytes(os.path.join(assets, rel), data); written[rel] = what
        log(f"  wrote {rel}: {size / 1e6:.2f} MB")
    # ---- the yard types: the years of the lots' ground, the parks' and the yards' layout, the pieces
    gys = {D["id"]: ground_years(D) for D in Ds}
    nnever = sum(1 for g in gys.values() for y in g.values() if y >= NEVER)
    log(f"ground years: {sum(len(g) for g in gys.values())} lots, {nnever} of a use that needs a building and have none (plain ground)")
    log.stage("ground years")
    parks, ptot = park_layout(Ds, roads, gys, log)
    log.stage("parks")
    yards, ytot = yard_layout(Ds, roads, gys, log)
    log.stage("yards")
    pieces = ground_pieces(Ds, area, roads, gys, log, parks=parks, yards=yards)
    log.stage("ground pieces")
    gdatas, ginfo = ground_bytes(pieces, log)
    names = ground_names(len(gdatas))
    for k, (rel, gd) in enumerate(zip(names, gdatas)):
        put(rel, gd, "NEW: yard type of every piece of ground inside the merged areas (GRD1 triangles; Layers/GroundTypes.cs draws "
            "them into render textures for AlatauGround.shader)" + (f"; part {k + 1} of {len(names)}" if len(names) > 1 else ""))
    for rel in ground_names(64)[len(names):]:                           # parts of an earlier, bigger run of this folder
        stale = os.path.join(assets, rel)
        if os.path.exists(stale):
            os.remove(stale); dropped.append(rel); log(f"  removed the stale {rel}")
    log.stage("map_ground")
    # ---- the parks' walks, benches and playground equipment
    walks = {"v": 1, "by": "tools/map/export/ground.py", "walks": [], "benches": [], "play": []}
    for d in dists:
        for k in ("walks", "benches", "play"):
            walks[k] += parks.get(d, {}).get(k, []) + yards.get(d, {}).get(k, [])
    put(F_WALKS, json.dumps(walks, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "NEW: walks of the parks (people walk them), benches and playground equipment places of the parks and the yards (GroundProps.cs; FilmLife)")
    log.stage("map_walks")
    # ---- map_blocks
    blk, nb = make_blocks(a.base, a.blocks_base, base_roads, roads, area, grid, log, regen=a.blocks_regen)
    put(F_BLOCKS, png_gray(blk), "distance to the road corridors: inside the areas from the merged roads (red lines of the street profiles), "
        "outside the base")
    log.stage("map_blocks")
    # ---- map_plan, map_dev, map_nature: PNG at zlib's default level, as the project's own files are (optimize, i.e. level 9, took 45–55 s
    # a picture to save 7 %)
    plan, npl = make_plan(a.base, Ds, area, grid, roads, log)
    bb = io.BytesIO(); Image.fromarray(plan).save(bb, format="PNG")
    put(F_PLAN, bb.getvalue(), "zoning colours repainted inside the areas from lot use (water and keep land as they were), outside the base")
    log.stage("map_plan")
    dev, nd = make_dev(a.base, Ds, area, grid, roads, gys, log)
    bb = io.BytesIO(); Image.fromarray(dev).save(bb, format="PNG")
    put(F_DEV, bb.getvalue(), "development year repainted inside the areas (street corridors by their street, lots by their first building), "
        "outside the base")
    log.stage("map_dev")
    nat, nn = make_nature(a.base, a.nature_base, Ds, area, grid, log)
    if nat is not None:
        bb = io.BytesIO(); Image.fromarray(nat).save(bb, format="PNG")
        put(F_NATURE, bb.getvalue(), "the ground before development: plain steppe inside the areas (the old plan's ghost taken out), outside the base")
    log.stage("map_nature")
    info = {"by": "tools/map/export/ground.py", "districts": dists, "types": {str(k): v for k, v in TYPES.items()}, "hard": list(HARD), "grd1": ginfo,
            "walks": {k: len(walks[k]) for k in ("walks", "benches", "play")},
            "parks": {k: round(v, 2) if isinstance(v, float) else v for k, v in sorted(ptot.items())},
            "yards": {k: round(v, 2) if isinstance(v, float) else v for k, v in sorted(ytot.items())},
            "never_lots": nnever,
            "px_inside": {"map_blocks": nb, "map_plan": npl, "map_dev": nd, "map_nature": nn}, "log": log.lines}
    update_manifest(run_dir, a.base, written, info, dropped)
    log(f"manifest: {os.path.join(run_dir, 'manifest.json')} (+{len(written)} files, `ground`)")
    log.stage("manifest")
    if a.picture:
        picture(gdatas, Ds, roads, a.picture, log, walks=walks)
        log.stage("picture")
    log(f"ground: {time.time() - log.t0:.1f} s in all")
    return info


if __name__ == "__main__":
    main()
