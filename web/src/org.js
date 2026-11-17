/* 沐寧 Munea · 機構專區（照護人員登入版）· 2026-11-18
 *
 * 照護據點的社工／個管、照服員、機構管理者用電腦登入：看已同意長輩的名單、本週關懷摘要、
 * 異常提醒並逐筆判定（補助案 C4：異常通知上線、由場域護理或照護人員逐筆判定）。
 * 設計書：docs/後台-B2B2C-產品框架設計-2026-10-28.md（2.3 權限矩陣、3.3 看得到／看不到、4.3 接口、4.4 機構專區自己長的頁）。
 * 後端：engine/org_api.py（/org/me、summary、elders、elder/care-week、reports）、engine/org_alerts.py（alerts、alert/mark、audit、settings）。
 *
 * 三條規矩（改這支檔之前先讀）：
 *   1. 分頁顯示只看 /org/me 回的 capabilities，不自己另寫一套角色判斷——誰能看什麼由後端說了算。
 *   2. 後端回來的文字一律當純文字放（textContent／文字節點），這支檔不用 innerHTML 這類把字串當 HTML 的寫法。
 *   3. 示範模式（網址帶 ?demo=1）完全不打接口、不載登入元件，只用本檔最下面的虛構資料；正常模式絕不讀示範資料。
 */
