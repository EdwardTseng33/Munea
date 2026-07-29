'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const STORE_DIR = path.join(ROOT, 'app-store', 'localizations');
const IAP_DIR = path.join(ROOT, 'app-store', 'in-app-purchases');

const APP_LIMITS = Object.freeze({
  name: Object.freeze({ minimum: 2, maximum: 30 }),
  subtitle: Object.freeze({ minimum: 1, maximum: 30 }),
  promotionalText: Object.freeze({ minimum: 1, maximum: 170 }),
  description: Object.freeze({ minimum: 1, maximum: 4000 }),
  keywordsBytes: Object.freeze({ minimum: 1, maximum: 100 }),
  keywordCharacters: Object.freeze({ minimum: 3 }),
});

const IAP_LIMITS = Object.freeze({
  displayName: Object.freeze({ minimum: 2, maximum: 30 }),
  description: Object.freeze({ minimum: 1, maximum: 45 }),
});

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function characterLength(value) {
  return [...String(value || '')].length;
}

function utf8Bytes(value) {
  return Buffer.byteLength(String(value || ''), 'utf8');
}

function lengthIssue(field, value, limits, issues) {
  const length = characterLength(value);
  if (length < limits.minimum || length > limits.maximum) {
    issues.push({
      field,
      rule: 'character-length',
      actual: length,
      minimum: limits.minimum,
      maximum: limits.maximum,
    });
  }
}

function validHttpsUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'https:' && Boolean(parsed.hostname);
  } catch {
    return false;
  }
}

function validateAppMetadata(metadata) {
  const issues = [];
  lengthIssue('name', metadata && metadata.name, APP_LIMITS.name, issues);
  lengthIssue('subtitle', metadata && metadata.subtitle, APP_LIMITS.subtitle, issues);
  lengthIssue(
    'promotionalText',
    metadata && metadata.promotionalText,
    APP_LIMITS.promotionalText,
    issues,
  );
  lengthIssue(
    'description',
    metadata && metadata.description,
    APP_LIMITS.description,
    issues,
  );

  const description = String((metadata && metadata.description) || '');
  if (/<\/?[A-Za-z][^>]*>/.test(description)) {
    issues.push({ field: 'description', rule: 'plain-text-only' });
  }

  const keywords = String((metadata && metadata.keywords) || '');
  const keywordBytes = utf8Bytes(keywords);
  if (
    keywordBytes < APP_LIMITS.keywordsBytes.minimum
    || keywordBytes > APP_LIMITS.keywordsBytes.maximum
  ) {
    issues.push({
      field: 'keywords',
      rule: 'utf8-byte-length',
      actual: keywordBytes,
      minimum: APP_LIMITS.keywordsBytes.minimum,
      maximum: APP_LIMITS.keywordsBytes.maximum,
    });
  }
  const keywordList = keywords.split(',').map((value) => value.trim()).filter(Boolean);
  if (keywordList.length === 0) {
    issues.push({ field: 'keywords', rule: 'at-least-one-keyword' });
  }
  keywordList.forEach((keyword, index) => {
    if (characterLength(keyword) < APP_LIMITS.keywordCharacters.minimum) {
      issues.push({
        field: `keywords[${index}]`,
        rule: 'minimum-character-length',
        actual: characterLength(keyword),
        minimum: APP_LIMITS.keywordCharacters.minimum,
      });
    }
  });

  for (const field of ['privacyPolicyUrl', 'supportUrl']) {
    if (!validHttpsUrl(metadata && metadata[field])) {
      issues.push({ field, rule: 'required-https-url' });
    }
  }
  if (
    metadata
    && metadata.marketingUrl
    && !validHttpsUrl(metadata.marketingUrl)
  ) {
    issues.push({ field: 'marketingUrl', rule: 'https-url-when-present' });
  }

  return {
    valid: issues.length === 0,
    issues,
    measurements: {
      nameCharacters: characterLength(metadata && metadata.name),
      subtitleCharacters: characterLength(metadata && metadata.subtitle),
      promotionalTextCharacters: characterLength(metadata && metadata.promotionalText),
      descriptionCharacters: characterLength(metadata && metadata.description),
      keywordsBytes: keywordBytes,
    },
  };
}

