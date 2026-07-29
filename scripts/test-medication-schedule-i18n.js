'use strict';

const assert = require('assert');
const fs = require('fs');
const {
  SLOT_IDS,
  displaySlot,
  normalizeDuration,
  normalizeSlot,
  scheduleSlots,
  storagePatch,
} = require('../web/src/i18n/medication-schedule.js');

const catalogs = Object.fromEntries(
  ['zh-TW', 'en', 'ja', 'es'].map((locale) => [
    locale,
    JSON.parse(fs.readFileSync(`web/src/i18n/${locale}.json`, 'utf8')),
  ]),
);
const translator = (locale) => (key, fallback) => catalogs[locale][key] || fallback;

assert.deepEqual(SLOT_IDS, [
  'after-breakfast',
  'after-lunch',
  'after-dinner',
  'bedtime',
]);
assert.equal(normalizeSlot('早餐後'), 'after-breakfast');
assert.equal(normalizeSlot('After Breakfast'), 'after-breakfast');
assert.equal(normalizeSlot('朝食後'), 'after-breakfast');
assert.equal(normalizeSlot('DESPUÉS DEL DESAYUNO'), 'after-breakfast');
assert.equal(normalizeDuration('once'), '1 天');
assert.equal(normalizeDuration('1回'), '1 天');
assert.equal(normalizeDuration('una vez'), '1 天');
assert.equal(normalizeDuration('14 days'), '14 天');
assert.equal(normalizeDuration('30 días'), '30 天');
assert.equal(normalizeSlot('21:30'), null);

assert.deepEqual(
  scheduleSlots({ time: '睡前、早餐後、早餐後、21:30' }).map((slot) => slot.storageValue),
  ['after-breakfast', 'bedtime', '21:30'],
  'Legacy labels must normalize, deduplicate, sort, and retain custom times',
);
assert.deepEqual(
  scheduleSlots({ slotIds: ['bedtime', 'after-lunch'] }).map((slot) => slot.storageValue),
  ['after-lunch', 'bedtime'],
  'Structured slot IDs must be preferred for new records',
);

assert.equal(displaySlot('after-breakfast', translator('zh-TW')), '早餐');
assert.equal(displaySlot('after-breakfast', translator('en')), 'Breakfast');
assert.equal(displaySlot('after-breakfast', translator('ja')), '朝食');
assert.equal(displaySlot('after-breakfast', translator('es')), 'Desayuno');
assert.equal(displaySlot('21:30', translator('en')), '21:30');

assert.deepEqual(
  storagePatch(['Before bed', 'after-breakfast', '21:30']),
  {
    slotIds: ['after-breakfast', 'bedtime'],
    time: '早餐後、睡前、21:30',
  },
  'New forms must dual-write canonical IDs and a legacy Taiwan-compatible time string',
);

console.log('PASS: medication schedule IDs stay stable across App languages');
