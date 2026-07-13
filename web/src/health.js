/* 沐寧 · Apple 健康（HealthKit）網頁橋接
   跟原生外掛 Capacitor.Plugins.Health 對接（原生程式：ios/App/App/HealthPlugin.swift）。
   - 只在 iPhone 真機（有原生外掛）才會動；網頁/模擬器自動變空轉，不影響其他功能。
   - 讀到的值：丟給狀態頁的 window.__muneaSetHealth（Windows 端負責呈現）＋步數餵給首頁走路任務。
   對接文件：docs/Apple健康串接-給Mac的實作說明-2026-07-08.md */
window.MuneaHealth = (function () {
  const GOAL = 500; // 走路任務目標步數（跟首頁「今天走 500 步」一致）
  let disconnectArmTimer = null;

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

  function renderConnectionState() {
    const on = connected();
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
    if (stateLabel) stateLabel.textContent = on ? '已連接' : '未連接';
    const detail = document.getElementById('cnHealthDetail');
    if (detail) detail.textContent = on
      ? '正在同步步數、心率、睡眠、血壓與血氧'
      : '自動含手錶與其他裝置 · 步數/心率/睡眠/血壓/血氧';
    const help = document.getElementById('cnHealthHelp');
    if (help) help.textContent = on
      ? '解除連接會停止沐寧後續同步，既有紀錄仍會保留。要撤銷 Apple 健康的系統授權，請到「健康 App」的個人頭像／隱私權設定中管理沐寧。'
      : '目前未同步。重新連接後才會讀取新的健康資料。';
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
      const s = await refresh();
      emitConnectionState();
      return { ok: true, summary: s };
    } catch (e) {
      return { ok: false, reason: 'error', message: String(e) };
    }
  }

  // 讀最新健康摘要，餵回網頁
  async function refresh() {
    if (!connected()) return null;
    const p = plugin();
    if (!p) return null;
    let s = null;
    try { s = await p.getSummary(); } catch (e) { return null; }
    if (!connected()) return null;
    if (!s || s.available === false) return null;
    // 狀態頁血壓/心率/睡眠等欄位：交給 Windows 端留的接口
    try { if (typeof window.__muneaSetHealth === 'function') window.__muneaSetHealth(s); } catch (e) {}
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
  }

  function disconnect() {
    try {
      localStorage.removeItem('munea.devicesOn');
      localStorage.setItem('munea.health.disconnectedAt', String(Date.now()));
    } catch (e) {}
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
    renderConnectionState();
    if (available() && connected()) { refresh(); }
  }

  bindConnectionUi();

  return { GOAL: GOAL, available: available, connected: connected, connect: connect, disconnect: disconnect, refresh: refresh, renderConnectionState: renderConnectionState, boot: boot, isNative: isNative };
})();
