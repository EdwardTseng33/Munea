// 撥號前「聲音引擎時鐘」檢查＋分層救援的守門（2026-11-16）。
//
// 背景：2026-11-13 真機（App 1.0.71）——App 從背景回來後的下一通，聲音引擎自稱 running、
// 麥克風 live，時鐘卻停在 0，一包聲音都送不出去，18 秒後整通被收掉。
//
// 這支測試分三段：
//   A. voice-audio-clock.js 的量測與救援順序（假時鐘，不等真實時間）
//   B. 把 app.js 裡真正的救援動作抽出來，用假的聲音引擎／假的原生外掛跑一遍
//   C. 原始碼守門：撥號流程真的接上、四語文案齊全、原生外掛真的進了 Xcode 專案
//
// 這個 bug 只有 iPhone 真機能重現；這裡全過只代表邏輯照設計走，不代表真機已修好。
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');
const Clock = require('../web/src/voice-audio-clock.js');
const app = read('web/src/app.js');
const html = read('web/index.html');
const rendererCopy = read('web/src/i18n/app-renderer-copy.js');
const swift = read('ios/App/App/AudioSessionPlugin.swift');
const viewController = read('ios/App/App/MuneaViewController.swift');
const pbxproj = read('ios/App/App.xcodeproj/project.pbxproj');

const LAYER_ORDER = ['web_suspend_resume', 'web_audio_session', 'native_audio_session', 'web_rebuild'];

// ── A. 量測與救援順序（假時鐘）──────────────────────────────────────────
function fakeWorld() {
  const world = { wallMs: 0 };
  world.sleep = async ms => {
    world.wallMs += ms;
    (world.contexts || []).forEach(ctx => { if (ctx.ticking) ctx.currentTime += ms / 1000; });
  };
  world.now = () => world.wallMs;
  world.context = (ticking, state = 'running') => {
    const ctx = { ticking, state, currentTime: 0 };
    world.contexts = (world.contexts || []).concat(ctx);
    return ctx;
  };
  return world;
}

