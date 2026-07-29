'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {
  buildOutputs,
  canonicalUrl,
} = require('./build-app-site-legal-localizations.js');

const root = path.resolve(__dirname, '..');
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
    assert(
      html.includes('<meta name="robots" content="noindex,nofollow" />'),
      `${relativePath} must stay out of search until translation and legal review`,
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
