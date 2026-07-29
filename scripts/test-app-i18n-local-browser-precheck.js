'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const EVIDENCE_PATH = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'app-local-browser-precheck-2026-07-29.json',
);

const evidence = JSON.parse(fs.readFileSync(EVIDENCE_PATH, 'utf8'));
assert.equal(evidence.schema, 'munea.app-local-browser-precheck.v1');
assert.equal(evidence.result, 'fail');
assert.equal(evidence.releaseEvidence, false);
assert.equal(evidence.scope.environment, 'local-fixture-only');
assert.equal(evidence.scope.productionTouched, false);
assert.equal(evidence.scope.appStoreConnectTouched, false);
assert.equal(evidence.scope.installedAppUsed, false);
assert.deepEqual(evidence.networkSafety.observedRequestHosts, ['127.0.0.1']);
assert.equal(evidence.networkSafety.observedExternalRequestCount, 0);
assert.equal(evidence.networkSafety.supabaseConfigured, false);
assert.equal(evidence.networkSafety.productionServiceConfigured, false);
assert.equal(evidence.networkSafety.browserErrors, 0);
assert.equal(evidence.conclusion.localeResolution, 'pass');
assert.equal(evidence.conclusion.sampledLayoutOverflow, 'pass');
assert.equal(evidence.conclusion.fullScreenTranslation, 'fail');
assert.equal(evidence.conclusion.releaseGate, 'blocked');

for (const locale of ['en', 'ja', 'es']) {
  const screen = evidence.screens[`${locale}/home`];
  assert.ok(screen.translationResult.startsWith('fail-untranslated'));
  assert.ok(screen.localizedEvidence.length >= 5);
  assert.ok(screen.untranslatedSamples.length >= 4);
}

for (const [screenId, screen] of Object.entries(evidence.screens)) {
  assert.equal(screen.horizontalOverflowPixels, 0, `${screenId} must not overflow`);
  const screenshotPath = path.resolve(ROOT, screen.screenshot.path);
  assert.ok(
    screenshotPath.startsWith(`${ROOT}${path.sep}`),
    `${screenId} screenshot must stay inside the repository`,
  );
  const bytes = fs.readFileSync(screenshotPath);
  assert.equal(bytes.length, screen.screenshot.bytes, `${screenId} byte count`);
  assert.equal(
    crypto.createHash('sha256').update(bytes).digest('hex'),
    screen.screenshot.sha256,
    `${screenId} screenshot checksum`,
  );
}

process.stdout.write('App local i18n browser precheck evidence passed.\n');
