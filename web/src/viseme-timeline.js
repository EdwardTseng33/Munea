/* 嘴型時間軸（2026-11-21 寧寧多嘴型草稿第三輪，開關 munea.faceExpressive 開了才載）
   為什麼不再「邊播邊聽」：11/21 測試機量到，語音主機送來的聲音和字幕都比她講話快很多（22 秒的話 3～4 秒就送完），
   每段字幕到的時候，對應的聲音大多還沒到。所以 App 收到聲音的當下就能先把整條時間軸算好：
     1. 聲音一塊塊進來（還沒播）→ 每 10 毫秒算一格：音量、共振峰（lipsync-driver.js 的分析器）
     2. 停頓（≥250 毫秒）把聲音切成一段段「一口氣講的話」
     3. 一段講完 → 照語速估這段有幾個字，再對到最近的標點（字幕的一句）；在這段裡挑最深的 N−1 個音量低谷切成 N 個字
     4. 每個字查 zh-vowel-table.js 得到 1～3 個嘴型（ㄅㄆㄇ 先閉一下；ㄛ 多半是滑過去的）
     5. 對不到標點（字幕跟實際講的不一樣、或停頓不在標點上）→ 這段只照音量開合，到下一個停頓再對齊
   嘴的規則（調研「人物對嘴自然度-調研-2026-11-21」附錄 B2／C2，該文件未進版控）：
     - 介音約 25%、主要母音約 55%、收尾約 20%；ㄅㄆㄇ 的閉嘴從字頭拿 60 毫秒
     - 下一個字是圓嘴開頭（ㄨㄩㄛ）→ 這個字最後 25% 提早變圓
     - 連續講話中間不閉嘴，只有 ㄅㄆㄇ 或停頓超過 150 毫秒才閉
   日文、英文：字幕法先不用（日文漢字讀音查不到），只用聲音頻譜猜母音。 */
