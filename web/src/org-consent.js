/* 機構照護模式的同意開關（設定 →「帳號與家庭」→「{機構} 看得到什麼」）· 2026-11-17
 *
 * 照護機構給長輩一個名額之後，機構的照護人員「預設看不到這一位」；要本人（或家人）在這裡
 * 把開關打開，機構端才看得到他的近況，而且隨時可以關。設計全文：
 * docs/後台-B2B2C-產品框架設計-2026-10-28.md（Q1 拍板 A、第 4.3 節 App 端兩支接口）。
 * 後端：POST /org-consent（查）、POST /org-consent/set（改），在 engine/org_api.py。
 *
 * 五條規矩：
 *   1. 預設關。沒有名額、或名額是企業福利（clientKind 不是 care）的人，設定頁完全不多東西——
 *      企業那邊不管開不開，永遠只看得到彙總（org_api.py 的 _consented_seats），給他一顆沒作用的開關是騙人。
 *   2. 成功才改畫面。按下去先變「處理中…」不能連點；伺服器說好了，開關才動；
 *      失敗（沒網路、沒登入、後端錯）開關留在原位，講一句白話的原因。
 *   3. 絕不自動幫人打開。輸入開通碼成功後只多一顆次要按鈕把這個視窗帶出來，開不開由他自己按。
 *   4. 「看得到什麼／永遠看不到什麼」用 App 自己的四語文案（orgConsent.sees*／never*），
 *      不顯示後端回的 whatOrgSees（那是寫死的中文）。文案要跟機構端實際拿到的東西一致，
 *      對照表在 scripts/test-org-consent-ui.js 最上面。
 *   5. 產品事件只記結果（{ result } 或 { error }），不帶機構名稱與名額代號。
 *
 * 這支是一般（非模組）程式，拿不到 app.js（模組）裡的工具，所以由 app.js 把「組網址、帶登入證與
 * 通行碼、有沒有登入、記事件」借給它（window.__muneaOrgConsentBridge）。
 * 開關旁的字、狀態、結果訊息都由程式依狀態決定，所以畫面檔上不掛 data-i18n
 * （巡邏的翻譯層會把它蓋回寫死的那一句）；翻譯走下面的 MESSAGES，換語言時靠 munea:locale-ready 重畫。
 *
 * 純邏輯（挑哪個名額、看懂伺服器回應）跟畫面分開，scripts/test-org-consent-ui.js 直接載入來測。
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root && root.document) root.MuneaOrgConsent = api.mount(root);
}(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  const STATUS_PATH = '/org-consent';
  const SET_PATH = '/org-consent/set';
  const EVENT_NAME = 'org_consent_set';
  const REQUEST_TIMEOUT_MS = 12000;
  // 進設定頁時順手重讀一次，但不要每點一下就打一次後端。
  const REFRESH_MIN_INTERVAL_MS = 30000;
  // 只有照護機構（care）才有「個人層」可看；企業福利（esg）永遠只有彙總，不顯示開關。
  // 用白名單：以後多出不認得的類型，寧可先不顯示，也不要給一顆不知道會開什麼的開關。
  const APPLICABLE_KINDS = Object.freeze(['care']);

  // 這幾種都是「登入證不在，或對不上帳號」——對使用者來說就是請先登入。
  const SIGN_IN_ERRORS = Object.freeze([
    'identity_required', 'auth_required', 'auth_token_missing', 'account_required',
    'family_cloud_identity_required', 'account_scope_missing',
  ]);
  // 伺服器的失敗代碼 → 畫面上講哪一句。沒列在這裡的一律當「連不上、沒有改到」。
  const ERROR_MESSAGES = Object.freeze({
    ...Object.fromEntries(SIGN_IN_ERRORS.map((code) => [code, 'errorSignIn'])),
    not_found: 'errorGone',
  });

  // 每一句都寫成 t('鍵', '中文')：文案盤點工具（scripts/i18n-surface-inventory.js）認這個寫法，
  // 才知道這些中文已經綁了四語的鍵。中文是語系檔還沒載到時的後備。
  const MESSAGES = Object.freeze({
    title: (t, values) => t('orgConsent.title', '{org} 看得到什麼', values),
    switchLabel: (t, values) => t('orgConsent.switchLabel', '讓 {org} 的照護人員看到我的近況', values),
    orgFallback: (t) => t('orgConsent.orgFallback', '照護機構'),
    stateOn: (t) => t('orgConsent.stateOn', '已開'),
    stateOff: (t) => t('orgConsent.stateOff', '沒開'),
    rowOn: (t) => t('orgConsent.rowOn', '已開，照護人員看得到你的近況'),
    rowOff: (t) => t('orgConsent.rowOff', '沒開，照護人員看不到你的近況'),
    saving: (t) => t('orgConsent.saving', '處理中…'),
    savedOn: (t, values) => t('orgConsent.savedOn', '開好了。{org} 的照護人員現在看得到你的近況。', values),
    savedOff: (t, values) => t('orgConsent.savedOff', '關好了。{org} 的照護人員現在看不到了。', values),
    fromSeatCode: (t, values) => t('orgConsent.fromSeatCode', '設定 {org} 看得到什麼', values),
    errorSignIn: (t) => t('orgConsent.errorSignIn', '請先登入再設定。'),
    errorGone: (t) => t('orgConsent.errorGone', '找不到這個機構給你的方案，沒有改到。'),
    errorNetwork: (t) => t('orgConsent.errorNetwork', '現在連不上，沒有改到。請稍後再試一次。'),
  });

  // 從 /org-consent 的回應挑出「這個人可以設定的那個名額」。沒有就回 null（＝設定頁不多東西）。
  // 一個帳號目前只會有一個機構名額（重複輸入開通碼會被擋 already_has_seat）；萬一有多個，取第一個適用的。
  function pickSeat(body) {
    const data = body && typeof body === 'object' ? body : null;
    if (!data || data.ok !== true || !Array.isArray(data.seats)) return null;
    for (const item of data.seats) {
      if (!item || typeof item !== 'object') continue;
      const seatId = String(item.seatId || '').trim();
      const org = item.org && typeof item.org === 'object' ? item.org : {};
      if (!seatId || !APPLICABLE_KINDS.includes(org.clientKind)) continue;
      return {
        seatId,
        org: String(org.name || '').trim(),
        // 只有明確是 granted 才算開；none、revoked、看不懂的值一律當關（預設關）。
        granted: !!(item.consent && item.consent.status === 'granted'),
      };
    }
    return null;
  }

  // 把「改開關」那次請求的結果整理成畫面要用的樣子。wanted＝使用者想改成開（true）或關（false）。
  // status 0＝根本沒連上（斷線、逾時、借不到工具）。
  function interpretSet(status, body, wanted) {
    const data = body && typeof body === 'object' ? body : null;
    if (data && data.ok === true) {
      const consent = data.seat && data.seat.consent;
      const granted = !!(consent && consent.status === 'granted');
      // 伺服器說成功、而且回來的狀態真的是他要的，才算改好。對不上就當沒改到，不猜。
      if (consent && typeof consent.status === 'string' && granted === !!wanted) {
        return { ok: true, granted, message: granted ? 'savedOn' : 'savedOff', event: { result: granted ? 'granted' : 'revoked' } };
      }
      return { ok: false, granted: null, message: 'errorNetwork', event: { error: 'unavailable' } };
    }
    const error = data && data.error;
    const code = String((error && typeof error === 'object' ? error.code : error) || '');
    if (Object.prototype.hasOwnProperty.call(ERROR_MESSAGES, code)) {
      return { ok: false, granted: null, message: ERROR_MESSAGES[code], event: { error: code } };
    }
    if (status === 401) {
      return { ok: false, granted: null, message: 'errorSignIn', event: { error: 'auth_required' } };
    }
    // 其他代碼不照抄進事件（只記認得的那幾種），一律歸成「連不上」。
    return { ok: false, granted: null, message: 'errorNetwork', event: { error: 'unavailable' } };
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
    const bridge = () => win.__muneaOrgConsentBridge || null;
    const loggedIn = () => {
      const tools = bridge();
      return !!(tools && typeof tools.isLoggedIn === 'function' && tools.isLoggedIn());
    };

    // seat＝這個人可以設定的名額（null＝沒有，設定頁不顯示入口）。
    // busy＝改開關的請求送出去了還沒回來。outcome＝上一次按開關的結果（顯示在開關下面）。
    let seat = null;
    let busy = false;
    let outcome = null;
    let lastRefreshAt = 0;
    let refreshing = null;
    let seatCodeOffer = false;   // 開通碼成功畫面上那顆次要按鈕現在該不該出現

    const orgValues = () => ({ org: (seat && seat.org) || MESSAGES.orgFallback(t) });

    // 帶機構名稱的短句（標題、開關那句、按鈕）：機構名稱後面那一截包成一塊，換行時整截一起下去，
    // 不會把「看到」「照護人員」這種詞從中間拆開；機構名稱本身照常折行，再長也不會撐破版面。
    // 報讀軟體與測試讀到的還是同一句完整的話（textContent 不變）。
    function fillWithOrg(node, renderMessage, values) {
      const text = renderMessage(t, values);
      node.textContent = text;
      if (typeof doc.createElement !== 'function' || typeof node.replaceChildren !== 'function') return;
      const marker = '\u0001';
      const parts = String(renderMessage(t, { org: marker })).split(marker);
      if (parts.length !== 2 || !parts[1].trim()) return;
      const tail = doc.createElement('span');
      tail.className = 'oc-keep';
      tail.textContent = parts[1].trim();
      node.replaceChildren(doc.createTextNode(parts[0] + values.org + (/^\s/.test(parts[1]) ? ' ' : '')), tail);
    }

    function render() {
      const on = !!(seat && seat.granted);
      const values = orgValues();

      const row = el('orgConsentRow');
      if (row) row.hidden = !seat;
      const rowTitle = el('orgConsentRowTitle');
      if (rowTitle) fillWithOrg(rowTitle, MESSAGES.title, values);
      const rowState = el('orgConsentRowState');
      if (rowState) rowState.textContent = MESSAGES[on ? 'rowOn' : 'rowOff'](t);
      const rowDot = el('orgConsentRowDot');
      if (rowDot) rowDot.classList.toggle('off', !on);
      const rowDotLabel = el('orgConsentRowDotLabel');
      if (rowDotLabel) rowDotLabel.textContent = MESSAGES[on ? 'stateOn' : 'stateOff'](t);

      const title = el('orgConsentTitle');
      if (title) fillWithOrg(title, MESSAGES.title, values);
      const label = el('orgConsentSwitchLabel');
      if (label) fillWithOrg(label, MESSAGES.switchLabel, values);
      const toggle = el('orgConsentSwitch');
      if (toggle) {
        toggle.setAttribute('aria-checked', on ? 'true' : 'false');
        toggle.setAttribute('aria-busy', busy ? 'true' : 'false');
        toggle.disabled = busy;
      }
      const knob = el('orgConsentKnob');
      if (knob) knob.classList.toggle('on', on);
      const message = el('orgConsentMsg');
      if (message) {
        message.textContent = busy ? MESSAGES.saving(t)
          : outcome ? (MESSAGES[outcome.message] || MESSAGES.errorNetwork)(t, values) : '';
        message.classList.toggle('busy', busy);
        message.classList.toggle('ok', !busy && !!(outcome && outcome.ok));
        message.classList.toggle('err', !busy && !!(outcome && !outcome.ok));
      }

      const offer = el('seatCodeConsentBtn');
      if (offer) {
        offer.hidden = !(seatCodeOffer && seat);
        fillWithOrg(offer, MESSAGES.fromSeatCode, values);
      }
    }

    async function request(path, payload) {
      const tools = bridge();
      if (!tools || typeof win.fetch !== 'function') return { status: 0, body: null };
      const controller = typeof win.AbortController === 'function' ? new win.AbortController() : null;
      const timer = win.setTimeout(() => { if (controller) controller.abort(); }, REQUEST_TIMEOUT_MS);
      try {
        const response = await win.fetch(tools.brainURL(path), {
          method: 'POST',
          headers: await tools.authHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
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

    // 重讀「有沒有名額、現在開或關」。沒登入不打後端。讀不到（斷線）就維持原樣，不把入口閃掉。
    function refresh(force) {
      if (!loggedIn()) {
        seat = null;
        seatCodeOffer = false;
        render();
        return Promise.resolve(null);
      }
      if (refreshing) return refreshing;
      if (!force && Date.now() - lastRefreshAt < REFRESH_MIN_INTERVAL_MS) return Promise.resolve(seat);
      refreshing = (async () => {
        try {
          const response = await request(STATUS_PATH, {});
          // 改開關的請求還在路上就不要蓋掉畫面，等它回來自己會更新。
          if (!busy && response.body && response.body.ok === true) {
            seat = pickSeat(response.body);
            lastRefreshAt = Date.now();
            render();
          }
          return seat;
        } finally {
          refreshing = null;
        }
      })();
      return refreshing;
    }

    function open() {
      const modal = el('orgConsentModal');
      if (!modal) return;
      if (!busy) outcome = null;
      render();
      modal.classList.add('show');
      // 上次捲到最下面按「完成」的話，這次打開要回到最上面（開關在最上面）。要等視窗顯示出來才捲得動。
      const sheet = typeof modal.querySelector === 'function' ? modal.querySelector('.modal') : null;
      if (sheet) sheet.scrollTop = 0;
    }

    function close() {
      const modal = el('orgConsentModal');
      if (modal) modal.classList.remove('show');
    }

    function finish(next) {
      busy = false;
      outcome = next;
      // 成功才改畫面上的開關；失敗時 seat.granted 沒動，開關留在原位。
      if (next.ok && seat) seat.granted = next.granted;
      render();
      const tools = bridge();
      // 只送結果或失敗原因——next.event 裡沒有機構名稱與名額代號，也不要在這裡加。
      try { if (tools && typeof tools.track === 'function') tools.track(EVENT_NAME, next.event); } catch (error) {}
    }

    async function onToggle() {
      if (busy) return;
      // 沒有名額資料（例如名額剛被機構收回）：重讀一次，還是沒有就老實說找不到。
      if (!seat) {
        await refresh(true);
        if (!seat) {
          outcome = { ok: false, message: loggedIn() ? 'errorGone' : 'errorSignIn' };
          render();
        }
        return;
      }
      // 視窗開著的時候登入過期了：不送，直接請他先登入。
      if (!loggedIn()) {
        finish({ ok: false, granted: null, message: 'errorSignIn', event: { error: 'auth_required' } });
        return;
      }
      const wanted = !seat.granted;
      const seatId = seat.seatId;
      busy = true;
      outcome = null;
      render();
      const response = await request(SET_PATH, { seatId, granted: wanted });
      finish(interpretSet(response.status, response.body, wanted));
    }

    // 開通碼視窗綁好名額之後會叫這支（web/src/seat-code.js 的 finish）：重讀一次，
    // 是照護機構的名額就在成功畫面多一顆次要按鈕。只是把按鈕拿出來，不會幫他打開開關。
    function afterSeatCode() {
      seatCodeOffer = true;
      render();
      return refresh(true);
    }

    function onSeatCodeOffer() {
      seatCodeOffer = false;
      render();
      if (win.MuneaSeatCode && typeof win.MuneaSeatCode.close === 'function') win.MuneaSeatCode.close();
      open();
    }

    function bind() {
      const modal = el('orgConsentModal');
      if (!modal) return;
      const row = el('orgConsentRow');
      const closeButton = el('orgConsentClose');
      const done = el('orgConsentDone');
      const toggle = el('orgConsentSwitch');
      const offer = el('seatCodeConsentBtn');
      const seatCodeEntry = el('seatCodeEntry');
      if (row) {
        row.addEventListener('click', open);
        row.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
        });
      }
      if (closeButton) closeButton.addEventListener('click', close);
      if (done) done.addEventListener('click', close);
      modal.addEventListener('click', (event) => { if (event.target === modal) close(); });
      if (toggle) toggle.addEventListener('click', onToggle);
      if (offer) offer.addEventListener('click', onSeatCodeOffer);
      // 重新打開開通碼視窗＝新的一輪，上一輪留下的次要按鈕收起來。
      if (seatCodeEntry) seatCodeEntry.addEventListener('click', () => { seatCodeOffer = false; render(); });
      // 點「設定」分頁時順手重讀（有間隔限制），機構那邊剛給名額也看得到入口。
      doc.addEventListener('click', (event) => {
        const target = event.target && typeof event.target.closest === 'function'
          ? event.target.closest('.tab-btn[data-view="settings"]') : null;
        if (target) refresh(false);
      });
      render();
      refresh(false);
    }

    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', bind, { once: true });
    else bind();
    win.addEventListener('munea:locale-ready', render);
    // 登入＝讀一次；登出＝把入口收掉（refresh 裡沒登入就會清）。
    win.addEventListener('munea:auth-state', () => { lastRefreshAt = 0; refresh(true); });

    return Object.freeze({ open, close, refresh, afterSeatCode });
  }

  return Object.freeze({
    STATUS_PATH,
    SET_PATH,
    EVENT_NAME,
    APPLICABLE_KINDS,
    ERROR_MESSAGES,
    MESSAGES,
    pickSeat,
    interpretSet,
    mount,
  });
}));
