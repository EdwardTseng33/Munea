(function (root, factory) {
  'use strict';

  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MuneaAppBindingRuntime = Object.freeze({ ...api });
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const SCHEMA = 'munea.i18n-app-binding-manifest.v1';
  const STATIC_MODE = 'static';
  const ATTRIBUTE_TARGETS = Object.freeze(new Set([
    'aria-label',
    'placeholder',
    'title',
  ]));

  function validateManifest(manifest) {
    if (!manifest || manifest.schema !== SCHEMA) {
      throw new TypeError(`App binding manifest must use ${SCHEMA}`);
    }
    if (!Array.isArray(manifest.staticBindings)) {
      throw new TypeError('App binding manifest staticBindings must be an array');
    }
    const signatures = new Set();
    for (const binding of manifest.staticBindings) {
      if (
        !binding
        || typeof binding.anchorId !== 'string'
        || !binding.anchorId
        || typeof binding.key !== 'string'
        || !binding.key
      ) {
        throw new TypeError('Every App static binding needs anchorId and key');
      }
      if (
        !['textContent', 'descendantText', ...ATTRIBUTE_TARGETS].includes(binding.target)
      ) {
        throw new TypeError(`Unsupported App binding target: ${binding.target}`);
      }
      if (![STATIC_MODE, 'state-owned'].includes(binding.applyMode)) {
        throw new TypeError(`Unsupported App binding applyMode: ${binding.applyMode}`);
      }
      const signature = `${binding.anchorId}:${binding.target}`;
      if (signatures.has(signature)) {
        throw new Error(`Duplicate App binding: ${signature}`);
      }
      signatures.add(signature);
    }
    return manifest;
  }

  function localeValue(localeFor) {
    return typeof localeFor === 'function' ? localeFor() : localeFor;
  }

  function rootContains(root, node) {
    if (!root || root.documentElement) return true;
    if (root === node) return true;
    return typeof root.contains === 'function' ? root.contains(node) : true;
  }

  function descendantTextNode(element) {
    if (!element || typeof element.querySelector !== 'function') return null;
    return element.querySelector('[data-i18n-descendant], span');
  }

  function writeBinding(element, binding, value) {
    if (binding.target === 'textContent') {
      if (element.textContent === value) return false;
      element.textContent = value;
      return true;
    }
    if (binding.target === 'descendantText') {
      const target = descendantTextNode(element);
      if (!target) throw new Error(`No descendant text target for #${binding.anchorId}`);
      if (target.textContent === value) return false;
      target.textContent = value;
      return true;
    }
    if (ATTRIBUTE_TARGETS.has(binding.target)) {
      if (element.getAttribute(binding.target) === value) return false;
      element.setAttribute(binding.target, value);
      return true;
    }
    throw new TypeError(`Unsupported App binding target: ${binding.target}`);
  }

  function createAppBindingRuntime(options) {
    const config = options || {};
    const manifest = validateManifest(config.manifest);
    const runtime = config.catalogRuntime;
    const documentLike = config.documentLike;
    const localeFor = config.localeFor;
    const reportIssue = typeof config.reportIssue === 'function'
      ? config.reportIssue
      : function () {};
    if (!runtime || typeof runtime.t !== 'function') {
      throw new TypeError('App binding runtime needs a catalog runtime');
    }
    if (!documentLike || typeof documentLike.getElementById !== 'function') {
      throw new TypeError('App binding runtime needs document.getElementById');
    }

    const bindings = manifest.staticBindings.filter(
      (binding) => binding.applyMode === STATIC_MODE,
    );

    function apply(root) {
      let found = 0;
      let changed = 0;
      for (const binding of bindings) {
        const element = documentLike.getElementById(binding.anchorId);
        if (!element || !rootContains(root, element)) continue;
        found += 1;
        try {
          const value = runtime.t(localeValue(localeFor), binding.key);
          if (writeBinding(element, binding, value)) changed += 1;
        } catch (error) {
          reportIssue(Object.freeze({
            anchorId: binding.anchorId,
            key: binding.key,
            reason: error && error.message ? error.message : String(error),
            target: binding.target,
          }));
        }
      }
      return Object.freeze({ changed, found, configured: bindings.length });
    }

    function observe(ObserverConstructor) {
      const Observer = ObserverConstructor || (
        typeof MutationObserver === 'function' ? MutationObserver : null
      );
      if (!Observer) return null;
      const target = documentLike.documentElement || documentLike;
      const observer = new Observer((records) => {
        for (const record of records || []) {
          for (const node of record.addedNodes || []) apply(node);
        }
      });
      observer.observe(target, {
        childList: true,
        subtree: true,
      });
      return observer;
    }

    return Object.freeze({
      apply,
      bindings: Object.freeze(bindings.map((binding) => Object.freeze({ ...binding }))),
      observe,
    });
  }

  return Object.freeze({
    SCHEMA,
    STATIC_MODE,
    createAppBindingRuntime,
    validateManifest,
  });
}));
