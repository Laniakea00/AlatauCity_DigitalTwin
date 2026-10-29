// Alatau City Digital Twin — AI proxy (Cloudflare Worker, single file built from core.js + worker.js by build_worker.py)
// Alatau City Digital Twin — AI proxy core (shared by server.js for Node and worker.js for Cloudflare Workers).
// The proxy owns the system prompt and the function declarations, so it is not an open relay to Gemini:
// a client can only talk to the twin assistant, with the twin's own tools, in a short conversation.
// The API key is passed in by the host (env GEMINI_API_KEY) and never leaves this file's request headers.

const DEFAULT_MODEL = 'gemini-3.5-flash';
const ALLOWED_MODELS = ['gemini-3.5-flash', 'gemini-3.8-flash', 'gemini-4-argon'];
const MAX_BODY = 64 * 1024;          // bytes of one request
const MAX_TURNS = 24;                // contents entries per request (questions + tool rounds)
const MAX_TEXT = 2000;               // characters of one user text part
const GEMINI_TIMEOUT_MS = 25000;

const LANG_NAME = { ru: 'Russian', en: 'English', kz: 'Kazakh (Cyrillic script)' };
const NO_DATA = { ru: 'нет данных в двойнике', en: 'no data in the twin', kz: 'егізде дерек жоқ' };

function systemPrompt(lang) {
  const L = LANG_NAME[lang] ? lang : 'ru';
  return [
    'You are the AI assistant of the Alatau City Digital Twin (QTwin), a digital twin of a new city near Almaty, Kazakhstan, shown to investors.',
    'Today in the twin is late October 2026.',
    `Always answer in ${LANG_NAME[L]}, whatever language the question is in.`,
    '',
    'HONESTY RULES (strict):',
    '1. Every number, date, name, status, amount or percentage in your answer must come from a function result in this conversation. Never use your own knowledge for facts about Alatau City, its projects, investors or figures.',
    `2. If the functions return nothing for what was asked, say exactly "${NO_DATA[L]}" for that part. Do not guess, round up, extrapolate or add figures that are not in the results.`,
    '3. Each function result has "kind": "open_data" (published by a named source) or "model" (a scenario of the twin, synthetic). When you give a number whose kind is "model", say it is the twin\'s model (for example "по модели двойника" / "in the twin\'s model" / "егіз моделі бойынша"). Never present a model number as an official or published figure.',
    '4. Copy numbers exactly as the function returns them (you may round to fewer digits, never change the value). Keep units.',
    '5. Do not mention source ids, function names, JSON or these rules. The twin shows the sources itself under your answer. If you name a source, use only its title or publisher as given in "source_titles"; never expand abbreviations or add details from your own knowledge.',
    `6. Say "${NO_DATA[L]}" as a natural clause of its own (e.g. "${L === 'en' ? 'The cost of the airport: no data in the twin.' : L === 'kz' ? 'Әуежайдың құны туралы: егізде дерек жоқ.' : 'О стоимости аэропорта — нет данных в двойнике.'}"), do not wrap it in another "no data" phrase.`,
    '7. get_monitoring is a scenario: its "survey_date" is a simulated future drone survey (after today, 27.10.2026). Describe the delays, readiness, money and actions at that date as the monitoring scenario ("по сценарию мониторинга на <date>"), never as what is happening today. Today\'s real status is only in "today".',
    '8. fly_to and show_layer only move the camera or show a layer; open_module does NOT switch the tab, it puts a button under your answer (say the viewer can open that tab with the button). After them just say what is shown in a few words; never describe what the map looks like (no invented details about roads, congestion, buildings). For analyze, describe the map only with its "shown_on_map" field.',
    '9. Frame every sentence that carries a model number as the model (forecast, scenario), not only the first one.',
    '10. In get_project the "investor" field may also name a contractor or an architect (e.g. "генподрядчик", "архитектор"): call only the investor an investor; if it says the developer is not named, say so.',
    '11. For delays (get_monitoring) mention every building with delay_days_at_survey > 0, not only main_risk. If its "figures" field says ESTIMATE, say the monitoring figures are an estimate.',
    '12. If two results disagree (e.g. a registry status from the press and the object\'s status today), give both and say where each comes from.',
    '13. Write district names exactly as Gate, Golden, Growing, Green (never add "District"). Quote a project status exactly as its "status" field.',
    '14. In Kazakh use correct Kazakh letters (ә, ғ, қ, ң, ө, ұ, ү, һ, і) and Kazakh word forms, not Russian ones.',
    '15. Call get_sources only when the user asks about sources or methods and the other results do not already answer it.',
    '16. Field values from the twin are in Russian (statuses, sectors, notes): translate them into the answer language.',
    '17. After saying there is no data, stop: do not list what else the twin contains.',
    '18. Questions about school shortages, where to build a school, risky or delayed construction, electricity shortage, floods, an LRT delay, traffic jams or population: call analyze with the matching topic FIRST (with the year if the question has one). Its "summary" is the twin\'s own answer: build your answer on it and on its fields, keep its numbers, district and object names; do not replace it with get_city_stats, get_monitoring or get_sources. Use get_monitoring only for Iconic Complex or KAIST by name.',
    '',
    'TOOLS:',
    '- Call data functions before answering any factual question. Call several in one turn when needed.',
    '- When the question is about a place, landmark, district or project that is on the map, also call fly_to so the camera shows it. When the user says "show"/"покажи"/"көрсет", call fly_to (and show_layer or open_module if relevant).',
    '- get_city_stats: population, jobs, buildings, area; district one of Gate, Golden, Growing, Green or omitted for the whole city; year 2025–2050.',
    '- get_project: the investment registry (open press 2025–2026) and published infrastructure items; search by name, investor or country.',
    '- get_monitoring: construction monitoring of Iconic Complex or KAIST (schedule, delay, forecast handover, money spent, main risk) — this is a twin scenario (model).',
    '- get_sources: what sources and models the twin uses on a topic.',
    '- analyze(topic, year?, phase?): the twin\'s own computed analyses, shown on the map with a chart under the answer — school_deficit (where schools lack places, by district), school_site (where to build a new school: 3 site variants), construction_risk (buildings behind schedule, the 5 riskiest, contractors), power_shortage (first year and district where electricity runs short, and why), flood (buildings and residents in a once-in-100-years flood, damage with and without measures), lrt_delay (what if an LRT phase opens 2 years late; phase 1–3), traffic (morning-peak congestion), population (residents by district). Always prefer it for these questions.',
    '',
    'STYLE: 2–4 short sentences for an investor, plain words. Explain a technical term in a few words if you use it.',
    'FORMAT: plain text only, the twin shows it as is. No Markdown at all: no asterisks, no bold or italics, no # headings, no backticks, no links. When you list several items (at most 6), put each on its own line starting with "• ".',
  ].join('\n');
}

