#!/usr/bin/env python3
"""Golden · level 2 · builder of tools/map/spec/golden.json v1 (w50): the whole district.

    python3 -I tools/map/district/golden_build.py [--no-check] [--out SPEC.json]

Builds on the approved level-0 scheme (district/golden_v0.json). Network: golden_net.py (existing roads, the frame of the
scheme axes with four new А-3 diamonds, local streets of every new quarter); zones: golden_zones.py. Here: the LRT v1 (the
trunk Gate – Golden – Growing-E with its stations and viaducts), the land of the interchanges, sanitary gaps, objects
(registry rows: by source / by rule), utilities (220 kV and other overhead lines through the new city into cable), targets,
phases, axes, joints, replaced roads, and the self-check (golden_check.py).
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
import shapely.affinity  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import substring, unary_union  # noqa: E402

import golden_common as C  # noqa: E402
import golden_net as N  # noqa: E402
import golden_zones as Z  # noqa: E402
import land_util as LU  # noqa: E402
from gate_common import terrain as TR  # noqa: E402  (tools/map/geo/terrain.py, the twin's ground)

SPEC_OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(C.SPEC_DIR, "golden.json")
MODEL = C.MODEL
Y4 = C.Y4
fillet = C.fillet
CITY = C.CITY
REG = C.REG
V0 = C.V0
GOLDEN = C.GOLDEN
P1 = C.P1
LOG = []
TIMES = {"net+zones import": round(time.time() - T0, 1)}


def poly_pts(g):
    return C.poly_pts(g)


def nm(v):
    return f"{v:,.0f}".replace(",", " ")


# ===================================================================================================== 1. interchange land
# the land of every interchange (ramps, loops, embankments of the overpass) is a utility zone: no blocks, no local streets.
# New diamonds (net_templates.t_diamond, checked on the frame network): ramps within ±105 m across А-3 and ±570 m along it,
# the minor street on an embankment ±150 m from the А-3 axis.
IC_ALONG, IC_ACROSS, IC_EMB = 590.0, 125.0, 170.0
IC_POLYS = {}


def _a3_dir(pt):
    L = min((LineString(N.SID[k]["line"]) for k in N.A3_IDS), key=lambda q: q.distance(Point(pt)))
    s = L.project(Point(pt))
    a, b = L.interpolate(max(0.0, s - 30)), L.interpolate(min(L.length, s + 30))
    u = np.array([b.x - a.x, b.y - a.y])
    return u / np.linalg.norm(u)


for nid, n in N.NODES.items():
    if n["type"] != "diamond":
        continue
    c = np.array([n["x"], n["z"]])
    u = _a3_dir(c)
    v = np.array([u[1], -u[0]])
    rect = Polygon([tuple(c + u * IC_ALONG + v * IC_ACROSS), tuple(c + u * IC_ALONG - v * IC_ACROSS),
                    tuple(c - u * IC_ALONG - v * IC_ACROSS), tuple(c - u * IC_ALONG + v * IC_ACROSS)])
    minor = LineString(N.SID[[s for s in n["streets"] if s.startswith("s_")][0]]["line"])
    s0 = minor.project(Point(c))
    emb = substring(minor, max(0, s0 - IC_EMB), min(minor.length, s0 + IC_EMB)).buffer(26.0, cap_style=2)
    IC_POLYS[nid] = rect.union(emb).intersection(GOLDEN).buffer(0)
EXIST_IC = {
    "ic_km30": ("cloverleaf", (-1783.0, -12164.7), ["c743968e", "45bdf8f1", "38829489", "a1fea52f", "7d79ac96", "44a1d6e1",
                                                     "7b4025f9", "6367d669"], "interchange_a3_km30_1",
                "существующая развязка А-3 × KZ05-10 (OSM, клеверный лист), съезды как в данных"),
    "ic_km39": ("cloverleaf", (-860.5, -3284.2), ["4f97dd9d", "28a86ee2", "b5074204", "60ff8c62", "e80d8f55", "8e388f39",
                                                   "78c4f723"], "interchange_a3_km39_0",
                "существующая развязка А-3 у км 39 (OSM), съезды как в данных; часть съездов — за границей района (Growing)"),
}
for nid, (typ, xy, ramps, rid, why) in EXIST_IC.items():
    full = [N.SH[r] for r in ramps if r in N.SH]
    rl = [LineString(N.SID[N.KEEP_IDS[f]]["line"]) for f in full if f in N.KEEP_IDS]
    P = Point(xy)
    a3 = sorted(N.A3_IDS, key=lambda k: LineString(N.SID[k]["line"]).distance(P))[:1]
    cross = [s["id"] for s in N.STREETS if s["_layer"] == "osm" and s["class"] not in ("expressway", "ramp")
             and LineString(s["line"]).distance(P) < 60.0][:1]
    N.node(nid, xy[0], xy[1], typ, a3 + cross, keep_existing=True, registry_id=rid, osm_ids=full, why_ru=why)
    IC_POLYS[nid] = unary_union(rl).convex_hull.buffer(15.0).intersection(GOLDEN).buffer(0)
IC_LAND = unary_union(list(IC_POLYS.values()))

# ===================================================================================================== 2. LRT line (frame)
J001 = (-2571.1, -15712.2)            # city.json joint J001: LRT Gate – Golden
J027 = (562.9, -3866.2)               # city.json joint J027: LRT Golden – Growing-E
A1S = [tuple(p) for p in N.SID["s_a1_s"]["line"]]
# level 2: back across А-3 south of the «K-Park» diamond (the scheme crossed it diagonally through the diamond, over the
# overpass embankment of X-T2 and its ramps — the viaduct could not clear them), then north west of А-3 to Теренкара
LRT_NE = [(-2150.0, -11780.0), (-1950.0, -11450.0), (-1500.0, -11050.0), (-1150.0, -10750.0), (-900.0, -10300.0),
          (-800.0, -9700.0), (-900.0, -9250.0), (-1250.0, -9030.0), (-1480.0, -8800.0), (-1520.0, -8250.0),
          (-1570.0, -7950.0), (-1650.0, -7350.0), (-1780.0, -6250.0), (-1650.0, -5650.0), (-1150.0, -5350.0), (-500.0, -5300.0),
          (200.0, -5250.0), (458.7, -5107.2), (552.8, -3922.2), J027]
LRT_PTS = fillet([J001] + A1S + LRT_NE, 300)
Z.SCHEME_CHANGES.append(("LRT", "у «K-Park» ЛРТ пересекает А-3 южнее ромба (у z −9030) и идёт к Теренкаре западнее А-3; у схемы линия "
                                "шла по диагонали через сам ромб над насыпью путепровода X-T2 и съездами — эстакада не набирала "
                                "габарит 5 м (правило 25); станция L6 «Golden-Центр / K-Park» — в западной части центра Z-K1"))
L_LRT = LineString(LRT_PTS)
LRT_W = float(LU.Norms().v("lrt.corridor_width_m", "double_track"))


def chain(pt):
    return L_LRT.project(Point(pt))


def at_chain(s):
    p = L_LRT.interpolate(s)
    return (p.x, p.y)


# the median of Западный проспект (south): from the junction with X-T4 to KZ05-10; own right of way elsewhere
S_MED0 = chain(A1S[0]) + 25.0
S_MED1 = chain(A1S[-1]) - 140.0                    # the line leaves the median before the KZ05-10 junction (curve R 300)
OWN_ROW = unary_union([substring(L_LRT, 0.0, S_MED0).buffer(LRT_W / 2 + 2, cap_style=2),
                       substring(L_LRT, S_MED1, L_LRT.length).buffer(LRT_W / 2 + 2, cap_style=2)])
# viaducts: over А-3 and the interchange land (three crossings), with 120 m ramps (6.5 m clearance + deck at ≤ 6 %)
RAMP_M = 120.0
PAD_M = 70.0           # full height this far before the hazard (an expressway on an embankment needs more than 6.5 m)
HAZ = unary_union([LineString(N.SID[k]["line"]).buffer(40.0) for k in N.A3_IDS]
                  + [LineString(s["line"]).buffer(20.0) for s in N.STREETS if s["class"] == "ramp"] + [IC_LAND])
_iv = []
_x = L_LRT.intersection(HAZ)
for q in getattr(_x, "geoms", [_x]):
    if q.is_empty or q.geom_type != "LineString":
        continue
    a_, b_ = sorted((chain(q.coords[0]), chain(q.coords[-1])))
    _iv.append([a_ - PAD_M - RAMP_M, b_ + PAD_M + RAMP_M])
_iv.sort()
SEC_ELEV = []
for a_, b_ in _iv:
    if SEC_ELEV and a_ <= SEC_ELEV[-1][1] + 250.0:
        SEC_ELEV[-1][1] = max(SEC_ELEV[-1][1], b_)
    else:
        SEC_ELEV.append([max(0.0, a_), min(L_LRT.length, b_)])
LRT_RAMPS = [substring(L_LRT, a_, a_ + RAMP_M).buffer(15.0, cap_style=2) for a_, _ in SEC_ELEV] + \
            [substring(L_LRT, b_ - RAMP_M, b_).buffer(15.0, cap_style=2) for _, b_ in SEC_ELEV]
LOG.append({"what": "ЛРТ: эстакады", "m": [[round(a_), round(b_)] for a_, b_ in SEC_ELEV]})
# stations: the scheme's ten, at their chainage on the line, plus two where the scheme's spacing was over 1.5 km
ST_PLAN = [("L1", "Жаңаталап"), ("L2", "Южный Golden"), ("L3", "Сады (KZ05-10)"), ("L3a", "Сады-Север"),
           ("L4", "Медкластер"), ("L5", "Университет «Көктерек»"), ("L6", "Golden-Центр / K-Park"),
           ("L7", "Теренкара-Запад"), ("L8", "Северный Golden"), ("L8a", "Северная магистраль"), ("L9", "Ақжар"), ("L10", "Әли")]
V0ST = {s["id"]: s for s in V0["lrt"]["stations"]}
S_PLAN = {k: chain((V0ST[k]["x"], V0ST[k]["z"])) for k in V0ST}
S_PLAN["L3a"] = 0.5 * (S_PLAN["L3"] + S_PLAN["L4"])
S_PLAN["L8a"] = 0.5 * (S_PLAN["L8"] + S_PLAN["L9"])
S_PLAN["L10"] = min(S_PLAN["L10"], S_PLAN["L9"] + 1420.0)
S_PLAN["L6"] = chain((-1480.0, -8720.0))           # the line now passes K-Park west of А-3: the station at Z-K1 (west)
STATION_PTS = [at_chain(S_PLAN[k]) for k, _ in ST_PLAN]

KV_220_SRC = "OSM voltage=220000 (Overture source_tags), реестр hv_lines_220 «ВЛ 220 кВ»"
CABLES = [("564b245a", 220, KV_220_SRC, 2034, "через логистику у км 39, жильё и центр севера, кампус и малоэтажные кварталы"),
          ("f3445a80", 220, KV_220_SRC, 2034, "вторая линия того же коридора, рядом с 564b245a"),
          ("bf8acecb", 220, KV_220_SRC, 2028, "через жильё юга (Z-R2S), логистику и малоэтажные кварталы; в Gate уже в кабеле"),
          ("b6e4919c", 35, MODEL + ": OSM w1276444747 — только power=line, без voltage; не 220 и не 110 кВ: стоит на опорах "
                               "power=pole (131 столб, 1 башня; линии 220 и 110 кВ выгрузки — на башнях power=tower), нанесена "
                               "той же правкой, что 7329b2c1 (22 кВ, АЭТ), северный конец в 113 м от неё — распределительная сеть; "
                               "класс 35 кВ — наибольший для такой линии (как land_util.UNKNOWN_KV)", 2030,
           "через медкластер, главный центр у K-Park и технокоридор"),
          ("7329b2c1", 22, "OSM voltage=22000, operator АЭТ (Overture source_tags)", 2031, "через главный центр и технокоридор")]
KV_OSM = {"4ea57bb1": 220, "f51c5bfe": 220, "20c6b40c": 220, "121ff315": 220, "988f9664": 220, "99d8168d": 220, "0bb49e7b": 220}
KV_MINOR_220V = {"68098e2f": (1, "OSM voltage=220 (В), power=minor_line — низковольтная сеть до 1 кВ")}
KV_LINE = (35, MODEL + ": OSM power=line без voltage — наименьший класс линий электропередачи 35 кВ (как land_util.UNKNOWN_KV), "
                       "охранная зона по utilities.power_line_protection_zone_m")
KV_MINOR = (10, MODEL + ": OSM power=minor_line (распределительная сеть на опорах) без voltage — класс 1–20 кВ")
# overhead power lines that stay (not laid in cable): their protected zones keep the local streets off (rule 4 — a road may
# cross a line, not run along it inside the zone)
_PZ = []
_CAB = {c_[0] for c_ in CABLES}
for _g, _p in C.layer_in("infrastructure", GOLDEN):
    if _p.get("subtype") != "power" or _p.get("class") != "power_line" or _p["id"][:8] in _CAB:
        continue
    _hw = LU.power_zone_m(LU.Norms(), {"kind": "power_line", "kv": KV_OSM.get(_p["id"][:8], KV_LINE[0]),
                                        "osm_class": "power_line"})[0]
    if _hw:
        _PZ.append(_g.buffer(_hw))
POWER_PZ = unary_union(_PZ) if _PZ else Polygon()

# the KAIST campus of Unity (LandmarkData kaist: plot PadW × PadD = 420 × 360 m, the QTwin campus model at its fixed size) at the
# QAIST point (owner: «перенести», 31.10), turned with the quarters round it (Unity yaw −4.5°, clockwise from north): no local
# street crosses it, the campus is one lot (8 m off for the pavements of the streets round it)
KAIST_XZ, KAIST_YAW, KAIST_W, KAIST_D = (-150.0, -11100.0), -4.5, 420.0, 360.0
KAIST_PAD = shapely.affinity.translate(shapely.affinity.rotate(box(-KAIST_W / 2, -KAIST_D / 2, KAIST_W / 2, KAIST_D / 2), -KAIST_YAW,
                                                               origin=(0, 0)), *KAIST_XZ)
# K-Park of Unity (LandmarkData kpark: its model is 360 × 280 m): zone Z-P3 is 260 × 420 m with arterials through it, so the park went
# over the streets; 300 m west, between the frame streets, turned 90° with the quarters (local streets go round it, as KAIST)
KPARK_XZ, KPARK_YAW, KPARK_W, KPARK_D = (-465.0, -8276.0), 0.0, 360.0, 280.0
KPARK_PAD = shapely.affinity.translate(shapely.affinity.rotate(box(-KPARK_W / 2, -KPARK_D / 2, KPARK_W / 2, KPARK_D / 2), -KPARK_YAW,
                                                               origin=(0, 0)), *KPARK_XZ)

# ===================================================================================================== 3. local streets
t = time.time()
N.LRT_RAMPS[:] = LRT_RAMPS
made = N.generate_local(stations=STATION_PTS, barriers=unary_union([OWN_ROW, IC_LAND, POWER_PZ, KAIST_PAD.buffer(8.0, join_style=2),
                                                                                 KPARK_PAD.buffer(8.0, join_style=2)]),
                        lrt_line=L_LRT)
LOG.append({"what": "местные улицы сгенерированы", "n": made, "s": round(time.time() - t, 1)})
TIMES["generate_local"] = round(time.time() - t, 1)


def ext_ok(P):
    return GOLDEN.exterior.distance(P) < 3.0 or any(math.dist((P.x, P.y), (n["x"], n["z"])) < 1.0 for n in N.NODES.values()
                                                    if n["type"] == "joint")


def extend_free_ends(layers=("frame",), reach=400.0):
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
            if N.houses_hit(seg.buffer(N.red_w(s["class"]) / 2.0)) or seg.crosses(L_LRT) or seg.intersects(IC_LAND):
                out.append({"what": "продолжение улицы каркаса задевает дома, ЛРТ или развязку: не строится", "id": s["id"], "at": P1(pt)})
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
TRIM_LOG = []
# frame streets whose end stays free (no street within 400 m ahead): cut back to their last junction
N.trim_free_ends(ext_ok, layers=("frame",), log=TRIM_LOG)
N.trim_free_ends(ext_ok, log=TRIM_LOG)
LOG += TRIM_LOG
N.snap_ends(tol=N.SNAP_J, log=LOG)
N.house_lanes(log=LOG)
N.link_dead_ends(log=LOG)


def serve_pieces(log=None, min_m2=2000.0, reach=150.0, inside=15.0):
    """Built zone land that the streets and the LRT's own corridor cut off from every street (rule 12): a local side street
    from the nearest street into the piece (≤ reach, ending `inside` m in), never across an expressway, a ramp, the LRT
    corridor, interchange land, water or a house (as gate_build.serve_pieces)."""
    lines = [(x["id"], LineString(x["line"]), x["class"]) for x in N.STREETS]
    lines += [("osm:" + oid, q, cls) for oid, q, cls in N.OSM_HOST]
    reds = unary_union([L.buffer(N.red_w(c) / 2.0) for _, L, c in lines if c not in ("expressway", "ramp")]
                       + [L.buffer(N.EXP_HALF) for _, L, c in lines if c in ("expressway", "ramp")])
    acc = [(sid, L, c) for sid, L, c in lines if c not in ("expressway", "ramp", "pedestrian_street", "bike_path")]
    at = shapely.STRtree([L for _, L, _ in acc])
    barrier = unary_union([L for _, L, c in lines if c in ("expressway", "ramp")] + [OWN_ROW, IC_LAND])
    made_ = []
    for z in Z.ZPLAN:
        if z["use"] not in Z.DEV_USES or (z.get("rules") or {}).get("lot_split") == "none":
            continue
        land = z["poly"].intersection(GOLDEN).difference(reds).difference(OWN_ROW).difference(IC_LAND).buffer(0)
        for q in getattr(land, "geoms", [land]):
            if q.geom_type != "Polygon" or q.area < min_m2:
                continue
            if any(acc[i][1].buffer(N.red_w(acc[i][2]) / 2.0 + 2.5).intersects(q) for i in at.query(q.buffer(N.EXP_HALF))):
                continue
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
                if sp.crosses(barrier) or sp.intersects(OWN_ROW) or sp.intersects(IC_LAND) or sp.intersects(N.WATER_POLY) \
                        or not GOLDEN.contains(sp) or N.houses_hit(sp.buffer(N.red_w("local") / 2.0)) or not q.contains(end):
                    continue
                best = (d, sid, sp)
            rec = {"zone": z["id"], "ha": round(q.area / 1e4, 2), "at": [round(v) for v in q.representative_point().coords[0]]}
            if best is None:
                if log is not None:
                    log.append({"what": "земля зоны без улицы: подъезда нет (ждёт решения)", **rec})
                continue
            sid_new = f"v_serve_{len(made_) + 1:02d}"
            N.street(sid_new, "local", best[2].coords, "въезд в квартал", int(z["years"][0]), layer="lane",
                     why=MODEL + f": земля зоны {z['id']} ({q.area / 1e4:.1f} га) отрезана от улиц линией ЛРТ, развязкой или "
                                 f"границами зон — въезд {best[2].length:.0f} м от {best[1]} (правило 12)")
            made_.append(sid_new)
            if log is not None:
                log.append({"what": "въезд в отрезанную землю зоны", "id": sid_new, "from": best[1], "m": round(best[2].length), **rec})
    return made_


serve_pieces(log=LOG)
N.trim_free_ends(ext_ok, layers=N.GEN + ("lane",), log=LOG)


def _ramp_terminals():
    """Points where a ramp of an existing interchange ends on a road (its terminal)."""
    rl = [LineString(x["line"]) for x in N.STREETS if x["class"] == "ramp"]
    roads = [LineString(x["line"]) for x in N.STREETS if x["class"] not in N.NO_JUNCTION]
    roads += [q for _, q, c in N.OSM_HOST if c not in N.NO_JUNCTION]
    rt = shapely.STRtree(roads)
    out = []
    for L in rl:
        for e in (L.coords[0], L.coords[-1]):
            P = Point(e)
            if any(roads[int(i)].distance(P) < 1.0 for i in rt.query(P.buffer(1.0))):
                out.append(P)
    return out


def cut_terminal_ends(log=None):
    """A generated street ending on a ramp terminal makes it a 5-arm junction (rule 6): cut back to its previous junction
    (or dropped when it has none); trim_free_ends then settles the rest."""
    terms = _ramp_terminals()
    if not terms:
        return 0
    n = 0
    for s in list(N.STREETS):
        if s["_layer"] not in N.GEN + ("lane",):
            continue
        for e in (0, -1):
            P = Point(s["line"][e])
            if min(t.distance(P) for t in terms) > 3.0:
                continue
            L = LineString(s["line"])
            oth = [o for o in N._lines_except(s["id"])]
            ot = shapely.STRtree([q for _, q, _ in oth])
            ch = [c for c in N._cut_points(L, oth, ot, s) if 3.0 < c < L.length - 3.0]
            if e == -1:
                ch = [c for c in ch if L.interpolate(c).distance(P) > 3.0]
                keep = substring(L, 0.0, max(ch)) if ch else None
            else:
                ch = [c for c in ch if L.interpolate(c).distance(P) > 3.0]
                keep = substring(L, min(ch), L.length) if ch else None
            if keep is None or keep.length < 25.0:
                N.STREETS.remove(s)
                N.SID.pop(s["id"], None)
            else:
                s["line"] = [[round(x, 1), round(z, 1)] for x, z in keep.coords]
            n += 1
            if log is not None:
                log.append({"what": "улица у узла съездов развязки: конец отведён (иначе пятый луч узла)", "id": s["id"],
                            "at": [round(P.x), round(P.y)]})
            break
    return n


if cut_terminal_ends(log=LOG):
    N.trim_free_ends(ext_ok, layers=N.GEN + ("lane",), log=LOG)
# new streets that leave the district by a few metres (an edge street along the border): clipped to it
for s in N.STREETS:
    if s["source"] != "new":
        continue
    L = LineString(s["line"])
    out_m = L.difference(GOLDEN).length
    if 0.0 < out_m < 5.0:
        q = L.intersection(GOLDEN.buffer(-0.05))
        q = max(getattr(q, "geoms", [q]), key=lambda g_: g_.length)
        s["line"] = [[round(x, 1), round(z, 1)] for x, z in q.coords]
        LOG.append({"what": "новая улица обрезана по границе района", "id": s["id"], "m": round(out_m, 1)})


def merge_near_junctions(tol=N.SNAP_J, log=None):
    """A new street end on a street a few metres from that street's crossing with another road is moved onto the crossing:
    phase_years counts junctions within SNAP_J as one, gen_network nodes them apart (the end would be blind while the
    street it ends on is not yet built)."""
    lines = [(x["id"], x) for x in N.STREETS]
    geo = {sid: LineString(x["line"]) for sid, x in lines}
    allL = [(sid, geo[sid], x["class"], x) for sid, x in lines if x["class"] not in N.NO_JUNCTION]
    allL += [("osm:" + oid, q, c, None) for oid, q, c in N.OSM_HOST if c not in N.NO_JUNCTION]
    tree = shapely.STRtree([L for _, L, _, _ in allL])
    n = 0
    for s in N.STREETS:
        if s["source"] != "new":
            continue
        for e in (0, -1):
            P = Point(s["line"][e])
            near = [allL[int(i)] for i in tree.query(P.buffer(tol)) if allL[int(i)][0] != s["id"]]
            hosts = [h for h in near if h[1].distance(P) < 0.5]
            if len(hosts) != 1:
                continue
            hid, H, _, hs = hosts[0]
            spans = [LineString([q["from"], q["to"]]).buffer(3.0) for q in (hs or {}).get("struct") or []
                     if q["kind"] in ("bridge", "overpass", "tunnel")]
            best = None
            for jid, M, _, ms in near:
                if jid == hid:
                    continue
                x = H.intersection(M)
                for q in getattr(x, "geoms", [x]):
                    if q.is_empty or q.geom_type != "Point":
                        continue
                    d = q.distance(P)
                    if 0.5 < d < tol and not any(sp.contains(q) for sp in spans) and (best is None or d < best[0]):
                        best = (d, q, jid)
            if best is None:
                continue
            s["line"][e] = [round(best[1].x, 1), round(best[1].y, 1)]
            n += 1
            if log is not None:
                log.append({"what": "конец улицы перенесён на соседнее пересечение (один узел вместо двух)", "id": s["id"],
                            "host": hid, "with": best[2], "m": round(best[0], 1)})
    return n


merge_near_junctions(log=LOG)
t = time.time()
YEAR_MOVES = N.phase_years(Polygon(), log=LOG)
TIMES["phase_years"] = round(time.time() - t, 1)


def tie_ends(tol=2.0, log=None):
    """New street ends that stopped 0.5–2 m short of the street they meet (a host whose end was moved by snap_ends after the
    piece was cut on it, or rounding): put on the host, with the point added to the host's line, so the junction is one node."""
    sid_at = {s["id"]: s for s in N.STREETS}
    allL = [(i, L, c) for i, L, c in N._lines_except(None) if c not in N.NO_JUNCTION]
    tree = shapely.STRtree([L.buffer(tol + 8.0) for _, L, _ in allL])
    n = 0
    for s in N.STREETS:
        if s["source"] != "new":
            continue
        for e in (0, -1):
            P = Point(s["line"][e])
            oth = [allL[int(j)] for j in tree.query(P) if allL[int(j)][0] != s["id"]]
            oth = [(i, LineString(sid_at[i]["line"]) if i in sid_at else L, c) for i, L, c in oth]
            near = sorted(((L.distance(P), i, L) for i, L, c in oth if L.distance(P) < tol), key=lambda t_: t_[0])
            if not near or near[0][0] < 0.5:
                continue
            d, hid, L = near[0]
            Q = L.interpolate(L.project(P))
            q = [round(Q.x, 1), round(Q.y, 1)]
            s["line"][e] = q
            h = sid_at.get(hid)
            if h is not None:
                HL = LineString(h["line"])
                m = HL.project(Point(q))
                acc, k = 0.0, 0
                for k in range(1, len(h["line"])):
                    acc += math.dist(h["line"][k - 1], h["line"][k])
                    if acc >= m:
                        break
                if min(math.dist(q, h["line"][k - 1]), math.dist(q, h["line"][k])) > 0.05:
                    h["line"].insert(k, q)
            n += 1
            if log is not None:
                log.append({"what": "конец улицы поставлен на улицу, к которой подходит", "id": s["id"], "host": hid,
                            "m": round(d, 2)})
    return n


