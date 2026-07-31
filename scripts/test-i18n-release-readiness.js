'use strict';

const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const zlib = require('zlib');
const {
  buildReadiness,
  formatReport,
  validateEvidenceConsistency,
  validateInstalledAppEvidence,
  validateLocaleDataEvidence,
  validateMemberDataIsolationEvidence,
  validateNativeReviewEvidence,
  validatePurchaseEvidence,
  validateVisualEvidence,
  validateVoiceEvidence,
} = require('./i18n-release-readiness.js');
const { crc32 } = require('./i18n-visual-qa-evidence.js');
const {
  validateAppMetadata,
  validateIapCopy,
  validateRepositoryStoreAssets,
} = require('./app-store-metadata-limits.js');

function pngChunk(type, data) {
  const typeBytes = Buffer.from(type, 'ascii');
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([typeBytes, data])));
  return Buffer.concat([length, typeBytes, data, checksum]);
}

function validPng(width, height, uniqueByte) {
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

const report = buildReadiness();
const requiredLocales = ['zh-TW', 'en', 'ja', 'es'];
const requiredGates = [
  'catalogCoverage',
  'appUiIntegration',
  'sourceCopyMigration',
  'localeDataReadiness',
  'memberDataIsolation',
  'runtimeLocalization',
  'binaryLocalization',
  'nativeLanguageReview',
  'visualQA',
  'voiceIntegration',
  'voiceE2E',
  'regionalSafetyAndLegal',
  'appStoreTechnicalValidation',
  'appStoreMetadata',
  'inAppPurchaseLocalization',
  'appStoreScreenshots',
  'marketAvailability',
  'installedAppE2E',
  'purchaseE2E',
  'exactBuildEvidenceChain',
];

assert.equal(report.schema, 'munea.i18n-release-readiness.v1');
assert.equal(report.appAvailabilityAuthority, 'App Store Connect Pricing and Availability');
assert.deepEqual(Object.keys(report.locales), requiredLocales);
assert.equal(report.allReady, false, 'International release must remain closed until every gate passes');

for (const locale of requiredLocales) {
  const entry = report.locales[locale];
  assert.deepEqual(Object.keys(entry.gates), requiredGates, `${locale} gate inventory drifted`);
  assert.equal(entry.ready, false, `${locale} must not be release-ready without current evidence`);
  assert.equal(
    entry.gates.appUiIntegration.passed,
    true,
    `${locale} shipping App UI integration must stay complete`,
  );
  assert(
    !entry.blockers.some(({ gate }) => gate === 'appUiIntegration'),
    `${locale} must not report a completed App UI integration as blocked`,
  );
  assert.equal(
    entry.gates.catalogCoverage.evidence,
    'web/src/i18n/review-manifest.json + web/src/i18n/app-surface-copy-manifest.json',
    `${locale} catalog coverage gate must include the complete App surface copy mapping`,
  );
  assert.equal(
    entry.gates.appUiIntegration.evidence,
    'web/src/i18n/app-screen-manifest.json + web/src/i18n/app-binding-manifest.json + web/src/i18n/app-surface-manifest.json',
    `${locale} App integration gate must include the complete shipping surface manifest`,
  );
  // 2026-07-31 文案搬遷歸零：這關從「必須還在擋」反轉成「必須是綠的」。
  // 再變紅＝有人加了沒綁鍵的新文案（worklist 契約會一起亮）。
  assert(
    !entry.blockers.some(({ gate }) => gate === 'sourceCopyMigration'),
    `${locale} source copy migration reached zero on 2026-07-31 and must stay green`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'localeDataReadiness'),
    `${locale} must require a redacted production LocaleContext data audit`,
  );
  assert.equal(
    entry.gates.localeDataReadiness.evidence,
    'docs/LOCALE-CONTEXT-DATA-READINESS.json + docs/qa/i18n/locale-context-data-audit.json',
    `${locale} locale data gate must use the canonical zero-write audit evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'memberDataIsolation'),
    `${locale} must require a real two-tenant staging isolation E2E`,
  );
  assert.equal(
    entry.gates.memberDataIsolation.evidence,
    'docs/MEMBER-DATA-ISOLATION-READINESS.json + docs/qa/i18n/member-data-isolation-e2e.json',
    `${locale} member security gate must cover RLS and Brain service-role paths`,
  );
  assert.equal(
    entry.gates.sourceCopyMigration.evidence,
    'docs/I18N-SURFACE-INVENTORY.json + docs/I18N-NON-USER-FACING-REVIEW.json + scripts/i18n-surface-inventory.js',
    `${locale} source-copy gate must use the shipping surface scanner`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'nativeLanguageReview'),
    `${locale} must require current catalog-bound native review evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'installedAppE2E'),
    `${locale} must require exact installed-App evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'visualQA'),
    `${locale} must require current visual evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'voiceIntegration'),
    `${locale} must require trusted Gateway and Live Voice locale integration`,
  );
  assert.equal(
    entry.gates.voiceIntegration.evidence,
    'engine/voice-locale-integration-manifest.json',
    `${locale} voice integration gate must use the canonical manifest`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'inAppPurchaseLocalization'),
    `${locale} must require current IAP localization and product evidence`,
  );
  assert.equal(
    entry.gates.appStoreTechnicalValidation.passed,
    true,
    `${locale} prepared App Store and IAP copy must satisfy Apple's technical limits`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'purchaseE2E'),
    `${locale} must require exact installed-App StoreKit evidence`,
  );
  assert(
    entry.blockers.some(({ gate }) => gate === 'exactBuildEvidenceChain'),
    `${locale} must require one consistent exact-build evidence chain`,
  );
  assert.equal(
    entry.gates.nativeLanguageReview.evidence,
    `docs/qa/i18n/${locale}/native-review.json`,
    `${locale} native review evidence must use the canonical path`,
  );
  assert.equal(
    entry.gates.visualQA.evidence,
    `docs/qa/i18n/${locale}/visual-qa.json`,
    `${locale} visual evidence must use the canonical path`,
  );
  assert.equal(
    entry.gates.voiceE2E.evidence,
    `docs/qa/i18n/${locale}/voice-e2e.json`,
    `${locale} voice evidence must use the canonical path`,
  );
}

