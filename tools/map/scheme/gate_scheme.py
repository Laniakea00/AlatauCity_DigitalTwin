"""Gate · level 0 scheme: builds tools/map/spec/gate.json (centres, axes, zones, LRT, objects, phases, joints, checks)
and draws /mnt/project-files/alatau_stage7/level0/schemes/gate/scheme.png.

    python3 -I tools/map/scheme/gate_scheme.py            # spec + checks + picture
    python3 -I tools/map/scheme/gate_scheme.py --no-png   # spec + checks only

Inputs (read-only): tools/map/spec/city.json, registry.json; the level-0 layers of w34 (Overture/OSM buildings, roads, water,
power lines, settlements); the twin (buildings.csv, existing_osm footprints, gate_district.bytes, terrain). Unity frame X/Z, metres.
All design geometry below is the cartographer's decision (модель qTwin) unless a row says it comes from a source."""
import gzip
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "geo"))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box, shape  # noqa: E402
from shapely.ops import linemerge, unary_union  # noqa: E402

import frames  # noqa: E402
import layers  # noqa: E402
import terrain  # noqa: E402
import twin  # noqa: E402

SPEC = os.path.join(frames.SPEC_DIR, "gate.json")
OUTDIR = os.environ.get("GATE_SCHEME_OUT", "/mnt/project-files/alatau_stage7/level0/schemes/gate")
CITY = json.load(open(os.path.join(frames.SPEC_DIR, "city.json"), encoding="utf-8"))
REG = json.load(open(os.path.join(frames.SPEC_DIR, "registry.json"), encoding="utf-8"))
G = Polygon(CITY["districts"]["gate"]["polygon"]).buffer(0)
T = terrain.terrain()

# ------------------------------------------------------------------ the main decision: where Iconic stands
ICONIC = (-3500.0, -19500.0)
ICONIC_YAW = 270.0          # plaza front faces east (to the LRT station and the arrival avenue); grid N–S / W–E like A-3 (1.6°)
QT_HALF, QT_R = 375.0, 335.0  # gate_district.bytes: Half 375 m, mask = disc r ≈ 335 m (35.3 ha), read below

# rejected / compared candidates (computed by candidates())
CANDIDATES = [
    ("K1", "центроид полигона Gate", tuple(CITY["centres"]["gate"]["centroid"])),
    ("K2", "полюс недоступности Gate", tuple(CITY["centres"]["gate"]["pole_of_inaccessibility"])),
    ("K3", "центр тяжести свободной земли", (-3933.0, -19742.0)),
    ("K4", "медиана будущих жителей (взвешенная)", (-3931.0, -20154.0)),
    ("K5", "Iconic сегодня", (CITY["iconic"]["x"], CITY["iconic"]["z"])),
    ("K6", "середина северного массива", (-3008.0, -18920.0)),
    ("K7", "Gate City (юг)", (-3700.0, -23000.0)),
    ("K8", "к югу от БАКАД, между сёлами", (-4700.0, -20600.0)),
    ("ВЫБОР", "центр Gate: север узла БАКАД", ICONIC),
]


# ------------------------------------------------------------------ data
def load():
    bx = G.bounds
    clip = box(bx[0] - 1500, bx[1] - 1500, bx[2] + 1500, bx[3] + 1500)
    D = {}
    for name in ("buildings", "roads", "rail", "water", "infrastructure", "derived/settlements", "derived/height_zones", "derived/lrt_v0"):
        g, p = layers.load(name, cache=False)
        s = np.flatnonzero(shapely.intersects(clip, g))
        D[name] = (g[s], [p[i] for i in s])
    B = twin.buildings()
    ex = B[(B.source == "existing_osm") & (B.x > bx[0] - 500) & (B.x < bx[2] + 500) & (B.z > bx[1] - 500) & (B.z < bx[3] + 500)]
    D["twin_existing"] = list(twin.footprints(ex.bid.values).values())
    D["buildings_csv"] = B
    return D


def qtwin_mask():
    """Footprint of the Gate District quarter (QTwinData.Gate): W, Half and the mask read from the file the code loads."""
    p = frames.asset("Resources/Landmarks/gate_district.bytes")
    b = gzip.open(p).read()
    assert b[:4] == b"QGD1"
    o = 4
    nv, ni = struct.unpack_from("<ii", b, o); o += 8
    o += nv * 12 + nv * 3 + nv * 4 + nv + ni * 4
    nt = struct.unpack_from("<i", b, o)[0]; o += 4 + nt * 20
    W = struct.unpack_from("<i", b, o)[0]; o += 4
    half = struct.unpack_from("<f", b, o)[0]; o += 4
    M = np.frombuffer(b, dtype=np.uint8, count=W * W, offset=o).reshape(W, W) > 127
    cell = 2 * half / W
    iz, ix = np.nonzero(M)
    lx = (ix + 0.5) * cell - half; lz = (iz + 0.5) * cell - half
    r = np.hypot(lx, lz)
    return {"W": int(W), "Half": float(half), "cells": int(M.sum()), "area_ha": round(float(M.sum() * cell * cell / 1e4), 2),
            "r_max": round(float(r.max() + cell / 2), 1), "lx": lx, "lz": lz, "cell": cell}


def to_world(lx, lz, cx, cz, yaw):
    """IconicDistrict: world = org + Euler(0, yaw, 0) · (lx, 0, lz)."""
    a = math.radians(yaw)
    return cx + lx * math.cos(a) + lz * math.sin(a), cz - lx * math.sin(a) + lz * math.cos(a)


def roads_by(D, pred):
    rg, rp = D["roads"]
    return [g for g, p in zip(rg, rp) if pred(p)]


def ref_has(p, r):
    return p.get("class") == "motorway" and p.get("ref") and r in p["ref"]


def chain(lines, simplify=25.0):
    m = linemerge(unary_union(lines))
    parts = sorted(getattr(m, "geoms", [m]), key=lambda q: -q.length)
    return parts[0].simplify(simplify)


def rc(coords):
    return [[int(round(x)), int(round(z))] for x, z in coords]


# ------------------------------------------------------------------ constraints
def constraints(D):
    bg, _ = D["buildings"]
    near = bg[shapely.intersects(G.buffer(300), bg)]
    houses = list(near) + [h for h in D["twin_existing"] if h.intersects(G.buffer(300))]
    # village = clusters of ≥ 15 existing buildings (each buffered 45 m); the rest are single existing buildings
    hb = unary_union([h.buffer(45) for h in houses]).buffer(-15)
    tree = shapely.STRtree(houses)
    vill = []
    for part in getattr(hb, "geoms", [hb]):
        n = len(tree.query(part, predicate="intersects"))
        if n >= 15:
            vill.append(part)
    V = unary_union(vill).buffer(25).buffer(-25)
    wg, wp = D["water"]
    wat = unary_union([g if g.geom_type in ("Polygon", "MultiPolygon") else g.buffer(4) for g in wg])
    ig, ip = D["infrastructure"]
    hv = [g for g, p in zip(ig, ip) if p.get("class") in ("power_line", "minor_line")]
    mw = unary_union(roads_by(D, lambda p: p.get("class") in ("motorway", "trunk")))
    return {"houses": houses, "tree": tree, "V": V, "water": wat, "hv": hv, "mw": mw}


