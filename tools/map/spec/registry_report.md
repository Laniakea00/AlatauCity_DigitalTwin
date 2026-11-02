# Реестр реальных объектов Alatau City — отчёт (уровень 0 w35, уровень 1 w42)

Собран `tools/map/registry/build_registry.py` из `research/alatau_objects.md`, `research/transport_site.md`, кода двойника и Overture 2026-10-21.0. Координаты — Unity X/Z (X = E − 663000, Z = N − 4830000, UTM 43N). © OpenStreetMap contributors, Overture Maps Foundation.

Всего строк: **279**; на карте (on_map): 252; названы в плане: 113.

Километраж А-3: по 14 столбам OSM (из 22 в 150 м от оси) км = 0.9859 × пикет + 13.476, СКО 0.45 км; пикет — расстояние по пути KAZ08 от его южного конца. Узел А-3 × БАКАД: пикет 8.69 км, км ≈ 22.0; точка (-2280.0, -20320.2).


## По району из источника (district; пусто = источник не называет)

| district | строк |
|---|---|
| — | 213 |
| Gate | 26 |
| Green | 16 |
| Golden | 13 |
| Growing | 10 |
| Gate и Golden | 1 |

## По району, выведенному исследованием (district_inferred)

| district_inferred | строк |
|---|---|
| — | 232 |
| Gate | 20 |
| Growing | 20 |
| Golden | 3 |
| Green | 2 |
| Gate / Golden | 1 |
| Gate / Growing | 1 |

## По району по геометрии (district_geom, полигоны city.json — контуры двойника, уровень 1)

| district_geom | строк |
|---|---|
| нет геометрии | 135 |
| Growing | 55 |
| Gate | 46 |
| outside | 21 |
| Golden | 13 |
| Green | 9 |

## По району спецификации (district_area: половины Growing)

| district_area | строк |
|---|---|
| нет геометрии | 135 |
| gate | 46 |
| growing_e | 44 |
| вне районов | 21 |
| golden | 13 |
| growing_w | 11 |
| green | 9 |

## По месту схемы (scheme_area)

| scheme_area | строк |
|---|---|
| нет в схемах | 109 |
| gate | 48 |
| growing_e | 44 |
| нет точки в схеме | 30 |
| green | 21 |
| golden | 16 |
| growing_w | 11 |

## По действию схемы (scheme_action)

| scheme_action | строк |
|---|---|
| нет в схемах | 109 |
| keep | 73 |
| by_rule | 50 |
| add | 26 |
| move | 18 |
| remove | 2 |
| reroute | 1 |

## Уровень 1: район до и после (district_geom)

До — уровень 0, полигоны geojson генплана; после — полигоны city.json (контуры двойника).

| район | до | после |
|---|---|---|
| нет геометрии | 135 | 135 |
| Growing | 29 | 55 |
| Gate | 47 | 46 |
| outside | 20 | 21 |
| Golden | 38 | 13 |
| Green | 10 | 9 |

Строк, у которых район сменился: 37.

| id | было (генплан) | стало (city.json) | половина |
|---|---|---|---|
| fap_zhanaarna | Golden | Growing | growing_e |
| fok_zarechny | Green | Growing | growing_e |
| mars_petcare | Golden | Growing | growing_e |
| danaflex | Golden | Growing | growing_e |
| sunny_paper | Golden | Growing | growing_e |
| g_trans | Golden | Growing | growing_e |
| car_assembly_zhanaarna | Golden | Growing | growing_e |
| modex_kairat | Golden | Growing | growing_e |
| tlc_zhetygen | Growing | Green | green |
| tlc_industrial_zone | Growing | Green | green |
| oiz_tulip | Golden | Growing | growing_e |
| industrial_daulet | Golden | Growing | growing_e |
| knauf | Green | Growing | growing_e |
| airfield_zhetygen | Growing | Green | green |
| gtes_doosan | Golden | Growing | growing_e |
| road_a3 | Golden | Growing | growing_w |
| rail_turksib | Golden | Growing | growing_e |
| rail_zhetygen_altynkol | Growing | Green | green |
| rail_bypass_zhetygen_kazybek | Golden | Growing | growing_w |
| rail_second_tracks | Golden | Growing | growing_e |
| rail_tulip_tracks | Golden | Growing | growing_e |
| station_zhanaarna | Golden | Growing | growing_e |
| station_kairat | Golden | Growing | growing_e |
| ps_alma_500 | Golden | Growing | growing_w |
| ps_zarechnoe | Green | Growing | growing_e |
| ps_220_golden_osm | Golden | Growing | growing_w |
| ps_arna_twin | Golden | Growing | growing_e |
| hv_lines_500 | Green | Growing | growing_w |
| hv_lines_220 | Golden | Growing | growing_w |
| settlement_zhanaarna | Golden | Growing | growing_e |
| settlement_kuygan | Growing | Green | green |
| settlement_daulet | Golden | Growing | growing_e |
| settlement_kairat | Golden | Growing | growing_e |
| settlement_zarechnoe | Green | Growing | growing_e |
| interchange_a3_km18_5 | Gate | outside (0.0 km from Gate) | — |
| interchange_a3_km42_4 | Golden | Growing | growing_e |
| interchange_a3_km55_9 | Green | Growing | growing_w |

## Уровень 1: флаги (строки не перенесены)

- **pepsico** — точка источника (центр мкр Ынтымак) стоит среди домов села; завод ставится по схеме Gate на корпус OSM 28 043 м² (схема gate (objects pepsico)); замер: {"overture_buildings_within_50m": 21, "within_100m": 79, "nearest_overture_building_m": 6.6, "twin_existing_osm_within_100m": 0, "source": "OUT/osm/buildings.geojson уровня 0 (Overture 2026-10-21.0: OSM + Microsoft ML Buildings)"}
- **agglo_rail_station_1** — точка = пересечение осей А-3 и БАКАД, внутри клеверной развязки; станция по схеме Gate — ТПУ у развязки (схема gate (objects agglo_rail_station_1)); замер: {"to_interchange_centre_m": 24.8, "interchange": "interchange_a3_bakad", "twin_interchange_zone_r_m": 378}
- **tlc_zhetygen** — контур OSM «ТЛЦ Логистика» лежит больше чем наполовину в Green, а объект ставит Growing-восток (схемы growing_e и green (objects tlc_zhetygen)); замер: {"share_pct_by_area": {"growing_e": 25.9, "green": 74.1}, "area_ha": 31.7}

