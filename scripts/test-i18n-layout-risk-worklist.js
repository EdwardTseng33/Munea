'use strict';

const assert = require('node:assert/strict');
const {
  LOCALES,
  buildLayoutRiskWorklist,
  estimatedWidthEm,
  formatSummary,
  riskSignals,
} = require('./i18n-layout-risk-worklist.js');

const worklist = buildLayoutRiskWorklist();

assert.equal(worklist.schema, 'munea.i18n-layout-risk-worklist.v1');
assert.deepEqual(worklist.locales, ['zh-TW', 'en', 'ja', 'es']);
assert.equal(worklist.catalogKeyCount, 484);
assert.equal(worklist.entryCount, 484 * LOCALES.length);
assert.equal(worklist.entries.length, worklist.entryCount);
assert.equal(
  Object.values(worklist.summary.bySeverity).reduce((sum, count) => sum + count, 0),
  worklist.entryCount,
);
for (const locale of LOCALES) {
  assert.equal(
    Object.values(worklist.summary.byLocale[locale]).reduce((sum, count) => sum + count, 0),
    484,
  );
}

for (let index = 1; index < worklist.entries.length; index += 1) {
  assert(
    worklist.entries[index - 1].score >= worklist.entries[index].score,
    'Layout risks must be sorted from highest to lowest score',
  );
}
for (const entry of worklist.entries) {
  assert(entry.states.length > 0, `${entry.key} must map to at least one shipping App state`);
  assert.equal(entry.reviewStatus, 'pending');
  assert.equal(entry.visualQaResult, 'pending');
}

assert(estimatedWidthEm('Restore purchases') > estimatedWidthEm('恢復購買'));
const dynamicRisk = riskSignals(
  'Position {position} of {total}, approximately {minutes} minutes',
  '第 {position} 位，約 {minutes} 分鐘',
  ['chat:queued'],
);
assert(dynamicRisk.factors.includes('dynamic-placeholder-width'));
assert(dynamicRisk.factors.some((factor) => factor.includes('expansion')));
assert.equal(worklist.policy.automaticVisualAcceptanceForbidden, true);
assert.equal(worklist.policy.exactInstalledAppScreenshotsRequired, true);
assert.match(formatSummary(worklist), /Top static risks:/);

console.log(
  `Layout risk worklist PASS: ${worklist.entryCount} checks `
  + `(${worklist.summary.bySeverity.high} high, ${worklist.summary.bySeverity.medium} medium)`,
);
