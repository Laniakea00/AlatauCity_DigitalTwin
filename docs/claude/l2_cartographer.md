# Level 2 cartographer: one district of Alatau City (template; the orchestrator's message names the district)

Read first, in this order:
- `/home/claude/wt/COMMON_RULES.md`, the Stage 7 sections.
- **`tools/map/CONTRACT.md`**. §3 is your file format. §8 is binding: it lists everything the tools settled at level 1.
- The plan `/mnt/project-files/alatau_stage7/plan/plan.md`, whole. Above all: «Каким должен быть город», «Чего быть не должно», «Задания по районам» (your row and «Что сдаёт картограф»), «Оркестрация» (the order inside a district).
- Your approved scheme: `tools/map/spec/<d>.json` v0 plus `/mnt/project-files/alatau_stage7/level0/schemes/<d>/scheme.png` and `scheme.md`. The owner approved these schemes on 31.10; keep their structure (axes, centres, zones, where each object stands) unless a rule or a better engineering solution forces a change, and list every change.
- `tools/map/spec/city.json` (your outline, joints, bids range, height limits, airport_new, lrt_schemes), the registry rows of your district (`tools/map/spec/registry.json`), and the lines for your district in `/mnt/project-files/alatau_stage7/level1/w42/spec_issues.md`.
- The level-1 reference: `tools/map/spec/gate_trial.json`, a v1 spec that passes the validator, with its builder `tools/map/district/gate_trial_build.py` and self-check `gate_trial_check.py`. Copy their approach, not their content.
- The level-2 reference: **`tools/map/spec/gate.json` v1.1** (the whole Gate district, done first) with `tools/map/district/gate_build.py`, `gate_check.py`, `gate_net.py`, `gate_zones.py`, `gate_numbers.py`, `gate_draw.py`, and its output `/mnt/project-files/alatau_stage7/out/gate/` (numbers.md, overview.png). Gate's joints with your district are fixed now: meet them, do not move them.

Worktree `/home/claude/wt/<you>`, branch `<you>` from integ (the orchestrator gives the commit). You own:
- `tools/map/spec/<d>.json`
- your scripts `tools/map/district/<d>_*.py`
- your output folder `/mnt/project-files/alatau_stage7/out/<d>/`

## Owner decisions that bind every district (31.10)
- Ready objects may be moved freely; list each one as «было → стало → почему».
- Iconic is at (−3500, −19500) in the centre of Gate.
- 220 kV overhead lines through district centres go into cable or around the core.
- New airport after 2040: 15 M passengers a year, runway 4000 m at 095°, centred at (−16000, 1500) (city.json `airport_new`).
- Zimovkas stay.
- District borders are the twin outlines.
- Jobs are the twin's 2050 figures, with no scaling.
- An LRT corridor to Zhetygen is reserved.
- Existing villages stay and get their own streets; new roads go around them, never through houses.
- Everything real goes where its source puts it, within its accuracy. Everything else is placed by rule and labelled «модель qTwin». Never invent real-world facts.

## Task
Write `tools/map/spec/<d>.json` (spec v1) for the whole district, from a builder script `tools/map/district/<d>_build.py` that regenerates it, plus a self-check `tools/map/district/<d>_check.py`, built the way the gate_trial ones are. Then:
1. Run `python3 tools/map/run.py <d>`.
2. Fix the spec, never the tools, in the plan's order: road frame (rules 5–9, 11) → blocks, lots and landmark objects (1–4, 10) → homes, jobs, education and medicine by radius (12–16, 18) → greens, parking, stops, LRT and years (all rules).
3. Stop when the validator gives 0 errors, except «ждёт соседа» at your edge joints.
4. Keep every bid inside your `city.json#bids.ranges.<d>`.
5. Keep homes, jobs, school and kindergarten places, park hectares and parking within ±5 % of the targets.

If an error is really a tool bug, do not work around it in the spec. Write it down with the evidence (spec ids, coordinates, the rule output) and send it to the orchestrator at once with SendMessage to "main". Then go on with everything else.

The district is large. If a run takes more than ~10 minutes, report the slow step with timings rather than cutting the district into pieces.

## Lessons from Gate (binding)
- Never draw driveway_* classes in the spec. Drives come only from land_driveways. A road into an industrial or logistics yard is `industrial`; the merge treats every driveway_* edge as a carless drive.
- Building numbers go up to 131,072. Your district has a first range and a second range (`city.json#bids.ranges` and `ranges2`), and its Overture-only existing houses have their own block. Never bend the design to save numbers.
- Drives, pads and buildings keep off landings, ramps and embankments (CONTRACT §8, w44). Leave room beside raised streets.
- Known: golden.json v0 has zones with nested polygon lists, and `net_osm.load` fails on them. Write v1 zones as CONTRACT §3 says (flat rings); if the tool still fails, report it.
- Give every power line its `kv` (rules 4 and 19 use the protection zones by voltage). Keep `params.keep_existing: true` only on real existing interchanges.
- Rule 14 in years before 2050 is a coverage report; still open schools, kindergartens and polyclinics no later than the houses they serve.
- Zones reach the red lines of their streets (no 1–2 m strip between a zone and the red line); a registry object's plot is its free land between the red lines.
- A registry plot must hold its building with the setbacks of the norms (e.g. `kindergartens.building_from_red_line_m` 25 m from every street): if it cannot, give it the whole block or lower its capacity, and say which.
- Fire gaps: two buildings over 28 m stand ≥ 22 m apart; land lowers the second one to ≤ 28 m. So in dense business or housing zones set the lowest floors so that floors × floor height ≤ 28 m (Gate: 6 floors × 4.43 m in b_cbd), and set jobs or homes per ha to what the blocks hold with those gaps under the height cap; check the zone reaches its floor area in the land log.
- Years: an object opens no earlier than the streets that serve it; the station, its bus station, parking and access streets open together.
- Targets are compared with the new city only: existing OSM houses (homes by the 600 m² rule) are counted apart (`homes_existing`), never added to the targets.
- The service table must reach 0 blocks out of norm; if land's site placement (not your spec) leaves blocks out, report the blocks and the reason from the land log.
- A full district run takes about 7 minutes on the current tools (Gate 399 s); four districts run at once on 4 cores, so expect up to twice that.

## Do not
- Touch generators, the validator, export, Unity, `city.json`, `registry.json`, norms, rules, or another district's spec. Write problems with them in your report.
- Install anything with pip except pyproj.

## Done when
- Spec v1, builder and self-check, green.
- `run.py <d>` gives 0 errors except «ждёт соседа».
- Pictures:
  - the top-down overview at 10 m/px in `OUT/<d>/overview.png`;
  - 2 × 2 km tiles at 1 m/px for the centre and the two densest areas in `OUT/<d>/tiles/`.
- One commit, one line, no attribution.
- A final report that lists, as the plan's «Что сдаёт картограф» asks:
  - the commit hash;
  - the validator counts;
  - the service table summary (the worst block for each service, and how many blocks miss a norm: must be 0);
  - moved objects «было → стало → почему»;
  - registry rows marked «по источнику / по правилу»;
  - the district numbers against targets (residents, jobs, km of roads, ha of parks, parking places) with their deviation;
  - three sentences in Russian for the owner on what the district now looks like;
  - tool bugs found.