## Уровень 1: дороги на общих проезжих частях (одна дорога с двумя номерами — не ошибка)

| id | участок | вместе с | км в городе | км в пробной зоне Gate | названия OSM |
|---|---|---|---|---|---|
| road_a3 | общий | road_a19 | 3.00 | 0.87 | Алматы-Усть-Каменогорск; Алматы-Өскемен |
| road_a3 | своя проезжая часть | — | 92.80 | 1.16 | Almaty-Öskemen Motorway; Алматы - Өскемен; Алматы-Өскемен; Жансүгіров көшесі; Солтүстік айналма |
| road_bakad | общий | road_a19 | 6.03 | 4.44 | ҮАААЖ |
| road_bakad | своя проезжая часть | — | 1.41 | 1.41 | ҮАААЖ |
| road_a19 | общий | road_a3 | 3.00 | 0.87 | Алматы-Усть-Каменогорск; Алматы-Өскемен |
| road_a19 | общий | road_bakad | 6.03 | 4.44 | ҮАААЖ |
| road_a19 | съезды развязки | — | 1.17 | 1.17 | — |
| road_a19 | своя проезжая часть | — | 6.90 | 0.00 | Алматы - Қорғас тасжолы |

## Уровень 1: ВЛ 220 кВ по участкам (решение владельца 31.10.2026: через центры Gate и Golden — в кабель или в обход ядра)

| линия OSM | район | состояние | км | в ядре, км | кабель | годы |
|---|---|---|---|---|---|---|
| 0bb49e7b | golden | воздушная | 1.13 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 0bb49e7b | growing_w | воздушная | 4.83 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 121ff315 | gate | кабель | 6.81 | 1.52 | gate.json#utilities/hv220_cable | [2027, 2027, 2028, 2027] |
| 121ff315 | golden | воздушная | 8.67 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 20c6b40c | gate | воздушная | 0.15 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 20c6b40c | golden | воздушная | 2.69 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 235a7bfa | growing_w | воздушная | 9.74 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 235a7bfa | growing_e | воздушная | 12.97 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 235a7bfa | green | воздушная | 8.47 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 4969c90a | gate | воздушная | 0.46 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 4ea57bb1 | golden | воздушная | 8.48 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 564b245a | golden | воздушная | 9.32 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 564b245a | growing_w | воздушная | 5.01 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 83f0e91a | growing_w | воздушная | 17.43 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 83f0e91a | growing_e | воздушная | 4.57 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 83f0e91a | green | воздушная | 8.58 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 8b790e95 | green | воздушная | 8.44 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 92ca2130 | gate | воздушная | 6.42 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 988f9664 | golden | воздушная | 0.45 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 99d8168d | golden | воздушная | 1.11 | 0.00 | — | [2025, 2025, 2025, 2025] |
| 99d8168d | growing_w | воздушная | 4.89 | 0.00 | — | [2025, 2025, 2025, 2025] |
| bf8acecb | gate | кабель | 3.18 | 0.30 | gate.json#utilities/hv220_cable_n | [2031, 2029, 2033, 2031] |
| bf8acecb | golden | воздушная | 13.76 | 0.00 | — | [2025, 2025, 2025, 2025] |
| bf8acecb | growing_w | воздушная | 3.28 | 0.00 | — | [2025, 2025, 2025, 2025] |
| e2663d8a | growing_w | воздушная | 2.30 | 0.00 | — | [2025, 2025, 2025, 2025] |
| f3445a80 | golden | воздушная | 7.78 | 0.00 | — | [2025, 2025, 2025, 2025] |
| f51c5bfe | golden | воздушная | 7.39 | 0.00 | — | [2025, 2025, 2025, 2025] |

Сводка, км: {"golden": {"overhead": 60.78}, "growing_w": {"overhead": 47.48}, "gate": {"cable": 9.99, "overhead": 7.03}, "growing_e": {"overhead": 17.54}, "green": {"overhead": 25.49}}. Схемы согласны: да. Правило: ядро района = зоны спецификации с use mixed_centre / business; кабель = utilities[] kind power_cable_220kv с replaces этой линии OSM.
- gate: ВЛ 220 кВ (OSM voltage=220000) в ядре 1.82 км, из них в кабеле 1.82 км, воздушных 0.00 км
- golden: ВЛ 220 кВ (OSM voltage=220000) ядро не пересекают; линия без напряжения b6e4919c проходит ядро 1.63 км — открыто, трассу задаёт схема golden
- открыто: линия OSM power=line без напряжения через ядро golden; если это 220 кВ (так читает её схема), по решению владельца — в кабель или в обход ядра; трассу задаёт схема района (b6e4919c, в ядре 1.63 км)

## Уровень 1: схемы расходятся в месте или действии

| id | владелец | записи схем | разнос, м |
|---|---|---|---|
| hospitals_stage1 | gate | gate: by_rule [-2510.0, -18165.0]; golden: by_rule [-1250, -10550] | 7719 |
| polyclinic_250 | growing_e | gate: by_rule [-5205.0, -22710.0]; growing_e: add [7230, 8130] | 33253 |
| fok_zarechny | growing_e | growing_e: keep [1450, 12155]; green: add [1450, 12155] | 0 |
| pepsico | gate | gate: move [-3078.5, -22541.2]; growing_e: move [-3696, -21440] | 1263 |
| tlc_zhetygen | green | growing_e: move [8666, 11819]; green: keep [8592, 11566] | 264 |
| airfield_zhetygen | green | growing_e: keep [7722, 14308]; green: keep [7705, 14242] | 68 |
| ps_zarechnoe | growing_e | growing_e: keep [575, 11824]; green: add [576, 11819] | 0 |
| settlement_zhetygen | growing_e | growing_e: keep [7501, 8350]; green: keep [7532, 8560] | 212 |
| settlement_zarechnoe | growing_e | growing_e: keep [1571, 12412]; green: keep [1519, 12448] | 63 |

## Уровень 1: место схемы отличается от места реестра (> 50 м)