for (const locale of ['en', 'ja', 'es']) {
  const entry = report.locales[locale];
  assert.equal(entry.gates.runtimeLocalization.passed, false);
  assert.equal(entry.gates.appUiIntegration.passed, true);
  // 2026-07-31 歸零後：搬遷關對三語一樣轉綠（其餘關卡照舊擋著、語系開關仍未開）
  assert.equal(entry.gates.sourceCopyMigration.passed, true);
  assert.equal(entry.gates.voiceIntegration.passed, false);
  assert.equal(entry.gates.binaryLocalization.passed, false);
  assert.equal(entry.gates.appStoreScreenshots.passed, false);
  assert.equal(entry.gates.inAppPurchaseLocalization.passed, false);
  assert.equal(entry.gates.marketAvailability.passed, false);
}

assert.equal(report.locales.es.storeLocale, null, 'Spanish stays variant-based; the storefront locale lives in the selected variant');
assert.deepEqual(
  report.locales.es.selectedStoreVariants,
  ['es-ES'],
  '2026-07-30 decision: first Spanish market is Spain (es-ES); es-MX stays prepared but unselected',
);
assert.deepEqual(
  Object.keys(report.locales.es.candidateStoreVariants),
  ['es-ES', 'es-MX'],
);
for (const [variantKey, variant] of Object.entries(report.locales.es.candidateStoreVariants)) {
  assert.equal(variant.ready, false);
  assert.equal(
    variant.gates.selected,
    variantKey === 'es-ES',
    'only the decided es-ES variant may be selected',
  );
  assert.equal(variant.gates.metadata, false);
  assert.equal(variant.gates.publicUrls, false);
  assert.equal(variant.gates.screenshots, false);
  assert.equal(variant.gates.regionalLegal, false);
  assert.equal(variant.gates.iap, false);
  assert.equal(variant.gates.availability, false);
}
assert(
  report.generatedFrom.includes('web/src/i18n/app-surface-copy-manifest.json'),
  'Release readiness must include the complete App surface copy mapping',
);
assert(
  report.generatedFrom.includes('web/legal/regional-safety-policy.json'),
  'Release readiness must include country-specific Spanish safety policy',
);
assert(
  report.generatedFrom.includes('docs/I18N-NON-USER-FACING-REVIEW.json'),
  'Release readiness must include fail-closed internal-copy review evidence',
);
assert(
  report.generatedFrom.includes('docs/LOCALE-CONTEXT-DATA-READINESS.json'),
  'Release readiness must include explicit LocaleContext data readiness',
);
assert(
  report.generatedFrom.includes('docs/MEMBER-DATA-ISOLATION-READINESS.json'),
  'Release readiness must include two-tenant member data isolation',
);
assert(
  report.generatedFrom.includes('scripts/i18n-native-review-worklist.js'),
  'Release readiness must include the catalog-bound native review worklist',
);
assert(
  report.generatedFrom.includes('scripts/i18n-native-review-evidence.js'),
  'Release readiness must include the fail-closed native review evidence compiler',
);
assert(
  report.generatedFrom.includes('scripts/i18n-visual-qa-worklist.js'),
  'Release readiness must include the exact-build visual capture worklist',
);
assert(
  report.generatedFrom.includes('scripts/i18n-visual-qa-evidence.js'),
  'Release readiness must include the exact-build visual evidence compiler',
);
assert(
  report.generatedFrom.includes('scripts/app-store-metadata-limits.js'),
  'Release readiness must include App Store and IAP field-limit validation',
);
assert(
  formatReport(report).includes('Overall: NOT READY'),
  'Human-readable report must lead with the actual release state',
);