async function sectionA() {
  {
    const world = fakeWorld();
    const healthy = await Clock.measure(world.context(true), { sleep: world.sleep });
    assert.strictEqual(healthy.ticking, true, 'a moving clock must be reported as ticking');
    assert.strictEqual(healthy.waitedMs, Clock.DEFAULTS.pollMs,
      'a healthy call must only pay one poll, not the whole window');
  }
  {
    const world = fakeWorld();
    const frozen = await Clock.measure(world.context(false), { sleep: world.sleep });
    assert.strictEqual(frozen.ticking, false, 'state=running with a frozen clock must NOT count as ticking');
    assert.strictEqual(frozen.state, 'running');
    assert.strictEqual(frozen.waitedMs, Clock.DEFAULTS.windowMs, 'a frozen clock is watched for the full window');
    assert(Clock.DEFAULTS.windowMs <= 300, 'the pre-dial check must decide within 300ms');
  }
  {
    const missing = await Clock.measure(null, { sleep: async () => {} });
    assert.strictEqual(missing.ticking, false);
    assert.strictEqual(missing.state, 'none');
  }

  // 跑一次 ensure：指定「哪一層做完之後時鐘開始走」
  async function run({ unstickAt = '', state = 'running', unavailable = [], throwAt = '', cancelAfter = '', claimOnly = '' } = {}) {
    const world = fakeWorld();
    const ctx = world.context(false, state);
    const ran = [];
    const reports = [];
    let cancelled = false;
    const layers = LAYER_ORDER.map(name => ({
      name,
      available: () => unavailable.indexOf(name) < 0,
      run: async () => {
        ran.push(name);
        if (name === cancelAfter) cancelled = true;
        if (name === throwAt) throw new Error('boom');
        if (name === unstickAt) ctx.ticking = true;
        if (name === claimOnly) return { recovered: true };   // 自稱救好了，但時鐘其實沒走
        return null;
      },
    }));
    const result = await Clock.ensure({
      measure: () => Clock.measure(ctx, { sleep: world.sleep }),
      layers,
      report: (kind, details) => reports.push({ kind, details }),
      isCancelled: () => cancelled,
      now: world.now,
    });
    return { result, ran, reports, kinds: reports.map(item => item.kind) };
  }

  {
    const world = fakeWorld();
    const ctx = world.context(true);
    const reports = [];
    let layerRuns = 0;
    const result = await Clock.ensure({
      measure: () => Clock.measure(ctx, { sleep: world.sleep }),
      layers: LAYER_ORDER.map(name => ({ name, run: async () => { layerRuns += 1; } })),
      report: kind => reports.push(kind),
      now: world.now,
    });
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.outcome, 'healthy');
    assert.strictEqual(layerRuns, 0, 'a healthy clock must not trigger any rescue layer');
    assert.deepStrictEqual(reports, [], 'a healthy call must not emit rescue diagnostics');
  }

  // 每一層都可能是救回來的那一層；救回來就停，後面更重的不再做
  for (let index = 0; index < LAYER_ORDER.length; index++) {
    const name = LAYER_ORDER[index];
    const { result, ran, kinds, reports } = await run({ unstickAt: name });
    assert.strictEqual(result.ok, true, `${name}: recovered call must be allowed to dial`);
    assert.strictEqual(result.outcome, 'recovered');
    assert.strictEqual(result.recoveredBy, name, `${name}: the layer that fixed it must be named`);
    assert.deepStrictEqual(ran, LAYER_ORDER.slice(0, index + 1), `${name}: layers must run light-to-heavy and stop once fixed`);
    assert.deepStrictEqual(kinds, ['stalled'].concat(Array(index + 1).fill('step'), 'recovered'),
      `${name}: diagnostics must be stalled → one step per layer → recovered`);
    const recovered = reports[reports.length - 1].details;
    assert.strictEqual(recovered.layer, name);
    assert(recovered.trail.endsWith(`${name}:ok`), `${name}: trail must end with the layer that worked`);
  }

  {
    // 四層都沒用、引擎仍自稱 running → 擋下這通
    const { result, ran, kinds, reports } = await run();
    assert.strictEqual(result.ok, false, 'a clock that never moves must block the dial');
    assert.strictEqual(result.outcome, 'unrecovered');
    assert.deepStrictEqual(ran, LAYER_ORDER, 'every layer must be tried before giving up');
    assert.deepStrictEqual(kinds, ['stalled', 'step', 'step', 'step', 'step', 'unrecovered']);
    const last = reports[reports.length - 1].details;
    assert.strictEqual(last.blocking, true);
    assert.strictEqual(last.trail, LAYER_ORDER.map(name => `${name}:no`).join(','));
  }

  {
    // 自稱救好但時鐘沒走，不算數（每層做完都要重新量）
    const { result, ran } = await run({ claimOnly: 'web_suspend_resume' });
    assert.strictEqual(result.ok, false, 'a layer must not be trusted without re-measuring the clock');
    assert.deepStrictEqual(ran, LAYER_ORDER);
  }

  {
    // 這台手機沒有的那一層：跳過、照樣往下
    const { result, ran, reports } = await run({ unavailable: ['web_audio_session', 'native_audio_session'], unstickAt: 'web_rebuild' });
    assert.strictEqual(result.recoveredBy, 'web_rebuild');
    assert.deepStrictEqual(ran, ['web_suspend_resume', 'web_rebuild'], 'unavailable layers must be skipped, not run');
    const skipped = reports.filter(item => item.kind === 'step' && item.details.ran === false).map(item => item.details.layer);
    assert.deepStrictEqual(skipped, ['web_audio_session', 'native_audio_session'], 'skipped layers must still be visible in diagnostics');
    assert(result.trail.includes('native_audio_session:skip'));
  }

  {
    // 某一層自己出錯不能讓整個撥號卡住
    const { result, ran, reports } = await run({ throwAt: 'web_audio_session', unstickAt: 'native_audio_session' });
    assert.strictEqual(result.recoveredBy, 'native_audio_session');
    assert.deepStrictEqual(ran, LAYER_ORDER.slice(0, 3));
    const failed = reports.find(item => item.kind === 'step' && item.details.layer === 'web_audio_session');
    assert(failed.details.note, 'a failing layer must leave a note in diagnostics');
  }

  {
    // 一般瀏覽器只是 suspended（等使用者點一下）：只試最輕那層，不拆麥克風、不擋撥號
    const { result, ran } = await run({ state: 'suspended' });
    assert.strictEqual(result.ok, true, 'a merely suspended engine must not block the dial');
    assert.strictEqual(result.outcome, 'not_running_passthrough');
    assert.deepStrictEqual(ran, ['web_suspend_resume'], 'heavy layers are only for the iPhone stuck states');
  }

  {
    // iPhone 的 interrupted：四層都試，但救不回來也不擋（既有流程會處理）
    const { result, ran } = await run({ state: 'interrupted' });
    assert.deepStrictEqual(ran, LAYER_ORDER);
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.outcome, 'not_running_passthrough');
  }

  {
    // 使用者取消撥號：立刻收工，不再往下動麥克風
    const { result, ran } = await run({ cancelAfter: 'web_suspend_resume' });
    assert.strictEqual(result.outcome, 'cancelled');
    assert.strictEqual(result.ok, true);
    assert.deepStrictEqual(ran, ['web_suspend_resume']);
  }
}

