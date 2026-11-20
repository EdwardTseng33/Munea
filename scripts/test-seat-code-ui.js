#!/usr/bin/env node
/* 機構開通碼視窗（設定 → 機構開通碼）的守門 · 2026-11-17
 *
 * 機構發的紙卡上印「點『設定』→『機構開通碼』」，長輩照著卡片找。這支守住：
 *   A. 畫面：設定頁「訂閱與點數」卡那排小連結有「機構開通碼」，字跟卡片對得上；
 *      視窗有輸入框（數字鍵盤）、主按鈕、結果訊息區。
 *   B. 行為（真的把 web/src/seat-code.js 跑起來）：打的是 /enterprise/redeem-code、
 *      帶登入證、使用者打什麼就送什麼；每一種失敗代碼都有對應的句子；
 *      成功後鎖輸入框、按鈕變「完成」、重讀方案；產品事件不帶開通碼。
 *   C. 文案：四語都有全部 seatCode.* 鍵，程式裡的中文後備跟語系檔一致。
 *
 * 跑法：node scripts/test-seat-code-ui.js（不需網路、不需鑰匙）
 * ⚠ 還沒掛進 npm run test:launch：#694／#696 正在改 package.json 同一行，等它們合併後再補。
 */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(ROOT, relativePath), 'utf8');
const html = read('web/index.html');
const app = read('web/src/app.js');
const source = read('web/src/seat-code.js');
const LOCALES = ['zh-TW', 'en', 'ja', 'es'];
const catalogs = Object.fromEntries(
  LOCALES.map((locale) => [locale, JSON.parse(read(`web/src/i18n/${locale}.json`))]),
);
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
const planLinks = block('<div class="plan-links">', '</div>', '「訂閱與點數」卡的小連結列');
assert.ok(planLinks.includes('id="planCancelBtn"') && planLinks.includes('id="restoreBtn"'),
  '小連結列原本的「管理訂閱」「恢復購買」不見了');
const entryMatch = planLinks.match(/<button\b[^>]*\bid="seatCodeEntry"[^>]*>([^<]*)<\/button>/);
assert.ok(entryMatch, '設定頁「訂閱與點數」卡的小連結列少了「機構開通碼」入口（#seatCodeEntry）');
assert.ok(/\bdata-i18n="seatCode\.entry"/.test(entryMatch[0]), '入口連結要綁 seatCode.entry');
assert.ok(/\btype="button"/.test(entryMatch[0]), '入口連結要是 type="button"');
assert.equal(entryMatch[1], '機構開通碼', '入口的字要跟紙卡上印的「機構開通碼」一模一樣');
assert.equal(catalogs['zh-TW']['seatCode.entry'], '機構開通碼', '語系檔的入口文字要跟紙卡一樣');

const modal = block('<div class="modal-mask" id="seatCodeModal">', '\n  </div>\n', '機構開通碼視窗');
for (const id of ['seatCodeClose', 'seatCodeInput', 'seatCodeMsg', 'seatCodeBtn']) {
  assert.ok(modal.includes(`id="${id}"`), `視窗裡少了 #${id}`);
}
assert.ok(/<h2\b[^>]*\bdata-i18n="seatCode\.title"/.test(modal), '視窗標題要綁 seatCode.title');
assert.ok(/<p\b[^>]*\bdata-i18n="seatCode\.body"/.test(modal), '視窗說明要綁 seatCode.body');
const inputTag = tagWithId('seatCodeInput');
assert.ok(/\binputmode="numeric"/.test(inputTag), '輸入框要跳數字鍵盤（inputmode="numeric"）');
assert.ok(/\bautocomplete="off"/.test(inputTag), '輸入框要關掉自動填入');
assert.ok(/\bdata-i18n-placeholder="seatCode\.placeholder"/.test(inputTag), '輸入框的範例字要綁 seatCode.placeholder');
assert.ok(/\bdata-i18n-aria-label="seatCode\.inputLabel"/.test(inputTag), '輸入框要有報讀名稱（seatCode.inputLabel）');
const messageTag = tagWithId('seatCodeMsg');
assert.ok(/\baria-live="polite"/.test(messageTag), '結果訊息區要 aria-live="polite"，報讀軟體才念得到結果');
// 主按鈕與結果訊息的字由程式依狀態改寫，掛了 data-i18n 會被巡邏的翻譯層蓋回去
// （scripts/test-live-text-not-i18n-tagged.js 只掃 app.js，所以這裡自己守）。
assert.ok(!/\bdata-i18n=/.test(tagWithId('seatCodeBtn')), '主按鈕的字由程式依狀態決定，不可以掛 data-i18n');
assert.ok(!/\bdata-i18n=/.test(messageTag), '結果訊息的字由程式決定，不可以掛 data-i18n');
assert.ok(/\bdata-i18n-aria-label="accessibility\.close"/.test(tagWithId('seatCodeClose')), '關閉鍵要有報讀名稱');

