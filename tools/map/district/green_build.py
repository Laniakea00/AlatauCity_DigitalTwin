#!/usr/bin/env python3
"""Green · level 2 · builder of tools/map/spec/green.json v1 (w51): the whole district.

    python3 -I tools/map/district/green_build.py [--no-check] [--out SPEC.json]

Builds on the approved level-0 scheme (district/green_v0.json = spec/green.json v0 of 31.10). Network: green_net.py (existing
roads, the frame of the scheme axes, local streets of every new quarter); zones: green_zones.py. Here: LRT v1 with its
stations (both ends are joints: J046 to Growing-E, J052 to Конаев), objects (registry rows: by source / by rule), targets and
densities, sanitary gaps, phases, axes, joints, replaced roads, power-line corridors with their voltage, and the self-check
(green_check.py). Every coordinate not from a source is the cartographer's design (label «модель qTwin»). Unity frame:
X east, Z north.
"""
import copy
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
T0 = time.time()
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import substring, unary_union  # noqa: E402

import green_common as C  # noqa: E402
import green_net as N  # noqa: E402
import green_zones as Z  # noqa: E402
import land_util as LU  # noqa: E402

SPEC_OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(C.SPEC_DIR, "green.json")
MODEL = C.MODEL
Y4 = C.Y4
fillet = C.fillet
CITY = C.CITY
REG = C.REG
V0 = C.V0
GREEN = C.GREEN
P1 = C.P1
poly_pts = C.poly_pts
LOG = []
TIMES = {}


def tick(what, t):
    TIMES[what] = round(time.time() - t, 1)


# ===================================================================================================== 1. LRT line (frame)
JN = {j["id"]: j for j in CITY["joints"]["items"]}
J046 = (JN["J046"]["x"], JN["J046"]["z"])          # LRT joint Green – Growing-E (south)
J052 = (JN["J052"]["x"], JN["J052"]["z"])          # LRT joint Green – Конаев (north)
# own right of way from J046 north along the Каскелен park, past the village Құйған-Север on its east side, into the median
# of Проспект Green at its south end; in the median to the avenue's north end; own right of way across the exhibition
# quarter to J052
LRT_S = fillet([J046, (3745.0, 13450.0), (3790.0, 13900.0), tuple(N.PROSP_S[0])], 200)
LRT_N = fillet([tuple(N.PROSP_N[-1]), (2860.0, 22900.0), J052], 250)    # 8° bend at the avenue's end (R ≈ 75 m at 10 m chords)
k_n = 0
LRT_PTS = [tuple(p) for p in LRT_S] + [tuple(p) for p in N.PROSP_S[1:]] + [tuple(p) for p in N.PROSP_N[1:]] + \
          [tuple(p) for p in LRT_N[k_n + 1:]]
q = [LRT_PTS[0]]
for p in LRT_PTS[1:]:
    if math.dist(p, q[-1]) > 0.5:
        q.append(p)
LRT_PTS = q
L_LRT = LineString(LRT_PTS)
LRT_W = N.LRT_W


def chain(pt):
    return L_LRT.project(Point(pt))


def at_chain(s):
    p = L_LRT.interpolate(s)
    return (p.x, p.y)


S_P0 = chain(N.PROSP_S[0])
S_PN = chain(N.PROSP_N[-1])
OWN_ROW = unary_union([substring(L_LRT, 0, S_P0).buffer(LRT_W / 2 + 2, cap_style=2),
                       substring(L_LRT, S_PN, L_LRT.length).buffer(LRT_W / 2 + 2, cap_style=2)])
# stations: the scheme's nine, projected on the line, then centred between the cross streets (rule 25)
ST_PLAN = [("st_kuygan", "Құйған"), ("st_kaskelen", "Каскелен"), ("st_south", "Южный"), ("st_central", "Центральные кварталы"),
           ("st_arnaut", "Арнаутская"), ("st_park", "Центральный парк"), ("st_zaliv", "Залив"), ("st_gc", "Green-Сити"),
           ("st_expo", "Выставка")]
V0ST = {s["id"]: s for s in V0["lrt"]["stations"]}
ST_S = {sid: chain((V0ST[sid]["x"], V0ST[sid]["z"])) for sid, _ in ST_PLAN}
ST_XY = {sid: at_chain(s) for sid, s in ST_S.items()}
LOG.append({"what": "ЛРТ: длина и станции по схеме (до центровки)", "m": round(L_LRT.length),
            "chain": {k: round(v) for k, v in ST_S.items()}})

# ===================================================================================================== 2. local streets
STATION_PTS = [ST_XY[k] for k, _ in ST_PLAN]
t = time.time()
made = N.generate_local(stations=STATION_PTS, barriers=OWN_ROW, lrt_line=L_LRT)
tick("generate_local", t)
LOG.append({"what": "местные улицы сгенерированы", "n": made, "s": TIMES["generate_local"]})


def ext_ok(P):
    return GREEN.exterior.distance(P) < 3.0 or any(math.dist((P.x, P.y), (n["x"], n["z"])) < 1.0 for n in N.NODES.values()
                                                   if n["type"] == "joint")


def _free_ends(layers):
    lines = N.all_lines()
    tree = shapely.STRtree([L for _, L, _, _ in lines])
    out = []
    for s in N.STREETS:
        if s["_layer"] not in layers:
            continue
        for end in (0, -1):
            P = Point(s["line"][end])
            if any(lines[i][0] != s["id"] and lines[i][2] not in N.NO_JUNCTION and lines[i][1].distance(P) < 0.5
                   for i in tree.query(P.buffer(0.6))):
                continue
            if ext_ok(P):
                continue
            if any(s["id"] in n.get("streets", []) and math.dist(s["line"][end], (n["x"], n["z"])) < 1.0 for n in N.NODES.values()):
                continue
            out.append((s, end))
    return out


