# Alatau City — цифровой двойник qTwin (Unity 6000.0.84f1, Built-in RP)

Сцена: `Assets/Scenes/AlatauCity.unity`. Меню **Alatau City**: Rebuild Scene · Setup UI assets · Build Windows · Export ZIP for team.

Полное описание проекта — `context.md`, запуск и сборка — `startup.md` (в корне архива для команды; исходники лежат в папке `_package` рядом с проектом).

* Геометрия: `Assets/CityData` (экспорт из Blender, `Tools/blend_export.py`), меши строит `Editor/AlatauCityBuilder.cs` в `Assets/Generated`.
* Синтетика двойника: `Assets/StreamingAssets/twin/*.json` (генераторы — `Tools/twin_gen`).
* Код: `Scripts/DigitalTwin` (состояние, модули M0–M5, слои, UI Toolkit), шейдеры: `Shaders/AlatauLit.shader`, `Resources/Shaders/*`.
* Система координат: X = восток, Y = высота над у. м., Z = север; UTM 43N: E = 663000 + X, N = 4830000 + Z.
