#!/usr/bin/env python3
"""Growing-West · level 2 · street network of the whole district (w52), imported by growing_w_build.py.

    python3 -I tools/map/district/growing_w_net.py            # build the frame in memory and print a summary

Layers (the gen_network grid is off for v1 specs, every street is drawn here):
  1. existing roads (Overture/OSM): А-3 carriageways and ramps, the tertiary roads (the old Каскелен road on the left bank,
     Енбек – Каскелен road to the А-3 km 46 interchange, the southern road to the А-3 km 37 interchange) stay as they are;
     the village streets stay; other existing roads inside new quarters are replaced (replaced_osm);
  2. the frame of new streets by the level-0 scheme axes (airport_trunk, art_south, art_link, art_plateau, blv_kaskelen,
     blv_centre, dst_westbank, dst_north) and the cartographer's additions (Енбек – Каскелен to the centre, the streets to
     the A-3 joints J147 / J148 and J146 of Growing-East, the south entry of the airport from Golden's X-IA at J143,
     the street over the railway to the southern industry);
  3. local streets of every new quarter (edge streets on unfronted sides, a grid at the zone's block size aligned with the
     frame, every end on a street), then free ends trimmed, ends snapped, lanes to houses, links from dead ends and opening
     years by pieces so that nothing ends blind in any year.
Every coordinate not from a source is the cartographer's design (label «модель qTwin»). Unity frame: X east, Z north.
"""
import copy
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.ops import nearest_points, substring, unary_union  # noqa: E402

import growing_w_common as C  # noqa: E402
import growing_w_zones as Z  # noqa: E402
import land_util as LU  # noqa: E402

MODEL = C.MODEL
Y4 = C.Y4
fillet = C.fillet
POLY = C.POLY
CITY = C.CITY
JOINT = {j["id"]: j for j in CITY["joints"]["items"] if "growing_w" in (j.get("between") or [])}

_LN = LU.Norms()
_RW = {}


def red_w(cls, profile=None):
    if cls not in _RW:
        _RW[cls] = float(LU.profile_from_norms(_LN, cls)["red_line_w"])
    w = _RW[cls]
    g = float((profile or {}).get("green_w") or 0.0)
    return max(w, g + 6.0) if g else w


def cw_off(cls, profile=None):
    """Offset of one carriageway from the axis of a divided street (gen/land_util.cw_offset: median/2 + lanes·lane_w/2),
    0 for an undivided one."""
    p = dict(LU.profile_from_norms(_LN, cls))
    p.update({k: v for k, v in (profile or {}).items() if k in ("median_w", "lanes", "lane_w")})
    if float(p.get("median_w") or 0.0) <= 0.0:
        return 0.0
    return float(p["median_w"]) / 2.0 + float(p["lanes"][0]) * float(p["lane_w"]) / 2.0


def cw_ends(line, cls, profile=None, end=-1):
    """The two carriageway ends of a divided street at its first (end=0) or last (end=-1) point."""
    e = cw_off(cls, profile)
    P = np.array(line[end], float)
    Q = np.array(line[1] if end == 0 else line[-2], float)
    t = (P - Q) / np.linalg.norm(P - Q)
    n = np.array([-t[1], t[0]])
    return [tuple(P + n * e), tuple(P - n * e)]


# roundabouts where a divided arterial ends (both carriageways meet the ring): two-lane ring, roundabouts.icd_m.double and
# circulating_width_m.two_lanes (middle of the bands), as gen/net_rings.ring_size builds it
_ICD = _LN.v("roundabouts.icd_m")["double"]
_RCW = _LN.v("roundabouts.circulating_width_m")["two_lanes"]
RING_R = 0.5 * (_ICD["min"] + _ICD["max"]) / 2.0 - 0.5 * (_RCW["min"] + _RCW["max"]) / 2.0
RING_OUT = RING_R + 0.5 * (_RCW["min"] + _RCW["max"]) / 2.0
RINGS = []                                          # (node id, (x, z))


# ===================================================================================================== open data
OSM = {p["id"]: (g, p) for g, p in C.layer_in("roads", POLY)}
SH = {k[:8]: k for k in OSM}


def osm(short):
    return OSM[SH[short]]


VILL = Z.VILL
WATER_POLY, WATER_LINE, _W = C.water()
STRIP = 35.0                                       # flood.water_protection_strip_min_m
WATER_STRIP = unary_union([WATER_POLY.buffer(STRIP), WATER_LINE.buffer(STRIP)])
HOUSES = [h["fp"] for h in C.houses()]
houses_hit = C.houses_hit

# power lines (kV from the OSM voltage tag; protection zone utilities.power_line_protection_zone_m by voltage)
_INF = [(g, p) for g, p in C.layer_in("infrastructure", POLY.buffer(100)) if p.get("class") == "power_line"]
_KV = C.osm_voltage({p["id"][:8] for _, p in _INF})
PZONE = {220.0: 25.0, 500.0: 30.0}
POWER = []                                         # [(id8, LineString clipped to the district + 100 m, kv, zone m, osm id)]
for g, p in _INF:
    k = p["id"][:8]
    kv = _KV.get(k, (None,))[0]
    clip = g.intersection(POLY.buffer(100))
    for q in getattr(clip, "geoms", [clip]):
        if q.geom_type == "LineString" and q.length > 5:
            POWER.append((k, q, kv, PZONE.get(kv, 25.0), p["id"]))
POWER_ZONE = unary_union([q.buffer(w) for _, q, _, w, _ in POWER])

# railway (Жетыген – Казыбек би bypass, OSM) and the airport spur (model): no tool models rails — kept free of streets here
RAIL = [g for g, p in C.layer_in("rail", POLY.buffer(100)) if p["id"].startswith("81f6836e")][0]
RAIL_ALL = [g for g, p in C.layer_in("rail", POLY.buffer(100))]          # every OSM track near the district
SPUR_FORK = RAIL.interpolate(RAIL.project(Point(-5800.0, -450.0)))
SPUR = fillet([(SPUR_FORK.x, SPUR_FORK.y), (-6900.0, 120.0), (-8200.0, 900.0), (-9600.0, 1750.0), (-10900.0, 2400.0),
               (-12000.0, 2520.0), (-13300.0, 2470.0), (-14400.0, 2540.0), (-15300.0, 2560.0)], 1200)
RAIL_HALF = 25.0                                   # m: rail corridor half width kept free of streets along it (model)
RAIL_BAR = unary_union([RAIL.buffer(RAIL_HALF), LineString(SPUR).buffer(RAIL_HALF)])

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


def water_bridges(line, pad=12.0):
    """Struct spans (bridge) where a new line crosses water (streams and water polygons), each padded on both sides."""
    L = LineString(line)
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
    return _spans(L, spans, "bridge")


def rail_overpasses(line, pad=30.0, tracks=None):
    """Struct spans (overpass) where a new line crosses a railway track (OSM; gen_network lifts the deck over the track by
    bridges.rail_clearance_m)."""
    L = LineString(line)
    spans = []
    for g in (tracks if tracks is not None else RAIL_ALL):
        x = L.intersection(g)
        for q in getattr(x, "geoms", [x]):
            if not q.is_empty and q.geom_type == "Point":
                s = L.project(q)
                spans.append((s - pad, s + pad))
    return _spans(L, spans, "overpass")


def _spans(L, spans, kind):
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 5:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        a, b = max(a, 0.5), min(b, L.length - 0.5)
        if b - a > 2:
            pa, pb = L.interpolate(a), L.interpolate(b)
            out.append(((pa.x, pa.y), (pb.x, pb.y), kind))
    return out


RAIL_CROSSINGS = []              # (x, z) where a new street crosses the airport spur (model qTwin, not in the rail data)


