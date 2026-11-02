#!/usr/bin/env python3
"""Green · level 2 · street network of the whole district (w51), imported by green_build.py.

    python3 -I tools/map/district/green_net.py            # build the frame in memory and print a summary

The network is made of three layers:
  1. existing roads (Overture/OSM): А-3 with its km 61 trumpet, улица Арнаутская, the Жетыгенская road, Октябрь – Толай,
     the village streets stay as they are (gen_network takes them from OSM; the main ones are listed as keep_existing
     streets); other existing roads inside new quarters are replaced (replaced_osm);
  2. the frame of new streets by the level-0 scheme axes (prosp_green with the LRT in its median, privokzal, yuzh, ozerny with
     the new А-3 diamond «Green-Север», arnaut_w over А-3, dubler_a3w, terr, east_link, bereg_e, log_st …);
  3. local streets of every new quarter, generated here (the generator's grid is off for v1 specs): an edge street along
     every side of the quarter that has no street (village, park, water, expressway, district edge) and a grid at the
     zone's block size, aligned with the frame, every end on a street.
Every coordinate not from a source is the cartographer's design (label «модель qTwin»). Unity frame: X east, Z north.
The generic part (registries, local grid, post-passes) is the Gate one (gate_net.py, w47) with Green's inputs.
"""
import copy
import heapq
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.ops import substring, unary_union  # noqa: E402

import green_common as C  # noqa: E402
import green_zones as Z  # noqa: E402
import land_util as LU  # noqa: E402

MODEL = C.MODEL
Y4 = C.Y4
fillet = C.fillet
CITY = C.CITY
V0 = C.V0
GREEN = C.GREEN
on = C.on

_LN = LU.Norms()
_RW = {}


def red_w(cls, profile=None):
    if cls not in _RW:
        _RW[cls] = float(LU.profile_from_norms(_LN, cls)["red_line_w"])
    w = _RW[cls]
    g = float((profile or {}).get("green_w") or 0.0)
    return max(w, g + 6.0) if g else w


# ===================================================================================================== open data
OSM = {p["id"]: (g, p) for g, p in C.layer_in("roads", GREEN)}
SH = {k[:8]: k for k in OSM}


def osm(short):
    return OSM[SH[short]]


VILL = unary_union([z["poly"] for z in Z.ZPLAN if z["use"] == "village_existing"])
_W = C.layer_in("water", GREEN.buffer(200))
WATER_POLY = unary_union([g for g, p in _W if g.geom_type in ("Polygon", "MultiPolygon") and p.get("class") != "swimming_pool"])
WATER_LINE = unary_union([g for g, p in _W if g.geom_type in ("LineString", "MultiLineString")])
STRIP = 35.0                                       # flood.water_protection_strip_min_m
WATER_STRIP = unary_union([WATER_POLY.buffer(STRIP), WATER_LINE.buffer(STRIP)])
RAIL = unary_union([g for g, p in C.layer_in("rail", GREEN.buffer(100))])
RAIL_TS = next(g for g, p in C.layer_in("rail", GREEN.buffer(100)) if str(p.get("id", "")).startswith("b6c61470"))   # Турксиб

from gen_blocks_lots import existing_houses  # noqa: E402

HOUSES = [h["fp"] for h in existing_houses(GREEN.buffer(80), Polygon())]
HTREE = shapely.STRtree(HOUSES)


def houses_hit(geom):
    return [HOUSES[i] for i in HTREE.query(geom, predicate="intersects")]


# ===================================================================================================== registries
STREETS, NODES = [], {}
SID = {}
SCHEME_CHANGES = []              # frame changes against the level-0 scheme: (id, why)


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
           use="road", years=None, layer="frame"):
    line = [(round(float(x), 1), round(float(z), 1)) for x, z in line]
    q = [line[0]]
    for p in line[1:]:
        if p != q[-1]:
            q.append(p)
    s = {"id": sid, "class": cls, "line": [list(p) for p in q], "name_ru": name_ru,
         "years": list(years) if years else Y4(base, use), "oneway": oneway, "profile": profile or {},
         "struct": [{"from": [round(a[0], 1), round(a[1], 1)], "to": [round(b[0], 1), round(b[1], 1)], "kind": k}
                    for a, b, k in struct],
         "source": source, "axis": axis}
    if why:
        s["why"] = why
    s["_layer"] = layer
    if sid in SID:
        raise SystemExit(f"street id {sid} twice")
    STREETS.append(s)
    SID[sid] = s
    return s


def L_(sid):
    return LineString(SID[sid]["line"])


def water_bridges(line, pad=12.0):
    """Struct spans (bridge) where a new line crosses water (streams and water polygons), each padded on both sides."""
    L = LineString(line)
    out = []
    spans = []
    for g in (WATER_LINE, WATER_POLY):
        x = L.intersection(g)
        if x.is_empty:
            continue
        for q in getattr(x, "geoms", [x]):
            if q.geom_type == "Point":
                s = L.project(q)
                spans.append((s - pad, s + pad))
            elif q.geom_type == "LineString":
                a, b = L.project(Point(q.coords[0])), L.project(Point(q.coords[-1]))
                spans.append((min(a, b) - pad, max(a, b) + pad))
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 5:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    for a, b in merged:
        a, b = max(a, 0.5), min(b, L.length - 0.5)
        if b - a > 2:
            pa, pb = L.interpolate(a), L.interpolate(b)
            out.append(((pa.x, pa.y), (pb.x, pb.y), "bridge"))
    return out


def rail_overpasses(line, pad=45.0, merge=150.0):
    """Struct spans (overpass) where a new line crosses the railway (Турксиб, the Жетыген yard): the street passes over
    the tracks, padded on both sides; tracks closer than `merge` along the line share one span."""
    L = LineString(line)
    x = L.intersection(RAIL)
    ch = sorted(L.project(q) for q in getattr(x, "geoms", [x]) if not q.is_empty and q.geom_type == "Point")
    spans = []
    for c in ch:
        if spans and c - spans[-1][1] < merge:
            spans[-1][1] = c
        else:
            spans.append([c, c])
    out = []
    for a, b in spans:
        a, b = max(a - pad, 0.5), min(b + pad, L.length - 0.5)
        pa, pb = L.interpolate(a), L.interpolate(b)
        out.append(((pa.x, pa.y), (pb.x, pb.y), "overpass"))
    return out


def merge_struct(spans):
    """Spans of one line merged where they overlap (a bridge inside an overpass is one span, the overpass)."""
    out = []
    for a, b, k in spans:
        out.append([a, b, k])
    return out


# ===================================================================================================== 1. existing roads
VILLAGE_OSM = {"residential", "service", "unclassified", "living_street", "unknown"}
KEEP_IDS = {}
AX_OSM = {"arnaut": {"a6a55552", "ad63b762", "a7e7808d", "f38b43e0", "14dbb8e7", "6ddef7a1", "3ecc49e8", "c738cb8c",
                     "fc833f0f", "e1928751", "490214e6", "0adff605", "33c2388e"},
          "east_n": {"17676108", "8edfe649", "1d87369b", "94f53580"},
          "tolai": {"b535ecf8", "52d20ac7", "6230af0d", "cb2e4e4e", "56948422"},
          "se_main": {"614d61e5", "e30092e0"}}


def osm_class(p, g):
    c, sub = p.get("class"), p.get("sub")
    if c == "motorway":
        return "ramp" if sub == "link" else "expressway"
    if c in ("tertiary", "secondary", "primary"):
        return "village_main" if g.intersection(VILL).length > 0.5 * g.length else "district_transport"
    return None


def keep_name(p):
    n = p.get("name") or ""
    if n.startswith("Алматы-Ө"):
        return "А-3 Алматы – Қонаев"
    if p.get("sub") == "link":
        return "съезд развязки А-3 км 61"
    if p["id"][:8] in AX_OSM["east_n"] or p["id"][:8] in ("719385e1", "77b26302", "daeee94e", "688065bc", "fd9b47c7"):
        return n or "Жетыгенская дорога"
    return n


for oid, (g, p) in sorted(OSM.items()):
    cls = osm_class(p, g)
    if cls is None:
        continue
    clip = g.intersection(GREEN)
    if clip.length < 3.0:
        continue
    sid = ("k_" if cls in ("expressway", "ramp") else "t_") + oid[:8]
    nm = keep_name(p)
    ax = "a3" if cls == "expressway" else next((a for a, ids in AX_OSM.items() if oid[:8] in ids), None)
    parts = [clip] if clip.geom_type == "LineString" else [q for q in clip.geoms if q.geom_type == "LineString"]
    line = max(parts, key=lambda q: q.length).coords
    street(sid, cls, line, nm or ("улица села" if cls == "village_main" else ""), 2025, oneway=cls in ("expressway", "ramp"),
           source="keep_existing:" + oid, axis=ax, years=C.EXISTING, layer="osm",
           why="существующая дорога OSM/Overture, как есть (направление линии = направление движения)" if cls in ("expressway", "ramp")
           else "существующая дорога OSM, как есть")
    KEEP_IDS[oid] = sid

HOST_OSM = {oid for oid, (g, p) in OSM.items() if p.get("class") in VILLAGE_OSM | {"tertiary", "secondary"}}


def osm_line(oid):
    g = OSM[oid][0].intersection(GREEN)
    parts = [g] if g.geom_type == "LineString" else [q for q in getattr(g, "geoms", []) if q.geom_type == "LineString"]
    return parts


def k_of(short):
    return KEEP_IDS.get(SH[short]) if short in SH else None


