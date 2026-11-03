#!/usr/bin/env python3
"""Growing-East · level 2 · street network of the whole district (w53), imported by growing_e_build.py.

    python3 -I tools/map/district/growing_e_net.py          # build in memory and print a summary

The network is made of three layers (the approach of the Gate builder gate_net.py, not its content):
  1. existing roads (Overture/OSM): the A-3 with its ramps and interchanges, the tract through Zhetygen, the village streets
     and the roads that serve houses stay as they are (gen_network takes them from OSM); other existing roads inside new
     quarters are replaced (replaced_osm);
  2. the frame of new streets by the level-0 scheme axes (Центральная, Южная, Восточная магистрали, the streets from the A-3
     interchanges, the LRT avenue, the OIZ and industrial streets, the bridge to Заречное, the pedestrian embankment);
  3. local streets of every new quarter, generated here (the generator's grid is off for v1 specs): an edge street along
     every side of the quarter that has no street (village, park, river, expressway, district edge) and a grid at the zone's
     block size, aligned with the frame, every end on a street.
Every coordinate not from a source is the cartographer's design (label «модель qTwin»). Unity frame: X east, Z north.
"""
import copy
import heapq
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
import shapely.ops  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.ops import substring, unary_union  # noqa: E402

import growing_e_common as C  # noqa: E402
import growing_e_zones as Z  # noqa: E402
import land_util as LU  # noqa: E402

T0 = time.time()
MODEL = C.MODEL
Y4 = C.Y4
fillet = C.fillet
DIST = C.DIST
V0 = C.V0
AX = {a["id"]: a for a in V0["axes"]}
LOG = []

_LN = LU.Norms()
_RW = {}


def red_w(cls, profile=None):
    if cls not in _RW:
        _RW[cls] = float(LU.profile_from_norms(_LN, cls)["red_line_w"])
    w = _RW[cls]
    g = float((profile or {}).get("green_w") or (profile or {}).get("median_w") or 0.0)
    return max(w, g + 30.0) if g > 6.0 else w


# ===================================================================================================== open data
OSM = {p["id"]: (g, p) for g, p in C.layer_in("roads", DIST)}
SH = {k[:8]: k for k in OSM}


def osm(short):
    return OSM[SH[short]]


VILL = Z.vill_union()
_W = C.layer_in("water", DIST.buffer(200))
WATER_POLY = unary_union([g for g, p in _W if g.geom_type in ("Polygon", "MultiPolygon") and p.get("class") != "swimming_pool"])
WATER_LINE = unary_union([g for g, p in _W if g.geom_type in ("LineString", "MultiLineString")])
# the carriageway is wider than its axis: a bridge starts where the carriage (≤ 12 m half width) meets the water, not the axis
# (run 2, rule 4: s_south (373.6, -232.5), s_km44 (2605.2, 2433.5), s_ind2 (9050.2, 2034.4), v_link_019 (2585.1, 1686.4))
WATER_POLY_G = WATER_POLY.buffer(12.0)
STRIP = 35.0                                       # flood.water_protection_strip_min_m
WATER_STRIP = unary_union([WATER_POLY.buffer(STRIP), WATER_LINE.buffer(STRIP)])
RAIL = unary_union([g for g, p in C.layer_in("rail", DIST.buffer(100))])
RAIL_CLEAR = 30.0                                  # half span of a street overpass over the tracks (m), model

from gen_blocks_lots import existing_houses  # noqa: E402

_t = time.time()
HOUSES = [h["fp"] for h in existing_houses(DIST.buffer(80), Polygon())]
HTREE = shapely.STRtree(HOUSES)
LOG.append({"what": "существующие дома (twin existing_osm + Overture ≥ 25 м²)", "n": len(HOUSES), "s": round(time.time() - _t, 1)})


def houses_hit(geom):
    return [HOUSES[i] for i in HTREE.query(geom, predicate="intersects")]


# ===================================================================================================== registries
STREETS, NODES = [], {}
SID = {}
CHANGES = []                     # frame changes against the level-0 scheme: (id, why)


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


def _spans(L, geoms, pad):
    spans = []
    for g in geoms:
        if g is None or g.is_empty:
            continue
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
    return merged


def water_bridges(line, pad=12.0):
    """Struct spans (bridge) where a new line crosses water (streams and water polygons), each padded on both sides."""
    L = LineString(line)
    out = []
    for a, b in _spans(L, (WATER_LINE, WATER_POLY_G), pad):
        a, b = max(a, 0.5), min(b, L.length - 0.5)
        if b - a > 2:
            pa, pb = L.interpolate(a), L.interpolate(b)
            out.append(((pa.x, pa.y), (pb.x, pb.y), "bridge"))
    return out


def rail_overpasses(line, pad=RAIL_CLEAR):
    """Struct spans (overpass) where a new line crosses the railways (Турксиб, обход Жетыген – Казыбек бек, the KNAUF and
    TLC sidings): «переезды в разных уровнях» (plan, Турксиб). Spans of a multi-track crossing merge into one."""
    L = LineString(line)
    out = []
    for a, b in _spans(L, (RAIL,), pad):
        a, b = max(a, 0.5), min(b, L.length - 0.5)
        if b - a > 2:
            pa, pb = L.interpolate(a), L.interpolate(b)
            out.append(((pa.x, pa.y), (pb.x, pb.y), "overpass"))
    return out


def structs(line):
    """Bridges over water and overpasses over the tracks of a new line, without overlaps (an overpass wins)."""
    ov = rail_overpasses(line)
    br = water_bridges(line)
    L = LineString(line)
    keep = list(ov)
    for a, b, k in br:
        sa, sb = sorted((L.project(Point(a)), L.project(Point(b))))
        if any(not (sb < min(L.project(Point(x)), L.project(Point(y))) or sa > max(L.project(Point(x)), L.project(Point(y))))
               for x, y, _ in ov):
            continue
        keep.append((a, b, k))
    return keep


# ===================================================================================================== 1. existing roads
VILLAGE_OSM = {"residential", "service", "unclassified", "living_street", "unknown"}
KEEP_IDS = {}


