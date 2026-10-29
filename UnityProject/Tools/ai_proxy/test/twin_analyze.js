// Test stand-in for the analyze function (AiModule.Analysis in Assets/Scripts/DigitalTwin/Modules/AiModule.cs): a port of the scripted
// intents (Schools, Placement, Risky, Power, Flood, LrtDelay, Traffic, Population) on the same data files, base scenario, year 2026,
// so the transcripts show what the model gets in Unity. buildings.csv and traffic.json are not in the repository (large files):
// set TWIN_BUILDINGS_CSV and TWIN_TRAFFIC_JSON, or they are looked up in the usual places; without them those topics return an error.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ASSETS = path.resolve(HERE, '../../../Assets');
const TWIN = path.join(ASSETS, 'StreamingAssets/twin');
const first = (...ps) => ps.find(p => p && fs.existsSync(p));
const CSV = first(process.env.TWIN_BUILDINGS_CSV, path.join(ASSETS, 'CityData/buildings.csv'), '/mnt/user-data/uploads/AlatauCity_DigitalTwin/UnityProject/Assets/CityData/buildings.csv');
const TRAFFIC = first(process.env.TWIN_TRAFFIC_JSON, path.join(TWIN, 'traffic.json'), '/tmp/claude-0/repo/UnityProject/Assets/StreamingAssets/twin/traffic.json');
const J = f => JSON.parse(fs.readFileSync(f, 'utf8'));

const S = 'base', SCEN_NAME = 'Базовый', MIN_Y = 2026, MAX_Y = 2050, Y0 = 2025, NY = 26, YEAR = 2026;
const DN = ['Gate', 'Golden', 'Growing', 'Green'];
const loads = J(path.join(TWIN, 'loads.json')), cons = J(path.join(TWIN, 'construction.json')), nets = J(path.join(TWIN, 'networks.json')), risk = J(path.join(TWIN, 'risk.json'));
const traffic = TRAFFIC ? J(TRAFFIC) : null;
const KIND = {}; for (const m of fs.readFileSync(path.join(ASSETS, 'Scripts/DigitalTwin/Loc.cs'), 'utf8').matchAll(/\["kind_(\w+)"\] = "([^"]+)"/g)) KIND[m[1]] = m[2];

// ------------------------------------------------------------------ helpers mirroring Unity / .NET
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const R = v => Math.sign(v) * Math.round(Math.abs(v)), R1 = v => Math.round(v * 10) / 10;
const grp = s => s.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
const N0 = v => (v < 0 ? '-' : '') + grp(String(Math.round(Math.abs(v))));
const N1 = v => { const s = Math.abs(v).toFixed(1).split('.'); return (v < 0 ? '-' : '') + grp(s[0]) + ',' + s[1]; };
const YI = y => clamp(y - Y0, 0, NY - 1);

// ------------------------------------------------------------------ buildings (CityDatabase) and the base-scenario years (CityStats)
let B = null;
function buildings() {
  if (B || !CSV) return B;
  const lines = fs.readFileSync(CSV, 'utf8').split('\n'); B = [];
  for (let i = 1; i < lines.length; i++) {
    const p = lines[i].trim().split(','); if (p.length < 16) continue;
    const b = { bid: +p[0], district: p[2], kind: p[3], use: p[4], source: p[5], year: +p[6] || 0, height: +p[8] || 0, gfa: +p[9] || 0, x: +p[11] || 0, z: +p[12] || 0 };
    b.eff = b.year;                                       // TwinScenario.EffectiveYear, base scenario
    B.push(b);
  }
  return B;
}
const stands = (b, y) => b.source === 'existing_osm' || b.eff <= y;
const residentsOf = b => b.use === 'housing' ? b.gfa / 30 : b.source === 'existing_osm' ? Math.max(3, b.gfa / 35) : 0;
const cat = u => ({ housing: 0, business: 1, social: 2, industry: 3, energy: 3, leisure: 4 })[u] ?? -1;
function residents(d, y) { let s = 0; for (const b of buildings()) if (b.district === DN[d] && cat(b.use) === 0 && b.eff <= Math.min(y, MAX_Y)) s += b.gfa; return s / 30; }
function residentsNear(px, pz, r, y, bids) { let s = 0; for (const b of buildings()) { const dx = b.x - px, dz = b.z - pz; if (dx * dx + dz * dz > r * r || !stands(b, y)) continue; s += residentsOf(b); bids && bids.push(b.bid); } return s; }

