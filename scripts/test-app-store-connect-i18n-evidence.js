'use strict';

const assert = require('node:assert/strict');
const {
  EVIDENCE_CHECKS,
  buildCurrentRequirements,
  compileEvidence,
  validateEvidence,
  validateSnapshot,
} = require('./app-store-connect-i18n-evidence.js');

const referenceTime = new Date('2026-07-29T12:00:00Z');
const options = {
  spanishVariants: ['es-ES'],
  referenceTime,
};
const requirements = buildCurrentRequirements(options);

function validSnapshot() {
  return {
    schema: 'munea.app-store-connect-i18n-snapshot.v1',
    capturedAt: '2026-07-29T11:30:00Z',
    captureMethod: requirements.captureMethod,
    evidenceReference: 'asc-readonly-export-001',
    containsSecrets: false,
    productionWritesPerformed: false,
    bundleIdentifier: requirements.bundleIdentifier,
    appStoreConnectAppId: '1234567890',
    appAvailability: {
      territories: requirements.targets.map(({ territory }) => territory),
    },
    localizations: Object.fromEntries(requirements.targets.map((target) => [
      target.appStoreLocale,
      {
        metadata: JSON.parse(JSON.stringify(target.metadata)),
        screenshotCount: 5,
      },
    ])),
    iapProducts: requirements.products.map((facts, index) => ({
      productId: facts.productId,
      type: facts.type,
      appStoreConnectProductId: String(9000000000 + index),
      reviewScreenshotAttached: true,
      availableTerritories: requirements.targets.map(({ territory }) => territory),
      localizations: Object.fromEntries(requirements.targets.map((target) => [
        target.appStoreLocale,
        JSON.parse(JSON.stringify(target.iapCopy[facts.productId])),
      ])),
      localizedPrices: Object.fromEntries(requirements.targets.map((target) => [
        target.territory,
        {
          currency: {
            TW: 'TWD',
            US: 'USD',
            JP: 'JPY',
            ES: 'EUR',
          }[target.territory],
          displayPrice: `localized-price-${target.territory}`,
        },
      ])),
    })),
  };
}

const snapshot = validSnapshot();
assert.equal(validateSnapshot(snapshot, requirements, referenceTime), true);
const evidence = compileEvidence(snapshot, options);
assert.equal(evidence.schema, 'munea.app-store-connect-i18n-audit.v1');
assert.equal(evidence.result, 'pass');
assert.equal(evidence.productCount, 8);
assert.deepEqual(evidence.targetLocales, ['zh-Hant', 'en-US', 'ja', 'es-ES']);
assert(Object.values(evidence.checks).every(Boolean));
assert.deepEqual(Object.keys(evidence.checks), EVIDENCE_CHECKS);

const currentRequirements = buildCurrentRequirements();
assert.equal(
  currentRequirements.spanishMarketSelectionComplete,
  currentRequirements.targets.some(({ catalogLocale }) => catalogLocale === 'es'),
  'Spanish audit readiness must follow the selected repository market variants',
);
if (!currentRequirements.spanishMarketSelectionComplete) {
  assert.equal(
    validateEvidence(evidence, referenceTime),
    false,
    'Evidence cannot pass until a Spanish market is selected in the repository',
  );
}

const stale = validSnapshot();
stale.capturedAt = '2026-07-20T11:30:00Z';
assert.throws(
  () => validateSnapshot(stale, requirements, referenceTime),
  /stale/,
);

const wrongCopy = validSnapshot();
wrongCopy.localizations['en-US'].metadata.subtitle += ' changed';
assert.throws(
  () => validateSnapshot(wrongCopy, requirements, referenceTime),
  /differs from repository copy/,
);

const missingProduct = validSnapshot();
missingProduct.iapProducts.pop();
assert.throws(
  () => validateSnapshot(missingProduct, requirements, referenceTime),
  /required 8 products/,
);

const missingPrice = validSnapshot();
delete missingPrice.iapProducts[0].localizedPrices.JP;
assert.throws(
  () => validateSnapshot(missingPrice, requirements, referenceTime),
  /no localized price/,
);

const noReviewScreenshot = validSnapshot();
noReviewScreenshot.iapProducts[0].reviewScreenshotAttached = false;
assert.throws(
  () => validateSnapshot(noReviewScreenshot, requirements, referenceTime),
  /App Review screenshot is missing/,
);

const unavailable = validSnapshot();
unavailable.appAvailability.territories = ['TW', 'US', 'JP'];
assert.throws(
  () => validateSnapshot(unavailable, requirements, referenceTime),
  /unavailable in required territory ES/,
);

console.log(
  'PASS: fixture snapshot validator accepts complete current evidence and rejects stale or incomplete evidence',
);
