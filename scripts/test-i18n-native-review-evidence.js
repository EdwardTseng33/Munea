'use strict';

const assert = require('node:assert');
const {
  buildNativeReviewWorklist,
} = require('./i18n-native-review-worklist.js');
const {
  REQUIRED_CHECKS,
  compileNativeReviewEvidence,
} = require('./i18n-native-review-evidence.js');

function completedWorklist(locale = 'en') {
  const worklist = buildNativeReviewWorklist(locale);
  worklist.review = {
    exactCommit: 'a'.repeat(40),
    reviewedAt: '2026-07-28T12:00:00Z',
    reviewerReference: 'native-review-ticket-001',
    reviewerRole: 'native-language-reviewer',
  };
  for (const entry of worklist.entries) {
    entry.result = 'pass';
    entry.checks = Object.fromEntries(REQUIRED_CHECKS.map((check) => [check, true]));
    if (entry.exactSourceMatchDisposition === 'requires-review') {
      entry.reviewerNote = 'Reviewed in context and accepted for this locale.';
    }
  }
  return worklist;
}

const evidence = compileNativeReviewEvidence(completedWorklist());
assert.equal(evidence.schema, 'munea.i18n-native-review.v1');
assert.equal(evidence.locale, 'en');
assert.equal(evidence.result, 'pass');
assert.equal(evidence.reviewedKeyCount, 430);
assert.equal(evidence.openIssues, 0);
assert.deepEqual(
  Object.keys(evidence.checks),
  REQUIRED_CHECKS,
);
assert(Object.values(evidence.checks).every(Boolean));

const incomplete = completedWorklist();
incomplete.entries[0].checks.spokenCopyReadAloud = false;
assert.throws(
  () => compileNativeReviewEvidence(incomplete),
  /spokenCopyReadAloud/,
);

const rejected = completedWorklist();
rejected.entries[1].result = 'pending';
assert.throws(
  () => compileNativeReviewEvidence(rejected),
  /has not passed native review/,
);

const drifted = completedWorklist();
drifted.entries[2].translation = `${drifted.entries[2].translation} changed`;
assert.throws(
  () => compileNativeReviewEvidence(drifted),
  /translation differs/,
);

const missingKey = completedWorklist();
missingKey.entries.pop();
missingKey.entryCount -= 1;
assert.throws(
  () => compileNativeReviewEvidence(missingKey),
  /every current catalog key/,
);

const invalidCommit = completedWorklist();
invalidCommit.review.exactCommit = 'not-a-commit';
assert.throws(
  () => compileNativeReviewEvidence(invalidCommit),
  /40-character Git SHA/,
);

console.log('PASS: native review evidence requires every current catalog key');
