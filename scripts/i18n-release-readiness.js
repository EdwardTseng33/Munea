'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { buildReport: buildSurfaceReport } = require('./i18n-surface-inventory.js');
const {
  pngDimensions,
  profileDimensionsMatch,
} = require('./i18n-visual-qa-evidence.js');
const {
  validateAppStoreNativeReviewEvidence,
} = require('./app-store-native-review-evidence.js');
const {
  validateEvidence: validateAppStoreConnectEvidence,
} = require('./app-store-connect-i18n-evidence.js');
const {
  validateRepositoryStoreAssets,
} = require('./app-store-metadata-limits.js');

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

function evidenceWithinAge(value, maximumAgeHours, referenceTime = new Date()) {
  if (
    !validIsoDate(value)
    || !Number.isFinite(maximumAgeHours)
    || maximumAgeHours <= 0
  ) return false;
  const referenceMs = referenceTime instanceof Date
    ? referenceTime.getTime()
    : Date.parse(referenceTime);
  if (!Number.isFinite(referenceMs)) return false;
  const evidenceMs = Date.parse(value);
  const futureClockSkewMs = 5 * 60 * 1000;
  return evidenceMs <= referenceMs + futureClockSkewMs
    && referenceMs - evidenceMs <= maximumAgeHours * 60 * 60 * 1000;
}

function requiredStrings(value, fields) {
  return value && fields.every((field) => (
    typeof value[field] === 'string' && value[field].trim() !== ''
  ));
}

function requiredTrue(value, fields) {
  return value && fields.every((field) => value[field] === true);
}

function validPngEvidence(filePath, expectedSha256, profile) {
  if (!/^[0-9a-f]{64}$/i.test(expectedSha256 || '') || !fs.existsSync(filePath)) {
    return false;
  }
  try {
    const data = fs.readFileSync(filePath);
    const dimensions = pngDimensions(data);
    return profileDimensionsMatch(profile, dimensions.width, dimensions.height)
      && crypto.createHash('sha256').update(data).digest('hex')
        === expectedSha256.toLowerCase();
  } catch {
    return false;
  }
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
      || !Number.isSafeInteger(evidence.binaryBytes)
      || evidence.binaryBytes <= 0
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
  const usedScreenshotHashes = new Set();
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
          || usedScreenshotHashes.has(String(capture.sha256 || '').toLowerCase())
          || !validPngEvidence(screenshotPath, capture.sha256, profile)) {
        return false;
      }
      usedScreenshots.add(screenshotPath);
      usedScreenshotHashes.add(capture.sha256.toLowerCase());
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
    && Number.isSafeInteger(evidence.binaryBytes)
    && evidence.binaryBytes > 0
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
  const runtimeIdentity = evidence && evidence.runtimeIdentity;
  return evidence.schema === 'munea.i18n-installed-app-e2e.v1'
    && evidence.locale === locale
    && evidence.result === 'pass'
    && /^[0-9a-f]{40}$/i.test(evidence.exactCommit || '')
    && /^[0-9a-f]{64}$/i.test(evidence.binarySha256 || '')
    && Number.isSafeInteger(evidence.binaryBytes)
    && evidence.binaryBytes > 0
    && runtimeIdentity
    && runtimeIdentity.schema === 'munea.ios-build-identity.v1'
    && runtimeIdentity.bundleIdentifier === 'net.munea.app'
    && runtimeIdentity.exactCommit === evidence.exactCommit
    && runtimeIdentity.appVersion === evidence.appVersion
    && runtimeIdentity.build === evidence.build
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
      || !Number.isSafeInteger(evidence.binaryBytes)
      || evidence.binaryBytes <= 0
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
    && visual.binaryBytes === installed.binaryBytes
    && voice.binaryBytes === installed.binaryBytes
    && purchase.binaryBytes === installed.binaryBytes
    && purchase.backendRevision === installed.serviceRevisions.brain
    && sameServiceRevisions;
}

