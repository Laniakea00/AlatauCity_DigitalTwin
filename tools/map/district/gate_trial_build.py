#!/usr/bin/env python3
"""Gate · level 1 · trial quarter at Iconic: builds tools/map/spec/gate_trial.json (spec v1, CONTRACT §3).

    python3 -I tools/map/district/gate_trial_build.py            # write the spec, then run the self-check
    python3 -I tools/map/district/gate_trial_build.py --no-check

Inputs (read-only): spec/{city,gate,norms,registry}.json, the level-0 Overture/OSM layers (roads, buildings), the twin
(roads.json, gate_district.bytes, gate_roads.json). Every coordinate below that does not come from those sources is the
cartographer's design (label «модель qTwin»). Unity frame: X east, Z north, metres.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import gate_common as C  # noqa: E402

SPEC_OUT = os.path.join(C.SPEC_DIR, "gate_trial.json")
MODEL = "модель qTwin"

# ----------------------------------------------------------------------------------------------------- years (4 values)
Y0, Y1, AFTER = 2025, 2050, 2099


def eff_year(year, use, scen):
    """Port of twin_common.effective_year (UnityProject/Tools/twin_gen/twin_common.py)."""
    if year <= Y0:
        return year
    dy = year - Y0
    if scen == "fast":
        return Y0 + max(1, int(round(dy * 0.75)))
    if scen == "slow":
        e = Y0 + int(round(dy * 1.3))
        return AFTER if e > Y1 else e
    if scen == "infra":
        return year + 2 if use == "housing" and year <= 2036 else year
    return year


def Y4(base, use="road"):
    return [eff_year(int(base), use, s) for s in ("base", "fast", "slow", "infra")]


# ----------------------------------------------------------------------------------------------------- geometry helpers
def fillet(pts, R, step_deg=6.0):
    """Polyline with every inner corner replaced by a circular arc of radius R (shortened where segments are short)."""
    P = [np.array(p, float) for p in pts]
    Q = [P[0]]                                     # drop straight-through vertices: only real corners get arcs
    for i in range(1, len(P) - 1):
        u = P[i] - Q[-1]; v = P[i + 1] - P[i]
        if np.linalg.norm(u) < 1e-6:
            continue
        cr = abs(u[0] * v[1] - u[1] * v[0]) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9)
        if cr > math.sin(math.radians(0.5)) or np.dot(u, v) < 0:
            Q.append(P[i])
    Q.append(P[-1])
    P = Q
    if len(P) < 3:
        return [tuple(p) for p in P]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        u = (a - b) / np.linalg.norm(a - b); v = (c - b) / np.linalg.norm(c - b)
        cosang = float(np.clip(np.dot(u, v), -1, 1))
        th = math.acos(cosang)                      # interior angle
        if abs(math.pi - th) < 1e-3:
            out.append(b); continue
        defl = math.pi - th
        T = R * math.tan(defl / 2)
        T = min(T, 0.45 * np.linalg.norm(a - b), 0.45 * np.linalg.norm(c - b))
        r = T / math.tan(defl / 2)
        p1 = b + u * T; p2 = b + v * T
        bis = (u + v) / np.linalg.norm(u + v)
        cen = b + bis * (r / math.sin(th / 2))
        a1 = math.atan2(*(p1 - cen)[::-1]); a2 = math.atan2(*(p2 - cen)[::-1])
        d = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        n = max(2, int(abs(math.degrees(d)) / step_deg) + 1)
        for k in range(n + 1):
            t = a1 + d * k / n
            out.append(cen + r * np.array([math.cos(t), math.sin(t)]))
    out.append(P[-1])
    res = [tuple(out[0])]
    for p in out[1:]:
        if math.hypot(p[0] - res[-1][0], p[1] - res[-1][1]) > 0.3:
            res.append(tuple(p))
    return res


def line_x_at_z(line, z):
    g = LineString([(-1e5, z), (1e5, z)]).intersection(line)
    if g.is_empty:
        return None
    pts = [g] if g.geom_type == "Point" else list(g.geoms)
    return pts[0].x


def line_z_at_x(line, x):
    g = LineString([(x, -1e6), (x, 1e6)]).intersection(line)
    if g.is_empty:
        return None
    pts = [g] if g.geom_type == "Point" else list(g.geoms)
    return pts[0].y


def poly_pts(p, nd=1):
    p = p.buffer(0)
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda q: q.area)
    return [[round(x, nd), round(z, nd)] for x, z in list(p.exterior.coords)[:-1]]


def rect(x0, z0, x1, z1):
    return box(min(x0, x1), min(z0, z1), max(x0, x1), max(z0, z1))


# ===================================================================================================== inputs
CITY = C.spec("city")
GATE0 = C.spec_v0()                     # the approved level-0 scheme (frozen copy: district/gate_v0.json)
NORMS = C.spec("norms")
REG = {r["id"]: r for r in C.spec("registry")["rows"]}
GATE_POLY = Polygon(CITY["districts"]["gate"]["polygon"]).buffer(0)
WORK = box(-4900, -21000, -1500, -18300)
OSM_ROADS = C.layer_in("roads", WORK)
OSM = {p["id"]: (g, p) for g, p in OSM_ROADS}
SHORT = {k[:8]: k for k in OSM}


def osm(short):
    return OSM[SHORT[short]]


BAKAD_WB = osm("27df9cd9")[0]          # westbound carriageway west of the A-3 interchange
BAKAD_EB = osm("6035cf98")[0]
A3_SB_N = osm("0f2288b1")[0]           # A-3 southbound north of the interchange


def z_wb(x):
    return line_z_at_x(BAKAD_WB, x)


def z_eb(x):
    return line_z_at_x(BAKAD_EB, x)


def z_c(x):
    return (z_wb(x) + z_eb(x)) / 2.0


# ===================================================================================================== keep (Gate District)
KEEP_R_MASK, KEEP_AREA = C.keep_radius()
KEEP_R = round(KEEP_R_MASK, 1)                  # edge of the quarter's ground: Unity cuts the model's ground on this round (w46)
# the keep follows the model's real outline: the round, and where a model building stands past it (one block of the quarter's
# west side, world x −3843…−3829, z −19567…−19551, up to 349 m from Iconic, 30.6 m high) that block's walls and coping + 0.5 m
KEEP_POLY, KEEP_BULGES = C.keep_outline(KEEP_R)
KEEP_PTS = poly_pts(KEEP_POLY, 2)
KEEP_POLY = Polygon(KEEP_PTS)


def keep_stubs():
    """Street ends of the quarter at its rim (gate_roads.json moved by Δ): [(x, z, dir_unit, oneway)]."""
    from collections import Counter
    roads = C.gate_roads_world()
    deg = Counter()
    for o, w in roads:
        for e in (w[0], w[-1]):
            deg[(round(e[0], 0), round(e[1], 0))] += 1
    out = []
    for o, w in roads:
        for a, b in ((w[0], w[1]), (w[-1], w[-2])):
            if deg[(round(a[0], 0), round(a[1], 0))] != 1:
                continue
            r = math.hypot(a[0] - C.ICONIC[0], a[1] - C.ICONIC[1])
            if r < KEEP_R - 30:
                continue
            d = (a - b) / np.linalg.norm(a - b)
            out.append((float(a[0]), float(a[1]), d, o))
    return out


STUBS = keep_stubs()


def stub(x, z, tol=12.0):
    best = min(STUBS, key=lambda s: math.hypot(s[0] - x, s[1] - z))
    if math.hypot(best[0] - x, best[1] - z) > tol:
        raise SystemExit(f"keep stub near ({x}, {z}) not found")
    return (round(best[0], 1), round(best[1], 1))


# Attach points (from the quarter's street ends; names by side) — checked against gate_roads.json at run time
ATT = {
    "W1": stub(-3784, -19334), "NW": stub(-3731, -19266), "W2": stub(-3836, -19448), "W3": stub(-3836, -19542),
    "W4": stub(-3798, -19656), "SW": stub(-3731, -19750), "SWt": stub(-3701, -19769), "Sw": stub(-3637, -19810),
    "Se": stub(-3365, -19812), "SEt": stub(-3296, -19769), "E1": stub(-3208, -19334), "E4": stub(-3210, -19656),
    "Nw": stub(-3637, -19190), "Nc": stub(-3501, -19171), "Ne": stub(-3365, -19188),
}

# ===================================================================================================== design constants
AVE_X = -3970.0           # Западный проспект (scheme x −3990, moved 20 m east: 42 m clear of the existing building at x −4012)
EAST_X = -3100.0          # Восточная улица with the LRT in its median (scheme LRT axis x −3100)
DUB_X = -2340.0           # дублёр А-3
Z_AVE = -19500.0          # Проспект Ворот (Iconic axis)
Z_PARK = -18900.0         # Парковая улица
Z_NORTH = -18520.0        # Северная улица (scheme ax_north)
Z_E1, Z_E4 = ATT["E1"][1], ATT["E4"][1]
Z_GO = -19125.0           # улица делового квартала Griffin (between Парковая and E1)
Z_19040 = -19040.0
IC_W = (AVE_X, round(z_c(AVE_X), 1))         # new diamond: Западный проспект × БАКАД
TERM_M = 175.0                                # ramp terminals 175 m from the BAKAD axis (deck +6.5 m, 5 % approaches)
T_N = (AVE_X, round(IC_W[1] + TERM_M, 1))
T_S = (AVE_X, round(IC_W[1] - TERM_M, 1))
RB_W = (-3875.0, -19495.0)                    # «Западная площадь» roundabout (W2, W3, Проспект Ворот-запад, Западная ул.)
CORNER = (-2520.0, -19998.0)                  # roundabout where the BAKAD street turns into the дублёр
HOOK_T = (-4300.0, T_S[1])                    # west bound of the low-rise houses at Южный проезд


# ===================================================================================================== area
def area_polygon():
    ver = A3_SB_N.parallel_offset(25, "right")                 # 25 m west of the A-3 SB carriageway centre line
    pts = [(-4005, -18495), (-2300, -18495), (-2300, -18780), (-2160, -18905)]
    pts += [(line_x_at_z(ver, z), z) for z in np.arange(-18905, -19800, -60.0)] + [(line_x_at_z(ver, -19800), -19800)]
    pts += [(-2141, -19800), (-2149, -19987), (-2110, -20100), (-1957, -20356), (-1818, -20468), (-1830, -20800),
            (-2560, -20800), (-2560, -20690), (-3100, -20690),
            # village piece: along the transverse street (6 m south of it), then 4 m west of улица Мусаева
            (-3166, -20775), (-3283, -20751), (-3314, -20744), (-3390, -20727), (-3413, -20721), (-3504, -20699),
            (-3518, -20693), (-3371, -20330), (-3385, -20300), (-3385, z_eb(-3385) - 35)]
    pts += [(x, z_eb(x) - 35) for x in np.arange(-3420, -3821, -40.0)]
    pts += [(-3830, -20140), (-3850, -20230), (-4680, -20230), (-4680, -19790), (-4005, -19790)]
    P = Polygon(pts).buffer(0).intersection(GATE_POLY)
    return Polygon([(round(x, 1), round(z, 1)) for x, z in P.exterior.coords])


AREA = area_polygon()
AREA_IN = AREA.buffer(-0.5)

# ===================================================================================================== streets
STREETS, NODES = [], {}


def node(nid, x, z, typ, streets=(), **params):
    if nid in NODES:
        n = NODES[nid]
        for s in streets:
            if s not in n["streets"]:
                n["streets"].append(s)
        n["params"].update(params)
        return n
    NODES[nid] = {"id": nid, "x": round(float(x), 1), "z": round(float(z), 1), "type": typ, "streets": list(streets),
                  "params": dict(params)}
    return NODES[nid]


def street(sid, cls, line, name_ru, base, *, oneway=False, struct=(), source="new", axis=None, profile=None, why=None,
           use="road", years=None):
    line = [(round(float(x), 1), round(float(z), 1)) for x, z in line]
    s = {"id": sid, "class": cls, "line": [list(p) for p in line], "name_ru": name_ru,
         "years": list(years) if years else Y4(base, use), "oneway": oneway, "profile": profile or {},
         "struct": [{"from": [round(a[0], 1), round(a[1], 1)], "to": [round(b[0], 1), round(b[1], 1)], "kind": k}
                    for a, b, k in struct],
         "source": source, "axis": axis}
    if why:
        s["why"] = why
    STREETS.append(s)
    return s


def on_line(line, z=None, x=None):
    L = LineString(line)
    if z is not None:
        return (line_x_at_z(L, z), z)
    return (x, line_z_at_x(L, x))


def split_line(line, z=None, x=None):
    """Two polylines: the part before and after the point of the line at z (or x); the point ends one and starts the other."""
    L = LineString(line)
    q = Point(on_line(line, z=z) if z is not None else on_line(line, x=x))
    d = L.project(q)
    acc, a, b = 0.0, [tuple(line[0])], []
    for i in range(1, len(line)):
        seg = math.dist(line[i - 1], line[i])
        if acc + seg < d - 0.05:
            a.append(tuple(line[i]))
        elif not b:
            a.append((q.x, q.y))
            b = [(q.x, q.y)] + ([tuple(line[i])] if acc + seg > d + 0.05 else [])
        else:
            b.append(tuple(line[i]))
        acc += seg
    return a, b


# ---------------------------------------------------------------- keep_existing: A-3 × БАКАД interchange and BAKAD
def osm_class(p):
    if p["class"] == "motorway":
        return "ramp" if p.get("sub") == "link" else "expressway"
    return None


def keep_name(p):
    n = p.get("name") or ""
    if n == "ҮАААЖ":
        return "БАКАД (Большая Алматинская кольцевая)"
    if n.startswith("Алматы"):
        return "А-3 Алматы – Өскемен"
    if p.get("sub") == "link":
        return "съезд развязки А-3 × БАКАД"
    return n


def keep_pieces(g):
    i = g.intersection(AREA)
    if i.is_empty:
        return []
    geoms = [i] if i.geom_type == "LineString" else [q for q in getattr(i, "geoms", []) if q.geom_type == "LineString"]
    return [q for q in geoms if q.length > 3.0]


EXPRESS_IDS = []
for oid, (g, p) in sorted(OSM.items()):
    cls = osm_class(p)
    if cls is None:
        continue
    for k, piece in enumerate(keep_pieces(g)):
        sid = "k_" + oid[:8] + ("" if k == 0 else f"_{k}")
        struct = []
        if p.get("bridge") or (p.get("level") or 0) >= 1:
            struct = [(piece.coords[0], piece.coords[-1], "overpass")]
        name = keep_name(p)
        ax = "ax_bakad" if "БАКАД" in name and cls == "expressway" else ("ax_a3" if cls == "expressway" else None)
        street(sid, cls, piece.coords, name, 2025, oneway=True, struct=struct, source="keep_existing:" + oid, axis=ax,
               years=C.EXISTING, why="как в OSM/Overture (направление линии = направление движения)")
        EXPRESS_IDS.append(sid)

# ---------------------------------------------------------------- keep_existing: village Ынтымақ piece and its streets
VILLAGE_CLS = {"residential", "service", "unclassified", "living_street"}
TRIM = {  # at-grade service accesses onto БАКАД EB are closed (rule 8): the village streets end at their first junction
    "48ea38c0": (-3291.0, -20144.0), "c7184e6f": (-3197.0, -20177.0)}
VILLAGE_IDS = []
for oid, (g, p) in sorted(OSM.items()):
    if p["class"] not in VILLAGE_CLS:
        continue
    for k, piece in enumerate(keep_pieces(g)):
        why = "существующая улица села (OSM), остаётся как есть"
        s8 = oid[:8]
        if s8 in TRIM:
            cut = Point(TRIM[s8])
            d = piece.project(cut)
            a = LineString([piece.interpolate(t) for t in np.linspace(0, d, 2)]) if d > 0 else None
            pts = list(piece.coords)
            # keep the part on the village side of the cut point
            far = piece.project(Point(pts[0])) if Point(pts[0]).distance(BAKAD_EB) > Point(pts[-1]).distance(BAKAD_EB) else piece.length
            from shapely.ops import substring
            piece = substring(piece, d, piece.length) if far == piece.length else substring(piece, 0, d)
            why = "существующий проезд села; въезд прямо на БАКАД закрыт (узел в одном уровне на скоростной дороге запрещён), обрезан у первого перекрёстка"
        L = piece.length
        if s8 == "09d8c252":
            cls = "village_main"
        elif p["class"] == "unclassified":
            cls = "local"
        elif p["class"] == "residential" and (p.get("name") or L > 150):
            cls = "village_secondary"
        else:
            cls = "village_lane"
        sid = "v_" + s8 + ("" if k == 0 else f"_{k}")
        street(sid, cls, piece.coords, p.get("name") or "улица села Ынтымақ", 2025, source="keep_existing:" + oid,
               years=C.EXISTING, why=why)
        VILLAGE_IDS.append(sid)

# ---------------------------------------------------------------- new skeleton
# Западный проспект (arterial_regulated): south leg → diamond over БАКАД → north → bend NE to Северная улица
A_N = (AVE_X, -18754.0)
ave_line = fillet([(AVE_X, -20230.0), T_S, IC_W, T_N, (AVE_X, Z_AVE), (AVE_X, -19334.0), (AVE_X, Z_PARK), A_N,
                   (AVE_X + 338 * math.sin(math.radians(40)), -18754 + 338 * math.cos(math.radians(40)))], 400)
ave_line = [p for p in ave_line if AREA.buffer(1).contains(Point(p))] or ave_line
L_ave = LineString(ave_line)
P_NORTH_W = on_line(ave_line, z=Z_NORTH)
P_AVE_N_EDGE = on_line(ave_line, z=-18495.0)
dz_deck = 37.0
street("s_west_ave_s", "district_transport", [(AVE_X, -20230.0), T_S], "Западный проспект (южное продолжение)", 2033,
       axis="ax_west", why="продолжение проспекта к югу от узла: связь с малоэтажной застройкой и западом села (уровень 2)")
ave_pts = [T_S] + [p for p in ave_line if p[1] > T_S[1] + 1]
street("s_west_ave", "arterial_regulated", ave_pts, "Западный проспект", 2033, axis="ax_west",
       struct=[((AVE_X, IC_W[1] - 150), (AVE_X, IC_W[1] - dz_deck), "embankment"),
               ((AVE_X, IC_W[1] - dz_deck), (AVE_X, IC_W[1] + dz_deck), "overpass"),
               ((AVE_X, IC_W[1] + dz_deck), (AVE_X, IC_W[1] + 150), "embankment")],
       why="ось схемы ax_west (x −3990) сдвинута на 20 м к востоку: существующее строение (Microsoft ML, 2 628 м², x −4147…−4012) "
           "остаётся в 42 м от оси; узел с БАКАД — неполный клеверный лист B2 (вместо трубы схемы), путепровод проспекта над БАКАД")
street("s_ave_w_west", "local", [(AVE_X, Z_AVE), (-4005.0, Z_AVE)], "улица к западным кварталам (продолжение за area)", 2033,
       why="западный луч перекрёстка Проспекта Ворот; дальше — сеть малоэтажных кварталов (уровень 2)")
street("s_ave_w", "district_transport", [(AVE_X, Z_AVE), RB_W], "Проспект Ворот (западный)", 2033, axis="ax_avenue_w",
       why="схема ax_avenue_w (2030) кончается на Западном проспекте (ax_west, 2033): открывается вместе с ним; до 2033 запад "
           "квартала обслуживает Западная площадь с улицы вдоль БАКАД")
street("s_w2", "local", [ATT["W2"], RB_W], "въезд W2 квартала Gate District", 2029)
street("s_w3", "local", [ATT["W3"], RB_W], "въезд W3 квартала Gate District", 2029)
street("s_west_st", "local", [RB_W, (RB_W[0], -19334.0), (RB_W[0], Z_19040), (RB_W[0], Z_PARK)], "Западная улица", 2029,
       why="открывается в 2029 вместе с Iconic (квартиры квартала keep — с 2029): подъезд к детсадам kg_gate_4, kg_gate_5, школе «Сити» и поликлинике у парка, которые открываются тогда же")
street("s_w1", "district_transport", [ATT["W1"], (RB_W[0], ATT["W1"][1]), (AVE_X, ATT["W1"][1])],
       "Северо-западный въезд (W1)", 2033, why="главный въезд кольца квартала (25 м); к проспекту — только правые повороты; "
                                               "открывается с Западным проспектом (2033), до того — въезды W2/W3 с Западной площади")
street("s_w4", "local", [ATT["W4"], (RB_W[0], ATT["W4"][1])], "въезд W4 квартала Gate District", 2029)

# улица вдоль БАКАД (district_transport): from «Западная площадь» around the quarter, along the park to the дублёр
BK = fillet([RB_W, (RB_W[0], ATT["W4"][1]), (-3870.0, -19720.0), (-3830.0, -19800.0), (-3760.0, -19860.0),
             (-3660.0, -19893.0), (-3365.0, -19922.0), (-3100.0, -19950.0), (-2900.0, -19972.0), (-2700.0, -19988.0),
             CORNER], 250)
L_BK = LineString(BK)
street("s_bakad_st", "district_transport", BK, "улица вдоль БАКАД", 2029, axis="ax_bakad_st",
       why="схема: (−3990,−19880)→(−2560,−19980); начало перенесено на «Западную площадь» — у проспекта узел ромба, а пятый луч в его примыкании запрещён")
P_BK_SW = on_line(BK, x=ATT["SW"][0])
P_BK_Sw = on_line(BK, x=ATT["Sw"][0])
P_BK_Se = on_line(BK, x=ATT["Se"][0])
street("s_sw", "local", [ATT["SW"], (ATT["SW"][0], ATT["SWt"][1]), P_BK_SW], "юго-западный въезд (SW)", 2029)
street("s_swt", "local", [ATT["SWt"], (ATT["SW"][0], ATT["SWt"][1])], "въезд SWt", 2029)
street("s_sw2", "local", [ATT["Sw"], P_BK_Sw], "южный въезд (S-запад)", 2029)
street("s_se", "local", [ATT["Se"], P_BK_Se], "южный въезд (S-восток), ось пешеходного моста", 2029)
# pedestrian bridge over БАКАД on the S-east axis, landing at the village service road (OSM 7c663bbc)
z_wb_p, z_eb_p = z_wb(ATT["Se"][0]), z_eb(ATT["Se"][0])
street("s_ped_bridge", "pedestrian_street", [P_BK_Se, (ATT["Se"][0], -20137.0), (-3350.0, -20137.0)],
       "пешеходный мост через БАКАД", 2033, axis="ax_ped_bridge",
       struct=[((ATT["Se"][0], z_wb_p + 28), (ATT["Se"][0], z_eb_p - 25), "overpass")],
       why="сквозь парк БАКАД, мост над обеими проезжими частями, спуск к проезду села у торгового двора (OSM 7c663bbc)")

# Восточная улица with the LRT in the median: north edge → Iconic → over БАКАД → ТПУ → south edge
EAST = fillet([(EAST_X, -18495.0), (EAST_X, -19720.0), (-3047.0, -19955.0), (-3010.0, -20110.0), (-2975.0, -20330.0),
               (-2955.0, -20600.0), (-2952.0, -20690.0)], 300)
L_EAST = LineString(EAST)
z_bk_e = None
P_EAST_BK = L_EAST.intersection(L_BK)
P_EAST_BK = (P_EAST_BK.x, P_EAST_BK.y)
zw, ze = line_z_at_x(BAKAD_WB, -3010), line_z_at_x(BAKAD_EB, -3010)
EAST_N, EAST_S = split_line(EAST, z=P_EAST_BK[1])
EAST_N, EAST_M = split_line(EAST_N, z=Z_AVE)
EAST_PROFILE = {"median_w": 8.0, "lanes": [2, 2], "note_ru": "в разделительной полосе — пути ЛРТ (на земле до z −19720, дальше эстакада)"}
street("s_east", "district_transport", EAST_N, "Восточная улица (ЛРТ в разделительной полосе)", 2028, axis="ax_tpu",
       profile=EAST_PROFILE,
       why="1-я очередь (2028, вместе с Проспектом Ворот, который на ней кончается): от северного края до Проспекта Ворот; "
           "полоса под ЛРТ резервируется сразу, пути — в 2031 (ax_lrt)")
street("s_east_m", "district_transport", EAST_M, "Восточная улица (ЛРТ в разделительной полосе)", 2029, axis="ax_tpu",
       profile=EAST_PROFILE, why="2-я очередь (2029, вместе с улицей вдоль БАКАД и въездом Е4): от Проспекта Ворот до улицы вдоль БАКАД")
street("s_east_s", "district_transport", EAST_S, "Восточная улица (путепровод над БАКАД, ТПУ)", 2030, axis="ax_tpu",
       profile=EAST_PROFILE,
       struct=[(on_line(EAST, z=-19975.0), on_line(EAST, z=zw + 30), "embankment"),
               (on_line(EAST, z=zw + 30), on_line(EAST, z=ze - 30), "overpass"),
               (on_line(EAST, z=ze - 30), on_line(EAST, z=-20265.0), "embankment")],
       why="схема ax_tpu: путепровод над БАКАД без съездов (узел grade_separation), ТПУ; открывается в 2030 вместе со станцией ТПУ (реестр agglo_rail_station_1, ГП727: 2030); пути ЛРТ в разделительной полосе — в 2031 (ax_lrt)")

street("s_ave", "arterial_regulated", [(EAST_X, Z_AVE), (-2960.0, Z_AVE), (-2700.0, Z_AVE), (-2520.0, Z_AVE), (DUB_X, Z_AVE)],
       "Проспект Ворот", 2028, axis="ax_avenue",
       why="схема: проспект от путепровода над А-3 (J013/J014) к Iconic; путепровод над А-3 — уровень 3 (восточный конец за границей "
           "города), в пробной зоне проспект кончается на дублёре; от Восточной до квартала — Площадь Ворот (пешеходная)")
street("s_gate_sq", "pedestrian_street", [(EAST_X, Z_AVE), (-3166.0, Z_AVE)], "Площадь Ворот", 2028,
       why="пешеходная площадь перед восточным фасадом Iconic: сектор обзора, выход со станции ЛРТ «Iconic»")
street("s_e1", "local", [ATT["E1"], (EAST_X, ATT["E1"][1]), (-2960.0, Z_E1), (-2700.0, Z_E1), (DUB_X, Z_E1)],
       "улица Е1", 2029)
street("s_e4", "district_transport", [ATT["E4"], (EAST_X, ATT["E4"][1]), (-2960.0, Z_E4), (-2700.0, Z_E4), (-2520.0, Z_E4),
                                      (DUB_X, Z_E4)], "улица Е4 (юго-восточный въезд квартала)", 2029)
street("s_set", "local", [ATT["SEt"], (EAST_X - 25.0, ATT["SEt"][1])], "въезд SEt", 2029,
       why="примыкание к западной проезжей части Восточной без пересечения путей ЛРТ (пути уже на подъёме)")

DUB = fillet([CORNER, (-2440.0, -19950.0), (-2370.0, -19870.0), (DUB_X, -19780.0), (DUB_X, Z_E4), (DUB_X, Z_AVE),
              (DUB_X, Z_E1), (DUB_X, -19100.0), (DUB_X, Z_PARK), (DUB_X, Z_NORTH), (DUB_X, -18495.0)], 250)
DUB_S, DUB_N = split_line(DUB, z=-19100.0)
street("s_dubler", "district_transport", DUB_N, "дублёр А-3", 2027, axis="ax_dubler_n",
       why="схема ax_dubler_n (2027): 1-я очередь от северного края до въезда Griffin; к северу от z −18900 ось держится x −2340 "
           "(схема уходила на x −2260 — там петля развязки А-3 × А-19)")
street("s_dubler_s", "district_transport", DUB_S, "дублёр А-3 (южный отрезок)", 2028, axis="ax_dubler_n",
       why="2-я очередь дублёра — вместе с Проспектом Ворот (2028), поворот к улице вдоль БАКАД у кольца")

street("s_park_w", "district_transport", [(AVE_X, Z_PARK), (RB_W[0], Z_PARK)], "Парковая улица (западный отрезок)", 2033,
       why="открывается с Западным проспектом (2033), на котором кончается")
street("s_park", "district_transport", [(RB_W[0], Z_PARK), (ATT["NW"][0], Z_PARK), (ATT["Nw"][0], Z_PARK),
                                        (ATT["Nc"][0], Z_PARK), (ATT["Ne"][0], Z_PARK), (-3232.0, Z_PARK), (EAST_X, Z_PARK),
                                        (-2960.0, Z_PARK), (-2700.0, Z_PARK), (DUB_X, Z_PARK)], "Парковая улица", 2029,
       why="открывается в 2029 вместе с Iconic (квартиры квартала keep — с 2029): подъезд к детсадам kg_gate_4, kg_gate_5, школе «Сити» и поликлинике у парка, которые открываются тогда же")
street("s_north", "arterial_regulated", [P_NORTH_W, (-3501.0, Z_NORTH), (-3232.0, Z_NORTH), (EAST_X, Z_NORTH),
                                         (-2700.0, Z_NORTH), (DUB_X, Z_NORTH), (-2300.0, Z_NORTH)], "Северная улица", 2033,
       axis="ax_north", why="схема ax_north (2032) кончается на Западном проспекте (2033): открывается вместе с ним; к востоку от "
                            "дублёра — к развязке А-3 × А-19 (уровень 2, стык на краю area)")
street("s_nw", "local", [ATT["NW"], (ATT["NW"][0], Z_19040), (ATT["NW"][0], Z_PARK)], "северо-западная улица", 2029,
       why="открывается в 2029 вместе с Iconic (квартиры квартала keep — с 2029): подъезд к детсадам kg_gate_4, kg_gate_5, школе «Сити» и поликлинике у парка, которые открываются тогда же")
street("s_nw2", "local", [ATT["Nw"], (ATT["Nw"][0], Z_19040), (ATT["Nw"][0], Z_PARK)], "улица N-запад", 2029,
       why="открывается в 2029 вместе с Iconic (квартиры квартала keep — с 2029): подъезд к детсадам kg_gate_4, kg_gate_5, школе «Сити» и поликлинике у парка, которые открываются тогда же")
street("s_boulevard", "boulevard", [ATT["Nc"], (ATT["Nc"][0], Z_19040), (ATT["Nc"][0], Z_PARK)], "Бульвар Gate", 2029,
       axis="ax_boulevard", profile={"green_w": 24.0, "note_ru": "зелёная полоса по оси ≥ 18 м, проезды по сторонам — местные"},
       why="схема ax_boulevard: от северного входа квартала к парку; концы — площадь у входа и Парковая улица; открывается в 2029 вместе с Iconic (квартиры квартала keep — с 2029): подъезд к детсадам kg_gate_4, kg_gate_5, школе «Сити» и поликлинике у парка, которые открываются тогда же")
street("s_park_walk", "pedestrian_street", [(ATT["Nc"][0], Z_PARK), (ATT["Nc"][0], Z_NORTH)], "аллея Центрального парка", 2033,
       axis="ax_boulevard", why="продолжение бульвара через Центральный парк до Северной улицы (регулируемый переход)")
street("s_ne", "local", [ATT["Ne"], (ATT["Ne"][0], Z_19040), (ATT["Ne"][0], Z_PARK)], "улица N-восток", 2029,
       why="открывается в 2029 вместе с Iconic (квартиры квартала keep — с 2029): подъезд к детсадам kg_gate_4, kg_gate_5, школе «Сити» и поликлинике у парка, которые открываются тогда же")
street("s_19040", "local", [(RB_W[0], Z_19040), (ATT["NW"][0], Z_19040), (ATT["Nw"][0], Z_19040), (ATT["Nc"][0], Z_19040),
                            (ATT["Ne"][0], Z_19040), (-3232.0, Z_19040), (EAST_X, Z_19040)], "улица Сити-Северная", 2029,
       why="открывается в 2029 вместе с Iconic (квартиры квартала keep — с 2029): подъезд к детсадам kg_gate_4, kg_gate_5, школе «Сити» и поликлинике у парка, которые открываются тогда же")
street("s_x3232", "local", [(-3232.0, Z_19040), (-3232.0, Z_PARK), (-3232.0, Z_NORTH)], "Парковая восточная улица", 2033)
street("s_x2960", "local", [(-2960.0, Z_E1), (-2960.0, Z_AVE), (-2960.0, Z_E4), on_line(BK, x=-2960.0)], "улица L7", 2029)
street("s_x2960_n", "local", [(-2960.0, Z_PARK), (-2960.0, Z_GO), (-2960.0, Z_E1)], "улица L7 (северный отрезок)", 2031,
       why="открывается с улицами делового квартала Griffin (2031)")
street("s_x2960_nn", "local", [(-2960.0, Z_NORTH), (-2960.0, Z_PARK)], "улица L7 (у школы «Парк»)", 2033,
       why="делит квартал 410 × 380 м у парка: проезды к домам и детсаду короче 150 м (правило 12); открывается с Северной улицей")
street("s_x2700", "local", [(-2700.0, Z_E1), (-2700.0, Z_AVE), (-2700.0, Z_E4), on_line(BK, x=-2700.0)], "Логистическая улица", 2029,
       why="западная граница участка Griffin; грузовой подъезд — с дублёра")
street("s_x2700_n", "local", [(-2700.0, Z_PARK), (-2700.0, Z_GO), (-2700.0, Z_E1)], "Логистическая улица (северный отрезок)", 2031,
       why="открывается с улицами делового квартала Griffin (2031)")
street("s_x2700_nn", "local", [(-2700.0, Z_NORTH), (-2700.0, Z_PARK)], "Логистическая улица (у парка)", 2033,
       why="открывается с Северной улицей (2033), на которой кончается")
street("s_x2520_nn", "local", [(-2520.0, Z_NORTH), (-2520.0, Z_PARK)], "улица у детских садов", 2033,
       why="делит квартал 350 × 380 м у дублёра: проезды короче 150 м (правило 12); открывается с Северной улицей")
street("s_go_mid", "local", [(-2960.0, Z_GO), (-2700.0, Z_GO)], "улица делового квартала Griffin", 2031,
       why="делит квартал 260 × 420 м: каждое здание в 25 м от проезжей части (правило 12); открывается с улицами L7 и "
           "Логистической (2031)")
street("s_x2520", "local", [CORNER, (-2520.0, Z_E4), (-2520.0, Z_AVE)], "улица у дублёра", 2028,
       why="вместе с южным отрезком дублёра и Проспектом Ворот (2028): кольцо у поворота не остаётся тупиком")
GRIF_R, GRIF_C = 16.0, (-2420.0, -19100.0)       # turning ring at the КПП: centre-line radius 16 m (island Ø 25 m ≥ 16 m)
_ring = [(GRIF_C[0] + GRIF_R * math.cos(math.radians(a)), GRIF_C[1] + GRIF_R * math.sin(math.radians(a))) for a in range(0, 181, 15)]
street("s_griffin_in", "industrial", [(DUB_X, -19100.0), _ring[0]], "въезд Griffin Logopark (к КПП, с разворотным кольцом)", 2027,
       why="грузовой въезд логопарка прямо с дублёра (не через жилые улицы): промышленная улица до КПП с разворотным кольцом "
           "(fire_access.turning_ring_m: островок ≥ 16 м; тупик промышленной улицы правило 5 не допускает)")
# the ring is one closed one-way street (anticlockwise seen from above, as a roundabout: north half east → west past the КПП,
# south half back west → east), so every truck that comes to the gate and leaves runs round all of it (tester r2 item 72: its
# south half carried no cars both ways). One street: gen_network took two halves meeting at the entry for the two carriageways
# of one road and ran the entry 32 m on across the island
street("s_griffin_ring", "industrial", [(GRIF_C[0] + GRIF_R * math.cos(math.radians(a)), GRIF_C[1] + GRIF_R * math.sin(math.radians(a)))
                                        for a in range(0, 361, 15)],
       "разворотное кольцо у КПП Griffin", 2027, oneway=True, profile={"oneway": True},
       why="разворотное кольцо у КПП логопарка, одностороннее движение против часовой стрелки (как на кольце): к КПП по северной "
           "половине, обратно к въезду по южной; грузовики разворачиваются, не въезжая на территорию")

# South of БАКАД: Южный проезд (keeps the existing building with street access), ТПУ streets
ZS = T_S[1]
street("s_south_link", "district_transport", [T_S, (-4080.0, ZS), HOOK_T, (-4520.0, ZS), (-4680.0, ZS)],
       "Южный проезд", 2033,
       why="западный луч южного узла развязки: малоэтажные дома, подъезд к существующему строению, связь с западом (twin)")
street("s_barn_drive", "local_secondary", [(-4080.0, ZS), (-4080.0, -20118.0)], "подъезд к существующему строению", 2033,
       why="строение (Microsoft ML Buildings 9fd2f313…, 2 628 м²) остаётся, подъезд с Южного проезда")
TPU_W = (-3102.0, -20311.0)                    # end of the village service road OSM 531450dd
Z_TPU_S = -20640.0
TPU_LOOP = fillet([on_line(EAST, z=-20330.0), (-2700.0, -20330.0), (-2640.0, -20330.0), (-2640.0, Z_TPU_S),
                   on_line(EAST, z=Z_TPU_S)], 30)
street("s_tpu1", "district_transport", [TPU_W] + TPU_LOOP, "улица ТПУ", 2030,
       why="связь села (проезд OSM 531450dd) с ТПУ и Восточной; за Восточной — кольцевой проезд ТПУ вокруг станции "
           "агломерационной ж/д (автобусы, такси, P+R) с выездом обратно на Восточную: тупика нет; открывается в 2030 вместе со станцией ТПУ (реестр agglo_rail_station_1, ГП727: 2030)")

# ===================================================================================================== nodes
STREET = {s["id"]: s for s in STREETS}


def end(sid, which):
    p = STREET[sid]["line"][0 if which == 0 else -1]
    return p[0], p[1]


# new interchange: partial cloverleaf B2 (exit loops beyond the structure in NW and SE; the SW quadrant with the existing
# building 9fd2f313 stays free); the template builds every ramp
wb_ids = [s["id"] for s in STREETS if s["source"].endswith("27df9cd9-") or s["id"].startswith("k_27df9cd9")]
eb_ids = [s["id"] for s in STREETS if s["id"].startswith("k_6035cf98")]
node("ic_west_bakad", IC_W[0], IC_W[1], "partial_cloverleaf", ["s_west_ave", wb_ids[0], eb_ids[0]],
     major=wb_ids[0], major_pair=eb_ids[0], upper="minor", variant="B", quadrants=["nw", "se"],
     why_ru="неполный клеверный лист B2 (разрешён для скоростной × магистральной регулируемой, node_matrix): петли съездов за "
            "путепроводом в СЗ и ЮВ квадрантах, въезды — прямыми съездами там же; ЮЗ квадрант (существующее строение 9fd2f313, "
            "Microsoft ML, 2 628 м²) свободен; ромб без ЮЗ съезда терял бы съезд с БАКАД (на восток), а ручной съезд к Южному "
            "проезду не вмещал нормативную полосу торможения; до развязки А-3 × БАКАД 1,72 км (норма ≥ 1,6)")
node("n_term_s", *T_S, "crossing_signal", ["s_west_ave", "s_west_ave_s", "s_south_link"])
node("n_barn", -4080.0, ZS, "crossing", ["s_south_link", "s_barn_drive"])
node("n_barn_end", -4080.0, -20118.0, "end", ["s_barn_drive"], why_ru="подъезд к строению, разворот у ворот")
node("n_ave_w", AVE_X, Z_AVE, "crossing_signal", ["s_west_ave", "s_ave_w", "s_ave_w_west"])
node("n_w1", AVE_X, ATT["W1"][1], "right_in_right_out", ["s_west_ave", "s_w1"],
     why_ru="166 м до светофора у Проспекта Ворот: только правые повороты")
node("n_park_w", AVE_X, Z_PARK, "crossing_signal", ["s_west_ave", "s_park_w"])
node("n_north_w", *P_NORTH_W, "crossing_signal", ["s_west_ave", "s_north"])
node("n_rb_west", *RB_W, "roundabout", ["s_ave_w", "s_w2", "s_w3", "s_west_st", "s_bakad_st"], r=22.0,
     name_ru="Западная площадь")
node("n_w1_west", RB_W[0], ATT["W1"][1], "crossing", ["s_w1", "s_west_st"])
node("n_w4", RB_W[0], ATT["W4"][1], "crossing", ["s_bakad_st", "s_w4"])
node("n_sw", *P_BK_SW, "crossing", ["s_bakad_st", "s_sw"])
node("n_swt", ATT["SW"][0], ATT["SWt"][1], "crossing", ["s_sw", "s_swt"])
node("n_sw2", *P_BK_Sw, "crossing", ["s_bakad_st", "s_sw2"])
node("n_se", *P_BK_Se, "crossing", ["s_bakad_st", "s_se", "s_ped_bridge"])
node("n_ped_s", -3350.0, -20137.0, "crossing", ["s_ped_bridge"], why_ru="спуск моста у проезда села OSM 7c663bbc")
node("n_east_bk", *P_EAST_BK, "crossing_signal", ["s_east_m", "s_east_s", "s_bakad_st"], lrt="elevated_above")
node("ic_east_bakad", *on_line(EAST, z=(zw + ze) / 2), "grade_separation", ["s_east_s", wb_ids[0], eb_ids[0]],
     upper="minor", why_ru="Восточная улица и эстакада ЛРТ над БАКАД без съездов")
node("n_corner", *CORNER, "roundabout", ["s_bakad_st", "s_dubler_s", "s_x2520"], r=20.0)
node("n_x2960_bk", *on_line(BK, x=-2960.0), "crossing", ["s_bakad_st", "s_x2960"])
node("n_x2700_bk", *on_line(BK, x=-2700.0), "crossing", ["s_bakad_st", "s_x2700"])
for zz, nm, typ in ((Z_NORTH, "north", "crossing_signal"), (Z_PARK, "park", "crossing_signal"), (Z_19040, "19040", "crossing_signal"),
                    (Z_E1, "e1", "crossing_signal"), (Z_AVE, "ave", "crossing_signal"), (Z_E4, "e4", "crossing_signal")):
    sid = {"north": "s_north", "park": "s_park", "19040": "s_19040", "e1": "s_e1", "ave": "s_ave", "e4": "s_e4"}[nm]
    node(f"n_east_{nm}", EAST_X, zz, typ, ["s_east_m" if zz < Z_AVE else "s_east", sid], lrt="level_crossing_signal")
node("n_east_ave", EAST_X, Z_AVE, "crossing_signal", ["s_east_m", "s_gate_sq"])
node("n_set", EAST_X - 25.0, ATT["SEt"][1], "crossing", ["s_east_m", "s_set"],
     why_ru="примыкание справа к западной проезжей части; пути ЛРТ в разделительной полосе уже на подъёме — пересечения нет")
for x in (-2960.0, -2700.0, -2520.0):
    sid = {-2960.0: "s_x2960", -2700.0: "s_x2700", -2520.0: "s_x2520"}[x]
    node(f"n_ave_{int(-x)}", x, Z_AVE, "crossing_signal" if x == -2700.0 else "right_in_right_out", ["s_ave", sid])
    node(f"n_e4_{int(-x)}", x, Z_E4, "crossing", ["s_e4", sid])
for x in (-2960.0, -2700.0):
    sid = "s_x2960" if x == -2960.0 else "s_x2700"
    node(f"n_e1_{int(-x)}", x, Z_E1, "crossing", ["s_e1", sid, sid + "_n"])
    node(f"n_park_{int(-x)}", x, Z_PARK, "crossing", ["s_park", sid + "_n", sid + "_nn"])
    node(f"n_go_{int(-x)}", x, Z_GO, "crossing", [sid + "_n", "s_go_mid"])
    node(f"n_north_{int(-x)}", x, Z_NORTH, "right_in_right_out", ["s_north", sid + "_nn"])
node("n_park_2520", -2520.0, Z_PARK, "crossing", ["s_park", "s_x2520_nn"])
node("n_north_2520", -2520.0, Z_NORTH, "right_in_right_out", ["s_north", "s_x2520_nn"])
node("n_dub_e4", DUB_X, Z_E4, "crossing_signal", ["s_dubler_s", "s_e4"])
node("n_dub_ave", DUB_X, Z_AVE, "crossing_signal", ["s_dubler_s", "s_ave"])
node("n_dub_e1", DUB_X, Z_E1, "crossing", ["s_dubler_s", "s_e1"])
node("n_dub_griffin", DUB_X, -19100.0, "crossing", ["s_dubler", "s_dubler_s", "s_griffin_in"])
# no spec node where the entry meets the ring: with one, gen_network looks 40 m on (snap_street_ends, at-grade end) and runs the
# entry across the island to the ring's far side, 32 m off (it takes the ring's two sides for a divided road's carriageways)
node("n_dub_park", DUB_X, Z_PARK, "crossing_signal", ["s_dubler", "s_park"])
node("n_dub_north", DUB_X, Z_NORTH, "crossing_signal", ["s_dubler", "s_north"])
for x, sid in ((RB_W[0], "s_west_st"), (ATT["NW"][0], "s_nw"), (ATT["Nw"][0], "s_nw2"), (ATT["Nc"][0], "s_boulevard"),
               (ATT["Ne"][0], "s_ne"), (-3232.0, "s_x3232")):
    if sid != "s_x3232":
        node(f"n_park_{sid}", x, Z_PARK, "crossing", ["s_park", sid] + (["s_park_w"] if sid == "s_west_st" else []))
    node(f"n_19040_{sid}", x, Z_19040, "crossing", ["s_19040", sid])
node("n_park_s_x3232", -3232.0, Z_PARK, "crossing", ["s_park", "s_x3232"])
node("n_park_s_park_walk", ATT["Nc"][0], Z_PARK, "crossing", ["s_park_walk"])
node("n_north_walk", ATT["Nc"][0], Z_NORTH, "crossing_signal", ["s_north", "s_park_walk"], why_ru="регулируемый пешеходный переход")
node("n_north_3232", -3232.0, Z_NORTH, "right_in_right_out", ["s_north", "s_x3232"])
node("n_tpu_w", *TPU_W, "crossing", ["s_tpu1"], why_ru="стык с проездом села OSM 531450dd")
node("n_tpu_east", *on_line(EAST, z=-20330.0), "crossing_signal", ["s_tpu1", "s_east_s"])
node("n_tpu_s", *on_line(EAST, z=Z_TPU_S), "crossing", ["s_tpu1", "s_east_s"],
     why_ru="выезд кольцевого проезда ТПУ на Восточную (под эстакадой ЛРТ)")
node("n_ave_w_end", -4005.0, Z_AVE, "joint", ["s_ave_w_west"])

# keep attach nodes (street ends at the quarter's rim)
for k, (x, z) in ATT.items():
    sids = [s["id"] for s in STREETS if s["source"] == "new" and (tuple(s["line"][0]) == (x, z) or tuple(s["line"][-1]) == (x, z))]
    node(f"n_keep_{k}", x, z, "joint", sids, keep="k_gate_district", what_ru="улица квартала Gate District (gate_roads.json)")
node("n_gate_sq_keep", -3166.0, Z_AVE, "joint", ["s_gate_sq"], keep="k_gate_district", what_ru="площадь перед фасадом Iconic")

# ===================================================================================================== keep_existing nodes and edge joints
TWIN = C.twin_roads()
TW_IN = C.twin_edges_in(AREA.buffer(10), TWIN)
EDGE = AREA.exterior
cuts = []
for i, e, l in TW_IN:
    x = l.intersection(EDGE)
    for p in ([x] if x.geom_type == "Point" else [q for q in getattr(x, "geoms", []) if q.geom_type == "Point"]):
        cuts.append({"i": i, "c": e["c"], "x": p.x, "z": p.y})

EDGE_JOINTS = []
used_cuts = set()


def snap_key(p):
    return (round(p[0], 1), round(p[1], 1))


ends_at = {}
for s in STREETS:
    for k in (0, -1):
        ends_at.setdefault(snap_key(s["line"][k]), []).append((s["id"], k))
node_at = {snap_key((n["x"], n["z"])): n for n in NODES.values()}


def find_node(p, tol=1.5):
    k = snap_key(p)
    if k in node_at:
        return node_at[k]
    best = None
    for n in NODES.values():
        d = math.hypot(n["x"] - p[0], n["z"] - p[1])
        if d <= tol and (best is None or d < best[0]):
            best = (d, n)
    return best[1] if best else None


ej_n = 0
for key, lst in sorted(ends_at.items()):
    p = Point(key)
    on_edge = p.distance(EDGE) < 1.0
    n = find_node(key)
    if on_edge:
        s0 = STREET[lst[0][0]]
        src = s0["source"]
        osm_id = src.split(":", 1)[1] if src.startswith("keep_existing:") else None
        cand = sorted(cuts, key=lambda c: math.hypot(c["x"] - key[0], c["z"] - key[1]))
        cut = next((c for c in cand if (c["i"], round(c["x"]), round(c["z"])) not in used_cuts), None)
        gap = math.hypot(cut["x"] - key[0], cut["z"] - key[1]) if cut else 1e9
        ej_n += 1
        ej = {"id": f"ej{ej_n:02d}", "x": key[0], "z": key[1], "class": s0["class"],
              "connects": ("osm:" + osm_id) if osm_id else (f"twin_edge:{cut['i']}" if cut else "twin_edge:none"),
              "street": s0["id"]}
        if cut and gap <= 80.0:
            used_cuts.add((cut["i"], round(cut["x"]), round(cut["z"])))
            if osm_id:
                ej["twin_edge"] = cut["i"]
            ej["twin_gap_m"] = round(gap, 1)
        elif not osm_id:
            ej["twin_gap_m"] = round(gap, 1) if cut else None
        EDGE_JOINTS.append(ej)
        if n is None:
            node(ej["id"], key[0], key[1], "joint", [x[0] for x in lst], edge_joint=ej["id"])
        else:
            n["params"]["edge_joint"] = ej["id"]
            if n["type"] != "joint":
                n["params"]["note_ru"] = "узел на краю area"
        node_at[key] = NODES.get(ej["id"]) or n
        continue
    if n is not None:
        for sid, _ in lst:
            if sid not in n["streets"]:
                n["streets"].append(sid)
        continue
    # unnamed ends: keep_existing network (interchange internals, village junctions and dead ends)
    sids = [x[0] for x in lst]
    cls = {STREET[s]["class"] for s in sids}
    # also count streets passing through this point (T-junction onto the middle of another street)
    thru = [s["id"] for s in STREETS if s["id"] not in sids and LineString(s["line"]).distance(p) < 1.0]
    allsids = sids + thru
    if cls & {"expressway", "ramp"}:
        incoming = sum(1 for sid, k in lst if k == -1) + len(thru)
        outgoing = sum(1 for sid, k in lst if k == 0) + len(thru)
        typ = "diverge" if outgoing > incoming else ("merge" if incoming > outgoing else "ic")
        node(f"k_n{len(NODES):03d}", key[0], key[1], typ, allsids, ic="ic_a3_bakad")
    elif len(allsids) == 1:
        node(f"v_end{len(NODES):03d}", key[0], key[1], "end", allsids, why_ru="тупик существующей улицы села (OSM)")
    else:
        node(f"v_n{len(NODES):03d}", key[0], key[1], "crossing", allsids)
    node_at[key] = list(NODES.values())[-1]

# the existing cloverleaf as one interchange node (keep_existing)
ic_streets = [s["id"] for s in STREETS if s["id"].startswith("k_") and s["class"] == "expressway"]
node("ic_a3_bakad", -2270.0, -20315.0, "cloverleaf", ic_streets, keep_existing=True, registry_id="interchange_a3_bakad",
     osm_ids=[s["source"].split(":", 1)[1] for s in STREETS if s["id"].startswith("k_")],
     why_ru="существующий клевер с распределительными дорогами по А-3 (OSM/Overture), остаётся как есть; путепроводы БАКАД над А-3",
     # tester r2 item 71: the loop k_92670eef → k_d080e3ad → k_dc8f8e80 (А-3 S → БАКАД E) carries 4.3–5.7k veh/h; layout kept
     ramps={"А-3 S → БАКАД E": {"lanes": 2, "from_year": 2035,
                                "why_ru": "реконструкция петли: спрос выше 1 200 авт./ч (норма второй полосы), модель qTwin"}})

# twin roads cut by the area edge that no trial street continues: listed so merge can trim them (log only)
for c in cuts:
    if (c["i"], round(c["x"]), round(c["z"])) in used_cuts:
        continue
    ej_n += 1
    EDGE_JOINTS.append({"id": f"ej{ej_n:02d}", "x": round(c["x"], 1), "z": round(c["z"], 1),
                        "class": {"highway": "expressway", "ring": "expressway", "main": "district_transport"}.get(c["c"], "local"),
                        "connects": f"twin_edge:{c['i']}", "street": None,
                        "note_ru": "улица двойника обрезана краем area, пробная сеть её не продолжает (уровень 2 перерисует)"})

# ===================================================================================================== LRT v1
LRT_LINE = [p for p in EAST]
L_LRT = LineString(LRT_LINE)
z_ramp = -19720.0
lrt = {
    "lines": [{
        "id": "lrt_gate_golden", "name_ru": "ЛРТ Gate – Golden (участок пробной зоны)",
        "line": [[round(x, 1), round(z, 1)] for x, z in LRT_LINE],
        "sections": [{"from": list(map(lambda v: round(v, 1), LRT_LINE[0])), "to": [EAST_X, z_ramp], "kind": "ground"},
                     {"from": [EAST_X, z_ramp], "to": list(map(lambda v: round(v, 1), LRT_LINE[-1])), "kind": "elevated"}],
        "stations": [
            {"id": "st_park", "name_ru": "Центральный парк", "x": EAST_X, "z": -18710.0,
             "between": ["s_park", "s_north"], "kind": "ground"},
            {"id": "st_iconic", "name_ru": "Iconic", "x": EAST_X, "z": -19578.0, "between": ["s_ave", "s_e4"], "kind": "ground"},
            {"id": "st_tpu", "name_ru": "ТПУ Gate (А-3 × БАКАД)", "x": round(on_line(EAST, z=-20462.0)[0], 1), "z": -20462.0,
             "between": ["s_tpu1", "v_eb195f5c"], "kind": "elevated"}],
        "ends": [],
        "joints": [{"edge_joint": None, "x": round(LRT_LINE[0][0], 1), "z": round(LRT_LINE[0][1], 1), "to": "lrt_v0 (север, Golden)"},
                   {"edge_joint": None, "x": round(LRT_LINE[-1][0], 1), "z": round(LRT_LINE[-1][1], 1), "to": "lrt_v0 (юг, Gate City)"}],
        "years": Y4(2031),
        "why": "ось схемы (x −3100) в разделительной полосе Восточной улицы; на земле с регулируемыми переездами до z −19720, "
               "далее подъём ≤ 6 % и эстакада над улицей вдоль БАКАД, БАКАД и улицей ТПУ; станции между поперечными улицами; "
               "концы линии — депо и конечные — вне пробной зоны (ends пуст, см. joints)"}],
    "depots": []}

# ===================================================================================================== keep
keep = [{"id": "k_gate_district", "what_ru": "квартал Gate District с Iconic Complex (кольцо, овальная площадь, дворы) — "
                                             "данные квартала как есть, сдвиг Δ = (−330, −420)",
         "polygon": KEEP_PTS, "registry_id": "iconic_complex",
         "attach": [{"street_id": NODES[f"n_keep_{k}"]["streets"][0], "x": x, "z": z, "stub": k} for k, (x, z) in ATT.items()]
         + [{"street_id": "s_gate_sq", "x": -3166.0, "z": Z_AVE, "stub": "E-forecourt"}],
         "source": "Resources/Landmarks/gate_district.bytes (круг земли квартала r %.1f м — по нему Unity режет землю модели, "
                   "IconicDistrict.AreaRadius; маска %.1f га; плюс %d здание модели за кругом — его стены и парапет + 0,5 м, %.0f м²) и "
                   "Resources/Film/Traffic/gate_roads.json, мир = (−3500 − z_лок, −19500 + x_лок)"
                   % (KEEP_R_MASK, KEEP_AREA / 1e4, len(KEEP_BULGES), sum(g.area for g in KEEP_BULGES)),
         "years": C.EXISTING}]

# ===================================================================================================== red lines (land_util)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
import land_util as LU  # noqa: E402  (w44, read only: street profile widths from norms.json, storey heights)

_LN = LU.Norms()
_RW = {}


def red_w(st):
    """Red-line width of a spec street the way the land tools cut blocks (norms.street_profiles; boulevard green strip)."""
    if st["class"] not in _RW:
        _RW[st["class"]] = float(LU.profile_from_norms(_LN, st["class"])["red_line_w"])
    w = _RW[st["class"]]
    g = float((st.get("profile") or {}).get("green_w") or 0.0)
    return max(w, g + 6.0) if g else w


RED = unary_union([LineString(st["line"]).buffer(red_w(st) / 2.0) for st in STREETS if len(st["line"]) > 1])
RED_FLAT = unary_union([LineString(st["line"]).buffer(red_w(st) / 2.0, cap_style=2) for st in STREETS if len(st["line"]) > 1])
# fire gaps (w44, rule 12): two buildings over 28 m stand ≥ 22 m apart (fire_access.distance_to_wall_m, width_min_m), so in a
# dense zone about half of them stay at 28 m: a zone's lowest floors allow a 28 m building (storey heights: land_util.floor_heights,
# the twin's medians), and the City zones keep the jobs their blocks hold with the gaps under the 50 m cap (gen_buildings, integ
# 28b3071: b_cbd 782 948 of 837 114 m², b_cbd_e 569 440 of 637 148 m² at 330 and 320 jobs/ha) — Gate v1.1
FH_M = LU.floor_heights()
LO_BUS = int(28.0 // FH_M.get("business", 4.43))          # 6
LO_RES = int(28.0 // FH_M.get("res_mid", 3.6))            # 7
FIRE_GAP = ("пожарные разрывы 22 м между зданиями выше 28 м (fire_access.distance_to_wall_m, width_min_m): из двух близких "
            "зданий выше 28 м поднимается одно, второе остаётся до 28 м — нижняя этажность %d × %.2f м ≤ 28 м (land_util.floor_heights)")

# ===================================================================================================== zones
ZONES = []
taken = Polygon()


def simple_parts(g, min_area=300.0):
    """Polygons without holes (the spec polygon format has no holes): split by a vertical line through each hole."""
    out = []
    stack = [g]
    while stack:
        q = stack.pop().buffer(0)
        if q.is_empty:
            continue
        if q.geom_type in ("MultiPolygon", "GeometryCollection"):
            stack += [p for p in q.geoms if p.geom_type == "Polygon"]
            continue
        if q.area < min_area:
            continue
        if not q.interiors:
            out.append(q)
            continue
        hx = Polygon(q.interiors[0]).representative_point().x
        x0, z0, x1, z1 = q.bounds
        stack += [q.intersection(box(x0 - 1, z0 - 1, hx, z1 + 1)), q.intersection(box(hx, z0 - 1, x1 + 1, z1 + 1))]
    return sorted(out, key=lambda p: -p.area)


def zone(zid, use, name_ru, geom, years, rules, why, density=None, max_parts=1):
    """Zone = geom ∩ area minus the zones already placed; parts beyond max_parts are left to the remainder."""
    global taken
    g = geom.buffer(0).intersection(AREA).difference(taken).buffer(0)
    parts = simple_parts(g, 500.0)[:max_parts]
    made = []
    for k, q in enumerate(parts):
        taken = taken.union(q)
        z = {"id": zid if k == 0 else f"{zid}_{k + 1}", "use": use, "name_ru": name_ru, "polygon": poly_pts(q),
             "years": years, "rules": rules, "why": why, "area_ha": round(q.area / 1e4, 2)}
        if density:
            z["density"] = density
        ZONES.append(z)
        made.append(z)
    return made


def rules(floors, cap, far, block, split, park_type, homes, jobs, setback=6.0, per_home=1.0, office=None, retail=None):
    """parking.per_home 1.0: residential.parking_per_apartment, class III min (С08-11); office / retail parking None while
    malls.parking_office / parking_mall are not_verified (CONTRACT §8 defaults)."""
    return {"floors": floors, "height_cap_m": cap, "far": far, "block_side_m": block, "setback_m": setback,
            "lot_split": split, "parking": {"per_home": per_home, "per_100m2_office": office, "per_100m2_retail": retail,
                                            "type": park_type}, "homes_per_ha": homes, "jobs_per_ha": jobs}


zone("z_gate_district", "mixed_centre", "Квартал Gate District с Iconic (keep)", KEEP_POLY, [2026, 2032],
     {"lot_split": "none", "floors": [3, 56], "height_cap_m": 272, "far": None, "block_side_m": None, "setback_m": None,
      "parking": {"type": "underground"}, "homes_per_ha": 104, "jobs_per_ha": 202},
     "keep: квартал не генерируется; числа — из схемы v0 (z_gate_district)")
v_village = [z for z in GATE0["zones"] if z["id"] == "v_yntymak_5"][0]
zone("v_yntymak", "village_existing", "Село Ынтымақ (существующее, северо-восточная часть)", Polygon(v_village["polygon"]),
     [2025, 2025], {"lot_split": "houses", "floors": [1, 2], "height_cap_m": 9, "far": 0.25, "block_side_m": None,
                    "setback_m": 3, "parking": {"per_home": 1.0, "type": "surface"}, "homes_per_ha": None, "jobs_per_ha": None},
     "существующие дома и улицы села остаются как есть (OSM); новые улицы обходят", {"floors_typical": 1, "far": 0.25})
# central park: Парковая улица — проспект — Северная улица — Парковая восточная улица
park_c = Polygon([(AVE_X + 25, Z_PARK + 15), (-3232 - 8, Z_PARK + 15), (-3232 - 8, Z_NORTH - 25), (P_NORTH_W[0] + 30, Z_NORTH - 25)]
                 + [(x + 30, z) for x, z in reversed(ave_line) if Z_NORTH - 25 > z > Z_PARK + 15])
zone("p_central", "park", "Центральный парк", park_c, [2030, 2032], {"lot_split": "none"},
     "схема p_central (16,3 га) расширена до улиц: проспект (запад), Парковая, Северная, Парковая восточная; школа у южного края")
# school + kindergartens zone inside the park edge are lots (objects); CBD ring
def cell(bounds, cuts, seed):
    """Block cell: bounds minus street corridors (line, half-width + setback); the piece holding seed."""
    g = bounds
    for ln, w in cuts:
        g = g.difference(LineString(ln).buffer(w, cap_style=2, join_style=2))
    parts = list(g.geoms) if hasattr(g, "geoms") else [g]
    return min(parts, key=lambda q: q.distance(Point(seed))).buffer(0)


cbd_box = cell(Polygon([(AVE_X + 25, Z_PARK - 15), (-3000.0, Z_PARK - 15), (-3000.0, on_line(BK, x=-3000.0)[1] + 12)]
                       + [(x, z + 12) for x, z in reversed(BK) if x < -3000.0] + [(AVE_X + 25, T_N[1] + 40)]),
               [(EAST, 25.0), (BK, 12.0)], (-3300.0, -19700.0))
cbd_n = cbd_box.intersection(rect(ATT["NW"][0] - 8, Z_PARK - 15, ATT["Ne"][0] + 8, ATT["Nc"][1] - 0)).difference(KEEP_POLY)
zone("b_cbd_n", "business", "Сити-Север (офисы и квартиры у парка)", cbd_n, [2031, 2038],
     rules([LO_BUS, 14], 50, 3.0, [110, 150], "towers", "underground", 42, 155),
     "схема b_cbd_1/2 (FAR 4,0): квартиры в Сити — только у парка, в 500 м от школы «Сити» и 300 м от детсадов; при потолке "
     "50 м (кольцевой пожарный проезд не нужен) кварталы вмещают ≈ половину плотности схемы: 42 кв./га и 155 мест/га; "
     + FIRE_GAP % (LO_BUS, FH_M.get("business", 4.43)))
zone("b_cbd", "business", "Сити (деловое кольцо вокруг Iconic)", cbd_box.difference(KEEP_POLY), [2029, 2036],
     rules([LO_BUS, 11], 50, 2.6, [110, 150], "towers", "underground", 0, 305),
     "схема b_cbd_1/2: плотный деловой центр вокруг Iconic вдоль осей и ЛРТ (правило Gate владельца); жильё здесь не ставим — "
     "шум проспекта и БАКАД; парковки только подземные; при потолке 50 м и пожарных разрывах 22 м кварталы вмещают "
     "305 мест/га (схема — 450; без разрывов — 330); " + FIRE_GAP % (LO_BUS, FH_M.get("business", 4.43)))
zone("b_cbd_e", "business", "Сити-Восток (у станции «Iconic» и L7)",
     cell(rect(EAST_X, -20010, -2700 + 8, Z_E1).union(rect(EAST_X + 25, Z_E1, -2960 + 8, Z_PARK - 15)),
          [(EAST, 25.0), (BK, 12.0)], (-2900.0, -19700.0)),
     [2029, 2035], rules([LO_BUS, 11], 50, 2.6, [110, 150], "towers", "underground", 0, 285),
     "схема b_cbd_2 + b_a3_strip (запад): у станции «Iconic», L7 — участок по правилу; при потолке 50 м и пожарных разрывах 22 м — "
     "285 мест/га (схема — 420; без разрывов — 320); " + FIRE_GAP % (LO_BUS, FH_M.get("business", 4.43)))
# utility lot of the twin's ПС 110/10 кВ «Gate-1» and Котельная «Gate-1» (StreamingAssets/twin/networks.json ps_gate_1, hb_gate_1:
# synthetic, at (−2712, −19047) in this business quarter, first stage 2030): the quarter's south-east corner, entered from улица Е1
# (2029) and Логистическая; offices and logistics round it, the nearest homes (r_high_ne) ≈ 300 m off (tester r2 items 58–60:
# the twin's plants stood on office lots and in red lines; w45 places them on these lots)
EN1 = rect(-2840.0, Z_E1, -2700.0 + 8, Z_E1 + 125.0)
UTIL_RULES = {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0}
zone("u_energy_gate_1", "utility", "ПС 110/10 кВ и котельная «Gate-1»", EN1, [2030, 2030], dict(UTIL_RULES),
     MODEL + ": участок ПС 110/10 кВ «Gate-1» и котельной «Gate-1» двойника (networks.json ps_gate_1, hb_gate_1, первая очередь "
             "2030; точка двойника (−2712, −19047) — в этом деловом квартале); въезд с улицы Е1 и Логистической, жилья ближе 300 м нет")
# CONTRACT §8 (w45): a utility zone names the twin's facilities it hosts. The twin's re-run numbers Gate-1 / Gate-2 by its own
# load centres (trial merge: «Gate-2» stands inside the trial area, «Gate-1» outside), so the zone names both pairs and w45's
# nearest-zone rule puts each on the nearer energy lot (in Gate: this one or u_energy_gate_2)
ENERGY_FAC = ["hb_gate_1", "ps_gate_1", "hb_gate_2", "ps_gate_2"]
ZONES[-1]["facilities"] = list(ENERGY_FAC)
zone("b_offices_griffin", "business", "Деловой квартал у Griffin", rect(-2960 + 8, Z_E1, -2700 + 8, Z_PARK - 15), [2030, 2036],
     rules([5, 11], 50, 2.0, [110, 150], "perimeter", "multi", 0, 250),
     "в схеме r_mid_rest_2 (жильё); заменено на офисы: в 2×СЗЗ логопарка и в секторе ветра 200°–295° (правило 15)")
zone("l_griffin", "logistics", "Griffin Logopark", rect(-2700 + 8, Z_E1 + 34, DUB_X - 15, Z_PARK - 15), [2026, 2027],
     {**rules([1, 1], 18, 0.8, [300, 450], "industrial", "multi", 0, 80, setback=10.0), "szz_class": "V"},
     "реестр griffin_logopark: 125 478 м² (у Griffin 125 421 м²), 600 / 1 000 рабочих мест, точность 500 м; участок 12,5 га у дублёра "
     "по точке реестра; одноэтажный склад ≈ 0,8 участка, 80 мест/га ≈ 1 000 мест (верхняя цифра реестра, полная мощность); "
     "стоянки — в паркинге (в Gate модельные стоянки под землёй или в паркингах); СЗЗ класса V (50 м): модель qTwin — склады и "
     "логистика готовых товаров без выбросов, наименьший класс szz.class_width_m (в szz.class_examples складов нет)",
     {"floors_typical": 1, "far": 0.8})
zone("b_strip", "business", "Деловой пояс у дублёра",
     cell(rect(-2700 + 8, -20040, -2300, Z_E1), [(BK, 12.0), (DUB, 15.0)], (-2550.0, -19700.0)), [2028, 2033],
     rules([6, 11], 50, 2.4, [110, 150], "perimeter", "multi", 0, 260),
     "схема b_a3_strip (FAR 2,6); жильё убрано: шум А-3/БАКАД, школа дальше 500 м за Проспектом Ворот")
zone("b_a3_edge", "business", "Полоса между дублёром и А-3", Polygon(
     [(DUB_X + 15, -18905), (-2205, -18905), (-2205, -19780), (DUB_X + 15, -19780)]), [2028, 2034],
     rules([3, 8], 35, 1.2, [110, 200], "rows", "multi", 0, 33, setback=10.0),
     "узкая полоса (130–215 м) у А-3: офисы, сервис, пожарное депо; жилья нет (≥ 50 м от проезжей части А-3); ряды зданий "
     "с отступом 10 м вмещают ≈ 33 места/га")
zone("p_a3_buffer", "park", "Зелёный буфер у границы к А-3", rect(-2205, -19780, -2100, -18905), [2028, 2032], {"lot_split": "none"},
     "полоса до границы пробной зоны (к А-3 в соседнем районе): глубже 150 м от дублёра проезды становятся тупиками "
     "длиннее нормы (fire_access.dead_end_max_m)")
zone("p_ne_sq", "park", "Сквер у дублёра (северо-восток)", rect(-2512, -18630, -2440, -18545), [2033, 2035], {"lot_split": "none"},
     "сквер 0,6 га у Северной улицы: дома у дублёра дальше 500 м от Центрального парка (правило 14, parks.square_or_playground)")
zone("r_high_ne", "residential_high", "Жилой район у Центрального парка", rect(-3232 + 8, Z_PARK + 15, DUB_X - 15, Z_NORTH - 25),
     [2032, 2040], rules([LO_RES, 14], 50, 1.8, [110, 150], "perimeter", "underground", 149, 30),
     "схема r_high_n (149 кв./га); подземные паркинги — центр Gate; " + FIRE_GAP % (LO_RES, FH_M.get("res_mid", 3.6)))
zone("u_tpu_stations", "utility", "Вокзалы ТПУ (ж/д и автобусы)", rect(-2930, -20590, -2680, -20352).union(rect(-3075, -20590, -2990, -20420)),
     [2030, 2031], {"lot_split": "none", "homes_per_ha": 0, "jobs_per_ha": 0},
     "участки станции агломерационной ж/д и автовокзала: транспорт, не офисная плотность (рабочие места вокзалов в цели не входят)",
     max_parts=2)
zone("p_tpu_sq", "park", "Сквер ТПУ у парка БАКАД", rect(-2760, -20322, -2580, -20240), [2031, 2034], {"lot_split": "none"},
     "полоса ≈ 75 м между кольцом ТПУ и парком БАКАД (востокнее паркинга): зданиям в глубине не хватает пожарного проезда "
     "(правило 12, 27–71 м до проезжей части), въезда с БАКАД нет; сквер и площадка ожидания у станции")
zone("b_tpu", "business", "ТПУ Gate (ж/д, ЛРТ, автобусы)", rect(-3085, -20690, -2580, -20240), [2031, 2036],
     rules([4, 6], 27, 2.0, [110, 150], "perimeter", "multi", 0, 200),
     "схема b_tpu; станция агломерационной ж/д вынесена ≥ 400 м от центра развязки А-3 × БАКАД (замечание w42); здания до 6 "
     "этажей (≤ 28 м): фасады у кольца ТПУ в ≈ 22 м от проезжей части, а пожарный проезд в 8–10 м от стены (выше 28 м) между "
     "кольцом и станцией не помещается")
zone("p_water", "park", "Долина ручья (у развязки А-3 × БАКАД)", Polygon([z for z in GATE0["zones"] if z["id"] == "p_water_6"][0]["polygon"]),
     [2025, 2030], {"lot_split": "none"}, "схема p_water_6")
bk_park = Polygon([(AVE_X + 25, T_N[1] + 40)] + [(x, z - 15) for x, z in BK if x <= CORNER[0] + 1]
                  + [(CORNER[0], z_wb(-2757) + 20 if CORNER[0] < -2757 else -20120)]
                  + [(x, z_wb(x) + 25) for x in np.arange(-2760, AVE_X + 24, -40.0)] + [(AVE_X + 25, z_wb(AVE_X + 25) + 25)])
zone("p_bakad", "park", "Парк БАКАД (с кабелем 220 кВ)", bk_park, [2027, 2030], {"lot_split": "none"},
     "схема p_bakad: зелёный буфер БАКАД, в нём кабель 220 кВ вместо ВЛ, пешеходный мост, эстакада ЛРТ, съезды развязки")
zone("p_west_buffer", "park", "Зелёный буфер развязки (северо-запад)", rect(-4680, -19790, AVE_X - 25, -19900).union(
     Polygon([(x, z_wb(x) + 25) for x in np.arange(-4680, AVE_X - 24, 40.0)] + [(AVE_X - 25, -19790), (-4680, -19790)])),
     [2033, 2036], {"lot_split": "none"}, "петля и въезд развязки (СЗ) и буфер ≥ 50 м от БАКАД; малоэтажное жильё схемы r_low_wb_2 здесь не помещается")
zone("r_low_sw", "residential_low", "Малоэтажные дома у Южного проезда", rect(HOOK_T[0] + 15, z_eb(-4100) - 50, AVE_X - 25, ZS - 15),
     [2034, 2044], rules([2, 4], 15, 0.4, [80, 150], "rows", "multi", 38, 3),
     "схема r_low_wb_1 (38 кв./га); блокированные дома рядами (lot_split rows): участок «houses» по C08 ≈ 500 м² с отступами "
     "6 м не вмещает дом глубиной 13 м; существующее строение остаётся в своём участке; стоянки — в паркинге (в Gate модельные "
     "стоянки под землёй или в паркингах)")
zone("p_south_edge", "park", "Озеленение у Южного проезда", rect(-4680, ZS - 15, AVE_X - 25, -20230), [2033, 2036], {"lot_split": "none"},
     "полоса ≈ 20 м между Южным проездом и южной границей пробной зоны: для домов мелко, деревья вдоль улицы")
zone("p_sw_buffer", "park", "Зелёный буфер БАКАД (юго-запад)", rect(-4680, z_eb(-4680) - 25, HOOK_T[0] + 15, ZS + 15),
     [2033, 2036], {"lot_split": "none"}, "буфер БАКАД (≥ 50 м до жилья); ЮЗ квадрант развязки без съездов")
zone("p_se_buffer", "park", "Зелёный буфер въезда (юго-восток)", Polygon([(AVE_X + 25, z_eb(AVE_X + 25) - 25), (-3830, z_eb(-3830) - 25),
                                                                         (-3830, -20140), (-3850, -20230), (AVE_X + 25, -20230)]),
     [2033, 2036], {"lot_split": "none"}, "въезд ромба (ЮВ) и буфер до домов села")
zone("u_hv_south", "utility", "Энергетический коридор (юго-восток)",
     Polygon([z for z in GATE0["zones"] if z["id"] == "u_hv_south_2"][0]["polygon"]), [2025, 2025], {"lot_split": "none"}, "схема u_hv_south_2")
# utility lot of the twin's ПС 220/110 кВ «Gate» (networks.json hv_gate: synthetic, «питающий центр района; связь с сетью 220 кВ
# KEGOC — модель», at (−2077, −20160) in the A-3 × БАКАД interchange, first stage 2026): beside the 220 kV corridor 92ca2130 /
# 74b9e818 west of A-3, entered from the existing street v_1335da7e (2025), which ended there at nothing (tester r2 items 37, 58)
HVG = rect(-2290.0, -20800.0, -2140.0, -20690.0)
zone("u_hv_gate", "utility", "ПС 220/110 кВ «Gate»", HVG, [2026, 2026], dict(UTIL_RULES),
     MODEL + ": участок ПС 220/110 кВ «Gate» двойника (networks.json hv_gate, первая очередь 2026) у коридора ВЛ 220 кВ 92ca2130 / "
             "74b9e818 западнее А-3, вне развязки; въезд с существующей улицы v_1335da7e")
ZONES[-1]["facility"] = "hv_gate"

# TPU plots (Gate v1.1, w44 round 2): registry plots up to the red lines of the streets they are entered from, never crossed by one.
# Bus station: the 85 × 170 m box was crossed by the existing village street v_eb195f5c and the red line of s_east_s (the lot came
# out 40 % short); the plot is the land between them, the TPU ring s_tpu1 and the village, cut from the north to 14 450 m².
RED_CLEAR = 0.05
ZB = {z["id"]: z for z in ZONES}


def zpoly(zid):
    return Polygon(ZB[zid]["polygon"]).buffer(0)


def zset(zid, g):
    q = max(simple_parts(g.buffer(0), 1.0), key=lambda p_: p_.area)
    ZB[zid]["polygon"] = poly_pts(q)
    ZB[zid]["area_ha"] = round(q.area / 1e4, 2)


def near_red(pt, r):
    return unary_union([LineString(x["line"]).buffer(red_w(x) / 2.0 + RED_CLEAR) for x in STREETS
                        if x["class"] not in ("expressway", "ramp") and len(x["line"]) > 1
                        and LineString(x["line"]).distance(Point(pt)) < r])


BUS_AT, BUS_M2 = Point(-3040.0, -20450.0), 14450.0
_av = box(-3110.0, -20620.0, -2900.0, -20330.0).difference(near_red(BUS_AT, 250.0)).difference(zpoly("v_yntymak").buffer(1.0))
_av = max([q for q in getattr(_av, "geoms", [_av]) if q.contains(BUS_AT)], key=lambda q: q.area)
_lo, _hi = _av.bounds[1], _av.bounds[3]
for _ in range(60):
    _mid = (_lo + _hi) / 2.0
    if _av.intersection(box(-4000.0, -21000.0, -2000.0, _mid)).area > BUS_M2:
        _hi = _mid
    else:
        _lo = _mid
BUS_FP = _av.intersection(box(-4000.0, -21000.0, -2000.0, _hi)).simplify(0.5)
if abs(BUS_FP.area - BUS_M2) > 150.0:
    raise SystemExit(f"автовокзал ТПУ: свободной земли {_av.area:.0f} м² < 14 450 м²")
_old_bus = zpoly("u_tpu_stations_2")
for _z in ZONES:
    if _z["id"] != "u_tpu_stations_2" and Polygon(_z["polygon"]).buffer(0).intersects(BUS_FP):
        zset(_z["id"], Polygon(_z["polygon"]).buffer(0).difference(BUS_FP))
zset("u_tpu_stations_2", BUS_FP)
zset("b_tpu", zpoly("b_tpu").union(_old_bus.difference(BUS_FP).difference(zpoly("u_tpu_stations"))))
# P+R: the 170 × 75 m box ran over the red line of the TPU ring and east into the interchange land (41 % short, with the
# business zone's 2031): the plot is the free land of b_tpu round the registry point up to the red lines, its own zone, the
# station's years; the same places on one more deck
PK_AT = Point(-2845.0, -20287.5)
PK_M2 = 12750.0
_avP = zpoly("b_tpu").difference(near_red(PK_AT, 300.0)).buffer(0)
_avP = min(getattr(_avP, "geoms", [_avP]), key=lambda q: (q.distance(PK_AT) > 40.0, -q.area))
if _avP.area < PK_M2:
    PK_M2 = math.floor((_avP.area - 20.0) / 50.0) * 50.0
_lo, _hi = 0.0, 400.0
for _ in range(60):
    _mid = (_lo + _hi) / 2.0
    if _avP.intersection(box(PK_AT.x - 1.6 * _mid, PK_AT.y - _mid, PK_AT.x + 1.6 * _mid, PK_AT.y + _mid)).area > PK_M2:
        _hi = _mid
    else:
        _lo = _mid
PARK_FP = _avP.intersection(box(PK_AT.x - 1.6 * _hi, PK_AT.y - _hi, PK_AT.x + 1.6 * _hi, PK_AT.y + _hi)).buffer(0)
PARK_FP = max(getattr(PARK_FP, "geoms", [PARK_FP]), key=lambda q: q.area).simplify(0.5)
if abs(PARK_FP.area - PK_M2) > 150.0:
    raise SystemExit(f"паркинг ТПУ: участок {PARK_FP.area:.0f} м² вместо {PK_M2:.0f} м²")
PK_M2 = int(round(PARK_FP.area / 50.0) * 50)
zset("b_tpu", zpoly("b_tpu").difference(PARK_FP))
_tpu = ZB["u_tpu_stations"]
ZONES.append({"id": "u_tpu_parking", "use": "utility", "name_ru": "Паркинг ТПУ «Gate» (многоуровневый)", "polygon": poly_pts(PARK_FP),
              "years": list(_tpu["years"]), "rules": dict(_tpu["rules"]),
              "why": MODEL + ": участок многоуровневого паркинга ТПУ (tpu_parking) — свободная земля зоны b_tpu у точки до красных "
                             "линий, годы станции ТПУ", "area_ha": round(PARK_FP.area / 1e4, 2)})
ZB["u_tpu_parking"] = ZONES[-1]
# a TPU zone short of the red line of a street it is entered from takes the band between it and that red line (otherwise
# gen_blocks_lots hands the plot the neighbours' strips; w44)
ACC = {c for c in LU.DRIVABLE if c not in LU.NO_ACCESS and not c.startswith("driveway")}
REACH = {}
for _zid in ("u_tpu_stations", "u_tpu_stations_2", "u_tpu_parking"):
    z0 = zpoly(_zid)
    acc = unary_union([LineString(x["line"]).buffer(red_w(x) / 2.0, cap_style=2) for x in STREETS
                       if x["class"] in ACC and len(x["line"]) > 1 and LineString(x["line"]).distance(z0) < 80.0])
    d_ = z0.distance(acc)
    if d_ <= 0.3 or d_ > 3.0:
        continue
    band = (z0.buffer(d_ + 0.3, join_style=2).intersection(acc.buffer(d_ + 0.6, join_style=2)).difference(acc).difference(z0).buffer(0))
    if band.is_empty:
        continue
    for _z in ZONES:
        if _z["id"] != _zid and Polygon(_z["polygon"]).buffer(0).intersects(band):
            zset(_z["id"], Polygon(_z["polygon"]).buffer(0).difference(band))
    zset(_zid, z0.union(band))
    REACH[_zid] = round(band.area)
taken = unary_union([Polygon(z["polygon"]).buffer(0) for z in ZONES])
# l_se (scheme: logistics, FAR 0.45) east of A-3: no street reaches it from the trial area (A-3 and БАКАД have no ramps here) and
# the 220 kV corridor runs over it — it stays in the utility remainder, as in Gate v1.1 (u_motorways_trial); before, it was a
# reserve block «резерв: земля вне зон спецификации» (tester r2 item 65)
zone("u_motorways", "utility", "Полосы отвода А-3 и БАКАД, поле развязок", AREA, [2025, 2025], {"lot_split": "none"},
     "остаток area: проезжие части, съезды, поле клеверной развязки, полосы улиц между зонами; блоки здесь не строятся",
     max_parts=40)

# ===================================================================================================== objects (registry + by rule)
OBJ = []


def obj(rid, name_ru, action, frm, to, accuracy, why, *, kind=None, footprint=None, lot_m2=None, yaw=None, years=None,
        capacity=None, source=None, parent=None):
    o = {"registry_id": rid, "name_ru": name_ru, "action": action, "from": frm, "to": to, "yaw": yaw, "accuracy": accuracy,
         "why": why}
    if kind:
        o["kind"] = kind
    if footprint is not None:
        g = footprint if isinstance(footprint, Polygon) else Polygon(footprint)
        o["footprint"] = poly_pts(g)
        o["lot_m2"] = round(g.area) if lot_m2 is None else lot_m2
    elif lot_m2:
        o["lot_m2"] = lot_m2
    if years:
        o["years"] = years
    if capacity:
        o["capacity"] = capacity
    if source:
        o["source"] = source
    if parent:
        o["parent"] = parent
    OBJ.append(o)
    return o


v0obj = {o["registry_id"]: o for o in GATE0["objects"]}


def rname(rid):
    return REG[rid]["name_ru"] if rid in REG else v0obj.get(rid, {}).get("name_ru", rid)


complex_plot = rect(C.ICONIC[0] - 100, C.ICONIC[1] - 136, C.ICONIC[0] + 100, C.ICONIC[1] + 136)
for rid in ("iconic_complex", "iconic_tower_main", "iconic_tower_second", "iconic_podium", "iconic_offices_6", "iconic_greenery"):
    obj(rid, rname(rid), "move", [-3170, -19080], list(C.ICONIC), "district_only",
        "решение владельца 31.10: Iconic в центре Gate, весь квартал сдвинут на Δ (CONTRACT §7); участок комплекса |x_лок| < 136, |z_лок| < 100",
        kind="landmark", footprint=complex_plot if rid == "iconic_complex" else None, yaw=270.0,
        parent=None if rid == "iconic_complex" else "iconic_complex", years=Y4(2029, "office"))
# iconic_offices_6 (registry, action add: «шесть малоэтажных офисных корпусов с внутренними дворами», S35 Forbes.kz 27.10.2026;
# «офисы вокруг башен», S31 SOM): the plot of the complex is the rebuilt plaza (IconicPlaza, granite ±133 × ±98 m), so the six
# blocks stand in the quarter round it, on its free ground in the twin's quarter model (Resources/Landmarks/gate_district.bytes):
# the courtyard ground (tag 26, ≤ 0.8 m) of the blocks tools/build_gate_district.py took out beyond the round of the complex,
# ≥ 12 m from the kept buildings, ≥ 11 m from the quarter's own streets (Resources/Film/Traffic/gate_roads.json), outside the oval
# square and ≥ 10 m inside the round (largest square that fits, 2 m search grid; w47 round 3). Low-rise: 4 floors of 4.43 m
# (land_util.floor_heights, business), a ring 15 m deep round an inner court (модель qTwin). The land tools give parts of a group
# no lot (they live on the keep lot L00123); Unity stands them (w46: clash check with IconicPlaza lawns, pavilions, flags, trees).
ICONIC_OFFICES = [("NE", (-3342.0, -19318.0, -3282.0, -19258.0)), ("E", (-3262.0, -19415.0, -3206.0, -19359.0)),
                  ("SE", (-3338.0, -19750.0, -3290.0, -19702.0)), ("SW", (-3715.0, -19746.0, -3659.0, -19690.0)),
                  ("W", (-3825.0, -19529.0, -3765.0, -19469.0)), ("NW", (-3715.0, -19314.0, -3663.0, -19262.0))]
_fhb = FH_M.get("business", 4.43)
_oi = next(o for o in OBJ if o["registry_id"] == "iconic_offices_6")
_oi["parts"] = []
for _k, (_side, _b) in enumerate(ICONIC_OFFICES):
    _out = rect(*_b)
    _in = _out.buffer(-15.0, join_style=2)
    _oi["parts"].append({"id": f"iconic_office_{_k + 1}", "side": _side, "footprint": poly_pts(_out), "courtyard": poly_pts(_in),
                         "to": [round(_out.centroid.x, 1), round(_out.centroid.y, 1)], "floors": 4, "height_m": round(4 * _fhb, 1),
                         "gfa_m2": round(_out.difference(_in).area * 4)})
_oi["why"] = ("реестр iconic_offices_6 (action add, S35: шесть малоэтажных офисных корпусов с внутренними дворами; S31: офисы "
              "вокруг башен): участок комплекса — площадь IconicPlaza, места на нём нет, поэтому шесть корпусов стоят в квартале "
              "Gate District вокруг участка, на свободной земле модели квартала двойника (gate_district.bytes: дворы снятых кварталов, "
              "≥ 12 м от оставленных зданий, ≥ 11 м от улиц квартала); 4 этажа × 4,43 м, кольцо глубиной 15 м вокруг двора "
              "(модель qTwin); части группы живут на участке keep (L00123), ставит их Unity (parts)")
obj("gate_district_ring", rname("gate_district_ring"), "move", [-3170, -19080], list(C.ICONIC), "none",
    "кольцо и площадь квартала едут вместе с Iconic (keep k_gate_district)", kind="landmark", footprint=KEEP_POLY)
obj("gateway_district_som", rname("gateway_district_som"), "by_rule", None, list(C.ICONIC), "district_only",
    "программа района без точки: центр — квартал Gate District (модель qTwin)", kind="landmark")
obj("intl_business_centre", rname("intl_business_centre"), "by_rule", None, [-3700.0, -19800.0], "district_only",
    "«более 3,7 млн м²» на весь район, точки нет: в пробной зоне — деловое кольцо Сити (зоны b_cbd*, b_cbd_e), здания по правилам зон",
    kind="business")
l7 = rect(EAST_X + 25, -19560, -2960 - 8, Z_E4 + 11)
obj("l7_lotte", rname("l7_lotte"), "move", REG["l7_lotte"]["geom"]["coordinates"], [round(l7.centroid.x, 1), round(l7.centroid.y, 1)],
    "none", "точки в источнике нет («в Alatau City»): по правилу — угол Проспекта Ворот и Восточной напротив Iconic, вне сектора обзора фасада",
    kind="business", footprint=l7, years=Y4(2031, "office"))
grif = rect(-2680, -19300, -2365, -18902)
obj("griffin_logopark", rname("griffin_logopark"), "move", REG["griffin_logopark"]["geom"]["coordinates"],
    [round(grif.centroid.x, 1), round(grif.centroid.y, 1)], "road_km_500m",
    "точка реестра по км А-3 (точность 500 м); участок 12,5 га у дублёра в %d м от точки, грузовой въезд с дублёра"
    % round(math.hypot(grif.centroid.x - REG["griffin_logopark"]["geom"]["coordinates"][0], grif.centroid.y - REG["griffin_logopark"]["geom"]["coordinates"][1])),
    kind="logistics", footprint=grif, years=Y4(2027, "industry"))
rail = rect(-2930, -20590, -2680, -20352)
ic_c = (-2255.0, -20323.0)
d_rail = Point(ic_c).distance(rail)
obj("agglo_rail_station_1", rname("agglo_rail_station_1"), "move", REG["agglo_rail_station_1"]["geom"]["coordinates"],
    [round(rail.centroid.x, 1), round(rail.centroid.y, 1)], "settlement_1km",
    "точка реестра в 25 м от центра клеверной развязки — вынесена в ТПУ: участок станции в %d м от центра развязки (≥ 400), "
    "в %d м от точки реестра (точность 1 км); трасса линии не опубликована — участок под станцию и пути (резерв)"
    % (d_rail, math.hypot(rail.centroid.x + 2280, rail.centroid.y + 20320)), kind="transit", footprint=rail, years=Y4(2030))
obj("a3_dubler", rname("a3_dubler"), "by_rule", None, [DUB_X, -19100.0], "district_only", "улица s_dubler", kind=None)
obj("road_bakad", rname("road_bakad"), "keep", [-2841, -20156], [-2841, -20156], "point_50m", "проезжие части БАКАД — улицы k_27df9cd9, k_6035cf98 и др. (OSM)")
obj("road_a3", rname("road_a3"), "keep", None, None, "point_50m", "проезжие части А-3 — улицы k_* (OSM)")
obj("interchange_a3_bakad", rname("interchange_a3_bakad"), "keep", [-2255, -20323], [-2255, -20323], "point_50m", "узел ic_a3_bakad (keep_existing)")
obj("road_a19", rname("road_a19"), "keep", None, None, "point_50m",
    "своей проезжей части А-19 в пробной зоне нет: маршрут KAZ06 идёт здесь по проезжим частям БАКАД и А-3 — общий участок, "
    "одна дорога с двумя номерами (реестр road_a19: «ОБЩИЙ УЧАСТОК, НЕ ОШИБКА», geom_details.concurrency); рисуется один раз, "
    "как БАКАД / А-3")
obj("hv_lines_220", rname("hv_lines_220"), "reroute", None, None, "point_50m",
    "ВЛ 220 кВ (OSM 121ff315) через центр Gate убирается в кабель вдоль парка БАКАД (utilities.hv220_cable); решение владельца: кабель или обход ядра")
obj("settlement_yntymak", rname("settlement_yntymak"), "keep", None, None, "point_50m", "зона v_yntymak, улицы v_* (OSM)")
obj("settlement_zhanadaur", rname("settlement_zhanadaur"), "keep", None, None, "point_50m",
    "контур посёлка задевает запад area (поля); домов Жанадаура в area нет")

# social by rule (модель qTwin): schools 500 m, kindergartens 300 m, polyclinic 1 km, fire 3 km
SOC = [
    ("school_gate_n", "Школа «Парк» на 2 000 мест", "school", rect(-2953, -18805, -2773, -18627), 2000, 2034,
     "школа на 2 000 мест (участок ≈ 3,2 га по норме schools.plot_2000_places_ha) в жилом районе у парка, вход с улицы L7; без пересечения магистралей"),
    ("school_gate_park", "Школа «Сити» на 2 000 мест", "school", rect(-3745, Z_PARK + 15, -3565, -18688), 2000, 2029,
     "школа на 2 000 мест у южного края Центрального парка (участок 3,55 га ≥ 3,2 га schools.plot_2000_places_ha): квартиры "
     "Сити-Севера и квартала Iconic (≤ 500 м от его края) — путь детей без магистралей; открывается с Iconic (2029): 3 697 квартир "
     "квартала × 2,5 = 9 243 жителя × 165 мест на 1 000 (schools.places_per_1000_genplan) = 1 525 мест"),
    ("kg_gate_1", "Детский сад (260 мест)", "kindergarten", rect(-3050, -18830, -2975, -18705), 260, 2033,
     "≤ 300 м до домов (норма многоэтажной застройки), участок 35 м²/место"),
    ("kg_gate_2", "Детский сад (260 мест)", "kindergarten", rect(-2695, -18640, -2595, -18535), 260, 2034, "≤ 300 м до домов"),
    ("kg_gate_6", "Детский сад (140 мест)", "kindergarten", rect(-2860, -18880, -2780, -18815), 140, 2034,
     "≤ 300 м до домов к югу от школы «Парк» (улица L7 у школы делит квартал)"),
    ("kg_gate_7", "Детский сад (140 мест)", "kindergarten", rect(-3215, -18625, -3135, -18560), 140, 2034,
     "≤ 300 м до домов у Северной улицы между Парковой восточной и Восточной улицами"),
    ("kg_gate_3", "Детский сад (260 мест)", "kindergarten", rect(-2500, -18872, -2400, -18772), 260, 2035, "≤ 300 м до домов"),
    ("kg_gate_4", "Детский сад (170 мест)", "kindergarten", rect(-3720, -19030, -3645, -18935), 170, 2029,
     "Сити-Север и северная часть квартала Iconic, ≤ 300 м до квартир; открывается с Iconic (2029); допускается и встроенный "
     "(norms kindergartens.placement)"),
    ("kg_gate_5", "Детский сад (140 мест)", "kindergarten", rect(-3460, -19030, -3380, -18965), 140, 2029,
     "Сити-Север и северная часть квартала Iconic, ≤ 300 м до квартир; открывается с Iconic (2029); вне сектора обзора северного "
     "входа Iconic"),
    ("kg_gate_8", "Детский сад (280 мест)", "kindergarten", None, 280, 2029,
     "южная и восточная части квартала Iconic, ≤ 300 м до квартир; открывается с Iconic (2029): с kg_gate_4 и kg_gate_5 — 590 мест "
     "≥ 9 243 жителя квартала × 63,2 на 1 000 (kindergartens.places_per_1000_genplan) = 584; участок 35 м²/место "
     "(kindergartens.plot_m2_per_place) в деловом кольце Сити, въезд с южного въезда квартала S-восток (2029)"),
    ("polyclinic_gate_park", "Поликлиника у станции «Центральный парк»", "polyclinic", "east_red", None, 2029,
     "радиус 1 000 м покрывает жильё пробной зоны и квартал Iconic; у станции ЛРТ; открывается с Iconic (2029), въезд с "
     "Восточной улицы (2028)"),
    ("fire_gate_a3", "Пожарное депо у дублёра", "fire_station", rect(-2325, -19740, -2245, -19680), None, 2030,
     "радиус 3 км покрывает всю пробную зону; выезд на дублёр, к А-3 и БАКАД через развязку"),
    ("tpu_bus_station", "Автовокзал ТПУ", "transit", BUS_FP, None, 2030,
     "автобусы у станций ЛРТ и ж/д, со стороны села; участок 14 450 м² — земля между улицей села v_eb195f5c, Восточной улицей "
     "s_east_s, кольцом ТПУ s_tpu1 и селом до красных линий (прямоугольник 85 × 170 м уровня 1 пересекали улица села и красная "
     "линия s_east_s); открывается вместе со станцией ТПУ (реестр agglo_rail_station_1, ГП727: 2030)"),
    ("tpu_parking", "Перехватывающий паркинг ТПУ (многоуровневый)", "parking", PARK_FP, None, 2030,
     "многоуровневый (наземные стоянки > 50 мест в центре — ошибка по норме); участок %s м² — свободная земля зоны b_tpu у точки "
     "(−2845, −20287.5) до красных линий (прямоугольник 170 × 75 м уровня 1, 12 750 м², заходил на красную линию кольца ТПУ и на "
     "землю развязки), те же места — на один ярус больше; открывается вместе со станцией ТПУ (реестр agglo_rail_station_1, "
     "ГП727: 2030)" % f"{PK_M2:,}".replace(",", " ")),
]


def plot_near(zids, seed, m2, aspect=1.0):
    """A plot of m2 in the zones' land net of red lines round the seed (the piece holding it), a box grown about the seed."""
    land = unary_union([zpoly(z) for z in zids]).difference(RED_FLAT.buffer(RED_CLEAR)).buffer(0)
    land = next(q for q in getattr(land, "geoms", [land]) if q.buffer(0.5).contains(Point(seed)))
    lo, hi = 0.0, 400.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if land.intersection(box(seed[0] - aspect * mid, seed[1] - mid, seed[0] + aspect * mid, seed[1] + mid)).area > m2:
            hi = mid
        else:
            lo = mid
    g = land.intersection(box(seed[0] - aspect * hi, seed[1] - hi, seed[0] + aspect * hi, seed[1] + hi)).buffer(0)
    return max(getattr(g, "geoms", [g]), key=lambda q: q.area).simplify(0.3)


