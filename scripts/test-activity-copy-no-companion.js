'use strict';

// 活動文案不掛 AI 名字、也不宣稱 AI 會打電話（2026-08-01 Edward「寧寧開獎這種系統文字也要拿掉」）
//
// 兩個問題同一批修的：
//   1. AI 的名字使用者可以改。系統在描述功能時掛名字，換成別的名字就變成
//      「由旺財開獎」——而且開獎其實是程式隨機抽，AI 根本沒參與。
//   2. 更嚴重的是那批文案說「會親口問不方便滑手機的家人」。查過 activity_created
//      只是統計事件，沒有任何一條路會讓 AI 外撥電話——App 對使用者說了一件不會發生的事。
//      真正會發生的是：活動同步到雲端，家庭圈的人打開 App 看得到（syncPullAll 有拉 activities）。
//
// 這支守的是「不要再寫回去」。真的做出外撥功能的那天，把 CALL_CLAIMS 那條拿掉即可。

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const LOCALES = ['zh-TW', 'en', 'ja', 'es'];
const SYSTEM_PREFIXES = ['activity.', 'demo.', 'book.', 'feed.'];

const catalogs = Object.fromEntries(
  LOCALES.map((l) => [l, JSON.parse(fs.readFileSync(path.join(ROOT, 'web/src/i18n', `${l}.json`), 'utf8'))]),
);

// 1) 系統描述功能的文案不掛 AI 名字
const tagged = [];
for (const locale of LOCALES) {
  for (const [key, value] of Object.entries(catalogs[locale])) {
    if (typeof value !== 'string') continue;
    if (!SYSTEM_PREFIXES.some((p) => key.startsWith(p))) continue;
    if (value.includes('{companion}')) tagged.push(`${locale}:${key}`);
  }
}
assert.deepEqual(tagged, [], `活動／示範文案不該掛 AI 名字（名字使用者可改）：${tagged.join(', ')}`);

// 2) 不宣稱 AI 會打電話給家人——這條路不存在
const CALL_CLAIMS = [
  /親口(問|告訴|說)/,                      // zh
  /(口頭|電話で|お電話で).{0,6}(聞|伝え|確認)/, // ja
  /\b(call|phone|ring)s? (them|him|her|family|everyone)\b/i, // en
  /\b(llamar|llamará|telefonear)\b/i,      // es
];
const claims = [];
for (const locale of LOCALES) {
  for (const [key, value] of Object.entries(catalogs[locale])) {
    if (typeof value !== 'string') continue;
    if (!SYSTEM_PREFIXES.some((p) => key.startsWith(p))) continue;
    if (CALL_CLAIMS.some((re) => re.test(value))) claims.push(`${locale}:${key} → ${value}`);
  }
}
assert.deepEqual(claims, [], `活動文案不能說 AI 會打電話問家人（沒有這條路）：\n  ${claims.join('\n  ')}`);

// 3) 程式裡的備援文字也要跟著改——文案表讀不到時顯示的是它
const appJs = fs.readFileSync(path.join(ROOT, 'web/src/app.js'), 'utf8');
const staleFallbacks = [];
appJs.split(/\r?\n/).forEach((line, i) => {
  const m = line.match(/muneaT\(\s*'((?:activity|demo|book|feed)\.[A-Za-z0-9_.]+)'\s*,\s*'([^']*)'/g) || [];
  m.forEach((call) => {
    const parsed = call.match(/muneaT\(\s*'((?:activity|demo|book|feed)\.[A-Za-z0-9_.]+)'\s*,\s*'([^']*)'/);
    if (!parsed) return;
    const [, key, fallback] = parsed;
    if (fallback.includes('{companion}') || CALL_CLAIMS.some((re) => re.test(fallback))) {
      staleFallbacks.push(`app.js:${i + 1} ${key}`);
    }
  });
});
assert.deepEqual(staleFallbacks, [], `備援文字沒跟著改：${staleFallbacks.join(', ')}`);

