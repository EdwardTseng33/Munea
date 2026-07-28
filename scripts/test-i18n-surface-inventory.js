'use strict';

const assert = require('assert');
const {
  applyStaticLocalizedAssetBinding,
  buildReport,
  loadInventory,
  scanHtml,
  scanJavaScript,
  validateReport,
} = require('./i18n-surface-inventory.js');

const jsCandidates = scanJavaScript(`
  // const ignored = '註解不算';
  const visible = '儲存成功';
  const template = \`你好，\${name}\`;
  const bound = t('common.save', '儲存');
  const direct = window.MuneaI18n.t('common.cancel', null, '取消');
  const legacy = localizedFallback('medication.slot.bedtime', '睡前');
  const unknown = t('missing.catalog.key', '未翻譯');
  /* "區塊註解不算" */
  const english = "Save";
`);
assert.deepEqual(
  jsCandidates.map((item) => item.text),
  ['儲存成功', '你好，${name}', '儲存', '取消', '睡前', '未翻譯'],
  'JavaScript scanner should keep localized literals and ignore comments',
);
assert.deepEqual(
  jsCandidates.map((item) => item.bindingStatus),
  ['unbound', 'unbound', 'bound', 'bound', 'bound', 'unbound'],
  'Only fallback literals attached to catalog-complete keys may be classified as bound',
);
assert.deepEqual(
  jsCandidates.filter((item) => item.bindingStatus === 'bound').map((item) => item.bindingKey),
  ['common.save', 'common.cancel', 'medication.slot.bedtime'],
);

const htmlCandidates = scanHtml(`
  <!-- <p>註解不算</p> -->
  <style>.button::before { content: "裝飾不算"; }</style>
  <h1 data-i18n="settings.title">設定</h1>
  <button data-i18n-aria-label="common.save" aria-label="儲存">送出</button>
  <p data-i18n="missing.catalog.key">未翻譯</p>
  <script>const toast = '完成'; // '忽略'</script>
`);
assert.deepEqual(
  htmlCandidates.map((item) => item.text),
  ['完成', '儲存', '設定', '送出', '未翻譯'],
  'HTML scanner should cover inline scripts, localizable attributes, and text nodes',
);
assert.deepEqual(
  htmlCandidates.map((item) => item.bindingStatus),
  ['unbound', 'bound', 'bound', 'unbound', 'unbound'],
  'HTML bindings must be recognized only when their catalog key is complete',
);
const lateHanCandidate = scanHtml(
  `<script>const longCopy = '${'a'.repeat(180)}仍需翻譯';</script>`,
);
assert.equal(lateHanCandidate.length, 1, 'Han text after the preview limit must remain inventoried');
assert.match(lateHanCandidate[0].text, /仍需翻譯/, 'The audit preview must retain the Han evidence');
assert(lateHanCandidate[0].rawText.length > 180, 'The migration worklist must retain full source copy');

const inventory = loadInventory();
assert.deepEqual(
  inventory.requiredLocales,
  ['zh-TW', 'en', 'ja', 'es'],
  'The delivery inventory must cover the four approved locales',
);
const legalInventory = inventory.surfaces.find(
  (surface) => surface.id === 'legal-and-support',
);
const staticAssetCandidate = { bindingStatus: 'unbound' };
assert.deepEqual(
  applyStaticLocalizedAssetBinding(
    'web/privacy.html',
    [staticAssetCandidate],
    legalInventory.staticLocalizedAssets,
    inventory.requiredLocales,
  ),
  [],
  'A complete four-locale static legal asset may bind its Traditional Chinese source',
);
assert.equal(staticAssetCandidate.bindingStatus, 'bound');
assert.equal(staticAssetCandidate.bindingKey, 'static-asset:privacy');
const missingStaticAssetCandidate = { bindingStatus: 'unbound' };
assert.match(
  applyStaticLocalizedAssetBinding(
    'web/privacy.html',
    [missingStaticAssetCandidate],
    {
      ...legalInventory.staticLocalizedAssets,
      manifest: 'web/legal/missing-manifest.json',
    },
    inventory.requiredLocales,
  )[0],
  /missing or unsafe static localization manifest/,
);
assert.equal(
  missingStaticAssetCandidate.bindingStatus,
  'unbound',
  'A broken static localization bundle must fail closed',
);
assert.ok(
  inventory.surfaces.some((surface) => surface.id === 'operations-admin'),
  'The operations admin must be included in the delivery scope',
);
const marketingSite = inventory.surfaces.find(
  (surface) => surface.id === 'marketing-site',
);
assert.deepEqual(
  marketingSite.files,
  ['app-site/index.html'],
  'The marketing inventory must audit the Firebase-hosted public site',
);
assert.equal(
  marketingSite.baselineHanCandidates,
  195,
  'The public-site baseline must fail closed when new untranslated copy is added',
);
assert.ok(
  !inventory.surfaces.some((surface) => surface.files.includes('web/landing.html')),
  'The legacy internal landing prototype must not stand in for the deployed public site',
);
assert.ok(
  inventory.surfaces.some((surface) => surface.id === 'voice-and-gateway'),
  'The voice and Gateway path must be included in the delivery scope',
);
assert.ok(
  inventory.surfaces.some((surface) => surface.id === 'ios-and-store'),
  'The iOS binary and App Store must be included in the delivery scope',
);
assert.ok(
  inventory.surfaces
    .find((surface) => surface.id === 'ios-and-store')
    .requiredStates.includes('purchase-e2e'),
  'The App Store surface must include real-device purchase acceptance',
);