(function () {
  'use strict';

  const W = window;
  const D = document;

  // ───────────────────────── 設定 ─────────────────────────
  const API = Object.freeze({
    me: '/org/me',
    summary: '/org/summary',
    elders: '/org/elders',
    careWeek: '/org/elder/care-week',
    alerts: '/org/alerts',
    mark: '/org/alert/mark',
    audit: '/org/audit',
    reports: '/org/reports',
    settings: '/org/settings',
    settingsSave: '/org/settings/save',
  });
  const REPORT_PATH = '/enterprise/portal/report';
  // 公開薄門碼：跟 App 同一把（web/src/app.js 的 MUNEA_APP_KEY），擋陌生流量用，不是登入憑證。
  // 部署端可以在載入本檔前設 window.MUNEA_ORG_APP_KEY 換掉。
  const PUBLIC_APP_KEY = 'mnk_03d3a1545a3c5215b924c162c54e83f2ecd059e5'; // gitleaks:allow
  const LOGO = 'icons/munea-logo.png';
  const REMARK_MAX = 200;
  const TIMEOUT_MS = 15000;
  const ALERTS_FRESH_MS = 60000;
  const FRESH_MS = 300000;
  const NO_CONTACT_LIMITS = [1, 30];

  const TAB_LABELS = { overview: '總覽', elders: '長輩', alerts: '提醒', audit: '紀錄', reports: '月報' };
  const ROLE_LABELS = { org_admin: '機構管理者', case_manager: '社工／個管', care_worker: '照服員' };
  const TYPE_LABELS = { mood_drop: '心情下降', no_contact: '沒聯絡', guardian: '守護腦亮燈' };
  const RESULT_LABELS = { correct: '正確', false_alarm: '誤報', watching: '觀察中' };
  // 每顆按鈕的說明固定兩行、在標點處斷，手機上也不會把「通知」「值得」拆成兩半
  const RESULT_HINTS = { correct: ['事情屬實，', '也值得通知'], false_alarm: ['事情不屬實，', '或不值得通知'], watching: ['還不能確定，', '之後再判'] };
  const STATUS_LABELS = { unmarked: '還沒判定', correct: '正確', false_alarm: '誤報', watching: '觀察中' };
  const STATUS_ORDER = ['unmarked', 'correct', 'false_alarm', 'watching'];
  const YES_NO = { yes: '是', no: '否' };
  const FLAG_TEXT = { none: '今天沒互動', mood: '心情低落', guard: '守護亮燈' };
  // 掛心事四類：順序與名稱跟後端 org_api.SPOKEN_CATEGORY_RULES 一致；後端只回次數大於 0 的，這裡補成四類都列。
  const SPOKEN_CATS = [['appetite', '吃不下'], ['sleep', '睡不好'], ['body', '身體不舒服'], ['other', '心情或生活上的掛心事']];

  // ───────────────────────── 模式 ─────────────────────────
  const query = new URLSearchParams(W.location.search || '');
  const DEMO = query.get('demo') === '1';
  const DEMO_ROLES = ['org_admin', 'case_manager', 'care_worker', 'esg', 'guest', 'none'];
  const DEMO_START = DEMO_ROLES.indexOf(query.get('role')) >= 0 ? query.get('role') : 'org_admin';
  const DEMO_FAIL = DEMO ? String(query.get('fail') || '') : '';
  let demoRole = DEMO_START;

  const root = D.getElementById('app');
  const S = {
    me: null,
    caps: {},
    tabs: [],
    tab: '',
    seq: 0,
    weekSeq: 0,
    cache: {},
    inflight: {},
    tabButtons: {},
    badge: null,
    main: null,
    alerts: [],
    alertUi: null,
    alertEls: {},
    judgeBtns: {},
    alertFilter: 'all',
    elderRows: [],
    modal: null,
    authError: '',
  };

  // ───────────────────────── 畫面小工具 ─────────────────────────
  // 數字跟前後的字之間換成不斷行空白：「近 30 天」「4 ÷ 5」不會被拆成兩行（只影響顯示，字的內容不變）
  function glue(text) {
    return String(text).replace(/(\d|%) /g, '$1\u00a0').replace(/ (\d)/g, '\u00a0$1');
  }

  function h(tag, props, kids) {
    const el = D.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (key) {
        const val = props[key];
        if (val === null || val === undefined || val === false) return;
        if (key === 'class') el.className = String(val);
        else if (key === 'text') el.textContent = glue(val);
        else if (key === 'hidden' || key === 'disabled') el[key] = true;
        else if (key === 'value') el.value = String(val);
        else if (key.slice(0, 2) === 'on' && typeof val === 'function') el.addEventListener(key.slice(2), val);
        else el.setAttribute(key, val === true ? '' : String(val));
      });
    }
    add(el, kids);
    return el;
  }

  function add(el, kids) {
    if (kids === null || kids === undefined || kids === false) return el;
    (Array.isArray(kids) ? kids : [kids]).forEach(function (kid) {
      if (kid === null || kid === undefined || kid === false || kid === '') return;
      if (Array.isArray(kid)) add(el, kid);
      else el.appendChild(typeof kid === 'object' ? kid : D.createTextNode(glue(kid)));
    });
    return el;
  }

  function clear(el) {
    while (el && el.firstChild) el.removeChild(el.firstChild);
    return el;
  }

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const ICONS = {
    lock: 'M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3',
    close: 'M6 6l12 12M18 6L6 18',
    chevron: 'M9 6l6 6-6 6',
    refresh: 'M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4.2h-4.2',
    person: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20a7.5 7.5 0 0 1 15 0',
    bell: 'M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0',
  };

  function icon(name, cls) {
    const svg = D.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('class', 'ic' + (cls ? ' ' + cls : ''));
    const path = D.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', ICONS[name] || '');
    svg.appendChild(path);
    return svg;
  }

  function wordmark(cls) {
    return h('span', { class: 'wordmark' + (cls ? ' ' + cls : '') }, ['Mu', h('b', { text: 'nea' }), h('span', { class: 'wordmark-zh', text: '沐寧' })]);
  }

  function demoBadge(cls) {
    return h('span', { class: 'demo-badge' + (cls ? ' ' + cls : ''), text: '示範資料' });
  }

  function note(text, kind) {
    return h('div', { class: 'note' + (kind ? ' ' + kind : '') }, [
      h('span', { class: 'note-ic', 'aria-hidden': 'true', text: kind === 'err' ? '!' : 'i' }),
      h('div', { class: 'note-text', text: text }),
    ]);
  }

  function errorNote(text, retry) {
    const box = note(text, 'err');
    box.setAttribute('role', 'alert');
    if (retry) box.appendChild(h('button', { type: 'button', class: 'btn-quiet note-action', onclick: retry }, '再試一次'));
    return box;
  }

  function loadingLine() { return h('p', { class: 'loading-line', text: '讀取中…' }); }

  // 一段裡不可以拆開的小單位（例：「範圍：整家」「最後互動 11/17」）
  function nw(text) { return h('span', { class: 'nw', text: text }); }
  function units(parts, sep) {
    const out = [];
    parts.forEach(function (part, i) { if (i) out.push(sep || ' · '); out.push(nw(part)); });
    return out;
  }
  // 後端的固定句型裡有 2026-11-16 這種日期；日期整個不斷行（內容原樣、一樣當純文字放）
  function withDates(text) {
    return String(text || '').split(/(\d{4}-\d{2}-\d{2})/).map(function (part, i) { return i % 2 ? nw(part) : part; });
  }
  function emptyBox(text) { return h('div', { class: 'empty-box', text: text }); }

  function avatar(label) {
    const first = Array.from(String(label || '').trim())[0] || '·';
    return h('span', { class: 'avatar', 'aria-hidden': 'true', text: first });
  }

  let toastTimer = null;
  function toast(text) {
    let el = D.getElementById('toast');
    if (!el) {
      el = h('div', { id: 'toast', class: 'toast', role: 'status', 'aria-live': 'polite' });
      D.body.appendChild(el);
    }
    el.textContent = glue(text);
    el.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 2600);
  }

  // ───────────────────────── 日期與數字 ─────────────────────────
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function isNum(x) { return typeof x === 'number' && isFinite(x); }
  function pct(x) { return Math.round(x * 100) + '%'; }
  function fmtLevel(x) { return Math.round(x) === x ? String(x) : x.toFixed(1); }

  function parseDay(text) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(text || ''));
    return m ? { y: +m[1], m: +m[2], d: +m[3] } : null;
  }
  function day(text) {
    const p = parseDay(text);
    return p ? p.m + '/' + p.d : '—';
  }
  function dayShift(text, n) {
    const p = parseDay(text);
    if (!p) return '';
    const t = new Date(Date.UTC(p.y, p.m - 1, p.d + n));
    return t.getUTCFullYear() + '-' + pad(t.getUTCMonth() + 1) + '-' + pad(t.getUTCDate());
  }
  const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];
  function weekday(text) {
    const p = parseDay(text);
    return p ? WEEKDAYS[new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay()] : '';
  }
  function when(iso) {
    if (!iso) return '—';
    const t = new Date(iso);
    if (isNaN(t.getTime())) return '—';
    const year = t.getFullYear() !== new Date().getFullYear() ? t.getFullYear() + '/' : '';
    return year + (t.getMonth() + 1) + '/' + t.getDate() + ' ' + pad(t.getHours()) + ':' + pad(t.getMinutes());
  }
  function dateOnly(iso) {
    if (!iso) return '—';
    const t = new Date(iso);
    if (isNaN(t.getTime())) return day(iso);
    return t.getFullYear() + '/' + (t.getMonth() + 1) + '/' + t.getDate();
  }

  // ───────────────────────── 錯誤的白話 ─────────────────────────
  function explain(code, ctx) {
    if (code === 'network' || code === 'timeout') {
      if (ctx === 'mark') return '連不上沐寧，這筆判定還沒送出。內容都還在，網路恢復後再按一次送出。';
      if (ctx === 'settings') return '連不上沐寧，設定還沒存。請確認網路後再按一次儲存。';
      return '連不上沐寧，請確認網路後再試一次。';
    }
    if (code === 'app_key_required') return '這個網址目前不能使用機構專區，請聯絡沐寧。';
    if (code === 'login_unavailable') return '登入元件沒有載入成功，請確認網路後再試一次。';
    if (ctx === 'mark') {
      if (code === 'mark_not_recorded') return '這筆判定沒有存進紀錄，所以還不算數。內容都還在，請再按一次送出。';
      if (code === 'alerts_unavailable') return '提醒暫時讀不到，這筆判定還沒送出。內容都還在，請稍後再按一次送出。';
      if (code === 'not_found') return '這筆提醒已經看不到了，可能長輩關閉了同意。請重新整理提醒。';
      if (code === 'result_invalid') return '請先選一個判定結果。';
    }
    if (ctx === 'settings') {
      if (code === 'settings_not_recorded') return '設定沒有存進紀錄，所以還沒生效。請再按一次儲存。';
      if (code === 'no_contact_days_invalid') return '天數要在 1 到 30 之間。';
      if (code === 'not_found') return '只有機構管理者可以改這個設定。';
    }
    if (code === 'alerts_unavailable') return '提醒暫時讀不到，請稍後再試。';
    if (ctx === 'audit' && code === 'audit_unavailable') return '紀錄暫時讀不到，請稍後再試。';
    if (ctx === 'week') {
      if (code === 'audit_unavailable') return '查看紀錄暫時寫不進去。為了每次查看都留下紀錄，這次先不顯示摘要，請稍後再試。';
      if (code === 'not_found') return '找不到這位長輩的摘要，可能已經關閉同意。請重新整理名單。';
    }
    if (code === 'internal_error' || /^http_5/.test(String(code || ''))) return '沐寧這邊出了點問題，請稍後再試。';
    if (code === 'not_found') return '這一頁目前沒有你可以看的資料。';
    return '讀取失敗，請稍後再試。';
  }

  // ───────────────────────── 接口 ─────────────────────────
  function appKey() { return String(W.MUNEA_ORG_APP_KEY || PUBLIC_APP_KEY); }

  async function call(path, body) {
    try {
      if (DEMO) return await Promise.resolve(demoCall(path, body || {}));
      return await realCall(path, body || {}, false);
    } catch (e) {
      return { ok: false, error: 'network' };
    }
  }

  async function realCall(path, body, retried) {
    const token = await auth.token();
    if (!token) return { ok: false, error: 'auth_required', status: 401 };
    const ctl = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = ctl ? setTimeout(function () { ctl.abort(); }, TIMEOUT_MS) : null;
    let res;
    try {
      res = await fetch(path, {
        method: 'POST',
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token, 'X-Munea-Key': appKey() },
        body: JSON.stringify(body),
        signal: ctl ? ctl.signal : undefined,
      });
    } catch (e) {
      return { ok: false, error: 'network' };
    } finally {
      if (timer) clearTimeout(timer);
    }
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (res.status === 401) {
      if (!retried && await auth.recover()) return realCall(path, body, true);
      return { ok: false, error: 'auth_required', status: 401 };
    }
    if (!data || typeof data !== 'object') return { ok: false, error: res.ok ? 'bad_response' : 'http_' + res.status, status: res.status };
    if (data.ok === false || !res.ok) {
      const err = data.error;
      const code = typeof err === 'string' ? err : (err && err.code) || 'http_' + res.status;
      return { ok: false, error: code, status: res.status };
    }
    return data;
  }

  // 同一份資料在這次登入裡先留著（週關懷摘要例外：每看一次都要留紀錄，所以每次都重拿）。
  function load(key, path, body, maxAgeMs) {
    const hit = S.cache[key];
    if (hit && hit.res && hit.res.ok && (!maxAgeMs || Date.now() - hit.at < maxAgeMs)) return Promise.resolve(hit.res);
    if (S.inflight[key]) return S.inflight[key];
    const job = call(path, body || {}).then(function (res) {
      delete S.inflight[key];
      S.cache[key] = { res: res, at: Date.now() };
      return res;
    });
    S.inflight[key] = job;
    return job;
  }

  function reload(key) {
    delete S.cache[key];
    openTab(S.tab);
  }

  // ───────────────────────── 登入（跟 App 同一套 Supabase Google 登入） ─────────────────────────
  function pageUrl() { return W.location.origin + W.location.pathname; }

  // auth-config.js 的回跳網址預設是 App 首頁；機構專區要回到這一頁。
  function pinRedirect() {
    const cfg = W.MUNEA_SUPABASE_CONFIG;
    if (cfg) cfg.redirectTo = pageUrl();
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      const el = D.createElement('script');
      el.setAttribute('src', src);
      el.onload = function () { resolve(); };
      el.onerror = function () { reject(new Error('script_failed')); };
      D.head.appendChild(el);
    });
  }

  function takeAuthParams() {
    const q = new URLSearchParams(W.location.search || '');
    if (q.get('error') || q.get('error_description')) S.authError = 'oauth';
    let changed = false;
    ['code', 'error', 'error_code', 'error_description'].forEach(function (key) {
      if (q.has(key)) { q.delete(key); changed = true; }
    });
    if (!changed) return;
    const rest = q.toString();
    try { W.history.replaceState(null, '', W.location.pathname + (rest ? '?' + rest : '') + (W.location.hash || '')); } catch (e) { /* 網址留著也不影響使用 */ }
  }

  const auth = {
    loaded: false,
    async load() {
      if (!this.loaded) {
        await loadScript('src/auth-config.js');
        pinRedirect();
        await loadScript('src/auth.js');
        this.loaded = true;
      }
      if (!W.MuneaAuth) throw new Error('auth_missing');
      await W.MuneaAuth.init();
      takeAuthParams();
    },
    async token() {
      try { return W.MuneaAuth ? await W.MuneaAuth.getAccessToken() : null; } catch (e) { return null; }
    },
    async recover() {
      try { return !!(W.MuneaAuth && await W.MuneaAuth.recoverRejectedSession()); } catch (e) { return false; }
    },
    email() {
      try { const st = W.MuneaAuth && W.MuneaAuth.state(); return (st && st.email) || ''; } catch (e) { return ''; }
    },
    unavailable() {
      try { const st = W.MuneaAuth && W.MuneaAuth.state(); return !!st && st.status === 'unconfigured'; } catch (e) { return false; }
    },
  };

  async function signIn(btn, msg) {
    if (DEMO) {
      demoRole = DEMO_START === 'guest' || DEMO_START === 'none' ? 'org_admin' : DEMO_START;
      return enter();
    }
    btn.disabled = true;
    btn.textContent = '正在前往 Google…';
    msg.hidden = true;
    pinRedirect();
    let res = null;
    try { res = W.MuneaAuth ? await W.MuneaAuth.signInWithProvider('google') : null; } catch (e) { res = null; }
    if (res && res.ok) return; // 瀏覽器接著會跳去 Google，登入完回到這一頁
    btn.disabled = false;
    btn.textContent = '用 Google 帳號登入';
    msg.textContent = '沒辦法開啟 Google 登入，請稍後再試。';
    msg.hidden = false;
  }

  async function signOut() {
    closeModal();
    S.me = null;
    S.cache = {};
    S.inflight = {};
    if (DEMO) {
      demoRole = 'guest';
      return renderLogin();
    }
    try { if (W.MuneaAuth) await W.MuneaAuth.signOut(); } catch (e) { /* 本機登入狀態清不掉也照樣回登入頁 */ }
    renderLogin();
  }

  // ───────────────────────── 進門前的畫面 ─────────────────────────
  function screen(kids) {
    closeModal();
    clear(root);
    root.appendChild(h('div', { class: 'screen' }, [DEMO ? demoBadge('screen-badge') : null, h('div', { class: 'screen-card' }, kids)]));
  }

  function lockup() {
    return h('div', { class: 'lockup' }, [h('img', { class: 'lockup-logo', src: LOGO, alt: '', width: '64', height: '64' }), wordmark('lg')]);
  }

  function renderLoading() {
    screen([lockup(), h('p', { class: 'screen-loading', text: '讀取中…' })]);
  }

  function renderLogin() {
    S.me = null;
    const btn = h('button', { type: 'button', class: 'btn btn-primary btn-block' }, '用 Google 帳號登入');
    const msg = h('p', { class: 'screen-msg', role: 'alert', hidden: true });
    btn.addEventListener('click', function () { signIn(btn, msg); });
    screen([
      lockup(),
      h('h1', { class: 'screen-title', text: '機構專區' }),
      btn,
      h('p', { class: 'screen-hint', text: '只有機構邀請過的帳號才能進來' }),
      msg,
    ]);
    if (S.authError) {
      msg.textContent = '登入沒有完成，請再試一次。';
      msg.hidden = false;
      S.authError = '';
    } else if (!DEMO && auth.unavailable()) {
      msg.textContent = '登入元件沒有載入成功，請確認網路後重新整理這一頁。';
      msg.hidden = false;
    }
  }

  function renderNoAccess() {
    const email = DEMO ? 'staff@example.org' : auth.email();
    const out = h('button', { type: 'button', class: 'btn btn-secondary btn-block' }, '登出');
    out.addEventListener('click', signOut);
    screen([
      lockup(),
      h('h1', { class: 'screen-title', text: '還沒有機構專區的權限' }),
      h('p', { class: 'screen-text', text: '這個 Google 帳號還沒有機構專區的權限。請貴單位的沐寧聯絡窗口幫你開通。' }),
      email ? h('p', { class: 'screen-hint', text: '目前登入：' + email }) : null,
      out,
    ]);
  }

  function renderFatal(code, retry) {
    const again = h('button', { type: 'button', class: 'btn btn-primary btn-block' }, '再試一次');
    again.addEventListener('click', function () { retry(); });
    screen([
      lockup(),
      h('h1', { class: 'screen-title', text: '暫時打不開機構專區' }),
      h('p', { class: 'screen-text', text: explain(code, 'me') }),
      again,
    ]);
  }

  // ───────────────────────── 分頁：只看 capabilities ─────────────────────────
  function capFlag(caps, key, fallback) {
    return typeof caps[key] === 'boolean' ? caps[key] : !!fallback;
  }

  function tabsFor(caps) {
    caps = caps || {};
    const out = [];
    if (caps.summary) out.push('overview');
    if (caps.elders) out.push('elders');
    // 提醒：後端 /org/alerts 用 careWeek 這一格放行（照服員、企業窗口沒有）。後端日後補上 alerts 這一格就直接用它。
    if (capFlag(caps, 'alerts', caps.careWeek)) out.push('alerts');
    // 紀錄：後端 /org/audit 只給機構管理者（不分分點＝siteScoped 為 false）而且不是企業客戶（level L0）。日後補上 audit 這一格就直接用它。
    if (capFlag(caps, 'audit', caps.siteScoped === false && caps.level !== 'L0')) out.push('audit');
    if (caps.reports) out.push('reports');
    return out;
  }

  function roleLabel(me) {
    if (((me && me.org) || {}).clientKind === 'esg') return '企業窗口';
    return ROLE_LABELS[((me && me.staff) || {}).role] || '';
  }

  async function enter() {
    renderLoading();
    const me = await call(API.me, {});
    if (!me.ok) {
      if (me.error === 'not_found') return renderNoAccess();
      if (me.error === 'auth_required') return renderLogin();
      return renderFatal(me.error, enter);
    }
    S.me = me;
    S.caps = me.capabilities || {};
    S.tabs = tabsFor(S.caps);
    S.cache = {};
    S.inflight = {};
    S.alertFilter = 'all';
    if (!S.tabs.length) return renderNoAccess();
    renderShell();
    openTab(String(W.location.hash || '').replace(/^#/, '')); // 網址上的分頁沒權限或不存在，openTab 會換成第一頁
    if (S.tabs.indexOf('alerts') >= 0 && S.tab !== 'alerts') loadAlerts().then(updateBadge);
  }

  function renderShell() {
    clear(root);
    const me = S.me;
    const org = me.org || {};
    const staff = me.staff || {};
    const site = S.caps.siteScoped && S.caps.siteLabel ? S.caps.siteLabel : '';
    const nav = h('nav', { class: 'tabs', 'aria-label': '機構專區分頁' });
    S.tabButtons = {};
    S.badge = null;
    S.tabs.forEach(function (key) {
      const btn = h('button', { type: 'button', class: 'tab', onclick: function () { openTab(key); } }, TAB_LABELS[key]);
      if (key === 'alerts') {
        S.badge = h('span', { class: 'tab-badge num', hidden: true });
        btn.appendChild(S.badge);
      }
      S.tabButtons[key] = btn;
      nav.appendChild(btn);
    });
    const signOutBtn = h('button', { type: 'button', class: 'btn-quiet signout' }, '登出');
    signOutBtn.addEventListener('click', signOut);
    const header = h('header', { class: 'topbar' }, [
      h('div', { class: 'topbar-in' }, [
        h('div', { class: 'brand' }, [
          h('img', { class: 'brand-logo', src: LOGO, alt: '', width: '32', height: '32' }),
          wordmark(),
          h('span', { class: 'brand-sub', text: '機構專區' }),
        ]),
        h('span', { class: 'topbar-gap' }),
        DEMO ? demoBadge() : null,
        h('span', { class: 'topbar-break', 'aria-hidden': 'true' }),
        h('div', { class: 'who' }, [
          h('div', { class: 'who-org', text: (org.name || '') + (site ? ' · ' + site : '') }),
          h('div', { class: 'who-name', text: [staff.displayName, roleLabel(me)].filter(Boolean).join(' · ') }),
        ]),
        signOutBtn,
      ]),
      nav,
    ]);
    S.main = h('main', { id: 'main', class: 'main', tabindex: '-1' });
    const footText = S.caps.level === 'L0'
      ? '這裡只有整家加總的數字，沒有任何一位長輩的個人資料。'
      : '機構專區只列出已同意「機構照護模式」的長輩，看不到對話內容與原句。查看週關懷摘要、判定提醒都會留下紀錄。';
    add(root, [header, S.main, h('footer', { class: 'foot', text: footText })]);
  }

  const PAGES = {
    overview: pageOverview,
    elders: pageElders,
    alerts: pageAlerts,
    audit: pageAudit,
    reports: pageReports,
  };

  function openTab(key) {
    if (S.tabs.indexOf(key) < 0) key = S.tabs[0];
    closeModal();
    S.tab = key;
    S.weekSeq += 1;
    Object.keys(S.tabButtons).forEach(function (k) {
      if (k === key) S.tabButtons[k].setAttribute('aria-current', 'page');
      else S.tabButtons[k].removeAttribute('aria-current');
    });
    try { W.history.replaceState(null, '', '#' + key); } catch (e) { /* 舊瀏覽器沒有也沒關係 */ }
    clear(S.main);
    S.seq += 1;
    PAGES[key](S.main, S.seq);
  }

  function pageHead(title, onRefresh) {
    const sub = h('p', { class: 'page-sub' });
    const head = h('div', { class: 'page-head' }, [
      h('div', { class: 'page-title' }, [h('h1', { text: title }), sub]),
      onRefresh ? h('button', { type: 'button', class: 'btn-quiet refresh', 'aria-label': '重新整理', onclick: onRefresh }, [icon('refresh'), h('span', { class: 'btn-label', text: '重新整理' })]) : null,
    ]);
    return { head: head, sub: sub };
  }

  function section(title, lead, kids) {
    return h('section', { class: 'section' }, [
      h('div', { class: 'section-head' }, [h('h2', { text: title }), lead ? h('p', { text: lead }) : null]),
      kids,
    ]);
  }

  function tile(label, value, extra, hint) {
    return h('div', { class: 'tile' }, [h('div', { class: 'tile-label', text: label }), value, extra || null, hint ? h('div', { class: 'tile-hint', text: hint }) : null]);
  }

  function numValue(n, unit) {
    if (!isNum(n)) return naValue('—');
    return h('div', { class: 'tile-value num' }, [String(n), unit ? h('span', { class: 'unit', text: unit }) : null]);
  }

  function naValue(text) { return h('div', { class: 'tile-value na', text: text }); }

  function rateValue(rate, suppressed, emptyText) {
    if (isNum(rate)) return h('div', { class: 'tile-value num', text: pct(rate) });
    return naValue(suppressed ? '人數太少不顯示' : emptyText || '還沒有資料');
  }

  function meter(ratio) {
    const bar = h('span');
    bar.style.width = Math.max(0, Math.min(100, Math.round((ratio || 0) * 100))) + '%';
    return h('div', { class: 'meter', 'aria-hidden': 'true' }, bar);
  }

  // ───────────────────────── 總覽 ─────────────────────────
  function pageOverview(main, seq) {
    const top = pageHead('總覽', function () { reload('summary'); });
    const body = h('div', null, loadingLine());
    add(main, [top.head, body]);
    load('summary', API.summary, {}, FRESH_MS).then(function (res) {
      if (seq !== S.seq) return;
      clear(body);
      if (!res.ok) return add(body, errorNote(explain(res.error, 'summary'), function () { reload('summary'); }));
      const period = res.period || {};
      const scope = res.scope || {};
      const seats = res.seats || {};
      const usage = res.usage || {};
      const guardian = res.guardian || {};
      const min = (res.privacy && res.privacy.minGroupSize) || 5;
      const siteScoped = !!(scope.siteScoped && scope.siteLabel);
      clear(top.sub);
      add(top.sub, units(['統計期間 ' + day(period.start) + '–' + day(period.end) + '（近 ' + (period.days || 30) + ' 天）', '範圍：' + (siteScoped ? scope.siteLabel : '整家')]));

      // 名額：後端只拿生效中的名額算，所以「待開通」一定是 0，不放；分點人員的「合約名額」是整家的，跟分點人數混在一起會誤導，也不放。
      const seatTiles = [];
      if (!siteScoped) seatTiles.push(tile('合約名額', numValue(seats.quota, '位')));
      seatTiles.push(tile(siteScoped ? '已啟用（' + scope.siteLabel + '）' : '已啟用', numValue(seats.active, '位'),
        siteScoped || !isNum(seats.utilization) ? null : meter(seats.utilization),
        siteScoped || !isNum(seats.utilization) ? null : '使用率 ' + pct(seats.utilization)));
      if (!siteScoped) seatTiles.push(tile('尚未使用', numValue(seats.unusedQuota, '位')));
      if (res.consent) seatTiles.push(tile('已同意機構照護模式', numValue(res.consent.grantedSeats, '位'), null, '名單只列已同意的'));
      add(body, section('名額', '一位長輩一個名額。', h('div', { class: 'tiles' }, seatTiles)));

      const suppressed = !!(usage.smallSampleSuppressed || guardian.smallSampleSuppressed);
      const usageKids = [];
      if (suppressed) usageKids.push(note('人數太少時不顯示比例，避免指認到個人（未滿 ' + min + ' 人）。'));
      usageKids.push(h('div', { class: 'tiles' }, [
        tile('啟用人數', numValue(usage.enabledCount, '位'), null, '名額已綁定的人'),
        tile('近 30 天有互動', numValue(usage.activeCount, '位'), null,
          isNum(usage.activeRate) ? '佔啟用人數 ' + pct(usage.activeRate) : suppressed ? '比例：人數太少不顯示' : null),
        tile('留存', rateValue(usage.retentionRate, suppressed, usage.retentionBaseCount === 0 ? '上一期還沒有人使用' : '還沒有資料'), null,
          '上一個 30 天有用、這 30 天還在用'),
        tile('平均每人每週互動', isNum(usage.avgWeeklyInteractionsPerPerson)
          ? numValue(usage.avgWeeklyInteractionsPerPerson, '次')
          : naValue(suppressed ? '人數太少不顯示' : '還沒有資料'), null, '通話、提醒完成、App 操作都算一次'),
      ]));
      add(body, section('使用狀況', '近 30 天，開通的長輩有多少人真的在用。', usageKids));

      add(body, section('守護', '只有次數，沒有內容。', h('div', { class: 'tiles' }, [
        tile('守護提醒', isNum(guardian.highRiskEventCount)
          ? numValue(guardian.highRiskEventCount, '次')
          : naValue(suppressed ? '人數太少不顯示' : '還沒有資料'), null, '近 30 天，需要留意或立即處理'),
        tile('用藥提醒完成率', rateValue(guardian.medicationCompletionRate, suppressed,
          guardian.medicationDecidedCount === 0 ? '近 30 天沒有用藥提醒' : '還沒有資料'), null, '到點提醒後，有按「吃了」的比例'),
      ])));
      // 企業窗口的頁尾已經是這句，不重複
      if (S.caps.level !== 'L0') add(body, h('p', { class: 'privacy-line', text: '這一頁只有加總的數字，沒有任何一位長輩的個人資料。' }));
    });
  }

  // ───────────────────────── 長輩（名單＋本週關懷摘要） ─────────────────────────
  function flagTag(kind) { return h('span', { class: 'flag flag-' + kind, text: FLAG_TEXT[kind] }); }

  function pageElders(main, seq) {
    const canOpen = S.caps.careWeek === true;
    const top = pageHead('長輩', function () { reload('elders'); });
    add(top.sub, ['只列出同意', nw('「機構照護模式」'), '的長輩，旗標多的排前面。']);
    const legend = h('ul', { class: 'legend', 'aria-label': '旗標說明' }, [
      h('li', null, [flagTag('none'), '今天還沒跟沐寧通話']),
      h('li', null, [flagTag('mood'), '心情連續偏低，或比自己平常低']),
      h('li', null, [flagTag('guard'), '這週有守護提醒']),
    ]);
    const list = h('ul', { class: 'elder-list', 'aria-label': '長輩名單' }, h('li', null, loadingLine()));
    const listCard = h('div', { class: 'card' }, list);
    const layout = h('div', { class: 'elders' + (canOpen ? '' : ' single') }, listCard);
    let detail = null;
    if (canOpen) {
      detail = h('aside', { class: 'card detail', 'aria-label': '本週關懷摘要', 'aria-live': 'polite' });
      detailEmpty(detail);
      layout.appendChild(detail);
    }
    add(main, [
      top.head,
      canOpen ? null : note('你的帳號看得到名單與旗標；本週關懷摘要由社工或機構管理者查看。'),
      legend,
      layout,
    ]);
    S.elderRows = [];
    load('elders', API.elders, {}, FRESH_MS).then(function (res) {
      if (seq !== S.seq) return;
      clear(list);
      if (!res.ok) {
        clear(listCard);
        return add(listCard, errorNote(explain(res.error, 'elders'), function () { reload('elders'); }));
      }
      const elders = res.elders || [];
      clear(top.sub);
      add(top.sub, ['已同意', nw('「機構照護模式」'), '的長輩 ' + elders.length + ' 位，旗標多的排前面。']);
      if (res.partial && res.partial.length) listCard.insertBefore(note('部分資料暫時讀不到，旗標可能不完整。'), list);
      if (!elders.length) {
        clear(listCard);
        return add(listCard, emptyBox('目前還沒有長輩同意「機構照護模式」。同意之後會出現在這裡。'));
      }
      elders.forEach(function (e) { list.appendChild(elderRow(e, canOpen, detail)); });
    });
  }

  function elderRow(e, canOpen, detail) {
    const flags = e.flags || {};
    const tags = [];
    if (flags.noInteractionToday === true) tags.push(flagTag('none'));
    if (flags.lowMood === true) tags.push(flagTag('mood'));
    if (flags.guardianLit === true) tags.push(flagTag('guard'));
    const meta = ['名額代號 ' + (e.seatCode || '—')];
    if (e.siteLabel && !S.caps.siteScoped) meta.push(e.siteLabel);
    meta.push(e.lastInteractionDate ? '最後互動 ' + day(e.lastInteractionDate) : '還沒有互動紀錄');
    const kids = [
      avatar(e.label),
      h('span', { class: 'elder-main' }, [
        h('span', { class: 'elder-name', text: e.label || '—' }),
        h('span', { class: 'elder-meta' }, units(meta)),
        tags.length ? h('span', { class: 'flags' }, tags) : null,
      ]),
    ];
    let row;
    if (canOpen) {
      kids.push(icon('chevron', 'chev'));
      row = h('button', { type: 'button', class: 'elder-row', 'aria-pressed': 'false' }, kids);
      row.addEventListener('click', function () { openWeek(e, row, detail); });
      S.elderRows.push(row);
    } else {
      row = h('div', { class: 'elder-row' }, kids);
    }
    return h('li', null, row);
  }

  function detailEmpty(box) {
    clear(box);
    add(box, h('div', { class: 'detail-empty' }, h('div', null, [icon('person'), '點名單裡的長輩，看本週關懷摘要。'])));
  }

  function openWeek(e, row, detail) {
    S.elderRows.forEach(function (btn) { btn.setAttribute('aria-pressed', btn === row ? 'true' : 'false'); });
    const mine = ++S.weekSeq;
    clear(detail);
    add(detail, [weekHead(e.label, e.seatCode, e.siteLabel, null, detail), loadingLine()]);
    if ((W.innerWidth || 1280) < 960 && typeof detail.scrollIntoView === 'function') {
      try { detail.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (err) { detail.scrollIntoView(); }
    }
    call(API.careWeek, { seatId: e.seatId }).then(function (res) {
      if (mine !== S.weekSeq || S.tab !== 'elders') return;
      clear(detail);
      if (!res.ok) {
        return add(detail, [
          weekHead(e.label, e.seatCode, e.siteLabel, null, detail),
          errorNote(explain(res.error, 'week'), function () { openWeek(e, row, detail); }),
        ]);
      }
      renderWeek(detail, res, e);
    });
  }

  function weekHead(label, seatCode, siteLabel, period, detail) {
    const meta = ['名額代號 ' + (seatCode || '—')];
    if (siteLabel && !S.caps.siteScoped) meta.push(siteLabel);
    if (period && period.start) meta.push(day(period.start) + '–' + day(period.end) + '（近 ' + (period.days || 7) + ' 天）');
    const close = h('button', { type: 'button', class: 'btn-quiet detail-close', 'aria-label': '關閉摘要' }, icon('close'));
    close.addEventListener('click', function () {
      S.weekSeq += 1;
      S.elderRows.forEach(function (btn) { btn.setAttribute('aria-pressed', 'false'); });
      detailEmpty(detail);
    });
    return h('div', { class: 'detail-head' }, [
      avatar(label),
      h('div', { class: 'detail-who' }, [h('div', { class: 'detail-name', text: label || '—' }), h('div', { class: 'detail-meta' }, units(meta))]),
      close,
    ]);
  }

  function renderWeek(box, res, fallback) {
    const week = res.week;
    add(box, weekHead(res.label || fallback.label, res.seatCode || fallback.seatCode, res.siteLabel || fallback.siteLabel, week && week.period, box));
    if (!week) {
      add(box, [h('div', { class: 'block' }, note((res.privacy && res.privacy.statement) || '這個名額還沒綁到長輩本人，沒有可讀的紀錄。')), logged()]);
      return;
    }
    if (res.partial && res.partial.length) add(box, h('div', { class: 'block' }, note('部分資料暫時讀不到，這一頁可能不完整。')));
    const contact = week.contact || {};
    const mood = week.moodTrend || {};
    const spoken = week.spokenHealth || {};
    const safety = week.safety || {};
    const counts = safety.counts || {};
    const urgent = (counts.critical || 0) + (counts.crisis || 0);
    const since = contact.daysSinceLastCall;
    add(box, h('div', { class: 'week-tiles' }, [
      tile('通話', numValue(contact.calls, '次'), null, '有通話 ' + ((contact.daysWithCall || []).length) + ' 天'),
      tile('最長空檔', numValue(contact.longestGapDays, '天'), null, '期間內連續沒通話'),
      tile('最後通話', contact.lastCallDate ? h('div', { class: 'tile-value num', text: day(contact.lastCallDate) }) : naValue('沒有紀錄'), null,
        isNum(since) ? (since === 0 ? '今天' : since + ' 天前') : null),
      tile('需要留意', numValue(safety.highOrCritical || 0, '次'), null, urgent ? '其中立即處理 ' + urgent + ' 次' : '守護提醒'),
    ]));

    const moodKids = [];
    const avg = isNum(mood.weekAverage) ? '本週平均 ' + fmtLevel(mood.weekAverage) + ' 級' : '本週沒有心情紀錄';
    const base = isNum(mood.baselineAverage) ? '；自己前 ' + (mood.baselineDays || 14) + ' 天平均 ' + fmtLevel(mood.baselineAverage) + ' 級' : '';
    moodKids.push(h('p', { class: 'mood-sum', text: avg + base + '。' }));
    moodKids.push(moodChart(week.period || {}, mood.daily || []));
    if (mood.source) moodKids.push(h('p', { class: 'block-src', text: '來源：' + mood.source }));
    add(box, h('div', { class: 'block' }, [h('h3', { text: '心情（1–5 級，5 最好）' })].concat(moodKids)));

    add(box, h('div', { class: 'block' }, [
      h('h3', { text: '本人提到的掛心事' }),
      spokenCats(spoken.categories),
      spoken.source ? h('p', { class: 'block-src', text: '來源：' + spoken.source }) : null,
    ]));

    const anomalies = res.anomalies || [];
    add(box, h('div', { class: 'block' }, [
      h('h3', { text: '規則跑出來的提醒' }),
      anomalies.length
        ? h('div', { class: 'anoms' }, anomalies.map(function (a) {
          return h('div', { class: 'anom' }, [
            typeTag(a.type, a.typeLabel),
            h('p', { class: 'anom-fact' }, withDates(a.fact)),
            a.suggestion ? h('p', { class: 'anom-sugg' }, ['建議：', a.suggestion]) : null,
          ]);
        }))
        : h('p', { class: 'none-line', text: '這週沒有規則提醒。' }),
    ]));
    add(box, logged());
  }

  function logged() {
    return h('p', { class: 'logged' }, [icon('lock'), '這次查看已留下紀錄']);
  }

  function moodChart(period, daily) {
    const byDate = {};
    (daily || []).forEach(function (d) { if (d && d.date) byDate[String(d.date).slice(0, 10)] = d; });
    const days = [];
    const n = Math.max(1, Math.min(31, period.days || 7));
    for (let i = 0; i < n; i += 1) days.push(dayShift(period.start, i));
    const spoken = [];
    const cols = days.map(function (date) {
      const d = byDate[date];
      const level = d && isNum(d.level) ? d.level : null;
      spoken.push(day(date) + (level === null ? ' 沒有紀錄' : ' ' + fmtLevel(level) + ' 級'));
      const track = h('div', { class: 'mood-track' + (level === null ? ' none' : '') });
      if (level !== null) {
        const bar = h('div', { class: 'mood-bar' + (level <= 2 ? ' low' : '') });
        bar.style.height = Math.max(8, Math.min(100, (level / 5) * 100)) + '%';
        track.appendChild(bar);
      }
      return h('div', { class: 'mood-col' }, [
        h('div', { class: 'mood-level num' + (level === null ? ' none' : ''), text: level === null ? '—' : fmtLevel(level) }),
        track,
        h('div', { class: 'mood-date' }, [day(date), h('span', { class: 'mood-wd', text: '週' + weekday(date) })]),
      ]);
    });
    return h('div', { class: 'mood-chart', role: 'img', 'aria-label': '近 ' + n + ' 天心情：' + spoken.join('、') }, cols);
  }

  function spokenCats(list) {
    const got = {};
    (list || []).forEach(function (c) { if (c && c.key) got[c.key] = c; });
    const rows = SPOKEN_CATS.map(function (pair) {
      const c = got[pair[0]];
      return { label: (c && c.label) || pair[1], count: c && isNum(c.count) ? c.count : 0 };
    });
    (list || []).forEach(function (c) {
      if (c && c.key && !SPOKEN_CATS.some(function (pair) { return pair[0] === c.key; })) {
        rows.push({ label: c.label || c.key, count: isNum(c.count) ? c.count : 0 });
      }
    });
    return h('div', { class: 'cats' }, rows.map(function (r) {
      return h('div', { class: 'cat' + (r.count ? '' : ' zero') }, [
        h('span', { class: 'cat-label', text: r.label }),
        h('span', { class: 'cat-count num' }, [String(r.count), h('span', { class: 'unit', text: '次' })]),
      ]);
    }));
  }

  function typeTag(type, label) {
    return h('span', { class: 'type-tag type-' + String(type || 'other').replace(/[^a-z_]/g, ''), text: label || TYPE_LABELS[type] || '提醒' });
  }

  // ───────────────────────── 提醒（提醒匣＋逐筆判定） ─────────────────────────
  function loadAlerts(force) {
    if (force) delete S.cache.alerts;
    return load('alerts', API.alerts, {}, ALERTS_FRESH_MS);
  }

  function tally(list) {
    const counts = { unmarked: 0, correct: 0, false_alarm: 0, watching: 0 };
    (list || []).forEach(function (a) {
      const k = a && a.status;
      if (Object.prototype.hasOwnProperty.call(counts, k)) counts[k] += 1;
    });
    const judged = counts.correct + counts.false_alarm;
    return { counts: counts, judged: judged, rate: judged ? counts.correct / judged : null };
  }

  function updateBadge() {
    if (!S.badge) return;
    const hit = S.cache.alerts;
    const res = hit && hit.res;
    if (!res || !res.ok) { S.badge.hidden = true; return; }
    const n = tally(res.alerts || []).counts.unmarked;
    S.badge.textContent = String(n);
    S.badge.setAttribute('aria-label', n + ' 筆還沒判定');
    S.badge.hidden = n === 0;
  }

  function pageAlerts(main, seq) {
    const top = pageHead('提醒', function () { delete S.cache.settings; reload('alerts'); });
    top.sub.textContent = glue('規則每天算一次，第一次算到就發到這裡（近 90 天）。請逐筆判定。');
    const setting = h('div', { class: 'setting-bar' }, loadingLine());
    const stats = h('div', { class: 'alert-stats' });
    const acc = h('p', { class: 'accuracy' });
    const filters = h('div', { class: 'filters', role: 'group', 'aria-label': '依判定狀態篩選' });
    const list = h('div', { class: 'alert-list' }, loadingLine());
    add(main, [top.head, setting, stats, acc, filters, list]);
    S.alertUi = { stats: stats, acc: acc, filters: filters, list: list };
    S.alertEls = {};
    S.judgeBtns = {};
    S.settingJob = renderSetting(setting, seq);
    loadAlerts().then(function (res) {
      if (seq !== S.seq) return;
      clear(list);
      if (!res.ok) {
        stats.hidden = true;
        acc.hidden = true;
        filters.hidden = true;
        updateBadge();
        return add(list, errorNote(explain(res.error, 'alerts'), function () { reload('alerts'); }));
      }
      if (!Array.isArray(res.alerts)) res.alerts = [];
      S.alerts = res.alerts;
      if (res.partial && res.partial.length) main.insertBefore(note('部分資料暫時讀不到，清單可能不完整。'), stats);
      drawAlertSummary();
      drawFilters();
      drawAlertList();
      updateBadge();
    });
  }

  // 「幾天沒聯絡才提醒」：能不能改看後端回的 canEdit（只有機構管理者是 true）。
  function renderSetting(bar, seq) {
    return load('settings', API.settings, {}, FRESH_MS).then(function (res) {
      if (seq !== S.seq) return;
      clear(bar);
      const label = h('span', { class: 'setting-label', text: '幾天沒聯絡才提醒' });
      if (!res.ok) {
        add(bar, [icon('bell'), label, h('span', { class: 'setting-hint', text: '目前的設定暫時讀不到；提醒照常計算。' })]);
        return;
      }
      const settings = res.settings || {};
      const days = isNum(settings.noContactDays) ? settings.noContactDays : null;
      const updated = settings.updatedAt ? '上次修改 ' + when(settings.updatedAt) : '目前是預設值';
      if (!res.canEdit) {
        add(bar, [icon('bell'), label, h('span', { class: 'setting-ctrl' }, [
          h('span', { class: 'setting-value num', text: days === null ? '—' : String(days) }), '天',
        ]), h('span', { class: 'setting-hint', text: '由機構管理者設定' })]);
        return;
      }
      const limits = (res.limits && res.limits.noContactDays) || NO_CONTACT_LIMITS;
      const lo = isNum(limits[0]) ? limits[0] : NO_CONTACT_LIMITS[0];
      const hi = isNum(limits[1]) ? limits[1] : NO_CONTACT_LIMITS[1];
      const select = h('select', { id: 'noContactDays', 'aria-label': '幾天沒聯絡才提醒（天）' });
      for (let n = lo; n <= hi; n += 1) select.appendChild(h('option', { value: String(n), text: String(n) }));
      select.value = String(days === null ? 3 : days);
      const save = h('button', { type: 'button', class: 'btn btn-secondary btn-sm', disabled: true }, '儲存');
      const msg = h('div', { class: 'setting-msg', hidden: true });
      select.addEventListener('change', function () {
        save.disabled = Number(select.value) === days;
        msg.hidden = true;
      });
      save.addEventListener('click', function () { saveSetting(select, save, msg); });
      add(bar, [icon('bell'), label, h('span', { class: 'setting-ctrl' }, [select, '天']), save,
        h('span', { class: 'setting-hint', text: updated }), msg]);
    });
  }

  async function saveSetting(select, save, msg) {
    const value = Number(select.value);
    if (!(value >= NO_CONTACT_LIMITS[0] && value <= NO_CONTACT_LIMITS[1])) return;
    save.disabled = true;
    save.textContent = '儲存中…';
    msg.hidden = true;
    const res = await call(API.settingsSave, { noContactDays: value });
    save.textContent = '儲存';
    if (!res.ok) {
      save.disabled = false;
      clear(msg);
      add(msg, errorNote(explain(res.error, 'settings')));
      msg.hidden = false;
      return;
    }
    const hit = S.cache.settings;
    if (hit && hit.res && hit.res.ok) hit.res.settings = Object.assign({}, hit.res.settings, res.settings || { noContactDays: value });
    else delete S.cache.settings;
    // 天數變了：提醒匣與名單旗標都要照新天數重算
    delete S.cache.alerts;
    delete S.cache.elders;
    openTab('alerts');
    toast('已儲存：' + value + ' 天沒聯絡才提醒');
    await S.settingJob;
    const again = D.getElementById('noContactDays');
    if (again && typeof again.focus === 'function') again.focus();
  }

  function drawAlertSummary() {
    const ui = S.alertUi;
    const t = tally(S.alerts);
    clear(ui.stats);
    STATUS_ORDER.forEach(function (k) {
      add(ui.stats, h('div', { class: 'tile stat-' + k }, [
        h('div', { class: 'tile-label', text: STATUS_LABELS[k] }),
        h('div', { class: 'tile-value num', text: String(t.counts[k]) }),
      ]));
    });
    clear(ui.acc);
    if (t.rate === null) {
      add(ui.acc, [h('strong', { text: '準確率（參考）' }), '：還沒有可以算的判定。算法是 ', nw('正確 ÷（正確＋誤報）'), '，', nw('觀察中不算。')]);
    } else {
      add(ui.acc, [h('strong', { text: '準確率（參考）' }), '：', h('strong', { class: 'num', text: pct(t.rate) }), '　',
        nw('正確 ÷（正確＋誤報）＝ ' + t.counts.correct + ' ÷ ' + t.judged), '，', nw('觀察中不算。')]);
    }
  }

  function drawFilters() {
    const ui = S.alertUi;
    clear(ui.filters);
    ['all'].concat(STATUS_ORDER).forEach(function (k) {
      const chip = h('button', { type: 'button', class: 'chip', 'aria-pressed': S.alertFilter === k ? 'true' : 'false' }, k === 'all' ? '全部' : STATUS_LABELS[k]);
      chip.addEventListener('click', function () {
        S.alertFilter = k;
        drawFilters();
        drawAlertList();
      });
      ui.filters.appendChild(chip);
    });
  }

  function drawAlertList() {
    const ui = S.alertUi;
    clear(ui.list);
    S.alertEls = {};
    S.judgeBtns = {};
    if (!S.alerts.length) return add(ui.list, h('div', { class: 'card' }, emptyBox('目前沒有提醒。規則算到新的提醒時，會出現在這裡。')));
    const shown = S.alerts.filter(function (a) { return S.alertFilter === 'all' || a.status === S.alertFilter; });
    if (!shown.length) return add(ui.list, h('div', { class: 'card' }, emptyBox('這個篩選底下沒有提醒。')));
    shown.forEach(function (a) {
      const card = alertCard(a);
      S.alertEls[a.alertId] = card;
      ui.list.appendChild(card);
    });
  }

  function statusPill(status, label) {
    const key = STATUS_LABELS[status] ? status : 'unmarked';
    return h('span', { class: 'status-pill status-' + key, text: label || STATUS_LABELS[key] });
  }

  function alertCard(a) {
    const status = a.status || 'unmarked';
    const seatBits = ['名額代號 ' + (a.seatCode || '—')];
    if (a.siteLabel && !S.caps.siteScoped) seatBits.push(a.siteLabel);
    const judge = h('button', { type: 'button', class: 'btn btn-sm ' + (status === 'unmarked' ? 'btn-secondary' : 'btn-outline') }, status === 'unmarked' ? '判定' : '再判一次');
    judge.addEventListener('click', function () { openMark(a, judge); });
    S.judgeBtns[a.alertId] = judge;
    return h('article', { class: 'card alert-card' }, [
      h('div', { class: 'alert-top' }, [
        typeTag(a.type, a.typeLabel),
        h('div', { class: 'alert-who' }, [h('span', { class: 'alert-name', text: a.label || '—' }), h('span', { class: 'alert-seat', text: seatBits.join(' · ') })]),
        statusPill(status, a.statusLabel),
      ]),
      h('p', { class: 'alert-fact' }, withDates(a.fact)),
      a.suggestion ? h('p', { class: 'alert-sugg' }, ['建議：', a.suggestion]) : null,
      h('div', { class: 'alert-foot' }, [h('span', { class: 'alert-meta', text: '發出 ' + when(a.raisedAt) + ' · 編號 ' + (a.alertId || '—') }), judge]),
      markHistory(a.markHistory),
    ]);
  }

  function markHistory(list) {
    if (!Array.isArray(list) || !list.length) return null;
    const items = list.slice().reverse().map(function (m, i) {
      const who = (m.markedBy || '（沒有名字）') + (m.markedByRole ? '（' + m.markedByRole + '）' : '');
      const extra = [];
      if (YES_NO[m.isReal]) extra.push('事情是真的：' + YES_NO[m.isReal]);
      if (YES_NO[m.worthNotifying]) extra.push('值得通知：' + YES_NO[m.worthNotifying]);
      if (m.remark) extra.push('備註：' + m.remark);
      return h('li', null, [
        h('div', null, [
          when(m.markedAt) + ' ' + who + ' 判為 ',
          h('strong', { text: m.resultLabel || RESULT_LABELS[m.result] || '—' }),
          i === 0 && list.length > 1 ? h('span', { class: 'hist-latest', text: '以這筆為準' }) : null,
        ]),
        extra.length ? h('div', { class: 'hist-extra', text: extra.join(' · ') }) : null,
      ]);
    });
    return h('div', { class: 'history' }, [h('h3', { text: '判定歷程' }), h('ol', null, items)]);
  }

  function cleanRemark(text) {
    return Array.from(String(text || '').replace(/\s+/g, ' ').trim()).slice(0, REMARK_MAX).join('');
  }

  function markBody(alertId, form, remarkRaw) {
    const body = { alertId: alertId, result: form.result };
    if (form.isReal === 'yes' || form.isReal === 'no') body.isReal = form.isReal;
    if (form.worthNotifying === 'yes' || form.worthNotifying === 'no') body.worthNotifying = form.worthNotifying;
    const remark = cleanRemark(remarkRaw);
    if (remark) body.remark = remark;
    return body;
  }

  function applyMark(view) {
    const i = S.alerts.findIndex(function (a) { return a.alertId === view.alertId; });
    if (i >= 0) S.alerts[i] = view;
    else S.alerts.unshift(view);
    const old = S.alertEls[view.alertId];
    if (old && old.parentNode) {
      const fresh = alertCard(view);
      old.parentNode.replaceChild(fresh, old);
      S.alertEls[view.alertId] = fresh;
    }
    drawAlertSummary();
    updateBadge();
  }

  // ── 判定小視窗：蓋在原地、關了回原地；送不出去時不關、不清空 ──
  function openMark(alert, returnBtn) {
    closeModal();
    const form = { result: '', isReal: '', worthNotifying: '' };
    let busy = false;

    const resultBtns = {};
    const resultGroup = h('div', { class: 'result-group', role: 'group', 'aria-labelledby': 'markResultLabel' });
    ['correct', 'false_alarm', 'watching'].forEach(function (k) {
      const btn = h('button', { type: 'button', class: 'result-btn', 'aria-pressed': 'false' }, [
        h('strong', { text: RESULT_LABELS[k] }),
        h('span', { class: 'result-hint' }, RESULT_HINTS[k].map(function (line) { return h('span', { class: 'nw', text: line }); })),
      ]);
      btn.addEventListener('click', function () {
        form.result = k;
        Object.keys(resultBtns).forEach(function (x) { resultBtns[x].setAttribute('aria-pressed', x === k ? 'true' : 'false'); });
        sync();
      });
      resultBtns[k] = btn;
      resultGroup.appendChild(btn);
    });

    function ynRow(key, text) {
      const btns = {};
      const group = h('span', { class: 'yn', role: 'group', 'aria-label': text });
      ['yes', 'no'].forEach(function (v) {
        const btn = h('button', { type: 'button', 'aria-pressed': 'false' }, YES_NO[v]);
        btn.addEventListener('click', function () {
          form[key] = form[key] === v ? '' : v; // 再按一次＝不填
          btns.yes.setAttribute('aria-pressed', form[key] === 'yes' ? 'true' : 'false');
          btns.no.setAttribute('aria-pressed', form[key] === 'no' ? 'true' : 'false');
        });
        btns[v] = btn;
        group.appendChild(btn);
      });
      return h('div', { class: 'yn-row' }, [h('span', { text: text }), group]);
    }

    const remark = h('textarea', { id: 'markRemark', rows: '3', placeholder: '例：已打電話確認，家屬說這兩天有回診。' });
    const counter = h('div', { class: 'counter', 'aria-live': 'polite' });
    function countLeft() { counter.textContent = glue('還可以輸入 ' + (REMARK_MAX - Array.from(remark.value || '').length) + ' 字'); }
    remark.addEventListener('input', function () {
      const chars = Array.from(remark.value || '');
      if (chars.length > REMARK_MAX) remark.value = chars.slice(0, REMARK_MAX).join('');
      countLeft();
    });
    countLeft();

    const err = h('div', { hidden: true });
    const submit = h('button', { type: 'button', class: 'btn btn-primary', disabled: true }, '送出判定');
    const cancel = h('button', { type: 'button', class: 'btn btn-secondary' }, '取消');
    const close = h('button', { type: 'button', class: 'btn-quiet', 'aria-label': '關閉' }, icon('close'));
    function sync() { submit.disabled = busy || !form.result; }

    submit.addEventListener('click', async function () {
      if (busy || !form.result) return;
      busy = true;
      sync();
      submit.textContent = '送出中…';
      err.hidden = true;
      const res = await call(API.mark, markBody(alert.alertId, form, remark.value));
      busy = false;
      submit.textContent = '送出判定';
      sync();
      if (!res.ok || !res.alert) {
        clear(err);
        add(err, errorNote(explain(res.ok ? 'bad_response' : res.error, 'mark')));
        err.hidden = false;
        return;
      }
      applyMark(res.alert);
      closeModal(res.alert.alertId);
      toast('已送出判定：' + (res.alert.statusLabel || RESULT_LABELS[form.result]));
    });
    cancel.addEventListener('click', function () { if (!busy) closeModal(); });
    close.addEventListener('click', function () { if (!busy) closeModal(); });

    const context = h('div', { class: 'modal-context' }, [
      typeTag(alert.type, alert.typeLabel),
      h('strong', { text: alert.label || '—' }),
      h('span', { class: 'alert-seat', text: '　名額代號 ' + (alert.seatCode || '—') }),
      h('p', null, withDates(alert.fact)),
    ]);
    const dialog = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'markTitle' }, [
      h('div', { class: 'modal-head' }, [h('h2', { id: 'markTitle', text: '判定這筆提醒' }), close]),
      context,
      h('span', { class: 'field-label', id: 'markResultLabel', text: '判定結果' }),
      resultGroup,
      h('span', { class: 'field-label' }, ['補充判斷', h('small', { text: '選填，再按一次可取消' })]),
      ynRow('isReal', '事情是真的嗎'),
      ynRow('worthNotifying', '值得通知嗎'),
      h('label', { class: 'field-label', for: 'markRemark' }, ['備註', h('small', { text: '選填，最多 ' + REMARK_MAX + ' 字' })]),
      remark,
      // 後端會把電話、身分證號遮掉，但全名、病名擋不住，所以先講清楚
      h('div', { class: 'remark-foot' }, [h('p', { class: 'remark-hint', text: '請不要寫長輩的全名、電話、身分證或病名' }), counter]),
      h('p', { class: 'modal-rule', text: '判定送出後不能修改；想改就再判一次，以最後一次為準。' }),
      err,
      h('div', { class: 'modal-actions' }, [cancel, submit]),
    ]);
    const backdrop = h('div', { class: 'modal-backdrop' }, dialog);
    D.body.appendChild(backdrop);
    S.modal = { backdrop: backdrop, dialog: dialog, returnBtn: returnBtn, isBusy: function () { return busy; } };
    if (typeof resultBtns.correct.focus === 'function') resultBtns.correct.focus();
  }

  function closeModal(updatedAlertId) {
    const m = S.modal;
    if (!m) return;
    S.modal = null;
    if (m.backdrop.parentNode) m.backdrop.parentNode.removeChild(m.backdrop);
    const back = (updatedAlertId && S.judgeBtns[updatedAlertId]) || m.returnBtn;
    if (back && typeof back.focus === 'function') back.focus();
  }

  D.addEventListener('keydown', function (ev) {
    const m = S.modal;
    if (!m) return;
    if (ev.key === 'Escape') {
      if (!m.isBusy()) closeModal();
      return;
    }
    if (ev.key !== 'Tab' || typeof m.dialog.querySelectorAll !== 'function') return;
    const items = Array.prototype.filter.call(m.dialog.querySelectorAll('button, textarea'), function (el) { return !el.disabled; });
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (ev.shiftKey && D.activeElement === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && D.activeElement === last) { ev.preventDefault(); first.focus(); }
  });

  // ───────────────────────── 紀錄（只有機構管理者） ─────────────────────────
  function pageAudit(main, seq) {
    const top = pageHead('紀錄', function () { reload('audit'); });
    top.sub.textContent = glue('誰在什麼時候看了誰的週關懷摘要、判定了什麼（近 90 天）。紀錄只能新增，不能刪改。');
    const box = h('div', { class: 'card table-card' }, loadingLine());
    add(main, [top.head, box]);
    load('audit', API.audit, {}, FRESH_MS).then(function (res) {
      if (seq !== S.seq) return;
      clear(box);
      if (!res.ok) return add(box, errorNote(explain(res.error, 'audit'), function () { reload('audit'); }));
      const items = res.items || [];
      if (!items.length) return add(box, emptyBox('近 90 天還沒有紀錄。'));
      const body = h('tbody');
      items.forEach(function (it) {
        body.appendChild(h('tr', null, [
          h('td', { class: 'td-time num', 'data-label': '時間', text: when(it.at) }),
          h('td', { 'data-label': '誰' }, [it.actor || '—', it.actorRole ? h('span', { class: 'td-role', text: '　' + it.actorRole }) : null]),
          h('td', { 'data-label': '做了什麼', text: (it.action || '—') + (it.result ? '（' + it.result + '）' : '') }),
          h('td', { class: 'num', 'data-label': '對象', text: it.seatCode || '—' }),
        ]));
      });
      add(box, h('table', { class: 'table' }, [
        h('thead', null, h('tr', null, [
          h('th', { scope: 'col', text: '時間' }),
          h('th', { scope: 'col', text: '誰' }),
          h('th', { scope: 'col', text: '做了什麼' }),
          h('th', { scope: 'col', text: '對象（名額代號）' }),
        ])),
        body,
      ]));
      if (isNum(res.count) && res.count > items.length) add(box, note('只列出最新的 ' + items.length + ' 筆。'));
    });
  }

  // ───────────────────────── 月報 ─────────────────────────
  function reportHref(res, id) {
    const path = typeof res.downloadPath === 'string' && /^\/[^/\\]/.test(res.downloadPath) ? res.downloadPath : REPORT_PATH;
    return path + '?t=' + encodeURIComponent(res.downloadToken) + '&id=' + encodeURIComponent(id);
  }

  function pageReports(main, seq) {
    const top = pageHead('月報', function () { reload('reports'); });
    top.sub.textContent = '每月月結後產生，內容只有整家加總的數字。開啟連結當天有效。';
    const box = h('div', { class: 'card' }, loadingLine());
    add(main, [top.head, box]);
    delete S.cache.reports; // 每次打開都拿當天有效的開啟憑證
    load('reports', API.reports).then(function (res) {
      if (seq !== S.seq) return;
      clear(box);
      if (!res.ok) return add(box, errorNote(explain(res.error, 'reports'), function () { reload('reports'); }));
      const list = (res.reports && res.reports.list) || [];
      if (!list.length) return add(box, emptyBox('目前還沒有月報。每個月月結後會出現在這裡。'));
      if (!res.downloadToken) add(box, note('開啟憑證暫時拿不到，請按「重新整理」再試。'));
      list.forEach(function (item) {
        let action;
        if (item.available && res.downloadToken) {
          action = h('a', { class: 'btn btn-secondary btn-sm', href: reportHref(res, item.id), target: '_blank', rel: 'noopener noreferrer' }, '開啟月報');
          if (DEMO) action.addEventListener('click', function (ev) { ev.preventDefault(); toast('示範模式沒有月報檔案可以開。'); });
        } else {
          action = h('span', { class: 'pill', text: item.available ? '暫時打不開' : '尚未產生' });
        }
        box.appendChild(h('div', { class: 'report-row' }, [
          h('div', null, [
            h('div', { class: 'report-month', text: item.period || '—' }),
            h('div', { class: 'report-meta', text: item.available ? '產生於 ' + dateOnly(item.generatedAt) : '月結完成後會出現在這裡' }),
          ]),
          action,
        ]));
      });
    });
  }

  // ───────────────────────── 示範資料（只在 ?demo=1 用） ─────────────────────────
  // 全部虛構：機構、人員、長輩稱呼、名額代號都不是真的。形狀照後端回應，
  // 權限照後端（org_api.capabilities_for、org_alerts 各支的放行條件）模擬，四種角色看到的跟正式的一樣。
  let demoState = null;

  function demoCall(path, body) {
    if (!demoState) demoState = buildDemo();
    if (DEMO_FAIL === 'network') return { ok: false, error: 'network' };
    if (demoRole === 'guest' || demoRole === 'none') return { ok: false, error: 'not_found' };
    return demoState.handle(demoRole, path, body || {});
  }

  function buildDemo() {
    const now = new Date();
    function ymd(offset) {
      const t = new Date(now.getFullYear(), now.getMonth(), now.getDate() - offset);
      return t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());
    }
    function at(offset, hh, mm) {
      return new Date(now.getFullYear(), now.getMonth(), now.getDate() - offset, hh, mm).toISOString();
    }
    function clone(x) { return JSON.parse(JSON.stringify(x)); }
    const NF = { ok: false, error: 'not_found' };
    const TODAY = ymd(0);

    const care = { id: 'org-demo-care', name: '示範照護中心', clientKind: 'care', planTier: 'plus', contractEnd: (now.getFullYear() + 1) + '-06-30' };
    const esg = { id: 'org-demo-esg', name: '示範科技公司', clientKind: 'esg', planTier: 'plus', contractEnd: (now.getFullYear() + 1) + '-03-31' };
    const staff = {
      org_admin: { id: 'stf-demo-admin', displayName: '林主任', role: 'org_admin', siteLabel: null, status: 'active' },
      case_manager: { id: 'stf-demo-case', displayName: '陳社工', role: 'case_manager', siteLabel: '北院', status: 'active' },
      care_worker: { id: 'stf-demo-worker', displayName: '張照服員', role: 'care_worker', siteLabel: '北院', status: 'active' },
      esg: { id: 'stf-demo-hr', displayName: '王經理', role: 'org_admin', siteLabel: null, status: 'active' },
    };
    const settings = { noContactDays: 3, updatedAt: null };

    function capsFor(person, org) { // 照 engine/org_api.py capabilities_for
      const role = person.role;
      const isEsg = org.clientKind === 'esg';
      const scoped = role !== 'org_admin';
      return {
        summary: true,
        elders: !isEsg && ['org_admin', 'case_manager', 'care_worker'].indexOf(role) >= 0,
        careWeek: !isEsg && ['org_admin', 'case_manager'].indexOf(role) >= 0,
        reports: ['org_admin', 'case_manager'].indexOf(role) >= 0,
        siteScoped: scoped,
        siteLabel: scoped ? person.siteLabel : null,
        level: isEsg ? 'L0' : (['org_admin', 'case_manager'].indexOf(role) >= 0 ? 'L2' : 'L1'),
      };
    }
    function meFor(role) {
      const person = staff[role];
      const org = role === 'esg' ? esg : care;
      return { ok: true, staff: person, org: org, capabilities: capsFor(person, org) };
    }
    function inScope(me, siteLabel) {
      return !me.capabilities.siteScoped || !me.capabilities.siteLabel || siteLabel === me.capabilities.siteLabel;
    }

    const MOOD_SRC = '機器觀察（每次通話後由沐寧記錄的心情天氣，1–5 級）';
    const SPOKEN_SRC = '本人口述的掛心事，只給類別與次數（不含原句與短語；由記憶層歸類、不是臨床事實）';
    const GUARD_SUGG = '聯絡本人或家屬確認狀況。機構端看不到通話原句。';
    function moodStreak(offsets) { // 句型照 engine/care_week.py _low_streak_fact
      const listed = offsets.map(ymd).join('、');
      const daily = offsets.every(function (off, i) { return i === 0 || offsets[i - 1] - off === 1; });
      const fact = daily
        ? '心情連續 ' + offsets.length + ' 天在 2 級以下（' + listed + '）。'
        : '心情連續 ' + offsets.length + ' 次有紀錄都在 2 級以下（' + listed + '，中間幾天沒有紀錄）。';
      return { type: 'mood_drop', when: ymd(offsets[offsets.length - 1]), fact: fact, suggestion: '打個電話問候；這是觀察，不是判定。' };
    }
    function noContact(lastOffset, asOf, days) { // asOf＝這句話是哪一天算的（幾天前）；過去發出的提醒保留當天的句子
      const ref = asOf || 0;
      return { type: 'no_contact', when: ymd(ref), fact: '最後一次通話是 ' + ymd(lastOffset) + '，到 ' + ymd(ref) + ' 已經 ' + (lastOffset - ref) + ' 天沒聯絡（設定：' + (days || settings.noContactDays) + ' 天提醒）。', suggestion: '確認一下人在不在、電話通不通。' };
    }
    function guardianLit(count, offset, hh, mm) {
      return { type: 'guardian', when: at(offset, hh, mm), fact: '守護腦這週亮了 ' + count + ' 次高風險燈（high×' + count + '）。', suggestion: GUARD_SUGG };
    }
    function cat(key, count) {
      const label = SPOKEN_CATS.filter(function (p) { return p[0] === key; })[0][1];
      return { key: key, label: label, count: count };
    }

    // 七位已同意的長輩：mood＝{幾天前: 心情級數}、calls＝哪幾天有通話（幾天前）、last＝最後一次通話是幾天前
    const ELDERS = [
      { seatId: '3f2a9c1b-5d7e-4a10-9c2b-7e1f0a6d4b21', label: '王阿嬤', site: '北院', mood: { 6: 3, 5: 4, 4: 3, 3: 2, 2: 1, 1: 2 }, calls: [6, 5, 4, 3, 2, 1], extra: 1, base: 3.6,
        cats: [cat('sleep', 2), cat('other', 1)], safety: { high: 1 }, anomalies: function () { return [moodStreak([3, 2, 1]), guardianLit(1, 2, 21, 40)]; } },
      { seatId: '17ae5f30-8b2c-4d6e-a1f9-3c5d7e9b0a42', label: '黃伯伯', site: '南院', mood: { 6: 4, 5: 4, 3: 3, 2: 4 }, calls: [6, 5, 3, 2], extra: 0, base: 3.9,
        cats: [cat('body', 1)], safety: { high: 1 }, anomalies: function () { return [guardianLit(1, 2, 15, 20)]; } },
      { seatId: '5b7c19d2-6e4a-4f80-8d3b-2a9c1e7f5d63', label: '張爺爺', site: '北院', mood: { 6: 3, 4: 4, 1: 3 }, calls: [6, 4, 1], extra: 0, base: 3.4,
        cats: [], safety: null, anomalies: function () { return []; } },
      { seatId: 'c95b2e64-1a3f-4b7d-9e05-6f8a2d4c1b84', label: '林奶奶', site: '北院', mood: { 6: 4, 5: 3, 4: 4, 3: 2, 1: 1, 0: 2 }, calls: [6, 5, 4, 3, 1, 0], extra: 2, base: 3.8,
        cats: [cat('appetite', 1), cat('other', 2)], safety: null, anomalies: function () { return [moodStreak([3, 1, 0])]; } },
      { seatId: '8d41e07a-2f6b-4c19-b7e3-9a0d5c8f2e15', label: '陳阿公', site: '南院', mood: {}, calls: [], extra: 0, base: 3.2, last: 9,
        cats: [], safety: null, anomalies: function () { return [noContact(9)]; } },
      { seatId: 'a04f6e85-9c1d-4e2b-8f7a-5d3b6c0e9a76', label: '吳奶奶', site: '南院', mood: { 5: 4, 3: 5, 0: 4 }, calls: [5, 3, 0], extra: 0, base: 4.1,
        cats: [cat('sleep', 1)], safety: null, anomalies: function () { return []; } },
      { seatId: 'e6038d9f-4b5a-4c71-a2e8-7f1c9d3b6e97', label: '李阿姨', site: '北院', mood: { 6: 4, 5: 5, 4: 4, 3: 4, 2: 5, 1: 4, 0: 4 }, calls: [6, 5, 4, 3, 2, 1, 0], extra: 1, base: 4.2,
        cats: [], safety: null, anomalies: function () { return []; } },
    ];

    function weekOf(e) {
      const daily = [];
      for (let off = 6; off >= 0; off -= 1) {
        if (e.mood[off] !== undefined) daily.push({ date: ymd(off), level: e.mood[off], chats: 1 });
      }
      let longest = 0;
      let run = 0;
      for (let off = 6; off >= 0; off -= 1) {
        if (e.calls.indexOf(off) >= 0) run = 0;
        else { run += 1; longest = Math.max(longest, run); }
      }
      const last = e.calls.length ? Math.min.apply(null, e.calls) : (isNum(e.last) ? e.last : null);
      const levels = daily.map(function (d) { return d.level; });
      const avg = levels.length ? Math.round((levels.reduce(function (a, b) { return a + b; }, 0) / levels.length) * 10) / 10 : null;
      const lowest = daily.reduce(function (lo, d) { return !lo || d.level < lo.level ? d : lo; }, null);
      const safety = e.safety || {};
      const hi = (safety.high || 0) + (safety.critical || 0);
      return {
        period: { start: ymd(6), end: TODAY, days: 7 },
        contact: { source: '系統紀錄（每通電話結束後的摘要）', calls: e.calls.length + e.extra, daysWithCall: e.calls.slice().sort(function (a, b) { return b - a; }).map(ymd),
          longestGapDays: longest, lastCallDate: last === null ? null : ymd(last), daysSinceLastCall: last, empty: e.calls.length === 0 },
        moodTrend: { source: MOOD_SRC, daysWithChat: daily.length, daily: daily, weekAverage: avg, baselineAverage: e.base, baselineDays: 14,
          lowestDay: lowest ? { date: lowest.date, level: lowest.level } : null, empty: !daily.length },
        spokenHealth: { source: SPOKEN_SRC, categories: e.cats, empty: !e.cats.length },
        safety: { source: '系統紀錄（守護腦風險評估）', counts: safety, highOrCritical: hi, empty: !hi },
        honesty: { allEmpty: false, note: '每一段都標了來源；沒資料的段落寫「這週沒有紀錄」，不是「他沒事」。' },
        partial: [],
      };
    }
    function elderItem(e) {
      const week = weekOf(e);
      const types = e.anomalies().map(function (a) { return a.type; }).filter(function (t, i, arr) { return arr.indexOf(t) === i; }).sort();
      return {
        seatId: e.seatId, seatCode: e.seatId.slice(0, 8).toUpperCase(), label: e.label, siteLabel: e.site,
        flags: { noInteractionToday: week.contact.lastCallDate !== TODAY, lowMood: types.indexOf('mood_drop') >= 0, guardianLit: week.safety.highOrCritical > 0 },
        anomalyTypes: types, lastInteractionDate: week.contact.lastCallDate, partial: [],
      };
    }
    function bySeat(seatId) { return ELDERS.filter(function (e) { return e.seatId === seatId; })[0] || null; }

    // 提醒：發出時間、判定歷程（by＝誰判的）
    const ALERTS = [
      { alertId: 'ALR-' + ymd(1).replace(/-/g, '') + '-3FA2C1', seatId: ELDERS[0].seatId, pick: function () { return moodStreak([3, 2, 1]); }, raisedAt: at(0, 8, 5), marks: [] },
      { alertId: 'ALR-' + ymd(0).replace(/-/g, '') + '-9B04E7', seatId: ELDERS[3].seatId, pick: function () { return moodStreak([3, 1, 0]); }, raisedAt: at(0, 8, 6), marks: [] },
      { alertId: 'ALR-' + ymd(2).replace(/-/g, '') + '-58D1AA', seatId: ELDERS[0].seatId, pick: function () { return guardianLit(1, 2, 21, 40); }, raisedAt: at(1, 8, 10),
        marks: [{ result: 'watching', isReal: 'yes', worthNotifying: null, remark: '已請家屬今晚陪同，明天再確認。', markedAt: at(1, 9, 0), by: 'org_admin' }] },
      { alertId: 'ALR-' + ymd(2).replace(/-/g, '') + '-C7E390', seatId: ELDERS[1].seatId, pick: function () { return guardianLit(1, 2, 15, 20); }, raisedAt: at(1, 8, 10),
        marks: [{ result: 'false_alarm', isReal: 'no', worthNotifying: 'no', remark: '家屬說是在聊電視劇情，本人沒事。', markedAt: at(1, 10, 32), by: 'org_admin' }] },
      { alertId: 'ALR-' + ymd(9).replace(/-/g, '') + '-1D6F2B', seatId: ELDERS[4].seatId, pick: function () { return noContact(9, 6, 3); }, raisedAt: at(6, 8, 0),
        marks: [
          { result: 'watching', isReal: null, worthNotifying: null, remark: '電話沒人接，先請家屬聯絡。', markedAt: at(5, 9, 10), by: 'org_admin' },
          { result: 'correct', isReal: 'yes', worthNotifying: 'yes', remark: '家屬回報住院中，已跟家屬約好出院後再聯絡。', markedAt: at(4, 14, 0), by: 'org_admin' },
        ] },
      { alertId: 'ALR-' + ymd(12).replace(/-/g, '') + '-E40B87', seatId: ELDERS[2].seatId, pick: function () { return noContact(12, 9, 3); }, raisedAt: at(9, 8, 0),
        marks: [{ result: 'correct', isReal: 'yes', worthNotifying: 'yes', remark: '已打電話，本人說手機沒電。', markedAt: at(9, 11, 20), by: 'case_manager' }] },
      { alertId: 'ALR-' + ymd(15).replace(/-/g, '') + '-7A9C35', seatId: ELDERS[6].seatId, pick: function () { return moodStreak([17, 16, 15]); }, raisedAt: at(15, 8, 0),
        marks: [{ result: 'correct', isReal: 'yes', worthNotifying: 'yes', remark: '家裡有事，已安排家訪。', markedAt: at(14, 10, 0), by: 'case_manager' }] },
      { alertId: 'ALR-' + ymd(20).replace(/-/g, '') + '-2C5E18', seatId: ELDERS[5].seatId, pick: function () { return noContact(20, 17, 3); }, raisedAt: at(17, 8, 0),
        marks: [{ result: 'correct', isReal: 'yes', worthNotifying: 'yes', remark: '', markedAt: at(16, 15, 45), by: 'org_admin' }] },
    ];
    function markView(m) {
      const person = staff[m.by] || {};
      return { result: m.result, resultLabel: RESULT_LABELS[m.result] || '', isReal: m.isReal || null, worthNotifying: m.worthNotifying || null,
        remark: m.remark || '', markedAt: m.markedAt, markedBy: person.displayName || '', markedByRole: ROLE_LABELS[person.role] || '' };
    }
    function alertView(raw) {
      const e = bySeat(raw.seatId);
      const a = raw.pick();
      const history = raw.marks.map(markView);
      const latest = history.length ? history[history.length - 1] : null;
      return {
        alertId: raw.alertId, seatId: raw.seatId, seatCode: raw.seatId.slice(0, 8).toUpperCase(), label: e.label, siteLabel: e.site,
        type: a.type, typeLabel: TYPE_LABELS[a.type], when: a.when, fact: a.fact, suggestion: a.suggestion, raisedAt: raw.raisedAt,
        status: latest ? latest.result : 'unmarked', statusLabel: latest ? latest.resultLabel : '還沒判定', lastMark: latest, markHistory: history,
      };
    }

    const AUDIT = [
      { at: at(0, 9, 12), action: '看了週關懷摘要', eventType: 'org_care_week_read', by: 'case_manager', seat: ELDERS[0].seatId },
      { at: at(1, 10, 32), action: '判定了一筆提醒', eventType: 'org_alert_marked', by: 'org_admin', seat: ELDERS[1].seatId, result: '誤報' },
      { at: at(1, 9, 0), action: '判定了一筆提醒', eventType: 'org_alert_marked', by: 'org_admin', seat: ELDERS[0].seatId, result: '觀察中' },
      { at: at(1, 8, 55), action: '看了週關懷摘要', eventType: 'org_care_week_read', by: 'org_admin', seat: ELDERS[0].seatId },
      { at: at(2, 16, 40), action: '長輩（或家人）打開了同意', eventType: 'org_consent_granted', by: '', seat: ELDERS[5].seatId },
      { at: at(4, 14, 0), action: '判定了一筆提醒', eventType: 'org_alert_marked', by: 'org_admin', seat: ELDERS[4].seatId, result: '正確' },
      { at: at(5, 9, 10), action: '判定了一筆提醒', eventType: 'org_alert_marked', by: 'org_admin', seat: ELDERS[4].seatId, result: '觀察中' },
      { at: at(6, 11, 5), action: '第一次登入', eventType: 'org_staff_activated', by: 'care_worker', seat: null },
      { at: at(8, 19, 20), action: '長輩（或家人）關掉了同意', eventType: 'org_consent_revoked', by: '', seat: 'f1c3b8e2-7d4a-4e6b-9c0f-1a2b3c4d5e6f' },
      { at: at(9, 11, 20), action: '判定了一筆提醒', eventType: 'org_alert_marked', by: 'case_manager', seat: ELDERS[2].seatId, result: '正確' },
      { at: at(14, 10, 0), action: '判定了一筆提醒', eventType: 'org_alert_marked', by: 'case_manager', seat: ELDERS[6].seatId, result: '正確' },
      { at: at(16, 15, 45), action: '判定了一筆提醒', eventType: 'org_alert_marked', by: 'org_admin', seat: ELDERS[5].seatId, result: '正確' },
    ];
    function auditView(it) {
      const person = staff[it.by] || null;
      return { at: it.at, action: it.action, eventType: it.eventType, actor: person ? person.displayName : '長輩或家人',
        actorRole: person ? ROLE_LABELS[person.role] || '' : '', seatCode: it.seat ? it.seat.slice(0, 8).toUpperCase() : null, result: it.result || null };
    }

    function summaryFor(me) {
      const scoped = me.capabilities.siteScoped && me.capabilities.siteLabel;
      const isEsg = me.org.clientKind === 'esg';
      const big = isEsg
        ? { quota: 50, active: 23, active30: 18, rate: 0.7826, retention: 0.85, base: 20, avg: 3.1, high: 2, med: 0.88, decided: 160 }
        : { quota: 20, active: 12, active30: 10, rate: 0.8333, retention: 0.9, base: 10, avg: 4.6, high: 3, med: 0.92, decided: 214 };
      const active = scoped ? 4 : big.active;
      const small = active < 5;
      return {
        ok: true,
        org: { name: me.org.name, planTier: me.org.planTier, contractStart: (now.getFullYear()) + '-01-01', contractEnd: me.org.contractEnd },
        seats: { quota: big.quota, active: active, pending: 0, released: 0, unusedQuota: Math.max(big.quota - active, 0), utilization: Math.round((active / big.quota) * 10000) / 10000 },
        period: { start: ymd(29), end: TODAY, days: 30, previousStart: ymd(59) },
        usage: { enabledCount: active, activeCount: scoped ? 4 : big.active30, activeRate: small ? null : big.rate, retentionRate: small ? null : big.retention,
          retentionBaseCount: small ? null : big.base, avgWeeklyInteractionsPerPerson: small ? null : big.avg, smallSampleSuppressed: small },
        guardian: { highRiskEventCount: small ? null : big.high, followedUpCount: null, followUpTrackingAvailable: false,
          medicationCompletionRate: small ? null : big.med, medicationDecidedCount: small ? null : big.decided, smallSampleSuppressed: small },
        reports: { count: 0, list: [] },
        privacy: { personalDataIncluded: false, smallSampleSuppressed: small, minGroupSize: 5, statement: '' },
        generatedAt: now.toISOString(),
        scope: { siteLabel: me.capabilities.siteLabel, siteScoped: me.capabilities.siteScoped },
        consent: me.capabilities.elders ? { grantedSeats: ELDERS.filter(function (e) { return inScope(me, e.site); }).length } : null,
      };
    }

    function reportsFor() {
      const list = [];
      for (let back = 1; back <= 3; back += 1) {
        const first = new Date(now.getFullYear(), now.getMonth() - back, 1);
        const last = new Date(now.getFullYear(), now.getMonth() - back + 1, 0);
        const made = new Date(now.getFullYear(), now.getMonth() - back + 1, 3, 9, 0);
        list.push({ id: 'rep-demo-' + back, period: first.getFullYear() + '年' + (first.getMonth() + 1) + '月',
          periodStart: first.getFullYear() + '-' + pad(first.getMonth() + 1) + '-01',
          periodEnd: last.getFullYear() + '-' + pad(last.getMonth() + 1) + '-' + pad(last.getDate()),
          generatedAt: made.toISOString(), available: true });
      }
      return { ok: true, reports: { count: list.length, list: list }, downloadToken: 'demo-token', downloadPath: REPORT_PATH };
    }

    function handle(role, path, body) {
      const me = meFor(role);
      const caps = me.capabilities;
      if (path === API.me) return clone(me);
      if (path === API.summary) return clone(summaryFor(me));
      if (path === API.elders) {
        if (!caps.elders) return NF;
        const items = ELDERS.filter(function (e) { return inScope(me, e.site); }).map(elderItem);
        items.sort(function (a, b) { // 照後端：旗標多的在前，同樣多的照稱呼
          const fa = Object.keys(a.flags).filter(function (k) { return a.flags[k]; }).length;
          const fb = Object.keys(b.flags).filter(function (k) { return b.flags[k]; }).length;
          return fb - fa || (a.label < b.label ? -1 : a.label > b.label ? 1 : 0);
        });
        return clone({ ok: true, period: { start: ymd(6), end: TODAY, days: 7 }, scope: { siteLabel: caps.siteLabel, siteScoped: caps.siteScoped, level: caps.level },
          count: items.length, elders: items, partial: [], privacy: { statement: '只列出長輩或家人已同意「機構照護模式」的人；沒同意的不會出現在這裡。沒有對話內容。' } });
      }
      if (path === API.careWeek) {
        if (!caps.careWeek) return NF;
        const e = bySeat(String(body.seatId || ''));
        if (!e || !inScope(me, e.site)) return NF;
        return clone({ ok: true, seatId: e.seatId, seatCode: e.seatId.slice(0, 8).toUpperCase(), label: e.label, siteLabel: e.site, week: weekOf(e),
          anomalies: e.anomalies().map(function (a) { return { type: a.type, when: a.when, fact: a.fact, suggestion: a.suggestion }; }), partial: [],
          privacy: { statement: '這一頁是事實排列不是判定；沒有對話內容、沒有原句。這次查看已留下紀錄（誰、何時、看了誰）。' } });
      }
      if (path === API.alerts) {
        if (!caps.careWeek) return NF;
        if (DEMO_FAIL === 'alerts') return { ok: false, error: 'alerts_unavailable' };
        const views = ALERTS.map(alertView).filter(function (a) { return inScope(me, a.siteLabel); });
        views.sort(function (a, b) { return a.raisedAt < b.raisedAt ? 1 : a.raisedAt > b.raisedAt ? -1 : 0; });
        const t = tally(views);
        return clone({ ok: true, count: views.length, alerts: views, counts: t.counts,
          accuracy: { correct: t.counts.correct, falseAlarm: t.counts.false_alarm, judged: t.judged, rate: t.rate === null ? null : Math.round(t.rate * 10000) / 10000,
            method: '正確 ÷（正確＋誤報）；觀察中不計。漏報要對照情境演練劇本另外算，不在這裡。' },
          scope: { siteLabel: caps.siteLabel, siteScoped: caps.siteScoped }, canMark: true, lookbackDays: 90, partial: [],
          privacy: { statement: '只列已同意長輩的提醒；提醒內容是規則的固定句型，沒有對話原句。每一筆判定都會留下紀錄（誰、何時、判成什麼），不能刪改。' } });
      }
      if (path === API.mark) {
        if (!caps.careWeek) return NF;
        if (['correct', 'false_alarm', 'watching'].indexOf(body.result) < 0) return { ok: false, error: 'result_invalid', allowed: ['correct', 'false_alarm', 'watching'] };
        if (DEMO_FAIL === 'mark') return { ok: false, error: 'mark_not_recorded' };
        const raw = ALERTS.filter(function (a) { return a.alertId === body.alertId; })[0];
        if (!raw || !inScope(me, bySeat(raw.seatId).site)) return NF;
        raw.marks.push({ result: body.result, isReal: body.isReal || null, worthNotifying: body.worthNotifying || null,
          remark: cleanRemark(body.remark), markedAt: new Date().toISOString(), by: role });
        AUDIT.unshift({ at: new Date().toISOString(), action: '判定了一筆提醒', eventType: 'org_alert_marked', by: role, seat: raw.seatId, result: RESULT_LABELS[body.result] });
        return clone({ ok: true, alert: alertView(raw) });
      }
      if (path === API.audit) {
        if (me.staff.role !== 'org_admin' || me.org.clientKind === 'esg') return NF;
        if (DEMO_FAIL === 'audit') return { ok: false, error: 'audit_unavailable' };
        return clone({ ok: true, count: AUDIT.length, items: AUDIT.map(auditView), lookbackDays: 90 });
      }
      if (path === API.reports) return caps.reports ? clone(reportsFor()) : NF;
      if (path === API.settings) {
        if (!caps.careWeek) return NF;
        return clone({ ok: true, settings: settings, canEdit: me.staff.role === 'org_admin', limits: { noContactDays: NO_CONTACT_LIMITS } });
      }
      if (path === API.settingsSave) {
        if (me.staff.role !== 'org_admin' || me.org.clientKind === 'esg') return NF;
        const n = Number(body.noContactDays);
        if (!(Math.round(n) === n && n >= 1 && n <= 30)) return { ok: false, error: 'no_contact_days_invalid', allowed: NO_CONTACT_LIMITS };
        if (DEMO_FAIL === 'settings') return { ok: false, error: 'settings_not_recorded' };
        settings.noContactDays = n;
        settings.updatedAt = new Date().toISOString();
        AUDIT.unshift({ at: settings.updatedAt, action: '改了提醒設定', eventType: 'org_settings_saved', by: role, seat: null });
        return clone({ ok: true, settings: settings });
      }
      return NF;
    }

    return { handle: handle };
  }

  // ───────────────────────── 開機 ─────────────────────────
  async function boot() {
    if (!root) return;
    if (DEMO) {
      D.title = '示範資料 · ' + D.title;
      return demoRole === 'guest' ? renderLogin() : enter();
    }
    renderLoading();
    try {
      await auth.load();
    } catch (e) {
      return renderFatal('login_unavailable', boot);
    }
    const token = await auth.token();
    if (!token) return renderLogin();
    return enter();
  }

  boot();
})();