# ------------------------------------------------------------------ axes (skeleton) — design
def design_axes(D, C):
    a3 = chain(roads_by(D, lambda p: ref_has(p, "KAZ08")), 30).intersection(G.buffer(400))
    bakad = chain(roads_by(D, lambda p: ref_has(p, "KZ02-01") and "KAZ08" not in p["ref"]), 30).intersection(G.buffer(400))
    k6 = linemerge(unary_union(roads_by(D, lambda p: p.get("class") == "motorway" and p.get("ref") and "KAZ06" in p["ref"]
                                         and "KAZ08" not in p["ref"])))
    kaz06 = min(getattr(k6, "geoms", [k6]), key=lambda q: q.distance(Point(-1180, -17580))).simplify(30).intersection(G.buffer(600))
    ter = roads_by(D, lambda p: p.get("class") in ("tertiary", "secondary") and True)
    tm = linemerge(unary_union([g for g in ter if g.intersects(G.buffer(300))]))
    tparts = sorted(getattr(tm, "geoms", [tm]), key=lambda q: -q.length)

    def pick(pt):
        return min(tparts, key=lambda q: q.distance(Point(pt))).simplify(25)
    village_spine = pick((-4496, -16540))     # Жаңадәуір – Қоянқұс village road over BAKAD (existing overpass)
    yntymak_rd = pick((-3801, -21577))        # Ынтымақ road to A-3
    road17 = pick((-6833, -25100))            # road «17» along the west edge

    def longest(g):
        return max(getattr(g, "geoms", [g]), key=lambda q: q.length)
    ax = []

    def A(id_, cls, name, line, status, years, why):
        ax.append({"id": id_, "class": cls, "name_ru": name, "line": rc(line), "status": status, "years": years, "why": why})
    A("ax_a3", "expressway", "Трасса А-3 Алматы – Қонаев (KAZ08)", longest(a3).coords, "keep_existing", [2025, 2025],
      "существует (OSM); главная ось север–юг, узлы только в разных уровнях; в Gate — 3 развязки (км 18,5, БАКАД, Ынтымақ–Жанадаур)")
    A("ax_bakad", "expressway", "БАКАД (1-е полукольцо)", longest(bakad).coords, "keep_existing", [2025, 2025],
      "существует (OSM, 2023); делит Gate на северный массив и сёла юга; новый узел-«труба» у Западного проспекта, ≥ 1,6 км от соседних")
    A("ax_a19", "expressway", "А-19/KAZ06 Алматы – Хоргос", longest(kaz06).coords, "keep_existing", [2025, 2025],
      "существует (OSM); уходит на северо-восток от развязки Ынтымақ–Жанадаур")
    A("ax_village_spine", "district", "Сельская ось Жаңадәуір – Қоянқұс (путепровод над БАКАД)", village_spine.coords, "keep_existing",
      [2025, 2025], "существующая улица сёл (OSM tertiary); остаётся главной улицей сёл, получает тротуары; новые оси её не режут")
    A("ax_yntymak_rd", "district", "Улица Ынтымақ – А-3", yntymak_rd.coords, "keep_existing", [2025, 2025],
      "существующая улица (OSM tertiary): связь Ынтымақа с А-3 и с Проспектом Gate City")
    A("ax_road17", "arterial", "Дорога «17» вдоль западной границы", longest(road17.intersection(G.buffer(200))).coords, "keep_existing",
      [2025, 2025], "существующая (OSM secondary); обслуживает западную полосу малоэтажной застройки")
    ix, iz = ICONIC
    A("ax_avenue", "arterial", "Проспект Ворот (бульвар к Iconic)", [(-2128, -19503), (-2330, -19500), (ix + QT_R, iz)], "new", [2026, 2028],
      "церемониальная ось: от стыка J013/J014 (путепровод над А-3) прямо на фасад площади Iconic; на ней станция ЛРТ «Iconic»; "
      "первая улица 4D-очереди 1, раньше домов")
    A("ax_avenue_w", "district", "Проспект Ворот (западный отрезок)", [(ix - QT_R, iz), (-3990, iz)], "new", [2028, 2030],
      "продолжение оси за кольцом Gate District до Западного проспекта и села Жаңадәуір")
    A("ax_west", "arterial", "Западный проспект (вдоль края Жаңадәуір)",
      [(-3990, -19950), (-3990, -18900), (-3800, -18520), (-3330, -18120), (-3290, -17300), (-3330, -16600)], "new", [2029, 2033],
      "магистраль ≈ в 100 м от домов Жаңадәуір: даёт селу новую фасадную улицу и зелёный буфер; на юге — узел-«труба» на БАКАД "
      "(все съезды на северной стороне, Ынтымақ не трогаем)")
    A("ax_dubler_n", "district", "Дублёр А-3 (север)", [(-2560, -19980), (-2330, -19760), (-2330, -19000), (-2260, -18450), (-2230, -17300), (-2240, -16450)],
      "new", [2026, 2027],
      "дорога-дублёр генплана вдоль А-3 в Gate: подъезд грузовиков Griffin и офисов полосы А-3 с узлов, не через центр; "
      "заменяет новую развязку (между узлами 2 км, чаще 1,6 км нельзя)")
    A("ax_north", "arterial", "Северная улица (от развязки Ынтымақ–Жанадаур)", [(-2090, -18400), (-2260, -18450), (-3800, -18520)], "new",
      [2030, 2032], "второй вход с А-3 через существующую развязку; шаг магистралей ≈ 1 км (норма 800–1000 м)")
    A("ax_esentai", "district", "Улица Есентай", [(-3290, -17300), (-2230, -17300)], "new", [2036, 2038],
      "районная улица северной части, у станции ЛРТ «Есентай» и больницы")
    A("ax_bakad_st", "district", "Улица вдоль БАКАД", [(-3990, -19880), (-3100, -19960), (-2560, -19980)], "new", [2027, 2029],
      "южная граница Сити: за ней парк-шумозащита БАКАД (в нём же новая трасса ВЛ)")
    A("ax_boulevard", "boulevard", "Бульвар Gate (Iconic – Центральный парк)", [(ix, iz + QT_R), (ix, -18520)], "new", [2029, 2031],
      "пешеходная ось с бульваром: от северного входа кольца Gate District к Центральному парку и Северной улице")
    A("ax_tpu", "district", "Восточная улица (ТПУ – Ынтымақ – Gate City)",
      [(-3100, -19500), (-3010, -19950), (-2960, -20200), (-2930, -20480), (-2960, -21000), (-3020, -21600), (-3110, -22000),
       (-3330, -22200), (-3520, -22560), (-3700, -22850), (-3950, -23250)], "new", [2027, 2031],
      "вторая связь через БАКАД (в проёме между Ынтымақ и Есентаем, вместе с ЛРТ): Сити – ТПУ – станции юга – админцентр")
    A("ax_gatecity", "arterial", "Проспект Gate City (юг)",
      [(-5050, -20640), (-4760, -21100), (-4700, -22000), (-4600, -22850), (-4300, -23250), (-3950, -23300), (-3800, -23550), (-3790, -23760),
       (-3700, -23915), (-3300, -23915), (-3245, -23790)],
      "new", [2031, 2035],
      "N–S ось юга между сёлами (не через дома) от сельской оси у путепровода над БАКАД к админцентру и развязке А-3 км 18,5")
    A("ax_ped_bridge", "pedestrian", "Пешеходный мост над БАКАД (Сити – Ынтымақ)", [(-3400, -19840), (-3400, -20160)], "new", [2032, 2033],
      "селу Ынтымақ — 10 минут пешком до Iconic, не через узел; мост, а не переход в уровне")
    lrt = [(-2571, -15712), (-2720, -16200), (-2830, -16500), (-2980, -17000), (-3060, -17600), (-3100, -18200), (-3100, -19500),
           (-3030, -19900), (-2975, -20150), (-2930, -20480), (-2955, -21000), (-3030, -21600), (-3110, -21950), (-3300, -22450),
           (-3480, -22720), (-3750, -23080), (-4000, -23420), (-4180, -23700), (-4300, -23950), (-4380, -24180)]
    A("ax_lrt", "lrt_corridor", "ЛРТ, ствол Gate – Golden", lrt, "new", [2028, 2031],
      "ствол ЛРТ через ТПУ у А-3 × БАКАД и центр (станция «Iconic» в 400 м к востоку от башни, как в модели QTwin: линия к востоку от комплекса); "
      "стык J001 с Golden; конец — депо у станции «Gate City-Юг»")
    A("ax_metro3", "lrt_corridor", "Резерв 3-й линии метро Алматы (решение не принято)", [(-4174, -25054), (-3576, -24287)], "new", [2050, 2050],
      "трасса OSM «Future Almaty Metro Line 3» между стыками J007 и J006; только резерв коридора (в 05.2026 продление не планируется)")
    return ax, {"a3": longest(a3), "bakad": longest(bakad), "kaz06": longest(kaz06)}


