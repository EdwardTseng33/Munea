const fs = require('fs');

const html = fs.readFileSync('web/index.html', 'utf8');
const app = fs.readFileSync('web/src/app.js', 'utf8');
const auth = fs.readFileSync('web/src/auth.js', 'utf8');
const css = fs.readFileSync('web/src/styles.css', 'utf8');
const versionSource = fs.readFileSync('web/src/version.js', 'utf8');
const privacy = fs.readFileSync('web/privacy.html', 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(/id="verRowNum">—<\/span>/.test(html) && /id="verCurrent">—<\/span>/.test(html), 'Version UI placeholders must not contain a stale semantic version');
assert(!/id="(?:verRowNum|verCurrent)">\d+\.\d+\.\d+<\/span>/.test(html), 'Version UI must not hard-code a fallback release number');
assert(versionSource.includes('window.MuneaApplyVersionToStaticUi') && versionSource.includes("['verRowNum', 'verCurrent']"), 'The version SSOT must bind both static version labels immediately');

assert(app.includes('const __pullPromise = Promise.resolve(syncPullAll());'), 'Family sync bypass must still produce a safe promise for downstream initialization');
const criticalConsentSetup = app.match(/function setupCriticalConsentControls\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(criticalConsentSetup.includes("$('#consentAgree')") && criticalConsentSetup.includes("sheet.querySelector('.mx-close')"), 'Consent agree and close controls must be bound by the critical early setup');
assert(criticalConsentSetup.includes("$('#consentDetail')") && criticalConsentSetup.includes("openInAppReader('privacy', { returnToConsent: true })"), 'Consent privacy detail must open the in-App reader and return to consent');
assert(criticalConsentSetup.includes("$('#readerBack')") && criticalConsentSetup.includes('closeInAppReader'), 'The in-App privacy reader must retain a working back control');
assert(app.indexOf("document.addEventListener('DOMContentLoaded', setupCriticalConsentControls)") < app.indexOf("document.addEventListener('DOMContentLoaded', init)"), 'Critical consent controls must bind before the main App initialization');
assert(!app.includes("window.open('privacy.html', '_blank')"), 'Consent privacy detail must not leave the App in a new window');
assert(privacy.includes('目前機房位於日本東京'), 'Privacy disclosure must identify the current Tokyo data region');
assert(!privacy.includes('目前機房位於澳洲'), 'Privacy disclosure must not retain the retired Sydney production region');
const connectCall = app.match(/async function connectCall\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(connectCall.indexOf('setCallDialing(true)') < connectCall.indexOf('LiveVoice.prime()'), 'Call button must enter dialing state before microphone or network preparation');
assert(connectCall.includes('if (!developmentDirectCall)') && connectCall.includes('Promise.race([') && connectCall.includes('setTimeout(resolve, 1200)'), 'Family relay lookup must not block development calls or delay production dialing indefinitely');
assert(/if \(!LiveVoice\.prime\(\)\) \{\s*setCallDialing\(false\)/.test(connectCall), 'Microphone failure must leave the dialing state');

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
assert(/\.auth-title\s*\{[^}]*white-space:\s*nowrap;[^}]*text-overflow:\s*ellipsis;/s.test(css), 'Long account names must stay on one truncated line');
assert(/\.auth-secondary\s*\{[^}]*height:\s*40px;[^}]*background:\s*var\(--mint\);[^}]*border:\s*1px solid var\(--teal-d\);/s.test(css), 'Sign-out must keep the latest secondary-button design');
assert(/\.mem-badge\.test\s*\{[^}]*background:\s*var\(--coral-soft\);[^}]*color:\s*var\(--coral-d\);/s.test(css), 'Development account must use the single TEST badge design');

