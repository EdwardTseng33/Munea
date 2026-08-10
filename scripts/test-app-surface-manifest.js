'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, relativePath), 'utf8'));
}

function readText(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), 'utf8');
}

const manifest = readJson('web/src/i18n/app-surface-manifest.json');
const screenManifest = readJson('web/src/i18n/app-screen-manifest.json');
assert.equal(manifest.schema, 'munea.i18n-app-surface-manifest.v1');
assert.equal(manifest.integrationStatus, 'integrated');
assert.equal(manifest.integrationEvidence.releaseEvidence, false);
assert.equal(
  manifest.integrationEvidence.report,
  'docs/qa/i18n/local-browser-precheck/full-surface-all-profiles-2026-07-29/full-surface-all-profiles-local-browser-precheck.json',
);
assert.deepEqual(manifest.captureProfiles, [
  'iphone-small-standard',
  'iphone-standard',
  'iphone-dynamic-type-large',
]);
// 2026-08-10：39（原本 38）＋ screen:onboarding-intro 開場三頁。
// 這個數字是刻意寫死的閘門——加畫面就要來這裡改一次，畫面總數才不會無聲漂移。
assert.equal(manifest.surfaces.length, 39, 'The complete App visual surface count drifted');

const states = manifest.surfaces.map(({ state }) => state);
assert.equal(new Set(states).size, states.length, 'App visual states must be unique');
const requiredStates = [
  'screen:home',
  'screen:status',
  'screen:family',
  'screen:settings',
  'screen:connect',
  'chat:queued',
  'chat:text-fallback',
  'modal:quiz',
  'modal:challenge',
  'modal:activity-detail',
  'modal:feedback',
  'modal:interests',
  'modal:safety',
  'modal:companion',
  'modal:report',
  'reader:legal',
  'modal:family-circle',
  'modal:invite-family',
  'modal:join-circle',
  'modal:top-up',
  'reader:subscription',
  'modal:appointment',
  'modal:history',
  'modal:consent',
  'modal:version',
  'modal:medication-reminder',
  'modal:medication-manager',
  'modal:auth',
  'page:notification-settings',
  'modal:notification-inbox',
];
for (const state of requiredStates) {
  assert.ok(states.includes(state), `Missing App visual state: ${state}`);
}

const sourceCache = new Map();
for (const surface of manifest.surfaces) {
  assert.ok(
    ['dom-anchor', 'composite-state', 'dynamic-source'].includes(surface.captureMode),
    `${surface.state} has an unsupported capture mode`,
  );
  assert.equal(surface.localizationStatus, 'integrated');
  assert.ok(surface.coverageGroup, `${surface.state} is missing a coverage group`);
  if (!sourceCache.has(surface.source)) sourceCache.set(surface.source, readText(surface.source));
  const source = sourceCache.get(surface.source);
  if (surface.captureMode === 'dynamic-source') {
    assert.ok(source.includes(surface.sourceMarker), `${surface.state} source marker is missing`);
    assert.ok(source.includes(surface.anchorId), `${surface.state} dynamic anchor is missing`);
  } else {
    assert.ok(
      source.includes(`id="${surface.anchorId}"`),
      `${surface.state} DOM anchor ${surface.anchorId} is missing`,
    );
  }
}

const requiredCoverageGroups = [
  ...Object.keys(screenManifest.requiredStates),
  ...Object.keys(screenManifest.requiredModals).map((name) => `modal:${name}`),
];
const coverageGroups = new Set(manifest.surfaces.map(({ coverageGroup }) => coverageGroup));
for (const group of requiredCoverageGroups) {
  assert.ok(coverageGroups.has(group), `Legacy screen coverage group is unmapped: ${group}`);
}

console.log(
  `App surface manifest PASS: ${manifest.surfaces.length} states x `
  + `${manifest.captureProfiles.length} profiles x 4 locales = `
  + `${manifest.surfaces.length * manifest.captureProfiles.length * 4} required screenshots`,
);