const storeTechnicalValidation = validateRepositoryStoreAssets();
assert.equal(
  storeTechnicalValidation.allValid,
  true,
  'Every prepared App Store locale and all eight IAP products must satisfy Apple limits',
);
const validMetadata = {
  name: 'Munea',
  subtitle: 'Voice companion',
  promotionalText: 'A familiar voice for everyday life.',
  description: 'Talk, remember, and stay connected.',
  keywords: 'voice,family,companion',
  privacyPolicyUrl: 'https://app.munea.net/privacy',
  supportUrl: 'https://app.munea.net/support',
};
assert.equal(validateAppMetadata(validMetadata).valid, true);
assert.equal(
  validateAppMetadata({ ...validMetadata, name: 'x'.repeat(31) }).valid,
  false,
  'An App name over 30 characters must fail closed',
);
assert.equal(
  validateAppMetadata({ ...validMetadata, keywords: 'a'.repeat(101) }).valid,
  false,
  'Keywords over 100 UTF-8 bytes must fail closed',
);
assert.equal(
  validateAppMetadata({ ...validMetadata, description: '<b>Not plain text</b>' }).valid,
  false,
  'HTML in the App Store description must fail closed',
);
const sampleProducts = {
  'net.munea.sample': {
    displayName: 'Munea Sample',
    description: 'A valid sample purchase',
  },
};
assert.equal(validateIapCopy(sampleProducts, ['net.munea.sample']).valid, true);
assert.equal(
  validateIapCopy({
    'net.munea.sample': {
      ...sampleProducts['net.munea.sample'],
      description: 'x'.repeat(46),
    },
  }, ['net.munea.sample']).valid,
  false,
  'An IAP description over 45 characters must fail closed',
);
assert.equal(
  validateIapCopy({}, ['net.munea.sample']).valid,
  false,
  'Missing IAP products must fail closed',
);

