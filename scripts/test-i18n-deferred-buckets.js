'use strict';
// 證據測試：四類「暫不進翻譯目錄」的字，各自的『門／出口』真的存在。
// docs/I18N-NON-USER-FACING-REVIEW.json 引用本檔作為下列 reasonCode 的證據；
// 本檔若失敗＝該類的前提被拆了，對應條目全部失效、必須重新審核。
//
// 1) zh-intent-matcher —— 中文語音/文字指令的比對式與回話。整包活在聊天區
//    （CHAT_RULES → parseChatIntent → chatHandle 的前半），只有聽懂中文指令才會回；
//    分語言的指令設計是獨立議題（見 i18n 交付計畫），不是漏翻。
// 2) family-feed-recipient-locale —— 寫進家人動態牆的句子。牆上內容存庫後發給
//    每個家人，「照收件人語言呈現」是後端 Phase 2b 的工作；前端先翻反而會把
//    存庫內容綁死在發文者語言。所有此類字必須落在 pushFamilyFeed(...) 呼叫範圍
//    或其固定的取名支援行上。
// 3) backend-template-identity（本檔補充組）—— 送往後端／語音引擎的載荷字
//    （意見箱分類、檢舉前綴、系統悄悄話）。收件端是中文營運台或當前中文語音腦。
// 4) brand-proper-noun —— 「沐寧 Munea」品牌專名（報告紙本頁首尾）。專有名詞
//    不進翻譯目錄；程式碼內備有明示註解。
const assert = require('assert');
const fs = require('fs');

const app = fs.readFileSync('web/src/app.js', 'utf8');
const review = JSON.parse(fs.readFileSync('docs/I18N-NON-USER-FACING-REVIEW.json', 'utf8'));
const appLines = app.split('\n');