tie_ends(log=LOG)


def split_rings(log=None):
    """A street drawn as a closed ring loses its closing piece in gen_network (sent to main as a tool bug): two halves."""
    for s in list(N.STREETS):
        if s["line"][0] != s["line"][-1] or len(s["line"]) < 4:
            continue
        L = LineString(s["line"])
        mid = L.length / 2.0
        q = L.interpolate(mid)
        qq = [round(q.x, 1), round(q.y, 1)]
        a = [[round(x, 1), round(z, 1)] for x, z in substring(L, 0.0, mid).coords][:-1] + [qq]
        b = [qq] + [[round(x, 1), round(z, 1)] for x, z in substring(L, mid, L.length).coords][1:]
        s2 = copy.deepcopy(s)
        s2["id"] = s["id"] + "_b"
        s["line"], s2["line"] = a, b
        LA, LB = LineString(a), LineString(b)
        st = s.get("struct") or []
        s["struct"] = [x for x in st if LA.distance(Point(x["from"])) < 1.0 and LA.distance(Point(x["to"])) < 1.0]
        s2["struct"] = [x for x in st if x not in s["struct"]]
        N.STREETS.insert(N.STREETS.index(s) + 1, s2)
        N.SID[s2["id"]] = s2
        if log is not None:
            log.append({"what": "улица-кольцо разделена на две (gen_network теряет замыкающий участок кольца)", "id": s["id"]})


