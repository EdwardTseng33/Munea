(function () {
  const AUTH_STATE_EVENT = 'munea:auth-state';
  const ALLOWED_OAUTH_PROVIDERS = new Set(['apple', 'google']);
  let client = null;
  let initPromise = null;
  let session = null;
  let status = 'guest';
  let lastEvent = 'INITIAL';

  function config() {
    return window.MUNEA_SUPABASE_CONFIG || {};
  }

  function publishableKey(cfg) {
    return cfg.publishableKey || cfg.anonKey || cfg.key || '';
  }

  function redirectTo(path) {
    const cfg = config();
    if (cfg.redirectTo) return cfg.redirectTo;
    try {
      return new URL(path || 'index.html', window.location.href).toString();
    } catch (e) {
      return window.location.href;
    }
  }

  function setState(nextStatus, nextSession, eventName) {
    status = nextStatus;
    session = nextSession || null;
    lastEvent = eventName || lastEvent;
    window.dispatchEvent(new CustomEvent(AUTH_STATE_EVENT, { detail: publicState() }));
  }

  function publicState() {
    const user = session && session.user ? session.user : null;
    return {
      configured: isConfigured(),
      status,
      event: lastEvent,
      user,
      userId: user ? user.id : null,
      email: user ? user.email || null : null,
      provider: user && user.app_metadata ? user.app_metadata.provider || null : null,
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
  }

  async function init() {
    if (initPromise) return initPromise;
    initPromise = (async () => {
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
    const result = await supabaseClient.auth.signInWithOAuth({
      provider: normalized,
      options: {
        redirectTo: redirectTo('index.html'),
        scopes: normalized === 'google' ? 'openid email profile' : undefined,
      },
    });
    return { ok: !result.error, result, error: result.error || null };
  }

  async function signInWithEmail(email) {
    const cleanEmail = String(email || '').trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      return { ok: false, error: { code: 'invalid_email' } };
    }
    const supabaseClient = await ensureClient();
    if (!supabaseClient) return { ok: false, error: { code: 'auth_not_configured' } };
    const result = await supabaseClient.auth.signInWithOtp({
      email: cleanEmail,
      options: {
        emailRedirectTo: redirectTo('index.html'),
      },
    });
    return { ok: !result.error, result, error: result.error || null };
  }

  async function signOut() {
    const supabaseClient = await ensureClient();
    if (!supabaseClient) {
      setState('guest', null, 'SIGNED_OUT');
      return { ok: true };
    }
    const result = await supabaseClient.auth.signOut();
    if (!result.error) setState('guest', null, 'SIGNED_OUT');
    return { ok: !result.error, result, error: result.error || null };
  }

  async function getAccessToken() {
    const supabaseClient = await ensureClient();
    if (!supabaseClient) return null;
    try {
      const result = await supabaseClient.auth.getSession();
      const currentSession = result && result.data ? result.data.session : null;
      if (currentSession !== session) {
        setState(currentSession ? 'signed-in' : 'guest', currentSession, 'SESSION_REFRESHED');
      }
      return currentSession && currentSession.access_token ? currentSession.access_token : null;
    } catch (e) {
      setState('guest', null, 'SESSION_UNAVAILABLE');
      return null;
    }
  }

  window.MuneaAuth = {
    AUTH_STATE_EVENT,
    providers: Object.freeze({ APPLE: 'apple', GOOGLE: 'google', EMAIL_OTP: 'email_otp' }),
    init,
    state: publicState,
    isConfigured,
    signInWithProvider,
    signInWithApple: () => signInWithProvider('apple'),
    signInWithGoogle: () => signInWithProvider('google'),
    signInWithEmail,
    signOut,
    getAccessToken,
  };

  init();
})();
