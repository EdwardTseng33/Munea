'use strict';

const assert = require('assert');
const fs = require('fs');
const { resolveLegalPage } = require('../web/src/i18n/legal-routing.js');

function readJson(path) {
  return JSON.parse(fs.readFileSync(path, 'utf8'));
}

const catalogManifest = readJson('web/src/i18n/catalog-manifest.json');
const legalManifest = readJson('web/legal/manifest.json');

// 法律頁指到哪，要跟著「這個語系的法務核准了沒」走，不要寫死。
// （2026-08-01：原本寫死「三語一律退回繁中」，那是三語法律頁還掛著
//  「翻譯稿、尚未經法務確認」時的狀態；7/31 Edward 核准發佈後前提就變了。）
for (const locale of ['en', 'ja', 'es']) {
  const approved = legalManifest.locales[locale].legalReview === 'approved';

  const production = resolveLegalPage({
    catalogManifest,
    kind: 'privacy',
    legalManifest,
    locale,
  });
  if (approved) {
    assert.equal(production.resolvedLocale, locale, `${locale} 法律頁已核准，應該指到自己那份`);
    assert.equal(production.path, `legal/${locale}/privacy.html`);
    assert.equal(production.usedFallback, false);
  } else {
    assert.equal(production.resolvedLocale, 'zh-TW', `${locale} 法律頁沒核准，必須退回繁中`);
    assert.equal(production.path, 'privacy.html');
    assert.equal(production.usedFallback, true);
  }

  // 預覽模式一律看得到該語系那份，不論核准與否——這條跟核准狀態無關
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
  assert.match(
    draftPreview.legalReview,
    approved ? /^approved$/ : /^pending/,
    `${locale} 預覽回報的核准狀態要跟正本一致`,
  );
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
  // 核准狀態跟著正本走，不寫死——7/31 Edward 定了只做西班牙（ES 核准），
  // 墨西哥本次不上架（MX 標成 pending-market-not-launched）。
  assert.equal(
    spanishVariant.legalReview,
    legalManifest.locales.es.regionalVariants[legalRegion].legalReview,
    `西文 ${legalRegion} 變體回報的核准狀態要跟正本一致`,
  );
}
// 兩個西語市場必須分得開——不能因為都講西班牙文就混用同一套法務狀態
assert.notEqual(
  legalManifest.locales.es.regionalVariants.ES.legalReview,
  legalManifest.locales.es.regionalVariants.MX.legalReview,
  '西班牙與墨西哥的法務狀態必須各自獨立，本次只上架西班牙',
);

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

// 「法務核准了」不等於「這個語系可以開」——兩道關要各自成立。
// 原本用英文來測這條，但英文 2026-08-01 已經開了，測不出來；
// 改成自己造一個「法務已核准、但語系關著」的情境，規矩照守，
// 而且不再依賴「哪個語系剛好是關的」這種會過期的前提。
const approvedButDisabled = JSON.parse(JSON.stringify(legalManifest));
approvedButDisabled.locales.en.legalReview = 'approved';
const gatedCatalog = JSON.parse(JSON.stringify(catalogManifest));
for (const entry of gatedCatalog.locales) {
  if (entry.locale === 'en') {
    entry.runtimeEnabled = false;
    entry.binaryLocalizationEnabled = false;
    entry.status = 'development';
  }
}
const disabledEnglish = resolveLegalPage({
  catalogManifest: gatedCatalog,
  kind: 'privacy',
  legalManifest: approvedButDisabled,
  locale: 'en',
});
assert.equal(
  disabledEnglish.resolvedLocale,
  'zh-TW',
  '法務核准不能繞過語系開關——語系關著就必須退回繁中',
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
