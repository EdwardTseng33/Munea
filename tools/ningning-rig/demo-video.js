// 新寧寧 demo 影片：無頭 Chrome 逐格算畫面（虛擬時鐘、每格 1/30 秒），嘴巴吃寧寧真聲音的音量表，
// 最後 ffmpeg 配原聲。用法：node demo-video.js <網址> <輸出資料夾> [除錯埠]
const { spawn } = require('node:child_process');
const fs = require('node:fs'); const path = require('node:path'); const os = require('node:os');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const [URL, OUTDIR, PORT = '9371'] = process.argv.slice(2);
const FPS = 30, FRAME_MS = 1000 / FPS;
const LEVELS = JSON.parse(fs.readFileSync(path.join(__dirname, 'voice-levels.json'), 'utf8')); // 每 90 毫秒一筆
const SPEECH_MS = 22790;
// 分鏡：首頁 1.5 秒 → 聊聊頁待機 2.5 秒（呼吸、眨眼）→ 接通 0.5 秒 → 講話整段 → 講完聽你說 2 秒
const HOME_MS = 1500, IDLE_MS = 2500, CONNECT_MS = 500, TAIL_MS = 2000;
fs.rmSync(OUTDIR, { recursive: true, force: true });
fs.mkdirSync(OUTDIR, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'demovid-'));
const chrome = spawn(CHROME, ['--headless=new', '--hide-scrollbars', '--mute-audio',
  '--use-angle=d3d11', '--enable-gpu',
  '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile, '--window-size=375,812', 'about:blank'],
  { stdio: 'ignore' });
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
  // 等開機畫面自己淡出（不硬藏，免得錄到一半的淡出）
  for (let i = 0; i < 60; i++) { const gone = await evalJs(`(function(){ var o=document.getElementById('bootSplash'); if(!o||o.hidden) return true; var cs=getComputedStyle(o); return cs.display==='none'||cs.visibility==='hidden'||+cs.opacity===0; })()`); if (gone === true) break; await sleep(250); }
  await sleep(1200);

  let n = 0;
  const shoot = async () => {
    const shot = await send('Page.captureScreenshot', { format: 'jpeg', quality: 92 });
    fs.writeFileSync(path.join(OUTDIR, String(n++).padStart(5, '0') + '.jpg'), Buffer.from(shot.data, 'base64'));
  };
  const dup = (count) => { const last = path.join(OUTDIR, String(n - 1).padStart(5, '0') + '.jpg');
    for (let i = 0; i < count; i++) fs.copyFileSync(last, path.join(OUTDIR, String(n++).padStart(5, '0') + '.jpg')); };

  // 首頁
  console.log('home', await evalJs(`(function(){ var o=document.getElementById('onboarding'); if(o){o.hidden=true;o.style.display='none';} return document.querySelector('.view.active')?document.querySelector('.view.active').id:'?'; })()`));
  const SKIN = process.env.SKIN || '';
  if (!SKIN && !process.env.NOHOME) { await shoot(); dup(Math.round(HOME_MS / FRAME_MS) - 1); }

  // 進聊聊頁，停掉即時動畫迴圈，改成由這支腳本逐格餵時間
  console.log('chat t0', await evalJs(`(function(){
    var el = Array.prototype.filter.call(document.querySelectorAll('button,[role=button],a'), function(e){ return e.offsetParent && (e.innerText||'').replace(/\\s+/g,'').indexOf('開始聊聊')>=0; })
      .sort(function(a,b){ return a.innerText.length-b.innerText.length; })[0];
    if (el) el.click();
    return new Promise(function(r){ setTimeout(function(){
      var F = window.MuneaFlatFace; if (F.raf) cancelAnimationFrame(F.raf); F.running = false; clearInterval(F._pollTimer);
      F.__speak = false; F.speaking = function(){ return F.__speak; };
      var t0 = Math.ceil(performance.now()) + 1000;
      F._lastT = 0; F._blinkUntil = 0; F._secondBlinkAt = 0; F._sylUntil = 0; F._mouthSince = 0; F._nextBlink = t0 + 900;
      F.__t0 = t0;
      window.__demo = function(vt, speak, lvl, connected, timerSec){
        F.__speak = speak;
        if (lvl != null) { F._lvl = lvl; F._lvlAt = vt; }
        F._frame(vt);
        var fn = document.querySelector('#chat .face-name');
        if (fn) { fn.classList.toggle('off', !connected); var st = fn.querySelector('.fn-status');
          var key = connected ? 'voice.call.online' : 'voice.call.offline';
          if (st.getAttribute('data-i18n') !== key) { st.setAttribute('data-i18n', key); st.textContent = connected ? '在線' : '未在線'; } }
        var b = document.getElementById('callToggle'); b.classList.toggle('start', !connected); b.classList.toggle('end', connected);
        var lbl = document.getElementById('callToggleLabel'); lbl.textContent = connected ? '結束通話' : '開始通話';
        var pts = document.querySelector('.hud-pill.pts'); if (pts && connected) pts.style.display = 'none';
        var tm = document.getElementById('callTimer'); if (tm) tm.textContent = '00:' + String(timerSec).padStart(2,'0');
        return F._mouth;
      };
      r(F.__t0);
    }, 1800); });
  })()`));

  if (SKIN) console.log('skin', await evalJs(`(function(){
    var F=window.MuneaFlatFace, bg=${JSON.stringify(process.env.SKIN_BG || '#C5E4DC')};
    var map={base:'base',half:'half',open:'open',eyes:'eyes'};
    F.root.style.background=bg; F.body.style.transform='none';
    return Promise.all(Object.keys(map).map(function(k){ return new Promise(function(res){
      var u='_demo/${process.env.SKIN}-'+map[k]+'.png?v='+Date.now(); var im=new Image(); im.onload=im.onerror=function(){ F.layer[k].style.backgroundImage='url("'+u+'")'; res(im.naturalWidth); }; im.src=u; }); }))
      .then(function(w){ return new Promise(function(r){ setTimeout(function(){ r(w.join(',')); }, 600); }); });
  })()`));
  const counts = { closed: 0, half: 0, open: 0 };
  const chatT0 = await evalJs('MuneaFlatFace.__t0');
  let vt = chatT0;
  const idleFrames = Math.round(IDLE_MS / FRAME_MS);
  for (let i = 0; i < idleFrames; i++, vt += FRAME_MS) { await evalJs(`__demo(${vt}, false, null, false, 0)`); await shoot(); }
  const callStart = vt;
  const connFrames = Math.round(CONNECT_MS / FRAME_MS);
  for (let i = 0; i < connFrames; i++, vt += FRAME_MS) { await evalJs(`__demo(${vt}, false, null, true, 0)`); await shoot(); }
  const speechStartFrame = n;
  const speechFrames = Math.round(SPEECH_MS / FRAME_MS);
  const speechStart = vt;
  for (let i = 0; i < speechFrames; i++, vt += FRAME_MS) {
    const idx = Math.floor((vt - speechStart) / 90);
    const lvl = LEVELS[Math.min(idx, LEVELS.length - 1)];
    const mouth = await evalJs(`__demo(${vt}, true, ${lvl}, true, ${Math.floor((vt - callStart) / 1000)})`);
    counts[mouth]++;
    await shoot();
    if (i % 150 === 0) console.log('speech frame', i, '/', speechFrames);
  }
  const tailFrames = Math.round(TAIL_MS / FRAME_MS);
  for (let i = 0; i < tailFrames; i++, vt += FRAME_MS) { await evalJs(`__demo(${vt}, false, null, true, ${Math.floor((vt - callStart) / 1000)})`); await shoot(); }

  const total = counts.closed + counts.half + counts.open;
  const meta = { frames: n, fps: FPS, speechStartMs: Math.round(speechStartFrame * FRAME_MS),
    mouthShare: Object.fromEntries(Object.entries(counts).map(([k, v]) => [k, Math.round(v / total * 100) + '%'])), errors };
  fs.writeFileSync(path.join(OUTDIR, '_meta.json'), JSON.stringify(meta, null, 2));
  console.log(JSON.stringify(meta));
  ws.close(); chrome.kill(); process.exit(0);
})().catch(e => { console.error(String(e)); chrome.kill(); process.exit(1); });