KG8_AT = (-3300.0, -19850.0)
for rid, nm, kind, fp, cap, yb, why in SOC:
    capd = {"places": cap} if cap else None
    if fp is None:
        fp = plot_near(["b_cbd"], KG8_AT, cap * 35.0)
    elif fp == "east_red":
        # the level-1 box stopped 10 m short of the red line of Восточная улица: the land tools took Парковая восточная (2033)
        # for its access and opened it in 2033; up to the red line, Восточная (2028) is its access
        fp = rect(-3225, -18800, -3080, -18720).difference(RED_FLAT.buffer(RED_CLEAR)).buffer(0)
        fp = max(getattr(fp, "geoms", [fp]), key=lambda q: q.area).simplify(0.3)
    o = obj(rid, nm, "by_rule", None, [round(fp.centroid.x, 1), round(fp.centroid.y, 1)], "none", MODEL + ": " + why, kind=kind,
            footprint=fp, years=Y4(yb, "social"), capacity=capd)
    if rid == "tpu_bus_station":
        o["lot_m2"] = 14450
    if rid == "tpu_parking":
        o["lot_m2"] = PK_M2
    if rid == "kg_gate_4":
        # the 75 × 95 m plot did not hold the 200-place building (3 000 m², 3 floors) with the norm setbacks (w44): the plot is the
        # whole block between its four streets; the building ≥ 25 m from their red lines (kindergartens.building_from_red_line_m)
        # in the 80 × 112 m block: the 29 × 63 m patch holds 850 m² on 3 floors = 2 550 m² = 170 places at the twin's 15 m²
        _at = Point(o["to"])
        _blk = zpoly("b_cbd_n").difference(RED_FLAT).buffer(0)
        _blk = next(q for q in getattr(_blk, "geoms", [_blk]) if q.buffer(0.5).contains(_at)).simplify(0.3)
        o["footprint"] = poly_pts(_blk)
        o["lot_m2"] = round(_blk.area)
        o["to"] = [round(_blk.centroid.x, 1), round(_blk.centroid.y, 1)]
        o["why"] += ("; участок — весь квартал между четырьмя улицами (%s м²): здание сада не ближе 25 м к красным линиям "
                     "(kindergartens.building_from_red_line_m), пятно 29 × 63 м вмещает 850 м² на 3 этажа = 2 550 м² = 170 мест "
                     "(15 м² на место двойника)" % f"{o['lot_m2']:,}".replace(",", " "))

