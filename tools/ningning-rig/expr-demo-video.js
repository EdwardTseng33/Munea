// 表情草稿影片（2026-11-21）：聊聊頁真畫面，無頭 Chrome 逐格算（虛擬時鐘、每格 1/30 秒），最後 ffmpeg 配原聲。
// 跟 demo-video.js 同一套做法，差別：
//   MODE=current → 只餵「每 90 毫秒音量」（App 現在的做法），臉用主線原本的程式
//   MODE=new     → 每格餵母音嘴型（expr-track.js 算好的）＋照時間軸換表情
// 用法：MODE=new node expr-demo-video.js <App 網址> <輸出資料夾> <track.json> [除錯埠]
const { spawn } = require('node:child_process');
const fs = require('node:fs'); const path = require('node:path'); const os = require('node:os');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const [URL, OUTDIR, TRACK, PORT = '9381'] = process.argv.slice(2);
const MODE = process.env.MODE || 'new';
const T = JSON.parse(fs.readFileSync(TRACK, 'utf8'));
const FPS = T.fps, FRAME_MS = 1000 / FPS;
// 她這一輪的開始與結束（秒，聲音時間）；中間短停頓仍算她在講
const TURN = [0.6, 15.45];
// 表情時間軸（秒）：對著「阿姨早安｜昨天晚上有睡好嗎｜你上次說膝蓋會痠，今天有好一點嗎｜對了，十點要吃血壓的藥喔｜時間到我再提醒你一次」
const EXPR = [[0, 'listen'], [0.55, 'smile'], [2.45, 'neutral'], [5.0, 'concern'], [9.7, 'neutral'], [13.3, 'smile']];
fs.rmSync(OUTDIR, { recursive: true, force: true });
fs.mkdirSync(OUTDIR, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'exprvid-'));
const chrome = spawn(CHROME, ['--headless=new', '--hide-scrollbars', '--mute-audio', '--use-angle=d3d11', '--enable-gpu',
  '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile, '--window-size=375,812', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  let target = null;
  for (let i = 0; i < 80; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); target = l.find(t => t.type === 'page'); if (target) break; } catch (e) {} await sleep(250); }
  if (!target) throw new Error('Chrome never came up');
  const ws = new WebSocket(target.webSocketDebuggerUrl); await new Promise(r => ws.addEventListener('open', r));
  let id = 0; const pending = new Map(); const errors = [];
  ws.addEventListener('message', ev => { const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === 'Runtime.exceptionThrown') errors.push('EXC ' + JSON.stringify(m.params.exceptionDetails.exception && m.params.exceptionDetails.exception.description || m.params.exceptionDetails.text).slice(0, 240));
  });
  const send = (method, params) => new Promise((res, rej) => { const n = ++id; pending.set(n, m => m.error ? rej(new Error(method + ': ' + JSON.stringify(m.error))) : res(m.result)); ws.send(JSON.stringify({ id: n, method, params: params || {} })); });
  const evalJs = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error('EVAL ' + JSON.stringify(r.exceptionDetails.exception && r.exceptionDetails.exception.description || r.exceptionDetails.text).slice(0, 300)); return r.result.value; };
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setTimezoneOverride', { timezoneId: 'Asia/Taipei' });
  await send('Emulation.setDeviceMetricsOverride', { width: 375, height: 812, deviceScaleFactor: 2, mobile: true });
  await send('Page.navigate', { url: URL });
  for (let i = 0; i < 80; i++) { const ok = await evalJs('document.readyState==="complete"'); if (ok === true) break; await sleep(250); }
  for (let i = 0; i < 60; i++) { const gone = await evalJs(`(function(){ var o=document.getElementById('bootSplash'); if(!o||o.hidden) return true; var cs=getComputedStyle(o); return cs.display==='none'||cs.visibility==='hidden'||+cs.opacity===0; })()`); if (gone === true) break; await sleep(250); }
  await sleep(1200);
  await evalJs(`(function(){ var o=document.getElementById('onboarding'); if(o){o.hidden=true;o.style.display='none';} return 1; })()`);

  console.log('chat', await evalJs(`(function(){
    var el = Array.prototype.filter.call(document.querySelectorAll('button,[role=button],a'), function(e){ return e.offsetParent && (e.innerText||'').replace(/\\s+/g,'').indexOf('開始聊聊')>=0; })
      .sort(function(a,b){ return a.innerText.length-b.innerText.length; })[0];
    if (el) el.click();
    return new Promise(function(r){ setTimeout(function(){
      var F = window.MuneaFlatFace; if (F.raf) cancelAnimationFrame(F.raf); F.running = false; clearInterval(F._pollTimer);
      F.__speak = false; F.speaking = function(){ return F.__speak; };
      var t0 = Math.ceil(performance.now()) + 1000;
      F._lastT = 0; F._blinkUntil = 0; F._secondBlinkAt = 0; F._sylUntil = 0; F._mouthSince = 0; F._nextBlink = t0 + 1400;
      F.__t0 = t0;
      window.__demo = function(vt, speak, lvl, vis, expr, timerSec){
        F.__speak = speak;
        if (lvl != null) { F._lvl = lvl; F._lvlAt = vt; }
        if (vis && F.setViseme) F.setViseme(vis.open, vis.shape, vt);
        if (expr && F.setExpression) F.setExpression(expr);
        F._frame(vt);
        var fn = document.querySelector('#chat .face-name');
        if (fn) { fn.classList.toggle('off', false); var st = fn.querySelector('.fn-status');
          if (st && st.getAttribute('data-i18n') !== 'voice.call.online') { st.setAttribute('data-i18n', 'voice.call.online'); st.textContent = '在線'; } }
        var b = document.getElementById('callToggle'); if (b) { b.classList.toggle('start', false); b.classList.toggle('end', true); }
        var lbl = document.getElementById('callToggleLabel'); if (lbl) lbl.textContent = '結束通話';
        var pts = document.querySelector('.hud-pill.pts'); if (pts) pts.style.display = 'none';
        var tm = document.getElementById('callTimer'); if (tm) tm.textContent = '00:' + String(timerSec).padStart(2,'0');
        return F._mouth + '|' + (F._eyeShown || (F._eyesClosed ? 'closed' : 'none')) + '|' + (F._browsOn ? 'concern' : '-');
      };
      r(Object.keys(F.img).join(',') + ' has=' + JSON.stringify(F._has || {}));
    }, 1800); });
  })()`));

  const t0 = await evalJs('MuneaFlatFace.__t0');
  const counts = {}; const log = [];
  let n = 0;
  for (let i = 0; i < T.frames.length; i++) {
    const t = i / FPS, vt = t0 + i * FRAME_MS;
    const speak = t >= TURN[0] && t <= TURN[1];
    const lvl = T.levels[Math.min(Math.floor(t / 0.09), T.levels.length - 1)];
    let expr = null, vis = null;
    if (MODE === 'new') {
      for (const [at, e] of EXPR) if (t >= at) expr = e;
      vis = T.frames[i];
    }
    const st = await evalJs(`__demo(${vt}, ${speak}, ${speak ? lvl : 'null'}, ${JSON.stringify(vis)}, ${JSON.stringify(expr)}, ${3 + Math.floor(t)})`);
    counts[st] = (counts[st] || 0) + 1; log.push(st);
    const shot = await send('Page.captureScreenshot', { format: 'jpeg', quality: 92 });
    fs.writeFileSync(path.join(OUTDIR, String(n++).padStart(5, '0') + '.jpg'), Buffer.from(shot.data, 'base64'));
    if (i % 100 === 0) console.log('frame', i, '/', T.frames.length, st);
  }
  fs.writeFileSync(path.join(OUTDIR, '_meta.json'), JSON.stringify({ mode: MODE, frames: n, fps: FPS, counts, errors, log }, null, 1));
  console.log(JSON.stringify({ mode: MODE, frames: n, errors }));
  ws.close(); chrome.kill(); process.exit(0);
})().catch(e => { console.error(String(e)); chrome.kill(); process.exit(1); });
