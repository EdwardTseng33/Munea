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
const reviewedAppOccurrences = JSON.parse(
  fs.readFileSync('docs/I18N-NON-USER-FACING-REVIEW.json', 'utf8'),
).entries
  .filter((entry) => appSurface.files.includes(entry.path))
  .reduce((sum, entry) => sum + entry.expectedOccurrences, 0);

assert.equal(worklist.schema, 'munea.i18n-migration-worklist.v3');
assert.equal(worklist.surface, 'app-webview');
assert.deepEqual(worklist.requiredLocales, ['zh-TW', 'en', 'ja', 'es']);
assert(
  worklist.summary.totalOccurrences <= appSurface.baselineHanCandidates,
  'Current App copy inventory must not exceed the checked-in migration baseline',
);
assert(worklist.summary.boundOccurrences > 0, 'Bound fallbacks must be reported separately');
assert.equal(worklist.summary.reviewedNonUserFacingOccurrences, reviewedAppOccurrences);
// 2026-07-31 搬遷歸零後反轉：從「還有債要留在清單上」變成「不准再欠新債」。
// 新增中文文案必須當場綁鍵（或誠實入冊 docs/I18N-NON-USER-FACING-REVIEW.json），
// 否則這裡亮紅——防止上架後的文案漂移（守門跟不上程式的老病，#364 教訓）。
assert.equal(worklist.summary.unboundOccurrences, 0, 'New copy must ship bound (or reviewed) — the migration reached zero on 2026-07-31');
assert.equal(
  worklist.summary.boundOccurrences
    + worklist.summary.reviewedNonUserFacingOccurrences
    + worklist.summary.unboundOccurrences,
  worklist.summary.totalOccurrences,
);
// 歸零前這三類「待辦分類」都必須有量；歸零後清單是空的、只要不出現負值即可
// （有新債時 unboundOccurrences===0 的斷言會先亮，這裡不重複把關）。
assert((worklist.summary.resolutionKinds['reuse-existing-key'] || 0) >= 0);
assert((worklist.summary.resolutionKinds['review-existing-keys'] || 0) >= 0);
assert((worklist.summary.resolutionKinds['create-key'] || 0) >= 0);
assert.equal(
  worklist.summary.bindingKinds.attribute || 0,
  0,
  'Every App/WebView localizable HTML attribute must stay catalog-bound',
);
// 原本的「>500」是防掃描器假歸零的地板（立於債 1,091 時）；2026-07-31 遷移
// 真把唯一字串清到 500 以下、地板功成身退。假歸零仍由三道守著：上面的
// totalOccurrences 對帳、下面的 entries 加總對帳、以及 surface-inventory 契約。
assert(
  worklist.summary.unboundOccurrences === 0 || worklist.summary.uniqueSourceStrings > 0,
  'The worklist must expose the real unbound App copy debt',
);
assert.equal(
  worklist.entries.reduce((sum, entry) => sum + entry.occurrences.length, 0),
  worklist.summary.occurrences,
);
assert.equal(new Set(worklist.entries.map((entry) => entry.suggestedKey)).size, worklist.entries.length);
const migratedAttributeKeys = [
  'accessibility.manageFamily',
  'accessibility.removeImage',
  'accessibility.removePhoto',
  'accessibility.toggleCall',
  'accessibility.toggleCaptions',
  'accessibility.toggleMicrophone',
  'activity.adjustGoal',
  'activity.deadlineDate',
  'activity.deadlineTime',
  'activity.voteQuestionPlaceholder',
  'activity.quizQuestionCountAria',
  'activity.quizDeadlineDate',
  'activity.quizDeadlineTime',
  'activity.eventDate',
  'activity.eventTime',
  'activity.voteDeadlineDate',
  'activity.voteDeadlineTime',
  'activity.drawDate',
  'activity.drawTime',
  'appointment.close',
  'appointment.time',
  'familyCircle.close',
  'feedback.photoPreviewAlt',
  'feedback.npsAria',
  'history.close',
  'history.nextMonth',
  'history.previousMonth',
  'profile.close',
  'purchase.close',
  'subscription.creditRulesTitle',
  'subscription.topUpCreditRulesTitle',
  'textChat.inputAria',
];
for (const key of migratedAttributeKeys) {
  const lingeringAttributeOccurrence = worklist.entries
    .filter((entry) => entry.suggestedKey === key)
    .flatMap((entry) => entry.occurrences)
    .find((occurrence) => occurrence.kind.startsWith('attribute:'));
  assert(
    !lingeringAttributeOccurrence,
    `${key} must stay catalog-bound after the attribute migration batches`,
  );
}
const appSourceLines = fs.readFileSync('web/src/app.js', 'utf8').split(/\r?\n/);
const careCopyStart = appSourceLines.findIndex((line) => line.includes('function localizedCareLabels(')) + 1;
const careCopyEnd = appSourceLines.findIndex((line) => line.includes('function careAdvance(')) + 1;
assert(careCopyStart > 0 && careCopyEnd >= careCopyStart, 'Care copy region must stay discoverable');
const lingeringCareCopy = worklist.entries.flatMap((entry) => entry.occurrences.map((occurrence) => ({
  source: entry.source,
  ...occurrence,
}))).find((occurrence) => (
  occurrence.file === 'web/src/app.js'
  && occurrence.line >= careCopyStart
  && occurrence.line <= careCopyEnd
));
assert(
  !lingeringCareCopy,
  `Care carousel copy must stay catalog-bound: ${JSON.stringify(lingeringCareCopy)}`,
);
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
