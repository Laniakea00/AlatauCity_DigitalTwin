"""Helpers of the Unity export (w45): readers and writers of the twin's binary and json formats, terrain, class mapping.

Formats (research/code_map.md §1–2):
  AQL1  layer_*.bytes: 'AQL1', i32 count, per object: u16 nameLen, name utf8, u8 kind, i32 nv, i32 nt, f32 V[nv*3], u32 T[nt*3],
        u8 col[nt], u16 year[nt], i32 bid[nt]
  ABB1  bid_bounds.bytes: 'ABB1', i32 n, f32[n*4] (x0, z0, x1, z1) per bid
  HID1  hide_extra.bytes: 'HID1', i32 n, n × (i32 bid, u32 code)
"""
import csv
import hashlib
import io
import json
import math
import os
import struct

import numpy as np

TWIN = os.environ.get("ALATAU_TWIN", "/mnt/user-data/uploads/AlatauCity_DigitalTwin/UnityProject/Assets")
OUT = os.environ.get("ALATAU_OUT", "/mnt/project-files/alatau_stage7/out")
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
SPEC = os.path.join(REPO, "tools", "map", "spec")
TWIN_GEN = os.path.join(REPO, "UnityProject", "Tools", "twin_gen")

# the Unity files merge writes (paths relative to Assets/)
F_ROADS = "StreamingAssets/twin/roads.json"
F_FILM = "Resources/Landmarks/film_roads.json"
F_CSV = "CityData/buildings.csv"
F_AQL = "CityData/layer_buildings.bytes"
F_BOUNDS = "Resources/Landmarks/bid_bounds.bytes"
F_HIDE = "Resources/Landmarks/hide_extra.bytes"
F_ORDER = "Resources/Landmarks/map_order.json"
F_LRT = "Resources/Landmarks/lrt_routes.json"
F_NOPLANT = "Resources/Landmarks/noplant.json"
F_PARKING = "Resources/Landmarks/parking.json"
F_DISTRICTS = "Resources/Landmarks/districts.json"
F_SOLAR = "Resources/Landmarks/solar.json"
F_RAIL = "Resources/Landmarks/rail.json"
F_NORMS = "StreamingAssets/twin/norms_social.json"
TWIN_JSON = ["networks", "loads", "construction", "finance", "traffic", "scenarios", "risk"]

# building numbers (bid): the per-building lookups of Unity are 256 × 512 texels (BidTable.cs, AlatauLit tuv), so bids are 0 … 131 071.
# The binary layers carry the bid as i32 (AQL1, HID1) or as the index of an ABB1 entry: the table is the only limit.
BID_LIMIT = 256 * 512

# ------------------------------------------------------------------ road classes
FAST = {"expressway"}
MAIN = {"arterial_road_regulated", "arterial_continuous", "arterial_regulated", "district_transport", "district_pedestrian"}
NO_CARS = {"pedestrian_street", "bike_path"}
DRIVES = {"driveway_main", "driveway_secondary"}       # drives to buildings and fire lanes (driveways.json): access only, never a route


def carless(t, prof=None):
    """No cars by design: a pedestrian street, a bike path, or a street profile with no lanes (a boulevard's green strip)."""
    return t in NO_CARS or (prof is not None and t is not None and sum(int(v) for v in (prof.get("lanes") or [1, 1])) <= 0)


# structure kinds along a segment → code in roads.json `st` (CONTRACT §6)
ST_CODE = {"ground": 0, "embankment": 1, "cut": 2, "bridge": 3, "overpass": 4, "tunnel": 5}


def old_class(t, name="", street=""):
    """The four classes every current reader knows (CONTRACT §6): expressway → highway, BAKAD → ring, arterial_* and district_* → main,
    everything else → street."""
    tag = (str(name) + " " + str(street)).lower()
    if "бакад" in tag or "bakad" in tag:
        return "ring"
    if t in FAST:
        return "highway"
    if t in MAIN:
        return "main"
    return "street"


