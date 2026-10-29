/* 寧寧的臉（2026-10-28 Edward 拍板：頭不轉、直接正視前方；只留講話嘴型、眨眼、呼吸）。
   素材：一張正面全身圖＋微張／張開嘴＋閉眼三張貼片。頭不轉、不歪、不變形，
   整個人只做呼吸起伏。蓋在聊聊頁最上層：底下的通話、聲音線路照舊不動。
   所有動作都在手機上算、不吃網路。 */
(function () {
  'use strict';
  var DIR = 'avatars/ningning-rig/';
  var SKIN = { bg: '#BADDD6', aspect: 1536 / 2752, dir: DIR };
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
    // 由 app.js 接上：現在是不是她在講話、目前播出去的音量（0～1；拿不到回 -1）
    speaking: function () { return false; },
    sampleLevel: null,
    _pollTimer: 0, _lvl: -1, _lvlAt: 0, _gainMax: 0.06, _open: 0, _mouth: 'closed', _mouthSince: 0,
    _blinkUntil: 0, _nextBlink: 0, _secondBlinkAt: 0, _syl: 0, _sylUntil: 0, _still: false, _eyesClosed: false,

    mount: function (host) {
      if (this.root || !host) return !!this.root;
      var root = el('flat-face');
      root.id = 'flatFace';
      root.setAttribute('aria-hidden', 'true');
      this.stage = el('ff-stage', root);
      this.body = el('ff-part ff-body', this.stage);
      // 全身圖 → 嘴兩段 → 閉眼放最後（8/12 眨眼鬼影教訓：覆蓋貼圖一律畫在最上面）
      this.img.body = this._img('body', this.body);
      this.img.half = this._img('half', this.body);
      this.img.open = this._img('open', this.body);
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

    _load: function (im, src) {
      return new Promise(function (resolve) {
        im.onload = im.onerror = function () { resolve(); };
        im.src = src;
      });
    },

    // 換一套角色素材；回傳全部圖片載好的 Promise
    setSkin: function (skin) {
      this.skin = skin;
      if (!this.root) return Promise.resolve();
      this.root.style.background = skin.bg;
      this.stage.style.aspectRatio = String(skin.aspect);
      return Promise.all([
        this._load(this.img.body, skin.dir + 'body.webp'),
        this._load(this.img.half, skin.dir + 'mouth-half.webp'),
        this._load(this.img.open, skin.dir + 'mouth-open.webp'),
        this._load(this.img.eyes, skin.dir + 'eyes-closed.webp'),
      ]);
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
      this._mouth = m;
      this._mouthSince = now;
      this.img.half.style.visibility = m === 'half' ? 'visible' : 'hidden';
      this.img.open.style.visibility = m === 'open' ? 'visible' : 'hidden';
    },

    _setEyes: function (closed) {
      if (closed === this._eyesClosed) return;
      this._eyesClosed = closed;
      this.img.eyes.style.visibility = closed ? 'visible' : 'hidden';
    },

    _frame: function (now) {
      var t = now / 1000;
      var speaking = this.speaking();

      // 嘴：只有她真的在講話才動。音量決定「張多大」，再乘上音節節奏讓嘴一開一合——
      // 通話中每 0.09 秒才讀得到一次音量，太粗；只照音量的話用寧寧真聲音模擬有 78% 時間張到最大。
      // 乘上節奏後閉 30%／微張 48%／張開 22%、每秒換 5～6 次，接近真人講話。拿不到音量時就只用節奏。
      var target = 0;
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
        target = loud * this._syl;
      }
      // 平滑照實際經過的時間算（快張約 21 毫秒、慢合約 51 毫秒），手機慢一點、掉格也一樣的手感
      var dt = Math.min(100, Math.max(0, now - (this._lastT || now)));
      this._lastT = now;
      var tau = target > this._open ? 21 : 51;
      this._open += (target - this._open) * (1 - Math.exp(-dt / tau));
      var want = this._open < 0.16 ? 'closed' : (this._open < 0.55 ? 'half' : 'open');
      // 嘴形至少停 60 毫秒，避免在兩段之間來回閃
      if (want !== this._mouth && now - this._mouthSince >= 60) this._setMouth(want, now);

      // 眨眼：2.4～5.8 秒一次、閉 170 毫秒；偶爾連眨兩下
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
