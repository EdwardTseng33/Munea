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
  /* "區塊註解不算" */
  const english = "Save";
`);
assert.deepEqual(
  jsCandidates.map((item) => item.text),
  ['儲存成功', '你好，${name}'],
  'JavaScript scanner should keep localized literals and ignore comments',
);

const htmlCandidates = scanHtml(`
  <!-- <p>註解不算</p> -->
  <style>.button::before { content: "裝飾不算"; }</style>
  <h1>設定</h1>
  <button aria-label="返回">←</button>
  <script>const toast = '完成'; // '忽略'</script>
`);
assert.deepEqual(
  htmlCandidates.map((item) => item.text),
  ['完成', '返回', '設定'],
  'HTML scanner should cover inline scripts, localizable attributes, and text nodes',
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

const report = buildReport(inventory);
const missingFiles = report.surfaces.flatMap((surface) => surface.missingFiles);
assert.deepEqual(missingFiles, [], `Every inventory file must exist: ${missingFiles.join(', ')}`);
assert.ok(
  report.surfaces.find((surface) => surface.id === 'app-webview').hanCandidates > 0,
  'The baseline must expose the App WebView localization debt',
);
assert.deepEqual(validateReport(report), [], 'The checked-in baseline must not regress');

console.log('PASS: i18n surface inventory contract');
