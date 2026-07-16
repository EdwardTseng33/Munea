const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const vm = require('vm');

const sourceConfigPath = path.resolve('web/src/auth-config.js');
const sourceConfigBefore = fs.readFileSync(sourceConfigPath, 'utf8');
const sourceHashBefore = crypto.createHash('sha256').update(sourceConfigBefore).digest('hex');

assert.match(sourceConfigBefore, /enabled:\s*false/, 'Production auth config must keep developer mode disabled');
assert.match(sourceConfigBefore, /seedFixtures:\s*false/, 'Production auth config must keep fixtures disabled');
assert.match(sourceConfigBefore, /bypassCallControl:\s*false/, 'Production auth config must require Call Control');
assert.doesNotMatch(sourceConfigBefore, /MUNEA_IOS_DEVELOPMENT_PROFILE_START/, 'Development override leaked into production Web source');

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'munea-dev-profile-'));
const tempConfig = path.join(tempDir, 'auth-config.js');
fs.writeFileSync(tempConfig, 'window.MUNEA_DEV_CONFIG = { enabled: false, seedFixtures: false };\n', 'utf8');

const result = spawnSync(process.execPath, ['scripts/enable-ios-development-profile.mjs', tempConfig], {
  cwd: process.cwd(),
  encoding: 'utf8',
});
assert.strictEqual(result.status, 0, result.stderr || 'Development profile command failed');

const generated = fs.readFileSync(tempConfig, 'utf8');
const context = { window: {} };
vm.runInNewContext(generated, context);
const config = context.window.MUNEA_DEV_CONFIG;

assert.strictEqual(config.enabled, true);
assert.strictEqual(config.autoSignIn, true);
assert.strictEqual(config.skipOnboarding, true);
assert.strictEqual(config.seedFixtures, true);
assert.strictEqual(config.bypassCallControl, true);
assert.strictEqual(config.analyticsExcluded, true);
assert.strictEqual(config.fixtureVersion, '1.0.26-build33-tokyo-v1');
assert.strictEqual(config.displayName, 'Edward 測試帳號');
assert.strictEqual(config.plan, 'pro');
assert.strictEqual(config.purchasedPoints, 700);
assert.match(generated, /MUNEA_IOS_DEVELOPMENT_PROFILE_START/);

const sourceHashAfter = crypto.createHash('sha256').update(fs.readFileSync(sourceConfigPath, 'utf8')).digest('hex');
assert.strictEqual(sourceHashAfter, sourceHashBefore, 'Development profile command modified production Web source');

const app = fs.readFileSync('web/src/app.js', 'utf8');
for (const token of ['seedDeveloperFixtures', 'Edward', '媽媽', '爸爸', '姊姊', 'munea.famVitals', 'munea.familyFeed2']) {
  assert(app.includes(token), `Missing development fixture contract: ${token}`);
}
assert.match(app, /kind:\s*'walk'/);
assert.match(app, /names:\s*\['媽媽', '爸爸', '姊姊'\]/);
assert.doesNotMatch(app, /type:\s*'walk'/);
assert.match(app, /function usesDevelopmentDirectCall\(\)/);
assert.match(app, /if \(!developmentDirectCall\) await CallControl\.waitUntilActive\(15000\)/);

// --gateway 模式（2026-07-16 聊聊門禁事故後補）：真登入＋走總機領證，不直連、不自動登入、不種假資料
const gatewayConfigPath = path.join(tempDir, 'auth-config-gateway.js');
fs.writeFileSync(gatewayConfigPath, 'window.MUNEA_DEV_CONFIG = { enabled: false, seedFixtures: false };\n', 'utf8');
const gatewayResult = spawnSync(process.execPath, ['scripts/enable-ios-development-profile.mjs', gatewayConfigPath, '--gateway'], {
  cwd: process.cwd(),
  encoding: 'utf8',
});
assert.strictEqual(gatewayResult.status, 0, gatewayResult.stderr || 'Gateway development profile command failed');
const gatewayGenerated = fs.readFileSync(gatewayConfigPath, 'utf8');
const gatewayContext = { window: {} };
vm.runInNewContext(gatewayGenerated, gatewayContext);
const gatewayConfig = gatewayContext.window.MUNEA_DEV_CONFIG;
assert.strictEqual(gatewayConfig.enabled, true, 'Gateway profile keeps developer diagnostics on');
assert.strictEqual(gatewayConfig.bypassCallControl, false, 'Gateway profile must route calls through Call Control');
assert.strictEqual(gatewayConfig.autoSignIn, false, 'Gateway profile must not auto sign in the fixture account');
assert.strictEqual(gatewayConfig.seedFixtures, false, 'Gateway profile must not seed fixture data over a real account');
assert.strictEqual(gatewayConfig.analyticsExcluded, true, 'Gateway profile is still a dev build for analytics');
assert.strictEqual(gatewayConfig.authUserId, undefined, 'Gateway profile must not carry the fixture identity');
assert.match(gatewayConfig.fixtureVersion, /gateway/, 'Gateway profile is tagged so packages are distinguishable');
// 位址優先序防呆：有領到證時語音位址一定用證上的（app.js:getLiveVoiceUrl 第一行）
assert.match(app, /if \(CallControl\.active\) return \(CallControl\.active\.voice && CallControl\.active\.voice\.url\) \|\| ''/);

console.log('Development profile PASS: isolated auto sign-in, points, family fixtures, direct test calls, and gateway mode');
