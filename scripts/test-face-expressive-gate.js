#!/usr/bin/env node
/* 寧寧多嘴型＋表情（2026-11-21 草稿）守門：開關預設關＝跟以前一模一樣。
   1. 開關關：聊聊頁只載原本 4 張圖（不多要 7 張貼片），嘴型只有閉／微張／張開
   2. 開關開但角色沒有貼片（沐沐）：一樣只載 4 張、不會有 7 個找不到圖的請求
   3. 開關開＋寧寧：載 11 張，嘴型照母音選
   4. app.js：開關只認 localStorage munea.faceExpressive === '1'；只有寧寧標 expressive；
      嘴型驅動器用到才載（index.html 不直接引用）；表情事件／量聲音都先看開關 */
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..');
const WEB = path.join(ROOT, 'web');
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8');

// ---- 迷你假 DOM：只夠 companion-face.js 掛上去、換圖 ----
const requested = [];
function fakeEl() {
  const el = {
    style: {}, children: [], className: '', attrs: {},
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; if (k === 'src') this._src = ''; },
    closest() { return null; },
  };
  Object.defineProperty(el, 'src', {
    get() { return this._src || ''; },
    set(v) {
      this._src = v; requested.push(v);
      const ok = fs.existsSync(path.join(WEB, v.split('?')[0]));
      setImmediate(() => { const cb = ok ? this.onload : this.onerror; if (cb) cb(); });
    },
  });
  return el;
}
global.window = global;
global.document = { createElement: () => fakeEl(), querySelector: () => null };
global.performance = global.performance || { now: () => Date.now() };
global.requestAnimationFrame = () => 0;
global.cancelAnimationFrame = () => {};
global.matchMedia = () => ({ matches: false });
eval(read('web/src/companion-face.js'));
const F = window.MuneaFlatFace;
F.mount(fakeEl());

const NEW_PARTS = /mouth-(ee|oo|oh|smile)|eyes-(smile|soft)|brows-concern/;
const NING = { dir: 'avatars/ningning-rig/', bg: '#BADDD6', aspect: 1536 / 2752, expressive: true };
const MUMU = { dir: 'avatars/mumu-rig/', bg: '#F6EBD7', aspect: 1536 / 2752, expressive: false };

(async () => {
  // 1. 預設關
  assert.strictEqual(F.expressive, false, '開關預設要關');
  requested.length = 0;
  await F.setSkin(NING);
  assert.strictEqual(requested.filter(u => NEW_PARTS.test(u)).length, 0, '開關關：不准多載貼片');
  assert.strictEqual(requested.length, 4, '開關關：只載原本 4 張');
  for (const shape of ['a', 'e', 'i', 'o', 'u', 'sib']) {
    for (const open of [0.2, 0.5, 0.9]) {
      assert.ok(['closed', 'half', 'open'].includes(F._mouthFor(shape, open)), `開關關：${shape}/${open} 只能用原本三段嘴`);
    }
  }

  // 2. 開關開＋沐沐
  F.expressive = true;
  requested.length = 0;
  await F.setSkin(MUMU);
  assert.strictEqual(requested.filter(u => NEW_PARTS.test(u)).length, 0, '沐沐沒有貼片：不准去要那 7 張圖');
  assert.ok(Object.values(F._has).every(v => v === false), '沐沐：多的嘴型都要記成沒有');

  // 3. 開關開＋寧寧
  requested.length = 0;
  await F.setSkin(NING);
  assert.strictEqual(requested.filter(u => NEW_PARTS.test(u)).length, 7, '開關開＋寧寧：7 張貼片都要載');
  assert.ok(Object.values(F._has).every(v => v === true), '寧寧的 7 張貼片都要在 web/avatars/ningning-rig/');
  assert.strictEqual(F._mouthFor('i', 0.6), 'ee');
  assert.strictEqual(F._mouthFor('u', 0.6), 'oo');
  assert.strictEqual(F._mouthFor('sil', 0.9), 'closed');

  // 4. app.js 接線
  const app = read('web/src/app.js');
  assert.match(app, /localStorage\.getItem\('munea\.faceExpressive'\) === '1'/, '開關只認 munea.faceExpressive === 1');
  assert.match(app, /face\.expressive = faceExpressiveOn\(\);\s*\n\s*FaceViseme\.on = face\.expressive;\s*\n\s*face\.setSkin\(/, '進聊聊頁要先定開關再換圖');
  assert.match(app, /if \(FaceViseme\.on\) FaceViseme\.ensure\(\);/, '量聲音那條分支要先看開關');
  assert.match(app, /expression\(expr\) \{\s*\n\s*if \(!this\.on\) return;/, '表情事件要先看開關');
  assert.match(app, /expressive: !!s\.expressive/, 'flatSkinFor 要把角色有沒有貼片帶給臉');
  const profile = read('web/src/companion-profile.js');
  assert.strictEqual((profile.match(/expressive: true/g) || []).length, 1, '目前只有寧寧有表情貼片');
  assert.ok(!/lipsync-driver/.test(read('web/index.html')), '嘴型驅動器用到才載，index.html 不直接引用');
  for (const f of ['mouth-ee', 'mouth-oo', 'mouth-oh', 'mouth-smile', 'eyes-smile', 'eyes-soft', 'brows-concern']) {
    assert.ok(!fs.existsSync(path.join(WEB, 'avatars/mumu-rig', f + '.webp')) || /mumu-flat-male[\s\S]*expressive: true/.test(profile),
      '沐沐補了貼片就要在 companion-profile 標 expressive');
  }
  console.log('Face expressive gate PASS：預設關只載 4 張、沐沐不多要圖、寧寧開了才載 7 張貼片並照母音選嘴');
})().catch(e => { console.error('Face expressive gate FAIL：' + e.message); process.exit(1); });
