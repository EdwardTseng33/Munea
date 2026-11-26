#!/usr/bin/env node
/* 對嘴前後對比（2026-11-21 第三輪）：同一段聲音＋字幕，跑「第二輪草稿」與「第三輪」兩版的臉，逐格記嘴型，算：
   - 圓嘴字（含ㄨㄩㄛㄠㄡ）那個字講的時候有沒有出現圓嘴（oo／oh）
   - ㄅㄆㄇ 字字頭有沒有閉嘴
   - 一秒換幾次嘴、少於 2 格（30 格／秒）就換掉的「一閃而過」次數
   - 第三輪另外記：多少格是字幕決定的、每句音節數跟字數
   基準（每個字在什麼時候講）：照停頓切句，句子裡每個字平均分配時間——這是近似值，兩版用同一把尺。
   第二輪那版照它的做法：整段聲音的頻譜猜母音（lipsync-driver 的離線版，跟 live() 同一套特徵）＋亂數音節節奏（固定亂數種子）。
   用法：node eval-lipsync.js <聲音.wav> <turns.json> <第二輪 companion-face.js> [輸出.json]
     turns.json：[{ "from": 秒, "to": 秒, "text": "這一輪她說的話" }, ...] */
'use strict';
const fs = require('fs'); const path = require('path');
const [WAV, TURNS, OLDFACE, OUT] = process.argv.slice(2);
const ROOT = path.resolve(__dirname, '../..'), WEB = path.join(ROOT, 'web');
const FPS = 60;

function readWav(p) {
  const b = fs.readFileSync(p); let off = 12, fmt = null, data = null;
  while (off < b.length - 8) { const id = b.toString('ascii', off, off + 4), size = b.readUInt32LE(off + 4);
    if (id === 'fmt ') fmt = { sr: b.readUInt32LE(off + 12) }; if (id === 'data') { data = b.subarray(off + 8, off + 8 + size); break; } off += 8 + size + (size & 1); }
  const n = data.length / 2, x = new Float32Array(n); for (let i = 0; i < n; i++) x[i] = data.readInt16LE(i * 2) / 32768;
  return { sr: fmt.sr, x };
}
// 固定亂數（第二輪的音節節奏用 Math.random）
let seed = 12345; Math.random = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };

// ---- 迷你假 DOM（跟 scripts/test-face-expressive-gate.js 同一套）----
function fakeEl() {
  const el = { style: {}, children: [], attrs: {}, appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; if (k === 'src') this._src = ''; }, closest() { return null; } };
  Object.defineProperty(el, 'src', { get() { return this._src || ''; }, set(v) { this._src = v; const ok = fs.existsSync(path.join(WEB, v.split('?')[0])); setImmediate(() => { const cb = ok ? this.onload : this.onerror; if (cb) cb(); }); } });
  return el;
}
global.window = global; global.document = { createElement: () => fakeEl(), querySelector: () => null };
global.requestAnimationFrame = () => 0; global.cancelAnimationFrame = () => {}; global.matchMedia = () => ({ matches: false });
eval(fs.readFileSync(path.join(WEB, 'src/lipsync-driver.js'), 'utf8'));
eval(fs.readFileSync(path.join(WEB, 'src/zh-vowel-table.js'), 'utf8'));
eval(fs.readFileSync(path.join(WEB, 'src/viseme-timeline.js'), 'utf8'));
function loadFace(src) { delete window.MuneaFlatFace; eval(fs.readFileSync(src, 'utf8')); const F = window.MuneaFlatFace; F.mount(fakeEl()); return F; }

const { sr, x } = readWav(WAV);
const turns = JSON.parse(fs.readFileSync(TURNS, 'utf8'));
const VT = window.MuneaVisemeTimeline;

// ---- 基準：每個字的時間（停頓切句、句內平均）----
function groundTruth() {
  const truth = [];
  // 每 10 毫秒音量，找 >= 250 毫秒的停頓
  const hop = Math.round(0.01 * sr), rms = [];
  for (let i = 0; i + hop <= x.length; i += hop) { let e = 0; for (let k = i; k < i + hop; k++) e += x[k] * x[k]; rms.push(Math.sqrt(e / hop)); }
  const thr = 0.01;
  for (const T of turns) {
    if (T.phrases) {      // 手動標的句子時間（有逗號但沒停頓的時候，自動切會對不上）
      // 句尾的字會拉長（句末延長）：最後一個字給 1.6 倍時間，其他平均
      T.phrases.forEach(([a, b, p]) => { const chars = [...p].filter(c => /[㐀-鿿]/.test(c));
        const wt = chars.map((c, j) => j === chars.length - 1 && chars.length > 1 ? 1.6 : 1), tot = wt.reduce((x, y) => x + y, 0);
        let t = a; chars.forEach((c, j) => { const w = (b - a) * wt[j] / tot; truth.push({ ch: c, seq: window.MuneaZhVowels[c] || '?', t0: t, t1: t + w }); t += w; }); });
      continue;
    }
    const segs = []; let s = null, last = null;
    for (let i = Math.floor(T.from * 100); i < Math.min(rms.length, Math.ceil(T.to * 100)); i++) {
      if (rms[i] > thr) { if (s === null) s = i; last = i; } else if (s !== null && i - last > 25) { segs.push([s / 100, (last + 1) / 100]); s = null; }
    }
    if (s !== null) segs.push([s / 100, (last + 1) / 100]);
    const phrases = T.text.split(/[，。？！、,.?!]/).filter(p => p.trim());
    if (segs.length !== phrases.length) console.warn('⚠ 句數對不上', T.text, segs.length, phrases.length);
    phrases.forEach((p, k) => {
      const seg = segs[Math.min(k, segs.length - 1)]; const chars = [...p].filter(c => /[㐀-鿿]/.test(c));
      const w = (seg[1] - seg[0]) / chars.length;
      chars.forEach((c, j) => truth.push({ ch: c, seq: window.MuneaZhVowels[c] || '?', t0: seg[0] + j * w, t1: seg[0] + (j + 1) * w }));
    });
  }
  return truth;
}

