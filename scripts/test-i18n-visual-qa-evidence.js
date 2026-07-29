'use strict';

const assert = require('node:assert');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');
const {
  buildVisualQaWorklist,
} = require('./i18n-visual-qa-worklist.js');
const {
  PROFILE_POINT_SIZES,
  REQUIRED_CHECKS,
  compileVisualQaEvidence,
} = require('./i18n-visual-qa-evidence.js');

function testCrc32(buffer) {
  let checksum = 0xffffffff;
  for (const byte of buffer) {
    checksum ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      checksum = (checksum & 1)
        ? (0xedb88320 ^ (checksum >>> 1))
        : (checksum >>> 1);
    }
  }
  return (checksum ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBytes = Buffer.from(type, 'ascii');
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(testCrc32(Buffer.concat([typeBytes, data])));
  return Buffer.concat([length, typeBytes, data, checksum]);
}

function png(width, height, uniqueByte) {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 6;
  return Buffer.concat([
    Buffer.from('89504e470d0a1a0a', 'hex'),
    pngChunk('IHDR', header),
    pngChunk('IDAT', zlib.deflateSync(Buffer.from([uniqueByte]))),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

function candidateIpa(evidenceDir, name = 'candidate.ipa') {
  const filePath = path.join(evidenceDir, name);
  if (!fs.existsSync(filePath)) {
    fs.writeFileSync(
      filePath,
      Buffer.concat([
        Buffer.from('504b0304', 'hex'),
        Buffer.from(`munea-exact-build-${name}`, 'utf8'),
      ]),
    );
  }
  return filePath;
}

function compile(worklist, evidenceDir, ipaPath = candidateIpa(evidenceDir)) {
  return compileVisualQaEvidence(worklist, { evidenceDir, ipaPath });
}

function completedWorklist(evidenceDir) {
  const worklist = buildVisualQaWorklist('en');
  const ipaData = fs.readFileSync(candidateIpa(evidenceDir));
  worklist.buildIdentity = {
    captureCommit: 'a'.repeat(40),
    binarySha256: crypto.createHash('sha256').update(ipaData).digest('hex'),
    binaryBytes: ipaData.length,
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
  const evidence = compile(worklist, temp);
  assert.equal(evidence.schema, 'munea.i18n-visual-qa.v1');
  assert.equal(evidence.result, 'pass');
  assert.equal(evidence.locale, 'en');
  assert.equal(evidence.screens.length, 38);
  assert.equal(evidence.screens.flatMap(({ captures }) => captures).length, 114);
  assert.equal(
    new Set(evidence.screens.flatMap(({ captures }) => captures.map(({ sha256 }) => sha256))).size,
    114,
  );
  assert.equal(evidence.binaryBytes, fs.statSync(candidateIpa(temp)).size);

  const incomplete = completedWorklist(temp);
  incomplete.entries[0].checks.noClipping = false;
  assert.throws(
    () => compile(incomplete, temp),
    /noClipping/,
  );

  const missing = completedWorklist(temp);
  fs.unlinkSync(path.join(temp, missing.entries[1].screenshot));
  assert.throws(
    () => compile(missing, temp),
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
    () => compile(wrongDimensions, temp),
    /dimensions do not match/,
  );

  const truncated = completedWorklist(temp);
  fs.writeFileSync(
    path.join(temp, truncated.entries[2].screenshot),
    Buffer.from('89504e470d0a1a0a0000000d49484452000001860000034c', 'hex'),
  );
  assert.throws(
    () => compile(truncated, temp),
    /not a complete PNG/,
  );

  const badCrc = completedWorklist(temp);
  const corruptPath = path.join(temp, badCrc.entries[2].screenshot);
  const corrupt = fs.readFileSync(corruptPath);
  corrupt[corrupt.length - 1] ^= 0xff;
  fs.writeFileSync(corruptPath, corrupt);
  assert.throws(
    () => compile(badCrc, temp),
    /invalid CRC/,
  );

  const duplicate = completedWorklist(temp);
  fs.copyFileSync(
    path.join(temp, duplicate.entries[3].screenshot),
    path.join(temp, duplicate.entries[6].screenshot),
  );
  assert.throws(
    () => compile(duplicate, temp),
    /bytes are reused/,
  );

  const drifted = completedWorklist(temp);
  drifted.entries[5].screenshot = '../escape.png';
  assert.throws(
    () => compile(drifted, temp),
    /differs from current worklist/,
  );

  const differentIpa = candidateIpa(temp, 'different.ipa');
  assert.throws(
    () => compile(completedWorklist(temp), temp, differentIpa),
    /binarySha256 does not match/,
  );
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}

console.log('PASS: visual QA evidence requires 114 unique exact-build screenshots');