def osm_class(p, g):
    c, sub = p.get("class"), p.get("sub")
    if c == "motorway":
        return "ramp" if sub == "link" else "expressway"
    if c in ("tertiary", "secondary", "primary"):
        if sub == "link":
            return "village_main" if g.intersection(VILL).length > 0.5 * g.length else "district_transport"
        return "village_main" if g.intersection(VILL).length > 0.5 * g.length else "district_transport"
    return None


def keep_name(p):
    n = p.get("name") or ""
    if n.startswith("Алматы") or n.startswith("Almaty"):
        return "А-3 Алматы – Қонаев"
    if p.get("sub") == "link":
        return "съезд развязки"
    return n


def osm_parts(oid, poly=DIST):
    g = OSM[oid][0].intersection(poly)
    return [q for q in C.lines_of(g) if q.length >= 3.0]


# the Central magistral of the scheme rebuilds the existing road from the A-3 km 46 interchange to the tract (secondary,
# 3 km): these OSM pieces are replaced by the new street on the same alignment (replaced_osm)
CENTRAL_OLD = ["196070bc", "df2c007f", "2874dce7", "25fa2b80", "3594c363"]
RETIRED = [SH[s] for s in CENTRAL_OLD if s in SH]
RETIRED_WHY = {SH[s]: "реконструкция: Центральная магистраль на трассе существующей дороги" for s in CENTRAL_OLD if s in SH}

for oid, (g, p) in sorted(OSM.items()):
    if oid in RETIRED_WHY:
        continue
    cls = osm_class(p, g)
    if cls is None:
        continue
    pool = DIST.buffer(2.0) if cls in ("expressway", "ramp") else DIST
    parts = osm_parts(oid, pool)
    if not parts:
        continue
    sid = ("k_" if cls in ("expressway", "ramp") else "t_") + oid[:8]
    nm = keep_name(p)
    ax = "ax_a3" if cls == "expressway" else None
    line = max(parts, key=lambda q: q.length).coords
    street(sid, cls, line, nm or ("улица села" if cls == "village_main" else "существующая дорога"), 2025,
           oneway=cls in ("expressway", "ramp"), source="keep_existing:" + oid, axis=ax, years=C.EXISTING, layer="osm",
           why="существующая дорога OSM/Overture, как есть (направление линии = направление движения)" if cls in ("expressway", "ramp")
           else "существующая дорога OSM, как есть")
    KEEP_IDS[oid] = sid

# Восточная магистраль, южный участок (ax_east_s): the scheme lays it on the existing tract Алматы – Жетыген (OSM secondary
# 72d99739, e4b125d0 …): the OSM pieces along the axis get the class of the frame (arterial_regulated) and the axis; the long
# way 782874d5 (Илийский тракт) runs on along ax_tract to Жетыген and keeps district_transport
_EAST_S = LineString(AX["ax_east_s"]["line"]).buffer(60.0)
EAST_S_UP = []
for s in STREETS:
    if s["_layer"] != "osm" or s["class"] not in ("district_transport", "village_main"):
        continue
    oid = s["source"].split(":", 1)[1]
    L = LineString(s["line"])
    if OSM[oid][1].get("sub") == "link" or L.length < 40.0 or L.intersection(_EAST_S).length < 0.8 * L.length:
        continue
    s["class"], s["axis"] = "arterial_regulated", "ax_east_s"
    s["name_ru"] = "Восточная магистраль (тракт Алматы – Жетыген)"
    s["why"] = ("существующая дорога OSM на оси схемы ax_east_s: тракт Алматы – Жетыген становится Восточной магистралью "
                "(класс arterial_regulated, как остальные магистрали района; трасса и год — как в данных)")
    EAST_S_UP.append(s["id"])
CHANGES.append(("ax_east_s", "магистраль непрерывного движения схемы (trunk) — магистральная улица регулируемого движения "
                             "(arterial_regulated) на существующем тракте: к тракту примыкают сёла и кварталы, развязки в разных "
                             "уровнях через 0,8–1,2 км на тракте не помещаются без сноса домов; так же — все магистрали схемы"))

# existing roads inside new quarters are replaced by the new streets (tracks are not built anyway); a road that serves
# existing houses stays
DEV = Z.dev_union()
DEV_IN = DEV.difference(VILL)
for oid, (g, p) in OSM.items():
    if p.get("class") in ("motorway", "tertiary", "secondary", "primary") or oid in KEEP_IDS or oid in RETIRED_WHY:
        continue
    gi = g.intersection(DIST)
    if gi.length < 1.0:
        continue
    if p.get("class") == "track" and gi.intersects(DEV_IN):
        RETIRED.append(oid)
        RETIRED_WHY[oid] = "полевая дорога внутри нового квартала"
    elif gi.intersection(DEV_IN.buffer(5)).length > 0.5 * gi.length and not houses_hit(gi.buffer(30.0)):
        RETIRED.append(oid)
        RETIRED_WHY[oid] = "дорога внутри нового квартала без домов: заменяется улицами квартала"
RETIRED_SET = set(RETIRED)
# OSM service drives (sub driveway / parking_aisle / alley) would come out of gen_network as driveway_secondary, a class
# CONTRACT §8 does not use: the ones that stay are kept as village lanes (in a village) or local side streets
for oid, (g, p) in sorted(OSM.items()):
    if p.get("class") != "service" or p.get("sub") not in ("driveway", "parking_aisle", "alley") or oid in KEEP_IDS \
            or oid in RETIRED_SET:
        continue
    parts = osm_parts(oid)
    if not parts:
        continue
    q = max(parts, key=lambda q_: q_.length)
    cls = "village_lane" if q.intersection(VILL).length > 0.5 * q.length else "local_secondary"
    street("v_" + oid[:8], cls, q.coords, "проезд (OSM)", 2025, source="keep_existing:" + oid, years=C.EXISTING, layer="osm",
           why=f"существующий проезд OSM (service/{p.get('sub')}): класс {cls} вместо driveway_secondary, который CONTRACT §8 "
               "не использует")
    KEEP_IDS[oid] = "v_" + oid[:8]
