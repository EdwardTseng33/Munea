const fs = require('fs');
const vm = require('vm');

let appUrlOpen = null;
let browserOpened = '';
let browserClosed = 0;
const oauthRequests = [];
let exchangedCode = '';
let appleNativeCalls = 0;
let googleNativeCalls = 0;
let googleNativeSignOutCalls = 0;
let lastIdTokenRequest = null;
let lastProfileUpdate = null;
let signOutRequest = null;
let createClientCalls = 0;
let currentSession = null;
let getUserCalls = 0;
let refreshSessionCalls = 0;
const rejectedTokens = new Set();
const authEvents = [];

const signedInSession = {
  access_token: 'access-token',
  refresh_token: 'refresh-token',
  user: {
    id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    email: 'tester@example.com',
    app_metadata: { provider: 'google' },
  },
};

const client = {
  auth: {
    async getSession() {
      const cloned = currentSession ? { ...currentSession, user: { ...currentSession.user } } : null;
      return { data: { session: cloned }, error: null };
    },
    async getUser(token) {
      getUserCalls += 1;
      if (rejectedTokens.has(token)) {
        return { data: { user: null }, error: { status: 403, code: 'bad_jwt', message: 'invalid JWT' } };
      }
      return { data: { user: currentSession && currentSession.user ? currentSession.user : signedInSession.user }, error: null };
    },
    async refreshSession() {
      refreshSessionCalls += 1;
      currentSession = {
        ...signedInSession,
        access_token: 'refreshed-access-token',
        refresh_token: 'refreshed-refresh-token',
        user: { ...signedInSession.user },
      };
      return { data: { session: currentSession }, error: null };
    },
    onAuthStateChange() {},
    async signInWithOAuth(request) {
      oauthRequests.push(request);
      return { data: { url: 'https://example.supabase.co/oauth' }, error: null };
    },
    async signInWithIdToken(request) {
      lastIdTokenRequest = request;
      currentSession = {
        ...signedInSession,
        access_token: `${request.provider}-access-token`,
        user: { ...signedInSession.user, app_metadata: { provider: request.provider } },
      };
      return {
        data: { session: currentSession },
        error: null,
      };
    },
    async updateUser(request) {
      lastProfileUpdate = request;
      return { data: { user: signedInSession.user }, error: null };
    },
    async exchangeCodeForSession(code) {
      exchangedCode = code;
      currentSession = signedInSession;
      return { data: { session: currentSession }, error: null };
    },
    async signInWithOtp() { return { data: {}, error: null }; },
    async signOut(request) {
      signOutRequest = request;
      return { error: null };
    },
  },
};

