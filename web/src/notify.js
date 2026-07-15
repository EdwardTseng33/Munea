/* 沐寧通知橋：本機排程、APNs token、權限狀態、通知收件匣與點擊導頁。 */
window.MuneaNotify = (function () {
  'use strict';

  var BRAIN_URL_DEFAULT = 'https://munea-brain-staging-491603544409.asia-east1.run.app';
  var _syncTimer = null;
  var _listenersReady = false;
  var _permission = { status: 'not_determined', granted: false, canAsk: true, canOpenSettings: false };
  var _lastToken = null;
  var _pendingOpen = null;
  var _lastSync = null;
  var _settingsLoaded = false;
  var _settingsSaving = false;
  var _settingsPending = false;
  var _notificationSettings = {
    pushEnabled: false,
    categories: { medication: true, clinic: true, family: true, safety: true }
  };

  function plugin() {
    return (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Notify) || null;
  }

  function isNative() {
    try { return !!(window.Capacitor && (window.Capacitor.isNativePlatform ? window.Capacitor.isNativePlatform() : true)); }
    catch (e) { return false; }
  }

  function brainUrl(path) {
    try {
      var override = localStorage.getItem('munea.brainUrl');
      if (override) return override.replace(/\/$/, '') + path;
      if (override === '') return path;
      return isNative() ? BRAIN_URL_DEFAULT + path : path;
    } catch (e) { return path; }
  }

  async function api(path, body) {
    var auth = window.MuneaAuth;
    if (!auth || typeof auth.getAccessToken !== 'function') return null;
    var token = await auth.getAccessToken();
    if (!token) return null;
    var headers = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token };
    try { if (typeof MUNEA_APP_KEY === 'string' && MUNEA_APP_KEY) headers['X-Munea-Key'] = MUNEA_APP_KEY; } catch (e) {}
    var controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timeout = controller ? setTimeout(function () { controller.abort(); }, 5000) : null;
    try {
      var options = { method: 'POST', headers: headers, body: JSON.stringify(body || {}) };
      if (controller) options.signal = controller.signal;
      var response = await fetch(brainUrl(path), options);
      return response.ok ? await response.json() : null;
    } catch (e) { return null; }
    finally { if (timeout) clearTimeout(timeout); }
  }

  function normalizeNotificationSettings(value) {
    var source = value && typeof value === 'object' ? value : {};
    var categories = source.categories && typeof source.categories === 'object' ? source.categories : {};
    return {
      pushEnabled: !!source.pushEnabled,
      categories: {
        medication: categories.medication !== false,
        clinic: categories.clinic !== false,
        family: categories.family !== false,
        safety: categories.safety !== false
      }
    };
  }

  function cacheNotificationSettings() {
    try { localStorage.setItem('munea.notification.settings.v1', JSON.stringify(_notificationSettings)); } catch (e) {}
  }

  function setNotificationSettingsPending(pending) {
    _settingsPending = !!pending;
    try {
      if (_settingsPending) localStorage.setItem('munea.notification.settings.pending.v1', '1');
      else localStorage.removeItem('munea.notification.settings.pending.v1');
    } catch (e) {}
  }

  function restoreNotificationSettings() {
    try {
      var cached = JSON.parse(localStorage.getItem('munea.notification.settings.v1') || 'null');
      if (cached) _notificationSettings = normalizeNotificationSettings(cached);
      _settingsPending = localStorage.getItem('munea.notification.settings.pending.v1') === '1';
    } catch (e) {}
  }

  async function loadNotificationSettings() {
    restoreNotificationSettings();
    var result = null;
    if (_settingsPending) {
      result = await api('/notifications/settings', {
        action: 'set', pushEnabled: _notificationSettings.pushEnabled,
        categories: _notificationSettings.categories
      });
      if (result && result.settings) setNotificationSettingsPending(false);
    } else {
      result = await api('/notifications/settings', { action: 'get' });
    }
    if (result && result.settings) {
      _notificationSettings = normalizeNotificationSettings(result.settings);
      cacheNotificationSettings();
    }
    _settingsLoaded = true;
    renderSettingsRows();
    renderNotificationSettings();
    return _notificationSettings;
  }

  async function saveNotificationSettings(patch) {
    var next = normalizeNotificationSettings({
      pushEnabled: Object.prototype.hasOwnProperty.call(patch || {}, 'pushEnabled') ? patch.pushEnabled : _notificationSettings.pushEnabled,
      categories: Object.assign({}, _notificationSettings.categories, patch && patch.categories || {})
    });
    _notificationSettings = next;
    cacheNotificationSettings();
    renderSettingsRows();
    renderNotificationSettings();
    var result = await api('/notifications/settings', {
      action: 'set', pushEnabled: next.pushEnabled, categories: next.categories
    });
    var synced = !!(result && result.settings);
    setNotificationSettingsPending(!synced);
    if (result && result.settings) {
      _notificationSettings = normalizeNotificationSettings(result.settings);
      cacheNotificationSettings();
      renderSettingsRows();
      renderNotificationSettings();
    }
    return { settings: _notificationSettings, synced: synced };
  }

  function routineTimes() {
    var result = { b: '07:30', l: '12:00', d: '18:00', s: '22:00' };
    try { result = Object.assign(result, JSON.parse(localStorage.getItem('munea.routine') || '{}')); } catch (e) {}
    return result;
  }

  function slotTime(slot) {
    var map = { '早餐後': ['b', 30], '午餐後': ['l', 30], '晚餐後': ['d', 30], '睡前': ['s', -30] };
    var match = map[slot];
    if (!match) return null;
    var parts = String(routineTimes()[match[0]] || '08:00').split(':');
    var minutes = ((+parts[0] || 8) * 60 + (+parts[1] || 0) + match[1] + 1440) % 1440;
    return { hour: Math.floor(minutes / 60), minute: minutes % 60 };
  }

  function localDateKey(date) {
    return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
  }

  function dateParts(date) {
    return { year: date.getFullYear(), month: date.getMonth() + 1, day: date.getDate() };
  }

  function medStartDates() {
    try { return JSON.parse(localStorage.getItem('munea.medStartDates.v1') || '{}') || {}; } catch (e) { return {}; }
  }

  function medKey(med) {
    return String(med.id || med.reminderId || med.name || '藥') + '|' + String(med.time || '');
  }

  function startDateFor(med, starts, finite) {
    var key = medKey(med);
    var value = med.startDate || med.start_date || starts[key];
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) {
      value = finite ? localDateKey(new Date()) : '2000-01-01';
      starts[key] = value;
    }
    return new Date(value + 'T12:00:00');
  }

  function durationDays(med) {
    if (med.endDate || med.end_date) return null;
    var match = String(med.days || '').match(/(7|14|30|90)/);
    return match ? Number(match[1]) : null;
  }

  function privacyFields(detailTitle, detailBody, eventType, resourceId, deepLink) {
    return {
      title: detailTitle,
      body: detailBody,
      publicTitle: '沐寧提醒',
      publicBody: '你的健康提醒到了，解鎖後查看。',
      eventType: eventType,
      resourceId: String(resourceId || ''),
      deepLink: deepLink,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Taipei'
    };
  }

  function buildMedicationItems(items) {
    var meds = [];
    try { meds = JSON.parse(localStorage.getItem('munea.meds')) || []; } catch (e) {}
    var starts = medStartDates();
    var recurring = {};
    var finite = {};
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12);
    meds.forEach(function (med) {
      var duration = durationDays(med);
      var explicitEnd = med.endDate || med.end_date;
      var start = startDateFor(med, starts, !!(duration || explicitEnd));
      var end = explicitEnd ? new Date(explicitEnd + 'T12:00:00') : null;
      if (!end && duration) { end = new Date(start); end.setDate(end.getDate() + duration - 1); }
      String(med.time || '').split('、').forEach(function (raw) {
        var slot = raw.trim();
        var timing = slotTime(slot);
        if (!slot || !timing) return;
        var name = String(med.name || '藥').split(/\s+/)[0];
        if (!end) {
          (recurring[slot] = recurring[slot] || { time: timing, names: [] }).names.push(name);
          return;
        }
        var cursor = new Date(start < today ? today : start);
        while (cursor <= end) {
          var dateKey = localDateKey(cursor);
          var key = dateKey + '|' + slot;
          if (!finite[key]) finite[key] = { date: new Date(cursor), slot: slot, time: timing, names: [] };
          finite[key].names.push(name);
          cursor.setDate(cursor.getDate() + 1);
        }
      });
    });
    try { localStorage.setItem('munea.medStartDates.v1', JSON.stringify(starts)); } catch (e) {}
    Object.keys(recurring).forEach(function (slot) {
      var group = recurring[slot];
      items.push(Object.assign({
        id: 'med-recurring-' + slot,
        hour: group.time.hour,
        minute: group.time.minute,
        repeats: true
      }, privacyFields(
        '該吃藥了', slot + '的藥：' + group.names.join('、') + '。吃完回沐寧打個勾。',
        'medication_due', slot, 'munea://medications/' + encodeURIComponent(slot)
      )));
    });
    Object.keys(finite).sort().forEach(function (key) {
      var group = finite[key];
      var parts = dateParts(group.date);
      items.push(Object.assign({
        id: 'med-' + localDateKey(group.date) + '-' + group.slot,
        hour: group.time.hour,
        minute: group.time.minute
      }, parts, privacyFields(
        '該吃藥了', group.slot + '的藥：' + group.names.join('、') + '。吃完回沐寧打個勾。',
        'medication_due', localDateKey(group.date) + '|' + group.slot,
        'munea://medications/' + localDateKey(group.date) + '/' + encodeURIComponent(group.slot)
      )));
    });
  }

  function buildItems() {
    var items = [];
    buildMedicationItems(items);
    var activities = [];
    try { activities = JSON.parse(localStorage.getItem('munea.activities')) || []; } catch (e) {}
    if (Array.isArray(activities)) activities.forEach(function (activity) {
      if (!activity || activity.kind !== 'event' || !activity.dateISO) return;
      var startsAt = new Date(activity.dateISO + 'T' + (activity.time || '18:00'));
      var remindAt = new Date(startsAt.getTime() - 30 * 60 * 1000);
      if (isNaN(remindAt) || remindAt <= new Date()) return;
      items.push(Object.assign({
        id: 'act-' + activity.id,
        hour: remindAt.getHours(), minute: remindAt.getMinutes()
      }, dateParts(remindAt), privacyFields(
        (activity.title || '家庭聚會') + '快到了', '再 30 分鐘，別忘了喔。',
        'family_activity', activity.id, 'munea://family/activities/' + activity.id
      )));
    });
    var visits = [];
    try { visits = JSON.parse(localStorage.getItem('munea.visits')) || []; } catch (e) {}
    if (Array.isArray(visits)) visits.forEach(function (visit) {
      if (!visit || !visit.dateISO) return;
      var visitAt = new Date(visit.dateISO + 'T' + (visit.time || '09:00'));
      var remindAt = new Date(visitAt.getTime() - 60 * 60 * 1000);
      if (isNaN(remindAt) || remindAt <= new Date()) return;
      items.push(Object.assign({
        id: 'visit-' + visit.id,
        hour: remindAt.getHours(), minute: remindAt.getMinutes()
      }, dateParts(remindAt), privacyFields(
        (visit.title || '回診') + '提醒', '等等 ' + (visit.time || '') + '記得帶健保卡。',
        'clinic_upcoming', visit.id, 'munea://visits/' + visit.id
      )));
    });
    return items;
  }

  function notificationCategory(eventType) {
    var categories = {
      medication_due: 'medication', medication_missed: 'medication',
      clinic_upcoming: 'clinic', family_relay: 'family', family_invitation: 'family',
      family_activity: 'family', health_alert: 'safety'
    };
    return categories[String(eventType || '')] || 'family';
  }

  function enabledNotificationItems() {
    if (!_notificationSettings.pushEnabled) return [];
    return buildItems().filter(function (item) {
      return _notificationSettings.categories[notificationCategory(item.eventType)] !== false;
    });
  }

  function emitPermission() {
    try { window.dispatchEvent(new CustomEvent('munea:notification-permission', { detail: Object.assign({}, _permission) })); } catch (e) {}
    renderSettingsRows();
  }

  function settingsIcon() {
    return '<span class="sr-ico"><svg class="ic" viewBox="0 0 24 24"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></svg></span>';
  }

  function removeLegacySettingsRows() {
    ['notificationPermissionRow', 'notificationPrivacyRow', 'notificationTestRow', 'notificationInboxRow'].forEach(function (id) {
      var element = document.getElementById(id);
      if (element) element.remove();
    });
  }

  function notificationMasterOn() {
    return !!(_notificationSettings.pushEnabled && _permission.granted);
  }

  function renderSettingsRows() {
    var anchor = document.getElementById('safetyRow');
    if (!anchor || !anchor.parentNode) return;
    removeLegacySettingsRows();
    anchor.hidden = true;
    anchor.style.display = 'none';
    var row = document.getElementById('notificationCenterRow');
    if (!row) {
      row = document.createElement('div');
      row.className = 'set-row';
      row.id = 'notificationCenterRow';
      row.style.cursor = 'pointer';
      row.innerHTML = settingsIcon() + '<span class="sr-main">通知中心<small>用藥、看診、家人與安全通知</small></span><span class="sr-arrow"><b id="notificationCenterState"></b> ›</span>';
      anchor.parentNode.insertBefore(row, anchor);
      row.addEventListener('click', function () { void openNotificationSettings(); });
    }
    var state = document.getElementById('notificationCenterState');
    if (state) state.textContent = notificationMasterOn() ? '已開啟' : '已關閉';
  }

  function isDevelopmentProfile() {
    return !!(window.MUNEA_DEV_CONFIG && window.MUNEA_DEV_CONFIG.enabled === true);
  }

  function ensureNotificationSettings() {
    var mask = document.getElementById('notificationSettingsModal');
    if (mask) return mask;
    mask = document.createElement('div');
    mask.className = 'modal-mask';
    mask.id = 'notificationSettingsModal';
    mask.setAttribute('aria-hidden', 'true');
    mask.innerHTML = '<div class="modal notification-settings-modal" role="dialog" aria-modal="true" aria-labelledby="notificationSettingsTitle"><div class="modal-grab"></div><div class="auth-modal-head"><div><h2 id="notificationSettingsTitle">通知中心</h2><p class="modal-sub">選擇哪些事情要提醒你</p></div><button class="auth-close" id="notificationSettingsClose" type="button" aria-label="關閉">×</button></div><div class="notification-setting-list"><div class="notification-setting-row notification-master-row"><span><b>App 推播通知</b><small id="notificationPermissionMessage">開啟後才會收到提醒</small></span><button class="notification-switch" type="button" role="switch" data-notification-setting="pushEnabled" aria-label="App 推播通知"><i></i></button></div><p class="notification-setting-heading">提醒類型</p><div class="notification-setting-row"><span><b>用藥提醒</b><small>到時間提醒你查看與確認</small></span><button class="notification-switch" type="button" role="switch" data-notification-setting="medication" aria-label="用藥提醒"><i></i></button></div><div class="notification-setting-row"><span><b>看診提醒</b><small>回診與看診行程提醒</small></span><button class="notification-switch" type="button" role="switch" data-notification-setting="clinic" aria-label="看診提醒"><i></i></button></div><div class="notification-setting-row"><span><b>家人消息</b><small>家人傳話、邀請與家庭活動</small></span><button class="notification-switch" type="button" role="switch" data-notification-setting="family" aria-label="家人消息"><i></i></button></div><div class="notification-setting-row"><span><b>安全通知</b><small>只控制你自己手機；家人守護通知不受影響</small></span><button class="notification-switch" type="button" role="switch" data-notification-setting="safety" aria-label="安全通知"><i></i></button></div></div><p class="notification-privacy-note">鎖定畫面不顯示藥名、健康數值或家人訊息內容。</p><button class="notification-test-action" id="notificationTestAction" type="button" hidden>傳送測試通知</button><p class="notification-save-state" id="notificationSaveState" aria-live="polite"></p></div>';
    document.body.appendChild(mask);
    function close() {
      mask.classList.remove('show');
      mask.setAttribute('aria-hidden', 'true');
    }
    mask.addEventListener('click', function (event) {
      if (event.target === mask) close();
      var toggle = event.target.closest('[data-notification-setting]');
      if (toggle) void changeNotificationSetting(toggle.dataset.notificationSetting);
    });
    mask.querySelector('#notificationSettingsClose').addEventListener('click', close);
    mask.querySelector('#notificationTestAction').addEventListener('click', async function () {
      var label = mask.querySelector('#notificationSaveState');
      if (label) label.textContent = '正在傳送測試通知…';
      var result = await sendTestNotification();
      if (label) label.textContent = result && result.scheduled !== false ? '測試通知已排程' : '測試通知未送出';
    });
    return mask;
  }

  function renderNotificationSettings() {
    var mask = document.getElementById('notificationSettingsModal');
    if (!mask) return;
    var masterOn = notificationMasterOn();
    mask.querySelectorAll('[data-notification-setting]').forEach(function (button) {
      var key = button.dataset.notificationSetting;
      var on = key === 'pushEnabled' ? masterOn : !!_notificationSettings.categories[key];
      button.setAttribute('aria-checked', on ? 'true' : 'false');
      button.classList.toggle('on', on);
      button.disabled = _settingsSaving || (key !== 'pushEnabled' && !masterOn);
    });
    var permissionMessage = mask.querySelector('#notificationPermissionMessage');
    if (permissionMessage) {
      permissionMessage.textContent = _permission.status === 'denied'
        ? '已被 iPhone 關閉，點開關前往系統設定'
        : (masterOn ? '重要提醒會送到這支手機' : '開啟時才會詢問 iPhone 通知權限');
    }
    var testAction = mask.querySelector('#notificationTestAction');
    if (testAction) testAction.hidden = !isDevelopmentProfile();
  }

  async function openNotificationSettings() {
    var mask = ensureNotificationSettings();
    mask.classList.add('show');
    mask.setAttribute('aria-hidden', 'false');
    renderNotificationSettings();
    if (!_settingsLoaded) await loadNotificationSettings();
  }

  async function disableCurrentDevice() {
    var deviceId = null;
    try { deviceId = localStorage.getItem('munea.pushDeviceId'); } catch (e) {}
    if (!deviceId) {
      _lastToken = null;
      return true;
    }
    var result = await api('/push/devices', { action: 'unregister', id: deviceId });
    if (result && result.ok) {
      _lastToken = null;
      try { localStorage.removeItem('munea.pushDeviceId'); } catch (e) {}
      return true;
    }
    return false;
  }

  async function changeNotificationSetting(key) {
    if (_settingsSaving) return;
    _settingsSaving = true;
    renderNotificationSettings();
    var message = document.getElementById('notificationSaveState');
    if (message) message.textContent = '';
    try {
      if (key === 'pushEnabled') {
        var enable = !notificationMasterOn();
        if (enable && _permission.status === 'denied') {
          if (message) message.textContent = '請在 iPhone 設定中允許沐寧通知';
          await window.MuneaNotify.openSettings();
          return;
        }
        if (enable && !_permission.granted) await requestPermission();
        if (enable && !_permission.granted) {
          if (message) message.textContent = '尚未取得通知權限';
          return;
        }
        var saved = await saveNotificationSettings({ pushEnabled: enable });
        var deviceSynced = enable ? true : await disableCurrentDevice();
        if (message) message.textContent = saved.synced && deviceSynced ? '設定已更新' : '這支手機已更新；雲端尚未同步';
      } else {
        if (!notificationMasterOn() || !Object.prototype.hasOwnProperty.call(_notificationSettings.categories, key)) return;
        var categories = {};
        categories[key] = !_notificationSettings.categories[key];
        var categorySaved = await saveNotificationSettings({ categories: categories });
        if (message) message.textContent = categorySaved.synced ? '設定已更新' : '這支手機已更新；雲端尚未同步';
      }
      sync();
    } finally {
      _settingsSaving = false;
      renderSettingsRows();
      renderNotificationSettings();
    }
  }

  async function refreshPermission() {
    var native = plugin();
    if (!native || typeof native.getPermissionStatus !== 'function') return _permission;
    try { _permission = Object.assign(_permission, await native.getPermissionStatus()); } catch (e) {}
    emitPermission();
    return _permission;
  }

  async function registerToken(data) {
    if (!data || !data.token) return null;
    _lastToken = data;
    var status = await refreshPermission();
    var result = await api('/push/devices', {
      action: 'register',
      device: {
        token: data.token,
        environment: data.environment || 'production',
        bundleId: data.bundleId || 'net.munea.app',
        appVersion: data.appVersion || '',
        locale: (window.MuneaI18n && window.MuneaI18n.current()) || 'zh-TW',
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Taipei',
        permissionStatus: status.status,
        notificationsEnabled: !!status.granted,
        showSensitiveContent: false
      }
    });
    if (result && result.device && result.device.id) {
      try { localStorage.setItem('munea.pushDeviceId', result.device.id); } catch (e) {}
    }
    return result;
  }

  async function unregisterBeforeSignOut() {
    var deviceId = null;
    try { deviceId = localStorage.getItem('munea.pushDeviceId'); } catch (e) {}
    if (!deviceId) return { ok: true, skipped: true };
    var result = await api('/push/devices', { action: 'unregister', id: deviceId });
    if (result && result.ok) {
      try { localStorage.removeItem('munea.pushDeviceId'); } catch (e) {}
    }
    return result;
  }

  function clickView(view) {
    var button = document.querySelector('.tab-btn[data-view="' + view + '"]');
    if (button) button.click();
  }

  function routeDeepLink(url) {
    if (!url || String(url).indexOf('munea://') !== 0) return false;
    var value = String(url);
    if (value.indexOf('munea://medications') === 0) clickView('status');
    else if (value.indexOf('munea://visits') === 0) {
      clickView('settings');
      setTimeout(function () { var entry = document.getElementById('visitEntry'); if (entry) entry.click(); }, 120);
    } else if (value.indexOf('munea://relay') === 0) clickView('chat');
    else if (value.indexOf('munea://family') === 0 || value.indexOf('munea://health') === 0) clickView('family');
    else return false;
    return true;
  }

  function notificationTypeLabel(type) {
    var labels = {
      medication_due: '用藥提醒', medication_missed: '漏服提醒', clinic_upcoming: '看診提醒',
      family_relay: '家人傳話', family_invitation: '家庭邀請', family_activity: '家庭活動',
      health_alert: '健康通知'
    };
    return labels[type] || '照護通知';
  }

  function notificationTimeLabel(value) {
    if (!value) return '';
    var date = new Date(value);
    if (isNaN(date)) return '';
    try { return new Intl.DateTimeFormat('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date); }
    catch (e) { return date.toLocaleString(); }
  }

  function ensureNotificationInbox() {
    var mask = document.getElementById('notificationInboxModal');
    if (mask) return mask;
    mask = document.createElement('div');
    mask.className = 'modal-mask';
    mask.id = 'notificationInboxModal';
    mask.setAttribute('aria-hidden', 'true');
    mask.innerHTML = '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="notificationInboxTitle"><div class="modal-grab"></div><div class="auth-modal-head"><div><h2 id="notificationInboxTitle">通知中心</h2><p class="modal-sub">推播沒有送達時，重要事件仍會保留在這裡。</p></div><button class="auth-close" id="notificationInboxClose" type="button" aria-label="關閉">×</button></div><div id="notificationInboxList" style="display:grid;gap:10px;padding-bottom:12px"></div></div>';
    document.body.appendChild(mask);
    function close() {
      mask.classList.remove('show');
      mask.setAttribute('aria-hidden', 'true');
    }
    mask.addEventListener('click', function (event) { if (event.target === mask) close(); });
    mask.querySelector('#notificationInboxClose').addEventListener('click', close);
    return mask;
  }

  function notificationCard(item) {
    var button = document.createElement('button');
    button.type = 'button';
    button.style.cssText = 'width:100%;border:1px solid var(--line);border-radius:18px;background:#fff;padding:14px;text-align:left;color:var(--ink);font:inherit;display:grid;gap:5px;cursor:pointer;opacity:' + (item.readAt ? '.72' : '1');
    var head = document.createElement('span');
    head.style.cssText = 'display:flex;justify-content:space-between;gap:12px;font-size:13px;color:var(--muted)';
    var type = document.createElement('b');
    type.style.color = item.readAt ? 'var(--muted)' : 'var(--teal-d)';
    type.textContent = notificationTypeLabel(item.eventType);
    var time = document.createElement('span');
    time.textContent = notificationTimeLabel(item.createdAt);
    head.appendChild(type);
    head.appendChild(time);
    var title = document.createElement('strong');
    title.style.fontSize = '16px';
    title.textContent = item.title || '你的健康提醒到了';
    var body = document.createElement('span');
    body.style.cssText = 'font-size:14px;line-height:1.5;color:var(--ink-2)';
    body.textContent = item.body || '';
    button.appendChild(head);
    button.appendChild(title);
    button.appendChild(body);
    button.addEventListener('click', async function () {
      await api('/notifications', { action: 'opened', id: item.id });
      ensureNotificationInbox().classList.remove('show');
      routeDeepLink(item.deepLink);
      void refreshNotificationBadge();
    });
    return button;
  }

  async function refreshNotificationBadge() {
    var result = await api('/notifications', { action: 'list', unreadOnly: true, limit: 100 });
    var badge = document.getElementById('notificationUnreadCount');
    var count = result && Number(result.unreadCount || 0);
    if (badge) badge.textContent = count > 0 ? (count > 99 ? '99+' : String(count)) : '';
    return count || 0;
  }

  async function openNotificationInbox() {
    var mask = ensureNotificationInbox();
    var list = mask.querySelector('#notificationInboxList');
    mask.classList.add('show');
    mask.setAttribute('aria-hidden', 'false');
    list.textContent = '正在載入通知…';
    var result = await api('/notifications', { action: 'list', limit: 100 });
    list.textContent = '';
    if (!result || !Array.isArray(result.notifications)) {
      list.textContent = '請先登入，或稍後再試一次。';
      return;
    }
    if (!result.notifications.length) {
      list.textContent = '目前沒有通知。新的提醒與家人消息會保留在這裡。';
      return;
    }
    result.notifications.forEach(function (item) { list.appendChild(notificationCard(item)); });
    var badge = document.getElementById('notificationUnreadCount');
    if (badge) badge.textContent = result.unreadCount ? String(result.unreadCount) : '';
  }

  async function handleOpen(data) {
    _pendingOpen = data || null;
    if (data && data.eventId) await api('/notifications', { action: 'opened', id: data.eventId });
    if (data && data.deepLink && routeDeepLink(data.deepLink)) _pendingOpen = null;
    try { window.dispatchEvent(new CustomEvent('munea:notification-open', { detail: data || {} })); } catch (e) {}
  }

  async function setupListeners() {
    var native = plugin();
    if (!native || _listenersReady || typeof native.addListener !== 'function') return false;
    _listenersReady = true;
    await native.addListener('remoteToken', function (data) { void registerToken(data); });
    await native.addListener('notificationOpened', function (data) { void handleOpen(data); });
    await native.addListener('notificationReceived', function (data) {
      try { window.dispatchEvent(new CustomEvent('munea:notification-received', { detail: data || {} })); } catch (e) {}
    });
    await native.addListener('registrationError', function (data) {
      try { window.dispatchEvent(new CustomEvent('munea:notification-registration-error', { detail: data || {} })); } catch (e) {}
    });
    if (typeof native.getPendingLaunchNotification === 'function') {
      try {
        var pending = await native.getPendingLaunchNotification();
        if (pending && pending.notification) await handleOpen(pending.notification);
      } catch (e) {}
    }
    return true;
  }

  async function requestPermission() {
    var native = plugin();
    if (!native) return _permission;
    var result = await native.requestPermission();
    _permission = Object.assign(_permission, result || {});
    await refreshPermission();
    if (_permission.granted && typeof native.registerRemoteNotifications === 'function') {
      var registration = await native.registerRemoteNotifications();
      if (registration && registration.token) await registerToken(registration);
    }
    return _permission;
  }

  async function sendTestNotification() {
    var native = plugin();
    if (!native) return { scheduled: false, error: 'native_only' };
    var status = await refreshPermission();
    if (!status.granted) status = await requestPermission();
    if (!status.granted || typeof native.scheduleTestNotification !== 'function') return { scheduled: false };
    try {
      var result = await native.scheduleTestNotification();
      _lastSync = result || { scheduled: true };
      renderSettingsRows();
      return result;
    } catch (error) {
      _lastSync = { error: true };
      renderSettingsRows();
      return { scheduled: false, error: String(error && error.message || error) };
    }
  }

  function sync() {
    var native = plugin();
    if (!native) return;
    clearTimeout(_syncTimer);
    _syncTimer = setTimeout(async function () {
      var status = await refreshPermission();
      if (!status.granted) return;
      var items = enabledNotificationItems();
      try {
        _lastSync = await native.sync({
          items: items,
          showSensitiveContent: false
        });
        renderSettingsRows();
        renderNotificationSettings();
      } catch (e) {
        _lastSync = { error: true };
        renderSettingsRows();
        renderNotificationSettings();
      }
    }, 800);
  }

  async function boot() {
    var native = plugin();
    var status = _permission;
    if (native) {
      await setupListeners();
      status = await refreshPermission();
    }
    await loadNotificationSettings();
    if (native) {
      if (_notificationSettings.pushEnabled && status.granted && typeof native.registerRemoteNotifications === 'function') {
        var registration = await native.registerRemoteNotifications();
        if (registration && registration.token) await registerToken(registration);
      }
      sync();
    }
    void refreshNotificationBadge();
    if (_pendingOpen && document.readyState !== 'loading') void handleOpen(_pendingOpen);
  }

  window.addEventListener('munea:auth-state', function (event) {
    if (event.detail && event.detail.status === 'signed-in') {
      if (_notificationSettings.pushEnabled && _lastToken) void registerToken(_lastToken);
      void boot();
    } else {
      var badge = document.getElementById('notificationUnreadCount');
      if (badge) badge.textContent = '';
    }
  });
  function bootWhenReady() {
    restoreNotificationSettings();
    renderSettingsRows();
    if (_pendingOpen) void handleOpen(_pendingOpen);
    void boot();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootWhenReady);
  else setTimeout(bootWhenReady, 0);

  return {
    available: function () { return !!plugin(); },
    boot: boot,
    sync: sync,
    requestPermission: requestPermission,
    permissionStatus: refreshPermission,
    openSettings: function () { var native = plugin(); return native && native.openSettings ? native.openSettings() : Promise.resolve({ opened: false }); },
    openDeepLink: routeDeepLink,
    list: function (options) { return api('/notifications', Object.assign({ action: 'list' }, options || {})); },
    mark: function (id, action) { return api('/notifications', { id: id, action: action || 'read' }); },
    openInbox: openNotificationInbox,
    sendTest: sendTestNotification,
    unregisterBeforeSignOut: unregisterBeforeSignOut
  };
})();
