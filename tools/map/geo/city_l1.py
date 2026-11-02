"""Level 1 (w42): fixes of the shared city data that the five approved district schemes found. Used by build_city.py.

* partition: bays and gaps that no district covered are given to their neighbour (twin outline rule: the longest shared edge),
  twin buildings that stand a metre outside their own district are taken in, the districts are made one exact coverage
  (shared edges identical, 1 m grid, every polygon valid);
* joints: rebuilt robustly (a crossing needs a real district on each side; a road piece that only ends on a border is not a
  crossing), the level-0 ids are kept where the crossing still exists, the rest go to `retired` with the reason; the duplicate
  BAKAD ring of the twin (T-R002) is replaced by the Overture BAKAD; every crossing of a scheme axis (expressway, trunk,
  arterial, lrt_corridor) with a district or half border gets a joint;
* lrt_schemes: lines and stations of the five specs, with the check that neighbours' lines meet at a joint;
* the new airport (runway line and height zones) and the Iconic move.

Unity frame: X east, Z north, metres."""
import json
import math
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, MultiLineString, Point, Polygon  # noqa: E402
from shapely.ops import nearest_points, substring, unary_union  # noqa: E402

import frames  # noqa: E402
import terrain  # noqa: E402

SPEC_IDS = ["gate", "golden", "growing_w", "growing_e", "green"]
SCHEME_CLASSES = {"expressway": "road", "trunk": "road", "arterial": "road", "lrt_corridor": "lrt"}
FOLLOW_BUF_M = 80.0           # an axis with FOLLOW_SHARE of its length within this distance of a border is that border
FOLLOW_SHARE = 0.5
WIGGLE_M = 400.0              # a scheme axis that leaves a district and comes back within this length runs along the border
JOINT_TOL_M = 150.0            # a scheme axis meets a joint when it crosses the same border within this distance (growing_w used 150 m)
MATCH_OLD_M = 30.0             # a rebuilt crossing keeps the level-0 id of the same line within this distance
GRID_M = 1.0                   # district polygons: coordinates on a 1 m grid
SIMPLIFY_M = 1.0               # coverage simplification tolerance (shared edges stay shared)
ICONIC_NEW = (-3500.0, -19500.0)
AIRPORT_NEW = {"id": "alatau_new", "centre": (-16000.0, 1500.0), "bearing_deg": 95.0, "length_m": 4000.0, "width_m": 45.0,
               "pax_m_per_year": 15, "build_years": [2041, 2045]}
Y0, Y1, AFTER = 2025, 2050, 2099


def years4(open_year, existing=False, not_before=None):
    """[base, fast, slow, infra] for a road or line that opens in `open_year`: the twin's own rule
    (UnityProject/Tools/twin_gen/twin_common.py effective_year, use ≠ housing); existing = 2025 everywhere.
    not_before: no scenario earlier than this year (the new airport: «после 2040» → 2041)."""
    y = int(open_year)
    if existing or y <= Y0:
        return [Y0] * 4
    dy = y - Y0
    fast = max(Y0 + max(1, int(round(dy * 0.75))), not_before or 0)
    slow = Y0 + int(round(dy * 1.3))
    return [y, fast, AFTER if slow > Y1 else slow, y]


