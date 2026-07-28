(function (root, factory) {
  'use strict';

  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MuneaDomLocalizer = Object.freeze({ ...api });
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const ATTRIBUTE_BINDINGS = Object.freeze([
    Object.freeze({ marker: 'data-i18n-aria-label', attribute: 'aria-label' }),
    Object.freeze({ marker: 'data-i18n-placeholder', attribute: 'placeholder' }),
    Object.freeze({ marker: 'data-i18n-title', attribute: 'title' }),
    Object.freeze({ marker: 'data-i18n-value', attribute: 'value' }),
  ]);

  function matchingNodes(root, selector) {
    if (!root) return [];
    const nodes = [];
    if (typeof root.matches === 'function' && root.matches(selector)) nodes.push(root);
    if (typeof root.querySelectorAll === 'function') {
      nodes.push(...root.querySelectorAll(selector));
    }
    return nodes;
  }

  function translationValues(valuesFor, key, node) {
    if (typeof valuesFor !== 'function') return undefined;
    const values = valuesFor(key, node);
    if (values == null) return undefined;
    if (typeof values !== 'object' || Array.isArray(values)) {
      throw new TypeError(`i18n values for ${key} must be an object`);
    }
    return values;
  }

  function translated(runtime, locale, key, node, valuesFor) {
    if (!runtime || typeof runtime.t !== 'function') {
      throw new TypeError('i18n catalog runtime is required');
    }
    return runtime.t(locale, key, translationValues(valuesFor, key, node));
  }

  function apply(root, runtime, locale, valuesFor) {
    let bindingCount = 0;
    for (const node of matchingNodes(root, '[data-i18n]')) {
      const key = node.getAttribute('data-i18n');
      if (!key) continue;
      node.textContent = translated(runtime, locale, key, node, valuesFor);
      bindingCount += 1;
    }

    for (const binding of ATTRIBUTE_BINDINGS) {
      for (const node of matchingNodes(root, `[${binding.marker}]`)) {
        const key = node.getAttribute(binding.marker);
        if (!key) continue;
        node.setAttribute(
          binding.attribute,
          translated(runtime, locale, key, node, valuesFor),
        );
        bindingCount += 1;
      }
    }
    return bindingCount;
  }

  function applyDocumentLocale(documentLike, runtime, locale) {
    if (!documentLike || !documentLike.documentElement) {
      throw new TypeError('document.documentElement is required');
    }
    if (!runtime || typeof runtime.localeMetadata !== 'function') {
      throw new TypeError('i18n catalog runtime is required');
    }
    const metadata = runtime.localeMetadata(locale);
    const htmlLang = metadata.htmlLang || metadata.locale;
    documentLike.documentElement.setAttribute('lang', htmlLang);
    documentLike.documentElement.setAttribute('dir', metadata.direction || 'ltr');
    return Object.freeze({
      direction: metadata.direction || 'ltr',
      htmlLang,
      locale: metadata.locale,
    });
  }

  return Object.freeze({
    ATTRIBUTE_BINDINGS,
    apply,
    applyDocumentLocale,
  });
}));
