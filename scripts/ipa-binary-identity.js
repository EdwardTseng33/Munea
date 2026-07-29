'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

function requiredString(value, label) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} is required`);
  }
  return value.trim();
}

function inspectIpaBinary(ipaPath) {
  const requestedPath = path.resolve(requiredString(ipaPath, 'ipaPath'));
  if (path.extname(requestedPath).toLowerCase() !== '.ipa') {
    throw new Error('ipaPath must point to an .ipa file');
  }
  if (!fs.existsSync(requestedPath)) {
    throw new Error('IPA file does not exist');
  }
  const realPath = fs.realpathSync(requestedPath);
  const stat = fs.statSync(realPath);
  if (!stat.isFile() || stat.size < 4) {
    throw new Error('IPA path is not a non-empty regular file');
  }
  const descriptor = fs.openSync(realPath, 'r');
  const prefix = Buffer.alloc(4);
  try {
    if (fs.readSync(descriptor, prefix, 0, prefix.length, 0) !== prefix.length) {
      throw new Error('IPA file is truncated');
    }
  } finally {
    fs.closeSync(descriptor);
  }
  if (!prefix.equals(Buffer.from('504b0304', 'hex'))) {
    throw new Error('IPA file is not a ZIP archive');
  }
  const data = fs.readFileSync(realPath);
  return {
    binarySha256: crypto.createHash('sha256').update(data).digest('hex'),
    binaryBytes: data.length,
  };
}

function verifyDeclaredIpaIdentity(buildIdentity, ipaPath) {
  if (!buildIdentity || typeof buildIdentity !== 'object') {
    throw new Error('buildIdentity is required');
  }
  const declaredSha256 = requiredString(
    buildIdentity.binarySha256,
    'buildIdentity.binarySha256',
  ).toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(declaredSha256)) {
    throw new Error('buildIdentity.binarySha256 must be a 64-character SHA-256');
  }
  if (
    !Number.isSafeInteger(buildIdentity.binaryBytes)
    || buildIdentity.binaryBytes <= 0
  ) {
    throw new Error('buildIdentity.binaryBytes must be a positive integer');
  }
  const actual = inspectIpaBinary(ipaPath);
  if (declaredSha256 !== actual.binarySha256) {
    throw new Error('buildIdentity.binarySha256 does not match the supplied IPA');
  }
  if (buildIdentity.binaryBytes !== actual.binaryBytes) {
    throw new Error('buildIdentity.binaryBytes does not match the supplied IPA');
  }
  return actual;
}

module.exports = {
  inspectIpaBinary,
  verifyDeclaredIpaIdentity,
};
