"""Coordinate frames and data paths of the Alatau map pipeline (level 0).

Frames
------
* WGS84 lon/lat (EPSG:4326): Overture Maps, web sources.
* UTM 43N (EPSG:32643): E, N in metres.
* Unity (the twin's world frame): X = east, Z = north, Y = height (m a.s.l.).
      X = E - 663000,  Z = N - 4830000          (CityDatabase.cs, bim_export.py, roads.json "frame")
* Maket "rel" frame of alatau_plan_utm43n_rel.geojson: x, y in metres relative to its own
  ``origin_utm43n`` = (662482.686, 4837350.528), i.e.
      X = x_rel + (662482.686 - 663000) = x_rel - 517.314
      Z = y_rel + (4837350.528 - 4830000) = y_rel + 7350.528
  (pure translation; proved in build_city.py, see transform_proof.json)

Paths
-----
* ASSETS: the Unity ``Assets`` folder that holds the big LFS files (buildings.csv, layer_*.bytes,
  terrain_heights.bytes, roads.json). The repo clone has no LFS payload, so the read-only laptop
  snapshot is used when the repo copy is missing. Override with ALATAU_ASSETS.
* OUT: where big outputs go (never into the repo). Override with ALATAU_L0_OUT.

Run ``python3 -I frames.py`` for a self-check.
"""
import json
import os

import numpy as np

E0, N0 = 663000.0, 4830000.0
EPSG_UTM = 32643
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SPEC_DIR = os.path.join(REPO, "tools", "map", "spec")

OUT = os.environ.get("ALATAU_L0_OUT", "/mnt/project-files/alatau_stage7/level0/w34")
MAKET_DIR = os.environ.get("ALATAU_MAKET", "/mnt/user-data/uploads/Downloads/alatau_maket")
PLAN_GEOJSON = os.path.join(MAKET_DIR, "alatau_plan_utm43n_rel.geojson")
_ASSET_CANDIDATES = [os.environ.get("ALATAU_ASSETS", ""),
                     os.path.join(REPO, "UnityProject", "Assets"),
                     "/mnt/user-data/uploads/AlatauCity_DigitalTwin/UnityProject/Assets"]

# Overture release and the box the brief asks for
OVERTURE_RELEASE = "2026-10-21.0"
BBOX_LONLAT = (76.55, 43.25, 77.50, 44.05)          # lon0, lat0, lon1, lat1
ATTRIBUTION = "© OpenStreetMap contributors, Overture Maps Foundation"


def asset(rel, required=True):
    """Absolute path of a Unity asset (relative to Assets/): the first candidate root where it really exists
    (an LFS pointer file of < 1 kB does not count for the big binaries)."""
    for root in _ASSET_CANDIDATES:
        if not root:
            continue
        p = os.path.join(root, rel)
        if os.path.isfile(p) and (os.path.getsize(p) > 1024 or rel.endswith(".json")):
            return p
    if required:
        raise FileNotFoundError(f"asset {rel} not found in {[c for c in _ASSET_CANDIDATES if c]}")
    return None


def out(*parts):
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


# ------------------------------------------------------------------ transforms
_tr = {}


def _transformer(inverse=False):
    from pyproj import Transformer
    k = "inv" if inverse else "fwd"
    if k not in _tr:
        _tr[k] = (Transformer.from_crs(EPSG_UTM, 4326, always_xy=True) if inverse
                  else Transformer.from_crs(4326, EPSG_UTM, always_xy=True))
    return _tr[k]


def lonlat_to_utm(lon, lat):
    return _transformer().transform(np.asarray(lon, float), np.asarray(lat, float))


def utm_to_lonlat(e, n):
    return _transformer(True).transform(np.asarray(e, float), np.asarray(n, float))


def utm_to_unity(e, n):
    return np.asarray(e, float) - E0, np.asarray(n, float) - N0


def unity_to_utm(x, z):
    return np.asarray(x, float) + E0, np.asarray(z, float) + N0


def lonlat_to_unity(lon, lat):
    e, n = lonlat_to_utm(lon, lat)
    return utm_to_unity(e, n)


def unity_to_lonlat(x, z):
    return utm_to_lonlat(*unity_to_utm(x, z))


