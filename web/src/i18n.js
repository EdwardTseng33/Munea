/* Munea browser localization bootstrap.
 * UI language follows iOS App Language / navigator preferences. Draft locales
 * remain unavailable unless the checked-in release manifest enables them or an
 * explicit developer profile requests a preview. There is no user-facing
 * language switch and no locale value is persisted in browser storage. */
(function () {
  'use strict';

  const DEFAULT_LOCALE = 'zh-TW';
  const FALLBACK_METADATA = Object.freeze({
    locale: DEFAULT_LOCALE,
    label: '繁體中文',
    htmlLang: 'zh-Hant-TW',
    weatherLanguage: 'zh',
  });
  const FALLBACK_MESSAGES = Object.freeze({
    'app.title': 'Munea 沐寧',
    'settings.title': '設定',
    'tab.home': '首頁',
    'tab.status': '狀態',
    'tab.chat': '聊聊',
    'tab.family': '家人',
    'tab.settings': '設定',
    'voice.connecting': '正在連線...',
    'voice.ready': '直接說，我在這裡',
    'voice.fallback': '我在這裡，今天過得好嗎？想聊什麼都可以。',
  });
  const scriptBase = (document.currentScript && document.currentScript.src)
    ? new URL('.', document.currentScript.src)
    : new URL('src/', document.baseURI);
  const assetUrl = (relativePath) => new URL(relativePath, scriptBase).toString();

  let runtime = null;
  let domLocalizer = null;
  let currentLocale = DEFAULT_LOCALE;
  let metadataByLocale = { [DEFAULT_LOCALE]: FALLBACK_METADATA };
  let initialized = false;

  function loadScript(globalName, relativePath) {
    if (window[globalName]) return Promise.resolve(window[globalName]);
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = assetUrl(relativePath);
      script.async = false;
      script.onload = () => {
        if (window[globalName]) resolve(window[globalName]);
        else reject(new Error(`i18n script did not expose ${globalName}`));
      };
      script.onerror = () => reject(new Error(`failed to load i18n script: ${relativePath}`));
      document.head.appendChild(script);
    });
  }

  async function fetchJson(relativePath) {
    const response = await fetch(assetUrl(relativePath), { cache: 'no-cache' });
    if (!response.ok) {
      throw new Error(`failed to load i18n asset ${relativePath}: HTTP ${response.status}`);
    }
    return response.json();
  }

  function developerPreviewLocale() {
    const config = window.MUNEA_DEV_CONFIG || {};
    return config.enabled === true && typeof config.i18nPreviewLocale === 'string'
      ? config.i18nPreviewLocale
      : null;
  }

  function resolvedPreferredLanguages() {
    if (!runtime) return [DEFAULT_LOCALE];
    const preferred = runtime.devicePreferredLanguages(navigator)
      .map((value) => runtime.normalizeLocale(value))
      .filter(Boolean);
    const result = [];
    for (const locale of [currentLocale, ...preferred]) {
      if (!result.includes(locale)) result.push(locale);
    }
    return result;
  }

  function resolveConfiguredLocale() {
    if (!runtime) return DEFAULT_LOCALE;
    const previewLocale = developerPreviewLocale();
    return previewLocale
      ? runtime.resolveLocale([previewLocale])
      : runtime.currentFromDevice(navigator);
  }

  function current() {
    return currentLocale;
  }

  function normalize(value) {
    return runtime ? (runtime.normalizeLocale(value) || DEFAULT_LOCALE) : DEFAULT_LOCALE;
  }

  function t(key, values, fallback) {
    if (runtime) return runtime.t(currentLocale, key, values, fallback);
    let text = FALLBACK_MESSAGES[key] || fallback || key;
    for (const [name, value] of Object.entries(values || {})) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
    return text;
  }

  function apply(root) {
    const scope = root || document;
    if (runtime && domLocalizer) {
      domLocalizer.apply(scope, runtime, currentLocale);
      domLocalizer.applyDocumentLocale(document, runtime, currentLocale);
    } else {
      document.documentElement.setAttribute('lang', FALLBACK_METADATA.htmlLang);
      scope.querySelectorAll('[data-i18n]').forEach((element) => {
        element.textContent = t(
          element.getAttribute('data-i18n'),
          null,
          element.textContent,
        );
      });
    }
    document.title = t('app.title', null, 'Munea 沐寧');
    return currentLocale;
  }

  function setLocale() {
    // Deliberately ignore caller-provided locale. UI language follows the App
    // language, except for an explicit developer preview profile.
    currentLocale = resolveConfiguredLocale();
    apply();
    return currentLocale;
  }

  function supportedSnapshot() {
    return Object.freeze(Object.fromEntries(
      Object.entries(metadataByLocale).map(([locale, metadata]) => [
        locale,
        Object.freeze({ ...metadata }),
      ]),
    ));
  }

  function weatherLanguage() {
    return (metadataByLocale[currentLocale] || FALLBACK_METADATA).weatherLanguage || 'zh';
  }

  async function initialize() {
    try {
      const [manifest, catalogRuntimeApi, domLocalizerApi] = await Promise.all([
        fetchJson('i18n/catalog-manifest.json'),
        loadScript('MuneaCatalogRuntime', 'i18n/catalog-runtime.js'),
        loadScript('MuneaDomLocalizer', 'i18n/dom-localizer.js'),
      ]);
      const catalogs = Object.fromEntries(await Promise.all(
        manifest.locales.map(async (entry) => [
          entry.locale,
          await fetchJson(`i18n/${entry.catalog}`),
        ]),
      ));
      const previewLocale = developerPreviewLocale();
      runtime = catalogRuntimeApi.createCatalogRuntime({
        allowDevelopmentLocales: Boolean(previewLocale),
        catalogs,
        manifest,
        reportMissingKey: (event) => {
          try {
            window.dispatchEvent(new CustomEvent('munea:i18n-missing-key', { detail: event }));
          } catch (error) {}
        },
      });
      domLocalizer = domLocalizerApi;
      metadataByLocale = Object.fromEntries(
        manifest.locales.map((entry) => [entry.locale, Object.freeze({ ...entry })]),
      );
      currentLocale = resolveConfiguredLocale();
      initialized = true;
      apply();
      try {
        window.dispatchEvent(new CustomEvent('munea:locale-ready', {
          detail: {
            locale: currentLocale,
            preferredLanguages: resolvedPreferredLanguages(),
            preview: Boolean(previewLocale),
          },
        }));
      } catch (error) {}
      return Object.freeze({ locale: currentLocale, fallback: false });
    } catch (error) {
      currentLocale = DEFAULT_LOCALE;
      initialized = true;
      apply();
      try { console.warn('Munea i18n bootstrap fell back to zh-TW:', error); } catch (ignored) {}
      return Object.freeze({ locale: currentLocale, fallback: true, error: error.message });
    }
  }

  const ready = initialize();
  window.MuneaI18n = Object.freeze({
    get supported() { return supportedSnapshot(); },
    get initialized() { return initialized; },
    apply,
    current,
    normalize,
    preferredLanguages: resolvedPreferredLanguages,
    ready,
    setLocale,
    t,
    weatherLanguage,
  });
}());
