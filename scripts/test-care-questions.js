#!/usr/bin/env node
/* 口袋問題（要問醫生的問題）——M1 PR-3 · 2026-07-27
 *
 * 為什麼有這支：口袋問題是 M1 驗證 H1（「就醫時刻是不是真痛點」）的第一支探針。
 * 它碰語音線工具、碰 App 寫入、碰推播文字，三處都有踩過雷的前例：
 *   ① 2026-07-15 事故：aiAddVisitReminder／aiAddMedReminder 沒接共用文字守門，
 *      語音辨識雜訊直接被存成藥名／看診名 → 這支的守門必須真的驗，不能只看有沒有寫。
 *   ② 2026-07-16 事故：約吃飯被硬塞成看診提醒 → 能力握手（cap 旗標）是防「舊版 App
 *      拿到工具卻沒地方寫、AI 卻已經跟長輩說『記好了』」的空頭承諾。
 *   ③ 用藥照片上雲事故（018_strip_medication_photos.sql）：敏感內容進了不該進的地方。
 *      健康疑問同屬敏感內容——推播與埋點都只能帶「數量」、不能帶問題內文。
 *
 * 兩部分：
 *   Part A（行為）——把 app.js 裡的口袋問題區塊抽出來，在沙盒裡**真的執行**，
 *     驗守門、去重、上限、未問過的篩選、埋點內容。app.js 太大無法整支載入，
 *     所以抽區塊跑；抽取失敗會直接讓測試爆掉（＝有人改了區塊邊界，該重看這支測試）。
 *   Part B（契約）——跨檔案接線的 source-level 鎖（沿用 test-voice-launch-policy.js
 *     的手法）：能力握手兩邊對得上、工具只在允許時聲明、推播不外洩內文、
 *     語音說明書有「不判嚴重度」那條邊界。
 *
 * 跑法：node scripts/test-care-questions.js（不需網路、不需鑰匙）
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web', 'src', 'app.js'), 'utf8');
const notify = fs.readFileSync(path.join(root, 'web', 'src', 'notify.js'), 'utf8');
const voiceServer = fs.readFileSync(path.join(root, 'engine', 'live_voice_server.py'), 'utf8');

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

/* ─── Part A · 行為：真的跑一遍儲存邏輯 ─────────────────────────── */

function sliceBlock(source, startMarker, endMarker, label) {
  const start = source.indexOf(startMarker);
  expect(start >= 0, `抽取失敗：找不到 ${label} 的起點（${startMarker}）`);
  const end = source.indexOf(endMarker, start);
  expect(end >= 0, `抽取失敗：找不到 ${label} 的終點（${endMarker}）`);
  return source.slice(start, end + endMarker.length);
}

// 共用文字守門（事故①的那道門）＋口袋問題區塊
const guardBlock = sliceBlock(app, 'function muneaIsCleanZhText(raw) {', '\n}', 'muneaIsCleanZhText');
const careBlock = sliceBlock(
  app,
  "const CARE_Q_KEY = 'munea.careQuestions';",
  'window.__muneaSaveCareQuestions = saveCareQuestions;',
  '口袋問題區塊',
);

