#!/usr/bin/env node
/* 就診摘要 UI（M1 · PR-4c）——接線與紅線契約。
 *
 * 後端組裝已由 engine/test_visit_summary*.py 顧到；這支顧的是「畫面這一層會不會出事」：
 *
 *   ① 入口真的存在（前一版那個面板就是死在「按鈕不存在」——#reportBtn 全專案沒有，
 *      面板永遠打不開，而且沒有任何測試抓得到。這支就是那個教訓的守門員。）
 *   ② 畫面不得出現判定字眼或警示色（後端守一遍，畫面再守一遍——
 *      加一個紅色驚嘆號就等於我們在說「這個不正常」）
 *   ③ 來源圖例必須在（醫師要能分辨自述 vs 量測）
 *   ④ 截斷與部分資料要顯示出來，不可悄悄少一塊
 *   ⑤ 沒有「子女代為新增」的入口（Edward 2026-07-28：降低子女負擔，不是給他做工的工具）
 *   ⑥ 使用者文字一律逸出後才進 innerHTML（口袋問題是使用者輸入）
 *
 * 跑法：node scripts/test-visit-summary-ui.js
 */
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web', 'src', 'app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'web', 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'web', 'src', 'styles.css'), 'utf8');
const server = fs.readFileSync(path.join(root, 'engine', 'server.py'), 'utf8');

let passed = 0;
function expect(condition, message) {
  if (!condition) throw new Error(message);
  passed += 1;
}
function ok(label) { console.log('PASS ' + label); }

/* ① 入口存在——這一版最重要的一條 */
expect(html.includes('id="reportModal"'), '① 摘要面板不見了');
expect(!app.includes("$('#reportBtn')"), '① 還在綁不存在的 #reportBtn（就是上一版死掉的原因）');
expect(app.includes("item.dataset.task === 'visit'") && app.includes("openVisitSummary('daily-task')"),
  '① 今天的看診任務卡沒有接到摘要');
expect(app.includes("if ($('#visitSummaryRow'))"), '① 設定頁入口沒接');
expect(html.includes('id="visitSummaryRow"'), '① 設定頁那一列不存在');
// 每一個被綁的 id 都必須真的在 HTML 裡——這正是上一版沒人抓到的洞
['rptExportBtn', 'rptPeriodTabs', 'rptBody', 'rptPeriodLine', 'reportClose']
  .forEach(id => expect(html.includes('id="' + id + '"'), `① app.js 綁了 #${id}，但 HTML 裡沒有這個元素`));
ok('① 入口與所綁元素全部存在（含上一版死因的回歸測試）');

/* ①b 版型必須吃既有子頁規範（Edward 2026-07-29：「不要自己創一個新的」）*/
const reportBlock = html.slice(html.indexOf('id="reportModal"') - 200, html.indexOf('id="fontModal"'));
expect(/class="reader-page sub-page"[^>]*id="reportModal"/.test(html),
  '①b 就診摘要不是 reader-page 子頁——又變回底部彈窗了');
expect(!/modal-mask[^>]*id="reportModal"/.test(html), '①b 還掛著 modal-mask（彈窗遺留）');
['nav-head', 'nav-back', 'nav-title', 'reader-scroll', 'seg']
  .forEach(cls => expect(reportBlock.includes(cls), `①b 子頁少了既有規範元件 .${cls}`));
// 渲染出來的內容也要用既有 class，不可以又長出一套自訂版型
['set-section', 'set-list', 'set-row', 'reader-card']
  .forEach(cls => expect(app.includes(`"${cls}` ) || app.includes(`'${cls}`) || app.includes(`class="${cls}`),
    `①b 渲染沒有用既有 class .${cls}`));
expect(!app.includes('rpt-sec') && !app.includes('rpt-q-n') && !app.includes('rpt-tl'),
  '①b app.js 還在用改版前那套自訂 .rpt-* 版型');
