const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web', 'src', 'app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'web', 'index.html'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'web', 'src', 'styles.css'), 'utf8');
const voiceServer = fs.readFileSync(path.join(root, 'engine', 'live_voice_server.py'), 'utf8');
const avatarServer = fs.readFileSync(path.join(root, 'deploy', 'runpod-avatar', 'flashhead_server.py'), 'utf8');
const chatEngine = fs.readFileSync(path.join(root, 'engine', 'chat_engine.py'), 'utf8');
const apiServer = fs.readFileSync(path.join(root, 'engine', 'server.py'), 'utf8');
const characters = JSON.parse(fs.readFileSync(path.join(root, 'engine', 'characters.json'), 'utf8'));

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(app.includes('const base = (this._playbackTurn || 0) <= 1 ? 0.48 : 0.22'),
  'first-turn playback buffer is not larger than steady-state buffering');
expect(app.includes('Math.min(0.72, base + Math.min(3, this._playbackUnderruns || 0) * 0.08)'),
  'playback buffer does not adapt after an underrun');
expect(app.includes('const sameLineDelay = (this._playbackTurn || 0) <= 1 ? 1100 : 600'),
  'same-line playback still blocks later user turns with the opening delay');
expect(app.includes('const tailMs = sameLine ? 120 : 400'),
  'same-line speech tail does not release the microphone promptly');
expect(app.includes('function preDialConnWarm') && app.includes("preDialConnWarm('boot')") && app.includes("preDialConnWarm('resume')"),
  'pre-dial connection warmup is not wired at boot and foreground resume');
expect(app.includes('this._postGuardUntil = performance.now() + policy.DEFAULTS.postSpeechGuardMs'),
  'post-speech microphone guard window is not armed while the assistant speaks');
expect(app.includes('performance.now() < (this._postGuardUntil || 0)'),
  'mic frames stream raw during assistant mid-sentence stalls (post-speech guard missing)');
expect(app.includes('sustainMs: policy.DEFAULTS.openingSustainMs'),
  'opening turns do not tighten barge-in sustain while echo cancellation converges');
expect(apiServer.includes('不要編造') && !apiServer.includes('自然接續就好'),
  'call recap wording invites the model to fabricate last-call content');
expect(voiceServer.includes('這是一通新接起的電話'),
  'voice base prompt lacks the new-call no-fabricated-memory red line');
expect(app.includes('this._assistantAudioPendingBytes < 960') && app.includes("trackProductEvent('voice_tiny_audio_buffered'"),
  'sub-frame assistant audio can still start a false playback turn');
expect(app.includes("trackProductEvent('voice_user_speech_unrecognized'") && app.includes("trackProductEvent('voice_user_speech_recognized'"),
  'user speech recognition gaps are not observable without transcripts');
expect(app.includes('const cfg = developerConfig();') && !app.includes('devAuthConfig()'),
  'development Voice endpoint is read through an undefined config helper');
expect(app.includes('this._sameLineWarmup = this._sameLine'),
  'Avatar same-line audio does not start in warmup mode');
expect(app.includes('prepareOpeningAudioPath(waitMs = 1000)') && app.includes('new Int16Array(24000).buffer'),
  'Avatar same-line audio is not warmed independently before the greeting');
expect(app.includes("stage: 'before_greet'") && app.includes("'pending_first_audio'") && app.includes("'local_fallback'"),
  'inconclusive silent warmup does not preserve same-line verification and local fallback modes');
expect(app.includes("return { mode, verified: stable, receiverAttached }") && !app.includes("opening_audio_not_ready"),
  'an inconclusive silent warmup can still tear down an otherwise healthy call');
expect(!app.includes('_sameLineWarmupPending'),
  'the first assistant answer is still being consumed as the audio warmup');
expect(app.includes('await LiveVoice.prepareOpeningAudioPath(1000)') && app.indexOf('await LiveVoice.prepareOpeningAudioPath(1000)') < app.indexOf('LiveVoice.greet()'),
  'the greeting can start before the one-second audio warmup');
