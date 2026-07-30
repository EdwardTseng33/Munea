'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const iosApp = path.join(root, 'ios', 'App', 'App');
const manifest = JSON.parse(
  fs.readFileSync(path.join(root, 'web', 'src', 'i18n', 'catalog-manifest.json'), 'utf8'),
);
const project = fs.readFileSync(
  path.join(root, 'ios', 'App', 'App.xcodeproj', 'project.pbxproj'),
  'utf8',
);
const swiftFiles = [
  'AppDelegate.swift',
  'AppleSignInPlugin.swift',
  'GoogleSignInPlugin.swift',
  'StorePlugin.swift',
  'NotifyPlugin.swift',
  'ExportPlugin.swift',
];
const swift = swiftFiles
  .map((file) => fs.readFileSync(path.join(iosApp, file), 'utf8'))
  .join('\n');

const nativeKeys = [
  'native.auth.apple.inProgress',
  'native.auth.apple.identityTokenMissing',
  'native.auth.google.inProgress',
  'native.auth.google.clientIdMissing',
  'native.auth.google.identityTokenMissing',
  'native.common.windowUnavailable',
  'native.common.viewUnavailable',
  'native.store.productIdMissing',
  'native.store.transactionIdMissing',
  'native.notification.testTitle',
  'native.notification.testBody',
  'native.notification.defaultTitle',
  'native.notification.defaultBody',
  'native.notification.publicTitle',
  'native.notification.publicBody',
  'native.notification.itemsMissing',
  'native.export.defaultFilename',
  'native.export.emptyContent',
  'native.export.inProgress',
  'native.export.renderTimeout',
  'native.export.pdfFailed',
  'native.export.writeFailed',
  'native.export.loadFailed',
];

function parseStrings(source, locale) {
  const values = new Map();
  const linePattern = /^\s*"([^"]+)"\s*=\s*"((?:\\.|[^"])*)";\s*$/gm;
  for (const match of source.matchAll(linePattern)) {
    assert(!values.has(match[1]), `${locale} duplicates ${match[1]}`);
    values.set(match[1], match[2]);
  }
  return values;
}

assert(
  swift.includes('table: "InfoPlist"'),
  'native copy must use the already-packaged InfoPlist.strings localization table',
);
for (const key of nativeKeys) {
  assert(
    new RegExp(`muneaNativeText\\(\\s*"${key.replaceAll('.', '\\.')}"`).test(swift),
    `native Swift bridge does not consume ${key}`,
  );
}

const localeValues = new Map();
for (const locale of manifest.locales) {
  const stringsPath = path.join(iosApp, `${locale.nativeLocale}.lproj`, 'InfoPlist.strings');
  assert(fs.existsSync(stringsPath), `${locale.locale} is missing ${stringsPath}`);
  const values = parseStrings(fs.readFileSync(stringsPath, 'utf8'), locale.locale);
  localeValues.set(locale.locale, values);
  for (const key of nativeKeys) {
    assert(values.has(key), `${locale.locale} is missing native copy ${key}`);
    assert(values.get(key).trim(), `${locale.locale} has blank native copy ${key}`);
  }
  assert.equal(
    locale.runtimeEnabled,
    locale.binaryLocalizationEnabled,
    `${locale.locale} runtime and binary release flags must move together`,
  );
}

const traditionalChinese = localeValues.get('zh-TW');
for (const locale of ['en', 'ja', 'es']) {
  const values = localeValues.get(locale);
  for (const key of nativeKeys) {
    assert.notEqual(
      values.get(key),
      traditionalChinese.get(key),
      `${locale} still reuses the Traditional Chinese native copy for ${key}`,
    );
  }
}

const knownRegionsStart = project.indexOf('knownRegions = (');
const knownRegionsEnd = project.indexOf(');', knownRegionsStart);
assert(knownRegionsStart >= 0 && knownRegionsEnd > knownRegionsStart, 'Xcode knownRegions not found');
const knownRegions = project.slice(knownRegionsStart, knownRegionsEnd);
const variantStart = project.indexOf('/* InfoPlist.strings */ = {');
const variantEnd = project.indexOf('/* End PBXVariantGroup section */', variantStart);
assert(variantStart >= 0 && variantEnd > variantStart, 'Xcode InfoPlist.strings variant group not found');
const variantGroup = project.slice(variantStart, variantEnd);

for (const locale of manifest.locales.filter((entry) => entry.binaryLocalizationEnabled)) {
  assert(
    knownRegions.includes(locale.nativeLocale),
    `release-enabled locale ${locale.nativeLocale} is absent from Xcode knownRegions`,
  );
  assert(
    variantGroup.includes(`/* ${locale.nativeLocale} */`),
    `release-enabled locale ${locale.nativeLocale} is absent from the InfoPlist.strings variant group`,
  );
}

for (const file of ['AppleSignInPlugin.swift', 'GoogleSignInPlugin.swift', 'StorePlugin.swift', 'NotifyPlugin.swift', 'ExportPlugin.swift']) {
  const source = fs.readFileSync(path.join(iosApp, file), 'utf8');
  assert.doesNotMatch(
    source,
    /(?:call|pendingCall|pending)\.reject\(\s*"[^"\n]*[\u3400-\u9fff]/,
    `${file} still sends a hard-coded Chinese rejection to the Web layer`,
  );
}

console.log(
  `PASS: ${nativeKeys.length} native bridge strings cover ${manifest.locales.length} locales; `
    + 'runtime/binary flags and Xcode membership fail closed',
);
