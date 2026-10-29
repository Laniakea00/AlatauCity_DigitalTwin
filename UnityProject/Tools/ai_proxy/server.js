// Alatau City Digital Twin — AI proxy for Node 22 (no dependencies).
// Run: GEMINI_API_KEY=... node server.js   (PORT, default 8787; AI_EXTRA_ORIGINS — comma-separated extra allowed origins)
// The key is read from the environment only. Request and response bodies are never logged.
import http from 'node:http';
import { chat, corsOrigin, RateLimiter, MAX_BODY, ALLOWED_MODELS, DEFAULT_MODEL } from './core.js';

const PORT = Number(process.env.PORT || 8787);
const KEY = process.env.GEMINI_API_KEY || '';
const EXTRA = (process.env.AI_EXTRA_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
const TRUST_PROXY = process.env.TRUST_PROXY === '1';          // behind a reverse proxy: take the client IP from X-Forwarded-For
const limiter = new RateLimiter(Number(process.env.RATE_PER_MIN || 30), Number(process.env.RATE_BURST || 12));

function send(res, status, obj, origin) {
  const h = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
  if (origin) { h['Access-Control-Allow-Origin'] = origin; h['Vary'] = 'Origin'; }
  res.writeHead(status, h); res.end(JSON.stringify(obj));
}

const server = http.createServer((req, res) => {
  const t0 = Date.now();
  const origin = corsOrigin(req.headers.origin, EXTRA);
  const done = (status, obj) => { send(res, status, obj, origin || null); console.log(`${new Date().toISOString()} ${req.method} ${req.url} ${status} ${Date.now() - t0} ms`); };
  if (origin === false) return done(403, { error: 'origin not allowed' });
  if (req.method === 'OPTIONS') {
    res.writeHead(204, { 'Access-Control-Allow-Origin': origin || '*', 'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '600', 'Vary': 'Origin' });
    return res.end();
  }
  if (req.method === 'GET' && req.url === '/health') return done(200, { ok: true, models: ALLOWED_MODELS, default: DEFAULT_MODEL, key: KEY ? 'set' : 'missing' });
  if (req.method !== 'POST' || req.url !== '/chat') return done(404, { error: 'not found' });
  const ip = (TRUST_PROXY && String(req.headers['x-forwarded-for'] || '').split(',')[0].trim()) || req.socket.remoteAddress || '?';
  if (!limiter.take(ip)) return done(429, { error: 'too many requests' });
  const len = Number(req.headers['content-length'] || 0);
  if (len > MAX_BODY) { done(413, { error: 'request too large' }); return req.destroy(); }
  const chunks = []; let size = 0, aborted = false;
  req.on('data', c => { size += c.length; if (size > MAX_BODY && !aborted) { aborted = true; done(413, { error: 'request too large' }); req.destroy(); } else chunks.push(c); });
  req.on('end', async () => {
    if (aborted) return;
    let body; try { body = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { return done(400, { error: 'invalid JSON' }); }
    try { const r = await chat(body, KEY); done(r.status, r.json); }
    catch { done(500, { error: 'proxy error' }); }
  });
});
server.requestTimeout = 40000; server.headersTimeout = 10000;
server.listen(PORT, () => console.log(`AI proxy on :${PORT} · key ${KEY ? 'set' : 'MISSING'} · default model ${DEFAULT_MODEL}`));