function pack(a, topic, map, extra) {
  const d = { topic, kind: 'model', scenario: SCEN_NAME, ...extra, summary: a.text, shown_on_map: map };
  if (a.chart) d.chart_under_answer = a.chart;
  for (const k of Object.keys(d)) if (d[k] === null || d[k] === undefined) delete d[k];
  d.sources = a.src; return d;
}

// ------------------------------------------------------------------ the analyses
function schools(y) {
  const yi = YI(y), so = loads.social[S], gap = [], cov = []; let worst = 0;
  for (let d = 0; d < 4; d++) { const nd = so.need[d][0][yi], cp = so.cap[d][0][yi]; gap[d] = nd - cp; cov[d] = nd > 0 ? cp / nd : 1; if (gap[d] > gap[worst]) worst = d; }
  let text;
  if (gap[worst] <= 0) text = `В ${y} году мест в школах хватает во всех районах.`;
  else {
    const others = [0, 1, 2, 3].filter(d => d !== worst && gap[d] > 50).map(d => `${DN[d]} −${N0(gap[d])}`);
    text = `В ${y} году больше всего школ не хватает в ${DN[worst]}: не хватает ${N0(gap[worst])} мест, обеспеченность ${R(cov[worst] * 100)} %.` + (others.length ? ' Ещё: ' + others.join(', ') + '.' : ' В остальных районах мест хватает.');
  }
  const a = { text, chart: 'Школы по городу', src: ['model_social', 'model_city'] };
  return pack(a, 'school_deficit', 'new buildings tinted by district: red = less than 90 % of the needed school places, amber = slightly short, green = enough; camera on the district with the largest shortfall', {
    year: y, norm: '120 school places per 1000 residents (SP RK guideline); places = schools of the master plan by their opening year in the twin scenario',
    largest_shortfall_district: gap[worst] > 0 ? DN[worst] : null, all_districts_have_enough: gap[worst] <= 0,
    by_district: [0, 1, 2, 3].map(d => ({ district: DN[d], places_needed: R(so.need[d][0][yi]), places_available: R(so.cap[d][0][yi]), shortfall_places: R(Math.max(0, gap[d])), coverage_pct: R(cov[d] * 100) })) });
}

function planSchool(y) {
  const yi = YI(y), so = loads.social[S]; let d = 0, g = -1;
  for (let k = 0; k < 4; k++) { const gap = so.need[k][0][yi] - so.cap[k][0][yi]; if (gap > g) { g = gap; d = k; } }
  const all = buildings();
  const sch = all.filter(b => b.kind === 'education' && stands(b, y));
  const homes = all.filter(b => b.district === DN[d] && b.use === 'housing' && stands(b, y));
  const covered = (x, z) => sch.some(s => (s.x - x) ** 2 + (s.z - z) ** 2 < 800 * 800);
  const unc = homes.filter(b => !covered(b.x, b.z));
  const groups = new Map(); for (const b of unc) { const k = Math.floor(b.x / 400) + ',' + Math.floor(b.z / 400); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(b); }
  const cells = [...groups.values()].map(gr => ({ x: gr.reduce((s, b) => s + b.x, 0) / gr.length, z: gr.reduce((s, b) => s + b.z, 0) / gr.length }));
  const scored = cells.map(p => ({ p, kids: unc.filter(b => (b.x - p.x) ** 2 + (b.z - p.z) ** 2 < 800 * 800).reduce((s, b) => s + residentsOf(b), 0) * 0.12 })).sort((a, b) => b.kids - a.kids);
  const r = { d, gap: Math.max(0, g), cells: cells.length, homes: homes.length, far: unc.length, pick: [] };
  for (const x of scored) { if (r.pick.every(o => Math.hypot(o.p.x - x.p.x, o.p.z - x.p.z) > 1500)) r.pick.push(x); if (r.pick.length === 3) break; }
  if (r.pick.length) r.seats = clamp(R(r.pick[0].kids / 100) * 100, 600, 1500);
  return r;
}
function placement(y) {
  const P = planSchool(y), d = P.d, g = P.gap, pick = P.pick, seats = P.seats, L = ['A', 'B', 'C'];
  const a = { src: ['model_social', 'model_city'] };
  if (!pick.length) { a.text = `В ${y} году в ${DN[d]} все дома в 10 минутах от школы.`; return pack(a, 'school_site', 'nothing', { year: y, district: DN[d], all_homes_within_10_min_of_a_school: true }); }
  a.text = `Больше всего мест не хватает в ${DN[d]} (${N0(Math.max(0, g))} мест в ${y}). Я сравнил участки, откуда до школы дальше 10 минут пешком, и предлагаю 3 варианта. Лучший — A: рядом ${N0(pick[0].kids)} детей школьного возраста, школа на ${N0(seats)} мест закроет ${R(100 * Math.min(seats, g) / Math.max(g, 1))} % дефицита района.` + (g > seats * 1.5 ? ` Всего району нужно ещё ~${Math.ceil(g / 1000)} школ по 1 000 мест — B и C следующие по очереди.` : '');
  return pack(a, 'school_site', 'homes within 10 min of variant A in green, homes now farther than 10 min from any school in amber, variants A–C as pins; camera on A', {
    year: y, district: DN[d], shortfall_places: R(g), variants: pick.map((x, i) => ({ variant: L[i], school_age_children_within_10_min_walk: R(x.kids) })),
    recommended: 'A', school_places: seats, closes_pct_of_district_shortfall: R(100 * Math.min(seats, g) / Math.max(g, 1)),
    more_schools_of_1000_places_needed: g > seats * 1.5 ? Math.ceil(g / 1000) : null, homes_checked: P.homes, homes_farther_than_10_min: P.far, candidate_sites_compared: P.cells,
    method: '10 min walk = 800 m; candidate sites = 400 m grid cells; school-age children = 12 % of residents; variants at least 1.5 km apart' });
}

