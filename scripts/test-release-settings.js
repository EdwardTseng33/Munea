const fs = require('fs');

function read(path) {
  return fs.readFileSync(path, 'utf8');
}

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const app = read('web/src/app.js');
const admin = read('web/src/admin.js');
const index = read('web/index.html');
const landing = read('web/landing.html');
const store = read('web/src/store.js');
const appleStore = read('engine/apple_store.py');
const billingPolicy = read('supabase/sql/012_current_app_billing_policy.sql');
const authConfig = read('web/src/auth-config.js');
const swiftStore = read('ios/App/App/StorePlugin.swift');
const auth = read('web/src/auth.js');
const infoPlist = read('ios/App/App/Info.plist');
const reviewNotes = read('docs/送審資料包-2026-07-09.md');

expect(!app.includes('__muneaNativeRestore'), 'restore button still calls the retired native global');
expect(app.includes('window.MuneaStore.restore()'), 'restore button is not wired to MuneaStore.restore');
expect(app.includes('window.MuneaStore.manageSubscriptions()'), 'cancel button is not wired to Apple subscription management');
expect(app.includes("brainPost('/privacy-export', { action: 'request' })"), 'data export does not create a request');
expect(app.includes('deletion && deletion.ok && deletion.accountDeleted'), 'local data can be cleared before cloud deletion succeeds');
expect(app.includes('const POINTS = { total: 0, used: 0'), 'point wallet still starts with a stale paid-plan allowance');
expect(app.includes('plus: 150, pro: 300'), 'current subscription grants are missing from the app');
expect(app.includes('free: 1, plus: 4, pro: 12'), 'current family limits are missing from the app');
expect(index.includes('NT$1,199') && index.includes('NT$599'), 'current subscription prices are missing from the app');
expect(index.includes('data-p="150"') && index.includes('data-p="300"') && index.includes('data-p="600"') && index.includes('data-p="1000"'), 'current point packs are missing from the app');
expect(admin.includes('每月贈 150 點') && admin.includes('每月贈 300 點'), 'admin still shows retired subscription grants');
expect(!admin.includes('每月贈 200 點') && !admin.includes('每月贈 400 點'), 'admin contains retired subscription grants');
expect(landing.includes('Legacy internal prototype') && landing.includes('每月贈 150 點聊聊') && landing.includes('每月贈 300 點聊聊'), 'legacy landing artifact is not clearly marked or still shows retired grants');

const expectedPointProducts = {
  150: 'net.munea.app.points.200',
  300: 'net.munea.app.points.500',
  600: 'net.munea.app.points.1000',
  1000: 'net.munea.app.points.1800',
};
for (const [points, productId] of Object.entries(expectedPointProducts)) {
  expect(store.includes(`${points}: '${productId}'`), `StoreKit mapping is wrong for ${points} points`);
}
expect(appleStore.includes('"net.munea.app.points.200": {"kind": "points", "points": 150}'), 'backend grant is wrong for the 150-point product');
expect(appleStore.includes('"net.munea.app.points.500": {"kind": "points", "points": 300}'), 'backend grant is wrong for the 300-point product');
expect(appleStore.includes('"net.munea.app.points.1000": {"kind": "points", "points": 600}'), 'backend grant is wrong for the 600-point product');
expect(appleStore.includes('"net.munea.app.points.1800": {"kind": "points", "points": 1000}'), 'backend grant is wrong for the 1000-point product');
expect(billingPolicy.includes("array['free', 'plus', 'pro']"), 'Supabase plan order is not aligned to the current app');
expect(billingPolicy.includes('"monthlyPoints": 150') && billingPolicy.includes('"monthlyPoints": 300'), 'Supabase monthly grants are not aligned to the current app');

expect(authConfig.includes('window.MUNEA_SUPABASE_CONFIG'), 'public Supabase auth config is missing');
expect(/https:\/\/[a-z0-9-]+\.supabase\.co/.test(authConfig), 'Supabase project URL is missing');
expect(authConfig.includes('sb_publishable_'), 'Supabase publishable key is missing');
expect(!/service[_-]?role|SUPABASE_SERVICE_ROLE_KEY/i.test(authConfig), 'server-only Supabase key leaked into browser config');

expect(swiftStore.includes('CAPPluginMethod(name: "manageSubscriptions"'), 'native subscription management method is not registered');
expect(swiftStore.includes('AppStore.showManageSubscriptions'), 'native subscription management sheet is not implemented');
expect(!reviewNotes.includes('Guest accounts include'), 'review notes still claim a guest trial');
expect(reviewNotes.includes('Voice chat and\n   private account data require sign-in'), 'review notes do not explain the sign-in gate');
expect(auth.includes("skipBrowserRedirect: native"), 'native OAuth still uses the embedded WebView');
expect(auth.includes("app.addListener('appUrlOpen'"), 'native OAuth callback listener is missing');
expect(auth.includes('exchangeCodeForSession'), 'native OAuth PKCE code exchange is missing');
expect(infoPlist.includes('<string>munea</string>'), 'iOS OAuth callback URL scheme is missing');

console.log('Release settings contracts PASS');
