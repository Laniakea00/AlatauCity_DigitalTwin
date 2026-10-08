# twin_gen — синтетические данные цифрового двойника Alatau City

Детерминированный генератор (seed 2050) → `Assets/StreamingAssets/twin/*.json`. Все числа — модель, не официальные данные.

```
pip install --break-system-packages bpy==5.2.2 scipy shapely networkx numba
python3 -I extract_blend.py Alatau_City_3D.blend blend_geo.json        # оси улиц, ЛРТ, трассы, объекты генплана
python3 gen_roads.py blend_geo.json roads.pkl                          # граф дорог
python3 gen_twin.py Assets/CityData/buildings.csv blend_geo.json roads.pkl Assets/StreamingAssets/twin
python3 gen_risk.py Assets/CityData/buildings.csv blend_geo.json Assets/StreamingAssets/twin/risk.json   # паводки (модель)
python3 validate_twin.py Assets/CityData/buildings.csv Assets/StreamingAssets/twin   # проверка балансов
```

| Файл | Содержимое |
|---|---|
| roads.json | граф дорог (узлы, рёбра с полилинией, класс, год открытия по 4 сценариям) |
| networks.json | объекты инфраструктуры (этапы ввода, мощность и спрос по годам и сценариям) и магистральные сети вдоль улиц |
| loads.json | жители, рабочие места, нагрузки по районам; баланс «спрос / мощность / дефицит»; социальная инфраструктура |
| construction.json | по каждому зданию: длительность стройки, генподрядчик, задержка; S-кривые план/факт; ЛРТ по очередям |
| finance.json | CAPEX по годам, районам, назначению и источникам; инфраструктура по видам (млрд ₸, цены 2026) |
| traffic.json | утренний час пик: загрузка рёбер (v/c×100) на 2030–2050 по сценариям + KPI |
| scenarios.json | описание сценариев |

Нормы и допущения — `norms.py` (с источниками). Формула сценариев в `twin_common.effective_year` должна совпадать с `TwinScenario.EffectiveYear` (C#).
Заложенные «ошибки плана» базового сценария (их должен показать двойник): ПС 220/110 «Golden» 2-я очередь +3 года (дефицит ~27 МВт в 2035),
котельная «Growing-1» 2-я очередь +3 года, КОС №4 3-я очередь +3 года.
