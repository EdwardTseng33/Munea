'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const {
  createCatalogRuntime,
  devicePreferredLanguages,
  normalizeLocaleTag,
} = require('../web/src/i18n/catalog-runtime.js');

const ROOT = path.resolve(__dirname, '..');
const CATALOG_DIR = path.join(ROOT, 'web', 'src', 'i18n');
const manifest = JSON.parse(
  fs.readFileSync(path.join(CATALOG_DIR, 'catalog-manifest.json'), 'utf8'),
);
const catalogs = Object.fromEntries(
  manifest.locales.map((entry) => [
    entry.locale,
    JSON.parse(fs.readFileSync(path.join(CATALOG_DIR, entry.catalog), 'utf8')),
  ]),
);
const supportedLocales = manifest.locales.map(({ locale }) => locale);

assert.equal(normalizeLocaleTag('zh-Hant-TW', supportedLocales), 'zh-TW');
assert.equal(normalizeLocaleTag('zh_TW', supportedLocales), 'zh-TW');
assert.equal(normalizeLocaleTag('en-US', supportedLocales), 'en');
assert.equal(normalizeLocaleTag('ja-JP', supportedLocales), 'ja');
assert.equal(normalizeLocaleTag('es-MX', supportedLocales), 'es');
assert.equal(normalizeLocaleTag('de-DE', supportedLocales), null);

assert.deepEqual(
  devicePreferredLanguages({ languages: ['ja-JP', 'en-US'], language: 'es-MX' }),
  ['ja-JP', 'en-US'],
);
assert.deepEqual(devicePreferredLanguages({ language: 'es-MX' }), ['es-MX']);
assert.deepEqual(devicePreferredLanguages({}), []);

const productionRuntime = createCatalogRuntime({ manifest, catalogs });
assert.deepEqual(productionRuntime.enabledLocales, ['zh-TW']);
assert.equal(productionRuntime.currentFromDevice({ languages: ['ja-JP'] }), 'zh-TW');
assert.equal(productionRuntime.currentFromDevice({ languages: ['en-US'] }), 'zh-TW');
assert.equal(productionRuntime.currentFromDevice({ languages: ['es-MX'] }), 'zh-TW');
assert.equal(productionRuntime.currentFromDevice({ languages: ['de-DE'] }), 'zh-TW');
assert.equal(productionRuntime.localeMetadata('ja-JP').htmlLang, 'zh-Hant-TW');

const previewRuntime = createCatalogRuntime({
  manifest,
  catalogs,
  allowDevelopmentLocales: true,
});
assert.deepEqual(previewRuntime.enabledLocales, ['zh-TW', 'en', 'ja', 'es']);
assert.equal(
  previewRuntime.currentFromDevice({ languages: ['fr-FR', 'ja-JP', 'en-US'] }),
  'ja',
);
assert.equal(previewRuntime.currentFromDevice({ language: 'es-ES' }), 'es');
assert.equal(previewRuntime.localeMetadata('ja-JP').htmlLang, 'ja');
assert.equal(
  previewRuntime.t('en-US', 'error.retryAfterSeconds', { seconds: 5 }),
  'Try again in 5 seconds.',
);
assert.equal(
  previewRuntime.t('ja-JP', 'error.retryAfterSeconds', {}),
  '{seconds}秒後にもう一度お試しください。',
);
assert.equal(previewRuntime.tp('en-US', 'time.minutes', 1), '1 minute');
assert.equal(previewRuntime.tp('en-US', 'time.minutes', 3), '3 minutes');
assert.equal(previewRuntime.tp('ja-JP', 'time.minutes', 3), '3 分');
assert.equal(previewRuntime.tp('es-MX', 'time.minutes', 1), '1 minuto');
assert.equal(previewRuntime.formatNumber('en-US', 1234.5), '1,234.5');
assert.match(
  previewRuntime.formatDate('ja-JP', '2026-07-28T00:00:00Z', {
    dateStyle: 'medium',
    timeZone: 'UTC',
  }),
  /2026/,
);
assert.equal(
  previewRuntime.formatList('en-US', ['Mimi', 'Nening'], { type: 'conjunction' }),
  'Mimi and Nening',
);
assert.ok(
  previewRuntime.formatRelativeTime('es-ES', -1, 'day', { numeric: 'auto' }).length > 0,
);
assert.throws(() => previewRuntime.t('en-US', ''), /non-empty string/);
assert.throws(() => previewRuntime.t('en-US'), /non-empty string/);
assert.throws(() => previewRuntime.tp('en-US', 'time.minutes', Number.NaN), /finite number/);
assert.throws(() => previewRuntime.formatDate('en-US', 'not-a-date'), /valid/);
assert.throws(() => previewRuntime.formatList('en-US', 'Mimi'), /array/);

const missingEvents = [];
const catalogsWithGap = JSON.parse(JSON.stringify(catalogs));
delete catalogsWithGap.ja['common.save'];
const fallbackRuntime = createCatalogRuntime({
  manifest,
  catalogs: catalogsWithGap,
  allowDevelopmentLocales: true,
  reportMissingKey: (event) => missingEvents.push(event),
});
assert.equal(fallbackRuntime.t('ja-JP', 'common.save'), '儲存');
assert.equal(fallbackRuntime.t('ja-JP', 'common.save'), '儲存');
assert.equal(missingEvents.length, 1, 'missing-key telemetry must be deduplicated');
assert.deepEqual(missingEvents[0], {
  event: 'i18n_missing_key',
  key: 'common.save',
  requestedLocale: 'ja',
  resolvedLocale: 'ja',
  fallbackLocale: 'zh-TW',
});
assert.ok(!Object.hasOwn(missingEvents[0], 'value'));
assert.ok(!Object.hasOwn(missingEvents[0], 'userText'));

const catalogsWithoutKey = JSON.parse(JSON.stringify(catalogsWithGap));
delete catalogsWithoutKey['zh-TW']['common.save'];
const literalRuntime = createCatalogRuntime({
  manifest,
  catalogs: catalogsWithoutKey,
  allowDevelopmentLocales: true,
  reportMissingKey: () => {
    throw new Error('telemetry unavailable');
  },
});
assert.equal(
  literalRuntime.t('ja-JP', 'common.save', null, 'Save safely'),
  'Save safely',
);

assert.throws(
  () => createCatalogRuntime({ manifest, catalogs: { 'zh-TW': catalogs['zh-TW'] } }),
  /missing i18n catalog: en/,
);

const runtimeSource = fs.readFileSync(
  path.join(CATALOG_DIR, 'catalog-runtime.js'),
  'utf8',
);
assert.ok(!runtimeSource.includes('localStorage'), 'UI locale runtime must not add an in-App selector');
assert.ok(!runtimeSource.includes('conversationLocale'), 'UI locale must stay independent from voice language');

console.log(
  'i18n runtime PASS: iOS language resolution, release gates, plural/date/number/list formatting, '
  + 'fallback, telemetry',
);