def fix_frame_ends(layers=("frame",), reach=400.0, back=90.0, near_m=300.0):
    """Free ends of the frame streets: (a) cut back to the last junction when it is within `back` m of the end (a stub left
    past a quarter's edge street), else (b) on along the street's direction to the first street (≤ reach), else (c) a
    straight link to the nearest street (≤ near_m); never through houses, across an expressway, a ramp, the railway or
    water beyond a bridge. What is left is logged (the self-check lists it)."""
    out = []
    for s, end in _free_ends(layers):
        L = LineString(s["line"])
        oth = [(sid, M, cls) for sid, M, cls, _ in N.all_lines() if sid != s["id"]]
        ot = shapely.STRtree([M for _, M, _ in oth])
        ch = [c for c in N._cut_points(L, oth, ot, s) if 0.5 < c < L.length - 0.5]
        pt = s["line"][end]
        if ch:
            c = ch[-1] if end == -1 else ch[0]
            stub = L.length - c if end == -1 else c
            if stub <= back:
                q_ = substring(L, 0, c) if end == -1 else substring(L, c, L.length)
                s["line"] = [P1(p) for p in q_.coords]
                s["struct"] = [x for x in s.get("struct") or [] if q_.distance(Point(x["from"])) < 1 and q_.distance(Point(x["to"])) < 1]
                out.append({"what": "конец улицы каркаса обрезан до перекрёстка", "id": s["id"], "m": round(stub, 1)})
                continue
        prev = s["line"][1] if end == 0 else s["line"][-2]
        d = np.array(pt, float) - np.array(prev, float)
        d /= np.linalg.norm(d)
        hosts = [M for sid, M, cls in oth if cls not in N.NO_HOST]
        barrier = unary_union([M for _, M, cls in oth if cls in ("expressway", "ramp")])
        hp = N._ray_hit(tuple(pt), d, hosts, reach)
        cand = []
        if hp is not None:
            cand.append(LineString([tuple(pt), hp]))
        P = Point(pt)
        for M in sorted(hosts, key=lambda M: M.distance(P))[:6]:
            if M.distance(P) > near_m:
                break
            f = M.interpolate(M.project(P))
            if f.distance(P) > 1.0:
                cand.append(LineString([tuple(pt), (f.x, f.y)]))
        done = False
        for seg in cand:
            if N.houses_hit(seg.buffer(N.red_w(s["class"]) / 2.0)) or seg.crosses(barrier) or seg.intersects(N.RAIL) \
                    or not GREEN.buffer(1.0).contains(seg):
                continue
            hp_ = seg.coords[-1]
            if end == 0:
                s["line"].insert(0, P1(hp_))
            else:
                s["line"].append(P1(hp_))
            s["struct"] += [{"from": P1(a_), "to": P1(b_), "kind": k} for a_, b_, k in N.water_bridges(list(seg.coords))]
            out.append({"what": "улица каркаса продолжена до ближайшей улицы", "id": s["id"], "to": P1(hp_),
                        "m": round(seg.length, 1)})
            done = True
            break
        if not done:
            out.append({"what": "конец улицы каркаса без продолжения", "id": s["id"], "at": P1(pt)})
    return out


t = time.time()
LOG += fix_frame_ends()
TRIM_LOG = []
N.trim_free_ends(ext_ok, log=TRIM_LOG)
LOG += TRIM_LOG
N.snap_ends(tol=10.0, log=LOG)
N.house_lanes(log=LOG)
N.link_dead_ends(log=LOG)
N.merge_through(log=LOG)


def fix_divided_ends(log=None):
    """The end of a divided frame street (its two carriageways end apart) where more than one street starts: gen_network
    takes one street across both carriageways and the next only to the near one, so a third street that ends at the same
    point would leave a carriageway end blind in some year. A generated street ending there is moved 30 m along the frame
    street it runs with (the one nearest its own direction)."""
    n = 0
    div = [x for x in N.STREETS if x["class"] == "arterial_regulated"]
    for d in div:
        for e in (0, -1):
            E = Point(d["line"][e])
            at = [(x, k) for x in N.STREETS if x is not d for k in (0, -1) if Point(x["line"][k]).distance(E) < 1.0]
            if len(at) < 2:
                continue
            frame = [(x, k) for x, k in at if x["_layer"] == "frame"]
            for x, k in at:
                if x["_layer"] == "frame" or not frame:
                    continue
                L = LineString(x["line"])
                dx = np.array(L.interpolate(min(20.0, L.length) if k == 0 else max(0.0, L.length - 20.0)).coords[0]) - np.array(E.coords[0])
                best = None
                for f, kf in frame:
                    F = LineString(f["line"])
                    q_ = F.interpolate(30.0 if kf == 0 else F.length - 30.0)
                    v = np.array(q_.coords[0]) - np.array(E.coords[0])
                    c = float(dx @ v) / (np.linalg.norm(dx) * np.linalg.norm(v) + 1e-9)
                    if best is None or c > best[0]:
                        best = (c, q_, f["id"])
                c, q_, fid = best
                if N.houses_hit(LineString([q_, L.interpolate(30.0 if k == 0 else L.length - 30.0)]).buffer(7.5)):
                    continue
                x["line"][k] = [round(q_.x, 2), round(q_.y, 2)]
                n += 1
                if log is not None:
                    log.append({"what": "конец улицы квартала снят с конца разделённой магистрали на соседнюю улицу",
                                "id": x["id"], "street": d["id"], "onto": fid, "at": [round(q_.x), round(q_.y)]})
    return n


fix_divided_ends(log=LOG)
tick("post-pass", t)


def serve_pieces(log=None, min_m2=2000.0, reach=150.0, inside=15.0):
    """Built zone land that the streets and the LRT's own corridor cut off from every street (rule 12: a block with
    buildings needs an entry): a local side street from the nearest street into the piece (≤ reach, ending `inside` m in),
    never across an expressway, a ramp, the LRT corridor, the railway, water or a house. Returns the streets made."""
    lines = [(x["id"], LineString(x["line"]), x["class"]) for x in N.STREETS]
    lines += [("osm:" + oid, q_, cls) for oid, q_, cls in N.OSM_HOST]
    reds = unary_union([L.buffer(N.red_w(c) / 2.0) for _, L, c in lines if c not in ("expressway", "ramp")]
                       + [L.buffer(N.EXP_HALF) for _, L, c in lines if c in ("expressway", "ramp")])
    acc = [(sid, L, c) for sid, L, c in lines if c not in ("expressway", "ramp", "pedestrian_street", "bike_path", "boulevard")]
    at = shapely.STRtree([L for _, L, _ in acc])
    barrier = unary_union([L for _, L, c in lines if c in ("expressway", "ramp")] + [OWN_ROW])
    made_ = []
    for z in Z.ZPLAN:
        if z["use"] not in Z.DEV_USES or (z.get("rules") or {}).get("lot_split") == "none":
            continue
        land = z["poly"].intersection(GREEN).difference(reds).difference(OWN_ROW).buffer(0)
        for q_ in getattr(land, "geoms", [land]):
            if q_.geom_type != "Polygon" or q_.area < min_m2:
                continue
            if any(acc[i][1].buffer(N.red_w(acc[i][2]) / 2.0 + 2.5).intersects(q_) for i in at.query(q_.buffer(N.EXP_HALF))):
                continue
            best = None
            for i in at.query(q_.buffer(reach)):
                sid, L, c = acc[i]
                a, b = shapely.ops.nearest_points(L, q_)
                d = a.distance(b)
                if d > reach - inside or (best is not None and d >= best[0]):
                    continue
                u = np.array([b.x - a.x, b.y - a.y]) / max(d, 1e-6)
                end = Point(b.x + u[0] * inside, b.y + u[1] * inside)
                sp = LineString([(a.x, a.y), (end.x, end.y)])
                if sp.crosses(barrier) or sp.intersects(OWN_ROW) or sp.intersects(N.WATER_POLY) or sp.intersects(N.RAIL) \
                        or not GREEN.contains(sp) or N.houses_hit(sp.buffer(N.red_w("local") / 2.0)) or not q_.contains(end):
                    continue
                best = (d, sid, sp)
            rec = {"zone": z["id"], "ha": round(q_.area / 1e4, 2), "at": [round(v) for v in q_.representative_point().coords[0]]}
            if best is None:
                if log is not None:
                    log.append({"what": "земля зоны без улицы: подъезда нет (ждёт решения)", **rec})
                continue
            sid_new = f"v_serve_{len(made_) + 1:02d}"
            N.street(sid_new, "local", best[2].coords, "въезд в квартал", int(z["years"][0]), layer="lane",
                     why=MODEL + f": земля зоны {z['id']} ({q_.area / 1e4:.1f} га) отрезана от улиц линией ЛРТ и границами зон — "
                                 f"въезд {best[2].length:.0f} м от {best[1]} (правило 12: у квартала со зданиями есть въезд)")
            made_.append(sid_new)
            if log is not None:
                log.append({"what": "въезд в отрезанную землю зоны", "id": sid_new, "from": best[1], "m": round(best[2].length), **rec})
    return made_


