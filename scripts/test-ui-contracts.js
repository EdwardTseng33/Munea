const fs = require('fs');

const html = fs.readFileSync('web/index.html', 'utf8');
const app = fs.readFileSync('web/src/app.js', 'utf8');
const auth = fs.readFileSync('web/src/auth.js', 'utf8');
const css = fs.readFileSync('web/src/styles.css', 'utf8');
const versionSource = fs.readFileSync('web/src/version.js', 'utf8');
const privacy = fs.readFileSync('web/privacy.html', 'utf8');
const store = fs.readFileSync('web/src/store.js', 'utf8');
const medication = fs.readFileSync('web/src/medication.js', 'utf8');
const storePlugin = fs.readFileSync('ios/App/App/StorePlugin.swift', 'utf8');
const rendererCopySource = fs.readFileSync('web/src/i18n/app-renderer-copy.js', 'utf8');
const legalRoutingSource = fs.readFileSync('web/src/i18n/legal-routing.js', 'utf8');
const zhCatalog = JSON.parse(fs.readFileSync('web/src/i18n/zh-TW.json', 'utf8'));
const COPY_LOCALES = ['zh-TW', 'en', 'ja', 'es'];
const catalogs = Object.fromEntries(
  COPY_LOCALES.map(locale => [
    locale,
    JSON.parse(fs.readFileSync(`web/src/i18n/${locale}.json`, 'utf8')),
  ]),
);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

// ── 文案類守門的通用寫法（2026-07-30 立）──────────────────────────────────────
// 背景：畫面文字已經改成「index.html 放英文底稿、執行時由 web/src/i18n/*.json 套上該語言」。
// 在 index.html 裡 grep 中文＝守著隨時會被翻譯批次改掉的寫法，不是守使用者實際看得到什麼。
// 這個坑 2026-07 連續踩四次（7/28 renderCarePriority、7/29 sec-head 比對、7/29 通話前置並行、
// 7/30 訂閱點數揭露在乾淨 main 上長期紅燈——揭露一直都在，是守門找錯地方）。
//
// 所以文案類的意圖一律拆三層守，不再對畫面檔 grep 某一國語言的句子：
//   ① 結構：畫面上真的有那個節點（節點不在＝翻譯再對也沒人看得到）
//   ② 接線：那個節點由哪個文案 key 餵（key 是穩定的，句子不是）
//   ③ 文案：翻譯表裡那個 key 真的講到該講的事
// 唯一例外是反向守門（「這句話必須永遠消失」）——那裡寫死的是不該再出現的舊句，本來就該寫死。
//
// ③ 的四語系逐句合規用字，各自有 scripts/test-*-localizations.js 專門守（例如訂閱點數在
// test-purchase-flow-localizations.js）。這裡只驗「四語系都有、不空白」＋「zh-TW／en 兩份正本
// 真的講到重點」，避免同一份用字表要在兩個地方維護、改文案時到處誤紅。
function assertCatalogSays(key, patterns, why) {
  COPY_LOCALES.forEach((locale) => {
    const value = catalogs[locale][key];
    assert(typeof value === 'string' && value.trim(), `${locale}:${key} 文案不見了——${why}`);
  });
  Object.entries(patterns).forEach(([locale, expected]) => {
    [].concat(expected).forEach((pattern) => {
      assert(pattern.test(catalogs[locale][key]), `${locale}:${key} 必須講到 ${pattern}——${why}`);
    });
  });
}

