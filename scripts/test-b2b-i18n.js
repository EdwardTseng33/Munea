#!/usr/bin/env node
/* B2B 合作頁 · 四語系守門測試
 *
 * 先重跑產生器，再驗產出——這樣「有人直接改 munea-b2b/index.html」的情況
 * 會在這裡被沖掉、測試也會抓到文案表少字，不會靜悄悄上線一個半中半英的頁面。
 *
 * 跑法：npm run test:b2b-i18n
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(ROOT, 'munea-b2b');
const SRC = path.join(ROOT, 'b2b-src');
const SITE = 'https://munea-b2b.vercel.app';

execFileSync(process.execPath, [path.join(SRC, 'build.mjs')], { cwd: ROOT, stdio: 'pipe' });

const LOCALES = [
  { code: 'zh', dir: '', lang: 'zh-Hant', url: `${SITE}/` },
  { code: 'en', dir: 'en', lang: 'en', url: `${SITE}/en` },
  { code: 'ja', dir: 'ja', lang: 'ja', url: `${SITE}/ja` },
  { code: 'es', dir: 'es', lang: 'es', url: `${SITE}/es` },
];

/* ── 1. 四份文案表的 key 必須完全一致 ── */
const dicts = {};
for (const l of LOCALES) {
  dicts[l.code] = JSON.parse(fs.readFileSync(path.join(SRC, 'i18n', `${l.code}.json`), 'utf8'));
}
const zhKeys = Object.keys(dicts.zh).sort();
for (const l of LOCALES.slice(1)) {
  const keys = Object.keys(dicts[l.code]).sort();
  const missing = zhKeys.filter((k) => !keys.includes(k));
  const extra = keys.filter((k) => !zhKeys.includes(k));
  assert.equal(missing.length, 0, `${l.code}.json 少了 key：${missing.join(', ')}`);
  assert.equal(extra.length, 0, `${l.code}.json 多了中文沒有的 key：${extra.join(', ')}`);
}

/* ── 2. 每個語系的頁面本身 ── */
for (const l of LOCALES) {
  const file = path.join(l.dir ? path.join(OUT, l.dir) : OUT, 'index.html');
  const html = fs.readFileSync(file, 'utf8');
  const at = (m) => `[${l.code}] ${m}`;

  assert.doesNotMatch(html, /\{\{[^}]+\}\}/, at('還有沒換掉的 {{ }} 標記'));
  assert.match(html, new RegExp(`<html lang="${l.lang}">`), at('html lang 不對'));
  assert.match(html, new RegExp(`<link rel="canonical" href="${l.url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}">`), at('canonical 不對'));

  // hreflang 四語互指 + x-default，少一條就代表搜尋引擎看不到其他語系
  for (const a of [...LOCALES.map((x) => x.lang), 'x-default']) {
    assert.match(html, new RegExp(`hreflang="${a}"`), at(`缺 hreflang=${a}`));
  }

  // 字型跟著語系給：中文頁才准載中文字型（英日西載了等於白扛 2MB）
  if (l.code === 'zh') {
    assert.match(html, /Noto\+Sans\+TC/, at('中文頁沒載中文字型'));
    assert.match(html, /--wb:keep-all/, at('中文頁的斷行規則被改掉了'));
  } else {
    assert.doesNotMatch(html, /Noto\+Sans\+TC|Noto\+Serif\+TC/, at('非中文頁不該載中文字型'));
    assert.match(html, /--wb:normal/, at('非中文頁斷行規則不對（日文會斷得很醜）'));
  }

  // 素材一律根路徑，否則 /en /ja /es 底下會去抓 /en/assets/... 破圖
  assert.doesNotMatch(html, /(src|href|poster)="assets\//, at('有相對路徑的素材，子目錄會破圖'));
  assert.doesNotMatch(html, /url\('assets\//, at('CSS 裡有相對路徑的素材'));
  assert.match(html, /href="\/call\.html"/, at('通話頁連結不是根路徑'));

  // 表單真正送出的值要維持中文——名單進 Edward 信箱時四個語系長一樣
  for (const v of ['長照機構', '健康中心', '企業人資永續', '高齡村', '策略聯盟', '其他', '機構席次', 'ESG 席次', '白牌合作']) {
    assert.match(html, new RegExp(`value="${v}"`), at(`表單送出值 ${v} 被翻譯掉了`));
  }

  // 語言選單四個選項都在，且指到不帶尾斜線的網址
  for (const other of LOCALES) {
    assert.match(html, new RegExp(`href="${other.url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`), at(`語言選單缺 ${other.code}`));
  }
  assert.doesNotMatch(html, new RegExp(`href="${SITE}/(en|ja|es)/"`), at('語言選單帶了尾斜線，會多吃一次轉址'));

  // 頁面內嵌的 JS 要能 parse（文案裡的引號若沒跳脫好，這裡會爆）
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
  assert.ok(scripts.length > 0, at('沒有內嵌 JS'));
  scripts.forEach((m, i) => {
    assert.doesNotThrow(() => new Function(m[1]), at(`內嵌 JS 第 ${i + 1} 段 parse 失敗`));
  });

  // 非中文頁不該殘留成段的中文（品牌字、公司名、語言選單、表單送出值除外）
  if (l.code !== 'zh') {
    const body = html
      .replace(/<style>[\s\S]*?<\/style>/g, '')
      .replace(/<script>[\s\S]*?<\/script>/g, '')
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/value="[^"]*"/g, '')
      .replace(/沐寧|嘉瑪科技股份有限公司|切換語言|中文|繁中|日本語/g, '');
    const leftover = body.match(/[\u4e00-\u9fff]{2,}/g);
    if (l.code !== 'ja') {
      assert.equal(leftover, null, at(`還有沒翻到的中文：${(leftover || []).slice(0, 5).join('、')}`));
    }
  }
}

/* ── 3. sitemap / robots ── */
const sitemap = fs.readFileSync(path.join(OUT, 'sitemap.xml'), 'utf8');
for (const l of LOCALES) assert.match(sitemap, new RegExp(`<loc>${l.url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}</loc>`), `sitemap 缺 ${l.code}`);
assert.match(fs.readFileSync(path.join(OUT, 'robots.txt'), 'utf8'), new RegExp(`Sitemap: ${SITE}/sitemap.xml`));

console.log(`PASS munea-b2b 四語系（${LOCALES.map((l) => l.code).join(' / ')}）· 文案表對齊、hreflang 互指、素材根路徑、表單送出值維持中文`);
