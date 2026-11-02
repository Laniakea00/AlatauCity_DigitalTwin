#!/usr/bin/env python3
"""Gate · level 2 · builder of tools/map/spec/gate.json v1 (w47): the whole district.

    python3 -I tools/map/district/gate_build.py [--no-check] [--out SPEC.json]

Builds on the approved level-0 scheme (district/gate_v0.json) and the level-1 trial quarter (gate_trial_build.py, taken
over inside the trial area as it is, changed only where it joins the rest). Network: gate_net.py (trial streets, existing
roads, the frame of the scheme axes, local streets of every new quarter); zones: gate_zones.py. Here: LRT v1 with its
stations and depot, objects (registry rows: by source / by rule), keep, views, utilities (220 kV cable), targets, phases,
axes, joints, replaced roads, and the self-check (gate_check.py).
Every coordinate not from a source is the cartographer's design (label «модель qTwin»). Unity frame: X east, Z north.
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

import gate_common as C  # noqa: E402
import gate_trial_build as T  # noqa: E402
import gate_net as N  # noqa: E402
import gate_zones as Z  # noqa: E402
import land_util as LU  # noqa: E402

SPEC_OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(C.SPEC_DIR, "gate.json")
MODEL = "модель qTwin"
Y4 = T.Y4
fillet = T.fillet
CITY = T.CITY
REG = T.REG
V0 = C.spec_v0()
GATE = T.GATE_POLY
TRIAL = T.AREA
LOG = []


def P1(p):
    return [round(float(p[0]), 1), round(float(p[1]), 1)]


def poly_pts(g):
    return T.poly_pts(g)


# ===================================================================================================== 1. LRT line (frame)
J001 = (-2571.1, -15712.2)                    # city.json joint J001: LRT Gate – Golden
# s_east_y (Восточная улица, ЛРТ в разделительной полосе) runs on to Проспект Gate City; the LRT leaves it there for the depot
EY = N.SID["s_east_y"]
a, b = np.array(EY["line"][-2], float), np.array(EY["line"][-1], float)
dv = (b - a) / np.linalg.norm(b - a)
GC_L = LineString(N.SID["s_gatecity"]["line"])
hit = LineString([tuple(b), tuple(b + dv * 400.0)]).intersection(GC_L)
P_EY_GC = (hit.x, hit.y) if hit.geom_type == "Point" else (hit.geoms[0].x, hit.geoms[0].y)
EY["line"].append(P1(P_EY_GC))
EY["why"] += "; кончается на Проспекте Gate City у админцентра (дальше ЛРТ идёт к депо по своей полосе)"
LRT_SOUTH = fillet([P_EY_GC, (-4060.0, -23480.0), (-4170.0, -23720.0), (-4280.0, -23960.0), (-4380.0, -24180.0),
                    (-4600.0, -24330.0)], 300)
LRT_NORTH = [J001, (-2720.0, -16200.0)]
LRT_PTS = (LRT_NORTH + [tuple(p) for p in N.EAST_N[::-1]] + [tuple(p) for p in T.EAST[1:]] + [tuple(p) for p in N.EAST_S[1:]]
           + [tuple(p) for p in EY["line"][len(N.EAST_S):]] + [tuple(p) for p in LRT_SOUTH[1:]])
q = [LRT_PTS[0]]
for p in LRT_PTS[1:]:
    if math.dist(p, q[-1]) > 0.5:
        q.append(p)
LRT_PTS = q
L_LRT = LineString(LRT_PTS)
DEPOT = Polygon([(-4600.0, -24250.0), (-4600.0, -24470.0), (-4880.0, -24470.0), (-4880.0, -24250.0)])
LRT_W = float(LU.Norms().v("lrt.corridor_width_m", "double_track"))


def chain(pt):
    return L_LRT.project(Point(pt))


def at_chain(s):
    p = L_LRT.interpolate(s)
    return (p.x, p.y)


# viaduct: from the trial's rise at z −19720 over the A-3 × БАКАД interchange field and Ынтымақ; down in the median of
# s_east_y and on the ground 45 m before the existing street 441b50b7 (crossed at grade); no local street crosses the
# ramps (120 m: 6.5 m of clearance + deck at ≤ 6 %)
_x441 = L_LRT.intersection(N.osm("441b50b7")[0])
_c441 = min(chain((q.x, q.y)) for q in getattr(_x441, "geoms", [_x441]))
SEC_ELEV = [(chain((T.EAST_X, -19720.0)), _c441 - 45.0)]
RAMP_M = 120.0
LRT_RAMPS = [substring(L_LRT, a, a + RAMP_M).buffer(15.0, cap_style=2) for a, _ in SEC_ELEV] + \
            [substring(L_LRT, b - RAMP_M, b).buffer(15.0, cap_style=2) for _, b in SEC_ELEV]

# own right of way (not in a street median): J001 → Набережная, and Проспект Gate City → депо
S_EMB = chain(N.EAST_N[-1])
S_GC = chain(P_EY_GC)
OWN_ROW = unary_union([substring(L_LRT, 0, S_EMB).buffer(LRT_W / 2 + 2, cap_style=2),
                       substring(L_LRT, S_GC, L_LRT.length).buffer(LRT_W / 2 + 2, cap_style=2)])
# stations: trial ones as they are; the others by chainage, then centred between the cross streets (rule 25)
ST_TRIAL = {"st_park": (T.EAST_X, -18710.0), "st_iconic": (T.EAST_X, -19578.0),
            "st_tpu": (round(T.on_line(T.EAST, z=-20462.0)[0], 1), -20462.0)}
ST_PLAN = [("st_besterek", "Бестерек", N.on(N.EAST_N, z=-16700.0), "ground"),
           ("st_esentai", "Есентай", N.on(N.EAST_N, z=-17620.0), "ground"),
           ("st_park", "Центральный парк", ST_TRIAL["st_park"], "ground"),
           ("st_iconic", "Iconic", ST_TRIAL["st_iconic"], "ground"),
           ("st_tpu", "ТПУ Gate (А-3 × БАКАД)", ST_TRIAL["st_tpu"], "elevated"),
           ("st_yntymak", "Ынтымақ", None, "elevated"),
           ("st_gatecity", "Gate City", None, "ground"),
           ("st_admin", "Административный центр", None, "ground"),
           ("st_south", "Gate City-Юг (депо)", None, "ground")]
s_tpu = chain(ST_TRIAL["st_tpu"])
S_PLAN = {"st_yntymak": s_tpu + 1150.0, "st_gatecity": s_tpu + 2300.0, "st_admin": s_tpu + 3250.0}
S_PLAN["st_south"] = min(S_PLAN["st_admin"] + 1050.0, L_LRT.length - 120.0)
ST_XY = {}
for sid, nm, xy, kind in ST_PLAN:
    ST_XY[sid] = xy if xy is not None else at_chain(S_PLAN[sid])

# ===================================================================================================== 2. existing interchanges
OSM = N.OSM


def oid_full(short):
    return N.SH[short]


def ic_existing(nid, x, z, typ, streets, ramps, rid, why):
    N.node(nid, x, z, typ, streets, keep_existing=True, registry_id=rid, osm_ids=[oid_full(r) for r in ramps if r in N.SH],
           why_ru=why)


def k_of(short):
    return N.KEEP_IDS.get(oid_full(short)) if short in N.SH else None


ic_existing("ic_a3_a19", -2052.5, -18338.8, "trumpet", [k_of("3cec7dd6"), k_of("164f7618")],
            ["be1950a1", "7c490ced", "b6783511", "8cd1a33b", "fda944b2"], "interchange_a3_yntymak_zhanadaur",
            "существующая развязка А-3 × А-19 (OSM), съезды как в данных; новых съездов в Gate не добавляется")
ic_existing("ic_a3_gatecity", -3302.0, -23824.0, "diamond", [k_of("1424848a"), "s_gatecity"],
            ["fd499b4d", "86370d28"], "interchange_a3_km18_5",
            "существующий съезд А-3 у ЖК Gate City (OSM, реестр interchange_a3_km18_5 в 74 м); Проспект Gate City приходит к "
            "его концевому узлу; восточные съезды (c1053ec1, 0229484f) за границей города сняты (retire_existing)")
# Проспект Gate City ends at the ramp terminal of the existing interchange (OSM node where ramp fd499b4d meets the ЖК streets)
GCs = N.SID["s_gatecity"]
term = OSM[oid_full("fd499b4d")][0]
t0 = term.coords[0] if Point(term.coords[0]).distance(Point(GCs["line"][-1])) < Point(term.coords[-1]).distance(Point(GCs["line"][-1])) else term.coords[-1]
GCs["line"][-1] = P1(t0)
# ===================================================================================================== 3. local streets
STATION_PTS = [ST_XY[k] for k in ("st_besterek", "st_esentai", "st_yntymak", "st_gatecity", "st_admin", "st_south")]
t = time.time()
N.LRT_RAMPS[:] = LRT_RAMPS
made = N.generate_local(stations=STATION_PTS, barriers=OWN_ROW.union(DEPOT.buffer(10)), lrt_line=L_LRT)
LOG.append({"what": "местные улицы сгенерированы", "n": made, "s": round(time.time() - t, 1)})


# free ends of frame and trial streets: on along their direction to the first street (≤ 400 m), never through houses
def ext_ok(P):
    return GATE.exterior.distance(P) < 3.0 or any(math.dist((P.x, P.y), (n["x"], n["z"])) < 1.0 for n in N.NODES.values()
                                                  if n["type"] == "joint")


def extend_free_ends(layers=("frame", "trial"), reach=400.0):
    out = []
    lines = N.all_lines()
    for s in N.STREETS:
        if s["_layer"] not in layers:
            continue
        oth = [(sid, L, cls) for sid, L, cls, _ in lines if sid != s["id"]]
        ot = shapely.STRtree([L for _, L, _ in oth])
        for end in (0, -1):
            pt = s["line"][end]
            if N._attached(pt, oth, ot, ext_ok):
                continue
            # an end on a declared node (e.g. the trial's n_set: a right-in onto the west carriageway, clear of the LRT) is joined
            if any(s["id"] in n.get("streets", []) and math.dist(pt, (n["x"], n["z"])) < 1.0 for n in N.NODES.values()):
                continue
            prev = s["line"][1] if end == 0 else s["line"][-2]
            d = np.array(pt, float) - np.array(prev, float)
            d /= np.linalg.norm(d)
            hosts = [L for sid, L, cls in oth if cls not in N.NO_HOST]
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
            s["struct"] += [{"from": P1(a_), "to": P1(b_), "kind": k} for a_, b_, k in N.water_bridges([tuple(pt), hp])]
            out.append({"what": "улица каркаса продолжена до ближайшей улицы", "id": s["id"], "to": P1(hp),
                        "m": round(seg.length, 1)})
    return out


LOG += extend_free_ends()
# central park (p_central, 21.6 ha): the main east–west alley across s_park_walk, from the street on the west edge to the
# one on the east edge, 50 m north of the school plot (pedestrian_street; the paths, entrances and playgrounds by rule)
_pk = next(z for z in Z.ZPLAN if z["id"] == "p_central")["poly"]
_lines = [LineString(x["line"]) for x in N.STREETS if x["id"] != "s_park_walk" and x["class"] not in ("expressway", "ramp")]
_c = (-3500.0, -18650.0)
_w = N._ray_hit(_c, (-1.0, 0.0), _lines, 700.0)
_e = N._ray_hit(_c, (1.0, 0.0), _lines, 700.0)
if _w and _e:
    N.street("s_park_alley", "pedestrian_street", [_w, _c, _e], "главная аллея Центрального парка", 2033, layer="frame",
             why=MODEL + ": главная аллея парка с запада на восток через s_park_walk, в 50 м севернее участка школы; год — "
                         "как у s_park_walk и улиц на краях парка")
    N.change("s_park_alley", "новая главная аллея Центрального парка (пешеходная улица) с запада на восток")
    LOG.append({"what": "главная аллея Центрального парка", "m": round(LineString([_w, _c, _e]).length),
                "in_park_m": round(LineString([_w, _c, _e]).intersection(_pk).length)})
TRIM_LOG = []
N.trim_free_ends(ext_ok, log=TRIM_LOG)
LOG += TRIM_LOG
N.snap_ends(tol=N.SNAP_J, log=LOG)
N.house_lanes(log=LOG)
N.link_dead_ends(log=LOG)


def serve_pieces(log=None, min_m2=2000.0, reach=150.0, inside=15.0):
    """Built zone land that the streets and the LRT's own corridor cut off from every street (rule 12: a block with
    buildings needs an entry): a local side street from the nearest street into the piece (≤ reach, ending `inside` m in),
    never across an expressway, a ramp, the LRT corridor, water or a house. Returns the streets made."""
    lines = [(x["id"], LineString(x["line"]), x["class"]) for x in N.STREETS]
    lines += [("osm:" + oid, q, cls) for oid, q, cls in N.OSM_HOST]
    reds = unary_union([L.buffer(N.red_w(c) / 2.0) for _, L, c in lines if c not in ("expressway", "ramp")]
                       + [L.buffer(N.EXP_HALF) for _, L, c in lines if c in ("expressway", "ramp")])
    acc = [(sid, L, c) for sid, L, c in lines if c not in ("expressway", "ramp", "pedestrian_street", "bike_path")]
    at = shapely.STRtree([L for _, L, _ in acc])
    barrier = unary_union([L for _, L, c in lines if c in ("expressway", "ramp")] + [OWN_ROW])
    made = []
    for z in Z.ZPLAN:
        if z["use"] not in Z.DEV_USES or (z.get("rules") or {}).get("lot_split") == "none":
            continue
        land = z["poly"].intersection(GATE).difference(reds).difference(OWN_ROW).buffer(0)
        for q in getattr(land, "geoms", [land]):
            if q.geom_type != "Polygon" or q.area < min_m2:
                continue
            if any(acc[i][1].buffer(N.red_w(acc[i][2]) / 2.0 + 2.5).intersects(q) for i in at.query(q.buffer(N.EXP_HALF))):
                continue                                  # a street already fronts it
            best = None
            for i in at.query(q.buffer(reach)):
                sid, L, c = acc[i]
                a, b = shapely.ops.nearest_points(L, q)
                d = a.distance(b)
                if d > reach - inside or (best is not None and d >= best[0]):
                    continue
                u = np.array([b.x - a.x, b.y - a.y]) / max(d, 1e-6)
                end = Point(b.x + u[0] * inside, b.y + u[1] * inside)
                sp = LineString([(a.x, a.y), (end.x, end.y)])
                if sp.crosses(barrier) or sp.intersects(OWN_ROW) or sp.intersects(N.WATER_POLY) or not GATE.contains(sp) \
                        or N.houses_hit(sp.buffer(N.red_w("local") / 2.0)) or not q.contains(end):
                    continue
                best = (d, sid, sp)
            rec = {"zone": z["id"], "ha": round(q.area / 1e4, 2), "at": [round(v) for v in q.representative_point().coords[0]]}
            if best is None:
                if log is not None:
                    log.append({"what": "земля зоны без улицы: подъезда нет (ждёт решения)", **rec})
                continue
            sid_new = f"v_serve_{len(made) + 1:02d}"
            N.street(sid_new, "local", best[2].coords, "въезд в квартал", int(z["years"][0]), layer="lane",
                     why=MODEL + f": земля зоны {z['id']} ({q.area / 1e4:.1f} га) отрезана от улиц линией ЛРТ и границами зон — "
                                 f"въезд {best[2].length:.0f} м от {best[1]} (правило 12: у квартала со зданиями есть въезд)")
            made.append(sid_new)
            if log is not None:
                log.append({"what": "въезд в отрезанную землю зоны", "id": sid_new, "from": best[1], "m": round(best[2].length), **rec})
    return made


serve_pieces(log=LOG)
YEAR_MOVES = N.phase_years(N.TRIAL, log=LOG)

# no driveway classes in the spec (drives come only from land_driveways): the barn access is a short local street
for s in N.STREETS:
    if s["class"].startswith("driveway"):
        s["class"] = "local"
        s["why"] = (s.get("why") or "") + "; в gate.json — местная улица (проезды даёт только land_driveways)"
        N.change(s["id"], "класс driveway_* → local: в gate.json нет классов driveway_* (проезды строит land_driveways)")

# ===================================================================================================== 4. LRT v1
# cross streets of the line (at grade where the line is on the ground), then each station centred in its gap
ROADS_X = []
for s in N.STREETS:
    if s["class"] in ("expressway", "ramp"):
        continue
    x = LineString(s["line"]).intersection(L_LRT)
    for g in getattr(x, "geoms", [x]):
        if g.geom_type == "Point":
            ROADS_X.append((chain((g.x, g.y)), s["id"]))
ROADS_X.sort()
PLAT = 33.0


def place_station(sid, xy):
    s0 = chain(xy)
    if sid in ST_TRIAL:
        return xy, s0
    before = [c for c in ROADS_X if c[0] < s0 - 1]
    after = [c for c in ROADS_X if c[0] > s0 + 1]
    lo = before[-1][0] if before else 0.0
    hi = after[0][0] if after else L_LRT.length
    if hi - lo < PLAT + 20:
        LOG.append({"what": "станция ЛРТ: промежуток между улицами мал", "id": sid, "m": round(hi - lo, 1)})
    sm = 0.5 * (lo + hi) if (hi - lo) < 200 or abs(s0 - 0.5 * (lo + hi)) > (hi - lo) / 2 - PLAT else s0
    return at_chain(sm), sm


STATIONS = []
for sid, nm, xy, kind in ST_PLAN:
    p, sm = place_station(sid, ST_XY[sid])
    before = [c for c in ROADS_X if c[0] < sm]
    after = [c for c in ROADS_X if c[0] > sm]
    elev = any(a_ <= sm <= b_ for a_, b_ in SEC_ELEV)
    STATIONS.append({"id": sid, "name_ru": nm, "x": round(p[0], 1), "z": round(p[1], 1),
                     "between": [before[-1][1] if before else None, after[0][1] if after else None],
                     "kind": "elevated" if elev else "ground", "_s": sm})
STATIONS.sort(key=lambda s_: s_["_s"])
SECTIONS = []
cuts = [0.0]
for a_, b_ in SEC_ELEV:
    cuts += [a_, b_]
cuts.append(L_LRT.length)
for k in range(len(cuts) - 1):
    a_, b_ = cuts[k], cuts[k + 1]
    if b_ - a_ < 1:
        continue
    SECTIONS.append({"from": P1(at_chain(a_)), "to": P1(at_chain(b_)), "kind": "elevated" if k % 2 == 1 else "ground"})
LRT = {
    "lines": [{
        "id": "lrt_gate_golden", "name_ru": "ЛРТ Gate – Golden (участок Gate)",
        "line": [P1(p) for p in LRT_PTS],
        "sections": SECTIONS,
        "stations": [{k: v for k, v in s_.items() if not k.startswith("_")} for s_ in STATIONS],
        "ends": [{"kind": "joint", "id": "J001", "to": "golden"}, {"kind": "depot", "id": "depot_gate_south"}],
        "joints": [{"joint_id": "J001", "x": J001[0], "z": J001[1], "to": "golden"}],
        "years": Y4(2031),
        "why": "ось схемы ax_lrt: от стыка J001 с Golden через Бестерек и Есентай в разделительной полосе Восточной улицы, "
               "через пробную зону (как на уровне 1: на земле до z −19720, эстакада над БАКАД и ТПУ), вдоль Ынтымака эстакадой "
               "до z −21900, по Восточной улице к Gate City и админцентру, дальше по своей полосе к депо; станции между "
               "поперечными улицами, шаг 0,8–1,5 км"}],
    "depots": [{"id": "depot_gate_south", "polygon": poly_pts(DEPOT), "years": Y4(2031),
                "why": MODEL + ": депо ЛРТ в зоне схемы u_depot у южного конца линии"}]}

# ===================================================================================================== 5. zones
ZONES = []
ZIDS = set()
taken = Polygon()


def zone_out(z, poly, rules):
    global taken
    parts = T.simple_parts(poly.buffer(0).intersection(GATE).difference(taken).buffer(0), 500.0)
    for k, q in enumerate(parts):
        taken = taken.union(q)
        zid = z["id"] if k == 0 else f"{z['id']}_p{k + 1}"
        if zid in ZIDS:
            zid = zid + "_s"                        # a scheme zone that has a namesake in the trial area (p_central …)
        ZIDS.add(zid)
        d = {"id": zid, "use": z["use"], "name_ru": z["name_ru"], "polygon": poly_pts(q),
             "years": z["years"], "rules": copy.deepcopy(rules), "why": z["why"], "area_ha": round(q.area / 1e4, 2), "_src": z["src"],
             "_base": z["id"]}
        if z.get("density"):
            d["density"] = z["density"]
        for k_ in ("facility", "facilities"):            # CONTRACT §8 (w45): the twin's facilities this utility zone hosts
            if z.get(k_) and k == 0:
                d[k_] = copy.deepcopy(z[k_])
        ZONES.append(d)


# TPU plots (bus station, P+R, zones up to the red lines), kg_gate_4's block, the plants' utility lots, the City floors and densities
# under the 22 m fire gaps, l_griffin's SZZ class and multi-storey car parks: in gate_trial_build.py since round 3 (the
# trial fixture is Gate v1.1 in the trial area); the trial's zones and objects come here as they are

# sanitary gaps (rule 15): every industrial and logistics zone states its SZZ class; no housing within the class width w,
# nor within w × zone_factor in the downwind sector (szz.wind_sector_deg). The gap is planted (park zone) on the scheme's
# side; a trial zone is never cut.
_LN = LU.Norms()
SZZ_W = {k: float(v["min"]) for k, v in _LN.v("szz.class_width_m").items()}
_WS = _LN.v("szz.wind_sector_deg")
SZZ_F, SZZ_SECTOR = float(_WS["zone_factor"]), tuple(_WS["default_sector"])
SZZ_CLASS = {
    "i_pepsico": ("IV", MODEL + ": пищевое производство (PepsiCo, 16–21 тыс. т/год); ближайшие примеры szz.class_examples — "
                        "класс IV (безалкогольные напитки, пивоварни)"),
}
SZZ_DEFAULT = ("V", MODEL + ": склады и логистика готовых товаров без выбросов — наименьший класс szz.class_width_m "
                           "(в szz.class_examples складов нет)")
for z in Z.ZPLAN:
    if z["use"] in ("industry", "logistics"):
        if z["src"] != "v0" and z["rules"].get("szz_class"):
            continue                                  # the trial states it (l_griffin: V)
        cls_, why_ = SZZ_CLASS.get(z["id"], SZZ_DEFAULT)
        z["rules"]["szz_class"] = cls_
        z["why"] = z["why"] + f"; СЗЗ класса {cls_} ({SZZ_W[cls_]:.0f} м): {why_}"
        if z["src"] != "v0":
            Z.CHANGES.append((z["id"], f"класс СЗЗ задан: {cls_} ({SZZ_W[cls_]:.0f} м) — {why_}"))


def _wedge(poly, a0, a1, r, step=20.0):
    """Points within r of `poly` in the bearing range a0..a1 (azimuth from +z toward +x, as in rule 15): a union of sectors
    from points every `step` m on the boundary and from the centroid."""
    b = poly.exterior
    pts = [b.interpolate(t) for t in np.arange(0.0, b.length, step)] + [poly.centroid]
    angs = np.radians(np.linspace(a0, a1 if a1 >= a0 else a1 + 360.0, 13))
    out = []
    for p in pts:
        out.append(Polygon([(p.x, p.y)] + [(p.x + r * math.sin(t), p.y + r * math.cos(t)) for t in angs]))
    return unary_union(out)


RES_USES = ("residential_high", "residential_mid", "residential_low", "mixed_centre", "waterfront")
SZZ_LOG = []
for I in [z for z in Z.ZPLAN if z["use"] in ("industry", "logistics")
          and (z["rules"].get("lot_split") != "none" or z["id"] in Z.PLANT_AS_IS)]:
    w = SZZ_W[I["rules"]["szz_class"]]
    reach = w * SZZ_F
    for R in [z for z in Z.ZPLAN if z["use"] in RES_USES]:
        if I["poly"].distance(R["poly"]) >= reach:
            continue
        if R["src"] == "v0":
            strip = R["poly"].intersection(I["poly"].buffer(w).union(_wedge(I["poly"], *SZZ_SECTOR, reach)))
        elif I["src"] == "v0":
            back = ((SZZ_SECTOR[0] + 180.0) % 360.0, (SZZ_SECTOR[1] + 180.0) % 360.0)
            strip = I["poly"].intersection(R["poly"].buffer(w).union(_wedge(R["poly"], *back, reach)))
        else:
            continue
        if strip.area < 500.0:
            continue
        cls_ = I["rules"]["szz_class"]
        zone_out({"id": f"g_szz_{I['id']}_{R['id']}", "use": "park", "src": "v0", "years": R["years"],
                  "name_ru": f"Санитарный разрыв {I['name_ru']} — {R['name_ru']} (озеленение)",
                  "why": f"СЗЗ класса {cls_}: {w:.0f} м, в подветренном секторе {SZZ_SECTOR[0]:.0f}–{SZZ_SECTOR[1]:.0f}° — "
                         f"{reach:.0f} м (правило 15): жильё не ближе к производству"},
                 strip, {"lot_split": "none"})
        SZZ_LOG.append((I["id"], R["id"], cls_, round(strip.area / 1e4, 2)))
        Z.SCHEME_CHANGES.append((f"g_szz_{I['id']}_{R['id']}", f"санитарный разрыв класса {cls_} ({w:.0f} м, по ветру {reach:.0f} м; "
                                 f"{strip.area / 1e4:.2f} га) из зоны {R['id'] if R['src'] == 'v0' else I['id']}: озеленение"))
# existing houses (villages next to the zone and houses standing inside it) keep the same gap: it is carved from the
# production zone of the scheme, the houses stay as they are
for I in [z for z in Z.ZPLAN if z["use"] in ("industry", "logistics") and z["src"] == "v0" and z["rules"].get("lot_split") != "none"]:
    w = SZZ_W[I["rules"]["szz_class"]]
    reach = w * SZZ_F
    back = ((SZZ_SECTOR[0] + 180.0) % 360.0, (SZZ_SECTOR[1] + 180.0) % 360.0)
    vil = [R["poly"] for R in Z.ZPLAN if R["use"] == "village_existing" and I["poly"].distance(R["poly"]) < reach]
    hs = [h for h in N.HOUSES if I["poly"].buffer(reach).intersects(h) and not any(v.contains(h.centroid) for v in vil)]
    if not vil and not hs:
        continue
    near = unary_union(vil + hs)
    wedges = [_wedge(q, *back, reach) for q in vil] + [_wedge(h.convex_hull.buffer(0.5), *back, reach, step=10.0) for h in hs]
    strip = I["poly"].intersection(near.buffer(w).union(unary_union(wedges))).buffer(0)
    if strip.area < 500.0:
        continue
    cls_ = I["rules"]["szz_class"]
    zone_out({"id": f"g_szz_{I['id']}_houses", "use": "park", "src": "v0", "years": I["years"],
              "name_ru": f"Санитарный разрыв {I['name_ru']} — существующие дома (озеленение)",
              "why": f"СЗЗ класса {cls_}: {w:.0f} м, в подветренном секторе {SZZ_SECTOR[0]:.0f}–{SZZ_SECTOR[1]:.0f}° — {reach:.0f} м "
                     "(правило 15) от существующих домов (сёла рядом и дома внутри зоны остаются)"},
             strip, {"lot_split": "none"})
    SZZ_LOG.append((I["id"], "existing houses", cls_, round(strip.area / 1e4, 2)))
    Z.SCHEME_CHANGES.append((f"g_szz_{I['id']}_houses", f"санитарный разрыв класса {cls_} ({w:.0f} м, по ветру {reach:.0f} м; "
                             f"{strip.area / 1e4:.2f} га) из зоны {I['id']} у существующих домов ({len(hs)} внутри и рядом, "
                             f"сёл рядом {len(vil)}): озеленение"))
LOG.append({"what": "санитарные разрывы (озеленение) между производством и жильём", "pairs": SZZ_LOG})
# island quarters that no street can reach (gate_net.UNSERVED): reserve, not buildable
for k, P in enumerate(N.UNSERVED):
    q = P.buffer(N.D_IN + 2.0)
    zone_out({"id": f"x_unserved_{k + 1}", "use": "reserve", "src": "v0", "years": [2050, 2050],
              "name_ru": "Резерв: участок без подъезда (между водой, трассой и сёлами)",
              "why": "ни одна улица не доходит до участка без пересечения трассы или домов: резерв до подъезда"},
             q, {"lot_split": "none"})
    LOG.append({"what": "участок без подъезда переведён в резерв", "ha": round(q.area / 1e4, 1), "at": [round(v) for v in P.centroid.coords[0]]})
    Z.SCHEME_CHANGES.append((f"x_unserved_{k + 1}", f"{q.area / 1e4:.1f} га у ({P.centroid.x:.0f}, {P.centroid.y:.0f}) — резерв: "
                             "до участка не дойти улицей без пересечения трассы или домов"))

# utility lot of the twin's ПС 110/10 кВ «Gate-2» and Котельная «Gate-2» (StreamingAssets/twin/networks.json ps_gate_2, hb_gate_2:
# synthetic, at (−4764, −23084) in the scheme's housing r_mid_s_10, first stage 2034): 16 000 m² of that zone's land round the
# twin's point, up to the red lines of the local streets there (tester r2 items 59, 60: the merge put them in red lines and on an
# office lot; w45 places them on these lots). Модель qTwin: no plot or sanitary-gap norm for plants in norms.json.
EN2_AT, EN2_M2 = (-4764.0, -23084.0), 16000.0
_zr = next(z for z in Z.ZPLAN if z["id"] == "r_mid_s_10")
_red2 = unary_union([LineString(x["line"]).buffer(N.red_w(x["class"], x.get("profile")) / 2.0 + 0.05, cap_style=2) for x in N.STREETS
                     if len(x["line"]) > 1 and LineString(x["line"]).distance(Point(EN2_AT)) < 400.0])
_l2 = _zr["poly"].difference(_red2).buffer(0)
_l2 = min(getattr(_l2, "geoms", [_l2]), key=lambda q: (q.distance(Point(EN2_AT)) > 1.0, -q.area))
_lo, _hi = 0.0, 400.0
for _ in range(60):
    _mid = (_lo + _hi) / 2.0
    if _l2.intersection(box(EN2_AT[0] - _mid, EN2_AT[1] - _mid, EN2_AT[0] + _mid, EN2_AT[1] + _mid)).area > EN2_M2:
        _hi = _mid
    else:
        _lo = _mid
EN2 = _l2.intersection(box(EN2_AT[0] - _hi, EN2_AT[1] - _hi, EN2_AT[0] + _hi, EN2_AT[1] + _hi)).buffer(0)
EN2 = max(getattr(EN2, "geoms", [EN2]), key=lambda q: q.area).simplify(0.3)
_zr["poly"] = _zr["poly"].difference(EN2).buffer(0)
Z.ZPLAN.append({"id": "u_energy_gate_2", "use": "utility", "name_ru": "ПС 110/10 кВ и котельная «Gate-2»", "poly": EN2,
                "years": [2034, 2034], "rules": {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0}, "density": None, "src": "v0",
                "facilities": list(T.ENERGY_FAC),
                "why": MODEL + ": участок ПС 110/10 кВ «Gate-2» и котельной «Gate-2» двойника (networks.json ps_gate_2, hb_gate_2, первая "
                               "очередь 2034) у точки двойника (−4764, −23084), до красных линий местных улиц"})
Z.SCHEME_CHANGES.append(("u_energy_gate_2", "участок %s м² вынут из жилой зоны r_mid_s_10 у точки двойника (−4764, −23084) под ПС 110/10 кВ "
                                            "и котельную «Gate-2» (замечания тестера r2, п. 59–60)" % f"{EN2.area:,.0f}".replace(",", " ")))
for z in Z.ZPLAN:
    if z["id"] == "u_motorways_trial":
        continue
    zone_out(z, z["poly"], z["rules"])
for z in Z.ZPLAN:
    if z["id"] == "u_motorways_trial":
        zone_out(z, z["poly"], z["rules"])
# the depot takes its plot out of u_depot (same use: utility)
# no land outside the zones: every leftover sliver joins the zone it shares the longest border with
_gap = GATE.difference(unary_union([Polygon(z["polygon"]).buffer(0) for z in ZONES]))
_ZT = shapely.STRtree([Polygon(z["polygon"]).buffer(0) for z in ZONES])
for g in [q for q in getattr(_gap, "geoms", [_gap]) if q.geom_type == "Polygon" and q.area > 1.0]:
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
# zones exactly disjoint after the rounding (earlier zones keep their land; slivers overlapped by up to 12 m² and became
# overlapping lots, rule 1)
LOG.append({"what": "зоны без перекрытий после округления", "n": T.disjoint(ZONES)})

# ===================================================================================================== 6. targets and densities
LN = LU.Norms()
RW = {}


def red_w(cls, profile=None):
    return N.red_w(cls, profile)


RED = unary_union([LineString(s["line"]).buffer(red_w(s["class"], s.get("profile")) / 2.0, cap_style=2) for s in N.STREETS
                   if s["class"] not in ("expressway", "ramp")]
                  + [LineString(s["line"]).buffer(25.0, cap_style=2) for s in N.STREETS if s["class"] == "expressway"]
                  + [q.buffer(red_w(cls) / 2.0, cap_style=2) for _, q, cls in N.OSM_HOST])
LRT_GROUND = OWN_ROW
NET_LAND = GATE.difference(RED).difference(T.KEEP_POLY).difference(LRT_GROUND).difference(DEPOT)


def net_ha(z):
    return Polygon(z["polygon"]).buffer(0).intersection(NET_LAND).area / 1e4


KEEP_HOMES, KEEP_JOBS = 3697, 7180     # keep k_gate_district (the trial run: lots of source keep), modelled as is
POP_PLAN, JOBS_PLAN = 223000, 99338
RES_PER_HOME = 2.5                       # rule 24: residents = GFA / 30, homes = GFA / 75 (home_m2)
HOMES_T = int(round((POP_PLAN - KEEP_HOMES * RES_PER_HOME) / RES_PER_HOME, -1))
JOBS_T = int(round(JOBS_PLAN - KEEP_JOBS, -2))
SKIP = {"village_existing"}
NETHA = {z["id"]: net_ha(z) for z in ZONES}
# homes: residential_mid / high / waterfront scaled by one factor (FH); low-rise, business and mixed keep the scheme density.
# jobs: shops, services and offices in the residential zones (schools and kindergartens count as jobs, gen_buildings
# subtracts them); logistics, industry, medical and sport keep the scheme density; business and mixed_centre scaled (FJ).
# m² per job of the twin (land_util.twin_m2): business 90, social 50, industry 100 — the floor area has to fit the zone.
# residential_mid 40 (was 25): its zones fill their floor area in full, while the office zones b_ne_1/2, c_admin and b_datahub
# cannot hold theirs (buildings over 50 m without a fire ring and over 28 m without a fire band are lowered; Gate r5: jobs
# −8 %), so the street-floor shops and services of the mid-rise quarters take the part FJ moves out of the office zones
JOBS_RES = {"residential_high": 60.0, "residential_mid": 40.0, "residential_low": 5.0, "waterfront": 20.0}
H_SCALED = {"residential_high", "residential_mid", "waterfront"}
J_SCALED = {"business", "mixed_centre"}
J_KEEP = {"b_tpu"}                 # the 3,6 ha of the scheme's ТПУ quarter outside the trial area keep the scheme's 200 jobs/ha


def _sum(key, pick):
    return sum(NETHA[z["id"]] * (z["rules"].get(key) or 0) for z in ZONES if pick(z))


def _counted(z):
    return z["use"] not in SKIP and z["_base"] != "z_gate_district"


# fire gaps (w44, rule 12): two buildings over 28 m stand ≥ 22 m apart (2 × 8 m + 6 m), so in a dense zone about half of them
# stay at 28 m. A zone's lowest floors allow a 28 m building (storey heights: land_util.floor_heights, the twin's medians;
# housing up to 9 floors is res_mid), and the City zones keep the jobs their blocks hold with the gaps under the 50 m cap.
FH_M = LU.floor_heights()
TALL_H = 28.0
# jobs/ha the City zones hold with 22 m gaps and the 50 m cap (gen_buildings, integ 28b3071: b_cbd 782 948 of 837 114 m²,
# b_cbd_e 569 440 of 637 148 m² at 330 and 320 jobs/ha)
CBD_FIT = {"b_cbd": 305.0, "b_cbd_e": 285.0}
_fl_done = {}
for z in ZONES:
    r = z["rules"]
    fl = r.get("floors")
    if not fl or z["use"] in SKIP:
        continue
    _fh = FH_M.get("business", 4.43) if z["use"] in ("business", "mixed_centre") else FH_M.get("res_mid", 3.6)
    lo = int(TALL_H // _fh)
    msg = []
    if fl[0] > lo:
        r["floors"] = [lo, fl[1]]
        msg.append(f"нижняя этажность {fl[0]} → {lo} ({lo} × {_fh:.2f} м ≤ 28 м)")
    if z["_base"] in CBD_FIT and (r.get("jobs_per_ha") or 0) > CBD_FIT[z["_base"]]:
        msg.append(f"рабочих мест {r['jobs_per_ha']:.0f} → {CBD_FIT[z['_base']]:.0f} на га")
        r["jobs_per_ha"] = CBD_FIT[z["_base"]]
    if msg and z["_base"] not in _fl_done:
        _fl_done[z["_base"]] = (z["_src"], "; ".join(msg))
for _b, (_src, _m) in sorted(_fl_done.items()):
    _w = (f"{_m}: пожарные разрывы 22 м между зданиями выше 28 м (fire_access.distance_to_wall_m, width_min_m) — "
          "из двух близких зданий выше 28 м поднимается одно, второе остаётся до 28 м (замечание w44)")
    if _src == "v0":
        Z.SCHEME_CHANGES.append((_b, _w))
    else:
        Z.CHANGES.append((_b, _w))
LOG.append({"what": "этажность и плотность под пожарные разрывы 22 м", "ids": sorted(_fl_done)})
for z in ZONES:
    if z["_src"] == "v0" and z["use"] in JOBS_RES:
        z["rules"]["jobs_per_ha"] = max(float(z["rules"].get("jobs_per_ha") or 0), JOBS_RES[z["use"]])
h_fix = _sum("homes_per_ha", lambda z: _counted(z) and not (z["_src"] == "v0" and z["use"] in H_SCALED))
h_var = _sum("homes_per_ha", lambda z: _counted(z) and z["_src"] == "v0" and z["use"] in H_SCALED)
j_fix = _sum("jobs_per_ha", lambda z: _counted(z) and not (z["_src"] == "v0" and z["use"] in J_SCALED and z["_base"] not in J_KEEP))
j_var = _sum("jobs_per_ha", lambda z: _counted(z) and z["_src"] == "v0" and z["use"] in J_SCALED and z["_base"] not in J_KEEP)
FH = (HOMES_T - h_fix) / h_var
FJ = (JOBS_T - j_fix) / j_var
M2_JOB = {"business": 90.0, "social": 50.0, "industry": 100.0}
for z in ZONES:
    if z["_src"] != "v0" or z["use"] in SKIP:
        continue
    r = z["rules"]
    if z["use"] in H_SCALED and r.get("homes_per_ha"):
        r["homes_per_ha"] = round(r["homes_per_ha"] * FH, 1)
    if z["use"] in J_SCALED and z["_base"] not in J_KEEP and r.get("jobs_per_ha"):
        r["jobs_per_ha"] = round(r["jobs_per_ha"] * FJ, 1)
    # the floor area the densities need, with a margin for the service lots carved from the zone (schools, kindergartens)
    m2j = 100.0 if z["use"] in ("logistics", "industry") else (50.0 if z["use"] == "medical" else 90.0)
    need = ((r.get("homes_per_ha") or 0) * 75.0 + (r.get("jobs_per_ha") or 0) * m2j) / 1e4
    if r.get("far") is not None and need * 1.25 > r["far"]:
        r["far"] = round(need * 1.25 + 0.05, 1)
        fl = r.get("floors") or [3, 9]
        top = max(fl[1], int(math.ceil(r["far"] / 0.28)))
        if z["use"] in ("logistics", "industry"):
            top = fl[1]
        r["floors"] = [fl[0], min(top, 25)]
        r["height_cap_m"] = max(r.get("height_cap_m") or 0, round(r["floors"][1] * 3.6 + 6))
homes = sum(NETHA[z["id"]] * (z["rules"].get("homes_per_ha") or 0) for z in ZONES if z["use"] not in SKIP and z["_base"] != "z_gate_district")
jobs = sum(NETHA[z["id"]] * (z["rules"].get("jobs_per_ha") or 0) for z in ZONES if z["use"] not in SKIP and z["_base"] != "z_gate_district")
HOMES_R = int(round(homes, -1))
TARGETS = {"homes_2050": HOMES_R, "population_2050": int(round(HOMES_R * RES_PER_HOME)),
           "jobs_2050": int(round(jobs, -2)), "home_m2": 75.0,
           "plan_row": {"area_km2": 40, "population_2050": POP_PLAN, "jobs_2050": JOBS_PLAN},
           "keep": {"homes": KEEP_HOMES, "population": int(KEEP_HOMES * RES_PER_HOME), "jobs": KEEP_JOBS,
                    "source": "keep k_gate_district (данные квартала Gate District двойника, прогон gate_trial уровня 1)"},
           "source": "жители: строка плана Gate — 223 тыс. в 2050 г. (= CityStats.DistrictTarget2050k[0] двойника, "
                     "UnityProject/Assets/Scripts/DigitalTwin/CityStats.cs:13) минус квартал keep Gate District (3 697 квартир × 2,5); "
                     "сёла (существующие дома) двойник и CityStats не считают — они сверх цели и в отчёте отдельно; "
                     "рабочие места: двойник 2050 г. в полигоне Gate без масштабирования — 99 338 (buildings.csv, базовый сценарий: "
                     "офисы 88 764 + соцсфера 9 163 + досуг 1 408 + промышленность 3) минус keep (7 180); "
                     "по зонам — плотности схемы (homes_per_ha, jobs_per_ha), умноженные на общий коэффициент (квартиры ×%.3f, "
                     "места ×%.3f) так, чтобы плотность × чистая площадь кварталов (без красных линий и keep) дала цель; "
                     "зоны пробной зоны — как на уровне 1" % (FH, FJ)}

# ===================================================================================================== 7. objects
OBJ = []
TRIAL_OBJ = {o["registry_id"]: o for o in T.OBJ}
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


# the trial's objects as they are (Iconic group, keep ring, L7, Griffin, agglo station, social of the trial quarter …)
SRC_TRIAL = {"iconic_complex", "iconic_tower_main", "iconic_tower_second", "iconic_podium", "iconic_offices_6", "iconic_greenery",
             "gate_district_ring", "griffin_logopark", "interchange_a3_bakad", "road_bakad", "road_a3"}
for o in T.OBJ:
    d = copy.deepcopy(o)
    d["basis"] = "по источнику" if d["registry_id"] in SRC_TRIAL else "по правилу"
    if d["registry_id"] == "l7_lotte":
        d["chip"] = "модель"      # the source gives no point («в Alatau City»): the place is the trial's, by rule, shown as a model
    if d["registry_id"] == "road_a19":
        d["why"] = ("существующая (OSM): А-19 приходит к А-3 у развязки ic_a3_a19 на северо-востоке Gate (улицы k_* оси ax_a19); у Gate "
                    "маршрут KAZ06 идёт по общим проезжим частям: 9 сегментов — вместе с БАКАД (KZ02-01), 4 — вместе с А-3 (KAZ08), "
                    "там это одна дорога с двумя номерами, отдельной трассы А-19 нет (заметка реестра)")
        d["to"] = d["from"] = [-2057, -18466]
    if d["registry_id"] in ("settlement_yntymak", "settlement_zhanadaur"):
        d["why"] = "существующие дома и улицы села остаются (зоны village_existing, улицы OSM); новые улицы обходят село"
    if d["registry_id"] == "hv_lines_220":
        d["why"] = ("ВЛ 220 кВ: через центр Gate — в кабель (utilities: hv220_cable пробной зоны, hv220_cable_n по Восточной "
                    "улице и улице Есентай); южные линии остаются воздушными в своих коридорах (зоны u_hv_south_*), "
                    "решение владельца 31.10: кабель или обход ядра")
    OBJ.append(d)
have = {o["registry_id"] for o in OBJ}
# PepsiCo: on its OSM building (the twin's existing house bid 48572, 28 041 m²), never on the registry point
pep_fp = None
for g, p in C.layer_in("buildings", Point(-3079.0, -22541.0).buffer(5)) if hasattr(C, "layer_in") else []:
    if g.area > 20000:
        pep_fp = g
pep_c = (-3079.0, -22541.0) if pep_fp is None else (round(pep_fp.centroid.x, 1), round(pep_fp.centroid.y, 1))
obj("pepsico", "move", REG["pepsico"]["geom"]["coordinates"], list(pep_c), "point_50m",
    "по источнику: завод PepsiCo в мкр Ынтымақ строится — его корпус есть в OSM (здание двойника bid 48572, 28 041 м², 347 × 82 м); "
    "точка реестра стояла среди домов Ынтымака — объект на своём корпусе, корпус остаётся существующим зданием; "
    "вокруг — зона i_pepsico (промышленность)", yaw=-74.0, basis="по источнику")
# the А-3 diamond at ЖК Gate City: registry interchange_a3_km18_5 (OSM ramps, 74 m from node ic_a3_gatecity; the level-0 spec
# named km16_5, 1.9 km south, outside the city)
obj("interchange_a3_km18_5", "keep", REG["interchange_a3_km18_5"]["geom"]["coordinates"], [-3302.0, -23824.0], "point_50m",
    "по источнику: существующая развязка OSM (узел ic_a3_gatecity, ромб); в Gate её западные съезды fd499b4d и 86370d28 — "
    "к Проспекту Gate City; восточные съезды c1053ec1 и 0229484f и проезд 4d44246d с узла А-3 ведут за границу города "
    "на обрывок базовой карты (зданий нет, дальше улицы только 2099 г.) — сняты (retire_existing)", basis="по источнику")
# hospital (Golden gets its own id), polyclinic (Growing-E gets its own id)
hosp = Polygon(Z.ZBY["m_hospital"]["poly"]).buffer(0)
hfp = box(-2600.0, -18270.0, -2420.0, -18060.0).intersection(hosp)
obj("hospitals_stage1", "by_rule", None, [round(hfp.centroid.x, 1), round(hfp.centroid.y, 1)], "district_only",
    MODEL + ": генплан — больница 500 коек в Gate (1-я очередь); участок 3,8 га в зоне схемы m_hospital у дублёра и станции «Есентай»; "
            "Golden получает свой id", kind="hospital", footprint=hfp, years=Y4(2032, "social"), capacity={"beds": 500})
pc = box(-5260.0, -22760.0, -5150.0, -22660.0)
obj("polyclinic_250", "by_rule", [6930, 7814], [round(pc.centroid.x, 1), round(pc.centroid.y, 1)], "district_only",
    MODEL + ": часть программы «Коянкус» — поликлиника на 250 посещений в смену на свободной земле у западного края села "
            "(точка схемы стояла в огородах села); Growing-E получает свой id", kind="polyclinic", footprint=pc,
    years=Y4(2036, "social"), capacity={"visits_per_shift": 250})
# the Gate-2 plants on their lot (substation 4 500 m² on the west side, the boiler on the rest; модель qTwin), years = the twin's
# first stage by scenario
_x0, _lo, _hi = EN2.bounds[0], EN2.bounds[0], EN2.bounds[2]
for _ in range(50):
    _mid = (_lo + _hi) / 2.0
    if EN2.intersection(box(_x0 - 1, -1e6, _mid, 1e6)).area > 4500.0:
        _hi = _mid
    else:
        _lo = _mid
for _fid, _kind, _fp in (("ps_gate_2", "substation", EN2.intersection(box(_x0 - 1, -1e6, _hi, 1e6))),
                         ("hb_gate_2", "utility", EN2.difference(box(_x0 - 1, -1e6, _hi, 1e6)))):
    _f = T.TWIN_FAC[_fid]
    _fp = max(getattr(_fp.buffer(0), "geoms", [_fp.buffer(0)]), key=lambda q: q.area).simplify(0.3)
    obj(_fid, "by_rule", [_f["x"], _f["z"]], [round(_fp.centroid.x, 1), round(_fp.centroid.y, 1)], "none",
        MODEL + ": участок объекта двойника «%s» (networks.json %s, синтетический, первая очередь %d) — зона u_energy_gate_2 у "
                "точки двойника (%d, %d)" % (_f["name"], _fid, _f["stages"][0][0], _f["x"], _f["z"]),
        name_ru=_f["name"], kind=_kind, footprint=_fp, years=[int(st[0]) for st in _f["stages"]],
        source="StreamingAssets/twin/networks.json facilities[%s]" % _fid)
for o in V0["objects"]:
    rid = o["registry_id"]
    if rid in have or rid in {x["registry_id"] for x in OBJ}:
        continue
    d = {"registry_id": rid, "name_ru": o["name_ru"], "action": o["action"], "from": o.get("from"), "to": o.get("to"),
         "yaw": o.get("yaw"), "accuracy": o.get("accuracy"), "why": o.get("why"),
         "basis": "по правилу" if o["action"] in ("by_rule",) or str(o.get("why", "")).startswith(MODEL) else "по источнику"}
    OBJ.append(d)
for rid, r in REG.items():
    if r.get("district") == "gate" and rid not in {x["registry_id"] for x in OBJ}:
        LOG.append({"what": "строка реестра без объекта", "id": rid})

# ===================================================================================================== 8. keep, views, utilities
KEEP = copy.deepcopy(T.keep)
VIEWS = copy.deepcopy(T.VIEWS)
# 220 kV: the two overhead lines that cross the new city go into cable for their whole run inside Gate, along their own
# corridor (model route) — 121ff315 (north-west reserve, low-rise west, Жанадаур, the centre: joins the trial's cable along
# the BAKAD park) and bf8acecb (waterfront north, Data Hub, mid-rise north, aquapark, technopark); the two southern lines
# (92ca2130, 74b9e818) stay overhead in the scheme's corridors u_hv_south_*, away from new houses.
INF = {p["id"][:8]: (g, p) for g, p in C.layer_in("infrastructure", GATE) if p.get("class") == "power_line"}


def in_gate(short):
    g = INF[short][0].intersection(GATE)
    parts = [g] if g.geom_type == "LineString" else [q for q in g.geoms if q.geom_type == "LineString"]
    return max(parts, key=lambda q: q.length)


trial_cab = [tuple(p) for p in T.UTIL[0]["line"]]
L121 = in_gate("121ff315")
s0 = L121.project(Point(trial_cab[0]))
LOG.append({"what": "кабель 121ff315: начало кабеля пробной зоны от линии ВЛ", "m": round(L121.distance(Point(trial_cab[0])), 1)})
cab121 = list(substring(L121, 0, s0).coords) + trial_cab
if Point(cab121[0]).distance(Point(L121.coords[-1])) < Point(cab121[0]).distance(Point(L121.coords[0])):
    cab121 = list(substring(L121, s0, L121.length).coords)[::-1] + trial_cab
Lbf = in_gate("bf8acecb")
UTIL = [{"id": "hv220_cable", "kind": "power_cable_220kv", "line": [P1(p) for p in cab121],
         "replaces": "osm:" + INF["121ff315"][1]["id"], "years": Y4(2027),
         "why": "ВЛ 220 кВ (OSM 121ff315) через центр Gate — в кабель на всём протяжении в Gate: по своей трассе от северной "
                "границы до Жанадаура, дальше трассой уровня 1 по парку БАКАД до опоры у А-3 (решение владельца 31.10: кабель "
                "или обход ядра; модель qTwin трассы)"},
        {"id": "hv220_cable_n", "kind": "power_cable_220kv", "line": [P1(p) for p in Lbf.coords],
         "replaces": "osm:" + INF["bf8acecb"][1]["id"], "years": Y4(2031),
         "why": "ВЛ (OSM bf8acecb) над набережной, кварталами севера, аквапарком и технопарком — в кабель по своей трассе на всём "
                "протяжении в Gate (модель qTwin трассы), к началу застройки севера (2031)"}]

# ===================================================================================================== 9. axes, joints, phases
axes = copy.deepcopy(V0["axes"])
for a_ in axes:
    if a_["id"] == "ax_road17":
        pcs = [LineString(N.SID[s["id"]]["line"]) for s in N.STREETS if s.get("axis") == "ax_road17"]
        U = unary_union(pcs).intersection(GATE.buffer(-10.0))
        parts = [g for g in getattr(U, "geoms", [U]) if g.geom_type == "LineString"]
        if parts:
            longest = max(parts, key=lambda g: g.length)
            a_["line"] = [P1(p) for p in longest.simplify(2.0).coords]
            a_["why"] = (a_.get("why") or "") + "; линия оси — по дороге OSM внутри границы Gate (не ближе 10 м к границе): " \
                                                 "раньше ось шесть раз выходила за границу у x ≈ −6740 (spec_issues)"
    if a_["id"] == "ax_lrt":
        a_["line"] = [P1(p) for p in LRT_PTS[::max(1, len(LRT_PTS) // 40)]] + [P1(LRT_PTS[-1])]
GJ = [j for j in CITY["joints"]["items"] if "gate" in (j.get("between") or [])]
JOINTS = []
for j in GJ:
    JOINTS.append({"joint_id": j.get("id"), "x": j["x"], "z": j["z"], "kind": j.get("kind"), "between": j.get("between"),
                   "line": j.get("line")})
PHASES = copy.deepcopy(V0["phases"])

# ===================================================================================================== 10. spec
STREETS_OUT = []
for s in N.STREETS:
    d = {k: v for k, v in s.items() if not k.startswith("_")}
    q = [list(map(float, d["line"][0]))]
    for pt in d["line"][1:]:
        if math.dist(pt, q[-1]) > 0.05:          # a repeated vertex (left by a split) is not a segment
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
replaced = sorted((set(N.RETIRED) | set(T.spec["replaced_osm"])) - set(N.ORPHAN_OSM))

# agglomeration rail at the TPU station (tester r2 item 55): the trial's design, cut at the district's east edge (the city's)
RAIL = T.rail_spec(GATE, "Алматы-1: остальные 12,4 км 1-й очереди — вне города (за восточной границей района)")
RAIL_SZZ = sorted(z["id"] for z in ZONES_OUT if z["use"] in ("residential_high", "residential_mid", "residential_low", "mixed_centre",
                                                              "village_existing", "waterfront")
                  and Polygon(z["polygon"]).buffer(0).distance(LineString([(q[0], q[1]) for q in RAIL["lines"][0]["tracks"][0]["pts"]])) < 100.0)

spec = {
    "district": "gate", "version": 1, "level": 2,
    "made_by": "w47 tools/map/district/gate_build.py (весь район Gate)",
    "boundary": "city.json#districts/gate",
    "attribution": C.ATTRIBUTION,
    "area": [P1(p) for p in list(GATE.exterior.coords)[:-1]],
    "area_ha": round(GATE.area / 1e4, 1),
    "targets": TARGETS,
    "centres": V0["centres"],
    "axes": axes,
    "zones": ZONES_OUT,
    "lrt": LRT,
    "rail": RAIL,
    "objects": OBJ,
    "phases": PHASES,
    "joints": JOINTS,
    "edge_joints": [],
    "streets": STREETS_OUT,
    "nodes": NODES_OUT,
    "keep": KEEP,
    "views": VIEWS,
    "views_convention": T.VIEW_CONV,
    "utilities": UTIL,
    "corridors": None,
    "replaced_osm": replaced,
    "retire_existing": [{"osm": oid, "why_ru": why} for oid, why in sorted(N.ORPHAN_OSM.items())],
    "scheme_changes": [{"id": k, "why": v} for k, v in Z.SCHEME_CHANGES + N.SCHEME_CHANGES],
    "trial_changes": [{"id": k, "why": v} for k, v in N.TRIAL_CHANGED.items()] + [{"id": k, "why": v} for k, v in Z.CHANGES],
    "checks": {},
}

# overhead power lines that stay (rules 4 and 19, land), with their voltage: the trial builder's table (gate_trial_build.kv_corridors)
for u in UTIL:
    u["kv"] = 220
    u["kv_basis"] = T.KV_220_SRC
CORR = T.kv_corridors(spec)
spec["corridors"] = CORR
LOG.append({"what": "ВЛ в коридорах spec с напряжением", "n": len(CORR),
            "kv": sorted({(c["id"], c["kv"]) for c in CORR})})

if __name__ == "__main__":
    import gate_check as CHK
    res = CHK.run(spec, verbose=False)
    spec["checks"] = res
    spec["checks"]["build_log"] = LOG[:400]
    txt = json.dumps(spec, ensure_ascii=False, indent=1)
    with open(SPEC_OUT + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write(txt + "\n")
    os.replace(SPEC_OUT + ".tmp", SPEC_OUT)
    from collections import Counter
    print(f"wrote {SPEC_OUT}: {len(txt) // 1024} KB; streets {len(STREETS_OUT)}, nodes {len(NODES_OUT)}, zones {len(ZONES_OUT)}, "
          f"objects {len(OBJ)}; {time.time() - T0:.1f} s")
    print("targets", {k: TARGETS[k] for k in ("homes_2050", "population_2050", "jobs_2050")}, "FH %.3f FJ %.3f" % (FH, FJ))
    print("log", Counter(x["what"] for x in LOG))
    print(f"rail: {RAIL['lines'][0]['length_m']} m, edge {RAIL['lines'][0]['edge_joints']}, homes zones within 100 m {RAIL_SZZ}")
    for r_ in T.rail_check(RAIL, os.path.join(C.OUT, "gate")):
        print("  rail over", r_, "LOW" if r_[4] < r_[5] else "")
    if "--no-check" not in sys.argv:
        ok = CHK.main([SPEC_OUT])
        sys.exit(0 if ok else 1)
