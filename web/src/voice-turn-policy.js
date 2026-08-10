(function exposeVoiceTurnPolicy(root, factory) {
  const policy = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = policy;
  if (root) root.MuneaVoiceTurnPolicy = policy;
})(typeof window !== 'undefined' ? window : globalThis, function buildVoiceTurnPolicy() {
  const DEFAULTS = Object.freeze({
    minRms: 0.028,
    maxRms: 0.07,
    noiseMultiplier: 4,
    // 2026-08-08 Edward 真機（1.0.55／1.0.56）：「整句話頻繁出現斷字、卡住一個字跳針」。
    // 因果：判定成「他插話」→ 立刻把她嘴邊的話整包丟掉 → 要重新囤半秒才出得了聲，
    // 那半秒就是斷字。實測那通清了 29 次、輪次才 21 次＝一輪內誤判好幾次。
    // 病根是她自己的聲音從喇叭繞回麥克風（回音殘留），被當成使用者在講話。
    // 門檻太鬆。但這裡加嚴有天花板：既有合約要求「持續 4 格（≈171ms）的
    // 近場人聲必須讓路」（scripts/test-voice-turn-policy.js），那是「真人插話要跟得上」
    // 的產品底線，不能為了擋回音把它犧牲掉——我第一版設 220 就被那條守門擋下來。
    // 取 150ms，再加 110ms duck-confirm；總停聲目標仍在 300ms 內。
    sustainMs: 150,
    // Duck first, then require fresh post-duck evidence.  Three 48 kHz Web
    // Audio callbacks are about 42.7ms, so 110ms usually captures 2-3 frames
    // while keeping the stricter 190 + 110ms opening path within 300ms.
    duckConfirmMs: 110,
    duckEvidenceMs: 80,
    // 預捲必須「蓋得住」對應的持續人聲門檻，開頭的字才補得回來（2026-07-16 Edward「回長話第一句沒反應」）：
    // 一格 ≈ 42.7ms（2048 樣本 @48kHz）。平常取 12 格 ≈ 512ms 留餘裕；
    // 開場取 18 格 ≈ 768ms，含起音爬升與中途小停頓的餘裕。
    preRollFrames: 12,
    openingPreRollFrames: 18,
    // 講完後守門期（2026-07-16）：她停口後這段時間內，收音仍走「持續人聲才放行」，
    // 蓋住 GLOWS 偶發 1.8~2s 供聲卡點的句中空檔——回音/噪音不再裸流上去被當成插話。
    postSpeechGuardMs: 1800,
    // 開場前兩輪 iPhone 回音消除尚未收斂、回音殘留最強：插話所需持續人聲拉長一級。
    //
    // 開場仍比平常嚴，但 190 + 100ms duck-confirm 不超過 300ms。
    openingSustainMs: 190,
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

  function localStopLatencyMs(detectedSpeechMs, stopOperationMs) {
    const detection = Math.max(0, Number(detectedSpeechMs) || 0);
    const stop = Math.max(0, Number(stopOperationMs) || 0);
    return Math.round(detection + stop);
  }

  return { DEFAULTS, createState, thresholdFor, observe, localStopLatencyMs };
});
