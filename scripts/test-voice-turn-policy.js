const assert = require('assert');
const policy = require('../web/src/voice-turn-policy.js');

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
assert.strictEqual(policy.DEFAULTS.preRollFrames, 6, 'barge-in must retain microphone pre-roll');

const quiet = policy.observe(policy.createState(0.01), 0.006, 42.7, false);
assert(quiet.state.noiseFloor < 0.01, 'listening silence should adapt the local noise floor');
assert.strictEqual(quiet.shouldInterrupt, false, 'listening noise calibration cannot interrupt');

// 講完後守門期（2026-07-16 Edward「前10秒斷續/怪收音」）：守門值必須蓋住 GLOWS 1.8~2s 供聲卡點
assert(policy.DEFAULTS.postSpeechGuardMs >= 1500, 'post-speech guard must cover GLOWS 1.8-2s stalls');
// 開場插話加嚴：所需持續人聲必須比平常長（回音消除未收斂期）
assert(policy.DEFAULTS.openingSustainMs > policy.DEFAULTS.sustainMs, 'opening turns must demand longer sustained speech');

function observeSeriesWith(levels, options) {
  let state = policy.createState();
  let result = null;
  for (const level of levels) {
    result = policy.observe(state, level, 42.7, true, options);
    state = result.state;
  }
  return result;
}
// 4 格（~171ms）過得了平常門檻、必須過不了開場門檻；8 格（~342ms）真人講話仍放行
assert.strictEqual(
  observeSeriesWith([0.055, 0.055, 0.055, 0.055], { sustainMs: policy.DEFAULTS.openingSustainMs }).shouldInterrupt,
  false,
  'opening sustain must reject short bursts that pass the normal gate',
);
assert.strictEqual(
  observeSeriesWith(Array(8).fill(0.055), { sustainMs: policy.DEFAULTS.openingSustainMs }).shouldInterrupt,
  true,
  'real sustained speech must still pass during the opening gate',
);

console.log('Voice turn policy PASS: echo rejection, sustained barge-in, pre-roll, post-speech guard, opening sustain');
