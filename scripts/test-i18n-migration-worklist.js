'use strict';

const assert = require('assert');
const fs = require('fs');
const {
  bindingKind,
  buildMigrationWorklist,
  catalogValueIndex,
  formatSummary,
  stableKey,
} = require('./i18n-migration-worklist.js');

const worklist = buildMigrationWorklist();
const inventory = JSON.parse(fs.readFileSync('docs/I18N-SURFACE-INVENTORY.json', 'utf8'));
const appSurface = inventory.surfaces.find((surface) => surface.id === 'app-webview');

assert.equal(worklist.schema, 'munea.i18n-migration-worklist.v3');
assert.equal(worklist.surface, 'app-webview');
assert.deepEqual(worklist.requiredLocales, ['zh-TW', 'en', 'ja', 'es']);
assert.equal(worklist.summary.totalOccurrences, appSurface.baselineHanCandidates);
assert(worklist.summary.boundOccurrences > 0, 'Bound fallbacks must be reported separately');
assert.equal(worklist.summary.reviewedNonUserFacingOccurrences, 8);
assert(worklist.summary.unboundOccurrences > 0, 'Unbound copy must remain in the worklist');
assert.equal(
  worklist.summary.boundOccurrences
    + worklist.summary.reviewedNonUserFacingOccurrences
    + worklist.summary.unboundOccurrences,
  worklist.summary.totalOccurrences,
);
assert(worklist.summary.resolutionKinds['reuse-existing-key'] > 0);
assert(worklist.summary.resolutionKinds['review-existing-keys'] > 0);
assert(worklist.summary.resolutionKinds['create-key'] > 0);
assert(
  worklist.summary.uniqueSourceStrings > 500,
  'The worklist must expose the real unbound App copy debt',
);
assert.equal(
  worklist.entries.reduce((sum, entry) => sum + entry.occurrences.length, 0),
  worklist.summary.occurrences,
);
assert.equal(new Set(worklist.entries.map((entry) => entry.suggestedKey)).size, worklist.entries.length);
for (const entry of worklist.entries) {
  assert.equal(entry.reviewStatus, 'pending', 'No catalog match may auto-approve source migration');
  if (entry.resolutionKind === 'reuse-existing-key') {
    assert.equal(entry.catalogMatches.length, 1);
    assert.equal(entry.suggestedKey, entry.catalogMatches[0]);
  }
  if (entry.resolutionKind === 'review-existing-keys') {
    assert(entry.catalogMatches.length > 1);
    assert.equal(entry.suggestedKey, stableKey(entry.source));
  }
}
assert(catalogValueIndex().get('設定').includes('settings.title'));
assert.equal(stableKey('開心'), stableKey('開心'), 'Suggested keys must be deterministic');
assert.notEqual(stableKey('開心'), stableKey('平靜'), 'Different source copy must not share a key');
assert.equal(
  bindingKind({ kind: 'inline-string', text: '<button>先不用</button>' }),
  'markup-refactor',
);
assert.equal(
  bindingKind({ kind: 'template-string', text: '還有 {count} 分鐘' }),
  'interpolated-copy',
);
assert.match(formatSummary(worklist), /Unique source strings:/);
assert.throws(
  () => buildMigrationWorklist('locale-contract'),
  /not a localized-text surface/,
);

console.log(
  `PASS: deterministic i18n migration worklist (${worklist.summary.occurrences} occurrences, `
  + `${worklist.summary.uniqueSourceStrings} unique)`,
);
