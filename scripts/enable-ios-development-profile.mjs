#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';

const startMarker = '// MUNEA_IOS_DEVELOPMENT_PROFILE_START';
const endMarker = '// MUNEA_IOS_DEVELOPMENT_PROFILE_END';
const target = path.resolve(process.argv[2] || 'ios/App/App/public/src/auth-config.js');
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
const profile = `${startMarker}
window.MUNEA_DEV_CONFIG = {
  enabled: true,
  allowNonLocalhost: true,
  autoSignIn: true,
  skipOnboarding: true,
  seedFixtures: true,
  analyticsExcluded: true,
  authUserId: '00000000-0000-4000-8000-000000000104',
  email: 'edward.dev@munea.local',
  displayName: 'Edward 測試帳號',
  profileName: 'Edward',
  plan: 'pro',
  purchasedPoints: 700,
  fixtureVersion: '1.0.4-build9-family-v2',
};
${endMarker}`;

fs.writeFileSync(target, `${source}\n\n${profile}\n`, 'utf8');
console.log(`Development profile enabled only in generated iOS assets: ${target}`);
