'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const REPORT_PATH = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'full-surface-standard-2026-07-29',
  'full-surface-standard-local-browser-precheck.json',
);
const report = JSON.parse(fs.readFileSync(REPORT_PATH, 'utf8'));
const manifest = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n', 'app-surface-manifest.json'), 'utf8'),
);
const expectedLocales = ['zh-TW', 'en', 'ja', 'es'];
const expectedStates = manifest.surfaces.map(({ state }) => state);

assert.equal(report.schema, 'munea.app-full-surface-standard-local-browser-precheck.v1');
assert.equal(report.result, 'pass-local-precheck');
assert.equal(report.releaseEvidence, false);
assert.equal(report.scope.environment, 'local-fixture-only');
assert.equal(report.scope.captureProfile, 'iphone-standard');
assert.equal(report.scope.productionTouched, false);
assert.equal(report.scope.stagingTouched, false);
assert.equal(report.scope.appStoreConnectTouched, false);
assert.equal(report.scope.installedAppUsed, false);
assert.deepEqual(report.networkSafety.observedExternalRequests, []);
assert.deepEqual(report.failures, []);
assert.equal(report.screens.length, expectedLocales.length * expectedStates.length);

const observed = new Set();
for (const screen of report.screens) {
  assert.ok(expectedLocales.includes(screen.locale), `Unexpected locale ${screen.locale}`);
  assert.ok(expectedStates.includes(screen.state), `Unexpected state ${screen.state}`);
  const identity = `${screen.locale}/${screen.state}`;
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

for (const locale of expectedLocales) {
  for (const state of expectedStates) {
    assert.ok(observed.has(`${locale}/${state}`), `Missing ${locale}/${state}`);
  }
}

process.stdout.write(
  `Full-surface App i18n browser evidence PASS: ${report.screens.length} local screenshots.\n`,
);
