'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {
  buildVisualQaWorklist,
} = require('./i18n-visual-qa-worklist.js');

const REQUIRED_CHECKS = Object.freeze([
  'noOverflow',
  'noClipping',
  'noUntranslatedCopy',
  'layoutAccepted',
]);
const REQUIRED_PROFILES = Object.freeze([
  'iphone-small-standard',
  'iphone-standard',
  'iphone-dynamic-type-large',
]);
const PROFILE_POINT_SIZES = Object.freeze({
  'iphone-small-standard': [375, 667],
  'iphone-standard': [390, 844],
  'iphone-dynamic-type-large': [390, 844],
});

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

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

const PNG_SIGNATURE = Buffer.from('89504e470d0a1a0a', 'hex');
const CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < table.length; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : (value >>> 1);
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(buffer) {
  let checksum = 0xffffffff;
  for (const byte of buffer) {
    checksum = CRC32_TABLE[(checksum ^ byte) & 0xff] ^ (checksum >>> 8);
  }
  return (checksum ^ 0xffffffff) >>> 0;
}

function pngDimensions(buffer) {
  if (
    !Buffer.isBuffer(buffer)
    || buffer.length < 57
    || !buffer.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)
  ) {
    throw new Error('screenshot is not a complete PNG');
  }

  let offset = PNG_SIGNATURE.length;
  let chunkIndex = 0;
  let width = 0;
  let height = 0;
  let seenHeader = false;
  let seenImageData = false;
  let seenEnd = false;
  while (offset < buffer.length) {
    if (buffer.length - offset < 12) {
      throw new Error('screenshot PNG has a truncated chunk');
    }
    const dataLength = buffer.readUInt32BE(offset);
    if (dataLength > buffer.length - offset - 12) {
      throw new Error('screenshot PNG chunk length exceeds the file');
    }
    const typeOffset = offset + 4;
    const dataOffset = typeOffset + 4;
    const crcOffset = dataOffset + dataLength;
    const typeBytes = buffer.subarray(typeOffset, dataOffset);
    const type = typeBytes.toString('ascii');
    if (!/^[A-Za-z]{4}$/.test(type)) {
      throw new Error('screenshot PNG contains an invalid chunk type');
    }
    const expectedCrc = buffer.readUInt32BE(crcOffset);
    const actualCrc = crc32(buffer.subarray(typeOffset, crcOffset));
    if (actualCrc !== expectedCrc) {
      throw new Error(`screenshot PNG chunk ${type} has an invalid CRC`);
    }
    if (chunkIndex === 0 && type !== 'IHDR') {
      throw new Error('screenshot PNG must start with IHDR');
    }
    if (type === 'IHDR') {
      if (seenHeader || dataLength !== 13) {
        throw new Error('screenshot PNG has an invalid IHDR chunk');
      }
      width = buffer.readUInt32BE(dataOffset);
      height = buffer.readUInt32BE(dataOffset + 4);
      seenHeader = true;
    } else if (type === 'IDAT') {
      if (!seenHeader || seenEnd || dataLength === 0) {
        throw new Error('screenshot PNG has an invalid IDAT chunk');
      }
      seenImageData = true;
    } else if (type === 'IEND') {
      if (!seenHeader || !seenImageData || seenEnd || dataLength !== 0) {
        throw new Error('screenshot PNG has an invalid IEND chunk');
      }
      seenEnd = true;
      if (crcOffset + 4 !== buffer.length) {
        throw new Error('screenshot PNG contains data after IEND');
      }
    } else if (seenEnd) {
      throw new Error('screenshot PNG contains a chunk after IEND');
    }
    offset = crcOffset + 4;
    chunkIndex += 1;
  }
  if (!seenHeader || !seenImageData || !seenEnd) {
    throw new Error('screenshot PNG is missing IHDR, IDAT, or IEND');
  }
  if (width <= 0 || height <= 0) throw new Error('screenshot dimensions are invalid');
  return { width, height };
}

function profileDimensionsMatch(profile, width, height) {
  const points = PROFILE_POINT_SIZES[profile];
  if (!points) return false;
  return [1, 2, 3].some((scale) => (
    width === points[0] * scale && height === points[1] * scale
  ));
}

function screenshotPathInsideEvidenceDir(evidenceDir, relativePath) {
  if (
    typeof relativePath !== 'string'
    || relativePath.trim() === ''
    || path.isAbsolute(relativePath)
  ) {
    throw new Error('screenshot path must be relative to the evidence directory');
  }
  const root = path.resolve(evidenceDir);
  const candidate = path.resolve(root, relativePath);
  if (!candidate.startsWith(`${root}${path.sep}`)) {
    throw new Error('screenshot path escapes the evidence directory');
  }
  if (!fs.existsSync(candidate)) {
    throw new Error(`screenshot is missing: ${relativePath}`);
  }
  const realRoot = fs.realpathSync(root);
  const realCandidate = fs.realpathSync(candidate);
  if (!realCandidate.startsWith(`${realRoot}${path.sep}`)) {
    throw new Error('screenshot symlink escapes the evidence directory');
  }
  return realCandidate;
}