def parts(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [q for q in getattr(g, "geoms", []) if q.geom_type == "Polygon" and not q.is_empty]


def one_polygon(g):
    """The main body of g without holes; the crumbs it drops are returned too."""
    ps = sorted(parts(g), key=lambda q: -q.area)
    main = Polygon(ps[0].exterior)
    return main, ps[1:]


def load_specs():
    return {d: json.load(open(os.path.join(frames.SPEC_DIR, d + ".json"), encoding="utf-8")) for d in SPEC_IDS}


# ====================================================================== partition
def partition_fixes(D, city_ref, gp):
    """D: {Gate, Golden, Growing, Green} twin polygons (slivers ≤ 5 m already given). city_ref: the real city outline (genplan
    geojson = OSM county «Алатау»). Returns (D2, rows): bays inside the city that no district covers (mean width 2A/P ≥ 50 m) and
    gaps between two districts up to 50 m wide, each given whole to the neighbour with the longest shared edge."""
    U = unary_union(list(D.values()))
    def nb(g):
        return {k: g.boundary.intersection(D[k].buffer(0.5)).length for k in D}
    cand = [("выемка", g) for g in parts(city_ref.difference(U))
            if g.area >= 1e4 and 2 * g.area / g.length >= 50.0 and sum(v >= 50 for v in nb(g).values()) >= 2]
    taken = unary_union([g for _, g in cand]) if cand else Polygon()
    closed = U.buffer(25, join_style="mitre").buffer(-25, join_style="mitre")
    for g in parts(closed.difference(U).difference(taken)):
        sh = {k: g.boundary.intersection(D[k].buffer(0.5)).length for k in D}
        if g.area >= 1e3 and sum(v >= 50 for v in sh.values()) >= 2:
            cand.append(("щель", g))
    add = {k: [] for k in D}
    rows = []
    for kind, g in cand:
        sh = {k: g.boundary.intersection(D[k].buffer(0.5)).length for k in D}
        k = max(sh, key=sh.get)
        gshare = {n.capitalize(): round(g.intersection(gp[n][0]).area / g.area * 100, 1) for n in ("gate", "golden", "growing", "green")}
        gshare = {n: v for n, v in gshare.items() if v > 0}
        rp = g.representative_point()
        add[k].append(g)
        rows.append({"kind": kind, "area_ha": round(g.area / 1e4, 2), "at": [round(rp.x), round(rp.y)], "to": k,
                     "shared_edge_m": {n: round(v) for n, v in sh.items() if v > 1}, "genplan_share_pct": gshare,
                     "mean_width_m": round(2 * g.area / g.length, 1),
                     "rule": "правило контуров двойника: кусок получает сосед с самой длинной общей границей"})
    D2 = {}
    for k in D:
        if add[k]:
            main, crumbs = one_polygon(unary_union([D[k]] + add[k]))
            D2[k] = main
        else:
            D2[k] = D[k]
    return D2, rows


def building_patches(D2, B):
    """Twin buildings (buildings.csv) whose own district is K but whose point lies just outside every district (≤ 10 m from K):
    K takes a 3 m strip to them. Returns (D3, rows)."""
    U = unary_union(list(D2.values()))
    xs, zs = B.x.values, B.z.values
    out = ~shapely.contains_xy(U, xs, zs)
    add = defaultdict(list)
    rows = []
    for i in np.flatnonzero(out):
        k = B.district.values[i]
        if k not in D2:
            continue
        p = Point(xs[i], zs[i])
        d = D2[k].distance(p)
        if d > 10:
            continue
        q = D2[k].exterior.interpolate(D2[k].exterior.project(p))
        strip = LineString([(q.x, q.y), (p.x, p.y)]).buffer(3.0) if d > 0.01 else p.buffer(3.0)
        others = unary_union([D2[n] for n in D2 if n != k])
        add[k].append(strip.difference(others))
        rows.append({"bid": int(B.bid.values[i]), "district": k, "x": round(float(xs[i]), 1), "z": round(float(zs[i]), 1),
                     "outside_m": round(d, 2)})
    D3 = {}
    for k in D2:
        D3[k] = one_polygon(unary_union([D2[k]] + add[k]))[0] if add[k] else D2[k]
    return D3, rows


def halves_single(gw, ge):
    """Each Growing half one polygon: a crumb of the split goes to the half it shares the longest edge with."""
    W, cw = one_polygon(gw)
    E, ce = one_polygon(ge)
    moved = []
    for c in cw + ce:
        lw = c.boundary.intersection(W.buffer(0.5)).length
        le = c.boundary.intersection(E.buffer(0.5)).length
        if lw >= le:
            W = one_polygon(unary_union([W, c]))[0]
        else:
            E = one_polygon(unary_union([E, c]))[0]
        moved.append({"area_m2": round(c.area, 1), "to": "growing_w" if lw >= le else "growing_e"})
    return W, E, moved


def make_coverage(areas):
    """Node every outline together, cut the plane into faces and give each face to the area that holds it (a face no area or two
    areas hold, i.e. a mismatch of the twin outlines, goes to the area with the longest shared edge). The result shares edges
    exactly. Then simplify the coverage (shared edges stay shared), snap to the 1 m grid and repair any ring the snap broke."""
    keys = list(areas)
    lines = unary_union([areas[k].boundary for k in keys])
    faces = list(shapely.get_parts(shapely.polygonize(list(getattr(lines, "geoms", [lines])))))
    city = unary_union([areas[k] for k in keys])
    got = defaultdict(list)
    loose = 0.0
    for f in faces:
        rp = f.representative_point()
        hold = [k for k in keys if areas[k].contains(rp)]
        if len(hold) == 1:
            got[hold[0]].append(f)
            continue
        if not city.buffer(1.0).contains(f):
            continue
        sh = {k: f.boundary.intersection(areas[k].boundary.buffer(0.05)).length for k in keys}
        k = max(sh, key=sh.get)
        got[k].append(f)
        loose += f.area
    cov = {k: one_polygon(unary_union(got[k]))[0] for k in keys}
    arr = np.array([cov[k] for k in keys], dtype=object)
    valid_before = bool(shapely.coverage_is_valid(arr))
    simp = shapely.coverage_simplify(arr, tolerance=SIMPLIFY_M)
    snapped = shapely.transform(simp, lambda c: np.round(c / GRID_M) * GRID_M)
    res, fixed = {}, []
    for k, g in zip(keys, snapped):
        if not g.is_valid:
            why = shapely.is_valid_reason(g)
            a0 = g.area
            g2 = shapely.make_valid(g, method="structure", keep_collapsed=False)
            main, crumbs = one_polygon(g2)
            fixed.append({"area": k, "reason": why, "area_ha_before": round(a0 / 1e4, 3), "area_ha_after": round(main.area / 1e4, 3),
                          "dropped_m2": round(sum(c.area for c in crumbs), 1)})
            g = main
        res[k] = g
    return res, {"faces": len(faces), "mismatch_faces_m2": round(loose, 1), "coverage_valid_before": valid_before,
                 "coverage_valid_after": bool(shapely.coverage_is_valid(np.array([res[k] for k in keys], dtype=object))),
                 "repaired": fixed}


def coverage_checks(areas, code_ha):
    """Validity, holes and overlaps of the district set, and area against the code (CityStats)."""
    keys = list(areas)
    U = unary_union([areas[k] for k in keys])
    holes = [Polygon(r) for g in parts(U) for r in g.interiors]
    over = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            x = areas[a].intersection(areas[b]).area
            if x > 1.0:
                over.append({"pair": [a, b], "m2": round(x, 1)})
    rows = {k: {"valid": bool(areas[k].is_valid), "type": areas[k].geom_type, "area_ha": round(areas[k].area / 1e4, 1),
                **({"area_code_ha": code_ha[k], "diff_pct": round((areas[k].area / 1e4 / code_ha[k] - 1) * 100, 2)} if k in code_ha else {})}
            for k in keys}
    return {"districts": rows, "union_parts": len(parts(U)), "holes": len(holes), "holes_m2": round(sum(h.area for h in holes), 1),
            "holes_over_0_1ha": sum(1 for h in holes if h.area > 1000), "overlaps": over,
            "overlaps_m2": round(sum(o["m2"] for o in over), 1), "overlaps_over_0_1ha": sum(1 for o in over if o["m2"] > 1000)}


# ====================================================================== joints
def side_fn(areas, eps=0.5):
    names = list(areas)
    bnd = unary_union([areas[n].boundary for n in names])
    shapely.prepare(bnd)
    for n in names:
        shapely.prepare(areas[n])

    def side(x, z):
        for n in names:
            if shapely.contains_xy(areas[n], x, z):
                return n
        if shapely.dwithin(bnd, Point(x, z), eps):
            return "border"
        return "outside"
    return side, bnd


def _probe(ln, s, sgn, side, steps):
    for d in steps:
        t = s + sgn * d
        if t <= 0.0 or t >= ln.length:
            t = min(max(t, 0.0), ln.length)
            if abs(t - s) < 1.0:
                return "end"
            q = ln.interpolate(t)
            v = side(q.x, q.y)
            return "end" if v == "border" else v
        q = ln.interpolate(t)
        v = side(q.x, q.y)
        if v != "border":
            return v
    return "border"


def _tangent(ln, s, h=20.0):
    a = ln.interpolate(max(0.0, s - h)); b = ln.interpolate(min(ln.length, s + h))
    return math.atan2(b.y - a.y, b.x - a.x)


def crossing_angle(ln, s, bnd_parts, p):
    """Angle (0…90°) between line ln at chainage s and the border piece nearest to p."""
    q = min(bnd_parts, key=lambda g: g.distance(p))
    t1 = _tangent(ln, s)
    t2 = _tangent(q, q.project(p))
    d = abs((math.degrees(t1 - t2) + 180.0) % 180.0)
    return min(d, 180.0 - d)


def line_events(ln, bnd, side, along_win=40.0, along_len=30.0, along_buf=4.0, steps=(12, 25, 40, 60), min_angle=None):
    """Where line ln meets the borders. Returns [(Point, side_before, side_after)]; a side is an area name, 'outside',
    'end' (the line ends there) or 'border' (runs on the border). A stretch that runs along a border is skipped: by length near
    the border (twin and OSM lines), or, with min_angle, when the line meets the border at less than min_angle degrees
    (hand-drawn scheme axes that follow a border zig-zag across it)."""
    X = ln.intersection(bnd)
    pts = []
    for g in getattr(X, "geoms", [X]):
        if g.is_empty:
            continue
        if g.geom_type == "Point":
            pts.append(g)
        elif g.geom_type in ("LineString", "MultiLineString"):
            for q in getattr(g, "geoms", [g]):
                pts.extend([Point(q.coords[0]), Point(q.coords[-1])])
    bb = bnd.buffer(along_buf) if min_angle is None else None
    bparts = list(getattr(bnd, "geoms", [bnd])) if min_angle is not None else None
    out = []
    for p in pts:
        s = ln.project(p)
        if min_angle is None:
            local = substring(ln, max(0.0, s - along_win), min(ln.length, s + along_win))
            if local.intersection(bb).length > along_len:
                continue
        elif crossing_angle(ln, s, bparts, p) < min_angle:
            continue
        out.append((p, _probe(ln, s, -1, side, steps), _probe(ln, s, +1, side, steps)))
    # the same place twice (vertex on the border)
    ded = []
    for e in out:
        if not any(e[0].distance(f[0]) < 1.0 for f in ded):
            ded.append(e)
    return ded


AREA_SIDES = set(SPEC_IDS) | {"outside"}


def crossings_of_lines(lines, areas, city_ext):
    """lines: [(kind, id, class, years, LineString)]. Returns joints [{x, z, kind, line, lines, class, between, years}] and the
    internal touches that are no crossing (a piece that ends on a border with nothing on the other side)."""
    side, bnd = side_fn(areas)
    cross, touch = [], []
    for kind, lid, cls, years, ln in lines:
        for p, a, b in line_events(ln, bnd, side):
            if a in AREA_SIDES and b in AREA_SIDES:
                if a != b:
                    cross.append({"p": p, "kind": kind, "lines": [lid], "class": cls, "years": years, "between": sorted([a, b])})
            elif (a in AREA_SIDES) != (b in AREA_SIDES):
                touch.append({"p": p, "kind": kind, "line": lid, "class": cls, "years": years, "side": a if a in AREA_SIDES else b})
    # touches at one point from both sides make one crossing; one side only: at the city edge = the road leaves the city
    used = [False] * len(touch)
    dropped = []
    for i, t in enumerate(touch):
        if used[i]:
            continue
        grp = [j for j in range(len(touch)) if not used[j] and touch[j]["kind"] == t["kind"] and touch[j]["p"].distance(t["p"]) <= 3.0]
        for j in grp:
            used[j] = True
        sides = sorted(set(touch[j]["side"] for j in grp))
        x = float(np.mean([touch[j]["p"].x for j in grp])); z = float(np.mean([touch[j]["p"].y for j in grp]))
        base = {"p": Point(x, z), "kind": t["kind"], "lines": sorted(set(touch[j]["line"] for j in grp)), "class": t["class"], "years": t["years"]}
        if len(sides) >= 2:
            for a in range(len(sides)):
                for b in range(a + 1, len(sides)):
                    cross.append({**base, "between": [sides[a], sides[b]], "from_touch": True})
        elif sides and sides[0] != "outside" and city_ext.distance(base["p"]) <= 3.0:
            cross.append({**base, "between": sorted([sides[0], "outside"]), "from_touch": True})
        else:
            dropped.append({**base, "side": sides[0] if sides else None})
    # the same crossing of the same line found twice
    ded = []
    for c in cross:
        if any(c["p"].distance(d["p"]) < 15 and c["between"] == d["between"] and set(c["lines"]) & set(d["lines"]) for d in ded):
            continue
        ded.append(c)
    return ded, dropped


def match_old(new, old, tol=MATCH_OLD_M):
    """One-to-one match of rebuilt crossings to level-0 joints on the same line (nearest first). Returns {new index: old id} and
    {old id: new index} for old joints that duplicate a matched crossing of the same line."""
    pairs = []
    for i, n in enumerate(new):
        for o in old:
            if o["kind"] != n["kind"] or o["line"] not in n["lines"]:
                continue
            d = math.hypot(o["x"] - n["p"].x, o["z"] - n["p"].y)
            if d <= tol:
                pairs.append((d, i, o["id"]))
    pairs.sort()
    n2o, taken = {}, set()
    for d, i, oid in pairs:
        if i in n2o or oid in taken:
            continue
        n2o[i] = oid
        taken.add(oid)
    dup = {}
    for d, i, oid in pairs:
        if oid not in taken and oid not in dup:
            dup[oid] = i
    return n2o, dup


_shared = {}


def shared_border(areas, city_ext, pair):
    """The border line between the two areas of pair (or an area and the outside)."""
    if pair in _shared:
        return _shared[pair]
    a, b = pair
    if b == "outside" or a == "outside":
        k = a if b == "outside" else b
        g = areas[k].exterior.intersection(city_ext.buffer(0.5))
    else:
        g = areas[a].exterior.intersection(areas[b].exterior.buffer(0.5))
    _shared[pair] = None if g.is_empty else g
    return _shared[pair]


def scheme_events(specs, areas, city_ext):
    """Every place where a scheme axis of class expressway/trunk/arterial/lrt_corridor or a scheme LRT line meets a border:
    real crossings, and axis ends within 60 m of a border (the street stops at the border, e.g. at an A-3 interchange).
    A stretch that runs along a border (A-3 on the Growing split, a corridor along the city edge) is skipped."""
    side, bnd = side_fn(areas)
    ev = []
    wiggles = []

    def add_line(d, aid, cls, kind, yrs, pts, why):
        ln = LineString(pts)
        if ln.length < 1:
            return
        cr = []
        for p, a, b in line_events(ln, bnd, side, steps=(30, 60, 100), min_angle=20.0):
            if a in AREA_SIDES and b in AREA_SIDES and a != b:
                cr.append({"p": p, "s": ln.project(p), "spec": d, "axis": aid, "class": cls, "kind": kind, "years": yrs, "between": sorted([a, b]),
                           "how": "crossing", "why": why})
        # an axis that is itself the border (A-3 on the Growing split, a road along the city edge): no crossing of that border
        for pair in sorted(set(tuple(e["between"]) for e in cr)):
            sh = shared_border(areas, city_ext, pair)
            if sh is not None and ln.intersection(sh.buffer(FOLLOW_BUF_M)).length >= FOLLOW_SHARE * ln.length:
                for e in cr:
                    if tuple(e["between"]) == pair:
                        e["follows_border"] = True
        wiggles.extend(e for e in cr if e.get("follows_border"))
        cr = [e for e in cr if not e.get("follows_border")]
        # a hand-drawn axis that follows a border wanders across it: out and back within WIGGLE_M is no crossing
        cr.sort(key=lambda e: e["s"])
        drop = set()
        for i in range(len(cr) - 1):
            if cr[i]["between"] == cr[i + 1]["between"] and cr[i + 1]["s"] - cr[i]["s"] < WIGGLE_M:
                drop.update((i, i + 1))
        wiggles.extend(cr[i] for i in sorted(drop))
        ev.extend(e for i, e in enumerate(cr) if i not in drop)
        for end, s_end, sgn in ((Point(pts[0]), 0.0, +1), (Point(pts[-1]), ln.length, -1)):
            s0 = side(end.x, end.y)
            if s0 not in SPEC_IDS:             # the end sits on the border: its district is the one the line comes from
                s0 = _probe(ln, s_end, sgn, side, (5, 15, 30, 60))
            if s0 not in SPEC_IDS:
                continue
            dist = bnd.distance(end)
            if dist > 60.0:
                continue
            q = nearest_points(bnd, end)[0]
            # the other side: a point just beyond the border along the line's own direction
            far = None
            for n in SPEC_IDS:
                if n != s0 and areas[n].distance(end) <= dist + 5.0:
                    far = n
                    break
            if far is None:
                far = "outside" if city_ext.distance(end) <= dist + 5.0 else None
            if far is None:
                continue
            if any(e["spec"] == d and e["axis"] == aid and e["p"].distance(q) < JOINT_TOL_M for e in ev):
                continue
            ev.append({"p": Point(q.x, q.y), "spec": d, "axis": aid, "class": cls, "kind": kind, "years": yrs, "between": sorted([s0, far]),
                       "how": "end_%dm" % round(dist), "why": why})

    for d, s in specs.items():
        for a in s.get("axes", []):
            kind = SCHEME_CLASSES.get(a["class"])
            if not kind:
                continue
            ln = a["line"]
            segs = ln if ln and isinstance(ln[0][0], list) else [ln]
            existing = a.get("status", "").startswith("keep") and a.get("years", [Y0])[-1] <= Y0
            yrs = years4(a.get("years", [Y0])[-1], existing)
            for seg in segs:
                add_line(d, a["id"], a["class"], kind, yrs, seg, "axis")
        L = s.get("lrt") or {}
        lyrs = L.get("years")
        for key in ("line", "west_branch"):
            if L.get(key):
                add_line(d, "lrt." + key, "lrt", "lrt", years4(lyrs[-1]) if lyrs else None, L[key], "lrt")
    for e in wiggles:
        e["wiggle"] = True
    return ev, wiggles


def kind_ok(joint_kind, ev_kind):
    return joint_kind == ev_kind or (ev_kind == "lrt" and joint_kind == "rail")


def attach_scheme(joints, events, next_id):
    """Each scheme event meets the nearest joint of the same border pair and a fitting kind within JOINT_TOL_M; an event with
    no joint makes one. Returns (joints, report)."""
    made = 0
    attached = 0
    for e in sorted(events, key=lambda e: (e["between"], e["kind"], -e["p"].y, e["p"].x)):
        best = None
        for j in joints:
            if j["between"] != e["between"] or not kind_ok(j["kind"], e["kind"]):
                continue
            dd = math.hypot(j["x"] - e["p"].x, j["z"] - e["p"].y)
            key = (0 if j["kind"] == e["kind"] else 1, dd)
            if dd <= JOINT_TOL_M and (best is None or key < best[0]):
                best = (key, j)
        ref = {"spec": e["spec"], "axis": e["axis"], "how": e["how"], "_p": (e["p"].x, e["p"].y)}
        if best is not None:
            best[1].setdefault("axes", []).append({**ref, "dist_m": round(best[0][1], 1)})
            attached += 1
            continue
        j = {"x": round(e["p"].x, 1), "z": round(e["p"].y, 1), "kind": e["kind"], "line": "%s:%s" % (e["spec"], e["axis"]),
             "class": e["class"], "between": e["between"], "years": e["years"], "source": "scheme_axis",
             "axes": [{**ref, "dist_m": 0.0}], "new_l1": True}
        joints.append(j)
        made += 1
    return joints, {"events": len(events), "met_existing_joint": attached, "new_joints": made}


# ====================================================================== LRT of the schemes
def lrt_schemes(specs, joints, areas, out_layer):
    """Lines and stations of the five specs (pointers into the specs + one merged layer) and, at every LRT joint, whether the
    lines of both neighbours reach it."""
    import layers
    feats, props, routes = [], [], []
    lines_by_spec = {}
    for d, s in specs.items():
        L = s.get("lrt") or {}
        for key in ("line", "west_branch"):
            if not L.get(key):
                continue
            ln = LineString(L[key])
            lid = "%s.lrt.%s" % (d, key)
            lines_by_spec.setdefault(d, []).append((lid, ln))
            yrs = L.get("years")
            feats.append(ln)
            props.append({"id": lid, "district": d, "kind": "line", "len_km": round(ln.length / 1000, 2), "years_build": yrs,
                          "pointer": "tools/map/spec/%s.json#lrt/%s" % (d, key), "source": "схема района %s (уровень 0, утверждена 31.10)" % d})
            routes.append({"id": lid, "district": d, "pointer": "%s.json#lrt/%s" % (d, key), "len_km": round(ln.length / 1000, 2),
                           "from": [round(c) for c in ln.coords[0]], "to": [round(c) for c in ln.coords[-1]], "build_years": yrs})
        for a in s.get("axes", []):
            if a["class"] == "lrt_corridor" and "metro" not in a["id"]:
                ln = LineString(a["line"])
                lines_by_spec.setdefault(d, []).append(("%s.axes.%s" % (d, a["id"]), ln))
    stations = []
    for d, s in specs.items():
        for st in (s.get("lrt") or {}).get("stations", []):
            inside = areas[d].contains(Point(st["x"], st["z"]))
            row = {"id": "%s.%s" % (d, st["id"]), "district": d, "name_ru": st.get("name_ru"), "x": st["x"], "z": st["z"], "in_own_district": bool(inside)}
            stations.append(row)
            feats.append(Point(st["x"], st["z"]))
            props.append({"id": row["id"], "district": d, "kind": "station", "name_ru": st.get("name_ru"), "pointer": "tools/map/spec/%s.json#lrt/stations" % d})
    # duplicate stations on a shared border: the same place in two specs
    for i, a in enumerate(stations):
        for b in stations[i + 1:]:
            if a["district"] != b["district"] and math.hypot(a["x"] - b["x"], a["z"] - b["z"]) < 300:
                a.setdefault("same_as", []).append(b["id"])
    meets = []
    for j in joints:
        if j["kind"] != "lrt":
            continue
        row = {"joint": j["id"], "between": j["between"], "x": j["x"], "z": j["z"]}
        ok = True
        for d in j["between"]:
            if d == "outside":
                continue
            ls = lines_by_spec.get(d, [])
            dist = min((ln.distance(Point(j["x"], j["z"])) for _, ln in ls), default=None)
            row["dist_m_" + d] = None if dist is None else round(dist, 1)
            if dist is None or dist > 50.0:
                ok = False
        row["meet"] = ok
        if not ok:
            row["note_ru"] = "линии ЛРТ соседей не сходятся в этом стыке (дальше 50 м)"
        meets.append(row)
    # line ends that sit on a border without a joint
    side, bnd = side_fn(areas)
    ends = []
    for d, ls in lines_by_spec.items():
        for lid, ln in ls:
            for end in (Point(ln.coords[0]), Point(ln.coords[-1])):
                if bnd.distance(end) <= 60.0:
                    jd = min((math.hypot(j["x"] - end.x, j["z"] - end.y) for j in joints if j["kind"] in ("lrt", "rail")), default=1e9)
                    ends.append({"line": lid, "end": [round(end.x), round(end.y)], "nearest_lrt_joint_m": round(jd, 1), "ok": jd <= 50.0})
    layers.write(out_layer, feats, props, {"what": "ЛРТ пяти утверждённых схем районов (уровень 0): линии и станции", "source": "tools/map/spec/<district>.json#lrt"})
    return {"routes": routes, "stations": stations, "joints": meets, "line_ends_on_borders": ends,
            "not_meeting": [m for m in meets if not m["meet"]] + [e for e in ends if not e["ok"]]}


# ====================================================================== airport and Iconic
def airport_runway():
    a = AIRPORT_NEW
    cx, cz = a["centre"]
    b = math.radians(a["bearing_deg"])
    dx, dz = math.sin(b) * a["length_m"] / 2, math.cos(b) * a["length_m"] / 2
    return [[round(cx - dx, 1), round(cz - dz, 1)], [round(cx + dx, 1), round(cz + dz, 1)]]


def iconic_block(old_block):
    """city.json#iconic after the owner's approval of 31.10: the new place, the old one under `before`, `stale` kept."""
    x, z = ICONIC_NEW
    T = terrain.terrain()
    blk = {"x": x, "z": z, "yaw": 270,
           "source": "решение владельца 31.10.2026 (страница схем уровня 0): Iconic → (−3500, −19500), yaw 270, вместе со всем кварталом Gate District; "
                     "tools/map/CONTRACT.md §7; tools/map/spec/gate.json objects «iconic_complex»",
           "delta_from_before": [round(x - old_block["x"], 1), round(z - old_block["z"], 1)],
           "before": {k: old_block[k] for k in ("x", "z", "yaw", "source")},
           "used_by": old_block.get("used_by"),
           "stale": old_block.get("stale"),
           "twin_ground_m": round(float(T.height(x, z)), 1)}
    return blk
