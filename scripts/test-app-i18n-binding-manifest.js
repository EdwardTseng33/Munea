'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'web', 'index.html'), 'utf8');
const app = fs.readFileSync(path.join(ROOT, 'web', 'src', 'app.js'), 'utf8');
const bootstrap = fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n.js'), 'utf8');
const domLocalizer = fs.readFileSync(
  path.join(ROOT, 'web', 'src', 'i18n', 'dom-localizer.js'),
  'utf8',
);
const manifest = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n', 'app-binding-manifest.json'), 'utf8'),
);
const catalogs = Object.fromEntries(
  ['zh-TW', 'en', 'ja', 'es'].map((locale) => [
    locale,
    JSON.parse(
      fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n', `${locale}.json`), 'utf8'),
    ),
  ]),
);

assert.equal(manifest.schema, 'munea.i18n-app-binding-manifest.v1');
assert.equal(manifest.integrationStatus, 'pending-conflicting-main-screen-prs');
assert.equal(manifest.dynamicContentObserver, 'integrated');
assert.match(domLocalizer, /function observe\(/, 'Dynamic DOM localizer observer is missing');
assert.match(
  bootstrap,
  /domLocalizer\.observe\(\s*document,/,
  'App locale bootstrap must observe dynamically inserted shipping UI',
);
assert.ok(manifest.staticBindings.length >= 25);
assert.ok(manifest.dynamicBindings.length >= 7);
assert.ok(manifest.markupRefactors.length >= 5);

const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]));
const bindingSignatures = new Set();

function assertKeys(keys, label) {
  for (const key of keys) {
    for (const [locale, catalog] of Object.entries(catalogs)) {
      assert.equal(typeof catalog[key], 'string', `${locale}:${label}:${key} is missing`);
      assert.ok(catalog[key].trim(), `${locale}:${label}:${key} is empty`);
    }
  }
}

for (const binding of manifest.staticBindings) {
  assert.ok(ids.has(binding.anchorId), `static anchor is missing: ${binding.anchorId}`);
  assert.ok(
    ['textContent', 'descendantText', 'aria-label', 'placeholder', 'title'].includes(binding.target),
    `unsupported binding target: ${binding.target}`,
  );
  const signature = `${binding.anchorId}:${binding.target}`;
  assert.ok(!bindingSignatures.has(signature), `duplicate binding: ${signature}`);
  bindingSignatures.add(signature);
  assertKeys([binding.key], `static:${signature}`);
}

for (const binding of manifest.dynamicBindings) {
  assert.ok(ids.has(binding.anchorId), `dynamic anchor is missing: ${binding.anchorId}`);
  assert.match(
    app,
    new RegExp(`function\\s+${binding.renderer}\\s*\\(`),
    `dynamic renderer is missing: ${binding.renderer}`,
  );
  assert.ok(binding.keys.length >= 2, `${binding.anchorId} needs at least two dynamic states`);
  assertKeys(binding.keys, `dynamic:${binding.anchorId}`);
}

for (const refactor of manifest.markupRefactors) {
  assert.ok(ids.has(refactor.containerId), `refactor container is missing: ${refactor.containerId}`);
  assert.ok(refactor.keys.length >= 3, `${refactor.containerId} refactor is underspecified`);
  assertKeys(refactor.keys, `refactor:${refactor.containerId}`);
}

console.log(
  `App i18n binding manifest PASS: ${manifest.staticBindings.length} static, `
  + `${manifest.dynamicBindings.length} dynamic, ${manifest.markupRefactors.length} refactors`,
);
