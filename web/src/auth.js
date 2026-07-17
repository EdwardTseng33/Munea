(function () {
  const AUTH_STATE_EVENT = 'munea:auth-state';
  const ALLOWED_OAUTH_PROVIDERS = new Set(['apple', 'google']);
  let client = null;
  let clientPromise = null;
  let initPromise = null;
  let session = null;
  let status = 'guest';
  let lastEvent = 'INITIAL';
  let nativeAuthListenerPromise = null;
  let verifiedAccessToken = '';
  let tokenValidation = null;

  function config() {
    return window.MUNEA_SUPABASE_CONFIG || {};
  }

  function devConfig() {
    return window.MUNEA_DEV_CONFIG || {};
  }

  function isLocalDevHost() {
    return ['localhost', '127.0.0.1', ''].includes(window.location.hostname) || window.location.protocol === 'file:';
  }

  function isDeveloperModeAllowed() {
    const cfg = devConfig();
    return cfg.enabled === true && (cfg.allowNonLocalhost === true || isLocalDevHost());
  }

  function devUserId() {
    const cfg = devConfig();
    return cfg.authUserId || cfg.userId || '00000000-0000-4000-8000-000000000001';
  }

  function makeDeveloperSession(overrides = {}) {
    const cfg = { ...devConfig(), ...overrides };
    const id = cfg.authUserId || cfg.userId || devUserId();
    const email = cfg.email || 'developer@munea.local';
    return {
      access_token: cfg.accessToken || `dev-local-token-${id}`,
      token_type: 'bearer',
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      user: {
        id,
        email,
        app_metadata: { provider: 'dev-bypass', role: 'developer' },
        user_metadata: { name: cfg.displayName || 'Munea Developer' },
      },
      developer: true,
    };
  }

  function publishableKey(cfg) {
    return cfg.publishableKey || cfg.anonKey || cfg.key || '';
  }

  function redirectTo(path) {
    const cfg = config();
    if (isNativeApp()) return cfg.nativeRedirectTo || 'munea://auth/callback';
    if (cfg.redirectTo) return cfg.redirectTo;
    try {
      return new URL(path || 'index.html', window.location.href).toString();
    } catch (e) {
      return window.location.href;
    }
  }

  function nativePlugin(name) {
    const capacitor = window.Capacitor;
    return capacitor && capacitor.Plugins ? capacitor.Plugins[name] || null : null;
  }

  function isNativeApp() {
    const capacitor = window.Capacitor;
    if (!capacitor) return false;
    if (typeof capacitor.isNativePlatform === 'function') return capacitor.isNativePlatform();
    return !!(capacitor.Plugins && (capacitor.Plugins.App || capacitor.Plugins.Browser));
  }

  function authCallbackParams(rawUrl) {
    try {
      const parsed = new URL(rawUrl);
      const query = parsed.searchParams;
      const hash = new URLSearchParams((parsed.hash || '').replace(/^#/, ''));
      return {
        code: query.get('code') || hash.get('code') || '',
        accessToken: query.get('access_token') || hash.get('access_token') || '',
        refreshToken: query.get('refresh_token') || hash.get('refresh_token') || '',
        error: query.get('error_description') || hash.get('error_description') || query.get('error') || hash.get('error') || '',
      };
    } catch (e) {
      return { code: '', accessToken: '', refreshToken: '', error: 'invalid_callback_url' };
    }
  }

  async function completeNativeAuth(rawUrl) {
    if (!/^munea:\/\/auth\/callback(?:[/?#]|$)/i.test(String(rawUrl || ''))) return false;
    const browser = nativePlugin('Browser');
    if (browser && typeof browser.close === 'function') {
      try { await browser.close(); } catch (e) {}
    }
    const params = authCallbackParams(rawUrl);
    if (params.error) {
      setState('guest', null, 'OAUTH_ERROR');
      return false;
    }
    const supabaseClient = await ensureClient();
    if (!supabaseClient) return false;
    try {
      let result = null;
      if (params.code && typeof supabaseClient.auth.exchangeCodeForSession === 'function') {
        result = await supabaseClient.auth.exchangeCodeForSession(params.code);
      } else if (params.accessToken && params.refreshToken && typeof supabaseClient.auth.setSession === 'function') {
        result = await supabaseClient.auth.setSession({
          access_token: params.accessToken,
          refresh_token: params.refreshToken,
        });
      }
      const nextSession = result && result.data ? result.data.session : null;
      if (!result || result.error || !nextSession) {
        setState('guest', null, 'OAUTH_SESSION_FAILED');
        return false;
      }
      setState('signed-in', nextSession, 'SIGNED_IN');
      return true;
    } catch (e) {
      setState('guest', null, 'OAUTH_SESSION_FAILED');
      return false;
    }
  }

  function setupNativeAuthListener() {
    if (!isNativeApp()) return Promise.resolve(false);
    if (nativeAuthListenerPromise) return nativeAuthListenerPromise;
    nativeAuthListenerPromise = (async () => {
      const app = nativePlugin('App');
      if (!app || typeof app.addListener !== 'function') return false;
      await app.addListener('appUrlOpen', event => {
        if (event && event.url) void completeNativeAuth(event.url);
      });
      if (typeof app.getLaunchUrl === 'function') {
        try {
          const launch = await app.getLaunchUrl();
          if (launch && launch.url) await completeNativeAuth(launch.url);
        } catch (e) {}
      }
      return true;
    })();
    return nativeAuthListenerPromise;
  }

  function sameSession(left, right) {
    if (left === right) return true;
    if (!left || !right) return false;
    const leftUserId = left.user && left.user.id ? left.user.id : '';
    const rightUserId = right.user && right.user.id ? right.user.id : '';
    return leftUserId === rightUserId &&
      String(left.access_token || '') === String(right.access_token || '');
  }

  function setState(nextStatus, nextSession, eventName) {
    const normalizedSession = nextSession || null;
    const nextAccessToken = normalizedSession && normalizedSession.access_token
      ? String(normalizedSession.access_token)
      : '';
    if (verifiedAccessToken && verifiedAccessToken !== nextAccessToken) verifiedAccessToken = '';
    const changed = status !== nextStatus || !sameSession(session, normalizedSession);
    status = nextStatus;
    session = normalizedSession;
    lastEvent = eventName || lastEvent;
    if (!changed) return false;
    window.dispatchEvent(new CustomEvent(AUTH_STATE_EVENT, { detail: publicState() }));
    return true;
  }

  function publicState() {
    const user = session && session.user ? session.user : null;
    const userMetadata = user && user.user_metadata ? user.user_metadata : {};
    const avatarUrl = userMetadata.avatar_url || userMetadata.picture || userMetadata.photo_url || null;
    return {
      configured: isConfigured(),
      developerMode: isDeveloperModeAllowed() && !!(session && session.developer),
      status,
      event: lastEvent,
      user,
      userId: user ? user.id : null,
      authUserId: user ? user.id : null,
      email: user ? user.email || null : null,
      name: userMetadata.name || userMetadata.full_name || userMetadata.displayName || null,
      provider: user && user.app_metadata ? user.app_metadata.provider || null : null,
      avatarUrl,
    };
  }

  function isConfigured() {
    const cfg = config();
    return !!(cfg.url && publishableKey(cfg));
  }

  async function loadFactory(cfg) {
    if (window.supabase && typeof window.supabase.createClient === 'function') {
      return window.supabase.createClient;
    }
    if (!cfg.sdkUrl) return null;
    try {
      const mod = await import(cfg.sdkUrl);
      return mod.createClient || (mod.default && mod.default.createClient) || null;
    } catch (e) {
      return null;
    }
  }

  async function ensureClient() {
    if (client) return client;
    if (clientPromise) return clientPromise;
    clientPromise = (async () => {
      const cfg = config();
      if (!isConfigured()) {
        setState('guest', null, 'UNCONFIGURED');
        return null;
      }
      const createClient = await loadFactory(cfg);
      if (!createClient) {
        setState('unconfigured', null, 'SDK_MISSING');
        return null;
      }
      client = createClient(cfg.url, publishableKey(cfg), {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
          flowType: 'pkce',
          ...(cfg.authOptions || {}),
        },
      });
      return client;
    })();
    try { return await clientPromise; }
    finally { clientPromise = null; }
  }

  async function init() {
    if (initPromise) return initPromise;
    initPromise = (async () => {
      await setupNativeAuthListener();
      if (isDeveloperModeAllowed() && devConfig().autoSignIn === true) {
        return signInAsDeveloper({ reason: 'auto_sign_in' });
      }
      const supabaseClient = await ensureClient();
      if (!supabaseClient) return publicState();
      try {
        const result = await supabaseClient.auth.getSession();
        const currentSession = result && result.data ? result.data.session : null;
        setState(currentSession ? 'signed-in' : 'guest', currentSession, 'SESSION_LOADED');
        supabaseClient.auth.onAuthStateChange((eventName, nextSession) => {
          setState(nextSession ? 'signed-in' : 'guest', nextSession, eventName);
        });
      } catch (e) {
        setState('guest', null, 'SESSION_UNAVAILABLE');
      }
      return publicState();
    })();
    return initPromise;
  }

  async function signInWithProvider(provider) {
    const normalized = String(provider || '').toLowerCase();
    if (!ALLOWED_OAUTH_PROVIDERS.has(normalized)) {
      return { ok: false, error: { code: 'unsupported_provider' } };
    }
    const supabaseClient = await ensureClient();
    if (!supabaseClient) return { ok: false, error: { code: 'auth_not_configured' } };
    const native = isNativeApp();
    if (native && normalized === 'apple') return signInWithNativeApple(supabaseClient);
    if (native && normalized === 'google') return signInWithNativeGoogle(supabaseClient);
    if (native) await setupNativeAuthListener();
    const result = await supabaseClient.auth.signInWithOAuth({
      provider: normalized,
      options: {
        redirectTo: redirectTo('index.html'),
        scopes: normalized === 'google' ? 'openid email profile' : undefined,
        queryParams: normalized === 'google' ? { prompt: 'select_account' } : undefined,
        skipBrowserRedirect: native,
      },
    });
    if (!result.error && native) {
      const browser = nativePlugin('Browser');
      const authUrl = result && result.data ? result.data.url : '';
      if (!browser || typeof browser.open !== 'function' || !authUrl) {
        return { ok: false, error: { code: 'native_oauth_unavailable' } };
      }
      try {
        await browser.open({ url: authUrl, presentationStyle: 'fullscreen' });
      } catch (e) {
        return { ok: false, error: { code: 'native_oauth_open_failed' } };
      }
    }
    return { ok: !result.error, result, error: result.error || null };
  }

  async function signInWithNativeGoogle(supabaseClient) {
    const google = nativePlugin('GoogleSignIn');
    if (!google || typeof google.signIn !== 'function') {
      return { ok: false, error: { code: 'native_google_unavailable' } };
    }
    if (!supabaseClient.auth || typeof supabaseClient.auth.signInWithIdToken !== 'function') {
      return { ok: false, error: { code: 'google_id_token_unsupported' } };
    }
    try {
      const credential = await google.signIn();
      if (!credential || credential.state === 'cancelled') {
        return { ok: false, cancelled: true, error: { code: 'google_sign_in_cancelled' } };
      }
      if (!credential.identityToken) {
        return { ok: false, error: { code: 'google_identity_token_missing' } };
      }
      const result = await supabaseClient.auth.signInWithIdToken({
        provider: 'google',
        token: credential.identityToken,
      });
      const nextSession = result && result.data ? result.data.session : null;
      if (result.error || !nextSession) {
        return { ok: false, result, error: result.error || { code: 'google_session_missing' } };
      }

      const metadata = {};
      const fullName = String(credential.fullName || [credential.givenName, credential.familyName].filter(Boolean).join(' ')).trim();
      if (fullName) metadata.full_name = fullName;
      if (credential.givenName) metadata.given_name = credential.givenName;
      if (credential.familyName) metadata.family_name = credential.familyName;
      if (credential.avatarUrl) metadata.avatar_url = credential.avatarUrl;
      if (Object.keys(metadata).length && typeof supabaseClient.auth.updateUser === 'function') {
        try { await supabaseClient.auth.updateUser({ data: metadata }); } catch (e) {}
      }
      setState('signed-in', nextSession, 'SIGNED_IN');
      return { ok: true, result, session: nextSession };
    } catch (e) {
      return {
        ok: false,
        error: {
          code: e && e.code ? e.code : 'native_google_sign_in_failed',
          message: e && e.message ? e.message : 'Google sign in failed',
        },
      };
    }
  }

  async function signInWithNativeApple(supabaseClient) {
    const apple = nativePlugin('AppleSignIn');
    if (!apple || typeof apple.signIn !== 'function') {
      return { ok: false, error: { code: 'native_apple_unavailable' } };
    }
    if (!supabaseClient.auth || typeof supabaseClient.auth.signInWithIdToken !== 'function') {
      return { ok: false, error: { code: 'apple_id_token_unsupported' } };
    }
    try {
      const credential = await apple.signIn();
      if (!credential || credential.state === 'cancelled') {
        return { ok: false, cancelled: true, error: { code: 'apple_sign_in_cancelled' } };
      }
      if (!credential.identityToken || !credential.nonce) {
        return { ok: false, error: { code: 'apple_identity_token_missing' } };
      }
      const result = await supabaseClient.auth.signInWithIdToken({
        provider: 'apple',
        token: credential.identityToken,
        nonce: credential.nonce,
      });
      const nextSession = result && result.data ? result.data.session : null;
      if (result.error || !nextSession) {
        return { ok: false, result, error: result.error || { code: 'apple_session_missing' } };
      }

      const fullName = String(credential.fullName || [credential.givenName, credential.familyName].filter(Boolean).join(' ')).trim();
      if (fullName && typeof supabaseClient.auth.updateUser === 'function') {
        try {
          await supabaseClient.auth.updateUser({
            data: {
              full_name: fullName,
              given_name: credential.givenName || '',
              family_name: credential.familyName || '',
            },
          });
        } catch (e) {}
      }
      setState('signed-in', nextSession, 'SIGNED_IN');
      return { ok: true, result, session: nextSession };
    } catch (e) {
      return {
        ok: false,
        error: {
          code: e && e.code ? e.code : 'native_apple_sign_in_failed',
          message: e && e.message ? e.message : 'Apple sign in failed',
        },
      };
    }
  }

  async function signInAsDeveloper(overrides = {}) {
    if (!isDeveloperModeAllowed()) {
      return { ok: false, error: { code: 'developer_mode_not_allowed' } };
    }
    const devSession = makeDeveloperSession(overrides);
    setState('signed-in', devSession, 'DEV_SIGNED_IN');
    return { ok: true, session: devSession, state: publicState() };
  }

  async function signOut() {
    const signedInProvider = publicState().provider;
    if (window.MuneaNotify && typeof window.MuneaNotify.unregisterBeforeSignOut === 'function') {
      try { await window.MuneaNotify.unregisterBeforeSignOut(); } catch (e) {}
    }
    if (session && session.developer) {
      setState('guest', null, 'SIGNED_OUT');
      return { ok: true };
    }
    const supabaseClient = await ensureClient();
    if (!supabaseClient) {
      setState('guest', null, 'SIGNED_OUT');
      return { ok: true };
    }
    const result = await supabaseClient.auth.signOut({ scope: 'local' });
    if (!result.error) {
      if (isNativeApp() && signedInProvider === 'google') {
        const google = nativePlugin('GoogleSignIn');
        if (google && typeof google.signOut === 'function') {
          try { await google.signOut(); } catch (e) {}
        }
      }
      setState('guest', null, 'SIGNED_OUT');
    }
    return { ok: !result.error, result, error: result.error || null };
  }

  function isCredentialRejection(error) {
    if (!error) return false;
    const statusCode = Number(error.status || error.statusCode || 0);
    const code = String(error.code || error.error_code || '').toLowerCase();
    const message = String(error.message || '').toLowerCase();
    return statusCode === 401 || statusCode === 403 ||
      ['bad_jwt', 'invalid_jwt', 'refresh_token_not_found', 'refresh_token_already_used'].includes(code) ||
      /invalid jwt|jwt expired|token.*expired|invalid refresh token/.test(message);
  }

  async function validateOrRefreshSession(supabaseClient, currentSession) {
    if (!currentSession || !currentSession.access_token) return null;
    const token = String(currentSession.access_token);
    if (verifiedAccessToken === token) return currentSession;
    if (!supabaseClient.auth || typeof supabaseClient.auth.getUser !== 'function') return currentSession;
    if (tokenValidation && tokenValidation.token === token) return tokenValidation.promise;

    const promise = (async () => {
      let validation = null;
      try { validation = await supabaseClient.auth.getUser(token); }
      catch (error) {
        // A network outage must not erase an otherwise refreshable local
        // session. Gateway availability is reported separately.
        if (!isCredentialRejection(error)) return currentSession;
        validation = { error };
      }
      if (validation && !validation.error && validation.data && validation.data.user) {
        verifiedAccessToken = token;
        return currentSession;
      }
      if (validation && validation.error && !isCredentialRejection(validation.error)) return currentSession;
      if (typeof supabaseClient.auth.refreshSession !== 'function') return null;

      let refreshed = null;
      try { refreshed = await supabaseClient.auth.refreshSession(); }
      catch (error) {
        if (!isCredentialRejection(error)) return currentSession;
        return null;
      }
      const nextSession = refreshed && refreshed.data ? refreshed.data.session : null;
      if (!nextSession || refreshed.error || !nextSession.access_token) return null;

      const refreshedToken = String(nextSession.access_token);
      try {
        const recheck = await supabaseClient.auth.getUser(refreshedToken);
        if (recheck && !recheck.error && recheck.data && recheck.data.user) {
          verifiedAccessToken = refreshedToken;
          return nextSession;
        }
        if (recheck && recheck.error && !isCredentialRejection(recheck.error)) return nextSession;
      } catch (error) {
        if (!isCredentialRejection(error)) return nextSession;
      }
      return null;
    })();
    tokenValidation = { token, promise };
    try { return await promise; }
    finally {
      if (tokenValidation && tokenValidation.promise === promise) tokenValidation = null;
    }
  }

  async function getAccessToken() {
    if (session && session.developer) return session.access_token || null;
    const supabaseClient = await ensureClient();
    if (!supabaseClient) return null;
    try {
      const result = await supabaseClient.auth.getSession();
      const loadedSession = result && result.data ? result.data.session : null;
      const currentSession = await validateOrRefreshSession(supabaseClient, loadedSession);
      setState(currentSession ? 'signed-in' : 'guest', currentSession,
        currentSession ? 'SESSION_REFRESHED' : 'SESSION_REJECTED');
      return currentSession && currentSession.access_token ? currentSession.access_token : null;
    } catch (e) {
      setState('guest', null, 'SESSION_UNAVAILABLE');
      return null;
    }
  }

  window.MuneaAuth = {
    AUTH_STATE_EVENT,
    providers: Object.freeze({ APPLE: 'apple', GOOGLE: 'google' }),
    init,
    state: publicState,
    isConfigured,
    signInWithProvider,
    signInWithApple: () => signInWithProvider('apple'),
    signInWithGoogle: () => signInWithProvider('google'),
    signInAsDeveloper,
    signOut,
    getAccessToken,
  };

  init();
})();
