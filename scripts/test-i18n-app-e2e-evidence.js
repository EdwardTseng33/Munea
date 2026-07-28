'use strict';

const assert = require('node:assert');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  DATA_HANDLING_CHECKS,
  INSTALLED_APP_STEPS,
  PRODUCT_CHECKS,
  PURCHASE_STEPS,
  VOICE_STEPS,
  buildAppE2eWorklist,
  compileAppE2eEvidence,
} = require('./i18n-app-e2e-evidence.js');

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'munea-app-e2e-'));
const ipaPath = path.join(temp, 'candidate.ipa');
const ipaData = Buffer.concat([
  Buffer.from('504b0304', 'hex'),
  Buffer.from('munea-exact-app-e2e-build', 'utf8'),
]);
fs.writeFileSync(ipaPath, ipaData);

function complete(locale = 'en') {
  const worklist = buildAppE2eWorklist(locale);
  worklist.buildIdentity = {
    exactCommit: 'a'.repeat(40),
    binarySha256: crypto.createHash('sha256').update(ipaData).digest('hex'),
    binaryBytes: ipaData.length,
    appVersion: '1.0.45',
    build: '500',
  };
  worklist.run = {
    testedAt: '2026-07-28T12:00:00Z',
    testerReference: 'qa-ticket-001',
    evidenceReference: 'secure-evidence/i18n-run-001',
    profile: 'staging-gateway',
    environment: 'staging',
    device: 'iPhone-15-iOS-18.5',
    conversationLocale: locale,
    serviceRevisions: {
      brain: 'brain-staging-001',
      voice: 'voice-staging-001',
      gateway: 'gateway-staging-001',
      avatar: 'avatar-staging-001',
    },
    dataHandling: Object.fromEntries(
      DATA_HANDLING_CHECKS.map((field) => [field, true]),
    ),
  };
  worklist.installedApp.steps = Object.fromEntries(
    INSTALLED_APP_STEPS.map((field) => [field, true]),
  );
  worklist.voice.steps = Object.fromEntries(
    VOICE_STEPS.map((field) => [field, true]),
  );
  worklist.purchase.testedAt = '2026-07-28T12:20:00Z';
  worklist.purchase.backendRevision = 'brain-staging-001';
  worklist.purchase.steps = Object.fromEntries(
    PURCHASE_STEPS.map((field) => [field, true]),
  );
  worklist.purchase.products.forEach((product) => {
    product.result = 'pass';
    product.checks = Object.fromEntries(PRODUCT_CHECKS.map((field) => [field, true]));
  });
  return worklist;
}

try {
const completed = complete();
const evidence = compileAppE2eEvidence(completed, { ipaPath });
assert.equal(evidence.installed.schema, 'munea.i18n-installed-app-e2e.v1');
assert.equal(evidence.voice.schema, 'munea.i18n-voice-e2e.v1');
assert.equal(evidence.purchase.schema, 'munea.i18n-purchase-e2e.v1');
assert.equal(evidence.installed.exactCommit, evidence.voice.exactCommit);
assert.equal(evidence.voice.binarySha256, evidence.purchase.binarySha256);
assert.equal(evidence.purchase.products.length, 8);
assert.equal(evidence.purchase.backendRevision, evidence.installed.serviceRevisions.brain);
assert.equal(evidence.installed.binaryBytes, ipaData.length);

const incomplete = complete();
incomplete.installedApp.steps.avatarReady = false;
assert.throws(
  () => compileAppE2eEvidence(incomplete, { ipaPath }),
  /installedApp\.steps\.avatarReady must be true/,
);

const productMismatch = complete();
productMismatch.purchase.products.pop();
assert.throws(
  () => compileAppE2eEvidence(productMismatch, { ipaPath }),
  /all 8 current products/,
);

const revisionMismatch = complete();
revisionMismatch.purchase.backendRevision = 'different-brain-revision';
assert.throws(
  () => compileAppE2eEvidence(revisionMismatch, { ipaPath }),
  /must match run\.serviceRevisions\.brain/,
);

const sensitiveReference = complete();
sensitiveReference.run.testerReference = 'person@example.com';
assert.throws(
  () => compileAppE2eEvidence(sensitiveReference, { ipaPath }),
  /opaque, non-sensitive reference/,
);

const spanish = complete('es');
spanish.purchase.storeLocale = 'es-ES';
assert.throws(
  () => compileAppE2eEvidence(spanish, { ipaPath }),
  /Spanish App Store variant is not selected/,
);

const differentIpaPath = path.join(temp, 'different.ipa');
fs.writeFileSync(
  differentIpaPath,
  Buffer.concat([Buffer.from('504b0304', 'hex'), Buffer.from('other-build')]),
);
assert.throws(
  () => compileAppE2eEvidence(complete(), { ipaPath: differentIpaPath }),
  /binarySha256 does not match/,
);

console.log('PASS: App E2E compiler requires exact-build call, voice, and 8-product evidence');
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
