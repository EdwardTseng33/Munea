/* 沐寧 · 蘋果內購網頁橋接（原生程式：ios/App/App/StorePlugin.swift）
   - 只在 App 裡（有原生外掛）才會動；網頁預覽自動空轉、購買鈕維持示範行為。
   - 付款成功一律走 window.__muneaApplyPurchase(產品ID) 生效（app.js 已備好）。
   - 商品 ID 唯一真相：docs/蘋果內購金流設定-Edward步驟單-2026-07-08.md 第 4 步表。 */
window.MuneaStore = (function () {
  var TX_KEY = 'munea.store.processedTransactions.v1';
  var BRAIN_URL = 'https://munea-brain-staging-491603544409.asia-east1.run.app';
  var APP_KEY = 'mnk_03d3a1545a3c5215b924c162c54e83f2ecd059e5';
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
  function processedTransactions() {
    try {
      var value = JSON.parse(localStorage.getItem(TX_KEY) || '[]');
      return Array.isArray(value) ? value : [];
    } catch (e) { return []; }
  }
  function brainBase() {
    try { return (localStorage.getItem('munea.brainUrl') || BRAIN_URL).replace(/\/$/, ''); } catch (e) { return BRAIN_URL; }
  }
  async function verify(transaction) {
    var auth = window.MuneaAuth;
    var state = auth && typeof auth.state === 'function' ? auth.state() : {};
    var token = auth && typeof auth.getAccessToken === 'function' ? await auth.getAccessToken() : null;
    if (!state.authUserId || !token) return { ok: false, reason: 'signin_required' };
    if (!transaction.signedTransaction) return { ok: false, reason: 'signed_transaction_missing' };
    try {
      var response = await fetch(brainBase() + '/apple/transaction', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token,
          'X-Munea-Key': APP_KEY
        },
        body: JSON.stringify({
          signedTransaction: transaction.signedTransaction,
          transactionId: transaction.transactionId
        })
      });
      var payload = await response.json().catch(function () { return {}; });
      if (!response.ok || !payload.ok || !payload.verified) {
        return { ok: false, reason: (payload.error && payload.error.code) || 'server_verification_failed' };
      }
      return { ok: true, payload: payload };
    } catch (e) {
      return { ok: false, reason: 'server_unavailable' };
    }
  }
  async function finish(transaction) {
    var p = plugin();
    if (!p || !p.finish || !transaction.transactionId) return;
    try { await p.finish({ transactionId: String(transaction.transactionId) }); } catch (e) {}
  }
  async function apply(transaction) {
    var data = typeof transaction === 'string' ? { productId: transaction } : (transaction || {});
    var pid = data.productId || '';
    var txid = String(data.transactionId || '');
    var seen = processedTransactions();
    try {
      var verified = await verify(data);
      if (!verified.ok) return verified;
      if (txid && seen.indexOf(txid) >= 0) { await finish(data); return { ok: true, duplicate: true, verified: true }; }
      if (typeof window.__muneaApplyPurchase !== 'function') return { ok: false };
      var ok = !!window.__muneaApplyPurchase(pid, data);
      if (!ok) return { ok: false };
      var wallet = verified.payload && verified.payload.walletSummary;
      if (wallet && typeof wallet.purchased === 'number') {
        try { localStorage.setItem('munea.ptsBought', String(wallet.purchased)); } catch (e) {}
      }
      if (txid) {
        seen.push(txid);
        localStorage.setItem(TX_KEY, JSON.stringify(seen.slice(-200)));
      }
      await finish(data);
      return { ok: true, duplicate: !!verified.payload.idempotentReplay, verified: true };
    } catch (e) { return { ok: false }; }
  }
  // 背景到帳（自動續訂、家人核准後）→ 直接生效
  (function listen() {
    var p = plugin();
    if (p && p.addListener) {
        try { p.addListener('purchase', function (d) { if (d && d.productId) void apply(d); }); } catch (e) {}
    }
  })();

  // 跳蘋果付款視窗；成功 → 生效 → {ok:true}
  async function purchase(pid) {
    var p = plugin();
    if (!p) return { ok: false, reason: 'unsupported' };
    if (!pid) return { ok: false, reason: 'badid' };
    try {
      var authState = window.MuneaAuth && typeof window.MuneaAuth.state === 'function' ? window.MuneaAuth.state() : {};
      var r = await p.purchase({ productId: pid, appAccountToken: authState.authUserId || '' });
      var st = (r && r.state) || 'error';
      if (st === 'purchased') {
        var applied = await apply(r);
        return { ok: !!applied.ok, duplicate: !!applied.duplicate, verified: !!applied.verified, reason: applied.reason, transactionId: r && r.transactionId };
      }
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
      var transactions = (r && r.transactions) || [];
      var subs = transactions.filter(function (tx) { return tx.productId && tx.productId.indexOf('.points.') < 0; });
      subs.sort(function (a, b) { return (b.productId.indexOf('.pro.') >= 0 ? 1 : 0) - (a.productId.indexOf('.pro.') >= 0 ? 1 : 0); });
      if (subs.length) {
        var restored = await apply(subs[0]);
        return { ok: !!restored.ok, restored: subs[0].productId, reason: restored.reason };
      }
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
