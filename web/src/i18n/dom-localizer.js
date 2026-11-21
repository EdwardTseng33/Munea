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
    Object.freeze({ marker: 'data-i18n-alt', attribute: 'alt' }),
    Object.freeze({ marker: 'data-i18n-value', attribute: 'value' }),
  ]);
  const OBSERVED_ATTRIBUTES = Object.freeze([
    'data-i18n',
    ...ATTRIBUTE_BINDINGS.map(({ marker }) => marker),
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

  // data-i18n-live：這個元素的字，程式會依狀態改（2026-11-17）。
  //
  // 翻譯層平常是無條件覆寫：元素掛著 data-i18n，程式一改它的字就被巡邏的
  // MutationObserver 蓋回寫死的那一句。11/17 查到的後果：
  //   「刪除我的資料」按第一下該變成「再按一次：永久刪除帳號與資料」，警告被蓋掉，
  //   再按一下帳號就沒了；隱私權政策的頁面標題寫「使用條款」；題數拉到 20 仍寫 10 題。
  //
  // 加了 data-i18n-live 的元素：翻譯層先照翻譯鍵寫預設那一句（各語言都有字），
  // 並記住自己寫了什麼。之後看到元素上的字不是自己寫的那一句，就是程式改的，
  // 這個元素的字從此歸程式管，翻譯層不再碰。
  //   - 程式換了翻譯鍵（setAttribute('data-i18n', …)）＝交還給翻譯層，照新鍵重寫。
  //   - 程式寫的若只是「同一個鍵在別的語言的那一句」（舊程式直接寫中文原句），
  //     那是同一句話、語言不對，照樣改回目前語言。
  //
  // 沒加的元素行為完全不變。不能改成全部適用：很多舊程式會在開機時往元素寫過期文案，
  // 全靠翻譯層蓋回正確的那一句（11/17 實測，改成全部適用會讓隱私說明退回舊版）。
  const LIVE_MARKER = 'data-i18n-live';
  const lastWritten = new WeakMap(); // 元素 → { key, value }：翻譯層上次寫的
  const programOwned = new WeakMap(); // 元素 → 當時的翻譯鍵

  function sameSentenceInAnotherLocale(runtime, locale, key, node, valuesFor, text) {
    const locales = Array.isArray(runtime.enabledLocales) ? runtime.enabledLocales : [];
    for (const other of locales) {
      if (other === locale) continue;
      try {
        if (translated(runtime, other, key, node, valuesFor) === text) return true;
      } catch (error) {
        // 別的語言缺這個鍵：當作不是同一句
      }
    }
    return false;
  }

  function apply(root, runtime, locale, valuesFor) {
    let bindingCount = 0;
    for (const node of matchingNodes(root, '[data-i18n]')) {
      const key = node.getAttribute('data-i18n');
      if (!key) continue;
      bindingCount += 1;
      const live = node.getAttribute(LIVE_MARKER) != null;
      if (live && programOwned.get(node) === key) continue;
      const value = translated(runtime, locale, key, node, valuesFor);
      const current = node.textContent;
      if (live) {
        const previous = lastWritten.get(node);
        if (
          previous
          && previous.key === key
          && current !== previous.value
          && current !== value
          && !sameSentenceInAnotherLocale(runtime, locale, key, node, valuesFor, current)
        ) {
          programOwned.set(node, key);
          continue;
        }
        programOwned.delete(node);
        lastWritten.set(node, { key, value });
      }
      if (current !== value) node.textContent = value;
    }

    for (const binding of ATTRIBUTE_BINDINGS) {
      for (const node of matchingNodes(root, `[${binding.marker}]`)) {
        const key = node.getAttribute(binding.marker);
        if (!key) continue;
        const value = translated(runtime, locale, key, node, valuesFor);
        if (node.getAttribute(binding.attribute) !== value) {
          node.setAttribute(binding.attribute, value);
        }
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

  function observe(
    root,
    runtime,
    localeFor,
    valuesFor,
    ObserverConstructor,
  ) {
    const target = root && root.documentElement ? root.documentElement : root;
    if (!target) throw new TypeError('i18n observation root is required');
    const Observer = ObserverConstructor || (
      typeof MutationObserver === 'function' ? MutationObserver : null
    );
    if (!Observer) return null;
    const resolvedLocale = () => (
      typeof localeFor === 'function' ? localeFor() : localeFor
    );
    const observer = new Observer((records) => {
      const pending = new Set();
      for (const record of records || []) {
        if (record.type === 'attributes' && record.target) {
          pending.add(record.target);
        }
        if (record.type === 'childList' && record.target) {
          pending.add(record.target);
        }
        for (const node of record.addedNodes || []) {
          pending.add(node);
        }
      }
      for (const node of pending) {
        apply(node, runtime, resolvedLocale(), valuesFor);
      }
    });
    observer.observe(target, {
      attributeFilter: [...OBSERVED_ATTRIBUTES],
      attributes: true,
      childList: true,
      subtree: true,
    });
    return observer;
  }

  return Object.freeze({
    ATTRIBUTE_BINDINGS,
    OBSERVED_ATTRIBUTES,
    apply,
    applyDocumentLocale,
    observe,
  });
}));