expect(!css.includes('.rpt-sec') && !css.includes('.rpt-addq'),
  '①b styles.css 還留著改版前那套自訂 .rpt-* 樣式');
ok('①b 版型吃既有子頁規範（nav-head／set-section／set-list／seg／reader-card）');

/* ①c 「看完醫生了」整顆拿掉——這一頁是歷史資料，不是待辦事項 */
expect(!html.includes('rptDoneBtn'), '①c「看完醫生了」還在版型裡');
expect(!app.includes('rptDoneBtn'), '①c app.js 還綁著「看完醫生了」');
expect(app.includes('autoArchiveCareQuestions'), '①c 拿掉按鈕後沒有接自動歸檔，問題會永遠提醒同一題');
ok('①c 拿掉「看完醫生了」，改為看診日過了自動歸檔');

/* ①d 開頁不得再出現「整理中」——資料在本機就先畫（Edward 2026-07-29）*/
expect(app.includes('buildLocalVisitSummary'), '①d 沒有本機先組一份，開頁又會空白');
expect(!app.includes("visit.preparing"), '①d 還留著「整理中…」那條路');
expect(app.includes('timelinePending'), '①d 時間軸沒有「還在讀」狀態');
expect(app.includes('timelineFailed'), '①d 時間軸沒有「讀不到」狀態');
// 「還在讀」跟「沒事發生」必須是兩個不同狀態，講反了醫師會以為他這段期間都好好的
expect(app.indexOf('visit.timelineLoading') > 0 && app.indexOf('visit.timelineEmpty') > 0,
  '①d 讀取中與真的沒事共用同一句文案');
ok('①d 開頁用本機資料先畫，不再有「整理中」');

/* ①e 診間安全：把手機遞給醫生時，畫面不該有一排「刪除」等著被誤觸。
   刪除鍵藏在「編輯」後面，而且每次重開都回到閱讀狀態。 */
expect(app.includes('_rptEditing'), '①e 沒有閱讀／編輯兩種狀態，刪除鍵會一直露在外面');
expect(/_rptEditing\s*\?[\s\S]{0,200}vs-del/.test(app),
  '①e 刪除鍵沒有被 _rptEditing 包住＝診間也看得到，醫生捲頁可能誤刪');
expect(/_rptEditing = false;[\s\S]{0,200}autoArchiveCareQuestions/.test(app),
  '①e 重開摘要時沒有回到閱讀狀態，上次整理完的編輯模式會殘留到診間');
expect(css.includes('.vs-del') && /\.vs-del[^}]*min-height: 44px/.test(css),
  '①e 刪除鍵點擊區小於 44px，長輩按不準');
// 用「刪除」兩個字而不是 ✕ 圖示：長輩讀得懂字、猜不出圖示，刪除又不可逆
expect(app.includes("muneaT('common.delete'"), '①e 刪除鍵用圖示而非文字');
ok('①e 診間是乾淨的閱讀狀態，刪除鍵收在「編輯」後面且點擊區夠大');

/* ①f 字級要照規範——這一頁是給長輩在診間唸給醫生聽的，縮小字等於白做。
   規範（styles.css :root）寫明「內文 17」，.set-row 就是 17px。 */
expect(/questions\.forEach[\s\S]{0,400}class="set-row"/.test(app),
  '①f 問題列沒有用 .set-row（17px 內文字級），自己縮成小字了');
expect(/questions\.forEach[\s\S]{0,400}sr-main/.test(app), '①f 問題文字沒有走 .sr-main');
ok('①f 問題列吃規範的內文字級（.set-row 17px），不自己縮小');

