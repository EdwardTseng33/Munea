'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const I18N_DIR = path.join(ROOT, 'web', 'src', 'i18n');
const LOCALES = ['zh-TW', 'en', 'ja', 'es'];

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, relativePath), 'utf8'));
}

const surfaceManifest = readJson('web/src/i18n/app-surface-manifest.json');
const copyManifest = readJson('web/src/i18n/app-surface-copy-manifest.json');
const catalogs = Object.fromEntries(
  LOCALES.map((locale) => [
    locale,
    readJson(`web/src/i18n/${locale}.json`),
  ]),
);

assert.equal(copyManifest.schema, 'munea.i18n-app-surface-copy-manifest.v1');
assert.equal(copyManifest.catalogStatus, 'complete-for-current-surface-inventory');

const expectedStates = surfaceManifest.surfaces.map(({ state }) => state).sort();
const actualStates = copyManifest.surfaces.map(({ state }) => state).sort();
assert.deepEqual(actualStates, expectedStates, 'Copy manifest must cover every shipping App state exactly once');
assert.equal(new Set(actualStates).size, actualStates.length, 'Copy manifest states must be unique');

const referenceCatalog = catalogs['zh-TW'];
const referenceKeys = Object.keys(referenceCatalog).sort();
const coveredKeys = new Set();

for (const surface of copyManifest.surfaces) {
  assert.ok(Array.isArray(surface.keyPrefixes), `${surface.state} keyPrefixes must be an array`);
  assert.ok(Array.isArray(surface.requiredKeys), `${surface.state} requiredKeys must be an array`);
  assert.equal(
    new Set(surface.requiredKeys).size,
    surface.requiredKeys.length,
    `${surface.state} requiredKeys must not contain duplicates`,
  );

  const prefixKeys = surface.keyPrefixes.flatMap((prefix) => {
    assert.equal(typeof prefix, 'string', `${surface.state} has a non-string key prefix`);
    assert.ok(prefix.length > 0, `${surface.state} has an empty key prefix`);
    const matches = referenceKeys.filter((key) => key.startsWith(prefix));
    assert.ok(matches.length > 0, `${surface.state} prefix ${prefix} matches no catalog keys`);
    return matches;
  });
  const resolvedKeys = [...new Set([...prefixKeys, ...surface.requiredKeys])];
  assert.ok(resolvedKeys.length >= 3, `${surface.state} must bind at least three meaningful copy keys`);

  for (const key of resolvedKeys) {
    for (const locale of LOCALES) {
      assert.equal(
        typeof catalogs[locale][key],
        'string',
        `${surface.state} key ${key} is missing from ${locale}`,
      );
      assert.notEqual(catalogs[locale][key].trim(), '', `${surface.state} key ${key} is blank in ${locale}`);
    }
    coveredKeys.add(key);
  }
}

assert.deepEqual(
  [...coveredKeys].sort(),
  referenceKeys,
  'Every catalog key must belong to at least one shipping App surface',
);

for (const locale of ['en', 'es']) {
  for (const [key, value] of Object.entries(catalogs[locale])) {
    assert.ok(!/\p{Script=Han}/u.test(value), `${locale}.${key} must not contain Han text`);
  }
}

const surfaceMap = new Map(copyManifest.surfaces.map((surface) => [surface.state, surface]));
const criticalKeys = {
  'screen:connect': 'connect.medicalDisclaimer',
  'modal:safety': 'safety.disclaimer',
  'modal:consent': 'consent.emergencyGeneric',
  'modal:medication-manager': 'medicationManager.disclaimer',
  'page:notification-settings': 'notification.privacy',
};
for (const [state, key] of Object.entries(criticalKeys)) {
  const surface = surfaceMap.get(state);
  assert.ok(
    surface.requiredKeys.includes(key),
    `${state} must explicitly require high-risk copy key ${key}`,
  );
}

console.log(
  `App surface copy manifest PASS: ${actualStates.length} states cover `
  + `${coveredKeys.size} keys across ${LOCALES.length} locales`,
);