// ── B. app.js 真正的救援動作（假引擎＋假原生外掛，走真實計時）────────────────
function extractLiveVoiceAudioClockBlock() {
  const start = app.indexOf('  _audioSessionPlugin() {');
  const end = app.indexOf('  _setMicOpen(open) {');
  assert(start > 0 && end > start, 'app.js must keep the audio-clock block between _resumeAudio and _setMicOpen');
  return app.slice(start, end);
}

function makeContext(world, ticking) {
  const ctx = {
    state: 'running',
    _base: 0,
    _since: Date.now(),
    suspendCalls: 0,
    resumeCalls: 0,
    get currentTime() {
      return this._base + ((world.ticking && this.state === 'running') ? (Date.now() - this._since) / 1000 : 0);
    },
    async suspend() { this.suspendCalls += 1; this.state = 'suspended'; if (world.onSuspendResume) world.suspended = true; },
    async resume() {
      this.resumeCalls += 1; this.state = 'running'; this._since = Date.now();
      if (world.onSuspendResume && world.suspended) world.ticking = true;
    },
    async close() { this.state = 'closed'; world.closed += 1; },
  };
  world.ticking = ticking;
  return ctx;
}

async function simulate({ fix = '', nativePlugin = true, webSession = true, micPipeline = { ok: true } } = {}) {
  const world = { ticking: false, closed: 0, primed: 0, reactivated: 0, statusAsked: 0, sessionTypes: [] };
  const events = [];
  const marks = [];
  if (fix === 'web_suspend_resume') world.onSuspendResume = true;
  const plugin = {
    async status() { world.statusAsked += 1; return { capture: 'muted', captureAtResign: 'active', captureAtResume: 'muted', resumeUnmuted: true }; },
    async reactivate() {
      world.reactivated += 1;
      if (fix === 'native_audio_session') world.ticking = true;
      return { pulsed: true, failedStep: '', errorCode: 0, captureBefore: 'muted', captureAfter: 'active', unmuted: true };
    },
  };
  const audioSession = {};
  let sessionType = 'auto';
  Object.defineProperty(audioSession, 'type', {
    get() { return sessionType; },
    set(value) {
      sessionType = value; world.sessionTypes.push(value);
      if (fix === 'web_audio_session' && value === 'play-and-record') world.ticking = true;
    },
    enumerable: true,
  });
  const windowStub = {
    MuneaVoiceAudioClock: Clock,
    Capacitor: { Plugins: nativePlugin ? { AudioSession: plugin } : {} },
  };
  const navigatorStub = webSession ? { audioSession } : {};
  const CallChime = { _ctx: null, arm() { this._ctx = makeContext(world, world.ticking); } };
  const build = new Function('window', 'navigator', 'CallChime', 'voiceCallMark', 'voiceCallFail', 'trackProductEvent',
    `return ({\n${extractLiveVoiceAudioClockBlock()}\n});`);
  const voice = build(
    windowStub, navigatorStub, CallChime,
    (stage, status, details) => marks.push({ stage, status, details }),
    (stage, error, details) => marks.push({ stage, status: 'fail', error, details }),
    (name, props) => { events.push({ name, props }); return Promise.resolve(null); },
  );
  const track = { readyState: 'live', muted: false, stopped: false, stop() { this.stopped = true; } };
  Object.assign(voice, {
    ac: makeContext(world, false),
    playCtx: makeContext(world, false),
    mic: { getAudioTracks: () => [track], getTracks: () => [track] },
    proc: { disconnect() {} },
    _micSrc: { disconnect() {} },
    _primeCancelled: false,
    _primePipelinePromise: Promise.resolve(micPipeline),
    _foregroundAt: Date.now() - 90000,
    prime() {
      world.primed += 1;
      if (fix === 'web_rebuild') world.ticking = true;
      this.ac = makeContext(world, world.ticking);
      this.playCtx = makeContext(world, world.ticking);
      this._primePipelinePromise = Promise.resolve({ ok: true });
      return true;
    },
  });
  const result = await voice.ensureAudioClock();
  await new Promise(resolve => setTimeout(resolve, 20));   // 讓「附上原生狀態」那筆事件送完
  return { result, events, marks, world, voice, track, names: events.map(item => item.name) };
}