split_rings(log=LOG)
# every new street that crosses water does so on a bridge (an end moved by the passes above can bring a link into a stream)
for s in N.STREETS:
    if s["source"] != "new" or any(x["kind"] == "bridge" for x in s.get("struct") or []):
        continue
    br = N.water_bridges(s["line"])
    if br:
        s["struct"] = list(s.get("struct") or []) + [{"from": [round(a[0], 1), round(a[1], 1)], "to": [round(b[0], 1), round(b[1], 1)],
                                                      "kind": k} for a, b, k in br]
        LOG.append({"what": "мост на новой улице через воду", "id": s["id"], "n": len(br)})
for s in N.STREETS:
    if s["class"].startswith("driveway"):
        s["class"] = "local"
        s["why"] = (s.get("why") or "") + "; в golden.json — местная улица (проезды даёт только land_driveways)"

# ===================================================================================================== 4. LRT v1
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
SP_MIN, SP_MAX = 800.0, 1500.0
ON_RAMP = [(a_, a_ + RAMP_M) for a_, _ in SEC_ELEV] + [(b_ - RAMP_M, b_) for _, b_ in SEC_ELEV]


def _ok_at(sm, prev_s, next_s):
    if any(a_ - PLAT / 2 - 5 <= sm <= b_ + PLAT / 2 + 5 for a_, b_ in ON_RAMP):
        return False
    if any(abs(c - sm) < PLAT / 2 + 8 for c, _ in ROADS_X):
        return False
    if prev_s is not None and not (SP_MIN + 5 <= sm - prev_s <= SP_MAX - 5):
        return False
    if next_s is not None and not (SP_MIN + 5 <= next_s - sm <= SP_MAX - 5):
        return False
    return 60.0 < sm < L_LRT.length - 60.0


