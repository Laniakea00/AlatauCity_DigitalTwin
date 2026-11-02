"""gen_network (w43): spec v1 (or level-0 axes) + existing roads → OUT/<d>/network.json (CONTRACT §4).

    python3 tools/map/gen/gen_network.py <district | path/to/spec.json> [--out OUT] [--no-grid | --grid] [--no-village]

Steps (one log line each in network.json `log`, nothing is dropped silently):
 1. existing roads (Overture/OSM, W34) inside area: class map, bridges / tunnels / levels, tracks only where they serve
    houses;
 2. spec streets (v1 `streets`, else the level-0 `axes`: keep_existing axes come from step 1, lrt corridors go to
    gen_lrt), clipped to the area;
 3. spec nodes: interchange templates (net_templates), rings (net_rings), at-grade types; existing interchanges
    (params.existing) are taken from OSM with their link roads as ramps;
 4. new roads that cross an expressway or a ramp without a node pass over it (grade separation, logged);
 5. local grid inside the superblocks (level-0 specs; a v1 spec draws its own streets) and village lanes to every house (net_grid);
 6. planar graph: a node at every crossing in one level; 5+ arm nodes become roundabouts;
 7. node kinds, heights (terrain + profile + structures), struct spans, year splits of divided streets moved onto the
    junction for both carriageways (year_gaps), export.
"""
import argparse
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from lib import geom as G  # noqa: E402
from lib import jio, norms, paths, rail  # noqa: E402
from lib import years as Y  # noqa: E402
import net_osm  # noqa: E402
import net_templates as T  # noqa: E402
from net_core import Network  # noqa: E402
from net_rings import RingError, ring  # noqa: E402
from net_roads import apply_result, assign_hints, make_road, road_from_ways  # noqa: E402

AXIS_CLASS = {"expressway": "expressway", "arterial": "arterial_regulated", "district": "district_transport",
              "local": "local", "pedestrian": "pedestrian_street", "boulevard": "boulevard", "bike": "bike_path"}
INTERCHANGES = {"diamond", "partial_cloverleaf", "cloverleaf", "trumpet", "directional", "grade_separation"}
AT_GRADE = {"crossing", "crossing_signal", "right_in_right_out"}
NO_LIFT_OVER = {"expressway", "ramp"}           # a new road never meets these at grade
REGULATED = {"arterial_regulated", "arterial_road_regulated", "district_transport"}   # crossings at grade, spaced
PROFILE_FIELDS = ["class", "lanes", "lane_w", "median_w", "sidewalk_w", "verge_w", "bike_w", "parking_w", "red_line_w"]


def area_polygon(spec, city):
    import shapely
    poly = None
    if spec.get("area"):
        poly = shapely.Polygon(spec["area"])
    b = spec.get("boundary")
    bpoly = None
    if isinstance(b, list) and len(b) >= 3:
        bpoly = shapely.Polygon(b)
    elif isinstance(b, dict) and b.get("polygon"):
        bpoly = shapely.Polygon(b["polygon"])
    if poly is None:
        poly = bpoly
    elif bpoly is not None and bpoly.is_valid and not spec.get("area_ignores_boundary"):
        inter = poly.intersection(bpoly)
        if inter.area > 0.5 * poly.area:
            poly = inter if inter.geom_type == "Polygon" else max(inter.geoms, key=lambda g: g.area)
    return poly.buffer(0)


def city_polygon(city):
    import shapely
    polys = []
    for d in (city.get("districts") or {}).values():
        p = d.get("polygon") if isinstance(d, dict) else None
        if p and len(p) >= 3:
            polys.append(shapely.Polygon(p).buffer(0))
    return shapely.union_all(polys) if polys else None


def spec_streets(spec, net):
    """Streets of the spec v1, or the level-0 axes turned into streets."""
    if spec.get("streets"):
        return list(spec["streets"])
    out = []
    for a in spec.get("axes", []):
        cls = AXIS_CLASS.get(a.get("class"))
        if a.get("class") == "lrt_corridor":
            continue
        if a.get("status") == "keep_existing":
            net.L("ось существует: дорога берётся из OSM", [a["id"]])
            continue
        if cls is None:
            net.L("ось неизвестного класса не строится", [a["id"]], cls=a.get("class"))
            continue
        out.append({"id": a["id"], "class": cls, "line": a["line"], "name_ru": a.get("name_ru", ""),
                    "years": a.get("years"), "oneway": False, "profile": {}, "struct": [], "source": "new",
                    "axis": a["id"]})
    return out


PROFILE_KEYS = {"lanes", "lane_w", "median_w", "sidewalk_w", "verge_w", "bike_w", "parking_w", "carriageways",
                "oneway", "shoulder_w"}


def profile_overrides(net, st):
    """Spec profile overrides → norms.profile overrides: only profile fields (notes dropped); green_w (boulevard green
    strip on the axis) is the median; a median on a one-carriageway class makes the street divided."""
    ov = dict(st.get("profile") or {})
    out = {k: v for k, v in ov.items() if k in PROFILE_KEYS}
    if "green_w" in ov:
        out["median_w"] = float(ov["green_w"])
    # streets[].oneway (CONTRACT §3): true makes a new street one carriageway in its drawn direction (false or absent:
    # the class profile); profile.oneway wins when both are given and differ
    if "oneway" in st and st["oneway"] is not None:
        if "oneway" in out and bool(out["oneway"]) != bool(st["oneway"]):
            net.L("улица spec: oneway улицы и profile.oneway расходятся — берётся profile.oneway", [st["id"]],
                  street_oneway=bool(st["oneway"]), profile_oneway=bool(out["oneway"]), warn=True)
        elif st["oneway"]:
            out["oneway"] = True
    if float(out.get("median_w", 0) or 0) > 0 and "carriageways" not in out and st["class"] not in ("boulevard",):
        if net.N.profile(st["class"]).get("carriageways", 1) == 1:
            out["carriageways"] = 2
            net.L("разделительная полоса в профиле: улица строится двумя проезжими частями", [st["id"]],
                  median_w=out["median_w"])
    return out or None


def street_years(st):
    y = st.get("years")
    if y is None:
        return list(Y.EXISTING)
    if isinstance(y, list) and len(y) == 2:
        return Y.years4(int(y[1]))          # a level-0 axis [start, end]: the street opens when it is built
    return Y.norm4(y)


def build_streets(net, spec, area, keep_polys, attach):
    import shapely
    N = net.N
    roads = {}
    for st in spec_streets(spec, net):
        src = st.get("source") or "new"
        if src.startswith("keep_existing"):
            continue                       # built from OSM with the spec's class (net_osm.load keep=…)
        line = shapely.LineString(st["line"])
        clip = line.intersection(area)
        parts = [clip] if clip.geom_type == "LineString" else [g for g in getattr(clip, "geoms", []) if g.geom_type == "LineString"]
        parts = [p for p in parts if p.length > 5.0]
        if not parts:
            net.L("улица spec вне участка", [st["id"]])
            continue
        if clip.length < line.length - 1.0:
            net.L("улица spec обрезана по участку", [st["id"]], kept_m=round(clip.length, 1), of_m=round(line.length, 1))
        yrs = street_years(st)
        for k, part in enumerate(parts):
            P = np.array(part.coords, float)
            sid = st["id"] if len(parts) == 1 else f"{st['id']}#{k + 1}"
            road, ways = make_road(N, st["class"], P, overrides=profile_overrides(net, st), years=yrs,
                                   name_ru=st.get("name_ru", ""), street=st["id"], source="new", id_prefix=sid)
            for w in ways:
                for e, pt in ((0, w.P[0]), (1, w.P[-1])):
                    q = shapely.Point(pt)
                    if area.exterior.distance(q) < 1.0 + road.e():
                        w.end_kind[e] = "joint"
                        w.end_ref[e] = f"area:{st['id']}"
                    for kid, kp in keep_polys.items():
                        if kp.exterior.distance(q) < 15.0 + road.e() or any(
                                np.hypot(pt[0] - a["x"], pt[1] - a["z"]) < 25.0 + road.e() for a in attach.get(kid, [])):
                            w.end_kind[e] = "joint"
                            w.end_ref[e] = f"keep:{kid}"
                # spec structures: bridge / overpass → passes over what it crosses; tunnel → under
                for s in st.get("struct") or []:
                    a_ = G.project(w.P, s["from"])[0]
                    b_ = G.project(w.P, s["to"])[0]
                    a_, b_ = min(a_, b_), max(a_, b_)
                    if s["kind"] in ("bridge", "overpass"):
                        w.lifts.append((a_, b_, f"spec:{s['kind']}"))
                    elif s["kind"] == "tunnel":
                        w.unders.append((a_, b_, "spec:tunnel"))
                net.add(w)
            roads.setdefault(st["id"], []).append(road)
    return roads


