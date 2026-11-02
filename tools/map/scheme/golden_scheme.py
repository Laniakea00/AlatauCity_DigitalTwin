"""Golden, level 0: the district scheme (spec + checks + picture + page).

    python3 -I tools/map/scheme/golden_scheme.py            # writes tools/map/spec/golden.json and
                                                            # /mnt/project-files/alatau_stage7/level0/schemes/golden/{scheme.png, scheme.md}

All design decisions are the hand-written data at the top (centres, axes, zone sketches, LRT, objects, phases).
Zones are sketches: each is clipped to the Golden outline of city.json and to the zones above it in ZONE_ORDER,
so the result covers the district without overlaps. Coordinates: Unity X = east, Z = north, metres."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "geo"))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import frames  # noqa: E402
import layers  # noqa: E402
import terrain  # noqa: E402
import twin  # noqa: E402

OUT = os.environ.get("GOLDEN_OUT", "/mnt/project-files/alatau_stage7/level0/schemes/golden")
SPEC = os.path.join(frames.SPEC_DIR, "golden.json")
CITY = json.load(open(os.path.join(frames.SPEC_DIR, "city.json"), encoding="utf-8"))
REG = json.load(open(os.path.join(frames.SPEC_DIR, "registry.json"), encoding="utf-8"))
GOLD = shapely.make_valid(Polygon(CITY["districts"]["golden"]["polygon"]))
GOLD = max(GOLD.geoms, key=lambda g: g.area) if GOLD.geom_type != "Polygon" else GOLD

M2_PER_RESIDENT = 30.0          # CityStats.M2PerResident (twin) = генплан 30 м²/чел. к 2050
M2_PER_HOME = 75.0              # модель qTwin: квартира 75 м² брутто → 2,5 жителя на квартиру
M2_PER_JOB = {"business": 90.0, "social": 50.0, "industry": 100.0, "leisure": 120.0}   # CityStats.M2PerJob


# ------------------------------------------------------------------ helpers
A3 = [(-2110, -16400), (-2120, -15839), (-2128, -14310), (-759, -6034), (-800, -4500), (-882, -3034)]   # registry road_a3, simplified


def a3x(z):
    P = np.array(A3, float)
    o = np.argsort(P[:, 1])
    return float(np.interp(z, P[o, 1], P[o, 0]))


def rect(x0, z0, x1, z1):
    return [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]


def circle(x, z, r, n=36):
    return [[round(x + r * math.cos(2 * math.pi * i / n)), round(z + r * math.sin(2 * math.pi * i / n))] for i in range(n)]


def poly_coords(g, nd=0, simp=25.0):
    """Largest-first list of rings (exterior only) of a (Multi)Polygon, rounded, simplified."""
    g = g.simplify(simp, preserve_topology=True)
    polys = [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and p.area > 2000]
    polys.sort(key=lambda p: -p.area)
    return [[[round(x, nd) if nd else int(round(x)), round(z, nd) if nd else int(round(z))] for x, z in p.exterior.coords[:-1]] for p in polys]


# ------------------------------------------------------------------ the design: centres
CENTRES = [
    {"id": "C1", "kind": "main", "name_ru": "Центр Golden у K-Park", "x": -850, "z": -8800,
     "why": "K-Park назван источником «сердцем Golden»; здесь пересекаются А-3 (новая развязка «K-Park»), "
            "главная поперечная магистраль и ствол ЛРТ; центр стоит на южном берегу Теренкары и выходит к парку"},
    {"id": "C2", "kind": "sub", "name_ru": "Университетский город «Көктерек»", "x": -700, "z": -10450,
     "why": "кампус «рядом с действующим центром космической связи» (Vlast, S21): QAIST, кластер вузов на 40 тыс. "
            "и медкластер вокруг центра «Көктерек»; станция ЛРТ и развязка А-3 «Көктерек»"},
    {"id": "C3", "kind": "sub", "name_ru": "Южный Golden — Жаңаталап", "x": -2500, "z": -13550,
     "why": "первый район у границы с Gate; станция ЛРТ на западной стороне А-3, пешеходный мост на восток"},
    {"id": "C4", "kind": "sub", "name_ru": "Северный Golden", "x": -1750, "z": -6250,
     "why": "пересадка ствола ЛРТ и второй линии (коридор на запад), развязка А-3 «Северная»"},
    {"id": "C5", "kind": "local", "name_ru": "Центр «Есентай»", "x": -900, "z": -14450,
     "why": "повседневный центр восточной стороны юга: школа, поликлиника, рынок у развязки «Жаңаталап»"},
    {"id": "C7", "kind": "local", "name_ru": "Центр «Ақжар»", "x": 650, "z": -5450,
     "why": "повседневный центр северо-восточного кармана между дачами и Әли; станция ЛРТ «Северо-восток»"},
]

# ------------------------------------------------------------------ LRT (the trunk inside Golden)
LRT_LINE = [(-2571.4, -15712.3), (-2560, -15000), (-2500, -14000), (-2420, -12900), (-2300, -12000), (-1950, -11450),
            (-1500, -11050), (-1150, -10750), (-900, -10300), (-800, -9700), (-850, -9200), (-900, -8700),
            (-1050, -8300), (-1150, -8060), (-1350, -7960), (-1420, -7800), (-1650, -7350), (-1780, -6250), (-1650, -5650), (-1150, -5350),
            (-500, -5300), (200, -5250), (458.7, -5107.2), (552.8, -3922.2), (562.8, -3866.4)]
LRT_STATIONS = [
    {"id": "L1", "name_ru": "Жаңаталап", "x": -2545, "z": -14700},
    {"id": "L2", "name_ru": "Южный Golden", "x": -2480, "z": -13550},
    {"id": "L3", "name_ru": "Сады (KZ05-10)", "x": -2340, "z": -12300},
    {"id": "L4", "name_ru": "Медкластер", "x": -1250, "z": -10840},
    {"id": "L5", "name_ru": "Университет «Көктерек»", "x": -830, "z": -9800},
    {"id": "L6", "name_ru": "Golden-Центр / K-Park", "x": -890, "z": -8800},
    {"id": "L7", "name_ru": "Теренкара-Запад", "x": -1620, "z": -7600},
    {"id": "L8", "name_ru": "Северный Golden", "x": -1770, "z": -6300},
    {"id": "L9", "name_ru": "Ақжар", "x": -600, "z": -5310},
    {"id": "L10", "name_ru": "Әли", "x": 380, "z": -4500},
]

# ------------------------------------------------------------------ axes (skeleton only)
A3_INTERCHANGES = [
    {"name_ru": "Жаңаталап (новая)", "z": -14450, "status": "new", "years": [2028, 2030]},
    {"name_ru": "км 30,1 (существует, OSM)", "z": -12165, "status": "keep_existing", "years": [2025, 2025]},
    {"name_ru": "Көктерек (новая)", "z": -10250, "status": "new", "years": [2029, 2031]},
    {"name_ru": "K-Park (новая)", "z": -8250, "status": "new", "years": [2030, 2033]},
    {"name_ru": "Северная (новая)", "z": -5550, "status": "new", "years": [2036, 2038]},
    {"name_ru": "км 39,0 (существует, OSM)", "z": -3284, "status": "keep_existing", "years": [2025, 2025]},
]
for it in A3_INTERCHANGES:
    it["x"] = round(a3x(it["z"]))

AXES = [
    {"id": "X-A3", "class": "expressway", "name_ru": "А-3 Алматы – Қонаев (скоростная, 6 полос)",
     "line": [[-2114, -15636], [-2120, -15839 + 1000], [-2128, -14310], [-759, -6034], [-800, -4500], [-860, -3290]],
     "status": "keep_existing", "years": [2025, 2025],
     "why": "существующая ось города (OSM); все узлы в разных уровнях: 2 существующие развязки + 4 новые с шагом 1,9–2,5 км (норма ≥ 1,6 км)"},
    {"id": "X-A19", "class": "expressway", "name_ru": "А-19 (угол района, существующая)",
     "line": [[45, -16376], [182, -16245]], "status": "keep_existing", "years": [2025, 2025],
     "why": "существующая трасса режет юго-восточный угол на 0,2 км; стыки J004/J005 и J044/J045"},
    {"id": "X-T1", "class": "trunk", "name_ru": "KZ05-10 — магистраль «Сады»",
     "line": [[-5151, -11697], [-4308, -11814], [-3816, -11558], [-3203, -11626], [-2738, -12021], [-1783, -12165], [-1405, -12228]],
     "status": "keep_existing", "years": [2025, 2025],
     "why": "существующая областная дорога: связь с западными сёлами и развязкой км 30,1; стыки J042 и J043"},
    {"id": "X-T2", "class": "trunk", "name_ru": "Проспект K-Park (главная поперечная)",
     "line": [[-2050, -8250], [a3x(-8250), -8250], [-650, -8450], [-150, -9150],
              [700, -9050], [1700, -8850], [2609, -8722]],
     "status": "new", "years": [2030, 2033],
     "why": "поперечная ось через главный центр: от Западного проспекта через развязку «K-Park» к стыку J041 на востоке; "
            "обходит дачи «Пчёлка» с юга вдоль Теренкары"},
    {"id": "X-T3", "class": "trunk", "name_ru": "Северная магистраль",
     "line": [[-7000, -5750], [-4500, -5700], [-2600, -5600], [a3x(-5550), -5550], [-250, -5450]],
     "status": "new", "years": [2035, 2038],
     "why": "отделяет жильё от северной логистической зоны; развязка «Северная»; на востоке — к северо-восточному проспекту"},
    {"id": "X-T4", "class": "trunk", "name_ru": "Южная поперечная «Жаңаталап»",
     "line": [[-3300, -14100], [-2600, -14300], [a3x(-14450), -14450], [-850, -14500]],
     "status": "new", "years": [2027, 2030],
     "why": "первая новая поперечная: от улиц Жаңаталапа через развязку «Жаңаталап» на восточную сторону А-3"},
    {"id": "X-A1", "class": "arterial", "name_ru": "Западный проспект (бульвар ЛРТ)",
     "line": [[-2560, -14300], [-2440, -12900], [-2350, -12050], [-2700, -11000], [-2700, -10100],
              [-2550, -9300], [-2050, -8250], [-2050, -8100], [-2100, -7000], [-2150, -5800], [-2000, -4600], [-1500, -3700]],
     "status": "new", "years": [2027, 2040],
     "why": "дублёр А-3 с запада в 400–900 м; в южной части в его середине идёт ствол ЛРТ; на севере ведёт к логистике и км 39"},
    {"id": "X-A2", "class": "arterial", "name_ru": "Проспект Знаний (восточный)",
     "line": [[-850, -14500], [-1250, -13300], [-1480, -12400], [-1520, -12050], [-1350, -11500],
              [-1050, -11000], [-600, -9700], [-650, -8450]],
     "status": "new", "years": [2027, 2033],
     "why": "главная улица восточной стороны: от поперечной «Жаңаталап» на север, проход у развязки км 30,1 к Университетскому городу и центру"},
    {"id": "X-A3n", "class": "arterial", "name_ru": "Северо-восточный проспект",
     "line": [[-250, -7200], [-150, -6500], [-250, -5450], [-100, -4300], [-200, -3800], [-532, -3421]],
     "status": "new", "years": [2034, 2038],
     "why": "между дачами «Рассвет» и «Энергетик» к стыку J030 (Growing-восток); каркас северо-восточного кармана"},
    {"id": "X-D1", "class": "district", "name_ru": "Улица Көктерек",
     "line": [[a3x(-10250), -10250], [-600, -10150], [300, -10100], [1300, -10200]],
     "status": "new", "years": [2029, 2032], "why": "въезд в Университетский город от развязки «Көктерек»; адрес QAIST и медкластера"},
    {"id": "X-D2", "class": "district", "name_ru": "Улица Ипподромная",
     "line": [[-850, -14500], [-300, -13600], [-700, -13100], [-1250, -13300]],
     "status": "new", "years": [2040, 2046], "why": "кольцевой подъезд к спортцентру и ипподрому с двух магистралей"},
    {"id": "X-D3", "class": "district", "name_ru": "Улица Косөзен",
     "line": [[-7000, -5750], [-6950, -3900]], "status": "new", "years": [2038, 2046],
     "why": "западная граница застройки вдоль бровки долины Каскелена, подъезд к очистным"},
    {"id": "X-D4", "class": "district", "name_ru": "Улица Ақжар",
     "line": [[-250, -5450], [400, -5450], [1200, -5300]], "status": "new", "years": [2036, 2040],
     "why": "главная улица северо-восточного кармана: станция «Ақжар» — центр — Әли"},
    {"id": "X-B1", "class": "boulevard", "name_ru": "Бульвар Знаний",
     "line": [[-1250, -10840], [-1080, -11250], [-880, -11500], [-450, -11500], [0, -11460], [550, -10600], [700, -9800], [-150, -9450], [-830, -9800]],
     "status": "new", "years": [2029, 2040],
     "why": "пешеходно-велосипедное кольцо кампуса: станции ЛРТ — QAIST — центр «Көктерек» — кластер вузов — парк"},
    {"id": "X-L2", "class": "lrt_corridor", "name_ru": "Коридор второй линии ЛРТ (резерв)",
     "line": [[-1770, -6300], [-3000, -6450], [-4300, -6650], [-5500, -6500], [-6500, -6200]],
     "status": "new", "years": [2046, 2050],
     "why": "вторая линия по генплану (3 линии): коридор держим к западным кварталам резерва (а не к складам, как черновик west_gate); строится вместе с ними после 2050; конечная и депо у Косөзена"},
    {"id": "X-IA", "class": "expressway", "name_ru": "Коридор дороги IA (резерв, трасса не опубликована)",
     "line": [[-17600, -8900], [-17000, -3800], [-17100, 1000]],
     "status": "new", "years": [2041, 2050],
     "why": "план: «новая дорога IA по западной стороне города, западнее неё лесопарк»; держим коридор 150 м; стыков в city.json нет"},
]

# ------------------------------------------------------------------ zone sketches (priority order: earlier wins)
# "auto" geometry keys are built from layers (water, villages, rivers); polygons are sketches clipped to the district.
CORE_X = -7400          # west edge of the core; west of it the twin-only wing beyond the Kaskelen valley


ZONES = [
    # id, use, sketch, density, years, why
    {"id": "Z-W", "use": "waterfront", "auto": "water", "name_ru": "Вода и водоохранная полоса 35 м", "years": [2025, 2025],
     "why": "пруды, водохранилища и реки OSM с полосой 35 м (Водный кодекс): только набережные и парки"},
    {"id": "Z-V1", "use": "village_existing", "auto": "zhanatalap", "name_ru": "Жаңаталап (существующий)", "years": [2025, 2050],
     "density": {"floors_typical": "1–2"}, "why": "существующий микрорайон: свои улицы, новые дороги его обходят"},
    {"id": "Z-V2", "use": "village_existing", "auto": "dachas", "name_ru": "Дачные массивы и сады (существующие)", "years": [2025, 2050],
     "density": {"floors_typical": "1–2"},
     "why": "«Пчёлка», «Рассвет», «Энергетик», «Дружба», сады у Теренкары (OSM): остаются, получают улицы и сети"},
    {"id": "Z-V3", "use": "village_existing", "auto": "houses", "name_ru": "Прочие существующие дома и усадьбы", "years": [2025, 2050],
     "density": {"floors_typical": "1–2"}, "why": "все здания Overture и existing_osm двойника вне массивов: не сносим"},
    {"id": "Z-U1", "use": "utility", "auto": "space_centre", "name_ru": "Центр космической связи «Көктерек» (существующий)",
     "years": [2025, 2025], "why": "действующий объект (контур OSM 25 га) остаётся как есть; кампус рядом, не на нём"},
    {"id": "Z-U2", "use": "utility", "poly": [rect(-7300, -3900, -6500, -3300)], "name_ru": "Очистные сооружения Golden",
     "years": [2034, 2037], "density": {"jobs_per_ha": 3},
     "why": "по правилу (одни очистные на район): самая низкая точка застройки (≈ 560 м), на западе, ниже по ветру; СЗЗ 400 м — только логистика"},
    {"id": "Z-P1", "use": "park", "auto": "rivers", "name_ru": "Речные парки Теренкары, Малой Алматинки и Есентая",
     "years": [2028, 2045], "density": {"jobs_per_ha": 1},
     "why": "зелёные хребты района: пойма и откосы под парки, набережные, велодорожки; дают норму 16 м² зелени на жителя"},
    {"id": "Z-P2", "use": "park", "auto": "kaskelen", "name_ru": "Долина Каскелена — лесопарк", "years": [2030, 2050],
     "density": {"jobs_per_ha": 0.5}, "why": "долина и откосы Каскелена (уклон до 10 %): лесопарк, граница застройки"},
    {"id": "Z-P3", "use": "park", "poly": [rect(-720, -8960, -300, -8700)], "name_ru": "K-Park (10 га)", "years": [2025, 2027],
     "density": {"jobs_per_ha": 5}, "why": "строится, открытие 2027 (S72); место двойника сохранено — это сердце главного центра"},
    {"id": "Z-M1", "use": "medical", "poly": [[[-1500, -10780], [-900, -10760], [-860, -10080], [-1420, -10040]]],
     "name_ru": "Медкластер: две больницы 937 + 927 коек, корейские клиники", "years": [2027, 2040],
     "density": {"floors_typical": "5–9", "far": 1.2, "jobs_per_ha": 140},
     "why": "место двойника сохранено: у развязки «Көктерек» (скорая с А-3) и станции ЛРТ, рядом с вузами (медфакультеты)"},
    {"id": "Z-C1", "use": "campus", "poly": [[[-820, -11420], [650, -11420], [650, -10250], [-40, -10250], [-40, -10950], [-820, -10950]]],
     "name_ru": "Кампус QAIST (≈ 115 га, 5 тыс. студентов) и институт KAIST", "years": [2027, 2036],
     "density": {"floors_typical": "3–8", "far": 0.6, "jobs_per_ha": 25},
     "why": "по источнику кампус «рядом с центром космической связи»: участок обнимает «Көктерек» с юга и востока; ≤ 120 га"},
    {"id": "Z-C2", "use": "campus", "poly": [[[-760, -10250], [1400, -10250], [1700, -9500], [600, -9250], [-200, -9300], [-760, -9550]]],
     "name_ru": "Кластер вузов (35 тыс. студентов, британский хаб) и общежития", "years": [2032, 2050],
     "density": {"floors_typical": "4–9", "far": 0.9, "homes_per_ha": 15, "jobs_per_ha": 35},
     "why": "вторая часть 400-гектарного центра образования, здравоохранения и спорта (S03) — к северу и востоку от «Көктерек»"},
    {"id": "Z-S1", "use": "sport", "poly": [[[-1300, -14250], [-400, -14250], [-150, -13200], [-1250, -13050]]],
     "name_ru": "Спортивный центр, ипподром и этноаул", "years": [2040, 2050], "density": {"jobs_per_ha": 8},
     "why": "по правилу вместо отменённого стадиона: у развязок км 30,1 и «Жаңаталап» и А-19 (зрители не едут через жильё), "
            "вдали от больниц; этноаул рядом с ипподромом"},
    {"id": "Z-K1", "use": "mixed_centre", "poly": [[[-1300, -9350], [-560, -9300], [-300, -8960], [-300, -8700], [-560, -8450],
                                                     [-1050, -8300], [-1450, -8600]]],
     "name_ru": "Главный центр у K-Park", "years": [2031, 2042],
     "density": {"floors_typical": "6–12", "far": 2.2, "homes_per_ha": 120, "jobs_per_ha": 160},
     "why": "площадь у станции, торговые улицы, офисы, гостиницы, культура; ТРЦ ≤ 250 м от станции; парковки под землёй"},
    {"id": "Z-K2", "use": "mixed_centre", "circle": [-2480, -13550, 380], "name_ru": "Центр «Южный Golden»", "years": [2028, 2034],
     "density": {"floors_typical": "5–12", "far": 1.9, "homes_per_ha": 110, "jobs_per_ha": 120}, "why": "у станции L2: первый центр района"},
    {"id": "Z-K3", "use": "mixed_centre", "circle": [-1770, -6300, 420], "name_ru": "Центр «Северный Golden»", "years": [2037, 2044],
     "density": {"floors_typical": "5–12", "far": 1.9, "homes_per_ha": 110, "jobs_per_ha": 120}, "why": "пересадка двух линий ЛРТ и развязка «Северная»"},
    {"id": "Z-K5", "use": "mixed_centre", "circle": [-900, -14450, 260], "name_ru": "Центр «Есентай»", "years": [2029, 2034],
     "density": {"floors_typical": "4–9", "far": 1.5, "homes_per_ha": 100, "jobs_per_ha": 90}, "why": "повседневный центр юго-востока"},
    {"id": "Z-K6", "use": "mixed_centre", "circle": [650, -5450, 260], "name_ru": "Центр «Ақжар»", "years": [2036, 2042],
     "density": {"floors_typical": "4–9", "far": 1.5, "homes_per_ha": 100, "jobs_per_ha": 90}, "why": "повседневный центр северо-востока"},
    {"id": "Z-L1", "use": "logistics", "poly": [[[-7400, -4950], [-3400, -5050], [-3400, 500], [-7400, 500]]],
     "name_ru": "Агропереработка, склады и цеха МСБ (Косөзен – трасса)", "years": [2027, 2045],
     "density": {"floors_typical": "1–3", "far": 0.45, "jobs_per_ha": 40},
     "why": "источник: «между Косөзеном и Капчагайской трассой — склады, логистика, цеха МСБ; крупных заводов с выбросами нет»; "
            "кластер агропереработки и Hyundai Green Food; к западу от жилья (ветер В и СВ)"},
    {"id": "Z-L2", "use": "logistics", "poly": [[[-3400, -5050], [-1300, -5000], [-1050, -3000], [-1200, 500], [-3400, 500]]],
     "name_ru": "Логистический узел у развязки км 39", "years": [2027, 2040],
     "density": {"floors_typical": "1–3", "far": 0.5, "jobs_per_ha": 30},
     "why": "склады у существующей развязки км 39,0 и выхода к ж/д Жетыгена: грузовики не заходят в жилые кварталы"},
    {"id": "Z-L3", "use": "logistics", "poly": [[[-700, -4900], [400, -4800], [700, -3800], [-600, -3300]]],
     "name_ru": "Склады у полигона Әли", "years": [2034, 2042], "density": {"floors_typical": "1–2", "far": 0.4, "jobs_per_ha": 25},
     "why": "в 1 км от полигона у Әли жильё не ставим (СЗЗ полигона); здесь склады и коммунальные базы"},
    {"id": "Z-P4", "use": "park", "circle": [-2200, -9750, 520], "name_ru": "Городской парк «Төменгі Тереңқара»", "years": [2032, 2036],
     "density": {"jobs_per_ha": 2}, "why": "водохранилище у А-3 становится городским парком (норма ≥ 15 га, 10 м² на жителя) напротив K-Park"},
    {"id": "Z-B1", "use": "business", "auto": "a3_band", "name_ru": "Технологический коридор вдоль А-3", "years": [2028, 2048],
     "density": {"floors_typical": "4–10", "far": 1.3, "jobs_per_ha": 130},
     "why": "полоса 60–330 м от оси А-3: офисы, лаборатории, гостиницы, торговля закрывают жильё от шума трассы (жильё ≥ 50 м от трассы)"},
    {"id": "Z-H1", "use": "residential_high", "auto": "lrt_ring", "name_ru": "Жильё 9–12 этажей у станций ЛРТ", "years": [2029, 2048],
     "density": {"floors_typical": "9–12", "far": 1.5, "homes_per_ha": 165, "jobs_per_ha": 25},
     "why": "в 500 м от станций плотнее всего (норма: максимальная плотность у станций); не выше 12 этажей (Golden 4–12, генплан)"},
    {"id": "Z-R3", "use": "residential_low", "auto": "village_ring", "name_ru": "Жильё 2–4 этажа у существующих посёлков", "years": [2030, 2050],
     "density": {"floors_typical": "2–4", "far": 0.55, "homes_per_ha": 65, "jobs_per_ha": 6},
     "why": "полоса 150 м вокруг сёл и дач: без высоток во дворе малоэтажки (правило 16)"},
    {"id": "Z-R2S", "use": "residential_mid", "auto": "core_south", "name_ru": "Жильё 5–8 этажей — юг", "years": [2028, 2040],
     "density": {"floors_typical": "5–8", "far": 1.0, "homes_per_ha": 115, "jobs_per_ha": 15},
     "why": "кварталы с дворами, школы и сады по радиусам; первая очередь растёт от Gate на север"},
    {"id": "Z-R2N", "use": "residential_mid", "auto": "core_north", "name_ru": "Жильё 5–8 этажей — север", "years": [2034, 2050],
     "density": {"floors_typical": "5–8", "far": 1.0, "homes_per_ha": 115, "jobs_per_ha": 15},
     "why": "вторая и третья очереди: от главного центра на север и на запад по второй линии ЛРТ"},
    {"id": "Z-RW", "use": "reserve", "auto": "core_rest", "name_ru": "Резерв роста после 2050: западные кварталы", "years": [2050, 2050],
     "density": {"jobs_per_ha": 0},
     "why": "675 тыс. жителей помещаются в 1,3 км от ствола ЛРТ и А-3; запад ядра держим под вторую линию ЛРТ и рост после 2050 (сейчас поля)"},
    {"id": "Z-F1", "use": "park", "auto": "west_forest", "name_ru": "Лесопарк западной границы (пески Мойынкум)", "years": [2035, 2050],
     "density": {"jobs_per_ha": 0.2}, "why": "план: западнее дороги IA — лесопарк; защищает город от песка и ветра"},
    {"id": "Z-F2", "use": "park", "auto": "scarp", "name_ru": "Откосы плато (уклон > 8 %)", "years": [2035, 2050],
     "density": {"jobs_per_ha": 0}, "why": "крутые откосы не застраиваются: озеленение против эрозии"},
    {"id": "Z-R0", "use": "reserve", "auto": "rest", "name_ru": "Резерв после 2050 (западное плато)", "years": [2050, 2050],
     "density": {"jobs_per_ha": 0},
     "why": "крыло за Каскеленом есть только в контуре двойника, в Golden генплана его нет; держим пустым — и для захода на аэропорт Growing-запад"},
]

PHASES = [
    {"queue": 1, "years": [2026, 2030], "what_ru": "Юг у Gate: поперечная «Жаңаталап», Западный проспект и Проспект Знаний до KZ05-10; "
     "первые кварталы и центр «Южный Golden»; K-Park (2027); первая больница медкластера (500 коек) и первая очередь QAIST; "
     "логистика у км 39",
     "zones": ["Z-K2", "Z-K5", "Z-P3", "Z-M1", "Z-C1", "Z-L2"], "axes": ["X-T4", "X-A1", "X-A2", "X-D1"]},
    {"queue": 2, "years": [2031, 2036], "what_ru": "Ствол ЛРТ Gate–Golden (2031), развязки «Көктерек» и «K-Park», проспект K-Park; "
     "главный центр, Бульвар Знаний, жильё у станций юга и центра",
     "zones": ["Z-K1", "Z-H1", "Z-R2S", "Z-B1", "Z-P1", "Z-P4"], "axes": ["X-T2", "X-B1", "X-P1"]},
    {"queue": 3, "years": [2037, 2043], "what_ru": "Север: развязка и магистраль «Северная», северо-восточный проспект; центры «Северный Golden» "
     "и «Ақжар», жильё севера, кластер вузов, очистные, агропереработка",
     "zones": ["Z-K3", "Z-K6", "Z-R2N", "Z-C2", "Z-U2", "Z-L1", "Z-L3"], "axes": ["X-T3", "X-A3n", "X-P2"]},
    {"queue": 4, "years": [2044, 2050], "what_ru": "Спортцентр, ипподром и этноаул; малоэтажные кварталы у сёл; лесопарки долины Каскелена и западной границы; "
     "коридоры второй линии ЛРТ и дороги IA — в резерве",
     "zones": ["Z-R3", "Z-S1", "Z-P2", "Z-F1", "Z-F2"], "axes": ["X-L2", "X-D2", "X-D3", "X-IA"]},
]


# ------------------------------------------------------------------ inputs from layers
def load_inputs():
    I = {}
    clip = GOLD.buffer(500)
    wg, wp = layers.load("water")
    sel = shapely.intersects(clip, wg)
    I["water_polys"] = unary_union([g for g, s in zip(wg, sel) if s and "Polygon" in g.geom_type]).intersection(GOLD.buffer(50))
    I["water_lines"] = [g for g, s in zip(wg, sel) if s and "Line" in g.geom_type]
    mg, mp = layers.load("derived/water_main")
    I["rivers"] = {p["id"]: g for g, p in zip(mg, mp)}
    lg, lp = layers.load("land_use")
    I["allot"] = unary_union([g for g, p in zip(lg, lp) if g.intersects(GOLD) and p.get("class") == "allotments"])
    I["zhanatalap"] = unary_union([g for g, p in zip(lg, lp) if p.get("name") == "Жаңаталап"])
    I["space_centre"] = unary_union([g for g, p in zip(lg, lp) if "ғарыштық" in (p.get("name") or "")])
    I["ali"] = unary_union([g for g, p in zip(lg, lp) if p.get("name") == "Әли"])
    bg, bp = layers.load("buildings")
    sel = shapely.intersects(clip, bg)
    I["bld"] = bg[sel]
    B = twin.buildings()
    ex = B[(B.source == "existing_osm")]
    ins = shapely.contains_xy(clip, ex.x.values, ex.z.values)
    I["twin_ex"] = np.c_[ex.x.values[ins], ex.z.values[ins]]
    I["B"] = B
    rg, rp = layers.load("roads")
    sel = shapely.intersects(clip, rg)
    I["roads"] = [(g, p.get("class", "unknown")) for g, p, s in zip(rg, rp, sel) if s]
    rl, _ = layers.load("rail")
    I["rail"] = [g for g in rl if g.intersects(clip.buffer(3000))]
    ig, ip = layers.load("infrastructure")
    I["power"] = [g for g, p in zip(ig, ip) if p.get("class") == "power_line" and g.intersects(clip)]
    kg, kp = layers.load("derived/kapchagay_levels")
    I["flood485"] = unary_union([g for g, p in zip(kg, kp) if p.get("real_m") == 485.0])
    pts = house_points(I)
    inside = shapely.contains_xy(GOLD.buffer(10), pts[:, 0], pts[:, 1])
    g = unary_union(shapely.buffer(shapely.points(pts[inside]), 30, quad_segs=4))
    I["house_blob"] = g.buffer(40).buffer(-40)
    I["village_all"] = unary_union([I["house_blob"], I["zhanatalap"], I["allot"], I["ali"]])
    sg, sp = layers.load("derived/settlements")
    I["settl"] = [(g, p) for g, p in zip(sg, sp) if g.intersects(GOLD.buffer(2500))]
    return I


def house_points(I):
    c = np.array([(g.centroid.x, g.centroid.y) for g in I["bld"]]) if len(I["bld"]) else np.zeros((0, 2))
    return np.vstack([c, I["twin_ex"]])


# ------------------------------------------------------------------ zone builder
def auto_geom(key, I, built):
    T = terrain.terrain()
    if key == "water":
        return I["water_polys"].buffer(35).difference(I["village_all"]).union(I["water_polys"])
    if key == "zhanatalap":
        return I["zhanatalap"]
    if key == "dachas":
        return I["allot"].union(I["ali"])
    if key == "houses":
        return I["house_blob"]
    if key == "space_centre":
        return I["space_centre"]
    if key == "rivers":
        R = I["rivers"]
        parts = [R["terenkara"].buffer(110), R["malaya_almatinka"].buffer(140), R["yesentai"].buffer(80)]
        return unary_union(parts).intersection(box(CORE_X, -17000, 4000, 2000))
    if key == "kaskelen":
        k = I["rivers"]["kaskelen"].buffer(450)
        return k.union(box(-10400, -5600, CORE_X, 1200).intersection(GOLD).intersection(k.buffer(900)))
    if key == "a3_band":
        a3 = LineString(A3)
        return a3.buffer(330, cap_style="flat").difference(a3.buffer(0))
    if key == "lrt_ring":
        return unary_union([Point(s["x"], s["z"]).buffer(520) for s in LRT_STATIONS])
    if key == "village_ring":
        v = unary_union([built[z] for z in ("Z-V1", "Z-V2")] + [built["Z-V3"]])
        big = unary_union([p for p in getattr(v, "geoms", [v]) if p.area > 15e4])
        return big.buffer(150)
    if key == "core_south":
        return box(CORE_X, -17000, 4000, -9300).intersection(envelope())
    if key == "core_north":
        return box(CORE_X, -9300, 4000, 2000).intersection(envelope())
    if key == "core_rest":
        return box(CORE_X, -17000, 4000, 2000)
    if key == "west_forest":
        west = box(-19000, -17000, CORE_X, 2000).intersection(GOLD)
        return west.difference(GOLD.buffer(-900)).intersection(box(-19000, -17000, -15000, 2000))
    if key == "scarp":
        xs = np.arange(-19000, CORE_X, 100.0); zs = np.arange(-10000, 2000, 100.0)
        X, Z = np.meshgrid(xs, zs)
        S = T.slope(X, Z)
        m = S > 0.08
        cells = [box(x - 50, z - 50, x + 50, z + 50) for x, z in zip(X[m], Z[m])]
        g = unary_union(cells).buffer(60).buffer(-60) if cells else Polygon()
        return unary_union([p for p in getattr(g, "geoms", [g]) if p.area > 30e4])
    if key == "rest":
        return GOLD
    raise KeyError(key)


ENVELOPE_M = 1300      # застройка до 2050: в пешей и велосипедной доступности от ствола ЛРТ и А-3


def envelope():
    return LineString(LRT_LINE).buffer(ENVELOPE_M).union(LineString(A3).buffer(ENVELOPE_M))


def build_zones(I):
    built, taken = {}, Polygon()
    for z in ZONES:
        if "poly" in z:
            g = unary_union([Polygon(r) for r in z["poly"]])
        elif "circle" in z:
            g = Point(z["circle"][0], z["circle"][1]).buffer(z["circle"][2])
        else:
            g = auto_geom(z["auto"], I, built)
        g = shapely.make_valid(g).intersection(GOLD).difference(taken)
        g = shapely.make_valid(g)
        g = unary_union([p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and p.area > 500])
        built[z["id"]] = g
        taken = taken.union(g)
    return built


# ------------------------------------------------------------------ capacity and checks
def zone_capacity(z, g):
    d = z.get("density", {})
    ha = g.area / 1e4
    homes = d.get("homes_per_ha", 0) * ha
    res = homes * M2_PER_HOME / M2_PER_RESIDENT
    jobs = d.get("jobs_per_ha", 0) * ha
    return ha, homes, res, jobs


HALF_W = {"expressway": 35, "trunk": 25, "arterial": 20, "district": 12, "boulevard": 15, "pedestrian": 4, "lrt_corridor": 8}


def run_checks(I, built):
    T = terrain.terrain()
    C = {}
    pts = house_points(I)
    P = shapely.points(pts)
    hits = {}
    for z in ZONES:
        if z["use"] in ("village_existing",):
            continue
        g = built[z["id"]]
        n = int(shapely.contains(g, P).sum()) if not g.is_empty else 0
        hits[z["id"]] = n
    C["houses_hit_by_zones"] = {"total_except_villages_and_kept_facilities": sum(v for k, v in hits.items() if k != "Z-U1"),
                                "space_centre_own_buildings_kept": hits.get("Z-U1", 0),
                                "by_zone": {k: v for k, v in hits.items() if v}}
    ah = {}
    br = {}
    for a in AXES:
        if a["status"] == "keep_existing":
            continue
        L = LineString(a["line"])
        corr = L.buffer(HALF_W[a["class"]])
        idx = shapely.intersects(corr, I["bld"])
        n = int(idx.sum()) + int(shapely.contains(corr, shapely.points(I["twin_ex"])).sum())
        ah[a["id"]] = n
        nb = sum(1 for wl in I["water_lines"] if L.intersects(wl))
        br[a["id"]] = nb
    L = LineString(LRT_LINE)
    corr = L.buffer(6)
    ah["LRT"] = int(shapely.intersects(corr, I["bld"]).sum()) + int(shapely.contains(corr, shapely.points(I["twin_ex"])).sum())
    C["houses_hit_by_new_axes"] = {"total": sum(ah.values()), "by_axis": {k: v for k, v in ah.items() if v}}
    C["river_crossings_new_axes"] = {"note": "пересечения рек и каналов OSM новыми осями: мосты (правило 4 допускает мост выше паводка 1 % + 0,5 м)",
                                     "by_axis": {k: v for k, v in br.items() if v}}
    wp = I["water_polys"]
    on_water = {}
    for z in ZONES:
        if z["use"] in ("waterfront", "park", "village_existing", "reserve"):
            continue
        a = built[z["id"]].intersection(wp).area
        if a > 100:
            on_water[z["id"]] = round(a)
    C["build_zones_on_water_m2"] = on_water or 0
    axw = {}
    for a in AXES:
        if a["status"] == "keep_existing":
            continue
        ln = LineString(a["line"]).intersection(wp.buffer(-5)).length
        if ln > 60:
            axw[a["id"]] = round(ln)
    C["new_axes_over_water_m"] = {"by_axis": axw or 0, "note": "длина новых осей над водными полигонами OSM: только косые переходы рек (мосты), вдоль воды оси не идут"}
    C["kapchagay_485_flood"] = {"golden_area_inside_m2": round(GOLD.intersection(I["flood485"]).area),
                                "lowest_ground_m": round(float(np.min(T.height(*np.array(GOLD.exterior.coords).T))), 1),
                                "note": "Golden лежит на 530–650 м, линия 485 м до района не доходит"}
    # joints
    J = [j for j in CITY["joints"]["items"] if "golden" in j["between"]]
    met = []
    for j in J:
        p = Point(j["x"], j["z"])
        if j["kind"] == "lrt":
            d, ax = LineString(LRT_LINE).distance(p), "LRT"
        elif j["kind"] == "rail":
            d, ax = 0.0, "rail_existing"
            r = [g for g in I["rail"]]
            d = min(g.distance(p) for g in r) if r else 1e9
        else:
            best = min(((LineString(a["line"]).distance(p), a["id"]) for a in AXES if a["class"] in ("expressway", "trunk", "arterial")),
                       key=lambda t: t[0])
            d, ax = best
            if d > 30 and j["line"].startswith("T-H") and LineString(A3).distance(p) < 450:
                d, ax = 0.0, "X-A3"     # carriageways and ramps of the A-3 interchanges: part of the expressway node
        met.append({"joint_id": j["id"], "kind": j["kind"], "axis": ax, "dist_m": round(d, 1), "met": d <= 30})
    C["joints"] = {"count": len(J), "met": sum(m["met"] for m in met), "items": met}
    # registry
    mine = registry_rows_of_golden()
    have = {o["registry_id"] for o in OBJECTS}
    C["registry"] = {"rows_of_golden": len(mine), "with_row": sum(1 for r in mine if r["id"] in have),
                     "missing": [r["id"] for r in mine if r["id"] not in have],
                     "genplan_golden_outside_cityjson": genplan_only_rows()}
    # shares and capacity
    tot = GOLD.area / 1e4
    share, cap = {}, {"population": 0.0, "homes": 0.0, "jobs": 0.0}
    for z in ZONES:
        ha, homes, res, jobs = zone_capacity(z, built[z["id"]])
        share[z["use"]] = share.get(z["use"], 0) + ha
        cap["population"] += res; cap["homes"] += homes; cap["jobs"] += jobs
    students_res = 0.3 * 40000          # модель: 30 % студентов в общежитиях кампусов (часть Z-C2 homes)
    C["zone_share_pct"] = {k: round(100 * v / tot, 1) for k, v in sorted(share.items(), key=lambda t: -t[1])}
    C["zone_area_ha"] = {k: round(v) for k, v in sorted(share.items(), key=lambda t: -t[1])}
    C["covered_ha"] = round(sum(share.values()), 1)
    C["district_ha"] = round(tot, 1)
    green = share.get("park", 0) + share.get("waterfront", 0)
    C["capacity"] = {"population": round(cap["population"]), "homes": round(cap["homes"]), "jobs": round(cap["jobs"]),
                     "population_vs_target_pct": round(100 * (cap["population"] / TARGETS["population_2050"] - 1), 1),
                     "jobs_vs_target_pct": round(100 * (cap["jobs"] / TARGETS["jobs_2050"] - 1), 1),
                     "public_green_m2_per_resident": round(green * 1e4 / cap["population"], 1),
                     "students_in_dorms_model": students_res,
                     "method": "жители = homes_per_ha × га × 75 м² / 30 м² (CityStats: 30 м² на жителя; 75 м² на квартиру — модель qTwin); "
                               "рабочие места = jobs_per_ha × га (модель qTwin по CityStats: 90/50/100/120 м² на место)"}
    # slope
    cx, cz = CENTRES[0]["x"], CENTRES[0]["z"]
    rr = np.linspace(0, 600, 7)
    ang = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    sx = (cx + np.outer(rr, np.cos(ang))).ravel(); sz = (cz + np.outer(rr, np.sin(ang))).ravel()
    sl = T.slope(sx, sz) * 100
    C["slope_main_centre"] = {"mean_pct": round(float(sl.mean()), 2), "max_pct": round(float(sl.max()), 2), "radius_m": 600}
    ss = {}
    for a in AXES + [{"id": "LRT", "line": LRT_LINE}]:
        s, x, z, h = T.profile(a["line"], step=25.0)
        if len(s) < 3:
            continue
        g = np.abs(np.gradient(h, s)) * 100
        ss[a["id"]] = {"mean_grade_pct": round(float(g.mean()), 2), "max_grade_pct": round(float(g.max()), 2),
                       "ground_slope_max_pct": round(float((T.slope(x, z) * 100).max()), 1)}
    C["slope_axes"] = ss
    # airfield height zones
    afs = CITY["height_limits"]["airfields"]
    gp = np.array(GOLD.representative_point().coords[0])
    xs = np.arange(-19000, 3500, 250.0); zs = np.arange(-16500, 1500, 250.0)
    X, Z = np.meshgrid(xs, zs)
    ins = shapely.contains_xy(GOLD, X.ravel(), Z.ravel())
    res = {}
    for a in afs:
        d = np.hypot(X.ravel()[ins] - a["x"], Z.ravel()[ins] - a["z"])
        sh = float((d <= 30000).mean())
        if sh > 0:
            res[a["id"]] = {"share_of_golden_in_30km_pct": round(100 * sh, 1), "min_dist_km": round(float(d.min()) / 1000, 1)}
    tall = [z["id"] for z in ZONES if "12" in str(z.get("density", {}).get("floors_typical", ""))]
    C["height_limits"] = {"airfields_30km": res, "max_floors_planned": 12, "max_height_m": 42,
                          "zones_up_to_12_floors": tall,
                          "result": "ничего ≥ 50 м не планируется (потолок 12 этажей ≈ 42 м); акцент выше — только с пометкой «нужно согласование»"}
    return C


# ------------------------------------------------------------------ registry
def reg_rows():
    return {r["id"]: r for r in REG["rows"]}


def registry_rows_of_golden():
    out = []
    for r in REG["rows"]:
        g = r.get("geom")
        inside = False
        if g:
            s = shape(g)
            if s.geom_type == "Point":
                inside = GOLD.contains(s)
            elif "Line" in s.geom_type:
                inside = s.intersection(GOLD).length > 100
            else:
                inside = s.intersection(GOLD).area > 1e4
        named = r.get("district") in ("Golden", "Gate и Golden") or (r.get("district") is None and r.get("district_inferred") == "Golden" and not g)
        if inside or named:
            out.append(r)
    return out


def genplan_only_rows():
    mine = {r["id"] for r in registry_rows_of_golden()}
    return [r["id"] for r in REG["rows"] if r.get("district_geom") == "Golden" and r["id"] not in mine]


R = reg_rows()


def acc(i):
    return R[i]["accuracy"] if i in R else None


def pt(i):
    g = R[i].get("geom")
    return [round(v, 1) for v in g["coordinates"]] if g and g["type"] == "Point" else None


OBJECTS = [
    {"registry_id": "qaist", "name_ru": "QAIST (филиал KAIST)", "action": "move", "from": pt("qaist"), "to": [-150, -11100], "yaw": 0,
     "accuracy": acc("qaist"),
     "why": "точка двойника — модель (district_only); в 2,3 км от «Көктерек» и в 600 м от развязки км 30,1, за узкой горловиной у А-3. "
            "Источник (S21): кампус рядом с центром космической связи — переносим на 2,1 км в один Университетский город у «Көктерек»"},
    {"registry_id": "kaist_research_institute", "name_ru": "Исследовательский институт KAIST", "action": "move", "from": pt("kaist_research_institute"),
     "to": [300, -10500], "yaw": 0, "accuracy": acc("kaist_research_institute"), "why": "часть QAIST, едет вместе с кампусом (восточное крыло у «Көктерек»)"},
    {"registry_id": "academic_cluster", "name_ru": "Кластер вузов / университетский городок (40 тыс. студентов)", "action": "add",
     "from": None, "to": [450, -9750], "yaw": 0, "accuracy": acc("academic_cluster"),
     "why": "300+ одинаковых «школ» двойника заменяются кампусом в зоне Z-C2 в пределах 1 км от «Көктерек» (точность источника — 1 км)"},
    {"registry_id": "space_comm_centre", "name_ru": "Центр космической связи «Көктерек»", "action": "keep", "from": [-442, -10648], "to": [-442, -10648],
     "yaw": None, "accuracy": acc("space_comm_centre"), "why": "существующий объект, контур OSM 25 га; кампус рядом, не на нём"},
    {"registry_id": "medcluster_golden", "name_ru": "Медкластер: две больницы (937 и 927 коек)", "action": "keep", "from": pt("medcluster_golden"),
     "to": pt("medcluster_golden"), "yaw": 90, "accuracy": acc("medcluster_golden"),
     "why": "место двойника хорошее: 550 м от А-3 у новой развязки «Көктерек», у станции ЛРТ «Медкластер», рядом с вузами"},
    {"registry_id": "hospitals_stage1", "name_ru": "Больница 1-й очереди Golden (500 коек)", "action": "by_rule", "from": None, "to": [-1250, -10550],
     "yaw": None, "accuracy": acc("hospitals_stage1"), "why": "первый корпус медкластера к 2030 (генплан: по 500 коек в Gate и Golden)"},
    {"registry_id": "korean_clinics", "name_ru": "Корейские клиники", "action": "by_rule", "from": None, "to": [-1050, -10150], "yaw": None,
     "accuracy": acc("korean_clinics"), "why": "в медкластере, по правилу (места в источнике нет)"},
    {"registry_id": "k_park", "name_ru": "K-Park (10 га, открытие 2027)", "action": "keep", "from": pt("k_park"), "to": pt("k_park"), "yaw": None,
     "accuracy": acc("k_park"), "why": "точка двойника — модель, но место хорошее: у станции ЛРТ и Теренкары, вокруг вырастает главный центр"},
    {"registry_id": "k_park_parts", "name_ru": "Состав K-Park (мемориал, сад, музей, каток)", "action": "keep", "from": pt("k_park_parts"),
     "to": pt("k_park_parts"), "yaw": None, "accuracy": acc("k_park_parts"), "why": "внутри K-Park"},
    {"registry_id": "sport_centre_hippodrome", "name_ru": "Спортивный центр и ипподром", "action": "by_rule", "from": None, "to": [-750, -13700],
     "yaw": 0, "accuracy": acc("sport_centre_hippodrome"),
     "why": "по правилу: у развязок км 30,1 и «Жаңаталап» и А-19 — зрители не едут через жильё; вдали от больниц и лабораторий"},
    {"registry_id": "ethnoaul", "name_ru": "Этноаул", "action": "by_rule", "from": None, "to": [-350, -13350], "yaw": None, "accuracy": acc("ethnoaul"),
     "why": "рядом с ипподромом: общие праздники и конные игры"},
    {"registry_id": "stadium_50k", "name_ru": "Стадион на 50 тыс. (отменён)", "action": "remove", "from": None, "to": None, "yaw": None,
     "accuracy": acc("stadium_50k"), "why": "отменён к 2026 году (план); вместо него спортцентр и ипподром"},
    {"registry_id": "british_edu_hub", "name_ru": "Британский образовательный хаб", "action": "by_rule", "from": None, "to": [1000, -9800], "yaw": None,
     "accuracy": acc("british_edu_hub"), "why": "в кластере вузов Z-C2 (места в источнике нет)"},
    {"registry_id": "golden_midrise", "name_ru": "Среднеэтажные кварталы Golden (4–12 эт.)", "action": "by_rule", "from": None, "to": None, "yaw": None,
     "accuracy": acc("golden_midrise"), "why": "зоны Z-R2S, Z-R2N, Z-H1; 792 дома-дубля двойника заменяются кварталами генератора"},
    {"registry_id": "hyundai_green_food", "name_ru": "Hyundai Green Food", "action": "by_rule", "from": None, "to": [-5400, -3800], "yaw": None,
     "accuracy": acc("hyundai_green_food"), "why": "в зоне агропереработки Z-L1, к западу от жилья (ветер В и СВ)"},
    {"registry_id": "agro_processing_golden", "name_ru": "Кластер агропереработки и логистический узел", "action": "by_rule", "from": None,
     "to": [-4300, -4100], "yaw": None, "accuracy": acc("agro_processing_golden"), "why": "зона Z-L1 между Косөзеном и А-3"},
    {"registry_id": "kosozen_logistics", "name_ru": "Склады и цеха МСБ (Косөзен – трасса)", "action": "by_rule", "from": None, "to": [-2400, -4000],
     "yaw": None, "accuracy": acc("kosozen_logistics"), "why": "источник: «между Косөзеном и Капчагайской трассой»; зоны Z-L1 и Z-L2"},
    {"registry_id": "airport_alatau", "name_ru": "Аэропорт «Алатау»", "action": "move", "from": pt("airport_alatau"), "to": None, "yaw": None,
     "accuracy": acc("airport_alatau"),
     "why": "по плану аэропорт в Growing; точка реестра попала в Golden только по контуру двойника — место задаёт картограф Growing-запад; в Golden не планируем"},
    {"registry_id": "airport_rail_station", "name_ru": "Ж/д станция «Алатау» у аэропорта", "action": "move", "from": pt("airport_rail_station"), "to": None,
     "yaw": None, "accuracy": acc("airport_rail_station"), "why": "вместе с аэропортом в Growing-запад"},
    {"registry_id": "road_a3", "name_ru": "А-3 Алматы – Қонаев", "action": "keep", "from": None, "to": None, "yaw": None, "accuracy": acc("road_a3"),
     "why": "ось X-A3; добавляем 4 развязки"},
    {"registry_id": "road_a19", "name_ru": "А-19 (угол района)", "action": "keep", "from": None, "to": None, "yaw": None, "accuracy": acc("road_a19"),
     "why": "ось X-A19"},
    {"registry_id": "road_kz05_10", "name_ru": "KZ05-10", "action": "keep", "from": None, "to": None, "yaw": None, "accuracy": acc("road_kz05_10"),
     "why": "ось X-T1"},
    {"registry_id": "interchange_a3_km30_1", "name_ru": "Развязка А-3 км 30,1", "action": "keep", "from": pt("interchange_a3_km30_1"),
     "to": pt("interchange_a3_km30_1"), "yaw": None, "accuracy": acc("interchange_a3_km30_1"), "why": "существующая (OSM)"},
    {"registry_id": "interchange_a3_km39_0", "name_ru": "Развязка А-3 км 39,0", "action": "keep", "from": pt("interchange_a3_km39_0"),
     "to": pt("interchange_a3_km39_0"), "yaw": None, "accuracy": acc("interchange_a3_km39_0"), "why": "существующая (OSM), узел логистики"},
    {"registry_id": "rail_bypass_zhetygen_kazybek", "name_ru": "Обходная ж/д Жетыген – Казыбек би", "action": "keep", "from": None, "to": None,
     "yaw": None, "accuracy": acc("rail_bypass_zhetygen_kazybek"), "why": "существующая; режет западное крыло (резерв), стыки J031 и J040"},
    {"registry_id": "hv_lines_220", "name_ru": "ВЛ 220 кВ", "action": "keep", "from": None, "to": None, "yaw": None, "accuracy": acc("hv_lines_220"),
     "why": "существующие; в ядре (у K-Park и кампуса) — см. открытый вопрос 1"},
    {"registry_id": "settlement_zhanatalap", "name_ru": "Жаңаталап", "action": "keep", "from": None, "to": None, "yaw": None,
     "accuracy": acc("settlement_zhanatalap"), "why": "существующий: зона Z-V1, обходится осями"},
    {"registry_id": "settlement_baiserke", "name_ru": "Байсерке (за границей)", "action": "keep", "from": None, "to": None, "yaw": None,
     "accuracy": acc("settlement_baiserke"), "why": "соседнее село, задевает границу на 1,3 га: не застраиваем"},
    {"registry_id": "district_golden", "name_ru": "Район Golden", "action": "keep", "from": None, "to": None, "yaw": None,
     "accuracy": acc("district_golden"), "why": "контур — city.json#districts/golden (контур двойника)"},
]

TWIN_JOBS_NOTE = None


def twin_targets():
    B = twin.buildings()
    inside = shapely.contains_xy(GOLD, B.x.values, B.z.values)
    S = B[inside & (B.year <= 2050)]
    mpj = dict(M2_PER_JOB, energy=100.0)
    jobs = sum(S[S.use == u].gfa_m2.sum() / m for u, m in mpj.items())
    return int(round(jobs))


TARGETS = {}


RIVER_PATHS = [("X-P1", "terenkara", "Зелёный хребет Теренкары", [2028, 2045],
                "пешеходная и велосипедная набережная вдоль Теренкары (30 м от русла); через сёла и дачи идёт по их улицам, здесь — только новые участки"),
               ("X-P2", "malaya_almatinka", "Набережная Малой Алматинки", [2033, 2048],
                "вторая зелёная ось вдоль восточной реки, связь кампуса с парками; новые участки вне дач")]


def river_paths(I):
    """Pedestrian axes along the rivers: the river line offset 30 m, minus existing villages, pieces ≥ 400 m."""
    from shapely.ops import linemerge
    out = []
    for pid, rid, name, years, why in RIVER_PATHS:
        r = I["rivers"][rid].intersection(GOLD.buffer(-40))
        r = linemerge(unary_union([q for q in getattr(r, "geoms", [r]) if "Line" in q.geom_type]))
        pieces = []
        for q in getattr(r, "geoms", [r]):
            if q.length < 400:
                continue
            q = q.simplify(40)
            for side in (30, -30):
                o = q.offset_curve(side, join_style="round")
                o = o.difference(I["village_all"].buffer(12)).difference(I["water_polys"].buffer(5))
                for oo in getattr(o, "geoms", [o]):
                    if oo.geom_type == "LineString" and oo.length >= 400:
                        pieces.append(oo)
                break
        pieces = [p for p in pieces if p.intersection(box(CORE_X, -17000, 4000, 2000)).length > 0.8 * p.length]
        for n, pc in enumerate(sorted(pieces, key=lambda p: -p.length)[:6], 1):
            out.append({"id": f"{pid}-{n}", "class": "pedestrian", "name_ru": f"{name}, участок {n}",
                        "line": [[round(x), round(z)] for x, z in pc.simplify(20).coords], "status": "new", "years": years, "why": why})
    return out


# ------------------------------------------------------------------ spec
def build_spec(I, built, C):
    zones = []
    for z in ZONES:
        g = built[z["id"]]
        ha, homes, res, jobs = zone_capacity(z, g)
        zz = {"id": z["id"], "use": z["use"], "name_ru": z["name_ru"], "polygon": poly_coords(g),
              "area_ha": round(ha, 1), "density": z.get("density", {}), "years": z["years"], "why": z["why"]}
        if res or jobs:
            zz["capacity"] = {"residents": int(round(res, -2)), "jobs": int(round(jobs, -2))}
        zones.append(zz)
    axes = []
    for a in AXES:
        aa = {k: a[k] for k in ("id", "class", "name_ru")}
        aa["line"] = [[int(round(x)), int(round(z))] for x, z in a["line"]]
        aa.update({k: a[k] for k in ("status", "years", "why")})
        if a["id"] == "X-A3":
            aa["nodes"] = A3_INTERCHANGES
        axes.append(aa)
    jmap = [{"joint_id": m["joint_id"], "axis": m["axis"]} for m in C["joints"]["items"]]
    spec = {
        "district": "golden",
        "version": 0,
        "boundary": "city.json#districts/golden",
        "targets": TARGETS,
        "centres": CENTRES,
        "axes": axes,
        "zones": zones,
        "lrt": {"line": [[round(x, 1), round(z, 1)] for x, z in LRT_LINE], "stations": LRT_STATIONS,
                "why": "ствол идёт к центрам, а не вдоль трассы: юг по Западному проспекту (как черновик), через А-3 к медкластеру и "
                       "Университетскому городу, главный центр у K-Park, затем снова на запад от А-3 — в обход дач «Пчёлка» и «Рассвет», "
                       "которые черновик lrt_v0 резал, — и на стык J027; станции через 0,9–1,3 км; три пересечения А-3 — на эстакадах"},
        "objects": OBJECTS,
        "phases": PHASES,
        "joints": jmap,
        "checks": C,
    }
    spec["checks"]["open_questions"] = OPEN_Q
    return spec


OPEN_Q = [
    "ЛЭП 220 кВ проходят через главный центр у K-Park и кампус «Көктерек» (охранные зоны 2 × 25 м). Убрать их в кабель в зелёных коридорах или перенести опоры в обход ядра? (кабель / обход)",
    "Аэропорт Growing-запад окажется у северо-западной границы Golden? Западное крыло Golden в схеме — резерв и лесопарк без зданий, так что заход свободен в любом случае; нужно ли держать его пустым и после 2050? (да / нет)",
]


def write_spec(spec):
    s = json.dumps(spec, ensure_ascii=False, indent=1)
    # keep coordinate pairs on one line so the file stays hand-editable
    import re
    s = re.sub(r"\[\n\s+(-?[\d.]+),\n\s+(-?[\d.]+)\n\s+\]", r"[\1, \2]", s)
    tmp = SPEC + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(s + "\n")
    os.replace(tmp, SPEC)
    print(f"[spec] {SPEC}: {os.path.getsize(SPEC) / 1e3:.0f} kB")


# ------------------------------------------------------------------ main
def main(draw=True):
    global TARGETS
    jobs = twin_targets()
    TARGETS = {"population_2050": 675000, "jobs_2050": jobs, "homes_2050": None,
               "source": "жители — CityStats.DistrictTarget2050k[1] = 675 тыс. (код двойника; = генплан № 727); "
                         f"рабочие места — двойник в контуре Golden city.json: buildings.csv, базовый сценарий, год ≤ 2050, "
                         f"формулы CityStats (м² на место: деловые 90, социальные 50, промышленность и энергия 100, досуг 120) = " + f"{jobs:,}".replace(",", " ")
                         + "; для сравнения генплан № 727 даёт Golden 337 400 мест (norms.json quarters.genplan_jobs_2050) — его контур другой; "
                           "квартир в коде двойника нет (homes_2050 = null), оценка схемы — checks.capacity.homes"}
    I = load_inputs()
    AXES[:] = [a for a in AXES if not a["id"].startswith(("X-P1", "X-P2"))] + river_paths(I)
    for ph in PHASES:
        ph["axes"] = [a["id"] for a in AXES if any(a["id"] == x or a["id"].startswith(x + "-") for x in ph["axes"])]
    built = build_zones(I)
    C = run_checks(I, built)
    spec = build_spec(I, built, C)
    write_spec(spec)
    print(json.dumps({k: C[k] for k in ("houses_hit_by_zones", "houses_hit_by_new_axes", "capacity", "zone_share_pct", "covered_ha", "district_ha")},
                     ensure_ascii=False, indent=1))
    print("joints met", C["joints"]["met"], "/", C["joints"]["count"], [m for m in C["joints"]["items"] if not m["met"]])
    print("registry", C["registry"]["rows_of_golden"], C["registry"]["with_row"], C["registry"]["missing"])
    if draw:
        import golden_draw
        golden_draw.draw(spec, I, built, OUT)
    return spec, I, built


if __name__ == "__main__":
    main(draw="--nodraw" not in sys.argv)
