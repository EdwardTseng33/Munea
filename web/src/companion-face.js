/* 寧寧的臉（2026-10-26 Edward：人物離鏡頭遠一點、頭會自然微動、五官跟著位移、身體有律動）。
   Rive 角色檔做好前的過渡版：一張純色塊寧寧拆成三層——身體／頭（五官處是空白皮膚）／五官——
   再加「微張／張開」兩段嘴與閉眼。每層都是同尺寸的全畫布透明圖，不動時疊起來跟原圖一模一樣。
   蓋在聊聊頁最上層：底下的通話、聲音線路照舊不動。
   動作：身體呼吸起伏＋輕微晃動；頭沿脖子小幅左右擺、輕輕點頭（講話時點得多一點）；
   五官往頭轉的方向多移一點，看起來像真的轉頭；隨機眨眼；講話時嘴巴跟著播出的聲音開合。 */
(function () {
  'use strict';
  var DIR = 'avatars/ningning-rig/';
  var SKIN = {
    bg: '#BADDD6',           // 跟圖的背景同色：手機比圖寬的時候，兩側看不出邊
    zoom: 1,                 // 整張圖佔滿畫面高度；大小比例照原本照片寧寧的視訊構圖
    aspect: 1536 / 2752,
    pivot: [50.9, 50.5],     // 頭轉動的軸心（下巴下緣、脖子上端），以整張圖的百分比計
    waist: 100,              // 身體晃動的軸心高度（畫面底邊）
    layers: {
      body: DIR + 'body.webp', head: DIR + 'head.webp', feat: DIR + 'feat.webp',
      half: DIR + 'mouth-half.webp', open: DIR + 'mouth-open.webp', eyes: DIR + 'eyes-closed.webp',
      front: DIR + 'hair-front.webp',
    },
    faceMask: DIR + 'facemask.png',   // 臉的範圍：五官只准畫在這裡面
  };
  var POLL_MS = 90;          // 問一次「現在播出的聲音多大」的間隔
  var LEVEL_FRESH_MS = 350;  // 超過這麼久沒拿到音量，就改用講話節奏模擬嘴型

  function el(cls, parent) {
    var d = document.createElement('div');
    d.className = cls;
    if (parent) parent.appendChild(d);
    return d;
  }

  var F = {
    root: null, stage: null, body: null, head: null, faceClip: null, feat: null, layer: {}, raf: 0, running: false,
    skin: SKIN,
    // 由 app.js 接上：現在是不是她在講話、目前播出去的音量（0～1；拿不到回 -1）
    speaking: function () { return false; },
    sampleLevel: null,
    _pollTimer: 0, _lvl: -1, _lvlAt: 0, _gainMax: 0.06, _open: 0, _mouth: 'closed', _mouthSince: 0,
    _blinkUntil: 0, _nextBlink: 0, _secondBlinkAt: 0, _syl: 0, _sylUntil: 0, _nod: 0, _still: false,
    _look: 0, _lookVel: 0, _lookTarget: 0, _nextLook: 0,

    mount: function (host) {
      if (this.root || !host) return !!this.root;
      var root = el('flat-face');
      root.id = 'flatFace';
      root.setAttribute('aria-hidden', 'true');
      this.stage = el('ff-stage', root);
      // 桌子不跟著人晃，放在身體後面、固定不動
      this.layer.table = this._img('table', this.stage);
      this.body = el('ff-part ff-body', this.stage);
      this.layer.body = this._img('body', this.body);
      this.head = el('ff-part ff-head', this.body);
      this.layer.head = this._img('head', this.head);
      // 五官跟著頭轉、再往轉的方向多走一點；外面包一層「只露出臉範圍」的遮罩，
      // 跑出臉邊的腮紅、眉尾會藏到頭髮後面，不會畫到頭髮上
      this.faceClip = el('ff-part ff-faceclip', this.head);
      this.feat = el('ff-part ff-feat', this.faceClip);
      // 疊放順序固定：五官 → 嘴 → 閉眼放最後（8/12 眨眼鬼影教訓：覆蓋貼圖一律畫在最上面）
      ['feat', 'half', 'open', 'eyes'].forEach(function (k) { F.layer[k] = F._img(k, F.feat); });
      // 垂在臉上的細髮絲另外一層、疊在五官上面，跟著頭動——橫過眉尾的那縷才不會被眉毛蓋住或斷開
      this.layer.front = this._img('front', this.head);
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
      parent.appendChild(im);
      return im;
    },

    // 換一套角色素材；回傳全部圖片載好的 Promise
    setSkin: function (skin) {
      this.skin = skin;
      if (!this.root) return Promise.resolve();
      this.root.style.background = skin.bg;
      this.stage.style.height = (skin.zoom * 100) + '%';
      this.stage.style.aspectRatio = String(skin.aspect);
      this.head.style.transformOrigin = skin.pivot[0] + '% ' + skin.pivot[1] + '%';
      this.body.style.transformOrigin = '50% ' + (skin.waist || 100) + '%';
      var mask = skin.faceMask ? 'url("' + skin.faceMask + '")' : 'none';
      this.faceClip.style.webkitMaskImage = mask;
      this.faceClip.style.maskImage = mask;
      var self = this;
      return Promise.all(Object.keys(this.layer).map(function (k) {
        return new Promise(function (resolve) {
          var im = self.layer[k];
          im.onload = im.onerror = function () { resolve(); };
          if (skin.layers[k]) { im.src = skin.layers[k]; im.style.display = ''; } else { im.removeAttribute('src'); im.style.display = 'none'; resolve(); }
        });
      }));
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
      var im = this.layer[k];
      // 用顯示／隱藏切換、不用透明度淡入淡出：淡入淡出的那一瞬間會露出兩層疊影
      if (im) im.style.visibility = on ? 'visible' : 'hidden';
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
      this._show('eyes', now < this._blinkUntil);

      if (this._still) return;
      // 身體：只有呼吸（4.2 秒一次、胸口微微起伏），以畫面底邊為軸；不左右晃
      var br = Math.sin(t * 2 * Math.PI / 4.2);
      this.body.style.transform = 'translateY(' + (-br * 0.2).toFixed(3) + '%) scale('
        + (1 + br * 0.002).toFixed(5) + ',' + (1 + br * 0.004).toFixed(5) + ')';
      // 頭：像真人用脖子轉頭看——大部分時間正對你，偶爾往左或往右轉一點、停一兩秒再轉回來。
      // 不歪頭、不來回擺（Edward 10/26：頭不要這樣晃動，脖子左轉一點、右轉一點）。
      if (now >= this._nextLook) {
        var choices = speaking ? [0, 0, 0.7, -0.7] : [0, 0, 0.7, -0.7, 1, -1];
        var next = this._lookTarget;
        while (next === this._lookTarget) next = choices[Math.floor(Math.random() * choices.length)];
        this._lookTarget = next;
        this._nextLook = now + (next === 0 ? 2600 + Math.random() * 2600 : 1400 + Math.random() * 1600);
      }
      // 轉過去的速度用臨界阻尼的彈簧：起步和停下都是緩的，約 0.6 秒到位、不會晃過頭
      var ds = dt / 1000, w = 7.5;
      this._lookVel += (w * w * (this._lookTarget - this._look) - 2 * w * this._lookVel) * ds;
      this._look += this._lookVel * ds;
      var look = this._look, mag = Math.abs(look);
      var nodTarget = speaking ? this._open : 0;
      this._nod += (nodTarget - this._nod) * (1 - Math.exp(-dt / 160));
      // 轉頭：整顆頭（頭髮、髮絲、五官一體）往轉的方向移，遠的那一側稍微收窄——像臉真的轉過去。
      // 五官不再相對頭移動：多移一點點就會讓橫過眉尾的髮絲斷開（Edward 10/26 圈出左眉）。
      var px = this.skin.pivot[0] + (look > 0 ? 1 : -1) * 14;
      this.head.style.transformOrigin = px.toFixed(2) + '% ' + this.skin.pivot[1] + '%';
      this.head.style.transform = 'translate(' + (look * 1.2).toFixed(3) + '%,' + (this._nod * 0.2).toFixed(3) + '%) scaleX('
        + (1 - mag * 0.045).toFixed(4) + ')';
    },
  };

  window.MuneaFlatFace = F;
})();
