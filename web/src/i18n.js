/* Munea locale runtime. Keep UI copy in keyed dictionaries; do not use UI text as a key. */
(function () {
  'use strict';

  const STORAGE_KEY = 'munea.locale.v1';
  const DEFAULT_LOCALE = 'zh-TW';
  const locales = {
    'zh-TW': { label: '繁體中文', htmlLang: 'zh-Hant-TW', weatherLanguage: 'zh' },
    en: { label: 'English', htmlLang: 'en', weatherLanguage: 'en' },
    ja: { label: '日本語', htmlLang: 'ja', weatherLanguage: 'ja' },
    es: { label: 'Español', htmlLang: 'es', weatherLanguage: 'es' },
  };
  const messages = {
    'zh-TW': { 'app.title': 'Munea 沐寧', 'settings.title': '設定', 'settings.language': '語言', 'settings.languageHint': '介面、日期格式與陪伴語言', 'tab.home': '首頁', 'tab.status': '狀態', 'tab.chat': '聊聊', 'tab.family': '家人', 'tab.settings': '設定', 'voice.connecting': '正在連線...', 'voice.ready': '直接說，我在這裡', 'voice.fallback': '我在這裡，今天過得好嗎？想聊什麼都可以。' },
    en: { 'app.title': 'Munea', 'settings.title': 'Settings', 'settings.language': 'Language', 'settings.languageHint': 'Interface, date formats, and companion language', 'tab.home': 'Home', 'tab.status': 'Health', 'tab.chat': 'Talk', 'tab.family': 'Family', 'tab.settings': 'Settings', 'voice.connecting': 'Connecting...', 'voice.ready': 'Just speak — I am here.', 'voice.fallback': 'I am here. How has your day been? We can talk about anything.' },
    ja: { 'app.title': 'Munea', 'settings.title': '設定', 'settings.language': '言語', 'settings.languageHint': '画面、日付形式、コンパニオンの言語', 'tab.home': 'ホーム', 'tab.status': '状態', 'tab.chat': '話す', 'tab.family': '家族', 'tab.settings': '設定', 'voice.connecting': '接続しています...', 'voice.ready': '話しかけてください。ここにいます。', 'voice.fallback': 'ここにいます。今日はどんな一日でしたか？何でも話してください。' },
    es: { 'app.title': 'Munea', 'settings.title': 'Ajustes', 'settings.language': 'Idioma', 'settings.languageHint': 'Interfaz, formato de fecha e idioma del acompañante', 'tab.home': 'Inicio', 'tab.status': 'Estado', 'tab.chat': 'Hablar', 'tab.family': 'Familia', 'tab.settings': 'Ajustes', 'voice.connecting': 'Conectando...', 'voice.ready': 'Habla cuando quieras; estoy aquí.', 'voice.fallback': 'Estoy aquí. ¿Cómo ha ido tu día? Podemos hablar de lo que quieras.' },
  };

  function normalize(locale) {
    const raw = String(locale || '').replace('_', '-');
    if (locales[raw]) return raw;
    const lower = raw.toLowerCase();
    if (lower.startsWith('zh')) return 'zh-TW';
    if (lower.startsWith('ja')) return 'ja';
    if (lower.startsWith('es')) return 'es';
    if (lower.startsWith('en')) return 'en';
    return DEFAULT_LOCALE;
  }
  function storedLocale() { try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; } }
  function current() { return normalize(storedLocale() || navigator.language || DEFAULT_LOCALE); }
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
    scope.querySelectorAll('[data-locale-select]').forEach((el) => { el.value = current(); });
  }
  function setLocale(locale, options) {
    const next = normalize(locale); const previous = current();
    try { localStorage.setItem(STORAGE_KEY, next); } catch (e) {}
    apply();
    if (next !== previous && !(options && options.silent)) window.dispatchEvent(new CustomEvent('munea:locale-change', { detail: { locale: next, previousLocale: previous } }));
    return next;
  }
  function preferredLanguages() { const selected = current(); return [selected].concat(Object.keys(locales).filter((locale) => locale !== selected)); }

  window.MuneaI18n = Object.freeze({ supported: Object.freeze({ ...locales }), current, normalize, setLocale, t, apply, preferredLanguages, weatherLanguage: () => locales[current()].weatherLanguage });
  document.addEventListener('DOMContentLoaded', () => { apply(); document.querySelectorAll('[data-locale-select]').forEach((el) => el.addEventListener('change', () => setLocale(el.value))); });
})();
