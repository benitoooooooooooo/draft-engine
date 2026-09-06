// Evaluate JS in the logged-in Chrome context (yellow-mode data layer).
// Usage: bun fetch_cdp_eval.js <nav-url> <js-expression> [out-file]
// The expression runs same-origin with Yahoo session cookies; awaits promises.
const port = 9333;
const [,, navUrl, expr, out] = process.argv;
if (!navUrl || !expr) { console.error('usage: fetch_cdp_eval.js <navUrl> <expr> [out]'); process.exit(2); }

const ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
const ws = new WebSocket(ver.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
function send(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    pending.set(msgId, { resolve, reject });
    ws.send(JSON.stringify({ id: msgId, method, params, sessionId }));
  });
}
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id).resolve(m.result); pending.delete(m.id); }
};
await new Promise(r => ws.onopen = r);

const { targetId } = await send('Target.createTarget', { url: navUrl, background: true });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
await send('Page.enable', {}, sessionId);
for (let i = 0; i < 60; i++) {
  await new Promise(r => setTimeout(r, 500));
  const { result } = await send('Runtime.evaluate',
    { expression: 'document.readyState', returnByValue: true }, sessionId);
  if (result?.value === 'complete') break;
}
await new Promise(r => setTimeout(r, 1500));

const { result, exceptionDetails } = await send('Runtime.evaluate', {
  expression: expr, awaitPromise: true, returnByValue: true,
  maxContentLength: 100_000_000,
}, sessionId);
if (exceptionDetails) {
  console.error('JS EXCEPTION:', JSON.stringify(exceptionDetails).slice(0, 400));
  process.exit(1);
}
const value = typeof result?.value === 'string' ? result.value : JSON.stringify(result?.value);
if (out) { await Bun.write(out, value); console.log(`wrote ${out} (${value.length} chars)`); }
else console.log(value.slice(0, 4000));
await send('Target.closeTarget', { targetId });
ws.close();
process.exit(0);