const authSheet = html.match(/<div class="modal-mask auth-sheet" id="authSheet"[\s\S]*?<\/div>\s*<!-- ===== 底部 5 分頁 ===== -->/)?.[0] || '';
assert(authSheet.includes('id="authAppleBtn"') && authSheet.includes('id="authGoogleBtn"'), 'Auth sheet must keep Apple and Google sign-in');
assert(!/authEmailInput|authEmailBtn|電子信箱登入|寄登入信/.test(authSheet), 'Consumer auth sheet must not expose personal email sign-in');
const openAuthSheet = app.match(/function openAuthSheet\(\) \{[\s\S]*?\n\}/)?.[0] || '';
assert(openAuthSheet && !/\.focus\s*\(/.test(openAuthSheet), 'Opening auth sheet must not focus an input or open the keyboard');

const subscriptionSheet = html.match(/<div class="reader-page sub-page" id="planModal">([\s\S]*?)<div class="modal-mask" id="visitModal">/)?.[1] || '';
assert(subscriptionSheet.includes('會員月點數') && subscriptionSheet.includes('每期重發，不累積'), 'Subscription plans must explain that monthly credits do not roll over');
assert(subscriptionSheet.includes('加購點數') && subscriptionSheet.includes('可累積，不會過期'), 'Subscription plans must distinguish durable purchased credits');
assert((subscriptionSheet.match(/當期有效・不累積/g) || []).length === 2, 'Every paid plan credit allowance must show its non-rollover label');
const pointsPane = subscriptionSheet.match(/<div id="subPoints"[\s\S]*?<\/div>\s*<\/div>\s*<div class="plan-confirm-bar"/)?.[0] || '';
assert(pointsPane.includes('會員月點數') && pointsPane.includes('每期重發，不累積'), 'Points purchase pane must explain monthly-credit expiry');
assert(pointsPane.includes('加購點數') && pointsPane.includes('可累積，不會過期'), 'Points purchase pane must explain purchased-credit retention');
assert(pointsPane.includes('扣點順序') && pointsPane.includes('先扣月點數，再扣加購'), 'Points purchase pane must explain credit deduction order');
assert(/\.credit-rules\s*\{[^}]*font-size/s.test(css) || css.includes('.cr-row {'), 'Credit rule explanation must have dedicated readable styling');
assert(html.includes('立即建立只屬於你的 JSON 資料副本'), 'Data export sheet must explain immediate scoped delivery');
assert(app.includes('result.exportPackage') && app.includes('navigator.canShare') && app.includes('a.download = filename'), 'Data export must share or download the generated JSON package');

assert(html.includes('src/medication.js'), 'App shell must load the shared medication occurrence service');
assert(app.includes("item.dataset.task === 'pill' && window.MuneaMedication"), 'Home medication checkbox must use the shared occurrence service');
assert(app.includes("window.MuneaMedication.setStatus(dose, 'taken', 'notification')"), 'Reminder completion must use the shared occurrence service');
const deviceEmptyState = html.match(/window\.MMDEV = function\(\)\{[\s\S]*?\n\};/)?.[0] || '';
assert(deviceEmptyState && !deviceEmptyState.includes('medTrendChart'), 'Medication history must not be hidden by Apple Health empty state');
assert(html.includes('用藥紀錄是 Munea 自己的帳本，不依賴 Apple Health'), 'Medication trend must remain independent from Apple Health');
assert(app.includes("type: 'action_result'") && app.includes("await window.__muneaHandleVoiceAction"), 'Voice AI must wait for the App action result before confirming reminders');
assert(app.includes("action: 'claim'") && app.includes("action === 'send_family_relay'"), 'Family relay must use a recipient-specific claim queue and the voice action bridge');

// 情緒監測卡防磚（2026-07-16 真機事故）：後端 moodKey 曾以英文字串回來，重畫時炸掉＝按鍵綁定消失、整卡死掉
assert(html.includes('function normMoodKey'), 'Mood card must normalize every mood key before use');
assert(/var server=j\.signals\.map\(function\(sg\)\{ var i=normMoodKey\(sg\.moodKey\)/.test(html), 'Cloud mood signals must pass through normMoodKey before merging');
assert(/x\.i!=null/.test(html), 'Cloud mood rows without a safe key must be dropped, not saved');
assert(/var ni=normMoodKey\(x\.i\); if\(ni==null\) continue;/.test(html), 'Cached mood entries must be sanitized on load so a poisoned cache heals itself');
assert(/if\(i!=null&&!MOODS\[i\]\) i=null;/.test(html), 'Mood card decorate must survive an unknown mood key instead of dying');

console.log('UI contracts OK: version SSOT, critical consent controls, Tokyo privacy disclosure, billing credit rules, medication data chain, social auth, quiet keyboard, latest account card, challenge controls, and real family activities');