| id | реестр (geom) | схема (scheme_to) | действие | схема-владелец | район схемы |
|---|---|---|---|---|---|
| iconic_complex | -3170, -19080 | -3500, -19500 | move | gate | gate |
| iconic_tower_main | -3170, -19080 | -3500, -19500 | move | gate | gate |
| iconic_tower_second | -3170, -19080 | -3500, -19500 | move | gate | gate |
| iconic_podium | -3170, -19080 | -3500, -19500 | move | gate | gate |
| iconic_offices_6 | -3170, -19080 | -3500, -19500 | move | gate | gate |
| iconic_greenery | -3170, -19080 | -3500, -19500 | move | gate | gate |
| gate_district_ring | -3170, -19080 | -3500, -19500 | move | gate | gate |
| gate_city_business | -3911, -23291 | -4150, -23150 | by_rule | gate | gate |
| admin_centre_new | -3911, -23291 | -4000, -23300 | add | gate | gate |
| gov_buildings_zhetygen | 6930, 7814 | 7280, 8330 | add | growing_e | growing_e |
| l7_lotte | -2300, -19600 | -3022, -19602 | move | gate | gate |
| bi_group_plot | -3911, -23291 | -4300, -23800 | by_rule | gate | gate |
| gate_city_new_quarters | -3911, -23291 | -4150, -23800 | by_rule | gate | gate |
| rent_to_own_koyankus | -5730, -23238 | -5000, -23300 | by_rule | gate | gate |
| qaist | -1457, -12698 | -150, -11100 | move | golden | golden |
| academic_cluster | -471, -10543 | 450, -9750 | add | golden | golden |
| school_gate_city_20_keleshek | -3911, -23291 | -3558, -23583 | add | gate | gate |
| school_koyankus_old | -5730, -23238 | -5590, -23797 | add | gate | gate |
| kindergarten_gate_city_280 | -3911, -23291 | -3420, -23380 | add | gate | gate |
| gate_city_social_set | -3911, -23291 | -4250, -23500 | by_rule | gate | gate |
| kaist_research_institute | -1457, -12698 | 300, -10500 | move | golden | golden |
| marina_kapchagay | 5177, 23845 | 4885, 25332 | move | green | green |
| house_of_culture_zhetygen | 6930, 7814 | 7380, 8240 | add | growing_e | growing_e |
| sport_complex_zhetygen | 6930, 7814 | 7120, 8000 | add | growing_e | growing_e |
| sport_complex_koyankus | -5730, -23238 | -5025, -22125 | add | gate | gate |
| park_gate_city_yntymak | -3804, -22366 | -3925, -22575 | add | gate | gate |
| pepsico | -3696, -21440 | -3078, -22541 | move | gate | gate |
| car_assembly_zhanaarna | 248, 561 | 150, -1150 | by_rule | growing_e | growing_e |
| modex_kairat | 5734, -1182 | 5650, -1600 | by_rule | growing_e | growing_e |
| griffin_logopark | -2441, -19107 | -2522, -19101 | move | gate | gate |
| oiz_tulip | 248, 561 | 211, -1709 | add | growing_e | growing_e |
| industrial_daulet | 7593, 182 | 7700, 200 | by_rule | growing_e | growing_e |
| agglo_rail_station_1 | -2280, -20320 | -2805, -20471 | move | gate | gate |
| overpass_zhetygen_950 | 8332, 9495 | 8300, 9300 | keep | growing_e | growing_e |
| ps_kokpa_1 | -3911, -23291 | -3850, -24050 | add | gate | gate |
| gtes_doosan | 8185, 979 | 10100, 4780 | by_rule | growing_e | growing_e |
| water_intake_gate_city | -3911, -23291 | -3700, -24050 | move | gate | gate |
| kns_gate_city | -3911, -23291 | -3800, -24200 | add | gate | gate |
| agrs_gate_city | -3911, -23291 | -3650, -24200 | keep | gate | gate |
| boiler_gate_city | -3911, -23291 | -3750, -24130 | add | gate | gate |
| rail_tulip_tracks | 248, 561 | 300, -700 | by_rule | growing_e | growing_e |
| grs_zhetygen | 6930, 7814 | 6250, 4950 | by_rule | growing_e | growing_e |

## Уровень 1: строки на карте, которых нет ни в одной схеме (87)