function compileVisualQaEvidence(worklist, options = {}) {
  if (!worklist || worklist.schema !== 'munea.i18n-visual-qa-worklist.v2') {
    throw new Error('visual QA worklist schema is invalid');
  }
  if (!Array.isArray(worklist.locales) || worklist.locales.length !== 1) {
    throw new Error('compile exactly one locale visual QA run at a time');
  }
  const [locale] = worklist.locales;
  const canonical = buildVisualQaWorklist(locale);
  if (
    worklist.entryCount !== canonical.entryCount
    || !Array.isArray(worklist.entries)
    || worklist.entries.length !== canonical.entries.length
  ) {
    throw new Error('visual QA must include all 114 current state/profile captures');
  }
  const evidenceDir = path.resolve(
    requiredString(options.evidenceDir, 'evidenceDir'),
  );
  if (!fs.existsSync(evidenceDir) || !fs.statSync(evidenceDir).isDirectory()) {
    throw new Error('evidenceDir does not exist');
  }

  const build = worklist.buildIdentity;
  if (!build || typeof build !== 'object') throw new Error('buildIdentity is required');
  const captureCommit = requiredString(build.captureCommit, 'buildIdentity.captureCommit');
  const binarySha256 = requiredString(build.binarySha256, 'buildIdentity.binarySha256');
  const appVersion = requiredString(build.appVersion, 'buildIdentity.appVersion');
  const buildNumber = requiredString(build.build, 'buildIdentity.build');
  if (!/^[0-9a-f]{40}$/i.test(captureCommit)) {
    throw new Error('captureCommit must be a 40-character Git SHA');
  }
  if (!/^[0-9a-f]{64}$/i.test(binarySha256)) {
    throw new Error('binarySha256 must be a 64-character SHA-256');
  }
  const review = worklist.review;
  if (!review || typeof review !== 'object') throw new Error('visual review metadata is required');
  if (!validIsoDate(review.capturedAt)) {
    throw new Error('review.capturedAt must be an ISO 8601 timestamp');
  }
  const reviewerReference = requiredString(
    review.reviewerReference,
    'review.reviewerReference',
  );
  const reviewerRole = requiredString(review.reviewerRole, 'review.reviewerRole');

  const hashes = new Set();
  const screenshots = new Set();
  const screenMap = new Map();
  for (let index = 0; index < canonical.entries.length; index += 1) {
    const expected = canonical.entries[index];
    const entry = worklist.entries[index];
    if (!entry || entry.sequence !== expected.sequence) {
      throw new Error(`visual QA sequence drifted at ${expected.sequence}`);
    }
    for (const immutableField of [
      'locale',
      'state',
      'profile',
      'captureMode',
      'source',
      'anchorId',
      'captureSource',
      'staticRisk',
      'screenshot',
      'workspacePath',
    ]) {
      if (JSON.stringify(entry[immutableField]) !== JSON.stringify(expected[immutableField])) {
        throw new Error(
          `${expected.state}/${expected.profile} ${immutableField} differs from current worklist`,
        );
      }
    }
    if (entry.result !== 'pass') {
      throw new Error(`${entry.state}/${entry.profile} has not passed visual review`);
    }
    for (const check of REQUIRED_CHECKS) {
      if (!entry.checks || entry.checks[check] !== true) {
        throw new Error(`${entry.state}/${entry.profile} is missing check ${check}`);
      }
    }
    if (screenshots.has(entry.screenshot)) {
      throw new Error(`screenshot path is reused: ${entry.screenshot}`);
    }
    screenshots.add(entry.screenshot);
    const screenshotPath = screenshotPathInsideEvidenceDir(
      evidenceDir,
      entry.screenshot,
    );
    const data = fs.readFileSync(screenshotPath);
    const dimensions = pngDimensions(data);
    if (!profileDimensionsMatch(entry.profile, dimensions.width, dimensions.height)) {
      throw new Error(
        `${entry.state}/${entry.profile} screenshot dimensions do not match its profile`,
      );
    }
    const digest = sha256(data);
    if (hashes.has(digest)) {
      throw new Error('screenshot bytes are reused across state/profile captures');
    }
    hashes.add(digest);
    if (!screenMap.has(entry.state)) {
      screenMap.set(entry.state, {
        state: entry.state,
        result: 'pass',
        captures: [],
      });
    }
    screenMap.get(entry.state).captures.push({
      profile: entry.profile,
      screenshot: entry.screenshot,
      sha256: digest,
      result: 'pass',
      checks: Object.fromEntries(REQUIRED_CHECKS.map((check) => [check, true])),
    });
  }

  const screens = [...screenMap.values()];
  if (
    screens.some((screen) => (
      screen.captures.length !== REQUIRED_PROFILES.length
      || JSON.stringify(screen.captures.map(({ profile }) => profile))
        !== JSON.stringify(REQUIRED_PROFILES)
    ))
  ) {
    throw new Error('every state must contain all three capture profiles in order');
  }
  return {
    schema: 'munea.i18n-visual-qa.v1',
    locale,
    result: 'pass',
    captureCommit,
    binarySha256,
    capturedAt: review.capturedAt,
    appVersion,
    build: buildNumber,
    reviewerReference,
    reviewerRole,
    profiles: [...REQUIRED_PROFILES],
    screens,
  };
}

function main() {
  const inputIndex = process.argv.indexOf('--input');
  const outputIndex = process.argv.indexOf('--output');
  const input = inputIndex >= 0 ? process.argv[inputIndex + 1] : '';
  const output = outputIndex >= 0 ? process.argv[outputIndex + 1] : '';
  if (!input || !output) {
    throw new Error('usage: --input <completed-worklist.json> --output <visual-qa.json>');
  }
  const inputPath = path.resolve(input);
  const outputPath = path.resolve(output);
  const worklist = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const evidence = compileVisualQaEvidence(worklist, {
    evidenceDir: path.dirname(outputPath),
  });
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
  process.stdout.write(
    `Visual QA evidence PASS: ${evidence.locale}, ${evidence.screens.length} states, `
    + `${evidence.screens.length * evidence.profiles.length} screenshots\n`,
  );
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`Visual QA evidence refused: ${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  PROFILE_POINT_SIZES,
  REQUIRED_CHECKS,
  REQUIRED_PROFILES,
  compileVisualQaEvidence,
  crc32,
  pngDimensions,
  profileDimensionsMatch,
};