HOST_OSM = {oid for oid, (g, p) in OSM.items() if p.get("class") in VILLAGE_OSM}
OSM_HOST = []                   # [(oid, line, class)] existing roads that stay and take new streets
for oid in sorted(HOST_OSM - RETIRED_SET - set(KEEP_IDS)):
    g, p = OSM[oid]
    cls = {"service": "driveway_main", "living_street": "village_secondary"}.get(p["class"], "village_secondary")
    if g.intersection(VILL).length <= 0.5 * g.length and p["class"] in ("residential", "unclassified", "unknown"):
        cls = "local"
    for q in osm_parts(oid):
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


# ===================================================================================================== 2. frame of new streets
LRT_PROFILE = {"median_w": 8.0, "lanes": [2, 2],
               "note_ru": "в разделительной полосе — пути ЛРТ (двухпутный коридор lrt.corridor_width_m 7,6 м)"}
RES_EAST_TRUNK = {"median_w": 8.0, "lanes": [2, 2],
                  "note_ru": "широкая разделительная полоса — резерв коридора ЛРТ к Жетыгену (решение владельца 31.10)"}


def axis_line(aid, R=None):
    pts_ = [tuple(map(float, p)) for p in AX[aid]["line"]]
    return fillet(pts_, R) if R else pts_


def years0(aid):
    return int(AX[aid]["years"][0])


def clip_in(pts_, sid=None):
    """The longest piece of a line inside the district (a scheme axis may start at a joint a few metres outside the border or
    leave the district for a while): ends that leave the district end on the border."""
    L = LineString(pts_)
    g = L.intersection(DIST.buffer(0.3))
    parts = C.lines_of(g) if not g.is_empty else []
    if not parts:
        return pts_
    q = max(parts, key=lambda a: a.length)
    if q.length < L.length - 0.5 and sid:
        CHANGES.append((sid, f"трасса оси обрезана по границе района: вне района {L.length - q.length:.0f} м (улица кончается на границе)"))
    out = [tuple(p) for p in q.coords]
    if math.dist(out[0], pts_[-1]) < math.dist(out[0], pts_[0]) and math.dist(out[-1], pts_[0]) < math.dist(out[-1], pts_[-1]):
        out = out[::-1]
    return out


def frame(sid, cls, pts_, name, base, axis, why, profile=None):
    pts_ = clip_in(pts_, sid)
    st = structs(pts_)
    s = street(sid, cls, pts_, name, base, axis=axis, struct=st, profile=profile, why=why, layer="frame")
    return s


# --- Центральная магистраль: on the existing road from the km 46 interchange to the tract (reconstruction), then the scheme
_old = [osm(s)[0] for s in CENTRAL_OLD]
_oldline = shapely.ops.linemerge(unary_union(_old))
if _oldline.geom_type != "LineString":
    _oldline = max(C.lines_of(_oldline), key=lambda q: q.length)
_oc = list(_oldline.coords)
if _oc[0][0] > _oc[-1][0]:
    _oc = _oc[::-1]
_east = [tuple(map(float, p)) for p in AX["ax_central"]["line"]]
_east = [p for p in _east if p[0] > _oc[-1][0] + 300.0]
CENTRAL = _oc[:-1] + fillet([_oc[-2], _oc[-1]] + _east, 450)[1:]
frame("s_central", "arterial_regulated", CENTRAL, "Центральная магистраль Growing", years0("ax_central"), "ax_central",
      "схема ax_central (2027–30): реконструкция существующей дороги от развязки А-3 км 46 до тракта (3 км, на её трассе; "
      "существующие отрезки — в replaced_osm), дальше новая трасса через Турксиб (путепровод) в промпояс; реестр "
      "road_growing_10km «дорога 10,3 км с путепроводом 400 м» (модель qTwin трассы); широкая разделительная полоса от центра "
      "до Восточной магистрали — резерв коридора ЛРТ к Жетыгену (решение владельца 31.10)",
      profile={"median_w": 8.0, "lanes": [2, 2], "note_ru": "широкая разделительная полоса — резерв коридора ЛРТ от станции «Центр "
                                                           "Growing» к Восточной магистрали и Жетыгену (решение владельца 31.10)"})
# --- Южная промышленная магистраль
SOUTH = fillet(axis_line("ax_south"), 450)
frame("s_south", "arterial_regulated", SOUTH, "Южная промышленная магистраль", years0("ax_south"), "ax_south",
      "схема ax_south (2026–29): от развязки А-3 км 42,4 в обход Жанаарны с юга к промпоясу; путепроводы над ж/д")
# --- Восточная магистраль, северный участок (обход Жетыгена с запада)
EASTN = fillet(axis_line("ax_east_n"), 450)
frame("s_east_n", "arterial_regulated", EASTN, "Восточная магистраль (обход Жетыгена)", years0("ax_east_n"), "ax_east_n",
      "схема ax_east_n (2036–40): продолжение тракта (ax_east_s) на север в обход Жетыгена с запада к дороге на ТЛЦ; широкая "
      "разделительная полоса — резерв коридора ЛРТ к Жетыгену (решение владельца 31.10)", profile=dict(RES_EAST_TRUNK))
# --- streets from the A-3 interchanges
KM44 = fillet(axis_line("ax_km44"), 350)
frame("s_km44", "arterial_regulated", KM44, "Улица от развязки А-3 км 44", years0("ax_km44"), "ax_km44",
      "схема ax_km44 (2031–34): от существующей развязки А-3 км 44 на восток к тракту")
N48 = fillet(axis_line("ax_n48"), 350)
frame("s_n48", "arterial_regulated", N48, "Улица от развязки А-3 км 48", years0("ax_n48"), "ax_n48",
      "схема ax_n48 (2036–40): от новой развязки А-3 км ≈ 48 на восток к Восточной магистрали")
N50 = fillet(axis_line("ax_n50"), 350)
frame("s_n50", "arterial_regulated", N50, "Улица от развязки А-3 км 50,5", years0("ax_n50"), "ax_n50",
      "схема ax_n50 (2042–46): от новой развязки А-3 км ≈ 50,5 на восток к Восточной магистрали")
