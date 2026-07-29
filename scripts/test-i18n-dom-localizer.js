'use strict';

const assert = require('assert');
const fs = require('fs');
const { createCatalogRuntime } = require('../web/src/i18n/catalog-runtime.js');
const {
  ATTRIBUTE_BINDINGS,
  OBSERVED_ATTRIBUTES,
  apply,
  applyDocumentLocale,
  observe,
} = require('../web/src/i18n/dom-localizer.js');

function readJson(path) {
  return JSON.parse(fs.readFileSync(path, 'utf8'));
}

class FakeElement {
  constructor(attributes = {}) {
    this.attributes = { ...attributes };
    this.children = [];
    this.textContent = '';
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name)
      ? this.attributes[name]
      : null;
  }

  matches(selector) {
    const match = /^\[([a-z0-9-]+)\]$/i.exec(selector);
    return Boolean(match && this.getAttribute(match[1]) != null);
  }

  querySelectorAll(selector) {
    const matches = [];
    const visit = (node) => {
      if (node.matches(selector)) matches.push(node);
      node.children.forEach(visit);
    };
    this.children.forEach(visit);
    return matches;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
}

const manifest = readJson('web/src/i18n/catalog-manifest.json');
const catalogs = Object.fromEntries(
  manifest.locales.map((entry) => [
    entry.locale,
    readJson(`web/src/i18n/${entry.catalog}`),
  ]),
);
const runtime = createCatalogRuntime({
  allowDevelopmentLocales: true,
  catalogs,
  manifest,
});

const root = new FakeElement({ 'data-i18n-title': 'reader.privacyTitle' });
const text = new FakeElement({ 'data-i18n': 'voice.queue.position.one' });
const aria = new FakeElement({ 'data-i18n-aria-label': 'reader.back' });
const placeholder = new FakeElement({ 'data-i18n-placeholder': 'feedback.placeholder' });
root.append(text, aria, placeholder);

const applied = apply(root, runtime, 'en', (key) => (
  key === 'voice.queue.position.one' ? { count: 3 } : undefined
));
assert.equal(applied, 4, 'Every text and attribute binding should be applied once');
assert.equal(text.textContent, 'You are number 3 in line');
assert.equal(aria.getAttribute('aria-label'), 'Back');
assert.equal(placeholder.getAttribute('placeholder'), catalogs.en['feedback.placeholder']);
assert.equal(root.getAttribute('title'), 'Privacy Policy');
assert.equal(text.getAttribute('innerHTML'), null, 'The localizer must never write innerHTML');

const documentElement = new FakeElement();
const appliedLocale = applyDocumentLocale(
  { documentElement },
  runtime,
  'ja',
);
assert.deepEqual(appliedLocale, {
  direction: 'ltr',
  htmlLang: 'ja',
  locale: 'ja',
});
assert.equal(documentElement.getAttribute('lang'), 'ja');
assert.equal(documentElement.getAttribute('dir'), 'ltr');

assert.deepEqual(
  ATTRIBUTE_BINDINGS.map((binding) => binding.attribute),
  ['aria-label', 'placeholder', 'title', 'value'],
  'Only the reviewed safe attribute allowlist may be written',
);
assert.throws(
  () => apply(text, runtime, 'en', () => 'unsafe'),
  /must be an object/,
  'Interpolation data must be supplied as structured values',
);

let observedTarget = null;
let observedOptions = null;
let observerCallback = null;
class FakeMutationObserver {
  constructor(callback) {
    observerCallback = callback;
  }

  observe(target, options) {
    observedTarget = target;
    observedOptions = options;
  }
}
const dynamicRoot = new FakeElement();
const mutationObserver = observe(
  dynamicRoot,
  runtime,
  () => 'es',
  null,
  FakeMutationObserver,
);
assert(mutationObserver instanceof FakeMutationObserver);
assert.equal(observedTarget, dynamicRoot);
assert.deepEqual(observedOptions, {
  attributeFilter: [...OBSERVED_ATTRIBUTES],
  attributes: true,
  childList: true,
  subtree: true,
});
const dynamicText = new FakeElement({ 'data-i18n': 'notification.centerTitle' });
observerCallback([{ type: 'childList', addedNodes: [dynamicText] }]);
assert.equal(dynamicText.textContent, catalogs.es['notification.centerTitle']);
dynamicText.textContent = '通知中心';
observerCallback([{ type: 'childList', target: dynamicText, addedNodes: [] }]);
assert.equal(
  dynamicText.textContent,
  catalogs.es['notification.centerTitle'],
  'A renderer overwriting localized text must be corrected on the existing bound element',
);
dynamicText.setAttribute('data-i18n', 'notification.noItems');
observerCallback([{ type: 'attributes', target: dynamicText, addedNodes: [] }]);
assert.equal(dynamicText.textContent, catalogs.es['notification.noItems']);
assert.equal(
  observe(dynamicRoot, runtime, 'en', null, null),
  null,
  'Non-browser runtimes may omit MutationObserver without breaking localization',
);

console.log('PASS: safe DOM localization contract');