function risky(y) {
  const pb = cons.per_building, names = cons.contractors.map(c => c.name), list = [];
  for (const b of buildings()) {
    if (b.source === 'existing_osm') continue;
    const plan = b.eff, start = plan - Math.max(1, pb.duration_years[b.bid] ?? 2), dm = pb.delay_months[b.bid] ?? 0, fact = plan + Math.ceil(dm / 12);
    if (dm <= 0 || y < start || y >= fact || plan > 2050) continue;
    list.push({ b, delay: dm, plan, fact });
  }
  const top = [...list].sort((p, q) => q.b.gfa * q.delay - p.b.gfa * p.delay).slice(0, 5);
  const synth = 'Schedules, general contractors and delays of each building are synthetic (QTwin model); contractors are conventional numbered names, not real companies.';
  const a = { src: ['model_build'] };
  if (!top.length) { a.text = `В ${y} году отстающих строек нет.`; return pack(a, 'construction_risk', 'nothing', { year: y, objects_behind_schedule: 0, note: synth }); }
  const gfa = list.reduce((s, x) => s + x.b.gfa, 0);
  const cnt = new Map(); for (const x of list) { const c = pb.contractor[x.b.bid]; cnt.set(c, (cnt.get(c) || 0) + 1); }
  const [tcKey, tcN] = [...cnt.entries()].sort((p, q) => q[1] - p[1])[0];
  a.text = `В ${y} году отстают ${list.length} объектов (${N1(gfa / 1e6)} млн м²). Самые рискованные — где большая площадь и большая задержка: показал 5 на карте. Чаще всего отстаёт «${names[tcKey]}» (${tcN} объектов).`;
  return pack(a, 'construction_risk', 'all buildings behind schedule in red; the 5 riskiest as numbered pins with delay and contractor; camera on the first', {
    year: y, objects_behind_schedule: list.length, floor_area_behind_mln_m2: R1(gfa / 1e6), most_frequent_contractor: names[tcKey], most_frequent_contractor_objects: tcN,
    ranking: 'riskiest = largest floor area × delay',
    top5: top.map((x, i) => ({ rank: i + 1, type: KIND[x.b.kind] || x.b.kind, district: x.b.district, floor_area_thousand_m2: R(x.b.gfa / 1000), delay_months: x.delay,
      plan_completion_year: x.plan, forecast_completion_year: x.fact, contractor: names[pb.contractor[x.b.bid]] ?? '—' })), note: synth });
}

