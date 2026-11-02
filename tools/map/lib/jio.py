"""JSON io: UTF-8, LF; files over 1 MB are written compact (CONTRACT: no indent for files over 1 MB)."""
import json
import os

from . import paths

BIG = 1 << 20


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path, indent=None):
    """Write atomically. Small files get one object per line at the top level (readable diffs), big ones compact."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if indent and len(s) < BIG:
        s = json.dumps(obj, ensure_ascii=False, indent=indent)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
        f.write("\n")
    os.replace(tmp, path)
    return os.path.getsize(path)


def load_spec(district):
    return load_json(paths.spec_path(district))


def load_city():
    return load_json(os.path.join(paths.SPEC, "city.json"))


def load_out(district, name, out=None):
    """OUT/<d>/<name> as a dict, or None when the file is missing."""
    p = os.path.join(out or paths.OUT, district, name)
    return load_json(p) if os.path.isfile(p) else None


def load_geojson(path):
    """(features list) of a GeoJSON FeatureCollection."""
    return load_json(path)["features"]


def r1(v):
    return round(float(v), 1)


def r2(v):
    return round(float(v), 2)
