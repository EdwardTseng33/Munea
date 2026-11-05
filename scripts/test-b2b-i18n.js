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
  // 2026-11-05 宣稱對齊現況：守護腦高風險訊號目前只進內部告警、沒有自動通知家人；
  // 聲音不是自研引擎；App 有四語；角色名跟 App 一致（寧寧＝Nina／あかり／Lucía）。
  const visibleCopy = html.replace(/<!--[\s\S]*?-->/g, '');
  assert.doesNotMatch(
    visibleCopy,
    /即時通知家人|出事會叫人|notified right away|calls for help|すぐ通知|人を呼ぶ|人を呼びます|Aviso inmediato|avisa al momento|llama a alguien/i,
    at('又寫回「即時通知家人／出事會叫人」——目前沒有這個功能'),
  );
  assert.doesNotMatch(visibleCopy, /自研|Our own real-time|自社開発|Motor propio/i, at('不可宣稱自研語音影像引擎'));
  assert.doesNotMatch(visibleCopy, /台語互動持續優化|Hokkien is still being improved|台湾語（台湾閩南語）は改善|taiwanés \(hokkien\) sigue/i, at('台語進度沒有事實佐證'));
  assert.doesNotMatch(visibleCopy, /not supported today|対応していません|no admite otros idiomas/i, at('App 已有四語，不能寫不支援其他語言'));
  assert.doesNotMatch(visibleCopy, /2026 是照護科技|2026-07 上路|effective July 2026|2026年7月開始|julio de 2026/, at('會過期／未查證的政策日期'));
  const companionName = { zh: '寧寧', en: 'Nina', ja: 'あかり', es: 'Lucía' }[l.code];
  assert.ok(visibleCopy.includes(companionName), at(`角色名要跟 App 一致：${companionName}`));
  if (l.code !== 'zh') assert.doesNotMatch(visibleCopy, /Ningning|ニンニン/, at('英日西不該再叫 Ningning'));

  // 2026-11-05 網頁試打已移除：不准再連回 call.html，想試用就走「下載 App」
  assert.doesNotMatch(html, /call\.html|\/api\/call-key/, at('還連著已移除的網頁試打'));
  assert.match(
    html,
    /id="try-app"[\s\S]*?href="https:\/\/apps\.apple\.com\/(?:tw\/)?app\/id6788658125"/,
    at('缺「下載 App 直接試用」的 App Store 連結'),
  );

  // 示範影片：每個語系播自己那支（英日西的夥伴要講當地語言），而且檔案真的在
  const suffix = l.code === 'zh' ? '' : '-' + l.code;
  assert.doesNotMatch(html, /real(?:fe)?male|real-(?:fe)?male/, at('還在引用舊的真人照影片（2026-10-28 新形象後只剩寧寧一支）'));
  for (const who of ['ningning', 'mumu']) {
    const mp4 = `${who}-talk-demo${suffix}.mp4`;
    assert.match(html, new RegExp(`/assets/${mp4.replace('.', '\\.')}`), at(`示範影片沒指到 ${mp4}`));
    assert.ok(fs.existsSync(path.join(OUT, 'assets', mp4)), at(`示範影片檔不見了：${mp4}`));
  }

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
