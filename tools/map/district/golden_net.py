#!/usr/bin/env python3
"""Golden · level 2 · street network of the whole district (w50), imported by golden_build.py.

    python3 -I tools/map/district/golden_net.py            # build in memory, print a summary

The network is made of three layers (as Gate's, gate_net.py):
  1. existing roads (Overture/OSM): А-3 and А-19 with their ramps and the two existing interchanges (km 30.1, km 39), the
     regional road KZ05-10, the tertiary roads, village streets stay as they are (gen_network takes them from OSM); existing
     roads inside new quarters are replaced (replaced_osm), among them ул. Болысбаева (e51c1fb2) with its two at-grade links
     onto А-3 (replaced by the «Жаңаталап» cross street and its diamond);
  2. the frame of new streets by the level-0 scheme axes (X-T2..X-T4, X-A1..X-A3n, X-D1..X-D4, X-B1) with four new
     diamonds on А-3 («Жаңаталап», «Көктерек», «K-Park», «Северная»);
  3. local streets of every new quarter, generated here (the generator's grid is off for v1 specs): an edge street along
     every side of the quarter that has no street (village, park, river, expressway, district edge) and a grid at the
     zone's block size, aligned with the frame, every end on a street.
The generic generator and post-pass functions (generate_local … phase_years) are Gate's (gate_net.py, w47), carried over
as they are (gate_net builds Gate on import, so it cannot be imported here).
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

import golden_common as C  # noqa: E402
import land_util as LU  # noqa: E402

MODEL = C.MODEL
Y4 = C.Y4
fillet = C.fillet
CITY = C.CITY
V0 = C.V0
GOLDEN = C.GOLDEN
GATE = GOLDEN                     # the generic functions below were written for Gate: the district polygon
V0AX = {a["id"]: a for a in V0["axes"]}

_LN = LU.Norms()
_RW = {}


def red_w(cls, profile=None):
    if cls not in _RW:
        _RW[cls] = float(LU.profile_from_norms(_LN, cls)["red_line_w"])
    w = _RW[cls]
    g = float((profile or {}).get("green_w") or 0.0)
    return max(w, g + 6.0) if g else w


# ===================================================================================================== open data
OSM = {p["id"]: (g, p) for g, p in C.layer_in("roads", GOLDEN)}
SH = {k[:8]: k for k in OSM}


def osm(short):
    return OSM[SH[short]]


import golden_zones as Z  # noqa: E402

VILL = Z.VILL
_W = C.layer_in("water", GOLDEN.buffer(200))
WATER_POLY = unary_union([g for g, p in _W if g.geom_type in ("Polygon", "MultiPolygon") and p.get("class") != "swimming_pool"])
WATER_LINE = unary_union([g for g, p in _W if g.geom_type in ("LineString", "MultiLineString")])
STRIP = 35.0                                       # flood.water_protection_strip_min_m
WATER_STRIP = unary_union([WATER_POLY.buffer(STRIP), WATER_LINE.buffer(STRIP)])

from gen_blocks_lots import existing_houses  # noqa: E402

HOUSES = [h["fp"] for h in existing_houses(GOLDEN.buffer(80), Polygon())]
HTREE = shapely.STRtree(HOUSES)


def houses_hit(geom):
    return [HOUSES[i] for i in HTREE.query(geom, predicate="intersects")]


# ===================================================================================================== registries
STREETS, NODES = [], {}
SID = {}
SCHEME_CHANGES = []              # frame changes against the level-0 scheme: (id, why)
TRIAL_CHANGED = {}               # (Gate's trial-quarter changes; Golden has no trial quarter: stays empty)


def change(sid, why):
    SCHEME_CHANGES.append((sid, why))


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


# ===================================================================================================== 1. existing roads
VILLAGE_OSM = {"residential", "service", "unclassified", "living_street", "unknown"}
KEEP_IDS = {}
KZ0510 = {"f0e1db1c", "e86740b0", "6bd6a553", "351e8a39", "3e4edf2f", "e19f88e8", "3e9d06ce", "9efcca6d", "863f9816",
          "6b0f4b22", "185ed19a"}
# ул. Болысбаева: a 2 km tertiary road from Жаңаталап diagonally through the new southern quarters to А-3, where it joins
# the expressway at grade by two tertiary links (rule 6: no at-grade junction on an expressway); replaced by the cross street
# «Жаңаталап» (X-T4) from the same village street end and its diamond 950 m to the south
REPLACED_BY_FRAME = {"e51c1fb2": "ул. Болысбаева: заменена поперечной «Жаңаталап» (X-T4) от того же конца улицы села",
                     "3d40717a": "съезд ул. Болысбаева на А-3 в одном уровне: заменён ромбом «Жаңаталап»",
                     "9f367528": "съезд ул. Болысбаева на А-3 в одном уровне: заменён ромбом «Жаңаталап»",
                     # a roadside service loop on the east edge of А-3 at (−1360, −9760…−9970): the north-east ramp of
                     # the diamond «Көктерек» runs over it (rule 7: ramps met it at 17–42°, its own exit onto А-3 cut the
                     # ramp's speed-change lane to 37 m); the two buildings there get a lane from the local street east
                     "a84b7e85": "сервисная петля у А-3 (подъезд к двум придорожным зданиям): на её месте северо-восточный "
                                 "съезд ромба «Көктерек»; к зданиям — проулок от местной улицы с востока",
                     "bffa8864": "сервисная петля у А-3 (вторая ветка): на её месте северо-восточный съезд ромба «Көктерек»",
                     # a residential street east of А-3 at (−744, −5965): its first 32 m run to the expressway's edge,
                     # where the south ramp of the diamond «Северная» now lies (rule 7: the ramp crossed it at 52–53°);
                     # the rest of it (71 m along the houses) stays as v_ccd42a63, the houses keep their streets east
                     "ccd42a63": "жилая улица у А-3: первые 32 м до края трассы сняты (там съезд ромба «Северная»), "
                                 "остальные 71 м вдоль домов — улица v_ccd42a63"}
CUT_OSM = {"ccd42a63": (-716.9, -5946.9)}        # OSM roads kept from this vertex on (the part before it is retired)


def osm_class(p, g):
    c, sub = p.get("class"), p.get("sub")
    if c == "motorway":
        return "ramp" if sub == "link" else "expressway"
    if c in ("tertiary", "secondary", "primary"):
        return "village_main" if g.intersection(VILL).length > 0.5 * g.length else "district_transport"
    return None


def keep_name(p, oid):
    n = p.get("name") or ""
    if n.startswith(("Алматы-Ө", "Алматы - Ө", "Almaty-Ö")):
        return "А-3 Алматы – Өскемен"
    if n.startswith("Алматы - Қорғас"):
        return "А-19 Алматы – Қорғас"
    if p.get("sub") == "link":
        return "съезд развязки"
    if oid[:8] in KZ0510:
        return "KZ05-10 (областная дорога)"
    return n


for oid, (g, p) in sorted(OSM.items()):
    if oid[:8] in REPLACED_BY_FRAME:
        continue
    cls = osm_class(p, g)
    if cls is None:
        continue
    clip = g.intersection(GOLDEN)
    if clip.length < 3.0:
        continue
    sid = ("k_" if cls in ("expressway", "ramp") else "t_") + oid[:8]
    nm = keep_name(p, oid)
    ax = None
    if cls == "expressway":
        ax = "X-A19" if "А-19" in nm else "X-A3"
    elif oid[:8] in KZ0510:
        ax = "X-T1"
    parts = [clip] if clip.geom_type == "LineString" else [q for q in clip.geoms if q.geom_type == "LineString"]
    line = max(parts, key=lambda q: q.length).coords
    street(sid, cls, line, nm or ("улица села" if cls == "village_main" else ""), 2025, oneway=cls in ("expressway", "ramp"),
           source="keep_existing:" + oid, axis=ax, years=C.EXISTING, layer="osm",
           why="существующая дорога OSM/Overture, как есть (направление линии = направление движения)" if cls in ("expressway", "ramp")
           else "существующая дорога OSM, как есть")
    KEEP_IDS[oid] = sid

HOST_OSM = {oid for oid, (g, p) in OSM.items() if p.get("class") in VILLAGE_OSM | {"tertiary", "secondary"}}


def osm_line(oid):
    g = OSM[oid][0].intersection(GOLDEN)
    parts = [g] if g.geom_type == "LineString" else [q for q in getattr(g, "geoms", []) if q.geom_type == "LineString"]
    return parts


def k_at(pt, tol=60.0, cls="expressway"):
    """Spec ids of the kept OSM streets of class cls within tol of pt, nearest first."""
    P = Point(pt)
    c = [(LineString(s["line"]).distance(P), s["id"]) for s in STREETS if s["_layer"] == "osm" and s["class"] == cls]
    return [sid for d, sid in sorted(c) if d < tol]


# ===================================================================================================== 2. frame of new streets
A3 = unary_union([LineString(s["line"]) for s in STREETS if s["class"] == "expressway" and s["axis"] == "X-A3"])
A3_IDS = [s["id"] for s in STREETS if s["class"] == "expressway" and s["axis"] == "X-A3"]
LRT_MEDIAN = {"median_w": 8.0, "lanes": [2, 2], "note_ru": "в разделительной полосе — пути ЛРТ"}
OVER_HALF = 55.0                  # m: overpass half length over А-3 (both carriageways + shoulders)
EMB_HALF = 150.0                  # m: embankment ends (deck +6.5 m at ≤ 5 % on both sides)


def a3_cross(line):
    """Centre of the crossing of a line with А-3 (midpoint of the crossings with its two carriageways) and the two ids."""
    L = LineString(line)
    hits = []
    for sid in A3_IDS:
        x = L.intersection(LineString(SID[sid]["line"]))
        for q in getattr(x, "geoms", [x]):
            if q.geom_type == "Point":
                hits.append((L.project(q), sid, q))
    hits.sort()
    if len(hits) < 2:
        raise SystemExit(f"линия не пересекает обе проезжие части А-3: {hits}")
    a, b = hits[0], hits[1]
    c = 0.5 * (a[0] + b[0])
    P = L.interpolate(c)
    return (P.x, P.y), c, a[1], b[1]


def over_a3(line):
    """Struct of a new street over А-3: embankment, overpass, embankment (chainages along the line)."""
    L = LineString(line)
    _, c, _, _ = a3_cross(line)
    pt = lambda s: (L.interpolate(s).x, L.interpolate(s).y)
    return [(pt(c - EMB_HALF), pt(c - OVER_HALF), "embankment"), (pt(c - OVER_HALF), pt(c + OVER_HALF), "overpass"),
            (pt(c + OVER_HALF), pt(c + EMB_HALF), "embankment")]


_SKIP_OSM = {"track", "footway", "path", "cycleway", "steps", "pedestrian", "bridleway"}


def chain_head(kid):
    """The spec id gen_network keeps for an expressway piece: net_osm._chain joins OSM pieces of one carriageway that meet
    end to start with no other road at that point, and the joined way keeps the first piece's street id."""
    def key(p):
        return (round(float(p[0]), 1), round(float(p[1]), 1))
    from collections import defaultdict
    at = defaultdict(list)
    for oid, (g, p) in OSM.items():
        if oid[:8] in REPLACED_BY_FRAME or p.get("class") in _SKIP_OSM:
            continue
        for q in osm_line(oid):
            at[key(q.coords[0])].append((oid, 0))
            at[key(q.coords[-1])].append((oid, 1))
    cur = kid
    seen = {cur}
    while True:
        s = SID[cur]
        uses = at[key(s["line"][0])]
        prev = [o for o, e in uses if e == 1 and KEEP_IDS.get(o) and SID[KEEP_IDS[o]]["class"] == s["class"]]
        if len(uses) != 2 or len(prev) != 1 or KEEP_IDS[prev[0]] in seen:
            return cur
        cur = KEEP_IDS[prev[0]]
        seen.add(cur)


