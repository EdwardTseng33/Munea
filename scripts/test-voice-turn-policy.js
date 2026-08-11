const assert = require('assert');
const fs = require('fs');
const path = require('path');
const policy = require('../web/src/voice-turn-policy.js');
const app = fs.readFileSync(path.join(__dirname, '..', 'web', 'src', 'app.js'), 'utf8');
const voiceServer = fs.readFileSync(path.join(__dirname, '..', 'engine', 'live_voice_server.py'), 'utf8');

function observeSeries(levels, speakerActive = true) {
  let state = policy.createState();
  let result = null;
  for (const level of levels) {
    result = policy.observe(state, level, 42.7, speakerActive);
    state = result.state;
  }
  return result;
}

assert.strictEqual(
  observeSeries(Array(50).fill(0.018)).shouldInterrupt,
  false,
  'speaker echo residue must not trigger barge-in',
);
assert.strictEqual(
  observeSeries([0.08, 0.012, 0.012, 0.012]).shouldInterrupt,
  false,
  'one loud tap must not trigger barge-in',
);
assert.strictEqual(
  observeSeries([0.055, 0.055, 0.055, 0.055]).shouldInterrupt,
  true,
  'sustained near-field speech must trigger barge-in',
);
// 預捲必須蓋得住門檻（2026-07-16 Edward「回長話第一句沒反應」）：一格 ≈ 42.7ms，
// 判定成功那刻，門檻那段時間內的聲音都要還在暫存裡，開頭的字才補得回來。
const FRAME_MS = 42.7;
assert(policy.DEFAULTS.preRollFrames * FRAME_MS >= policy.DEFAULTS.sustainMs + 100,
  'pre-roll must cover the normal sustain window plus onset margin');
assert(policy.DEFAULTS.openingPreRollFrames * FRAME_MS >= policy.DEFAULTS.openingSustainMs + 200,
  'opening pre-roll must cover the stricter opening sustain window plus onset margin');
assert(policy.DEFAULTS.openingPreRollFrames > policy.DEFAULTS.preRollFrames,
  'opening turns must retain more pre-roll than normal turns');

function captureOpening(levels, options) {
  let state = policy.createOpeningCapture();
  let last = null;
  levels.forEach((level, index) => {
    last = policy.captureOpeningFrame(state, `frame-${index}`, level, FRAME_MS, options);
    state = last.state;
  });
  return { state, last, drained: policy.drainOpeningCapture(state, options) };
}

const openingSilence = captureOpening(Array(12).fill(0.004));
assert.strictEqual(openingSilence.drained.frames.length, 0,
  'opening local buffer must not turn room noise into a model turn');
const openingHello = captureOpening([0.004, 0.004, 0.045, 0.052]);
assert.strictEqual(openingHello.state.detected, true,
  'two sustained near-field frames must preserve a short first hello');
assert(openingHello.drained.frames.length >= 4 && openingHello.drained.bufferedMs >= FRAME_MS * 4 - 1,
  'opening flush must include the onset pre-roll instead of clipping the first word');
const openingAtReady = captureOpening([0.004, 0.04]);
assert.strictEqual(openingAtReady.drained.candidate, true,
  'a voice onset racing with ready must be flushed instead of losing its first frame');
const boundedOpening = captureOpening(Array(100).fill(0.05));
assert(boundedOpening.drained.bufferedMs <= policy.DEFAULTS.openingCaptureMaxMs + FRAME_MS,
  'opening capture must stay local and bounded');

const quiet = policy.observe(policy.createState(0.01), 0.006, 42.7, false);
assert(quiet.state.noiseFloor < 0.01, 'listening silence should adapt the local noise floor');
assert.strictEqual(quiet.shouldInterrupt, false, 'listening noise calibration cannot interrupt');

// 講完後守門期（2026-07-16 Edward「前10秒斷續/怪收音」）：守門值必須蓋住 GLOWS 1.8~2s 供聲卡點
assert(policy.DEFAULTS.postSpeechGuardMs >= 1500, 'post-speech guard must cover GLOWS 1.8-2s stalls');
// 開場插話加嚴：所需持續人聲必須比平常長（回音消除未收斂期）
assert(policy.DEFAULTS.openingSustainMs > policy.DEFAULTS.sustainMs, 'opening turns must demand longer sustained speech');
assert(policy.DEFAULTS.sustainMs + policy.DEFAULTS.duckConfirmMs <= 300,
  'normal barge-in detection plus duck confirmation must stay within 300ms');
assert(policy.DEFAULTS.openingSustainMs + policy.DEFAULTS.duckConfirmMs <= 300,
  'opening barge-in detection plus duck confirmation must stay within 300ms');
assert(policy.DEFAULTS.duckEvidenceMs <= policy.DEFAULTS.duckConfirmMs,
  'post-duck evidence must fit inside the confirmation window');