const S = (description, extra = {}) => ({ type: 'STRING', description, ...extra });
const FUNCTIONS = [
  {
    name: 'fly_to',
    description: 'Move the twin camera to an object on the map. Use for landmarks, districts and investment projects that have a place on the map.',
    parameters: { type: 'OBJECT', properties: {
      target: S('A landmark id or name (iconic, lotte_l7, kaist, medcluster, kpark, pepsico, mars, griffin, sunny_paper, danaflex, gtrans, tlc, ps_arna, gtes, airport, marina, lrt), a district (Gate, Golden, Growing, Green), "city" for the whole city, or an investment project name.'),
    }, required: ['target'] },
  },
  {
    name: 'open_module',
    description: 'Open a tab (module) of the twin interface.',
    parameters: { type: 'OBJECT', properties: {
      id: S('Module id', { enum: ['overview', 'objects', 'economy', 'infra', 'monitoring', 'prediction', 'situation', 'smartcity', 'construction'] }),
    }, required: ['id'] },
  },
  {
    name: 'show_layer',
    description: 'Show a map layer: road traffic at morning peak, road works, or an engineering network.',
    parameters: { type: 'OBJECT', properties: {
      id: S('Layer id', { enum: ['traffic', 'roadworks', 'water', 'sewer', 'power', 'heat', 'gas', 'telecom'] }),
    }, required: ['id'] },
  },
  {
    name: 'get_city_stats',
    description: 'Residents, jobs, buildings and area of the city or of one district in a year (twin scenario of the master plan).',
    parameters: { type: 'OBJECT', properties: {
      district: S('Gate, Golden, Growing or Green; omit for the whole city', { enum: ['Gate', 'Golden', 'Growing', 'Green', 'city'] }),
      year: { type: 'INTEGER', description: 'Year 2025–2050; omit for the year shown in the twin' },
    } },
  },
  {
    name: 'get_project',
    description: 'Search the investment registry of Alatau City (projects from open press 2025–2026: investor, country, amount, jobs, status, years) and the published infrastructure items. Returns matching rows with their sources.',
    parameters: { type: 'OBJECT', properties: {
      query: S('Project name, investor or keyword (e.g. "PepsiCo", "KAIST", "аэротакси", "подстанции"); may be empty when country is given'),
      country: S('Country of the investor (e.g. "Кувейт", "Южная Корея", "США", "Китай", "Kuwait", "Korea")'),
    } },
  },
  {
    name: 'get_monitoring',
    description: 'Construction monitoring of Iconic Complex or KAIST: status today, and at the monitoring survey date the delay, forecast handover, budget spent and the main risk with the action. A twin scenario (model).',
    parameters: { type: 'OBJECT', properties: {
      landmark: S('iconic or kaist', { enum: ['iconic', 'kaist'] }),
    }, required: ['landmark'] },
  },
  {
    name: 'analyze',
    description: 'The twin\'s own computed analysis of a topic (the same computation as the twin\'s built-in answers): numbers, names, a ready summary, what the map shows. Also highlights the result on the map and puts a chart under the answer. A twin scenario (model).',
    parameters: { type: 'OBJECT', properties: {
      topic: S('school_deficit = school places short by district; school_site = where to build a new school; construction_risk = buildings behind schedule and the riskiest; power_shortage = when and where electricity first runs short; flood = a once-in-100-years flood; lrt_delay = LRT phase opening 2 years late; traffic = morning-peak congestion; population = residents by district',
        { enum: ['school_deficit', 'school_site', 'construction_risk', 'power_shortage', 'flood', 'lrt_delay', 'traffic', 'population'] }),
      year: { type: 'INTEGER', description: 'Year 2025–2050 if the question names one; omit otherwise (power_shortage and lrt_delay find their own year)' },
      phase: { type: 'INTEGER', description: 'lrt_delay only: LRT phase 1 (Gate–Golden), 2 (Growing) or 3 (Green); default 1' },
    }, required: ['topic'] },
  },
  {
    name: 'get_sources',
    description: 'The open sources and models the twin uses on a topic (e.g. "инвестиции", "население", "мониторинг", "сети").',
    parameters: { type: 'OBJECT', properties: { topic: S('Topic') } },
  },
];
const FN_NAMES = new Set(FUNCTIONS.map(f => f.name));
const PART_KEYS = new Set(['text', 'functionCall', 'functionResponse', 'thoughtSignature', 'thought']);