STATIONS = []
_prev = None
_order = [k for k, _ in ST_PLAN]
for i, (sid, nm_) in enumerate(ST_PLAN):
    s0 = S_PLAN[sid]
    nxt = S_PLAN[_order[i + 1]] if i + 1 < len(_order) else None
    before = [c for c, _ in ROADS_X if c < s0 - 1]
    after = [c for c, _ in ROADS_X if c > s0 + 1]
    lo = before[-1] if before else 0.0
    hi = after[0] if after else L_LRT.length
    cands = [0.5 * (lo + hi)] + [s0 + d for d in sorted(np.arange(-400.0, 401.0, 5.0), key=abs)]
    sm = next((c for c in cands if _ok_at(c, _prev, nxt)), None)
    if sm is None:
        sm = next((c for c in cands if _ok_at(c, _prev, None)), s0)
        LOG.append({"what": "станция ЛРТ: места по всем условиям нет, взято ближайшее допустимое к предыдущей", "id": sid})
    S_PLAN[sid] = sm
    _prev = sm
    p = at_chain(sm)
    b4 = [c for c in ROADS_X if c[0] < sm]
    af = [c for c in ROADS_X if c[0] > sm]
    elev = any(a_ <= sm <= b_ for a_, b_ in SEC_ELEV)
    STATIONS.append({"id": sid, "name_ru": nm_, "x": round(p[0], 1), "z": round(p[1], 1),
                     "between": [b4[-1][1] if b4 else None, af[0][1] if af else None],
                     "kind": "elevated" if elev else "ground", "_s": sm})
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
        "id": "lrt_gate_golden", "name_ru": "ЛРТ Gate – Golden – Growing (участок Golden)",
        "line": [P1(p) for p in LRT_PTS],
        "sections": SECTIONS,
        "stations": [{k: v for k, v in s_.items() if not k.startswith("_")} for s_ in STATIONS],
        "ends": [{"kind": "joint", "id": "J001", "to": "gate"}, {"kind": "joint", "id": "J027", "to": "growing_e"}],
        "joints": [{"joint_id": "J001", "x": J001[0], "z": J001[1], "to": "gate"},
                   {"joint_id": "J027", "x": J027[0], "z": J027[1], "to": "growing_e"}],
        "years": Y4(2031),
        "why": "ствол схемы: от стыка J001 с Gate по своей полосе на север до поперечной «Жаңаталап», в разделительной полосе "
               "Западного проспекта до KZ05-10, эстакадой над А-3 к медкластеру и Университетскому городу, главный центр у "
               "K-Park, эстакадой обратно на запад от А-3 (в обход дач «Пчёлка» и «Рассвет»), к Северному Golden, эстакадой "
               "над А-3 у развязки «Северная» к Ақжару и Әли и на стык J027 с Growing-восток; станции между поперечными "
               "улицами, шаг 0,8–1,5 км (две станции добавлены: у схемы шаги 1,9 и 1,8 км)"}],
    "depots": []}

# ===================================================================================================== 5. zones
ZONES = []
ZIDS = set()
taken = Polygon()


def valid_pts(q):
    """The spec ring of polygon q (largest part, 0.1 m), valid after rounding: a ring whose rounding pinches or crosses
    itself (two vertices a few cm apart) is simplified a little until it is not."""
    pts = None
    for tol in (0.0, 0.05, 0.15, 0.4, 1.0):
        g = (q.simplify(tol) if tol else q).buffer(0)
        if g.is_empty:
            continue
        pts = C.poly_pts(g)
        if len(pts) >= 3 and Polygon(pts).is_valid:
            return pts
    g = shapely.make_valid(Polygon(pts))
    g = max([p_ for p_ in getattr(g, "geoms", [g]) if p_.geom_type == "Polygon"], key=lambda p_: p_.area)
    return C.poly_pts(g.buffer(0))


def opened(g, r=0.25):
    """g without necks and slivers thinner than 2r (they make rings that touch themselves once rounded); never larger than g."""
    o = g.buffer(-r, join_style=2, mitre_limit=5.0).buffer(r, join_style=2, mitre_limit=5.0)
    return o.intersection(g).buffer(0)


def zone_out(z, poly, rules):
    global taken
    parts = C.simple_parts(opened(poly.buffer(0).intersection(GOLDEN).difference(taken).buffer(0)), 500.0)
    for k, q in enumerate(parts):
        taken = taken.union(q)
        zid = z["id"] if k == 0 else f"{z['id']}_p{k + 1}"
        while zid in ZIDS:
            zid = zid + "_s"
        ZIDS.add(zid)
        d = {"id": zid, "use": z["use"], "name_ru": z["name_ru"], "polygon": valid_pts(q),
             "years": z["years"], "rules": copy.deepcopy(rules), "why": z["why"], "area_ha": round(q.area / 1e4, 2),
             "_src": z.get("src", "v0"), "_base": z["id"]}
        if z.get("density"):
            d["density"] = z["density"]
        ZONES.append(d)


# interchange land first (utility), then the sanitary gaps, the island quarters, the scheme's zones
IC_NAME = {"ic_zhanatalap": "«Жаңаталап»", "ic_kokterek": "«Көктерек»", "ic_kpark": "«K-Park»", "ic_north": "«Северная»",
           "ic_km30": "км 30,1", "ic_km39": "км 39"}
for nid, P in IC_POLYS.items():
    ex = nid in EXIST_IC
    yrs = [2025, 2025] if ex else [int(N.SID[[s for s in N.NODES[nid]["streets"] if s.startswith("s_")][0]]["years"][0])] * 2
    zone_out({"id": "u_" + nid, "use": "utility", "name_ru": f"Земля развязки {IC_NAME[nid]} (съезды, насыпи)", "years": yrs,
              "why": (MODEL + ": " if not ex else "") + "земля развязки — съезды, петли, насыпи путепровода; без кварталов и "
                     "местных улиц (здания и проезды не встают на насыпи и съезды)"}, P, {"lot_split": "none"})
    Z.SCHEME_CHANGES.append(("u_" + nid, f"земля развязки {IC_NAME[nid]} ({P.area / 1e4:.1f} га) вынута из зон схемы: "
                                         "съезды и насыпи не застраиваются"))
