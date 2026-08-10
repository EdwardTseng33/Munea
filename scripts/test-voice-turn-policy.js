const assert = require('assert');
const fs = require('fs');
const path = require('path');
const policy = require('../web/src/voice-turn-policy.js');
const app = fs.readFileSync(path.join(__dirname, '..', 'web', 'src', 'app.js'), 'utf8');

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

assert.strictEqual(
  observeSeriesWith([0.055, 0.055], { sustainMs: policy.DEFAULTS.duckEvidenceMs }).shouldInterrupt,
  true,
  'two fresh post-duck voice callbacks must confirm a real interruption',
);
assert.strictEqual(
  observeSeriesWith([0.055, 0.006, 0.006], { sustainMs: policy.DEFAULTS.duckEvidenceMs }).shouldInterrupt,
  false,
  'speaker residue that collapses after ducking must not confirm an interruption',
);

// 跨層順序契約：本地先停聲；伺服器進入證據緩衝；預捲送完；最後才提交裁決。
// 這守的是 WebSocket 實際送出順序，不只是 client/server 各自單測通過。
const beginStart = app.indexOf('_beginBargeIn(rms, threshold, sustainMs, preRoll, detectedSpeechMs, postDuckFrames = 0)');
const beginEnd = app.indexOf('\n  greet()', beginStart);
const beginBarge = app.slice(beginStart, beginEnd);
const stopAt = beginBarge.indexOf('this._stopAssistantPlayback()');
const evidenceStartAt = beginBarge.indexOf("type: 'barge_in_start'");
const preRollAt = beginBarge.indexOf('evidence.forEach(frame => this._sendMicBuffer(frame))');
const commitAt = beginBarge.indexOf("type: 'barge_in', ...payload");
assert(stopAt >= 0 && stopAt < evidenceStartAt && evidenceStartAt < preRollAt && preRollAt < commitAt,
  'barge-in must stop playback, buffer evidence, send pre-roll, then commit in that order');
assert(beginBarge.includes('sustain_ms:') && beginBarge.includes('threshold:'),
  'barge-in evidence must carry the browser threshold and sustain contract to the server');
assert(beginBarge.includes('post_duck_frames:') && beginBarge.includes('post_duck_sustain_ms:'),
  'barge-in evidence must identify the fresh post-duck decision slice');
assert(beginBarge.includes('local_stop_ms:') && beginBarge.includes("voiceCallMark('barge_in_local_stop'"),
  'barge-in must record onset-to-local-stop latency in the privacy-safe call trace');
assert(beginBarge.includes("timing_basis: 'audio_callback_estimate'")
  && app.includes('this._bargeSpeechOnsetAt = observedAt - frameMs'),
  'local stop timing must use a monotonic audio-callback onset estimate and label its basis');
assert(app.includes('this._duckPostRoll.push(buf)')
  && app.includes('self._duckPreRoll.concat(self._duckPostRoll)')
  && app.includes('self._duckConfirmPassed')
  && app.includes('self._duckPostRoll.length > 0')
  && app.includes('self._duckConfirmState.speechMs > 0'),
  'duck confirmation must judge fresh post-duck frames instead of the old echo pre-roll');
assert(app.includes('_ensureLocalPlaybackGain()')
  && app.includes('s.connect(this._ensureLocalPlaybackGain()'),
  'voice-only fallback must pass through the same duckable playback gain');

console.log('Voice turn policy PASS: echo rejection, sustained barge-in, <=300ms local stop target, two-phase evidence ordering, pre-roll, post-speech guard, opening sustain');
