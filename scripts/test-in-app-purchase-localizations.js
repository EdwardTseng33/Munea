'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const IAP_DIR = path.join(ROOT, 'app-store', 'in-app-purchases');
const MANIFEST_PATH = path.join(IAP_DIR, 'manifest.json');
const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'));

const expectedProducts = {
  'net.munea.app.plus.monthly': {
    type: 'auto-renewable-subscription',
    plan: 'plus',
    billingPeriod: 'month',
    monthlyPoints: 100,
    familyCircleLimit: 4,
  },
  'net.munea.app.plus.yearly': {
    type: 'auto-renewable-subscription',
    plan: 'plus',
    billingPeriod: 'year',
    monthlyPoints: 100,
    familyCircleLimit: 4,
  },
  'net.munea.app.pro.monthly': {
    type: 'auto-renewable-subscription',
    plan: 'pro',
    billingPeriod: 'month',
    monthlyPoints: 200,
    familyCircleLimit: 12,
  },
  'net.munea.app.pro.yearly': {
    type: 'auto-renewable-subscription',
    plan: 'pro',
    billingPeriod: 'year',
    monthlyPoints: 200,
    familyCircleLimit: 12,
  },
  'net.munea.app.points.200': {
    type: 'consumable',
    grantedPoints: 100,
    eligiblePlans: ['plus', 'pro'],
  },
  'net.munea.app.points.500': {
    type: 'consumable',
    grantedPoints: 300,
    eligiblePlans: ['plus', 'pro'],
  },
  'net.munea.app.points.1000': {
    type: 'consumable',
    grantedPoints: 600,
    eligiblePlans: ['plus', 'pro'],
  },
  'net.munea.app.points.1800': {
    type: 'consumable',
    grantedPoints: 1000,
    eligiblePlans: ['plus', 'pro'],
  },
};
const productIds = Object.keys(expectedProducts);
const localeKeys = ['zh-TW', 'en', 'ja', 'es'];
const sourceProductIdPattern = /net\.munea\.app\.(?:plus|pro)\.(?:monthly|yearly)|net\.munea\.app\.points\.(?:200|500|1000|1800)/g;

function uniqueProductIds(source) {
  return [...new Set(source.match(sourceProductIdPattern) || [])].sort();
}

assert.equal(manifest.schema, 'munea.app-store-iap-localizations.v1');
assert.equal(manifest.authority, 'repository-draft-only');
assert.equal(manifest.billingFactsSource, 'docs/BILLING-CREDITS-ENTITLEMENT-v1.md');
assert.equal(manifest.productSet.repositoryAlignment, 'verified');
assert.equal(manifest.productSet.appStoreConnectStatus, 'unverified');
assert.equal(manifest.availability.currentState, 'unverified');
assert.equal(manifest.availability.changeAuthorized, false);
assert.equal(manifest.pricePolicy.sourceOfTruth, 'StoreKit localized Product.displayPrice');
assert.equal(manifest.pricePolicy.repositoryCopyMayContainPrice, false);
assert.equal(manifest.pricePolicy.appStoreConnectStatus, 'unverified');
assert.deepEqual(Object.keys(manifest.locales), localeKeys);

const products = Object.fromEntries(
  manifest.productSet.products.map((product) => [product.productId, product]),
);
assert.deepEqual(Object.keys(products).sort(), productIds.sort(), 'IAP product set must contain exactly 8 products');
for (const [productId, expected] of Object.entries(expectedProducts)) {
  const product = products[productId];
  assert(product, `Missing product facts for ${productId}`);
  for (const [field, value] of Object.entries(expected)) {
    assert.deepEqual(product[field], value, `${productId}.${field} drifted from billing facts`);
  }
  assert.equal(
    product.reviewScreenshotStatus,
    'unverified',
    `${productId} must not claim an App Review screenshot without current evidence`,
  );
}

