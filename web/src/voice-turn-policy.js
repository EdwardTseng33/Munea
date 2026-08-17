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
    // Duck first, then require fresh post-duck evidence. Three 48 kHz Web
    // Audio callbacks are about 42.7ms; 128ms captures three frames while
    // keeping the stricter 172 + 128ms opening path within 300ms.
    // 兩格（約 85ms）在 iPhone 上仍可能只是喇叭 duck 尚未走完的殘響；正式事故
    // 2026-08-10 就是在 post_duck_frames=2、RMS=0.051 時被誤接受。至少等三格
    // 新鮮音訊（約 128ms），正常 150+128ms、開場 172+128ms 仍守在 300ms 內。
    duckConfirmMs: 128,
    duckEvidenceMs: 120,
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
    // 開場仍比平常嚴，但 172 + 128ms duck-confirm 不超過 300ms。
    openingSustainMs: 172,
    // The call shell can be visible before the Voice provider is ready. Keep a
    // short, local-only opening pre-roll so a natural first "hello" is not
    // replaced by standby silence during that handshake window.
    openingCaptureMinRms: 0.018,
    openingCaptureNoiseMultiplier: 3,
    openingCaptureSustainMs: 80,
    openingCaptureCandidateMs: 32,
    openingCapturePreRollFrames: 8,
    openingCaptureMaxMs: 2200,
    // Once a real opening utterance is followed by the same quiet window used
    // by Voice AAD, freeze that utterance locally. Do not queue the caller's
    // wait silence and replay the wait a second time after Voice becomes ready.
    openingCaptureCompleteQuietMs: 650,
    openingCaptureTailMs: 160,
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

  function createOpeningCapture(noiseFloor) {
    return {
      noiseFloor: Number.isFinite(noiseFloor) ? Math.max(0, noiseFloor) : 0.006,
      candidateMs: 0,
      detected: false,
      preRoll: [],
      frames: [],
      bufferedMs: 0,
      lastVoiceFrameIndex: -1,
      trailingQuietMs: 0,
      complete: false,
    };
  }

  function openingCaptureThreshold(state, options) {
    const cfg = { ...DEFAULTS, ...(options || {}) };
    const floor = Math.max(0, Number(state && state.noiseFloor) || 0);
    return Math.min(cfg.maxRms, Math.max(
      cfg.openingCaptureMinRms,
      floor * cfg.openingCaptureNoiseMultiplier,
    ));
  }

  function captureOpeningFrame(state, frame, rms, frameMs, options) {
    const cfg = { ...DEFAULTS, ...(options || {}) };
    const next = {
      ...createOpeningCapture(),
      ...(state || {}),
      preRoll: Array.isArray(state && state.preRoll) ? state.preRoll.slice() : [],
      frames: Array.isArray(state && state.frames) ? state.frames.slice() : [],
    };
    const level = Math.max(0, Number(rms) || 0);
    const durationMs = Math.max(0, Number(frameMs) || 0);
    const threshold = openingCaptureThreshold(next, cfg);
    const entry = { frame, durationMs, rms: level };
    let detectedNow = false;

    if (!next.detected) {
      next.preRoll.push(entry);
      while (next.preRoll.length > cfg.openingCapturePreRollFrames) next.preRoll.shift();
      if (level < cfg.openingCaptureMinRms) {
        next.noiseFloor = next.noiseFloor * 0.94 + level * 0.06;
      }
      if (level >= threshold) next.candidateMs += durationMs;
      else next.candidateMs = Math.max(0, next.candidateMs - durationMs * 1.5);
      if (next.candidateMs >= cfg.openingCaptureSustainMs) {
        next.detected = true;
        detectedNow = true;
        next.frames = next.preRoll.slice();
        next.preRoll = [];
        next.bufferedMs = next.frames.reduce((sum, item) => sum + item.durationMs, 0);
        next.lastVoiceFrameIndex = next.frames.length - 1;
        next.trailingQuietMs = 0;
      }
    } else if (!next.complete) {
      next.frames.push(entry);
      next.bufferedMs += durationMs;
      const continuationThreshold = Math.max(0.008, threshold * 0.45);
      if (level >= continuationThreshold) {
        next.lastVoiceFrameIndex = next.frames.length - 1;
        next.trailingQuietMs = 0;
      } else {
        next.trailingQuietMs += durationMs;
        if (next.trailingQuietMs >= cfg.openingCaptureCompleteQuietMs) next.complete = true;
      }
    }

    while (next.detected && next.frames.length > 1 && next.bufferedMs > cfg.openingCaptureMaxMs) {
      const removed = next.frames.shift();
      next.bufferedMs = Math.max(0, next.bufferedMs - (removed.durationMs || 0));
      next.lastVoiceFrameIndex = Math.max(-1, next.lastVoiceFrameIndex - 1);
    }
    return { state: next, threshold, detectedNow };
  }

  function drainOpeningCapture(state, options) {
    const cfg = { ...DEFAULTS, ...(options || {}) };
    const current = { ...createOpeningCapture(), ...(state || {}) };
    const candidate = !current.detected && current.candidateMs >= cfg.openingCaptureCandidateMs;
    let entries = current.detected
      ? (Array.isArray(current.frames) ? current.frames : [])
      : (candidate && Array.isArray(current.preRoll) ? current.preRoll : []);
    let retainedTailMs = 0;
    if (current.detected && current.lastVoiceFrameIndex >= 0 && entries.length) {
      let end = Math.min(entries.length, current.lastVoiceFrameIndex + 1);
      while (end < entries.length && retainedTailMs < cfg.openingCaptureTailMs) {
        retainedTailMs += Number(entries[end].durationMs) || 0;
        end += 1;
      }
      entries = entries.slice(0, end);
    }
    return {
      frames: entries.map(entry => entry.frame).filter(frame => frame !== null && frame !== undefined),
      bufferedMs: Math.round(entries.reduce((sum, entry) => sum + (Number(entry.durationMs) || 0), 0)),
      detected: !!current.detected,
      candidate,
      complete: !!current.complete,
      observedQuietMs: Math.round(Number(current.trailingQuietMs) || 0),
      retainedTailMs: Math.round(retainedTailMs),
      state: createOpeningCapture(current.noiseFloor),
    };
  }

  return {
    DEFAULTS, createState, thresholdFor, observe, localStopLatencyMs,
    createOpeningCapture, openingCaptureThreshold, captureOpeningFrame, drainOpeningCapture,
  };
});