# ------------------------------------------------------------------ io
def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return len(data)


def write_json(path, obj):
    return write_bytes(path, dumps(obj).encode("utf-8"))


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_aql(path):
    f = open(path, "rb").read()
    assert f[:4] == b"AQL1", path
    n = struct.unpack_from("<i", f, 4)[0]; o = 8; out = []
    for _ in range(n):
        L = struct.unpack_from("<H", f, o)[0]; o += 2; name = f[o:o + L].decode("utf-8"); o += L
        kind = f[o]; o += 1; nv, nt = struct.unpack_from("<ii", f, o); o += 8
        V = np.frombuffer(f, np.float32, nv * 3, o).reshape(-1, 3); o += nv * 12
        T = np.frombuffer(f, np.uint32, nt * 3, o).reshape(-1, 3); o += nt * 12
        col = np.frombuffer(f, np.uint8, nt, o); o += nt
        yr = np.frombuffer(f, np.uint16, nt, o); o += nt * 2
        bid = np.frombuffer(f, np.int32, nt, o); o += nt * 4
        out.append([name, kind, V, T, col, yr, bid])
    assert o == len(f), (path, o, len(f))
    return out


def aql_bytes(objs):
    bb = io.BytesIO(); bb.write(b"AQL1"); bb.write(struct.pack("<i", len(objs)))
    for name, kind, V, T, col, yr, bid in objs:
        nb = name.encode("utf-8"); bb.write(struct.pack("<H", len(nb))); bb.write(nb); bb.write(struct.pack("<B", kind))
        bb.write(struct.pack("<ii", len(V), len(T)))
        bb.write(np.asarray(V, "<f4").tobytes()); bb.write(np.asarray(T, "<u4").tobytes())
        bb.write(np.asarray(col, np.uint8).tobytes()); bb.write(np.asarray(yr, "<u2").tobytes()); bb.write(np.asarray(bid, "<i4").tobytes())
    return bb.getvalue()


# ------------------------------------------------------------------ the buildings layer in parts (the laptop file channel takes ≤ 25 MB a file)
PART_LIMIT = 24_000_000          # bytes: no file the merge writes may be larger (merge_districts.put refuses it)


def part_path(path, k):
    """Part k of a layer file: k = 0 is the file itself (layer_buildings.bytes), then layer_buildings_1.bytes, _2 …"""
    if k == 0:
        return path
    root, ext = os.path.splitext(path)
    return f"{root}_{k}{ext}"


def aql_part_paths(path):
    """The parts of a layer that exist: the file itself and every consecutive _1, _2 … after it (old data: just the file)."""
    out = [path] if os.path.exists(path) else []
    k = 1
    while out and os.path.exists(part_path(path, k)):
        out.append(part_path(path, k)); k += 1
    return out


def combine_aql(objs):
    """Objects of the same name (pieces of one chunk written to several parts) joined into one, in order of first appearance — what
    the Unity builder sees (AlatauCityBuilder.ReadLayer)."""
    order, by = [], {}
    for o in objs:
        if o[0] not in by:
            by[o[0]] = []; order.append(o[0])
        by[o[0]].append(o)
    out = []
    for name in order:
        ps = by[name]
        if len(ps) == 1:
            out.append(list(ps[0])); continue
        Vs, Ts, nv = [], [], 0
        for p in ps:
            Vs.append(p[2]); Ts.append(np.asarray(p[3], np.int64) + nv); nv += len(p[2])
        out.append([name, ps[0][1], np.concatenate(Vs), np.concatenate(Ts).astype(np.uint32), np.concatenate([p[4] for p in ps]),
                    np.concatenate([p[5] for p in ps]), np.concatenate([p[6] for p in ps])])
    return out


def read_aql_parts(path):
    """A layer as one object list, whatever the number of parts it is stored in."""
    objs = []
    for p in aql_part_paths(path):
        objs += read_aql(p)
    return combine_aql(objs)


