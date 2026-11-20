#!/usr/bin/env node
/* 機構照護模式同意開關（設定 →「{機構} 看得到什麼」）的守門 · 2026-11-17
 *
 * 照護機構的人員預設看不到任何一位長輩；本人在 App 把開關打開，機構端才看得到他。這支守住：
 *   A. 畫面：設定頁「帳號與家庭」那組有一列入口，預設收著（沒有名額的人看不到）；
 *      視窗有標題、整列式開關（預設關）、結果訊息區、「隨時可以關」那句、兩張清單、完成鍵；
 *      開通碼成功畫面多一顆次要按鈕（預設收著）。
 *   B. 行為（真的把 web/src/org-consent.js 跑起來）：有照護機構名額才顯示入口、企業福利不顯示；
 *      開與關各打 /org-consent/set、帶登入證、參數只有 { seatId, granted }；處理中不能連點；
 *      成功才動開關，失敗留在原位並講原因（含後端「同意留不下來就不算數」「企業名額不收同意」兩種）；
 *      絕不自動幫人打開；產品事件不帶機構名稱與名額代號。
 *   C. 文案：四語都有全部 orgConsent.* 鍵、程式裡的中文後備跟語系檔一致、沒有公文字與禁用字、
 *      日文對照護機構用「施設」。
 *   D. 文案跟後端對得上：兩張清單各對到 engine/org_api.py 實際給機構的欄位（見下表）。
 *      後端那幾行一動，這裡會紅，提醒回來對文案——文案不可以比機構端實際看到的多或少。
 *
 *   「打開後看得到」        ← 機構端實際拿到的（engine/org_api.py）
 *   sees1 你的稱呼           ← _elder_label：nickname／profileName（L1 名單與 L2 摘要的 label）
 *   sees2 哪幾天聊、聊幾次   ← _strip_week_for_org 的 contact（calls、daysWithCall、longestGapDays、lastCallDate）
 *                               ＋ moodTrend.daily[].chats；L1 的 lastInteractionDate、noInteractionToday
 *   sees3 每天的心情高低     ← moodTrend（daily[].level 1–5、weekAverage、baselineAverage、lowestDay）；L1 的 lowMood
 *   sees4 四類各提到幾次     ← spokenHealth.categories＝[{key, label, count}]，由 _spoken_categories 把心情訊號的 concerns
 *                               歸成固定四類再數次數：吃不下（appetite）／睡不好（sleep）／身體不舒服（body）／
 *                               心情或生活上的掛心事（other）。只有類別與次數，任何短語都不回（2026-11-17 #711；
 *                               在那之前機構拿到的是短語本身，這支測試就是那時候對出落差的）。
 *   sees5 需要留意的次數     ← safety（counts 只認已知風險等級、highOrCritical）；L1 的 guardianLit；
 *                               異常規則的 fact 都是由上面的數字組的
 *   「永遠看不到」           ← _consent_view 的 whatOrgNeverSees 四項，一對一：
 *   never1 聊天的內容 ← 對話內容｜never2 原話 ← 心情與口述的原句或短語｜never3 吃什麼藥 ← 用藥明細｜never4 家人留的話 ← 家人帶話
 *
 * 跑法：node scripts/test-org-consent-ui.js（不需網路、不需鑰匙）
 * ⚠ 還沒掛進 npm run test:launch：#694／#696 正在改 package.json 同一行，等它們合併後跟 test-seat-code-ui.js 一起補。
 */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(ROOT, relativePath), 'utf8');
const html = read('web/index.html');
const app = read('web/src/app.js');
const source = read('web/src/org-consent.js');
const seatCodeSource = read('web/src/seat-code.js');
const backend = read('engine/org_api.py');
const LOCALES = ['zh-TW', 'en', 'ja', 'es'];
const catalogs = Object.fromEntries(
  LOCALES.map((locale) => [locale, JSON.parse(read(`web/src/i18n/${locale}.json`))]),
);
const OrgConsent = require(path.join(ROOT, 'web', 'src', 'org-consent.js'));
const SeatCode = require(path.join(ROOT, 'web', 'src', 'seat-code.js'));

function tagWithId(id) {
  const match = html.match(new RegExp(`<[a-z0-9]+\\b[^>]*\\bid="${id}"[^>]*>`));
  assert.ok(match, `index.html 找不到 #${id}`);
  return match[0];
}

function block(startMarker, endMarker, label) {
  const start = html.indexOf(startMarker);
  assert.ok(start >= 0, `index.html 找不到 ${label}`);
  const end = html.indexOf(endMarker, start);
  assert.ok(end > start, `index.html 的 ${label} 沒有結尾`);
  return html.slice(start, end);
}

// ---------- A. 畫面 ----------
const accountGroup = block('data-i18n="settings.section.accountFamily"', '<h2 class="set-section"', '設定頁「帳號與家庭」那組');
assert.ok(accountGroup.includes('id="famCircleRow"'), '「帳號與家庭」原本的「全家健康圈」不見了');
assert.ok(accountGroup.includes('id="orgConsentRow"'), '設定頁「帳號與家庭」那組少了機構照護模式的入口（#orgConsentRow）');
const rowTag = tagWithId('orgConsentRow');
assert.ok(/\shidden(\s|>)/.test(rowTag), '入口預設要收著（hidden）：沒有機構名額的人設定頁不可以多東西');
assert.ok(/\brole="button"/.test(rowTag) && /\btabindex="0"/.test(rowTag), '入口要能用鍵盤與報讀軟體操作（role="button" tabindex="0"）');
for (const id of ['orgConsentRowTitle', 'orgConsentRowState', 'orgConsentRowDot', 'orgConsentRowDotLabel']) {
  assert.ok(accountGroup.includes(`id="${id}"`), `入口那一列少了 #${id}`);
  // 這幾個字都帶機構名稱或跟著狀態變，掛了 data-i18n 會被巡邏的翻譯層蓋回去。
  assert.ok(!/\bdata-i18n=/.test(tagWithId(id)), `#${id} 的字由程式決定，不可以掛 data-i18n`);
}

const modal = block('<div class="modal-mask" id="orgConsentModal">', '\n  </div>\n', '機構照護模式視窗');
for (const id of ['orgConsentClose', 'orgConsentTitle', 'orgConsentSwitch', 'orgConsentSwitchLabel',
  'orgConsentKnob', 'orgConsentMsg', 'orgConsentDone']) {
  assert.ok(modal.includes(`id="${id}"`), `視窗裡少了 #${id}`);
}
const switchTag = tagWithId('orgConsentSwitch');
assert.ok(/^<button\b/.test(switchTag) && /\btype="button"/.test(switchTag), '開關要是 <button type="button">（整列都能按）');
assert.ok(/\brole="switch"/.test(switchTag), '開關要標 role="switch"，報讀軟體才知道它是開關');
assert.ok(/\baria-checked="false"/.test(switchTag), '開關在畫面檔上預設是關（aria-checked="false"）');
assert.ok(/\baria-labelledby="orgConsentSwitchLabel"/.test(switchTag), '開關的報讀名稱要指到旁邊那句話');
assert.ok(!/\bclass="[^"]*\bon\b/.test(tagWithId('orgConsentKnob')), '開關的圓鈕在畫面檔上不可以預設是開的樣子');
const messageTag = tagWithId('orgConsentMsg');
assert.ok(/\brole="status"/.test(messageTag) && /\baria-live="polite"/.test(messageTag),
  '結果訊息區要 aria-live="polite"，報讀軟體才念得到「開好了／沒有改到」');