expect(app.includes('this._renderStream.addTrack(e.track)') && app.includes('vid.srcObject = this._renderStream'),
  'Avatar audio and video tracks are not combined on the single playback clock');
expect(app.includes('showLiveFrame()') && app.includes("bg.classList.add('livevid')") && app.includes('Avatar.showLiveFrame();'),
  'the live Avatar can be exposed before the first validated frame');
expect(app.includes("trackProductEvent('voice_playback_underrun'"),
  'playback underruns are not observable');
expect(app.includes("trackProductEvent('voice_sameline_warmup'"),
  'Avatar audio warmup outcome is not observable');
expect(app.includes("const meter = document.getElementById('faceAud'); if (meter) meter.muted = true") &&
  app.includes("const player = document.getElementById('faceVid'); if (player) player.muted = !!muted"),
  'same-line audio can be unmuted on two media elements and play twice');
expect(app.includes('aud.srcObject = ms; aud.muted = true'),
  'the analyser-only faceAud element can briefly emit duplicate audio');
expect(app.includes("localStorage.getItem('munea.dailyCallOpening')") && app.includes("url += '&day_call='"),
  'same-day calls do not carry a dedicated rotating opening index');
expect(app.includes("localStorage.setItem('munea.dailyCallOpening'") && app.includes('LiveVoice._openingRecorded = true'),
  'completed calls do not advance the same-day opening route');
expect(html.includes('src/voice-turn-policy.js'),
  'the tested local barge-in policy is not loaded before the App module');
expect(app.includes("this.ws.send(JSON.stringify({ type: 'barge_in' }))"),
  'local barge-in does not notify the voice bridge');
expect(app.includes('policy.DEFAULTS.preRollFrames'),
  'barge-in does not retain microphone pre-roll');
expect(app.includes('policy.DEFAULTS.openingPreRollFrames'),
  'opening turns do not retain the longer pre-roll that covers the stricter opening sustain gate (first-sentence loss)');
expect(app.includes('function _fhPreParentVid') && app.includes('_fhPreParentVid();'),
  'dialing does not pre-parent the live face player into the frame, so connecting rebuilds the video layer (first-call black flash)');
expect(app.includes('function _fhWarmArt') && app.includes('_fhWarmArt();') && app.includes('img.decode()'),
  'full-body art is not decoded before connecting (first-call dark flash while the PNG decodes)');
expect(styles.includes('.fh-frame') && !styles.includes('background: #0E1A17'),
  'the face frame still uses a near-black backdrop that reads as a black flash before art paints');
expect(!app.includes('if (speechActive()) { this.micLevel = 0; return; }'),
  'assistant playback still disables microphone uplink unconditionally');
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
// 2026-07-24：prefix_padding_ms 改走 _voice_rhythm_param 三層 fallback（呼叫端明確值→
// 環境變數→這裡的 300 預設）；不設環境變數＝跟改動前的字面 300ms 完全一樣的行為，
// 契約檢查同步改成看 fallback 呼叫是否仍以 300 為內建預設。
expect(voiceServer.includes('prefix_padding_ms=_voice_rhythm_param(') &&
  voiceServer.includes('"MUNEA_VOICE_PREFIX_PADDING_MS", 300)'),
  'server VAD does not require sustained speech before committing a turn');
expect(voiceServer.includes('types.LanguageHints(language_codes=["cmn-Hant-TW"])'),
  'S2S input/output transcription is not explicitly biased to Taiwan Mandarin');
expect(voiceServer.includes('adaptation_phrases=phrases'),
  'ASR does not receive call-specific product, person, and topic vocabulary');
expect(voiceServer.includes('START_OF_ACTIVITY_INTERRUPTS'),
  'server activity is not explicitly configured to interrupt playback');
expect(voiceServer.includes('TURN_END_SILENCE_MS = 180'),
  'voice turns do not carry a final PCM tail guard');
expect(voiceServer.includes('st["client_barge_in"] = True'),
  'voice bridge does not suppress stale model audio after local barge-in');
expect(voiceServer.includes('{"type": "barge_in_ack"}'),
  'local barge-in can leave the App dropping a newly generated response');
