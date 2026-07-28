'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {
  buildNativeReviewWorklist,
} = require('./i18n-native-review-worklist.js');

const REQUIRED_CHECKS = Object.freeze([
  'meaningPreserved',
  'grammarNatural',
  'toneAppropriate',
  'culturalContextAccepted',
  'placeholderContextAccepted',
  'spokenCopyReadAloud',
]);

function validIsoDate(value) {
  return typeof value === 'string'
    && value.trim() !== ''
    && !Number.isNaN(Date.parse(value));
}

function requiredString(value, label) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} is required`);
  }
  return value.trim();
}

function compileNativeReviewEvidence(worklist) {
  if (!worklist || worklist.schema !== 'munea.i18n-native-review-worklist.v1') {
    throw new Error('native review worklist schema is invalid');
  }
  if (!Array.isArray(worklist.locales) || worklist.locales.length !== 1) {
    throw new Error('compile exactly one locale review at a time');
  }
  const [locale] = worklist.locales;
  const canonical = buildNativeReviewWorklist(locale);
  const expectedCatalog = canonical.catalogs[locale];
  const reviewedCatalog = worklist.catalogs && worklist.catalogs[locale];
  if (JSON.stringify(reviewedCatalog) !== JSON.stringify(expectedCatalog)) {
    throw new Error('reviewed catalog identity differs from current catalog');
  }
  if (
    worklist.entryCount !== canonical.entryCount
    || !Array.isArray(worklist.entries)
    || worklist.entries.length !== canonical.entries.length
  ) {
    throw new Error('review must include every current catalog key exactly once');
  }

  const expectedKeys = new Set();
  for (let index = 0; index < canonical.entries.length; index += 1) {
    const expected = canonical.entries[index];
    const entry = worklist.entries[index];
    if (!entry || entry.sequence !== expected.sequence || entry.key !== expected.key) {
      throw new Error(`review entry order or key drifted at sequence ${expected.sequence}`);
    }
    if (expectedKeys.has(entry.key)) {
      throw new Error(`duplicate review key: ${entry.key}`);
    }
    expectedKeys.add(entry.key);
    for (const immutableField of [
      'locale',
      'contentVariant',
      'sourceLocale',
      'source',
      'translation',
      'sourceSha256',
      'translationSha256',
      'exactSourceMatch',
      'exactSourceMatchDisposition',
    ]) {
      if (JSON.stringify(entry[immutableField]) !== JSON.stringify(expected[immutableField])) {
        throw new Error(`${entry.key} ${immutableField} differs from current worklist`);
      }
    }
    if (JSON.stringify(entry.placeholders) !== JSON.stringify(expected.placeholders)) {
      throw new Error(`${entry.key} placeholder contract differs from current worklist`);
    }
    if (entry.result !== 'pass') {
      throw new Error(`${entry.key} has not passed native review`);
    }
    for (const check of REQUIRED_CHECKS) {
      if (!entry.checks || entry.checks[check] !== true) {
        throw new Error(`${entry.key} is missing native review check ${check}`);
      }
    }
    if (
      entry.exactSourceMatch
      && entry.exactSourceMatchDisposition === 'requires-review'
      && !requiredString(entry.reviewerNote, `${entry.key} reviewerNote`)
    ) {
      throw new Error(`${entry.key} exact source match needs a reviewer note`);
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
  const reviewerReference = requiredString(
    review.reviewerReference,
    'review.reviewerReference',
  );
  const reviewerRole = requiredString(review.reviewerRole, 'review.reviewerRole');

  return {
    schema: 'munea.i18n-native-review.v1',
    locale,
    contentVariant: expectedCatalog.contentVariant,
    result: 'pass',
    exactCommit,
    reviewedAt: review.reviewedAt,
    reviewerReference,
    reviewerRole,
    catalogSha256: expectedCatalog.catalogSha256,
    reviewedKeyCount: expectedCatalog.keyCount,
    reviewedKeysSha256: expectedCatalog.keysSha256,
    openIssues: 0,
    checks: Object.fromEntries(REQUIRED_CHECKS.map((check) => [check, true])),
  };
}

function main() {
  const inputIndex = process.argv.indexOf('--input');
  const outputIndex = process.argv.indexOf('--output');
  const input = inputIndex >= 0 ? process.argv[inputIndex + 1] : '';
  const output = outputIndex >= 0 ? process.argv[outputIndex + 1] : '';
  if (!input || !output) {
    throw new Error('usage: --input <completed-worklist.json> --output <native-review.json>');
  }
  const inputPath = path.resolve(input);
  const outputPath = path.resolve(output);
  const worklist = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const evidence = compileNativeReviewEvidence(worklist);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
  process.stdout.write(
    `Native review evidence PASS: ${evidence.locale}, ${evidence.reviewedKeyCount} keys\n`,
  );
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`Native review evidence refused: ${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  REQUIRED_CHECKS,
  compileNativeReviewEvidence,
};
