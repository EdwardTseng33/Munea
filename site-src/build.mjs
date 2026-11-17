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
import { loadGuides, esc } from './guides.mjs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = dirname(fileURLToPath(import.meta.url));
const OUT = join(SRC, '..', 'app-site');

const config = JSON.parse(readFileSync(join(SRC, 'config.json'), 'utf8'));

/** 要產生的頁面：首頁＋「給照護機構」短頁（2026-11-05 Edward：官網與 B2B 分開，官網只開一頁介紹機構方案）。
 *  slug＝語系資料夾底下的子路徑；網址一律不帶尾斜線（/for-organizations、/en/for-organizations）。 */
const PAGES = [
  { id: 'home', template: 'index.html', slug: '' },
  { id: 'org', template: 'org.html', slug: 'for-organizations' },
];

/* 字型是這個頁面最重的一塊（中文字型一套就近 2MB）。
 * 中文頁才需要 Noto Sans/Serif TC；英日西頁只要 Poppins，
 * 標誌裡那兩個中文字交給系統字型就好 —— 光這一刀，非中文頁少扛約 2MB。 */
const LATIN_ONLY = 'family=Poppins:wght@400;500;600;700&family=Noto+Serif:wght@500;600';
// 日文：Google 會依頁面實際用到的字切小塊下載，不會整套 2MB 都拉
const WITH_JP =
  'family=Poppins:wght@400;500;600;700' +
  '&family=Noto+Sans+JP:wght@400;700' +
  '&family=Noto+Serif+JP:wght@600';
// 中文字型一種粗細就約 500KB（Google 會切成上百個小塊丟給瀏覽器）。
// 原本載了 Sans 四種＋Serif 三種＝七套，光字型就近 2MB。
// 中文只留「內文 400 ＋ 標題 700」、襯線只留 600；
// 樣式表裡寫 500/600 的地方由瀏覽器就近取用，中文字看不出差別。
const WITH_TC =
  'family=Poppins:wght@400;500;600;700' +
  '&family=Noto+Sans+TC:wght@400;700' +
  '&family=Noto+Serif+TC:wght@600';
/* 2026-11-18：字型改成「不擋第一次畫面」。
 * 原本字型樣式表是同步載入，慢網路（Slow 4G＋手機 CPU 慢 4 倍）下中文首頁要 4.7 秒才畫出第一個字；
 * 拿掉這個阻擋，同條件 2.3 秒。做法：
 *   - Poppins（品牌字 Munea、英文標題）：swap——到了就換上，拉丁字寬差異小；
 *   - 中日文字型與襯線：optional——第一次來訪若沒在極短時間內到，就整頁用系統字型（iPhone 是蘋方），
 *     不中途換字、不會整段跳動；第二次來訪已在快取，直接用品牌字型。 */
const fontLink = (families) => {
  const parts = families.split('&');
  const latin = parts.filter((p) => p.startsWith('family=Poppins'));
  const rest = parts.filter((p) => !p.startsWith('family=Poppins'));
  const urls = [
    `https://fonts.googleapis.com/css2?${latin.join('&')}&display=swap`,
    ...(rest.length ? [`https://fonts.googleapis.com/css2?${rest.join('&')}&display=optional`] : []),
  ];
  return (
    urls.map((u) => `<link rel="preload" as="style" href="${u}" onload="this.onload=null;this.rel='stylesheet'">`).join('\n') +
    `\n<noscript>${urls.map((u) => `<link rel="stylesheet" href="${u}">`).join('')}</noscript>`
  );
};

/** 語系設定：dir = 產出的資料夾（中文放根目錄）  */
const LOCALES = [
  { code: 'zh', dir: '', htmlLang: 'zh-Hant-TW', hreflang: 'zh-Hant', ogLocale: 'zh_TW', fonts: WITH_TC },
  { code: 'en', dir: 'en', htmlLang: 'en', hreflang: 'en', ogLocale: 'en_US', fonts: LATIN_ONLY },
  { code: 'ja', dir: 'ja', htmlLang: 'ja', hreflang: 'ja', ogLocale: 'ja_JP', fonts: WITH_JP },
  { code: 'es', dir: 'es', htmlLang: 'es', hreflang: 'es', ogLocale: 'es_ES', fonts: LATIN_ONLY },
];