LRT_STATIONS = [
    ("st_bestereк", "Бестерек", (-2830, -16500)),
    ("st_esentai", "Есентай", (-3060, -17600)),
    ("st_park", "Центральный парк", (-3100, -18560)),
    ("st_iconic", "Iconic", (-3100, -19500)),
    ("st_tpu", "ТПУ Gate (А-3 × БАКАД)", (-2930, -20480)),
    ("st_yntymak", "Ынтымақ", (-3030, -21600)),
    ("st_gatecity", "Gate City", (-3480, -22720)),
    ("st_admin", "Административный центр", (-4000, -23420)),
    ("st_south", "Gate City-Юг (конечная, депо)", (-4380, -24180)),
]

CENTRES = [
    ("c_iconic", "main", "Центр Gate · Iconic", ICONIC,
     "центр будущих жителей Gate лежит на БАКАД у x ≈ −3900; ближайшее место, где квартал Gate District (r 335 м) встаёт на свободную землю "
     "с буфером до сёл и трассы, — северная сторона этого узла; сюда сходятся ЛРТ, Проспект Ворот, Бульвар Gate и Западный проспект"),
    ("c_tpu", "sub", "ТПУ Gate (А-3 × БАКАД)", (-2930, -20480),
     "пересадка ЛРТ / агломерационная ж/д (станция генплана у А-3 × БАКАД к 2030) / автобусы; въезд с трасс без захода в центр"),
    ("c_admin", "sub", "Административный центр · Gate City", (-4000, -23300),
     "генплан: новый административный центр города в Gate City (точность 1 км); станция ЛРТ, сквер, акимат рядом"),
    ("c_north", "local", "Северный центр · Есентай", (-2950, -17600), "центр северной жилой части у станции ЛРТ и больницы"),
    ("c_yntymak", "local", "Центр у станции Ынтымақ", (-3030, -21600), "магазины, поликлиника и сад для Ынтымақа у станции ЛРТ"),
    ("c_koyankus", "local", "Центр Қоянқұс", (-5750, -23250), "сельский центр у сельской оси: акимат, школа, спорткомплекс (по реестру)"),
]


