#!/usr/bin/env python3
"""Cartographer's numbers for the whole Gate district (w47, level 2), as the plan asks («Что сдаёт картограф»):
residents, jobs, km of roads, ha of parks, parking places (with the deviation from the target), the service table per
residential block, the moved objects «было → стало → почему» and the registry objects «по источнику / по правилу».

    python3 -I tools/map/district/gate_numbers.py [--out OUT]

Reads spec/gate.json and OUT/gate/*.json (run tools/map/run.py gate first); writes
OUT/gate/numbers.md (Russian) and prints the headline numbers. Counting follows validate/rules/years.py (rule 24)
and validate/rules/buildings.py (rule 14 service table), so the numbers here are the validator's numbers.
"""
import importlib.util
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
sys.path[:0] = [MAP, os.path.join(MAP, "validate"), os.path.join(MAP, "gen")]
from shapely.geometry import LineString, Polygon  # noqa: E402

import context  # noqa: E402
import land_rulekit as K  # noqa: E402
import land_util as U  # noqa: E402

D = "gate"
SVC_RU = {"kindergarten": "сад", "school": "школа", "polyclinic": "поликл.", "pharmacy_shop": "аптека/магазин",
          "square_or_park": "сквер/парк", "stop": "остановка", "fire_station": "пож. депо"}


def pct(got, t):
    return f"{(got - t) / t * 100:+.1f} %" if t else "—"


