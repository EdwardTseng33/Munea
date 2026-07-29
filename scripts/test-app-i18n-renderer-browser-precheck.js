'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const evidencePath = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'dynamic-renderers',
  'app-renderer-browser-precheck-2026-07-29.json',
);
const evidence = JSON.parse(fs.readFileSync(evidencePath, 'utf8'));

assert.equal(evidence.schema, 'munea.app-renderer-local-browser-precheck.v1');
assert.equal(evidence.result, 'pass-local-renderer-copy');
assert.equal(evidence.releaseEvidence, false);
assert.equal(evidence.scope.environment, 'local-fixture-only');
assert.equal(evidence.scope.productionTouched, false);
assert.equal(evidence.scope.stagingTouched, false);
assert.equal(evidence.scope.appStoreConnectTouched, false);
assert.equal(evidence.scope.installedAppUsed, false);
assert.deepEqual(evidence.networkSafety.observedRequestHosts, ['127.0.0.1']);
assert.equal(evidence.networkSafety.observedExternalRequestCount, 0);
assert.equal(evidence.networkSafety.browserErrors, 0);
assert.equal(evidence.conclusion.dynamicRendererCopy, 'pass');
assert.equal(evidence.conclusion.appRuntimeIntegration, 'pending-conflicting-main-screen-prs');
assert.equal(evidence.conclusion.releaseGate, 'blocked');

const hanPattern = /[\u3400-\u9fff\uf900-\ufaff]/u;
for (const locale of ['zh-TW', 'en', 'ja', 'es']) {
  const screenId = `${locale}/dynamic-renderers`;
  const screen = evidence.screens[screenId];
  assert.equal(screen.resolvedLocale, locale);
  assert.equal(screen.horizontalOverflowPixels, 0, `${screenId} overflowed`);
  assert.equal(screen.translationResult, 'pass-renderer-copy');
  assert.equal(screen.layoutResult, 'pass');
  for (const family of ['queue', 'care', 'visit', 'plan']) {
    assert.ok(screen[family].length >= 2, `${screenId}:${family} evidence is incomplete`);
  }
  if (locale === 'en' || locale === 'es') {
    assert.ok(
      !hanPattern.test(JSON.stringify(screen)),
      `${screenId} contains unexpected Han text`,
    );
  }
  const screenshotPath = path.resolve(ROOT, screen.screenshot.path);
  assert.ok(screenshotPath.startsWith(`${ROOT}${path.sep}`));
  const bytes = fs.readFileSync(screenshotPath);
  assert.equal(bytes.length, screen.screenshot.bytes, `${screenId} byte count`);
  assert.equal(
    crypto.createHash('sha256').update(bytes).digest('hex'),
    screen.screenshot.sha256,
    `${screenId} screenshot checksum`,
  );
}

console.log('App renderer browser precheck PASS: four locales, localhost only');
