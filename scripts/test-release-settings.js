const fs = require('fs');

function read(path) {
  return fs.readFileSync(path, 'utf8').replace(/\r\n/g, '\n');
}

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function hasUsageDescription(plist, key) {
  return new RegExp(`<key>${key}</key>\\s*<string>[^<]{8,}</string>`).test(plist);
}

const app = read('web/src/app.js');
const admin = read('web/src/admin.js');
const index = read('web/index.html');
const landing = read('web/landing.html');
const store = read('web/src/store.js');
const appleStore = read('engine/apple_store.py');
const billingPolicy = read('supabase/sql/013_current_app_billing_policy.sql');
const authConfig = read('web/src/auth-config.js');
const swiftStore = read('ios/App/App/StorePlugin.swift');
const swiftAppleSignIn = read('ios/App/App/AppleSignInPlugin.swift');
const appEntitlements = read('ios/App/App/App.entitlements');
const viewController = read('ios/App/App/MuneaViewController.swift');
const xcodeProject = read('ios/App/App.xcodeproj/project.pbxproj');
const iosExport = read('scripts/ios-export-app-store.sh');
const iosDevProfile = read('scripts/enable-ios-development-profile.mjs');
const auth = read('web/src/auth.js');
const infoPlist = read('ios/App/App/Info.plist');
const privacyManifest = read('ios/App/App/PrivacyInfo.xcprivacy');
const reviewNotes = read('docs/送審資料包-2026-07-09.md');
const canaryDeploy = read('deploy/cloudrun/canary-deploy.sh');

