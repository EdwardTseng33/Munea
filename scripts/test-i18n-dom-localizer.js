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
const alt = new FakeElement({ 'data-i18n-alt': 'companion.nening.name' });
root.append(text, aria, placeholder, alt);

const applied = apply(root, runtime, 'en', (key) => (
  key === 'voice.queue.position.one' ? { count: 3 } : undefined
));
assert.equal(applied, 5, 'Every text and attribute binding should be applied once');
assert.equal(text.textContent, 'You’re number 3 in line');
assert.equal(aria.getAttribute('aria-label'), 'Back');
assert.equal(placeholder.getAttribute('placeholder'), catalogs.en['feedback.placeholder']);
assert.equal(alt.getAttribute('alt'), catalogs.en['companion.nening.name']);
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
  ['aria-label', 'placeholder', 'title', 'alt', 'value'],
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

// 2026-11-17：加了 data-i18n-live 的元素，程式依狀態寫上去的字不可以被蓋回寫死的那一句。
// 真實案例：「刪除我的資料」按第一下要變成「再按一次：永久刪除帳號與資料」，
// 警告被蓋掉，使用者再按一下帳號就永久刪除了。
const liveButton = new FakeElement({ 'data-i18n': 'data.delete', 'data-i18n-live': '' });
observerCallback([{ type: 'childList', addedNodes: [liveButton] }]);
assert.equal(liveButton.textContent, catalogs.es['data.delete'], 'A live element still gets its localized default');
liveButton.textContent = catalogs.es['data.confirmDeleteAccount'];
observerCallback([{ type: 'childList', target: liveButton, addedNodes: [] }]);
assert.equal(
  liveButton.textContent,
  catalogs.es['data.confirmDeleteAccount'],
  'State text the program wrote on a live element must not be reverted to the static sentence',
);
apply(liveButton, runtime, 'ja');
assert.equal(
  liveButton.textContent,
  catalogs.es['data.confirmDeleteAccount'],
  'A later full pass must still leave program-owned text to the program',
);
// 程式把字寫回預設那一句（還原）也照程式的
liveButton.textContent = catalogs.es['data.delete'];
observerCallback([{ type: 'childList', target: liveButton, addedNodes: [] }]);
assert.equal(liveButton.textContent, catalogs.es['data.delete']);
// 程式換了翻譯鍵＝交還給翻譯層；之後再被程式改寫，一樣歸程式
liveButton.setAttribute('data-i18n', 'purchase.restore');
observerCallback([{ type: 'attributes', target: liveButton, addedNodes: [] }]);
assert.equal(liveButton.textContent, catalogs.es['purchase.restore']);
liveButton.textContent = '…';
observerCallback([{ type: 'childList', target: liveButton, addedNodes: [] }]);
assert.equal(liveButton.textContent, '…');
// 舊程式直接寫中文原句（同一個鍵的另一種語言）：仍然改回目前語言
const liveLegacy = new FakeElement({ 'data-i18n': 'data.delete', 'data-i18n-live': '' });
observerCallback([{ type: 'childList', addedNodes: [liveLegacy] }]);
liveLegacy.textContent = catalogs['zh-TW']['data.delete'];
observerCallback([{ type: 'childList', target: liveLegacy, addedNodes: [] }]);
assert.equal(
  liveLegacy.textContent,
  catalogs.es['data.delete'],
  'The same sentence written in the source language is still corrected to the current locale',
);
// 沒加 data-i18n-live 的元素：行為不變，照舊蓋回
const plain = new FakeElement({ 'data-i18n': 'data.delete' });
observerCallback([{ type: 'childList', addedNodes: [plain] }]);
plain.textContent = catalogs.es['data.confirmDeleteAccount'];
observerCallback([{ type: 'childList', target: plain, addedNodes: [] }]);
assert.equal(
  plain.textContent,
  catalogs.es['data.delete'],
  'Elements without data-i18n-live keep the unconditional overwrite',
);
assert.equal(
  observe(dynamicRoot, runtime, 'en', null, null),
  null,
  'Non-browser runtimes may omit MutationObserver without breaking localization',
);

console.log('PASS: safe DOM localization contract');
