'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '..');
const I18N_DIR = path.join(ROOT, 'web', 'src', 'i18n');
const LEGAL_DIR = path.join(ROOT, 'web', 'legal');
const STORE_DIR = path.join(ROOT, 'app-store', 'localizations');
const IAP_DIR = path.join(ROOT, 'app-store', 'in-app-purchases');
const QA_DIR = path.join(ROOT, 'docs', 'qa', 'i18n');

const STORE_LOCALE_BY_CATALOG = {
  'zh-TW': 'zh-Hant',
  en: 'en-US',
  ja: 'ja',
  es: 'es',
};

const REQUIRED_VISUAL_PROFILES = [
  'iphone-small-standard',
  'iphone-standard',
  'iphone-dynamic-type-large',
];

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function validIsoDate(value) {
  return typeof value === 'string'
    && value.trim() !== ''
    && !Number.isNaN(Date.parse(value));
}

function requiredStrings(value, fields) {
  return value && fields.every((field) => (
    typeof value[field] === 'string' && value[field].trim() !== ''
  ));
}

function requiredTrue(value, fields) {
  return value && fields.every((field) => value[field] === true);
}

function validPngEvidence(filePath, expectedSha256) {
  if (!/^[0-9a-f]{64}$/i.test(expectedSha256 || '') || !fs.existsSync(filePath)) {
    return false;
  }
  const data = fs.readFileSync(filePath);
  const pngSignature = '89504e470d0a1a0a';
  return data.length >= 24
    && data.subarray(0, 8).toString('hex') === pngSignature
    && data.readUInt32BE(16) > 0
    && data.readUInt32BE(20) > 0
    && crypto.createHash('sha256').update(data).digest('hex') === expectedSha256.toLowerCase();
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function validateNativeReviewEvidence(
  evidence,
  locale,
  catalogPath,
  expectedContentVariant,
) {
  if (!fs.existsSync(catalogPath)) return false;
  const catalogSource = fs.readFileSync(catalogPath, 'utf8');
  let catalog;
  try {
    catalog = JSON.parse(catalogSource);
  } catch {
    return false;
  }
  const keys = Object.keys(catalog).sort();
  return evidence.schema === 'munea.i18n-native-review.v1'
    && evidence.locale === locale
    && evidence.contentVariant === expectedContentVariant
    && evidence.result === 'pass'
    && /^[0-9a-f]{40}$/i.test(evidence.exactCommit || '')
    && validIsoDate(evidence.reviewedAt)
    && requiredStrings(evidence, ['reviewerReference', 'reviewerRole'])
    && evidence.catalogSha256 === sha256(catalogSource)
    && evidence.reviewedKeyCount === keys.length
    && evidence.reviewedKeysSha256 === sha256(keys.join('\n'))
    && evidence.openIssues === 0
    && requiredTrue(evidence.checks, [
      'meaningPreserved',
      'grammarNatural',
      'toneAppropriate',
      'culturalContextAccepted',
      'placeholderContextAccepted',
      'spokenCopyReadAloud',
    ]);
}

function validateVisualEvidence(evidence, locale, filePath, requiredStates) {
  if (evidence.schema !== 'munea.i18n-visual-qa.v1'
      || evidence.locale !== locale
      || evidence.result !== 'pass'
      || !/^[0-9a-f]{40}$/i.test(evidence.captureCommit || '')
      || !/^[0-9a-f]{64}$/i.test(evidence.binarySha256 || '')
      || !validIsoDate(evidence.capturedAt)
      || !requiredStrings(evidence, ['appVersion', 'build'])
      || !Array.isArray(evidence.profiles)
      || evidence.profiles.length !== REQUIRED_VISUAL_PROFILES.length
      || !REQUIRED_VISUAL_PROFILES.every((profile) => evidence.profiles.includes(profile))
      || !Array.isArray(evidence.screens)) {
    return false;
  }
  if (new Set(evidence.screens.map((screen) => screen.state)).size !== evidence.screens.length) {
    return false;
  }
  const screens = new Map(evidence.screens.map((screen) => [screen.state, screen]));
  const evidenceDir = path.dirname(filePath);
  const usedScreenshots = new Set();
  for (const state of requiredStates) {
    const screen = screens.get(state);
    if (!screen
        || screen.result !== 'pass'
        || !Array.isArray(screen.captures)
        || screen.captures.length !== REQUIRED_VISUAL_PROFILES.length) {
      return false;
    }
    const captures = new Map(screen.captures.map((capture) => [capture.profile, capture]));
    if (captures.size !== screen.captures.length) return false;
    for (const profile of REQUIRED_VISUAL_PROFILES) {
      const capture = captures.get(profile);
      if (!capture
          || capture.result !== 'pass'
          || !requiredTrue(capture.checks, [
            'noOverflow',
            'noClipping',
            'noUntranslatedCopy',
            'layoutAccepted',
          ])
          || typeof capture.screenshot !== 'string') {
        return false;
      }
      const screenshotPath = path.resolve(evidenceDir, capture.screenshot);
      const relativePath = path.relative(evidenceDir, screenshotPath);
      if (!relativePath
          || relativePath.startsWith(`..${path.sep}`)
          || path.isAbsolute(relativePath)
          || !/\.png$/i.test(screenshotPath)
          || usedScreenshots.has(screenshotPath)
          || !validPngEvidence(screenshotPath, capture.sha256)) {
        return false;
      }
      usedScreenshots.add(screenshotPath);
    }
  }
  return true;
}

function validateVoiceEvidence(evidence, locale) {
  return evidence.schema === 'munea.i18n-voice-e2e.v1'
    && evidence.locale === locale
    && evidence.result === 'pass'
    && /^[0-9a-f]{40}$/i.test(evidence.exactCommit || '')
    && /^[0-9a-f]{64}$/i.test(evidence.binarySha256 || '')
    && validIsoDate(evidence.testedAt)
    && requiredStrings(evidence, [
      'appVersion',
      'build',
      'profile',
      'environment',
      'device',
      'conversationLocale',
    ])
    && requiredStrings(evidence.serviceRevisions, [
      'brain',
      'voice',
      'gateway',
      'avatar',
    ])
    && requiredTrue(evidence.steps, [
      'openingInLocale',
      'microphoneAudioUnderstood',
      'assistantResponseAudible',
      'assistantResponseVisible',
      'mixedLanguageTurn',
      'temporaryVoiceSwitch',
      'permanentPreferenceConfirmed',
    ]);
}

function validateInstalledAppEvidence(evidence, locale) {
  return evidence.schema === 'munea.i18n-installed-app-e2e.v1'
    && evidence.locale === locale
    && evidence.result === 'pass'
    && /^[0-9a-f]{40}$/i.test(evidence.exactCommit || '')
    && /^[0-9a-f]{64}$/i.test(evidence.binarySha256 || '')
    && validIsoDate(evidence.testedAt)
    && requiredStrings(evidence, [
      'appVersion',
      'build',
      'profile',
      'environment',
      'device',
    ])
    && requiredStrings(evidence.serviceRevisions, [
      'brain',
      'voice',
      'gateway',
      'avatar',
    ])
    && requiredTrue(evidence.steps, [
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
    ]);
}

function validatePurchaseEvidence(evidence, locale, requiredProductIds) {
  if (evidence.schema !== 'munea.i18n-purchase-e2e.v1'
      || evidence.locale !== locale
      || evidence.result !== 'pass'
      || !/^[0-9a-f]{40}$/i.test(evidence.exactCommit || '')
      || !/^[0-9a-f]{64}$/i.test(evidence.binarySha256 || '')
      || !validIsoDate(evidence.testedAt)
      || !requiredStrings(evidence, [
        'appVersion',
        'build',
        'profile',
        'environment',
        'device',
        'storeLocale',
        'backendRevision',
      ])
      || !requiredTrue(evidence.steps, [
        'signedIn',
        'storeProductsLoaded',
        'freeMemberPointPurchaseBlocked',
        'cancelPathCreatedNoEntitlement',
        'unverifiedPathCreatedNoEntitlement',
        'activeSubscriptionRestorePassed',
      ])
      || !Array.isArray(evidence.products)) {
    return false;
  }
  const expected = [...requiredProductIds].sort();
  const actual = evidence.products.map(({ productId }) => productId).sort();
  if (actual.length !== new Set(actual).size
      || JSON.stringify(actual) !== JSON.stringify(expected)) {
    return false;
  }
  return evidence.products.every((product) => (
    product.result === 'pass'
    && requiredTrue(product.checks, [
      'localizedNameMatched',
      'storeKitPriceDisplayed',
      'purchaseSheetOpened',
      'serverTransactionVerified',
      'entitlementApplied',
      'transactionFinished',
      'postPurchaseStateRefreshed',
    ])
  ));
}

function validateEvidenceConsistency(evidenceSet) {
  const source = evidenceSet || {};
  const visual = source.visual;
  const voice = source.voice;
  const installed = source.installed;
  const purchase = source.purchase;
  if (!visual || !voice || !installed || !purchase) return false;
  const exactCommit = installed.exactCommit;
  const appVersion = installed.appVersion;
  const build = installed.build;
  const sameServiceRevisions = ['brain', 'voice', 'gateway', 'avatar']
    .every((service) => (
      voice.serviceRevisions
      && installed.serviceRevisions
      && voice.serviceRevisions[service] === installed.serviceRevisions[service]
    ));
  return visual.captureCommit === exactCommit
    && voice.exactCommit === exactCommit
    && purchase.exactCommit === exactCommit
    && [visual, voice, purchase].every((evidence) => (
      evidence.appVersion === appVersion && evidence.build === build
    ))
    && visual.binarySha256 === installed.binarySha256
    && voice.binarySha256 === installed.binarySha256
    && purchase.binarySha256 === installed.binarySha256
    && purchase.backendRevision === installed.serviceRevisions.brain
    && sameServiceRevisions;
}

function evidenceResult(locale, filename, validator) {
  const filePath = path.join(QA_DIR, locale, filename);
  if (!fs.existsSync(filePath)) {
    return { exists: false, passed: false, path: path.relative(ROOT, filePath).replaceAll('\\', '/') };
  }
  try {
    const evidence = readJson(filePath);
    return {
      exists: true,
      passed: validator(evidence, locale, filePath),
      path: path.relative(ROOT, filePath).replaceAll('\\', '/'),
      evidence,
    };
  } catch (error) {
    return {
      exists: true,
      passed: false,
      path: path.relative(ROOT, filePath).replaceAll('\\', '/'),
      error: error.message,
    };
  }
}

function check(condition, reason, evidence) {
  return { passed: Boolean(condition), reason, evidence };
}

function buildReadiness() {
  const catalogManifest = readJson(path.join(I18N_DIR, 'catalog-manifest.json'));
  const reviewManifest = readJson(path.join(I18N_DIR, 'review-manifest.json'));
  const screenManifest = readJson(path.join(I18N_DIR, 'app-screen-manifest.json'));
  const bindingManifest = readJson(path.join(I18N_DIR, 'app-binding-manifest.json'));
  const surfaceManifest = readJson(path.join(I18N_DIR, 'app-surface-manifest.json'));
  const legalManifest = readJson(path.join(LEGAL_DIR, 'manifest.json'));
  const storeManifest = readJson(path.join(STORE_DIR, 'manifest.json'));
  const iapManifest = readJson(path.join(IAP_DIR, 'manifest.json'));
  const requiredVisualStates = surfaceManifest.surfaces.map(({ state }) => state);
  const catalogEntries = new Map(
    catalogManifest.locales.map((entry) => [entry.locale, entry]),
  );
  const requiredProductIds = iapManifest.productSet.products.map(({ productId }) => productId);

  const locales = {};
  for (const locale of Object.keys(reviewManifest.locales)) {
    const catalog = catalogEntries.get(locale);
    const review = reviewManifest.locales[locale];
    const legal = legalManifest.locales[locale];
    const storeKey = STORE_LOCALE_BY_CATALOG[locale];
    const store = storeManifest.locales[storeKey];
    const iapLocale = iapManifest.locales[locale];
    const catalogPath = path.join(I18N_DIR, catalog.catalog);
    const nativeReviewEvidence = evidenceResult(
      locale,
      'native-review.json',
      (evidence, evidenceLocale) => validateNativeReviewEvidence(
        evidence,
        evidenceLocale,
        catalogPath,
        review.contentVariant,
      ),
    );
    const visualEvidence = evidenceResult(
      locale,
      'visual-qa.json',
      (evidence, evidenceLocale, filePath) => (
        validateVisualEvidence(evidence, evidenceLocale, filePath, requiredVisualStates)
      ),
    );
    const voiceEvidence = evidenceResult(locale, 'voice-e2e.json', validateVoiceEvidence);
    const installedEvidence = evidenceResult(
      locale,
      'installed-app-e2e.json',
      validateInstalledAppEvidence,
    );
    const purchaseEvidence = evidenceResult(
      locale,
      'purchase-e2e.json',
      (evidence, evidenceLocale) => (
        validatePurchaseEvidence(evidence, evidenceLocale, requiredProductIds)
      ),
    );

    const gates = {
      catalogCoverage: check(
        review.catalogCoverage === 'approved',
        'catalog coverage review must be approved',
        'web/src/i18n/review-manifest.json',
      ),
      appUiIntegration: check(
        screenManifest.bindingStatus === 'integrated'
          && bindingManifest.integrationStatus === 'integrated'
          && surfaceManifest.integrationStatus === 'integrated'
          && surfaceManifest.surfaces.every(({ localizationStatus }) => (
            localizationStatus === 'integrated'
          )),
        'all shipping App surfaces, dynamic renderers, and markup refactors must be wired to catalog keys',
        'web/src/i18n/app-screen-manifest.json + web/src/i18n/app-binding-manifest.json + web/src/i18n/app-surface-manifest.json',
      ),
      runtimeLocalization: check(
        catalog.runtimeEnabled === true,
        'locale runtime must be enabled only after all release gates',
        'web/src/i18n/catalog-manifest.json',
      ),
      binaryLocalization: check(
        catalog.binaryLocalizationEnabled === true,
        'locale must be included in the exact iOS binary',
        'web/src/i18n/catalog-manifest.json',
      ),
      nativeLanguageReview: check(
        review.nativeLanguageReview === 'approved' && nativeReviewEvidence.passed,
        'native-language review needs approval plus evidence bound to the current complete catalog',
        nativeReviewEvidence.path,
      ),
      visualQA: check(
        review.visualQA === 'approved' && visualEvidence.passed,
        'visual QA needs approval plus current screenshot evidence',
        visualEvidence.path,
      ),
      voiceE2E: check(
        review.voiceE2E === 'approved' && voiceEvidence.passed,
        'voice E2E needs approval plus current real-call evidence',
        voiceEvidence.path,
      ),
      regionalSafetyAndLegal: check(
        review.regionalSafetyAndLegal === 'approved'
          && legal.legalReview === 'approved'
          && store.publicUrlStatus === 'deployed-and-verified',
        'regional safety, legal review, and public legal URLs must all be verified',
        'web/legal/manifest.json',
      ),
      appStoreMetadata: check(
        review.appStoreMetadata === 'approved'
          && store.metadataReview === 'approved',
        'App Store metadata must be reviewed for the selected locale variant',
        'app-store/localizations/manifest.json',
      ),
      inAppPurchaseLocalization: check(
        review.inAppPurchaseLocalization === 'approved'
          && iapLocale.metadataReview === 'approved'
          && iapManifest.productSet.appStoreConnectStatus === 'verified'
          && iapManifest.productSet.products.every((product) => (
            product.reviewScreenshotStatus === 'approved'
          )),
        'all 8 IAP products need approved localized copy, current App Store identity, and review screenshots',
        'app-store/in-app-purchases/manifest.json',
      ),
      appStoreScreenshots: check(
        store.screenshotStatus === 'approved',
        'localized App Store screenshots must be approved',
        'app-store/localizations/manifest.json',
      ),
      marketAvailability: check(
        review.marketAvailability === 'approved'
          && store.promotionAuthorized === true
          && storeManifest.appAvailability.currentState === 'verified'
          && iapManifest.availability.currentState === 'verified'
          && iapManifest.pricePolicy.appStoreConnectStatus === 'verified',
        'App and all IAP storefront availability and prices must be verified before promotion',
        'app-store/localizations/manifest.json + app-store/in-app-purchases/manifest.json',
      ),
      installedAppE2E: check(
        installedEvidence.passed,
        'the exact installed iPhone build must pass the full App acceptance gate',
        installedEvidence.path,
      ),
      purchaseE2E: check(
        purchaseEvidence.passed,
        'the exact installed iPhone build must pass all 8 StoreKit Sandbox purchase paths',
        purchaseEvidence.path,
      ),
      exactBuildEvidenceChain: check(
        visualEvidence.passed
          && voiceEvidence.passed
          && installedEvidence.passed
          && purchaseEvidence.passed
          && validateEvidenceConsistency({
            visual: visualEvidence.evidence,
            voice: voiceEvidence.evidence,
            installed: installedEvidence.evidence,
            purchase: purchaseEvidence.evidence,
          }),
        'visual, voice, installed-App, and purchase evidence must identify the same commit, App version, build, binary, and service revisions',
        `docs/qa/i18n/${locale}/`,
      ),
    };

    const blockers = Object.entries(gates)
      .filter(([, gate]) => !gate.passed)
      .map(([gate, value]) => ({ gate, reason: value.reason, evidence: value.evidence }));
    locales[locale] = {
      contentVariant: review.contentVariant,
      storeLocale: store.appStoreLocale,
      ready: blockers.length === 0,
      blockers,
      gates,
    };
  }

  return {
    schema: 'munea.i18n-release-readiness.v1',
    generatedFrom: [
      'web/src/i18n/catalog-manifest.json',
      'web/src/i18n/review-manifest.json',
      'web/src/i18n/app-screen-manifest.json',
      'web/src/i18n/app-binding-manifest.json',
      'web/src/i18n/app-surface-manifest.json',
      'web/legal/manifest.json',
      'app-store/localizations/manifest.json',
      'app-store/in-app-purchases/manifest.json',
      'docs/qa/i18n/<locale>/*.json',
    ],
    appAvailabilityAuthority: storeManifest.appAvailability.sourceOfTruth,
    locales,
    allReady: Object.values(locales).every((entry) => entry.ready),
  };
}

function formatReport(report) {
  const lines = [
    'Munea i18n release readiness',
    `Overall: ${report.allReady ? 'READY' : 'NOT READY'}`,
  ];
  for (const [locale, entry] of Object.entries(report.locales)) {
    lines.push(`${locale}: ${entry.ready ? 'READY' : `BLOCKED (${entry.blockers.length})`}`);
    for (const blocker of entry.blockers) {
      lines.push(`  - ${blocker.gate}: ${blocker.reason} [${blocker.evidence}]`);
    }
  }
  return lines.join('\n');
}

if (require.main === module) {
  const report = buildReadiness();
  process.stdout.write(`${formatReport(report)}\n`);
  if (process.argv.includes('--json')) {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  }
  if (process.argv.includes('--strict') && !report.allReady) {
    process.exitCode = 1;
  }
}

module.exports = {
  buildReadiness,
  formatReport,
  validateInstalledAppEvidence,
  validateEvidenceConsistency,
  validateNativeReviewEvidence,
  validatePurchaseEvidence,
  validateVisualEvidence,
  validateVoiceEvidence,
};
