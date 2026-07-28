'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const STORE_DIR = path.join(ROOT, 'app-store', 'localizations');
const IAP_DIR = path.join(ROOT, 'app-store', 'in-app-purchases');
const REQUIREMENTS_PATH = path.join(
  ROOT,
  'app-store',
  'connect-audit-requirements.json',
);
const METADATA_FIELDS = Object.freeze([
  'name',
  'subtitle',
  'promotionalText',
  'description',
  'keywords',
  'whatsNew',
  'privacyPolicyUrl',
  'supportUrl',
  'marketingUrl',
]);
const EVIDENCE_CHECKS = Object.freeze([
  'appIdentityMatched',
  'spanishMarketSelected',
  'appAvailabilityMatched',
  'metadataMatched',
  'screenshotsAttached',
  'productSetMatched',
  'iapMetadataMatched',
  'iapReviewScreenshotsAttached',
  'iapAvailabilityMatched',
  'localizedPricesObserved',
]);

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function validIsoDate(value) {
  return typeof value === 'string'
    && value.trim() !== ''
    && !Number.isNaN(Date.parse(value));
}

function withinAge(value, maximumAgeHours, referenceTime = new Date()) {
  if (!validIsoDate(value)) return false;
  const now = referenceTime instanceof Date
    ? referenceTime.getTime()
    : Date.parse(referenceTime);
  const captured = Date.parse(value);
  if (!Number.isFinite(now) || !Number.isFinite(captured)) return false;
  return captured <= now + (5 * 60 * 1000)
    && now - captured <= maximumAgeHours * 60 * 60 * 1000;
}