expect(!app.includes('__muneaNativeRestore'), 'restore button still calls the retired native global');
expect(app.includes('window.MuneaStore.restore()'), 'restore button is not wired to MuneaStore.restore');
expect(app.includes('window.MuneaStore.manageSubscriptions()'), 'cancel button is not wired to Apple subscription management');
expect(app.includes("brainPost('/privacy-export', { action: 'request' })"), 'data export does not create a request');
expect(app.includes('result.exportPackage') && app.includes("navigator.share") && app.includes("a.download = filename"), 'data export does not deliver the generated JSON file');
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
expect(/enabled:\s*false/.test(authConfig) && /seedFixtures:\s*false/.test(authConfig), 'production auth config must keep developer fixtures disabled');
expect(/bypassCallControl:\s*false/.test(authConfig), 'production auth config must require Call Control');
expect(!authConfig.includes('MUNEA_IOS_DEVELOPMENT_PROFILE_START'), 'development profile leaked into production Web source');
expect(iosDevProfile.includes('ios/App/App/public/src/auth-config.js'), 'iOS development profile must target generated assets only');
expect(iosDevProfile.includes('Refusing to enable the development profile in the production Web source'), 'development profile lacks production source guard');
expect(iosDevProfile.includes('bypassCallControl: true'), 'iOS development profile does not enable its isolated direct-call path');
expect(!index.includes('id="authEmailInput"') && !index.includes('id="authEmailBtn"'), 'consumer app still exposes email sign-in controls');
expect(!auth.includes('signInWithOtp') && !auth.includes('signInWithEmail'), 'email OTP auth remains exposed in the consumer auth module');
const openAuthSheet = app.match(/function openAuthSheet\(\) \{[\s\S]*?\n\}/)?.[0] || '';
expect(openAuthSheet && !/\.focus\s*\(/.test(openAuthSheet), 'auth sheet still opens the keyboard automatically');

expect(swiftStore.includes('CAPPluginMethod(name: "manageSubscriptions"'), 'native subscription management method is not registered');
expect(swiftStore.includes('AppStore.showManageSubscriptions'), 'native subscription management sheet is not implemented');
expect(!reviewNotes.includes('Guest accounts include'), 'review notes still claim a guest trial');
expect(reviewNotes.includes('Voice chat and\n   private account data require sign-in'), 'review notes do not explain the sign-in gate');
expect(auth.includes("skipBrowserRedirect: native"), 'native OAuth still uses the embedded WebView');
expect(auth.includes("app.addListener('appUrlOpen'"), 'native OAuth callback listener is missing');
expect(auth.includes('exchangeCodeForSession'), 'native OAuth PKCE code exchange is missing');
expect(auth.includes("nativePlugin('AppleSignIn')"), 'native Apple plugin bridge is missing');
expect(auth.includes('signInWithIdToken'), 'native Apple ID token is not exchanged with Supabase');
expect(infoPlist.includes('<string>munea</string>'), 'iOS OAuth callback URL scheme is missing');
expect(hasUsageDescription(infoPlist, 'NSCameraUsageDescription'), 'iOS camera usage description is missing');
expect(hasUsageDescription(infoPlist, 'NSPhotoLibraryUsageDescription'), 'iOS photo library usage description is missing');
expect(swiftAppleSignIn.includes('ASAuthorizationAppleIDProvider'), 'native Sign in with Apple request is missing');
expect(swiftAppleSignIn.includes('request.nonce = self.sha256(nonce)'), 'native Apple nonce binding is missing');
expect(appEntitlements.includes('com.apple.developer.applesignin'), 'Sign in with Apple entitlement is missing');
expect(viewController.includes('registerPluginInstance(AppleSignInPlugin())'), 'native Apple plugin is not registered');
expect(xcodeProject.includes('AppleSignInPlugin.swift in Sources'), 'native Apple plugin is not compiled by Xcode');
expect(iosExport.includes('codesign -d --entitlements - "$APP_PATH"'), 'IPA export still uses the retired entitlements output syntax');
expect(!iosExport.includes('codesign -d --entitlements :-'), 'IPA export uses deprecated codesign entitlement syntax');
expect(iosExport.includes('com.apple.developer.applesignin'), 'IPA export does not verify Apple sign-in entitlement');
expect(iosExport.includes('NSCameraUsageDescription') && iosExport.includes('NSPhotoLibraryUsageDescription'), 'IPA export does not verify photo privacy usage strings');
expect(xcodeProject.includes('PrivacyInfo.xcprivacy in Resources'), 'PrivacyInfo.xcprivacy is not bundled by the Xcode target');
expect(privacyManifest.includes('<key>NSPrivacyTracking</key>') && privacyManifest.includes('<false/>'), 'privacy manifest must declare no tracking');
expect(privacyManifest.includes('NSPrivacyCollectedDataTypeHealth') && privacyManifest.includes('NSPrivacyCollectedDataTypeAudioData'), 'privacy manifest is missing health or audio collection declarations');
expect(iosExport.includes('PrivacyInfo.xcprivacy'), 'IPA export does not verify the privacy manifest');
expect(iosExport.includes('PRIVACY_DATA_TYPE_COUNT=') && iosExport.includes('NSPrivacyCollectedDataTypes raw'),
  'IPA export does not validate the structured privacy data-type count');
expect(iosExport.includes('development account or fixtures leaked into the App Store IPA'), 'IPA export does not reject development fixtures');
expect(iosExport.includes('bypassCallControl'), 'IPA export does not reject the development Call Control bypass');
expect(iosExport.includes('exported IPA does not contain the latest Web design assets'), 'IPA export does not verify current Web design assets');
expect(canaryDeploy.includes('command -v gcloud') && canaryDeploy.includes('GCLOUD=(gcloud)'), 'canary deploy is not compatible with macOS gcloud');
expect(canaryDeploy.includes('GCLOUD=(cmd //c gcloud.cmd)'), 'canary deploy lost Windows gcloud compatibility');
expect(canaryDeploy.includes('MUNEA_GCP_PROJECT') && canaryDeploy.includes('--project "$PROJECT"'), 'canary deploy does not pin the Google Cloud project');
expect(canaryDeploy.includes('MUNEA_APP_KEY') && canaryDeploy.includes('--no-traffic'), 'canary deploy is missing its app gate or zero-traffic safety gate');

console.log('Release settings contracts PASS');
