# Alatau City — как открыть, запустить и собрать проект

Что это за проект и как он устроен — в `context.md`.

## 0. Только посмотреть (без Unity)

1. Откройте папку `Build_Windows` и запустите `AlatauCity.exe`.
2. Папку целиком не разбирайте: рядом с exe должны лежать `AlatauCity_Data`, `MonoBleedingEdge`, `D3D12` и `UnityPlayer.dll`.
3. Если Windows SmartScreen предупредит о неизвестном издателе: «Подробнее» → «Выполнить в любом случае».

Приложение открывается на весь экран, 1920×1080. Выход — Alt+F4.

## 1. Что нужно для работы с проектом

| | |
|---|---|
| ОС | Windows 10/11 x64 (на macOS проект тоже откроется, но проверялся только на Windows) |
| Unity | **6000.0.84f1** — ровно эта версия; другие версии Unity 6 могут переимпортировать проект с отличиями |
| Модули Unity | Windows Build Support (Mono) — ставится вместе с редактором для Windows |
| Пакеты | Внешних нет, только встроенные модули Unity (`Packages/manifest.json`) |
| Железо | Видеокарта с DirectX 11/12, от 16 ГБ ОЗУ, около 8 ГБ на диске после первого импорта |

Как установить нужную версию Unity:
- В Unity Hub: **Installs → Install Editor → Archive** (откроется страница архива https://unity.com/releases/editor/archive).
- Найдите **6000.0.84f1** и нажмите «Install» (откроется в Hub).

## 2. Открыть проект

1. **Распакуйте архив в короткий путь**, например `C:\Work\AlatauCity_DigitalTwin`. Длинные пути Windows (больше 260 символов) могут сломать импорт.
2. Unity Hub → **Projects → Add → Add project from disk** → выберите папку **`UnityProject`** (в ней лежат `Assets`, `Packages`, `ProjectSettings`).
3. Откройте проект в Unity 6000.0.84f1. **Первый запуск займёт 10–20 минут:** Unity создаёт папку `Library` и сжимает текстуры карты 8K. Это нормально, его не нужно прерывать.
4. Сцена `Assets/Scenes/AlatauCity.unity` откроется сама. Если не открылась, откройте её из окна Project.
5. Если сцены нет или папка `Assets/Generated` пуста, выполните меню **Alatau City → Rebuild Scene** (1–2 минуты). Сцена и меши пересоберутся из `Assets/CityData`.

## 3. Запустить в редакторе

1. Окно **Game**: разрешение **Full HD (1920×1080)**, режим **Play Maximized**. Работает и 1366×768 (компактная раскладка).
2. Нажмите **Play**. Интерфейс строится сам: в сцене нет UI-объектов, их создаёт `TwinUI.cs` при старте. Данные двойника подгружаются за 1–3 секунды.
3. Слева — иконки модулей: Обзор, Стройка, Прогноз, Инфраструктура, Ситуационный центр, ИИ-управление. По центру шапки — выбор района, справа — сценарий и год.

### Управление

| Действие | Мышь / тачпад | Клавиши |
|---|---|---|
| Сдвиг карты | перетаскивание левой кнопкой | W A S D или стрелки |
| Поворот | правая кнопка или Alt + перетаскивание | Q / E |
| Наклон | — | R / F |
| Масштаб | колесо | Z / X (или + / −), Shift — быстрее |
| Ракурсы | кнопки в нижней панели | 1–6 — районы и виды, Home или 0 — обзор, T — сверху |
| Год | шкала внизу, кнопка «Пуск» | Пробел — проигрывание, PageUp / PageDown — ±1 год |
| Паспорт здания | клик по зданию | — |
| Презентация (авто-тур, 16 шагов, ~6 мин) | кнопка внизу левой панели или иконка в шапке | F5 — старт/стоп, Пробел — пауза, ← → — шаги, Esc — выход |

## 4. Собрать Windows-версию

- **Alatau City → Build Windows** собирает `Builds/Windows/AlatauCity.exe` за 1–2 минуты; итог около 690 МБ. Скрипт `Assets/Editor/AlatauBuild.cs` сам выставляет полноэкранный режим 1920×1080 и название «Alatau City · Digital Twin».
- Можно и вручную: **File → Build Profiles → Windows**, сцена `Assets/Scenes/AlatauCity.unity`, Architecture x86_64 → **Build**.
- **Обязательно** с exe должна поехать папка `AlatauCity_Data/StreamingAssets/twin`: в ней данные двойника. Unity копирует её сама.

## 5. Меню Alatau City

| Пункт | Что делает |
|---|---|
| Rebuild Scene | Заново строит сцену и меши `Assets/Generated` из `Assets/CityData` |
| Setup UI assets | Пересоздаёт `Resources/UI/TwinPanel.asset` и `TwinTheme.tss`, если UI не показывается |
| Build Windows | Сборка в `Builds/Windows` |
| Export ZIP for team | Собирает такой же архив, как этот: проект без `Library`, сборка, документы из `_package` |

## 6. Перегенерировать данные (не обязательно)

Всё, что нужно для работы, уже лежит в проекте. Генераторы нужны, только если вы меняете модель, нормы или карту. Скрипты лежат в `UnityProject/Tools/twin_gen`, подробности — в их `README.md`.

1. Установите Python 3.11+ и зависимости:
   ```
   pip install numpy scipy shapely networkx numba pillow
   pip install bpy==5.2.2     # только для extract_blend.py и blend_export.py; bpy требует ту версию Python, под которую собран
   ```
2. Синтетика двойника (результат — `Assets/StreamingAssets/twin/*.json`, seed 2050, детерминированно). Нужен исходный `Alatau_City_3D.blend` из набора QTwin — в архив он не входит:
   ```
   python -I extract_blend.py Alatau_City_3D.blend blend_geo.json
   python gen_roads.py blend_geo.json roads.pkl
   python gen_twin.py ../../Assets/CityData/buildings.csv blend_geo.json roads.pkl ../../Assets/StreamingAssets/twin
   python gen_risk.py ../../Assets/CityData/buildings.csv blend_geo.json ../../Assets/StreamingAssets/twin/risk.json
   python validate_twin.py ../../Assets/CityData/buildings.csv ../../Assets/StreamingAssets/twin
   ```
3. Карта-подложка (`map_plan.png`, `map_nature.png`, `map_dev.png`):
   ```
   python gen_map.py ../../Assets ../../Assets/Resources/Map
   ```
4. Геометрия города, только при изменении blend-файла. Скрипт лежит в `Tools`, на уровень выше `twin_gen`:
   ```
   python -I ../blend_export.py Alatau_City_3D.blend ../../Assets/CityData <манифест QTwin .csv>
   ```
   Затем в Unity выполните **Alatau City → Rebuild Scene**.

Формула сценариев в Python (`twin_common.effective_year`) должна совпадать с C# (`TwinScenario.EffectiveYear`). Если меняете одну, меняйте и другую.

## 7. Если что-то не так

| Проблема | Что сделать |
|---|---|
| Здания или земля розовые (нет шейдера) | Дождитесь окончания импорта; затем правый клик по `Assets/Shaders` и `Assets/Resources/Shaders` → **Reimport** |
| После Play нет интерфейса | **Alatau City → Setup UI assets**, затем снова Play |
| Пустая сцена, нет города | **Alatau City → Rebuild Scene** |
| Карта старая или пёстрая, не растёт по годам | Проверьте, что в `Assets/Resources/Map` есть три PNG; правый клик → **Reimport** (импорт настраивает `Editor/AlatauMapImport.cs`) |
| Панели пустые, цифр нет | Нет данных: проверьте `Assets/StreamingAssets/twin/*.json`, ошибки смотрите в Console с префиксом `[Alatau]` |
| Тормозит на слабом ноутбуке | Game view → меньшее разрешение; Quality → ниже тени (сцена настроена на тени до 9 км) |
| Клавиши не двигают камеру | Курсор стоит в поле ввода ИИ-ассистента — кликните по карте; во время авто-тура камера управляется туром |