# --- LRT avenue (бульвар Growing): the LRT in the median, from Жанаарна to Каскелен
# the OIZ street runs into the boulevard: one line filleted through the corner at the boulevard's start (run 3: a 54° corner
# there left both divided streets' carriageways unjoined, gen_network joins them only up to 10°), split on the arc
_oiz_raw = axis_line("ax_oiz")[:-1]
_blvd_raw = axis_line("ax_lrt_blvd")[1:]
_ob = fillet(_oiz_raw + _blvd_raw, 400)
_kc = min(range(len(_ob)), key=lambda i: math.dist(_ob[i], _blvd_raw[0]))
BLVD = _ob[_kc:]
frame("s_blvd", "district_transport", BLVD, "Бульвар Growing (ЛРТ в разделительной полосе)", years0("ax_lrt_blvd"),
      "ax_lrt_blvd", "схема ax_lrt_blvd (2031–36): проспект с ЛРТ в широкой разделительной полосе и бульваром вдоль неё",
      profile=dict(LRT_PROFILE))
# --- главная улица OIZ TULIP (the LRT in the median south of Жанаарна)
OIZ = _ob[:_kc + 1]
frame("s_oiz", "district_transport", OIZ, "Главная улица OIZ TULIP (ЛРТ в разделительной полосе)", years0("ax_oiz"), "ax_oiz",
      "схема ax_oiz (2027–30): главная улица индустриального парка, на севере переходит в бульвар Growing; ЛРТ — в её "
      "разделительной полосе", profile=dict(LRT_PROFILE))
CHANGES.append(("s_oiz", "северный конец — в начале бульвара Growing (у станции Жанаарна-вокзал), не в (300, −480): "
                         "улица и ЛРТ идут одной трассой"))
# --- industrial streets
for sid, aid, nm, R in (("s_ind1", "ax_ind1", "Промышленная улица 1", 300), ("s_ind2", "ax_ind2", "Промышленная улица 2", 300),
                        ("s_ind3", "ax_ind3", "Промышленная улица 3", 300)):
    frame(sid, "industrial", fillet(axis_line(aid), R), nm, years0(aid), aid,
          f"схема {aid}: главная улица промпояса (класс industrial — грузовой транспорт к заводам)")
# --- мост Заречное – Каскелен
MOY = fillet(axis_line("ax_moynak"), 300)
frame("s_moynak", "district_transport", MOY, "Мост Заречное – Каскелен", years0("ax_moynak"), "ax_moynak",
      "схема ax_moynak (2042–46): связь Заречного с центром Каскелен, мост через реку Каскелен")
# --- pedestrian streets
frame("s_centre_walk", "pedestrian_street", fillet(axis_line("ax_centre_walk"), 150), "Пешеходная улица Центра",
      years0("ax_centre_walk"), "ax_centre_walk", "схема ax_centre_walk (2033–36): пешеходная ось главного центра")
FRAME_IDS = [s["id"] for s in STREETS if s["_layer"] == "frame"]

# ===================================================================================================== 3. interchanges
EXP = [s for s in STREETS if s["class"] == "expressway"]


def links_near(x, z, r):
    out = []
    for oid, (g, p) in OSM.items():
        if p.get("class") == "motorway" and p.get("sub") == "link" and g.distance(Point(x, z)) < r:
            out.append(oid)
    return out


def exp_near(x, z):
    P = Point(x, z)
    return sorted(EXP, key=lambda s: LineString(s["line"]).distance(P))


def minor_of(ids, x, z, r):
    """The street the existing ramps lead to (most ramp ends within 5 m), else the nearest street within r."""
    from collections import Counter
    cnt = Counter()
    for oid in ids:
        g = OSM[oid][0]
        for q in C.lines_of(g) or [g]:
            for e in (q.coords[0], q.coords[-1]):
                for st in STREETS:
                    if st["class"] not in ("expressway", "ramp") and LineString(st["line"]).distance(Point(e)) < 5.0:
                        cnt[st["id"]] += 1
    if cnt:
        return cnt.most_common(1)[0][0]
    cand = [(LineString(st["line"]).distance(Point(x, z)), st["id"]) for st in STREETS if st["class"] not in ("expressway", "ramp")]
    cand = [c for c in cand if c[0] < r]
    return min(cand)[1] if cand else None


def ic_existing(nid, x, z, typ, minor, rid, why, r=600.0):
    ids = links_near(x, z, r)
    if minor is None:
        minor = minor_of(ids, x, z, r)
    e = exp_near(x, z)
    streets = [e[0]["id"]] + ([minor] if minor else [])
    node(nid, x, z, typ, streets, keep_existing=True, registry_id=rid, osm_ids=ids, radius_m=r, why_ru=why)
    return ids


ic_existing("ic_a3_km42", -561.0, 162.0, "diamond", "s_south", "interchange_a3_km42_4",
            "существующая развязка А-3 км ≈ 42,4 (OSM), съезды как в данных; к ней приходит Южная магистраль", r=450.0)
ic_existing("ic_a3_km44", -280.0, 1700.0, "diamond", "s_km44", None,
            "существующая развязка А-3 км ≈ 44 (OSM, съезды c5dc1f4a, 71dada4c); к ней приходит улица км 44", r=350.0)
ic_existing("ic_a3_km46", 130.0, 3883.0, "diamond", "s_central", "interchange_a3_km46_1",
            "существующая развязка А-3 км ≈ 46,1 (OSM), съезды как в данных; к ней приходит Центральная магистраль", r=450.0)
ic_existing("ic_a3_km55", 360.0, 13800.0, "diamond", None, None,
            "существующая развязка А-3 у Заречного (OSM), съезды как в данных", r=500.0)
# new interchanges km ≈ 48 and ≈ 50,5 (scheme ax_n48 / ax_n50): the A-3 is the border, its southbound carriageway lies on it
# and the northbound one 14 m inside Growing-East, so only the east half of a diamond is here: an exit from the northbound
# carriageway to the street and an entry from the street onto it (hand ramps, «модель qTwin»: speed-change lanes 170–210 m
# alongside the carriageway, merge angle < 2°, radius ≥ 60 m, terminal 150 m east of the A-3 as a 4-arm crossing); the
# street passes over both carriageways (grade_separation); the west half is Growing-West's (spec_issues: J147, J146).
RAMP_R = 60.0
TERM_M = 220.0                    # the terminal off the A-3: past the street's ramp down from its overpass (was 150 m: on the deck)


