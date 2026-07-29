"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web", "admin.html"), "utf8");
const runtime = fs.readFileSync(path.join(root, "web", "src", "admin-i18n.js"), "utf8");
const admin = fs.readFileSync(path.join(root, "web", "src", "admin.js"), "utf8");
const css = fs.readFileSync(path.join(root, "web", "src", "admin.css"), "utf8");
const locales = ["en", "ja", "es"];
const catalogs = Object.fromEntries(locales.map((locale) => [
  locale,
  JSON.parse(fs.readFileSync(path.join(root, "web", "src", "i18n", `admin-${locale}.json`), "utf8")),
]));
const han = /[\u3400-\u9fff\uf900-\ufaff]/u;

const englishKeys = Object.keys(catalogs.en.exact).sort();
const englishPatterns = catalogs.en.patterns.map((item) => item.source);
assert(englishKeys.length >= 180, "admin catalogs must cover the operational launch surfaces");
for (const locale of locales) {
  const catalog = catalogs[locale];
  assert.equal(catalog.locale, locale);
  assert.deepStrictEqual(
    Object.keys(catalog.exact).sort(),
    englishKeys,
    `${locale} admin exact-copy keys must match English`,
  );
  assert.deepStrictEqual(
    catalog.patterns.map((item) => item.source),
    englishPatterns,
    `${locale} admin dynamic-copy patterns must match English`,
  );
  for (const [source, target] of Object.entries(catalog.exact)) {
    if (locale !== "ja") {
      assert.notEqual(target.trim(), source.trim(), `${locale} must translate: ${source}`);
    }
    assert(target.trim(), `${locale} translation must not be empty: ${source}`);
  }
}

for (const locale of ["en", "es"]) {
  for (const [source, target] of Object.entries(catalogs[locale].exact)) {
    assert(!han.test(target), `${locale} translation still contains Han copy for: ${source}`);
  }
  for (const item of catalogs[locale].patterns) {
    assert(!han.test(item.target), `${locale} pattern still contains Han copy: ${item.source}`);
  }
}

for (const source of [
  "營運後台",
  "總覽儀表板",
  "用戶管理",
  "安全守護警示",
  "訂閱與點數",
  "國家／地區",
  "App 操作語言",
  "陪伴聊天語言",
  "安全／法律區域",
  "資料區域",
]) {
  for (const locale of locales) {
    assert(catalogs[locale].exact[source], `${locale} missing critical admin copy: ${source}`);
  }
}

assert(
  html.indexOf("src/admin-i18n.js") < html.indexOf("src/admin.js"),
  "admin locale runtime must load before the application",
);
assert(runtime.includes("LOCAL_HOST_RE.test(location.hostname)"));
assert(runtime.includes('new URLSearchParams(location.search).get("lang")'));
assert(
  !runtime.includes("localStorage") && !runtime.includes("sessionStorage"),
  "admin UI locale must follow the browser and must not create a hidden language preference",
);
assert(runtime.includes("MutationObserver"), "dynamic admin renders must be localized");
assert(
  runtime.includes('"data-label"'),
  "mobile table pseudo-labels must be translated with the visible table content",
);
assert(
  runtime.includes("translated === normalizedText(raw)"),
  "same-text Japanese translations must not trigger an observer rewrite loop",
);
assert(runtime.includes("audit,"), "runtime must expose an untranslated-copy audit for browser QA");
assert(runtime.includes("data-i18n-skip"), "the runtime must support excluding user-provided content");
assert(runtime.includes("data.i18nError") || runtime.includes("dataset.i18nError"));
assert(css.includes("html.admin-i18n-pending body"), "mixed-language paint must be hidden while the catalog loads");
assert(css.includes("overflow-wrap: anywhere"), "long English and Spanish labels must wrap safely");
assert(admin.includes("window.MuneaAdminI18n.current()"), "admin date formatting must follow the operator locale");
assert(admin.includes("Intl.DateTimeFormat().resolvedOptions().timeZone"), "admin dates must follow the operator time zone");
assert(
  admin.includes('uiLocale:ctx.uiLocale||a.locale||"—"')
    && admin.includes('conversationLocale:ctx.conversationLocale||p.locale||a.locale||"—"'),
  "missing language data must remain unknown instead of defaulting to Traditional Chinese",
);
assert(
  admin.includes("Promise.resolve(window.MuneaAdminI18n && window.MuneaAdminI18n.ready)"),
  "admin initialization must wait for the locale catalog",
);

console.log(`Admin localization contract OK (${englishKeys.length} exact strings, ${englishPatterns.length} patterns, ${locales.length + 1} locales)`);
