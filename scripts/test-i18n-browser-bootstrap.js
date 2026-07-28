'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const catalogRuntime = require('../web/src/i18n/catalog-runtime.js');
const domLocalizer = require('../web/src/i18n/dom-localizer.js');

const manifest = JSON.parse(fs.readFileSync('web/src/i18n/catalog-manifest.json', 'utf8'));
const catalogs = Object.fromEntries(
  manifest.locales.map((entry) => [
    entry.catalog,
    JSON.parse(fs.readFileSync(`web/src/i18n/${entry.catalog}`, 'utf8')),
  ]),
);
const source = fs.readFileSync('web/src/i18n.js', 'utf8');

class FakeElement {
  constructor(attributes = {}) {
    this.attributes = { ...attributes };
    this.textContent = '';
  }

  getAttribute(name) {
    return this.attributes[name] || null;
  }

  matches(selector) {
    const match = /^\[([a-z0-9-]+)\]$/i.exec(selector);
    return Boolean(match && this.getAttribute(match[1]) != null);
  }

  querySelectorAll() {
    return [];
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
}

function createBrowser(options = {}) {
  const tab = new FakeElement({ 'data-i18n': 'tab.home' });
  const html = new FakeElement();
  const events = [];
  const document = {
    baseURI: 'https://app.munea.test/',
    currentScript: { src: 'https://app.munea.test/src/i18n.js' },
    documentElement: html,
    head: { appendChild() { throw new Error('preloaded test globals should avoid script injection'); } },
    title: '',
    createElement: () => new FakeElement(),
    querySelectorAll: (selector) => (selector === '[data-i18n]' ? [tab] : []),
  };
  const window = {
    MUNEA_DEV_CONFIG: options.devConfig || { enabled: false },
    MuneaCatalogRuntime: catalogRuntime,
    MuneaDomLocalizer: domLocalizer,
    dispatchEvent: (event) => events.push(event),
  };
  const fetch = async (url) => {
    const pathname = new URL(url).pathname;
    if (options.failFetch) throw new Error('offline');
    if (pathname.endsWith('/catalog-manifest.json')) {
      return { ok: true, json: async () => manifest };
    }
    const filename = pathname.split('/').pop();
    if (catalogs[filename]) return { ok: true, json: async () => catalogs[filename] };
    return { ok: false, status: 404, json: async () => ({}) };
  };
  function CustomEvent(type, init) {
    this.type = type;
    this.detail = init && init.detail;
  }
  const context = {
    console: { ...console, warn: () => {} },
    CustomEvent,
    document,
    fetch,
    navigator: { languages: options.languages || ['ja-JP', 'en-US'], language: 'ja-JP' },
    URL,
    window,
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'i18n.js' });
  return { document, events, html, tab, window };
}

(async () => {
  const production = createBrowser();
  const productionReady = await production.window.MuneaI18n.ready;
  assert.deepEqual({ ...productionReady }, { locale: 'zh-TW', fallback: false });
  assert.equal(
    production.window.MuneaI18n.current(),
    'zh-TW',
    'A device language must not bypass a disabled locale release gate',
  );
  assert.equal(production.tab.textContent, '首頁');
  assert.equal(production.html.getAttribute('lang'), 'zh-Hant-TW');
  assert.equal(production.window.MuneaI18n.setLocale('es'), 'zh-TW');

  const preview = createBrowser({
    devConfig: { enabled: true, i18nPreviewLocale: 'ja-JP' },
  });
  await preview.window.MuneaI18n.ready;
  assert.equal(preview.window.MuneaI18n.current(), 'ja');
  assert.equal(preview.tab.textContent, 'ホーム');
  assert.equal(preview.html.getAttribute('lang'), 'ja');
  assert.equal(preview.window.MuneaI18n.weatherLanguage(), 'ja');
  assert.deepEqual(
    Array.from(preview.window.MuneaI18n.preferredLanguages()),
    ['ja', 'en'],
  );
  const localeReady = preview.events.find((event) => event.type === 'munea:locale-ready');
  assert(localeReady, 'Browser bootstrap must announce locale readiness');
  assert.equal(localeReady.detail.preview, true);

  const fallback = createBrowser({ failFetch: true, languages: ['es-MX'] });
  const fallbackReady = await fallback.window.MuneaI18n.ready;
  assert.equal(fallbackReady.fallback, true);
  assert.equal(fallback.window.MuneaI18n.current(), 'zh-TW');
  assert.equal(fallback.tab.textContent, '首頁');

  console.log('PASS: browser i18n bootstrap follows device language and release gates');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
