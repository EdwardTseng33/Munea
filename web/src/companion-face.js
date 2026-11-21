/* 寧寧的臉（2026-10-28 Edward 拍板：頭不轉、直接正視前方；只留講話嘴型、眨眼、呼吸）。
   素材：一張正面全身圖＋微張／張開嘴＋閉眼三張貼片。頭不轉、不歪、不變形，
   整個人只做呼吸起伏。蓋在聊聊頁最上層：底下的通話、聲音線路照舊不動。
   所有動作都在手機上算、不吃網路。
   2026-11-21 草稿（待 Edward 看影片）：多三種嘴型（ㄧ扁寬 ee／ㄨ圓 oo／ㄛ圓開 oh）＋閉嘴微笑，
   表情三種（傾聽＝柔和眼／微笑＝彎眼＋嘴角上揚／關心＝眉頭微抬）。都是同一張定稿圖「只改嘴／眼／眉」
   切出的貼片；角色沒有這些貼片（例如沐沐）就自動退回原本三段嘴、行為跟以前一模一樣。
   嘴形來源：setViseme(張口量, 母音) 有新資料就照母音選嘴；沒有就照舊用音量＋節奏。
   表情：setExpression('neutral'|'listen'|'smile'|'concern')；眼睛／眉毛趁眨眼那一下換，不會硬跳。 */