def maket_origin(path=PLAN_GEOJSON):
    with open(path, encoding="utf-8") as f:
        head = f.read(4096)
    i = head.find('"origin_utm43n"')
    if i >= 0:
        j = head.find("[", i)
        k = head.find("]", j)
        return tuple(float(v) for v in head[j + 1:k].split(","))
    return tuple(json.load(open(path, encoding="utf-8"))["origin_utm43n"])


def rel_offset(path=PLAN_GEOJSON):
    """(dx, dz) that takes the maket rel frame into the Unity frame."""
    oe, on = maket_origin(path)
    return oe - E0, on - N0


def rel_to_unity(x, y, path=PLAN_GEOJSON):
    dx, dz = rel_offset(path)
    return np.asarray(x, float) + dx, np.asarray(y, float) + dz


# shapely helpers ----------------------------------------------------------------
def geom_lonlat_to_unity(g):
    import shapely
    def f(c):
        x, z = lonlat_to_unity(c[:, 0], c[:, 1])
        return np.column_stack([x, z])
    return shapely.transform(g, f)


def geom_rel_to_unity(g, path=PLAN_GEOJSON):
    import shapely
    dx, dz = rel_offset(path)
    return shapely.transform(g, lambda c: c + np.array([dx, dz]))


def geom_unity_to_lonlat(g):
    import shapely
    def f(c):
        lon, lat = unity_to_lonlat(c[:, 0], c[:, 1])
        return np.column_stack([lon, lat])
    return shapely.transform(g, f)


def round_geom(g, nd=1):
    import shapely
    return shapely.set_precision(g, 10 ** -nd) if nd is not None else g


# ------------------------------------------------------------------ terrain grid (city_meta.json)
def terrain_meta():
    m = json.load(open(asset("CityData/city_meta.json"), encoding="utf-8"))["terrain"]
    return {k: m[k] for k in ("nx", "ny", "step", "x0", "z0", "u_a", "u_b", "v_a", "v_b", "zmin", "zmax")}


def frame_spec():
    """The frame block written into spec/city.json."""
    t = terrain_meta()
    return {
        "axes": "Unity: X = восток, Z = север, Y = высота над уровнем моря, метры",
        "utm": "EPSG:32643 (WGS 84 / UTM 43N)",
        "formula": "X = E − 663000, Z = N − 4830000 (E, N — UTM 43N); lon/lat → UTM через pyproj (tools/map/geo/frames.py)",
        "maket_rel": "alatau_plan_utm43n_rel.geojson: X = x_rel − 517.314, Z = y_rel + 7350.528 (сдвиг на origin_utm43n = 662482.686, 4837350.528)",
        "terrain_grid": {"file": "UnityProject/Assets/CityData/terrain_heights.bytes", "meta": "UnityProject/Assets/CityData/city_meta.json",
                         "nx": t["nx"], "ny": t["ny"], "step_m": t["step"], "x0": t["x0"], "z0": t["z0"],
                         "x1": t["x0"] + (t["nx"] - 1) * t["step"], "z1": t["z0"] + (t["ny"] - 1) * t["step"],
                         "layout": "float32, строка 0 = юг, столбец 0 = запад, индекс = r·nx + c; высоты двойника = GLO-30 − 2 м у воды (FloodModel.Datum)",
                         "sampler": "tools/map/geo/terrain.py (как CityGround.HeightAt, билинейно)"},
        "map_uv": {"u": f"{t['u_a']:.10e}·x + {t['u_b']:.10f}", "v": f"{t['v_a']:.10e}·z + {t['v_b']:.10f}",
                   "covers": "x −21800…21800, z −30300…31400 (Resources/Map/*.png, master_plan_zoning.png)"},
        "bounds_gen_roads": {"x": [-21800, 21800], "z": [-30300, 31400]},
    }


if __name__ == "__main__":
    # self-check: the Zhetygen aerodrome control point and a round trip
    x, z = lonlat_to_unity(77.1206, 43.7317)
    lon, lat = unity_to_lonlat(x, z)
    print(f"Zhetygen aerodrome KTA 43.7317 N 77.1206 E -> Unity X {float(x):.1f}, Z {float(z):.1f}; back {float(lat):.6f} N {float(lon):.6f} E")
    print("maket origin", maket_origin(), "offset", rel_offset())
    for rel in ("CityData/buildings.csv", "CityData/terrain_heights.bytes", "CityData/layer_infrastructure.bytes",
                "StreamingAssets/twin/roads.json", "CityData/city_meta.json"):
        print(rel, "->", asset(rel, required=False))
    print("OUT", OUT)
