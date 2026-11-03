"""Active recreation on the large empty sports land of the map (модель qTwin, owner 03.11.2026: «зелёные квадратики сделай как
места для активного отдыха: гольф, теннис, парки»): every group of sport lots over MIN_HA ha without buildings becomes
  - a golf club where its zone is golf_*: holes in rows (tee, fairway, green with its flag, bunkers), ponds, cart paths, a
    clubhouse with its car park at the edge nearest the street;
  - a sports park elsewhere: a grid of activity blocks — a tennis centre, padel courts, football pitches, a stadium with its
    running track, a skate park, a ropes park, basketball courts, playgrounds, picnic lawns, ponds — with paths between the
    blocks, a cycling loop round the park and rows of trees.
Writes UnityProject/Assets/Resources/Landmarks/recreation.json (drawn by Landmarks/CoastLayer.cs):
  fairways [{p: [x,z,…], w, y}]  greens/bunkers [{x, z, r, y}]  ponds [{t: [triangles x,z,…], y}]  paths [{p, w, y}]
  items [{k: kind, x, z, yaw, w, d, y}]  trees [x, z, …]
usage: python tools/map/export/recreation.py [out root (tools/map/out)] [out json]"""
import json
import math
import os
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely import affinity as A

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUTR = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ALATAU_OUT") or os.path.join(REPO, "tools", "map", "out")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(REPO, "UnityProject", "Assets", "Resources", "Landmarks", "recreation.json")
DISTRICTS = ("gate", "golden", "green", "growing_w", "growing_e")
MIN_HA = 20.0
SKIP_ZONES = ("track",)                      # the existing autodrome stays as it is

rng = np.random.default_rng(2035)
doc = {"v": 1, "made_by": "tools/map/export/recreation.py (модель qTwin)", "fairways": [], "greens": [], "bunkers": [], "ponds": [],
       "paths": [], "items": [], "trees": [], "sites": []}


def frame(poly):
    """(centre, angle deg, length, width) of the polygon's minimum rotated rectangle: its long side along local x."""
    mr = poly.minimum_rotated_rectangle
    c = list(mr.exterior.coords)[:4]
    e0 = np.subtract(c[1], c[0]); e1 = np.subtract(c[2], c[1])
    if np.linalg.norm(e0) < np.linalg.norm(e1):
        e0, e1 = e1, e0
    ang = math.degrees(math.atan2(e0[1], e0[0]))
    ctr = mr.centroid
    return (ctr.x, ctr.y), ang, float(np.linalg.norm(e0)), float(np.linalg.norm(e1))


def to_world(c, ang, x, z):
    a = math.radians(ang)
    return c[0] + x * math.cos(a) - z * math.sin(a), c[1] + x * math.sin(a) + z * math.cos(a)


def uyaw(ang):
    """Unity yaw of a local +x axis at math angle ang (from +x toward +z, counterclockwise)."""
    return round(90.0 - ang, 1)


def tri(poly):
    out = []
    q = shapely.segmentize(poly, 12.0)
    for t in getattr(shapely.constrained_delaunay_triangles(q), "geoms", []):
        if q.buffer(0.05).contains(t.centroid):
            for x, z in list(t.exterior.coords)[:3]:
                out += [round(x, 1), round(z, 1)]
    return out