# ------------------------------------------------------------------ zones — design (priority order: first wins)
def design_zones(C, ax_geo):
    ix, iz = ICONIC
    Z = []

    def add(id_, use, geom, name, density, years, why):
        Z.append({"id": id_, "use": use, "geom": geom, "name_ru": name, "density": density, "years": years, "why": why})
    # 1 existing villages (built footprint, not the administrative outline)
    S = {p["name"]: g for g, p in zip(*C["settle"])}
    V = C["V"].intersection(G)
    names = [("Жаңадәуір", "Жаңадәуір"), ("Ынтымақ", "Ынтымақ"), ("Қоянқұс", "Қоянқұс"), ("Гейт Сити", "Gate City")]
    parts = {}
    for p in getattr(V, "geoms", [V]):
        if p.area < 3e3:
            continue
        nm = min(names, key=lambda n: S[n[0]].distance(p.representative_point()))[1]
        parts.setdefault(nm, []).append(p)
    for nm, ps in parts.items():
        add("v_" + {"Жаңадәуір": "zhanadaur", "Ынтымақ": "yntymak", "Қоянқұс": "koyankus", "Gate City": "gatecity_w"}[nm], "village_existing",
            unary_union(ps), f"Село {nm} (существующее)", {"floors_typical": 1, "far": 0.25}, [2025, 2025],
            "существующие дома (OSM + existing_osm двойника) остаются; свои улицы — на уровне 1; новые оси обходят")
    # 2 rivers and ponds with the 35 m water-protection strip
    add("p_water", "park", C["water"].buffer(35).intersection(G), "Реки, пруды и водоохранная полоса 35 м", {}, [2025, 2030],
        "Есентай, Бестерек-Карасу, Правый Есентай и пруды: без зданий, бульвары и велодорожки по берегам")
    # 3 motorway corridors and interchanges
    corr = unary_union([C["mw"].buffer(45), Point(-2255, -20323).buffer(430), Point(-2052, -18339).buffer(240), Point(-3240, -23783).buffer(210),
                        Point(-3990, -19990).buffer(170)])
    add("u_motorways", "utility", corr.intersection(G), "Коридоры А-3, БАКАД, А-19 и развязки", {}, [2025, 2033],
        "проезжая часть, откосы, съезды; новый узел-«труба» БАКАД × Западный проспект (x ≈ −3990)")
    # 4 the Gate District quarter (QTwin) round Iconic
    add("z_gate_district", "mixed_centre", Point(ix, iz).buffer(QT_R, 64), "Gate District (QTwin) с Iconic Complex",
        {"floors_typical": 9, "far": 2.6}, [2026, 2032],
        "квартал QTwin переносится с Iconic целиком (сохранить); 4D: кольцо и радиальные улицы 2026–27, Iconic 2026–30, полумесяц 2028–31, дворы 2030–32")
    # 5 HV lines (south pair stays; the north line moves into the BAKAD park)
    hv_south = unary_union([h for h in C["hv"] if h.intersects(box(-8000, -27300, -1500, -20300)) and h.length > 3000]).buffer(30)
    add("u_hv_south", "utility", hv_south.intersection(G).difference(box(-9000, -20250, 0, -15000)), "Коридор двух ВЛ (луг, велодорожка)", {},
        [2025, 2025], "охранная зона существующих ВЛ (OSM): без зданий и деревьев; дороги пересекают поперёк")
    # 6 hand-drawn zones
    bk = ax_geo["bakad"]
    bakad_park = bk.buffer(190).difference(bk.buffer(45)).intersection(box(-4300, -20400, -2560, -19600)).intersection(
        box(-4300, -19990, -2560, -19600).union(Polygon([(-4300, -19990), (-2560, -20160), (-2560, -19600), (-4300, -19600)])))
    add("p_bakad", "park", bakad_park, "Парк-шумозащита вдоль БАКАД (с новой трассой ВЛ)", {}, [2027, 2030],
        "150 м между трассой и Сити: шум, ветер, новая трасса ВЛ из центра; деревья только вне её охранной зоны")
    add("l_griffin", "logistics", box(-2650, -19280, -2150, -18760), "Griffin Logopark (класс А)", {"floors_typical": 1, "far": 0.5, "jobs_per_ha": 45},
        [2026, 2027], "по источнику: 1,0 км до БАКАД и 0,6 км до развязки (±0,5 км), у А-3; грузовики только по дублёру с узлов; "
        "от жилья ≥ 300 м (СЗЗ класс V — 50 м)")
    add("b_a3_strip", "business", box(-2900, -20000, -2150, -19280), "Ворота А-3: офисы, отели, выставочный зал",
        {"floors_typical": 12, "far": 2.6}, [2027, 2033], "фасад города к трассе; буфер между логистикой и жильём")
    add("b_cbd", "business", box(-3990, -19900, -2900, -18900), "Сити Gate: башни вдоль Проспекта Ворот и ЛРТ",
        {"floors_typical": 20, "far": 4.0}, [2027, 2036],
        "самая плотная застройка района — у станции «Iconic» и площади; подземные паркинги (правило 17)")
    add("p_central", "park", box(-3720, -18900, -3290, -18520), "Центральный парк Gate (≈ 16 га)", {}, [2030, 2032],
        "районный парк ≥ 10 га в 10 минутах от всех кварталов севера; конец Бульвара Gate")
    add("m_hospital", "medical", box(-2650, -18300, -2250, -17900), "Больница Gate 500 коек и поликлиника", {"floors_typical": 6, "far": 0.9, "jobs_per_ha": 110},
        [2030, 2033], "генплан: 1-я очередь — больницы по 500 коек в Gate и Golden; у развязки (скорая) и станции ЛРТ")
    add("b_datahub", "business", box(-2700, -17100, -2150, -16420), "Технопарк и ЦОД Alatau Data Hub", {"floors_typical": 5, "far": 1.0},
        [2027, 2034], "ЦОД двойника остаётся на месте (модель), вокруг — технопарк у дублёра А-3")
    add("r_high_n", "residential_high", box(-3990, -18900, -2650, -17800), "Жильё у станции «Центральный парк» (высокое)",
        {"floors_typical": 12, "far": 1.3, "homes_per_ha": 260, "jobs_per_ha": 40}, [2031, 2038], "в 500 м от ЛРТ — 12–16 этажей, кварталы 120–150 м")
    add("w_north", "waterfront", box(-4600, -16500, -2150, -15500), "Набережная Есентай – Бестерек-Карасу", {"floors_typical": 5, "far": 0.35},
        [2040, 2046], "прогулочный берег северной границы; 4–6 этажей, кафе, пляжи у прудов")
    add("r_mid_n", "residential_mid", box(-3800, -17800, -2150, -16420), "Жильё севера (среднеэтажное)", {"floors_typical": 7, "far": 0.6},
        [2036, 2043], "6–9 этажей, дворы, школы и сады по радиусам")
    add("s_aquapark", "sport", box(-2100, -18400, -1600, -17880), "Аквапарк (существует) и спортпарк", {"jobs_per_ha": 10}, [2025, 2035],
        "существующий аквапарк (OSM) на восточной стороне А-3 + спортивные поля")
    add("b_ne", "business", box(-2100, -17880, -700, -16800), "Технопарк Gate-Северо-Восток (за А-3)", {"floors_typical": 6, "far": 1.2},
        [2040, 2048], "клин между А-3 и А-19: под жильё шумно, под офисы и лаборатории — удобно")
    add("x_ne", "reserve", box(-2100, -17880, 300, -15400), "Резерв за А-19 (после 2050; сейчас поля)", {}, [2050, 2050],
        "земля между двумя трассами: цель 2050 г. достигается без неё; держим под технопарк следующего этапа")
    add("l_se", "logistics", box(-2420, -22200, -900, -20400), "Логистика Gate-Восток (за А-3, у БАКАД)", {"floors_typical": 1, "far": 0.45, "jobs_per_ha": 40},
        [2036, 2042], "у промзоны Покровка и JTI; въезд с БАКАД, к жилью ветер не несёт (жильё к востоку и северо-востоку от складов не стоит)")
    add("b_tpu", "business", box(-3120, -20800, -2650, -20200), "ТПУ Gate: вокзал, автостанция, офисы", {"floors_typical": 10, "far": 2.0},
        [2028, 2031], "станция агломерационной ж/д (генплан, к 2030) и ЛРТ; многоуровневый паркинг вместо полей")
    add("r_high_y", "residential_high", box(-3120, -22000, -2700, -20800), "Кварталы у станции Ынтымақ", {"floors_typical": 9, "far": 1.2},
        [2032, 2037], "узкая полоса между селом и Есентаем вдоль ЛРТ")
    pep = Polygon([(-3330, -22760), (-3100, -22830), (-2780, -22420), (-2900, -22150), (-3150, -22250)])
    add("i_pepsico", "industry", pep.union(box(-3420, -23060, -3060, -22760)), "Завод PepsiCo и тепличный комплекс (существуют)",
        {"floors_typical": 1, "far": 0.35, "jobs_per_ha": 35}, [2025, 2027],
        "корпус OSM 28 043 м² у А-3 = застройка PepsiCo 28 000 м² (вывод по площади, мкр Ынтымақ ±1 км); СЗЗ 100 м, жилья к западу-юго-западу нет")
    add("p_gatecity_park", "park", box(-4750, -22800, -3550, -22330), "Парк Gate (между Gate City и Ынтымақом, городской)", {}, [2031, 2034],
        "парковая зона из эскиза Vlast.kz 2025 «между Gate City и Ынтымаком»")
    add("c_admin", "mixed_centre", box(-4400, -23620, -3700, -23000), "Административный центр города (Gate City)",
        {"floors_typical": 8, "far": 1.5}, [2031, 2038],
        "генплан: новый административный центр в Gate City; площадь, станция ЛРТ «Административный центр»")
    add("r_gatecity", "residential_mid", box(-3700, -23850, -3260, -23200), "ЖК Gate City (существует) и его новые кварталы",
        {"floors_typical": 9, "far": 0.9}, [2025, 2034], "построенный ЖК со школой № 20 остаётся; рядом — его очереди")
    add("u_gatecity", "utility", box(-3950, -24300, -3550, -23950), "Инженерный узел Gate City (ПС «Кокпа-1», котельная, КНС, АГРС, водозабор)", {},
        [2025, 2028], "объекты реестра «у Gate City» (точность 1 км) собраны в один узел у А-3, подальше от жилья")
    add("u_depot", "utility", box(-4950, -24520, -4600, -24220), "Депо ЛРТ", {}, [2029, 2031], "конец линии — депо (правило 25), у конечной «Gate City-Юг»")
    add("s_south", "sport", box(-5250, -22350, -4800, -21900), "Спортпарк Gate (стадион, бассейн)", {"jobs_per_ha": 10}, [2034, 2037],
        "спорт для юга и сёл, у Проспекта Gate City")
    add("r_high_s", "residential_high", box(-4600, -24000, -3700, -22800), "Жильё вокруг админцентра (высокое)", {"floors_typical": 12, "far": 1.3},
        [2033, 2040], "у двух станций ЛРТ юга")
    add("x_west", "reserve", box(-8000, -27400, -6350, -18000), "Резерв западной полосы (после 2050; сейчас поля)", {},
        [2050, 2050], "за сельской полосой, далеко от ЛРТ: цель 2050 г. достигается компактным городом у осей, полоса остаётся резервом")
    add("x_nw", "reserve", box(-6400, -18300, -3990, -15500), "Резерв северо-запада у прудов (после 2050)", {},
        [2050, 2050], "за селом Жаңадәуір, вдали от ЛРТ: цель 2050 г. достигается без неё; пока поля и прогулочные берега")
    add("r_low_wb", "residential_low", box(-6400, -20300, -3990, -18300), "Кварталы между Жаңадәуір и БАКАД (малоэтажные)", {"floors_typical": 4, "far": 0.3},
        [2036, 2044], "рядом с селом — 3–5 этажей, у Западного проспекта и сельской оси")
    add("r_mid_n2", "residential_mid", box(-4000, -18900, -3300, -16420), "Кварталы у края Жаңадәуір", {"floors_typical": 6, "far": 0.6},
        [2036, 2042], "переход от Сити к селу: 5–7 этажей")
    add("r_mid_s", "residential_mid", box(-5300, -24350, -2000, -20200), "Новые кварталы юга (среднеэтажные)", {"floors_typical": 6, "far": 0.6},
        [2036, 2046], "между сёлами и А-3, вдоль Проспекта Gate City и ЛРТ")
    add("x_south", "reserve", box(-8000, -27400, -2000, -20200), "Резерв юга (после 2050; коридор метро)", {}, [2050, 2050],
        "южный край у резерва метро и границы с Алматы: после 2050 или по решению о метро")
    add("r_mid_rest", "residential_mid", G, "Прочие новые кварталы (среднеэтажные)", {"floors_typical": 6, "far": 0.6},
        [2038, 2046], "остаток свободной земли")
    return Z


