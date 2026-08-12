'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {
  buildOutputs,
  canonicalUrl,
} = require('./build-app-site-legal-localizations.js');

const root = path.resolve(__dirname, '..');
// 法律頁的核准狀態正本——搜尋引擎收錄與否要跟著它走，不要在測試裡寫死。
const legalManifest = JSON.parse(
  fs.readFileSync(path.join(root, 'web', 'legal', 'manifest.json'), 'utf8'),
);
const outputs = buildOutputs();
assert.equal(outputs.size, 10, 'Expected one shared stylesheet plus nine localized legal pages');

for (const [filePath, expected] of outputs) {
  assert(fs.existsSync(filePath), `Generated hosting asset is missing: ${filePath}`);
  assert.equal(
    fs.readFileSync(filePath, 'utf8'),
    expected,
    `Generated hosting asset drifted from its source: ${path.relative(root, filePath)}`,
  );
}

for (const locale of ['en', 'ja', 'es']) {
  const storeFile = locale === 'en' ? 'en-US.json' : locale === 'es' ? 'es-draft.json' : 'ja.json';
  const storeMetadata = JSON.parse(
    fs.readFileSync(path.join(root, 'app-store', 'localizations', storeFile), 'utf8'),
  );
  for (const pageKind of ['privacy', 'terms', 'support']) {
    const relativePath = `app-site/legal/${locale}/${pageKind}.html`;
    const html = fs.readFileSync(path.join(root, relativePath), 'utf8');
    assert(
      html.includes(`<link rel="canonical" href="${canonicalUrl(locale, pageKind)}" />`),
      `${relativePath} has the wrong canonical URL`,
    );
    // 搜尋引擎收錄要跟著「這個語系核准了沒」走，不是寫死。
    // 原本寫死 noindex——那是頁面還掛著「翻譯稿、尚未經法務確認」時的狀態。
    // 2026-07-31 Edward 核准三語法律頁發佈（見 web/legal/manifest.json 的 approvalBasis：
    // owner 具名核准、未經法律專業審查），生成工具就會產出 index,follow。
    // 寫死一邊 = 產品決定變了守門就紅，這是 7/29「守門清單跟不上程式」那條教訓的同一款。
    const approved = legalManifest.locales[locale].legalReview === 'approved';
    assert(
      html.includes(
        approved
          ? '<meta name="robots" content="index,follow" />'
          : '<meta name="robots" content="noindex,nofollow" />',
      ),
      approved
        ? `${relativePath} 已核准發佈，應該讓搜尋引擎收錄（index,follow）`
        : `${relativePath} 還沒核准，必須擋著搜尋引擎（noindex,nofollow）`,
    );
    assert(html.includes('href="../../warm.css"'), `${relativePath} must use the public-site theme`);
    assert(html.includes('href="../legal.css"'), `${relativePath} must use the shared legal layout`);
    assert(!html.includes('../../src/'), `${relativePath} references a non-hosted source asset`);
    assert(!/<script[\s>]/i.test(html), `${relativePath} must remain static and script-free`);
  }
  assert.equal(
    storeMetadata.privacyPolicyUrl,
    canonicalUrl(locale, 'privacy'),
    `${locale} App Store privacy URL must match the generated public page`,
  );
  assert.equal(
    storeMetadata.supportUrl,
    canonicalUrl(locale, 'support'),
    `${locale} App Store support URL must match the generated public page`,
  );
}

console.log('PASS: localized legal pages are reproducible Firebase hosting assets');