(function () {
  'use strict';
  var DIR = 'avatars/ningning-rig/';
  // expressive：這個角色有沒有多嘴型／表情貼片（目前只有寧寧）。沒有的角色不去要那 7 張圖。
  var SKIN = { bg: '#BADDD6', aspect: 1536 / 2752, dir: DIR, expressive: true };
  var EXTRA = { ee: 'mouth-ee', oo: 'mouth-oo', oh: 'mouth-oh', msmile: 'mouth-smile',
    brows: 'brows-concern', esoft: 'eyes-soft', esmile: 'eyes-smile',
    // 11/21 第三輪：手勢（身體＋手臂那一層的貼片，疊在全身圖上、臉的貼片下面）
    gWaveMid: 'gesture-wave-mid', gWaveUp: 'gesture-wave-up', gWaveTilt: 'gesture-wave-tilt',
    gChestMid: 'gesture-chest-mid', gChestOn: 'gesture-chest-on', gPalm: 'gesture-palm' };
  // 手勢＝一串關鍵格：[貼片, 停多久毫秒, 換到這一格的淡入毫秒]；最後回到放下（淡出）
  var GESTURES = {
    wave: [['gWaveMid', 130, 120], ['gWaveUp', 260, 90], ['gWaveTilt', 200, 80], ['gWaveUp', 200, 80],
      ['gWaveTilt', 200, 80], ['gWaveUp', 240, 80], ['gWaveMid', 130, 90], [null, 0, 220]],
    chest: [['gChestMid', 150, 200], ['gChestOn', 1700, 120], ['gChestMid', 150, 120], [null, 0, 240]],
    palm: [['gPalm', 1500, 260], [null, 0, 260]] };
  var MOUTH_FADE_MS = 60;    // 相鄰兩個嘴型交叉淡化（11/21 第三輪；只在開關開時用；調研：扁平色塊過渡要短，60 毫秒內）
  var CLOSE_FADE_MS = 35;    // ㄅㄆㄇ 閉嘴是「快閃」，換得更快
  var MOUTH_HOLD_MS = 66;    // 每個嘴型至少停 2 格（30 格／秒）
  var POLL_MS = 90;          // 問一次「現在播出的聲音多大」的間隔
  var LEVEL_FRESH_MS = 350;  // 超過這麼久沒拿到音量，就改用講話節奏模擬嘴型

  function el(cls, parent) {
    var d = document.createElement('div');
    d.className = cls;
    if (parent) parent.appendChild(d);
    return d;
  }

  var F = {
    root: null, stage: null, body: null, img: {}, raf: 0, running: false, skin: SKIN,
    // 多嘴型＋表情的總開關（app.js 依 localStorage munea.faceExpressive 設；預設關＝跟以前一模一樣、也不載多的圖）
    expressive: false,
    // 由 app.js 接上：現在是不是她在講話、目前播出去的音量（0～1；拿不到回 -1）
    speaking: function () { return false; },
    sampleLevel: null,
    _pollTimer: 0, _lvl: -1, _lvlAt: 0, _gainMax: 0.06, _open: 0, _mouth: 'closed', _mouthSince: 0,
    _blinkUntil: 0, _nextBlink: 0, _secondBlinkAt: 0, _syl: 0, _sylUntil: 0, _still: false, _eyesClosed: false,
    _has: {}, _vis: null, _visAt: -1e9, _expr: 'neutral', _exprWant: 'neutral', _eyeShown: 'none', _browsOn: false,
    // 第三輪：嘴型來源（app.js 的時間軸；每格問一次「現在聽到的那一刻是哪個嘴」）、嘴型淡化、手勢
    visemeProvider: null, _mouthPrev: null, _gesture: null, _gLayer: null, _gPrev: null, _gSince: 0, _gFade: 0,

    mount: function (host) {
      if (this.root || !host) return !!this.root;
      var root = el('flat-face');
      root.id = 'flatFace';
      root.setAttribute('aria-hidden', 'true');
      this.stage = el('ff-stage', root);
      this.body = el('ff-part ff-body', this.stage);
      // 全身圖 → 嘴兩段 → 閉眼放最後（8/12 眨眼鬼影教訓：覆蓋貼圖一律畫在最上面）
      this.img.body = this._img('body', this.body);
      // 手勢層：在全身圖上、所有臉的貼片下面
      ['gWaveMid', 'gWaveUp', 'gWaveTilt', 'gChestMid', 'gChestOn', 'gPalm'].forEach(function (k) { this.img[k] = this._img(k, this.body); }, this);
      this.img.half = this._img('half', this.body);
      this.img.open = this._img('open', this.body);
      // 11/21 草稿：多的嘴型、眉毛、表情眼；閉眼仍放最上面
      this.img.ee = this._img('ee', this.body);
      this.img.oo = this._img('oo', this.body);
      this.img.oh = this._img('oh', this.body);
      this.img.msmile = this._img('msmile', this.body);
      this.img.brows = this._img('brows', this.body);
      this.img.esoft = this._img('esoft', this.body);
      this.img.esmile = this._img('esmile', this.body);
      this.img.eyes = this._img('eyes', this.body);
      host.appendChild(root);
      // 淺色背景：頂部名字／計時改深色字（白字實測只有 2.2:1，看不清楚）
      var screen = host.closest('.face-screen');
      if (screen) screen.classList.add('flat-mode');
      this.root = root;
      try { this._still = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}
      this.setSkin(this.skin);
      return true;
    },

    _img: function (k, parent) {
      var im = document.createElement('img');
      im.className = 'ff-img ff-' + k;
      im.alt = '';
      im.decoding = 'async';
      if (k !== 'body') im.style.visibility = 'hidden';
      parent.appendChild(im);
      return im;
    },

    _load: function (im, src, key) {
      var self = this;
      return new Promise(function (resolve) {
        im.onload = function () { if (key) self._has[key] = true; resolve(); };
        im.onerror = function () { if (key) self._has[key] = false; resolve(); };
        if (key) self._has[key] = false;
        im.src = src;
      });
    },

    // 換一套角色素材；回傳全部圖片載好的 Promise
    setSkin: function (skin) {
      this.skin = skin;
      if (!this.root) return Promise.resolve();
      this.root.style.background = skin.bg;
      this.stage.style.aspectRatio = String(skin.aspect);
      var jobs = [
        this._load(this.img.body, skin.dir + 'body.webp'),
        this._load(this.img.half, skin.dir + 'mouth-half.webp'),
        this._load(this.img.open, skin.dir + 'mouth-open.webp'),
        this._load(this.img.eyes, skin.dir + 'eyes-closed.webp'),
      ];
      // 多的嘴型／表情貼片：開關開、而且這個角色有，才去載；否則一張都不要（沐沐不會多出 7 個找不到圖的請求）
      var extras = !!(this.expressive && skin.expressive);
      for (var k in EXTRA) {
        if (extras) jobs.push(this._load(this.img[k], skin.dir + EXTRA[k] + '.webp', k));
        else { this._has[k] = false; this.img[k].removeAttribute('src'); this.img[k].style.visibility = 'hidden'; }
      }
      return Promise.all(jobs);
    },

    // 外面（聲音分析）每一小段報一次：張口量 0～1、母音 a/e/i/o/u/sib/sil/closed
    setViseme: function (open, shape, now) {
      this._vis = { open: open, shape: shape };
      this._visAt = now == null ? performance.now() : now;
    },

    // 表情：neutral 一般／listen 傾聽（柔和眼）／smile 微笑（彎眼＋嘴角）／concern 關心（眉頭微抬）
    setExpression: function (name) {
      if (['neutral', 'listen', 'smile', 'concern'].indexOf(name) < 0) name = 'neutral';
      this._exprWant = name;
    },

    start: function () {
      if (!this.root) this.mount(document.querySelector('#chat .face-bg'));
      if (!this.root || this.running) return;
      this.running = true;
      this._nextBlink = performance.now() + 1200;
      this._startPolling();
      var self = this;
      var tick = function (now) {
        if (!self.running) return;
        self._frame(now);
        self.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
    },

    stop: function () {
      this.running = false;
      if (this.raf) cancelAnimationFrame(this.raf);
      this.raf = 0;
      clearInterval(this._pollTimer);
      this._pollTimer = 0;
      this._setMouth('closed', performance.now());
      this._fadeMouth(performance.now() + 1000);
      this._gesture = null; this._gPrev = null;
      if (this._gLayer && this.img[this._gLayer]) { this.img[this._gLayer].style.visibility = 'hidden'; this.img[this._gLayer].style.opacity = ''; }
      this._gLayer = null;
      this._expr = this._exprWant = 'neutral';
      this._setEyes(false);
    },

    _startPolling: function () {
      var self = this;
      clearInterval(this._pollTimer);
      this._pollTimer = setInterval(function () {
        if (!self.sampleLevel || !self.speaking()) return;
        Promise.resolve(self.sampleLevel()).then(function (v) {
          if (typeof v === 'number' && v >= 0) { self._lvl = v; self._lvlAt = performance.now(); }
        }).catch(function () {});
      }, POLL_MS);
    },

    // 貼片用顯示／隱藏切換、不用透明度淡入淡出：淡入淡出那一瞬間會露出兩層疊影
    _setMouth: function (m, now) {
      if (m === this._mouth) return;
      var prev = this._mouth;
      this._mouth = m;
      this._mouthSince = now;
      var keys = ['half', 'open', 'ee', 'oo', 'oh', 'msmile'];
      if (!this.expressive || !this.visemeProvider) {
        for (var i = 0; i < keys.length; i++) { this.img[keys[i]].style.visibility = m === keys[i] ? 'visible' : 'hidden'; this.img[keys[i]].style.opacity = ''; }
        return;
      }
      // 交叉淡化：新嘴從 0 淡到 1、舊嘴先留著，淡完才藏（全程不會露出底下的閉嘴，也不會兩張半透明疊在一起太久）
      for (var j = 0; j < keys.length; j++) {
        var k = keys[j], im = this.img[k];
        if (k === m) { im.style.visibility = 'visible'; im.style.opacity = '0'; }
        else if (k === prev) { im.style.visibility = 'visible'; im.style.opacity = '1'; }
        else { im.style.visibility = 'hidden'; im.style.opacity = ''; }
      }
      this._mouthPrev = prev;
    },

    _fadeMouth: function (now) {
      if (!this.expressive || !this.visemeProvider) return;
      var p = Math.min(1, (now - this._mouthSince) / (this._mouth === 'closed' ? CLOSE_FADE_MS : MOUTH_FADE_MS));
      var cur = this.img[this._mouth], prev = this._mouthPrev && this.img[this._mouthPrev];
      if (cur) cur.style.opacity = p >= 1 ? '' : p.toFixed(3);
      if (prev) {
        if (this._mouth === 'closed') prev.style.opacity = (1 - p).toFixed(3);   // 閉嘴＝原圖：舊嘴淡出
        if (p >= 1) { prev.style.visibility = 'hidden'; prev.style.opacity = ''; this._mouthPrev = null; }
      }
    },

    // 手勢：開關開、角色有貼片才做；同時只做一個，做完自己放下
    playGesture: function (name, now) {
      var seq = GESTURES[name];
      var need = { wave: 'gWaveUp', chest: 'gChestOn', palm: 'gPalm' }[name];
      if (!seq || !this.expressive || !this._has[need]) return false;
      if (this._gesture) return false;
      this._gesture = { seq: seq, step: -1, until: 0 };
      this._gNext(now == null ? performance.now() : now);
      return true;
    },

    _gNext: function (now) {
      var G = this._gesture; G.step++;
      var kf = G.seq[G.step];
      if (!kf) { this._gesture = null; return; }
      this._gPrev = this._gLayer; this._gLayer = kf[0]; this._gSince = now; this._gFade = kf[2];
      G.until = now + kf[2] + kf[1];
      if (this._gLayer) { var im = this.img[this._gLayer]; im.style.visibility = 'visible'; im.style.opacity = '0'; }
    },

    _stepGesture: function (now) {
      var G = this._gesture;
      if (!G && !this._gPrev) return;
      var p = this._gFade ? Math.min(1, (now - this._gSince) / this._gFade) : 1;
      var cur = this._gLayer && this.img[this._gLayer], prev = this._gPrev && this.img[this._gPrev];
      if (cur) cur.style.opacity = p >= 1 ? '' : p.toFixed(3);
      if (prev) {
        if (!this._gLayer) prev.style.opacity = (1 - p).toFixed(3);     // 放下：最後一格淡出
        if (p >= 1) { prev.style.visibility = 'hidden'; prev.style.opacity = ''; this._gPrev = null; }
      }
      if (G && now >= G.until) this._gNext(now);
    },

    // 眼睛同一時間只露一種：閉眼／彎眼／柔和眼／原圖（彎眼上面再疊閉眼會露出兩層）
    _showEyes: function (which) {
      if (which === this._eyeShown) return;
      this._eyeShown = which;
      this.img.eyes.style.visibility = which === 'closed' ? 'visible' : 'hidden';
      this.img.esmile.style.visibility = which === 'smile' ? 'visible' : 'hidden';
      this.img.esoft.style.visibility = which === 'soft' ? 'visible' : 'hidden';
    },

    _setBrows: function (on) {
      on = !!(on && this._has.brows);
      if (on === this._browsOn) return;
      this._browsOn = on;
      this.img.brows.style.visibility = on ? 'visible' : 'hidden';
    },

    // 母音 → 這個角色有的嘴型；沒有新嘴型的角色照舊只分微張／張開
    _mouthFor: function (shape, open) {
      if (open < 0.16 || shape === 'sil' || shape === 'closed') return 'closed';
      var H = this._has;
      // 高頻多（ㄙㄘㄕ這類，或壓縮過的聲音）分不出母音：只照張口量走微張／張開，不要一直咧嘴
      if (shape === 'sib') return open < 0.7 ? 'half' : 'open';
      if ((shape === 'e' || shape === 'i') && H.ee) return open < 0.35 ? 'half' : 'ee';
      if (shape === 'u' && H.oo) return 'oo';
      if (shape === 'o' && H.oh && H.oo) return open < 0.45 ? 'oo' : 'oh';
      return open < 0.55 ? 'half' : 'open';
    },

    // 眉毛跟著「目前的表情」走；眼睛：閉眼優先，其次彎眼／柔和眼
    _setEyes: function (closed) {
      this._eyesClosed = closed;
      var e = this._expr;
      this._showEyes(closed ? 'closed' : (e === 'smile' && this._has.esmile ? 'smile'
        : (e === 'listen' && this._has.esoft ? 'soft' : 'none')));
      this._setBrows(e === 'concern');
    },

    _frame: function (now) {
      var t = now / 1000;
      var speaking = this.speaking();
      // 第三輪：有時間軸就直接照它（字幕母音＋真的聽到那一刻；沒聲音＝閉嘴），不再乘亂數節奏
      var direct = null;
      if (this.expressive && this.visemeProvider) { try { direct = this.visemeProvider(now); } catch (e) { direct = null; } }

      // 嘴：只有她真的在講話才動。音量決定「張多大」，再乘上音節節奏讓嘴一開一合——
      // 通話中每 0.09 秒才讀得到一次音量，太粗；只照音量的話用寧寧真聲音模擬有 78% 時間張到最大。
      // 乘上節奏後閉 30%／微張 48%／張開 22%、每秒換 5～6 次，接近真人講話。拿不到音量時就只用節奏。
      var target = 0;
      var fresh = speaking && this._vis && now - this._visAt < LEVEL_FRESH_MS;
      if (speaking) {
        if (now >= this._sylUntil) {
          this._syl = Math.random() < 0.2 ? 0.1 : 0.25 + Math.random() * 0.75;
          this._sylUntil = now + 120 + Math.random() * 100;
        }
        var loud = 1;
        if (this._lvl >= 0 && now - this._lvlAt < LEVEL_FRESH_MS) {
          this._gainMax = Math.max(this._gainMax * 0.997, this._lvl, 0.03);
          loud = Math.min(1, Math.max(0, (this._lvl - 0.004) / (this._gainMax * 0.85)));
        }
        // 有母音資料：張口量用它（已經跟著聲音走），一樣乘上音節節奏，嘴才會一開一合、不會整段張著
        target = (fresh ? this._vis.open : loud) * this._syl;
      }
      // 平滑照實際經過的時間算（快張約 21 毫秒、慢合約 51 毫秒），手機慢一點、掉格也一樣的手感
      var dt = Math.min(100, Math.max(0, now - (this._lastT || now)));
      this._lastT = now;
      var tau = target > this._open ? 21 : 51;
      this._open += (target - this._open) * (1 - Math.exp(-dt / tau));
      if (direct) this._open = direct.open;
      // 有母音資料：嘴形照母音選（那份資料的嘴形本身已經停得住，至少 70 毫秒）
      var want = direct ? (this._has[direct.mouth] === false ? (direct.mouth === 'closed' ? 'closed' : (direct.open < 0.55 ? 'half' : 'open')) : direct.mouth)
        : fresh ? this._mouthFor(this._vis.shape, this._open)
        : (this._open < 0.16 ? 'closed' : (this._open < 0.55 ? 'half' : 'open'));
      // 關心的時候講話嘴巴收一點：大張嘴配眉頭上抬會變成「嚇到」
      if (this._expr === 'concern') want = want === 'open' ? 'half' : (want === 'oh' ? 'oo' : want);
      // 沒在講話時：微笑表情就閉嘴微笑
      if (want === 'closed' && (direct ? direct.code === 'sil' : !speaking) && this._expr === 'smile' && this._has.msmile) want = 'msmile';
      // 嘴形至少停 60 毫秒（有時間軸時 66 毫秒＝2 格），避免在兩段之間來回閃
      // ㄅㄆㄇ 閉嘴不讓步：不用等上一個嘴停滿 2 格
      var urgent = direct && direct.code === 'M';
      if (want !== this._mouth && (urgent || now - this._mouthSince >= (direct ? MOUTH_HOLD_MS : 60))) this._setMouth(want, now);
      this._fadeMouth(now);
      this._stepGesture(now);

      // 換表情：趁眨一下的時候換（閉眼那 170 毫秒裡換掉眼睛和眉毛，看起來就不會硬跳）
      if (this._exprWant !== this._expr) {
        if (now >= this._blinkUntil) {
          this._blinkUntil = now + 170;
          this._secondBlinkAt = 0;
          this._nextBlink = now + 2400 + Math.random() * 3400;
        }
        this._expr = this._exprWant;
      }
      // 眨眼：2.4～5.8 秒一次、閉 170 毫秒；偶爾連眨兩下（彎眼笑的時候不眨，眼睛本來就瞇著）
      if (this._expr === 'smile' && this._has.esmile && now >= this._nextBlink && now > this._blinkUntil) this._nextBlink = now + 1500;
      if (now >= this._nextBlink && now > this._blinkUntil) {
        this._blinkUntil = now + 170;
        this._secondBlinkAt = Math.random() < 0.12 ? now + 330 : 0;
        this._nextBlink = now + 2400 + Math.random() * 3400;
      }
      if (this._secondBlinkAt && now >= this._secondBlinkAt) {
        this._blinkUntil = now + 150;
        this._secondBlinkAt = 0;
      }
      this._setEyes(now < this._blinkUntil);

      if (this._still) return;

      // 身體：只有呼吸（4.2 秒一次、胸口微微起伏），以畫面底邊為軸；頭不轉、不歪、不左右晃
      var br = Math.sin(t * 2 * Math.PI / 4.2);
      this.body.style.transform = 'translateY(' + (-br * 0.2).toFixed(3) + '%) scale('
        + (1 + br * 0.002).toFixed(5) + ',' + (1 + br * 0.004).toFixed(5) + ')';
    },
  };

  window.MuneaFlatFace = F;
})();
