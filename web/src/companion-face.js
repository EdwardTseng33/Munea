/* 扁平插畫寧寧（2026-09-30 Edward：Rive 取代寧寧的臉，先推一版上架）。
   Rive 角色檔做好前的過渡版：一張全身底圖＋「微張／張開」兩段嘴＋閉眼，共四張全畫布圖，
   全部用同一套 cover 裁切疊在一起，所以天生對齊、不會錯位。
   蓋在聊聊頁最上層：底下的通話、聲音線路照舊不動，只是雲端那張擬真臉被新寧寧蓋住。
   動作：整個人極輕微的呼吸起伏、隨機眨眼、講話時嘴巴跟著「喇叭真的正在播的聲音」開合。 */
(function () {
  'use strict';
  var ASSET = {
    base: 'avatars/ningning-flat-full.png',
    half: 'avatars/ningning-flat/mouth-half.png',
    open: 'avatars/ningning-flat/mouth-open.png',
    eyes: 'avatars/ningning-flat/eyes-closed.png',
  };
  var POLL_MS = 90;          // 問一次「現在播出的聲音多大」的間隔
  var LEVEL_FRESH_MS = 350;  // 超過這麼久沒拿到音量，就改用講話節奏模擬嘴型

  var F = {
    root: null, body: null, layer: {}, raf: 0, running: false,
    // 由 app.js 接上：現在是不是她在講話、目前播出去的音量（0～1；拿不到回 -1）
    speaking: function () { return false; },
    sampleLevel: null,
    _pollTimer: 0, _lvl: -1, _lvlAt: 0, _gainMax: 0.06, _open: 0, _mouth: 'closed', _mouthSince: 0,
    _blinkUntil: 0, _nextBlink: 0, _secondBlinkAt: 0, _syl: 0, _sylUntil: 0,

    mount: function (host) {
      if (this.root || !host) return !!this.root;
      var root = document.createElement('div');
      root.className = 'flat-face';
      root.id = 'flatFace';
      root.setAttribute('aria-hidden', 'true');
      var body = document.createElement('div');
      body.className = 'ff-body';
      // 疊放順序固定：底圖 → 嘴 → 閉眼放最後（8/12 眨眼鬼影教訓：覆蓋貼圖一律畫在最上面）
      ['base', 'half', 'open', 'eyes'].forEach(function (k) {
        var d = document.createElement('div');
        d.className = 'ff-layer ff-' + k;
        d.style.backgroundImage = 'url("' + ASSET[k] + '")';
        body.appendChild(d);
        F.layer[k] = d;
      });
      root.appendChild(body);
      host.appendChild(root);
      this.root = root;
      this.body = body;
      return true;
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
      this._show('eyes', false);
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

    _show: function (k, on) {
      var el = this.layer[k];
      // 用顯示／隱藏切換、不用透明度淡入淡出：淡入淡出的那一瞬間會露出兩層疊影
      if (el) el.style.visibility = on ? 'visible' : 'hidden';
    },

    _setMouth: function (m, now) {
      if (m === this._mouth) return;
      this._mouth = m;
      this._mouthSince = now;
      this._show('half', m === 'half');
      this._show('open', m === 'open');
    },

    _frame: function (now) {
      var t = now / 1000;
      // 呼吸：4.2 秒一次、幅度極小（整個人一起動，零件不會錯開）
      var br = Math.sin(t * 2 * Math.PI / 4.2);
      this.body.style.transform = 'translateY(' + (-br * 0.18).toFixed(3) + '%) scale(' + (1 + br * 0.0028).toFixed(5) + ')';

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
      this._show('eyes', now < this._blinkUntil);

      // 嘴：只有她真的在講話才動；有播出音量就照音量，拿不到音量才用講話節奏模擬
      var target = 0;
      if (this.speaking()) {
        if (this._lvl >= 0 && now - this._lvlAt < LEVEL_FRESH_MS) {
          this._gainMax = Math.max(this._gainMax * 0.997, this._lvl, 0.03);
          target = Math.min(1, Math.max(0, (this._lvl - 0.004) / (this._gainMax * 0.7)));
        } else {
          if (now >= this._sylUntil) {
            this._syl = Math.random() < 0.2 ? 0.05 : 0.3 + Math.random() * 0.7;
            this._sylUntil = now + 110 + Math.random() * 120;
          }
          target = this._syl;
        }
      }
      this._open += (target - this._open) * (target > this._open ? 0.55 : 0.28);
      var want = this._open < 0.16 ? 'closed' : (this._open < 0.55 ? 'half' : 'open');
      // 嘴形至少停 60 毫秒，避免在兩段之間來回閃
      if (want !== this._mouth && now - this._mouthSince >= 60) this._setMouth(want, now);
    },
  };

  window.MuneaFlatFace = F;
})();
