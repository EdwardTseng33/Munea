const assert = require('assert');
const fs = require('fs');

const swift = fs.readFileSync('ios/App/App/NotifyPlugin.swift', 'utf8');
const delegate = fs.readFileSync('ios/App/App/AppDelegate.swift', 'utf8');
const entitlements = fs.readFileSync('ios/App/App/App.entitlements', 'utf8');
const project = fs.readFileSync('ios/App/App.xcodeproj/project.pbxproj', 'utf8');
const web = fs.readFileSync('web/src/notify.js', 'utf8');
const html = fs.readFileSync('web/index.html', 'utf8');
const auth = fs.readFileSync('web/src/auth.js', 'utf8');

for (const method of ['getPermissionStatus', 'registerRemoteNotifications', 'getPendingLaunchNotification', 'openSettings', 'scheduleTestNotification']) {
  assert(swift.includes(`name: "${method}"`), `NotifyPlugin must expose ${method}`);
}
assert(!swift.includes('removeAllPendingNotificationRequests'), 'Local sync must not delete unrelated pending notifications');
assert(swift.includes('munea.local.'), 'Local notification identifiers must be namespaced');
assert(swift.includes('notificationOpened'), 'Native bridge must emit notification click events');
assert(swift.includes('showSensitiveContent'), 'Native local notifications must honor the privacy preference');
assert(delegate.includes('didRegisterForRemoteNotificationsWithDeviceToken'), 'AppDelegate must capture the APNs device token');
assert(delegate.includes('UNUserNotificationCenterDelegate'), 'AppDelegate must route foreground and opened notifications');
assert(entitlements.includes('aps-environment'), 'Push entitlement is required');
assert(project.includes('com.apple.Push'), 'Xcode target must enable Push Notifications capability');
assert(project.includes('APS_ENVIRONMENT = development') && project.includes('APS_ENVIRONMENT = production'), 'Debug and release APNs environments must be explicit');
assert(web.includes("api('/push/devices'"), 'Web bridge must register device tokens with the backend');
assert(html.includes('src/notify.js?v=20261109-askincontext'), 'Notification UI changes must invalidate the stale WebView script cache');
assert(web.includes("api('/notifications'"), 'Web bridge must mark opened notifications in the durable inbox');
assert(web.includes('notificationInboxModal') && web.includes('openNotificationInbox'), 'App must expose a durable notification inbox');
assert(web.includes("api('/notifications/settings'") && web.includes("action: 'set'"), 'Notification switches must persist through the backend settings API');
assert(web.includes('controller.abort()') && web.includes('}, 5000)'), 'Notification settings API must not hold App startup indefinitely');
assert(web.includes('notificationCenterRow') && web.includes('notificationSettingsPage'), 'Settings must expose one notification-center row and its full-screen sub-page');
assert(web.includes('reader-page notification-page'), 'Notification center must be a full-screen sub-page, not a bottom sheet (2026-07-16 Edward)');
assert(web.includes('notificationSafetyContacts') && web.includes('munea.safetyContacts'), 'Notification center must expose the safety emergency-contact entry');
for (const category of ['medication', 'clinic', 'family', 'safety']) {
  assert(web.includes(`data-notification-setting=\"${category}\"`), `Notification center must expose the ${category} switch`);
}
assert(web.includes("anchor.hidden = true") && web.includes("anchor.style.display = 'none'"), 'The standalone safety-notification row must be removed from settings');
assert(web.includes('enabledNotificationItems()'), 'Category switches must filter native local schedules too');
assert(web.includes('munea.notification.settings.pending.v1') && web.includes('這支手機已更新；雲端尚未同步'), 'Failed backend saves must remain queued and visible instead of reporting false success');
assert(!web.includes("if (items.length && status.status === 'not_determined')"), 'Notification permission must only be requested by the master switch');
assert(!web.includes('sendTestNotification') && !web.includes('notificationTestAction') && !web.includes('傳送測試通知'), 'Production web bundle must not contain any test-notification action (2026-07-16 Edward)');
assert(web.includes('resumePermissionSync') && web.includes('visibilitychange'), 'Returning from iOS Settings must re-check permission and auto-complete the pending enable');
assert(web.includes('munea.notification.enableIntent.v1'), 'The enable intent must survive the round-trip to iOS Settings');
assert(web.includes("action: 'unregister'"), 'Notification bridge must support device unregister');
assert(auth.includes('unregisterBeforeSignOut'), 'Sign-out must detach the current APNs device before the session is cleared');
assert(web.includes('munea://medications') && web.includes('munea://visits') && web.includes('munea://relay'), 'Required deep links must be routed');
assert(!web.includes('munea.notification.showSensitive') && web.includes('showSensitiveContent: false'), 'Lock-screen privacy must be fixed on with no user bypass');
assert(web.includes('durationDays') && web.includes('endDate'), 'Finite medication schedules must stop at their treatment end');
for (const legacySlot of ['早餐後', '午餐後', '晚餐後', '睡前']) {
  assert(web.includes(`'${legacySlot}':`), `${legacySlot} must remain a legacy schedule identity`);
}
for (const key of [
  'notification.publicTitle',
  'notification.publicBody',
  'notification.medicationDueTitle',
  'notification.medicationDueBody',
  'notification.familyActivityTitle',
  'notification.clinicTitle',
  'notification.clinicBody',
  'notification.enabled',
  'notification.localEnabledCloudPending',
  'notification.allowInSettings',
  'notification.updated',
  'notification.localUpdatedCloudPending',
  'notification.medicationMissed',
  'notification.familyRelay',
  'notification.familyInvitation',
  'notification.familyActivity',
  'notification.loading',
  'notification.signInRequired',
  'notification.emptyDetail',
]) {
  assert(web.includes(`'${key}'`), `Notification UI must localize ${key}`);
}
assert(
  web.includes("new Intl.DateTimeFormat(locale"),
  'Notification inbox timestamps must follow the current App language',
);