function requiredString(value, label) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} is required`);
  }
  return value.trim();
}

function cleanProductFacts(product) {
  return Object.fromEntries(
    Object.entries(product).filter(([field]) => field !== 'reviewScreenshotStatus'),
  );
}

function targetFromManifest(
  catalogLocale,
  appStoreLocale,
  territory,
  metadataFile,
  iapCopyFile,
) {
  return {
    catalogLocale,
    appStoreLocale,
    territory,
    metadata: Object.fromEntries(
      METADATA_FIELDS.map((field) => [
        field,
        readJson(path.join(STORE_DIR, metadataFile))[field],
      ]),
    ),
    iapCopy: readJson(path.join(IAP_DIR, iapCopyFile)),
  };
}

function buildCurrentRequirements(options = {}) {
  const base = readJson(REQUIREMENTS_PATH);
  const store = readJson(path.join(STORE_DIR, 'manifest.json'));
  const iap = readJson(path.join(IAP_DIR, 'manifest.json'));
  const explicitSpanishVariants = options.spanishVariants;
  const spanishVariants = explicitSpanishVariants === undefined
    ? (store.locales.es.selectedVariants || [])
    : explicitSpanishVariants;
  const targets = [
    targetFromManifest(
      'zh-TW',
      'zh-Hant',
      'TW',
      store.locales['zh-Hant'].metadataFile,
      iap.locales['zh-TW'].copyFile,
    ),
    targetFromManifest(
      'en',
      'en-US',
      'US',
      store.locales['en-US'].metadataFile,
      iap.locales.en.copyFile,
    ),
    targetFromManifest(
      'ja',
      'ja',
      'JP',
      store.locales.ja.metadataFile,
      iap.locales.ja.copyFile,
    ),
  ];
  for (const variant of spanishVariants) {
    const storeVariant = store.locales.es.marketVariants[variant];
    const iapVariant = iap.locales.es.marketVariants[variant];
    if (!storeVariant || !iapVariant) {
      throw new Error(`Unsupported selected Spanish market variant: ${variant}`);
    }
    targets.push(targetFromManifest(
      'es',
      variant,
      storeVariant.targetTerritories[0],
      storeVariant.metadataFile,
      iapVariant.copyFile,
    ));
  }
  const requirements = {
    ...base,
    spanishMarketSelectionComplete: spanishVariants.length > 0,
    targets,
    products: iap.productSet.products.map(cleanProductFacts),
  };
  requirements.requirementsSha256 = sha256(JSON.stringify({
    schema: requirements.schema,
    maximumAgeHours: requirements.maximumAgeHours,
    captureMethod: requirements.captureMethod,
    bundleIdentifier: requirements.bundleIdentifier,
    spanishMarketSelectionComplete: requirements.spanishMarketSelectionComplete,
    targets: requirements.targets,
    products: requirements.products,
  }));
  return requirements;
}

function validateSnapshot(snapshot, requirements, referenceTime = new Date()) {
  if (!snapshot || snapshot.schema !== 'munea.app-store-connect-i18n-snapshot.v1') {
    throw new Error('App Store Connect snapshot schema is invalid');
  }
  if (!requirements.spanishMarketSelectionComplete) {
    throw new Error('Spanish App Store market selection is incomplete');
  }
  if (!withinAge(snapshot.capturedAt, requirements.maximumAgeHours, referenceTime)) {
    throw new Error('App Store Connect snapshot is missing, future-dated, or stale');
  }
  if (snapshot.captureMethod !== requirements.captureMethod) {
    throw new Error('snapshot must come from the approved read-only capture method');
  }
  if (snapshot.containsSecrets !== false || snapshot.productionWritesPerformed !== false) {
    throw new Error('snapshot must contain no secrets and perform no production writes');
  }
  requiredString(snapshot.evidenceReference, 'snapshot.evidenceReference');
  if (
    snapshot.bundleIdentifier !== requirements.bundleIdentifier
    || !/^\d{6,20}$/.test(String(snapshot.appStoreConnectAppId || ''))
  ) {
    throw new Error('App Store Connect app identity does not match Munea');
  }

  const appTerritories = new Set(snapshot.appAvailability && snapshot.appAvailability.territories);
  const localizationMap = snapshot.localizations || {};
  for (const target of requirements.targets) {
    if (!appTerritories.has(target.territory)) {
      throw new Error(`App is unavailable in required territory ${target.territory}`);
    }
    const localization = localizationMap[target.appStoreLocale];
    if (!localization) {
      throw new Error(`Missing App Store localization ${target.appStoreLocale}`);
    }
    for (const field of METADATA_FIELDS) {
      if (localization.metadata && localization.metadata[field] !== target.metadata[field]) {
        throw new Error(`${target.appStoreLocale}.${field} differs from repository copy`);
      }
      if (!localization.metadata || localization.metadata[field] === undefined) {
        throw new Error(`${target.appStoreLocale}.${field} is missing`);
      }
    }
    if (!Number.isSafeInteger(localization.screenshotCount)
        || localization.screenshotCount < 5) {
      throw new Error(`${target.appStoreLocale} needs at least five App Store screenshots`);
    }
  }

  if (!Array.isArray(snapshot.iapProducts)) {
    throw new Error('snapshot.iapProducts must be an array');
  }
  const expectedIds = requirements.products.map(({ productId }) => productId).sort();
  const observedIds = snapshot.iapProducts.map(({ productId }) => productId).sort();
  if (JSON.stringify(observedIds) !== JSON.stringify(expectedIds)) {
    throw new Error('App Store Connect IAP product set differs from the required 8 products');
  }
  const factsById = new Map(
    requirements.products.map((product) => [product.productId, product]),
  );
  for (const product of snapshot.iapProducts) {
    const facts = factsById.get(product.productId);
    if (
      product.type !== facts.type
      || !/^\d{6,20}$/.test(String(product.appStoreConnectProductId || ''))
    ) {
      throw new Error(`${product.productId} identity or product type differs`);
    }
    if (product.reviewScreenshotAttached !== true) {
      throw new Error(`${product.productId} App Review screenshot is missing`);
    }
    const territories = new Set(product.availableTerritories);
    for (const target of requirements.targets) {
      if (!territories.has(target.territory)) {
        throw new Error(`${product.productId} is unavailable in ${target.territory}`);
      }
      const copy = product.localizations && product.localizations[target.appStoreLocale];
      const expectedCopy = target.iapCopy[product.productId];
      if (JSON.stringify(copy) !== JSON.stringify(expectedCopy)) {
        throw new Error(
          `${product.productId}.${target.appStoreLocale} differs from repository copy`,
        );
      }
      const price = product.localizedPrices && product.localizedPrices[target.territory];
      if (
        !price
        || !requiredString(price.currency, `${product.productId}.${target.territory}.currency`)
        || !requiredString(
          price.displayPrice,
          `${product.productId}.${target.territory}.displayPrice`,
        )
      ) {
        throw new Error(`${product.productId} has no localized price in ${target.territory}`);
      }
    }
  }
  return true;
}

function compileEvidence(snapshot, options = {}) {
  const requirements = buildCurrentRequirements(options);
  validateSnapshot(snapshot, requirements, options.referenceTime || new Date());
  return {
    schema: 'munea.app-store-connect-i18n-audit.v1',
    result: 'pass',
    capturedAt: snapshot.capturedAt,
    captureMethod: snapshot.captureMethod,
    evidenceReference: snapshot.evidenceReference,
    bundleIdentifier: snapshot.bundleIdentifier,
    appStoreConnectAppId: String(snapshot.appStoreConnectAppId),
    containsSecrets: false,
    productionWritesPerformed: false,
    requirementsSha256: requirements.requirementsSha256,
    snapshotSha256: sha256(JSON.stringify(snapshot)),
    targetLocales: requirements.targets.map(({ appStoreLocale }) => appStoreLocale),
    targetTerritories: [
      ...new Set(requirements.targets.map(({ territory }) => territory)),
    ],
    productCount: requirements.products.length,
    checks: Object.fromEntries(EVIDENCE_CHECKS.map((check) => [check, true])),
  };
}

function validateEvidence(evidence, referenceTime = new Date()) {
  try {
    const requirements = buildCurrentRequirements();
    return requirements.spanishMarketSelectionComplete
      && evidence
      && evidence.schema === 'munea.app-store-connect-i18n-audit.v1'
      && evidence.result === 'pass'
      && withinAge(evidence.capturedAt, requirements.maximumAgeHours, referenceTime)
      && evidence.captureMethod === requirements.captureMethod
      && typeof evidence.evidenceReference === 'string'
      && evidence.evidenceReference.trim() !== ''
      && evidence.bundleIdentifier === requirements.bundleIdentifier
      && /^\d{6,20}$/.test(String(evidence.appStoreConnectAppId || ''))
      && evidence.containsSecrets === false
      && evidence.productionWritesPerformed === false
      && evidence.requirementsSha256 === requirements.requirementsSha256
      && /^[0-9a-f]{64}$/.test(evidence.snapshotSha256 || '')
      && JSON.stringify(evidence.targetLocales) === JSON.stringify(
        requirements.targets.map(({ appStoreLocale }) => appStoreLocale),
      )
      && JSON.stringify(evidence.targetTerritories) === JSON.stringify([
        ...new Set(requirements.targets.map(({ territory }) => territory)),
      ])
      && evidence.productCount === requirements.products.length
      && EVIDENCE_CHECKS.every((check) => evidence.checks && evidence.checks[check] === true);
  } catch {
    return false;
  }
}

function main() {
  const inputIndex = process.argv.indexOf('--input');
  const outputIndex = process.argv.indexOf('--output');
  const input = inputIndex >= 0 ? process.argv[inputIndex + 1] : '';
  const output = outputIndex >= 0 ? process.argv[outputIndex + 1] : '';
  if (!input || !output) {
    throw new Error(
      'usage: --input <read-only-app-store-connect-snapshot.json> '
      + '--output <app-store-connect-audit.json>',
    );
  }
  const snapshot = readJson(path.resolve(input));
  const evidence = compileEvidence(snapshot);
  const outputPath = path.resolve(output);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
  process.stdout.write(
    `App Store Connect i18n evidence PASS: ${evidence.targetLocales.length} locales, `
    + `${evidence.productCount} products\n`,
  );
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`App Store Connect i18n evidence refused: ${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  EVIDENCE_CHECKS,
  METADATA_FIELDS,
  buildCurrentRequirements,
  compileEvidence,
  validateEvidence,
  validateSnapshot,
};
