'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const catalogRuntime = require('../web/src/i18n/catalog-runtime.js');
const domLocalizer = require('../web/src/i18n/dom-localizer.js');
const appBindingRuntime = require('../web/src/i18n/app-binding-runtime.js');

const manifest = JSON.parse(fs.readFileSync('web/src/i18n/catalog-manifest.json', 'utf8'));
const bindingManifest = JSON.parse(
  fs.readFileSync('web/src/i18n/app-binding-manifest.json', 'utf8'),
);
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

  querySelector() {
    return null;
  }

  contains(node) {
    return this === node;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
}

function createBrowser(options = {}) {
  const tab = new FakeElement({ 'data-i18n': 'tab.home' });
  const html = new FakeElement();
  const signIn = new FakeElement();
  const events = [];
  const observations = [];
  class FakeMutationObserver {
    constructor(callback) {
      this.callback = callback;
    }

    observe(target, observerOptions) {
      observations.push({ observer: this, observerOptions, target });
    }

    disconnect() {}
  }
  const browserDomLocalizer = {
    ...domLocalizer,
    observe: (root, runtime, localeFor, valuesFor) => domLocalizer.observe(
      root,
      runtime,
      localeFor,
      valuesFor,
      FakeMutationObserver,
    ),
  };
  const document = {
    baseURI: 'https://app.munea.test/',
    currentScript: { src: 'https://app.munea.test/src/i18n.js' },
    documentElement: html,
    getElementById: (id) => (id === 'authSignInBtn' ? signIn : null),
    head: { appendChild() { throw new Error('preloaded test globals should avoid script injection'); } },
    title: '',
    createElement: () => new FakeElement(),
    querySelectorAll: (selector) => (selector === '[data-i18n]' ? [tab] : []),
  };
  const window = {
    MUNEA_DEV_CONFIG: options.devConfig || { enabled: false },
    MuneaCatalogRuntime: catalogRuntime,
    MuneaDomLocalizer: browserDomLocalizer,
    MuneaAppBindingRuntime: appBindingRuntime,
    dispatchEvent: (event) => events.push(event),
  };
  const fetch = async (url) => {
    const pathname = new URL(url).pathname;
    if (options.failFetch) throw new Error('offline');
    if (pathname.endsWith('/catalog-manifest.json')) {
      return { ok: true, json: async () => manifest };
    }
    if (pathname.endsWith('/app-binding-manifest.json')) {
      return { ok: true, json: async () => bindingManifest };
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
    MutationObserver: FakeMutationObserver,
    URL,
    window,
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'i18n.js' });
  return { document, events, html, observations, signIn, tab, window };
}

// 開了哪些語系跟著開關表走，別在測試裡寫死清單——寫死的話語系一開這裡就紅，
// 而紅的原因跟「程式對不對」無關，只是清單過期。（2026-08-01 三語開通當晚踩到）
const enabled = new Set(
  manifest.locales.filter((entry) => entry.runtimeEnabled).map((entry) => entry.locale),
);
// 每個語系各挑一句，用來驗「畫面真的換成那個語言」
const HOME_TAB = { 'zh-TW': '首頁', ja: 'ホーム', en: 'Home', es: 'Inicio' };
const HTML_LANG = { 'zh-TW': 'zh-Hant-TW', ja: 'ja', en: 'en', es: 'es' };

(async () => {
  // 這條規矩不管開幾種語系都要成立：**目錄裡沒有的語言一律退回繁中**。
  // 用德文來守，因為德文永遠不在四語裡，不會因為開關變動而失效。
  const unsupported = createBrowser({ languages: ['de-DE'] });
  await unsupported.window.MuneaI18n.ready;
  assert.equal(
    unsupported.window.MuneaI18n.current(),
    'zh-TW',
    '沒收錄的裝置語言必須退回繁中，不能繞過關卡',
  );

  // 裝置語言是 ja-JP／en-US：日文開著就該落在日文，沒開就退回繁中
  const production = createBrowser();
  const productionReady = await production.window.MuneaI18n.ready;
  const shown = enabled.has('ja') ? 'ja' : 'zh-TW';
  assert.deepEqual({ ...productionReady }, { locale: shown, fallback: false });
  assert.equal(
    production.window.MuneaI18n.current(),
    shown,
    `裝置語言 ja-JP 在日文${enabled.has('ja') ? '已開' : '未開'}時應落在 ${shown}`,
  );
  assert.equal(production.tab.textContent, HOME_TAB[shown]);
  assert.equal(production.html.getAttribute('lang'), HTML_LANG[shown]);
  assert.equal(production.observations.length, 2, 'Dynamic and declarative App content must be observed');
  const dynamicObservation = production.observations.find(
    ({ observerOptions }) => Array.isArray(observerOptions.attributeFilter),
  );
  assert(dynamicObservation, 'Dynamic data-i18n observer is missing');
  const dynamic = new FakeElement({ 'data-i18n': 'notification.centerTitle' });
  dynamicObservation.observer.callback([
    { type: 'childList', addedNodes: [dynamic] },
  ]);
  assert.equal(
    dynamic.textContent,
    catalogs[`${shown}.json`]['notification.centerTitle'],
    '後來才長出來的畫面元素也要跟著當前語言',
  );
  // setLocale 刻意不接受呼叫端指定語言（見 i18n.js 的註解）：
  // 介面語言只跟著 iPhone 的「設定 → Munea → 語言」走，App 內部沒有語言切換鈕。
  // 所以不管傳什麼進去，都必須回到「裝置決定的那個語言」——這是防止程式碼某處
  // 偷偷把使用者切到別的語言。
  for (const attempt of ['es', 'de', 'zh-TW']) {
    assert.equal(
      production.window.MuneaI18n.setLocale(attempt),
      shown,
      `setLocale('${attempt}') 必須被忽略、維持裝置決定的 ${shown}——語言只由系統設定決定`,
    );
  }

  const preview = createBrowser({
    devConfig: { enabled: true, i18nPreviewLocale: 'ja-JP' },
  });
  preview.window.MUNEA_DEV_CONFIG = {
    enabled: true,
    voiceUrl: 'https://voice.example.test',
  };
  await preview.window.MuneaI18n.ready;
  assert.equal(preview.window.MuneaI18n.current(), 'ja');
  assert.equal(preview.tab.textContent, 'ホーム');
  assert.equal(preview.signIn.textContent, 'ログイン');
  assert.equal(preview.html.getAttribute('lang'), 'ja');
  assert.equal(preview.window.MuneaI18n.weatherLanguage(), 'ja');
  assert.deepEqual(
    Array.from(preview.window.MuneaI18n.preferredLanguages()),
    ['ja', 'en'],
  );
  const localeReady = preview.events.find((event) => event.type === 'munea:locale-ready');
  assert(localeReady, 'Browser bootstrap must announce locale readiness');
  assert.equal(localeReady.detail.preview, true);

  // 連不到網路、文案表載不下來時，必須退回內建的繁中，不能整個畫面空白。
  // 這條跟開幾種語系無關——載不到就是載不到，一律走內建那份。
  const fallback = createBrowser({ failFetch: true, languages: ['es-MX'] });
  const fallbackReady = await fallback.window.MuneaI18n.ready;
  assert.equal(fallbackReady.fallback, true, '載不到文案表時必須標成 fallback');
  assert.equal(
    fallback.window.MuneaI18n.current(),
    'zh-TW',
    '載不到文案表就只剩內建繁中，不論裝置語言是什麼',
  );
  assert.equal(fallback.tab.textContent, '首頁');

  console.log('PASS: browser i18n bootstrap follows device language and release gates');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