| id | тип | район (city.json) | действие реестра |
|---|---|---|---|
| ansa_hub | business_mixed | — | by_rule |
| cn_investor_housing | business_mixed | — | by_rule |
| k_smart_town | district_program | — | by_rule |
| private_sector | residential | — | keep |
| schools_genplan | district_program | — | by_rule |
| kindergartens_genplan | district_program | — | by_rule |
| polyclinics_genplan | district_program | — | by_rule |
| ambulance_genplan | ambulance | — | by_rule |
| german_med_cluster | hospital | — | by_rule |
| moyynkum_forest_park | park | — | by_rule |
| mekhanizator_recreation | park | — | by_rule |
| khan_tengri_biopharma | industry | — | by_rule |
| r_pharm | industry | — | by_rule |
| steppe_pharma | industry | — | by_rule |
| etasa_fiber | industry | — | by_rule |
| sugar_plant | industry | — | by_rule |
| tricycle_assembly | industry | — | by_rule |
| saf_complex | industry | — | by_rule |
| sinomach_agro | industry | — | by_rule |
| agropark | industrial_zone | — | by_rule |
| g2_power | industry | — | by_rule |
| amk_ceratech | industry | — | by_rule |
| keumjeong | industry | — | by_rule |
| vitrosys_lab | research | — | by_rule |
| proton_therapy | hospital | — | by_rule |
| battery_complex | industry | — | by_rule |
| ahlers_pilot | logistics | — | by_rule |
| dar_metall_recycling | waste | — | by_rule |
| wilo_engineering | industry | — | by_rule |
| mtc_woodworking | industry | — | by_rule |
| integrity_birlik_tlc | logistics | — | by_rule |
| integrity_400ha | industrial_zone | — | by_rule |
| industrial_north_kosozen | industrial_zone | — | by_rule |
| cimc_logistics_dc | logistics | — | by_rule |
| german_warehouses | logistics | — | by_rule |
| dcg_compute | datacenter | — | by_rule |
| huawei_smart_city | datacenter | — | by_rule |
| henkel_plant | industry | — | keep |
| mareven_food | industry | — | keep |
| landfill_karaoy | waste | — | keep |
| landfill_ali | waste | golden | keep |
| taza_zher | waste | outside (2.2 km from Golden) | keep |
| dachas_36 | dacha | — | keep |
| lrt_regional | lrt | — | by_rule |
| lrt_city | lrt | — | by_rule |
| lrt_depots | lrt | — | by_rule |
| river_tram | port_marina | — | by_rule |
| fire_depots_genplan | district_program | — | by_rule |
| road_ia | road | — | by_rule |
| arterial_continuous_east | road | — | by_rule |
| half_rings_3_4 | road | — | by_rule |
| road_yntymak_zhanadaur | road | — | keep |
| exit_kokterek | road | — | keep |
| road_almaty_zhetygen | road | — | keep |
| rail_agglomeration | rail_line | — | by_rule |
| station_moyynkum | rail_station | outside (0.1 km from Golden) | keep |
| station_sorbulak | rail_station | outside (19.0 km from Golden) | keep |
| station_baiserke | rail_station | outside (2.0 km from Golden) | keep |
| station_konaev | rail_station | outside (4.2 km from Green) | keep |
| micromobility_network | district_program | — | by_rule |
| water_kapchagay | water | — | keep |
| river_kaskelen | water | — | keep |
| river_malaya_almatinka | water | — | keep |
| river_ili | water | — | keep |
| sorbulak | water | — | keep |
| canal_bak | water | outside (12.0 km from Gate) | keep |
| moyynkum_sands | label_only | — | by_rule |
| substations_programme | substation | — | by_rule |
| kogtu_chp_10 | power_plant | — | by_rule |
| heat_rk1 | heat_plant | — | by_rule |
| grs_baiserke | gas_station | outside (1.7 km from Golden) | keep |
| grs_new_2 | gas_station | — | by_rule |
| water_intakes_4 | water_intake | — | by_rule |
| pumping_stations_12 | pumping_station | — | by_rule |
| wwtp_4 | sewage | — | by_rule |
| storm_basins_29 | sewage | — | by_rule |
| waste_new_sites | waste | — | by_rule |
| settlement_otegen_batyr | settlement | outside (1.6 km from Gate) | keep |
| settlement_zhanalyk | settlement | outside (0.5 km from Growing) | keep |
| settlement_kosozen | settlement | outside (0.8 km from Golden) | keep |
| settlement_ali | settlement | golden | keep |
| settlement_karaoy | settlement | outside (2.4 km from Golden) | keep |
| settlement_nura | settlement | outside (1.5 km from Green) | keep |
| settlement_tuganbay | settlement | outside (1.8 km from Green) | keep |
| settlement_kokterek | settlement | — | keep |
| settlement_pokrovka | settlement | — | keep |
| interchange_a3_km18_5 | interchange | outside (0.0 km from Gate) | add |

## По типу

| type | строк |
|---|---|
| industry | 30 |
| settlement | 24 |
| label_only | 16 |
| district_program | 15 |
| road | 13 |
| interchange | 11 |
| rail_station | 11 |
| logistics | 10 |
| business_mixed | 9 |
| residential | 9 |
| tourism_leisure | 9 |
| industrial_zone | 8 |
| sport | 8 |
| water | 8 |
| substation | 7 |
| waste | 7 |
| park | 6 |
| power_plant | 6 |
| rail_line | 6 |
| clinic | 5 |
| hospital | 5 |
| district | 4 |
| gas_station | 4 |
| admin | 3 |
| datacenter | 3 |
| heat_plant | 3 |
| lrt | 3 |
| research | 3 |
| school | 3 |
| university | 3 |
| water_intake | 3 |
| culture | 2 |
| hotel | 2 |
| port_marina | 2 |
| power_line | 2 |
| pumping_station | 2 |
| sewage | 2 |
| vertiport | 2 |
| airfield | 1 |
| airport | 1 |
| ambulance | 1 |
| bridge | 1 |
| college | 1 |
| dacha | 1 |
| kindergarten | 1 |
| metro | 1 |
| military | 1 |
| religious | 1 |

## По статусу

| status | строк |
|---|---|
| built | 111 |
| planned | 84 |
| announced | 61 |
| under_construction | 20 |
| cancelled | 1 |
| removed | 1 |
| reserve | 1 |

## По действию

| action | строк |
|---|---|
| by_rule | 127 |
| keep | 104 |
| add | 38 |
| move | 7 |
| remove | 2 |
| reroute | 1 |

## По точности

| accuracy | строк |
|---|---|
| none | 100 |
| point_50m | 73 |
| settlement_1km | 55 |
| district_only | 49 |
| road_km_500m | 2 |

## Расхождение района: источник/вывод против полигона city.json

| id | район источника | вывод | по геометрии |
|---|---|---|---|
| tlc_zhetygen | — | Growing | Green |
| tlc_industrial_zone | — | Growing | Green |
| airfield_zhetygen | — | Growing | Green |
| settlement_zarechnoe | — | Green | Growing |

## Все расхождения источников (кто побеждает и почему)

