/**
 * DTM Malawi · RE2CLID GIS workspace — assistant proxy (Cloudflare Worker)
 *
 * Lets the GIS website ask Claude without putting the Anthropic API key in the website.
 * The key lives only here, as a Cloudflare secret. The worker accepts requests from the website's address only,
 * checks an access token, limits model and answer length, and forwards the request to the Anthropic Messages API.
 *
 * Settings (Cloudflare → Workers → this worker → Settings → Variables and Secrets):
 *   ANTHROPIC_API_KEY  (Secret, required)  key from console.anthropic.com → API keys
 *   ACCESS_TOKEN       (Secret, required)  any long random phrase; the same phrase is entered in the website's assistant settings
 *   ALLOWED_ORIGINS    (Text, optional)    website addresses allowed to call, comma-separated
 *                                          default: https://cjanuare-ship-it.github.io
 *   MODELS             (Text, optional)    models allowed, comma-separated; the first is the default
 *                                          default: claude-sonnet-5-5,claude-haiku-5-5
 *   MAX_TOKENS         (Text, optional)    longest answer per request (default 2000)
 *   DAILY_LIMIT        (Text, optional)    requests per visitor per day, best effort (default 300)
 * Optional binding: a Rate Limiting binding named LIMITER for stricter per-visitor limits.
 * Also set a monthly spend limit for the key in the Anthropic console (Settings → Limits).
 */
const ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages';
const MAX_BODY = 600_000; // bytes; the workspace description plus a conversation fits well under this
const seen = new Map();   // best-effort per-visitor counter (per worker instance)

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const allowed = (env.ALLOWED_ORIGINS || 'https://cjanuare-ship-it.github.io').split(',').map(s => s.trim().replace(/\/$/, '')).filter(Boolean);
    const originOk = allowed.includes('*') || allowed.includes(origin);
    const cors = {
      'Access-Control-Allow-Origin': originOk ? origin || '*' : allowed[0] || 'null',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'content-type, x-dtm-token',
      'Access-Control-Max-Age': '86400',
      'Vary': 'Origin',
    };
    const reply = (status, obj) => new Response(JSON.stringify(obj), { status, headers: { ...cors, 'content-type': 'application/json' } });
    const fail = (status, code, message) => reply(status, { type: 'error', error: { type: code, message } });

    if (request.method === 'OPTIONS') return new Response(null, { status: originOk ? 204 : 403, headers: cors });
    if (!originOk) return fail(403, 'origin_not_allowed', `This address (${origin || 'unknown'}) may not use the assistant. Add it to ALLOWED_ORIGINS.`);
    if (request.method === 'GET') return reply(200, { ok: true, service: 'DTM Malawi GIS assistant proxy', models: models(env), keyConfigured: !!env.ANTHROPIC_API_KEY, tokenRequired: !!env.ACCESS_TOKEN });
    if (request.method !== 'POST') return fail(405, 'method_not_allowed', 'Use POST.');
    if (!env.ANTHROPIC_API_KEY) return fail(500, 'not_configured', 'The proxy has no ANTHROPIC_API_KEY secret yet.');
    if (env.ACCESS_TOKEN && request.headers.get('x-dtm-token') !== env.ACCESS_TOKEN) return fail(401, 'bad_token', 'The access token is missing or wrong. Check the assistant settings in the website.');

    // limits per visitor
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    if (env.LIMITER) { try { const { success } = await env.LIMITER.limit({ key: ip }); if (!success) return fail(429, 'rate_limited', 'Too many questions in a short time. Wait a minute and ask again.'); } catch (e) { /* binding not set up: ignore */ } }
    const day = new Date().toISOString().slice(0, 10), k = ip + '|' + day, n = (seen.get(k) || 0) + 1; seen.set(k, n);
    if (seen.size > 5000) for (const key of seen.keys()) if (!key.endsWith(day)) seen.delete(key);
    if (n > (+env.DAILY_LIMIT || 300)) return fail(429, 'daily_limit', 'The daily number of questions for this connection has been reached. Try again tomorrow.');

    // read and check the request
    const len = +(request.headers.get('content-length') || 0); if (len > MAX_BODY) return fail(413, 'too_large', 'The question and workspace description are too large.');
    let body; try { const text = await request.text(); if (text.length > MAX_BODY) return fail(413, 'too_large', 'The question and workspace description are too large.'); body = JSON.parse(text); } catch (e) { return fail(400, 'invalid_json', 'The request is not valid JSON.'); }
    if (!body || !Array.isArray(body.messages) || !body.messages.length) return fail(400, 'invalid_request', 'messages are required.');
    const ms = models(env); const model = ms.includes(body.model) ? body.model : ms[0];
    const maxTokens = Math.min(+body.max_tokens || 1500, +env.MAX_TOKENS || 2000);
    const forward = { model, max_tokens: maxTokens, messages: body.messages };
    for (const key of ['system', 'tools', 'tool_choice', 'temperature']) if (body[key] !== undefined) forward[key] = body[key];

    let res;
    try {
      res = await fetch(ANTHROPIC_URL, { method: 'POST', headers: { 'content-type': 'application/json', 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' }, body: JSON.stringify(forward) });
    } catch (e) { return fail(502, 'upstream_unreachable', 'Could not reach Anthropic. Try again shortly.'); }
    const out = await res.text();
    return new Response(out, { status: res.status, headers: { ...cors, 'content-type': 'application/json' } });
  },
};
function models(env) { return (env.MODELS || 'claude-sonnet-5-5,claude-haiku-5-5').split(',').map(s => s.trim()).filter(Boolean); }
