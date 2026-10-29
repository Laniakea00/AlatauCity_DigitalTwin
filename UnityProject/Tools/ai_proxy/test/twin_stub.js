// Test stand-in for the twin's functions (Assets/Scripts/DigitalTwin/Ai/AiTools.cs), built from the real data of the repository:
// StreamingAssets/twin/loads.json, Data/InvestRegistry.cs, Landmarks/LandmarkData.cs, Data/Sources.cs, Data/TwinModels.cs.
// The result shapes and the computations mirror AiTools.cs so the transcripts show what the model gets in Unity.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { analyze } from './twin_analyze.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ASSETS = path.resolve(HERE, '../../../Assets');
const DT = path.join(ASSETS, 'Scripts/DigitalTwin');
const read = p => fs.readFileSync(p, 'utf8');

// ------------------------------------------------------------------ a tiny C# argument-list reader
function splitArgs(s) {
  const out = []; let depth = 0, cur = '', str = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (str) { cur += c; if (c === '\\') { cur += s[++i]; continue; } if (c === '"') str = false; continue; }
    if (c === '"') { str = true; cur += c; continue; }
    if ('([{'.includes(c)) depth++; if (')]}'.includes(c)) depth--;
    if (c === ',' && depth === 0) { out.push(cur.trim()); cur = ''; continue; }
    cur += c;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}