async function sectionB() {
  {
    // 四層都沒用：擋下這通，而且每一層都真的做過
    const { result, names, marks, world } = await simulate();
    assert.strictEqual(result.ok, false, 'a clock no layer can move must block the dial');
    assert.strictEqual(world.primed, 1, 'the last web layer must rebuild the microphone and engines once');
    assert.strictEqual(world.reactivated, 1, 'the native layer must be asked exactly once');
    assert.deepStrictEqual(world.sessionTypes, ['auto', 'play-and-record'], 'the web audio session must be re-declared as play-and-record');
    assert.deepStrictEqual(names.filter(name => name !== 'voice_audio_clock_step'),
      ['voice_audio_clock_stalled', 'voice_audio_clock_unrecovered']);
    assert.strictEqual(names.filter(name => name === 'voice_audio_clock_step').length, 4, 'one step event per layer');
    const failMark = marks.find(mark => mark.stage === 'audio_clock_preflight');
    assert(failMark && failMark.status === 'fail' && failMark.error === 'audio_clock_stuck',
      'an unrecovered clock must be recorded as a failed call stage');
  }

  {
    // 正常通話：不動任何東西、不多送事件，只在通話診斷留一筆 pass
    const sim = await simulateHealthy();
    assert.strictEqual(sim.result.ok, true);
    assert.strictEqual(sim.result.outcome, 'healthy');
    assert.deepStrictEqual(sim.names, [], 'a healthy call must not send extra product events');
    assert.strictEqual(sim.world.reactivated, 0);
    assert.strictEqual(sim.world.primed, 0);
    assert.strictEqual(sim.track.stopped, false, 'a healthy microphone must not be torn down');
    assert(sim.marks.some(mark => mark.stage === 'audio_clock_preflight' && mark.status === 'pass'));
  }

  for (const layer of LAYER_ORDER) {
    const { result, events, names, world, marks } = await simulate({ fix: layer });
    assert.strictEqual(result.ok, true, `${layer}: a rescued call must be allowed to dial`);
    assert.strictEqual(result.recoveredBy, layer, `${layer}: must be credited as the layer that worked`);
    assert.strictEqual(names[names.length - 1], 'voice_audio_clock_recovered');
    const recovered = events[events.length - 1].props;
    assert.strictEqual(recovered.layer, layer);
    const index = LAYER_ORDER.indexOf(layer);
    assert.strictEqual(world.reactivated, index >= 2 ? 1 : 0, `${layer}: native layer must only run when lighter layers failed`);
    assert.strictEqual(world.primed, index >= 3 ? 1 : 0, `${layer}: full rebuild must only run as the last web layer`);
    assert(marks.some(mark => mark.stage === 'audio_clock_preflight' && mark.status === 'pass' && mark.details.recoveredBy === layer));
  }

  {
    // 「卡住」那筆事件要帶得出後台判讀需要的狀態，而且只有狀態
    const { events } = await simulate({ fix: 'native_audio_session' });
    const stalled = events.find(item => item.name === 'voice_audio_clock_stalled').props;
    ['audioState', 'playState', 'trackState', 'trackMuted', 'sinceForegroundMs', 'nativeLayer', 'webSessionType',
      'capture', 'captureAtResign', 'captureAtResume'].forEach(key =>
      assert(key in stalled, `stalled diagnostics must include ${key}`));
    assert.strictEqual(stalled.audioState, 'running');
    assert.strictEqual(stalled.ticking, false);
    assert(stalled.sinceForegroundMs >= 90000);
    const nativeStep = events.find(item => item.name === 'voice_audio_clock_step' && item.props.layer === 'native_audio_session').props;
    assert.strictEqual(nativeStep.pulsed, true);
    assert.strictEqual(nativeStep.captureBefore, 'muted');
    assert.strictEqual(nativeStep.captureAfter, 'active');
    const everything = JSON.stringify(events);
    assert(!/transcript|"text"|"reply"|pcm|samples/i.test(everything), 'diagnostics must never carry audio or conversation content');
  }

  {
    // 沒有原生外掛（Android／瀏覽器）、也沒有網頁聲音工作階段：那兩層跳過
    const { result, world, events } = await simulate({ fix: 'web_rebuild', nativePlugin: false, webSession: false });
    assert.strictEqual(result.recoveredBy, 'web_rebuild');
    assert.strictEqual(world.reactivated, 0);
    const skipped = events.filter(item => item.name === 'voice_audio_clock_step' && item.props.ran === false).map(item => item.props.layer);
    assert.deepStrictEqual(skipped, ['web_audio_session', 'native_audio_session']);
  }

  {
    // 麥克風沒要到：這道檢查不介入（原本的麥克風失敗流程處理）
    const { result, names, world } = await simulate({ micPipeline: { ok: false, error: 'NotAllowedError' } });
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.outcome, 'skipped');
    assert.deepStrictEqual(names, []);
    assert.strictEqual(world.primed, 0);
  }

  {
    // 使用者已取消：重建那層不可以再把麥克風打開
    const { voice, world } = await simulate({ fix: 'native_audio_session' });
    voice._primeCancelled = true;
    const before = world.primed;
    const rebuilt = await voice._audioClockRebuild();
    assert.strictEqual(rebuilt.primed, false);
    assert.strictEqual(world.primed, before, 'a cancelled call must not reopen the microphone');
  }
}

