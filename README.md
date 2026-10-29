# Alatau City — Digital Twin (Unity)

Цифровой двойник Alatau City на Unity: шкала времени 2026–2050 по генплану, районы Gate / Golden / Growing / Green, реальные инвестпроекты, ЛРТ, стройка, прогноз, инфраструктура, ситуационный центр, ИИ-ассистент и презентация для инвесторов по зонам.

Подробное описание проекта — [README_RU.md](README_RU.md), [startup.md](startup.md), [context.md](context.md), ТЗ и прогресс — в [docs/](docs/).

## Как открыть (первый раз)
1. Unity **6000.0.84f1** (Built-in RP). В Unity Hub: *Add project from disk* → папка `UnityProject` (именно в склонированном репозитории, а не старая копия из архива).
2. Дальше всё само (`Assets/Editor/AlatauProjectSetup.cs`): при открытии проект проверяет версию Unity, собирает город `Assets/Generated` из `Assets/CityData`, если его нет (несколько минут, ~830 МБ, в git не хранится), фото-текстуры материалов, открывает сцену `Assets/Scenes/AlatauCity.unity`, ставит качество **Ultra** и окно Game **Full HD 1920×1080, Play Maximized**. Повторить вручную: меню **Alatau City → Привести проект к эталону**.
3. Play.
4. Сборка под Windows: **Alatau City → Build Windows**; без интерфейса (сервер сборки):
   `Unity.exe -batchmode -quit -projectPath UnityProject -executeMethod AlatauCity.EditorTools.AlatauBuild.BuildWindowsCI -logFile build.log`

Файлы `Assets/Generated` получают одинаковые id на всех машинах (по имени файла), поэтому сцена из git работает у всех. Если после автосборки GitHub Desktop показывает изменённую `AlatauCity.unity` — её можно спокойно откатить (Discard) или закоммитить: она одинаковая.

## Структура
- `UnityProject/Assets/Scripts/DigitalTwin` — код двойника (модули, UI, слои, презентация `TwinTour.cs`)
- `UnityProject/Assets/Scripts/DigitalTwin/Landmarks` — реальные объекты, ЛРТ, метки, паспорта
- `UnityProject/Assets/Shaders`, `Assets/Resources/Shaders` — шейдеры (здания, земля, объекты)
- `UnityProject/Assets/CityData` — исходные данные генплана
- `UnityProject/Tools` — Python-генераторы данных
- `web/` — старая веб-версия (three.js)
- [docs/DEPLOY_WEB.md](docs/DEPLOY_WEB.md) — план вывода двойника на домен

## Работа в команде

### Почему git справляется, хотя папка весит больше 1 ГБ
- В git хранится только то, что нельзя пересобрать: код, шейдеры, данные, текстуры (≈ 150–200 МБ, самый большой файл — 34 МБ).
- Остальное каждый собирает у себя и в git не попадает (`.gitignore`): `Library/` — кэш Unity, `Assets/Generated/` (~830 МБ), `Builds/`, `Temp/`, `Logs/`, `UserSettings/`.
- Ограничения GitHub: файл до 100 МБ (на 50 МБ — предупреждение), репозиторий желательно до 1–5 ГБ. Мы далеко от обоих.

### Подключить коллегу (один раз)
1. Владелец репозитория: GitHub → `Settings → Collaborators → Add people` → логин или почта коллеги.
2. Коллега принимает приглашение, ставит **GitHub Desktop** и через **Unity Hub** — Unity **6000.0.84f1**.
3. GitHub Desktop → `File → Clone repository` → `AlatauCity_DigitalTwin`.
4. Unity Hub → `Add project from disk` → папка `UnityProject`. Первый импорт 10–20 минут (собирается `Library/`).
5. Unity при первом открытии сам соберёт город и откроет сцену (см. «Как открыть»), затем Play.

### Каждый день
1. Перед работой: GitHub Desktop → **Fetch origin → Pull**.
2. Своя ветка на задачу: `Current branch → New branch` (например `ui-chart`, `textures-green`).
3. Коммиты маленькие и с понятным текстом; **Push** в свою ветку.
4. Готово — **Create Pull Request** на GitHub, второй человек смотрит и нажимает Merge в `main`.
5. После слияния все делают Pull.

### Как не ломать друг другу работу
- Сцену `AlatauCity.unity` и общие префабы одновременно правит один человек — договориться в чате. Код (`.cs`), шейдеры и данные можно править параллельно, git сольёт сам.
- Не коммитить `Library/`, `Assets/Generated/` и сборки — они уже в `.gitignore`.
- Файлы больше 50 МБ в репозиторий не класть (видео, сырые облака точек, архивы) — их держать на общем диске и класть в проект ссылкой.
- Unity уже настроен для git: сериализация в текст (Force Text), видимые `.meta`. Каждый новый файл коммитится вместе со своим `.meta`.
