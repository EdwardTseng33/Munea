// 通話中離開畫面被 App 收線：誠實記錄＋回來有說明（2026-11-16）。
//
// 背景：畫面離開滿 5 秒，App 會自己把通話收掉。原本的做法是「替使用者按一次通話鍵」，
// 結束原因被記成 user_ended，跟使用者自己掛的分不出來；回到畫面也沒有任何說明，
// 使用者的感受是「講幾分鐘自己斷訊」。
//
// 這支測試：
//   A. 把 app.js 裡真正的收線流程抽出來，用假時鐘跑（離開 5 秒／離開 3 秒就回來／撥號中／沒在通話）
//   B. 「通話中螢幕不睡」回到前景會強制重設
//   C. 原始碼守門：三個紀錄點用同一個原因、不走評分、四語文案、後端對原因不設白名單
//
// 螢幕自動鎖、切到別的 App 只有真機能驗；這裡全過只代表邏輯照設計走。
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.join(__dirname, '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');
const app = read('web/src/app.js');
const rendererCopy = read('web/src/i18n/app-renderer-copy.js');

function extract(startMarker, endMarker) {
  const start = app.indexOf(startMarker);
  assert(start >= 0, `app.js is missing: ${startMarker}`);
  const end = app.indexOf(endMarker, start + startMarker.length);
  assert(end > start, `app.js is missing the end of: ${startMarker}`);
  return app.slice(start, end);
}

const completeSource = extract('function completeChatSession(reason = \'ended\') {', '\nfunction showView(id) {');
const leaveSource = extract('let _hangupOnLeaveT = null;', '  // 忙線／失敗卡按鈕');

