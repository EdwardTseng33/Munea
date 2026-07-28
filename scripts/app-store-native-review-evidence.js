'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {
  REQUIRED_CHECKS,
  buildAppStoreNativeReviewWorklist,
} = require('./app-store-native-review-worklist.js');

function requiredString(value, label) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} is required`);
  }
  return value.trim();
}

function validIsoDate(value) {
  return typeof value === 'string'
    && value.trim() !== ''
    && !Number.isNaN(Date.parse(value));
}

function compileAppStoreNativeReviewEvidence(worklist) {
  if (!worklist || worklist.schema !== 'munea.app-store-native-review-worklist.v1') {
    throw new Error('App Store native review worklist schema is invalid');
  }
  if (!Array.isArray(worklist.targets) || worklist.targets.length !== 1) {
    throw new Error('compile exactly one App Store locale review at a time');
  }
  const [target] = worklist.targets;
  const canonical = buildAppStoreNativeReviewWorklist(target);
  const expectedReview = canonical.reviews[target];
  const reviewedIdentity = worklist.reviews && worklist.reviews[target];
  if (JSON.stringify(reviewedIdentity) !== JSON.stringify(expectedReview)) {
    throw new Error('reviewed App Store source identity differs from current files');
  }
  if (
    worklist.entryCount !== canonical.entryCount
    || !Array.isArray(worklist.entries)
    || worklist.entries.length !== canonical.entries.length
  ) {
    throw new Error('review must include every current App Store and IAP field');
  }

  const seen = new Set();
  for (let index = 0; index < canonical.entries.length; index += 1) {
    const expected = canonical.entries[index];
    const entry = worklist.entries[index];
    const signature = `${expected.kind}:${expected.key}`;
    if (
      !entry
      || entry.sequence !== expected.sequence
      || entry.kind !== expected.kind
      || entry.key !== expected.key
    ) {
      throw new Error(`review entry order or key drifted at sequence ${expected.sequence}`);
    }
    if (seen.has(signature)) throw new Error(`duplicate App Store review field: ${signature}`);
    seen.add(signature);
    for (const field of [
      'target',
      'catalogLocale',
      'appStoreLocale',
      'source',
      'translation',
      'sourceSha256',
      'translationSha256',
      'exactSourceMatch',
    ]) {
      if (JSON.stringify(entry[field]) !== JSON.stringify(expected[field])) {
        throw new Error(`${signature} ${field} differs from current worklist`);
      }
    }
    if (entry.result !== 'pass') {
      throw new Error(`${signature} has not passed native review`);
    }
    for (const check of REQUIRED_CHECKS) {
      if (!entry.checks || entry.checks[check] !== true) {
        throw new Error(`${signature} is missing review check ${check}`);
      }
    }
    if (entry.exactSourceMatch && target !== 'zh-TW') {
      requiredString(entry.reviewerNote, `${signature} reviewerNote`);
    }
  }

  const review = worklist.review;
  if (!review || typeof review !== 'object') {
    throw new Error('worklist review metadata is required');
  }
  const exactCommit = requiredString(review.exactCommit, 'review.exactCommit');
  if (!/^[0-9a-f]{40}$/i.test(exactCommit)) {
    throw new Error('review.exactCommit must be a 40-character Git SHA');
  }
  if (!validIsoDate(review.reviewedAt)) {
    throw new Error('review.reviewedAt must be an ISO 8601 timestamp');
  }

  return {
    schema: 'munea.app-store-native-review.v1',
    target,
    catalogLocale: expectedReview.catalogLocale,
    appStoreLocale: expectedReview.appStoreLocale,
    result: 'pass',
    exactCommit,
    reviewedAt: review.reviewedAt,
    reviewerReference: requiredString(
      review.reviewerReference,
      'review.reviewerReference',
    ),
    reviewerRole: requiredString(review.reviewerRole, 'review.reviewerRole'),
    identities: expectedReview.identities,
    reviewedEntryCount: expectedReview.entryCount,
    reviewedEntriesSha256: expectedReview.entriesSha256,
    openIssues: 0,
    checks: Object.fromEntries(REQUIRED_CHECKS.map((check) => [check, true])),
  };
}

function validateAppStoreNativeReviewEvidence(evidence, target) {
  try {
    const canonical = buildAppStoreNativeReviewWorklist(target);
    const expected = canonical.reviews[target];
    return evidence
      && evidence.schema === 'munea.app-store-native-review.v1'
      && evidence.target === target
      && evidence.catalogLocale === expected.catalogLocale
      && evidence.appStoreLocale === expected.appStoreLocale
      && evidence.result === 'pass'
      && /^[0-9a-f]{40}$/i.test(evidence.exactCommit || '')
      && validIsoDate(evidence.reviewedAt)
      && typeof evidence.reviewerReference === 'string'
      && evidence.reviewerReference.trim() !== ''
      && typeof evidence.reviewerRole === 'string'
      && evidence.reviewerRole.trim() !== ''
      && JSON.stringify(evidence.identities) === JSON.stringify(expected.identities)
      && evidence.reviewedEntryCount === expected.entryCount
      && evidence.reviewedEntriesSha256 === expected.entriesSha256
      && evidence.openIssues === 0
      && REQUIRED_CHECKS.every((check) => evidence.checks && evidence.checks[check] === true);
  } catch {
    return false;
  }
}

function main() {
  const inputIndex = process.argv.indexOf('--input');
  const outputIndex = process.argv.indexOf('--output');
  const input = inputIndex >= 0 ? process.argv[inputIndex + 1] : '';
  const output = outputIndex >= 0 ? process.argv[outputIndex + 1] : '';
  if (!input || !output) {
    throw new Error(
      'usage: --input <completed-worklist.json> '
      + '--output <app-store-native-review.json>',
    );
  }
  const worklist = JSON.parse(fs.readFileSync(path.resolve(input), 'utf8'));
  const evidence = compileAppStoreNativeReviewEvidence(worklist);
  const outputPath = path.resolve(output);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
  process.stdout.write(
    `App Store native review evidence PASS: ${evidence.target}, `
    + `${evidence.reviewedEntryCount} fields\n`,
  );
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`App Store native review evidence refused: ${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  compileAppStoreNativeReviewEvidence,
  validateAppStoreNativeReviewEvidence,
};