def join_carriageway_ends(net, snapped=(), tol=1.0, max_kink=10.0, merged=0.3):
    """A divided street continued by another divided street with a kink: each carriageway is offset from its own axis,
    so at the joint the carriageway ends of the two streets miss each other by 2·e·sin(kink/2) (0.4 m at 2.5°). A free
    end of a new carriageway and a free end of another one within `tol` m that continue each other (one ends where the
    other starts, directions within `max_kink`°) are moved to the point where the two lines meet (the midpoint when
    they are parallel), nearest pairs first. Ends that snap_street_ends took to a road (`snapped`: a junction at the
    joint, where each street meets that road in its own years) and ends closer than `merged` m (planarize merges
    them) are left alone. Returns the number of joints."""
    from scipy.spatial import cKDTree
    snapped = set(snapped)
    ends = []
    for w in net.ways:
        if w.source != "new" or w.role != "primary" or not w.oneway or w.cls in NO_LIFT_OVER or len(w.P) < 2:
            continue
        for e in (0, 1):
            if w.end_kind[e] is None and (id(w), e) not in snapped:
                ends.append((w, e))
    if len(ends) < 2:
        return 0
    E = np.array([w.P[-1] if e == 1 else w.P[0] for w, e in ends])
    cos = math.cos(math.radians(max_kink))
    pairs = []
    for i, k in sorted(cKDTree(E).query_pairs(tol)):
        (wa, ea), (wb, eb) = ends[i], ends[k]
        if wa is wb or ea == eb:
            continue
        da = _unit_vec(E[i] - (wa.P[-2] if ea == 1 else wa.P[1]))     # out of each way at its end
        db = _unit_vec(E[k] - (wb.P[-2] if eb == 1 else wb.P[1]))
        if float(np.dot(da, db)) <= -cos and np.hypot(*(E[i] - E[k])) > merged:
            pairs.append((float(np.hypot(*(E[i] - E[k]))), i, k, da, db))
    took, n = set(), 0
    for dd, i, k, da, db in sorted(pairs, key=lambda t: t[:3]):
        if i in took or k in took:
            continue
        took |= {i, k}
        pa, pb = E[i], E[k]
        # pa + ta·da = pb + tb·db
        den = da[0] * (-db[1]) - da[1] * (-db[0])
        m = None
        if abs(den) > 1e-6:
            r = pb - pa
            ta = (r[0] * (-db[1]) - r[1] * (-db[0])) / den
            tb = (da[0] * r[1] - da[1] * r[0]) / den
            if abs(ta) <= tol and abs(tb) <= tol:
                m = pa + da * ta
        if m is None:
            m = (pa + pb) / 2.0
        for (w, e), d in ((ends[i], da), (ends[k], db)):
            _move_end(w, e, m, d)
            w.end_kind[e] = "continued"
        n += 1
        (wa, ea), (wb, eb) = ends[i], ends[k]
        net.L("концы проезжих частей продолжающих друг друга улиц соединены", [wa.id, wb.id], gap_m=round(dd, 2),
              x=round(float(m[0]), 1), z=round(float(m[1]), 1))
    return n


def _move_end(w, e, p, d):
    """Move end e of way w to point p, along its own direction d (out of the way): extend or trim; a point off that
    line (a joint of two parallel lines) replaces the end vertex. Spec structure chainages move with the start."""
    q = w.P[-1] if e == 1 else w.P[0]
    t = float(np.dot(p - q, d))
    L0 = w.L
    if abs(t) < 1e-9:
        P = w.P.copy()
    elif t > 0:
        P = np.vstack([w.P, q + d * t]) if e == 1 else np.vstack([q + d * t, w.P])
    else:
        P = G.cut(w.P, 0.0, w.L + t) if e == 1 else G.cut(w.P, -t, w.L)
    if e == 1:
        P[-1] = p
    else:
        P[0] = p
    w.P = P
    w.refresh()
    if e == 0:
        sh = w.L - L0
        w.lifts = [(a_ + sh, b_ + sh, why) for a_, b_, why in w.lifts]
        w.unders = [(a_ + sh, b_ + sh, why) for a_, b_, why in w.unders]


SNAP_KEEP_M = 1.0     # a street end is never trimmed back closer than this to the street's other end (a model parameter)


