"""Driveways and fire lanes inside blocks (w44): python3 tools/map/gen/land_driveways.py <district> [--out OUT] [--spec S]
(also called at the end of gen_buildings.py).

Reads   OUT/<d>/network.json, blocks.json, lots.json, buildings.json, lrt.json; norms.json (fire_access.*,
        setbacks.building_line_max_m, street_profiles.driveway_main).
Writes  OUT/<d>/driveways.json in the network format of CONTRACT §4: {schema:"qtwin.network/1", kind:"driveways", profiles,
        nodes:[{id,x,z,y,kind,ic,r, attach?:{segment,x,z}, turnaround?:{w_m,l_m}}], segments:[{id,a,b,class,pid,oneway,pts,
        struct,years,name_ru,street,ic, serves:[building ids], role:"access"|"fire"|"ring"|"link"}], pads:[{node,polygon,years}], log}.

Per block, one shortest-path tree on a grid of the block's free land (cells clear of every building by half the driveway's
red line) from the bordering streets (not expressways, ramps or continuous arterials) to each new building that a street does
not already serve. Every distance is measured as the validator (rule 12) measures it: from the wall to the nearest
carriageway polygon of a street or a drive (flat caps).
 * every building: a drive of class driveway_main (≥ fire_access.width_min_m) within setbacks.building_line_max_m (25 m);
 * buildings over 28 m (fire_access.distance_to_wall_m "building_over_28m"): the carriageway edge 8–10 m from the wall. The
   router aims at the cells where a drive along the wall has its edge in the band; when the drive ends facing the wall (its
   flat end, not its side, comes nearest), a straight stub carries it on to the band;
 * ring access (fire_access.ring_required: the fire classes of land_util.FIRE_CLASS, residential and other buildings over
   the norm heights): a loop at the norm distance from the walls, cut where other buildings stand; each piece is linked to
   the tree at both ends by grid routes that keep off the piece's own track (a closed piece at one point);
 * dead ends: a turnaround pad of fire_access.turnaround_min_m along the dead-end piece (a square shifted along and across the
   drive, or a hammerhead T / L, turned along the drive or the nearby walls) within PAD_BACK_MAX of the end; where none fits
   or the piece is longer than fire_access.dead_end_max_m, a loop through the yard from the dead end on to a street or
   another drive; each street connection is a node with attach {segment, x, z}.
 * street pieces off grade (land_util.offgrade: over land_util.OFFGRADE_MIN above or below the terrain by the network heights —
   landings and ramps of footbridges, embankments, cuts, spans with less than fire_access.arches.height_min_m beneath) are
   obstacles with their side slopes, like buildings and the LRT ground corridor: no drive crosses them, roots on them or ties
   to the street across them; a drive attaches only where its street is at grade, and may pass under a span with the clearance.
Years: a drive opens with the first building it serves, never before its street (every scenario)."""
import math
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from scipy.sparse import coo_matrix  # noqa: E402
from scipy.sparse.csgraph import dijkstra  # noqa: E402
from shapely.geometry import LineString, MultiLineString, Point  # noqa: E402
from shapely.ops import linemerge, nearest_points, substring, unary_union  # noqa: E402

import land_util as U  # noqa: E402

CELL = 2.0          # grid step of the router (m): a model parameter, finer than the 2 m band of the 8–10 m fire lane
TIGHT_COST = 4.0    # cost factor of a drive squeezed between buildings without its sidewalks: a model parameter
SNAP = 0.6          # a loose drive end this close to another drive joins it (m)
GRID = 0.05         # noding precision of the drive lines (m)
EDGE_MARGIN = 0.5   # the router keeps this far inside the far limit of a distance band: room for the output simplification (m)
STUB_STEP = 1.0     # step of a straight stub on from a drive end towards the band (m): a model parameter
ALT_TRIES = 12      # other band cells tried when a drive leaves a wall short of its band: a model parameter
ALT_SPACING = 3 * CELL  # those cells stand at least this far apart (m): three grid cells, a model parameter
ZONE_COST = 4.0     # cost factor of a drive nearer a tall building's wall than its fire band: a model parameter
SIMPLIFY = 0.4      # simplification tolerance of the output drive lines (m), below EDGE_MARGIN
PAD_BACK_MAX = 40.0  # farthest a fire engine backs from a dead end to its turnaround pad along the drive (m): a model parameter
BAND_TOL = 0.05     # rounding of the drawn carriageway edges when a distance band is checked (m), as rule 12 takes it
PAD_OFF_USES = ("park", "square", "playground", "transit")   # lot uses a turnaround pad keeps off while it fits elsewhere (model qTwin)
PAD_AHEAD_MAX = 20.0  # farthest a dead end is carried on ahead to open ground for its pad when none fits back along it (m) — модель qTwin
PAD_CLEAR = 0.5     # clearance of a turnaround pad from walls and the LRT corridor (m): a model parameter
TIE_CLEAR_M = 0.25  # a root cell's straight tie to the street keeps its carriageway this far off walls (m): модель qTwin
TIE_NEAR_M = 60.0   # walls looked at for those ties: within this of the block (m), past the street's own width — модель qTwin
PAD_STEP = 1.5      # step of the pad shifts along and across the drive (m): a model parameter
LOOP_MAX = 200.0    # longest new drive that turns a dead end into a loop through the yard (m): a model parameter
DEAD_END_PASSES = 3  # rounds of the dead-end treatment per block (a loop can change the next round's dead ends)


def _over_m(k):
    import re
    m = re.search(r"over_(\d+)m", k)
    return float(m.group(1)) if m else None


def _range_m(k):
    """(10.0, 28.0) from «building_10_28m»; None for a key without a height range."""
    import re
    m = re.search(r"(\d+)_(\d+)m", k)
    return (float(m.group(1)), float(m.group(2))) if m else None


def fire_params(norms):
    dw = norms.v("fire_access.distance_to_wall_m")
    hi_key = next(k for k in dw if _over_m(k))
    mid_key = next(k for k in dw if k != hi_key and isinstance(dw[k], dict))
    rr = norms.v("fire_access.ring_required")
    return {"hi_h": _over_m(hi_key), "hi": (dw[hi_key]["min"], dw[hi_key]["max"]), "mid": (dw[mid_key]["min"], dw[mid_key]["max"]),
            "mid_h": _range_m(mid_key) or (0.0, _over_m(hi_key)),
            "lim": norms.v("setbacks.building_line_max_m", "max_from_carriageway"), "width": norms.v("fire_access.width_min_m", "default"),
            "ring_res": rr["residential_over_m"], "ring_other": rr["other_over_m"], "turn": norms.v("fire_access.turnaround_min_m"),
            "dead_end_max": norms.v("fire_access.dead_end_max_m")}


def needs(b, lot_use, F, norms):
    """(edge distance band (lo, hi) of the drive from the wall, ring?) for a building: over 28 m the band of
    fire_access.distance_to_wall_m building_over_28m, else that of building_10_28m (5–8 m). A drive of a building's own and
    the fire ring of a school or kindergarten run in it, not anywhere within the building-line limit."""
    h = b["height_m"]
    ring = U.ring_required(norms, lot_use, b["use"], h)
    if h > F["hi_h"]:
        return F["hi"], ring
    return F["mid"], ring


def key(c):
    """Node key of a drive point: the noding grid."""
    return (round(round(c[0] / GRID) * GRID, 2), round(round(c[1] / GRID) * GRID, 2))


def _rect(a0, a1, b0, b1):
    return [(a0, b0), (a1, b0), (a1, b1), (a0, b1), (a0, b0)]


def _offsets(m):
    return sorted(np.arange(-m, m + 1e-6, PAD_STEP).tolist() if m > 0 else [0.0], key=lambda x: (abs(x), x))


def pad_shapes(turn, w):
    """Turnaround shapes in drive coordinates (a along the drive towards the dead end, b across): (squares, hammerheads).
    Squares tl×tw shifted so the drive's carriageway stays inside; hammerheads: a crossbar tl long and w wide across the drive
    (shifted across: a T in the middle, an L at the ends) and a stem of tw along it, backwards or forwards. Each shape's
    minimum rotated rectangle is tl×tw."""
    tw, tl = sorted(turn)
    sq = [_rect(a - tl / 2, a + tl / 2, b - tw / 2, b + tw / 2) for a in _offsets(tl / 2 - w / 2) for b in _offsets(tw / 2 - w / 2)]
    hh = []
    for b0 in _offsets(tl / 2 - w / 2):
        t = [(w / 2, b0 - tl / 2), (w / 2, b0 + tl / 2), (-w / 2, b0 + tl / 2), (-w / 2, w / 2), (-(tw - w / 2), w / 2),
             (-(tw - w / 2), -w / 2), (-w / 2, -w / 2), (-w / 2, b0 - tl / 2), (w / 2, b0 - tl / 2)]
        hh.append(t)
        hh.append([(-a, b) for a, b in t])
    return np.array(sq, dtype=float), np.array(hh, dtype=float)


