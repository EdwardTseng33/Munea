'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(process.env.MUNEA_TEST_ROOT || path.join(__dirname, '..'));

function openingTagById(html, id) {
  const escapedId = id.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&');
  const match = html.match(new RegExp(`<[^>]+\\bid=["']${escapedId}["'][^>]*>`, 'u'));
  return match ? match[0] : '';
}

function classNames(openingTag) {
  const match = openingTag.match(/\bclass=["']([^"']*)["']/u);
  return new Set((match ? match[1] : '').split(/\s+/u).filter(Boolean));
}

function applyFontScaleSelector(appSource) {
  const start = appSource.indexOf('function applyFontScale()');
  const end = appSource.indexOf('window.__muneaApplyFontScale', start);
  assert.notEqual(start, -1, 'applyFontScale() must exist');
  assert.notEqual(end, -1, 'applyFontScale() test hook must exist');
  const source = appSource.slice(start, end);
  const selectors = [...source.matchAll(/querySelectorAll\(\s*(["'])(.*?)\1\s*\)/gu)]
    .map(match => match[2]);
  assert.ok(selectors.length, 'applyFontScale() must target at least one surface selector');
  return selectors.join(',');
}

function selectorCoversReaderSurface(selector, surfaceId) {
  return selector.split(',').some((rawPart) => {
    const part = rawPart.trim();
    return (
      part === '.reader-page'
      || part.startsWith('.reader-page ')
      || part === `#${surfaceId}`
      || part.startsWith(`#${surfaceId} `)
      || part.includes('[data-font-scale')
    );
  });
}

function assessSurface({ html, appSource, surfaceId }) {
  const tag = openingTagById(html, surfaceId);
  assert.ok(tag, `${surfaceId} must exist`);
  const usesReaderPage = classNames(tag).has('reader-page');
  const selector = applyFontScaleSelector(appSource);
  return {
    usesReaderPage,
    selector,
    covered: !usesReaderPage || selectorCoversReaderSurface(selector, surfaceId),
  };
}

function runSelfTests() {
  const oldModal = '<div class="modal-mask" id="reportModal"><div class="modal"></div></div>';
  const readerPage = '<div class="reader-page sub-page" id="reportModal"><div class="reader-scroll"></div></div>';
  const oldApp = `
    function applyFontScale() {
      document.querySelectorAll('.screen .pad, .modal').forEach(() => {});
    }
    window.__muneaApplyFontScale = applyFontScale;
  `;
  const fixedApp = `
    function applyFontScale() {
      document.querySelectorAll('.screen .pad, .modal, .reader-page .reader-scroll').forEach(() => {});
    }
    window.__muneaApplyFontScale = applyFontScale;
  `;

  assert.equal(
    assessSurface({ html: oldModal, appSource: oldApp, surfaceId: 'reportModal' }).covered,
    true,
    'legacy modal remains covered by .modal',
  );
  assert.equal(
    assessSurface({ html: readerPage, appSource: oldApp, surfaceId: 'reportModal' }).covered,
    false,
    'reader-page conversion must fail when font scaling still targets only .modal',
  );
  assert.equal(
    assessSurface({ html: readerPage, appSource: fixedApp, surfaceId: 'reportModal' }).covered,
    true,
    'reader-page content selector must satisfy the font-scale gate',
  );
}

function main() {
  runSelfTests();
  const html = fs.readFileSync(path.join(ROOT, 'web', 'index.html'), 'utf8');
  const appSource = fs.readFileSync(path.join(ROOT, 'web', 'src', 'app.js'), 'utf8');
  const result = assessSurface({
    html,
    appSource,
    surfaceId: 'reportModal',
  });

  assert.equal(
    result.covered,
    true,
    [
      'reportModal is a reader-page but applyFontScale() does not target reader-page content.',
      `Observed selector: ${result.selector}`,
      'The App XL setting would therefore remain visually identical to standard.',
    ].join(' '),
  );

  console.log(
    `PASS i18n font-scale surface gate: reportModal=${result.usesReaderPage ? 'reader-page-covered' : 'modal-covered'}`,
  );
}

main();
