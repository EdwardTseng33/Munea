'use strict';

const assert = require('node:assert/strict');
const {
  REQUIRED_CHECKS,
  TARGETS,
  buildAppStoreNativeReviewWorklist,
} = require('./app-store-native-review-worklist.js');

const worklist = buildAppStoreNativeReviewWorklist();
const expectedPerTarget = 32;

assert.equal(worklist.schema, 'munea.app-store-native-review-worklist.v1');
assert.deepEqual(worklist.targets, TARGETS);
assert.equal(worklist.entryCount, expectedPerTarget * TARGETS.length);
assert.deepEqual(
  worklist.entries.map(({ sequence }) => sequence),
  Array.from({ length: worklist.entryCount }, (_, index) => index + 1),
);
assert.equal(worklist.approvalPolicy.automaticPassForbidden, true);
assert.equal(worklist.approvalPolicy.nativeLanguageReviewerRequired, true);
assert.equal(worklist.approvalPolicy.allEightProductsRequired, true);
assert.equal(worklist.approvalPolicy.screenshotCopyReviewRequired, true);

for (const target of TARGETS) {
  const review = worklist.reviews[target];
  const entries = worklist.entries.filter((entry) => entry.target === target);
  assert.equal(review.entryCount, expectedPerTarget);
  assert.equal(entries.length, expectedPerTarget);
  assert.match(review.entriesSha256, /^[a-f0-9]{64}$/);
  assert.equal(
    entries.filter(({ kind }) => kind === 'app-metadata').length,
    6,
  );
  assert.equal(
    entries.filter(({ kind }) => kind === 'app-store-screenshot-copy').length,
    10,
  );
  assert.equal(
    entries.filter(({ kind }) => kind === 'in-app-purchase-metadata').length,
    16,
  );
  for (const identity of Object.values(review.identities)) {
    assert.match(identity.sha256, /^[a-f0-9]{64}$/);
    assert(identity.bytes > 0);
    assert.equal(typeof identity.scope, 'string');
    assert(identity.scope);
  }
  for (const entry of entries) {
    assert.equal(entry.result, 'pending');
    assert.deepEqual(
      entry.checks,
      Object.fromEntries(REQUIRED_CHECKS.map((check) => [check, 'pending'])),
    );
  }
}

assert.equal(worklist.reviews['es-ES'].catalogLocale, 'es');
assert.equal(worklist.reviews['es-ES'].appStoreLocale, 'es-ES');
assert.equal(worklist.reviews['es-ES'].safetyRegion, 'ES');
assert.equal(worklist.reviews['es-MX'].legalRegion, 'MX');
assert.equal(
  worklist.reviews.en.identities.metadata.scope,
  'complete-file',
);
assert.equal(
  worklist.reviews.en.identities.storeManifest.scope,
  'selected-locale-routing-and-region-policy',
);
assert.equal(
  worklist.reviews.en.identities.iapManifest.scope,
  'product-facts-and-selected-locale-routing',
);

for (const target of TARGETS) {
  const single = buildAppStoreNativeReviewWorklist(target);
  assert.deepEqual(single.targets, [target]);
  assert.equal(single.entryCount, expectedPerTarget);
}
assert.throws(
  () => buildAppStoreNativeReviewWorklist('es'),
  /Unsupported App Store review target/,
);
assert.throws(
  () => buildAppStoreNativeReviewWorklist('fr'),
  /Unsupported App Store review target/,
);

console.log(
  `PASS: App Store native review worklist covers ${TARGETS.length} targets `
  + `and ${worklist.entryCount} fields`,
);
