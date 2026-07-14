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
assert.strictEqual(config.analyticsExcluded, true);
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

console.log('Development profile PASS: isolated auto sign-in, points, and family fixtures');
