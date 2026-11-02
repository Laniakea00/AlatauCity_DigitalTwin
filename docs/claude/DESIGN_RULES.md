# Design rules for the whole platform (stage 4, 30.10.2026)

The owner (30.10): «слишком много текста и это тяжело для чтения, не знаю куда смотреть и что воспринимать. Не только для этого места, но и для всей платформы. Сделай это лучшим дизайнерским решением, которое ты можешь реализовать.»

The viewer is a busy investor or an official in a meeting. They glance at a panel for 3 seconds. Each panel must answer one question at a glance, and the details must stay one click away.

1. **Answer first.** A block opens with its answer: one big number, or one short status phrase of 7 words or fewer. Example: «Сдача в срок · сен 2030», not a paragraph.
2. **One focal point per block.** The answer is the largest and brightest element. Everything else is smaller and muted.
3. **Text budget.** Under the answer, at most ONE visible line of prose (~60 characters). Put everything longer (why, how it is counted, assumptions, methodology, legal notes) into `Widgets.Details(parent, "Почему так" | "Как считается" | "Подробнее")`, which is folded by default. Never delete honest assumptions; fold them.
4. **No repetition on one screen.** A fact appears once. If a banner, a KPI and a chart caption say the same thing, keep the best one.
5. **Plain words, no jargon labels.** Write «Темп работ», «Цена работ», «Прогноз стоимости», not SPI / CPI / EAC / PV / EV / AC. The abbreviation may appear only as a small muted suffix or inside Details.
6. **Colour means status only.**
   - Green = on track. Amber = attention. Red = problem. Blue = interactive, selected or accent.
   - Panels are neutral dark.
   - No big saturated red or orange backgrounds or full red borders around whole cards. Show status with a dot, a thin 3 px left accent bar, or a coloured value.
   - At most one red thing per screen should shout.
7. **Type scale: four sizes only.**
   - 26–28 px for the hero number.
   - 15–16 px for block titles and answers.
   - 13 px for body text.
   - 11 px for meta, labels and source lines.
   - Bold only for answers and titles.
8. **Numbers.**
   - Right-align them in rows.
   - Make the unit smaller and muted: «39» with a small «дн.».
   - Join number and unit with a non-breaking space.
   - Round sensibly: 58 %, not 58,3 %, unless precision matters.
9. **Spacing.**
   - Use an 8 px grid and consistent paddings.
   - Separate groups with space rather than lines.
   - Align left edges.
   - Empty space is good.
10. **Labels.**
    - Labels are 1–3 words.
    - A button says what happens, and it must visibly happen: camera flies, element highlights, panel opens.
    - Every clickable thing has a hover state and a selected state.
11. **Sources.** Keep the chips (the honest-numbers rule), but as ONE quiet line at the bottom of a block. Never put them in the middle of content and never repeat them per row.
12. **Lists.** Show the 3–5 most important items. The rest go behind «Ещё N ›» or a Details.
13. **Scrollbars.**
    - Side columns scroll with the wheel or by drag, without a visible scrollbar.
    - Long lists inside popups (sources, notifications, navigator, documents) may keep a thin scrollbar.
14. **Repeated meta lines.** Remove meta lines that repeat in every card («на дату съёмки 07.09.2028», «демо-сценарий…»). Say it once in the page header.
15. **Languages.**
    - Russian is the source; EN/KZ come through the translator.
    - Keep sentences as complete `string.Format` templates.
    - Shorter Russian means shorter EN/KZ too. Check that nothing clips in EN, which is the longest.
