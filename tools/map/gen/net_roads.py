"""Roads as Ways: a divided road becomes two oneway carriageways (right-hand traffic), an undivided one a single Way;
plus the glue that puts a template Result into a Network (gen_network, w43)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import geom as G  # noqa: E402
from net_core import Way  # noqa: E402
from net_templates import Road  # noqa: E402


def pid_of(cls, prof, form):
    """Profile id: the class, '/cw' for one carriageway of a divided road, '+<hash>' for overrides."""
    base = cls + ("/cw" if form == "cw" else "")
    return base if not prof.get("_override") else f"{base}+{prof['_override']}"


def carriageway_profile(prof):
    """Profile of ONE carriageway of a divided road (lanes [n, 0]; sidewalk / verge / bike on the outer side = right)."""
    p = dict(prof)
    n = max(prof["lanes"])
    p["lanes"] = [n, 0]
    p["sidewalk_w"] = [0.0, prof["sidewalk_w"][1]]
    p["verge_w"] = [0.0, prof["verge_w"][1]]
    p["bike_w"] = [0.0, prof["bike_w"][1]]
    p["parking_w"] = [0.0, prof["parking_w"][1]]
    p["form"] = "carriageway"
    return p


def make_road(N, cls, axis, *, overrides=None, years=None, name_ru="", street=None, source="new", role="primary",
              id_prefix=None):
    """(Road, [Ways]) for a road along `axis` (polyline). Divided classes give two oneway Ways drawn in their direction
    of travel at ± cw_offset; others one two-way Way on the axis."""
    prof = N.profile(cls, overrides)
    if overrides:
        import hashlib
        prof["_override"] = hashlib.md5(repr(sorted(overrides.items())).encode()).hexdigest()[:6]
    axis = G.densify(G.dedup(axis), 5.0)
    ways = []
    if prof["carriageways"] == 2 and not prof.get("oneway"):
        e = prof["cw_offset"]
        cp = carriageway_profile(prof)
        fwd = G.offset(axis, e)                 # travels along the axis direction, on its right
        bwd = G.offset(axis, -e)[::-1].copy()   # travels against it, on the left of the axis
        wf = Way(cls, fwd, oneway=True, prof=cp, pid=pid_of(cls, prof, "cw"), years=years, name_ru=name_ru,
                 street=street, source=source, role=role, id=(id_prefix + "+") if id_prefix else None)
        wb = Way(cls, bwd, oneway=True, prof=cp, pid=pid_of(cls, prof, "cw"), years=years, name_ru=name_ru,
                 street=street, source=source, role=role, id=(id_prefix + "-") if id_prefix else None)
        wf.axis_prof = wb.axis_prof = prof
        ways = [wf, wb]
        road = Road(cls, prof, axis, {+1: wf, -1: wb}, name_ru, years, street)
    else:
        w = Way(cls, axis, oneway=bool(prof.get("oneway")), prof=prof, pid=pid_of(cls, prof, "road"), years=years,
                name_ru=name_ru, street=street, source=source, role=role, id=id_prefix)
        w.axis_prof = prof
        ways = [w]
        road = Road(cls, prof, axis, {0: w}, name_ru, years, street)
    return road, ways


def road_from_ways(N, cls, ways_pm, axis=None, name_ru="", years=None, street=None):
    """Road object for existing carriageways (e.g. two OSM motorway ways): ways_pm = {+1: w, -1: w} or {0: w}."""
    prof = N.profile(cls)
    if axis is None:
        if 0 in ways_pm:
            axis = ways_pm[0].P
        else:
            a, b = ways_pm[+1].P, ways_pm[-1].P[::-1]
            n = 200
            sa = np.linspace(0, G.length(a), n)
            sb = np.linspace(0, G.length(b), n)
            pa = np.array([G.point_at(a, s) for s in sa])
            pb = np.array([G.project(b, p)[2] for p in pa])
            axis = (pa + pb) / 2.0
            e = float(np.median(np.hypot(*(pa - pb).T))) / 2.0
            prof = dict(prof)
            prof["cw_offset"] = e
    return Road(cls, prof, axis, ways_pm, name_ru, years, street)


def apply_result(net, res):
    """Put a template Result into the network: ramps, lifts, node hints, cuts."""
    real = set(id(w) for w in net.ways)
    for w in res.ramps:
        # a parent that is a virtual carriageway (OSM pieces chained): take the real piece next to the ramp
        ps = []
        for p in getattr(w, "parents", []) or []:
            if p is not None and id(p) not in real and getattr(p, "pieces", None):
                p = min(p.pieces, key=lambda q: min(G.project(q.P, w.P[0])[1], G.project(q.P, w.P[-1])[1]))
            ps.append(p)
        w.parents = ps
        w.parent = ps[0] if ps else None
        w.prof = w.prof or net.N.profile("ramp")
        if getattr(w, "lane_w", None):
            w.prof = net.N.profile("ramp", {"lane_w": float(w.lane_w)}) if w.lane_w != w.prof["lane_w"] else w.prof
        w.pid = "ramp" if w.prof["lane_w"] == net.N.profile("ramp")["lane_w"] else f"ramp+{w.prof['lane_w']:.1f}"
        net.add(w)
    real |= set(id(w) for w in res.ramps)          # the template's own ramps take their lifts as they are
    for way, s0, s1, why in res.lifted:
        if id(way) in real:
            way.lifts.append((float(s0), float(s1), why))
            continue
        # a virtual chain: the lift goes onto each real piece it overlaps
        pa, pb = way.at(max(0.0, s0)), way.at(min(way.L, s1))
        for q in getattr(way, "pieces", []):
            a_, da, _ = G.project(q.P, pa)
            b_, db, _ = G.project(q.P, pb)
            lo_, hi_ = (0.0 if da > 1.0 else min(a_, b_)), (q.L if db > 1.0 else max(a_, b_))
            if da > 1.0 and db > 1.0:
                # both ends off this piece: lifted over its whole length only if the piece lies inside the span
                m = G.project(way.P, q.at(q.L / 2))[0]
                if not (s0 <= m <= s1):
                    continue
            if hi_ - lo_ > 0.5:
                q.lifts.append((lo_, hi_, why))
    net.hints = getattr(net, "hints", []) + [(p, k, res.id) for p, k in res.hints]
    cut = getattr(res, "cut_minor", None)
    if cut:
        for w in cut["ways"]:
            s, _, _ = G.project(w.P, cut["point"])
            sc = G.project(w.P, cut["C"])[0]
            sub = G.cut(w.P, s, w.L) if sc < s else G.cut(w.P, 0, s)
            net.L("стебель трубы укорочен до точки разделения на два направления", [w.id], ic=res.id,
                  removed_m=round(w.L - G.length(sub), 1))
            w.P = sub
            w.refresh()
            w.keep_exact = True
    rec = res.record()
    rec["ramps"] = [w.id for w in res.ramps]
    net.ics.append(rec)
    return rec


def assign_hints(net, tol=0.6):
    """After planarize: node kinds from the template hints (diverge, merge, crossing_signal…) and their interchange."""
    from scipy.spatial import cKDTree
    if not getattr(net, "hints", None) or not net.nodes:
        return
    P = np.array([n.p for n in net.nodes])
    tree = cKDTree(P)
    for h in net.hints:
        p, k, icid = h[:3]
        d, i = tree.query(p)
        if d <= tol:
            n = net.nodes[i]
            if n.kind in (None, "ic") or (n.kind in ("diverge", "merge") and k == "crossing_signal") \
                    or k in ("roundabout", "square"):
                n.kind = k
            if len(h) > 3:
                n.r = round(float(h[3]), 2)
            n.ic = n.ic or icid