def _off(L, s_, d):
    """Point at chainage s_ of L, offset d metres to the right of its direction (east of a northbound carriageway)."""
    a, b = L.interpolate(max(s_ - 2.0, 0.0)), L.interpolate(min(s_ + 2.0, L.length))
    t = np.array([b.x - a.x, b.y - a.y])
    t /= np.linalg.norm(t)
    p = L.interpolate(s_)
    return (p.x + t[1] * d, p.y - t[0] * d)


def _dense(L, sc, offs, cut, pts_, head, step=10.0):
    """The part of a ramp alongside the carriageway L re-drawn every `step` m at the offsets `offs` [(chainage from sc, m)]
    (linear between them); the filleted rest of the ramp is kept beyond chainage sc + cut. The ramp's own end stands 0.15 m
    off the carriageway on the ramp's side (gen_network ties an end within 0.3 m of a way to it): an end exactly on the line
    is rounded to 0.1 m and may fall on the far side, and its first leg then crosses the carriageway (km 50, run 3)."""
    ss = [sc + a_ for a_, _ in offs]
    ds = [d for _, d in offs]
    lo, hi = min(ss), max(ss)
    if head:
        vs = list(np.arange(lo, sc + cut, step))
        return [_off(L, v, float(np.interp(v, ss, ds))) for v in vs] + [p for p in pts_ if L.project(Point(p)) > sc + cut]
    vs = list(np.arange(sc + cut, hi, step)) + [hi]
    return [p for p in pts_ if L.project(Point(p)) < sc + cut] + [_off(L, v, float(np.interp(v, ss, ds))) for v in vs]


def half_diamond(nid, sid, J, nb_id, sb_id, yr, kmname):
    Ls = LineString(SID[sid]["line"])
    Lnb = LineString(SID[nb_id]["line"])
    X = Lnb.intersection(Ls)
    if X.is_empty:
        raise SystemExit(f"{nid}: {sid} не пересекает {nb_id}")
    X = X if X.geom_type == "Point" else X.geoms[0]
    sc = Lnb.project(X)
    s_t = Ls.project(X) + TERM_M
    T_ = Ls.interpolate(s_t)
    # the street is divided (gen_network draws its carriageways cw_offset off the axis): each ramp ends on the carriageway on
    # its own side — the exit, coming from the south, on the southern one; the entry, leaving to the north, on the northern
    # one. Ending on the axis they crossed the near carriageway, the crossing came out separated and the street passed over
    # both ramps, which met only each other (owner 03.11.2026); a joint node at each end ties it to its carriageway
    _pr = LU.profile_from_norms(_LN, SID[sid]["class"])
    e_cw = _pr.get("median_w", 0.0) / 2.0 + _pr["lanes"][0] * _pr["lane_w"] / 2.0 if len(_pr["lanes"]) == 2 and _pr.get("median_w", 0.0) > 0 else 0.0
    _a, _b = Ls.interpolate(s_t - 5.0), Ls.interpolate(s_t + 5.0)
    _d = np.array([_b.x - _a.x, _b.y - _a.y]); _d /= max(np.linalg.norm(_d), 1e-9)
    _cw = [(T_.x + _d[1] * e_cw * k, T_.y - _d[0] * e_cw * k) for k in (1.0, -1.0)]
    T_ex, T_en = min(_cw, key=lambda q: q[1]), max(_cw, key=lambda q: q[1])
    ex = fillet([_off(Lnb, sc - 430, 0.0), _off(Lnb, sc - 370, 1.2), _off(Lnb, sc - 310, 3.2), _off(Lnb, sc - 255, 5.6),
                 _off(Lnb, sc - 150, 30.0), (T_ex[0], T_ex[1] - 70.0), T_ex], RAMP_R)
    en = fillet([T_en, (T_en[0], T_en[1] + 70.0), _off(Lnb, sc + 150, 30.0), _off(Lnb, sc + 255, 5.6), _off(Lnb, sc + 330, 3.2),
                 _off(Lnb, sc + 400, 1.2), _off(Lnb, sc + 465, 0.0)], RAMP_R)
    # the speed-change lane follows the carriageway every 10 m (a 60 m chord on a curved carriageway crossed it 1 m after the
    # ramp's start at km 50, run 3: the lane was cut there, rule 7 «1 м из 100 м»); the ramp ends exactly on its line
    ex = _dense(Lnb, sc, [(-430, 0.15), (-420, 0.6), (-370, 1.6), (-310, 3.4), (-255, 5.6)], -285, ex, head=True)
    en = _dense(Lnb, sc, [(255, 5.6), (310, 3.4), (370, 1.6), (455, 0.6), (465, 0.15)], 285, en, head=False)
    ids = []
    for rid_, pts_, nm in ((f"r_{nid}_exit", ex, f"съезд с А-3 (на север) на улицу {kmname}"),
                           (f"r_{nid}_entry", en, f"въезд с улицы {kmname} на А-3 (на север)")):
        hh = houses_hit(LineString(pts_).buffer(6.0))
        if hh or not DIST.contains(LineString(pts_)):
            CHANGES.append((rid_, f"ручной съезд не построен: {'дома' if hh else 'выходит за границу'}"))
            continue
        street(rid_, "ramp", pts_, nm, yr, oneway=True, struct=structs(pts_), layer="ramp",
               why=MODEL + f": восточная половина ромба {nid} — ручной съезд (переходно-скоростная полоса вдоль северной проезжей "
                           f"части {nb_id}, радиус ≥ {RAMP_R:.0f} м, примыкание к {sid} в {TERM_M:.0f} м от А-3)")
        ids.append(rid_)
        _te = T_ex if rid_.endswith("_exit") else T_en
        node(f"{rid_}_t", _te[0], _te[1], "joint", [rid_, sid],
             why_ru=f"съезд примыкает к проезжей части {sid} на своей стороне (в {e_cw:.1f} м от оси улицы), в одном уровне")
    node(nid, J[0], J[1], "grade_separation", [nb_id, sid], major=nb_id, major_pair=sb_id, hand_ramps=ids,
         why_ru=f"новая развязка А-3 {kmname} по схеме: улица проходит над обеими проезжими частями, съезды восточной стороны "
                f"(северная проезжая часть {nb_id} — в районе) ручные: {', '.join(ids)}; западная половина (съезды с южной проезжей "
                f"части по границе) — у Growing-запад (стык {'J147' if sid == 's_n48' else 'J146'}, spec_issues)")
    CHANGES.append((nid, "ромб схемы → путепровод + восточная половина ромба ручными съездами: шаблон diamond требует обе "
                         "проезжие части и улицу по обе стороны А-3 в районе, а южная проезжая часть лежит на границе"))
    return ids


