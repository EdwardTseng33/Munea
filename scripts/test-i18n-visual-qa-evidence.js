'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  buildVisualQaWorklist,
} = require('./i18n-visual-qa-worklist.js');
const {
  PROFILE_POINT_SIZES,
  REQUIRED_CHECKS,
  compileVisualQaEvidence,
} = require('./i18n-visual-qa-evidence.js');

function png(width, height, uniqueByte) {
  const buffer = Buffer.alloc(25);
  Buffer.from('89504e470d0a1a0a', 'hex').copy(buffer, 0);
  Buffer.from('49484452', 'hex').copy(buffer, 12);
  buffer.writeUInt32BE(width, 16);
  buffer.writeUInt32BE(height, 20);
  buffer.writeUInt8(uniqueByte, 24);
  return buffer;
}

function completedWorklist(evidenceDir) {
  const worklist = buildVisualQaWorklist('en');
  worklist.buildIdentity = {
    captureCommit: 'a'.repeat(40),
    binarySha256: 'b'.repeat(64),
    appVersion: '1.0.45',
    build: '500',
  };
  worklist.review = {
    capturedAt: '2026-07-28T12:00:00Z',
    reviewerReference: 'visual-review-ticket-001',
    reviewerRole: 'visual-qa-reviewer',
  };
  worklist.entries.forEach((entry, index) => {
    entry.result = 'pass';
    entry.checks = Object.fromEntries(REQUIRED_CHECKS.map((check) => [check, true]));
    const [width, height] = PROFILE_POINT_SIZES[entry.profile];
    const filePath = path.join(evidenceDir, entry.screenshot);
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, png(width, height, index + 1));
  });
  return worklist;
}

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'munea-visual-evidence-'));
try {
  const worklist = completedWorklist(temp);
  const evidence = compileVisualQaEvidence(worklist, { evidenceDir: temp });
  assert.equal(evidence.schema, 'munea.i18n-visual-qa.v1');
  assert.equal(evidence.result, 'pass');
  assert.equal(evidence.locale, 'en');
  assert.equal(evidence.screens.length, 38);
  assert.equal(evidence.screens.flatMap(({ captures }) => captures).length, 114);
  assert.equal(
    new Set(evidence.screens.flatMap(({ captures }) => captures.map(({ sha256 }) => sha256))).size,
    114,
  );

  const incomplete = completedWorklist(temp);
  incomplete.entries[0].checks.noClipping = false;
  assert.throws(
    () => compileVisualQaEvidence(incomplete, { evidenceDir: temp }),
    /noClipping/,
  );

  const missing = completedWorklist(temp);
  fs.unlinkSync(path.join(temp, missing.entries[1].screenshot));
  assert.throws(
    () => compileVisualQaEvidence(missing, { evidenceDir: temp }),
    /screenshot is missing/,
  );
  fs.writeFileSync(
    path.join(temp, missing.entries[1].screenshot),
    png(...PROFILE_POINT_SIZES[missing.entries[1].profile], 2),
  );

  const wrongDimensions = completedWorklist(temp);
  fs.writeFileSync(
    path.join(temp, wrongDimensions.entries[2].screenshot),
    png(320, 480, 250),
  );
  assert.throws(
    () => compileVisualQaEvidence(wrongDimensions, { evidenceDir: temp }),
    /dimensions do not match/,
  );

  const duplicate = completedWorklist(temp);
  fs.copyFileSync(
    path.join(temp, duplicate.entries[3].screenshot),
    path.join(temp, duplicate.entries[6].screenshot),
  );
  assert.throws(
    () => compileVisualQaEvidence(duplicate, { evidenceDir: temp }),
    /bytes are reused/,
  );

  const drifted = completedWorklist(temp);
  drifted.entries[5].screenshot = '../escape.png';
  assert.throws(
    () => compileVisualQaEvidence(drifted, { evidenceDir: temp }),
    /differs from current worklist/,
  );
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}

console.log('PASS: visual QA evidence requires 114 unique exact-build screenshots');