# utility lots of the twin's synthetic power and heat plants (StreamingAssets/twin/networks.json facilities, read only): w45 places
# the plants on them (tester r2 items 58–60). Years = each plant's first stage by scenario (base, fast, slow, infra).
with open(C.twin_path("StreamingAssets/twin/networks.json"), encoding="utf-8") as _f:
    TWIN_FAC = {f_["id"]: f_ for f_ in json.load(_f)["facilities"]}


def plant(fid, kind, fp, zid, access=None):
    f_ = TWIN_FAC[fid]
    yrs = [int(st[0]) for st in f_["stages"]]
    if access:                          # not before the street it is entered from (the land tools would raise it, w44 log)
        yrs = [max(a, b) for a, b in zip(yrs, STREET[access]["years"])]
    o = obj(fid, f_["name"], "by_rule", [f_["x"], f_["z"]], [round(fp.centroid.x, 1), round(fp.centroid.y, 1)], "none",
            MODEL + ": участок объекта двойника «%s» (networks.json %s, синтетический, первая очередь %d) — зона %s; точка двойника "
                    "(%d, %d) стояла %s" % (f_["name"], fid, yrs[0], zid, f_["x"], f_["z"],
                                           "внутри развязки А-3 × БАКАД" if fid == "hv_gate" else "в деловом квартале у Griffin"),
            kind=kind, footprint=fp, years=yrs, source="StreamingAssets/twin/networks.json facilities[%s]" % fid)
    return o