def find_pad(ch, turn, w, obst, area=None):
    """A turnaround pad for the dead-end piece ch (a line that starts at the dead end): going back from the end every CELL m
    up to PAD_BACK_MAX, the first shape of pad_shapes, turned along the drive or along the walls nearby, that keeps PAD_CLEAR
    off obst and stays inside area. None if nothing fits."""
    sq, hh = pad_shapes(turn, w)
    L = ch.length
    ob = U.clean(unary_union(obst).buffer(PAD_CLEAR)) if obst else None
    if ob is not None and not ob.is_empty:
        shapely.prepare(ob)
    else:
        ob = None
    ar = area.buffer(0.25) if area is not None else None
    if ar is not None:
        shapely.prepare(ar)
    wall_angs = []
    for q in obst:
        a = U.axis(q)[0] % (math.pi / 2)
        if all(min(abs(a - x), math.pi / 2 - abs(a - x)) > math.radians(2.0) for x in wall_angs):
            wall_angs.append(a)
    for s in np.arange(0.0, min(L, PAD_BACK_MAX) + 1e-6, CELL):
        P = ch.interpolate(s)
        A_, B_ = ch.interpolate(max(s - 3.0, 0.0)), ch.interpolate(min(s + 3.0, L))
        dx, dz = A_.x - B_.x, A_.y - B_.y
        phi = math.atan2(dz, dx) if math.hypot(dx, dz) > 1e-6 else 0.0
        angs = [phi] + [a for a in wall_angs if min(abs((a - phi) % (math.pi / 2)), math.pi / 2 - abs((a - phi) % (math.pi / 2))) > math.radians(2.0)]
        cand = []
        for a in angs:
            cand.append((a, sq))
        for a in angs:
            cand.append((a, hh))
            cand.append((a + math.pi / 2, hh))
        for a, shp in cand:
            u = np.array([math.cos(a), math.sin(a)])
            n = np.array([-u[1], u[0]])
            XY = P.x + shp[..., 0:1] * u[0] + shp[..., 1:2] * n[0], P.y + shp[..., 0:1] * u[1] + shp[..., 1:2] * n[1]
            arr = np.concatenate([XY[0], XY[1]], axis=-1)
            polys = shapely.polygons(arr)
            ok = np.ones(len(polys), dtype=bool)
            if ob is not None:
                ok &= ~shapely.intersects(ob, polys)
            if ar is not None:
                ok &= shapely.covered_by(polys, ar)
            if ok.any():
                return polys[int(np.argmax(ok))]
    return None


def pad_ahead(ch, turn, w, obst, area, room):
    """A turnaround pad ahead of the dead end of ch (a line that starts there) when none fits back along it: the drive carried
    straight on by CELL steps up to min(PAD_AHEAD_MAX, room), its carriageway PAD_CLEAR off obst and inside area, to the first end
    where find_pad fits a pad (T9 gate_trial dn99: a 31 m drive between two walls 9 m apart, rule 12). (end point, pad) or
    None."""
    if ch.length < 1.0 or room < CELL:
        return None
    E0 = np.asarray(ch.coords[0])
    P1 = ch.interpolate(min(3.0, ch.length))
    u = E0 - np.array([P1.x, P1.y])
    if np.hypot(*u) < 1e-6:
        return None
    u = u / np.hypot(*u)
    ob = U.clean(unary_union(obst)) if obst else None
    ar = area.buffer(0.25) if area is not None else None
    for e in np.arange(CELL, min(PAD_AHEAD_MAX, room) + 1e-6, CELL):
        E = E0 + e * u
        cor = LineString([E0, E]).buffer(w / 2.0 + PAD_CLEAR, cap_style="flat")
        if (ob is not None and cor.intersects(ob)) or (ar is not None and not cor.buffer(-0.05).within(ar)):
            return None             # the way ahead is shut: no farther end opens
        pad = find_pad(LineString([E, E0]), turn, w, obst, area)
        if pad is not None:
            return (float(E[0]), float(E[1])), pad
    return None


def node_graph(lines):
    """The drive lines [(LineString, role, building, years, street)] noded into a networkx MultiGraph (edge attribute ls):
    near misses snapped, pieces that reach no street dropped, noding slivers pruned (not the ends of building drives),
    degree-2 chains merged. Returns (graph, {attach node: street id}, [a node of each dropped piece])."""
    import networkx as nx
    noded = shapely.union_all(MultiLineString([ln for ln, *_ in lines]), grid_size=GRID)
    edges = [g for g in getattr(noded, "geoms", [noded]) if g.geom_type == "LineString" and g.length > 0.2]
    Gr = nx.MultiGraph()
    for e in edges:
        Gr.add_edge(key(e.coords[0]), key(e.coords[-1]), ls=e)
    attach_pts = {}
    protect = set()
    for ln, role, bid, yrs, sid in lines:
        if sid is not None:
            attach_pts[key(ln.coords[0])] = sid
        if role in ("access", "fire"):
            protect.add(key(ln.coords[-1]))
    # near misses of the noding: a loose end within SNAP of another drive joins it (split there, or its end node)
    edge_list = [(u, v, k, dd["ls"]) for u, v, k, dd in Gr.edges(keys=True, data=True)]
    etree = shapely.STRtree([e[3] for e in edge_list]) if edge_list else None
    for nd in [n_ for n_ in Gr.nodes if Gr.degree(n_) == 1 and n_ not in attach_pts]:
        if nd not in Gr or Gr.degree(nd) != 1:
            continue
        P = Point(nd)
        (a0, b0, k0, d0), = Gr.edges(nd, keys=True, data=True)
        own = d0["ls"]
        for j in etree.query(P.buffer(SNAP)):
            u, v, k, ls = edge_list[int(j)]
            if nd in (u, v) or not Gr.has_edge(u, v, k) or Gr.edges[u, v, k]["ls"] is not ls or ls.distance(P) > SNAP:
                continue
            t = ls.project(P)
            s0, s1 = key(ls.coords[0]), key(ls.coords[-1])
            if t < SNAP:
                tgt = s0
            elif t > ls.length - SNAP:
                tgt = s1
            else:
                q = ls.interpolate(t)
                tgt = key((q.x, q.y))
                Gr.remove_edge(u, v, k)
                Gr.add_edge(s0, tgt, ls=LineString(list(substring(ls, 0, t).coords[:-1]) + [tgt]))
                Gr.add_edge(tgt, s1, ls=LineString([tgt] + list(substring(ls, t, ls.length).coords[1:])))
            if tgt == (b0 if a0 == nd else a0):
                continue
            oc = list(own.coords)
            oc = oc[:-1] + [tgt] if key(oc[-1]) == nd else [tgt] + oc[1:]
            Gr.remove_edge(a0, b0, k0)
            Gr.remove_node(nd)
            other_end = b0 if a0 == nd else a0
            Gr.add_edge(other_end, tgt, ls=LineString(oc))
            break
    # drop pieces that reach no street
    dropped = []
    for comp in list(nx.connected_components(Gr)):
        if not any(c in attach_pts for c in comp):
            dropped.append(next(iter(comp)))
            Gr.remove_nodes_from(comp)
    # parallel drives between the same two nodes whose carriageways overlap (near-identical lines): the shorter one stays
    for u, v in {(min(a, b), max(a, b)) for a, b in Gr.edges() if a != b}:
        es = sorted(Gr.get_edge_data(u, v).items(), key=lambda kv: kv[1]["ls"].length)
        for k_, dd in es[1:]:
            if dd["ls"].hausdorff_distance(es[0][1]["ls"]) < CELL:
                Gr.remove_edge(u, v, k_)
    # prune noding slivers (dead-end stubs shorter than two cells hanging off a junction; a building's drive end stays) and
    # merge degree-2 chains (not through attach points), until neither changes the graph: a merge can make a stub
    outer = True
    while outer:
        outer = False
        changed = True
        while changed:
            changed = False
            for nd in list(Gr.nodes):
                if nd in Gr and Gr.degree(nd) == 1 and nd not in attach_pts and nd not in protect:
                    (u, v, k, dd), = Gr.edges(nd, keys=True, data=True)
                    o = v if u == nd else u
                    if dd["ls"].length < 2 * CELL and Gr.degree(o) >= 3:
                        Gr.remove_edge(u, v, k)
                        Gr.remove_node(nd)
                        changed = outer = True
        changed = True
        while changed:
            changed = False
            for nd in list(Gr.nodes):
                if nd not in Gr or Gr.degree(nd) != 2 or nd in attach_pts:
                    continue
                es = list(Gr.edges(nd, keys=True, data=True))
                if len(es) != 2 or es[0][0] == es[0][1] or es[1][0] == es[1][1]:
                    continue
                (u1, v1, k1, d1), (u2, v2, k2, d2) = es
                o1 = v1 if u1 == nd else u1
                o2 = v2 if u2 == nd else u2
                m = linemerge([d1["ls"], d2["ls"]])
                if m.geom_type != "LineString":
                    continue
                Gr.remove_edge(u1, v1, k1)
                Gr.remove_edge(u2, v2, k2)
                Gr.remove_node(nd)
                Gr.add_edge(o1, o2, ls=m)
                changed = outer = True
    # a closed loop (a ring all round a building) gets a second node half way: no segment starts and ends at one node
    for u, v, k, dd in [e for e in Gr.edges(keys=True, data=True) if e[0] == e[1]]:
        ls = dd["ls"]
        h = ls.length / 2.0
        q = ls.interpolate(h)
        mid = key((q.x, q.y))
        Gr.remove_edge(u, v, k)
        Gr.add_edge(u, mid, ls=LineString(list(substring(ls, 0, h).coords[:-1]) + [mid]))
        Gr.add_edge(mid, v, ls=LineString([mid] + list(substring(ls, h, ls.length).coords[1:])))
    return Gr, attach_pts, dropped


