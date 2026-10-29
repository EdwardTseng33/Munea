// 官網／B2B 用的新寧寧短片：無頭 Chrome 逐格算（虛擬時鐘），嘴巴吃指定的音量表。
// 用法：node face-video.js <face-only 網址> <輸出資料夾> [--w 720] [--h 1280] [--fps 30] [--levels <json>|none]
//        [--lead 400] [--tail 600] [--ms 8000(純待機用)] [--port 9431]
const { spawn } = require('node:child_process');
const fs = require('node:fs'); const path = require('node:path'); const os = require('node:os');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const argv = process.argv.slice(2);
const [URL, OUTDIR] = argv;
const opt = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const W = +opt('w', 720), H = +opt('h', 1280), FPS = +opt('fps', 30), FRAME_MS = 1000 / FPS;
const LEVELS = opt('levels', 'none') === 'none' ? null : JSON.parse(fs.readFileSync(opt('levels'), 'utf8'));
const LEAD = +opt('lead', 400), TAIL = +opt('tail', 600), IDLE_MS = +opt('ms', 8000), PORT = opt('port', '9431');
const TOTAL = LEVELS ? LEAD + LEVELS.length * 90 + TAIL : IDLE_MS;
fs.rmSync(OUTDIR, { recursive: true, force: true }); fs.mkdirSync(OUTDIR, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'facevid-'));
const chrome = spawn(CHROME, ['--headless=new', '--hide-scrollbars', '--mute-audio', '--use-angle=d3d11', '--enable-gpu',
  '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile, `--window-size=${W},${H}`, 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  let target = null;
  for (let i = 0; i < 80; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); target = l.find(t => t.type === 'page'); if (target) break; } catch (e) {} await sleep(250); }
  if (!target) throw new Error('Chrome never came up');
  const ws = new WebSocket(target.webSocketDebuggerUrl); await new Promise(r => ws.addEventListener('open', r));
  let id = 0; const pending = new Map(); const errors = [];
  ws.addEventListener('message', ev => { const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === 'Runtime.exceptionThrown') errors.push(JSON.stringify(m.params.exceptionDetails.exception && m.params.exceptionDetails.exception.description || m.params.exceptionDetails.text).slice(0, 240)); });
  const send = (method, params) => new Promise((res, rej) => { const n = ++id; pending.set(n, m => m.error ? rej(new Error(method + ': ' + JSON.stringify(m.error))) : res(m.result)); ws.send(JSON.stringify({ id: n, method, params: params || {} })); });
  const evalJs = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error('EVAL ' + JSON.stringify(r.exceptionDetails.exception && r.exceptionDetails.exception.description || r.exceptionDetails.text).slice(0, 300)); return r.result.value; };
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: URL });
  for (let i = 0; i < 80; i++) { if ((await evalJs('document.readyState==="complete"')) === true) break; await sleep(200); }
  await evalJs('window.__faceReady');
  await sleep(300);
  const t0 = await evalJs(`(function(){ var F=window.MuneaFlatFace; if (F.raf) cancelAnimationFrame(F.raf); F.running=false; clearInterval(F._pollTimer);
    F.__speak=false; F.speaking=function(){ return F.__speak; };
    var t0=Math.ceil(performance.now())+1000; F._lastT=0; F._blinkUntil=0; F._secondBlinkAt=0; F._sylUntil=0; F._mouthSince=0; F._nextBlink=t0+1400; F._open=0; F._setMouth('closed',t0); F._setEyes(false);
    window.__demo=function(vt,speak,lvl){ F.__speak=speak; if(lvl!=null){F._lvl=lvl;F._lvlAt=vt;} F._frame(vt); return F._mouth; }; return t0; })()`);
  let n = 0; const counts = { closed: 0, half: 0, open: 0 };
  const frames = Math.round(TOTAL / FRAME_MS);
  for (let i = 0; i < frames; i++) {
    const vt = t0 + i * FRAME_MS;
    let speak = false, lvl = null;
    if (LEVELS) { const k = Math.floor((vt - t0 - LEAD) / 90); if (k >= 0 && k < LEVELS.length) { speak = true; lvl = LEVELS[k]; } }
    const mouth = await evalJs(`__demo(${vt}, ${speak}, ${lvl})`); if (speak) counts[mouth]++;
    const shot = await send('Page.captureScreenshot', { format: 'jpeg', quality: 92 });
    fs.writeFileSync(path.join(OUTDIR, String(n++).padStart(5, '0') + '.jpg'), Buffer.from(shot.data, 'base64'));
  }
  const total = counts.closed + counts.half + counts.open || 1;
  const meta = { frames: n, fps: FPS, w: W, h: H, totalMs: TOTAL, leadMs: LEAD, mouthShare: Object.fromEntries(Object.entries(counts).map(([k, v]) => [k, Math.round(v / total * 100) + '%'])), errors };
  fs.writeFileSync(path.join(OUTDIR, '_meta.json'), JSON.stringify(meta, null, 2)); console.log(JSON.stringify(meta));
  ws.close(); chrome.kill(); process.exit(0);
})().catch(e => { console.error(String(e)); chrome.kill(); process.exit(1); });