# ===================================================================================================== 2. frame of new streets
LRT_W = float(_LN.v("lrt.corridor_width_m", "double_track"))
PROSP_PROFILE = {"median_w": round(LRT_W + 2.4, 1), "lanes": [2, 2],
                 "note_ru": "в разделительной полосе — пути ЛРТ (двухпутный коридор 7,6 м и ограждения)"}
A3_NB, A3_SB = "3b7602a4", "ac2ba3f1"                     # А-3 north- and southbound carriageways (OSM) between km 61 and Конаев

# --- Проспект Green (scheme prosp_green, arterial): the LRT runs in its median. The scheme's line crossed the village
# Құйған-Север (vil_6, 1.1 km inside it, 6 m from a house at (3720, 14487)): the avenue goes round the village on its east
# side, between the village and the Каскелен shore (≥ 45 m from the village outline, ≥ 60 m from its houses), and
# rejoins the scheme's line at (3308, 15900), where Южная улица and the bridge to the east bank meet it.
PROSP_S = fillet([(3925.0, 14195.0), (3985.0, 14360.0), (3990.0, 15150.0), (3308.0, 15900.0), (3050.0, 16350.0),
                  (2750.0, 17550.0), (2800.0, 18930.0)], 450)
PROSP_N = fillet([(2800.0, 18930.0), (2750.0, 20100.0), (2900.0, 21150.0), (3050.0, 21700.0), (2950.0, 22550.0)], 450)
SCHEME_CHANGES.append(("s_prosp", "южный участок проспекта (и ЛРТ в нём) обходит село Құйған-Север (vil_6) с востока, между селом "
                                  "и берегом Каскелена: линия схемы шла 1,1 км через село в 6 м от дома (3720, 14487); "
                                  "отклонение ≤ 300 м, к линии схемы возвращается у (3308, 15900)"))
X_ARN_PROSP = on(PROSP_S, z=18930.0)
street("s_prosp", "arterial_regulated", PROSP_S, "Проспект Green (южный участок, ЛРТ по оси)", 2029, axis="prosp_green",
       profile=dict(PROSP_PROFILE), struct=water_bridges(PROSP_S),
       why="схема prosp_green (1-я очередь 2028–2034): от Құйғана вдоль восточного края села к Южному кварталу, центрам "
           "Южный и Арнаутская; полоса ЛРТ в разделительной полосе")
street("s_prosp_n", "arterial_regulated", PROSP_N, "Проспект Green (северный участок, ЛРТ по оси)", 2032, axis="prosp_green",
       profile=dict(PROSP_PROFILE), struct=water_bridges(PROSP_N),
       why="схема prosp_green: от Арнаутской через центральные кварталы и парк к Green-Сити и выставочному кварталу; "
           "вместе с ЛРТ 2-й очереди и Озёрным проспектом")
# the avenue's south end: улица Құйған west to the village's existing street f5b4d7a4 (the avenue does not end blind)
_f5 = osm("f5b4d7a4")[0]
K_END = _f5.interpolate(_f5.project(Point(3640.0, 14196.0)))
street("s_kuygan", "district_transport", [PROSP_S[0], (3800.0, 14200.0), (K_END.x, K_END.y)], "улица Құйған", 2029,
       why=MODEL + ": начало Проспекта Green на существующей улице села Құйған-Север (OSM f5b4d7a4); проспект не кончается "
                   "тупиком, село получает выезд на проспект и ЛРТ")
# --- Привокзальная (arterial) and Южная (district): the scheme's lines
PRIV = fillet([(1450.0, 16400.0), (1400.0, 17250.0), (1500.0, 18975.0), (1550.0, 21650.0)], 400)
street("s_privokzal", "arterial_regulated", PRIV, "Привокзальная улица", 2028, axis="privokzal",
       why="схема privokzal (2027–2031): вдоль Турксиба от Южной улицы мимо вокзала Іле и Арнаутской к Озёрному проспекту")
X_YUZH = (3308.0, 15900.0)
YUZH = fillet([(1450.0, 16400.0), (2200.0, 15850.0), X_YUZH], 300)
street("s_yuzh", "district_transport", YUZH, "Южная улица", 2028, axis="yuzh", struct=water_bridges(YUZH),
       why="схема yuzh (2027–2031): от Привокзальной к Проспекту Green, южная граница центральных кварталов")
# --- Озёрный проспект with the new А-3 diamond «Green-Север» (scheme ozerny; node of the scheme at z 21650)
Z_OZ = 21650.0
X_NB, X_SB = on(osm("abdc4b98")[0], z=Z_OZ)[0], on(osm(A3_SB)[0], z=Z_OZ)[0]
IC_N = (round((X_NB + X_SB) / 2.0, 1), Z_OZ)
X_DUB = -350.0
OZ_A3 = [(X_DUB, Z_OZ), IC_N, (1550.0, Z_OZ)]
OZ = [(1550.0, Z_OZ), (3050.0, 21700.0)]
street("s_ozerny_a3", "arterial_regulated", OZ_A3, "Озёрный проспект (развязка «Green-Север»)", 2033, axis="ozerny",
       struct=rail_overpasses(OZ_A3) + water_bridges(OZ_A3),
       why="схема ozerny (2030–2033): от дублёра А-3 через новую развязку «Green-Север» на А-3 и над Турксибом (путепровод) "
           "к Привокзальной; открывается в 2033 вместе с дублёром и первыми кварталами делового пояса А-3")
street("s_ozerny", "arterial_regulated", OZ, "Озёрный проспект", 2031, axis="ozerny", struct=water_bridges(OZ),
       why="схема ozerny (2030–2033): от Привокзальной к Проспекту Green (Green-Сити, курорт)")
node("rb_x_dub", X_DUB, Z_OZ, "roundabout", ["s_ozerny_a3", "s_ozerny_w", "s_dubler"],
     why_ru=MODEL + ": западный конец Озёрного проспекта (магистраль с разделительной полосой) — кольцо, где расходятся "
                    "дублёр А-3 и Северная улица к террасам (магистраль × районная: кольцо по node_matrix)")
SCHEME_CHANGES.append(("s_ozerny_a3", "Озёрный проспект западнее Привокзальной с развязкой «Green-Север» и дублёр А-3, Арнаутская-Запад "
                                      "открываются в 2033 (у схемы 2030–2033 и 2034–2037): участок проспекта через А-3 "
                                      "без улиц по ту сторону кончался бы тупиком магистрали (правило 5); улицы делового пояса — "
                                      "за год до его первых зданий (2034)"))
node("ic_green_n", IC_N[0], IC_N[1], "diamond", ["s_ozerny_a3", "k_" + "abdc4b98", "k_" + A3_SB], major="k_abdc4b98",
     major_pair="k_" + A3_SB, upper="minor",
     why_ru="новая развязка «Green-Север» (схема): ромб на А-3 у Озёрного проспекта, проспект — путепроводом над А-3; "
            "до существующей развязки км 61 — 2,7 км")
OZ_E = [(3050.0, 21700.0), (3950.0, 21600.0)]
street("s_ozerny_e", "district_transport", OZ_E, "Озёрный проспект (к курорту)", 2031, axis="ozerny",
       why="схема ozerny: восточный конец от Проспекта Green к курорту IRCC (2030–2040), дальше — Бульвар к озеру")
SCHEME_CHANGES.append(("s_ozerny_e", "Озёрный проспект восточнее Проспекта Green — районная улица (а не магистраль) до курорта: "
                                     "у схемы ось шла поверх Бульвара к озеру; бульвар начинается в её конце"))
# --- the shore street of Green-Сити: from the avenue's north end east past the heat-pump station along the shore park to
# the end of Озёрный проспект (scheme heat_st, continued so that it is not a dead end)
# the avenue's north end is a T on one through street: from the district border on the trace of the existing dirt road to
# Конаев (OSM a1806e72, its part in the exhibition quarter is replaced) past the avenue's end east along the shore of
# Green-Сити to the heat-pump station and south along the shore park to the end of Озёрный проспект (scheme heat_st)
_a18 = osm("a1806e72")[0]
_b18 = _a18.intersection(GREEN.exterior)
_b18 = _b18 if _b18.geom_type == "Point" else list(_b18.geoms)[0]
EXPO = fillet([(_b18.x, _b18.y), (2414.0, 23082.0), (2481.0, 22874.0), (2542.0, 22728.0), (2640.0, 22558.0),
               (2950.0, 22550.0)], 150)
HEAT = fillet([(2950.0, 22550.0), (3700.0, 22470.0), (3950.0, 22250.0), (3950.0, 21600.0)], 150)
HEAT = [tuple(p) for p in EXPO] + [tuple(p) for p in HEAT[1:]]
street("s_heat", "district_transport", HEAT, "Береговая улица Green-Сити (от дороги на Конаев к тепловой станции)", 2032,
       axis="heat_st", struct=water_bridges(HEAT),
       why="схема heat_st (2032–2034) — подъезд к станции тепловых насосов; " + MODEL + ": на запад — по трассе грунтовой "
           "дороги на Конаев (OSM a1806e72) до границы района, где она продолжается; на юг — вдоль берегового парка к концу "
           "Озёрного проспекта у курорта; Проспект Green кончается на ней Т-образным перекрёстком")
SCHEME_CHANGES.append(("s_heat", "улица к тепловой станции продолжена на юг вдоль берегового парка (x 3950) до Озёрного проспекта и "
                                 "на запад по трассе дороги OSM a1806e72 до границы района (z 23 359, дорога на Конаев): "
                                 "тупиковая районная улица и конец магистрали без перекрёстка запрещены правилом 5"))