expect(voiceServer.includes('barge_cancelled and source in ("model_output", "mandarin_pronunciation")'),
  'a cancelled model turn can replay language-correction audio after barge-in');
expect(voiceServer.includes('localization.contains_unstable_mandarin_speech'),
  'user-verified Mandarin mispronunciations do not trigger safe TTS rewriting');
expect(voiceServer.includes('localization.voice_opening_instruction(fam, topics, location, day_call)'),
  'proactive greetings do not use the rotating opening policy');
expect(voiceServer.includes('await asyncio.wait_for(future, timeout=8)') && voiceServer.includes('"app_write_timeout"'),
  'voice tools can still report success without waiting for the App write receipt');
expect(voiceServer.includes('name="send_family_relay"') && voiceServer.includes('st["relay_greet_id"]'),
  'verified family relays are not available to the voice model opening');
expect(voiceServer.includes('verify_family_relay_proof(relay)') && voiceServer.includes('hmac.compare_digest'),
  'the voice bridge can trust unsigned or client-tampered family relay content');
expect(voiceServer.includes('{"type": "relay_spoken"'),
  'the App cannot acknowledge a relay only after the spoken opening finishes');
expect(voiceServer.includes('{"type": "relay_interrupted"') && app.includes("this._finishRelay('release')"),
  'an interrupted relay can remain claimed instead of returning to the next-call queue');
expect(voiceServer.includes('"phase": "greet_input_ready"'),
  'the microphone remains closed while the proactive greeting is being generated');
expect(voiceServer.includes('await asyncio.sleep(1.0)') && voiceServer.includes('node.proactive_greet_skipped'),
  'opening speech can overlap the proactive greeting instead of using the one-second warmup window');
expect(voiceServer.includes('"greet_requested": False') && voiceServer.includes('node.proactive_greet_ignored'),
  'duplicate greet requests can start overlapping model turns');
expect(voiceServer.includes('[即時語音話量上限]') && voiceServer.includes('一般閒聊預設只回答一句'),
  'live voice does not enforce the one-sentence default');
expect(voiceServer.includes('[即時語音能量]') && voiceServer.includes('預設比對方穩一點'),
  'live voice opening can still default to a high-energy delivery');
expect(avatarServer.includes('self.slot.audio_out.playout_held()'),
  'Avatar video can start consuming frames before the audio prebuffer releases');
expect((avatarServer.includes('OPENING_PREBUFFER_S = 1.0') ||
        avatarServer.includes('MUNEA_FH_OPENING_PREBUFFER_S", "1.0"')) &&
       avatarServer.includes('slot.audio_out.arm_prebuffer(OPENING_PREBUFFER_S)'),
  'the first Avatar turn does not get a one-second post-PCM warmup buffer');
expect(voiceServer.includes('"node.asr_input"'),
  'ASR/VAD tuning cannot be audited without storing raw transcripts');
const liveConfigStart = voiceServer.indexOf('def live_config(');
const liveConfigEnd = voiceServer.indexOf('async def search_current_information(', liveConfigStart + 1);
const liveConfig = voiceServer.slice(liveConfigStart, liveConfigEnd);
expect(liveConfigStart >= 0 && liveConfigEnd > liveConfigStart &&
  liveConfig.includes('tools = []') &&
  liveConfig.includes('if live_lookup_enabled():') &&
  liveConfig.includes('tools.append(_LIVE_LOOKUP_TOOL)') &&
  liveConfig.includes('tools=tools') &&
  !liveConfig.includes('google_search=types.GoogleSearch()') &&
  voiceServer.includes('name=live_lookup.TOOL_NAME') &&
  voiceServer.includes('if function_name == live_lookup.TOOL_NAME') &&
  voiceServer.includes('response = await _run_live_lookup(fargs, cue_already_spoken=turn_out > 0)'),
  'current-information lookup can still bypass the feature-gated controlled Voice tool path');