const exactCommit = 'a'.repeat(40);
const evidenceReferenceTime = '2026-07-28T12:00:00Z';
const localeDataManifest = {
  requiredEvidence: {
    environment: 'production',
    captureMode: 'read-only-redacted-export',
    writesPerformed: false,
    minimumActiveRecords: 1,
    explicitCoverage: 1,
    invalidActiveRecords: 0,
    accountIsolationFailures: 0,
    exportIssueCount: 0,
    containsDirectIdentifiers: false,
    containsNames: false,
    containsContactDetails: false,
    recordReferencesAreOrdinalOnly: true,
    maximumAgeHours: 24,
  },
};
const localeDataEvidence = {
  schema: 'munea.locale-context-data-audit.v1',
  result: 'pass',
  sourceCommit: exactCommit,
  generatedAt: '2026-07-28T08:00:00Z',
  sourceExport: {
    schema: 'munea.locale-context-data-export.v1',
    sourceCommit: exactCommit,
    generatedAt: '2026-07-28T07:55:00Z',
    environment: 'production',
    captureMode: 'read-only-redacted-export',
    writesPerformed: false,
  },
  summary: {
    recordCount: 1,
    activeRecordCount: 1,
    completeActiveRecords: 1,
    invalidActiveRecords: 0,
    invalidInactiveRecords: 0,
    accountIsolationFailures: 0,
    explicitCoverage: 1,
    exportIssueCount: 0,
  },
  outputPrivacy: {
    containsDirectIdentifiers: false,
    containsNames: false,
    containsContactDetails: false,
    recordReferencesAreOrdinalOnly: true,
  },
  exportIssues: [],
  records: [{
    record: 'record-0001',
    active: true,
    status: 'complete',
    issues: [],
  }],
};
assert.equal(
  validateLocaleDataEvidence(
    localeDataEvidence,
    localeDataManifest,
    evidenceReferenceTime,
  ),
  true,
);
assert.equal(
  validateLocaleDataEvidence(
    {
      ...localeDataEvidence,
      summary: {
        ...localeDataEvidence.summary,
        accountIsolationFailures: 1,
      },
    },
    localeDataManifest,
    evidenceReferenceTime,
  ),
  false,
  'Cross-account LocaleContext evidence must fail closed',
);
assert.equal(
  validateLocaleDataEvidence(
    {
      ...localeDataEvidence,
      outputPrivacy: {
        ...localeDataEvidence.outputPrivacy,
        containsDirectIdentifiers: true,
      },
    },
    localeDataManifest,
    evidenceReferenceTime,
  ),
  false,
  'LocaleContext release evidence must remain identifier-free',
);
assert.equal(
  validateLocaleDataEvidence(
    {
      ...localeDataEvidence,
      generatedAt: '2026-07-26T08:00:00Z',
      sourceExport: {
        ...localeDataEvidence.sourceExport,
        generatedAt: '2026-07-26T07:55:00Z',
      },
    },
    localeDataManifest,
    evidenceReferenceTime,
  ),
  false,
  'Stale production LocaleContext evidence must expire',
);
const memberDataIsolationManifest = {
  requiredEvidence: {
    environment: 'staging',
    captureMode: 'read-only-preprovisioned-two-tenant',
    realMemberDataUsed: false,
    productionWritesPerformed: false,
    fixtureAccounts: 2,
    fixtureLifecycleReviewed: true,
    containsSecrets: false,
    containsPersonalData: false,
    maximumAgeHours: 24,
  },
  requiredScenarios: [
    'ownAccountReadable',
    'otherAccountPersonDeniedByRls',
    'otherAccountPersonDeniedByBrain',
    'otherAccountFamilyDeniedByBrain',
    'clientTenantOverrideDenied',
    'removedMemberDenied',
    'unknownUserDenied',
    'fixtureLifecycleReviewed',
  ],
  requiredChecks: [
    { name: 'staging_release_identity', allowedStatusCodes: [200], commitMatched: true },
    { name: 'tenant_a_reads_own_person_via_rls', allowedStatusCodes: [200], rowCount: 1 },
    { name: 'tenant_b_reads_own_person_via_rls', allowedStatusCodes: [200], rowCount: 1 },
    {
      name: 'tenant_a_cannot_read_tenant_b_person_via_rls',
      allowedStatusCodes: [200],
      rowCount: 0,
    },
    {
      name: 'tenant_b_cannot_read_tenant_a_person_via_rls',
      allowedStatusCodes: [200],
      rowCount: 0,
    },
    { name: 'tenant_a_reads_own_person_via_brain', allowedStatusCodes: [200] },
    { name: 'tenant_b_reads_own_person_via_brain', allowedStatusCodes: [200] },
    {
      name: 'tenant_a_cannot_read_tenant_b_person_via_brain',
      allowedStatusCodes: [403],
    },
    {
      name: 'tenant_b_cannot_read_tenant_a_person_via_brain',
      allowedStatusCodes: [403],
    },
    {
      name: 'tenant_a_cannot_read_tenant_b_family_via_brain',
      allowedStatusCodes: [403],
    },
    {
      name: 'tenant_b_cannot_read_tenant_a_family_via_brain',
      allowedStatusCodes: [403],
    },
    { name: 'client_tenant_override_denied', allowedStatusCodes: [403] },
    { name: 'removed_member_denied', allowedStatusCodes: [403] },
    { name: 'unknown_user_denied', allowedStatusCodes: [200, 401, 403] },
  ],
};
const memberDataIsolationEvidence = {
  schema: 'munea.member-data-isolation-e2e.v1',
  result: 'pass',
  exactCommit,
  testedAt: '2026-07-28T08:00:00Z',
  environment: 'staging',
  captureMode: 'read-only-preprovisioned-two-tenant',
  realMemberDataUsed: false,
  productionWritesPerformed: false,
  fixtureAccounts: 2,
  fixtureLifecycleReviewed: true,
  containsSecrets: false,
  containsPersonalData: false,
  stagingIdentitySchema: 'munea.service-release.v1',
  stagingService: 'brain',
  stagingEnvironment: 'staging',
  stagingCommit: exactCommit,
  stagingRevision: 'brain-staging-revision',
  stagingProjectRef: 'abcdefghijklmnopqrst',
  evidenceReference: 'staging-security-run-001',
  fixtureLifecycleReference: 'staging-fixtures-001',
  scenarios: Object.fromEntries(
    memberDataIsolationManifest.requiredScenarios.map((scenario) => [scenario, true]),
  ),
  checks: memberDataIsolationManifest.requiredChecks.map((contract) => ({
    name: contract.name,
    result: 'pass',
    statusCode: contract.allowedStatusCodes[0],
    ...(Object.hasOwn(contract, 'rowCount') ? { rowCount: contract.rowCount } : {}),
    ...(Object.hasOwn(contract, 'commitMatched')
      ? { commitMatched: contract.commitMatched }
      : {}),
  })),
  scope: {
    directSupabaseRls: true,
    brainServiceRoleAuthorization: true,
    writesAttempted: false,
    productionTargetsForbidden: true,
    responsePayloadsStored: false,
  },
};
const validateIsolationEvidence = (evidence) => validateMemberDataIsolationEvidence(
  evidence,
  memberDataIsolationManifest,
  evidenceReferenceTime,
);
assert.equal(
  validateIsolationEvidence(memberDataIsolationEvidence),
  true,
);
assert.equal(
  validateIsolationEvidence(
    {
      ...memberDataIsolationEvidence,
      scenarios: {
        ...memberDataIsolationEvidence.scenarios,
        otherAccountPersonDeniedByBrain: false,
      },
    },
  ),
  false,
  'A service-role BOLA path must keep international release blocked',
);
assert.equal(
  validateIsolationEvidence(
    {
      ...memberDataIsolationEvidence,
      stagingCommit: 'b'.repeat(40),
    },
  ),
  false,
  'Isolation evidence must be bound to the Brain commit returned by staging',
);
assert.equal(
  validateIsolationEvidence(
    {
      ...memberDataIsolationEvidence,
      checks: memberDataIsolationEvidence.checks.slice(1),
    },
  ),
  false,
  'Isolation evidence must include every required RLS and Brain check',
);
assert.equal(
  validateIsolationEvidence(
    {
      ...memberDataIsolationEvidence,
      stagingRevision: 'unknown',
    },
  ),
  false,
  'An unknown staging revision cannot satisfy the isolation gate',
);
assert.equal(
  validateIsolationEvidence(
    {
      ...memberDataIsolationEvidence,
      stagingProjectRef: 'fespbkdwafueyonppzwq',
    },
  ),
  false,
  'Production Supabase evidence must never satisfy the staging isolation gate',
);
assert.equal(
  validateIsolationEvidence({
    ...memberDataIsolationEvidence,
    testedAt: '2026-07-26T08:00:00Z',
  }),
  false,
  'Stale two-tenant isolation evidence must expire',
);
const enCatalogPath = path.join(__dirname, '..', 'web', 'src', 'i18n', 'en.json');
const enCatalogSource = fs.readFileSync(enCatalogPath, 'utf8');
const enCatalogKeys = Object.keys(JSON.parse(enCatalogSource)).sort();
const nativeReviewEvidence = {
  schema: 'munea.i18n-native-review.v1',
  locale: 'en',
  contentVariant: 'international-English',
  result: 'pass',
  exactCommit,
  reviewedAt: '2026-07-28T08:00:00Z',
  reviewerReference: 'review-ticket-001',
  reviewerRole: 'native-language-reviewer',
  catalogSha256: crypto.createHash('sha256').update(enCatalogSource).digest('hex'),
  reviewedKeyCount: enCatalogKeys.length,
  reviewedKeysSha256: crypto.createHash('sha256').update(enCatalogKeys.join('\n')).digest('hex'),
  openIssues: 0,
  checks: Object.fromEntries([
    'meaningPreserved',
    'grammarNatural',
    'toneAppropriate',
    'culturalContextAccepted',
    'placeholderContextAccepted',
    'spokenCopyReadAloud',
  ].map((key) => [key, true])),
};
assert.equal(
  validateNativeReviewEvidence(
    nativeReviewEvidence,
    'en',
    enCatalogPath,
    'international-English',
  ),
  true,
);
assert.equal(
  validateNativeReviewEvidence(
    { ...nativeReviewEvidence, catalogSha256: '0'.repeat(64) },
    'en',
    enCatalogPath,
    'international-English',
  ),
  false,
  'Native review must expire when the reviewed catalog bytes differ',
);
const serviceRevisions = {
  brain: 'brain-revision',
  voice: 'voice-revision',
  gateway: 'gateway-revision',
  avatar: 'avatar-revision',
};
const voiceEvidence = {
  schema: 'munea.i18n-voice-e2e.v1',
  locale: 'en',
  result: 'pass',
  exactCommit,
  binarySha256: 'b'.repeat(64),
  binaryBytes: 60000000,
  testedAt: '2026-07-28T08:00:00Z',
  appVersion: '1.0.45',
  build: '49',
  profile: 'staging-gateway',
  environment: 'staging',
  device: 'iPhone acceptance device',
  conversationLocale: 'en',
  serviceRevisions,
  steps: {
    openingInLocale: true,
    microphoneAudioUnderstood: true,
    assistantResponseAudible: true,
    assistantResponseVisible: true,
    mixedLanguageTurn: true,
    temporaryVoiceSwitch: true,
    permanentPreferenceConfirmed: true,
  },
};
assert.equal(validateVoiceEvidence(voiceEvidence, 'en'), true);
assert.equal(
  validateVoiceEvidence({ ...voiceEvidence, steps: { openingInLocale: true } }, 'en'),
  false,
  'A partial voice flow must not pass',
);

