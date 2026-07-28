(function (root, factory) {
  'use strict';

  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MuneaLegalRouting = Object.freeze({ ...api });
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const PAGE_KINDS = Object.freeze(['privacy', 'terms', 'support']);

  function catalogEntry(manifest, locale) {
    if (!manifest || !Array.isArray(manifest.locales)) {
      throw new TypeError('catalog manifest.locales is required');
    }
    return manifest.locales.find((entry) => entry && entry.locale === locale) || null;
  }

  function legalEntry(manifest, locale, legalRegion) {
    if (!manifest || !manifest.locales || typeof manifest.locales !== 'object') {
      throw new TypeError('legal manifest.locales is required');
    }
    const base = manifest.locales[locale] || null;
    const region = String(legalRegion || '').trim().toUpperCase();
    const regional = base
      && base.regionalVariants
      && region
      && base.regionalVariants[region];
    if (!regional) return base;
    return {
      ...base,
      ...regional,
      legalRegion: region,
      pages: regional.pages || base.pages,
    };
  }

  function webPath(manifestPath) {
    const raw = String(manifestPath || '').replaceAll('\\', '/');
    if (!raw || raw.startsWith('/') || /^[a-z][a-z0-9+.-]*:/i.test(raw)) {
      throw new Error('legal page path must be relative');
    }
    if (raw.startsWith('../')) {
      const rootPage = raw.slice(3);
      if (!/^[A-Za-z0-9._-]+$/.test(rootPage)) {
        throw new Error('legal root page path must be a file name');
      }
      return rootPage;
    }
    if (raw.split('/').some((part) => !part || part === '.' || part === '..')) {
      throw new Error('legal page path contains an unsafe segment');
    }
    return `legal/${raw}`;
  }

  function resolveLegalPage(options) {
    const config = options || {};
    const kind = String(config.kind || '');
    if (!PAGE_KINDS.includes(kind)) {
      throw new RangeError(`unsupported legal page kind: ${kind}`);
    }

    const catalogManifest = config.catalogManifest;
    const legalManifest = config.legalManifest;
    const fallbackLocale = legalManifest && (
      legalManifest.fallbackLocale || legalManifest.defaultLocale
    );
    const requestedLocale = catalogEntry(catalogManifest, config.locale)
      ? config.locale
      : fallbackLocale;
    const requestedCatalog = catalogEntry(catalogManifest, requestedLocale);
    const requestedLegal = legalEntry(
      legalManifest,
      requestedLocale,
      config.legalRegion,
    );
    const draftAllowed = config.allowDraft === true;
    const requestedReady = Boolean(
      requestedCatalog
      && requestedLegal
      && requestedLegal.pages
      && requestedLegal.pages[kind]
      && (
        draftAllowed
        || (
          requestedCatalog.runtimeEnabled === true
          && requestedLegal.legalReview === 'approved'
        )
      ),
    );

    const resolvedLocale = requestedReady ? requestedLocale : fallbackLocale;
    const resolvedLegal = legalEntry(
      legalManifest,
      resolvedLocale,
      resolvedLocale === requestedLocale ? config.legalRegion : null,
    );
    if (!resolvedLegal || !resolvedLegal.pages || !resolvedLegal.pages[kind]) {
      throw new Error(`missing ${kind} page for legal fallback locale ${fallbackLocale}`);
    }

    return Object.freeze({
      kind,
      legalReview: resolvedLegal.legalReview,
      path: webPath(resolvedLegal.pages[kind]),
      requestedLegalReview: requestedLegal ? requestedLegal.legalReview : null,
      requestedLocale,
      requestedLegalRegion: requestedLegal ? requestedLegal.legalRegion || null : null,
      resolvedLocale,
      resolvedLegalRegion: resolvedLegal.legalRegion || null,
      usedFallback: resolvedLocale !== requestedLocale,
    });
  }

  return Object.freeze({
    PAGE_KINDS,
    resolveLegalPage,
  });
}));
