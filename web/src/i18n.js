/* Munea v1 ships in Traditional Chinese (Taiwan) only.
 * Keep this small API so callers stay stable until a complete localization ships. */
(function () {
  'use strict';

  const STORAGE_KEY = 'munea.locale.v1';
  const DEFAULT_LOCALE = 'zh-TW';
  const locales = {
    'zh-TW': { label: '繁體中文', htmlLang: 'zh-Hant-TW', weatherLanguage: 'zh' },
  };
  const messages = {
    'zh-TW': { 'app.title': 'Munea 沐寧', 'settings.title': '設定', 'tab.home': '首頁', 'tab.status': '狀態', 'tab.chat': '聊聊', 'tab.family': '家人', 'tab.settings': '設定', 'voice.connecting': '正在連線...', 'voice.ready': '直接說，我在這裡', 'voice.fallback': '我在這裡，今天過得好嗎？想聊什麼都可以。' },
  };

  function normalize() { return DEFAULT_LOCALE; }
  function current() { return DEFAULT_LOCALE; }
  function t(key, values, fallback) {
    let text = (messages[current()] && messages[current()][key]) || messages[DEFAULT_LOCALE][key] || fallback || key;
    Object.entries(values || {}).forEach(([name, value]) => { text = text.replaceAll(`{${name}}`, String(value)); });
    return text;
  }
  function apply(root) {
    const scope = root || document;
    document.documentElement.lang = locales[current()].htmlLang;
    document.title = t('app.title');
    scope.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n, null, el.textContent); });
  }
  function setLocale() {
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
    apply();
    return DEFAULT_LOCALE;
  }
  function preferredLanguages() { return [DEFAULT_LOCALE]; }

  window.MuneaI18n = Object.freeze({ supported: Object.freeze({ ...locales }), current, normalize, setLocale, t, apply, preferredLanguages, weatherLanguage: () => locales[current()].weatherLanguage });
  document.addEventListener('DOMContentLoaded', () => { setLocale(); });
})();