def diamond(nid, sid, name_ru, why):
    s = SID[sid]
    C0, c, ka, kb = a3_cross(s["line"])
    ka, kb = chain_head(ka), chain_head(kb)
    node(nid, C0[0], C0[1], "diamond", [ka, kb, sid], major=ka, major_pair=kb, upper="minor", name_ru=name_ru, why_ru=why)
    return C0


def bridges(line):
    return water_bridges(line)


def chk_line(pts):
    return [(round(x, 1), round(z, 1)) for x, z in pts]


# --- X-T4 «Жаңаталап»: from the east end of the village street (where ул. Болысбаева began) east over А-3 (diamond)
V_END = tuple(round(v, 1) for v in osm("72a25603")[0].coords[0])
T4 = fillet([V_END, (-3350.0, -14545.0), (-2600.0, -14335.0), (-2120.0, -14440.0), (-850.0, -14500.0)], 350)
street("s_t4", "arterial_regulated", T4, "Поперечная улица «Жаңаталап»", 2028, axis="X-T4",
       struct=over_a3(T4) + bridges(T4),
       why="схема X-T4 (2027–30): первая поперечная — от улиц Жаңаталапа (конец ул. Умурзакова, где начиналась ул. Болысбаева) "
           "через новую развязку «Жаңаталап» на восточную сторону А-3 к центру «Есентай»")