- **iconic_complex** — место. T_24kz_20261027: «у подножия Заилийского Алатау», точное место не указано; T_gp727_zakon: территория в Илийской впадине, полого наклонена к Иле → побеждает **T_gp727_zakon**: генплан описывает рельеф всей территории; 24.kz даёт образный оборот без места
- **iconic_complex** — центр Gate. OWNER_3110: Iconic должен стоять в центре Gate; TWIN_networks: двойник: −3170, −19080; центроид полигона gate генплана (−4077, −20430), до него 1,63 км → побеждает **OWNER_3110**: решение владельца сильнее текущей позиции двойника; что считать центром (сдвинуть Iconic к центроиду или провести новую границу Gate вокруг Iconic) решает картограф Gate — граница района в спецификации задаётся заново
- **iconic_tower_main** — этажность. S33: «more than 56 storeys»; T_24kz_20261027: 272 м / 58 эт. → побеждает **S33**: данные застройщика; высота 272 м совпадает у обоих
- **iconic_tower_second** — высота и функция. S33: 80 м, отель 5* и брендированные резиденции; S35: 78 м, жилая башня → побеждает **S33**: застройщик (WCN) — первоисточник; 2 м разницы не меняют карту
- **intl_business_centre** — площадь. S01: более 3,7 млн м²; S09: 3,6 млн м² → побеждает **S01**: генплан — первоисточник
- **private_sector** — будущее ИЖС. S01: ст. 67: новые участки под ИЖС не выдаются; S108: заменить частный сектор высотными домами (пересказ) → побеждает **PLAN**: план двойника: сёла остаются на месте; снос не задан источником как решение
- **qaist** — число студентов. S74: 5 тыс. студентов; TWIN_networks: двойник: 40 тыс. → побеждает **S74**: 40 тыс. — весь кластер вузов Golden (S01/S03), не QAIST
- **school_gate_city_20_keleshek** — одна или две школы. S113: № 20, 1 550 учеников, 01.09.2026; S20: «Келешек» 900 мест, 02.2026; T_gov_alatau: 07.09.2026 открыта школа «Келешек» → побеждает **PLAN**: план: одна строка с двумя источниками до подтверждения; мощность берём 900 (госисточник)
- **kindergarten_gate_city_280** — существует ли. PLAN: ЖК Gate City «со школой № 20 и детсадом на 280 мест»; S21: «В районе нет детского сада» (10.2025) → побеждает **S21**: более поздний репортаж с места; статус planned
- **ethnoaul** — район. S78: Golden; S15: Growing → побеждает **S78**: источник 2025 года после корректировки генплана 09.2025; BES — 2023
- **house_of_culture_zhetygen** — мощность. S16: 280 мест (BES 02.2025); S26: 600 мест (Zakon.kz 02.2025) → побеждает **не решено**: оба источника 02.2025; на карту не влияет (участок 1 га), в панели показываем оба числа
- **mars_petcare** — 40-й км против «у Жетыгена». S80: 40-й км трассы, мкр Жетіген; PLAN: «на 40-м км трассы у самого Жетыгена»; OVT: по столбам OSM 40-й км лежит ≈ 12,8 км к ЮЗ от точки Жетыгена, в полигоне Golden → побеждает **S80**: километр — точная привязка ОВОС; «мкр Жетіген» — адресная принадлежность к городу, а не к селу; в 09.2025 участок рассматривался для Golden (S22)
- **mars_petcare** — годы. S80: стройка 08.2026–01.2029, эксплуатация с 2031 → побеждает **S80**: одна версия
- **growing_industry_types** — металлургия. S01: металлургическая промышленность в Growing; S22: в СЭЗ металлургия и «грязные» производства исключены → побеждает **S22**: правовой режим СЭЗ новее; генератор не ставит классы I–II без указания
- **griffin_logopark** — расстояния вдоль А-3. S82: 1,0 км до БАКАД; S82: 0,6 км до развязки А3 × Ынтымак – Жанадаур → побеждает **среднее**: по OSM эти два условия дают точки в ~0,4 км друг от друга; берём середину, допуск ±500 м
- **tlc_zhetygen** — место. PLAN: Growing «как есть с чипом «модель»: ТЛЦ «Жетыген»»; OVT: контур OSM «ТЛЦ Логистика», 31,6 га, у станции Жетыген → побеждает **OVT**: реальный контур на местности точнее модели; разрешено решением владельца 31.10
- **tlc_zhetygen** — площадь. S86: 51 га; OVT: 31,6 га в OSM → побеждает **S86**: OSM может покрывать только освоенную часть (20 га освоено по S86)
- **tlc_industrial_zone** — площадь. S86: 30 га; T_forbes_tlc_20230606: промзона 10 га → побеждает **S86**: более новый источник
- **oiz_tulip** — 23-й км А3 против Жанаарны. S88: 23-й км А3; S88: мкр Жанаарна, 2 км до ст. Жанаарна, 12 км до ст. Жетыген; OVT: по столбам OSM 23-й км А-3 лежит в Gate, ≈ 20 км к югу от Жанаарны → побеждает **S88 (Жанаарна)**: две независимые привязки к станциям согласуются с Жанаарной; километр, вероятно, считается от другого начала
- **dry_port** — район. S03: Growing; S01: Gate → побеждает **S03**: план и приложение № 727 ставят в Growing; там же действующий ТЛЦ у ж/д
- **frutta_fruit_art** — место Fruit Art. S22: FRUTTA рядом с АВЗ; S116: место Fruit Art не указано → побеждает **S22**: единственная привязка
- **airfield_zhetygen** — будущее. S24: «В перспективе его планируют переделать под пассажирский»; S03: новый аэропорт «Алатау» на западной границе → побеждает **S03**: генплан ставит пассажирский аэропорт отдельно
- **bus_cemetery** — существует ли. S25: есть (01.2024); T_bes_buses_20260512: вывезено в конце 2023 → побеждает **T_bes_buses_20260512**: более новый источник
- **space_comm_centre** — кампус на месте или рядом. S21: «рядом с действующим центром космической связи» (пересказ в alatau_objects.md № 31); S21: «кампус — на месте центра космической связи» (пересказ в transport_site.md §8) → побеждает **S21 «рядом»**: два пересказа одной статьи Vlast; R1 перечитывал формулировки 31.10.2026; действующий центр остаётся
- **airport_alatau** — мощность. S03: 15 млн пасс.; S65: 40 млн пасс. → побеждает **S03**: скорректированный генплан 09.2025 новее новостей 03.2025
- **airport_alatau** — год. S03: после 2040; T_gp388_zakon: генплан 2024: к 2030; TWIN_networks: двойник 2032–2036 → побеждает **S03**: последняя редакция генплана
- **airport_alatau** — место. S66: западная граница у Жанаарны; S65: 29 км от Алматы, 25 км от Конаева — ближе к самой Жанаарне, которая в ~18 км восточнее западной границы; T_konaev_gp_2026: генплан Конаева: севернее KAZ08 к Баканасу; T_ts_tca: Gate: «здесь же — ж/д узлы и аэропорт» → побеждает **S66 / план**: план прямо задаёт западную границу у Жанаарны; расстояния 29/25 км и версии Конаева/TCA — в отчёт
- **uam_center_eurasia** — район. S70: Growing (КГА, 29.10.2026); S69: Golden; S71: Golden → побеждает **S70**: самый новый источник, городской архитектурный комитет
- **uam_center_eurasia** — «рядом с Алматы». S19: у Алматы; S70: Growing — 25+ км от Алматы → побеждает **не решено**: место площадки не опубликовано
- **metro_line3_reserve** — будет ли. S58: предварительно 2027–2028; S60: пока не планируется (05.2026) → побеждает **S60**: более новое заявление вице-премьера; поэтому резерв
- **lrt_regional** — вид транспорта. S61: LRT Алматы – Алатау – Конаев; S03: 3 линии внутри города 76,2 км; S63: вариант маглева RETD → побеждает **S03**: генплан — для внутренней сети
- **kns_gate_city** — год. T_teng_20220513: построена к 05.2022; S50: единственный завершённый объект программы 2026 → побеждает **оба**: вероятно, достройка/реконструкция в 2026; на карте с 2022
- **road_works_2026** — объём. S43: 15 км новых; T_newtimes_20261015: 1,5 км новых → побеждает **S43**: официальный протокол совета
- **rail_bypass_zhetygen_kazybek** — длина. T_24kz_20250430: 75 км новой линии; T_bes_20250107: 123–130 км со станционными путями → побеждает **оба**: разное определение длины
- **ps_alma_500** — год ввода. T_kt_alma: 25.12.2012; T_kegoc_alma: акт 11.07.2013; OVT: start_date 2012-12-12 → побеждает **T_kegoc_alma**: акт госкомиссии
- **wwtp_4** — сколько КОС. S03: 4 КОС, по одной на район (вывод R1 из «в каждом районе»); T_gp727_zakon: «по 4 КОС и по 4 инфильтрационных бассейна в каждом районе» (пересказ R3) → побеждает **S03 / план**: план берёт 4 очистных (по одной на район); формулировка генплана в пересказах расходится

