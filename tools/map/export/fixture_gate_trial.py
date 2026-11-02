#!/usr/bin/env python3
"""Fixture district `gate_trial_fixture` for merge_districts.py while the real generators are being written (w45 brief, item 3).

    python3 tools/map/export/fixture_gate_trial.py [--out OUT]

Converts what the twin draws today inside x −4200…−1700, z −20600…−18300 into the contract formats (CONTRACT §4):
  * network.json — the film strokes (Resources/Landmarks/film_roads.json, the clean geometry Unity draws) clipped to the box, split
    at their junctions and crossings; heights from the terrain; classes: highway → expressway (one carriageway each, oriented for
    right-hand traffic), highway ramps → ramp, main → arterial_regulated, street → local; years as drawn;
  * one synthetic interchange on A-3 at z = −18900: a district_transport cross road over A-3 on a 80 m overpass (deck 7 m above A-3,
    5.5 m clearance) with 4 % embankment approaches, and a diamond of four ramps (diverge / merge nodes on the A-3 carriageways,
    signalised terminals on the cross road);
  * to exercise the new street types: one street turned into a boulevard (12 m green median), one into a pedestrian street, one dead
    end into a driveway, and a new two-way bike path;
  * buildings.json — every twin building in the box kept by bid (footprint = convex hull of its mesh), those under the new roads
    removed, a row of new 9-storey blocks (bid null) east of A-3;
  * lrt.json — the LRT trunk inside the box with its stations; features.json — one parking lot and one no-plant plaza;
  * spec.json — the area (merge reads it when there is no spec/<d>.json).
A picture of the result goes to OUT/_fixtures/w45/gate_trial_fixture.png."""
import argparse
import collections
import math
import os
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import util as U  # noqa: E402

sys.path.insert(0, U.TWIN_GEN)
import twin_common as TC  # noqa: E402

D_ID = "gate_trial_fixture"
BOX = (-4200.0, -20600.0, -1700.0, -18300.0)
Z0 = -18900.0                       # the cross road
CLEAR, DECK = 5.5, 1.5              # clearance under the deck, deck depth
SLOPE = 0.04                        # approach gradient
SPAN_HALF = 40.0                    # overpass half length (covers both carriageways and their shoulders)
TERM = 75.0                         # ramp terminals: metres from the A-3 axis along the cross road
RAMP_L = 330.0                      # diverge / merge points: metres along A-3 from the cross road
FAST = ("highway", "ring")


def years4(y):
    return [TC.effective_year(int(y), "infra_road", "generated", s) for s in TC.SCENARIOS]


def resample(P, step):
    L = LineString(P); n = max(1, int(math.ceil(L.length / step)))
    return [tuple(L.interpolate(L.length * i / n).coords[0]) for i in range(n + 1)]


