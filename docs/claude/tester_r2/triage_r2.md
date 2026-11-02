# Tester round 2 (gate_trial, data r2d / integ 5a45374): who fixes what

Source: `tester_round2.md` in this folder (123 items: 31 blockers, 80 errors, 12 cosmetic). Gemini: `gemini_step5_8.json` (94 items, tester confirmed 60). Item numbers below are the tester's.

Rule for everyone (unchanged): fix the cause in your tool or spec, never by excusing the check. Base for this round: integ f20a5a1 (w44 round 3 merged). Spec fixes for the trial area go into `gate.json` (w47); `gate_trial.json` is a fixture, but this round w47 also brings it in line with Gate v1.1 (items 53, 54).

## Already closed in integ f20a5a1 (rerun r2e, /mnt/project-files/alatau_stage7/l1r2e)
- 1–28 (rule 12: drive band 5–8 m, opening years, ring): w44 round 3. Validator on r2e: 2 errors left (items 29, 30).

## w44 (land: blocks, lots, buildings, drives) — round 4
- 29 school L00199 plot 3576 < 3600 m²: plot sizing must reach the norm (round up, never down).
- 30, 48, 49 kindergarten places within 300 m short (B0008 34/42, B0014 143/159, B0011 14/42); 48 polyclinic 10/11 visits: size social buildings to the demand in their radius.
- 41 school L00020 plot taken by analogue, not by norm.
- 42 kindergarten L00040: 200 places in data, building 2550 m² = 170 places. Data and building agree.
- 73 school L00015: lot 2032, building and drive ds17 2036; ds17 runs over the football field and running track.
- 78 15 social lots open 2–9 years before their building (L00015, L00019, L00021, L00024, L00026, L00035, L00047, L00112, L00198, L00199, L00233, L00242, L00412, L00414, L00424): lot year = building year.
- 79 micro facilities (polyclinics of 27 and 68 visits, schools of 50/100/150 seats): use normative typical sizes, not the smallest legal unit, unless the demand in the radius really is that small (then say so in the log).
- 80 office parking: 2,051,366 m² offices with no parking norm. Count spaces by norms.json.
- 98 12 business lots in b_a3_edge (L00087, L00088, L00090, L00093, L00095, L00096, L00098, L00102, L00103, L00104, L00107, L00108) have no buildings: build them or do not cut them.
- 118–120 floor area short: b_cbd −8.8 %, b_cbd_e −12.5 %, b_tpu −54.7 % (≤ 5 % allowed).
- 61 Griffin 42,047 m² in 2 sheds vs zone l_griffin 99,309 m² (landmark ≈ 120k); 63 bus station 8917 vs 14,450 m²; 64 P+R lot 11,096 vs 12,750 m². Generated object = spec area (w47 checks the spec numbers).
- 74 57 new buildings on ground with > 1.5 m fall and no plinth (only 5 plinths): mark plinth_m / terrace for each (w45 draws it, w43 makes rule 3 catch it).
- 107 asphalt turnaround pad in the middle of a paved plaza (t10_lrt_park): pads do not land inside plazas.
- 108 office b00245 (48.7 m) 6 m from the L7 lot: keep 22 m from landmark lots too.

## w43 (roads, validator core) — round 5 additions (after the rail items)
- 74 rule 3 must catch a building on > 1.5 m fall without plinth_m.
- 108 rule 12 gap ≥ 22 m between tall buildings must include landmarks (L7 has no buildings.json row; use its lot / registry footprint).
- 75, 76 village lanes s343 (38 m) and s337 (10 m stub) end in gardens: a lane ends at a house or a turnaround, a stub with nothing is dropped.
- 31 rule 1: existing road s112 × existing house b00435 (3 m²), 36 existing dead end s65 227 m: existing-only defects as warnings (as rule 5 / rule 9), but the tester counts every warning: say in the report which existing defects cannot be fixed without touching 2025 data.