def main(argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    ctx = context.build(D, out)
    spec = ctx.spec
    T = spec.get("targets") or {}
    area = Polygon(spec["area"]).buffer(0)
    m2_res = U.twin_m2()[0]
    home_m2 = float(T.get("home_m2") or U.LEVEL0_HOME_M2)
    B = K.buildings(ctx)
    lots = K.lots(ctx)
    land = [L for L in lots if L["use"] == "landmark"]
    keep = [L for L in land if L["source"] == "keep"]

    # residents, homes, jobs: rule 24 (new city without keep and without existing houses) and the area with the keep quarter;
    # existing houses carry homes / jobs by the 600 m² rule (gen_buildings, w44) but stay out of the targets
    homes_all = sum(b["homes"] for b in B if b["source"] != "existing_osm") + sum(L["capacity"].get("homes", 0) for L in land)
    jobs_all = sum(b["jobs"] for b in B if b["source"] != "existing_osm") + sum(L["capacity"].get("jobs", 0) for L in land)
    homes_ex = sum(b["homes"] for b in B if b["source"] == "existing_osm")
    jobs_ex = sum(b["jobs"] for b in B if b["source"] == "existing_osm")
    res_new_b = sum(b["gfa_m2"] for b in B if b["use"] == "housing") / m2_res
    res_land = sum(L["capacity"].get("homes", 0) for L in land) * home_m2 / m2_res
    keep_h = sum(L["capacity"].get("homes", 0) for L in keep)
    keep_j = sum(L["capacity"].get("jobs", 0) for L in keep)
    homes_new, jobs_new = homes_all - keep_h, jobs_all - keep_j
    res_new = res_new_b + res_land - keep_h * home_m2 / m2_res
    lotb = K.lot_by_id(ctx)
    res_exist = sum(b["gfa_m2"] for b in B if b["use"] == "existing" and (lotb.get(b.get("lot")) or {}).get("use") in U.RESIDENTIAL_USES) / m2_res

    # roads: km inside the area by class, new and existing (built by 2025 in the base scenario)
    km = {}
    for s in ctx.network["segments"]:
        ln = LineString([(p[0], p[1]) for p in s["pts"]]).intersection(area)
        k = (s["class"], "существующие" if s["years"][0] <= 2025 else "новые")
        km[k] = km.get(k, 0.0) + ln.length / 1000.0
    dv = ctx.driveways or {"segments": []}
    km_drive = sum(U.seg_line(s).length for s in dv["segments"]) / 1000.0

    # parks: greens of features.json by kind (ha)
    g_ha = {}
    for g in (ctx.features or {}).get("greens", []):
        g_ha[g["kind"]] = g_ha.get(g["kind"], 0.0) + K.geom(g).area / 1e4
    park_zone_ha = sum(z["area_ha"] for z in spec["zones"] if z["use"] == "park")

    # parking: places by type vs the norm need (homes × zone per_home; schools by parking.school_2000_places)
    pk = (ctx.features or {}).get("totals", {}).get("parking_cap", {})
    pk_total = sum(pk.values())
    zr = {z["id"]: z.get("rules") or {} for z in spec["zones"]}
    blk = {b["id"]: b for b in K.blocks(ctx)}
    need_h = 0.0
    for L in lots:
        z = (blk.get(L["block"]) or {}).get("zone")
        per = ((zr.get(z) or {}).get("parking") or {}).get("per_home") or 0
        need_h += math.ceil(sum(b["homes"] for b in B if b.get("lot") == L["id"] and b["source"] != "existing_osm") * per)
    N = K.norms(ctx)
    sp = N.v("parking.school_2000_places")
    sp = sp.get("spaces", sp) if isinstance(sp, dict) else sp
    typ = N.num("schools.typical_capacity")
    need_s = sum(sp * L["capacity"].get("places", 0) / typ for L in lots if L["use"] == "school")
    need_pk = need_h + need_s

    # service table (rule 14)
    spec_b = importlib.util.spec_from_file_location("qtwin_rules_buildings", os.path.join(MAP, "validate", "rules", "buildings.py"))
    mb = importlib.util.module_from_spec(spec_b)
    spec_b.loader.exec_module(mb)
    rows = mb.service_table(ctx, 2050)
    pc = mb.places_check(ctx, 2050) if hasattr(mb, "places_check") else None
    res_rows = [r for r in rows if not r["village"]]
    miss = [r for r in rows if any(not v["ok"] for v in r["services"].values())]
    worst = {}
    for sv in mb.SERVICES:
        cand = [(r["services"][sv]["dist_m"] if r["services"][sv]["dist_m"] is not None else 1e9, r) for r in rows]
        if cand:
            d_, r_ = max(cand, key=lambda t: t[0])
            worst[sv] = (r_["block"], r_["services"][sv]["dist_m"], r_["services"][sv]["norm_m"], r_["services"][sv]["ok"])
    # school and kindergarten places (lots), park ha, building counts (new, Overture-only existing kept, twin houses kept)
    sch_pl = sum(L["capacity"].get("places", 0) for L in lots if L["use"] == "school")
    kg_pl = sum(L["capacity"].get("places", 0) for L in lots if L["use"] == "kindergarten")
    kg_bi = sum(L["capacity"].get("kindergarten_builtin_places", 0) for L in lots)
    n_new = sum(1 for b in B if b["source"] != "existing_osm")
    n_ov = sum(1 for b in B if b["source"] == "existing_osm" and b.get("bid") is None)
    n_tw = sum(1 for b in B if b["source"] == "existing_osm" and b.get("bid") is not None)
    nres = res_new + res_exist + keep_h * home_m2 / m2_res

    L_ = []
    a = L_.append
    a("# Район Gate — числа картографа (w47, уровень 2)")
    a("")
    a(f"Спецификация `tools/map/spec/gate.json`, выход `OUT/gate/`, площадь {area.area / 1e4:.1f} га. Год 2050, базовый сценарий. "
      "Счёт как в валидаторе (правила 24 и 14). Цели — `targets` спецификации: " + T.get("source", ""))
    a("")
    a("## Числа района")
    a("")
    a("| Число | Карта | Цель | Расхождение |")
    a("| --- | --- | --- | --- |")
    a(f"| Жители нового города (без квартала Iconic и села) | {res_new:,.0f} | {T.get('population_2050', 0):,} | {pct(res_new, T.get('population_2050'))} |")
    a(f"| Квартиры нового города | {homes_new:,} | {T.get('homes_2050', 0):,} | {pct(homes_new, T.get('homes_2050'))} |")
    a(f"| Рабочие места нового города | {jobs_new:,} | {T.get('jobs_2050', 0):,} | {pct(jobs_new, T.get('jobs_2050'))} |")
    a(f"| Места парковки (подземные {pk.get('underground', 0):,}, многоуровневые {pk.get('multi', 0):,}, наземные {pk.get('surface', 0):,}) "
      f"| {pk_total:,} | {need_pk:,.0f} | {pct(pk_total, need_pk)} |")
    if pc:
        ns, nk = pc["school"]["norm"], pc["kindergarten"]["norm"]
        a(f"| Места в школах (норма {pc['school']['key']} на {pc['residents']:,} жителей, правило 14) | {sch_pl:,} | {ns:,} | {pct(sch_pl, ns)} |")
        a(f"| Места в детских садах, отдельные + встроенные (норма {pc['kindergarten']['key']}) | {kg_pl:,} + {kg_bi:,} | {nk:,} | "
          f"{pct(kg_pl + kg_bi, nk)} |")
    else:
        a(f"| Места в школах | {sch_pl:,} | — | по радиусам и норме мест (правило 14) |")
        a(f"| Места в детских садах (отдельные + встроенные) | {kg_pl:,} + {kg_bi:,} | — | по радиусам и норме мест |")
    a(f"| Км дорог в районе (без проездов) | {sum(km.values()):.2f} | — | цели нет |")
    a(f"| Проезды внутри кварталов, км | {km_drive:.2f} | — | цели нет |")
    a(f"| Парки и скверы (зелень park + square + boulevard), га | {sum(v for k, v in g_ha.items() if k in ('park', 'square', 'boulevard')):.1f} | — | "
      f"цели нет; зоны парков {park_zone_ha:.1f} га |")
    a("")
    a(f"Весь участок вместе с кварталом Iconic (keep): квартир {homes_all:,}, рабочих мест {jobs_all:,}, жителей "
      f"{res_new_b + res_land:,.0f}; плюс жители существующих домов села ≈ {res_exist:,.0f} (существующие дома: квартир "
      f"{homes_ex:,}, рабочих мест {jobs_ex:,} — в цели не входят). "
      "Парковка по норме: 1,0 места на квартиру (residential.parking_per_apartment, класс III, min), школы — "
      "parking.school_2000_places; офисы и торговля — 0, пока malls.parking_office / parking_mall not_verified (CONTRACT §8).")
    a("")
    PR = (T.get("plan_row") or {})
    a("Строка плана: 40 км², 223 тыс. жителей, рабочие места двойника 2050 г. 99 338.")
    a("")
    a("| Число | Район на карте | Строка плана | Расхождение |")
    a("| --- | --- | --- | --- |")
    a(f"| Площадь, км² | {area.area / 1e6:.2f} | 40 | {pct(area.area / 1e6, 40)} |")
    a(f"| Жители (новый город + квартал Iconic) | {res_new + keep_h * home_m2 / m2_res:,.0f} | {PR.get('population_2050', 223000):,} | "
      f"{pct(res_new + keep_h * home_m2 / m2_res, PR.get('population_2050', 223000))} |")
    a(f"| Жители с сёлами (сёла двойник не считает) | {nres:,.0f} | — | сёла ≈ {res_exist:,.0f} |")
    a(f"| Рабочие места (новый город + квартал Iconic) | {jobs_all:,} | {PR.get('jobs_2050', 99338):,} | {pct(jobs_all, PR.get('jobs_2050', 99338))} |")
    a("")
    a(f"Здания: новых {n_new:,}, существующих домов Overture (без номера двойника) {n_ov:,}, домов двойника {n_tw:,}.")
    a("")
    a("Км дорог по классам:")
    a("")
    a("| Класс | Новые | Существующие |")
    a("| --- | --- | --- |")
    for c in sorted({k[0] for k in km}, key=lambda c: -sum(v for k, v in km.items() if k[0] == c)):
        a(f"| {c} | {km.get((c, 'новые'), 0):.2f} | {km.get((c, 'существующие'), 0):.2f} |")
    a("")
    a("Зелень по видам, га: " + ", ".join(f"{k} {v:.1f}" for k, v in sorted(g_ha.items(), key=lambda t: -t[1])))
    a("")
    a("## Таблица обслуживания (жилые кварталы, 2050)")
    a("")
    a(f"Кварталов в таблице {len(rows)}, из них не выполняют хотя бы одну норму: {len(miss)}.")
    a("")
    a("Худший квартал по каждой службе: " + "; ".join(
        f"{SVC_RU[k]} — {v[0]} {'нет на сети' if v[1] is None else str(v[1]) + ' м'} / {v[2]:.0f}{'' if v[3] else ' ✗'}" for k, v in worst.items()))
    nmiss = {sv: sum(1 for r in rows if not r["services"][sv]["ok"]) for sv in mb.SERVICES}
    a("")
    a("Кварталов вне нормы по службам: " + ", ".join(f"{SVC_RU[k]} {v}" for k, v in nmiss.items()) +
      f"; из них сёл: {sum(1 for r in miss if r['village'])}.")
    a("")
    a("Худшее расстояние пешком по сети от дома квартала до ближайшего объекта, м / норма (✗ — дальше нормы). "
      "Квартал у границы area с ✗ — «ждёт соседа», если объект ближе у соседнего района.")
    a("")
    a("| Квартал | Дома | Жители | " + " | ".join(SVC_RU[s] for s in mb.SERVICES) + " |")
    a("| --- | --- | --- | " + " | ".join("---" for _ in mb.SERVICES) + " |")
    for r in rows:
        cells = []
        for s in mb.SERVICES:
            v = r["services"][s]
            d = "—" if v["dist_m"] is None else f"{v['dist_m']}"
            cells.append(f"{d}/{v['norm_m']:.0f}{'' if v['ok'] else ' ✗'}")
        a(f"| {r['block']}{' (село)' if r['village'] else ''} | {r['houses']} | {r['residents']} | " + " | ".join(cells) + " |")
    a("")
    a("## Перенесённые объекты: было → стало → почему")
    a("")
    a("| Объект | Было (x, z) | Стало (x, z) | Сдвиг, м | Почему |")
    a("| --- | --- | --- | --- | --- |")
    for o in spec["objects"]:
        if o["action"] == "move" and o.get("from") and o.get("to") and not o.get("parent"):
            dd = math.dist(o["from"], o["to"])
            a(f"| {o['registry_id']} ({o['name_ru']}) | {o['from'][0]:.1f}, {o['from'][1]:.1f} | {o['to'][0]:.1f}, {o['to'][1]:.1f}, yaw {o.get('yaw')} | {dd:.0f} | {o['why']} |")
    a("")
    a("## Изменения в пробной зоне (gate_trial.json остаётся фикстурой уровня 1)")
    a("")
    for c in spec.get("trial_changes") or []:
        a(f"- `{c['id']}`: {c['why']}")
    a("")
    a("## Изменения против схемы уровня 0")
    a("")
    for c in spec.get("scheme_changes") or []:
        a(f"- `{c['id']}`: {c['why']}")
    a("")
    a("## Объекты реестра: по источнику / по правилу")
    a("")
    a("| Объект | Действие | Как поставлен | Точность источника | Почему |")
    a("| --- | --- | --- | --- | --- |")
    for o in spec["objects"]:
        how = (o.get("basis") or ("по правилу" if o["action"] == "by_rule" else "по источнику")) + (f" («{o['chip']}»)" if o.get("chip") else "")
        a(f"| {o['registry_id']} | {o['action']} | {how} | {o.get('accuracy') or '—'} | {o['why']} |")
    a("")
    txt = "\n".join(L_) + "\n"
    od = os.path.join(out or C_OUT(), D)
    with open(os.path.join(od, "numbers.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    print(f"жители {res_new:.0f} / цель {T.get('population_2050')} ({pct(res_new, T.get('population_2050'))}); "
          f"квартиры {homes_new} / {T.get('homes_2050')} ({pct(homes_new, T.get('homes_2050'))}); "
          f"рабочие места {jobs_new} / {T.get('jobs_2050')} ({pct(jobs_new, T.get('jobs_2050'))}); "
          f"парковка {pk_total} / норма {need_pk:.0f} ({pct(pk_total, need_pk)}); дороги {sum(km.values()):.2f} км, "
          f"проезды {km_drive:.2f} км; парки и скверы {sum(v for k, v in g_ha.items() if k in ('park', 'square', 'boulevard')):.1f} га; "
          f"кварталов в таблице обслуживания {len(rows)}, не по норме {len(miss)}; школы {sch_pl}, сады {kg_pl}+{kg_bi}; "
          f"зданий новых {n_new}, Overture {n_ov}, двойника {n_tw}; худшие: {worst} → {os.path.join(od, 'numbers.md')}")


def C_OUT():
    from lib import paths
    return paths.OUT


if __name__ == "__main__":
    main(sys.argv[1:])
