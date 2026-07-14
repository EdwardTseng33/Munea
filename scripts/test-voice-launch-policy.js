const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web', 'src', 'app.js'), 'utf8');
const voiceServer = fs.readFileSync(path.join(root, 'engine', 'live_voice_server.py'), 'utf8');

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
expect(voiceServer.includes('localization.requires_taiwanese_hokkien_fallback(obj["text"])'),
  'explicit Hokkien text requests are not blocked before reaching the conversational model');
expect(voiceServer.includes('await _arm_language_block("audio_input")'),
  'recognized Hokkien audio is not blocked at the server boundary');
expect(voiceServer.includes('if data and not st.get("language_block")'),
  'Hokkien model audio can still reach the client after the language gate triggers');
expect(voiceServer.includes('server.tts_b64(localization.TAIWANESE_HOKKIEN_FALLBACK'),
  'the deterministic Mandarin fallback does not bypass conversational generation');
expect(voiceServer.includes('asyncio.to_thread(_hokkien_fallback_pcm, char)'),
  'the deterministic Mandarin fallback is not prewarmed off the call-ready path');

console.log('Voice launch buffering and Hokkien gate policy PASS');
