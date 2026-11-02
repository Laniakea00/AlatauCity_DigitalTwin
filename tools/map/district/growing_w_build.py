#!/usr/bin/env python3
"""Growing-West · level 2 · spec v1 builder (w52): writes tools/map/spec/growing_w.json from the level-0 scheme
(district/growing_w_v0.json), the open data and the cartographer's design, then runs the self-check growing_w_check.py.

    python3 -I tools/map/district/growing_w_build.py [--out PATH] [--no-check]

Sections: 1. LRT line (in the median of the airport trunk); 2. local streets and the post-pass (growing_w_net);
3. LRT v1 (stations between cross streets); 4. zones (airport lot, sorting yard, rail corridors, sanitary gaps, coverage);
5. targets and densities; 6. objects (registry rows, «по источнику / по правилу»); 7. corridors with voltage;
8. joints, phases, axes; 9. the spec. Every coordinate not from a source is labelled «модель qTwin».
"""
import copy
import json
import math
import os
import sys
import time

T0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import substring, unary_union  # noqa: E402

import growing_w_common as C  # noqa: E402
import growing_w_zones as Z  # noqa: E402
import growing_w_net as N  # noqa: E402
import land_util as LU  # noqa: E402

SPEC_OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(C.SPEC_DIR, "growing_w.json")
MODEL = C.MODEL
Y4 = C.Y4
CITY = C.CITY
REG = C.REG
POLY = C.POLY
V0 = C.spec_v0()
LOG = []


def P1(p):
    return [round(float(p[0]), 1), round(float(p[1]), 1)]


poly_pts = C.poly_pts

# ===================================================================================================== 1. LRT line
LRT_W = float(LU.Norms().v("lrt.corridor_width_m", "double_track"))
J062 = (N.JOINT["J062"]["x"], N.JOINT["J062"]["z"])
TL = N.TL
P_M = C.on_line(N.TRUNK, x=-1150.0)
S_M = TL.project(Point(P_M))
S_END = TL.length - 40.0                         # the line stops 40 m short of the trunk's end at the terminal
# into the median along the trunk's own direction: the last 120 m before P_M lie on the trunk's tangent at P_M, so the
# curve meets the median without a kink (rule 25: curve radius)
_tm = np.array(TL.interpolate(S_M + 2.0).coords[0]) - np.array(TL.interpolate(S_M - 2.0).coords[0])
_tm /= np.linalg.norm(_tm)
Q_M = tuple(np.array(P_M) - _tm * 120.0)
LRT_PTS = C.fillet([J062, (-650.0, 2275.0), Q_M, P_M], 300) + [p for p in list(substring(TL, S_M + 1.0, S_END).coords)]
q = [LRT_PTS[0]]
for p in LRT_PTS[1:]:
    if math.dist(p, q[-1]) > 0.5:
        q.append(p)
LRT_PTS = q
L_LRT = LineString(LRT_PTS)
S_MERGE = L_LRT.project(Point(P_M))
RAMP_END = S_MERGE + 220.0                       # elevated from J062 over A-3 and the trunk's north carriageway, ramp down in the median


def chain(pt):
    return L_LRT.project(Point(pt))


def at_chain(s):
    p = L_LRT.interpolate(s)
    return (p.x, p.y)


# no street joins the trunk where the LRT climbs over its north carriageway and ramps down in the median
NO_JOIN = substring(TL, max(S_M - 90.0, 0.0), S_M + 240.0).buffer(45.0, cap_style=2)
# nor where the trunk climbs over the А-3 south-bound carriageway right after the joint J148 (overpass and its approaches)
NO_JOIN = NO_JOIN.union(substring(TL, 0.0, 220.0).buffer(45.0, cap_style=2))
LOG.append({"what": "ЛРТ: эстакада от J062 над А-3 и северной проезжей частью магистрали, спуск в разделительную полосу",
            "merge": P1(P_M), "elevated_m": round(RAMP_END)})

# ===================================================================================================== 2. local streets
t = time.time()
made = N.generate_local()
LOG.append({"what": "местные улицы сгенерированы", "n": made, "s": round(time.time() - t, 1)})
JOINT_PTS = [Point(n["x"], n["z"]) for n in N.NODES.values() if n["type"] == "joint"]


NODE_PTS = [Point(n["x"], n["z"]) for n in N.NODES.values()]


RING_PTS = [Point(c) for _, c in N.RINGS]


def ext_ok(P):
    """An end that may stay: on the district border, at a declared node (existing interchange terminals), at a joint (the
    carriageway joints of a divided street lie off its axis) or inside a ring."""
    return POLY.exterior.distance(P) < 3.0 or any(P.distance(j) < 1.0 for j in NODE_PTS) \
        or any(P.distance(j) < 10.0 for j in JOINT_PTS) or any(P.distance(r) < N.RING_R for r in RING_PTS)


def extend_free_ends(layers=("frame",), reach=400.0):
    out = []
    lines = N.all_lines()
    tree_all = shapely.STRtree([L for _, L, _, _ in lines])
    for s in N.STREETS:
        if s["_layer"] not in layers:
            continue
        oth = [(sid, L, cls) for sid, L, cls, _ in lines]
        for end in (0, -1):
            pt = s["line"][end]
            if N._attached(pt, oth, tree_all, ext_ok, skip=s["id"]):
                continue
            if any(s["id"] in n.get("streets", []) and math.dist(pt, (n["x"], n["z"])) < 1.0 for n in N.NODES.values()):
                continue
            prev = s["line"][1] if end == 0 else s["line"][-2]
            d = np.array(pt, float) - np.array(prev, float)
            d /= np.linalg.norm(d)
            hosts = [L for sid, L, cls in oth if cls not in N.NO_HOST and sid != s["id"]]
            hp = N._ray_hit(tuple(pt), d, hosts, reach)
            if hp is None:
                out.append({"what": "конец улицы каркаса без продолжения", "id": s["id"], "at": P1(pt)})
                continue
            seg = LineString([tuple(pt), hp])
            if N.houses_hit(seg.buffer(N.red_w(s["class"]) / 2.0)):
                out.append({"what": "продолжение улицы каркаса задевает дома: не строится", "id": s["id"], "at": P1(pt)})
                continue
            if end == 0:
                s["line"].insert(0, P1(hp))
            else:
                s["line"].append(P1(hp))
            s["struct"] += [{"from": P1(a_), "to": P1(b_), "kind": k} for a_, b_, k in N.structs([tuple(pt), hp])]
            out.append({"what": "улица каркаса продолжена до ближайшей улицы", "id": s["id"], "to": P1(hp), "m": round(seg.length, 1)})
    return out


LOG += extend_free_ends()


def cut_no_join(log=None):
    """Generated streets that end on the trunk inside NO_JOIN (the LRT ramp): the end is cut back to the street's last
    junction before it (trim_free_ends then treats it as any free end)."""
    n = 0
    for s in N.STREETS:
        if s["_layer"] not in N.GEN:
            continue
        for e in (0, -1):
            P = Point(s["line"][e])
            if NO_JOIN.contains(P) and TL.distance(P) < 1.0:
                L = LineString(s["line"])
                q = substring(L, 0.0, L.length - 30.0) if e == -1 else substring(L, 30.0, L.length)
                if q.length < 5:
                    continue
                s["line"] = [P1(p) for p in q.coords]
                n += 1
                if log is not None:
                    log.append({"what": "улица не примыкает к магистрали у рампы ЛРТ: укорочена", "id": s["id"]})
    return n


cut_no_join(LOG)
TRIM_LOG = []
N.trim_free_ends(ext_ok, layers=N.GEN + ("frame",), log=TRIM_LOG)
LOG += TRIM_LOG
N.snap_ends(tol=N.SNAP_J, log=LOG)
N.align_opposite_ts(log=LOG)
N.close_gaps(log=LOG)
N.house_lanes(log=LOG)
N.link_dead_ends(log=LOG)


