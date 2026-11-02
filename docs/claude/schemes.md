# Level 0, last step: one district scheme for the owner's approval

Read first: `/home/claude/wt/COMMON_RULES.md` (the Stage 7 sections, including the speed and memory baseline, then honesty and commits). Then the plan `/mnt/project-files/alatau_stage7/plan/plan.md`, all of: «Каким должен быть город» (both subsections), «Чего быть не должно: жёсткие правила», «Уровни работы», «Задания по районам», «Оркестрация». The plan is in Russian; the owner reads only Russian, so everything you write for him is in Russian.

Your district, worktree, model and special points are in the message that started you.

## What the owner approves
The plan's level 0 gate: «вы утвердили схемы четырёх районов». A scheme is the idea of the district on one picture: where its centres are, its main axes (roads, LRT, boulevards), its zones (what stands where), where every real object of the registry stands, and in what order it is built. It is NOT the street network or the buildings: that is level 1–2. Keep it at the level of a good urban designer's concept plan: few, strong, readable decisions, each with a reason.

## Inputs (all already exist; read, do not rebuild)
- `tools/map/spec/city.json` v0 (in your worktree): frame, district polygons (`districts`, the twin outlines), Growing split on A-3 (`growing_split`), water and Kapchagay flood levels, existing 2025 roads/rail/power/settlements, `trunk_v0` and `lrt_v0` (drafts: you may redesign them inside your district), boundary `joints` (fixed: your axes must meet them; if one is wrong, say so in open questions), `bids`, `height_limits`, `centres`, `iconic`. Big layers it references: `/mnt/project-files/alatau_stage7/level0/w34/` (osm/, derived/, genplan/, README.md, compare.md, city_overview.png, gate_overview.png). The code that made them: `tools/map/geo/` (frames.py, terrain.py for height and slope, layers.py, render_maps.py for drawing helpers).
- `tools/map/spec/registry.json` + `registry_report.md` (279 real objects: place, accuracy, sources, where they are in the twin today, proposed action), `norms.json`, `rules.json` (if `norms.json`/`rules.json` are not in your worktree yet, the orchestrator merges them; until then use `/mnt/project-files/alatau_stage7/research/norms.md`).
- Research: `/mnt/project-files/alatau_stage7/research/` (alatau_objects.md, transport_site.md, norms.md, inventory.md, code_map.md).
- The twin today (read-only): the integ repo in your worktree and the laptop snapshot `/mnt/user-data/uploads/AlatauCity_DigitalTwin` (StreamingAssets/twin/*.json, buildings.csv with `district`, LandmarkData.cs for landmark positions).

## Deliver
1. **`tools/map/spec/<district>.json` v0** (UTF-8, LF, Unity X/Z metres, small and hand-editable), with exactly these top-level keys so all districts match:
   - `district`, `version` (0), `boundary` ("city.json#districts/<id>"), `targets` {population_2050, jobs_2050, homes_2050 if known, source}: take the twin code's district targets (the plan's table gives population: Gate 223 k, Golden 675 k, Growing 650 k split W/E by the twin's own figures, Green 320 k) and say where each number comes from.
   - `centres`: [{id, kind: main|sub|local, name_ru, x, z, why}].
   - `axes`: [{id, class: expressway|trunk|arterial|district|boulevard|pedestrian|lrt_corridor, name_ru, line: [[x,z],…], status: keep_existing|keep_twin|new, years: [first, done], why}]. Only the skeleton: expressways, trunk roads, arterials, the main district streets, main boulevards and pedestrian axes.
   - `zones`: [{id, use, polygon: [[x,z],…], density: {floors_typical, far, homes_per_ha, jobs_per_ha} as relevant, years: [first, done], why}], with `use` from: mixed_centre, business, residential_high, residential_mid, residential_low, village_existing, campus, medical, industry, logistics, utility, park, waterfront, sport, reserve. Zones cover the district without overlaps; water, existing villages and protected strips are zones too.
   - `lrt`: {line: [[x,z],…], stations: [{id, name_ru, x, z}], why}.
   - `objects`: one row per registry object of your district and per object the plan moves into it: {registry_id, name_ru, action: keep|move|add|by_rule|remove, from: [x,z]|null, to: [x,z]|null, yaw, accuracy, why}. Moves follow the owner's decisions below and the plan's districts table.
   - `phases`: [{queue, years: [first, done], what_ru, zones: [ids], axes: [ids]}], streets before the houses they serve.
   - `joints`: [{joint_id (from city.json), axis}].
   - `checks`: the numbers you computed (see 4) and `open_questions`: at most two, each answerable with one word.
2. **The scheme picture** `/mnt/project-files/alatau_stage7/level0/schemes/<district>/scheme.png`, north up, scale bar, Russian legend and labels, about 3000–4500 px on the long side: district boundary; terrain shading or contours if it helps; water and flood lines; existing villages, roads, rail and power lines (muted); zones in clear colours; axes by class (thick to thin); LRT with stations; centres; every registry object as a labelled marker, with an arrow from its old place when it moves; boundary joints; a small inset or numbered labels for the build queues. It must read in 10 seconds on a phone. Put the drawing code in `tools/map/scheme/<district>_scheme.py` (reuse `tools/map/geo/render_maps.py` helpers; do not edit shared files).
3. **`/mnt/project-files/alatau_stage7/level0/schemes/<district>/scheme.md`**, in Russian, one page: the idea in two sentences; centres; axes; zones with their share of area; what moves where and why; the build order; the numbers; the open questions. Plain words, no jargon without a short explanation.
4. **Checks** you run and report (a small script is fine, output into `checks` in the spec):
   - no zone and no new axis on water, inside the Kapchagay 485 m flood line, or on existing village houses (Overture buildings + twin `existing_osm`): count of houses hit must be 0 for new axes and for every zone except `village_existing`;
   - every joint of your district is met by an axis;
   - every registry object of your district has a row in `objects`;
   - the share of each zone use and the population/jobs capacity of the zones vs `targets` (within ±10 % at scheme level);
   - slope under the main centre and the axes (terrain.py), and the airfield height zones (`height_limits`) for anything planned 50 m or taller.

## Owner's decisions to follow (31.10)
- Gate must come out «идеальным»; Iconic must be in the centre of Gate. Other ready objects may be moved freely (L7 included) when the city is better for it; say why for each move.
- The Gate District ring is built in 4D in queues: streets first, then the houses they serve.
- Existing villages stay and get their own streets; new axes go around them, never through houses.
- Everything real goes where its source puts it, within its accuracy; everything else by rule, marked «модель qTwin».

## Do not
Touch Unity, the laptop, `/mnt/project-files/alatau_stage7/level0/w34/` files, another district's spec, `city.json`, or any shared file. Do not invent real-world facts: if a source does not place something, it is by rule and says so. Do not pip-install anything but pyproj (Pillow, numpy, shapely are there if `python3 -c "import shapely"` works; check before you rely on one).

## Done when
The spec loads with `python3 -c "import json; json.load(open(...))"`, the picture and the page exist, every check in 4 passes or is explained, and one commit (one line, no attribution) is in your worktree with the spec and your scheme script.

## Final report
Commit hash; the idea in two sentences; centres with coordinates; moved objects (from → to, why); the check results; open questions; anything in city.json or the registry you believe is wrong.
