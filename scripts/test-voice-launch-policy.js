const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web', 'src', 'app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'web', 'index.html'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'web', 'src', 'styles.css'), 'utf8');
const voiceServer = fs.readFileSync(path.join(root, 'engine', 'live_voice_server.py'), 'utf8');
const avatarServer = fs.readFileSync(path.join(root, 'deploy', 'runpod-avatar', 'flashhead_server.py'), 'utf8');
const chatEngine = fs.readFileSync(path.join(root, 'engine', 'chat_engine.py'), 'utf8');
// 2026-07-31：人設書改成一國一本後，語音風格規矩從 live_voice_server.py 搬進
// engine/persona/voice-style.<國>.txt。守門要跟著看新地方——不然程式改對了、
// 清單沒跟上，閘門紅著沒人發現（同一個病第六次）。四本都要有，缺一本＝那一國沒紀律。
const personaDir = path.join(root, 'engine', 'persona');
const VOICE_STYLE_LOCALES = ['zh-TW', 'ja', 'en', 'es'];
const voiceStyleBooks = Object.fromEntries(VOICE_STYLE_LOCALES.map((loc) => [
  loc, fs.readFileSync(path.join(personaDir, `voice-style.${loc}.txt`), 'utf8'),
]));
// 各國書用自己的語言寫段落標題（日文是［リアルタイム音声・話す量の上限］），
// 所以按語言查標題、不是查中文字串。少一段＝那一國沒有這條紀律。
const VOICE_STYLE_HEADINGS = {
  volumeCap: {
    'zh-TW': '[即時語音話量上限]', ja: '[リアルタイム音声・話す量の上限]',
    en: '[Live speech · how much to say]', es: '[Voz en directo · cuánto hablar]',
  },
  energy: {
    'zh-TW': '[即時語音能量]', ja: '[リアルタイム音声・声の温度]',
    en: '[Live speech · energy]', es: '[Voz en directo · energía]',
  },
};
const everyVoiceStyleBookHas = (section) =>
  VOICE_STYLE_LOCALES.every((loc) => voiceStyleBooks[loc].includes(VOICE_STYLE_HEADINGS[section][loc]));
const apiServer = fs.readFileSync(path.join(root, 'engine', 'server.py'), 'utf8');
const characters = JSON.parse(fs.readFileSync(path.join(root, 'engine', 'characters.json'), 'utf8'));

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(app.includes('const base = (this._playbackTurn || 0) <= 1 ? 0.48 : 0.22'),
  'first-turn playback buffer is not larger than steady-state buffering');
expect(app.includes('Math.min(0.72, base + Math.min(3, this._playbackUnderruns || 0) * 0.08)'),
  'playback buffer does not adapt after an underrun');
expect(app.includes('Math.max(200, Math.min(350,') && app.includes('Number(Avatar._lastPrebufferMs)'),
  'same-line playback accounting is not bounded to the measured 200-350ms Avatar prebuffer');
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
expect(app.includes("type: 'barge_in_start', ...payload") &&
  app.includes("type: 'barge_in', ...payload"),
  'local barge-in does not send the two-phase evidence and commit messages');
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
const speechActiveStart = app.indexOf('function speechActive() {');
const speechActiveEnd = app.indexOf('\n}', speechActiveStart) + 2;
const speechActiveContract = app.slice(speechActiveStart, speechActiveEnd);
expect(speechActiveStart >= 0 &&
  speechActiveContract.includes('LiveVoice._playoutUntil') &&
  !speechActiveContract.includes('_faceAudLevel'),
  'raw Avatar idle audio can still keep speechActive true and suppress microphone uplink');
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
expect(
  voiceServer.includes('language_codes=localization.asr_language_hints(') &&
  voiceServer.includes('locale_profile["sessionLocale"]') &&
  voiceServer.includes('language_code=locale_profile["speechLanguageCode"]') &&
  voiceServer.includes('output_audio_transcription=transcription_config') &&
  voiceServer.includes('input_audio_transcription=transcription_config'),
  'S2S input/output transcription and speech are not driven by the verified call locale profile'
);
expect(voiceServer.includes('adaptation_phrases=phrases'),
  'ASR does not receive call-specific product, person, and topic vocabulary');
expect(voiceServer.includes('START_OF_ACTIVITY_INTERRUPTS'),
  'server activity is not explicitly configured to interrupt playback');
expect(voiceServer.includes('TURN_END_SILENCE_MS = 180'),
  'voice turns do not carry a final PCM tail guard');
expect(voiceServer.includes('st["client_barge_in"] = True'),
  'voice bridge does not suppress stale model audio after local barge-in');