def village_entry(q_, acc, at, barrier, reach, inside=4.0, step=8.0):
    """(rank, host id, lane) — the shortest village lane from a street to land of a village zone that no street reaches:
    tried from points every `step` m along the zone's edge, square from the nearest street, never across a road it does not
    join, water, the railway, a corridor or a house (a lane of village_lane red width), ending `inside` m into the zone."""
    hw = N.red_w("village_lane") / 2.0
    ring = q_.exterior
    best = None
    for t in np.arange(0.0, ring.length, step):
        b = ring.interpolate(t)
        for i in at.query(b.buffer(reach)):
            sid, L, c = acc[i]
            a = L.interpolate(L.project(b))
            d = a.distance(b)
            if d < 1.0 or d > reach - inside:
                continue
            rank = (1 if sid.startswith("osm:") else 0, d)
            if best is not None and rank >= best[0]:
                continue
            u = np.array([b.x - a.x, b.y - a.y]) / d
            end = Point(b.x + u[0] * inside, b.y + u[1] * inside)
            sp = LineString([(a.x, a.y), (end.x, end.y)])
            if sp.crosses(barrier) or sp.intersects(N.WATER_POLY) or not POLY.contains(sp) or sp.intersects(N.RAIL) \
                    or sp.intersects(LineString(N.SPUR)) or N.houses_hit(sp.buffer(hw)) or not q_.contains(end) \
                    or NO_JOIN.contains(Point(a.x, a.y)) or sp.intersection(N.POWER_ZONE).length > 60.0:
                continue
            # the lane meets no other street on its way (it would cross it at a node nobody drew)
            if any(acc[j][0] != sid and acc[j][1].intersects(sp) for j in at.query(sp)):
                continue
            best = (rank, sid, sp)
    return best


def serve_pieces(log=None, min_m2=2000.0, reach=150.0, inside=15.0):
    """Built zone land cut off from every street (rule 12: a block with buildings needs an entry): a local side street from
    the nearest street into the piece (≤ reach, ending `inside` m in), never across an expressway, a ramp, water, a
    corridor or a house."""
    lines = [(x["id"], LineString(x["line"]), x["class"]) for x in N.STREETS]
    lines += [("osm:" + oid, q_, cls) for oid, q_, cls in N.OSM_HOST]
    reds = unary_union([L.buffer(N.red_w(c) / 2.0) for _, L, c in lines if c not in ("expressway", "ramp")]
                       + [L.buffer(N.EXP_HALF) for _, L, c in lines if c in ("expressway", "ramp")])
    # streets a block may be entered from, as rule 12 takes them (land_util DRIVABLE without NO_ACCESS: no boulevard, no
    # pedestrian street)
    acc = [(sid, L, c) for sid, L, c in lines if c in LU.DRIVABLE and c not in LU.NO_ACCESS]
    at = shapely.STRtree([L for _, L, _ in acc])
    barrier = unary_union([L for _, L, c in lines if c in ("expressway", "ramp")])
    made_ = []
    for z in Z.ZPLAN:
        vil = z["use"] == "village_existing"
        if z["use"] not in Z.DEV_USES and not vil:
            continue
        land = z["poly"].intersection(POLY).difference(reds).difference(N.BARRIER).difference(N.WATER_STRIP).buffer(0)
        if vil:
            land = z["poly"].intersection(POLY).difference(reds).buffer(0)
        inside_z = 6.0 if vil else inside
        for q_ in getattr(land, "geoms", [land]):
            if q_.geom_type != "Polygon" or q_.area < min_m2:
                continue
            # served: at least 12 m of the piece's edge lies on the red line of a street it may be entered from (a corner
            # touch is not an entry, rule 12 asks a lot of the block with its access street within 2 m)
            front = sum(acc[i][1].buffer(N.red_w(acc[i][2]) / 2.0 + 2.0).intersection(q_.exterior).length
                        for i in at.query(q_.buffer(N.EXP_HALF)))
            if front >= 12.0:
                continue
            best = None
            if vil:
                best = village_entry(q_, acc, at, barrier, reach)
            for i in ([] if vil else at.query(q_.buffer(reach))):
                sid, L, c = acc[i]
                a, b = shapely.ops.nearest_points(L, q_)
                d = a.distance(b)
                # an existing road comes last: its dead ends are as OSM has them, and a new street on one makes it longer
                rank = (1 if sid.startswith("osm:") else 0, d)
                if d > reach - inside_z or (best is not None and rank >= best[0]):
                    continue
                u = np.array([b.x - a.x, b.y - a.y]) / max(d, 1e-6)
                end = Point(b.x + u[0] * inside_z, b.y + u[1] * inside_z)
                sp = LineString([(a.x, a.y), (end.x, end.y)])
                if sp.crosses(barrier) or sp.intersects(N.WATER_POLY) or not POLY.contains(sp) or sp.intersects(N.RAIL) \
                        or sp.intersects(LineString(N.SPUR)) \
                        or N.houses_hit(sp.buffer(N.red_w("local") / 2.0)) or not q_.contains(end) or NO_JOIN.contains(Point(a.x, a.y)):
                    continue
                best = (rank, sid, sp)
            rec = {"zone": z["id"], "ha": round(q_.area / 1e4, 2), "at": [round(v) for v in q_.representative_point().coords[0]]}
            if best is None and vil:
                if log is not None:
                    log.append({"what": "земля села без улицы: проезда без сноса дома нет — как в OSM", **rec})
                continue
            if best is None:
                # no street reaches it without crossing a road, the railway, water, a corridor or a house: a reserve
                N.UNSERVED.append(q_.buffer(-(N.D_IN + 2.0)).buffer(0) if q_.buffer(-(N.D_IN + 2.0)).area > 100.0 else q_)
                if log is not None:
                    log.append({"what": "земля зоны без улицы: подъезда нет — резерв", **rec})
                continue
            sid_new = f"v_serve_{len(made_) + 1:02d}"
            if vil:
                _host = next((x for x in N.STREETS if x["id"] == best[1]), None)
                _yb = max(2026, int(_host["years"][0]) if _host else 2026)
                N.street(sid_new, "village_lane", best[2].coords, "проулок к усадьбе", _yb, layer="lane",
                         years=list(_host["years"]) if _host and int(_host["years"][0]) > 2026 else None,
                         why=MODEL + f": земля села {z['id']} ({q_.area / 1e4:.1f} га) не выходит ни на одну улицу — проулок "
                                     f"{best[2].length:.0f} м от {best[1]} (решение 31.10: сёла получают свои улицы; правило 12)")
            else:
                N.street(sid_new, "local", best[2].coords, "въезд в квартал", int(z["years"][0]), layer="lane",
                         why=MODEL + f": земля зоны {z['id']} ({q_.area / 1e4:.1f} га) отрезана от улиц — въезд {best[2].length:.0f} м "
                                     f"от {best[1]} (правило 12: у квартала со зданиями есть въезд)")
            made_.append(sid_new)
            if log is not None:
                log.append({"what": "въезд в отрезанную землю зоны", "id": sid_new, "from": best[1], "m": round(best[2].length), **rec})
    return made_


serve_pieces(log=LOG)
N.close_gaps(log=LOG)
YEAR_MOVES = N.phase_years(log=LOG)
for s in N.STREETS:
    if s["class"].startswith("driveway"):
        s["class"] = "local"
        s["why"] = (s.get("why") or "") + "; в growing_w.json — местная улица (проезды даёт только land_driveways)"
LOG.append({"what": "сеть готова", "streets": len(N.STREETS), "s": round(time.time() - T0, 1)})

# ===================================================================================================== 3. LRT v1
ROADS_X = []
for s in N.STREETS:
    if s["class"] in ("expressway", "ramp"):
        continue
    if not s["id"].startswith("s_trunk"):
        x = LineString(s["line"]).intersection(L_LRT)
        for g in getattr(x, "geoms", [x]):
            if g.geom_type == "Point":
                ROADS_X.append((chain((g.x, g.y)), s["id"]))
        # a street ending on the trunk (T-junction): its end on the trunk axis is a crossing of the median
        for e in (0, -1):
            P = Point(s["line"][e])
            if L_LRT.distance(P) < 1.0:
                ROADS_X.append((chain((P.x, P.y)), s["id"]))
for oid, q_, cls in N.OSM_HOST:
    x = q_.intersection(L_LRT)
    for g in getattr(x, "geoms", [x]):
        if g.geom_type == "Point":
            ROADS_X.append((chain((g.x, g.y)), "osm:" + oid))
