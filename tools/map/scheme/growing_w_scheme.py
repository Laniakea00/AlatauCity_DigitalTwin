"""Growing-West level-0 scheme: build the spec (tools/map/spec/growing_w.json) from growing_w_design.py, run the checks,
draw the scheme picture.

    python3 -I tools/map/scheme/growing_w_scheme.py build   # design → spec + checks
    python3 -I tools/map/scheme/growing_w_scheme.py check   # checks of the spec as it stands (hand edits included)
    python3 -I tools/map/scheme/growing_w_scheme.py draw    # scheme.png
    python3 -I tools/map/scheme/growing_w_scheme.py all
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "geo"))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, shape  # noqa: E402

import growing_w_design as D  # noqa: E402
import layers  # noqa: E402
import terrain  # noqa: E402

OUT_DIR = os.environ.get("GW_OUT", "/mnt/project-files/alatau_stage7/level0/schemes/growing_w")
M2_PER_RES, PERS_PER_HOME, HOUSING_SHARE = 30.0, 3.0, 0.85
AIRPORT_JOBS = 15000          # model qTwin: ≈ 1 000 jobs per 1 mln passengers × 15 mln (genplan № 727 capacity)
HALF_W = {"expressway": 40, "trunk": 30, "arterial": 20, "district": 15, "boulevard": 15, "pedestrian": 8, "lrt_corridor": 10}

USE_RU = {"mixed_centre": "центр (смешанная)", "business": "деловая", "residential_high": "жильё 9–12 эт.", "residential_mid": "жильё 5–8 эт.",
          "residential_low": "жильё 2–3 эт.", "village_existing": "существующие посёлки и дачи", "campus": "кампус", "medical": "медицина",
          "industry": "промышленность", "logistics": "логистика", "utility": "инженерия, ЛЭП, лётное поле", "park": "парки и лесопарк",
          "waterfront": "река и набережная", "sport": "спорт", "reserve": "резерв"}


def rnd(coords):
    return [[int(round(x)), int(round(z))] for x, z in coords]


def capacity(use, area_ha, dens):
    far = dens.get("far", 0.0)
    if use in ("residential_high", "residential_mid", "residential_low"):
        res = area_ha * 1e4 * far * HOUSING_SHARE / M2_PER_RES
    elif use == "mixed_centre":
        res = area_ha * 1e4 * far * 0.45 / M2_PER_RES
    else:
        res = 0.0
    jobs = area_ha * dens.get("jobs_per_ha", 0)
    return res, jobs


# ------------------------------------------------------------------ build
def build_spec():
    c, W, E, reg, zones, H = D.build()
    split = c["growing_split"]["line"]
    # coverage simplify keeps neighbours glued
    geoms = [z[2] for z in zones]
    parts = []
    for z in zones:
        for k, p in enumerate([p for p in getattr(z[2], "geoms", [z[2]]) if p.area > 2e3]):
            parts.append((z, k, len(getattr(z[2], "geoms", [z[2]])), p))
    # merge crumbs (< 5 ha) of non-fixed zones into the neighbour with the longest shared edge
    fixed = ("village_existing", "waterfront")
    changed = True
    while changed:
        changed = False
        for i, (z, k, n, p) in enumerate(parts):
            if p.area >= 5e4 or z[1] in fixed or z[0] in ("air_airside", "air_terminal", "campus_voc"):
                continue
            best, bl = None, 0.0
            for j, (z2, k2, n2, p2) in enumerate(parts):
                if j == i or z2[1] in fixed:
                    continue
                if not p.buffer(1).intersects(p2):
                    continue
                l = p.boundary.intersection(p2.buffer(1)).length
                if l > bl:
                    best, bl = j, l
            if best is not None:
                z2, k2, n2, p2 = parts[best]
                m = shapely.union_all([p2, p]).buffer(0.01).buffer(-0.01)
                if m.geom_type == "Polygon":
                    parts[best] = (z2, k2, n2, m)
                    parts.pop(i)
                    changed = True
                    break
    # renumber parts per zone
    cnt = {}
    for z, k, n, p in parts:
        cnt[z[0]] = cnt.get(z[0], 0) + 1
    seen = {}
    parts2 = []
    for z, k, n, p in parts:
        seen[z[0]] = seen.get(z[0], 0) + 1
        parts2.append((z, seen[z[0]] - 1, cnt[z[0]], p))
    parts = parts2
    simp = shapely.coverage_simplify(np.array([p for _, _, _, p in parts], dtype=object), 12)
    out_z = []
    air_area = sum(p.area for (z, _, _, p) in parts if z[0] in ("air_airside", "air_terminal")) / 1e4
    for (z, k, n, p), s in zip(parts, simp):
        zid = z[0] if n == 1 else f"{z[0]}_{k + 1}"
        dens = dict(z[3])
        if z[0] in ("air_airside", "air_terminal"):
            dens["jobs_per_ha"] = round(AIRPORT_JOBS / air_area, 1)
        s = shapely.make_valid(s)
        if s.geom_type != "Polygon":
            s = max([q for q in getattr(s, "geoms", [s]) if q.geom_type == "Polygon"], key=lambda q: q.area)
        poly = rnd(s.exterior.coords)
        row = {"id": zid, "use": z[1], "name_ru": z[5], "polygon": poly, "density": dens, "years": z[4], "why": z[6]}
        holes = [rnd(r.coords) for r in s.interiors if Polygon(r).area > 2e3]
        if holes:
            row["holes"] = holes
        out_z.append(row)
    axes = [{"id": "a3", "class": "expressway", "name_ru": "Трасса А-3 Алматы – Қонаев (граница с Growing-восток)", "line": rnd(split),
             "status": "keep_existing", "years": [2025, 2025],
             "why": "существующая скоростная дорога; по ней проходит граница половин Growing, общая с w41; развязки км 44,0 и км 55,9 (реестр) остаются, узлы только в разных уровнях"}]
    axes += [dict(a) for a in D.AXES]
    p0, p1 = D.rwy_ends()
    objects = objects_rows(reg, W, p0, p1)
    spec = {
        "district": "growing_w",
        "version": 0,
        "boundary": "city.json#districts/growing_w",
        "targets": {
            "population_2050": 232100,
            "jobs_2050": 133782,
            "homes_2050": None,
            "source": ("население: цель кода двойника для всего Growing 650 тыс. (CityStats.DistrictTarget2050k) × доля Growing-запад в жителях двойника 2050 "
                       "(buildings.csv district=Growing, жители = жилая GFA / 30 м², базовый сценарий, год ≤ 2050, точка здания в полигоне половины): "
                       "261 221 / (261 221 + 470 307) = 35,71 % → 650 000 × 0,3571 = 232 100 (w41: 417 900). Рабочие места: собственные рабочие места двойника 2050 "
                       "внутри полигона (формулы CityStats: деловые 90, социальные 50, промышленность и энергетика 100, досуг 120 м² на место) = 133 782 из 401 245 по Growing (33,3 %), "
                       "без масштабирования — правило оркестратора для всех районов. В 2026 году в половине W жителей двойника 0 (140 существующих домов не считаются), "
                       "поэтому доли взяты по 2050. Число квартир в коде двойника не задано (homes_2050 = null); оценка схемы — в checks."),
        },
        "centres": D.CENTRES,
        "axes": axes,
        "zones": out_z,
        "lrt": {"line": D.LRT["line"], "stations": D.LRT["stations"], "why": D.LRT["why"]},
        "objects": objects,
        "phases": expand_phases(phases(), [z["id"] for z in out_z]),
        "joints": joints_map(c),
        "checks": {},
        "open_questions": [],
    }
    return spec


def objects_rows(reg, W, p0, p1):
    R = {r["id"]: r for r in reg["rows"]}
    rows = []

    def acc(i):
        return R[i]["accuracy"]

    def pt(i):
        g = shape(R[i]["geom"]) if R[i].get("geom") else None
        if g is None:
            return None
        q = g if g.geom_type == "Point" else g.representative_point()
        return [round(q.x, 1), round(q.y, 1)]
    C = D.RWY["centre"]
    rows.append({"registry_id": "airport_alatau", "name_ru": "Международный аэропорт «Алатау» (ВПП 4 000 м, 095°/275°)", "action": "move",
                 "from": pt("airport_alatau"), "to": [C[0], C[1]], "yaw": D.RWY["bearing"], "accuracy": acc("airport_alatau"), "chip": D.MODEL,
                 "from_twin": [-5900, 8300], "years": [2041, 2045],
                 "why": ("точка реестра по правилу (−16488, 561) лежит в Golden по контурам двойника; в двойнике аэропорт стоит на уступе (−5900, 8300, уклон 5–6 %). "
                         "Ставим на ровное плато хвоста Growing-запад у западной границы города (640 м, уклон вдоль ВПП 0,5 %): ВПП 4 000 × 45 м по аналогу ICAO Annex 14 "
                         "(код 4E), курс 095°/275° — по восточным ветрам Илийской и вдоль хвоста; к югу и западу от пары ВЛ 500 кВ из ПС «Алма», без их переноса; "
                         "заходы с запада над пустой степью, с востока над промзоной и сухим портом, не над жильём. 15 млн пасс./год по генплану № 727 (вариант 40 млн из новостей 03.2025 потребовал бы вторую ВПП, а она в хвост района не помещается). "
                         "Расстояния из новостей (29 км до Алматы, 25 км до Конаева) по прямой дают точку (−9000, 5750) у озёр Жаманкум — сам источник называет озёра помехой; "
                         "мы на 6–7 км юго-западнее, в 1,6 км от ближайшего озера.")})
    rows.append({"registry_id": "airport_rail_station", "name_ru": "Ж/д вокзал «Алатау» у терминала, аэроэкспресс", "action": "move",
                 "from": pt("airport_rail_station"), "to": [-15300, 2800], "yaw": 95, "accuracy": acc("airport_rail_station"), "chip": D.MODEL,
                 "line": D.RAIL_SPUR, "years": [2039, 2041],
                 "why": "у терминала, в одном узле с конечной ЛРТ; ветка 10,6 км от обходной ж/д внутри Growing-запад (развилка у ПС «Алма»), подъём на плато ≈ 1 %; поезда на Алматы-2 по обходу через Жанаарну, на Конаев через Жетыген"})
    rows.append({"registry_id": "rail_sorting_station", "name_ru": "Сортировочная станция", "action": "by_rule", "from": None, "to": [-3300, 120], "yaw": 90,
                 "accuracy": acc("rail_sorting_station"), "chip": D.MODEL, "years": [2040, 2045],
                 "why": "«между аэропортом и Конаевым» (генплан): на обходной ж/д между развилкой аэропортовой ветки и Жанаарной, парк ≈ 4 × 0,3 км вдоль пути, вне жилья ≥ 150 м"})
    rows.append({"registry_id": "dry_port", "name_ru": "Сухой порт (контейнерный терминал, таможня)", "action": "by_rule", "from": None, "to": [-2000, 900], "yaw": 0,
                 "accuracy": acc("dry_port"), "chip": D.MODEL, "years": [2028, 2035],
                 "why": "«Growing у ж/д» (генплан № 727): у обходной ж/д, сортировочной станции и развязки А-3 у Жанаарны"})
    rows.append({"registry_id": "rhenus_hub", "name_ru": "Транспортно-индустриальный хаб Rhenus Logistics", "action": "by_rule", "from": None, "to": [-7250, 450], "yaw": 0,
                 "accuracy": acc("rhenus_hub"), "chip": D.MODEL, "years": [2030, 2034],
                 "why": "источник даёт только район; ставим у развилки обходной ж/д и аэропортовой ветки (ж/д + авиа + А-3)"})
    rows.append({"registry_id": "vocational_institute", "name_ru": "Профтехинститут (10–15 тыс. учащихся)", "action": "by_rule", "from": None, "to": [-2350, 3350], "yaw": 0,
                 "accuracy": acc("vocational_institute"), "chip": D.MODEL, "years": [2036, 2042],
                 "why": "генплан: в Growing; ставим у центра и станции ЛРТ, профиль — авиация и логистика рядом с аэропортом и сухим портом"})
    for i, nm, why in (
            ("growing_polycentres", "Жилые кварталы Growing с полицентрами (половина W)", "вдоль Каскелена: центр «Каскелен», левобережный и северный центры; зоны res_* и ctr_main"),
            ("growing_industry_types", "Предприятия генплана в Growing (половина W)", "промзоны плато и юга (ind_plateau, ind_south) к западу и юго-западу от жилья; без классов I–II (режим СЭЗ)"),
            ("district_growing", "Район Growing (половина W)", "граница — контур двойника, разрезанный по А-3 (city.json growing_split)")):
        rows.append({"registry_id": i, "name_ru": nm, "action": "by_rule" if i != "district_growing" else "keep", "from": None, "to": None, "yaw": 0,
                     "accuracy": acc(i), "chip": D.MODEL if i != "district_growing" else None, "why": why})
    for i, nm, act, to, why in (
            ("road_a3", "А-3 / KAZ08 «Алматы – Қонаев»", "keep", None, "существующая; граница половин Growing, общая с w41 (ось a3)"),
            ("rail_bypass_zhetygen_kazybek", "Обходная ж/д Жетыген – Казыбек би", "keep", None, "существующая (12.2025); 7,2 км в Growing-запад, стыки J031 и J063; на ней развилка аэропортовой ветки"),
            ("ps_alma_500", "ПС 500/220/10 кВ «Алма» (KEGOC)", "add", pt("ps_alma_500"), "существующая, контур OSM; в двойнике её нет — добавляем на место"),
            ("ps_220_golden_osm", "ПС 220 кВ (OSM, без имени)", "add", pt("ps_220_golden_osm"), "существующая, контур OSM"),
            ("hv_lines_500", "ВЛ 500 кВ (KEGOC)", "keep", None, "существующие; аэропорт поставлен так, чтобы их не переносить; дороги пересекают коридор поперёк"),
            ("hv_lines_220", "ВЛ 220 кВ", "keep", None, "существующие; охранные коридоры — зона util_power"),
            ("ses_osm_pv", "Поле СЭС (OSM; в двойнике «СЭС Каскелен»)", "keep", pt("ses_osm_pv"), "существующее поле 108 га; магистраль и ЛРТ обходят его с севера"),
            ("interchange_a3_km44_0", "Развязка А-3, км 44,0", "add", pt("interchange_a3_km44_0"), "существующая (OSM); вход аэропортовой магистрали"),
            ("interchange_a3_km55_9", "Развязка А-3, км 55,9", "add", pt("interchange_a3_km55_9"), "существующая (OSM); вход дороги плато с севера")):
        rows.append({"registry_id": i, "name_ru": nm, "action": act, "from": to if act == "keep" else None, "to": to, "yaw": 0, "accuracy": acc(i), "chip": None, "why": why})
    return rows


def phases():
    return [
        {"queue": 1, "years": [2027, 2030], "what_ru": "Южная промышленная улица и сухой порт у обходной ж/д; первый участок аэропортовой магистрали от развязки км 44 до центра; парк на Каскелене",
         "zones": ["log_dryport", "log_rhenus", "river_kaskelen"], "axes": ["art_south", "airport_trunk"]},
        {"queue": 2, "years": [2030, 2036], "what_ru": "Центр «Каскелен» и кварталы у ЛРТ правого берега; улица Енбек – Каскелен; ветка ЛРТ от А-3 до центра (2036)",
         "zones": ["ctr_main", "res_centre_e", "campus_voc", "biz_a3"], "axes": ["art_k46", "blv_centre", "lrt_airport"]},
        {"queue": 3, "years": [2034, 2042], "what_ru": "Левый берег и кварталы вдоль набережной; связь Южная – Аэропортовая; южная промзона и первая очередь промзоны плато",
         "zones": ["res_westbank", "res_north", "ind_south", "ind_plateau", "park_escarpment"], "axes": ["art_link", "dst_westbank", "dst_north", "blv_kaskelen"]},
        {"queue": 4, "years": [2039, 2045], "what_ru": "Аэропорт: магистраль на плато, ж/д ветка и вокзал «Алатау», ЛРТ до терминала, ВПП, терминал и грузовой терминал; сортировочная станция",
         "zones": ["air_airside", "air_terminal", "log_cargo", "air_reserve"], "axes": ["airport_trunk", "lrt_airport"]},
        {"queue": 5, "years": [2045, 2050], "what_ru": "Малоэтажные кварталы у дачных массивов, дорога плато на развязку км 55,9, вторая очередь промзоны плато",
         "zones": ["res_low_north", "ind_plateau"], "axes": ["art_plateau"]},
    ]


def expand_phases(ph, ids):
    for q in ph:
        q["zones"] = [i for zid in q["zones"] for i in ids if i == zid or i.startswith(zid + "_")]
    return ph


def joints_map(c):
    out = []
    for j in c["joints"]["items"]:
        if "growing_w" not in j["between"]:
            continue
        jid = j["id"]
        if j["kind"] == "rail":
            ax = "rail:rail_bypass_zhetygen_kazybek"
        elif j["kind"] == "lrt":
            ax = "lrt_airport"
        elif jid in ("J076", "J077", "J078", "J139", "J140", "J141"):
            ax = "art_south"
        elif jid == "J072":
            ax = "art_k46"
        elif jid in ("J064", "J065", "J066", "J067", "J127"):
            ax = "art_plateau"
        elif jid in ("J032", "J033", "J034"):
            ax = "a3_ramps_s"
        else:
            ax = "a3"
        out.append({"joint_id": jid, "axis": ax})
    return out


# ------------------------------------------------------------------ checks
def zone_poly(z):
    g = shapely.make_valid(Polygon(z["polygon"], z.get("holes", [])))
    return shapely.union_all([q for q in getattr(g, "geoms", [g]) if q.geom_type in ("Polygon", "MultiPolygon")])


def run_checks(spec):
    c, W, E = D.load_ctx()
    reg = json.load(open(os.path.join(D.SPEC, "registry.json"), encoding="utf-8"))
    T = terrain.terrain()
    H = D.houses(W)
    own = D.utility_own(reg)
    Hn = H[~shapely.within(H, own)]
    ch = {}
    Z = [(z, zone_poly(z)) for z in spec["zones"]]
    # coverage
    U = shapely.union_all([p for _, p in Z])
    ov = sum(p.area for _, p in Z) - U.area
    ch["coverage"] = {"district_ha": round(W.area / 1e4, 1), "zones_ha": round(U.area / 1e4, 1), "uncovered_ha": round(W.difference(U).area / 1e4, 2),
                      "outside_ha": round(U.difference(W).area / 1e4, 2), "overlap_ha": round(ov / 1e4, 2), "zones": len(Z)}
    # houses
    hit = {}
    for z, p in Z:
        if z["use"] == "village_existing":
            continue
        n = int(shapely.intersects(p.buffer(-1), Hn).sum())
        if n:
            hit[z["id"]] = n
    ax_hit = {}
    for a in spec["axes"]:
        if a["status"] != "new":
            continue
        n = int(shapely.intersects(LineString(a["line"]).buffer(HALF_W[a["class"]]), Hn).sum())
        if n:
            ax_hit[a["id"]] = n
    lrt_g = LineString(spec["lrt"]["line"])
    n_lrt = int(shapely.intersects(lrt_g.buffer(10), Hn).sum())
    spur = [o for o in spec["objects"] if o.get("line")]
    n_spur = int(shapely.intersects(LineString(spur[0]["line"]).buffer(15), Hn).sum()) if spur else 0
    ch["houses"] = {"houses_in_district": int(len(H)), "utility_own_buildings": int(len(H) - len(Hn)),
                    "zones_hit": hit, "zones_hit_total": int(sum(hit.values())), "new_axes_hit": ax_hit, "lrt_hit": n_lrt, "rail_spur_hit": n_spur,
                    "rule": "дом = здание Overture (OSM + Microsoft ML) или existing_osm двойника; постройки ПС и СЭС внутри их контуров + 30 м не считаются; дорога — буфер полуширины по классу"}
    # water and flood
    wg, wp = layers.load("water")
    wat = shapely.union_all([g for g in wg if g.geom_type in ("Polygon", "MultiPolygon") and g.intersects(W)])
    built = ("mixed_centre", "business", "residential_high", "residential_mid", "residential_low", "campus", "medical", "industry", "logistics", "sport")
    wz = {z["id"]: round(p.intersection(wat).area, 1) for z, p in Z if z["use"] in built and p.intersects(wat)}
    bridges = []
    kas = shapely.union_all([g for g, pp in zip(wg, wp) if pp.get("name") in ("Қаскелең", "Каскелен")])
    for a in spec["axes"] + [{"id": "lrt_airport", "line": spec["lrt"]["line"], "status": "new"}] + ([{"id": "rail_spur", "line": spur[0]["line"], "status": "new"}] if spur else []):
        if a["status"] != "new":
            continue
        g = LineString(a["line"])
        x = g.intersection(kas.union(wat))
        if not x.is_empty:
            pts = x if x.geom_type in ("Point", "MultiPoint") else x.centroid
            bridges.append({"axis": a["id"], "crossings": len(getattr(x, "geoms", [x])), "at": [round(v) for v in pts.centroid.coords[0]], "as": "мост"})
    kl, kp = layers.load("derived/kapchagay_levels")
    f485 = [g for g, pp in zip(kl, kp) if "485" in json.dumps(pp)]
    fl = shapely.union_all(f485) if f485 else None
    ch["water"] = {"built_zones_on_water_m2": wz, "axes_on_water": "только мосты", "bridges": bridges,
                   "flood_485_in_district_ha": round(fl.intersection(W).area / 1e4, 2) if fl is not None else "слой 485 не найден",
                   "min_ground_m": round(float(T.height(*np.array(W.exterior.coords).T).min()), 1),
                   "note": "минимальная отметка района 508 м, линия 485 м до района не доходит"}
    # joints
    axl = {a["id"]: LineString(a["line"]) for a in spec["axes"]}
    axl["lrt_airport"] = lrt_g
    rl, rp = layers.load("rail")
    axl["rail:rail_bypass_zhetygen_kazybek"] = shapely.union_all([g for g, pp in zip(rl, rp) if (pp.get("name") or "").startswith("Жетыген")])
    J = {j["id"]: j for j in c["joints"]["items"]}
    jr = []
    for m in spec["joints"]:
        j = J[m["joint_id"]]
        d = axl[m["axis"]].distance(Point(j["x"], j["z"]))
        jr.append({"joint_id": m["joint_id"], "axis": m["axis"], "dist_m": round(d, 1), "ok": d <= 150})
    ch["joints"] = {"count": len(jr), "met": sum(r["ok"] for r in jr), "max_dist_m": max(r["dist_m"] for r in jr), "failed": [r for r in jr if not r["ok"]], "tolerance_m": 150}
    # registry coverage
    ids = {o["registry_id"] for o in spec["objects"]}
    mine = []
    for r in reg["rows"]:
        if r.get("geom"):
            g = shape(r["geom"])
            q = g if g.geom_type == "Point" else g.representative_point()
            if W.contains(q):
                mine.append(r["id"])
    ch["registry"] = {"rows_with_point_in_district": sorted(mine), "missing": sorted(set(mine) - ids), "rows_in_spec": len(ids),
                      "agreed_split": "без геометрии: W берёт airport_alatau, airport_rail_station, rail_sorting_station, dry_port, rhenus_hub, vocational_institute; "
                                      "E (w41) — uam_center_eurasia, evtol_plant, road_growing_10km; общие программы — обе половины (оркестратор, 31.10)"}
    # shares and capacity
    from collections import defaultdict
    a = defaultdict(float); res = 0.0; jobs = 0.0; homes = 0.0
    for z, p in Z:
        ha = p.area / 1e4
        a[z["use"]] += ha
        r_, j_ = capacity(z["use"], ha, z.get("density", {}))
        res += r_; jobs += j_; homes += r_ / PERS_PER_HOME
    vz = shapely.union_all([p for z, p in Z if z["use"] == "village_existing"])
    vill = int(shapely.intersects(vz, Hn).sum())
    vill_res = 0
    tgt = spec["targets"]
    ch["zones_share"] = {k: {"ha": round(v), "pct": round(100 * v / (W.area / 1e4), 1)} for k, v in sorted(a.items(), key=lambda t: -t[1])}
    ch["capacity"] = {"residents_new": round(res), "village_houses_kept": vill, "residents_total": round(res + vill_res),
                      "target_population": tgt["population_2050"], "pop_dev_pct": round(100 * (res + vill_res - tgt["population_2050"]) / tgt["population_2050"], 1),
                      "jobs": round(jobs), "target_jobs": tgt["jobs_2050"], "jobs_dev_pct": round(100 * (jobs - tgt["jobs_2050"]) / tgt["jobs_2050"], 1),
                      "homes_model": round(homes),
                      "method": f"жители = площадь × FAR × доля жилья ({HOUSING_SHARE} в жилых зонах, 0,45 в центре) / 30 м² (как CityStats); рабочие места = площадь × jobs_per_ha; "
                                f"аэропорт {AIRPORT_JOBS} мест (модель qTwin: ≈ 1 000 на 1 млн пасс.); квартира = {PERS_PER_HOME} чел.; существующие дома посёлков и дач, как в CityStats, в цель не входят",
                      "ok_10pct": abs(res + vill_res - tgt["population_2050"]) <= 0.1 * tgt["population_2050"] and abs(jobs - tgt["jobs_2050"]) <= 0.1 * tgt["jobs_2050"]}
    # slope
    cz = shapely.union_all([p for z, p in Z if z["id"] == "ctr_main" or z["id"].startswith("ctr_main_")])
    mc = [ce for ce in spec["centres"] if ce["kind"] == "main"][0]
    xs = np.arange(cz.bounds[0], cz.bounds[2], 50); zs = np.arange(cz.bounds[1], cz.bounds[3], 50)
    X, Y = np.meshgrid(xs, zs); m = shapely.contains_xy(cz, X, Y)
    sl = T.slope(X[m], Y[m]) * 100
    ch["slope"] = {"main_centre_point_pct": round(float(T.slope(mc["x"], mc["z"]) * 100), 2), "main_centre_zone_mean_pct": round(float(sl.mean()), 2),
                   "main_centre_zone_p90_pct": round(float(np.percentile(sl, 90)), 2), "axes": {}}
    for ax in spec["axes"] + [{"id": "lrt_airport", "line": spec["lrt"]["line"]}] + ([{"id": "rail_spur", "line": spur[0]["line"]}] if spur else []):
        s, x, z, h = T.profile(ax["line"], 25)
        if len(s) < 10:
            continue
        hs = np.interp(np.arange(0, s[-1], 200), s, h)
        g200 = np.abs(np.diff(hs)) / 200 * 100 if len(hs) > 1 else np.array([0])
        h2 = np.interp(np.arange(0, s[-1], 100), s, h)
        k = 20 if len(h2) > 20 else len(h2) - 1
        g2k = np.abs(h2[k:] - h2[:-k]).max() / (k * 100) * 100 if k > 0 else 0.0
        ch["slope"]["axes"][ax["id"]] = {"len_km": round(s[-1] / 1000, 2), "rise_m": round(float(h.max() - h.min()), 1),
                                          "terrain_max_grade_200m_pct": round(float(g200.max()), 2), "terrain_max_grade_2km_pct": round(float(g2k), 2),
                                          "mean_grade_pct": round(float(abs(h[-1] - h[0]) / s[-1] * 100), 2)}
    ch["slope"]["note"] = ("уклон рельефа под осью; профиль дороги, ЛРТ и ж/д выравнивается насыпью и выемкой: проектный уклон ≈ уклону за 2 км "
                           "(ЛРТ ≤ 6 %, ж/д ветка ≤ 1,2 %, магистраль ≤ 5 %)")
    # height limits
    hz, hp = layers.load("derived/height_zones")
    hzs = {pp["id"]: g for g, pp in zip(hz, hp)}
    tall = [z["id"] for z, _ in Z if z.get("density", {}).get("floors_typical", 0) * 3.3 >= 50]
    arp = Point(*D.RWY["centre"])
    ch["height_new_airport"] = {"r10_share_pct": round(100 * arp.buffer(10000, 128).intersection(W).area / W.area, 1),
                                "r30_share_pct": round(100 * arp.buffer(30000, 128).intersection(W).area / W.area, 1),
                                "note": "кольца от новой КТА (центр ВПП); в city.json height_limits ещё стоит старая точка (−5900, 8300)"}
    ch["height"] = {"max_floors_rule": "все зоны ≤ 12 этажей (≈ 40 м): ни одного здания ≥ 50 м, согласование аэродромов не нужно; исключение — диспетчерская вышка аэропорта (≈ 50–70 м, модель), «нужно согласование» как часть проекта аэропорта",
                    "zones_with_typical_50m_plus": tall,
                    "district_share_in": {k: round(100 * hzs[k].intersection(W).area / W.area, 1) for k in hzs if hzs[k].intersects(W)}}
    ch["airport"] = airport_checks(c, W, T, Hn)
    return ch


def surfaces_for(p_thr, d, length=15000.0, inner=150.0, div=0.15, start=60.0):
    s = p_thr + d * start
    v = np.array([-d[1], d[0]])
    return Polygon([s + v * inner, s - v * inner, s + d * length - v * (inner + div * length), s + d * length + v * (inner + div * length)])


def climb_for(p_end, d, length=15000.0):
    s = p_end + d * 60
    v = np.array([-d[1], d[0]])
    wfin = 600.0
    k = (wfin - 90) / 0.125
    return Polygon([s + v * 90, s - v * 90, s + d * k - v * wfin, s + d * length - v * wfin, s + d * length + v * wfin, s + d * k + v * wfin])


def airport_surfaces():
    p0, p1 = D.rwy_ends()
    u = (p1 - p0) / np.linalg.norm(p1 - p0)
    return {"approach_w": surfaces_for(p0, -u), "approach_e": surfaces_for(p1, u), "climb_w": climb_for(p0, -u), "climb_e": climb_for(p1, u)}


def airport_checks(c, W, T, Hn):
    p0, p1 = D.rwy_ends()
    s, x, z, h = T.profile([p0, p1], 25)
    af = {a["id"]: a for a in c["height_limits"]["airfields"]}
    zh = af["zhetygen_mil"]
    C = np.array(D.RWY["centre"])
    d_zh = float(np.hypot(*(C - [zh["x"], zh["z"]])))
    # Zhetygen runway (Overture) and its surfaces
    zr0, zr1 = np.array([7421.0, 13077.0]), np.array([8025.0, 15549.0])
    zu = (zr1 - zr0) / np.linalg.norm(zr1 - zr0)
    zs = shapely.union_all([surfaces_for(zr0, -zu), surfaces_for(zr1, zu), climb_for(zr0, -zu), climb_for(zr1, zu)])
    S = airport_surfaces()
    ours = shapely.union_all(list(S.values()))
    golden = Polygon(c["districts"]["golden"]["polygon"]).buffer(0)
    strip = D.rwy_rect(-D.RWY["length"] / 2 - 60, D.RWY["length"] / 2 + 60, -140, 140)
    ig, ip = layers.load("infrastructure")
    pl = shapely.union_all([g for g, pp in zip(ig, ip) if pp.get("class") in ("power_line", "minor_line") and g.distance(W) < 20000])
    # power-line clearance under the approach surfaces (towers assumed 50 m, model)
    elev = float(h.max())
    clear = {}
    for k, poly in S.items():
        g = poly.intersection(pl)
        if g.is_empty:
            clear[k] = None
            continue
        thr = p0 if k.endswith("_w") else p1
        d = (p0 - p1) / np.linalg.norm(p0 - p1) if k.endswith("_w") else (p1 - p0) / np.linalg.norm(p1 - p0)
        pts = np.array([[q.x, q.y] for gg in getattr(g, "geoms", [g]) for q in (gg.interpolate(t) for t in np.arange(0, gg.length + 1, 50))])
        dist = (pts - thr) @ d - 60
        if k.startswith("approach"):
            lim = np.where(dist < 3000, 0.02 * dist, np.where(dist < 6600, 60 + 0.025 * (dist - 3000), 150.0))
        else:
            lim = 0.02 * dist
        top = T.height(pts[:, 0], pts[:, 1]) + 50 - elev
        clear[k] = round(float((lim - top).min()), 1)
    hz = c["height_limits"]
    return {
        "runway": {"ends": [rnd([p0])[0], rnd([p1])[0]], "bearing_deg": D.RWY["bearing"], "length_m": D.RWY["length"], "width_m": D.RWY["width"],
                   "elev_min_max_m": [round(float(h.min()), 1), round(float(h.max()), 1)], "longitudinal_slope_pct": round(float((h.max() - h.min()) / s[-1] * 100), 2),
                   "norm": "аналог ICAO Annex 14 т. I (код 4): уклон ≤ 1 %, полоса ВПП 2 × 140 м, RESA 240 м, захода 15 км (2 % / 2,5 % / горизонт 150 м), взлёт 2 %; длина 4 000 м — как у длинных ВПП региона (ALA 4 420 м по OSM) при 640 м над морем; аналог, проверить на уровне 1"},
        "strip_inside_district": strip.within(W),
        "houses_within_300m_of_strip": int(shapely.intersects(strip.buffer(300), Hn).sum()),
        "nearest_houses_m": round(float(shapely.distance(strip, Hn).min())),
        "nearest_lake_m": round(float(strip.distance(shapely.union_all([g for g in layers.load("water")[0] if g.geom_type in ("Polygon", "MultiPolygon") and g.area > 5e4])))),
        "power_lines_min_dist_to_runway_m": round(float(strip.distance(pl))),
        "power_line_clearance_under_surfaces_m": clear,
        "zhetygen": {"arp": [zh["x"], zh["z"]], "dist_arp_to_arp_km": round(d_zh / 1000, 1), "r10_zones_overlap": d_zh < 20000,
                     "surfaces_overlap_ha": round(ours.intersection(zs).area / 1e4, 1),
                     "zhetygen_runway": "Overture: (7421, 13077) – (8025, 15549), курс ≈ 014°/194°, 2 544 м",
                     "note": "курсы почти перпендикулярны (095° и 014°); 15-км поверхности заходов и взлётов двух аэродромов не пересекаются; кольца 30 км пересекаются (обычное дело для двух аэродромов), кольца 10 км — нет"},
        "golden": {"surfaces_over_golden_ha": round(ours.intersection(golden).area / 1e4, 1),
                   "surface_height_there": "≥ 150 м над порогом (≈ 790 м абс.) — над Golden (550–640 м) это ≥ 150–240 м; Golden строит 4–12 этажей, конфликта нет"},
        "r30_new_airport_vs_city_json": "city.json height_limits ещё держит старую точку аэропорта (alatau_new_r10/r30 из (−5900, 8300)?); после утверждения пересчитать кольца от новой КТА"
                                         if any(a["id"].startswith("alatau") for a in hz["airfields"]) else "в city.json нового аэропорта нет",
    }


def write_spec(spec):
    tmp = D.OUT_SPEC + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(dump(spec))
    os.replace(tmp, D.OUT_SPEC)


def dump(spec):
    """Compact but hand-editable JSON: one zone / axis / object per line block, coordinates inline."""
    s = json.dumps(spec, ensure_ascii=False, indent=1)
    import re
    s = re.sub(r"\[\s+(-?\d+(?:\.\d+)?),\s+(-?\d+(?:\.\d+)?)\s+\]", r"[\1, \2]", s)
    s = re.sub(r"\[\s*((?:\[-?\d+(?:\.\d+)?, -?\d+(?:\.\d+)?\],?\s*)+)\]", lambda m: "[" + re.sub(r"\s+", " ", m.group(1)).strip() + "]", s)
    s = re.sub(r"\[\s+(\d{4}),\s+(\d{4})\s+\]", r"[\1, \2]", s)
    return s + "\n"


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("build", "all"):
        spec = build_spec()
    else:
        spec = json.load(open(D.OUT_SPEC, encoding="utf-8"))
    if what in ("build", "check", "all"):
        spec["checks"] = run_checks(spec)
        spec["open_questions"] = [
            {"id": "q1", "question_ru": "Аэропорт рассчитываем на 15 млн пассажиров в год (генплан № 727), а не на 40 млн из новостей 2025 года?", "answer": "да / нет",
             "why": "40 млн требуют второй ВПП в 1–1,5 км от первой; в хвосте Growing-запад она не помещается (граница района и пара ВЛ 500 кВ), пришлось бы выходить за город или переносить ЛЭП"},
            {"id": "q2", "question_ru": "Две зимовки у западного торца ВПП (23 постройки в 350–950 м от лётной полосы) оставляем на месте?", "answer": "да / нет",
             "why": "правило «сёла остаются» их сохраняет, но они попадают в шумовую и охранную зону аэропорта; при «нет» — выкуп и снос к 2041 году"}]
        write_spec(spec)
        print(json.dumps(spec["checks"], ensure_ascii=False, indent=1)[:6000])
    if what in ("draw", "all"):
        import growing_w_draw
        growing_w_draw.draw(spec, os.path.join(OUT_DIR, "scheme.png"))