# --- Бульвар к озеру (boulevard): from the end of Озёрный проспект across the IRCC cape to the tower at its tip
BLV = fillet([(3950.0, 21600.0), (4600.0, 21480.0), (5120.0, 21390.0)], 300)
street("s_blv_lake", "boulevard", BLV, "Бульвар к озеру", 2034, axis="blv_lake", struct=water_bridges(BLV),
       why="схема blv_lake (2033–2037): от Озёрного проспекта через курорт IRCC к 30-этажной доминанте на мысу")
# --- Арнаутская-Запад (scheme arnaut_w) and the crossing of А-3 north of the km 61 trumpet. The scheme's axis started at
# the trumpet's west side, but the trumpet (OSM) has no west leg: its loop stands there. The street runs from Террасная to
# the дублёр, then over А-3 (grade separation, no ramps: the trumpet is 450 m south) and over the Турксиб to Привокзальная.
Z_AX = 19450.0
x_nb, x_sb = on(osm(A3_NB)[0], z=Z_AX)[0], on(osm(A3_SB)[0], z=Z_AX)[0]
ARN_W = fillet([(-2300.0, 19050.0), (-1300.0, 19010.0), (X_DUB + 20.0, 19000.0)], 300)
street("s_arnaut_w", "district_transport", ARN_W, "Арнаутская-Запад", 2033, axis="arnaut_w", struct=water_bridges(ARN_W),
       why="схема arnaut_w (2034–2037): от Террасной улицы к дублёру А-3")
AX_LINE = fillet([(X_DUB + 20.0, 19000.0), (-120.0, 19060.0), (150.0, Z_AX), (1250.0, Z_AX), (1500.0, Z_AX)], 250)
_x_rail_ax = on(RAIL_TS, z=Z_AX)[0]
_ax_st = [((x_sb - 75.0, Z_AX), (round(_x_rail_ax + 45.0, 1), Z_AX), "overpass")]
street("s_arnaut_x", "district_transport", AX_LINE, "Арнаутская-Запад (путепровод над А-3 и Турксибом)", 2033, axis="arnaut_w",
       struct=_ax_st,
       why=MODEL + ": продолжение Арнаутской-Запад над А-3 (без съездов) и над Турксибом к Привокзальной: связь Западных "
                   "террас и делового пояса А-3 с центром Арнаутская в обход петли развязки км 61")
node("gs_arnaut_a3", (x_nb + x_sb) / 2.0, Z_AX, "grade_separation", ["s_arnaut_x", "k_" + A3_NB, "k_" + A3_SB], upper="minor",
     why_ru="Арнаутская-Запад над А-3 без съездов (до развязки км 61 450 м)")
SCHEME_CHANGES.append(("s_arnaut_x", "Арнаутская-Запад не примыкает к развязке км 61 (у трубы OSM нет западного луча — там её петля): "
                                     "от дублёра она идёт путепроводом над А-3 (z 19450) и Турксибом к Привокзальной"))
# --- дублёр А-3 (запад), Северная (ozerny_w), Террасная (terr)
DUB = fillet([(-250.0, 15900.0), (-300.0, 17600.0), (X_DUB + 20.0, 19000.0), (X_DUB, Z_OZ)], 500)
street("s_dubler", "district_transport", DUB, "Дублёр А-3 (запад)", 2033, axis="dubler_a3w",
       why="схема dubler_a3w (2034–2036): вдоль делового пояса западнее А-3, от южной границы к Озёрному проспекту")
OZW = fillet([(-2300.0, 21800.0), (-1300.0, 21720.0), (X_DUB, Z_OZ)], 400)
street("s_ozerny_w", "district_transport", OZW, "Северная улица (к террасам)", 2037, axis="ozerny_w", struct=water_bridges(OZW),
       why="схема ozerny_w (2036–2039): от Озёрного проспекта к Западным террасам")
TERR = [(-2300.0, 17700.0), (-2300.0, 19050.0), (-2300.0, 21800.0)]
street("s_terr", "district_transport", TERR, "Террасная улица", 2037, axis="terr", struct=water_bridges(TERR),
       why="схема terr (2036–2040): ось Западных террас")
SCHEME_CHANGES.append(("track_st", "улица к существующему автодрому (схема track_st) не строится: у автодрома в OSM нет ни дорог, "
                                   "ни зданий, районная улица 2 км кончалась бы у него тупиком (правило 5); подъезд — когда "
                                   "появится объект"))
# --- Мост на Восточный берег (east_link, arterial) and Восточная береговая (bereg_e, arterial) to the joint J145
J145 = next(j for j in CITY["joints"]["items"] if j.get("id") == "J145")
P_ZH = on(osm("94f53580")[0], z=17640.0)
EAST_LINK = fillet([X_YUZH, (3900.0, 15980.0), (4400.0, 15960.0), (5300.0, 16000.0), (6000.0, 16500.0), (6700.0, 17350.0),
                    (7600.0, 17620.0), (8650.0, 17660.0), P_ZH], 400)
street("s_east_link", "arterial_regulated", EAST_LINK, "Мост на Восточный берег", 2036, axis="east_link",
       struct=water_bridges(EAST_LINK),
       why="схема east_link (2035–2038): от Проспекта Green мостами через Каскелен и залив к Жетыгенской дороге")
BEREG = fillet([P_ZH, (11000.0, 17500.0), (12600.0, 17300.0), (15000.0, 17000.0), (17300.0, 16700.0),
                (J145["x"], J145["z"])], 500)
street("s_bereg_e", "arterial_regulated", BEREG, "Восточная береговая", 2037, axis="bereg_e", struct=water_bridges(BEREG),
       why="схема bereg_e (2035–2040): от Жетыгенской дороги вдоль восточного берега к стыку J145 (город за границей Green)")
node("J145", J145["x"], J145["z"], "joint", ["s_bereg_e"], joint_id="J145", to="outside")
SCHEME_CHANGES.append(("s_east_link", "восточный конец — на существующей Жетыгенской дороге (OSM 94f53580, z 17640), а не в 250 м "
                                      "восточнее неё; Восточная береговая начинается там же"))
# --- улица логистического парка (log_st): from the Жетыгенская road over the Жетыген yard into the logistics park
P_LOG = on(osm("17676108")[0], z=12420.0)
LOG = fillet([P_LOG, (8500.0, 12480.0), (9300.0, 12600.0), (11000.0, 12930.0), (12800.0, 13020.0)], 400)
street("s_log", "district_transport", LOG, "Улица логистического парка", 2039, axis="log_st",
       struct=rail_overpasses(LOG) + water_bridges(LOG),
       why="схема log_st (2038–2041): от Жетыгенской дороги путепроводом над путями станции Жетыген в логистический парк "
           "(севернее Турксиба: у схемы конец линии упирался в пути у x 12900)")
SCHEME_CHANGES.append(("s_log", "улица логистического парка идёт по логистическому парку севернее Турксиба (z 12 930–13 020) "
                                "и над путями станции Жетыген путепроводом; у схемы восточный конец лежал на путях"))

# --- the existing km 61 trumpet (OSM): kept as it is; Арнаутская starts at its ramp terminal
node("ic_km61", 424.9, 18983.6, "trumpet", [k_of("62d0b51b"), k_of("f811d203"), k_of("a6a55552")], keep_existing=True,
     registry_id="interchange_a3_km61_0", osm_ids=[SH[r] for r in ("de5e8724", "fcf18c77", "b297434e", "c6350f3c", "20371606")],
     why_ru="существующая развязка А-3 км 61 (OSM, труба): съезды как в данных; к её концевому узлу приходит Арнаутская")

FRAME_IDS = [s["id"] for s in STREETS if s["_layer"] == "frame"]

# ===================================================================================================== 3. local streets
KEEP_POLY = Polygon()
NO_HOST = {"expressway", "ramp", "pedestrian_street", "bike_path", "boulevard", "driveway_main", "driveway_secondary"}
D_IN = 10.0                     # edge streets run 10 m inside the quarter's border (local red line 15 m: half 7.5 + 2.5)
EXP_HALF = 45.0                 # expressways: half red line 25 + 20 m (no quarter edge right at the carriageway)

# existing roads inside new quarters are replaced by the new streets (tracks are not built anyway)
DEV_IN = Z.DEV.difference(VILL)
RETIRED = []
for oid, (g, p) in OSM.items():
    if p.get("class") in ("motorway", "tertiary", "secondary", "primary") or oid in KEEP_IDS:
        continue
    gi = g.intersection(GREEN)
    if gi.length < 1.0:
        continue
    if p.get("class") == "track" and gi.intersects(DEV_IN):
        RETIRED.append(oid)
    elif gi.intersection(DEV_IN.buffer(5)).length > 0.5 * gi.length and not houses_hit(gi.buffer(30.0)):
        RETIRED.append(oid)                      # a road that serves existing houses stays
# OSM bridges that lead nowhere in the source itself (bridge=yes, one end touches no road): stubs of a field track that OSM
# does not have; kept they would be a bridge ending in the air (rule 9)
BRIDGE_STUBS = {"f258c9e8-ad1e-4b5f-a5ab-3189f1260208": (-8319, 27745), "e5a8b0fc-a851-4f77-82c4-e4698e25d8a1": (-8873, 26143)}
for oid, at in BRIDGE_STUBS.items():
    if oid in OSM and oid not in RETIRED:
        RETIRED.append(oid)
        SCHEME_CHANGES.append((f"osm_{oid[:8]}", f"мостик OSM {oid[:8]} у ({at[0]}, {at[1]}) ({OSM[oid][0].length:.0f} м, bridge=yes) "
                                                 "в источнике одним концом ни к чему не примыкает (обрывок полевой дороги, "
                                                 "которой в OSM нет) — в карту не берётся (replaced_osm)"))
