// 「通話中」即時嘴型＋表情的本機證明影片（2026-11-21）。跟 expr-demo-video.js 不同：這支不逐格算，
// 是真的讓聲音走 App 的本機播放路線（LiveVoice._scheduleLocalPlayback），臉由 App 自己的動畫迴圈即時畫。
// 送資料的節奏照測試機量到的樣子：聲音和字幕都比她講話快約 5 倍送到、送完就來「這輪講完」，App 自己排隊慢慢播。
//   MODE=old（第二輪草稿）：表情事件一到就換（FaceViseme.expression）、「講完」後 1.2 秒換傾聽（turnDone）
//   MODE=new（第三輪）：字幕＋表情事件帶「第幾個字」＋手勢（FaceViseme.caption／serverEvent／turnComplete），
//     事件內容照 engine/face_expression.py 的規則算好
// 同時錄 CPU 剖析（Profiler）與 App 自己的計時，量效能。
// 用法：MODE=new node expr-live-call-video.js <App 網址> <輸出資料夾> <聲音.wav>
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs'); const path = require('node:path'); const os = require('node:os');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const [URL, OUTDIR, WAV, PORT = '9391'] = process.argv.slice(2);
// 三輪（秒，原聲時間）＋語音主機規則算出的表情與送出時間（從該輪開頭算）；輪與輪之間留 1.4 秒＝換對方講
// evt＝engine/face_expression.py 對這句話會送的事件（test 裡驗過同樣的規則）
const TURNS = [
  { from: 0.62, to: 4.62, text: '阿姨早安，昨天晚上有睡好嗎？', evt: { expr: 'smile', pos: 2, gesture: 'wave', gpos: 0 } },
  { from: 5.25, to: 9.45, text: '你上次說膝蓋會痠，今天有好一點嗎？', evt: { expr: 'concern', pos: 7, gesture: 'chest', gpos: 7 } },
  { from: 10.2, to: 15.4, text: '對了，十點要吃血壓的藥喔，時間到我再提醒你一次。', evt: { expr: 'neutral', pos: 24 } },
];
const MODE = process.env.MODE || 'new';
const SPEEDUP = 5;   // 送資料比講話快幾倍（測試機量到約 5～6 倍）
const GAP = 1.4, LEAD_IN = 1.2;

