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

  const googleSignedOut = await windowObject.MuneaAuth.signOut();
  expect(googleSignedOut.ok, 'Google local sign out did not complete');
  expect(googleNativeSignOutCalls === 1, 'native Google session was not cleared on sign out');

  const apple = await windowObject.MuneaAuth.signInWithApple();
  expect(apple.ok, 'native Apple sign in did not complete');
  expect(appleNativeCalls === 1, 'native Apple plugin was not called exactly once');
  expect(oauthRequests.length === 0, 'Apple incorrectly used the browser OAuth path');
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

  console.log('Native Google and Apple ID token PASS');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