function entriesOf(code) {
  return review.entries.filter((e) => e.reasonCode === code);
}
function escapeRe(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
function lineNumbersOf(text) {
  const out = [];
  const pattern = new RegExp(escapeRe(text));
  appLines.forEach((line, i) => { if (pattern.test(line)) out.push(i + 1); });
  return out;
}
function blockRanges(marker, open, close) {
  const ranges = [];
  let idx = 0;
  for (;;) {
    idx = app.indexOf(marker, idx);
    if (idx < 0) break;
    let depth = 0;
    let j = app.indexOf(open, idx);
    for (; j < app.length; j += 1) {
      if (app[j] === open) depth += 1;
      else if (app[j] === close) { depth -= 1; if (depth === 0) break; }
    }
    ranges.push([app.slice(0, idx).split('\n').length, app.slice(0, j).split('\n').length]);
    idx = j;
  }
  return ranges;
}

// ── 1) 中文指令區的門 ───────────────────────────────────────────
const chatStartIdx = app.indexOf('const CHAT_RULES = [');
const chatEndIdx = app.indexOf('const acted = parseChatIntent(t);');
assert.ok(chatStartIdx > 0 && chatEndIdx > chatStartIdx, 'chat-intent zone markers must exist in order');
const chatStartLine = app.slice(0, chatStartIdx).split('\n').length;
const chatEndLine = app.slice(0, chatEndIdx).split('\n').length;
// parseChatIntent 只有聊天線在叫（定義 1 + 測試鉤 1 + chatHandle 1）
assert.equal((app.match(/parseChatIntent\(/g) || []).length, 3, 'parseChatIntent must stay a chat-lane-only helper');
for (const entry of entriesOf('zh-intent-matcher')) {
  assert.equal(entry.path, 'web/src/app.js', `${entry.id} must point at app.js`);
  const hits = lineNumbersOf(entry.text);
  assert.ok(hits.length >= 1, `${entry.id}: text not found`);
  // 同字可能在圈外另有「已綁」的用法（例：上午＝common.am 的備援）；
  // 未綁位置的逐筆對帳由 surface-inventory 契約負責，這裡守「圈內確實存在」。
  assert.ok(
    hits.some((no) => no >= chatStartLine && no <= chatEndLine),
    `${entry.id}: "${entry.text}" has no occurrence inside the chat-intent zone [${chatStartLine}-${chatEndLine}]`,
  );
}

// ── 2) 家人動態牆的出口 ─────────────────────────────────────────
const feedRanges = blockRanges('pushFamilyFeed(', '(', ')');
assert.ok(feedRanges.length >= 5, 'pushFamilyFeed call sites must be locatable');
const FEED_SUPPORT = ["danger.push('", "let who = '家人'", 'who = pf.nick', 'function myFeedName', "getElementById('ptName')?.textContent"];
for (const entry of entriesOf('family-feed-recipient-locale')) {
  assert.equal(entry.path, 'web/src/app.js', `${entry.id} must point at app.js`);
  const hits = lineNumbersOf(entry.text);
  assert.ok(hits.length >= 1, `${entry.id}: text not found`);
  assert.ok(
    hits.some((no) => {
      const line = appLines[no - 1];
      return feedRanges.some(([a, b]) => no >= a && no <= b) || FEED_SUPPORT.some((s) => line.includes(s));
    }),
    `${entry.id}: "${entry.text}" has no occurrence inside a pushFamilyFeed call`,
  );
}

// ── 3) 後端載荷（本檔補充組：意見箱／檢舉／語音悄悄話）────────────
for (const entry of entriesOf('backend-template-identity')) {
  if (entry.evidence !== 'scripts/test-i18n-deferred-buckets.js') continue;
  const hits = lineNumbersOf(entry.text);
  assert.ok(hits.length >= 1, `${entry.id}: text not found`);
  assert.ok(
    hits.some((no) => {
      const line = appLines[no - 1];
      return line.includes("brainPost('/feedback'") || line.includes('LiveVoice.ws.send') || line.includes('dataset.c');
    }),
    `${entry.id}: "${entry.text}" has no occurrence on a backend payload line`,
  );
}

// ── 4) 品牌專名 ────────────────────────────────────────────────
assert.ok(app.includes('品牌名是專有名詞，不進 i18n'), 'brand proper-noun comment marker must stay');
for (const entry of entriesOf('brand-proper-noun')) {
  const hits = lineNumbersOf(entry.text);
  assert.ok(hits.length >= 1, `${entry.id}: brand text not found`);
}

// ── 5) 存庫代號的顯示拆分器（本檔補充組）────────────────────────
// 中文代號可以留在存庫與比對式裡的前提：畫面呈現走「代號 → 翻譯鍵」的
// 拆分器。拆分器被拆掉＝代號會裸奔上畫面，此類條目全部失效。
for (const gate of [
  'function moodDayShort(',           // 心情週圖的星期軸
  'const MOOD_WEEKDAY_KEYS = {',
  'function interestTopicLabel(',     // 興趣籤顯示
  'function localizedMedicationDuration(', // 用藥天數顯示
  'function medSlotLabel(',           // 用藥時段顯示
  'function actDisplayName(',         // 活動名單裡的「你」
  'const MOOD_ZH2KEY = {',            // 聊天觀察心情詞 → 鍵
]) {
  assert.ok(app.includes(gate), `storage-token display splitter missing: ${gate}`);
}
const html = fs.readFileSync('web/index.html', 'utf8');
for (const gate of ['function moodLabel(i){ return MOODS[i].label(); }', 'function weekdayLabel(date']) {
  assert.ok(html.includes(gate), `inline display splitter missing: ${gate}`);
}
for (const entry of entriesOf('legacy-storage-identity')) {
  if (entry.evidence !== 'scripts/test-i18n-deferred-buckets.js') continue;
  const source = entry.path === 'web/index.html' ? html : app;
  assert.ok(source.includes(entry.text), `${entry.id}: token text not found in ${entry.path}`);
}

console.log(
  'Deferred-bucket evidence PASS: '
  + `${entriesOf('zh-intent-matcher').length} zh-intent, `
  + `${entriesOf('family-feed-recipient-locale').length} family-feed, `
  + `${entriesOf('brand-proper-noun').length} brand entries verified`,
);