# the K-Park plot right after: one zone of its own, so no zone border cuts the model's lot (it lies across the park zone Z-P3's
# neighbours west of it)
zone_out({"id": "z_kpark", "use": "park", "name_ru": "K-Park (корейский парк и павильоны)", "years": [2025, 2027],
          "why": "участок под модель Unity kpark 360 × 280 м (объект k_park)"}, KPARK_PAD, {"lot_split": "none"})
Z.SCHEME_CHANGES.append(("z_kpark", f"участок K-Park ({KPARK_PAD.area / 1e4:.1f} га) вынут из зон схемы: модель 360 × 280 м целиком"))
# sanitary gaps (rule 15): every logistics / industry zone states its SZZ class; no housing within the class width w, nor
# within w × zone_factor in the downwind sector; the gap is planted (park zone) on the housing side
_LN = LU.Norms()
SZZ_W = {k: float(v["min"]) for k, v in _LN.v("szz.class_width_m").items()}
_WS = _LN.v("szz.wind_sector_deg")
SZZ_F, SZZ_SECTOR = float(_WS["zone_factor"]), tuple(_WS["default_sector"])
SZZ_CLASS = {
    "Z-L1": ("IV", MODEL + ": агропереработка (Hyundai Green Food, кластер агропереработки) — пищевые производства; ближайшие "
                   "примеры szz.class_examples — класс IV"),
    "Z-U2": ("III", MODEL + ": очистные сооружения района — класс III szz.class_width_m (300 м)"),
}
SZZ_DEFAULT = ("V", MODEL + ": склады и логистика готовых товаров без выбросов — наименьший класс szz.class_width_m")
for z in Z.ZPLAN:
    if z["use"] in ("industry", "logistics") or z["id"] in SZZ_CLASS:
        cls_, why_ = SZZ_CLASS.get(z["id"], SZZ_DEFAULT)
        z["rules"]["szz_class"] = cls_
        z["why"] = z["why"] + f"; СЗЗ класса {cls_} ({SZZ_W[cls_]:.0f} м): {why_}"


def _wedge(poly, a0, a1, r, step=20.0):
    b = poly.exterior if poly.geom_type == "Polygon" else max(poly.geoms, key=lambda q: q.area).exterior
    pts = [b.interpolate(t_) for t_ in np.arange(0.0, b.length, step)] + [poly.centroid]
    angs = np.radians(np.linspace(a0, a1 if a1 >= a0 else a1 + 360.0, 13))
    return unary_union([Polygon([(p.x, p.y)] + [(p.x + r * math.sin(t_), p.y + r * math.cos(t_)) for t_ in angs]) for p in pts])


RES_USES = ("residential_high", "residential_mid", "residential_low", "mixed_centre")
SZZ_LOG = []
for I in [z for z in Z.ZPLAN if z["rules"].get("szz_class")]:
    w = SZZ_W[I["rules"]["szz_class"]]
    reach = w * SZZ_F
    for R in [z for z in Z.ZPLAN if z["use"] in RES_USES]:
        if I["poly"].distance(R["poly"]) >= reach:
            continue
        strip = R["poly"].intersection(I["poly"].buffer(w).union(_wedge(I["poly"], *SZZ_SECTOR, reach)))
        if strip.area < 500.0:
            continue
        cls_ = I["rules"]["szz_class"]
        zone_out({"id": f"g_szz_{I['id']}_{R['id']}", "use": "park", "years": R["years"],
                  "name_ru": f"Санитарный разрыв {I['name_ru']} — {R['name_ru']} (озеленение)",
                  "why": f"СЗЗ класса {cls_}: {w:.0f} м, в подветренном секторе {SZZ_SECTOR[0]:.0f}–{SZZ_SECTOR[1]:.0f}° — "
                         f"{reach:.0f} м (правило 15): жильё не ближе к производству"}, strip, {"lot_split": "none"})
        SZZ_LOG.append((I["id"], R["id"], cls_, round(strip.area / 1e4, 2)))
        Z.SCHEME_CHANGES.append((f"g_szz_{I['id']}_{R['id']}", f"санитарный разрыв класса {cls_} ({w:.0f} м, по ветру "
                                 f"{reach:.0f} м; {strip.area / 1e4:.2f} га) из зоны {R['id']}: озеленение"))
# existing houses (villages and houses standing inside or next to the zone) keep the same gap, carved from the production zone
for I in [z for z in Z.ZPLAN if z["rules"].get("szz_class") and z["rules"].get("lot_split") != "none"]:
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
    zone_out({"id": f"g_szz_{I['id']}_houses", "use": "park", "years": I["years"],
              "name_ru": f"Санитарный разрыв {I['name_ru']} — существующие дома (озеленение)",
              "why": f"СЗЗ класса {cls_}: {w:.0f} м, в подветренном секторе — {reach:.0f} м (правило 15) от существующих домов"},
             strip, {"lot_split": "none"})
    SZZ_LOG.append((I["id"], "existing houses", cls_, round(strip.area / 1e4, 2)))
    Z.SCHEME_CHANGES.append((f"g_szz_{I['id']}_houses", f"санитарный разрыв класса {cls_} ({w:.0f} м, по ветру {reach:.0f} м; "
                             f"{strip.area / 1e4:.2f} га) из зоны {I['id']} у существующих домов ({len(hs)} домов, сёл {len(vil)})"))
LOG.append({"what": "санитарные разрывы (озеленение)", "pairs": SZZ_LOG})
for k, P in enumerate(N.UNSERVED):
    q = P.buffer(N.D_IN + 2.0)
    zone_out({"id": f"x_unserved_{k + 1}", "use": "reserve", "years": [2050, 2050],
              "name_ru": "Резерв: участок без подъезда", "why": "ни одна улица не доходит до участка без пересечения трассы, "
                                                                "воды или домов: резерв до подъезда"}, q, {"lot_split": "none"})
    Z.SCHEME_CHANGES.append((f"x_unserved_{k + 1}", f"{q.area / 1e4:.1f} га у ({P.centroid.x:.0f}, {P.centroid.y:.0f}) — резерв: "
                             "до участка не дойти улицей"))
# the land under the LRT viaducts: no buildings (rule 25 — the deck never passes through a building; the land tools clear
# only the ground corridor)
for k, (a_, b_) in enumerate(SEC_ELEV):
    q = substring(L_LRT, a_, b_).buffer(LRT_W / 2 + 5.0, cap_style=2)
    zone_out({"id": f"u_lrt_viaduct_{k + 1}", "use": "utility", "years": [2031, 2031],
              "name_ru": "Полоса под эстакадой ЛРТ", "why": MODEL + f": полоса {LRT_W + 10:.1f} м под эстакадой ЛРТ "
                                                                     "(участок {:.0f}–{:.0f} м линии): без зданий".format(a_, b_)},
             q, {"lot_split": "none"})
# zone strips too narrow for a quarter between corridors (golden_net.generate_local): planted
for k, P in enumerate(N.THIN):
    zz = max(Z.ZPLAN, key=lambda z_: z_["poly"].intersection(P).area)
    zone_out({"id": f"g_strip_{k + 1}", "use": "park", "years": zz["years"],
              "name_ru": f"Озеленение узкой полосы ({zz['name_ru']})",
              "why": MODEL + f": полоса зоны {zz['id']} уже 45 м между коридорами (А-3, ЛРТ, съезды, вода) — квартал не "
                             "помещается, озеленение"}, P.buffer(2.0), {"lot_split": "none"})
    Z.SCHEME_CHANGES.append((f"g_strip_{k + 1}", f"{P.area / 1e4:.2f} га узкой полосы зоны {zz['id']} у "
                             f"({P.centroid.x:.0f}, {P.centroid.y:.0f}) — озеленение (уже 45 м)"))
# steep ground in the built zones (slope over STEEP of the twin's terrain, the hill at Z-R2S south of Көктерек, the banks of
# the streams): lots there need cuts and fills over the 1.5 m of rule 3 — planted, not built
STEEP = 0.10
_xs = np.arange(Z.DEV.bounds[0], Z.DEV.bounds[2], 25.0)
_zs = np.arange(Z.DEV.bounds[1], Z.DEV.bounds[3], 25.0)
_X, _Zg = np.meshgrid(_xs, _zs)
_m = TR.terrain().slope(_X, _Zg, d=25.0) > STEEP
_steep = unary_union([box(x - 12.5, z - 12.5, x + 12.5, z + 12.5) for x, z in zip(_X[_m], _Zg[_m])])
_steep = _steep.buffer(-5.0, join_style=2).buffer(10.0, join_style=2).intersection(Z.DEV).difference(taken).buffer(0)
for k, P in enumerate(sorted([q for q in getattr(_steep, "geoms", [_steep]) if q.geom_type == "Polygon" and q.area > 5000.0],
                             key=lambda q: (-q.centroid.y, q.centroid.x))):
    zz = max(Z.ZPLAN, key=lambda z_: z_["poly"].intersection(P).area)
    zone_out({"id": f"g_slope_{k + 1}", "use": "park", "years": zz["years"], "name_ru": f"Склон ({zz['name_ru']}) — озеленение",
              "why": MODEL + f": уклон рельефа больше {STEEP * 100:.0f} % — террасы участков дали бы срезку/подсыпку больше "
                             "1,5 м (правило 3): склон озеленяется"}, P, {"lot_split": "none"})
    Z.SCHEME_CHANGES.append((f"g_slope_{k + 1}", f"{P.area / 1e4:.2f} га склона (уклон > {STEEP * 100:.0f} %) в зоне {zz['id']} "
                             f"у ({P.centroid.x:.0f}, {P.centroid.y:.0f}) — озеленение"))