def snap_street_ends(net, spec, reach=20.0, back=12.0, min_ang=10.0):
    """A spec street drawn to the axis of a divided road ends in its median and touches neither carriageway. Each free
    end of a new street is moved along its own direction onto the road it ends at (the road with a carriageway
    nearest along the ray, within `reach` m): the far carriageway (both directions can turn), the near one for a
    right_in_right_out node or for the second of two streets that meet there from opposite sides (the first one
    already crosses to it); an end drawn a little past the road (`back` m) is trimmed back to it. A carriageway of a
    divided street meeting the road obliquely at an angle a crosses it e/tan(a) before or after the street's axis
    does (e: its offset from the axis), so it looks that much farther both ways. A road crossing the ray at less than
    `min_ang`° and a street of the same corridor (continuing this one) are not what the street ends at, nor is a road
    reached only by trimming the street back to within SNAP_KEEP_M of its other end (a short link looking back along itself
    onto the road its other end meets); a way that would still collapse is dropped with a log line. Ends at rings,
    interchanges, joints, spec `end` nodes and the area edge are left as drawn. A street ending on a loop (a spec street
    drawn closed, first point = last point, such as a turning ring) or on a road the ray crosses twice on one carriageway
    goes to the near side only: the far hit is the loop's other side, across its island. Returns the moved ends
    {(id(way), end)}."""
    import shapely
    skip = []
    for nd in spec.get("nodes", []):
        t = nd.get("type")
        p = np.array([float(nd["x"]), float(nd["z"])])
        if t in ("roundabout", "square"):
            skip.append((p, float((nd.get("params") or {}).get("r", (nd.get("params") or {}).get("r_m", 40.0))) + 40.0))
        elif t in INTERCHANGES:
            skip.append((p, 80.0))
        elif t in ("joint", "end", "edge"):
            skip.append((p, 3.0))
    riro = [np.array([float(nd["x"]), float(nd["z"])]) for nd in spec.get("nodes", []) if nd.get("type") == "right_in_right_out"]
    at_grade = [np.array([float(nd["x"]), float(nd["z"])]) for nd in spec.get("nodes", []) if nd.get("type") in AT_GRADE]
    targets = [o for o in net.ways if o.role == "primary" and o.cls not in NO_LIFT_OVER and o.cls != "ramp"]
    corr = street_corridors(spec)
    loops = {st["id"] for st in spec.get("streets") or [] if len(st.get("line") or []) > 2
             and np.hypot(*(np.asarray(st["line"][0], float) - np.asarray(st["line"][-1], float))) < 0.5}
    lines = [shapely.LineString(o.P) for o in targets]
    tree = shapely.STRtree(lines)
    done = []                                  # (point, direction) of ends already snapped to a far carriageway
    moved = set()
    for w in list(net.ways):
        if w.source != "new" or w.role != "primary" or w.cls in NO_LIFT_OVER or w.street is None:
            continue
        for e in (0, 1):
            if w.end_kind[e] is not None or len(w.P) < 2:
                continue
            p = w.P[-1] if e == 1 else w.P[0]
            q = w.P[-2] if e == 1 else w.P[1]
            if any(np.hypot(*(p - c)) < r for c, r in skip):
                continue
            d = _unit_vec(p - q)
            # the spec puts an at-grade node at this end: the street meets a road there, look twice as far
            rch = 2.0 * reach if any(np.hypot(*(p - c)) < 3.0 for c in at_grade) else reach
            ax = getattr(w, "axis_prof", None) or {}
            off = float(ax.get("cw_offset", 0.0)) if w.oneway and ax.get("carriageways") == 2 else 0.0
            obl = off / math.tan(math.radians(min_ang))
            ray = shapely.LineString([p - d * (back + obl), p + d * (rch + obl)])
            own = corr.get(w.street, w.street)
            hits = {}
            for i in tree.query(ray, predicate="intersects"):
                o = targets[i]
                if o.street == w.street or o is w:
                    continue
                ck = corr.get(o.street, o.street or o.id)
                if ck == own:
                    continue            # a street that continues this one
                for _, so, pt, ang in G.crossings(np.array(ray.coords), o.P):
                    if o.lifted_at(so) or o.under_at(so) or ang < min_ang:
                        continue        # passes over / under, or runs alongside
                    t = float(np.dot(np.asarray(pt) - p, d))
                    ext = off / math.tan(math.radians(ang))      # the carriageway's own shift along the road
                    if t < -(back + ext) or t > rch + ext:
                        continue        # a road the street crosses before its end, not the one it ends at
                    if t <= -(w.L - SNAP_KEEP_M):
                        continue        # the road at the street's other end: trimming to it would leave nothing
                    hits.setdefault(ck, []).append((t, o))
            if not hits:
                continue
            # one group per road: a divided street split into several spec streets is one corridor, so its two
            # carriageways are always found together (one piece's carriageway may end just short of the ray)
            key = min(hits, key=lambda k: min(abs(t) for t, _ in hits[k]))
            ts, way_at = [], []
            for t, o in sorted(hits[key], key=lambda h: h[0]):
                if not ts or t - ts[-1] > 0.5:
                    ts.append(t)
                    way_at.append(o)
            behind = [k for k, t in enumerate(ts) if t <= 0.5]
            k_near = behind[-1] if behind else 0                # the carriageway on the street's own side
            near, far = ts[k_near], ts[-1]
            # a loop (closed spec street, turning ring) or one carriageway crossed twice: its far hit is across the
            # loop's island, not the other carriageway of a divided road
            loop = len(ts) > 1 and (way_at[-1] is way_at[k_near] or any(o.street in loops for _, o in hits[key]))
            want_near = loop or any(np.hypot(*(p - c)) < 6.0 for c in riro) or any(
                np.hypot(*(p - dp)) < 3.0 and float(np.dot(d, dd)) < -0.5 for dp, dd in done)
            t = near if want_near else far
            if abs(t) < 0.05:
                continue
            new_p = p + d * t
            if t > 0:
                w.P = np.vstack([w.P, new_p]) if e == 1 else np.vstack([new_p, w.P])
            else:
                s_cut = w.L + t if e == 1 else -t
                w.P = G.cut(w.P, 0.0, s_cut) if e == 1 else G.cut(w.P, s_cut, w.L)
            if len(w.P) < 2 or G.chainage(w.P)[-1] < SNAP_KEEP_M:
                net.ways.remove(w)
                net.L("улица spec короче минимума после привязки концов к дорогам: отрезок снят", [w.id, key],
                      left_m=round(float(G.chainage(w.P)[-1]) if len(w.P) >= 2 else 0.0, 2), warn=True)
                break
            w.refresh()
            if e == 0:                          # chainages of the spec structures move with the start
                w.lifts = [(a_ + t, b_ + t, why) for a_, b_, why in w.lifts]
                w.unders = [(a_ + t, b_ + t, why) for a_, b_, why in w.unders]
            if not want_near:
                done.append((p, d))
            moved.add((id(w), e))
            net.L("конец улицы доведён до проезжей части дороги, к которой она примыкает"
                  + (" (ближней: правый поворот или встречный конец)" if want_near else " (дальней)"),
                  [w.id, key], moved_m=round(t, 1))
    return moved


def street_corridors(spec, tol=1.5, max_turn=30.0):
    """Spec streets that continue one another end to end (ends within tol m, directions within max_turn degrees) form
    one corridor: {street id: corridor key} (the key is the first street's id)."""
    ends = []
    for st in spec.get("streets") or []:
        L = np.array(st.get("line") or [], float)
        if len(L) < 2:
            continue
        ends.append((st["id"], L[0], _unit_vec(L[0] - L[1])))
        ends.append((st["id"], L[-1], _unit_vec(L[-1] - L[-2])))
    root = {sid: sid for sid, _, _ in ends}

    def find(a):
        while root[a] != a:
            root[a] = root[root[a]]
            a = root[a]
        return a
    cos = math.cos(math.radians(max_turn))
    if len(ends) > 1:
        from scipy.spatial import cKDTree
        for i, k in sorted(cKDTree(np.array([e[1] for e in ends])).query_pairs(tol + 1e-9)):
            (a, pa, da), (b, pb, db) = ends[i], ends[k]
            if a != b and np.hypot(*(pa - pb)) <= tol and float(np.dot(da, db)) <= -cos:
                ra, rb = find(a), find(b)
                if ra != rb:
                    root[max(ra, rb)] = min(ra, rb)       # a corridor's key is its smallest street id
    return {sid: find(sid) for sid in root}


def _unit_vec(v):
    n = float(np.hypot(v[0], v[1]))
    return np.asarray(v, float) / n if n > 1e-9 else np.array([1.0, 0.0])


