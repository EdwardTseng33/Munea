// Public Supabase browser configuration. Never place a server-only key here.
window.MUNEA_SUPABASE_CONFIG = {
  url: 'https://fespbkdwafueyonppzwq.supabase.co',
  publishableKey: 'sb_publishable_fP-PoA531waoIOmxl8tsWg_kCeZQD0e',
  sdkUrl: 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm',
  redirectTo: new URL('index.html', window.location.href).toString(),
  nativeRedirectTo: 'munea://auth/callback',
  environment: 'production-tokyo',
};

window.MUNEA_DEV_CONFIG = {
  enabled: false,
  autoSignIn: false,
  skipOnboarding: false,
  seedFixtures: false,
  bypassCallControl: false,
  analyticsExcluded: true,
};
