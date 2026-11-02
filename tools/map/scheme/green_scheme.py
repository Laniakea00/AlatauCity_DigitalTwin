"""Green district, level 0: the scheme (spec tools/map/spec/green.json + checks + picture).

    python3 -I tools/map/scheme/green_scheme.py            # build spec from the design below, run checks, draw
    python3 -I tools/map/scheme/green_scheme.py --draw     # only re-run checks and redraw from the existing green.json

The design (centres, axes, zone outlines, densities, objects, queues) is written in this file in Unity X/Z metres.
Zone outlines are rough design boxes; the script clips them in priority order against the ground truth of level 0
(district polygon, Kapchagay 485 m line + 45–50 m setback, water, existing houses, airfield, transport and power corridors),
so the zones never overlap and never take flooded land or existing houses. The result is written to green.json, which
is then the hand-editable source; --draw re-checks and redraws it without rebuilding.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "geo"))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box  # noqa: E402
from shapely.ops import linemerge, nearest_points, unary_union  # noqa: E402

import frames  # noqa: E402
import layers  # noqa: E402
import terrain  # noqa: E402
import twin  # noqa: E402

SPEC = os.path.join(frames.SPEC_DIR, "green.json")
CITY = os.path.join(frames.SPEC_DIR, "city.json")
REG = os.path.join(frames.SPEC_DIR, "registry.json")
OUTDIR = os.environ.get("GREEN_SCHEME_OUT", "/mnt/project-files/alatau_stage7/level0/schemes/green")
M2_PER_RES = 30.0                                             # CityStats.M2PerResident
M2_PER_JOB = {"business": 90.0, "social": 50.0, "industry": 100.0, "leisure": 120.0}   # CityStats.M2PerJob
BUILT = {"mixed_centre", "business", "residential_high", "residential_mid", "residential_low", "campus", "medical",
         "industry", "logistics", "utility", "sport"}           # where people live or work
ATTR = "© OpenStreetMap contributors, Overture Maps Foundation"


# ----------------------------------------------------------------------------------------------------------------- ground
def ground():
    c = json.load(open(CITY, encoding="utf-8"))
    G = Polygon(c["districts"]["green"]["polygon"])
    kg, kp = layers.load("derived/kapchagay_levels")
    lv = {int(p["real_m"]): g.buffer(0) for g, p in zip(kg, kp)}
    F = lv[485].intersection(G)
    # setback line: 485 m polygon + ≈ 50 m, small inlets closed, simplified (stays ≥ 45 m off the 485 line)
    FS = lv[485].buffer(110).buffer(-40).simplify(20).intersection(G)
    wg, wp = layers.load("water")
    W = unary_union([g for g in wg if g.geom_type.endswith("Polygon") and g.intersects(G)]).buffer(0).intersection(G)
    W = unary_union([p for p in getattr(W, "geoms", [W]) if p.geom_type == "Polygon" and p.area > 3e4])
    ig, ip = layers.load("infrastructure")
    PL = unary_union([g for g, p in zip(ig, ip) if p.get("class") == "power_line" and g.intersects(G.buffer(100))])
    ug, up = layers.load("land_use")
    MIL = unary_union([g for g, p in zip(ug, up) if p.get("subtype") == "military" and g.intersects(G)]).intersection(G)
    RWY = unary_union([g for g, p in zip(ig, ip) if p.get("class") == "runway" and g.geom_type.endswith("Polygon") and g.intersects(G)])
    TRACK = unary_union([g for g, p in zip(ug, up) if p.get("subtype") == "recreation" and p.get("class") == "track" and g.intersects(G)])
    rl, _ = layers.load("rail")
    RAIL = unary_union([g for g in rl if g.intersects(G.buffer(300))])
    rg, rp = layers.load("roads")
    A3 = unary_union([g for g, p in zip(rg, rp) if p.get("class") == "motorway" and g.intersects(G.buffer(300))])
    # existing houses: Overture buildings + the twin's existing_osm footprints (points ± 6 m)
    bg, _ = layers.load("buildings")
    HOUSES = bg[shapely.intersects(G.buffer(200), bg)]
    B = twin.buildings()
    ex = B[(B.source == "existing_osm")]
    ex = ex[shapely.contains_xy(G.buffer(200), ex.x.values, ex.z.values)]
    TWIN_EX = np.array([Point(x, z).buffer(6, quad_segs=2) for x, z in zip(ex.x.values, ex.z.values)], dtype=object)
    sett = {s["name"]: Polygon(s["polygon"]) for s in c["existing_2025"]["settlements"]}
    return dict(c=c, G=G, lv=lv, F=F, FS=FS, W=W, PL=PL, MIL=MIL, RWY=RWY, TRACK=TRACK, RAIL=RAIL, A3=A3,
                HOUSES=HOUSES, TWIN_EX=TWIN_EX, sett=sett)


def runway_axis(RWY):
    """Runway centreline ends (south, north) from the OSM runway polygon (minimum rotated rectangle)."""
    r = RWY.minimum_rotated_rectangle
    pts = np.asarray(r.exterior.coords)[:4]
    e = [(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    e.sort(key=lambda ab: np.hypot(*(ab[1] - ab[0])))
    a = (e[0][0] + e[0][1]) / 2; b = (e[1][0] + e[1][1]) / 2
    return (a, b) if a[1] < b[1] else (b, a)


def funnel(end, other, length=4000, w0=150, div=0.15):
    d = (end - other) / np.hypot(*(end - other)); n = np.array([-d[1], d[0]])
    w1 = w0 + div * length
    return Polygon([end + n * w0, end + d * length + n * w1, end + d * length - n * w1, end - n * w0])


def villages(g):
    """Existing settlements: clusters of existing houses (Overture + twin existing_osm) linked within 300 m; each cluster is the convex hull
    of its houses + 40 m (named OSM settlement outlines of Arna, Kuygan and Konaev added), so every existing house is inside a village zone."""
    G = g["G"]
    hs = [h for h in list(g["HOUSES"]) + list(g["TWIN_EX"]) if h.intersects(G)]
    cl = unary_union([h.buffer(150, quad_segs=2) for h in hs])
    tree = shapely.STRtree(hs)
    out = []
    for c in getattr(cl, "geoms", [cl]):
        idx = tree.query(c, predicate="intersects")
        hull = unary_union([hs[i] for i in idx]).convex_hull.buffer(40, quad_segs=2).simplify(10)
        out.append(hull)
    for n in ("Арна", "Құйған", "Қонаев"):
        out.append(g["sett"][n].simplify(10))
    V = unary_union(out).intersection(G).buffer(0)
    return unary_union([Polygon(p.exterior) for p in getattr(V, "geoms", [V]) if p.geom_type == "Polygon"]).intersection(G)


# ----------------------------------------------------------------------------------------------------------------- design
CENTRES = [
    dict(id="c_green_city", kind="main", name_ru="Green-Сити", x=3050, z=21700,
         why="Главный центр у воды: пересечение ЛРТ, Озёрного проспекта (развязка А-3 «Green-Север») и Бульвара к озеру; "
             "отсюда 2 км бульвара до мыса с курортом и доминантой. Участок выше 485 м (488–492 м), ровный."),
    dict(id="c_arnaut", kind="sub", name_ru="Арнаутская", x=2800, z=18935,
         why="Районный центр южной половины: станция ЛРТ на существующей улице Арнаутской, которая связывает развязку А-3 км 61, "
             "станцию Іле и село Арна мостом через Каскелен; рядом больница района."),
    dict(id="c_ile", kind="sub", name_ru="Іле (вокзал)", x=1500, z=17250,
         why="Ворота Green с железной дороги: существующая станция Іле (Турксиб, пригородные поезда Алматы – Конаев), пересадка на автобус до ЛРТ; "
             "деловой пояс вдоль путей."),
    dict(id="c_ircc", kind="sub", name_ru="Курорт Капчагай (IRCC)", x=4650, z=21300,
         why="Курортно-развлекательный центр 100 га на мысу, обращённом к водохранилищу; ≥ 500 м от А-3 (норма для зон отдыха), "
             "выше 485 м с отступом; перед ним береговой парк с пляжами."),
    dict(id="c_marina", kind="local", name_ru="Марина и северные пляжи", x=4800, z=25150,
         why="Тихая бухта между Конаевым и песчаной косой: вода у берега при нынешнем уровне 477–479 м; существующая дорога «На ASP Arena»; "
             "только причалы и пляжные павильоны (их можно ниже 485 м)."),
    dict(id="c_west", kind="local", name_ru="Западные террасы", x=-2300, z=19050,
         why="Центр террасного жилья на склоне к западу от А-3 (560–600 м, вид на озеро); на продолжении Арнаутской через развязку км 61."),
    dict(id="c_east", kind="local", name_ru="Восточный берег", x=12900, z=17250,
         why="Центр курортов и малоэтажного жилья восточного берега на Восточной береговой; > 4,5 км от ВПП Жетыгена."),
    dict(id="c_kuygan", kind="local", name_ru="Құйған", x=3700, z=13800,
         why="Первая станция ЛРТ в Green со стороны Growing; обслуживает село Куйган и Южный квартал."),
]

# axes: (id, class, name, line, status, years, why, extra)
AXES = [
    ("a3", "expressway", "Трасса А-3 Алматы – Конаев",
     [[233, 15652], [195, 16358], [170, 16855], [300, 18200], [421, 19066], [600, 20422], [681, 21593], [716, 22141], [749, 22629]],
     "keep_existing", [2025, 2025],
     "Существующая скоростная дорога (OSM); все узлы в разных уровнях: существующая развязка км 61 и новая «Green-Север» в 2,6 км к северу (не чаще 1,6 км).",
     {"nodes": [{"at": [425, 18984], "type": "развязка (существующая, км ≈ 61)", "status": "keep_existing", "years": [2025, 2025]},
                {"at": [690, 21650], "type": "ромб «Green-Север» (новая)", "status": "new", "years": [2030, 2032]}]}),
    ("lrt_south", "lrt_corridor", "ЛРТ, участок Құйған – Арнаутская",
     [[3740, 13067], [3700, 14100], [3680, 15250], [3050, 16350], [2750, 17550], [2800, 18930], [2750, 20100]],
     "new", [2029, 2032],
     "Ствол ЛРТ из Growing (стык J046) проходит не по берегу, как в черновике, а по оси жилого пояса между Турксибом и Каскеленом: "
     "у станций жильё с обеих сторон, а не наполовину вода.", {"bridges": [{"at": [3740, 13075], "over": "край русла Каскелена у стыка J046", "type": "мост ЛРТ"}]}),
    ("lrt_north", "lrt_corridor", "ЛРТ, участок Арнаутская – Green-Сити – Конаев",
     [[2750, 20100], [2900, 21150], [3050, 21700], [2950, 22550], [2706, 23376]],
     "new", [2033, 2036],
     "Продолжение ствола через главный центр к стыку J052 (на Конаев); в черновике конец линии стоял в зоне затопления у Конаева.", {}),
    ("prosp_green", "arterial", "Проспект Green (ЛРТ по оси)",
     [[3700, 14100], [3680, 15250], [3050, 16350], [2750, 17550], [2800, 18930], [2750, 20100], [2900, 21150], [3050, 21700], [2950, 22550]],
     "new", [2028, 2034],
     "Главная улица района вдоль ЛРТ: бульварный профиль, станции между перекрёстками; строится раньше кварталов, которые обслуживает.", {}),
    ("arnaut", "arterial", "Улица Арнаутская (реконструкция) и мост на Арну",
     [[470, 19000], [1100, 18975], [2800, 18935], [3500, 18890], [4300, 18830], [5016, 18737], [5707, 18857]],
     "keep_existing", [2027, 2030],
     "Существующая улица (OSM, третьестепенная) от развязки А-3 км 61 до Арны: расширяется до магистральной, путепровод над Турксибом.", {}),
    ("arnaut_w", "district", "Арнаутская-Запад (к террасам)",
     [[397, 18990], [-400, 19000], [-1300, 19010], [-2300, 19050]],
     "new", [2034, 2037],
     "Связь развязки км 61 с центром Западных террас; пересекает коридоры ЛЭП 500 кВ поперёк.", {}),
    ("ozerny", "arterial", "Озёрный проспект",
     [[690, 21650], [1550, 21650], [3050, 21700], [3900, 21600]],
     "new", [2030, 2033],
     "От новой развязки А-3 «Green-Север» над Турксибом к главному центру и курорту.", {}),
    ("ozerny_w", "district", "Северная улица (к террасам)",
     [[690, 21650], [-300, 21680], [-1300, 21720], [-2300, 21800]],
     "new", [2036, 2039],
     "Западная ветка развязки «Green-Север» к северной части террас.", {}),
    ("terr", "district", "Террасная улица",
     [[-2300, 17600], [-2300, 19050], [-2300, 21800]],
     "new", [2036, 2040],
     "Улица вдоль склона, от неё террасы спускаются к А-3; на обоих концах — Арнаутская-Запад и Северная.", {}),
    ("dubler_a3w", "district", "Дублёр А-3 (запад)",
     [[-250, 15900], [-300, 17600], [-330, 19000], [-350, 21680]],
     "new", [2034, 2036],
     "Улица через деловой пояс в 0,5–1 км западнее А-3: въезды к участкам с дублёра, не с трассы; связывает Арнаутскую-Запад и Северную.", {}),
    ("heat_st", "district", "Проезд к тепловой станции",
     [[2950, 22550], [3700, 22470]],
     "new", [2032, 2034],
     "Подъезд от Проспекта Green к станции тепловых насосов (генплан), выше 485 м.", {}),
    ("track_st", "district", "Улица к автодрому",
     [[-2300, 21800], [-2450, 22700], [-2700, 23600]],
     "new", [2036, 2040],
     "Продолжение Террасной улицы к существующему автодрому (OSM): ближайшая улица общего пользования к нему сейчас в 1,6 км.", {}),
    ("privokzal", "arterial", "Привокзальная улица",
     [[1450, 16400], [1400, 17250], [1500, 18975], [1550, 21650]],
     "new", [2027, 2031],
     "Вдоль Турксиба в 250–350 м от путей: подъезд к станции Іле и к деловому поясу, который закрывает жильё от шума дороги и путей.", {}),
    ("yuzh", "district", "Южная улица",
     [[1450, 16400], [2200, 15850], [3360, 15900]],
     "new", [2027, 2031],
     "Связывает Привокзальную с Проспектом Green у станции «Южный».", {}),
    ("blv_lake", "boulevard", "Бульвар к озеру",
     [[3050, 21700], [3900, 21600], [4600, 21480], [5150, 21380]],
     "new", [2033, 2037],
     "Пешеходный бульвар 2 км от станции ЛРТ Green-Сити через курорт к доминанте на мысу и береговому парку.", {}),
    ("east_link", "arterial", "Мост на Восточный берег",
     [[3360, 15900], [3900, 15980], [4400, 15960], [5300, 16000], [6000, 16500], [6700, 17350], [7600, 17620], [8650, 17660], [9300, 17650]],
     "new", [2035, 2038],
     "Связь ядра с востоком в обход аэродрома с севера: мост 350 м через Каскелен там, где русло самое узкое, и мост через пойму Малой Алматинки "
     "(≈ 230 м ниже 485 м, низ пролёта выше 485,5 м); под зоной подхода к ВПП — только дорога, без застройки.",
     {"bridges": [{"at": [4980, 15985], "over": "Каскелен", "type": "мост"}, {"at": [7450, 17580], "over": "пойма Малой Алматинки (ниже 485 м)", "type": "мост"}]}),
    ("bereg_e", "arterial", "Восточная береговая",
     [[9300, 17650], [11000, 17500], [12600, 17300], [15000, 17000], [17300, 16700], [18250, 16600]],
     "new", [2035, 2040],
     "Даёт дорогу курортам восточного берега (в двойнике 1 908 домов дальше 200 м от дорог); идёт по краю застройки выше 485 м, до границы города.", {}),
    ("east_n", "arterial", "Жетыгенская (к Восточному берегу)",
     [[7572, 11713], [7900, 13030], [8270, 14500], [8650, 16050], [9020, 17550], [9300, 17650]],
     "keep_existing", [2034, 2036],
     "Существующая дорога из Жетыгена на север (OSM) вдоль восточной стороны аэродрома: реконструкция; участок севернее 485 м остаётся подъездом к пляжу.", {}),
    ("tolai", "district", "Октябрь-Толай",
     [[13654, 10572], [14357, 11322], [14530, 11981], [14709, 15352], [15122, 15999], [15233, 16971]],
     "keep_existing", [2025, 2025],
     "Существующая дорога (OSM) с юга к восточному берегу.", {}),
    ("log_st", "district", "Улица логистического парка",
     [[7800, 12400], [9500, 12550], [11000, 12800], [12900, 12700]],
     "new", [2038, 2041],
     "Вдоль ж/д Жетыген – Алтынколь с её северной стороны: подъезд к логистике рядом с ТЛЦ «Жетыген».", {}),
    ("prom_c", "pedestrian", "Набережная Green-Сити",
     [[6540,19950],[6200,20070],[6130,20310],[6180,20470],[6050,20570],[5850,20570],[5680,20490],[5480,20690],[5420,20870],[5500,21010],[5450,21220],[5340,21340],[5410,21550],[5350,21710],[5160,21780],[4940,22160],[4850,22220],[4670,22220],[4430,22200],[4230,22070],[4110,22120],[4080,22240],[4140,22380],[4310,22490],[4270,22750],[4540,22870],[4540,22970],[4210,23100],[3830,22730],[3520,22610],[3310,22830],[3320,23080]],
     "new", [2033, 2040],
     "Пешеходная и велосипедная набережная 7,2 км между застройкой и линией 485 м (линия отступа минус 25 м), от залива у Арны до пляжей севернее "
     "Green-Сити; устья оврагов (≈ 170 м ниже 485 м) — мостками. Трасса — «модель qTwin».", {}),
    ("prom_e", "pedestrian", "Набережная Восточного берега",
     [[10320,18880],[10540,18840],[10560,18550],[10720,18310],[11040,18120],[11070,18000],[11150,17940],[11480,18080],[11690,18020],[12030,18090],[12330,17930],[12540,18110],[12670,18000],[12820,18010],[13130,17780],[13340,17890],[13560,17880],[13690,17970],[13900,17980],[14090,17840],[14400,17970],[14580,18210],[14750,18250],[14920,18460],[15300,18300],[15490,18310],[15700,18400],[15870,18630],[16080,18570],[16160,18310],[16120,18150],[16230,18060],[16360,18100],[16440,18280],[16620,18230],[16780,18380],[17030,18220],[17250,18160],[17510,18250]],
     "new", [2038, 2045],
     "Набережная 9,2 км вдоль отелей и малоэтажки Восточного берега, параллельно Восточной береговой: выход к пляжам; ≈ 280 м через устья оврагов ниже 485 м — мостками. "
     "Трасса — «модель qTwin».", {}),
    ("se_main", "arterial", "Дорога на юго-востоке (черновик T-M052)",
     [[17823, 9888], [18393, 10155], [18606, 10555]],
     "keep_twin", [2025, 2025],
     "Магистраль черновика двойника на границе города (стыки J060, J061); перепроектирование не нужно.", {}),
]

# zones in priority order: (id, use, name, design polygon or special, density, years, why, queue)
D = {  # density templates: floors, FAR (gross), housing share, m² per job for the rest
    "gc": dict(floors_typical="6–12 (доминанты до 30 эт. — по согласованию)", far=2.0, housing_share=0.35, job_m2=90),
    "sc": dict(floors_typical="5–9", far=1.6, housing_share=0.50, job_m2=90),
    "ile": dict(floors_typical="4–9", far=1.4, housing_share=0.45, job_m2=90),
    "biz": dict(floors_typical="3–9", far=1.15, housing_share=0.0, job_m2=90),
    "expo": dict(floors_typical="2–6 (залы)", far=0.9, housing_share=0.0, job_m2=120),
    "ircc": dict(floors_typical="4–12 (отели, казино, океанариум)", far=1.353, housing_share=0.0, job_m2=120),
    "theme": dict(floors_typical="1–3 (аттракционы)", far=0.25, housing_share=0.0, job_m2=120),
    "hotel": dict(floors_typical="2–6 (отели, санатории)", far=0.6, housing_share=0.0, job_m2=120),
    "mid": dict(floors_typical="3–6", far=0.36, housing_share=0.90, job_m2=50),
    "low": dict(floors_typical="2–4 (террасы, таунхаусы)", far=0.30, housing_share=0.92, job_m2=50),
    "med": dict(floors_typical="3–7", far=1.0, housing_share=0.0, job_m2=50),
    "log": dict(floors_typical="1–2 (склады)", far=0.45, housing_share=0.0, job_m2=100),
    "util": dict(floors_typical="1–2", far=0.1, housing_share=0.0, job_m2=100),
    "f1": dict(floors_typical="1–4 (трибуны, боксы)", far=0.06, housing_share=0.0, job_m2=120),
    "golf": dict(floors_typical="1–2 (клуб)", far=0.01, housing_share=0.0, job_m2=120),
    "park": dict(floors_typical="0–1 (павильоны)", far=0.005, housing_share=0.0, job_m2=120),
}

ZONES = [
    # id, use, name, design, density key, years, queue, why
    ("gc", "mixed_centre", "Green-Сити — главный центр", [[2300, 20950], [3950, 20950], [3950, 22400], [2300, 22400]], "gc", [2033, 2045], 2,
     "Плотный центр вокруг станции ЛРТ и Озёрного проспекта: туристический центр, торговля, офисы, жильё над первыми этажами; высотки — только у станции и по согласованию с аэродромом."),
    ("ircc", "business", "Курортно-развлекательный центр (IRCC) 100 га", [[3950, 20600], [5600, 20600], [5600, 21900], [3950, 21900]], "ircc", [2030, 2040], 2,
     "Генплан: 1 353,3 тыс. м² на 100 га, 2030–2040 (казино, океанариум, аквапарк, пристань); на мысу у Бульвара к озеру, ≥ 500 м от А-3."),
    ("expo", "business", "Выставочный и деловой квартал", [[1250, 22400], [3700, 22400], [3700, 23450], [1250, 23450]], "expo", [2036, 2044], 3,
     "Выставочные комплексы и туристический центр Iconic Building-2 у станции «Выставка», на въезде из Конаева; залы низкие, не закрывают вид на озеро."),
    ("heat", "utility", "Станция тепловых насосов", [[3700, 22250], [4150, 22250], [4150, 22700], [3700, 22700]], "util", [2032, 2034], 2,
     "Генплан: тепловые насосы 500 Гкал/ч на воде водохранилища; здание выше 485 м, водозабор — трубой через береговой парк."),
    ("sc_arnaut", "mixed_centre", "Центр Арнаутская", [[2150, 18450], [3350, 18450], [3350, 19450], [2150, 19450]], "sc", [2030, 2038], 1,
     "Районный центр у станции ЛРТ на существующей улице: школы, поликлиника, рынок, офисы."),
    ("med", "medical", "Больница района Green (по правилу)", [[3350, 19450], [3850, 19450], [3850, 19950], [3350, 19950]], "med", [2032, 2036], 2,
     "Больница и поликлиника района у центра Арнаутская и ЛРТ (нормы: 5 коек на 1000 жителей; участок по норме — уровень 1)."),
    ("sc_ile", "mixed_centre", "Центр Іле у вокзала", [[1250, 16750], [1950, 16750], [1950, 17700], [1250, 17700]], "ile", [2027, 2032], 1,
     "Пристанционная площадь, автобусы до ЛРТ, гостиницы и торговля."),
    ("park_c", "park", "Центральный парк Green", [[2250, 19950], [3150, 19950], [3150, 20950], [2250, 20950]], "park", [2032, 2036], 2,
     "Городской парк между Арнаутской и Green-Сити, на оси ЛРТ (норма: городской парк ≥ 15 га в 20 мин пешком)."),
    ("biz_rail", "business", "Деловой пояс вдоль Турксиба", [[1000, 15650], [1950, 15650], [1950, 22400], [1000, 22400]], "biz", [2029, 2044], 1,
     "Офисы, гостиницы, сервис и торговля между путями и жильём: работа у вокзала и шумовой экран для кварталов."),
    ("park_river", "waterfront", "Набережная и парк Каскелена", "river_bank", "park", [2028, 2036], 1,
     "Полоса 150 м вдоль западного берега Каскелена: пешеходная набережная, велодорожка, пляжи на реке."),
    ("res_s", "residential_mid", "Южный квартал", [[1800, 12900], [4300, 12900], [4300, 16650], [1800, 16650]], "mid", [2029, 2036], 1,
     "Среднеэтажное жильё у станций «Құйған», «Каскелен», «Южный»; первые дома — у ЛРТ первой очереди."),
    ("res_c", "residential_mid", "Центральные кварталы", [[1900, 16650], [4300, 16650], [4300, 20950], [1900, 20950]], "mid", [2031, 2042], 2,
     "Среднеэтажное жильё (3–6 эт., дворы и школьные участки внутри) по обе стороны Проспекта Green; к реке этажность снижается."),
    ("res_lake", "residential_low", "Малоэтажные дома у залива", [[3650, 19950], [5600, 19950], [5600, 20600], [3650, 20600]], "low", [2034, 2042], 3,
     "«Малоэтажные дома вдоль набережной» (Yestate): 2–4 этажа на краю береговой зоны, выше 485 м с отступом."),
    ("res_n", "residential_mid", "Северные кварталы", [[1950, 20950], [2300, 20950], [2300, 22400], [1950, 22400]], "mid", [2034, 2040], 3,
     "Жильё между деловым поясом и Green-Сити."),
    ("biz_a3w", "business", "Деловой пояс А-3 (запад)", [[-950, 15800], [250, 15800], [500, 22100], [-950, 22100]], "biz", [2034, 2046], 3,
     "Линейная застройка вдоль въездной магистрали (генплан, гл. 6): офисы, отели у трассы, сервис; между А-3 и коридорами ЛЭП 500 кВ."),
    ("terr", "residential_low", "Западные террасы", [[-3000, 17600], [-1250, 17600], [-1250, 21600], [-3000, 21600]], "low", [2037, 2050], 4,
     "«Террасное жильё с видом на озеро» (Yestate): склон 560–620 м, обращённый на северо-восток к Капчагаю; 2–4 этажа уступами, без высоток."),
    ("track", "sport", "Существующий автодром (OSM)", "track", "f1", [2025, 2025], 1,
     "Существующая трасса у Конаева (OSM: recreation/track, 75 га) остаётся."),
    # east
    ("theme", "business", "Тематический парк", [[9450, 15800], [10900, 15800], [10900, 17200], [9450, 17200]], "theme", [2037, 2042], 3,
     "«Казахстанский аналог Диснейленда» (источники) — большой и шумный, поэтому на востоке, у Восточной береговой, вне зоны подхода к ВПП."),
    ("f1", "sport", "Автодром Формулы-1", [[10000, 13600], [11900, 13600], [11900, 15250], [10000, 15250]], "f1", [2038, 2042], 3,
     "Трасса Ф-1 (источники без места): шумный объект — рядом с аэродромом, в 2+ км от жилья, у Жетыгенской дороги и ж/д."),
    ("resort_e", "business", "Отели и курорты Восточного берега", [[10900, 15800], [12700, 15800], [12700, 18700], [10900, 18700]], "hotel", [2036, 2044], 3,
     "Курорты, которые в двойнике стоят без дорог, собраны вдоль Восточной береговой; пляжи — в береговом парке перед ними."),
    ("res_e", "residential_low", "Малоэтажный Восточный берег", [[12700, 16900], [15000, 16900], [15000, 18800], [12700, 18800]], "low", [2040, 2050], 4,
     "Малоэтажное жильё у воды дальше 4,5 км от ВПП (шум); выше 485 м с отступом."),
    ("golf", "sport", "Гольф-клуб Восточный", [[15000, 16000], [17000, 16000], [17000, 18800], [15000, 18800]], "golf", [2040, 2045], 4,
     "Гольф-поля (источники без места) на плоском берегу у устья Сазталгара; клуб выше 485 м."),
    ("log", "logistics", "Логистический парк у Жетыгена", [[7600, 11800], [13000, 12400], [13000, 13400], [7600, 13400]], "log", [2038, 2046], 4,
     "Склады и сервис у ж/д Жетыген – Алтынколь рядом с ТЛЦ «Жетыген» (Growing); к северу от путей, на юго-востоке от жилья."),
    ("wwtp", "utility", "Очистные сооружения Green (по правилу)", [[14600, 11400], [15400, 11400], [15400, 12000], [14600, 12000]], "util", [2033, 2036], 2,
     "Генплан: по одним очистным на район, место по правилу — ниже по рельефу и далеко от жилья (санзона 400 м)."),
]

BACKGROUND = [  # (id, use, name, region box, density key, why)
    ("bg_core", "park", "Парки и зелёные полосы ядра", [-200, 12000, 9000, 24000], "park",
     "Остаток ядра между кварталами, реками и прудами: парки, бульвары, зелёные полосы вдоль путей и ЛЭП."),
    ("bg_west_park", "park", "Западный лесопарк и склоны", [-5600, 15000, 0, 30000], "park",
     "Полоса леса и степи за террасами и на крутых склонах (> 12 %): прогулки, велодорожки, зелёный пояс от песков."),
    ("bg_west", "reserve", "Западная степь — резерв после 2050", [-14000, 15000, -5600, 30000], "park",
     "Плато 600–700 м далеко от воды и ЛРТ: пастбища и степь остаются резервом города."),
    ("bg_east", "reserve", "Восточная степь и поля — резерв", [5000, 8000, 20000, 24000], "park",
     "Поля и степь востока в зоне 10 км аэродрома: резерв; дороги и сети — по мере надобности."),
]


# ----------------------------------------------------------------------------------------------------------------- build
def dehole(p):
    """Split a polygon with holes into hole-free parts (vertical cut through each hole)."""
    if p.geom_type == "MultiPolygon":
        return [q for g in p.geoms for q in dehole(g)]
    if p.geom_type != "Polygon" or p.is_empty:
        return []
    if not p.interiors:
        return [p]
    h = Polygon(p.interiors[0]); cx = h.representative_point().x
    x0, z0, x1, z1 = p.bounds
    out = []
    for b in (box(x0 - 1, z0 - 1, cx, z1 + 1), box(cx, z0 - 1, x1 + 1, z1 + 1)):
        q = p.intersection(b)
        for g in getattr(q, "geoms", [q]):
            if g.geom_type == "Polygon" and g.area > 1:
                out += dehole(g)
    return out


def ring(p):
    return [[int(round(x)), int(round(z))] for x, z in list(p.exterior.coords)[:-1]]


def dens(key, area_ha=None):
    d = dict(D[key])
    far, hs, jm2 = d["far"], d["housing_share"], d.pop("job_m2")
    d["residents_per_ha"] = round(far * hs * 10000 / M2_PER_RES, 1)
    d["jobs_per_ha"] = round(far * (1 - hs) * 10000 / jm2, 1)
    d["m2_per_job"] = jm2
    return d


def build_zones(g, V, AIR):
    G, FS, W = g["G"], g["FS"], g["W"]
    T = terrain.terrain()
    corr = unary_union([g["A3"].buffer(150), g["RAIL"].buffer(100)]).intersection(G)
    plc = g["PL"].buffer(40).intersection(G)
    taken = []
    zones = []

    def add(zid, use, name, geom, dkey, years, queue, why, extra=None, min_ha=3.0, tol=8, clip=None):
        prev = taken[-1] if taken else Polygon()
        geom = geom.intersection(G).difference(prev).buffer(0)
        parts = []
        for q in dehole(geom):
            if q.area < min_ha * 1e4:
                continue
            q = q.simplify(tol).buffer(0).difference(prev).intersection(G).buffer(0)
            if clip is not None:
                q = q.difference(clip).buffer(0)
            q = max(getattr(q, "geoms", [q]), key=lambda r: r.area) if not q.is_empty else q
            if q.is_empty or q.geom_type != "Polygon" or q.area < min_ha * 1e4:
                continue
            if use in BUILT and use != "utility" and q.buffer(-60).area < 0.3 * q.area:
                continue                       # strips narrower than ≈ 150 m between corridors: not a building plot, left to the green
            parts += dehole(q)
        parts.sort(key=lambda q: -q.area)
        for i, q in enumerate(parts):
            zz = dict(id=zid if len(parts) == 1 else f"{zid}_{i + 1}", use=use, name_ru=name, polygon=ring(q),
                      density=dens(dkey), years=years, queue=queue, why=why)
            if extra:
                zz.update(extra)
            zones.append((zz, Polygon(zz["polygon"]).buffer(0)))
        taken.append(unary_union([prev] + [z[1] for z in zones[-len(parts):]] if parts else [prev]))

    # fixed land first
    add("vil", "village_existing", "Существующая застройка (сёла, дачи, фермы)", V, "park", [2025, 2025], 0,
        "Существующие дома остаются (решение владельца 31.10); улицы сёл — уровень 1, новые оси их обходят.",
        {"density": {"floors_typical": "1–2 (существующие)", "far": None, "residents_per_ha": 0, "jobs_per_ha": 0,
                     "note": "существующие жители не входят в цель 2050 (CityStats считает только новое жильё)"}}, min_ha=0.0, tol=0)
    for z, p in zones:
        if z["use"] == "village_existing":
            c0 = p.representative_point()
            for nm in ("Арна", "Құйған", "Қонаев"):
                if g["sett"][nm].buffer(300).contains(c0):
                    z["name_ru"] = {"Арна": "Село Арна (существующее)", "Құйған": "Село Куйган (существующее)",
                                    "Қонаев": "Окраина Конаева (существующие дома)"}[nm]
    wz = unary_union([p for p in getattr(W, "geoms", [W]) if p.area > 10e4])
    add("water", "waterfront", "Вода: Капчагай, Каскелен, пруды", wz, "park", [2025, 2025], 0,
        "Акватория внутри границы района; только причалы и марина.", {"kind": "water", "density": {"residents_per_ha": 0, "jobs_per_ha": 0}})
    add("air", "reserve", "Аэродром Жетыген: режимная территория и зоны подхода", AIR, "park", [2025, 2025], 0,
        "Действующий военный аэродром (OSM, КТА по research) остаётся; ВПП + 500 м и полосы подхода 4 км от торцов — без застройки.",
        {"density": {"residents_per_ha": 0, "jobs_per_ha": 0}})
    add("corr", "utility", "Коридор А-3 и Турксиба", corr, "util", [2025, 2025], 0,
        "Полоса отвода трассы (±150 м) и железной дороги (±100 м): жильё не ближе 100 м к путям и 150 м к А-3.",
        {"density": {"residents_per_ha": 0, "jobs_per_ha": 0}}, clip=W.buffer(3))
    shore = unary_union([g["F"], FS]).difference(W)
    for zid, name, bx in (("wf_n", "Береговой парк: марина, пляжи и коса", [0, 23300, 9000, 30000]),
                          ("wf_c", "Береговой парк Green-Сити (набережная, пляжи)", [0, 18300, 9300, 23300]),
                          ("wf_e", "Береговой парк Восточного берега (пляжи)", [5000, 14000, 20000, 23000])):
        add(zid, "waterfront", name, shore.intersection(box(*bx)), "park", [2030, 2045], 2 if zid != "wf_e" else 3,
            "Земля ниже отметки 485 м (затопляется при проектном уровне) и отступ 45–50 м: только набережная, пляжи, парк и причалы, без капитальных зданий.")
    # built zones: never on the 485 setback, water, houses, airfield, corridors, power lines
    forbid = unary_union([FS, W, V, AIR, corr, plc])
    forbid2 = unary_union([FS, W.buffer(3), g["F"].buffer(3)])   # metre rounding of vertices must not push a built zone into water or below 485 m
    steep = slope_mask(G, T, 15.0)
    for zid, use, name, design, dkey, years, queue, why in ZONES:
        if design == "river_bank":
            riv = unary_union([p for p in getattr(W, "geoms", [W]) if p.intersects(box(3000, 13000, 5200, 20800))])
            geom = riv.buffer(150).difference(riv).intersection(box(2900, 13000, 4800, 19700))
            geom = geom.difference(unary_union([FS, V, AIR, corr]))
        elif design == "track":
            geom = g["TRACK"].difference(forbid)
        else:
            geom = Polygon(design).difference(forbid)
            if use in ("mixed_centre", "business", "medical"):
                geom = geom.difference(steep)
        add(zid, use, name, geom, dkey, years, queue, why, clip=forbid2 if use in BUILT else None)
    # background: everything left, by region
    for zid, use, name, bx, dkey, why in BACKGROUND:
        add(zid, use, name, box(*bx), dkey, [2030, 2050], 4 if use == "reserve" else 3, why,
            {"density": dens(dkey) if use != "reserve" else {"residents_per_ha": 0, "jobs_per_ha": 0}})
    # absorb leftovers (slivers from simplification and parts < 0.5 ha) into the neighbour with the longest shared edge
    U = unary_union([p for _, p in zones])
    rest = G.difference(U).buffer(0)
    pieces = [q for q in getattr(rest, "geoms", [rest]) if q.geom_type == "Polygon" and q.area > 1]
    for q in sorted(pieces, key=lambda r: -r.area):
        wet = q.intersects(W) or q.intersects(g["F"]) or q.intersects(V)
        cand = [(i, q.buffer(2).intersection(p).area, z["use"] in BUILT) for i, (z, p) in enumerate(zones)
                if z["use"] != "village_existing" and p.distance(q) < 1.5 and not (wet and z["use"] in BUILT)]
        cand.sort(key=lambda t: (t[2], -t[1]))
        for i, _, _ in cand:
            u = unary_union([zones[i][1], q]).buffer(0.01).buffer(-0.01)
            if u.geom_type == "Polygon" and not u.interiors:
                u = u.simplify(0.5)
                zones[i][0]["polygon"] = ring(u)
                zones[i] = (zones[i][0], Polygon(zones[i][0]["polygon"]).buffer(0))
                break
    return zones


def slope_mask(G, T, pct):
    x0, z0, x1, z1 = G.bounds
    xs = np.arange(x0, x1, 100) + 50; zs = np.arange(z0, z1, 100) + 50
    X, Z = np.meshgrid(xs, zs)
    S = T.slope(X, Z) * 100
    cells = [box(x - 50, z - 50, x + 50, z + 50) for x, z, s in zip(X.ravel(), Z.ravel(), S.ravel()) if s > pct]
    return unary_union(cells) if cells else Polygon()


def lrt_stations(line):
    L = LineString(line)
    want = [("st_kuygan", "Құйған", 3700, 13800), ("st_kaskelen", "Каскелен", 3690, 15000), ("st_south", "Южный", 3150, 16200),
            ("st_central", "Центральные кварталы", 2820, 17350), ("st_arnaut", "Арнаутская", 2790, 18680),
            ("st_park", "Центральный парк", 2760, 19900), ("st_zaliv", "Залив", 2850, 21000), ("st_gc", "Green-Сити", 3020, 21950),
            ("st_expo", "Выставка", 2860, 22950)]
    out = []
    for sid, nm, x, z in want:
        p = L.interpolate(L.project(Point(x, z)))
        out.append(dict(id=sid, name_ru=nm, x=int(round(p.x)), z=int(round(p.y)), chain_m=int(round(L.project(p)))))
    return out


def objects_table(g, zones_geo, centres):
    reg = json.load(open(REG, encoding="utf-8"))
    rows = {r["id"]: r for r in reg["rows"]}
    zc = {z["id"]: Polygon(z["polygon"]).representative_point() for z, _ in zones_geo}
    wg, wp = layers.load("derived/water_main")
    kap = [q for q, p in zip(wg, wp) if p.get("id") == "kapchagay"][0]
    marina_to = nearest_points(kap, Point(4600, 25000))[0]

    def pt(zid):
        p = zc.get(zid) or zc.get(zid + "_1")
        return [int(round(p.x)), int(round(p.y))]

    def acc(rid):
        return rows[rid]["accuracy"] if rid in rows else None

    def geomxy(rid):
        gm = rows[rid].get("geom")
        if not gm:
            return None
        from shapely.geometry import shape
        s = shape(gm)
        p = s if s.geom_type == "Point" else (s.representative_point() if s.geom_type.endswith("Polygon") else s.interpolate(0.5, normalized=True))
        return [int(round(p.x)), int(round(p.y))]

    O = []

    def row(rid, action, frm, to, yaw, why, **kw):
        r = rows.get(rid)
        O.append(dict(registry_id=rid, name_ru=r["name_ru"] if r else kw.pop("name_ru"), action=action, **{"from": frm}, to=to,
                      yaw=yaw, accuracy=acc(rid), why=why, **kw))

    row("marina_kapchagay", "move", [5177, 23845], [int(round(marina_to.x)), int(round(marina_to.y))], 30,
        "Точка двойника (модель) в 718 м от воды на земле 481 м: при нынешнем уровне 477–479 м там суша. Источник места не даёт (только «Капчагайское "
        "водохранилище»), поэтому по правилу: урез воды в тихой бухте между Конаевым и песчаной косой, у существующей дороги «На ASP Arena» и у "
        "северных пляжей; понтоны на плавучих причалах (уровень меняется на 8 м). Сдвиг 1,5 км. «модель qTwin»", height_m=None)
    row("resort_ircc", "by_rule", None, pt("ircc"), None,
        "Генплан: 100 га на побережье, 2030–2040; по правилу — мыс к востоку от Green-Сити, выше 485 м, ≥ 500 м от А-3. «модель qTwin»", height_m=45)
    row("casino_zone", "by_rule", None, [4300, 21250], None, "В составе курорта IRCC (генплан: казино — основа курорта). «модель qTwin»", height_m=45)
    row("oceanarium_aquapark", "by_rule", None, [4900, 21000], None, "В составе курорта IRCC у Бульвара к озеру. «модель qTwin»", height_m=30)
    row("green_tower_30", "by_rule", None, [5100, 21400], 225,
        "«Главный ориентир — 30-этажный комплекс у озера» (Yestate): на конце Бульвара к озеру, на мысу, ближайшей к воде точке застройки "
        "(выше 485 м). ≈ 105 м — нужно согласование с аэродромом. «модель qTwin»", height_m=105, approval="нужно согласование")
    row("iconic_building_2", "by_rule", None, [3250, 21850], 180,
        "Туристический центр у станции ЛРТ Green-Сити, в начале Бульвара к озеру: сюда приезжают туристы по ЛРТ и с А-3. Высота не опубликована; "
        "если ≥ 50 м — нужно согласование. «модель qTwin»", height_m=None, approval="если ≥ 50 м — нужно согласование")
    row("green_tourist_centre", "by_rule", None, [3600, 21500], None,
        "«Два участка и песчаная коса» (Vlast): участок 1 — Green-Сити с курортом на мысу, участок 2 — Восточный берег, коса — северные пляжи. "
        "Точка — Green-Сити. «модель qTwin»", height_m=None)
    row("green_terraces", "by_rule", None, pt("terr"), None,
        "Террасы с видом на озеро — склон к западу от А-3; малоэтажные дома вдоль набережной — зоны «у залива» и «Восточный берег». «модель qTwin»", height_m=15)
    row("f1_track", "by_rule", None, pt("f1"), None,
        "Шумный объект: на востоке у аэродрома, в 2+ км от жилья, у Жетыгенской дороги. «модель qTwin»", height_m=20)
    row("golf_diving", "by_rule", None, pt("golf"), None,
        "Гольф — на плоском восточном берегу у Сазталгара; дайвинг-клубы — у марины. «модель qTwin»", height_m=10)
    row("theme_parks", "by_rule", None, pt("theme"), None, "На востоке у Восточной береговой, вне зоны подхода к ВПП. «модель qTwin»", height_m=40)
    row("urban_beaches", "by_rule", None, [4300, 24600], None,
        "«В северной части — городские пляжи» (Yestate): береговой парк между Конаевым и косой; ещё пляжи вдоль всего берегового парка. «модель qTwin»", height_m=None)
    row("expo_complexes", "by_rule", None, pt("expo"), None, "Выставочный квартал у станции «Выставка» на въезде из Конаева. «модель qTwin»", height_m=25)
    row("sand_spit_leisure", "add", None, [5739, 26777], None,
        "Существующий центр отдыха на песчаной косе (Vlast) — точного места в источнике нет; по правилу на северной косе. В Overture на этой косе "
        "есть курорт «ASP Arena» (54 га) — вероятное совпадение, источником не подтверждено. «модель qTwin»", height_m=None)
    row("heat_pumps_green", "by_rule", None, pt("heat"), None, "Станция у берега рядом с главными потребителями (центр, курорт); водозабор трубой. «модель qTwin»", height_m=15)
    row("district_green", "keep", None, None, None, "Граница — city.json#districts/green (контур двойника 31 796 га; см. открытый вопрос о восточной части).")
    row("airfield_zhetygen", "keep", geomxy("airfield_zhetygen"), geomxy("airfield_zhetygen"), 14,
        "Действующий аэродром, ВПП 01/19 целиком внутри контура Green двойника (в реестре district_geom = Growing). Оставляем; вокруг — зона без застройки.")
    row("settlement_arna", "keep", geomxy("settlement_arna"), geomxy("settlement_arna"), None, "Существующее село остаётся; мост Арнаутской связывает его с центром.")
    row("settlement_kuygan", "keep", geomxy("settlement_kuygan"), geomxy("settlement_kuygan"), None,
        "Существующее село (в реестре district_geom = Growing, но контур OSM целиком в Green); у станции ЛРТ «Құйған».")
    row("settlement_konaev", "keep", geomxy("settlement_konaev"), geomxy("settlement_konaev"), None,
        "Соседний город вне Алатау; 125 га его контура OSM заходят в контур Green — там существующие дома, зона «существующая застройка».")
    row("station_ile", "keep", geomxy("station_ile"), geomxy("station_ile"), None, "Существующая станция; центр Іле у вокзала.")
    row("interchange_a3_km61_0", "keep", geomxy("interchange_a3_km61_0"), geomxy("interchange_a3_km61_0"), None, "Существующая развязка; к ней Арнаутская.")
    row("road_a3", "keep", None, None, None, "Существующая А-3 через Green (ось a3).")
    row("rail_turksib", "keep", None, None, None, "Существующий Турксиб; коридор ±100 м без жилья.")
    row("rail_zhetygen_altynkol", "keep", None, None, None, "Существующая ветка вдоль юго-востока; логистика к северу от путей.")
    row("rail_second_tracks", "by_rule", None, None, None, "В полосе существующих путей (коридор ±100 м).")
    row("hv_lines_500", "keep", None, None, None, "Существующие ВЛ 500 кВ: коридор ±40 м без застройки, дороги пересекают поперёк.")
    row("hv_lines_220", "keep", None, None, None, "Существующие ВЛ: коридор без застройки.")
    tl = geomxy("tlc_zhetygen")
    row("tlc_zhetygen", "keep", None, tl, None,
        "Объект Growing-восток (реестр: перенос на контур OSM «ТЛЦ Логистика»). 23 из 32 га этого контура лежат в контуре Green двойника: "
        "ставит картограф Growing-восток, Green примыкает логистическим парком.", outside_note="Growing-E")
    row("settlement_zhetygen", "keep", None, geomxy("settlement_zhetygen"), None,
        "Жетыген (Growing): край его контура OSM касается границы Green; Green не трогает, связь — Жетыгенская дорога.", outside_note="Growing-E")
    row("tlc_industrial_zone", "by_rule", None, None, None,
        "Промзона при ТЛЦ «Жетыген» — объект Growing-восток; с северной стороны путей к ней примыкает логистический парк Green.", outside_note="Growing-E")
    for rid, why in (("fok_zarechny", "ФОК Заречный"), ("knauf", "KNAUF"), ("ps_zarechnoe", "ПС «Заречное»"),
                     ("settlement_zarechnoe", "Заречное"), ("interchange_a3_km55_9", "развязка А-3 км 55,9")):
        xy = geomxy(rid)
        row(rid, rows[rid]["action"]["do"], xy, xy, None,
            f"{why}: в реестре district_geom = Green, но по контуру city.json точка в Growing ({Point(xy).distance(g['G']) / 1000:.1f} км от границы Green). "
            "Строка для сверки; ставит картограф Growing.", outside_note="Growing")
    return O


def phases():
    return [
        dict(queue=1, years=[2027, 2032], what_ru="Ворота и юг: реконструкция Арнаутской с мостом на Арну, Привокзальная и Южная, Проспект Green и ЛРТ от "
             "Құйғана до Арнаутской; затем центр Іле, деловой пояс у путей, Южный квартал, центр Арнаутская, набережная Каскелена.",
             zones=["sc_ile", "biz_rail", "res_s", "sc_arnaut", "park_river"], axes=["arnaut", "privokzal", "yuzh", "prosp_green", "lrt_south"]),
        dict(queue=2, years=[2030, 2045], what_ru="Центр у воды: развязка «Green-Север» и Озёрный проспект, затем курорт IRCC 2030–2040 (генплан), ЛРТ до Green-Сити "
             "и Конаева, Бульвар к озеру, Green-Сити, центральные кварталы, больница, парк, береговой парк с марином и пляжами.",
             zones=["ircc", "gc", "res_c", "med", "park_c", "heat", "wf_c", "wf_n", "wwtp"], axes=["ozerny", "lrt_north", "blv_lake", "prom_c", "heat_st"]),
        dict(queue=3, years=[2034, 2046], what_ru="Восток и запад: мост на Восточный берег, Восточная береговая и Жетыгенская, потом отели, тематический парк, "
             "Ф-1; деловой пояс А-3 и Арнаутская-Запад; выставочный квартал и малоэтажка у залива.",
             zones=["resort_e", "theme", "f1", "biz_a3w", "expo", "res_lake", "res_n", "wf_e"], axes=["east_link", "bereg_e", "east_n", "arnaut_w", "dubler_a3w", "prom_e"]),
        dict(queue=4, years=[2036, 2050], what_ru="Достройка: Северная и Террасная улицы, затем Западные террасы; улица логистики, затем логистический парк; "
             "малоэтажный Восточный берег и гольф.",
             zones=["terr", "log", "res_e", "golf"], axes=["ozerny_w", "terr", "log_st", "track_st"]),
    ]


def build():
    g = ground()
    G = g["G"]
    V = villages(g)
    a, b = runway_axis(g["RWY"])
    AIR = unary_union([g["MIL"], g["RWY"].buffer(500), funnel(b, a), funnel(a, b)]).intersection(G)
    zones_geo = build_zones(g, V, AIR)
    lrt_line = AXES[1][3] + AXES[2][3][1:]
    st = lrt_stations(lrt_line)
    c = g["c"]
    spec = {
        "district": "green", "version": 0, "boundary": "city.json#districts/green",
        "about": "Схема района Green, уровень 0 (w39, 31.10.2026). Координаты — Unity X (восток) / Z (север), метры. Всё, что не из источника, — «модель qTwin». "
                 "Зоны построены tools/map/scheme/green_scheme.py из эскизных контуров с обрезкой по отметке 485 м + 45–50 м, воде, существующим домам, аэродрому и коридорам. "
                 + ATTR,
        "targets": {
            "population_2050": 320000, "jobs_2050": 304901, "homes_2050": None,
            "source": {
                "population_2050": "CityStats.DistrictTarget2050k[3] = 320 (тыс.) — UnityProject/Assets/Scripts/DigitalTwin/CityStats.cs:13; то же в генплане (≈ 320 тыс., ГП727)",
                "jobs_2050": "правило оркестратора 31.10: собственные рабочие места двойника в 2050 внутри контура Green — buildings.csv, базовый сценарий (год ≤ 2050), "
                             "формулы CityStats (нежилая площадь / 90 бизнес, 50 соцобъекты, 100 промышленность, 120 отдых): 220 367 + 13 410 + 4 901 + 66 223 = 304 901, "
                             "без масштабирования. Для сравнения: генплан — ≈ 173,5 тыс. (norms.json quarters.genplan_jobs_2050)",
                "homes_2050": "не задано: двойник считает жителей как жильё / 30 м², квартиры не считает",
            },
        },
        "centres": CENTRES,
        "axes": [dict(id=i, **{"class": cl}, name_ru=n, line=ln, status=s, years=y, why=w, **ex) for i, cl, n, ln, s, y, w, ex in AXES],
        "zones": [z for z, _ in zones_geo],
        "lrt": {"line": lrt_line, "stations": st,
                "why": "Ствол ЛРТ (генплан: 3 линии, остановки через 0,8–1,5 км) входит из Growing в стыке J046 и уходит на Конаев в стыке J052. Внутри Green "
                       "трасса перенесена с берега Каскелена на ось жилого пояса, через центры Арнаутская и Green-Сити; 9 станций через 0,97–1,37 км, каждая "
                       "в 200–300 м от перекрёстка. Названия станций — «модель qTwin». Конец черновика в зоне затопления у Конаева убран."},
        "objects": objects_table(g, zones_geo, CENTRES),
        "phases": phases(),
        "joints": [
            {"joint_id": "J046", "axis": "lrt_south"}, {"joint_id": "J047", "axis": "existing:rail_turksib"},
            {"joint_id": "J048", "axis": "existing:rail_turksib"}, {"joint_id": "J049", "axis": "existing:rail_turksib"},
            {"joint_id": "J050", "axis": "existing:rail_turksib"}, {"joint_id": "J051", "axis": "a3"},
            {"joint_id": "J052", "axis": "lrt_north"}, {"joint_id": "J053", "axis": "existing:rail_turksib"},
            {"joint_id": "J054", "axis": "existing:rail_zhetygen_altynkol"}, {"joint_id": "J055", "axis": "existing:rail_zhetygen_altynkol"},
            {"joint_id": "J056", "axis": "existing:rail_zhetygen"}, {"joint_id": "J057", "axis": "existing:rail_zhetygen"},
            {"joint_id": "J058", "axis": "a3"}, {"joint_id": "J059", "axis": "a3"},
            {"joint_id": "J060", "axis": "se_main"}, {"joint_id": "J061", "axis": "se_main"},
        ],
        "checks": {},
    }
    return spec, g, V


# ----------------------------------------------------------------------------------------------------------------- checks
def run_checks(spec, g=None, V=None):
    g = g or ground()
    G, F, W = g["G"], g["F"], g["W"]
    T = terrain.terrain()
    c = g["c"]
    ZG = [(z, Polygon(z["polygon"]).buffer(0)) for z in spec["zones"]]
    houses = list(g["HOUSES"]) + list(g["TWIN_EX"])
    H = np.array([h for h in houses if h.intersects(G)], dtype=object)
    tree = shapely.STRtree(H)
    ch = {}
    # 1. land: zones vs 485, water, houses
    rows = []
    built_in_485 = 0.0; built_in_water = 0.0; hits = 0
    for z, p in ZG:
        a485 = p.intersection(F).area / 1e4
        aw = p.intersection(W).area / 1e4
        idx = tree.query(p, predicate="intersects")
        nh = int(sum(1 for i in idx if H[i].intersection(p).area > 1.0))
        if z["use"] in BUILT:
            built_in_485 += a485; built_in_water += aw
        if z["use"] != "village_existing":
            hits += nh
        if z["use"] in BUILT and (a485 > 0.01 or aw > 0.01) or (z["use"] != "village_existing" and nh):
            rows.append({"zone": z["id"], "in_485_ha": round(a485, 2), "in_water_ha": round(aw, 2), "houses_hit": nh})
    min_set = min([p.distance(F) for z, p in ZG if z["use"] in BUILT] or [0])
    ch["land_zones"] = {"built_zones_in_485_ha": round(built_in_485, 2), "built_zones_in_water_ha": round(built_in_water, 2),
                        "houses_hit_outside_village_zones": hits, "min_distance_built_zone_to_485_line_m": round(min_set, 1),
                        "houses_total_in_green": int(len(H)), "problems": rows,
                        "pass": built_in_485 < 0.01 and built_in_water < 0.01 and hits == 0,
                        "note": "485 м — проектная отметка (НПУ) Капчагая, слой derived/kapchagay_levels (реальные 485 м = 483 м рельефа двойника); "
                                "дома — Overture (OSM) + existing_osm двойника. Зоны waterfront/park/reserve в полосе 485 м разрешены (набережная, пляжи, причалы)."}
    # coverage / overlaps
    U = unary_union([p for _, p in ZG])
    over = 0.0
    tz = shapely.STRtree([p for _, p in ZG])
    for i, (_, p) in enumerate(ZG):
        for j in tz.query(p, predicate="intersects"):
            if j > i:
                over += p.intersection(ZG[j][1]).area
    ch["coverage"] = {"district_ha": round(G.area / 1e4, 1), "zones_ha": round(sum(p.area for _, p in ZG) / 1e4, 1),
                      "uncovered_ha": round(G.difference(U).area / 1e4, 2), "outside_district_ha": round(U.difference(G).area / 1e4, 2),
                      "overlaps_ha": round(over / 1e4, 2), "pass": G.difference(U).area < 5e4 and over < 5e4,
                      "note": "допуск 5 га на округление контуров до метра и упрощение 6 м"}
    # 2. axes: new axes vs 485, water, houses
    arows = []
    for a in spec["axes"]:
        L = LineString(a["line"])
        Li = L.intersection(G)
        l485 = Li.intersection(F).length; lw = Li.intersection(W).length
        idx = tree.query(L.buffer(12), predicate="intersects")
        nh = len(idx)
        arows.append({"axis": a["id"], "status": a["status"], "len_km": round(L.length / 1000, 2), "in_485_m": round(l485), "on_water_m": round(lw),
                      "houses_within_12m": nh})
    hasbr = {a["id"] for a in spec["axes"] if a.get("bridges")}
    ped = {a["id"] for a in spec["axes"] if a["class"] == "pedestrian"}
    newbad = [r for r in arows if r["status"] == "new" and (r["houses_within_12m"] or (
        ((r["in_485_m"] > 0 and r["axis"] not in ped) or r["on_water_m"] > 0) and r["axis"] not in hasbr))]
    ch["land_axes"] = {"axes": arows, "new_axes_problems": newbad,
                       "bridges_declared": [dict(r, bridges=[b for a in spec["axes"] if a["id"] == r["axis"] for b in a["bridges"]]) for r in arows if r["axis"] in hasbr],
                       "pass": not newbad,
                       "note": "дом в 12 м от оси новой оси = задет (существующие дороги keep_existing не считаются). Новая ось над водой или ниже 485 м допустима только "
                               "мостом (ключ bridges у оси): правило 4 — дорога в пойме только мостом или дамбой выше паводка + 0,5 м. Набережные (pedestrian) ниже 485 м разрешены "
                               "заданием (парк и набережная могут быть там), но не по воде."}
    # 3. joints
    J = {j["id"]: j for j in c["joints"]["items"] if "green" in j["between"]}
    axd = {a["id"]: LineString(a["line"]) for a in spec["axes"]}
    rl, rlp = layers.load("rail")
    RAILS = unary_union(list(rl))
    jr = []
    for jj in spec["joints"]:
        j = J[jj["joint_id"]]; P = Point(j["x"], j["z"])
        d = axd[jj["axis"]].distance(P) if jj["axis"] in axd else RAILS.distance(P)
        jr.append({"joint": jj["joint_id"], "kind": j["kind"], "axis": jj["axis"], "dist_m": round(d, 1)})
    missing = sorted(set(J) - {x["joint_id"] for x in spec["joints"]})
    ch["joints"] = {"joints_of_green": len(J), "met": sum(1 for r in jr if r["dist_m"] <= 25), "missing": missing, "rows": jr,
                    "pass": not missing and all(r["dist_m"] <= 25 for r in jr),
                    "note": "ж/д стыки встречает существующая ж/д (OSM), не новая ось"}
    # 4. registry
    reg = json.load(open(REG, encoding="utf-8"))
    from shapely.geometry import shape
    mine = set()
    for r in reg["rows"]:
        if r.get("district") == "Green" or r.get("district_inferred") == "Green" or (r.get("district_geom") or "").startswith("Green"):
            mine.add(r["id"])
        elif r.get("geom"):
            try:
                if shape(r["geom"]).intersects(G):
                    mine.add(r["id"])
            except Exception:
                pass
    have = {o["registry_id"] for o in spec["objects"]}
    ch["registry"] = {"registry_rows_for_green": len(mine), "rows_in_objects": len(mine & have), "missing": sorted(mine - have),
                      "extra": sorted(have - mine), "pass": not (mine - have),
                      "rule": "строка реестра в Green: district / district_inferred / district_geom = Green или геометрия пересекает контур Green"}
    # 4b. access: every built zone reaches a scheme street or an existing road within 200 m (the twin has 1 908 resort houses > 200 m from a road)
    rg, rp = layers.load("roads")
    near = shapely.intersects(G.buffer(1000), rg)
    ROADS = unary_union([LineString(a["line"]) for a in spec["axes"] if a["class"] not in ("lrt_corridor", "pedestrian")] +
                        [g_ for g_, p_, k in zip(rg, rp, near) if k and p_.get("class") not in ("path", "footway", "track", "cycleway", "steps")])
    far = []
    for z, p in ZG:
        if z["use"] in BUILT and not z["id"].startswith("corr"):
            d = p.distance(ROADS)
            if d > 200:
                far.append({"zone": z["id"], "dist_m": round(d)})
    ch["access"] = {"built_zones": sum(1 for z, _ in ZG if z["use"] in BUILT and not z["id"].startswith("corr")), "farther_than_200m": far,
                    "pass": not far,
                    "note": "дороги = оси схемы (кроме ЛРТ и набережных) + существующие дороги OSM (без троп и полевых дорог); внутренние улицы зон — уровень 1. "
                            "Курорты Восточного берега, которые в двойнике стоят без дорог, получают Восточную береговую и набережную."}
    # 5. shares and capacity
    area = {}
    res = jobs = 0.0
    for z, p in ZG:
        a = p.area / 1e4
        area[z["use"]] = area.get(z["use"], 0) + a
        d = z.get("density") or {}
        res += a * (d.get("residents_per_ha") or 0); jobs += a * (d.get("jobs_per_ha") or 0)
    tot = sum(area.values())
    t = spec["targets"]
    ch["shares"] = {u: {"ha": round(v, 1), "pct": round(100 * v / tot, 1)} for u, v in sorted(area.items(), key=lambda kv: -kv[1])}
    ch["capacity"] = {"residents": int(round(res, -2)), "jobs": int(round(jobs, -2)),
                      "residents_vs_target_pct": round(100 * (res / t["population_2050"] - 1), 1),
                      "jobs_vs_target_pct": round(100 * (jobs / t["jobs_2050"] - 1), 1),
                      "pass": abs(res / t["population_2050"] - 1) <= 0.10 and abs(jobs / t["jobs_2050"] - 1) <= 0.10,
                      "method": "жители = площадь зоны × FAR × доля жилья / 30 м²; места = площадь × FAR × (1 − доля жилья) / м² на место (CityStats); "
                                "существующие жители сёл не входят (как в CityStats)"}
    # 6. slope and heights
    def slope_stats(geom, step=25.0):
        if geom.geom_type in ("Point",):
            return {"slope_pct": round(float(T.slope(geom.x, geom.y)) * 100, 2), "h_m": round(float(T.height(geom.x, geom.y)), 1)}
        if geom.geom_type == "LineString":
            s, x, z, h = T.profile(list(geom.coords), step)
            sl = T.slope(x, z) * 100
            grade = np.abs(np.diff(h)) / step * 100
            return {"slope_mean_pct": round(float(sl.mean()), 2), "slope_max_pct": round(float(sl.max()), 2),
                    "grade_p95_pct": round(float(np.percentile(grade, 95)), 2), "h_min_m": round(float(h.min()), 1), "h_max_m": round(float(h.max()), 1)}
        x0, z0, x1, z1 = geom.bounds
        X, Z = np.meshgrid(np.arange(x0, x1, step), np.arange(z0, z1, step))
        m = shapely.contains_xy(geom, X, Z)
        sl = T.slope(X[m], Z[m]) * 100
        return {"slope_mean_pct": round(float(sl.mean()), 2), "slope_p95_pct": round(float(np.percentile(sl, 95)), 2)}
    main = [c_ for c_ in spec["centres"] if c_["kind"] == "main"][0]
    gcz = [p for z, p in ZG if z["id"] in ("gc", "gc_1")]
    ch["slope"] = {"main_centre_point": slope_stats(Point(main["x"], main["z"])),
                   "main_centre_zone": slope_stats(gcz[0]) if gcz else None,
                   "axes": {a["id"]: slope_stats(LineString(a["line"])) for a in spec["axes"] if a["class"] in ("expressway", "arterial", "lrt_corridor", "boulevard", "district")},
                   "lrt_max_grade_rule_pct": 6.0, "source": "tools/map/geo/terrain.py (рельеф двойника, 50 м)"}
    ch["slope"]["axes_grade_p95_over_8pct"] = {k: v["grade_p95_pct"] for k, v in ch["slope"]["axes"].items() if v["grade_p95_pct"] > 8}
    ch["slope"]["note"] = ("Главный центр стоит на ровной площадке (уклон ≈ 2 %, по зоне p95 ≈ 6 %); ЛРТ не круче 5 % (p95) — правило 6 % выполнено. "
                           "Западные улицы (Террасная, Северная, Арнаутская-Запад, Дублёр А-3) пересекают овраги склона глубиной до 40 м: продольный уклон "
                           "p95 8–13 % по рельефу 50 м; на уровне 1 трассу ведут по горизонталям, через овраги — мосты или насыпи.")
    af = [a for a in c["height_limits"]["airfields"] if a["id"] == "zhetygen_mil"][0]
    K = Point(af["x"], af["z"])
    tall = []
    for o in spec["objects"]:
        h = o.get("height_m")
        if o.get("to") and (h is None or h >= 50) and o["action"] in ("by_rule", "add", "move"):
            d = Point(o["to"]).distance(K) / 1000
            tall.append({"object": o["registry_id"], "height_m": h, "km_from_KTA_zhetygen": round(d, 1),
                         "flag": "нужно согласование" if (h or 0) >= 50 else ("если ≥ 50 м — нужно согласование" if h is None else "ниже 50 м")})
    for z, p in ZG:
        if z["use"] == "mixed_centre" and "30" in str(z["density"].get("floors_typical", "")) or z["id"] in ("gc",):
            q = p.representative_point()
            tall.append({"zone": z["id"], "height_m": "≥ 50 (доминанты до 30 эт.)", "km_from_KTA_zhetygen": round(q.distance(K) / 1000, 1),
                         "flag": "нужно согласование"})
    inside10 = [z["id"] for z, p in ZG if z["use"] in BUILT and p.distance(K) < 10000]
    ch["heights"] = {"airfield": af["name"], "kta": [af["x"], af["z"]], "rule": c["height_limits"]["norm"],
                     "tall_items": tall, "built_zones_within_10km_all_need_approval": inside10,
                     "policy": "в Green жильё 2–9 этажей (< 30 м); выше 50 м — только доминанта у озера, Iconic Building-2 (если ≥ 50 м) и высотки у станции "
                               "Green-Сити; у всех — «нужно согласование». Весь район в 30 км от КТА, большая часть застройки — в 10 км (согласование всех объектов)."}
    ch["summary"] = {k: v.get("pass") for k, v in ch.items() if isinstance(v, dict) and "pass" in v}
    return ch


def open_questions():
    return [
        {"q": "Восточную часть Green за Каскеленом (≈ 9 060 га с военным аэродромом) оставляем в Green, как в контуре двойника? По geojson генплана и "
              "по источникам («восточная граница — по озеру и реке Каскелен») она в Growing, а Green вместо неё получает ≈ 8 900 га к юго-западу. Да / нет",
         "answer": "да / нет"},
        {"q": "Рабочие места Green к 2050: держим 305 тыс. двойника (так в схеме) или снижаем до 173,5 тыс. по генплану (меньше делового пояса вдоль А-3 и путей)? Двойник / генплан",
         "answer": "двойник / генплан"},
    ]


# ----------------------------------------------------------------------------------------------------------------- main
def dump(spec):
    s = json.dumps(spec, ensure_ascii=False, indent=1)
    # keep coordinate lists on one line: hand-editable and small
    import re
    s = re.sub(r"\[\s+(-?\d+(?:\.\d+)?),\s+(-?\d+(?:\.\d+)?)\s+\]", r"[\1, \2]", s)
    s = re.sub(r"\[\s+((?:\[-?\d+, -?\d+\],?\s*)+)\]", lambda m: "[" + re.sub(r"\s+", " ", m.group(1)).strip() + "]", s)
    tmp = SPEC + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(s + "\n")
    os.replace(tmp, SPEC)


def main():
    draw_only = "--draw" in sys.argv
    if draw_only:
        spec = json.load(open(SPEC, encoding="utf-8")); g = None
    else:
        spec, g, V = build()
    spec["checks"] = run_checks(spec, g)
    spec["checks"]["open_questions"] = open_questions()
    dump(spec)
    print(json.dumps(spec["checks"]["summary"], ensure_ascii=False))
    print("capacity", spec["checks"]["capacity"])
    print("shares", {k: v["pct"] for k, v in spec["checks"]["shares"].items()})
    if "--nodraw" not in sys.argv:
        draw(spec, os.path.join(OUTDIR, "scheme.png"))



# ----------------------------------------------------------------------------------------------------------------- picture
USE_STYLE = {  # use: (fill, label)
    "mixed_centre": ("#d62728", "центр (смешанная застройка)"),
    "business": ("#f08030", "деловая, курорт, отели, развлечения"),
    "residential_mid": ("#f5b82e", "жильё 3–6 этажей"),
    "residential_low": ("#f9dc84", "жильё 2–4 этажа, террасы"),
    "medical": ("#e377c2", "больница"),
    "logistics": ("#a495c8", "логистика"),
    "utility": ("#bdbdbd", "инженерные объекты, коридоры дорог и ж/д"),
    "sport": ("#6cc04a", "спорт: Ф-1, гольф, автодром"),
    "park": ("#b4dc98", "парки, лесопарк, зелёные полосы"),
    "waterfront": ("#86d3c9", "береговой парк ниже 485 м: набережная, пляжи, причалы"),
    "reserve": ("#efeadc", "резерв: степь и поля; аэродром"),
    "village_existing": ("#b98b62", "существующие сёла и дома"),
}
AX_STYLE = {  # class: (colour, width px, label)
    "expressway": ("#6d1a1a", 9, "скоростная дорога А-3"),
    "arterial": ("#c0392b", 5.5, "магистральная улица"),
    "district": ("#e67e22", 3.5, "улица районного значения"),
    "boulevard": ("#1e7b4a", 5, "пешеходный бульвар"),
    "pedestrian": ("#0b6e63", 3.5, "набережная (пешеходы, велосипед)"),
}
LABXY = {"wf_c": (5800, 23250), "f1": (10950, 14950), "bg_west": (-9500, 21000), "wf_e": (12500, 19700), "air": (7100, 13900), "bg_east": (15000, 13700),
         "biz_rail": (1450, 20350), "res_c": (3700, 18300), "res_s": (3200, 14500), "biz_a3w": (-350, 17200), "terr": (-2150, 20600),
         "expo": (2000, 22700), "ircc": (4750, 20690), "res_e": (14050, 17750), "park_c": (2350, 20450), "med": (3900, 19700), "res_lake": (4700, 20250),
         "bg_west_park": (-4000, 23000), "track": (-2900, 24400)}
QCOL = {0: "#bdbdbd", 1: "#1b9e77", 2: "#d95f02", 3: "#7570b3", 4: "#e7298a"}


def draw(spec, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection, PolyCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Circle, FancyArrowPatch, Patch
    import matplotlib.patheffects as pe

    c = json.load(open(CITY, encoding="utf-8"))
    G = Polygon(c["districts"]["green"]["polygon"])
    X0, Z0, X1, Z1 = -13300, 8300, 19400, 28900
    W_PX, SIDE = 3650, 850                     # map + sidebar (object list, queues, signs)
    mpp = (X1 - X0) / W_PX
    H_PX = (Z1 - Z0) / mpp
    fr = W_PX / (W_PX + SIDE)
    fig = plt.figure(figsize=((W_PX + SIDE) / 100, H_PX / 100), dpi=100)
    ax = fig.add_axes([0, 0, fr, 1])
    sb = fig.add_axes([fr, 0, 1 - fr, 1])
    sb.set_xlim(0, 1); sb.set_ylim(0, 1); sb.axis("off")
    sb.add_patch(plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor="#999999", linewidth=1.5))
    ax.set_xlim(X0, X1); ax.set_ylim(Z0, Z1); ax.set_aspect("equal"); ax.axis("off")
    fig.patch.set_facecolor("#f6f4ee")
    halo = [pe.withStroke(linewidth=3.5, foreground="white")]
    halo2 = [pe.withStroke(linewidth=5, foreground="white")]

    def polys(geoms):
        out = []
        for g in geoms:
            for q in getattr(g, "geoms", [g]):
                if q.geom_type == "Polygon" and not q.is_empty:
                    out.append(np.asarray(q.exterior.coords))
        return out

    def lines(geoms):
        out = []
        for g in geoms:
            for q in getattr(g, "geoms", [g]):
                if q.geom_type in ("LineString", "LinearRing") and len(q.coords) > 1:
                    out.append(np.asarray(q.coords))
                elif q.geom_type == "Polygon":
                    out.append(np.asarray(q.exterior.coords))
        return out

    # terrain shading
    T = terrain.terrain()
    xs = np.arange(X0, X1, 100.0); zs = np.arange(Z0, Z1, 100.0)
    XX, ZZ = np.meshgrid(xs, zs)
    Hh = T.height(XX, ZZ)
    gz, gx = np.gradient(Hh, 100.0)
    shade = np.clip(0.5 + (-gx * 0.6 + gz * 0.8) * 4, 0, 1)
    ax.imshow(shade, origin="lower", extent=(X0, X1, Z0, Z1), cmap="Greys_r", vmin=-0.3, vmax=1.3, alpha=0.35, zorder=0, interpolation="bilinear")
    cs = ax.contour(XX, ZZ, Hh, levels=list(range(500, 760, 20)), colors="#9a8a70", linewidths=0.5, alpha=0.45, zorder=0.5)
    ax.clabel(cs, fontsize=9, fmt="%d м", inline=True)
    # water of the region
    wg, wp = layers.load("water")
    clip = box(X0, Z0, X1, Z1)
    sel = shapely.intersects(clip, wg)
    ax.add_collection(PolyCollection(polys([g for g, s_ in zip(wg, sel) if s_ and g.geom_type.endswith("Polygon")]),
                                     facecolor="#9ccbeb", edgecolor="#6aa9d6", linewidths=0.5, zorder=1))
    ax.add_collection(LineCollection(lines([g for g, s_ in zip(wg, sel) if s_ and g.geom_type.endswith("LineString")]),
                                     colors="#6aa9d6", linewidths=1.0, zorder=1))
    # zones
    for z in spec["zones"]:
        if z.get("kind") == "water":
            continue
        col = USE_STYLE[z["use"]][0]
        P = np.asarray(z["polygon"])
        hatch = None
        if z["id"].startswith("air"):
            hatch = "xx"
        ax.add_collection(PolyCollection([P], facecolor=col, edgecolor="white", linewidths=0.8, alpha=0.88, zorder=2,
                                         hatch=hatch))
    # outside the district: dim
    outside = clip.difference(G)
    ax.add_collection(PolyCollection(polys([outside]), facecolor="#ffffff", edgecolor="none", alpha=0.55, zorder=2.5))
    # 485 line and the working level
    kg, kp = layers.load("derived/kapchagay_levels")
    lv = {int(p["real_m"]): g for g, p in zip(kg, kp)}
    rings485 = []
    for q in getattr(lv[485], "geoms", [lv[485]]):
        if q.area > 20e4:
            rings485.append(LineString(q.exterior.coords))
            rings485 += [LineString(r.coords) for r in q.interiors if Polygon(r).area > 20e4]
    l485 = unary_union(rings485).simplify(25).intersection(G.buffer(300))
    ax.add_collection(LineCollection(lines([l485]), colors="#08306b", linewidths=1.7, linestyles=(0, (6, 3)), alpha=0.85, zorder=6))
    # existing network (muted)
    rg, rp = layers.load("roads")
    sel = np.flatnonzero(shapely.intersects(clip, rg))
    main = [rg[i] for i in sel if rp[i].get("class") in ("motorway", "trunk", "primary", "secondary", "tertiary")]
    minor = [rg[i] for i in sel if rp[i].get("class") in ("residential", "unclassified", "living_street")]
    ax.add_collection(LineCollection(lines(minor), colors="#8c8c8c", linewidths=0.5, alpha=0.6, zorder=3))
    ax.add_collection(LineCollection(lines(main), colors="#6b6b6b", linewidths=1.6, alpha=0.8, zorder=3.1))
    rl, _ = layers.load("rail")
    rsel = shapely.intersects(clip, rl)
    ax.add_collection(LineCollection(lines(rl[rsel]), colors="#2b2b2b", linewidths=3.0, zorder=7))
    ax.add_collection(LineCollection(lines(rl[rsel]), colors="#ffffff", linewidths=1.4, linestyles=(0, (6, 6)), zorder=7.1))
    ig, ip = layers.load("infrastructure")
    pl = [g for g, p in zip(ig, ip) if p.get("class") == "power_line" and g.intersects(clip)]
    ax.add_collection(LineCollection(lines(pl), colors="#7d3c98", linewidths=1.3, linestyles=(0, (10, 3, 2, 3)), alpha=0.85, zorder=4))
    rw = [g for g, p in zip(ig, ip) if p.get("class") == "runway" and g.geom_type.endswith("Polygon") and g.intersects(clip)]
    ax.add_collection(PolyCollection(polys(rw), facecolor="#333333", edgecolor="#000000", zorder=7))
    # district boundary
    ax.add_collection(LineCollection(lines([G.exterior]), colors="#1d6b3a", linewidths=4.5, zorder=8))
    # airfield KTA and 10 km circle
    af = [a for a in c["height_limits"]["airfields"] if a["id"] == "zhetygen_mil"][0]
    ax.add_patch(Circle((af["x"], af["z"]), 10000, fill=False, edgecolor="#555555", linewidth=1.6, linestyle=(0, (8, 6)), zorder=8.5))
    ax.plot([af["x"]], [af["z"]], marker="P", markersize=16, color="#222222", markeredgecolor="white", zorder=20)
    ax.text(af["x"] + 250, af["z"] - 150, "Аэродром Жетыген (военный, ВПП 2,5 км)\nКТА: 10 км — согласование всех объектов,\n30 км (весь район) — всё ≥ 50 м",
            fontsize=12.5, va="top", zorder=21, path_effects=halo2, color="#222222")
    ang = math.radians(208)
    ax.text(af["x"] + 10000 * math.cos(ang), af["z"] + 10000 * math.sin(ang), "10 км от КТА", fontsize=12, color="#555555",
            rotation=-62, ha="center", va="center", zorder=9, path_effects=halo)
    # axes
    for a in spec["axes"]:
        if a["class"] == "lrt_corridor":
            continue
        col, w, _ = AX_STYLE[a["class"]]
        L = np.asarray(a["line"])
        ls = "-" if a["status"] != "keep_existing" else "-"
        ax.plot(L[:, 0], L[:, 1], color="white", linewidth=w + 3, solid_capstyle="round", zorder=9, alpha=0.9)
        ax.plot(L[:, 0], L[:, 1], color=col, linewidth=w, solid_capstyle="round", linestyle=ls, zorder=9.5 if a["class"] != "expressway" else 9.6)
        if a["status"] in ("keep_existing", "keep_twin"):
            ax.plot(L[:, 0], L[:, 1], color="white", linewidth=max(1.0, w * 0.28), linestyle=(0, (2, 3)), zorder=9.7)
        for n in a.get("nodes", []):
            ax.plot(*n["at"], marker="o", markersize=17, markerfacecolor="white", markeredgecolor=col, markeredgewidth=3.5, zorder=12)
        for b in a.get("bridges", []):
            ax.plot(*b["at"], marker="s", markersize=10, color="#111111", zorder=12)
    # LRT
    L = np.asarray(spec["lrt"]["line"])
    ax.plot(L[:, 0], L[:, 1], color="white", linewidth=9, zorder=13)
    ax.plot(L[:, 0], L[:, 1], color="#c2185b", linewidth=5.5, zorder=13.5)
    for st in spec["lrt"]["stations"]:
        ax.plot(st["x"], st["z"], marker="o", markersize=13, markerfacecolor="white", markeredgecolor="#c2185b", markeredgewidth=3, zorder=14)
        if any(ce["name_ru"].startswith(st["name_ru"]) and math.hypot(ce["x"] - st["x"], ce["z"] - st["z"]) < 600 for ce in spec["centres"]):
            continue
        right = st["name_ru"] in ("Выставка", "Центральные кварталы")
        ax.text(st["x"] + (170 if right else -170), st["z"], st["name_ru"], fontsize=12, color="#8e0f45", ha="left" if right else "right",
                va="center", zorder=14, path_effects=halo)
    # centres
    for ce in spec["centres"]:
        mk, ms = {"main": ("*", 46), "sub": ("o", 26), "local": ("o", 16)}[ce["kind"]]
        ax.plot(ce["x"], ce["z"], marker=mk, markersize=ms, markerfacecolor="#ffd400" if ce["kind"] == "main" else "#ffffff",
                markeredgecolor="#7a0000", markeredgewidth=3, zorder=16)
        fs = {"main": 24, "sub": 17, "local": 14}[ce["kind"]]
        dx = {"c_green_city": (-260, 330), "c_arnaut": (260, 260), "c_ile": (-200, -330), "c_ircc": (220, 330), "c_marina": (220, 160),
              "c_west": (-250, 230), "c_east": (0, -380), "c_kuygan": (260, -200)}.get(ce["id"], (200, 200))
        ha = "right" if dx[0] < 0 else ("center" if dx[0] == 0 else "left")
        ax.text(ce["x"] + dx[0], ce["z"] + dx[1], ce["name_ru"], fontsize=fs, fontweight="bold", color="#5c0000", ha=ha, va="center",
                zorder=17, path_effects=halo2)
    # zone labels (main zones, with queue)
    lab = {"ircc": "Курорт IRCC, 100 га", "expo": "Выставки", "terr": "жильё террасами", "res_c": "Центральные\nкварталы",
           "res_s": "Южный\nквартал", "biz_rail": "Деловой\nпояс", "biz_a3w": "Деловой пояс А-3", "theme": "Тематический\nпарк",
           "f1": "Автодром Ф-1", "resort_e": "Отели и курорты\nВосточного берега", "res_e": "Малоэтажный\nВосточный берег",
           "golf": "Гольф", "log": "Логистический парк", "wf_c": "Береговой парк: набережная и пляжи", "wf_e": "Береговой парк Восточного берега",
           "bg_west": "Западная степь — резерв после 2050", "bg_west_park": "Западный лесопарк", "air": "Аэродром",
           "bg_east": "Восточная степь — резерв", "park_c": "Центр.\nпарк", "med": "Больница", "wwtp": "Очистные", "res_lake": "Малоэтажка у залива",
           "sc_ile": "", "gc": "", "sc_arnaut": "", "park_river": "", "heat": "", "track": "Автодром\n(сущ.)"}
    seen = set()
    for z in spec["zones"]:
        base = z["id"].rsplit("_", 1)[0] if z["id"][-1].isdigit() and "_" in z["id"] else z["id"]
        if base in seen or base not in lab or not lab[base]:
            continue
        seen.add(base)
        p = Polygon(z["polygon"])
        q = Point(*LABXY[base]) if base in LABXY else p.representative_point()
        if base not in LABXY and any(math.hypot(o["to"][0] - q.x, o["to"][1] - q.y) < 300 for o in spec["objects"] if o.get("to")):
            q = Point(q.x, q.y - 420)
        qtxt = f"  [{z['queue']}]" if z["queue"] else ""
        big = base in ("bg_west", "bg_west_park", "bg_east", "wf_c", "wf_e")
        ax.text(q.x, q.y, lab[base] + (qtxt if z["use"] in BUILT else ""), fontsize=17 if big else 13.5, ha="center", va="center",
                color="#333333", style="italic" if big else "normal", zorder=15, path_effects=halo)
    ax.text(3400, 21300, "", zorder=15)
    # joints
    J = {j["id"]: j for j in c["joints"]["items"]}
    for jj in spec["joints"]:
        j = J[jj["joint_id"]]
        if j["kind"] == "rail" and jj["joint_id"] not in ("J047", "J053", "J054", "J055"):
            continue
        ax.plot(j["x"], j["z"], marker="D", markersize=13, markerfacecolor="#ffeb3b", markeredgecolor="#333333", markeredgewidth=1.8, zorder=18)
        ax.text(j["x"] + 120, j["z"] - 120, jj["joint_id"], fontsize=11, ha="left", va="top", zorder=18, path_effects=halo)
    # objects: numbered markers, arrows for moves
    objs = [o for o in spec["objects"] if o.get("to")]
    num = {}
    for i, o in enumerate(objs, 1):
        num[o["registry_id"]] = i
        x, z = o["to"]
        if not (X0 < x < X1 and Z0 < z < Z1):
            continue
        out = bool(o.get("outside_note"))
        if o["action"] == "move" and o.get("from"):
            fx, fz = o["from"]
            ax.plot(fx, fz, marker="o", markersize=16, markerfacecolor="white", markeredgecolor="#333333", markeredgewidth=2, linestyle="none", zorder=19)
            ax.add_patch(FancyArrowPatch((fx, fz), (x, z), arrowstyle="-|>", mutation_scale=30, linewidth=3, color="#111111",
                                         connectionstyle="arc3,rad=0.15", zorder=19.5, shrinkA=10, shrinkB=14))
            ax.text(fx + 160, fz - 60, "было (модель двойника)", fontsize=11, zorder=19, path_effects=halo, va="top")
        ax.plot(x, z, marker="o", markersize=22, markerfacecolor="#555555" if out else "#111111", markeredgecolor="white", markeredgewidth=2, zorder=20)
        ax.text(x, z, str(i), fontsize=11.5, color="white", ha="center", va="center", fontweight="bold", zorder=21)
    # title
    t = spec["targets"]; ch = spec.get("checks", {})
    cap = ch.get("capacity", {})
    ax.text(X0 + 300, Z1 - 250, "Green — курортный район у Капчагая · схема уровня 0", fontsize=34, fontweight="bold", va="top", zorder=30,
            path_effects=halo2)
    ax.text(X0 + 300, Z1 - 900, "Вся застройка выше отметки 485 м (проектный уровень водохранилища) с отступом 50 м; ниже — береговой парк, пляжи и марина.\n"
            f"Цель 2050: {t['population_2050'] / 1000:.0f} тыс. жителей, {t['jobs_2050'] / 1000:.0f} тыс. рабочих мест · ёмкость схемы: "
            f"{cap.get('residents', 0) / 1000:.0f} тыс. и {cap.get('jobs', 0) / 1000:.0f} тыс.",
            fontsize=17, va="top", zorder=30, path_effects=halo2)
    # legend of zones (SW corner of the map, outside the district)
    lx0, lz0 = X0 + 150, Z0 + 150
    hz = [Patch(facecolor=v[0], edgecolor="#777777", label=v[1]) for k, v in USE_STYLE.items()]
    hz.append(Line2D([], [], color="#08306b", lw=2.5, ls=(0, (6, 3)), label="отметка 485 м: ниже — только парк, пляжи, причалы"))
    leg1 = ax.legend(handles=hz, loc="lower left", bbox_to_anchor=((lx0 + 100 - X0) / (X1 - X0), (lz0 + 100 - Z0) / (Z1 - Z0)),
                     fontsize=13.5, frameon=True, facecolor="white", edgecolor="#999999", framealpha=0.95, fancybox=False,
                     borderpad=0.9, title="Зоны", title_fontsize=17, handlelength=2.2)
    leg1.set_zorder(41)
    leg1._legend_box.align = "left"
    # sidebar: registry objects, queues, signs
    sb.text(0.04, 0.988, "Объекты реестра (номер на карте)", fontsize=15.5, fontweight="bold", va="top")
    rows_ = []
    for o in objs:
        i = num[o["registry_id"]]
        tag = {"move": "перенос", "keep": "есть", "by_rule": "по правилу", "add": "добавить", "remove": "убрать"}[o["action"]]
        nm = o["name_ru"].split("(")[0].strip()
        if len(nm) > 40:
            nm = nm[:39] + "…"
        rows_.append(f"{i:>2}  {nm} — {tag}" + (" (в Growing)" if o.get("outside_note") else ""))
    sb.text(0.04, 0.962, "\n".join(rows_), fontsize=12.2, va="top", family="DejaVu Sans", linespacing=1.25)
    # queue inset
    iy0, ih = 0.415, 0.215
    ia = fig.add_axes([fr + 0.004, iy0, 1 - fr - 0.008, ih])
    ia.set_facecolor("#fbfbfb")
    for z in spec["zones"]:
        if z["use"] in BUILT and z["queue"]:
            ia.add_collection(PolyCollection([np.asarray(z["polygon"])], facecolor=QCOL[z["queue"]], edgecolor="none"))
    ia.add_collection(LineCollection(lines([G.exterior]), colors="#1d6b3a", linewidths=1.2))
    for a in spec["axes"]:
        if a["class"] in ("lrt_corridor",):
            continue
        Q = max([p["queue"] for p in spec["phases"] if a["id"] in p["axes"]] or [0])
        LL = np.asarray(a["line"])
        ia.plot(LL[:, 0], LL[:, 1], color=QCOL[Q] if Q else "#888888", linewidth=1.8)
    ia.set_xlim(-6500, 19000); ia.set_ylim(10200, 25300); ia.set_aspect("equal", adjustable="datalim"); ia.set_xticks([]); ia.set_yticks([])
    for s_ in ia.spines.values():
        s_.set_edgecolor("#999999")
    ia.legend(handles=[Patch(facecolor=QCOL[q], label=f"{q}: {p['years'][0]}–{p['years'][1]}") for q, p in zip((1, 2, 3, 4), spec["phases"])],
              loc="lower right", fontsize=11, framealpha=0.9)
    sb.text(0.04, iy0 + ih + 0.008, "Очереди: цвет зоны = очередь, улица того же цвета строится раньше", fontsize=12.5, fontweight="bold", va="bottom")
    qshort = {1: "Арнаутская с мостом, Привокзальная, Проспект Green и ЛРТ\n     → Іле, деловой пояс, Южный квартал, Арнаутская",
              2: "развязка «Green-Север», Озёрный, ЛРТ на Конаев\n     → курорт IRCC, Green-Сити, больница, набережная",
              3: "мост на восток, Восточная береговая, Жетыгенская\n     → отели, Ф-1, тематический парк; деловой пояс А-3",
              4: "Северная, Террасная, улица логистики\n     → террасы, логистика, гольф, Восточный берег"}
    sb.text(0.04, iy0 - 0.008, "\n".join(f"[{p['queue']}] {p['years'][0]}–{p['years'][1]}: {qshort[p['queue']]}" for p in spec["phases"]),
            fontsize=11.3, va="top", linespacing=1.25)
    ex_road = (Line2D([], [], color="#c0392b", lw=5), Line2D([], [], color="white", lw=1.5, ls=(0, (2, 3))))
    la = [Line2D([], [], color=v[0], lw=v[1] * 0.9, label=v[2]) for k, v in AX_STYLE.items()]
    la += [ex_road,
           Line2D([], [], color="#c2185b", lw=5, marker="o", mfc="white", mec="#c2185b", ms=11, label="ЛРТ и станции"),
           Line2D([], [], ls="", marker="o", mfc="white", mec="#c0392b", mew=3, ms=14, label="развязка А-3"),
           Line2D([], [], ls="", marker="s", color="#111111", ms=9, label="мост"),
           Line2D([], [], color="#2b2b2b", lw=3, label="ж/д (существующая)"),
           Line2D([], [], color="#7d3c98", lw=1.5, ls=(0, (10, 3, 2, 3)), label="ЛЭП (существующие)"),
           Line2D([], [], color="#6b6b6b", lw=1.6, label="дороги сегодня (OSM)"),
           Line2D([], [], color="#1d6b3a", lw=4, label="граница района Green"),
           Line2D([], [], ls="", marker="*", mfc="#ffd400", mec="#7a0000", ms=24, label="главный центр"),
           Line2D([], [], ls="", marker="o", mfc="white", mec="#7a0000", mew=3, ms=16, label="центр района / местный центр"),
           Line2D([], [], ls="", marker="D", mfc="#ffeb3b", mec="#333333", ms=11, label="стык с соседом (city.json)"),
           Line2D([], [], ls="", marker="o", mfc="#111111", mec="white", ms=16, label="объект реестра (номер в списке)"),
           Line2D([], [], color="#111111", lw=3, marker=">", label="перенос объекта: было → стало")]
    labels = [h.get_label() if h is not ex_road else "белый пунктир по оси: существующая дорога" for h in la]
    leg2 = sb.legend(handles=la, labels=labels, loc="lower left", bbox_to_anchor=(0.02, 0.005), fontsize=12.5, frameon=False,
                     title="Оси и знаки", title_fontsize=15.5, handlelength=2.6)
    leg2._legend_box.align = "left"
    # scale bar, north arrow, attribution
    sx, sz = 11500, Z0 + 500
    ax.plot([sx, sx + 5000], [sz, sz], color="black", linewidth=10, solid_capstyle="butt", zorder=45)
    ax.plot([sx, sx + 2500], [sz, sz], color="white", linewidth=5, solid_capstyle="butt", zorder=46)
    ax.text(sx + 2500, sz + 250, "5 км", fontsize=17, ha="center", va="bottom", zorder=46, path_effects=halo2)
    ax.annotate("С", xy=(X1 - 700, Z1 - 1900 + 1500), xytext=(X1 - 700, Z1 - 1900), ha="center", va="center", fontsize=26, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", lw=4, color="k"), zorder=46)
    ax.text(X1 - 150, Z0 + 120, f"{ATTR} · рельеф двойника (GLO-30) · Unity X/Z, м · {mpp:.1f} м/пикс. · модель qTwin, кроме объектов с источником · "
            "tools/map/scheme/green_scheme.py", fontsize=11, ha="right", va="bottom", zorder=46, path_effects=halo)
    tmp = path + ".tmp.png"
    fig.savefig(tmp, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    os.replace(tmp, path)
    print(f"[draw] {path}: {W_PX + SIDE} × {H_PX:.0f} px, {os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
