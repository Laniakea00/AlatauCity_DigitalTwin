"""At-grade ring junctions of gen_network (w43): roundabout and transport square.

The ring is a counter-clockwise (right-hand traffic) carriageway around the node, split at every arm into oneway arcs,
so the graph has a node where each arm meets the ring and no closed circle. Arms are cut back to the ring centreline
(the part inside is logged). Sizes come from the norms:
* roundabout: inscribed circle diameter roundabouts.icd_m (single_B12 / double / triple by the arms' lanes per
  direction, middle of the band) and the circulating width roundabouts.circulating_width_m (middle of the band);
* square: the large ring of roundabouts.large_ring_dbn at the upper recommended speed (island radius, ring width).
params: icd_m (roundabout) or r_m (ring centreline radius) override the norm.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import geom as G  # noqa: E402
from lib import years as Y  # noqa: E402
from net_core import Way  # noqa: E402


class RingError(Exception):
    pass


def _mid(band):
    return 0.5 * (float(band["min"]) + float(band["max"]))


def ring_size(N, kind, lanes, params=None):
    """(centreline radius, circulating width, lanes on the ring, why)."""
    params = params or {}
    if kind == "square":
        tbl = N.norm("roundabouts.large_ring_dbn")
        v = int(tbl["recommended_kmh"]["max"])
        r_island, width, weave = (float(x) for x in tbl[str(v)])
        lane_w = float(N.norm("roundabouts.lanes_dbn")["lane_m"]["min"])
        n = max(1, int(round(width / lane_w)))
        r = float(params.get("r_m", r_island + width / 2.0))
        return r, width, n, f"roundabouts.large_ring_dbn[{v}]: остров R {r_island:.0f} м, ширина {width} м"
    icd = N.norm("roundabouts.icd_m")
    cw = N.norm("roundabouts.circulating_width_m")
    if lanes <= 1:
        D, width, n, key = _mid(icd["single_B12"]), _mid(cw["single"]), 1, "single_B12"
    elif lanes == 2:
        D, width, n, key = _mid(icd["double"]), _mid(cw["two_lanes"]), 2, "double"
    else:
        D, width, n, key = _mid(icd["triple"]), _mid(cw["three_lanes"]), 3, "triple"
    D = float(params.get("icd_m", D))
    r = float(params.get("r_m", D / 2.0 - width / 2.0))
    return r, width, n, f"roundabouts.icd_m.{key} {D:.1f} м, ширина кольца {width:.2f} м"


def ring(net, ic_id, C, kind, params=None, years=None, name_ru=""):
    """Build a ring at C in the network (before planarize). Returns the interchange record."""
    N = net.N
    C = np.asarray(C, float)
    params = params or {}
    def near(w, d=120.0):           # bounding box first: project() on every way of a district is slow
        b = w.bbox()
        return b[0] - d < C[0] < b[2] + d and b[1] - d < C[1] < b[3] + d and G.project(w.P, C)[1] < d
    arms = [w for w in net.ways if w.role == "primary" and near(w)
            and w.cls not in ("expressway", "ramp", "bike_path", "pedestrian_street", "boulevard")]
    if not arms:
        raise RingError("у кольца нет подходящих улиц")
    def lanes_of(ws):
        return max(max(w.prof["lanes"]) if w.prof else 1 for w in ws)

    # the ring's size and class come from the streets that reach it (not from a road passing nearby)
    r, width, n, why = ring_size(N, kind, lanes_of(arms), params)
    for _ in range(2):
        real = [w for w in arms if G.project(w.P, C)[1] < r] or arms
        r2 = ring_size(N, kind, lanes_of(real), params)
        if abs(r2[0] - r) < 0.01:
            break
        r, width, n, why = r2
    circle = G.arc_pts(C, r, 0.0, 2 * math.pi, step=1.0)
    best = min(real, key=lambda w: N.class_rank(w.cls))
    cls = best.cls
    cuts = []                      # (angle, point)
    removed = []
    for w in list(arms):
        if G.project(w.P, C)[1] >= r:
            continue               # passes outside the ring
        xs = sorted(G.crossings(w.P, circle), key=lambda c: c[0])
        d0 = float(np.hypot(*(w.P[0] - C)))
        d1 = float(np.hypot(*(w.P[-1] - C)))
        inside0, inside1 = d0 < r, d1 < r
        ss = []
        for c in xs:                # the circle's closing vertex can give one crossing twice
            if not ss or c[0] - ss[-1] > 1e-3:
                ss.append(c[0])
        # chainage intervals inside the circle
        bounds = ([0.0] if inside0 else []) + ss + ([w.L] if inside1 else [])
        if len(bounds) % 2:
            raise RingError(f"улица {w.id} пересекает кольцо неоднозначно")
        spans = [(bounds[i], bounds[i + 1]) for i in range(0, len(bounds), 2)]
        for a, b in sorted(spans, reverse=True):
            for s in (a, b):
                if 0.0 < s < w.L:
                    p = w.at(s)
                    cuts.append((math.atan2(p[1] - C[1], p[0] - C[0]), p))
            pieces = net.carve(w, a, b)
            removed.append((w.id, round(b - a, 1)))
            for pc in pieces:
                pc.keep_exact = True
            if not pieces:
                break
            w = pieces[0]
    if len(cuts) < 3:
        raise RingError(f"к кольцу подходит {len(cuts)} луча (нужно ≥ 3)")
    cuts.sort(key=lambda c: c[0])
    # merge points closer than 3 m (one arm) — keep the first
    pts = []
    for a, p in cuts:
        if pts and np.hypot(*(p - pts[-1][1])) < 3.0:
            continue
        pts.append((a, p))
    prof = N.profile(cls, {"lanes": [n, 0], "lane_w": round(width / n, 2), "oneway": True, "median_w": 0.0,
                           "carriageways": 1, "sidewalk_w": [0.0, best.prof["sidewalk_w"][1] if best.prof else 0.0],
                           "verge_w": [0.0, 0.0], "bike_w": [0.0, 0.0], "parking_w": [0.0, 0.0],
                           "shoulder_w": [0.0, 0.0]})
    pid = f"{cls}+{kind}{n}x{width / n:.2f}"
    # the ring is built with its first new arm (an existing road alone does not bring a new ring)
    new_arms = [w.years for w in real if w.source != "osm" and not str(w.source).startswith("osm:")]
    yrs = years or (Y.earliest(*new_arms) if new_arms else Y.latest(*[w.years for w in real]))
    ring_ways = []
    for i, (a0, p0) in enumerate(pts):
        a1, p1 = pts[(i + 1) % len(pts)]
        sweep = (a1 - a0) % (2 * math.pi)
        arc = G.arc_pts(C, r, a0, sweep, step=2.0)
        arc[0], arc[-1] = p0, p1
        w = Way(cls, arc, oneway=True, prof=prof, pid=pid, years=yrs, name_ru=name_ru, ic=ic_id, source="template",
                role="primary")
        w.keep_exact = True
        w.ring = kind
        net.add(w)
        ring_ways.append(w)
    net.hints = getattr(net, "hints", []) + [(p, kind, ic_id, r) for _, p in pts]
    net.L(f"{'кольцо' if kind == 'roundabout' else 'транспортная площадь'}: участки улиц внутри кольца убраны",
          [i for i, _ in removed], ic=ic_id, removed_m=[m for _, m in removed])
    rec = {"id": ic_id, "template": kind, "x": round(float(C[0]), 1), "z": round(float(C[1]), 1),
           "major": best.street, "minor": None, "params": dict(params, r_m=round(r, 2), width_m=round(width, 2), lanes=n),
           "notes": [f"{kind}: радиус по оси кольца {r:.1f} м, {len(pts)} лучей; {why}"],
           "ramps": [w.id for w in ring_ways]}
    net.ics.append(rec)
    return rec
