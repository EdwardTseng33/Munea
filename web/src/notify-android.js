/* 沐寧 Android 本機提醒橋（2026-11-20，補助案 B2「提醒」流程）
 *
 * 為什麼有這支：iOS 的本機提醒走 App 自己寫的原生外掛 Notify（ios/App/App/NotifyPlugin.swift），
 * Android 一直沒有對應的東西——App 關著，吃藥／看診提醒不會響。
 * 這支把官方 @capacitor/local-notifications 包成「跟 iOS Notify 一模一樣的介面」
 * （getPermissionStatus／requestPermission／sync／openSettings／getPendingLaunchNotification／addListener），
 * notify.js 只要在 Android 上拿這支當 plugin()，其餘排程邏輯（buildItems、分類開關、隱私遮罩）一行都不用分叉。
 *
 * 只在 Android 原生殼裡生效：iOS 照舊用原生 Notify（這支 available() 回 false），瀏覽器也一樣。
 *
 * 跟 iOS 不一樣、刻意的三件事：
 * 1. 「每天固定時間」的提醒展開成未來 14 天、一天一則的單次提醒。原因：官方外掛的每日重複在第二次之後
 *    改用不會叫醒手機的鬧鐘（螢幕關著要等使用者拿起手機才跳）；單次提醒走「省電模式也會叫醒」的那種。
 *    每次打開 App 都會重排，所以只要 14 天內打開過一次就不會斷。
 * 2. 不用「精準鬧鐘」（SCHEDULE_EXACT_ALARM，已在 AndroidManifest 移除）：提醒可能晚幾分鐘，
 *    但不用把長輩帶去「鬧鐘與提醒」系統設定頁，也不碰 Google Play 精準鬧鐘政策。
 * 3. 已經過去的時間不排（官方外掛遇到過去時間會「立刻補發」，iOS 則是直接不響）。
 */