const SITE = config.siteUrl.replace(/\/$/, '');
// 主機設定是 trailingSlash:false —— /en/ 會被 301 轉到 /en。
// 對外網址（canonical / hreflang / sitemap / 語言選單）一律用不帶尾斜線的那個，
// 否則 Google 收到的每個語系網址都會先吃一次轉址。
const urlFor = (dir, slug = '') => {
  const path = [dir, slug].filter(Boolean).join('/');
  return path ? `${SITE}/${path}` : `${SITE}/`;
};

/** 產生 hreflang 互指區塊（含 x-default 指向中文版） */
function hreflangBlock(slug = '') {
  const rows = LOCALES.map(
    (l) => `<link rel="alternate" hreflang="${l.hreflang}" href="${urlFor(l.dir, slug)}">`
  );
  rows.push(`<link rel="alternate" hreflang="x-default" href="${urlFor('', slug)}">`);
  return rows.join('\n');
}

/** 語言選單：目前語系標勾、其他語系連到同一頁的對應語言網址 */
function langMenu(active, slug = '') {
  return LOCALES.map((l) => {
    const label = config.langLabels[l.code];
    const cls = l.code === active ? 'lang-opt is-active' : 'lang-opt';
    const sel = l.code === active ? 'true' : 'false';
    return (
      `<a class="${cls}" role="option" aria-selected="${sel}" hreflang="${l.hreflang}" ` +
      `href="${urlFor(l.dir, slug)}"><span class="tick"></span>${label.native}<span class="sub">${label.short}</span></a>`
    );
  }).join('\n          ');
}

/** B2B 網站的同語系網址（B2B 也是中文在根目錄、其他語系 /en /ja /es，不帶尾斜線） */
const b2bUrlFor = (dir) => {
  const base = config.b2bUrl.replace(/\/$/, '');
  return dir ? `${base}/${dir}` : `${base}/`;
};

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
      'cta.navHref': config.appStoreUrl,
      'cta.navAttrs': ' target=\"_blank\" rel=\"noopener\"',
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
    'cta.navHref': '#download',
    'cta.navAttrs': '',
    'cta.state': 'soon',
  };
}

/**
 * 常見問題 → FAQPage 結構化資料（給 Google 與 AI 搜尋讀）。
 * 問答只寫一次（文案表的 faq.1.q／faq.1.a…），頁面上看得到的字跟結構化資料逐字相同，
 * Google 規定兩邊要一致。問答一律純文字：出現 < 或 & 直接報錯，免得頁面和 JSON 兩邊對不上。
 */
function faqJsonLd(dict, localeCode, htmlLang) {
  const entities = [];
  for (let i = 1; Object.prototype.hasOwnProperty.call(dict, `faq.${i}.q`); i++) {
    const q = dict[`faq.${i}.q`];
    const a = dict[`faq.${i}.a`];
    if (!a) throw new Error(`[${localeCode}] faq.${i}.q 有問題、卻少了 faq.${i}.a`);
    for (const [k, v] of [[`faq.${i}.q`, q], [`faq.${i}.a`, a]]) {
      if (/[<>&]/.test(v)) throw new Error(`[${localeCode}] ${k} 要是純文字（不可含 < > &）`);
    }
    entities.push({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } });
  }
  if (!entities.length) throw new Error(`[${localeCode}] 文案表沒有任何 faq.N.q`);
  const data = { '@context': 'https://schema.org', '@type': 'FAQPage', inLanguage: htmlLang, mainEntity: entities };
  // 防止內容裡出現 </script> 提早關掉標籤
  return JSON.stringify(data).replace(/</g, '\\u003c');
}

