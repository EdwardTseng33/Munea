'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const values = new Map();
const translations = {
  en: {
    'companion.nening.name': 'Ningning',
    'companion.nening.label': 'Warm companion',
  },
  ja: {
    'companion.nening.name': 'ニンニン',
    'companion.nening.label': 'やさしいコンパニオン',
  },
};
let locale = 'en';
const window = {
  MuneaI18n: {
    t: (key, ignored, fallback) => translations[locale][key] || fallback,
  },
};
const context = {
  console,
  Date,
  JSON,
  localStorage: {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
  },
  window,
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(
  fs.readFileSync('web/src/companion-profile.js', 'utf8'),
  context,
  { filename: 'companion-profile.js' },
);

const profile = window.MuneaCompanionProfile;
assert.equal(profile.templateFor('nening-real-female').backendChar, '寧寧');
assert.equal(profile.templateFor('nening-real-female').defaultName, 'Ningning');
assert.equal(profile.templateFor('nening-real-female').templateLabel, 'Warm companion');
assert(
  Object.values(profile.templates).map((entry) => entry.defaultName).includes('Ningning'),
  'Direct template iteration must also expose localized default names',
);

profile.saveProfile({
  templateId: 'nening-real-female',
  displayName: '寧寧',
  nameTouched: false,
});
assert.equal(profile.loadProfile().displayName, 'Ningning');

locale = 'ja';
assert.equal(
  profile.loadProfile().displayName,
  'ニンニン',
  'An untouched default name must follow the current App language',
);
assert.equal(profile.templateFor('nening-real-female').templateLabel, 'やさしいコンパニオン');

profile.saveProfile({
  templateId: 'nening-real-female',
  displayName: 'My Mimi',
  nameTouched: true,
});
locale = 'en';
assert.equal(
  profile.loadProfile().displayName,
  'My Mimi',
  'A user-customized companion name must survive language changes',
);
assert.equal(profile.loadProfile().nameTouched, true);

console.log('PASS: companion names and labels follow App language without changing backend identity');
