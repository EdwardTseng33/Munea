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
['rptExportBtn', 'rptPeriodTabs', 'rptDoneBtn', 'rptBody', 'rptPeriodLine', 'reportClose']
  .forEach(id => expect(html.includes('id="' + id + '"'), `① app.js 綁了 #${id}，但 HTML 裡沒有這個元素`));
ok('① 入口與所綁元素全部存在（含上一版死因的回歸測試）');

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

/* ②b 視覺也不得像醫療警報 */
const rptCss = css.slice(css.indexOf('/* ── 就診摘要'), css.indexOf('@media print'));
expect(!/red|#f00|#e0|crimson|--danger|--alert/i.test(rptCss),
  '②b 摘要樣式用了紅色／警示色——看起來像醫療警報就等於在判讀');
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

/* ⑧ 匯出：分享前警告 + PDF 走零套件的列印 */
expect(app.includes('傳出去之後就收不回來'), '⑧ 匯出前沒有提醒健康資料不可回收');
expect(app.includes('window.print()'), '⑧ PDF 沒有走瀏覽器內建列印');
expect(css.includes('@media print'), '⑧ 缺列印樣式，印出來會夾雜 App 的殼');
expect(!/jspdf|html2canvas|pdfmake/i.test(app), '⑧ 引入了外部 PDF 套件——違反零支出與零新依賴');
ok('⑧ 匯出有隱私提醒、PDF 零套件、列印樣式齊備');

/* ⑨ 後端契約對得上 */
expect(app.includes("brainPost('/visit-summary'"), '⑨ 前端沒有呼叫 /visit-summary');
expect(server.includes('self.path == "/visit-summary"'), '⑨ 後端沒有這條路由');
expect(app.includes("'/visit-summary': 15000"), '⑨ 沒給摘要足夠的等待時間（要撈三路資料）');
ok('⑨ 前後端契約對得上');

console.log(`\n✅ 就診摘要 UI：${passed} 項契約全過`);
