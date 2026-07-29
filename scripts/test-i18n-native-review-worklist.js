'use strict';

const assert = require('node:assert/strict');

const {
  JA_SHARED_SOURCE_KEYS,
  LOCALES,
  buildNativeReviewWorklist,
} = require('./i18n-native-review-worklist.js');

const worklist = buildNativeReviewWorklist();
const expectedPerLocale = worklist.catalogs['zh-TW'].keyCount;

assert.equal(worklist.schema, 'munea.i18n-native-review-worklist.v1');
assert.deepEqual(worklist.locales, LOCALES);
assert.equal(worklist.entryCount, expectedPerLocale * LOCALES.length);
assert.deepEqual(worklist.approvalPolicy, {
  automaticPassForbidden: true,
  nativeLanguageReviewerRequired: true,
  everyCatalogKeyRequired: true,
  catalogByteIdentityRequired: true,
  openIssuesMustBeZero: true,
});

const signatures = new Set();
for (const entry of worklist.entries) {
  const signature = `${entry.locale}:${entry.key}`;
  assert.ok(!signatures.has(signature), `Duplicate native review entry: ${signature}`);
  signatures.add(signature);
  assert.equal(entry.result, 'pending');
  assert.match(entry.sourceSha256, /^[a-f0-9]{64}$/);
  assert.match(entry.translationSha256, /^[a-f0-9]{64}$/);
  assert.deepEqual(entry.checks, {
    meaningPreserved: 'pending',
    grammarNatural: 'pending',
    toneAppropriate: 'pending',
    culturalContextAccepted: 'pending',
    placeholderContextAccepted: 'pending',
    spokenCopyReadAloud: 'pending',
  });
}

for (const locale of LOCALES) {
  const entries = worklist.entries.filter((entry) => entry.locale === locale);
  assert.equal(entries.length, expectedPerLocale, `${locale} native review count drifted`);
  assert.equal(worklist.catalogs[locale].keyCount, expectedPerLocale);
  assert.match(worklist.catalogs[locale].catalogSha256, /^[a-f0-9]{64}$/);
  assert.match(worklist.catalogs[locale].keysSha256, /^[a-f0-9]{64}$/);
  for (const entry of entries) {
    assert.deepEqual(
      entry.placeholders,
      [...entry.translation.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)]
        .map((match) => match[1])
        .sort(),
      `${locale}:${entry.key} placeholder context differs`,
    );
  }
}

const hanPattern = /[\u3400-\u9fff\uf900-\ufaff]/u;
for (const locale of ['en', 'es']) {
  for (const entry of worklist.entries.filter((item) => item.locale === locale)) {
    assert.ok(!hanPattern.test(entry.translation), `${locale}:${entry.key} contains Han text`);
    if (entry.exactSourceMatch) {
      assert.ok(
        !hanPattern.test(entry.source),
        `${locale}:${entry.key} is still identical to a Chinese source string`,
      );
    }
  }
}

const japaneseExactMatches = worklist.entries
  .filter((entry) => entry.locale === 'ja' && entry.exactSourceMatch)
  .map((entry) => entry.key)
  .sort();
assert.deepEqual(
  japaneseExactMatches,
  [...JA_SHARED_SOURCE_KEYS].sort(),
  'Japanese source-identical terms require an explicit reviewed allowlist',
);
for (const entry of worklist.entries.filter(
  (item) => item.locale === 'ja' && item.exactSourceMatch,
)) {
  assert.equal(
    entry.exactSourceMatchDisposition,
    'approved-shared-japanese-term',
  );
}

for (const locale of LOCALES) {
  const localeOnly = buildNativeReviewWorklist(locale);
  assert.deepEqual(localeOnly.locales, [locale]);
  assert.equal(localeOnly.entryCount, expectedPerLocale);
}
assert.throws(
  () => buildNativeReviewWorklist('fr'),
  /Unsupported native review locale/,
);

console.log(
  `Native review worklist PASS: ${worklist.entryCount} key reviews, `
  + `${expectedPerLocale} per locale`,
);