/* ①g 只留 60 天——跟天數選項的上限一致，超過就再也顯示不到 */
expect(app.includes('VISIT_DATA_RETENTION_DAYS'), '①g 沒有保存期限，資料會無限累積在手機上');
expect(/VISIT_DATA_RETENTION_DAYS = 60/.test(app), '①g 保存期限不是 60 天');
expect(app.includes('pruneVisitSummaryData'), '①g 有定義期限但沒有真的清');
// 還沒問的一律留著——他可能兩個月前就想問，只是還沒輪到看診，那不是過期資料
expect(/if \(!q \|\| !q\.askedAt\) return true;/.test(app),
  '①g 清理時把「還沒問的」也清掉了');
ok('①g 只留 60 天，但還沒問的問題不會被清掉');

/* ①h 字級設定要套得到這一頁——**這條不在這裡驗**。
   main 的 scripts/test-i18n-font-scale-surface-gate.js（#349）驗的是同一條
   不變式，而且做得更嚴：它會正確解析 applyFontScale 的選擇器清單，還帶
   新舊 markup 的自我檢查。同一條不變式擺兩份，只會讓未來改動要同時滿足
   兩組訊息不同的斷言，不會多守到任何東西，所以這裡只留指標。

   （背景：2026-07-29 把 #reportModal 從 .modal 改成 .reader-page 後就掉出
   applyFontScale 的選擇器，使用者選「特大」完全沒變大。註記量測陷阱：
   CSS zoom **不會**改變 computed font-size，量 font-size 會誤判成沒生效；
   實際算繪尺寸由 scripts/probe-visit-summary-font-scale.js 量。） */

/* ①i aria-label 必須走宣告式綁定（data-i18n-aria-label）。
   兩個教訓寫在這裡：
   ① 我一度以為 aria-label 不支援 i18n（grep 錯檔案：機制在 i18n/dom-localizer.js
      不在 i18n.js），於是改用 JS setAttribute——但那段只在非 zh-TW 才跑，
      等於 aria 只有外語使用者是對的，**中文讀屏使用者拿到的是 markup 裡的舊字**。
   ② 改名時只動 markup 沒動 catalog（或反過來），讀屏文字就會停在舊文案。
   宣告式綁定讓四語系一視同仁，也讓改文案不可能忘記同步。 */
