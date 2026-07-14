const fs = require('fs');
const vm = require('vm');

let appUrlOpen = null;
let browserOpened = '';
let browserClosed = 0;
let oauthRequest = null;
let exchangedCode = '';

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
      oauthRequest = request;
      return { data: { url: 'https://example.supabase.co/oauth' }, error: null };
    },
    async exchangeCodeForSession(code) {
      exchangedCode = code;
      return { data: { session: signedInSession }, error: null };
    },
    async signInWithOtp() { return { data: {}, error: null }; },
    async signOut() { return { error: null }; },
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
  expect(oauthRequest.options.redirectTo === 'munea://auth/callback', 'native OAuth redirect is not the app deep link');
  expect(oauthRequest.options.skipBrowserRedirect === true, 'native OAuth would still navigate the embedded WebView');
  expect(browserOpened === 'https://example.supabase.co/oauth', 'OAuth URL was not opened with the native browser');

  await appUrlOpen({ url: 'munea://auth/callback?code=pkce-code' });
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(exchangedCode === 'pkce-code', 'PKCE authorization code was not exchanged');
  expect(browserClosed === 1, 'native browser was not closed after callback');
  expect(windowObject.MuneaAuth.state().status === 'signed-in', 'native callback did not publish a signed-in session');

  console.log('Native OAuth deep-link PASS');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
