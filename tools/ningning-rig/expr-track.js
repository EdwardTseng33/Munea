// 表情草稿影片用：把一段寧寧的聲音（24kHz 單聲道 16-bit WAV）算成「每一格畫面」的嘴巴指令。
// 嘴形用 9/29 試驗室的通用嘴型驅動器（tools/ningning-rig/lipsync-driver.js，從試驗室分支 lab/ning-lipsync-20260929 原樣搬來：音量→張口、共振峰→ㄚㄝㄧㄛㄨ），
// 另外照 App 現在的做法算「每 90 毫秒的音量」給舊版臉用，兩邊吃同一段聲音才比得公平。
// 用法：node expr-track.js <聲音.wav> <輸出.json> [lipsync-driver.js 路徑]
const fs = require('node:fs'); const path = require('node:path');
const [WAV, OUT, DRIVER = path.join(__dirname, 'lipsync-driver.js')] = process.argv.slice(2);
const FPS = 30, LEAD = 0.05;   // 嘴巴比聲音早 50 毫秒（9/29 量出來的寧寧轉接頭設定）

function readWav(p) {
  const b = fs.readFileSync(p);
  let off = 12, fmt = null, data = null;
  while (off < b.length - 8) {
    const id = b.toString('ascii', off, off + 4), size = b.readUInt32LE(off + 4);
    if (id === 'fmt ') fmt = { ch: b.readUInt16LE(off + 10), sr: b.readUInt32LE(off + 12), bits: b.readUInt16LE(off + 22) };
    if (id === 'data') { data = b.subarray(off + 8, off + 8 + size); break; }
    off += 8 + size + (size & 1);
  }
  if (!fmt || !data || fmt.bits !== 16) throw new Error('只吃 16-bit PCM WAV');
  const n = Math.floor(data.length / 2 / fmt.ch), x = new Float32Array(n);
  for (let i = 0; i < n; i++) x[i] = data.readInt16LE(i * 2 * fmt.ch) / 32768;
  return { sampleRate: fmt.sr, x };
}

global.window = global;
eval(fs.readFileSync(DRIVER, 'utf8'));
const { sampleRate, x } = readWav(WAV);
const buffer = { sampleRate, length: x.length, duration: x.length / sampleRate, numberOfChannels: 1, getChannelData: () => x };
const track = window.LipSync.analyze(buffer);
const sample = window.LipSync.makeSampler(track);
const frames = [];
const nFrames = Math.ceil(track.dur * FPS);
for (let i = 0; i < nFrames; i++) {
  const s = sample(Math.min(track.dur - 0.011, i / FPS + LEAD));
  frames.push(s ? { open: +s.open.toFixed(3), shape: s.shape } : { open: 0, shape: 'sil' });
}
// App 版：每 90 毫秒一筆的音量（均方根），跟 voice-levels.json 同一種量法
const hop = Math.round(0.09 * sampleRate), levels = [];
for (let i = 0; i + hop <= x.length; i += hop) {
  let e = 0; for (let k = i; k < i + hop; k++) e += x[k] * x[k];
  levels.push(+Math.sqrt(e / hop).toFixed(4));
}
const shapes = {}; frames.forEach(f => { shapes[f.shape] = (shapes[f.shape] || 0) + 1; });
fs.writeFileSync(OUT, JSON.stringify({ fps: FPS, dur: track.dur, frames, levels }));
console.log('frames', frames.length, 'dur', track.dur.toFixed(2), 'shapes', JSON.stringify(shapes));