/** 常見問題的頁面 HTML（跟 faqJsonLd 同一份資料；第一題預設展開） */
function faqHtml(dict) {
  const items = [];
  for (let i = 1; Object.prototype.hasOwnProperty.call(dict, `faq.${i}.q`); i++) {
    items.push(
      `      <details class="faq-item"${i === 1 ? ' open' : ''}>\n` +
      `        <summary><span class="fq"><b>Q${i}</b><span>${dict[`faq.${i}.q`]}</span></span><span class="fx" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg></span></summary>\n` +
      `        <p class="fa">${dict[`faq.${i}.a`]}</p>\n` +
      `      </details>`
    );
  }
  return items.join('\n');
}

/* ── 指南：有文章的語系才產生（西文暫無） ── */
const GUIDES = Object.fromEntries(LOCALES.map((l) => [l.code, loadGuides(SRC, l.code)]));
const hasGuides = (code) => GUIDES[code].length > 0;
const guideUrl = (l, slug = '') => urlFor(l.dir, slug ? `guide/${slug}` : 'guide');
/** 首頁「指南」區塊挑哪三篇（照搜尋字研究的優先序；沒列到就取最新三篇） */
const FEATURED = {
  zh: ['topics-to-talk-with-elderly-parents', 'iphone-medication-reminder-for-parents', 'parents-living-alone-7-things'],
  en: ['ai-companion-for-seniors', 'check-in-on-elderly-parent-living-alone', 'elliq-alternatives'],
  ja: ['mimamori-app-guide', 'ai-hanashiaite-elderly', 'talking-with-elderly-parents-far-away'],
};
function featured(code) {
  const all = GUIDES[code];
  const pick = (FEATURED[code] || []).map((s) => all.find((g) => g.slug === s)).filter(Boolean);
  for (const g of all) if (pick.length < 3 && !pick.includes(g)) pick.push(g);
  return pick.slice(0, 3);
}
const guideCard = (l, g, dict) =>
  `        <a class="g-card" href="${guideUrl(l, g.slug)}"><b>${esc(g.title)}</b><span>${esc(g.description)}</span>` +
  (dict ? `<small>${dict['guide.read'].replace('{n}', g.readingMinutes)}</small>` : '') + `</a>`;

