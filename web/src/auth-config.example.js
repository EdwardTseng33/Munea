// Copy this shape into a private/dev-only config injection when testing Supabase Auth.
// Only use the Supabase publishable/anon key in browser code. Never put server-only keys here.
window.MUNEA_SUPABASE_CONFIG = {
  url: 'https://YOUR_PROJECT_REF.supabase.co',
  publishableKey: 'YOUR_SUPABASE_PUBLISHABLE_OR_ANON_KEY',
  // Pin an exact @supabase/supabase-js v2 ESM URL or preload window.supabase before auth.js.
  sdkUrl: 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm',
  redirectTo: new URL('index.html', window.location.href).toString(),
  nativeRedirectTo: 'munea://auth/callback',
};

// Optional local-only developer mode. Keep disabled in production builds.
window.MUNEA_DEV_CONFIG = {
  enabled: false,
  autoSignIn: false,
  skipOnboarding: false,
  seedFixtures: false,
  analyticsExcluded: true,
  authUserId: '00000000-0000-4000-8000-000000000001',
  email: 'developer@munea.local',
  displayName: 'Munea Developer',
};
