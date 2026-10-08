"""Restyle the master-plan zoning raster into a calm "maket" base map + a pre-development version + a development-year raster.

in : master_plan_zoning.png (4360x6170, ~10 m/px), terrain_heights.bytes (50 m DEM), buildings.csv, city_meta.json
out: map_plan.png   — the city as planned (muted zoning palette, relief shading, clean roads)
     map_nature.png — the same ground before development: steppe with a faint plan "ghost" (roads/parcels barely visible)
     map_dev.png    — 8-bit: year the ground of each pixel is developed (value + 2000; 0 = always as is)
The ground shader blends nature → earthworks → plan by the timeline year (Assets/Shaders/AlatauGround.shader).
Usage: python3 gen_map.py <Assets dir> <out dir> [scale]"""
import sys, json, csv, numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
from scipy.spatial import cKDTree
Image.MAX_IMAGE_PIXELS = None

# reference colours of the source raster → class
REF = {
    "steppe": [(175,167,145),(169,162,140),(182,174,151),(160,154,133),(138,131,114),(150,143,124),(190,182,160),(125,119,104),(200,192,170),(115,110,96),(105,100,88),(95,90,80)],
    "unused": [(209,195,176),(229,223,192),(220,210,190)],
    "res_low": [(254,250,176),(250,240,170)],
    "res_mid": [(255,218,103),(217,166,33),(245,205,95)],
    "res_high": [(253,143,63),(241,117,54)],
    "public": [(240,77,111),(225,60,90)],
    "health": [(240,140,190),(250,170,210)],
    "industry": [(154,131,192),(170,150,210),(140,115,180)],
    "utility": [(178,189,211)],
    "transport": [(166,165,172)],
    "green": [(164,229,141),(156,217,134),(143,197,121)],
    "park": [(103,194,103)],
    "forest": [(79,143,87),(88,152,93)],
    "resort": [(86,212,189)],
    "agri": [(210,233,123),(190,212,111)],
    "water": [(103,160,222),(79,134,199),(48,100,174)],
    "river": [(149,217,252),(125,195,240)],
    "road": [(249,248,245),(235,235,232)],
    "lrt": [(214,40,150),(230,0,126),(200,50,160)],
    "dark": [(30,28,31),(76,71,66),(55,52,50)],
}
REF["reserve"] = [(1,1,1)]   # never matched directly: large light areas split off from "road"
# muted palette for a dark UI with white buildings (sRGB)
PAL = {
    "steppe": (86,84,78), "unused": (100,97,89),
    "res_low": (198,186,150), "res_mid": (205,178,124), "res_high": (203,150,112), "public": (194,122,120), "health": (194,144,162),
    "industry": (142,131,166), "utility": (130,140,154), "transport": (132,132,136),
    "green": (116,140,106), "park": (100,134,94), "forest": (86,114,84), "resort": (102,152,142), "agri": (152,156,110),
    "water": (46,82,112), "river": (72,120,158), "road": (218,214,206), "lrt": (218,214,206), "dark": (60,58,54), "reserve": (122,118,108),
}
NAMES = list(REF.keys())
ALWAYS = {"steppe", "water", "river", "dark"}          # look the same before and after development
ZONES = [n for n in NAMES if n not in ALWAYS]


def classify(img):
    refs, cls = [], []
    for i, n in enumerate(NAMES):
        for c in REF[n]: refs.append(c); cls.append(i)
    refs = np.array(refs, np.float32); cls = np.array(cls, np.int16)
    H, W, _ = img.shape; out = np.zeros((H, W), np.int16)
    for r0 in range(0, H, 32):
        blk = img[r0:r0 + 32].astype(np.float32)
        d = ((blk[:, :, None, :] - refs[None, None]) ** 2).sum(-1)
        out[r0:r0 + 32] = cls[d.argmin(-1)]
    return out


def mode_filter(lab, size, n):
    """majority filter over class labels (removes anti-aliasing speckle and hatch patterns)"""
    best = np.zeros(lab.shape, np.float32); res = lab.copy()
    for k in range(n):
        f = ndimage.uniform_filter((lab == k).astype(np.float32), size)
        m = f > best; best[m] = f[m]; res[m] = k
    return res


