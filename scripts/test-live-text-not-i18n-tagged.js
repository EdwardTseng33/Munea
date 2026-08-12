#!/usr/bin/env node
/* 程式會改寫的文字，不可以同時掛 data-i18n（2026-08-01 一天踩三次）
 *
 * 畫面上有一個一直在巡邏的翻譯層（web/src/i18n/dom-localizer.js 的 MutationObserver）：
 * 只要有節點被重新加進畫面，它就對帶 data-i18n 的元素**無條件**套用翻譯值
 * （`if (node.textContent !== value) node.textContent = value;`）。
 *
 * 所以「程式依狀態算出來的文字」＋「data-i18n」放在同一個元素上，結果永遠是後者贏，
 * 而且是在使用者眼前被蓋回去。同一天踩到三次：
 *   早上　蘋果健康：程式有四種說法，畫面永遠寫「目前未同步」
 *   下午　情緒卡　：點「愉悅」，上面永遠停在「平靜」
 *   傍晚　用藥卡　：還沒設定用藥，程式要顯示「去設定 ›」，畫面卻寫「尚未服用」
 *
 * 這支測試把 index.html 上「掛了 data-i18n」與「程式會改它文字」的元素對一次，
 * 有交集就紅。修法一律是拿掉 data-i18n，翻譯改走程式裡的 t()／muneaUiT()，
 * 切語言時靠 munea:locale-ready 重畫。
 */
const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('web/index.html', 'utf8');
const sources = [html, fs.readFileSync('web/src/app.js', 'utf8')].join('\n');

// 1) index.html 上每個「有 id 又掛 data-i18n」的元素
const tagged = new Map();
for (const match of html.matchAll(/<[^>]+>/g)) {
  const tag = match[0];
  const id = (tag.match(/\bid="([A-Za-z0-9_]+)"/) || [])[1];
  const key = (tag.match(/\bdata-i18n="([^"]+)"/) || [])[1];
  if (id && key) tagged.set(id, key);
}
assert.ok(tagged.size > 20, '沒抓到帶 data-i18n 的元素，這支測試的偵測方式壞了');

// 2) 程式有沒有把它抓出來、然後改它的文字
const escaped = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function programWritesText(id) {
  const grab = new RegExp(
    `(?:getElementById\\(['"]${escaped(id)}['"]\\)|\\$\\(['"]#${escaped(id)}['"]\\))`,
    'g',
  );
  for (const hit of sources.matchAll(grab)) {
    // 直接接 .textContent = ／.innerHTML =
    const tail = sources.slice(hit.index, hit.index + 120);
    if (/^\s*\)?\s*\.(?:textContent|innerHTML)\s*=/.test(tail.slice(hit[0].length))) return true;
    // 或先存進變數，同一段程式裡再寫它（例：var chip=document.getElementById('medChip'); chip.textContent=…）
    // 注意 hit.index 指向 getElementById，所以往前看的那段結尾是「var chip=document.」而不是「=」
    const assigned = sources
      .slice(Math.max(0, hit.index - 60), hit.index)
      .match(/(?:var|let|const)\s+([A-Za-z0-9_]+)\s*=\s*(?:document\.)?$/);
    if (assigned) {
      const varName = assigned[1];
      const near = sources.slice(hit.index, hit.index + 2000);
      if (new RegExp(`\\b${escaped(varName)}\\s*\\.(?:textContent|innerHTML)\\s*=`).test(near)) return true;
    }
  }
  return false;
}

/* 已知待查清單（2026-08-01 建立）
 *
 * 這 43 個都「掛了 data-i18n，而且程式碰得到它的文字」，但**不見得每個都壞**：
 * 很多是程式設的值剛好等於同一個翻譯鍵（例如 restoreBtn 設的就是 purchase.restore），
 * 那只是重複、不會出錯。真正會壞的是「程式依狀態給不同文字」的那種。
 *
 * 已經確認壞掉並修好的三個（不在清單裡）：
 *   cnHealthHelp／moodLabel 系列／medChip／authStatusText／callToggleLabel
 *
 * 這份清單的作用是**擋新增**：以後有人再把 data-i18n 掛到程式會改的元素上，
 * 這支會立刻紅。清單裡的舊項目要逐一人工確認「程式設的值會不會跟翻譯值不同」，
 * 確認安全就從清單移除也行、確認會壞就比照修法拿掉標籤。
 */
const KNOWN_SUSPECTS = new Set([
  'actChip', 'bpChip', 'bpSub', 'busyCardTitle', 'chatCaption', 'chatName',
  'companionHomeName', 'dataDeleteBtn', 'dataExportBtn', 'eventTaskTitle', 'fbTextLabel',
  'fcInviteBtn', 'fcLeaveBtn', 'goalHint', 'hrChip', 'hrSub', 'invLimitNote', 'inviteNote',
  'joinCircleBtn', 'managePlanBtn', 'medDueDesc', 'medDueName', 'medDueSay',
  'medTrendChip', 'moodTitle', 'npsWord', 'obsPeriod', 'pageTitle', 'pillTitle',
  'planCancelBtn', 'ptAv', 'quizNVal', 'quizProgress', 'rcHint', 'rcTitle', 'readerTitle',
  'restoreBtn', 'settingsCompanionName', 'settingsTemplateLabel', 'sleepTrendChip',
  'visitTaskTitle', 'walkGoalVal',
  // 這兩顆是純按鍵：程式設的就是同一個翻譯鍵，被蓋回去也是同一句、不會出錯
  'medAddBtn', 'medPhotoBtn',
]);

const offenders = [];
for (const [id, key] of tagged) {
  if (programWritesText(id) && !KNOWN_SUSPECTS.has(id)) offenders.push(`#${id}（${key}）`);
}

assert.deepStrictEqual(
  offenders, [],
  '這些元素的文字由程式依狀態算出來，卻同時掛著 data-i18n——巡邏的翻譯層會把真話蓋回寫死的那一句：\n  '
  + offenders.join('\n  ')
  + '\n修法：拿掉 data-i18n，翻譯改用程式裡的 t()／muneaUiT()，切語言時靠 munea:locale-ready 重畫。',
);

console.log(
  `Live-text guard PASS：掃過 ${tagged.size} 個帶翻譯標籤的元素，`
  + `沒有新的被程式改寫文字（${KNOWN_SUSPECTS.size} 個舊的在待查清單裡）`,
);
