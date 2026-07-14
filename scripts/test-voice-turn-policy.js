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

console.log('Voice turn policy PASS: echo rejection, sustained barge-in, and pre-roll');
