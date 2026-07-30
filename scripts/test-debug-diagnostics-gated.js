'use strict';
// 證據測試：兩類「非用戶文案」的門真的存在。
// 1) debug-panel-diagnostic —— _diag / _diagNote 的診斷字只在 munea.debug=1 顯示
//    （_diagNote 帶 force 的呼叫點不在此類、不得入冊）。
// 2) developer-fixture —— 示範資料只在開發設定 seedFixtures=true 時寫入。
// docs/I18N-NON-USER-FACING-REVIEW.json 引用本檔作為這兩類條目的證據；
// 本檔若失敗，代表門被拆了，對應條目全部失效、必須重新審核。
const assert = require('assert');
const fs = require('fs');

const app = fs.readFileSync('web/src/app.js', 'utf8');
const css = fs.readFileSync('web/src/styles.css', 'utf8');
const review = JSON.parse(fs.readFileSync('docs/I18N-NON-USER-FACING-REVIEW.json', 'utf8'));

// ── 1) 診斷小窗的門 ─────────────────────────────────────────────
const diagBody = app.slice(app.indexOf('_diag(msg)'), app.indexOf('_diagNote(msg, force)'));
assert(
  /localStorage\.getItem\('munea\.debug'\) !== '1'\) return;/.test(diagBody),
  '_diag must early-return unless munea.debug=1',
);
const diagNoteBody = app.slice(app.indexOf('_diagNote(msg, force)'), app.indexOf('wake()'));
assert(
  diagNoteBody.includes("localStorage.getItem('munea.debug') === '1'"),
  '_diagNote must show the panel only in debug mode (or explicit force)',
);
assert(
  /body:not\(\.debug\) \.ai-dev-panel \{ display: none !important; \}/.test(css),
  'the developer panel must stay hidden outside debug mode',
);

// 入冊的 debug-panel-diagnostic 條目：該字在 app.js 的每一處都必須落在
// _diag('…') 或 _diagNote('…')（無 force 參數）呼叫行上。
const lines = app.split('\n');
// 與入冊產生器共用的同一條「有門」判定：行內必須是 _diag / _diagNote 呼叫，
// 且不得出現 force 直開跡象（`, true` / force 變數 / mx 門檻式）——那些故障時
// 會真的跳給使用者看、不屬於本類。
function lineHasGatedDiag(line) {
  return (line.includes("._diag('") || line.includes("._diagNote('"))
    && !/\btrue\b/.test(line)
    && !/\bforce\b/.test(line)
    && !/\bmx\s*</.test(line);
}
// 清單記的是頭尾去空白後的字；原始碼可能是「'線路 '」這種帶尾空白的字面，
// 也可能是反引號模板字串。
function literalPattern(text, flags) {
  const esc = text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`['\`]\\s*${esc}\\s*['\`]`, flags);
}
for (const entry of review.entries) {
  if (entry.reasonCode !== 'debug-panel-diagnostic') continue;
  assert.equal(entry.path, 'web/src/app.js', `${entry.id} must point at app.js`);
  const pattern = literalPattern(entry.text);
  const hits = lines.filter((line) => pattern.test(line));
  assert.ok(hits.length >= 1, `${entry.id}: text not found`);
  for (const line of hits) {
    assert.ok(
      lineHasGatedDiag(line),
      `${entry.id}: "${entry.text}" appears outside a gated _diag/_diagNote call`,
    );
  }
}

// ── 2) 開發示範資料的門 ─────────────────────────────────────────
assert(
  app.includes('function seedDeveloperFixtures(cfg) {\n  if (cfg.seedFixtures !== true) return;'),
  'seedDeveloperFixtures must refuse to run without the developer flag',
);
const fixtureStart = app.indexOf('function developerFixtureVitals');
const fixtureEnd = app.indexOf('\nfunction ', app.indexOf('function seedDeveloperFixtures'));
assert(fixtureStart > 0 && fixtureEnd > fixtureStart, 'developer fixture block must be locatable');
const fixtureBlock = app.slice(fixtureStart, fixtureEnd);
for (const entry of review.entries) {
  if (entry.reasonCode !== 'developer-fixture') continue;
  assert.equal(entry.path, 'web/src/app.js', `${entry.id} must point at app.js`);
  const pattern = literalPattern(entry.text, 'g');
  const total = (app.match(pattern) || []).length;
  const inBlock = (fixtureBlock.match(pattern) || []).length;
  assert.ok(total >= 1, `${entry.id}: text not found`);
  assert.equal(
    total,
    inBlock,
    `${entry.id}: "${entry.text}" also appears outside the developer fixture block`,
  );
}

console.log('PASS: debug diagnostics and developer fixtures stay gated away from real users');