for (const id of ['orgConsentTitle', 'orgConsentSwitchLabel', 'orgConsentMsg']) {
  assert.ok(!/\bdata-i18n=/.test(tagWithId(id)), `#${id} 的字由程式決定，不可以掛 data-i18n`);
}
assert.ok(/\bdata-i18n-aria-label="accessibility\.close"/.test(tagWithId('orgConsentClose')), '關閉鍵要有報讀名稱');
assert.ok(/\bdata-i18n="common\.done"/.test(tagWithId('orgConsentDone')), '最下面的鍵是「完成」（common.done）');

const SEES = ['sees1', 'sees2', 'sees3', 'sees4', 'sees5'];
const NEVER = ['never1', 'never2', 'never3', 'never4'];
const listKeys = (className) => {
  const list = modal.match(new RegExp(`<ul class="oc-list ${className}">([\\s\\S]*?)</ul>`));
  assert.ok(list, `視窗裡少了清單 .${className}`);
  return [...list[1].matchAll(/<li data-i18n="orgConsent\.([A-Za-z0-9]+)">/g)].map((match) => match[1]);
};
assert.deepEqual(listKeys('oc-sees'), SEES, '「打開後看得到」清單要剛好是 sees1–sees5（跟後端對照表一致）');
assert.deepEqual(listKeys('oc-never'), NEVER, '「永遠看不到」清單要剛好是 never1–never4（跟後端四項一對一）');
for (const key of ['seesTitle', 'neverTitle', 'anytime']) {
  assert.ok(modal.includes(`data-i18n="orgConsent.${key}"`), `視窗裡少了 orgConsent.${key}`);
}
// 「隨時可以關」緊跟在開關下面：英、日、西的清單比較長，放最後會被擠到畫面外，按開關的當下看不到這句。
assert.ok(modal.indexOf('id="orgConsentSwitch"') < modal.indexOf('id="orgConsentMsg"')
  && modal.indexOf('id="orgConsentMsg"') < modal.indexOf('orgConsent.anytime')
  && modal.indexOf('orgConsent.anytime') < modal.indexOf('oc-sees')
  && modal.indexOf('oc-sees') < modal.indexOf('oc-never')
  && modal.indexOf('oc-never') < modal.indexOf('id="orgConsentDone"'),
'視窗順序：開關 → 結果訊息 → 隨時可以關 → 看得到 → 永遠看不到 → 完成');

const seatModal = block('<div class="modal-mask" id="seatCodeModal">', '\n  </div>\n', '機構開通碼視窗');
assert.ok(seatModal.includes('id="seatCodeConsentBtn"'), '開通碼視窗少了帶去「看得到什麼」的次要按鈕（#seatCodeConsentBtn）');
const offerTag = tagWithId('seatCodeConsentBtn');
assert.ok(/\shidden(\s|>)/.test(offerTag), '次要按鈕預設要收著：只有綁到照護機構的名額才出現');
assert.ok(/\bclass="[^"]*\bquiet\b/.test(offerTag), '那顆是次要按鈕（.quiet），不可以跟主按鈕「完成」搶');
assert.ok(!/\bdata-i18n=/.test(offerTag), '次要按鈕的字帶機構名稱，不可以掛 data-i18n');
assert.ok(seatModal.indexOf('id="seatCodeBtn"') < seatModal.indexOf('id="seatCodeConsentBtn"'), '次要按鈕排在主按鈕下面');

assert.ok(/<script src="src\/org-consent\.js\?v=[^"]+"><\/script>/.test(html),
  'index.html 要用一般（非模組）方式載入 src/org-consent.js，並帶快取版號');