expect(voiceServer.includes('{"type": "barge_in_ack", "accepted": True') &&
  voiceServer.includes('{"type": "barge_in_ack", "accepted": False'),
  'local barge-in does not receive an explicit accepted/rejected acknowledgement');
expect(voiceServer.includes('barge_cancelled and source == "model_output"'),
  'a cancelled model turn can replay language-correction audio after barge-in');
expect(voiceServer.includes('localization.contains_unstable_mandarin_speech'),
  'user-verified Mandarin mispronunciations do not trigger safe TTS rewriting');
expect(
  voiceServer.includes('opening = localization.voice_opening_instruction(') &&
  voiceServer.includes('opening = active_profile["openingMessage"]'),
  'proactive greetings do not use the rotating localized opening policy'
);
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
expect(everyVoiceStyleBookHas('volumeCap'),
  'a persona book is missing the response-length section');
expect(voiceStyleBooks['zh-TW'].includes('短是預設，不是硬上限') &&
  voiceStyleBooks['zh-TW'].includes('健康說明先講結論') &&
  voiceStyleBooks['zh-TW'].includes('二十到四十秒'),
  'live voice does not adapt response length to the task');
expect(everyVoiceStyleBookHas('energy'),
  'a persona book is missing the delivery-energy section');
expect(voiceStyleBooks['zh-TW'].includes('預設比對方穩一點'),
  'live voice opening can still default to a high-energy delivery');
expect(avatarServer.includes('self.slot.audio_out.playout_held()'),
  'Avatar video can start consuming frames before the audio prebuffer releases');
expect(avatarServer.includes('MUNEA_FH_OPENING_PREBUFFER_S", "0.35"') &&
       avatarServer.includes('OPENING_PREBUFFER_S = max(') &&
       avatarServer.includes('slot.audio_out.arm_prebuffer(OPENING_PREBUFFER_S)'),
  'the first Avatar turn does not get the configurable post-PCM warmup buffer');
expect(avatarServer.includes('MUNEA_FH_AUDIO_PREBUFFER_MIN_S') &&
       avatarServer.includes('MUNEA_FH_AUDIO_PREBUFFER_MAX_S') &&
       avatarServer.includes('min(0.35') &&
       avatarServer.includes('adaptive_min_s=AUDIO_PREBUFFER_MIN_S') &&
       avatarServer.includes('adaptive_max_s=AUDIO_PREBUFFER_MAX_S'),
  'steady Avatar turns do not use the bounded adaptive prebuffer');
expect(voiceServer.includes('"node.asr_input"'),
  'ASR/VAD tuning cannot be audited without storing raw transcripts');
// 2026-07-29 更新：原版寫死「live_config 不准出現內建 Google 搜尋」——那是 7/17
// 「查詢一律走我們代查」時代的規定。Edward 7/28 驗測後拍板改走「她自己查」（native，
// 掛 Gemini 內建搜尋；實測第一聲 5.1 秒→1.3 秒、過場句三嘴變一嘴，PR #274）。
// 這條政策的「精神」不變、只換形狀：查詢能力必須有開關控管（native_search_enabled /
// live_lookup_enabled 兩道門、demo 間一律不給），不准無條件常開。
const liveConfigStart = voiceServer.indexOf('def live_config(');
const liveConfigEnd = voiceServer.indexOf('async def search_current_information(', liveConfigStart + 1);
const liveConfig = voiceServer.slice(liveConfigStart, liveConfigEnd);
// 2026-07-29：查詢改走 Gemini 內建搜尋（#274 刻意的——舊的橋接查詢會讓她說「我幫你查一下」
// 再空白 9 秒＝客服腔）。原本「不准出現內建搜尋」那條斷言已與現行設計相反、屬過期測試。
// 換成守真正該守的兩件事：①橋接查詢那條路仍完整保留（一個環境變數就能退回去）
// ②**開了搜尋就必須同時擋住「拿網路內容回答健康問題」**——搜尋結果沒人審過，
// 內容農場跟醫學會指引長得一樣，而健康建議講錯長輩會照著做（7/24 拍板：健康走策展題庫）。
expect(liveConfigStart >= 0 && liveConfigEnd > liveConfigStart &&
  liveConfig.includes('tools = []') &&
  liveConfig.includes('if native_search_enabled() and not demo_mode:') &&
  liveConfig.includes('tools.append(types.Tool(google_search=types.GoogleSearch()))') &&
  liveConfig.includes('elif live_lookup_enabled():') &&
  liveConfig.includes('tools.append(_LIVE_LOOKUP_TOOL)') &&
  liveConfig.includes('tools=tools') &&
  voiceServer.includes('name=live_lookup.TOOL_NAME') &&
  voiceServer.includes('if function_name == live_lookup.TOOL_NAME') &&
  voiceServer.includes('response = await _run_live_lookup(fargs, cue_already_spoken=turn_out > 0)'),
  'the controlled bridge-lookup path is no longer intact as a fallback');