assert.ok(/<script src="src\/seat-code\.js\?v=[^"]+"><\/script>/.test(html),
  'index.html 要用一般（非模組）方式載入 src/seat-code.js，並帶快取版號');
const bridgeMatch = app.match(/window\.__muneaSeatCodeBridge = \{([^}]*)\};/);
assert.ok(bridgeMatch, 'app.js 要把登入證等工具借給 seat-code.js（window.__muneaSeatCodeBridge）');
for (const tool of ['brainURL', 'authHeaders: muneaAuthHeaders', 'isLoggedIn', 'requireLogin',
  'track: trackProductEvent', 'refreshPlan: refreshServerPlanEntitlement']) {
  assert.ok(bridgeMatch[1].includes(tool), `借給 seat-code.js 的工具少了 ${tool}`);
}
// app.js 是模組，一般程式看不到它最上層的常數；通行碼只能走借來的 authHeaders。
assert.ok(!/\bMUNEA_APP_KEY\b/.test(source), 'seat-code.js 不可以自己去拿 MUNEA_APP_KEY（拿不到，通行碼會整個沒帶）');

// ---------- B1. 看懂伺服器回應 ----------
assert.equal(SeatCode.REDEEM_PATH, '/enterprise/redeem-code');
assert.equal(SeatCode.EVENT_NAME, 'seat_code_redeem');