const report = buildReport(inventory);
const missingFiles = report.surfaces.flatMap((surface) => surface.missingFiles);
assert.deepEqual(missingFiles, [], `Every inventory file must exist: ${missingFiles.join(', ')}`);
assert.ok(
  report.surfaces.find((surface) => surface.id === 'app-webview').hanCandidates > 0,
  'The baseline must expose the App WebView localization debt',
);
const appWebView = report.surfaces.find((surface) => surface.id === 'app-webview');
assert.ok(appWebView.boundHanCandidates > 0, 'Catalog-bound fallback copy must remain auditable');
assert.equal(
  appWebView.reviewedNonUserFacingHanCandidates,
  8,
  'Only exact reviewed backend and legacy storage identities may be excluded from UI debt',
);
const companionProfile = appWebView.files.find(
  (file) => file.path === 'web/src/companion-profile.js',
);
assert.equal(companionProfile.boundHanCandidates, 12);
assert.equal(companionProfile.reviewedNonUserFacingHanCandidates, 7);
assert.equal(companionProfile.unboundHanCandidates, 0);
assert.deepEqual(companionProfile.reviewFailures, []);
const medication = appWebView.files.find(
  (file) => file.path === 'web/src/medication.js',
);
assert.equal(medication.boundHanCandidates, 4);
assert.equal(medication.reviewedNonUserFacingHanCandidates, 1);
assert.equal(medication.unboundHanCandidates, 0);
assert.deepEqual(medication.reviewFailures, []);
assert.ok(
  appWebView.unboundHanCandidates > 0,
  'The App must remain blocked while unbound localized copy exists',
);
assert.equal(
  appWebView.boundHanCandidates
    + appWebView.reviewedNonUserFacingHanCandidates
    + appWebView.unboundHanCandidates,
  appWebView.hanCandidates,
);
const legalAndSupport = report.surfaces.find(
  (surface) => surface.id === 'legal-and-support',
);
assert.ok(
  legalAndSupport.hanCandidates > 0,
  'The Traditional Chinese legal source must remain visible in the audit',
);
assert.equal(
  legalAndSupport.boundHanCandidates,
  legalAndSupport.hanCandidates,
  'Every legal source candidate must bind to a complete four-locale static asset bundle',
);
assert.equal(legalAndSupport.unboundHanCandidates, 0);
assert.deepEqual(legalAndSupport.reviewFailures, []);
for (const file of legalAndSupport.files) {
  assert.equal(file.boundHanCandidates, file.hanCandidates);
  assert.equal(file.unboundHanCandidates, 0);
  assert.ok(
    file.candidates.every(
      (candidate) => candidate.bindingType === 'localized-static-asset',
    ),
  );
}
const marketingReport = report.surfaces.find(
  (surface) => surface.id === 'marketing-site',
);
assert.equal(marketingReport.hanCandidates, 195);
assert.equal(marketingReport.unboundHanCandidates, 195);
assert.equal(marketingReport.files[0].path, 'app-site/index.html');
assert.deepEqual(validateReport(report), [], 'The checked-in baseline must not regress');

console.log('PASS: i18n surface inventory contract');
