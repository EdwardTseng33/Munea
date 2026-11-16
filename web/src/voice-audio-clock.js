(function exposeVoiceAudioClock(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.MuneaVoiceAudioClock = api;
})(typeof window !== 'undefined' ? window : globalThis, function buildVoiceAudioClock() {
  'use strict';

  // 撥號前確認「聲音引擎的時鐘真的在走」（2026-11-16）。
  //
  // 真機證據（2026-11-13，App 1.0.71）：App 從背景回到前景後，下一通的聲音引擎
  // 狀態寫 running、麥克風軌道 live，但 currentTime 停在 0——收音程式一次都沒被叫到，
  // 一包聲音都送不出去，18 秒後整通被收掉。換一顆新的引擎時鐘一樣不走，
  // 所以「狀態」不能信，只能量時鐘。
  //
  // 這個檔只做兩件事，而且不碰任何聲音內容：
  //   measure()  在一小段時間內看 currentTime 有沒有前進
  //   ensure()   時鐘不走就照順序一層一層救，每層做完都重新量一次，並回報哪一層有效
  // 真正的救法（暫停再恢復、換聲音工作階段、叫原生層、整組重建）由 app.js 傳進來，
  // 這裡只管順序與量測，方便用假時鐘測試。

  const DEFAULTS = Object.freeze({
    windowMs: 300,        // 最多看這麼久
    pollMs: 50,           // 每隔這麼久看一次；一看到有前進就提早收工（正常通話只多等一格）
    minAdvanceSec: 0.02,  // 前進超過這麼多才算「在走」
  });

  // running＝自稱在跑但時鐘不走（11/13 真機的樣子）；interrupted＝只有 iPhone 有的「被系統打斷」。
  const ESCALATE_STATES = Object.freeze(['running', 'interrupted']);

  const realSleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  function readTime(ctx) {
    try {
      const value = Number(ctx && ctx.currentTime);
      return Number.isFinite(value) ? value : null;
    } catch (error) { return null; }
  }

  function readState(ctx) {
    try { return String((ctx && ctx.state) || 'none'); } catch (error) { return 'unknown'; }
  }

  function errorCode(error) {
    if (!error) return '';
    const raw = typeof error === 'string' ? error : (error.name || error.message || String(error));
    return String(raw).replace(/\s+/g, '_').slice(0, 64);
  }

  async function measure(ctx, options) {
    const config = Object.assign({}, DEFAULTS, options || {});
    const sleep = typeof config.sleep === 'function' ? config.sleep : realSleep;
    const start = readTime(ctx);
    if (start === null) {
      return { ticking: false, advancedMs: 0, waitedMs: 0, state: readState(ctx), startTime: null };
    }
    let waited = 0;
    let advanced = 0;
    while (waited < config.windowMs) {
      const step = Math.max(1, Math.min(config.pollMs, config.windowMs - waited));
      await sleep(step);
      waited += step;
      const now = readTime(ctx);
      advanced = now === null ? 0 : now - start;
      if (advanced >= config.minAdvanceSec) break;
    }
    return {
      ticking: advanced >= config.minAdvanceSec,
      advancedMs: Math.round(Math.max(0, advanced) * 1000),
      waitedMs: waited,
      state: readState(ctx),
      startTime: +start.toFixed(2),
    };
  }

  // 一行看完每層結果，例如 "web_suspend_resume:no,web_audio_session:skip,native_audio_session:ok"
  function trailOf(attempts) {
    return (attempts || []).map(attempt =>
      attempt.layer + ':' + (attempt.ran ? (attempt.ticking ? 'ok' : 'no') : 'skip')).join(',');
  }

  // options:
  //   measure()      → Promise<{ ticking, state, ... }>   每次呼叫都重新量「現在那顆」引擎
  //   layers         → [{ name, available?(), run() }]     由輕到重
  //   report(kind, details)  kind = stalled | step | recovered | unrecovered
  //   isCancelled()  使用者已取消撥號 → 立刻收工，不再往下救
  //   now()          測試用的時鐘
  //
  // 回傳 ok=false 只有一種情況：每一層都試過，引擎仍然「自稱 running、時鐘不走」。
  // 其他狀態（suspended／interrupted）已有既有的「點一下畫面」等處理，這裡不擋撥號。
  async function ensure(options) {
    const config = options || {};
    const measureNow = config.measure;
    const layers = Array.isArray(config.layers) ? config.layers : [];
    const report = typeof config.report === 'function' ? config.report : () => {};
    const isCancelled = typeof config.isCancelled === 'function' ? config.isCancelled : () => false;
    const now = typeof config.now === 'function' ? config.now : () => Date.now();
    const startedAt = now();
    const attempts = [];
    const finish = (ok, outcome, extra) => Object.assign({
      ok, outcome, recoveredBy: '', attempts, trail: trailOf(attempts), totalMs: Math.max(0, now() - startedAt),
    }, extra || {});
    const safeReport = (kind, details) => { try { report(kind, details); } catch (error) {} };

    const first = await measureNow();
    if (first && first.ticking) return finish(true, 'healthy', { first });
    if (isCancelled()) return finish(true, 'cancelled', { first });
    safeReport('stalled', Object.assign({}, first));

    let last = first || { ticking: false, state: 'unknown' };
    for (const layer of layers) {
      if (isCancelled()) return finish(true, 'cancelled', { first, last });
      // 較重的幾層只對 iPhone 的卡死狀態出手。試過第一層後引擎若只是 suspended
      //（一般瀏覽器在等使用者點一下才准出聲），不拆麥克風、不動系統設定，直接交還原流程。
      if (attempts.length > 0 && ESCALATE_STATES.indexOf(String(last.state || '')) < 0) break;
      const layerStartedAt = now();
      let ran = true;
      let note = '';
      let detail = null;
      try {
        if (typeof layer.available === 'function' && !layer.available()) {
          ran = false;
          note = 'unavailable';
        } else {
          detail = await layer.run();
        }
      } catch (error) {
        note = errorCode(error) || 'layer_failed';
      }
      // 每一層做完都重新量時鐘：只有量到真的在走，才算這一層救回來。
      if (ran) last = (await measureNow()) || last;
      const attempt = {
        layer: String(layer.name || 'unnamed'),
        ran,
        ticking: !!(ran && last && last.ticking),
        state: String((last && last.state) || 'unknown'),
        advancedMs: ran && last ? Number(last.advancedMs) || 0 : 0,
        ms: Math.max(0, now() - layerStartedAt),
        note,
        detail,
      };
      attempts.push(attempt);
      safeReport('step', Object.assign({ step: attempts.length }, attempt));
      if (attempt.ticking) {
        const done = finish(true, 'recovered', { recoveredBy: attempt.layer, first, last });
        safeReport('recovered', { layer: attempt.layer, step: attempts.length, totalMs: done.totalMs, trail: done.trail });
        return done;
      }
    }

    const blocking = String((last && last.state) || '') === 'running';
    const done = finish(!blocking, blocking ? 'unrecovered' : 'not_running_passthrough', { first, last });
    safeReport('unrecovered', {
      state: String((last && last.state) || 'unknown'), blocking, totalMs: done.totalMs, trail: done.trail,
    });
    return done;
  }

  return { DEFAULTS, measure, ensure, trailOf };
});
