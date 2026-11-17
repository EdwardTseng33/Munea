/* 機構開通碼視窗（設定 →「訂閱與點數」卡最下面 →「機構開通碼」）· 2026-11-17
 *
 * 機構發給長輩一張卡，上面印 8 位數字（1234-5678）。長輩登入 App 後在這裡輸入，
 * 席次就綁到他的帳號。後端是 POST /enterprise/redeem-code
 * （engine/server.py 的 enterprise_redeem_code_response），設計全文在
 * docs/企業席次-後台管理與月結-需求單-2026-07-20.md 第 9 節。
 *
 * 四條規矩：
 *   1. 使用者打什麼就送什麼。全形數字、空白、橫線由伺服器處理；這裡不可以把英文字母
 *      濾掉再送——混進字母就是打錯，要讓伺服器照實判定（需求單 9.3 第 6 條）。
 *   2. 身分只靠登入證。這支是一般（非模組）程式，拿不到 app.js（模組）裡的工具，
 *      所以由 app.js 把「組網址、帶登入證與通行碼、記事件、重讀方案」借給它
 *      （window.__muneaSeatCodeBridge），這裡不自己另寫一份。
 *   3. 產品事件只記結果（{ result } 或 { error }），不記開通碼——紀錄外流就等於碼外流。
 *   4. 主按鈕與結果訊息的字由程式依狀態決定，所以畫面檔上不掛 data-i18n
 *      （巡邏的翻譯層會把它蓋回寫死的那一句，見 scripts/test-live-text-not-i18n-tagged.js）；
 *      翻譯走下面的 MESSAGES，換語言時靠 munea:locale-ready 重畫。
 *
 * 純邏輯（看懂伺服器回應、輸入框怎麼顯示）跟畫面分開，scripts/test-seat-code-ui.js 直接載入來測。
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root && root.document) root.MuneaSeatCode = api.mount(root);
}(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  const REDEEM_PATH = '/enterprise/redeem-code';
  const EVENT_NAME = 'seat_code_redeem';
  // 一般請求只等 6 秒；開通要查碼、綁席次、可能當場開會員，給寬一點，逾時就老實說連不上。
  const REQUEST_TIMEOUT_MS = 12000;

  // 伺服器的失敗代碼 → 畫面上講哪一句。沒列在這裡的一律當「連不上、稍後再試」。
  const ERROR_MESSAGES = Object.freeze({
    invalid_code_format: 'errorFormat',
    code_not_found: 'errorNotFound',
    code_already_used: 'errorUsed',
    code_expired: 'errorExpired',
    already_has_seat: 'errorHasSeat',
    too_many_attempts: 'errorTooMany',
    // 以下五種都是「登入證不在，或對不上帳號」——對使用者來說就是請先登入。
    auth_required: 'errorSignIn',
    auth_token_missing: 'errorSignIn',
    account_required: 'errorSignIn',
    family_cloud_identity_required: 'errorSignIn',
    account_scope_missing: 'errorSignIn',
  });
  const SUCCESS_RESULTS = Object.freeze(['activated', 'registered', 'waiting']);

  // 每一句都寫成 t('鍵', '中文')：文案盤點工具（scripts/i18n-surface-inventory.js）認這個寫法，
  // 才知道這些中文已經綁了四語的鍵。中文是語系檔還沒載到時的後備。
  const MESSAGES = Object.freeze({
    submit: (t) => t('seatCode.submit', '開通'),
    submitting: (t) => t('seatCode.submitting', '開通中…'),
    done: (t) => t('seatCode.done', '完成'),
    orgFallback: (t) => t('seatCode.orgFallback', '機構'),
    activated: (t, values) => t('seatCode.activated', '開通好了。{org} 已經幫你開通 {plan} 方案。', values),
    registered: (t, values) => t('seatCode.registered', '登記好了。等 {org} 完成開通手續，方案會自動生效，不用再輸入一次。', values),
    waiting: (t, values) => t('seatCode.waiting', '登記好了。你自己訂的方案比較高，會先用你自己的；到期後自動接上 {org} 提供的方案。', values),
    alreadyYours: (t) => t('seatCode.alreadyYours', '這組號碼你已經用過了，不用再輸入。'),
    errorFormat: (t) => t('seatCode.errorFormat', '開通碼是 8 個數字，請再看一下卡片上的號碼。'),
    errorNotFound: (t) => t('seatCode.errorNotFound', '找不到這組號碼，請再對一次卡片上的數字。'),
    errorUsed: (t) => t('seatCode.errorUsed', '這組號碼已經有人用過了，請跟給你號碼的機構確認。'),
    errorExpired: (t) => t('seatCode.errorExpired', '這組號碼已經失效，請跟給你號碼的機構確認。'),
    errorHasSeat: (t) => t('seatCode.errorHasSeat', '你的帳號已經有機構提供的方案了，不用再輸入。'),
    errorTooMany: (t) => t('seatCode.errorTooMany', '試太多次了，請 10 分鐘後再試。'),
    errorSignIn: (t) => t('seatCode.errorSignIn', '請先登入再輸入開通碼。'),
    errorNetwork: (t) => t('seatCode.errorNetwork', '現在連不上，請稍後再試一次。'),
  });

  // 方案名稱照 App 既有寫法（app.js 的 circlePlanLabel）：四語都叫 Plus／Pro。
  function planLabel(planTier) {
    return String(planTier || '').toLowerCase() === 'pro' ? 'Pro' : 'Plus';
  }

  // 輸入時順手把純數字排成卡片上的樣子（1234-5678），只是好對、不是驗證。
  // 只要混進別的字（英文字母、全形、超過 8 碼）就完全不動它，原樣留給伺服器判斷。
  function formatForDisplay(value) {
    const raw = String(value == null ? '' : value);
    const compact = raw.replace(/[\s-]/g, '');
    if (!/^[0-9]{0,8}$/.test(compact)) return raw;
    return compact.length > 4 ? `${compact.slice(0, 4)}-${compact.slice(4)}` : compact;
  }

  // 把一次請求的結果（HTTP 狀態碼＋回應內容）整理成畫面要用的樣子。
  // status 0＝根本沒連上（斷線、逾時、借不到工具）。
  function interpretResponse(status, body) {
    const data = body && typeof body === 'object' ? body : null;
    if (data && data.ok === true) {
      const values = {
        org: String(data.organizationName || '').trim(),
        plan: planLabel(data.planTier),
      };
      // 同一個人重複輸入自己的碼：不管席次現在是哪個狀態，只說「你已經用過了」。
      if (data.alreadyYours === true) {
        return { ok: true, message: 'alreadyYours', values, event: { result: 'already_yours' } };
      }
      if (SUCCESS_RESULTS.includes(data.result)) {
        return { ok: true, message: data.result, values, event: { result: data.result } };
      }
      // 說成功卻不是認得的結果：寧可請他稍後再試，也不要編一句「開通好了」。
      return { ok: false, message: 'errorNetwork', values: null, event: { error: 'unavailable' } };
    }
    const error = data && data.error;
    const code = String((error && typeof error === 'object' ? error.code : error) || '');
    if (Object.prototype.hasOwnProperty.call(ERROR_MESSAGES, code)) {
      return { ok: false, message: ERROR_MESSAGES[code], values: null, event: { error: code } };
    }
    if (status === 401) {
      return { ok: false, message: 'errorSignIn', values: null, event: { error: 'auth_required' } };
    }
    // 其他代碼不照抄進事件（只記認得的那幾種），一律歸成「連不上」。
    return { ok: false, message: 'errorNetwork', values: null, event: { error: 'unavailable' } };
  }

  // 把結果變成一句話。機構名稱空白時用「機構」頂著；英文、西文的頂替字是小寫，
  // 落在句首要補大寫（只在頂替時做，真的機構名稱一個字都不動）。
  function messageText(t, outcome) {
    const render = MESSAGES[outcome.message] || MESSAGES.errorNetwork;
    if (!outcome.values) return render(t);
    if (outcome.values.org) return render(t, outcome.values);
    const text = render(t, { org: MESSAGES.orgFallback(t), plan: outcome.values.plan });
    return String(text).replace(/(^|[.!?]\s+)(\p{Ll})/gu, (match, lead, letter) => lead + letter.toUpperCase());
  }

  function mount(win) {
    const doc = win.document;
    const el = (id) => doc.getElementById(id);
    const t = (key, fallback, values) => {
      if (win.MuneaI18n && typeof win.MuneaI18n.t === 'function') {
        return win.MuneaI18n.t(key, values || null, fallback);
      }
      let text = fallback;
      for (const [name, value] of Object.entries(values || {})) text = text.split(`{${name}}`).join(String(value));
      return text;
    };
    const bridge = () => win.__muneaSeatCodeBridge || null;

    // idle＝可以輸入；busy＝送出去了還沒回來；done＝綁好了，按鈕變「完成」。
    let state = 'idle';
    let outcome = null;

    function render() {
      const input = el('seatCodeInput');
      const button = el('seatCodeBtn');
      const message = el('seatCodeMsg');
      if (!input || !button || !message) return;
      button.textContent = MESSAGES[state === 'busy' ? 'submitting' : state === 'done' ? 'done' : 'submit'](t);
      button.disabled = state === 'busy';
      button.classList.toggle('busy-spin', state === 'busy');
      input.disabled = state !== 'idle';
      message.textContent = outcome ? messageText(t, outcome) : '';
      message.classList.toggle('ok', !!(outcome && outcome.ok));
      message.classList.toggle('err', !!(outcome && !outcome.ok));
    }

    function open() {
      const modal = el('seatCodeModal');
      if (!modal) return;
      // 上一筆還在路上就不要清掉，免得回應回來時畫面對不上。
      if (state !== 'busy') {
        state = 'idle';
        outcome = null;
        const input = el('seatCodeInput');
        if (input) input.value = '';
      }
      render();
      modal.classList.add('show');
    }

    function close() {
      const modal = el('seatCodeModal');
      if (modal) modal.classList.remove('show');
    }

    async function request(code) {
      const tools = bridge();
      if (!tools || typeof win.fetch !== 'function') return { status: 0, body: null };
      const controller = typeof win.AbortController === 'function' ? new win.AbortController() : null;
      const timer = win.setTimeout(() => { if (controller) controller.abort(); }, REQUEST_TIMEOUT_MS);
      try {
        const response = await win.fetch(tools.brainURL(REDEEM_PATH), {
          method: 'POST',
          headers: await tools.authHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ code }),
          signal: controller ? controller.signal : undefined,
        });
        let body = null;
        try { body = await response.json(); } catch (error) { body = null; }
        return { status: response.status, body };
      } catch (error) {
        return { status: 0, body: null };
      } finally {
        win.clearTimeout(timer);
      }
    }

    function finish(next) {
      outcome = next;
      state = next.ok ? 'done' : 'idle';
      render();
      const tools = bridge();
      // 只送結果或失敗原因——next.event 裡沒有開通碼，也不要在這裡加。
      try { if (tools && typeof tools.track === 'function') tools.track(EVENT_NAME, next.event); } catch (error) {}
      // 綁好之後重讀一次方案，設定頁的方案名稱才會跟著變（跟購買成功後呼叫的是同一支）。
      try { if (next.ok && tools && typeof tools.refreshPlan === 'function') tools.refreshPlan(); } catch (error) {}
      // 綁好的如果是照護機構的名額，成功畫面多一顆次要按鈕帶去「看得到什麼」（web/src/org-consent.js）。
      // 只是通知它重讀一次；要不要打開開關由使用者自己按，這裡不代勞。
      try {
        if (next.ok && win.MuneaOrgConsent && typeof win.MuneaOrgConsent.afterSeatCode === 'function') win.MuneaOrgConsent.afterSeatCode();
      } catch (error) {}
    }

    async function submit() {
      if (state === 'busy') return;
      if (state === 'done') { close(); return; }
      const input = el('seatCodeInput');
      if (!input) return;
      const code = input.value;
      // 什麼都沒打就不送：送了會被算成一次猜錯（10 分鐘 5 次就暫時擋）。
      if (!code.trim()) {
        outcome = { ok: false, message: 'errorFormat', values: null };
        render();
        input.focus();
        return;
      }
      // 視窗開著的時候登入過期了：不送，直接請他先登入。
      const tools = bridge();
      if (tools && typeof tools.isLoggedIn === 'function' && !tools.isLoggedIn()) {
        finish({ ok: false, message: 'errorSignIn', values: null, event: { error: 'auth_required' } });
        return;
      }
      state = 'busy';
      outcome = null;
      render();
      const response = await request(code);
      finish(interpretResponse(response.status, response.body));
    }

    function onEntry() {
      const tools = bridge();
      // 沒登入就走 App 既有的「先登入」提示（跟加入家庭圈同一套），登入後再點一次進來。
      if (tools && typeof tools.requireLogin === 'function'
        && !tools.requireLogin(MESSAGES.errorSignIn(t), 'seat_code')) return;
      open();
    }

    function onInput(event) {
      const input = event.target;
      if (event.isComposing) return;
      // 只在游標停在最後面時整理，免得在中間修改時游標被拉走。
      if (input.selectionStart !== input.value.length) return;
      const formatted = formatForDisplay(input.value);
      if (formatted !== input.value) input.value = formatted;
    }

    function bind() {
      const modal = el('seatCodeModal');
      if (!modal) return;
      const entry = el('seatCodeEntry');
      const closeButton = el('seatCodeClose');
      const button = el('seatCodeBtn');
      const input = el('seatCodeInput');
      if (entry) entry.addEventListener('click', onEntry);
      if (closeButton) closeButton.addEventListener('click', close);
      modal.addEventListener('click', (event) => { if (event.target === modal) close(); });
      if (button) button.addEventListener('click', submit);
      if (input) {
        input.addEventListener('input', onInput);
        input.addEventListener('keydown', (event) => { if (event.key === 'Enter') submit(); });
      }
      render();
    }

    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', bind, { once: true });
    else bind();
    win.addEventListener('munea:locale-ready', render);

    return Object.freeze({ open, close });
  }

  return Object.freeze({
    REDEEM_PATH,
    EVENT_NAME,
    ERROR_MESSAGES,
    MESSAGES,
    formatForDisplay,
    interpretResponse,
    messageText,
    mount,
    planLabel,
  });
}));