const lookupFlow = voiceServer.slice(voiceServer.indexOf('async def _run_live_lookup'));
// 2026-07-25 去罐頭化：_send_lookup_cue 改吃 category 參數挑貼題過場話，呼叫點仍必須在
// 真的打網路查詢之前。
expect(lookupFlow.indexOf('await _send_lookup_cue(category)') >= 0 &&
  lookupFlow.indexOf('await _send_lookup_cue(category)') < lookupFlow.indexOf('search_current_information(cli') &&
  lookupFlow.includes('asyncio.wait_for('),
  'lookup network I/O can start before the spoken cue or run without a timeout');
expect(['node.lookup_started', 'node.lookup_cue_sent', 'node.lookup_done',
  'node.lookup_failed', 'node.lookup_answer_audio'].every(event => voiceServer.includes(event)) &&
  voiceServer.includes('lookups=st["lookup_count"]'),
  'controlled lookup stages are not observable in Voice diagnostics');
expect(chatEngine.includes('localization.taiwan_mandarin_launch_instruction("zh-TW")'),
  'the shared text/opening brain can bypass the Mandarin-only persona guard');
expect(apiServer.includes('localization.assistant_output_text'),
  'text chat can display residual Hokkien model output');
expect(Object.values(characters).every(character => character.persona.includes('台灣國語')),
  'every selectable persona must explicitly use Taiwan Mandarin');

// ── 收音管先建後招呼＋上行/死線看門（2026-07-16 蟲 b/c：mic_uplink 5-6 秒、整通 in_bytes=0、死線乾等 30 秒）──
expect(app.includes('this._sendMicBuffer(this._silentUplinkFrame(inp.length))'),
  'closed-mic frames stop feeding the uplink, so the server sees in_bytes=0 until the greeting finishes');
expect(app.includes('nowMs - this._silentKeepaliveAt >= 500'),
  'gated-mic keepalive is not rate-limited to one small packet per 500ms (full-rate silence burns Gemini input tokens during opening/mute)');
expect(!app.includes('if (!this.micOpen) { this.micLevel = 0; return; }'),
  'the microphone pipeline waits for the greeting again instead of sending silent standby frames');
expect(app.includes('const micPipelineReady = this._setupMicPipeline(micPromise);') &&
  app.indexOf('const micPipelineReady = this._setupMicPipeline(micPromise);') < app.indexOf('this.ws = new WebSocket(url)'),
  'the microphone pipeline is no longer built in parallel with (before) the WebSocket handshake');
expect(app.includes('this._armUplinkWatch()') && app.includes("'microphone_uplink_slow'") && app.includes("'microphone_uplink_rebuilt'"),
  'the 3-second uplink watchdog with automatic pipeline rebuild is missing');
expect(app.includes('(this._micRebuilds || 0) >= 2'),
  'uplink pipeline rebuilds are not capped at two attempts');
expect(app.includes("this._armDeadLineWatch('ready_timeout', 10000)") &&
  app.includes("this._armDeadLineWatch('no_audio_both_ways', 5000)") &&
  app.includes("'dead_line_reconnect'"),
  'a dead line can leave the user waiting for the 30-second readiness gate instead of auto-reconnecting');

// ── 臉部影像流看門（2026-07-16 Edward 真機：嘴巴卡頓後畫面凍住不再動、ICE 未 failed 就沒人管）──
expect(app.includes('Avatar._armFaceWatch();') && app.includes("'face_stream_stalled'"),
  'a frozen face stream (frames stop while ICE stays connected) has no watchdog');
expect(app.includes('只在「有聲音輸出但無新幀」時累計'),
  'the face watchdog can misfire during idle periods where engine idle-feed frames are legitimately sparse');
expect(app.includes('(this._faceRebuilds || 0) >= 2'),
  'face stream rebuilds are not capped at two attempts before degrading');
expect(app.includes("'face_fallback_voice_only'") && app.includes('LiveVoice._sameLineFellBack = true;'),
  'voice-only degradation is missing or leaves same-line audio dead when the face is torn down');

console.log('Voice launch policy PASS: buffering, language gate, tail guard, varied opening, and barge-in');