t = time.time()
serve_pieces(log=LOG)


# farmsteads in village zones that no street of the generated network comes within 150 m of (gen_network run of 01.11:
# its village lattice reaches house_access_m + 60 m round a village, these stand 266–649 m off): rule 12 «квартал без
# въезда», rule 14 «нет на сети». Each gets one lane «модель qTwin» as an existing farm track.
HAMLET_AT = [(-1485.0, 22358.0), (-111.0, 22604.0), (14296.0, 16383.0), (8216.0, 16476.0), (11785.0, 19142.0)]


def hamlet_lanes(log=None, reach=1200.0, stop=12.0):
    """One lane per farmstead of HAMLET_AT: from the nearest street (an existing road when one is within 1.5 × the
    nearest) to `stop` m short of its nearest house, never through a house, water, rail or a motorway. Years 2025 and the
    OSM layer (a farm track the source does not have; phase_years keeps it as an existing road)."""
    made_ = []
    lines = [(s["id"], LineString(s["line"]), s["class"], s["years"][0] <= 2025) for s in N.STREETS
             if s["class"] not in ("expressway", "ramp", "arterial_continuous")]
    lines += [("osm:" + oid, q_, cls, True) for oid, q_, cls in N.OSM_HOST if cls not in ("expressway", "ramp")]
    tree = shapely.STRtree([L for _, L, _, _ in lines])
    barrier = unary_union([LineString(s["line"]).buffer(30.0) for s in N.STREETS if s["class"] in ("expressway", "ramp")]
                          + [q_.buffer(30.0) for _, q_, c_ in N.OSM_HOST if c_ in ("expressway", "ramp")])
    for at in HAMLET_AT:
        hs = [h for h in N.HOUSES if h.distance(Point(at)) < 80.0]
        rec = {"houses": len(hs), "at": [round(v) for v in at]}
        if not hs:
            if log is not None:
                log.append({"what": "хутор: домов у точки нет", **rec})
            continue
        hu = unary_union(hs)
        cands = []
        for i in tree.query(hu.buffer(reach)):
            sid, L, cls, old = lines[int(i)]
            a, b = shapely.ops.nearest_points(L, hu)
            d = a.distance(b)
            u = np.array([b.x - a.x, b.y - a.y]) / max(d, 1e-6)
            end = Point(b.x - u[0] * stop, b.y - u[1] * stop)
            sp = LineString([(a.x, a.y), (end.x, end.y)])
            if sp.length < 5.0 or sp.intersects(N.WATER_POLY) or sp.intersects(N.RAIL) or sp.intersects(barrier) \
                    or N.houses_hit(sp.buffer(N.red_w("village_lane") / 2.0)) or not GREEN.contains(sp):
                continue
            cands.append((sp.length, sid, sp, old))
        if not cands:
            if log is not None:
                log.append({"what": "хутор без подъезда: дорогу провести нельзя (вода, пути, трасса или дома)", **rec})
            continue
        cands.sort(key=lambda t: t[0])
        olds = [c_ for c_ in cands if c_[3] and c_[0] <= 1.5 * cands[0][0]]
        best = olds[0] if olds else cands[0]
        sid_new = f"v_hamlet_{len(made_) + 1}"
        N.street(sid_new, "village_lane", best[2].coords, "подъезд к хутору (модель qTwin)", 2025, years=C.EXISTING, layer="osm",
                 why=MODEL + f": {len(hs)} существующих дома в {best[0] + stop:.0f} м от ближайшей улицы ({best[1]}); в OSM подъезда "
                             "нет, сельский проулок gen_network до них не дотягивается — полевой подъезд как существующий "
                             "проулок (правила 12 и 14: у дома есть въезд и пешая связь)")
        made_.append(sid_new)
        if log is not None:
            log.append({"what": "подъезд к хутору", "id": sid_new, "from": best[1], "m": round(best[0]), "existing_host": best[3], **rec})
        Z.SCHEME_CHANGES.append((sid_new, f"подъезд {best[0]:.0f} м к {len(hs)} существующим домам у ({rec['at'][0]}, {rec['at'][1]}): "
                                          "хутор в стороне от улиц, в OSM дороги к нему нет"))
    return made_


HAMLETS = hamlet_lanes(log=LOG)
YEAR_MOVES = N.phase_years(Polygon(), log=LOG)
tick("serve+years", t)
for s in N.STREETS:
    if s["class"].startswith("driveway"):
        s["class"] = "local"
        s["why"] = (s.get("why") or "") + "; в green.json — местная улица (проезды даёт только land_driveways)"

# ===================================================================================================== 3. LRT v1
ROADS_X = []
_LB = L_LRT.buffer(7.0, cap_style=2)          # a street that ends at the avenue's axis is taken across its median


def _x_lrt(L, sid):
    x = L.intersection(_LB)
    for g in getattr(x, "geoms", [x]):
        if g.is_empty:
            continue
        ROADS_X.append((chain(g.centroid.coords[0]), sid))


for s in N.STREETS:
    if s["class"] in ("expressway", "ramp"):
        continue
    _x_lrt(LineString(s["line"]), s["id"])
for oid, q_, cls in N.OSM_HOST:
    _x_lrt(q_, "osm:" + oid[:8])
ROADS_X.sort()
PLAT = 33.0


def place_station(sid, s0):
    before = [c for c in ROADS_X if c[0] <= s0]
    after = [c for c in ROADS_X if c[0] > s0]
    lo = before[-1][0] if before else 0.0
    hi = after[0][0] if after else L_LRT.length
    if hi - lo < PLAT + 20:
        LOG.append({"what": "станция ЛРТ: промежуток между улицами мал", "id": sid, "m": round(hi - lo, 1)})
    sm = 0.5 * (lo + hi) if (hi - lo) < 200 or abs(s0 - 0.5 * (lo + hi)) > (hi - lo) / 2 - PLAT else s0
    return at_chain(sm), sm


STATIONS = []
for sid, nm in ST_PLAN:
    p, sm = place_station(sid, ST_S[sid])
    before = [c for c in ROADS_X if c[0] < sm]
    after = [c for c in ROADS_X if c[0] > sm]
    STATIONS.append({"id": sid, "name_ru": nm, "x": round(p[0], 1), "z": round(p[1], 1),
                     "between": [before[-1][1] if before else None, after[0][1] if after else None], "kind": "ground", "_s": sm})
