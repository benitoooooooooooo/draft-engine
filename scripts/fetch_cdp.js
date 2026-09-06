// CDP page fetcher for the persistent Yahoo Chrome (runs via bun on the mini).
// Usage: bun fetch_cdp.js <url> <out-file> [waitMs]
// Connects to the running headful/headless chrome on :9333, opens url in a
// background tab, waits for load + settle, writes document.outerHTML.
const port = 9333;
const [,, url, out, waitMs] = process.argv;
if (!url || !out) { console.error('usage: fetch_cdp.js <url> <out.html> [settleMs]'); process.exit(2); }

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

const { targetId } = await send('Target.createTarget', { url: 'about:blank', background: true });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
await send('Page.enable', {}, sessionId);
await send('Page.navigate', { url }, sessionId);

// wait for load event equivalent: poll readyState
for (let i = 0; i < 60; i++) {
  await new Promise(r => setTimeout(r, 500));
  const { result } = await send('Runtime.evaluate',
    { expression: 'document.readyState', returnByValue: true }, sessionId);
  if (result?.value === 'complete') break;
}
await new Promise(r => setTimeout(r, parseInt(waitMs || '2500', 10)));

const { result } = await send('Runtime.evaluate',
  { expression: 'document.documentElement.outerHTML', returnByValue: true, maxContentLength: 50_000_000 }, sessionId);
if (!result?.value) { console.error('empty html'); process.exit(1); }
await Bun.write(out, result.value);
await send('Target.closeTarget', { targetId });
console.log(`wrote ${out} (${result.value.length} bytes)`);
ws.close();
process.exit(0);
