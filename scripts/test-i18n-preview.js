'use strict';

const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('tools/i18n-preview.html', 'utf8');
const catalogs = Object.fromEntries(
  ['zh-TW', 'en', 'ja', 'es'].map((locale) => [
    locale,
    JSON.parse(fs.readFileSync(`web/src/i18n/${locale}.json`, 'utf8')),
  ]),
);
const keys = new Set([
  ...[...html.matchAll(/data-i18n="([^"]+)"/g)].map((match) => match[1]),
  ...[...html.matchAll(/api\.t\(\s*'([^']+)'/g)].map((match) => match[1]),
]);

assert(keys.size >= 25, 'The QA preview must cover representative App copy');
for (const [locale, catalog] of Object.entries(catalogs)) {
  for (const key of keys) {
    assert.equal(typeof catalog[key], 'string', `${locale} preview key is missing: ${key}`);
    assert(catalog[key].trim(), `${locale} preview key is empty: ${key}`);
  }
}
assert(html.includes("const allowed = ['zh-TW', 'en', 'ja', 'es']"));
assert(html.includes('MUNEA_DEV_CONFIG'));
assert(html.includes('enabled: true'));
assert(html.includes('This page is not release evidence.'));
assert(html.includes('width: min(100%, 430px)'));
assert(html.includes('font-size: 125%'));
assert(!/https?:\/\//i.test(html), 'The local QA page must not call external services');
assert(!/localStorage|sessionStorage/.test(html), 'The QA page must not persist a language');

console.log(`PASS: local i18n QA preview covers ${keys.size} catalog keys without production access`);
