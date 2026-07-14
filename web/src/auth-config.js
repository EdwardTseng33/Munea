// Public Supabase browser configuration. Never place a server-only key here.
window.MUNEA_SUPABASE_CONFIG = {
  url: 'https://uhmpmystjjdqqxlpsthc.supabase.co',
  publishableKey: 'sb_publishable_Ou8sb6J8yFHMgC1Mcz2eyw_sT2CprIZ',
  sdkUrl: 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm',
  redirectTo: new URL('index.html', window.location.href).toString(),
  nativeRedirectTo: 'munea://auth/callback',
};

window.MUNEA_DEV_CONFIG = {
  enabled: false,
  autoSignIn: false,
  skipOnboarding: false,
  seedFixtures: false,
  analyticsExcluded: true,
};