def build_coverage(Z):
    """First wins on a 1 m grid (exact coverage, integer vertices); inputs pre-simplified (villages grown 8 m first, so
    the simplified outline still holds every house); slivers merge into the neighbour with the longest shared edge; holes cut."""
    GS = 1.0
    rem = shapely.set_precision(G, GS)
    pieces = []
    for z in Z:
        src = z["geom"]
        src = src.buffer(8, quad_segs=4).simplify(6) if z["use"] == "village_existing" else src.simplify(6)
        src = shapely.make_valid(src)
        src = unary_union([q for q in getattr(src, "geoms", [src]) if q.geom_type in ("Polygon", "MultiPolygon")])
        g = shapely.intersection(src, rem, grid_size=GS)
        g = unary_union([q for q in getattr(g, "geoms", [g]) if q.geom_type in ("Polygon", "MultiPolygon")])
        if g.is_empty:
            continue
        rem = shapely.difference(rem, g, grid_size=GS)
        rem = unary_union([q for q in getattr(rem, "geoms", [rem]) if q.geom_type in ("Polygon", "MultiPolygon")])
        for p in getattr(g, "geoms", [g]):
            if p.geom_type == "Polygon" and p.area > 1:
                pieces.append([z, p])
    for p in getattr(rem, "geoms", [rem]):          # whatever the grid left over goes to the last zone
        if p.geom_type == "Polygon" and p.area > 1:
            pieces.append([Z[-1], p])
    changed = True
    while changed:
        changed = False
        pieces.sort(key=lambda t: t[1].area)
        for i, (z, p) in enumerate(pieces):
            if p.area >= 3e4 or z["use"] == "village_existing" and p.area >= 2e3:
                continue
            best, bl = None, 0.0
            for j, (z2, p2) in enumerate(pieces):
                if j == i or p.distance(p2) > 0.01:
                    continue
                l = shapely.intersection(p.boundary, p2.boundary, grid_size=GS).length
                if l > bl:
                    best, bl = j, l
            if best is not None:
                u = shapely.union(pieces[best][1], p, grid_size=GS)
                if u.geom_type != "Polygon":
                    continue
                pieces[best][1] = u
                pieces.pop(i)
                changed = True
                break

    def cut(p):
        if not p.interiors:
            return [p]
        h = Polygon(p.interiors[0]).representative_point()
        x0, z0, x1, z1 = p.bounds
        out = []
        for bb in (box(x0 - 1, z0 - 1, round(h.x), z1 + 1), box(round(h.x), z0 - 1, x1 + 1, z1 + 1)):
            q = shapely.intersection(p, bb, grid_size=GS)
            for r in getattr(q, "geoms", [q]):
                if r.geom_type == "Polygon" and r.area > 1:
                    out += cut(r)
        return out
    flat = []
    for z, p in pieces:
        for q in cut(p):
            flat.append((z, q))
    # one planar partition: node every edge on the 1 m grid, polygonize, give each face to the piece it lies in
    lines = shapely.union_all([q.boundary for _, q in flat] + [G.boundary], grid_size=GS)
    faces = [f for f in shapely.get_parts(shapely.polygonize(shapely.get_parts(lines))) if f.area > 0.5]
    tree = shapely.STRtree([q for _, q in flat])
    own = {}
    for f in faces:
        rp = f.representative_point()
        if not G.contains(rp):
            continue
        cand = tree.query(f, predicate="intersects")
        best = max(cand, key=lambda i: flat[i][1].intersection(f).area) if len(cand) else tree.nearest(rp)
        own.setdefault(int(best), []).append(f)
    flat2 = []
    for i, (z, _) in enumerate(flat):
        if i not in own:
            continue
        u = shapely.union_all(own[i])
        for q in sorted(getattr(u, "geoms", [u]), key=lambda q: -q.area):
            if q.geom_type == "Polygon" and q.area > 1:
                flat2 += [(z, r) for r in cut(q)]
    flat = flat2
    count = {}
    for z, _ in flat:
        count[z["id"]] = count.get(z["id"], 0) + 1
    res, k = [], {}
    for z, g in flat:
        k[z["id"]] = k.get(z["id"], 0) + 1
        zid = z["id"] if count[z["id"]] == 1 else f"{z['id']}_{k[z['id']]}"
        ring = rc(shapely.remove_repeated_points(g).exterior.coords[:-1])
        res.append({"id": zid, "use": z["use"], "name_ru": z["name_ru"], "polygon": ring, "density": dict(z["density"]),
                    "years": z["years"], "why": z["why"], "_g": Polygon(ring), "_base": z["id"]})
    return res


# ------------------------------------------------------------------ objects of the registry
MOVES = {"pepsico", "griffin_logopark"}
OBJ_PLACE = {   # id: (action, to, yaw, why) — the cartographer's placement; None = registry point as is
    "iconic_complex": ("move", ICONIC, ICONIC_YAW, "решение владельца: Iconic в центре Gate; центр = север узла БАКАД (см. кандидаты); квартал QTwin, площадь, флаги и камеры едут вместе"),
    "iconic_tower_main": ("move", ICONIC, ICONIC_YAW, "часть Iconic, едет вместе с комплексом"),
    "iconic_tower_second": ("move", ICONIC, ICONIC_YAW, "часть Iconic, едет вместе с комплексом"),
    "iconic_podium": ("move", ICONIC, ICONIC_YAW, "часть Iconic, едет вместе с комплексом"),
    "iconic_offices_6": ("move", ICONIC, ICONIC_YAW, "часть Iconic (модель BIM), едет вместе с комплексом"),
    "iconic_greenery": ("move", ICONIC, ICONIC_YAW, "площадь и сад Iconic (IconicPlaza, 4 флагштока) едут вместе с комплексом"),
    "gate_district_ring": ("move", ICONIC, ICONIC_YAW, "квартал QTwin в локальной системе Iconic: смещение без поворота (yaw 270 сохранён); вся маска r 335 м на свободной земле"),
    "gateway_district_som": ("by_rule", ICONIC, None, "мастер-план SOM — весь Gate; центр — Iconic"),
    "intl_business_centre": ("by_rule", (-3300, -19780), None, "место в источниках не дано; ставим в Сити у станции «Iconic»"),
    "l7_lotte": ("move", (-2960, -19640), 0.0, "источник места не даёт (модель); городскому отелю место у площади Iconic и станции ЛРТ, а не у развязки рядом со складами"),
    "griffin_logopark": ("move", (-2420, -19020), 0.0, "по источнику: у А-3, 1,0 км до БАКАД, 0,6 км до развязки (±0,5 км, 0,1 км от точки реестра); в зоне логистики у дублёра, грузовики с узлов, до жилья ≥ 300 м"),
    "pepsico": ("move", (-3079, -22541), -74.0, "по источнику — мкр Ынтымақ (±1 км); корпус OSM 28 043 м² (347 × 82 м) у А-3 совпадает с застройкой завода 28 000 м² — ставим на него (вывод, имени в OSM нет); точка реестра (центр села) стояла на домах"),
    "school_gate_city_20_keleshek": ("add", (-3558, -23583), None, "здание OSM класса «школа» 4 802 м² в ЖК Gate City"),
    "school_koyankus_old": ("add", (-5590, -23797), None, "ближайший к точке села участок школы OSM (вывод, ±1 км)"),
    "kindergarten_gate_city_280": ("add", (-3420, -23380), None, "в ЖК Gate City (±1 км)"),
    "gate_city_business": ("by_rule", (-4150, -23150), None, "в административном центре"),
    "admin_centre_new": ("add", (-4000, -23300), None, "генплан: Gate City (±1 км); центр зоны админцентра"),
    "gate_city_social_set": ("by_rule", (-4250, -23500), None, "соцобъекты квартала — у админцентра, точные места на уровне 1 по радиусам"),
    "gate_city_project_2021": ("by_rule", (-3900, -23300), None, "проект 2021 = Gate City; центр — админцентр"),
    "bi_group_plot": ("by_rule", (-4300, -23800), None, "участок не опубликован; в кварталах у админцентра"),
    "gate_city_new_quarters": ("by_rule", (-4150, -23800), None, "новые кварталы Gate City — жильё вокруг админцентра"),
    "rent_to_own_koyankus": ("by_rule", (-5000, -23300), None, "у Қоянқұс, но на свободной земле, не на домах села"),
    "hospitals_stage1": ("by_rule", (-2450, -18100), None, "генплан: 500 коек в Gate в 1-й очереди; зона «Больница Gate»"),
    "polyclinic_250": ("by_rule", (-5050, -22600), None, "часть «Коянкус»: у сельского центра на свободной земле; часть «Жетыген» — в Growing"),
    "sport_complex_koyankus": ("add", (-5025, -22125), None, "в Спортпарке Gate у Қоянқұс (±1 км)"),
    "park_gate_city_yntymak": ("add", (-3925, -22575), None, "зона «Парк между Gate City и Ынтымаком»"),
    "agglo_rail_station_1": ("add", (-2930, -20480), None, "генплан: у А-3 × БАКАД (±1 км, 0,7 км от точки реестра — она внутри клеверной развязки); ТПУ с ЛРТ"),
    "metro_line3_reserve": ("add", (-3900, -24700), None, "резерв станции на трассе OSM «Future Almaty Metro Line 3», решение не принято"),
    "a3_dubler": ("by_rule", (-2330, -19000), None, "ось «Дублёр А-3 (север)»"),
    "ps_kokpa_1": ("add", (-3850, -24050), None, "у Gate City (±1 км): инженерный узел у А-3"),
    "water_intake_gate_city": ("move", (-3700, -24050), None, "у Gate City (±1 км); wi_2 двойника стоял в 6 км к северу"),
    "kns_gate_city": ("add", (-3800, -24200), None, "у Gate City (±1 км): инженерный узел"),
    "agrs_gate_city": ("keep", (-3650, -24200), None, "существующая АГРС у Gate City (±1 км); точка в инженерном узле — модель"),
    "boiler_gate_city": ("add", (-3750, -24130), None, "у Gate City (±1 км): инженерный узел"),
    "road_alfarabi_bakad": ("by_rule", None, None, "трасса не опубликована; у южной границы с Алматы — на уровне 3 со стыком"),
}


