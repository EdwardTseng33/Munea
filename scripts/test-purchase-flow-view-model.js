'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createPurchaseFlow } = require('../web/src/i18n/purchase-flow.js');

const ROOT = path.resolve(__dirname, '..');
const LOCALE_PRICES = {
  'zh-TW': 'NT$300',
  en: '$9.99',
  ja: '¥1,500',
  es: '9,99 €',
};

function catalog(locale) {
  return JSON.parse(
    fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n', `${locale}.json`), 'utf8'),
  );
}

function translator(locale) {
  const messages = catalog(locale);
  return (key, values) => {
    assert.equal(typeof messages[key], 'string', `${locale}:${key} is missing`);
    return messages[key].replace(
      /\{([A-Za-z][A-Za-z0-9_]*)\}/g,
      (token, name) => (
        Object.prototype.hasOwnProperty.call(values || {}, name)
          ? String(values[name])
          : token
      ),
    );
  };
}

for (const [locale, displayPrice] of Object.entries(LOCALE_PRICES)) {
  const flow = createPurchaseFlow({ t: translator(locale) });
  const credits = flow.creditPack({
    productId: 'net.munea.app.points.200',
    displayName: 'localized product name',
    description: 'localized product description',
    displayPrice,
  }, {
    credits: 100,
    minutes: 20,
  });
  assert.equal(credits.ok, true);
  assert.equal(credits.displayPrice, displayPrice);
  assert.ok(credits.buyLabel.includes(displayPrice), `${locale} lost the StoreKit price`);
  assert.ok(!credits.buyLabel.includes('{price}'), `${locale} left a price placeholder visible`);

  const plan = flow.subscription({
    productId: 'net.munea.app.plus.monthly',
    displayName: 'localized plan name',
    description: 'localized plan description',
    displayPrice,
  }, {
    plan: 'plus',
    billingPeriod: 'month',
  });
  assert.equal(plan.ok, true);
  assert.equal(plan.displayPrice, displayPrice);
  assert.ok(plan.confirmTitle.includes(displayPrice), `${locale} confirm title lost StoreKit price`);
  assert.ok(plan.upgradeLabel.includes(displayPrice), `${locale} upgrade label lost StoreKit price`);
  assert.ok(plan.changeLabel.includes(displayPrice), `${locale} change label lost StoreKit price`);

  const missingPrice = flow.localizedProduct({
    productId: 'net.munea.app.plus.monthly',
    displayName: 'localized plan name',
  });
  assert.equal(missingPrice.ok, false);
  assert.equal(missingPrice.reason, 'localized_product_missing');
  assert.ok(!JSON.stringify(missingPrice).match(/(?:NT|US)\$|[$€¥]/u));

  for (const reason of [
    'signin_required',
    'authentication_required',
    'invalid_auth_token',
    'apple_account_token_mismatch',
    'server_unavailable',
    'notfound',
    'badid',
    'store_products_unavailable',
    'unsupported',
    'unverified',
    'server_verification_failed',
    'signed_transaction_missing',
    'cancelled',
    'pending',
    'unknown_error',
  ]) {
    const message = flow.failureMessage(reason);
    assert.ok(message && message !== reason, `${locale}:${reason} leaked a raw error code`);
  }
  assert.equal(flow.restoreMessage({ ok: true }), translator(locale)('purchase.restoreSuccess'));
  assert.equal(flow.restoreMessage({ ok: false, reason: 'none' }), translator(locale)('purchase.restoreNone'));
}

const moduleSource = fs.readFileSync(
  path.join(ROOT, 'web', 'src', 'i18n', 'purchase-flow.js'),
  'utf8',
);
assert.ok(!/(?:NT|US)\$|[$€¥]|\b(?:USD|TWD|JPY|EUR)\b/u.test(moduleSource));

console.log('Purchase flow view model PASS: four StoreKit price formats and all result states');
