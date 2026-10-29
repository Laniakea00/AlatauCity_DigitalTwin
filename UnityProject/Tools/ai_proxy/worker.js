// Alatau City Digital Twin — AI proxy as a Cloudflare Worker (same contract as server.js). Not deployed: hosting is the owner's decision.
// Secret: `wrangler secret put GEMINI_API_KEY`. Optional var AI_EXTRA_ORIGINS. Rate limit here is per isolate (best effort);
// for a hard limit add a Cloudflare rate-limiting rule on /chat.
import { chat, corsOrigin, RateLimiter, MAX_BODY, ALLOWED_MODELS, DEFAULT_MODEL } from './core.js';

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
