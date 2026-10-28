#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';

const startMarker = '// MUNEA_IOS_DEVELOPMENT_PROFILE_START';
const endMarker = '// MUNEA_IOS_DEVELOPMENT_PROFILE_END';
const args = process.argv.slice(2);
// --gateway＝「走總機領證」測試包（2026-07-16 · 聊聊門禁事故後補）：
// 不直連語音橋、不自動登入測試帳號、不種假資料——用真帳號走正式領證流程，
// 專門用來驗「通話許可證」新門禁的端到端。預設（不帶 flag）＝原本的直連測試包、行為不變。
const gatewayMode = args.includes('--gateway');
// 2026-07-18 專用真測試帳號施工：帳密只從 build-time env 注入，絕不寫死在原始碼裡；
// 沒設定時留空字串（signInWithTestAccount 會回 test_account_credentials_missing、不會硬撞總機）。
const testAccountEmail = process.env.MUNEA_TEST_ACCOUNT_EMAIL || '';
const testAccountPassword = process.env.MUNEA_TEST_ACCOUNT_PASSWORD || '';
const positional = args.filter(a => !a.startsWith('--'));
// 預設路徑是 iOS 的；2026-10-28 B1 查核點起，Android 流程測試也借同一支腳本，
// 呼叫時帶 android/app/src/main/assets/public/src/auth-config.js 當第一個位置參數即可——
// 純改這份生成出來的設定檔，不動 web/ 的 App 邏輯一行。
const target = path.resolve(positional[0] || 'ios/App/App/public/src/auth-config.js');
const productionConfig = path.resolve('web/src/auth-config.js');

if (target === productionConfig) {
  throw new Error('Refusing to enable the development profile in the production Web source.');
}
if (!fs.existsSync(target)) {
  throw new Error(`Missing generated native auth config: ${target}. Run Capacitor sync first.`);
}

const escapeRegExp = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const existingBlock = new RegExp(`${escapeRegExp(startMarker)}[\\s\\S]*?${escapeRegExp(endMarker)}\\s*`, 'g');
const source = fs.readFileSync(target, 'utf8').replace(existingBlock, '').trimEnd();
const profile = gatewayMode ? `${startMarker}
window.MUNEA_DEV_CONFIG = {
  enabled: true,
  allowNonLocalhost: true,
  autoSignIn: false,
  skipOnboarding: false,
  seedFixtures: false,
  bypassCallControl: false,
  analyticsExcluded: true,
  fixtureVersion: '1.0.37-build44-tokyo-gateway-v1',
  testAccountEmail: ${JSON.stringify(testAccountEmail)},
  testAccountPassword: ${JSON.stringify(testAccountPassword)},
  voiceUrl: 'wss://munea-voice-staging-491603544409.asia-east1.run.app',
  brainUrl: 'https://munea-brain-staging-491603544409.asia-east1.run.app',
};
${endMarker}` : `${startMarker}
window.MUNEA_DEV_CONFIG = {
  enabled: true,
  allowNonLocalhost: true,
  autoSignIn: true,
  skipOnboarding: true,
  seedFixtures: true,
  bypassCallControl: true,
  analyticsExcluded: true,
  authUserId: '00000000-0000-4000-8000-000000000104',
  email: 'edward.dev@munea.local',
  displayName: 'Edward 測試帳號',
  profileName: 'Edward',
  plan: 'pro',
  purchasedPoints: 700,
  fixtureVersion: '1.0.37-build44-tokyo-v1',
  voiceUrl: 'wss://munea-voice-staging-491603544409.asia-east1.run.app',
  brainUrl: 'https://munea-brain-staging-491603544409.asia-east1.run.app',
};
// 2026-10-28 B1 查核點：skipOnboarding 只蓋到舊版迎賓精靈用的
// ONBOARDING_COMPLETED_KEY，蓋不到 2026 年後新增的「開場三頁故事卡」
// （web/src/app.js 的 openOnboardingIntro()/runBootSplash()，用另一個 key
// munea.onboardingIntroSeen.v1，App 裡自己註解寫「刻意不重用」）。故事卡
// 啟動後 2.4 秒自動彈出、不看任何開發設定，而且「下一步」按鈕螢幕座標
// 剛好蓋住底部導覽「聊聊」分頁——擋到 UI 自動化測試、也會擋到任何第一次
// 用這支測試包登入的人。這裡只是在生成出來的測試設定檔多塞一行
// localStorage.setItem，不動 web/ 的 App 邏輯一行；故事卡兩套 key 沒對齊
// 本身是個真的產品缺口，建議之後在 App 端統一（不在這支腳本處理）。
try { localStorage.setItem('munea.onboardingIntroSeen.v1', 'true'); } catch (e) {}
${endMarker}`;

fs.writeFileSync(target, `${source}\n\n${profile}\n`, 'utf8');
console.log(gatewayMode
  ? `Development GATEWAY profile enabled (real login + Call Control lease) in: ${target}`
  : `Development profile enabled only in generated native assets (iOS/Android build copy): ${target}`);
