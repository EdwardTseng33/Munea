const fs = require('fs');
const vm = require('vm');

const appSource = fs.readFileSync('web/src/app.js', 'utf8');
const localizedExpiryBinding = "muneaT('subscription.expiryDate', '訂閱到期日：{date}', { date })";
const localizedExpiryBindingCount = appSource.split(localizedExpiryBinding).length - 1;
if (localizedExpiryBindingCount < 2) {
  throw new Error(
    'settings plan card and subscription summary must keep the verified expiry date visible through the localized copy contract',
  );
}
for (const locale of ['zh-TW', 'en', 'ja', 'es']) {
  const catalog = JSON.parse(fs.readFileSync(`web/src/i18n/${locale}.json`, 'utf8'));
  const template = catalog['subscription.expiryDate'];
  if (typeof template !== 'string' || !template.includes('{date}')) {
    throw new Error(`${locale} subscription.expiryDate must preserve the verified date placeholder`);
  }
}

const storage = new Map();
let serverCalls = 0;
let applied = 0;
let finished = 0;
let managed = 0;
let nativePurchases = 0;
let productLoads = 0;
let loadedProductIds = [];
let serverAllows = true;
let restoreTransactions = [];
let appliedPurchase = null;
let currentTransaction = {
  state: 'purchased',
  productId: 'net.munea.app.points.200',
  transactionId: '100000000000001',
  originalTransactionId: '100000000000001',
  signedTransaction: 'header.payload.signature'
};

const plugin = {
  addListener() {},
  async getProducts({ ids }) {
    productLoads += 1;
    loadedProductIds = ids.slice();
    return {
      products: ids.map(productId => ({
        productId,
        displayName: `Localized ${productId}`,
        description: 'Localized product description',
        displayPrice: productId.includes('.monthly') ? '$19.99' : '$99.99'
      }))
    };
  },
  async purchase() { nativePurchases += 1; return { ...currentTransaction }; },
  async finish() { finished += 1; return { ok: true }; },
  async restore() { return { transactions: restoreTransactions.map(tx => ({ ...tx })) }; },
  async manageSubscriptions() { managed += 1; return { ok: true }; }
};

