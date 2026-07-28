(function (root, factory) {
  'use strict';

  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MuneaCatalogRuntime = Object.freeze({ ...api });
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function normalizedLanguageFamily(value) {
    const raw = String(value || '').trim().replaceAll('_', '-').toLowerCase();
    if (raw.startsWith('zh')) return 'zh-TW';
    if (raw.startsWith('en')) return 'en';
    if (raw.startsWith('ja')) return 'ja';
    if (raw.startsWith('es')) return 'es';
    return null;
  }

  function normalizeLocaleTag(value, supportedLocales) {
    const supported = new Set(supportedLocales || []);
    const family = normalizedLanguageFamily(value);
    return family && supported.has(family) ? family : null;
  }

  function devicePreferredLanguages(navigatorLike) {
    const source = navigatorLike || {};
    const candidates = Array.isArray(source.languages) && source.languages.length
      ? source.languages
      : [source.language];
    return candidates
      .map((value) => String(value || '').trim())
      .filter(Boolean);
  }

  function createCatalogRuntime(options) {
    const config = options || {};
    const manifest = config.manifest;
    const catalogs = config.catalogs;
    if (!manifest || !Array.isArray(manifest.locales)) {
      throw new TypeError('i18n manifest.locales is required');
    }
    if (!catalogs || typeof catalogs !== 'object') {
      throw new TypeError('i18n catalogs are required');
    }

    const entries = new Map();
    for (const entry of manifest.locales) {
      if (!entry || !entry.locale || entries.has(entry.locale)) {
        throw new Error(`invalid or duplicate i18n locale: ${entry && entry.locale}`);
      }
      if (!catalogs[entry.locale] || typeof catalogs[entry.locale] !== 'object') {
        throw new Error(`missing i18n catalog: ${entry.locale}`);
      }
      entries.set(entry.locale, { ...entry });
    }

    const fallbackLocale = manifest.fallbackLocale || manifest.defaultLocale;
    if (!entries.has(fallbackLocale)) {
      throw new Error(`missing i18n fallback locale: ${fallbackLocale}`);
    }

    const allowDevelopmentLocales = config.allowDevelopmentLocales === true;
    const enabledLocales = [...entries.values()]
      .filter((entry) => entry.runtimeEnabled || (
        allowDevelopmentLocales && entry.status === 'development'
      ))
      .map((entry) => entry.locale);
    if (!enabledLocales.includes(fallbackLocale)) {
      throw new Error('i18n fallback locale must be runtime-enabled');
    }

    const allLocales = [...entries.keys()];
    const missingKeys = new Set();
    const reportMissingKey = typeof config.reportMissingKey === 'function'
      ? config.reportMissingKey
      : null;

    function resolveLocale(preferredLanguages) {
      const candidates = Array.isArray(preferredLanguages)
        ? preferredLanguages
        : [preferredLanguages];
      for (const candidate of candidates) {
        const normalized = normalizeLocaleTag(candidate, allLocales);
        if (normalized && enabledLocales.includes(normalized)) return normalized;
      }
      return fallbackLocale;
    }

    function resolveDeviceLocale(navigatorLike) {
      return resolveLocale(devicePreferredLanguages(navigatorLike));
    }

    function reportMissing(requestedLocale, resolvedLocale, key) {
      const signature = `${resolvedLocale}:${key}`;
      if (!reportMissingKey || missingKeys.has(signature)) return;
      missingKeys.add(signature);
      try {
        reportMissingKey(Object.freeze({
          event: 'i18n_missing_key',
          key,
          requestedLocale,
          resolvedLocale,
          fallbackLocale,
        }));
      } catch (error) {
        // Telemetry must never break visible copy or App startup.
      }
    }

    function interpolate(template, values) {
      return String(template).replace(
        /\{([A-Za-z][A-Za-z0-9_]*)\}/g,
        (token, name) => (
          Object.prototype.hasOwnProperty.call(values || {}, name)
            ? String(values[name])
            : token
        ),
      );
    }

    function t(locale, key, values, literalFallback) {
      if (typeof key !== 'string' || !key.trim()) {
        throw new TypeError('i18n key must be a non-empty string');
      }
      const requestedLocale = normalizeLocaleTag(locale, allLocales) || fallbackLocale;
      const resolvedLocale = enabledLocales.includes(requestedLocale)
        ? requestedLocale
        : fallbackLocale;
      let template = catalogs[resolvedLocale][key];
      if (typeof template !== 'string') {
        reportMissing(requestedLocale, resolvedLocale, key);
        template = catalogs[fallbackLocale][key];
      }
      if (typeof template !== 'string') template = literalFallback || key;
      return interpolate(template, values);
    }

    function localeMetadata(locale) {
      const resolvedLocale = resolveLocale([locale]);
      return Object.freeze({ ...entries.get(resolvedLocale) });
    }

    return Object.freeze({
      currentFromDevice: resolveDeviceLocale,
      devicePreferredLanguages,
      enabledLocales: Object.freeze([...enabledLocales]),
      fallbackLocale,
      localeMetadata,
      normalizeLocale: (value) => normalizeLocaleTag(value, allLocales),
      resolveLocale,
      t,
    });
  }

  return Object.freeze({
    createCatalogRuntime,
    devicePreferredLanguages,
    normalizeLocaleTag,
  });
}));
