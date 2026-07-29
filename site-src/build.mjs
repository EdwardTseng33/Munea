#!/usr/bin/env node
/**
 * 沐寧官網 · 四語系靜態頁產生器
 * ------------------------------------------------------------------
 * 一份版型（site-src/index.html）＋ 四份文案表（site-src/i18n/*.json）
 *   →  產出 app-site/index.html（中）、/en/、/ja/、/es/
 *
 * 為什麼原料放在 app-site 外面：app-site 整個資料夾都會被發佈到網路上。
 * 版型與文案表放進去，就算設了排除規則也可能哪天被繞過；放外面＝結構上不可能外流。
 *
 * 為什麼要產生成四個網址、而不是用 JS 當場切換：
 *   Google 只會收錄它「看得到的那一份」。舊做法把英文藏在標籤屬性裡、
 *   靠瀏覽器切換，搜尋引擎永遠只看到中文版 —— 英日西做了也沒人搜得到。
 *   四個真網址＋hreflang 互指，四個語系才各自有搜尋價值。
 *
 * 用法：node site-src/build.mjs
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = dirname(fileURLToPath(import.meta.url));
const OUT = join(SRC, '..', 'app-site');

const config = JSON.parse(readFileSync(join(SRC, 'config.json'), 'utf8'));
const template = readFileSync(join(SRC, 'index.html'), 'utf8');

/* 字型是這個頁面最重的一塊（中文字型一套就近 2MB）。
 * 中文頁才需要 Noto Sans/Serif TC；英日西頁只要 Poppins，
 * 標誌裡那兩個中文字交給系統字型就好 —— 光這一刀，非中文頁少扛約 2MB。 */
const LATIN_ONLY = 'family=Poppins:wght@400;500;600;700';
// 中文字型一種粗細就約 500KB（Google 會切成上百個小塊丟給瀏覽器）。
// 原本載了 Sans 四種＋Serif 三種＝七套，光字型就近 2MB。
// 中文只留「內文 400 ＋ 標題 700」、襯線只留 600；
// 樣式表裡寫 500/600 的地方由瀏覽器就近取用，中文字看不出差別。
const WITH_TC =
  'family=Poppins:wght@400;500;600;700' +
  '&family=Noto+Sans+TC:wght@400;700' +
  '&family=Noto+Serif+TC:wght@600';
const fontLink = (families) =>
  `<link href="https://fonts.googleapis.com/css2?${families}&display=swap" rel="stylesheet">`;

/** 語系設定：dir = 產出的資料夾（中文放根目錄）  */
const LOCALES = [
  { code: 'zh', dir: '', htmlLang: 'zh-Hant-TW', hreflang: 'zh-Hant', ogLocale: 'zh_TW', fonts: WITH_TC },
  { code: 'en', dir: 'en', htmlLang: 'en', hreflang: 'en', ogLocale: 'en_US', fonts: LATIN_ONLY },
  { code: 'ja', dir: 'ja', htmlLang: 'ja', hreflang: 'ja', ogLocale: 'ja_JP', fonts: LATIN_ONLY },
  { code: 'es', dir: 'es', htmlLang: 'es', hreflang: 'es', ogLocale: 'es_ES', fonts: LATIN_ONLY },
];

const SITE = config.siteUrl.replace(/\/$/, '');
// 主機設定是 trailingSlash:false —— /en/ 會被 301 轉到 /en。
// 對外網址（canonical / hreflang / sitemap / 語言選單）一律用不帶尾斜線的那個，
// 否則 Google 收到的每個語系網址都會先吃一次轉址。
const urlFor = (dir) => (dir ? `${SITE}/${dir}` : `${SITE}/`);

/** 產生 hreflang 互指區塊（含 x-default 指向中文版） */
function hreflangBlock() {
  const rows = LOCALES.map(
    (l) => `<link rel="alternate" hreflang="${l.hreflang}" href="${urlFor(l.dir)}">`
  );
  rows.push(`<link rel="alternate" hreflang="x-default" href="${urlFor('')}">`);
  return rows.join('\n');
}

/** 語言選單：目前語系標勾、其他語系連到對應網址 */
function langMenu(active) {
  return LOCALES.map((l) => {
    const label = config.langLabels[l.code];
    const cls = l.code === active ? 'lang-opt is-active' : 'lang-opt';
    const sel = l.code === active ? 'true' : 'false';
    return (
      `<a class="${cls}" role="option" aria-selected="${sel}" hreflang="${l.hreflang}" ` +
      `href="${urlFor(l.dir)}"><span class="tick"></span>${label.native}<span class="sub">${label.short}</span></a>`
    );
  }).join('\n          ');
}