const EXPECTED_ERRORS = {
  invalid_code_format: 'errorFormat',
  code_not_found: 'errorNotFound',
  code_already_used: 'errorUsed',
  code_expired: 'errorExpired',
  already_has_seat: 'errorHasSeat',
  too_many_attempts: 'errorTooMany',
  auth_required: 'errorSignIn',
  auth_token_missing: 'errorSignIn',
  account_required: 'errorSignIn',
  family_cloud_identity_required: 'errorSignIn',
  account_scope_missing: 'errorSignIn',
};
for (const [code, message] of Object.entries(EXPECTED_ERRORS)) {
  const outcome = SeatCode.interpretResponse(200, { ok: false, error: { code } });
  assert.equal(outcome.ok, false);
  assert.equal(outcome.message, message, `失敗代碼 ${code} 應該顯示 seatCode.${message}`);
  assert.deepEqual(outcome.event, { error: code }, `失敗代碼 ${code} 的事件只帶 { error }`);
}
// 登入類的失敗實際上是 HTTP 401（engine/server.py 的 _json_error）
assert.equal(
  SeatCode.interpretResponse(401, { ok: false, error: { code: 'auth_token_missing', message: 'x', requestId: 'y' } }).message,
  'errorSignIn',
);
assert.equal(SeatCode.interpretResponse(401, null).message, 'errorSignIn', 'HTTP 401 沒帶內容也要當「請先登入」');
assert.deepEqual(SeatCode.interpretResponse(401, null).event, { error: 'auth_required' });
for (const [status, body] of [
  [0, null], [500, null], [403, { ok: false, error: { code: 'forbidden' } }],
  [200, { ok: false, error: { code: 'redeem_failed' } }], [200, { ok: false }], [200, 'oops'],
  [200, { ok: true, result: 'something_new' }],
]) {
  const outcome = SeatCode.interpretResponse(status, body);
  assert.equal(outcome.ok, false, `${status} ${JSON.stringify(body)} 不可以當成功`);
  assert.equal(outcome.message, 'errorNetwork', `${status} ${JSON.stringify(body)} 應該說「連不上、稍後再試」`);
  assert.deepEqual(outcome.event, { error: 'unavailable' }, '不認得的代碼不照抄進事件');
}
for (const result of ['activated', 'registered', 'waiting']) {
  const outcome = SeatCode.interpretResponse(200, {
    ok: true, result, alreadyYours: false, organizationName: '安心日照中心', planTier: 'pro', waitingUntil: null,
  });
  assert.equal(outcome.ok, true);
  assert.equal(outcome.message, result);
  assert.deepEqual(outcome.values, { org: '安心日照中心', plan: 'Pro' });
  assert.deepEqual(outcome.event, { result });
  // 已經是自己的碼：不論 result，一律只說「你已經用過了」
  const again = SeatCode.interpretResponse(200, {
    ok: true, result, alreadyYours: true, organizationName: '安心日照中心', planTier: 'plus',
  });
  assert.equal(again.ok, true);
  assert.equal(again.message, 'alreadyYours', `alreadyYours 為真時（result=${result}）只顯示 alreadyYours 那句`);
}
assert.equal(SeatCode.planLabel('plus'), 'Plus');
assert.equal(SeatCode.planLabel('pro'), 'Pro');

// 輸入框顯示：純數字排成卡片上的樣子；混進別的字就完全不動（不可以把字母濾掉）
assert.equal(SeatCode.formatForDisplay('1234'), '1234');
assert.equal(SeatCode.formatForDisplay('12345'), '1234-5');
assert.equal(SeatCode.formatForDisplay('12345678'), '1234-5678');
assert.equal(SeatCode.formatForDisplay('1234-5678'), '1234-5678');
assert.equal(SeatCode.formatForDisplay('1234-'), '1234');
assert.equal(SeatCode.formatForDisplay('1234 5678'), '1234-5678');
assert.equal(SeatCode.formatForDisplay('12a45678'), '12a45678', '混進英文字母要原樣留著，交給伺服器判定打錯');
assert.equal(SeatCode.formatForDisplay('１２３４５６７８'), '１２３４５６７８', '全形數字原樣送，伺服器會處理');
assert.equal(SeatCode.formatForDisplay('123456789'), '123456789', '超過 8 碼不要偷偷截掉');