const installedEvidence = {
  schema: 'munea.i18n-installed-app-e2e.v1',
  locale: 'en',
  result: 'pass',
  exactCommit,
  binarySha256: 'b'.repeat(64),
  binaryBytes: 60000000,
  testedAt: '2026-07-28T08:00:00Z',
  appVersion: '1.0.45',
  build: '49',
  profile: 'staging-gateway',
  environment: 'staging',
  device: 'iPhone acceptance device',
  runtimeIdentity: {
    schema: 'munea.ios-build-identity.v1',
    bundleIdentifier: 'net.munea.app',
    exactCommit,
    appVersion: '1.0.45',
    build: '49',
  },
  serviceRevisions,
  steps: Object.fromEntries([
    'callButtonTapped',
    'microphoneGranted',
    'authPassed',
    'accountBootstrapPassed',
    'creditsPassed',
    'gatewayLeaseAcquired',
    'voiceReady',
    'avatarReady',
    'openingHeard',
    'microphoneAudioSent',
    'assistantResponseAudible',
    'assistantResponseVisible',
    'hangupReleasedCapacity',
  ].map((key) => [key, true])),
};
assert.equal(validateInstalledAppEvidence(installedEvidence, 'en'), true);
assert.equal(
  validateInstalledAppEvidence({ ...installedEvidence, binarySha256: 'unknown' }, 'en'),
  false,
  'Installed App evidence must identify the exact binary',
);
assert.equal(
  validateInstalledAppEvidence({ ...installedEvidence, binaryBytes: null }, 'en'),
  false,
  'Installed App evidence must include the exact IPA byte size',
);
assert.equal(
  validateInstalledAppEvidence({
    ...installedEvidence,
    runtimeIdentity: {
      ...installedEvidence.runtimeIdentity,
      build: '50',
    },
  }, 'en'),
  false,
  'Installed App runtime identity must match the candidate build',
);