def _obj_bytes(name, nv, nt):
    return 2 + len(name.encode("utf-8")) + 1 + 8 + nv * 12 + nt * (12 + 1 + 2 + 4)


def split_aql(objs, limit=PART_LIMIT):
    """Objects → parts (lists of objects), each written part ≤ limit bytes. A chunk goes whole into the current part, or whole into a
    new one; only a chunk larger than a whole part is cut, into pieces of whole buildings (a bid never spans two parts; each piece keeps
    its triangles in order and the vertices they use), so combine_aql of the parts gives the same triangles (in the same order unless a
    chunk had to be cut)."""
    parts, size = [[]], 8

    def new_part():
        nonlocal size
        parts.append([]); size = 8
    for o in objs:
        name, kind, V, T, col, yr, bid = o
        s = _obj_bytes(name, len(V), len(T))
        if size + s <= limit:
            parts[-1].append(o); size += s; continue
        if 8 + s <= limit:
            new_part(); parts[-1].append(o); size += s; continue
        # a chunk larger than a part: cut into pieces of whole buildings (in order of their first triangle; each piece keeps its
        # triangles in their order)
        ub, first, inv = np.unique(bid, return_index=True, return_inverse=True)
        ntb = np.bincount(inv, minlength=len(ub))
        pv = np.unique(np.stack([np.repeat(inv, 3), np.asarray(T, np.int64).ravel()], 1), axis=0)
        nvb = np.bincount(pv[:, 0], minlength=len(ub))
        seq = np.argsort(first, kind="stable"); i = 0
        while i < len(seq):
            j, nv_, nt_ = i, 0, 0
            while j < len(seq) and size + _obj_bytes(name, nv_ + nvb[seq[j]], nt_ + ntb[seq[j]]) <= limit:
                nv_ += nvb[seq[j]]; nt_ += ntb[seq[j]]; j += 1
            if j == i:
                if parts[-1]:
                    new_part(); continue
                raise SystemExit(f"split_aql: building {int(ub[seq[i]])} of '{name}' is larger than a {limit / 1e6:.0f} MB part")
            m = np.isin(inv, seq[i:j]); Tp = T[m]; used = np.unique(Tp); remap = np.full(len(V), -1, np.int64); remap[used] = np.arange(len(used))
            parts[-1].append([name, kind, V[used], remap[Tp].astype(np.uint32), col[m], yr[m], bid[m]])
            size += _obj_bytes(name, len(used), int(m.sum())); i = j
            if i < len(seq):
                new_part()
    return [p for p in parts if p]


def read_bounds(path):
    f = open(path, "rb").read(); assert f[:4] == b"ABB1"; n = struct.unpack_from("<i", f, 4)[0]
    return np.frombuffer(f, "<f4", n * 4, 8).reshape(n, 4).copy()


def bounds_bytes(B):
    return b"ABB1" + struct.pack("<i", len(B)) + np.asarray(B, "<f4").tobytes()


def read_hide(path):
    f = open(path, "rb").read(); assert f[:4] == b"HID1"; n = struct.unpack_from("<i", f, 4)[0]
    return [struct.unpack_from("<iI", f, 8 + 8 * i) for i in range(n)]


def hide_bytes(pairs):
    return b"HID1" + struct.pack("<i", len(pairs)) + b"".join(struct.pack("<iI", b, c) for b, c in pairs)


CSV_COLS = ["bid", "id", "district", "kind", "use", "source", "year", "floors", "height_m", "gfa_m2", "parcel", "x", "z", "ground_m", "easting", "northing"]


def read_csv_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        return list(rd), rd.fieldnames