STATIONS.sort(key=lambda s_: s_["_s"])
LOG.append({"what": "ЛРТ: станции между поперечными улицами", "chain": [round(s_["_s"]) for s_ in STATIONS],
            "spacing": [round(b["_s"] - a["_s"]) for a, b in zip(STATIONS, STATIONS[1:])]})
LRT_YEARS = Y4(2033)
# Growing-E brings the line to J046 on a viaduct (its section 12757–13067 elevated); it stays up over the two existing OSM
# roads just north of the joint (08a85d88 and 0d0e30e9, unclassified, no junction where the line crosses: rule 1 allows an
# at-grade LRT crossing only at a node) and comes down at the ramp slope (lrt.ramp_slope_max_pct) before the first new street
LRT_EL_M = 360.0
LRT = {
    "lines": [{
        "id": "lrt_green", "name_ru": "ЛРТ Құйған – Green-Сити – Конаев (участок Green)",
        "line": [P1(p) for p in LRT_PTS],
        "sections": [{"from": P1(LRT_PTS[0]), "to": P1(at_chain(LRT_EL_M)), "kind": "elevated"},
                     {"from": P1(at_chain(LRT_EL_M)), "to": P1(LRT_PTS[-1]), "kind": "ground"}],
        "stations": [{k: v for k, v in s_.items() if not k.startswith("_")} for s_ in STATIONS],
        "ends": [{"kind": "joint", "id": "J046", "x": J046[0], "z": J046[1], "to": "growing_e"},
                 {"kind": "joint", "id": "J052", "x": J052[0], "z": J052[1], "to": "outside"}],
        "joints": [{"joint_id": "J046", "x": J046[0], "z": J046[1], "to": "growing_e"},
                   {"joint_id": "J052", "x": J052[0], "z": J052[1], "to": "outside"}],
        "years": LRT_YEARS,
        "why": "оси схемы lrt_south + lrt_north (ствол ЛРТ генплана): от стыка J046 с Growing-E по своей полосе вдоль парка "
               "Каскелена и восточного края села Құйған-Север, дальше в разделительной полосе Проспекта Green через центры "
               "Южный, Арнаутская и Green-Сити, по своей полосе через выставочный квартал к стыку J052 на Конаев; 9 станций "
               "схемы, каждая между поперечными улицами; первые 360 м от стыка — эстакада (продолжение эстакады Growing-E над "
               "двумя существующими дорогами OSM без перекрёстков), дальше на земле (рельеф 485–500 м); одна очередь 2033 "
               "(у схемы 2029–2036: участок без связи с соседями не открывается отдельно)"}],
    "depots": []}

# ===================================================================================================== 4. zones
ZONES = []
ZIDS = set()
taken = Polygon()


def zone_out(z, poly, rules):
    global taken
    parts = C.simple_parts(poly.buffer(0).intersection(GREEN).difference(taken).buffer(0), 500.0)
    for k, q_ in enumerate(parts):
        taken = taken.union(q_)
        zid = z["id"] if k == 0 else f"{z['id']}_p{k + 1}"
        if zid in ZIDS:
            zid = zid + "_s"
        ZIDS.add(zid)
        d = {"id": zid, "use": z["use"], "name_ru": z["name_ru"], "polygon": poly_pts(q_),
             "years": z["years"], "rules": copy.deepcopy(rules), "why": z["why"], "area_ha": round(q_.area / 1e4, 2),
             "_src": z["src"], "_base": z["id"]}
        if z.get("density"):
            # the scheme's «floors_typical» is a text range ("5–9"): the land tools read a number there, so it goes as text
            dd = dict(z["density"])
            ft = dd.pop("floors_typical", None)
            if ft is not None and not isinstance(ft, (int, float)):
                dd["floors_typical_ru"] = str(ft)
            elif ft is not None:
                dd["floors_typical"] = ft
            d["density"] = dd
        ZONES.append(d)


# the 30-storey landmark tower at the tip of the IRCC cape (registry green_tower_30, scheme point (5100, 21400)): its own zone
# with the tower's height (≈ 105 m; ≥ 50 m — «нужно согласование», heights.airfield_approval_radius_km)
TOWER_AT = (5100.0, 21400.0)
_irc = Z.ZBY["ircc"]
_red_near = unary_union([LineString(x["line"]).buffer(N.red_w(x["class"], x.get("profile")) / 2.0 + 0.05, cap_style=2)
                         for x in N.STREETS if LineString(x["line"]).distance(Point(TOWER_AT)) < 400.0])
_free = _irc["poly"].difference(_red_near).buffer(0)
_blk = min(getattr(_free, "geoms", [_free]), key=lambda g: g.distance(Point(TOWER_AT)))
TOWER_FP = _blk.intersection(Point(TOWER_AT).buffer(75.0)).buffer(0)
if TOWER_FP.geom_type != "Polygon":
    TOWER_FP = max(TOWER_FP.geoms, key=lambda g: g.area)
_irc["poly"] = _irc["poly"].difference(TOWER_FP).buffer(0)
Z.ZPLAN.append({"id": "gc_tower", "use": "mixed_centre", "name_ru": "Доминанта у озера (30 этажей)", "poly": TOWER_FP,
                "years": [2036, 2040],
                "rules": C.rules([24, 30], 110, 6.0, [80, 160], "towers", "underground", 150.0, 120.0),
                "density": None, "src": "v0",
                "why": MODEL + ": участок 30-этажной доминанты на мысу курорта (реестр green_tower_30, «главный ориентир» Yestate), "
                               "≈ 105 м; ≥ 50 м — нужно согласование (аэродром Жетыген в 30 км)"})
Z.SCHEME_CHANGES.append(("gc_tower", f"участок доминанты ({TOWER_FP.area / 1e4:.1f} га) вынут из зоны ircc в свою зону высотой до "
                                     "110 м (30 этажей): правила зоны курорта (4–12 этажей) не дают башню реестра"))

# sanitary gaps (rule 15): logistics zones state their SZZ class
_LN = LU.Norms()
SZZ_W = {k: float(v["min"]) for k, v in _LN.v("szz.class_width_m").items()}
_WS = _LN.v("szz.wind_sector_deg")
SZZ_F, SZZ_SECTOR = float(_WS["zone_factor"]), tuple(_WS["default_sector"])
SZZ_DEFAULT = ("V", MODEL + ": склады и логистика готовых товаров без выбросов — наименьший класс szz.class_width_m "
                           "(в szz.class_examples складов нет)")
for z in Z.ZPLAN:
    if z["use"] in ("industry", "logistics"):
        z["rules"]["szz_class"] = SZZ_DEFAULT[0]
        z["why"] = z["why"] + f"; СЗЗ класса {SZZ_DEFAULT[0]} ({SZZ_W[SZZ_DEFAULT[0]]:.0f} м): {SZZ_DEFAULT[1]}"
        z["rules"]["parking"]["type"] = "multi"