def back_line(Gr, nd, ch):
    """The dead-end piece ch (from its dead end nd) carried on past its junction along the longest other drive there, up to
    PAD_BACK_MAX: where a fire engine backs to a turnaround when the piece itself (a short branch of a building's own up to its
    band) has no room for one."""
    cc = list(ch.coords)
    j = key(cc[-1])
    if j not in Gr:
        return ch
    es = [dd["ls"] for u, v, dd in Gr.edges(j, data=True) if not dd["ls"].equals(ch) and nd not in (key(dd["ls"].coords[0]), key(dd["ls"].coords[-1]))]
    if not es or ch.length >= PAD_BACK_MAX:
        return ch
    nx_ = max(es, key=lambda g: g.length)
    c2 = list(nx_.coords)
    if key(c2[0]) != j:
        c2 = c2[::-1]
    ln = LineString(cc + c2[1:])
    return substring(ln, 0.0, min(ln.length, PAD_BACK_MAX))


def dead_ends(Gr, attach_pts):
    """[(node, the dead-end piece as a line starting at the node)]: degree-1 nodes that are not street attach points."""
    out = []
    for nd in Gr.nodes:
        if Gr.degree(nd) != 1 or nd in attach_pts:
            continue
        (u, v, dd), = Gr.edges(nd, data=True)
        ls = dd["ls"]
        if key(ls.coords[0]) != nd:
            ls = LineString(list(ls.coords)[::-1])
        out.append((nd, ls))
    return out


