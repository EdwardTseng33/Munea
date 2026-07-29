'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  inspectIpaBinary,
  verifyDeclaredIpaIdentity,
} = require('./ipa-binary-identity.js');

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'munea-ipa-identity-'));
try {
  const ipaPath = path.join(temp, 'candidate.ipa');
  const data = Buffer.concat([
    Buffer.from('504b0304', 'hex'),
    Buffer.from('munea-exported-candidate', 'utf8'),
  ]);
  fs.writeFileSync(ipaPath, data);
  const expectedSha256 = crypto.createHash('sha256').update(data).digest('hex');
  assert.deepEqual(inspectIpaBinary(ipaPath), {
    binarySha256: expectedSha256,
    binaryBytes: data.length,
  });
  assert.deepEqual(
    verifyDeclaredIpaIdentity({
      binarySha256: expectedSha256,
      binaryBytes: data.length,
    }, ipaPath),
    {
      binarySha256: expectedSha256,
      binaryBytes: data.length,
    },
  );
  assert.throws(
    () => verifyDeclaredIpaIdentity({
      binarySha256: 'b'.repeat(64),
      binaryBytes: data.length,
    }, ipaPath),
    /binarySha256 does not match/,
  );
  assert.throws(
    () => verifyDeclaredIpaIdentity({
      binarySha256: expectedSha256,
      binaryBytes: data.length + 1,
    }, ipaPath),
    /binaryBytes does not match/,
  );

  const notZip = path.join(temp, 'not-zip.ipa');
  fs.writeFileSync(notZip, Buffer.from('not a zip archive', 'utf8'));
  assert.throws(() => inspectIpaBinary(notZip), /not a ZIP archive/);
  assert.throws(() => inspectIpaBinary(path.join(temp, 'missing.ipa')), /does not exist/);
  assert.throws(() => inspectIpaBinary(path.join(temp, 'candidate.zip')), /must point to an .ipa/);
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}

console.log('PASS: exact-build evidence is bound to the supplied IPA bytes');
