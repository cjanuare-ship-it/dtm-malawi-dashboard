// Local test of the proxy with a fake Anthropic API (node test_worker.mjs)
import worker from './worker.js';
const calls = [];
globalThis.fetch = async (url, init) => { calls.push({ url, init }); const b = JSON.parse(init.body); return new Response(JSON.stringify({ id: 'msg_1', type: 'message', role: 'assistant', model: b.model, content: [{ type: 'text', text: 'ok' }], usage: {} }), { status: 200 }); };
const env = { ANTHROPIC_API_KEY: 'sk-test', ACCESS_TOKEN: 'secret-phrase', DAILY_LIMIT: '3' };
const site = 'https://cjanuare-ship-it.github.io';
const req = (method, { origin = site, token = 'secret-phrase', body, ip = '1.1.1.1' } = {}) => new Request('https://proxy.example.workers.dev/', { method, headers: { Origin: origin, 'x-dtm-token': token, 'content-type': 'application/json', 'CF-Connecting-IP': ip }, body: body ? JSON.stringify(body) : undefined });
let pass = 0, fail = 0; const ok = (name, cond, extra = '') => { cond ? pass++ : fail++; console.log((cond ? 'PASS ' : 'FAIL ') + name + (extra ? ' — ' + extra : '')); };
const msg = { model: 'claude-sonnet-5-5', max_tokens: 99999, system: [{ type: 'text', text: 'sys', cache_control: { type: 'ephemeral' } }], messages: [{ role: 'user', content: 'hi' }], tools: [], evil: 'drop me' };

let r = await worker.fetch(req('OPTIONS'), env); ok('preflight from site', r.status === 204 && r.headers.get('access-control-allow-origin') === site);
r = await worker.fetch(req('OPTIONS', { origin: 'https://evil.example' }), env); ok('preflight from other site refused', r.status === 403);
r = await worker.fetch(req('GET'), env); const h = await r.json(); ok('health check', r.status === 200 && h.ok && h.keyConfigured && h.tokenRequired);
r = await worker.fetch(req('POST', { body: msg, token: 'wrong' }), env); ok('wrong token refused', r.status === 401);
r = await worker.fetch(req('POST', { body: msg, origin: 'https://evil.example' }), env); ok('other origin refused', r.status === 403);
r = await worker.fetch(req('POST', { body: msg }), env); const j = await r.json(); const sent = JSON.parse(calls.at(-1).init.body);
ok('forwarded to Anthropic', r.status === 200 && j.content[0].text === 'ok' && calls.at(-1).url === 'https://api.anthropic.com/v1/messages');
ok('key added server-side', calls.at(-1).init.headers['x-api-key'] === 'sk-test');
ok('max_tokens capped', sent.max_tokens === 2000, String(sent.max_tokens));
ok('unknown fields dropped', !('evil' in sent));
ok('system with cache_control passed', sent.system[0].cache_control.type === 'ephemeral');
r = await worker.fetch(req('POST', { body: { ...msg, model: 'some-expensive-model' } }), env); ok('model limited to allow-list', JSON.parse(calls.at(-1).init.body).model === 'claude-sonnet-5-5');
await worker.fetch(req('POST', { body: msg }), env);
r = await worker.fetch(req('POST', { body: msg }), env); ok('daily limit reached (4th of 3)', r.status === 429, String(r.status));
r = await worker.fetch(req('POST', { body: msg, ip: '2.2.2.2' }), env); ok('other visitor not limited', r.status === 200);
r = await worker.fetch(req('POST', { body: { messages: [] }, ip: '3.3.3.3' }), env); ok('empty request refused', r.status === 400);
r = await worker.fetch(req('POST', { body: msg, ip: '4.4.4.4' }), { ...env, ANTHROPIC_API_KEY: '' }); ok('missing key reported', r.status === 500);
console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