function readWav(p) {
  const b = fs.readFileSync(p); let off = 12, fmt = null, data = null;
  while (off < b.length - 8) { const id = b.toString('ascii', off, off + 4), size = b.readUInt32LE(off + 4);
    if (id === 'fmt ') fmt = { sr: b.readUInt32LE(off + 12) }; if (id === 'data') { data = b.subarray(off + 8, off + 8 + size); break; } off += 8 + size + (size & 1); }
  return { sr: fmt.sr, pcm: data };
}
const { sr, pcm } = readWav(WAV);
fs.rmSync(OUTDIR, { recursive: true, force: true }); fs.mkdirSync(path.join(OUTDIR, 'frames'), { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'exprlive-'));
const chrome = spawn(CHROME, ['--headless=new', '--hide-scrollbars', '--mute-audio', '--autoplay-policy=no-user-gesture-required',
  '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile, '--window-size=375,812', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  let target = null;
  for (let i = 0; i < 80; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); target = l.find(t => t.type === 'page'); if (target) break; } catch (e) {} await sleep(250); }
  if (!target) throw new Error('Chrome never came up');
  console.log('stage chrome up');
  const ws = new WebSocket(target.webSocketDebuggerUrl); await new Promise(r => ws.addEventListener('open', r));
  let id = 0; const pending = new Map(); const errors = []; const frames = []; const netFails = [];
  ws.addEventListener('message', ev => { const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === 'Runtime.exceptionThrown') errors.push('EXC ' + JSON.stringify(m.params.exceptionDetails.exception && m.params.exceptionDetails.exception.description || m.params.exceptionDetails.text).slice(0, 240));
    if (m.method === 'Network.responseReceived' && m.params.response.status >= 400) netFails.push(m.params.response.status + ' ' + m.params.response.url);
    if (m.method === 'Page.screencastFrame') {
      const n = frames.length; const f = path.join(OUTDIR, 'frames', String(n).padStart(5, '0') + '.jpg');
      fs.writeFileSync(f, Buffer.from(m.params.data, 'base64')); frames.push({ f, ts: m.params.metadata.timestamp });
      send('Page.screencastFrameAck', { sessionId: m.params.sessionId }).catch(() => {});
    }
  });
  const send = (method, params) => new Promise((res, rej) => { const n = ++id; pending.set(n, m => m.error ? rej(new Error(method + ': ' + JSON.stringify(m.error))) : res(m.result)); ws.send(JSON.stringify({ id: n, method, params: params || {} })); });
  const evalJs = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error('EVAL ' + JSON.stringify(r.exceptionDetails.exception && r.exceptionDetails.exception.description || r.exceptionDetails.text).slice(0, 300)); return r.result.value; };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 375, height: 812, deviceScaleFactor: 2, mobile: true });
  await send('Page.navigate', { url: URL });
  console.log('stage navigated');
  await sleep(1500);
  await evalJs(`localStorage.setItem('munea.faceExpressive','1'); 1`);
  await send('Page.navigate', { url: URL });
  for (let i = 0; i < 80; i++) { const ok = await evalJs('document.readyState==="complete"'); if (ok === true) break; await sleep(250); }
  for (let i = 0; i < 60; i++) { const gone = await evalJs(`(function(){ var o=document.getElementById('bootSplash'); if(!o||o.hidden) return true; var cs=getComputedStyle(o); return cs.display==='none'||cs.visibility==='hidden'||+cs.opacity===0; })()`); if (gone === true) break; await sleep(250); }
  console.log('stage booted');
  console.log('probe', await evalJs(`typeof window.MuneaFaceViseme + ' ' + typeof MuneaFlatFace + ' ' + localStorage.getItem('munea.faceExpressive') + ' ' + (document.querySelector('.view.active')||{}).id`));
  await sleep(1000);
  console.log('chat', await evalJs(`(function(){
    var o=document.getElementById('onboarding'); if(o){o.hidden=true;o.style.display='none';}
    var el = Array.prototype.filter.call(document.querySelectorAll('button,[role=button],a'), function(e){ return e.offsetParent && (e.innerText||'').replace(/\\s+/g,'').indexOf('開始聊聊')>=0; })
      .sort(function(a,b){ return a.innerText.length-b.innerText.length; })[0];
    if (el) el.click();
    return new Promise(function(r){ setTimeout(function(){ var F=window.MuneaFlatFace; r('expressive=' + F.expressive + ' has=' + JSON.stringify(F._has) + ' viseme.on=' + window.MuneaFaceViseme.on); }, 2000); });
  })()`));

  // 聲音放進頁面（只放這三輪要用的片段）
  const segs = TURNS.map(t => pcm.subarray(Math.round(t.from * sr) * 2, Math.round(t.to * sr) * 2).toString('base64'));
  await evalJs(`window.__segs = ${JSON.stringify(segs)}; window.__turns = ${JSON.stringify(TURNS)}; 1`);

  await send('Profiler.enable'); await send('Profiler.setSamplingInterval', { interval: 200 }); await send('Profiler.start');
  await send('Page.startScreencast', { format: 'jpeg', quality: 88, everyNthFrame: 1 });
  const result = await evalJs(`(async function(){
    var F = window.MuneaFlatFace, LV = window.MuneaLiveVoice, FV = window.MuneaFaceViseme, GAP=${GAP}, LEAD=${LEAD_IN}, MODE=${JSON.stringify(MODE)}, SPEED=${SPEEDUP};
    var ctx = new AudioContext({ sampleRate: ${sr} }); LV.playCtx = ctx; await ctx.resume();
    F.speaking = function(){ return !!(LV._srcs && LV._srcs.length); };
    var fn = document.querySelector('#chat .face-name'); if (fn) { fn.classList.remove('off'); var st = fn.querySelector('.fn-status'); if (st) st.textContent = '在線'; }
    var b = document.getElementById('callToggle'); if (b) { b.classList.remove('start'); b.classList.add('end'); }
    var lbl = document.getElementById('callToggleLabel'); if (lbl) lbl.textContent = '結束通話';
    var pts = document.querySelector('.hud-pill.pts'); if (pts) pts.style.display = 'none';
    var t0 = performance.now(), tm = document.getElementById('callTimer');
    var clock = setInterval(function(){ if (tm) tm.textContent = '00:' + String(5 + Math.floor((performance.now()-t0)/1000)).padStart(2,'0'); }, 200);
    var states = [], audioStarts = [];
    var probe = setInterval(function(){ states.push({ t: +((performance.now()-t0)/1000).toFixed(2), mouth: F._mouth, eyes: F._eyeShown, brows: F._browsOn, expr: F._expr, gesture: F._gLayer || null, speaking: F.speaking() }); }, 33);
    F.setExpression('listen');
    await new Promise(function(r){ setTimeout(r, LEAD*1000); });
    for (var i = 0; i < __turns.length; i++) {
      var T = __turns[i], raw = atob(__segs[i]), n = raw.length / 2, f = new Float32Array(n);
      for (var k = 0; k < n; k++) { var v = raw.charCodeAt(2*k) | (raw.charCodeAt(2*k+1) << 8); if (v >= 32768) v -= 65536; f[k] = v / 32768; }
      LV._turnHasScheduledAudio = false; LV._playbackTurn = i + 2;
      var dur = n / ${sr}, sendMs = dur / SPEED * 1000;
      if (MODE === 'new') FV.caption(T.text);                      // 字幕跟第一塊聲音一起到
      var startAt = null, wallStart = 0;
      // 聲音一塊塊（每塊 0.1 秒）照「比講話快 SPEED 倍」的節奏送到
      for (var c = 0, j = 0; c < n; c += 2400, j++) {
        (function(c, j){ setTimeout(function(){
          LV._scheduleLocalPlayback(f.subarray(c, Math.min(n, c + 2400)));
          if (j === 0) { startAt = LV.playHead - Math.min(n, 2400) / ${sr}; wallStart = Date.now() + (startAt - ctx.currentTime) * 1000; }
        }, j * 100 / SPEED); })(c, j);
      }
      // 表情事件：觸發字的字幕到的時候（照字的位置估）
      var evAt = Math.min(sendMs, (T.evt.pos / Math.max(1, T.text.length)) * sendMs);
      setTimeout((function(T){ return function(){ if (MODE === 'new') FV.serverEvent(Object.assign({ type: 'face_expression' }, T.evt)); else FV.expression(T.evt.expr); }; })(T), evAt);
      // 送完＝主機的「這輪講完」
      setTimeout(function(){ if (MODE === 'new') FV.turnComplete(); else FV.turnDone(); }, sendMs + 150);
      await new Promise(function(r){ setTimeout(r, 200); });
      audioStarts.push({ turn: i, wall: wallStart / 1000, dur: dur });
      await new Promise(function(r){ setTimeout(r, Math.max(0, wallStart - Date.now()) + dur * 1000 + GAP * 1000); });
    }
    clearInterval(probe); clearInterval(clock);
    var stats = FV.stats ? FV.stats() : null;
    return { states: states, audioStarts: audioStarts, stats: stats, ctxRate: ctx.sampleRate, has: F._has };
  })()`);
  await send('Page.stopScreencast');
  const prof = (await send('Profiler.stop')).profile;
  await sleep(300);

  // CPU 剖析：依檔案加總「自己花的時間」
  const byFile = {}; const total = { ms: 0 };
  const dtById = {}; const idx = new Map(prof.nodes.map(n => [n.id, n]));
  for (let i = 0; i < prof.samples.length; i++) { const d = (prof.timeDeltas[i] || 0) / 1000; dtById[prof.samples[i]] = (dtById[prof.samples[i]] || 0) + d; total.ms += d; }
  for (const [nid, ms] of Object.entries(dtById)) {
    const n = idx.get(+nid); const url = (n.callFrame.url || '').split('/').pop().split('?')[0] || '(' + n.callFrame.functionName + ')';
    byFile[url] = (byFile[url] || 0) + ms;
  }
  const top = Object.entries(byFile).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([k, v]) => [k, +v.toFixed(1)]);

  // 影片：依截圖時間戳記組回去，聲音照真的開始播的牆上時間對齊
  const t0 = frames[0].ts, tEnd = frames[frames.length - 1].ts + 0.05;
  const list = frames.map((fr, i) => `file '${fr.f.replace(/\\/g, '/')}'\nduration ${((i + 1 < frames.length ? frames[i + 1].ts : tEnd) - fr.ts).toFixed(4)}`).join('\n') + `\nfile '${frames[frames.length - 1].f.replace(/\\/g, '/')}'\n`;
  fs.writeFileSync(path.join(OUTDIR, 'frames.txt'), list);
  const totalS = tEnd - t0, outPcm = Buffer.alloc(Math.ceil(totalS * sr) * 2);
  result.audioStarts.forEach((a, i) => { const seg = Buffer.from(segs[i], 'base64'); const o = Math.max(0, Math.round((a.wall - t0) * sr)) * 2; seg.copy(outPcm, o, 0, Math.min(seg.length, outPcm.length - o)); });
  const hdr = Buffer.alloc(44); hdr.write('RIFF', 0); hdr.writeUInt32LE(36 + outPcm.length, 4); hdr.write('WAVEfmt ', 8); hdr.writeUInt32LE(16, 16); hdr.writeUInt16LE(1, 20); hdr.writeUInt16LE(1, 22); hdr.writeUInt32LE(sr, 24); hdr.writeUInt32LE(sr * 2, 28); hdr.writeUInt16LE(2, 32); hdr.writeUInt16LE(16, 34); hdr.write('data', 36); hdr.writeUInt32LE(outPcm.length, 40);
  fs.writeFileSync(path.join(OUTDIR, 'audio.wav'), Buffer.concat([hdr, outPcm]));
  const meta = { frames: frames.length, seconds: +totalS.toFixed(2), captureFps: +(frames.length / totalS).toFixed(1), analyzer: result.stats,
    cpuTopSelfMs: top, cpuTotalMs: +total.ms.toFixed(0), errors, netFails, has: result.has, audioStarts: result.audioStarts.map(a => ({ turn: a.turn, at: +(a.wall - t0).toFixed(2), dur: +a.dur.toFixed(2) })) };
  fs.writeFileSync(path.join(OUTDIR, '_meta.json'), JSON.stringify(meta, null, 1));
  fs.writeFileSync(path.join(OUTDIR, '_states.json'), JSON.stringify(result.states));
  console.log(JSON.stringify(meta, null, 1));
  ws.close(); chrome.kill(); process.exit(0);
})().catch(e => { console.error(String(e)); chrome.kill(); process.exit(1); });
