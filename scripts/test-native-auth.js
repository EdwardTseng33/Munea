const fs = require('fs');
const vm = require('vm');

let appUrlOpen = null;
let browserOpened = '';
let browserClosed = 0;
const oauthRequests = [];
let exchangedCode = '';
let appleNativeCalls = 0;
let appleIdTokenRequest = null;
let appleProfileUpdate = null;
let signOutRequest = null;

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
    async getSession() { return { data: { session: null }, error: null }; },
    onAuthStateChange() {},
    async signInWithOAuth(request) {
      oauthRequests.push(request);
      return { data: { url: 'https://example.supabase.co/oauth' }, error: null };
    },
    async signInWithIdToken(request) {
      appleIdTokenRequest = request;
      return {
        data: {
          session: {
            ...signedInSession,
            user: { ...signedInSession.user, app_metadata: { provider: 'apple' } },
          },
        },
        error: null,
      };
    },
    async updateUser(request) {
      appleProfileUpdate = request;
      return { data: { user: signedInSession.user }, error: null };
    },
    async exchangeCodeForSession(code) {
      exchangedCode = code;
      return { data: { session: signedInSession }, error: null };
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
  supabase: { createClient() { return client; } },
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
    },
  },
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

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

(async () => {
  await windowObject.MuneaAuth.init();
  expect(typeof appUrlOpen === 'function', 'native appUrlOpen listener was not registered');

  const started = await windowObject.MuneaAuth.signInWithGoogle();
  expect(started.ok, 'native Google OAuth did not start');
  expect(oauthRequests[0].options.redirectTo === 'munea://auth/callback', 'native OAuth redirect is not the app deep link');
  expect(oauthRequests[0].options.skipBrowserRedirect === true, 'native OAuth would still navigate the embedded WebView');
  expect(oauthRequests[0].options.queryParams.prompt === 'select_account', 'Google OAuth would silently reuse the previous account');
  expect(browserOpened === 'https://example.supabase.co/oauth', 'OAuth URL was not opened with the native browser');

  await appUrlOpen({ url: 'munea://auth/callback?code=pkce-code' });
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(exchangedCode === 'pkce-code', 'PKCE authorization code was not exchanged');
  expect(browserClosed === 1, 'native browser was not closed after callback');
  expect(windowObject.MuneaAuth.state().status === 'signed-in', 'native callback did not publish a signed-in session');

  const apple = await windowObject.MuneaAuth.signInWithApple();
  expect(apple.ok, 'native Apple sign in did not complete');
  expect(appleNativeCalls === 1, 'native Apple plugin was not called exactly once');
  expect(oauthRequests.length === 1, 'Apple incorrectly used the browser OAuth path');
  expect(appleIdTokenRequest && appleIdTokenRequest.provider === 'apple', 'Apple ID token was not sent to Supabase');
  expect(appleIdTokenRequest.token === 'apple-identity-token', 'Apple identity token was changed');
  expect(appleIdTokenRequest.nonce === 'raw-apple-nonce', 'Apple raw nonce was not sent to Supabase');
  expect(appleProfileUpdate && appleProfileUpdate.data.full_name === 'Munea Tester', 'first Apple profile name was not saved');
  expect(windowObject.MuneaAuth.state().provider === 'apple', 'Apple session was not published');

  const signedOut = await windowObject.MuneaAuth.signOut();
  expect(signedOut.ok, 'local sign out did not complete');
  expect(signOutRequest && signOutRequest.scope === 'local', 'sign out would revoke sessions on other devices');
  expect(windowObject.MuneaAuth.state().status === 'guest', 'local sign out did not publish guest state');

  console.log('Native Google OAuth and Apple ID token PASS');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