for z in Z.ZPLAN:
    zone_out(z, z["poly"], z["rules"])
# no land outside the zones: every leftover sliver joins the zone it shares the longest border with
_gap = GOLDEN.difference(unary_union([Polygon(z["polygon"]).buffer(0) for z in ZONES]))
_ZT = shapely.STRtree([Polygon(z["polygon"]).buffer(0) for z in ZONES])
for g in [q for q in getattr(_gap, "geoms", [_gap]) if q.geom_type == "Polygon" and q.area > 1.0]:
    best, bl = None, 0.0
    for i in _ZT.query(g.buffer(0.5)):
        sh = Polygon(ZONES[int(i)]["polygon"]).buffer(0).boundary.intersection(g.buffer(0.5)).length
        if sh > bl:
            best, bl = int(i), sh
    if best is None:
        continue
    m = Polygon(ZONES[best]["polygon"]).buffer(0).union(g.buffer(0.01)).buffer(0)
    nb = [Polygon(ZONES[int(j)]["polygon"]).buffer(0) for j in _ZT.query(m) if int(j) != best]
    if nb:
        m = m.difference(unary_union(nb)).buffer(0)     # the 1 cm pad and rounding must not overlap the neighbours
        if m.geom_type == "MultiPolygon":
            m = max(m.geoms, key=lambda q_: q_.area)
    if m.geom_type == "Polygon" and not m.interiors:
        m = opened(m)
        if m.geom_type != "Polygon":
            continue
        ZONES[best]["polygon"] = valid_pts(m)
        ZONES[best]["area_ha"] = round(m.area / 1e4, 2)
_bad = [z["id"] for z in ZONES if not Polygon(z["polygon"]).is_valid]
assert not _bad, f"invalid zone rings: {_bad}"
TIMES["zones"] = round(time.time() - T0, 1)

# ===================================================================================================== 6. targets and densities
RED = unary_union([LineString(s["line"]).buffer(N.red_w(s["class"], s.get("profile")) / 2.0, cap_style=2) for s in N.STREETS
                   if s["class"] not in ("expressway", "ramp")]
                  + [LineString(s["line"]).buffer(25.0, cap_style=2) for s in N.STREETS if s["class"] == "expressway"]
                  + [q.buffer(N.red_w(cls) / 2.0, cap_style=2) for _, q, cls in N.OSM_HOST])
NET_LAND = GOLDEN.difference(RED).difference(OWN_ROW).difference(IC_LAND)


def net_ha(z):
    return Polygon(z["polygon"]).buffer(0).intersection(NET_LAND).area / 1e4


