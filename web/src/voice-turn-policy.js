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
    preRollFrames: 6,
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