RETIRED_SET = set(RETIRED)
for oid, (g, p) in sorted(OSM.items()):
    if p.get("class") != "service" or p.get("sub") not in ("driveway", "parking_aisle", "alley") or oid in KEEP_IDS \
            or oid in RETIRED_SET:
        continue
    parts = osm_line(oid)
    if not parts or max(q.length for q in parts) < 3.0:
        continue
    q = max(parts, key=lambda q_: q_.length)
    cls = "village_lane" if q.intersection(VILL).length > 0.5 * q.length else "local_secondary"
    street("v_" + oid[:8], cls, q.coords, "проезд (OSM)", 2025, source="keep_existing:" + oid, years=C.EXISTING, layer="osm",
           why=f"существующий проезд OSM (service/{p.get('sub')}): класс {cls} вместо driveway_secondary, который CONTRACT §8 "
               "не использует")
    KEEP_IDS[oid] = "v_" + oid[:8]
OSM_HOST = []                   # [(oid, line, class)] existing roads that stay and take new streets
for oid in sorted(HOST_OSM - RETIRED_SET - set(KEEP_IDS)):
    g, p = OSM[oid]
    cls = {"service": "driveway_main", "living_street": "village_secondary"}.get(p["class"], "village_secondary")
    if g.intersection(VILL).length <= 0.5 * g.length and p["class"] in ("residential", "unclassified", "unknown"):
        cls = "local"
    for q in osm_line(oid):
        OSM_HOST.append((oid, q, cls))


def all_lines(include_osm=True):
    """[(sid, LineString, class, half red line)] of every street now in the network (new, kept, OSM roads that stay)."""
    out = []
    for s in STREETS:
        out.append((s["id"], LineString(s["line"]), s["class"], red_w(s["class"], s.get("profile")) / 2.0))
    if include_osm:
        for oid, q, cls in OSM_HOST:
            out.append(("osm:" + oid, q, cls, red_w(cls) / 2.0))
    return out


def corridors(lines):
    polys = []
    for sid, L, cls, half in lines:
        h = EXP_HALF if cls == "expressway" else (12.0 if cls == "ramp" else half)
        polys.append(L.buffer(h, cap_style=2))
    return unary_union(polys)


def _dir_deg(lines):
    """Dominant direction (degrees mod 90) of a set of lines, weighted by length."""
    hist = np.zeros(90)
    flat = []
    for L in lines:
        flat += [q for q in getattr(L, "geoms", [L]) if q.geom_type == "LineString"]
    for L in flat:
        P = np.asarray(L.coords)
        for a, b in zip(P[:-1], P[1:]):
            v = b - a
            ln = float(np.hypot(*v))
            if ln < 1:
                continue
            ang = math.degrees(math.atan2(v[0], v[1])) % 90.0
            hist[int(ang) % 90] += ln
    if hist.sum() < 1:
        return None
    sm = np.array([hist[[(i + k) % 90 for k in range(-3, 4)]].sum() for i in range(90)])
    i = int(np.argmax(sm))
    w = [(i + k) % 90 for k in range(-3, 4)]
    ang = np.array([(i + k) for k in range(-3, 4)], float)
    return float((ang * hist[w]).sum() / max(hist[w].sum(), 1e-9)) % 90.0


def _rot(theta):
    t = math.radians(theta)
    u = np.array([math.sin(t), math.cos(t)])          # first axis: bearing theta
    v = np.array([math.cos(t), -math.sin(t)])         # across
    return u, v


def _ray_hit(p, dvec, lines, reach):
    """First point where the ray p + t·dvec (0 < t ≤ reach) meets one of lines."""
    seg = LineString([p, (p[0] + dvec[0] * reach, p[1] + dvec[1] * reach)])
    best = None
    for L in lines:
        x = seg.intersection(L)
        if x.is_empty:
            continue
        for q in getattr(x, "geoms", [x]):
            if q.geom_type != "Point":
                continue
            t = math.dist(p, (q.x, q.y))
            if t > 0.3 and (best is None or t < best[0]):
                best = (t, (q.x, q.y))
    return best[1] if best else None


GEN_LOG = []
STATIONS_AT = []                 # [(x, z)] LRT stations: no local street crosses the line within ±STATION_GAP of them
STATION_GAP = 75.0
UNSERVED = []                    # [Polygon] island quarters no street can reach: the builder turns them into reserve
LRT_RAMPS = []                   # [Polygon] where the LRT climbs or descends between ground and viaduct: no local street crosses
GRID_BY_ZONE = {"theme": (300.0, 300.0), "resort_e": (240.0, 220.0), "expo_1": (240.0, 220.0), "expo_2": (240.0, 220.0),
                "ircc": (220.0, 200.0)}


def generate_local(stations=(), barriers=None, lrt_line=None):
    """Edge streets and grids of every new quarter (pieces of the development zones between streets, water and villages).
    stations: LRT stations (no cross street within STATION_GAP); barriers: land kept free (the LRT corridor off the streets)."""
    STATIONS_AT[:] = list(stations)
    lines = all_lines()
    host = [(sid, L, cls, half) for sid, L, cls, half in lines if cls not in NO_HOST]
    corr = corridors(lines)
    if barriers is not None:
        corr = corr.union(barriers)
    region = DEV_IN.difference(corr).difference(WATER_STRIP).difference(KEEP_POLY.buffer(5)).intersection(GREEN.buffer(-5))
    pieces = [p for p in getattr(region, "geoms", [region]) if p.area > 15000.0]
    pieces.sort(key=lambda p: (-p.centroid.y, p.centroid.x))
    host_tree = shapely.STRtree([L for _, L, _, _ in host])
    made = 0
    later = []
    for k, piece in enumerate(pieces):
        zs = sorted(((z["poly"].intersection(piece).area, z) for z in Z.ZPLAN if z["use"] in Z.GRID and z["src"] == "v0"),
                    key=lambda t: -t[0])
        if not zs or zs[0][0] < 1000:
            continue
        zone = zs[0][1]
        S1, S2 = GRID_BY_ZONE.get(zone["id"], Z.GRID[zone["use"]])
        near = [host[i][1] for i in host_tree.query(piece.buffer(60))]
        theta = _dir_deg([L.intersection(piece.buffer(60)) for L in near if not L.intersection(piece.buffer(60)).is_empty])
        if theta is None:
            mrr = piece.minimum_rotated_rectangle
            c = np.asarray(mrr.exterior.coords)
            v = c[1] - c[0]
            theta = math.degrees(math.atan2(v[0], v[1])) % 90.0
        tag = f"p{k + 1:02d}"
        defer = []
        made += _piece(tag, piece, zone, zs, theta, S1, S2, host, lrt_line, defer=defer)
        if defer:
            later.append((tag, piece, zone, zs, theta, S1, S2, defer))
    if later:
        host = [(sid, L, cls, half) for sid, L, cls, half in all_lines() if cls not in NO_HOST]
        for tag, piece, zone, zs, theta, S1, S2, defer in later:
            made += _piece(tag, piece, zone, zs, theta, S1, S2, host, lrt_line, only_parts=set(defer))
    return made


def _fronted(pt, host, host_tree):
    best = 1e9
    for i in host_tree.query(Point(pt).buffer(D_IN + 40)):
        sid, L, cls, half = host[i]
        best = min(best, L.distance(Point(pt)) - half)
    return best <= D_IN + 6.0


HOUSE_GAP = 10.5     # m: a new street's axis keeps this far from an existing house (7.5 m half red line + 3 m)


def _detour(LL, hh, inside):
    """The line LL with every crossing of a house (hh) replaced by the way round it at HOUSE_GAP, on the side that lies in
    `inside` (the quarter); a house the way round touches joins the group (up to 5 rounds); None when a house sits at the
    line's end or no way round lies in the quarter."""
    hh = list(hh)
    for _ in range(5):
        out = _detour1(LL, hh, inside)
        if out is None or not out.is_simple:
            return None
        more = [b for b in houses_hit(out.buffer(7.5)) if not any(b.equals(h) for h in hh)]
        if not more:
            return out
        hh += more
    return None


def _detour1(LL, hh, inside):
    U_ = unary_union([b.buffer(HOUSE_GAP, quad_segs=4) for b in hh])
    out = LL
    for poly in sorted(getattr(U_, "geoms", [U_]), key=lambda g: LL.project(g.centroid)):
        if not out.intersects(poly):
            continue
        xs = out.intersection(poly.exterior)
        ch = sorted(out.project(q) for q in getattr(xs, "geoms", [xs]) if q.geom_type == "Point")
        if len(ch) < 2 or ch[0] < 1.0 or ch[-1] > out.length - 1.0:
            return None
        a, b = out.interpolate(ch[0]), out.interpolate(ch[-1])
        ring = LineString(poly.exterior.coords)
        Lr = ring.length
        sa, sb = ring.project(a), ring.project(b)

        def fwd(s0, s1):
            if s0 <= s1:
                return list(substring(ring, s0, s1).coords)
            return list(substring(ring, s0, Lr).coords) + list(substring(ring, 0, s1).coords)[1:]
        arcs = [fwd(sa, sb), fwd(sb, sa)[::-1]]
        arcs = [c for c in arcs if len(c) >= 2 and inside.contains(LineString(c).interpolate(0.5, normalized=True))]
        if not arcs:
            return None
        arc = min(arcs, key=lambda c: LineString(c).length)
        out = LineString(list(substring(out, 0, ch[0]).coords) + arc[1:-1] + list(substring(out, ch[-1], out.length).coords))
    return out.simplify(1.0)