def run(d, out, spec_path=None, og=None):
    """og: the street pieces off grade (U.offgrade) when the caller has them already (gen_buildings)."""
    t0 = time.time()
    spec = U.load_spec(d, spec_path)
    norms = U.Norms()
    log = U.Log()
    od = U.out_dir(out, d)
    net = U.read_json(os.path.join(od, "network.json"))
    blocks = U.read_json(os.path.join(od, "blocks.json"))["blocks"]
    lots = {L["id"]: L for L in U.read_json(os.path.join(od, "lots.json"))["lots"]}
    bdoc = U.read_json(os.path.join(od, "buildings.json"))
    # land a turnaround pad keeps off while it fits elsewhere: parks, squares, playgrounds, transit forecourts (tester item
    # 107: an asphalt pad in a paved plaza)
    off_polys = [U.geom(L) for L in lots.values() if L["use"] in PAD_OFF_USES]
    off_tree = U.strtree(off_polys) if off_polys else None
    n_off = [0, 0]          # pads kept off that land, pads that fit only on it

    def pad_at(ch, back, obst, area=None, obst_back=None):
        """find_pad on the dead-end piece, then on the line backing past its junction (obst_back: its obstacles, else
        obst): off the parks and plazas first."""
        off = [off_polys[int(j)] for j in off_tree.query(ch.buffer(PAD_BACK_MAX + 25.0))] if off_tree is not None else []
        for k, extra in enumerate([off, []] if off else [[]]):
            pad = find_pad(ch, F["turn"], w_car, obst + extra, area)
            if pad is None and back is not None:
                pad = find_pad(back(), F["turn"], w_car, (obst if obst_back is None else obst_back) + extra, area)
            if pad is not None:
                if off:
                    n_off[k] += 1
                return pad
        return None
    F = fire_params(norms)
    pr = U.profile_from_norms(norms, "driveway_main")
    w_car = sum(pr["lanes"]) * pr["lane_w"]
    if w_car < F["width"]:
        raise SystemExit(f"driveway_main carriageway {w_car} m < fire_access.width_min_m {F['width']} m")
    half = pr["red_line_w"] / 2.0                      # drive + sidewalks stay this far from walls
    cw = w_car / 2.0
    T = U.terrain()
    segs = {s["id"]: s for s in net["segments"]}
    # street pieces off grade (landings, ramps, embankments, cuts, low spans): no drive crosses or roots on them; a drive may
    # pass under a span with the fire clearance (land_util.offgrade)
    og = U.offgrade(net, norms, T) if og is None else og
    # and the spec railway's viaduct and the LRT viaduct where a fire engine does not pass under them
    # (fire_access.arches.height_min_m, rule 25 under_decks)
    lrt = U.read_json(os.path.join(od, "lrt.json")) or {}
    og_polys = [p["poly"] for p in og] + U.rail_low_decks(spec, norms, T) + U.lrt_low_decks(lrt, norms, T)
    og_tree = U.strtree(og_polys) if og_polys else None
    og_by_seg = defaultdict(list)
    for p in og:
        og_by_seg[p["seg"]["id"]].append(p)
    # access streets: their parts at grade (level 0, off every off-grade piece); acc = (segment, red-line polygon, part line)
    acc = []
    for s in net["segments"]:
        if s["class"] not in U.DRIVABLE or s["class"] in U.NO_ACCESS or s["class"].startswith("driveway"):
            continue          # a driveway_* piece in the spec network is not a street to attach to (merge takes it for a drive)
        rw = U.red_half(U.seg_profile(net, s, norms))
        if rw <= 0:
            continue
        own = unary_union([p["poly"] for p in og_by_seg.get(s["id"], [])]) if og_by_seg.get(s["id"]) else None
        for part in U.at_grade_parts(s, og_by_seg.get(s["id"], [])):
            q = part.buffer(rw, quad_segs=4)
            if own is not None:
                q = U.clean(q.difference(own))
            if not q.is_empty:
                acc.append((s, q, part))
    acc_tree = U.strtree([p for _, p, _ in acc])
    car_streets = U.clean(unary_union([p for s, p, lv in U.network_polys(net, norms, "carriage") if s["class"] in U.DRIVABLE and lv == 0]))
    shapely.prepare(car_streets)        # «within distance» of a building against the whole network: an indexed test
    # street carriageways one by one, as rule 12 takes them, for the fire band of a tall building: some carriageway with its
    # edge in the band (lo..hi from the wall); one nearer only does not do
    st_sp = [(s, p) for s, p, lv in U.network_polys(net, norms, "carriage") if s["class"] in U.DRIVABLE and s["class"] not in U.NO_ACCESS and lv == 0]
    st_car = [p for _, p in st_sp]
    st_tree = U.strtree(st_car) if st_car else None

    def open_by(sg, yrs):
        """The street stands in every scenario year of yrs (rule 12: access standing in the year the building opens)."""
        sy = sg.get("years") or [0] * 4
        return yrs is None or not any(yrs[i] < sy[i] for i in range(4))

    def street_in_band(bp, lo, hi, yrs=None):
        if st_tree is None:
            return False
        return any(lo <= st_car[int(j)].distance(bp) <= hi and open_by(st_sp[int(j)][0], yrs)
                   for j in st_tree.query(bp, predicate="dwithin", distance=hi))

    def street_within(bp, r, yrs=None):
        """A street carriageway (no motorway: rule 12's own set) within r of the wall, standing by yrs."""
        if st_tree is None:
            return False
        return any(open_by(st_sp[int(j)][0], yrs) for j in st_tree.query(bp, predicate="dwithin", distance=r))
    B = bdoc["buildings"]
    for b in B:
        b["_p"] = U.from_coords(b["footprint"])
    btree = U.strtree([b["_p"] for b in B])
    # the LRT ground corridor is no place for a drive (crossings are the streets' business)
    w_lrt = norms.v("lrt.corridor_width_m", "double_track")
    lrt_polys = []
    for Ln in lrt.get("lines", []):
        ls_ = LineString([(q[0], q[1]) for q in Ln["pts"]])
        for sec in Ln.get("sections", []):
            if sec["kind"] == "ground" and sec["to_m"] - sec["from_m"] > 1:
                lrt_polys.append(substring(ls_, max(0, sec["from_m"]), min(ls_.length, sec["to_m"])).buffer(w_lrt / 2, cap_style="flat"))
    lrt_tree = U.strtree(lrt_polys) if lrt_polys else None
    by_block = defaultdict(list)
    for b in B:
        L = lots.get(b.get("lot"))
        if L is not None and b["source"] != "existing_osm":
            by_block[L["block"]].append(b)

    lines = []          # (LineString, role, building id, years, attach seg id | None)
    unserved = []
    far = []            # buildings whose drive edge stays beyond the band (the router could not reach closer)
    pads_pre = {}       # dead-end node key -> pad polygon (found with the block's land)
    stats = defaultdict(int)
    for blk in blocks:
        bs = by_block.get(blk["id"])
        if not bs or blk["use"] == "landmark":
            continue
        BP = U.geom(blk)
        todo = []
        for b in bs:
            (lo, hi), ring = needs(b, lots[b["lot"]]["use"], F, norms)
            tall = b["height_m"] > F["hi_h"]
            # a street carriageway that stands when the building opens already serves it (a tall one: in its fire band; one
            # up to 28 m: within the building-line limit); a street opened later does not (rule 12, opening years)
            if not ring and (street_in_band(b["_p"], lo, hi, b["years"]) if tall else street_within(b["_p"], F["lim"], b["years"])):
                continue
            # banded: rule 12 asks some carriageway with its edge in the band, and a nearer one does not do — a building over
            # 28 m, and one of 10–28 m with no street within the limit (its own drive or pad at the wall is no fire access);
            # a drive of a lower building's own comes up to the wall the same way (tester item 68), a nearer one is no fault
            banded = tall or (b["height_m"] >= F["mid_h"][0] and not street_within(b["_p"], F["lim"], b["years"]))
            todo.append((b, lo, hi, ring, banded))
        if not todo:
            continue
        inner = U.clean(BP.buffer(-half))
        obst_b = [B[int(j)]["_p"] for j in btree.query(BP.buffer(half + 1.0))]
        if lrt_tree is not None:
            obst_b += [lrt_polys[int(j)] for j in lrt_tree.query(BP.buffer(half + 1.0))]
        if og_tree is not None:
            obst_b += [og_polys[int(j)] for j in og_tree.query(BP.buffer(half + 1.0))]
        ub = unary_union(obst_b) if obst_b else None
        obst = U.clean(ub.buffer(half + 0.25)) if obst_b else U.Polygon()
        free_poly = U.clean(inner.difference(obst))
        if free_poly.is_empty and not obst_b:
            unserved += [b["id"] for b, *_ in todo]
            continue
        x0, z0, x1, z1 = BP.bounds
        xs = np.arange(x0 + CELL / 2, x1, CELL)
        zs = np.arange(z0 + CELL / 2, z1, CELL)
        X, Z = np.meshgrid(xs, zs)
        # passages between buildings (arches, gaps of a perimeter block) may drop the sidewalks: carriageway clearance only,
        # at TIGHT_COST per metre so the router keeps to the full width wherever it can
        tight_poly = U.clean(inner.difference(ub.buffer(cw + 0.5))) if obst_b else inner
        tight_b = tight_poly.buffer(0.05)
        shapely.prepare(tight_b)
        free = shapely.contains_xy(tight_poly, X, Z)
        loose = shapely.contains_xy(free_poly, X, Z)
        if free.sum() < 2:
            unserved += [b["id"] for b, *_ in todo]
            continue
        n_before = len(lines)
        idx = -np.ones(free.shape, dtype=np.int64)
        idx[free] = np.arange(int(free.sum()))
        lflat = loose[free]
        rows, cols, wts = [], [], []
        ny, nx = free.shape
        for di, dj in ((0, 1), (1, 0), (1, 1), (1, -1)):
            if dj < 0:
                a = idx[0:ny - di, -dj:nx]
                bb = idx[di:ny, 0:nx + dj]
            elif dj > 0:
                a = idx[0:ny - di, 0:nx - dj]
                bb = idx[di:ny, dj:nx]
            else:
                a = idx[0:ny - di, :]
                bb = idx[di:ny, :]
            m = (a >= 0) & (bb >= 0)
            rows.append(a[m])
            cols.append(bb[m])
            lo_a, lo_b = lflat[a[m]], lflat[bb[m]]
            wts.append(CELL * math.hypot(di, dj) * np.where(lo_a & lo_b, 1.0, TIGHT_COST))
        n = int(free.sum())
        R_, C_, W_ = np.concatenate(rows), np.concatenate(cols), np.concatenate(wts)
        G = coo_matrix((W_, (R_, C_)), shape=(n, n)).tocsr()
        PX, PZ = X[free], Z[free]
        pts = shapely.points(PX, PZ)
        # sources: free cells next to an access street of this block
        near_acc = [int(j) for j in acc_tree.query(BP.buffer(1.0), predicate="intersects")]
        if not near_acc:
            unserved += [b["id"] for b, *_ in todo]
            log("квартал без улицы для въезда", [blk["id"]], warn=True)
            continue
        acc_u = unary_union([acc[j][1] for j in near_acc])
        shapely.prepare(acc_u)
        src = np.flatnonzero(shapely.dwithin(acc_u, pts, half + 1.5 * CELL))     # an indexed «within», not every cell's distance
        if len(src) == 0:
            unserved += [b["id"] for b, *_ in todo]
            continue
        # the street of each root cell: the nearest access street; a building roots only on streets open by its years
        cell_sid = np.full(len(pts), -1, dtype=np.int64)
        dj_ = np.array([shapely.distance(acc[j][1], pts[src]) for j in near_acc])
        cell_sid[src] = np.array(near_acc)[np.argmin(dj_, axis=0)]
        # a root whose tie to the street centreline would cross the LRT ground corridor or a street piece off grade is no root
        bar_near = [lrt_polys[int(j)] for j in lrt_tree.query(BP.buffer(60.0))] if lrt_tree is not None else []
        bar_near += [og_polys[int(j)] for j in og_tree.query(BP.buffer(60.0))] if og_tree is not None else []
        if bar_near:
            lu = unary_union(bar_near)
            shapely.prepare(lu)
            keep_src = []
            for c in src:
                sl = acc[int(cell_sid[c])][2]
                q = sl.interpolate(sl.project(pts[c]))
                if LineString([(PX[c], PZ[c]), (q.x, q.y)]).intersects(lu):
                    cell_sid[c] = -1
                else:
                    keep_src.append(c)
            src = np.array(keep_src, dtype=np.int64)
            if len(src) == 0:
                unserved += [b["id"] for b, *_ in todo]
                continue
        # nor one whose tie's carriageway would cross a building: the tie runs straight from the root cell to the street
        # centreline, outside the cells' clearance, and a house at the street front stood under it (Gate G1: ds1667, ds2071,
        # ds2618 over three village houses by 2–5 m², rule 1)
        bld_near = [B[int(j)]["_p"] for j in btree.query(BP.buffer(TIE_NEAR_M))]
        if bld_near:
            bu = unary_union(bld_near)
            shapely.prepare(bu)
            qs = [acc[int(cell_sid[c])][2].interpolate(acc[int(cell_sid[c])][2].project(pts[c])) for c in src]
            ties = shapely.linestrings(np.array([[(PX[c], PZ[c]), (q.x, q.y)] for c, q in zip(src, qs)]).reshape(-1, 2, 2))
            bad = shapely.dwithin(bu, ties, cw + TIE_CLEAR_M)
            if bad.any():
                stats["roots_off_house"] += int(bad.sum())
                cell_sid[src[bad]] = -1
                src = src[~bad]
                if len(src) == 0:
                    unserved += [b["id"] for b, *_ in todo]
                    continue
        is_src = np.zeros(len(pts), dtype=bool)
        is_src[src] = True
        tree_par = {}               # grid cell -> parent cell (-1 at a root cell next to the street)
        tree_sid = np.full(len(pts), -1, dtype=np.int64)      # street (acc index) the tree cell hangs from
        in_tree = np.zeros(len(pts), dtype=bool)
        cell_yrs = np.full((len(pts), 4), 10 ** 6, dtype=np.int64)    # earliest years of a drive through the cell
        state = {}

        def allowed_streets(yrs):
            ok = {j for j in near_acc if not any(yrs[i] < acc[j][0]["years"][i] for i in range(4))}
            return frozenset(ok or near_acc)

        def masked(keep, zoned=False):
            m_ = keep[R_] & keep[C_]
            w_ = W_ if not zoned else state["W_z"]
            return coo_matrix((w_[m_], (R_[m_], C_[m_])), shape=(n, n)).tocsr()

        def route(allow, keep=None, bare=False):
            """Distances from the street cells of the allowed streets and from the tree cells hanging from them (over the
            cells of keep only, when given). The cells nearer a tall building's wall than its fire band cost ZONE_COST per
            metre (state["zcost"]) unless bare: drives keep off them wherever they can, so a drive that passes a tall
            building is in its band or beyond, not nearer."""
            zc = None if bare else state.get("zcost")
            k_ = (allow, len(tree_par), id(keep), zc is not None)
            if state.get("k") != k_:
                al = np.array(sorted(allow))
                srcm = (np.isin(cell_sid, al) & is_src) | (in_tree & np.isin(tree_sid, al))
                if keep is not None:
                    srcm &= keep
                srcs = np.flatnonzero(srcm)
                if len(srcs) == 0:
                    state["dist"], state["pred"] = np.full(n, np.inf), np.full(n, -9999, dtype=np.int64)
                else:
                    if keep is None:
                        Gm = G if zc is None else zc
                    else:
                        Gm = masked(keep, zc is not None)
                    state["dist"], state["pred"] = dijkstra(Gm, directed=False, indices=srcs, min_only=True, return_predecessors=True)[:2]
                state["k"] = k_
                state["keep"] = keep        # holds the mask alive while its id keys the cache
            return state["dist"], state["pred"]

        def tree_path(c):
            out_ = [c]
            while tree_par[out_[-1]] >= 0:
                out_.append(tree_par[out_[-1]])
            return out_[::-1]

        def grow(t, allow, keep=None, bare=False):
            """Cells street -> t: along the tree as far as it goes, then the new cells (added to the tree)."""
            if in_tree[t]:
                return tree_path(t)
            _, pred = route(allow, keep, bare)
            p = [t]
            while pred[p[-1]] >= 0 and not in_tree[p[-1]]:
                p.append(pred[p[-1]])
            p = p[::-1]
            if in_tree[p[0]]:
                base, prev, p = tree_path(p[0]), p[0], p[1:]
                root = tree_sid[prev]
            else:
                base, prev, root = [], -1, cell_sid[p[0]]
            for c in p:
                tree_par[c] = prev
                in_tree[c] = True
                tree_sid[c] = root
                prev = c
            return base + p

        def attach_line(cells):
            """Polyline street centreline -> cells; returns (LineString, segment id)."""
            c0 = Point(PX[cells[0]], PZ[cells[0]])
            j = int(cell_sid[cells[0]]) if cell_sid[cells[0]] >= 0 else min(near_acc, key=lambda j: acc[j][1].distance(c0))
            s, sl = acc[j][0], acc[j][2]
            q = sl.interpolate(sl.project(c0))
            return LineString([(q.x, q.y)] + [(PX[c], PZ[c]) for c in cells]), s["id"]

        def add(ln, role, bid, yrs, sid, cells=()):
            lines.append((ln, role, bid, yrs, sid))
            if len(cells):
                cc = np.asarray(cells, dtype=np.int64)
                cell_yrs[cc] = np.minimum(cell_yrs[cc], np.asarray(yrs, dtype=np.int64))

        def near_car(bp, rng, extra=None):
            """Carriageway (flat caps) of this block's drives within rng of the building: the lines clipped to a box
            2 m beyond rng + cw, so every carriageway point within rng keeps its true shape."""
            box = shapely.box(*bp.buffer(rng + cw + 2.0).bounds)
            ls_ = [ln for ln, *_ in lines[n_before:]] + ([extra] if extra is not None else [])
            parts = []
            for g in ls_:
                if g.intersects(box):
                    q = g.intersection(box)
                    parts += [h for h in getattr(q, "geoms", [q]) if h.geom_type == "LineString" and h.length > 0]
            return MultiLineString(parts).buffer(cw, cap_style="flat") if parts else None

        def car_dist(bp, extra=None):
            """The validator's measure: wall to the nearest carriageway of this block's drives (flat caps)."""
            cp = near_car(bp, F["lim"], extra)
            return math.inf if cp is None else bp.distance(cp)

        def own_dist(bp, ln, own):
            """Rule 12's measure for a tall building's own drive: its carriageway (flat caps) from coordinate own on (the
            junction with the drive it branches off, or the street) to the wall."""
            cc = list(ln.coords)[own:]
            if len(cc) < 2:
                return math.inf
            return bp.distance(LineString(cc).buffer(cw, cap_style="flat"))

        def reach_wall(ln, bp, lo, hi, own=None):
            """(line, edge distance). The band cells are measured for a drive along the wall; a drive that ends facing the
            wall has its flat end nearest, up to cw farther: a straight stub on to the band, clear of the other buildings as a
            tight passage — towards the nearest wall point (to max(lo, hi − 1) m), else straight on along the drive's last
            leg, metre by metre, until its edge is in the band; the stub that comes nearest when none gets there.
            own (a tall building): the distance is that of the building's own drive from coordinate own on, and a stub never
            brings its edge nearer than lo + EDGE_MARGIN (rule 12: some carriageway in the band, a nearer one does not do)."""
            meas = (lambda l_: own_dist(bp, l_, own)) if own is not None else (lambda l_: car_dist(bp, l_))
            near_lim = lo + EDGE_MARGIN if own is not None else -math.inf
            de = meas(ln)
            if near_lim <= de <= hi - EDGE_MARGIN:
                return ln, de
            if de < near_lim:
                return ln, de           # nearer than the band already: no stub makes it farther
            cc = list(ln.coords)
            E = Point(cc[-1])
            Wp = nearest_points(bp, E)[0]
            dE = E.distance(Wp)
            tgt = max(lo, hi - 2 * EDGE_MARGIN)
            best = (de, ln)
            if dE > tgt + 0.1:
                f = (dE - tgt) / dE
                E2 = (E.x + (Wp.x - E.x) * f, E.y + (Wp.y - E.y) * f)
                if tight_b.contains(LineString([(E.x, E.y), E2])):
                    ln2 = LineString(cc + [E2])
                    de2 = meas(ln2)
                    if near_lim <= de2 < best[0]:
                        best = (de2, ln2)
            if best[0] > hi - EDGE_MARGIN and len(cc) >= 2:
                ux, uz = cc[-1][0] - cc[-2][0], cc[-1][1] - cc[-2][1]
                nu = math.hypot(ux, uz)
                if nu > 1e-6:
                    ux, uz = ux / nu, uz / nu
                    for st in np.arange(STUB_STEP, dE, STUB_STEP):
                        E2 = (E.x + ux * st, E.y + uz * st)
                        if not tight_b.contains(LineString([(E.x, E.y), E2])) or bp.distance(Point(E2)) < lo:
                            break
                        ln2 = LineString(cc + [E2])
                        de2 = meas(ln2)
                        if de2 < near_lim:
                            break
                        if de2 < best[0]:
                            best = (de2, ln2)
                        if de2 <= hi - EDGE_MARGIN:
                            break
            return best[1], best[0]

        def path_to(t, allow, keep=None, own=False, bare=False):
            """The cells grow(t, allow, keep) would add, street -> t, without adding them. own: also the index (in the line
            of attach_line) where the new cells begin — at the junction with the tree, or at the street."""
            if in_tree[t]:
                tp = tree_path(t)
                return (tp, len(tp)) if own else tp
            _, pred = route(allow, keep, bare)
            p = [t]
            while pred[p[-1]] >= 0 and not in_tree[p[-1]]:
                p.append(pred[p[-1]])
            p = p[::-1]
            if in_tree[p[0]]:
                tp = tree_path(p[0])
                cells = tp + p[1:]
                return (cells, len(tp)) if own else cells
            return (p, 0) if own else p

        def alt_targets(band, dist, first):
            """Other band cells to try when the first target leaves the wall short of the band: reachable, cheapest first,
            at least ALT_SPACING apart, at most ALT_TRIES."""
            cand = np.flatnonzero(band & np.isfinite(dist))
            cand = cand[np.argsort(dist[cand], kind="stable")]
            out_ = []
            taken = [first]
            for c in cand:
                if all(math.hypot(PX[c] - PX[o], PZ[c] - PZ[o]) >= ALT_SPACING for o in taken):
                    out_.append(int(c))
                    taken.append(c)
                    if len(out_) >= ALT_TRIES:
                        break
            return out_

        def loop_from(nd, ch, yrs):
            """A drive from the dead end nd on to a street open by yrs or to the tree, over new ground (not back along its
            own piece ch): the dead end becomes a through drive. True when built."""
            P = Point(nd)
            dp = shapely.distance(P, pts)
            c0 = int(np.argmin(dp))
            if dp[c0] > 2 * CELL:
                return False
            dch = shapely.distance(ch, pts)
            others = MultiLineString([ln for ln, *_ in lines[n_before:]])
            shapely.prepare(others)
            on_line = shapely.dwithin(others, pts, CELL / 4)
            disc = dp <= w_car + CELL
            allow = allowed_streets(yrs)
            al = np.array(sorted(allow))
            tgt = ((np.isin(cell_sid, al) & is_src) | (in_tree & np.isin(tree_sid, al))) & (dch > w_car + CELL / 2)
            # new ground only: off the piece's corridor and off the cells other drives run through (except where it joins)
            keep = ((dch > w_car + CELL / 2) & ~on_line) | disc | tgt
            keep &= ~tall_zone          # a loop through the yard keeps out of the tall buildings' fire bands' near side
            keep[c0] = True
            tgt &= keep
            if not tgt.any():
                return False
            dd_, pred = dijkstra(masked(keep), directed=False, indices=c0, return_predecessors=True)
            cand = np.flatnonzero(tgt & np.isfinite(dd_) & (dd_ <= LOOP_MAX))
            if len(cand) == 0:
                return False
            t = int(cand[np.argmin(dd_[cand])])
            p = [t]
            while p[-1] != c0:
                p.append(int(pred[p[-1]]))
            p = p[::-1]                 # c0 -> t
            head = [] if dp[c0] < 0.1 else [(P.x, P.y)]
            new_ln = LineString(head + [(PX[c], PZ[c]) for c in p]) if len(head) + len(p) >= 2 else None
            if new_ln is None:
                return False
            smp = shapely.line_interpolate_point(new_ln, np.arange(0.0, new_ln.length, 1.0))
            if shapely.dwithin(others, smp, cw).mean() > 0.5:
                return False            # it would run along drives already there: no loop
            if in_tree[t]:
                ln = LineString(head + [(PX[c], PZ[c]) for c in p])
                ly = [max(a, int(c)) if int(c) < 10 ** 6 else a for a, c in zip(yrs, cell_yrs[t])]
                sid, root = None, tree_sid[t]
            else:                       # a street cell: the loop leaves the yard by its own entry
                ln0, sid = attach_line(p[::-1])
                ln = LineString(list(ln0.coords) + head[::-1])
                ly = [max(a, c) for a, c in zip(yrs, segs[sid]["years"])]
                root = cell_sid[t]
            prev = t if in_tree[t] else -1
            for c in p[::-1]:
                if not in_tree[c]:
                    tree_par[c] = prev
                    in_tree[c] = True
                    tree_sid[c] = root
                prev = c
            add(ln, "link", None, ly, sid, p)      # a turnaround loop: it serves no building (their own drives do)
            stats["loops"] += 1
            return True

        def yrs_of(P):
            best = min(lines[n_before:], key=lambda r: r[0].distance(P))
            return best[3]

        dist0 = route(frozenset(near_acc))[0]
        order = []
        tall_zone = np.zeros(len(pts), dtype=bool)     # cells nearer a tall building's wall than its fire band
        for b, lo, hi, ring, banded in todo:
            # wall distance of the cells near the building only (the band and the nearest band cell need no others)
            shapely.prepare(b["_p"])
            near_b = shapely.dwithin(b["_p"], pts, hi + cw + 2 * CELL)      # the band and its fallback below
            dw = np.full(len(pts), np.inf)
            dw[near_b] = shapely.distance(b["_p"], pts[near_b])
            band = (dw >= lo + cw + EDGE_MARGIN) & (dw <= hi + cw - EDGE_MARGIN)
            if banded:
                tall_zone |= dw < lo + cw + EDGE_MARGIN
            if banded and not (band & np.isfinite(dist0)).any():
                # no cell for a drive along the wall in the band: cells a little farther, the drive brought in by its stub
                band = (dw >= lo + cw + EDGE_MARGIN) & (dw <= hi + cw + 2 * CELL)
            reach = dist0[band & np.isfinite(dist0)]
            order.append((-(reach.min() if len(reach) else 0.0), b["id"], b, lo, hi, ring, banded, band, dw))
        order.sort(key=lambda r: (r[0], r[1]))      # farthest first: the long drives become trunks the near ones branch off
        if tall_zone.any():
            state["W_z"] = W_ * np.where(tall_zone[R_] | tall_zone[C_], ZONE_COST, 1.0)
            state["zcost"] = coo_matrix((state["W_z"], (R_, C_)), shape=(n, n)).tocsr()
        for _, _, b, lo, hi, ring, banded, band, dw in order:
            allow = allowed_streets(b["years"])
            tall = banded           # the band logic of a tall building (its own branch, a nearer drive does not serve)
            keep = None
            strict = band & (dw <= hi + cw - EDGE_MARGIN)
            dist, _ = route(allow)
            on_tree = np.flatnonzero(strict & in_tree & np.isin(tree_sid, np.array(sorted(allow))))
            if tall and len(on_tree):
                # a drive in the band already serves when the block's drives near the wall keep their edge in the band (rule 12
                # measures each piece whole; a nearer one does not serve); else the building's own branch, clear of its near side
                dn_ = car_dist(b["_p"])
                if not (lo + EDGE_MARGIN <= dn_ <= hi - EDGE_MARGIN):
                    on_tree = on_tree[:0]
            if len(on_tree):
                t = int(on_tree[np.argmin(dw[on_tree])])
            elif tall:
                keep = ~(dw < lo + cw + EDGE_MARGIN)
                dist, _ = route(allow, keep)
                cand = np.flatnonzero(band & np.isfinite(dist) & ~in_tree)
                if len(cand) == 0:
                    keep = None
                    dist, _ = route(allow)
                    cand = np.flatnonzero(band & np.isfinite(dist) & ~in_tree)
                if len(cand) == 0:
                    cand = np.flatnonzero(band & np.isfinite(dist))
                if len(cand) == 0:
                    unserved.append(b["id"])
                    continue
                t = int(cand[np.argmin(dist[cand])])
            else:
                cand = np.flatnonzero(band & np.isfinite(dist))
                if len(cand) == 0:
                    unserved.append(b["id"])
                    continue
                t = int(cand[np.argmin(dist[cand])])

            def off_band(x):
                """How far the edge distance x is outside the band the drive aims at (0 inside)."""
                lo_ = lo + EDGE_MARGIN if tall else -math.inf
                return max(lo_ - x, x - (hi - EDGE_MARGIN), 0.0)
            # the target's drive (with its stub on to the wall); when its edge stays out of the band, other band cells are
            # tried and the first that brings it in (else the nearest) is built
            best = None
            tries = [t]
            k_ = 0
            while k_ < len(tries):
                tt = tries[k_]
                if tall and in_tree[tt] and strict[tt] and len(on_tree):
                    ln_, sid_ = attach_line(tree_path(tt))       # a drive already in the band, none nearer
                    ln0_, de_ = ln_, car_dist(b["_p"])
                elif tall:
                    cells_, own_ = path_to(tt, allow, keep, own=True)
                    ln0_, sid_ = attach_line(cells_)
                    ln_, de_ = reach_wall(ln0_, b["_p"], lo, hi, own=own_)
                else:
                    ln0_, sid_ = attach_line(path_to(tt, allow))
                    ln_, de_ = reach_wall(ln0_, b["_p"], lo, hi)
                if best is None or off_band(de_) < off_band(best[0]) - 1e-6:
                    best = (de_, tt, ln_, sid_, ln_ is not ln0_)
                if off_band(de_) == 0.0:
                    break
                if k_ == 0:
                    tries += alt_targets(band, dist, t)
                    if len(tries) > 1:
                        stats["alt"] += 1
                k_ += 1
            de, t, ln, sid, stub = best
            stats["stubs"] += int(stub)
            cells = grow(t, allow, keep)
            if de > hi or (tall and de < lo):
                far.append(f"{b['id']} {de:.1f} м")
            yrs = [max(a, c) for a, c in zip(b["years"], segs[sid]["years"])]
            add(ln, "fire" if b["height_m"] > F["hi_h"] else "access", b["id"], yrs, sid, cells)
        # ring access: the loop at the norm distance (the middle of the band), only along the walls no carriageway serves
        # yet: a street within the building's limit (rule 12's ring: 25 m, over 28 m the far edge of its band), a drive of
        # the block with its edge in the band
        for _, _, b, lo, hi, ring, banded, band, dw in order:
            if not ring:
                continue
            bp = b["_p"]
            dc = (lo + hi) / 2.0 + cw
            loop = bp.buffer(dc, join_style="mitre", mitre_limit=2.0).exterior
            k = max(16, int(loop.length / CELL))
            lp = shapely.line_interpolate_point(loop, np.arange(k) * loop.length / k)
            wall = shapely.line_interpolate_point(bp.exterior, shapely.line_locate_point(bp.exterior, lp))
            ok = shapely.dwithin(car_streets, wall, hi if b["height_m"] > F["hi_h"] else F["lim"])
            cp = near_car(bp, hi)
            if cp is not None:
                ok |= shapely.distance(cp, wall) <= hi - EDGE_MARGIN
            if ok.all():
                continue
            other = [q for q in obst_b if not q.equals(bp)]
            fr = U.clean(inner.difference(unary_union(other).buffer(half + 0.25))) if other else inner
            runs, cur = [], []
            start = int(np.argmax(ok)) if ok.any() else 0      # start the circular scan on a served point
            for ii in range(k + 1):
                q = (start + ii) % k
                if not ok[q] or (not ok.any()):
                    cur.append(lp[q])
                elif cur:
                    runs.append(cur)
                    cur = []
            if cur:
                runs.append(cur)
            for run_ in runs:
                if len(run_) < 2:
                    continue
                piece = LineString([(g.x, g.y) for g in run_])
                parts = piece.intersection(fr)
                if parts.geom_type == "MultiLineString":
                    parts = linemerge(parts)          # a loop cut at its start point is one piece again
                for part in [g for g in getattr(parts, "geoms", [parts]) if g.geom_type == "LineString" and g.length > 4.0]:
                    allow = allowed_streets(b["years"])
                    closed = part.is_closed
                    # the links keep off the piece's own track (they would run along it), except near the ends they serve
                    dpart = shapely.distance(part, pts)
                    ends = [part] if closed else [Point(part.coords[0]), Point(part.coords[-1])]
                    near_end = np.zeros(len(pts), dtype=bool)
                    if not closed:
                        for e in ends:
                            near_end |= shapely.distance(e, pts) <= w_car + CELL
                    keep = None if closed else (dpart > w_car + CELL / 2) | near_end
                    dist, _ = route(allow, keep)
                    links = []
                    for e in ends:
                        de_ = dpart if closed else shapely.distance(e, pts)
                        c2 = np.flatnonzero((de_ <= CELL * 1.5) & np.isfinite(dist) & (True if keep is None else keep))
                        if len(c2) == 0:
                            continue
                        t2 = int(c2[np.argmin(dist[c2])]) if closed else int(c2[np.argmin(de_[c2])])
                        cells2 = grow(t2, allow, keep)
                        dist, _ = route(allow, keep)
                        ln2, sid2 = attach_line(cells2)
                        q = part.interpolate(part.project(Point(PX[t2], PZ[t2])))
                        yrs = [max(a, c) for a, c in zip(b["years"], segs[sid2]["years"])]
                        links.append((LineString(list(ln2.coords) + [(q.x, q.y)]), yrs, sid2, cells2))
                    if not links:
                        log("кольцевой проезд: кусок без связи с улицей", [b["id"]], warn=True)
                        continue
                    for ln2, yrs, sid2, cells2 in links:
                        add(ln2, "link", b["id"], yrs, sid2, cells2)
                    add(part, "ring", b["id"], [min(y[i] for _, y, _, _ in links) for i in range(4)], None)
        # dead ends: a turnaround pad on the dead-end piece; else (or when it is longer than the norm) a loop through the yard
        if len(lines) > n_before:
            tried = set()
            for _pass in range(DEAD_END_PASSES):
                Gb, att_b, _ = node_graph(lines[n_before:])
                changed = False
                for nd, ch in dead_ends(Gb, att_b):
                    # obstacles near the dead-end piece, and near the line backing past its junction (Gate G5: a pad
                    # backed 20–32 m from stubs of 2–3 m onto houses 32 and 43 m off the stub, 14 and 17 m², rule 1)
                    obst_pad, obst_back = [], []
                    for r_, ob_ in ((25.0, obst_pad), (PAD_BACK_MAX + 25.0, obst_back)):
                        ob_ += [B[int(j)]["_p"] for j in btree.query(ch.buffer(r_))]
                        if lrt_tree is not None:
                            ob_ += [lrt_polys[int(j)] for j in lrt_tree.query(ch.buffer(r_))]
                        if og_tree is not None:
                            ob_ += [og_polys[int(j)] for j in og_tree.query(ch.buffer(r_))]
                    pad = pad_at(ch, (lambda: back_line(Gb, nd, ch)) if ch.length < PAD_BACK_MAX else None, obst_pad, BP, obst_back)
                    if pad is not None and ch.length <= F["dead_end_max"]:
                        pads_pre[nd] = pad
                        continue
                    if nd not in tried:
                        tried.add(nd)
                        if loop_from(nd, ch, yrs_of(Point(nd))):
                            changed = True
                            pads_pre.pop(nd, None)
                            continue
                    if pad is not None:
                        pads_pre[nd] = pad
                        continue
                    # no pad back along the dead end: the drive carried on ahead to open ground where one fits
                    if ch.length > 2 * CELL:
                        ah = pad_ahead(ch, F["turn"], w_car, obst_back, BP, F["dead_end_max"] - ch.length)
                        if ah is not None:
                            E, pad = ah
                            for i in range(n_before, len(lines)):
                                cc_ = list(lines[i][0].coords)
                                if key(cc_[-1]) == nd:
                                    cc_ = cc_ + [E]
                                elif key(cc_[0]) == nd and lines[i][4] is None:
                                    cc_ = [E] + cc_
                                else:
                                    continue
                                lines[i] = (LineString(cc_),) + tuple(lines[i][1:])
                                changed = True
                                stats["ahead"] += 1
                                break
                            continue
                    # a stub just off a junction (a building's step on towards the wall, a ring piece's end) with no room
                    # for a pad: the drive ends at the junction instead
                    if ch.length <= 2 * CELL:
                        for i in range(n_before, len(lines)):
                            cc_ = list(lines[i][0].coords)
                            if len(cc_) > 2 and key(cc_[-1]) == nd:
                                cc_ = cc_[:-1]
                            elif len(cc_) > 2 and key(cc_[0]) == nd and lines[i][4] is None:
                                cc_ = cc_[1:]
                            else:
                                continue
                            lines[i] = (LineString(cc_),) + tuple(lines[i][1:])
                            changed = True
                            stats["trimmed"] += 1
                if not changed:
                    break
    # ------------------------------------------------------------------ noding into a graph
    doc = build_graph(lines, segs, pr, F, T, [b["_p"] for b in B] + lrt_polys + og_polys, log, d, pads_pre, w_car, pad_at)
    if any(n_off):
        log("разворотные площадки вне парков, скверов, площадок и привокзальных площадей, где помещаются (замечание 107)", [],
            kept_off=n_off[0], only_there=n_off[1], uses=sorted(PAD_OFF_USES))
    # the fire band as rule 12 takes it: a new building over hi_h needs some carriageway (street, drive or pad) with its edge
    # F["hi"] from the wall; one nearer only does not do
    dsp = [(sg, p) for sg, p, _ in U.network_polys(doc, norms, "carriage")] + \
        [({"id": f"pad_{pd['node']}", "years": pd["years"]}, U.from_coords(pd["polygon"])) for pd in doc["pads"]]
    n_drv = len(dsp)
    dsp += st_sp
    dpolys = [p for _, p in dsp]
    dtree = U.strtree(dpolys) if dpolys else None
    drv_tree = U.strtree(dpolys[:n_drv]) if n_drv else None

    def mid_ok(b):
        """Rule 12 for a building of 10–28 m: a street carriageway within the limit, or some drive or pad of the block whose
        edge lies in the 5–8 m band (one nearer only does not do)."""
        if street_within(b["_p"], F["lim"]):
            return True
        if drv_tree is None:
            return False
        return any(F["mid"][0] - BAND_TOL <= dpolys[int(j)].distance(b["_p"]) <= F["mid"][1] + BAND_TOL
                   for j in drv_tree.query(b["_p"], predicate="dwithin", distance=F["lim"]))
    mid_miss, tall_ok28, acc_late = {}, set(), {}
    for b in B:
        if b["source"] == "existing_osm" or b.get("keep") or dtree is None:
            continue
        h = b["height_m"]
        if F["mid_h"][0] <= h <= F["hi_h"] and not mid_ok(b):
            ds_ = [dpolys[int(j)].distance(b["_p"]) for j in drv_tree.query(b["_p"], predicate="dwithin", distance=F["lim"])] \
                if drv_tree is not None else []
            mid_miss[b["id"]] = round(min(ds_), 1) if ds_ else None
        if h > F["hi_h"] and mid_ok(b):
            tall_ok28.add(b["id"])
        # the carriageway within reach (rule 12: the far edge of the band over 28 m, else the limit) that opens first, per
        # scenario: a building that opens before it opens later (gen_buildings). A tall one is measured at the limit too, for
        # when gen_buildings keeps it to 28 m
        for r_, tag in ((F["hi"][1], "tall"), (F["lim"], "low")) if h > F["hi_h"] else ((F["lim"], "low"),):
            reach = [int(j) for j in dtree.query(b["_p"], predicate="dwithin", distance=r_)]
            if not reach:
                continue
            ay = [min((dsp[j][0].get("years") or [0] * 4)[i] for j in reach) for i in range(4)]
            if any(b["years"][i] < ay[i] for i in range(4)):
                j0 = min(reach, key=lambda j: (dsp[j][0].get("years") or [0] * 4)[0])
                acc_late.setdefault(b["id"], {})[tag] = {"years": ay, "by": dsp[j0][0]["id"]}
    band_miss, band_near = [], {}
    for b in B:
        if b["source"] == "existing_osm" or b.get("keep") or b["height_m"] <= F["hi_h"] or dtree is None:
            continue
        ds_ = [dpolys[int(j)].distance(b["_p"]) for j in dtree.query(b["_p"], predicate="dwithin", distance=F["hi"][1])]
        if not any(F["hi"][0] <= x <= F["hi"][1] for x in ds_):
            band_miss.append(f"{b['id']} {min(ds_):.1f} м" if ds_ else b["id"])
            band_near[b["id"]] = dpolys[int(dtree.nearest(b["_p"]))].distance(b["_p"])
    # the ring as rule 12 takes it (fire_access.ring_required): wall points farther than the building's limit from every
    # carriageway; gen_buildings keeps such a building to the ring height where the height is what asks for the ring
    lim = norms.v("setbacks.building_line_max_m", "max_from_carriageway")
    ring_miss = {}
    for b in B:
        L = lots.get(b.get("lot"))
        if b["source"] == "existing_osm" or b.get("keep") or L is None or dtree is None or \
                not U.ring_required(norms, L["use"], b["use"], b["height_m"]):
            continue
        dmax = F["hi"][1] if b["height_m"] > F["hi_h"] else lim
        ring = b["_p"].exterior
        wp = shapely.line_interpolate_point(ring, np.arange(max(8, int(ring.length / 4.0))) * ring.length / max(8, int(ring.length / 4.0)))
        near = [dpolys[int(j)] for j in dtree.query(b["_p"], predicate="dwithin", distance=dmax + 1.0)]
        far_w = shapely.distance(unary_union(near), wp) > dmax + 1.0 if near else np.ones(len(wp), bool)
        if far_w.any():
            ring_miss[b["id"]] = round(float(far_w.mean()), 2)
    doc["log"] = log.rows + ([{"what": "здания без проезда: свободной земли до них нет", "ids": unserved, "warn": True}] if unserved else []) \
        + ([{"what": "проезд не подходит к стене на норму (кромка проезжей части дальше)", "ids": far, "warn": True}] if far else []) \
        + ([{"what": f"здания выше {F['hi_h']:.0f} м без проезжей части в {F['hi'][0]}–{F['hi'][1]} м от стены (ближайшая в … м)",
             "ids": band_miss, "warn": True}] if band_miss else []) \
        + ([{"what": f"здания {F['mid_h'][0]:.0f}–{F['mid_h'][1]:.0f} м без улицы в {F['lim']} м и без проезда в {F['mid'][0]}–{F['mid'][1]} м "
                     f"от стены (ближайший проезд в … м)", "ids": [f"{i} {x} м" if x is not None else i for i, x in mid_miss.items()],
             "warn": True}] if mid_miss else [])
    U.write_json(os.path.join(od, "driveways.json"), doc)
    doc["_band_miss"] = band_near          # {building id: nearest carriageway, m} for gen_buildings (not written)
    doc["_ok28"] = tall_ok28                # tall buildings rule 12 would pass at 28 m (a street within the limit, a drive in 5–8 m)
    doc["_mid_miss"] = mid_miss            # {building id of 10–28 m: nearest drive, m} with no street within the limit, no drive in 5–8 m
    doc["_acc_late"] = acc_late            # {building id: {"tall"|"low": {years: first access per scenario, by: carriageway id}}}
    doc["_ring_miss"] = ring_miss          # {building id: share of its wall beyond the limit}
    bid_ = {b["id"]: b for b in B}
    # {building id: nearest carriageway, m} of the buildings no drive reached (no free land to them)
    doc["_unserved"] = {i: (dpolys[int(dtree.nearest(bid_[i]["_p"]))].distance(bid_[i]["_p"]) if dtree is not None else 1e9)
                        for i in dict.fromkeys(unserved) if i in bid_}
    print(f"{d}: driveways {len(doc['segments'])} segments, {len(doc['nodes'])} nodes, {len(doc['pads'])} turnarounds, "
          f"{sum(U.seg_line(s).length for s in doc['segments']) / 1000:.1f} km; unserved {len(unserved)}, short of the band {len(far)}, "
          f"tall without the band {len(band_miss)}, 10–28 m without the 5–8 m band {len(mid_miss)}, opening before access {len(acc_late)}; "
          f"stubs {stats['stubs']} (trimmed {stats['trimmed']}), other targets tried {stats['alt']}, loops {stats['loops']}, "
          f"street ties off walls {stats['roots_off_house']}, carried on to a pad {stats['ahead']}; {time.time() - t0:.1f} s")
    return doc