HALF_IC = {}
for nid, sid, J, nb_id, km in (("ic_a3_km48", "s_n48", (291.3, 6020.1), "k_ff5e5368", "км 48"),
                               ("ic_a3_km50", "s_n50", (327.6, 8180.0), "k_e299582d", "км 50,5")):
    HALF_IC[nid] = half_diamond(nid, sid, J, nb_id, "k_847914aa", years0("ax_n48" if sid == "s_n48" else "ax_n50"), km)


# ===================================================================================================== 4. local streets
NO_HOST = {"expressway", "ramp", "pedestrian_street", "bike_path", "boulevard", "driveway_main", "driveway_secondary"}
D_IN = 10.0                     # edge streets run 10 m inside the quarter's border (local red line 15 m: half 7.5 + 2.5)
EXP_HALF = 45.0                 # expressways: half red line 25 + 20 m (no quarter edge right at the carriageway)


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
    u = np.array([math.sin(t), math.cos(t)])
    v = np.array([math.cos(t), -math.sin(t)])
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


def _ray_hit_tree(p, dvec, lines, tree, reach):
    seg = LineString([p, (p[0] + dvec[0] * reach, p[1] + dvec[1] * reach)])
    return _ray_hit(p, dvec, [lines[i] for i in tree.query(seg)], reach)


GEN_LOG = []
STATIONS_AT = []                 # [(x, z)] LRT stations: no local street crosses the line within ±STATION_GAP of them
STATION_GAP = 75.0
UNSERVED = []                    # [Polygon] island quarters no street can reach: the builder turns them into reserve
LRT_RAMPS = []                   # [Polygon] where the LRT climbs or descends: no local street crosses
BARRIERS = []                    # [geometry] land no local street crosses (LRT own right of way, rail)


def generate_local(stations=(), barriers=None, lrt_line=None):
    """Edge streets and grids of every new quarter (pieces of the development zones between streets, water and villages)."""
    STATIONS_AT[:] = list(stations)
    lines = all_lines()
    host = [(sid, L, cls, half) for sid, L, cls, half in lines if cls not in NO_HOST]
    corr = corridors(lines)
    if barriers is not None:
        corr = corr.union(barriers)
    region = DEV_IN.difference(corr).difference(WATER_STRIP).difference(RAIL.buffer(25.0)).intersection(DIST.buffer(-5))
    pieces = [p for p in getattr(region, "geoms", [region]) if p.area > 15000.0]
    pieces.sort(key=lambda p: (-p.centroid.y, p.centroid.x))
    made = 0
    later = []
    ztree = shapely.STRtree([z["poly"] for z in Z.ZPLAN])
    for k, piece in enumerate(pieces):
        zs = sorted(((Z.ZPLAN[int(i)]["poly"].intersection(piece).area, Z.ZPLAN[int(i)]) for i in ztree.query(piece)
                     if Z.ZPLAN[int(i)]["use"] in Z.GRID), key=lambda t: -t[0])
        if not zs or zs[0][0] < 1000:
            continue
        zone = zs[0][1]
        S1, S2 = Z.GRID[zone["use"]]
        host_tree = shapely.STRtree([L for _, L, _, _ in host])
        near = [host[i][1] for i in host_tree.query(piece.buffer(60))]
        theta = _dir_deg([L.intersection(piece.buffer(60)) for L in near if not L.intersection(piece.buffer(60)).is_empty])
        if theta is None:
            mrr = piece.minimum_rotated_rectangle
            c = np.asarray(mrr.exterior.coords)
            v = c[1] - c[0]
            theta = math.degrees(math.atan2(v[0], v[1])) % 90.0
        tag = f"p{k + 1:03d}"
        defer = []
        made += _piece(tag, piece, zone, zs, theta, S1, S2, host, lrt_line, defer=defer)
        if defer:
            later.append((tag, piece, zone, zs, theta, S1, S2, defer))
        # streets of this piece become hosts of the next ones (a quarter edge on the neighbour's edge street is fronted)
        host = [(sid, L, cls, half) for sid, L, cls, half in all_lines() if cls not in NO_HOST]
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


def _barrier_hit(LL):
    return any(LL.crosses(b) or LL.within(b) for b in BARRIERS)


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
        pts_ = [ring.interpolate(Lr * i / m) for i in range(m)]
        fr = [_fronted((q.x, q.y), host, host_tree) for q in pts_]
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
                if any(conn.intersects(X) for X in barrier) or houses_hit(conn.buffer(7.5)) or _barrier_hit(conn):
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
                   struct=structs([(a.x, a.y), (b.x, b.y)]),
                   why=MODEL + ": квартал окружён сёлами, парками или водой — кольцевая улица и выезд к ближайшей улице")
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
                line = [(pts_[i].x, pts_[i].y) for i in seq]
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
                    GEN_LOG.append({"what": "краевая улица обходит дома", "piece": tag, "n": len(hh)})
                else:
                    cut = LL.difference(unary_union([b.buffer(HOUSE_GAP) for b in hh]))
                    runs_ = [q for q in C.lines_of(cut) if q.length >= 30.0]
                    GEN_LOG.append({"what": "краевая улица задевает дома: разрезана у домов", "piece": tag, "n": len(hh)})
            for pi, q in enumerate(runs_):
                if lrt_line is not None and q.intersects(lrt_line) and (any(q.intersects(r) for r in LRT_RAMPS) or _barrier_hit(q)):
                    GEN_LOG.append({"what": "краевая улица пересекала рампу или свой коридор ЛРТ: не строится", "piece": tag})
                    continue
                if RAIL.intersects(q):
                    GEN_LOG.append({"what": "краевая улица пересекала ж/д: не строится", "piece": tag})
                    continue
                street(f"e_{tag}_{j}_{i}" + (f"_{pi}" if pi else ""), cls_local, q.coords, "улица по краю квартала", yb,
                       layer="edge", why=why, struct=structs(list(q.coords)))
                n += 1
        # grid
        u, v = _rot(theta)
        c = np.asarray(P.centroid.coords[0])
        R = max(P.bounds[2] - P.bounds[0], P.bounds[3] - P.bounds[1]) * 0.8 + 50
        edge_now = [LineString(s["line"]) for s in STREETS if s["id"].startswith(f"e_{tag}_{j}_")]
        guide = unary_union([ring] + edge_now)
        grid_hosts = host_lines + edge_now
        gtree = shapely.STRtree(grid_hosts)
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
                        hit = _ray_hit_tree(e, d_out, grid_hosts, gtree, D_IN + 45.0)
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
                            GEN_LOG.append({"what": "линия сетки задевает дом: снята", "piece": tag})
                            continue
                        LL = dt
                    if RAIL.intersects(LL):
                        continue
                    if lrt_line is not None and LL.intersects(lrt_line):
                        xpt = LL.intersection(lrt_line)
                        xpt = xpt if xpt.geom_type == "Point" else xpt.centroid
                        if any(math.dist((xpt.x, xpt.y), st) < STATION_GAP for st in STATIONS_AT):
                            continue
                        if any(r.contains(xpt) for r in LRT_RAMPS) or _barrier_hit(LL):
                            continue
                    street(f"g_{tag}_{j}_{fam}{kk - k0:02d}" + (f"_{qi}" if qi else ""), cls_local, LL.coords, "улица квартала", yb,
                           layer="grid", why=MODEL + f": сетка квартала зоны {zone['id']} (шаг {S:.0f} м)",
                           struct=structs(list(LL.coords)))
                    n += 1
    return n


