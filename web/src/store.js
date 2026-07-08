/* 沐寧 · 蘋果內購網頁橋接（原生程式：ios/App/App/StorePlugin.swift）
   - 只在 App 裡（有原生外掛）才會動；網頁預覽自動空轉、購買鈕維持示範行為。
   - 付款成功一律走 window.__muneaApplyPurchase(產品ID) 生效（app.js 已備好）。
   - 商品 ID 唯一真相：docs/蘋果內購金流設定-Edward步驟單-2026-07-08.md 第 4 步表。 */
window.MuneaStore = (function () {
  var SUB = {
    'plus|month': 'net.munea.app.plus.monthly',
    'plus|year': 'net.munea.app.plus.yearly',
    'pro|month': 'net.munea.app.pro.monthly',
    'pro|year': 'net.munea.app.pro.yearly'
  };
  var PTS = {
    200: 'net.munea.app.points.200',
    500: 'net.munea.app.points.500',
    1000: 'net.munea.app.points.1000',
    1800: 'net.munea.app.points.1800'
  };
  function plugin() {
    return (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Store) || null;
  }
  function apply(pid) {
    try { if (typeof window.__muneaApplyPurchase === 'function') return window.__muneaApplyPurchase(pid); } catch (e) {}
    return false;
  }
  // 背景到帳（自動續訂、家人核准後）→ 直接生效
  (function listen() {
    var p = plugin();
    if (p && p.addListener) {
      try { p.addListener('purchase', function (d) { if (d && d.productId) apply(d.productId); }); } catch (e) {}
    }
  })();

  // 跳蘋果付款視窗；成功 → 生效 → {ok:true}
  async function purchase(pid) {
    var p = plugin();
    if (!p) return { ok: false, reason: 'unsupported' };
    if (!pid) return { ok: false, reason: 'badid' };
    try {
      var r = await p.purchase({ productId: pid });
      var st = (r && r.state) || 'error';
      if (st === 'purchased') { apply(pid); return { ok: true }; }
      return { ok: false, reason: st }; // cancelled / pending / notfound / unverified
    } catch (e) {
      return { ok: false, reason: 'error', message: String(e) };
    }
  }

  // 換手機/重裝找回訂閱（只回復訂閱、點數是消耗品不會重複入帳）
  async function restore() {
    var p = plugin();
    if (!p) return { ok: false, reason: 'unsupported' };
    try {
      var r = await p.restore();
      var ids = (r && r.productIds) || [];
      var subIds = ids.filter(function (id) { return id.indexOf('net.munea.app.p') === 0 && id.indexOf('.points.') < 0; });
      // Pro 優先於 Plus（權益較高者生效）
      subIds.sort(function (a, b) { return (b.indexOf('.pro.') >= 0 ? 1 : 0) - (a.indexOf('.pro.') >= 0 ? 1 : 0); });
      if (subIds.length) { apply(subIds[0]); return { ok: true, restored: subIds[0] }; }
      return { ok: false, reason: 'none' };
    } catch (e) {
      return { ok: false, reason: 'error', message: String(e) };
    }
  }

  return {
    available: function () { return !!plugin(); },
    subId: function (plan, cyc) { return SUB[plan + '|' + cyc] || null; },
    ptsId: function (n) { return PTS[n] || null; },
    purchase: purchase,
    restore: restore
  };
})();