function power() {
  const bal = loads.balance[S].power_hv, city = bal.city; let fy = -1, fd = -1, fv = 0;
  for (let i = 0; i < NY && fy < 0; i++) for (let d = 0; d < 4; d++) { if (bal.districts[d].deficit[i] > 0.5) { fy = Y0 + i; fd = d; fv = bal.districts[d].deficit[i]; break; } }
  const a = { src: ['model_loads'], chart: 'Электроэнергия по годам' };
  if (fy < 0) { a.text = 'При этом сценарии электроэнергии хватает до 2050 года во всех районах.'; delete a.chart; return pack(a, 'power_shortage', 'nothing', { enough_until: 2050 }); }
  const f = nets.facilities.find(x => x.res === 'power_hv' && x.district === fd);
  const si = ['base', 'fast', 'slow', 'infra'].indexOf(S);
  const cause = f && f.delayed_stages && f.delayed_stages.length ? `${f.delayed_stages[0]}-я очередь «${f.name}» сдвинута на ${f.stages[si][f.delayed_stages[0] - 1]} год` : 'рост спроса опережает ввод мощностей';
  a.text = `Впервые — в ${fy} году, в ${DN[fd]}: не хватит ${N1(fv)} МВт. Причина: ${cause}. Варианты: перенести ввод очереди на год раньше или временно перевести часть нагрузки на соседнюю подстанцию. Это видно и во вкладке «Прогноз».`;
  const yi = YI(fy);
  return pack(a, 'power_shortage', "new buildings tinted by district in the first shortage year: red = demand above the substations' capacity, green = enough; camera on that district", {
    first_shortage_year: fy, district: DN[fd], shortfall_mw: R1(fv), cause, city_demand_mw: R(city.demand[yi]), city_capacity_mw: R(city.cap[yi]),
    districts_short_that_year: [0, 1, 2, 3].filter(d => bal.districts[d].deficit[yi] > 0.5).map(d => DN[d]),
    options: 'bring the delayed substation stage forward by a year, or move part of the load to a neighbouring substation for a while',
    method: 'demand = floor area × specific load (housing 10 W/m², offices 12, social 15, industry 30); capacity = 220/110 kV substations of the master plan by stage in the twin scenario' });
}

function branchPeak(N, T0, T1, ppu, fixed, fixedAt, H = 72, NT = 49) {
  let dmg = 0; const dt = H / (NT - 1); let last = 0;
  for (let k = 0; k < NT; k++) { const t = k * dt; const a = t >= T0 && t < T1 ? N : 0; if (k > 0) dmg += a * ppu * dt / 1e6; last = dmg + (t >= fixedAt ? fixed : 0); }
  return last;
}
function flood(y) {
  const depth = risk.scenarios.flood_1pct.depth_cm; let people = 0, damage = 0, n = 0;
  for (const b of buildings()) { if (b.bid >= depth.length || depth[b.bid] <= 0 || !stands(b, y)) continue; people += residentsOf(b); n++; const share = clamp(depth[b.bid] / 100 / Math.max(3, b.height), 0, 1) + 0.05; damage += b.gfa * 300000 * Math.min(0.4, share) / 1e9; }
  const no = branchPeak(people, 30, 66, 600, damage * 1000, 32), yes = branchPeak(people * 0.35, 6, 40, 300, damage * 1000 * 0.3, 30);
  const a = { src: ['model_flood', 'model_city'] };
  a.text = n === 0 ? 'В зоне паводка нет зданий.' : `При паводке «раз в 100 лет» в ${y} году подтопит ${N0(n)} зданий, где живут ~${N0(people)} человек. Если поставить дамбу и эвакуировать заранее — ущерб в ${N1(no / Math.max(yes, 1))} раза меньше.`;
  return pack(a, 'flood', 'buildings in the flood zone in blue; camera on the Kaskelen floodplain', {
    year: y, event: 'flood with a 1 % chance per year (once in 100 years) on the Kaskelen river', buildings_flooded: n, residents_in_zone: R(people),
    damage_without_measures_bn_kzt: R1(no / 1000), damage_with_dam_and_early_evacuation_bn_kzt: R1(yes / 1000), damage_reduction_times: R1(no / Math.max(yes, 1)),
    measures: 'temporary dam and evacuation of the floodplain 24 h ahead',
    method: 'water depth at a building = river rise − terrain height above the river − 2.5 m per km from the channel; not a hydrological study' });
}

