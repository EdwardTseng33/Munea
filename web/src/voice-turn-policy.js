(function exposeVoiceTurnPolicy(root, factory) {
  const policy = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = policy;
  if (root) root.MuneaVoiceTurnPolicy = policy;
})(typeof window !== 'undefined' ? window : globalThis, function buildVoiceTurnPolicy() {
  const DEFAULTS = Object.freeze({
    minRms: 0.028,
    maxRms: 0.07,
    noiseMultiplier: 4,
    sustainMs: 150,
    // 預捲必須「蓋得住」對應的持續人聲門檻，開頭的字才補得回來（2026-07-16 Edward「回長話第一句沒反應」）：
    // 一格 ≈ 42.7ms（2048 樣本 @48kHz）。平常門檻 150ms → 10 格 ≈ 427ms；
    // 開場門檻 300ms（openingSustainMs）→ 用 openingPreRollFrames 18 格 ≈ 768ms，含起音爬升與中途小停頓的餘裕。
    preRollFrames: 10,
    openingPreRollFrames: 18,
    // 講完後守門期（2026-07-16）：她停口後這段時間內，收音仍走「持續人聲才放行」，
    // 蓋住 GLOWS 偶發 1.8~2s 供聲卡點的句中空檔——回音/噪音不再裸流上去被當成插話。
    postSpeechGuardMs: 1800,
    // 開場前兩輪 iPhone 回音消除尚未收斂、回音殘留最強：插話所需持續人聲拉長一級。
    openingSustainMs: 300,
  });

  function createState(noiseFloor) {
    return {
      noiseFloor: Number.isFinite(noiseFloor) ? noiseFloor : 0.006,
      speechMs: 0,
    };
  }

  function thresholdFor(state, options) {
    const cfg = { ...DEFAULTS, ...(options || {}) };
    const floor = Math.max(0, Number(state && state.noiseFloor) || 0);
    return Math.min(cfg.maxRms, Math.max(cfg.minRms, floor * cfg.noiseMultiplier));
  }

  function observe(state, rms, frameMs, speakerActive, options) {
    const cfg = { ...DEFAULTS, ...(options || {}) };
    const next = { ...createState(), ...(state || {}) };
    const level = Math.max(0, Number(rms) || 0);
    const duration = Math.max(0, Number(frameMs) || 0);
    const threshold = thresholdFor(next, cfg);

    if (!speakerActive) {
      if (level < cfg.minRms) next.noiseFloor = next.noiseFloor * 0.94 + level * 0.06;
      next.speechMs = 0;
      return { state: next, threshold, shouldInterrupt: false };
    }

    if (level >= threshold) next.speechMs += duration;
    else next.speechMs = Math.max(0, next.speechMs - duration * 1.5);
    return {
      state: next,
      threshold,
      shouldInterrupt: next.speechMs >= cfg.sustainMs,
    };
  }

  return { DEFAULTS, createState, thresholdFor, observe };
});