async function simulateHealthy() {
  // 跟 simulate 一樣，但引擎一開始就在走
  const world = { ticking: true, closed: 0, primed: 0, reactivated: 0 };
  const events = [];
  const marks = [];
  const plugin = { async status() { return {}; }, async reactivate() { world.reactivated += 1; return {}; } };
  const CallChime = { _ctx: null, arm() {} };
  const build = new Function('window', 'navigator', 'CallChime', 'voiceCallMark', 'voiceCallFail', 'trackProductEvent',
    `return ({\n${extractLiveVoiceAudioClockBlock()}\n});`);
  const voice = build(
    { MuneaVoiceAudioClock: Clock, Capacitor: { Plugins: { AudioSession: plugin } } }, {}, CallChime,
    (stage, status, details) => marks.push({ stage, status, details }),
    (stage, error, details) => marks.push({ stage, status: 'fail', error, details }),
    (name, props) => { events.push({ name, props }); return Promise.resolve(null); },
  );
  const track = { readyState: 'live', muted: false, stopped: false, stop() { this.stopped = true; } };
  Object.assign(voice, {
    ac: makeContext(world, true), playCtx: makeContext(world, true),
    mic: { getAudioTracks: () => [track], getTracks: () => [track] },
    _primeCancelled: false, _primePipelinePromise: Promise.resolve({ ok: true }),
    prime() { world.primed += 1; return true; },
  });
  const result = await voice.ensureAudioClock();
  return { result, events, marks, world, track, names: events.map(item => item.name) };
}