(function (g) {
  'use strict';
  var HOP = 0.010;
  var PAUSE = /[，。？！、；：,.?!;:…—～\n]/;
  var KANA = /[぀-ヿ]/;
  var M_FRAMES = 6;           // ㄅㄆㄇ 閉嘴 60 毫秒（調研：至少一格、40～60 毫秒）
  var SILENT_CLOSE = 15;      // 停頓超過 150 毫秒才閉嘴
  var SEG_PAUSE = 25;         // 停頓 250 毫秒＝一段話結束
  var DEFAULT_RATE = 4.3;     // 每秒幾個字（11/21 測試機量到約 3.8～4.4）

  function tokenize(text, state) {
    var out = [], zh = g.MuneaZhVowels || {}, s = String(text || '');
    if (state) state.kana = state.kana || KANA.test(s);
    if (state && state.kana) return out;                   // 日文：不走字幕法
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      if (PAUSE.test(c)) { if (out.length && out[out.length - 1] !== '|') out.push('|'); continue; }
      if (c === '嗯' || c === '唔') { out.push('M'); continue; }
      if (/[㐀-鿿]/.test(c)) out.push(zh[c] || '?');
    }
    return out;
  }
  function syllableCount(text) { return tokenize(text, {}).filter(function (t) { return t !== '|'; }).length; }

  function mouthOf(code, open) {
    switch (code) {
      case 'M': return 'closed';
      case 'A': return open < 0.45 ? 'half' : 'open';
      case 'O': return open < 0.3 ? 'oo' : 'oh';
      case 'U': return 'oo';
      case 'I': return open < 0.2 ? 'half' : 'ee';
      case 'H': return 'half';
      default: return null;
    }
  }
  function energyMouth(open) { return open < 0.16 ? 'closed' : (open < 0.55 ? 'half' : 'open'); }
  function segments(seq) {
    if (seq.length === 1) return [1];
    if (seq.length === 3) return [0.25, 0.55, 0.2];
    return ('IU'.indexOf(seq[0]) >= 0 && 'AOH'.indexOf(seq[1]) >= 0) ? [0.3, 0.7] : [0.75, 0.25];
  }

  function Timeline(sampleRate) {
    var LS = g.LipSync;
    this.sr = sampleRate || 24000;
    this.an = LS.makeAnalyzer(this.sr);
    this.vowelOf = LS.vowelOf;
    this.frames = [];
    this.turns = [];
    this._floor = -60; this._top = -20; this._open = 0;
    this._tail = null; this._tailEnd = -1;
    this._newTurn = true;
    this.stats = { segments: 0, synced: 0, unsynced: 0, noCaption: 0 };
  }
  Timeline.prototype._turn = function () {
    if (this._newTurn || !this.turns.length) {
      // syl：已經排好時間的字 {from, to, peak, tok}；segs：一段段話 {from, to, mode:'caption'|'energy'|'spectrum'}
      this.turns.push({ tokens: [], ptr: 0, syl: [], segs: [], state: {}, firstFrame: this.frames.length,
        segStart: -1, lastVoiced: -1, silRun: 0, scanned: this.frames.length, rate: DEFAULT_RATE, rateN: 0 });
      this._newTurn = false;
      if (this.turns.length > 6) this.turns.shift();
    }
    return this.turns[this.turns.length - 1];
  };
  Timeline.prototype.currentTurn = function () { return this.turns[this.turns.length - 1] || null; };
  // 主機說這一輪講完：還沒收尾的那一段現在收尾，之後進來的算新的一輪
  Timeline.prototype.endTurn = function () {
    var T = this.turns[this.turns.length - 1];
    if (T && !this._newTurn) { this._scan(T); if (T.segStart >= 0) this._closeSeg(T, T.segStart, T.lastVoiced, true); }
    this._newTurn = true;
  };
  Timeline.prototype.pushCaption = function (text) {
    var T = this._turn();
    Array.prototype.push.apply(T.tokens, tokenize(text, T.state));
  };
  Timeline.prototype.pushAudio = function (f32, t0) {
    var T = this._turn();
    var sr = this.sr, win = this.an.winN, hop = Math.round(HOP * sr);
    var buf = f32, lead = 0;
    if (this._tail && Math.abs(t0 - this._tailEnd) < 0.005) {
      buf = new Float32Array(this._tail.length + f32.length); buf.set(this._tail); buf.set(f32, this._tail.length); lead = this._tail.length;
    }
    for (var off = 0; off + win <= buf.length; off += hop) {
      if (off + win <= lead) continue;
      var f = this.an.frame(buf, off), db = 20 * Math.log10(f.rms + 1e-6);
      this._floor += (db < this._floor) ? (db - this._floor) * 0.2 : 0.02;
      if (db > this._top) this._top = db; else this._top -= 0.01;
      var r = Math.pow(Math.max(0, Math.min(1, (db - (this._floor + 6)) / Math.max(12, this._top - (this._floor + 6)))), 0.75);
      this._open += (r - this._open) * (r > this._open ? 0.39 : 0.133);
      this.frames.push({ t: t0 + (off - lead + win / 2) / sr, r: r, open: this._open, voiced: db > Math.max(this._floor + 8, this._top - 30), f1: f.f1, f2: f.f2, hf: f.hf });
    }
    var keep = Math.min(buf.length, win);
    this._tail = buf.slice(buf.length - keep); this._tailEnd = t0 + f32.length / sr;
    this._scan(T);
  };
  // 切段：連續 250 毫秒沒聲音＝一段話結束
  Timeline.prototype._scan = function (T) {
    var F = this.frames;
    for (var i = T.scanned; i < F.length; i++) {
      if (F[i].voiced) { if (T.segStart < 0) T.segStart = i; T.lastVoiced = i; T.silRun = 0; }
      else if (T.segStart >= 0) { T.silRun++; if (T.silRun >= SEG_PAUSE) { this._closeSeg(T, T.segStart, T.lastVoiced, false); T.segStart = -1; } }
    }
    T.scanned = F.length;
  };
  Timeline.prototype._closeSeg = function (T, a, b, last) {
    if (b - a < 6) return;                                   // 太短（雜音）
    var F = this.frames, dur = F[b].t - F[a].t + HOP;
    this.stats.segments++;
    // 這段大概幾個字
    var est = Math.max(1, Math.round(dur * T.rate));
    var counts = [], c = 0, k, firstTok = T.ptr;
    while (firstTok < T.tokens.length && T.tokens[firstTok] === '|') firstTok++;
    for (k = firstTok; k < T.tokens.length; k++) { if (T.tokens[k] === '|') counts.push({ n: c, next: k + 1 }); else c++; }
    var remaining = c;
    if (!remaining && !counts.length) {                       // 字幕還沒到（或日文英文）：頻譜猜
      T.segs.push({ from: a, to: b, mode: 'spectrum' }); this.stats.noCaption++; return;
    }
    if (last && remaining) counts.push({ n: remaining, next: T.tokens.length });
    var tol = Math.max(3, Math.round(est * 0.45)), best = null;
    counts.forEach(function (o) { if (o.n > 0 && Math.abs(o.n - est) <= tol && (!best || Math.abs(o.n - est) < Math.abs(best.n - est))) best = o; });
    // 這一輪最後一段：剩下的字能塞進來就全給它
    if (last && remaining && Math.abs(remaining - est) <= tol) best = { n: remaining, next: T.tokens.length };
    if (!best) {
      // 對不到標點：這段只照音量開合；指標先照估計往前走，下一段再對齊
      T.segs.push({ from: a, to: b, mode: 'energy' }); this.stats.unsynced++;
      var skip = Math.min(est, remaining), j = firstTok;
      while (skip > 0 && j < T.tokens.length) { if (T.tokens[j] !== '|') skip--; j++; }
      T.ptr = j; return;
    }
    // 對到了：在這段裡挑最深的 n−1 個音量低谷切成 n 個字
    var n = best.n, cuts = this._cuts(a, b, n), toks = [];
    for (k = firstTok; k < T.tokens.length && toks.length < n; k++) if (T.tokens[k] !== '|') toks.push(k);
    var bounds = [a].concat(cuts, [b + 1]);
    for (k = 0; k < n; k++) {
      var s0 = bounds[k], s1 = bounds[k + 1] - 1, pk = s0;
      for (var q = s0; q <= s1; q++) if (F[q].r > F[pk].r) pk = q;
      T.syl.push({ from: s0, to: s1, peak: pk, tok: toks[k], t: F[pk].t });
    }
    T.segs.push({ from: a, to: b, mode: 'caption' }); this.stats.synced++;
    T.ptr = best.next;
    if (n >= 4) { T.rateN++; T.rate += ((n / dur) - T.rate) / Math.min(T.rateN + 1, 4); }   // 語速跟著這個人慢慢調（太短的段落不算）
  };
  Timeline.prototype._cuts = function (a, b, n) {
    if (n <= 1) return [];
    var F = this.frames, sm = [], i;
    for (i = a; i <= b; i++) { var s = 0, c = 0; for (var d = -2; d <= 2; d++) { var j = i + d; if (j >= a && j <= b) { s += F[j].r; c++; } } sm.push(s / c); }
    var cand = [];
    for (i = 2; i < sm.length - 2; i++) if (sm[i] <= sm[i - 1] && sm[i] <= sm[i + 1]) {
      var lp = 0, rp = 0, k;
      for (k = i; k >= 0; k--) lp = Math.max(lp, sm[k]);
      for (k = i; k < sm.length; k++) rp = Math.max(rp, sm[k]);
      // 只看附近 150 毫秒內的高點當深度
      var l = 0, r = 0;
      for (k = Math.max(0, i - 15); k < i; k++) l = Math.max(l, sm[k]);
      for (k = i + 1; k <= Math.min(sm.length - 1, i + 15); k++) r = Math.max(r, sm[k]);
      cand.push({ i: i, depth: Math.min(l, r) - sm[i] });
    }
    cand.sort(function (x, y) { return y.depth - x.depth; });
    var minGap = Math.max(6, Math.floor(0.45 * sm.length / n)), pick = [];
    for (i = 0; i < cand.length && pick.length < n - 1; i++) {
      if (pick.every(function (p) { return Math.abs(p - cand[i].i) >= minGap; }) && cand[i].i >= minGap / 2 && sm.length - cand[i].i >= minGap / 2) pick.push(cand[i].i);
    }
    // 低谷不夠：在最長的那幾個字中間平分
    while (pick.length < n - 1) {
      var pts = [0].concat(pick.slice().sort(function (x, y) { return x - y; }), [sm.length]), bi = 0, bl = -1;
      for (i = 0; i + 1 < pts.length; i++) if (pts[i + 1] - pts[i] > bl) { bl = pts[i + 1] - pts[i]; bi = i; }
      pick.push(Math.round((pts[bi] + pts[bi + 1]) / 2));
    }
    return pick.sort(function (x, y) { return x - y; }).map(function (p) { return a + p; });
  };
  // 某一輪字幕的第幾個字 → 那個字的音量高點時間（還沒排好就回 null）
  Timeline.prototype.syllableTime = function (T, syl) {
    if (!T) return null;
    var count = -1, i;
    for (i = 0; i < T.tokens.length; i++) { if (T.tokens[i] !== '|') count++; if (count === syl) break; }
    if (count < syl) return null;
    for (var n = 0; n < T.syl.length; n++) if (T.syl[n].tok >= i) return T.syl[n].t;
    return null;
  };
  Timeline.prototype._findFrame = function (t) {
    var F = this.frames, lo = 0, hi = F.length - 1;
    if (!F.length || t < F[0].t - HOP || t > F[hi].t + HOP) return -1;
    while (lo < hi) { var m = (lo + hi + 1) >> 1; if (F[m].t <= t) lo = m; else hi = m - 1; }
    return lo;
  };
  Timeline.prototype._turnOfFrame = function (i) {
    for (var k = this.turns.length - 1; k >= 0; k--) if (this.turns[k].firstFrame <= i) return this.turns[k];
    return this.turns[0] || null;
  };
  Timeline.prototype._shortGap = function (i) {
    var F = this.frames, a = -1, b = -1, k;
    for (k = i; k >= Math.max(0, i - SILENT_CLOSE); k--) if (F[k].voiced) { a = k; break; }
    for (k = i; k < Math.min(F.length, i + SILENT_CLOSE); k++) if (F[k].voiced) { b = k; break; }
    return a >= 0 && b >= 0 && (b - a) < SILENT_CLOSE;
  };
  // 播放時間 t 那一刻的嘴：{ open, mouth, code, src }
  Timeline.prototype.sample = function (t, useCaptions) {
    var i = this._findFrame(t);
    if (i < 0) return { open: 0, mouth: 'closed', code: 'sil', src: 'none' };
    var F = this.frames, f = F[i];
    var T = this._turnOfFrame(i);
    var seg = null, k;
    if (T) for (k = T.segs.length - 1; k >= 0; k--) if (T.segs[k].from <= i && i <= T.segs[k].to) { seg = T.segs[k]; break; }
    var quiet = !f.voiced || f.open < 0.14;
    var mode = useCaptions === false ? 'spectrum' : (seg ? seg.mode : 'energy');   // 還沒收尾的段落：先照音量
    if (mode === 'caption') {
      var sy = null, si = -1;
      for (k = T.syl.length - 1; k >= 0; k--) if (T.syl[k].from <= i) { sy = T.syl[k]; si = k; break; }
      if (sy && i <= sy.to) {
        var seq = T.tokens[sy.tok];
        if (seq && seq !== '?') {
          var code;
          if (seq[0] === 'M' && i - sy.from < M_FRAMES) code = 'M';
          else {
            var body = seq[0] === 'M' ? seq.slice(1) : seq;
            var start = seq[0] === 'M' ? sy.from + M_FRAMES : sy.from;
            var span = Math.max(1, sy.to + 1 - start), p = Math.max(0, Math.min(0.999, (i - start) / span));
            var segp = segments(body), acc = 0, q = 0;
            for (; q < segp.length; q++) { acc += segp[q]; if (p < acc) break; }
            code = body[Math.min(q, body.length - 1)];
            var next = T.syl[si + 1], nseq = next && T.tokens[next.tok];
            if (p > 0.75 && nseq && 'UO'.indexOf(nseq[0]) >= 0 && code !== 'U' && code !== 'O' && next.from - sy.to <= 2) code = 'U';
          }
          if (code === 'M') return { open: f.open, mouth: 'closed', code: 'M', src: 'caption' };
          var m = mouthOf(code, Math.max(f.open, 0.2));    // 字的中間音量掉一下也不閉嘴（只有 ㄅㄆㄇ 與停頓才閉）
          if (m) return { open: f.open, mouth: m, code: code, src: 'caption' };
        }
      }
    }
    if (quiet) {
      if (this._shortGap(i)) return { open: f.open, mouth: 'half', code: 'gap', src: 'energy' };
      return { open: f.open, mouth: 'closed', code: 'sil', src: 'energy' };
    }
    if (mode === 'spectrum') {
      var v = f.hf > 0.45 ? 'H' : ({ a: 'A', e: 'H', i: 'I', o: 'O', u: 'U' })[this.vowelOf(f.f1, f.f2)];
      return { open: f.open, mouth: mouthOf(v, f.open), code: v, src: 'spectrum' };
    }
    return { open: f.open, mouth: energyMouth(f.open), code: 'nrg', src: 'energy' };
  };
  Timeline.prototype.cancelAfter = function (t) {
    var F = this.frames, i = F.length;
    while (i > 0 && F[i - 1].t > t) i--;
    F.length = i; this._tail = null;
    this.turns.forEach(function (T) {
      T.syl = T.syl.filter(function (s) { return s.to < i; });
      T.segs = T.segs.filter(function (s) { return s.to < i; });
      T.scanned = Math.min(T.scanned, i); T.segStart = -1;
    });
    this._newTurn = true;
  };
  Timeline.prototype.prune = function (beforeT) {
    var F = this.frames, drop = 0;
    while (drop < F.length - 200 && F[drop].t < beforeT) drop++;
    if (drop < 3000) return;
    F.splice(0, drop);
    this.turns.forEach(function (T) {
      T.firstFrame -= drop; T.scanned -= drop; if (T.segStart >= 0) T.segStart -= drop; T.lastVoiced -= drop;
      T.syl.forEach(function (s) { s.from -= drop; s.to -= drop; s.peak -= drop; });
      T.segs.forEach(function (s) { s.from -= drop; s.to -= drop; });
    });
  };

  g.MuneaVisemeTimeline = { Timeline: Timeline, tokenize: tokenize, syllableCount: syllableCount, mouthOf: mouthOf };
})(typeof window !== 'undefined' ? window : globalThis);