let built = 0;
for (const l of LOCALES) {
  const dict = JSON.parse(readFileSync(join(SRC, 'i18n', `${l.code}.json`), 'utf8'));

  const vars = {
    ...dict,
    ...ctaVars(dict),
    // 示範影片：中文用原檔名，英日西各播自己那支（同一位夥伴、講當地語言）
    'meta.demoSuffix': l.code === 'zh' ? '' : '-' + l.code,
    // 條款／隱私／客服：三語版本早就做好了（app-site/legal/{en,ja,es}/），
    // 但四個語系的頁尾一直都連到中文版。這裡讓每個語系連自己那一份。
    // 中文走 /privacy 這種乾淨網址（主機有轉址規則），其他語系直接指檔案。
    'meta.legalPrivacy': l.code === 'zh' ? '/privacy' : `/legal/${l.code}/privacy.html`,
    'meta.legalTerms': l.code === 'zh' ? '/terms' : `/legal/${l.code}/terms.html`,
    'meta.legalSupport': l.code === 'zh' ? '/support' : `/legal/${l.code}/support.html`,
    'meta.htmlLang': l.htmlLang,
    'meta.fonts': fontLink(l.fonts),
    'meta.ogLocale': l.ogLocale,
    'meta.ogAlternates': ogAlternates(l.code),
    'meta.langCurrent': config.langLabels[l.code].short,
    'meta.year': String(config.year),
    'meta.contactEmail': config.contactEmail,
    'meta.b2bUrl': config.b2bUrl,
    'meta.siteUrl': SITE,
    'meta.ogImage': `${SITE}/assets/og-image.jpg`,
    // 品牌識別資料用：把官網／App Store／粉專串成同一個品牌實體（見 index.html 的 ld+json）
    'meta.appStoreUrl': config.appStoreUrl,
    'meta.facebookUrl': config.facebookUrl,
    'meta.faqJsonLd': faqJsonLd(dict, l.code, l.htmlLang),
    'meta.faqHtml': faqHtml(dict),
    'meta.guideIndex': guideUrl(l),
    'meta.navGuide': hasGuides(l.code) ? `<a href="${guideUrl(l)}">${dict['guide.navIndex']}</a>` : '',
    'meta.footGuide': hasGuides(l.code) ? `<a href="${guideUrl(l)}">${dict['guide.navIndex']}</a>` : '',
    'meta.guidesSection': hasGuides(l.code)
      ? `<!-- ═══ 指南入口 ═══ -->\n<section id="guides">\n  <div class="wrap">\n    <div class="sec-head reveal">\n      <div class="eyebrow center">${dict['guide.sectionEyebrow']}</div>\n      <h2>${dict['guide.sectionH2']}</h2>\n      <p>${dict['guide.sectionSub']}</p>\n    </div>\n    <div class="g-list reveal">\n${featured(l.code).map((g) => guideCard(l, g)).join('\n')}\n    </div>\n    <div class="g-more"><a href="${guideUrl(l)}">${dict['guide.more']}</a></div>\n  </div>\n</section>`
      : '',
    // 首頁／「給照護機構」頁互連用的網址（同語系）
    'meta.home': urlFor(l.dir),
    'meta.orgUrl': urlFor(l.dir, 'for-organizations'),
    'meta.b2bLocaleUrl': b2bUrlFor(l.dir),
  };

  for (const page of PAGES) {
    const template = readFileSync(join(SRC, page.template), 'utf8');
    const html = render(template, {
      ...vars,
      'meta.canonical': urlFor(l.dir, page.slug),
      'meta.hreflang': hreflangBlock(page.slug),
      'meta.langMenu': langMenu(l.code, page.slug),
    }, `${l.code}/${page.id}`);
    const dir = join(l.dir ? join(OUT, l.dir) : OUT, page.slug);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'index.html'), html, 'utf8');
    const shown = '/' + [l.dir, page.slug].filter(Boolean).join('/');
    console.log(`  ✓ ${shown}  ${(html.length / 1024).toFixed(0)}KB  (${l.htmlLang})`);
  }

  if (hasGuides(l.code)) {
    const guideLocales = LOCALES.filter((x) => hasGuides(x.code));
    const homeMenu = langMenu(l.code, '');
    const idxHreflang = [
      ...guideLocales.map((x) => `<link rel="alternate" hreflang="${x.hreflang}" href="${guideUrl(x)}">`),
      `<link rel="alternate" hreflang="x-default" href="${guideUrl(LOCALES[0])}">`,
    ].join('\n');
    const org = { '@type': 'Organization', '@id': `${SITE}/#organization`, name: '沐寧 Munea', url: `${SITE}/`, logo: `${SITE}/assets/paining-logo.png` };
    const crumbs = (items) => ({ '@type': 'BreadcrumbList', itemListElement: items.map((it, k) => ({ '@type': 'ListItem', position: k + 1, name: it[0], item: it[1] })) });
    const ld = (graph) => JSON.stringify({ '@context': 'https://schema.org', '@graph': graph }).replace(/</g, '\\u003c');

    for (const g of GUIDES[l.code]) {
      const canonical = guideUrl(l, g.slug);
      const toc = g.toc.length >= 3
        ? `<nav class="g-toc" aria-label="${dict['guide.tocTitle']}"><b>${dict['guide.tocTitle']}</b><ol>${g.toc.map((t) => `<li><a href="#${t.id}">${esc(t.text)}</a></li>`).join('')}</ol></nav>`
        : '';
      const related = g.related.length
        ? `<section class="g-related" aria-label="${dict['guide.related']}"><h2>${dict['guide.related']}</h2><div class="g-list">\n${g.related.map((s) => GUIDES[l.code].find((x) => x.slug === s)).filter(Boolean).map((x) => guideCard(l, x, dict)).join('\n')}\n</div></section>`
        : '';
      const graph = [
        org,
        {
          '@type': 'Article', '@id': `${canonical}#article`, headline: g.title, description: g.description,
          inLanguage: l.htmlLang, datePublished: g.published, dateModified: g.updated,
          author: { '@type': 'Organization', name: dict['guide.byline'], url: `${SITE}/` },
          publisher: { '@id': `${SITE}/#organization` }, mainEntityOfPage: canonical, image: `${SITE}/assets/og-image.jpg`,
        },
        crumbs([[dict['guide.crumbHome'], urlFor(l.dir)], [dict['guide.navIndex'], guideUrl(l)], [g.title, canonical]]),
      ];
      if (g.faq.length) {
        graph.push({ '@type': 'FAQPage', mainEntity: g.faq.map((f) => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a.join(' ') } })) });
      }
      const fmtDate = (d) => (l.code === 'en' ? new Date(d + 'T00:00:00Z').toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' }) : d.replace(/-/g, '/'));
      const html = render(readFileSync(join(SRC, 'guide.html'), 'utf8'), {
        ...vars,
        'g.title': esc(g.title),
        'g.titleTag': esc(`${g.title}｜${dict['guide.siteSuffix']}`),
        'g.description': esc(g.description),
        'g.canonical': canonical,
        'g.hreflang': '',
        'g.published': g.published,
        'g.updated': g.updated,
        'g.updatedText': fmtDate(g.updated),
        'g.readText': dict['guide.read'].replace('{n}', g.readingMinutes),
        'g.toc': toc,
        'g.body': g.html,
        'g.related': related,
        'g.langMenu': homeMenu,
        'g.jsonLd': ld(graph),
      }, `${l.code}/guide/${g.slug}`);
      const gdir = join(l.dir ? join(OUT, l.dir) : OUT, 'guide', g.slug);
      mkdirSync(gdir, { recursive: true });
      writeFileSync(join(gdir, 'index.html'), html, 'utf8');
    }

    const idx = render(readFileSync(join(SRC, 'guide-index.html'), 'utf8'), {
      ...vars,
      'g.canonical': guideUrl(l),
      'g.hreflang': idxHreflang,
      'g.langMenu': homeMenu,
      // 列表順序：搜尋字研究的優先三篇在前，其他照日期
      'g.cards': [...featured(l.code), ...GUIDES[l.code].filter((g) => !featured(l.code).includes(g))].map((g) => guideCard(l, g, dict)).join('\n'),
      'g.jsonLd': ld([
        org,
        { '@type': 'CollectionPage', '@id': `${guideUrl(l)}#page`, name: dict['guide.indexH1'], description: dict['guide.indexDesc'], inLanguage: l.htmlLang, url: guideUrl(l),
          hasPart: GUIDES[l.code].map((g) => ({ '@type': 'Article', headline: g.title, url: guideUrl(l, g.slug) })) },
        crumbs([[dict['guide.crumbHome'], urlFor(l.dir)], [dict['guide.navIndex'], guideUrl(l)]]),
      ]),
    }, `${l.code}/guide`);
    const idir = join(l.dir ? join(OUT, l.dir) : OUT, 'guide');
    mkdirSync(idir, { recursive: true });
    writeFileSync(join(idir, 'index.html'), idx, 'utf8');
    console.log(`  ✓ /${[l.dir, 'guide'].filter(Boolean).join('/')}  ${GUIDES[l.code].length} 篇`);
  }
  built++;
}