def registry_rows():
    rows = []
    for r in REG["rows"]:
        g = r.get("geom")
        inside = False
        if g:
            try:
                inside = shape(g).intersects(G)
            except Exception:
                inside = False
        di = (r.get("district_inferred") or "") + " " + (r.get("district") or "")
        geo = r.get("district_geom") or ""
        near_outside = geo.startswith("outside (") and float(geo.split("(")[1].split()[0]) <= 1.5 and "Gate" in geo
        if r["id"] in MOVES or "Gate" in di or (inside and r["type"] not in ("settlement",)) or near_outside or \
                (inside and r["type"] == "settlement" and r.get("district_geom") == "Gate"):
            if r["id"] in ("settlement_zhanatalap",):
                continue
            rows.append(r)
    return rows


def objects():
    out = []
    for r in registry_rows():
        g = r.get("geom")
        frm = None
        if g:
            s = shape(g)
            p = s if s.geom_type == "Point" else s.representative_point()
            frm = [int(round(p.x)), int(round(p.y))]
        twin_from = {"pepsico": [8500, 940], "griffin_logopark": [-5713, 1735], "water_intake_gate_city": [-324, -16461]}.get(r["id"])
        if r["id"] in OBJ_PLACE:
            act, to, yaw, why = OBJ_PLACE[r["id"]]
            to = [int(round(to[0])), int(round(to[1]))] if to else None
        else:
            act = r["action"]["do"]
            to = frm
            yaw = None
            why = r["action"]["reason"]
        if twin_from:
            frm = twin_from
        if r["id"].startswith("iconic") or r["id"] == "gate_district_ring":
            frm = [int(CITY["iconic"]["x"]), int(CITY["iconic"]["z"])]
        out.append({"registry_id": r["id"], "name_ru": r["name_ru"], "action": act, "from": frm, "to": to, "yaw": yaw,
                    "accuracy": r["accuracy"], "why": why})
    return out


# ------------------------------------------------------------------ capacity (twin formulas: residents = housing GFA / 30, jobs = GFA / m² per job)
USE_MIX = {   # residential share of GFA, m² of GFA per job for the rest (CityStats: business 90, social 50, leisure 120, industry 100)
    "mixed_centre": (0.30, 90), "business": (0.10, 90), "residential_high": (0.86, 60), "residential_mid": (0.90, 60),
    "residential_low": (0.95, 60), "waterfront": (0.75, 120)}


def capacity(zones):
    res = jobs = 0.0
    for z in zones:
        a = z["_g"].area / 1e4
        d = z["density"]
        if z["use"] in USE_MIX and "far" in d:
            sh, m2 = USE_MIX[z["use"]]
            gfa = a * d["far"] * 1e4
            r = gfa * sh / 30.0
            j = gfa * (1 - sh) / m2
            d["homes_per_ha"] = int(round(d["far"] * sh * 1e4 / 75.0))
            d["jobs_per_ha"] = int(round(d["far"] * (1 - sh) * 1e4 / m2))
        else:
            r = 0.0
            j = a * d.get("jobs_per_ha", 0)
        z["_res"], z["_jobs"] = r, j
        res += r
        jobs += j
    return res, jobs


# ------------------------------------------------------------------ phases and joints
PHASES = [
    (1, [2026, 2030], "Очередь 1 · Iconic и кольцо Gate District. Сначала улицы: дублёр А-3 и Проспект Ворот (2026–27), кольцо и радиальные "
     "улицы квартала (2026–27), улица вдоль БАКАД (2027–29); затем дома: Iconic (2026–30), полумесяц квартала (2028–31), дворы (2030–32). "
     "Griffin (2026–27) и PepsiCo (существует) — сразу, у дублёра и А-3.",
     ["z_gate_district", "l_griffin", "i_pepsico", "b_a3_strip"], ["ax_dubler_n", "ax_avenue", "ax_bakad_st"]),
    (2, [2028, 2036], "Очередь 2 · ЛРТ, ТПУ и Сити. ЛРТ Gate – Golden и Восточная улица (2027–31), Западный проспект с узлом на БАКАД (2029–33), "
     "Бульвар и Северная улица (2029–32); затем Сити, ТПУ, парк БАКАД, Центральный парк, больница, технопарк у ЦОД, жильё у станций.",
     ["b_cbd", "b_tpu", "p_bakad", "p_central", "m_hospital", "b_datahub", "r_high_n", "r_high_y", "u_depot"],
     ["ax_lrt", "ax_tpu", "ax_west", "ax_boulevard", "ax_avenue_w", "ax_north"]),
    (3, [2031, 2040], "Очередь 3 · Юг: админцентр и Gate City. Проспект Gate City (2031–35) и пешеходный мост над БАКАД; затем "
     "админцентр, кварталы Gate City, парк Gate City – Ынтымақ, спортпарк, инженерный узел, депо ЛРТ.",
     ["c_admin", "r_gatecity", "r_high_s", "p_gatecity_park", "s_south", "u_gatecity"], ["ax_gatecity", "ax_ped_bridge"]),
    (4, [2036, 2046], "Очередь 4 · Север и середина. Улица Есентай (2036–38); затем среднеэтажные кварталы севера и у сёл, кварталы юга, "
     "набережная Есентай, логистика за А-3.",
     ["r_mid_n", "r_mid_n2", "r_low_wb", "r_mid_s", "w_north", "l_se"], ["ax_esentai"]),
    (5, [2040, 2050], "Очередь 5 · Окраины. Технопарк за А-3, остаток кварталов; запад, северо-запад, юг и клин за А-19 — резерв после 2050.",
     ["b_ne", "r_mid_rest", "s_aquapark", "x_ne", "x_west", "x_south", "x_nw"], []),
]

JOINT_AXIS = {"J001": "ax_lrt", "J002": "ax_a3", "J003": "ax_a3", "J004": "ax_a19", "J005": "ax_a19", "J006": "ax_metro3", "J007": "ax_metro3",
              "J008": "ax_a19", "J009": "ax_a19", "J010": "ax_a19", "J011": "ax_a19", "J012": "ax_a3", "J013": "ax_avenue", "J014": "ax_avenue",
              "J015": "ax_bakad", "J016": "ax_bakad", "J017": "ax_bakad", "J018": "ax_bakad", "J019": "ax_bakad", "J020": "ax_bakad",
              "J021": "ax_bakad", "J022": "ax_a3", "J023": "ax_a3", "J024": "ax_a3", "J025": "ax_a3", "J026": "ax_a3"}
HALF_W = {"expressway": 25, "trunk": 25, "arterial": 20, "district": 12, "boulevard": 15, "pedestrian": 3, "lrt_corridor": 6}


