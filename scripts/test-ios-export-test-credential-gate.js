// 2026-07-18 專用真測試帳號施工：驗證出貨門「正式 IPA 含測試憑證就 exit 1」真的有牙——
// 直接從 scripts/ios-export-app-store.sh 原始碼切出這道新門（不是重寫一份影子邏輯），
// 拿一份假造的、含測試帳密欄位的 auth-config.js 去跑，斷言它真的 FAIL + exit 1；
// 再拿一份乾淨的正式 auth-config.js 去跑，斷言這道門不誤殺。
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const scriptSource = fs.readFileSync('scripts/ios-export-app-store.sh', 'utf8');
const gateStart = scriptSource.indexOf('TEST_ACCOUNT_CREDENTIAL_PATTERN=');
assert.ok(gateStart >= 0, 'could not locate the test-account credential gate in ios-export-app-store.sh');
const gateEnd = scriptSource.indexOf('\nfi\n', gateStart);
assert.ok(gateEnd > gateStart, 'could not find the closing fi for the test-account credential gate');
const gateBlock = scriptSource.slice(gateStart, gateEnd + '\nfi'.length);
assert.match(gateBlock, /exit 1/, 'the isolated gate block does not exit 1 on a match');

function runGate(authConfigContents) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'munea-export-gate-'));
  const authConfigPath = path.join(tempDir, 'auth-config.js');
  fs.writeFileSync(authConfigPath, authConfigContents, 'utf8');
  const wrapper = `set -euo pipefail\nAUTH_CONFIG_PATH="$1"\n${gateBlock}\necho GATE_DID_NOT_TRIGGER\n`;
  const result = spawnSync('bash', ['-c', wrapper, 'bash', authConfigPath], { encoding: 'utf8' });
  fs.rmSync(tempDir, { recursive: true, force: true });
  return result;
}

const poisoned = runGate([
  "window.MUNEA_SUPABASE_CONFIG = { url: 'https://fespbkdwafueyonppzwq.supabase.co', publishableKey: 'sb_publishable_x' };",
  "window.MUNEA_DEV_CONFIG = {",
  "  enabled: false,",
  "  testAccountEmail: 'dev@munea.net',",
  "  testAccountPassword: 'super-secret-leaked-password',",
  "};",
  "",
].join('\n'));
assert.strictEqual(poisoned.status, 1, `poisoned auth-config.js did not exit 1 (got ${poisoned.status}); stdout: ${poisoned.stdout} stderr: ${poisoned.stderr}`);
assert.match(poisoned.stdout, /FAIL exported IPA auth configuration contains test account credentials/,
  'poisoned auth-config.js did not print the expected FAIL message');
assert.doesNotMatch(poisoned.stdout, /GATE_DID_NOT_TRIGGER/, 'poisoned auth-config.js incorrectly fell through the gate');

const clean = runGate([
  "window.MUNEA_SUPABASE_CONFIG = { url: 'https://fespbkdwafueyonppzwq.supabase.co', publishableKey: 'sb_publishable_x' };",
  "window.MUNEA_DEV_CONFIG = {",
  "  enabled: false,",
  "  autoSignIn: false,",
  "  seedFixtures: false,",
  "  bypassCallControl: false,",
  "  analyticsExcluded: true,",
  "};",
  "",
].join('\n'));
assert.strictEqual(clean.status, 0, `clean production auth-config.js unexpectedly failed the gate (got ${clean.status}); stdout: ${clean.stdout} stderr: ${clean.stderr}`);
assert.match(clean.stdout, /GATE_DID_NOT_TRIGGER/, 'clean production auth-config.js did not fall through the gate as expected');

// 順帶確認：真正的正式來源檔（web/src/auth-config.js）本身也乾淨過關（不是只測我手造的樣本）。
const productionConfig = runGate(fs.readFileSync('web/src/auth-config.js', 'utf8'));
assert.strictEqual(productionConfig.status, 0,
  `the real production web/src/auth-config.js unexpectedly failed the test-account credential gate; stdout: ${productionConfig.stdout}`);

console.log('ios-export-app-store.sh test-account credential gate PASS: blocks poisoned config (exit 1), passes clean production config');