# ===================================================================================================== 5. post-pass
GEN = ("edge", "grid")
NO_JUNCTION = {"expressway", "ramp"}


class Index:
    """All lines of the network (spec streets + OSM roads that stay) with one STRtree, rebuilt on demand."""

    def __init__(self):
        self.items = [(s["id"], LineString(s["line"]), s["class"]) for s in STREETS]
        self.items += [("osm:" + oid, q, cls) for oid, q, cls in OSM_HOST]
        self.tree = shapely.STRtree([L for _, L, _ in self.items])

    def near(self, geom, skip=None):
        return [self.items[int(i)] for i in self.tree.query(geom) if self.items[int(i)][0] != skip]


def _attached_ix(pt, ix, sid, extra_ok):
    P = Point(pt)
    for oid, L, cls in ix.near(P.buffer(0.6), skip=sid):
        if cls in NO_JUNCTION:
            continue
        if L.distance(P) < 0.5:
            return True
    return extra_ok(P)


def _cut_points_ix(L, ix, s):
    spans = []
    for st in s.get("struct") or []:
        a, b = L.project(Point(st["from"])), L.project(Point(st["to"]))
        spans.append((min(a, b), max(a, b)))
    ch = []
    for sid, M, cls in ix.near(L.buffer(0.6), skip=s.get("id")):
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
        ix = Index()
        drop = []
        for k, s in enumerate(STREETS):
            if s["_layer"] not in layers:
                continue
            L = LineString(s["line"])
            f0 = not _attached_ix(s["line"][0], ix, s["id"], extra_ok)
            f1 = not _attached_ix(s["line"][-1], ix, s["id"], extra_ok)
            if not (f0 or f1):
                continue
            ch = [c for c in _cut_points_ix(L, ix, s) if 0.5 < c < L.length - 0.5]
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
    """Generated street ends on a street a few metres from another street's end on that same street: moved onto that end
    (one junction, not two crossings a few metres apart)."""
    moved = 0
    ix = Index()
    ends = []
    for sid, q, cls in ix.items:
        ends += [(sid, Point(q.coords[0])), (sid, Point(q.coords[-1]))]
    etree = shapely.STRtree([p for _, p in ends])
    for s in STREETS:
        if s["_layer"] not in layers:
            continue
        for e in (0, -1):
            P = Point(s["line"][e])
            on_ = [L for sid, L, cls in ix.near(P.buffer(0.6), skip=s["id"]) if cls not in NO_JUNCTION and L.distance(P) < 0.5]
            if not on_:
                continue
            near = sorted((ends[int(i)][1].distance(P), ends[int(i)][1]) for i in etree.query(P.buffer(tol))
                          if ends[int(i)][0] != s["id"])
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
                                    "id": s["id"], "m": round(d, 1)})
                    break
    return moved


LANE_REACH = 25.0      # m: a house is served when a street is this close (rule 12, fire_access.max_distance_to_building_m)
LANE_MAX = 150.0       # m: dead-end limit of a lane (fire_access.dead_end_max_m)
LINK_MAX = 150.0
LINK_MIN = 15.0
DEAD_END_OK = {"driveway_main", "driveway_secondary", "local", "local_secondary", "village_lane", "industrial"}


def house_lanes(log=None):
    """Existing houses outside the villages and outside the new quarters (farms in parks, reserves and corridors) with no
    street within LANE_REACH: a village lane from the nearest street toward the group, its red line ending 1.5 m short of
    the house (≤ LANE_MAX, never through a house, never across an expressway, a ramp, water or the tracks)."""
    hs = [h for h in HOUSES if DIST.contains(h.centroid) and not VILL.contains(h.centroid)
          and not DEV.buffer(-5.0).contains(h.centroid)]
    lines = [(s["id"], LineString(s["line"])) for s in STREETS if s["class"] not in ("expressway", "ramp", "pedestrian_street", "bike_path")]
    lines += [("osm:" + oid, q) for oid, q, cls in OSM_HOST]
    lt = shapely.STRtree([q for _, q in lines])
    barrier = unary_union([LineString(s["line"]) for s in STREETS if s["class"] in ("expressway", "ramp")])
    far = [h for h in hs if lines[int(lt.query_nearest(h)[0])][1].distance(h) > LANE_REACH]
    if not far:
        return 0
    grp = unary_union([h.buffer(20.0) for h in far])
    made = 0
    for G_ in getattr(grp, "geoms", [grp]):
        mine = [h for h in far if G_.contains(h.centroid)]
        if not mine:
            continue
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
        end = LineString([a, b]).interpolate(max(d - rh - 1.5, 0.0))
        lane = LineString([(a.x, a.y), (end.x, end.y)])
        if lane.length < LINK_MIN - 0.5 or houses_hit(lane.buffer(rh + 1.0)) or lane.crosses(barrier) \
                or lane.intersects(WATER_POLY) or lane.intersects(RAIL):
            if log is not None:
                log.append({"what": "дом вне села: проулок к нему пересёк бы дом, трассу, воду или ж/д — не строится", **rec})
            continue
        made += 1
        street(f"v_lane_{made:03d}", "village_lane", lane.coords, "проезд к существующему дому", 2026, layer="lane",
               why=MODEL + f": существующий дом вне села без улицы в {LANE_REACH:.0f} м — проулок от {sid} (≤ {LANE_MAX:.0f} м, "
                           "тупик класса village_lane)")
        if log is not None:
            log.append({"what": "проулок к существующему дому вне села", "id": f"v_lane_{made:03d}", **rec})
    return made


