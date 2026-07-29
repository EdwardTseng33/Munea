(function (root, factory) {
  'use strict';

  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MuneaPurchaseFlow = Object.freeze({ ...api });
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const FAILURE_KEYS = Object.freeze({
    signin_required: 'purchase.signInRequiredBody',
    authentication_required: 'purchase.signInRequiredBody',
    invalid_auth_token: 'purchase.signInRequiredBody',
    apple_account_token_mismatch: 'purchase.accountMismatch',
    server_unavailable: 'purchase.networkError',
    notfound: 'purchase.productUnavailable',
    badid: 'purchase.productUnavailable',
    store_products_unavailable: 'purchase.productUnavailable',
    unsupported: 'purchase.storeUnavailable',
    unverified: 'purchase.unverified',
    server_verification_failed: 'purchase.serverVerificationFailed',
    signed_transaction_missing: 'purchase.serverVerificationFailed',
    cancelled: 'purchase.cancelled',
    pending: 'purchase.pending',
  });

  function nonEmpty(value) {
    const normalized = String(value == null ? '' : value).trim();
    return normalized || null;
  }

  function createPurchaseFlow(options) {
    const config = options || {};
    if (typeof config.t !== 'function') {
      throw new TypeError('purchase flow requires an i18n translator');
    }
    const t = config.t;

    function localizedProduct(product) {
      const source = product || {};
      const productId = nonEmpty(source.productId || source.id);
      const displayName = nonEmpty(source.displayName || source.title);
      const description = nonEmpty(source.description);
      const displayPrice = nonEmpty(source.displayPrice);
      if (!productId || !displayName || !displayPrice) {
        return Object.freeze({
          ok: false,
          reason: 'localized_product_missing',
          message: t('purchase.storeUnavailable'),
        });
      }
      return Object.freeze({
        ok: true,
        productId,
        displayName,
        description: description || '',
        displayPrice,
      });
    }

    function creditPack(product, facts) {
      const localized = localizedProduct(product);
      if (!localized.ok) return localized;
      const values = facts || {};
      const credits = Number(values.credits);
      const minutes = Number(values.minutes);
      if (!Number.isFinite(credits) || credits <= 0) {
        throw new TypeError('credit pack requires a positive credits value');
      }
      if (!Number.isFinite(minutes) || minutes <= 0) {
        throw new TypeError('credit pack requires a positive minutes value');
      }
      return Object.freeze({
        ...localized,
        kind: 'credits',
        credits,
        minutes,
        amountLabel: t('purchase.creditsAmount', { credits }),
        minutesLabel: t('purchase.approxMinutes', { minutes }),
        buyLabel: t('purchase.buyCredits', {
          credits,
          price: localized.displayPrice,
        }),
      });
    }

    function subscription(product, facts) {
      const localized = localizedProduct(product);
      if (!localized.ok) return localized;
      const values = facts || {};
      const plan = String(values.plan || '').toLowerCase();
      if (plan !== 'plus' && plan !== 'pro') {
        throw new TypeError('subscription requires plan plus or pro');
      }
      const planLabel = t(plan === 'plus' ? 'subscription.planPlus' : 'subscription.planPro');
      return Object.freeze({
        ...localized,
        kind: 'subscription',
        plan,
        planLabel,
        billingPeriod: values.billingPeriod === 'year' ? 'year' : 'month',
        confirmTitle: t('subscription.confirmTitle', {
          plan: planLabel,
          price: localized.displayPrice,
        }),
        upgradeLabel: t('subscription.upgradeTo', {
          plan: planLabel,
          price: localized.displayPrice,
        }),
        changeLabel: t('subscription.changeTo', {
          plan: planLabel,
          price: localized.displayPrice,
        }),
      });
    }

    function failureMessage(reason) {
      return t(FAILURE_KEYS[String(reason || '')] || 'purchase.failed');
    }

    function restoreMessage(result) {
      const value = result || {};
      if (value.ok) return t('purchase.restoreSuccess');
      if (value.reason === 'none') return t('purchase.restoreNone');
      return failureMessage(value.reason);
    }

    return Object.freeze({
      connectingMessage: () => t('purchase.connectingStore'),
      creditPack,
      failureMessage,
      loadingMessage: () => t('purchase.loadingProducts'),
      localizedProduct,
      restoreMessage,
      restoringMessage: () => t('purchase.restoring'),
      subscription,
    });
  }

  return Object.freeze({
    createPurchaseFlow,
  });
}));
