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
assert(html.includes('src/notify.js?v=20260715-v1022'), 'Notification UI changes must invalidate the stale WebView script cache');
assert(web.includes("api('/notifications'"), 'Web bridge must mark opened notifications in the durable inbox');
assert(web.includes('notificationInboxModal') && web.includes('openNotificationInbox'), 'App must expose a durable notification inbox');
assert(web.includes("api('/notifications/settings'") && web.includes("action: 'set'"), 'Notification switches must persist through the backend settings API');
assert(web.includes('controller.abort()') && web.includes('}, 5000)'), 'Notification settings API must not hold App startup indefinitely');
assert(web.includes('notificationCenterRow') && web.includes('notificationSettingsModal'), 'Settings must expose one notification-center row and its switch sheet');
for (const category of ['medication', 'clinic', 'family', 'safety']) {
  assert(web.includes(`data-notification-setting=\"${category}\"`), `Notification center must expose the ${category} switch`);
}
assert(web.includes("anchor.hidden = true") && web.includes("anchor.style.display = 'none'"), 'The standalone safety-notification row must be removed from settings');
assert(web.includes('enabledNotificationItems()'), 'Category switches must filter native local schedules too');
assert(web.includes('munea.notification.settings.pending.v1') && web.includes('這支手機已更新；雲端尚未同步'), 'Failed backend saves must remain queued and visible instead of reporting false success');
assert(!web.includes("if (items.length && status.status === 'not_determined')"), 'Notification permission must only be requested by the master switch');
assert(web.includes('isDevelopmentProfile()') && web.includes('testAction.hidden = !isDevelopmentProfile()'), 'Test notifications must stay hidden outside development profiles');
assert(web.includes("action: 'unregister'"), 'Notification bridge must support device unregister');
assert(auth.includes('unregisterBeforeSignOut'), 'Sign-out must detach the current APNs device before the session is cleared');
assert(web.includes('munea://medications') && web.includes('munea://visits') && web.includes('munea://relay'), 'Required deep links must be routed');
assert(!web.includes('munea.notification.showSensitive') && web.includes('showSensitiveContent: false'), 'Lock-screen privacy must be fixed on with no user bypass');
assert(web.includes('durationDays') && web.includes('endDate'), 'Finite medication schedules must stop at their treatment end');

console.log('Notification platform native/web contract: ALL PASS');