window.MuneaAndroidNotify = (function () {
  'use strict';

  var CHANNEL_ID = 'munea-reminders';
  var SOURCE = 'munea.local';           // 跟 iOS 的 localPrefix 同一個意思：只動自己排的
  var REPEAT_DAYS = 14;                 // 每天固定的提醒往後展開幾天
  var MAX_SCHEDULED = 120;              // Android 一個 App 最多 500 個鬧鐘，留很大餘裕
  var MIN_LEAD_MS = 30 * 1000;          // 30 秒內就要響的不排，避免被當成「過去時間」立刻補發

  function t(key, fallback, values) {
    return window.MuneaI18n ? window.MuneaI18n.t(key, values || null, fallback) : fallback;
  }

  function capacitor() { return window.Capacitor || null; }

  function platform() {
    try {
      var cap = capacitor();
      return cap && typeof cap.getPlatform === 'function' ? cap.getPlatform() : 'web';
    } catch (e) { return 'web'; }
  }

  function local() {
    var cap = capacitor();
    return (cap && cap.Plugins && cap.Plugins.LocalNotifications) || null;
  }

  function settingsPlugin() {
    var cap = capacitor();
    return (cap && cap.Plugins && cap.Plugins.MuneaNotificationSettings) || null;
  }

  function available() { return platform() === 'android' && !!local(); }

  // 官方外掛的權限字（granted／denied／prompt／prompt-with-rationale）→ iOS Notify 的同一組欄位。
  // Android 13 以上第一次拒絕後是 prompt-with-rationale（系統還願意再問一次），第二次才是 denied。
  function permissionFrom(display) {
    var value = String(display || 'prompt');
    var granted = value === 'granted';
    var denied = value === 'denied';
    return {
      status: granted ? 'authorized' : (denied ? 'denied' : 'not_determined'),
      granted: granted,
      canAsk: !granted && !denied,
      canOpenSettings: !granted,
      platform: 'android'
    };
  }

  async function getPermissionStatus() {
    var plugin = local();
    if (!plugin) return permissionFrom('denied');
    var result = await plugin.checkPermissions();
    return permissionFrom(result && result.display);
  }

  // Android 12 以下沒有通知權限視窗（預設就是開的）；13 以上這裡才會跳系統詢問。
  // 只有 notify.js 的「開通知」動作會呼叫這裡（設定頁總開關、或剛設定好用藥／看診提醒時的說明卡）。
  async function requestPermission() {
    var plugin = local();
    if (!plugin) return permissionFrom('denied');
    var result = await plugin.requestPermissions();
    return permissionFrom(result && result.display);
  }

  async function openSettings() {
    var plugin = settingsPlugin();
    if (!plugin || typeof plugin.open !== 'function') return { opened: false };
    try { return await plugin.open(); } catch (e) { return { opened: false }; }
  }

  // 字串 id → 正整數（Android 通知 id 只收 int）。同一個 id 每次算出來一樣，重排時會覆蓋同一則。
  function numericId(key) {
    var hash = 5381;
    var text = String(key);
    for (var i = 0; i < text.length; i++) hash = ((hash << 5) + hash + text.charCodeAt(i)) | 0;
    return (hash & 0x7fffffff) || 1;
  }

  function dateKey(date) {
    return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
  }

  // 一個 notify.js 項目 → 未來真的要響的時間點（可能 0 個、1 個或展開成多天）。
  // 項目格式跟送給 iOS 的一樣：hour/minute 必有；year/month/day＝某一天；repeats＝每天；weekdays＝每週幾（1=週日）。
  function fireTimes(item, now) {
    var hour = Number(item.hour);
    var minute = Number(item.minute);
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return [];
    var earliest = now + MIN_LEAD_MS;
    var result = [];
    if (item.year && item.month && item.day) {
      var once = new Date(Number(item.year), Number(item.month) - 1, Number(item.day), hour, minute, 0, 0);
      if (once.getTime() > earliest) result.push({ key: String(item.id), at: once.getTime() });
      return result;
    }
    var weekdays = Array.isArray(item.weekdays) ? item.weekdays.map(Number) : null;
    var repeats = !!item.repeats || !!(weekdays && weekdays.length);
    var base = new Date(now);
    for (var offset = 0; offset <= REPEAT_DAYS; offset++) {
      var day = new Date(base.getFullYear(), base.getMonth(), base.getDate() + offset, hour, minute, 0, 0);
      if (day.getTime() <= earliest) continue;
      if (weekdays && weekdays.length && weekdays.indexOf(day.getDay() + 1) === -1) continue;
      result.push({ key: String(item.id) + '@' + dateKey(day), at: day.getTime() });
      if (!repeats) break;               // 沒有日期、也不重複＝下一次那個時間響一次
      if (result.length >= REPEAT_DAYS) break;
    }
    return result;
  }

  function buildNotifications(items, showSensitive, now) {
    var entries = [];
    (Array.isArray(items) ? items : []).forEach(function (item) {
      if (!item || !item.id) return;
      fireTimes(item, now).forEach(function (time) { entries.push({ item: item, key: time.key, at: time.at }); });
    });
    entries.sort(function (a, b) { return a.at - b.at; });
    var candidateCount = entries.length;
    entries = entries.slice(0, MAX_SCHEDULED);
    var usedIds = {};
    var notifications = entries.map(function (entry) {
      var id = numericId(entry.key);
      while (usedIds[id]) id = (id % 0x7ffffffe) + 1;
      usedIds[id] = true;
      var item = entry.item;
      // 跟 iOS 同一條隱私規矩：showSensitiveContent 固定 false → 通知上只寫「沐寧提醒／解鎖後查看」，
      // 不出現藥名、看診內容（notify.js 已經把兩種文字都準備好了）。
      var title = showSensitive ? item.title : item.publicTitle;
      var body = showSensitive ? item.body : item.publicBody;
      return {
        id: id,
        title: title || t('notification.publicTitle', '沐寧提醒'),
        body: body || t('notification.publicBody', '你的健康提醒到了，解鎖後查看。'),
        channelId: CHANNEL_ID,
        schedule: { at: new Date(entry.at), allowWhileIdle: true },
        isExactNotification: false,
        foreground: true,
        autoCancel: true,
        extra: {
          source: SOURCE,
          key: entry.key,
          eventId: item.eventId || '',
          eventType: item.eventType || '',
          resourceId: item.resourceId || '',
          deepLink: item.deepLink || ''
        }
      };
    });
    return { notifications: notifications, dropped: Math.max(0, candidateCount - notifications.length) };
  }

  async function ensureChannel(plugin) {
    if (typeof plugin.createChannel !== 'function') return;
    try {
      await plugin.createChannel({
        id: CHANNEL_ID,
        name: t('notification.android.channelName', '健康提醒'),
        description: t('notification.android.channelDescription', '吃藥、看診與家庭活動的提醒'),
        importance: 4,        // 高：會從螢幕上方跳出來
        visibility: 0,        // 鎖定畫面依系統設定隱藏內容
        vibration: true
      });
    } catch (e) {}
  }

  // 跟 iOS sync 同一個約定：收到「現在應該排著的全部項目」，自己排的舊提醒裡不在清單上的就取消。
  async function sync(options) {
    var plugin = local();
    if (!plugin) throw new Error('LocalNotifications plugin missing');
    var built = buildNotifications(options && options.items, !!(options && options.showSensitiveContent), Date.now());
    await ensureChannel(plugin);
    var keep = {};
    built.notifications.forEach(function (n) { keep[n.id] = true; });
    var pending = null;
    try { pending = await plugin.getPending(); } catch (e) {}
    var stale = ((pending && pending.notifications) || []).filter(function (n) {
      return n && n.extra && n.extra.source === SOURCE && !keep[n.id];
    }).map(function (n) { return { id: n.id }; });
    if (stale.length) await plugin.cancel({ notifications: stale });
    var scheduled = 0;
    var warning = null;
    if (built.notifications.length) {
      var result = await plugin.schedule({ notifications: built.notifications });
      scheduled = (result && result.notifications && result.notifications.length) || built.notifications.length;
      warning = (result && result.warning) || null;
    }
    return { scheduled: scheduled, failed: 0, dropped: built.dropped, cancelled: stale.length, warning: warning, platform: 'android' };
  }

  function payloadFrom(event) {
    var notification = (event && event.notification) || event || {};
    var extra = notification.extra || {};
    var payload = { source: 'local', platform: 'android' };
    ['eventId', 'eventType', 'resourceId', 'deepLink'].forEach(function (key) {
      if (extra[key]) payload[key] = String(extra[key]);
    });
    return payload;
  }

  // iOS Notify 的事件名 → 官方外掛的事件名。點通知打開 App（含 App 原本關著）用的是
  // localNotificationActionPerformed；外掛會把它留到有人來聽（App 冷啟動時也收得到）。
  // 遠端推播（remoteToken／registrationError）Android 這版還沒有，給一個什麼都不做的把手。
  async function addListener(eventName, callback) {
    var plugin = local();
    var noop = { remove: function () { return Promise.resolve(); } };
    if (!plugin || typeof plugin.addListener !== 'function') return noop;
    if (eventName === 'notificationOpened') {
      return plugin.addListener('localNotificationActionPerformed', function (event) {
        if (event && event.notification && event.notification.extra && event.notification.extra.source !== SOURCE) return;
        callback(payloadFrom(event));
      });
    }
    if (eventName === 'notificationReceived') {
      return plugin.addListener('localNotificationReceived', function (event) { callback(payloadFrom(event)); });
    }
    return noop;
  }

  return {
    available: available,
    getPermissionStatus: getPermissionStatus,
    requestPermission: requestPermission,
    openSettings: openSettings,
    sync: sync,
    addListener: addListener,
    getPendingLaunchNotification: function () { return Promise.resolve({ notification: null }); },
    // 給測試用：不碰原生，只看「會排成什麼樣子」
    _buildNotifications: buildNotifications,
    _fireTimes: fireTimes,
    _numericId: numericId
  };
})();
