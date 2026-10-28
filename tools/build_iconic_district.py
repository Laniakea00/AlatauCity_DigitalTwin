"""Quarters round Iconic Complex as on the presentation model (2 June 2026): white housing blocks round courtyards, L-blocks with a
corner tower, slabs and point towers, packed on the free land within 640 m of the tower — away from the film roads, the motorway
interchange, the round square, the water of the Iconic grounds and the plan's own buildings (which stay, drawn white by the film look).

Writes UnityProject/Assets/Resources/Landmarks/iconic_district.json in the local frame of the Iconic model (x along the podium, z across),
read by Scripts/DigitalTwin/Landmarks/IconicDistrict.cs.   Usage: python tools/build_iconic_district.py  (needs shapely)"""
import csv, json, math, random, struct, sys
from pathlib import Path
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
from shapely import affinity

ROOT = Path(__file__).resolve().parent.parent / "UnityProject" / "Assets"
X0, Z0, YAW = -2567.0, -20654.0, 105.2          # LandmarkData: Iconic Complex
R = 640.0
_a = math.radians(YAW); CA, SA = math.cos(_a), math.sin(_a)

def loc(x, z):
    dx, dz = x - X0, z - Z0
    return dx * CA - dz * SA, dx * SA + dz * CA

def main():
    region = Point(0, 0).buffer(R, 64)
    obs = []
    half = {"highway": 30, "ring": 24, "main": 19, "street": 13}
    for s in json.load(open(ROOT / "Resources/Landmarks/film_roads.json", encoding="utf-8"))["s"]:
        g = s["g"]; pts = [loc(g[i], g[i + 1]) for i in range(0, len(g), 2)]
        if len(pts) < 2 or all(abs(u) > R + 80 or abs(v) > R + 80 for u, v in pts): continue
        obs.append(LineString(pts).buffer(half.get(s["c"], 14)))
    # the cloverleaf west of the tower and the land between its ramps
    obs.append(Polygon([(-700, -700), (-330, -700), (-330, -260), (-110, -60), (-110, 250), (-330, 520), (-330, 700), (-700, 700)]))
    obs.append(affinity.scale(Point(0, 0).buffer(1, 64), 157, 122))                     # the round square
    park = json.load(open(ROOT / "Resources/Landmarks/iconic_park.json", encoding="utf-8")); t = park["tris"]
    water = [Polygon([loc(t[i], t[i + 1]), loc(t[i + 2], t[i + 3]), loc(t[i + 4], t[i + 5])]) for i in range(0, len(t), 8) if round(t[i + 6]) == 7]
    if water: obs.append(unary_union(water).buffer(8))
    b = (ROOT / "Resources/Landmarks/bid_bounds.bytes").read_bytes(); n = struct.unpack("<i", b[4:8])[0]
    bb = struct.unpack("<%df" % (n * 4), b[8:8 + n * 16])
    pad = box(-141, -106, 141, 106)                                                       # buildings the Iconic plot replaces
    with open(ROOT / "CityData/buildings.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bid = int(r["bid"]); x0, z0, x1, z1 = bb[bid * 4:bid * 4 + 4]
            if x1 <= x0: continue
            u, v = loc(float(r["x"]), float(r["z"]))
            if abs(u) > R + 100 or abs(v) > R + 100: continue
            poly = Polygon([loc(x0, z0), loc(x1, z0), loc(x1, z1), loc(x0, z1)])
            if not poly.intersects(pad): obs.append(poly.buffer(12))
    free = region.difference(unary_union(obs))
    rnd = random.Random(7); out = []
    cands = sorted(((x, y) for x in range(-int(R), int(R) + 1, 4) for y in range(-int(R), int(R) + 1, 4)), key=lambda q: q[0] ** 2 + q[1] ** 2)
    # biggest pieces first, nearest the tower first: courtyard blocks, L-blocks with a tower, slabs, point towers
    for name, w, d in (("court", 66, 50), ("lblock", 52, 44), ("slab", 60, 16), ("tower", 30, 30)):
        for x, y in cands:
            if not free.contains(Point(x, y)): continue
            for rot in (0, 90):
                ww, dd = (w, d) if rot == 0 else (d, w)
                r = box(x - ww / 2, y - dd / 2, x + ww / 2, y + dd / 2)
                if free.contains(r.buffer(3, join_style=2)):
                    fl = rnd.choice([7, 8, 8, 9, 10]) if name != "tower" else rnd.choice([22, 25, 28, 30, 34])
                    tw = rnd.choice([16, 18, 20, 24]) if name == "lblock" else 0
                    out.append(dict(t=name, x=x, z=y, w=ww, d=dd, f=fl, tf=tw, s=rnd.randint(0, 9999), r=rot))
                    free = free.difference(r.buffer(18, join_style=2)); break
    dst = ROOT / "Resources/Landmarks/iconic_district.json"
    dst.write_text(json.dumps({"cx": X0, "cz": Z0, "yaw": YAW, "b": out}, separators=(",", ":")), encoding="utf-8")
    print(len(out), "buildings ->", dst)

if __name__ == "__main__":
    main()