change("s_t4", "западный конец — на конце улицы села (72a25603), где начиналась ул. Болысбаева (снята: шла по диагонали через новые "
               "кварталы и выходила на А-3 в одном уровне); у схемы ось кончалась в поле у (−3300, −14100)")
C_T4 = diamond("ic_zhanatalap", "s_t4", "Развязка «Жаңаталап»",
               "новый ромб на А-3 (схема 2028–30); до существующей развязки км 30,1 — 2,3 км (норма ≥ 1,6 км)")
# --- X-A1 Западный проспект: LRT in the median from X-T4 to KZ05-10, then north along the scheme axis to the north
P_A1S = on(T4, x=-2585.0)
A1_S = fillet([P_A1S, (-2520.0, -13500.0), (-2440.0, -12900.0), (-2355.0, -12020.0)], 600)
P_A1_KZ = on(L_("t_863f9816"), x=-2355.0)
A1_S[-1] = P_A1_KZ
A1_N_ALL = fillet([P_A1_KZ, (-2420.0, -11600.0), (-2700.0, -11000.0), (-2700.0, -10100.0), (-2560.0, -9300.0),
                   (-2050.0, -8250.0), (-2060.0, -8100.0), (-2100.0, -7000.0), (-2150.0, -5800.0), (-2000.0, -4600.0),
                   (-2000.0, -3700.0)], 450)
