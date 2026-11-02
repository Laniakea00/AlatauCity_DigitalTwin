# Инструменты Claude на Gemini

Ключ Gemini даёт Anuar. Хранить только в переменной окружения `GEMINI_API_KEY` (или в файле `~/.gemini_key`, путь меняется через `GEMINI_KEY_FILE`). Никогда не в репозиторий, не в сборку, не в чат. Скрипты ключ не печатают.

Python 3.12+. Для проверки кадров нужен `pillow`.

| Скрипт | Что делает |
|---|---|
| `gemini.py` | Общий клиент: `from gemini import ask; ask(model, text, images=[...], json_out=True, thinking='high')`. |
| `gemini_review.py` | **Тестер кода.** Gemini 4 Argon сверяет изменение с задачей: `--task task.md --repo . --base <коммит> [--img кадры] --out review.json`. Вердикт pass/fail и список проблем. |
| `map_review.py` | **Тестер карты** (шаги 5 и 8 из `docs/claude/tester.md`): `map_review.py context.md out.json кадр1.png кадр2.png …`. |
| `shot_review.py` | Проверка интерфейса по скриншотам: обрезанный текст, непереведённые строки, противоречивые цифры. |
| `design_review.py` | Проверка дизайна «было/стало» по `docs/claude/DESIGN_RULES.md`: `design_review.py task.md out.json было1.jpg -- стало1.jpg`. |
| `gemini_image.py` | **Генератор картинок** (Nano Banana Pro, `gemini-3-pro-image`): текстуры, фасады, небо, перерисовка кадра. `gemini_image.py "промпт" out.png [--ref образец.png] [--aspect 16:9]`. Картинки синтетические: в продукте с пометкой «модель qTwin». |
| `loc_add.py` | Переводит новые русские строки из C# на EN/KZ и дописывает в `Resources/Loc/strings.json`: `loc_add.py <корень репо> --files a.cs b.cs`. |
| `loc_list.py` | То же для готового списка строк в JSON. |
| `loc_nbsp.py` | Копирует переводы для строк, отличающихся только неразрывными пробелами. |

Модели в ключе (02.11): `gemini-4-argon` (проверки), `gemini-3-pro-image` (картинки), `gemini-3.8-flash-tts` (озвучка), `lyria-3.5` (музыка).

Заметки:
- `strings.json` записан одной строкой. Править только этими скриптами, `UnityProject/Tools/loc/merge.py` перезаписывает файл целиком, им не пользоваться.
- В `loc_add.py` и `loc_nbsp.py` папка Editor отсекается по `'/Editor/'`: на Windows путь с `\`, поправить при первом запуске.
- Правило команды: каждую готовую часть проверять Gemini, не больше 2 кругов «переделай».
