'use strict';

const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {
  buildReadiness,
  formatReport,
  validateEvidenceConsistency,
  validateInstalledAppEvidence,
  validateNativeReviewEvidence,
  validatePurchaseEvidence,
  validateVisualEvidence,
  validateVoiceEvidence,
} = require('./i18n-release-readiness.js');

const report = buildReadiness();
const requiredLocales = ['zh-TW', 'en', 'ja', 'es'];
const requiredGates = [
  'catalogCoverage',
  'appUiIntegration',
  'sourceCopyMigration',
  'runtimeLocalization',
  'binaryLocalization',
  'nativeLanguageReview',
  'visualQA',
  'voiceIntegration',
  'voiceE2E',
  'regionalSafetyAndLegal',
  'appStoreMetadata',
  'inAppPurchaseLocalization',
  'appStoreScreenshots',
  'marketAvailability',
  'installedAppE2E',
  'purchaseE2E',
  'exactBuildEvidenceChain',
];

assert.equal(report.schema, 'munea.i18n-release-readiness.v1');
assert.equal(report.appAvailabilityAuthority, 'App Store Connect Pricing and Availability');
assert.deepEqual(Object.keys(report.locales), requiredLocales);
assert.equal(report.allReady, false, 'International release must remain closed until every gate passes');