def structs(line):
    """Spec spans of a new line: bridges over water, overpasses over the railway (OSM 81f6836e: gen_network lifts the deck
    over the track, rules 6 and 9). The airport spur is a model line that no tool knows: its crossings are listed in
    RAIL_CROSSINGS (an overpass over nothing would «lie on the ground», rule 9)."""
    for a_, b_, _ in rail_overpasses(line, tracks=[LineString(SPUR)]):
        RAIL_CROSSINGS.append((round((a_[0] + b_[0]) / 2.0), round((a_[1] + b_[1]) / 2.0)))
    return water_bridges(line) + rail_overpasses(line)


# ===================================================================================================== 1. existing roads
KEEP_IDS = {}
A3_IDS = set()


def osm_class(p, g):
    c, sub = p.get("class"), p.get("sub")
    if c == "motorway":
        return "ramp" if sub == "link" else "expressway"
    if c in ("tertiary", "secondary", "primary"):
        return "village_main" if g.intersection(VILL).length > 0.5 * g.length else "district_transport"
    return None


def keep_name(p):
    n = p.get("name") or ""
    if p.get("class") == "motorway" and p.get("sub") != "link":
        return "А-3 Алматы – Қонаев"
    if p.get("sub") == "link":
        return "съезд развязки А-3"
    return n


def osm_parts(oid):
    g = OSM[oid][0].intersection(POLY)
    return [g] if g.geom_type == "LineString" else [q for q in getattr(g, "geoms", []) if q.geom_type == "LineString"]


TERTIARY_NAME = {"3ce40062": "старая дорога Каскелен – Жанаарна (левый берег)", "7422a574": "старая дорога Каскелен – Жанаарна",
                 "ff356758": "старая дорога Каскелен – Жанаарна", "ea724976": "дорога к мосту через Каскелен",
                 "87546a75": "дорога Енбек – Каскелен", "8a83d4dd": "дорога Енбек – Каскелен",
                 "7cd5eaf2": "дорога Енбек – Каскелен (к развязке км 46)", "d492aa6d": "южная дорога к развязке А-3 км 37"}
for oid, (g, p) in sorted(OSM.items()):
    cls = osm_class(p, g)
    if cls is None:
        continue
    parts = [q for q in osm_parts(oid) if q.length >= 3.0]
    if not parts:
        continue
    sid = ("k_" if cls in ("expressway", "ramp") else "t_") + oid[:8]
    nm = TERTIARY_NAME.get(oid[:8]) or keep_name(p)
    ax = "a3" if cls == "expressway" else ("a3_ramps_s" if cls == "ramp" and Point(g.coords[0]).y < -2500 else None)
    street(sid, cls, max(parts, key=lambda q: q.length).coords, nm or ("улица села" if cls == "village_main" else ""), 2025,
           oneway=cls in ("expressway", "ramp"), source="keep_existing:" + oid, axis=ax, years=C.EXISTING, layer="osm",
           why="существующая дорога OSM/Overture, как есть (направление линии = направление движения)" if cls in ("expressway", "ramp")
           else "существующая дорога OSM, как есть")
    KEEP_IDS[oid] = sid
    if cls in ("expressway", "ramp"):
        A3_IDS.add(oid)


def k_of(short):
    return KEEP_IDS.get(SH.get(short))


# ===================================================================================================== 2. frame of new streets
TRUNK_PROFILE = {"median_w": 9.0, "lanes": [2, 2],
                 "note_ru": "в разделительной полосе 9 м — пути ЛРТ (линия аэропорта, стыки на перекрёстках в одном уровне)"}


def cut_at(line, pts_):
    """Split a polyline at the points nearest to pts_ (in order) → list of polylines."""
    L = LineString(line)
    ch = [0.0] + sorted(L.project(Point(p)) for p in pts_) + [L.length]
    return [list(substring(L, a, b).coords) for a, b in zip(ch[:-1], ch[1:]) if b - a > 1.0]


# --- the airport lot (runway 4 000 m at 095°, city.json airport_new): 2 300 m each way along the runway, 450 m south and
# 1 000 m north of its axis (strip, taxiways, apron, terminal), within the district
J143 = (JOINT["J143"]["x"], JOINT["J143"]["z"])
AIR_C = np.mean(np.array(CITY["airport_new"]["line"], float), axis=0)
_U = np.array([math.sin(math.radians(95.0)), math.cos(math.radians(95.0))])
_V = np.array([math.sin(math.radians(5.0)), math.cos(math.radians(5.0))])     # across the runway, to the north
AIR_SOUTH_M, AIR_NORTH_M, AIR_HALF_L = 450.0, 1000.0, 2300.0


def air_pt(a, c):
    p = AIR_C + _U * a + _V * c
    return (float(p[0]), float(p[1]))


AIRPORT_LOT = Polygon([air_pt(-AIR_HALF_L, -AIR_SOUTH_M), air_pt(AIR_HALF_L, -AIR_SOUTH_M), air_pt(AIR_HALF_L, AIR_NORTH_M),
                       air_pt(-AIR_HALF_L, AIR_NORTH_M)]).intersection(POLY)
# the zimovkas stay (owner 31.10, scheme q2): the lot leaves out their village land and every house with 30 m round it
_zim = unary_union([VILL.buffer(5.0)] + [h.buffer(30.0) for h in houses_hit(AIRPORT_LOT)])
AIRPORT_LOT = AIRPORT_LOT.difference(_zim).buffer(0)
AIRPORT_LOT = max(getattr(AIRPORT_LOT, "geoms", [AIRPORT_LOT]), key=lambda g: g.area).simplify(1.0)

# --- Аэропортовая магистраль (scheme airport_trunk): from the А-3 joint J148 (km 44, the overpass and ramps are drawn
# with Growing-East at level 3) through the centre «Каскелен» to the airport terminal. LRT in its median west of x −1000.
J148 = (JOINT["J148"]["x"], JOINT["J148"]["z"])
TRUNK = fillet([J148, (-700.0, 1925.0), (-1500.0, 2150.0), (-2700.0, 2560.0), (-3350.0, 2800.0), (-4050.0, 3150.0),
                (-4600.0, 3165.0), (-5000.0, 3165.0), (-5600.0, 3150.0), (-6500.0, 2950.0), (-7700.0, 2800.0),
                (-9000.0, 2750.0), (-10400.0, 2900.0), (-11700.0, 2950.0), (-12400.0, 2800.0), (-13300.0, 2720.0),
                (-14400.0, 2760.0), (-15300.0, 2750.0), (-15850.0, 2650.0), (-15960.0, 2300.0)], 900)
_t = LineString(TRUNK)
TRUNK = list(substring(_t, 0.0, min(_t.project(q) for q in getattr(_t.intersection(AIRPORT_LOT.exterior), "geoms",
                                                                         [_t.intersection(AIRPORT_LOT.exterior)]))).coords)
TL = LineString(TRUNK)
AIR_GATE_N = TRUNK[-1]
_tc = [TL.interpolate(TL.project(Point(p))) for p in [(-3350.0, 2800.0), (-5000.0, 3165.0), (-9000.0, 2750.0)]]
_tparts = cut_at(TRUNK, [(q.x, q.y) for q in _tc])
_ty = [(2030, "от стыка J148 (км 44 А-3) до центра «Каскелен»"), (2032, "центр «Каскелен» и мост через Каскелен"),
       (2036, "левый берег и подъём на плато"), (2041, "плато: промзона и грузовой терминал до аэропорта")]
