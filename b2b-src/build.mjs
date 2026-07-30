#!/usr/bin/env node
/**
 * 沐寧 B2B 合作頁 · 四語系靜態頁產生器
 * ------------------------------------------------------------------
 * 一份版型（b2b-src/index.html）＋ 四份文案表（b2b-src/i18n/*.json）
 *   →  產出 munea-b2b/index.html（中）、/en/、/ja/、/es/
 *
 * 跟官網（site-src/build.mjs）同一套做法，理由也一樣：
 *   四個真網址＋hreflang 互指，四個語系才各自被搜尋引擎看得到；
 *   靠 JS 當場切換的話，Google 永遠只收錄中文那一份。
 *
 * 原料放在 munea-b2b 外面：那個資料夾整包會被 Vercel 發佈出去。
 *
 * 用法：npm run b2b:build（＝ node b2b-src/build.mjs）
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = dirname(fileURLToPath(import.meta.url));
const OUT = join(SRC, '..', 'munea-b2b');

const config = JSON.parse(readFileSync(join(SRC, 'config.json'), 'utf8'));
const template = readFileSync(join(SRC, 'index.html'), 'utf8');

/* 中文字型一種粗細約 500KB，Sans 四種＋Serif 三種就快 2MB。
 * 只有中文頁需要，英日西頁載了也用不到 —— 所以字型跟著語系給。
 * 日文頁不另外載 Google 日文字型（一樣是 MB 起跳），改用系統內建的日文字型，
 * 手機與桌機都有、字重也夠，讀起來乾淨。 */
const FONT_LATIN = 'family=Poppins:wght@400;500;600;700';
const FONT_TC =
  'family=Poppins:wght@400;500;600;700' +
  '&family=Noto+Sans+TC:wght@400;500;700;900' +
  '&family=Noto+Serif+TC:wght@500;600;700';
const fontLink = (families) =>
  `<link href="https://fonts.googleapis.com/css2?${families}&display=swap" rel="stylesheet">`;

const VARS_TC =
  '--f-body:"Noto Sans TC","Poppins",sans-serif; ' +
  '--f-head:"Poppins","Noto Sans TC",sans-serif; ' +
  '--f-serif:"Noto Serif TC",serif; ' +
  '--wb:keep-all;';
const VARS_LATIN =
  '--f-body:"Poppins",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; ' +
  '--f-head:"Poppins",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; ' +
  '--f-serif:Georgia,"Times New Roman",serif; ' +
  '--wb:normal;';
const VARS_JA =
  '--f-body:"Poppins","Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic","Noto Sans JP",Meiryo,sans-serif; ' +
  '--f-head:"Poppins","Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic","Noto Sans JP",Meiryo,sans-serif; ' +
  '--f-serif:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",serif; ' +
  '--wb:normal;';

/** 語系設定：dir = 產出的資料夾（中文放根目錄） */
const LOCALES = [
  { code: 'zh', dir: '', htmlLang: 'zh-Hant', hreflang: 'zh-Hant', ogLocale: 'zh_TW', fonts: FONT_TC, vars: VARS_TC },
  { code: 'en', dir: 'en', htmlLang: 'en', hreflang: 'en', ogLocale: 'en_US', fonts: FONT_LATIN, vars: VARS_LATIN },
  { code: 'ja', dir: 'ja', htmlLang: 'ja', hreflang: 'ja', ogLocale: 'ja_JP', fonts: FONT_LATIN, vars: VARS_JA },
  { code: 'es', dir: 'es', htmlLang: 'es', hreflang: 'es', ogLocale: 'es_ES', fonts: FONT_LATIN, vars: VARS_LATIN },
];

const SITE = config.siteUrl.replace(/\/$/, '');
// 對外網址一律不帶尾斜線（canonical / hreflang / sitemap / 語言選單都用同一個寫法），
// 免得同一頁被搜尋引擎當成兩個網址。
const urlFor = (dir) => (dir ? `${SITE}/${dir}` : `${SITE}/`);

/** hreflang 互指（x-default 指中文版） */
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

let built = 0;
for (const l of LOCALES) {
  const dict = JSON.parse(readFileSync(join(SRC, 'i18n', `${l.code}.json`), 'utf8'));

  // 頁面 JS 要用到的字，整包丟成一個 JS 物件（JSON.stringify 會把引號跳脫好，
  // 西班牙文的 ¿ ' 這種字元不會把程式碼弄壞）
  const jsDict = {};
  for (const [k, v] of Object.entries(dict)) {
    if (k.startsWith('js.')) jsDict[k.slice(3)] = v;
  }

  const vars = {
    ...dict,
    'js.dict': JSON.stringify(jsDict),
    'meta.htmlLang': l.htmlLang,
    'meta.langCode': l.code,
    'meta.fonts': fontLink(l.fonts),
    'meta.fontVars': l.vars,
    'meta.canonical': urlFor(l.dir),
    'meta.ogLocale': l.ogLocale,
    'meta.ogAlternates': ogAlternates(l.code),
    'meta.hreflang': hreflangBlock(),
    'meta.langMenu': langMenu(l.code),
    'meta.langCurrent': config.langLabels[l.code].short,
    'meta.siteUrl': SITE,
  };

  const html = render(template, vars, l.code);
  const dir = l.dir ? join(OUT, l.dir) : OUT;
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'index.html'), html, 'utf8');
  console.log(`  ✓ ${l.dir ? `/${l.dir}` : '/'}  ${(html.length / 1024).toFixed(0)}KB  (${l.htmlLang})`);
  built++;
}

/* ── sitemap：四個語系全列，每筆帶 hreflang 互指 ── */
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
</urlset>
`;
writeFileSync(join(OUT, 'sitemap.xml'), sitemap, 'utf8');

writeFileSync(
  join(OUT, 'robots.txt'),
  `User-agent: *\nAllow: /\n\nSitemap: ${SITE}/sitemap.xml\n`,
  'utf8'
);

console.log(`  ✓ sitemap.xml + robots.txt（${LOCALES.length} 語系）`);

/* ── 保險絲：產出的頁面不該還留著沒換掉的 {{ }} ── */
let leftoverFound = false;
for (const l of LOCALES) {
  const p = join(l.dir ? join(OUT, l.dir) : OUT, 'index.html');
  const leftover = readFileSync(p, 'utf8').match(/\{\{[^}]+\}\}/g);
  if (leftover) {
    console.error(`✗ ${p} 還有沒換掉的標記：${leftover.slice(0, 5).join(', ')}`);
    leftoverFound = true;
  }
}
if (leftoverFound) process.exitCode = 1;
else console.log(`\n完成：${built} 個語系，四個真網址（/ · /en · /ja · /es）\n`);
