# Alatau City — Digital Twin (Unity)

Цифровой двойник Alatau City на Unity: генплан 2025–2050, районы Gate / Golden / Growing / Green, реальные инвестпроекты, ЛРТ, стройка, прогноз, инфраструктура, ситуационный центр, ИИ-ассистент и презентация для инвесторов по зонам.

Подробное описание проекта — [README_RU.md](README_RU.md), [startup.md](startup.md), [context.md](context.md), ТЗ и прогресс — в [docs/](docs/).

## Как открыть (первый раз)
1. Unity **6000.0.84f1** (Built-in RP). В Unity Hub: *Add project from disk* → папка `UnityProject`.
2. После импорта: меню **Alatau City → Rebuild Scene**. Команда собирает `Assets/Generated` (рельеф, здания по годам, ~830 МБ) из `Assets/CityData`; эта папка в git не хранится.
3. Открыть сцену `Assets/Scenes/AlatauCity.unity` → Play.
4. Сборка под Windows: **Alatau City → Build Windows**.

## Структура
- `UnityProject/Assets/Scripts/DigitalTwin` — код двойника (модули, UI, слои, презентация `TwinTour.cs`)
- `UnityProject/Assets/Scripts/DigitalTwin/Landmarks` — реальные объекты, ЛРТ, метки, паспорта
- `UnityProject/Assets/Shaders`, `Assets/Resources/Shaders` — шейдеры (здания, земля, объекты)
- `UnityProject/Assets/CityData` — исходные данные генплана
- `UnityProject/Tools` — Python-генераторы данных
- `web/` — веб-версия

## Работа в команде
- Перед работой — *Fetch / Pull*, коммиты небольшие, сцену `AlatauCity.unity` одновременно правит один человек.
- `Library/`, `Temp/`, `Logs/`, `Builds/`, `UserSettings/` и `Assets/Generated/` не коммитятся (`.gitignore`).
