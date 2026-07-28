'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');

const {
  LOCALES,
  buildVisualQaWorklist,
  stateSlug,
} = require('./i18n-visual-qa-worklist.js');

const surfaceManifest = JSON.parse(
  fs.readFileSync('web/src/i18n/app-surface-manifest.json', 'utf8'),
);
const worklist = buildVisualQaWorklist();
const expectedPerLocale = surfaceManifest.surfaces.length
  * surfaceManifest.captureProfiles.length;

assert.equal(worklist.schema, 'munea.i18n-visual-qa-worklist.v1');
assert.deepEqual(worklist.locales, LOCALES);
assert.equal(worklist.entryCount, expectedPerLocale * LOCALES.length);
assert.equal(worklist.entryCount, 456);
assert.equal(worklist.approvalPolicy.automaticPassForbidden, true);
assert.equal(worklist.approvalPolicy.currentRunScreenshotsOnly, true);
assert.equal(worklist.approvalPolicy.exactInstalledAppRequired, true);
assert.equal(worklist.approvalPolicy.manualVisualReviewRequired, true);
assert.deepEqual(worklist.buildIdentity, {
  captureCommit: null,
  binarySha256: null,
  appVersion: null,
  build: null,
});

const signatures = new Set();
const screenshotPaths = new Set();
for (const entry of worklist.entries) {
  const signature = `${entry.locale}:${entry.state}:${entry.profile}`;
  assert.ok(!signatures.has(signature), `Duplicate visual QA entry: ${signature}`);
  signatures.add(signature);
  assert.ok(!screenshotPaths.has(entry.workspacePath), `Duplicate screenshot path: ${entry.workspacePath}`);
  screenshotPaths.add(entry.workspacePath);
  assert.equal(entry.captureSource, 'exact-installed-iphone-app');
  assert.equal(entry.result, 'pending');
  assert.deepEqual(entry.checks, {
    noOverflow: 'pending',
    noClipping: 'pending',
    noUntranslatedCopy: 'pending',
    layoutAccepted: 'pending',
  });
  assert.match(entry.screenshot, /^visual\/[a-z0-9-]+__iphone-[a-z-]+\.png$/);
}

for (const locale of LOCALES) {
  const localeEntries = worklist.entries.filter((entry) => entry.locale === locale);
  assert.equal(localeEntries.length, expectedPerLocale);
  for (const surface of surfaceManifest.surfaces) {
    for (const profile of surfaceManifest.captureProfiles) {
      assert.ok(
        signatures.has(`${locale}:${surface.state}:${profile}`),
        `Missing visual QA job: ${locale}:${surface.state}:${profile}`,
      );
    }
  }
}

const english = buildVisualQaWorklist('en');
assert.deepEqual(english.locales, ['en']);
assert.equal(english.entryCount, expectedPerLocale);
assert.throws(() => buildVisualQaWorklist('fr'), /Unsupported visual QA locale/);
assert.equal(stateSlug('modal:notification-inbox'), 'modal-notification-inbox');

console.log(
  `Visual QA worklist PASS: ${worklist.entryCount} exact-build captures, `
  + `${expectedPerLocale} per locale`,
);