def _piece(tag, piece, zone, zs, theta, S1, S2, host, lrt_line, defer=None, only_parts=None):
    host_tree = shapely.STRtree([L for _, L, _, _ in host])
    host_lines = [L for _, L, _, _ in host]
    inner = piece.buffer(-D_IN).simplify(1.0)
    parts = [q for q in getattr(inner, "geoms", [inner]) if q.geom_type == "Polygon" and q.area > 8000.0]
    yb = max(2026, int(zone["years"][0]) - 1)
    cls_local = "industrial" if zone["use"] in ("logistics", "industry") else "local"
    n = 0
    for j, P in enumerate(parts):
        if only_parts is not None and j not in only_parts:
            continue
        ring = P.exterior
        Lr = ring.length
        m = max(int(Lr / 5.0), 12)
        pts = [ring.interpolate(Lr * i / m) for i in range(m)]
        fr = [_fronted((q.x, q.y), host, host_tree) for q in pts]
        edge_lines = []
        if not any(fr):
            barrier = [L for _, L, c_, _ in all_lines(include_osm=False) if c_ in ("expressway", "ramp")]
            cands = []
            for i in host_tree.query(P.buffer(400)):
                sid, L, cls, half = host[i]
                a, b = shapely.ops.nearest_points(ring, L)
                cands.append((a.distance(b), a, b, sid))
            best = None
            for dd, a, b, sid in sorted(cands, key=lambda t: t[0]):
                if dd > 300:
                    break
                conn = LineString([a, b])
                if any(conn.intersects(X) for X in barrier) or houses_hit(conn.buffer(7.5)) or conn.intersects(RAIL):
                    continue
                best = (dd, a, b, sid)
                break
            if best is None and defer is not None:
                defer.append(j)
                continue
            if best is None:
                UNSERVED.append(P)
                GEN_LOG.append({"what": "квартал без улицы рядом (или путь к ней через трассу / дома): оставлен без сети (резерв)",
                                "piece": tag, "ha": round(piece.area / 1e4, 1), "at": [round(v) for v in P.centroid.coords[0]]})
                continue
            dd, a, b, sid = best
            s0 = ring.project(a)
            ringL = LineString(list(ring.coords))
            half1 = substring(ringL, s0, min(Lr, s0 + Lr / 2)) if s0 + Lr / 2 <= Lr else LineString(
                list(substring(ringL, s0, Lr).coords) + list(substring(ringL, 0, s0 + Lr / 2 - Lr).coords)[1:])
            e = s0 + Lr / 2
            if e <= Lr:
                half2 = LineString(list(substring(ringL, e, Lr).coords) + list(substring(ringL, 0, s0).coords)[1:])
            else:
                half2 = substring(ringL, e - Lr, s0)
            edge_lines = [list(half1.coords), list(half2.coords)]
            street(f"g_{tag}_{j}_c", cls_local, [(a.x, a.y), (b.x, b.y)], "соединительная улица квартала", yb, layer="edge",
                   struct=water_bridges([(a.x, a.y), (b.x, b.y)]),
                   why=MODEL + ": квартал окружён сёлами, парками или водой — кольцевая улица и выезд к ближайшей улице")
        else:
            i0 = next((i for i in range(m) if fr[i]), 0)
            order = [(i0 + t) % m for t in range(m)]
            runs, cur = [], []
            for i in order:
                if not fr[i]:
                    cur.append(i)
                elif cur:
                    runs.append(cur); cur = []
            if cur:
                runs.append(cur)
            used_ext = set()
            for run in runs:
                if len(run) * Lr / m < 30.0:
                    continue
                a_i, b_i = (run[0] - 1) % m, (run[-1] + 1) % m
                seq = [a_i] + run + [b_i]
                line = [(pts[i].x, pts[i].y) for i in seq]
                for end in (0, -1):
                    q = Point(line[end])
                    cand = [(host[i][1].distance(q), host[i][1]) for i in host_tree.query(q.buffer(D_IN + 40))]
                    if cand:
                        L = min(cand, key=lambda t: t[0])[1]
                        f = L.interpolate(L.project(q))
                        key = (round(q.x, 1), round(q.y, 1))
                        if key in used_ext:
                            continue
                        used_ext.add(key)
                        if end == 0:
                            line.insert(0, (f.x, f.y))
                        else:
                            line.append((f.x, f.y))
                edge_lines.append(line)
        for i, line in enumerate(edge_lines):
            LL = LineString(line).simplify(1.5)
            hh = houses_hit(LL.buffer(7.5))
            why = MODEL + ": улица по краю квартала (" + zone["id"] + ") вдоль села, парка, воды или трассы"
            runs_ = [LL]
            if hh:
                dt = _detour(LL, hh, piece)
                if dt is not None:
                    runs_ = [dt]
                    GEN_LOG.append({"what": "краевая улица обходит дома", "piece": tag, "n": len(hh),
                                    "at": [round(v) for v in hh[0].centroid.coords[0]]})
                else:
                    cut = LL.difference(unary_union([b.buffer(HOUSE_GAP) for b in hh]))
                    runs_ = [q for q in getattr(cut, "geoms", [cut]) if q.geom_type == "LineString" and q.length >= 30.0]
                    GEN_LOG.append({"what": "краевая улица задевает дома: разрезана у домов", "piece": tag, "n": len(hh),
                                    "parts": len(runs_), "at": [round(v) for v in hh[0].centroid.coords[0]]})
            for pi, q in enumerate(runs_):
                if any(q.intersects(r) for r in LRT_RAMPS) and lrt_line is not None and q.intersects(lrt_line):
                    GEN_LOG.append({"what": "краевая улица пересекала рампу ЛРТ: не строится", "piece": tag})
                    continue
                if q.intersects(RAIL):
                    cut = q.difference(RAIL.buffer(25.0))
                    q = max([g for g in getattr(cut, "geoms", [cut]) if g.geom_type == "LineString"] or [LineString()],
                            key=lambda g: g.length)
                    if q.is_empty or q.length < 30.0:
                        continue
                street(f"e_{tag}_{j}_{i}" + (f"_{pi}" if pi else ""), cls_local, q.coords, "улица по краю квартала", yb,
                       layer="edge", why=why, struct=water_bridges(list(q.coords)))
                n += 1
        # grid
        u, v = _rot(theta)
        c = np.asarray(P.centroid.coords[0])
        R = max(P.bounds[2] - P.bounds[0], P.bounds[3] - P.bounds[1]) * 0.8 + 50
        edge_now = [LineString(s["line"]) for s in STREETS if s["id"].startswith(f"e_{tag}_{j}_")]
        guide = unary_union([ring] + edge_now)
        for fam, (dvec, nvec, S) in enumerate(((u, v, S2), (v, u, S1))):
            o0 = float(np.dot(c, nvec))
            k0, k1 = int(math.floor((o0 - R) / S)), int(math.ceil((o0 + R) / S))
            for kk in range(k0, k1 + 1):
                off = kk * S + S / 2.0
                t0 = float(np.dot(c, dvec))
                p0 = nvec * off + dvec * (t0 - R)
                p1 = nvec * off + dvec * (t0 + R)
                seg = LineString([tuple(p0), tuple(p1)]).intersection(P)
                for qi, q in enumerate(getattr(seg, "geoms", [seg])):
                    if q.geom_type != "LineString" or q.length < 45.0:
                        continue
                    sm = [q.interpolate(f, normalized=True) for f in (0.2, 0.35, 0.5, 0.65, 0.8)]
                    dist = sorted(guide.distance(x) for x in sm)
                    if dist[2] < 0.45 * S:
                        continue
                    line = list(q.coords)
                    for end in (0, -1):
                        e = line[end]
                        if any(E.distance(Point(e)) < 1.0 for E in edge_now):
                            continue            # ends on the quarter's own edge street: a T there, not across it
                        d_out = -dvec if end == 0 else dvec
                        hit = _ray_hit(e, d_out, host_lines + edge_now, D_IN + 45.0)
                        if hit is not None:
                            if end == 0:
                                line.insert(0, hit)
                            else:
                                line.append(hit)
                    LL = LineString(line)
                    if LL.intersects(RAIL):
                        continue
                    hh = houses_hit(LL.buffer(7.5))
                    if hh:
                        dt = _detour(LL, hh, piece)
                        if dt is None:
                            GEN_LOG.append({"what": "линия сетки задевает дом: снята", "piece": tag, "at": [round(v_) for v_ in LL.centroid.coords[0]]})
                            continue
                        GEN_LOG.append({"what": "линия сетки обходит дом", "piece": tag, "at": [round(v_) for v_ in hh[0].centroid.coords[0]]})
                        LL = dt
                    if lrt_line is not None and LL.intersects(lrt_line):
                        xpt = LL.intersection(lrt_line)
                        xpt = xpt if xpt.geom_type == "Point" else xpt.centroid
                        if any(math.dist((xpt.x, xpt.y), st) < STATION_GAP for st in STATIONS_AT):
                            continue
                        if any(r.contains(xpt) for r in LRT_RAMPS):
                            GEN_LOG.append({"what": "линия сетки пересекала рампу ЛРТ: снята", "piece": tag, "at": [round(xpt.x), round(xpt.y)]})
                            continue
                    street(f"g_{tag}_{j}_{fam}{kk - k0:02d}" + (f"_{qi}" if qi else ""), cls_local, LL.coords, "улица квартала", yb, layer="grid",
                           why=MODEL + f": сетка квартала зоны {zone['id']} (шаг {S:.0f} м)", struct=water_bridges(list(LL.coords)))
                    n += 1
    return n