for i, (part, (yb, what)) in enumerate(zip(_tparts, _ty)):
    st = structs(part)
    if i == 0:
        # over the А-3 south-bound carriageway right after the joint (the interchange is level 3 with Growing-East)
        L0 = LineString(part)
        st = [(part[0], tuple(L0.interpolate(110.0).coords[0]), "overpass")] + st
    street(f"s_trunk_{i + 1}", "arterial_regulated", part, "Аэропортовая магистраль", yb, axis="airport_trunk",
           profile=dict(TRUNK_PROFILE), struct=st,
           why=f"схема airport_trunk: {what} ({yb}); класс arterial_regulated (перекрёстки в одном уровне со светофорами), "
               "ЛРТ в разделительной полосе")
for _k, _p in enumerate(cw_ends(_tparts[-1], "arterial_regulated", TRUNK_PROFILE), 1):
    # one node per carriageway end: gen_network gives a spec joint to the one network node within 3 m
    node(f"n_air_gate_n{_k}", _p[0], _p[1], "joint", ["s_trunk_4"], landmark="airport_alatau",
         why_ru="магистраль приходит к терминалу аэропорта: дальше привокзальная площадь и внутренние проезды модели "
                "airport (Unity), сеть района их не рисует; узел на каждой проезжей части")
SCHEME_CHANGES.append(("airport_trunk", "класс trunk → arterial_regulated: перекрёстки в одном уровне, ЛРТ аэропорта — в "
                                        "разделительной полосе 9 м (а не отдельной полосой в 140 м севернее); западный конец — "
                                        "у терминала на северной границе территории аэропорта, отрезок у грузового терминала на 80–150 м севернее схемы, "
                                        "чтобы ж/д ветка к вокзалу шла южнее магистрали без пересечения"))

# --- Южная промышленная улица (scheme art_south): from the А-3 underpass at Жанаарна (OSM bdc5c57b, west end) to the
# Rhenus hub; the joint J077 of Growing-East's ax_south is the other end of that underpass
UNDER_W = (-591.5, 222.1)                          # west end of the OSM tunnel bdc5c57b (exact vertex)
# a divided street cannot end on the one-lane tunnel road: it ends at a two-lane ring 60 m south-west of the portal, and
# a two-lane district street runs from the ring to the tunnel (the OSM track 54bdd9fc to the house by the portal starts
# there too, to the north-west)
RING_TUN = (-645.0, 195.0)
RING_HUB = (-6900.0, 620.0)
SOUTH = fillet([RING_TUN, (-1800.0, 330.0), (-3300.0, 380.0), (-5000.0, 420.0), (-5600.0, 600.0), (-6200.0, 660.0),
                RING_HUB], 600)
street("s_south", "arterial_regulated", SOUTH, "Южная промышленная улица", 2028, axis="art_south", struct=structs(SOUTH),
       why="схема art_south (2027–30): от кольца у западного выхода тоннеля под А-3 у Жанаарны (OSM bdc5c57b; на другой "
           "стороне — ax_south Growing-восток, стык J077) вдоль сухого порта к кольцу у хаба Rhenus; мосты через Каскелен")
street("s_south_tun", "district_transport", [RING_TUN, UNDER_W], "Южная промышленная улица (въезд в тоннель под А-3)", 2028,
       axis="art_south",
       why=MODEL + ": от кольца до западного выхода существующего тоннеля под А-3 (OSM bdc5c57b, одна полоса в каждую "
                   "сторону): улица с разделительной полосой не может кончаться на однополосной дороге, переход — кольцом")
node("n_ring_tunnel", RING_TUN[0], RING_TUN[1], "roundabout", ["s_south", "s_south_tun"],
     why_ru=MODEL + ": двухполосное кольцо у тоннеля под А-3 — конец Южной промышленной улицы с разделительной полосой")
RINGS.append(("n_ring_tunnel", RING_TUN))
SCHEME_CHANGES.append(("art_south", "восточный конец — кольцо в 60 м от западного выхода существующего тоннеля под А-3 у "
                                    "Жанаарны (−592, 222) и короткая улица district_transport до тоннеля, а не точка на проезжей "
                                    "части А-3 (−570, 165); у Каскелена — севернее пруда (−5900, 300): мост через протоку 25–40 м "
                                    "вместо 400 м вдоль берега пруда; западный конец — кольцо у хаба Rhenus, где начинается "
                                    "Связь Южная – Аэропортовая"))

# --- Связь Южная – Аэропортовая (scheme art_link)
LINK = fillet([RING_HUB, (-6600.0, 1600.0), (-6450.0, 2300.0), C.on_line(TRUNK, x=-6500.0)], 500)
street("s_link", "arterial_regulated", LINK, "Связь Южная – Аэропортовая", 2036, axis="art_link", struct=structs(LINK),
       why="схема art_link (2034–38): от кольца Южной промышленной улицы у хаба Rhenus по уступу к Аэропортовой магистрали")
node("n_ring_hub", RING_HUB[0], RING_HUB[1], "roundabout", ["s_south", "s_link"],
     why_ru=MODEL + ": двухполосное кольцо у хаба Rhenus: Южная промышленная улица (2028) кончается на нём до 2036, потом "
                    "от него идёт Связь Южная – Аэропортовая")
RINGS.append(("n_ring_hub", RING_HUB))

# --- Дорога плато (scheme art_plateau): from the trunk north over the plateau to the А-3 km 55,9 trumpet (W terminal of the
# OSM links dfc7b64c / 3e1f1193 / 87899a36)
KM559 = (250.2, 13683.2)                           # the terminal node of the OSM ramps dfc7b64c / 3e1f1193 / 87899a36
_pl = LineString(fillet([C.on_line(TRUNK, x=-9000.0), (-8900.0, 5200.0), (-8300.0, 7700.0), (-7600.0, 10200.0),
                         (-7100.0, 12600.0), (-6200.0, 13700.0), (-3500.0, 13800.0), (-1200.0, 13780.0), (-300.0, 13720.0),
                         KM559], 900))
# the trumpet's stem: the divided street ends at a two-lane ring 90 m west of the ramps' terminal node; one carriageway
# (district_transport, as the one-lane ramps) runs from the ring to the terminal
RING_KM559 = tuple(_pl.interpolate(_pl.length - 90.0).coords[0])
PLAT = list(substring(_pl, 0.0, _pl.length - 90.0).coords)
street("s_plateau", "arterial_regulated", PLAT, "Дорога плато (север – юг)", 2046, axis="art_plateau", struct=structs(PLAT),
       why="схема art_plateau (2040–50): от Аэропортовой магистрали у технопарка на север по плато и на восток к кольцу у "
           "развязки А-3 км 55,9")
street("s_plateau_stem", "district_transport", [RING_KM559, KM559], "Дорога плато (въезд на развязку км 55,9)", 2046,
       axis="art_plateau",
       why=MODEL + ": от кольца до концевого узла существующих съездов развязки А-3 км 55,9 (OSM, однополосные): улица с "
                   "разделительной полосой не может кончаться на узле однополосных съездов, переход — кольцом")
node("n_ring_km559", RING_KM559[0], RING_KM559[1], "roundabout", ["s_plateau", "s_plateau_stem"],
     why_ru=MODEL + ": двухполосное кольцо в начале ствола развязки км 55,9 — конец Дороги плато с разделительной полосой")
RINGS.append(("n_ring_km559", RING_KM559))
SCHEME_CHANGES.append(("art_plateau", "восточный конец — кольцо в 90 м от концевого узла существующей развязки км 55,9 "
                                      "(250, 13683), где сходятся съезды OSM, и ствол district_transport до него, а не точка на "
                                      "А-3 (350, 13760)"))