def _road_for(net, ref, C, roads, osm_ways, spec, params=None):
    """Road object for a node's street reference: a spec street id, a level-0 axis id (existing → OSM carriageways)."""
    N = net.N
    ex = [w for w in osm_ways if ref in w.streets()]          # a chained way carries one street per OSM piece
    if ex and ref not in roads:
        w = min(ex, key=lambda w: G.project(w.P, C)[1])
        if w.cls == "expressway":
            pair_ref = (params or {}).get("major_pair") if (params or {}).get("major") == ref else None
            cands = [o for o in osm_ways if pair_ref and pair_ref in o.streets()]
            if cands:
                o = min(cands, key=lambda o: G.project(o.P, C)[1])
                return road_from_ways(N, "expressway", {+1: net_osm.virtual_carriageway(osm_ways, w),
                                                        -1: net_osm.virtual_carriageway(osm_ways, o)},
                                      street=ref, name_ru=w.name_ru, years=list(w.years))
            pair = net_osm.carriageway_pairs(osm_ways, C)
            if pair:
                return road_from_ways(N, "expressway", {+1: pair[0], -1: pair[1]}, street=ref, name_ru=w.name_ru,
                                      years=list(w.years))
        v = net_osm.virtual_carriageway(net.ways, w, reach=800.0, same_class=False)
        return road_from_ways(N, w.cls, {0: v}, street=ref, name_ru=w.name_ru, years=list(w.years))
    if ref in roads:
        r = min(roads[ref], key=lambda r: G.project(r.axis, C)[1])
        if not r.divided:
            # a minor road that ends near the node continues along the street it runs into (virtual chain)
            w0 = r.cws[0]
            v = net_osm.virtual_carriageway(net.ways, w0, reach=800.0, same_class=False)
            if v is not w0:
                r = road_from_ways(N, r.cls, {0: v}, street=r.street, name_ru=r.name_ru, years=r.years)
                r.prof = w0.prof
        return r
    axes = {a["id"]: a for a in spec.get("axes", [])}
    a = axes.get(ref)
    cls = AXIS_CLASS.get(a.get("class")) if a else None
    if ref.startswith("osm:") or (a and a.get("status") == "keep_existing"):
        if cls == "expressway" or cls is None:
            pair = net_osm.carriageway_pairs(osm_ways, C)
            if pair:
                wa, wb = pair
                return road_from_ways(N, "expressway", {+1: wa, -1: wb}, street=ref, name_ru=wa.name_ru,
                                      years=list(Y.EXISTING))
        near = [w for w in osm_ways if G.project(w.P, C)[1] < 40.0]
        if near:
            w = min(near, key=lambda w: G.project(w.P, C)[1])
            return road_from_ways(N, w.cls, {0: w}, street=ref, name_ru=w.name_ru, years=list(Y.EXISTING))
    return None


def build_nodes(net, spec, roads, osm_ways):
    N = net.N
    done = []
    for nd in spec.get("nodes", []):
        C = np.array([float(nd["x"]), float(nd["z"])])
        kind = nd.get("type")
        params = dict(nd.get("params") or {})
        if params.get("existing") or params.get("keep_existing"):
            rad = float(params.get("radius_m", 600.0))
            ids = set(params.get("osm_ids") or [])
            if ids:
                links = [w for w in osm_ways if w.cls == "ramp" and any(x in ids for x in w.source[4:].split("+"))]
            else:
                links = [w for w in osm_ways if w.cls == "ramp" and G.project(w.P, C)[1] < rad]
            for w in links:
                w.ic = nd["id"]
                w.role = "primary"           # existing OSM geometry: its levels come from Overture
            net.ics.append({"id": nd["id"], "template": kind, "x": round(C[0], 1), "z": round(C[1], 1),
                            "major": (list(nd.get("streets") or []) + [None, None])[0], "minor": (list(nd.get("streets") or []) + [None, None])[1],
                            "params": params, "notes": ["существующая развязка (OSM): съезды как в данных"],
                            "ramps": [w.id for w in links], "existing": True})
            net.L("развязка существующая: съезды из OSM", [nd["id"]] + [w.id for w in links], template=kind)
            done.append(nd["id"])
            continue
        if kind in ("roundabout", "square"):
            if "r" in params and "r_m" not in params:
                params["r_m"] = float(params["r"])
            try:
                ring(net, nd["id"], C, kind, params, name_ru=nd.get("name_ru", ""))
                done.append(nd["id"])
            except RingError as e:
                net.L(f"кольцо не построено: {e}", [nd["id"]], error=True)
            continue
        if kind in AT_GRADE or kind in ("diverge", "merge", "joint", "end", "edge", "ic"):
            net.spec_kinds.append((C, kind, nd["id"], set(nd.get("streets") or [])))
            done.append(nd["id"])
            continue
        if kind not in INTERCHANGES:
            net.L("тип узла неизвестен, узел не строится", [nd["id"]], type=kind)
            continue
        refs = list(nd.get("streets") or [])
        refs = [r for r in refs if r != params.get("major_pair")]
        rs = [(ref, _road_for(net, ref, C, roads, osm_ways, spec, params)) for ref in refs]
        rs = [(ref, r) for ref, r in rs if r is not None]
        if len(rs) < 2:
            net.L("развязка: не найдены две дороги узла", [nd["id"]], streets=refs, error=True)
            continue
        major_ref = params.get("major")
        rs.sort(key=lambda t: (0 if t[0] == major_ref else 1, N.class_rank(t[1].cls)))
        major, minor = rs[0][1], rs[1][1]
        try:
            res = T.build(kind, nd["id"], C, major, minor, params, N)
        except T.TemplateError as e:
            net.L(f"шаблон {kind} не вписан: {e}; вместо него путепровод без съездов", [nd["id"]], error=True)
            res = T.build("grade_separation", nd["id"], C, major, minor, params, N)
            res.template = kind
        rec = apply_result(net, res)
        rec["lifted"] = [w.id for w, *_ in res.lifted]
        for hr in params.get("hand_ramps") or []:
            hw = [w for w in net.ways if hr in w.streets()]
            for w in hw:
                w.ic = nd["id"]
                rec["ramps"].append(w.id)
            net.L("ручной съезд из spec вместо съезда шаблона", [nd["id"], hr], found=len(hw))
        if params.get("ramps_hint"):
            net.L("ramps_hint: форма съездов строится шаблоном, подсказка не используется для геометрии",
                  [nd["id"]], quadrants=sorted(params["ramps_hint"]))
        net.L(f"развязка {kind}: построено {len(res.ramps)} съездов", [nd["id"]] + rec["ramps"], notes=res.notes)
        done.append(nd["id"])
    return done


def auto_grade_separation(net):
    """A new road crossing an expressway or a ramp where no node is defined passes over it."""
    import shapely
    fast = [o for o in net.ways if o.cls in NO_LIFT_OVER]
    if not fast:
        return
    tree = shapely.STRtree([shapely.LineString(o.P) for o in fast])
    for w in net.ways:
        if w.source != "new" or w.role != "primary" or w.cls in NO_LIFT_OVER:
            continue
        for k in sorted(tree.query(shapely.LineString(w.P), predicate="intersects")):      # in net.ways order
            o = fast[k]
            if o is w:
                continue
            for sa, sb, pt, ang in G.crossings(w.P, o.P):
                if w.lifted_at(sa) or w.under_at(sa):
                    continue
                half = (o.prof["cw_w"] if o.prof else 10.0) / 2.0 + 8.0
                h = half / max(math.sin(math.radians(max(ang, 20.0))), 0.3)
                w.lifts.append((sa - h, sa + h, "auto"))
                net.L("новая улица пересекает скоростную дорогу или съезд без узла: проходит над ней (путепровод)",
                      [w.id, o.id], x=round(float(pt[0]), 1), z=round(float(pt[1]), 1))


def arms(n):
    k = 0
    for w, s in n.uses:
        k += 1 if (s < 0.05 or s > w.L - 0.05) else 2
    return k