function validateLocaleDataEvidence(evidence, readinessManifest, referenceTime = new Date()) {
  const required = readinessManifest && readinessManifest.requiredEvidence;
  const summary = evidence && evidence.summary;
  const privacy = evidence && evidence.outputPrivacy;
  const source = evidence && evidence.sourceExport;
  if (!required || !summary || !privacy || !source) return false;
  return evidence.schema === 'munea.locale-context-data-audit.v1'
    && evidence.result === 'pass'
    && /^[0-9a-f]{40}$/i.test(evidence.sourceCommit || '')
    && validIsoDate(evidence.generatedAt)
    && evidenceWithinAge(evidence.generatedAt, required.maximumAgeHours, referenceTime)
    && source.schema === 'munea.locale-context-data-export.v1'
    && source.sourceCommit === evidence.sourceCommit
    && validIsoDate(source.generatedAt)
    && evidenceWithinAge(source.generatedAt, required.maximumAgeHours, referenceTime)
    && Date.parse(source.generatedAt) <= Date.parse(evidence.generatedAt)
    && source.environment === required.environment
    && source.captureMode === required.captureMode
    && source.writesPerformed === required.writesPerformed
    && Number.isInteger(summary.recordCount)
    && summary.recordCount >= summary.activeRecordCount
    && Number.isInteger(summary.activeRecordCount)
    && summary.activeRecordCount >= required.minimumActiveRecords
    && summary.completeActiveRecords === summary.activeRecordCount
    && summary.invalidActiveRecords === required.invalidActiveRecords
    && summary.accountIsolationFailures === required.accountIsolationFailures
    && summary.exportIssueCount === required.exportIssueCount
    && summary.explicitCoverage === required.explicitCoverage
    && privacy.containsDirectIdentifiers === required.containsDirectIdentifiers
    && privacy.containsNames === required.containsNames
    && privacy.containsContactDetails === required.containsContactDetails
    && privacy.recordReferencesAreOrdinalOnly === required.recordReferencesAreOrdinalOnly
    && Array.isArray(evidence.exportIssues)
    && evidence.exportIssues.length === 0
    && Array.isArray(evidence.records)
    && evidence.records.length === summary.recordCount
    && evidence.records.every((record, index) => (
      record.record === `record-${String(index + 1).padStart(4, '0')}`
      && typeof record.active === 'boolean'
      && record.status === 'complete'
      && Array.isArray(record.issues)
      && record.issues.length === 0
    ));
}

