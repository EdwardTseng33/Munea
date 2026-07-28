'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const values = new Map();
const translations = Object.fromEntries(
  ['zh-TW', 'en', 'ja', 'es'].map((localeKey) => [
    localeKey,
    JSON.parse(fs.readFileSync(`web/src/i18n/${localeKey}.json`, 'utf8')),
  ]),
);
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
assert.equal(
  profile.templateFor('nening-real-female').templateLabel,
  translations.en['companion.nening.label'],
);
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
  translations.ja['companion.nening.name'],
  'An untouched default name must follow the current App language',
);
assert.equal(
  profile.templateFor('nening-real-female').templateLabel,
  translations.ja['companion.nening.label'],
);

const templateContract = {
  'nening-real-female': ['寧寧', 'companion.nening'],
  'companion-real-male': ['阿宏', 'companion.ahong'],
  'munea-2d-xiaoyun': ['小昀', 'companion.xiaoyun'],
  'munea-2d-ayuan': ['阿原', 'companion.ayuan'],
  'munea-2d-mimi': ['咪咪', 'companion.mimi'],
  'munea-2d-wangcai': ['旺財', 'companion.wangcai'],
};
for (const localeKey of ['zh-TW', 'en', 'ja', 'es']) {
  locale = localeKey;
  for (const [templateId, [backendChar, keyPrefix]] of Object.entries(templateContract)) {
    const template = profile.templateFor(templateId);
    assert.equal(template.backendChar, backendChar, `${templateId} backend identity must not localize`);
    assert.equal(template.defaultName, translations[localeKey][`${keyPrefix}.name`]);
    assert.equal(template.templateLabel, translations[localeKey][`${keyPrefix}.label`]);
  }
}

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