// 聯集（7/29 合併）：我方＝預設關的結構檢查；主線＝健康問題不准拿搜尋結果回答的護欄。
expect(voiceServer.includes('def voice_search_mode()') &&
  voiceServer.includes('return SEARCH_MODE_NATIVE if os.environ.get("MUNEA_VOICE_LIVE_LOOKUP", "0").strip() == "1" else SEARCH_MODE_OFF'),
  'voice search no longer defaults to off when no env flag is set');
expect(voiceServer.includes('if native_search_enabled() and not demo_mode:') &&
  voiceServer.includes('絕對不准用查到的網路內容回答') &&
  voiceServer.includes('寧可說不知道，也不要拿網路上的東西當健康建議'),
  'native search is enabled without the rule that health questions must never be answered from search results');
const lookupFlow = voiceServer.slice(voiceServer.indexOf('async def _run_live_lookup'));
// 2026-07-30：過場句與查詢材料都跟當輪 responseLocale 走；呼叫點仍必須在真的打網路
// 查詢之前，而且網路查詢仍包在總 timeout 裡。用穩定的行為標記，不綁單行排版。
const lookupCueCall = 'await _send_lookup_cue(category, response_locale)';
const lookupNetworkCall = 'search_current_information(';
expect(lookupFlow.indexOf(lookupCueCall) >= 0 &&
  lookupFlow.indexOf(lookupCueCall) < lookupFlow.indexOf(lookupNetworkCall) &&
  lookupFlow.includes('cli, query, lookup_location, locale=response_locale,') &&
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
  app.includes("if (phase === 'no_audio_both_ways')") &&
  app.includes("'dead_line_kept_open'") &&
  app.includes("'dead_line_reconnect'"),
  'the ready-timeout reconnect or the zero-uplink keep-open recovery is missing');
const zeroUplinkGuard = app.slice(
  app.indexOf("if (phase === 'no_audio_both_ways')"),
  app.indexOf("const sessionKey", app.indexOf("if (phase === 'no_audio_both_ways')")),
);
expect(zeroUplinkGuard.includes('return;') && !zeroUplinkGuard.includes('this.ws.close()'),
  'a ready Voice socket can still be hard-closed solely because microphone packets are late');

// ── 臉部影像流看門（2026-07-16 Edward 真機：嘴巴卡頓後畫面凍住不再動、ICE 未 failed 就沒人管）──
expect(app.includes('Avatar._armFaceWatch();') && app.includes("'face_stream_stalled'"),
  'a frozen face stream (frames stop while ICE stays connected) has no watchdog');
expect(app.includes('只在「有聲音輸出但無新幀」時累計'),
  'the face watchdog can misfire during idle periods where engine idle-feed frames are legitimately sparse');
expect(app.includes('(this._faceRebuilds || 0) >= 2'),
  'face stream rebuilds are not capped at two attempts before degrading');
expect(app.includes("'face_fallback_voice_only'") && app.includes('LiveVoice._sameLineFellBack = true;'),
  'voice-only degradation is missing or leaves same-line audio dead when the face is torn down');
const voiceOnlyStart = app.indexOf('_fallbackVoiceOnly(reason) {');
const voiceOnlyEnd = app.indexOf('\n  stop() {', voiceOnlyStart);
const voiceOnlyFallback = app.slice(voiceOnlyStart, voiceOnlyEnd);
expect(voiceOnlyStart >= 0 && voiceOnlyEnd > voiceOnlyStart &&
  !voiceOnlyFallback.includes('try { this.stop();') &&
  voiceOnlyFallback.includes("voiceCallMark('avatar_transport_preserved'") &&
  app.includes("if (CallControl.active) { this._fallbackVoiceOnly('stall_preserve_paired_lease'); return; }"),
  'audio-only degradation can still close the paired Avatar transport and stale the whole call lease');
expect(app.includes('let _hangupOnLeaveT = null;') &&
  app.includes("if (document.visibilityState !== 'hidden') return;") &&
  app.includes("else { _cancelHangupOnLeave(); try { LiveVoice._resumeAudio();"),
  'a transient iOS WebView visibility change can still hang up an active call immediately');

console.log('Voice launch policy PASS: buffering, language gate, tail guard, varied opening, and barge-in');