// ---------- C. 文案 ----------
const STATIC_KEYS = ['entry', 'title', 'body', 'placeholder', 'inputLabel'];
const messageKeys = {};   // MESSAGES 的名字 → { key, fallback }
for (const [name, render] of Object.entries(SeatCode.MESSAGES)) {
  messageKeys[name] = render((key, fallback) => ({ key, fallback }), { org: 'X', plan: 'Y' });
  assert.equal(messageKeys[name].key, `seatCode.${name}`, `MESSAGES.${name} 綁的鍵名不對`);
}
for (const message of new Set([...Object.values(EXPECTED_ERRORS), 'errorNetwork', 'activated', 'registered',
  'waiting', 'alreadyYours', 'submit', 'submitting', 'done'])) {
  assert.ok(messageKeys[message], `seat-code.js 的 MESSAGES 少了 ${message}`);
}
const requiredKeys = [
  ...STATIC_KEYS.map((name) => `seatCode.${name}`),
  ...Object.values(messageKeys).map(({ key }) => key),
];
const placeholdersOf = (text) => (String(text).match(/\{[A-Za-z][A-Za-z0-9_]*\}/g) || []).sort();
const zhSeatKeys = Object.keys(catalogs['zh-TW']).filter((key) => key.startsWith('seatCode.')).sort();
assert.deepEqual(zhSeatKeys, [...requiredKeys].sort(), '語系檔的 seatCode.* 鍵要跟畫面／程式用到的完全一致（不多不少）');
for (const locale of LOCALES) {
  assert.deepEqual(
    Object.keys(catalogs[locale]).filter((key) => key.startsWith('seatCode.')).sort(),
    zhSeatKeys,
    `${locale} 的 seatCode.* 鍵跟繁中不一致`,
  );
  for (const key of requiredKeys) {
    assert.equal(typeof catalogs[locale][key], 'string', `${locale} 少了 ${key}`);
    assert.ok(catalogs[locale][key].trim(), `${locale} 的 ${key} 是空的`);
    assert.deepEqual(placeholdersOf(catalogs[locale][key]), placeholdersOf(catalogs['zh-TW'][key]),
      `${locale} 的 ${key} 佔位字跟繁中不一樣`);
    if (locale === 'en' || locale === 'es') {
      assert.ok(!/\p{Script=Han}/u.test(catalogs[locale][key]), `${locale} 的 ${key} 混到中文`);
    }
  }
}
for (const [name, { key, fallback }] of Object.entries(messageKeys)) {
  assert.equal(fallback, catalogs['zh-TW'][key], `seat-code.js 裡 ${name} 的中文後備跟語系檔不一致`);
}
for (const key of ['seatCode.activated', 'seatCode.registered', 'seatCode.waiting']) {
  assert.ok(catalogs['zh-TW'][key].includes('{org}'), `${key} 要帶機構名稱`);
}
assert.ok(catalogs['zh-TW']['seatCode.activated'].includes('{plan}'), '已開通那句要帶方案名稱');

// ---------- B2. 真的把視窗跑起來（假畫面、假網路） ----------
const CODE = '1234-5678';

function fakeElement(id) {
  const classes = new Set();
  const listeners = {};
  return {
    id,
    value: '',
    textContent: '',
    disabled: false,
    focused: 0,
    selectionStart: 0,
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
      toggle: (name, force) => { if (force) classes.add(name); else classes.delete(name); },
    },
    addEventListener(type, handler) { (listeners[type] = listeners[type] || []).push(handler); },
    async fire(type, event = {}) {
      for (const handler of listeners[type] || []) await handler({ target: this, ...event });
    },
    focus() { this.focused += 1; },
  };
}

function createApp({ loggedIn = true, locale = 'zh-TW' } = {}) {
  const elements = Object.fromEntries(
    ['seatCodeModal', 'seatCodeEntry', 'seatCodeClose', 'seatCodeInput', 'seatCodeMsg', 'seatCodeBtn']
      .map((id) => [id, fakeElement(id)]),
  );
  const calls = { fetch: [], track: [], refreshPlan: 0, requireLogin: [] };
  let respond = null;
  const win = {
    document: {
      readyState: 'complete',
      getElementById: (id) => elements[id] || null,
      addEventListener() {},
    },
    addEventListener() {},
    setTimeout,
    clearTimeout,
    AbortController,
    MuneaI18n: {
      t(key, values, fallback) {
        let text = catalogs[locale][key] || fallback;
        for (const [name, value] of Object.entries(values || {})) text = text.split(`{${name}}`).join(String(value));
        return text;
      },
    },
    fetch(url, options) {
      calls.fetch.push({ url, options });
      return new Promise((resolve, reject) => { respond = { resolve, reject }; });
    },
    __muneaSeatCodeBridge: {
      brainURL: (pathname) => `https://brain.example${pathname}`,
      authHeaders: async (base) => ({ ...base, Authorization: 'Bearer token-for-test', 'X-Munea-Key': 'key-for-test' }),
      isLoggedIn: () => loggedIn,
      requireLogin(reason, feature) { calls.requireLogin.push({ reason, feature }); return loggedIn; },
      track(name, properties) { calls.track.push({ name, properties }); },
      refreshPlan() { calls.refreshPlan += 1; },
    },
  };
  const controller = SeatCode.mount(win);
  const tick = () => new Promise((resolve) => setImmediate(resolve));
  return {
    elements,
    calls,
    controller,
    tick,
    shown: () => elements.seatCodeModal.classList.contains('show'),
    async reply(status, body) {
      respond.resolve({ status, ok: status >= 200 && status < 300, json: async () => body });
      await tick();
    },
    async fail() { respond.reject(new Error('network down')); await tick(); },
    async type(text) {
      elements.seatCodeInput.value = text;
      elements.seatCodeInput.selectionStart = text.length;
      await elements.seatCodeInput.fire('input');
    },
  };
}

