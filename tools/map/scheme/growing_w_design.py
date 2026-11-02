"""Growing-West (growing_w) level-0 scheme: the hand design (centres, axes, zone seeds, airport) and the builder of
tools/map/spec/growing_w.json. Coordinates: Unity X/Z metres (X = E − 663000, Z = N − 4830000, UTM 43N).

    python3 -I tools/map/scheme/growing_w_design.py      # rebuild the spec from this design, then run the checks

After the first build the spec is the source of truth (hand-editable); growing_w_scheme.py checks and draws it."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "geo"))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, shape  # noqa: E402

import layers  # noqa: E402
import terrain  # noqa: E402
import twin  # noqa: E402

SPEC = os.path.join(HERE, "..", "spec")
OUT_SPEC = os.path.join(SPEC, "growing_w.json")
MODEL = "модель qTwin"

# ------------------------------------------------------------------ airport (model qTwin, placed by rule)
# Runway: 4 000 m, true bearing 095°/275°, centre (-16000, 1500). Chosen by a search over the plateau of the
# Growing-W tail (rwy search in the scheme notes): longitudinal slope ≤ 1 %, strip inside the district, no houses
# within 300 m, the 500 kV pair from PS Alma-500 ≥ 500 m from the runway and below the approach surfaces.
RWY = {"centre": (-16000.0, 1500.0), "bearing": 95.0, "length": 4000.0, "width": 45.0}


def rwy_frame():
    a = math.radians(RWY["bearing"])
    u = np.array([math.sin(a), math.cos(a)])          # along the runway (towards 095°)
    v = np.array([-math.cos(a), math.sin(a)])         # left of u = towards 005° (north side)
    return np.array(RWY["centre"]), u, v


def rwy_rect(a0, a1, b0, b1):
    """Rectangle in the runway frame: a along u from the centre, b along v (north positive)."""
    C, u, v = rwy_frame()
    pts = [C + u * a + v * b for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1))]
    return Polygon(pts)


def rwy_ends():
    C, u, v = rwy_frame()
    L = RWY["length"] / 2
    return C - u * L, C + u * L


# ------------------------------------------------------------------ centres
CENTRES = [
    {"id": "c_main", "kind": "main", "name_ru": "Центр Growing-запад «Каскелен»", "x": -4050, "z": 3250,
     "why": "там, где аэропортовая ось (магистраль и ЛРТ) пересекает Каскелен: центр на двух берегах реки, 4 км от А-3, ровная долина (уклон < 2 %), вне шумовой полосы ВПП"},
    {"id": "c_airport", "kind": "sub", "name_ru": "Аэросити «Алатау» (терминал и вокзал)", "x": -15300, "z": 2950,
     "why": "терминал аэропорта, вокзал «Алатау» и конечная ЛРТ в одном узле с северной стороны ВПП"},
    {"id": "c_dryport", "kind": "local", "name_ru": "Сухой порт и сортировочная станция", "x": -2300, "z": 650,
     "why": "у обходной ж/д и развязки А-3 у Жанаарны: контейнерный терминал, таможня, офисы логистики"},
    {"id": "c_westbank", "kind": "local", "name_ru": "Левобережный центр", "x": -5650, "z": 3900,
     "why": "повседневные услуги левого берега Каскелена у станции ЛРТ, в 10 минутах пешком от всех домов берега"},
    {"id": "c_north", "kind": "local", "name_ru": "Северный центр у реки", "x": -1050, "z": 6500,
     "why": "услуги для новых кварталов и дачных массивов севера, у набережной Каскелена и съезда с А-3"},
    {"id": "c_plateau", "kind": "local", "name_ru": "Технопарк «Плато»", "x": -9300, "z": 3300,
     "why": "сервисный центр западной промзоны у станции ЛРТ на аэропортовой оси: столовые, учебный центр, пожарное депо"},
]

# ------------------------------------------------------------------ axes (skeleton only)
A3_LINE = None  # filled from city.json growing_split
AXES = [
    {"id": "a3_ramps_s", "class": "expressway", "name_ru": "Съезды развязки А-3 у границы с Golden", "line": [[-1132, -3130], [-1021, -3204], [-870, -3262]],
     "status": "keep_existing", "years": [2025, 2025],
     "why": "существующие съезды развязки на стыке Golden / Growing (стыки J032–J037); остаются как есть"},
    {"id": "airport_trunk", "class": "trunk", "name_ru": "Аэропортовая магистраль",
     "line": [[-268, 1802], [-1500, 2150], [-2700, 2560], [-3350, 2800], [-4050, 3150], [-4600, 3165], [-5000, 3165], [-5600, 3150],
              [-6500, 2950], [-7700, 2800], [-9000, 2750], [-10400, 2900], [-11700, 2950], [-12400, 2750],
              [-13300, 2600], [-14400, 2750], [-15300, 2750], [-16600, 2650]],
     "status": "new", "years": [2030, 2041],
     "why": "единственная прямая связь аэропорта с А-3 (развязка км 44): участок до центра — к 2030, подъём на плато и до терминала — к 2041; обходит дачи, СЭС и посёлки, мост через Каскелен в центре, ЛЭП 500 кВ пересекает один раз под углом ≈ 45°"},
    {"id": "art_south", "class": "arterial", "name_ru": "Южная промышленная улица", "line": [[-570, 165], [-1800, 330], [-3300, 380], [-5000, 420], [-6200, 450], [-6900, 620]],
     "status": "new", "years": [2027, 2030],
     "why": "вдоль северной стороны обходной ж/д: обслуживает сухой порт, сортировочную станцию и хаб Rhenus, выходит на развязку А-3 у Жанаарны (стык J076)"},
    {"id": "art_k46", "class": "arterial", "name_ru": "Улица Енбек – Каскелен", "line": [[130, 3900], [-1000, 3850], [-2200, 3700], [-3350, 3500], [-4050, 3150]],
     "status": "new", "years": [2030, 2034],
     "why": "вторая связь центра с А-3 (развязка км 46,1, стык J072): продолжает дорогу на Енбек на запад"},
    {"id": "art_link", "class": "arterial", "name_ru": "Связь Южная – Аэропортовая", "line": [[-6900, 620], [-6600, 1600], [-6450, 2300], [-6500, 2950]],
     "status": "new", "years": [2034, 2038],
     "why": "соединяет промышленный юг с аэропортовой осью у подножия уступа, не заходя в жилые кварталы"},
    {"id": "art_plateau", "class": "arterial", "name_ru": "Дорога плато (север – юг)", "line": [[-9000, 2750], [-8900, 5200], [-8300, 7700], [-7600, 10200], [-7100, 12600], [-6200, 13700], [-3500, 13800], [-1200, 13780], [350, 13760]],
     "status": "new", "years": [2040, 2050],
     "why": "открывает западную промзону и резерв плато, выводит их на развязку А-3 км 55,9 (стыки J064–J067) по северу, мимо дачных массивов"},
    {"id": "blv_kaskelen", "class": "boulevard", "name_ru": "Набережная Каскелена", "line": [[-4050, 3150], [-3647, 3433], [-2907, 4274], [-2629, 4398], [-1942, 5148], [-1574, 5851], [-1055, 6291], [-666, 7142]],
     "status": "new", "years": [2030, 2045],
     "why": "главный бульвар района: пешеходная и велосипедная набережная по правому берегу от центра на север (≈ 120–190 м от русла, вне водоохранной полосы), на неё выходят школы и парки"},
    {"id": "blv_centre", "class": "pedestrian", "name_ru": "Пешеходная улица центра", "line": [[-4700, 3600], [-4050, 3420], [-3350, 3150], [-2900, 2900]],
     "status": "new", "years": [2031, 2036],
     "why": "пешеходная ось центра от станции ЛРТ «Центр» через мост на левый берег"},
    {"id": "dst_westbank", "class": "district", "name_ru": "Улица левого берега", "line": [[-6500, 2950], [-6100, 3900], [-5600, 4800], [-4700, 5600]],
     "status": "new", "years": [2034, 2040],
     "why": "главная улица левобережных кварталов у подножия уступа"},
    {"id": "dst_north", "class": "district", "name_ru": "Улица Северная", "line": [[-2200, 3700], [-1700, 4800], [-1100, 5700], [-1050, 6500], [-600, 7400]],
     "status": "new", "years": [2034, 2042],
     "why": "главная улица правобережных кварталов, параллельно набережной"},
]

LRT = {
    "line": [[-147, 2425], [-1500, 2350], [-2700, 2690], [-3350, 2900], [-4050, 3240], [-4700, 3390], [-5600, 3290],
             [-6500, 3090], [-7700, 2940], [-9000, 2890], [-10400, 3040], [-11700, 3090], [-12400, 2890], [-13300, 2740],
             [-14400, 2890], [-15300, 2900]],
    "stations": [
        {"id": "L1", "name_ru": "Каскелен-Восток", "x": -1450, "z": 2360},
        {"id": "L2", "name_ru": "Солнечная (СЭС)", "x": -2700, "z": 2690},
        {"id": "L3", "name_ru": "Центр Каскелен", "x": -3900, "z": 3167},
        {"id": "L4", "name_ru": "Левый берег", "x": -5300, "z": 3325},
        {"id": "L5", "name_ru": "Уступ", "x": -6500, "z": 3090},
        {"id": "L6", "name_ru": "Плато-Восток", "x": -7700, "z": 2940},
        {"id": "L7", "name_ru": "Технопарк", "x": -9000, "z": 2890},
        {"id": "L8", "name_ru": "Промзона Запад", "x": -10400, "z": 3040},
        {"id": "L9", "name_ru": "Грузовой терминал", "x": -11700, "z": 3090},
        {"id": "L10", "name_ru": "Аэропорт-Восток", "x": -13300, "z": 2740},
        {"id": "L11", "name_ru": "Аэропорт «Алатау»", "x": -15300, "z": 2900},
    ],
    "why": "ветка ствола ЛРТ от А-3 (стык J062) через центр района к терминалу аэропорта: заменяет черновик west_growing, который вёл к старому месту аэропорта (−5900, 8300); идёт рядом с аэропортовой магистралью, станции через 1,2–1,6 км, подъём на плато по уступу ≈ 3 %, модель qTwin",
}

# rail spur to the airport (new, modelled): junction on the bypass inside Growing-W, climb ≈ 1 % to the plateau
RAIL_SPUR = [[-5600, -200], [-6900, 120], [-8200, 900], [-9600, 1750], [-10900, 2450], [-12000, 2620], [-13300, 2560], [-14400, 2700], [-15300, 2800]]

# ------------------------------------------------------------------ zone seeds (priority order after the fixed layers)
ZONE_SEEDS = [
    # id, use, polygon (rough; clipped to the district and to higher-priority zones), density, years, name, why
    ("ctr_main", "mixed_centre", [[-4900, 2950], [-4500, 2700], [-3600, 2650], [-2900, 2700], [-2700, 3050], [-3100, 3550], [-3800, 3800], [-4600, 3900], [-5100, 3500]],
     {"floors_typical": 9, "far": 1.4, "homes_per_ha": 62, "jobs_per_ha": 100}, [2031, 2040], "Центр «Каскелен»",
     "плотный центр на двух берегах у станции ЛРТ: офисы, торговля, жильё над первыми этажами; до 12 этажей (< 50 м, без согласования аэродромов)"),
    ("campus_voc", "campus", [[-2700, 3050], [-1900, 3000], [-1700, 3600], [-2400, 3700], [-3000, 3550]],
     {"floors_typical": 4, "far": 0.5, "jobs_per_ha": 30}, [2036, 2042], "Профтехинститут (авиация, логистика)",
     "вуз на 10–15 тыс. учащихся рядом с центром и ЛРТ; участок по норме 30–75 м² на учащегося"),
    ("biz_a3", "business", [[-1000, 1000], [-300, 1000], [-150, 2400], [0, 4600], [200, 7600], [-300, 7600], [-550, 4600], [-800, 2400]],
     {"floors_typical": 4, "far": 0.5, "jobs_per_ha": 50}, [2030, 2045], "Деловая полоса у А-3",
     "офисы, шоурумы, сервис вдоль А-3; держат шум трассы, жильё не ближе 50 м от проезжей части"),
    ("log_dryport", "logistics", [[-5600, -150], [-700, -100], [-1100, 1000], [-1100, 2000], [-3150, 2300], [-3150, 900], [-4600, 900], [-5000, 1300], [-5600, 900]],
     {"floors_typical": 2, "far": 0.25, "jobs_per_ha": 20}, [2028, 2045], "Сухой порт, сортировочная станция, хаб Rhenus",
     "у обходной ж/д и А-3, под глиссадой ВПП, где жильё ставить нельзя; ветер E/NE уносит пыль от жилья"),
    ("ind_south", "industry", [[-7600, -800], [-4600, -1700], [-850, -3300], [-650, -100], [-7600, -100]],
     {"floors_typical": 2, "far": 0.25, "jobs_per_ha": 25}, [2032, 2050], "Южная промзона",
     "к югу от обходной ж/д, у ПС «Алма»: лёгкая промышленность и склады; с подветренной (юго-западной) стороны от жилья"),
    ("log_rhenus", "logistics", [[-7800, -650], [-5600, -150], [-5600, 900], [-6200, 1300], [-7600, 1500], [-8000, 400]],
     {"floors_typical": 2, "far": 0.25, "jobs_per_ha": 20}, [2030, 2040], "Логистика у развилки ж/д",
     "развилка обходной ж/д и аэропортовой ветки: склады и хаб под глиссадой"),
    ("res_centre_e", "residential_high", [[-3150, 2300], [-1100, 2000], [-900, 2400], [-750, 3900], [-1700, 3950], [-2600, 3900], [-3400, 4100], [-3100, 3550], [-2700, 3050], [-2900, 2700]],
     {"floors_typical": 10, "far": 1.0, "homes_per_ha": 94, "jobs_per_ha": 10}, [2032, 2045], "Кварталы у ЛРТ (правый берег)",
     "9–12 этажей в 800 м от станций ЛРТ, к северу от шумовой полосы ВПП"),
    ("res_westbank", "residential_mid", [[-6900, 3000], [-6600, 2300], [-5000, 2600], [-4600, 3900], [-5300, 4300], [-6200, 4300], [-6800, 3900]],
     {"floors_typical": 6, "far": 0.6, "homes_per_ha": 57, "jobs_per_ha": 8}, [2034, 2045], "Левобережные кварталы",
     "5–9 этажей между рекой и уступом, вид на реку и горы; вокруг существующего посёлка"),
    ("res_north", "residential_mid", [[-750, 3900], [-600, 5300], [-1500, 5400], [-2400, 5300], [-3300, 5000], [-3900, 4300], [-3400, 4100], [-2600, 3900], [-1700, 3950]],
     {"floors_typical": 6, "far": 0.6, "homes_per_ha": 57, "jobs_per_ha": 8}, [2036, 2048], "Правобережные кварталы вдоль реки",
     "5–9 этажей вдоль набережной, полицентр у реки"),
    ("res_low_north", "residential_low", [[-500, 6300], [-400, 7600], [-1300, 8200], [-2400, 8300], [-3400, 8400], [-3900, 7600], [-3300, 6600], [-2600, 5900], [-1500, 6400]],
     {"floors_typical": 3, "far": 0.22, "homes_per_ha": 21, "jobs_per_ha": 4}, [2038, 2050], "Малоэтажные кварталы у дачных массивов",
     "2–3 этажа рядом с дачами: та же этажность, что у соседей; в 10 км от аэродрома Жетыген — всё по согласованию, поэтому низко"),
    ("ind_plateau", "industry", [[-12600, 2200], [-10600, 1300], [-8200, 300], [-7400, 1600], [-7600, 3500], [-8000, 4300], [-12000, 4100]],
     {"floors_typical": 2, "far": 0.25, "jobs_per_ha": 25}, [2034, 2050], "Западная промзона (плато)",
     "плато 600–640 м к западу от жилья: заводы с подветренной стороны при ветрах E/NE, вдоль аэропортовой оси и ж/д ветки"),
    ("log_cargo", "logistics", [[-14300, 2000], [-12600, 2200], [-12600, 4600], [-13800, 4900], [-14500, 4300]],
     {"floors_typical": 2, "far": 0.25, "jobs_per_ha": 20}, [2041, 2050], "Грузовой терминал и авиалогистика",
     "склады и экспресс-почта у лётного поля, к востоку от терминала"),
    ("res_reserve_valley", "reserve", [[-5600, 4700], [-4200, 4900], [-3300, 5000], [-2600, 5900], [-3300, 6600], [-3900, 7600], [-3400, 8400], [-1300, 8200], [-400, 7600], [-300, 7600], [300, 15700], [-3600, 15700], [-4300, 12000], [-4800, 9000], [-6000, 6000]],
     {}, [2050, 2060], "Резерв долины (после 2050)",
     "долина к северу от новых кварталов и между дачными массивами: сады и агропарк до 2050, жильё после 2050; на севере — 10 км от аэродрома Жетыген, где любое здание по согласованию"),
    ("res_reserve_plateau", "reserve", [[-12600, 4600], [-11400, 6000], [-9800, 6400], [-8200, 5600], [-7600, 3500], [-6000, 6000], [-4800, 9000], [-4300, 12000], [-3600, 15700], [-9500, 16300], [-10400, 11000], [-11500, 8000], [-13500, 6000]],
     {}, [2050, 2060], "Резерв плато (после 2050)",
     "свободное ровное плато за пределами потребности 2050 года: второй этап промзоны и логистики после 2050"),
]


def load_ctx():
    c = json.load(open(os.path.join(SPEC, "city.json"), encoding="utf-8"))
    W = Polygon(c["districts"]["growing_w"]["polygon"])
    E = Polygon(c["districts"]["growing_e"]["polygon"])
    return c, W, E


def houses(W):
    """Existing houses in Growing-W: Overture buildings + twin existing_osm points. Returns shapely array."""
    bg, bp = layers.load("buildings")
    sel = np.flatnonzero(shapely.intersects(W, bg))
    B = twin.buildings()
    ex = B[B.source == "existing_osm"]
    pts = shapely.points(ex.x.values, ex.z.values)
    pw = pts[shapely.contains(W, pts)]
    return np.concatenate([bg[sel], pw]).astype(object)


def utility_own(reg):
    """Footprints of kept utilities (their own buildings are not houses)."""
    g = [shape(r["geom"]).buffer(30) for r in reg["rows"] if r["id"] in ("ps_alma_500", "ps_220_golden_osm", "ses_osm_pv")]
    return shapely.union_all(g)


def village_clusters(W, H, own):
    keep = H[~shapely.within(H, own)]
    U = shapely.union_all([g.buffer(75) for g in keep]).buffer(-45)
    parts = [p for p in getattr(U, "geoms", [U]) if not p.is_empty]
    out = []
    for p in parts:
        n = int(shapely.intersects(p, keep).sum())
        q = p.buffer(20).simplify(15)
        out.append((q, n))
    return out


def build():
    c, W, E = load_ctx()
    reg = json.load(open(os.path.join(SPEC, "registry.json"), encoding="utf-8"))
    T = terrain.terrain()
    H = houses(W)
    own = utility_own(reg)
    zones = []          # (id, use, geom, density, years, name, why)
    taken = shapely.Polygon()

    def add(zid, use, geom, dens, years, name, why):
        nonlocal taken
        g = geom.intersection(W).difference(taken)
        g = g.buffer(0)
        if g.is_empty or g.area < 1e3:
            return
        zones.append([zid, use, g, dens, years, name, why])
        taken = taken.union(g)

    # 1 villages
    vc = village_clusters(W, H, own)
    vc.sort(key=lambda t: -t[0].area)
    big = [t for t in vc if t[1] >= 8]
    small = [t for t in vc if t[1] < 8]
    for i, (g, n) in enumerate(big):
        add(f"vil_{i + 1:02d}", "village_existing", g, {"houses": n}, [2025, 2025], "Существующий посёлок / дачный массив",
            f"{n} домов (Overture/OSM и existing_osm двойника) остаются; новые улицы обходят их")
    if small:
        add("vil_farms", "village_existing", shapely.union_all([g for g, n in small]), {"houses": sum(n for g, n in small)}, [2025, 2025],
            "Отдельные усадьбы и зимовки", "мелкие группы до 7 построек: остаются на месте, получают подъезды")
    # 2 kept utilities (substations, SES)
    for r in reg["rows"]:
        if r["id"] in ("ps_alma_500", "ps_220_golden_osm", "ses_osm_pv"):
            nm = {"ps_alma_500": "ПС 500 кВ «Алма»", "ps_220_golden_osm": "ПС 220 кВ (OSM)", "ses_osm_pv": "Поле СЭС"}[r["id"]]
            add("util_" + r["id"], "utility", shape(r["geom"]).buffer(30), {}, [2025, 2025], nm, "существующий объект реестра, остаётся")
    # 3 river Kaskelen: water + 35 m strip + floodplain park ≈ 150 m each side
    wg, wp = layers.load("water")
    kas = [g for g, p in zip(wg, wp) if p.get("name") in ("Қаскелең", "Каскелен") and g.intersects(W)]
    wat = [g for g in wg if g.geom_type in ("Polygon", "MultiPolygon") and g.intersects(W)]
    riv = shapely.union_all([g.buffer(150) for g in kas] + [g.buffer(60) for g in wat])
    add("river_kaskelen", "waterfront", riv, {}, [2030, 2045], "Река Каскелен и прибрежный парк",
        "вода, водоохранная полоса ≥ 35 м и пойма: только парк, набережная и велодорожка, без капитальных зданий")
    # lakes at the north-west border (Zhamankum group): 500 m water-protection zone for lakes > 2 km² → nature park
    lakes = [g for g in wg if g.geom_type in ("Polygon", "MultiPolygon") and g.area > 2e5 and g.distance(W) < 600 and not g.intersects(W.buffer(-1))]
    add("park_lakes", "park", shapely.union_all([g.buffer(500 if g.area > 2e6 else 300) for g in lakes]), {}, [2025, 2050],
        "Природный парк у озёр Жаманкум", "водоохранная зона озёр (500 м у озёр > 2 км², 300 м у меньших): без застройки; держит птиц подальше от аэропорта")
    # 4 power corridors (≈ 40 m each side) and the bypass rail corridor (30 m)
    ig, ip = layers.load("infrastructure")
    pl = shapely.union_all([g for g, p in zip(ig, ip) if p.get("class") in ("power_line", "minor_line") and g.intersects(W)])
    add("util_power", "utility", pl.buffer(40), {}, [2025, 2025], "Коридоры ЛЭП 220–500 кВ",
        "охранные зоны ВЛ (≈ 25–30 м от крайнего провода, аналог ПП РФ № 160): без зданий и деревьев, дороги только поперёк")
    rl, rp = layers.load("rail")
    rr = shapely.union_all([g for g in rl if g.intersects(W)])
    add("util_rail", "utility", rr.buffer(30), {}, [2025, 2025], "Обходная ж/д Жетыген – Казыбек би", "существующая линия (12.2025) и её полоса отвода")
    # 5 airport
    p0, p1 = rwy_ends()
    L = RWY["length"] / 2
    add("air_airside", "utility", rwy_rect(-L - 300, L + 300, -200, 950), {"floors_typical": 1}, [2041, 2045], "Аэропорт: лётное поле",
        "ВПП 4 000 × 45 м, полоса ВПП 280 м, концевые зоны 240 м, рулёжные дорожки и перрон; модель qTwin")
    add("air_terminal", "business", rwy_rect(-1900, 1300, 950, 1900), {"floors_typical": 4, "far": 0.6, "jobs_per_ha": 60}, [2041, 2045],
        "Терминал, вокзал «Алатау», аэросити", "терминал на 15 млн пасс./год, вокзал, гостиницы и офисы аэросити; модель qTwin")
    add("air_reserve", "reserve", rwy_rect(-L - 2500, L + 400, -1500, 3000), {}, [2041, 2060], "Охранная зона аэропорта",
        "зона шума и безопасности вокруг лётного поля: без жилья; поля, СЭС, резерв расширения")
    # 6 escarpment belt: smoothed terrain 565–600 m and slope ≥ 3 % → forest park
    xs = np.arange(-18600, 600, 100.0); zs = np.arange(-3300, 16400, 100.0)
    X, Z = np.meshgrid(xs, zs)
    from scipy.ndimage import gaussian_filter
    Hh = gaussian_filter(T.height(X, Z), 2)
    S = np.hypot(*np.gradient(Hh, 100.0))
    m = (Hh > 566) & (Hh < 600) & (S > 0.025) & (X > -12000)
    cells = [shapely.box(x - 50, z - 50, x + 50, z + 50) for x, z in zip(X[m], Z[m])]
    belt = shapely.union_all(cells).buffer(60).buffer(-60)
    belt = shapely.union_all([p for p in getattr(belt, "geoms", [belt]) if p.area > 30e4]).buffer(150).buffer(-150).simplify(50)
    add("park_escarpment", "park", belt, {}, [2034, 2050], "Лесопарк «Уступ»",
        "склон между долиной и плато (уклон 3–8 %): лесопарк, смотровые площадки, зелёный барьер между промзоной плато и жильём долины")
    # 7 hand seeds
    for zid, use, poly, dens, years, name, why in ZONE_SEEDS:
        add(zid, use, Polygon(poly), dens, years, name, why)
    # 8 remainder: valley → residential_low, plateau → reserve
    rest = W.difference(taken)
    for i, p in enumerate([p for p in getattr(rest, "geoms", [rest]) if p.area > 1e3]):
        x, z = p.representative_point().coords[0]
        h = T.height(x, z)
        if h < 575 and p.area < 40e4:
            add(f"park_rest_{i}", "park", p, {}, [2035, 2050], "Сквер / зелёный клин", "остаток долины между зонами: зелень и площадки")
        elif h < 575:
            add(f"res_rest_{i}", "reserve", p, {}, [2050, 2060], "Резерв долины", "остаток долины: резерв после 2050")
        else:
            add(f"res_rest_{i}", "reserve", p, {}, [2050, 2060], "Резерв", "остаток плато: резерв после 2050")
    return c, W, E, reg, zones, H


if __name__ == "__main__":
    c, W, E, reg, zones, H = build()
    tot = sum(z[2].area for z in zones)
    print(len(zones), "zones", round(tot / 1e4), "ha of", round(W.area / 1e4))
    from collections import defaultdict
    a = defaultdict(float)
    for z in zones:
        a[z[1]] += z[2].area / 1e4
    for k, v in sorted(a.items(), key=lambda t: -t[1]):
        print(f"  {k:18s} {v:8.0f} ha {100 * v / (W.area / 1e4):5.1f} %")