def node_kinds(net, city_poly, edge_joints):
    import shapely
    N = net.N
    for n in net.nodes:
        a = arms(n)
        ic = {w.ic for w, _ in n.uses if w.ic}
        if not n.ic and len(ic) == 1:
            n.ic = next(iter(ic))
        if n.kind in ("roundabout", "square", "diverge", "merge", "crossing_signal", "crossing", "right_in_right_out"):
            continue
        if a == 1:
            w, s = n.uses[0]
            e = 0 if s < 0.05 else 1
            if w.end_kind[e] == "joint":
                n.kind = "joint"
                n.ref = w.end_ref[e]
            elif city_poly is not None and city_poly.exterior.distance(shapely.Point(n.p)) < 5.0:
                n.kind = "edge"
            else:
                n.kind = "end"
            continue
        cls = sorted({w.cls for w, _ in n.uses}, key=N.class_rank)
        if n.kind == "ic" or (a == 2 and n.ic):
            n.kind = "ic"
            continue
        if a == 2:
            n.kind = "ic" if n.ic else N.default_node(cls[0], cls[-1])
            continue
        if n.ic and all(w.role == "ramp" or w.ic for w, _ in n.uses):
            n.kind = "ic" if n.kind is None else n.kind
            continue
        n.kind = N.default_node(cls[0], cls[1] if len(cls) > 1 else cls[0])
    # joints: area edge / keep / city joints (edge_joints of the spec by proximity)
    # each joint node takes the nearest edge joint (≤ 30 m), one to one, nearest pairs first; a spec joint that names
    # a street wins over one without (twin road cut at the edge) and over a city.json joint at the same place
    jn = [n for n in net.nodes if n.kind == "joint"]
    pairs = []
    for i, n in enumerate(jn):
        for k, ej in enumerate(edge_joints):
            dd = float(np.hypot(n.p[0] - ej["x"], n.p[1] - ej["z"]))
            if dd < 30.0:
                rank = 0 if ej.get("street") else (1 if ej.get("spec", True) else 2)
                pairs.append((dd + 5.0 * rank, i, k))
    took_n, took_j, name = set(), set(), {}
    for _, i, k in sorted(pairs):
        if i in took_n or k in took_j:
            continue
        took_n.add(i)
        took_j.add(k)
        name[i] = edge_joints[k]["id"]
    net.joints = [{"id": name.get(i) or f"{n.ref or 'joint'}@{n.id}", "node": n.id} for i, n in enumerate(jn)]


def apply_spec_kinds(net, tol=3.0, corridor=15.0):
    """Node types the spec lists (crossing, crossing_signal, right_in_right_out, diverge, merge, joint, end) win over
    the defaults (rings and template nodes keep theirs). A spec node is a point on the street axes; at a divided road
    the junction is several network nodes (one per carriageway), so an at-grade type goes to every node within
    `corridor` m where the node's streets meet; other types go to the nearest node within tol m."""
    if not net.spec_kinds or not net.nodes:
        return
    from scipy.spatial import cKDTree
    P = np.array([n.p for n in net.nodes])
    tree = cKDTree(P)
    miss = []
    for p, kind, nid, streets in net.spec_kinds:
        hit = []
        if kind in AT_GRADE and streets:
            for i in tree.query_ball_point(p, corridor):
                n = net.nodes[i]
                st = set().union(*(w.streets_near(n.p) for w, _ in n.uses))
                if len(st & streets) >= 2 or (len(st & streets) >= 1 and arms(n) >= 3):
                    hit.append(n)
        if not hit:
            d, i = tree.query(p)
            if d <= tol:
                hit = [net.nodes[i]]
        if not hit:
            miss.append(nid)
            continue
        for n in hit:
            if n.kind in ("roundabout", "square"):
                continue
            if kind in ("joint", "end", "edge") and arms(n) != 1:
                continue
            n.kind = kind
            n.ref = n.ref or nid
    if miss:
        net.L(f"узлы spec не совпали с узлами сети ({tol:.0f} м): тип по умолчанию", miss)


def five_arm_rings(net, spec, same_junction_m=30.0):
    """5+ arm at-grade nodes become roundabouts (rule 6); returns True when the network changed. One junction gets one
    ring: a ring stands at the spec node when one is within same_junction_m (the carriageway crossings of a divided
    road are nodes of the same junction), and a 5+ arm node inside or next to a ring already built here is part of
    that ring, not a second one."""
    changed = False
    spec_nodes = [(np.array([float(nd["x"]), float(nd["z"])]), nd) for nd in spec.get("nodes", [])]
    built = []                                   # (centre, r, ring id)
    for n in list(net.nodes):
        if arms(n) >= 5 and n.kind not in ("roundabout", "square") and not n.ic:
            if any(w.cls in NO_LIFT_OVER for w, _ in n.uses):
                continue
            C, snd = n.p, None
            if spec_nodes:
                q, nd = min(spec_nodes, key=lambda t: float(np.hypot(*(t[0] - n.p))))
                if np.hypot(*(q - n.p)) < same_junction_m:
                    C, snd = q, nd
            twin = [rid for c, r, rid in built if np.hypot(*(C - c)) < r + same_junction_m]
            if twin:
                net.L("узел с 5+ лучами входит в уже построенное кольцо того же перекрёстка", [n.id, twin[0]],
                      x=round(float(n.p[0]), 1), z=round(float(n.p[1]), 1))
                continue
            rid = f"ring_{snd['id'] if snd else n.id}"
            try:
                rec = ring(net, rid, C, "roundabout", {})
                built.append((np.asarray(C, float), float(rec["params"]["r_m"]), rid))
                net.L("узел с 5+ лучами: построено кольцо"
                      + (f" в центре узла spec {snd['id']} ({snd.get('type')} заменён кольцом по п. 6)" if snd else ""),
                      [rid] + ([snd["id"]] if snd else []), x=round(float(C[0]), 1), z=round(float(C[1]), 1))
                changed = True
            except RingError as e:
                net.L(f"узел с 5+ лучами: кольцо не вписано ({e})", [n.id], error=True)
    return changed


def year_gaps(net, segs, reach=20.0):
    """A divided street's year split stands where its axis is split; each carriageway is split at its own node there,
    and a road ending at the street T-snaps to the far carriageway (snap_street_ends). Where the two do not meet, one
    carriageway end (or the T end) stands blind in the year it is built, e.g. a split at the median crossing while the
    cross road's far carriageway lies a few m on, in the next year's piece. Per scenario and per year: the end of a new
    road that is a dead end in that year (not a joint or edge) but not in the final network, and that a few m of later
    carriageway (oneway pieces of new streets, no ramps or interchanges, at most `reach` m in all, as snap_street_ends
    looks) link to a node already standing that year, gets those pieces built in that year: the year split lands on
    the junction for both carriageways. Existing years are never moved. Logs each gap; returns the pieces moved."""
    import heapq
    from collections import defaultdict
    kind = {n.id: n.kind for n in net.nodes}
    pos = {n.id: n.p for n in net.nodes}
    at = defaultdict(list)
    for i, s in enumerate(segs):
        at[s["a"]].append(i)
        at[s["b"]].append(i)
    length = [G.length(np.array([p[:2] for p in s["pts"]])) for s in segs]
    gap_ok = [bool(s["oneway"]) and s["class"] != "ramp" and not s["ic"] and s.get("_source") == "new" for s in segs]
    moved = 0
    for k, scen in enumerate(Y.SCENARIOS):
        done = set()
        while True:
            years = sorted({int(s["years"][k]) for s in segs if int(s["years"][k]) > Y.EXISTING[k]})
            fixed = False
            for yr in years:
                deg = defaultdict(int)
                for s in segs:
                    if int(s["years"][k]) <= yr:
                        deg[s["a"]] += 1
                        deg[s["b"]] += 1
                for nid in [n for n, dg in deg.items() if dg == 1]:
                    if kind.get(nid) in ("joint", "edge") or len(at[nid]) < 2 or (nid, yr) in done:
                        continue
                    done.add((nid, yr))
                    s0 = next(segs[i] for i in at[nid] if int(segs[i]["years"][k]) <= yr)
                    if int(s0["years"][k]) <= Y.EXISTING[k]:
                        continue                 # an existing road's end: as its source draws it, not a year split
                    # shortest run of later carriageway pieces from the dead end to a node standing in yr
                    best, heap, prev = {nid: 0.0}, [(0.0, nid)], {}
                    goal = None
                    while heap:
                        dist, u = heapq.heappop(heap)
                        if dist > best.get(u, 1e18):
                            continue
                        if u != nid and deg.get(u, 0) > 0:
                            goal = u
                            break
                        for i in at[u]:
                            s = segs[i]
                            if int(s["years"][k]) <= yr or not gap_ok[i]:
                                continue
                            v = s["b"] if s["a"] == u else s["a"]
                            nd = dist + length[i]
                            if nd <= reach and nd < best.get(v, 1e18):
                                best[v], prev[v] = nd, (u, i)
                                heapq.heappush(heap, (nd, v))
                    if goal is None:
                        continue
                    run, v = [], goal
                    while v != nid:
                        v, i = prev[v]
                        run.append(i)
                    was = sorted({int(segs[i]["years"][k]) for i in run})
                    for i in run:
                        segs[i]["years"][k] = yr
                    moved += len(run)
                    fixed = True
                    gap = segs[run[0]]
                    net.L(f"конец {s0.get('street') or s0['class']} стоял бы тупиком в {yr} г. ({scen}): "
                          f"{best[goal]:.1f} м проезжей части {gap.get('street') or gap['class']} "
                          f"({', '.join(map(str, was))} г.) строятся в {yr} г., граница очереди ложится на узел "
                          f"для обеих проезжих частей", [s0["id"], nid] + [segs[i]["id"] for i in run] + [goal],
                          scenario=scen, year=yr, x=round(float(pos[nid][0]), 1), z=round(float(pos[nid][1]), 1))
                    break                        # degrees changed: count them again
                if fixed:
                    break
            if not fixed:
                break
    return moved


