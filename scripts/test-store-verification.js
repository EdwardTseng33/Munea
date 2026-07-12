const fs = require('fs');
const vm = require('vm');

const storage = new Map();
let serverCalls = 0;
let applied = 0;
let finished = 0;
let serverAllows = true;
let currentTransaction = {
  state: 'purchased',
  productId: 'net.munea.app.points.200',
  transactionId: '100000000000001',
  originalTransactionId: '100000000000001',
  signedTransaction: 'header.payload.signature'
};

const plugin = {
  addListener() {},
  async purchase() { return { ...currentTransaction }; },
  async finish() { finished += 1; return { ok: true }; },
  async restore() { return { transactions: [] }; }
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
          ? { ok: true, verified: true, walletSummary: { purchased: 200 }, idempotentReplay: serverCalls > 1 }
          : { ok: false, verified: false, error: { code: 'apple_signature_verification_failed' } };
      }
    };
  },
  window: {
    Capacitor: { Plugins: { Store: plugin } },
    MuneaAuth: {
      state() { return { authUserId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' }; },
      async getAccessToken() { return 'test-access-token'; }
    },
    __muneaApplyPurchase() { applied += 1; return true; }
  }
};
context.window.window = context.window;
context.window.localStorage = context.localStorage;
context.window.fetch = context.fetch;

vm.createContext(context);
vm.runInContext(fs.readFileSync('web/src/store.js', 'utf8'), context);

(async () => {
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

  console.log('Store server verification PASS', { serverCalls, applied, finished });
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