// 2026-11-08 補（push_registration_zero 調查）：push_devices 與 notification_deliveries
// 正式庫 0 筆、Cloud Run 60 天日誌對 /push/devices 零打進——真因是整條註冊流程完全沒有
// 任何診斷麵包屑，連「失敗」跟「從沒試過」都分不清楚。鎖住這次補的回報路徑，避免被日後
// 改動悄悄砍掉而又變回全黑箱。
assert(web.includes('function reportPushDiagnostic'), 'Push bridge must have a diagnostic reporter so registration attempts are observable in product_events');
assert(web.includes("reportPushDiagnostic('push_registration_error'"), 'A failed native APNs registration must be reported, not only dispatched into an uncaught CustomEvent');
assert(web.includes("reportPushDiagnostic('push_permission_result'"), 'The permission prompt outcome (granted/denied) must be reported');
assert(web.includes("reportPushDiagnostic('push_permission_request_failed'"), 'A thrown/rejected permission request must be caught and reported, not left as an unhandled rejection inside changeNotificationSetting()');
assert(web.includes("reportPushDiagnostic('push_registered'"), 'A successful /push/devices registration must be reported');
assert(web.includes("reportPushDiagnostic('push_register_failed'"), 'A failed /push/devices registration (null/erroring server response) must be reported');
assert(
  /async function requestPermission[\s\S]*?try \{[\s\S]*?await native\.requestPermission\(\)[\s\S]*?\} catch \(e\) \{/.test(web),
  'requestPermission() must not let native.requestPermission() rejections escape as an unhandled promise rejection'
);

// 2026-11-09 Edward 拍板 A 案：通知權限改成「需要時才問」——第一次成功建立吃藥提醒之後
// 才用一句人話問要不要開通知，不在開 App 就先問。
assert(web.includes('async function askInContext(reasonKey)'), 'A shared ask-in-context entry point must exist so other features (e.g. emergency contacts) can trigger it');
assert(web.includes('askInContext: askInContext'), 'askInContext must be exposed on window.MuneaNotify for other scripts to call');
assert(web.includes("if (!plugin()) return;") && web.includes('askInContext'), 'Android/web without the native plugin must end askInContext quietly, with no card shown');
assert(web.includes('if (notificationMasterOn()) return;'), 'Already-enabled devices must not be asked again');
assert(web.includes("_permission.status === 'denied'") && web.includes('notification.askInContext.deniedHint'), 'A denied iOS permission must fall back to a gentle hint instead of the explanation card');
assert(web.includes('ASK_IN_CONTEXT_THROTTLE_MS') && web.includes('7 * 24 * 60 * 60 * 1000'), 'A declined (or hinted) reason must stay quiet for 7 days before asking again');
assert(web.includes("ensureAskInContextModal") && web.includes("pushAskAccept") && web.includes("pushAskDecline"), 'The in-context ask must reuse the App modal-mask/modal-btn styling, not a new bespoke UI');
for (const key of [
  'notification.askInContext.title',
  'notification.askInContext.medicationBody',
  'notification.askInContext.clinicBody',
  'notification.askInContext.safetyContactBody',
  'notification.askInContext.defaultBody',
  'notification.askInContext.accept',
  'notification.askInContext.decline',
  'notification.askInContext.deniedHint',
]) {
  assert(web.includes(`'${key}'`), `In-context notification ask must localize ${key}`);
}
const appWeb = fs.readFileSync('web/src/app.js', 'utf8');
assert(appWeb.includes("window.MuneaNotify.askInContext('medication')"), 'The first successful medication reminder must trigger the in-context notification ask');
assert(appWeb.includes("window.MuneaNotify.askInContext('clinic')"), 'A successful clinic-visit reminder must also trigger the in-context notification ask');
assert(appWeb.includes('window.__muneaToast = toast;'), 'app.js must expose its toast() so notify.js (a separate, non-module script) can reuse the same gentle-hint UI');

console.log('Notification platform native/web contract: ALL PASS');
