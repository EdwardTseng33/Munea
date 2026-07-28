'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const SITE_DIR = path.join(ROOT, 'app-site');
const html = fs.readFileSync(path.join(SITE_DIR, 'index.html'), 'utf8');
const runtime = fs.readFileSync(path.join(SITE_DIR, 'warm.js'), 'utf8');

function decodeAttribute(value) {
  return value
    .replace(/&amp;/g, '&')
    .replace(/&apos;|&#39;/g, "'")
    .replace(/&quot;|&#34;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>');
}

const sourceMatches = [
  ...html.matchAll(/data-en=(?:"([^"]*)"|'([^']*)')/g),
];
const englishSources = [
  ...new Set(sourceMatches.map((match) => decodeAttribute(match[1] || match[2]))),
].sort();
const attributeSources = [
  ...new Set(
    [...html.matchAll(/data-en-(?:aria-label|alt|content)="([^"]+)"/g)]
      .map((match) => decodeAttribute(match[1])),
  ),
].sort();

assert.equal(
  englishSources.length,
  136,
  'Every public-site copy change must deliberately update the four-locale catalog',
);

for (const locale of ['ja', 'es']) {
  const catalogPath = path.join(SITE_DIR, 'i18n', `${locale}.json`);
  const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
  assert.equal(catalog.schemaVersion, 1);
  assert.equal(catalog.locale, locale);
  assert.deepEqual(
    Object.keys(catalog.translations).sort(),
    englishSources,
    `${locale} catalog must exactly cover every data-en source string`,
  );
  assert.deepEqual(
    Object.keys(catalog.attributes).sort(),
    attributeSources,
    `${locale} catalog must exactly cover every localized metadata and accessibility attribute`,
  );
  assert.deepEqual(Object.keys(catalog.messages).sort(), ['mute', 'soundOn']);
  for (const [source, translated] of Object.entries(catalog.translations)) {
    assert.equal(typeof translated, 'string');
    assert(translated.trim(), `${locale} translation is empty for: ${source}`);
    assert(!translated.includes('\uFFFD'), `${locale} translation contains broken encoding`);
    if (locale === 'es') {
      assert(
        !/[\u3400-\u9fff\uf900-\ufaff]/u.test(translated),
        `Spanish translation contains accidental Han copy: ${source}`,
      );
    }
    if (!/^(?:Munea(?: FamilyWellness AI)?|A-Yuan)$/.test(source)) {
      assert.notEqual(
        translated,
        source,
        `${locale} must not silently use English as a completed translation: ${source}`,
      );
    }
  }
  for (const [source, translated] of Object.entries(catalog.attributes)) {
    assert.equal(typeof translated, 'string');
    assert(translated.trim(), `${locale} attribute translation is empty for: ${source}`);
    if (locale === 'es') {
      assert(
        !/[\u3400-\u9fff\uf900-\ufaff]/u.test(translated),
        `Spanish attribute translation contains accidental Han copy: ${source}`,
      );
    }
    if (source !== 'Munea') {
      assert.notEqual(
        translated,
        source,
        `${locale} must not silently retain English accessibility copy: ${source}`,
      );
    }
  }
}

const localeOptions = [
  ...html.matchAll(/class="lang-opt"[^>]*data-lang="([^"]+)"/g),
].map((match) => match[1]);
assert.deepEqual(localeOptions, ['zh-TW', 'en', 'ja', 'es']);
assert.match(
  html,
  /@media\(max-width:900px\)\{\.hero-grid\{grid-template-columns:minmax\(0,1fr\)\}\.hero-grid>div\{min-width:0\}\.hero h1 \.word\{white-space:normal\}/,
  'The later public-site CSS must preserve the single-column mobile hero',
);
assert.match(
  html,
  /--teal:#1F6F68;--teal-d:#1F655F;--teal-dd:#174F4B;--muted:#52615C/,
  'Public-site foreground colors must retain the reviewed contrast-safe palette',
);
assert.match(html, /footer \.logo-word b\{color:#8FD4CC\}/);
assert.match(html, /footer \.foot-col h4,footer \.foot-bottom\{color:#C2CCC9\}/);
assert.equal(
  [...html.matchAll(/class="cb(?: on)?" role="img" aria-label=/g)].length,
  2,
  'Mock call controls with accessible names must use a permitted ARIA role',
);
assert.match(runtime, /navigator\.languages/);
assert.match(runtime, /normalizeLocale/);
assert.match(runtime, /fetch\(`i18n\/\$\{locale\}\.json`\)/);
assert.match(runtime, /localizedAttributes = \['aria-label', 'alt', 'content'\]/);
assert.match(runtime, /catalogs\.get\(locale\)\.attributes\[binding\.source\]/);
assert.match(runtime, /EN_MESSAGES = \{soundOn:'Sound on',mute:'Mute'\}/);
assert.match(html, /syncButton\(btn,muted\)/);
assert.match(runtime, /data-i18n-error/);
assert.match(runtime, /new CustomEvent\('careon-lang'/);
for (const locale of ['zh-TW', 'en', 'ja', 'es']) {
  assert(
    runtime.includes(`'${locale}'`),
    `Marketing runtime must explicitly support ${locale}`,
  );
}

assert(
  !html.includes('In an emergency call 119'),
  'English copy must not infer Taiwan emergency policy from language',
);
assert.match(
  html,
  /In an emergency, contact local emergency services\. In Taiwan, call 119;/,
);
assert.match(
  html,
  /緊急狀況請聯絡所在地緊急服務。台灣使用者可撥 119/,
);
assert(
  [...html.matchAll(/https:\/\/apps\.apple\.com\/tw\/app\/munea/g)].length >= 3,
  'The existing Taiwan App Store URL must remain explicit until other storefronts are verified',
);
assert(
  !/apps\.apple\.com\/\$\{|replace\([^)]*apps\.apple\.com/.test(runtime),
  'UI language must not invent an App Store country',
);

console.log('PASS: public marketing site has complete zh-TW/en/ja/es copy and safe locale routing');
