const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const values = new Map();
const listeners = new Map();
global.localStorage = {
  getItem: key => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: key => values.delete(key),
};
global.CustomEvent = function (name, options) { this.type = name; this.detail = options.detail; };
global.window = global;
window.addEventListener = (name, handler) => {
  const handlers = listeners.get(name) || [];
  handlers.push(handler);
  listeners.set(name, handlers);
};
window.dispatchEvent = event => (listeners.get(event.type) || []).forEach(handler => handler(event));

vm.runInThisContext(fs.readFileSync('web/src/medication.js', 'utf8'), { filename: 'medication.js' });

const meds = [
  { id: 'med-a', name: '血壓藥', time: '早餐後、晚餐後' },
  { id: 'med-b', name: '維他命', time: '午餐後' },
];

(async () => {
  await MuneaMedication.configure({ scope: 'guest', meds: () => meds });
  const today = MuneaMedication.dateKey();
  let summary = MuneaMedication.daySummary(today, meds);
  assert.deepStrictEqual({ taken: summary.taken, expected: summary.expected }, { taken: 0, expected: 3 });

  MuneaMedication.markNext(meds, 'home');
  summary = MuneaMedication.daySummary(today, meds);
  assert.strictEqual(summary.taken, 1, 'Home action must write the shared dose ledger');

  MuneaMedication.toggleNext(meds, 'status');
  summary = MuneaMedication.daySummary(today, meds);
  assert.strictEqual(summary.taken, 2, 'Status action must update the same dose ledger');

  const third = MuneaMedication.findDose(meds, '晚餐後|血壓藥', today);
  assert(third, 'Notification dose must be addressable by its legacy reminder key');
  MuneaMedication.setStatus(third, 'taken', 'notification');
  summary = MuneaMedication.daySummary(today, meds);
  assert.strictEqual(summary.taken, 3, 'Notification action must complete the same day record');
  assert.strictEqual(summary.status, 'full');

  MuneaMedication.undoLast(meds, 'home-undo');
  summary = MuneaMedication.daySummary(today, meds);
  assert.strictEqual(summary.taken, 2, 'Undo must change the durable occurrence, not only CSS');

  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayKey = MuneaMedication.dateKey(yesterday);
  localStorage.setItem('munea.medDone.' + yesterdayKey, JSON.stringify({ '早餐後|血壓藥': true }));
  localStorage.removeItem('munea.medicationDoses.migrated.v1.guest');
  await MuneaMedication.configure({ scope: 'guest', meds: () => meds });
  const historical = MuneaMedication.daySummary(yesterdayKey, meds);
  assert(historical && historical.taken === 1, 'Medication history must migrate without Apple Health');
  assert.strictEqual(localStorage.getItem('munea.devicesOn'), null, 'Medication history must not require HealthKit state');

  const twoDaysAgo = new Date();
  twoDaysAgo.setDate(twoDaysAgo.getDate() - 2);
  const missedDay = MuneaMedication.dateKey(twoDaysAgo);
  MuneaMedication.ensureDay(meds, missedDay);
  MuneaMedication.reconcileMissed();
  const missed = MuneaMedication.daySummary(missedDay, meds);
  assert.strictEqual(missed.missed, 3, 'Past scheduled doses must reconcile to missed instead of staying pending forever');

  // Isolate the cross-device case from the guest-to-account migration tested above.
  localStorage.removeItem('munea.medDone.' + today);
  const remoteCalls = [];
  const remoteDose = {
    ...MuneaMedication.slotsFor(meds, today)[0],
    personId: 'person-1', expectedCount: 3, status: 'taken', source: 'other-device',
    takenAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
  };
  await MuneaMedication.configure({
    scope: 'person-1',
    meds: () => meds,
    post: async body => {
      remoteCalls.push(body);
      return body.action === 'list' ? { ok: true, doses: [remoteDose] } : { ok: true, dose: body.dose };
    },
  });
  summary = MuneaMedication.daySummary(today, meds);
  assert.strictEqual(summary.taken, 1, 'Cross-device taken state must beat generated local schedule');
  assert(remoteCalls.some(call => call.action === 'list'), 'Signed-in configuration must pull cloud history');
  assert.strictEqual(remoteCalls.filter(call => call.action === 'save' && call.dose.scheduledDate === today).length, 3, 'Every scheduled occurrence must be idempotently upserted');

  const finiteStart = new Date();
  finiteStart.setDate(finiteStart.getDate() - 8);
  const finiteMeds = [{ id: 'finite-med', name: '短期藥', time: '早餐後', days: '7 天', startDate: MuneaMedication.dateKey(finiteStart) }];
  assert.strictEqual(MuneaMedication.slotsFor(finiteMeds, today).length, 0, 'Finite medication must stop producing doses after its treatment end date');

  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowKey = MuneaMedication.dateKey(tomorrow);
  const tomorrowIsoWeekday = ((tomorrow.getDay() + 6) % 7) + 1;
  const weeklyMeds = [{ id: 'weekly-med', name: '每週藥', time: '睡前', weekdays: [tomorrowIsoWeekday] }];
  assert.strictEqual(MuneaMedication.slotsFor(weeklyMeds, tomorrowKey).length, 1, 'Selected weekday must produce a scheduled dose');
  const dayAfter = new Date(tomorrow); dayAfter.setDate(dayAfter.getDate() + 1);
  assert.strictEqual(MuneaMedication.slotsFor(weeklyMeds, MuneaMedication.dateKey(dayAfter)).length, 0, 'Unselected weekday must not produce a dose');

  console.log('Medication service data chain: ALL PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