_hv = zpoly("u_hv_gate").difference(RED_FLAT).buffer(0)
plant("hv_gate", "substation", max(getattr(_hv, "geoms", [_hv]), key=lambda q: q.area).simplify(0.3), "u_hv_gate")
_en = zpoly("u_energy_gate_1").difference(RED_FLAT).buffer(0)
_en = max(getattr(_en, "geoms", [_en]), key=lambda q: q.area)
_x0, _lo, _hi = _en.bounds[0], _en.bounds[0], _en.bounds[2]
for _ in range(50):                      # the substation: 4 500 m² on the west side (модель qTwin: ОРУ 110 кВ, 2 трансформатора)
    _mid = (_lo + _hi) / 2.0
    if _en.intersection(box(_x0 - 1, -1e6, _mid, 1e6)).area > 4500.0:
        _hi = _mid
    else:
        _lo = _mid
plant("ps_gate_1", "substation", _en.intersection(box(_x0 - 1, -1e6, _hi, 1e6)).simplify(0.3), "u_energy_gate_1", access="s_e1")
plant("hb_gate_1", "utility", _en.difference(box(_x0 - 1, -1e6, _hi, 1e6)).buffer(0).simplify(0.3), "u_energy_gate_1", access="s_e1")

# ===================================================================================================== views (rule 17)
VIEWS = [
    {"id": "view_iconic_east", "registry_id": "iconic_complex", "apex": [-3400.0, Z_AVE], "dir_deg": 90.0, "fov_deg": 14.0,
     "len_m": 1040.0, "why": "восточный фасад Iconic вдоль Проспекта Ворот до дублёра; в секторе — только улица, площадь и низкие крыши"},
    {"id": "view_iconic_north", "registry_id": "iconic_complex", "apex": [C.ICONIC[0], -19364.0], "dir_deg": 0.0, "fov_deg": 12.0,
     "len_m": 820.0, "why": "северный вход квартала: бульвар и аллея парка до Северной улицы"},
    {"id": "view_l7", "registry_id": "l7_lotte", "apex": [round(l7.centroid.x, 1), round(l7.centroid.y, 1)], "dir_deg": 300.0,
     "fov_deg": 40.0, "len_m": 230.0, "why": "фасад L7 к Площади Ворот и Iconic"},
]
VIEW_CONV = "dir_deg — азимут по часовой стрелке от севера (+Z): 0 = север, 90 = восток"

