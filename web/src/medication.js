/* Munea medication adherence service.
   Reminder definitions stay in munea.meds / routine_reminders; this service owns
   each scheduled dose occurrence so Home, Status and notification actions share
   one durable record. */
(function (global) {
  'use strict';

  const STORE_PREFIX = 'munea.medicationDoses.v1.';
  const LEGACY_PREFIX = 'munea.medDone.';
  const MIGRATION_PREFIX = 'munea.medicationDoses.migrated.v1.';
  const VALID_STATUS = new Set(['scheduled', 'taken', 'snoozed', 'skipped', 'missed']);
  let scope = 'guest';
  let post = null;
  let medsProvider = () => [];
  let configured = false;
  let syncPromise = Promise.resolve();

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

  function doseKey(day, med, slot) {
    return [day, medIdentity(med), String(slot || '').trim()].join('|');
  }

  function slotsFor(meds, day) {
    const out = [];
    (Array.isArray(meds) ? meds : []).forEach(med => {
      String((med && med.time) || '').split('、').forEach(raw => {
        const slot = raw.trim();
        if (!slot) return;
        out.push({
          doseKey: doseKey(day, med, slot),
          legacyKey: slot + '|' + (med.name || '藥'),
          reminderId: med.id || med.reminderId || null,
          medicationName: med.name || '藥',
          slot,
          scheduledDate: day,
          photo: med.photo || '',
        });
      });
    });
    const order = ['早餐後', '午餐後', '晚餐後', '睡前'];
    out.sort((a, b) => {
      const ai = order.indexOf(a.slot), bi = order.indexOf(b.slot);
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
      medicationName: event.medicationName || '藥',
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

  function setStatus(dose, status, source) {
    if (!dose || !dose.doseKey || !VALID_STATUS.has(status)) return null;
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
  };
})(window);