def export(net, spec, d, area, segs):
    N = net.N
    profiles = {}
    for w in net.ways:
        for pid, prof in [(w.pid, w.prof)] + list((getattr(w, "stage_prof", None) or {}).items()):
            if pid not in profiles and prof:
                profiles[pid] = {k: (list(v) if isinstance(v, (list, tuple)) else v) for k, v in prof.items() if k in PROFILE_FIELDS}
    nodes = [{"id": n.id, "x": jio.r2(n.p[0]), "z": jio.r2(n.p[1]), "y": jio.r2(n.y if n.y is not None else 0.0),
              "kind": n.kind, "ic": n.ic, "r": n.r, **({"lrt": n.lrt} if getattr(n, "lrt", None) else {})} for n in net.nodes]
    seg_by_way = {}
    for s in segs:
        seg_by_way.setdefault(s["_way"], []).append(s)
    ics = []
    for rec in net.ics:
        ramp_ids = [s["id"] for wid in rec.get("ramps", []) for s in seg_by_way.get(wid, [])]
        struct_ids = []
        C = np.array([rec["x"], rec["z"]])
        for s in segs:
            if not any(r["kind"] in ("overpass", "bridge") for r in s["struct"]):
                continue
            if s["ic"] == rec["id"] or s["_way"] in rec.get("lifted", []):
                P = np.array([p[:2] for p in s["pts"]])
                if s["ic"] == rec["id"] or G.project(P, C)[1] < 400.0:
                    struct_ids.append(s["id"])
        ics.append({"id": rec["id"], "template": rec["template"], "x": rec["x"], "z": rec["z"], "major": rec.get("major"),
                    "minor": rec.get("minor"), "ramps": ramp_ids, "structures": struct_ids,
                    "params": rec.get("params"), "notes": rec.get("notes")})
        if rec.get("ramp_lanes"):
            ics[-1]["ramp_lanes"] = [{"key": r["key"], "lanes": r["lanes"], "from_year": r["from_year"],
                                      "segments": [s["id"] for wid in r["_ways"] for s in seg_by_way.get(wid, [])]}
                                     for r in rec["ramp_lanes"]]
    out_segs = [{k: v for k, v in s.items() if not k.startswith("_")} for s in segs]
    return {"schema": "qtwin.network/1", "district": d,
            "area": [[jio.r1(x), jio.r1(z)] for x, z in np.array(area.exterior.coords)[:-1]],
            "profiles": profiles, "nodes": nodes, "segments": out_segs, "interchanges": ics, "joints": net.joints,
            "log": net.log}