POP_PLAN, JOBS_PLAN = 675000, 237191
RES_PER_HOME = 2.5                       # rule 24: residents = GFA / 30, homes = GFA / 75 (home_m2)
HOMES_T = int(round(POP_PLAN / RES_PER_HOME, -1))
JOBS_T = JOBS_PLAN
SKIP = {"village_existing"}
NETHA = {z["id"]: net_ha(z) for z in ZONES}
JOBS_RES = {"residential_high": 30.0, "residential_mid": 20.0, "residential_low": 6.0}
H_SCALED = {"residential_high", "residential_mid", "mixed_centre"}
J_SCALED = {"business", "mixed_centre", "logistics"}
FH_M = LU.floor_heights()
TALL_H = 28.0
_fl_done = {}
for z in ZONES:
    r = z["rules"]
    fl = r.get("floors")
    if not fl or z["use"] in SKIP:
        continue
    _fh = FH_M.get("business", 4.43) if z["use"] in ("business", "mixed_centre") else FH_M.get("res_mid", 3.6)
    lo = int(TALL_H // _fh)
    if fl[0] > lo:
        r["floors"] = [lo, fl[1]]
        _fl_done.setdefault(z["_base"], f"нижняя этажность {fl[0]} → {lo} ({lo} × {_fh:.2f} м ≤ 28 м)")
for _b, _m in sorted(_fl_done.items()):
    Z.SCHEME_CHANGES.append((_b, f"{_m}: пожарные разрывы 22 м между зданиями выше 28 м (fire_access) — из двух близких зданий "
                                 "выше 28 м поднимается одно, второе остаётся до 28 м"))
for z in ZONES:
    if z["use"] in JOBS_RES:
        z["rules"]["jobs_per_ha"] = max(float(z["rules"].get("jobs_per_ha") or 0), JOBS_RES[z["use"]])


def _sum(key, pick):
    return sum(NETHA[z["id"]] * (z["rules"].get(key) or 0) for z in ZONES if pick(z))


h_fix = _sum("homes_per_ha", lambda z: z["use"] not in SKIP and z["use"] not in H_SCALED)
h_var = _sum("homes_per_ha", lambda z: z["use"] in H_SCALED)
j_fix = _sum("jobs_per_ha", lambda z: z["use"] not in SKIP and z["use"] not in J_SCALED)
j_var = _sum("jobs_per_ha", lambda z: z["use"] in J_SCALED)
# land yield: the land tools build a little less than density × net land (lots round the plots, setbacks, fire bands);
# measured on the level-2 scratch run of 01.11 (homes 256 194 of 270 030, jobs 224 915 of 237 200), модель qTwin
H_YIELD, J_YIELD = 0.949, 0.948
FH = (HOMES_T / H_YIELD - h_fix) / h_var
FJ = (JOBS_T / J_YIELD - j_fix) / j_var
H_CAP = 49.0                              # m: under the 50 m airfield threshold (heights.airfield_height_threshold_m)
for z in ZONES:
    if z["use"] in SKIP:
        continue
    r = z["rules"]
    if z["use"] in H_SCALED and r.get("homes_per_ha"):
        r["homes_per_ha"] = round(r["homes_per_ha"] * FH, 1)
    if z["use"] in J_SCALED and r.get("jobs_per_ha"):
        r["jobs_per_ha"] = round(r["jobs_per_ha"] * FJ, 1)
    m2j = 100.0 if z["use"] in ("logistics", "industry") else (50.0 if z["use"] in ("medical", "campus") else 90.0)
    need = ((r.get("homes_per_ha") or 0) * 75.0 + (r.get("jobs_per_ha") or 0) * m2j) / 1e4
    if r.get("far") is not None and need * 1.25 > r["far"]:
        r["far"] = round(need * 1.25 + 0.05, 1)
        fl = r.get("floors") or [3, 9]
        fh = FH_M.get("business", 4.43) if z["use"] in ("business", "mixed_centre") else FH_M.get("res_mid", 3.6)
        top = max(fl[1], int(math.ceil(r["far"] / 0.28)))
        if z["use"] in ("logistics", "industry"):
            top = fl[1]
        top = min(top, int((H_CAP - 4.0) // fh))
        r["floors"] = [min(fl[0], top), top]
        r["height_cap_m"] = min(H_CAP, max(r.get("height_cap_m") or 0, round(top * fh + 4.0, 1)))
homes = sum(NETHA[z["id"]] * (z["rules"].get("homes_per_ha") or 0) for z in ZONES if z["use"] not in SKIP)
jobs = sum(NETHA[z["id"]] * (z["rules"].get("jobs_per_ha") or 0) for z in ZONES if z["use"] not in SKIP)
TARGETS = {"homes_2050": HOMES_T, "population_2050": POP_PLAN, "jobs_2050": JOBS_T, "home_m2": 75.0,
           "plan_row": {"area_km2": round(GOLDEN.area / 1e6), "population_2050": POP_PLAN, "jobs_2050": JOBS_PLAN},
           "source": "жители: 675 тыс. в 2050 г. — CityStats.DistrictTarget2050k[1] двойника (= генплан № 727); квартиры = жители / "
                     "2,5; существующие дома (сёла, дачи) двойник и CityStats не считают — они сверх цели и в отчёте отдельно; "
                     "рабочие места: двойник 2050 г. в полигоне Golden без масштабирования — 237 191 (buildings.csv, базовый "
                     "сценарий, формулы CityStats); по зонам — плотности схемы (homes_per_ha, jobs_per_ha), умноженные на общий "
                     "коэффициент (квартиры ×%.3f для зон жилья 5–14 этажей и центров, места ×%.3f для деловых, центров и "
                     "логистики), так что плотность × чистая площадь кварталов (без красных линий, полосы ЛРТ и земли развязок) "
                     "даёт цель, делённую на выход земли (%.3f квартир, %.3f мест — замер прогона land, модель qTwin): "
                     "по плотностям зон %d квартир, %d мест" % (FH, FJ, H_YIELD, J_YIELD, round(homes, -1), round(jobs, -2))}

# ===================================================================================================== 7. objects
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


ZB = {}
for z in ZONES:
    ZB.setdefault(z["_base"], []).append(z)


def zpoly(base):
    return unary_union([Polygon(z["polygon"]).buffer(0) for z in ZB.get(base, [])])


def zone_years(base):
    return int(ZB[base][0]["years"][0])


def plot_at(pt, base, m2, aspect=1.4):
    """A plot of m2 round pt inside zone base, off the red lines, the LRT corridor and houses (a by-rule registry plot)."""
    avail = zpoly(base).difference(RED).difference(OWN_ROW).buffer(0)
    hs = unary_union([h.buffer(6.0) for h in N.houses_hit(Point(pt).buffer(600))]) if N.houses_hit(Point(pt).buffer(600)) else Polygon()
    avail = avail.difference(hs).buffer(0)
    P = Point(pt)
    parts = [q for q in getattr(avail, "geoms", [avail]) if q.geom_type == "Polygon" and q.area > 0.6 * m2]
    if not parts:
        return None
    q = min(parts, key=lambda q_: q_.distance(P))
    c = q.representative_point() if not q.contains(P) else P
    lo, hi = 0.0, 600.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if q.intersection(box(c.x - aspect * mid, c.y - mid, c.x + aspect * mid, c.y + mid)).area > m2:
            hi = mid
        else:
            lo = mid
    g = q.intersection(box(c.x - aspect * hi, c.y - hi, c.x + aspect * hi, c.y + hi)).buffer(0)
    g = max(getattr(g, "geoms", [g]), key=lambda x: x.area).simplify(0.5)
    return g


def put(rid, action, frm, to, base, m2, kind, years, why, accuracy="district_only", basis="по правилу", **kw):
    fp = plot_at(to, base, m2) if m2 else None
    if m2 and fp is None:
        LOG.append({"what": "объект реестра: участок не найден", "id": rid, "zone": base})
    tt = [round(fp.centroid.x, 1), round(fp.centroid.y, 1)] if fp is not None else list(to)
    return obj(rid, action, frm, tt, accuracy, why, basis=basis, kind=kind, footprint=fp, years=years, **kw)


def regpt(rid):
    g = (REG.get(rid) or {}).get("geom") or {}
    return list(g["coordinates"]) if g.get("type") == "Point" else None


# --- campus «Көктерек»: QAIST moves next to the space centre (the source: «рядом с действующим центром космической связи»)
obj("qaist", "move", regpt("qaist"), list(KAIST_XZ), "district_only",
    "по источнику (S21, Vlast): кампус QAIST «рядом с действующим центром космической связи «Көктерек»»; точка двойника "
    "(−1457, −12698) — модель (district_only), в 2,3 км от «Көктерек» за развязкой км 30,1; теперь — квартал кампуса Z-C1 "
    "южнее центра космической связи: участок 420 × 360 м под модель Unity kaist (местные улицы его обходят); первая очередь к 2028",
    basis="по источнику", kind="landmark", footprint=KAIST_PAD, years=Y4(2028, "social"), yaw=KAIST_YAW, capacity={"students": 5000})
put("kaist_research_institute", "move", regpt("kaist_research_institute"), (300.0, -10500.0), "Z-C1", 40000.0, "university",
    Y4(2029, "social"), "часть QAIST: едет вместе с кампусом — восточное крыло у «Көктерек» (точка источника — точка QAIST "
                       "двойника); участок 4 га по правилу", basis="по правилу")
put("academic_cluster", "add", None, (450.0, -9750.0), "Z-C2", 100000.0, "university", Y4(2036, "social"),
    "по источнику — университетский городок «в районе Көктерек» (точность 1 км); вместо 300+ одинаковых «школ» двойника — "
    "кампус в зоне Z-C2 в 1 км от «Көктерек»; участок 10 га головного вуза, остальное — кварталы кампуса зоны",
    accuracy="settlement_1km", basis="по источнику", capacity={"students": 40000})
put("british_edu_hub", "by_rule", None, (1000.0, -9800.0), "Z-C2", 60000.0, "university", Y4(2040, "social"),
    MODEL + ": в кластере вузов Z-C2 (места в источнике нет)", accuracy="none")
put("medcluster_golden", "keep", regpt("medcluster_golden"), regpt("medcluster_golden"), "Z-M1", 160000.0, "hospital",
    Y4(2030, "social"), "место двойника хорошее: 550 м от А-3 у новой развязки «Көктерек», у станции ЛРТ «Медкластер», рядом с "
                        "вузами; первая больница (500 коек, генплан: больницы 1-й очереди) — к 2030; модель Unity medcluster",
    basis="по источнику", capacity={"beds": 1864})
put("korean_clinics", "by_rule", None, (-1050.0, -10150.0), "Z-M1", 15000.0, "clinic", Y4(2031, "social"),
    MODEL + ": в медкластере (места в источнике нет)")
obj("k_park", "move", regpt("k_park"), list(KPARK_XZ), "district_only",
    "точка двойника — модель, но место хорошее: у станции ЛРТ и Теренкары, вокруг вырастает главный центр; модель Unity kpark "
    "360 × 280 м не помещается в зону Z-P3 (260 × 420 м, через неё идут магистрали) — участок под модель в 300 м западнее, "
    "между улицами каркаса (местные улицы его обходят); зона Z-P3 остаётся парком", basis="по источнику", kind="landmark",
    footprint=KPARK_PAD, years=Y4(2027), yaw=KPARK_YAW)
obj("k_park_parts", "move", regpt("k_park"), list(KPARK_XZ), "district_only", "внутри K-Park (его модель)", basis="по источнику")
put("sport_centre_hippodrome", "by_rule", None, (-750.0, -13700.0), "Z-S1", 400000.0, "sport", Y4(2046, "social"),
    MODEL + ": у развязок «Жаңаталап» и км 30,1 — зрители не едут через жильё; вдали от больниц; зона Z-S1")
obj("stadium_50k", "remove", None, None, "none", "по источнику: стадион на 50 тыс. отменён (план 2026); вместо него — спортцентр "
                                                 "и ипподром", basis="по источнику")
put("ethnoaul", "by_rule", None, (-350.0, -13350.0), "Z-S1", 50000.0, "culture", Y4(2046, "social"),
    MODEL + ": рядом с ипподромом — общие праздники и конные игры")
# the agro-processing zone Z-L1 is reached in 2026–30 only by the existing road d492aa6d along the north border: the first
# plants stand on it (an object opens no earlier than its streets)
_d492 = LineString(N.osm_line(N.SH["d492aa6d"])[0])


def near_d492(x, off=180.0):
    p = Point(N.on(_d492, x=x))
    s = _d492.project(p)
    a, b = _d492.interpolate(max(0, s - 20)), _d492.interpolate(min(_d492.length, s + 20))
    u = np.array([b.x - a.x, b.y - a.y]); u /= np.linalg.norm(u)
    n_ = np.array([u[1], -u[0]])
    if n_[1] > 0:
        n_ = -n_
    return (p.x + n_[0] * off, p.y + n_[1] * off)


_hy = near_d492(-4300.0)
_base_hy = next((z["_base"] for z in ZONES if Polygon(z["polygon"]).buffer(0).contains(Point(_hy))), "Z-L1")
put("hyundai_green_food", "by_rule", None, _hy, _base_hy, 100000.0, "logistics", Y4(2028),
    MODEL + ": в зоне агропереработки к западу от жилья (ветер В и СВ), у существующей дороги d492aa6d — до 2036 г. других "
            "улиц у зоны нет (схема ставила точку у (−5400, −3800), куда улицы приходят в 2038 г.)")
_ag = near_d492(-3300.0)
_base_ag = next((z["_base"] for z in ZONES if Polygon(z["polygon"]).buffer(0).contains(Point(_ag))), "Z-L1")
put("agro_processing_golden", "by_rule", None, _ag, _base_ag, 150000.0, "logistics", Y4(2030),
    MODEL + ": кластер агропереработки — у существующей дороги d492aa6d между Косөзеном и А-3 (схема: (−4300, −4100))")
put("kosozen_logistics", "by_rule", None, (-2400.0, -4000.0), "Z-L2", 150000.0, "logistics", Y4(2038),
    MODEL + ": источник — «между Косөзеном и Капчагайской трассой»; зона Z-L2 у Западного проспекта")
obj("space_comm_centre", "keep", [-442.0, -10648.0], [-442.0, -10648.0], "point_50m",
    "существующий объект, контур OSM 25 га (зона Z-U1); кампус рядом, не на нём", basis="по источнику")
obj("landfill_ali", "keep", regpt("landfill_ali"), regpt("landfill_ali"), "settlement_1km",
    "существующий полигон у посёлка Әли (точность источника 1 км): не трогаем; рядом — только склады (Z-L3, Z-L3e), жилья нет",
    basis="по источнику")
# the airport is Growing-West's (owner 31.10: runway centre (−16000, 1500), city.json airport_new; growing_w.json carries both
# objects): here only a reference without geometry, so the merge places it once; nothing in Golden is tied to its point
for rid in ("airport_alatau", "airport_rail_station"):
    obj(rid, "move", None, None, "district_only", "только ссылка: аэропорт и его станция — в Growing-запад (решение владельца "
        "31.10: ВПП с центром (−16000, 1500), city.json airport_new; объекты в growing_w.json); старая точка реестра "
        "(−16488, 561) попадала в Golden только по контуру двойника; в Golden к аэропорту ничего не привязано", basis="по источнику")
obj("golden_midrise", "by_rule", None, None, "district_only", "зоны Z-R2S, Z-R2N, Z-H1 и центры: дома-дубли двойника заменяются "
    "кварталами генератора (4–12 этажей)", basis="по правилу")
for rid, why in (("road_a3", "существующая (OSM), ось X-A3; добавлены 4 ромба: «Жаңаталап», «Көктерек», «K-Park», «Северная»"),
                 ("road_a19", "существующая (OSM), режет юго-восточный угол на 0,2 км (стыки J004/J005, J044/J045)"),
                 ("road_kz05_10", "существующая (OSM), ось X-T1, развязка км 30,1; стыки J042, J043"),
                 ("rail_bypass_zhetygen_kazybek", "существующая; режет западное крыло (резерв), стыки J031 и J040"),
                 ("settlement_zhanatalap", "существующее село: зона Z-V1, улицы OSM; новые улицы обходят дома"),
                 ("settlement_baiserke", "соседнее село задевает границу на 1,3 га: не застраиваем"),
                 ("settlement_ali", "существующий посёлок: зона Z-V4 вокруг домов (в схеме уровня 0 земли не было)"),
                 ("district_golden", "контур — city.json#districts/golden"),
                 ("interchange_a3_km30_1", "существующая (OSM), узел ic_km30 (keep_existing), съезды как в данных"),
                 ("interchange_a3_km39_0", "существующая (OSM), узел ic_km39 (keep_existing), съезды как в данных")):
    pt = regpt(rid)
    obj(rid, "keep", pt, pt, (REG.get(rid) or {}).get("accuracy") or "district_only", why, basis="по источнику")
obj("hv_lines_220", "reroute", None, None, "point_50m",
    "ВЛ 220 кВ: через новые кварталы севера, кампус и юг — в кабель (utilities: 564b245a, f3445a80, bf8acecb); линии ядра у "
    "K-Park и медкластера (b6e4919c без напряжения в OSM, 7329b2c1 22 кВ) — тоже в кабель; в логистике и резерве остаются "
    "воздушными в своих коридорах (решение владельца 31.10: кабель или обход ядра)", basis="по источнику")
have = {o["registry_id"] for o in OBJ}
for r in C.spec("registry")["rows"]:
    mine = "golden" in (r.get("district_area"), r.get("scheme_spec"), r.get("scheme_area")) or (
        r.get("scheme_conflict") or {}).get("owner") == "golden"
    if mine and r["id"] not in have:
        LOG.append({"what": "строка реестра без объекта", "id": r["id"]})

# ===================================================================================================== 8. utilities, corridors
INF = {p["id"][:8]: (g, p) for g, p in C.layer_in("infrastructure", GOLDEN) if p.get("class") in ("power_line", "minor_line")}


def in_golden(short):
    g = INF[short][0].intersection(GOLDEN)
    parts = [g] if g.geom_type == "LineString" else [q for q in g.geoms if q.geom_type == "LineString"]
    return parts


UTIL = []
for short, kv, basis, yr, why in CABLES:
    parts = in_golden(short)
    for k, q in enumerate(parts):
        if q.length < 5.0:
            continue
        UTIL.append({"id": f"cable_{short}" + (f"_{k + 1}" if k else ""), "kind": "power_cable_220kv" if kv == 220 else "power_cable",
                     "line": [P1(p) for p in q.coords], "replaces": "osm:" + INF[short][1]["id"], "years": Y4(yr),
                     "why": f"воздушная линия (OSM {short}) {why} — в кабель на всём протяжении в Golden по своей трассе "
                            f"(модель qTwin трассы), к началу застройки ({yr})", "kv": kv, "kv_basis": basis})

# ===================================================================================================== 9. axes, joints, phases
axes = copy.deepcopy(V0["axes"])
for a_ in axes:
    if a_["id"] == "X-IA":
        a_["why"] = ("план: «новая дорога IA по западной стороне города, западнее неё лесопарк»; коридор 150 м держим в резерве "
                     "(трасса не опубликована, до 2050 не строится); стыки city.json J143 (с Growing-запад) и J144 (наружу) — "
                     "на концах коридора")
    if a_["id"] in ("X-P1-1", "X-P1-2", "X-P2-1", "X-P2-2", "X-P2-3", "X-P2-4", "X-P2-5"):
        a_["why"] = (a_.get("why") or "") + "; уровень 2: аллеи речных парков (зелень строит land по правилам), не улицы сети"
    if a_["id"] == "X-L2":
        a_["why"] = (a_.get("why") or "") + "; уровень 2: коридор в резерве, до 2050 не строится"
axes.append({"id": "LRT", "class": "lrt", "name_ru": "Ствол ЛРТ Gate – Golden – Growing",
             "line": [P1(p) for p in LRT_PTS[::max(1, len(LRT_PTS) // 40)]] + [P1(LRT_PTS[-1])], "years": [2031, 2031],
             "why": "ось ЛРТ уровня 2 (lrt.lines[0])"})
GJ = [j for j in CITY["joints"]["items"] if "golden" in (j.get("between") or [])]
JOINTS = [{"joint_id": j.get("id"), "x": j["x"], "z": j["z"], "kind": j.get("kind"), "between": j.get("between"),
           "line": j.get("line")} for j in GJ]
PHASES = copy.deepcopy(V0["phases"])

# ===================================================================================================== 10. spec
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
    "district": "golden", "version": 1, "level": 2,
    "made_by": "w50 tools/map/district/golden_build.py (весь район Golden)",
    "boundary": "city.json#districts/golden",
    "attribution": C.ATTRIBUTION,
    "area": [P1(p) for p in list(GOLDEN.exterior.coords)[:-1]],
    "area_ha": round(GOLDEN.area / 1e4, 1),
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
    "utilities": UTIL,
    "corridors": None,
    "replaced_osm": replaced,
    "scheme_changes": [{"id": k, "why": v} for k, v in Z.SCHEME_CHANGES + N.SCHEME_CHANGES],
    "trial_changes": [],
    "checks": {},
}
_tmp = {k: v for k, v in spec.items() if k != "corridors"}
CORR = []
for c in LU.corridors(copy.deepcopy(_tmp)):
    if not str(c.get("source", "")).startswith("osm:"):
        continue
    short = c["source"][4:12]
    if short in KV_OSM:
        kv, basis = KV_OSM[short], KV_220_SRC
    elif short in KV_MINOR_220V:
        kv, basis = KV_MINOR_220V[short]
    else:
        kv, basis = KV_MINOR if c.get("osm_class") == "minor_line" else KV_LINE
    CORR.append({**c, "kv": kv, "kv_basis": basis})
spec["corridors"] = CORR
LOG.append({"what": "ВЛ в коридорах spec с напряжением", "n": len(CORR), "kv": sorted({(c["id"], c["kv"]) for c in CORR})})
TIMES["total"] = round(time.time() - T0, 1)
LOG.append({"what": "время шагов сборки, с", **TIMES})

if __name__ == "__main__":
    import golden_check as CHK
    res = CHK.run(spec, verbose=False)
    spec["checks"] = res
    spec["checks"]["build_log"] = LOG[:600]
    txt = json.dumps(spec, ensure_ascii=False, indent=1)
    with open(SPEC_OUT + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write(txt + "\n")
    os.replace(SPEC_OUT + ".tmp", SPEC_OUT)
    from collections import Counter
    print(f"wrote {SPEC_OUT}: {len(txt) // 1024} KB; streets {len(STREETS_OUT)}, nodes {len(NODES_OUT)}, zones {len(ZONES_OUT)}, "
          f"objects {len(OBJ)}; {time.time() - T0:.1f} s; {TIMES}")
    print("targets", {k: TARGETS[k] for k in ("homes_2050", "population_2050", "jobs_2050")}, "FH %.3f FJ %.3f est homes %d jobs %d" % (FH, FJ, homes, jobs))
    print("stations", [(s_["id"], round(s_["_s"]), s_["kind"]) for s_ in STATIONS])
    print("log", Counter(x["what"] for x in LOG))
    if "--no-check" not in sys.argv:
        ok = CHK.main([SPEC_OUT])
        sys.exit(0 if ok else 1)