# ===================================================================================================== 4. post-pass
GEN = ("edge", "grid")
NO_JUNCTION = {"expressway", "ramp"}


def _lines_except(sid):
    out = [(s["id"], LineString(s["line"]), s["class"]) for s in STREETS if s["id"] != sid]
    out += [("osm:" + oid, q, cls) for oid, q, cls in OSM_HOST]
    return out


def _attached(pt, others, tree, extra_ok):
    P = Point(pt)
    for i in tree.query(P.buffer(0.6)):
        sid, L, cls = others[i]
        if cls in NO_JUNCTION:
            continue
        if L.distance(P) < 0.5:
            return True
    return extra_ok(P)


def _cut_points(L, others, tree, s):
    """Chainages along L where it meets another street in one level (not expressways or ramps, not over its own spans)."""
    spans = []
    for st in s.get("struct") or []:
        a, b = L.project(Point(st["from"])), L.project(Point(st["to"]))
        spans.append((min(a, b), max(a, b)))
    ch = []
    for i in tree.query(L.buffer(0.6)):
        sid, M, cls = others[i]
        if cls in NO_JUNCTION:
            continue
        x = L.intersection(M.buffer(0.3))
        for q in getattr(x, "geoms", [x]):
            if q.is_empty:
                continue
            c = L.project(q.centroid) if q.geom_type != "Point" else L.project(q)
            if not any(a - 1 <= c <= b + 1 for a, b in spans):
                ch.append(c)
    return sorted(ch)


def trim_free_ends(extra_ok, layers=GEN, min_len=25.0, log=None):
    """Generated streets whose end is on no other street: cut back to their last junction (both ends), drop what is left
    shorter than min_len. Repeated until nothing changes (a dropped street can free the ends of others)."""
    changed, rounds = True, 0
    while changed and rounds < 12:
        changed, rounds = False, rounds + 1
        others_all = [(s["id"], LineString(s["line"]), s["class"]) for s in STREETS]
        others_all += [("osm:" + oid, q, cls) for oid, q, cls in OSM_HOST]
        tree_all = shapely.STRtree([L for _, L, _ in others_all])
        drop = []
        for k, s in enumerate(STREETS):
            if s["_layer"] not in layers:
                continue
            L = LineString(s["line"])
            near = [int(i) for i in tree_all.query(L.buffer(1.0)) if others_all[int(i)][0] != s["id"]]
            oth = [others_all[i] for i in near]
            ot = shapely.STRtree([q for _, q, _ in oth]) if oth else shapely.STRtree([LineString([(1e7, 1e7), (1e7 + 1, 1e7)])])
            if not oth:
                oth = [("~", LineString([(1e7, 1e7), (1e7 + 1, 1e7)]), "x")]
            f0 = not _attached(s["line"][0], oth, ot, extra_ok)
            f1 = not _attached(s["line"][-1], oth, ot, extra_ok)
            if not (f0 or f1):
                continue
            ch = [c for c in _cut_points(L, oth, ot, s) if 0.5 < c < L.length - 0.5]
            a = ch[0] if (f0 and ch) else (0.0 if not f0 else None)
            b = ch[-1] if (f1 and ch) else (L.length if not f1 else None)
            if a is None or b is None or b - a < min_len:
                drop.append(k)
                if log is not None:
                    log.append({"what": "улица без связи на конце: снята", "id": s["id"]})
                changed = True
                continue
            q = substring(L, a, b)
            s["line"] = [[round(x, 1), round(z, 1)] for x, z in q.coords]
            s["struct"] = [st for st in s.get("struct") or [] if q.distance(Point(st["from"])) < 1 and q.distance(Point(st["to"])) < 1]
            changed = True
        for k in sorted(drop, reverse=True):
            SID.pop(STREETS[k]["id"], None)
            del STREETS[k]
    return rounds


def snap_ends(layers=GEN, tol=6.0, log=None):
    """Generated street ends that sit on a street a few metres from another street's end on that same street: moved onto
    that end, so the place is one junction, not two crossings a metre or five apart."""
    moved = 0
    allL = [(s["id"], LineString(s["line"]), s["class"]) for s in STREETS] + [("osm:" + oid, q, cls) for oid, q, cls in OSM_HOST]
    tree = shapely.STRtree([q for _, q, _ in allL])
    ends = [Point(q.coords[0]) for _, q, _ in allL] + [Point(q.coords[-1]) for _, q, _ in allL]
    owner = [sid for sid, _, _ in allL] * 2
    which = [0] * len(allL) + [-1] * len(allL)
    etree = shapely.STRtree(ends)

    def end_now(i):           # the end as it is now (an end moved earlier in this pass is where it was moved to)
        x = SID.get(owner[i])
        return Point(x["line"][which[i]]) if x is not None else ends[i]
    for s in STREETS:
        if s["_layer"] not in layers:
            continue
        for e in (0, -1):
            P = Point(s["line"][e])
            on_ = [allL[i][1] for i in tree.query(P.buffer(0.6)) if allL[i][0] != s["id"] and allL[i][2] not in NO_JUNCTION
                   and allL[i][1].distance(P) < 0.5]
            if not on_:
                continue
            near = sorted(((end_now(i).distance(P), end_now(i)) for i in etree.query(P.buffer(tol + 7.0)) if owner[i] != s["id"]),
                          key=lambda t: t[0])
            if not near or near[0][0] <= 0.5:
                continue
            for d, Q in near:
                if d >= tol:
                    break
                if any(M.distance(Q) < 0.5 for M in on_):
                    L0 = LineString(s["line"])
                    if L0.length > 40.0:          # keep the rest of the line where it was (T-junctions along it stay on it)
                        k = L0.interpolate(15.0 if e == 0 else L0.length - 15.0)
                        cut = 15.0 if e == 0 else L0.length - 15.0
                        cs = [L0.project(Point(c)) for c in s["line"]]
                        if e == 0:
                            s["line"] = [s["line"][0]] + [[round(k.x, 1), round(k.y, 1)]] + \
                                [c for c, ch in zip(s["line"], cs) if ch > cut + 0.5]
                        else:
                            s["line"] = [c for c, ch in zip(s["line"], cs) if ch < cut - 0.5] + \
                                [[round(k.x, 1), round(k.y, 1)], s["line"][-1]]
                    s["line"][e] = [round(Q.x, 1), round(Q.y, 1)]
                    moved += 1
                    if log is not None:
                        log.append({"what": "конец улицы перенесён на соседний перекрёсток (один узел вместо двух)",
                                    "id": s["id"], "m": round(d, 1), "at": [round(Q.x), round(Q.y)]})
                    break
    moved += reattach_ends(layers, log=log)
    return moved


def reattach_ends(layers=GEN, tol=2.5, log=None):
    """Generated street ends left a metre or two off the street they met (that street's end was moved by snap_ends):
    moved onto it again."""
    n = 0
    allL = [(s["id"], LineString(s["line"]), s["class"]) for s in STREETS] + [("osm:" + oid, q, cls) for oid, q, cls in OSM_HOST]
    tree = shapely.STRtree([q for _, q, _ in allL])
    for s in STREETS:
        if s["_layer"] not in layers:
            continue
        for e in (0, -1):
            P = Point(s["line"][e])
            near = sorted(((allL[i][1].distance(P), allL[i][1]) for i in tree.query(P.buffer(tol))
                           if allL[i][0] != s["id"] and allL[i][2] not in NO_JUNCTION), key=lambda t: t[0])
            if not near or near[0][0] < 0.3 or near[0][0] > tol:
                continue
            M = near[0][1]
            Q = M.interpolate(M.project(P))
            s["line"][e] = [round(Q.x, 2), round(Q.y, 2)]
            n += 1
            if log is not None:
                log.append({"what": "конец улицы возвращён на улицу после переноса узла", "id": s["id"], "m": round(near[0][0], 1)})
    return n


