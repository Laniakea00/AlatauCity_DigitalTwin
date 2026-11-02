"""OUT/compare.md: open map data (Overture/OSM) against the twin.

    python3 -I tools/map/geo/compare_twin.py           (build_city.py runs it at the end)

1) existing roads: OSM km by class vs roads.json edges open in 2025 (base scenario) — the twin has no class «existing»;
2) villages whose streets the twin lacks; 3) OSM buildings vs the twin's existing_osm buildings (count, match rate, offset);
4) anything surprising."""
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import frames  # noqa: E402
import layers  # noqa: E402
import twin  # noqa: E402

MAP_CLASS = {"motorway": "highway", "trunk": "highway", "primary": "main", "secondary": "main", "tertiary": "street",
             "residential": "street", "living_street": "street", "unclassified": "street", "service": "service", "track": "track", "unknown": "unknown"}
STREETS = ("tertiary", "residential", "living_street", "unclassified")


def f0(v):
    return f"{v:,.0f}".replace(",", " ")


def f1(v):
    return f"{v:,.1f}".replace(",", " ").replace(".", ",")


def main():
    D, _ = twin.district_polygons()
    city = twin.city_outline(D)
    shapely.prepare(city)
    spec = json.load(open(os.path.join(frames.SPEC_DIR, "city.json"), encoding="utf-8"))
    L = []
    w = L.append
    w("# Сравнение: открытые данные (Overture/OSM) и двойник\n")
    w(f"Данные: Overture Maps {frames.OVERTURE_RELEASE} («© OpenStreetMap contributors, Overture Maps Foundation»), выгрузка 31.10.2026; двойник — "
      "`roads.json`, `buildings.csv`, `layer_buildings.bytes` (снимок ноутбука 31.10.2026 15:47). Всё в системе Unity, только внутри границы города "
      f"(объединение районов двойника, {f0(city.area / 1e4)} га). Скрипт: `tools/map/geo/compare_twin.py`.\n")

    # ------------------------------------------------------------------ 1. roads
    rg, rp = layers.load("roads")
    hit = np.flatnonzero(shapely.intersects(city, rg))
    osm = []
    for i in hit:
        g = rg[i].intersection(city)
        osm.append((g, rp[i]))
    okm = Counter(); okm_d = defaultdict(Counter)
    for g, p in osm:
        okm[p.get("class", "unknown")] += g.length / 1000
        for k in twin.DISTRICTS:
            if g.intersects(D[k]):
                okm_d[k][MAP_CLASS.get(p.get("class", "unknown"), "unknown")] += g.intersection(D[k]).length / 1000
    R = twin.roads()
    tw = []
    for i, e in enumerate(R["edges"]):
        gg = e["g"]
        ls = LineString(list(zip(gg[0::2], gg[1::2])))
        tw.append((ls, e))
    tg = np.array([t[0] for t in tw], dtype=object)
    tin = shapely.intersects(city, tg)
    tkm = Counter(); tkm_all = Counter(); tkm_d = defaultdict(Counter)
    for (ls, e), ok in zip(tw, tin):
        if not ok:
            continue
        g = ls.intersection(city)
        tkm_all[e["c"]] += g.length / 1000
        if e["y"][0] <= 2025:
            tkm[e["c"]] += g.length / 1000
            for k in twin.DISTRICTS:
                if g.intersects(D[k]):
                    tkm_d[k][e["c"]] += g.intersection(D[k]).length / 1000
    w("## 1. Существующие дороги: км по классам\n")
    w("В `roads.json` нет класса «existing»: существующей считаем дорогу, открытую к 2025 году в базовом сценарии (`y[0] ≤ 2025`). "
      "Генератор двойника (`gen_twin.py road_years`) ставит 2025 всем трассам, кольцу и магистралям, в том числе будущим, а улицам — год по застройке, поэтому "
      "«2025» в двойнике — это не «есть на земле», а «не позже старта».\n")
    w("| Класс OSM | км OSM в городе | ≈ класс двойника |\n|---|---:|---|")
    for c, v in okm.most_common():
        w(f"| {c} | {f1(v)} | {MAP_CLASS.get(c, '—')} |")
    w(f"| **всего** | **{f1(sum(okm.values()))}** | |\n")
    w("| Класс двойника | км двойника, год ≤ 2025 | км двойника, все годы | км OSM в тех же классах (сведено) |\n|---|---:|---:|---:|")
    agg = Counter()
    for c, v in okm.items():
        agg[MAP_CLASS.get(c, "unknown")] += v
    for c in ("highway", "ring", "main", "street"):
        w(f"| {c} | {f1(tkm[c])} | {f1(tkm_all[c])} | {f1(agg.get(c, 0)) if c != 'ring' else 'в OSM БАКАД = motorway/trunk'} |")
    w(f"| service + track (в двойнике нет) | — | — | {f1(agg['service'] + agg['track'])} |")
    w(f"| **всего** | **{f1(sum(tkm.values()))}** | **{f1(sum(tkm_all.values()))}** | **{f1(sum(okm.values()))}** |\n")
    w("По районам (км, OSM сведено к классам двойника / двойник год ≤ 2025):\n")
    w("| Район | highway OSM / двойник | main OSM / двойник | street OSM / двойник | service+track OSM |\n|---|---:|---:|---:|---:|")
    for k in twin.DISTRICTS:
        o, t = okm_d[k], tkm_d[k]
        w(f"| {k} | {f1(o['highway'])} / {f1(t['highway'] + t['ring'])} | {f1(o['main'])} / {f1(t['main'])} | {f1(o['street'])} / {f1(t['street'])} | {f1(o['service'] + o['track'])} |")
    # coverage: share of OSM streets that have any twin road within 25 m
    tw25 = unary_union([ls for (ls, e), ok in zip(tw, tin) if ok and e["y"][0] <= 2025]).buffer(25)
    twall25 = unary_union([ls for (ls, e), ok in zip(tw, tin) if ok]).buffer(25)
    shapely.prepare(tw25); shapely.prepare(twall25)
    cov = {}
    for grp, classes in (("трассы и магистрали (motorway…secondary)", ("motorway", "trunk", "primary", "secondary")),
                         ("улицы (tertiary, residential, living_street, unclassified)", STREETS)):
        gs = [g for g, p in osm if p.get("class") in classes]
        tot = sum(g.length for g in gs)
        c25 = sum(g.intersection(tw25).length for g in gs)
        call = sum(g.intersection(twall25).length for g in gs)
        cov[grp] = (tot, c25, call)
    w("\nДоля дорог OSM, у которых в двойнике есть дорога в 25 м (по длине):\n")
    w("| Что | км OSM | рядом дорога двойника ≤ 2025 | рядом дорога двойника любого года |\n|---|---:|---:|---:|")
    for grp, (tot, a, b) in cov.items():
        w(f"| {grp} | {f1(tot / 1000)} | {a / tot * 100:.0f} % | {b / tot * 100:.0f} % |")
    w("")

    # ------------------------------------------------------------------ 2. villages without their streets
    sg, sp = layers.load("derived/settlements")
    rows = []
    street_geoms = [(g, p) for g, p in osm if p.get("class") in STREETS + ("service",)]
    sgeo = np.array([g for g, _ in street_geoms], dtype=object)
    for g, p in zip(sg, sp):
        if p.get("share_in_city", 0) <= 0.05:
            continue
        shapely.prepare(g)
        m = shapely.intersects(g, sgeo)
        okm_s = sum(sgeo[i].intersection(g).length for i in np.flatnonzero(m)) / 1000
        t25 = 0.0; tall = 0.0
        for (ls, e), ok in zip(tw, tin):
            if ok and e["c"] == "street" and ls.intersects(g):
                L_ = ls.intersection(g).length / 1000
                tall += L_
                if e["y"][0] <= 2025:
                    t25 += L_
        # how much of the village's OSM streets the twin covers (any year, 25 m)
        cv = sum(sgeo[i].intersection(g).intersection(twall25).length for i in np.flatnonzero(m)) / 1000
        rows.append((p["name"], p.get("district"), p.get("overture_buildings", 0), p.get("twin_existing_buildings", 0), okm_s, t25, tall, cv))
    rows.sort(key=lambda r: -r[4])
    w("## 2. Посёлки: есть ли у них улицы в двойнике\n")
    w("Улицы OSM = tertiary, residential, living_street, unclassified, service внутри контура посёлка (контуры: `derived/settlements.geojson`). "
      "«Покрыто» — доля длины улиц OSM, у которых в двойнике есть улица любого года в 25 м. **Улиц 2025 года у двойника нет ни в одном посёлке города** "
      "(колонка «≤ 2025» везде 0): всё, что там есть, — плановые оси 2026–2099, проложенные частично по старым улицам, частично поверх домов.\n")
    w("| Посёлок | Район | Зданий OSM | Зданий двойника (existing) | Улиц OSM, км | Улиц двойника ≤ 2025, км | Улиц двойника всех лет, км | Покрыто | Вывод |\n|---|---|---:|---:|---:|---:|---:|---:|---|")
    lacking = []
    for n, d, nb, nt, o, t25, tall, cv in rows:
        share = cv / o if o else 0
        verdict = "улиц нет" if share < 0.25 else ("частично" if share < 0.6 else "есть")
        if share < 0.6 and o >= 1:
            lacking.append(n)
        w(f"| {n} | {d or '—'} | {f0(nb)} | {f0(nt)} | {f1(o)} | {f1(t25)} | {f1(tall)} | {share * 100:.0f} % | {verdict} |")
    w(f"\n**Посёлки без своих улиц в двойнике сегодня (2025):** все {len(rows)}: {', '.join(r[0] for r in rows)}. "
      f"**Даже с плановыми осями всех лет покрыто меньше 60 %:** {', '.join(lacking) if lacking else 'нет'}.\n")

    # ------------------------------------------------------------------ 3. buildings
    bg, bp = layers.load("buildings")
    bc = shapely.centroid(bg)
    inb = shapely.contains_xy(city, shapely.get_x(bc), shapely.get_y(bc))
    B = twin.buildings()
    ex = B[B.source == "existing_osm"]
    ex_in = ex[shapely.contains_xy(city, ex.x.values, ex.z.values)]
    fp = twin.footprints(ex.bid.values)
    src = Counter(bp[i].get("src", "?") for i in np.flatnonzero(inb))
    og = bg[inb]
    tree = shapely.STRtree(og)
    # match: twin footprint ↔ OSM footprint with IoU ≥ 0.3 (best), else centroid-in
    tb = np.array([fp[b] for b in ex_in.bid.values], dtype=object)
    pairs = tree.query(tb, predicate="intersects")
    best = {}
    for ti, oi in zip(pairs[0], pairs[1]):
        a, b = tb[ti], og[oi]
        inter = a.intersection(b).area
        iou = inter / (a.area + b.area - inter) if inter > 0 else 0
        if iou > best.get(ti, (0, -1))[0]:
            best[ti] = (iou, oi)
    m30 = {ti: oi for ti, (iou, oi) in best.items() if iou >= 0.3}
    mc = 0
    ctr = shapely.centroid(tb)
    for ti in range(len(tb)):
        if ti in m30:
            continue
        q = tree.query(ctr[ti], predicate="within")
        if len(q):
            mc += 1
    dx = np.array([shapely.get_x(og[oi].centroid) - shapely.get_x(ctr[ti]) for ti, oi in m30.items()])
    dz = np.array([shapely.get_y(og[oi].centroid) - shapely.get_y(ctr[ti]) for ti, oi in m30.items()])
    used_o = set(m30.values())
    ious = np.array([best[ti][0] for ti in m30])
    w("## 3. Здания: OSM (Overture) и существующие здания двойника\n")
    w(f"- Зданий Overture в городе (центр внутри границы): **{f0(inb.sum())}**; по источникам: " + ", ".join(f"{k} {f0(v)}" for k, v in src.most_common()) + ".")
    w(f"- Существующих зданий двойника (`existing_osm`): всего {f0(len(ex))}, в городе **{f0(len(ex_in))}**.")
    w(f"- Совпадение по контуру (IoU ≥ 0,3; контур двойника — выпуклая оболочка меша): **{f0(len(m30))} из {f0(len(ex_in))} = {len(m30) / len(ex_in) * 100:.1f} %**, "
      f"медиана IoU {np.median(ious):.2f}; ещё {f0(mc)} зданий двойника стоят центром внутри здания OSM. Итого найдено {(len(m30) + mc) / len(ex_in) * 100:.1f} %.")
    w(f"- Сдвиг центров совпавших пар (OSM − двойник): медиана dx {np.median(dx):+.2f} м, dz {np.median(dz):+.2f} м; 90 % пар ближе {np.percentile(np.hypot(dx, dz), 90):.1f} м. "
      "Значит, система координат двойника = UTM 43N − (663000, 4830000) без сдвига: существующие дома двойника стоят ровно на месте зданий OSM.")
    w(f"- Зданий OSM в городе, которых у двойника нет: **{f0(inb.sum() - len(used_o))}** ({(inb.sum() - len(used_o)) / inb.sum() * 100:.0f} %).\n")
    w("| Район | Зданий OSM | Существующих в двойнике | Совпало (IoU ≥ 0,3) | Доля двойника, найденная в OSM | Зданий OSM без пары |\n|---|---:|---:|---:|---:|---:|")
    ex_in_d = ex_in.assign(i=np.arange(len(ex_in)))
    for k in twin.DISTRICTS:
        no = int(shapely.contains_xy(D[k], shapely.get_x(bc[inb]), shapely.get_y(bc[inb])).sum())
        sub = ex_in_d[shapely.contains_xy(D[k], ex_in_d.x.values, ex_in_d.z.values)]
        mm = sum(1 for i in sub.i.values if i in m30)
        oin = [oi for oi in used_o if D[k].contains(og[oi].centroid)]
        w(f"| {k} | {f0(no)} | {f0(len(sub))} | {f0(mm)} | {mm / max(1, len(sub)) * 100:.0f} % | {f0(no - len(oin))} |")
    w("")

    # ------------------------------------------------------------------ 4. surprises
    pr = json.load(open(os.path.join(frames.OUT, "transform_proof.json"), encoding="utf-8"))
    w("## 4. Что удивило\n")
    gp_rows = {r["district"]: r for r in pr["districts"]}
    w(f"1. **Районы geojson ≠ районы двойника.** Внешний контур совпадает (медиана {pr['city_outline']['geojson_to_twin']['median_m']} м), "
      f"Gate почти совпадает, но внутренние границы Golden/Growing/Green в geojson — прямые разрезы, подогнанные по площади. "
      f"Из зданий Growing двойника внутри geojson-Growing только {gp_rows['Growing']['share_in_geojson_pct']} %, Green — {gp_rows['Green']['share_in_geojson_pct']} %. "
      "В city.json взяты контуры двойника (модель QTwin), geojson — альтернатива.")
    if isinstance(pr.get("osm_boundary"), dict):
        ob = pr["osm_boundary"]
        w(f"2. **Контур города в geojson — это граница Алатау из OSM.** Граница county «Алатау» в Overture: {f0(ob['area_ha'])} га, центроид "
          f"({ob['centroid'][0]:.0f}, {ob['centroid'][1]:.0f}) = origin geojson (−517, 7351); медиана расхождения с geojson {ob['osm_to_geojson']['median_m']} м.")
    w(f"3. **Трасса А-3 (KAZ08) и ось двойника.** Ось деления Growing — это трасса двойника класса highway, в OSM под ней KAZ08 / E40 / AH60 "
      f"(«{', '.join(spec['growing_split']['osm_names'][:1])}»).")
    af = [a for a in spec["height_limits"]["airfields"] if a["named_by"] == "overture"]
    if af:
        w("4. **Аэродромы, которых нет в research:** " + "; ".join(f"{a['name']} ({a['x']:.0f}, {a['z']:.0f})" for a in af) +
          ". Байсерке лежит внутри города. Все добавлены в высотные зоны с пометкой «найден в Overture».")
    tomtom = sum(1 for g, p in osm if p.get("src") == "TomTom")
    w(f"5. **В дорогах Overture есть не только OSM:** {tomtom} сегментов в городе от TomTom. Здания: " + ", ".join(f"{k} {f0(v)}" for k, v in src.most_common()) + ".")
    wr = {r["id"]: r for r in spec["water"]["features"]}
    if "bak" in wr:
        b = wr["bak"]
        w("6. **БАК** " + (f"в OSM есть ({', '.join(b.get('osm_names', []))}), но {b.get('note', 'в городе')}." if b.get("found") else "в OSM не найден."))
    gl = []
    for key, nm in (("kaskelen", "Каскелен"), ("malaya_almatinka", "Малая Алматинка"), ("yesentai", "Есентай"), ("bak", "БАК"), ("kapchagay", "берег Капшагая")):
        r = wr.get(key)
        if r and r.get("genplan_vs_osm"):
            g = r["genplan_vs_osm"]
            gl.append(f"{nm} — медиана {g['median_m']} м, 90 % ближе {g['p90_m']} м")
    if gl:
        w("7. **Реки geojson генплана — это линии OSM:** расстояние от линии geojson (после сдвига) до объекта Overture: " + "; ".join(gl) +
          ". Ещё одно независимое подтверждение сдвига.")
    w(f"8. **Существующие улицы.** В двойнике у посёлков почти нет своих улиц 2025 года: улицы двойника там — плановые оси, которые идут поверх домов "
      f"(research/inventory.md §2.5: 446 из 475 зданий, разрезанных осями, — existing_osm).")
    w(f"9. **Iconic.** В коде два места: LandmarkData −3170, −19080 (действующее) и −2567, −20654 (первое место, его помнят только инструменты Python и "
      f"неиспользуемый iconic_district.json). До центроида Gate {spec['iconic']['dist_to_gate_centroid_m']:.0f} м, до полюса недоступности "
      f"{spec['iconic']['dist_to_gate_pole_m']:.0f} м: Iconic стоит в северной части Gate, а не в центре (решение владельца — в центр).")
    p = frames.out("compare.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"[compare] {p}")


if __name__ == "__main__":
    main()