// 4) 文案表不准寫死預設的 AI 名字（companion.* 本身除外——那裡就是在列名字）
const DEFAULT_NAMES = { 'zh-TW': /寧寧/, ja: /あかり/, en: /\bNina\b/, es: /\bLuc[ií]a\b/ };
const hardcoded = [];
for (const locale of LOCALES) {
  const re = DEFAULT_NAMES[locale];
  for (const [key, value] of Object.entries(catalogs[locale])) {
    if (typeof value !== 'string' || key.startsWith('companion.')) continue;
    if (re.test(value)) hardcoded.push(`${locale}:${key} → ${value}`);
  }
}
assert.deepEqual(hardcoded, [], `文案寫死了 AI 預設名字，改名後會顯示錯的名字：\n  ${hardcoded.join('\n  ')}`);

// 5) 活動結束那句首頁動態要走文案表（2026-11-15）
//
// 以前 announceActEnd() 直接把中文句子塞進家人動態，英日西的首頁就冒出
// 「「Family walking challenge」結束了，收進家庭記錄簿」。這裡守三件事：
//   a. announceActEnd 裡每一則動態都經過 muneaT('feed.…')，沒有再直接串句子；
//   b. 程式裡 feed.* 的備援文字跟 zh-TW 文案表一字不差（讀不到文案表時顯示的是它）；
//   c. 新增的六個鍵四語都有、程式也真的在用，文案表裡沒有沒人用的 feed.*。
const endStart = appJs.indexOf('function announceActEnd(a) {');
const endStop = appJs.indexOf('function updateActEmpty()', endStart);
assert.ok(endStart > 0 && endStop > endStart, 'announceActEnd 必須找得到');
const endBody = appJs.slice(endStart, endStop);
const feedCalls = endBody.match(/pushFamilyFeed\(/g) || [];
assert.ok(feedCalls.length >= 9, 'announceActEnd 的動態出口數量對不上，檢查是否改了結構');
const rawFeed = endBody.split(/\r?\n/).filter((line) => /pushFamilyFeed\(\s*['"`]/.test(line));
assert.deepEqual(rawFeed, [], `活動結束動態不能直接寫死句子，要走 muneaT('feed.…')：\n  ${rawFeed.join('\n  ')}`);

const feedFallbackDrift = [];
const usedFeedKeys = new Set();
for (const m of appJs.matchAll(/muneaT\(\s*'(feed\.[A-Za-z0-9_.]+)'\s*,\s*'([^']*)'/g)) {
  const [, key, fallback] = m;
  usedFeedKeys.add(key);
  if (catalogs['zh-TW'][key] !== fallback) {
    feedFallbackDrift.push(`${key}：程式「${fallback}」≠ 文案表「${catalogs['zh-TW'][key]}」`);
  }
}
assert.deepEqual(feedFallbackDrift, [], `feed.* 備援文字跟 zh-TW 文案表不一致：\n  ${feedFallbackDrift.join('\n  ')}`);
for (const key of ['feed.familyBook', 'feed.quizEnded', 'feed.quizEndedSelf', 'feed.voteEnded', 'feed.eventEndedWent', 'feed.actEnded']) {
  assert.ok(usedFeedKeys.has(key), `${key} 沒有被 app.js 用到`);
  for (const locale of LOCALES) assert.ok(catalogs[locale][key], `${locale}:${key} 缺翻譯`);
}
const unusedFeedKeys = Object.keys(catalogs['zh-TW']).filter((k) => k.startsWith('feed.') && !usedFeedKeys.has(k));
assert.deepEqual(unusedFeedKeys, [], `文案表有 feed.* 但程式沒在用：${unusedFeedKeys.join(', ')}`);

console.log(
  `PASS: 活動文案不掛 AI 名字、不宣稱外撥電話（${LOCALES.length} 語系 × ${SYSTEM_PREFIXES.join('/')}），備援文字同步，無寫死名字`,
);

// 同一類守門（不對使用者說做不到的話）：隱私文字那支掛在這裡一起跑，test:ui-contracts 就會帶到。
// 沒直接加進 package.json 的 test:ui-contracts／test:launch 那兩行，是因為 #694、#696 正在改同兩行、會撞；
// 等它們併了再搬過去。單獨跑：npm run test:privacy-copy。
require('./test-privacy-copy-honest.js');
