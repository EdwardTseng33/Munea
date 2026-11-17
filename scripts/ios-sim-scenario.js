
// ===== MUNEA iOS SIMULATOR SCENARIO (test builds only) =====
// Appended to the GENERATED ios/App/App/public/src/auth-config.js by the iOS simulator
// test workflow. Never part of web/ or of any shipped build. It drives the real App UI:
// several calls, a background/foreground round trip between calls, a direct poke of the
// native AudioSession plugin, and leaving the screen in the middle of a call.
(function () {
  if (window.__MUNEA_SIM_SCENARIO__) return;
  window.__MUNEA_SIM_SCENARIO__ = true;
  var T0 = Date.now();
  var lines = [];
  var q = function (s) { return document.querySelector(s); };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  function slim(v) {
    try { var s = JSON.stringify(v); return s && s.length > 900 ? s.slice(0, 900) + '...' : v; } catch (e) { return String(v); }
  }
  function overlay() {
    var el = document.getElementById('__simOverlay');
    if (!el && document.body) {
      el = document.createElement('div');
      el.id = '__simOverlay';
      el.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;pointer-events:none;'
        + 'font:9px/1.25 Menlo,monospace;color:#fff;background:rgba(0,0,0,.72);padding:3px 5px;white-space:pre-wrap;word-break:break-all';
      document.body.appendChild(el);
    }
    if (el) el.textContent = lines.slice(-7).join('\n');
  }
  // The console channel works on the simulator, so keep screenshots clean: no overlay.
  overlay = function () {};
  function log(tag, obj) {
    var line;
    try { line = tag + ' ' + JSON.stringify(Object.assign({ t: Date.now() - T0 }, obj || {})); } catch (e) { line = tag + ' {}'; }
    lines.push(line.slice(0, 160));
    try { console.log('MUNEA_SIM ' + line); } catch (e) {}
    try { overlay(); } catch (e) {}
  }
  window.addEventListener('error', function (e) { log('JS_ERROR', { m: String(e && e.message).slice(0, 200) }); });
  window.addEventListener('unhandledrejection', function (e) { log('JS_REJECTION', { m: String(e && e.reason).slice(0, 200) }); });

  // Product events the App sends to the backend (state only, never conversation content).
  var origFetch = window.fetch;
  window.fetch = function (input, init) {
    try {
      var url = typeof input === 'string' ? input : ((input && input.url) || '');
      if (url.indexOf('/product-event') >= 0 && init && typeof init.body === 'string') {
        var b = JSON.parse(init.body);
        if (/^voice_/.test(b.eventName || '')) log('EVENT', { name: b.eventName, p: slim(b.properties) });
      }
      // The two requests 1.0.71 always had rejected: do they carry both credentials now, and what comes back?
      var hit = /\/(wellbeing\/[a-z]+|notifications(\/settings)?|push\/devices)(\?|$)/.exec(url);
      if (hit) {
        var hs = (init && init.headers) || {};
        var names = (typeof hs.forEach === 'function' && !Array.isArray(hs))
          ? (function () { var out = []; hs.forEach(function (v, k) { out.push(k); }); return out; })()
          : Object.keys(hs);
        var lower = names.map(function (n) { return String(n).toLowerCase(); });
        var info = { path: hit[1], appKey: lower.indexOf('x-munea-key') >= 0, signIn: lower.indexOf('authorization') >= 0 };
        return origFetch.apply(this, arguments).then(function (res) {
          log('GATED_REQUEST', Object.assign(info, { status: res.status }));
          return res;
        }, function (err) {
          log('GATED_REQUEST', Object.assign(info, { status: 'network_error' }));
          throw err;
        });
      }
    } catch (e) {}
    return origFetch.apply(this, arguments);
  };

  function text(sel) { var el = q(sel); return el ? (el.textContent || '').trim().slice(0, 80) : null; }
  function snap() {
    var btn = q('#callToggle'), card = q('#busyCard'), chat = q('#chat'), fn = q('.face-name');
    return {
      label: text('#callToggleLabel'),
      dialing: !!(btn && btn.classList.contains('dialing')),
      chat: chat ? chat.dataset.state : null,
      online: fn ? !fn.classList.contains('off') : null,
      card: card && !card.hidden ? { title: text('#busyCardTitle'), note: text('#busyCardNote'), btn: text('#busyCardBtn'), mode: card.dataset.mode } : null,
      vis: document.visibilityState,
    };
  }
  function click(sel) { var el = q(sel); if (el) { el.click(); return true; } log('MISSING', { sel: sel }); return false; }
  function plugin() { return window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.AudioSession; }
  async function nativeStatus(tag) {
    try {
      var p = plugin();
      if (!p) { log('NATIVE_STATUS', { tag: tag, present: false }); return; }
      log('NATIVE_STATUS', { tag: tag, r: slim(await p.status()) });
    } catch (e) { log('NATIVE_STATUS_ERR', { tag: tag, m: String(e).slice(0, 200) }); }
  }
  // Same question the App asks before dialing: does a running audio engine's clock actually move?
  async function clockProbe(tag) {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      var ac = new AC();
      try { await Promise.race([ac.resume(), sleep(400)]); } catch (e) {}
      var a = ac.currentTime; await sleep(350); var b = ac.currentTime;
      log('CLOCK_PROBE', { tag: tag, state: ac.state, from: +a.toFixed(3), to: +b.toFixed(3), ticking: b > a });
      try { await ac.close(); } catch (e) {}
    } catch (e) { log('CLOCK_PROBE_ERR', { tag: tag, m: String(e).slice(0, 200) }); }
  }
  document.addEventListener('visibilitychange', function () { log('VISIBILITY', { v: document.visibilityState }); });
  function waitHiddenThenVisible(timeoutMs) {
    return new Promise(function (res) {
      var sawHidden = document.visibilityState === 'hidden', done = false;
      function h() {
        if (document.visibilityState === 'hidden') sawHidden = true;
        else if (sawHidden && !done) { done = true; document.removeEventListener('visibilitychange', h); res(true); }
      }
      document.addEventListener('visibilitychange', h);
      setTimeout(function () { if (!done) { done = true; document.removeEventListener('visibilitychange', h); res(false); } }, timeoutMs);
    });
  }
  var topicsSeen = 0;
  async function dial(name, maxMs) {
    log(name + '_BEGIN', snap());
    click('.tab-btn[data-view="chat"]'); await sleep(1500);
    click('#callToggle');
    var start = Date.now(), last = '', connectedAt = null, cardSince = null;
    while (Date.now() - start < maxMs) {
      await sleep(500);
      var s = snap();
      var key = JSON.stringify([s.label, s.dialing, s.chat, s.online, s.card]);
      if (key !== last) { log(name + '_STATE', s); last = key; }
      // First call ever: the App shows its privacy notice and waits for the person to agree.
      var sheet = q('#consentSheet');
      if (sheet && sheet.classList.contains('show')) {
        await sleep(2500);
        log(name + '_CONSENT_SHEET', { title: text('#consentSheet .mr-say span'), button: text('#consentAgree') });
        click('#consentAgree');
        start = Date.now();
        continue;
      }
      // Asked once before an early call: "topics you like". Record whether the skip link is actually
      // visible to a person, then go on the way a person would (Save with nothing picked starts the call).
      var topics = q('#interestsModal');
      if (topics && topics.classList.contains('show')) {
        await sleep(16000);
        var skip = q('#interestsSkip');
        var closeBtn = q('#interestsModal .mx-close, #interestsModal .auth-close');
        var skipVisible = !!(skip && getComputedStyle(skip).display !== 'none' && skip.offsetHeight > 0);
        topicsSeen += 1;
        log(name + '_TOPICS_SHEET', {
          times: topicsSeen,
          skipText: text('#interestsSkip'),
          skipVisible: skipVisible,
          hasCloseButton: !!closeBtn,
          askedFlag: localStorage.getItem('munea.interestsAsked'),
        });
        if (topicsSeen === 1 && closeBtn) {
          // What a confused person does: close it with the X, then press the call button again.
          // Fixed behaviour: the call goes out. Old behaviour: the same sheet comes back.
          closeBtn.click();
          await sleep(1500);
          log(name + '_TOPICS_CLOSED_WITH_X', { stillOpen: topics.classList.contains('show'), askedFlag: localStorage.getItem('munea.interestsAsked') });
          click('#callToggle');
        } else {
          log(name + '_TOPICS_CAME_BACK', { times: topicsSeen });
          click('#interestsSave');
        }
        start = Date.now();
        continue;
      }
      if (s.online && !connectedAt) { connectedAt = Date.now(); log(name + '_CONNECTED', { afterMs: connectedAt - start }); break; }
      if (s.card && !s.dialing && !s.online) { cardSince = cardSince || Date.now(); if (Date.now() - cardSince > 4000) break; } else cardSince = null;
    }
    return { connectedAt: connectedAt, start: start };
  }
  async function hangUp(name) {
    var s = snap();
    log(name + '_BEFORE_HANGUP', s);
    if (s.online || s.dialing) { click('#callToggle'); await sleep(3000); }
    var after = snap();
    if (after.card) { click('#busyCardBtn'); await sleep(800); }
    log(name + '_DONE', snap());
  }
  async function call(name, holdMs) {
    var r = await dial(name, 45000);
    if (r.connectedAt) await sleep(holdMs);
    await hangUp(name);
    return !!r.connectedAt;
  }
  async function waitFor(fn, timeoutMs) {
    var start = Date.now();
    while (Date.now() - start < timeoutMs) { try { if (fn()) return true; } catch (e) {} await sleep(300); }
    return false;
  }
  async function main() {
    var ready = await waitFor(function () { return q('#callToggle') && q('.tab-btn[data-view="chat"]'); }, 60000);
    await sleep(7000);
    var D = window.MuneaVoiceDiagnostics;
    ['mark', 'fail', 'end'].forEach(function (fn) {
      if (D && typeof D[fn] === 'function') {
        var o = D[fn];
        D[fn] = function () { try { log('DIAG', { fn: fn, a: slim(Array.prototype.slice.call(arguments)) }); } catch (e) {} return o.apply(D, arguments); };
      }
    });
    var cap = window.Capacitor;
    log('BOOT', {
      ready: ready,
      native: !!(cap && cap.isNativePlatform && cap.isNativePlatform()),
      platform: cap && cap.getPlatform && cap.getPlatform(),
      audioSessionPlugin: !!plugin(),
      webAudioSession: !!navigator.audioSession,
      webAudioSessionType: navigator.audioSession ? navigator.audioSession.type : null,
      ua: navigator.userAgent.slice(0, 120),
    });
    // Test builds only: the development auto sign-in can be undone at start-up by a request that
    // left before it (a stale "no session" answer arrives later and overwrites the state).
    // Record it when it happens and sign in again, so the run still tests the calls.
    var authApi = window.MuneaAuth;
    var authStatus = function () { try { return (authApi.state() || {}).status; } catch (e) { return 'unknown'; } };
    await sleep(1500);
    var statusAtBoot = authStatus();
    if (statusAtBoot !== 'signed-in' && authApi && typeof authApi.signInAsDeveloper === 'function') {
      try { await authApi.signInAsDeveloper({ reason: 'sim_scenario_resign' }); } catch (e) {}
      await sleep(800);
    }
    log('SIGN_IN', { atBoot: statusAtBoot, now: authStatus(), resigned: statusAtBoot !== 'signed-in' });
    await nativeStatus('boot');
    await clockProbe('boot');

    var c1 = await call('CALL1', 20000);
    log('PHASE', { name: 'READY_FOR_BACKGROUND_1', connected: c1 });
    var cyc1 = await waitHiddenThenVisible(240000);
    log('PHASE', { name: 'BACK_FROM_BACKGROUND_1', cycled: cyc1 });
    await sleep(2000);
    await nativeStatus('after_background');
    await clockProbe('after_background');
    var c2 = await call('CALL2', 20000);

    try {
      var p = plugin();
      if (p) log('NATIVE_REACTIVATE', { r: slim(await p.reactivate()) });
      else log('NATIVE_REACTIVATE', { present: false });
    } catch (e) { log('NATIVE_REACTIVATE_ERR', { m: String(e).slice(0, 200) }); }
    await nativeStatus('after_reactivate');
    await clockProbe('after_reactivate');
    var c3 = await call('CALL3', 14000);

    var r4 = await dial('CALL4', 45000);
    if (r4.connectedAt) await sleep(4000);
    log('PHASE', { name: 'READY_FOR_BACKGROUND_2', connected: !!r4.connectedAt });
    var cyc2 = await waitHiddenThenVisible(240000);
    await sleep(2500);
    log('CALL4_AFTER_RETURN', Object.assign({ cycled: cyc2 }, snap()));
    await sleep(20000);
    log('CALL4_AFTER_RETURN_LATER', snap());
    await hangUp('CALL4');

    log('SCENARIO_DONE', { call1: c1, call2: c2, call3: c3, call4: !!r4.connectedAt });

    // Short tour so the other 1.0.72 screens get a screenshot each.
    await sleep(3000);
    click('.tab-btn[data-view="status"]'); await sleep(5000); log('TOUR', { at: 'status' }); await sleep(16000);
    click('.tab-btn[data-view="settings"]'); await sleep(3000); log('TOUR', { at: 'settings' }); await sleep(16000);
    var entry = q('#seatCodeEntry');
    if (entry) { try { entry.scrollIntoView({ block: 'center' }); } catch (e) {} entry.click(); }
    await sleep(2500);
    log('TOUR', { at: 'seat-code', modal: !!(q('#seatCodeModal') && q('#seatCodeModal').classList.contains('show')), entry: !!entry });
    await sleep(17000);
    log('TOUR_DONE', {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { main(); });
  else main();
})();