// ── A. 真正的收線流程 ────────────────────────────────────────────────────
function world({ connected = true, dialing = false, preflight = false, serverControl = true } = {}) {
  let nextTimerId = 1;
  const timers = new Map();
  const documentListeners = {};
  const windowListeners = {};
  const log = {
    events: [], callEnds: [], controlReleases: [], cards: [], toggleClicks: 0, reviewAsks: 0,
    liveVoiceStops: 0, resumes: 0, storageWrites: [],
  };
  const context = {
    console,
    Date,
    Math,
    Set,
    Boolean,
    document: {
      visibilityState: 'visible',
      addEventListener(name, callback) { documentListeners[name] = callback; },
      getElementById() { return { dataset: {} }; },
    },
    localStorage: {
      getItem() { return null; },
      setItem(key, value) { log.storageWrites.push([key, value]); },
    },
    setTimeout(callback, delay) { const id = nextTimerId++; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    callConnected: connected,
    callDialing: dialing,
    callPreflightPending: preflight,
    chatOpened: true,
    activeChatSessionId: 'voice-session-1',
    activeChatStartedAt: Date.now() - 82000,
    activeChatTurnCount: 4,
    _callSec: 82,
    POINTS: { total: 0, used: 0 },
    CallControl: {
      url() { return serverControl ? 'https://call-control.invalid' : ''; },
      release(reason) {
        log.controlReleases.push(reason);
        // 總機回什麼，App 就記什麼：已經講的時間由總機算，跟結束原因無關
        return Promise.resolve({ billed_credits: 2, billable_seconds: 82 });
      },
    },
    LiveVoice: {
      stop() { log.liveVoiceStops += 1; },
      saveMemory() {},
      _resumeAudio() { log.resumes += 1; },
    },
    FaceWave: { stop() {} },
    FaceIdle: { start() {} },
    voiceCallEnd(outcome, reason, details) { log.callEnds.push({ outcome, reason, details }); },
    trackProductEvent(name, props) { log.events.push({ name, props }); return Promise.resolve(null); },
    refreshServerCredits() {},
    pushWallet() {}, renderPoints() {}, updateMedCount() {}, toast() {}, muneaT() { return ''; },
    stopCallTimer() {}, setFaceState() {},
    showCallStatusCard(state) { log.cards.push(state); },
    $(selector) {
      if (selector !== '#callToggle') return null;
      return { click() { log.toggleClicks += 1; } };
    },
  };
  context.window = {
    addEventListener(name, callback) { windowListeners[name] = callback; },
    __muneaMaybeAskReview() { log.reviewAsks += 1; },
    __muneaStopListen() {},
  };
  context.setCallToggle = value => {
    context.callConnected = value; context.callDialing = false; context.callPreflightPending = false;
  };
  vm.createContext(context);
  vm.runInContext(completeSource, context);
  vm.runInContext(leaveSource, context);
  const setVisibility = state => { context.document.visibilityState = state; documentListeners.visibilitychange(); };
  const fireTimers = () => { const pending = [...timers.entries()]; pending.forEach(([id, timer]) => { timers.delete(id); timer.callback(); }); };
  return { context, log, timers, setVisibility, fireTimers, windowListeners };
}

async function sectionA() {
  {
    // 已接通的通話，離開畫面滿 5 秒
    const w = world({ connected: true });
    w.setVisibility('hidden');
    assert.strictEqual(w.timers.size, 1, 'leaving the screen must arm exactly one release timer');
    assert.strictEqual([...w.timers.values()][0].delay, 5000, 'the grace period before releasing must stay 5 seconds');
    assert.strictEqual(w.log.liveVoiceStops, 0, 'the call must not be released the moment the screen is left');
    w.fireTimers();
    await new Promise(resolve => setImmediate(resolve));

    assert.strictEqual(w.log.liveVoiceStops, 1, 'a call hidden for 5 seconds must be released once');
    assert.strictEqual(w.log.toggleClicks, 0, 'the App must not fake a tap on the call button — that is what recorded user_ended');
    assert.strictEqual(w.context.callConnected, false);
    assert.strictEqual(w.context.chatOpened, false);

    // 三個紀錄點用同一個原因
    assert.deepStrictEqual(w.log.callEnds.map(item => [item.outcome, item.reason]), [['completed', 'background_release']],
      'the call diagnostic must record background_release, still as a completed (not failed) call');
    assert.deepStrictEqual(w.log.controlReleases, ['background_release'], 'the call gateway must be told background_release');
    const completed = w.log.events.find(item => item.name === 'voice_session_completed');
    assert(completed && completed.props.reason === 'background_release', 'voice_session_completed must record background_release');
    const released = w.log.events.find(item => item.name === 'call_control_released');
    assert(released && released.props.reason === 'background_release', 'call_control_released must record background_release');
    assert.strictEqual(released.props.billedCredits, 2, 'billing figures must be reported exactly as the gateway returned them');
    assert.strictEqual(released.props.billableSeconds, 82);
    assert(!w.log.events.some(item => item.props && item.props.reason === 'user_ended'),
      'nothing about a background release may be recorded as user_ended');
    assert(w.log.events.some(item => item.name === 'voice_background_release'), 'the background release event must still be sent');

    // 不算「好好聊完」
    assert.strictEqual(w.log.reviewAsks, 0, 'a background release must never trigger the rating prompt');
    assert(!w.log.storageWrites.some(([key]) => key === 'munea.stat.chatsCompleted'),
      'a background release must not count as a completed chat');

    // 回到畫面才說明，而且只說一次
    assert.deepStrictEqual(w.log.cards, [], 'the notice must wait until the user is back on screen');
    w.setVisibility('visible');
    assert.deepStrictEqual(w.log.cards, ['backgroundEnded'], 'returning to the screen must explain why the call ended');
    w.setVisibility('hidden');
    w.setVisibility('visible');
    assert.deepStrictEqual(w.log.cards, ['backgroundEnded'], 'the notice must appear only once');
  }

  {
    // 離開 3 秒就回來：不掛斷、不出卡
    const w = world({ connected: true });
    w.setVisibility('hidden');
    assert.strictEqual(w.timers.size, 1);
    w.setVisibility('visible');
    assert.strictEqual(w.timers.size, 0, 'coming back before 5 seconds must cancel the pending release');
    w.fireTimers();
    assert.strictEqual(w.log.liveVoiceStops, 0, 'a short absence must not end the call');
    assert.strictEqual(w.context.callConnected, true);
    assert.deepStrictEqual(w.log.cards, [], 'no notice when the call was not ended');
    assert.deepStrictEqual(w.log.callEnds, []);
    assert.strictEqual(w.log.resumes, 1, 'coming back must resume the audio path');
  }

  {
    // 計時器響的時候人已經回來了：不掛斷
    const w = world({ connected: true });
    w.setVisibility('hidden');
    w.context.document.visibilityState = 'visible';   // 回來了，但還沒收到事件
    w.fireTimers();
    assert.strictEqual(w.log.liveVoiceStops, 0, 'the timer must re-check that the screen is still hidden');
  }

  {
    // 還在撥號就離開：一樣記 background_release，但算「取消」不算失敗
    const w = world({ connected: false, dialing: true });
    w.windowListeners.pagehide();
    w.context.document.visibilityState = 'hidden';
    w.fireTimers();
    assert.deepStrictEqual(w.log.callEnds.map(item => [item.outcome, item.reason]), [['cancelled', 'background_release']],
      'a dial abandoned by leaving the screen is cancelled, not failed, and not user_cancelled');
    assert.deepStrictEqual(w.log.controlReleases, ['background_release']);
    w.setVisibility('visible');
    assert.deepStrictEqual(w.log.cards, ['backgroundEnded']);
  }

  {
    // 還在排隊（前置中）就離開：排隊位子一樣要放掉
    const w = world({ connected: false, preflight: true });
    w.setVisibility('hidden');
    w.fireTimers();
    assert.deepStrictEqual(w.log.controlReleases, ['background_release'], 'leaving while queued must release the queue slot');
    assert.strictEqual(w.context.callPreflightPending, false);
    assert.deepStrictEqual(w.log.callEnds.map(item => item.outcome), ['cancelled']);
  }

  {
    // 沒在通話：離開畫面什麼都不做
    const w = world({ connected: false });
    w.setVisibility('hidden');
    assert.strictEqual(w.timers.size, 0, 'no call, no release timer');
    w.setVisibility('visible');
    assert.deepStrictEqual(w.log.cards, []);
  }

  {
    // 回來時已經又在撥了：不打擾，之後也不補出
    const w = world({ connected: true });
    w.setVisibility('hidden');
    w.fireTimers();
    w.context.callDialing = true;
    w.setVisibility('visible');
    assert.deepStrictEqual(w.log.cards, [], 'no notice on top of a new call');
    w.context.callDialing = false;
    w.setVisibility('hidden');
    w.setVisibility('visible');
    assert.deepStrictEqual(w.log.cards, [], 'a skipped notice must not show up later out of context');
  }

  {
    // 使用者自己按掛斷的路沒有被改到：原因仍是 user_ended
    const w = world({ connected: true });
    vm.runInContext("completeChatSession('user_ended')", w.context);
    assert.deepStrictEqual(w.log.callEnds.map(item => [item.outcome, item.reason]), [['completed', 'user_ended']]);
    w.setVisibility('hidden');
    w.setVisibility('visible');
    assert.deepStrictEqual(w.log.cards, [], 'a call the user ended must not get the left-the-screen notice');
  }
}

// ── B. 通話中螢幕不睡：回到前景強制重設 ─────────────────────────────────────
function sectionB() {
  const source = extract('const CallKeepAwake = {', 'function setCallToggle(connected) {');
  const calls = { keepAwake: 0, allowSleep: 0, webLock: 0 };
  const documentListeners = {};
  const context = {
    console: { warn() {} },
    callConnected: true, callDialing: false, callPreflightPending: false,
    document: { visibilityState: 'visible', addEventListener(name, callback) { documentListeners[name] = callback; } },
    navigator: {},
    window: { Capacitor: { Plugins: { KeepAwake: {
      keepAwake() { calls.keepAwake += 1; return Promise.resolve(); },
      allowSleep() { calls.allowSleep += 1; return Promise.resolve(); },
    } } } },
  };
  vm.createContext(context);
  vm.runInContext(`${source}\nglobalThis.KeepAwake = CallKeepAwake;`, context);
  const keep = context.KeepAwake;

  keep.sync();
  assert.strictEqual(calls.keepAwake, 1, 'entering a call must ask the phone to stay awake');
  keep.sync();
  assert.strictEqual(calls.keepAwake, 1, 'sync() is edge-triggered: it does nothing while the wanted state is unchanged');
  assert.strictEqual(keep.reassert(), true);
  assert.strictEqual(calls.keepAwake, 2, 'reassert() must re-apply keep-awake even though the wanted state is unchanged');

  documentListeners.visibilitychange();
  assert.strictEqual(calls.keepAwake, 3, 'returning to the foreground during a call must re-apply keep-awake');
  context.document.visibilityState = 'hidden';
  documentListeners.visibilitychange();
  assert.strictEqual(calls.keepAwake, 3, 'going to the background must not touch keep-awake');

  context.callConnected = false;
  context.document.visibilityState = 'visible';
  documentListeners.visibilitychange();
  assert.strictEqual(calls.keepAwake, 3, 'no call, no keep-awake on return');
  assert.strictEqual(keep.reassert(), false);
  assert.strictEqual(keep.on, false, 'reassert() must leave the remembered state matching reality');

  // 瀏覽器（沒有原生外掛）：改走螢幕喚醒鎖
  const webCalls = { lock: 0 };
  const webContext = {
    console: { warn() {} },
    callConnected: true, callDialing: false, callPreflightPending: false,
    document: { visibilityState: 'visible', addEventListener() {} },
    navigator: { wakeLock: { request() { webCalls.lock += 1; return Promise.resolve({ addEventListener() {}, release() {} }); } } },
    window: {},
  };
  vm.createContext(webContext);
  vm.runInContext(`${source}\nglobalThis.KeepAwake = CallKeepAwake;`, webContext);
  webContext.KeepAwake.reassert();
  assert.strictEqual(webCalls.lock, 1, 'without the native plugin, reassert() must request the web wake lock');
}

// ── C. 原始碼守門 ────────────────────────────────────────────────────────
function sectionC() {
  assert(!leaveSource.includes(".click()"), 'the hidden-for-5-seconds timer must not click the call button on the user\'s behalf');
  assert(leaveSource.includes('releaseCallForBackground(source)'), 'the timer must release the call through releaseCallForBackground');
  assert(leaveSource.includes('showBackgroundReleaseNotice()'), 'returning to the screen must offer the one-time notice');

  const releaseFn = extract('function releaseCallForBackground(source) {', '\n}\n');
  assert(releaseFn.includes("completeChatSession('background_release')"), 'the background release must be completed with its own reason');
  assert(!releaseFn.includes('user_ended') && !releaseFn.includes('user_cancelled'),
    'the background release must not borrow the user-initiated reasons');
  assert(!releaseFn.includes('__muneaMaybeAskReview') && !releaseFn.includes('chatsCompleted'),
    'the background release must stay out of the "good chat → please rate" path');
  assert(releaseFn.includes('LiveVoice.stop()') && releaseFn.includes('setCallToggle(false)'),
    'the background release must tear the call down the same way the call button does');

  // 評分那條路仍然只跟「使用者自己關掉聊聊」綁在一起
  const reviewCallers = app.split("window.__muneaMaybeAskReview('chat_completed')").length - 1;
  assert.strictEqual(reviewCallers, 1, 'only one place may ask for a rating after a chat');
  const chatExit = extract("if ($('#chatExit')) $('#chatExit').addEventListener('click', () => {", "\n  });");
  assert(chatExit.includes("__muneaMaybeAskReview('chat_completed')") && chatExit.includes("'user_ended'"),
    'the rating prompt must stay tied to the user closing the chat themselves');

  assert(completeSource.includes("'background_release'") && completeSource.includes("reason === 'background_release' && !callConnected"),
    'completeChatSession must classify background_release as completed (connected) or cancelled (still dialing)');

  // 四語文案：平實、不道歉連發、不用驚嘆號
  assert(rendererCopy.includes('backgroundEnded: Object.freeze({')
    && rendererCopy.includes("title: 'voice.call.backgroundEndedTitle'")
    && rendererCopy.includes("note: 'voice.call.backgroundEndedNote'"), 'the notice must go through the four-locale renderer copy');
  const catalogs = {};
  ['zh-TW', 'en', 'ja', 'es'].forEach(locale => {
    catalogs[locale] = JSON.parse(read(`web/src/i18n/${locale}.json`));
    const text = `${catalogs[locale]['voice.call.backgroundEndedTitle'] || ''} ${catalogs[locale]['voice.call.backgroundEndedNote'] || ''}`;
    assert(text.trim().length > 12, `${locale} is missing the left-the-screen notice`);
    assert(!/[!！¡]/.test(text), `${locale}: the notice must not use exclamation marks`);
    assert(!/抱歉|對不起|不好意思|sorry|apolog|申し訳|すみません|ごめん|lo siento|perd[oó]n|disculp/i.test(text),
      `${locale}: the notice must not pile on apologies`);
  });
  assert.strictEqual(
    catalogs['zh-TW']['voice.call.backgroundEndedTitle'] + '。' + catalogs['zh-TW']['voice.call.backgroundEndedNote'],
    '剛剛離開了畫面，通話先結束了。想繼續聊，再按一次通話就好。',
    'the zh-TW notice must read exactly as approved');

  // 後端對結束原因不設白名單、計費不看原因——所以新原因可以原樣送給總機。
  // 這兩個檔不是這次改的；如果哪天後端開始只認固定幾個值，這裡會紅，提醒回頭處理。
  const gateway = read('deploy/gateway/gateway_server.py');
  assert(/class CallLeaseV2Body\(BaseModel\):[\s\S]{0,160}reason: str = "completed"/.test(gateway),
    'the call gateway release body no longer takes a free-form reason — re-check background_release');
  const callControlSql = read('supabase/sql/010_realtime_call_control.sql');
  assert(callControlSql.includes("end_reason=left(coalesce(p_reason,'completed'),120)"),
    'the release function no longer stores the reason as free text — re-check background_release');
  assert(/end_reason text,/.test(callControlSql) && !/end_reason[^\n]*check\s*\(/i.test(callControlSql),
    'call_leases.end_reason gained a constraint — re-check background_release');
  assert(/v_seconds := case when v_call\.active_at is null then 0/.test(callControlSql),
    'billable time must be derived from when the call became active, not from the end reason');
}

(async () => {
  await sectionA();
  sectionB();
  sectionC();
  console.log('PASS voice background release: honest end reason in all three records, no rating prompt, one-time notice on return, keep-awake re-applied');
})().catch(error => {
  console.error('FAIL', error && error.stack || error);
  process.exit(1);
});