ROADS_X = sorted({(round(c, 1), sid) for c, sid in ROADS_X})
PLAT = float(LU.Norms().v("lrt.platform_length_m")["min"])
HALF_P = PLAT / 2.0 + 12.0                        # half platform + clear distance to the cross street
SP_MIN, SP_MAX, SP_GOAL = 820.0, 1480.0, 1250.0
_cx = [c for c, _ in ROADS_X]


def free_at(s):
    return all(abs(s - c) >= HALF_P for c in _cx) and RAMP_END + 40.0 <= s <= L_LRT.length - HALF_P


def best_near(goal, lo, hi):
    cand = [goal + d * k for k in range(0, 400) for d in (1.0, -1.0)]
    for s in cand:
        if lo <= s <= hi and free_at(s):
            return s
    return None


V0_NAMES = [(s_["x"], s_["name_ru"]) for s_ in V0["lrt"]["stations"]]
ST_S = []
s_prev = None
first = best_near(RAMP_END + 120.0, RAMP_END + 40.0, RAMP_END + 900.0)
ST_S.append(first)
# the terminus: its platform ends at the buffer stop (rule 25: the terminal station is within a platform of the line end)
T_GOAL = L_LRT.length - PLAT / 2.0 - 2.0
while True:
    s_prev = ST_S[-1]
    if T_GOAL - s_prev <= SP_MAX:
        break
    s_new = best_near(s_prev + SP_GOAL, s_prev + SP_MIN, s_prev + SP_MAX)
    if s_new is None:
        LOG.append({"what": "ЛРТ: нет места для станции между улицами в шаге 0,8–1,5 км", "after": round(s_prev)})
        s_new = s_prev + SP_GOAL
    ST_S.append(s_new)
term = next((T_GOAL - d for d in np.arange(0.0, PLAT / 2.0, 0.5)
             if all(abs(T_GOAL - d - c) >= HALF_P for c in _cx)), None)
if term is None:
    term = T_GOAL
    LOG.append({"what": "ЛРТ: конечная — без промежутка между улицами", "s": round(term)})
ST_S.append(term)
STATIONS = []
used = set()
for k, s_ in enumerate(ST_S):
    p = at_chain(s_)
    nm = None
    for x0, n0 in sorted(V0_NAMES, key=lambda t: abs(t[0] - p[0])):
        if abs(x0 - p[0]) < 700 and n0 not in used:
            nm = n0
            break
    if k == len(ST_S) - 1:
        nm = "Аэропорт «Алатау»"
    if nm is None or nm in used:
        nm = f"Аэропортовая-{k + 1}"
    used.add(nm)
    before = [c for c in ROADS_X if c[0] < s_]
    after = [c for c in ROADS_X if c[0] > s_]
    STATIONS.append({"id": f"st_gw_{k + 1:02d}", "name_ru": nm, "x": round(p[0], 1), "z": round(p[1], 1),
                     "between": [before[-1][1] if before else None, after[0][1] if after else None],
                     "kind": "elevated" if s_ < RAMP_END else "ground", "_s": s_})
SECTIONS = [{"from": P1(LRT_PTS[0]), "to": P1(at_chain(RAMP_END)), "kind": "elevated"},
            {"from": P1(at_chain(RAMP_END)), "to": P1(LRT_PTS[-1]), "kind": "ground"}]
LRT = {
    "lines": [{
        "id": "lrt_growing_w_airport", "name_ru": "ЛРТ «Аэропорт» (участок Growing-запад)",
        "line": [P1(p) for p in LRT_PTS],
        "sections": SECTIONS,
        "stations": [{k: v for k, v in s_.items() if not k.startswith("_")} for s_ in STATIONS],
        "ends": [{"kind": "joint", "id": "J062", "to": "growing_e"}, {"kind": "terminus", "id": STATIONS[-1]["id"]}],
        "joints": [{"joint_id": "J062", "x": J062[0], "z": J062[1], "to": "growing_e"}],
        "years": Y4(2036),
        "why": "схема lrt_airport: от стыка J062 у А-3 эстакадой над А-3 и северной проезжей частью магистрали, дальше в "
               "разделительной полосе Аэропортовой магистрали через центр «Каскелен» к терминалу аэропорта; станции между "
               "поперечными улицами, шаг 0,8–1,5 км. Год 2036 (2-я очередь схемы: ветка от А-3 до центра); до аэропорта линия "
               "открывается с участками магистрали"}],
    "depots": []}
SCHEME_CHANGES_LRT = ("lrt_airport", "ЛРТ в разделительной полосе магистрали (9 м) вместо отдельной полосы в 90–220 м севернее: "
                                     "общие перекрёстки, нет второй линии разрезов кварталов; станции переставлены по промежуткам "
                                     f"между улицами, их {len(STATIONS)} (шаг 0,8–1,5 км, у схемы 11 станций и шаги до 2 км)")
LOG.append({"what": "ЛРТ: станции", "n": len(STATIONS), "km": round(L_LRT.length / 1000, 2),
            "spacing_m": [round(b["_s"] - a["_s"]) for a, b in zip(STATIONS[:-1], STATIONS[1:])]})

# ===================================================================================================== 4. zones
ZONES = []
ZIDS = set()
taken = Polygon()


def simple_parts(g, min_area=300.0):
    out = []
    stack = [g]
    while stack:
        q_ = stack.pop().buffer(0)
        if q_.is_empty:
            continue
        if q_.geom_type in ("MultiPolygon", "GeometryCollection"):
            stack += [p for p in q_.geoms if p.geom_type == "Polygon"]
            continue
        if q_.area < min_area:
            continue
        if not q_.interiors:
            out.append(q_)
            continue
        hx = Polygon(q_.interiors[0]).representative_point().x
        x0, z0, x1, z1 = q_.bounds
        stack += [q_.intersection(box(x0 - 1, z0 - 1, hx, z1 + 1)), q_.intersection(box(hx, z0 - 1, x1 + 1, z1 + 1))]
    return sorted(out, key=lambda p: -p.area)


def zone_out(z, poly, rules):
    global taken
    parts = simple_parts(poly.buffer(0).intersection(POLY).difference(taken).buffer(0), 500.0)
    for k, q_ in enumerate(parts):
        taken = taken.union(q_)
        zid = z["id"] if k == 0 else f"{z['id']}_p{k + 1}"
        while zid in ZIDS:
            zid = zid + "_s"
        ZIDS.add(zid)
        d = {"id": zid, "use": z["use"], "name_ru": z["name_ru"], "polygon": poly_pts(q_),
             "years": z["years"], "rules": copy.deepcopy(rules), "why": z["why"], "area_ha": round(q_.area / 1e4, 2),
             "_src": z.get("src", "v0"), "_base": z["id"]}
        if z.get("density"):
            d["density"] = z["density"]
        ZONES.append(d)


ZB = {z["id"]: z for z in Z.ZPLAN}
# --- the airport: the scheme's airside zone becomes the airport lot (runway 4 000 m at 095°, owner 31.10); the rest of
# the old airside land joins the airport's protection reserve
AIR = N.AIRPORT_LOT
old_air = ZB["air_airside"]["poly"]
ZB["air_airside"]["poly"] = AIR
ZB["air_airside"]["rules"] = {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0}
ZB["air_airside"]["why"] = ("решение владельца 31.10: ВПП 4 000 × 45 м, курс 095°, центр (−16000, 1500), после 2040; территория "
                            "аэропорта — 4,6 км вдоль ВПП, 450 м к югу и 1 000 м к северу от оси (лётная полоса, рулёжки, "
                            "перрон, терминал), участок модели airport")
for zid in ("air_terminal", "air_reserve_1", "air_reserve_2", "air_reserve_3", "air_reserve_4", "res_rest_3", "res_rest_2",
            "ind_plateau_3", "log_cargo_2"):
    if zid in ZB:
        ZB[zid]["poly"] = ZB[zid]["poly"].difference(AIR).buffer(0)
_rest = old_air.difference(AIR).buffer(0)
if _rest.area > 1000:
    Z.ZPLAN.append({"id": "air_reserve_5", "use": "reserve", "name_ru": "Охранная зона аэропорта", "poly": _rest,
                    "years": [2041, 2060], "rules": {"lot_split": "none"}, "density": None, "src": "v0",
                    "why": "часть лётного поля схемы вне территории аэропорта (ВПП 4 000 м по решению 31.10): охранная зона"})