/** Text of the call's argument list starting at index i (just after '('). */
function callArgs(src, i) {
  let depth = 1, str = false, j = i;
  for (; j < src.length; j++) {
    const c = src[j];
    if (str) { if (c === '\\') { j++; continue; } if (c === '"') str = false; continue; }
    if (c === '"') str = true; else if (c === '(') depth++; else if (c === ')') { depth--; if (depth === 0) break; }
  }
  return src.slice(i, j);
}
function val(tok, consts) {
  tok = tok.trim();
  if (tok === 'null') return null;
  if (tok === 'true') return true; if (tok === 'false') return false;
  if (/^".*"$/s.test(tok)) return tok.split(/"\s*\+\s*"/).join('').slice(1, -1).replace(/\\"/g, '"');
  if (consts[tok] !== undefined) return consts[tok];
  const e = tok.replace(/(\d)f\b/g, '$1').replace(/KztPerUsd/g, '447.94');
  if (/^[\d.eE+\-*/ ()]+$/.test(e)) return Function('return (' + e + ')')();
  return tok;
}

// ------------------------------------------------------------------ sources
const SRC_CONST = {};
const sourcesCs = read(path.join(DT, 'Data/Sources.cs')), registryCs = read(path.join(DT, 'Data/InvestRegistry.cs')), modelsCs = read(path.join(DT, 'Data/TwinModels.cs'));
for (const cs of [sourcesCs, registryCs, modelsCs, read(path.join(DT, 'Landmarks/IconicMonitorControl.cs'))]) {
  for (const m of cs.matchAll(/(?:const string|,)\s*(\w+)\s*=\s*("[^"]*"|Sources\.\w+)/g)) {
    const v = m[2].startsWith('"') ? m[2].slice(1, -1) : null;
    if (v) { SRC_CONST[m[1]] = v; SRC_CONST['Sources.' + m[1]] = v; SRC_CONST['DSources.' + m[1]] = v; }
  }
}
for (const m of registryCs.matchAll(/(\w+)\s*=\s*Sources\.(\w+)/g)) SRC_CONST[m[1]] = SRC_CONST['Sources.' + m[2]];
for (const m of modelsCs.matchAll(/(\w+)\s*=\s*"([^"]+)"/g)) SRC_CONST['TwinModels.' + m[1]] = m[2];
export const SOURCES = {};
for (const cs of [sourcesCs, registryCs, modelsCs, read(path.join(DT, 'Landmarks/IconicMonitorControl.cs'))]) {
  for (const m of cs.matchAll(/(?:Sources|DSources)?\.?\bRegister(Model)?\(/g)) {
    const a = splitArgs(callArgs(cs, m.index + m[0].length)); if (a.length < 2) continue;
    const id = val(a[0], SRC_CONST); if (typeof id !== 'string' || id === 's') continue;
    if (m[1]) SOURCES[id] = { id, title: val(a[1], SRC_CONST), publisher: 'QTwin', model: true, note: val(a[2] || 'null', SRC_CONST) };
    else SOURCES[id] = { id, title: val(a[1], SRC_CONST), publisher: val(a[2], SRC_CONST), date: val(a[3] || 'null', SRC_CONST), url: val(a[4] || 'null', SRC_CONST), note: val(a[5] || 'null', SRC_CONST), model: false };
  }
}

// ------------------------------------------------------------------ invest registry
const SECTORS = JSON.parse('[' + registryCs.match(/Sectors = \{([^}]*)\}/)[1] + ']');
const STATUS = JSON.parse('[' + registryCs.match(/StatusNames = \{([^}]*)\}/)[1] + ']');
const DN = ['Gate', 'Golden', 'Growing', 'Green'];
export const PROJECTS = [];
{
  const body = registryCs.slice(registryCs.indexOf('List<Project> Projects'), registryCs.indexOf('// ------------------------------------------------------------------ infrastructure'));
  for (const m of body.matchAll(/\bP\(/g)) {
    const a = splitArgs(callArgs(body, m.index + 2)).map(t => val(t, SRC_CONST));
    const [name, inv, country, sector, district, status, src, usd = 0, jobs = 0, years = null, lm = null, note = null, amountNote = null, src2 = null] = a;
    PROJECTS.push({ name, investor: inv, country, sector, district, status, src, usd, jobs, years, lm, note, amountNote, src2 });
  }
}
export const INFRA = [];
for (const m of registryCs.matchAll(/new InfraItem \{([^}]*)\}/g)) {
  const o = {}; for (const kv of splitArgs(m[1])) { const k = kv.slice(0, kv.indexOf('=')).trim(); o[k] = val(kv.slice(kv.indexOf('=') + 1), SRC_CONST); }
  INFRA.push(o);
}

// ------------------------------------------------------------------ landmarks (ids, names, the parts of Iconic and KAIST)
const lmCs = read(path.join(DT, 'Landmarks/LandmarkData.cs'));
export const LANDMARKS = [];
for (const m of lmCs.matchAll(/Id = "(\w+)", Name = "([^"]+)", Short = "([^"]+)"/g)) {
  if (lmCs.slice(m.index - 14, m.index).includes('LPart')) continue;
  const rest = lmCs.slice(m.index, m.index + 4000);
  const lm = { id: m[1], name: m[2], short: m[3], district: +(rest.match(/District = (\d)/) || [0, -1])[1],
    statusNote: (rest.match(/StatusNote = "([^"]*)"/) || [])[1], source: (rest.match(/Source = "([^"]*)"/) || [])[1], sourceDate: (rest.match(/SourceDate = "([^"]*)"/) || [])[1], parts: [] };
  LANDMARKS.push(lm);
}
for (const lm of LANDMARKS) {
  const start = lmCs.indexOf(`Id = "${lm.id}", Name`); const next = lmCs.indexOf('L.Add(', start + 10); const seg = lmCs.slice(start, next < 0 ? undefined : next);
  for (const m of seg.matchAll(/new LPart \{([\s\S]*?)\}\)/g)) {
    const o = {}; for (const kv of splitArgs(m[1])) { const e = kv.indexOf('='); if (e < 0) continue; o[kv.slice(0, e).trim()] = val(kv.slice(e + 1), SRC_CONST); }
    lm.parts.push({ name: o.Name, A: o.A, B: o.B, capex: o.Capex || 0, delay: o.Delay || 0, recover: !!o.Recover, risk: o.Risk, tower: !!o.Tower });
  }
}

// ------------------------------------------------------------------ loads (residents, jobs by district and year)
const loads = JSON.parse(read(path.join(ASSETS, 'StreamingAssets/twin/loads.json')));
const AREA_HA = [3988, 15660, 36622, 31730], TARGET_2050K = [223, 675, 650, 320];

// ------------------------------------------------------------------ the functions (mirror of AiTools.cs)
const DAY = y => { const d = new Date(Date.UTC(Math.floor(y), 0, 1) + (y - Math.floor(y)) * 365 * 86400000); return `${String(d.getUTCDate()).padStart(2, '0')}.${String(d.getUTCMonth() + 1).padStart(2, '0')}.${d.getUTCFullYear()}`; };
const clamp01 = x => Math.max(0, Math.min(1, x)), smooth = (a, b, t) => { t = clamp01((t - a) / (b - a)); return t * t * (3 - 2 * t); };
const norm = s => String(s || '').toLowerCase().replace(/ё/g, 'е');
const COUNTRY_ALIASES = { kuwait: 'кувейт', korea: 'корея', 'south korea': 'корея', usa: 'сша', us: 'сша', 'united states': 'сша', america: 'сша', 'ақш': 'сша', china: 'китай', 'қытай': 'китай', germany: 'германия', 'германия': 'германия', kazakhstan: 'казахстан', 'қазақстан': 'казахстан', 'кәрея': 'корея', 'оңтүстік корея': 'корея' };

let YEAR = 2026; export function setYear(y) { YEAR = y; }
const SCEN = 'base';

function cityStats({ district, year } = {}) {
  const y = Math.max(2026, Math.min(2050, year ? Math.round(year) : YEAR)), yi = loads.years.indexOf(y);
  let d = DN.findIndex(x => norm(x) === norm(district));
  const L = loads.loads[SCEN], sum = k => d >= 0 ? L[k][d][yi] : L[k].reduce((s, a) => s + a[yi], 0);
  const r = { kind: 'model', scope: d >= 0 ? DN[d] : 'city', year: y, scenario: 'Базовый', residents: Math.round(sum('res')), jobs: Math.round(sum('jobs')),
    area_ha: d >= 0 ? AREA_HA[d] : AREA_HA.reduce((a, b) => a + b, 0), area_kind: 'open_data (master plan)',
    note: 'Twin scenario of the master-plan build-out: residents = housing floor area / 30 m² per person. Not official statistics.',
    sources: ['model_city', 'genplan_388'] };
  if (d < 0) r.by_district = DN.map((n, i) => ({ district: n, residents: Math.round(L.res[i][yi]) }));
  return r;
}

function projectRow(p) {
  return { name: p.name, investor: p.investor, country: p.country || 'не раскрыто', sector: SECTORS[p.sector], status: STATUS[p.status],
    amount_usd_m: p.usd > 0 ? Math.round(p.usd * 10) / 10 : 'не раскрыто', amount_note: p.amountNote || undefined, jobs: p.jobs > 0 ? p.jobs : 'не раскрыто',
    years: p.years || 'не раскрыто', district: p.district >= 0 ? DN[p.district] : 'не указан', on_map: !!p.lm, note: p.note, sources: [p.src, p.src2].filter(Boolean) };
}
function getProject({ query = '', country = '' } = {}) {
  const q = norm(query).trim(), c0 = norm(country).trim(), c = COUNTRY_ALIASES[c0] || c0;
  const toks = q.split(/[^\p{L}\p{N}]+/u).filter(t => t.length >= 3).map(t => t.slice(0, 5));
  const hay = p => norm([p.name, p.investor, p.country, SECTORS[p.sector], p.lm].join(' '));
  const byCountry = p => !c || norm(p.country).includes(c) || norm(p.investor).includes(c) || norm(p.note).includes(c);
  const hit = h => h.includes(q) || toks.some(t => h.includes(t));
  // names, investors, countries and sectors first; the free-text notes only when nothing else matches
  let found = PROJECTS.filter(p => byCountry(p) && (!q || hit(hay(p))));
  const infra = q ? INFRA.filter(i => { const h = norm([i.Name, i.Kind, i.What].join(' ')); return h.includes(q) || toks.some(t => h.includes(t)); }).slice(0, 5)
    .map(i => ({ name: i.Name, kind: i.Kind, what: i.What, when: i.When, status: i.Status, amount: i.Amount || 'не раскрыто', sources: [i.Src] })) : [];
  if (!found.length && !infra.length && q) found = PROJECTS.filter(p => byCountry(p) && hit(norm(p.note)));
  const rows = found.slice(0, 8).map(projectRow);
  const ids = new Set(); rows.forEach(r => r.sources.forEach(s => ids.add(s))); infra.forEach(r => r.sources.forEach(s => ids.add(s)));
  return { kind: 'open_data', registry_size: PROJECTS.length, found: rows.length, projects: rows, infrastructure: infra,
    government_summary: 'Government summary 26.08.2026: 67 investment projects ≈ $6.9 bn, ≈ 55 000 jobs, 26 infrastructure projects (the registry lists the ones named in the press).',
    note: rows.length + infra.length === 0 ? 'Nothing in the registry matches.' : 'Amounts and jobs as published; "не раскрыто" = not disclosed in the press.',
    sources: rows.length || !q ? [...ids, 'gov_summary_2608'].filter((x, i, a) => a.indexOf(x) === i) : [...ids] };
}

function monitoring({ landmark }) {
  const L = LANDMARKS.find(l => l.id === norm(landmark)); if (!L || !L.parts.length) return { kind: 'model', error: 'no monitoring for this object', available: ['iconic', 'kaist'], sources: [] };
  const P = L.parts, begin = Math.min(...P.map(p => p.A)), finish = Math.max(...P.map(p => p.B));
  const report = begin + 0.5 * (finish - begin), T0 = Math.floor(begin), T1 = Math.max(Math.ceil(finish + 0.05), 2030 + 1);
  const delayAt = (p, d) => { if (Math.abs(p.delay) < 1e-5) return 0; const up = smooth(0, 1, (d - (p.A + 0.1)) / 0.9); const down = d <= report || !p.recover ? 1 : clamp01(1 - (d - report) / 1.4); return p.delay * up * down; };
  const planP = (p, d) => d <= p.A ? 0 : clamp01((d - p.A) / Math.max(p.B - p.A, 0.01));
  const factP = (p, d) => planP(p, d - delayAt(p, d));
  const factDate = (p, q) => { q = Math.max(q, 1e-4); let a = T0 - 2, b = T1 + 3; for (let k = 0; k < 30; k++) { const m = (a + b) / 2; if (factP(p, m) >= q) b = m; else a = m; } return b; };
  const parts = P.map(p => ({ name: p.name, plan_handover: DAY(p.B), forecast_handover: DAY(factDate(p, 1)), delay_days_at_survey: Math.round(delayAt(p, report) * 365),
    plan_ready_pct: Math.round(planP(p, report) * 100), fact_ready_pct: Math.round(factP(p, report) * 100), budget_usd_m: p.capex }));
  const budget = P.reduce((s, p) => s + p.capex, 0), spent = P.reduce((s, p) => s + p.capex * factP(p, report), 0), planned = P.reduce((s, p) => s + p.capex * planP(p, report), 0);
  const fEnd = Math.max(...P.map(p => factDate(p, 1)));
  let worst = P[0], wv = -1; for (const p of P) { const v = delayAt(p, report) * p.capex; if (v > wv) { wv = v; worst = p; } }
  return { kind: 'model', object: L.name,
    today: { date: '27.10.2026', status: L.statusNote, kind: 'open_data', publishers: L.source, published: L.sourceDate },
    survey_date: DAY(report), survey_note: `Simulated drone survey on ${DAY(report)}, in the middle of the works and in the future relative to today (27.10.2026). Delays, readiness, forecast and money at that date are a twin scenario, not developer data.`,
    plan_handover: DAY(finish), forecast_handover: DAY(fEnd), forecast_vs_plan_days: Math.round((fEnd - finish) * 365),
    budget_usd_m: Math.round(budget), spent_usd_m_at_survey: Math.round(spent), planned_spent_usd_m_at_survey: Math.round(planned), spent_method: 'budget × actual readiness of each building',
    main_risk: { building: worst.name, delay_days: Math.round(delayAt(worst, report) * 365), risk_and_action: worst.risk },
    parts, sources: ['mon_schedule', 'mon_ev', 'mon_actions'] };
}

const TOPIC_SYN = [[/насел|жител|халық|тұрғын|popul|resident|people/, 'жител'], [/invest|инвест|инвес/, 'инвест'], [/monitor|монитор/, 'монитор'], [/стройк|құрылыс|construct/, 'стройк'],
  [/электр|power|electric|energy|энерг/, 'электр'], [/tax|налог|салық|regime|режим/, 'налог'], [/сет|network|grid|желі/, 'сет'], [/traffic|трафик|пробк|затор|транспорт/, 'транспорт']];
function sources({ topic = '' } = {}) {
  let t0 = norm(topic); for (const [re, w] of TOPIC_SYN) if (re.test(t0)) { t0 = w; break; }
  const t = t0, toks = t.split(/[^\p{L}\p{N}]+/u).filter(x => x.length >= 3).map(x => x.slice(0, 5));
  const by = f => Object.values(SOURCES).filter(s => { const h = norm(f(s)); return t && (h.includes(t) || toks.some(x => h.includes(x))); });
  let list = by(s => [s.title, s.publisher].join(' '));            // titles first, the notes only when no title matches
  if (!list.length) list = by(s => s.note || '');
  list = list.slice(0, 8);
  return { kind: 'open_data', found: list.length, sources_list: list.map(s => ({ title: s.title, publisher: s.publisher, date: s.date || undefined, url: s.url || undefined, model: s.model })), sources: list.map(s => s.id) };
}

const MODULES = { overview: 'Обзор', objects: 'Объекты', economy: 'Экономика', infra: 'Инфраструктура', monitoring: 'Мониторинг стройки', prediction: 'Прогноз', situation: 'Ситуационный центр', smartcity: 'Smart City', construction: 'Стройка' };
const LAYERS = { traffic: 'загрузка дорог в утренний час пик', roadworks: 'дорожные работы', water: 'водопровод', sewer: 'канализация', power: 'электросети', heat: 'теплосети', gas: 'газопровод', telecom: 'связь' };
function flyTo({ target = '' }) {
  const t = norm(target).trim();
  const d = DN.findIndex(x => norm(x) === t); if (d >= 0) return { ok: true, shown: DN[d], type: 'district' };
  if (['city', 'город', 'весь город', 'қала'].includes(t)) return { ok: true, shown: 'Alatau City', type: 'city' };
  const lm = LANDMARKS.find(l => l.id === t) || LANDMARKS.find(l => norm(l.name) === t || norm(l.short) === t) || LANDMARKS.find(l => t.length >= 3 && (norm(l.name).includes(t) || norm(l.short).includes(t) || t.includes(norm(l.short))));
  if (lm) return { ok: true, shown: lm.name, type: 'landmark', district: DN[lm.district] };
  const p = PROJECTS.find(p => p.lm && (norm(p.name).includes(t) || norm(p.investor).includes(t)));
  if (p) { const l2 = LANDMARKS.find(l => l.id === p.lm); if (l2) return { ok: true, shown: l2.name, type: 'project' }; }
  return { ok: false, error: 'not on the map', known: LANDMARKS.map(l => l.id) };
}

export function run(name, args) {
  const r = run0(name, args);
  if (Array.isArray(r.sources) && r.sources.length) r.source_titles = r.sources.map(id => SOURCES[id]).filter(Boolean).map(s => s.model ? `${s.title} (model QTwin)` : `${s.publisher}${s.date ? ' · ' + s.date : ''} · ${s.title}`);
  return r;
}
function run0(name, args) {
  switch (name) {
    case 'fly_to': return flyTo(args);
    case 'open_module': return MODULES[args.id] ? { ok: true, offered: MODULES[args.id], note: 'The tab is NOT opened automatically: a button «open the tab» is shown under the answer.' } : { ok: false, error: 'unknown module' };
    case 'analyze': return analyze(args);
    case 'show_layer': return LAYERS[args.id] ? { ok: true, shown: LAYERS[args.id] } : { ok: false, error: 'unknown layer' };
    case 'get_city_stats': return cityStats(args);
    case 'get_project': return getProject(args);
    case 'get_monitoring': return monitoring(args);
    case 'get_sources': return sources(args);
  }
  return { ok: false, error: 'unknown function' };
}
