'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const LOCALES = ['zh-TW', 'en', 'ja', 'es'];
const REQUIRED_KEYS = [
  'purchase.topUpTitle',
  'purchase.topUpDescription',
  'purchase.selectPack',
  'purchase.signInRequiredTitle',
  'purchase.signInRequiredBody',
  'purchase.storeUnavailable',
  'purchase.connectingStore',
  'purchase.loadingProducts',
  'purchase.retry',
  'purchase.buyCredits',
  'purchase.creditsAmount',
  'purchase.approxMinutes',
  'purchase.success',
  'purchase.cancelled',
  'purchase.pending',
  'purchase.failed',
  'purchase.productUnavailable',
  'purchase.unverified',
  'purchase.accountMismatch',
  'purchase.serverVerificationFailed',
  'purchase.networkError',
  'purchase.manageSubscription',
  'purchase.restore',
  'purchase.restoring',
  'purchase.restoreSuccess',
  'purchase.restoreNone',
  'subscription.title',
  'subscription.tagline',
  'subscription.plansTab',
  'subscription.creditsTab',
  'subscription.unlockCredits',
  'subscription.benefitsIntro',
  'subscription.benefitMemoryTitle',
  'subscription.benefitMemoryBody',
  'subscription.benefitCareTitle',
  'subscription.benefitCareBody',
  'subscription.benefitVoiceTitle',
  'subscription.benefitVoiceBody',
  'subscription.benefitFamilyTitle',
  'subscription.benefitFamilyBody',
  'subscription.billingMonthly',
  'subscription.billingYearly',
  'subscription.savePercent',
  'subscription.planFree',
  'subscription.planPlus',
  'subscription.planPro',
  'subscription.currentPlan',
  'subscription.choosePlan',
  'subscription.upgradeTo',
  'subscription.changeTo',
  'subscription.pricePerMonth',
  'subscription.billedYearly',
  'subscription.creditRulesTitle',
  'subscription.monthlyCreditsTitle',
  'subscription.monthlyCreditsBody',
  'subscription.purchasedCreditsTitle',
  'subscription.purchasedCreditsBody',
  'subscription.deductionOrderTitle',
  'subscription.deductionOrderBody',
  'subscription.freeTrial',
  'subscription.plusAudience',
  'subscription.plusFeature1',
  'subscription.plusFeature2',
  'subscription.plusFeature3',
  'subscription.plusFeature4',
  'subscription.proAudience',
  'subscription.proFeature1',
  'subscription.proFeature2',
  'subscription.proFeature3',
  'subscription.proFeature4',
  'subscription.proFeature5',
  'subscription.confirmTitle',
  'subscription.confirmBody',
  'subscription.confirmAction',
  'subscription.cancel',
  'subscription.purchasePending',
  'subscription.manageInAppStore',
  'subscription.restoreTitle',
  'subscription.restoreBody',
];

function readCatalog(locale) {
  const filePath = path.join(ROOT, 'web', 'src', 'i18n', `${locale}.json`);
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function placeholders(value) {
  return [...String(value).matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)]
    .map((match) => match[1])
    .sort();
}

const catalogs = new Map(LOCALES.map((locale) => [locale, readCatalog(locale)]));
const source = catalogs.get('zh-TW');

for (const locale of LOCALES) {
  const catalog = catalogs.get(locale);
  for (const key of REQUIRED_KEYS) {
    assert.equal(typeof catalog[key], 'string', `${locale}:${key} is missing`);
    assert.ok(catalog[key].trim(), `${locale}:${key} is empty`);
    assert.deepEqual(
      placeholders(catalog[key]),
      placeholders(source[key]),
      `${locale}:${key} placeholder mismatch`,
    );
  }
}

const forbiddenPrice = /(?:NT|US)\$|[$€¥]|\b(?:USD|TWD|JPY|EUR)\b/u;
for (const locale of LOCALES) {
  const catalog = catalogs.get(locale);
  for (const [key, value] of Object.entries(catalog)) {
    if (!key.startsWith('purchase.') && !key.startsWith('subscription.')) continue;
    assert.ok(
      !forbiddenPrice.test(value),
      `${locale}:${key} hard-codes a price or currency; render StoreKit displayPrice instead`,
    );
  }
}

for (const locale of LOCALES) {
  const catalog = catalogs.get(locale);
  for (const key of [
    'purchase.buyCredits',
    'subscription.upgradeTo',
    'subscription.changeTo',
    'subscription.confirmTitle',
  ]) {
    assert.ok(
      placeholders(catalog[key]).includes('price'),
      `${locale}:${key} must accept StoreKit displayPrice`,
    );
  }
}

const han = /[\u3400-\u9fff\uf900-\ufaff]/u;
for (const locale of ['en', 'es']) {
  const catalog = catalogs.get(locale);
  for (const key of REQUIRED_KEYS) {
    assert.ok(!han.test(catalog[key]), `${locale}:${key} unexpectedly contains Han text`);
  }
}

const policyPatterns = {
  'zh-TW': {
    monthly: /不會累積/,
    purchased: /不會到期/,
    trial: /一次 5 分鐘/,
  },
  en: {
    monthly: /do not roll over/i,
    purchased: /do not expire/i,
    trial: /one 5-minute trial/i,
  },
  ja: {
    monthly: /繰り越されません/,
    purchased: /有効期限はありません/,
    trial: /1回限り5分間/,
  },
  es: {
    monthly: /no se acumulan/i,
    purchased: /no caducan/i,
    trial: /única prueba de 5 minutos/i,
  },
};

for (const locale of LOCALES) {
  const catalog = catalogs.get(locale);
  const patterns = policyPatterns[locale];
  assert.match(catalog['subscription.monthlyCreditsBody'], patterns.monthly);
  assert.match(catalog['subscription.purchasedCreditsBody'], patterns.purchased);
  assert.match(catalog['subscription.freeTrial'], patterns.trial);
}

console.log(
  `Purchase flow localizations PASS: ${REQUIRED_KEYS.length} keys across ${LOCALES.length} locales`,
);