function validateIapCopy(copy, requiredProductIds) {
  const issues = [];
  const actualProductIds = Object.keys(copy || {}).sort();
  const required = [...requiredProductIds].sort();
  const missing = required.filter((productId) => !actualProductIds.includes(productId));
  const unexpected = actualProductIds.filter((productId) => !required.includes(productId));
  if (missing.length) issues.push({ field: 'products', rule: 'missing-products', productIds: missing });
  if (unexpected.length) {
    issues.push({ field: 'products', rule: 'unexpected-products', productIds: unexpected });
  }

  for (const productId of required) {
    const product = copy && copy[productId];
    if (!product) continue;
    lengthIssue(
      `${productId}.displayName`,
      product.displayName,
      IAP_LIMITS.displayName,
      issues,
    );
    lengthIssue(
      `${productId}.description`,
      product.description,
      IAP_LIMITS.description,
      issues,
    );
  }

  return {
    valid: issues.length === 0,
    issues,
    productCount: actualProductIds.length,
  };
}

function targetAssets(storeManifest, iapManifest) {
  const fixed = [
    ['zh-TW', storeManifest.locales['zh-Hant'].metadataFile, iapManifest.locales['zh-TW'].copyFile],
    ['en', storeManifest.locales['en-US'].metadataFile, iapManifest.locales.en.copyFile],
    ['ja', storeManifest.locales.ja.metadataFile, iapManifest.locales.ja.copyFile],
  ];
  const spanish = Object.keys(storeManifest.locales.es.marketVariants || {}).map((variant) => [
    variant,
    storeManifest.locales.es.marketVariants[variant].metadataFile,
    iapManifest.locales.es.marketVariants[variant].copyFile,
  ]);
  return [...fixed, ...spanish];
}

function validateRepositoryStoreAssets() {
  const storeManifest = readJson(path.join(STORE_DIR, 'manifest.json'));
  const iapManifest = readJson(path.join(IAP_DIR, 'manifest.json'));
  const requiredProductIds = iapManifest.productSet.products.map(({ productId }) => productId);
  const targets = {};

  for (const [target, metadataFile, iapFile] of targetAssets(storeManifest, iapManifest)) {
    const metadata = validateAppMetadata(readJson(path.join(STORE_DIR, metadataFile)));
    const iap = validateIapCopy(readJson(path.join(IAP_DIR, iapFile)), requiredProductIds);
    targets[target] = {
      valid: metadata.valid && iap.valid,
      metadataFile: path.posix.join('app-store/localizations', metadataFile),
      iapFile: path.posix.join('app-store/in-app-purchases', iapFile),
      metadata,
      iap,
    };
  }

  return {
    schema: 'munea.app-store-metadata-technical-validation.v1',
    limitsSource: {
      appInformation: 'https://developer.apple.com/help/app-store-connect/reference/app-information/app-information/',
      platformVersion: 'https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information',
      inAppPurchase: 'https://developer.apple.com/help/app-store-connect/reference/in-app-purchases-and-subscriptions/in-app-purchase-information',
    },
    allValid: Object.values(targets).every(({ valid }) => valid),
    targets,
  };
}

function formatReport(report) {
  const lines = [
    'Munea App Store metadata technical validation',
    `Overall: ${report.allValid ? 'PASS' : 'FAIL'}`,
  ];
  for (const [target, result] of Object.entries(report.targets)) {
    lines.push(`${target}: ${result.valid ? 'PASS' : 'FAIL'}`);
    for (const issue of [...result.metadata.issues, ...result.iap.issues]) {
      lines.push(`  - ${issue.field}: ${issue.rule}`);
    }
  }
  return lines.join('\n');
}

if (require.main === module) {
  const report = validateRepositoryStoreAssets();
  process.stdout.write(`${formatReport(report)}\n`);
  if (process.argv.includes('--json')) {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  }
  if (process.argv.includes('--strict') && !report.allValid) {
    process.exitCode = 1;
  }
}

module.exports = {
  APP_LIMITS,
  IAP_LIMITS,
  characterLength,
  formatReport,
  utf8Bytes,
  validateAppMetadata,
  validateIapCopy,
  validateRepositoryStoreAssets,
};
