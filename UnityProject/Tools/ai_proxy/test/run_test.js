// Imitates the Unity client loop (Ai/AiClient.cs) against a running proxy: question → model asks for functions → the twin stub runs them
// on the repository's data → results go back → the model answers. Writes a Markdown transcript (no key is ever seen by this script).
// Usage: node test/run_test.js [proxyUrl] [out.md]
import fs from 'node:fs';
import { run } from './twin_stub.js';

const URL_ = process.argv[2] || 'http://localhost:8787';
const OUT = process.argv[3] || 'transcripts.md';
const MAX_ROUNDS = 4;

export const QUESTIONS = [
  ['ru', 'Успевает ли Iconic?'],
  ['ru', 'Сколько людей будет жить в Gate в 2030?'],
  ['ru', 'Покажи KAIST'],
  ['ru', 'Какие проекты в реестре от Кувейта?'],
  ['en', 'Which American companies invest in Alatau and how much?'],
  ['en', 'How many people will live in the whole city in 2050? Where does this number come from?'],
  ['kz', 'KAIST құрылысы кестеден қалып жатыр ма?'],
  ['kz', 'Gate ауданында 2035 жылы қанша адам тұрады?'],
  ['ru', 'Сколько стоит новый аэропорт Алатау?'],
  ['en', 'Show me the traffic at the morning peak'],
  ['ru', 'Какой ВВП у Alatau City и сколько налогов он платит?'],
  ['ru', 'Какие инфраструктурные проекты по электричеству и сколько они стоят?'],
];

// round 2 (w9): the six suggested chips of the AI tab in RU, two in EN and two in KZ (SET=w9)
export const QUESTIONS_W9 = [
  ['ru', 'Где в 2035 не хватает школ?'],
  ['ru', 'Что будет, если ЛРТ до Golden запустят на 2 года позже?'],
  ['ru', 'Покажи самые рискованные стройки'],
  ['ru', 'Когда впервые не хватит электроэнергии?'],
  ['ru', 'Какие дома затопит паводок?'],
  ['ru', 'Где поставить новую школу?'],
  ['en', 'Where will there be a shortage of school places in 2035?'],
  ['en', 'Show me the riskiest construction sites'],
  ['kz', '2035 жылы қай жерде мектеп жетіспейді?'],
  ['kz', 'Электр қуаты алғаш рет қашан жетпей қалады?'],
];
const MD = /\*\*|__|^\s*[*-]\s|^\s*#|`/m;

async function post(body) {
  const t0 = Date.now();
  const r = await fetch(URL_ + '/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'http://localhost:5173' }, body: JSON.stringify(body) });
  return { status: r.status, json: await r.json(), ms: Date.now() - t0 };
}

export async function ask(lang, q, model) {
  const contents = [{ role: 'user', parts: [{ text: q }] }];
  const log = { lang, q, rounds: [], text: '', sources: new Set(), ms: 0, error: null };
  for (let round = 0; round < MAX_ROUNDS; round++) {
    const r = await post({ lang, contents, model });
    log.ms += r.ms;
    if (r.status !== 200) { log.error = `HTTP ${r.status}: ${r.json.error}`; break; }
    const d = r.json;
    if (!d.calls.length) { log.text = d.text; log.model = d.model; break; }
    contents.push(JSON.parse(d.content));
    const parts = [];
    for (const c of d.calls) {
      const res = run(c.name, c.args || {});
      (res.sources || []).forEach(s => log.sources.add(s));
      log.rounds.push({ call: `${c.name}(${JSON.stringify(c.args || {})})`, result: res });
      const fr = { name: c.name, response: res }; if (c.id) fr.id = c.id;
      parts.push({ functionResponse: fr });
    }
    contents.push({ role: 'user', parts });
    if (round === MAX_ROUNDS - 1) log.error = 'no final answer after ' + MAX_ROUNDS + ' rounds';
  }
  return log;
}

function md(logs, title) {
  const out = [`# ${title}`, '', `Proxy: ${URL_} · model per answer below · stub functions on the repository data (twin_stub.js mirrors Ai/AiTools.cs).`, ''];
  logs.forEach((l, i) => {
    out.push(`## ${i + 1}. [${l.lang.toUpperCase()}] ${l.q}`, '');
    out.push(`*${l.model || '—'} · ${(l.ms / 1000).toFixed(1)} s · ${l.rounds.length} tool call(s)*`, '');
    if (l.rounds.length) {
      out.push('**Tool calls**', '');
      for (const r of l.rounds) {
        let res = JSON.stringify(r.result); if (res.length > 3000) res = res.slice(0, 3000) + ' …';
        out.push('- `' + r.call + '`', '  ```json', '  ' + res, '  ```');
      }
      out.push('');
    }
    out.push('**Answer** (raw model text)', '', l.error ? `> ERROR: ${l.error}` : l.text.split('\n').map(s => '> ' + s).join('\n'), '');
    if (!l.error) out.push(`Markdown in the raw text: ${MD.test(l.text) ? 'YES' : 'no'}`, '');
    if (l.sources.size) out.push('**Source chips:** ' + [...l.sources].join(', '), '');
  });
  return out.join('\n');
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const logs = [];
  for (const [lang, q] of (process.env.SET === 'w9' ? QUESTIONS_W9 : QUESTIONS)) { const l = await ask(lang, q); logs.push(l); console.log(`[${lang}] ${q} → ${l.error || l.text.slice(0, 120).replace(/\n/g, ' ')}`); }
  fs.writeFileSync(OUT, md(logs, process.env.TITLE || 'AI assistant transcripts (Gemini via proxy, twin functions)'));
  console.log('written', OUT);
}