# --- Улица Енбек – Каскелен: the existing tertiary 87546a75 from the А-3 km 46 interchange is kept; a new street from it to
# the trunk at the centre's east edge, east of the 500 kV corridor (scheme art_k46 ran over the existing road and across
# the corridor)
K46_A = C.on_line(osm("87546a75")[0], x=-2600.0)
K46 = fillet([K46_A, (-2850.0, 3400.0), (-3150.0, 3020.0), C.on_line(TRUNK, x=-3350.0)], 400)
street("s_k46", "district_transport", K46, "улица Енбек – Каскелен", 2032, axis="art_k46", struct=structs(K46),
       why="схема art_k46: восточная часть — существующая дорога 87546a75 (развязка км 46 А-3 полная, OSM), новая часть — "
           "от неё к магистрали у центра, восточнее коридора ВЛ 500 кВ")
SCHEME_CHANGES.append(("art_k46", "восточная часть — существующая дорога Енбек – Каскелен (OSM 87546a75) с её развязкой км 46; "
                                  "новая улица только от неё (−2600, 3794) к магистрали (−3350, 2800), восточнее коридора ВЛ 500 кВ "
                                  "4fab2f0d; класс district_transport, как у существующей дороги"))

# --- Набережная Каскелена (scheme blv_kaskelen), boulevard on the right bank. It ends on the Северная (dst_north) where
# the two meet (z ≈ 6250): the scheme's last 1,2 km ran 25–60 m beside the Северная, east of it and away from the river,
# cutting a strip of land off between the two and touching the river at the Северная's bridge
DN_A = C.on_line(osm("87546a75")[0], x=-2200.0)
DN = fillet([DN_A, (-1700.0, 4800.0), (-1100.0, 5700.0), (-1050.0, 6500.0), (-600.0, 7400.0)], 500)
_dn = LineString(DN)
_s_blv = _dn.project(Point(-1060.0, 6250.0))
_pb = np.array(_dn.interpolate(_s_blv).coords[0])
_tb = np.array(_dn.interpolate(_s_blv + 5.0).coords[0]) - np.array(_dn.interpolate(_s_blv - 5.0).coords[0])
_tb = _tb / np.linalg.norm(_tb)
_nb = np.array([-_tb[1], _tb[0]])
_nb = _nb if _nb[0] < 0 else -_nb                       # the normal towards the west (the boulevard comes from the south-west)
BLV_END = (float(_pb[0]), float(_pb[1]))
BLV = fillet([C.on_line(TRUNK, x=-4050.0), (-3647.0, 3433.0), (-2907.0, 4274.0), (-2629.0, 4398.0), (-1942.0, 5148.0),
              (-1574.0, 5851.0), tuple(_pb + _nb * 110.0), BLV_END], 300)
street("s_blv_kaskelen", "boulevard", BLV, "бульвар Набережная Каскелена", 2034, axis="blv_kaskelen", struct=structs(BLV),
       why="схема blv_kaskelen (2030–45): бульвар правого берега от центра на северо-восток вдоль поймы до улицы Северная")
SCHEME_CHANGES.append(("blv_kaskelen", "конец — на улице Северная у (−1060, 6250), примыкание под прямым углом: последние 1,2 км схемы "
                                       "шли в 25–60 м рядом с Северной, по её восточной стороне (не у реки), отрезали полосу земли "
                                       "и касались реки у моста Северной"))
# --- Пешеходная улица центра (scheme blv_centre)
PED = fillet([(-4600.0, 3400.0), (-4150.0, 3350.0), (-3350.0, 3150.0), (-2900.0, 2900.0)], 200)
street("s_ped_centre", "pedestrian_street", PED, "пешеходная улица центра «Каскелен»", 2033, axis="blv_centre",
       struct=structs(PED), why="схема blv_centre (2031–36): пешеходная улица через оба берега, мост через Каскелен")
SCHEME_CHANGES.append(("blv_centre", "западный конец — (−4600, 3400) в центре левого берега, мост через Каскелен там, где пойма уже: отрезок схемы к (−4700, 3600) шёл "
                                     "через село (дома в 5 м от оси)"))
# --- Улица левого берега (scheme dst_westbank)
# it starts 100 m west of the Связь Южная – Аэропортовая (x −6500): two streets on one point of the divided trunk make a
# 5-arm node, which gen_network turns into a ring (with the LRT in the median)
WB = fillet([C.on_line(TRUNK, x=-6600.0), (-6150.0, 3900.0), (-5650.0, 4400.0)], 500)
street("s_westbank", "district_transport", WB, "улица левого берега", 2036, axis="dst_westbank", struct=structs(WB),
       why="схема dst_westbank (2034–40): от магистрали по западному краю левобережных кварталов на север; северный отрезок "
           "схемы через резерв (−4700, 5600) не строится до решения по резерву")
SCHEME_CHANGES.append(("dst_westbank", "северный конец — на улице северного края кварталов левого берега (z ≈ 4300): отрезок схемы "
                                       "через резерв res_reserve_valley_9 к (−4700, 5600) без застройки не нужен"))
# --- Улица Северная (scheme dst_north)
street("s_north", "district_transport", DN, "улица Северная", 2035, axis="dst_north", struct=structs(DN),
       why="схема dst_north (2034–42): от дороги Енбек – Каскелен на север через северные кварталы к северному центру; "
           "2035 — с кварталами res_north, улицы которых на неё выходят")
# --- streets to the А-3 joints of Growing-East (km 48 J147, km 50,5 J146): over the south-bound carriageway, the ramps are
# level 3 with Growing-East
J147 = (JOINT["J147"]["x"], JOINT["J147"]["z"])
J146 = (JOINT["J146"]["x"], JOINT["J146"]["z"])
N48 = fillet([C.on_line(DN, z=5900.0), (-600.0, 5980.0), J147], 300)
street("s_n48", "district_transport", N48, "улица к развязке А-3 км 48", 2040, struct=structs(N48),
       why=MODEL + ": от улицы Северная через деловую зону у А-3 к стыку J147 (ax_n48 Growing-восток, км ≈ 48): путепровод "
                   "над А-3 и съезды — уровень 3 вместе с Growing-восток (замечание w42); проезжие части А-3 здесь — в "
                   "Growing-восток, в районе путепровода нет")
N50 = fillet([DN[-1], (-200.0, 7800.0), J146], 300)
street("s_n50", "district_transport", N50, "улица к развязке А-3 км 50,5", 2046, struct=structs(N50),
       why=MODEL + ": продолжение улицы Северная к стыку J146 (ax_n50 Growing-восток, км ≈ 50,5): путепровод над А-3 и "
                   "съезды — уровень 3 вместе с Growing-восток (замечание w42)")
# --- south entry of the airport: Golden's X-IA (joint J143) on to the airport's south gate (service and cargo yard)
_gate = LineString([J143, (J143[0], J143[1] + 3000.0)]).intersection(AIRPORT_LOT.exterior)
AIR_GATE_S = (J143[0], min(q.y for q in getattr(_gate, "geoms", [_gate])))
XIA = [J143, AIR_GATE_S]
street("s_air_south", "arterial_regulated", XIA, "южный въезд аэропорта «Алатау»", 2050, struct=structs(XIA),
       why=MODEL + ": продолжение X-IA Golden от стыка J143 до южных ворот аэропорта (служебная и грузовая зона у ВПП); "
                   "дальше — внутренние дороги модели аэропорта")
for _k, _p in enumerate(cw_ends(XIA, "arterial_regulated", None), 1):
    node(f"n_air_gate_s{_k}", _p[0], _p[1], "joint", ["s_air_south"], landmark="airport_alatau",
         why_ru="южные ворота аэропорта: дорога входит на территорию аэропорта (внутренние проезды — модель airport, "
                "Unity); узел на каждой проезжей части")