/** og:locale:alternate —— 告訴社群平台這頁還有哪些語言 */
function ogAlternates(active) {
  return LOCALES.filter((l) => l.code !== active)
    .map((l) => `<meta property="og:locale:alternate" content="${l.ogLocale}">`)
    .join('\n');
}

/** 把 {{key}} 換成該語系的字。找不到的 key 一律報錯，不靜默漏字。 */
function render(tpl, dict, localeCode) {
  const missing = new Set();
  const out = tpl.replace(/\{\{([a-zA-Z0-9_.]+)\}\}/g, (_, key) => {
    if (Object.prototype.hasOwnProperty.call(dict, key)) return dict[key];
    missing.add(key);
    return '';
  });
  if (missing.size) {
    throw new Error(
      `[${localeCode}] 文案表少了 ${missing.size} 個 key：\n  ` + [...missing].join('\n  ')
    );
  }
  return out;
}

/** App Store 還沒過審時，下載鍵改成「即將上架」——絕不留死連結 */
function ctaVars(dict) {
  const live = Boolean(config.appStoreUrl && config.appStoreUrl.trim());
  if (live) {
    return {
      'cta.href': config.appStoreUrl,
      'cta.tagOpen': `<a class="btn btn-appstore" href="${config.appStoreUrl}" target="_blank" rel="noopener"`,
      'cta.tagClose': '</a>',
      'cta.small': dict['cta.onAppStore'],
      'cta.big': dict['cta.freeDownload'],
      'cta.navLabel': dict['cta.freeDownload'],
      'cta.state': 'live',
    };
  }
  return {
    'cta.href': '#download',
    'cta.tagOpen': '<a class="btn btn-appstore is-soon" href="#download"',
    'cta.tagClose': '</a>',
    'cta.small': dict['cta.comingSoonSmall'],
    'cta.big': dict['cta.comingSoonBig'],
    'cta.navLabel': dict['cta.comingSoonBig'],
    'cta.state': 'soon',
  };
}

let built = 0;
for (const l of LOCALES) {
  const dict = JSON.parse(readFileSync(join(SRC, 'i18n', `${l.code}.json`), 'utf8'));

  const vars = {
    ...dict,
    ...ctaVars(dict),
    'meta.htmlLang': l.htmlLang,
    'meta.fonts': fontLink(l.fonts),
    'meta.canonical': urlFor(l.dir),
    'meta.ogLocale': l.ogLocale,
    'meta.ogAlternates': ogAlternates(l.code),
    'meta.hreflang': hreflangBlock(),
    'meta.langMenu': langMenu(l.code),
    'meta.langCurrent': config.langLabels[l.code].short,
    'meta.year': String(config.year),
    'meta.contactEmail': config.contactEmail,
    'meta.b2bUrl': config.b2bUrl,
    'meta.siteUrl': SITE,
    'meta.ogImage': `${SITE}/assets/og-image.jpg`,
  };

  const html = render(template, vars, l.code);
  const dir = l.dir ? join(OUT, l.dir) : OUT;
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'index.html'), html, 'utf8');
  console.log(`  ✓ ${l.dir ? `/${l.dir}/` : '/'}  ${(html.length / 1024).toFixed(0)}KB  (${l.htmlLang})`);
  built++;
}

/* ── sitemap：四個語系全列，每筆帶 hreflang 互指 ── */
const legalPages = ['privacy', 'terms', 'support'];
const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
${LOCALES.map(
  (l) => `  <url>
    <loc>${urlFor(l.dir)}</loc>
${LOCALES.map((a) => `    <xhtml:link rel="alternate" hreflang="${a.hreflang}" href="${urlFor(a.dir)}"/>`).join('\n')}
    <xhtml:link rel="alternate" hreflang="x-default" href="${urlFor('')}"/>
    <changefreq>weekly</changefreq><priority>1.0</priority>
  </url>`
).join('\n')}
${legalPages
  .map((p) => `  <url><loc>${SITE}/${p}</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>`)
  .join('\n')}
</urlset>
`;
writeFileSync(join(OUT, 'sitemap.xml'), sitemap, 'utf8');

console.log(`  ✓ sitemap.xml（${LOCALES.length} 語系 + ${legalPages.length} 條款頁）`);
console.log(
  `\n完成：${built} 個語系。下載鍵狀態＝${config.appStoreUrl ? 'App Store 正式連結' : '即將上架（App 尚未過審）'}\n`
);

/* ── 保險絲：產出的頁面不該還留著沒換掉的 {{ }} ── */
for (const l of LOCALES) {
  const p = join(l.dir ? join(OUT, l.dir) : OUT, 'index.html');
  const leftover = readFileSync(p, 'utf8').match(/\{\{[^}]+\}\}/g);
  if (leftover) {
    console.error(`✗ ${p} 還有沒換掉的標記：${leftover.slice(0, 5).join(', ')}`);
    process.exitCode = 1;
  }
}
