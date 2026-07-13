/* 沐寧 · Apple 健康（HealthKit）網頁橋接
   跟原生外掛 Capacitor.Plugins.Health 對接（原生程式：ios/App/App/HealthPlugin.swift）。
   - 只在 iPhone 真機（有原生外掛）才會動；網頁/模擬器自動變空轉，不影響其他功能。
   - 讀到的值：丟給狀態頁的 window.__muneaSetHealth（Windows 端負責呈現）＋步數餵給首頁走路任務。
   對接文件：docs/Apple健康串接-給Mac的實作說明-2026-07-08.md */
window.MuneaHealth = (function () {
  const GOAL = 500; // 走路任務目標步數（跟首頁「今天走 500 步」一致）

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

  // 使用者點「連接 Apple 健康」→ 跳系統授權 → 讀一次資料
  async function connect() {
    const p = plugin();
    if (!p) return { ok: false, reason: 'unsupported' }; // 不在 App 裡（網頁預覽）
    try {
      const r = await p.requestAuthorization();
      if (r && r.available === false) return { ok: false, reason: 'unavailable' }; // 這台沒有健康資料
      try { localStorage.setItem('munea.devicesOn', '1'); } catch (e) {}
      const s = await refresh();
      return { ok: true, summary: s };
    } catch (e) {
      return { ok: false, reason: 'error', message: String(e) };
    }
  }

  // 讀最新健康摘要，餵回網頁
  async function refresh() {
    const p = plugin();
    if (!p) return null;
    let s = null;
    try { s = await p.getSummary(); } catch (e) { return null; }
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
        if (history && history.available !== false && Array.isArray(history.days)) {
          window.__muneaSetHealthHistory(history.days);
        }
      }
    } catch (e) {}
    try { localStorage.setItem('munea.health.last', JSON.stringify({ t: Date.now(), s: s })); } catch (e) {}
    return s;
  }

  // App 啟動：之前連過就靜默刷新一次（含把步數帶回走路任務）
  function boot() { if (available() && connected()) { refresh(); } }

  return { GOAL: GOAL, available: available, connected: connected, connect: connect, refresh: refresh, boot: boot, isNative: isNative };
})();