def _wedge(poly, a0, a1, r, step=20.0):
    b = poly.exterior
    pts = [b.interpolate(t_) for t_ in np.arange(0.0, b.length, step)] + [poly.centroid]
    angs = np.radians(np.linspace(a0, a1 if a1 >= a0 else a1 + 360.0, 13))
    out = []
    for p in pts:
        out.append(Polygon([(p.x, p.y)] + [(p.x + r * math.sin(t_), p.y + r * math.cos(t_)) for t_ in angs]))
    return unary_union(out)


RES_USES = ("residential_high", "residential_mid", "residential_low", "mixed_centre")
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
        zone_out({"id": f"g_szz_{I['id']}_{R['id']}", "use": "park", "src": "v0", "years": R["years"],
                  "name_ru": f"Санитарный разрыв {I['name_ru']} — {R['name_ru']} (озеленение)",
                  "why": f"СЗЗ класса {I['rules']['szz_class']}: {w:.0f} м, в подветренном секторе — {reach:.0f} м (правило 15)"},
                 strip, {"lot_split": "none"})
        SZZ_LOG.append((I["id"], R["id"], round(strip.area / 1e4, 2)))
    back = ((SZZ_SECTOR[0] + 180.0) % 360.0, (SZZ_SECTOR[1] + 180.0) % 360.0)
    vil = [R["poly"] for R in Z.ZPLAN if R["use"] == "village_existing" and I["poly"].distance(R["poly"]) < reach]
    hs = [h for h in N.HOUSES if I["poly"].buffer(reach).intersects(h) and not any(v.contains(h.centroid) for v in vil)]
    if vil or hs:
        near = unary_union(vil + hs)
        wedges = [_wedge(q_, *back, reach) for q_ in vil] + [_wedge(h.convex_hull.buffer(0.5), *back, reach, step=10.0) for h in hs]
        strip = I["poly"].intersection(near.buffer(w).union(unary_union(wedges))).buffer(0)
        if strip.area >= 500.0:
            zone_out({"id": f"g_szz_{I['id']}_houses", "use": "park", "src": "v0", "years": I["years"],
                      "name_ru": f"Санитарный разрыв {I['name_ru']} — существующие дома (озеленение)",
                      "why": f"СЗЗ класса {I['rules']['szz_class']}: {w:.0f} м, по ветру {reach:.0f} м (правило 15) от "
                             "существующих домов (сёла рядом остаются)"},
                     strip, {"lot_split": "none"})
            SZZ_LOG.append((I["id"], "existing houses", round(strip.area / 1e4, 2)))
            Z.SCHEME_CHANGES.append((f"g_szz_{I['id']}_houses", f"санитарный разрыв ({strip.area / 1e4:.2f} га) из зоны {I['id']} "
                                     "у существующих домов: озеленение"))
LOG.append({"what": "санитарные разрывы (озеленение) между логистикой и жильём", "pairs": SZZ_LOG})
for k, P in enumerate(N.UNSERVED):
    q_ = P.buffer(N.D_IN + 2.0)
    zone_out({"id": f"x_unserved_{k + 1}", "use": "reserve", "src": "v0", "years": [2050, 2050],
              "name_ru": "Резерв: участок без подъезда (между водой, трассой и сёлами)",
              "why": "ни одна улица не доходит до участка без пересечения трассы или домов: резерв до подъезда"},
             q_, {"lot_split": "none"})
    LOG.append({"what": "участок без подъезда переведён в резерв", "ha": round(q_.area / 1e4, 1), "at": [round(v) for v in P.centroid.coords[0]]})
    Z.SCHEME_CHANGES.append((f"x_unserved_{k + 1}", f"{q_.area / 1e4:.1f} га у ({P.centroid.x:.0f}, {P.centroid.y:.0f}) — резерв: "
                             "до участка не дойти улицей"))
for z in Z.ZPLAN:
    zone_out(z, z["poly"], z["rules"])
_gap = GREEN.difference(unary_union([Polygon(z["polygon"]).buffer(0) for z in ZONES]))
_ZT = shapely.STRtree([Polygon(z["polygon"]).buffer(0) for z in ZONES])
for g in [q_ for q_ in getattr(_gap, "geoms", [_gap]) if q_.geom_type == "Polygon" and q_.area > 1.0]:
    best, bl = None, 0.0
    for i in _ZT.query(g.buffer(0.5)):
        sh = Polygon(ZONES[int(i)]["polygon"]).buffer(0).exterior.intersection(g.buffer(0.5)).length
        if sh > bl:
            best, bl = int(i), sh
    if best is None:
        continue
    m = Polygon(ZONES[best]["polygon"]).buffer(0).union(g.buffer(0.05)).buffer(0)
    if m.geom_type == "Polygon" and not m.interiors:
        ZONES[best]["polygon"] = poly_pts(m)
        ZONES[best]["area_ha"] = round(m.area / 1e4, 2)
# no overlaps left by the gap filling or by rounding the vertices to 0.1 m along long shared borders
_done = []
for z in ZONES:
    p_ = Polygon(z["polygon"]).buffer(0)
    if _done:
        p_ = p_.difference(unary_union([q_.buffer(0.03, join_style=2) for q_ in _done])).buffer(0)
    if p_.geom_type != "Polygon":
        p_ = max(getattr(p_, "geoms", [p_]), key=lambda g: g.area)
    z["polygon"] = poly_pts(p_)
    z["area_ha"] = round(p_.area / 1e4, 2)
    _done.append(Polygon(z["polygon"]).buffer(0))

# ===================================================================================================== 5. targets and densities
RED = unary_union([LineString(s["line"]).buffer(N.red_w(s["class"], s.get("profile")) / 2.0, cap_style=2) for s in N.STREETS
                   if s["class"] not in ("expressway", "ramp")]
                  + [LineString(s["line"]).buffer(25.0, cap_style=2) for s in N.STREETS if s["class"] == "expressway"]
                  + [q_.buffer(N.red_w(cls) / 2.0, cap_style=2) for _, q_, cls in N.OSM_HOST])
NET_LAND = GREEN.difference(RED).difference(OWN_ROW)


def net_ha(z):
    return Polygon(z["polygon"]).buffer(0).intersection(NET_LAND).area / 1e4


POP_PLAN, JOBS_PLAN = 320000, 304901
RES_PER_HOME = 2.5
HOMES_T = int(round(POP_PLAN / RES_PER_HOME, -1))
JOBS_T = int(round(JOBS_PLAN, -2))
SKIP = {"village_existing"}
NETHA = {z["id"]: net_ha(z) for z in ZONES}
JOBS_RES = {"residential_mid": 25.0, "residential_low": 5.0}
H_SCALED = {"residential_mid", "residential_low"}
J_SCALED = {"business", "mixed_centre"}
J_KEEP = {"gc_tower"}
H_KEEP = {"gc_tower"}


def _sum(key, pick):
    return sum(NETHA[z["id"]] * (z["rules"].get(key) or 0) for z in ZONES if pick(z))


def _counted(z):
    return z["use"] not in SKIP