## Объекты, которые называет план, а исследование не ставит в точку

Точность `none` или `district_only` (место — по правилу) или нет геометрии. Генератор ставит их по norms.json / rules.json с чипом «модель qTwin».

Колонка «геометрия сейчас»: `twin_model` — точка/контур двойника с чипом «модель qTwin» (не источник); `нет` — генератор ставит по правилу.

| id | имя | точность | геометрия сейчас | действие | что известно о месте |
|---|---|---|---|---|---|
| iconic_complex | Iconic Complex (Alatau City Iconic Complex; Iconic Building-1) | district_only | twin_model | keep | Gateway District, «along the Almaty-Qonaev highway»; «его южная часть граничит с Алматы» (Forbes, пересказ) |
| iconic_tower_main | Главная башня Iconic | district_only | same_as | keep | в составе № 1 |
| iconic_tower_second | Вторая башня Iconic | district_only | same_as | keep | в составе № 1 |
| iconic_podium | Подиум Iconic | district_only | same_as | keep | в составе № 1; связан пешеходными галереями и террасами |
| iconic_offices_6 | Шесть малоэтажных офисных корпусов Iconic | district_only | same_as | add | вокруг башен № 2–3 |
| gate_district_ring | Кольцо и овальная площадь Gate District (модель) | none | twin_model | keep | вокруг Iconic (модель QTwin) |
| l7_lotte | L7 by Lotte — многофункциональный комплекс с гостиницей | none | twin_model | keep | «в Alatau City» |
| iconic_building_2 | Iconic Building-2 — туристический центр | district_only | нет | by_rule | побережье Капчагая (вывод) |
| green_tower_30 | 30-этажный комплекс у озера — «главный ориентир» Green | district_only | нет | by_rule | у Капчагайского водохранилища |
| k_smart_town | K-Smart Town / Alatau Smart City (KIND) | none | нет | by_rule | — |
| green_terraces | Террасное жильё и малоэтажная застройка вдоль набережной | district_only | нет | by_rule | набережная Капчагая |
| qaist | QAIST (филиал KAIST) | district_only | twin_model | keep | — |
| vocational_institute | Профтехинститут | district_only | нет | by_rule | — |
| schools_genplan | Школы по генплану (173 к 2050) | none | нет | by_rule | по квартальным центрам (место не дано) |
| kindergartens_genplan | Детские сады по генплану (227 к 2050) | none | нет | by_rule | — |
| medcluster_golden | Медицинский кластер Golden — две многопрофильные больницы | district_only | twin_model | keep | в центре образования, здравоохранения и спорта |
| hospitals_stage1 | Больницы 1-й очереди (по 500 коек) | district_only | нет | by_rule | — |
| polyclinics_genplan | Поликлиники по генплану | none | нет | by_rule | — |
| korean_clinics | Корейские клиники в Golden | district_only | нет | by_rule | — |
| k_park | K-Park | district_only | twin_model | keep | «сердце района Golden District» |
| sport_centre_hippodrome | Спортивный центр и ипподром | district_only | нет | by_rule | центр образования, здравоохранения и спорта |
| stadium_50k | Футбольный стадион на 50 тыс. мест | none | нет | remove | по Vlast: «к югу от села Коктерек» (пересказ) |
| resort_ircc | Интегрированный курортно-развлекательный центр | district_only | нет | by_rule | побережье Капчагайского водохранилища |
| f1_track | Трасса Формулы-1 | district_only | нет | by_rule | — |
| golf_diving | Гольф-поля, дайвинг-клубы | district_only | нет | by_rule | — |
| oceanarium_aquapark | Океанариум; всепогодный аквапарк | district_only | нет | by_rule | — |
| theme_parks | Тематические парки, «казахстанский аналог Диснейленда» | district_only | нет | by_rule | — |
| casino_zone | Казино / игорная зона | district_only | нет | by_rule | побережье Капчагая |
| marina_kapchagay | Пристань / марина, яхт-клубы | district_only | twin_model | keep | Капчагайское водохранилище |
| urban_beaches | Городские пляжи | district_only | нет | by_rule | «Urban beaches planned in the northern part» |
| expo_complexes | Выставочные комплексы | district_only | нет | by_rule | — |
| sand_spit_leisure | Центр автомобильного отдыха на песчаной косе | none | нет | add | песчаная коса Капчагая |
| danaflex | Завод гибкой упаковки (вероятно, «ДанаФлекс») | none | twin_model | keep | — |
| sunny_paper | Sunny Paper — гофрированная бумага | none | twin_model | keep | СЭЗ Alatau |
| g_trans | G-Trans Service | none | twin_model | keep | — |
| agro_processing_golden | Кластер агропереработки и логистический узел | district_only | нет | by_rule | — |
| dry_port | Сухой порт (генплан) | district_only | нет | by_rule | — |
| henkel_plant | Завод Henkel | none | нет | keep | — |
| mareven_food | Mareven Food | none | нет | keep | — |
| dachas_36 | 36 присоединённых дачных массивов | none | нет | keep | «под чашей озера» — «Механизатор» |
| uam_center_eurasia | UAM Center Eurasia — первый вертипорт | district_only | нет | by_rule | «вдоль республиканской трассы рядом с Алматы» |
| lrt_city | Городской LRT (генплан): 3 линии | none | нет | by_rule | маршруты не опубликованы |
| lrt_depots | Депо ЛРТ (3 линии) | none | нет | by_rule | — |
| river_tram | Речной трамвай | none | нет | by_rule | по рекам (река не указана) |
| a3_dubler | Дорога-дублёр вдоль трассы Алматы – Конаев (Gate) | district_only | нет | by_rule | вдоль А3 |
| gtes_doosan | Газовая электростанция 2×250 МВт (Doosan, с переходом на водород) | none | twin_model | by_rule | «в Alatau City» |
| datacenter_alatau_data_hub | ЦОД «Alatau Data Hub» (модель двойника) | none | twin_model | keep | — |
| fire_depots_genplan | Пожарные депо по генплану (37) | none | нет | by_rule | — |
| road_ia | Дорога республиканского значения IА «Алматы – Талдыкорган – Усть-Каменогорск» (проект) | none | нет | by_rule | по западной стороне города; трасса не опубликована |
| arterial_continuous_east | Магистраль непрерывного движения (восток, до Green) | none | нет | by_rule | «магистральная улица непрерывного движения с восточной стороны до района Green» (пересказ) |
| half_rings_3_4 | 3-е и 4-е полукольца | none | нет | by_rule | трассы не опубликованы |
| rail_agglomeration | Агломерационная ж/д | none | нет | by_rule | 1-я очередь: Алматы-1 → станция у БАКАД/А-3, 13,2 км (0,8 км в Алатау) |
| rail_sorting_station | Сортировочная станция | none | нет | by_rule | «между аэропортом и Қонаев» |
| micromobility_network | Велосеть и микромобильность | none | нет | by_rule | вдоль рек и к воде (план) |
| ps_arna_twin | ПС «Арна» 220/110 кВ (двойник) | none | twin_model | keep | — |
| substations_programme | Подстанции по дорожной карте: 11 (+15 в регионе), 2 во 2-м этапе | none | нет | by_rule | места не опубликованы (кроме «Кокпа-1») |
| ses_fields_twin | Поля СЭС двойника (320 МВт и ВИЭ 200 МВт) | none | twin_model | keep | — |
| kogtu_chp_10 | 10 газотурбинных ТЭЦ (КоГТУ) генплана | none | нет | by_rule | места не указаны |
| heat_pumps_green | Тепловые насосы на воде Капчагайского вдхр. (Green) | district_only | нет | by_rule | на воде Капчагайского водохранилища |
| water_intakes_4 | 4 водозабора (2 на Покровском и 2 на Талгарском МПВ) | none | нет | by_rule | Покровское и Талгарское месторождения подземных вод |
| pumping_stations_12 | 12 насосных станций (по 3 на район) | none | нет | by_rule | — |
| wwtp_4 | 4 очистных сооружения и 4 инфильтрационных бассейна (по одному на район) | none | нет | by_rule | «в каждом районе» |