/* ── sitemap：四個語系全列，每筆帶 hreflang 互指 ── */
// 法律頁的正本網址在 app.munea.net（蘋果登記的），不混進 munea.net 的網站地圖
const legalPages = [];
// 2026-11-18：solutions.html（舊定位：取藥櫃／藥師把關）已 301 轉到 /for-organizations，原檔封存在 site-src/_archive/
const extraPages = [];
// lastmod 要是真的修改日——每次產生都寫今天，Google 會判定這欄不可信而整欄忽略
const SITE_UPDATED = config.siteUpdated;
const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
${PAGES.flatMap((page) =>
  LOCALES.map(
    (l) => `  <url>
    <loc>${urlFor(l.dir, page.slug)}</loc>
${LOCALES.map((a) => `    <xhtml:link rel="alternate" hreflang="${a.hreflang}" href="${urlFor(a.dir, page.slug)}"/>`).join('\n')}
    <xhtml:link rel="alternate" hreflang="x-default" href="${urlFor('', page.slug)}"/>
    <lastmod>${SITE_UPDATED}</lastmod><changefreq>monthly</changefreq><priority>${page.slug ? '0.7' : '1.0'}</priority>
  </url>`
  )
).join('\n')}
${LOCALES.filter((l) => hasGuides(l.code)).map((l) => {
  const alts = LOCALES.filter((x) => hasGuides(x.code));
  const latest = GUIDES[l.code].map((g) => g.updated).sort().pop();
  return `  <url>
    <loc>${guideUrl(l)}</loc>
${alts.map((a) => `    <xhtml:link rel="alternate" hreflang="${a.hreflang}" href="${guideUrl(a)}"/>`).join('\n')}
    <xhtml:link rel="alternate" hreflang="x-default" href="${guideUrl(alts[0])}"/>
    <lastmod>${latest}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority>
  </url>
${GUIDES[l.code].map((g) => `  <url><loc>${guideUrl(l, g.slug)}</loc><lastmod>${g.updated}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>`).join('\n')}`;
}).join('\n')}
${[...extraPages, ...legalPages]
  .map((p) => `  <url><loc>${SITE}/${p}</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>`)
  .join('\n')}