function contrastRatio(hexA, hexB) {
  const luminance = (hex) => {
    const rgb = hex.match(/[0-9a-f]{2}/gi).map(v => parseInt(v, 16) / 255);
    const linear = rgb.map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  };
  const [lighter, darker] = [luminance(hexA), luminance(hexB)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

// 品牌定色守門（2026-07-30 Edward 拍板）：主企業色＝薄荷綠不是深綠、橘＝Logo 上的那個橘。
// 7/24 曾為了白字 AA 4.5 把主按鈕加深成 #2A7E78，被 Edward 抓「主色變深綠」退回——
// 品牌優先是拍板取捨：主按鈕薄荷綠白字 3.16:1 守 AA 大字級 3:1 底線，不得再往深綠推。
assert(contrastRatio('#37A099', '#FFFFFF') >= 3, 'Primary button mint must keep at least AA large-text contrast with white');
assert(contrastRatio('#B0392D', '#FFFFFF') >= 4.5, 'Danger action red must keep WCAG AA contrast on white');
assert(css.includes('--teal: #3AA8A0;') && css.includes('--btn-green: #37A099;') && css.includes('--coral: #F4A261;'),
  'Brand tokens must stay pinned to the 2026-07-30 ruling: mint primary, mint button, logo orange');
assert(css.includes('--danger-d: #B0392D;'), 'Accessible danger color token must stay pinned');
assert(/class="modal-btn danger" id="dataDeleteBtn"/.test(html), 'Data deletion must use the danger style instead of the primary action style');
assert(/\.modal-btn\.danger\[data-arm="1"\]\s*\{[^}]*background:\s*var\(--danger-d\);[^}]*color:\s*#fff;/s.test(css), 'Armed deletion must render as a solid danger action');
assert(/b\.dataset\.arm = '1'/.test(app), 'Data deletion must retain the two-step armed confirmation behavior');

assert(/id="verRowNum">—<\/span>/.test(html) && /id="verCurrent">—<\/span>/.test(html), 'Version UI placeholders must not contain a stale semantic version');
assert(!/id="(?:verRowNum|verCurrent)">\d+\.\d+\.\d+<\/span>/.test(html), 'Version UI must not hard-code a fallback release number');
assert(versionSource.includes('window.MuneaApplyVersionToStaticUi') && versionSource.includes("['verRowNum', 'verCurrent']"), 'The version SSOT must bind both static version labels immediately');

// 內頁真版印章（通話畫面角落）只准開發包／瀏覽器預覽顯示；正式包一律藏（2026-07-18 Edward A）。
// 這是給打包驗版用的除錯標籤，長輩看到只會困惑。若哪天有人把 gate 拿掉、變回無條件顯示，這裡亮紅燈。
const verStampBlock = app.match(/const _vs = document\.getElementById\('webVerStamp'\);[\s\S]{0,600}?\n\s*\} catch/)?.[0] || '';
assert(verStampBlock.length > 0, 'webVerStamp assignment block not found (內頁真版印章)');
assert(/isDeveloperBypassAllowed\(\)/.test(verStampBlock) && /!isPackagedApp\(\)/.test(verStampBlock),
  '內頁真版印章必須只在開發包或非打包預覽顯示——正式包不得出現除錯版本角標');
assert(/muneaT\('version\.webBuild', 'Web v\{version\}', \{ version: MuneaVersion\.current \}\)[\s\S]*?: ''/.test(verStampBlock),
  '內頁真版印章正式包必須清空（三元運算 else 分支要給空字串，不能留舊值）');

assert(app.includes('const __pullPromise = Promise.resolve(syncPullAll());'), 'Family sync bypass must still produce a safe promise for downstream initialization');
const criticalConsentSetup = app.match(/function setupCriticalConsentControls\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(criticalConsentSetup.includes("$('#consentAgree')") && criticalConsentSetup.includes("sheet.querySelector('.mx-close')"), 'Consent agree and close controls must be bound by the critical early setup');
assert(criticalConsentSetup.includes("$('#consentDetail')") && criticalConsentSetup.includes("openInAppReader('privacy', { returnToConsent: true })"), 'Consent privacy detail must open the in-App reader and return to consent');
assert(criticalConsentSetup.includes("$('#readerBack')") && criticalConsentSetup.includes('closeInAppReader'), 'The in-App privacy reader must retain a working back control');
assert(app.indexOf("document.addEventListener('DOMContentLoaded', setupCriticalConsentControls)") < app.indexOf("document.addEventListener('DOMContentLoaded', init)"), 'Critical consent controls must bind before the main App initialization');
assert(!app.includes("window.open('privacy.html', '_blank')"), 'Consent privacy detail must not leave the App in a new window');
assert(app.startsWith("import './i18n/legal-routing.js';"), 'The App must load the reviewed legal routing contract before opening an in-App legal page');
const legalReader = app.match(/async function openInAppReader\(kind, options\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(legalReader.includes('resolveInAppLegalPage(kind)') && legalReader.includes("muneaT('reader.loading'") && legalReader.includes("muneaT('reader.loadError'"),
  'The in-App legal reader must resolve the locale-aware page and localize its loading and failure states');
assert(app.includes("fetchJsonDocument('src/i18n/catalog-manifest.json')") && app.includes("fetchJsonDocument('legal/manifest.json')"),
  'The App legal reader must use the catalog and legal-review manifests as its routing authority');
assert(app.includes('legalRegion: trustedLegalRegion()') && !legalRoutingSource.includes('countryCode'),
  'Legal routing must consume only the explicit trusted legalRegion and must never infer it from country or language');
const draftGate = app.match(/function isLocalI18nDraftPreview\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(draftGate.includes('localOrigin') && draftGate.includes('config.enabled === true') && draftGate.includes('requestedLocale === muneaLocale()'),
  'Unreviewed localized legal drafts must be limited to an explicit local i18n preview');
assert(app.includes('captureTrustedLocaleContext(response)') && app.includes('response.store && response.store.account'),
  'The legal region may be captured only from the backend account-bootstrap response, not from the active UI locale');
assert(privacy.includes('目前機房位於日本東京'), 'Privacy disclosure must identify the current Tokyo data region');
assert(!privacy.includes('目前機房位於澳洲'), 'Privacy disclosure must not retain the retired Sydney production region');
const connectCall = app.match(/async function connectCall\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(connectCall.indexOf('LiveVoice.prime()') < connectCall.indexOf('setCallDialing(true)'), 'Call button must not show dialing before microphone and credit preflight');
const creditRefreshIndex = connectCall.indexOf('creditState = await refreshServerCredits()');
const zeroCreditIndex = connectCall.indexOf("throw new Error('insufficient_credits')");
const gatewayAcquireIndex = connectCall.indexOf('await CallControl.acquire(');
const productionDialingIndex = connectCall.indexOf('setCallDialing(true)', zeroCreditIndex);
assert(creditRefreshIndex >= 0 && creditRefreshIndex < zeroCreditIndex, 'Server credit balance must be checked before a zero-credit call is rejected');
assert(zeroCreditIndex >= 0 && zeroCreditIndex < gatewayAcquireIndex && gatewayAcquireIndex < productionDialingIndex, 'Production dialing must start only after credits and Gateway acceptance');
assert(connectCall.includes('setTimeout(__muneaShowCallCreditBlocked, 0)'), 'Credit rejection must open the explanatory credit or plan dialog');
assert(connectCall.includes('if (!developmentDirectCall)') && connectCall.includes('Promise.race([') && connectCall.includes('setTimeout(resolve, 1200)'), 'Family relay lookup must not block development calls or delay production dialing indefinitely');
assert(/if \(!LiveVoice\.prime\(\)\) \{\s*setCallPreflightPending\(false\)/.test(connectCall), 'Microphone failure must leave the preflight state without showing dialing');

// 點數是否足夠只在後端靜默判斷；畫面不得出現「查點數」字樣，只維持一般撥號觀感（Edward 2026-07-20拍板）。
assert(!connectCall.includes('確認可用點數中') && !connectCall.includes('正在確認帳號與可用點數'), 'Credit preflight must run silently: the button and caption must not show checking-credits copy to the caller');
assert(!/setCallPreflightPending\([^)]*點數/.test(connectCall) && !/setCallHint\([^)]*點數/.test(connectCall), 'No preflight busy label or caption may mention credits while the check is still running');
// 開發者 Gateway 模式（真登入、非直連）測試帳號不能被 0 點卡住；正式用戶（非開發者旁路）依然照擋。
assert(connectCall.includes("if (availableCredits <= 0 && !isGatewayDeveloperProfile()) throw new Error('insufficient_credits');"), 'Only the developer Gateway profile may skip the zero-credit block; production callers must still be stopped');

// 通話狀態卡（2026-07-23 排隊／全滿 → 2026-07-24 Edward 拍板 P0 擴成通用失敗卡）：排隊要顯示第幾位或準備中敘事＋
// 帶粗略等待時間；隊伍全滿要明講請稍後再試並提供「先用文字聊」出口；撥號各種失敗一律要有看得見的卡，不能只寫進被
// CSS 藏起來的 #chatCaption；排隊／前置連線中都必須能取消（按通話鍵、離開聊聊頁、切走 App 三條路都要真取消）。
assert(html.includes('id="busyCard"') && html.includes('id="busyCardBtn"'), 'Busy card markup must exist on the call screen');
assert(html.includes('id="busyCardAlt"'), 'Busy card must expose a secondary exit button element for the full-queue text-chat fallback');
assert(css.includes('.busy-card'), 'Busy card styles must exist');
assert(app.includes("showBusyCard('queued', queue)"), 'Queued gateway responses must surface the busy card with the full queue payload (position and eta_s), not just a bare position number');
assert(app.includes("showBusyCard('full')"), 'A full queue must surface the explicit busy-try-later card');
assert(zhCatalog['voice.queue.fullTitle'] === '現在忙線中' && zhCatalog['voice.queue.fullBody'].includes('請稍後再試試看'), 'Full-queue catalog copy must say busy-try-later in plain language');
assert(app.includes("muneaT('voice.queue.pending'") && app.includes("muneaT('voice.queue.wait'"), 'Queued call button and hidden fallback hint must follow the App language');
const busyCardFallbackBody = app.slice(
  app.indexOf('function showBusyCard(mode, payload)'),
  app.indexOf('function formatQueueEta'),
);
assert(busyCardFallbackBody.includes("muneaT('voice.queue.fullTitle'") && busyCardFallbackBody.includes("'voice.queue.fullBody'"), 'Busy-card fallback copy must stay localized even before renderer-copy initialization');
assert(/if \(\(callDialing \|\| callPreflightPending\) && !callConnected\)/.test(app), 'Tapping the call button must cancel while queued (preflight pending), not only while dialing');
assert(app.includes('if (callConnected || callDialing || callPreflightPending)'), 'Leaving the call screen while queued must hang up and release the queue slot');
assert(/callConnected \|\| callDialing \|\| callPreflightPending\) && \$\('#callToggle'\)/.test(app), 'Backgrounding the App while queued must cancel the queue slot');
assert(app.includes("if (reason === 'call_cancelled')"), 'A user-initiated cancel must exit quietly instead of reporting a busy failure');

// 排隊敘事＋等待時間人話化（2026-07-24 P0）：position<=1 要用「準備中」講法而不是誤導的「排第 1 位」；
// eta_s（後端一直都有算，之前被前端丟掉）要轉成粗略區間，不給會顯得說謊的精確倒數。
assert(app.includes('function formatQueueEta(') && app.includes("if (n < 90) return 'soon';") && app.includes('if (n <= 600) return Math.ceil(n / 60);'),
  'Queue ETA must be bucketed into a soon/minutes/none narrative from queue.eta_s, not shown as a raw countdown');
assert(app.includes("preparing = position <= 1") && busyCardFallbackBody.includes("'voice.queue.preparingWithCompanion'"),
  'Position 1 must use a preparing narrative instead of the misleading "you are #1 in line" framing');
assert(busyCardFallbackBody.includes("'voice.queue.note'"), 'The queue note must use the localized softened stay-on-screen phrasing instead of the old "leaving cancels the queue" warning');

// 無聲失敗全部接上看得見的卡（2026-07-24 Edward 拍板 P0）：登入失效／帳號未就緒／服務設定異常／暖機超時／
// 斷線重連失敗／連線逾時／影像席位全滿／拿不到麥克風，過去全部只寫進被藏起來的 #chatCaption，等於零回饋。
assert(app.includes('function showCallStatusCard(stateOrOptions)'), 'A generic visible localized failure card function must exist for non-queue call failures');
const statusCardKeys = ['voice.call.authExpiredTitle', 'voice.call.accountPreparingTitle', 'voice.call.serviceUpdatingTitle', 'voice.call.unavailable', 'voice.call.activationPendingTitle', 'voice.call.readinessPendingTitle', 'voice.call.disconnectedTitle', 'voice.call.microphonePermissionTitle'];
statusCardKeys.forEach(key => assert(zhCatalog[key], `Failure card catalog key missing for: ${key}`));
assert(rendererCopySource.includes("action: 'reopen-auth'") && app.includes("action === 'reopen-auth'") && app.includes('openAuthSheet()'),
  'An expired session must offer a one-tap re-login action on the visible card, not just a hidden caption');
assert(app.includes("showCallStatusCard('activationPending')"), 'The gateway activation timeout must also surface a visible localized card, matching the other silent-failure fixes');
assert(app.includes("muneaT('voice.call.dialing'") && app.includes("muneaT('voice.call.online'") && app.includes("muneaT('voice.call.offline'"), 'Call control labels and presence state must use the locale catalog');
['auth.chatSignInRequired', 'voice.caption.enabled', 'voice.caption.disabled', 'accessibility.markComplete'].forEach(key => {
  assert(zhCatalog[key], `Dynamic App catalog key missing for: ${key}`);
});
assert(/muneaT\(\s*'auth\.chatSignInRequired'/.test(app) && app.includes("muneaT('voice.caption.enabled'") && app.includes("muneaT('voice.caption.disabled'"),
  'Sign-in and caption feedback must be rendered from the active locale catalog');
assert(app.includes("muneaT('accessibility.markComplete'"), 'Task completion controls must expose a localized accessible label');
const runtimeVoiceKeys = [
  'voice.runtime.playbackBlocked',
  'voice.runtime.audioOnlyFallback',
  'voice.runtime.microphoneTapToResume',
  'voice.runtime.listening',
  'voice.runtime.reconnecting',
  'voice.runtime.microphonePermission',
  'voice.runtime.heard',
  'voice.runtime.thinking',
  'voice.runtime.didNotHear',
  'voice.runtime.recordingTapWhenDone',
  'voice.runtime.microphoneMuted',
  'voice.runtime.microphoneMutedHint',
  'voice.runtime.recoveredTitle',
  'voice.runtime.recoveredBody',
  'voice.runtime.degradedTitle',
  'voice.runtime.degradedBody',
  'voice.runtime.textFallbackPrompt',
  'voice.runtime.deviceTextFallbackPrompt',
  'voice.runtime.microphoneTextFallbackPrompt',
];
runtimeVoiceKeys.forEach(key => assert(zhCatalog[key], `Voice runtime catalog key missing for: ${key}`));
assert(app.includes('function setLocalizedRuntimeHint(state, busy = false)')
  && app.includes('function setLocalizedRuntimeCaption(state)'),
  'Voice runtime hints and recovery captions must use named localized renderers');
assert(!/setCallHint\(\s*['"`][^'"`\r\n]*\p{Script=Han}/u.test(app),
  'Call runtime hints must not bypass the locale catalog with inline Han copy');
assert(!/setCaption\(\s*['"`][^'"`\r\n]*\p{Script=Han}/u.test(app),
  'Call recovery captions must not bypass the locale catalog with inline Han copy');
assert(app.includes('function applyTaskAccessibilityLabels()') && /refreshLocalizedDynamicUi\(\)[\s\S]*?applyTaskAccessibilityLabels\(\)/.test(app),
  'Task completion accessibility labels must refresh after the active App locale changes');
assert(app.includes('function localizeAuthTerms()') && /refreshLocalizedDynamicUi\(\)[\s\S]*?localizeAuthTerms\(\)/.test(app),
  'The complete auth terms disclosure and close label must refresh with the active App locale');
[
  'medication.duration.days',
  'medication.duration.longTerm',
  'medication.action.added',
  'medicationReminder.dueSay',
  'medicationReminder.description',
  'medicationReminder.speech',
  'medicationReminder.takenToast',
  'medicationManager.scheduleMultiple',
  'medicationManager.emptySlot',
  'medicationManager.removeSlot',
  'medicationManager.addedToast',
].forEach(key => assert(zhCatalog[key], `Medication surface catalog key missing for: ${key}`));
assert(app.includes('function localizeMedicationSurfaces()')
  && /refreshLocalizedDynamicUi\(\)[\s\S]*?localizeMedicationSurfaces\(\)/.test(app),
  'Medication manager and due-reminder surfaces must refresh when the App locale changes');
assert(/async function aiAddMedReminder[\s\S]*?muneaIsCleanDisplayText\(rawName\)/.test(app)
  && !/async function aiAddMedReminder[\s\S]{0,260}?muneaIsCleanZhText\(rawName\)/.test(app),
  'Voice-created medication names must accept safe English, Japanese, and Spanish text');
assert(app.includes('function canonicalMedicationSlot(slot)')
  && app.includes("import './i18n/medication-schedule.js'")
  && app.includes("'after-breakfast': '早餐後'")
  && app.includes("'after-lunch': '午餐後'")
  && app.includes("'after-dinner': '晚餐後'")
  && app.includes('window.MuneaMedicationScheduleI18n?.normalizeSlot(label)')
  && app.includes('function canonicalMedicationDuration(duration)')
  && app.includes('window.MuneaMedicationScheduleI18n?.normalizeDuration(raw)')
  && /async function aiAddMedReminder[\s\S]*?days: canonicalMedicationDuration\(a && a\.days\)/.test(app)
  && app.includes('function localizedMedicationDuration(duration)')
  && app.includes('function medicationReminderSpeech(medication)'),
  'Medication storage identifiers, visible durations, and spoken reminders must stay locale-aware');
assert(
  /const durationMatch = String\(med\.days \|\| ''\)\.match\(\/\(\\d\+\)\/\)/.test(medication),
  'Medication scheduling must honor one-day and arbitrary finite treatments from voice actions',
);
const medicationManagerUi = app.slice(
  app.indexOf("const setReminders = $('#medEntrySettings')"),
  app.indexOf("if ($('#medEntryStatus'))"),
);
const medicationReminderUi = app.slice(
  app.indexOf('function fireMedReminder(med)'),
  app.indexOf('setInterval(checkDueMeds'),
);
assert(!/toast\(['"`](?:拿掉了|這張照片讀不到|先寫藥名|點一下什麼時候吃|記下了，藥吃了|好，10 分鐘後)/.test(
  medicationManagerUi + medicationReminderUi,
),
  'Medication manager and due-reminder feedback must not bypass the locale catalog');
assert(css.includes(':is(html:lang(en), html:lang(es)) .reader-card :is(p, li)'),
  'English and Spanish legal copy must use natural left alignment instead of stretched CJK justification');
[
  'common.today',
  'medication.takeName',
  'medication.taskProgress',
  'visit.defaultTitle',
  'visit.defaultNote',
  'event.familyTitle',
  'event.arriveOnTime',
  'home.walkProgressMet',
  'home.walkProgress',
  'home.walkGoalMet',
  'home.walkSteps',
].forEach(key => assert(zhCatalog[key], `Home task catalog key missing for: ${key}`));
assert(app.includes('function localizedMedicationSlot(slot)')
  && app.includes("muneaT('medication.taskProgress'")
  && app.includes("muneaT('visit.defaultTitle'")
  && app.includes("muneaT('event.familyTitle'")
  && app.includes("muneaT('home.walkProgressMet'"),
  'Medication, visit, family-event, and walking cards must render from the active locale catalog');
assert(app.includes("muneaLocale() === 'zh-TW'")
  && app.includes("sub.removeAttribute('data-i18n')")
  && app.includes("chip.removeAttribute('data-i18n')"),
  'Multilingual medicine names must not be truncated at the first word, and state-owned walking output must not be overwritten by static DOM localization');
assert(app.includes('function muneaIsCleanDisplayText(raw)')
  && /function muneaSafeDisplayText[\s\S]*?muneaIsCleanDisplayText\(s\)/.test(app),
  'Stored user-visible names must accept safe multilingual text instead of applying the Chinese-only ASR guard');
assert(app.includes("!/[\u005cp{L}\u005cp{N}]/u.test(meaningful)")
  && app.includes('https?:\\/\\/'),
  'The multilingual display guard must accept Unicode letters while rejecting URL-like and control-character payloads');
assert(/refreshLocalizedDynamicUi\(\)[\s\S]*?renderDailyTasks\(\)[\s\S]*?renderStatusCharts\(true\)/.test(app),
  'Locale changes must rerender daily tasks and locale-formatted chart weekday labels');
assert(app.includes("new Intl.DateTimeFormat(muneaLocale(), { weekday: 'narrow' })")
  && /function _visitDayShort[\s\S]*?new Intl\.DateTimeFormat\(muneaLocale\(\)/.test(app),
  'Weekday labels and visit dates must use the active locale instead of fixed Chinese date text');

// 全滿態給出口：先用文字聊（2026-07-24 Edward 拍板 P0）——不新造頁面，重用既有 chatHandle 文字管線，
// 不佔用 Avatar／即時語音席位，讓長輩在滿載時仍有話可聊而不是只能乾等或放棄。
assert(html.includes('id="textChatPanel"') && html.includes('id="textChatLog"') && html.includes('id="textChatInput"') && html.includes('id="textChatSend"'),
  'The text-chat fallback panel markup must exist on the call screen');
assert(app.includes('function startTextFallbackChat()') && app.includes('function sendTextFallbackMessage()') && app.includes('function exitTextFallbackChat()'),
  'The text-chat fallback lifecycle functions must exist');
assert(app.includes('await window.__chatSay(text);'), 'The text-chat fallback must reuse the existing chatHandle pipeline (via its window.__chatSay bridge) instead of a new chat backend');
assert(app.includes("$('#busyCardAlt')") && app.includes('startTextFallbackChat()'), 'The full-queue card alt button must trigger the text-chat fallback');
assert(app.includes('exitTextFallbackChat()'), 'Leaving the call screen must also tear down the text-chat fallback panel so the next visit starts clean');

const challengeSheet = html.match(/<div class="modal-mask" id="chalModal">([\s\S]*?)<div class="modal-mask" id="actDetailModal">/)?.[1] || '';
assert(challengeSheet, 'Missing challenge creation sheet');
assert(/class="range-row"[^>]*>\s*<input type="range" id="walkGoal"/.test(challengeSheet), 'Walk goal must use the visible range bar');
assert(/class="range-row"[^>]*>\s*<input type="range" id="quizN"/.test(challengeSheet), 'Quiz count must use the visible range bar');
assert(!/id="(?:walkGoal|quizN)"[^>]*(?:hidden|display\s*:\s*none)/.test(challengeSheet), 'Visible challenge sliders must not be hidden');
assert(!/class="step-(?:row|btn|val)"/.test(challengeSheet), 'Challenge sliders must not regress to stepper buttons');

const sendIndex = challengeSheet.indexOf('id="startChalBtn"');
const rewardIndex = challengeSheet.indexOf('id="rewardFields"');
assert(sendIndex > rewardIndex, 'Send invitation button must remain after the form fields');
assert(!/#(?:chalModal\s+)?#?startChalBtn[^\{]*\{[^\}]*position\s*:\s*(?:sticky|fixed)/s.test(css), 'Send invitation button must scroll with form content');
assert(!app.includes("$$('#chalModal .step-btn')"), 'Challenge stepper event handlers must stay removed');

const familyActivitySection = html.match(/id="newChalBtn"[\s\S]*?<div class="sec-head"><div><h2>全家狀態/)?.[0] || '';
assert(familyActivitySection.includes('id="actEmpty"'), 'Family activities must keep a real empty-state anchor');
assert(!familyActivitySection.includes('class="quest-card'), 'Family activities must not ship hard-coded demo cards');
assert(!html.includes('id="demoEventDate"') && !app.includes('fixDemoEventDate'), 'Retired demo activity dates must stay removed');
assert(app.includes('function updateActEmpty()') && app.includes('empty.parentNode.insertBefore(card, empty.nextSibling)'), 'Real activity cards must render from the empty-state anchor');
assert((app.match(/updateActEmpty\(\);/g) || []).length >= 4, 'Family activity empty state must update after render, delete, restore, and expiry');
assert(/\.quest-empty\s*\{[^}]*border:[^}]*dashed/s.test(css), 'Family activity empty state must remain visibly styled');

assert(!html.includes('id="authProviderText"'), 'Account card subtitle must stay removed');
assert(css.includes('--fs-action-primary: 16px;'), 'Primary action typography token must stay at 16px');
assert(/\.auth-primary\s*\{[^}]*font-size:\s*var\(--fs-action-primary\)/s.test(css), 'Sign-in button must use the primary action typography token');
assert(/class="ic auth-ava-placeholder"[^>]*>[\s\S]*?<circle cx="12" cy="7" r="4"\/>[\s\S]*?<path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"\/>/.test(html), 'Guest avatar must use the latest centered account-person icon');
assert(/\.auth-ava\.guest\s*\{[^}]*background:\s*var\(--mint\);[^}]*color:\s*var\(--teal-d\);/s.test(css), 'Guest avatar must keep visible mint contrast');
assert(/\.auth-ava \.auth-ava-placeholder\s*\{[^}]*width:\s*26px;[^}]*height:\s*26px;[^}]*stroke-width:\s*2;/s.test(css), 'Guest avatar icon size and stroke must remain aligned');
assert(/\.auth-ava-img\[hidden\]\s*\{\s*display:\s*none(?:\s*!important)?;\s*\}/s.test(css), 'Hidden account image must not displace the centered guest icon');
assert((html.match(/id="memBadge"/g) || []).length === 1 && !html.includes('authDevBadge'), 'Account card must render exactly one plan or TEST badge');
assert(app.includes('function authDisplayName(state)') && /name:\s*userMetadata\.name/.test(auth), 'Signed-in account card must receive and display the Google or Apple name');
assert(/\.auth-title\s*\{[^}]*white-space:\s*normal;[^}]*overflow-wrap:\s*anywhere;/s.test(css), 'Long account names and translated guest labels must wrap instead of truncating');
assert(/\.auth-secondary\s*\{[^}]*height:\s*40px;[^}]*background:\s*var\(--mint\);[^}]*border:\s*1px solid var\(--teal-d\);/s.test(css), 'Sign-out must keep the latest secondary-button design');
assert(/\.mem-badge\.test\s*\{[^}]*background:\s*var\(--coral-soft\);[^}]*color:\s*var\(--coral-d\);/s.test(css), 'Development account must use the single TEST badge design');

const authSheet = html.match(/<div class="modal-mask auth-sheet" id="authSheet"[\s\S]*?<\/div>\s*<!-- ===== 底部 5 分頁 ===== -->/)?.[0] || '';
assert(authSheet.includes('id="authAppleBtn"') && authSheet.includes('id="authGoogleBtn"'), 'Auth sheet must keep Apple and Google sign-in');
assert(!/authEmailInput|authEmailBtn|電子信箱登入|寄登入信/.test(authSheet), 'Consumer auth sheet must not expose personal email sign-in');
const openAuthSheet = app.match(/function openAuthSheet\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(openAuthSheet && !/\.focus\s*\(/.test(openAuthSheet), 'Opening auth sheet must not focus an input or open the keyboard');

// AI 陪伴角色的說明：設定頁與選角卡片必須在四語系都講同一句，
// 且卡片一定使用明確 key，不能再依賴中文原句剛好與翻譯表相同。
const companionCards = [...html.matchAll(/data-ava="([^"]+)"[\s\S]{0,400}?<b data-i18n="([^"]+)">([^<]+)<\/b><small data-i18n="([^"]+)">([^<]+)<\/small>/g)];
assert(companionCards.length >= 2, 'Companion picker must keep its selectable persona cards');
const companionLabelKey = { 'nening-real-female': 'companion.nening.label', 'companion-real-male': 'companion.ahong.label' };
const companionJoiner = { 'zh-TW': '，', en: ', ', ja: '。', es: ', ' };
companionCards.forEach(([, ava, typeKey, typeFallback, traitKey, traitFallback]) => {
  const labelKey = companionLabelKey[ava];
  if (!labelKey) return;
  assert(zhCatalog[typeKey] === typeFallback, `Companion type fallback must match ${typeKey}`);
  assert(zhCatalog[traitKey] === traitFallback, `Companion trait fallback must match ${traitKey}`);
  Object.entries(catalogs).forEach(([locale, catalog]) => {
    const cardLabel = `${catalog[typeKey]}${companionJoiner[locale]}${catalog[traitKey]}`;
    assert(
      catalog[labelKey] === cardLabel,
      `${locale} 設定頁角色說明必須跟選角卡片講同一句：「${catalog[labelKey]}」 vs「${cardLabel}」`,
    );
    assert(!catalog[labelKey].includes(' · '), `${locale} 角色說明不得使用「·」串標籤`);
  });
});
assert(
  html.includes('<small id="settingsTemplateLabel">' + zhCatalog['companion.nening.label'] + '</small>'),
  '設定頁角色說明的預設字必須跟文案表一致（不然沒載到翻譯時又會兩邊不一樣）',
);

// 健康數據誠實層：蘋果不會告訴 App 讀取被拒絕，所以「有沒有資料」只能看真的讀到什麼，
// 不能看使用者按過連接鍵（munea.devicesOn）。讀不到卻把「穩定/正常」標籤秀出來 = 沒有根據的生理宣稱。
const healthSource = fs.readFileSync('web/src/health.js', 'utf8');
const mmdev = html.match(/window\.MMDEV = function\(\)\{[\s\S]*?\n\};/)?.[0] || '';
assert(mmdev, 'Status page must keep the health honesty layer (MMDEV)');
assert(/metricStates/.test(mmdev) && /metricStates/.test(healthSource), 'Health honesty layer must render from per-metric read results');
assert(/hide\('bpChip'\)/.test(mmdev) && /hide\('hrChip'\)/.test(mmdev), 'Blood-pressure and heart-rate chips must be hidden when the metric was not read');
assert(!/^\s*var has = !!localStorage\.getItem\('munea\.devicesOn'\);[\s\S]*?if\(has\)\{[^}]*forEach\(show\)/m.test(mmdev), 'Health chips must not be shown just because the connect button was tapped');
assert(/hasAnyValue/.test(healthSource) && /r\.empty/.test(app), 'Connecting Apple Health with nothing readable must be reported honestly, not promised as syncing');
assert(!/predicate: nil/.test(fs.readFileSync('ios/App/App/HealthPlugin.swift', 'utf8')), 'Latest vitals must be time-bounded so stale readings are not shown as today');

// ── 訂閱點數揭露：不遞延／不過期／扣點順序（2026-07-30 改寫）─────────────────────
// 原本是在 index.html 的 planModal 裡 grep「會員月點數」「當月有效・不留到下個月」等中文句子。
// 四語系化之後底稿改成英文、中文改由 zh-TW.json 執行時套上，於是這幾條在乾淨 main 上長期紅燈：
// 消費者揭露一直都在，紅的是守門。改照上面的三層守——節點在 → 由哪個 key 餵 → 文案表真的講到。
const subscriptionSheet = html.match(/<div class="reader-page sub-page" id="planModal">([\s\S]*?)<div class="modal-mask" id="visitModal">/)?.[1] || '';
assert(subscriptionSheet, 'Subscription sheet markup not found (planModal)');
// ① 結構：訂閱方案／加購點數兩個分頁，各要有一組完整三行的點數規則
const pointsPaneStart = subscriptionSheet.indexOf('<div id="subPoints"');
assert(pointsPaneStart > 0, 'Subscription sheet must keep the separate credit-purchase pane');
const plansPane = subscriptionSheet.slice(0, pointsPaneStart);
const pointsPane = subscriptionSheet.slice(pointsPaneStart);
[['訂閱方案', plansPane], ['加購點數', pointsPane]].forEach(([paneName, pane]) => {
  assert((pane.match(/class="credit-rules/g) || []).length === 1, `${paneName}分頁必須有一組點數使用規則`);
  assert((pane.match(/class="cr-row"/g) || []).length === 3, `${paneName}分頁的點數規則必須是三行：月點數／加購點數／扣點順序`);
});
// ② 接線：三行由哪三組 key 餵，且兩個分頁都要跟著換語言（少接一邊＝加購頁會停在英文）
[
  'subscription.monthlyCreditsTitle', 'subscription.monthlyCreditsBody',
  'subscription.purchasedCreditsTitle', 'subscription.purchasedCreditsBody',
  'subscription.deductionOrderTitle', 'subscription.deductionOrderBody',
].forEach((key) => {
  assert(app.includes(`'${key}'`), `點數規則必須由 ${key} 餵，四語系才會一起換`);
});
assert(/#subPlans \.credit-rules \.cr-row[^']*#subPoints \.credit-rules \.cr-row/.test(app), '加購點數分頁的規則也要跟著換語言，不能只換訂閱分頁');
// ③ 文案：三條規則各自要講到不遞延／不過期／先扣月點
assertCatalogSays('subscription.monthlyCreditsBody', { 'zh-TW': /不會累積|不留到下/, en: /do not roll over/i }, '每月方案點數必須說明不會留到下一期');
assertCatalogSays('subscription.purchasedCreditsBody', { 'zh-TW': /不會到期/, en: /do not expire/i }, '加購點數必須說明不會過期');
assertCatalogSays('subscription.deductionOrderBody', { 'zh-TW': /每月點數[\s\S]*加購點數/, en: /before purchased credits/i }, '扣點順序必須說明先扣月點數、再扣加購');
// 每張付費方案卡的點數那一行都要自己標「當月點數不遞延」。
// 原本寫死 .length === 2，方案一增減就會誤紅；改成從畫面上真的有幾張方案卡推出來。
const planCards = [...plansPane.matchAll(/<button class="ppk[^"]*" data-t="([a-z]+)" type="button">([\s\S]*?)<\/button>/g)]
  .map(([, plan, body]) => ({ plan, body }));
assert(planCards.length >= 2, '付費方案卡片必須留在畫面上（至少 Plus 與 Pro）');
const rolloverLabelled = planCards.filter(({ body }) => /do not roll over/i.test(body.match(/<li>([\s\S]*?)<\/li>/)?.[1] || ''));
assert(
  rolloverLabelled.length === planCards.length,
  `每張付費方案卡的點數那行都要標不遞延：方案 ${planCards.length} 張、標到的 ${rolloverLabelled.length} 張`,
);
assert(app.includes("'subscription.monthlyVoiceCredits'"), '方案卡的點數那行必須由 subscription.monthlyVoiceCredits 餵');
assertCatalogSays('subscription.monthlyVoiceCredits', { 'zh-TW': /不會累積|不留到下/, en: /do not roll over/i }, '方案卡的每月點數必須說明不會留到下一期');
assert(/\.credit-rules\s*\{[^}]*font-size/s.test(css) || css.includes('.cr-row {'), 'Credit rule explanation must have dedicated readable styling');
// 資料匯出說明（2026-07-30 改寫）：這段已經是 data-i18n="data.description" 的翻譯節點，
// index.html 裡那句中文只是還沒換掉的底稿，跟 zh-TW.json 的正本已經對不起來（正本沒有「立即」兩字）。
assert(/data-i18n="data\.description"/.test(html), '資料匯出說明必須由文案表餵，才會跟著 App 語言換');
assertCatalogSays('data.description', { 'zh-TW': [/JSON/, /登入/], en: [/JSON/, /sign(ing)? in/i] }, '資料匯出說明必須講清楚登入後可建立自己的 JSON 資料副本');
assert(app.includes('result.exportPackage') && app.includes('navigator.canShare') && app.includes('a.download = filename'), 'Data export must share or download the generated JSON package');

assert(html.includes('src/medication.js'), 'App shell must load the shared medication occurrence service');
assert(app.includes("item.dataset.task === 'pill' && window.MuneaMedication"), 'Home medication checkbox must use the shared occurrence service');
assert(app.includes("window.MuneaMedication.setStatus(dose, 'taken', 'notification')"), 'Reminder completion must use the shared occurrence service');
const deviceEmptyState = html.match(/window\.MMDEV = function\([^)]*\)\{[\s\S]*?\n\};/)?.[0] || '';
assert(deviceEmptyState && !deviceEmptyState.includes('medTrendChart'), 'Medication history must not be hidden by Apple Health empty state');
assert(html.includes('用藥紀錄是 Munea 自己的帳本，不依賴 Apple Health'), 'Medication trend must remain independent from Apple Health');
assert(app.includes("type: 'action_result'") && app.includes("await window.__muneaHandleVoiceAction"), 'Voice AI must wait for the App action result before confirming reminders');
assert(app.includes("action: 'claim'") && app.includes("action === 'send_family_relay'"), 'Family relay must use a recipient-specific claim queue and the voice action bridge');

// 邀請碼拒絕理由要講人話（2026-07-17 Edward 指示：不能全混成「連上雲端並完成帳號驗證」一句）
assert(app.includes('INVITE_FAIL_TEXT'), 'Invite failures must map server reasons to plain-language text');
assert(app.includes('先登入帳號，才能邀請家人') && app.includes('網路不通，請檢查連線後再試一次') && app.includes('只有家庭健康圈的圈主能建立邀請碼'), 'Invite failure texts must cover sign-in, owner and network reasons');
assert(/family_plan_required.*upsell|upsell\('family-invite'\)/s.test(app.match(/function fillInvCode[\s\S]*?\n  \}/)?.[0] || ''), 'Plan-gated invite failures must open the same upgrade sheet as the entry gate');
assert(!app.includes('需要連上雲端並完成帳號驗證'), 'The old catch-all invite error sentence must stay dead');
assert(/id="invTempNote" style="display:none"><\/p>/.test(html), 'Invite note must start empty; the stale offline-temp-code copy must stay removed');
assert(app.includes('function syncAccountScopedCaches') && app.includes("removeItem('munea.inviteCode')") && app.includes("removeItem('munea.plan')"), 'Switching accounts must clear the previous account\'s plan and invite-code cache');

// 情緒監測卡防磚（2026-07-16 真機事故）：後端 moodKey 曾以英文字串回來，重畫時炸掉＝按鍵綁定消失、整卡死掉
assert(html.includes('function normMoodKey'), 'Mood card must normalize every mood key before use');
assert(/var server=j\.signals\.map\(function\(sg\)\{ var i=normMoodKey\(sg\.moodKey\)/.test(html), 'Cloud mood signals must pass through normMoodKey before merging');
assert(/x\.i!=null/.test(html), 'Cloud mood rows without a safe key must be dropped, not saved');
assert(/var ni=normMoodKey\(x\.i\); if\(ni==null\) continue;/.test(html), 'Cached mood entries must be sanitized on load so a poisoned cache heals itself');
assert(/if\(i!=null&&!MOODS\[i\]\) i=null;/.test(html), 'Mood card decorate must survive an unknown mood key instead of dying');

// 訂閱確認欄（2026-07-17 Edward 真機回報）：整頁會捲（.sub-page overflow-y:auto），
// absolute 會跟著內容捲走、浮到畫面中間；fixed 才真的釘在手機下方。
const planConfirmCss = css.match(/\.plan-confirm-bar \{[^}]*\}/)?.[0] || '';
assert(planConfirmCss, 'Plan confirm bar must keep a dedicated style rule');
assert(/position:\s*fixed/.test(planConfirmCss), 'Plan confirm bar must be fixed to the phone bottom; absolute scrolls away inside the scrollable plan page');
assert(!/position:\s*absolute/.test(planConfirmCss), 'The old absolute positioning must stay dead — it floated the bar into mid-screen');
assert(/\.sub-page \{[^}]*overflow-y:\s*auto/.test(css), 'The plan page scrolls as a whole; this is why the confirm bar cannot be absolute');

// 畫面寫什麼＝就扣什麼：確認欄開著時改方案／月年繳，不重畫就會扣錯商品
assert(app.includes('function planConfirmHtml') && app.includes('function syncPlanConfirm'), 'Plan confirm text must be re-rendered from a single source, not snapshotted once');
const renderSubUiBody = app.match(/function renderSubUI\(\) \{[\s\S]*?\n  \}/)?.[0] || '';
assert(renderSubUiBody, 'renderSubUI must remain a readable single function');
assert(renderSubUiBody.includes('syncPlanConfirm()'), 'Changing plan or billing cycle must re-sync the open confirm bar');
const showPlanConfirmBody = app.match(/function showPlanConfirm\(\) \{[\s\S]*?\n  \}/)?.[0] || '';
assert(showPlanConfirmBody.includes('_planPick = _subPlan;'), 'The picked plan must always follow the currently selected plan');
assert(!/\$\('#planConfirm'\)\.style\.display = ''/.test(app), 'Plan confirm bar must only be opened through showPlanConfirm');
assert((app.match(/\$\('#planConfirm'\)\.style\.display = 'none'/g) || []).length === 0, 'Plan confirm bar must only be closed through hidePlanConfirm');
assert(/#planClose'\)\.addEventListener\('click', \(\) => \{\s*hidePlanConfirm\(\);/.test(app), 'Closing the plan page must drop a half-finished confirm bar');
assert(/#managePlanBtn'\)\.addEventListener\('click', \(\) => \{\s*hidePlanConfirm\(\);/.test(app), 'Opening the plan page must start from a clean confirm state');
assert(app.includes("body.style.paddingBottom = (bar.offsetHeight + 18)"), 'Content must be padded so the fixed bar never buries the subscription terms');

// 免費不能買點數（Edward 2026-07-17 拍板 Ⓐ）：免費走一次性 5 分鐘體驗、不吃點數，
// 賣他點數＝收了錢給不出東西（蘋果也會擋）。但已經買過的點必須看得到、留著。
const renderPlanStateBody = app.match(/function renderPlanState\(\) \{[\s\S]*?\n  \}/)?.[0] || '';
assert(renderPlanStateBody, 'renderPlanState must remain a readable single function');
assert(renderSubUiBody.includes("seg.style.display = cur === 'free' ? 'none' : ''"), 'Free members must not see the points-purchase switcher at all');
assert(renderSubUiBody.includes("unlock.style.display = cur === 'free' ? '' : 'none'"), 'Free members must be told when points purchasing unlocks');
// 2026-07-30 改寫：這句已經搬進文案表（subscription.unlockCredits），HTML 裡只剩英文底稿。
assert(/id="pointsUnlockNotice"[\s\S]{0,200}?data-i18n="subscription\.unlockCredits"/.test(html), '免費會員必須看得到「訂閱之後才能加購點數」的說明，且由文案表餵');
assertCatalogSays('subscription.unlockCredits', { 'zh-TW': [/訂閱/, /點數/], en: /credit/i }, '免費會員必須被告知加購點數要先訂閱');
assert(renderSubUiBody.includes("if (cur === 'free') showSubPane('plans')"), 'Free members must be forced onto the subscription pane');
assert(/dataset\.pane === 'points' && circlePlan\(\) === 'free'\) return;/.test(app), 'Clicking the points tab must be blocked for free members as a second guard');
assert(app.includes('function showSubPane'), 'Pane switching must go through one function so the free guard cannot be bypassed');
assert(renderPlanStateBody.includes("_tBtn.style.display = _isFreeP ? 'none' : ''"), 'The top-up button must stay hidden for free members');
// 只要有點數就一定看得到餘額（Edward 親訓）。
// 2026-07-30 晚改寫：餘額與說明句從 renderPlanState 搬進 renderCreditRow，且改讀伺服器錢包。
// 原因是同一張卡上兩個數字來自兩個來源——餘額讀伺服器、說明句讀本機「歷史累計買過」
// （localStorage munea.ptsBought，只增不減、後台發的點也永遠不會寫進來）：
//   ① 餘額 193 卻寫「你還有 500 點沒用完」
//   ② 後台發點給免費會員，本機沒有那筆 → 整列餘額被藏起來，違反這條拍板本身
const renderCreditRowBody = app.match(/function renderCreditRow\(\) \{[\s\S]*?\n  \}/)?.[0] || '';
assert(renderCreditRowBody, 'renderCreditRow must remain a readable single function');
assert(/function creditsInHand\(\) \{[^}]*ptsLeft\(\)/.test(app), '手上還剩多少點必須讀 ptsLeft（伺服器餘額優先）');
assert(/const inHand = isFree \? creditsInHand\(\) : 0;/.test(renderCreditRowBody), 'Leftover points must come from the server wallet, not a local counter');
assert(/lbl\.style\.display = \(!isFree \|\| inHand > 0\) \? '' : 'none'/.test(renderCreditRowBody), 'Any member holding points must still see the balance');
// 反向守門：餘額／說明句一旦回頭讀本機累計，上面兩個症狀就會同時復發
assert(!/POINTS\.bought/.test(renderCreditRowBody), '點數列不准讀本機累計購買數（只增不減、看不到後台發的點）');
assert(!/POINTS\.bought/.test(renderPlanStateBody), '方案卡不准用本機累計購買數決定要不要顯示餘額');
// 伺服器餘額（/credits/balance）回來時只會走 renderPoints，它必須回頭重算這一列，
// 否則開機兩支並行、餘額後到就沒人重畫（畫面停在「手上沒有點數」）
assert(
  (app.match(/function renderPoints\(\) \{[\s\S]*?\n\}/)?.[0] || '').includes('__muneaRenderCreditRow'),
  'A late server balance must still repaint the settings credit row',
);
assert(
  renderCreditRowBody.includes("'subscription.freeCreditsLeft'") && renderCreditRowBody.includes('{ credits: inHand }'),
  'Free members with leftover points must be told the points are kept and how to use them',
);
assertCatalogSays('subscription.freeCreditsLeft', { 'zh-TW': [/留著|保留/, /訂閱/], en: [/remain/i, /subscribe/i] }, '免費會員手上剩的加購點數必須說明會留著、以及怎麼用');
assert(/remainingCredits/.test(rendererCopySource), '文案層的免費說明句必須吃「手上還剩多少點」');
// 換方案時不准憑空生出「已用」——舊寫法填 Math.round(pts * 0.3)，畫面會寫「每月送 100 · 已用 30」，
// 那 30 點誰都沒用過。本機只負責不要顯示超過額度的數，真相在伺服器。
assert(!/POINTS\.used = Math\.round\(pts \* 0\.3\)/.test(app), '換方案不准捏造「已用」點數');
const ptsPillHiddenBody = app.match(/function ptsPillHidden\(\) \{[^}]*\}/)?.[0] || '';
assert(/isFree\(\)\) && ptsLeft\(\) <= 0/.test(ptsPillHiddenBody), 'The chat points chip may only hide when a free member truly has zero points');
// 「點數快用完、去加值」只對付費成立（免費 0 點時 0 < 30 會誤觸發、且加值鈕根本是藏的）
const refreshLowStateBody = app.match(/function refreshLowState\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(/const low = !\(window\.MMPLAN && window\.MMPLAN\.isFree\(\)\) && ptsLeft\(\) < LOW_PTS;/.test(refreshLowStateBody), 'The low-points warning must never fire for free members');
assert(!/strip\.style\.display = ptsLeft\(\) < LOW_PTS/.test(app), 'The plan-blind low-points warning must stay dead');

const renderPointsBody = app.match(/function renderPoints\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(renderPointsBody.includes("muneaT('settings.creditsBalance'") && renderPointsBody.includes('Intl.NumberFormat(muneaLocale())'), 'The live credit balance must use compact locale copy and number formatting');
const callBudgetTickBody = app.match(/function callBudgetTick\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(callBudgetTickBody.includes("muneaT('credits.lowTitle'") && callBudgetTickBody.includes("muneaT('credits.lowBody'"), 'The low-credit call warning must be localized without changing the budget gate');
const pointsPopupCopyBody = app.match(/function renderPointsPopupCopy\(root\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(pointsPopupCopyBody && app.includes("'credits.exhaustedTitle'") && app.includes("'credits.exhaustedBody'"), 'The exhausted-credit dialog must render localized title and body copy');
assert(app.includes("muneaT('settings.topUpCredits'") && app.includes("muneaT('common.notNow'"), 'The exhausted-credit dialog actions must use shared localized labels');
const refreshLocalizedDynamicUiBody = app.match(/function refreshLocalizedDynamicUi\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(refreshLocalizedDynamicUiBody.includes('renderPointsPopupCopy()'), 'An open exhausted-credit dialog must rerender after the iOS App Language changes');
assert(app.includes("muneaT('credits.freeTrialEnded'"), 'The free-trial exhaustion toast must be localized');
assert(app.includes("muneaT(\n          'credits.freeTrialOneMinute'"), 'The one-minute free-trial warning must be localized and must not call a minute a credit');
assert(!app.includes("toast('免費體驗剩約 1 點"), 'The free-trial warning must never label a remaining minute as one credit');

// 付款失敗要講原因（同邀請碼 105 號教訓：不能全混成一句）。
// 2026-07-30 改寫：訊息已經從 app.js 的中文字串搬進 web/src/i18n/purchase-flow.js 的理由對照表，
// 所以改守「每個理由有沒有對到自己的 key」＋「四語系裡這些句子彼此不同、也不等於通用失敗句」——
// 「不能全混成一句」本來就是可以直接驗的結構事實，不必去比對某一國語言的句子長什麼樣。
const purchaseFlowSource = fs.readFileSync('web/src/i18n/purchase-flow.js', 'utf8');
assert(app.includes('function planPurchaseFailMessage'), 'Purchase failures must map reasons to plain-language text');
assert(/purchaseFlow\s*\?\s*purchaseFlow\.failureMessage\(reason\)/.test(app), '付款失敗訊息必須走同一張理由對照表，不能每處各寫一句');
const PURCHASE_FAIL_REASONS = {
  signin_required: 'purchase.signInRequiredBody',
  notfound: 'purchase.productUnavailable',
  store_products_unavailable: 'purchase.productUnavailable',
  unverified: 'purchase.unverified',
  apple_account_token_mismatch: 'purchase.accountMismatch',
  server_verification_failed: 'purchase.serverVerificationFailed',
};
Object.entries(PURCHASE_FAIL_REASONS).forEach(([reason, key]) => {
  assert(
    new RegExp(`${reason}:\\s*'${key.replace(/\./g, '\\.')}'`).test(purchaseFlowSource),
    `付款失敗理由 ${reason} 必須對到 ${key}，不能落回通用失敗句`,
  );
});
const purchaseFailKeys = [...new Set(Object.values(PURCHASE_FAIL_REASONS))];
COPY_LOCALES.forEach((locale) => {
  const texts = purchaseFailKeys.map(key => catalogs[locale][key]);
  purchaseFailKeys.forEach((key, index) => {
    assert(texts[index] && texts[index] !== catalogs[locale]['purchase.failed'], `${locale}:${key} 不能空白、也不能跟通用失敗句同一句`);
  });
  assert(new Set(texts).size === texts.length, `${locale} 每個付款失敗理由必須各講各的，不能混成同一句`);
});
assert(app.includes("reason === 'apple_account_token_mismatch'"), 'An Apple account-token mismatch must stay a separately handled purchase outcome');
assertCatalogSays('purchase.accountMismatch', { 'zh-TW': [/帳戶|帳號/, /恢復|切換/], en: [/account/i, /restore/i] }, '買到別的帳戶名下時要講清楚是哪個帳戶、怎麼恢復');
assertCatalogSays('purchase.serverVerificationFailed', { 'zh-TW': [/請勿重複購買|不要重複/, /恢復購買/], en: [/do not buy again/i, /restore/i] }, '驗證失敗必須擋住重複付款、並指向恢復購買');
assert(app.includes("'TEST · ' + (_memBadgePlan || 'free').toUpperCase()"), 'Developer badges must expose the simulated FREE/PLUS/PRO identity');

// App Store 評分視窗整條鏈（2026-07-29 立）。背景：網頁端 2026-07 就寫好時機閘，但原生那半從沒實作，
// 呼叫寫成「找不到就安靜跳過」＝沒有紅字、沒有痕跡，壞了幾個月沒人發現。新 App 沒評分數量＝搜尋排名被壓死，
// 所以這條鏈斷掉的代價很高。以下四道確保網頁與原生永遠成對存在，任何一端被拿掉就亮紅燈。
assert(/@objc func requestReview\(_ call: CAPPluginCall\)/.test(storePlugin), 'The native App Store review sheet must stay implemented in StorePlugin.swift');
assert(/CAPPluginMethod\(name: "requestReview"/.test(storePlugin), 'requestReview must stay registered in pluginMethods or the web bridge cannot reach it');
assert(/AppStore\.requestReview\(in: scene\)/.test(storePlugin) && /SKStoreReviewController\.requestReview\(in: scene\)/.test(storePlugin), 'The review sheet must cover both iOS 16+ and the iOS 15 floor');
assert(/requestReview: requestReview/.test(store) && /p\.requestReview/.test(store), 'MuneaStore must expose requestReview so app.js can bridge to the native sheet');
assert(/window\.__muneaRequestReview = function \(\) \{ return window\.MuneaStore\.requestReview\(\); \}/.test(app), 'app.js must bridge __muneaRequestReview to the native plugin');
// 最要命的一條：原生沒接上時絕不能先蓋「這版問過了」的章，否則補好原生也叫不動已裝機的人（2026-07-29 修）
const askReviewBody = app.match(/window\.__muneaMaybeAskReview = function \(moment\) \{[\s\S]*?\n  \};/)?.[0] || '';
assert(askReviewBody, 'The review timing gate must remain a readable single function');
assert(askReviewBody.indexOf("typeof window.__muneaRequestReview !== 'function'") < askReviewBody.indexOf("localStorage.setItem('munea.reviewAsked."), 'The native-availability check must run BEFORE the once-per-version flag is written');

console.log('UI contracts OK: version SSOT, critical consent controls, Tokyo privacy disclosure, billing credit rules, medication data chain, social auth, quiet keyboard, latest account card, challenge controls, real family activities, and the App Store review chain');

// Multilingual catalogs stay development-only until their UI, Voice, regional,
// App Store, and real-device gates pass. Keep this in the existing launch suite
// without competing with active work that is editing package.json.
require('./test-i18n-catalogs.js');
require('./test-i18n-runtime.js');
require('./test-i18n-browser-bootstrap.js');
require('./test-i18n-preview.js');
require('./test-i18n-dom-localizer.js');
require('./test-i18n-legal-routing.js');
require('./test-i18n-migration-worklist.js');
require('./test-i18n-pseudo-catalog.js');
require('./test-companion-profile-localization.js');
require('./test-medication-schedule-i18n.js');
require('./test-i18n-surface-inventory.js');
require('./test-purchase-flow-localizations.js');
require('./test-purchase-flow-view-model.js');
require('./test-app-screen-localizations.js');
require('./test-app-binding-runtime.js');
require('./test-app-i18n-binding-manifest.js');
require('./test-app-surface-manifest.js');
require('./test-app-surface-copy-manifest.js');
require('./test-app-full-surface-i18n-browser-precheck.js');
require('./test-i18n-native-review-worklist.js');
require('./test-i18n-native-review-evidence.js');
require('./test-i18n-visual-qa-worklist.js');
require('./test-i18n-visual-qa-evidence.js');
require('./test-ipa-binary-identity.js');
require('./test-ios-build-identity.js');
require('./test-i18n-app-e2e-evidence.js');
require('./test-ios-export-i18n-binary-gate.js');
require('./test-i18n-layout-risk-worklist.js');
require('./test-legal-localizations.js');
require('./test-marketing-site-localizations.js');
require('./test-app-store-localizations.js');
require('./test-in-app-purchase-localizations.js');
require('./test-i18n-release-readiness.js');
