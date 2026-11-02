"""Loader for the level-0 layer files (GeoJSON in the Unity frame) written by fetch_overture.py and build_city.py.

    import layers
    geoms, props = layers.load("roads")            # OUT/osm/roads.geojson  → shapely geometries (Unity X/Z) + property dicts
    geoms, props = layers.load("derived/trunk_v0")  # OUT/derived/trunk_v0.geojson
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import frames  # noqa: E402

_cache = {}


def path(name):
    if name.endswith(".geojson"):
        name = name[:-8]
    sub = name if "/" in name else "osm/" + name
    return os.path.join(frames.OUT, sub + ".geojson")


def load(name, cache=True):
    from shapely.geometry import shape
    p = path(name)
    if cache and p in _cache:
        return _cache[p]
    with open(p, encoding="utf-8") as f:
        fc = json.load(f)
    geoms = np.array([shape(ft["geometry"]) for ft in fc["features"]], dtype=object)
    props = [ft["properties"] for ft in fc["features"]]
    if cache:
        _cache[p] = (geoms, props)
    return geoms, props


def write(name, geoms, props, meta=None, nd=1):
    """Write a FeatureCollection (Unity frame) to OUT/<name>.geojson, one feature per line."""
    import shapely
    p = os.path.join(frames.OUT, name + ".geojson")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    geoms = np.asarray(geoms, dtype=object)
    gj = shapely.to_geojson(shapely.transform(geoms, lambda c: np.round(c, nd)))
    head = {"type": "FeatureCollection", "name": os.path.basename(name),
            "crs": "Unity twin frame: X = E − 663000, Z = N − 4830000 (UTM 43N, EPSG:32643), metres", **(meta or {})}
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False)[:-1] + ',"features":[\n')
        for i, (g, pr) in enumerate(zip(gj, props)):
            f.write(("" if i == 0 else ",\n") + '{"type":"Feature","properties":' +
                    json.dumps(pr, ensure_ascii=False, separators=(",", ":")) + ',"geometry":' + g + "}")
        f.write("\n]}\n")
    os.replace(tmp, p)
    return p, os.path.getsize(p)