Z.CHANGES.append(("air_airside", "лётное поле = территория аэропорта под ВПП 4 000 м 095° (4,6 × 1,45 км, "
                                 f"{AIR.area / 1e4:.0f} га), остаток схемы — охранная зона air_reserve_5"))

# --- corridors kept free of rule buildings: the railway, the airport spur (model), the sorting yard
RAIL_STRIP = N.RAIL.buffer(20.0).intersection(POLY)
SPUR_L = LineString(N.SPUR)
SPUR_STRIP = SPUR_L.buffer(20.0).intersection(POLY)
_r = N.RAIL
_s_a = _r.project(Point(-4300.0, -300.0))
_s_b = _r.project(Point(-1700.0, -300.0))
_yard_axis = substring(_r, min(_s_a, _s_b), max(_s_a, _s_b))
YARD = _yard_axis.buffer(-250.0, single_sided=True, cap_style=2) if False else None
_off = _yard_axis.offset_curve(140.0)
YARD = _yard_axis.buffer(25.0, cap_style=2).union(LineString(_off.coords).buffer(115.0, cap_style=2)).convex_hull
YARD = YARD.difference(N.POWER_ZONE.buffer(2.0)).intersection(POLY).buffer(0)
YARD = max(getattr(YARD, "geoms", [YARD]), key=lambda g: g.area).simplify(1.0)
_red_all = unary_union([LineString(s["line"]).buffer(N.red_w(s["class"], s.get("profile")) / 2.0 + 0.5, cap_style=2)
                        for s in N.STREETS if s["class"] not in ("expressway", "ramp")])
YARD = YARD.difference(_red_all).buffer(0)
YARD = max(getattr(YARD, "geoms", [YARD]), key=lambda g: g.area).simplify(1.0)
Z.ZPLAN.insert(0, {"id": "util_rail_yard", "use": "utility", "name_ru": "Сортировочная станция (парк путей)", "poly": YARD,
                   "years": [2040, 2045], "rules": {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0}, "density": None,
                   "src": "l2", "why": MODEL + ": сортировочная станция генплана «между аэропортом и Конаевым» — парк путей "
                                               "вдоль обходной ж/д с северной стороны, между ПС «Алма» и А-3"})
Z.ZPLAN.insert(0, {"id": "util_rail_spur", "use": "utility", "name_ru": "Ж/д ветка к аэропорту (полоса отвода)",
                   "poly": SPUR_STRIP, "years": [2039, 2041], "rules": {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0},
                   "density": None, "src": "l2",
                   "why": MODEL + ": полоса 40 м ветки от обходной ж/д у ПС «Алма» к вокзалу «Алатау» (реестр airport_rail_station)"})
Z.ZPLAN.insert(0, {"id": "util_rail_bypass", "use": "utility", "name_ru": "Обходная ж/д Жетыген – Казыбек би (полоса отвода)",
                   "poly": RAIL_STRIP, "years": [2025, 2025], "rules": {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0},
                   "density": None, "src": "l2",
                   "why": "существующая ж/д (OSM 81f6836e): полоса 40 м без застройки — путей не моделирует ни один инструмент"})
# the LRT viaduct from J062 to the ramp in the trunk's median: a strip without buildings under it (rule 25: a viaduct over
# buildings), the rest of the line runs in the median between the carriageways
LRT_VIA = substring(L_LRT, 0.0, RAMP_END).buffer(LRT_W / 2.0 + 4.0, cap_style=2).intersection(POLY).buffer(0)
Z.ZPLAN.insert(0, {"id": "g_lrt_viaduct", "use": "park", "name_ru": "Зелёная полоса под эстакадой ЛРТ", "poly": LRT_VIA,
                   "years": [LRT["lines"][0]["years"][0], LRT["lines"][0]["years"][0] + 5], "rules": {"lot_split": "none", "homes_per_ha": 0,
                                                                                "jobs_per_ha": 0},
                   "density": None, "src": "l2",
                   "why": MODEL + f": полоса {LRT_W + 8.0:.1f} м под эстакадой ЛРТ от стыка J062 до спуска в разделительную "
                                  "полосу магистрали — опоры и пролёт над землёй без зданий (правило 25)"})
Z.CHANGES.append(("g_lrt_viaduct", f"зелёная полоса без застройки под эстакадой ЛРТ ({LRT_VIA.area / 1e4:.1f} га) из зон под ней"))
Z.CHANGES.append(("util_rail_*", "полосы отвода обходной ж/д и ветки к аэропорту и парк сортировочной станции — отдельные "
                                 "зоны utility (застройка по правилам на путях невозможна; ж/д не моделируется инструментами)"))

# --- sanitary gaps (rule 15)
_LN = LU.Norms()
SZZ_W = {k: float(v["min"]) for k, v in _LN.v("szz.class_width_m").items()}
_WS = _LN.v("szz.wind_sector_deg")
SZZ_F, SZZ_SECTOR = float(_WS["zone_factor"]), tuple(_WS["default_sector"])
SZZ_DEFAULT = {"logistics": ("V", MODEL + ": склады, сухой порт и логистика готовых товаров без выбросов — наименьший класс "
                                          "szz.class_width_m"),
               "industry": ("IV", MODEL + ": предприятия генплана без классов I–II (схема: режим СЭЗ); лёгкая и пищевая "
                                         "промышленность, сборка — класс IV szz.class_examples")}
for z in Z.ZPLAN:
    if z["use"] in ("industry", "logistics"):
        cls_, why_ = SZZ_DEFAULT[z["use"]]
        z["rules"]["szz_class"] = cls_
        z["why"] = (z.get("why") or "") + f"; СЗЗ класса {cls_} ({SZZ_W[cls_]:.0f} м): {why_}"


def _wedge(poly, a0, a1, r, step=40.0):
    b = poly.exterior if poly.geom_type == "Polygon" else max(poly.geoms, key=lambda g: g.area).exterior
    pts_ = [b.interpolate(t_) for t_ in np.arange(0.0, b.length, step)] + [poly.centroid]
    angs = np.radians(np.linspace(a0, a1 if a1 >= a0 else a1 + 360.0, 13))
    out = []
    for p in pts_:
        out.append(Polygon([(p.x, p.y)] + [(p.x + r * math.sin(t_), p.y + r * math.cos(t_)) for t_ in angs]))
    return unary_union(out)


RES_USES = ("residential_high", "residential_mid", "residential_low", "mixed_centre", "waterfront", "campus")
SZZ_LOG = []
for I in [z for z in Z.ZPLAN if z["use"] in ("industry", "logistics")]:
    w = SZZ_W[I["rules"]["szz_class"]]
    reach = w * SZZ_F
    for R in [z for z in Z.ZPLAN if z["use"] in RES_USES]:
        if I["poly"].distance(R["poly"]) >= reach:
            continue
        strip = R["poly"].intersection(I["poly"].buffer(w).union(_wedge(I["poly"], *SZZ_SECTOR, reach)))
        if strip.area < 500.0:
            continue
        cls_ = I["rules"]["szz_class"]
        zone_out({"id": f"g_szz_{I['id']}_{R['id']}", "use": "park", "src": "l2", "years": R["years"],
                  "name_ru": f"Санитарный разрыв {I['name_ru']} — {R['name_ru']} (озеленение)",
                  "why": f"СЗЗ класса {cls_}: {w:.0f} м, в подветренном секторе {SZZ_SECTOR[0]:.0f}–{SZZ_SECTOR[1]:.0f}° — "
                         f"{reach:.0f} м (правило 15): жильё не ближе к производству"},
                 strip, {"lot_split": "none"})
        SZZ_LOG.append((I["id"], R["id"], cls_, round(strip.area / 1e4, 2)))
        Z.CHANGES.append((f"g_szz_{I['id']}_{R['id']}", f"санитарный разрыв класса {cls_} ({w:.0f} м, по ветру {reach:.0f} м; "
                          f"{strip.area / 1e4:.2f} га) из зоны {R['id']}: озеленение"))