def main(assets, outdir, scale=1.0):
    meta = json.load(open(f"{assets}/CityData/city_meta.json"))["terrain"]
    src = Image.open(f"{assets}/Textures/master_plan_zoning.png").convert("RGB")
    if scale != 1.0: src = src.resize((int(src.width * scale), int(src.height * scale)), Image.LANCZOS)
    img = np.asarray(src); H, W, _ = img.shape
    print("classify", W, H)
    lab = classify(img)
    k = NAMES.index
    # hatch in forest: light-green strokes inside forest become forest
    fr = ndimage.uniform_filter((lab == k("forest")).astype(np.float32), max(3, int(9 * scale)))
    lab[(fr > 0.3) & np.isin(lab, [k("green"), k("park"), k("agri")])] = k("forest")
    # keep thin roads / lines, smooth the rest
    # large light areas are reserve / unused land, not roads: keep only thin white features as roads
    rd = lab == k("road"); big = ndimage.binary_opening(rd, structure=np.ones((max(3, int(9 * scale)),) * 2))
    big = ndimage.binary_dilation(big, iterations=max(1, int(2 * scale))) & rd
    lab[big] = k("reserve")
    thin = np.isin(lab, [k("road"), k("dark"), k("lrt"), k("river")])
    sm = mode_filter(lab, max(3, int(5 * scale) | 1), len(NAMES)); lab = np.where(thin, lab, sm)

    # world coordinates of pixel centres
    u = (np.arange(W) + 0.5) / W; v = 1 - (np.arange(H) + 0.5) / H
    X = (u - meta["u_b"]) / meta["u_a"]; Z = (v - meta["v_b"]) / meta["v_a"]
    # relief shading from the DEM
    dem = np.fromfile(f"{assets}/CityData/terrain_heights.bytes", np.float32).reshape(meta["ny"], meta["nx"])
    gy, gx = np.gradient(ndimage.gaussian_filter(dem, 2.2), meta["step"])
    az, alt = np.radians(315), np.radians(42); ex = 2.5
    slope = np.arctan(ex * np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    hs = (hs - hs.mean()) / (hs.std() + 1e-6)
    ci = (X - meta["x0"]) / meta["step"]; ri = (Z - meta["z0"]) / meta["step"]
    RI, CI = np.meshgrid(ri, ci, indexing="ij")
    shade = ndimage.map_coordinates(hs, [RI, CI], order=1, mode="nearest").astype(np.float32)
    shade = np.clip(1 + 0.075 * shade, 0.8, 1.18)

    pal = np.array([PAL[n] for n in NAMES], np.float32)
    plan = pal[lab]
    base = np.array(PAL["steppe"], np.float32)
    # nature: zones fade to steppe with a faint ghost of the plan; streets as a light trace
    ghost = np.full(len(NAMES), 0.14, np.float32)
    for n in ALWAYS: ghost[k(n)] = 1.0
    ghost[k("road")] = ghost[k("lrt")] = 0.22; ghost[k("forest")] = 0.25; ghost[k("park")] = 0.18; ghost[k("green")] = 0.12
    g = ghost[lab][..., None]
    nature = base * (1 - g) + plan * g
    # relief on everything; water stays flat
    flat = np.isin(lab, [k("water"), k("river")])[..., None]
    sh = np.where(flat, 1.0, shade[..., None])
    plan = np.clip(plan * sh, 0, 255); nature = np.clip(nature * sh, 0, 255)

    def save(a, name):
        im = Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.55 * max(scale, 0.5)))
        im.save(f"{outdir}/{name}", optimize=True); print("saved", name, im.size)
    save(plan, "map_plan.png"); save(nature, "map_nature.png")

    # development year: nearest planned buildings (base scenario years)
    B = [r for r in csv.DictReader(open(f"{assets}/CityData/buildings.csv", encoding="utf-8")) if r["source"] != "existing_osm" and 2025 < int(r["year"]) <= 2050 and r["kind"] != "solar"]
    xy = np.array([[float(r["x"]), float(r["z"])] for r in B]); yr = np.array([int(r["year"]) for r in B])
    sol = [r for r in csv.DictReader(open(f"{assets}/CityData/buildings.csv", encoding="utf-8")) if r["kind"] == "solar" and 2025 < int(r["year"]) <= 2050]
    tree = cKDTree(xy)
    f = 4; h2, w2 = H // f, W // f
    Xs = X[f // 2::f][:w2]; Zs = Z[f // 2::f][:h2]
    PX, PZ = np.meshgrid(Xs, Zs)
    pts = np.c_[PX.ravel(), PZ.ravel()]
    d, ii = tree.query(pts, k=6, distance_upper_bound=320)
    yy = np.where(np.isfinite(d), yr[np.minimum(ii, len(yr) - 1)], 9999).min(1).astype(np.float32)
    d2, i2 = tree.query(pts, k=1, distance_upper_bound=1400)
    far = np.where(np.isfinite(d2), yr[np.minimum(i2, len(yr) - 1)] + 2, 2042)
    dev = np.where(yy < 9999, yy, far).reshape(h2, w2)
    if sol:
        st = cKDTree(np.array([[float(r["x"]), float(r["z"])] for r in sol])); sy = np.array([int(r["year"]) for r in sol])
        ds, js = st.query(pts, k=1, distance_upper_bound=200)
        sdev = np.where(np.isfinite(ds), sy[np.minimum(js, len(sy) - 1)], 9999).reshape(h2, w2)
        dev = np.minimum(dev, sdev)
    labs = lab[f // 2::f, f // 2::f][:h2, :w2]
    dev = np.where(np.isin(labs, [k(n) for n in ALWAYS]), 2000, dev)
    dev = ndimage.median_filter(dev, 3)
    Image.fromarray(np.clip(dev - 2000, 0, 255).astype(np.uint8)).save(f"{outdir}/map_dev.png")
    print("saved map_dev.png", w2, h2, "years", np.unique(dev)[:5], "...")
    return lab


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 1.0)
