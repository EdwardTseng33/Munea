/* lipsync-driver.js — 嘴巴吃真聲音（2026-09-29 · 規格書施工順序第 6 步）
   一支通用的嘴型驅動器：把一段聲音（檔案，或之後的即時串流）變成「每 10 毫秒一格」的嘴巴指令：
     open   0~1                  張多大——跟著音量走，快張、慢合
     shape  a/e/i/o/u/sib/closed 嘴形——從共振峰猜母音；氣音→露齒；閉塞音→閉嘴
     stress true/false           重音——帶動眉毛與點頭
   角色引擎各接一個轉接頭（adapter）：{ lead, set(open,shape,meta), idle(), rendered() }
     lead      嘴巴要比聲音早幾秒（引擎自己的彈簧會晚一點，用這個補回來）
     rendered  回報引擎「實際畫出來」的張口量——量尺靠它比對聲音
   量尺：播完問 LipSync.stats() → 嘴跟聲音差幾毫秒、相關係數、嘴形平均停留、起口誤差。
   不靠任何外部函式庫；聲音解碼用瀏覽器內建 Web Audio。 */
(function (global) {
  'use strict';
  var HOP = 0.010, WIN = 0.025;

  /* ---------- FFT：實數輸入、就地 radix-2 ---------- */
  function fft(re, im) {
    var n = re.length, i, j, bit, t, len, ang, wr, wi, s, cr, ci, k, a, b, xr, xi, ncr;
    for (i = 1, j = 0; i < n; i++) {
      bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) { t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (len = 2; len <= n; len <<= 1) {
      ang = -2 * Math.PI / len; wr = Math.cos(ang); wi = Math.sin(ang);
      for (s = 0; s < n; s += len) {
        cr = 1; ci = 0;
        for (k = 0; k < len / 2; k++) {
          a = s + k; b = a + len / 2;
          xr = re[b] * cr - im[b] * ci; xi = re[b] * ci + im[b] * cr;
          re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
          ncr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = ncr;
        }
      }
    }
  }

  function percentile(arr, p) {
    if (!arr.length) return 0;
    var s = Array.prototype.slice.call(arr).sort(function (x, y) { return x - y; });
    var i = Math.min(s.length - 1, Math.max(0, Math.round((s.length - 1) * p)));
    return s[i];
  }
  function clamp01(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }

  /* ---------- 單格特徵：音量、第一／第二共振峰、高頻比例 ---------- */
  function makeAnalyzer(sr) {
    var winN = Math.round(WIN * sr), N = 1;
    while (N < winN) N <<= 1;
    var hann = new Float32Array(winN), i;
    for (i = 0; i < winN; i++) hann[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (winN - 1));
    var re = new Float32Array(N), im = new Float32Array(N), mag = new Float32Array(N / 2), sm = new Float32Array(N / 2);
    var binHz = sr / N;
    function bin(hz) { return Math.min(N / 2 - 1, Math.max(1, Math.round(hz / binHz))); }
    var top = Math.min(8000, sr / 2 - 1);
    var B = { f1lo: bin(200), f1hi: bin(1000), f2lo: bin(900), f2hi: bin(3000),
              hfLo: bin(4000), hfHi: bin(top), allLo: bin(80), allHi: bin(top) };
    var gap = Math.round(250 / binHz);
    function peakIn(lo, hi) {
      var best = lo, bv = -1, k;
      for (k = lo; k <= hi; k++) if (sm[k] > bv) { bv = sm[k]; best = k; }
      return best;
    }
    function energy(lo, hi) { var e = 0, k; for (k = lo; k <= hi; k++) e += mag[k] * mag[k]; return e; }
    return {
      winN: winN,
      frame: function (x, off) {
        var rms = 0, prev = 0, s, pe, k;
        for (k = 0; k < winN; k++) {
          s = (off + k < x.length && off + k >= 0) ? x[off + k] : 0;
          rms += s * s;
          pe = s - 0.97 * prev; prev = s;          // 預強調：把高頻抬平，共振峰才不會被低頻蓋掉
          re[k] = pe * hann[k]; im[k] = 0;
        }
        for (k = winN; k < N; k++) { re[k] = 0; im[k] = 0; }
        rms = Math.sqrt(rms / winN);
        fft(re, im);
        for (k = 0; k < N / 2; k++) mag[k] = Math.sqrt(re[k] * re[k] + im[k] * im[k]);
        for (k = 0; k < N / 2; k++) {              // 五格平滑（約 120Hz）：抹掉諧波尖刺、留共振峰的包絡
          var a = 0, c = 0, m;
          for (m = -2; m <= 2; m++) if (k + m >= 0 && k + m < N / 2) { a += mag[k + m]; c++; }
          sm[k] = a / c;
        }
        var f1b = peakIn(B.f1lo, B.f1hi);
        var f2b = peakIn(Math.max(B.f2lo, f1b + gap), B.f2hi);
        var eAll = energy(B.allLo, B.allHi), eHf = energy(B.hfLo, B.hfHi);
        return { rms: rms, f1: f1b * binHz, f2: f2b * binHz, hf: eHf / (eAll + 1e-12) };
      }
    };
  }

  /* ---------- 嘴形判定（女聲共振峰中心；距離最近者勝） ---------- */
  var VOWELS = [
    { s: 'a', f1: 850, f2: 1400 },
    { s: 'e', f1: 560, f2: 2100 },
    { s: 'i', f1: 340, f2: 2600 },
    { s: 'o', f1: 480, f2: 950 },
    { s: 'u', f1: 370, f2: 780 }
  ];
  function vowelOf(f1, f2) {
    var best = 'a', bd = 1e9, i, d;
    for (i = 0; i < VOWELS.length; i++) {
      d = Math.pow((f1 - VOWELS[i].f1) / 150, 2) + Math.pow((f2 - VOWELS[i].f2) / 350, 2);
      if (d < bd) { bd = d; best = VOWELS[i].s; }
    }
    return best;
  }

  /* ---------- 整段分析：每 10 毫秒一格 ---------- */
  function analyze(buffer) {
    var sr = buffer.sampleRate, x = buffer.getChannelData(0);
    var an = makeAnalyzer(sr), hopN = Math.round(HOP * sr);
    var n = Math.max(1, Math.floor((x.length - an.winN) / hopN) + 1);
    var raw = new Array(n), i, f;
    var dbs = [];
    for (i = 0; i < n; i++) {
      f = an.frame(x, i * hopN);
      f.db = 20 * Math.log10(f.rms + 1e-6);
      raw[i] = f; dbs.push(f.db);
    }
    // 音量→張口：地板取安靜段、天花取最響的 3%；中間用 0.75 次方讓一般說話也看得見嘴在動
    var floor = percentile(dbs, 0.10), gateDb = floor + 8;
    var voiced = dbs.filter(function (d) { return d > gateDb; });
    var topDb = voiced.length ? percentile(voiced, 0.97) : floor + 30;
    var span = Math.max(12, topDb - (floor + 6));
    var frames = new Array(n), open = 0;
    for (i = 0; i < n; i++) {
      f = raw[i];
      var r = clamp01((f.db - (floor + 6)) / span);
      r = Math.pow(r, 0.75);
      var alpha = r > open ? 0.39 : 0.133;         // 快張（20ms）、慢合（70ms）
      open += (r - open) * alpha;
      var shape;
      if (f.db <= gateDb) shape = 'sil';
      else if (f.hf > 0.45) shape = 'sib';
      else shape = vowelOf(f.f1, f.f2);
      frames[i] = { t: i * HOP, rms: f.rms, raw: r, open: open, shape: shape, f1: f.f1, f2: f.f2, hf: f.hf,
                    stress: false, big: false, closed: false };
    }
    // 閉塞音：說話中間音量突然掉到很低、但不超過 80 毫秒＝ㄅㄆㄇ那種閉一下
    for (i = 0; i < n; i++) {
      if (frames[i].raw < 0.12) {
        var j = i; while (j < n && frames[j].raw < 0.12) j++;
        var run = j - i, before = i - 1 >= 0 ? frames[i - 1].open : 0, after = j < n ? frames[Math.min(n - 1, j + 3)].raw : 0;
        if (run <= 8 && before > 0.3 && after > 0.3) for (var k = i; k < j; k++) { frames[k].closed = true; frames[k].shape = 'closed'; }
        i = j;
      }
    }
    // 重音：局部最響、比前 300 毫秒平均高兩成、間隔 250 毫秒以上
    var last = -100;
    for (i = 1; i < n - 1; i++) {
      var o = frames[i].open;
      if (o >= frames[i - 1].open && o >= frames[i + 1].open && o > 0.7 && i - last > 25) {
        var m = 0, c = 0, q;
        for (q = Math.max(0, i - 30); q < i; q++) { m += frames[q].open; c++; }
        m = c ? m / c : 0;
        if (o > 1.2 * m) { frames[i].stress = true; frames[i].big = o > 0.9; last = i; }
      }
    }
    var onset = -1;
    for (i = 0; i < n; i++) if (frames[i].open > 0.15) { onset = frames[i].t; break; }
    return { hop: HOP, frames: frames, dur: x.length / sr, sr: sr, onset: onset, gateDb: gateDb, topDb: topDb };
  }

  /* ---------- 讀某一刻的指令（嘴形要停得住：至少 70 毫秒、且新嘴形連續兩格才換） ---------- */
  function makeSampler(track) {
    var state = { shape: 'sil', since: -1 };
    return function (t) {
      var fr = track.frames, idx = Math.floor(t / track.hop);
      if (idx < 0) idx = 0;
      if (idx >= fr.length) return null;
      var f = fr[idx], nx = fr[Math.min(fr.length - 1, idx + 1)];
      var a = (t - f.t) / track.hop, open = f.open + (nx.open - f.open) * clamp01(a);
      var want = f.shape;
      if (want !== state.shape) {
        var prevSame = idx > 0 && fr[idx - 1].shape === want;
        var hard = want === 'sil' || want === 'closed' || state.shape === 'sil' || state.shape === 'closed';
        if ((prevSame && t - state.since >= 0.07) || (hard && prevSame)) { state.shape = want; state.since = t; }
      }
      return { open: open, shape: state.shape, stress: f.stress, big: f.big, closed: f.closed, rms: f.rms, t: t };
    };
  }

  /* ---------- 播放與量尺 ---------- */
  var ctx = null, cur = null, log = null, lastTrack = null;
  function audioCtx() {
    if (!ctx) { var AC = global.AudioContext || global.webkitAudioContext; ctx = AC ? new AC() : null; }
    return ctx;
  }
  function load(url) {
    return fetch(url).then(function (r) { return r.arrayBuffer(); }).then(function (ab) {
      var c = audioCtx();
      if (!c) throw new Error('這個瀏覽器沒有 Web Audio');
      return new Promise(function (res, rej) { c.decodeAudioData(ab, res, rej); });
    }).then(function (buf) { return { buffer: buf, track: analyze(buf) }; });
  }
  function stop() {
    if (cur) { var c = cur; cur = null; try { if (c.src) c.src.stop(); } catch (e) {} if (c.adapter && c.adapter.idle) c.adapter.idle(); }
  }
  function play(clip, adapter, opts) {
    opts = opts || {};
    stop();
    var track = clip.track, sample = makeSampler(track), lead = (opts.lead != null ? opts.lead : (adapter.lead || 0));
    var c = audioCtx(), silent = false, t0 = 0, p0 = 0, src = null;
    log = { t: [], cmd: [], rendered: [], rms: [], shapes: [], lead: lead, silent: false };
    lastTrack = track;
    function start() {
      if (c && c.state === 'running') {
        src = c.createBufferSource(); src.buffer = clip.buffer; src.connect(c.destination);
        t0 = c.currentTime + 0.05; src.start(t0);
      } else { silent = true; log.silent = true; p0 = performance.now() + 50; }
      var h = { src: src, adapter: adapter, done: false };
      cur = h;
      (function tick() {
        if (cur !== h) return;
        var t = silent ? (performance.now() - p0) / 1000 : (c.currentTime - t0);
        var s = sample(t + lead);
        if (s === null || t > track.dur + 0.05) {
          h.done = true; cur = null; if (adapter.idle) adapter.idle();
          if (opts.onEnd) opts.onEnd();
          return;
        }
        if (t + lead >= 0) {
          adapter.set(s.open, s.shape, { stress: s.stress, big: s.big, closed: s.closed, t: s.t });
          var rendered = adapter.rendered ? adapter.rendered() : s.open;
          var atNow = sample(Math.max(0, t));               // 量尺看的是「現在正在響的聲音」
          log.t.push(t); log.cmd.push(s.open); log.rendered.push(rendered);
          log.rms.push(atNow ? atNow.rms : 0); log.shapes.push(s.shape);
        }
        requestAnimationFrame(tick);
      })();
    }
    if (c && c.state !== 'running') c.resume().then(start, start); else start();
    return { stop: stop };
  }
  // QA 用：不播聲音、直接把某一刻的嘴巴指令套上去（拍多狀態並排圖）
  function freezeAt(clip, adapter, t) {
    stop();
    var s = makeSampler(clip.track)(t);
    if (s) adapter.set(s.open, s.shape, { stress: false, big: false, closed: s.closed, t: t });
    return s;
  }

  function corr(a, b) {
    var n = Math.min(a.length, b.length), i, ma = 0, mb = 0;
    if (n < 3) return 0;
    for (i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
    ma /= n; mb /= n;
    var sab = 0, saa = 0, sbb = 0;
    for (i = 0; i < n; i++) { var da = a[i] - ma, db = b[i] - mb; sab += da * db; saa += da * da; sbb += db * db; }
    return (saa > 0 && sbb > 0) ? sab / Math.sqrt(saa * sbb) : 0;
  }
  // 量尺：把「畫出來的張口量」跟「聲音包絡」重新取樣到 10 毫秒格，找相關係數最高的時間差
  function stats() {
    if (!log || log.t.length < 10) return { ok: false, reason: 'no_log' };
    var hop = HOP, tEnd = log.t[log.t.length - 1], n = Math.floor(tEnd / hop) + 1, R = new Float32Array(n), V = new Float32Array(n), i, j = 0;
    for (i = 0; i < n; i++) {
      var t = i * hop;
      while (j < log.t.length - 1 && log.t[j + 1] <= t) j++;
      R[i] = log.rendered[j]; V[i] = log.rms[j];
    }
    var vmax = 0; for (i = 0; i < n; i++) if (V[i] > vmax) vmax = V[i];
    for (i = 0; i < n; i++) V[i] = vmax ? Math.pow(V[i] / vmax, 0.75) : 0;
    var bestLag = 0, bestC = -2, lag, c;
    for (lag = -15; lag <= 15; lag++) {              // 正＝嘴比聲音晚
      var A = [], Bv = [];
      for (i = 0; i < n; i++) { var k = i - lag; if (k >= 0 && k < n) { A.push(R[i]); Bv.push(V[k]); } }
      c = corr(A, Bv);
      if (c > bestC) { bestC = c; bestLag = lag; }
    }
    var onR = -1, onV = -1;
    for (i = 0; i < n; i++) { if (onR < 0 && R[i] > 0.15) onR = i * hop; if (onV < 0 && V[i] > 0.15) onV = i * hop; }
    var holds = [], run = 1;
    for (i = 1; i < log.shapes.length; i++) { if (log.shapes[i] === log.shapes[i - 1]) run++; else { holds.push(run); run = 1; } }
    var meanHold = holds.length ? holds.reduce(function (p, q) { return p + q; }, 0) / holds.length : run;
    var frameMs = log.t.length > 1 ? (tEnd - log.t[0]) * 1000 / (log.t.length - 1) : 0;
    // 張口量分佈：畫出來的嘴有多少時間是「微張／半開／全開」——全開太少＝嘴在含滷蛋
    var hist = { shut: 0, tiny: 0, half: 0, full: 0 };
    for (i = 0; i < log.rendered.length; i++) { var ro = log.rendered[i]; if (ro < 0.06) hist.shut++; else if (ro < 0.44) hist.tiny++; else if (ro < 0.76) hist.half++; else hist.full++; }
    return {
      openHist: hist, fps: Math.round(frameMs ? 1000 / frameMs : 0),
      ok: true, silent: log.silent, leadMs: Math.round(log.lead * 1000), frames: log.t.length,
      corr: Math.round(bestC * 1000) / 1000, lagMs: bestLag * 10,
      corrAtZero: Math.round(corr(Array.prototype.slice.call(R), Array.prototype.slice.call(V)) * 1000) / 1000,
      onsetSkewMs: (onR >= 0 && onV >= 0) ? Math.round((onR - onV) * 1000) : null,
      meanShapeHoldMs: Math.round(meanHold * frameMs),
      shapes: countShapes(log.shapes)
    };
  }
  function countShapes(arr) { var m = {}, i; for (i = 0; i < arr.length; i++) m[arr[i]] = (m[arr[i]] || 0) + 1; return m; }

  /* ---------- 即時串流（之後接聊聊的真聲音軌）：同一套特徵，門檻改成邊聽邊估 ---------- */
  function live(input, adapter, opts) {
    opts = opts || {};
    var c = audioCtx(), node = input;
    if (input && typeof input.getAudioTracks === 'function') node = c.createMediaStreamSource(input);
    var an = c.createAnalyser(); an.fftSize = 2048; node.connect(an);
    var buf = new Float32Array(an.fftSize), A = makeAnalyzer(c.sampleRate);
    var floorDb = -60, topDb = -20, open = 0, state = { shape: 'sil', since: 0, prev: 'sil' }, on = true, recent = [];
    (function tick() {
      if (!on) return;
      an.getFloatTimeDomainData(buf);
      var f = A.frame(buf, buf.length - A.winN), db = 20 * Math.log10(f.rms + 1e-6), now = performance.now() / 1000;
      floorDb += (db < floorDb) ? (db - floorDb) * 0.2 : 0.02;           // 地板：跟著安靜段慢慢走
      if (db > topDb) topDb = db; else topDb -= 0.01;                   // 天花：跟著最響的慢慢退
      var r = Math.pow(clamp01((db - (floorDb + 6)) / Math.max(12, topDb - (floorDb + 6))), 0.75);
      open += (r - open) * (r > open ? 0.39 : 0.133);
      var want = db <= floorDb + 8 ? 'sil' : (f.hf > 0.45 ? 'sib' : vowelOf(f.f1, f.f2));
      recent.push(r); if (recent.length > 30) recent.shift();
      var closed = r < 0.12 && Math.max.apply(null, recent) > 0.3;
      if (closed) want = 'closed';
      if (want !== state.shape && (want === state.prev || want === 'sil' || want === 'closed') && now - state.since >= 0.07) { state.shape = want; state.since = now; }
      state.prev = want;
      adapter.set(closed ? 0 : open, state.shape, { stress: false, big: false, closed: closed, t: now });
      requestAnimationFrame(tick);
    })();
    return { stop: function () { on = false; try { node.disconnect(an); } catch (e) {} if (adapter.idle) adapter.idle(); } };
  }

  // QA 用：吐出逐格紀錄（時間、指令張口、實際畫出的張口、嘴形）
  function dump() { return log ? { t: log.t, cmd: log.cmd, rendered: log.rendered, shapes: log.shapes, rms: log.rms } : null; }
  global.LipSync = { load: load, analyze: analyze, play: play, stop: stop, freezeAt: freezeAt, live: live, stats: stats,
                     dump: dump, HOP: HOP, makeSampler: makeSampler, lastTrack: function () { return lastTrack; } };
  global.__lip = global.LipSync;
})(window);