# ===================================================================================================== utilities (power)
hv_cable = [(-4005.0, -19570.0), (AVE_X + 40, T_N[1] + 20)] + [(x, z - 45) for x, z in BK if -3830 <= x <= -2560] + [(-2440, -20030), (-2328, -19982)]
UTIL = [{"id": "hv220_cable", "kind": "power_cable_220kv", "line": [[round(x, 1), round(z, 1)] for x, z in hv_cable],
         "replaces": "osm:" + osm("121ff315")[1]["id"] if "121ff315" in SHORT else "OSM power_line 121ff315",
         "years": Y4(2027), "why": "ВЛ 220 кВ через центр Gate (над кварталом Iconic) — в кабель по парку БАКАД до опоры у А-3; "
                                    "решение владельца: кабель или обход ядра (модель qTwin трассы)"}]



def disjoint(zones):
    """Zones exactly disjoint after the 0.1 m rounding: each zone loses what the zones before it hold (the remainder comes last),
    the cut vertices kept to the millimetre; an invalid ring (touching itself) is repaired. Rounded, neighbours overlapped by
    slivers of up to 12 m², which the land tools turned into overlapping lots (rule 1)."""
    acc, n = Polygon(), 0
    for z in zones:
        p_ = Polygon(z["polygon"])
        q_ = p_.buffer(0).difference(acc).buffer(0) if not acc.is_empty else p_.buffer(0)
        if not p_.is_valid or abs(p_.area - q_.area) > 0.01:
            q_ = max(simple_parts(q_, 1.0), key=lambda g_: g_.area)
            for _ in range(3):                      # rounding can make a slit ring touch itself: clean and round again
                if Polygon(poly_pts(q_, 3)).is_valid:
                    break
                q_ = Polygon(poly_pts(q_, 3)).buffer(0)
                q_ = max(getattr(q_, "geoms", [q_]), key=lambda g_: g_.area)
            z["polygon"] = poly_pts(q_, 3)
            z["area_ha"] = round(q_.area / 1e4, 2)
            n += 1
        acc = acc.union(Polygon(z["polygon"]).buffer(0))
    return n