# villages (existing houses) keep their homes; the sanitary gap is taken from the industry side: no industry or logistics
# land within the class width of a village, nor within twice the width where the village lies downwind
# (szz.wind_sector_deg default_sector: the village to the south-west – west of the works, i.e. the works north-east – east)
_VIL = [z for z in Z.ZPLAN if z["use"] == "village_existing"]
_UP = ((SZZ_SECTOR[0] + 180.0) % 360.0, (SZZ_SECTOR[1] + 180.0) % 360.0)
for I in [z for z in Z.ZPLAN if z["use"] in ("industry", "logistics")]:
    w = SZZ_W[I["rules"]["szz_class"]]
    reach = w * SZZ_F
    near = [V for V in _VIL if V["poly"].distance(I["poly"]) < reach]
    if not near:
        continue
    reach_poly = unary_union([V["poly"].buffer(w).union(_wedge(V["poly"], *_UP, reach)) for V in near])
    strip = I["poly"].intersection(reach_poly).buffer(0)
    if strip.area < 500.0:
        continue
    cls_ = I["rules"]["szz_class"]
    vids = ", ".join(V["id"] for V in near)
    zone_out({"id": f"g_szz_{I['id']}_vil", "use": "park", "src": "l2", "years": I["years"],
              "name_ru": f"Санитарный разрыв {I['name_ru']} — сёла (озеленение)",
              "why": f"СЗЗ класса {cls_}: {w:.0f} м от сёл {vids}, с наветренной для них стороны {reach:.0f} м (правило 15); "
                     "дома сёл остаются, разрыв — за счёт производственной зоны"},
             strip, {"lot_split": "none"})
    SZZ_LOG.append((I["id"], "сёла", cls_, round(strip.area / 1e4, 2)))
    Z.CHANGES.append((f"g_szz_{I['id']}_vil", f"санитарный разрыв класса {cls_} ({w:.0f} м, по ветру {reach:.0f} м; "
                      f"{strip.area / 1e4:.2f} га) из зоны {I['id']} у сёл {vids}: озеленение"))
# housing keeps szz.rail_m housing_from_outer_track_axis (100 m) from every OSM track (rule 15, rail)
RAIL_SZZ = float(_LN.v("szz.rail_m")["housing_from_outer_track_axis"])
_TRK = unary_union(N.RAIL_ALL).intersection(POLY.buffer(RAIL_SZZ + 50.0))
for R in [z for z in Z.ZPLAN if z["use"] in RES_USES]:
    if _TRK.is_empty or R["poly"].distance(_TRK) >= RAIL_SZZ + 5.0:
        continue
    strip = R["poly"].intersection(_TRK.buffer(RAIL_SZZ + 5.0)).buffer(0)
    if strip.area < 100.0:
        continue
    zone_out({"id": f"g_szz_rail_{R['id']}", "use": "park", "src": "l2", "years": R["years"],
              "name_ru": f"Санитарный разрыв ж/д — {R['name_ru']} (озеленение)",
              "why": f"жильё не ближе {RAIL_SZZ:.0f} м к оси крайнего пути (szz.rail_m, правило 15): полоса {strip.area / 1e4:.2f} га "
                     f"из зоны {R['id']}"},
             strip, {"lot_split": "none"})
    SZZ_LOG.append(("ж/д", R["id"], "rail", round(strip.area / 1e4, 2)))
    Z.CHANGES.append((f"g_szz_rail_{R['id']}", f"санитарный разрыв ж/д {RAIL_SZZ:.0f} м ({strip.area / 1e4:.2f} га) из зоны "
                      f"{R['id']}: озеленение"))
LOG.append({"what": "санитарные разрывы (озеленение) между производством и жильём", "pairs": SZZ_LOG})
for k, P in enumerate(N.UNSERVED):
    q_ = P.buffer(N.D_IN + 2.0)
    zone_out({"id": f"x_unserved_{k + 1}", "use": "reserve", "src": "l2", "years": [2050, 2060],
              "name_ru": "Резерв: участок без подъезда",
              "why": "ни одна улица не доходит до участка без пересечения трассы, коридора ЛЭП или домов: резерв до подъезда"},
             q_, {"lot_split": "none"})
    Z.CHANGES.append((f"x_unserved_{k + 1}", f"{q_.area / 1e4:.1f} га у ({P.centroid.x:.0f}, {P.centroid.y:.0f}) — резерв: "
                      "до участка не дойти улицей без пересечения трассы, коридора или домов"))
for z in Z.ZPLAN:
    zone_out(z, z["poly"], z["rules"])
# every leftover sliver joins the zone it shares the longest border with
_gap = POLY.difference(unary_union([Polygon(z["polygon"]).buffer(0) for z in ZONES]))
_ZT = shapely.STRtree([Polygon(z["polygon"]).buffer(0) for z in ZONES])
for g in [q_ for q_ in getattr(_gap, "geoms", [_gap]) if q_.geom_type == "Polygon" and q_.area > 1.0]:
    best, bl = None, 0.0
    for i in _ZT.query(g.buffer(0.5)):
        sh = Polygon(ZONES[int(i)]["polygon"]).buffer(0).boundary.intersection(g.buffer(0.5)).length
        if sh > bl:
            best, bl = int(i), sh
    if best is None:
        continue
    m = Polygon(ZONES[best]["polygon"]).buffer(0).union(g.buffer(0.05)).buffer(0)
    if m.geom_type == "Polygon" and not m.interiors:
        ZONES[best]["polygon"] = poly_pts(m)
        ZONES[best]["area_ha"] = round(m.area / 1e4, 2)



