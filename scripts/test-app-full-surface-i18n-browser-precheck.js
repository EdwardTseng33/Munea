'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const REPORT_PATH = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'full-surface-all-profiles-2026-07-29',
  'full-surface-all-profiles-local-browser-precheck.json',
);
const report = JSON.parse(fs.readFileSync(REPORT_PATH, 'utf8'));
const manifest = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n', 'app-surface-manifest.json'), 'utf8'),
);
const expectedLocales = ['zh-TW', 'en', 'ja', 'es'];
const expectedStates = manifest.surfaces.map(({ state }) => state);
const expectedProfiles = [
  ['iphone-small-standard', 375, 667, 'std'],
  ['iphone-standard', 390, 844, 'std'],
  ['iphone-dynamic-type-large', 390, 844, 'xl'],
];
assert.equal(report.schema, 'munea.app-full-surface-local-browser-precheck.v2');
assert.equal(report.result, 'pass-local-precheck');
assert.equal(report.releaseEvidence, false);
assert.match(
  report.sourceBaseCommit,
  /^[0-9a-f]{40}$/u,
  'Browser evidence must identify the exact 40-character source commit',
);
assert.doesNotThrow(
  () => execFileSync(
    'git',
    ['merge-base', '--is-ancestor', report.sourceBaseCommit, 'HEAD'],
    { cwd: ROOT, stdio: 'ignore' },
  ),
  'Browser evidence source commit must be an ancestor of the tested HEAD',
);
// 2026-07-30 Edward 兩度拍板：①開發「動到哪個畫面才截那幾張」（capture 工具的
// --states/--locales/--profiles），不必每次改版全拍 456 張；②打包出貨前也不強制全拍——
// 全套模式純屬選用工具，任何關卡都不逼它。原「證據跟上每次畫面改動」的新鮮度檢查已整組移除。
// 這裡只驗留存證據本身完整（張數、雜湊、零失敗、可追到來源存檔點），因為壞掉的證據比沒有更誤導。
assert.equal(report.scope.environment, 'local-fixture-only');
assert.deepEqual(
  report.scope.captureProfiles.map(({ id, viewport, appFontScale }) => [
    id,
    viewport.width,
    viewport.height,
    appFontScale,
  ]),
  expectedProfiles,
);
assert.deepEqual(manifest.captureProfiles, expectedProfiles.map(([id]) => id));
assert.equal(report.scope.productionTouched, false);
assert.equal(report.scope.stagingTouched, false);
assert.equal(report.scope.appStoreConnectTouched, false);
assert.equal(report.scope.installedAppUsed, false);
assert.deepEqual(report.networkSafety.observedExternalRequests, []);
assert.deepEqual(report.failures, []);
assert.equal(
  report.screens.length,
  expectedLocales.length * expectedStates.length * expectedProfiles.length,
);

const observed = new Set();
for (const screen of report.screens) {
  assert.ok(expectedLocales.includes(screen.locale), `Unexpected locale ${screen.locale}`);
  assert.ok(expectedStates.includes(screen.state), `Unexpected state ${screen.state}`);
  const profile = expectedProfiles.find(([id]) => id === screen.profile);
  assert.ok(profile, `Unexpected profile ${screen.profile}`);
  assert.deepEqual(
    [screen.viewport.width, screen.viewport.height, screen.appFontScale],
    profile.slice(1),
    `${screen.profile} runtime profile`,
  );
  const identity = `${screen.profile}/${screen.locale}/${screen.state}`;
  assert.ok(!observed.has(identity), `Duplicate screen ${identity}`);
  observed.add(identity);
  assert.equal(screen.translationResult, 'pass', `${identity} translation`);
  assert.equal(screen.layoutResult, 'pass', `${identity} layout`);
  assert.equal(screen.visibilityResult, 'pass', `${identity} visibility`);
  assert.deepEqual(screen.browserErrors, [], `${identity} browser errors`);
  const screenshotPath = path.resolve(ROOT, screen.screenshot.path);
  assert.ok(screenshotPath.startsWith(`${ROOT}${path.sep}`), `${identity} path scope`);
  const bytes = fs.readFileSync(screenshotPath);
  assert.equal(bytes.length, screen.screenshot.bytes, `${identity} screenshot bytes`);
  assert.equal(
    crypto.createHash('sha256').update(bytes).digest('hex'),
    screen.screenshot.sha256,
    `${identity} screenshot checksum`,
  );
}

for (const [profile] of expectedProfiles) {
  for (const locale of expectedLocales) {
    for (const state of expectedStates) {
      assert.ok(
        observed.has(`${profile}/${locale}/${state}`),
        `Missing ${profile}/${locale}/${state}`,
      );
    }
  }
}

process.stdout.write(
  `Full-surface App i18n browser evidence PASS: ${report.screens.length} local screenshots bound to ${report.sourceBaseCommit.slice(0, 8)}.\n`,
);
