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
// 要守的是「顯示名字來自文案表」，不是「名字剛好等於某三個字」。
// 原本寫死 'Ningning'，2026-08-01 把四國角色改成當地人名（英文 Nina）就整支紅了——
// 紅的原因跟程式對不對無關。這是「守門寫死程式長什麼樣」的第七次。
// 改成跟當下語言的文案表比對：以後改名字不會誤紅，但名字若沒跟著語言走仍會抓到。
assert.equal(profile.templateFor('nening-real-female').backendChar, '寧寧');
assert.equal(
  profile.templateFor('nening-real-female').defaultName,
  translations.en['companion.nening.name'],
  '角色的預設名必須來自文案表，不可以寫死',
);
assert.equal(
  profile.templateFor('nening-real-female').templateLabel,
  translations.en['companion.nening.label'],
);
assert(
  Object.values(profile.templates).map((entry) => entry.defaultName)
    .includes(translations.en['companion.nening.name']),
  'Direct template iteration must also expose localized default names',
);
// 伺服器端的角色識別是中文、顯示名字是當地語言——兩者必須不同，
// 否則代表顯示名字又退回用中文的識別碼了。
assert.notEqual(
  profile.templateFor('nening-real-female').defaultName,
  profile.templateFor('nening-real-female').backendChar,
  '英文版的顯示名字不可以等於伺服器端的中文識別碼',
);

profile.saveProfile({
  templateId: 'nening-real-female',
  displayName: '寧寧',
  nameTouched: false,
});
assert.equal(profile.loadProfile().displayName, translations.en['companion.nening.name']);

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
  'munea-2d-xiaoyun': ['小昀', 'companion.xiaoyun'],
  'munea-2d-mimi': ['咪咪', 'companion.mimi'],
};
// 男生角色全數下線（Edward 2026-09-30）：名單裡不能再有他們
for (const retired of ['companion-real-male', 'munea-2d-ayuan', 'munea-2d-wangcai']) {
  assert.ok(!profile.templates[retired], `${retired} must be removed from the companion roster`);
  assert.equal(profile.normalizeTemplateId(retired), 'nening-real-female', `${retired} must fall back to Ningning`);
}
for (const alias of ['real-m', 'toon-m', 'dog']) {
  assert.equal(profile.normalizeTemplateId(alias), 'nening-real-female', `alias ${alias} must not revive a male companion`);
}
locale = 'en';
{
  // 存的是男生預設名（很多人只是點過輸入框就被標成「自己取的」）→ 改回寧寧，不能變成寧寧的臉叫 Sam
  const migrated = profile.normalizeProfile({ templateId: 'companion-real-male', displayName: 'Sam', nameTouched: true });
  assert.equal(migrated.templateId, 'nening-real-female');
  assert.equal(migrated.nameTouched, false, 'A retired male default name must not count as a custom name');
  assert.equal(migrated.displayName, translations.en['companion.nening.name']);
  const zhDefault = profile.normalizeProfile({ templateId: 'companion-real-male', displayName: '阿宏', nameTouched: true });
  assert.equal(zhDefault.nameTouched, false, 'Retired defaults must be recognised in every language');
  // 真的自己取的名字要保留
  const custom = profile.normalizeProfile({ templateId: 'companion-real-male', displayName: 'Grace', nameTouched: true });
  assert.equal(custom.templateId, 'nening-real-female');
  assert.equal(custom.displayName, 'Grace', 'A genuinely custom name survives the move to Ningning');
  assert.equal(custom.nameTouched, true);
}
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