def clean_cover(zones, grid=0.1, tol=0.3):
    """Zones as one coverage on the 0.1 m grid: rounding each ring alone leaves hair-line overlaps along long shared borders
    (a vertex of one zone on the edge of the next moves off it), which land turns into overlapping lots (rule 1). Every ring
    takes its neighbours' vertices within tol (so shared borders carry the same vertices), then the zones are cut in order."""
    def big(g):
        g = g.buffer(0)
        if g.geom_type != "Polygon":
            ps = [q for q in getattr(g, "geoms", []) if q.geom_type == "Polygon"]
            g = max(ps, key=lambda q: q.area) if ps else Polygon()
        return g
    extra = []

    def parts(g, z):
        """The largest polygon of g; the other pieces over 300 m² become parts of the same zone (id _q<k>)."""
        g = g.buffer(0)
        ps = sorted([q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon"], key=lambda q: -q.area)
        for q in ps[1:]:
            if q.area >= 300.0:
                extra.append((z, q))
        return ps[0] if ps else Polygon()
    P = [parts(shapely.set_precision(Polygon(z["polygon"]).buffer(0), grid), z) for z in zones]
    tree = shapely.STRtree(P)
    S_ = []
    for i, p in enumerate(P):
        nb = [int(j) for j in tree.query(p.buffer(tol)) if int(j) != i and not P[int(j)].is_empty]
        if nb and not p.is_empty:
            ref = shapely.MultiPoint([c for j in nb for c in P[j].exterior.coords])
            p = big(shapely.snap(p, ref, tol))
        S_.append(p)
    tree = shapely.STRtree(S_)
    out, lost = [], 0.0
    for i, p in enumerate(S_):
        prev = [out[int(j)] for j in tree.query(p) if int(j) < i and not out[int(j)].is_empty]
        q = p.difference(unary_union(prev)) if prev else p
        q2 = parts(shapely.set_precision(q, grid), zones[i])
        lost += q.area - q2.area
        out.append(q2)
    # pieces split off: cut by everything placed so far, on the grid, as zone parts of their own
    placed = unary_union(out)
    for z, q in extra:
        q = shapely.set_precision(q.difference(placed), grid).buffer(0)
        for k, r in enumerate([r for r in getattr(q, "geoms", [q]) if r.geom_type == "Polygon" and r.area >= 300.0]):
            d = copy.deepcopy(z)
            d["id"] = f"{z['id']}_q{k + 1}"
            while d["id"] in {x["id"] for x in zones}:
                d["id"] += "_s"
            d["polygon"] = [[round(x, 1), round(y, 1)] for x, y in list(r.exterior.coords)[:-1]]
            d["area_ha"] = round(r.area / 1e4, 2)
            zones.append(d)
            placed = placed.union(r)
            lost -= r.area
    # where two borders still cross (not shared), the later zone gives way by 0.1 m. set_precision keeps its grid on the
    # geometry and later overlays run on that grid, so a 4 cm sliver reads as 0 m² there: the test runs in floating point,
    # as the land tools read the spec
    def fl(g):
        return shapely.set_precision(g, 0.0)
    out = [fl(p) for p in out]
    tree = shapely.STRtree(out)
    for _round in range(2):
        for i, p in enumerate(out):
            if p.is_empty:
                continue
            for j in tree.query(p):
                j = int(j)
                if j == i or out[j].is_empty:
                    continue
                if p.intersection(out[j]).area > 0.2 and (j < i or _round == 1):
                    p = fl(parts(shapely.set_precision(p.difference(out[j].buffer(0.1, join_style="mitre")), grid), zones[i]))
            out[i] = p
    for z, q in zip(zones, out):
        if q.is_empty:
            z["polygon"] = []
            continue
        z["polygon"] = [[round(x, 1), round(y, 1)] for x, y in list(q.exterior.coords)[:-1]]
        z["area_ha"] = round(q.area / 1e4, 2)
    return lost


_lost = clean_cover(ZONES)
ZONES = [z for z in ZONES if len(z["polygon"]) >= 3 and Polygon(z["polygon"]).area >= 1.0]
LOG.append({"what": "зоны на сетке 0,1 м одним покрытием (общие границы — общие вершины)", "lost_m2": round(_lost, 1)})

# ===================================================================================================== 5. targets and densities
RED = unary_union([LineString(s["line"]).buffer(N.red_w(s["class"], s.get("profile")) / 2.0, cap_style=2) for s in N.STREETS
                   if s["class"] not in ("expressway", "ramp")]
                  + [LineString(s["line"]).buffer(25.0, cap_style=2) for s in N.STREETS if s["class"] == "expressway"]
                  + [q_.buffer(N.red_w(cls) / 2.0, cap_style=2) for _, q_, cls in N.OSM_HOST])
NOBUILD = unary_union([RED, N.POWER_ZONE, N.WATER_STRIP, RAIL_STRIP, SPUR_STRIP])
NET_LAND = POLY.difference(NOBUILD)


def net_ha(z):
    return Polygon(z["polygon"]).buffer(0).intersection(NET_LAND).area / 1e4


POP_PLAN, JOBS_PLAN = int(V0["targets"]["population_2050"]), int(V0["targets"]["jobs_2050"])
RES_PER_HOME = 2.5
# calibration of the zone density against what the land tools build on the net land (first full run, w52): homes and jobs
# of gen_buildings ÷ density × net ha of this builder
# runs 1–3 (w52): gen_buildings builds 0.90 of the jobs and 1.00 of the homes that density × net ha of this builder gives
# (run 3 on integ db2b682: jobs 128 167 of 142 300, homes 92 641 of 92 850): the share of the zones that social plots,
# drives and grading strips take
CAL_H, CAL_J = 1.0, 0.90
HOMES_T = int(round(POP_PLAN / RES_PER_HOME, -1))
JOBS_T = int(round(JOBS_PLAN, -2))
SKIP = {"village_existing"}
NETHA = {z["id"]: net_ha(z) for z in ZONES}
JOBS_RES = {"residential_high": 30.0, "residential_mid": 15.0, "residential_low": 4.0}
H_SCALED = {"residential_high", "residential_mid", "mixed_centre"}
J_SCALED = {"business", "mixed_centre", "industry", "logistics"}


def _sum(key, pick):
    return sum(NETHA[z["id"]] * (z["rules"].get(key) or 0) for z in ZONES if pick(z))


FH_M = LU.floor_heights()
TALL_H = 28.0
for z in ZONES:
    if z["use"] in ("industry", "logistics"):
        # two production floors of LU.floor_heights()["industry"] (13.6 m) stay under 28 m (no fire-gap pairs, rule 16 far
        # below 50 m): with one floor (cap 18 m) the zones did not reach their floor area in gen_buildings (first run)
        z["rules"]["floors"] = [1, 2]
        z["rules"]["height_cap_m"] = 28
for z in ZONES:
    r = z["rules"]
    fl = r.get("floors")
    if not fl or z["use"] in SKIP:
        continue
    _fh = FH_M.get("business", 4.43) if z["use"] in ("business", "mixed_centre") else FH_M.get("res_mid", 3.6)
    lo = int(TALL_H // _fh)
    if fl[0] > lo:
        r["floors"] = [lo, fl[1]]
for z in ZONES:
    if z["use"] in JOBS_RES:
        z["rules"]["jobs_per_ha"] = max(float(z["rules"].get("jobs_per_ha") or 0), JOBS_RES[z["use"]])
h_fix = _sum("homes_per_ha", lambda z: z["use"] not in SKIP and z["use"] not in H_SCALED)
h_var = _sum("homes_per_ha", lambda z: z["use"] in H_SCALED)
j_fix = _sum("jobs_per_ha", lambda z: z["use"] not in SKIP and z["use"] not in J_SCALED)
j_var = _sum("jobs_per_ha", lambda z: z["use"] in J_SCALED)
FH = (HOMES_T / CAL_H - h_fix) / h_var
FJ = (JOBS_T / CAL_J - j_fix) / j_var
CAP_M = 49.0                       # rule 16: every building under 50 m (the whole district is within 30 km of two airfields)
for z in ZONES:
    if z["use"] in SKIP:
        continue
    r = z["rules"]
    if z["use"] in H_SCALED and r.get("homes_per_ha"):
        r["homes_per_ha"] = round(r["homes_per_ha"] * FH, 1)
    if z["use"] in J_SCALED and r.get("jobs_per_ha"):
        r["jobs_per_ha"] = round(r["jobs_per_ha"] * FJ, 1)
    m2j = 100.0 if z["use"] in ("logistics", "industry") else 90.0
    need = ((r.get("homes_per_ha") or 0) * 75.0 + (r.get("jobs_per_ha") or 0) * m2j) / 1e4
    if r.get("far") is not None and need * 1.25 > r["far"]:
        r["far"] = round(need * 1.25 + 0.05, 1)
        fl = r.get("floors") or [3, 9]
        top = max(fl[1], int(math.ceil(r["far"] / 0.28)))
        if z["use"] in ("logistics", "industry"):
            top = fl[1]
        top = min(top, int(CAP_M // 3.6))
        r["floors"] = [min(fl[0], top), top]
        r["height_cap_m"] = min(CAP_M, max(r.get("height_cap_m") or 0, round(r["floors"][1] * 3.6 + 4)))
homes = sum(NETHA[z["id"]] * (z["rules"].get("homes_per_ha") or 0) for z in ZONES if z["use"] not in SKIP)
jobs = sum(NETHA[z["id"]] * (z["rules"].get("jobs_per_ha") or 0) for z in ZONES if z["use"] not in SKIP)
TARGETS = {"homes_2050": HOMES_T, "population_2050": POP_PLAN, "jobs_2050": JOBS_PLAN, "home_m2": 75.0,
           "plan_by_density": {"homes": int(round(homes * CAL_H, -1)), "jobs": int(round(jobs * CAL_J, -2))},
           "source": V0["targets"]["source"] + (
               " Квартиры: жители / 2,5 (правило 24: жильё / 30 м² на жителя, 75 м² на квартиру). Существующие дома сёл (OSM) "
               "двойник не считает — они сверх цели и в отчёте отдельно. По зонам — плотности схемы, умноженные на общий "
               "коэффициент (квартиры ×%.3f для res_high, res_mid, mixed_centre; места ×%.3f для business, mixed_centre, "
               "industry, logistics), так чтобы плотность × чистая площадь кварталов (без красных линий, охранных зон ЛЭП, "
               "водоохранных полос и полос ж/д) дала цель" % (FH, FJ))}
LOG.append({"what": "плотности под цели", "FH": round(FH, 3), "FJ": round(FJ, 3), "homes": round(homes), "jobs": round(jobs)})

# ===================================================================================================== 6. objects
OBJ = []
v0obj = {o["registry_id"]: o for o in V0["objects"]}


def rname(rid):
    return v0obj.get(rid, {}).get("name_ru") or (REG[rid]["name_ru"] if rid in REG else rid)


def obj(rid, action, frm, to, accuracy, why, *, name_ru=None, basis="по правилу", **kw):
    o = {"registry_id": rid, "name_ru": name_ru or rname(rid), "action": action, "from": frm, "to": to,
         "yaw": kw.pop("yaw", None), "accuracy": accuracy, "why": why, "basis": basis}
    fp = kw.pop("footprint", None)
    if fp is not None:
        g = fp if isinstance(fp, Polygon) else Polygon(fp)
        o["footprint"] = poly_pts(g)
        o["lot_m2"] = round(g.area)
    for k, v in kw.items():
        if v is not None:
            o[k] = v
    OBJ.append(o)
    return o


def reg_pt(rid):
    g = (REG.get(rid) or {}).get("geom") or {}
    c = g.get("coordinates")
    return [round(c[0], 1), round(c[1], 1)] if g.get("type") == "Point" and c else None


MOVED = []      # (registry id, было, стало, почему) for the report
AC = N.AIR_C
obj("airport_alatau", "move", reg_pt("airport_alatau"), [round(AC[0], 1), round(AC[1], 1)], "district_only",
    "решение владельца 31.10 (city.json airport_new): ВПП 4 000 × 45 м, курс 095°/275°, центр (−16000, 1500), 15 млн пасс./год "
    "(генплан № 727), строительство после 2040. Точка реестра (−16488, 561) по правилу «западная граница» лежит у края района "
    "и южнее ВПП; территория аэропорта — 4,6 × 1,45 км вдоль ВПП (модель airport); магистраль и ЛРТ подходят к терминалу с "
    "севера, южный въезд — продолжение X-IA Golden (J143)", kind="landmark", footprint=AIR, yaw=95.0,
    years=Y4(2041), basis="по источнику", from_twin=[-5900, 8300])
MOVED.append(("airport_alatau", "(−16488, 561) реестр; модель Unity (−5900, 8300)", "(−16000, 1500), ВПП 095°",
              "решение владельца 31.10 (city.json airport_new); модель Unity airport пока стоит на старом месте и с двумя ВПП"))
# rail station «Алатау»: at the end of the spur, next to the terminal and the LRT terminus
ST_RAIL = Point(N.SPUR[-1])
_u = np.array(N.SPUR[-1]) - np.array(N.SPUR[-4])
_u = _u / np.linalg.norm(_u)
_v = np.array([-_u[1], _u[0]])
_c = np.array(N.SPUR[-1]) - _u * 250.0
RS_FP = Polygon([tuple(_c - _u * 300 - _v * 60), tuple(_c + _u * 300 - _v * 60), tuple(_c + _u * 300 + _v * 60),
                 tuple(_c - _u * 300 + _v * 60)]).difference(_red_all).difference(AIR.buffer(2.0)).buffer(0)
RS_FP = max(getattr(RS_FP, "geoms", [RS_FP]), key=lambda g: g.area).simplify(0.5)
obj("airport_rail_station", "move", reg_pt("airport_rail_station"), P1(RS_FP.centroid.coords[0]), "district_only",
    MODEL + ": вокзал у терминала, в одном узле с конечной ЛРТ «Аэропорт «Алатау»»: конец ветки 10–11 км от обходной ж/д у ПС "
            "«Алма» (полоса util_rail_spur, южнее магистрали, без пересечения с ней); поезда на Алматы-2 и Конаев по обходу",
    kind="transit", footprint=RS_FP, yaw=round(math.degrees(math.atan2(_u[0], _u[1])), 1), years=Y4(2041),
    line=[P1(p) for p in N.SPUR[::max(1, len(N.SPUR) // 30)]] + [P1(N.SPUR[-1])])
MOVED.append(("airport_rail_station", "(−16488, 561) реестр (точка аэропорта)", f"({RS_FP.centroid.x:.0f}, {RS_FP.centroid.y:.0f})",
              "у нового терминала, на конце ветки; точка реестра — точка аэропорта по правилу"))
obj("rail_sorting_station", "by_rule", None, P1(YARD.representative_point().coords[0]), "none",
    MODEL + ": «между аэропортом и Конаевым» (генплан): парк путей вдоль обходной ж/д с северной стороны между ПС «Алма» и А-3 "
            f"({YARD.area / 1e4:.0f} га), вне жилья; Южная промышленная улица севернее, проезд s_rail_x над парком",
    kind="utility", footprint=YARD, yaw=90.0, years=Y4(2045))
MOVED.append(("rail_sorting_station", "схема (−3300, 120)", f"({YARD.representative_point().x:.0f}, {YARD.representative_point().y:.0f})",
              "на сами пути обходной ж/д (схема ставила точку в 400 м от путей)"))


def lot_box(c, w, h, zone_id, ang=0.0):
    c = np.array(c, float)
    u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
    v = np.array([-u[1], u[0]])
    P = Polygon([tuple(c - u * w / 2 - v * h / 2), tuple(c + u * w / 2 - v * h / 2), tuple(c + u * w / 2 + v * h / 2),
                 tuple(c - u * w / 2 + v * h / 2)])
    zp = unary_union([Polygon(z["polygon"]).buffer(0) for z in ZONES if z["_base"] == zone_id])
    g = P.intersection(zp).difference(_red_all).difference(N.POWER_ZONE).difference(N.WATER_STRIP).buffer(0)
    hh = N.houses_hit(g)
    if hh:
        g = g.difference(unary_union([h.buffer(10.0) for h in hh])).buffer(0)
    g = max(getattr(g, "geoms", [g]), key=lambda q_: q_.area) if not g.is_empty else g
    return g.simplify(0.5)


DP = lot_box((-2000.0, 900.0), 700.0, 450.0, "log_dryport_2")
obj("dry_port", "by_rule", None, P1(DP.representative_point().coords[0]), "district_only",
    MODEL + ": «Growing у ж/д» (генплан № 727): контейнерный терминал и таможня в зоне log_dryport_2 у Южной промышленной "
            "улицы, обходной ж/д и сортировочной станции, в 1,5 км от А-3", kind="logistics", footprint=DP, years=Y4(2030))
RH = lot_box((-7000.0, 700.0), 500.0, 400.0, "log_rhenus_2")
obj("rhenus_hub", "by_rule", None, P1(RH.representative_point().coords[0]), "district_only",
    MODEL + ": источник даёт только район; хаб у конца Южной промышленной улицы и начала связи с Аэропортовой магистралью, "
            "рядом с ж/д веткой к аэропорту (ж/д + авиа + А-3)", kind="logistics", footprint=RH, years=Y4(2032))
VI = lot_box((-2350.0, 3350.0), 420.0, 380.0, "campus_voc")
obj("vocational_institute", "by_rule", None, P1(VI.representative_point().coords[0]), "district_only",
    MODEL + ": генплан — профтехинститут в Growing (10–15 тыс. учащихся); у центра «Каскелен», улицы Енбек – Каскелен и станции "
            "ЛРТ; профиль — авиация и логистика рядом с аэропортом и сухим портом", kind="college", footprint=VI,
    years=Y4(2038, "social"), capacity={"places": 12000})
obj("ps_alma_500", "add", None, [-5428.3, -640.8], "point_50m", "существующая (контур OSM), зона util_ps_alma_500; в двойнике её нет",
    basis="по источнику")
obj("ps_220_golden_osm", "add", None, [-4548.0, 1354.4], "point_50m", "существующая (контур OSM)", basis="по источнику")
obj("interchange_a3_km44_0", "add", None, reg_pt("interchange_a3_km44_0"), "point_50m",
    "существующий параллельный съезд А-3 (OSM 05cf2037); полная развязка с Аэропортовой магистралью (путепровод у стыка J148 и "
    "съезды) — уровень 3 вместе с Growing-восток", basis="по источнику")
obj("interchange_a3_km55_9", "add", None, reg_pt("interchange_a3_km55_9"), "point_50m",
    "существующая (OSM): Дорога плато приходит к концевому узлу съездов (250, 13683)", basis="по источнику")
for rid, why in (("road_a3", "существующая; граница половин Growing, общая с Growing-восток (улицы k_* оси a3)"),
                 ("rail_bypass_zhetygen_kazybek", "существующая (OSM 81f6836e); полоса отвода util_rail_bypass; на ней развилка "
                                                  "ветки к аэропорту и сортировочная станция"),
                 ("hv_lines_500", "существующие ВЛ 500 кВ остаются воздушными в своих охранных зонах (corridors, 30 м): через "
                                  "центр «Каскелен» проходит 4fab2f0d — между зонами ctr_main_2 и ctr_main_1 (зона util_power, "
                                  "улицы её пересекают); решение 31.10 о кабеле касается ВЛ 220 кВ"),
                 ("hv_lines_220", "существующие ВЛ 220 кВ остаются воздушными: через центры района не идут (ближайшая 83f0e91a — в "
                                  "3,2 км от центра «Каскелен»); охранные зоны 25 м — corridors"),
                 ("ses_osm_pv", "существующее поле СЭС 108 га (зона util_ses_osm_pv); магистраль и ЛРТ обходят его с севера"),
                 ("district_growing", "граница — контур двойника, разрезанный по А-3 (city.json growing_split)")):
    o = v0obj.get(rid, {})
    obj(rid, "keep", o.get("from"), o.get("to"), o.get("accuracy") or "point_50m", why, basis="по источнику")
for rid in ("growing_polycentres", "growing_industry_types"):
    o = v0obj[rid]
    obj(rid, "by_rule", None, None, "district_only", o["why"])
have = {o["registry_id"] for o in OBJ}
for o in V0["objects"]:
    if o["registry_id"] not in have:
        LOG.append({"what": "объект схемы не перенесён", "id": o["registry_id"]})

# ===================================================================================================== 7. corridors
KV_SRC = "OSM voltage (Overture source_tags уровня 0, w35/overture/infrastructure.parquet)"
CORR = []
for k, q_, kv, w, oid in N.POWER:
    CORR.append({"id": f"pl_{k}", "kind": "power_line", "line": [P1(p) for p in q_.coords], "state": "overhead", "width_m": None,
                 "source": "osm:" + oid, "years": list(C.EXISTING), "osm_class": "power_line", "kv": kv,
                 "kv_basis": f"{KV_SRC}: voltage={int(kv * 1000)}"})
ids_ = {}
for c in CORR:
    ids_[c["id"]] = ids_.get(c["id"], 0) + 1
    if ids_[c["id"]] > 1:
        c["id"] = f"{c['id']}_{ids_[c['id']]}"

# ===================================================================================================== 8. axes, joints, phases
STREET_OF_AXIS = {}
for s in N.STREETS:
    if s.get("axis"):
        STREET_OF_AXIS.setdefault(s["axis"], []).append(s["id"])
axes = copy.deepcopy(V0["axes"])
for a_ in axes:
    pcs = [LineString(s["line"]) for s in N.STREETS if s.get("axis") == a_["id"] and s["_layer"] == "frame"]
    if pcs and a_["id"] not in ("a3", "a3_ramps_s"):
        U_ = unary_union(pcs)
        try:
            U_ = shapely.line_merge(U_)
        except Exception:
            pass
        parts = [g for g in getattr(U_, "geoms", [U_]) if g.geom_type == "LineString"]
        if parts:
            a_["line"] = [P1(p) for p in max(parts, key=lambda g: g.length).simplify(2.0).coords]
    a_["streets"] = STREET_OF_AXIS.get(a_["id"], [])
    for k_ in ("joints",):
        a_.pop(k_, None)
axes.append({"id": "lrt_airport", "class": "lrt", "name_ru": "ЛРТ «Аэропорт»", "status": "new", "years": [2036, 2041],
             "line": [P1(p) for p in L_LRT.simplify(2.0).coords], "streets": [s for s in STREET_OF_AXIS.get("airport_trunk", [])]})
STREET_AT = {"J062": "ЛРТ lrt_growing_w_airport (конец, эстакада над А-3)",
             "J148": "s_trunk_1 (Аэропортовая магистраль, путепровод над А-3; съезды км 44 — уровень 3 с Growing-восток)",
             "J147": "s_n48 (путепровод над А-3; съезды км 48 — уровень 3 с Growing-восток)",
             "J146": "s_n50 (путепровод над А-3; съезды км 50,5 — уровень 3 с Growing-восток)",
             "J143": "s_air_south (продолжение X-IA Golden до южных ворот аэропорта)",
             "J077": "s_south через существующий тоннель OSM bdc5c57b под А-3 (западный выход (−592, 222))",
             "J031": "обходная ж/д (OSM 81f6836e), полоса util_rail_bypass", "J063": "обходная ж/д (OSM 81f6836e), полоса util_rail_bypass"}
JOINTS = []
for j in CITY["joints"]["items"]:
    if "growing_w" not in (j.get("between") or []):
        continue
    how = STREET_AT.get(j["id"])
    if how is None and j.get("kind") == "road":
        how = "А-3 / съезды OSM (k_*), как есть"
    JOINTS.append({"joint_id": j["id"], "x": j["x"], "z": j["z"], "kind": j.get("kind"), "between": j.get("between"),
                   "line": j.get("line"), "met_by": how})
PHASES = copy.deepcopy(V0["phases"])
for ph in PHASES:
    ph["axes"] = [a for a in ph.get("axes", [])]
    ph["streets"] = sorted({s for a in ph["axes"] for s in STREET_OF_AXIS.get(a, [])})

# ===================================================================================================== 9. spec
STREETS_OUT = []
for s in N.STREETS:
    d = {k: v for k, v in s.items() if not k.startswith("_")}
    q = [list(map(float, d["line"][0]))]
    for pt in d["line"][1:]:
        if math.dist(pt, q[-1]) > 0.05:
            q.append(list(map(float, pt)))
    d["line"] = q
    if len(q) < 2:
        continue
    STREETS_OUT.append(d)
SIDS = {s["id"] for s in STREETS_OUT}
NODES_OUT = []
for n in N.NODES.values():
    d = copy.deepcopy(n)
    d["streets"] = [x for x in d["streets"] if x in SIDS]
    if not d["streets"] and not d["params"].get("keep_existing"):
        continue
    NODES_OUT.append(d)
ZONES_OUT = [{k: v for k, v in z.items() if not k.startswith("_")} for z in ZONES]

spec = {
    "district": "growing_w", "version": 1, "level": 2,
    "made_by": "w52 tools/map/district/growing_w_build.py",
    "boundary": "city.json#districts/growing_w",
    "attribution": C.ATTRIBUTION,
    "area": [P1(p) for p in list(POLY.exterior.coords)[:-1]],
    "area_ha": round(POLY.area / 1e4, 1),
    "targets": TARGETS,
    "centres": V0["centres"],
    "axes": axes,
    "zones": ZONES_OUT,
    "lrt": LRT,
    "objects": OBJ,
    "phases": PHASES,
    "joints": JOINTS,
    "edge_joints": [],
    "streets": STREETS_OUT,
    "nodes": NODES_OUT,
    "keep": [],
    "views": [],
    "utilities": [],
    "corridors": CORR,
    "replaced_osm": sorted(set(N.RETIRED)),
    "scheme_changes": [{"id": k, "why": v} for k, v in N.SCHEME_CHANGES + [SCHEME_CHANGES_LRT]] + [{"id": k, "why": v} for k, v in Z.CHANGES],
    "moved_objects": [{"id": a, "was": b, "now": c, "why": d} for a, b, c, d in MOVED],
    "open_questions": V0.get("open_questions", []),
    "checks": {},
}

if __name__ == "__main__":
    import growing_w_check as CHK
    res = CHK.run(spec, verbose=False)
    spec["checks"] = res
    spec["checks"]["build_log"] = LOG[:500]
    txt = json.dumps(spec, ensure_ascii=False, indent=1)
    with open(SPEC_OUT + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write(txt + "\n")
    os.replace(SPEC_OUT + ".tmp", SPEC_OUT)
    from collections import Counter
    print(f"wrote {SPEC_OUT}: {len(txt) // 1024} KB; streets {len(STREETS_OUT)}, nodes {len(NODES_OUT)}, zones {len(ZONES_OUT)}, "
          f"objects {len(OBJ)}; {time.time() - T0:.1f} s")
    print("targets", {k: TARGETS[k] for k in ("homes_2050", "population_2050", "jobs_2050")}, "FH %.3f FJ %.3f" % (FH, FJ),
          TARGETS["plan_by_density"])
    print("log", Counter(x["what"] for x in LOG))
    if "--no-check" not in sys.argv:
        ok = CHK.main([SPEC_OUT])
        sys.exit(0 if ok else 1)
