'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const CATALOG_DIR = path.join(ROOT, 'web', 'src', 'i18n');
const MANIFEST_PATH = path.join(CATALOG_DIR, 'catalog-manifest.json');
const REVIEW_MANIFEST_PATH = path.join(CATALOG_DIR, 'review-manifest.json');

function readText(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

function readJson(filePath) {
  return JSON.parse(readText(filePath));
}

function sorted(values) {
  return [...values].sort();
}

function placeholders(value) {
  return sorted(String(value).match(/\{[A-Za-z][A-Za-z0-9_]*\}/g) || []);
}

const manifest = readJson(MANIFEST_PATH);
const reviewManifest = readJson(REVIEW_MANIFEST_PATH);
assert.equal(manifest.schemaVersion, 1);
assert.equal(manifest.defaultLocale, 'zh-TW');
assert.equal(manifest.fallbackLocale, 'zh-TW');
assert.deepEqual(
  manifest.locales.map(({ locale }) => locale),
  ['zh-TW', 'en', 'ja', 'es'],
);
assert.ok(manifest.releaseGates.includes('voiceE2E'));
assert.ok(manifest.releaseGates.includes('regionalSafetyAndLegal'));
assert.ok(manifest.releaseGates.includes('inAppPurchaseLocalization'));
assert.ok(manifest.releaseGates.includes('marketAvailability'));

const localeEntries = new Map(manifest.locales.map((entry) => [entry.locale, entry]));
const catalogs = new Map();
for (const entry of manifest.locales) {
  assert.match(entry.catalog, /^[A-Za-z-]+\.json$/);
  assert.ok(entry.label, `${entry.locale} label is missing`);
  assert.ok(entry.htmlLang, `${entry.locale} htmlLang is missing`);
  assert.ok(entry.weatherLanguage, `${entry.locale} weatherLanguage is missing`);
  const catalogPath = path.join(CATALOG_DIR, entry.catalog);
  assert.ok(fs.existsSync(catalogPath), `missing catalog: ${entry.catalog}`);
  catalogs.set(entry.locale, readJson(catalogPath));
}

const defaultCatalog = catalogs.get(manifest.defaultLocale);
const defaultKeys = sorted(Object.keys(defaultCatalog));
assert.ok(defaultKeys.length >= 90, 'core catalog must contain at least 90 keys');

for (const [locale, catalog] of catalogs) {
  assert.deepEqual(sorted(Object.keys(catalog)), defaultKeys, `${locale} key set differs`);
  for (const key of defaultKeys) {
    const value = catalog[key];
    assert.equal(typeof value, 'string', `${locale}:${key} must be a string`);
    assert.equal(value, value.trim(), `${locale}:${key} has surrounding whitespace`);
    assert.ok(value.length > 0, `${locale}:${key} is empty`);
    assert.ok(!/<\/?[A-Za-z][^>]*>/.test(value), `${locale}:${key} contains raw HTML`);
    assert.deepEqual(
      placeholders(value),
      placeholders(defaultCatalog[key]),
      `${locale}:${key} placeholder mismatch`,
    );
  }
}

assert.equal(reviewManifest.schemaVersion, 1);
assert.deepEqual(
  Object.keys(reviewManifest.locales),
  manifest.locales.map(({ locale }) => locale),
  'review manifest locales differ from catalog manifest',
);
assert.deepEqual(
  reviewManifest.requiredApprovals,
  [
    'catalogCoverage',
    'nativeLanguageReview',
    'visualQA',
    'voiceE2E',
    'regionalSafetyAndLegal',
    'appStoreMetadata',
    'inAppPurchaseLocalization',
    'marketAvailability',
  ],
);
for (const entry of manifest.locales) {
  const review = reviewManifest.locales[entry.locale];
  assert.ok(review.contentVariant, `${entry.locale} content variant is missing`);
  assert.ok(review.speechVariantPolicy, `${entry.locale} speech policy is missing`);
  for (const gate of reviewManifest.requiredApprovals) {
    assert.ok(review[gate], `${entry.locale}:${gate} review state is missing`);
  }
  // 「進包裡」跟「對外發佈」是兩件事——原本這道守門把它們當成同一件，結果卡成死循環：
  // visualQA 與 voiceE2E 要拿實機逐語系走一遍才生得出證據，可是語系沒進包裡就走不了。
  // 「先給我證據才准進包」→「不進包就生不出證據」，兩邊互相等，永遠過不了。
  //
  // 所以照真實階段拆開（2026-08-01，Edward 拍板三語上架那晚）：
  //   development       語系關著，什麼都不用。
  //   release-candidate 語系進包了，可以打包、可以實機測——但**還沒對外**。
  //                     只要求文案齊全，外加一筆具名放行紀錄（誰、哪天、憑什麼）。
  //   production        對外發佈。八關全部 approved，一關都不能少。
  //
  // 換句話說：把關的位置從「能不能打包」移到「能不能上架」，關卡本身沒有放鬆。
  const stage = entry.status;
  const enabled = entry.runtimeEnabled || entry.binaryLocalizationEnabled;

  if (enabled) {
    assert.ok(
      stage === 'release-candidate' || stage === 'production',
      `${entry.locale} 語系打開了，status 卻是「${stage}」——打開就必須標成 release-candidate（待測）或 production（可對外）`,
    );
  }

  if (stage === 'production') {
    for (const gate of reviewManifest.requiredApprovals) {
      assert.equal(
        review[gate],
        'approved',
        `${entry.locale} 標成可對外發佈，但「${gate}」還沒核准`,
      );
    }
  }

  if (stage === 'release-candidate') {
    assert.equal(
      review.catalogCoverage,
      'approved',
      `${entry.locale} 要進包裡測試，文案必須先齊全（catalogCoverage）`,
    );
    const signoff = review.releaseCandidateSignoff;
    assert.ok(
      signoff && signoff.approvedBy && signoff.approvedAt && signoff.basis,
      `${entry.locale} 標成待測，但沒有具名放行紀錄——releaseCandidateSignoff 要寫明誰、哪一天、憑什麼`,
    );
    assert.ok(
      Array.isArray(signoff.stillPending),
      `${entry.locale} 的放行紀錄要列出還沒過的關卡（stillPending），不能只寫「放行」不寫欠什麼`,
    );
  }
}
assert.equal(
  reviewManifest.locales.es.contentVariant,
  'neutral-international-Spanish',
  'Spanish UI copy must not silently imply a country or safety region',
);

const hanPattern = /[\u3400-\u9fff\uf900-\ufaff]/u;
for (const locale of ['en', 'es']) {
  for (const [key, value] of Object.entries(catalogs.get(locale))) {
    assert.ok(!hanPattern.test(value), `${locale}:${key} unexpectedly contains Han text`);
  }
}

const indexSource = readText(path.join(ROOT, 'web', 'index.html'));
const wiredKeys = [...indexSource.matchAll(/data-i18n="([^"]+)"/g)].map((match) => match[1]);
for (const key of wiredKeys) {
  assert.ok(defaultCatalog[key], `wired data-i18n key missing from catalog: ${key}`);
}

const runtimeSource = readText(path.join(ROOT, 'web', 'src', 'i18n.js'));
const runtimeKeys = [...runtimeSource.matchAll(/'([a-z][a-z0-9]*(?:\.[A-Za-z0-9]+)+)'\s*:/g)]
  .map((match) => match[1]);
for (const key of runtimeKeys) {
  assert.ok(defaultCatalog[key], `current runtime key missing from catalog: ${key}`);
}

const developmentLocales = manifest.locales.filter(({ locale }) => locale !== manifest.defaultLocale);
// 2026-08 語系開放後由 scripts/toggle-locale-release.py 鬆開這三條。
// 原意是防「沒過上架關卡就有人手滑打開語系」；語系正式開放之後，
// 把關的責任交給 scripts/i18n-release-readiness.js（那支是真的在看證據）。
// 要退版關回去：python scripts/toggle-locale-release.py --disable en ja es
// for (const entry of developmentLocales) {
//   assert.equal(entry.status, 'development', `${entry.locale} must stay development-only`);
//   assert.equal(entry.runtimeEnabled, false, `${entry.locale} runtime was enabled before release gates`);
//   assert.equal(
//     entry.binaryLocalizationEnabled,
//     false,
//     `${entry.locale} binary localization was enabled before release gates`,
//   );
// }

const expectedBinaryLocales = sorted(
  manifest.locales
    .filter(({ binaryLocalizationEnabled }) => binaryLocalizationEnabled)
    .map(({ nativeLocale }) => nativeLocale),
);
const infoPlist = readText(path.join(ROOT, 'ios', 'App', 'App', 'Info.plist'));
const requiredUsageDescriptionKeys = [
  'CFBundleDisplayName',
  'NSMicrophoneUsageDescription',
  'NSCameraUsageDescription',
  'NSPhotoLibraryUsageDescription',
  'NSSpeechRecognitionUsageDescription',
  'NSUserNotificationsUsageDescription',
  'NSLocalNetworkUsageDescription',
  'NSHealthShareUsageDescription',
  'NSHealthUpdateUsageDescription',
];
const defaultInfoPlistStrings = readText(path.join(
  ROOT,
  'ios',
  'App',
  'App',
  `${localeEntries.get(manifest.defaultLocale).nativeLocale}.lproj`,
  'InfoPlist.strings',
));
const requiredInfoPlistKeys = sorted(
  [...defaultInfoPlistStrings.matchAll(/^"([^"]+)"\s*=\s*"((?:[^"\\]|\\.)*)";\s*$/gm)]
    .map((match) => match[1]),
);
for (const key of requiredUsageDescriptionKeys) {
  assert.ok(
    requiredInfoPlistKeys.includes(key),
    `default InfoPlist.strings is missing required usage copy: ${key}`,
  );
}
for (const entry of manifest.locales) {
  const stringsPath = path.join(
    ROOT,
    'ios',
    'App',
    'App',
    `${entry.nativeLocale}.lproj`,
    'InfoPlist.strings',
  );
  const stringsSource = readText(stringsPath);
  const localizedValues = new Map(
    [...stringsSource.matchAll(/^"([^"]+)"\s*=\s*"((?:[^"\\]|\\.)*)";\s*$/gm)]
      .map((match) => [match[1], match[2]]),
  );
  assert.deepEqual(
    sorted([...localizedValues.keys()]),
    sorted(requiredInfoPlistKeys),
    `${entry.nativeLocale} InfoPlist.strings key parity differs`,
  );
  for (const key of requiredInfoPlistKeys) {
    assert.ok(localizedValues.get(key).trim(), `${entry.nativeLocale}:${key} must not be empty`);
  }
  if (entry.locale === 'en' || entry.locale === 'es') {
    for (const [key, value] of localizedValues) {
      assert.ok(!hanPattern.test(value), `${entry.nativeLocale}:${key} unexpectedly contains Han text`);
    }
  }
}
const plistBlock = infoPlist.match(
  /<key>CFBundleLocalizations<\/key>\s*<array>([\s\S]*?)<\/array>/,
);
assert.ok(plistBlock, 'CFBundleLocalizations is missing');
const plistLocales = sorted(
  [...plistBlock[1].matchAll(/<string>([^<]+)<\/string>/g)].map((match) => match[1]),
);
assert.deepEqual(plistLocales, expectedBinaryLocales, 'Info.plist binary locales differ from manifest');

const projectSource = readText(
  path.join(ROOT, 'ios', 'App', 'App.xcodeproj', 'project.pbxproj'),
);
const variantGroup = projectSource.match(
  /A1AA0001B2BB0001C3CC0040 \/\* InfoPlist\.strings \*\/ = \{[\s\S]*?children = \(([\s\S]*?)\);[\s\S]*?name = InfoPlist\.strings;/,
);
assert.ok(variantGroup, 'InfoPlist.strings variant group is missing');
const targetLocales = sorted(
  [...variantGroup[1].matchAll(/\/\* ([A-Za-z-]+) \*\//g)].map((match) => match[1]),
);
assert.deepEqual(
  targetLocales,
  expectedBinaryLocales,
  'Xcode target binary locales differ from release manifest',
);

assert.equal(localeEntries.get('zh-TW').status, 'production');
assert.equal(localeEntries.get('zh-TW').runtimeEnabled, true);
console.log(
  `i18n catalogs PASS: ${catalogs.size} locales, ${defaultKeys.length} keys, `
    + `${expectedBinaryLocales.join(',')} binary-enabled`,
);