# --- street over the railway to the southern industry (the tertiary d492aa6d south of the rail)
_rx = LineString([(-3500.0, -300.0), (-3500.0, -4000.0)]).intersection(POLY)
_rx = _rx if _rx.geom_type == "LineString" else max(_rx.geoms, key=lambda g: g.length)
RX_B = min(_rx.coords, key=lambda c: c[1])              # the district's south-west border (the tertiary d492aa6d is in Golden)
RX = [C.on_line(SOUTH, x=-3500.0), (-3500.0, -300.0), RX_B]
street("s_rail_x", "industrial", RX, "проезд над ж/д к южной промзоне", 2032, struct=structs(RX),
       why=MODEL + ": связь Южной промышленной улицы с южной промзоной (за обходной ж/д), до границы района у дороги "
                   "d492aa6d (она — в Golden, в 40 м за границей); над путями обходной ж/д — путепровод (struct overpass, "
                   "gen_network поднимает его на габарит bridges.rail_clearance_m)")

FRAME_IDS = [s["id"] for s in STREETS if s["_layer"] == "frame"]


# ===================================================================================================== 3. existing interchanges
def ic_existing(nid, x, z, typ, streets, ramps, rid, why):
    node(nid, x, z, typ, [s for s in streets if s], keep_existing=True, registry_id=rid,
         osm_ids=[SH[r] for r in ramps if r in SH], why_ru=why)


ic_existing("ic_a3_km46", 106.0, 4023.0, "partial_cloverleaf", [k_of("745abfad"), k_of("87546a75")],
            ["79589a88", "5369dfcc", "0b71c783", "d3e8c84f", "360288d1"], None,
            "существующая развязка А-3 км 46 (OSM): петли и съезды западной стороны как в данных; дорога Енбек – Каскелен "
            "приходит к ней с запада")
ic_existing("ic_a3_km559", 250.0, 13683.0, "trumpet", [k_of("68d9d482"), "s_plateau_stem"],
            ["dfc7b64c", "3e1f1193", "87899a36"], "interchange_a3_km55_9",
            "существующая развязка А-3 км 55,9 (OSM): Дорога плато приходит к концевому узлу съездов")
ic_existing("ic_a3_km44", -231.0, 2060.0, "partial_cloverleaf", [k_of("b0daaa49"), k_of("2c11a22a")], ["05cf2037"], "interchange_a3_km44_0",
            "существующий параллельный съезд А-3 у км 44 (OSM 05cf2037); полная развязка магистрали — уровень 3 с Growing-восток")

# ===================================================================================================== 4. local streets
NO_HOST = {"expressway", "ramp", "pedestrian_street", "bike_path", "boulevard", "driveway_main", "driveway_secondary"}
D_IN = 10.0                     # edge streets run 10 m inside the quarter's border (local red line 15 m: half 7.5 + 2.5)
EXP_HALF = 45.0                 # expressways: half red line 25 + 20 m

DEV_IN = Z.DEV.difference(VILL)
RETIRED = []
for oid, (g, p) in OSM.items():
    if p.get("class") in ("motorway", "tertiary", "secondary", "primary") or oid in KEEP_IDS:
        continue
    gi = g.intersection(POLY)
    if gi.length < 1.0:
        continue
    if p.get("class") == "track" and gi.intersects(DEV_IN):
        RETIRED.append(oid)
    elif gi.intersection(DEV_IN.buffer(5)).length > 0.5 * gi.length and not houses_hit(gi.buffer(30.0)):
        RETIRED.append(oid)                      # a road that serves existing houses stays
    elif p.get("class") == "track" and gi.intersects(AIRPORT_LOT):
        RETIRED.append(oid)                      # field tracks across the airfield
RETIRED_SET = set(RETIRED)
for oid, (g, p) in sorted(OSM.items()):
    if p.get("class") != "service" or p.get("sub") not in ("driveway", "parking_aisle", "alley") or oid in KEEP_IDS \
            or oid in RETIRED_SET:
        continue
    parts = osm_parts(oid)
    if not parts or max(q.length for q in parts) < 3.0:
        continue
    q = max(parts, key=lambda q_: q_.length)
    cls = "village_lane" if q.intersection(VILL).length > 0.5 * q.length else "local_secondary"
    street("v_" + oid[:8], cls, q.coords, "проезд (OSM)", 2025, source="keep_existing:" + oid, years=C.EXISTING, layer="osm",
           why=f"существующий проезд OSM (service/{p.get('sub')}): класс {cls} вместо driveway_secondary, который CONTRACT §8 "
               "не использует")
    KEEP_IDS[oid] = "v_" + oid[:8]
HOST_OSM = {oid for oid, (g, p) in OSM.items() if p.get("class") in ("residential", "service", "unclassified", "living_street",
                                                                      "unknown")}
OSM_HOST = []                   # [(oid, line, class)] existing roads that stay and take new streets
for oid in sorted(HOST_OSM - RETIRED_SET - set(KEEP_IDS)):
    g, p = OSM[oid]
    cls = {"service": "driveway_main", "living_street": "village_secondary"}.get(p["class"], "village_secondary")
    if g.intersection(VILL).length <= 0.5 * g.length and p["class"] in ("residential", "unclassified", "unknown"):
        cls = "local"
    for q in osm_parts(oid):
        OSM_HOST.append((oid, q, cls))
# village tracks gen_network keeps (they serve village houses within 25 m): hosts too
for oid, (g, p) in OSM.items():
    if p.get("class") == "track" and oid not in RETIRED_SET and g.intersection(VILL).length > 0 \
            and houses_hit(g.intersection(VILL.buffer(25)).buffer(25.0)):
        for q in osm_parts(oid):
            OSM_HOST.append((oid, q, "village_lane"))


def all_lines(include_osm=True):
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
    return np.array([math.sin(t), math.cos(t)]), np.array([math.cos(t), -math.sin(t)])


def _ray_hit(p, dvec, lines, reach):
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
UNSERVED = []
# no local street comes into a ring (a local arm on a ring of an arterial is forbidden, norms.node_matrix)
RING_ZONE = unary_union([Point(c).buffer(RING_OUT - 2.5) for _, c in RINGS])
BARRIER = None                   # land kept free of local streets: power-line zones, rail corridors, the airport


def generate_local(barriers=None):
    global BARRIER
    lines = all_lines()
    host = [(sid, L, cls, half) for sid, L, cls, half in lines if cls not in NO_HOST]
    corr = corridors(lines)
    BARRIER = unary_union([POWER_ZONE.buffer(3.0), RAIL_BAR, AIRPORT_LOT.buffer(5.0), RING_ZONE]
                          + ([barriers] if barriers is not None else []))
    corr = corr.union(BARRIER)
    region = DEV_IN.difference(corr).difference(WATER_STRIP).intersection(POLY.buffer(-5))
    pieces = [p for p in getattr(region, "geoms", [region]) if p.area > 15000.0]
    pieces.sort(key=lambda p: (-p.centroid.y, p.centroid.x))
    host_tree = shapely.STRtree([L for _, L, _, _ in host])
    made = 0
    later = []
    zt = [(z, z["poly"]) for z in Z.ZPLAN if z["use"] in Z.GRID]
    for k, piece in enumerate(pieces):
        zs = sorted(((zp.intersection(piece).area, z) for z, zp in zt if zp.intersects(piece)), key=lambda t: -t[0])
        if not zs or zs[0][0] < 1000:
            continue
        zone = zs[0][1]
        S1, S2 = Z.GRID[zone["use"]]
        pb = piece.buffer(60)
        near = [host[i][1] for i in host_tree.query(pb)]
        theta = _dir_deg([L.intersection(pb) for L in near if not L.intersection(pb).is_empty])
        if theta is None:
            mrr = piece.minimum_rotated_rectangle
            c = np.asarray(mrr.exterior.coords)
            v = c[1] - c[0]
            theta = math.degrees(math.atan2(v[0], v[1])) % 90.0
        tag = f"p{k + 1:03d}"
        defer = []
        made += _piece(tag, piece, zone, theta, S1, S2, host, defer=defer)
        if defer:
            later.append((tag, piece, zone, theta, S1, S2, defer))
    if later:
        host = [(sid, L, cls, half) for sid, L, cls, half in all_lines() if cls not in NO_HOST]
        for tag, piece, zone, theta, S1, S2, defer in later:
            made += _piece(tag, piece, zone, theta, S1, S2, host, only_parts=set(defer))
    return made