</urlset>
`;
writeFileSync(join(OUT, 'sitemap.xml'), sitemap, 'utf8');

console.log(`  ✓ sitemap.xml（${LOCALES.length} 語系＋指南 ${Object.values(GUIDES).reduce((n, g) => n + g.length, 0)} 篇）`);
console.log(
  `\n完成：${built} 個語系。下載鍵狀態＝${config.appStoreUrl ? 'App Store 正式連結' : '即將上架（App 尚未過審）'}\n`
);

/* ── 保險絲：產出的頁面不該還留著沒換掉的 {{ }} ── */
for (const l of LOCALES) for (const page of PAGES) {
  const p = join(l.dir ? join(OUT, l.dir) : OUT, page.slug, 'index.html');
  const leftover = readFileSync(p, 'utf8').match(/\{\{[^}]+\}\}/g);
  if (leftover) {
    console.error(`✗ ${p} 還有沒換掉的標記：${leftover.slice(0, 5).join(', ')}`);
    process.exitCode = 1;
  }
}

/* ── 保險絲：指南文章裡的站內連結必須指到真的有產生的頁面 ──
 * 2026-11-18 第二輪評分抓到英文指南寫成 /guides/en/...（實際是 /en/guide/...），4 條全 404。 */
{
  const { existsSync: exists } = await import('node:fs');
  const broken = [];
  for (const l of LOCALES) {
    for (const g of GUIDES[l.code]) {
      for (const m of g.html.matchAll(/href="(\/[^"#?]*)/g)) {
        const p = m[1].replace(/\/$/, '');
        const target = join(OUT, p);
        if (!(exists(join(target, 'index.html')) || exists(target) || exists(target + '.html'))) {
          broken.push(`${l.code}/${g.slug} → ${m[1]}`);
        }
      }
    }
  }
  if (broken.length) {
    console.error(`✗ 指南裡有 ${broken.length} 條站內連結指到不存在的頁面：\n  ` + broken.join('\n  '));
    process.exitCode = 1;
  }
}
