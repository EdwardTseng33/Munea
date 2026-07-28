'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const runtimeApi = require('../web/src/i18n/app-binding-runtime.js');

const manifest = JSON.parse(
  fs.readFileSync('web/src/i18n/app-binding-manifest.json', 'utf8'),
);

class FakeElement {
  constructor(id, textContent = '') {
    this.id = id;
    this.textContent = textContent;
    this.attributes = {};
    this.children = [];
  }

  append(child) {
    this.children.push(child);
  }

  contains(node) {
    return this === node || this.children.some(
      (child) => child === node || child.contains(node),
    );
  }

  getAttribute(name) {
    return Object.hasOwn(this.attributes, name) ? this.attributes[name] : null;
  }

  querySelector(selector) {
    if (selector !== '[data-i18n-descendant], span') return null;
    return this.children[0] || null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
}

const nodes = new Map();
function addNode(id, text = '') {
  const node = new FakeElement(id, text);
  nodes.set(id, node);
  return node;
}

const signIn = addNode('authSignInBtn', '登入');
const stateOwned = addNode('authStatusText', '已登入');
const removePhoto = addNode('pfAvatarClear');
const apple = addNode('authAppleBtn');
const appleLabel = new FakeElement('', '使用 Apple 登入');
apple.append(appleLabel);
const missingDescendant = addNode('authGoogleBtn');
const issues = [];
const observations = [];

class FakeMutationObserver {
  constructor(callback) {
    this.callback = callback;
  }

  observe(target, options) {
    observations.push({ observer: this, options, target });
  }

  disconnect() {}
}

const documentLike = {
  documentElement: new FakeElement('html'),
  getElementById: (id) => nodes.get(id) || null,
};
const catalogRuntime = {
  t(locale, key) {
    return `${locale}:${key}`;
  },
};
const runtime = runtimeApi.createAppBindingRuntime({
  catalogRuntime,
  documentLike,
  localeFor: () => 'ja',
  manifest,
  reportIssue: (issue) => issues.push(issue),
});

const first = runtime.apply(documentLike);
assert.equal(first.configured, 20);
assert.equal(signIn.textContent, 'ja:auth.signIn');
assert.equal(
  stateOwned.textContent,
  '已登入',
  'Static localization must not overwrite state-owned renderer output',
);
assert.equal(removePhoto.getAttribute('aria-label'), 'ja:accessibility.removePhoto');
assert.equal(removePhoto.getAttribute('title'), 'ja:accessibility.removePhoto');
assert.equal(appleLabel.textContent, 'ja:auth.apple');
assert.equal(issues.length, 1);
assert.equal(issues[0].anchorId, 'authGoogleBtn');

const second = runtime.apply(documentLike);
assert.equal(second.changed, 0, 'Reapplying the same locale must be idempotent');

const observer = runtime.observe(FakeMutationObserver);
assert(observer instanceof FakeMutationObserver);
assert.equal(observations.length, 1);
assert.deepEqual(observations[0].options, { childList: true, subtree: true });

const lateTopUp = addNode('topUpBtn', '加購點數');
observer.callback([{ type: 'childList', addedNodes: [lateTopUp] }]);
assert.equal(lateTopUp.textContent, 'ja:settings.topUpCredits');

assert.throws(
  () => runtimeApi.validateManifest({ schema: 'wrong', staticBindings: [] }),
  /App binding manifest/,
);
assert.throws(
  () => runtimeApi.validateManifest({
    schema: runtimeApi.SCHEMA,
    staticBindings: [{
      anchorId: 'x',
      applyMode: 'always',
      key: 'common.save',
      target: 'textContent',
    }],
  }),
  /applyMode/,
);

console.log(
  `App static binding runtime PASS: ${runtime.bindings.length} safe bindings, `
  + `${manifest.staticBindings.length - runtime.bindings.length} state-owned bindings deferred`,
);