# ------------------------------------------------------------------ checks
def checks(D, C, axes, zones, qt, res, jobs, targets):
    out = {}
    houses, tree = C["houses"], C["tree"]
    cents = np.array([(h.representative_point().x, h.representative_point().y) for h in houses])
    inG = shapely.contains_xy(G, cents[:, 0], cents[:, 1])
    vmask = shapely.contains_xy(C["V"], cents[:, 0], cents[:, 1])
    # 1 houses under zones
    zr = {}
    village_out = 0
    for z in zones:
        m = shapely.contains_xy(z["_g"], cents[:, 0], cents[:, 1]) & inG
        if z["use"] != "village_existing":
            nv = int((m & vmask).sum())
            village_out += nv
            if m.sum():
                zr[z["id"]] = {"village_houses": nv, "single_existing_buildings": int((m & ~vmask).sum())}
    out["houses_in_non_village_zones"] = {"village_houses_total": village_out, "by_zone": zr,
                                          "rule": "дом села = здание в группе ≥ 15 существующих (OSM + existing_osm); одиночные существующие здания (теплицы, заводы, ЖК Gate City, фермы) остаются в своих зонах как существующие"}
    # 2 houses under new axes (half-width by class)
    ah = {}
    for a in axes:
        if a["status"] != "new":
            continue
        L = LineString(a["line"]).buffer(HALF_W[a["class"]])
        idx = tree.query(L, predicate="intersects")
        ah[a["id"]] = int(len(idx))
    out["houses_under_new_axes"] = ah
    # 3 water and flood
    wa = {}
    for a in axes:
        if a["status"] != "new":
            continue
        x = LineString(a["line"]).intersection(C["water"])
        n = len(getattr(x, "geoms", [x])) if not x.is_empty else 0
        if n:
            wa[a["id"]] = n
    out["new_axes_crossing_water_bridges"] = wa
    zw = {z["id"]: round(z["_g"].intersection(C["water"]).area / 1e4, 2) for z in zones
          if z["use"] not in ("park", "waterfront", "village_existing", "utility", "reserve") and z["_g"].intersection(C["water"]).area > 100}
    out["water_ha_inside_built_zones"] = zw
    xs = np.arange(G.bounds[0], G.bounds[2], 100.0)
    zs = np.arange(G.bounds[1], G.bounds[3], 100.0)
    X, Zg = np.meshgrid(xs, zs)
    m = shapely.contains_xy(G, X, Zg)
    hmin = float(T.height(X[m], Zg[m]).min())
    out["kapchagay_485"] = {"min_ground_twin_m": round(hmin, 1), "min_ground_real_m": round(hmin + 2, 1), "flooded": hmin + 2 <= 485.0}
    # 4 joints
    jj = []
    for j in CITY["joints"]["items"]:
        if "gate" not in j["between"]:
            continue
        a = next(a for a in axes if a["id"] == JOINT_AXIS[j["id"]])
        d = LineString(a["line"]).distance(Point(j["x"], j["z"]))
        jj.append({"joint": j["id"], "axis": a["id"], "dist_m": round(d, 1)})
    out["joints"] = jj
    # 5 slope
    def slopes(geom, step=25):
        if geom.geom_type == "Polygon":
            x0, z0, x1, z1 = geom.bounds
            X2, Z2 = np.meshgrid(np.arange(x0, x1, step), np.arange(z0, z1, step))
            mm = shapely.contains_xy(geom, X2, Z2)
            return T.slope(X2[mm], Z2[mm]) * 100
        s = np.arange(0, geom.length, step)
        P = np.array([geom.interpolate(v).coords[0] for v in s])
        return T.slope(P[:, 0], P[:, 1]) * 100
    sc = slopes(Point(*ICONIC).buffer(QT_R))
    out["slope_pct"] = {"gate_district_disc": {"max": round(float(sc.max()), 1), "mean": round(float(sc.mean()), 1)}}
    for a in axes:
        if a["status"] == "new":
            s = slopes(LineString(a["line"]))
            out["slope_pct"][a["id"]] = {"max": round(float(s.max()), 1), "p95": round(float(np.percentile(s, 95)), 1)}
    # 6 the QTwin footprint at the new place
    wx, wz = to_world(qt["lx"], qt["lz"], ICONIC[0], ICONIC[1], ICONIC_YAW)
    cells = np.c_[wx, wz]
    hh = tree.query(Point(*ICONIC).buffer(qt["r_max"] + 5), predicate="intersects")
    hc = sum(1 for i in hh if shapely.contains_xy(houses[i].buffer(qt["cell"]), cells[:, 0], cells[:, 1]).any())
    wcell = int(shapely.contains_xy(C["water"], cells[:, 0], cells[:, 1]).sum())
    corr = unary_union([C["mw"].buffer(45), Point(-2255, -20323).buffer(430)])
    icell = int(shapely.contains_xy(corr, cells[:, 0], cells[:, 1]).sum())
    out["gate_district_footprint"] = {"W": qt["W"], "Half_m": qt["Half"], "mask_area_ha": qt["area_ha"], "mask_r_max_m": qt["r_max"],
                                      "new_centre": list(ICONIC), "yaw": ICONIC_YAW, "houses_hit": hc, "water_cells": wcell,
                                      "motorway_or_interchange_cells": icell, "inside_gate": bool(shapely.contains_xy(G, wx, wz).all()),
                                      "min_gap_to_village_house_m": round(Point(*ICONIC).distance(unary_union([houses[i] for i in tree.query(Point(*ICONIC).buffer(1500))])) - qt["r_max"], 0),
                                      "min_gap_to_motorway_axis_m": round(Point(*ICONIC).distance(C["mw"]) - qt["r_max"], 0),
                                      "slope_max_pct": out["slope_pct"]["gate_district_disc"]["max"]}
    # 7 height zones (≥ 50 m)
    hz = list(zip(*D["derived/height_zones"]))
    tall = [("Iconic T1 272 м", ICONIC), ("Iconic T2 80 м", ICONIC), ("L7 by Lotte 100 м (модель)", (-2960, -19640)),
            ("башни Сити до 150 м", (-3400, -19300))]
    out["airfield_height_zones"] = [{"what": n, "zones": sorted(p["id"] for g, p in hz if g.contains(Point(*pt))),
                                     "flag": "нужно согласование"} for n, pt in tall]
    # 8 coverage
    U = unary_union([z["_g"] for z in zones])
    ov = sum(z["_g"].area for z in zones) - U.area
    out["coverage"] = {"zones": len(zones), "district_ha": round(G.area / 1e4, 1), "zones_ha": round(U.area / 1e4, 1),
                       "gap_ha": round(G.difference(U).area / 1e4, 2), "overlap_ha": round(ov / 1e4, 2), "outside_gate_ha": round(U.difference(G).area / 1e4, 2)}
    # 9 shares and capacity
    sh = {}
    for z in zones:
        sh[z["use"]] = sh.get(z["use"], 0) + z["_g"].area / 1e4
    out["zone_share_pct"] = {k: round(100 * v / (G.area / 1e4), 1) for k, v in sorted(sh.items(), key=lambda t: -t[1])}
    out["zone_area_ha"] = {k: round(v, 1) for k, v in sorted(sh.items(), key=lambda t: -t[1])}
    out["capacity"] = {"population_2050": int(round(res, -2)), "jobs_2050": int(round(jobs, -2)),
                       "population_vs_target_pct": round(100 * (res / targets["population_2050"] - 1), 1),
                       "jobs_vs_target_pct": round(100 * (jobs / targets["jobs_2050"] - 1), 1),
                       "plus_real_landmark_jobs": "Griffin 600–1 000, PepsiCo 350–900 (источники реестра; сверх цели, т.к. в buildings.csv их нет)",
                       "village_residents_osm_2025": "≈ 15 700 (OSM population: Жаңадәуір 4 944, Ынтымақ 4 476, Қоянқұс 6 300); двойник, как CityStats, их не считает",
                       "formula": "жители = жилая GFA / 30 м²; рабочие места = нежилая GFA / 90 (офисы), 60 (соцсфера и торговля в жилье), 120 (досуг) или jobs_per_ha"}
    # 10 registry coverage
    return out


