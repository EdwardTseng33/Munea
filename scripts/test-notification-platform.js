const assert = require('assert');
const fs = require('fs');

const swift = fs.readFileSync('ios/App/App/NotifyPlugin.swift', 'utf8');
const delegate = fs.readFileSync('ios/App/App/AppDelegate.swift', 'utf8');
const entitlements = fs.readFileSync('ios/App/App/App.entitlements', 'utf8');
const project = fs.readFileSync('ios/App/App.xcodeproj/project.pbxproj', 'utf8');
const web = fs.readFileSync('web/src/notify.js', 'utf8');
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
assert(web.includes("api('/notifications'"), 'Web bridge must mark opened notifications in the durable inbox');
assert(web.includes('notificationInboxModal') && web.includes('openNotificationInbox'), 'App must expose a durable notification inbox');
assert(web.includes("action: 'unregister'"), 'Notification bridge must support device unregister');
assert(auth.includes('unregisterBeforeSignOut'), 'Sign-out must detach the current APNs device before the session is cleared');
assert(web.includes('munea://medications') && web.includes('munea://visits') && web.includes('munea://relay'), 'Required deep links must be routed');
assert(web.includes('munea.notification.showSensitive'), 'Lock-screen details must be opt-in');
assert(web.includes('durationDays') && web.includes('endDate'), 'Finite medication schedules must stop at their treatment end');

console.log('Notification platform native/web contract: ALL PASS');