for (const locale of requiredLocales) {
  const entry = report.locales[locale];
  assert.deepEqual(Object.keys(entry.gates), requiredGates, `${locale} gate inventory drifted`);
  assert.equal(entry.ready, false, `${locale} must not be release-ready without current evidence`);
  assert(
    entry.blockers.some(({ gate }) => gate === 'appUiIntegration'),
    `${locale} must require completed App UI integration`,
  );
  assert.equal(
    entry.gates.catalogCoverage.evidence,
    'web/src/i18n/review-manifest.json + web/src/i18n/app-surface-copy-manifest.json',
    `${locale} catalog coverage gate must include the complete App surface copy mapping`,
  );
  assert.equal(
    entry.gates.appUiIntegration.evidence,
    'web/src/i18n/app-screen-manifest.json + web/src/i18n/app-binding-manifest.json + web/src/i18n/app-surface-manifest.json',
    `${locale} App integration gate must include the complete shipping surface manifest`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'sourceCopyMigration'),
    `${locale} must remain blocked while hard-coded App WebView copy exists`,
  );
  assert.equal(
    entry.gates.sourceCopyMigration.evidence,
    'docs/I18N-SURFACE-INVENTORY.json + scripts/i18n-surface-inventory.js',
    `${locale} source-copy gate must use the shipping surface scanner`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'nativeLanguageReview'),
    `${locale} must require current catalog-bound native review evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'installedAppE2E'),
    `${locale} must require exact installed-App evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'visualQA'),
    `${locale} must require current visual evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'voiceIntegration'),
    `${locale} must require trusted Gateway and Live Voice locale integration`,
  );
  assert.equal(
    entry.gates.voiceIntegration.evidence,
    'engine/voice-locale-integration-manifest.json',
    `${locale} voice integration gate must use the canonical manifest`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'inAppPurchaseLocalization'),
    `${locale} must require current IAP localization and product evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'purchaseE2E'),
    `${locale} must require exact installed-App StoreKit evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'exactBuildEvidenceChain'),
    `${locale} must require one consistent exact-build evidence chain`,
  );
  assert.equal(
    entry.gates.nativeLanguageReview.evidence,
    `docs/qa/i18n/${locale}/native-review.json`,
    `${locale} native review evidence must use the canonical path`,
  );
  assert.equal(
    entry.gates.visualQA.evidence,
    `docs/qa/i18n/${locale}/visual-qa.json`,
    `${locale} visual evidence must use the canonical path`,
  );
  assert.equal(
    entry.gates.voiceE2E.evidence,
    `docs/qa/i18n/${locale}/voice-e2e.json`,
    `${locale} voice evidence must use the canonical path`,
  );
}

for (const locale of ['en', 'ja', 'es']) {
  const entry = report.locales[locale];
  assert.equal(entry.gates.runtimeLocalization.passed, false);
  assert.equal(entry.gates.appUiIntegration.passed, false);
  assert.equal(entry.gates.sourceCopyMigration.passed, false);
  assert.equal(entry.gates.voiceIntegration.passed, false);
  assert.equal(entry.gates.binaryLocalization.passed, false);
  assert.equal(entry.gates.appStoreScreenshots.passed, false);
  assert.equal(entry.gates.inAppPurchaseLocalization.passed, false);
  assert.equal(entry.gates.marketAvailability.passed, false);
}

assert.equal(report.locales.es.storeLocale, null, 'Spanish market variant must remain undecided');
assert(
  report.generatedFrom.includes('web/src/i18n/app-surface-copy-manifest.json'),
  'Release readiness must include the complete App surface copy mapping',
);
assert(
  report.generatedFrom.includes('scripts/i18n-visual-qa-worklist.js'),
  'Release readiness must include the exact-build visual capture worklist',
);
assert(
  formatReport(report).includes('Overall: NOT READY'),
  'Human-readable report must lead with the actual release state',
);

const exactCommit = 'a'.repeat(40);
const enCatalogPath = path.join(__dirname, '..', 'web', 'src', 'i18n', 'en.json');
const enCatalogSource = fs.readFileSync(enCatalogPath, 'utf8');
const enCatalogKeys = Object.keys(JSON.parse(enCatalogSource)).sort();
const nativeReviewEvidence = {
  schema: 'munea.i18n-native-review.v1',
  locale: 'en',
  contentVariant: 'international-English',
  result: 'pass',
  exactCommit,
  reviewedAt: '2026-07-28T08:00:00Z',
  reviewerReference: 'review-ticket-001',
  reviewerRole: 'native-language-reviewer',
  catalogSha256: crypto.createHash('sha256').update(enCatalogSource).digest('hex'),
  reviewedKeyCount: enCatalogKeys.length,
  reviewedKeysSha256: crypto.createHash('sha256').update(enCatalogKeys.join('\n')).digest('hex'),
  openIssues: 0,
  checks: Object.fromEntries([
    'meaningPreserved',
    'grammarNatural',
    'toneAppropriate',
    'culturalContextAccepted',
    'placeholderContextAccepted',
    'spokenCopyReadAloud',
  ].map((key) => [key, true])),
};
assert.equal(
  validateNativeReviewEvidence(
    nativeReviewEvidence,
    'en',
    enCatalogPath,
    'international-English',
  ),
  true,
);
assert.equal(
  validateNativeReviewEvidence(
    { ...nativeReviewEvidence, catalogSha256: '0'.repeat(64) },
    'en',
    enCatalogPath,
    'international-English',
  ),
  false,
  'Native review must expire when the reviewed catalog bytes differ',
);
const serviceRevisions = {
  brain: 'brain-revision',
  voice: 'voice-revision',
  gateway: 'gateway-revision',
  avatar: 'avatar-revision',
};
const voiceEvidence = {
  schema: 'munea.i18n-voice-e2e.v1',
  locale: 'en',
  result: 'pass',
  exactCommit,
  binarySha256: 'b'.repeat(64),
  testedAt: '2026-07-28T08:00:00Z',
  appVersion: '1.0.45',
  build: '49',
  profile: 'staging-gateway',
  environment: 'staging',
  device: 'iPhone acceptance device',
  conversationLocale: 'en',
  serviceRevisions,
  steps: {
    openingInLocale: true,
    microphoneAudioUnderstood: true,
    assistantResponseAudible: true,
    assistantResponseVisible: true,
    mixedLanguageTurn: true,
    temporaryVoiceSwitch: true,
    permanentPreferenceConfirmed: true,
  },
};
assert.equal(validateVoiceEvidence(voiceEvidence, 'en'), true);
assert.equal(
  validateVoiceEvidence({ ...voiceEvidence, steps: { openingInLocale: true } }, 'en'),
  false,
  'A partial voice flow must not pass',
);

const installedEvidence = {
  schema: 'munea.i18n-installed-app-e2e.v1',
  locale: 'en',
  result: 'pass',
  exactCommit,
  binarySha256: 'b'.repeat(64),
  testedAt: '2026-07-28T08:00:00Z',
  appVersion: '1.0.45',
  build: '49',
  profile: 'staging-gateway',
  environment: 'staging',
  device: 'iPhone acceptance device',
  serviceRevisions,
  steps: Object.fromEntries([
    'callButtonTapped',
    'microphoneGranted',
    'authPassed',
    'accountBootstrapPassed',
    'creditsPassed',
    'gatewayLeaseAcquired',
    'voiceReady',
    'avatarReady',
    'openingHeard',
    'microphoneAudioSent',
    'assistantResponseAudible',
    'assistantResponseVisible',
    'hangupReleasedCapacity',
  ].map((key) => [key, true])),
};
assert.equal(validateInstalledAppEvidence(installedEvidence, 'en'), true);
assert.equal(
  validateInstalledAppEvidence({ ...installedEvidence, binarySha256: 'unknown' }, 'en'),
  false,
  'Installed App evidence must identify the exact binary',
);

const purchaseProductIds = [
  'net.munea.app.plus.monthly',
  'net.munea.app.plus.yearly',
  'net.munea.app.pro.monthly',
  'net.munea.app.pro.yearly',
  'net.munea.app.points.200',
  'net.munea.app.points.500',
  'net.munea.app.points.1000',
  'net.munea.app.points.1800',
];
const purchaseEvidence = {
  schema: 'munea.i18n-purchase-e2e.v1',
  locale: 'en',
  result: 'pass',
  exactCommit,
  binarySha256: 'c'.repeat(64),
  testedAt: '2026-07-28T08:00:00Z',
  appVersion: '1.0.45',
  build: '49',
  profile: 'sandbox-gateway',
  environment: 'sandbox',
  device: 'iPhone acceptance device',
  storeLocale: 'en-US',
  backendRevision: 'brain-revision',
  steps: Object.fromEntries([
    'signedIn',
    'storeProductsLoaded',
    'freeMemberPointPurchaseBlocked',
    'cancelPathCreatedNoEntitlement',
    'unverifiedPathCreatedNoEntitlement',
    'activeSubscriptionRestorePassed',
  ].map((key) => [key, true])),
  products: purchaseProductIds.map((productId) => ({
    productId,
    result: 'pass',
    checks: Object.fromEntries([
      'localizedNameMatched',
      'storeKitPriceDisplayed',
      'purchaseSheetOpened',
      'serverTransactionVerified',
      'entitlementApplied',
      'transactionFinished',
      'postPurchaseStateRefreshed',
    ].map((key) => [key, true])),
  })),
};
assert.equal(validatePurchaseEvidence(purchaseEvidence, 'en', purchaseProductIds), true);
assert.equal(
  validatePurchaseEvidence(
    { ...purchaseEvidence, products: purchaseEvidence.products.slice(0, 7) },
    'en',
    purchaseProductIds,
  ),
  false,
  'Purchase evidence must cover the exact 8-product set',
);

const consistentVisualEvidence = {
  schema: 'munea.i18n-visual-qa.v1',
  locale: 'en',
  result: 'pass',
  captureCommit: exactCommit,
  binarySha256: installedEvidence.binarySha256,
  capturedAt: '2026-07-28T08:00:00Z',
  appVersion: installedEvidence.appVersion,
  build: installedEvidence.build,
};
assert.equal(
  validateEvidenceConsistency({
    visual: consistentVisualEvidence,
    voice: { ...voiceEvidence, appVersion: installedEvidence.appVersion, build: installedEvidence.build },
    installed: installedEvidence,
    purchase: {
      ...purchaseEvidence,
      appVersion: installedEvidence.appVersion,
      build: installedEvidence.build,
      binarySha256: installedEvidence.binarySha256,
      backendRevision: installedEvidence.serviceRevisions.brain,
    },
  }),
  true,
  'One exact build and service revision chain must pass',
);
assert.equal(
  validateEvidenceConsistency({
    visual: consistentVisualEvidence,
    voice: { ...voiceEvidence, appVersion: installedEvidence.appVersion, build: installedEvidence.build },
    installed: installedEvidence,
    purchase: {
      ...purchaseEvidence,
      exactCommit: 'd'.repeat(40),
      appVersion: installedEvidence.appVersion,
      build: installedEvidence.build,
      binarySha256: installedEvidence.binarySha256,
      backendRevision: installedEvidence.serviceRevisions.brain,
    },
  }),
  false,
  'Evidence from a different source commit must not be combined',
);

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'munea-i18n-visual-'));
try {
  const visualEvidencePath = path.join(tempDir, 'visual-qa.json');
  const profileSpecs = [
    ['iphone-small-standard', 375, 667],
    ['iphone-standard', 390, 844],
    ['iphone-dynamic-type-large', 390, 844],
  ];
  const captures = profileSpecs.map(([profile, width, height], index) => {
    const pngEvidence = Buffer.alloc(25);
    Buffer.from('89504e470d0a1a0a', 'hex').copy(pngEvidence, 0);
    Buffer.from('49484452', 'hex').copy(pngEvidence, 12);
    pngEvidence.writeUInt32BE(width, 16);
    pngEvidence.writeUInt32BE(height, 20);
    pngEvidence.writeUInt8(index, 24);
    const screenshot = `home-${profile}.png`;
    fs.writeFileSync(path.join(tempDir, screenshot), pngEvidence);
    return {
      profile,
      screenshot,
      sha256: crypto.createHash('sha256').update(pngEvidence).digest('hex'),
      result: 'pass',
      checks: {
        noOverflow: true,
        noClipping: true,
        noUntranslatedCopy: true,
        layoutAccepted: true,
      },
    };
  });
  const visualEvidence = {
    schema: 'munea.i18n-visual-qa.v1',
    locale: 'en',
    result: 'pass',
    captureCommit: exactCommit,
    binarySha256: installedEvidence.binarySha256,
    capturedAt: '2026-07-28T08:00:00Z',
    appVersion: '1.0.45',
    build: '49',
    profiles: profileSpecs.map(([profile]) => profile),
    screens: [{
      state: 'home',
      result: 'pass',
      captures,
    }],
  };
  assert.equal(
    validateVisualEvidence(visualEvidence, 'en', visualEvidencePath, ['home']),
    true,
  );
  assert.equal(
    validateVisualEvidence(
      { ...visualEvidence, binarySha256: 'unknown' },
      'en',
      visualEvidencePath,
      ['home'],
    ),
    false,
    'Visual evidence must identify the exact installed binary',
  );
  assert.equal(
    validateVisualEvidence(
      {
        ...visualEvidence,
        screens: [{
          ...visualEvidence.screens[0],
          captures: [
            { ...captures[0], screenshot: '../escape.png' },
            ...captures.slice(1),
          ],
        }],
      },
      'en',
      visualEvidencePath,
      ['home'],
    ),
    false,
    'Visual evidence must not reference screenshots outside its evidence directory',
  );
  assert.equal(
    validateVisualEvidence(
      {
        ...visualEvidence,
        screens: [{
          ...visualEvidence.screens[0],
          captures: captures.slice(0, 2),
        }],
      },
      'en',
      visualEvidencePath,
      ['home'],
    ),
    false,
    'Every App state must have all three real visual profiles',
  );
  const duplicateScreenshot = 'home-duplicate.png';
  fs.copyFileSync(
    path.join(tempDir, captures[0].screenshot),
    path.join(tempDir, duplicateScreenshot),
  );
  assert.equal(
    validateVisualEvidence(
      {
        ...visualEvidence,
        screens: [{
          ...visualEvidence.screens[0],
          captures: [
            captures[0],
            {
              ...captures[1],
              screenshot: duplicateScreenshot,
              sha256: captures[0].sha256,
            },
            captures[2],
          ],
        }],
      },
      'en',
      visualEvidencePath,
      ['home'],
    ),
    false,
    'Copied screenshot bytes must not be reused for another state or profile',
  );
} finally {
  fs.rmSync(tempDir, { recursive: true, force: true });
}

console.log('PASS: i18n release readiness stays evidence-gated');