def candidates(C, zones, lrt_line):
    """Each candidate: village houses in the quarter (r 335 + 30 m), gap to the motorways, LRT, mean distance to the residents of the
    scheme (zone capacities + village houses × 2,5 чел, модель)."""
    P, W = [], []
    for z in zones:
        if z.get("_res", 0) > 0:
            c = z["_g"].centroid
            P.append((c.x, c.y)); W.append(z["_res"])
    hc = np.array([(h.centroid.x, h.centroid.y) for h in C["houses"]])
    m = shapely.contains_xy(C["V"], hc[:, 0], hc[:, 1]) & shapely.contains_xy(G, hc[:, 0], hc[:, 1])
    P = np.r_[np.array(P), hc[m]]
    W = np.r_[np.array(W), np.full(m.sum(), 2.5)]
    rows = []
    for k, name, (x, z) in CANDIDATES:
        c = Point(x, z)
        nh = len(C["tree"].query(c.buffer(QT_R + 30), predicate="intersects"))
        wat = c.buffer(QT_R).intersection(C["water"]).area
        md = float((np.hypot(P[:, 0] - x, P[:, 1] - z) * W).sum() / W.sum())
        rows.append({"id": k, "name_ru": name, "x": int(round(x)), "z": int(round(z)), "houses_in_quarter": int(nh),
                     "water_m2": int(round(wat)), "gap_to_motorway_m": int(round(c.distance(C["mw"]) - QT_R)),
                     "lrt_m": int(round(c.distance(lrt_line))), "mean_dist_to_residents_m": int(round(md)),
                     "dist_from_today_m": int(round(math.hypot(x - CITY["iconic"]["x"], z - CITY["iconic"]["z"])))})
    return rows


REJECT = {
    "K1": "между БАКАД (410 м) и двумя сёлами: на месте квартала стоят дома Ынтымақ, осям некуда сходиться",
    "K2": "в сёлах юго-запада: на месте квартала — дома, до ЛРТ и трасс далеко",
    "K3": "в 270 м от БАКАД, под ВЛ: шум и охранная зона на месте площади",
    "K4": "на самой БАКАД: туда ставится не башня, а узел (труба + мост), центр — к северу от него",
    "K5": "квартал встаёт, но центр уходит на север от жителей юга; ось ЛРТ у самой А-3",
    "K6": "ещё севернее K5: дальше от сёл и юга, ближе к логистике А-3",
    "K7": "под двумя ВЛ, у теплиц и PepsiCo; вода в круге квартала",
    "K8": "узкая полоса между сёлами: квартал помещается, Сити — нет; далеко от ЛРТ и узла",
}


def build(write=True):
    D = load()
    C = constraints(D)
    C["settle"] = D["derived/settlements"]
    qt = qtwin_mask()
    axes, ax_geo = design_axes(D, C)
    zones = build_coverage(design_zones(C, ax_geo))
    bc = twin.buildings()
    inG = shapely.contains_xy(G, bc.x.values, bc.z.values) & (bc.year.values <= 2050)
    gfa = {u: float(bc[inG & (bc.use == u)].gfa_m2.sum()) for u in ("business", "social", "industry", "energy", "leisure", "housing")}
    jobs_t = gfa["business"] / 90 + gfa["social"] / 50 + (gfa["industry"] + gfa["energy"]) / 100 + gfa["leisure"] / 120
    targets = {"population_2050": 223000, "jobs_2050": int(round(jobs_t)), "homes_2050": None,
               "source": "жители — CityStats.DistrictTarget2050k[0] = 223 тыс. (UnityProject/Assets/Scripts/DigitalTwin/CityStats.cs:13); "
                         "рабочие места — сами здания двойника 2050 г. в полигоне Gate по формулам CityStats (buildings.csv, базовый сценарий: "
                         f"офисы {gfa['business'] / 90:,.0f} + соцсфера {gfa['social'] / 50:,.0f} + досуг {gfa['leisure'] / 120:,.0f} + промышленность "
                         f"{(gfa['industry'] + gfa['energy']) / 100:,.0f}), без масштабирования (правило оркестратора 31.10); для сравнения loads.json → 99 673; "
                         "квартир — нет в коде (в схеме справочно: жилая GFA / 75 м²)".replace(",", " ")}
    res, jobs = capacity(zones)
    lrt_line = LineString(next(a for a in axes if a["id"] == "ax_lrt")["line"])
    ck = checks(D, C, axes, zones, qt, res, jobs, targets)
    ck["iconic_candidates"] = candidates(C, zones, lrt_line)
    for r in ck["iconic_candidates"]:
        r["verdict"] = REJECT.get(r["id"], "выбран")
    objs = objects()
    ck["registry"] = {"rows": len(objs), "by_action": {a: sum(1 for o in objs if o["action"] == a) for a in ("keep", "move", "add", "by_rule", "remove")}}
    # streets before houses
    zy = {z["_base"]: z["years"][0] for z in zones}
    ay = {a["id"]: a["years"][0] for a in axes}
    sb = []
    for q, yrs, _, zs, xs in PHASES:
        zs_new = [z for z in zs if z in zy and zy[z] > 2025]
        if xs and zs_new:
            sb.append({"queue": q, "first_street": min(ay[x] for x in xs), "first_house": min(zy[z] for z in zs_new),
                       "ok": min(ay[x] for x in xs) <= min(zy[z] for z in zs_new)})
    ck["streets_before_houses"] = sb
    ck["open_questions"] = [
        "Iconic ставим в (−3500, −19500), в 0,5 км к юго-западу от нынешнего места: центр будущих жителей Gate лежит на БАКАД, ближе квартал не встаёт. Согласны? (да/нет)",
        "Северную ВЛ, которая сегодня идёт через место Сити, переносим в парк вдоль БАКАД (модель qTwin). Переносим? (да/нет)",
    ]
    spec = {
        "district": "gate", "version": 0, "boundary": "city.json#districts/gate", "targets": targets,
        "centres": [{"id": i, "kind": k, "name_ru": n, "x": int(p[0]), "z": int(p[1]), "why": w} for i, k, n, p, w in CENTRES],
        "axes": axes,
        "zones": [{k: v for k, v in z.items() if not k.startswith("_")} for z in zones],
        "lrt": {"line": next(a for a in axes if a["id"] == "ax_lrt")["line"],
                "stations": [{"id": i, "name_ru": n, "x": int(p[0]), "z": int(p[1])} for i, n, p in LRT_STATIONS],
                "why": "ствол Gate – Golden перерисован через центр: ТПУ у А-3 × БАКАД (пересадка на агломерационную ж/д), станция «Iconic» "
                       "в 400 м к востоку от башни на Проспекте Ворот, на юге — через Ынтымақ и Gate City к депо; шаг станций 0,9–1,3 км; "
                       "на севере стык J001 с Golden; профиль (земля/эстакада) — уровень 1"},
        "objects": objs,
        "phases": [{"queue": q, "years": y, "what_ru": w, "zones": [z for z in zs], "axes": xs} for q, y, w, zs, xs in PHASES],
        "joints": [{"joint_id": j, "axis": a} for j, a in sorted(JOINT_AXIS.items())],
        "checks": ck,
    }
    if write:
        txt = json.dumps(spec, ensure_ascii=False, indent=1)
        # keep coordinate pairs on one line so the file stays hand-editable
        import re
        txt = re.sub(r"\[\n\s+(-?\d+),\n\s+(-?\d+)\n\s+\]", r"[\1, \2]", txt)
        txt = re.sub(r"\[\n\s+(\[-?\d+, -?\d+\](?:,\n\s+\[-?\d+, -?\d+\])*)\n\s+\]",
                     lambda m: "[" + re.sub(r",\n\s+", ", ", m.group(1)) + "]", txt)
        with open(SPEC, "w", encoding="utf-8", newline="\n") as f:
            f.write(txt + "\n")
        print(f"[gate] {SPEC}: {os.path.getsize(SPEC) / 1e3:.0f} kB")
    return spec, D, C, zones, axes, ax_geo


if __name__ == "__main__":
    spec, D, C, zones, axes, ax_geo = build()
    ck = spec["checks"]
    for k in ("houses_in_non_village_zones", "houses_under_new_axes", "new_axes_crossing_water_bridges", "water_ha_inside_built_zones",
              "kapchagay_485", "gate_district_footprint", "coverage", "zone_share_pct", "capacity", "registry", "streets_before_houses", "slope_pct"):
        print(k, json.dumps(ck[k], ensure_ascii=False)[:1500])
    print("joints", [j for j in ck["joints"] if j["dist_m"] > 40])
    for r in ck["iconic_candidates"]:
        print(r)
    if "--no-png" not in sys.argv:
        sys.path.insert(0, HERE)
        import gate_render
        gate_render.render(spec, D, C, zones, axes, ax_geo, OUTDIR)