def _pad_plain(F, w_car):
    """pad_at without land to keep off: find_pad on the dead-end piece, then backing past its junction."""
    def pad_at(ch, back, obst, area=None, obst_back=None):
        pad = find_pad(ch, F["turn"], w_car, obst, area)
        if pad is None and back is not None:
            pad = find_pad(back(), F["turn"], w_car, obst if obst_back is None else obst_back, area)
        return pad
    return pad_at


def build_graph(lines, segs, pr, F, T, B, log, d, pads_pre=None, w_car=6.0, pad_at=None):
    """Node the drive lines, merge chains, attach nodes on streets, turnaround pads on dead ends (found per block, else clear
    of the polygons B)."""
    if not lines:
        return {"schema": "qtwin.network/1", "district": d, "kind": "driveways", "profiles": {"driveway_main": pr}, "nodes": [], "segments": [], "pads": []}
    pads_pre = pads_pre or {}
    Gr, attach_pts, dropped = node_graph(lines)
    for c in dropped:
        log("кусок проезда без связи с улицей убран", [f"{c[0]:.0f},{c[1]:.0f}"], warn=True)
    meta_tree = shapely.STRtree([ln.buffer(0.3, quad_segs=1) for ln, *_ in lines])
    nid = {}
    nodes, segs_out, pads = [], [], []
    for nd in Gr.nodes:
        nid[nd] = f"dn{len(nodes)}"
        deg = Gr.degree(nd)
        rec = {"id": nid[nd], "x": nd[0], "z": nd[1], "y": round(float(T.height(nd[0], nd[1])), 2),
               "kind": "crossing" if (deg >= 3 or nd in attach_pts) else ("end" if deg == 1 else "crossing"), "ic": None, "r": None}
        if nd in attach_pts:
            rec["attach"] = {"segment": attach_pts[nd], "x": nd[0], "z": nd[1]}
        nodes.append(rec)
    for u, v, dd in Gr.edges(data=True):
        ls = dd["ls"]
        if key(ls.coords[0]) != u:
            ls = LineString(list(ls.coords)[::-1])
        mid = ls.interpolate(0.5, normalized=True)
        hits = [lines[int(j)] for j in meta_tree.query(mid, predicate="intersects")]
        if not hits:
            hits = [lines[int(meta_tree.nearest(mid))]]
        ls = ls.simplify(SIMPLIFY, preserve_topology=False)
        serves = sorted({h[2] for h in hits if h[2] is not None})
        roles = {h[1] for h in hits}
        yrs = [min(h[3][i] for h in hits) for i in range(4)] if hits else list(U.EXISTING_YEARS)
        P = np.asarray(ls.coords)
        y = T.height(P[:, 0], P[:, 1])
        segs_out.append({"id": f"ds{len(segs_out)}", "a": nid[u], "b": nid[v], "class": "driveway_main", "pid": "driveway_main",
                         "oneway": False, "pts": [[round(float(x), 2), round(float(z), 2), round(float(yy), 2)] for (x, z), yy in zip(P, y)],
                         "struct": [{"from_m": 0.0, "to_m": round(ls.length, 2), "kind": "ground"}], "years": yrs, "name_ru": None,
                         "street": None, "ic": None, "serves": serves,
                         "role": "ring" if "ring" in roles else ("fire" if "fire" in roles else ("link" if roles == {"link"} else "access"))})
    # turnarounds on dead ends
    tw, tl = sorted(F["turn"])
    inc = {}
    for s in segs_out:
        inc[s["a"]] = s
        inc[s["b"]] = s
    nrec = {n["id"]: n for n in nodes}
    bt = U.strtree(B)
    long_ = []
    for nd, ch in dead_ends(Gr, attach_pts):
        n = nrec[nid[nd]]
        s = inc[n["id"]]
        pad = pads_pre.get(nd)
        if pad is None:
            pad = (pad_at or _pad_plain(F, w_car))(ch, (lambda: back_line(Gr, nd, ch)) if ch.length < PAD_BACK_MAX else None,
                                                    [B[int(j)] for j in bt.query(ch.buffer(25.0))], None,
                                                    [B[int(j)] for j in bt.query(ch.buffer(PAD_BACK_MAX + 25.0))])
        if ch.length > F["dead_end_max"]:
            long_.append(f"{n['id']} {ch.length:.0f} м")
        if pad is None:
            log("разворотная площадка не помещается у тупика", [n["id"]], warn=True)
            continue
        n["turnaround"] = {"w_m": tw, "l_m": tl}
        pads.append({"node": n["id"], "polygon": U.coords(pad), "years": s["years"]})
    if long_:
        log(f"тупиковый проезд длиннее fire_access.dead_end_max_m {F['dead_end_max']} м, петли нет", long_, warn=True)
    return {"schema": "qtwin.network/1", "district": d, "kind": "driveways", "made_by": "w44 land_driveways.py",
            "profiles": {"driveway_main": pr}, "nodes": nodes, "segments": segs_out, "pads": pads}


if __name__ == "__main__":
    a = U.cli(__doc__).parse_args()
    run(a.district, a.out, a.spec)