def golf(poly, y, street):
    c, ang, L, W = frame(poly)
    inner = poly.buffer(-25.0)
    rows = max(1, int((W - 60) // 85))
    holes = 0
    pts_all = []
    for r in range(rows):
        z = -W / 2 + 60 + r * 85
        x0, x1 = -L / 2 + 50, L / 2 - 50
        seg = 0
        x = x0 if r % 2 == 0 else x1
        step = 330.0 if r % 2 == 0 else -330.0
        while (step > 0 and x + step <= x1) or (step < 0 and x + step >= x0):
            a = to_world(c, ang, x, z); b = to_world(c, ang, x + step * 0.92, z + rng.uniform(-14, 14))
            mid = to_world(c, ang, x + step * 0.5, z + rng.uniform(-18, 18))
            line = LineString([a, mid, b])
            if inner.contains(line) and holes < 18:
                doc["fairways"].append({"p": [round(v, 1) for q in line.coords for v in q], "w": round(rng.uniform(30, 40), 1), "y": y})
                doc["greens"].append({"x": round(b[0], 1), "z": round(b[1], 1), "r": round(rng.uniform(14, 18), 1), "y": y})
                doc["items"].append({"k": "tee", "x": round(a[0], 1), "z": round(a[1], 1), "yaw": uyaw(ang), "w": 12, "d": 8, "y": y})
                for k in range(3):
                    off = rng.uniform(-1, 1)
                    bq = to_world(c, ang, x + step * rng.uniform(0.55, 0.95), z + (26 if off > 0 else -26) + off * 6)
                    if inner.contains(Point(bq)):
                        doc["bunkers"].append({"x": round(bq[0], 1), "z": round(bq[1], 1), "r": round(rng.uniform(6, 11), 1), "y": y})
                pts_all += [a, b]
                holes += 1
            x += step
            seg += 1
    # ponds between the rows, cart paths along the rows, a clubhouse at the edge nearest the street
    for k in range(max(1, rows - 1)):
        pc = to_world(c, ang, rng.uniform(-L / 3, L / 3), -W / 2 + 60 + k * 85 + 42)
        pond = Point(pc).buffer(rng.uniform(28, 45), quad_segs=6)
        pond = A.scale(pond, 1.6, 0.8, origin=pc).intersection(inner)
        if pond.area > 600:
            doc["ponds"].append({"t": tri(pond), "y": y})
    for r in range(rows):
        z = -W / 2 + 60 + r * 85 + 30
        ln = LineString([to_world(c, ang, -L / 2 + 40, z), to_world(c, ang, L / 2 - 40, z)]).intersection(inner)
        for q in getattr(ln, "geoms", [ln]):
            if q.geom_type == "LineString" and q.length > 40:
                doc["paths"].append({"p": [round(v, 1) for p in q.coords for v in p], "w": 3.0, "y": y})
    cp = poly.exterior.interpolate(poly.exterior.project(street)) if street is not None else poly.representative_point()
    ch = Point(cp).buffer(1).centroid
    inward = np.subtract(poly.centroid.coords[0], ch.coords[0]); inward /= max(np.linalg.norm(inward), 1e-9)
    hq = (ch.x + inward[0] * 70, ch.y + inward[1] * 70)
    yaw = round(math.degrees(math.atan2(-inward[0], -inward[1])), 1)
    doc["items"].append({"k": "clubhouse", "x": round(hq[0], 1), "z": round(hq[1], 1), "yaw": yaw, "w": 60, "d": 30, "y": y})
    doc["items"].append({"k": "parking", "x": round(ch.x + inward[0] * 25, 1), "z": round(ch.y + inward[1] * 25, 1), "yaw": yaw, "w": 70, "d": 32, "y": y})
    doc["items"].append({"k": "driving_range", "x": round(hq[0] + inward[0] * 120, 1), "z": round(hq[1] + inward[1] * 120, 1), "yaw": yaw, "w": 90, "d": 180, "y": y})
    # trees along the rough between the rows
    for r in range(rows + 1):
        z = -W / 2 + 60 + r * 85 - 42
        for x in np.arange(-L / 2 + 40, L / 2 - 40, 22):
            q = to_world(c, ang, x + rng.uniform(-6, 6), z + rng.uniform(-6, 6))
            if inner.contains(Point(q)) and rng.random() < 0.75:
                doc["trees"] += [round(q[0], 1), round(q[1], 1)]
    return holes


# activity blocks of a sports park: kind, block size (along, across), how many of them in the mix
PARK_MIX = ["tennis", "football", "padel", "playground", "picnic", "basketball", "skate", "ropes", "picnic", "football",
            "tennis", "pond", "stadium", "picnic", "playground", "pond"]


def park(poly, y):
    c, ang, L, W = frame(poly)
    inner = poly.buffer(-20.0)
    BX, BZ, GAP = 150.0, 110.0, 14.0
    nx, nz = int(L // (BX + GAP)), int(W // (BZ + GAP))
    k = 0
    used = []
    for i in range(nx):
        for j in range(nz):
            x = -L / 2 + GAP + (BX + GAP) * (i + 0.5); z = -W / 2 + GAP + (BZ + GAP) * (j + 0.5)
            cell = Polygon([to_world(c, ang, x + sx * BX / 2, z + sz * BZ / 2) for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            if not inner.contains(cell):
                continue
            kind = PARK_MIX[k % len(PARK_MIX)]; k += 1
            cx, cz = to_world(c, ang, x, z)
            if kind == "pond":
                pond = A.scale(Point(cx, cz).buffer(46, quad_segs=8), 1.4, 0.95, origin=(cx, cz))
                pond = A.rotate(pond, ang, origin=(cx, cz)).intersection(cell.buffer(-6))
                doc["ponds"].append({"t": tri(pond), "y": y})
            else:
                doc["items"].append({"k": kind, "x": round(cx, 1), "z": round(cz, 1), "yaw": uyaw(ang), "w": BX, "d": BZ, "y": y})
            used.append(cell)
            # trees round the block's edge
            for t in np.arange(0, cell.exterior.length, 18):
                q = cell.exterior.interpolate(t)
                if rng.random() < (0.9 if kind in ("picnic", "playground", "pond") else 0.45):
                    doc["trees"] += [round(q.x + rng.uniform(-3, 3), 1), round(q.y + rng.uniform(-3, 3), 1)]
            if kind == "picnic":
                for _ in range(10):
                    q = (cx + rng.uniform(-60, 60), cz + rng.uniform(-40, 40))
                    doc["trees"] += [round(q[0], 1), round(q[1], 1)]
    # paths between the blocks (the grid lines inside the park) and the cycling loop round it
    for i in range(nx + 1):
        x = -L / 2 + GAP / 2 + (BX + GAP) * i
        ln = LineString([to_world(c, ang, x, -W / 2), to_world(c, ang, x, W / 2)]).intersection(inner)
        for q in getattr(ln, "geoms", [ln]):
            if q.geom_type == "LineString" and q.length > 30:
                doc["paths"].append({"p": [round(v, 1) for p in q.coords for v in p], "w": 5.0, "y": y})
    for j in range(nz + 1):
        z = -W / 2 + GAP / 2 + (BZ + GAP) * j
        ln = LineString([to_world(c, ang, -L / 2, z), to_world(c, ang, L / 2, z)]).intersection(inner)
        for q in getattr(ln, "geoms", [ln]):
            if q.geom_type == "LineString" and q.length > 30:
                doc["paths"].append({"p": [round(v, 1) for p in q.coords for v in p], "w": 5.0, "y": y})
    loop = poly.buffer(-10.0).exterior if poly.buffer(-10.0).geom_type == "Polygon" else None
    if loop is not None:
        loop = loop.simplify(3.0)
        doc["paths"].append({"p": [round(v, 1) for p in loop.coords for v in p], "w": 4.0, "y": y, "k": "bike"})
    return k


for d in DISTRICTS:
    lp = os.path.join(OUTR, d, "lots.json"); bp = os.path.join(OUTR, d, "blocks.json"); bb = os.path.join(OUTR, d, "buildings.json")
    np_ = os.path.join(OUTR, d, "network.json")
    if not os.path.exists(lp):
        continue
    L = json.load(open(lp, encoding="utf-8")); L = L["lots"] if isinstance(L, dict) else L
    B = json.load(open(bp, encoding="utf-8")); B = B["blocks"] if isinstance(B, dict) else B
    bz = {b["id"]: b.get("zone") or "" for b in B}
    built = {b.get("lot") for b in json.load(open(bb, encoding="utf-8")).get("buildings", [])} if os.path.exists(bb) else set()
    groups = {}
    for l in L:
        if l["use"] != "sport" or l["id"] in built or float(l.get("area_m2") or 0) < 2e4:
            continue
        z = bz.get(l["block"], "")
        if z.startswith(SKIP_ZONES):
            continue
        groups.setdefault(z, []).append(l)
    streets = []
    if os.path.exists(np_):
        nj = json.load(open(np_, encoding="utf-8"))
        streets = [LineString([p[:2] for p in s["pts"]]) for s in nj["segments"] if s["class"] in ("arterial_regulated", "district_transport", "local")]
    stree = shapely.STRtree(streets) if streets else None
    for z, ls in groups.items():
        poly = unary_union([Polygon(l["polygon"]).buffer(0.5) for l in ls]).buffer(-0.5)
        parts = [q for q in getattr(poly, "geoms", [poly]) if q.geom_type == "Polygon" and q.area > MIN_HA * 1e4]
        y = min(min(l.get("years") or [2035]) for l in ls)
        y = int(y if y > 2025 else 2035)
        for q in parts:
            q = q.simplify(2.0)
            st = None
            if stree is not None:
                j = stree.nearest(q.centroid); st = streets[int(j)].interpolate(streets[int(j)].project(q.centroid))
            if z.startswith("golf"):
                n = golf(q, y, st); what = f"golf club, {n} holes"
            else:
                n = park(q, y); what = f"sports park, {n} activity blocks"
            doc["sites"].append({"district": d, "zone": z, "ha": round(q.area / 1e4, 1), "what": what, "y": y})

open(OUT, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
print("recreation:", "; ".join(f"{s['district']}/{s['zone']} {s['ha']} ha → {s['what']} ({s['y']})" for s in doc["sites"]))
print(f"  {len(doc['fairways'])} fairways, {len(doc['bunkers'])} bunkers, {len(doc['ponds'])} ponds, {len(doc['paths'])} paths, "
      f"{len(doc['items'])} items, {len(doc['trees']) // 2} trees → {OUT}")
