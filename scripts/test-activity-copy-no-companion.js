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
const SYSTEM_PREFIXES = ['activity.', 'demo.', 'book.'];

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
  const m = line.match(/muneaT\(\s*'((?:activity|demo|book)\.[A-Za-z0-9_.]+)'\s*,\s*'([^']*)'/g) || [];
  m.forEach((call) => {
    const parsed = call.match(/muneaT\(\s*'((?:activity|demo|book)\.[A-Za-z0-9_.]+)'\s*,\s*'([^']*)'/);
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

console.log(
  `PASS: 活動文案不掛 AI 名字、不宣稱外撥電話（${LOCALES.length} 語系 × ${SYSTEM_PREFIXES.join('/')}），備援文字同步，無寫死名字`,
);
