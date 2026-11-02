"""Sources cited in research/transport_site.md, research/norms.md and the twin code
that are not in the S01-S149 table of research/alatau_objects.md section 7.

Each entry: code -> (publisher / title, url, date as printed by the research file).
Dates are copied from the research files; "б/д" means the page shows no date.
"""

EXT = {
    # transport_site.md, section 1.1 (coordinates)
    "T_ruwiki_alatau": ("ru.wikipedia — Алатау (город)", "https://ru.wikipedia.org/wiki/Алатау_(город)", "просмотр 10.2026"),
    "T_riteme_zhetygen": ("wiki.riteme.site — Zhetygen (зеркало en.wikipedia)", "https://wiki.riteme.site/wiki/Zhetygen", "просмотр 10.2026"),
    "T_bamwor_zhetigen": ("bamwor.com — Zhetigen", "https://bamwor.com/en/countries/kazakhstan/cities/zhetigen", "б/д"),
    "T_dic_airfield": ("dic.academic.ru — копия ru.wikipedia «Жетыген (аэродром)»", "https://dic.academic.ru/dic.nsf/ruwiki/1301773", "б/д"),
    "T_teng_20240110": ("Tengrinews — G4 City: что известно о новом городе", "https://tengrinews.kz/kazakhstan_news/g4-city-sputnik-almatyi-izvestno-novom-kazahstanskom-gorode-522654/", "10.01.2024"),
    "T_teng_20240523": ("Tengrinews — репортаж «Новый город, на который у Казахстана большие надежды»", "https://tengrinews.kz/article/novyiy-gorod-kotoryiy-kazahstana-bolshie-nadejdyi-reportaj-2454/", "23.05.2024"),
    "T_ruwiki_kapchagay": ("ru.wikipedia — Капчагайское водохранилище", "https://ru.wikipedia.org/wiki/Капчагайское_водохранилище", "просмотр 10.2026"),
    "T_otegen_wiki": ("en.wikipedia — Otegen Batyr", "https://en.wikipedia.org/wiki/Otegen_Batyr", "просмотр 10.2026"),
    "T_ecoportal_bak": ("ecoportal.kz — заключение по скважинам Alatau Green Production у с. Панфилово", "https://ecoportal.kz/Rubric/RubService/LoadFile/46881", "19.09.2024"),
    "T_konaev_wiki": ("wiki.riteme.site — Qonaev", "https://wiki.riteme.site/wiki/Qonaev", "просмотр 10.2026"),
    # transport_site.md, section 4 (existing transport)
    "T_gp727_zakon": ("zakon.uchet.kz — генплан г. Алатау, пост. № 727 (гл. 8)", "https://zakon.uchet.kz/rus/docs/P2500000727", "09.09.2025"),
    "T_gp388_zakon": ("zakon.uchet.kz — генплан г. Алатау, пост. № 388", "https://zakon.uchet.kz/rus/docs/P2400000388", "17.05.2024"),
    "T_teng_20230414": ("Tengrinews — платную трассу Алматы – Усть-Каменогорск перенесут", "https://tengrinews.kz/kazakhstan_news/platnuyu-trassu-almatyi-ust-kamenogorsk-perenesut-predelyi-496465/", "14.04.2023"),
    "T_informburo_bakad": ("Informburo — всё о БАКАД", "https://informburo.kz/fotoreportazh/vsyo-o-bakad-stroitelnye-texnologii-skorost-peremeshheniya-sposoby-oplaty", "15.06.2023"),
    "T_inform_overpass_km68": ("Inform.kz — новый путепровод в сторону Алатау", "https://www.inform.kz/ru/probki-naviezde-izalmati-noviy-puteprovod-poyavitsya-vstoronu-alatau-c3fe5f", "13.02.2025"),
    "T_inform_roads2026": ("Inform.kz — где начнут строить дороги в Алматинской области в 2026 году", "https://www.inform.kz/ru/gde-nachnut-stroit-dorogi-v-almatinskoy-oblasti-v-2026-godu-d0a005", "б/д"),
    "T_railways_950": ("railways.kz — new road bridge opened for traffic, city of Alatau", "https://railways.kz/en/news2026/new-road-bridge-opened-traffic-city-alatau/", "20.06.2026"),
    "T_baq_20251011": ("Baq.kz — Алатау: место надежд и ям", "https://rus.baq.kz/alatau-mesto-nadezhd-i-yam-kak-zhivut-v-gorode-buduschego-segodnya_300024405/", "11.10.2025"),
    "T_azattyq_20240119": ("Azattyq Asia — репортаж из Алатау", "https://www.azattyqasia.org/a/kazakhstan-almaty-region-alatau-reportage/32777038.html", "19.01.2024"),
    "T_teng_20260213": ("Tengrinews — пригородный поезд: сколько жители мёрзнут в ожидании", "https://tengrinews.kz/article/20-minut-chasa-skolko-jiteli-prigoroda-mrznut-ojidanii-3784/", "13.02.2026"),
    "T_forbes_20121222": ("Forbes.kz — второй путь в Китай открыт", "https://forbes.kz/articles/vtoroy_put_v_kitay_otkryit", "22.12.2012"),
    "T_railnews_20260728": ("rail-news.kz — обводная линия в обход узла станции Алматы перешла на цифровое управление", "https://rail-news.kz/ru/news/24376-obvodnaia-liniia-v-obxod-uzla-stancii-almaty-peresla-na-cifrovoe-upravlenie.html", "28.07.2026"),
    "T_kursiv_20260614": ("Kursiv — обходная линия", "https://kz.kursiv.media/?p=6977335", "14.06.2026"),
    "T_24kz_20250430": ("24.kz — как новая ж/д линия избавит Алматы от перегруза", "https://24.kz/ru/news/social/707804-kak-novaya-zh-d-liniya-izbavit-almaty-ot-peregruza", "30.04.2025"),
    "T_bes_20250107": ("BES.media — строительство железной дороги в обход Алматы через Алатау", "https://bes.media/news/stroitelstvo-zheleznoy-dorogi-v-obhod-almati-cherez-noviy-gorod-alatau-vo-skolko-oboydyotsya-proekt-i-kto-ego-vipolnyaet/", "07.01.2025"),
    "T_forbes_tlc_20230606": ("Forbes.kz — открылся ТЛЦ «Жетыген»", "https://forbes.kz/articles/v_kazahstane_otkryilsya_mejdunarodnyiy_transportno-logisticheskiy_tsentr_jetyigen", "06.06.2023"),
    "T_bes_tlc_20240611": ("BES.media — ТЛ-хаб в Алатау: ещё $150 млн", "https://bes.media/amp/transportno-logisticheskiy-hab-v-alatau-dlya-razgruzki-dorog-almati-investiruyut-eshyo-150-mln-dollarov-a446d3/", "11.06.2024"),
    "T_informburo_train": ("Informburo — поезд Алматы – Конаев совершил первый рейс", "https://informburo.kz/novosti/poezd-almaty-konaev-sovershil-svoj-pervyj-rejs", "11.11.2022"),
    "T_inform_uam": ("Inform.kz — аэротакси, СЭЗ и особый статус", "https://www.inform.kz/ru/aerotaksi-sez-i-osobiy-status-kak-razvivaetsya-gorod-alatau-fdcd0797", "после 19.05.2026"),
    "T_alataunews_20250304": ("alataunews.kz — новый аэропорт построят в Алматинской области", "https://alataunews.kz/ru/novosti/region/novyj-aeroport-postroyat-v-almatinskoj-oblasti/", "04.03.2025"),
    "T_konaev_gp_2026": ("gov.kz — проект генплана Конаева (docx)", "https://www.gov.kz/uploads/2026/2/27/fd460cbd6ec3a902931cf1bc441179d0_original.153409.docx", "27.02.2026"),
    # transport_site.md, section 6 (engineering)
    "T_teng_20220513": ("Tengrinews — Гейт Сити: что сейчас происходит на месте будущего города", "https://tengrinews.kz/fotoarchive/geit-siti-byt-seicas-proisxodit-meste-budushhego-goroda-1438/", "13.05.2022"),
    "T_newtimes_20261015": ("NewTimes — на развитие Алатау выделили 35 млрд тенге", "https://newtimes.kz/obshchestvo/224862-na-razvitie-alatau-vydelili-35-mlrd-tenge-kuda-poidut-dengi", "15.10.2026"),
    "T_kegoc_alma": ("KEGOC — инвестпроекты, ПС 500 кВ «Алма»", "https://www.kegoc.kz/ru/about/investicionnye-proekty/18393/?category=31", "б/д"),
    "T_kt_alma": ("kt.kz — введена в работу новая подстанция 500 кВ «Алма»", "https://www.kt.kz/rus/ekonomika/vvedena_v_rabotu_novaja_podstancija_500_kv_alma_1153566870.html", "25.12.2012"),
    "T_kapital_20260814": ("Kapital.kz — масштабное отключение света в Алматы и области", "https://kapital.kz/gosudarstvo/151672/masshtabnoe-otklyuchenie-sveta-proizoshlo-v-almaty-i-almatinskoj-oblasti.html", "14.08.2026"),
    "T_kazpravda_tec3": ("Казправда — модернизация Алматинской ТЭЦ-3", "https://kazpravda.kz/n/modernizatsiya-almatinskoy-tets-3-zavershitsya-v-2026-godu/", "б/д"),
    "T_teng_20260716": ("Tengrinews — как устроена Капчагайская ГЭС", "https://tengrinews.kz/article/baklanyi-katamaranyi-milliardyi-kilovatt-energii-ustroena-4245/", "16.07.2026"),
    "T_kapital_20260115": ("Kapital.kz — инфраструктурные проекты на 365,1 млрд тенге", "https://kapital.kz/economic/144104/infrastrukturnye-proekty-na-3651-mlrd-tenge-planiruyut-realizovat-v-alatau-do-2028-goda.html", "15.01.2026"),
    "T_ecoportal_talgar": ("ecoportal.kz — Талгарское МПВ", "https://ecoportal.kz/Rubric/RubService/LoadFile/50760", "23.12.2024"),
    "T_inform_2026_networks": ("Inform.kz — дороги, газ, интернет и жильё: что строят в Алатау", "https://www.inform.kz/ru/dorogi-gaz-internet-i-zhile-chto-stroyat-v-novom-gorode-alatau-d2831e", "2026"),
    "T_inform_2026_twoyears": ("Inform.kz — Алатау спустя два года", "https://www.inform.kz/ru/alatau-spustya-dva-goda-chto-izmenilos-v-novom-gorode-3b163a", "начало 2026"),
    "T_bes_sorbulak": ("BES.media — Сорбулак заполнен на 77 %", "https://bes.media/news/sorbulak-zapolnen-na-77-est-li-ugroza-proryva-ogromnogo-nakopitelya-pod-almaty/", "09.10.2026"),
    "T_bes_buses_20260512": ("BES.media — от Жетыгена до Кайназара: старые автобусы", "https://bes.media/news/ot-zhetigena-do-kaynazara-kak-starie-avtobusi-almati-stali-metallolomom/", "12.05.2026"),
    "T_ovos_bypass": ("ecoportal.kz — ОВОС обходной линии, нетехническое резюме", "https://ecoportal.kz/Public/PubHearings/LoadFile/134897", "б/д"),
    "T_ektu_kaskelen": ("ВКТУ — гидрология р. Каскелен, стр. 239–246", "https://storage.ektu.kz/nextcloud/index.php/s/9WbWn56zL4FExfA/download/239-246.pdf", "2024"),
    "T_zakon_bak": ("Zakon.kz — Большой Алматинский канал", "https://www.zakon.kz/stati/6457242-kak-bolshoy-almatinskiy-kanal-spas-region-ot-zasukhi-i-kak-vyglyadit-seychas.html", "22.11.2024"),
    "T_nur_20230912": ("NUR.KZ — обмеление Капшагая", "https://www.nur.kz/society/2036299-voda-ushla-daleko-ot-berega-obmelenie-kapshagaya-obyasnili-v-ministerstve-vodnyh-resursov/", "12.09.2023"),
    "T_24kz_20261027": ("24.kz — в Alatau City начали строить первый небоскрёб", "https://24.kz/ru/news/social/801976-v-alatau-city-nachali-stroit-pervyj-v-gorode-neboskrjob", "27.10.2026"),
    "T_teng_en_20260602": ("en.Tengrinews — dozens of investment projects worth 2 trillion tenge", "https://en.tengrinews.kz/kazakhstan_news/dozens-of-investment-projects-worth-2-trillion-tenge-tokayev-271723/", "02.06.2026"),
    "T_gov_alatau": ("gov.kz — акимат г. Алатау", "https://www.gov.kz/memleket/entities/almobl-alatau?lang=ru", "б/д"),
    "T_teng_dachas_20240316": ("Tengrinews — какие дачи присоединили к сёлам и городам области", "https://tengrinews.kz/news/kakie-dachi-prisoedinili-selam-gorodam-almatinskoy-oblasti-529422/", "16.03.2024"),
    "T_kazpravda_20240116": ("Казправда — Алатау станет мегаполисом", "https://kazpravda.kz/n/alatau-stanet-megapolisom/", "16.01.2024"),
    "T_almatytv_20250930": ("Almaty.tv — город будущего: строительство Алатау стартует в 2026", "https://almaty.tv/ru/news/obschestvo/gorod-budushchego-v-kazakhstane-stroitelstvo-alatau-startuet-uzhe-v-2026-godu", "30.09.2025"),
    "T_ts_tca": ("Times of Central Asia — по пересказу transport_site.md §2.1 (URL в строке не указан)", None, "б/д"),
    # twin code citations without URL (LandmarkData.cs); kept as the twin states them
    "TWIN_ps_arna": ("код двойника LandmarkData.cs: «primeminister.kz, Qazinform» (URL в исследовании не найден)", None, "15.01.2026 / 03.02.2026"),
    "TWIN_networks": ("StreamingAssets/twin/networks.json двойника (модель QTwin, без внешнего источника)", None, "06.10.2026"),
}

# Owner decisions and project documents (not public sources; used for actions)
DOCS = {
    "OWNER_3110": "решение владельца 31.10.2026 18:48Z (COMMON_RULES, Stage 7)",
    "PLAN": "plan/plan.md (план перерисовки карты, Stage 7)",
    "OWNER_3110_HV": "решение владельца 31.10.2026 (утверждение схем уровня 0, COMMON_RULES, Stage 7, levels 1–2): ВЛ 220 кВ через центры Gate и Golden — в кабель или в обход ядра",
    "SPEC_GATE": "tools/map/spec/gate.json — утверждённая схема Gate (уровень 1)",
}