def link_dead_ends(log=None):
    """Existing roads that end in nothing inside the district: a straight through link from the dead end to the nearest
    other street (≤ LINK_MAX), never through a house, never across an expressway, a ramp, water or the tracks."""
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
            if DIST.exterior.distance(E) < 3.0:
                continue
            if any(j != i and lines[j][1].distance(E) < 0.5 for j in tree.query(E.buffer(0.6))) \
                    or any(k.distance(E) < 0.5 for k in links):
                continue
            # a short dead end of a class that may end (rule 5: ≤ 150 m) stays
            near_c = []
            for j in tree.query(L.buffer(0.6)):
                if j == i:
                    continue
                x = L.intersection(lines[j][1].buffer(0.3))
                for q in getattr(x, "geoms", [x]):
                    if not q.is_empty:
                        near_c.append(L.project(q.centroid))
            s_e = 0.0 if e == 0 else L.length
            branch = min((abs(c - s_e) for c in near_c if abs(c - s_e) > 0.5), default=L.length)
            if cls in DEAD_END_OK | {"village_secondary", "village_main"} and branch <= LINK_MAX:
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
                if any(lines[j][1].intersects(inner) for j in tree.query(inner)) or any(M.intersects(inner) for M in links):
                    continue
                near = [lines[j][1] for j in tree.query(inner.buffer(3.0)) if lines[j][0] != host] + links
                if any(inner.intersection(M.buffer(3.0)).length > 3.0 for M in near):
                    continue
                lcls = "village_lane" if VILL.contains(link.centroid) else "local"
                if houses_hit(link.buffer(red_w(lcls) / 2.0)) or link.crosses(barrier) or link.intersects(WATER_POLY) \
                        or link.intersects(RAIL) or not DIST.contains(link):
                    continue
                made += 1
                links.append(link)
                street(f"v_link_{made:03d}", lcls, link.coords, "сквозной проезд из тупика", 2026, layer="link",
                       struct=structs(list(link.coords)),       # over a stream or along a bank: a bridge (run 5, rule 4)
                       why=MODEL + f": тупик существующей улицы {sid} длиннее нормы — сквозной проезд {d:.0f} м к {host} "
                                   "(между домами, не через дом)")
                if log is not None:
                    log.append({"what": "тупик существующей улицы: сквозной проезд", "id": f"v_link_{made:03d}", "from": sid,
                                "to": host, "m": round(d)})
                done = True
                break
            if not done:
                kept += 1
                if log is not None:
                    log.append({"what": "тупик существующей улицы: проезда без сноса дома нет — как в OSM", "id": sid,
                                "at": [round(E.x), round(E.y)]})
    return made, kept


SNAP_J = 6.0
GRADE_SEP_TYPES = {"grade_separation", "diamond", "partial_cloverleaf", "cloverleaf", "trumpet", "directional"}


def phase_years(use="road", log=None):
    """Opening years by pieces of street between junctions, so that no street ends blind in any year (push): a piece of a
    new street opens no earlier than some street at each of its ends; a street with pieces of different years is split into
    runs (the first run keeps the id). Existing roads are 2025 and end blind as OSM has them."""
    lines = [(s["id"], LineString(s["line"]), s["class"], s) for s in STREETS]
    lines += [("osm:" + oid, q, cls, None) for oid, q, cls in OSM_HOST]
    tree = shapely.STRtree([L for _, L, _, _ in lines])
    gsep = [Point(n["x"], n["z"]) for n in NODES.values() if n["type"] in GRADE_SEP_TYPES]
    gtree = shapely.STRtree(gsep) if gsep else None
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
                if in_span(sid, q) or in_span(sid2, q) or (gtree is not None and len(gtree.query(q.buffer(25.0)))):
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
    pts_ = []
    for sid, a, b in pieces:
        L = LID[sid][0]
        pts_.append(L.interpolate(a))
        pts_.append(L.interpolate(b))
    ptree = shapely.STRtree(pts_)
    parent = list(range(len(pts_)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, P in enumerate(pts_):
        for j in ptree.query(P.buffer(SNAP_J)):
            if j != i and P.distance(pts_[j]) < SNAP_J:
                ri, rj = find(i), find(int(j))
                if ri != rj:
                    parent[ri] = rj
    node_of = [find(i) for i in range(len(pts_))]
    at = {}
    for i, n in enumerate(node_of):
        at.setdefault(n, []).append(i // 2)
    joints = [Point(n["x"], n["z"]) for n in NODES.values() if n["type"] == "joint"]
    edge = {n for n in at if DIST.exterior.distance(pts_[n]) < 3.0 or any(pts_[n].distance(j) < 3.0 for j in joints)}
    grp, year, fixed = [], {}, set()
    for k, (sid, a, b) in enumerate(pieces):
        L, cls, s = LID[sid]
        g = sid if s is None else (sid, k)
        grp.append(g)
        year[g] = 2025 if s is None else int(s["years"][0])
        if s is None or s.get("_layer") == "osm":
            fixed.add(g)

    def others(k, n):
        return [q for q in at[n] if q != k]
    for _ in range(400):
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
                    moved = True
        if not moved:
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
    print(f"loaded in {time.time() - T0:.1f} s; houses {len(HOUSES)}; retired {len(RETIRED)}; osm hosts {len(OSM_HOST)}")
    summary()
    print(CHANGES)