async function runOld() {
  const F = loadFace(OLDFACE);
  F.expressive = true; await F.setSkin({ dir: 'avatars/ningning-rig/', bg: '#BADDD6', aspect: 1536 / 2752, expressive: true });
  const track = window.LipSync.analyze({ sampleRate: sr, length: x.length, duration: x.length / sr, numberOfChannels: 1, getChannelData: () => x });
  const sample = window.LipSync.makeSampler(track);
  const out = [];
  for (let i = 0; i < Math.ceil(track.dur * FPS); i++) {
    const t = i / FPS, now = 10000 + t * 1000;
    const speaking = turns.some(T => t >= T.from - 0.05 && t <= T.to);
    F.speaking = () => speaking;
    const s = sample(Math.min(track.dur - 0.011, t));
    if (speaking && s) F.setViseme(s.open, s.shape, now);
    F._frame(now);
    out.push({ t, mouth: F._mouth });
  }
  return { frames: out };
}

async function runNew() {
  const F = loadFace(path.join(WEB, 'src/companion-face.js'));
  F.expressive = true; await F.setSkin({ dir: 'avatars/ningning-rig/', bg: '#BADDD6', aspect: 1536 / 2752, expressive: true });
  const tl = new VT.Timeline(sr);
  // 跟真的一樣：每一輪的字幕和聲音在開口前就陸續送到（聲音一塊 0.1 秒）
  for (const T of turns) {
    tl.pushCaption(T.text);
    const a = Math.round(T.from * sr), b = Math.round(T.to * sr);
    for (let k = a; k < b; k += 2400) tl.pushAudio(x.subarray(k, Math.min(b, k + 2400)), k / sr);
    tl.endTurn();
  }
  const LEAD = 0.065;
  let src = { caption: 0, spectrum: 0, energy: 0, none: 0 };
  F.visemeProvider = () => { const s = tl.sample(curT + LEAD); src[s.src] = (src[s.src] || 0) + 1; return s; };
  F.speaking = () => false;
  let curT = 0; const out = [];
  for (let i = 0; i < Math.ceil(x.length / sr * FPS); i++) {
    curT = i / FPS; const now = 10000 + curT * 1000;
    F._frame(now);
    out.push({ t: curT, mouth: F._mouth });
  }
  const per = tl.turns.map(T => ({ chars: T.tokens.filter(c => c !== '|').length, syllablesPlaced: T.syl.length, segments: T.segs.map(s => s.mode).join(',') }));
  return { frames: out, src, perTurn: per, segStats: tl.stats };
}

function score(frames, truth, lead) {
  // lead：這一版刻意讓嘴比聲音早多少秒——評分時把嘴的時間往後挪回來，才是在比「嘴型選得對不對」
  const at = t => frames[Math.max(0, Math.min(frames.length - 1, Math.round((t - (lead || 0)) * FPS)))].mouth;
  const any = (t0, t1, set) => { for (let t = t0; t <= t1; t += 1 / FPS) if (set.includes(at(t))) return true; return false; };
  let round = 0, roundHit = 0, lab = 0, labHit = 0; const misses = [], roundMiss = [];
  for (const c of truth) {
    const w = c.t1 - c.t0, body = c.seq.replace(/^M/, '');
    if (/[UO]/.test(body)) { round++; if (any(c.t0 - 0.3 * w, c.t1 + 0.3 * w, ['oo', 'oh'])) roundHit++; else roundMiss.push(c.ch + '@' + c.t0.toFixed(2)); }
    if (c.seq[0] === 'M') { lab++; if (any(c.t0 - 0.3 * w, c.t0 + 0.6 * w, ['closed'])) labHit++; else misses.push(c.ch + '@' + c.t0.toFixed(2)); }
  }
  // 30 格／秒下的切換次數與一閃而過
  const f30 = []; for (let t = 0; t < frames.length / FPS; t += 1 / 30) f30.push(at(t));
  let changes = 0, flicker = 0, run = 1;
  for (let i = 1; i < f30.length; i++) { if (f30[i] !== f30[i - 1]) { changes++; if (run < 2 && i > 1) flicker++; run = 1; } else run++; }
  const speechS = truth.length ? (turns.reduce((s, T) => s + (T.to - T.from), 0)) : 1;
  const hist = {}; f30.forEach(m => hist[m] = (hist[m] || 0) + 1);
  return { roundChars: round, roundHit, roundRate: +(roundHit / Math.max(1, round)).toFixed(2), labialChars: lab, labialHit: labHit,
    labialRate: +(labHit / Math.max(1, lab)).toFixed(2), labialMiss: misses, roundMiss, changesPerSec: +(changes / speechS).toFixed(1), flickerUnder2Frames: flicker, mouthHist: hist };
}

(async () => {
  const truth = groundTruth();
  const before = await runOld(), after = await runNew();
  const res = { before: score(before.frames, truth, 0), after: score(after.frames, truth, 0.065), afterSources: after.src, afterPerTurn: after.perTurn, afterSegments: after.segStats,
    truthChars: truth.length, note: '基準＝停頓切句、句內每字平均分配（句尾字 1.6 倍）的近似值；圓嘴／閉嘴容許字的前後各 30% 寬度；第三輪的嘴刻意早 65 毫秒，評分時扣回' };
  console.log(JSON.stringify(res, null, 1));
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(res, null, 1));
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
