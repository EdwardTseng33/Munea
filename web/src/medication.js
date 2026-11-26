/* Munea medication adherence service.
   Reminder definitions stay in munea.meds / routine_reminders; this service owns
   each scheduled dose occurrence so Home, Status and notification actions share
   one durable record. */
(function (global) {
  'use strict';

  const STORE_PREFIX = 'munea.medicationDoses.v1.';
  const LEGACY_PREFIX = 'munea.medDone.';
  const MIGRATION_PREFIX = 'munea.medicationDoses.migrated.v1.';
  const LEGACY_GENERIC_MEDICATION_NAME = '藥';
  const VALID_STATUS = new Set(['scheduled', 'taken', 'snoozed', 'skipped', 'missed']);
  // 上次登入的人用的是哪一份用藥紀錄（只記分區名，不記藥名或紀錄）。2026-11-26 Edward：
  // 「狀態頁一點進去先是舊的樣子，過幾秒才換成新的」——開 App 時登入要幾秒才確認，這幾秒原本讀的是
  // 「訪客」那一份，用藥卡先寫「尚未服用」再跳成「都完成了」。現在這幾秒先讀上次那個人的。
  // 只讀不送：post 要等 configure() 接上才有。確認其實沒登入時 app.js 會換回訪客；
  // 登出／換帳號時 app.js 的帳號清理（munea. 開頭全清）會連這把鑰匙一起清掉，下一個人看不到。
  const LAST_SCOPE_KEY = 'munea.medicationScope.last.v1';
  function rememberedScope() {
    try { return localStorage.getItem(LAST_SCOPE_KEY) || 'guest'; } catch (e) { return 'guest'; }
  }
  let scope = rememberedScope();
  let post = null;
  let medsProvider = () => [];
  let configured = false;
  let syncPromise = Promise.resolve();

  function t(key, fallback) {
    return global.MuneaI18n
      ? global.MuneaI18n.t(key, null, fallback)
      : fallback;
  }

  function localizedFallback(key, fallback) {
    return Object.freeze({
      localized: t(key, fallback),
      fallback,
    });
  }

  function genericMedicationName() {
    return t('medication.genericName', 'Medication');
  }

  function safeScope(value) {
    return encodeURIComponent(String(value || 'guest').trim() || 'guest');
  }

  function dateKey(value) {
    const d = value instanceof Date ? value : (value ? new Date(value + 'T12:00:00') : new Date());
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function storeKey() { return STORE_PREFIX + safeScope(scope); }

  function loadStore() {
    try {
      const value = JSON.parse(localStorage.getItem(storeKey()) || '{}');
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    } catch (e) { return {}; }
  }

  function saveStore(value) {
    try { localStorage.setItem(storeKey(), JSON.stringify(value || {})); } catch (e) {}
  }

  function medIdentity(med) {
    return String((med && (med.id || med.reminderId)) || (med && med.name) || 'medication');
  }

  function medicationStartStore() {
    try {
      const value = JSON.parse(localStorage.getItem('munea.medStartDates.v1') || '{}');
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    } catch (e) { return {}; }
  }

  function scheduledOn(med, day, starts) {
    med = med || {};
    const identity = medIdentity(med) + '|' + String(med.time || '');
    const durationMatch = String(med.days || '').match(/(\d+)/);
    let start = med.startDate || med.start_date || starts[identity];
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(start || ''))) {
      // Legacy long-term medicines predate this field and must keep their history.
      // Finite treatments start when first created unless an explicit date exists.
      start = (durationMatch || med.endDate || med.end_date) ? dateKey() : '2000-01-01';
      starts[identity] = start;
    }
    if (day < start) return false;
    let end = med.endDate || med.end_date || null;
    if (!end) {
      if (durationMatch) {
        const value = new Date(start + 'T12:00:00');
        value.setDate(value.getDate() + Number(durationMatch[1]) - 1);
        end = dateKey(value);
      }
    }
    if (end && day > end) return false;
    const weekdays = Array.isArray(med.weekdays) ? med.weekdays : [];
    if (weekdays.length) {
      const value = new Date(day + 'T12:00:00');
      const jsDay = value.getDay();
      const isoDay = ((jsDay + 6) % 7) + 1;
      const numeric = weekdays.map(Number).filter(Number.isFinite);
      const usesJsDays = numeric.includes(0);
      if (!numeric.includes(usesJsDays ? jsDay : isoDay)) return false;
    }
    return true;
  }

  function doseKey(day, med, slot) {
    return [day, medIdentity(med), String(slot || '').trim()].join('|');
  }

  function slotsFor(meds, day) {
    const out = [];
    const starts = medicationStartStore();
    (Array.isArray(meds) ? meds : []).forEach(med => {
      if (!scheduledOn(med, day, starts)) return;
      String((med && med.time) || '').split('、').forEach(raw => {
        const slot = raw.trim();
        if (!slot) return;
        out.push({
          doseKey: doseKey(day, med, slot),
          legacyKey: slot + '|' + (med.name || LEGACY_GENERIC_MEDICATION_NAME),
          reminderId: med.id || med.reminderId || null,
          medicationName: med.name || genericMedicationName(),
          slot,
          scheduledDate: day,
          photo: med.photo || '',
        });
      });
    });
    try { localStorage.setItem('munea.medStartDates.v1', JSON.stringify(starts)); } catch (e) {}
    const order = [
      localizedFallback('medication.slot.afterBreakfast', '早餐後'),
      localizedFallback('medication.slot.afterLunch', '午餐後'),
      localizedFallback('medication.slot.afterDinner', '晚餐後'),
      localizedFallback('medication.slot.bedtime', '睡前'),
    ];
    const slotOrder = (slot) => order.findIndex(({ fallback, localized }) => (
      slot === fallback || slot === localized
    ));
    out.sort((a, b) => {
      const ai = slotOrder(a.slot), bi = slotOrder(b.slot);
      if (ai === bi) return a.medicationName.localeCompare(b.medicationName, 'zh-Hant');
      return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi);
    });
    return out;
  }

  function normalizeEvent(event) {
    event = event || {};
    const status = VALID_STATUS.has(event.status) ? event.status : 'scheduled';
    return {
      id: event.id || null,
      personId: event.personId || scope,
      reminderId: event.reminderId || null,
      doseKey: String(event.doseKey || ''),
      medicationName: event.medicationName || genericMedicationName(),
      slot: event.slot || '',
      scheduledDate: event.scheduledDate || dateKey(),
      scheduledAt: event.scheduledAt || null,
      expectedCount: Math.max(0, Number(event.expectedCount) || 0),
      status,
      takenAt: status === 'taken' ? (event.takenAt || new Date().toISOString()) : null,
      source: event.source || 'app',
      timezone: event.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Taipei',
      updatedAt: event.updatedAt || new Date().toISOString(),
    };
  }

  function legacyMap(day) {
    try {
      const value = JSON.parse(localStorage.getItem(LEGACY_PREFIX + day) || '{}');
      return value && typeof value === 'object' ? value : {};
    } catch (e) { return {}; }
  }

  function updateLegacy(event) {
    if (!event || !event.scheduledDate) return;
    const map = legacyMap(event.scheduledDate);
    const legacyKey = event.slot + '|' + event.medicationName;
    if (event.status === 'taken') map[legacyKey] = true;
    else delete map[legacyKey];
    try { localStorage.setItem(LEGACY_PREFIX + event.scheduledDate, JSON.stringify(map)); } catch (e) {}
  }

  function emit(event) {
    try { global.dispatchEvent(new CustomEvent('munea:medication-change', { detail: event || {} })); } catch (e) {}
  }

  function ensureDay(meds, dayValue) {
    const day = dateKey(dayValue);
    const doses = slotsFor(meds, day);
    const store = loadStore();
    const legacy = legacyMap(day);
    let changed = false;
    doses.forEach(dose => {
      const current = store[dose.doseKey];
      if (!current) {
        store[dose.doseKey] = normalizeEvent({
          ...dose,
          personId: scope,
          expectedCount: doses.length,
          status: legacy[dose.legacyKey] ? 'taken' : 'scheduled',
          takenAt: legacy[dose.legacyKey] ? new Date(day + 'T12:00:00').toISOString() : null,
          source: legacy[dose.legacyKey] ? 'legacy-import' : 'schedule',
        });
        changed = true;
      } else if (!current.expectedCount) {
        store[dose.doseKey] = normalizeEvent({ ...current, expectedCount: doses.length });
        changed = true;
      }
    });
    if (changed) saveStore(store);
    return doses.map(dose => ({ ...dose, ...(store[dose.doseKey] || {}) }));
  }

  function dayEvents(meds, dayValue) {
    const day = dateKey(dayValue);
    const scheduled = slotsFor(meds, day);
    const store = loadStore();
    const existing = Object.values(store).filter(event => event && event.scheduledDate === day);
    if (day === dateKey() && scheduled.length) return ensureDay(meds, day);
    if (existing.length) return existing;
    if (Object.keys(legacyMap(day)).length && scheduled.length) return ensureDay(meds, day);
    return [];
  }

  function daySummary(dayValue, meds) {
    const day = dateKey(dayValue);
    const events = dayEvents(meds || medsProvider(), day);
    if (!events.length) return null;
    const taken = events.filter(event => event.status === 'taken').length;
    const skipped = events.filter(event => event.status === 'skipped').length;
    const missed = events.filter(event => event.status === 'missed').length;
    const expected = Math.max(events.length, ...events.map(event => Number(event.expectedCount) || 0));
    return {
      day,
      expected,
      taken,
      skipped,
      missed,
      pending: Math.max(0, expected - taken - skipped - missed),
      status: taken >= expected && expected > 0 ? 'full' : (taken > 0 ? 'partial' : (missed > 0 ? 'miss' : 'pending')),
      events,
    };
  }

  function send(event) {
    if (!post || !event || scope === 'guest') return Promise.resolve(null);
    syncPromise = syncPromise.then(() => post({ action: 'save', dose: event })).catch(() => null);
    return syncPromise;
  }

  // 登入還沒確認（configure() 還沒跑）、手上讀的是「上次那個人」那份時，改紀錄的動作（吃了、稍後、略過、取消）
  // 一律先收著，等 configure() 確認現在是誰、拉完雲端之後才寫進「現在這個人」那份。
  // 不可以直接寫：萬一登入其實過期了，這一下就寫進上一個人的紀錄（2026-11-26）。
  // 也不可以直接丟：從通知按「吃了」把 App 叫起來時，動作常常就落在這幾秒裡。
  let pendingWrites = [];
  function holdingForIdentity() { return !configured && scope !== 'guest'; }
  function replayPendingWrites() {
    const queued = pendingWrites;
    pendingWrites = [];
    queued.forEach(item => { try { setStatus(item.dose, item.status, item.source); } catch (e) {} });
  }

  function setStatus(dose, status, source) {
    if (!dose || !dose.doseKey || !VALID_STATUS.has(status)) return null;
    if (holdingForIdentity()) {
      pendingWrites.push({ dose: { ...dose }, status, source });
      return null;
    }
    const store = loadStore();
    if (store[dose.doseKey] && store[dose.doseKey].status === status) return store[dose.doseKey];
    const event = normalizeEvent({
      ...(store[dose.doseKey] || {}),
      ...dose,
      personId: scope,
      status,
      takenAt: status === 'taken' ? new Date().toISOString() : null,
      source: source || 'app',
      updatedAt: new Date().toISOString(),
    });
    store[event.doseKey] = event;
    saveStore(store);
    updateLegacy(event);
    emit(event);
    send(event);
    return event;
  }

  function markNext(meds, source) {
    const events = ensureDay(meds, dateKey());
    const next = events.find(event => event.status !== 'taken' && event.status !== 'skipped');
    return next ? setStatus(next, 'taken', source || 'home') : null;
  }

  function undoLast(meds, source) {
    const events = ensureDay(meds, dateKey()).filter(event => event.status === 'taken');
    const last = events[events.length - 1];
    return last ? setStatus(last, 'scheduled', source || 'undo') : null;
  }

  function toggleNext(meds, source) {
    const summary = daySummary(dateKey(), meds);
    if (summary && summary.expected > 0 && summary.taken >= summary.expected) return undoLast(meds, source || 'status');
    return markNext(meds, source || 'status');
  }

  function findDose(meds, legacyKey, dayValue) {
    return ensureDay(meds, dayValue || dateKey()).find(event => event.legacyKey === legacyKey || (event.slot + '|' + event.medicationName) === legacyKey) || null;
  }

  function mergeRemote(events) {
    if (!Array.isArray(events) || !events.length) return;
    const store = loadStore();
    events.forEach(raw => {
      const event = normalizeEvent(raw);
      if (!event.doseKey) return;
      const local = store[event.doseKey];
      if (!local || local.source === 'schedule' || String(event.updatedAt || '') >= String(local.updatedAt || '')) {
        store[event.doseKey] = event;
        updateLegacy(event);
      }
    });
    saveStore(store);
    emit({ source: 'cloud-refresh' });
  }

  function reconcileMissed() {
    const today = dateKey();
    const store = loadStore();
    const changed = [];
    Object.keys(store).forEach(key => {
      const current = store[key];
      if (!current || current.scheduledDate >= today || !['scheduled', 'snoozed'].includes(current.status)) return;
      const event = normalizeEvent({
        ...current,
        status: 'missed',
        takenAt: null,
        source: 'missed-reconciliation',
        updatedAt: new Date().toISOString(),
      });
      store[key] = event;
      updateLegacy(event);
      changed.push(event);
    });
    if (changed.length) {
      saveStore(store);
      changed.forEach(event => { emit(event); send(event); });
    }
    return changed;
  }

  async function refresh(days) {
    if (!post || scope === 'guest') return [];
    const end = dateKey();
    const startDate = new Date(end + 'T12:00:00');
    startDate.setDate(startDate.getDate() - Math.max(1, Number(days) || 35) + 1);
    const result = await post({ action: 'list', personId: scope, startDate: dateKey(startDate), endDate: end, limit: 1000 });
    const events = result && Array.isArray(result.doses) ? result.doses : [];
    mergeRemote(events);
    return events;
  }

  function migrateLegacy(meds) {
    const marker = MIGRATION_PREFIX + safeScope(scope);
    try { if (localStorage.getItem(marker) === '1') return; } catch (e) {}
    const today = new Date();
    for (let offset = 34; offset >= 0; offset -= 1) {
      const d = new Date(today);
      d.setDate(d.getDate() - offset);
      const day = dateKey(d);
      if (Object.keys(legacyMap(day)).length) ensureDay(meds, day);
    }
    try { localStorage.setItem(marker, '1'); } catch (e) {}
  }

  function configure(options) {
    options = options || {};
    scope = String(options.scope || 'guest');
    try {
      if (scope !== 'guest') localStorage.setItem(LAST_SCOPE_KEY, scope);
      else localStorage.removeItem(LAST_SCOPE_KEY);
    } catch (e) {}
    post = typeof options.post === 'function' ? options.post : null;
    medsProvider = typeof options.meds === 'function' ? options.meds : medsProvider;
    configured = true;
    const meds = medsProvider();
    migrateLegacy(meds);
    ensureDay(meds, dateKey());
    emit({ source: 'configured', scope });
    // Pull first so a stale local "scheduled" record cannot overwrite a dose
    // already marked taken on another device. The final upserts are idempotent.
    return refresh(35).catch(() => []).then(() => {
      reconcileMissed();
      replayPendingWrites();
      const today = ensureDay(medsProvider(), dateKey());
      return Promise.all(today.map(send)).then(() => dayEvents(medsProvider(), dateKey()));
    });
  }

  global.MuneaMedication = {
    configure,
    dateKey,
    slotsFor,
    ensureDay,
    dayEvents,
    daySummary,
    markNext,
    undoLast,
    toggleNext,
    findDose,
    setStatus,
    refresh,
    reconcileMissed,
    configured: () => configured,
    scope: () => scope,
    pendingWrites: () => pendingWrites.length,
  };
})(window);
