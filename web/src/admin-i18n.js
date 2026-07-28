(function () {
  "use strict";

  const SUPPORTED = ["zh-TW", "en", "ja", "es"];
  const HTML_LANG = { "zh-TW": "zh-Hant", en: "en", ja: "ja", es: "es" };
  const LOCAL_HOST_RE = /^(?:localhost|127\.0\.0\.1|\[?::1\]?)$/i;
  const ATTRIBUTE_NAMES = ["aria-label", "placeholder", "title", "data-label"];
  const SKIP_SELECTOR = "script,style,noscript,code,pre,[data-i18n-skip]";

  function normalizeLocale(value) {
    const raw = String(value || "").trim().replace(/_/g, "-").toLowerCase();
    if (raw.startsWith("zh")) return "zh-TW";
    if (raw.startsWith("ja")) return "ja";
    if (raw.startsWith("es")) return "es";
    if (raw.startsWith("en")) return "en";
    return "";
  }

  function resolveLocale() {
    const injected = normalizeLocale(window.MUNEA_ADMIN_LOCALE);
    if (injected && SUPPORTED.includes(injected)) return injected;
    if (LOCAL_HOST_RE.test(location.hostname)) {
      const forced = normalizeLocale(new URLSearchParams(location.search).get("lang"));
      if (forced && SUPPORTED.includes(forced)) return forced;
    }
    const preferred = Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language];
    for (const candidate of preferred) {
      const locale = normalizeLocale(candidate);
      if (locale && SUPPORTED.includes(locale)) return locale;
    }
    return "zh-TW";
  }

  function normalizedText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function compilePattern(entry) {
    let source = normalizedText(entry.source);
    let cursor = 0;
    let expression = "^";
    const tokenRe = /\{(\d+)\}/g;
    let match;
    while ((match = tokenRe.exec(source))) {
      expression += escapeRegExp(source.slice(cursor, match.index));
      expression += "(.+?)";
      cursor = match.index + match[0].length;
    }
    expression += escapeRegExp(source.slice(cursor)) + "$";
    return {
      regex: new RegExp(expression, "u"),
      target: String(entry.target || ""),
    };
  }

  function renderPattern(target, captures) {
    return target.replace(/\{(\d+)\}/g, (_, index) => captures[Number(index)] || "");
  }

  const locale = resolveLocale();
  document.documentElement.classList.add("admin-i18n-pending");
  let catalog = { exact: {}, patterns: [] };
  let compiledPatterns = [];
  let observer = null;
  let translating = false;

  function translationFor(value) {
    const source = normalizedText(value);
    if (!source) return "";
    if (Object.prototype.hasOwnProperty.call(catalog.exact, source)) {
      return String(catalog.exact[source]);
    }
    for (const pattern of compiledPatterns) {
      const match = source.match(pattern.regex);
      if (match) return renderPattern(pattern.target, match.slice(1));
    }
    return "";
  }

  function translateTextNode(node) {
    if (!node || !node.parentElement || node.parentElement.closest(SKIP_SELECTOR)) return;
    const raw = node.nodeValue || "";
    const translated = translationFor(raw);
    if (!translated || translated === normalizedText(raw)) return;
    const leading = raw.match(/^\s*/u)?.[0] || "";
    const trailing = raw.match(/\s*$/u)?.[0] || "";
    node.nodeValue = leading + translated + trailing;
  }

  function translateAttributes(element) {
    if (!element || element.nodeType !== Node.ELEMENT_NODE || element.matches(SKIP_SELECTOR)) return;
    for (const attribute of ATTRIBUTE_NAMES) {
      if (!element.hasAttribute(attribute)) continue;
      const raw = element.getAttribute(attribute);
      const translated = translationFor(raw);
      if (translated && translated !== normalizedText(raw)) {
        element.setAttribute(attribute, translated);
      }
    }
  }

  function translateElement(element) {
    if (!element || element.nodeType !== Node.ELEMENT_NODE || element.matches(SKIP_SELECTOR)) return;
    translateAttributes(element);
    element.querySelectorAll("*").forEach(translateAttributes);
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(translateTextNode);
  }

  function translate(root) {
    if (locale === "zh-TW" || translating || !root) return;
    translating = true;
    try {
      if (root.nodeType === Node.TEXT_NODE) translateTextNode(root);
      else translateElement(root);
    } finally {
      translating = false;
    }
  }

  function audit(root) {
    if (locale === "zh-TW") return [];
    const scope = root || document.documentElement;
    const unresolved = new Set();
    const inspect = (value) => {
      const source = normalizedText(value);
      const translated = translationFor(source);
      if (translated && translated !== source) unresolved.add(source);
    };
    if (scope.nodeType === Node.ELEMENT_NODE) {
      [scope, ...scope.querySelectorAll("*")].forEach((element) => {
        if (element.matches(SKIP_SELECTOR)) return;
        ATTRIBUTE_NAMES.forEach((attribute) => {
          if (element.hasAttribute(attribute)) inspect(element.getAttribute(attribute));
        });
      });
      const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        if (!walker.currentNode.parentElement?.closest(SKIP_SELECTOR)) {
          inspect(walker.currentNode.nodeValue);
        }
      }
    } else if (scope.nodeType === Node.TEXT_NODE) {
      inspect(scope.nodeValue);
    }
    return [...unresolved];
  }

  function watch() {
    if (locale === "zh-TW" || observer) return;
    observer = new MutationObserver((mutations) => {
      if (translating) return;
      for (const mutation of mutations) {
        if (mutation.type === "characterData") translate(mutation.target);
        mutation.addedNodes.forEach(translate);
      }
    });
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
    });
  }

  async function load() {
    document.documentElement.lang = HTML_LANG[locale];
    document.documentElement.dataset.adminLocale = locale;
    if (locale === "zh-TW") return;
    const response = await fetch(`src/i18n/admin-${locale}.json`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`admin_catalog_http_${response.status}`);
    const loaded = await response.json();
    if (loaded.locale !== locale || !loaded.exact || !Array.isArray(loaded.patterns)) {
      throw new Error("admin_catalog_invalid");
    }
    catalog = loaded;
    compiledPatterns = loaded.patterns.map(compilePattern);
    if (loaded.title) document.title = loaded.title;
    translate(document.documentElement);
    watch();
  }

  const ready = load()
    .catch((error) => {
      document.documentElement.dataset.i18nError = String(error && error.message || error);
      document.documentElement.lang = "zh-Hant";
      console.error("[Munea admin i18n]", error);
    })
    .finally(() => document.documentElement.classList.remove("admin-i18n-pending"));

  window.MuneaAdminI18n = Object.freeze({
    current: () => locale,
    ready,
    translate,
    audit,
  });
})();