street("s_a1_s", "district_transport", A1_S, "Западный проспект (юг, ЛРТ в разделительной полосе)", 2027, axis="X-A1",
       profile=dict(LRT_MEDIAN), struct=bridges(A1_S),
       why="схема X-A1 (2027–40), южная часть: дублёр А-3 с запада; в разделительной полосе — ствол ЛРТ (2031)")
# the north end runs on to ул. d492aa6d (existing tertiary road along the north border), straight north at x −2000 (the
# scheme's last leg to (−1500, −3700) ran over the houses at (−1450, −3490))
_d492 = LineString(osm_line(SH["d492aa6d"])[0])
A1_N_ALL.append(on(_d492, x=-2000.0))
change("s_a1", "северный конец — прямо на север по x −2000 до существующей дороги d492aa6d: последний отрезок схемы к (−1500, −3700) "
               "проходил по домам у (−1450, −3490) и кончался в поле")
street("s_a1", "district_transport", A1_N_ALL, "Западный проспект", 2031, axis="X-A1", struct=bridges(A1_N_ALL),
       why="схема X-A1 (2027–40): дублёр А-3 с запада в 400–900 м — от KZ05-10 мимо садов и Теренкары (мост) к западному концу "
           "проспекта K-Park и на север к логистике у км 39; на севере доведён до существующей дороги d492aa6d")
