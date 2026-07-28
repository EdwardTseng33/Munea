'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {
  validateInstalledAppEvidence,
  validatePurchaseEvidence,
  validateVoiceEvidence,
} = require('./i18n-release-readiness.js');
const {
  verifyDeclaredIpaIdentity,
} = require('./ipa-binary-identity.js');
const {
  validateIosBuildIdentity,
} = require('./ios-build-identity.js');

const ROOT = path.resolve(__dirname, '..');
const IAP_MANIFEST_PATH = path.join(
  ROOT,
  'app-store',
  'in-app-purchases',
  'manifest.json',
);
const SUPPORTED_LOCALES = Object.freeze(['zh-TW', 'en', 'ja', 'es']);
const CONVERSATION_LOCALE = Object.freeze({
  'zh-TW': 'zh-TW',
  en: 'en',
  ja: 'ja',
  es: 'es',
});
const INSTALLED_APP_STEPS = Object.freeze([
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
const VOICE_STEPS = Object.freeze([
  'openingInLocale',
  'microphoneAudioUnderstood',
  'assistantResponseAudible',
  'assistantResponseVisible',
  'mixedLanguageTurn',
  'temporaryVoiceSwitch',
  'permanentPreferenceConfirmed',
]);
const PURCHASE_STEPS = Object.freeze([
  'signedIn',
  'storeProductsLoaded',
  'freeMemberPointPurchaseBlocked',
  'cancelPathCreatedNoEntitlement',
  'unverifiedPathCreatedNoEntitlement',
  'activeSubscriptionRestorePassed',
]);
const PRODUCT_CHECKS = Object.freeze([
  'localizedNameMatched',
  'storeKitPriceDisplayed',
  'purchaseSheetOpened',
  'serverTransactionVerified',
  'entitlementApplied',
  'transactionFinished',
  'postPurchaseStateRefreshed',
]);
const DATA_HANDLING_CHECKS = Object.freeze([
  'noPersonalData',
  'noRawAudio',
  'noCredentials',
  'noTransactionPayloads',
]);

function readIapManifest() {
  return JSON.parse(fs.readFileSync(IAP_MANIFEST_PATH, 'utf8'));
}

function falseChecks(fields) {
  return Object.fromEntries(fields.map((field) => [field, false]));
}

function requiredString(value, label) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} is required`);
  }
  return value.trim();
}

function validIsoDate(value) {
  return typeof value === 'string'
    && value.trim() !== ''
    && !Number.isNaN(Date.parse(value));
}

function requireAllTrue(value, fields, label) {
  for (const field of fields) {
    if (!value || value[field] !== true) {
      throw new Error(`${label}.${field} must be true`);
    }
  }
}

function requireOpaqueReference(value, label) {
  const reference = requiredString(value, label);
  if (
    reference.length > 160
    || /@/.test(reference)
    || /\s/.test(reference)
    || /eyJ[a-zA-Z0-9_-]{20,}/.test(reference)
  ) {
    throw new Error(`${label} must be an opaque, non-sensitive reference`);
  }
  return reference;
}

function selectedStoreLocale(locale, iapManifest) {
  const config = iapManifest.locales[locale];
  if (!config) throw new Error(`IAP locale configuration is missing for ${locale}`);
  if (locale !== 'es') return config.appStoreLocale;
  return config.selectedVariant || null;
}

function buildAppE2eWorklist(locale) {
  if (!SUPPORTED_LOCALES.includes(locale)) {
    throw new Error(`unsupported locale: ${locale}`);
  }
  const iapManifest = readIapManifest();
  const products = iapManifest.productSet.products.map(({ productId }) => productId);
  return {
    schema: 'munea.i18n-app-e2e-worklist.v1',
    locale,
    candidateStoreLocales: locale === 'es'
      ? [...iapManifest.locales.es.candidateAppStoreLocales]
      : [iapManifest.locales[locale].appStoreLocale],
    buildIdentity: {
      exactCommit: '',
      binarySha256: '',
      binaryBytes: null,
      appVersion: '',
      build: '',
    },
    run: {
      testedAt: '',
      testerReference: '',
      evidenceReference: '',
      profile: '',
      environment: '',
      device: '',
      conversationLocale: CONVERSATION_LOCALE[locale],
      serviceRevisions: {
        brain: '',
        voice: '',
        gateway: '',
        avatar: '',
      },
      dataHandling: falseChecks(DATA_HANDLING_CHECKS),
    },
    installedApp: {
      runtimeIdentity: {
        schema: 'munea.ios-build-identity.v1',
        bundleIdentifier: '',
        exactCommit: '',
        appVersion: '',
        build: '',
      },
      steps: falseChecks(INSTALLED_APP_STEPS),
    },
    voice: {
      steps: falseChecks(VOICE_STEPS),
    },
    purchase: {
      testedAt: '',
      profile: 'sandbox-gateway',
      environment: 'sandbox',
      storeLocale: selectedStoreLocale(locale, iapManifest),
      backendRevision: '',
      steps: falseChecks(PURCHASE_STEPS),
      products: products.map((productId) => ({
        productId,
        result: 'pending',
        checks: falseChecks(PRODUCT_CHECKS),
      })),
    },
  };
}

function validateBuildIdentity(build, ipaPath) {
  if (!build || typeof build !== 'object') throw new Error('buildIdentity is required');
  const exactCommit = requiredString(build.exactCommit, 'buildIdentity.exactCommit');
  const appVersion = requiredString(build.appVersion, 'buildIdentity.appVersion');
  const buildNumber = requiredString(build.build, 'buildIdentity.build');
  if (!/^[0-9a-f]{40}$/i.test(exactCommit)) {
    throw new Error('buildIdentity.exactCommit must be a 40-character Git SHA');
  }
  const binaryIdentity = verifyDeclaredIpaIdentity(build, ipaPath);
  return {
    exactCommit,
    binarySha256: binaryIdentity.binarySha256,
    binaryBytes: binaryIdentity.binaryBytes,
    appVersion,
    build: buildNumber,
  };
}

function compileAppE2eEvidence(worklist, options = {}) {
  if (!worklist || worklist.schema !== 'munea.i18n-app-e2e-worklist.v1') {
    throw new Error('App E2E worklist schema is invalid');
  }
  const { locale } = worklist;
  if (!SUPPORTED_LOCALES.includes(locale)) throw new Error(`unsupported locale: ${locale}`);
  const canonical = buildAppE2eWorklist(locale);
  const iapManifest = readIapManifest();
  const productIds = iapManifest.productSet.products.map(({ productId }) => productId);
  const build = validateBuildIdentity(worklist.buildIdentity, options.ipaPath);
  const run = worklist.run;
  if (!run || typeof run !== 'object') throw new Error('run metadata is required');
  if (!validIsoDate(run.testedAt)) throw new Error('run.testedAt must be an ISO 8601 timestamp');
  const testerReference = requireOpaqueReference(run.testerReference, 'run.testerReference');
  const evidenceReference = requireOpaqueReference(run.evidenceReference, 'run.evidenceReference');
  const profile = requiredString(run.profile, 'run.profile');
  const environment = requiredString(run.environment, 'run.environment');
  const device = requiredString(run.device, 'run.device');
  const conversationLocale = requiredString(
    run.conversationLocale,
    'run.conversationLocale',
  );
  if (conversationLocale !== canonical.run.conversationLocale) {
    throw new Error(`run.conversationLocale must be ${canonical.run.conversationLocale}`);
  }
  const serviceRevisions = {};
  for (const service of ['brain', 'voice', 'gateway', 'avatar']) {
    serviceRevisions[service] = requiredString(
      run.serviceRevisions && run.serviceRevisions[service],
      `run.serviceRevisions.${service}`,
    );
  }
  requireAllTrue(run.dataHandling, DATA_HANDLING_CHECKS, 'run.dataHandling');
  const installedApp = worklist.installedApp;
  if (!installedApp || typeof installedApp !== 'object') {
    throw new Error('installedApp run is required');
  }
  const runtimeIdentity = validateIosBuildIdentity(
    installedApp.runtimeIdentity,
    {
      bundleIdentifier: 'net.munea.app',
      exactCommit: build.exactCommit,
      appVersion: build.appVersion,
      build: build.build,
    },
  );
  requireAllTrue(
    installedApp.steps,
    INSTALLED_APP_STEPS,
    'installedApp.steps',
  );
  requireAllTrue(
    worklist.voice && worklist.voice.steps,
    VOICE_STEPS,
    'voice.steps',
  );

  const purchase = worklist.purchase;
  if (!purchase || typeof purchase !== 'object') throw new Error('purchase run is required');
  if (!validIsoDate(purchase.testedAt)) {
    throw new Error('purchase.testedAt must be an ISO 8601 timestamp');
  }
  const purchaseProfile = requiredString(purchase.profile, 'purchase.profile');
  const purchaseEnvironment = requiredString(purchase.environment, 'purchase.environment');
  const storeLocale = requiredString(purchase.storeLocale, 'purchase.storeLocale');
  const expectedStoreLocale = selectedStoreLocale(locale, iapManifest);
  if (!expectedStoreLocale) {
    throw new Error(
      'Spanish App Store variant is not selected; approve es-ES or es-MX in the IAP manifest first',
    );
  }
  if (storeLocale !== expectedStoreLocale) {
    throw new Error(`purchase.storeLocale must match selected variant ${expectedStoreLocale}`);
  }
  const backendRevision = requiredString(
    purchase.backendRevision,
    'purchase.backendRevision',
  );
  if (backendRevision !== serviceRevisions.brain) {
    throw new Error('purchase.backendRevision must match run.serviceRevisions.brain');
  }
  requireAllTrue(purchase.steps, PURCHASE_STEPS, 'purchase.steps');
  if (!Array.isArray(purchase.products) || purchase.products.length !== productIds.length) {
    throw new Error('purchase.products must contain all 8 current products');
  }
  const actualProductIds = purchase.products.map(({ productId }) => productId);
  if (
    actualProductIds.length !== new Set(actualProductIds).size
    || JSON.stringify([...actualProductIds].sort()) !== JSON.stringify([...productIds].sort())
  ) {
    throw new Error('purchase.products must match the current IAP product set exactly');
  }
  for (const product of purchase.products) {
    if (product.result !== 'pass') {
      throw new Error(`${product.productId} result must be pass`);
    }
    requireAllTrue(product.checks, PRODUCT_CHECKS, `${product.productId}.checks`);
  }

  const common = {
    locale,
    result: 'pass',
    exactCommit: build.exactCommit,
    binarySha256: build.binarySha256,
    binaryBytes: build.binaryBytes,
    appVersion: build.appVersion,
    build: build.build,
    testerReference,
    evidenceReference,
    dataHandling: Object.fromEntries(DATA_HANDLING_CHECKS.map((field) => [field, true])),
  };
  const installed = {
    schema: 'munea.i18n-installed-app-e2e.v1',
    ...common,
    testedAt: run.testedAt,
    profile,
    environment,
    device,
    runtimeIdentity,
    serviceRevisions,
    steps: Object.fromEntries(INSTALLED_APP_STEPS.map((field) => [field, true])),
  };
  const voice = {
    schema: 'munea.i18n-voice-e2e.v1',
    ...common,
    testedAt: run.testedAt,
    profile,
    environment,
    device,
    conversationLocale,
    serviceRevisions,
    steps: Object.fromEntries(VOICE_STEPS.map((field) => [field, true])),
  };
  const purchaseEvidence = {
    schema: 'munea.i18n-purchase-e2e.v1',
    ...common,
    testedAt: purchase.testedAt,
    profile: purchaseProfile,
    environment: purchaseEnvironment,
    device,
    storeLocale,
    backendRevision,
    steps: Object.fromEntries(PURCHASE_STEPS.map((field) => [field, true])),
    products: productIds.map((productId) => ({
      productId,
      result: 'pass',
      checks: Object.fromEntries(PRODUCT_CHECKS.map((field) => [field, true])),
    })),
  };
  if (!validateInstalledAppEvidence(installed, locale)) {
    throw new Error('compiled installed-App evidence failed the release validator');
  }
  if (!validateVoiceEvidence(voice, locale)) {
    throw new Error('compiled voice evidence failed the release validator');
  }
  if (!validatePurchaseEvidence(purchaseEvidence, locale, productIds)) {
    throw new Error('compiled purchase evidence failed the release validator');
  }
  return { installed, voice, purchase: purchaseEvidence };
}

function writeNewJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, {
    encoding: 'utf8',
    flag: 'wx',
  });
}

function argValue(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : '';
}

function main() {
  const locale = argValue('--locale');
  const template = argValue('--template');
  if (template) {
    writeNewJson(path.resolve(template), buildAppE2eWorklist(locale));
    process.stdout.write(`App E2E worklist created for ${locale}: ${template}\n`);
    return;
  }
  const input = argValue('--input');
  const outputDir = argValue('--output-dir');
  const ipaPath = argValue('--ipa');
  if (!input || !outputDir || !ipaPath) {
    throw new Error(
      'usage: --locale <locale> --template <worklist.json> OR '
      + '--input <completed-worklist.json> --output-dir <locale-evidence-dir> '
      + '--ipa <candidate.ipa>',
    );
  }
  const worklist = JSON.parse(fs.readFileSync(path.resolve(input), 'utf8'));
  const evidence = compileAppE2eEvidence(worklist, { ipaPath });
  const target = path.resolve(outputDir);
  const outputs = [
    ['installed-app-e2e.json', evidence.installed],
    ['voice-e2e.json', evidence.voice],
    ['purchase-e2e.json', evidence.purchase],
  ];
  for (const [name] of outputs) {
    if (fs.existsSync(path.join(target, name))) {
      throw new Error(`refusing to overwrite existing evidence: ${name}`);
    }
  }
  for (const [name, value] of outputs) {
    writeNewJson(path.join(target, name), value);
  }
  process.stdout.write(
    `App E2E evidence PASS: ${evidence.installed.locale}, exact build `
    + `${evidence.installed.appVersion} (${evidence.installed.build})\n`,
  );
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`App E2E evidence refused: ${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  DATA_HANDLING_CHECKS,
  INSTALLED_APP_STEPS,
  PRODUCT_CHECKS,
  PURCHASE_STEPS,
  SUPPORTED_LOCALES,
  VOICE_STEPS,
  buildAppE2eWorklist,
  compileAppE2eEvidence,
};