N_DISJ = disjoint(ZONES)

# ===================================================================================================== targets (trial area, model)
NET_LAND = AREA.difference(RED).difference(KEEP_POLY)


def net_ha(z):
    """Zone land net of streets and keep: the area the land tools spread the zone densities over (CONTRACT §4 w44)."""
    return Polygon(z["polygon"]).buffer(0).intersection(NET_LAND).area / 1e4


homes = sum(net_ha(z) * (z["rules"].get("homes_per_ha") or 0) for z in ZONES if z["use"] not in ("mixed_centre", "village_existing"))
jobs = sum(net_ha(z) * (z["rules"].get("jobs_per_ha") or 0) for z in ZONES if z["use"] not in ("mixed_centre", "village_existing"))
HOMES_R = int(round(homes, -1))
TARGETS = {"homes_2050": HOMES_R, "population_2050": int(round(HOMES_R * 2.5)),
           "jobs_2050": int(round(jobs, -2)), "home_m2": 75.0,
           "source": MODEL + ": плотности зон (homes_per_ha, jobs_per_ha) × чистая площадь кварталов зоны (без красных линий "
                     "улиц по norms.street_profiles и без keep); жители = квартиры × 2,5; квартал Iconic и село не считаются "
                     "(keep / существующие)"}

# ===================================================================================================== spec
axes_in = [a for a in GATE0["axes"] if LineString(a["line"]).intersects(AREA)]
joints_in = [{"joint_id": j["id"], "x": j["x"], "z": j["z"], "line": j.get("line"), "dist_to_area_m": round(Point(j["x"], j["z"]).distance(AREA), 1)}
             for j in CITY["joints"]["items"] if Point(j["x"], j["z"]).distance(AREA) < 40]