# --- X-A2 Проспект Знаний (east of А-3): from X-T4 north past the km 30.1 interchange to the campus and X-T2
# east of А-3 at km 30.1 the district border comes to the interchange's ramp terminal on KZ05-10 (−1423, −12220): the
# avenue passes through that junction (it cannot pass east of it, and west of it it would cross the ramps)
TERM30 = tuple(round(v, 1) for v in osm("7d79ac96")[0].coords[0])
A2S = fillet([(-850.0, -14500.0), (-1250.0, -13300.0), (-1460.0, -12450.0), TERM30], 450)
A2S[0] = on(T4, x=-850.0)
A2S[-1] = TERM30
# … but a fifth arm at the ramp terminal (KZ05-10 both ways + two ramps) needs a ring (rule 6), and a ring does not fit
# between the ramps and the border: the avenue ends on the existing road fa23ea6d 26 m south of the terminal
_fa = LineString(osm_line(SH["fa23ea6d"])[0])
_LA2S = LineString(A2S)
_xa = _LA2S.intersection(_fa)
_xa = _xa if _xa.geom_type == "Point" else min(getattr(_xa, "geoms", []), key=lambda q_: _LA2S.project(q_))
A2S = [tuple(c) for c in substring(_LA2S, 0.0, _LA2S.project(_xa)).coords]
A2S[-1] = (round(_xa.x, 1), round(_xa.y, 1))
# north of KZ05-10 the avenue cannot start at the terminal either: the border and the ramp 7d79ac96 meet there (no 40 m
# corridor between them); it starts north of the interchange land and is tied to the local streets there
A2 = fillet([(-1335.0, -11640.0), (-1300.0, -11500.0), (-1050.0, -11000.0), (-600.0, -9700.0), (-660.0, -8650.0),
             (-583.0, -8544.0)], 450)
street("s_a2_s", "district_transport", A2S, "Проспект Знаний (юг)", 2028, axis="X-A2", struct=bridges(A2S),
       why="схема X-A2 (2027–33): главная улица восточной стороны — от поперечной «Жаңаталап» на север к узлу съездов развязки "
           "км 30,1 на KZ05-10")
change("s_a2_s", "южная часть кончается на существующей дороге fa23ea6d в 26 м южнее узла съездов км 30,1 на KZ05-10 "
                 "(−1423, −12220): пятый луч узла съездов требует кольца (правило 6), а кольцо не помещается между съездами "
                 "и границей района; к KZ05-10 и Gate — по fa23ea6d")
change("s_a2", "у развязки км 30,1 проспект разорван: южная часть (s_a2_s) кончается у узла съездов на KZ05-10 (−1423, −12220), "
               "северная (s_a2) начинается севернее земли развязки — между съездом 7d79ac96 и границей района нет места для "
               "красной линии 40 м, а западнее ось схемы пересекала бы два съезда; связь — по KZ05-10 и местным улицам")
# --- X-T2 Проспект K-Park: from Западный проспект over А-3 (diamond «K-Park») through the centre to J041 on the east border
J041 = (2608.7, -8721.6)
T2 = fillet([on(A1_N_ALL, z=-8250.0), (-1126.0, -8250.0), (-650.0, -8450.0), (-150.0, -9150.0), (700.0, -9050.0),
             (1700.0, -8880.0), (2100.0, -8745.0), (2440.0, -8685.0), J041], 350)
T2[-1] = J041
change("s_t2", "восточный конец — через (2100, −8745) и (2440, −8685) к J041: прямая схемы (1700, −8850)→J041 у x 2450–2600 "
               "выходила за границу района на 15–20 м (там граница и дома соседа)")
_a2end = LineString(T2).interpolate(LineString(T2).project(Point(A2[-1])))
A2[-1] = (_a2end.x, _a2end.y)
street("s_t2", "arterial_regulated", T2, "Проспект K-Park", 2031, axis="X-T2", struct=over_a3(T2) + bridges(T2),
       why="схема X-T2 (2030–33): главная поперечная через центр — от Западного проспекта через развязку «K-Park» к стыку J041 "
           "на восточной границе (дорога на восток, существующая fca7be0d)")
change("s_a2", "северный конец — на X-T2 у (−583, −8544), а не в точке схемы (−650, −8450): там X-T2 идёт мостом через "
               "протоку (примыкание на мосту невозможно); последние 130 м повёрнуты к X-T2 под углом ~70°")
street("s_a2", "district_transport", A2, "Проспект Знаний", 2029, axis="X-A2", struct=bridges(A2),
       why="схема X-A2 (2027–33): от земли развязки км 30,1 на север к Университетскому городу и центру K-Park")
