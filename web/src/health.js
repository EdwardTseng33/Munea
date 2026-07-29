/* 沐寧 · Apple 健康（HealthKit）網頁橋接
   跟原生外掛 Capacitor.Plugins.Health 對接（原生程式：ios/App/App/HealthPlugin.swift）。
   - 只在 iPhone 真機（有原生外掛）才會動；網頁/模擬器自動變空轉，不影響其他功能。
   - 讀到的值：丟給狀態頁的 window.__muneaSetHealth（Windows 端負責呈現）＋步數餵給首頁走路任務。
   對接文件：docs/Apple健康串接-給Mac的實作說明-2026-07-08.md */
window.MuneaHealth = (function () {
  const GOAL = 500; // 走路任務目標步數（跟首頁「今天走 500 步」一致）
  const REFRESH_COOLDOWN_MS = 60000;
  let disconnectArmTimer = null;
  let refreshPromise = null;
  let lastRefreshAt = 0;
  let lastSummary = null;
  // 讀到資料了沒：true=至少一項有值、false=一項都沒有、null=還沒讀過（不亂猜）
  let hasData = null;

  function plugin() {
    return (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Health) || null;
  }
  function isNative() {
    try { return !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()); }
    catch (e) { return false; }
  }
  // 這台裝置能不能用（有原生外掛 = 在 App 裡）
  function available() { return !!plugin(); }
  function connected() { try { return localStorage.getItem('munea.devicesOn') === '1'; } catch (e) { return false; } }

  // 蘋果不會告訴 App「使用者拒絕了讀取」——授權視窗跳過就一律算成功。
  // 所以「有沒有真的連上」只能看讀不讀得到值，不能看 requestAuthorization 的回覆。
  function hasAnyValue(s) {
    if (!s) return false;
    return ['steps', 'hr', 'spo2', 'bpSys', 'bpDia', 'sleepHours']
      .some(k => typeof s[k] === 'number' && isFinite(s[k]) && s[k] > 0);
  }
  function setHasData(v) {
    hasData = v;
    try {
      if (v === null) localStorage.removeItem('munea.health.hasData');
      else localStorage.setItem('munea.health.hasData', v ? '1' : '0');
    } catch (e) {}
  }
  // 上次真的讀到的摘要（重開 App 後、第一次刷新回來前也要有依據，不能空窗期亂猜）
  function cachedSummary() {
    if (lastSummary) return lastSummary;
    try {
      const raw = JSON.parse(localStorage.getItem('munea.health.last') || 'null');
      return raw && raw.s ? raw.s : null;
    } catch (e) { return null; }
  }

  // 每一項指標現在是什麼狀態：
  //   'off'   還沒連 Apple 健康
  //   'ok'    真的讀到值了
  //   'empty' 連了，但這一項讀不到（沒授權這項、或這支手機還沒有這種紀錄）
  // 畫面一律照這個渲染。不可以用「使用者按過連接鍵」當作有資料——
  // 蘋果不會告訴 App 讀取被拒絕，按過鍵不代表讀得到任何東西。
  function metricStates() {
    const all = v => ({ bp: v, hr: v, spo2: v, sleep: v, steps: v });
    if (!connected()) return all('off');
    const s = cachedSummary();
    if (!s) return all('empty');
    const has = k => typeof s[k] === 'number' && isFinite(s[k]) && s[k] > 0;
    return {
      bp: (has('bpSys') && has('bpDia')) ? 'ok' : 'empty',
      hr: has('hr') ? 'ok' : 'empty',
      spo2: has('spo2') ? 'ok' : 'empty',
      sleep: has('sleepHours') ? 'ok' : 'empty',
      steps: has('steps') ? 'ok' : 'empty'
    };
  }

  function loadHasData() {
    try {
      const v = localStorage.getItem('munea.health.hasData');
      hasData = v === '1' ? true : v === '0' ? false : null;
    } catch (e) { hasData = null; }
  }

  function renderConnectionState() {
    const on = connected();
    const blank = on && hasData === false;   // 說已連接、卻一項都讀不到
    const btn = document.getElementById('cnHealthBtn');
    if (btn) {
      btn.classList.toggle('done', on);
      btn.classList.toggle('disconnect', on);
      btn.classList.remove('arm');
      delete btn.dataset.disconnectArmed;
      btn.textContent = on ? '解除連接' : (btn.dataset.label || '連接');
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    const state = document.getElementById('healthSettingsState');
    if (state) state.classList.toggle('off', !on);
    const stateLabel = document.getElementById('healthSettingsStateLabel');
    if (stateLabel) stateLabel.textContent = !on ? '未連接' : blank ? '讀不到資料' : '已連接';
    const detail = document.getElementById('cnHealthDetail');
    if (detail) detail.textContent = !on
      ? '自動含手錶與其他裝置 · 步數/心率/睡眠/血壓/血氧'
      : blank
        ? '已連接，但目前一項資料都讀不到'
        : '正在同步步數、心率、睡眠、血壓與血氧';
    const help = document.getElementById('cnHealthHelp');
    if (help) help.textContent = !on
      ? '目前未同步。重新連接後才會讀取新的健康資料。'
      : blank
        ? '沐寧還讀不到任何一項。請打開手機的「健康」App → 右上角的個人照片 → 「App 與服務」→ 沐寧 → 把要給沐寧看的項目打開（步數、心率、睡眠、血壓、血氧）。如果這支手機本來就還沒有這些紀錄，等有了就會自己出現。'
        : '解除連接會停止沐寧後續同步，既有紀錄仍會保留。要撤銷 Apple 健康的系統授權，請到「健康 App」的個人頭像／隱私權設定中管理沐寧。';
  }

  function emitConnectionState() {
    setTimeout(renderConnectionState, 0);
    try { window.dispatchEvent(new CustomEvent('munea:health-connection', { detail: { connected: connected() } })); } catch (e) {}
  }

  // 使用者點「連接 Apple 健康」→ 跳系統授權 → 讀一次資料
  async function connect() {
    const p = plugin();
    if (!p) return { ok: false, reason: 'unsupported' }; // 不在 App 裡（網頁預覽）
    try {
      const r = await p.requestAuthorization();
      if (r && r.available === false) return { ok: false, reason: 'unavailable' }; // 這台沒有健康資料
      try { localStorage.setItem('munea.devicesOn', '1'); } catch (e) {}
      const s = await refresh({ force: true });
      emitConnectionState();
      // 一項都沒讀到就照實說：多半是授權視窗裡沒打開項目，也可能這支手機本來就沒紀錄。
      // 蘋果不讓 App 分辨這兩者，所以不猜原因、只講現況跟怎麼開。
      if (!hasAnyValue(s)) return { ok: true, empty: true, summary: s };
      return { ok: true, summary: s };
    } catch (e) {
      return { ok: false, reason: 'error', message: String(e) };
    }
  }

  // 讀最新健康摘要，餵回網頁
  async function refresh(options) {
    if (!connected()) return null;
    const p = plugin();
    if (!p) return null;
    if (refreshPromise) return refreshPromise;
    const force = !!(options && options.force);
    if (!force && lastRefreshAt && Date.now() - lastRefreshAt < REFRESH_COOLDOWN_MS) return lastSummary;

    lastRefreshAt = Date.now();
    refreshPromise = (async function () {
      let s = null;
      try { s = await p.getSummary(); } catch (e) { return null; }
      if (!connected()) return null;
      if (!s || s.available === false) return null;
      // 記住這次到底有沒有值——沒有的話畫面要照實講，不能繼續寫「正在同步」
      setHasData(hasAnyValue(s));
      setTimeout(renderConnectionState, 0);
      lastSummary = s;
      // 狀態頁血壓/心率/睡眠等欄位：交給 Windows 端留的接口
      try { if (typeof window.__muneaSetHealth === 'function') window.__muneaSetHealth(s); } catch (e) {}
      // 數字寫完後再跑一次誠實層：這次沒讀到的項目要收回「—」並把標籤藏起來，
      // 否則上一輪讀到、這一輪讀不到時，畫面會留著舊值跟舊標籤繼續宣稱。
      try { if (typeof window.MMDEV === 'function') window.MMDEV(); } catch (e) {}
      // 步數 → 首頁走路任務（app.js 的接口）
      if (typeof s.steps === 'number' && typeof window.__muneaSetSteps === 'function') {
        try { window.__muneaSetSteps(s.steps); } catch (e) {}
      }
      try {
        if (typeof p.getHistory === 'function' && typeof window.__muneaSetHealthHistory === 'function') {
          const history = await p.getHistory({ days: 35 });
          if (connected() && history && history.available !== false && Array.isArray(history.days)) {
            window.__muneaSetHealthHistory(history.days);
          }
        }
      } catch (e) {}
      try { localStorage.setItem('munea.health.last', JSON.stringify({ t: Date.now(), s: s })); } catch (e) {}
      return s;
    })();
    try { return await refreshPromise; }
    finally { refreshPromise = null; }
  }

  function disconnect() {
    try {
      localStorage.removeItem('munea.devicesOn');
      localStorage.setItem('munea.health.disconnectedAt', String(Date.now()));
    } catch (e) {}
    setHasData(null);
    emitConnectionState();
    return { ok: true, authorizationRetained: true };
  }

  function bindConnectionUi() {
    const btn = document.getElementById('cnHealthBtn');
    if (!btn) return;
    btn.addEventListener('click', function (event) {
      if (!connected()) {
        setTimeout(renderConnectionState, 0);
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      if (btn.dataset.disconnectArmed !== '1') {
        btn.dataset.disconnectArmed = '1';
        btn.classList.add('arm');
        btn.textContent = '再按一次解除';
        clearTimeout(disconnectArmTimer);
        disconnectArmTimer = setTimeout(renderConnectionState, 4000);
        return;
      }
      clearTimeout(disconnectArmTimer);
      disconnect();
    }, true);
    renderConnectionState();
  }

  // App 啟動：之前連過就靜默刷新一次（含把步數帶回走路任務）
  function boot() {
    loadHasData();
    renderConnectionState();
    if (available() && connected()) { refresh(); }
  }

  loadHasData();
  bindConnectionUi();

  return { GOAL: GOAL, REFRESH_COOLDOWN_MS: REFRESH_COOLDOWN_MS, available: available, connected: connected, connect: connect, disconnect: disconnect, refresh: refresh, renderConnectionState: renderConnectionState, boot: boot, isNative: isNative, metricStates: metricStates, hasAnyValue: hasAnyValue };
})();
