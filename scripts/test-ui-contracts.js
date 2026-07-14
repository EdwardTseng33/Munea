const fs = require('fs');

const html = fs.readFileSync('web/index.html', 'utf8');
const app = fs.readFileSync('web/src/app.js', 'utf8');
const auth = fs.readFileSync('web/src/auth.js', 'utf8');
const css = fs.readFileSync('web/src/styles.css', 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

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

console.log('UI contracts OK: billing credit rules, medication data chain, social auth, quiet keyboard, latest account card, and challenge controls');