C_T2 = diamond("ic_kpark", "s_t2", "Развязка «K-Park»", "новый ромб на А-3 (схема 2030–33) у главного центра")
node("n_rb_k5", T4[-1][0], T4[-1][1], "roundabout", ["s_t4", "s_a2_s"], r=22.0, name_ru="Площадь «Есентай»")
node("n_rb_zh", V_END[0], V_END[1], "roundabout", ["s_t4", "t_72a25603"], r=22.0, name_ru="Кольцо у въезда в Жаңаталап")
change("n_rb_k5", "кольцо R 22 м в углу X-T4 / X-A2 / X-D2 (центр Z-K5): X-T4 — две проезжие части, в углу без кольца одна "
                  "из них кончалась тупиком (правило 5)")
change("n_rb_zh", "кольцо R 22 м на западном конце X-T4 у улиц Жаңаталапа (72a25603, db01308d): две проезжие части X-T4 "
                  "сходятся на кольце, без него одна кончалась тупиком (правило 5)")
# --- X-D1 улица Көктерек: from Западный проспект (extended west, so the diamond has both sides) over А-3 to the campus
D1 = fillet([on(A1_N_ALL, z=-10100.0), (-1456.0, -10250.0), (-600.0, -10150.0), (300.0, -10100.0), (1300.0, -10200.0)], 300)
street("s_d1", "district_transport", D1, "Улица Көктерек", 2030, axis="X-D1", struct=over_a3(D1) + bridges(D1),
       why="схема X-D1 (2029–32): въезд в Университетский город от развязки «Көктерек»; адрес QAIST и медкластера")
change("s_d1", "продолжена на запад до Западного проспекта: у ромба «Көктерек» обе стороны А-3 — улицы (у схемы ось начиналась "
               "на самой развязке)")
C_D1 = diamond("ic_kokterek", "s_d1", "Развязка «Көктерек»", "новый ромб на А-3 (схема 2029–31) у Университетского города")
# --- X-T3 Северная магистраль: from улица Косөзен over А-3 (diamond «Северная») to the north-east pocket
T3 = fillet([(-7000.0, -5750.0), (-4500.0, -5700.0), (-2600.0, -5600.0), (-772.0, -5550.0), (-250.0, -5450.0)], 400)
street("s_t3", "arterial_regulated", T3, "Северная магистраль", 2036, axis="X-T3", struct=over_a3(T3) + bridges(T3),
       why="схема X-T3 (2035–38): отделяет жильё севера от логистики; развязка «Северная»; на востоке — к северо-восточному проспекту")
C_T3 = diamond("ic_north", "s_t3", "Развязка «Северная»", "новый ромб на А-3 (схема 2036–38)")
# --- X-D3 улица Косөзен (industrial): west edge of the logistics along the Каскелен valley brow
D3 = [on(LineString(osm_line(SH["82d8f642"])[0]), x=-7010.0), (-7000.0, -5750.0), (-6950.0, -3900.0)]
change("s_d3", "продолжена на юг на 400 м до существующей дороги 82d8f642: X-T3 (две проезжие части) кончается на ней "
               "Т-образно; в углу схемы X-T3/X-D3 одна проезжая часть X-T3 оставалась тупиком (правило 5)")
street("s_d3", "industrial", D3, "Улица Косөзен", 2038, axis="X-D3", struct=bridges(D3),
       why="схема X-D3 (2038–46): западная граница застройки вдоль бровки долины Каскелена, подъезд к складам и очистным")
# --- X-A3n Северо-восточный проспект: between the dacha massifs to the joint J030 (Growing-E)
J030 = (-532.0, -3421.0)
TERM39 = tuple(round(v, 1) for v in osm("60ff8c62")[0].coords[-1])      # ramp 60ff8c62 ends on 28dce1c7 / e8deab74
E8_END = on(LineString(osm_line(SH["e8deab74"])[0]), x=-250.0)        # on the existing tertiary e8deab74, inside Golden
A3N = fillet([(-250.0, -7200.0), (-150.0, -6500.0), (-250.0, -5450.0), (-100.0, -4300.0), (-200.0, -3800.0), E8_END], 350)
A3N[-1] = E8_END
street("s_a3n", "district_transport", A3N, "Северо-восточный проспект", 2036, axis="X-A3n", struct=bridges(A3N),
       why="схема X-A3n (2034–38): между дачами «Рассвет» и «Энергетик» к стыку J030 (Growing-восток), каркас северо-восточного кармана")