const windowObject = {
  location: {
    hostname: 'localhost',
    protocol: 'capacitor:',
    href: 'capacitor://localhost/index.html',
  },
  MUNEA_SUPABASE_CONFIG: {
    url: 'https://example.supabase.co',
    publishableKey: 'sb_publishable_test',
    nativeRedirectTo: 'munea://auth/callback',
  },
  MUNEA_DEV_CONFIG: { enabled: false },
  supabase: { createClient() { createClientCalls += 1; return client; } },
  Capacitor: {
    isNativePlatform() { return true; },
    Plugins: {
      App: {
        async addListener(name, callback) {
          if (name === 'appUrlOpen') appUrlOpen = callback;
          return { remove() {} };
        },
        async getLaunchUrl() { return undefined; },
      },
      Browser: {
        async open(options) { browserOpened = options.url; },
        async close() { browserClosed += 1; },
      },
      AppleSignIn: {
        async signIn() {
          appleNativeCalls += 1;
          return {
            state: 'authorized',
            identityToken: 'apple-identity-token',
            nonce: 'raw-apple-nonce',
            givenName: 'Munea',
            familyName: 'Tester',
            fullName: 'Munea Tester',
          };
        },
      },
      GoogleSignIn: {
        async signIn() {
          googleNativeCalls += 1;
          return {
            state: 'authorized',
            identityToken: 'google-identity-token',
            givenName: 'Munea',
            familyName: 'Tester',
            fullName: 'Munea Tester',
            avatarUrl: 'https://example.com/avatar.png',
          };
        },
        async signOut() {
          googleNativeSignOutCalls += 1;
          return { ok: true };
        },
      },
    },
  },
  dispatchEvent(event) { authEvents.push(event); },
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

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

async function testGateway401Recovery() {
  const appSource = fs.readFileSync('web/src/app.js', 'utf8');
  const start = appSource.indexOf('const CallControl = {');
  const end = appSource.indexOf('\nfunction getLiveVoiceUrl()', start);
  expect(start >= 0 && end > start, 'CallControl source could not be isolated');
  const requests = [];
  let recoverCalls = 0;
  const responses = [
    { ok: false, status: 401, async json() { return { detail: 'authentication_required' }; } },
    {
      ok: true,
      status: 200,
      async json() {
        return {
          status: 'connect', call_id: 'call-1', lease_version: 1,
          voice: { url: 'wss://voice.example' }, worker: { url: 'https://avatar.example' },
        };
      },
    },
  ];
  const callContext = {
    console,
    CALL_CONTROL_URL_DEFAULT: 'https://gateway.example',
    usesDevelopmentDirectCall() { return false; },
    developerConfig() { return {}; },
    isDeveloperBypassAllowed() { return false; },
    async muneaAuthHeaders(headers) {
      return { ...headers, Authorization: 'Bearer stale-token', 'X-Munea-Key': 'door-key' };
    },
    window: {
      crypto: { randomUUID() { return 'stable-idempotency-key'; } },
      MuneaAuth: {
        async recoverRejectedSession() {
          recoverCalls += 1;
          return 'fresh-token';
        },
      },
    },
    async fetch(url, options) {
      requests.push({ url, options });
      return responses.shift();
    },
    voiceCallMark() {},
    setCallHint() {},
    clearInterval() {},
    setInterval() { return 1; },
  };
  callContext.globalThis = callContext;
  vm.createContext(callContext);
  const callControlSource = appSource.slice(start, end)
    .replace('const CallControl =', 'globalThis.CallControl =');
  vm.runInContext(callControlSource, callContext);
  const lease = await callContext.CallControl.acquire('nening');
  expect(lease && lease.status === 'connect', 'Gateway retry did not return the recovered lease');
  expect(requests.length === 2, 'Gateway 401 did not perform exactly one retry');
  expect(recoverCalls === 1, 'Gateway 401 did not force exactly one session recovery');
  expect(requests[0].options.headers.Authorization === 'Bearer stale-token', 'first request did not use the current token');
  expect(requests[1].options.headers.Authorization === 'Bearer fresh-token', 'retry did not use the recovered token');
  expect(requests[0].options.body === requests[1].options.body, 'Gateway retry changed the idempotent request body');
  expect(requests[1].options.body.includes('stable-idempotency-key'), 'Gateway retry lost the idempotency key');
}

async function testGatewayAccountBootstrapRecovery() {
  const appSource = fs.readFileSync('web/src/app.js', 'utf8');
  const start = appSource.indexOf('const CallControl = {');
  const end = appSource.indexOf('\nfunction getLiveVoiceUrl()', start);
  const requests = [];
  let bootstrapCalls = 0;
  const responses = [
    {
      ok: true,
      status: 200,
      async json() { return { status: 'reject', reason: 'account_not_ready' }; },
    },
    {
      ok: true,
      status: 200,
      async json() {
        return {
          status: 'connect', call_id: 'call-after-bootstrap', lease_version: 1,
          voice: { url: 'wss://voice.example' }, worker: { url: 'https://avatar.example' },
        };
      },
    },
  ];
  const callContext = {
    console,
    CALL_CONTROL_URL_DEFAULT: 'https://gateway.example',
    usesDevelopmentDirectCall() { return false; },
    developerConfig() { return {}; },
    isDeveloperBypassAllowed() { return false; },
    async muneaAuthHeaders(headers) {
      return { ...headers, Authorization: 'Bearer valid-token' };
    },
    async syncAccountBootstrap(action, extra) {
      bootstrapCalls += 1;
      expect(action === 'create', 'account recovery used the wrong bootstrap action');
      expect(extra && extra.force === true, 'account recovery did not force server verification');
      return { ok: true };
    },
    window: { crypto: { randomUUID() { return 'account-recovery-idempotency-key'; } } },
    async fetch(url, options) {
      requests.push({ url, options });
      return responses.shift();
    },
    voiceCallMark() {},
    setCallHint() {},
    clearInterval() {},
    setInterval() { return 1; },
  };
  callContext.globalThis = callContext;
  vm.createContext(callContext);
  vm.runInContext(
    appSource.slice(start, end).replace('const CallControl =', 'globalThis.CallControl ='),
    callContext,
  );
  const lease = await callContext.CallControl.acquire('nening');
  expect(lease && lease.status === 'connect', 'Gateway did not connect after account bootstrap');
  expect(bootstrapCalls === 1, 'account_not_ready did not trigger exactly one bootstrap');
  expect(requests.length === 2, 'account_not_ready did not retry exactly once');
  expect(requests[0].options.body === requests[1].options.body,
    'account bootstrap retry changed the idempotent request body');
}

(async () => {
  await Promise.all([
    windowObject.MuneaAuth.init(),
    windowObject.MuneaAuth.getAccessToken(),
    windowObject.MuneaAuth.getAccessToken(),
  ]);
  expect(createClientCalls === 1, 'concurrent auth calls created multiple Supabase clients');
  expect(typeof appUrlOpen === 'function', 'native appUrlOpen listener was not registered');

  const started = await windowObject.MuneaAuth.signInWithGoogle();
  expect(started.ok, 'native Google Sign-In did not complete');
  expect(googleNativeCalls === 1, 'native Google plugin was not called exactly once');
  expect(oauthRequests.length === 0, 'native Google incorrectly used the browser OAuth path');
  expect(browserOpened === '', 'native Google opened the Supabase browser flow');
  expect(lastIdTokenRequest && lastIdTokenRequest.provider === 'google', 'Google ID token was not sent to Supabase');
  expect(lastIdTokenRequest.token === 'google-identity-token', 'Google identity token was changed');
  expect(lastProfileUpdate && lastProfileUpdate.data.full_name === 'Munea Tester', 'Google profile name was not saved');
  expect(lastProfileUpdate.data.avatar_url === 'https://example.com/avatar.png', 'Google profile photo was not saved');
  expect(windowObject.MuneaAuth.state().status === 'signed-in', 'native Google session was not published');
  expect(windowObject.MuneaAuth.state().provider === 'google', 'native Google provider was not published');
  const eventsAfterSignIn = authEvents.length;
  expect(await windowObject.MuneaAuth.getAccessToken() === 'google-access-token', 'signed-in access token was not returned');
  expect(authEvents.length === eventsAfterSignIn, 'equivalent Supabase session caused a duplicate auth-state event');

  rejectedTokens.add('rejected-access-token');
  currentSession = {
    ...signedInSession,
    access_token: 'rejected-access-token',
    refresh_token: 'stale-refresh-token',
    user: { ...signedInSession.user },
  };
  expect(await windowObject.MuneaAuth.getAccessToken() === 'refreshed-access-token',
    'a server-rejected access token was not refreshed before an API call');
  expect(refreshSessionCalls === 1, 'a rejected access token did not trigger exactly one refresh');
  const verifiedCalls = getUserCalls;
  expect(await windowObject.MuneaAuth.getAccessToken() === 'refreshed-access-token',
    'the refreshed access token was not retained');
  expect(getUserCalls === verifiedCalls, 'a verified access token was revalidated on every API call');

  currentSession = {
    ...signedInSession,
    access_token: 'gateway-rejected-access-token',
    refresh_token: 'gateway-rejected-refresh-token',
    user: { ...signedInSession.user },
  };
  expect(await windowObject.MuneaAuth.getAccessToken() === 'gateway-rejected-access-token',
    'the SDK-valid test token was not cached before the Gateway rejection');
  expect(await windowObject.MuneaAuth.recoverRejectedSession() === 'refreshed-access-token',
    'a Gateway-rejected token did not force a session refresh');
  expect(refreshSessionCalls === 2, 'Gateway rejection did not trigger exactly one additional forced refresh');

  const googleSignedOut = await windowObject.MuneaAuth.signOut();
  expect(googleSignedOut.ok, 'Google local sign out did not complete');
  expect(googleNativeSignOutCalls === 1, 'native Google session was not cleared on sign out');

  const nativeGoogleSignIn = windowObject.Capacitor.Plugins.GoogleSignIn.signIn;
  windowObject.Capacitor.Plugins.GoogleSignIn.signIn = async () => {
    googleNativeCalls += 1;
    return { state: 'cancelled' };
  };
  const cancelledGoogle = await windowObject.MuneaAuth.signInWithGoogle();
  expect(!cancelledGoogle.ok && cancelledGoogle.cancelled, 'cancelled native Google Sign-In was not preserved');
  expect(oauthRequests.length === 0, 'cancelled native Google Sign-In incorrectly opened the browser fallback');

  windowObject.Capacitor.Plugins.GoogleSignIn.signIn = async () => {
    googleNativeCalls += 1;
    const error = new Error('native Google unavailable');
    error.code = 'google_sign_in_failed';
    throw error;
  };
  const fallbackGoogle = await windowObject.MuneaAuth.signInWithGoogle();
  expect(fallbackGoogle.ok, 'native Google failure did not start the browser OAuth fallback');
  expect(fallbackGoogle.authPath === 'browser-oauth', 'Google fallback did not identify the browser OAuth path');
  expect(fallbackGoogle.fallbackFrom === 'google_sign_in_failed', 'Google fallback lost the native failure code');
  expect(oauthRequests.length === 1, 'Google fallback did not issue exactly one OAuth request');
  expect(oauthRequests[0].provider === 'google', 'Google fallback used the wrong OAuth provider');
  expect(oauthRequests[0].options.redirectTo === 'munea://auth/callback', 'Google fallback lost the native callback');
  expect(oauthRequests[0].options.skipBrowserRedirect === true, 'Google fallback would navigate the embedded WebView');
  expect(oauthRequests[0].options.queryParams.prompt === 'select_account', 'Google fallback does not force account selection');
  expect(browserOpened === 'https://example.supabase.co/oauth', 'Google fallback did not open the system browser');
  await appUrlOpen({ url: 'munea://auth/callback?code=google-fallback-code' });
  await new Promise(resolve => setImmediate(resolve));
  expect(exchangedCode === 'google-fallback-code', 'Google fallback callback did not exchange the PKCE code');
  expect(browserClosed === 1, 'Google fallback callback did not close the system browser');
  expect(windowObject.MuneaAuth.state().status === 'signed-in', 'Google fallback did not publish the signed-in session');
  windowObject.Capacitor.Plugins.GoogleSignIn.signIn = nativeGoogleSignIn;

  const apple = await windowObject.MuneaAuth.signInWithApple();
  expect(apple.ok, 'native Apple sign in did not complete');
  expect(appleNativeCalls === 1, 'native Apple plugin was not called exactly once');
  expect(oauthRequests.length === 1, 'Apple incorrectly used the browser OAuth path');
  expect(lastIdTokenRequest && lastIdTokenRequest.provider === 'apple', 'Apple ID token was not sent to Supabase');
  expect(lastIdTokenRequest.token === 'apple-identity-token', 'Apple identity token was changed');
  expect(lastIdTokenRequest.nonce === 'raw-apple-nonce', 'Apple raw nonce was not sent to Supabase');
  expect(lastProfileUpdate && lastProfileUpdate.data.full_name === 'Munea Tester', 'first Apple profile name was not saved');
  expect(windowObject.MuneaAuth.state().provider === 'apple', 'Apple session was not published');

  const signedOut = await windowObject.MuneaAuth.signOut();
  expect(signedOut.ok, 'local sign out did not complete');
  expect(signOutRequest && signOutRequest.scope === 'local', 'sign out would revoke sessions on other devices');
  expect(googleNativeSignOutCalls === 1, 'Apple sign out incorrectly cleared Google Sign-In again');
  expect(windowObject.MuneaAuth.state().status === 'guest', 'local sign out did not publish guest state');

  await testGateway401Recovery();
  await testGatewayAccountBootstrapRecovery();

  console.log('Native auth, Gateway 401 recovery, and account bootstrap recovery PASS');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
