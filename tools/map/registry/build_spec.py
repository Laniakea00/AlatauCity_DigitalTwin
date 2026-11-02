#!/usr/bin/env python3
"""Build tools/map/spec/norms.json and tools/map/spec/rules.json (level 0, w35).

norms.json  every number of the plan's norms table («Что достраиваем по нормам») and of
            research/norms.md that the generator or the validator uses, one entry per key, each
            with value, unit, applies_to, source (document, clause, year, url), status
            (norm / analogue / not_verified), basis and the validator severity; plus street
            profiles per road class and the node-type matrix (road class x road class).
rules.json  the 25 rules of «Чего быть не должно»: text_ru and check_ru are read verbatim from
            plan.md at build time; group, severity, when, checked_by, params (keys into
            norms.json, checked here) and how are curated below.

Run: python3 tools/map/registry/build_spec.py [--plan /mnt/project-files/alatau_stage7/plan/plan.md]
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------------------------
# sources: the labels of research/norms.md §7 (urls copied from there), plus the plan itself
# kind -> default (status, basis)
# ---------------------------------------------------------------------------------------------
KIND = {
    "kz_norm": ("norm", "kz_norm"),
    "kz_norm_predecessor": ("norm", "kz_norm_predecessor"),
    "kz_norm_cited": ("norm", "kz_norm_cited_by_project"),
    "kz_genplan": ("norm", "kz_genplan"),
    "plan_rule": ("norm", "plan_rule"),
    "kz_fact": ("norm", "kz_fact"),
    "kz_project_fact": ("analogue", "kz_project_fact"),
    "foreign_norm": ("analogue", "foreign_norm"),
    "international_guide": ("analogue", "international_guide"),
    "kz_news": ("not_verified", "kz_news"),
    "research_synthesis": ("analogue", "research_synthesis"),
}
C08 = "СНиП РК 3.01-01-2008 «Градостроительство. Планировка и застройка городских и сельских населённых пунктов» (прямой предшественник СП РК 3.01-101-2013, полный текст которого не получен)"
SRC = {}
for _n in range(1, 24):
    SRC["С08-%d" % _n] = (C08 + ", стр. %d веб-версии" % _n, 2008, "https://dnaop.com/html/32571_%d.html" % _n, "kz_norm_predecessor")
SRC.update({
    "СП303": ("СП РК 3.03-101-2013 «Автомобильные дороги» (извлечение ПАРАГРАФ до п. 6.2.5)", 2013, "https://kbexpert.kz/wp-content/uploads/2021/07/СП-РК-3.03-101-2013-Автомобильные-дороги.pdf", "kz_norm"),
    "Астана23": ("Рабочий проект ул. Казыбек би, Астана (цитирует СП РК 3.01-101-2013)", 2023, "https://www.gov.kz/uploads/2024/3/28/7efa5065a2aaae677d4c933adf370b94_original.1131080.pdf", "kz_norm_cited"),
    "Каражар": ("Проект улиц с. Каражар (табл. 5-3 СП РК 3.01-101-2013)", None, "https://ecoportal.kz/Public/PubHearings/LoadFile/158395", "kz_norm_cited"),
    "Атырау": ("Рабочий проект школы на 2000 мест, Атырау (цитирует СП РК 3.02-111-2012)", 2024, "https://ecoportal.kz/Disscusion/DisHearings/LoadFile/87503", "kz_project_fact"),
    "ГП727": ("Генеральный план г. Алатау, приложение 1 к ПП РК № 727 от 09.09.2025", 2025, "https://primeminister.kz/assets/media/prilozenie-1-rus-727.pdf", "kz_genplan"),
    "ГП388": ("Генеральный план г. Алатау, приложение 2 к ПП РК № 388 от 17.05.2024", 2024, "https://primeminister.kz/assets/media/pril-rus-2-388.pdf", "kz_genplan"),
    "ТР405": ("Техрегламент «Общие требования к пожарной безопасности», приказ МЧС РК № 405 от 17.08.2021 (с изм. 2024)", 2021, "https://zakon.uchet.kz/rus/docs/V2100024045", "kz_norm"),
    "ТР381": ("Изменения техрегламента «Общие требования к пожарной безопасности» (2024)", 2024, "https://zakon.uchet.kz/rus/docs/V2400035265", "kz_norm"),
    "СЗЗ": ("Санитарные правила по санитарно-защитным зонам, приказ ҚР ДСМ-2 от 11.01.2022", 2022, "https://zakon.uchet.kz/rus/docs/V2200026447", "kz_norm"),
    "ДСМ52": ("Санитарные правила к административным и жилым зданиям (2022)", 2022, "https://zakon.uchet.kz/rus/docs/V2200028525", "kz_norm"),
    "ДО": ("Санитарные правила к дошкольным организациям (рег. V1700015893)", 2017, "https://zakon.uchet.kz/rus/docs/V1700015893", "kz_norm"),
    "ОБР": ("Санитарные правила к объектам образования (рег. V2100023890)", 2021, "https://zakon.uchet.kz/rus/docs/V2100023890", "kz_norm"),
    "ВОЗ25": ("Правила установления водоохранных зон и полос, приказ МВРИ № 120-НҚ от 09.06.2025", 2025, "https://zakon.uchet.kz/rus/docs/V2500036238", "kz_norm"),
    "Парк25": ("Новость о нормах парковок 2025 (номер документа в статье не назван)", 2025, "https://digitalbusiness.kz/2025-11-24/teper-dazhe-zhk-ekonom-klassa-budut-s-parkovochnimi-mestami-v-kazahstane/", "kz_news"),
    "Tengri_Kap": ("Tengrinews, 16.07.2026 — уровни Капчагайского вдхр. (research/transport_site.md §7)", 2026, "https://tengrinews.kz/article/baklanyi-katamaranyi-milliardyi-kilovatt-energii-ustroena-4245/", "kz_fact"),
    "ДБН": ("ДБН В.2.3-5-2001 «Улицы и дороги населённых пунктов» (Украина)", 2001, "https://dnaop.com/html/34184_5.html", "foreign_norm"),
    "normacs-4818": ("Ответ эксперта по СП 42.13330 (РФ), normacs № 4818", None, "https://www.normacs.info/answers/4818", "foreign_norm"),
    "СП37": ("СП 37.13330 п. 10.3.12 (РФ), ответ эксперта normacs № 5057", None, "https://www.normacs.info/answers/5057", "foreign_norm"),
    "СП35": ("СП 35.13330.2011 «Мосты и трубы» (РФ)", 2011, "https://base.garant.ru/6180789/", "foreign_norm"),
    "СНиП-мосты-2": ("СНиП 2.05.03-84* «Мосты и трубы», стр. 2", 1984, "https://dnaop.com/html/54069_2.html", "foreign_norm"),
    "СНиП-мосты-4": ("СНиП 2.05.03-84* «Мосты и трубы», стр. 4", 1984, "https://dnaop.com/html/54069_4.html", "foreign_norm"),
    "EC": ("Structure gauge (Wikipedia): Eurocode 1 ≥ 5 м, Великобритания 5,03 м, США Interstate 4,9 м", None, "https://en.wikipedia.org/wiki/Structure_gauge", "foreign_norm"),
    "NCHRP": ("NCHRP Report 672 (кольцевые пересечения), курс PDH c711", None, "https://pdhonline.com/courses/c711/c711content.pdf", "foreign_norm"),
    "Maine": ("MaineDOT Roundabout Design", None, "https://www.maine.gov/dot/sites/maine.gov.dot/files/inline-files/DG%20-%20Roundabout%20Design.pdf", "foreign_norm"),
    "SCDOT": ("SCDOT Roadway Design Manual, гл. 10 Interchanges", None, "https://scdot.org/business/pdf/roadway/revisedChapters/Chapter%2010%20-%20Interchanges.pdf", "foreign_norm"),
    "WSDOT": ("WSDOT Design Manual M 22-01, гл. 1360 Interchanges", None, "https://wsdot.wa.gov/publications/manuals/fulltext/M22-01/1360.pdf", "foreign_norm"),
    "MoDOT": ("MoDOT Engineering Policy Guide 234.5 Cloverleaf Interchanges", None, "https://epg.modot.org/index.php/234.5_Cloverleaf_Interchanges", "foreign_norm"),
    "UNH": ("UN-Habitat «A New Strategy of Sustainable Neighbourhood Planning: Five principles»", None, "https://unhabitat.org/sites/default/files/download-manager-files/A%20New%20Strategy%20of%20Sustainable%20Neighbourhood%20Planning%20Five%20principles.pdf", "international_guide"),
    "ITDP": ("ITDP TOD Standard 3.0", None, "https://itdp-indonesia.org/wp-content/uploads/2019/10/TOD-Standard-3.0.pdf", "international_guide"),
    "GDCI-тротуар": ("Global Street Design Guide (GDCI): тротуары, геометрия", None, "https://globaldesigningcities.org/publication/global-street-design-guide/designing-streets-people/designing-for-pedestrians/sidewalks/geometry/", "international_guide"),
    "GDCI-совм.": ("Global Street Design Guide (GDCI): коммерческие совмещённые улицы, пример 14 м", None, "https://globaldesigningcities.org/publication/global-street-design-guide/streets/shared-streets/commercial-shared-streets/example-2-14-m/", "international_guide"),
    "Gehl": ("Цитаты Gehl / Alexander (Viewpoint Vancouver, 12.03.2013)", 2013, "https://viewpointvancouver.ca/2013/03/12/eight-qualities-of-pedestrian-and-transit-oriented-design/", "international_guide"),
    "Lite": ("Standards for Light Urban Rail Transit System (Metro Lite) in India, MoHUA", None, "https://mohua.gov.in/upload/uploadfiles/files/Standards_for_Light_Urban_Rail_Transit_System_(Metro%20Lite)_in_India.pdf", "foreign_norm"),
    "AstLRT": ("Astana Light Metro (Wikipedia)", None, "https://en.wikipedia.org/wiki/Astana_Light_Metro", "kz_project_fact"),
    "UTM": ("Urban Transport Magazine — LRT Astana starts revenue service", None, "https://www.urban-transport-magazine.com/en/light-rail-transit-system-astana-finally-starts-revenue-service/", "kz_project_fact"),
    "Нусантара": ("Nusantara (IKN), UNCRD 2025", 2025, "https://uncrd.un.org/sites/uncrd.un.org//files/2025sctw_s1-nusantara.pdf", "international_guide"),
    "ОЗЭС330": ("Правила установления охранных зон объектов электрических сетей и особых условий использования земельных участков, расположенных в границах таких зон, приказ Министра энергетики РК № 330 от 28.09.2017 (рег. МЮ № 15943)", 2017, "https://zakon.uchet.kz/rus/docs/V1700015943", "kz_norm"),
    "ДСМ133": ("Государственный норматив сети организаций здравоохранения, приказ и.о. Министра здравоохранения РК № ҚР ДСМ-133/2020 от 15.10.2020 (рег. МЮ № 21452, с изм. ҚР ДСМ-59 от 30.06.2022)", 2020, "https://zakon.uchet.kz/rus/docs/V2000021452", "kz_norm"),
    "ГГНС185": ("Гарантированный государственный норматив сети организаций образования, приказ Министра образования и науки РК № 185 от 06.05.2022 (рег. МЮ № 27968, ред. 30.04.2025)", 2022, "https://zakon.uchet.kz/rus/docs/V2200027968", "kz_norm"),
    "QTWIN": ("Модель qTwin: UnityProject/Tools/twin_gen/norms.py (константы панели двойника) и наименьшие строки таблиц норм; открытой нормы РК на это число нет", 2026, None, "plan_rule"),
    "R2": ("research/norms.md — синтез исследователя R2 по источникам строки (не норма)", 2026, None, "research_synthesis"),
    "PLAN": ("plan/plan.md — утверждённый план перерисовки карты (экспорт Claude Doc, Stage 7); «правило qTwin» в плане — правило проекта", 2026, None, "plan_rule"),
    "OWNER_3110": ("Решение владельца 31.10.2026 18:48Z (COMMON_RULES.md, Stage 7)", 2026, None, "plan_rule"),
    "TWIN": ("Код двойника: UnityProject/Assets/Scripts/DigitalTwin/TwinScenario.cs (enum Scenario)", 2026, None, "plan_rule"),
})

E = collections.OrderedDict()


def _src(label, clause):
    doc, year, url, kind = SRC[label]
    return {"label": label, "doc": doc, "clause": clause, "year": year, "url": url}


def N(key, name, value, unit, applies_to, src, clause=None, status=None, basis=None, note=None,
      sev=None, sev_why=None, also=(), plan=None, derived=False, conflict=None):
    """one norm entry; src is a label of SRC, also = [(label, clause), ...]"""
    if key in E:
        raise SystemExit("duplicate norm key " + key)
    st, bs = KIND[SRC[src][3]]
    status = status or st
    basis = basis or bs
    if derived:
        basis = basis + "+derived"
    if sev is None:
        sev = "error" if status == "norm" else "warning"
    e = collections.OrderedDict()
    e["group"] = key.split(".")[0]
    e["name_ru"] = name
    e["value"] = value
    e["unit"] = unit
    e["applies_to"] = applies_to
    e["source"] = _src(src, clause)
    if also:
        e["also"] = [_src(l, c) for l, c in also]
    e["status"] = status
    e["basis"] = basis
    e["severity"] = sev
    if sev_why:
        e["severity_why"] = sev_why
    if derived:
        e["derived"] = True
    if plan:
        e["plan_row"] = plan
    if conflict:
        e["conflict"] = conflict
    if note:
        e["note"] = note
    E[key] = e
    return e


MULTI, LOW = "многоэтажная застройка (город)", "малоэтажная застройка"
R = lambda a, b: {"min": a, "max": b}  # noqa: E731

# ============================ schools ==========================================================
N("schools.radius_m", "Школа от дома", 500, "м", "жилой дом → общеобразовательная школа, город", "С08-8", "табл. 10.1", plan="Школа от дома")
N("schools.junior_path_no_at_grade_arterial", "Путь младшего школьника", True, "bool", "путь младших школьников не пересекает магистральные улицы в одном уровне", "С08-8", "прим. к табл. 10.1", plan="Школа от дома")
N("schools.rural_access", "Школа в селе (справочно)", {"walk_primary_km": 2, "walk_basic_secondary_km": 4, "transport_primary_min": 15, "transport_secondary_min": 30, "bus_when_over_km": 1}, "км / мин", "село", "С08-8", "табл. 10.1", sev="info")
N("schools.places_per_1000_genplan", "Мест в школах на 1000 жителей (генплан, минимум)", 165, "мест / 1000 жит.", "Алатау, все районы; число генплана — минимум (правило 14)", "ГП727", None, derived=True,
  note="308,2 тыс. дополнительных мест к 2050 / 1 870 тыс. жителей ≈ 165 [выч. R2]", plan="Мест в школах")
N("schools.places_per_1000_snip_reference", "Мест в школах на 1000 жителей (СНиП, справочно)", 180, "мест / 1000 жит.", "новые города; справочно, генплан сильнее", "С08-21", "прил. 6 (рекомендуемое)", sev="info", plan="Мест в школах")
N("schools.additional_places_2050", "Дополнительные места в школах к 2050", 308200, "мест", "Алатау", "ГП727", plan="Мест в школах")
N("schools.typical_capacity", "Типовая школа генплана", 2000, "мест", "новые школы Алатау", "ГП727", plan="Типовая школа генплана")
N("schools.new_2030_by_district", "Новые школы по 2000 мест к 2030 по районам", {"Gate": 6, "Golden": 2, "Growing": 3, "Green": 4}, "школ", "I очередь (2030)", "ГП727", plan="Типовая школа генплана")
N("schools.plot_m2_per_pupil", "Участок школы на 1 учащегося", {"25-300": 72, "300-600": 55, "600-900": 39, "900-1200": 33}, "м² / учащегося", "по вместимости школы; участок включает спортзону и здание", "С08-21", "прил. 6")
N("schools.plot_2000_places_ha", "Участок школы на 2000 мест", 3.1988, "га", "школа > 1200 мест (в С08 нормы нет); типовая школа генплана", "Атырау", None,
  note="факт РК: ≈ 16 м²/уч. [выч.], застройка 5 604 м², 5 этажей, спортзона 3 700 м² (50 м²/класс × 74 класса); план: «участок ≈ 3,2 га»", plan="Типовая школа генплана")
N("schools.plot_adjust_pct", "Поправки к участку школы", {"reconstruction": -20, "village_without_experimental_plot": 30}, "%", "реконструкция / село; спортзону можно объединять со спорткомплексом микрорайона", "С08-21", "прил. 6")
N("schools.grounds_m2_per_class", "Площадки школы на класс", {"play_preparatory_and_1st": 100, "play_2_to_4": 50, "quiet_rest": 25, "sport_zone": 50}, "м² / класс", "СП РК 3.02-111-2012 в проекте школы РК", "Атырау", "СП РК 3.02-111-2012 (по проекту)", status="norm", basis="kz_norm_cited_by_project",
  note="текст СП РК 3.02-111-2012 не открывался; числа — из проекта, который его цитирует")
N("schools.building_from_red_line_m", "Здание школы от красной линии", {"city": 25, "village": 10}, "м", "здание школы", "С08-9", None, plan="Участок детсада")
N("schools.boarding_plot_m2_per_pupil", "Участок школы-интерната на 1 учащегося", {"200-300": 72, "300-500": 55, ">500": 40, "dormitory_block_extra_ha": 0.2}, "м² / учащегося", "школа-интернат", "С08-21", "прил. 6")
N("schools.class_area_m2_per_pupil", "Учебные площади", {"classroom": 2.5, "workshop": 3.75}, "м² / учащегося", "здание школы, колледжа", "ОБР")
N("schools.min_places_city", "Наименьшая школа в городе", 25, "мест", "новая школа в городе (правило 14)", "QTWIN", "нижняя строка schools.plot_m2_per_pupil (25–300 учащихся)",
  status="not_verified", note="модель qTwin: открытой нормы наименьшей школы в городе в РК нет (ГГНС № 185, п. 3: в городах — сохранение действующей сети); "
  "берётся нижняя граница таблицы участков школ С08 (25 учащихся), как gen_blocks_lots.cap_limits", also=[("С08-21", "прил. 6: 25–300 учащихся — 72 м²")])
N("schools.rural_min_pupils", "Школа в селе: наименьший контингент", {"primary": 5, "basic_secondary": 41, "general_secondary": 81}, "учащихся",
  "сельский населённый пункт; организации дальше 3 км друг от друга (п. 7)", "ГГНС185", "п. 2, подп. 2)–4)")
N("schools.building_m2_per_seat", "Площадь здания школы на место", 12, "м² общей площади / место", "здание школы (gen_buildings, правило 14)", "QTWIN",
  "M2_PER_SCHOOL_SEAT", status="not_verified", note="модель qTwin: число панели двойника (twin_gen/norms.py); СП РК на здания школ в открытом доступе нет")

# ============================ kindergartens ====================================================
N("kindergartens.radius_m", "Детсад от дома", {"multi_storey": 300, "low_rise_and_village": 500}, "м", MULTI + " / " + LOW + " и сёла", "С08-8", "табл. 10.1", plan="Детсад от дома")
N("kindergartens.places_per_1000_genplan", "Мест в садах на 1000 жителей (фиксируется на уровне 0)", 63.2, "мест / 1000 жит.", "Алатау 2050; минимум по генплану (правило 14)", "ГП727", None, derived=True,
  note="(11 908 + 28 060 + 78 300) / 1 870 тыс. жит. ≈ 63,2 [выч. w35]: план читает этапы как прибавку («11,9 тыс. новых мест к 2030, ещё 28,1 тыс. к 2040 и 78,3 тыс. к 2050»). Если 78,3 тыс. — итог к 2050 (как у школ 308,2 тыс.), то ≈ 41,9; берём большее. Существующие места в число не входят",
  plan="Мест в садах")
N("kindergartens.new_places_genplan", "Новые места в садах по генплану", {"by_2030": 11908, "2031_2040": 28060, "additional_by_2050": 78300, "of_2050_in_147_plots": 41200, "of_2050_built_in": 37100}, "мест", "Алатау", "ГП727", plan="Мест в садах")
N("kindergartens.places_per_1000_snip_reference", "Мест в садах на 1000 (СНиП, справочно)", {"new_cities_max": 180, "in_residential_zone_max": 100}, "мест / 1000 жит.", "новые города; справочно, генплан сильнее", "С08-21", "прил. 6 (рекомендуемое)", sev="info")
N("kindergartens.coverage_pct", "Охват детей дошкольными организациями", {"total": 85, "general": 70, "specialised": 3, "health": 12}, "%", "дети дошкольного возраста", "С08-21", "прил. 6", sev="info")
N("kindergartens.plot_m2_per_place", "Участок детсада на 1 место", {"<=100": 40, ">100": 35, ">500_complex": 30}, "м² / место", "по вместимости сада", "С08-21", "прил. 6", plan="Участок детсада")
N("kindergartens.plot_reduction_pct", "Сокращение участка детсада", {"reconstruction": -25, "slope_over_20pct": -15, "new_cities": -10}, "%", "реконструкция / уклон / новые города", "С08-21", "прил. 6")
N("kindergartens.playground_m2_per_child", "Игровая площадка детсада", 4, "м² / ребёнка", "отдельно для каждой группы; теневой навес ≥ 20 м²", "ДО", also=[("С08-21", "ясельная группа 7,5 м²/место")])
N("kindergartens.group_size_max", "Наполняемость групп", {"1-2_years": 10, "2-3_years": 20, "3-7_years": 25}, "детей", "группы детсада", "ДО")
N("kindergartens.building_from_red_line_m", "Здание детсада от красной линии", {"city": 25, "village": 10}, "м", "здание детсада", "С08-9", plan="Участок детсада")
N("kindergartens.placement", "Размещение детсада", "вдали от транспортных магистралей, вне СЗЗ; допускается во встроенных помещениях 1–2 этажей жилого дома", "текст", "детсад", "ДО")
N("kindergartens.built_in_playground", "Площадки встроенных групп детсада", {"max_from_entrance_m": 30, "min_from_windows_m": 12}, "м", "встроенный детсад", "С08-3")
N("kindergartens.min_places_city", "Наименьший детсад в городе", 25, "мест", "новый детсад в городе, отдельный или встроенный (правило 14)", "QTWIN",
  "одна полная группа 3–7 лет (kindergartens.group_size_max)", status="not_verified",
  note="модель qTwin: открытой нормы наименьшего сада в городе в РК нет (ГГНС № 185, п. 3: в городах — сохранение действующей сети); "
  "берётся одна полная группа 3–7 лет по санитарным правилам, как gen_blocks_lots.cap_limits", also=[("ДО", "группа 3–7 лет — до 25 детей")])
N("kindergartens.rural_min_children", "Дошкольная организация в селе: наименьший контингент", 5, "детей дошкольного возраста",
  "сельский населённый пункт; организации дальше 3 км друг от друга (п. 7)", "ГГНС185", "п. 2, подп. 1)")
N("kindergartens.building_m2_per_place", "Площадь здания детсада на место", 15, "м² общей площади / место", "здание детсада (gen_buildings, правило 14)", "QTWIN",
  "M2_PER_KG_PLACE", status="not_verified", note="модель qTwin: число панели двойника (twin_gen/norms.py); СП РК на здания дошкольных организаций в открытом доступе нет")

# ============================ clinics and hospitals ============================================
N("clinics.polyclinic_radius_m", "Поликлиника от дома", 1000, "м", "поликлиника и её филиалы, город", "С08-8", "табл. 10.1", plan="Поликлиника от дома")
N("clinics.polyclinics_2050", "Поликлиники по генплану", {"count": 68, "visits_per_shift": 34000}, "шт. / посещ. в смену", "Алатау 2050", "ГП727", plan="Больницы")
N("clinics.polyclinic_visits_per_1000", "Посещений поликлиник в смену на 1000", 18, "посещ. / смену / 1000 жит.", "Алатау 2050; в С08 нормы на 1000 нет", "ГП727", derived=True, note="34,0 тыс. / 1 870 тыс. ≈ 18 [выч. R2]")
N("clinics.polyclinic_plot", "Участок поликлиники", {"ha_per_100_visits": 0.1, "min_ha": 0.3}, "га", "поликлиника", "С08-21", "прил. 6")
N("clinics.phc_attached_population", "Организации ПМСП в городе по численности прикреплённого населения",
  {"medical_ambulatory": R(1500, 10000), "phc_centre": R(10000, 30000), "city_polyclinic_over": 30000}, "чел. прикреплённого населения",
  "врачебная амбулатория, центр ПМСП, городская поликлиника (не менее одной ГП в городе); наименьшая — врачебная амбулатория от 1 500 чел.",
  "ДСМ133", "гл. 2, п. 1), подп. 1)")
_phc = E["clinics.phc_attached_population"]["value"]["medical_ambulatory"]["min"] * E["clinics.polyclinic_visits_per_1000"]["value"] / 1000.0
N("clinics.phc_min_visits_per_shift", "Наименьшая организация ПМСП: посещений в смену", _phc, "посещ. / смену",
  "поликлиника меньше этого — не поликлиника правила 14 (врачебная амбулатория от наименьшего числа прикреплённых)", "ДСМ133", "гл. 2, п. 1), подп. 1)",
  derived=True, also=[("ГП727", "18 посещений в смену на 1000 жителей")],
  note=f"clinics.phc_attached_population medical_ambulatory min × clinics.polyclinic_visits_per_1000 / 1000 = {_phc:g} [выч. w43]")
N("clinics.hospital_beds_2050", "Койки по генплану", {"total_2050": 9350, "stage1": "2 × 500", "golden": "937 + 927"}, "коек", "Алатау", "ГП727", plan="Больницы")
N("clinics.hospital_beds_per_1000", "Коек на 1000 жителей", 5.0, "коек / 1000 жит.", "Алатау 2050; в С08 нормы нет", "ГП727", derived=True, note="9 350 / 1 870 тыс. ≈ 5,0 [выч. R2]", plan="Больницы")
N("clinics.hospital_plot_m2_per_bed", "Участок стационара на 1 койку", {"<=50": 300, "50-100": R(200, 300), "100-200": R(140, 200), "200-400": R(100, 140), "400-1000": R(60, 80), ">1000": 60, "children_factor": 1.5, "maternity_factor": 0.7},
  "м² / койку", "по вместимости стационара", "С08-21", "прил. 6", note="строка 400–1000 в источнике частично искажена")
N("clinics.ambulance_plot", "Станция скорой помощи", {"ha_per_vehicle": 0.05, "min_ha": 0.1}, "га", "станция скорой помощи", "С08-21", "прил. 6")
N("clinics.milk_kitchen_radius_m", "Раздаточный пункт молочной кухни", {"multi_storey": 500, "low_rise": 800}, "м", MULTI + " / " + LOW, "С08-8", "табл. 10.1")

# ============================ pharmacy and shops ===============================================
N("pharmacy_shops.pharmacy_radius_m", "Аптека от дома", {"multi_storey": 500, "low_rise": 800}, "м", MULTI + " / " + LOW, "С08-8", "табл. 10.1", plan="Аптека, магазины повседневного спроса")
N("pharmacy_shops.daily_shops_radius_m", "Магазины, общепит, быт повседневного спроса", {"multi_storey": 500, "low_rise": 800, "village": 2000}, "м", MULTI + " / " + LOW + " / село", "С08-8", "табл. 10.1", plan="Аптека, магазины повседневного спроса")
N("pharmacy_shops.post_bank_radius_m", "Отделение связи и банка", 500, "м", "город", "С08-8", "табл. 10.1")
N("pharmacy_shops.radius_adjust_pct", "Поправки к радиусам обслуживания", {"desert_semidesert_rough_relief": -30, "complex_layout_reconstruction": 10}, "%", "все радиусы табл. 10.1", "С08-8", "табл. 10.1")
N("pharmacy_shops.microdistrict_service_radius_m", "Радиус обслуживания микрорайона", 500, "м", "микрорайон", "С08-3")
N("pharmacy_shops.pharmacy_plot_ha", "Участок аптеки", R(0.2, 0.3), "га", "отдельно стоящая аптека", "С08-21", "прил. 6")
N("pharmacy_shops.retail_m2_per_1000", "Торговая площадь на 1000", {"total": 280, "food": 100, "non_food": 180}, "м² торговой площади / 1000 жит.", "город", "С08-21", "прил. 6")
N("pharmacy_shops.catering_seats_per_1000", "Общепит", 40, "мест / 1000 жит.", "город", "С08-21", "прил. 6")
N("pharmacy_shops.services_jobs_per_1000", "Бытовое обслуживание", 9, "раб. мест / 1000 жит.", "город", "С08-21", "прил. 6")

# ============================ sport and culture ================================================
N("sport_culture.sport_territory_ha_per_1000", "Территория спорта", R(0.7, 0.9), "га / 1000 жит.", "35 % — в жилых районах", "С08-21", "прил. 6")
N("sport_culture.gyms_m2_per_1000", "Спортзалы", R(60, 80), "м² пола / 1000 жит.", "50 % — в жилых районах", "С08-21", "прил. 6")
N("sport_culture.pools_m2_per_1000", "Бассейны", R(20, 25), "м² зеркала воды / 1000 жит.", "45 % — в жилых районах", "С08-21", "прил. 6")
N("sport_culture.fitness_rooms_m2_per_1000", "Помещения для физкультуры", R(70, 80), "м² / 1000 жит.", "жилая застройка", "С08-21", "прил. 6")
N("sport_culture.fitness_rooms_radius_m", "Помещения для физкультурно-оздоровительных занятий", 500, "м", "от дома", "С08-8", "табл. 10.1")
N("sport_culture.sport_centre_radius_m", "Физкультурно-спортивный центр жилого района", 1500, "м", "от дома", "С08-8", "табл. 10.1")
N("sport_culture.culture_seats_per_1000", "Клубы, кинотеатры, театры, танцзалы", {"clubs": 80, "cinemas": R(25, 35), "theatres": R(5, 8), "dance_halls": 6, "culture_rooms_m2": R(50, 60)}, "мест / 1000 жит. (помещения — м²)", "город", "С08-21", "прил. 6")
N("sport_culture.libraries_per_1000", "Библиотеки городские", {"reading_places": R(2, 3), "fund_units": R(4000, 4500)}, "мест / 1000 жит.", "город", "С08-21", "прил. 6")
N("sport_culture.hotels_places_per_1000", "Гостиницы", 6, "мест / 1000 жит.", "город", "С08-21", "прил. 6")
N("sport_culture.baths", "Бани", {"places_per_1000": 5, "plot_ha": R(0.2, 0.4)}, "мест / 1000 жит.; га", "город", "С08-21", "прил. 6")
N("sport_culture.elderly_homes_per_1000", "Дома престарелых и инвалидов", 28, "мест / 1000 жителей старше 60 лет и взрослых инвалидов", "город", "С08-21", "прил. 6")
N("sport_culture.cemeteries_ha_per_1000", "Кладбища", {"traditional": 0.24, "urn": 0.02}, "га / 1000 жит.", "город", "С08-21", "прил. 6")

# ============================ parks and squares ================================================
N("parks.square_or_playground", "Сквер или площадка у дома", {"min_area_m2": 300, "max_distance_m": 500}, "м² / м", "каждый жилой дом", "ITDP", None, also=[("С08-7", None)],
  plan="Сквер, площадка, парк", note="план ставит рядом СНиП РК 2008 и ITDP; число 300 м² / 500 м — из ITDP")
N("parks.district_park_access", "Парк планировочного района", {"walk_min": 15, "network_m": 1200}, "мин / м по сети", "каждый жилой дом", "С08-7", None, also=[("PLAN", "«Сквер, площадка, парк»: ≈ 1200 м по сети")],
  plan="Сквер, площадка, парк", note="минуты — С08; ≈ 1200 м по сети — пересчёт плана")
N("parks.city_park_access", "Городской парк", {"walk_min": 20, "network_m": 1600}, "мин / м по сети", "каждый жилой дом", "С08-7", None, derived=True,
  plan="Сквер, площадка, парк", note="1600 м = 20 мин × 80 м/мин — та же скорость, что в пересчёте плана 15 мин ≈ 1200 м [выч. w35]")
N("parks.min_area_ha", "Минимальная площадь парков", {"city_park": 15, "district_park": 10, "residential_garden": 3, "square": 0.5}, "га", "по уровню парка (сквер меньше 0,5 га — только при реконструкции)", "С08-7", None, plan="Зелень")
N("parks.green_share_in_parks_min_pct", "Зелень в парках и садах", 70, "% площади", "парки и сады", "С08-7")
N("parks.large_parks", "Крупные парки и лесопарки", {"min_width_km": 0.5, "min_share_of_public_green_pct": 10}, "км / %", "город", "С08-7")
N("parks.children_parks_m2_per_person", "Детские парки", 0.5, "м² / чел.", "город", "С08-7")
N("parks.boulevard_min_width_m", "Бульвар", {"on_street_axis": 18, "one_side_between_carriageway_and_buildings": 10}, "м", "бульвар с одной продольной аллеей", "С08-7", plan="Улицы в красных линиях")
N("parks.path_width_multiple_m", "Ширина дорожек в парках", 0.75, "м (кратность)", "дорожки парков", "С08-7")
N("parks.visitors_per_ha_max", "Посетителей на 1 га (макс.)", {"city_park": 100, "recreation_zone_park": 70, "resort_park": 50, "forest_park": 10, "city_forest": R(1, 3)}, "чел. / га", "парки", "С08-7")
N("parks.mass_recreation_zone", "Зона массового кратковременного отдыха", {"m2_per_visitor": 500, "active_m2_per_visitor": 100, "min_ha": 50, "min_ha_desert": 30, "max_transport_h": 1.5}, "м² / га / ч", "зоны отдыха", "С08-7")
N("parks.beach", "Пляжи", {"m2_per_visitor_river_lake": 8, "m2_per_visitor_sea": 5, "m2_per_visitor_children": 4, "shoreline_m_per_visitor": 0.25}, "м² / м", "пляжи у реки, озера (Капчагай)", "С08-8")
N("parks.square_size_gehl_max_m2", "Размер площади (ориентир)", 10000, "м²", "центральные площади; почти все известные площади Европы < 10 000 м², большинство < 8 000 м²", "Gehl")

# ============================ greenery =========================================================
N("greenery.city_share_min_pct", "Доля зелени в городе", {"city": 40, "residential_district": 25, "extra_if_szz_wider_1km": 15}, "%", "застройка города / жилой район", "С08-7", plan="Зелень")
N("greenery.quarter_share_min_pct", "Озеленение квартала", {"normal": 25, "arid": 20, "paths_count_if_share_max": 30, "reduction_next_to_city_green": -25}, "% площади квартала", "квартал / микрорайон", "С08-5", "п. 7.5", plan="Зелень")
N("greenery.public_green_m2_per_person", "Озеленённые территории общего пользования", {"city_wide": 10, "residential_districts": 6}, "м² / чел.", "крупнейшие, крупные, большие города", "С08-7", "табл. 9.1", plan="Зелень")
N("greenery.table_9_1_adjust_pct", "Поправки к табл. 9.1", {"resort_cities_up_to": 50, "desert_semidesert": R(-30, -20), "steppe_forest_steppe": R(10, 20)}, "%", "по климату и назначению", "С08-7", "табл. 9.1")
N("greenery.genplan_frame", "Зелёный каркас генплана", "лесопарковая зона западнее трассы республиканского значения против песков Мойынкум; зелёные пешеходные связи рек Каскелен и Малая Алматинка; центр Golden 400+ га; общего гектарного итога зелени в ГП нет", "текст", "Алатау", "ГП727")

# ============================ stops and transit ================================================
N("stops.walk_max_m", "Остановка общественного транспорта", {"default": 500, "climate_subdistrict_IV": 400, "low_rise": R(600, 800), "minus_m_per_10m_elevation": 50}, "м", "от дома пешком", "С08-11", "п. 11.18", plan="Остановка общественного транспорта")
N("stops.near_destinations_max_m", "Остановка у центров / промзон / зон отдыха", {"centres": 250, "industrial_zones": 400, "recreation_zones": 800}, "м", "от входа", "С08-11", plan="Остановка общественного транспорта")
N("stops.spacing_m", "Расстояние между остановками", {"bus_trolley_tram": R(400, 600), "express_bus_rapid_tram": R(800, 1200), "metro": R(1000, 2000), "suburban_rail": R(1500, 2000)}, "м", "по виду транспорта", "С08-11", "п. 11.19")
N("stops.network_density_km_per_km2", "Плотность сети наземного транспорта", {"built_up": R(1.5, 2.5), "centres_max": 4.5}, "км / км²", "застроенная территория", "С08-11")
N("stops.transfer_walk_max_min", "Пересадка", 3, "мин пешком", "без ожидания", "С08-11")
N("stops.vehicle_load_persons_per_m2", "Расчёт вместимости", {"normal": 4, "rapid": 3}, "чел. / м²", "подвижной состав", "С08-11", sev="info")
N("stops.itdp_rapid_transit_m", "До скоростного транспорта (TOD)", {"optimal": 500, "max": 1000}, "м", "жильё и работа", "ITDP")
N("stops.genplan_surface_transit", "Наземный транспорт генплана", {"routes_km": 914, "speed_kmh": R(18, 25), "river_tram_stations": 8, "river_tram_km": 37}, "км / км/ч / шт.", "Алатау", "ГП727")
N("stops.agglomeration_rail", "Агломерационная ж/д", {"length_km": 53.5, "mean_station_spacing_km": 6.3, "speed_kmh": R(60, 70), "regional_rail_km": 126.6}, "км / км/ч", "Алматы – Конаев – Алатау, аэропорт", "ГП727")

# ============================ fire depots ======================================================
N("fire.depot_radius_km", "Пожарное депо: радиус выезда", 3, "км", "каждый дом", "С08-19", plan="Пожарное депо")
N("fire.arrival_min", "Прибытие первого подразделения", {"city": 10, "village": 20}, "мин", "город / село", "ТР405", plan="Пожарное депо")
N("fire.industrial_depot_radius_km", "Радиус депо для предприятий А, Б, В", {"over_50pct_area": 2, "up_to_50pct_and_G_D": 4, "reduction_if_over_50pct_III_V_pct": -40}, "км / %", "промышленные предприятия", "ТР381")

# ============================ universities and colleges =======================================
N("universities.golden_cluster_students", "Кластер вузов Golden", 40000, "студентов", "Golden", "ГП388", also=[("ГП727", None)], plan="Вузы и колледжи")
N("universities.qaist", "QAIST", {"students": 5000, "plot_max_ha": 120}, "студентов / га", "Golden, в составе кластера 40 тыс.", "PLAN", "«Вузы и колледжи»", plan="Вузы и колледжи", note="5 тыс. — реестр (S74); участок до 120 га — план")
N("universities.growing_tech_institute_students", "Технический институт Growing", R(10000, 15000), "студентов", "Growing", "ГП727", also=[("ГП388", None)], plan="Вузы и колледжи")
N("universities.study_zone_ha_per_1000", "Учебная зона вуза", {"university_technical": R(4, 7), "agricultural": R(5, 7), "medical": R(3, 5), "economic_pedagogical_culture_arts_architecture": R(2, 4)}, "га / 1000 студентов", "вуз", "С08-21", "прил. 6", plan="Вузы и колледжи")
N("universities.extra_zones_ha_per_1000", "Спортзона и общежития вуза", {"sport_zone": R(1, 2), "dormitories": R(1.5, 3), "reconstruction_pct": -40, "cooperation_pct": -20}, "га / 1000 студентов", "вуз", "С08-21", "прил. 6")
N("universities.dormitory_m2_per_person", "Общежитие колледжа / вуза", 6, "м² / чел.", "общежитие", "ОБР")
N("universities.college_plot_m2_per_student", "Участок колледжа на 1 учащегося", {"<=300": 75, "300-900": R(50, 65), "900-1600": R(30, 40)}, "м² / учащегося", "колледжи (ПТУ, ссузы)", "С08-21", "прил. 6", plan="Вузы и колледжи")
N("universities.science_plot", "Научные учреждения", {"natural_technical_ha_per_1000m2": R(0.12, 0.17), "social_ha_per_1000m2": R(0.08, 0.1), "building_max_pct": 50, "green_sport_min_pct": 10}, "га на 1000 м² площади / %", "НИИ, лаборатории", "С08-5", also=[("С08-6", None)])

# ============================ malls and business centres ======================================
N("malls.location", "Где стоят ТРЦ, супермаркеты, офисы", "в общественных центрах жилых районов (доступность ≤ 15 мин) и у станций ЛРТ", "текст", "ТРЦ, супермаркеты, офисы", "PLAN", "«Центры и торговля»", also=[("С08-4", None)], plan="Центры и торговля")
N("malls.public_centre_access_min", "Общественный центр жилого района", 15, "мин", "от дома", "С08-4", plan="Центры и торговля")
N("malls.max_distance_to_lrt_station_m", "ТРЦ от станции ЛРТ", 250, "м", "ТРЦ", "PLAN", "«Центры и торговля» (правило qTwin)", plan="Центры и торговля")
N("malls.gate_floor_area_m2", "Офисы, отели, торговля Gate", 3700000, "м² (более)", "Gate", "ГП727", also=[("ГП388", None)])
N("malls.housing_share_in_public_nodes_pct", "Жильё в общественных узлах", R(20, 50), "% общей застройки узла", "общественные узлы", "С08-4")
N("malls.jobs_in_residential_district_pct", "Места приложения труда в жилом районе", 40, "% трудоспособных (до)", "жилой район", "С08-4")
N("malls.facade", "Активный фасад (TOD)", {"entries_per_100m_min": 3, "entries_per_100m_best": 5, "active_frontage_min_pct": 20, "active_frontage_best_pct": 90, "shade_min_pct_sidewalks": 75}, "входов / %", "улицы центров", "ITDP")
N("malls.parking_office", "Парковка офисов и бизнес-центров", {"as_printed": "9–17", "gov_republican": "4–8", "gov_local": "11–17"}, "единица в извлечении неоднозначна", "офисы, госучреждения", "С08-22", "прил. 8 (рекомендуемое)", status="not_verified",
  note="[НЕ ПРОВЕРЕНО — перепроверить по тексту СП РК, прил. Е]; план: «нормы парковки для офисов и ТРЦ» — по аналогу; аналога с числом в research нет", plan="Не проверено: нормы парковки для офисов и ТРЦ")
N("malls.parking_mall", "Парковка ТРЦ и супермаркетов", {"staff": "110–130", "visitors": "32–35", "supermarket_over_2000m2": "18–22", "markets_universal": "40–45", "markets_food": "50–60"}, "единица в извлечении неясна", "ТРЦ, супермаркеты, рынки", "С08-22", "прил. 8 (рекомендуемое)", status="not_verified",
  note="[НЕ ПРОВЕРЕНО]; аналога с числом в research нет", plan="Не проверено: нормы парковки для офисов и ТРЦ")

# ============================ residential complexes ============================================
N("residential.courtyard_group_max_ha", "Группа домов с общим двором (ЖК)", 10, "га (как правило, до)", "ЖК", "С08-3", plan="ЖК")
N("residential.playgrounds_share_min_pct", "Площадки во дворе", 10, "% площади квартала", "игры, отдых, спорт суммарно (сокращение до 50 % — в оговорённых случаях)", "С08-5", "п. 7.6", plan="ЖК")
N("residential.yard_distances_from_windows_m", "Площадки от окон жилых домов", {"children_play": 12, "adult_rest": 10, "sport": R(10, 40), "household": 20, "dog_walking": 40}, "м", "двор", "С08-5")
N("residential.waste_bins", "Мусоросборники", {"min_from_playgrounds_and_kindergartens_m": 20, "max_from_farthest_entrance_with_chute_m": 100, "max_without_chute_m": 50}, "м", "двор", "С08-5")
N("residential.extended_day_playground", "Площадки групп продлённого дня (1–4 кл.)", {"plot_min_m2": 150, "per_class_min_m2": 100, "max_from_walls_m": 50, "min_from_windows_m": 12}, "м² / м", "встроенные группы", "С08-3")
N("residential.non_residential_in_quarter", "Нежилые объекты в квартале", {"unrelated_plot_max_ha": 0.5, "non_residential_fund_max_pct": 25, "territory_max_pct": 12}, "га / %", "микрорайон", "С08-3")
N("residential.non_residential_in_district", "Нежилые объекты в жилом районе", {"object_max_ha": 2, "fund_max_pct": 30, "territory_max_pct": 15}, "га / %", "жилой район (с обоснованием)", "С08-3")
N("residential.housing_m2_per_person", "Жилищная обеспеченность", {"target_2050": 30.0, "now": 17.2, "fund_2050_mln_m2": 55.8}, "м² общей площади / чел.", "Алатау", "ГП727")
N("residential.parking_per_apartment", "Машино-мест на квартиру (по классу жилья)", {"I": "по заданию (многоэтажное); 2,0–2,25 (малоэтажное 2–3+ комн.)", "II": R(1.25, 1.75), "III": R(1.0, 1.5), "IV": R(0.5, 1.25)}, "мест / квартиру", "ЖК", "С08-11", "табл. 11.7", plan="ЖК")
N("residential.parking_2025_change", "Изменение норм парковок 2025", {"economy_IV": "«минимальные» (число не названо)", "comfort": "≥ 1 на комплекс", "business": "1 на квартиру", "elite_I": "≥ 2 на квартиру"}, "мест", "ЖК", "Парк25", note="номер документа в статье не назван")

# ============================ quarters, density, coefficients =================================
N("quarters.microdistrict_ha", "Микрорайон (квартал по С08)", R(10, 100), "га", "ограничен магистралями", "С08-3", plan="Квартал")
N("quarters.residential_district_ha", "Жилой район", R(100, 300), "га", "жилой район", "С08-3")
N("quarters.block_side_m", "Сторона квартала (центр)", R(110, 150), "м", "центры районов; лучшие кварталы ≈ 1 га со сторонами ≈ 100 м", "ITDP", plan="Квартал")
N("quarters.arterial_step_m", "Шаг магистралей", R(800, 1000), "м", "сетка магистралей", "UNH", plan="Квартал")
N("quarters.unh_street_model", "Модель сетки UN-Habitat", {"street_step_m": 111, "street_km_per_km2_min": 18, "street_share_min_pct": 30, "service_walk_m": R(400, 450)}, "м / км/км² / %", "кварталы", "UNH")
N("quarters.entry_spacing_max_m", "Въезды в квартал с районных улиц", 200, "м (не реже чем через)", "квартал", "С08-5")
N("quarters.r2_grid_synthesis", "Синтез сетки для генератора (не норма)", {"arterials_m": R(800, 1000), "microdistrict_ha": R(64, 100), "local_streets_m": R(100, 150), "block_ha": R(1, 2), "entries_max_m": 200}, "м / га", "генератор кварталов", "R2", derived=True)
N("quarters.residential_zone_ha_per_1000", "Укрупнённая площадь жилой зоны", {"9_plus_floors": R(7, 8), "4_8_floors": R(8, 9), "up_to_3_no_plots": R(10, 11), "up_to_3_with_plots": R(20, 22), "estate": R(35, 40)}, "га / 1000 жит.", "при 20 м² жилой площади / чел.", "С08-3")
N("quarters.density_persons_per_ha", "Плотность населения жилой зоны (обратный пересчёт)", {"9_plus_floors": R(125, 143), "4_8_floors": R(111, 125), "up_to_3": R(91, 100)}, "чел. / га", "табл. расчётной плотности в С08 не найдена", "С08-3", derived=True, sev="info")
N("quarters.floor_zone_types", "Типы жилых зон по этажности", {"over_12": "высотная", "6_12": "многоэтажная", "4_5_6": "среднеэтажная", "1_3": "малоэтажная блокированная / усадебная"}, "этажей", "жилые зоны", "С08-2")
N("quarters.kz_kpz_residential", "КЗ / КПЗ жилых кварталов (брутто)", {"multi_storey_along_arterials": {"kz": 0.7, "kpz": R(2.0, 2.5)}, "inter_arterial_up_to_100ha": {"kz": 0.6, "kpz": R(1.5, 2.0)}, "inter_arterial_over_100ha": {"kz": 0.4, "kpz": 1.2},
  "reconstruction": {"kz": 0.6, "kpz": 1.6}, "low_mid_rise": {"kz": 0.4, "kpz": 0.8}, "blocked_with_plots": {"kz": 0.3, "kpz": 0.6}, "estate": {"kz": 0.2, "kpz": 0.4}}, "доля / коэффициент", "квартал; для элитного жилья на главных улицах КПЗ > 2,5 допускается", "С08-20")
N("quarters.kz_kpz_other_zones", "КЗ / КПЗ общественно-деловых и производственных зон", {"multifunctional": {"kz": 1.0, "kpz": 3.0}, "specialised": {"kz": 0.8, "kpz": 2.4}, "industrial": {"kz": 0.8, "kpz": 2.4}, "science_production": {"kz": 0.6, "kpz": 1.0}, "communal_storage": {"kz": 0.6, "kpz": 1.8}}, "доля / коэффициент", "квартал", "С08-20")
N("quarters.underground_share_max_pct", "Подземное строительство", {"centre_and_nodes": 30, "middle": 20, "periphery": 10}, "% наземной площади (до)", "крупнейшие города", "С08-2", sev="info")
N("quarters.unh_density", "Ориентир плотности UN-Habitat", {"persons_per_km2_min": 15000, "non_residential_floor_min_pct": 40, "affordable_pct": R(20, 50), "monofunctional_blocks_max_pct": 10}, "чел./км² / %", "районы", "UNH", sev="info")
N("quarters.genplan_population_2050", "Население 2050 по районам", {"Gate": 223000, "Golden": 675000, "Growing": 650000, "Green": 320000, "total": 1870000}, "чел.", "Алатау; Growing и Green — «≈»", "ГП727", note="правило 24: числа района против цели — допуск ±5 %")
N("quarters.genplan_jobs_2050", "Рабочие места 2050 по районам", {"Gate": 181500, "Golden": 337400, "Growing": 309200, "Green": 173500}, "мест", "Алатау", "ГП727")
N("quarters.genplan_territory_ha", "Территория города", {"total": 88000, "built_up": 36246}, "га", "Алатау", "ГП727")

# ============================ heights near airfields ==========================================
N("heights.core_along_a3", "Этажность по генплану", "центральное ядро — коридор А-3; этажность снижается от центра к периферии", "текст", "Алатау", "ГП727", plan="Этажность")
N("heights.gate_owner_rule", "Этажность Gate", "плотный центр вдоль осей и ЛРТ вокруг Iconic, внутри средняя этажность; Iconic стоит в центре Gate", "текст", "Gate", "OWNER_3110")
N("heights.airfield_approval_radius_km", "Радиус согласования высоких зданий от КТА", 30, "км", "КТА аэродрома Жетыген и будущего аэропорта «Алатау»", "С08-6", "п. 8.30", plan="Этажность")
N("heights.airfield_height_threshold_m", "Высота, с которой нужно согласование", 50, "м", "объекты ≥ 50 м над уровнем аэродрома в 30 км и любые объекты высотой ≥ 50 м", "С08-6", "п. 8.30", plan="Этажность")
N("heights.airfield_all_objects_radius_km", "Согласование всех объектов", 10, "км от КТА", "и в полосах воздушных подходов", "С08-6", "п. 8.30")
N("heights.airfield_food_waste_min_km", "Свалки пищевых отходов, бойни от КТА", 15, "км (не ближе)", "аэродром", "С08-6", "п. 8.30")
N("heights.airfield_points", "Контрольные точки для правила 16", {"zhetygen_airfield": "registry.json: airfield_zhetygen (points.control_point)", "alatau_airport": "registry.json: airport_alatau (центр ВПП по решению владельца 31.10.2026: −16000, 1500)"}, "ссылка", "правило 16", "PLAN", "правило 16")
N("heights.high_rise_floors", "Высотная застройка", 12, "этажей (более)", "отдельный тип жилой зоны", "С08-2")
N("heights.tod_max_density_m", "Максимальная плотность у станций", 500, "м от станции скоростного транспорта", "TOD", "ITDP")

# ============================ setbacks, gaps, insolation ======================================
N("setbacks.red_line_m", "Отступ зданий от красной линии", {"arterial_streets": 6, "residential_streets": 3}, "м (не меньше)", "жилые и общественные здания", "С08-4", plan="Отступы и линия застройки")
N("setbacks.housing_from_arterial_carriageway_m", "Жильё от проезжей части магистралей", {"default": 50, "with_noise_protection": 25}, "м", "магистральные дороги (А-3, БАКАД, IA)", "С08-9", plan="Отступы и линия застройки")
N("setbacks.building_line_max_m", "Линия застройки на районных и местных улицах", {"max_from_carriageway": 25, "else_fire_access_width": 6, "fire_access_min_from_building_line": 5}, "м", "районные и местные улицы", "С08-5", also=[("С08-9", None)], plan="Отступы и линия застройки")
N("building_gaps.long_sides_m", "Разрыв между длинными сторонами жилых домов", {"2_3_floors": 15, "4_floors": 20, "5_plus": "по инсоляции и освещённости"}, "м", "жилые дома", "С08-4", "п. 7.2", plan="Разрыв между домами")
N("building_gaps.long_side_to_end_with_windows_m", "Длинная сторона против торца с окнами", 10, "м", "жилые дома", "С08-4")
N("building_gaps.estate_m", "Усадебная застройка", {"windows_to_neighbour": 6, "house_to_plot_boundary": 3, "outbuilding_to_boundary": 1}, "м", "усадьбы", "С08-4")
N("building_gaps.fire_between_buildings_m", "Противопожарные разрывы (табл. 16.1)", {"I-II_to_I-II": 6, "I-II_to_III": 8, "III_to_III": 8, "with_IIIa-V": 10, "IIIa-V_to_IIIa-V": 15, "blank_walls_pct": -20, "seismic_9_pct": 20}, "м / %", "жилые и общественные здания", "С08-18", "табл. 16.1",
  also=[("ТР405", "I–II при противопожарной стене 1-го типа не нормируются; IV–V ≥ 18 м до Ф5, III–IIIб ≥ 12 м")])
N("building_gaps.residential_to_industrial_m", "Жилые/общественные до производственных и гаражей I–II", {"default": 9, "combustible_insulation": 15}, "м", "производственные здания", "С08-18")
N("building_gaps.monuments_from_expressways_m", "Памятники до скоростных магистралей", {"rough_relief": 100, "flat": 50}, "м", "памятники истории и культуры", "С08-18")
N("insolation.dwellings_h", "Инсоляция жилых помещений", {"hours": 2, "period": "22.02–22.10", "zone": "южная (южнее 48° с.ш.; Алатау ≈ 44°)", "nine_plus_floors_break": "один перерыв, если один период ≥ 1 ч, сумма +0,5 ч"}, "ч / сут", "жилые помещения", "ДСМ52", plan="Разрыв между домами")
N("insolation.children_h", "Инсоляция детских учреждений и площадок", {"hours": 3, "school_sport_zone_half_h": 2.5}, "ч / сут", "групповые детсадов, спальни интернатов, детские площадки, спортзоны школ", "ДСМ52", plan="Разрыв между домами")
N("insolation.classrooms_h", "Инсоляция школьных классов", 1.5, "ч (для 60 % классов, юг)", "средние и старшие классы", "ДСМ52")
N("insolation.rooms", "Какие комнаты инсолируются", {"apartments_1_3_rooms": 1, "apartments_4_plus": 2, "dormitory_rooms_pct": 60}, "комнат / %", "квартиры", "ДСМ52")

# ============================ sanitary zones ==================================================
N("szz.class_width_m", "СЗЗ по классам опасности", {"I": {"min": 1000}, "II": R(500, 999), "III": R(300, 499), "IV": R(100, 299), "V": R(50, 99)}, "м", "предприятия; в СЗЗ — никакого жилья, школ, детских площадок", "СЗЗ", plan="Санитарные зоны заводов")
N("szz.class_examples", "Примеры классов", {"I": "цемент, мясокомбинаты/бойни, нефтепереработка", "II": "мельницы > 2 т/ч, известь", "III": "элеваторы, кофеобжарка, ЖБИ", "IV": "пивоварни, безалкогольные напитки, мыло", "V": "готовые лекарственные формы, механообработка пластмасс"}, "текст", "классификация", "СЗЗ", sev="info")
N("szz.forbidden_inside", "В СЗЗ запрещено", ["жильё", "зоны отдыха", "сады и дачи", "спортсооружения", "детские площадки", "образовательные и детские организации", "резерв жилой застройки"], "список", "СЗЗ", "СЗЗ", plan="Санитарные зоны заводов")
N("szz.allowed_inside", "В СЗЗ допускается", ["здания обслуживания самого предприятия (административные, КБ, учебные)", "сети", "подстанции"], "список", "СЗЗ", "СЗЗ")
N("szz.green_share_min_pct", "Озеленение СЗЗ", {"width_up_to_300": 60, "300_1000": 50, "1000_3000": 40, "over_3000": 20, "tree_belt_housing_side_m": 50, "tree_belt_if_szz_up_to_100_m": 20}, "% / м", "СЗЗ", "С08-7")
N("szz.wind_sector_deg", "Подветренный сектор (пока нет розы ветров в цифрах)", {"default_sector": [200, 295], "green_warning_sector": [290, 20], "zone_factor": 2}, "градусы азимута от завода / множитель СЗЗ", "жильё, школы, сады в пределах двойной СЗЗ", "PLAN", "правило 15",
  note="Green: сектор 290°–20° даёт предупреждение (юго-восточные и южные ветры)")
N("szz.rail_m", "Железная дорога", {"housing_from_outer_track_axis": 100, "housing_with_cut_or_noise_protection": 50, "gardens": 50, "sorting_station_outside_city_min": 150}, "м", "ж/д", "С08-7", also=[("С08-6", None)])
N("szz.roads_I_III_m", "Автодороги общей сети", {"I_III_housing_from_subgrade_edge": 100, "I_III_gardens": 50, "IV_housing": 50, "IV_gardens": 25, "green_strip_housing_side_min": 10}, "м", "дороги общей сети (А-3, БАКАД вне города)", "С08-6")
N("szz.ports_m", "Порты", {"housing": 100, "flammable_liquid_stores_downstream": 500, "dusty_cargo": 300}, "м", "порты, причалы", "С08-6")
N("szz.landfill_m", "Полигон ТБО", 1000, "м", "Алатау", "ГП727")
N("szz.production_in_mixed_zone", "Производственные участки в смешанной / общественной зоне", {"boundary_from_housing_schools_m": 50, "szz_max_m": 50, "plot_max_ha": 5, "trucks_per_day_one_way_max": 50}, "м / га / шт.", "смешанная зона", "С08-4")
N("szz.petrol_station_m", "АЗС с подземными резервуарами", {"to_schools_kindergartens_hospitals_housing": 50, "cars_only_up_to_500_per_day": 25, "between_stations": 100}, "м", "АЗС", "С08-12", "п. 11.33")
N("szz.forest_edge_m", "Лесной массив", {"city_buildings": 50, "estate_1_2_floors": 15}, "м", "граница застройки", "С08-19")
N("szz.zoo_m", "Зоопарк", 50, "м", "до жилой и общественной застройки", "С08-7")
N("szz.resorts", "Зоны отдыха / курорты", {"recreation_from_sanatoria_camps_roads_rail_m": 500, "holiday_homes_m": 300, "new_resort_from_housing_m": 500, "reconstruction_m": 100, "from_roads_I_III_m": 500, "from_roads_IV_m": 200, "from_dachas_m": 300, "children_belt_m": 100}, "м", "Green: курорт у Капчагая", "С08-8")
N("szz.non_polluting_in_residential_m", "Объекты без загрязнения в жилой зоне", 25, "м", "санитарный разрыв", "С08-2")
N("szz.cemetery_to_school_hospital_m", "Кладбище у школы / больницы", 300, "м", "кладбища", "С08-9", "табл. 10.3", status="not_verified", note="выравнивание столбцов в источнике под вопросом")

# ============================ parking =========================================================
N("parking.cars_per_1000", "Уровень автомобилизации", {"default": R(250, 300), "low_rise": 400, "trucks": R(35, 55)}, "машин / 1000 жит.", "расчётный", "С08-9", plan="Парковки")
N("parking.permanent_storage", "Постоянное хранение у жилья", {"share_min_pct": 90, "walk_max_m": 800, "walk_max_reconstruction_m": 1500}, "% / м", "жильё", "С08-11", plan="Парковки")
N("parking.guest", "Гостевые стоянки у жилья", {"per_1000": 40, "max_from_entrances_m": 200}, "мест / 1000 жит. / м", "жильё", "С08-11", plan="Парковки")
N("parking.area_m2_per_space", "Площадь на 1 машино-место", {"open": R(25, 30), "multilevel_underground": R(30, 37), "kerbside": 18}, "м² / место", "стоянки", "С08-9", plan="Парковки")
N("parking.aisles_m", "Проезды стоянок", {"90deg_two_sided": 6.95, "90deg_one_sided": 6.0, "60deg": 4.2, "45deg": 3.6, "space_width_90deg": 3.0}, "м", "стоянки", "С08-9")
N("parking.disabled_spaces", "Места для МГН", {"1-25": 1, "26-50": 2, "51-75": 3, "76-100": 4, "101-150": 5, "151-200": 6, "201-300": 7, "301-400": 8, "401-500": 9, "501-1000": "2 %", ">1000": "20 + 1 на каждые 100", "width_m": "2,4 + 1,5"}, "мест", "любая стоянка", "С08-9")
N("parking.distance_from_parking_m", "Разрывы от гаражей и открытых стоянок (табл. 11.8)", {"columns": "машино-мест ≤ 10 / 11–50 / 51–100 / 101–300", "housing": [10, 15, 25, 35], "blank_end_walls": [10, 10, 15, 25], "public_buildings": [10, 10, 15, 25], "schools_kindergartens": [15, 25, 25, 50], "hospitals": [25, 50, "по согласованию", "по согласованию"],
  "garages_over_300_or_service_over_30_posts": "вне жилой зоны, ≥ 50 м"}, "м", "стоянки и гаражи", "С08-12", "табл. 11.8")
N("parking.garage_entries_m", "Въезды и выезды гаражей", {"from_arterial_intersection": 50, "from_local_intersection": 20, "from_stop": 30, "underground_from_windows_schools_kindergartens_hospitals": 15}, "м (не ближе)", "гаражи", "С08-12", "п. 11.28")
N("parking.temporary_walk_max_m", "Пешая доступность временных стоянок", {"housing_entrances": 100, "stations_large_shops": 150, "offices_parks_stadiums_other": R(250, 400)}, "м", "временные стоянки", "С08-11")
N("parking.garage_area_by_floors_m2", "Площадь гаража на 1 машину по этажности (застройка / участок)", {"1": [27, 30], "2": [15, 19.2], "3": [10, 13], "4": [8, 10], "5": [6, 8], "6-8": [4, 5.5]}, "м² / машину", "наземные гаражи", "С08-12")
N("parking.service_petrol", "СТО и АЗС", {"sto_post_per_cars": 200, "sto_10_posts_ha": 1.0, "sto_25_posts_ha": 2.0, "azs_pump_per_cars": 1200, "azs_5_pumps_ha": 0.2, "azs_11_pumps_ha": 0.4}, "шт. / га", "СТО, АЗС", "С08-12")
N("parking.depots_ha", "Депо и парки (участок)", {"bus_park_100": 2.3, "bus_park_300": 4.5, "bus_park_500": 6.5, "tram_depot_100_cars": 6, "tram_depot_200_cars": 8, "trolleybus_100": 3.5, "trolleybus_200": 6.0}, "га", "автобусные парки, трамвайные (ближайший тип к депо ЛРТ) и троллейбусные депо", "С08-22")
N("parking.other_appendix8", "Прочее прил. 8 (как напечатано)", {"special_polyclinics": "25–33 на посещения", "theatres_concert_halls": "10–12,5 на места", "stadiums": "25–30 на места трибун", "stations": "8–12 на пассажиров в час пик", "parks_beaches": "4–5 на единовременных посетителей", "hospitals": "≥ 1 место для скорой"}, "как напечатано", "общественные объекты", "С08-22", "прил. 8", status="not_verified",
  note="единицы прил. 8 в извлечении неоднозначны")
N("parking.school_2000_places", "Парковка школы на 2000 мест (факт РК)", {"spaces": 48, "of_them_disabled": 5, "plus_bus": True}, "мест", "школа 2000 мест: персонал + 1 место на 10 старшеклассников", "Атырау")
N("parking.ground_lot_max_in_centre", "Наземная стоянка в центре района", 50, "мест (больше — ошибка)", "полигон «центр района»; наземные поля только у ТРЦ, стадионов и на окраинах", "PLAN", "правило 17")

# ============================ fire access =====================================================
N("fire_access.width_min_m", "Ширина пожарных подъездов и проездов", {"default": 6, "with_hydrant": 8}, "м", "все здания", "ТР405", also=[("ТР381", None)], plan="Пожарные проезды")
N("fire_access.slope_max_pct", "Уклон пожарных проездов", {"drives": 10, "approaches": 6}, "%", "проезды / подъезды", "ТР405")
N("fire_access.sides", "С каких сторон подъезд", {"one_long_side": "Ф1.3 до 28 м; Ф1.2, Ф1.5, Ф2.1, Ф2.2, Ф3, Ф4.2, Ф4.3 до 18 м", "two_long_sides": "Ф1.3 28–75 м; Ф1.2, Ф1.5, Ф2, Ф3, Ф4.2, Ф4.3 18–50 м", "ring": "Ф1.1 (детсады, больницы), Ф4.1 (школы); Ф1.3 > 75 м; прочие > 50 м; функционально связанные комплексы"}, "текст (высота здания)", "здания по классу функциональной опасности", "ТР405", plan="Пожарные проезды")
N("fire_access.ring_required", "Кольцевой проезд обязателен", {"classes": ["Ф1.1", "Ф4.1"], "residential_over_m": 75, "other_over_m": 50}, "класс / м", "детсады, больницы, школы; жильё выше 75 м; прочие выше 50 м", "ТР405", plan="Пожарные проезды")
N("fire_access.distance_to_wall_m", "Край проезда до стены", {"building_10_28m": R(5, 8), "building_over_28m": R(8, 10), "blank_facade": "не нормируется"}, "м", "здания по высоте (С08: 5–8 м до 10 эт., 8–10 м > 10 эт.)", "ТР405", also=[("С08-18", None)], plan="Пожарные проезды")
N("fire_access.low_rise_within_m", "Малоэтажное жильё (≤ 3 эт.)", 50, "м (подъезд техники в пределах)", "малоэтажные дома", "ТР405")
N("fire_access.dead_end_max_m", "Тупиковый проезд", 150, "м", "проезды и местные улицы", "ТР405", plan="Пожарные проезды")
N("fire_access.turnaround_min_m", "Разворотная площадка в конце тупика", [15, 15], "м × м", "тупики", "ТР405", plan="Пожарные проезды")
N("fire_access.turning_ring_m", "Разворотные кольца", {"island_min_diameter": 16, "public_transport_min": 30, "parking_on_turnaround": False}, "м", "тупики, конечные", "С08-9")
N("fire_access.arches", "Арки и сквозные проезды", {"height_min_m": 4.5, "width_min_m": 3.5, "through_passages_every_m": 300, "stairwell_passages_max_m": 100}, "м", "здания по периметру квартала", "ТР405")
N("fire_access.industrial_sides", "Производственные здания", {"two_sides_if_width_over_m": 18, "all_sides_if_area_over_m2": 10000, "all_sides_if_width_over_m": 100}, "м / м²", "производственные здания", "ТР405")
N("fire_access.hydrants", "Гидранты", {"max_from_carriageway_m": 2.5, "min_from_walls_m": 5, "min_count_if_flow_ls": [2, 15], "hose_max_m": 150, "to_water_body_max_m": 200}, "м", "наружное пожаротушение", "ТР405")
N("fire_access.blank_facade_strip_m", "Полосы вдоль фасадов без входов", 6, "м", "фасады без входов", "С08-18")

# ============================ street cross-section (all classes) ==============================
N("street_xs.red_lines_m", "Ширина в красных линиях", {"arterial_roads": R(50, 75), "arterial_streets": R(40, 80), "local_streets_roads": R(15, 25)}, "м", "по классу", "С08-10", plan="Улицы в красных линиях")
N("street_xs.red_lines_no_buildings", "В красных линиях", "запрещено размещать здания, не относящиеся к транспортной инфраструктуре (временные лёгкие инфоконструкции — по согласованию)", "текст", "все улицы", "С08-11")
N("street_xs.bus_lane_m", "Крайняя полоса для автобусов / троллейбусов", 4.0, "м", "магистрали крупных городов; полосы 4 м и на грузовых магистралях", "С08-10")
N("street_xs.bus_carriageway_m", "Обособленная проезжая часть для автобусов", {"width": R(8, 12), "when_buses_per_peak_h_over": 40, "reconstruction_over": 20}, "м / авт/ч", "магистрали", "С08-10")
N("street_xs.sidewalk_extra_at_walls_m", "Тротуары у стен, подпорных стен, оград", 0.5, "м (+)", "все тротуары", "С08-10")
N("street_xs.sidewalk_arterial_snow_min_m", "Тротуар магистрали при снегопереносе > 200 м³/м", 3, "м", "магистральные улицы", "С08-10")
N("street_xs.sidewalk_local_1m_only", "Тротуар местной улицы 1,0 м", "только при реконструкции или потоке < 50 пеш/ч в обе стороны", "текст", "местные улицы", "С08-10")
N("street_xs.sidewalk_separation", "Отделение тротуара от проезжей части", "газоном, бортом, ограждением; вдоль местных проездов магистралей — полоса для остановки ≤ 0,8 м", "текст", "все улицы", "С08-11")
N("street_xs.tree_offsets_m", "Деревья до края проезжей части и тротуара (табл. 9.2)", {"trunk_to_carriageway": 2.0, "shrub_to_carriageway": 1.0, "trunk_to_sidewalk_edge": 0.7, "shrub_to_sidewalk_edge": 0.5}, "м", "посадки вдоль улиц", "С08-7", "табл. 9.2")
N("street_xs.green_strip_with_trees_min_m", "Газон с деревьями между проезжей частью и тротуаром", 2.7, "м", "улицы с рядовой посадкой", "С08-7", "табл. 9.2", derived=True, note="2,0 м от ствола до проезжей части + 0,7 м до края тротуара [выч. w35]")
N("street_xs.sidewalk_gdci", "Тротуар (международный ориентир)", {"quiet_recommended_clear": 2.4, "quiet_absolute_min": 1.8, "with_trees": "≥ 2,4 + приствольные ≥ 1,5", "commercial": 3, "busy": R(8, 10)}, "м", "тротуары", "GDCI-тротуар")
N("street_xs.bike_lane_on_carriageway_m", "Велополоса на проезжей части", {"one_way": 1.2, "contraflow": 1.5, "along_sidewalk": 1.0}, "м (не меньше)", "улицы", "С08-9")
N("street_xs.bike_clearances_m", "Зазоры велодорожки", {"to_carriageway_poles_trees": 0.75, "to_sidewalk": 0.5, "to_parking_and_stops": 1.5}, "м", "велодорожки", "С08-9")
N("street_xs.bike_separation_rule", "Когда велодорожку отделять", {"separate_if_car_speed_over_kmh": 30, "shared_marking_kmh": R(15, 30), "no_marking_below_kmh": 15}, "км/ч", "все улицы", "ITDP")
N("street_xs.median_rural_m", "Разделительная полоса загородных дорог", {"I-a_no_barrier": 6, "I-b_no_barrier": 5, "with_barrier": "≥ 2 + ширина ограждения", "safety_strip": 1.0}, "м", "дороги I-а / I-б (А-3, БАКАД)", "СП303")
N("street_xs.micromobility_genplan", "Микромобильность Алатау", {"share_min_pct": 5, "network_km_over": 1000}, "% / км", "Алатау", "ГП727")
N("street_xs.disabled_access", "Доступность для МГН", {"kerb_at_crossings_max_cm": 5, "ramp_max_permille": 100, "path_slope_max_permille": 50, "landing_every_m_at_30_60_permille": 100, "landing_len_m": 5}, "см / ‰ / м", "пешеходные пути", "С08-9")
N("street_xs.metro_shallow_zone_m", "Метро мелкого заложения", 40, "м (техническая зона вдоль линии)", "резерв линии метро", "С08-11")
N("street_xs.network_density_genplan", "Плотность сети (генплан)", {"total_km": 2097, "new_areas_km_per_km2": 5.1, "arterial_km_per_km2": 2.9, "continuous_arterials_km": 58.8, "a3_km": 48.3}, "км / км/км²", "Алатау", "ГП727")
N("street_xs.genplan_speed_regimes_kmh", "Режимы скоростей генплана", [70, 50, 30], "км/ч", "Алатау", "ГП727", sev="info")
N("street_xs.unh_network", "Ориентир сети UN-Habitat", {"street_share_min_pct": 30, "street_km_per_km2_min": 18, "arterial_step_m": R(800, 1000)}, "% / км/км² / м", "город", "UNH", sev="info")

# ============================ intersections ===================================================
N("intersections.continuous_all_grade_separated", "Магистрали непрерывного движения и скоростные дороги", True, "bool (все узлы в разных уровнях)", "скоростные, непрерывного движения", "ДБН", sev="error",
  sev_why="класс С08 «непрерывного движения» по смыслу без узлов в одном уровне; для А-3, БАКАД, IA план: «только развязки в разных уровнях»", also=[("PLAN", "«Узлы»")], plan="Узлы")
N("intersections.interchange_spacing_continuous_m", "Шаг развязок на улицах непрерывного движения", {"min": 800, "max": 1200, "centre_min": 600}, "м", "магистрали непрерывного движения", "ДБН", plan="Узлы")
N("intersections.interchange_spacing_regulated_m", "Шаг развязок на улицах регулируемого движения", R(500, 1500), "м", "регулируемые магистрали", "ДБН")
N("intersections.at_grade_spacing_arterial_m", "Шаг пересечений в одном уровне на магистралях", {"min": 300, "max": 800, "reconstruction_min": 200}, "м", "регулируемые магистрали", "ДБН", plan="Узлы")
N("intersections.local_join_regulated_m", "Примыкание местных улиц к регулируемым магистралям", R(300, 400), "м (обычно на регулируемых перекрёстках)", "регулируемые магистрали", "ДБН")
N("intersections.right_in_right_out_m", "Правоповоротные примыкания (вход/выход)", {"from_nearest_node_min": 100, "between_min": 150}, "м", "магистральная сеть", "ДБН")
N("intersections.quarter_entries_max_m", "Въезды в кварталы с районных улиц", 200, "м (не реже чем через)", "районные улицы", "С08-5")
N("intersections.interchange_warrant", "Когда регулируемая магистраль требует развязки", {"total_approach_veh_h": 6000, "single_left_turn_veh_h": 600}, "авт/ч (больше)", "регулируемые магистрали", "ДБН")
N("intersections.district_at_grade", "Магистрали районного значения", "пересечения в одном уровне; общегородские регулируемые — в одном или разных уровнях", "текст", "районные магистрали", "normacs-4818")
N("intersections.channelisation", "Канализированный узел и отдельные поворотные съезды", {"left_turn_veh_h": R(100, 300), "separate_turn_if_share_over_pct": 10, "design_separately_over_pct": 30}, "авт/ч / %", "узлы в одном уровне", "ДБН")
N("intersections.rural_interchange_required", "Развязки на загородных дорогах РК обязательны", "с дорогой I-а — всегда; I-б с I-б, II, III; II с II, III; III с III при суммарной перспективной интенсивности > 8000 трансп. ед/сут", "текст", "дороги общей сети", "СП303")
N("intersections.rural_spacing_km", "Шаг пересечений/примыканий вне населённых пунктов", {"I-a": 10, "I-b_and_II": 5, "III": 2}, "км (не меньше)", "дороги общей сети вне города", "СП303")
N("intersections.signal_roundabout_interchange_rule", "Светофор vs кольцо vs развязка (правило R2)", "светофор — регулируемые магистрали и их пересечения с районными; кольцо — при сопоставимых потоках и входящем + конфликтующем < 1800 авт/ч (2 полосы); развязка — по порогам 6000 / 600 авт/ч", "текст", "генератор узлов", "R2", also=[("ДБН", None), ("NCHRP", None)])
N("intersections.signal_warrants", "Критерии установки светофора (warrants)", None, "—", "узлы в одном уровне", "R2", status="not_verified", note="нормативных критериев РК не найдено [НЕ ПРОВЕРЕНО]; генератор ставит светофор по правилу R2 выше")
N("intersections.curb_radius_m", "Радиус закругления бортового камня", {"regulated_arterials": 8, "local_streets": 5, "transport_squares": 12, "constrained_arterial_min": 6, "constrained_square_min": 8, "no_curb_add_per_lane": 1}, "м", "узлы в одном уровне", "С08-9", "п. 11.10–11.11")
N("intersections.curb_radius_kz_project_m", "Радиусы в реальном проекте РК", {"local_to_district_arterial": [8, 12], "driveway_width": 6, "driveway_radius": 6}, "м", "примыкания местных улиц, въезды", "Астана23", status="analogue", basis="kz_project_fact")
N("intersections.visibility_vehicle_m", "Треугольник видимости «транспорт–транспорт»", {"40_kmh": [25, 25], "60_kmh": [40, 40]}, "м × м", "нерегулируемые пересечения", "С08-9")
N("intersections.visibility_pedestrian_m", "Треугольник «пешеход–транспорт»", {"25_kmh": [8, 40], "40_kmh": [10, 50]}, "м × м", "переходы", "С08-9")
N("intersections.visibility_clear", "В треугольнике видимости", {"no": "здания, киоски, реклама", "planting_max_m": 0.5, "rural_planting_max_m": 1.2}, "м", "треугольник видимости", "С08-9", also=[("СП303", None)])
N("intersections.max_legs_without_ring", "Лучей в узле без кольца или площади", 4, "лучей (5+ — только кольцо или площадь)", "все узлы в одном уровне", "PLAN", "правило 6")

# ============================ roundabouts =====================================================
N("roundabouts.when", "Когда кольцо", "при сопоставимой интенсивности на пересекающихся/примыкающих улицах; при явном преобладании направления — овальный/вытянутый островок", "текст", "узлы в одном уровне", "ДБН")
N("roundabouts.entry_capacity_veh_h", "Пропускная способность входа", {"one_lane_max": 1000, "two_lane_max": 1800}, "авт/ч (входящий + конфликтующий)", "кольца", "NCHRP")
N("roundabouts.icd_m", "Диаметр вписанной окружности (ICD)", {"mini": R(14, 27), "single_B12": R(27, 46), "single_WB15": R(32, 46), "single_WB20": R(40, 55), "double": R(46, 67), "double_WB20": R(50, 67), "triple": R(61, 76), "triple_WB20": R(67, 91)}, "м", "кольца по типу и расчётному автомобилю", "NCHRP", derived=True)
N("roundabouts.circulating_width_m", "Ширина кольцевой проезжей части", {"single": R(4.9, 6.1), "multi_per_lane": R(4.3, 4.9), "two_lanes": R(8.5, 9.8), "three_lanes": R(12.8, 14.6), "single_not_wider_than_entry_x": 1.2}, "м", "кольца", "NCHRP", derived=True)
N("roundabouts.entry_width_m", "Ширина входа", {"single": R(4.3, 5.5), "double": R(7.3, 9.1), "triple": R(11.0, 13.7)}, "м", "кольца", "NCHRP", derived=True)
N("roundabouts.entry_radius_max_m", "Радиус входа", {"single": 52, "multi": 84}, "м (не больше)", "кольца", "Maine", derived=True)
N("roundabouts.entry_speed_max_kmh", "Макс. скорость на входе", {"mini": 30, "single": 40, "multi": R(40, 50), "conflict_speed_diff_max": R(16, 24)}, "км/ч", "кольца", "NCHRP")
N("roundabouts.splitter_island_m", "Направляющий островок", {"length_min": 15, "length_desired": 30, "length_high_speed": 46, "width_at_crossing_min": 1.8}, "м", "кольца", "NCHRP", derived=True)
N("roundabouts.crossing_setback_m", "Пешеходный переход у кольца", 6, "м от края кольцевой проезжей части", "кольца", "NCHRP")
N("roundabouts.central_island", "Центральный остров", {"no_hard_objects": True, "truck_apron_m": 4.6}, "м", "кольца", "Maine")
N("roundabouts.large_ring_dbn", "Большие кольца (ДБН табл. 3.2): R острова / ширина кольца / участок переплетения", {"20": [25, 8.5, 25], "30": [30, 10.0, 35], "40": [40, 11.5, 45], "50": [45, 13.0, 60], "60": [50, 14.5, 70], "70": [55, 15.5, 80], "80": [60, 16.0, 90], "recommended_kmh": R(30, 40)}, "км/ч → м", "кольца советского типа", "ДБН", "табл. 3.2")
N("roundabouts.lanes_dbn", "Полосы на кольце", {"lane_m": R(3.75, 4.0), "min_lanes_near_capacity": 2, "right_turn_lane_m": 4, "max_lanes": 4, "splitter_radius_with_pt_min_m": 15, "splitter_radius_min_m": 10}, "м / шт.", "кольца", "ДБН", "п. 3.5–3.6")
N("roundabouts.forbidden", "Кольцо не по месту", ["кольцо с > 4 полосами по кругу", "кольцо на автомагистрали", "кольцо при резко неравных потоках"], "список", "все кольца", "ДБН", "п. 3.5–3.6", also=[("NCHRP", "пороги 1000 / 1800 авт/ч")])

# ============================ interchanges ====================================================
N("interchanges.types", "Типы развязок и где применять", {
    "diamond": "рассматривать первым; наименьшая площадь; при малых левых поворотах; ёмкость ограничена узлами на второстепенной дороге",
    "spui": "одноточечный ромб: наименьшая полоса отвода; часто единственный вариант в стеснённой застройке",
    "partial_cloverleaf": "петли в 1–3 квадрантах; петлю добавлять при левоповоротном потоке ≥ 500 авт/ч",
    "cloverleaf": "минимальный тип для двух магистралей с полным контролем доступа; ≈ 8 га отвода на квадрант; C-D дороги при переплетении > 1000 авт/ч",
    "trumpet": "трёхлучевые узлы; полупрямые съезды 1200–1500 авт/ч, петли 800–1200 авт/ч",
    "directional": "магистраль × магистраль при высоких объёмах; без переплетения; дорого, часто 4 уровня",
    "system_vs_service": "системная — магистраль × магистраль (клевер, направленная); обслуживающая — магистраль × улица (ромб, ParClo, SPUI)"},
  "текст", "развязки", "WSDOT", also=[("SCDOT", None), ("MoDOT", None)], plan="Узлы")
N("interchanges.parclo_loop_left_turn_veh_h", "Петля ParClo", 500, "авт/ч левого поворота (от)", "неполный клевер", "SCDOT", also=[("WSDOT", None)])
N("interchanges.parclo_a_terminal_spacing_m", "ParClo-A с петлями R 46 м: узлы на поперечной дороге", 213, "м", "пример", "SCDOT", derived=True, sev="info")
N("interchanges.cloverleaf_cd_weaving_veh_h", "C-D дороги у клевера", 1000, "авт/ч переплетения (больше — C-D обязательно)", "клевер", "MoDOT", also=[("WSDOT", None)])
N("interchanges.cloverleaf_quadrant_ha", "Отвод клевера на квадрант", 8, "га (≈ 20 акров)", "клевер", "WSDOT", derived=True, sev="info")
N("interchanges.compressed_cloverleaf_r30", "«Сжатый клевер» с петлёй R 30 м", "только на дорогах IV–V категорий в стеснённых условиях", "текст", "развязки", "СП303", plan="Съезды и петли")
N("interchanges.spacing_expressway_m", "Шаг развязок вдоль скоростной дороги", {"city_min": 1600, "rural_interstate": 4800, "rural_other": 3200, "closer_only_with": "C-D дороги или съезды в разных уровнях (параллельные съезды)"}, "м", "А-3, БАКАД, IA", "WSDOT", also=[("SCDOT", None), ("PLAN", "«Узлы»: не чаще чем через 1,6 км")], derived=True, plan="Узлы")
N("interchanges.genplan_counts", "Развязки по генплану", {"a3": 23, "bakad": 12, "ia": 16}, "развязок", "места и число по генплану", "PLAN", "«Узлы»", also=[("ГП727", None)], plan="Узлы")
N("interchanges.genplan_totals", "Развязки генплана всего", {"total": 78, "existing": 14, "by_2050": 34, "after_2050": 30, "stage1_by_2030": 7, "stage1_network_km": 359.3}, "развязок / км", "Алатау", "ГП727")
N("interchanges.expressway_grade_separated_only", "А-3, БАКАД, IA — только развязки в разных уровнях", True, "bool", "скоростные дороги", "PLAN", "«Узлы»", also=[("СП303", "с дорогой I-а — всегда; на I-а — только внеуличные переходы")], plan="Узлы")

# ============================ ramps and loops =================================================
N("ramps.design_speed_kmh", "Расчётная скорость правоповоротных съездов", {"from_I_II": 60, "from_III": 50}, "км/ч (не меньше)", "съезды", "СП303")
N("ramps.width_m", "Ширина проезжей части съезда", {"left_turn": 5.5, "right_turn": 5.0, "shoulder_inner": 1.5, "shoulder_outer": 3.0}, "м", "съезды", "СП303")
N("ramps.slope_max_permille", "Продольный уклон съезда", 40, "‰", "съезды", "СП303")
N("ramps.speed_wsdot_kmh", "Скорость съезда (верх / середина / низ)", {"80": [72, 48, 40], "97": [80, 72, 40], "113": [97, 80, 40], "129": [113, 97, 40]}, "км/ч (по скорости магистрали)", "съезды", "WSDOT", derived=True)
N("ramps.speed_share_modot", "Желательная скорость съезда", 0.7, "доля рабочей скорости магистрали", "съезды", "MoDOT")
N("ramps.min_radius_by_speed_m", "Мин. радиус по скорости (вираж)", {"24": 15, "32": 27, "40": 46, "48": 70, "56": 94, "64": 131, "72": 165}, "км/ч → м", "съезды и петли", "MoDOT", "табл. 2", derived=True)
N("ramps.loop_radius_m", "Радиус петли", {"roads_over_80_kmh": R(46, 76), "otherwise": R(30, 52), "loop_speed_min_kmh_on_expressways": 40, "r30_only": "сжатый клевер на IV–V (СП303)"}, "м", "петли развязок", "MoDOT", derived=True, also=[("СП303", "R 30 м — только IV–V"), ("PLAN", "«Съезды и петли»")], plan="Съезды и петли")
N("ramps.loop_overtravel_m", "Петля: перепробег", {"r34": 200, "r52": 305, "plus_8_kmh": "+50 % длины, +130 % отвода"}, "м", "петли", "MoDOT", derived=True, sev="info")
N("ramps.capacity_veh_h", "Ёмкость съездов", {"single_loop": R(800, 1200), "direct_free": R(800, 1200), "two_lane_ramp_over": 1200, "two_loops_weaving_limit": 1000}, "авт/ч", "съезды", "MoDOT", also=[("SCDOT", None)])
N("ramps.width_wsdot_m", "Ширина съезда (WSDOT)", {"one_lane_total_min": 6.1, "lane_min": 3.7, "left_shoulder_min": 0.6, "right_shoulder": R(1.2, 2.4), "two_lane_total_min": 9.1, "two_lanes_min": 7.3}, "м", "съезды", "WSDOT", derived=True)
N("ramps.cd_road_width_m", "C-D дорога", {"one_lane": 4.9, "two_lanes": 7.3}, "м", "C-D дороги", "SCDOT", derived=True)
N("ramps.grade_wsdot_pct", "Уклон съезда (желат. / макс.)", {"40_48_kmh": [5, 7], "56_64_kmh": [4, 6], "72_plus_kmh": [3, 5], "downgrade_extra": 2}, "%", "съезды", "WSDOT", derived=True)
N("ramps.speed_change_lanes_kz_m", "Переходно-скоростные полосы (табл. 22): разгон / торможение / отгон", {"I-b_II": [180, 100, 80], "III": [130, 75, 60], "IV": [40, 40, 30], "upgrade_40permille_I-b_II": [230, 90], "downgrade_40permille_I-b_II": [140, 110]}, "м", "загородные дороги", "СП303", "табл. 22")
N("ramps.deceleration_lane_kz_m", "Полоса торможения (табл. 21) при скорости магистрали 150 / 120 / 80", {"exit_80": [150, 40, 0], "exit_60": [230, 120, 0], "exit_40": [280, 170, 50], "taper_I-a": 120}, "м", "загородные дороги", "СП303", "табл. 21")
N("ramps.accel_from_stop_wsdot_m", "Разгон с места", {"80_kmh": 219, "97_kmh": 366, "113_kmh": 494, "129_kmh": 610, "upgrade_factor": R(1.3, 3.0)}, "м", "въезды на магистраль", "WSDOT", derived=True)
N("ramps.decel_to_stop_wsdot_m", "Торможение до 0", {"80_kmh": 133, "97_kmh": 162, "113_kmh": 187, "129_kmh": 224, "downgrade_factor": R(1.2, 1.35)}, "м", "выезды", "WSDOT", derived=True)
N("ramps.tapers_scdot", "Клинья", {"exit_divergence_deg": 4, "exit_divergence_range_deg": R(2, 5), "parallel_min_m": 91, "parallel_ratio": "25:1", "entrance_taper_min": "50:1", "entrance_taper_desired": "70:1", "to_crossroad": "25:1"}, "° / м / уклон", "съезды", "SCDOT", derived=True)
N("ramps.merge_angle_max_deg", "Съезд примыкает к скоростной дороге касательно", 4, "° (не больше), зазор 0, есть переходно-скоростная полоса", "скоростные дороги и магистрали непрерывного движения", "PLAN", "правило 7", also=[("SCDOT", "отклонение 4° (2–5°)")], plan="Съезды и петли")
N("ramps.merge_gap_m", "Зазор съезда и основной дороги", 0, "м", "примыкание съезда", "PLAN", "правило 7")
N("ramps.secondary_terminal_angle_deg", "Съезд ромба выходит на второстепенную дорогу", R(70, 110), "°", "ромб, неполный клевер", "PLAN", "«Съезды и петли» (угол примыкания — правило qTwin)", plan="Съезды и петли")
N("ramps.spacing_wsdot_m", "Расстояние между съездами (gore-to-gore)", {"entry_entry_or_exit_exit_mainline": 305, "same_on_cd": 244, "exit_then_entry": 152, "exit_then_entry_cd": 122, "entry_then_exit_weaving": R(305, 610)}, "м", "съезды", "WSDOT", derived=True)
N("ramps.weaving_m", "Длина переплетения", {"min": 305, "aux_lane_if_gores_closer_than": 457}, "м", "съезды", "SCDOT", derived=True)
N("ramps.curve_before_merge_min_m", "Кривая перед въездом на магистраль", 305, "м (R не меньше)", "въезды", "SCDOT", derived=True)

# ============================ rural roads (A-3, BAKAD, approaches) ============================
N("rural.categories_veh_day", "Категории по интенсивности", {"I-a": "> 14 000 (автомагистраль)", "I-b": "> 14 000 (скоростная)", "II": "6 000–14 000", "III": "2 000–6 000", "IV": "200–2 000", "V": "< 200"}, "физ. ед/сут", "дороги общей сети", "СП303")
N("rural.design_speed_kmh", "Расчётная скорость (основная / пересечённая / горная)", {"I-a": [150, 120, 80], "I-b": [120, 100, 60], "II": [120, 100, 60], "III": [100, 80, 50], "IV": [80, 60, 40], "V": [60, 40, 30]}, "км/ч", "дороги общей сети", "СП303")
N("rural.lanes", "Полосы и обочины", {"I-a": "≥ 2×2 по 3,75 м", "I-b_II": "2×2 / 2 по 3,75 м", "III_lane_m": 3.5, "IV_lane_m": 3.0, "shoulder_I_II_m": 3.75, "shoulder_III_m": 2.5, "shoulder_IV_m": 2.0}, "м", "дороги общей сети", "СП303")
N("rural.min_radius_m", "Мин. радиус в плане (осн. / горн.)", {"150": [1200, 1000], "120": [800, 600], "100": [600, 400], "80": [300, 250], "60": [150, 125], "50": [100, 100], "40": [60, 60], "30": [30, 30]}, "км/ч → м", "дороги общей сети", "СП303")
N("rural.max_grade_permille", "Макс. продольный уклон", {"150": 30, "120": 40, "100": 50, "80": 60, "60": 70, "40": 90}, "км/ч → ‰", "дороги общей сети", "СП303")
N("rural.stopping_sight_m", "Расстояние видимости для остановки", {"150": 300, "120": 250, "100": 200, "80": 150, "60": 85, "40": 55}, "км/ч → м", "дороги общей сети", "СП303")
N("rural.vertical_curve_m", "Мин. радиусы вертикальных кривых (выпуклая / вогнутая)", {"120": [15000, 5000], "100": [10000, 3000], "80": [5000, 2000], "60": [2500, 1500]}, "км/ч → м", "дороги общей сети", "СП303")
N("rural.suburban_roads", "Пригородные дороги (прил. 7): скорость / полоса / полос / R / уклон / земполотно", {"expressway": [150, 3.75, "4–8", 1000, 30, 65], "sectoral": [120, 3.75, "4–6", 600, 50, 50], "zonal": [100, 3.75, "2–4", 400, 60, 40], "freight_local": [70, 4.0, 2, 250, 70, 20], "park": [50, 3.0, 2, 175, 80, 15], "lane_if_heavy_trucks_over_20pct_m": 4.5},
  "км/ч / м / шт. / м / ‰ / м", "пригородные дороги", "С08-22", "прил. 7")

# ============================ pedestrian crossings ============================================
N("crossings.at_grade_spacing_regulated_m", "Переходы в одном уровне на регулируемых магистралях", R(200, 300), "м", "город", "С08-11", "п. 11.13", plan="Пешеходные переходы")
N("crossings.grade_separated_spacing_m", "Переходы в разных уровнях", {"expressways_rapid_tram_rail": R(400, 800), "continuous_arterials": R(300, 400)}, "м", "скоростные дороги, ж/д, ЛРТ на земле; магистрали непрерывного движения", "С08-11", "п. 11.13", plan="Пешеходные переходы")
N("crossings.grade_separated_on_regulated_if_ped_h", "Внеуличный переход на регулируемой магистрали", 3000, "пеш/ч (больше)", "регулируемые магистрали", "С08-11")
N("crossings.pedestrian_density_max", "Плотность пешеходного потока в час пик", {"large_retail_public_centres": 0.3, "transport_entertainment": 0.8}, "чел. / м²", "площади, тротуары", "С08-11")
N("crossings.rural_through_settlement", "Переходы на дорогах через населённый пункт", {"spacing_m": R(200, 300), "short_settlement_up_to_km": 0.5, "short_settlement_max_crossings": 2, "short_settlement_spacing_m": R(150, 200), "fence_each_side_m": 50}, "м", "дороги общей сети в сёлах", "СП303")
N("crossings.type_by_category", "Тип перехода по категории дороги (табл. 16)", {"I-a": "только в разных уровнях", "I-b": "в уровне при < 100 пеш/ч", "II": "в уровне при < 250 пеш/ч", "III": "в уровне при любом потоке"}, "текст", "дороги общей сети", "СП303", "табл. 16")
N("crossings.refuge_island_if_carriageway_m", "Островок безопасности на переходе", 15, "м ширины проезжей части (от)", "переходы", "СП303")
N("crossings.at_every_at_grade_node", "Переход в каждом узле в одном уровне", True, "bool", "улицы городского типа", "PLAN", "правило 10")
N("crossings.itdp", "Переходы (TOD)", {"where_speed_over_kmh": 15, "max_spacing_main_streets_m": 200, "width_min_m": 2}, "км/ч / м", "плотная сетка", "ITDP")

# ============================ LRT =============================================================
N("lrt.genplan", "LRT генплана", {"length_km": 76.2, "lines": 3, "speed_kmh": R(25, 40), "peak_per_direction": 55000, "pass_per_day": 200000}, "км / шт. / км/ч / пасс.", "Алатау", "ГП727", plan="ЛРТ")
N("lrt.station_spacing_km", "Шаг станций ЛРТ", R(0.8, 1.5), "км", "LRT Алатау", "ГП727", also=[("PLAN", "правило 25")], plan="ЛРТ")
N("lrt.station_axis_max_offset_m", "Станция на оси линии", 2, "м (не дальше)", "станции ЛРТ", "PLAN", "правило 25")
N("lrt.platform_between_cross_streets", "Платформа целиком между соседними поперечными улицами", True, "bool", "станции ЛРТ", "PLAN", "«ЛРТ», правило 25 (правило qTwin)", plan="ЛРТ")
N("lrt.line_ends", "Концы линии", ["депо", "конечная станция"], "список", "линии ЛРТ", "PLAN", "правило 25")
N("lrt.viaduct_clearance_over_road_m", "Низ эстакады ЛРТ над дорогой", 5.0, "м (не меньше)", "эстакады ЛРТ", "PLAN", "правило 25", also=[("EC", None)], note="то же число, что bridges.road_clearance_m")
N("lrt.ramp_slope_max_pct", "Переход эстакада–земля", 6, "% (не больше)", "рампы ЛРТ", "PLAN", "правило 25 (правило qTwin)", also=[("Lite", "макс. уклон 6 %")])
N("lrt.min_curve_radius_m", "Мин. радиус кривой LRT", 25, "м", "LRT", "Lite", note="Metro Lite: макс. скорость 60 км/ч")
N("lrt.corridor_width_m", "Полоса отвода LRT в уровне земли", {"double_track": 7.6, "double_track_staggered_pavilions": 8.5, "single_track": 3.5, "single_track_at_pavilion": 5.5}, "м", "LRT на земле", "Lite")
N("lrt.platform_length_m", "Длина платформы ЛРТ", {"min": 33, "rule": "не короче состава", "platform_width_per_side_min_m": 1.12}, "м", "станции ЛРТ", "Lite", None, status="analogue",
  note="аналог: 3-вагонный блок Metro Lite ≥ 33 м, ширина вагона 2,65 м; ширина платформы по NFPA 130. Длина платформы LRT Алатау/Астаны не найдена [НЕ ПРОВЕРЕНО]", plan="Не проверено: длина платформы ЛРТ")
N("lrt.astana_analogue", "Аналог: LRT Астаны (открыт 16.05.2026)", {"length_km": 22.4, "stations": 18, "mean_spacing_km": 1.3, "cars": 4, "capacity_pass": 652, "vmax_kmh": 80, "vavg_kmh": 50, "headway_min": R(4, 5), "power": "750 В DC", "automation": "GoA4"}, "разные", "сравнение", "AstLRT", also=[("UTM", None)], sev="info")
N("lrt.at_grade_crossing", "ЛРТ на земле и улица", "пересекаются только в узле-переезде со светофором", "текст", "ЛРТ на земле", "PLAN", "правило 1")
N("lrt.tod", "TOD у станций", {"frequency_max_min": 15, "hours": "≈ 7–22", "station_zone_optimal_m": 500, "station_zone_max_m": 1000}, "мин / м", "станции", "ITDP")

# ============================ flood and water =================================================
N("flood.design_flood_pct", "Расчётный паводок", {"residential_public": 1, "parks_sports": 10}, "% обеспеченности", "застройка / парки", "С08-16", plan="Вода и паводок")
N("flood.freeboard_m", "Запас над расчётным уровнем", 0.5, "м", "бровка подсыпки или дамбы; низ здания", "С08-16", plan="Вода и паводок")
N("flood.no_building_depth_m", "Глубина затопления без инженерной защиты", 1.5, "м (≥ — не строить)", "застройка", "С08-16")
N("flood.groundwater", "Грунтовые воды", {"lower_in_built_up_min_m": 2, "lower_in_parks_stadiums_min_m": 1, "fill_mineral_soil_min_m": 1}, "м", "микрорайоны, парки", "С08-16")
N("flood.water_protection_strip_min_m", "Водоохранная полоса", 35, "м (не уже)", "реки, Капчагай; здания кроме причалов, марины, пляжных павильонов", "ВОЗ25", plan="Вода и паводок")
N("flood.water_protection_strip_table_m", "Водоохранная полоса по угодьям и уклону (0 / ≤ 3° / > 3°)", {"arable": [35, 55, 100], "meadow": [35, 50, 75], "forest_shrub": [35, 35, 55], "other": [35, 35, 100], "fish_spawning_min": 100, "plus": "прогноз переработки берега за 10 лет"}, "м", "водоохранная полоса", "ВОЗ25")
N("flood.water_protection_zone", "Водоохранная зона", {"river": "от уреза межени до границы паводка + 500 м с каждого берега", "channel_reservoir": "как у реки; внутренняя граница — по НПУ (Капчагай — русловое, вывод R2)", "lake_up_to_2km2_m": 300, "lake_over_2km2_m": 500, "city_reduction_to_m": 70, "city_reduction_conditions": "все 4: барьеры стока, технологии без загрязнения, режим землепользования, централизованная канализация"}, "текст / м", "реки и водохранилища", "ВОЗ25")
N("flood.floodplain_allowed", "В пойме допустимы", ["парки", "набережные", "пляжи", "причалы без капитальных зданий"], "список", "пойма", "PLAN", "«Вода и паводок» (правило qTwin)", plan="Вода и паводок")
N("flood.road_in_floodplain", "Дорога в воде или в пойме", "только как мост или дамба выше паводка 1 % + 0,5 м", "текст", "дороги", "PLAN", "правило 4")
N("flood.resort_from_waterline_m", "Курортные объекты у воды", 50, "м от уреза (не ближе)", "Green", "С08-8")
N("flood.kapchagay_levels_m", "Уровни Капчагайского вдхр.", {"npu_design_max": 485, "working_max": 479, "2023_09_12": 476.13, "2026_07": R(477, 478)}, "м абс.", "граница воды и водоохранной зоны (по НПУ)", "Tengri_Kap", note="НПУ 485 м ни разу не достигался (research/transport_site.md §7)")
N("flood.water_code_bans", "Запреты ст. 86 Водного кодекса в зоне и полосе", None, "—", "водоохранные зоны", "ВОЗ25", status="not_verified", note="текст статьи не получен [НЕ ПРОВЕРЕНО]")

# ============================ bridges =========================================================
N("bridges.road_clearance_m", "Габарит моста над дорогой", 5.0, "м", "низ пролёта / эстакады над проезжей частью", "EC", None, status="analogue", sev="error",
  sev_why="правила 9 и 25 плана называют 5,0 м прямо", also=[("СП37", "п. 10.3.12: ≥ 5,0 м от низа эстакад/галерей до покрытия; ≥ высота ТС + 1,0 м при ТС > 4,0 м")],
  note="Eurocode 1 ≥ 5 м; Великобритания 5,03 м; США Interstate 4,9 м; казахстанского числа не найдено [НЕ ПРОВЕРЕНО для РК]", plan="Габарит моста над дорогой")
N("bridges.rail_clearance_m", "Габарит над железной дорогой", 6.4, "м от верха головки рельса до низа пролёта", "путепроводы над ж/д (gen_network, правило 9)", "QTWIN",
  "высота габарита приближения строений С по ГОСТ 9238 (6400 мм)", status="not_verified", sev="error",
  sev_why="путепровод ниже габарита не пропускает подвижной состав: ошибка, хотя число — модель",
  also=[("СП35", "п. 5.20 (→ ГОСТ 9238)")],
  note="модель qTwin: ГОСТ 9238-2013 — межгосударственный стандарт; его текст с числом в research не получен (w35, w43 не нашли открытого текста), 6,4 м — высота габарита С над УГР по памяти. "
  "gen_network поднимает настил над путём (+ clearance_margin_m, + deck_depth_m), правило 9 проверяет низ пролёта над путём", plan="Не проверено: габариты над железной дорогой")
N("bridges.navigable_clearance_m", "Габарит над судоходной рекой", None, "м", "мосты над судоходными путями", "СП35", "п. 5.22 (→ ГОСТ 26775)", status="not_verified",
  note="число не получено; судоходность Или / Капчагая в черте города не проверена", plan="Не проверено: габариты над судоходной рекой")
N("bridges.river_clearance_m", "Низ пролёта над расчётным паводком (несудоходные)", {"backwater_up_to_1m": 0.5, "backwater_over_1m": 0.75, "ice_jams": 1.0, "debris_flow": 1.5, "span_min_with_debris_m": 15}, "м", "мосты над реками", "СП35", also=[("СНиП-мосты-2", None)], plan="Мост над рекой")
N("bridges.pedestrian", "Пешеходные тоннели и закрытые переходы", {"tunnel_clear_height_min": 2.3, "tunnel_width_min": 3.0, "footbridge_width_min": 2.25}, "м", "внеуличные переходы", "СП35", "п. 5.21", also=[("СНиП-мосты-2", None)])
N("bridges.city_bridge_sidewalks", "Тротуары на городских мостах", {"width_min_m": 1.5, "lane_capacity_ped_h": 1500, "railing_min_m": 1.1, "parapet_m": 0.75}, "м / пеш/ч", "мосты в городе", "СНиП-мосты-4")
N("bridges.screens_over_electrified_rail_m", "Щиты на мостах над электрифицированной ж/д", 2.0, "м", "путепроводы и пешеходные мосты над контактной сетью", "СНиП-мосты-4")
N("bridges.farm_road_under_bridge_m", "Сельхоздороги под мостом", {"height_min": 4.5, "width_min": 6.0}, "м", "сельхоздороги", "СНиП-мосты-2")
N("bridges.rail_grade_separation_placement", "Размещение пересечений с ж/д в разных уровнях", "I–II категорий — вне населённых пунктов; III–IV — вне жилых и общественно-деловых зон", "текст", "ж/д", "С08-6")

# ============================ trees and utilities =============================================
N("trees.distance_to_structures_m", "Деревья и кустарники до сооружений (ствол / куст, табл. 9.2)", {"building_wall": [5.0, 1.5], "sidewalk_edge": [0.7, 0.5], "carriageway_edge": [2.0, 1.0], "lighting_mast_bridge_pier": [4.0, None], "tram_track": [5.0, 3.0], "gas_sewer": [1.5, None], "heating": [2.0, 1.0], "water": [2.0, None], "cables": [2.0, 0.7]}, "м", "кроны ≤ 5 м", "С08-7", "табл. 9.2")
N("utilities.to_foundations_m", "Подземные сети до фундаментов (табл. 12.5)", {"water_pressure_sewer": 5, "gravity_sewer": 3, "gas_low": 2, "gas_medium": 4, "gas_high": R(7, 10), "heating_channel": 2, "heating_channelless": 5, "cables": 0.6}, "м", "сети", "С08-15", "табл. 12.5")
N("utilities.power_line_protection_zone_m", "Охранная зона воздушной ЛЭП (по обе стороны от проекции крайних проводов)",
  {"up_to_1kV_bare": 2, "up_to_1kV_insulated": 1, "1-20kV": 10, "35kV": 15, "110kV": 20, "220kV": 25, "330-500kV": 30, "1150kV": 55}, "м",
  "здания (п. 17, 20: застройка зоны не допускается, строения — только по согласованию с сетевой организацией) и деревья (п. 18: просеки вдоль ВЛ в зелёных насаждениях населённого пункта) (правила 4 и 19)",
  "ОЗЭС330", "п. 10, 11", also=[("ОЗЭС330", "п. 17, 18, 20")],
  note="ширина задана как «не менее» от проекции крайнего провода; ось линии в данных — без смещения крайнего провода. Напряжение линий OSM слоя infrastructure не известно: валидатор берёт наименьший класс ВЛ (power_line — 35 кВ, minor_line — 1–20 кВ), пока спецификация не задаст kv")
N("utilities.gas_pipeline_protection_zone_m", "Охранная зона газопровода", None, "м", "здания и деревья (правило 4)", "R2", status="not_verified", note="в research нет; до ввода числа — предупреждение")
N("utilities.noise_limits_dba", "Предельные уровни шума у фасадов", None, "дБА", "жильё у магистралей", "С08-18", status="not_verified", note="ссылки на МСН 2.04-03-2005 и ДСМ-15, чисел нет")

# ============================ validator tolerances (plan rules) ===============================
N("validator.levels", "Уровни карты занятости", [-1, 0, 1], "уровень", "−1 подземные паркинги, тоннели, подземные переходы; 0 поверхность; +1 мосты, путепроводы, эстакады", "PLAN", "«Чего быть не должно»")
N("validator.occupancy_overlap_max_m2", "Пересечение контуров в одном уровне", 1, "м² (больше — ошибка)", "все контуры", "PLAN", "правило 1")
N("validator.occupancy_exceptions", "Исключения карты занятости", {"sidewalk_carriageway": "только в полосе перехода", "sidewalk_driveway_max_width_m": 6, "lrt_street": "только в узле-переезде со светофором", "stacked_levels": "верхний — мост, путепровод или эстакада, и выполнено правило 9"}, "текст / м", "правило 1", "PLAN", "правило 1")
N("validator.zone_purposes", "Назначения земли", ["улица", "квартал", "парк", "вода", "инженерный коридор", "резерв с подписью"], "список", "каждая точка внутри границы района", "PLAN", "правило 2")
N("validator.grading", "Отметки планировки", {"cut_fill_max_m": 1.5, "building_base_max_diff_m": 0.3, "plinth_or_terrace_if_slope_over_pct": 5}, "м / %", "каждый участок и здание", "PLAN", "правило 3")
N("validator.water_building_exceptions", "Здания, которым можно стоять у воды", ["причалы", "марина", "пляжные павильоны"], "список", "правило 4", "PLAN", "правило 4")
N("validator.dead_end_allowed_classes", "Тупик допускается", {"classes": ["driveway_main", "driveway_secondary", "local", "local_secondary", "village_lane"], "max_length_key": "fire_access.dead_end_max_m", "turnaround_key": "fire_access.turnaround_min_m"}, "классы", "правило 5", "PLAN", "правило 5")
N("validator.identical_models", "Одинаковые дома рядом", {"radius_m": 200, "max_same_model": 2, "exempt": ["типовые школы и сады", "панели СЭС", "склады", "существующие дома"], "facade_repeat_max_m": 60}, "м / шт.", "жилые и офисные здания", "PLAN", "правило 18")
N("validator.unity_counter_max", "Счётчики Unity", 0, "шт.", "машины вне полос и мест; люди вне тротуаров, площадей и парков", "PLAN", "правила 21–22")
N("validator.years", "Годы проверки", [2026, 2030, 2034, 2040, 2050], "год", "правила 1–13 и 15–22 (для того, что в этом году уже стоит)", "PLAN", "«Когда и как проверяем»")
N("validator.scenarios", "Сценарии", ["Base", "Fast", "Slow", "InfraFirst"], "сценарий", "правило 23 (каждый сценарий со сдвигом лет); прогоны Unity", "TWIN", "enum Scenario { Base, Fast, Slow, InfraFirst }", also=[("PLAN", "«в каждом из четырёх сценариев»")])
N("validator.existing_object_year", "Год существующих объектов", 2025, "год", "дома и заводы из OSM, факты реестра и улицы к ним — во всех сценариях", "PLAN", "«Когда и как проверяем»")
N("validator.order_4d", "4D-порядок", ["земля", "каркас", "фасад", "благоустройство"], "порядок", "правило 23", "PLAN", "правило 23")
N("validator.district_numbers_tolerance_pct", "Числа района против цели", 5, "% (±)", "жители, места, рабочие места района", "PLAN", "правило 24")
N("validator.panel_vs_data_tolerance", "Панель и данные", 0, "разница (совпадают точно)", "все панели", "PLAN", "правило 24")
N("validator.neighbour_wait", "«Ждёт соседа»", {"alone": "warning", "level_3": "error"}, "уровень серьёзности", "проверки, которым нужен сосед (обслуживание через границу, стыки улиц)", "PLAN", "«Когда и как проверяем»")
N("validator.analogue_policy", "Числа по аналогу", "предупреждение; не останавливает приёмку, каждое отдельной строкой в «было/стало», владелец принимает явно", "текст", "status = analogue / not_verified", "PLAN", "«Что достраиваем по нормам», последний абзац")

# ============================ registry accuracy (tester prompt, point 2) =====================
N("registry_tol.point_m", "Допуск точки", 50, "м", "accuracy = point_50m", "PLAN", "«Промпт тестеру», п. 2")
N("registry_tol.road_km_m", "Допуск километра трассы", 500, "м вдоль оси, правильная сторона трассы", "accuracy = road_km_500m", "PLAN", "«Промпт тестеру», п. 2")
N("registry_tol.settlement_m", "Допуск села или микрорайона", 1000, "м (внутри полигона или не дальше)", "accuracy = settlement_1km", "PLAN", "«Промпт тестеру», п. 2")
N("registry_tol.district_only", "Только район", "внутри района по правилу зоны", "текст", "accuracy = district_only", "PLAN", "«Промпт тестеру», п. 2")
N("registry_tol.moved_reference", "Сдвинутый объект", "эталон — новое место по утверждённому «было/стало»", "текст", "action = move", "PLAN", "«Промпт тестеру», п. 2")

# =============================================================================================
# road classes, street profiles, node types and the node-type matrix
# =============================================================================================
ROAD_CLASSES = collections.OrderedDict([
    # id: (ru, С08 category or other basis, plan class, node group)
    ("expressway", ("Скоростная дорога (А-3, БАКАД, IA)", "С08 табл. 11.5: магистральная дорога скоростного движения; вне города — СП303 I-а / I-б", "скоростная", "expressway")),
    ("arterial_road_regulated", ("Магистральная дорога регулируемого движения", "С08 табл. 11.5", "магистраль", "arterial_regulated")),
    ("arterial_continuous", ("Магистральная улица общегородского значения непрерывного движения", "С08 табл. 11.5", "магистраль", "arterial_continuous")),
    ("arterial_regulated", ("Магистральная улица общегородского значения регулируемого движения", "С08 табл. 11.5", "магистраль", "arterial_regulated")),
    ("district_transport", ("Магистральная улица районного значения транспортно-пешеходная", "С08 табл. 11.5; СП РК по Астана23", "районная", "district")),
    ("district_pedestrian", ("Магистральная улица районного значения пешеходно-транспортная", "С08 табл. 11.5", "районная", "district")),
    ("local", ("Улица в жилой застройке", "С08 табл. 11.5; СП РК по Астана23", "местная", "local")),
    ("local_secondary", ("Улица в жилой застройке второстепенная", "С08 табл. 11.5", "местная", "local")),
    ("industrial", ("Улица / дорога промышленных и коммунально-складских районов", "С08 табл. 11.5", "местная", "industrial")),
    ("park_road", ("Парковая дорога", "С08 табл. 11.5", "местная", "local")),
    ("driveway_main", ("Проезд основной", "С08 табл. 11.5", "проезд", "driveway")),
    ("driveway_secondary", ("Проезд второстепенный", "С08 табл. 11.5", "проезд", "driveway")),
    ("village_main", ("Поселковая улица в жилой застройке основная", "СП РК 3.01-101-2013 табл. 5-3 по проекту Каражар", "местная", "local")),
    ("village_secondary", ("Поселковая улица в жилой застройке второстепенная", "СП РК 3.01-101-2013 табл. 5-3 по проекту Каражар", "местная", "local")),
    ("village_lane", ("Поселковый проезд", "СП РК 3.01-101-2013 табл. 5-3 по проекту Каражар", "проезд", "driveway")),
    ("pedestrian_street", ("Пешеходная улица", "С08 табл. 11.5", "пешеходная улица", "pedestrian")),
    ("boulevard", ("Бульвар (зелёная полоса вдоль улицы своего класса)", "С08 р. 9 (бульвары)", "бульвар", "по классу проезжей части")),
    ("bike_path", ("Велодорожка", "С08 табл. 11.5", "велодорожка", "bike")),
    ("ramp", ("Съезд развязки", "СП303", "съезд", "ramp")),
])

NA = None
# class: field -> (value, unit, src, clause, status_override, note)
T115 = "табл. 11.5"
SP = collections.OrderedDict()
SP["expressway"] = {
    "speed_kmh": (120, "км/ч", "С08-10", T115), "lane_width_m": (3.75, "м", "С08-10", T115), "lanes": (R(4, 8), "полос", "С08-10", T115),
    "carriageways": (2, "шт.", "СП303", "разделительная полоса I-а"), "median_m": ({"no_barrier_min": 6.0, "with_barrier_min": "2,0 + ограждение", "safety_strip": 1.0}, "м", "СП303", None, None, "I-а; I-б — 5 м без ограждения"),
    "r_min_m": (600, "м", "С08-10", T115), "slope_max_permille": (30, "‰", "С08-10", T115),
    "sidewalk_m": (0, "м", "С08-10", T115, None, "тротуаров нет (правило 10)"), "red_lines_m": (R(50, 75), "м", "С08-10", None),
    "green_strip_m": ({"housing_side_min": 10}, "м", "С08-6", None, None, "зелёная полоса со стороны жилья (дороги I–III)"),
    "bike": ("нет на проезжей части", "текст", "PLAN", "правило 10"),
    "shoulder_m": (3.75, "м", "СП303", None, None, "обочина I–II категорий"),
}
SP["arterial_road_regulated"] = {
    "speed_kmh": (80, "км/ч", "С08-10", T115), "lane_width_m": (3.5, "м", "С08-10", T115), "lanes": (R(2, 6), "полос", "С08-10", T115),
    "carriageways": ({"lanes_lt_4": 1, "lanes_ge_4": 2}, "шт.", "PLAN", "правило 11", None, "разделитель при 4+ полосах — правило проекта"),
    "median_m": ({"min": 2.0, "note": "с ограждением ≥ 2 м + ограждение"}, "м", "СП303", None, "analogue", "загородная норма применена к городу"),
    "r_min_m": (400, "м", "С08-10", T115), "slope_max_permille": (50, "‰", "С08-10", T115),
    "sidewalk_m": (0, "м", "С08-10", T115, None, "тротуаров нет (правило 10)"), "red_lines_m": (R(50, 75), "м", "С08-10", None),
    "green_strip_m": (2.7, "м", "С08-7", "табл. 9.2", None, "газон с деревьями [выч.]"), "bike": ("обособленная велодорожка вне проезжей части", "текст", "ITDP", None),
    "bus_lane_m": (4.0, "м", "С08-10", None), "curb_radius_m": (8, "м", "С08-9", "п. 11.10"),
}
SP["arterial_continuous"] = {
    "speed_kmh": (100, "км/ч", "С08-10", T115), "lane_width_m": (3.75, "м", "С08-10", T115), "lanes": (R(4, 8), "полос", "С08-10", T115),
    "carriageways": (2, "шт.", "PLAN", "правило 11"), "median_m": ({"no_barrier_min": 5.0, "with_barrier_min": "2,0 + ограждение"}, "м", "СП303", None, "analogue", "как I-б; городской нормы в research нет"),
    "r_min_m": (500, "м", "С08-10", T115), "slope_max_permille": (40, "‰", "С08-10", T115),
    "sidewalk_m": (4.5, "м", "С08-10", T115), "red_lines_m": (R(40, 80), "м", "С08-10", None),
    "green_strip_m": (2.7, "м", "С08-7", "табл. 9.2", None, "газон с деревьями [выч.]"), "bike": ("обособленная велодорожка (скорость авто > 30 км/ч)", "текст", "ITDP", None),
    "bus_lane_m": (4.0, "м", "С08-10", None),
}
SP["arterial_regulated"] = {
    "speed_kmh": (80, "км/ч", "С08-10", T115), "lane_width_m": (3.5, "м", "С08-10", T115), "lanes": (R(4, 8), "полос", "С08-10", T115),
    "carriageways": (2, "шт.", "PLAN", "правило 11", None, "4+ полос — разделительная полоса"), "median_m": ({"min": 2.0, "note": "с ограждением ≥ 2 м + ограждение"}, "м", "СП303", None, "analogue", "загородная норма применена к городу"),
    "r_min_m": (400, "м", "С08-10", T115), "slope_max_permille": (50, "‰", "С08-10", T115),
    "sidewalk_m": (3.0, "м", "С08-10", T115), "red_lines_m": (R(40, 80), "м", "С08-10", None),
    "green_strip_m": (2.7, "м", "С08-7", "табл. 9.2", None, "газон с деревьями [выч.]"), "bike": ("обособленная велодорожка; велополоса ≥ 1,2 м допустима", "текст", "ITDP", None),
    "bus_lane_m": (4.0, "м", "С08-10", None), "curb_radius_m": ({"default": 8, "constrained_min": 6}, "м", "С08-9", "п. 11.10"),
}
SP["district_transport"] = {
    "speed_kmh": (60, "км/ч", "Астана23", "СП РК 3.01-101-2013", None, "С08: 70 км/ч; берём действующий СП РК"),
    "lane_width_m": ({"design": 3.75, "min": 3.5}, "м", "Астана23", "СП РК 3.01-101-2013", None, "СП РК 3,75–4,0; С08 3,5 — минимум"),
    "lanes": (R(2, 6), "полос", "С08-10", T115, None, "С08 2–4; СП РК 4–6"), "carriageways": (1, "шт.", "PLAN", "правило 11"),
    "median_m": (0, "м", "PLAN", "правило 11", None, "одна проезжая часть, разделитель не требуется"),
    "r_min_m": (250, "м", "С08-10", T115), "slope_max_permille": (54, "‰", "Астана23", "СП РК 3.01-101-2013", None, "С08: 60 ‰; берём строже"),
    "sidewalk_m": (3.0, "м", "Астана23", "СП РК 3.01-101-2013", None, "С08: 2,25 м; берём шире"), "red_lines_m": (R(40, 80), "м", "С08-10", None),
    "green_strip_m": (2.7, "м", "С08-7", "табл. 9.2", None, "газон с деревьями [выч.]"), "bike": ("обособленная велодорожка (скорость авто > 30 км/ч)", "текст", "ITDP", None),
    "bus_lane_m": (4.0, "м", "С08-10", None), "curb_radius_m": (8, "м", "С08-9", "п. 11.10"),
}
SP["district_pedestrian"] = {
    "speed_kmh": (50, "км/ч", "С08-10", T115), "lane_width_m": (4.0, "м", "С08-10", T115), "lanes": (2, "полос", "С08-10", T115), "carriageways": (1, "шт.", "PLAN", "правило 11"),
    "median_m": (0, "м", "PLAN", "правило 11", None, "одна проезжая часть, разделитель не требуется"),
    "r_min_m": (125, "м", "С08-10", T115), "slope_max_permille": (40, "‰", "С08-10", T115), "sidewalk_m": (3.0, "м", "С08-10", T115), "red_lines_m": (R(40, 80), "м", "С08-10", None),
    "green_strip_m": (2.7, "м", "С08-7", "табл. 9.2", None, "газон с деревьями [выч.]"), "bike": ("велополоса ≥ 1,2 м или обособленная (50 км/ч > 30)", "текст", "ITDP", None),
    "curb_radius_m": (8, "м", "С08-9", "п. 11.10"),
}
SP["local"] = {
    "speed_kmh": (40, "км/ч", "С08-10", T115), "lane_width_m": (3.0, "м", "С08-10", T115), "lanes": ({"min": 2, "max": 3, "note": "одна — под стоянку"}, "полос", "С08-10", T115),
    "carriageways": (1, "шт.", "PLAN", "правило 11"), "median_m": (0, "м", "PLAN", "правило 11", None, "одна проезжая часть, разделитель не требуется"),
    "r_min_m": (90, "м", "С08-10", T115), "slope_max_permille": (70, "‰", "С08-10", T115), "sidewalk_m": (1.5, "м", "С08-10", T115), "red_lines_m": (R(15, 25), "м", "С08-10", None),
    "green_strip_m": (2.7, "м", "С08-7", "табл. 9.2", None, "при посадке деревьев [выч.]"), "bike": ("обособленная при 40 км/ч (> 30) или зона 30 с общей полосой", "текст", "ITDP", None),
    "curb_radius_m": (5, "м", "С08-9", "п. 11.10"),
}
SP["local_secondary"] = {
    "speed_kmh": (30, "км/ч", "С08-10", T115), "lane_width_m": (3.0, "м", "С08-10", T115), "lanes": (2, "полос", "С08-10", T115), "carriageways": (1, "шт.", "PLAN", "правило 11"),
    "r_min_m": (50, "м", "С08-10", T115), "slope_max_permille": (80, "‰", "С08-10", T115), "sidewalk_m": (1.5, "м", "С08-10", T115), "red_lines_m": (R(15, 25), "м", "С08-10", None),
    "bike": ("общая полоса с разметкой (15–30 км/ч)", "текст", "ITDP", None), "curb_radius_m": (5, "м", "С08-9", "п. 11.10"),
}
SP["industrial"] = {
    "speed_kmh": ({"design": 50, "alt": 40}, "км/ч", "С08-10", T115), "lane_width_m": (3.5, "м", "С08-10", T115), "lanes": (R(2, 4), "полос", "С08-10", T115), "carriageways": (1, "шт.", "PLAN", "правило 11"),
    "r_min_m": (90, "м", "С08-10", T115), "slope_max_permille": (60, "‰", "С08-10", T115), "sidewalk_m": (1.5, "м", "С08-10", T115), "red_lines_m": (R(15, 25), "м", "С08-10", None),
    "bike": ("обособленная велодорожка (50 км/ч > 30)", "текст", "ITDP", None),
    "curb_radius_m": (5, "м", "С08-9", "п. 11.10", None, "местная улица по С08; для грузовиков — по траектории, отдельного числа РК не найдено"),
}
SP["park_road"] = {
    "speed_kmh": (40, "км/ч", "С08-10", T115), "lane_width_m": (3.0, "м", "С08-10", T115), "lanes": (2, "полос", "С08-10", T115), "carriageways": (1, "шт.", "PLAN", "правило 11"),
    "r_min_m": (75, "м", "С08-10", T115), "slope_max_permille": (80, "‰", "С08-10", T115), "sidewalk_m": (0, "м", "С08-10", T115, None, "по таблице «–»"), "red_lines_m": (R(15, 25), "м", "С08-10", None),
    "curb_radius_m": (5, "м", "С08-9", "п. 11.10"),
}
SP["driveway_main"] = {
    "speed_kmh": (40, "км/ч", "С08-10", T115), "lane_width_m": (3.0, "м", "С08-10", T115), "lanes": (2, "полос", "С08-10", T115), "carriageways": (1, "шт.", "PLAN", "правило 11"),
    "r_min_m": (50, "м", "С08-10", T115), "slope_max_permille": (70, "‰", "С08-10", T115), "sidewalk_m": (1.0, "м", "С08-10", T115),
    "fire_width_min_m": (6, "м", "ТР405", None), "curb_radius_m": (6, "м", "Астана23", None, "analogue", "въезды 6 м шириной с R 6 м (проект РК)"),
}
SP["driveway_secondary"] = {
    "speed_kmh": (30, "км/ч", "С08-10", T115), "lane_width_m": (3.5, "м", "С08-10", T115), "lanes": (1, "полос", "С08-10", T115), "carriageways": (1, "шт.", "PLAN", "правило 11"),
    "r_min_m": (25, "м", "С08-10", T115), "slope_max_permille": (80, "‰", "С08-10", T115), "sidewalk_m": (0.75, "м", "С08-10", T115),
    "curb_radius_m": (6, "м", "Астана23", None, "analogue", "въезды 6 м шириной с R 6 м (проект РК)"),
}
SP["village_main"] = {
    "speed_kmh": (40, "км/ч", "Каражар", "табл. 5-3"), "lanes": (2, "полос", "Каражар", "табл. 5-3"), "lane_width_m": (3.0, "м", "Каражар", "табл. 5-3"), "carriageway_m": (6.0, "м", "Каражар", "табл. 5-3"),
    "sidewalk_m": (1.5, "м", "С08-10", T115, None, "как улица в жилой застройке"), "curb_radius_m": (5, "м", "С08-9", "п. 11.10"),
}
SP["village_secondary"] = {
    "speed_kmh": (30, "км/ч", "Каражар", "табл. 5-3"), "lanes": (2, "полос", "Каражар", "табл. 5-3"), "lane_width_m": (2.75, "м", "Каражар", "табл. 5-3"), "carriageway_m": (5.5, "м", "Каражар", "табл. 5-3"),
    "sidewalk_m": (1.5, "м", "С08-10", T115, None, "как улица в жилой застройке второстепенная"), "curb_radius_m": (5, "м", "С08-9", "п. 11.10"),
}
SP["village_lane"] = {
    "speed_kmh": (20, "км/ч", "Каражар", "табл. 5-3"), "lanes": (1, "полос", "Каражар", "табл. 5-3"), "lane_width_m": (3.0, "м", "Каражар", "табл. 5-3"), "carriageway_m": (3.0, "м", "Каражар", "табл. 5-3"),
}
SP["pedestrian_street"] = {
    "pedestrian_lane_m": ({"main": 1.0, "secondary": 0.75}, "м (полоса движения; число полос — по расчёту)", "С08-10", T115), "slope_max_permille": ({"main": 40, "secondary": 60}, "‰", "С08-10", T115),
    "width_examples_m": ({"pedestrian_streets": [18, 10], "lanes": R(8, 10), "commercial_shared": R(12, 14)}, "м", "GDCI-совм.", None),
    "through_traffic": (False, "bool", "PLAN", "«Улицы в красных линиях»: пешеходная улица без сквозного движения машин"),
    "ends_connected": ("на обоих концах связана с тротуарами или площадью", "текст", "PLAN", "правило 10"),
}
SP["boulevard"] = {
    "green_width_m": ({"on_axis_min": 18, "one_side_min": 10}, "м", "С08-7", None), "path_width_multiple_m": (0.75, "м", "С08-7", None),
    "carriageway": ("по классу улицы, вдоль которой идёт бульвар", "текст", "PLAN", "«Улицы в красных линиях»"),
    "ends_connected": ("на обоих концах связан с тротуарами или площадью", "текст", "PLAN", "правило 10"),
}
SP["bike_path"] = {
    "speed_kmh": ({"separated": 20, "isolated": 30}, "км/ч", "С08-10", T115), "lane_width_m": (1.5, "м", "С08-10", T115), "lanes": ({"separated": R(1, 2), "isolated": R(2, 4)}, "полос", "С08-10", T115),
    "r_min_m": ({"separated": 30, "isolated": 50}, "м", "С08-10", T115), "slope_max_permille": ({"separated": 40, "isolated": 30}, "‰", "С08-10", T115),
    "clearances_m": ({"to_carriageway_poles_trees": 0.75, "to_sidewalk": 0.5, "to_parking_stops": 1.5}, "м", "С08-9", None),
}
SP["ramp"] = {
    "speed_kmh": ({"from_I_II_min": 60, "from_III_min": 50}, "км/ч", "СП303", None), "width_m": ({"left_turn": 5.5, "right_turn": 5.0}, "м", "СП303", None),
    "shoulder_m": ({"inner": 1.5, "outer": 3.0}, "м", "СП303", None), "slope_max_permille": (40, "‰", "СП303", None),
    "sidewalk_m": (0, "м", "PLAN", "правило 10", None, "на съездах тротуаров нет"), "loop_radius_key": ("ramps.loop_radius_m", "ключ", "PLAN", "правило 7"),
}

PROFILE_KEYS = collections.OrderedDict()
for cls, fields in SP.items():
    PROFILE_KEYS[cls] = collections.OrderedDict()
    ru = ROAD_CLASSES[cls][0]
    for f, spec in fields.items():
        v, unit, src, clause = spec[:4]
        st = spec[4] if len(spec) > 4 else None
        note = spec[5] if len(spec) > 5 else None
        if v is None and st is None:
            st = KIND[SRC[src][3]][0]
        key = "street.%s.%s" % (cls, f)
        N(key, "%s: %s" % (ru, f), v, unit, ru, src, clause, status=st, note=note, derived=(f == "green_strip_m" and v == 2.7),
          plan="Улицы в красных линиях" if f in ("red_lines_m", "r_min_m") else None)
        PROFILE_KEYS[cls][f] = key

NODE_TYPES = collections.OrderedDict([
    ("crossing", ("Перекрёсток в одном уровне без светофора (приоритет, знаки)", "at_grade")),
    ("crossing_signal", ("Перекрёсток в одном уровне со светофором", "at_grade")),
    ("right_in_right_out", ("Правоповоротное примыкание (вход / выход)", "at_grade")),
    ("roundabout", ("Кольцевое пересечение (мини / однополосное / двухполосное)", "at_grade")),
    ("square", ("Транспортная площадь", "at_grade")),
    ("diamond", ("Ромб (включая одноточечный SPUI)", "grade_separated")),
    ("partial_cloverleaf", ("Неполный клеверный лист (ParClo)", "grade_separated")),
    ("cloverleaf", ("Клеверный лист (C-D дороги при переплетении > 1000 авт/ч)", "grade_separated")),
    ("trumpet", ("Труба (только трёхлучевой узел)", "grade_separated")),
    ("directional", ("Направленная / полунаправленная развязка", "grade_separated")),
    ("grade_separation", ("Пересечение в разных уровнях без съездов (путепровод / тоннель)", "grade_separated")),
])
AT = [k for k, v in NODE_TYPES.items() if v[1] == "at_grade"]
GS = [k for k, v in NODE_TYPES.items() if v[1] == "grade_separated"]
GROUPS = ["expressway", "arterial_continuous", "arterial_regulated", "district", "industrial", "local", "driveway"]
GROUP_RU = {"expressway": "скоростная (А-3, БАКАД, IA)", "arterial_continuous": "магистраль непрерывного движения", "arterial_regulated": "регулируемая магистраль (улица или дорога)",
            "district": "районная магистраль", "industrial": "промышленная улица", "local": "местная / жилая / парковая / поселковая улица", "driveway": "проезд"}
S_EXP = ["PLAN:«Узлы»: А-3, БАКАД, IA — только развязки в разных уровнях", "СП303:с дорогой I-а — всегда развязка", "WSDOT", "SCDOT"]
S_CONT = ["ДБН:все узлы магистралей непрерывного движения — в разных уровнях", "WSDOT", "SCDOT"]
S_ATG = ["ДБН", "normacs-4818", "NCHRP", "С08-5:въезды ≤ 200 м"]
LOCAL_BAN = "правило 8 плана: «клевер на местной улице» — развязка на местной улице или проезде не допускается"

# (a, b): allowed, preferred, conditions, at-grade ban severity+why, grade-separated ban severity+why, sources
M = [
    ("expressway", "expressway", ["cloverleaf", "directional", "trumpet", "grade_separation"], ["cloverleaf", "trumpet"],
     {"cloverleaf": "C-D дороги при переплетении > 1000 авт/ч", "directional": "высокие объёмы", "trumpet": "трёхлучевой узел"},
     ("error", "светофор, кольцо или перекрёсток на скоростной дороге (правило 8, «Узлы»)"), ("warning", "системный узел: ромб и ParClo — обслуживающие типы"), S_EXP + ["MoDOT"]),
    ("expressway", "arterial_continuous", ["cloverleaf", "directional", "trumpet", "grade_separation"], ["cloverleaf", "trumpet"],
     {"trumpet": "трёхлучевой узел"}, ("error", "узел в одном уровне на скоростной дороге"),
     ("warning", "ромб и ParClo выводят съезды перекрёстком на улицу, у которой перекрёстков в одном уровне нет"), S_EXP + S_CONT[:1]),
    ("expressway", "arterial_regulated", ["diamond", "partial_cloverleaf", "trumpet", "grade_separation"], ["diamond"],
     {"partial_cloverleaf": "левоповоротный поток ≥ 500 авт/ч", "trumpet": "трёхлучевой узел", "diamond": "съезды на улицу перекрёстком 70–110°"},
     ("error", "узел в одном уровне на скоростной дороге"), ("warning", "клевер и направленная — системные типы магистраль × магистраль"), S_EXP),
    ("expressway", "district", ["diamond", "partial_cloverleaf", "trumpet", "grade_separation"], ["diamond"],
     {"partial_cloverleaf": "левоповоротный поток ≥ 500 авт/ч", "trumpet": "трёхлучевой узел", "any": "только в местах развязок генплана, шаг ≥ 1,6 км"},
     ("error", "узел в одном уровне на скоростной дороге"), ("warning", "клевер и направленная — системные типы"), S_EXP),
    ("expressway", "industrial", ["diamond", "partial_cloverleaf", "trumpet", "grade_separation"], ["diamond", "trumpet"],
     {"any": "только в местах развязок генплана, шаг ≥ 1,6 км"}, ("error", "узел в одном уровне на скоростной дороге"), ("warning", "клевер и направленная — системные типы"), S_EXP),
    ("expressway", "local", ["grade_separation"], ["grade_separation"], {"grade_separation": "местная улица проходит под или над дорогой без съездов"},
     ("error", "узел в одном уровне на скоростной дороге"), ("error", LOCAL_BAN), S_EXP + ["PLAN:правило 8"]),
    ("expressway", "driveway", ["grade_separation"], ["grade_separation"], {}, ("error", "узел в одном уровне на скоростной дороге"), ("error", LOCAL_BAN), S_EXP + ["PLAN:правило 8"]),
    ("arterial_continuous", "arterial_continuous", ["cloverleaf", "directional", "trumpet", "grade_separation"], ["cloverleaf", "trumpet"],
     {"cloverleaf": "C-D при переплетении > 1000 авт/ч", "trumpet": "трёхлучевой узел", "spacing": "развязки через 800–1200 м (в центре ≥ 600 м)"},
     ("error", "класс «непрерывного движения» не имеет узлов в одном уровне"), ("warning", "ромб и ParClo ставят перекрёсток на непрерывную улицу"), S_CONT + ["MoDOT"]),
    ("arterial_continuous", "arterial_regulated", ["diamond", "partial_cloverleaf", "trumpet", "grade_separation"], ["diamond"],
     {"diamond": "перекрёстки ромба — на регулируемой магистрали", "partial_cloverleaf": "левый поворот ≥ 500 авт/ч", "trumpet": "трёхлучевой узел"},
     ("error", "узел в одном уровне на улице непрерывного движения"), ("warning", "клевер и направленная — системные типы"), S_CONT),
    ("arterial_continuous", "district", ["diamond", "partial_cloverleaf", "trumpet", "right_in_right_out", "grade_separation"], ["diamond"],
     {"right_in_right_out": "через переходно-скоростные полосы; ≥ 100 м от узла и ≥ 150 м одно от другого"},
     ("error", "перекрёсток, кольцо или площадь на улице непрерывного движения"), ("warning", "клевер и направленная — системные типы"), S_CONT),
    ("arterial_continuous", "industrial", ["diamond", "partial_cloverleaf", "trumpet", "right_in_right_out", "grade_separation"], ["diamond", "right_in_right_out"],
     {"right_in_right_out": "через переходно-скоростные полосы; ≥ 100 м от узла и ≥ 150 м одно от другого"},
     ("error", "перекрёсток, кольцо или площадь на улице непрерывного движения"), ("warning", "клевер и направленная — системные типы"), S_CONT),
    ("arterial_continuous", "local", ["right_in_right_out", "grade_separation"], ["right_in_right_out"],
     {"right_in_right_out": "через переходно-скоростные полосы; ≥ 100 м от узла и ≥ 150 м одно от другого"},
     ("error", "перекрёсток, кольцо или площадь на улице непрерывного движения"), ("error", LOCAL_BAN), S_CONT + ["PLAN:правило 8"]),
    ("arterial_continuous", "driveway", ["grade_separation"], ["grade_separation"], {"grade_separation": "проезд подключается к местной улице, а не к непрерывной"},
     ("error", "узел в одном уровне на улице непрерывного движения"), ("error", LOCAL_BAN), S_CONT + ["PLAN:правило 8"]),
    ("arterial_regulated", "arterial_regulated", ["crossing_signal", "roundabout", "square", "diamond", "partial_cloverleaf", "trumpet", "grade_separation"], ["crossing_signal"],
     {"roundabout": "сопоставимые потоки; вход + конфликт < 1800 авт/ч; не больше 4 полос по кругу", "square": "5+ лучей",
      "diamond": "> 6000 авт/ч на подходах или левый поворот > 600 авт/ч", "partial_cloverleaf": "то же; петля при левом ≥ 500 авт/ч", "trumpet": "трёхлучевой узел при тех же порогах",
      "spacing": "пересечения через 300–800 м"},
     ("warning", "нерегулируемый перекрёсток двух магистралей — против правила R2"), ("warning", "клевер и направленная — системные типы"), S_ATG + ["R2"]),
    ("arterial_regulated", "district", ["crossing_signal", "roundabout", "square", "right_in_right_out", "diamond", "grade_separation"], ["crossing_signal"],
     {"roundabout": "сопоставимые потоки, < 1800 авт/ч", "diamond": "> 6000 авт/ч на подходах или левый поворот > 600 авт/ч", "right_in_right_out": "≥ 100 м от узла, ≥ 150 м одно от другого"},
     ("warning", "нерегулируемый полный перекрёсток с магистралью"), ("warning", "районные магистрали пересекаются в одном уровне (normacs-4818)"), S_ATG + ["R2"]),
    ("arterial_regulated", "industrial", ["crossing_signal", "roundabout", "right_in_right_out", "grade_separation"], ["crossing_signal"],
     {"roundabout": "сопоставимые потоки"}, ("warning", "нерегулируемый полный перекрёсток с магистралью"), ("warning", "развязка на промышленной улице не нужна"), S_ATG),
    ("arterial_regulated", "local", ["crossing_signal", "right_in_right_out", "grade_separation"], ["right_in_right_out", "crossing_signal"],
     {"crossing_signal": "примыкание местных улиц через 300–400 м, обычно на регулируемых перекрёстках", "right_in_right_out": "≥ 100 м от узла, ≥ 150 м одно от другого"},
     ("warning", "нерегулируемый полный перекрёсток или кольцо при резко неравных потоках"), ("error", LOCAL_BAN), S_ATG + ["PLAN:правило 8"]),
    ("arterial_regulated", "driveway", ["right_in_right_out", "grade_separation"], ["right_in_right_out"], {"right_in_right_out": "въезд в квартал; ≥ 100 м от узла"},
     ("warning", "полный перекрёсток проезда с магистралью"), ("error", LOCAL_BAN), S_ATG + ["PLAN:правило 8"]),
    ("district", "district", ["crossing_signal", "crossing", "roundabout", "square"], ["crossing_signal", "roundabout"],
     {"roundabout": "сопоставимые потоки", "square": "5+ лучей"}, ("warning", "—"), ("warning", "районные магистрали пересекаются в одном уровне (normacs-4818)"), S_ATG),
    ("district", "industrial", ["crossing_signal", "crossing", "roundabout"], ["crossing"], {}, ("warning", "—"), ("warning", "развязка на районной улице не нужна"), S_ATG),
    ("district", "local", ["crossing", "crossing_signal", "roundabout"], ["crossing"], {"roundabout": "мини / однополосное"}, ("warning", "—"), ("error", LOCAL_BAN), S_ATG + ["PLAN:правило 8"]),
    ("district", "driveway", ["crossing", "right_in_right_out"], ["crossing"], {"crossing": "въезды в квартал не реже чем через 200 м"}, ("warning", "—"), ("error", LOCAL_BAN), S_ATG + ["PLAN:правило 8"]),
    ("industrial", "industrial", ["crossing", "crossing_signal", "roundabout"], ["crossing"], {}, ("warning", "—"), ("warning", "развязка на промышленной улице не нужна"), S_ATG),
    ("industrial", "local", ["crossing", "roundabout"], ["crossing"], {}, ("warning", "—"), ("error", LOCAL_BAN), S_ATG + ["PLAN:правило 8"]),
    ("industrial", "driveway", ["crossing"], ["crossing"], {}, ("warning", "—"), ("error", LOCAL_BAN), S_ATG + ["PLAN:правило 8"]),
    ("local", "local", ["crossing", "roundabout", "square"], ["crossing"], {"roundabout": "мини-кольцо 14–27 м", "square": "5+ лучей"}, ("warning", "светофор на местной улице не нужен"), ("error", LOCAL_BAN), S_ATG + ["PLAN:правило 8"]),
    ("local", "driveway", ["crossing"], ["crossing"], {}, ("warning", "—"), ("error", LOCAL_BAN), S_ATG + ["PLAN:правило 8"]),
    ("driveway", "driveway", ["crossing"], ["crossing"], {}, ("warning", "—"), ("error", LOCAL_BAN), S_ATG + ["PLAN:правило 8"]),
]


def matrix():
    cells = []
    seen = set()
    for a, b, allowed, pref, cond, ban_at, ban_gs, srcs in M:
        pair = tuple(sorted((GROUPS.index(a), GROUPS.index(b))))
        if pair in seen:
            raise SystemExit("matrix pair twice: %s %s" % (a, b))
        seen.add(pair)
        for t in allowed + pref + [k for k in cond if k in NODE_TYPES]:
            if t not in NODE_TYPES:
                raise SystemExit("unknown node type " + t)
        if not set(pref) <= set(allowed):
            raise SystemExit("preferred not allowed: %s %s" % (a, b))
        src = []
        for s in srcs:
            lab, _, cl = s.partition(":")
            src.append(_src(lab, cl or None))
        fa = [t for t in AT if t not in allowed]
        fg = [t for t in GS if t not in allowed]
        cells.append(collections.OrderedDict([
            ("a", a), ("b", b), ("allowed", allowed), ("preferred", pref), ("conditions", cond),
            ("forbidden_at_grade", {"types": fa, "severity": ban_at[0], "why": ban_at[1]} if fa else None),
            ("forbidden_grade_separated", {"types": fg, "severity": ban_gs[0], "why": ban_gs[1]} if fg else None),
            ("status", "analogue"), ("basis", "синтез w35 по источникам ячейки; запреты с severity error опираются на план или норму РК"),
            ("source", src)]))
    n = len(GROUPS)
    if len(seen) != n * (n + 1) // 2:
        raise SystemExit("node matrix incomplete: %d of %d pairs" % (len(seen), n * (n + 1) // 2))
    return cells


CROSSING_MATRIX = [
    {"a": "lrt_at_grade", "b": ["expressway", "arterial_continuous"], "allowed": ["grade_separation"], "severity": "error",
     "why": "на скоростных и непрерывных узлов в одном уровне нет; ЛРТ и улица в одном уровне — только в узле-переезде со светофором", "source": [_src("PLAN", "правило 1"), _src("ДБН", None)], "status": "norm"},
    {"a": "lrt_at_grade", "b": ["arterial_regulated", "district", "industrial", "local", "driveway"], "allowed": ["level_crossing_signal", "grade_separation"], "severity": "error",
     "why": "ЛРТ на земле и улица только в узле-переезде со светофором", "source": [_src("PLAN", "правило 1")], "status": "norm"},
    {"a": "lrt_at_grade", "b": ["pedestrian"], "allowed": ["grade_separation", "level_crossing_signal"], "severity": "warning",
     "why": "внеуличные переходы через 400–800 м на линиях скоростного трамвая; в одном уровне — только в регулируемом узле с улицей", "source": [_src("С08-11", "п. 11.13")], "status": "norm"},
    {"a": "rail", "b": ["expressway", "arterial_continuous", "arterial_regulated", "district", "industrial", "local", "driveway"], "allowed": ["grade_separation"], "severity": "error",
     "why": "нормы РК о переездах в городе в research нет; правило w35: новые пересечения с ж/д — в разных уровнях (как путепровод 950 м у Жетыгена) — ошибка правила 6; существующие переезды 2025 остаются как в OSM — предупреждение", "source": [_src("С08-6", None)], "status": "not_verified"},
    {"a": "pedestrian", "b": ["expressway"], "allowed": ["grade_separation"], "severity": "error",
     "why": "на I-а — только в разных уровнях; на скоростных дорогах внеуличные переходы через 400–800 м", "source": [_src("СП303", "табл. 16"), _src("С08-11", "п. 11.13")], "status": "norm"},
    {"a": "pedestrian", "b": ["arterial_continuous"], "allowed": ["grade_separation"], "severity": "error", "why": "внеуличные переходы через 300–400 м", "source": [_src("С08-11", "п. 11.13")], "status": "norm"},
    {"a": "pedestrian", "b": ["arterial_regulated"], "allowed": ["at_grade_crossing", "grade_separation"], "severity": "error",
     "why": "в одном уровне через 200–300 м; внеуличный — при потоке > 3000 пеш/ч", "source": [_src("С08-11", "п. 11.13")], "status": "norm"},
    {"a": "pedestrian", "b": ["district", "industrial", "local", "driveway"], "allowed": ["at_grade_crossing"], "severity": "error",
     "why": "переход в каждом узле в одном уровне (правило 10)", "source": [_src("PLAN", "правило 10")], "status": "norm"},
]

GAPS = [
    ("bridges.rail_clearance_m", "габарит над ж/д (ГОСТ 9238) — открытого текста с числом нет; 6,4 м (габарит С) — модель qTwin"),
    ("bridges.navigable_clearance_m", "габарит над судоходной рекой (ГОСТ 26775) — числа нет"),
    ("malls.parking_office", "парковка офисов — единица прил. 8 неоднозначна, аналога с числом нет"),
    ("malls.parking_mall", "парковка ТРЦ — единица прил. 8 неясна, аналога с числом нет"),
    ("lrt.platform_length_m", "длина платформы LRT Алатау — только аналог Metro Lite ≥ 33 м"),
    ("intersections.signal_warrants", "критерии установки светофора — не найдены"),
    ("utilities.gas_pipeline_protection_zone_m", "охранная зона газопровода — числа нет"),
    ("utilities.noise_limits_dba", "уровни шума у фасадов — числа нет"),
    ("flood.water_code_bans", "запреты ст. 86 Водного кодекса — текст не получен"),
    ("szz.cemetery_to_school_hospital_m", "кладбище до школы — 300 м, выравнивание столбцов под вопросом"),
    ("parking.other_appendix8", "прочее прил. 8 — единицы неоднозначны"),
    ("residential.parking_2025_change", "нормы парковок 2025 — номер документа и число для эконом-класса не названы"),
]

# =============================================================================================
# rules: curated metadata; text is read from plan.md
# =============================================================================================
YEARS = [2026, 2030, 2034, 2040, 2050]
SCEN = ["Base", "Fast", "Slow", "InfraFirst"]
W_STD = {"years": YEARS, "scope": "для того, что в этом году уже стоит", "scenarios": None,
         "scenarios_note": "план не называет сценарий для этих правил; годы объектов берутся по сценарию Base, если оркестратор не задаст иначе (w35)"}
W_UNITY = {"years": YEARS, "scope": "прогон Unity по годам", "scenarios": SCEN, "scenarios_note": "логи прогона лет в четырёх сценариях («Промпт тестеру», п. 1 и логи прогона)"}
NB = {"case": "«ждёт соседа»: район проверяется один, проверке нужен сосед", "severity": "warning", "becomes_error": "уровень 3"}
EX = {"case": "существующие (2025) здания и дороги: как в OSM, сверяются с источником", "severity": "warning", "becomes_error": "никогда: существующее не перепроектируется"}
AN = {"case": "число из norms.json со status analogue / not_verified", "severity": "warning", "becomes_error": "после явного «ок» владельца число становится нормой проекта"}

RULES = {
    1: dict(group="land", sev={"default": "error", "warnings": []}, when=W_STD, by=["validator"],
            params=["validator.levels", "validator.occupancy_overlap_max_m2", "validator.occupancy_exceptions", "lrt.at_grade_crossing", "bridges.road_clearance_m"],
            how="Растеризует или пересекает полигоны всех слоёв в карте занятости по уровням −1/0/+1 и сообщает каждую пару с пересечением > 1 м² в одном уровне, кроме перечисленных исключений; наложение разных уровней принимает только для моста/путепровода/эстакады с выполненным правилом 9. ЛРТ на земле и дорога: наложение принимается у узла дороги в 30 м (узел-переезд со светофором, gen_network ставит его на пересечении); дорогу класса, где переезд не допускается (crossing_matrix lrt_at_grade: скоростная, непрерывная, съезд), сообщает правило 6, а не 1."),
    2: dict(group="land", sev={"default": "error", "warnings": []}, when=W_STD, by=["validator"], params=["validator.zone_purposes"],
            how="Вычитает из полигона района объединение всех зон с назначением и сообщает каждый остаток (с координатами центроида) как «безымянную землю»; резерв засчитывается только с подписью."),
    3: dict(group="land", sev={"default": "error", "warnings": []}, when=W_STD, by=["validator"], params=["validator.grading", "validator.levels"],
            how="Сравнивает отметку планировки каждого участка с DEM (подсыпка/срезка ≤ 1,5 м), низ каждого здания с отметкой участка (≤ 0,3 м), требует цоколь/террасу при уклоне > 5 %, проверяет, что объекты уровня −1 ниже рельефа, кроме входов и порталов, и что опоры стоят на земле."),
    4: dict(group="land", sev={"default": "error", "warnings": [{"case": "ширина охранной зоны ЛЭП или газопровода не задана (status not_verified)", "severity": "warning", "becomes_error": "когда число введено в norms.json"}, EX]}, when=W_STD, by=["validator"],
            params=["flood.design_flood_pct", "flood.freeboard_m", "flood.water_protection_strip_min_m", "flood.floodplain_allowed", "flood.road_in_floodplain", "validator.water_building_exceptions", "flood.kapchagay_levels_m",
                    "utilities.power_line_protection_zone_m", "utilities.gas_pipeline_protection_zone_m"],
            how="Пересекает здания с водой, буфером водоохранной полосы и зоной ниже паводка 1 % + 0,5 м (кроме причалов, марины, пляжных павильонов); дороги в воде/пойме допускает только как мост или дамбу выше этой отметки; здания и деревья в коридорах ЛЭП и газопроводов — ошибка, дорога может пересекать коридор, но не идти вдоль внутри; существующие (2025) здания и дороги сверяются с источником, не перепроектируются — предупреждение «как в OSM»."),
    5: dict(group="roads", sev={"default": "error", "warnings": [NB, EX]}, when=W_STD, by=["validator"],
            params=["fire_access.dead_end_max_m", "fire_access.turnaround_min_m", "validator.dead_end_allowed_classes", "validator.neighbour_wait"],
            how="Строит граф дорог в каждом году проверки и в каждом году между ними, где сеть меняется (тупик на один год тоже тупик), и проверяет каждый висячий конец: узел с другой дорогой, стык на границе района из spec/city.json (без соседа — «ждёт соседа») или граница города; иначе тупик допускается только для проезда или местной улицы ≤ 150 м с площадкой ≥ 15 × 15 м. Тупиковая ветвь улицы без зданий (ни дома в 25 м, ни участка с назначением, ни проезда с неё) — предупреждение «дорога никуда»; участок с назначением засчитывается и без зданий (объект реестра, сооружение, любое назначение кроме резерва без подписи)."),
    6: dict(group="roads", sev={"default": "error", "warnings": [{"case": "существующий переезд 2025 через ж/д (как в OSM)", "severity": "warning", "becomes_error": None},
                                                               {"case": "узел 5+ лучей, все лучи — существующие дороги 2025 (как в OSM)", "severity": "warning", "becomes_error": "хотя бы один луч новый"}]}, when=W_STD, by=["validator"],
            params=["intersections.max_legs_without_ring", "bridges.road_clearance_m", "@node_types", "@crossing_matrix"],
            how="Находит все геометрические пересечения осей в одном уровне и требует на каждом узел; пересечение без узла принимает только как путепровод с разницей отметок ≥ габарита; узлы с 5+ лучами принимает только типа roundabout или square (узел, все лучи которого — существующие дороги 2025, — предупреждение «как в OSM»). Пересечение дороги с путём ж/д (osm/rail.geojson, без тоннелей и заброшенных) — только в разных уровнях (путепровод, мост или тоннель дороги, или путь на мосту): новая дорога в одном уровне — ошибка, существующий переезд 2025 — предупреждение «как в OSM». ЛРТ на земле, пересекающая в одном уровне дорогу, где переезд не допускается (crossing_matrix lrt_at_grade: скоростная, непрерывная; съезд), — ошибка: нужна эстакада или тоннель."),
    7: dict(group="roads", sev={"default": "error", "warnings": [AN]}, when=W_STD, by=["validator"],
            params=["ramps.merge_angle_max_deg", "ramps.merge_gap_m", "ramps.secondary_terminal_angle_deg", "ramps.loop_radius_m", "ramps.speed_change_lanes_kz_m", "ramps.deceleration_lane_kz_m", "interchanges.compressed_cloverleaf_r30"],
            how="Для каждого съезда проверяет, что оба конца — узлы; у скоростной/непрерывной дороги угол примыкания ≤ 4°, зазор 0 и есть переходно-скоростная полоса; съезд ромба/ParClo выходит на второстепенную дорогу под углом 70–110°; радиус петли по таблице; замкнутый круг вместо петли — ошибка. Радиусы петель — аналог (MoDOT): нарушение — предупреждение."),
    8: dict(group="roads", sev={"default": "error", "warnings": [{"case": "запрещённый тип в ячейке матрицы с severity warning (аналог)", "severity": "warning", "becomes_error": "после явного «ок» владельца"}]}, when=W_STD, by=["validator"],
            params=["@node_matrix", "@road_classes", "@node_types", "interchanges.spacing_expressway_m", "intersections.interchange_spacing_continuous_m", "intersections.at_grade_spacing_arterial_m", "interchanges.genplan_counts"],
            how="Для каждого узла берёт классы двух главных дорог, находит ячейку node_matrix и сверяет тип узла со списком allowed; тип из forbidden_* даёт ошибку или предупреждение по severity ячейки; дополнительно проверяет шаг развязок вдоль А-3/БАКАД/IA (≥ 1,6 км, иначе — только с параллельными съездами)."),
    9: dict(group="roads", sev={"default": "error", "warnings": [{"case": "габарит над судоходной рекой (status not_verified, числа нет)", "severity": "warning", "becomes_error": "когда число введено в norms.json"},
                                                              {"case": "дефект только существующих дорог 2025 (мост OSM, не доходящий до дороги в самом источнике)", "severity": "warning", "becomes_error": None}]}, when=W_STD, by=["validator"],
            params=["bridges.road_clearance_m", "bridges.river_clearance_m", "bridges.rail_clearance_m", "bridges.navigable_clearance_m", "flood.design_flood_pct", "lrt.viaduct_clearance_over_road_m"],
            how="Для каждого моста/эстакады сравнивает отметку низа пролёта с отметкой того, что под ним (дорога ≥ 5,0 м; река — расчётный паводок + запас по таблице; ж/д — по аналогу), проверяет, что концы выходят на насыпь, в станцию или в узел, и что пролёт не лежит на земле. Над путём ж/д (osm/rail.geojson, без тоннелей и заброшенных) низ пролёта ≥ габарита С 6,4 м (модель qTwin). Дефект, в котором все отрезки — существующие дороги 2025, — предупреждение «как в OSM»."),
    10: dict(group="roads", sev={"default": "error", "warnings": [NB]}, when=W_STD, by=["validator"],
             params=["@street_profiles", "crossings.at_every_at_grade_node", "crossings.at_grade_spacing_regulated_m", "crossings.grade_separated_spacing_m", "@crossing_matrix", "street_xs.sidewalk_extra_at_walls_m"],
             how="Для улиц городского типа требует тротуары с обеих сторон шириной не меньше street_profiles[class].sidewalk_m, на скоростных/магистральных дорогах и съездах — отсутствие тротуаров; проверяет переход в каждом узле в одном уровне и шаг переходов по таблице; концы пешеходных улиц и бульваров — у тротуара или площади."),
    11: dict(group="roads", sev={"default": "error", "warnings": [AN]}, when=W_STD, by=["validator"], params=["@street_profiles", "@road_classes"],
             how="Сверяет у каждой дороги число полос, ширину полосы, число проезжих частей и ширину разделителя с профилем её класса; встречные полосы на одной проезжей части при carriageways = 2 — ошибка. Ширины разделителя — аналог (СП303 для загородных дорог): нарушение ширины — предупреждение. Съезды развязки с полосами из spec (узел развязки `ramps` {id съезда или движение: {lanes, from_year}}): каждый ключ должен найти съезд (interchanges[].ramp_lanes), и у каждого найденного отрезка с этого года до последнего года проверки не меньше lanes полос (профиль или segments[].stages) — иначе ошибка."),
    12: dict(group="roads", sev={"default": "error", "warnings": [NB, EX]}, when=W_STD, by=["validator"],
             params=["fire_access.width_min_m", "setbacks.building_line_max_m", "fire_access.distance_to_wall_m", "fire_access.ring_required", "fire_access.sides", "fire_access.dead_end_max_m", "quarters.entry_spacing_max_m"],
             how="Для каждого здания по контурам зданий и проезжих частей (без списка driveways.json) ищет проезд ≥ 6 м, связанный с уличным графом, и расстояние линии застройки до проезжей части (≤ 25 м или пожарный проезд), в том числе в год открытия здания; для зданий 10–28 м без улицы в 25 м — проезд с краем в 5–8 м от стены; для зданий > 28 м — проезд в 8–10 м от стены и не меньше 2 × 8 + 6 = 22 м между такими зданиями; для школ, садов, больниц и высоких зданий — кольцевой проезд; для каждого квартала — хотя бы один въезд с улицы. Зазор 22 м проверяется для пары, где хотя бы одно здание новое; второе может быть как есть — существующее, ориентир с моделью Unity или блок модели квартала keep (Gate District, gate_district.bytes); пара «как есть × как есть» не проверяется."),
    13: dict(group="buildings", sev={"default": "error", "warnings": [{"case": "участок школы > 1200 мест по аналогу (Атырау)", "severity": "warning", "becomes_error": "после явного «ок» владельца"}]}, when=W_STD, by=["validator"],
             params=["schools.plot_m2_per_pupil", "schools.plot_2000_places_ha", "kindergartens.plot_m2_per_place", "clinics.hospital_plot_m2_per_bed", "clinics.polyclinic_plot", "clinics.ambulance_plot",
                     "universities.study_zone_ha_per_1000", "universities.college_plot_m2_per_student", "schools.building_from_red_line_m", "kindergartens.building_from_red_line_m", "setbacks.red_line_m"],
             how="Для каждого объекта типа школа, детсад, больница, поликлиника, вуз, колледж находит его участок, считает нормативную площадь по вместимости и сравнивает; проверяет отступ здания от красной линии (школа и сад ≥ 25 м, прочие — по setbacks.red_line_m)."),
    14: dict(group="buildings", sev={"default": "error", "warnings": [NB, AN, {"case": "промежуточные годы 2026–2040", "severity": "report", "becomes_error": "на 2050"},
                                                                      {"case": "мест больше числа генплана", "severity": "info", "becomes_error": None}]},
             when={"years": YEARS, "error_years": [2050], "report_years": [2026, 2030, 2034, 2040], "scope": "на промежуточных годах — отчёт о покрытии против очередей генплана", "scenarios": None,
                   "scenarios_note": "план не называет сценарий; по умолчанию Base (w35)"}, by=["validator"],
             params=["kindergartens.radius_m", "schools.radius_m", "clinics.polyclinic_radius_m", "pharmacy_shops.pharmacy_radius_m", "pharmacy_shops.daily_shops_radius_m", "parks.square_or_playground", "parks.district_park_access",
                     "parks.city_park_access", "stops.walk_max_m", "fire.depot_radius_km", "schools.places_per_1000_genplan", "kindergartens.places_per_1000_genplan", "clinics.polyclinics_2050", "validator.neighbour_wait",
                     "clinics.phc_min_visits_per_shift", "kindergartens.min_places_city", "kindergartens.rural_min_children", "schools.min_places_city", "schools.rural_min_pupils",
                     "kindergartens.building_m2_per_place", "schools.building_m2_per_seat", "validator.panel_vs_data_tolerance"],
             how="Для каждого дома с квартирами (новое жильё и существующие дома — те же здания, что totals.residents в buildings.json, одно число) считает расстояние по пешеходной сети до ближайших детсада, школы, поликлиники, аптеки/магазина, сквера или парка, остановки и (по прямой) до пожарного депо, с радиусами для многоэтажной или малоэтажной застройки; каждый пробел — ошибка с координатами дома; места на 1000 жителей сверяет с минимумом генплана; вместимость в радиусе — по норме на 1000 жителей; поликлиника меньше наименьшей организации ПМСП не засчитывается; сад или школа меньше наименьшей вместимости и здание, площадь которого меньше мест × м² на место, отмечаются."),
    15: dict(group="buildings", sev={"default": "error", "warnings": [{"case": "Green: жильё в секторе 290°–20° от завода", "severity": "warning", "becomes_error": None},
                                                                   {"case": "существующий дом 2025 ближе szz.rail_m к пути ж/д", "severity": "warning", "becomes_error": None}]}, when=W_STD, by=["validator"],
             params=["szz.class_width_m", "szz.wind_sector_deg", "szz.forbidden_inside", "szz.allowed_inside", "szz.landfill_m", "szz.petrol_station_m", "szz.rail_m"],
             how="Для каждого промышленного объекта строит СЗЗ по классу вредности и запрещает в ней жильё, школы, сады, площадки; в пределах двойной СЗЗ запрещает жильё, школы и сады в секторе азимутов 200°–295° от завода (в Green сектор 290°–20° — предупреждение). Дом с квартирами ближе szz.rail_m (100 м от оси крайнего пути ж/д) — ошибка для нового дома, предупреждение для существующего 2025."),
    16: dict(group="buildings", sev={"default": "error", "warnings": []}, when=W_STD, by=["validator"],
             params=["heights.airfield_approval_radius_km", "heights.airfield_height_threshold_m", "heights.airfield_points", "heights.core_along_a3", "heights.gate_owner_rule"],
             how="Сравнивает высоту каждого здания с потолком полигона «центр»/«ось» (буфер от А-3 и ЛРТ) из спецификации; для зданий ≥ 50 м в 30 км от КТА Жетыген или будущего аэропорта требует флаг «нужно согласование» (registry.json, поле aviation) — без него ошибка."),
    17: dict(group="buildings", sev={"default": "error", "warnings": []}, when=W_STD, by=["validator"], params=["parking.ground_lot_max_in_centre"],
             how="Пересекает наземные стоянки с полигоном «центр района» (> 50 мест — ошибка) и с секторами обзора фасадов знаковых объектов из спецификации (любая стоянка — ошибка); вне центра наземные поля допускает только у ТРЦ, стадионов и на окраинах."),
    18: dict(group="buildings", sev={"default": "error", "warnings": [{"case": "повтор фасада длиннее 60 м", "severity": "tester", "becomes_error": "замечание тестера по кадрам"}]}, when=W_STD, by=["validator", "tester_frames"],
             params=["validator.identical_models"],
             how="В круге 200 м вокруг каждого жилого/офисного здания считает здания той же модели (кроме типовых школ и садов, панелей СЭС, складов и существующих домов) — больше двух = ошибка; повтор фасада > 60 м проверяет тестер на кадрах."),
    19: dict(group="green_and_services", sev={"default": "error", "warnings": []}, when=W_STD, by=["validator"], params=["trees.distance_to_structures_m", "validator.levels"],
             how="Проверяет каждую точку дерева против карты занятости (проезжая часть, тротуар, рельсы, здания, крыши) и маски «нельзя сажать», включая отступы табл. 9.2."),
    20: dict(group="green_and_services", sev={"default": "error", "warnings": []}, when=W_STD, by=["validator"], params=["validator.levels", "validator.occupancy_overlap_max_m2"],
             how="Проверяет каждую точку фонаря, светофора, остановки и знака против карты занятости: на проезжей части или внутри здания — ошибка (расширение проверки w24)."),
    21: dict(group="green_and_services", sev={"default": "error", "warnings": []}, when=W_UNITY, by=["unity_counter"], params=["validator.unity_counter_max"],
             how="Unity при прогоне считает машины вне полос и парковочных мест (поперёк, в газоне, в здании) и пишет счётчик в лог; любое значение больше 0 — ошибка."),
    22: dict(group="green_and_services", sev={"default": "error", "warnings": []}, when=W_UNITY, by=["unity_counter"], params=["validator.unity_counter_max"],
             how="Unity при прогоне считает людей вне тротуаров, площадей и парков (на проезжей части, в воде, на крышах) и пишет счётчик в лог; любое значение больше 0 — ошибка."),
    23: dict(group="green_and_services", sev={"default": "error", "warnings": [NB]},
             when={"years": "все годы появления (сравнение лет)", "scenarios": SCEN, "scope": "в каждом из четырёх сценариев с учётом сдвига лет в сценарии"}, by=["validator"],
             params=["validator.scenarios", "validator.existing_object_year", "validator.order_4d", "validator.neighbour_wait"],
             how="Для каждого объекта находит улицу, которая его обслуживает (въезд), и в каждом сценарии сравнивает годы со сдвигом сценария: год объекта < года улицы — ошибка; проверяет 4D-порядок земля → каркас → фасад → благоустройство и что существующие объекты и их улицы имеют год 2025."),
    24: dict(group="green_and_services", sev={"default": "error", "warnings": []},
             when={"years": YEARS, "scope": "w35: план не называет годы для правила 24; проверяем на каждом годе прогона", "scenarios": None}, by=["validator"],
             params=["validator.panel_vs_data_tolerance", "validator.district_numbers_tolerance_pct", "quarters.genplan_population_2050", "quarters.genplan_jobs_2050"],
             how="Сверяет каждое число панелей (жители, места, рабочие места района) и totals в buildings.json с тем же числом, посчитанным из данных карты, — должно совпасть точно; числа нового города (без кварталов keep и существующих домов OSM) против целей генплана — допуск ±5 %."),
    25: dict(group="green_and_services", sev={"default": "error", "warnings": [NB, AN]},
             when={"years": YEARS, "scope": "w35: план не называет годы для правила 25; проверяем как правила 1–22 для линий, которые в этом году уже стоят", "scenarios": None}, by=["validator"],
             params=["lrt.line_ends", "lrt.station_axis_max_offset_m", "lrt.platform_between_cross_streets", "lrt.station_spacing_km", "lrt.viaduct_clearance_over_road_m", "lrt.ramp_slope_max_pct", "lrt.platform_length_m", "lrt.min_curve_radius_m", "fire_access.arches", "bridges.road_clearance_m"],
             how="Для каждой линии ЛРТ проверяет, что оба конца — депо или конечная станция; каждая станция ≤ 2 м от оси и платформа целиком между соседними поперечными улицами; шаг станций 0,8–1,5 км; низ эстакады ≥ 5,0 м над дорогой; палуба не пересекает здания; рампа эстакада–земля ≤ 6 %. Длина платформы и радиус кривой — аналог: предупреждение. Под пролётами (w43, раунд 9): каждый проезд и разворотная площадка под путепроводом улицы, эстакадой ЛРТ или ж/д эстакадой (spec rail) — просвет ≥ 4,5 м (fire_access.arches.height_min_m, проезд пожарной машины; ниже 5,0 м bridges.road_clearance_m), по всей проезжей части под пролётом; улица под ж/д эстакадой — ≥ 5,0 м (bridges.road_clearance_m)."),
}
GROUP_EN = {"land": "land", "roads": "roads", "buildings": "buildings", "green_and_services": "green and services"}


def parse_plan(path):
    txt = open(path, encoding="utf-8").read()
    a = txt.index("## Чего быть не должно")
    b = txt.index("\n## ", a + 5)
    sec = txt[a:b]
    rules, group_ru = {}, None
    for line in sec.split("\n"):
        m = re.match(r"^\*\*(.+?)\*\*\s*$", line)
        if m and not line.startswith("**Когда"):
            group_ru = m.group(1)
            continue
        m = re.match(r"^\| (\d+) \| (.+?) \| (.+) \|\s*$", line)
        if m:
            n = int(m.group(1))
            if n in rules:
                raise SystemExit("rule %d twice in plan" % n)
            rules[n] = (m.group(2), m.group(3), group_ru)
    if sorted(rules) != list(range(1, 26)):
        raise SystemExit("plan rules are not 1..25: %s" % sorted(rules))
    m = re.search(r"\*\*Когда и как проверяем\.\*\* (.+)", sec)
    intro = sec.split("\n\n")[1].strip()
    return rules, intro, (m.group(1).strip() if m else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", default="/mnt/project-files/alatau_stage7/plan/plan.md")
    ap.add_argument("--out", default=os.path.normpath(os.path.join(HERE, "..", "spec")))
    a = ap.parse_args()

    # ---- checks on norms
    for k, e in E.items():
        if not e["source"].get("doc") or e["status"] not in ("norm", "analogue", "not_verified"):
            raise SystemExit("norm without source or status: " + k)
        if e["value"] is None and e["status"] == "norm":
            raise SystemExit("norm with null value must be not_verified: " + k)
        if e["severity"] not in ("error", "warning", "info"):
            raise SystemExit("bad severity " + k)
    cells = matrix()
    profiles = collections.OrderedDict()
    for cls, fk in PROFILE_KEYS.items():
        profiles[cls] = collections.OrderedDict((f, {"key": k, "value": E[k]["value"], "unit": E[k]["unit"], "status": E[k]["status"]}) for f, k in fk.items())
    groups = collections.OrderedDict()
    for k, e in E.items():
        groups.setdefault(e["group"], []).append(k)
    st = collections.Counter(e["status"] for e in E.values())
    norms = collections.OrderedDict([
        ("schema", "qtwin.norms/1"), ("level", 0), ("made_by", "w35, tools/map/registry/build_spec.py"), ("date", "2026-10-31"),
        ("inputs", ["plan/plan.md «Что достраиваем по нормам» и «Чего быть не должно»", "research/norms.md (R2, 31.10.2026)"]),
        ("status_vocab", {"norm": "число из нормы РК (или её прямого предшественника С08), генплана Алатау, факта на местности или утверждённого правила плана; нарушение — ошибка валидатора",
                          "analogue": "число из нормы другой страны, международного ориентира или проекта-аналога; валидатор — предупреждение отдельной строкой в «было/стало», владелец принимает явно",
                          "not_verified": "числа нет в открытом источнике или единица неоднозначна; value может быть null; валидатор — предупреждение"}),
        ("basis_vocab", {"kz_norm": "действующая норма РК", "kz_norm_predecessor": "СНиП РК 3.01-01-2008 вместо СП РК 3.01-101-2013", "kz_norm_cited_by_project": "норма РК в цитате проекта РК",
                         "kz_genplan": "генплан г. Алатау (ПП № 388 / № 727)", "kz_fact": "факт на местности", "kz_project_fact": "реальный проект РК как аналог",
                         "plan_rule": "утверждённый план / решение владельца / правило qTwin", "foreign_norm": "норма другой страны", "international_guide": "международный ориентир",
                         "research_synthesis": "синтез исследователя R2", "kz_news": "новость без номера документа", "+derived": "арифметика над числом источника ([выч.])"}),
        ("severity_policy", "severity записи: error — нарушение не даёт принять район; warning — отдельная строка «было/стало»; info — справочно. По умолчанию norm → error, analogue / not_verified → warning; исключения указаны в severity_why"),
        ("precedence", "1) нормы РК (СП/СН РК, техрегламент МЧС, санправила МЗ); 2) если в РК нет текста — С08; 3) если нет и там — аналог (ДБН Украины, AASHTO/DOT США, NCHRP) с пометкой (research/norms.md §0)"),
        ("conflict_rule_streets", "где проект Астаны 2023 (цитирует действующий СП РК 3.01-101-2013) расходится с С08: ширины берём большие, уклон — строже, скорость — по СП РК (запись street.district_transport.*)"),
        ("sources", collections.OrderedDict((k, {"doc": v[0], "year": v[1], "url": v[2], "kind": v[3]}) for k, v in SRC.items() if not k.startswith("С08-") or any(
            e["source"]["label"] == k or any(x["label"] == k for x in e.get("also", [])) for e in E.values()))),
        ("counts", {"norms": len(E), "by_status": dict(st), "by_group": {g: len(v) for g, v in groups.items()}, "node_matrix_cells": len(cells), "road_classes": len(ROAD_CLASSES)}),
        ("groups", groups),
        ("norms", E),
        ("road_classes", collections.OrderedDict((k, {"name_ru": v[0], "basis": v[1], "plan_class": v[2], "node_group": v[3]}) for k, v in ROAD_CLASSES.items())),
        ("street_profiles", profiles),
        ("node_types", collections.OrderedDict((k, {"name_ru": v[0], "level": v[1]}) for k, v in NODE_TYPES.items())),
        ("node_groups", GROUP_RU),
        ("node_matrix", cells),
        ("node_matrix_note", "пары неупорядочены (a, b); узел с 5+ лучами — только roundabout или square (правило 6); trumpet — только трёхлучевой узел; тип вне allowed — нарушение с severity из forbidden_*"),
        ("crossing_matrix", CROSSING_MATRIX),
        ("not_found", [{"key": k, "what": w} for k, w in GAPS]),
    ])
    for k, _ in GAPS:
        if k not in E:
            raise SystemExit("gap key missing " + k)

    # ---- rules
    plan_rules, intro, when_txt = parse_plan(a.plan)
    top = {"@node_matrix": "node_matrix", "@road_classes": "road_classes", "@node_types": "node_types", "@street_profiles": "street_profiles", "@crossing_matrix": "crossing_matrix"}
    out_rules = []
    for n in range(1, 26):
        text, check, group_ru = plan_rules[n]
        r = RULES[n]
        for p in r["params"]:
            if p.startswith("@"):
                if p not in top:
                    raise SystemExit("rule %d: unknown top-level param %s" % (n, p))
            elif p not in E:
                raise SystemExit("rule %d: param %s not in norms" % (n, p))
        out_rules.append(collections.OrderedDict([
            ("id", n), ("text_ru", text), ("check_ru", check), ("group", r["group"]), ("group_en", GROUP_EN[r["group"]]), ("group_ru", group_ru),
            ("severity", r["sev"]), ("when", r["when"]), ("checked_by", r["by"]),
            ("params", [{"key": p, "in": top[p] if p.startswith("@") else "norms", "status": None if p.startswith("@") else E[p]["status"]} for p in r["params"]]),
            ("how", r["how"])]))
    rules = collections.OrderedDict([
        ("schema", "qtwin.rules/1"), ("level", 0), ("made_by", "w35, tools/map/registry/build_spec.py"), ("date", "2026-10-31"),
        ("source", "plan/plan.md, раздел «Чего быть не должно: жёсткие правила» (text_ru и check_ru — дословно, читаются при сборке)"),
        ("plan_intro_ru", intro), ("plan_when_ru", when_txt),
        ("vocab", {"group": {"land": "Земля: один участок, одно назначение", "roads": "Дороги: сеть, по которой можно проехать", "buildings": "Здания и объекты: там, где им место", "green_and_services": "Зелень и мелочи, которые ломают картинку"},
                   "severity": {"error": "одно нарушение = район не принят", "warning": "отдельная строка в «было/стало», не останавливает приёмку", "report": "отчёт о покрытии (не ошибка)", "info": "в отчёт района", "tester": "проверяет тестер на кадрах"},
                   "checked_by": {"validator": "валидатор на данных карты до Unity", "unity_counter": "счётчик Unity в логе прогона", "tester_frames": "тестер по 15 кадрам"},
                   "params": "ключи norms.json (in = norms) или разделы верхнего уровня norms.json (in = node_matrix, street_profiles, road_classes, node_types, crossing_matrix)"}),
        ("rules", out_rules),
    ])
    os.makedirs(a.out, exist_ok=True)
    for name, doc in (("norms.json", norms), ("rules.json", rules)):
        with open(os.path.join(a.out, name), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
    print("norms", len(E), dict(st), "groups", len(groups), "matrix", len(cells), "rules", len(out_rules))


if __name__ == "__main__":
    main()