change("s_a3n", "северный конец — на существующей дороге e8deab74 у x −250 (в 250 м от стыка J030): к самому J030 ось пересекала бы "
                "съезд 60ff8c62 развязки км 39, а узел съезда с дорогами 28dce1c7 / e8deab74 лежит за границей района; дальше на "
                "Growing-восток — по e8deab74 и 28dce1c7 через J030")
# --- X-D4 улица Ақжар
D4 = fillet([(-250.0, -5450.0), (400.0, -5450.0), (1200.0, -5300.0)], 300)
street("s_d4", "district_transport", D4, "Улица Ақжар", 2037, axis="X-D4", struct=bridges(D4),
       why="схема X-D4 (2036–40): главная улица северо-восточного кармана: станция «Ақжар» — центр — Әли")
# --- X-D2 улица Ипподромная: the loop to the sport centre and the hippodrome from the two avenues
D2 = fillet([(-850.0, -14500.0), (-300.0, -13600.0), (-700.0, -13100.0), on(A2S, z=-13300.0)], 200)
D2[0] = A2S[0]
street("s_d2", "district_transport", D2, "Улица Ипподромная", 2040, axis="X-D2", struct=bridges(D2),
       why="схема X-D2 (2040–46): кольцевой подъезд к спортцентру и ипподрому с двух магистралей")
# --- X-B1 Бульвар Знаний: the campus ring (boulevard), its ends on Проспект Знаний
B1 = fillet([on(A2, z=-11250.0), (-880.0, -11500.0), (-450.0, -11500.0), (0.0, -11460.0),
             (550.0, -10600.0), (700.0, -9800.0), (-150.0, -9450.0), on(A2, z=-9600.0)], 150)
street("s_b1", "boulevard", B1, "Бульвар Знаний", 2032, axis="X-B1", struct=bridges(B1),
       why="схема X-B1 (2029–40): кольцо кампуса — станции ЛРТ, QAIST, центр «Көктерек», кластер вузов, парк; концы — на "
           "Проспекте Знаний")
change("s_b1", "концы бульвара — на Проспекте Знаний (у схемы кольцо начиналось и кончалось у станций ЛРТ, не на улицах)")

FRAME_IDS = [s["id"] for s in STREETS if s["_layer"] == "frame"]

# ===================================================================================================== 3. local streets
KEEP_POLY = Polygon()            # Golden has no keep quarter
NO_HOST = {"expressway", "ramp", "pedestrian_street", "bike_path", "boulevard", "driveway_main", "driveway_secondary"}
D_IN = 10.0                     # edge streets run 10 m inside the quarter's border (local red line 15 m: half 7.5 + 2.5)
EXP_HALF = 45.0                 # expressways: half red line 25 + 20 m (no quarter edge right at the carriageway)