def main(argv=None):
    import shapely
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("district")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-grid", action="store_true")
    ap.add_argument("--grid", action="store_true", help="local grid even when the spec draws its streets (v1)")
    ap.add_argument("--no-village", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    d = paths.district_id(a.district)
    spec = jio.load_spec(a.district)
    city = jio.load_city()
    N = norms.get()
    area = area_polygon(spec, city)
    net = Network(N, d, area)
    net.hints = []
    net.rail = rail.tracks(area, 50.0)            # decks over the tracks (heights), no village lane across them
    net.water = _water(area)                      # bridges (structures), no village lane through water
    net.lrt_ground = lrt_ground(spec, d, area, N)  # level-crossing nodes where the ground LRT crosses a road (planarize 3b)
    keep_polys = {k["id"]: shapely.Polygon(k["polygon"]).buffer(0) for k in spec.get("keep", []) if k.get("polygon")}
    attach = {k["id"]: k.get("attach") or [] for k in spec.get("keep", [])}
    zones = spec.get("zones", [])
    retire = {r["osm"]: r.get("why_ru", "") for r in spec.get("retire_existing", [])}
    for oid in spec.get("replaced_osm") or []:
        retire[oid] = "replaced_osm (spec)"
    keep = {}
    for st in spec.get("streets") or []:
        src = st.get("source") or ""
        if src.startswith("keep_existing:"):
            keep[src.split(":", 1)[1]] = st
    net.spec_kinds = []
    osm_ways = net_osm.load(net, area, zones, retire, keep)
    if keep:
        got = {w.source[4:] for w in osm_ways}
        miss = [k for k in keep if not any(k in g for g in got)]
        if miss:
            net.L("улицы keep_existing без дороги OSM в участке", [keep[k]["id"] for k in miss], error=True)
    roads = build_streets(net, spec, area, keep_polys, attach)
    join_carriageway_ends(net, snap_street_ends(net, spec))
    build_nodes(net, spec, roads, osm_ways)
    auto_grade_separation(net)
    # a spec v1 draws its local streets: the generated grid is for level-0 specs (axes only) unless asked for
    grid = a.grid or (not a.no_grid and not spec.get("streets"))
    if spec.get("streets") and not grid:
        net.L("местная сеть не генерируется: spec v1 задаёт улицы сам (--grid включает сетку)", [])
    if grid or not a.no_village:
        import net_grid
        if grid:
            net_grid.local_grid(net, spec, area, keep_polys)
        if not a.no_village:
            net_grid.village_lanes(net, spec, area)
    net.planarize()
    assign_hints(net)
    if five_arm_rings(net, spec):
        net.planarize()
        assign_hints(net)
    net.mid_block_crossings(REGULATED, float(N.norm("crossings.at_grade_spacing_regulated_m")["max"]))
    city_poly = city_polygon(city)
    edge_joints = list(spec.get("edge_joints") or [])
    for j in ((city.get("joints") or {}).get("items") or []):
        if area.buffer(30.0).contains(shapely.Point(j["x"], j["z"])) and j.get("kind") == "road":
            edge_joints.append({"id": j["id"], "x": j["x"], "z": j["z"], "spec": False})
    node_kinds(net, city_poly, edge_joints)
    apply_spec_kinds(net)
    lrt_crossing_kinds(net)
    ramp_lanes(net, spec)
    for ej in spec.get("edge_joints") or []:
        if ej.get("street") is None:
            net.L("стык на границе участка без продолжения: дорога двойника обрезана здесь и не продолжается",
                  [ej["id"]], twin_edge=ej.get("twin_edge"), connects=ej.get("connects"))
        elif not any(j for j in net.joints if j["id"] == ej["id"]):
            net.L("стык spec не совпал с концом улицы на границе (30 м)", [ej["id"], ej.get("street")],
                  x=ej["x"], z=ej["z"])
    net.heights()
    rail_at_grade(net)
    net.structures()
    segs = net.segments()
    year_gaps(net, segs)
    doc = export(net, spec, d, area, segs)
    if spec.get("utilities") is not None:
        doc["utilities"] = spec["utilities"]
    path = paths.out_file(d, "network.json", a.out)
    size = jio.save_json(doc, path, indent=1)
    km = {}
    for s in doc["segments"]:
        P = np.array([p[:2] for p in s["pts"]])
        km[s["class"]] = km.get(s["class"], 0.0) + G.length(P) / 1000.0
    from collections import Counter
    kinds = Counter(n["kind"] for n in doc["nodes"])
    st = Counter(r["kind"] for s in doc["segments"] for r in s["struct"] if r["kind"] != "ground")
    print(f"gen_network {d}: {len(doc['segments'])} отрезков, {len(doc['nodes'])} узлов, "
          f"{len(doc['interchanges'])} развязок, {size / 1e6:.2f} МБ, {time.time() - t0:.1f} с → {path}")
    print("  км по классам: " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(km.items(), key=lambda t: -t[1])))
    print("  узлы: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    print("  сооружения (участков): " + ", ".join(f"{k} {v}" for k, v in st.most_common()))
    errs = [e for e in net.log if e.get("error")]
    for e in errs:
        print("  ! " + e["what"], e["ids"][:4])
    return 0


LOOKALIKE = str.maketrans("ABCEHKMOPTXY", "АВСЕНКМОРТХУ")


def _fold(t):
    """A road name or token for matching: Latin letters that look Cyrillic read as Cyrillic, case and punctuation dropped."""
    return "".join(ch for ch in str(t).upper().translate(LOOKALIKE).lower() if ch.isalnum())


def _compass(v):
    a = math.degrees(math.atan2(float(v[1]), float(v[0]))) % 360.0
    return "E" if a < 45 or a >= 315 else ("N" if a < 135 else ("W" if a < 225 else "S"))


def _way_ends(w):
    """(start node, end node) of a way after planarize (None where its end is no node)."""
    cs = sorted(w.cuts, key=lambda c: c[0]) if getattr(w, "cuts", None) else []
    a = cs[0][1] if cs and cs[0][0] < 0.05 else None
    b = cs[-1][1] if cs and cs[-1][0] > w.L - 0.05 else None
    return a, b


def _road_at(n, ramp, s_ramp):
    """The road (a non-ramp way at node n) a ramp leaves or joins at its chainage s_ramp: the one whose direction of
    travel there best follows the ramp's. Returns (way, compass of travel, chainage, any direction) or None; any direction: a two-way road
    the ramp meets at more than 60° (a diamond terminal), whose traffic leaves or comes either way."""
    t = G.tangent_at(ramp.P, s_ramp, ramp.S)                 # a ramp runs one way: its direction is its travel
    best = None
    for w, s in n.uses:
        if w.cls == "ramp" or w.role == "ramp":
            continue
        a, b = w.at(max(s - 3.0, 0.0)), w.at(min(s + 3.0, w.L))
        d = (b - a) / max(float(np.hypot(*(b - a))), 1e-9)
        if not w.oneway and float(np.dot(d, t)) < 0:
            d = -d
        sc = float(np.dot(d, t))
        if best is None or sc > best[0]:
            best = (sc, w, _compass(d), s, not w.oneway and sc < 0.5)
    return None if best is None else best[1:]


def _road_names(w, s):
    q = w.piece_at(w.at(s))
    return set(w.streets_near(w.at(s))) | {w.street} - {None}, _fold(q[2] if q is not None else w.name_ru)


def ramp_lanes(net, spec):
    """Spec interchange `ramps` {<ramp id or movement>: {lanes, from_year?, why_ru?}} (template and kept existing
    interchanges alike): the ramp gets `lanes` lanes, from its opening (its profile) or from from_year (a year or 4,
    per scenario: segment `stages` [{years, pid, lanes, why_ru}], a reconstruction «модель qTwin»; the kept geometry
    stays, only lanes and width change). A ramp id is a spec street of the ramp (keep_existing k_…, a hand ramp): the
    ramp from branch point to branch point. A movement «<road> <N|S|E|W>[B] → <road> <N|S|E|W>[B]» (a road: its spec
    street id or the start of its name, Latin look-alike letters read as Cyrillic) is the movement's own ramp pieces
    from the diverge to the merge (pieces it shares with another movement keep theirs). Two or more lanes are
    ramps.width_wsdot_m two_lanes_min / 2 each; the red line grows by the extra carriageway width."""
    import re
    rx = re.compile(r"^\s*(.+?)\s+([NSEW])B?\s*(?:→|->|>)\s*(.+?)\s+([NSEW])B?\s*$", re.I)
    N = net.N
    lane2 = float(N.norm("ramps.width_wsdot_m")["two_lanes_min"]) / 2.0
    for nd in spec.get("nodes") or []:
        req = nd.get("ramps") or (nd.get("params") or {}).get("ramps")
        if not req:
            continue
        ws = [w for w in net.ways if w.ic == nd["id"] and w.cls == "ramp"]
        if not ws:
            net.L("spec ramps: у развязки нет съездов в сети", [nd["id"]], error=True)
            continue
        ends = {id(w): _way_ends(w) for w in ws}
        start_at = {}
        for w in ws:
            start_at.setdefault(id(ends[id(w)][0]), []).append(w)

        def roads(n):
            return n is not None and any(w.cls != "ramp" and w.role != "ramp" for w, _ in n.uses)
        paths = []
        for w in ws:
            n0 = ends[id(w)][0]
            if not roads(n0):
                continue
            stack = [[w]]
            while stack and len(paths) < 400:
                path = stack.pop()
                n1 = ends[id(path[-1])][1]
                if n1 is None:
                    continue
                if roads(n1):
                    paths.append(path)
                    continue
                for w2 in start_at.get(id(n1), []):
                    if w2 not in path and len(path) < 30:
                        stack.append(path + [w2])
        moves = []
        for path in paths:
            fr = _road_at(ends[id(path[0])][0], path[0], 0.0)
            to = _road_at(ends[id(path[-1])][1], path[-1], path[-1].L)
            if fr and to:
                moves.append((fr, to, path))
        mkey = lambda fr, to: (id(fr[0]), fr[1], id(to[0]), to[1])         # noqa: E731
        n_moves = {}
        for fr, to, path in moves:
            for w in path:
                n_moves.setdefault(id(w), set()).add(mkey(fr, to))
        for key, want in req.items():
            lanes = int(want.get("lanes") or 0)
            if lanes < 1:
                net.L("spec ramps: lanes не задано или < 1", [nd["id"], key], error=True)
                continue
            m = rx.match(str(key))
            hit = []
            if m:
                ft, fd, tt, td = m.group(1), m.group(2).upper(), m.group(3), m.group(4).upper()

                def match(tok, r):
                    ids, name = _road_names(r[0], r[2])
                    return tok in ids or (bool(_fold(tok)) and name.startswith(_fold(tok)))
                mine = [(fr, to, path) for fr, to, path in moves if (fr[1] == fd or fr[3]) and (to[1] == td or to[3])
                        and match(ft, fr) and match(tt, to)]
                keys = {mkey(fr, to) for fr, to, _ in mine}
                for fr, to, path in mine:
                    own = [w for w in path if n_moves[id(w)] <= keys]
                    hit += own or path
            else:
                hit = [w for w in ws if key in w.streets()]
                grow = True
                while grow:
                    grow = False
                    for w in list(hit):
                        a, b = ends[id(w)]
                        for n, nxt in ((b, start_at.get(id(b), [])), (a, [o for o in ws if ends[id(o)][1] is a])):
                            if n is None or roads(n) or len(n.uses) != 2 or len(nxt) != 1 or nxt[0] in hit:
                                continue
                            hit.append(nxt[0])
                            grow = True
            hit = list({id(w): w for w in hit}.values())
            if not hit:
                net.L("spec ramps: ключ не нашёл съезда развязки (id улицы съезда или движение «дорога N → дорога W»)",
                      [nd["id"], key], error=True,
                      movements=sorted({f"{fr[0].street or _road_names(fr[0], fr[2])[1][:12]} {'*' if fr[3] else fr[1]} → "
                                        f"{to[0].street or _road_names(to[0], to[2])[1][:12]} {'*' if to[3] else to[1]}"
                                        for fr, to, _ in moves}))
                continue
            fy = want.get("from_year")
            fy4 = None if fy is None else ([int(fy)] * 4 if not isinstance(fy, (list, tuple)) else [int(v) for v in fy])
            rec = next((r for r in net.ics if r["id"] == nd["id"]), None)
            if rec is not None:
                rec.setdefault("ramp_lanes", []).append({"key": key, "lanes": lanes, "from_year": fy4, "_ways": [w.id for w in hit]})
            for w in hit:
                prof = dict(w.prof or N.profile("ramp"))
                base_w = sum((prof.get("lanes") or [1, 0])) * float(prof.get("lane_w") or 0.0)
                lw = lane2 if lanes >= 2 else float(prof.get("lane_w") or lane2)
                prof["lanes"] = [lanes, 0]
                prof["lane_w"] = round(lw, 2)
                if prof.get("red_line_w") is not None:
                    prof["red_line_w"] = round(float(prof["red_line_w"]) + lanes * lw - base_w, 2)
                pid = f"{w.pid}_l{lanes}"
                y4 = None if fy4 is None else [max(int(a), int(b)) for a, b in zip(fy4, w.years)]
                if y4 is None or y4 == [int(v) for v in w.years]:
                    w.pid, w.prof = pid, prof
                    net.L(f"spec ramps: съезд развязки {nd['id']} — {lanes} полосы с открытия", [nd["id"], key, w.street or w.id])
                else:
                    why = want.get("why_ru") or f"реконструкция съезда: {lanes} полосы с {y4[0]} г. (модель qTwin)"
                    w.stages = [{"years": y4, "pid": pid, "lanes": lanes, "why_ru": why}]
                    w.stage_prof = {pid: prof}
                    net.L(f"spec ramps: съезд развязки {nd['id']} — {lanes} полосы с {y4} (реконструкция, модель qTwin)",
                          [nd["id"], key, w.street or w.id])


def lrt_ground(spec, d, area, N):
    """[(line id, Nx2)]: the ground runs of the spec LRT lines in the area, laid out as gen_lrt lays them (corners
    rounded to lrt.min_curve_radius_m, clipped to the area, spec sections by projection; elevated and tunnel sections
    left out)."""
    import gen_lrt
    lines, _ = gen_lrt.spec_lines(spec, d)
    out, log = [], []
    Rmin = float(N.norm("lrt.min_curve_radius_m"))
    for ln in lines:
        P0 = gen_lrt.fillet(np.asarray(ln["line"], float), Rmin, log, ln["id"])
        parts = gen_lrt.clip(P0, area, log, ln["id"])
        for k, P in enumerate(parts):
            lid = ln["id"] if len(parts) == 1 else f"{ln['id']}#{k + 1}"
            P = G.densify(P, gen_lrt.STEP)
            S = G.chainage(P)
            for a, b, kind in gen_lrt.sections_of(P, ln.get("sections")):
                if kind != "ground" or b - a < 1.0:
                    continue
                m = (S >= a - 1e-6) & (S <= b + 1e-6)
                R = np.vstack([G.point_at(P, a, S), P[m], G.point_at(P, b, S)])
                out.append((lid, G.dedup(R)))
    return out


def lrt_crossing_kinds(net):
    """A node where the ground LRT crosses a road in one level is a level crossing with signals (lrt.at_grade_crossing):
    kind crossing_signal (the film's signals) with `lrt` = the line, unless it is a ring, square or interchange node
    with ramps (logged); a road's own node inside an interchange zone (kind ic, no ramp) is a level crossing too. A
    crossing on a road the LRT may not cross at grade (a ramp, an expressway, a continuous arterial) gets no node and
    is an error of the log (rule 6 reports it)."""
    for n in net.nodes:
        if not getattr(n, "lrt", None):
            continue
        st = sorted({w.street or w.cls for w, _ in n.uses})
        plain_ic = n.kind == "ic" and all(w.cls != "ramp" and w.role != "ramp" for w, _ in n.uses)   # a road through an ic zone
        if n.kind in (None, "crossing", "crossing_signal", "right_in_right_out") or plain_ic:
            n.kind = "crossing_signal"
            net.L("ЛРТ на земле пересекает улицу в одном уровне: узел-переезд со светофором (lrt.at_grade_crossing)",
                  [n.lrt, n.id] + st, x=jio.r1(n.p[0]), z=jio.r1(n.p[1]))
        else:
            net.L(f"ЛРТ на земле пересекает узел {n.kind}: тип узла оставлен", [n.lrt, n.id] + st,
                  x=jio.r1(n.p[0]), z=jio.r1(n.p[1]))
    seen = set()
    for w, s, pt, line in getattr(net, "lrt_forbidden", []):
        key = (line, w.street or w.id, round(float(pt[0])), round(float(pt[1])))
        if key in seen:
            continue
        seen.add(key)
        net.L(f"ЛРТ на земле пересекает {w.cls} в одном уровне: здесь переезд не допускается, нужна эстакада или тоннель "
              f"(lrt.at_grade_crossing)", [line, w.street or w.id], error=True, x=jio.r1(pt[0]), z=jio.r1(pt[1]), cls=w.cls)


def rail_at_grade(net):
    """Log the crossings of a railway track in one level (no deck or tunnel of the road there, the track not on a bridge):
    a new road needs a spec struct overpass / tunnel (an error of the log and of rule 6), an existing road keeps its
    level crossing as in OSM."""
    seen = set()
    for w, s, pt, tid in net.rail_at_grade:
        new = int(w.years[0]) > Y.EXISTING[0]
        key = (w.street or w.id, tid, round(float(pt[0])), round(float(pt[1])))
        if key in seen:
            continue
        seen.add(key)
        if new:
            net.L("новая дорога пересекает ж/д в одном уровне: нужен путепровод или тоннель (struct в spec)",
                  [w.street or w.id, tid], error=True, x=round(float(pt[0]), 1), z=round(float(pt[1]), 1), cls=w.cls)
        else:
            net.L("существующий переезд через ж/д (как в OSM)", [w.street or w.id, tid],
                  x=round(float(pt[0]), 1), z=round(float(pt[1]), 1), cls=w.cls)


def _water(area):
    import shapely
    try:
        gj = jio.load_geojson(paths.w34("osm", "water.geojson"))
    except FileNotFoundError:
        return None
    polys = []
    for f in gj:
        g = shapely.geometry.shape(f["geometry"])
        if g.geom_type in ("Polygon", "MultiPolygon") and g.intersects(area):
            polys.append(g.intersection(area))
    return shapely.union_all(polys) if polys else None


if __name__ == "__main__":
    sys.exit(main())