for (const sourcePath of ['engine/apple_store.py', 'web/src/store.js']) {
  const source = fs.readFileSync(path.join(ROOT, sourcePath), 'utf8');
  assert.deepEqual(
    uniqueProductIds(source),
    [...productIds].sort(),
    `${sourcePath} product IDs drifted from the localized IAP registry`,
  );
}
const storeBridge = fs.readFileSync(path.join(ROOT, 'web', 'src', 'store.js'), 'utf8');
const appShell = fs.readFileSync(path.join(ROOT, 'web', 'src', 'app.js'), 'utf8');
const appHtml = fs.readFileSync(path.join(ROOT, 'web', 'index.html'), 'utf8');
const nativeStoreBridge = fs.readFileSync(
  path.join(ROOT, 'ios', 'App', 'App', 'StorePlugin.swift'),
  'utf8',
);
assert(nativeStoreBridge.includes('CAPPluginMethod(name: "getProducts"'));
for (const field of ['displayName', 'description', 'displayPrice']) {
  assert(
    nativeStoreBridge.includes(`"${field}": $0.`),
    `Native StoreKit product query must return ${field}`,
  );
}
assert(storeBridge.includes('getProducts: getProducts'));
assert(storeBridge.includes('PRODUCT_CACHE'));
assert(storeBridge.includes('displayPrice: String(item.displayPrice || \'\')'));
assert(appHtml.includes('src/i18n/purchase-flow.js'));
assert(appShell.includes('window.MuneaStore.getProducts()'));
assert(appShell.includes('product.displayPrice'));
assert(appShell.includes('muneaPurchaseFlow()'));
assert(appShell.includes("document.querySelector('#topUpModal .tu-card.on')"));
assert(appShell.includes("clearBtnBusy(b, muneaT('purchase.manageSubscription'"));
assert(
  !/displayPrice:\s*['"][^'"]*(?:NT\$|US\$|[$€¥￥])/.test(storeBridge),
  'Store bridge must never hard-code a localized display price',
);

const hanPattern = /[\u3400-\u9fff\uf900-\ufaff]/u;
function visibleFallbackBetween(startId, endId) {
  const start = appHtml.indexOf(`id="${startId}"`);
  const end = appHtml.indexOf(`id="${endId}"`, start + 1);
  assert(start >= 0 && end > start, `Could not isolate ${startId} fallback markup`);
  return appHtml
    .slice(start, end)
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
for (const [startId, endId] of [
  ['topUpModal', 'planModal'],
  ['planModal', 'visitModal'],
]) {
  assert(
    !hanPattern.test(visibleFallbackBetween(startId, endId)),
    `${startId} fallback markup contains accidental Han copy`,
  );
}
const forbiddenPricePattern = /(?:NT\$|US\$|[$€¥￥]|\b(?:USD|TWD|JPY|EUR)\b)/i;
for (const localeKey of localeKeys) {
  const locale = manifest.locales[localeKey];
  const copy = JSON.parse(fs.readFileSync(path.join(IAP_DIR, locale.copyFile), 'utf8'));
  assert.deepEqual(
    Object.keys(copy).sort(),
    [...productIds].sort(),
    `${localeKey} IAP copy must cover the exact 8-product set`,
  );
  for (const [productId, localized] of Object.entries(copy)) {
    assert.equal(typeof localized.displayName, 'string');
    assert.equal(typeof localized.description, 'string');
    assert(
      [...localized.displayName].length >= 2 && [...localized.displayName].length <= 30,
      `${localeKey}.${productId} display name must be 2-30 characters`,
    );
    assert(
      [...localized.description].length <= 45,
      `${localeKey}.${productId} description exceeds Apple's 45-character limit`,
    );
    assert(localized.description.trim(), `${localeKey}.${productId} description is empty`);
    assert(
      !forbiddenPricePattern.test(`${localized.displayName}\n${localized.description}`),
      `${localeKey}.${productId} must not hard-code a price or currency`,
    );
    if (localeKey === 'en' || localeKey === 'es') {
      assert(
        !hanPattern.test(`${localized.displayName}\n${localized.description}`),
        `${localeKey}.${productId} contains accidental Han copy`,
      );
    }
  }
}

const spanish = manifest.locales.es;
assert.equal(spanish.appStoreLocale, null, 'Spanish IAP locale must wait for the market decision');
assert.equal(spanish.selectedVariant, null);
assert.deepEqual(
  spanish.candidateAppStoreLocales,
  ['es-ES', 'es-MX'],
  'Spanish App Store choices must remain explicit',
);
assert.notEqual(spanish.metadataReview, 'approved');
assert.deepEqual(Object.keys(spanish.marketVariants), ['es-ES', 'es-MX']);
for (const variantKey of ['es-ES', 'es-MX']) {
  const variant = spanish.marketVariants[variantKey];
  const copy = JSON.parse(fs.readFileSync(path.join(IAP_DIR, variant.copyFile), 'utf8'));
  assert.match(variant.metadataReview, /^draft/);
  assert.equal(variant.availabilityAuthorized, false);
  assert.deepEqual(Object.keys(copy).sort(), [...productIds].sort());
  for (const [productId, localized] of Object.entries(copy)) {
    assert(
      [...localized.displayName].length >= 2 && [...localized.displayName].length <= 30,
      `${variantKey}.${productId} display name must be 2-30 characters`,
    );
    assert(
      [...localized.description].length <= 45,
      `${variantKey}.${productId} description exceeds Apple's 45-character limit`,
    );
    assert(!hanPattern.test(`${localized.displayName}\n${localized.description}`));
    assert(!forbiddenPricePattern.test(`${localized.displayName}\n${localized.description}`));
  }
}

for (const product of manifest.productSet.products.filter(({ type }) => type === 'consumable')) {
  const expectedGrant = expectedProducts[product.productId].grantedPoints;
  for (const localeKey of localeKeys) {
    const locale = manifest.locales[localeKey];
    const copy = JSON.parse(fs.readFileSync(path.join(IAP_DIR, locale.copyFile), 'utf8'));
    assert(
      copy[product.productId].displayName.includes(expectedGrant.toLocaleString('en-US'))
        || copy[product.productId].displayName.includes(String(expectedGrant)),
      `${localeKey}.${product.productId} must show the actual ${expectedGrant}-credit grant, not its legacy suffix`,
    );
  }
  for (const variant of Object.values(spanish.marketVariants)) {
    const copy = JSON.parse(fs.readFileSync(path.join(IAP_DIR, variant.copyFile), 'utf8'));
    assert(
      copy[product.productId].displayName.includes(String(expectedGrant)),
      `${variant.copyFile}.${product.productId} must show the actual ${expectedGrant}-credit grant`,
    );
  }
}

console.log('PASS: 8-product IAP facts, four-locale copy, Apple limits, and release gates');