## w47 (Gate spec, and the gate_trial fixture) — round 3
- 53, 54 rail station hall, bus station, P+R and their access streets open in 2030 (Gate v1.1 says so; the fixture still has 2031). Bring gate_trial in line with Gate v1.1.
- 52 registry iconic_offices_6 (6 low-rise office blocks around towers 2–3, action add) missing: no lot, no buildings. Read the registry row and its source first. The Iconic plot itself (270 × 200 m) is the rebuilt plaza (IconicPlaza: granite ±133 × ±98 m round the plot centre), so place the six blocks where the source puts them, in the Gate District quarter round the plot if the plot has no room, as gate.json registry objects; if the source does not support them, say so and propose the registry change instead.
- 77 Iconic: 3697 flats from 2029, first kindergarten 2032, school 2033, polyclinic 2034. Social objects within their radius from 2029.
- 32–35 HV lines pl_92ca2130, pl_74b9e818, pl_7fdf85db, pl_7437fd23 without kV: set kV in the spec.
- 43 SZZ class of zone l_griffin not set.
- 37, 38, 65 dead ends s37 (114 m to the reserve L00480) and s70 (56 m to nothing); L00480 3.35 ha «резерв: земля вне зон спецификации»: cover the land with a spec zone, streets only where they serve something.
- 67 targets 10,500 residents vs 4220 flats × 2.5 = 10,550: targets agree.
- 68 ramp s323 (ic_west_bakad) runs 107 m past the area edge.
- 71 ramps e16252, e16258, e16265 v/c 2.55 in 2035 and 2050: enough lanes / another ramp.
- 58–60 utilities: substation 220/110 «hv_gate» sits inside the interchange (15 m from the expressway axes), «ПС 110/10 Gate-2» inside the red lines of s241, boiler «Gate-2» on office lot L00050 5–7 m from b00068/b00069. Give them utility lots in the spec (w45 places the twin's facilities on them).
- 44–51 trial-edge «ждёт соседа» (B0078 without entry, services beyond radius at the cut): confirm each closes in full Gate; list any that do not.
- 61, 63, 64 Griffin / bus station / P+R areas: check the spec numbers are the intended ones (w44 makes the generated objects match).
- Gate (not trial): reserve block B1498 without street entry (from w44 round 3).

## w45 (export, merge, Unity roads and film) — round 5
- 55 rail station hall stands in a field: tracks and platforms of the agglomeration line at the hall.
- 58–60 place the twin's synthetic facilities (hv_gate, ps_gate_2, hb_gate_2) on the spec utility lots w47 adds (or outside red lines and interchanges if none), never inside a road or on another lot.
- 70 after the merge a base LRT station stays 244 m from the TPU station: a district station replaces the base one nearby.
- 72 28 through road edges with no cars in 2050: traffic uses them or they are not drawn as through roads.
- 85, 86, 87 Griffin: yard texture blotchy, stretched, seamed, markings over the seams; docks and truck fronts not visible on any frame; turnaround ring not joined to the yard.
- 88 facades longer than 60 m without a break (Griffin sheds, the barn, b00062).
- 74 plinths drawn for every building w44 marks.
- 91, 92, 110 trees on the paving of park alley s269, on sidewalks and kerbs at zebras (s88, s89); the «film trees on hard ground» counter says 0 while frames show them: the counter must see what the frames show.
- 100 identical buildings side by side (13 frames): neighbours differ.
- 106 moiré on the bus terminal facade.
- 111 no road signs at all («signs 0»): rule 20 needs them.

## w46 (Iconic, landmarks, panels) — round 3
- 52 (owner w47): when w47's iconic_offices_6 lands, check the six blocks do not clash with IconicPlaza (lawns, pavilions, flags, trees).
- 89, 90 Iconic plaza: trees in stone paving without grates (keep model); a row of trees and pedestrians run into the beige retaining wall at the sloped roof.
- 62 construction label «Строится 50 %» over an empty Griffin lot in 2026: label and site agree.
- 112 2026 panel «Зданий стоит 0» with a standing village; «Жители 64 тыс.».
- 113 network panel «Сети для участка» picks Growing, not Gate.
- 114 2050: «Город готов 100 %» next to «4 213 площадок в работе, 103 отстают».
- 115 Gate panel 228k / 78k vs tour card 191k / 76k on the same frame.
- 116, 117 trial zone panel: jobs 33,639 vs data 33,649; area 421 ha vs 419.4 ha.
- Also: apply w47's moved-object list (Gate v1.1 report) to LandmarkData.cs.

## w48 (ground of the new map) — round 2
- 81 park lots 78.3 ha (panel) vs 62.5 ha equipped vs 74.6 ha spec: 15.8 ha of «park» is bare lawn. Equip every park lot; panel = data = spec.
- 82 seam between the qTwin model ground and the map ground at the Iconic quarter (r2 frame): triangle shards, cut path, two drives end in square pads in lawn.
- 83 in 2026 the grid of future streets shows through the ground with sharp seams.
- 84 future lots are empty grey/white pads before their buildings: plain ground (or a fenced site in its build years).
- 93–97 park paths drawn as pale lines; people, benches and playgrounds on grass; paths ending in lawn; playgrounds with no path.
- 99 yards are solid grey paving; «ground props … 0 in the yards»: lawn, playground, benches in every yard.
- 101 village gardens: striped texture with sharp seams, houses standing on the stripes.
- 103, 105 stepped (raster) edges of playgrounds and paving; benches on grass along a path at the bus station.
- 104 kindergarten L00414 sports field shows in 2026, building b00532 opens 2028.

## Orchestrator
- 56 registry road_a19 geometry equals the BAKAD carriageways.
- 57 registry hv_lines_220 «keep» vs spec «cable» (owner decision 31.10: 220 kV in cable or around the core).
- 66 frames_context bounds; 109 shot plan: current IDs and the target in the centre of each frame (docks, plinths, canopy, ring joints).