// ── C. 原始碼守門 ────────────────────────────────────────────────────────
function sectionC() {
  // 救援順序：由輕到重
  const layersStart = app.indexOf('  _audioClockLayers() {');
  const layersBlock = app.slice(layersStart, app.indexOf('  async ensureAudioClock() {'));
  const positions = LAYER_ORDER.map(name => layersBlock.indexOf(`name: '${name}'`));
  assert(positions.every(position => position > 0), 'all four rescue layers must be declared in app.js');
  assert.deepStrictEqual(positions.slice().sort((a, b) => a - b), positions, 'rescue layers must be ordered light-to-heavy');

  // 撥號流程：先量時鐘，再向總機叫號；救不回來就不叫號
  const connectStart = app.indexOf('async function connectCall() {');
  const connectEnd = app.indexOf('let _connectedOnce = false;', connectStart);
  const connect = app.slice(connectStart, connectEnd);
  const primeAt = connect.indexOf('LiveVoice.prime()');
  const startAt = connect.indexOf('LiveVoice.ensureAudioClock()');
  const gateAt = connect.lastIndexOf('(await _audioClockReady).ok === false');
  const acquireAt = connect.indexOf('CallControl.acquire(');
  assert(primeAt > 0 && startAt > primeAt, 'the clock check must start right after the microphone is primed in the tap gesture');
  assert(gateAt > startAt && acquireAt > gateAt,
    'the clock verdict must be awaited BEFORE CallControl.acquire — a stuck engine must never take a seat or burn 18 seconds');
  assert.strictEqual(connect.split('(await _audioClockReady).ok === false) { abortCallForStuckAudio(); return; }').length - 1, 2,
    'both the gateway path and the developer-direct path must stop when the clock cannot be rescued');
  assert(connect.includes(".catch(() => ({ ok: true, outcome: 'check_failed' }))"),
    'a bug in the check itself must fail open, never block a call that would have worked');

  const abortStart = app.indexOf('function abortCallForStuckAudio() {');
  const abort = app.slice(abortStart, connectStart);
  assert(abortStart > 0 && abort.includes("showCallStatusCard('audioRestart')"),
    'the last resort must show the plain-language restart card');
  assert(abort.includes('LiveVoice.stop()') && abort.includes("voiceCallEnd('failed', 'audio_clock_stuck')"),
    'the blocked call must release the microphone and close its diagnostic trace');
  assert(!abort.includes('CallControl.acquire'), 'the blocked call must not contact the call gateway');

  // 診斷事件名稱
  ['voice_audio_clock_stalled', 'voice_audio_clock_step', 'voice_audio_clock_recovered', 'voice_audio_clock_unrecovered']
    .forEach(name => assert(app.includes(`'${name}'`), `diagnostic event ${name} must be reported`));
  assert(app.includes('LiveVoice._foregroundAt = Date.now()'), 'returning to the foreground must be timestamped for diagnostics');

  // 網頁載入順序與快取版號
  const clockTag = html.indexOf('src/voice-audio-clock.js?v=');
  const appTag = html.indexOf('src/app.js?v=');
  assert(clockTag > 0 && appTag > clockTag, 'voice-audio-clock.js must load before app.js');

  // 四語文案：最後手段的卡要白話、不嚇人、不講工程詞
  assert(rendererCopy.includes("audioRestart: Object.freeze({")
    && rendererCopy.includes("title: 'voice.call.audioRestartTitle'")
    && rendererCopy.includes("note: 'voice.call.audioRestartNote'"),
  'the restart card must be wired through the four-locale renderer copy');
  const catalogs = {};
  ['zh-TW', 'en', 'ja', 'es'].forEach(locale => {
    catalogs[locale] = JSON.parse(read(`web/src/i18n/${locale}.json`));
    ['voice.call.audioRestartTitle', 'voice.call.audioRestartNote'].forEach(key =>
      assert(String(catalogs[locale][key] || '').trim().length > 4, `${locale} is missing ${key}`));
  });
  const zhCard = catalogs['zh-TW']['voice.call.audioRestartTitle'] + catalogs['zh-TW']['voice.call.audioRestartNote'];
  assert(/關掉/.test(zhCard) && /打開/.test(zhCard), 'the zh-TW card must tell the user to close and reopen the App');
  ['錯誤', '異常', '故障', '失敗', '崩潰', '引擎', '工作階段', '系統', 'AudioContext', '！'].forEach(word =>
    assert(!zhCard.includes(word), `the zh-TW restart card must stay plain and calm (found "${word}")`));
  assert(/Munea/.test(catalogs.en['voice.call.audioRestartNote'])
    && /Munea/.test(catalogs.ja['voice.call.audioRestartNote'])
    && /Munea/.test(catalogs.es['voice.call.audioRestartNote']), 'en/ja/es cards must name the App the user has to reopen');

  // 這張卡要真的顯示得出來：index.html 的標題與按鈕帶著排隊卡預設字的標記，四語自動套字
  // 會把任何狀態卡的標題、按鈕改回「現在忙線中／取消排隊」（2026-11-16 瀏覽器實測）。
  // 兩個出卡函式都要先把標記拿掉，卡片上的字才是這張卡自己的字。
  assert(/id="busyCardTitle" data-i18n="voice\.queue\.fullTitle"/.test(html) && /id="busyCardBtn"[^>]*data-i18n="voice\.queue\.cancel"/.test(html),
    'guard assumption changed: the busy card default copy markers moved — re-check releaseBusyCardDefaultCopy');
  const releaseFnAt = app.indexOf('function releaseBusyCardDefaultCopy(');
  assert(releaseFnAt > 0 && app.slice(releaseFnAt, releaseFnAt + 260).includes("el.removeAttribute('data-i18n')"),
    'status cards must drop the default-copy marker before writing their own title and button');
  const busyCardFn = app.slice(app.indexOf('function showBusyCard(mode, payload) {'), app.indexOf('function formatQueueEta('));
  const statusCardFn = app.slice(app.indexOf('function showCallStatusCard(stateOrOptions) {'), app.indexOf('function setBtnBusy('));
  [['showBusyCard', busyCardFn], ['showCallStatusCard', statusCardFn]].forEach(([name, body]) => {
    const release = body.indexOf('releaseBusyCardDefaultCopy(title, btn);');
    const firstWrite = body.indexOf('title.textContent');
    assert(release > 0 && firstWrite > release,
      `${name} must release the default-copy markers before writing, or every card reads 現在忙線中／取消排隊`);
  });

  // 原生外掛：真的進了 App、真的進了 Xcode 專案
  assert(swift.includes('@objc(AudioSessionPlugin)') && swift.includes('public let jsName = "AudioSession"'),
    'the native plugin must be exposed to the web layer as Capacitor.Plugins.AudioSession');
  ['"reactivate"', '"status"'].forEach(method =>
    assert(swift.includes(`CAPPluginMethod(name: ${method}`), `native plugin must expose ${method}`));
  assert(viewController.includes('bridge?.registerPluginInstance(AudioSessionPlugin())'),
    'the native plugin must be registered on the bridge');
  assert.strictEqual(pbxproj.split('AudioSessionPlugin.swift').length - 1, 6,
    'AudioSessionPlugin.swift must be in the Xcode project exactly like the other plugins (file ref, build file, group, sources)');
  assert(/AudioSessionPlugin\.swift in Sources \*\/,/.test(pbxproj), 'AudioSessionPlugin.swift must be compiled into the App target');

  // 原生救援的關鍵順序：設定收放音 → 啟用 → 一定要放手並通知其他人
  const reactivateAt = swift.indexOf('@objc func reactivate(');
  const reactivate = swift.slice(reactivateAt);
  // 只看正常路徑（do 區塊）：出錯時的補救放手另外檢查，兩者不能互相頂替
  const happyPath = reactivate.slice(reactivate.indexOf('do {'), reactivate.indexOf('} catch {'));
  const categoryAt = happyPath.indexOf('setCategory(.playAndRecord');
  const activateAt = happyPath.indexOf('setActive(true)');
  const releaseAt = happyPath.indexOf('setActive(false, options: .notifyOthersOnDeactivation)');
  assert(categoryAt > 0 && activateAt > categoryAt && releaseAt > activateAt,
    'reactivate() must set play-and-record, activate, then release with notifyOthersOnDeactivation');
  assert(reactivate.includes('try? session.setActive(false, options: .notifyOthersOnDeactivation)'),
    'a failed reactivate() must still release the host audio session — a held host session would silence the web microphone');
  // 回到前景只做不打斷聲音的事：不可以在這裡啟用外殼的聲音工作階段
  const becomeActive = swift.slice(swift.indexOf('@objc private func appDidBecomeActive()'), swift.indexOf('@objc func status('));
  assert(becomeActive.includes('setMicrophoneCaptureState(.active'), 'returning to the foreground must un-mute a web microphone the system left muted');
  assert(!becomeActive.includes('setActive('),
    'returning to the foreground must not pulse the host audio session (it would interrupt a live call or the user\'s music)');
  assert(!/print\(|NSLog\(|os_log/.test(swift), 'the native plugin must not log anything');
}

(async () => {
  await sectionA();
  await sectionB();
  sectionC();
  console.log('PASS voice audio clock: pre-dial clock check, layered rescue order, diagnostics, four-locale restart card, native plugin wiring');
})().catch(error => {
  console.error('FAIL', error && error.stack || error);
  process.exit(1);
});