function validateMemberDataIsolationEvidence(
  evidence,
  readinessManifest,
  referenceTime = new Date(),
) {
  const required = readinessManifest && readinessManifest.requiredEvidence;
  const requiredScenarios = readinessManifest && readinessManifest.requiredScenarios;
  const requiredChecks = readinessManifest && readinessManifest.requiredChecks;
  const scope = evidence && evidence.scope;
  if (
    !required
    || !Array.isArray(requiredScenarios)
    || !Array.isArray(requiredChecks)
  ) return false;
  const checks = Array.isArray(evidence && evidence.checks) ? evidence.checks : [];
  const checkNames = checks.map((check) => check && check.name);
  const checksByName = new Map(checks.map((check) => [check && check.name, check]));
  const checkContractPassed = (
    checks.length === requiredChecks.length
    && new Set(checkNames).size === checkNames.length
    && requiredChecks.every((contract) => {
      const check = checksByName.get(contract.name);
      return check
        && check.result === 'pass'
        && Number.isInteger(check.statusCode)
        && Array.isArray(contract.allowedStatusCodes)
        && contract.allowedStatusCodes.includes(check.statusCode)
        && (
          !Object.hasOwn(contract, 'rowCount')
          || check.rowCount === contract.rowCount
        )
        && (
          !Object.hasOwn(contract, 'commitMatched')
          || check.commitMatched === contract.commitMatched
        );
    })
  );
  return evidence.schema === 'munea.member-data-isolation-e2e.v1'
    && evidence.result === 'pass'
    && /^[0-9a-f]{40}$/i.test(evidence.exactCommit || '')
    && validIsoDate(evidence.testedAt)
    && evidenceWithinAge(evidence.testedAt, required.maximumAgeHours, referenceTime)
    && evidence.environment === required.environment
    && evidence.captureMode === required.captureMode
    && evidence.realMemberDataUsed === required.realMemberDataUsed
    && evidence.productionWritesPerformed === required.productionWritesPerformed
    && evidence.fixtureAccounts === required.fixtureAccounts
    && evidence.fixtureLifecycleReviewed === required.fixtureLifecycleReviewed
    && evidence.containsSecrets === required.containsSecrets
    && evidence.containsPersonalData === required.containsPersonalData
    && requiredStrings(evidence, [
      'stagingIdentitySchema',
      'stagingService',
      'stagingEnvironment',
      'stagingCommit',
      'stagingRevision',
      'stagingProjectRef',
      'evidenceReference',
      'fixtureLifecycleReference',
    ])
    && evidence.stagingIdentitySchema === 'munea.service-release.v1'
    && evidence.stagingService === 'brain'
    && evidence.stagingEnvironment === 'staging'
    && evidence.stagingCommit === evidence.exactCommit
    && /^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$/.test(evidence.stagingRevision)
    && evidence.stagingRevision.toLowerCase() !== 'unknown'
    && !['fespbkdwafueyonppzwq', 'uhmpmystjjdqqxlpsthc'].includes(
      evidence.stagingProjectRef,
    )
    && scope
    && scope.directSupabaseRls === true
    && scope.brainServiceRoleAuthorization === true
    && scope.writesAttempted === false
    && scope.productionTargetsForbidden === true
    && scope.responsePayloadsStored === false
    && evidence.scenarios
    && requiredScenarios.every((scenario) => evidence.scenarios[scenario] === true)
    && checkContractPassed;
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
  const copyManifest = readJson(path.join(I18N_DIR, 'app-surface-copy-manifest.json'));
  const voiceIntegrationManifest = readJson(
    path.join(ROOT, 'engine', 'voice-locale-integration-manifest.json'),
  );
  const legalManifest = readJson(path.join(LEGAL_DIR, 'manifest.json'));
  const regionalSafetyPolicy = readJson(
    path.join(LEGAL_DIR, 'regional-safety-policy.json'),
  );
  const storeManifest = readJson(path.join(STORE_DIR, 'manifest.json'));
  const iapManifest = readJson(path.join(IAP_DIR, 'manifest.json'));
  const appStoreConnectRequirements = readJson(
    path.join(ROOT, 'app-store', 'connect-audit-requirements.json'),
  );
  const appStoreConnectEvidencePath = path.resolve(
    ROOT,
    appStoreConnectRequirements.evidencePath,
  );
  const appStoreConnectEvidenceInsideRoot = appStoreConnectEvidencePath
    .startsWith(`${ROOT}${path.sep}`);
  let appStoreConnectEvidencePassed = false;
  if (
    appStoreConnectEvidenceInsideRoot
    && fs.existsSync(appStoreConnectEvidencePath)
  ) {
    try {
      appStoreConnectEvidencePassed = validateAppStoreConnectEvidence(
        readJson(appStoreConnectEvidencePath),
      );
    } catch {
      appStoreConnectEvidencePassed = false;
    }
  }
  const appStoreConnectEvidenceRelativePath = path.relative(
    ROOT,
    appStoreConnectEvidencePath,
  ).replaceAll('\\', '/');
  const localeDataManifest = readJson(
    path.join(ROOT, 'docs', 'LOCALE-CONTEXT-DATA-READINESS.json'),
  );
  const memberDataIsolationManifest = readJson(
    path.join(ROOT, 'docs', 'MEMBER-DATA-ISOLATION-READINESS.json'),
  );
  const localeDataEvidencePath = path.resolve(ROOT, localeDataManifest.evidencePath);
  const localeDataEvidenceInsideRoot = localeDataEvidencePath.startsWith(`${ROOT}${path.sep}`);
  let localeDataEvidencePassed = false;
  if (
    localeDataManifest.status === 'approved'
    && localeDataManifest.productionMutationAuthorized === false
    && localeDataEvidenceInsideRoot
    && fs.existsSync(localeDataEvidencePath)
  ) {
    try {
      localeDataEvidencePassed = validateLocaleDataEvidence(
        readJson(localeDataEvidencePath),
        localeDataManifest,
      );
    } catch {
      localeDataEvidencePassed = false;
    }
  }
  const memberDataIsolationEvidencePath = path.resolve(
    ROOT,
    memberDataIsolationManifest.evidencePath,
  );
  const memberDataIsolationEvidenceInsideRoot = memberDataIsolationEvidencePath
    .startsWith(`${ROOT}${path.sep}`);
  let memberDataIsolationEvidencePassed = false;
  if (
    memberDataIsolationManifest.status === 'approved'
    && memberDataIsolationManifest.productionMutationAuthorized === false
    && memberDataIsolationEvidenceInsideRoot
    && fs.existsSync(memberDataIsolationEvidencePath)
  ) {
    try {
      memberDataIsolationEvidencePassed = validateMemberDataIsolationEvidence(
        readJson(memberDataIsolationEvidencePath),
        memberDataIsolationManifest,
      );
    } catch {
      memberDataIsolationEvidencePassed = false;
    }
  }
  const surfaceReport = buildSurfaceReport();
  const appWebViewSurface = surfaceReport.surfaces.find(({ id }) => id === 'app-webview');
  if (!appWebViewSurface) throw new Error('i18n app-webview surface inventory is missing');
  const requiredVisualStates = surfaceManifest.surfaces.map(({ state }) => state);
  const catalogEntries = new Map(
    catalogManifest.locales.map((entry) => [entry.locale, entry]),
  );
  const requiredProductIds = iapManifest.productSet.products.map(({ productId }) => productId);
  const storeTechnicalValidation = validateRepositoryStoreAssets();

  const locales = {};
  for (const locale of Object.keys(reviewManifest.locales)) {
    const catalog = catalogEntries.get(locale);
    const review = reviewManifest.locales[locale];
    const legal = legalManifest.locales[locale];
    const storeKey = STORE_LOCALE_BY_CATALOG[locale];
    const store = storeManifest.locales[storeKey];
    const iapLocale = iapManifest.locales[locale];
    const selectedStoreVariants = locale === 'es'
      ? (store.selectedVariants || []).map((variantKey) => ({
        key: variantKey,
        store: store.marketVariants && store.marketVariants[variantKey],
        iap: iapLocale.marketVariants && iapLocale.marketVariants[variantKey],
        nativeReviewEvidence: evidenceResult(
          variantKey,
          'app-store-native-review.json',
          (evidence) => validateAppStoreNativeReviewEvidence(evidence, variantKey),
        ),
        legal: legal.regionalVariants
          && legal.regionalVariants[
            store.marketVariants
            && store.marketVariants[variantKey]
            && store.marketVariants[variantKey].legalRegion
          ],
        policy: Object.values(regionalSafetyPolicy.regions).find(
          ({ appStoreLocale }) => appStoreLocale === variantKey,
        ),
      }))
      : [];
    const spanishSelectionValid = locale !== 'es' || (
      selectedStoreVariants.length > 0
      && selectedStoreVariants.length === new Set(
        selectedStoreVariants.map(({ key }) => key),
      ).size
      && selectedStoreVariants.every(({ store: variantStore, iap, legal: regionalLegal, policy }) => (
        variantStore && iap && regionalLegal && policy
      ))
    );
    const metadataApproved = locale === 'es'
      ? spanishSelectionValid
        && selectedStoreVariants.every(({ store: variantStore }) => (
          variantStore.metadataReview === 'approved'
        ))
      : store.metadataReview === 'approved';
    const publicUrlsVerified = locale === 'es'
      ? spanishSelectionValid
        && selectedStoreVariants.every(({ store: variantStore }) => (
          variantStore.publicUrlStatus === 'deployed-and-verified'
        ))
      : store.publicUrlStatus === 'deployed-and-verified';
    const screenshotsApproved = locale === 'es'
      ? spanishSelectionValid
        && selectedStoreVariants.every(({ store: variantStore }) => (
          variantStore.screenshotStatus === 'approved'
        ))
      : store.screenshotStatus === 'approved';
    const regionalPolicyApproved = locale === 'es'
      ? spanishSelectionValid
        && selectedStoreVariants.every(({ legal: regionalLegal, policy }) => (
          regionalLegal.legalReview === 'approved'
          && policy.legalReview === 'approved'
          && policy.emergencyNumberReview === 'official-source-verified'
        ))
      : legal.legalReview === 'approved';
    const iapMetadataApproved = locale === 'es'
      ? spanishSelectionValid
        && selectedStoreVariants.every(({ iap }) => iap.metadataReview === 'approved')
      : iapLocale.metadataReview === 'approved';
    const storeTechnicalTargets = locale === 'es'
      ? ['es-ES', 'es-MX']
      : [locale];
    const storeTechnicalValidationPassed = storeTechnicalTargets.every((target) => (
      storeTechnicalValidation.targets[target]
      && storeTechnicalValidation.targets[target].valid
    ));
    const storeNativeReviewEvidence = locale === 'es'
      ? null
      : evidenceResult(
        locale,
        'app-store-native-review.json',
        (evidence) => validateAppStoreNativeReviewEvidence(evidence, locale),
      );
    const storeNativeReviewPassed = locale === 'es'
      ? spanishSelectionValid
        && selectedStoreVariants.every(({ nativeReviewEvidence }) => (
          nativeReviewEvidence.passed
        ))
      : storeNativeReviewEvidence.passed;
    const storeNativeReviewEvidencePath = locale === 'es'
      ? (
        selectedStoreVariants.length > 0
          ? selectedStoreVariants
            .map(({ nativeReviewEvidence }) => nativeReviewEvidence.path)
            .join(' + ')
          : 'docs/qa/i18n/<selected-es-variant>/app-store-native-review.json'
      )
      : storeNativeReviewEvidence.path;
    const promotionAuthorized = locale === 'es'
      ? spanishSelectionValid
        && selectedStoreVariants.every(({ store: variantStore, iap, policy }) => (
          variantStore.promotionAuthorized === true
          && iap.availabilityAuthorized === true
          && policy.availabilityAuthorized === true
        ))
      : store.promotionAuthorized === true;
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
        review.catalogCoverage === 'approved'
          && copyManifest.catalogStatus === 'complete-for-current-surface-inventory',
        'catalog coverage review and complete App surface copy mapping must be approved',
        'web/src/i18n/review-manifest.json + web/src/i18n/app-surface-copy-manifest.json',
      ),
      appUiIntegration: check(
        screenManifest.bindingStatus === 'integrated'
          && bindingManifest.integrationStatus === 'integrated'
          && bindingManifest.dynamicContentObserver === 'integrated'
          && surfaceManifest.integrationStatus === 'integrated'
          && surfaceManifest.surfaces.every(({ localizationStatus }) => (
            localizationStatus === 'integrated'
          )),
        'all shipping App surfaces, dynamic renderers, and markup refactors must be wired to catalog keys',
        'web/src/i18n/app-screen-manifest.json + web/src/i18n/app-binding-manifest.json + web/src/i18n/app-surface-manifest.json',
      ),
      sourceCopyMigration: check(
        appWebViewSurface.unboundHanCandidates === 0,
        'all unbound App WebView copy must be moved into catalogs before release',
        'docs/I18N-SURFACE-INVENTORY.json + docs/I18N-NON-USER-FACING-REVIEW.json + scripts/i18n-surface-inventory.js',
      ),
      localeDataReadiness: check(
        localeDataEvidencePassed,
        'active production records need explicit LocaleContext policy and zero account-isolation failures from a redacted read-only audit',
        'docs/LOCALE-CONTEXT-DATA-READINESS.json + docs/qa/i18n/locale-context-data-audit.json',
      ),
      memberDataIsolation: check(
        memberDataIsolationEvidencePassed,
        'two isolated staging tenants must prove that RLS and Brain service-role handlers both deny cross-account data access',
        'docs/MEMBER-DATA-ISOLATION-READINESS.json + docs/qa/i18n/member-data-isolation-e2e.json',
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
      voiceIntegration: check(
        voiceIntegrationManifest.bridgeStatus === 'integrated'
          && voiceIntegrationManifest.appRequestPolicyStatus === 'integrated'
          && voiceIntegrationManifest.preHandlerPipelineContractStatus === 'integrated'
          && voiceIntegrationManifest.appRequestPolicyWiringStatus === 'integrated'
          && voiceIntegrationManifest.liveVoiceServerStatus === 'integrated'
          && voiceIntegrationManifest.gatewayResolverStatus === 'integrated'
          && voiceIntegrationManifest.gatewayClaimsStatus === 'integrated'
          && voiceIntegrationManifest.legacyTokenMode === 'disabled',
        'The pre-handler LocaleContext contract, Gateway claims, and Live Voice must consume the trusted locale session bridge with legacy mode disabled',
        'engine/voice-locale-integration-manifest.json',
      ),
      voiceE2E: check(
        review.voiceE2E === 'approved' && voiceEvidence.passed,
        'voice E2E needs approval plus current real-call evidence',
        voiceEvidence.path,
      ),
      regionalSafetyAndLegal: check(
        review.regionalSafetyAndLegal === 'approved'
          && regionalPolicyApproved
          && publicUrlsVerified,
        'regional safety, legal review, and public legal URLs must all be verified',
        'web/legal/manifest.json + web/legal/regional-safety-policy.json',
      ),
      appStoreTechnicalValidation: check(
        storeTechnicalValidationPassed,
        'App Store and all 8 IAP localized fields must satisfy Apple character, byte, URL, and plain-text rules',
        'scripts/app-store-metadata-limits.js + app-store/localizations/ + app-store/in-app-purchases/',
      ),
      appStoreMetadata: check(
        review.appStoreMetadata === 'approved'
          && storeTechnicalValidationPassed
          && metadataApproved
          && storeNativeReviewPassed
          && appStoreConnectEvidencePassed,
        'App Store metadata needs byte-bound native review plus a fresh read-only App Store Connect match',
        `${storeNativeReviewEvidencePath} + ${appStoreConnectEvidenceRelativePath}`,
      ),
      inAppPurchaseLocalization: check(
        review.inAppPurchaseLocalization === 'approved'
          && storeTechnicalValidationPassed
          && iapMetadataApproved
          && storeNativeReviewPassed
          && appStoreConnectEvidencePassed
          && iapManifest.productSet.appStoreConnectStatus === 'verified'
          && iapManifest.productSet.products.every((product) => (
            product.reviewScreenshotStatus === 'approved'
          )),
        'all 8 IAP products need byte-bound native review, fresh App Store Connect identity, and review screenshots',
        `${storeNativeReviewEvidencePath} + ${appStoreConnectEvidenceRelativePath}`,
      ),
      appStoreScreenshots: check(
        screenshotsApproved,
        'localized App Store screenshots must be approved',
        'app-store/localizations/manifest.json',
      ),
      marketAvailability: check(
        review.marketAvailability === 'approved'
          && promotionAuthorized
          && appStoreConnectEvidencePassed
          && storeManifest.appAvailability.currentState === 'verified'
          && iapManifest.availability.currentState === 'verified'
          && iapManifest.pricePolicy.appStoreConnectStatus === 'verified',
        'App and all IAP storefront availability and localized prices need a fresh read-only App Store Connect audit',
        appStoreConnectEvidenceRelativePath,
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
      ...(locale === 'es' ? {
        selectedStoreVariants: store.selectedVariants || [],
        candidateStoreVariants: Object.fromEntries(
          Object.entries(store.marketVariants || {}).map(([variantKey, variantStore]) => {
            const candidate = selectedStoreVariants.find(({ key }) => key === variantKey);
            const policy = candidate
              ? candidate.policy
              : Object.values(regionalSafetyPolicy.regions).find(
                ({ appStoreLocale }) => appStoreLocale === variantKey,
              );
            const variantIap = iapLocale.marketVariants
              && iapLocale.marketVariants[variantKey];
            const variantLegal = policy
              && legal.regionalVariants
              && legal.regionalVariants[policy.legalRegion];
            const variantGates = {
              selected: (store.selectedVariants || []).includes(variantKey),
              metadata: variantStore.metadataReview === 'approved',
              publicUrls: variantStore.publicUrlStatus === 'deployed-and-verified',
              screenshots: variantStore.screenshotStatus === 'approved',
              regionalLegal: Boolean(
                policy
                && variantLegal
                && policy.emergencyNumberReview === 'official-source-verified'
                && policy.legalReview === 'approved'
                && variantLegal.legalReview === 'approved'
              ),
              iap: Boolean(variantIap && variantIap.metadataReview === 'approved'),
              availability: Boolean(
                policy
                && variantIap
                && variantStore.promotionAuthorized === true
                && variantIap.availabilityAuthorized === true
                && policy.availabilityAuthorized === true
              ),
            };
            return [variantKey, {
              ready: Object.values(variantGates).every(Boolean),
              gates: variantGates,
            }];
          }),
        ),
      } : {}),
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
      'web/src/i18n/app-surface-copy-manifest.json',
      'docs/I18N-SURFACE-INVENTORY.json',
      'docs/I18N-NON-USER-FACING-REVIEW.json',
      'docs/LOCALE-CONTEXT-DATA-READINESS.json',
      'docs/MEMBER-DATA-ISOLATION-READINESS.json',
      'scripts/locale_context_data_audit.py',
      'scripts/member_data_isolation_probe.py',
      'scripts/i18n-native-review-worklist.js',
      'scripts/i18n-native-review-evidence.js',
      'scripts/app-store-native-review-worklist.js',
      'scripts/app-store-native-review-evidence.js',
      'scripts/app-store-metadata-limits.js',
      'app-store/connect-audit-requirements.json',
      'scripts/app-store-connect-i18n-evidence.js',
      'scripts/i18n-visual-qa-worklist.js',
      'scripts/i18n-visual-qa-evidence.js',
      'scripts/i18n-app-e2e-evidence.js',
      'engine/voice-locale-integration-manifest.json',
      'web/legal/manifest.json',
      'web/legal/regional-safety-policy.json',
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
  validateLocaleDataEvidence,
  validateMemberDataIsolationEvidence,
  validateEvidenceConsistency,
  validateAppStoreConnectEvidence,
  validateAppStoreNativeReviewEvidence,
  validateNativeReviewEvidence,
  validatePurchaseEvidence,
  validateVisualEvidence,
  validateVoiceEvidence,
};
