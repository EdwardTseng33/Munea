// 2026-07-18 專用真測試帳號施工：驗證「開發者鈕在 --gateway profile 走真登入路徑、非假證」。
// 兩段測試：
//   1) auth.js signInWithTestAccount() 真的呼叫 Supabase signInWithPassword、拿到的 session
//      不是 makeDeveloperSession() 造的假證（沒有 dev-local-token- 前綴、沒有 developer:true 標記）。
//   2) app.js signInDeveloperMode() 依 profile 正確分流：direct 測試包仍走 signInAsDeveloper（假證，
//      不變）；gateway 測試包改走 signInWithTestAccount（真登入），兩條路互不誤觸。
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

function extractFunction(source, signature) {
  const idx = source.indexOf(signature);
  if (idx === -1) throw new Error(`signature not found: ${signature}`);
  const braceStart = source.indexOf('{', idx);
  if (braceStart === -1) throw new Error(`no opening brace for: ${signature}`);
  let depth = 0;
  let i = braceStart;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') {
      depth--;
      if (depth === 0) { i++; break; }
    }
  }
  return source.slice(idx, i);
}

// ---------- Part 1: auth.js signInWithTestAccount() real-login behaviour ----------
const part1 = (function testAuthSignInWithTestAccount() {
  const passwordSignInCalls = [];
  const client = {
    auth: {
      async signInWithPassword(request) {
        passwordSignInCalls.push(request);
        if (request.email === 'dev@munea.net' && request.password === 'correct-horse-battery-staple') {
          return {
            data: {
              session: {
                access_token: 'real-tokyo-jwt-access-token',
                refresh_token: 'real-tokyo-jwt-refresh-token',
                user: { id: 'real-user-id', email: request.email, app_metadata: { role: 'qa_review' } },
              },
            },
            error: null,
          };
        }
        return { data: { session: null }, error: { status: 400, code: 'invalid_credentials', message: 'Invalid login credentials' } };
      },
      onAuthStateChange() {},
      async getSession() { return { data: { session: null }, error: null }; },
    },
  };

  const windowObject = {
    location: { hostname: 'localhost', protocol: 'capacitor:', href: 'capacitor://localhost/index.html' },
    MUNEA_SUPABASE_CONFIG: { url: 'https://example.supabase.co', publishableKey: 'sb_publishable_test' },
    MUNEA_DEV_CONFIG: {
      enabled: true,
      allowNonLocalhost: true,
      bypassCallControl: false,
      testAccountEmail: 'dev@munea.net',
      testAccountPassword: 'correct-horse-battery-staple',
    },
    supabase: { createClient() { return client; } },
    dispatchEvent() {},
  };

  const context = {
    console,
    URL,
    URLSearchParams,
    CustomEvent: class CustomEvent { constructor(name, options) { this.type = name; this.detail = options && options.detail; } },
    window: windowObject,
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('web/src/auth.js', 'utf8'), context);

  return (async () => {
    await windowObject.MuneaAuth.init();
    const result = await windowObject.MuneaAuth.signInWithTestAccount();
    assert.strictEqual(passwordSignInCalls.length, 1, 'signInWithTestAccount did not call Supabase signInWithPassword exactly once');
    assert.strictEqual(passwordSignInCalls[0].email, 'dev@munea.net', 'signInWithTestAccount sent the wrong email');
    assert.strictEqual(passwordSignInCalls[0].password, 'correct-horse-battery-staple', 'signInWithTestAccount sent the wrong password');
    assert.strictEqual(result.ok, true, 'signInWithTestAccount did not report success for valid credentials');
    assert.strictEqual(result.session.access_token, 'real-tokyo-jwt-access-token', 'signInWithTestAccount did not return the real Supabase access token');
    assert.ok(!result.session.access_token.startsWith('dev-local-token-'), 'signInWithTestAccount leaked a fixture dev-local-token session');
    assert.ok(!result.session.developer, 'signInWithTestAccount session was incorrectly marked as a fixture developer session');
    assert.strictEqual(windowObject.MuneaAuth.state().status, 'signed-in', 'signInWithTestAccount did not publish signed-in state');

    windowObject.MUNEA_DEV_CONFIG.testAccountEmail = '';
    windowObject.MUNEA_DEV_CONFIG.testAccountPassword = '';
    const missing = await windowObject.MuneaAuth.signInWithTestAccount();
    assert.strictEqual(missing.ok, false, 'signInWithTestAccount should fail when no credentials are configured');
    assert.strictEqual(missing.error.code, 'test_account_credentials_missing', 'signInWithTestAccount did not report the missing-credentials error code');

    windowObject.MUNEA_DEV_CONFIG.testAccountEmail = 'dev@munea.net';
    windowObject.MUNEA_DEV_CONFIG.testAccountPassword = 'wrong-password';
    const rejected = await windowObject.MuneaAuth.signInWithTestAccount();
    assert.strictEqual(rejected.ok, false, 'signInWithTestAccount should fail for a rejected password');
    assert.strictEqual(rejected.error.code, 'invalid_credentials', 'signInWithTestAccount did not surface the Supabase rejection code');

    console.log('auth.js signInWithTestAccount PASS: real Supabase login, no fixture leakage, fails closed without credentials');
  })();
})();