centres = [c for c in GATE0["centres"] if AREA.contains(Point(c["x"], c["z"]))]
phases = [{"queue": 1, "years": [2026, 2030],
           "what_ru": "Сначала улицы: дублёр до Griffin (2027); Проспект Ворот, Восточная улица до него (без ЛРТ), южный отрезок "
                      "дублёра (2028); улица вдоль БАКАД, Восточная улица до неё, въезды квартала с востока, юга и с Западной "
                      "площади, улицы Сити-Востока, северные въезды квартала, бульвар, улица Сити-Северная, Западная и Парковая "
                      "улицы — к детсадам, школе «Сити» и поликлинике, которые открываются с Iconic (2029); Восточная улица над БАКАД "
                      "и улица ТПУ — со станцией ТПУ (2030). Затем дома: Griffin (2027), Iconic (до 2029), пояс у дублёра (с 2028), "
                      "Сити и Сити-Восток (с 2029)",
           "streets": ["s_dubler", "s_griffin_in", "s_griffin_ring", "s_ave", "s_gate_sq", "s_east", "s_dubler_s", "s_x2520", "s_bakad_st", "s_east_m",
                       "s_e1", "s_e4", "s_w2", "s_w3", "s_w4", "s_sw", "s_swt", "s_sw2", "s_se", "s_set", "s_x2960", "s_x2700",
                       "s_west_st", "s_park", "s_19040", "s_nw", "s_nw2", "s_boulevard", "s_ne", "s_east_s", "s_tpu1"]},
          {"queue": 2, "years": [2031, 2040],
           "what_ru": "Сначала улицы: ЛРТ по Восточной улице, улицы делового квартала Griffin (2031); Западный проспект с развязкой на "
                      "БАКАД и всё, что на нём кончается: Проспект Ворот-запад, въезд W1, Северная улица и улицы жилого района у парка, Южный "
                      "проезд; пешеходный мост (2033). Затем дома: Сити-Север и ТПУ (с 2031), жильё у парка (с 2032), малоэтажные дома (с 2034)",
           "streets": ["s_x2960_n", "s_x2700_n", "s_go_mid", "s_west_ave", "s_west_ave_s", "s_ave_w", "s_ave_w_west", "s_w1", "s_park_w", "s_north",
                       "s_x3232", "s_x2960_nn", "s_x2700_nn", "s_x2520_nn", "s_park_walk", "s_south_link", "s_barn_drive", "s_ped_bridge"]}]

# ===================================================================================================== agglomeration rail
# Tester r2 item 55 (w45 draws it): the line of registry rail_agglomeration at its first station agglo_rail_station_1 (ГП727: 1st
# stage Алматы-1 → station at БАКАД/А-3, 13,2 km, 0,8 km inside the city, 2030; the route is not published, geom None). Модель
# qTwin: the line comes from Алматы-1 over the Turksib corridor east of А-3 and enters the city at its east edge south of the
# БАКАД; it crosses the А-3 × БАКАД cloverleaf (А-3, its ramps, the TPU street) on a viaduct, so the station is elevated: two
# tracks along the plot's north side (the side w44's land_transit gives the tracks: towards the motorways), a side platform on
# the hall's side, reached from the hall's upper floor by stairs and lifts (the viaduct clears the drives under it), buffer
# stops at the west end (a terminus until the line goes on, 2050).
RAIL_PLOT = (-2930.0, -20590.0, -2680.0, -20352.0)      # agglo_rail_station_1 footprint (rect `rail` of the objects)
RAIL_GAP_M = 5.0          # track centres (w44 land_transit TRACK_BED_M; модель qTwin)
RAIL_EDGE_M = 3.0         # north track axis from the plot's north edge
RAIL_ZC = RAIL_PLOT[3] - RAIL_EDGE_M - RAIL_GAP_M / 2.0  # line centre between the tracks
RAIL_XW = RAIL_PLOT[0] + 5.0                            # buffer stops 5 m inside the plot's west edge
RAIL_XS = -2735.0         # the curve begins 35 m past the platform's east end
RAIL_R = 500.0            # curve radius (≥ 60–70 km/h line speed, norms stops.agglomeration_rail; модель qTwin)
RAIL_AIM = (-1808.0, -20540.0)   # aimed at the city's east edge south of the БАКАД and its ramp (the area edge cuts it)
PLAT_X = (-2900.0, -2770.0)      # platform 130 m = w44 land_transit TRAIN_LEN_M (6 cars × ≈ 21,5 m), over the hall (x −2894…−2804)
PLAT_W_M = 8.0            # side platform (w44 PLATFORM_W_M)
PLAT_EDGE_M = 1.75        # track axis to the platform edge (модель qTwin: car 3,5 m wide)
PLAT_UP_M = 1.1           # high platform above the rail head (модель qTwin)
# rail head heights (absolute, as road y): the platform section level, rising and falling at ≤ 11 ‰. The deck's underside is
# the rail head less RAIL_DECK_M and spans RAIL_DECK_HALF_M each side of each track axis (lib MODEL rail_deck_below_m /
# rail_deck_half_m, as rule 25 «under_decks» and RailLayer take it); every point of it over a carriageway clears that
# carriageway by bridges.road_clearance_m 5,0 m, over a drive or turnaround pad by fire_access.arches.height_min_m 4,5 m, both
# with RAIL_MARGIN_M to spare. The station level is set over the highest ground under its deck (641,5 m at the buffer stops:
# any drive at grade there passes), the hump over ramp s35 k_f46e8f8f (651,45 m needed at its deck edge). Road surfaces of the
# runs of 01.11 (gate_trial r5, Gate r4 network.json / driveways.json); rail_check() measures it again on each build.
RAIL_DECK_M = 1.8
RAIL_DECK_HALF_M = 2.6
RAIL_MARGIN_M = 0.3
RAIL_PROFILE = [(0.0, 648.2), (230.0, 648.2), (560.0, 651.6), (700.0, 651.6)]
RAIL_FALL = 0.011


