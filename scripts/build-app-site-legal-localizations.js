'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SOURCE_ROOT = path.join(ROOT, 'web', 'legal');
const OUTPUT_ROOT = path.join(ROOT, 'app-site', 'legal');
const SOURCE_CSS = path.join(ROOT, 'web', 'src', 'legal.css');
const PAGE_KINDS = ['privacy', 'terms', 'support'];
const PUBLIC_LOCALES = ['en', 'ja', 'es'];

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function canonicalUrl(locale, pageKind) {
  return `https://app.munea.net/legal/${locale}/${pageKind}.html`;
}

function transformHtml(html, locale, pageKind, legalReview) {
  const canonical = canonicalUrl(locale, pageKind);
  const robots = legalReview === 'approved' ? 'index,follow' : 'noindex,nofollow';
  const metadata = [
    `  <link rel="canonical" href="${canonical}" />`,
    `  <meta name="robots" content="${robots}" />`,
  ].join('\n');
  const transformed = html
    .replace(
      '  <link rel="stylesheet" href="../../src/styles.css" />\n'
        + '  <link rel="stylesheet" href="../../src/legal.css" />',
      '  <link rel="stylesheet" href="../../warm.css" />\n'
        + '  <link rel="stylesheet" href="../legal.css" />',
    )
    .replace('</head>', `${metadata}\n</head>`);
  if (transformed === html || !transformed.includes(canonical)) {
    throw new Error(`Could not transform public legal page: ${locale}/${pageKind}`);
  }
  return transformed;
}

function buildOutputs() {
  const manifest = readJson(path.join(SOURCE_ROOT, 'manifest.json'));
  const outputs = new Map();
  outputs.set(
    path.join(OUTPUT_ROOT, 'legal.css'),
    fs.readFileSync(SOURCE_CSS, 'utf8'),
  );
  for (const locale of PUBLIC_LOCALES) {
    const localeConfig = manifest.locales[locale];
    if (!localeConfig) throw new Error(`Missing legal locale: ${locale}`);
    for (const pageKind of PAGE_KINDS) {
      const sourcePath = path.resolve(SOURCE_ROOT, localeConfig.pages[pageKind]);
      const html = fs.readFileSync(sourcePath, 'utf8');
      outputs.set(
        path.join(OUTPUT_ROOT, locale, `${pageKind}.html`),
        transformHtml(html, locale, pageKind, localeConfig.legalReview),
      );
    }
  }
  return outputs;
}

function writeOutputs(outputs = buildOutputs()) {
  for (const [filePath, content] of outputs) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, 'utf8');
  }
  return outputs.size;
}

if (require.main === module) {
  const count = writeOutputs();
  process.stdout.write(`Generated ${count} localized legal hosting assets.\n`);
}

module.exports = {
  buildOutputs,
  canonicalUrl,
  transformHtml,
  writeOutputs,
};
