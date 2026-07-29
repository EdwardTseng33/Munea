'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const STORE_DIR = path.join(ROOT, 'app-store', 'localizations');
const IAP_DIR = path.join(ROOT, 'app-store', 'in-app-purchases');
const SOURCE_TARGET = 'zh-TW';
const TARGETS = Object.freeze(['zh-TW', 'en', 'ja', 'es-ES', 'es-MX']);
const METADATA_FIELDS = Object.freeze([
  'name',
  'subtitle',
  'promotionalText',
  'description',
  'keywords',
  'whatsNew',
]);
const IAP_FIELDS = Object.freeze(['displayName', 'description']);
const REQUIRED_CHECKS = Object.freeze([
  'meaningAccurate',
  'grammarNatural',
  'toneAppropriate',
  'claimAccurate',
  'regionalContextAccepted',
  'storePresentationAccepted',
]);

function readText(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

function readJson(filePath) {
  return JSON.parse(readText(filePath));
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function targetConfig(target, storeManifest, iapManifest) {
  if (!TARGETS.includes(target)) {
    throw new Error(
      `Unsupported App Store review target: ${target}. `
      + `Use one of ${TARGETS.join(', ')}.`,
    );
  }
  if (target === 'es-ES' || target === 'es-MX') {
    const store = storeManifest.locales.es.marketVariants[target];
    const iap = iapManifest.locales.es.marketVariants[target];
    return {
      target,
      catalogLocale: 'es',
      appStoreLocale: target,
      metadataFile: store.metadataFile,
      iapCopyFile: iap.copyFile,
      screenshotLocale: 'es',
      targetTerritories: store.targetTerritories,
      safetyRegion: store.safetyRegion,
      legalRegion: store.legalRegion,
    };
  }
  const storeKey = {
    'zh-TW': 'zh-Hant',
    en: 'en-US',
    ja: 'ja',
  }[target];
  const store = storeManifest.locales[storeKey];
  const iap = iapManifest.locales[target];
  return {
    target,
    catalogLocale: target,
    appStoreLocale: store.appStoreLocale,
    metadataFile: store.metadataFile,
    iapCopyFile: iap.copyFile,
    screenshotLocale: storeKey,
    targetTerritories: store.targetTerritories,
    safetyRegion: null,
    legalRegion: null,
  };
}

function fileIdentity(relativePath) {
  const normalized = relativePath.replaceAll('\\', '/');
  const source = readText(path.join(ROOT, normalized));
  return {
    path: normalized,
    scope: 'complete-file',
    sha256: sha256(source),
    bytes: Buffer.byteLength(source),
  };
}

function contentIdentity(relativePath, scope, value) {
  const normalized = relativePath.replaceAll('\\', '/');
  const source = JSON.stringify(value);
  return {
    path: normalized,
    scope,
    sha256: sha256(source),
    bytes: Buffer.byteLength(source),
  };
}

function makeEntry(entries, values) {
  const source = String(values.source);
  const translation = String(values.translation);
  entries.push({
    sequence: entries.length + 1,
    target: values.target,
    catalogLocale: values.catalogLocale,
    appStoreLocale: values.appStoreLocale,
    kind: values.kind,
    key: values.key,
    source,
    translation,
    sourceSha256: sha256(source),
    translationSha256: sha256(translation),
    exactSourceMatch: values.target !== SOURCE_TARGET && source === translation,
    result: 'pending',
    checks: Object.fromEntries(REQUIRED_CHECKS.map((check) => [check, 'pending'])),
    reviewerNote: null,
  });
}

function buildTargetWorklist(target, manifests) {
  const {
    storeManifest,
    iapManifest,
    screenshotPlan,
  } = manifests;
  const sourceConfig = targetConfig(SOURCE_TARGET, storeManifest, iapManifest);
  const config = targetConfig(target, storeManifest, iapManifest);
  const sourceMetadata = readJson(path.join(STORE_DIR, sourceConfig.metadataFile));
  const targetMetadata = readJson(path.join(STORE_DIR, config.metadataFile));
  const sourceIap = readJson(path.join(IAP_DIR, sourceConfig.iapCopyFile));
  const targetIap = readJson(path.join(IAP_DIR, config.iapCopyFile));
  const sourceFrames = screenshotPlan.locales[sourceConfig.screenshotLocale].frames;
  const targetFrames = screenshotPlan.locales[config.screenshotLocale].frames;
  const sourceFramesById = new Map(sourceFrames.map((frame) => [frame.id, frame]));
  const entries = [];

  for (const field of METADATA_FIELDS) {
    makeEntry(entries, {
      ...config,
      kind: 'app-metadata',
      key: `metadata.${field}`,
      source: sourceMetadata[field],
      translation: targetMetadata[field],
    });
  }

  for (const frame of targetFrames) {
    const sourceFrame = sourceFramesById.get(frame.id);
    if (!sourceFrame) {
      throw new Error(`Missing source screenshot frame: ${frame.id}`);
    }
    for (const field of ['headline', 'supportingText']) {
      makeEntry(entries, {
        ...config,
        kind: 'app-store-screenshot-copy',
        key: `screenshot.${frame.id}.${field}`,
        source: sourceFrame[field],
        translation: frame[field],
      });
    }
  }

  const productIds = iapManifest.productSet.products.map(({ productId }) => productId);
  for (const productId of productIds) {
    if (!sourceIap[productId] || !targetIap[productId]) {
      throw new Error(`Missing IAP review copy for ${productId}`);
    }
    for (const field of IAP_FIELDS) {
      makeEntry(entries, {
        ...config,
        kind: 'in-app-purchase-metadata',
        key: `iap.${productId}.${field}`,
        source: sourceIap[productId][field],
        translation: targetIap[productId][field],
      });
    }
  }

  const identities = {
    storeManifest: contentIdentity(
      'app-store/localizations/manifest.json',
      'selected-locale-routing-and-region-policy',
      {
        catalogLocale: config.catalogLocale,
        appStoreLocale: config.appStoreLocale,
        metadataFile: config.metadataFile,
        targetTerritories: config.targetTerritories,
        safetyRegion: config.safetyRegion,
        legalRegion: config.legalRegion,
      },
    ),
    metadata: fileIdentity(`app-store/localizations/${config.metadataFile}`),
    screenshotPlan: contentIdentity(
      'app-store/localizations/screenshot-plan.json',
      'canvas-frame-order-and-selected-locale-copy',
      {
        canvas: screenshotPlan.canvas,
        frameOrder: screenshotPlan.frameOrder,
        frames: targetFrames,
      },
    ),
    iapManifest: contentIdentity(
      'app-store/in-app-purchases/manifest.json',
      'product-facts-and-selected-locale-routing',
      {
        products: iapManifest.productSet.products.map((product) => (
          Object.fromEntries(
            Object.entries(product).filter(([field]) => field !== 'reviewScreenshotStatus'),
          )
        )),
        appStoreLocale: config.appStoreLocale,
        copyFile: config.iapCopyFile,
      },
    ),
    iapCopy: fileIdentity(`app-store/in-app-purchases/${config.iapCopyFile}`),
  };

  return {
    config,
    identities,
    entries,
  };
}

function buildAppStoreNativeReviewWorklist(targetFilter) {
  const targets = targetFilter ? [targetFilter] : [...TARGETS];
  const manifests = {
    storeManifest: readJson(path.join(STORE_DIR, 'manifest.json')),
    iapManifest: readJson(path.join(IAP_DIR, 'manifest.json')),
    screenshotPlan: readJson(path.join(STORE_DIR, 'screenshot-plan.json')),
  };
  const reviews = {};
  const entries = [];
  for (const target of targets) {
    const review = buildTargetWorklist(target, manifests);
    reviews[target] = {
      catalogLocale: review.config.catalogLocale,
      appStoreLocale: review.config.appStoreLocale,
      targetTerritories: review.config.targetTerritories,
      safetyRegion: review.config.safetyRegion,
      legalRegion: review.config.legalRegion,
      identities: review.identities,
      entryCount: review.entries.length,
      entriesSha256: sha256(
        review.entries.map((entry) => (
          `${entry.kind}\t${entry.key}\t${entry.translationSha256}`
        )).join('\n'),
      ),
    };
    const sequenceOffset = entries.length;
    entries.push(...review.entries.map((entry, index) => ({
      ...entry,
      sequence: sequenceOffset + index + 1,
    })));
  }

  return {
    schema: 'munea.app-store-native-review-worklist.v1',
    sourceTarget: SOURCE_TARGET,
    targets,
    generatedFrom: [
      'app-store/localizations/manifest.json',
      'app-store/localizations/screenshot-plan.json',
      'app-store/in-app-purchases/manifest.json',
      ...Object.values(reviews).flatMap(({ identities }) => [
        identities.metadata.path,
        identities.iapCopy.path,
      ]),
    ],
    approvalPolicy: {
      automaticPassForbidden: true,
      nativeLanguageReviewerRequired: true,
      everyMetadataFieldRequired: true,
      allEightProductsRequired: true,
      screenshotCopyReviewRequired: true,
      sourceByteIdentityRequired: true,
      openIssuesMustBeZero: true,
    },
    reviews,
    entryCount: entries.length,
    entries,
  };
}

if (require.main === module) {
  const localeIndex = process.argv.indexOf('--locale');
  const target = localeIndex >= 0 ? process.argv[localeIndex + 1] : null;
  process.stdout.write(
    `${JSON.stringify(buildAppStoreNativeReviewWorklist(target), null, 2)}\n`,
  );
}

module.exports = {
  METADATA_FIELDS,
  REQUIRED_CHECKS,
  SOURCE_TARGET,
  TARGETS,
  buildAppStoreNativeReviewWorklist,
  sha256,
};