const ARIA_BOUND = [
  ['visitClose', 'appointment.close'],
  ['reportClose', 'accessibility.back'],
  ['rptExportBtn', 'visit.exportAria'],
  ['rptPeriodTabs', 'visit.periodAria'],
];
for (const [id, key] of ARIA_BOUND) {
  const tag = (html.match(new RegExp(`<[^>]*id="${id}"[^>]*>`)) || [''])[0];
  expect(tag.length > 0, `①i 找不到 #${id}，這條測試已失效需重寫`);
  expect(tag.includes(`data-i18n-aria-label="${key}"`),
    `①i #${id} 的 aria-label 沒有綁 ${key}＝讀屏文字不會跟著語系走`);
  for (const locale of ['zh-TW', 'en', 'ja', 'es']) {
    const catalog = JSON.parse(fs.readFileSync(path.join(root, 'web', 'src', 'i18n', `${locale}.json`), 'utf8'));
    expect(typeof catalog[key] === 'string' && catalog[key].trim(),
      `①i ${locale} 缺 ${key}，#${id} 的讀屏文字會是空的`);
  }
}
// 綁定之後就不該再有那段只跑外語的 JS setAttribute
expect(!/setAria\('#reportClose'/.test(app),
  '①i 又回到只在非 zh-TW 才跑的 JS setAria——中文讀屏使用者會拿到舊字');
ok(`①i ${ARIA_BOUND.length} 個 aria-label 走宣告式綁定，四語系都有值`);

/* ② 紅線：畫面不得出現判定字眼 */
const FORBIDDEN = ['偏高', '偏低', '過高', '過低', '異常', '不正常', '需注意', '警告', '危險',
  '疑似', '診斷', '嚴重', '正常值', '標準值'];

// 極窄的白名單：只放行「字面完全相符」的免責句。
// 為什麼要有這個例外——頁尾必須寫「非醫療診斷」，那是法律上該講的標準寫法；
// 為了閃過自己的禁字表去弱化免責聲明，是本末倒置。
// 為什麼只放行字面字串、不放行「凡是前面有『非』『不是』就通融」——
// 後者會被當成後門：「這不是嚴重的問題」也能混過去。這裡只挖掉這幾個完整句子，
// 其餘任何地方用到「診斷」「嚴重」照樣擋。
const ALLOWED_DISCLAIMERS = ['非醫療診斷'];
function stripDisclaimers(text) {
  return ALLOWED_DISCLAIMERS.reduce((acc, phrase) => acc.split(phrase).join(''), text);
}

// 註解不算違規——只看真正會執行的程式碼與真正會被印出來的版型。
// （沿用 test-cloud-sync-guard.js 的同一條規矩。）
// 這裡是必要的：解釋「為什麼不能寫『異常』」的註解，本身一定會出現「異常」兩個字。
function stripComments(code) {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}
function stripHtmlComments(markup) {
  return markup.replace(/<!--[\s\S]*?-->/g, '');
}

// 只掃摘要相關的程式與樣板字串，避免掃到全 App 無關文案
const summaryCode = stripDisclaimers(stripComments(
  app.slice(app.indexOf('const VISIT_SUMMARY_SNAP_KEY'), app.indexOf('function visitSummaryAsText') + 2600)));
FORBIDDEN.forEach(word => expect(!summaryCode.includes(word), `② 摘要畫面出現判定字眼「${word}」＝越過醫材紅線`));
const modalHtml = stripDisclaimers(stripHtmlComments(html.slice(html.indexOf('id="reportModal"'), html.indexOf('id="fontModal"'))));
FORBIDDEN.forEach(word => expect(!modalHtml.includes(word), `② 摘要版型出現判定字眼「${word}」`));
// 白名單本身要被用到——免責聲明不見了也是問題
expect(html.includes('非醫療診斷') && app.includes('非醫療診斷'), '② 頁尾與匯出文字缺少免責聲明');
ok(`② 畫面與版型都沒有判定字眼（掃 ${FORBIDDEN.length} 個禁字）`);

/* ②-i18n 四語系目錄也要掃。
 *
 * 程式碼裡留的是 zh-TW 退路字串，真正印在紙上給醫師看的是目錄裡那一份——
 * 只掃程式碼，等於只守住了退路、沒守住實際輸出。日文另外列，是因為漢字共用
 * （「異常」「診断」在日文照樣是判讀）；英西則各自列等義詞。
 * 免責句仍照 ② 的規矩挖掉：法律上該講的話不能為了閃自己的禁字表而弱化。 */
const LOCALE_FORBIDDEN = {
  'zh-TW': { words: FORBIDDEN, allow: ALLOWED_DISCLAIMERS },
  ja: {
    words: ['異常', '診断', '疑い', '重症', '正常値', '基準値', '危険', '警告', '高すぎ', '低すぎ'],
    allow: ['医学的診断ではありません'],
  },
  en: {
    words: ['abnormal', 'diagnos', 'severe', 'critical', 'too high', 'too low',
      'normal range', 'warning', 'danger', 'elevated', 'concerning'],
    allow: ['not a medical diagnosis'],
  },
  es: {
    words: ['anormal', 'diagnóstic', 'diagnostic', 'grave', 'severo', 'demasiado alto',
      'demasiado bajo', 'valores normales', 'advertencia', 'peligro'],
    allow: ['no es un diagnóstico médico'],
  },
};
// 就診摘要這條線實際會印出來的 key（含設定頁入口與看診推播那一句）
const SUMMARY_KEY_RE = /^(visit\.|settings\.visitSummary|notification\.clinicQuestions)/;
let scannedCopy = 0;
for (const [locale, rule] of Object.entries(LOCALE_FORBIDDEN)) {
  const catalog = JSON.parse(fs.readFileSync(path.join(root, 'web', 'src', 'i18n', `${locale}.json`), 'utf8'));
  const keys = Object.keys(catalog).filter(key => SUMMARY_KEY_RE.test(key));
  expect(keys.length >= 30, `②-i18n ${locale} 只找到 ${keys.length} 把摘要文案 key，目錄或前綴改過了、這支測試已失效`);
  for (const key of keys) {
    const copy = rule.allow.reduce((acc, phrase) => acc.split(phrase).join(''), String(catalog[key]));
    const lowered = copy.toLowerCase();
    // 一句文案算一項契約（不是一句 × 幾個禁字），否則通過項數會被字表長度灌水
    const hit = rule.words.find(word => lowered.includes(word.toLowerCase()));
    expect(!hit, `②-i18n ${locale} 的「${key}」出現判定字眼「${hit}」＝越過醫材紅線：${catalog[key]}`);
    scannedCopy += 1;
  }
}
// 免責聲明四語系都要在，缺一份等於那個語系的紙本沒有免責
for (const [locale, rule] of Object.entries(LOCALE_FORBIDDEN)) {
  const catalog = JSON.parse(fs.readFileSync(path.join(root, 'web', 'src', 'i18n', `${locale}.json`), 'utf8'));
  expect(String(catalog['visit.footer'] || '').includes(rule.allow[0]),
    `②-i18n ${locale} 的頁尾少了免責聲明「${rule.allow[0]}」`);
}
ok(`②-i18n 四語系目錄共 ${scannedCopy} 句文案都沒有判定字眼，且都帶免責聲明`);

/* ②b 視覺也不得像醫療警報。
   切片的結束點原本釘在 @media print，那條隨「一鍵匯出」改版拿掉了——
   改釘下一個區塊的註解，並且**驗證切得到**，免得切片悄悄變成整份 CSS
   （那樣這條會因為別的地方有紅色而亂紅，或反過來永遠通過）。 */
const rptCssStart = css.indexOf('/* ── 就診摘要');
const rptCssEnd = css.indexOf('/* 用藥時段清單 */', rptCssStart);
expect(rptCssStart >= 0 && rptCssEnd > rptCssStart,
  '②b 找不到就診摘要的樣式區塊，這條測試已失效需重寫');
const rptCss = css.slice(rptCssStart, rptCssEnd);
expect(rptCss.length < 4000, `②b 切片過大（${rptCss.length} 字元），應該只涵蓋就診摘要那一段`);
// 用字界，否則 prefers-redUCED-motion 裡的 "reduced" 會被當成紅色（假警報）
const alertColour = /\bred\b|\bcrimson\b|#f00\b|#e0[0-4]|--danger|--alert/i;
expect(!alertColour.test(rptCss),
  `②b 摘要樣式用了紅色／警示色——看起來像醫療警報就等於在判讀：${(rptCss.match(alertColour) || [''])[0]}`);
// 反向自我檢查：這條規則本身要真的抓得到紅色，不然它只是裝飾
expect(alertColour.test('color: var(--danger)') && alertColour.test('background: red;'),
  '②b 警示色偵測失效，改壞了');
ok('②b 摘要樣式沒有紅色或警示色');

/* ③ 來源圖例（醫師要分辨可信度） */
expect(app.includes('● 長輩自己說的') && app.includes('▲ 在家量的') && app.includes('✕ 用藥紀錄'),
  '③ 時間軸缺少來源圖例，醫師無法分辨自述與量測');
expect(app.includes('VISIT_SUMMARY_MARK'), '③ 三種來源沒有各自的標記');
ok('③ 三種來源標記與圖例都在');

/* ④ 截斷與部分資料要說出來 */
expect(app.includes('summary.timelineOmitted > 0') && app.includes('筆較早的紀錄沒有列出來'),
  '④ 截斷沒有顯示出來——醫師會以為這就是全部');
expect(app.includes('summary.partial') && app.includes('這一頁不是完整的'),
  '④ 部分資料讀不到時沒有提示——少了血壓看起來就像「他都沒量」');
ok('④ 截斷與部分資料都會顯示');

/* ⑤ 沒有子女代為新增的入口 */
expect(!/子女|幫他加|代為新增|幫家人加/.test(summaryCode),
  '⑤ 出現子女代為新增的入口——沐寧要降低子女負擔，不是給他做整理工的工具');
expect(app.includes("via: 'manual'"), '⑤ 長輩自己手動加一題的路徑不見了');
ok('⑤ 只有長輩自己加，沒有子女代勞入口');

/* ⑥ 使用者輸入必須逸出 */
expect(app.includes('function rptEsc'), '⑥ 沒有逸出函式');
expect(app.includes('rptEsc(muneaSafeDisplayText(q.text'),
  '⑥ 口袋問題（使用者輸入）沒有先逸出就進 innerHTML');
expect(app.includes('rptEsc(e.text)'), '⑥ 時間軸文字沒有逸出');
ok('⑥ 使用者輸入都先逸出再渲染');

/* ⑦ 離線與快照 */
expect(app.includes('loadVisitSummarySnapshot') && app.includes('saveVisitSummarySnapshot'),
  '⑦ 沒有快照＝診間沒網路就打不開，而且早期症狀會被記憶淘汰吃掉');
expect(app.indexOf('renderVisitSummary(_rptLastSummary);') < app.indexOf('const fresh = await fetchVisitSummary(days);'),
  '⑦ 應先畫快照再背景更新，否則沒網路時畫面是空的');
ok('⑦ 先畫快照、再背景更新（診間離線可用）');

/* ⑧ 匯出＝按一下就跳系統分享（Edward 2026-07-29：「不需要顯示一堆提醒或流程」）。
   原本那句「傳出去就收不回來」的 confirm 與 1/2/3 的 prompt 選單都由他判定拿掉——
   系統分享面板本身就是那個確認動作，再多問一次只是擋路。 */
const exportBlock = app.slice(app.indexOf("$('#rptExportBtn')"), app.indexOf("// 發起挑戰面板"));
expect(exportBlock.length > 200, '⑧ 找不到匯出的綁定區塊，這條測試已失效需重寫');
expect(!/window\.confirm/.test(exportBlock), '⑧ 匯出又出現 confirm 問答——他要的是按一下就好');
expect(!/window\.prompt/.test(exportBlock), '⑧ 匯出又出現 prompt 選單——他要的是按一下就好');
expect(exportBlock.includes('exportVisitSummaryPdf'), '⑧ 匯出沒有直接產 PDF');
expect(exportBlock.includes("dataset.busy"), '⑧ 連按兩下會跑兩份，沒有防連點');
expect(app.includes('sharePdf'), '⑧ 沒有走原生外掛的 PDF＋系統分享面板');
expect(!/jspdf|html2canvas|pdfmake/i.test(app), '⑧ 引入了外部 PDF 套件——違反零支出與零新依賴');
// window.print() 在 iOS WKWebView 完全無效，App 內絕不能走那條
expect(!exportBlock.includes('window.print()'), '⑧ App 內又走了 window.print()——在 WKWebView 按了沒反應');
ok('⑧ 匯出一鍵到系統分享、零套件、無多餘問答');

/* ⑨ 後端契約對得上 */
expect(app.includes("brainPost('/visit-summary'"), '⑨ 前端沒有呼叫 /visit-summary');
expect(server.includes('self.path == "/visit-summary"'), '⑨ 後端沒有這條路由');
expect(app.includes("'/visit-summary': 15000"), '⑨ 沒給摘要足夠的等待時間（要撈三路資料）');
ok('⑨ 前後端契約對得上');

console.log(`\n✅ 就診摘要 UI：${passed} 項契約全過`);