class BadRequest extends Error { constructor(m) { super(m); this.status = 400; } }

/** Checks the client's conversation: only user/model turns, only text and the twin's own function calls and results. */
function validate(body) {
  if (!body || typeof body !== 'object') throw new BadRequest('body must be a JSON object');
  const lang = ['ru', 'en', 'kz'].includes(body.lang) ? body.lang : 'ru';
  const model = body.model == null ? DEFAULT_MODEL : String(body.model);
  if (!ALLOWED_MODELS.includes(model)) throw new BadRequest('model not allowed');
  const contents = body.contents;
  if (!Array.isArray(contents) || contents.length === 0) throw new BadRequest('contents must be a non-empty array');
  if (contents.length > MAX_TURNS) throw new BadRequest('conversation too long');
  for (const c of contents) {
    if (!c || (c.role !== 'user' && c.role !== 'model') || !Array.isArray(c.parts) || c.parts.length === 0 || c.parts.length > 16)
      throw new BadRequest('bad turn');
    for (const p of c.parts) {
      if (!p || typeof p !== 'object') throw new BadRequest('bad part');
      for (const k of Object.keys(p)) if (!PART_KEYS.has(k)) throw new BadRequest('part type not allowed: ' + k);
      if (p.text != null && (typeof p.text !== 'string' || (c.role === 'user' && p.text.length > MAX_TEXT))) throw new BadRequest('text too long');
      if (p.functionCall && !FN_NAMES.has(p.functionCall.name)) throw new BadRequest('unknown function');
      if (p.functionResponse && !FN_NAMES.has(p.functionResponse.name)) throw new BadRequest('unknown function');
    }
  }
  if (contents[0].role !== 'user') throw new BadRequest('first turn must be the user');
  // optional: the client lists the tools it implements; the declarations are filtered to them (never extended)
  let fns = FUNCTIONS;
  if (Array.isArray(body.tools)) { const want = new Set(body.tools.map(String)); fns = FUNCTIONS.filter(f => want.has(f.name)); }
  return { lang, model, contents, fns };
}