const context = {
  console,
  localStorage: {
    getItem(key) { return storage.has(key) ? storage.get(key) : null; },
    setItem(key, value) { storage.set(key, String(value)); },
    removeItem(key) { storage.delete(key); }
  },
  fetch: async () => {
    serverCalls += 1;
    return {
      ok: serverAllows,
      async json() {
        return serverAllows
          ? {
              ok: true,
              verified: true,
              walletSummary: { purchased: 200 },
              idempotentReplay: serverCalls > 1,
              billing: currentTransaction.productId.includes('.plus.')
                ? { subscription: { status: 'active', expiresAt: '2026-08-14T00:00:00Z' } }
                : null
            }
          : { ok: false, verified: false, error: { code: 'apple_signature_verification_failed' } };
      }
    };
  },
  window: {
    MUNEA_DEV_CONFIG: { enabled: false },
    Capacitor: { Plugins: { Store: plugin } },
    MuneaAuth: {
      state() { return { authUserId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' }; },
      async getAccessToken() { return 'test-access-token'; }
    },
    __muneaApplyPurchase(_productId, purchase) { applied += 1; appliedPurchase = purchase; return true; }
  }
};
context.window.window = context.window;
context.window.localStorage = context.localStorage;
context.window.fetch = context.fetch;

vm.createContext(context);
vm.runInContext(fs.readFileSync('web/src/store.js', 'utf8'), context);

(async () => {
  const expectedPointProducts = {
    100: 'net.munea.app.points.200',
    300: 'net.munea.app.points.500',
    600: 'net.munea.app.points.1000',
    1000: 'net.munea.app.points.1800'
  };
  for (const [points, productId] of Object.entries(expectedPointProducts)) {
    if (context.window.MuneaStore.ptsId(Number(points)) !== productId) {
      throw new Error(`point package ${points} is not mapped to ${productId}`);
    }
  }
  const expectedAllProducts = [
    'net.munea.app.plus.monthly',
    'net.munea.app.plus.yearly',
    'net.munea.app.pro.monthly',
    'net.munea.app.pro.yearly',
    ...Object.values(expectedPointProducts)
  ];
  const localizedProducts = await context.window.MuneaStore.getProducts();
  if (!localizedProducts.ok || localizedProducts.products.length !== 8 ||
      productLoads !== 1 || loadedProductIds.join('|') !== expectedAllProducts.join('|')) {
    throw new Error('StoreKit localized product query did not load the exact 8-product set');
  }
  const cachedProduct = context.window.MuneaStore.product('net.munea.app.plus.monthly');
  if (!cachedProduct || cachedProduct.displayPrice !== '$19.99' ||
      cachedProduct.displayName !== 'Localized net.munea.app.plus.monthly') {
    throw new Error('localized StoreKit product metadata was not cached for App UI use');
  }

  const first = await context.window.MuneaStore.purchase(currentTransaction.productId);
  if (!first.ok || !first.verified || serverCalls !== 1 || applied !== 1 || finished !== 1) {
    throw new Error('verified purchase did not follow verify/apply/finish order');
  }

  const duplicate = await context.window.MuneaStore.purchase(currentTransaction.productId);
  if (!duplicate.ok || !duplicate.duplicate || serverCalls !== 2 || applied !== 1 || finished !== 2) {
    throw new Error('duplicate transaction was applied more than once or skipped server verification');
  }

  serverAllows = false;
  currentTransaction = { ...currentTransaction, transactionId: '100000000000002' };
  const rejected = await context.window.MuneaStore.purchase(currentTransaction.productId);
  if (rejected.ok || applied !== 1 || finished !== 2) {
    throw new Error('rejected transaction reached local entitlement or StoreKit finish');
  }

  serverAllows = true;
  currentTransaction = {
    ...currentTransaction,
    productId: 'net.munea.app.plus.monthly',
    transactionId: '100000000000003'
  };
  const subscription = await context.window.MuneaStore.purchase(currentTransaction.productId);
  if (!subscription.ok || applied !== 2 || finished !== 3 || !appliedPurchase.billing ||
      appliedPurchase.billing.subscription.expiresAt !== '2026-08-14T00:00:00Z') {
    throw new Error('verified subscription expiry was not forwarded to the app UI');
  }

  restoreTransactions = [{
    state: 'purchased',
    productId: 'net.munea.app.plus.monthly',
    transactionId: '100000000000004',
    originalTransactionId: '100000000000004',
    signedTransaction: 'header.payload.signature'
  }];
  const restored = await context.window.MuneaStore.restore();
  if (!restored.ok || restored.restored !== 'net.munea.app.plus.monthly' || applied !== 3 || finished !== 4) {
    throw new Error('restore did not verify, apply, and finish the active subscription');
  }

  const manageResult = await context.window.MuneaStore.manageSubscriptions();
  if (!manageResult.ok || managed !== 1) {
    throw new Error('native subscription management was not opened');
  }

  const callsBeforeSimulation = serverCalls;
  const nativeBeforeSimulation = nativePurchases;
  context.window.MUNEA_DEV_CONFIG = { enabled: true };
  context.window.MuneaAuth.state = () => ({
    authUserId: '00000000-0000-4000-8000-000000000104',
    developerMode: true
  });
  const simulated = await context.window.MuneaStore.purchase('net.munea.app.pro.monthly');
  if (!simulated.ok || !simulated.simulated || serverCalls !== callsBeforeSimulation ||
      nativePurchases !== nativeBeforeSimulation || applied !== 4) {
    throw new Error('developer purchase must simulate locally without Apple charge or server verification');
  }

  console.log('Store server verification PASS', {
    serverCalls,
    applied,
    finished,
    managed,
    nativePurchases,
    productLoads
  });
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