async function behaviour() {
  const zh = catalogs['zh-TW'];

  // 沒登入：走 App 既有的「先登入」，不開視窗
  {
    const ui = createApp({ loggedIn: false });
    await ui.elements.seatCodeEntry.fire('click');
    assert.equal(ui.shown(), false, '沒登入不可以開視窗');
    assert.deepEqual(ui.calls.requireLogin, [{ reason: zh['seatCode.errorSignIn'], feature: 'seat_code' }],
      '沒登入要走既有的登入把關，並帶「請先登入再輸入開通碼」');
  }

  // 已登入：開視窗 → 輸入 → 開通成功
  {
    const ui = createApp();
    const { seatCodeInput: input, seatCodeBtn: button, seatCodeMsg: message } = ui.elements;
    assert.equal(button.textContent, zh['seatCode.submit'], '還沒開視窗，主按鈕就要有字（截圖工具是直接把視窗打開）');
    await ui.elements.seatCodeEntry.fire('click');
    assert.equal(ui.shown(), true, '已登入點入口要開視窗');
    assert.equal(message.textContent, '');

    // 什麼都沒打：不送（送了會被算一次猜錯）
    await button.fire('click');
    assert.equal(ui.calls.fetch.length, 0, '空白不可以送出');
    assert.equal(message.textContent, zh['seatCode.errorFormat']);
    assert.equal(ui.calls.track.length, 0);

    await ui.type('12345678');
    assert.equal(input.value, CODE, '輸入 8 位數字要排成 1234-5678');
    const pending = button.fire('click');
    await ui.tick();
    assert.equal(button.textContent, zh['seatCode.submitting'], '送出後按鈕要變「開通中…」');
    assert.equal(button.disabled, true, '開通中不可以再按');
    assert.equal(input.disabled, true, '開通中輸入框先鎖住');
    await button.fire('click');
    assert.equal(ui.calls.fetch.length, 1, '開通中重複按不可以送第二次');

    const [{ url, options }] = ui.calls.fetch;
    assert.equal(url, 'https://brain.example/enterprise/redeem-code', '要打 /enterprise/redeem-code（網址由 app.js 的 brainURL 組）');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers.Authorization, 'Bearer token-for-test', '要帶登入證（app.js 的 muneaAuthHeaders）');
    assert.equal(options.headers['X-Munea-Key'], 'key-for-test', '要帶通行碼');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(options.body), { code: CODE }, '請求內容只有 code，不帶 accountId 之類的身分');

    await ui.reply(200, { ok: true, result: 'activated', alreadyYours: false, organizationName: '安心日照中心', planTier: 'plus', waitingUntil: null });
    await pending;
    assert.equal(message.textContent, '開通好了。安心日照中心 已經幫你開通 Plus 方案。');
    assert.equal(message.classList.contains('ok'), true);
    assert.equal(message.classList.contains('err'), false);
    assert.equal(input.disabled, true, '成功後輸入框鎖住');
    assert.equal(button.disabled, false);
    assert.equal(button.textContent, zh['seatCode.done'], '成功後主按鈕變「完成」');
    assert.equal(ui.calls.refreshPlan, 1, '成功後要重讀一次方案，設定頁的方案名稱才會更新');
    assert.deepEqual(ui.calls.track, [{ name: 'seat_code_redeem', properties: { result: 'activated' } }]);

    await button.fire('click');
    assert.equal(ui.shown(), false, '按「完成」要關視窗');
    assert.equal(ui.calls.fetch.length, 1, '按「完成」不可以再送一次');

    // 再打開是乾淨的
    await ui.elements.seatCodeEntry.fire('click');
    assert.equal(input.value, '');
    assert.equal(input.disabled, false);
    assert.equal(message.textContent, '');
    assert.equal(button.textContent, zh['seatCode.submit']);
  }

  // 每一種結果：句子、輸入框、按鈕、事件
  const cases = [
    ...Object.entries(EXPECTED_ERRORS).map(([code, message]) => ({
      label: code, status: code.startsWith('auth_') ? 401 : 200, body: { ok: false, error: { code } },
      text: zh[`seatCode.${message}`], ok: false, event: { error: code },
    })),
    { label: 'HTTP 500', status: 500, body: null, text: zh['seatCode.errorNetwork'], ok: false, event: { error: 'unavailable' } },
    { label: 'registered', status: 200, body: { ok: true, result: 'registered', alreadyYours: false, organizationName: '安心日照中心', planTier: 'pro' },
      text: '登記好了。等 安心日照中心 完成開通手續，方案會自動生效，不用再輸入一次。', ok: true, event: { result: 'registered' } },
    { label: 'waiting', status: 200, body: { ok: true, result: 'waiting', alreadyYours: false, organizationName: '安心日照中心', planTier: 'plus', waitingUntil: '2027-01-15T00:00:00Z' },
      text: '登記好了。你自己訂的方案比較高，會先用你自己的；到期後自動接上 安心日照中心 提供的方案。', ok: true, event: { result: 'waiting' } },
    { label: 'alreadyYours', status: 200, body: { ok: true, result: 'activated', alreadyYours: true, organizationName: '安心日照中心', planTier: 'plus' },
      text: zh['seatCode.alreadyYours'], ok: true, event: { result: 'already_yours' } },
    { label: '機構名稱空白', status: 200, body: { ok: true, result: 'activated', alreadyYours: false, organizationName: '', planTier: 'pro' },
      text: '開通好了。機構 已經幫你開通 Pro 方案。', ok: true, event: { result: 'activated' } },
  ];
  for (const testCase of cases) {
    const ui = createApp();
    const { seatCodeInput: input, seatCodeBtn: button, seatCodeMsg: message } = ui.elements;
    await ui.elements.seatCodeEntry.fire('click');
    await ui.type(CODE);
    const pending = button.fire('click');
    await ui.tick();
    await ui.reply(testCase.status, testCase.body);
    await pending;
    assert.equal(message.textContent, testCase.text, `${testCase.label}：顯示的句子不對`);
    assert.equal(message.classList.contains('ok'), testCase.ok, `${testCase.label}：成功／失敗的樣式不對`);
    assert.equal(message.classList.contains('err'), !testCase.ok, `${testCase.label}：成功／失敗的樣式不對`);
    assert.equal(input.disabled, testCase.ok, `${testCase.label}：成功才鎖輸入框，失敗要能改`);
    assert.equal(input.value, CODE, `${testCase.label}：輸入的內容要留著`);
    assert.equal(button.disabled, false, `${testCase.label}：按鈕要恢復可按`);
    assert.equal(button.textContent, testCase.ok ? zh['seatCode.done'] : zh['seatCode.submit'], `${testCase.label}：按鈕的字不對`);
    assert.equal(ui.calls.refreshPlan, testCase.ok ? 1 : 0, `${testCase.label}：成功才重讀方案`);
    assert.deepEqual(ui.calls.track, [{ name: 'seat_code_redeem', properties: testCase.event }], `${testCase.label}：事件內容不對`);
    // 事件只能帶 result 或 error 其中一個，而且整包找不到開通碼
    const serialized = JSON.stringify(ui.calls.track);
    assert.ok(!serialized.includes(CODE) && !serialized.includes('12345678') && !/1234|5678/.test(serialized),
      `${testCase.label}：產品事件不可以帶開通碼`);
    assert.equal(Object.keys(ui.calls.track[0].properties).length, 1, `${testCase.label}：事件只帶 { result } 或 { error }`);
  }

  // 斷線／逾時：說「連不上」，內容留著可以再按
  {
    const ui = createApp();
    await ui.elements.seatCodeEntry.fire('click');
    await ui.type(CODE);
    const pending = ui.elements.seatCodeBtn.fire('click');
    await ui.tick();
    await ui.fail();
    await pending;
    assert.equal(ui.elements.seatCodeMsg.textContent, zh['seatCode.errorNetwork']);
    assert.equal(ui.elements.seatCodeInput.disabled, false);
    assert.equal(ui.elements.seatCodeBtn.textContent, zh['seatCode.submit']);
    assert.deepEqual(ui.calls.track, [{ name: 'seat_code_redeem', properties: { error: 'unavailable' } }]);
  }

  // 使用者打什麼就送什麼：混進英文字母不可以被濾掉再送（需求單 9.3 第 6 條）
  {
    const ui = createApp();
    await ui.elements.seatCodeEntry.fire('click');
    await ui.type('12ab-5678');
    assert.equal(ui.elements.seatCodeInput.value, '12ab-5678');
    const pending = ui.elements.seatCodeBtn.fire('click');
    await ui.tick();
    assert.deepEqual(JSON.parse(ui.calls.fetch[0].options.body), { code: '12ab-5678' }, '混進字母要原樣送出，讓伺服器判定打錯');
    await ui.reply(200, { ok: false, error: { code: 'invalid_code_format' } });
    await pending;
    const serialized = JSON.stringify(ui.calls.track);
    assert.ok(!serialized.includes('12ab'), '產品事件不可以帶開通碼');
  }

  // 視窗開著時登入過期：不送，直接請他先登入
  {
    const ui = createApp({ loggedIn: false });
    ui.controller.open();
    await ui.type(CODE);
    await ui.elements.seatCodeBtn.fire('click');
    assert.equal(ui.calls.fetch.length, 0, '沒登入不可以送出');
    assert.equal(ui.elements.seatCodeMsg.textContent, zh['seatCode.errorSignIn']);
  }

  // 英文、西文：機構名稱空白時的頂替字落在句首要大寫；有名稱時一個字都不動
  {
    const ui = createApp({ locale: 'en' });
    await ui.elements.seatCodeEntry.fire('click');
    await ui.type(CODE);
    const pending = ui.elements.seatCodeBtn.fire('click');
    await ui.tick();
    await ui.reply(200, { ok: true, result: 'activated', alreadyYours: false, organizationName: '', planTier: 'plus' });
    await pending;
    assert.equal(ui.elements.seatCodeMsg.textContent, "You're all set. Your organization has activated the Plus plan for you.");
  }
  {
    const ui = createApp({ locale: 'en' });
    await ui.elements.seatCodeEntry.fire('click');
    await ui.type(CODE);
    const pending = ui.elements.seatCodeBtn.fire('click');
    await ui.tick();
    await ui.reply(200, { ok: true, result: 'activated', alreadyYours: false, organizationName: 'iCare 長照', planTier: 'pro' });
    await pending;
    assert.equal(ui.elements.seatCodeMsg.textContent, "You're all set. iCare 長照 has activated the Pro plan for you.");
  }
}

behaviour().then(() => {
  console.log(
    `Seat-code UI PASS：入口與視窗在、打 ${SeatCode.REDEEM_PATH}、${Object.keys(EXPECTED_ERRORS).length} 種失敗代碼都有句子、`
    + `事件不帶開通碼、四語各 ${requiredKeys.length} 個 seatCode.* 鍵`,
  );
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
