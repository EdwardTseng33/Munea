'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const SITE_SOURCE = path.join(ROOT, 'site-src');
const SITE_OUTPUT = path.join(ROOT, 'app-site');
const config = JSON.parse(
  fs.readFileSync(path.join(SITE_SOURCE, 'config.json'), 'utf8'),
);
const manifest = JSON.parse(
  fs.readFileSync(path.join(SITE_SOURCE, 'localization-manifest.json'), 'utf8'),
);
const siteUrl = String(config.siteUrl || '').replace(/\/+$/, '');
assert.equal(siteUrl, 'https://munea.net', 'Marketing canonical authority drifted');

const locales = [
  {
    locale: 'zh-TW',
    catalog: 'zh',
    output: 'index.html',
    htmlLang: 'zh-Hant-TW',
    canonical: `${siteUrl}/`,
  },
  {
    locale: 'en',
    catalog: 'en',
    output: 'en/index.html',
    htmlLang: 'en',
    canonical: `${siteUrl}/en`,
  },
  {
    locale: 'ja',
    catalog: 'ja',
    output: 'ja/index.html',
    htmlLang: 'ja',
    canonical: `${siteUrl}/ja`,
  },
  {
    locale: 'es',
    catalog: 'es',
    output: 'es/index.html',
    htmlLang: 'es',
    canonical: `${siteUrl}/es`,
  },
];

assert.equal(manifest.defaultLocale, 'zh-TW');
assert.equal(manifest.fallbackLocale, 'zh-TW');
assert.deepEqual(Object.keys(manifest.locales), locales.map((item) => item.locale));

const catalogs = new Map();
for (const item of locales) {
  const catalog = JSON.parse(
    fs.readFileSync(
      path.join(SITE_SOURCE, 'i18n', `${item.catalog}.json`),
      'utf8',
    ),
  );
  catalogs.set(item.locale, catalog);
}

const sourceKeys = Object.keys(catalogs.get('zh-TW')).sort();
assert(sourceKeys.length > 150, 'The public site must keep a complete translation catalog');
for (const item of locales) {
  const catalog = catalogs.get(item.locale);
  assert.deepEqual(
    Object.keys(catalog).sort(),
    sourceKeys,
    `${item.locale} must cover the same public-site keys as Traditional Chinese`,
  );
  for (const [key, value] of Object.entries(catalog)) {
    assert.equal(typeof value, 'string', `${item.locale}.${key} must be a string`);
    assert(value.trim(), `${item.locale}.${key} must not be empty`);
  }
}

for (const item of locales) {
  const html = fs.readFileSync(path.join(SITE_OUTPUT, item.output), 'utf8');
  const manifestEntry = manifest.locales[item.locale];
  assert.equal(manifestEntry.htmlLang, item.htmlLang);
  assert.match(
    html,
    new RegExp(`<html\\s+lang=["']${item.htmlLang}["']`, 'i'),
    `${item.output} must declare the expected html language`,
  );
  assert.match(
    html,
    new RegExp(
      `<link\\s+rel=["']canonical["']\\s+href=["']${item.canonical.replaceAll('.', '\\.')}["']`,
      'i',
    ),
    `${item.output} must keep its locale-specific canonical URL`,
  );
  assert.equal(
    [...html.matchAll(/<h1(?:\s|>)/gi)].length,
    1,
    `${item.output} must contain exactly one h1`,
  );
  assert.doesNotMatch(html, /\{\{[^}]+\}\}/, `${item.output} has an unresolved template key`);
  assert.doesNotMatch(html, /noindex/i, `${item.output} must stay indexable`);
  for (const target of locales) {
    assert.match(
      html,
      new RegExp(
        `class=["'][^"']*lang-opt[^"']*["'][^>]*href=["']${target.canonical.replaceAll('.', '\\.')}["']`,
        'i',
      ),
      `${item.output} must link to ${target.locale} as a real static URL`,
    );
  }
}

for (const locale of ['en', 'ja', 'es']) {
  const disclaimer = catalogs.get(locale)['foot.disclaimer'];
  assert.doesNotMatch(
    disclaimer,
    /\b(?:112|119|1925)\b/,
    `${locale} language must not infer a country-specific emergency number`,
  );
}

const verifiedAppStoreUrl = 'https://apps.apple.com/tw/app/id6788658125';
assert.equal(
  config.appStoreUrl,
  verifiedAppStoreUrl,
  'The public site must keep the verified Taiwan App Store URL for Munea',
);
for (const item of locales) {
  const html = fs.readFileSync(path.join(SITE_OUTPUT, item.output), 'utf8');
  const appStoreLinks = [
    ...html.matchAll(
      /<a\b[^>]*href=["']https:\/\/apps\.apple\.com\/tw\/app\/id6788658125["'][^>]*>/gi,
    ),
  ];
  assert.equal(
    appStoreLinks.length,
    3,
    `${item.output} must expose the verified App Store URL in all three download CTAs`,
  );
  for (const [anchor] of appStoreLinks) {
    assert.match(anchor, /\btarget=["']_blank["']/i, `${item.output} App Store CTA opens safely`);
    assert.match(anchor, /\brel=["']noopener["']/i, `${item.output} App Store CTA isolates its opener`);
  }
}

console.log(
  'PASS: public marketing site uses complete zh-TW/en/ja/es static paths without inferring country from language',
);
