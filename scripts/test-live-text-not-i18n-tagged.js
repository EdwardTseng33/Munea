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
 * 有交集、又沒有照下面「現在的規矩」處理的就紅。
 */
const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('web/index.html', 'utf8');
const sources = [html, fs.readFileSync('web/src/app.js', 'utf8')].join('\n');

// 1) index.html 上每個「有 id 又掛 data-i18n」的元素
const tagged = new Map();
const liveTagged = new Set();
for (const match of html.matchAll(/<[^>]+>/g)) {
  const tag = match[0];
  const id = (tag.match(/\bid="([A-Za-z0-9_]+)"/) || [])[1];
  const key = (tag.match(/\bdata-i18n="([^"]+)"/) || [])[1];
  if (id && key) tagged.set(id, key);
  if (id && /\bdata-i18n-live\b/.test(tag)) liveTagged.add(id);
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

/* 2026-11-17：待查清單清完了。
 *
 * 8/1 留下 43 個「掛了 data-i18n、程式又碰得到它的文字」的待查項，三個半月沒人逐一查。
 * 11/17 全部查完（瀏覽器實測＋逐一讀碼），其中三十幾個是真的壞，最嚴重的幾個：
 *   「刪除我的資料」按第一下的「再按一次：永久刪除帳號與資料」被蓋掉，再按一下帳號就沒了；
 *   血壓 168/102 顯示「穩定／正常範圍內」；吃藥提醒視窗的藥名永遠是示範的「脈優」；
 *   趨勢卡永遠寫示範數字；隱私權政策的頁面標題寫「使用條款」。
 *
 * 現在的規矩（三選一，沒有第四種）：
 *   1. 預設那一句本身就不該存在（示範數字、示範藥名、對健康數值下的判斷）
 *      → 拿掉 data-i18n、畫面檔不留預設字，全由程式寫。
 *   2. 預設那一句是對的，但程式會依狀態換字（按鈕的二次確認、進度、名字…）
 *      → 保留 data-i18n，加 data-i18n-live：翻譯層先寫預設，程式一改就歸程式管
 *        （web/src/i18n/dom-localizer.js）。
 *   3. 程式寫的就是同一句、或程式自己在執行時把標籤拔掉 → 列在下面，寫明原因。
 */
const VERIFIED_SAFE = new Map([
  // 陪伴角色的名字與說明：程式在執行時先 removeAttribute('data-i18n') 再寫（app.js 的 NAME_SLOTS）
  ['chatName', '執行時拔標籤'],
  ['companionHomeName', '執行時拔標籤'],
  ['settingsCompanionName', '執行時拔標籤'],
  ['settingsTemplateLabel', '執行時拔標籤'],
  // 純按鍵：程式設的就是同一個翻譯鍵，被蓋回去也是同一句
  ['medAddBtn', '同一句'],
  ['medPhotoBtn', '同一句'],
  // 匯出鍵：另一份綁定清單（app-binding-manifest.json）用不同的鍵寫它，加 live 會讓字變成
  // 「匯出資料副本」。維持現狀＝畫面是審過的「匯出一份給我」，代價只是等待中的「正在整理資料」看不到。
  ['dataExportBtn', '兩份清單用不同鍵；維持審過的文案'],
]);

const offenders = [];
for (const [id, key] of tagged) {
  if (programWritesText(id) && !liveTagged.has(id) && !VERIFIED_SAFE.has(id)) offenders.push(`#${id}（${key}）`);
}
// 例外清單不可以養著過期項目：列在裡面的一定還掛著 data-i18n、而且沒有 data-i18n-live
for (const id of VERIFIED_SAFE.keys()) {
  assert.ok(tagged.has(id), `VERIFIED_SAFE 裡的 #${id} 已經沒有 data-i18n，請從清單移除`);
  assert.ok(!liveTagged.has(id), `VERIFIED_SAFE 裡的 #${id} 已經加了 data-i18n-live，請從清單移除`);
}
// data-i18n-live 只能加在真的掛著 data-i18n 的元素上
for (const id of liveTagged) {
  assert.ok(tagged.has(id), `#${id} 有 data-i18n-live 卻沒有 data-i18n`);
}

assert.deepStrictEqual(
  offenders, [],
  '這些元素的文字由程式依狀態算出來，卻同時掛著 data-i18n——巡邏的翻譯層會把真話蓋回寫死的那一句：\n  '
  + offenders.join('\n  ')
  + '\n修法（看檔頭三選一）：預設那句不該存在就拿掉 data-i18n；預設是對的、只是程式會換字就加 data-i18n-live。',
);

console.log(
  `Live-text guard PASS：掃過 ${tagged.size} 個帶翻譯標籤的元素，`
  + `${liveTagged.size} 個標了 data-i18n-live（程式會換字），`
  + `${VERIFIED_SAFE.size} 個列在已確認安全清單，沒有新的被程式蓋掉的文字`,
);