def merge_through(layers=GEN, log=None):
    """Two generated streets of one class and years that meet end to end (and no other street ends there) become one
    street: two quarters' streets meeting on a street that opens later are one through street until then (gen_network
    would take each end to its own side of that street, two blind ends in the meantime)."""
    total = 0
    for _round in range(12):
        gen = [s for s in STREETS if s["_layer"] in layers]
        ends_all = [(s["id"], e, Point(s["line"][e])) for s in STREETS for e in (0, -1)]
        tree = shapely.STRtree([p for _, _, p in ends_all])
        used, n = set(), 0
        for s in gen:
            if s["id"] in used:
                continue
            for e in (0, -1):
                P = Point(s["line"][e])
                at = [ends_all[i] for i in tree.query(P.buffer(0.5)) if ends_all[i][2].distance(P) < 0.5]
                if len(at) != 2:
                    continue
                o = [a for a in at if a[0] != s["id"]]
                if len(o) != 1 or o[0][0] in used:
                    continue
                t = SID.get(o[0][0])
                if t is None or t["_layer"] not in layers or t["class"] != s["class"] or list(t["years"]) != list(s["years"]):
                    continue
                A = s["line"] if e == -1 else s["line"][::-1]
                B = t["line"] if o[0][1] == 0 else t["line"][::-1]
                da = np.array(A[-2], float) - np.array(A[-1], float)
                db = np.array(B[1], float) - np.array(B[0], float)
                cosang = float(da @ db) / (np.linalg.norm(da) * np.linalg.norm(db) + 1e-9)
                if cosang > 0.5:
                    continue                # folds back sharper than 60°
                if Point(A[0]).distance(Point(B[-1])) < 1.0:
                    continue                # would close a ring (gen_network takes no closed way)
                M = LineString([tuple(p) for p in A] + [tuple(p) for p in B[1:]])
                if not M.is_simple:
                    continue
                s["line"] = [list(p) for p in M.coords]
                s["struct"] = (s.get("struct") or []) + (t.get("struct") or [])
                s["why"] = (s.get("why") or "") + f"; продолжена улицей {t['id']} (одна улица через перекрёсток)"
                STREETS.remove(t)
                SID.pop(t["id"], None)
                used |= {s["id"], t["id"]}
                n += 1
                if log is not None:
                    log.append({"what": "две улицы кварталов, сходящиеся концами, — одна сквозная улица", "id": s["id"],
                                "with": t["id"], "at": [round(P.x), round(P.y)]})
                break
        total += n
        if not n:
            break
    return total


LANE_REACH = 25.0      # m: a house is served when a street is this close (rule 12, fire_access.max_distance_to_building_m)
LANE_MAX = 150.0       # m: dead-end limit of a village lane (fire_access.dead_end_max_m)
LINK_MAX = 150.0       # m: longest through link added at the dead end of an existing road (fire_access.dead_end_max_m)
LINK_MIN = 15.0        # m: no shorter link (a street of a few metres between two roads is not a street)
DEAD_END_OK = {"driveway_main", "driveway_secondary", "local", "local_secondary", "village_lane"}   # rule 5: may end ≤ 150 m


def house_lanes(log=None):
    """Existing houses outside the villages and outside the new quarters with no street within LANE_REACH: a village lane
    from the nearest street toward the group (≤ LANE_MAX, never through a house, never across an expressway, a ramp,
    the railway or water). Groups = houses within 40 m. (In Green every existing house stands in a village zone.)"""
    hs = [h for h in HOUSES if GREEN.contains(h.centroid) and not VILL.contains(h.centroid)
          and not Z.DEV.buffer(-5.0).contains(h.centroid)]
    if not hs:
        return 0
    lines = [(s["id"], LineString(s["line"])) for s in STREETS if s["class"] not in ("expressway", "ramp", "pedestrian_street", "bike_path")]
    lines += [("osm:" + oid, q) for oid, q, cls in OSM_HOST]
    lt = shapely.STRtree([q for _, q in lines])
    barrier = unary_union([LineString(s["line"]) for s in STREETS if s["class"] in ("expressway", "ramp")])
    far = [h for h in hs if lines[int(lt.query_nearest(h)[0])][1].distance(h) > LANE_REACH]
    if not far:
        return 0
    grp = unary_union([h.buffer(20.0) for h in far])
    made = 0
    for k, G in enumerate(getattr(grp, "geoms", [grp])):
        mine = [h for h in far if G.contains(h.centroid)]
        hu = unary_union(mine)
        i = int(lt.query_nearest(hu)[0])
        sid, L = lines[i]
        a, b = shapely.ops.nearest_points(L, hu)
        d = a.distance(b)
        rec = {"at": [round(b.x), round(b.y)], "houses": len(mine), "host": sid, "m": round(d)}
        if d - red_w("village_lane") / 2.0 - 1.5 > LANE_MAX:
            if log is not None:
                log.append({"what": "дом вне села дальше 150 м от улицы: проулка нет (ждёт решения)", **rec})
            continue
        rh = red_w("village_lane") / 2.0
        end = LineString([a, b]).interpolate(d - rh - 1.5)
        lane = LineString([(a.x, a.y), (end.x, end.y)])
        if lane.length < LINK_MIN - 0.5 or houses_hit(lane.buffer(rh + 1.0)) or lane.crosses(barrier) or lane.intersects(WATER_POLY) \
                or lane.intersects(RAIL):
            if log is not None:
                log.append({"what": "дом вне села: проулок к нему пересёк бы дом, трассу или воду — не строится", **rec})
            continue
        made += 1
        street(f"v_lane_{made:02d}", "village_lane", lane.coords, "проезд к существующему дому", 2026, layer="lane",
               why=MODEL + f": существующий дом вне села без улицы в {LANE_REACH:.0f} м — проулок от {sid} (≤ {LANE_MAX:.0f} м, "
                           "тупик класса village_lane)")
        if log is not None:
            log.append({"what": "проулок к существующему дому вне села", "id": f"v_lane_{made:02d}", **rec})
    return made


def link_dead_ends(log=None):
    """Existing roads (kept OSM streets and OSM roads that stay) that end in nothing inside Green: a straight through link
    from the dead end to the nearest other street — straight ahead first, else the shortest — ≤ LINK_MAX, never through
    a house, never across an expressway, a ramp, the railway or water, never back along its own road or along another
    street. Class: village lane in a village, local elsewhere. A dead end with no such link stays as it is (logged)."""
    lines = [(s["id"], LineString(s["line"]), s["class"]) for s in STREETS if s["class"] not in ("pedestrian_street", "bike_path")]
    lines += [("osm:" + oid, q, cls) for oid, q, cls in OSM_HOST]
    tree = shapely.STRtree([q for _, q, _ in lines])
    barrier = unary_union([q for _, q, c in lines if c in ("expressway", "ramp")])
    links = []
    made, kept = 0, 0
    for i, (sid, L, cls) in enumerate(lines):
        existing = sid.startswith("osm:") or SID[sid]["_layer"] == "osm"
        if not existing or cls in ("expressway", "ramp"):
            continue
        for e in (0, -1):
            E = Point(L.coords[e])
            if GREEN.exterior.distance(E) < 3.0:
                continue
            if any(j != i and lines[j][1].distance(E) < 0.5 for j in tree.query(E.buffer(0.6))) \
                    or any(k.distance(E) < 0.5 for k in links):
                continue
            near_i = [int(j) for j in tree.query(L.buffer(1.0)) if int(j) != i]
            oth = [lines[j] for j in near_i] or [("~", LineString([(1e7, 1e7), (1e7 + 1, 1e7)]), "x")]
            ch = _cut_points(L, oth, shapely.STRtree([q for _, q, _ in oth]), {"struct": []})
            s_e = 0.0 if e == 0 else L.length
            branch = min((abs(c - s_e) for c in ch if abs(c - s_e) > 0.5), default=L.length)
            if cls in DEAD_END_OK and branch <= LINK_MAX:
                continue
            Lc = L if e == -1 else LineString(L.coords[::-1])
            back = Lc.interpolate(max(Lc.length - 20.0, 0.0))
            dv = np.array([E.x - back.x, E.y - back.y])
            dv = dv / (np.hypot(*dv) or 1.0)
            cands = []
            ray = LineString([(E.x, E.y), (E.x + dv[0] * LINK_MAX, E.y + dv[1] * LINK_MAX)])
            for j in tree.query(ray.buffer(1.0)):
                if j == i or lines[j][2] in ("expressway", "ramp"):
                    continue
                x = ray.intersection(lines[j][1])
                for q in getattr(x, "geoms", [x]):
                    if q.geom_type == "Point" and q.distance(E) > 2.0:
                        cands.append((q.distance(E), 0, q, lines[j][0]))
            for j in tree.query(E.buffer(LINK_MAX)):
                if j == i or lines[j][2] in ("expressway", "ramp"):
                    continue
                q = lines[j][1].interpolate(lines[j][1].project(E))
                if 2.0 < q.distance(E) <= LINK_MAX:
                    cands.append((q.distance(E), 1, q, lines[j][0]))
            done = False
            for d, kind, q, host in sorted(cands, key=lambda t: (t[1], t[0])):
                if d < LINK_MIN:
                    continue
                link = LineString([(E.x, E.y), (q.x, q.y)])
                u = np.array([q.x - E.x, q.y - E.y]) / d
                if float(u @ dv) < -0.26:
                    continue
                inner = substring(link, 1.0, link.length - 1.0)
                near = [lines[j][1] for j in tree.query(inner.buffer(3.0)) if lines[j][0] != host] + links
                if any(M.intersects(inner) for M in [lines[j][1] for j in tree.query(inner)]) \
                        or any(M.intersects(inner) for M in links):
                    continue
                if any(inner.intersection(M.buffer(3.0)).length > 3.0 for M in near):
                    continue
                lcls = "village_lane" if VILL.contains(link.centroid) else "local"
                if houses_hit(link.buffer(red_w(lcls) / 2.0)) or link.crosses(barrier) or link.intersects(WATER_POLY) \
                        or link.intersects(RAIL) or not GREEN.contains(link):
                    continue
                made += 1
                links.append(link)
                street(f"v_link_{made:02d}", lcls, link.coords, "сквозной проезд из тупика", 2026, layer="link",
                       why=MODEL + f": тупик существующей улицы {sid} длиннее нормы — сквозной проезд {d:.0f} м к {host} "
                                   "(между домами, не через дом)")
                if log is not None:
                    log.append({"what": "тупик существующей улицы: сквозной проезд", "id": f"v_link_{made:02d}", "from": sid,
                                "to": host, "m": round(d), "at": [round(E.x), round(E.y)]})
                done = True
                break
            if not done:
                kept += 1
                if log is not None:
                    log.append({"what": "тупик существующей улицы: проезда без сноса дома нет — как в OSM", "id": sid,
                                "at": [round(E.x), round(E.y)]})
    return made, kept