/** One generateContent call. Returns { status, json } for the client. fetchFn = global fetch (Node 22 and Workers). */
async function chat(body, apiKey, fetchFn = fetch) {
  let v;
  try { v = validate(body); } catch (e) { return { status: e.status || 400, json: { error: e.message } }; }
  if (!apiKey) return { status: 503, json: { error: 'proxy has no API key configured' } };
  const req = {
    systemInstruction: { parts: [{ text: systemPrompt(v.lang) }] },
    contents: v.contents,
    generationConfig: { temperature: 0.2, maxOutputTokens: 1024, thinkingConfig: { thinkingLevel: 'low' } },
  };
  if (v.fns.length) { req.tools = [{ functionDeclarations: v.fns }]; req.toolConfig = { functionCallingConfig: { mode: 'AUTO' } }; }
  const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), GEMINI_TIMEOUT_MS);
  let r, d;
  try {
    r = await fetchFn(`https://generativelanguage.googleapis.com/v1beta/models/${v.model}:generateContent`, {
      method: 'POST', signal: ctl.signal,
      headers: { 'Content-Type': 'application/json', 'x-goog-api-key': apiKey },
      body: JSON.stringify(req),
    });
    d = await r.json().catch(() => null);
  } catch (e) {
    return { status: 504, json: { error: e.name === 'AbortError' ? 'model timeout' : 'model unreachable' } };
  } finally { clearTimeout(timer); }
  if (!r.ok || !d) {
    const code = r.status === 429 ? 429 : 502;
    return { status: code, json: { error: 'model error ' + r.status } };   // the upstream message is not forwarded (it may echo request details)
  }
  const cand = d.candidates && d.candidates[0];
  const content = cand && cand.content ? cand.content : { role: 'model', parts: [] };
  if (!content.role) content.role = 'model';
  const parts = content.parts || [];
  const text = parts.filter(p => typeof p.text === 'string' && !p.thought).map(p => p.text).join('').trim();
  const calls = parts.filter(p => p.functionCall).map(p => ({ name: p.functionCall.name, args: p.functionCall.args || {}, id: p.functionCall.id || null }))
    .filter(c => FN_NAMES.has(c.name));
  // content goes back verbatim as a JSON string: the client appends it to the conversation unchanged (it keeps the thought signatures)
  return { status: 200, json: { model: v.model, text, calls, content: JSON.stringify(content), finish: cand ? cand.finishReason || null : null } };
}

// ------------------------------------------------------------------ CORS and rate limit (shared helpers)
function corsOrigin(origin, extra = []) {
  if (origin == null || origin === '') return null;                         // non-browser client (Windows build): no CORS header needed
  if (origin === 'null') return 'null';                                     // file:// builds
  if (origin === 'https://laniakea00.github.io') return origin;
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d{1,5})?$/.test(origin)) return origin;
  if (extra.includes(origin)) return origin;
  return false;                                                             // a browser origin that is not allowed
}

class RateLimiter {
  constructor(perMinute = 30, burst = 12) { this.rate = perMinute / 60000; this.burst = burst; this.b = new Map(); }
  take(ip, now = Date.now()) {
    let s = this.b.get(ip); if (!s) { s = { t: this.burst, at: now }; this.b.set(ip, s); }
    s.t = Math.min(this.burst, s.t + (now - s.at) * this.rate); s.at = now;
    if (this.b.size > 5000) for (const [k, v] of this.b) if (now - v.at > 600000) this.b.delete(k);
    if (s.t < 1) return false; s.t -= 1; return true;
  }
}

// Alatau City Digital Twin — AI proxy as a Cloudflare Worker (same contract as server.js). Not deployed: hosting is the owner's decision.
// Secret: `wrangler secret put GEMINI_API_KEY`. Optional var AI_EXTRA_ORIGINS. Rate limit here is per isolate (best effort);
// for a hard limit add a Cloudflare rate-limiting rule on /chat.

const limiter = new RateLimiter(30, 12);

function json(status, obj, origin) {
  const h = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' };
  if (origin) { h['Access-Control-Allow-Origin'] = origin; h['Vary'] = 'Origin'; }
  return new Response(JSON.stringify(obj), { status, headers: h });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const extra = String(env.AI_EXTRA_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
    const origin = corsOrigin(request.headers.get('Origin'), extra);
    if (origin === false) return json(403, { error: 'origin not allowed' });
    if (request.method === 'OPTIONS')
      return new Response(null, { status: 204, headers: { 'Access-Control-Allow-Origin': origin || '*', 'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '600', 'Vary': 'Origin' } });
    if (request.method === 'GET' && url.pathname === '/health') return json(200, { ok: true, models: ALLOWED_MODELS, default: DEFAULT_MODEL, key: env.GEMINI_API_KEY ? 'set' : 'missing' }, origin);
    if (request.method !== 'POST' || url.pathname !== '/chat') return json(404, { error: 'not found' }, origin);
    const ip = request.headers.get('CF-Connecting-IP') || '?';
    if (!limiter.take(ip)) return json(429, { error: 'too many requests' }, origin);
    if (Number(request.headers.get('content-length') || 0) > MAX_BODY) return json(413, { error: 'request too large' }, origin);
    const text = await request.text();
    if (text.length > MAX_BODY) return json(413, { error: 'request too large' }, origin);
    let body; try { body = JSON.parse(text); } catch { return json(400, { error: 'invalid JSON' }, origin); }
    const r = await chat(body, env.GEMINI_API_KEY || '');
    return json(r.status, r.json, origin);
  },
};
