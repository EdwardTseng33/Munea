/* 寧寧的臉（2026-10-28 Edward：把臉收窄的轉頭像頭被擠壓 → 改成真的畫出轉頭角度、一張一張換）。
   素材：一張正面全身圖＋左右各兩個轉頭角度的「頭」圖層（L2 L1 R1 R2）＋每個角度各自的
   微張／張開嘴與閉眼貼片。頭不做任何變形：轉頭就是依序換成鄰近角度的圖（像翻頁動畫），
   每格至少停 0.08 秒再翻下一格、格與格之間只混 0.07 秒；整個人只做呼吸起伏。
   蓋在聊聊頁最上層：底下的通話、聲音線路照舊不動。所有動作都在手機上算、不吃網路。 */
(function () {
  'use strict';
  var DIR = 'avatars/ningning-rig/';
  var POSES = ['L2', 'L1', 'C', 'R1', 'R2'];   // 由左到右，C＝正面（正面沒有頭圖層，全身圖本身就是）
  var CENTER = 2;
  var SKIN = { bg: '#BADDD6', aspect: 1536 / 2752, dir: DIR };
  var POLL_MS = 90;          // 問一次「現在播出的聲音多大」的間隔
  var LEVEL_FRESH_MS = 350;  // 超過這麼久沒拿到音量，就改用講話節奏模擬嘴型
  var FADE_MS = 70;          // 兩個角度之間只混 0.07 秒（約手機 4 格）：長了會看到兩雙眼睛疊在一起、短了像跳格
  var HOLD_MS = 80;          // 每個角度至少停這麼久再換下一格（像手繪動畫一格一格翻）

  function el(cls, parent) {
    var d = document.createElement('div');
    d.className = cls;
    if (parent) parent.appendChild(d);
    return d;
  }

  var F = {
    root: null, stage: null, body: null, bodyImg: null, groups: [], raf: 0, running: false, skin: SKIN,
    // 由 app.js 接上：現在是不是她在講話、目前播出去的音量（0～1；拿不到回 -1）
    speaking: function () { return false; },
    sampleLevel: null,
    _pollTimer: 0, _lvl: -1, _lvlAt: 0, _gainMax: 0.06, _open: 0, _mouth: 'closed', _mouthSince: 0,
    _blinkUntil: 0, _nextBlink: 0, _secondBlinkAt: 0, _syl: 0, _sylUntil: 0, _still: false, _eyesClosed: false,
    _pose: CENTER, _target: CENTER, _fadeFrom: -1, _fadeTo: -1, _fadeStart: 0, _stepReadyAt: 0, _nextLook: 0,

    mount: function (host) {
      if (this.root || !host) return !!this.root;
      var root = el('flat-face');
      root.id = 'flatFace';
      root.setAttribute('aria-hidden', 'true');
      this.stage = el('ff-stage', root);
      this.body = el('ff-part ff-body', this.stage);
      this.bodyImg = this._img('body', this.body);
      // 每個角度一組：頭圖層（正面沒有）→ 嘴兩段 → 閉眼放最後（8/12 眨眼鬼影教訓：覆蓋貼圖一律畫在最上面）
      for (var i = 0; i < POSES.length; i++) {
        var g = el('ff-part ff-pose', this.body);
        g.style.opacity = i === CENTER ? '1' : '0';
        this.groups.push({
          el: g, name: POSES[i],
          head: i === CENTER ? null : this._img('head', g),
          half: this._img('half', g), open: this._img('open', g), eyes: this._img('eyes', g),
        });
      }
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
      if (k === 'half' || k === 'open' || k === 'eyes') im.style.visibility = 'hidden';
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
      var jobs = [this._load(this.bodyImg, skin.dir + 'body.webp')];
      this.groups.forEach(function (g) {
        if (g.head) jobs.push(F._load(g.head, skin.dir + 'head-' + g.name + '.webp'));
        jobs.push(F._load(g.half, skin.dir + 'mouth-half-' + g.name + '.webp'));
        jobs.push(F._load(g.open, skin.dir + 'mouth-open-' + g.name + '.webp'));
        jobs.push(F._load(g.eyes, skin.dir + 'eyes-closed-' + g.name + '.webp'));
      });
      return Promise.all(jobs);
    },

    start: function () {
      if (!this.root) this.mount(document.querySelector('#chat .face-bg'));
      if (!this.root || this.running) return;
      this.running = true;
      this._nextBlink = performance.now() + 1200;
      this._nextLook = performance.now() + 1500;
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
      this._snapTo(CENTER);
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
      this.groups.forEach(function (g) {
        g.half.style.visibility = m === 'half' ? 'visible' : 'hidden';
        g.open.style.visibility = m === 'open' ? 'visible' : 'hidden';
      });
    },

    _setEyes: function (closed) {
      if (closed === this._eyesClosed) return;
      this._eyesClosed = closed;
      this.groups.forEach(function (g) { g.eyes.style.visibility = closed ? 'visible' : 'hidden'; });
    },

    _snapTo: function (idx) {
      this._pose = idx; this._target = idx; this._fadeFrom = -1; this._fadeTo = -1;
      this.groups.forEach(function (g, i) { g.el.style.opacity = i === idx ? '1' : '0'; });
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

      // 轉頭：像真人用脖子轉頭看——大部分時間正對你，偶爾往左或往右轉一點、停一兩秒再轉回來。
      // 轉的方式是換成鄰近角度的圖（正面 → 轉一半 → 轉過去），頭本身完全不變形。
      if (now >= this._nextLook && this._fadeTo < 0) {
        var choices = speaking ? [0, 0, 0, 1, -1] : [0, 0, 1, -1, 2, -2];
        var next = this._target;
        while (next === this._target) next = CENTER + choices[Math.floor(Math.random() * choices.length)];
        this._target = next;
        this._nextLook = now + (next === CENTER ? 2600 + Math.random() * 2600 : 1400 + Math.random() * 1600);
      }
      if (this._fadeTo >= 0) {
        var a = FADE_MS > 0 ? Math.min(1, (now - this._fadeStart) / FADE_MS) : 1;
        this.groups[this._fadeTo].el.style.opacity = a.toFixed(3);
        this.groups[this._fadeFrom].el.style.opacity = (1 - a).toFixed(3);
        if (a >= 1) {
          this._pose = this._fadeTo;
          this._fadeFrom = -1; this._fadeTo = -1;
          this._stepReadyAt = now + HOLD_MS;
        }
      } else if (this._pose !== this._target && now >= this._stepReadyAt) {
        this._fadeFrom = this._pose;
        this._fadeTo = this._pose + (this._target > this._pose ? 1 : -1);
        this._fadeStart = now;
      }

      // 身體：只有呼吸（4.2 秒一次、胸口微微起伏），以畫面底邊為軸；不左右晃
      var br = Math.sin(t * 2 * Math.PI / 4.2);
      this.body.style.transform = 'translateY(' + (-br * 0.2).toFixed(3) + '%) scale('
        + (1 + br * 0.002).toFixed(5) + ',' + (1 + br * 0.004).toFixed(5) + ')';
    },
  };

  window.MuneaFlatFace = F;
})();
