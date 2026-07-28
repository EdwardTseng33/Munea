'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const LOCALES = ['zh-TW', 'en', 'ja', 'es'];

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, relativePath), 'utf8'));
}

const screenManifest = readJson('web/src/i18n/app-screen-manifest.json');
const surfaceInventory = readJson('docs/I18N-SURFACE-INVENTORY.json');
const appSurface = surfaceInventory.surfaces.find(({ id }) => id === 'app-webview');
assert.ok(appSurface, 'app-webview inventory is missing');
assert.equal(screenManifest.schema, 'munea.i18n-app-screen-manifest.v1');
assert.equal(screenManifest.bindingStatus, 'pending-main-screen-integration');
assert.equal(screenManifest.visualQaPending, true);
assert.deepEqual(
  Object.keys(screenManifest.requiredStates),
  appSurface.requiredStates,
  'screen manifest states differ from the App WebView release inventory',
);

const catalogs = Object.fromEntries(
  LOCALES.map((locale) => [locale, readJson(`web/src/i18n/${locale}.json`)]),
);
const allGroups = {
  ...screenManifest.requiredStates,
  ...Object.fromEntries(
    Object.entries(screenManifest.requiredModals)
      .map(([name, keys]) => [`modal:${name}`, keys]),
  ),
};
const han = /[\u3400-\u9fff\uf900-\ufaff]/u;

for (const [group, keys] of Object.entries(allGroups)) {
  assert.ok(Array.isArray(keys) && keys.length >= 5, `${group} must cover at least five keys`);
  assert.equal(new Set(keys).size, keys.length, `${group} contains duplicate keys`);
  for (const locale of LOCALES) {
    for (const key of keys) {
      const value = catalogs[locale][key];
      assert.equal(typeof value, 'string', `${locale}:${group}:${key} is missing`);
      assert.ok(value.trim(), `${locale}:${group}:${key} is empty`);
      if (locale === 'en' || locale === 'es') {
        assert.ok(!han.test(value), `${locale}:${group}:${key} unexpectedly contains Han text`);
      }
    }
  }
}

const coveredKeys = new Set(Object.values(allGroups).flat());
assert.ok(coveredKeys.size >= 100, 'App screen contract must cover at least 100 unique keys');

console.log(
  `App screen localizations PASS: ${Object.keys(screenManifest.requiredStates).length} states, `
  + `${Object.keys(screenManifest.requiredModals).length} modals, ${coveredKeys.size} unique keys`,
);