# existing roads inside new quarters are replaced by the new streets (tracks are not built anyway)
DEV_IN = Z.DEV.difference(VILL)
RETIRED = sorted(SH[k] for k in REPLACED_BY_FRAME)
for oid, (g, p) in OSM.items():
    if p.get("class") in ("motorway", "tertiary", "secondary", "primary") or oid in KEEP_IDS or oid in RETIRED:
        continue
    gi = g.intersection(GOLDEN)
    if gi.length < 1.0:
        continue
    if p.get("class") == "track" and gi.intersects(DEV_IN):
        RETIRED.append(oid)
    elif gi.intersection(DEV_IN.buffer(5)).length > 0.5 * gi.length and not houses_hit(gi.buffer(30.0)):
        RETIRED.append(oid)                      # a road that serves existing houses stays
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
for short, at in sorted(CUT_OSM.items()):
    oid = SH[short]
    g_, p_ = OSM[oid]
    cc = list(g_.coords)
    i_ = min(range(len(cc)), key=lambda i: math.dist(cc[i], at))
    cls = "village_secondary" if g_.intersection(VILL).length > 0.5 * g_.length else "local"
    street("v_" + short, cls, cc[i_:], p_.get("name") or "улица (OSM, часть)", 2025, years=C.EXISTING, layer="osm",
           why=f"существующая улица OSM {short} без её первых {LineString(cc[:i_ + 1]).length:.0f} м: "
               + REPLACED_BY_FRAME[short])
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
THIN = []                # zone strips too narrow for a quarter (generate_local): green zones in golden_build
THIN_HALF = 22.5
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
    # a spike of a piece narrower than 2 × THIN_HALF (a zone's tongue between a corridor and a park) is cut off the piece
    # (an opening with mitred corners keeps the quarter's own corners): the edge street would wrap it up and back down
    opened = []
    for p in pieces:
        o = p.buffer(-THIN_HALF, join_style=2).buffer(THIN_HALF, join_style=2).intersection(p)
        spikes = [s_ for s_ in getattr(p.difference(o), "geoms", [p.difference(o)])
                  if s_.geom_type == "Polygon" and s_.area > 1500.0]
        if not spikes:
            opened.append(p)
            continue
        parts_ = [q for q in getattr(o, "geoms", [o]) if q.geom_type == "Polygon"]
        keep_ = [q for q in parts_ if q.area > 15000.0]
        for s_ in spikes + [q for q in parts_ if 1500.0 < q.area <= 15000.0]:
            THIN.append(s_)
            GEN_LOG.append({"what": "узкий язык зоны (< 45 м) отрезан от квартала: без улиц, озеленение",
                            "ha": round(s_.area / 1e4, 2), "at": [round(v_) for v_ in s_.representative_point().coords[0]]})
        opened += keep_
    pieces = opened
    # a strip narrower than 2 × THIN_HALF between corridors (А-3's 45 m band and the LRT, a ramp and a stream) takes no
    # quarter: an edge street round it would run up one side and back down the other 20–40 m apart
    for p in [p for p in pieces if p.buffer(-THIN_HALF).area < 3000.0]:
        THIN.append(p)
        GEN_LOG.append({"what": "узкая полоса зоны между коридорами (< 45 м): без улиц, озеленение",
                        "ha": round(p.area / 1e4, 2), "at": [round(v_) for v_ in p.representative_point().coords[0]]})
    pieces = [p for p in pieces if p.buffer(-THIN_HALF).area >= 3000.0]
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
    lines += [("osm:" + oid, q) for oid, q, cls in OSM_HOST]          # existing drives (driveway_main) serve their houses too
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
        if lane.length < LINK_MIN - 0.5 or houses_hit(lane.buffer(rh + 1.0)) or lane.crosses(barrier) or lane.buffer(4.0).intersects(WATER_POLY):
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
    """Existing roads (kept OSM streets and OSM roads that stay) that end in nothing inside Golden: a straight through link
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
                # the carriageway, not only the axis, keeps off the water (rule 4 checks the carriageway polygon)
                if houses_hit(link.buffer(red_w(lcls) / 2.0)) or link.crosses(barrier) or link.buffer(6.0).intersects(WATER_POLY) \
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



def frame_report():
    """Frame streets: length, houses hit by the red line, metres over water, expressway / ramp crossings without a node."""
    exp = [(s["id"], LineString(s["line"])) for s in STREETS if s["class"] in ("expressway", "ramp")]
    for sid in FRAME_IDS:
        s = SID[sid]
        L = LineString(s["line"])
        hh = houses_hit(L.buffer(red_w(s["class"], s.get("profile")) / 2.0))
        wl = L.intersection(WATER_POLY).length
        xs = [k for k, M in exp if L.crosses(M)]
        print(f"  {sid:8s} {s['class']:20s} {L.length:7.0f} m  houses {len(hh):3d} {[tuple(round(v) for v in h.centroid.coords[0]) for h in hh[:4]]}"
              f"  water {wl:5.0f} m  crosses {xs[:6]}")


if __name__ == "__main__":
    frame_report()
    summary()
