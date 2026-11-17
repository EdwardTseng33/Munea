#!/usr/bin/env node
/* 狀態頁「○○的觀察」卡不可以自相矛盾（2026-11-17）
 *
 * 事故：卡片標題下方那行小字「剛剛幫你看過數據」寫死在畫面上。沒接健康裝置時，
 * 上面說「剛剛幫你看過數據」、下一句卻是「還沒接上健康裝置」。
 *
 * 規矩：沒有任何健康資料（沒連，或連了但一項都讀不到）就不顯示那行小字；
 * 真的讀到至少一項、或已經寫出真觀察，才顯示。
 *
 * 做法：把 index.html 裡負責「誠實空值」的那段小程式（window.MMDEV）抽出來，
 * 在沙盒裡用四種狀態真的跑一次，看那行小字顯示不顯示。
 *
 * 跑法：node scripts/test-status-observation-honesty.js
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');

// 畫面上那行小字要有可以被控制的記號，而且就是包著「剛剛幫你看過數據」的那一塊
assert(/<div id="obsReviewed"[^>]*>(?:(?!<\/div>).)*data-i18n="status\.dataReviewed"/.test(html),
  '「剛剛幫你看過數據」那行小字找不到 id="obsReviewed"（沒有記號就沒辦法在沒資料時收起來）');

const start = html.indexOf('window.MMDEV = function(){');
assert(start >= 0, '找不到 window.MMDEV');
const end = html.indexOf('</script>', start);
const mmdevSource = html.slice(start, end);

function run({ states, devicesOn = false, obsReal = '' }) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { id, style: {}, textContent: '', innerHTML: '', offsetParent: null });
    return elements.get(id);
  };
  const sandbox = {
    window: {
      muneaUiT: (key, fallback) => fallback,
      __muneaObsReal: obsReal,
      MuneaHealth: states
        ? { available: () => true, metricStates: () => states }
        : null,
    },
    document: { getElementById: id => element(id) },
    localStorage: { getItem: key => (key === 'munea.devicesOn' && devicesOn ? '1' : null) },
  };
  vm.createContext(sandbox);
  vm.runInContext(mmdevSource + '\nwindow.MMDEV();', sandbox);
  return { reviewed: element('obsReviewed').style.display, obsText: element('obsText').textContent };
}

const all = value => ({ bp: value, hr: value, spo2: value, sleep: value, steps: value });

// 1) 真機、還沒連 Apple 健康
let result = run({ states: all('off') });
assert.strictEqual(result.reviewed, 'none', '沒接健康裝置時還顯示「剛剛幫你看過數據」');
assert(result.obsText.includes('還沒接上健康裝置'), '沒接健康裝置時應該照實說還沒接上');

// 2) 真機、連了但一項都讀不到
result = run({ states: all('empty') });
assert.strictEqual(result.reviewed, 'none', '連了但一項都讀不到時還顯示「剛剛幫你看過數據」');
assert(result.obsText.includes('還讀不到資料'), '連了但讀不到時應該照實說讀不到');

// 3) 真機、至少讀到一項
result = run({ states: Object.assign(all('empty'), { hr: 'ok' }) });
assert.strictEqual(result.reviewed, 'flex', '讀到健康資料後「剛剛幫你看過數據」沒有出現');

// 4) 已經寫出真觀察（app.js 的 __muneaSetHealth 寫的）→ 一定顯示
result = run({ states: all('empty'), obsReal: '今天血壓 <b>118/76</b>，整體狀態不錯。' });
assert.strictEqual(result.reviewed, 'flex', '已經有真觀察時「剛剛幫你看過數據」被收起來了');

// 5) 網頁預覽（沒有原生外掛）：沒按過連接＝沒資料；按過＝示範有資料
assert.strictEqual(run({ states: null, devicesOn: false }).reviewed, 'none', '網頁預覽沒接裝置時還顯示「剛剛幫你看過數據」');
assert.strictEqual(run({ states: null, devicesOn: true }).reviewed, 'flex', '網頁預覽示範有資料時「剛剛幫你看過數據」沒有出現');

console.log('Status observation OK: 沒接裝置／連了讀不到 → 不顯示「剛剛幫你看過數據」；讀到至少一項或已有真觀察 → 顯示（共 6 種狀態實跑）');