## Прочие объекты на карте без места (geom null, не по ссылке на city.json)

| id | имя | статус | действие |
|---|---|---|---|
| gateway_district_som | Gateway District (мастер-план SOM) | planned | by_rule |
| intl_business_centre | Международный центр развития бизнеса (генплан) | planned | by_rule |
| ansa_hub | AÑSA HUB — многофункциональный центр + эндаумент-фонд | announced | by_rule |
| cn_investor_housing | Жилые и бизнес-центры китайского инвестора | announced | by_rule |
| green_tourist_centre | Туристический центр с крупными отелями, ЖК и ТЦ | planned | by_rule |
| golden_midrise | Среднеэтажные кварталы Golden | planned | by_rule |
| growing_polycentres | Жилые кварталы Growing с полицентрами | planned | by_rule |
| british_edu_hub | Образовательный хаб: британские вузы и школы | announced | by_rule |
| ambulance_genplan | Скорая помощь: 2 станции, 4 подстанции | planned | by_rule |
| german_med_cluster | Медицинский кластер шести немецких компаний | announced | by_rule |
| ethnoaul | Этноаул | announced | by_rule |
| mekhanizator_recreation | Рекреационная зона на месте дачного массива «Механизатор» | announced | by_rule |
| hyundai_green_food | Hyundai Green Food — производственно-логистический комплекс | announced | by_rule |
| khan_tengri_biopharma | Khan Tengri Biopharma | announced | by_rule |
| r_pharm | Фармзавод R-Pharm | announced | by_rule |
| steppe_pharma | Фармзавод Steppe Pharmaceuticals | announced | by_rule |
| etasa_fiber | Etasa Fiber | announced | by_rule |
| sugar_plant | Сахарный завод | announced | by_rule |
| tricycle_assembly | Сборка трициклов | announced | by_rule |
| evtol_plant | Сборка / производство eVTOL | announced | by_rule |
| saf_complex | Комплекс экоавиатоплива (SAF) и «зелёная» энергетика | announced | by_rule |
| sinomach_agro | Высокотехнологичный агропромышленный комплекс (Sinomach) | announced | by_rule |
| agropark | Агропарк | planned | by_rule |
| g2_power | Системы мониторинга на ИИ (G2 Power) | announced | by_rule |
| amk_ceratech | Элементы для промышленной очистки воды (AMK Ceratech) | announced | by_rule |
| keumjeong | Гибкие вентиляционные трубы (KEUMJEONG HI-TECH) | announced | by_rule |
| vitrosys_lab | Лаборатория клонирования деревьев и семян (Vitrosys) | announced | by_rule |
| proton_therapy | Центр протонной терапии | announced | by_rule |
| battery_complex | Комплекс производства аккумуляторов и СНЭ | announced | by_rule |
| ahlers_pilot | Пилот складирования / консолидации грузов (Ahlers) | announced | by_rule |
| dar_metall_recycling | Комплекс переработки отходов (D.A.R. Metall) | announced | by_rule |
| wilo_engineering | Инжиниринговый центр Wilo | announced | by_rule |
| mtc_woodworking | Деревообработка (MTC) | announced | by_rule |
| growing_industry_types | Предприятия генплана в Growing (пищевая, химия, металлургия, машиностроение, лёгкая, стройиндустрия) | planned | by_rule |
| integrity_birlik_tlc | ТЛЦ класса A Integrity Logistics (СИЗ «Бірлік») | announced | by_rule |
| integrity_400ha | Логистико-производственная зона Integrity Logistics (~400 га) | planned | by_rule |
| industrial_north_kosozen | Промзона севернее Косозена | planned | by_rule |
| rhenus_hub | Транспортно-индустриальный хаб Rhenus Logistics | announced | by_rule |
| cimc_logistics_dc | Логистика, ЦОДы и цифровая инфраструктура CIMC | announced | by_rule |
| german_warehouses | Склады класса A шести немецких компаний | announced | by_rule |
| dcg_compute | Вычислительные мощности, склады, энергетика DCG | announced | by_rule |
| huawei_smart_city | Smart City, облака, ЦОДы Huawei | announced | by_rule |
| landfill_karaoy | Мусорный полигон (Караойский с. о.) | built | keep |
| lrt_regional | LRT Алматы – Алатау – Конаев | announced | by_rule |
| road_yntymak_zhanadaur | Дорога Ынтымак – Жанадаур | built | keep |
| exit_kokterek | Съезд на Коктерек | built | keep |
| road_growing_10km | Дорога 10,3 км с путепроводом 400 м (Growing) | planned | by_rule |
| road_alfarabi_bakad | Дорога 1,6 км от ул. аль-Фараби до БАКАД (Gate) | planned | by_rule |
| road_almaty_zhetygen | Областная дорога Алматы – Жетыген – Капчагайское вдхр.; путепровод на км 6,8 | built | keep |
| moyynkum_sands | Пески Мойынкум | built | by_rule |
| heat_rk1 | Районная котельная РК-1 | planned | by_rule |
| grs_new_2 | Две новые ГРС (200 000 и 250 000 м³/ч) | planned | by_rule |
| storm_basins_29 | Ливневая канализация: 29 бассейнов | planned | by_rule |
| waste_new_sites | Новые полигоны, завод сортировки и МСЗ | planned | by_rule |
| settlement_kokterek | Коктерек | built | keep |
| settlement_pokrovka | Покровка | built | keep |

