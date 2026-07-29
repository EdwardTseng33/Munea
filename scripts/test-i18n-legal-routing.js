'use strict';

const assert = require('assert');
const fs = require('fs');
const { resolveLegalPage } = require('../web/src/i18n/legal-routing.js');

function readJson(path) {
  return JSON.parse(fs.readFileSync(path, 'utf8'));
}

const catalogManifest = readJson('web/src/i18n/catalog-manifest.json');
const legalManifest = readJson('web/legal/manifest.json');

for (const locale of ['en', 'ja', 'es']) {
  const production = resolveLegalPage({
    catalogManifest,
    kind: 'privacy',
    legalManifest,
    locale,
  });
  assert.equal(production.resolvedLocale, 'zh-TW');
  assert.equal(production.path, 'privacy.html');
  assert.equal(production.usedFallback, true);

  const draftPreview = resolveLegalPage({
    allowDraft: true,
    catalogManifest,
    kind: 'privacy',
    legalManifest,
    locale,
  });
  assert.equal(draftPreview.resolvedLocale, locale);
  assert.equal(draftPreview.path, `legal/${locale}/privacy.html`);
  assert.equal(draftPreview.usedFallback, false);
  assert.match(draftPreview.legalReview, /^pending/);
}

for (const legalRegion of ['ES', 'MX']) {
  const spanishVariant = resolveLegalPage({
    allowDraft: true,
    catalogManifest,
    kind: 'support',
    legalManifest,
    legalRegion,
    locale: 'es',
  });
  assert.equal(spanishVariant.requestedLocale, 'es');
  assert.equal(spanishVariant.resolvedLocale, 'es');
  assert.equal(spanishVariant.requestedLegalRegion, legalRegion);
  assert.equal(spanishVariant.resolvedLegalRegion, legalRegion);
  assert.equal(spanishVariant.path, 'legal/es/support.html');
  assert.equal(spanishVariant.legalReview, 'pending-qualified-review');
}

const spanishWithoutTrustedRegion = resolveLegalPage({
  allowDraft: true,
  catalogManifest,
  kind: 'support',
  legalManifest,
  locale: 'es',
});
assert.equal(
  spanishWithoutTrustedRegion.resolvedLegalRegion,
  null,
  'Spanish language alone must never select Spain or Mexico legal policy',
);

const traditionalChinese = resolveLegalPage({
  catalogManifest,
  kind: 'terms',
  legalManifest,
  locale: 'zh-TW',
});
assert.equal(traditionalChinese.path, 'terms.html');
assert.equal(traditionalChinese.legalReview, 'approved');
assert.equal(traditionalChinese.usedFallback, false);

const unsupported = resolveLegalPage({
  catalogManifest,
  kind: 'support',
  legalManifest,
  locale: 'fr-FR',
});
assert.equal(unsupported.requestedLocale, 'zh-TW');
assert.equal(unsupported.path, 'support.html');
assert.equal(unsupported.usedFallback, false);

assert.throws(
  () => resolveLegalPage({
    catalogManifest,
    kind: 'emergency',
    legalManifest,
    locale: 'en',
  }),
  /unsupported legal page kind/,
);

const approvedEnglishLegal = JSON.parse(JSON.stringify(legalManifest));
approvedEnglishLegal.locales.en.legalReview = 'approved';
const disabledEnglish = resolveLegalPage({
  catalogManifest,
  kind: 'privacy',
  legalManifest: approvedEnglishLegal,
  locale: 'en',
});
assert.equal(
  disabledEnglish.resolvedLocale,
  'zh-TW',
  'Legal approval alone must not bypass the runtime locale release gate',
);

const unsafeLegal = JSON.parse(JSON.stringify(legalManifest));
unsafeLegal.locales['zh-TW'].pages.privacy = '../../secret.html';
assert.throws(
  () => resolveLegalPage({
    catalogManifest,
    kind: 'privacy',
    legalManifest: unsafeLegal,
    locale: 'zh-TW',
  }),
  /legal root page path must be a file name/,
  'Manifest paths must not escape the reviewed Web legal surface',
);

console.log('PASS: release-gated legal reader routing');
