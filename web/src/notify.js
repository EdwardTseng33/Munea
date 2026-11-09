/* 沐寧通知橋：本機排程、APNs token、權限狀態、通知收件匣與點擊導頁。 */
window.MuneaNotify = (function () {
  'use strict';

  var BRAIN_URL_DEFAULT = 'https://munea-brain-491603544409.asia-east1.run.app';
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

  function t(key, fallback, values) {
    return window.MuneaI18n
      ? window.MuneaI18n.t(key, values || null, fallback)
      : fallback;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

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
      var dev = window.MUNEA_DEV_CONFIG || {};  // 開發包釘測試機（正式包沒這塊設定）
      if (dev.enabled === true && dev.brainUrl) return String(dev.brainUrl).replace(/\/$/, '') + path;
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

  // 推播註冊全程的診斷麵包屑（2026-11-08）：本來 registrationError 事件丟出去
  // 沒人接、也沒有任何一步寫進 product_events，出事完全看不到。這支只負責回報、
  // 絕不拋錯、絕不擋流程——診斷回報失敗也不能連帶讓推播本身失敗。
  function reportPushDiagnostic(eventName, properties) {
    try {
      void api('/product-event', {
        eventName: eventName,
        source: 'push-notify',
        properties: Object.assign({ platform: isNative() ? 'ios' : 'web' }, properties || {})
      });
    } catch (e) {}
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

  // 推播文字裡的時段顯示名（Edward 2026-07-29：不要寫飯前飯後、直接講餐別）。
  // 跟 app.js 的 MED_SLOT_LABEL 同一份意思；這支是獨立載入的小程式、不共用變數所以各留一份。
  function slotLabel(slot) {
    if (slot === '早餐後') return t('medication.slot.afterBreakfast', '早餐');
    if (slot === '午餐後') return t('medication.slot.afterLunch', '中餐');
    if (slot === '晚餐後') return t('medication.slot.afterDinner', '晚餐');
    if (slot === '睡前') return t('medication.slot.bedtime', '睡前');
    return slot;
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
      publicTitle: t('notification.publicTitle', '沐寧提醒'),
      publicBody: t('notification.publicBody', '你的健康提醒到了，解鎖後查看。'),
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
        var name = String(med.name || t('medication.genericName', '藥')).split(/\s+/)[0];
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
        t('notification.medicationDueTitle', '該吃藥了'),
        t('notification.medicationDueBody', '{slot}的藥：{medications}。吃完回沐寧打個勾。', {
          slot: slotLabel(slot),
          medications: group.names.join(t('common.listSeparator', '、'))
        }),
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
        t('notification.medicationDueTitle', '該吃藥了'),
        t('notification.medicationDueBody', '{slot}的藥：{medications}。吃完回沐寧打個勾。', {
          slot: slotLabel(group.slot),
          medications: group.names.join(t('common.listSeparator', '、'))
        }),
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
        t('notification.familyActivityTitle', '{title}快到了', {
          title: activity.title || t('notification.familyDefaultTitle', '家庭聚會')
        }),
        t('notification.familyActivityBody', '再 30 分鐘，別忘了喔。'),
        'family_activity', activity.id, 'munea://family/activities/' + activity.id
      )));
    });
    var visits = [];
    try { visits = JSON.parse(localStorage.getItem('munea.visits')) || []; } catch (e) {}
    if (Array.isArray(visits)) visits.forEach(function (visit) {
      if (!visit || !visit.dateISO) return;
      var visitAt = new Date(visit.dateISO + 'T' + (visit.time || '09:00'));
      // 提前多久由使用者自己選（Edward 2026-08-01）。原本寫死 2 小時
      // （他 2026-07-29 從 1 小時改的：1 小時是該出門的時間了，來不及看摘要）。
      // 舊資料沒有 remindBefore 這個欄位 → 一律當成 120 分，行為不變。
      var lead = Number(visit.remindBefore);
      if (!Number.isFinite(lead) || lead < 0) lead = 120;
      var remindAt = new Date(visitAt.getTime() - lead * 60 * 1000);
      if (isNaN(remindAt) || remindAt <= new Date()) return;
      // 口袋問題：有記下要問醫生的問題，就在看診提醒裡帶一句「有 N 個問題要問」。
      // 只帶**數量**、不帶問題內文——健康疑問屬敏感內容，不放進推播文字（鎖定畫面另有 publicBody 遮罩）。
      var openQ = 0;
      try {
        var qs = JSON.parse(localStorage.getItem('munea.careQuestions')) || [];
        if (Array.isArray(qs)) openQ = qs.filter(function (q) { return q && q.text && !q.askedAt; }).length;
      } catch (e) {}
      var visitBody = t('notification.clinicBody', '等等 {time} 記得帶健保卡。', { time: visit.time || '' });
      if (openQ > 0) {
        visitBody += t('notification.clinicQuestions', '你有 {n} 個問題要問醫生，記得帶著問。', { n: openQ });
      }
      items.push(Object.assign({
        id: 'visit-' + visit.id,
        hour: remindAt.getHours(), minute: remindAt.getMinutes()
      }, dateParts(remindAt), privacyFields(
        t('notification.clinicTitle', '{title}提醒', {
          title: visit.title || t('notification.clinicDefaultTitle', '回診')
        }),
        visitBody,
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
      anchor.parentNode.insertBefore(row, anchor);
    }
    // 標題要包在 <span> 裡，跟設定頁其他列一樣——共用的排版規則是靠
    // 「.sr-main 的第一個 span」找到標題的。這裡原本是裸文字，規則抓不到，
    // 於是只有這一列的標題在外語版會折行（Edward 2026-08-01 連指兩次都還在）。
    row.innerHTML = settingsIcon()
      + '<span class="sr-main"><span>' + escapeHtml(t('notification.centerTitle', '通知中心'))
      + '</span><small>' + escapeHtml(t('notification.centerSubtitle', '選擇這支手機要收到哪些提醒'))
      + '</small></span><span class="sr-arrow"><b id="notificationCenterState"></b> ›</span>';
    if (row.dataset.notificationBound !== '1') {
      row.dataset.notificationBound = '1';
      row.addEventListener('click', function () { void openNotificationSettings(); });
    }
    // 設定頁那一列右邊只放短短的狀態（跟「已連接」「0 種藥」「標準」同一個樣子）。
    // 原本放的是整句「重要提醒會送到這支手機」，把左邊的副標擠成「選擇要在…」，
    // 整列變成一句沒講完的話。完整說明留在點進去的那一頁，不搶這一列的寬度。
    var state = document.getElementById('notificationCenterState');
    if (state) state.textContent = notificationMasterOn()
      ? t('notification.centerStateOn', '已開啟')
      : t('notification.centerStateOff', '已關閉');
  }

  // 通知中心＝全螢幕子頁（7/16 Edward：內容多、不做彈窗）；沿用條款/方案同一套 reader-page 版型
  function ensureNotificationSettings() {
    var page = document.getElementById('notificationSettingsPage');
    if (page) return page;
    page = document.createElement('div');
    page.className = 'reader-page notification-page';
    page.id = 'notificationSettingsPage';
    page.setAttribute('aria-hidden', 'true');
    var centerTitle = escapeHtml(t('notification.centerTitle', '通知中心'));
    var pushTitle = escapeHtml(t('notification.push', 'App 推播通知'));
    var medicationTitle = escapeHtml(t('notification.medication', '用藥提醒'));
    var clinicTitle = escapeHtml(t('notification.clinic', '看診提醒'));
    var familyTitle = escapeHtml(t('notification.family', '家人消息'));
    var safetyTitle = escapeHtml(t('notification.safety', '安全通知'));
    page.innerHTML = '<div class="nav-head"><button class="nav-back" id="notificationSettingsBack" type="button" aria-label="' + escapeHtml(t('common.close', '關閉')) + '"><svg class="ic" viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg></button><span class="nav-title">' + centerTitle + '</span><span></span></div>' +
      '<div class="reader-scroll notification-page-scroll"><p class="notification-page-sub">' + escapeHtml(t('notification.centerSubtitle', '選擇這支手機要收到哪些提醒')) + '</p>' +
      '<div class="notification-setting-list">' +
      '<div class="notification-setting-row notification-master-row"><span><b>' + pushTitle + '</b><small id="notificationPermissionMessage">' + escapeHtml(t('notification.pushOff', '開啟後才會收到提醒')) + '</small></span><button class="notification-switch" type="button" role="switch" data-notification-setting="pushEnabled" aria-label="' + pushTitle + '"><i></i></button></div>' +
      '<p class="notification-setting-heading">' + escapeHtml(t('notification.reminderTypes', '提醒類型')) + '</p>' +
      '<div class="notification-setting-row"><span><b>' + medicationTitle + '</b><small>' + escapeHtml(t('settings.medicationRemindersSubtitle', '到時間通知你，打開就能確認')) + '</small></span><button class="notification-switch" type="button" role="switch" data-notification-setting="medication" aria-label="' + medicationTitle + '"><i></i></button></div>' +
      '<div class="notification-setting-row"><span><b>' + clinicTitle + '</b><small>' + escapeHtml(t('settings.appointmentRemindersSubtitle', '回診前一天提醒你')) + '</small></span><button class="notification-switch" type="button" role="switch" data-notification-setting="clinic" aria-label="' + clinicTitle + '"><i></i></button></div>' +
      '<div class="notification-setting-row"><span><b>' + familyTitle + '</b></span><button class="notification-switch" type="button" role="switch" data-notification-setting="family" aria-label="' + familyTitle + '"><i></i></button></div>' +
      '<div class="notification-setting-row"><span><b>' + safetyTitle + '</b><small>' + escapeHtml(t('settings.safetyNotificationsSubtitle', '同步資料需要留意時，通知你選定的家人。')) + '</small></span><button class="notification-switch" type="button" role="switch" data-notification-setting="safety" aria-label="' + safetyTitle + '"><i></i></button></div>' +
      '<div class="notification-setting-row notification-safety-contacts" id="notificationSafetyContacts" role="button" tabindex="0"><span><b>' + escapeHtml(t('notification.safetyRecipients', '安全通知的通知對象')) + '</b><small id="notificationSafetyContactsState">' + escapeHtml(t('notification.noContacts', '還沒設定緊急聯絡人')) + '</small></span><span class="notification-row-arrow">›</span></div>' +
      '</div>' +
      '<p class="notification-privacy-note">' + escapeHtml(t('notification.privacy', '鎖定畫面不顯示藥名、健康數值或家人訊息內容。')) + '</p>' +
      '<p class="notification-save-state" id="notificationSaveState" aria-live="polite"></p></div>';
    document.body.appendChild(page);
    page.querySelector('#notificationSettingsBack').addEventListener('click', closeNotificationSettings);
    page.addEventListener('click', function (event) {
      var toggle = event.target.closest('[data-notification-setting]');
      if (toggle) { void changeNotificationSetting(toggle.dataset.notificationSetting); return; }
      if (event.target.closest('#notificationSafetyContacts')) openSafetyContacts();
    });
    page.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' && event.target.closest('#notificationSafetyContacts')) openSafetyContacts();
    });
    return page;
  }

  function closeNotificationSettings() {
    var page = document.getElementById('notificationSettingsPage');
    if (!page) return;
    page.classList.remove('show');
    page.setAttribute('aria-hidden', 'true');
  }

  // 「通知對象」＝重用 app.js 既有的緊急聯絡人設定窗（單一名單、單一真相）
  function openSafetyContacts() {
    var row = document.getElementById('safetyRow');
    if (row) row.click();
  }

  // 2026-11-09：名單改存 personId，這裡要對回 munea.circleMembers 的名字才能顯示
  // （跟 app.js 的 safetyContactName() 同一份資料源、各自用自己的 localStorage 讀法，不互相 import）。
  function safetyContactNames() {
    try {
      var ids = JSON.parse(localStorage.getItem('munea.safetyContacts')) || [];
      if (!Array.isArray(ids)) return [];
      var members = [];
      try { members = JSON.parse(localStorage.getItem('munea.circleMembers')) || []; } catch (e2) {}
      if (!Array.isArray(members)) members = [];
      var names = [];
      for (var i = 0; i < ids.length; i++) {
        var pid = ids[i];
        var found = null;
        for (var j = 0; j < members.length; j++) {
          if (members[j] && members[j].personId === pid) { found = members[j]; break; }
        }
        if (found && found.name) names.push(found.name);
      }
      return names;
    } catch (e) { return []; }
  }

  function renderNotificationSettings() {
    var page = document.getElementById('notificationSettingsPage');
    if (!page) return;
    var masterOn = notificationMasterOn();
    page.querySelectorAll('[data-notification-setting]').forEach(function (button) {
      var key = button.dataset.notificationSetting;
      var on = key === 'pushEnabled' ? masterOn : !!_notificationSettings.categories[key];
      button.setAttribute('aria-checked', on ? 'true' : 'false');
      button.classList.toggle('on', on);
      button.disabled = _settingsSaving || (key !== 'pushEnabled' && !masterOn);
    });
    var permissionMessage = page.querySelector('#notificationPermissionMessage');
    if (permissionMessage) {
      permissionMessage.textContent = _permission.status === 'denied'
        ? t('notification.denied', '通知已被 iPhone 設定關閉。請開啟設定後再試一次。')
        : (masterOn
          ? t('notification.pushOn', '重要提醒會送到這支手機')
          : t('notification.permissionPrompt', '開啟時才會詢問 iPhone 通知權限'));
    }
    var contactsState = page.querySelector('#notificationSafetyContactsState');
    if (contactsState) {
      var names = safetyContactNames();
      contactsState.textContent = names.length
        ? names.join(' · ')
        : t('notification.noContacts', '還沒設定緊急聯絡人');
    }
  }

  async function openNotificationSettings() {
    var page = ensureNotificationSettings();
    page.classList.add('show');
    page.setAttribute('aria-hidden', 'false');
    renderNotificationSettings();
    void resumePermissionSync();
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

  // 「想開通知」的意向旗：使用者按了開關但 iPhone 權限還沒給 → 記 30 分鐘；
  // 他去系統設定打開、回到沐寧時（resumePermissionSync）就自動把 App 內的開關接上，不用再按一次。
  var ENABLE_INTENT_KEY = 'munea.notification.enableIntent.v1';
  function setEnableIntent() { try { localStorage.setItem(ENABLE_INTENT_KEY, String(Date.now())); } catch (e) {} }
  function clearEnableIntent() { try { localStorage.removeItem(ENABLE_INTENT_KEY); } catch (e) {} }
  function hasEnableIntent() {
    try {
      var at = Number(localStorage.getItem(ENABLE_INTENT_KEY) || 0);
      return at > 0 && (Date.now() - at) < 30 * 60 * 1000;
    } catch (e) { return false; }
  }

  async function enablePushNow(message) {
    clearEnableIntent();
    var saved = await saveNotificationSettings({ pushEnabled: true });
    var native = plugin();
    if (native && typeof native.registerRemoteNotifications === 'function') {
      try {
        var registration = await native.registerRemoteNotifications();
        if (registration && registration.token) await registerToken(registration);
      } catch (e) {}
    }
    if (message) message.textContent = saved.synced
      ? t('notification.enabled', '通知已開啟')
      : t('notification.localEnabledCloudPending', '這支手機已開啟；雲端尚未同步');
    return saved;
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
        if (enable) {
          if (!_permission.granted && _permission.status !== 'denied') await requestPermission();
          if (!_permission.granted) {
            setEnableIntent();
            if (message) message.textContent = t(
              'notification.allowInSettings',
              '請在 iPhone 設定中允許沐寧通知；回到沐寧會自動開啟'
            );
            await window.MuneaNotify.openSettings();
            return;
          }
          await enablePushNow(message);
        } else {
          clearEnableIntent();
          var saved = await saveNotificationSettings({ pushEnabled: false });
          var deviceSynced = await disableCurrentDevice();
          if (message) message.textContent = saved.synced && deviceSynced
            ? t('notification.updated', '設定已更新')
            : t('notification.localUpdatedCloudPending', '這支手機已更新；雲端尚未同步');
        }
      } else {
        if (!notificationMasterOn() || !Object.prototype.hasOwnProperty.call(_notificationSettings.categories, key)) return;
        var categories = {};
        categories[key] = !_notificationSettings.categories[key];
        var categorySaved = await saveNotificationSettings({ categories: categories });
        if (message) message.textContent = categorySaved.synced
          ? t('notification.updated', '設定已更新')
          : t('notification.localUpdatedCloudPending', '這支手機已更新；雲端尚未同步');
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
      reportPushDiagnostic('push_registered', { environment: data.environment || 'production' });
    } else {
      // 2026-11-08 補：以前這裡完全沒有回報——伺服器拒絕（401/403/驗證失敗）或
      // api() 因為拿不到登入 token／逾時直接回 null，兩種情況在 product_events
      // 裡長得一樣：什麼都沒有。現在至少留一筆「試過、但沒成功」。
      reportPushDiagnostic('push_register_failed', { error: (result && result.error) || 'no_response' });
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
      // 就診推播點開＝直接看摘要（Edward 2026-07-29：跟就診提醒連動）。
      // 他今天要出門看診，需要的是「這次要問什麼」，不是一張提醒設定清單。
      if (typeof window.__muneaOpenVisitSummary === 'function') {
        window.__muneaOpenVisitSummary('notification');
      } else {
        clickView('settings');
        setTimeout(function () { var entry = document.getElementById('visitEntry'); if (entry) entry.click(); }, 120);
      }
    } else if (value.indexOf('munea://relay') === 0) clickView('chat');
    else if (value.indexOf('munea://family') === 0 || value.indexOf('munea://health') === 0) clickView('family');
    else return false;
    return true;
  }

  function notificationTypeLabel(type) {
    var labels = {
      medication_due: t('notification.medication', '用藥提醒'),
      medication_missed: t('notification.medicationMissed', '漏服提醒'),
      clinic_upcoming: t('notification.clinic', '看診提醒'),
      family_relay: t('notification.familyRelay', '家人傳話'),
      family_invitation: t('notification.familyInvitation', '家庭邀請'),
      family_activity: t('notification.familyActivity', '家庭活動'),
      health_alert: t('notification.health', '健康通知')
    };
    return labels[type] || t('notification.care', '照護通知');
  }

  function notificationTimeLabel(value) {
    if (!value) return '';
    var date = new Date(value);
    if (isNaN(date)) return '';
    var locale = (window.MuneaI18n && window.MuneaI18n.current()) || 'zh-TW';
    try { return new Intl.DateTimeFormat(locale, { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date); }
    catch (e) { return date.toLocaleString(); }
  }

  function ensureNotificationInbox() {
    var mask = document.getElementById('notificationInboxModal');
    if (mask) return mask;
    mask = document.createElement('div');
    mask.className = 'modal-mask';
    mask.id = 'notificationInboxModal';
    mask.setAttribute('aria-hidden', 'true');
    mask.innerHTML = '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="notificationInboxTitle"><div class="modal-grab"></div><div class="auth-modal-head"><div><h2 id="notificationInboxTitle">'
      + escapeHtml(t('notification.centerTitle', '通知中心'))
      + '</h2><p class="modal-sub">' + escapeHtml(t('notification.inboxSubtitle', '推播沒有送達時，重要事件仍會保留在這裡。'))
      + '</p></div><button class="auth-close" id="notificationInboxClose" type="button" aria-label="'
      + escapeHtml(t('notification.close', '關閉通知中心'))
      + '">×</button></div><div id="notificationInboxList" style="display:grid;gap:10px;padding-bottom:12px"></div></div>';
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
    title.textContent = item.title || t('notification.defaultTitle', '你的照護提醒到了');
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
    list.textContent = t('notification.loading', '正在載入通知…');
    var result = await api('/notifications', { action: 'list', limit: 100 });
    list.textContent = '';
    if (!result || !Array.isArray(result.notifications)) {
      list.textContent = t('notification.signInRequired', '請先登入，或稍後再試一次。');
      return;
    }
    if (!result.notifications.length) {
      list.textContent = t('notification.emptyDetail', '目前沒有通知。新的提醒與家人消息會保留在這裡。');
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
      // 2026-11-08 修：這個事件原本只 dispatch 給網頁內的 CustomEvent，但沒有任何
      // 地方在聽——APNs 註冊失敗（例如 provisioning profile 沒帶 aps-environment、
      // 裝置沒網路）會完全無聲無息。現在同時回報診斷，下次才看得到「失敗」跟
      // 「從沒試過」的差別。
      reportPushDiagnostic('push_registration_error', { message: (data && data.message) || '' });
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
    // 2026-11-08 修：native.requestPermission() 以前沒包 try/catch，一旦 reject
    // 就會變成 changeNotificationSetting() 裡吞不到的 unhandled rejection——使用者
    // 按下開關後畫面什麼都沒發生、也完全查不到原因。現在失敗一律當「沒拿到授權」
    // 處理（回傳現有 _permission），並回報診斷，讓呼叫端走既有的「請去設定開」路。
    try {
      var result = await native.requestPermission();
      _permission = Object.assign(_permission, result || {});
      await refreshPermission();
      reportPushDiagnostic('push_permission_result', { status: _permission.status, granted: !!_permission.granted });
      if (_permission.granted && typeof native.registerRemoteNotifications === 'function') {
        var registration = await native.registerRemoteNotifications();
        if (registration && registration.token) await registerToken(registration);
      }
    } catch (e) {
      reportPushDiagnostic('push_permission_request_failed', { message: String((e && e.message) || e || '') });
    }
    return _permission;
  }

  // 回到前景就跟 iPhone 對一次權限帳：系統設定剛開了通知＋剛才有「想開」意向 → 自動接上，不用再按一次
  var _resumeSyncBusy = false;
  async function resumePermissionSync() {
    if (_resumeSyncBusy || !plugin()) return;
    _resumeSyncBusy = true;
    try {
      var status = await refreshPermission();
      if (status.granted && !_notificationSettings.pushEnabled && hasEnableIntent()) {
        await enablePushNow(document.getElementById('notificationSaveState'));
        sync();
      }
      renderSettingsRows();
      renderNotificationSettings();
    } finally { _resumeSyncBusy = false; }
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
  window.addEventListener('munea:locale-ready', function () {
    renderSettingsRows();
    renderNotificationSettings();
  });
  function bootWhenReady() {
    restoreNotificationSettings();
    renderSettingsRows();
    // App 從系統設定回來（或從背景回前景）→ 重新對一次 iPhone 權限帳
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') void resumePermissionSync();
    });
    try {
      var appPlugin = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.App;
      if (appPlugin && typeof appPlugin.addListener === 'function') appPlugin.addListener('resume', function () { void resumePermissionSync(); });
    } catch (e) {}
    if (_pendingOpen) void handleOpen(_pendingOpen);
    void boot();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootWhenReady);
  else setTimeout(bootWhenReady, 0);

  // ===== 場景化通知邀請：需要時才問（2026-11-09 Edward 拍板 A 案） =====
  // 背景：推播預設關、只有使用者自己到「設定→通知中心」打開總開關才會跳 iPhone 授權視窗——
  // 結果正式環境 0 台裝置登記，吃藥提醒推播、家人消息全都送不到。改成在「剛做完一件看得懂
  // 為什麼要開通知」的當下才問：先出一張 App 自己的說明卡（不是系統視窗），按「好」才真的去
  // 跑系統授權流程；按「先不要」同一個理由 7 天內不再問；iOS 已經 denied 就不再跳說明卡，
  // 改成溫和提示可以去系統設定開。Android／瀏覽器沒有這支原生外掛（iOS-only），直接安靜結束。
  var ASK_IN_CONTEXT_THROTTLE_PREFIX = 'munea.notification.askInContext.';
  var ASK_IN_CONTEXT_THROTTLE_MS = 7 * 24 * 60 * 60 * 1000;
  function askInContextThrottled(reasonKey) {
    try {
      var at = Number(localStorage.getItem(ASK_IN_CONTEXT_THROTTLE_PREFIX + reasonKey) || 0);
      return at > 0 && (Date.now() - at) < ASK_IN_CONTEXT_THROTTLE_MS;
    } catch (e) { return false; }
  }
  function setAskInContextThrottle(reasonKey) {
    try { localStorage.setItem(ASK_IN_CONTEXT_THROTTLE_PREFIX + reasonKey, String(Date.now())); } catch (e) {}
  }

  // reasonKey → 說明卡那句「為什麼要開」。另一位同事做緊急聯絡人功能時會呼叫
  // askInContext('safetyContact')，先把這個理由的文案備好；不認得的 reasonKey 走預設句。
  function askInContextBody(reasonKey) {
    if (reasonKey === 'medication') return t('notification.askInContext.medicationBody', '要在吃藥時間提醒你，需要先打開通知。');
    if (reasonKey === 'clinic') return t('notification.askInContext.clinicBody', '要在回診前提醒你，需要先打開通知。');
    if (reasonKey === 'safetyContact') return t('notification.askInContext.safetyContactBody', '要在需要留意時通知你選定的家人，需要先打開通知。');
    return t('notification.askInContext.defaultBody', '要能提醒你，需要先打開通知。');
  }

  function ensureAskInContextModal() {
    var mask = document.getElementById('pushAskModal');
    if (mask) return mask;
    mask = document.createElement('div');
    mask.className = 'modal-mask';
    mask.id = 'pushAskModal';
    mask.setAttribute('aria-hidden', 'true');
    mask.innerHTML = '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="pushAskTitle">'
      + '<div class="modal-grab"></div>'
      + '<h2 id="pushAskTitle">' + escapeHtml(t('notification.askInContext.title', '開啟通知')) + '</h2>'
      + '<p class="modal-sub" id="pushAskBody"></p>'
      + '<button class="modal-btn" id="pushAskAccept" type="button"></button>'
      + '<button class="modal-btn quiet" id="pushAskDecline" type="button" style="margin-top:10px"></button>'
      + '</div>';
    document.body.appendChild(mask);
    mask.addEventListener('click', function (event) { if (event.target === mask) closeAskInContextModal(); });
    return mask;
  }

  function closeAskInContextModal() {
    var mask = document.getElementById('pushAskModal');
    if (mask) { mask.classList.remove('show'); mask.setAttribute('aria-hidden', 'true'); }
  }

  // 真正開通知：跟「設定→通知中心」手動開總開關走同一條路（saveNotificationSettings／
  // requestPermission／enablePushNow），差別只是觸發時機不同；拿不到授權就記「想開」意向，
  // 使用者之後去 iPhone 設定打開、回到沐寧會自動接上（既有 resumePermissionSync 機制）。
  async function askInContext(reasonKey) {
    if (!plugin()) return;                  // Android／瀏覽器沒有這支原生外掛，安靜結束
    if (notificationMasterOn()) return;      // 已經開了，什麼都不用做
    await refreshPermission();
    if (_permission.status === 'denied') {
      if (askInContextThrottled(reasonKey)) return;
      setAskInContextThrottle(reasonKey);
      reportPushDiagnostic('push_ask_denied_hint_shown', { reason: reasonKey });
      if (typeof window.__muneaToast === 'function') {
        window.__muneaToast(t('notification.askInContext.deniedHint', '通知目前是關閉的，可以到 iPhone 設定裡打開'));
      }
      return;
    }
    if (askInContextThrottled(reasonKey)) return;
    var mask = ensureAskInContextModal();
    var body = mask.querySelector('#pushAskBody');
    var accept = mask.querySelector('#pushAskAccept');
    var decline = mask.querySelector('#pushAskDecline');
    if (body) body.textContent = askInContextBody(reasonKey);
    if (accept) accept.textContent = t('notification.askInContext.accept', '好，開通知');
    if (decline) decline.textContent = t('notification.askInContext.decline', '先不要');
    mask.classList.add('show');
    mask.setAttribute('aria-hidden', 'false');
    reportPushDiagnostic('push_ask_shown', { reason: reasonKey });
    if (accept) accept.onclick = async function () {
      if (accept) accept.onclick = null;
      if (decline) decline.onclick = null;
      closeAskInContextModal();
      reportPushDiagnostic('push_ask_accepted', { reason: reasonKey });
      if (_permission.granted) { await enablePushNow(); return; }
      await requestPermission();
      if (_permission.granted) await enablePushNow();
      else setEnableIntent();
    };
    if (decline) decline.onclick = function () {
      if (accept) accept.onclick = null;
      if (decline) decline.onclick = null;
      closeAskInContextModal();
      setAskInContextThrottle(reasonKey);
      reportPushDiagnostic('push_ask_declined', { reason: reasonKey });
    };
  }

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
    unregisterBeforeSignOut: unregisterBeforeSignOut,
    askInContext: askInContext
  };
})();