// ---------- Part 2: app.js signInDeveloperMode() profile routing ----------
const part2 = (function testDeveloperButtonRouting() {
  const app = fs.readFileSync('web/src/app.js', 'utf8');
  const developerConfigSrc = extractFunction(app, 'function developerConfig()');
  const isLocalDevHostSrc = extractFunction(app, 'function isLocalDevHost()');
  const isDeveloperBypassAllowedSrc = extractFunction(app, 'function isDeveloperBypassAllowed()');
  const usesDevelopmentDirectCallSrc = extractFunction(app, 'function usesDevelopmentDirectCall()');
  const isGatewayDeveloperProfileSrc = extractFunction(app, 'function isGatewayDeveloperProfile()');
  const signInDeveloperModeSrc = extractFunction(app, 'async function signInDeveloperMode()');

  for (const [name, src] of [
    ['isGatewayDeveloperProfile', isGatewayDeveloperProfileSrc],
    ['signInDeveloperMode', signInDeveloperModeSrc],
  ]) {
    assert.ok(src && src.length > 10, `could not isolate ${name} from web/src/app.js`);
  }
  assert.match(isGatewayDeveloperProfileSrc, /isDeveloperBypassAllowed\(\)\s*&&\s*!usesDevelopmentDirectCall\(\)/,
    'isGatewayDeveloperProfile no longer keys off the real Call Control bypass flag');
  assert.match(signInDeveloperModeSrc, /auth\.signInWithTestAccount/, 'signInDeveloperMode lost its real-login gateway path');
  assert.match(signInDeveloperModeSrc, /auth\.signInAsDeveloper/, 'signInDeveloperMode lost its fixture direct-call path');

  function buildContext(developerConfigValue) {
    const trackCalls = [];
    const messages = [];
    let updateAuthUICalls = 0;
    let closeAuthSheetCalls = 0;
    const testAccountCalls = [];
    const developerCalls = [];
    const context = {
      console,
      window: {
        MuneaAuth: {
          async signInWithTestAccount(overrides) {
            testAccountCalls.push(overrides);
            return { ok: true, session: { access_token: 'real-tokyo-jwt-access-token' } };
          },
          async signInAsDeveloper(overrides) {
            developerCalls.push(overrides);
            return { ok: true, session: { access_token: 'dev-local-token-00000000-0000-4000-8000-000000000104', developer: true } };
          },
        },
      },
      trackProductEvent(name, props) { trackCalls.push({ name, props }); },
      setAuthMessage(text, type) { messages.push({ text, type }); },
      updateAuthUI() { updateAuthUICalls += 1; },
      closeAuthSheet() { closeAuthSheetCalls += 1; },
    };
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(
      developerConfigSrc + '\n' + isLocalDevHostSrc + '\n' + isDeveloperBypassAllowedSrc + '\n' +
      usesDevelopmentDirectCallSrc + '\n' + isGatewayDeveloperProfileSrc + '\n' + signInDeveloperModeSrc +
      '\nglobalThis.developerConfig = developerConfig;\nglobalThis.signInDeveloperMode = signInDeveloperMode;',
      context,
    );
    context.developerConfig = () => developerConfigValue;
    return { context, trackCalls, messages, testAccountCalls, developerCalls, getUpdateCalls: () => updateAuthUICalls, getCloseCalls: () => closeAuthSheetCalls };
  }

  return (async () => {
    const direct = buildContext({ enabled: true, allowNonLocalhost: true, bypassCallControl: true });
    await direct.context.signInDeveloperMode();
    assert.strictEqual(direct.testAccountCalls.length, 0, 'direct profile incorrectly triggered the real test-account login');
    assert.strictEqual(direct.developerCalls.length, 1, 'direct profile did not use the fixture developer sign-in');
    assert.strictEqual(direct.getUpdateCalls(), 1, 'direct profile sign-in did not refresh the auth UI');
    assert.strictEqual(direct.getCloseCalls(), 1, 'direct profile sign-in did not close the auth sheet');

    const gateway = buildContext({ enabled: true, allowNonLocalhost: true, bypassCallControl: false });
    await gateway.context.signInDeveloperMode();
    assert.strictEqual(gateway.developerCalls.length, 0, 'gateway profile incorrectly used the fixture dev-local-token path');
    assert.strictEqual(gateway.testAccountCalls.length, 1, 'gateway profile did not call the real test-account login exactly once');
    assert.strictEqual(gateway.getUpdateCalls(), 1, 'gateway profile sign-in did not refresh the auth UI');
    assert.strictEqual(gateway.getCloseCalls(), 1, 'gateway profile sign-in did not close the auth sheet');
    assert.strictEqual(gateway.trackCalls.some(c => c.name === 'auth_developer_signed_in' && c.props.provider === 'test-account'), true,
      'gateway profile sign-in did not record the test-account analytics provider');

    const gatewayMissing = buildContext({ enabled: true, allowNonLocalhost: true, bypassCallControl: false });
    gatewayMissing.context.window.MuneaAuth.signInWithTestAccount = async () => {
      gatewayMissing.testAccountCalls.push('missing');
      return { ok: false, error: { code: 'test_account_credentials_missing' } };
    };
    await gatewayMissing.context.signInDeveloperMode();
    assert.strictEqual(gatewayMissing.getUpdateCalls(), 0, 'a failed gateway login must not refresh the auth UI as if signed in');
    assert.strictEqual(gatewayMissing.getCloseCalls(), 0, 'a failed gateway login must not close the auth sheet');
    assert.strictEqual(gatewayMissing.messages.some(m => m.text === '測試帳號憑證未設定' && m.type === 'error'), true,
      'missing gateway credentials did not surface the expected error message');

    console.log('app.js signInDeveloperMode routing PASS: direct profile keeps the fixture path, gateway profile uses real test-account login');
  })();
})();

Promise.all([part1, part2]).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
