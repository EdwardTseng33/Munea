const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web', 'src', 'app.js'), 'utf8');

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(app.includes('const base = (this._playbackTurn || 0) <= 1 ? 0.48 : 0.22'),
  'first-turn playback buffer is not larger than steady-state buffering');
expect(app.includes('Math.min(0.72, base + Math.min(3, this._playbackUnderruns || 0) * 0.08)'),
  'playback buffer does not adapt after an underrun');
expect(app.includes('this._sameLineWarmup = this._sameLine'),
  'Avatar same-line audio does not start in warmup mode');
expect(app.includes("result: 'local_fallback'"),
  'unstable Avatar audio does not fail safe to local playback');
expect(app.includes("trackProductEvent('voice_playback_underrun'"),
  'playback underruns are not observable');
expect(app.includes("trackProductEvent('voice_sameline_warmup'"),
  'Avatar audio warmup outcome is not observable');

console.log('Voice launch buffering policy PASS');
