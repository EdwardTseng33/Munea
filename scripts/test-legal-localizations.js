'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const legalRoot = path.resolve('web/legal');
const manifest = JSON.parse(
  fs.readFileSync(path.join(legalRoot, 'manifest.json'), 'utf8'),
);
const requiredLocales = ['zh-TW', 'en', 'ja', 'es'];
const requiredPages = ['privacy', 'terms', 'support'];
const regionalPolicy = JSON.parse(
  fs.readFileSync(path.join(legalRoot, 'regional-safety-policy.json'), 'utf8'),
);

assert.equal(manifest.schemaVersion, 1, 'Legal localization manifest must use schema version 1');
assert.equal(manifest.defaultLocale, 'zh-TW', 'Traditional Chinese must remain the legal default');
assert.equal(manifest.fallbackLocale, 'zh-TW', 'Traditional Chinese must remain the legal fallback');
assert.deepEqual(
  Object.keys(manifest.locales),
  requiredLocales,
  'Legal pages must cover exactly the four approved locales',
);

const localizedHtml = {};

for (const locale of requiredLocales) {
  const config = manifest.locales[locale];
  assert(config, `Missing legal manifest entry for ${locale}`);
  assert.deepEqual(
    Object.keys(config.pages),
    requiredPages,
    `${locale} must declare privacy, terms, and support pages`,
  );
  assert.equal(
    locale === 'zh-TW' ? config.legalReview : config.legalReview.startsWith('pending'),
    locale === 'zh-TW' ? 'approved' : true,
    `${locale} legal-review state must remain release-gated`,
  );

  localizedHtml[locale] = {};
  for (const pageName of requiredPages) {
    const filePath = path.resolve(legalRoot, config.pages[pageName]);
    assert(
      filePath.startsWith(path.resolve('web') + path.sep),
      `${locale}/${pageName} must stay inside the web tree`,
    );
    assert(fs.existsSync(filePath), `Missing ${locale}/${pageName}: ${filePath}`);

    const html = fs.readFileSync(filePath, 'utf8');
    localizedHtml[locale][pageName] = html;
    assert(
      new RegExp(`<html\\s+lang="${config.htmlLang}"`, 'i').test(html),
      `${locale}/${pageName} must declare html lang="${config.htmlLang}"`,
    );
    assert(/<title>[^<]+<\/title>/i.test(html), `${locale}/${pageName} needs a title`);
    assert(/class="privacy-page"/.test(html), `${locale}/${pageName} needs the shared page shell`);
    assert(/class="privacy-section"/.test(html), `${locale}/${pageName} needs readable sections`);
    assert(!/<script[\s>]/i.test(html), `${locale}/${pageName} must remain static and script-free`);
    assert(
      !/language[-_ ]?(?:selector|switcher)|id="[^"]*(?:language|locale)[^"]*"/i.test(html),
      `${locale}/${pageName} must not add an in-App language selector`,
    );

    if (locale !== 'zh-TW') {
      assert(
        /<meta\s+name="description"\s+content="[^"]+"/i.test(html),
        `${locale}/${pageName} needs localized metadata`,
      );
      assert(
        !/\b(?:119|1925)\b/.test(html),
        `${locale}/${pageName} must not inherit Taiwan emergency numbers from its language`,
      );
    }
  }
}

assert.equal(regionalPolicy.schema, 'munea.regional-safety-policy.v1');
assert.equal(regionalPolicy.authority, 'repository-draft-only');
assert.equal(regionalPolicy.selectionPolicy.languageNeverSelectsCountry, true);
assert.equal(regionalPolicy.selectionPolicy.trustedLocaleContextField, 'safetyRegion');
assert.equal(regionalPolicy.selectionPolicy.automaticPromotionForbidden, true);
assert.deepEqual(Object.keys(regionalPolicy.regions), ['ES', 'MX']);
assert.equal(regionalPolicy.regions.ES.emergencyNumber, '112');
assert.match(regionalPolicy.regions.ES.officialEmergencySource, /interior\.gob\.es/);
assert.equal(regionalPolicy.regions.MX.emergencyNumber, '911');
assert.match(regionalPolicy.regions.MX.officialEmergencySource, /gob\.mx/);
for (const [region, policy] of Object.entries(regionalPolicy.regions)) {
  assert.equal(policy.safetyRegion, region);
  assert.equal(policy.legalRegion, region);
  assert.equal(policy.appLanguage, 'es');
  assert.equal(policy.availabilityAuthorized, false);
  assert.match(policy.legalReview, /^pending/);
  assert.deepEqual(
    manifest.locales.es.regionalVariants[region].contentVariant,
    policy.appStoreLocale,
  );
}

for (const locale of ['en', 'es']) {
  for (const pageName of requiredPages) {
    assert(
      !/[\u3400-\u9fff\uf900-\ufaff]/u.test(localizedHtml[locale][pageName]),
      `${locale}/${pageName} must not contain accidental Han copy`,
    );
  }
}

assert(
  localizedHtml.en.privacy.includes('Tokyo, Japan'),
  'English privacy must disclose the current Tokyo data region',
);
assert(
  localizedHtml.ja.privacy.includes('日本・東京'),
  'Japanese privacy must disclose the current Tokyo data region',
);
assert(
  localizedHtml.es.privacy.includes('Tokio, Japón'),
  'Spanish privacy must disclose the current Tokyo data region',
);

for (const locale of requiredLocales) {
  for (const pageName of ['privacy', 'support']) {
    assert(
      localizedHtml[locale][pageName].includes('mailto:edwardt0303@gmail.com'),
      `${locale}/${pageName} must provide a working support contact`,
    );
  }
}

assert(
  /new call cannot start/i.test(localizedHtml.en.terms),
  'English terms must match the zero-credit call gate',
);
assert(
  localizedHtml.ja.terms.includes('新しい通話を開始できません'),
  'Japanese terms must match the zero-credit call gate',
);
assert(
  /no puede iniciarse una nueva llamada/i.test(localizedHtml.es.terms),
  'Spanish terms must match the zero-credit call gate',
);
assert(
  localizedHtml['zh-TW'].terms.includes('不會開始新的語音／虛擬形象通話'),
  'Traditional Chinese terms must match the zero-credit call gate',
);

console.log('PASS: legal localization assets and regional safety guardrails');