const purchaseProductIds = [
  'net.munea.app.plus.monthly',
  'net.munea.app.plus.yearly',
  'net.munea.app.pro.monthly',
  'net.munea.app.pro.yearly',
  'net.munea.app.points.200',
  'net.munea.app.points.500',
  'net.munea.app.points.1000',
  'net.munea.app.points.1800',
];
const purchaseEvidence = {
  schema: 'munea.i18n-purchase-e2e.v1',
  locale: 'en',
  result: 'pass',
  exactCommit,
  binarySha256: 'c'.repeat(64),
  binaryBytes: 60000000,
  testedAt: '2026-07-28T08:00:00Z',
  appVersion: '1.0.45',
  build: '49',
  profile: 'sandbox-gateway',
  environment: 'sandbox',
  device: 'iPhone acceptance device',
  storeLocale: 'en-US',
  backendRevision: 'brain-revision',
  steps: Object.fromEntries([
    'signedIn',
    'storeProductsLoaded',
    'freeMemberPointPurchaseBlocked',
    'cancelPathCreatedNoEntitlement',
    'unverifiedPathCreatedNoEntitlement',
    'activeSubscriptionRestorePassed',
  ].map((key) => [key, true])),
  products: purchaseProductIds.map((productId) => ({
    productId,
    result: 'pass',
    checks: Object.fromEntries([
      'localizedNameMatched',
      'storeKitPriceDisplayed',
      'purchaseSheetOpened',
      'serverTransactionVerified',
      'entitlementApplied',
      'transactionFinished',
      'postPurchaseStateRefreshed',
    ].map((key) => [key, true])),
  })),
};
assert.equal(validatePurchaseEvidence(purchaseEvidence, 'en', purchaseProductIds), true);
assert.equal(
  validatePurchaseEvidence(
    { ...purchaseEvidence, products: purchaseEvidence.products.slice(0, 7) },
    'en',
    purchaseProductIds,
  ),
  false,
  'Purchase evidence must cover the exact 8-product set',
);