SNAP_J = 6.0       # m: cut points and piece ends closer than this are one junction (no slivers of street between them)
GRADE_SEP_TYPES = {"grade_separation", "diamond", "partial_cloverleaf", "cloverleaf", "trumpet", "directional"}


def phase_years(fixed_poly, use="road", log=None):
    """Opening years by pieces of street between junctions, so that no street ends blind in any year:
      push — a piece of a new street opens no earlier than some street at each of its ends (a blind tail waits for the
             street it runs to: it becomes its own spec street with the later years);
      pull — a fixed piece (inside fixed_poly) whose end has no street open by its year gets the shortest chain of new
             pieces to a street open by then, opening with it.
    A street is split only at its junctions. Existing roads are 2025 and end blind as OSM has them."""
    specs = [s for s in STREETS]
    lines = [(s["id"], LineString(s["line"]), s["class"], s) for s in specs]
    lines += [("osm:" + oid, q, cls, None) for oid, q, cls in OSM_HOST]
    tree = shapely.STRtree([L for _, L, _, _ in lines])
    gsep = [Point(n["x"], n["z"]) for n in NODES.values() if n["type"] in GRADE_SEP_TYPES]
    spans = {}
    for sid, L, cls, s in lines:
        sp = []
        for st in (s or {}).get("struct") or []:
            if st["kind"] in ("overpass", "bridge", "tunnel"):
                sp.append(LineString([st["from"], st["to"]]).buffer(2.0))
        spans[sid] = sp

    def in_span(sid, P):
        return any(g.contains(P) for g in spans[sid])

    cuts = {sid: {0.0, L.length} for sid, L, _, _ in lines}
    for i, (sid, L, cls, s) in enumerate(lines):
        if cls == "expressway":
            continue
        for j in tree.query(L.buffer(0.6)):
            if j == i:
                continue
            sid2, M, cls2, _ = lines[j]
            if cls2 == "expressway":
                continue
            for e in (M.coords[0], M.coords[-1]):
                P = Point(e)
                if L.distance(P) < 0.6:
                    cuts[sid].add(L.project(P))
            if cls in NO_JUNCTION or cls2 in NO_JUNCTION:
                continue
            x = L.intersection(M)
            for q in getattr(x, "geoms", [x]):
                if q.is_empty or q.geom_type != "Point":
                    continue
                if in_span(sid, q) or in_span(sid2, q) or any(q.distance(g) < 25.0 for g in gsep):
                    continue
                cuts[sid].add(L.project(q))
    pieces = []
    for sid, L, cls, s in lines:
        ch = sorted(cuts[sid])
        m = [ch[0]]
        for c in ch[1:]:
            if c - m[-1] > SNAP_J:
                m.append(c)
        if L.length - m[-1] > 0.01:
            m[-1] = L.length
        for a, b in zip(m[:-1], m[1:]):
            pieces.append([sid, a, b])
    LID = {sid: (L, cls, s) for sid, L, cls, s in lines}
    pts = []
    for k, (sid, a, b) in enumerate(pieces):
        L = LID[sid][0]
        pts.append(L.interpolate(a)); pts.append(L.interpolate(b))
    ptree = shapely.STRtree(pts)
    parent = list(range(len(pts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, P in enumerate(pts):
        for j in ptree.query(P.buffer(SNAP_J)):
            if j != i and P.distance(pts[j]) < SNAP_J:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    node_of = [find(i) for i in range(len(pts))]
    at = {}
    for i, n in enumerate(node_of):
        at.setdefault(n, []).append(i // 2)
    joints = [Point(n["x"], n["z"]) for n in NODES.values() if n["type"] == "joint"]
    edge = {n for n in at if GREEN.exterior.distance(pts[n]) < 3.0 or any(pts[n].distance(j) < 3.0 for j in joints)}
    grp, year, fixed, existing = [], {}, set(), set()
    for k, (sid, a, b) in enumerate(pieces):
        L, cls, s = LID[sid]
        g = sid if s is None else (sid, k)
        grp.append(g)
        y0 = 2025 if s is None else int(s["years"][0])
        year[g] = y0
        mid = L.interpolate((a + b) / 2)
        if s is None or s.get("_layer") == "osm":
            fixed.add(g)
            existing.add(g)
        elif fixed_poly is not None and not fixed_poly.is_empty and fixed_poly.buffer(1.0).contains(mid):
            fixed.add(g)
    plen = [b - a for _, a, b in pieces]

    def others(k, n):
        return [q for q in at[n] if q != k]
    pulled = []
    for _round in range(60):
        changed = False
        for _ in range(200):
            moved = False
            for k in range(len(pieces)):
                g = grp[k]
                if g in fixed:
                    continue
                for n in (node_of[2 * k], node_of[2 * k + 1]):
                    if n in edge:
                        continue
                    o = [year[grp[q]] for q in others(k, n) if grp[q] != g]
                    if not o:
                        continue
                    need = min(o)
                    if need > year[g]:
                        year[g] = need
                        moved = changed = True
            if not moved:
                break
        for k in range(len(pieces)):
            g = grp[k]
            if g not in fixed or g in existing:
                continue
            y = year[g]
            for n in (node_of[2 * k], node_of[2 * k + 1]):
                if n in edge:
                    continue
                o = [q for q in others(k, n) if grp[q] != g]
                if not o or min(year[grp[q]] for q in o) <= y:
                    continue
                dist, prev, pq, goal = {n: 0.0}, {}, [(0.0, n)], None
                while pq:
                    d, u = heapq.heappop(pq)
                    if d > dist.get(u, 1e18):
                        continue
                    if u != n and (u in edge or any(year[grp[q]] <= y for q in at[u])):
                        goal = u
                        break
                    for q in at[u]:
                        gq = grp[q]
                        if q == k or gq in fixed or year[gq] <= y:
                            continue
                        v = node_of[2 * q + 1] if node_of[2 * q] == u else node_of[2 * q]
                        c = d + plen[q]
                        if c < dist.get(v, 1e18):
                            dist[v] = c
                            prev[v] = (u, q)
                            heapq.heappush(pq, (c, v))
                if goal is None:
                    continue
                v = goal
                while v != n:
                    u, q = prev[v]
                    gq = grp[q]
                    if gq not in fixed:
                        pulled.append((pieces[q][0], year[gq], y))
                        year[gq] = y
                        fixed.add(gq)
                    v = u
                changed = True
        if not changed:
            break
    by_sid = {}
    for k, (sid, a, b) in enumerate(pieces):
        if LID[sid][2] is not None:
            by_sid.setdefault(sid, []).append((a, b, year[grp[k]]))
    moves, new_streets = [], []
    for s in list(STREETS):
        runs = []
        for a, b, y in sorted(by_sid.get(s["id"], [])):
            if runs and runs[-1][2] == y:
                runs[-1][1] = b
            else:
                runs.append([a, b, y])
        if not runs:
            continue
        y_old = int(s["years"][0])
        if len(runs) == 1:
            if runs[0][2] != y_old:
                s["years"] = Y4(runs[0][2], use)
                moves.append((s["id"], y_old, runs[0][2]))
            continue
        L = LineString(s["line"])
        keep_i = 0
        made = [s]
        struct0 = list(s.get("struct") or [])
        for i, (a, b, y) in enumerate(runs):
            q = substring(L, a, b)
            st = [x for x in struct0 if q.distance(Point(x["from"])) < 1.0 and q.distance(Point(x["to"])) < 1.0]
            if i == keep_i:
                s2 = s
            else:
                s2 = copy.deepcopy(s)
                k = 1
                while f"{s['id']}_y{k}" in SID:
                    k += 1
                s2["id"] = f"{s['id']}_y{k}"
                s2["why"] = (s.get("why") or "") + f"; участок открывается в {y} (годы по участкам: без тупиков в каждом году)"
                new_streets.append(s2)
                made.append(s2)
                SID[s2["id"]] = s2
            s2["line"] = [[round(x, 1), round(z, 1)] for x, z in q.coords]
            s2["struct"] = st
            s2["years"] = Y4(y, use) if (i != keep_i or y != y_old) else s["years"]
            if s2 is not s or y != y_old:
                moves.append((s2["id"], y_old, y))
        for n in NODES.values():
            if s["id"] in n.get("streets", []):
                P = Point(n["x"], n["z"])
                dd = {x["id"]: LineString(x["line"]).distance(P) for x in made}
                ids = [k for k, v in dd.items() if v < max(1.0, min(dd.values()) + 1.0)]
                rest = [x for x in n["streets"] if x != s["id"]]
                n["streets"] = rest + [x for x in ids if x not in rest]
    STREETS.extend(new_streets)
    if log is not None:
        log.append({"what": "годы по участкам улиц: без тупиков в каждом году", "moved": len(moves), "split": len(new_streets),
                    "pulled": sorted({(p[0], p[2]) for p in pulled})})
    return moves


def summary():
    from collections import Counter
    c = Counter((s["_layer"], s["class"]) for s in STREETS)
    for k, v in sorted(c.items()):
        km = sum(LineString(s["line"]).length for s in STREETS if (s["_layer"], s["class"]) == k) / 1000
        print(f"  {k[0]:6s} {k[1]:20s} {v:5d} {km:7.1f} km")


if __name__ == "__main__":
    summary()
