#!/usr/bin/env node
/* App 打後端的每一通都要帶「通行碼＋登入證」（2026-11-17）
 *
 * 事故：正式環境的紀錄顯示，下面三支從 App 發出去的請求每一次都被擋（403）——
 *   · 心情趨勢 /wellbeing/trend
 *   · 通知匣 /notifications
 *   · 通知設定 /notifications/settings
 * 後端正式環境有一道薄門：沒帶對 X-Munea-Key 一律 403（engine/server.py do_POST 開頭）。
 *
 * 兩個真因：
 *   1. app.js 的 loadMoodWeekReal() 自己組標頭、只帶 Content-Type，沒走 muneaAuthHeaders()。
 *   2. notify.js 用 `typeof MUNEA_APP_KEY === 'string'` 去借 app.js 的常數——但 app.js 是
 *      <script type="module">，模組最上層的 const 別支程式永遠看不到，所以通行碼「從來沒帶過」
 *      （跟誰先載入無關）。
 *
 * 這支守三件事：
 *   A. 真的執行 loadMoodWeekReal() 與 notify.js 開機那兩通，看送出去的標頭。
 *   B. app.js 裡每個 fetch(brainURL(…)) 都走 muneaAuthHeaders；index.html 不准再裸打後端。
 *   C. 通行碼有三份（app.js／store.js／notify.js）必須相同；一般（非模組）程式不准再去借
 *      MUNEA_APP_KEY 這個別人看不到的名字。
 *
 * 跑法：node scripts/test-app-key-headers.js（不需網路、不需鑰匙）
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const read = relativePath => fs.readFileSync(path.join(root, relativePath), 'utf8');
const app = read('web/src/app.js');
const notify = read('web/src/notify.js');
const store = read('web/src/store.js');
const html = read('web/index.html');

function extract(source, startMarker, stopMarker, label) {
  const start = source.indexOf(startMarker);
  assert(start >= 0, `抽取失敗：找不到 ${label} 的起點`);
  const stop = source.indexOf(stopMarker, start + startMarker.length);
  assert(stop >= 0, `抽取失敗：找不到 ${label} 的終點`);
  return source.slice(start, stop);
}

// ---------- C. 通行碼三份一致 ----------
const appKeyMatch = app.match(/^const MUNEA_APP_KEY = '([^']+)';/m);
const storeKeyMatch = store.match(/^\s*var APP_KEY = '([^']+)';/m);
const notifyKeyMatch = notify.match(/^\s*var APP_KEY = '([^']+)';/m);
assert(appKeyMatch, 'app.js 找不到 MUNEA_APP_KEY 常數（scripts/voice_chain_probe.py 也靠這一行讀）');
assert(storeKeyMatch, 'store.js 找不到自己的 APP_KEY');
assert(notifyKeyMatch, 'notify.js 必須自己帶一份 APP_KEY——它借不到 app.js（模組）裡的常數');
const APP_KEY = appKeyMatch[1];
assert.strictEqual(storeKeyMatch[1], APP_KEY, 'store.js 的通行碼跟 app.js 不同（換鑰匙時漏改）');
assert.strictEqual(notifyKeyMatch[1], APP_KEY, 'notify.js 的通行碼跟 app.js 不同（換鑰匙時漏改）');

// app.js 是模組：它最上層的 const 別支程式看不到。index.html 裡所有「一般」程式都不准再靠那個名字。
assert(/<script type="module" src="src\/app\.js\?v=[^"]+"><\/script>/.test(html),
  'index.html 載入 app.js 的方式變了——請重新確認其他程式拿通行碼的做法還成立');
const classicScripts = [...html.matchAll(/<script src="(src\/[^"?]+\.js)(?:\?[^"]*)?"><\/script>/g)].map(m => m[1]);
assert(classicScripts.includes('src/notify.js') && classicScripts.includes('src/store.js'),
  '抽不到 index.html 的程式清單');
for (const script of classicScripts) {
  const file = path.join(root, 'web', script);
  if (!fs.existsSync(file)) continue;   // auth-config.js 是產生檔、不入庫
  assert(!/\bMUNEA_APP_KEY\b/.test(fs.readFileSync(file, 'utf8')),
    `${script} 用了 MUNEA_APP_KEY：那是 app.js（模組）裡的常數，這支程式永遠拿不到，通行碼會整個沒帶`);
}

// ---------- B. 靜態：每個打後端的 fetch 都要走 muneaAuthHeaders ----------
const brainFetches = [...app.matchAll(/fetch\(brainURL\(/g)];
assert(brainFetches.length >= 6, `app.js 的 fetch(brainURL( 只找到 ${brainFetches.length} 處，抽取規則可能壞了`);
const bare = [];
for (const match of brainFetches) {
  const windowText = app.slice(Math.max(0, match.index - 160), match.index + 320);
  if (!windowText.includes('muneaAuthHeaders(')) {
    bare.push(app.slice(0, match.index).split('\n').length);
  }
}
assert.deepStrictEqual(bare, [], `app.js 第 ${bare.join('、')} 行的 fetch(brainURL(…)) 沒走 muneaAuthHeaders（會被後端 403）`);
assert(/headers\['X-Munea-Key'\] = MUNEA_APP_KEY/.test(extract(app, 'async function muneaAuthHeaders(', '\nasync function companionProfileApi(', 'muneaAuthHeaders')),
  'muneaAuthHeaders 不再帶 X-Munea-Key');
// index.html 的小程式比 app.js 早執行；以前等不到就自己用相對路徑裸打後端（沒通行碼、沒登入證）。
const bareHtmlFetch = html.match(/fetch\(\s*['"]\/(?!\/)[^'"]*['"]/g) || [];
assert.deepStrictEqual(bareHtmlFetch, [], `index.html 還有裸打後端的 fetch：${bareHtmlFetch.join('、')}`);

// ---------- A1. 真的跑 loadMoodWeekReal()，看送出去的標頭 ----------
async function runMoodTrend() {
  const calls = [];
  const sandbox = {
    console,
    window: { MuneaAuth: { async getAccessToken() { return 'access-token-for-test'; } } },
    brainURL: p => 'https://brain.example' + p,
    cacheMyMoodToday() {},
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, async json() { return { daily: [] }; } };
    },
  };
  vm.createContext(sandbox);
  vm.runInContext([
    appKeyMatch[0],
    extract(app, 'async function muneaAuthHeaders(', '\nasync function companionProfileApi(', 'muneaAuthHeaders'),
    extract(app, 'const MOOD_ZH2KEY = {', '\nasync function loadMoodWeekReal(', 'MOOD_ZH2KEY'),
    extract(app, 'async function loadMoodWeekReal(', '\n// 7/16 心情真串接', 'loadMoodWeekReal'),
    'this.__run = loadMoodWeekReal;',
  ].join('\n'), sandbox);
  await sandbox.__run();
  assert.strictEqual(calls.length, 1, '心情趨勢應該只送一通');
  const headers = calls[0].options.headers || {};
  assert.strictEqual(calls[0].url, 'https://brain.example/wellbeing/trend');
  assert.strictEqual(headers['X-Munea-Key'], APP_KEY, '心情趨勢沒帶通行碼 X-Munea-Key（正式環境會 403）');
  assert.strictEqual(headers.Authorization, 'Bearer access-token-for-test', '心情趨勢沒帶登入證');
  assert.strictEqual(headers['Content-Type'], 'application/json');
}

// ---------- A2. 真的跑 notify.js（沒有 app.js 在場），看開機那兩通的標頭 ----------
async function runNotifyBoot() {
  const calls = [];
  const listeners = {};
  const storage = new Map();
  const documentStub = {
    readyState: 'loading',
    visibilityState: 'visible',
    addEventListener(name, handler) { (listeners[name] = listeners[name] || []).push(handler); },
    getElementById() { return null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  const windowStub = {
    MuneaAuth: { async getAccessToken() { return 'access-token-for-test'; } },
    addEventListener() {},
  };
  const sandbox = {
    console,
    window: windowStub,
    document: documentStub,
    localStorage: {
      getItem: key => (storage.has(key) ? storage.get(key) : null),
      setItem: (key, value) => { storage.set(key, String(value)); },
      removeItem: key => { storage.delete(key); },
    },
    AbortController,
    setTimeout,
    clearTimeout,
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, async json() { return { ok: true, settings: { pushEnabled: false, categories: {} }, unreadCount: 0 }; } };
    },
  };
  vm.createContext(sandbox);
  // 注意：這個沙盒裡完全沒有 app.js，也沒有任何叫 MUNEA_APP_KEY 的東西——通行碼必須是 notify.js 自己帶的。
  vm.runInContext(notify, sandbox);
  assert(windowStub.MuneaNotify, 'notify.js 沒有掛出 window.MuneaNotify');
  assert.strictEqual(calls.length, 0, 'notify.js 一載入就發請求了（應該等畫面就緒）');

  (listeners.DOMContentLoaded || []).forEach(handler => handler());
  for (let i = 0; i < 20 && calls.length < 2; i++) await new Promise(resolve => setTimeout(resolve, 5));
  const paths = calls.map(call => call.url);
  assert(paths.includes('/notifications/settings'), `開機沒有讀通知設定（實際：${paths.join('、') || '無'}）`);
  assert(paths.includes('/notifications'), `開機沒有讀通知匣未讀數（實際：${paths.join('、') || '無'}）`);

  await windowStub.MuneaNotify.list({ limit: 5 });
  await windowStub.MuneaNotify.mark('event-1', 'read');
  assert(calls.length >= 4, '通知匣的 list／mark 沒有送出請求');
  for (const call of calls) {
    const headers = call.options.headers || {};
    assert.strictEqual(headers['X-Munea-Key'], APP_KEY, `${call.url} 沒帶通行碼 X-Munea-Key（正式環境會 403）`);
    assert.strictEqual(headers.Authorization, 'Bearer access-token-for-test', `${call.url} 沒帶登入證`);
  }
  return paths;
}

(async () => {
  await runMoodTrend();
  const notifyPaths = await runNotifyBoot();
  console.log(`App key headers OK: ${brainFetches.length} 處 fetch(brainURL(…)) 都走 muneaAuthHeaders；` +
    `心情趨勢帶齊通行碼＋登入證；notify.js 不靠 app.js 也帶得出通行碼（開機：${[...new Set(notifyPaths)].join('、')}）；` +
    '三份通行碼一致；index.html 沒有裸打後端的 fetch');
})().catch(error => {
  console.error('FAIL ' + (error && error.message ? error.message : error));
  process.exit(1);
});
