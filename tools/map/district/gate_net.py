#!/usr/bin/env python3
"""Gate · level 2 · street network of the whole district (w47), imported by gate_build.py.

    python3 -I tools/map/district/gate_net.py [--png PATH] [--zoom x0 x1 z0 z1]     # build in memory, print, draw

The network is made of four layers:
  1. the trial quarter (level 1, gate_trial_build.py, built in memory): its streets, nodes and interchanges as they are,
     with the few streets that ended at the trial edge carried on into the rest of Gate;
  2. existing roads (Overture/OSM): expressways, ramps and interchanges, the village streets and the tertiary roads stay
     as they are (gen_network takes them from OSM); other existing roads inside new quarters are replaced (replaced_osm);
  3. the frame of new streets by the level-0 scheme axes (ax_west, ax_dubler_n, ax_esentai, ax_tpu, ax_gatecity …);
  4. local streets of every new quarter, generated here (the generator's grid is off for v1 specs): an edge street along
     every side of the quarter that has no street (village, park, stream, expressway, district edge) and a grid at the
     zone's block size, aligned with the frame, every end on a street.
Every coordinate not from a source is the cartographer's design (label «модель qTwin»). Unity frame: X east, Z north.
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

import gate_common as C  # noqa: E402
import gate_trial_build as T  # noqa: E402
import land_util as LU  # noqa: E402

MODEL = "модель qTwin"
Y4 = T.Y4
fillet = T.fillet
CITY = T.CITY
V0 = C.spec_v0()
GATE = T.GATE_POLY
TRIAL = T.AREA
V0Z = {z["id"]: z for z in V0["zones"]}

_LN = LU.Norms()
_RW = {}


def red_w(cls, profile=None):
    if cls not in _RW:
        _RW[cls] = float(LU.profile_from_norms(_LN, cls)["red_line_w"])
    w = _RW[cls]
    g = float((profile or {}).get("green_w") or 0.0)
    return max(w, g + 6.0) if g else w


# ===================================================================================================== open data
OSM = {p["id"]: (g, p) for g, p in C.layer_in("roads", GATE)}
SH = {k[:8]: k for k in OSM}


def osm(short):
    return OSM[SH[short]]


VILL = unary_union([Polygon(z["polygon"]).buffer(0) for z in V0["zones"] if z["use"] == "village_existing"])
_W = C.layer_in("water", GATE.buffer(200))
WATER_POLY = unary_union([g for g, p in _W if g.geom_type in ("Polygon", "MultiPolygon") and p.get("class") != "swimming_pool"])
WATER_LINE = unary_union([g for g, p in _W if g.geom_type in ("LineString", "MultiLineString")])
STRIP = 35.0                                       # flood.water_protection_strip_min_m
WATER_STRIP = unary_union([WATER_POLY.buffer(STRIP), WATER_LINE.buffer(STRIP)])

from gen_blocks_lots import existing_houses  # noqa: E402

HOUSES = [h["fp"] for h in existing_houses(GATE.buffer(80), Polygon())]
HTREE = shapely.STRtree(HOUSES)


def houses_hit(geom):
    return [HOUSES[i] for i in HTREE.query(geom, predicate="intersects")]


# ===================================================================================================== registries
STREETS, NODES = [], {}
SID = {}


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


def on(line, z=None, x=None):
    L = line if isinstance(line, LineString) else LineString(line)
    if z is not None:
        g = LineString([(-1e5, z), (1e5, z)]).intersection(L)
    else:
        g = LineString([(x, -1e6), (x, 1e6)]).intersection(L)
    pts = [g] if g.geom_type == "Point" else [q for q in getattr(g, "geoms", []) if q.geom_type == "Point"]
    if not pts:
        raise ValueError(f"no point at z={z} x={x}")
    p = pts[0]
    return (round(p.x, 1), round(p.y, 1))


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


# ===================================================================================================== 1. the trial quarter
TRIAL_SAME, TRIAL_CHANGED = [], {}
SCHEME_CHANGES = []              # frame changes against the level-0 scheme: (id, why)
_drop_nodes = {"n_ave_w_end"}
for s in T.STREETS:
    if s["source"] != "new":
        continue                                   # keep_existing pieces are rebuilt below over the whole district
    d = copy.deepcopy(s)
    d["_layer"] = "trial"
    STREETS.append(d)
    SID[d["id"]] = d
    TRIAL_SAME.append(d["id"])
for n in T.NODES.values():
    if n["id"].startswith(("k_n", "v_n", "v_end", "ej")) or n["id"] in _drop_nodes:
        continue
    NODES[n["id"]] = copy.deepcopy(n)
    p = NODES[n["id"]]["params"]
    p.pop("edge_joint", None)
    if p.get("note_ru") == "узел на краю area":
        p.pop("note_ru")


def change(sid, why):
    TRIAL_CHANGED[sid] = why
    if sid in TRIAL_SAME:
        TRIAL_SAME.remove(sid)


AVE_X, EAST_X, DUB_X = T.AVE_X, T.EAST_X, T.DUB_X
Z_NORTH, Z_PARK, Z_AVE = T.Z_NORTH, T.Z_PARK, T.Z_AVE

# --- Западный проспект: on to the north along the scheme axis ax_west (east of the Жанадаур stream), ends at the embankment
Z_EMB = -16500.0                                   # Набережная Есентай (scheme: border of the waterfront zones)
X_WN = -3300.0                                     # Западный проспект north of Есентай street
A_N = (AVE_X, -18754.0)
d40 = 760.0
P40 = (AVE_X + d40 * math.sin(math.radians(40)), -18754.0 + d40 * math.cos(math.radians(40)))
ave_full = fillet([(AVE_X, -20230.0), T.T_S, T.IC_W, T.T_N, (AVE_X, Z_AVE), (AVE_X, -19334.0), (AVE_X, Z_PARK), A_N, P40,
                   (X_WN, -17650.0), (X_WN, Z_EMB)], 400)
old = SID["s_west_ave"]
new_line = [tuple(old["line"][0])] + [p for p in ave_full if p[1] > T.T_S[1] + 1]
k0 = len(old["line"])
assert max(math.dist(a, b) for a, b in zip(old["line"][:-1], new_line[:k0 - 1])) < 0.2, "trial part of the avenue moved"
assert LineString(new_line).distance(Point(old["line"][-1])) < 0.2
new_line = new_line[:k0 - 1] + [tuple(old["line"][-1])] + [p for p in new_line[k0 - 1:] if p[1] > old["line"][-1][1] + 1]
old["line"] = [[round(x, 1), round(z, 1)] for x, z in new_line]
old["struct"] += [{"from": [round(a[0], 1), round(a[1], 1)], "to": [round(b[0], 1), round(b[1], 1)], "kind": k}
                  for a, b, k in water_bridges(new_line[k0 - 1:])]
change("s_west_ave", "продолжен на север по оси схемы ax_west (у восточного края Жанадаура, восточнее ручья) до Набережной Есентай; "
                     "часть в пробной зоне без изменений")

# --- дублёр А-3: on to the north (scheme ax_dubler_n), x −2340 past the A-3 × A-19 interchange loop, then x −2240
X_DUB_N = -2240.0
d = SID["s_dubler"]
dub_n = fillet([(DUB_X, -19100.0), (DUB_X, Z_PARK), (DUB_X, Z_NORTH), (DUB_X, -18495.0), (DUB_X, -18000.0),
                (X_DUB_N, -17750.0), (X_DUB_N, Z_EMB)], 250)
assert math.dist(d["line"][-1], (DUB_X, -18495.0)) < 0.2
d["line"] = d["line"][:-1] + [[round(x, 1), round(z, 1)] for x, z in dub_n if z >= -18495.0 - 0.01]
change("s_dubler", "продолжен на север по оси схемы ax_dubler_n до Набережной Есентай (x −2340, у петли развязки А-3 × А-19 "
                   "держится в 110 м от неё, севернее — x −2240)")

# --- Северная улица ends at the дублёр (the 40 m piece east of it ran to the trial edge)
d = SID["s_north"]
assert tuple(d["line"][-1]) == (-2300.0, Z_NORTH)
d["line"] = d["line"][:-1]
change("s_north", "кончается на дублёре: отрезок 40 м восточнее вёл к краю пробной зоны; развязки на А-3 × А-19 для улицы нет "
                  "(узел А-3 × А-19 — система скоростных дорог, съездов к Gate не имеет), связь — по дублёру")

# --- Восточная улица (ЛРТ в разделительной полосе): north to the embankment and south to Gate City (scheme ax_tpu / ax_lrt)
EAST_N = fillet([(EAST_X, -18495.0), (EAST_X, -18100.0), (-3060.0, -17600.0), (-2930.0, -17050.0), (-2830.0, -16600.0),
                 (-2805.0, Z_EMB)], 500)
street("s_east_n", "district_transport", EAST_N, "Восточная улица (север, ЛРТ в разделительной полосе)", 2031, axis="ax_tpu",
       profile=dict(T.EAST_PROFILE), struct=water_bridges(EAST_N),
       why="продолжение Восточной улицы с ЛРТ на север (ось ЛРТ схемы: Есентай, Бестерек) до Набережной Есентай; вместе с ЛРТ (2031)")
change("s_east", "северный конец (z −18495, край пробной зоны) продолжен улицей s_east_n")
# the first 30 m go straight on along the trial's s_east_s (a kink at the joint of two divided streets leaves their
# carriageway ends apart)
# south of Ынтымақ it crosses the 220 kV corridor of 92ca2130 / 74b9e818 (zones u_hv_south_*) once, at ~26°, and runs on
# ≥ 45 m off the south-east line (protection zone 25 m + half the red line), not along the lines inside their zone
EAST_S = fillet([(-2952.0, -20690.0), (-2951.0, -20720.0), (-2955.0, -21000.0), (-3020.0, -21600.0), (-3070.0, -21850.0),
                 (-3150.0, -22130.0), (-3520.0, -22560.0), (-3700.0, -22850.0), (-3920.0, -23210.0)], 300)
change("s_east_s", "южный конец (край пробной зоны) продолжен улицей s_east_y к Ынтымаку и Gate City")
# the TPU opens with its station (registry agglo_rail_station_1, ГП727: 2030): the TPU ring and its access street open in 2030
for _sid in ("s_tpu1", "s_east_s"):
    if int(SID[_sid]["years"][0]) > 2030:
        _was = SID[_sid]["years"][0]
        SID[_sid]["years"] = Y4(2030)
        change(_sid, (TRIAL_CHANGED.get(_sid, "") + "; " if TRIAL_CHANGED.get(_sid) else "") +
               f"открывается в 2030 вместе со станцией ТПУ (реестр agglo_rail_station_1, ГП727: 2030), а не в {_was}")

# --- Проспект Ворот (западный отрезок) and Южный проезд west: trial streets that ended at the trial edge
# (continued below with the generated network; see _join_trial_edges)

# ===================================================================================================== 2. existing roads
MOTOR = {"motorway"}
VILLAGE_OSM = {"residential", "service", "unclassified", "living_street", "unknown"}
KEEP_IDS = {}


def osm_class(p, g):
    c, sub = p.get("class"), p.get("sub")
    if c == "motorway":
        return "ramp" if sub == "link" else "expressway"
    if c in ("tertiary", "secondary", "primary"):
        return "village_main" if g.intersection(VILL).length > 0.5 * g.length else "district_transport"
    return None


def keep_name(p):
    n = p.get("name") or ""
    if n == "ҮАААЖ":
        return "БАКАД (Большая Алматинская кольцевая)"
    if n.startswith("Алматы-Ө") or n.startswith("Алматы-У"):
        return "А-3 Алматы – Өскемен"
    if n.startswith("Алматы - Қорғас"):
        return "А-19 Алматы – Қорғас"
    if p.get("sub") == "link":
        return "съезд развязки"
    return n


for oid, (g, p) in sorted(OSM.items()):
    cls = osm_class(p, g)
    if cls is None:
        continue
    clip = g.intersection(GATE)
    if clip.length < 3.0:
        continue
    sid = ("k_" if cls in ("expressway", "ramp") else "t_") + oid[:8]
    nm = keep_name(p)
    ax = None
    if cls == "expressway":
        ax = "ax_bakad" if "БАКАД" in nm else ("ax_a19" if "А-19" in nm else "ax_a3")
    elif oid[:8] in ("3db410c3", "64650d74", "fd0129ad", "dcf550f8", "a655a321", "557a7322", "4fc53ab4", "68a930f0",
                     "8afcb7f9", "59427eed", "9bb983b3", "a7f81518", "b4e43fb9"):
        ax = "ax_road17"
    parts = [clip] if clip.geom_type == "LineString" else [q for q in clip.geoms if q.geom_type == "LineString"]
    line = max(parts, key=lambda q: q.length).coords
    street(sid, cls, line, nm or ("улица села" if cls == "village_main" else ""), 2025, oneway=cls in ("expressway", "ramp"),
           source="keep_existing:" + oid, axis=ax, years=C.EXISTING, layer="osm",
           why="существующая дорога OSM/Overture, как есть (направление линии = направление движения)" if cls in ("expressway", "ramp")
           else "существующая дорога OSM, как есть")
    KEEP_IDS[oid] = sid
# the trial's village streets keep their ids and classes (level-1 design)
for s in T.STREETS:
    if s["source"].startswith("keep_existing:") and s["id"].startswith("v_"):
        oid = s["source"].split(":", 1)[1]
        if oid in KEEP_IDS or oid not in OSM:
            continue
        g = OSM[oid][0].intersection(GATE)
        parts = [g] if g.geom_type == "LineString" else [q for q in getattr(g, "geoms", []) if q.geom_type == "LineString"]
        if not parts:
            continue
        street(s["id"], s["class"], max(parts, key=lambda q: q.length).coords, s["name_ru"], 2025, source=s["source"],
               years=C.EXISTING, layer="osm", why="существующая улица села (OSM), класс — как в пробной зоне")
        KEEP_IDS[oid] = s["id"]

# hosts: streets a new street may end on (T-junction): everything but expressways, ramps and pedestrian ways
HOST_OSM = {oid for oid, (g, p) in OSM.items() if p.get("class") in VILLAGE_OSM | {"tertiary", "secondary"}}


def osm_line(oid):
    g = OSM[oid][0].intersection(GATE)
    parts = [g] if g.geom_type == "LineString" else [q for q in getattr(g, "geoms", []) if q.geom_type == "LineString"]
    return parts


# ===================================================================================================== 3. frame of new streets
# --- Набережная Есентай (district): along the border of the waterfront zones, from Западный проспект to the дублёр
EMB = [(X_WN, Z_EMB), (-2805.0, Z_EMB), (X_DUB_N, Z_EMB)]
street("s_emb", "district_transport", EMB, "Набережная Есентай", 2036, struct=water_bridges(EMB),
       why="схема: граница набережной Есентай (w_north) и кварталов r_mid_n; связь Западного проспекта, Восточной улицы и дублёра "
           "на севере; мост через ручей")
# --- улица Есентай (scheme ax_esentai): Западный проспект → дублёр → путепровод над А-3 → технопарк
Z_ES = -17300.0
x_a3 = on(osm("afdf7e2c")[0], z=Z_ES)[0]
ES = [(X_WN, Z_ES), on(EAST_N, z=Z_ES), (X_DUB_N, Z_ES), (x_a3 - 60, Z_ES), (x_a3 + 60, Z_ES), (-1700.0, Z_ES)]
street("s_esentai", "district_transport", ES, "улица Есентай", 2036, axis="ax_esentai",
       struct=[((x_a3 - 60, Z_ES), (x_a3 + 60, Z_ES), "overpass")] + water_bridges(ES),
       why="схема ax_esentai (2036–38); продолжена путепроводом над А-3 (узел grade_separation, без съездов) в технопарк за А-3 "
           "(b_ne_2): иначе к нему нет подъезда, кроме съезда прямо на А-3")
node("gs_esentai_a3", x_a3, Z_ES, "grade_separation", ["s_esentai", KEEP_IDS[SH["afdf7e2c"]]], upper="minor",
     why_ru="улица Есентай над А-3 без съездов")
street("s_east_y", "district_transport", EAST_S, "Восточная улица (Ынтымақ – Gate City, ЛРТ в разделительной полосе)", 2033,
       axis="ax_tpu", profile=dict(T.EAST_PROFILE), struct=water_bridges(EAST_S),
       why="схема ax_tpu: от ТПУ вдоль восточного края Ынтымака к Gate City; ЛРТ в разделительной полосе (2033, 2-я очередь ЛРТ)")
# --- Проспект Gate City (scheme ax_gatecity, arterial): around Ынтымақ and Gate City to the A-3 interchange at Gate City
GC_N = on(osm("e7d3ed63")[0], z=-20720.0)        # square on the existing road to the BAKAD bridge (not a 20° fork off 0f6dfc7e)
SCHEME_CHANGES.append(("s_gatecity", "северный конец — на существующей дороге e7d3ed63 к мосту через БАКАД под прямым углом "
                                     "(у схемы ось уходила с дороги 0f6dfc7e развилкой под 20°)"))
GC = fillet([GC_N, (-4760.0, -21100.0), (-4700.0, -22000.0), (-4600.0, -22850.0), (-4300.0, -23250.0), (-3950.0, -23300.0),
             (-3800.0, -23550.0), (-3790.0, -23760.0), (-3700.0, -23915.0), (-3420.0, -23915.0)], 300)
street("s_gatecity", "arterial_regulated", GC, "Проспект Gate City", 2033, axis="ax_gatecity", struct=water_bridges(GC),
       why="схема ax_gatecity (2031–35): от улицы Аль-Фараби у моста через БАКАД между Коянкусом и Ынтымаком на юг, вокруг "
           "админцентра и ЖК Gate City к развязке А-3 у Gate City")

FRAME_IDS = [s["id"] for s in STREETS if s["_layer"] in ("frame", "trial")]

# ===================================================================================================== 4. local streets
import gate_zones as Z  # noqa: E402

KEEP_POLY = T.KEEP_POLY
NO_HOST = {"expressway", "ramp", "pedestrian_street", "bike_path", "boulevard", "driveway_main", "driveway_secondary"}
D_IN = 10.0                     # edge streets run 10 m inside the quarter's border (local red line 15 m: half 7.5 + 2.5)
EXP_HALF = 45.0                 # expressways: half red line 25 + 20 m (no quarter edge right at the carriageway)

# existing roads inside new quarters are replaced by the new streets (tracks are not built anyway)
DEV_IN = Z.DEV.difference(VILL)
RETIRED = []
for oid, (g, p) in OSM.items():
    if p.get("class") in ("motorway", "tertiary", "secondary", "primary") or oid in KEEP_IDS:
        continue
    gi = g.intersection(GATE)
    if gi.length < 1.0:
        continue
    if p.get("class") == "track" and gi.intersects(DEV_IN):
        RETIRED.append(oid)
    elif gi.intersection(DEV_IN.buffer(5)).length > 0.5 * gi.length and not houses_hit(gi.buffer(30.0)):
        RETIRED.append(oid)                      # a road that serves existing houses (ЖК Gate City, farms) stays
RETIRED_SET = set(RETIRED)
# OSM service drives (sub driveway / parking_aisle / alley) would come out of gen_network as driveway_secondary, a class
# CONTRACT §8 does not use: the ones that stay are kept as village lanes (in a village) or local side streets
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
    in_vill = g.intersection(VILL).length > 0.5 * g.length
    cls = {"living_street": "village_secondary"}.get(p["class"], "village_secondary")
    if p["class"] == "service":
        # as the KEEP_IDS block above and gen_network (w43 round 5, net_osm): an existing service road is a village lane in a
        # village and a secondary local street elsewhere (red lines 3 / 15 m), never driveway_main
        cls = "village_lane" if in_vill else "local_secondary"
    elif not in_vill and p["class"] in ("residential", "unclassified", "unknown"):
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


def generate_local(stations=(), barriers=None, lrt_line=None):
    """Edge streets and grids of every new quarter (pieces of the development zones between streets, water and villages).
    stations: LRT stations (no cross street within STATION_GAP); barriers: land kept free (the LRT corridor off the streets)."""
    STATIONS_AT[:] = list(stations)
    lines = all_lines()
    host = [(sid, L, cls, half) for sid, L, cls, half in lines if cls not in NO_HOST]
    corr = corridors(lines)
    if barriers is not None:
        corr = corr.union(barriers)
    region = DEV_IN.difference(corr).difference(WATER_STRIP).difference(KEEP_POLY.buffer(5)).intersection(GATE.buffer(-5))
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
        S1, S2 = Z.GRID[zone["use"]]
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
    # islands with no street within reach of the frame: tied to the nearest street of the whole local network, once it is
    # drawn (a quarter between a stream and an expressway reaches the grid across the stream by a bridge)
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
            # an island between villages, parks and water: one ring street, tied to the nearest street by a connector
            # (never across an expressway or a ramp, never through a house; a stream is bridged)
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
                if any(conn.intersects(X) for X in barrier) or houses_hit(conn.buffer(7.5)):
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
            conn = LineString([a, b])
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
            # free runs of the ring: no street within reach — an edge street along them
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
                # extend both ends onto the street that fronts the ring there; two runs split by one fronted sample share that
                # sample: only the first takes the stub to the street, the second ends on the first (no doubled stub)
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
                    # the street stops short of the house on both sides (the dangling ends are cut back to their last
                    # junction by trim_free_ends), the rest of the edge is still served
                    cut = LL.difference(unary_union([b.buffer(HOUSE_GAP) for b in hh]))
                    runs_ = [q for q in getattr(cut, "geoms", [cut]) if q.geom_type == "LineString" and q.length >= 30.0]
                    GEN_LOG.append({"what": "краевая улица задевает дома: разрезана у домов", "piece": tag, "n": len(hh),
                                    "parts": len(runs_), "at": [round(v) for v in hh[0].centroid.coords[0]]})
            for pi, q in enumerate(runs_):
                if any(q.intersects(r) for r in LRT_RAMPS) and lrt_line is not None and q.intersects(lrt_line):
                    GEN_LOG.append({"what": "краевая улица пересекала рампу ЛРТ: не строится", "piece": tag})
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
            # lines along dvec, spaced S across (nvec); global phase: offsets are multiples of S in the rotated frame
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
                    # parallel and close to the quarter's edge or an edge street: that street already serves the strip
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


# ===================================================================================================== 5. post-pass
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
        tree = shapely.STRtree([L for _, L, _ in others_all])
        drop = []
        for k, s in enumerate(STREETS):
            if s["_layer"] not in layers:
                continue
            L = LineString(s["line"])
            idx = [i for i in range(len(others_all)) if others_all[i][0] == s["id"]]
            oth = [o for i, o in enumerate(others_all) if i not in idx]
            ot = shapely.STRtree([q for _, q, _ in oth])
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
    """Generated street ends that sit on a street a few metres from another street's end on that same street (an OSM road
    that ends there, a grid line from the next quarter): moved onto that end, so the place is one junction, not two
    crossings a metre or five apart."""
    moved = 0
    for s in STREETS:
        if s["_layer"] not in layers:
            continue
        oth = _lines_except(s["id"])
        tree = shapely.STRtree([q for _, q, _ in oth])
        ends = [Point(q.coords[0]) for _, q, _ in oth] + [Point(q.coords[-1]) for _, q, _ in oth]
        etree = shapely.STRtree(ends)
        for e in (0, -1):
            P = Point(s["line"][e])
            on_ = [oth[i][1] for i in tree.query(P.buffer(0.6)) if oth[i][2] not in NO_JUNCTION and oth[i][1].distance(P) < 0.5]
            if not on_:
                continue
            near = sorted((ends[i].distance(P), ends[i]) for i in etree.query(P.buffer(tol)))
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


LANE_REACH = 25.0      # m: a house is served when a street is this close (rule 12, fire_access.max_distance_to_building_m)
LANE_MAX = 150.0       # m: dead-end limit of a village lane (fire_access.dead_end_max_m)


def house_lanes(log=None):
    """Existing houses outside the villages and outside the new quarters (farms in parks, reserves and corridors) with no
    street within LANE_REACH: a village lane from the nearest street toward the group, its red line ending 1.5 m short of the house
    (≤ LANE_MAX, never through a house, never across an expressway, a ramp or water). Groups = houses within 40 m."""
    hs = [h for h in HOUSES if GATE.contains(h.centroid) and not VILL.contains(h.centroid)
          and not Z.DEV.buffer(-5.0).contains(h.centroid)]
    lines = [(s["id"], LineString(s["line"])) for s in STREETS if s["class"] not in ("expressway", "ramp", "pedestrian_street", "bike_path")]
    lines += [("osm:" + oid, q) for oid, q, cls in OSM_HOST]          # existing service roads serve their houses too
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
        # the lane's red line ends 1.5 m short of the house (rule 12: the house lot is within 2 m of its street's red line)
        rh = red_w("village_lane") / 2.0
        end = LineString([a, b]).interpolate(d - rh - 1.5)
        lane = LineString([(a.x, a.y), (end.x, end.y)])
        if lane.length < LINK_MIN - 0.5 or houses_hit(lane.buffer(rh + 1.0)) or lane.crosses(barrier) or lane.intersects(WATER_POLY):
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


LINK_MAX = 150.0       # m: longest through link added at the dead end of an existing road (fire_access.dead_end_max_m)
LINK_MIN = 15.0        # m: no shorter link (a street of a few metres between two roads is not a street)
DEAD_END_OK = {"driveway_main", "driveway_secondary", "local", "local_secondary", "village_lane"}   # rule 5: may end ≤ 150 m


def link_dead_ends(log=None):
    """Existing roads (kept OSM streets and OSM roads that stay) that end in nothing inside Gate: a straight through link
    from the dead end to the nearest other street — straight ahead first, else the shortest — ≤ LINK_MAX, never through
    a house (the link's red line clear of houses), never across an expressway, a ramp or water, never back along its own
    road or along another street (the link leaves the end within 105° of the road's own direction). An end that touches any
    line (an expressway too: the network joins them there) is not a dead end; a link made counts as a street for the ends
    after it. Class: village lane in a village, local elsewhere. A dead end with no such link stays as it is (logged)."""
    lines = [(s["id"], LineString(s["line"]), s["class"]) for s in STREETS if s["class"] not in ("pedestrian_street", "bike_path")]
    lines += [("osm:" + oid, q, cls) for oid, q, cls in OSM_HOST]
    tree = shapely.STRtree([q for _, q, _ in lines])
    barrier = unary_union([q for _, q, c in lines if c in ("expressway", "ramp")])
    links = []                      # LineStrings of the links made so far
    made, kept = 0, 0
    for i, (sid, L, cls) in enumerate(lines):
        existing = sid.startswith("osm:") or SID[sid]["_layer"] == "osm"
        if not existing or cls in ("expressway", "ramp"):
            continue
        for e in (0, -1):
            E = Point(L.coords[e])
            if GATE.exterior.distance(E) < 3.0:
                continue
            if any(j != i and lines[j][1].distance(E) < 0.5 for j in tree.query(E.buffer(0.6))) \
                    or any(k.distance(E) < 0.5 for k in links):
                continue
            # a short dead end of a class that may end (rule 5: ≤ 150 m) stays
            oth = [o for j, o in enumerate(lines) if j != i]
            ch = _cut_points(L, oth, shapely.STRtree([q for _, q, _ in oth]), {"struct": []})
            s_e = 0.0 if e == 0 else L.length
            branch = min((abs(c - s_e) for c in ch if abs(c - s_e) > 0.5), default=L.length)
            if cls in DEAD_END_OK and branch <= LINK_MAX:
                continue
            # the end's direction (last 20 m of the line)
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
                    continue              # it would turn back toward its own road (over 105°): not a through link
                inner = substring(link, 1.0, link.length - 1.0)
                near = [lines[j][1] for j in tree.query(inner.buffer(3.0)) if lines[j][0] != host] + links
                if any(M.intersects(inner) for M in [lines[j][1] for j in tree.query(inner)]) \
                        or any(M.intersects(inner) for M in links):
                    continue              # it would cross another street on the way: not one link
                if any(inner.intersection(M.buffer(3.0)).length > 3.0 for M in near):
                    continue              # it would run along another street
                lcls = "village_lane" if VILL.contains(link.centroid) else "local"
                if houses_hit(link.buffer(red_w(lcls) / 2.0)) or link.crosses(barrier) or link.intersects(WATER_POLY) \
                        or not GATE.contains(link):
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
      pull — a piece of the trial quarter (inside fixed_poly; its years are the level-1 design) whose end has no street
             open by its year gets the shortest chain of new pieces (by length) to a street open by then, opening with it.
    A street is split only at its junctions (a divided street there runs straight on, so its carriageways meet).
    Existing roads are 2025 and end blind as OSM has them."""
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

    # 1. cut every line at its junctions (ends on it, its ends on others, at-grade crossings)
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
    pieces = []          # [sid, a, b, group, length]
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
    # 2. nodes: piece ends clustered within SNAP_J (junction points a few metres apart are one junction)
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
    edge = {n for n in at if GATE.exterior.distance(pts[n]) < 3.0 or any(pts[n].distance(j) < 3.0 for j in joints)}
    # 3. year variables: one per piece, one per divided street; fixed: existing roads, trial pieces
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
        elif s.get("_layer") == "trial" and fixed_poly.buffer(1.0).contains(mid):
            fixed.add(g)
    plen = [b - a for _, a, b in pieces]

    def others(k, n):
        return [q for q in at[n] if q != k]
    pulled = []
    for _round in range(60):
        changed = False
        # push (forward fixpoint) of the free groups
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
        # pull for fixed pieces with a blind end
        for k in range(len(pieces)):
            g = grp[k]
            if g not in fixed or g in existing:          # existing roads end blind as in OSM (a warning, not ours to fix)
                continue
            y = year[g]
            for n in (node_of[2 * k], node_of[2 * k + 1]):
                if n in edge:
                    continue
                o = [q for q in others(k, n) if grp[q] != g]
                if not o or min(year[grp[q]] for q in o) <= y:
                    continue
                # Dijkstra over free pieces later than y, cost = length (a divided street: its whole length)
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
    # 4. write back: a street with pieces of different years is split into runs (the first run keeps the id)
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
        # the run that keeps the id: for a trial street the one inside the trial quarter, otherwise the first
        keep_i = 0
        if s.get("_layer") == "trial":
            keep_i = max(range(len(runs)), key=lambda i: substring(L, runs[i][0], runs[i][1]).intersection(fixed_poly).length)
        made = [s]
        for i, (a, b, y) in enumerate(runs):
            q = substring(L, a, b)
            st = [x for x in s.get("struct") or [] if q.distance(Point(x["from"])) < 1.0 and q.distance(Point(x["to"])) < 1.0]
            if i == keep_i:
                s2 = s
            else:
                s2 = copy.deepcopy(s)
                k = 1
                while f"{s['id']}_y{k}" in SID:
                    k += 1
                s2["id"] = f"{s['id']}_y{k}"
                s2["why"] = (s.get("why") or "") + f"; участок открывается в {y} (годы по участкам: без тупиков в каждом году)"
                if s.get("_layer") == "trial":
                    s2["_layer"] = "frame"
                new_streets.append(s2)
                made.append(s2)
                SID[s2["id"]] = s2
            s2["line"] = [[round(x, 1), round(z, 1)] for x, z in q.coords]
            s2["struct"] = st
            s2["years"] = Y4(y, use) if (i != keep_i or y != y_old) else s["years"]
            if s2 is not s or y != y_old:
                moves.append((s2["id"], y_old, y))
        if s.get("_layer") == "trial":
            extra = ", ".join(f"{x['id']} ({x['years'][0]})" for x in made if x is not s)
            TRIAL_CHANGED[s["id"]] = (TRIAL_CHANGED.get(s["id"], "") + "; " if s["id"] in TRIAL_CHANGED else "") + \
                f"продолжение за пробной зоной открывается позже, отдельными участками: {extra}"
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