FH_M = LU.floor_heights()
TALL_H = 28.0
_fl_done = {}
for z in ZONES:
    r = z["rules"]
    fl = r.get("floors")
    if not fl or z["use"] in SKIP or z["_base"] in H_KEEP:
        continue
    _fh = FH_M.get("business", 4.43) if z["use"] in ("business", "mixed_centre") else FH_M.get("res_mid", 3.6)
    lo = int(TALL_H // _fh)
    if fl[0] > lo:
        r["floors"] = [lo, fl[1]]
        _fl_done.setdefault(z["_base"], f"нижняя этажность {fl[0]} → {lo} ({lo} × {_fh:.2f} м ≤ 28 м)")
for _b, _m in sorted(_fl_done.items()):
    Z.SCHEME_CHANGES.append((_b, f"{_m}: пожарные разрывы 22 м между зданиями выше 28 м — из двух близких зданий выше 28 м "
                                 "поднимается одно, второе остаётся до 28 м"))
for z in ZONES:
    if z["use"] in JOBS_RES:
        z["rules"]["jobs_per_ha"] = max(float(z["rules"].get("jobs_per_ha") or 0), JOBS_RES[z["use"]])
# what the blocks of a zone hold: gen_buildings «зона не набирает плотность: не хватает места при потолке этажности» in the
# full run of 01.11 (the density of that run, got / need of its floor area). Most of these zones lie partly below the flood
# level 485,5 м (flood.kapchagay_levels_m + freeboard: land keeps that land as park), the logistics parks lose their land to
# truck yards and fire gaps between sheds, Green-Сити to the 22 m fire gaps of its towers. Their density is set to what
# their blocks hold (× 0.97), and the homes and jobs they cannot hold go to the other zones by the common factors.
HOLD = {"res_e": {"homes_per_ha": (50.1, 0.454)}, "res_lake": {"homes_per_ha": (50.1, 0.414)},
        "gc": {"homes_per_ha": (93.3, 0.943), "jobs_per_ha": (177.7, 0.891)},
        "ircc": {"jobs_per_ha": (138.8, 0.954)}, "ircc_p2": {"jobs_per_ha": (138.8, 0.205)},
        # logistics: the second run at 24.8 / 26.9 / 20.6 jobs per ha still held 89 / 90 / 94 % (sheds are not linear in the need)
        "log_1": {"jobs_per_ha": (24.8, 0.891)}, "log_2": {"jobs_per_ha": (26.9, 0.903)}, "log_3": {"jobs_per_ha": (20.6, 0.94)}}
HOLD_K = 0.97
# gen_buildings places ≈ 98.5 % of a zone's need in the zones that hold it (rounding of floors and footprints, run of 01.11):
# the densities aim that much over the plan, the targets stay the plan's
SHORT_K = 1.012
_held = set()
for z in ZONES:
    for key, (d_run, ratio) in HOLD.get(z["id"], {}).items():
        z["rules"][key] = round(d_run * ratio * HOLD_K, 1)
        _held.add((z["id"], key))
        Z.SCHEME_CHANGES.append((z["id"], f"{key} {d_run:g} → {z['rules'][key]:g}: кварталы зоны вмещают {ratio:.0%} площади "
                                          "по прогону gen_buildings (земля ниже паводка 485,5 м — парк, дворы складов, пожарные "
                                          "разрывы); остальное — в другие зоны"))


def _hv(z):
    return z["use"] in H_SCALED and z["_base"] not in H_KEEP and (z["id"], "homes_per_ha") not in _held


def _jv(z):
    return z["use"] in J_SCALED and z["_base"] not in J_KEEP and (z["id"], "jobs_per_ha") not in _held


h_fix = _sum("homes_per_ha", lambda z: _counted(z) and not _hv(z))
h_var = _sum("homes_per_ha", lambda z: _counted(z) and _hv(z))
j_fix = _sum("jobs_per_ha", lambda z: _counted(z) and not _jv(z))
j_var = _sum("jobs_per_ha", lambda z: _counted(z) and _jv(z))
FH = (HOMES_T * SHORT_K - h_fix) / h_var
FJ = (JOBS_T * SHORT_K - j_fix) / j_var
for z in ZONES:
    if z["use"] in SKIP:
        continue
    r = z["rules"]
    if _hv(z) and r.get("homes_per_ha"):
        r["homes_per_ha"] = round(r["homes_per_ha"] * FH, 1)
    if _jv(z) and r.get("jobs_per_ha"):
        r["jobs_per_ha"] = round(r["jobs_per_ha"] * FJ, 1)
    m2j = 100.0 if z["use"] in ("logistics", "industry") else (50.0 if z["use"] == "medical" else 90.0)
    need = ((r.get("homes_per_ha") or 0) * 75.0 + (r.get("jobs_per_ha") or 0) * m2j) / 1e4
    if r.get("far") is not None and need * 1.25 > r["far"]:
        r["far"] = round(need * 1.25 + 0.05, 1)
        fl = r.get("floors") or [3, 9]
        top = max(fl[1], int(math.ceil(r["far"] / 0.28)))
        if z["use"] in ("logistics", "industry"):
            top = fl[1]
        r["floors"] = [fl[0], min(top, 25 if z["_base"] not in H_KEEP else fl[1])]
        _fh = FH_M.get("business", 4.43) if z["use"] in ("business", "mixed_centre") else FH_M.get("res_mid", 3.6)
        r["height_cap_m"] = max(r.get("height_cap_m") or 0, round(r["floors"][1] * _fh + 4))
homes = sum(NETHA[z["id"]] * (z["rules"].get("homes_per_ha") or 0) for z in ZONES if _counted(z))
jobs = sum(NETHA[z["id"]] * (z["rules"].get("jobs_per_ha") or 0) for z in ZONES if _counted(z))
TARGETS = {"homes_2050": HOMES_T, "population_2050": int(round(HOMES_T * RES_PER_HOME, -2)),
           "jobs_2050": JOBS_T, "home_m2": 75.0,
           "plan_row": {"area_km2": 317, "population_2050": POP_PLAN, "jobs_2050": JOBS_PLAN},
           "source": "жители: строка плана Green — 320 тыс. в 2050 г. (= CityStats.DistrictTarget2050k[3] двойника, "
                     "UnityProject/Assets/Scripts/DigitalTwin/CityStats.cs:13; генплан ≈ 320 тыс.); сёла (существующие дома) "
                     "двойник и CityStats не считают — они сверх цели и в отчёте отдельно (homes_existing); "
                     "рабочие места: двойник 2050 г. в контуре Green без масштабирования — 304 901 (buildings.csv, базовый "
                     "сценарий: бизнес 220 367 + соцсфера 13 410 + промышленность 4 901 + отдых 66 223; решение владельца "
                     "31.10); по зонам — плотности схемы (жители / 2,5 = квартиры на га, места на га), умноженные на общий "
                     "коэффициент (квартиры ×%.3f в средне- и малоэтажных зонах, места ×%.3f в деловых и смешанных) так, "
                     "чтобы плотность × чистая площадь кварталов (без красных линий и полосы ЛРТ) дала цель с запасом 1,2 %% на потери "
                     "посадки зданий; зоны, кварталы которых больше не вмещают (ниже паводка, склады, пожарные разрывы), — по "
                     "прогону gen_buildings (HOLD в green_build.py)" % (FH, FJ)}
# parks: the park zones of the approved scheme (owner 31.10) on net land (without red lines); the map's measure is its park,
# square and boulevard greens (features.json), as green_numbers.py counts them
TARGETS["parks_ha"] = round(sum(NETHA[z["id"]] for z in ZONES if z["use"] == "park"), 1)
TARGETS["parks_source"] = ("парки схемы уровня 0 (зоны park, утверждены 31.10) на чистой земле без красных линий; на карте — зелень "
                           "park + square + boulevard (features.json); минимум СНиП РК 2008 — 10 + 6 м² на жителя")
LOG.append({"what": "цели и коэффициенты плотности", "FH": round(FH, 3), "FJ": round(FJ, 3), "homes": round(homes),
            "jobs": round(jobs)})

# ===================================================================================================== 6. objects
OBJ = []
v0obj = {o["registry_id"]: o for o in V0["objects"]}


def rname(rid):
    return REG[rid]["name_ru"] if rid in REG else v0obj.get(rid, {}).get("name_ru", rid)


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


def zone_at(pt):
    P = Point(pt)
    return next((z for z in ZONES if Polygon(z["polygon"]).buffer(0).contains(P)), None)


def free_at(pt, r=400.0):
    """The zone land round pt between the red lines (a registry plot fronts its street)."""
    z = zone_at(pt)
    if z is None:
        return None
    land = Polygon(z["polygon"]).buffer(0).difference(RED).difference(OWN_ROW).buffer(0)
    parts = [g for g in getattr(land, "geoms", [land]) if g.geom_type == "Polygon"]
    if not parts:
        return None
    return min(parts, key=lambda g: g.distance(Point(pt)))


MOVES = []        # «было → стало → почему»
# --- by source (existing, real)
REAL = {"settlement_kuygan", "settlement_arna", "settlement_konaev", "station_ile", "interchange_a3_km61_0", "road_a3",
        "rail_turksib", "rail_zhetygen_altynkol", "hv_lines_500", "hv_lines_220", "district_green", "airfield_zhetygen",
        "tlc_zhetygen", "settlement_zhetygen", "settlement_zarechnoe", "knauf"}
KTA = next(a for a in CITY["height_limits"]["airfields"] if a["id"] == "zhetygen_mil")
DROP = {"fok_zarechny": "ФОК Заречный — объект Growing (spec_issues: в green снять add)",
        "ps_zarechnoe": "ПС «Заречное» — объект Growing-восток (spec_issues: в green снять add)",
        "interchange_a3_km55_9": "развязка А-3 км 55,9 — в Growing (точка в 1,7 км от границы Green): строку ставит Growing"}
for o in V0["objects"]:
    rid = o["registry_id"]
    if rid in DROP:
        LOG.append({"what": "строка схемы снята (объект соседа)", "id": rid, "why": DROP[rid]})
        continue
    d = {"registry_id": rid, "name_ru": o["name_ru"], "action": o["action"], "from": o.get("from"), "to": o.get("to"),
         "yaw": o.get("yaw"), "accuracy": o.get("accuracy"), "why": o.get("why"),
         "basis": "по источнику" if rid in REAL else "по правилу"}
    for k in ("height_m", "approval", "outside_note"):
        if o.get(k) is not None:
            d[k] = o[k]
    if rid == "airfield_zhetygen":
        was = d["to"]
        d["to"] = d["from"] = [KTA["x"], KTA["z"]]
        d["why"] = ("действующий аэродром (ВПП 01/19 в контуре Green); точка — КТА zhetygen_mil из city.json#height_limits "
                    "(43°43′54″ N 77°07′14″ E, превышение 499 м); вокруг — зона без застройки; spec_issues: одна точка, владелец Green")
        MOVES.append(("airfield_zhetygen", was, d["to"], "одна точка на два района — КТА zhetygen_mil из city.json (spec_issues)"))
    if rid == "tlc_zhetygen":
        d["why"] = ("ТЛЦ «Жетыген» существует: контур OSM 31,7 га на 74 % в Green — ставит Green (keep, spec_issues), "
                    "Growing-E снимает свой move; модель ТЛЦ в Unity (landmark tlc) стоит по данным двойника")
        d.pop("outside_note", None)
    if rid == "settlement_zhetygen":
        was = d["to"]
        d["to"] = [7501, 8350]
        d["why"] = "Жетыген — в Growing-E; одна точка посёлка у growing_e (spec_issues), Green берёт её же"
        MOVES.append(("settlement_zhetygen", was, d["to"], "одна точка у Growing-E (spec_issues)"))
    if rid == "settlement_zarechnoe":
        was = d["to"]
        d["to"] = d["from"] = [1571, 12412]
        d["why"] = "Заречное — в Growing-E; одна точка у growing_e (spec_issues), Green берёт её же"
        MOVES.append(("settlement_zarechnoe", was, d["to"], "одна точка у Growing-E (spec_issues)"))
    if rid == "marina_kapchagay":
        d["kind"] = "landmark"
        d["lot_m2"] = 20000
        d["years"] = Y4(2034)
        d["basis"] = "по правилу"
        MOVES.append(("marina_kapchagay", o.get("from"), o.get("to"), "точка двойника в 718 м от воды на суше 481 м; марина — "
                      "в тихой бухте у дороги «На ASP Arena», у воды (схема 31.10)"))
    if rid == "green_tower_30":
        d["to"] = [round(TOWER_FP.centroid.x, 1), round(TOWER_FP.centroid.y, 1)]
        d["why"] = (o.get("why") or "") + f"; участок — своя зона gc_tower ({TOWER_FP.area / 1e4:.1f} га, до 110 м) на мысу курорта"
    if rid in ("settlement_kuygan", "settlement_arna"):
        d["why"] = (d.get("why") or "") + "; существующие дома и улицы села остаются (зоны village_existing, улицы OSM); новые улицы обходят село"
    if rid == "hv_lines_220":
        d["why"] = ("ВЛ 220 кВ (OSM 235a7bfa, 83f0e91a — по парковой полосе bg_west_park_3 западнее делового пояса; 8b790e95 — "
                    "по северо-западному резерву): через центры района не идут — остаются воздушными в своих коридорах "
                    "(охранная зона 25 м), решение владельца 31.10 (кабель только через центры)")
    if rid == "hv_lines_500":
        d["why"] = ("ВЛ 500 кВ (OSM 4fab2f0d) по западному парку и резерву, вдали от застройки: воздушная, охранная зона 30 м")
    if rid == "interchange_a3_km61_0":
        d["why"] = "существующая развязка А-3 км 61 (труба, OSM): как есть (узел ic_km61, keep_existing); к ней приходит Арнаутская"
    if rid == "road_a3":
        d["why"] = ("существующая А-3 через Green как есть; новая развязка «Green-Север» (ромб) у Озёрного проспекта и путепровод "
                    "Арнаутской-Запад без съездов")
    if rid == "station_ile":
        d["why"] = "существующая станция Іле (Турксиб); у неё центр Іле, Привокзальная улица"
    OBJ.append(d)
have = {o["registry_id"] for o in OBJ}
for rid, r in REG.items():
    mine = "green" in (r.get("district_area"), r.get("scheme_spec"), r.get("scheme_area")) or (
        r.get("scheme_conflict") or {}).get("owner") == "green"
    if mine and rid not in have:
        LOG.append({"what": "строка реестра без объекта", "id": rid})

# ===================================================================================================== 7. axes, joints, phases
AXIS_STREETS = {"prosp_green": ["s_prosp", "s_prosp_n"], "arnaut_w": ["s_arnaut_w", "s_arnaut_x"],
                "ozerny": ["s_ozerny_a3", "s_ozerny", "s_ozerny_e"], "ozerny_w": ["s_ozerny_w"], "terr": ["s_terr"], "dubler_a3w": ["s_dubler"],
                "heat_st": ["s_heat"], "privokzal": ["s_privokzal"], "yuzh": ["s_yuzh"], "blv_lake": ["s_blv_lake"],
                "east_link": ["s_east_link"], "bereg_e": ["s_bereg_e"], "log_st": ["s_log"]}
axes = copy.deepcopy(V0["axes"])
for a_ in axes:
    ids = AXIS_STREETS.get(a_["id"])
    if ids:
        parts = []
        for sid in ids:
            for s in N.STREETS:
                if s["id"] == sid or s["id"].startswith(sid + "_y"):
                    parts.append(LineString(s["line"]))
        U = unary_union(parts)
        U = U if U.geom_type == "LineString" else shapely.ops.linemerge(U)
        geoms = [U] if U.geom_type == "LineString" else list(U.geoms)
        a_["line"] = [P1(p) for g in geoms for p in g.simplify(2.0).coords]
        a_["why"] = (a_.get("why") or "") + "; линия оси — по улицам уровня 2 (" + ", ".join(ids) + ")"
    if a_["id"] == "lrt_south":
        a_["line"] = [P1(p) for p in substring(L_LRT, 0, chain(N.X_ARN_PROSP)).simplify(2.0).coords]
    if a_["id"] == "lrt_north":
        a_["line"] = [P1(p) for p in substring(L_LRT, chain(N.X_ARN_PROSP), L_LRT.length).simplify(2.0).coords]
    if a_["id"] == "track_st":
        a_["why"] = (a_.get("why") or "") + "; на уровне 2 не строится (см. scheme_changes track_st)"
    if a_["id"] == "east_n":
        a_["why"] = (a_.get("why") or "") + "; уровень 2: существующая Жетыгенская дорога OSM (17676108, 8edfe649, 94f53580) как есть"
GJ = [j for j in CITY["joints"]["items"] if "green" in (j.get("between") or [])]
JOINTS = [{"joint_id": j.get("id"), "x": j["x"], "z": j["z"], "kind": j.get("kind"), "between": j.get("between"),
           "line": j.get("line")} for j in GJ]
PHASES = copy.deepcopy(V0["phases"])

# ===================================================================================================== 8. spec
STREETS_OUT = []
for s in N.STREETS:
    d = {k: v for k, v in s.items() if not k.startswith("_")}
    q = [list(map(float, d["line"][0]))]
    for pt in d["line"][1:]:
        if math.dist(pt, q[-1]) > 0.05:
            q.append(list(map(float, pt)))
    d["line"] = q
    if len(q) < 2:
        LOG.append({"what": "улица из одной точки после разрезки: не пишется", "id": d["id"]})
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
replaced = sorted(set(N.RETIRED))

spec = {
    "district": "green", "version": 1, "level": 2,
    "made_by": "w51 tools/map/district/green_build.py (весь район Green)",
    "boundary": "city.json#districts/green",
    "attribution": C.ATTRIBUTION,
    "area": [P1(p) for p in list(GREEN.exterior.coords)[:-1]],
    "area_ha": round(GREEN.area / 1e4, 1),
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
    "views_convention": "dir_deg — азимут по часовой стрелке от севера (+Z): 0 = север, 90 = восток",
    "utilities": [],
    "corridors": None,
    "replaced_osm": replaced,
    "scheme_changes": [{"id": k, "why": v} for k, v in Z.SCHEME_CHANGES + N.SCHEME_CHANGES],
    "moved_objects": [{"id": a, "was": b, "now": c, "why": d} for a, b, c, d in MOVES],
    "checks": {},
}
# overhead power lines that stay (rules 4 and 19, land): OSM (Overture source_tags of level 0,
# w35/overture/infrastructure.parquet) tags 235a7bfa, 8b790e95, 83f0e91a voltage=220000 and 4fab2f0d voltage=500000
KV_OSM = {"235a7bfa": 220, "8b790e95": 220, "83f0e91a": 220, "4fab2f0d": 500}
KV_SRC = {220: "OSM voltage=220000 (Overture source_tags), реестр hv_lines_220 «ВЛ 220 кВ»",
          500: "OSM voltage=500000 (Overture source_tags), реестр hv_lines_500 «ВЛ 500 кВ»"}
KV_LINE = (110, MODEL + ": OSM power=line без voltage — принят 110 кВ (охранная зона 20 м)")
KV_MINOR = (10, MODEL + ": OSM power=minor_line без voltage — класс 1–20 кВ, охранная зона 10 м")
_tmp = {k: v for k, v in spec.items() if k != "corridors"}
CORR = []
for c in LU.corridors(copy.deepcopy(_tmp)):
    if not str(c.get("source", "")).startswith("osm:"):
        continue
    short = c["source"][4:12]
    if short in KV_OSM:
        kv, basis = KV_OSM[short], KV_SRC[KV_OSM[short]]
    else:
        kv, basis = KV_MINOR if c.get("osm_class") == "minor_line" else KV_LINE
    CORR.append({**c, "kv": kv, "kv_basis": basis})
spec["corridors"] = CORR
LOG.append({"what": "ВЛ в коридорах spec с напряжением", "n": len(CORR), "kv": sorted({(c["id"], c["kv"]) for c in CORR})})
LOG.append({"what": "время шагов сборки, с", **TIMES})

if __name__ == "__main__":
    import green_check as CHK
    res = CHK.run(spec, verbose=False)
    spec["checks"] = res
    spec["checks"]["build_log"] = LOG[:400]
    txt = json.dumps(spec, ensure_ascii=False, indent=1)
    with open(SPEC_OUT + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write(txt + "\n")
    os.replace(SPEC_OUT + ".tmp", SPEC_OUT)
    from collections import Counter
    print(f"wrote {SPEC_OUT}: {len(txt) // 1024} KB; streets {len(STREETS_OUT)}, nodes {len(NODES_OUT)}, zones {len(ZONES_OUT)}, "
          f"objects {len(OBJ)}; {time.time() - T0:.1f} s; steps {TIMES}")
    print("targets", {k: TARGETS[k] for k in ("homes_2050", "population_2050", "jobs_2050")}, "FH %.3f FJ %.3f" % (FH, FJ))
    print("log", Counter(x["what"] for x in LOG))
    if "--no-check" not in sys.argv:
        ok = CHK.main([SPEC_OUT])
        sys.exit(0 if ok else 1)
