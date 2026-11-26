// Android 本機提醒（補助案 B2「提醒」流程，2026-11-20）
//
// 鎖住三件事：
//  A. 原生設定：官方 @capacitor/local-notifications 版本對得上 Capacitor 主版本、通知權限與重開機權限在、
//     精準鬧鐘被拿掉、iOS 不會被裝進這個外掛（iOS 照舊用自己的 Notify）。
//  B. notify-android.js 這層轉接：排成什麼樣子（每天的提醒展開 14 天、過去時間不排、隱私遮罩、
//     只取消自己排的、點通知帶得回 deepLink）。用假的外掛跑，不需要模擬器。
//  C. notify.js 真的跑一遍：Android 上 plugin() 拿到轉接層、用藥提醒排得進官方外掛；
//     iOS 上照舊交給 Notify、送出去的項目跟以前一樣（轉接層不插手）。
//
// 由 scripts/test-notification-platform.js 最後呼叫（那支已在 npm run test:launch 裡）。

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

// ---------- A. 原生設定 ----------
const pkg = JSON.parse(read('package.json'));
const lnVersion = pkg.dependencies['@capacitor/local-notifications'];
assert(lnVersion, '@capacitor/local-notifications must be a runtime dependency');
assert(/^\d+\.\d+\.\d+$/.test(lnVersion), 'local-notifications must be pinned to an exact version like the other Capacitor plugins');
const androidMajor = String(pkg.dependencies['@capacitor/android']).replace(/^[^\d]*/, '').split('.')[0];
assert.strictEqual(lnVersion.split('.')[0], androidMajor, 'local-notifications major must match @capacitor/android major');

