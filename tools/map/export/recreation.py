"""Active recreation and tourist attractions on the open land of the map (модель qTwin).

Owner 03.11.2026: «зелёные квадратики сделай как места для активного отдыха: гольф, теннис, парки». Owner 05.11.2026: «тут должно
было быть огромное поле для гольфа … рядом с полем для гольфа активные способы отдыха: теннис, футбол, баскетбол, ипподромы … не так,
чтобы они плохо выглядели: разделены, у каждого своя зона, сделанная грамотно»; the golf rows of the East Golf Club are removed;
Green «зона, где реально будут много туристов».

  - GOLF_SITE (Green, zone f1, ≈ 310 ha): the Alatau Golf & Sports Park. Its larger part is an 18-hole championship course: holes in
    a routing of two loops of nine (par 3 / 4 / 5 by length), organic fairways of varying width with mowing stripes, tee boxes, greens
    with their flags and fringe, bunker clusters at the landing zones and by the greens, lakes between the holes, a turf rough over
    the whole course, groves between the holes, cart paths, a clubhouse with a terrace and its car park, a driving range and a
    practice green. The rest is a sports quarter: each sport on its own fenced plot with landscaping, an entrance and paths to a
    central promenade — a hippodrome (racecourse, grandstand, stables and paddock), a football stadium with training pitches, a tennis
    centre with a show court, a sports arena with outdoor basketball and volleyball courts, padel, a skate park and a playground;
    car parks at the edge, tree belts between the plots.
  - other sport land over MIN_HA ha without buildings (Golden, Growing-E): the same sports quarter, as many plots as fit;
  - SKIP_ZONES: the existing autodrome; NO_GOLF: the East Golf Club rows (zones golf_*) are no longer drawn (owner 05.11);
  - theme park of Green (zone theme): a ride park — roller coasters, a Ferris wheel, a drop tower, carousels, a castle, a lake
    with boats — and a water park with slides and pools; the lots without buildings only.
Writes UnityProject/Assets/Resources/Landmarks/recreation.json (drawn by Landmarks/CoastLayer.cs):
  turf [{t: triangles x,z,…, y}]  fairways [{t, y, s: stripe 0/1}]  greens/bunkers [{x, z, r, y}]  ponds [{t, y}]  paths [{p, w, y, k}]
  items [{k: kind, x, z, yaw, w, d, y}]  trees [x, z, …]  pines [x, z, …]  sites [...]
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
NO_GOLF = ("golf_",)                         # owner 05.11.2026: the East Golf Club rows are removed
GOLF_SITE = ("green", "f1")                  # owner 05.11.2026: the big golf course and the sports quarter

rng = np.random.default_rng(2035)
doc = {"v": 2, "made_by": "tools/map/export/recreation.py (модель qTwin)", "turf": [], "fairways": [], "greens": [], "bunkers": [],
       "ponds": [], "paths": [], "items": [], "trees": [], "pines": [], "sites": []}


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


def to_local(c, ang, x, z):
    a = math.radians(ang); dx, dz = x - c[0], z - c[1]
    return dx * math.cos(a) + dz * math.sin(a), -dx * math.sin(a) + dz * math.cos(a)


def uyaw(ang):
    """Unity yaw of a local +x axis at math angle ang (from +x toward +z, counterclockwise)."""
    return round(90.0 - ang, 1)


def polys(g):
    out = []
    for q in getattr(g, "geoms", [g]):
        if q.geom_type == "Polygon" and not q.is_empty:
            out.append(q)
        elif q.geom_type == "MultiPolygon":
            out += list(q.geoms)
    return out


def tri(poly, seg=12.0):
    out = []
    for p in polys(poly):
        q = shapely.segmentize(p, seg)
        for t in getattr(shapely.constrained_delaunay_triangles(q), "geoms", []):
            if q.buffer(0.05).contains(t.centroid):
                for x, z in list(t.exterior.coords)[:3]:
                    out += [round(x, 1), round(z, 1)]
    return out


def line_out(q, w, y, k=None):
    for g in getattr(q, "geoms", [q]):
        if g.geom_type == "LineString" and g.length > 20:
            d = {"p": [round(v, 1) for p in g.coords for v in p], "w": w, "y": y}
            if k:
                d["k"] = k
            doc["paths"].append(d)


def item(k, x, z, yaw, w, d, y):
    doc["items"].append({"k": k, "x": round(x, 1), "z": round(z, 1), "yaw": round(yaw, 1), "w": round(w, 1), "d": round(d, 1), "y": y})


def tree_ring(g, step, p, pine=False):
    for q in polys(g):
        L = q.exterior
        for t in np.arange(0, L.length, step):
            if rng.random() < p:
                pt = L.interpolate(t)
                doc["pines" if pine else "trees"].extend([round(pt.x + rng.uniform(-2, 2), 1), round(pt.y + rng.uniform(-2, 2), 1)])


def grove(g, n, pine_share=0.4):
    """n trees scattered in clumps inside g."""
    if g.is_empty or g.area < 400:
        return
    minx, minz, maxx, maxz = g.bounds
    made = 0; tries = 0
    centres = []
    while len(centres) < max(1, n // 7) and tries < n * 20:
        tries += 1
        p = Point(rng.uniform(minx, maxx), rng.uniform(minz, maxz))
        if g.contains(p):
            centres.append(p)
    for c in centres:
        pine = rng.random() < pine_share
        for _ in range(7):
            p = Point(c.x + rng.normal(0, 11), c.y + rng.normal(0, 11))
            if g.contains(p):
                doc["pines" if pine else "trees"].extend([round(p.x, 1), round(p.y, 1)]); made += 1
    return made


# ====================================================================================================== golf
def blob_line(pts, w0, w1, wobble):
    """An organic band along the polyline pts: discs of a width that swells from w0 to w1 and back, unioned and smoothed."""
    line = LineString(pts)
    discs = []
    n = max(8, int(line.length / 12))
    ph = rng.uniform(0, 6.28)
    for i in range(n + 1):
        t = i / n
        p = line.interpolate(t * line.length)
        w = w0 + (w1 - w0) * math.sin(t * math.pi) ** 0.7 + wobble * math.sin(t * 9.0 + ph)
        discs.append(p.buffer(max(w, 8.0) * 0.5, quad_segs=6))
    return unary_union(discs).buffer(6.0).buffer(-6.0).simplify(1.5)


def stripes(poly, c, ang_line, y, width=14.0):
    """The fairway cut into mowing stripes across the hole: alternate light and dark."""
    if poly.is_empty:
        return
    cx, cz = poly.centroid.x, poly.centroid.y
    R = math.sqrt(poly.area) * 3 + 400
    a = math.radians(ang_line)
    ux, uz = math.cos(a), math.sin(a)
    k = 0
    for s in np.arange(-R, R, width):
        b = Polygon([(cx + ux * s - uz * R, cz + uz * s + ux * R), (cx + ux * (s + width) - uz * R, cz + uz * (s + width) + ux * R),
                     (cx + ux * (s + width) + uz * R, cz + uz * (s + width) - ux * R), (cx + ux * s + uz * R, cz + uz * s - ux * R)])
        q = poly.intersection(b)
        if not q.is_empty and q.area > 20:
            t = tri(q, 10.0)
            if t:
                doc["fairways"].append({"t": t, "y": y, "s": k % 2})
        k += 1


def golf_course(poly, y, street):
    """18 holes in two loops of nine over poly; returns the number of holes and the union of the course's features."""
    c, ang, L, W = frame(poly)
    inner = poly.buffer(-30.0)
    doc["turf"].append({"t": tri(poly.buffer(-6.0), 20.0), "y": y})
    # the clubhouse corner: the course side nearest the street
    if street is not None:
        sx, sz = to_local(c, ang, street.x, street.y)
    else:
        sx, sz = -L / 2, 0.0
    flip = -1.0 if sx > 0 else 1.0                      # local x runs from the clubhouse end into the course
    lanes = max(2, int((W - 80) // 118))
    lane_w = (W - 80) / lanes
    # par pattern of 18 holes (lengths m): two nines, each with two par 3 and two par 5
    pars = [4, 5, 3, 4, 4, 3, 4, 5, 4, 4, 3, 5, 4, 4, 3, 4, 5, 4]
    plen = {3: (150, 200), 4: (330, 420), 5: (470, 540)}
    S = 300.0                                            # the clubhouse and range strip at the street end
    run, off = L - S - 50.0, (S - 50.0) / 2.0             # hole positions px in ±run/2 → local x = flip × (px + off)
    holes = []
    hole = 0; lane = 0; x = -run / 2; direction = 1
    feats = []
    while hole < 18 and lane < lanes:
        z0 = -W / 2 + 40 + lane_w * (lane % lanes + 0.5)
        par = pars[hole]
        ln = rng.uniform(*plen[par])
        x1 = x + direction * ln
        if (direction > 0 and x1 > run / 2) or (direction < 0 and x1 < -run / 2):
            lane += 1; direction = -direction
            x = run / 2 - 10 if direction < 0 else -run / 2 + 10
            continue
        dog = rng.uniform(-0.4, 0.4) * lane_w * (0.0 if par == 3 else 1.0)
        zt = z0 + rng.uniform(-lane_w * 0.18, lane_w * 0.18)
        zg = z0 + rng.uniform(-lane_w * 0.18, lane_w * 0.18)
        loc = [(x, zt), (x + direction * ln * 0.55, z0 + dog), (x1, zg)]
        pts = [to_world(c, ang, flip * (px + off), pz) for px, pz in loc]
        tee, mid, grn = pts
        fw_line = LineString([Point(tee).buffer(1).centroid, mid, grn])
        if not inner.buffer(10).contains(fw_line):
            x = x1 + direction * 25; continue
        hole += 1
        # fairway from ~ 60 m after the tee to the green's front (par 3: only a short apron)
        start = 0.0 if par == 3 else 60.0
        fl = fw_line.length
        sub = shapely.ops.substring(fw_line, start if par != 3 else fl - 40.0, fl - 18.0)
        wmax = rng.uniform(42, 58) if par != 3 else 26
        fw = blob_line(list(sub.coords), wmax * 0.65, wmax, 4.0).intersection(inner)
        a_line = math.degrees(math.atan2(grn[1] - tee[1], grn[0] - tee[0]))
        stripes(fw, c, a_line, y)
        gr = rng.uniform(15, 19)
        green = Point(grn).buffer(gr, quad_segs=8)
        green = A.scale(green, 1.25, 0.9, origin=Point(grn))
        green = A.rotate(green, a_line, origin=Point(grn))
        doc["greens"].append({"x": round(grn[0], 1), "z": round(grn[1], 1), "r": round(gr, 1), "y": y})
        doc["items"].append({"k": "tee", "x": round(tee[0], 1), "z": round(tee[1], 1), "yaw": uyaw(a_line), "w": 14, "d": 9, "y": y})
        # bunkers: a cluster by the green and one or two at the landing zone of par 4 / 5
        u = np.array([math.cos(math.radians(a_line)), math.sin(math.radians(a_line))]); n_ = np.array([-u[1], u[0]])
        for side in (-1, 1):
            if rng.random() < 0.8:
                b0 = np.array(grn) - u * rng.uniform(8, 20) + n_ * side * (gr + rng.uniform(6, 10))
                for j in range(rng.integers(1, 3)):
                    b = b0 + rng.normal(0, 4, 2)
                    doc["bunkers"].append({"x": round(float(b[0]), 1), "z": round(float(b[1]), 1), "r": round(float(rng.uniform(5, 8)), 1), "y": y})
        if par != 3:
            p_land = fw_line.interpolate(min(240.0, fl * 0.62))
            side = 1 if rng.random() < 0.5 else -1
            b = np.array([p_land.x, p_land.y]) + n_ * side * (wmax * 0.5 + rng.uniform(2, 6))
            for j in range(2):
                bb = b + u * j * 12 + rng.normal(0, 3, 2)
                doc["bunkers"].append({"x": round(float(bb[0]), 1), "z": round(float(bb[1]), 1), "r": round(float(rng.uniform(6, 10)), 1), "y": y})
        feats.append(fw.buffer(10)); feats.append(green.buffer(10)); feats.append(Point(tee).buffer(12))
        holes.append((tee, grn, par, fw_line))
        x = x1 + direction * 45
    played = unary_union(feats) if feats else Polygon()
    # lakes: in the rough between lanes, where nothing is played
    rough = inner.difference(played.buffer(14))
    lakes = []
    # up to 8 lakes where a 30 m disc fits in the rough, 250 m apart: water hazards next to the holes
    roomy = rough.buffer(-30.0)
    tries = 0
    while len(lakes) < 8 and tries < 400 and not roomy.is_empty:
        tries += 1
        minx, minz, maxx, maxz = roomy.bounds
        pc = Point(rng.uniform(minx, maxx), rng.uniform(minz, maxz))
        if not roomy.contains(pc) or any(pc.distance(l) < 250 for l in lakes):
            continue
        r0 = rng.uniform(32, 55)
        lake = A.scale(pc.buffer(r0, quad_segs=10), rng.uniform(1.3, 2.1), rng.uniform(0.6, 0.9), origin=pc)
        lake = A.rotate(lake, ang + rng.uniform(-35, 35), origin=pc).intersection(rough.buffer(-6)).buffer(4).buffer(-4)
        for lp in polys(lake):
            if lp.area > 1500:
                doc["ponds"].append({"t": tri(lp, 10.0), "y": y}); lakes.append(lp)
    lakes_u = unary_union(lakes) if lakes else Polygon()
    # (no cart paths: drawn as thin ribbons over the rough they read as stray lines from above)
    # groves in the rough between the holes, denser at the course's edge; a tree line along the boundary
    groves = rough.difference(lakes_u.buffer(12))
    for q in polys(groves):
        grove(q, int(q.area / 900), 0.45)
    tree_ring(poly.buffer(-12.0), 11.0, 0.9, pine=True)
    # clubhouse, car park, driving range and practice green at the street end
    side = -1.0 if sz < 0 else 1.0
    yaw = uyaw(ang + (0 if flip > 0 else 180))           # local +z into the course

    def inside(lx, lz, r):
        """The point (local) pulled toward the course's middle until a disc of radius r round it lies inside the course."""
        for k in range(30):
            p = to_world(c, ang, lx * (1 - k / 30), lz * (1 - k / 30))
            if poly.buffer(-r).contains(Point(p)):
                return p
        return None
    for kind, lx, lz, w_, d_ in (("clubhouse", -L / 2 + 70, side * (W / 2 - 110), 70, 34), ("parking", -L / 2 + 70, side * (W / 2 - 42), 90, 40),
                                 ("driving_range", -L / 2 + 160, -side * 60.0, 230, 110)):
        p = inside(flip * lx, lz, max(w_, d_) * 0.55)
        if p is not None:
            item(kind, p[0], p[1], yaw, w_, d_, y)
    p = inside(flip * (-L / 2 + 200), side * (W / 2 - 110), 30)
    if p is not None:
        doc["greens"].append({"x": round(p[0], 1), "z": round(p[1], 1), "r": 22.0, "y": y})
    return len(holes)


# ====================================================================================================== sports quarter
# each sport on its own plot: kind, plot (along, across) m, priority; the plot is fenced and landscaped, the facility in its middle
SPORT_PLOTS = [("hippodrome", 820, 420), ("stadium", 300, 230), ("tennis_centre", 250, 190), ("arena", 220, 160),
               ("football", 150, 110), ("football", 150, 110), ("basketball", 150, 110), ("padel", 120, 90),
               ("skate", 130, 100), ("playground", 120, 90), ("ropes", 130, 100), ("picnic", 150, 110),
               ("tennis", 150, 110), ("football", 150, 110), ("basketball", 150, 110), ("padel", 120, 90),
               ("picnic", 150, 110), ("playground", 120, 90), ("tennis", 150, 110), ("picnic", 150, 110)]


def sports_quarter(poly, y, street, plots=SPORT_PLOTS, gap=34.0):
    """Places the plots greedily (largest first) on a 10 m grid of the site's frame, gap m of green between them; returns their count."""
    c, ang, L, W = frame(poly)
    inner = poly.buffer(-22.0)
    placed = []
    taken = Polygon()
    if street is not None:
        sx, sz = to_local(c, ang, street.x, street.y)
    else:
        sx, sz = 0.0, -W
    # positions sorted from the street side inward, so the big crowd-pullers (hippodrome, stadium) sit by the access road
    cand = [(x, z) for x in np.arange(-L / 2, L / 2, 20.0) for z in np.arange(-W / 2, W / 2, 20.0)]
    cand.sort(key=lambda p: (p[0] - sx) ** 2 + (p[1] - sz) ** 2)
    for kind, pw, pd in plots:
        done = False
        for rot in (0.0, 90.0):
            w_, d_ = (pw, pd) if rot == 0 else (pd, pw)
            for x, z in cand:
                rect = Polygon([to_world(c, ang, x + sx_ * w_ / 2, z + sz_ * d_ / 2) for sx_, sz_ in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
                if not inner.contains(rect) or rect.buffer(gap * 0.5).intersects(taken):
                    continue
                cx, cz = to_world(c, ang, x, z)
                yaw = uyaw(ang + rot)
                # the facility (local w along its long side, as the drawing expects) and its plot
                item("plot", cx, cz, yaw, w_ if rot == 0 else d_, d_ if rot == 0 else w_, y)
                fw, fd = (pw - 30, pd - 30)
                if kind == "picnic":
                    grove(rect.buffer(-12), 40, 0.3)
                item(kind, cx, cz, yaw, fw, fd, y)
                tree_ring(rect.buffer(6.0), 12.0, 0.85)
                taken = taken.union(rect.buffer(gap * 0.5))
                placed.append((kind, rect))
                done = True
                break
            if done:
                break
    # the central promenade: a path round every plot's green belt joined into one walk, and a bike loop round the site
    if placed:
        belt = unary_union([r.buffer(gap * 0.5) for _, r in placed]).intersection(inner)
        for q in polys(belt):
            line_out(q.exterior.simplify(3.0).intersection(inner), 6.0, y, "promenade")
        rest = inner.difference(belt)
        for q in polys(rest):
            if q.area > 3000:
                grove(q, int(q.area / 1400), 0.35)
                if q.area > 25000 and rng.random() < 0.6:
                    pc = q.representative_point()
                    lake = A.scale(pc.buffer(min(45.0, math.sqrt(q.area) * 0.25), quad_segs=10), 1.5, 0.8, origin=pc).intersection(q.buffer(-10))
                    if lake.area > 1200:
                        doc["ponds"].append({"t": tri(lake, 10.0), "y": y})
        # car parks along the street side
        for i, (kind, r) in enumerate(placed):
            if kind in ("hippodrome", "stadium", "tennis_centre", "arena"):
                rc = r.centroid; lx, lz = to_local(c, ang, rc.x, rc.y)
                tz = (-W / 2 + 26) if sz < 0 else (W / 2 - 26)
                p = to_world(c, ang, lx, tz)
                if inner.buffer(14).contains(Point(p)) and not Point(p).buffer(20).intersects(unary_union([q for _, q in placed])):
                    item("parking", p[0], p[1], uyaw(ang), 100, 36, y)
    loop = poly.buffer(-10.0)
    if loop.geom_type == "Polygon":
        doc["paths"].append({"p": [round(v, 1) for p in loop.exterior.simplify(3.0).coords for v in p], "w": 4.0, "y": y, "k": "bike"})
    return len(placed)


# ====================================================================================================== theme park and water park
def theme_park(poly, y, land=None):
    c, ang, L, W = frame(poly)
    inner = (poly if land is None else land.intersection(poly)).buffer(-12.0)
    if inner.is_empty:
        return 0
    n = 0
    # a lake in the middle with boats, rides round it, the water park on the larger free end
    pc = max(polys(inner), key=lambda g: g.area).representative_point()
    lake = A.scale(pc.buffer(min(70.0, math.sqrt(inner.area) * 0.18), quad_segs=12), 1.6, 0.9, origin=pc).intersection(inner.buffer(-15))
    if lake.area > 2000:
        doc["ponds"].append({"t": tri(lake, 10.0), "y": y}); item("boats", pc.x, pc.y, uyaw(ang), 40, 20, y); n += 1
    rides = ["coaster", "wheel", "drop_tower", "carousel", "castle", "coaster", "swing", "carousel", "waterpark", "drop_tower", "swing", "castle",
             "coaster", "carousel", "swing", "castle", "drop_tower", "carousel", "coaster", "swing", "carousel", "castle", "swing", "carousel",
             "coaster", "drop_tower", "carousel", "swing"]
    sizes = {"coaster": (190, 110), "wheel": (80, 60), "drop_tower": (50, 50), "carousel": (60, 60), "castle": (110, 80),
             "swing": (60, 60), "waterpark": (230, 160)}
    taken = lake.buffer(30) if not lake.is_empty else Polygon()
    cand = [(x, z) for x in np.arange(-L / 2, L / 2, 15.0) for z in np.arange(-W / 2, W / 2, 15.0)]
    cand.sort(key=lambda p: p[0] ** 2 + p[1] ** 2)
    for k in rides:
        pw, pd = sizes[k]
        for x, z in cand:
            rect = Polygon([to_world(c, ang, x + sx_ * pw / 2, z + sz_ * pd / 2) for sx_, sz_ in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            if inner.contains(rect) and not rect.buffer(12).intersects(taken):
                cx, cz = to_world(c, ang, x, z)
                item(k, cx, cz, uyaw(ang), pw, pd, y)
                taken = taken.union(rect.buffer(12)); n += 1
                break
    # paved midway paths round the lake and to every ride, trees and flower beds in the rest
    if not lake.is_empty:
        line_out(lake.buffer(18).exterior.intersection(inner), 8.0, y, "plaza")
    for q in polys(inner.difference(taken.buffer(6))):
        if q.area > 2000:
            grove(q, int(q.area / 1100), 0.2)
    return n


def lots_of(d):
    lp = os.path.join(OUTR, d, "lots.json"); bp = os.path.join(OUTR, d, "blocks.json"); bb = os.path.join(OUTR, d, "buildings.json")
    if not os.path.exists(lp):
        return None, None, set()
    L = json.load(open(lp, encoding="utf-8")); L = L["lots"] if isinstance(L, dict) else L
    B = json.load(open(bp, encoding="utf-8")); B = B["blocks"] if isinstance(B, dict) else B
    built = {b.get("lot") for b in json.load(open(bb, encoding="utf-8")).get("buildings", [])} if os.path.exists(bb) else set()
    return L, {b["id"]: b.get("zone") or "" for b in B}, built


for d in DISTRICTS:
    L, bz, built = lots_of(d)
    if L is None:
        continue
    groups, theme = {}, []
    for l in L:
        z = bz.get(l["block"], "")
        if d == "green" and z == "theme" and l["id"] not in built:
            theme.append(l); continue                    # every lot of the ride park, small ones too: the streets cut it into blocks
        if l["id"] in built or float(l.get("area_m2") or 0) < 2e4:
            continue
        if l["use"] != "sport" or z.startswith(SKIP_ZONES) or z.startswith(NO_GOLF):
            continue
        groups.setdefault(z, []).append(l)
    streets = []
    np_ = os.path.join(OUTR, d, "network.json")
    if os.path.exists(np_):
        nj = json.load(open(np_, encoding="utf-8"))
        streets = [LineString([p[:2] for p in s["pts"]]) for s in nj["segments"] if s["class"] in ("arterial_regulated", "district_transport", "local")]
    stree = shapely.STRtree(streets) if streets else None

    def near_street(q):
        if stree is None:
            return None
        j = stree.nearest(q.centroid); return streets[int(j)].interpolate(streets[int(j)].project(q.centroid))

    def year_of(ls, dflt=2035):
        y = min(min(l.get("years") or [dflt]) for l in ls)
        return int(y if y > 2025 else dflt)

    for z, ls in groups.items():
        poly = unary_union([Polygon(l["polygon"]).buffer(0.5) for l in ls]).buffer(-0.5)
        parts = [q for q in polys(poly) if q.area > MIN_HA * 1e4]
        y = year_of(ls)
        for q in parts:
            q = q.simplify(2.0)
            st = near_street(q)
            if (d, z) == GOLF_SITE:
                # the larger part (≈ 60 %) the golf course, the rest by the access street the sports quarter; a 40 m tree belt between
                c, ang, Lx, Wz = frame(q)
                sx, sz = to_local(c, ang, st.x, st.y) if st is not None else (0.0, -Wz)
                cut = Lx * 0.08 * (1 if sx > 0 else -1)
                half = Polygon([to_world(c, ang, x_, z_) for x_, z_ in ((cut, -Wz), (Lx, -Wz), (Lx, Wz), (cut, Wz))]) if sx > 0 else \
                    Polygon([to_world(c, ang, x_, z_) for x_, z_ in ((-Lx, -Wz), (cut, -Wz), (cut, Wz), (-Lx, Wz))])
                sport_part = q.intersection(half).buffer(-20)
                golf_part = q.difference(half).buffer(-20)
                gq = max(polys(golf_part), key=lambda g: g.area)
                sq = max(polys(sport_part), key=lambda g: g.area)
                tree_ring(q.intersection(half.buffer(22)).difference(half.buffer(-22)).buffer(0), 9.0, 0.95, pine=True)
                n1 = golf_course(gq, y, st)
                n2 = sports_quarter(sq, y, st)
                what = f"golf course, {n1} holes ({gq.area / 1e4:.0f} ha) + sports quarter, {n2} plots ({sq.area / 1e4:.0f} ha)"
            else:
                n = sports_quarter(q, y, st, plots=[p for p in SPORT_PLOTS if p[0] != "hippodrome"])
                what = f"sports quarter, {n} plots"
            doc["sites"].append({"district": d, "zone": z, "ha": round(q.area / 1e4, 1), "what": what, "y": y})
    if theme:
        # one park over all its lots: the inner streets (≤ 40 m red lines) are bridged for the layout, rides stand on the lots only
        lots_u = unary_union([Polygon(l["polygon"]).buffer(0.5) for l in theme]).buffer(-0.5)
        y = year_of(theme, 2038)
        site = lots_u.buffer(22.0).buffer(-22.0)
        for q in polys(site):
            if q.area > 4e4:
                n = theme_park(q.simplify(2.0), y, lots_u)
                doc["sites"].append({"district": d, "zone": "theme", "ha": round(q.area / 1e4, 1), "what": f"theme park, {n} rides", "y": y})

open(OUT, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
print("recreation:", "; ".join(f"{s['district']}/{s['zone']} {s['ha']} ha → {s['what']} ({s['y']})" for s in doc["sites"]))
print(f"  {len(doc['fairways'])} fairway stripes, {len(doc['greens'])} greens, {len(doc['bunkers'])} bunkers, {len(doc['ponds'])} ponds, "
      f"{len(doc['paths'])} paths, {len(doc['items'])} items, {len(doc['trees']) // 2} trees, {len(doc['pines']) // 2} pines → {OUT}")
