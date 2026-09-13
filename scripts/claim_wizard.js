// Drive the Yahoo add/drop form with TRUSTED mouse events (CDP Input domain).
// bun claim_wizard.js <apid> <dropNameSubstring>
const port = 9333;
const [,, apid, dropName] = process.argv;
if (!apid || !dropName) { console.error('usage: claim_wizard.js <apid> <dropName>'); process.exit(2); }

const LID = JSON.parse(await Bun.file(`${process.env.HOME}/yahoo-bot/config.json`).text()).league_id;
const url = `https://football.fantasysports.yahoo.com/f1/${LID}/addplayer?apid=${apid}`;

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

const { targetId } = await send('Target.createTarget', { url, background: false });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
await send('Page.enable', {}, sessionId);
await send('Runtime.enable', {}, sessionId);
for (let i = 0; i < 60; i++) {
  await new Promise(r => setTimeout(r, 500));
  const { result } = await send('Runtime.evaluate',
    { expression: 'document.readyState', returnByValue: true }, sessionId);
  if (result?.value === 'complete') break;
}
await new Promise(r => setTimeout(r, 2000));

async function evl(expr) {
  const { result, exceptionDetails } = await send('Runtime.evaluate',
    { expression: expr, awaitPromise: true, returnByValue: true }, sessionId);
  if (exceptionDetails) return { exc: exceptionDetails.text };
  return { v: result?.value };
}
async function clickXY(x, y) {
  for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased']) {
    await send('Input.dispatchMouseEvent',
      { type, x, y, button: 'left', clickCount: type === 'mouseMoved' ? 0 : 1, buttons: type === 'mouseReleased' ? 0 : 1 },
      sessionId);
  }
}

// 1) locate Jeudy row's trigger button center
const find = (sel) => `(function(){var el=${sel};if(!el)return null;var r=el.getBoundingClientRect();return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()`;

let r1 = await evl(find(
  `[...document.querySelectorAll('form tr')].find(tr=>tr.innerText.includes(${JSON.stringify(dropName)}))?.querySelector('button.add-drop-trigger-btn')`
));
if (!r1.v) { console.log('trigger not found', JSON.stringify(r1)); process.exit(1); }
let p1 = JSON.parse(r1.v);
console.log('clicking drop trigger at', p1);
await clickXY(p1.x, p1.y);
await new Promise(r => setTimeout(r, 1000));

// 2) what did the page become? dump any new visible buttons + checked boxes
let r2 = await evl(`(function(){
  var f=[...document.querySelectorAll('form')].find(x=>/addplayer/.test(x.action));
  var checked=f?[...f.querySelectorAll('input[name=dpid]:checked')].map(c=>c.value):[];
  var btns=[...(f?f:document).querySelectorAll('button,a[class*=btn],[class*=submit]')].map(b=>({t:(b.innerText||'').trim().slice(0,25),c:(b.className||'').toString().slice(0,40)})).filter(b=>b.t);
  var body=(document.body.innerText.replace(/\\s+/g,' ')).slice(0,200);
  return JSON.stringify({checked, btns: btns.slice(0,12), body});})()`);
console.log('after trigger click:', r2.v);

// 3) find the confirm/add-player control anywhere on the page, trusted-click it
let r3 = await evl(find(
  `[...document.querySelectorAll('button,a,input[type=submit]')].find(b=>/add player|claim player|submit|confirm/i.test((b.innerText||b.value||'').trim()) && !(b.className||'').includes('add-drop-trigger'))`
));
console.log('confirm control:', r3.v);
if (r3.v && r3.v !== 'null') {
  let p3 = JSON.parse(r3.v);
  await clickXY(p3.x, p3.y);
  await new Promise(r => setTimeout(r, 1500));
  // a modal may have appeared with its own confirm
  let r4 = await evl(find(
    `[...document.querySelectorAll('[class*=modal] button,[role=dialog] button,[class*=overlay] button')].find(b=>/add|claim|confirm|submit|yes/i.test((b.innerText||'').trim()))`
  ));
  console.log('modal confirm:', r4.v);
  if (r4.v) { let p4 = JSON.parse(r4.v); await clickXY(p4.x, p4.y); }
}
await new Promise(r => setTimeout(r, 4000));

// 4) final state
let r5 = await evl(`JSON.stringify({url: location.href.slice(0,120),
  alerts: [...document.querySelectorAll('[class*=alert],[class*=toast],[class*=error],[class*=success]')].map(e=>e.innerText.trim().slice(0,120)).filter(Boolean).slice(0,4),
  seg: document.body.innerText.replace(/\\s+/g,' ').slice(0,260)})`);
console.log('FINAL:', r5.v);
// leave the tab open for eyeballing if background:false made a window; close anyway to keep profile tidy:
await send('Target.closeTarget', { targetId });
ws.close();
process.exit(0);