def _fronted(pt, host, host_tree):
    best = 1e9
    for i in host_tree.query(Point(pt).buffer(D_IN + 40)):
        sid, L, cls, half = host[i]
        best = min(best, L.distance(Point(pt)) - half)
    return best <= D_IN + 6.0


HOUSE_GAP = 10.5


def _detour(LL, hh, inside):
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


def _piece(tag, piece, zone, theta, S1, S2, host, defer=None, only_parts=None):
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
            barrier = unary_union([L for _, L, c_, _ in all_lines(include_osm=False) if c_ in ("expressway", "ramp")]
                                  + [BARRIER.boundary])
            cands = []
            for i in host_tree.query(P.buffer(400)):
                sid, L, cls, half = host[i]
                a, b = nearest_points(ring, L)
                cands.append((a.distance(b), a, b, sid))
            best = None
            for dd, a, b, sid in sorted(cands, key=lambda t: t[0]):
                if dd > 300:
                    break
                conn = LineString([a, b])
                if conn.intersects(barrier) or houses_hit(conn.buffer(7.5)):
                    continue
                best = (dd, a, b, sid)
                break
            if best is None and defer is not None:
                defer.append(j)
                continue
            if best is None:
                UNSERVED.append(P)
                GEN_LOG.append({"what": "квартал без улицы рядом (или путь к ней через трассу / дома / коридор): без сети (резерв)",
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
                   struct=structs([(a.x, a.y), (b.x, b.y)]),
                   why=MODEL + ": квартал окружён сёлами, парками, водой или коридорами — кольцевая улица и выезд к ближайшей улице")
        else:
            i0 = next((i for i in range(m) if fr[i]), 0)
            order = [(i0 + t) % m for t in range(m)]
            runs, cur = [], []
            for i in order:
                if not fr[i]:
                    cur.append(i)
                elif cur:
                    runs.append(cur)
                    cur = []
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
            why = MODEL + ": улица по краю квартала (" + zone["id"] + ") вдоль села, парка, воды, коридора или трассы"
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
                street(f"e_{tag}_{j}_{i}" + (f"_{pi}" if pi else ""), cls_local, q.coords, "улица по краю квартала", yb,
                       layer="edge", why=why, struct=structs(list(q.coords)))
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
                        d_out = -dvec if end == 0 else dvec
                        hit = _ray_hit(e, d_out, host_lines + edge_now, D_IN + 45.0)
                        if hit is not None:
                            if end == 0:
                                line.insert(0, hit)
                            else:
                                line.append(hit)
                    LL = LineString(line)
                    hh = houses_hit(LL.buffer(7.5))
                    if hh:
                        dt = _detour(LL, hh, piece)
                        if dt is None:
                            GEN_LOG.append({"what": "линия сетки задевает дом: снята", "piece": tag,
                                            "at": [round(v_) for v_ in LL.centroid.coords[0]]})
                            continue
                        GEN_LOG.append({"what": "линия сетки обходит дом", "piece": tag,
                                        "at": [round(v_) for v_ in hh[0].centroid.coords[0]]})
                        LL = dt
                    street(f"g_{tag}_{j}_{fam}{kk - k0:02d}" + (f"_{qi}" if qi else ""), cls_local, LL.coords, "улица квартала",
                           yb, layer="grid", why=MODEL + f": сетка квартала зоны {zone['id']} (шаг {S:.0f} м)",
                           struct=structs(list(LL.coords)))
                    n += 1
    return n


# ===================================================================================================== 5. post-pass
GEN = ("edge", "grid")
NO_JUNCTION = {"expressway", "ramp"}


def _all3():
    out = [(s["id"], LineString(s["line"]), s["class"]) for s in STREETS]
    out += [("osm:" + oid, q, cls) for oid, q, cls in OSM_HOST]
    return out


def _attached(pt, others, tree, extra_ok, skip=None):
    P = Point(pt)
    for i in tree.query(P.buffer(0.6)):
        sid, L, cls = others[i]
        if sid == skip or cls in NO_JUNCTION:
            continue
        if L.distance(P) < 0.5:
            return True
    return extra_ok(P)


def _cut_points(L, others, tree, s, skip=None):
    spans = []
    for st in s.get("struct") or []:
        a, b = L.project(Point(st["from"])), L.project(Point(st["to"]))
        spans.append((min(a, b), max(a, b)))
    ch = []
    for i in tree.query(L.buffer(0.6)):
        sid, M, cls = others[i]
        if sid == skip or cls in NO_JUNCTION:
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
    shorter than min_len; repeated until nothing changes."""
    changed, rounds = True, 0
    while changed and rounds < 12:
        changed, rounds = False, rounds + 1
        others_all = _all3()
        tree = shapely.STRtree([L for _, L, _ in others_all])
        drop = set()
        for k, s in enumerate(STREETS):
            if s["_layer"] not in layers:
                continue
            L = LineString(s["line"])
            f0 = not _attached(s["line"][0], others_all, tree, extra_ok, skip=s["id"])
            f1 = not _attached(s["line"][-1], others_all, tree, extra_ok, skip=s["id"])
            if not (f0 or f1):
                continue
            ch = [c for c in _cut_points(L, others_all, tree, s, skip=s["id"]) if 0.5 < c < L.length - 0.5]
            a = ch[0] if (f0 and ch) else (0.0 if not f0 else None)
            b = ch[-1] if (f1 and ch) else (L.length if not f1 else None)
            if a is None or b is None or b - a < min_len:
                drop.add(k)
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
    moved = 0
    oth_all = _all3()
    tree = shapely.STRtree([q for _, q, _ in oth_all])
    ends = []
    for idx, (_, q, _) in enumerate(oth_all):
        ends.append((Point(q.coords[0]), idx))
        ends.append((Point(q.coords[-1]), idx))
    etree = shapely.STRtree([e for e, _ in ends])
    for s in STREETS:
        if s["_layer"] not in layers:
            continue
        for e in (0, -1):
            P = Point(s["line"][e])
            on_ = [oth_all[i][1] for i in tree.query(P.buffer(0.6)) if oth_all[i][0] != s["id"]
                   and oth_all[i][2] not in NO_JUNCTION and oth_all[i][1].distance(P) < 0.5]
            if not on_:
                continue
            near = sorted((ends[i][0].distance(P), ends[i][0]) for i in etree.query(P.buffer(tol))
                          if oth_all[ends[i][1]][0] != s["id"])
            if not near or near[0][0] <= 0.5:
                continue
            for d, Q in near:
                if d >= tol:
                    break
                if any(M.distance(Q) < 0.5 for M in on_):
                    s["line"][e] = [round(Q.x, 1), round(Q.y, 1)]
                    moved += 1
                    if log is not None:
                        log.append({"what": "конец улицы перенесён на соседний перекрёсток (один узел вместо двух)",
                                    "id": s["id"], "m": round(d, 1), "at": [round(Q.x), round(Q.y)]})
                    break
    return moved


def align_opposite_ts(tol=30.0, log=None):
    """Streets that end on a divided street from opposite sides a few metres apart make two staggered junctions across one
    median (gen_network joins them into a 5-arm node and a ring): the later one is moved onto the other's point, its last
    stretch square to the divided street (from outside its red line), so the two make one crossing."""
    moved = 0
    gen = {s["id"]: s for s in STREETS if s["_layer"] in GEN + ("lane",)}
    for H in [s for s in STREETS if cw_off(s["class"], s.get("profile")) > 0.0]:
        HL = LineString(H["line"])
        ap = red_w(H["class"], H.get("profile")) / 2.0 + 8.0
        ts = []
        for s in gen.values():
            for e in (0, -1):
                P = Point(s["line"][e])
                if HL.distance(P) > 0.5:
                    continue
                c = HL.project(P)
                t = _tangent(HL, c)
                q = np.array(s["line"][1 if e == 0 else -2], float) - np.array([P.x, P.y])
                ts.append((c, float(np.sign(t[0] * q[1] - t[1] * q[0])), s["id"], e))
        ts.sort()
        used = set()
        for (ca, sa, ida, ea), (cb, sb, idb, eb) in zip(ts[:-1], ts[1:]):
            if sa == sb or not (0.5 < cb - ca < tol) or ida in used or idb in used or ida == idb:
                continue
            # move the end whose street has room for a square approach outside the red line
            for (c0, s0, i0, e0), (c1, s1, i1, e1) in (((ca, sa, ida, ea), (cb, sb, idb, eb)), ((cb, sb, idb, eb), (ca, sa, ida, ea))):
                s = gen[i1]
                Q = HL.interpolate(c0)
                t = _tangent(HL, c0)
                n = np.array([-t[1], t[0]]) * s1
                A = np.array([Q.x, Q.y]) + n * ap
                line = s["line"] if e1 == -1 else s["line"][::-1]
                X = np.array(line[-2], float)
                if HL.distance(Point(X)) < ap + 5.0:
                    continue
                newL = [list(map(float, p)) for p in line[:-1]] + [[round(A[0], 1), round(A[1], 1)], [round(Q.x, 1), round(Q.y, 1)]]
                seg = LineString([tuple(X), tuple(A), (Q.x, Q.y)])
                if houses_hit(seg.buffer(red_w(s["class"]) / 2.0)) or seg.intersects(WATER_POLY):
                    continue
                s["line"] = newL if e1 == -1 else newL[::-1]
                used |= {i0, i1}
                moved += 1
                if log is not None:
                    log.append({"what": "примыкание с другой стороны магистрали перенесено напротив (один перекрёсток вместо двух)",
                                "id": i1, "to": i0, "m": round(abs(c1 - c0), 1)})
                break
    return moved


def close_gaps(tol=2.0, log=None):
    """New street ends a few decimetres off the street they meet (a cut back to a junction lands up to 0.6 m off it): moved
    onto the nearest point of that street, so the junction is one node."""
    oth_all = _all3()
    tree = shapely.STRtree([q for _, q, _ in oth_all])
    n = 0
    for s in STREETS:
        if s["_layer"] == "osm":
            continue
        for e in (0, -1):
            P = Point(s["line"][e])
            best = None
            for i in tree.query(P.buffer(tol)):
                sid, M, cls = oth_all[i]
                if sid == s["id"] or cls in NO_JUNCTION:
                    continue
                d = M.distance(P)
                if best is None or d < best[0]:
                    best = (d, M, sid)
            if best is None or best[0] < 0.05 or best[0] > tol:
                continue
            Q = best[1].interpolate(best[1].project(P))
            s["line"][e] = [round(Q.x, 2), round(Q.y, 2)]
            n += 1
            if log is not None:
                log.append({"what": "конец улицы доведён до улицы, на которой он стоит", "id": s["id"], "to": best[2],
                            "m": round(best[0], 2)})
    return n


LANE_REACH = 25.0
LANE_MAX = 150.0
LINK_MAX = 150.0
LINK_MIN = 15.0
DEAD_END_OK = {"driveway_main", "driveway_secondary", "local", "local_secondary", "village_lane"}


def house_lanes(log=None):
    """Existing houses outside the villages and outside the new quarters (farms, zimovkas) with no street within
    LANE_REACH: a village lane from the nearest street toward the group (≤ LANE_MAX, its red line 1.5 m short of the
    house, never through a house, across an expressway, a ramp, water, a power-line zone or a rail corridor)."""
    hs = [h for h in HOUSES if POLY.contains(h.centroid) and not VILL.contains(h.centroid)
          and not Z.DEV.buffer(-5.0).contains(h.centroid)]
    lines = [(s["id"], LineString(s["line"])) for s in STREETS if s["class"] not in ("expressway", "ramp", "pedestrian_street", "bike_path")]
    lines += [("osm:" + oid, q) for oid, q, cls in OSM_HOST]
    lt = shapely.STRtree([q for _, q in lines])
    barrier = unary_union([LineString(s["line"]) for s in STREETS if s["class"] in ("expressway", "ramp")])
    far = [h for h in hs if lines[int(lt.query_nearest(h)[0])][1].distance(h) > LANE_REACH]
    if not far:
        return 0
    grp = unary_union([h.buffer(20.0) for h in far])
    made = 0
    rh = red_w("village_lane") / 2.0
    for k, G in enumerate(getattr(grp, "geoms", [grp])):
        mine = [h for h in far if G.contains(h.centroid)]
        hu = unary_union(mine)
        i = int(lt.query_nearest(hu)[0])
        sid, L = lines[i]
        a, b = nearest_points(L, hu)
        d = a.distance(b)
        rec = {"at": [round(b.x), round(b.y)], "houses": len(mine), "host": sid, "m": round(d)}
        if d - rh - 1.5 > LANE_MAX:
            if log is not None:
                log.append({"what": "дом вне села дальше 150 м от улицы: проулка нет (ждёт решения)", **rec})
            continue
        end = LineString([a, b]).interpolate(d - rh - 1.5)
        lane = LineString([(a.x, a.y), (end.x, end.y)])
        if lane.length < LINK_MIN - 0.5 or houses_hit(lane.buffer(rh + 1.0)) or lane.crosses(barrier) \
                or lane.intersects(WATER_POLY) or lane.intersection(POWER_ZONE).length > 60.0 or lane.intersects(RAIL_BAR):
            if log is not None:
                log.append({"what": "дом вне села: проулок к нему пересёк бы дом, трассу, воду или коридор — не строится", **rec})
            continue
        made += 1
        street(f"v_lane_{made:02d}", "village_lane", lane.coords, "проезд к существующему дому", 2026, layer="lane",
               why=MODEL + f": существующий дом вне села без улицы в {LANE_REACH:.0f} м — проулок от {sid} (≤ {LANE_MAX:.0f} м, "
                           "тупик класса village_lane)")
        if log is not None:
            log.append({"what": "проулок к существующему дому вне села", "id": f"v_lane_{made:02d}", **rec})
    return made


def link_dead_ends(log=None):
    """Existing roads that end in nothing inside the district: a straight through link from the dead end to the nearest
    other street (≤ LINK_MAX, never through a house, across an expressway, a ramp, water or a rail corridor, never back
    along its own road). A dead end with no such link stays as OSM has it (logged)."""
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
            if POLY.exterior.distance(E) < 3.0:
                continue
            if any(j != i and lines[j][1].distance(E) < 0.5 for j in tree.query(E.buffer(0.6))) \
                    or any(k.distance(E) < 0.5 for k in links):
                continue
            ch = _cut_points(L, lines, tree, {"struct": []}, skip=sid)
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
                        or not POLY.contains(link) or link.intersects(RAIL_BAR) or link.intersection(POWER_ZONE).length > 60.0:
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


SNAP_J = 6.0
SNAP_N = 1.0                     # m: piece ends of phase_years closer than this are one node (new ends are exact)
GOOD_CUT_M = 0.25                # m: planarize merges new ends within 0.3 m
GRADE_SEP_TYPES = {"grade_separation", "diamond", "partial_cloverleaf", "cloverleaf", "trumpet", "directional"}


def _tangent(L, s, d=3.0):
    a = L.interpolate(max(0.0, s - d))
    b = L.interpolate(min(L.length, s + d))
    v = np.array([b.x - a.x, b.y - a.y])
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def phase_years(use="road", log=None):
    """Opening years by pieces of street between junctions (push only): a piece of a new street opens no earlier than
    some street at each of its ends; a street whose pieces get different years is split into runs (the first keeps the id).
    Existing roads are 2025 and end blind as OSM has them; joints, rings and the district edge do not hold a piece back.
    * a cul-de-sac piece (one end free) holds nothing up: the street it hangs on needs another street there;
    * a divided street changes its year only at a junction where its carriageway ends meet the cross street's own nodes
      (every cross street there within ~2° of square to it: offset·|cot a| ≤ GOOD_CUT_M); elsewhere it opens as one piece, and
      where it continues a divided street of its corridor only that street (or a square junction) holds it."""
    lines = [(s["id"], LineString(s["line"]), s["class"], s) for s in STREETS]
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

    off = {sid: cw_off(cls, (s or {}).get("profile")) for sid, L, cls, s in lines if s is not None}
    corr = {sid: ((s or {}).get("axis") or sid) for sid, L, cls, s in lines}

    def good(sid, L, c, d2):
        e = off.get(sid, 0.0)
        if e <= 0.0:
            return True
        t = _tangent(L, c)
        cs = abs(float(np.dot(t, d2)))
        sn = abs(float(t[0] * d2[1] - t[1] * d2[0]))
        return sn > 1e-6 and e * cs / sn <= GOOD_CUT_M

    cuts = {sid: {0.0, L.length} for sid, L, _, _ in lines}
    good_c = {sid: set() for sid, L, _, _ in lines}
    bad_c = {sid: set() for sid, L, _, _ in lines}          # a cut is good only when every cross street there is square
    for i, (sid, L, cls, s) in enumerate(lines):
        if cls == "expressway":
            continue
        for j in tree.query(L.buffer(0.6)):
            if j == i:
                continue
            sid2, M, cls2, _ = lines[j]
            if cls2 == "expressway":
                continue
            for e in (0, -1):
                P = Point(M.coords[e])
                if L.distance(P) < 0.6:
                    c = L.project(P)
                    cuts[sid].add(c)
                    if corr[sid2] != corr[sid] and cls2 not in NO_JUNCTION:
                        q = M.coords[1] if e == 0 else M.coords[-2]
                        d2 = np.array([P.x - q[0], P.y - q[1]])
                        d2 = d2 / max(np.linalg.norm(d2), 1e-9)
                        if good(sid, L, c, d2):
                            good_c[sid].add(c)
                        else:
                            bad_c[sid].add(c)
            if cls in NO_JUNCTION or cls2 in NO_JUNCTION:
                continue
            x = L.intersection(M)
            for q in getattr(x, "geoms", [x]):
                if q.is_empty or q.geom_type != "Point":
                    continue
                if in_span(sid, q) or in_span(sid2, q) or any(q.distance(g) < 25.0 for g in gsep):
                    continue
                c = L.project(q)
                cuts[sid].add(c)
                if good(sid, L, c, _tangent(M, M.project(q))):
                    good_c[sid].add(c)
                else:
                    bad_c[sid].add(c)
    pieces = []                                    # [sid, a, b, good start, good end]
    for sid, L, cls, s in lines:
        ch = sorted(cuts[sid])
        m = [ch[0]]
        for c in ch[1:]:
            if c - m[-1] > SNAP_N:
                m.append(c)
        if L.length - m[-1] > 0.01:
            m[-1] = L.length
        gs = sorted(good_c[sid])
        bs = sorted(bad_c[sid])

        def is_good(c):
            return off.get(sid, 0.0) <= 0.0 or (any(abs(c - g) <= SNAP_N for g in gs)
                                                and not any(abs(c - g) <= SNAP_N for g in bs))
        for a, b in zip(m[:-1], m[1:]):
            pieces.append([sid, a, b, is_good(a), is_good(b)])
    LID = {sid: (L, cls, s) for sid, L, cls, s in lines}
    pts = []
    for k, (sid, a, b, _, _) in enumerate(pieces):
        L = LID[sid][0]
        pts.append(L.interpolate(a))
        pts.append(L.interpolate(b))
    ptree = shapely.STRtree(pts)
    parent = list(range(len(pts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, P in enumerate(pts):
        for j in ptree.query(P.buffer(SNAP_N)):
            if j != i and P.distance(pts[j]) < SNAP_N:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    node_of = [find(i) for i in range(len(pts))]
    at = {}
    for i, n in enumerate(node_of):
        at.setdefault(n, []).append(i // 2)
    joints = [Point(n["x"], n["z"]) for n in NODES.values() if n["type"] == "joint"]
    rings = [Point(c) for _, c in RINGS]
    edge = {n for n in at if POLY.exterior.distance(pts[n]) < 3.0 or any(pts[n].distance(j) < 10.0 for j in joints)
            or any(pts[n].distance(r) < RING_R for r in rings)}
    # cul-de-sac pieces: an end with no other piece (and not at the edge)
    leaf = set()
    for k in range(len(pieces)):
        for n in (node_of[2 * k], node_of[2 * k + 1]):
            if n not in edge and all(q == k for q in at[n]):
                leaf.add(k)
    grp, year, fixed = [], {}, set()
    run = {}
    for k, (sid, a, b, ga, gb) in enumerate(pieces):
        L, cls, s = LID[sid]
        if s is None:
            g = sid
        elif off.get(sid, 0.0) > 0.0:
            # a divided street: one group from one square junction to the next
            if sid not in run or ga:
                run[sid] = run.get(sid, -1) + 1
            g = (sid, "run", run[sid])
        else:
            g = (sid, k)
        grp.append(g)
        year[g] = 2025 if s is None else int(s["years"][0])
        if s is None or s.get("_layer") == "osm":
            fixed.add(g)
    for _ in range(400):
        moved = False
        for k in range(len(pieces)):
            g = grp[k]
            if g in fixed:
                continue
            sid = pieces[k][0]
            for e, n in ((0, node_of[2 * k]), (1, node_of[2 * k + 1])):
                if n in edge:
                    continue
                if any(grp[q] == g for q in at[n] if q != k):
                    continue                                   # the group goes on through this node
                o = [q for q in at[n] if q != k and grp[q] != g and q not in leaf]
                if off.get(sid, 0.0) > 0.0 and not pieces[k][3 + e]:
                    cont = [q for q in o if corr[pieces[q][0]] == corr[sid] and off.get(pieces[q][0], 0.0) > 0.0]
                    if cont:
                        o = cont
                ys = [year[grp[q]] for q in o]
                if not ys:
                    continue
                need = min(ys)
                if need > year[g]:
                    year[g] = need
                    moved = True
        if not moved:
            break
    by_sid = {}
    for k, (sid, a, b, _, _) in enumerate(pieces):
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
        made = [s]
        for i, (a, b, y) in enumerate(runs):
            q = substring(L, a, b)
            st = [x for x in s.get("struct") or [] if q.distance(Point(x["from"])) < 1.0 and q.distance(Point(x["to"])) < 1.0]
            if i == 0:
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
            s2["years"] = Y4(y, use) if (i != 0 or y != y_old) else s["years"]
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
        log.append({"what": "годы по участкам улиц: без тупиков в каждом году", "moved": len(moves), "split": len(new_streets)})
    return moves


def summary():
    from collections import Counter
    c = Counter((s["_layer"], s["class"]) for s in STREETS)
    for k, v in sorted(c.items()):
        km = sum(LineString(s["line"]).length for s in STREETS if (s["_layer"], s["class"]) == k) / 1000
        print(f"  {k[0]:6s} {k[1]:20s} {v:5d} {km:7.1f} km")


if __name__ == "__main__":
    summary()