def rail_centre(area):
    """Centre line of the two tracks: straight from the buffer stops, an arc of RAIL_R, straight towards RAIL_AIM, cut at the
    area edge. Returns (LineString, exit point or None)."""
    def at(ph):
        return (RAIL_XS + RAIL_R * math.sin(ph), RAIL_ZC - RAIL_R * (1.0 - math.cos(ph)))

    def miss(ph):
        p_, h_ = at(ph), (math.cos(ph), -math.sin(ph))
        return (RAIL_AIM[0] - p_[0]) * h_[1] - (RAIL_AIM[1] - p_[1]) * h_[0]
    lo, hi = 0.0, 0.8
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if miss(lo) * miss(mid) <= 0:
            hi = mid
        else:
            lo = mid
    ph = (lo + hi) / 2.0
    pts = [(RAIL_XW, RAIL_ZC)] + [at(ph * k / 12.0) for k in range(13)]
    h_ = (math.cos(ph), -math.sin(ph))
    pts.append((pts[-1][0] + h_[0] * 3000.0, pts[-1][1] + h_[1] * 3000.0))
    line = LineString(pts)
    inside = line.intersection(area.buffer(0))
    parts = [g for g in getattr(inside, "geoms", [inside]) if g.geom_type == "LineString"]
    first = min(parts, key=lambda g: Point(pts[0]).distance(g))
    ex = Point(first.coords[-1])
    first = first.segmentize(10.0)                     # vertices every ≤ 10 m: the rail head height follows the profile
    return first, (ex if area.exterior.distance(ex) < 0.5 else None), math.degrees(ph)


def dec(v, nd):
    return f"{v:.{nd}f}".replace(".", ",")


def rail_y(s, length):
    if s >= RAIL_PROFILE[-1][0]:
        return RAIL_PROFILE[-1][1] - RAIL_FALL * (s - RAIL_PROFILE[-1][0])
    return float(np.interp(s, [q[0] for q in RAIL_PROFILE], [q[1] for q in RAIL_PROFILE]))


def rail_spec(area, edge_to):
    """spec `rail` (CONTRACT §8, Gate v1.2): lines with track centre lines [x, z, y_rail_head], struct, ends, edge joints;
    platforms; the viaduct's corridor."""
    cl, ex, turn = rail_centre(area)
    L_ = cl.length
    tracks = []
    for k, off in enumerate((RAIL_GAP_M / 2.0, -RAIL_GAP_M / 2.0)):
        g = cl.offset_curve(off)
        pts = []
        for x, z in g.coords:
            s_ = cl.project(Point(x, z))
            pts.append([round(x, 2), round(z, 2), round(rail_y(s_, L_), 2)])
        tl = LineString([(q[0], q[1]) for q in pts]).length
        tracks.append({"id": f"rail_agglo_t{k + 1}", "side": "north" if off > 0 else "south", "pts": pts,
                       "struct": [{"from_m": 0.0, "to_m": round(tl, 1), "kind": "overpass"}]})
    zs = RAIL_ZC - RAIL_GAP_M / 2.0                    # south track (the hall's side)
    plat = rect(PLAT_X[0], zs - PLAT_EDGE_M - PLAT_W_M, PLAT_X[1], zs - PLAT_EDGE_M)
    y_pl = round(rail_y(cl.project(plat.centroid), L_) + PLAT_UP_M, 2)
    corridor = cl.buffer(RAIL_GAP_M / 2.0 + 2.5, cap_style=2).union(plat).buffer(0)
    p0 = cl.coords[0]
    line = {"id": "rail_agglo_1", "registry_id": "rail_agglomeration", "name_ru": REG["rail_agglomeration"]["name_ru"]
            + " — 1-я очередь у станции ТПУ «Gate»", "gauge_mm": 1520, "tracks": tracks, "years": Y4(2030),
            "length_m": round(L_, 1), "rail_head_y": [[round(s_, 1), round(rail_y(s_, L_), 2)] for s_ in
                                                      sorted({q[0] for q in RAIL_PROFILE} | {round(L_, 1)})],
            "ends": [{"kind": "buffer_stop", "x": round(p0[0], 1), "z": round(p0[1], 1), "station": "agglo_rail_station_1"}],
            "edge_joints": ([{"x": round(ex.x, 1), "z": round(ex.y, 1), "y": round(rail_y(L_, L_), 2), "to": edge_to}] if ex else []),
            "corridor": poly_pts(corridor, 1),
            "source": "реестр rail_agglomeration и agglo_rail_station_1 (ГП727, S03: 1-я очередь Алматы-1 → станция у БАКАД/А-3, "
                      "13,2 км, 0,8 км в черте города, 2030); трасса не опубликована (geom None) — " + MODEL,
            "why": MODEL + ": двухпутная линия (колея 1520) приходит с востока через коридор Турксиба и входит в город на его восточной "
                           "границе южнее БАКАД; развязку А-3 × БАКАД (А-3, её съезды, улица ТПУ) проходит по эстакаде, поэтому "
                           "станция эстакадная: пути вдоль северной стороны участка станции (сторона к магистралям, как у w44), "
                           "боковая платформа со стороны вокзала, вход с его второго этажа лестницами и лифтами, упоры в западном конце — тупиковая "
                           "станция 1-й очереди до продления линии (53,5 км к 2050). Кривая R %s м, поворот %s°; головка рельса "
                           "%s м на станции, до %s м над А-3, уклоны ≤ %d ‰; низ пролёта (головка рельса − %s м, %s м в каждую "
                           "сторону от оси пути) над каждой проезжей частью ≥ 5,0 м (bridges.road_clearance_m), над проездами "
                           "и площадками ≥ 4,5 м (fire_access.arches.height_min_m), с запасом %s м; на станции — над самой "
                           "высокой землёй под пролётом (%s м)" % (
                               dec(RAIL_R, 0), dec(turn, 1), dec(RAIL_PROFILE[0][1], 1), dec(RAIL_PROFILE[-1][1], 1),
                               round(RAIL_FALL * 1000), dec(RAIL_DECK_M, 1), dec(RAIL_DECK_HALF_M, 1), dec(RAIL_MARGIN_M, 1),
                               dec(RAIL_PROFILE[0][1] - RAIL_DECK_M - 4.5 - RAIL_MARGIN_M, 1))}
    platforms = [{"id": "rail_agglo_p1", "line": "rail_agglo_1", "station": "agglo_rail_station_1", "side": "south",
                  "tracks": ["rail_agglo_t2"], "polygon": poly_pts(plat, 2), "y": y_pl, "length_m": round(PLAT_X[1] - PLAT_X[0], 1),
                  "width_m": PLAT_W_M, "years": Y4(2030),
                  "why": (MODEL + ": боковая платформа %.0f × %.0f м (длина поезда 6 вагонов, w44 land_transit TRAIN_LEN_M) над "
                                  "залом вокзала, край в %.2f м от оси пути, высокая (%.1f м над головкой рельса)"
                          % (PLAT_X[1] - PLAT_X[0], PLAT_W_M, PLAT_EDGE_M, PLAT_UP_M)).replace(".", ",")}]
    return {"lines": [line], "platforms": platforms}


def rail_check(rail, out_dir):
    """Clearance under the viaduct as rule 25 «under_decks» measures it, on a run's network.json and driveways.json: the deck
    (rail head − RAIL_DECK_M, RAIL_DECK_HALF_M each side of each track) over every carriageway (land_util carriage polygon,
    bridges.road_clearance_m 5,0 m) and every drive and turnaround pad (fire_access.arches 4,5 m), sampled on a 0,5 m grid.
    Returns [(id, what, x, z, clear_m, need_m)], the lowest point per road / drive."""
    import shapely
    sys.path.insert(0, os.path.join(C.MAP, "gen"))
    import land_util as U
    out = []
    ln = rail["lines"][0]
    tr = [np.array(t_["pts"], float) for t_ in ln["tracks"]]
    fp = unary_union([LineString(q[:, :2]).buffer(RAIL_DECK_HALF_M, cap_style=2) for q in tr])
    axes = [(LineString(q[:, :2]), np.r_[0.0, np.cumsum(np.hypot(*np.diff(q[:, :2], axis=0).T))], q[:, 2]) for q in tr]
    nm = U.Norms()

    def under(Q):                                    # deck underside over each point: the nearer track's rail head − deck
        best = np.full(len(Q), np.inf)
        dist = np.full(len(Q), np.inf)
        for L, S, Y in axes:
            P = shapely.points(Q)
            d_ = shapely.distance(L, P)
            y_ = np.interp(shapely.line_locate_point(L, P), S, Y) - RAIL_DECK_M
            m = d_ < dist
            best[m], dist[m] = y_[m], d_[m]
        return best

    def along(P):
        P = np.asarray(P, float)
        S = np.r_[0.0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
        L = LineString(P[:, :2])
        return lambda Q: np.interp(shapely.line_locate_point(L, shapely.points(Q)), S, P[:, 2])

    def low(poly, surf, sid, what, need):
        ov = poly.intersection(fp)
        if ov.is_empty or ov.area < 0.01:
            return
        x0, z0, x1, z1 = ov.bounds
        gx, gz = np.meshgrid(np.arange(x0 + 0.25, x1, 0.5), np.arange(z0 + 0.25, z1, 0.5))
        gx, gz = gx.ravel(), gz.ravel()
        m = shapely.contains_xy(ov, gx, gz)
        Q = np.vstack([shapely.get_coordinates(ov), np.c_[gx[m], gz[m]]])
        c = under(Q) - surf(Q)
        k = int(np.argmin(c))
        out.append((sid, what, round(float(Q[k, 0]), 1), round(float(Q[k, 1]), 1), round(float(c[k]), 2), need))

    for name, need in (("network.json", 5.0), ("driveways.json", 4.5)):
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            net = json.load(f)
        for sg, poly, lv in U.network_polys(net, nm, "carriage"):
            if len(sg.get("pts") or []) >= 2 and poly.intersects(fp):
                low(poly, along(sg["pts"]), sg["id"], f"{sg['class']} {sg.get('street') or ''}".strip(), need)
        nodes = {n["id"]: n for n in net.get("nodes") or []}
        for pd in net.get("pads") or []:
            pg = Polygon(pd["polygon"]).buffer(0)
            y = (nodes.get(pd["node"]) or {}).get("y")
            if y is not None and pg.intersects(fp):
                low(pg, lambda Q, y=float(y): np.full(len(Q), y), "pad_" + pd["node"], "разворотная площадка", need)
    return sorted(out, key=lambda r_: r_[4] - r_[5])


RAIL = rail_spec(AREA, "Алматы-1: остальные 12,4 км 1-й очереди — вне города (за восточной границей пробной зоны)")
RAIL_SZZ = sorted(z["id"] for z in ZONES if z["use"] in ("residential_high", "residential_mid", "residential_low", "mixed_centre",
                                                          "village_existing", "waterfront")
                  and Polygon(z["polygon"]).buffer(0).distance(LineString([(q[0], q[1]) for q in RAIL["lines"][0]["tracks"][0]["pts"]])) < 100.0)

spec = {
    "district": "gate_trial", "version": 1, "level": 1,
    "made_by": "w47 tools/map/district/gate_trial_build.py (пробная зона Gate у Iconic)",
    "boundary": "city.json#districts/gate",
    "attribution": C.ATTRIBUTION,
    "area": [[round(x, 1), round(z, 1)] for x, z in list(AREA.exterior.coords)[:-1]],
    "area_ha": round(AREA.area / 1e4, 1),
    "targets": TARGETS,
    "centres": centres,
    "axes": axes_in,
    "zones": ZONES,
    "lrt": lrt,
    "rail": RAIL,
    "objects": OBJ,
    "phases": phases,
    "joints": joints_in,
    "edge_joints": EDGE_JOINTS,
    "streets": STREETS,
    "nodes": list(NODES.values()),
    "keep": keep,
    "views": VIEWS,
    "views_convention": VIEW_CONV,
    "utilities": UTIL,
    "corridors": None,
    "replaced_osm": sorted({p["id"] for g, p in OSM_ROADS if p["class"] == "track" and g.intersects(AREA)}),
    "checks": {},
}

# overhead power lines that stay (rules 4 and 19, land): the OSM lines of land_util.corridors with their voltage. OSM (Overture
# source_tags of level 0, w35/overture/infrastructure.parquet) tags 92ca2130, 4969c90a and 20c6b40c (and the two lines put into
# cable) voltage=220000 — registry hv_lines_220; the other lines carry no voltage tag (model below). Gate v1.1 uses the same table.
KV_OSM = {"92ca2130": 220, "4969c90a": 220, "20c6b40c": 220}
KV_220_SRC = "OSM voltage=220000 (Overture source_tags), реестр hv_lines_220 «ВЛ 220 кВ»"
KV_MODEL = {
    "74b9e818": (220, MODEL + ": вторая линия коридора 220 кВ 92ca2130 (идёт рядом с ней на всём протяжении, нанесена в OSM "
                              "одной правкой, w474419430 / w474419432); voltage в OSM нет"),
    "7fdf85db": (220, MODEL + ": пролёт 100 м у опоры линии 220 кВ при А-3 (в 80 м от трассы реестра hv_lines_220); voltage в OSM нет"),
}
KV_LINE = (110, MODEL + ": OSM power=line на опорах-башнях без voltage — линия электропередачи, класс не задан; принят 110 кВ "
                        "(сети района 110/10 кВ — реестр ps_kokpa_1), охранная зона 20 м, шире наименьшего класса 35 кВ (15 м)")
KV_MINOR = (10, MODEL + ": OSM power=minor_line (распределительная сеть на опорах) без voltage — класс 1–20 кВ, охранная зона 10 м")


def kv_corridors(sp):
    """land_util.corridors of a spec (its overhead OSM lines) with kv and kv_basis."""
    import copy as _copy
    out = []
    for c in LU.corridors(_copy.deepcopy({k: v for k, v in sp.items() if k != "corridors"})):
        if not str(c.get("source", "")).startswith("osm:"):
            continue
        short = c["source"][4:12]
        if short in KV_OSM:
            kv, basis = KV_OSM[short], KV_220_SRC
        elif short in KV_MODEL:
            kv, basis = KV_MODEL[short]
        else:
            kv, basis = KV_MINOR if c.get("osm_class") == "minor_line" else KV_LINE
        out.append({**c, "kv": kv, "kv_basis": basis})
    return out


for u in UTIL:
    u["kv"] = 220
    u["kv_basis"] = KV_220_SRC
spec["corridors"] = kv_corridors(spec)

if __name__ == "__main__":
    import gate_trial_check as CHK
    res = CHK.run(spec, verbose=False)
    spec["checks"] = res
    txt = json.dumps(spec, ensure_ascii=False, indent=1)
    with open(SPEC_OUT + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write(txt + "\n")
    os.replace(SPEC_OUT + ".tmp", SPEC_OUT)
    print(f"wrote {SPEC_OUT}: {len(txt) // 1024} KB; streets {len(STREETS)}, nodes {len(NODES)}, edge_joints {len(EDGE_JOINTS)}, "
          f"zones {len(ZONES)}, objects {len(OBJ)}; area {spec['area_ha']} ha")
    print(f"rail: {RAIL['lines'][0]['length_m']} m, edge {RAIL['lines'][0]['edge_joints']}, homes zones within 100 m {RAIL_SZZ}")
    for r_ in rail_check(RAIL, os.path.join(C.OUT, "gate_trial")):
        print("  rail over", r_, "LOW" if r_[4] < r_[5] else "")
    if "--no-check" not in sys.argv:
        ok = CHK.main([SPEC_OUT])
        sys.exit(0 if ok else 1)