## Высотки в 30 км от аэродрома / будущего аэропорта (правило №16)

- iconic_tower_main: высота из источника; до КТА Жетыген 35.1 км, до модели аэропорта 24.3 км → нужно согласование: True
- iconic_tower_second: высота из источника; до КТА Жетыген 35.1 км, до модели аэропорта 24.3 км → нужно согласование: True
- green_tower_30: этажность ≥ 15 ⇒ вероятно ≥ 50 м (вывод); до КТА Жетыген None км, до модели аэропорта None км → нужно согласование: проверить после размещения
- gate_city_new_quarters: этажность ≥ 15 ⇒ вероятно ≥ 50 м (вывод); до КТА Жетыген 39.3 км, до модели аэропорта 27.6 км → нужно согласование: True

## Зоны развязок двойника (film_roads) без съездов OSM в городе

Строки реестра для них нет: развязка у съездов OSM вне полигона города — реальная, но за пределами города (контекст карты); зона без съездов OSM — только модель двойника, генератор решает её по матрице узлов norms.json или убирает.

| x | z | r | до оси А-3, м | до оси БАКАД, м | ближайший кластер съездов OSM, м | в полигоне города | вывод |
|---|---|---|---|---|---|---|---|
| -11151.3 | -20521.2 | 324 | 8300 | 0 | 25 | нет | реальная развязка OSM вне города: контекст |
| 1412.8 | -15115.4 | 270 | 3542 | 6209 | 4350 | нет | только в двойнике: по матрице узлов или убрать |
| 7214.0 | -25349.9 | 288 | 10428 | 28 | 57 | нет | реальная развязка OSM вне города: контекст |
| 994.0 | 26490.3 | 270 | 2 | 46775 | 30 | нет | реальная развязка OSM вне города: контекст |

## Объекты двойника, которые переезжают (action = move)

- pepsico: было «landmark:pepsico (8500, 940) в Growing» → стало (-3696, -21440), Gate; план: «Griffin Logopark и PepsiCo ... оба переносим в Gate»; источник — мкр Ынтымак
- mars_petcare: было «landmark:mars (8806, 1370)» → стало (-614, -2226), Growing; план: «Mars (40-й км А-3 у Жетыгена)»; точка — 40-й км по километровым столбам OSM, восточная сторона трассы (А3 к западу от участка, как в S80)
- griffin_logopark: было «landmark:griffin (−5713, 1735) в Growing» → стало (-2441, -19107), Gate; план: «Griffin — у развязки А-3 × БАКАД ... переносим в Gate»; точка между 1,0 км от узла с БАКАД и 0,6 км до следующей развязки к северу
- tlc_zhetygen: было «landmark:tlc (7870, 9941)» → контур OSM, Green; OSM даёт реальный контур «ТЛЦ Логистика» у ст. Жетыген в ~1,8 км от точки двойника; решение владельца 31.10: готовые объекты можно двигать, если новое место лучше
- airport_alatau: было «landmark:airport (−5900, 8300), площадка 1600×3800, 2032–2036; станция ЛРТ (−6235.5, 7339)» → стало (-16000, 1500), Growing; решение владельца 31.10.2026: центр единственной ВПП 4 000 × 45 м, курс 095°/275°, (−16000, 1500), после 2040 (схема Growing-запад, city.json airport_new); было по плану «Переносим к западной границе, год появления 2041 и позже» — западная граница города на широте Жанаарны, внутрь на 1,9 км (модель)
- airport_rail_station: было «станция ЛРТ аэропорта (−6235.5, 7339)» → стало (-15035, 2554), Growing; по схеме Growing-запад: вокзал у терминала, в конце ж/д ветки и у конечной ЛРТ (не на ВПП); было — вместе с аэропортом (same_as)
- water_intake_gate_city: было «networks.json wi_2 (−324, −16461)» → стало (-3911, -23291), Gate; у Gate City; wi_2 двойника стоит в ~6 км севернее