const manifest = read('android/app/src/main/AndroidManifest.xml');
assert(manifest.includes('android.permission.POST_NOTIFICATIONS'), 'Android 13+ needs POST_NOTIFICATIONS to show reminders');
assert(manifest.includes('android.permission.RECEIVE_BOOT_COMPLETED'), 'Reminders must be restored after reboot');
assert(/SCHEDULE_EXACT_ALARM"\s+tools:node="remove"/.test(manifest), 'Exact-alarm permission must stay removed (Play policy + no settings-page detour for elders)');
assert(manifest.includes('xmlns:tools="http://schemas.android.com/tools"'), 'tools namespace is required for tools:node="remove"');

const mainActivity = read('android/app/src/main/java/net/munea/app/MainActivity.java');
assert(mainActivity.includes('registerPlugin(NotificationSettingsPlugin.class)'), 'The open-notification-settings plugin must be registered');
const settingsPlugin = read('android/app/src/main/java/net/munea/app/NotificationSettingsPlugin.java');
assert(settingsPlugin.includes('@CapacitorPlugin(name = "MuneaNotificationSettings")') && settingsPlugin.includes('ACTION_APP_NOTIFICATION_SETTINGS'), 'Settings plugin must open the App notification settings page');
assert(fs.existsSync(path.join(ROOT, 'android/app/src/main/res/drawable/ic_stat_munea_reminder.xml')), 'Notification small icon drawable must exist');

const capConfig = JSON.parse(read('capacitor.config.json'));
assert.strictEqual(capConfig.plugins.LocalNotifications.smallIcon, 'ic_stat_munea_reminder', 'Notifications must use the bell small icon, not the default info icon');
const iosAllow = capConfig.ios && capConfig.ios.includePlugins;
assert(Array.isArray(iosAllow), 'iOS must use an explicit plugin allowlist');
assert(!iosAllow.includes('@capacitor/local-notifications'), 'local-notifications must NOT be synced into iOS (iOS keeps its own Notify plugin)');
for (const name of Object.keys(pkg.dependencies)) {
  if (!name.startsWith('@capacitor/') || ['@capacitor/core', '@capacitor/android', '@capacitor/local-notifications'].includes(name)) continue;
  assert(iosAllow.includes(name), `${name} must stay in ios.includePlugins so iOS keeps it`);
}
const packageSwift = read('ios/App/CapApp-SPM/Package.swift');
assert(!packageSwift.includes('local-notifications'), 'iOS Package.swift must not contain local-notifications');
const capSettings = read('android/capacitor.settings.gradle');
assert(capSettings.includes("':capacitor-local-notifications'"), 'Android Gradle settings must include the plugin (npx cap sync android)');
assert(read('android/app/capacitor.build.gradle').includes("project(':capacitor-local-notifications')"), 'Android app must depend on the plugin');

const pluginManifestPath = path.join(ROOT, 'node_modules/@capacitor/local-notifications/android/src/main/AndroidManifest.xml');
if (fs.existsSync(pluginManifestPath)) {
  const pluginManifest = fs.readFileSync(pluginManifestPath, 'utf8');
  assert(pluginManifest.includes('LocalNotificationRestoreReceiver') && pluginManifest.includes('android.intent.action.BOOT_COMPLETED'), 'Plugin must ship its boot receiver (reminders survive reboot)');
}

const html = read('web/index.html');
const androidTag = html.indexOf('src/notify-android.js?v=');
const notifyTag = html.indexOf('src/notify.js?v=');
assert(androidTag > 0 && notifyTag > androidTag, 'notify-android.js must load before notify.js');

for (const locale of ['zh-TW', 'en', 'ja', 'es']) {
  const catalog = JSON.parse(read(`web/src/i18n/${locale}.json`));
  for (const key of ['notification.android.channelName', 'notification.android.channelDescription', 'notification.android.denied', 'notification.android.permissionPrompt', 'notification.android.allowInSettings', 'notification.android.deniedHint']) {
    assert(catalog[key] && catalog[key].trim(), `${locale} must translate ${key}`);
    if (key !== 'notification.android.channelDescription') assert(!/iPhone/.test(catalog[key]), `${locale} ${key} must not mention iPhone`);
  }
}

// ---------- 假外掛 ----------
function fakeLocalNotifications(display) {
  const calls = { schedule: [], cancel: [], createChannel: [], listeners: {} };
  let pending = [];
  const plugin = {
    calls,
    setPending(list) { pending = list; },
    async checkPermissions() { return { display }; },
    async requestPermissions() { display = 'granted'; return { display }; },
    async createChannel(channel) { calls.createChannel.push(channel); },
    async getPending() { return { notifications: pending.slice() }; },
    async cancel(arg) { calls.cancel.push(arg); },
    async schedule(arg) {
      calls.schedule.push(arg);
      pending = arg.notifications.map((n) => ({ id: n.id, extra: n.extra, schedule: n.schedule }));
      return { notifications: arg.notifications.map((n) => ({ id: n.id })) };
    },
    async addListener(name, cb) { calls.listeners[name] = cb; return { remove() {} }; },
  };
  return plugin;
}

function loadAdapter(platform, local) {
  const window = { Capacitor: { getPlatform: () => platform, Plugins: { LocalNotifications: local } } };
  vm.runInNewContext(read('web/src/notify-android.js'), { window, Date, Math, Number, String, Array, Promise, Error });
  return window.MuneaAndroidNotify;
}

async function adapterTests() {
  // 只在 Android 生效
  assert.strictEqual(loadAdapter('ios', fakeLocalNotifications('granted')).available(), false, 'Adapter must stay off on iOS');
  assert.strictEqual(loadAdapter('web', fakeLocalNotifications('granted')).available(), false, 'Adapter must stay off in a browser');
  assert.strictEqual(loadAdapter('android', null).available(), false, 'Adapter must stay off when the plugin is missing');

  // 權限字對照（iOS Notify 的同一組欄位）
  const expect = { granted: ['authorized', true], denied: ['denied', false], prompt: ['not_determined', false], 'prompt-with-rationale': ['not_determined', false] };
  for (const [display, [status, granted]] of Object.entries(expect)) {
    const permission = await loadAdapter('android', fakeLocalNotifications(display)).getPermissionStatus();
    assert.strictEqual(permission.status, status, `${display} → ${status}`);
    assert.strictEqual(permission.granted, granted);
  }
  const asking = fakeLocalNotifications('prompt');
  const granted = await loadAdapter('android', asking).requestPermission();
  assert.strictEqual(granted.granted, true, 'requestPermission must go through the plugin and report the result');

  // 排程
  const local = fakeLocalNotifications('granted');
  const adapter = loadAdapter('android', local);
  const now = new Date();
  const later = new Date(now.getTime() + 3 * 60 * 1000);
  const past = new Date(now.getTime() - 60 * 60 * 1000);
  const privacy = { title: '該吃藥了', body: '早餐的藥：脈優。', publicTitle: '沐寧提醒', publicBody: '你的健康提醒到了，解鎖後查看。' };
  const items = [
    Object.assign({ id: 'med-recurring-早餐後', hour: later.getHours(), minute: later.getMinutes(), repeats: true, eventType: 'medication_due', resourceId: '早餐後', deepLink: 'munea://medications/%E6%97%A9' }, privacy),
    Object.assign({ id: 'visit-v1', hour: later.getHours(), minute: later.getMinutes(), year: later.getFullYear(), month: later.getMonth() + 1, day: later.getDate(), eventType: 'clinic_upcoming', deepLink: 'munea://visits/v1' }, privacy),
    Object.assign({ id: 'med-past', hour: past.getHours(), minute: past.getMinutes(), year: past.getFullYear(), month: past.getMonth() + 1, day: past.getDate(), eventType: 'medication_due' }, privacy),
  ];
  local.setPending([
    { id: 999, extra: { source: 'munea.local', key: 'old' } },        // 自己排的舊提醒 → 要取消
    { id: 555, extra: { source: 'someone-else' } },                   // 不是自己排的 → 不能動
  ]);
  const result = await adapter.sync({ items, showSensitiveContent: false });
  const scheduled = local.calls.schedule[0].notifications;
  const recurring = scheduled.filter((n) => n.extra.key.startsWith('med-recurring-早餐後@'));
  assert(recurring.length >= 14 && recurring.length <= 15, `daily reminder must expand to the next 14 days (got ${recurring.length})`);
  assert(scheduled.some((n) => n.extra.key === 'visit-v1'), 'A future one-off reminder must be scheduled');
  assert(!scheduled.some((n) => n.extra.key.startsWith('med-past')), 'A reminder whose time already passed must not be scheduled (the plugin would fire it immediately)');
  const nowMs = Date.now();
  for (const n of scheduled) {
    assert(new Date(n.schedule.at).getTime() > nowMs, 'Every scheduled time must be in the future');
    assert.strictEqual(n.schedule.allowWhileIdle, true, 'Reminders must wake the phone in Doze');
    assert.strictEqual(n.isExactNotification, false, 'Reminders must not ask for exact alarms');
    assert.strictEqual(n.channelId, 'munea-reminders');
    assert.strictEqual(n.title, '沐寧提醒', 'Lock-screen privacy: title must be the public title');
    assert(!n.body.includes('脈優'), 'Lock-screen privacy: medicine names must never be in the notification');
    assert(Number.isInteger(n.id) && n.id > 0, 'Android notification ids must be positive ints');
  }
  assert.strictEqual(new Set(scheduled.map((n) => n.id)).size, scheduled.length, 'Notification ids must be unique');
  for (let i = 1; i < scheduled.length; i++) assert(new Date(scheduled[i - 1].schedule.at) <= new Date(scheduled[i].schedule.at), 'Nearest reminders first');
  assert.deepStrictEqual(local.calls.cancel[0].notifications.map((n) => n.id), [999], 'Only our own stale reminders may be cancelled');
  assert.strictEqual(local.calls.createChannel[0].importance, 4, 'Reminder channel must pop up (high importance)');
  assert.strictEqual(result.platform, 'android');

  // 再排一次：同一批提醒拿到同一組 id、不會被當成舊的取消
  await adapter.sync({ items, showSensitiveContent: false });
  assert.deepStrictEqual(local.calls.schedule[1].notifications.map((n) => n.id), scheduled.map((n) => n.id), 'Re-sync must reuse the same ids');
  assert.strictEqual(local.calls.cancel.length, 1, 'Re-sync of the same items must not cancel anything');

  // 上限
  const many = [];
  for (let i = 0; i < 300; i++) {
    const at = new Date(now.getTime() + (i + 2) * 60 * 60 * 1000);
    many.push(Object.assign({ id: 'act-' + i, hour: at.getHours(), minute: at.getMinutes(), year: at.getFullYear(), month: at.getMonth() + 1, day: at.getDate() }, privacy));
  }
  const capped = await loadAdapter('android', fakeLocalNotifications('granted')).sync({ items: many });
  assert.strictEqual(capped.scheduled, 120, 'Android schedules at most 120 (AlarmManager allows 500 per app)');
  assert.strictEqual(capped.dropped, 180);

  // 點通知 → deepLink 帶回 notify.js
  let opened = null;
  await adapter.addListener('notificationOpened', (data) => { opened = data; });
  local.calls.listeners.localNotificationActionPerformed({ actionId: 'tap', notification: { extra: { source: 'munea.local', deepLink: 'munea://visits/v1', eventType: 'clinic_upcoming' } } });
  assert.strictEqual(opened.deepLink, 'munea://visits/v1', 'Tapping a reminder must route to its screen');
  const token = await adapter.addListener('remoteToken', () => {});
  assert(token && typeof token.remove === 'function', 'Unsupported events must return a no-op handle');
}

// ---------- C. notify.js 真的跑 ----------
function makeStorage(seed) {
  const data = Object.assign({}, seed);
  return {
    getItem: (k) => (Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
  };
}

function runNotify(capacitor) {
  const now = new Date();
  const remind = new Date(now.getTime() + 3 * 60 * 1000);
  const breakfast = new Date(remind.getTime() - 30 * 60 * 1000);   // 早餐後＝早餐時間＋30 分
  const hhmm = (d) => String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  const localStorage = makeStorage({
    'munea.meds': JSON.stringify([{ id: 'm1', name: '脈優 5mg', time: '早餐後' }]),
    'munea.routine': JSON.stringify({ b: hhmm(breakfast) }),
    'munea.notification.settings.v1': JSON.stringify({ pushEnabled: true, categories: { medication: true, clinic: true, family: true, safety: true } }),
  });
  const document = {
    readyState: 'complete',
    getElementById: () => null,
    querySelector: () => null,
    addEventListener: () => {},
    createElement: () => ({ style: {}, dataset: {}, addEventListener() {}, appendChild() {}, setAttribute() {}, querySelector: () => null }),
    body: { appendChild() {} },
  };
  const window = { Capacitor: capacitor, addEventListener: () => {}, dispatchEvent: () => {} };
  const context = { window, document, localStorage, setTimeout, clearTimeout, console, Date, Intl, JSON, Math, Promise, Number, String, Array, Object, Error, CustomEvent: function () {} };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(read('web/src/notify-android.js'), context);
  vm.runInContext(read('web/src/notify.js'), context);
  return window;
}

async function wait(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

async function notifyJsTests() {
  // Android：notify.js → 轉接層 → 官方外掛
  const local = fakeLocalNotifications('granted');
  const androidWindow = runNotify({ getPlatform: () => 'android', isNativePlatform: () => true, Plugins: { LocalNotifications: local } });
  await wait(50);
  assert.strictEqual(androidWindow.MuneaNotify.available(), true, 'notify.js must see a native reminder plugin on Android');
  androidWindow.MuneaNotify.sync();
  await wait(1100);
  assert(local.calls.schedule.length >= 1, 'notify.js sync must reach the Android plugin');
  const meds = local.calls.schedule[local.calls.schedule.length - 1].notifications.filter((n) => n.extra.eventType === 'medication_due');
  assert(meds.length >= 14, 'A daily medication reminder must be scheduled on Android');
  assert(meds[0].extra.deepLink.startsWith('munea://medications/'), 'Medication reminder must open the medication screen');
  assert(meds.every((n) => !n.body.includes('脈優')), 'Medicine name must not leak into the Android notification');

  // iOS：照舊交給 Notify；轉接層就算載入了也不插手
  const iosCalls = [];
  const iosLocal = fakeLocalNotifications('granted');
  const notify = {
    async getPermissionStatus() { return { status: 'authorized', granted: true, canAsk: false, canOpenSettings: false }; },
    async requestPermission() { return { granted: true, status: 'authorized' }; },
    async sync(arg) { iosCalls.push(arg); return { scheduled: arg.items.length, failed: 0, dropped: 0 }; },
    async addListener() { return { remove() {} }; },
    async getPendingLaunchNotification() { return { notification: null }; },
  };
  const iosWindow = runNotify({ getPlatform: () => 'ios', isNativePlatform: () => true, Plugins: { Notify: notify, LocalNotifications: iosLocal } });
  await wait(50);
  iosWindow.MuneaNotify.sync();
  await wait(1100);
  assert(iosCalls.length >= 1, 'iOS must still sync through its own Notify plugin');
  assert.strictEqual(iosLocal.calls.schedule.length, 0, 'iOS must never schedule through local-notifications');
  const item = iosCalls[iosCalls.length - 1].items.find((i) => i.id === 'med-recurring-早餐後');
  assert(item && item.repeats === true && item.publicTitle, 'iOS receives the same recurring item shape as before');
  assert.strictEqual(iosCalls[iosCalls.length - 1].showSensitiveContent, false);
}

module.exports = (async () => {
  await adapterTests();
  await notifyJsTests();
  console.log('Android local notifications (B2 reminders): ALL PASS');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
  throw error;
});
