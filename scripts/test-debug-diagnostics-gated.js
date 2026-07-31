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

// 入冊的 debug-panel-diagnostic 條目：該字在 app.js 的每一處都必須（三選一）
// ① 落在 _diag('…') / _diagNote('…') 的「無 force」直呼叫上（字面收尾 ')'、沒接 , true）
// ② 落在 _diag / _diagNote 函式本體內（面板渲染字，例如「臉:」字頭——只有門開才會渲染）
// ③ 落在 AvSyncMeter 區塊內（start() 開頭就有 munea.debug=1 早退門）
const lines = app.split('\n');
function lineHasGatedDiag(line) {
  if (/\._diag(?:Note)?\('[^']*'\)/.test(line)) return true;   // 直呼叫、字面即收尾＝沒有 force 參數
  return (line.includes("._diag('") || line.includes("._diagNote('"))
    && !/\btrue\b/.test(line)
    && !/\bforce\b/.test(line)
    && !/\bmx\s*</.test(line);
}
// 區塊範圍（行號）：大括號深度掃描
function blockLineRange(marker) {
  const idx = app.indexOf(marker);
  assert.ok(idx > 0, `diag block marker not found: ${marker}`);
  let depth = 0;
  let j = app.indexOf('{', idx);
  for (; j < app.length; j += 1) {
    if (app[j] === '{') depth += 1;
    else if (app[j] === '}') { depth -= 1; if (depth === 0) break; }
  }
  const from = app.slice(0, idx).split('\n').length;
  const to = app.slice(0, j).split('\n').length;
  return [from, to];
}
const DIAG_SPANS = [
  blockLineRange('_diag(msg) {'),
  blockLineRange('_diagNote(msg, force) {'),
  blockLineRange('const AvSyncMeter = {'),
];
function lineIndexInDiagSpan(lineNo) {
  return DIAG_SPANS.some(([a, b]) => lineNo >= a && lineNo <= b);
}
// AvSyncMeter 的門必須還在：start() 非 debug 直接早退（拆了門＝條目全失效）
assert(
  /start\(videoEl\) \{[\s\S]{0,200}?localStorage\.getItem\('munea\.debug'\) !== '1'\) return;/.test(app),
  'AvSyncMeter.start must early-return unless munea.debug=1',
);
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
  const hits = [];
  lines.forEach((line, i) => { if (pattern.test(line)) hits.push({ line, no: i + 1 }); });
  if (!hits.length) {
    // 跨行模板字串：清單存的是壓平後的字，逐行對不到 → 用第一段漢字定位原始行
    const fragment = (entry.text.match(/\p{Script=Han}[^\s$]*/u) || [])[0];
    if (fragment) {
      lines.forEach((line, i) => { if (line.includes(fragment)) hits.push({ line, no: i + 1 }); });
    }
  }
  assert.ok(hits.length >= 1, `${entry.id}: text not found`);
  for (const { line, no } of hits) {
    assert.ok(
      lineHasGatedDiag(line) || lineIndexInDiagSpan(no),
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