const consistentVisualEvidence = {
  schema: 'munea.i18n-visual-qa.v1',
  locale: 'en',
  result: 'pass',
  captureCommit: exactCommit,
  binarySha256: installedEvidence.binarySha256,
  binaryBytes: installedEvidence.binaryBytes,
  capturedAt: '2026-07-28T08:00:00Z',
  appVersion: installedEvidence.appVersion,
  build: installedEvidence.build,
};
assert.equal(
  validateEvidenceConsistency({
    visual: consistentVisualEvidence,
    voice: { ...voiceEvidence, appVersion: installedEvidence.appVersion, build: installedEvidence.build },
    installed: installedEvidence,
    purchase: {
      ...purchaseEvidence,
      appVersion: installedEvidence.appVersion,
      build: installedEvidence.build,
      binarySha256: installedEvidence.binarySha256,
      backendRevision: installedEvidence.serviceRevisions.brain,
    },
  }),
  true,
  'One exact build and service revision chain must pass',
);
assert.equal(
  validateEvidenceConsistency({
    visual: consistentVisualEvidence,
    voice: { ...voiceEvidence, appVersion: installedEvidence.appVersion, build: installedEvidence.build },
    installed: installedEvidence,
    purchase: {
      ...purchaseEvidence,
      exactCommit: 'd'.repeat(40),
      appVersion: installedEvidence.appVersion,
      build: installedEvidence.build,
      binarySha256: installedEvidence.binarySha256,
      backendRevision: installedEvidence.serviceRevisions.brain,
    },
  }),
  false,
  'Evidence from a different source commit must not be combined',
);
assert.equal(
  validateEvidenceConsistency({
    visual: consistentVisualEvidence,
    voice: { ...voiceEvidence, appVersion: installedEvidence.appVersion, build: installedEvidence.build },
    installed: installedEvidence,
    purchase: {
      ...purchaseEvidence,
      appVersion: installedEvidence.appVersion,
      build: installedEvidence.build,
      binarySha256: installedEvidence.binarySha256,
      binaryBytes: installedEvidence.binaryBytes + 1,
      backendRevision: installedEvidence.serviceRevisions.brain,
    },
  }),
  false,
  'Evidence with a different IPA byte size must not be combined',
);

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'munea-i18n-visual-'));
try {
  const visualEvidencePath = path.join(tempDir, 'visual-qa.json');
  const profileSpecs = [
    ['iphone-small-standard', 375, 667],
    ['iphone-standard', 390, 844],
    ['iphone-dynamic-type-large', 390, 844],
  ];
  const captures = profileSpecs.map(([profile, width, height], index) => {
    const pngEvidence = validPng(width, height, index);
    const screenshot = `home-${profile}.png`;
    fs.writeFileSync(path.join(tempDir, screenshot), pngEvidence);
    return {
      profile,
      screenshot,
      sha256: crypto.createHash('sha256').update(pngEvidence).digest('hex'),
      result: 'pass',
      checks: {
        noOverflow: true,
        noClipping: true,
        noUntranslatedCopy: true,
        layoutAccepted: true,
      },
    };
  });
  const visualEvidence = {
    schema: 'munea.i18n-visual-qa.v1',
    locale: 'en',
    result: 'pass',
    captureCommit: exactCommit,
    binarySha256: installedEvidence.binarySha256,
    binaryBytes: installedEvidence.binaryBytes,
    capturedAt: '2026-07-28T08:00:00Z',
    appVersion: '1.0.45',
    build: '49',
    profiles: profileSpecs.map(([profile]) => profile),
    screens: [{
      state: 'home',
      result: 'pass',
      captures,
    }],
  };
  assert.equal(
    validateVisualEvidence(visualEvidence, 'en', visualEvidencePath, ['home']),
    true,
  );
  const corruptScreenshotPath = path.join(tempDir, captures[0].screenshot);
  const originalScreenshot = fs.readFileSync(corruptScreenshotPath);
  const corruptScreenshot = Buffer.from(originalScreenshot);
  corruptScreenshot[corruptScreenshot.length - 1] ^= 0xff;
  fs.writeFileSync(corruptScreenshotPath, corruptScreenshot);
  assert.equal(
    validateVisualEvidence(visualEvidence, 'en', visualEvidencePath, ['home']),
    false,
    'Release readiness must reject malformed PNG evidence even when JSON is hand-written',
  );
  fs.writeFileSync(corruptScreenshotPath, originalScreenshot);
  assert.equal(
    validateVisualEvidence(
      { ...visualEvidence, binarySha256: 'unknown' },
      'en',
      visualEvidencePath,
      ['home'],
    ),
    false,
    'Visual evidence must identify the exact installed binary',
  );
  assert.equal(
    validateVisualEvidence(
      {
        ...visualEvidence,
        screens: [{
          ...visualEvidence.screens[0],
          captures: [
            { ...captures[0], screenshot: '../escape.png' },
            ...captures.slice(1),
          ],
        }],
      },
      'en',
      visualEvidencePath,
      ['home'],
    ),
    false,
    'Visual evidence must not reference screenshots outside its evidence directory',
  );
  assert.equal(
    validateVisualEvidence(
      {
        ...visualEvidence,
        screens: [{
          ...visualEvidence.screens[0],
          captures: captures.slice(0, 2),
        }],
      },
      'en',
      visualEvidencePath,
      ['home'],
    ),
    false,
    'Every App state must have all three real visual profiles',
  );
  const duplicateScreenshot = 'home-duplicate.png';
  fs.copyFileSync(
    path.join(tempDir, captures[0].screenshot),
    path.join(tempDir, duplicateScreenshot),
  );
  assert.equal(
    validateVisualEvidence(
      {
        ...visualEvidence,
        screens: [{
          ...visualEvidence.screens[0],
          captures: [
            captures[0],
            {
              ...captures[1],
              screenshot: duplicateScreenshot,
              sha256: captures[0].sha256,
            },
            captures[2],
          ],
        }],
      },
      'en',
      visualEvidencePath,
      ['home'],
    ),
    false,
    'Copied screenshot bytes must not be reused for another state or profile',
  );
} finally {
  fs.rmSync(tempDir, { recursive: true, force: true });
}

console.log('PASS: i18n release readiness stays evidence-gated');