function observeSeriesWith(levels, options) {
  let state = policy.createState();
  let result = null;
  for (const level of levels) {
    result = policy.observe(state, level, 42.7, true, options);
    state = result.state;
  }
  return result;
}
// 4 格（~171ms）過得了平常門檻、必須過不了開場門檻；6 格（~256ms）
// 真人講話放行，並把實際 callback 邊界壓在 300ms 目標內。
assert.strictEqual(
  observeSeriesWith([0.055, 0.055, 0.055, 0.055], { sustainMs: policy.DEFAULTS.openingSustainMs }).shouldInterrupt,
  false,
  'opening sustain must reject short bursts that pass the normal gate',
);
assert.strictEqual(
  observeSeriesWith(Array(6).fill(0.055), { sustainMs: policy.DEFAULTS.openingSustainMs }).shouldInterrupt,
  true,
  'real sustained speech must still pass during the opening gate',
);
const openingDetection = observeSeriesWith(
  Array(6).fill(0.055),
  { sustainMs: policy.DEFAULTS.openingSustainMs },
);
assert(openingDetection.state.speechMs <= 300,
  'opening speech onset to interrupt callback must remain within the 300ms target');
assert.strictEqual(policy.localStopLatencyMs(openingDetection.state.speechMs, 3.4), 260,
  'local stop metric must combine detected speech evidence and synchronous stop work');

// 跨層順序契約：App 只送候選證據，Voice 裁決通過後才准停聲。
const beginStart = app.indexOf('_beginBargeIn(rms, threshold, sustainMs, preRoll, detectedSpeechMs, postDuckFrames = 0)');
const beginEnd = app.indexOf('\n  greet()', beginStart);
const beginBarge = app.slice(beginStart, beginEnd);
const evidenceStartAt = beginBarge.indexOf("type: 'barge_in_start'");
const preRollAt = beginBarge.indexOf('evidence.forEach(frame => this._sendMicBuffer(frame))');
const commitAt = beginBarge.indexOf("type: 'barge_in', ...payload");
assert(!beginBarge.includes('this._stopAssistantPlayback()')
  && evidenceStartAt >= 0 && evidenceStartAt < preRollAt && preRollAt < commitAt,
  'App must send evidence without making a destructive local speaker verdict');
assert(beginBarge.includes('sustain_ms:') && beginBarge.includes('candidate_threshold:'),
  'candidate sensitivity may be logged but must be labelled non-authoritative');
assert(beginBarge.includes('post_duck_frames:') && beginBarge.includes('post_duck_sustain_ms:'),
  'barge-in evidence must identify the fresh post-duck decision slice');
assert(beginBarge.includes("voiceCallMark('barge_in_candidate_sent'")
  && beginBarge.includes("timing_basis: 'audio_callback_estimate'")
  && app.includes('this._bargeSpeechOnsetAt = observedAt - frameMs'),
  'candidate timing must use a monotonic audio-callback onset estimate and label its basis');
assert(app.includes('this._duckPostRoll.push(buf)')
  && app.includes('self._duckPreRoll.concat(self._duckPostRoll)')
  && !app.includes('policy.confirmsPostDuck')
  && !app.includes('this._duckConfirmPassed'),
  'App must collect fresh post-duck evidence without a second amplitude verdict');
const ackStart = app.indexOf("if (o.type === 'barge_in_ack')");
const ackEnd = app.indexOf("if (o.type === 'voice_turn_timing'", ackStart);
const ackHandler = app.slice(ackStart, ackEnd);
assert(ackHandler.includes('const accepted = o.accepted !== false')
  && ackHandler.indexOf('if (accepted)') < ackHandler.indexOf('this._stopAssistantPlayback()'),
  'playback may stop only after the Voice arbiter accepts the evidence');
assert(voiceServer.includes('decide_speaker_evidence(')
  && !voiceServer.includes('normalized_rms_to_pcm16(obj.get("threshold"))'),
  'Voice must own the only final speaker verdict and ignore browser thresholds');
assert(app.includes('_ensureLocalPlaybackGain()')
  && app.includes('s.connect(this._ensureLocalPlaybackGain()'),
  'voice-only fallback must pass through the same duckable playback gain');
assert(app.includes("voiceCallMark('opening_user_voice_detected'")
  && app.includes("voiceCallMark('opening_user_voice_flushed'")
  && app.includes("voiceCallMark('opening_user_voice_acknowledged'")
  && app.indexOf('this._setMicOpen(true); this._openMicAfterGreet = false;')
    < app.indexOf('openingCapture.frames.forEach(frame => this._sendMicBuffer(frame))'),
  'opening speech must be acknowledged, measured, and flushed only after Voice ready opens the mic');
assert(voiceServer.includes('"node.first_non_silent_mic"'),
  'Voice logs cannot distinguish standby silence from the first real microphone audio');

console.log('Voice turn policy PASS: one Voice speaker verdict, opening capture/ack, non-destructive App candidate, pre-roll, post-speech guard');
