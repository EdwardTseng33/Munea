'use strict';

const assert = require('node:assert/strict');
const {
  REQUIRED_CHECKS,
  buildAppStoreNativeReviewWorklist,
} = require('./app-store-native-review-worklist.js');
const {
  compileAppStoreNativeReviewEvidence,
  validateAppStoreNativeReviewEvidence,
} = require('./app-store-native-review-evidence.js');

function completedWorklist(target = 'en') {
  const worklist = buildAppStoreNativeReviewWorklist(target);
  worklist.review = {
    exactCommit: 'a'.repeat(40),
    reviewedAt: '2026-07-29T08:00:00Z',
    reviewerReference: 'store-review-ticket-001',
    reviewerRole: 'native-language-store-reviewer',
  };
  for (const entry of worklist.entries) {
    entry.result = 'pass';
    entry.checks = Object.fromEntries(REQUIRED_CHECKS.map((check) => [check, true]));
    if (entry.exactSourceMatch && target !== 'zh-TW') {
      entry.reviewerNote = 'Reviewed in App Store context and accepted.';
    }
  }
  return worklist;
}

const evidence = compileAppStoreNativeReviewEvidence(completedWorklist());
assert.equal(evidence.schema, 'munea.app-store-native-review.v1');
assert.equal(evidence.target, 'en');
assert.equal(evidence.catalogLocale, 'en');
assert.equal(evidence.appStoreLocale, 'en-US');
assert.equal(evidence.reviewedEntryCount, 32);
assert.equal(evidence.openIssues, 0);
assert.equal(validateAppStoreNativeReviewEvidence(evidence, 'en'), true);

const incomplete = completedWorklist();
incomplete.entries[0].checks.claimAccurate = false;
assert.throws(
  () => compileAppStoreNativeReviewEvidence(incomplete),
  /claimAccurate/,
);

const pending = completedWorklist();
pending.entries[1].result = 'pending';
assert.throws(
  () => compileAppStoreNativeReviewEvidence(pending),
  /has not passed native review/,
);

const drifted = completedWorklist();
drifted.entries[2].translation += ' changed';
assert.throws(
  () => compileAppStoreNativeReviewEvidence(drifted),
  /translation differs/,
);

const missing = completedWorklist();
missing.entries.pop();
missing.entryCount -= 1;
assert.throws(
  () => compileAppStoreNativeReviewEvidence(missing),
  /every current App Store and IAP field/,
);

const exactMatch = completedWorklist('ja');
const matching = exactMatch.entries.find((entry) => entry.exactSourceMatch);
if (matching) {
  matching.reviewerNote = null;
  assert.throws(
    () => compileAppStoreNativeReviewEvidence(exactMatch),
    /reviewerNote/,
  );
}

assert.equal(
  validateAppStoreNativeReviewEvidence(
    { ...evidence, reviewedEntriesSha256: '0'.repeat(64) },
    'en',
  ),
  false,
);
assert.equal(validateAppStoreNativeReviewEvidence(evidence, 'ja'), false);

console.log('PASS: App Store native review evidence is complete and byte-bound');