const store = new Map();
const events = [];
const sandbox = {
  localStorage: {
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: k => store.delete(k),
  },
  trackProductEvent: (name, props) => { events.push({ name, props }); return Promise.resolve(null); },
  Date, Math, JSON, String, Array, Object, Number, Set, console,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
// 註：`const` 宣告在 script 頂層**不會**掛上 global（只有 `function` 宣告會），
// 所以 CARE_Q_MAX／CARE_Q_MAX_LEN 沒辦法直接從 sandbox 取——補一行把常數導出來。
const exposeConsts = '\nwindow.__careConsts = { CARE_Q_KEY, CARE_Q_MAX, CARE_Q_MAX_LEN };';
vm.runInContext(guardBlock + '\n' + careBlock + exposeConsts, sandbox, { filename: 'app.js#careQuestions' });

const { aiAddCareQuestion, loadCareQuestions, openCareQuestions, saveCareQuestions } = sandbox;
const { CARE_Q_MAX, CARE_Q_MAX_LEN } = sandbox.__careConsts;
expect(CARE_Q_MAX > 0 && CARE_Q_MAX_LEN > 0, '常數沒有正確導出，後面的上限測試會失去意義');

(async () => {
  /* A-1 正常記一題 */
  let r = await aiAddCareQuestion({ question: '膝蓋痠兩個禮拜了，上下樓會卡，要不要照X光？' });
  expect(r.ok === true, 'A-1 正常問題應該記得起來');
  expect(r.count === 1, `A-1 未問過的問題數應為 1，實得 ${r.count}`);
  expect(r.persistence === 'device', 'A-1 必須誠實回報只存在裝置端（H1 期間不進雲端）');
  expect(loadCareQuestions().length === 1, 'A-1 應真的寫進 localStorage');
  console.log('PASS A-1 正常記一題、回報 device 儲存');

  /* A-2 埋點只帶數量、絕不帶問題內文（事故③：敏感內容不可外流） */
  expect(events.length === 1, `A-2 應送出一筆埋點，實得 ${events.length}`);
  const ev = events[0];
  expect(ev.name === 'care_question_added', `A-2 事件名不符：${ev.name}`);
  expect(ev.props.questionCount === 1, 'A-2 埋點要帶未問過的問題數');
  const evJson = JSON.stringify(ev.props);
  expect(!evJson.includes('膝蓋'), 'A-2 ⚠ 埋點夾帶了問題內文——健康疑問屬敏感內容，只能帶數量');
  expect(!('text' in ev.props) && !('question' in ev.props), 'A-2 埋點不得有 text／question 欄位');
  console.log('PASS A-2 埋點只帶數量與長度、不帶問題內文');

  /* A-3 辨識雜訊要擋掉（事故①：不存假資料，寧可讓她再問一次） */
  const dirty = ['', '   ', 'hello there doctor', 'アイウエオ', '???????', '啊啊啊啊啊啊啊啊'];
  for (const bad of dirty) {
    const rr = await aiAddCareQuestion({ question: bad });
    expect(rr.ok === false, `A-3 應拒收不乾淨的問題文字：${JSON.stringify(bad)}`);
    expect(rr.error === 'question_text_unclear', `A-3 錯誤碼應為 question_text_unclear，實得 ${rr.error}`);
  }
  expect(loadCareQuestions().length === 1, 'A-3 被拒收的問題不可留在清單裡');
  console.log(`PASS A-3 擋掉 ${dirty.length} 種雜訊／空白輸入，清單未被污染`);

  /* A-4 重複問題不重複塞，但仍回 ok（她已經跟長輩說要記了，不該改口說失敗） */
  r = await aiAddCareQuestion({ question: '膝蓋痠兩個禮拜了，上下樓會卡，要不要照X光？' });
  expect(r.ok === true, 'A-4 重複問題仍應回 ok（避免她改口說沒記到）');
  expect(r.duplicate === true, 'A-4 應標記 duplicate');
  expect(loadCareQuestions().length === 1, 'A-4 重複問題不可產生第二筆');
  console.log('PASS A-4 重複問題回 ok 但不重複入帳');

  /* A-5 已問過的不算在「要問」裡（看診後清單要退場，否則永遠提醒同一題） */
  const arr = loadCareQuestions();
  arr[0].askedAt = new Date().toISOString();
  saveCareQuestions(arr);
  expect(openCareQuestions().length === 0, 'A-5 標記已問過後，未問清單應為空');
  expect(loadCareQuestions().length === 1, 'A-5 已問過的仍保留在歷史裡、不是刪掉');
  console.log('PASS A-5 已問過的退出「要問」清單但保留歷史');

  /* A-6 長度截斷與數量上限
     註：截斷後仍要過共用守門。用「同一個字重複 200 次」測截斷是錯的測法——
     守門會（正確地）把它判成亂碼擋掉（unique 字元比例不足）。要用真實的長問句。 */
  const long = '我這個膝蓋已經痠痛超過兩個禮拜了，早上起來特別僵硬，上下樓梯的時候會卡住還會有聲音，晚上翻身也會痛，請問需不需要照X光或做其他檢查？';
  expect(long.length > CARE_Q_MAX_LEN, 'A-6 測資本身要比上限長才測得到截斷');
  r = await aiAddCareQuestion({ question: long });
  expect(r.ok === true, `A-6 過長問題應截斷而非拒收，實得 error=${r.error}`);
  expect(r.question.length === CARE_Q_MAX_LEN, `A-6 應截到 ${CARE_Q_MAX_LEN} 字，實得 ${r.question.length}`);
  // 上限管的是「還沒問的」，不是總筆數——問過的要留著當病史（A-5 已經鎖了這點），
  // 用總筆數當上限會逼著刪歷史。
  const results = [];
  for (let i = 0; i < CARE_Q_MAX + 5; i += 1) {
    results.push(await aiAddCareQuestion({ question: `第${i}個要問醫生的問題是什麼呢` }));
  }
  expect(openCareQuestions().length <= CARE_Q_MAX,
    `A-6 未問清單不得超過上限 ${CARE_Q_MAX}，實得 ${openCareQuestions().length}`);
  // 滿了要**回報**，不可以默默擠掉最舊的——她答應要記住，偷偷刪掉就是毀約
  const full = results.filter(r => r && r.error === 'question_list_full');
  expect(full.length > 0, 'A-6 清單滿了應回 question_list_full，不可靜默丟棄');
  expect(!results.some(r => r && r.ok && r.count > CARE_Q_MAX), 'A-6 不得有超過上限還回 ok 的呼叫');
  console.log(`PASS A-6 長度截到 ${CARE_Q_MAX_LEN} 字、未問上限 ${CARE_Q_MAX} 題且滿了會明說`);

  /* A-7 滿了不可以默默擠掉最舊的那一題（她說會記住，結果偷偷刪＝毀約） */
  const beforeFull = openCareQuestions().map(q => q.text);
  await aiAddCareQuestion({ question: '這題應該要被擋下來而不是擠掉別人' });
  const afterFull = openCareQuestions().map(q => q.text);
  expect(JSON.stringify(beforeFull) === JSON.stringify(afterFull),
    'A-7 清單滿了再記一題，既有題目不可以被擠掉');
  console.log('PASS A-7 清單滿了擋在門口，不動既有題目');

  /* A-8 語音那條路真的走得通——不是只驗字串有沒有出現，是把整條鏈跑一遍。
     鏈路：Gemini 呼叫工具 → 伺服器轉成 {type:'action'} 送 ws → App 的
     handleVoiceAction → aiAddCareQuestion → localStorage → 就診摘要讀得到。
     這裡把 handleVoiceAction 那一段真的抽出來執行（不是 mock），只補它
     依賴的 muneaT / toast，證明語音記下來的問題會出現在摘要的清單裡。 */
  const actionBlock = sliceBlock(app, 'async function handleVoiceAction(action, args) {',
    'window.__muneaHandleVoiceAction = handleVoiceAction;', 'handleVoiceAction');
  const toasts = [];
  sandbox.toast = m => toasts.push(String(m));
  sandbox.muneaT = (k, fb, v) => String(fb).replace(/\{(\w+)\}/g, (_, n) => (v && v[n] != null ? v[n] : ''));
  sandbox.brainPost = async () => ({ ok: false });
  vm.runInContext(actionBlock, sandbox, { filename: 'app.js#handleVoiceAction' });
  const handleVoiceAction = sandbox.handleVoiceAction;
  expect(typeof handleVoiceAction === 'function', 'A-8 抽不出 handleVoiceAction');

  // 清乾淨再測，才知道是這一次語音存進去的
  saveCareQuestions([]);
  const before = openCareQuestions().length;
  const voiceResult = await handleVoiceAction('add_care_question',
    { question: '最近走路會喘，需不需要做心臟檢查？' });
  expect(voiceResult && voiceResult.ok === true,
    `A-8 語音記問題失敗：${JSON.stringify(voiceResult)}`);
  const after = openCareQuestions();
  expect(after.length === before + 1, 'A-8 語音記下的問題沒有進到清單');
  expect(after[after.length - 1].text.includes('走路會喘'), 'A-8 存進去的不是他說的那句');
  expect(toasts.some(m => m.includes('記下來了')), 'A-8 沒有跟長輩確認記好了');
  // 摘要那一頁讀的就是這份清單（openCareQuestions），所以進得了清單＝看得到
  console.log('PASS A-8 語音 → handleVoiceAction → 清單 → 就診摘要，整條走得通');

  /* A-9 清單滿了，語音那條**不可以**跟他說「我沒聽清楚」——
     他會一直重講，永遠不知道是滿了。失敗原因要講對。 */
  saveCareQuestions([]);
  for (let i = 0; i < CARE_Q_MAX; i += 1) {
    await aiAddCareQuestion({ question: `第${i}個要問醫生的問題是什麼呢` });
  }
  toasts.length = 0;
  const fullResult = await handleVoiceAction('add_care_question',
    { question: '這一題應該要被擋下來並且說明原因' });
  expect(fullResult && fullResult.ok === false && fullResult.error === 'question_list_full',
    `A-9 滿了應回 question_list_full，實得 ${JSON.stringify(fullResult)}`);
  expect(!toasts.some(m => m.includes('沒聽清楚')),
    `A-9 清單滿了卻跟他說「沒聽清楚」，他會一直重講：${toasts.join(' / ')}`);
  expect(toasts.some(m => m.includes('記滿')), `A-9 沒有講出真正的原因：${toasts.join(' / ')}`);
  console.log('PASS A-9 清單滿了講真正的原因，不謊稱沒聽清楚');

  /* ─── Part B · 契約：跨檔接線的 source-level 鎖 ──────────────── */

  // B-1 能力握手兩邊對得上（事故②：舊版拿到工具卻沒地方寫＝空頭承諾）
  expect(app.includes("url += '&cap_ask=1';"), 'B-1 App 沒送出 cap_ask 能力握手');
  expect(voiceServer.includes('_q.get("cap_ask") == ["1"]'), 'B-1 語音伺服器沒解析 cap_ask');
  console.log('PASS B-1 能力握手 cap_ask 兩邊接上');

  // B-2 工具只在允許時聲明（且 demo 模式一律不給，比照既有兩個工具）
  expect(voiceServer.includes('if allow_care_questions and not demo_mode:\n        tools.append(_CARE_QUESTION_TOOLS)'),
    'B-2 口袋問題工具沒有被能力旗標與 demo 模式雙重把關');
  expect(voiceServer.includes('name="add_care_question"'), 'B-2 找不到 add_care_question 工具宣告');
  console.log('PASS B-2 工具受 allow_care_questions＋demo_mode 雙重把關');

  // B-3 App 真的處理這個 action（否則 AI 呼叫了沒人接、逾時假失敗）
  expect(app.includes("if (action === 'add_care_question')"), 'B-3 App 的 handleVoiceAction 沒有接 add_care_question');
  console.log('PASS B-3 App 有接 add_care_question 動作');

  // B-4 語音說明書要有「保管問題、不回答問題」的邊界（配 chat_engine.CORE ②-B）
  expect(voiceServer.includes('不要順口幫他判斷嚴重不嚴重'), 'B-4 說明書缺「不判嚴重度」邊界');
  expect(voiceServer.includes('不要猜可能是什麼病'), 'B-4 說明書缺「不猜病名」邊界');
  console.log('PASS B-4 說明書有不判嚴重度／不猜病名的邊界');

  // B-5 推播只帶數量、不帶問題內文（事故③同一條原則）
  //
  // 精確檢查「組裝推播文字的那幾行」——不是全檔搜 .text。`q.text` 在這支檔案裡是
  // **篩選條件**（過濾出真的有內容的項目），出現在檔案裡完全正常；真正要防的是
  // 把內文接進 visitBody。所以只看對 visitBody 賦值／串接的那幾行。
  //
  // 文案本身在四語系目錄裡（notification.clinicQuestions），所以這裡驗的是
  // 「有掛上那把 key、而且只餵 n」，不是驗某一句中文字串——把中文釘在測試裡，
  // 下次翻譯一動就無故變紅，卻一點安全性都沒多守到。
  expect(/muneaT?\s*\(\s*['"]notification\.clinicQuestions['"]/.test(notify)
    || /t\(\s*['"]notification\.clinicQuestions['"]/.test(notify),
    'B-5 看診推播沒帶未問問題數（找不到 notification.clinicQuestions）');
  expect(/\{\s*n:\s*openQ\s*\}/.test(notify), 'B-5 推播文案只能餵數量 n，不得餵入問題內文');
  for (const locale of ['zh-TW', 'en', 'ja', 'es']) {
    const catalog = JSON.parse(fs.readFileSync(path.join(root, 'web/src/i18n', `${locale}.json`), 'utf8'));
    const copy = catalog['notification.clinicQuestions'];
    expect(typeof copy === 'string' && copy.includes('{n}'),
      `B-5 ${locale} 缺 notification.clinicQuestions 或沒有 {n} 佔位`);
  }
  expect(notify.includes('q.text && !q.askedAt'), 'B-5 推播應只計未問過的問題');
  const visitBodyLines = notify.split('\n').filter(l => /visitBody\s*\+?=/.test(l));
  expect(visitBodyLines.length >= 2, `B-5 找不到 visitBody 的組裝行（實得 ${visitBodyLines.length} 行），這支測試已失效需重寫`);
  for (const line of visitBodyLines) {
    expect(!/\.text\b/.test(line) && !/\bqs\b/.test(line) && !/\bq\./.test(line),
      `B-5 ⚠ 推播文字組裝夾帶了問題內文，只能帶數量：${line.trim()}`);
  }
  console.log(`PASS B-5 看診推播只帶數量、不帶問題內文（檢查 ${visitBodyLines.length} 行組裝碼）`);

  console.log('\n✅ 口袋問題全過：行為 9 組（含語音端對端）＋ 契約 5 組');
})().catch(err => { console.error('\n❌ FAIL:', err.message); process.exit(1); });
