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
const positional = args.filter(a => !a.startsWith('--'));
const target = path.resolve(positional[0] || 'ios/App/App/public/src/auth-config.js');
const productionConfig = path.resolve('web/src/auth-config.js');

if (target === productionConfig) {
  throw new Error('Refusing to enable the development profile in the production Web source.');
}
if (!fs.existsSync(target)) {
  throw new Error(`Missing generated iOS auth config: ${target}. Run Capacitor sync first.`);
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
${endMarker}`;

fs.writeFileSync(target, `${source}\n\n${profile}\n`, 'utf8');
console.log(gatewayMode
  ? `Development GATEWAY profile enabled (real login + Call Control lease) in: ${target}`
  : `Development profile enabled only in generated iOS assets: ${target}`);