function kpi(y) { const ys = traffic.years; let ti = 0; while (ti < ys.length - 1 && ys[ti] < y) ti++; return { year: ys[ti], k: traffic.by_scenario[S][String(ys[ti])].kpi }; }
function lrtDelay(phase) {
  const ph = clamp((phase || 1) - 1, 0, cons.lrt.phase_year[S].length - 1), py = cons.lrt.phase_year[S][ph], y = Math.min(2050, py + 1);
  const st = cons.lrt.stations.filter(s => Math.round(s[2]) === ph);
  let near = 0; for (const p of st) near += residentsNear(p[0], p[1], 900, y);
  const cars = near * 0.12 * (0.30 - 0.10) / 1.3;
  const { k } = kpi(y), ck = k.congested_km || 0, allCars = k.car_trips || 1;
  const extraKm = ck * cars / Math.max(allCars, 1) * 2.5, lost = near * 0.12 * 2 * 22 * 24 * (12 / 60) * 2000 / 1e9;
  const name = cons.lrt.phase_names[ph];
  const a = { src: ['model_traffic', 'model_city'] };
  a.text = `ЛРТ «${name}» вместо ${py} года откроется в ${py + 2}. У ${st.length} станций живут ~${N0(near / 1000)} тыс. человек — на 2 года они пересаживаются на машины: +${N0(cars)} машин в утренний час пик, заторы растут на ~${N0(extraKm)} км (+${R(100 * extraKm / Math.max(ck, 1))} %). Потерянное время людей — около ${N1(lost)} млрд ₸. Что поможет: временный BRT по трассе ЛРТ (см. «Ситуационный центр»).`;
  return pack(a, 'lrt_delay', "morning-peak traffic layer; homes within 900 m of the phase's stations in amber; the stations as pins", {
    lrt_phase: ph + 1, phase_name: name, planned_opening_year: py, delayed_opening_year: py + 2, delay_years: 2, stations: st.length, residents_within_900m_of_stations: R(near),
    extra_cars_morning_peak: R(cars), congested_km_on_time: R(ck), congested_km_with_delay: R(ck + extraKm), congestion_increase_pct: R(100 * extraKm / Math.max(ck, 1)),
    lost_time_bn_kzt: R1(lost), year_modelled: y, mitigation: 'temporary BRT along the LRT route (see the Situation centre tab)',
    method: '12 % of residents travel in the morning peak; near stations 30 % would take the LRT, 10 % take a bus without it, the rest drive (1.3 people per car); +12 min per trip, 2 000 ₸ per hour, over 24 months' });
}
function trafficA(y) {
  const { year, k } = kpi(y), ck = k.congested_km, dl = k.avg_delay_pct;
  const a = { src: ['model_traffic'], chart: 'Заторы, км', text: `Утренний час пик ${year} года: ${N0(ck)} км дорог в заторе, время в пути дольше свободного на ${R(dl)} %. Красным на карте — участки, где поток выше пропускной способности. Адаптивные светофоры уменьшат задержку примерно на 18 % (история №1).` };
  return pack(a, 'traffic', 'morning-peak traffic layer: red = roads loaded above 85 % of their capacity', {
    model_year: year, congested_km: R(ck), travel_time_above_free_flow_pct: R(dl), adaptive_signals_delay_cut_pct: 18, note: 'traffic is modelled every 5 years; adaptive signals effect = QTwin estimate (AI story 1)' });
}
function population(y) {
  let tot = 0; for (let d = 0; d < 4; d++) tot += residents(d, y);
  const a = { src: ['model_city'], chart: 'Жители, тыс.', text: `В ${y} году в Alatau City живёт ~${N0(tot / 1000)} тыс. человек.` };
  return pack(a, 'population', 'the whole city', { year: y, residents: R(tot), by_district: [0, 1, 2, 3].map(d => ({ district: DN[d], residents: R(residents(d, y)) })),
    method: 'housing floor area / 30 m² per person (QTwin build-out scenario of the master plan), not official statistics' });
}

export const TOPICS = ['school_deficit', 'school_site', 'construction_risk', 'power_shortage', 'flood', 'lrt_delay', 'traffic', 'population'];
export function analyze({ topic = '', year, phase } = {}) {
  const t = String(topic).toLowerCase().trim();
  if (!TOPICS.includes(t)) return { kind: 'model', error: 'unknown topic', topics: TOPICS, sources: [] };
  const Y = YEAR, yr = def => year > 0 ? clamp(Math.round(year), MIN_Y, MAX_Y) : def;
  const needB = ['school_site', 'construction_risk', 'flood', 'lrt_delay', 'population'].includes(t), needT = ['lrt_delay', 'traffic'].includes(t);
  if ((needB && !buildings()) || (needT && !traffic)) return { kind: 'model', error: 'twin data not loaded', sources: [] };
  switch (t) {
    case 'school_deficit': return schools(yr(Y < 2030 ? 2035 : Y));
    case 'school_site': return placement(yr(clamp(Y, 2032, 2050)));
    case 'construction_risk': return risky(yr(Y < 2027 || Y > 2048 ? 2033 : Y));
    case 'power_shortage': return power();
    case 'flood': return flood(yr(Math.max(Y, 2040)));
    case 'lrt_delay': return lrtDelay(phase || 1);
    case 'traffic': return trafficA(yr(Math.max(Y, 2035)));
    case 'population': return population(yr(Y));
  }
}