const bridgeMatch = app.match(/window\.__muneaOrgConsentBridge = \{([^}]*)\};/);
assert.ok(bridgeMatch, 'app.js 要把登入證等工具借給 org-consent.js（window.__muneaOrgConsentBridge）');
for (const tool of ['brainURL', 'authHeaders: muneaAuthHeaders', 'isLoggedIn', 'track: trackProductEvent']) {
  assert.ok(bridgeMatch[1].includes(tool), `借給 org-consent.js 的工具少了 ${tool}`);
}
assert.ok(!/\bMUNEA_APP_KEY\b/.test(source), 'org-consent.js 不可以自己去拿 MUNEA_APP_KEY（拿不到，通行碼會整個沒帶）');
// 後端回的 whatOrgSees／whatOrgNeverSees 是寫死的中文，App 要用自己的四語文案，不可以直接拿來顯示。
assert.ok(!/\.whatOrg(Sees|NeverSees)\b|\[['"]whatOrg/.test(source), 'org-consent.js 不可以讀後端的 whatOrgSees／whatOrgNeverSees 來顯示');

// ---------- D. 文案跟後端對得上 ----------
// 這裡釘住後端「機構端實際拿到什麼」的幾行。任何一行變了，回來對 orgConsent.sees*／never* 四語文案。
const BACKEND_FACTS = [
  ['never1–4', '"whatOrgNeverSees": ["對話內容", "心情與口述的原句或短語", "用藥明細", "家人帶話"],'],
  ['後端自述看得到什麼', '"whatOrgSees": ["整家彙總", "名單（稱呼）與三個旗標（今天沒互動／心情低落／守護亮燈）", "週關懷摘要（通話次數、心情走勢、掛心事的類別與次數、亮燈次數）"],'],
  ['sees1（稱呼）', 'label = person_info.get("nickname") or person_info.get("profileName") or ""'],
  ['sees2（聊了幾次、哪幾天）', '"source": contact.get("source"), "calls": contact.get("calls"), "daysWithCall": contact.get("daysWithCall"),'],
  ['sees2（最長空檔、最後一次）', '"longestGapDays": contact.get("longestGapDays"), "lastCallDate": contact.get("lastCallDate"),'],
  ['sees2／sees3（每天心情與次數，沒有原句）', 'daily = [{"date": d.get("date"), "level": d.get("level"), "chats": d.get("chats")} for d in mood.get("daily") or []]'],
  ['sees3（最低那天只有日期與級數）', '"lowestDay": {"date": lowest.get("date"), "level": lowest.get("level")} if lowest else None,'],
  ['sees4（掛心事只經過歸類）', '"categories": _spoken_categories((week.get("spokenHealth") or {}).get("items")),'],
  ['sees4（只回類別與次數，不回短語）', 'return [{"key": k, "label": label, "count": counts[k]} for k, label in order if counts.get(k)]'],
  ['sees4（其他掛心事那一類）', 'SPOKEN_CATEGORY_OTHER = ("other", "心情或生活上的掛心事")'],
  ['sees5（只有次數、只認已知等級）', '"counts": {k: v for k, v in (safety.get("counts") or {}).items() if k in ORG_RISK_LEVELS},'],
  ['企業福利永遠沒有個人層', 'if _client_kind(client) == "esg":\n        return []'],
  ['企業名額不收同意（consent_not_applicable）', 'return {"ok": False, "error": "consent_not_applicable"}'],
  ['同意留不下來就不算數（consent_not_recorded）', 'return {"ok": False, "error": "consent_not_recorded", "seat": _consent_view(seat, client, existing)}'],
];
for (const [what, line] of BACKEND_FACTS) {
  assert.ok(backend.includes(line), `engine/org_api.py 這一行變了（${what}）——請回來對 orgConsent.sees*／never* 四語文案是否還跟機構端實際拿到的一致：\n  ${line}`);
}
// 機構版週摘要有哪幾塊：多一塊＝機構多看到東西，文案要跟著加；少一塊要跟著拿掉。
const stripStart = backend.indexOf('def _strip_week_for_org(week):');
const stripBody = backend.slice(stripStart, backend.indexOf('\ndef ', stripStart + 10));
assert.deepEqual(
  [...stripBody.matchAll(/^ {8}"([A-Za-z]+)":/gm)].map((match) => match[1]),
  ['period', 'contact', 'moodTrend', 'spokenHealth', 'safety', 'honesty', 'partial'],
  '機構版週摘要（_strip_week_for_org）回的區塊變了——請回來對 orgConsent.sees* 文案',
);
// 掛心事固定歸成這幾類（sees4 一項一項寫出來的就是這幾類，加上「其他掛心事」）。多一類、少一類、改名，都要回來對文案。
const rulesStart = backend.indexOf('SPOKEN_CATEGORY_RULES = (');
const rulesBody = backend.slice(rulesStart, backend.indexOf('SPOKEN_CATEGORY_OTHER = ', rulesStart));
assert.deepEqual(
  [...rulesBody.matchAll(/^ {4}\("([a-z]+)", "([^"]+)", \(/gm)].map((match) => `${match[1]}:${match[2]}`),
  ['appetite:吃不下', 'sleep:睡不好', 'body:身體不舒服'],
  '機構端掛心事的類別（SPOKEN_CATEGORY_RULES）變了——請回來對 orgConsent.sees4 四語文案',
);

// ---------- B1. 純邏輯：挑名額、看懂回應 ----------
assert.equal(OrgConsent.STATUS_PATH, '/org-consent');
assert.equal(OrgConsent.SET_PATH, '/org-consent/set');
assert.equal(OrgConsent.EVENT_NAME, 'org_consent_set');
assert.deepEqual([...OrgConsent.APPLICABLE_KINDS], ['care'], '只有照護機構（care）顯示開關；企業福利（esg）永遠只有彙總，不顯示');

const ORG = '安心日照中心';
const SEAT_ID = 'seat-7f3a9c21';
const seatItem = ({ kind = 'care', status = 'none', seatId = SEAT_ID, name = ORG } = {}) => ({
  seatId, seatCode: 'S-7F3A', seatStatus: 'active', siteLabel: null,
  org: { id: 'org-1', name, clientKind: kind },
  consent: { status, grantedAt: null, revokedAt: null, grantedByRole: null },
  whatOrgSees: ['整家彙總'], whatOrgNeverSees: ['對話內容'],
});
const statusBody = (...items) => ({ ok: true, count: items.length, seats: items });

assert.equal(OrgConsent.pickSeat(statusBody()), null, '沒有名額＝沒有入口');
assert.equal(OrgConsent.pickSeat(null), null);
assert.equal(OrgConsent.pickSeat({ ok: false, error: 'identity_required' }), null);
assert.equal(OrgConsent.pickSeat({ ok: true }), null);
assert.equal(OrgConsent.pickSeat(statusBody(seatItem({ kind: 'esg' }))), null, '企業福利的名額不顯示開關');
assert.equal(OrgConsent.pickSeat(statusBody(seatItem({ kind: 'school' }))), null, '不認得的機構類型先不顯示');
assert.equal(OrgConsent.pickSeat(statusBody(seatItem({ kind: null }))), null, '沒標類型的不顯示');
assert.equal(OrgConsent.pickSeat(statusBody(seatItem({ seatId: '' }))), null, '沒有名額代號就沒辦法改，不顯示');
assert.deepEqual(OrgConsent.pickSeat(statusBody(seatItem())), { seatId: SEAT_ID, org: ORG, granted: false }, '沒設定過＝關');
assert.deepEqual(OrgConsent.pickSeat(statusBody(seatItem({ status: 'granted' }))), { seatId: SEAT_ID, org: ORG, granted: true });
assert.equal(OrgConsent.pickSeat(statusBody(seatItem({ status: 'revoked' }))).granted, false, '關掉過＝關');
assert.equal(OrgConsent.pickSeat(statusBody(seatItem({ status: 'something_new' }))).granted, false, '看不懂的狀態一律當關');
assert.equal(OrgConsent.pickSeat({ ok: true, seats: [{ seatId: SEAT_ID, org: { clientKind: 'care' } }] }).granted, false, '沒帶同意狀態＝關');
assert.equal(
  OrgConsent.pickSeat(statusBody(seatItem({ kind: 'esg', seatId: 'seat-esg' }), seatItem({ seatId: 'seat-care' }))).seatId,
  'seat-care', '同時有企業與照護機構的名額時，挑照護機構那個',
);

const viewBody = (status) => ({ ok: true, changed: true, seat: seatItem({ status }) });
assert.deepEqual(OrgConsent.interpretSet(200, viewBody('granted'), true),
  { ok: true, granted: true, message: 'savedOn', event: { result: 'granted' } });
assert.deepEqual(OrgConsent.interpretSet(200, viewBody('revoked'), false),
  { ok: true, granted: false, message: 'savedOff', event: { result: 'revoked' } });
// 從沒開過的人按「關」：後端回 changed:false、狀態 none——也算關好了
assert.equal(OrgConsent.interpretSet(200, { ok: true, changed: false, seat: seatItem({ status: 'none' }) }, false).ok, true);
// 伺服器說成功，回來的狀態卻不是他要的：當沒改到，不猜
for (const [body, wanted] of [
  [viewBody('revoked'), true], [viewBody('granted'), false], [{ ok: true }, true], [{ ok: true, seat: {} }, true],
  [{ ok: true, seat: { consent: {} } }, false],
]) {
  const outcome = OrgConsent.interpretSet(200, body, wanted);
  assert.equal(outcome.ok, false, `${JSON.stringify(body)}（想改成 ${wanted}）不可以當成功`);
  assert.equal(outcome.message, 'errorNetwork');
  assert.deepEqual(outcome.event, { error: 'unavailable' });
}
const EXPECTED_ERRORS = {
  identity_required: 'errorSignIn',
  auth_required: 'errorSignIn',
  auth_token_missing: 'errorSignIn',
  account_required: 'errorSignIn',
  family_cloud_identity_required: 'errorSignIn',
  account_scope_missing: 'errorSignIn',
  not_found: 'errorGone',
  consent_not_recorded: 'errorNotSaved',
  consent_not_applicable: 'errorNotApplicable',
};
assert.deepEqual({ ...OrgConsent.ERROR_MESSAGES }, EXPECTED_ERRORS, '失敗代碼對照表變了');
assert.deepEqual([...OrgConsent.STALE_SEAT_ERRORS], ['not_found', 'consent_not_applicable'], '哪幾種失敗要重讀名額');
// 後端回 consent_not_recorded 時會帶 seat（狀態維持原樣）——不可以因為有 seat 就當成功
for (const status of ['none', 'granted']) {
  const outcome = OrgConsent.interpretSet(200, { ok: false, error: 'consent_not_recorded', seat: seatItem({ status }) }, true);
  assert.equal(outcome.ok, false, 'ok 不是 true 就不算數（就算帶回來的狀態是 granted）');
  assert.equal(outcome.message, 'errorNotSaved');
}
for (const [code, message] of Object.entries(EXPECTED_ERRORS)) {
  // 後端這兩支回的是字串（{"ok": false, "error": "not_found"}）；登入把關那層回的是物件（{"error": {"code": …}}）
  for (const body of [{ ok: false, error: code }, { ok: false, error: { code, message: 'x', requestId: 'y' } }]) {
    const outcome = OrgConsent.interpretSet(200, body, true);
    assert.equal(outcome.ok, false);
    assert.equal(outcome.message, message, `失敗代碼 ${code} 應該顯示 orgConsent.${message}`);
    assert.deepEqual(outcome.event, { error: code });
  }
}
assert.equal(OrgConsent.interpretSet(401, null, true).message, 'errorSignIn', 'HTTP 401 沒帶內容也要當「請先登入」');
assert.deepEqual(OrgConsent.interpretSet(401, null, true).event, { error: 'auth_required' });
for (const [status, body] of [
  [0, null], [500, null], [403, { ok: false, error: { code: 'forbidden' } }], [200, { ok: false }], [200, 'oops'],
  [200, { ok: false, error: 'seat_id_required' }], [200, { ok: false, error: 'granted_required' }],
]) {
  const outcome = OrgConsent.interpretSet(status, body, true);
  assert.equal(outcome.ok, false, `${status} ${JSON.stringify(body)} 不可以當成功`);
  assert.equal(outcome.message, 'errorNetwork', `${status} ${JSON.stringify(body)} 應該說「連不上、沒有改到」`);
  assert.deepEqual(outcome.event, { error: 'unavailable' }, '不認得的代碼不照抄進事件');
}

// ---------- C. 文案 ----------
const STATIC_KEYS = ['seesTitle', ...SEES, 'neverTitle', ...NEVER, 'anytime'];
const messageKeys = {};   // MESSAGES 的名字 → { key, fallback }
for (const [name, render] of Object.entries(OrgConsent.MESSAGES)) {
  messageKeys[name] = render((key, fallback) => ({ key, fallback }), { org: 'X' });
  assert.equal(messageKeys[name].key, `orgConsent.${name}`, `MESSAGES.${name} 綁的鍵名不對`);
}
for (const message of ['title', 'switchLabel', 'orgFallback', 'stateOn', 'stateOff', 'rowOn', 'rowOff', 'saving',
  'savedOn', 'savedOff', 'fromSeatCode', ...new Set(Object.values(EXPECTED_ERRORS)), 'errorNetwork']) {
  assert.ok(messageKeys[message], `org-consent.js 的 MESSAGES 少了 ${message}`);
}
const requiredKeys = [
  ...STATIC_KEYS.map((name) => `orgConsent.${name}`),
  ...Object.values(messageKeys).map(({ key }) => key),
];
const placeholdersOf = (text) => (String(text).match(/\{[A-Za-z][A-Za-z0-9_]*\}/g) || []).sort();
const zhKeys = Object.keys(catalogs['zh-TW']).filter((key) => key.startsWith('orgConsent.')).sort();
assert.deepEqual(zhKeys, [...requiredKeys].sort(), '語系檔的 orgConsent.* 鍵要跟畫面／程式用到的完全一致（不多不少）');
// 公文字、禁用字（老闆親訂：白話、不煽情、不後台腔；對外不用「追蹤」「監測」）
const BANNED = {
  'zh-TW': /追蹤|監測|監控|同意書|授權|資料處理|個資|用戶|您|稽核|紀錄|寫入/,
  en: /\b(track|tracking|monitor|monitoring|surveillance|consent form|authoriz\w*|data processing|audit\w*|log|logged)\b/i,
  ja: /団体|追跡|監視|同意書|データ処理|監査|ログ(?!イン)/,
  es: /\b(rastre\w*|monitor\w*|vigil\w*|consentimiento|autoriz\w*|tratamiento de datos|auditor\w*|registro)\b/i,
};
for (const locale of LOCALES) {
  assert.deepEqual(
    Object.keys(catalogs[locale]).filter((key) => key.startsWith('orgConsent.')).sort(),
    zhKeys,
    `${locale} 的 orgConsent.* 鍵跟繁中不一致`,
  );
  for (const key of requiredKeys) {
    const value = catalogs[locale][key];
    assert.equal(typeof value, 'string', `${locale} 少了 ${key}`);
    assert.ok(value.trim(), `${locale} 的 ${key} 是空的`);
    assert.deepEqual(placeholdersOf(value), placeholdersOf(catalogs['zh-TW'][key]), `${locale} 的 ${key} 佔位字跟繁中不一樣`);
    assert.ok(!BANNED[locale].test(value), `${locale} 的 ${key} 用了公文字或禁用字：${value}`);
    if (locale === 'en' || locale === 'es') {
      assert.ok(!/\p{Script=Han}/u.test(value), `${locale} 的 ${key} 混到中文`);
      // 彎的撇號在沒載到拉丁字型時會被排成全形、字中間多一個空格（#704 踩過）
      assert.ok(!/[‘’]/.test(value), `${locale} 的 ${key} 要用直的撇號`);
    }
  }
}
for (const [name, { key, fallback }] of Object.entries(messageKeys)) {
  assert.equal(fallback, catalogs['zh-TW'][key], `org-consent.js 裡 ${name} 的中文後備跟語系檔不一致`);
}
for (const key of STATIC_KEYS) {
  const inHtml = modal.match(new RegExp(`data-i18n="orgConsent\\.${key}">([^<]*)<`));
  assert.ok(inHtml, `視窗裡找不到 orgConsent.${key}`);
  assert.equal(inHtml[1], catalogs['zh-TW'][`orgConsent.${key}`], `index.html 裡 ${key} 的中文底稿跟語系檔不一致`);
}
for (const key of ['title', 'switchLabel', 'savedOn', 'savedOff', 'fromSeatCode']) {
  for (const locale of LOCALES) {
    assert.ok(catalogs[locale][`orgConsent.${key}`].includes('{org}'), `${locale} 的 orgConsent.${key} 要帶機構名稱`);
  }
}
// 長輩看的字要短：清單每一項、開關那句都有上限（中日文算字、英西文算字母）
const LIMITS = { 'zh-TW': { item: 36, label: 24 }, ja: { item: 48, label: 28 }, en: { item: 110, label: 50 }, es: { item: 125, label: 56 } };
for (const locale of LOCALES) {
  for (const key of [...SEES, ...NEVER]) {
    assert.ok(catalogs[locale][`orgConsent.${key}`].length <= LIMITS[locale].item,
      `${locale} 的 orgConsent.${key} 太長（${catalogs[locale][`orgConsent.${key}`].length} > ${LIMITS[locale].item}）`);
  }
  assert.ok(catalogs[locale]['orgConsent.switchLabel'].length <= LIMITS[locale].label, `${locale} 的開關那句太長`);
}
// 日文對照護機構用「施設」（官網 site-src 與 B2B 網站 b2b-src 的日文都這樣寫），不用「団体」
for (const [key, value] of Object.entries(catalogs.ja)) {
  if (key.startsWith('orgConsent.') || key.startsWith('seatCode.')) {
    assert.ok(!value.includes('団体'), `ja 的 ${key} 還在用「団体」，要統一成「施設」`);
  }
}
assert.ok(catalogs.ja['seatCode.entry'].includes('施設') && catalogs.ja['orgConsent.orgFallback'].includes('施設'));

// ---------- B2. 真的把視窗跑起來（假畫面、假網路） ----------
function fakeElement(id) {
  const classes = new Set();
  const listeners = {};
  const attributes = {};
  return {
    id,
    value: '',
    textContent: '',
    disabled: false,
    hidden: false,
    selectionStart: 0,
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
      toggle: (name, force) => { if (force) classes.add(name); else classes.delete(name); },
    },
    setAttribute(name, value) { attributes[name] = String(value); },
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(attributes, name) ? attributes[name] : null; },
    addEventListener(type, handler) { (listeners[type] = listeners[type] || []).push(handler); },
    async fire(type, event = {}) {
      for (const handler of listeners[type] || []) await handler({ target: this, preventDefault() {}, ...event });
    },
    focus() {},
  };
}

const ELEMENT_IDS = ['orgConsentRow', 'orgConsentRowTitle', 'orgConsentRowState', 'orgConsentRowDot', 'orgConsentRowDotLabel',
  'orgConsentModal', 'orgConsentClose', 'orgConsentTitle', 'orgConsentSwitch', 'orgConsentSwitchLabel', 'orgConsentKnob',
  'orgConsentMsg', 'orgConsentDone', 'seatCodeConsentBtn', 'seatCodeEntry'];

function createApp({ loggedIn = true, locale = 'zh-TW', realDom = false } = {}) {
  const elements = Object.fromEntries(ELEMENT_IDS.map((id) => [id, fakeElement(id)]));
  if (realDom) {
    for (const element of Object.values(elements)) {
      element.children = [];
      element.replaceChildren = (...nodes) => { element.children = nodes; };
    }
  }
  // 畫面檔上的初始狀態：入口與次要按鈕收著
  elements.orgConsentRow.hidden = true;
  elements.seatCodeConsentBtn.hidden = true;
  const calls = { fetch: [], track: [], seatCodeClose: 0 };
  const state = { loggedIn };
  const windowListeners = {};
  const documentListeners = {};
  const win = {
    document: {
      readyState: 'complete',
      getElementById: (id) => elements[id] || null,
      addEventListener(type, handler) { (documentListeners[type] = documentListeners[type] || []).push(handler); },
      ...(realDom ? {
        createElement: (tag) => ({ tag, className: '', textContent: '' }),
        createTextNode: (text) => ({ text }),
      } : {}),
    },
    addEventListener(type, handler) { (windowListeners[type] = windowListeners[type] || []).push(handler); },
    // 逾時計時器不要拖住測試：有些情境故意不回應（例如重讀名額那一次），12 秒的逾時不該讓整支多等 12 秒。
    setTimeout: (handler, ms) => { const timer = setTimeout(handler, ms); timer.unref(); return timer; },
    clearTimeout,
    AbortController,
    MuneaI18n: {
      t(key, values, fallback) {
        let text = catalogs[locale][key] || fallback;
        for (const [name, value] of Object.entries(values || {})) text = text.split(`{${name}}`).join(String(value));
        return text;
      },
    },
    MuneaSeatCode: { close() { calls.seatCodeClose += 1; } },
    fetch(url, options) {
      return new Promise((resolve, reject) => { calls.fetch.push({ url, options, resolve, reject }); });
    },
    __muneaOrgConsentBridge: {
      brainURL: (pathname) => `https://brain.example${pathname}`,
      authHeaders: async (base) => ({ ...base, Authorization: 'Bearer token-for-test', 'X-Munea-Key': 'key-for-test' }),
      isLoggedIn: () => state.loggedIn,
      track(name, properties) { calls.track.push({ name, properties }); },
    },
  };
  const controller = OrgConsent.mount(win);
  const tick = async () => { for (let i = 0; i < 4; i += 1) await new Promise((resolve) => setImmediate(resolve)); };
  const requests = (pathname) => calls.fetch.filter(({ url }) => url === `https://brain.example${pathname}`);
  return {
    elements,
    calls,
    controller,
    state,
    tick,
    statusCalls: () => requests('/org-consent'),
    setCalls: () => requests('/org-consent/set'),
    shown: () => elements.orgConsentModal.classList.contains('show'),
    checked: () => elements.orgConsentSwitch.getAttribute('aria-checked'),
    async reply(call, status, body) {
      call.resolve({ status, ok: status >= 200 && status < 300, json: async () => body });
      await tick();
    },
    async fail(call) { call.reject(new Error('network down')); await tick(); },
    async fireWindow(type, detail) { for (const handler of windowListeners[type] || []) await handler({ detail }); await tick(); },
    async clickDocument(target) { for (const handler of documentListeners.click || []) await handler({ target }); await tick(); },
    // 開好 App、已登入、後端回這個名額清單
    async boot(body) {
      await tick();
      const [first] = requests('/org-consent');
      assert.ok(first, '已登入開 App 要讀一次 /org-consent');
      await this.reply(first, 200, body);
    },
  };
}

async function behaviour() {
  const zh = catalogs['zh-TW'];
  const withOrg = (key, org = ORG, catalog = zh) => catalog[key].split('{org}').join(org);

  // 沒登入：不打後端、沒有入口
  {
    const ui = createApp({ loggedIn: false });
    await ui.tick();
    assert.equal(ui.calls.fetch.length, 0, '沒登入不可以打後端');
    assert.equal(ui.elements.orgConsentRow.hidden, true, '沒登入沒有入口');
  }

  // 已登入、沒有名額：設定頁不多東西
  {
    const ui = createApp();
    await ui.tick();
    const [{ url, options }] = ui.calls.fetch;
    assert.equal(url, 'https://brain.example/org-consent', '查名額要打 /org-consent（網址由 app.js 的 brainURL 組）');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers.Authorization, 'Bearer token-for-test', '要帶登入證（app.js 的 muneaAuthHeaders）');
    assert.equal(options.headers['X-Munea-Key'], 'key-for-test', '要帶通行碼');
    assert.deepEqual(JSON.parse(options.body), {}, '查名額不帶 accountId 之類的身分（身分只靠登入證）');
    await ui.boot(statusBody());
    assert.equal(ui.elements.orgConsentRow.hidden, true, '沒有機構名額的人，設定頁不可以多出這一列');
    assert.equal(ui.setCalls().length, 0);
  }

  // 名額是企業福利（esg）：不顯示——企業那邊永遠只看彙總，開關沒有作用
  {
    const ui = createApp();
    await ui.boot(statusBody(seatItem({ kind: 'esg', status: 'none' })));
    assert.equal(ui.elements.orgConsentRow.hidden, true, '企業福利的名額不可以顯示開關');
    const after = ui.controller.afterSeatCode();
    await ui.tick();
    await ui.reply(ui.statusCalls()[1], 200, statusBody(seatItem({ kind: 'esg' })));
    await after;
    assert.equal(ui.elements.seatCodeConsentBtn.hidden, true, '企業福利的開通碼成功畫面不可以多出次要按鈕');
  }

  // 讀不到（斷線、後端錯）：不顯示入口，也不亂報錯
  for (const respond of ['fail', 500, 'not-ok']) {
    const ui = createApp();
    await ui.tick();
    const [first] = ui.statusCalls();
    if (respond === 'fail') await ui.fail(first);
    else if (respond === 500) await ui.reply(first, 500, null);
    else await ui.reply(first, 200, { ok: false, error: 'identity_required' });
    assert.equal(ui.elements.orgConsentRow.hidden, true, `查名額失敗（${respond}）時不顯示入口`);
    assert.equal(ui.calls.track.length, 0);
  }

  // 照護機構的名額：有入口、預設關；打開 → 處理中 → 開好了；再關掉
  {
    const ui = createApp();
    const { orgConsentRow: row, orgConsentSwitch: toggle, orgConsentMsg: message, orgConsentKnob: knob } = ui.elements;
    await ui.boot(statusBody(seatItem()));
    assert.equal(row.hidden, false, '有照護機構名額要顯示入口');
    assert.equal(ui.elements.orgConsentRowTitle.textContent, `${ORG} 看得到什麼`, '入口標題要帶機構名稱');
    assert.equal(ui.elements.orgConsentRowState.textContent, zh['orgConsent.rowOff'], '沒設定過，入口要寫「沒開」');
    assert.equal(ui.elements.orgConsentRowDotLabel.textContent, zh['orgConsent.stateOff']);
    assert.equal(ui.elements.orgConsentRowDot.classList.contains('off'), true, '沒開，入口右邊的圓點是灰的');
    assert.equal(ui.shown(), false, '讀到名額不可以自己把視窗打開');

    await row.fire('click');
    assert.equal(ui.shown(), true, '點入口要開視窗');
    assert.equal(ui.elements.orgConsentTitle.textContent, `${ORG} 看得到什麼`);
    assert.equal(ui.elements.orgConsentSwitchLabel.textContent, `讓 ${ORG} 的照護人員看到我的近況`);
    assert.equal(ui.checked(), 'false', '預設關');
    assert.equal(knob.classList.contains('on'), false, '預設關');
    assert.equal(message.textContent, '');
    assert.equal(ui.setCalls().length, 0, '打開視窗不可以順便幫他打開開關');

    // 按開關：處理中、不能連點、開關還沒動
    const pending = toggle.fire('click');
    await ui.tick();
    assert.equal(message.textContent, zh['orgConsent.saving'], '送出後要顯示「處理中…」');
    assert.equal(message.classList.contains('busy'), true);
    assert.equal(toggle.disabled, true, '處理中不可以再按');
    assert.equal(toggle.getAttribute('aria-busy'), 'true');
    assert.equal(ui.checked(), 'false', '伺服器還沒說好，開關不可以先動');
    assert.equal(knob.classList.contains('on'), false, '伺服器還沒說好，開關不可以先動');
    await toggle.fire('click');
    await ui.tick();
    assert.equal(ui.setCalls().length, 1, '處理中重複按不可以送第二次');

    const [{ url, options }] = ui.setCalls();
    assert.equal(url, 'https://brain.example/org-consent/set', '改開關要打 /org-consent/set');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers.Authorization, 'Bearer token-for-test', '要帶登入證');
    assert.equal(options.headers['X-Munea-Key'], 'key-for-test', '要帶通行碼');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(options.body), { seatId: SEAT_ID, granted: true }, '打開＝{ seatId, granted: true }，不帶別的');

    await ui.reply(ui.setCalls()[0], 200, viewBody('granted'));
    await pending;
    assert.equal(ui.checked(), 'true', '伺服器說好了，開關才變成開');
    assert.equal(knob.classList.contains('on'), true);
    assert.equal(toggle.disabled, false);
    assert.equal(toggle.getAttribute('aria-busy'), 'false');
    assert.equal(message.textContent, `開好了。${ORG} 的照護人員現在看得到你的近況。`);
    assert.equal(message.classList.contains('ok'), true);
    assert.equal(message.classList.contains('err'), false);
    assert.equal(message.classList.contains('busy'), false);
    assert.equal(ui.elements.orgConsentRowState.textContent, zh['orgConsent.rowOn'], '入口那一列要跟著變「已開」');
    assert.equal(ui.elements.orgConsentRowDot.classList.contains('off'), false);
    assert.deepEqual(ui.calls.track, [{ name: 'org_consent_set', properties: { result: 'granted' } }]);

    // 再按一次＝關
    const closing = toggle.fire('click');
    await ui.tick();
    assert.equal(ui.checked(), 'true', '關的請求還沒回來，開關留在開');
    assert.deepEqual(JSON.parse(ui.setCalls()[1].options.body), { seatId: SEAT_ID, granted: false }, '關掉＝{ seatId, granted: false }');
    await ui.reply(ui.setCalls()[1], 200, viewBody('revoked'));
    await closing;
    assert.equal(ui.checked(), 'false');
    assert.equal(knob.classList.contains('on'), false);
    assert.equal(message.textContent, `關好了。${ORG} 的照護人員現在看不到了。`);
    assert.equal(ui.elements.orgConsentRowState.textContent, zh['orgConsent.rowOff']);
    assert.deepEqual(ui.calls.track[1], { name: 'org_consent_set', properties: { result: 'revoked' } });

    // 產品事件：只有結果，找不到機構名稱與名額代號
    const serialized = JSON.stringify(ui.calls.track);
    assert.ok(!serialized.includes(ORG) && !serialized.includes(SEAT_ID) && !serialized.includes('seat'),
      '產品事件不可以帶機構名稱或名額代號');
    for (const { properties } of ui.calls.track) assert.equal(Object.keys(properties).length, 1, '事件只帶 { result } 或 { error }');

    // 完成鍵、關閉鍵都關視窗；再打開時上一次的訊息清掉
    await ui.elements.orgConsentDone.fire('click');
    assert.equal(ui.shown(), false, '按「完成」要關視窗');
    await row.fire('click');
    assert.equal(message.textContent, '', '重新打開視窗，上一次的結果訊息要清掉');
    await ui.elements.orgConsentClose.fire('click');
    assert.equal(ui.shown(), false, '按關閉鍵要關視窗');
    assert.equal(ui.setCalls().length, 2, '開關視窗不可以多送請求');
  }

  // 原本就開著的人：入口寫「已開」、開關是開的
  {
    const ui = createApp();
    await ui.boot(statusBody(seatItem({ status: 'granted' })));
    assert.equal(ui.elements.orgConsentRowState.textContent, zh['orgConsent.rowOn']);
    assert.equal(ui.checked(), 'true');
    assert.equal(ui.elements.orgConsentKnob.classList.contains('on'), true);
  }

  // 每一種失敗：開關留在原位、講原因、可以再按、事件只記原因
  const failures = [
    { label: '斷線', respond: (ui, call) => ui.fail(call), text: zh['orgConsent.errorNetwork'], event: { error: 'unavailable' } },
    { label: 'HTTP 500', respond: (ui, call) => ui.reply(call, 500, null), text: zh['orgConsent.errorNetwork'], event: { error: 'unavailable' } },
    { label: 'HTTP 401', respond: (ui, call) => ui.reply(call, 401, { ok: false, error: { code: 'auth_token_missing' } }),
      text: zh['orgConsent.errorSignIn'], event: { error: 'auth_token_missing' } },
    { label: 'identity_required', respond: (ui, call) => ui.reply(call, 200, { ok: false, error: 'identity_required' }),
      text: zh['orgConsent.errorSignIn'], event: { error: 'identity_required' } },
    { label: 'not_found', respond: (ui, call) => ui.reply(call, 200, { ok: false, error: 'not_found' }),
      text: zh['orgConsent.errorGone'], event: { error: 'not_found' } },
    { label: 'consent_not_recorded（同意留不下來，這次不算數）',
      respond: (ui, call, wanted) => ui.reply(call, 200, { ok: false, error: 'consent_not_recorded', seat: seatItem({ status: wanted ? 'none' : 'granted' }) }),
      text: zh['orgConsent.errorNotSaved'], event: { error: 'consent_not_recorded' } },
    { label: 'consent_not_applicable（其實是企業名額）', respond: (ui, call) => ui.reply(call, 200, { ok: false, error: 'consent_not_applicable' }),
      text: zh['orgConsent.errorNotApplicable'], event: { error: 'consent_not_applicable' } },
    { label: '回成功但狀態對不上', respond: (ui, call, wanted) => ui.reply(call, 200, viewBody(wanted ? 'revoked' : 'granted')),
      text: zh['orgConsent.errorNetwork'], event: { error: 'unavailable' } },
  ];
  for (const failure of failures) {
    for (const startGranted of [false, true]) {
      const ui = createApp();
      const { orgConsentSwitch: toggle, orgConsentMsg: message, orgConsentKnob: knob } = ui.elements;
      await ui.boot(statusBody(seatItem({ status: startGranted ? 'granted' : 'none' })));
      await ui.elements.orgConsentRow.fire('click');
      const pending = toggle.fire('click');
      await ui.tick();
      await failure.respond(ui, ui.setCalls()[0], !startGranted);
      await pending;
      const label = `${failure.label}（原本${startGranted ? '開' : '關'}）`;
      assert.equal(ui.checked(), String(startGranted), `${label}：失敗時開關要留在原位`);
      assert.equal(knob.classList.contains('on'), startGranted, `${label}：失敗時開關要留在原位`);
      assert.equal(ui.elements.orgConsentRowState.textContent, zh[startGranted ? 'orgConsent.rowOn' : 'orgConsent.rowOff'],
        `${label}：入口那一列不可以變`);
      assert.equal(message.textContent, failure.text, `${label}：顯示的句子不對`);
      assert.equal(message.classList.contains('err'), true, `${label}：要用失敗的樣式`);
      assert.equal(message.classList.contains('ok'), false, `${label}：不可以用成功的樣式`);
      assert.equal(toggle.disabled, false, `${label}：失敗後要能再按`);
      assert.deepEqual(ui.calls.track, [{ name: 'org_consent_set', properties: failure.event }], `${label}：事件內容不對`);
      // 再按一次會再送一次、方向一樣
      const retry = toggle.fire('click');
      await ui.tick();
      assert.equal(ui.setCalls().length, 2, `${label}：失敗後再按要能重送`);
      assert.deepEqual(JSON.parse(ui.setCalls()[1].options.body), { seatId: SEAT_ID, granted: !startGranted }, `${label}：重送的方向要一樣`);
      await ui.reply(ui.setCalls()[1], 200, viewBody(startGranted ? 'revoked' : 'granted'));
      await retry;
      assert.equal(ui.checked(), String(!startGranted), `${label}：重送成功後開關才動`);
    }
  }

  // 名額對不上了（其實是企業的、或已經不在）：講原因之外重讀一次，設定頁的入口跟著收掉；其他失敗不重讀
  for (const [error, reread] of [['consent_not_applicable', true], ['not_found', true], ['consent_not_recorded', false], ['identity_required', false]]) {
    const ui = createApp();
    await ui.boot(statusBody(seatItem()));
    await ui.elements.orgConsentRow.fire('click');
    const pending = ui.elements.orgConsentSwitch.fire('click');
    await ui.tick();
    await ui.reply(ui.setCalls()[0], 200, { ok: false, error });
    await pending;
    await ui.tick();
    assert.equal(ui.statusCalls().length, reread ? 2 : 1, `${error}：${reread ? '要' : '不用'}重讀名額`);
    if (reread) {
      await ui.reply(ui.statusCalls()[1], 200, error === 'not_found' ? statusBody() : statusBody(seatItem({ kind: 'esg' })));
      assert.equal(ui.elements.orgConsentRow.hidden, true, `${error}：重讀後設定頁的入口要收掉`);
      assert.equal(ui.elements.orgConsentMsg.textContent, zh[`orgConsent.${EXPECTED_ERRORS[error]}`], `${error}：視窗裡那句原因要留著`);
      assert.equal(ui.checked(), 'false');
    }
  }

  // 視窗開著時登入過期：不送，直接請他先登入
  {
    const ui = createApp();
    await ui.boot(statusBody(seatItem()));
    await ui.elements.orgConsentRow.fire('click');
    ui.state.loggedIn = false;
    await ui.elements.orgConsentSwitch.fire('click');
    await ui.tick();
    assert.equal(ui.setCalls().length, 0, '沒登入不可以送出');
    assert.equal(ui.elements.orgConsentMsg.textContent, zh['orgConsent.errorSignIn']);
    assert.equal(ui.checked(), 'false');
  }

  // 登出：入口收掉
  {
    const ui = createApp();
    await ui.boot(statusBody(seatItem({ status: 'granted' })));
    assert.equal(ui.elements.orgConsentRow.hidden, false);
    ui.state.loggedIn = false;
    await ui.fireWindow('munea:auth-state', { status: 'signed-out' });
    assert.equal(ui.elements.orgConsentRow.hidden, true, '登出後入口要收掉（下一個人不可以看到上一個人的機構）');
    assert.equal(ui.checked(), 'false');
  }

  // 登入：重讀一次
  {
    const ui = createApp({ loggedIn: false });
    await ui.tick();
    ui.state.loggedIn = true;
    await ui.fireWindow('munea:auth-state', { status: 'signed-in' });
    assert.equal(ui.statusCalls().length, 1, '登入後要讀一次名額');
    await ui.reply(ui.statusCalls()[0], 200, statusBody(seatItem()));
    assert.equal(ui.elements.orgConsentRow.hidden, false);
  }

  // 點「設定」分頁會重讀，但 30 秒內不重複打
  {
    const ui = createApp();
    await ui.boot(statusBody());
    const settingsTab = { closest: (selector) => (selector === '.tab-btn[data-view="settings"]' ? {} : null) };
    await ui.clickDocument(settingsTab);
    assert.equal(ui.statusCalls().length, 1, '剛讀過，點「設定」分頁不重複打後端');
    await ui.clickDocument({ closest: () => null });
    assert.equal(ui.statusCalls().length, 1, '點別的地方不打後端');
  }

  // 開通碼成功畫面的次要按鈕：只有照護機構的名額才出現；按了只是帶去視窗，不會自動打開開關
  {
    const ui = createApp();
    const offer = ui.elements.seatCodeConsentBtn;
    await ui.boot(statusBody());
    assert.equal(offer.hidden, true, '還沒綁名額，次要按鈕收著');
    const after = ui.controller.afterSeatCode();
    await ui.tick();
    assert.equal(offer.hidden, true, '還沒讀到名額之前不可以先把按鈕拿出來');
    assert.equal(ui.statusCalls().length, 2, '開通碼綁好後要重讀一次名額（不受 30 秒間隔限制）');
    await ui.reply(ui.statusCalls()[1], 200, statusBody(seatItem()));
    await after;
    assert.equal(offer.hidden, false, '綁到照護機構的名額，成功畫面要多一顆次要按鈕');
    assert.equal(offer.textContent, `設定 ${ORG} 看得到什麼`);
    assert.equal(ui.elements.orgConsentRow.hidden, false, '設定頁的入口也要跟著出現');
    assert.equal(ui.shown(), false, '不可以自己把視窗打開');
    assert.equal(ui.setCalls().length, 0, '綁好名額不可以自動幫他打開開關');

    await offer.fire('click');
    assert.equal(ui.calls.seatCodeClose, 1, '按次要按鈕要先把開通碼視窗關掉');
    assert.equal(ui.shown(), true, '按次要按鈕要開「看得到什麼」視窗');
    assert.equal(ui.checked(), 'false', '帶過來時開關還是關的');
    assert.equal(offer.hidden, true, '用過就收起來');
    await ui.tick();
    assert.equal(ui.setCalls().length, 0, '按次要按鈕只是帶去視窗，不可以自動幫他打開開關');
    assert.equal(ui.calls.track.length, 0);
  }
  {
    // 重新打開開通碼視窗＝新的一輪，上一輪留下的按鈕要收起來
    const ui = createApp();
    await ui.boot(statusBody(seatItem()));
    const after = ui.controller.afterSeatCode();
    await ui.tick();
    await ui.reply(ui.statusCalls()[1], 200, statusBody(seatItem()));
    await after;
    assert.equal(ui.elements.seatCodeConsentBtn.hidden, false);
    await ui.elements.seatCodeEntry.fire('click');
    assert.equal(ui.elements.seatCodeConsentBtn.hidden, true, '重新打開開通碼視窗，上一輪的次要按鈕要收起來');
  }

  // 機構名稱空白：用「照護機構」頂著
  {
    const ui = createApp();
    await ui.boot(statusBody(seatItem({ name: '' })));
    assert.equal(ui.elements.orgConsentRowTitle.textContent, '照護機構 看得到什麼');
    assert.equal(ui.elements.orgConsentSwitchLabel.textContent, '讓 照護機構 的照護人員看到我的近況');
  }

  // 截圖工具是直接把視窗打開（沒有名額資料）：字要齊、開關是關的
  {
    const ui = createApp({ loggedIn: false });
    await ui.tick();
    assert.equal(ui.elements.orgConsentTitle.textContent, '照護機構 看得到什麼', '還沒有名額資料，標題也要有字');
    assert.equal(ui.elements.orgConsentSwitchLabel.textContent, '讓 照護機構 的照護人員看到我的近況');
    assert.equal(ui.checked(), 'false');
  }

  // 真的瀏覽器裡（有 createElement）：機構名稱後面那一截包成一塊（.oc-keep），換行時不會把詞拆開；
  // 整句讀起來（textContent）還是同一句話。機構名稱在句尾的語言（西文標題）沒有後半截，就不包。
  for (const [locale, id, key] of [['zh-TW', 'orgConsentSwitchLabel', 'switchLabel'], ['ja', 'orgConsentTitle', 'title'],
    ['en', 'orgConsentRowTitle', 'title'], ['es', 'orgConsentTitle', 'title']]) {
    const ui = createApp({ locale, realDom: true });
    await ui.boot(statusBody(seatItem()));
    const node = ui.elements[id];
    const template = catalogs[locale][`orgConsent.${key}`];
    const [lead, tail] = template.split('{org}');
    assert.equal(node.textContent, template.split('{org}').join(ORG), `${locale} ${key}：整句要完整`);
    if (tail.trim()) {
      assert.equal(node.children.length, 2, `${locale} ${key}：要拆成「前半＋機構名稱」與「後半」兩塊`);
      assert.equal(node.children[0].text, lead + ORG + (/^\s/.test(tail) ? ' ' : ''));
      assert.equal(node.children[1].className, 'oc-keep');
      assert.equal(node.children[1].textContent, tail.trim());
    } else {
      assert.equal(node.children.length, 0, `${locale} ${key}：機構名稱在句尾，不用包`);
    }
  }

  // 英、日、西：句子帶得進機構名稱，換語言會重畫
  for (const locale of ['en', 'ja', 'es']) {
    const ui = createApp({ locale });
    await ui.boot(statusBody(seatItem()));
    await ui.elements.orgConsentRow.fire('click');
    assert.equal(ui.elements.orgConsentTitle.textContent, withOrg('orgConsent.title', ORG, catalogs[locale]));
    assert.ok(ui.elements.orgConsentTitle.textContent.includes(ORG));
    const pending = ui.elements.orgConsentSwitch.fire('click');
    await ui.tick();
    assert.equal(ui.elements.orgConsentMsg.textContent, catalogs[locale]['orgConsent.saving']);
    await ui.reply(ui.setCalls()[0], 200, viewBody('granted'));
    await pending;
    assert.equal(ui.elements.orgConsentMsg.textContent, withOrg('orgConsent.savedOn', ORG, catalogs[locale]));
    await ui.fireWindow('munea:locale-ready');
    assert.equal(ui.elements.orgConsentRowState.textContent, catalogs[locale]['orgConsent.rowOn']);
  }
  assert.equal(withOrg('orgConsent.title', ORG, catalogs.en), 'What 安心日照中心 can see');

  // 開通碼那支（seat-code.js）：成功才通知同意開關重讀；失敗不通知
  for (const { body, expected } of [
    { body: { ok: true, result: 'activated', alreadyYours: false, organizationName: ORG, planTier: 'plus' }, expected: 1 },
    { body: { ok: true, result: 'registered', alreadyYours: false, organizationName: ORG, planTier: 'plus' }, expected: 1 },
    { body: { ok: false, error: { code: 'code_not_found' } }, expected: 0 },
  ]) {
    const elements = Object.fromEntries(['seatCodeModal', 'seatCodeEntry', 'seatCodeClose', 'seatCodeInput', 'seatCodeMsg', 'seatCodeBtn']
      .map((id) => [id, fakeElement(id)]));
    let notified = 0;
    let respond = null;
    const controller = SeatCode.mount({
      document: { readyState: 'complete', getElementById: (id) => elements[id] || null, addEventListener() {} },
      addEventListener() {},
      setTimeout,
      clearTimeout,
      AbortController,
      fetch: () => new Promise((resolve) => { respond = resolve; }),
      MuneaOrgConsent: { afterSeatCode() { notified += 1; } },
      __muneaSeatCodeBridge: {
        brainURL: (pathname) => pathname,
        authHeaders: async (base) => base,
        isLoggedIn: () => true,
        requireLogin: () => true,
        track() {},
        refreshPlan() {},
      },
    });
    controller.open();
    elements.seatCodeInput.value = '1234-5678';
    const pending = elements.seatCodeBtn.fire('click');
    await new Promise((resolve) => setImmediate(resolve));
    respond({ status: 200, json: async () => body });
    await pending;
    assert.equal(notified, expected, `開通碼結果 ${JSON.stringify(body.result || body.error)}：通知同意開關的次數不對`);
  }
  assert.ok(/next\.ok && win\.MuneaOrgConsent/.test(seatCodeSource), 'seat-code.js 只在成功時通知 org-consent.js');
}

// 等不到回應的 await 會讓 Node 靜靜結束、看起來像通過。沒走到最後一行就算失敗。
let finished = false;
process.on('exit', () => {
  if (!finished && !process.exitCode) {
    console.error('Org-consent UI FAIL：測試沒有跑完（有一個 await 永遠等不到回應）');
    process.exitCode = 1;
  }
});

behaviour().then(() => {
  finished = true;
  console.log(
    `Org-consent UI PASS：有照護機構名額才有入口（企業福利不顯示）、預設關、開關各打 ${OrgConsent.SET_PATH}、`
    + `失敗留在原位、不自動打開、事件不帶機構與名額、四語各 ${requiredKeys.length} 個 orgConsent.* 鍵、`
    + `文案對照後端 ${BACKEND_FACTS.length} 行`,
  );
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