def csv_bytes(rows, cols):
    s = io.StringIO()
    w = csv.DictWriter(s, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    return s.getvalue().encode("utf-8")


# ------------------------------------------------------------------ terrain (CityGround.HeightAt)
class Terrain:
    def __init__(self, assets=TWIN):
        m = load_json(os.path.join(assets, "CityData/city_meta.json"))["terrain"]
        self.nx, self.ny, self.step, self.x0, self.z0 = int(m["nx"]), int(m["ny"]), float(m["step"]), float(m["x0"]), float(m["z0"])
        h = np.fromfile(os.path.join(assets, "CityData/terrain_heights.bytes"), dtype="<f4")
        self.h = h[: self.nx * self.ny].reshape(self.ny, self.nx).astype(np.float64)

    def height(self, x, z):
        x = np.asarray(x, float); z = np.asarray(z, float)
        c = np.clip((x - self.x0) / self.step, 0, self.nx - 1.001); r = np.clip((z - self.z0) / self.step, 0, self.ny - 1.001)
        c0 = c.astype(int); r0 = r.astype(int); a = c - c0; b = r - r0; h = self.h
        v = h[r0, c0] * (1 - a) * (1 - b) + h[r0, c0 + 1] * a * (1 - b) + h[r0 + 1, c0] * (1 - a) * b + h[r0 + 1, c0 + 1] * a * b
        return float(v) if v.ndim == 0 else v


# ------------------------------------------------------------------ geometry
def polyline_len(P):
    P = np.asarray(P, float)
    return float(np.sum(np.hypot(*(P[1:, :2] - P[:-1, :2]).T))) if len(P) > 1 else 0.0


def chain(P):
    """Metres along a polyline at each point."""
    P = np.asarray(P, float)
    d = np.hypot(*(P[1:, :2] - P[:-1, :2]).T) if len(P) > 1 else np.zeros(0)
    return np.concatenate([[0.0], np.cumsum(d)])


def flat(P, nd=1):
    return [round(float(v), nd) for p in P for v in p[:2]]


def r1(v):
    return float(round(float(v), 1))


def profile_dims(p):
    """Half widths of a profile (network.json profiles entry): carriageway (kerb to kerb / 2), to the outer edge of the sidewalks."""
    lanes = p.get("lanes") or [1, 1]
    lw = float(p.get("lane_w") or 3.0)
    car = (sum(lanes) * lw + float(p.get("median_w") or 0) + sum(p.get("parking_w") or [0, 0])) / 2.0
    side = max(float(a) + float(b) + float(c) for a, b, c in zip(p.get("sidewalk_w") or [0, 0], p.get("verge_w") or [0, 0], p.get("bike_w") or [0, 0]))
    return car, car + side


def _district_key(keys, d):
    """The city.json district key a district id belongs to (gate_trial* → gate; the longest key that prefixes it)."""
    for k in sorted(keys, key=len, reverse=True):
        if d == k or d.startswith(k + "_") or d.startswith(k):
            return k
    return None


def district_range(city, d):
    """Bid range of a district from city.json#bids (gate_trial* → gate): its first range, inside 0 … 65 535."""
    rg = city.get("bids", {}).get("ranges", {}); k = _district_key(rg, d)
    return (int(rg[k]["from"]), int(rg[k]["to"])) if k else None


def district_ranges(city, d):
    """Every range a new building of the district may take, in order of preference: the first range (0 … 65 535), then the second
    (city.json#bids.ranges2, inside 65 536 … 131 071)."""
    out = []
    for key in ("ranges", "ranges2"):
        rg = city.get("bids", {}).get(key, {}); k = _district_key(rg, d)
        if k:
            out.append((int(rg[k]["from"]), int(rg[k]["to"])))
    return out


def overture_range(city, d):
    """Range of the district's existing houses that only Overture has (gen_buildings: source existing_osm, bid null),
    city.json#bids.existing_overture.by_district."""
    rg = (city.get("bids", {}).get("existing_overture") or {}).get("by_district", {}); k = _district_key(rg, d)
    return (int(rg[k]["from"]), int(rg[k]["to"])) if k else None
