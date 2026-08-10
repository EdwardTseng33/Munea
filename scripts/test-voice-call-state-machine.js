const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web', 'src', 'app.js'), 'utf8');

function extract(startMarker, endMarker) {
  const start = app.indexOf(startMarker);
  const end = app.indexOf(endMarker, start + startMarker.length);
  assert(start >= 0 && end > start, `Unable to isolate ${startMarker}`);
  return app.slice(start, end);
}

function runAvatarFallbackContract() {
  const method = extract('_fallbackVoiceOnly(reason) {', '\n  stop() {');
  let stopCalls = 0;
  let closedTransports = 0;
  const marks = [];
  const storage = new Map();
  const nodes = {
    faceAud: { muted: false },
    faceVid: { muted: false },
  };
  const background = { classList: { remove() {} } };
  const context = {
    LiveVoice: { _sameLine: true, _sameLineFellBack: false },
    FaceIdle: { startCalls: 0, start() { this.startCalls += 1; } },
    voiceCallMark(name, outcome, detail) { marks.push({ name, outcome, detail }); },
    trackProductEvent() {},
    muneaT(_key, fallback) { return fallback; },
    setLocalizedRuntimeHint() {},
    localStorage: {
      setItem(key, value) { storage.set(key, value); },
    },
    document: {
      getElementById(id) { return nodes[id] || null; },
      querySelector(selector) { return selector === '#chat .face-bg' ? background : null; },
    },
    _fhComposite() {},
    clearInterval() {},
  };
  vm.createContext(context);
  vm.runInContext(`globalThis.holder = {${method}\n  };`, context);
  const avatar = context.holder;
  avatar.pc = { close() { closedTransports += 1; } };
  avatar.ws = { close() { closedTransports += 1; } };
  avatar.session = 'paired-call-session';
  avatar.stop = () => { stopCalls += 1; };
  avatar._diagNote = () => {};
  avatar._fallbackVoiceOnly('slow_face_lead');

  assert.strictEqual(stopCalls, 0, 'Voice-only fallback invoked Avatar.stop()');
  assert.strictEqual(closedTransports, 0, 'Voice-only fallback closed a paired transport');
  assert.strictEqual(avatar.session, 'paired-call-session', 'Voice-only fallback cleared the paired session');
  assert.strictEqual(context.LiveVoice._sameLineFellBack, true, 'Local voice playback was not enabled');
  assert.strictEqual(nodes.faceAud.muted, true, 'Avatar analyser audio remained audible');
  assert.strictEqual(nodes.faceVid.muted, true, 'Avatar player audio remained audible');
  assert.strictEqual(context.FaceIdle.startCalls, 1, 'Idle artwork did not replace the degraded face');
  assert(marks.some((event) => event.name === 'avatar_transport_preserved'),
    'Fallback did not emit transport-preserved evidence');
}

function runVisibilityContract() {
  const source = extract('let _hangupOnLeaveT = null;', "  // 忙線／失敗卡按鈕");
  let nextTimerId = 1;
  const timers = new Map();
  let hangups = 0;
  let resumes = 0;
  const documentListeners = {};
  const windowListeners = {};
  const document = {
    visibilityState: 'visible',
    addEventListener(name, callback) { documentListeners[name] = callback; },
  };
  const context = {
    document,
    window: { addEventListener(name, callback) { windowListeners[name] = callback; } },
    callConnected: true,
    callDialing: false,
    callPreflightPending: false,
    LiveVoice: { _resumeAudio() { resumes += 1; } },
    trackProductEvent() {},
    $(selector) {
      if (selector !== '#callToggle') return null;
      return { click() { hangups += 1; } };
    },
    setTimeout(callback, delay) {
      const id = nextTimerId++;
      timers.set(id, { callback, delay });
      return id;
    },
    clearTimeout(id) { timers.delete(id); },
  };
  vm.createContext(context);
  vm.runInContext(source, context);

  document.visibilityState = 'hidden';
  documentListeners.visibilitychange();
  assert.strictEqual(hangups, 0, 'Transient hidden state hung up immediately');
  assert.strictEqual(timers.size, 1, 'Hidden state did not arm one bounded release timer');
  assert.strictEqual([...timers.values()][0].delay, 5000, 'Background release grace is not 5 seconds');

  document.visibilityState = 'visible';
  documentListeners.visibilitychange();
  assert.strictEqual(timers.size, 0, 'Returning visible did not cancel the pending hangup');
  assert.strictEqual(hangups, 0, 'Returning visible still caused a hangup');
  assert.strictEqual(resumes, 1, 'Returning visible did not resume the audio path');

  document.visibilityState = 'hidden';
  windowListeners.pagehide();
  assert.strictEqual(timers.size, 1, 'Sustained pagehide did not arm the release timer');
  const timer = [...timers.values()][0];
  timer.callback();
  assert.strictEqual(hangups, 1, 'Sustained background did not release the call once');
}

function runLocalPlaybackContinuityContract() {
  const method = extract('_scheduleLocalPlayback(f) {', '\n  _setFaceAudioMuted(muted) {');
  const scheduled = [];
  const context = {
    Avatar: { on: true },
    faceEngine() { return 'flashhead'; },
    localStorage: { getItem() { return null; } },
    trackProductEvent() {},
  };
  vm.createContext(context);
  vm.runInContext(`globalThis.holder = {${method}\n  };`, context);
  const voice = context.holder;
  voice.playCtx = {
    currentTime: 0,
    destination: {},
    createBuffer(_channels, length, rate) {
      return { duration: length / rate, getChannelData() { return { set() {} }; } };
    },
    createBufferSource() {
      return {
        buffer: null,
        connect() {},
        start(at) { scheduled.push({ at, duration: this.buffer.duration }); },
      };
    },
  };
  voice.playHead = 0;
  voice._playbackTurn = 1;
  voice._playbackUnderruns = 0;
  voice._turnHasScheduledAudio = false;
  voice._srcs = [];
  voice._ensureLocalPlaybackGain = () => null;
  voice._playbackLeadSeconds = () => 0.48;
  voice._toListening = () => {};

  // Production Voice evidence showed 136-147ms delivery gaps. Each modeled
  // PCM chunk carries 200ms, so the first-turn queue must absorb that jitter.
  for (let index = 0; index < 80; index += 1) {
    voice.playCtx.currentTime = index * 0.147;
    voice._scheduleLocalPlayback(new Float32Array(4800));
  }
  assert.strictEqual(voice._playbackUnderruns, 0, '147ms PCM jitter caused a local playback underrun');
  assert.strictEqual(scheduled.length, 80, 'Not every PCM chunk was scheduled');
  for (let index = 1; index < scheduled.length; index += 1) {
    const previousEnd = scheduled[index - 1].at + scheduled[index - 1].duration;
    assert(Math.abs(scheduled[index].at - previousEnd) < 1e-9,
      `PCM scheduling gap before chunk ${index}`);
  }
}

runAvatarFallbackContract();
runVisibilityContract();
runLocalPlaybackContinuityContract();
console.log('Voice call state machine PASS: paired lease preserved, transient iOS hiding tolerated, 147ms PCM jitter continuous');
