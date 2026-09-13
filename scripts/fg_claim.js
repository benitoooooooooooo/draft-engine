// Foreground-tab trusted-click claim: opens add/drop wizard visibly on the
// mini Chrome, drives stage1->stage2->create-claim with real mouse events.
// usage: bun fg_claim.js <apid> <dropNameSubstring>
const port = 9333;
const cfg = JSON.parse(await Bun.file(`${process.env.HOME}/yahoo-bot/config.json`).text());
const LID = cfg.league_id;
const [,, apid, dropName] = process.argv;
if (!apid || !dropName) { console.error("usage: fg_claim.js <apid> <drop>"); process.exit(2); }

const ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
const ws = new WebSocket(ver.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (method, params = {}, sessionId) => new Promise((resolve) => {
  const msgId = ++id; pending.set(msgId, resolve);
  ws.send(JSON.stringify({ id: msgId, method, params, sessionId }));
});
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
await new Promise(r => ws.onopen = r);

const { targetId } = await send("Target.createTarget", { url: `https://football.fantasysports.yahoo.com/f1/${LID}/addplayer?apid=${apid}` });
const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
await send("Target.activateTarget", { targetId });
await send("Page.enable", {}, sessionId);
await send("Runtime.enable", {}, sessionId);

async function evl(expr) {
  const { result, exceptionDetails } = await send("Runtime.evaluate",
    { expression: expr, awaitPromise: true, returnByValue: true }, sessionId);
  if (exceptionDetails) return { exc: exceptionDetails.text };
  return { v: result?.value };
}
async function waitLoad(extra = 2000) {
  for (let i = 0; i < 40; i++) {
    await new Promise(r => setTimeout(r, 500));
    const { result } = await send("Runtime.evaluate", { expression: "document.readyState", returnByValue: true }, sessionId);
    if (result?.value === "complete") break;
  }
  await new Promise(r => setTimeout(r, extra));
}
async function clickXY(x, y) {
  for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
    await send("Input.dispatchMouseEvent",
      { type, x, y, button: "left", clickCount: type === "mouseMoved" ? 0 : 1, buttons: type === "mouseReleased" ? 0 : 1 }, sessionId);
  }
}
async function clickSel(selExpr, waitAfter = 1500) {
  const pos = await evl(
    "(function(){var el=" + selExpr + ";" +
    "if(!el)return null;el.scrollIntoView({block:'center'});" +
    "return new Promise(function(res){setTimeout(function(){var r=el.getBoundingClientRect();" +
    "res(JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,txt:(el.innerText||el.value||'').trim().slice(0,50)}));},350);});})()");
  if (!pos.v || pos.v === "null") { console.log("MISS:", selExpr.slice(0, 70), pos.exc || ""); return false; }
  const p = JSON.parse(pos.v);
  console.log("CLICK:", JSON.stringify(p.txt), "at", Math.round(p.x) + "," + Math.round(p.y));
  await clickXY(p.x, p.y);
  await new Promise(r => setTimeout(r, waitAfter));
  return true;
}

await waitLoad();
console.log("PAGE:", (await evl("JSON.stringify({title: document.title.slice(0,50), url: location.href.slice(0,110)})")).v);

// stage 1 -> toggle drop for Jeudy
await clickSel(`[...document.querySelectorAll('form tr')].find(tr=>tr.innerText.includes(${JSON.stringify(dropName)}))?.querySelector('button.add-drop-trigger-btn')`, 1800);
// the picker's CONFIRM control: Yahoo renders an inline href carrying stage=2
// (never click .roster-save-btn — that's Cancel in this picker!)
let done = await clickSel(`document.querySelector('a[href*="stage=2"]')`, 4000);
if (done) await waitLoad(1500);
let st = await evl("(function(){var b=[...document.querySelectorAll('form button,form input[type=submit]')].map(x=>(x.innerText||x.value||'').trim()).filter(Boolean);"
  + "return JSON.stringify({url: location.href.slice(0,120), btns: b.slice(0,8)});})()");
console.log("STATE:", st.v);

// stage 2 -> create claim
await clickSel(`[...document.querySelectorAll('form button,form input[type=submit]')].find(b=>/create claim|submit|confirm|add romeo/i.test((b.innerText||b.value||'')))`, 5000);
st = await evl("(function(){return JSON.stringify({url: location.href.slice(0,130),"
  + "alerts: [...document.querySelectorAll('[class*=alert],[class*=toast],[class*=Toast]')].map(e=>e.innerText.trim().slice(0,150)).filter(Boolean).slice(0,3),"
  + "seg: document.body.innerText.replace(/\\s+/g,' ').slice(0,240)});})()");
console.log("FINAL:", st.v);
await send("Target.closeTarget", { targetId });
ws.close();
process.exit(0);