def profile(norms, cls, lanes, **kw):
    sp = norms["street_profiles"].get(cls, {})

    def v(key, default):
        x = (sp.get(key) or {}).get("value", default)
        if isinstance(x, dict):
            x = x.get("min", next((q for q in x.values() if isinstance(q, (int, float))), default))
        return float(x) if isinstance(x, (int, float)) else default
    p = {"class": cls, "lanes": lanes, "lane_w": v("lane_width_m", 3.5), "median_w": v("median_m", 0.0),
         "sidewalk_w": [v("sidewalk_m", 0.0)] * 2, "verge_w": [v("green_strip_m", 0.0)] * 2, "bike_w": [0.0, 0.0], "parking_w": [0.0, 0.0],
         "red_line_w": v("red_lines_m", 15.0)}
    p.update(kw)
    return p


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=U.OUT); a = ap.parse_args()
    out_dir = os.path.join(a.out, D_ID); pic_dir = os.path.join(a.out, "_fixtures", "w45")
    norms = U.load_json(os.path.join(U.SPEC, "norms.json")); terrain = U.Terrain()
    film = U.load_json(os.path.join(U.TWIN, U.F_FILM))
    area = box(*BOX)
    log = []

    def H(x, z):
        return round(float(terrain.height(x, z)), 2)
    # ------------------------------------------------------------ pieces of the drawn roads inside the box
    pieces = []          # {P, cls, k, years, oneway, name}
    for i, s in enumerate(film["s"]):
        g = s["g"]; L = LineString([(g[j], g[j + 1]) for j in range(0, len(g), 2)])
        if not L.intersects(area):
            continue
        X = L.intersection(area)
        for q in getattr(X, "geoms", [X]):
            if q.geom_type != "LineString" or q.length < 5:
                continue
            c = [tuple(p) for p in q.coords]
            if L.project(Point(c[0])) > L.project(Point(c[-1])):
                c.reverse()
            if s["k"] == 2:
                cls = "ramp"
            elif s["c"] in FAST:
                cls = "expressway"
            elif s["c"] == "main":
                cls = "arterial_regulated"
            else:
                cls = "local"
            pieces.append({"P": c, "cls": cls, "oneway": s["k"] == 1 or s["k"] == 2, "years": list(s["y"]), "stroke": i,
                           "name": "БАКАД" if s["c"] == "ring" else ("А-3" if i in (38, 39) else None), "src": s["c"]})
    # one carriageway of a dual road: the other direction on its left (right-hand traffic)
    ow = [p for p in pieces if p["oneway"] and p["cls"] != "ramp"]
    for p in ow:
        L = LineString(p["P"]); votes = 0
        for f in (0.2, 0.4, 0.6, 0.8):
            m = L.interpolate(f, normalized=True); m2 = L.interpolate(min(1.0, f + 0.02), normalized=True)
            d = np.array([m2.x - m.x, m2.y - m.y]); d /= max(np.linalg.norm(d), 1e-9); left = np.array([-d[1], d[0]])
            best = None
            for q in ow:
                if q is p or q["src"] != p["src"]:
                    continue
                Lq = LineString(q["P"]); dist = Lq.distance(m)
                if 3 < dist < 45 and (best is None or dist < best[0]):
                    c = Lq.interpolate(Lq.project(m)); best = (dist, np.dot([c.x - m.x, c.y - m.y], left))
            if best:
                votes += 1 if best[1] > 0 else -1
        if votes < 0:
            p["P"].reverse()
    # ramps: the direction that leaves and joins the carriageways with their traffic
    for p in pieces:
        if p["cls"] != "ramp":
            continue
        score = 0.0
        P = np.array(p["P"])
        for end, tan in ((P[0], P[min(3, len(P) - 1)] - P[0]), (P[-1], P[-1] - P[max(-4, -len(P))])):
            tan = tan / max(np.linalg.norm(tan), 1e-9); best = None
            for q in ow:
                Lq = LineString(q["P"]); dist = Lq.distance(Point(end))
                if dist < 30 and (best is None or dist < best[0]):
                    t = Lq.project(Point(end)); a1 = Lq.interpolate(max(0, t - 5)); a2 = Lq.interpolate(min(Lq.length, t + 5))
                    dq = np.array([a2.x - a1.x, a2.y - a1.y]); best = (dist, float(np.dot(tan, dq / max(np.linalg.norm(dq), 1e-9))))
            if best:
                score += best[1]
        if score < 0:
            p["P"].reverse()
    # ------------------------------------------------------------ the synthetic interchange on A-3
    sb = next(p for p in pieces if p["stroke"] == 38); nb = next(p for p in pieces if p["stroke"] == 39)
    zl = LineString([(-3000, Z0), (-1000, Z0)])
    xs = LineString(sb["P"]).intersection(zl).x; xn = LineString(nb["P"]).intersection(zl).x
    if xs > xn:
        sb, nb, xs, xn = nb, sb, xn, xs
    xa = (xs + xn) / 2; ya = max(H(xs, Z0), H(xn, Z0)); deck = ya + CLEAR + DECK      # the higher carriageway keeps the clearance
    log.append(f"A-3 at z {Z0:.0f}: SB x {xs:.1f}, NB x {xn:.1f}, axis {xa:.1f}, surface {ya:.2f} m, deck {deck:.2f} m")

    def cross_y(x):
        return max(H(x, Z0), deck - SLOPE * max(0.0, abs(x - xa) - SPAN_HALF))
    # west end: the street the cross road starts from (first street crossing z0 that leaves room for the approach)
    xw = max(LineString(p["P"]).intersection(zl).x for p in pieces
             if p["cls"] == "local" and LineString(p["P"]).intersects(zl) and LineString(p["P"]).intersection(zl).geom_type == "Point"
             and LineString(p["P"]).intersection(zl).x < xa - SPAN_HALF - (deck - ya) / SLOPE - 20)
    xe = BOX[2] - 60.0

    def ramp_pts(cw, off):
        """Ramp on the right of a carriageway polyline (driving direction): an off-ramp leaves it RAMP_L before the cross road, an
        on-ramp joins it RAMP_L after; S-shaped lateral shift (smoothstep, zero slope at both ends) to the terminal on z = Z0."""
        L = LineString(cw["P"]); X = L.intersection(zl); u0 = L.project(Point(X.coords[0]))
        shift = TERM - abs(X.x - xa)
        u_a, u_b = (u0 - RAMP_L, u0 + 25) if off else (u0 - 25, u0 + RAMP_L)
        n = int((u_b - u_a) // 5) + 1; pts = []
        for i in range(n + 1):
            u = u_a + (u_b - u_a) * i / n
            c1 = L.interpolate(max(0, u - 2)); c2 = L.interpolate(min(L.length, u + 2)); c = L.interpolate(u)
            d = np.array([c2.x - c1.x, c2.y - c1.y]); d /= np.linalg.norm(d); right = np.array([d[1], -d[0]])
            f = (u - u_a) / RAMP_L if off else (u_b - u) / RAMP_L
            f = min(1.0, max(0.0, f)); sm = f * f * (3 - 2 * f)
            pts.append((c.x + right[0] * shift * sm, c.y + right[1] * shift * sm))
        Lp = LineString(pts); Xp = Lp.intersection(zl)
        t = Lp.project(Point(Xp.coords[0] if Xp.geom_type == "Point" else Xp.geoms[0].coords[0]))
        if off:
            P = [q for q in pts if Lp.project(Point(q)) < t - 0.5] + [(Lp.interpolate(t).x, Z0)]
        else:
            P = [(Lp.interpolate(t).x, Z0)] + [q for q in pts if Lp.project(Point(q)) > t + 0.5]
        return P, (u_a if off else u_b)
    ramps = []
    for base_cw, toward, name in ((nb, True, "NB off"), (nb, False, "NB on"), (sb, True, "SB off"), (sb, False, "SB on")):
        P, u_cw = ramp_pts(base_cw, toward)
        ramps.append({"P": P, "cw": base_cw, "u": u_cw, "off": toward, "name": name})
    term_e = [r["P"][-1] if r["off"] else r["P"][0] for r in ramps[:2]]
    term_w = [r["P"][-1] if r["off"] else r["P"][0] for r in ramps[2:]]
    xte = float(np.mean([p[0] for p in term_e])); xtw = float(np.mean([p[0] for p in term_w]))
    for r in ramps:
        i = -1 if r["off"] else 0; x = xte if r in ramps[:2] else xtw
        P = list(r["P"]); P[i] = (x, Z0); r["P"] = P
    log.append(f"cross road x {xw:.0f} … {xe:.0f}; terminals x {xtw:.1f} / {xte:.1f}; overpass x {xa - SPAN_HALF:.0f} … {xa + SPAN_HALF:.0f}")
    cross = [(x, Z0) for x in np.arange(xw, xe, 10.0)] + [(xe, Z0)]
    for x in (xtw, xte, xa - SPAN_HALF, xa + SPAN_HALF):
        cross.append((x, Z0))
    cross = sorted(set((round(x, 2), z) for x, z in cross))
    # ------------------------------------------------------------ street types to exercise: boulevard, pedestrian street, driveway, bike path
    loc = [p for p in pieces if p["cls"] == "local" and not p["oneway"]]

    def pick(cx, cz):
        return min(loc, key=lambda p: LineString(p["P"]).distance(Point(cx, cz)))
    blv = pick(-3300, -18850); blv["cls"] = "boulevard"
    ped = pick(-2950, -19300)
    if ped is blv:
        ped = sorted(loc, key=lambda p: LineString(p["P"]).distance(Point(-2950, -19300)))[1]
    ped["cls"] = "pedestrian_street"
    stub = min((p for p in loc if p["cls"] == "local" and LineString(p["P"]).length < 400), key=lambda p: LineString(p["P"]).distance(Point(-3600, -20200)))
    stub["cls"] = "driveway_main"
    bike = {"P": resample([(-3420, -19020), (-3200, -19060), (-3000, -19160)], 8), "cls": "bike_path", "oneway": False, "years": [2032, 2031, 2034, 2034],
            "stroke": -1, "name": "велодорожка", "src": "new"}
    log.append(f"types: boulevard = film stroke {blv['stroke']}, pedestrian street = {ped['stroke']}, driveway = {stub['stroke']}, bike path new")
    # ------------------------------------------------------------ split everything at the interchange points, then build the graph
    yrs_ic = [2031, 2030, 2034, 2029]
    segs_in = []        # (P, cls, oneway, years, name, extra)
    for p in pieces:
        segs_in.append({"P": p["P"], "cls": p["cls"], "oneway": p["oneway"], "years": p["years"], "name": p["name"], "kind": "film", "stroke": p["stroke"]})
    segs_in.append(dict(bike, kind="bike", P=bike["P"]))
    segs_in.append({"P": cross, "cls": "district_transport", "oneway": False, "years": yrs_ic, "name": "Путепровод через А-3 (фикстура)", "kind": "cross", "stroke": -1})
    for r in ramps:
        segs_in.append({"P": r["P"], "cls": "ramp", "oneway": True, "years": yrs_ic, "name": f"съезд {r['name']}", "kind": "ramp", "stroke": -1})
    # split points: ramp ends on the carriageways; ramp terminals on the cross road; T-ends and at-grade crossings of streets
    cuts = collections.defaultdict(list)    # seg index → [along]
    idx = {id(s): i for i, s in enumerate(segs_in)}
    ci = len(pieces) + 1
    for r in ramps:
        cw = next(i for i, s in enumerate(segs_in) if s.get("stroke") == r["cw"]["stroke"] and s["kind"] == "film")
        cuts[cw].append(r["u"])
        Lc = LineString(cross); x = r["P"][-1][0] if r["off"] else r["P"][0][0]
        cuts[ci].append(Lc.project(Point(x, Z0)))
    # the drawn cloverleaf ramps end a few metres off the carriageway centre lines: join each end to the nearest carriageway there
    cws = [i for i, q in enumerate(segs_in) if q["cls"] == "expressway"]
    for i, q in enumerate(segs_in):
        if q["cls"] != "ramp" or q["kind"] != "film":
            continue
        P = list(q["P"])
        for end in (0, -1):
            pe = Point(P[end]); best = None
            for j in cws:
                Lj = LineString(segs_in[j]["P"]); d = Lj.distance(pe)
                if d < 16 and (best is None or d < best[0]):
                    best = (d, j, Lj.project(pe))
            if best and best[0] > 0.3:
                d, j, t = best; Lj = LineString(segs_in[j]["P"]); c = Lj.interpolate(t)
                if 1 < t < Lj.length - 1:
                    cuts[j].append(t)
                if end == 0:
                    P.insert(0, (c.x, c.y))
                else:
                    P.append((c.x, c.y))
        q["P"] = P
    lines = [LineString(s["P"]) for s in segs_in]
    tree = shapely.STRtree(lines)
    grade = lambda s: s["cls"] in ("expressway", "ramp")  # noqa: E731
    for i, s in enumerate(segs_in):
        Li = lines[i]
        for j in tree.query(Li.buffer(8)):
            j = int(j)
            if j == i:
                continue
            sj = segs_in[j]; Lj = lines[j]
            if grade(s) or grade(sj) or s["kind"] == "cross" and sj["kind"] == "cross":
                continue
            if i < j:
                X = Li.intersection(Lj)
                for q in getattr(X, "geoms", [X]):
                    if q.geom_type == "Point":
                        cuts[i].append(Li.project(q)); cuts[j].append(Lj.project(q))
            for end in (Point(s["P"][0]), Point(s["P"][-1])):
                d = Lj.distance(end); t = Lj.project(end)
                if 0.01 < d < 8 and 2 < t < Lj.length - 2:
                    cuts[j].append(t)
    # cross road over A-3: no at-grade split with the carriageways (already excluded: expressway); cut the cross road where it meets
    # the west street exactly
    segs = []
    for i, s in enumerate(segs_in):
        L = lines[i]; ts = sorted(set(round(t, 2) for t in cuts.get(i, []) if 0.5 < t < L.length - 0.5))
        bounds_ = [0.0] + ts + [L.length]
        for a0, a1 in zip(bounds_[:-1], bounds_[1:]):
            if a1 - a0 < 0.5:
                continue
            sub = shapely.ops.substring(L, a0, a1)
            segs.append(dict(s, P=[tuple(p) for p in sub.coords], from_m=a0, to_m=a1))
    # nodes: ends clustered within 4 m; a street end that lies on another segment snaps to that split point
    ends = np.array([p for s in segs for p in (s["P"][0], s["P"][-1])])
    kd = cKDTree(ends); parent = list(range(len(ends)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i, j in kd.query_pairs(4.0):
        parent[find(i)] = find(j)
    groups = collections.defaultdict(list)
    for i in range(len(ends)):
        groups[find(i)].append(i)
    node_of = {}; nodes = []
    for g, members in groups.items():
        xy = ends[members].mean(axis=0)
        # a ramp end or a split point keeps its exact position
        node_of.update({m: len(nodes) for m in members}); nodes.append([float(xy[0]), float(xy[1])])
    deg = collections.Counter(node_of.values())
    # ------------------------------------------------------------ heights, structures, profiles, segments
    profiles = {
        "expressway_cw": profile(norms, "expressway", [3, 0], lane_w=3.75, median_w=0.0, verge_w=[3.0, 1.0], red_line_w=50.0),
        "ramp": profile(norms, "ramp", [1, 0], lane_w=5.0, verge_w=[1.5, 3.0], red_line_w=12.0),
        "arterial_regulated": profile(norms, "arterial_regulated", [2, 2], lane_w=3.5),
        "arterial_regulated_cw": profile(norms, "arterial_regulated", [2, 0], lane_w=3.5, median_w=0.0),
        "district_transport": profile(norms, "district_transport", [2, 2], lane_w=3.5, median_w=2.0),
        "local": profile(norms, "local", [1, 1]),
        "local_cw": profile(norms, "local", [1, 0]),
        "boulevard": profile(norms, "boulevard", [2, 2], lane_w=3.25, median_w=12.0, sidewalk_w=[3.0, 3.0], verge_w=[1.5, 1.5], bike_w=[1.5, 1.5], red_line_w=45.0),
        "pedestrian_street": profile(norms, "pedestrian_street", [0, 0], lane_w=0.0, median_w=0.0, sidewalk_w=[6.0, 6.0], verge_w=[2.0, 2.0], red_line_w=20.0),
        "driveway_main": profile(norms, "driveway_main", [1, 1], lane_w=2.75, sidewalk_w=[1.5, 0.0], verge_w=[0.0, 0.0], red_line_w=10.0),
        "bike_path": profile(norms, "bike_path", [0, 0], lane_w=0.0, median_w=0.0, sidewalk_w=[0.0, 0.0], verge_w=[1.0, 1.0], bike_w=[1.5, 1.5], red_line_w=6.0),
    }

    def pid(s):
        if s["cls"] in ("expressway",):
            return "expressway_cw"
        if s["cls"] in ("arterial_regulated", "local") and s["oneway"]:
            return s["cls"] + "_cw"
        return s["cls"]
    out_nodes = []
    for i, (x, z) in enumerate(nodes):
        on_edge = min(abs(x - BOX[0]), abs(x - BOX[2]), abs(z - BOX[1]), abs(z - BOX[3])) < 1.0
        out_nodes.append({"id": f"n{i}", "x": round(x, 1), "z": round(z, 1), "y": H(x, z), "kind": "joint" if on_edge else ("end" if deg[i] == 1 else "crossing"),
                          "ic": None, "r": None})
    out_segs = []
    ic_id = "ic_a3_z18900"
    for k, s in enumerate(segs):
        a = node_of[2 * k]; b = node_of[2 * k + 1]
        P = list(s["P"]); P[0] = tuple(nodes[a]); P[-1] = tuple(nodes[b])
        if s["kind"] == "cross":
            ys = [round(cross_y(x), 2) for x, z in P]
        elif s["kind"] == "ramp":
            # at the carriageway's height for the 60 m taper, then a straight grade to the cross road's height at the terminal
            off = s["name"].endswith("off")
            ch = U.chain(P); tot = ch[-1]
            x_t, z_t = P[-1] if off else P[0]; y_t = cross_y(x_t)
            dcw = ch if off else tot - ch
            k60 = int(np.argmin(np.abs(dcw - 60.0))); y60 = H(*P[k60])
            ys = [H(x, z) if dc <= 60 else round(y60 + (y_t - y60) * (dc - 60) / max(tot - 60, 1), 2) for dc, (x, z) in zip(dcw, P)]
            ys[-1 if off else 0] = round(y_t, 2)
        else:
            ys = [H(x, z) for x, z in P]
        ch = U.chain(P); struct = []
        cur = None
        for i in range(len(P) - 1):
            mx, mz = (P[i][0] + P[i + 1][0]) / 2, (P[i][1] + P[i + 1][1]) / 2; my = (ys[i] + ys[i + 1]) / 2
            if s["kind"] == "cross" and abs(mx - xa) <= SPAN_HALF:
                kind = "overpass"
            elif my - H(mx, mz) > 0.3:
                kind = "embankment"
            elif my - H(mx, mz) < -0.3:
                kind = "cut"
            else:
                kind = "ground"
            if cur and cur["kind"] == kind:
                cur["to_m"] = round(float(ch[i + 1]), 1)
            else:
                cur = {"from_m": round(float(ch[i]), 1), "to_m": round(float(ch[i + 1]), 1), "kind": kind}; struct.append(cur)
        ic = ic_id if s["kind"] in ("ramp",) or (s["kind"] == "cross" and any(q["kind"] == "overpass" for q in struct)) else None
        out_segs.append({"id": f"s{k}", "a": out_nodes[a]["id"], "b": out_nodes[b]["id"], "class": s["cls"], "pid": pid(s), "oneway": bool(s["oneway"]),
                         "pts": [[round(x, 1), round(z, 1), y] for (x, z), y in zip(P, ys)], "struct": struct, "years": s["years"],
                         "name_ru": s["name"], "street": None, "ic": ic, "source": f"film_stroke:{s['stroke']}" if s["stroke"] >= 0 else "new"})
    # node kinds of the interchange
    for r in ramps:
        seg = next(q for q in out_segs if q["class"] == "ramp" and q["name_ru"] == f"съезд {r['name']}")
        n_cw = seg["a"] if r["off"] else seg["b"]; n_t = seg["b"] if r["off"] else seg["a"]
        for n in out_nodes:
            if n["id"] == n_cw:
                n["kind"] = "diverge" if r["off"] else "merge"; n["ic"] = ic_id
            if n["id"] == n_t:
                n["kind"] = "crossing_signal"; n["ic"] = ic_id; n["y"] = round(cross_y(n["x"]), 2)
    for n in out_nodes:
        if abs(n["z"] - Z0) < 0.5 and xw - 1 <= n["x"] <= xe + 1:
            n["y"] = round(cross_y(n["x"]), 2)
    ramp_ids = [q["id"] for q in out_segs if q["ic"] == ic_id and q["class"] == "ramp"]
    struct_ids = [q["id"] for q in out_segs if q["ic"] == ic_id and q["class"] != "ramp"]
    joints = [{"id": "j" + n["id"][1:], "node": n["id"]} for n in out_nodes if n["kind"] == "joint"]
    net = {"schema": "qtwin.network/1", "district": D_ID, "area": [[BOX[0], BOX[1]], [BOX[2], BOX[1]], [BOX[2], BOX[3]], [BOX[0], BOX[3]]],
           "fixture": True, "made_by": "w45 tools/map/export/fixture_gate_trial.py: film strokes of the twin inside the box + synthetic diamond on A-3",
           "profiles": profiles, "nodes": out_nodes, "segments": out_segs,
           "interchanges": [{"id": ic_id, "template": "diamond", "x": round(xa, 1), "z": Z0, "major": "А-3", "minor": "Путепровод через А-3 (фикстура)",
                             "ramps": ramp_ids, "structures": struct_ids}],
           "joints": joints, "log": [{"what": w, "ids": []} for w in log]}
    # ------------------------------------------------------------ buildings
    rows, _ = U.read_csv_rows(os.path.join(U.TWIN, U.F_CSV))
    xy = np.array([[float(r["x"]), float(r["z"])] for r in rows])
    inside = np.flatnonzero(shapely.contains_xy(area, xy[:, 0], xy[:, 1]))
    aql = U.read_aql_parts(os.path.join(U.TWIN, U.F_AQL))
    want = set(inside.tolist()); hull = collections.defaultdict(list)
    for name, kind, V, T, col, yr, bid in aql:
        m = np.isin(bid, list(want))
        if m.any():
            for b in np.unique(bid[m]):
                vs = V[T[bid == b].ravel()]; hull[int(b)].append(vs[:, [0, 2]])
    new_roads = unary_union([LineString([(p[0], p[1]) for p in q["pts"]]).buffer(14 if q["class"] != "ramp" else 9) for q in out_segs if q["source"] == "new"])
    blds, removed = [], []
    for b in sorted(want):
        r = rows[b]
        pts = np.concatenate(hull[b]) if hull.get(b) else np.array([[xy[b, 0] - 5, xy[b, 1] - 5], [xy[b, 0] + 5, xy[b, 1] + 5]])
        fp = shapely.MultiPoint(pts).convex_hull
        if fp.geom_type != "Polygon":
            fp = fp.buffer(3)
        if fp.intersects(new_roads):
            removed.append(b); continue
        y = int(r["year"])
        blds.append({"id": f"tw{b}", "bid": b, "lot": None, "footprint": [[round(x, 1), round(z, 1)] for x, z in list(fp.exterior.coords)[:-1]],
                     "floors": int(float(r["floors"] or 1)), "height_m": float(r["height_m"] or 0), "base_y": float(r["ground_m"]), "use": r["use"],
                     "kind": r["kind"], "model": None, "source": "existing_osm" if r["source"] == "existing_osm" else "existing_twin", "registry_id": None,
                     "years": [TC.effective_year(y, r["use"], r["source"], s) for s in TC.SCENARIOS], "build_years": None,
                     "gfa_m2": float(r["gfa_m2"] or 0), "homes": None, "jobs": None, "keep_mesh": True})
    # new 9-storey blocks east of A-3, south of the cross road (and the ones replacing what the roads took)
    taken = unary_union([Polygon(b["footprint"]) for b in blds] + [new_roads])
    new_n = 0
    for k in range(40):
        if new_n >= max(10, len(removed)):
            break
        cx = -2000 + (k % 4) * 70; cz = -19000 - (k // 4) * 45
        fp = box(cx - 28, cz - 8, cx + 28, cz + 8)
        if not area.contains(fp) or fp.buffer(6).intersects(taken):
            continue
        taken = taken.union(fp); new_n += 1
        y = 2032 + new_n % 3
        blds.append({"id": f"nb{new_n}", "bid": None, "lot": None, "footprint": [[round(x, 1), round(z, 1)] for x, z in list(fp.exterior.coords)[:-1]],
                     "floors": 9, "height_m": 29.7, "base_y": H(cx, cz), "use": "housing", "kind": "res_mid", "model": "block_9", "source": "model",
                     "registry_id": None, "years": [TC.effective_year(y, "housing", "generated", s) for s in TC.SCENARIOS], "build_years": 2,
                     "gfa_m2": round(fp.area * 9 * 0.85, 1), "homes": int(fp.area * 9 * 0.85 / 60), "jobs": 0, "keep_mesh": False})
    buildings = {"schema": "qtwin.buildings/1", "fixture": True, "buildings": blds, "removed": removed, "solar": []}
    # ------------------------------------------------------------ LRT inside the box, stations from the twin
    routes = U.load_json(os.path.join(U.TWIN, U.F_LRT)); con = U.load_json(os.path.join(U.TWIN, "StreamingAssets/twin/construction.json"))["lrt"]
    lines = []
    for r in routes["routes"]:
        g = r["pts"]; L = LineString([(g[j], g[j + 1]) for j in range(0, len(g), 2)])
        if not L.intersects(area):
            continue
        X = L.intersection(area)
        for q in getattr(X, "geoms", [X]):
            if q.geom_type != "LineString" or q.length < 50:
                continue
            P = [tuple(p) for p in q.coords]
            st = [s for s in con["stations"] if area.contains(Point(s[0], s[1])) and q.distance(Point(s[0], s[1])) < 60]
            lines.append({"id": f"{r['name']}_fixture", "pts": [[round(x, 1), round(z, 1), H(x, z)] for x, z in P],
                          "sections": [{"from_m": 0.0, "to_m": round(q.length, 1), "kind": "ground"}],
                          "stations": [{"id": f"st{k}", "name_ru": f"Станция {k + 1} (фикстура)", "x": s[0], "z": s[1], "chain_m": round(q.project(Point(s[0], s[1])), 1),
                                        "platform_m": 33, "kind": "ground"} for k, s in enumerate(st)],
                          "ends": [{"kind": "terminus", "id": "area_edge"}, {"kind": "terminus", "id": "area_edge"}], "years": [2031, 2030, 2034, 2029]})
    lrt = {"schema": "qtwin.lrt/1", "fixture": True, "lines": lines, "depots": []}
    # ------------------------------------------------------------ features: a parking lot by the new blocks, a plaza without trees
    feats = {"schema": "qtwin.features/1", "fixture": True,
             "parking": [{"id": "pk1", "type": "surface", "cap": 120, "levels": 1, "polygon": [[-1990, -18960], [-1900, -18960], [-1900, -18930], [-1990, -18930]],
                          "lot": None, "years": [2033, 2031, 2035, 2033]}],
             "stops": [], "greens": [], "plazas": [{"id": "pl1", "polygon": [[-2700, -19050], [-2640, -19050], [-2640, -18990], [-2700, -18990]]}],
             "noplant": [{"polygon": [[-2700, -19050], [-2640, -19050], [-2640, -18990], [-2700, -18990]], "why": "площадь (фикстура)", "years": [2031, 2030, 2034, 2029]}]}
    spec = {"district": D_ID, "version": 1, "fixture": True, "area": net["area"], "edge_joints": []}
    for name, obj in (("network", net), ("buildings", buildings), ("lrt", lrt), ("features", feats), ("spec", spec),
                      ("blocks", {"schema": "qtwin.blocks/1", "fixture": True, "blocks": []}), ("lots", {"schema": "qtwin.lots/1", "fixture": True, "lots": []})):
        n = U.write_json(os.path.join(out_dir, name + ".json"), obj)
        print(f"{name}.json {n / 1e3:.0f} kB")
    print("\n".join(log))
    print(f"network: {len(out_nodes)} nodes, {len(out_segs)} segments ({collections.Counter(q['class'] for q in out_segs)}), {len(joints)} joints")
    print(f"buildings: {sum(1 for b in blds if b['bid'] is not None)} kept, {len(removed)} removed, {new_n} new; lrt lines {len(lines)}")
    # ------------------------------------------------------------ picture
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 2, figsize=(22, 10))
    col = {"expressway": "r", "ramp": "m", "arterial_regulated": "b", "district_transport": "darkorange", "local": "0.45", "boulevard": "g",
           "pedestrian_street": "c", "driveway_main": "y", "bike_path": "lime"}
    for ax, lim in ((axs[0], BOX), (axs[1], (xa - 450, Z0 - 420, xa + 450, Z0 + 420))):
        for q in out_segs:
            P = np.array(q["pts"]); ax.plot(P[:, 0], P[:, 1], color=col.get(q["class"], "k"), lw=2.2 if q["class"] in ("ramp", "district_transport") else 1.0)
            if q["oneway"] and ax is axs[1]:
                m = len(P) // 2
                if m + 1 < len(P):
                    ax.annotate("", xy=P[m + 1, :2], xytext=P[m, :2], arrowprops=dict(arrowstyle="->", color=col.get(q["class"], "k")))
        for b in blds:
            Pg = np.array(b["footprint"] + [b["footprint"][0]]); ax.plot(Pg[:, 0], Pg[:, 1], color="tab:green" if b["bid"] is None else "0.7", lw=0.6)
        for n in out_nodes:
            if n["kind"] in ("diverge", "merge", "crossing_signal", "joint"):
                ax.plot(n["x"], n["z"], "o", ms=3, color={"diverge": "m", "merge": "m", "crossing_signal": "k", "joint": "tab:blue"}[n["kind"]])
        ax.set_xlim(lim[0], lim[2]); ax.set_ylim(lim[1], lim[3]); ax.set_aspect("equal"); ax.grid(True, lw=0.3)
    axs[1].set_title("diamond on A-3: overpass x %.0f…%.0f, deck %.1f m (A-3 %.1f m)" % (xa - SPAN_HALF, xa + SPAN_HALF, deck, ya))
    os.makedirs(pic_dir, exist_ok=True); plt.savefig(os.path.join(pic_dir, "gate_trial_fixture.png"), dpi=70, bbox_inches="tight")
    # height profile of the cross road and the ramps
    fig, ax = plt.subplots(figsize=(12, 4))
    for q in out_segs:
        if q["source"] == "new" and q["class"] in ("district_transport", "ramp"):
            P = np.array(q["pts"]); ax.plot(P[:, 0], P[:, 2], lw=1.5, label=f"{q['id']} {q['class']}")
            ax.plot(P[:, 0], [H(x, z) for x, z in P[:, :2]], "k:", lw=0.6)
    ax.axvspan(xa - SPAN_HALF, xa + SPAN_HALF, color="0.9"); ax.set_xlim(xa - 450, xa + 450); ax.grid(True, lw=0.3)
    plt.savefig(os.path.join(pic_dir, "gate_trial_fixture_profile.png"), dpi=70, bbox_inches="tight")


if __name__ == "__main__":
    main()
