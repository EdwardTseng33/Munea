'use strict';

const assert = require('assert');
const {
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
  const unknown = t('missing.catalog.key', '未翻譯');
  /* "區塊註解不算" */
  const english = "Save";
`);
assert.deepEqual(
  jsCandidates.map((item) => item.text),
  ['儲存成功', '你好，${name}', '儲存', '取消', '未翻譯'],
  'JavaScript scanner should keep localized literals and ignore comments',
);
assert.deepEqual(
  jsCandidates.map((item) => item.bindingStatus),
  ['unbound', 'unbound', 'bound', 'bound', 'unbound'],
  'Only fallback literals attached to catalog-complete keys may be classified as bound',
);
assert.deepEqual(
  jsCandidates.filter((item) => item.bindingStatus === 'bound').map((item) => item.bindingKey),
  ['common.save', 'common.cancel'],
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

const inventory = loadInventory();
assert.deepEqual(
  inventory.requiredLocales,
  ['zh-TW', 'en', 'ja', 'es'],
  'The delivery inventory must cover the four approved locales',
);
assert.ok(
  inventory.surfaces.some((surface) => surface.id === 'operations-admin'),
  'The operations admin must be included in the delivery scope',
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
assert.ok(
  appWebView.unboundHanCandidates > 0,
  'The App must remain blocked while unbound localized copy exists',
);
assert.equal(
  appWebView.boundHanCandidates + appWebView.unboundHanCandidates,
  appWebView.hanCandidates,
);
assert.deepEqual(validateReport(report), [], 'The checked-in baseline must not regress');

console.log('PASS: i18n surface inventory contract');
