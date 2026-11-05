const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const appSite = path.join(root, "app-site");

function read(relativePath) {
  return fs.readFileSync(path.join(appSite, relativePath), "utf8");
}

function readRoot(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function countMatches(value, pattern) {
  return [...value.matchAll(pattern)].length;
}

const verificationFile = "googleaa0c51d3d9781eb5.html";
const verificationToken = "google-site-verification: googleaa0c51d3d9781eb5.html";
assert.equal(read(verificationFile).trim(), verificationToken);

const firebaseRc = JSON.parse(readRoot(".firebaserc"));
assert.equal(firebaseRc.projects?.default, "gen-lang-client-0229303523");
assert.deepEqual(
  firebaseRc.targets?.["gen-lang-client-0229303523"]?.hosting?.public,
  ["munea-public"],
);

const firebaseConfig = JSON.parse(readRoot("firebase.json"));
const hosting = firebaseConfig.hosting;
assert.equal(hosting.target, "public");
assert.equal(hosting.public, "app-site");
assert.equal(
  Object.hasOwn(hosting, "cleanUrls"),
  false,
  "cleanUrls redirects the exact Google verification file away from its .html URL",
);
assert.equal(hosting.trailingSlash, false);
assert.ok(hosting.ignore.includes("vercel.json"));

const publicPages = ["privacy", "terms", "support"];
for (const page of publicPages) {
  assert.ok(
    hosting.redirects?.some(
      (route) =>
        route.regex === `/${page}\\.html` &&
        route.destination === `/${page}` &&
        route.type === 301,
    ),
    `Missing permanent redirect for /${page}.html`,
  );
  assert.ok(
    hosting.rewrites?.some(
      (route) => route.source === `/${page}` && route.destination === `/${page}.html`,
    ),
    `Missing clean public route for /${page}`,
  );
}

const globalHeaders = hosting.headers?.find((entry) => entry.source === "**")?.headers || [];
for (const key of [
  "Strict-Transport-Security",
  "X-Content-Type-Options",
  "X-Frame-Options",
  "Referrer-Policy",
  "Permissions-Policy",
]) {
  assert.ok(globalHeaders.some((header) => header.key === key), `Missing hosting header ${key}`);
}

// 網頁本身必須每次回來確認有沒有新版。主機預設 max-age=3600，等於每次改版都有
// 一小時空窗，回訪的人拿到的還是舊頁面（2026-07-30 換示範影片時踩到）。
// 靜態檔那條規則排在後面會蓋掉這個值，圖片影片仍快取一天。
const globalCache = globalHeaders.find((header) => header.key === "Cache-Control")?.value || "";
assert.match(
  globalCache,
  /max-age=0/,
  "HTML must revalidate every visit, otherwise a deploy takes up to an hour to reach returning visitors",
);
const assetCache = (hosting.headers || []).find((entry) => /mp4/.test(entry.source))?.headers || [];
assert.match(
  assetCache.find((header) => header.key === "Cache-Control")?.value || "",
  /max-age=\d{3,}/,
  "static assets should still be cached",
);

// 四語系合約：每個語系一個真網址，彼此用 hreflang 互指。
// 靠 JS 當場換字的舊做法，Google 只看得到中文版 —— 這裡守住不准回頭。
const locales = [
  { code: "zh", dir: "", hreflang: "zh-Hant" },
  { code: "en", dir: "en", hreflang: "en" },
  { code: "ja", dir: "ja", hreflang: "ja" },
  { code: "es", dir: "es", hreflang: "es" },
];
// trailingSlash:false —— 對外網址不帶尾斜線，否則每個語系都要先吃一次轉址
const localeUrl = (dir) => (dir ? `https://munea.net/${dir}` : "https://munea.net/");

const sitemap = read("sitemap.xml");
const sitemapUrls = [...locales.map((l) => localeUrl(l.dir)), "https://munea.net/solutions.html"];
for (const url of sitemapUrls) {
  assert.match(sitemap, new RegExp(`<loc>${url.replaceAll(".", "\\.")}</loc>`));
}
assert.equal(countMatches(sitemap, /<url>/g), sitemapUrls.length);
for (const l of locales) {
  assert.match(
    sitemap,
    new RegExp(`hreflang="${l.hreflang}" href="${localeUrl(l.dir).replaceAll(".", "\\.")}"`),
    `sitemap missing hreflang alternate for ${l.code}`,
  );
}
assert.match(sitemap, /hreflang="x-default"/, "sitemap needs an x-default alternate");

const robots = read("robots.txt");
assert.match(robots, /^User-agent:\s*\*/m);
assert.match(robots, /^Allow:\s*\/$/m);
assert.match(robots, /^Sitemap:\s*https:\/\/munea\.net\/sitemap\.xml$/m);

const pages = [
  ...locales.map((l) => ({
    file: l.dir ? `${l.dir}/index.html` : "index.html",
    canonical: localeUrl(l.dir),
    locale: l,
  })),
  // 法律頁的正本留在 app.munea.net —— 那是 App Store 登記的網址，動它要改蘋果後台
  { file: "privacy.html", canonical: "https://app.munea.net/privacy" },
  { file: "terms.html", canonical: "https://app.munea.net/terms" },
  { file: "support.html", canonical: "https://app.munea.net/support" },
];

for (const page of pages) {
  const html = read(page.file);
  assert.match(html, /<title\b[^>]*>[^<]+<\/title>/i, `${page.file} needs a title`);
  assert.match(
    html,
    /<meta\s+name=["']description["']\s+content=["'][^"']+["']/i,
    `${page.file} needs a meta description`,
  );
  assert.match(
    html,
    new RegExp(
      `<link\\s+rel=["']canonical["']\\s+href=["']${page.canonical.replaceAll(".", "\\.")}["']`,
      "i",
    ),
    `${page.file} has the wrong canonical URL`,
  );
  assert.equal(countMatches(html, /<h1(?:\s|>)/gi), 1, `${page.file} needs exactly one h1`);
  assert.doesNotMatch(html, /noindex/i, `${page.file} must remain indexable`);

  if (!page.locale) continue;

  // 每個語系頁都要：宣告自己的語言、把其他三語都指出去、附 x-default
  assert.match(
    html,
    new RegExp(`<html\\s+lang=["'][^"']*${page.locale.code}[^"']*["']`, "i"),
    `${page.file} must declare lang for ${page.locale.code}`,
  );
  for (const other of locales) {
    assert.match(
      html,
      new RegExp(
        `rel="alternate"\\s+hreflang="${other.hreflang}"\\s+href="${localeUrl(other.dir).replaceAll(".", "\\.")}"`,
      ),
      `${page.file} missing hreflang alternate for ${other.code}`,
    );
  }
  assert.match(html, /hreflang="x-default"/, `${page.file} needs an x-default alternate`);

  // 上架前不准留死連結：App Store 網址沒填就不該出現在頁面上
  const appStoreUrl = JSON.parse(readRoot("site-src/config.json")).appStoreUrl;
  if (!appStoreUrl) {
    assert.doesNotMatch(
      html,
      /apps\.apple\.com/i,
      `${page.file} must not link to the App Store before the app is live`,
    );
  }
}

// 示範影片：每個語系播自己那支（英日西的寧寧要講當地語言），而且檔案真的在。
// 打招呼與待機那兩支是無聲動畫，沒有語言問題，維持一份共用。
// 2026-10-28 新形象：只剩寧寧一支（男生 9/30 下線）；舊的 realfemale／realmale 檔不得再出現。
for (const l of locales) {
  const html = read(l.dir ? `${l.dir}/index.html` : "index.html");
  const suffix = l.code === "zh" ? "" : `-${l.code}`;
  assert.doesNotMatch(html, /real(?:fe)?male|real-(?:fe)?male/, `${l.code} must not reference the retired real-photo videos`);
  for (const who of ["ningning", "mumu"]) {
    const mp4 = `${who}-talk-demo${suffix}.mp4`;
    assert.match(
      html,
      new RegExp(`/assets/${mp4.replaceAll(".", "\\.")}`),
      `${l.code} demo video should be ${mp4}`,
    );
    assert.ok(
      fs.existsSync(path.join(appSite, "assets", mp4)),
      `missing demo video asset ${mp4}`,
    );
  }
}

// 條款／隱私／客服：每個語系要連自己語言那一份（三語版本在 app-site/legal/<code>/）。
// 四個語系的頁尾一路都連中文版，是 2026-07-31 才抓到的——翻譯早就做好了、只是沒接上。
for (const l of locales) {
  const html = read(l.dir ? `${l.dir}/index.html` : "index.html");
  for (const page of ["privacy", "terms", "support"]) {
    const href = l.code === "zh" ? `/${page}` : `/legal/${l.code}/${page}.html`;
    assert.match(
      html,
      new RegExp(`href="${href.replaceAll(".", "\\.")}"`),
      `${l.code} footer should link to ${href}`,
    );
    if (l.code !== "zh") {
      assert.ok(
        fs.existsSync(path.join(appSite, "legal", l.code, `${page}.html`)),
        `missing translated legal page: ${l.code}/${page}.html`,
      );
    }
  }
}

// 2026-10-30 搜尋能見度：iPhone 智慧橫幅＋常見問題結構化資料＋品牌資料不放個人信箱＋/llms.txt
for (const l of locales) {
  const file = l.dir ? `${l.dir}/index.html` : "index.html";
  const html = read(file);
  assert.match(
    html,
    /<meta name="apple-itunes-app" content="app-id=6788658125">/,
    `${file} needs the iPhone smart app banner`,
  );
  const blocks = [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map((m) =>
    JSON.parse(m[1]),
  );
  const org = blocks.flatMap((b) => b["@graph"] || []).find((n) => n["@type"] === "Organization");
  assert.ok(org, `${file} must keep the Organization entity`);
  // 個人信箱不放進品牌識別資料；munea.net 網域信箱收得到信之前，這欄一律留空
  assert.equal(Object.hasOwn(org, "email"), false, `${file} Organization must not publish an email`);
  assert.doesNotMatch(JSON.stringify(org.sameAs || []), /mailto:|@gmail\.com/i, `${file} sameAs must not list a mailbox`);
  const faq = blocks.find((b) => b["@type"] === "FAQPage");
  assert.ok(faq, `${file} needs FAQPage structured data`);
  assert.ok(faq.mainEntity.length >= 6, `${file} FAQ should answer at least 6 questions`);
  // 結構化資料的每一題都要在頁面上看得到（Google 規定兩邊一致）
  for (const q of faq.mainEntity) {
    assert.equal(q["@type"], "Question");
    assert.ok(html.includes(`<span>${q.name}</span>`), `${file} FAQ question not visible on page: ${q.name}`);
    assert.ok(
      html.includes(`<p class="fa">${q.acceptedAnswer.text}</p>`),
      `${file} FAQ answer not visible on page: ${q.name}`,
    );
  }
  // 紅線：不寫急難號碼、不用「追蹤／監測」
  const faqText = JSON.stringify(faq);
  assert.doesNotMatch(faqText, /\b(?:112|119|1925|911)\b/, `${file} FAQ must not cite emergency numbers`);
  assert.doesNotMatch(faqText, /追蹤|監測|監控|\btrack|\bmonitor/i, `${file} FAQ must not describe Munea as tracking`);
}
const llms = read("llms.txt");
assert.match(llms, /^# Munea/m, "llms.txt needs a title line");
assert.match(llms, /https:\/\/apps\.apple\.com\/app\/id6788658125/, "llms.txt must link the App Store listing");
for (const l of locales) {
  assert.ok(llms.includes(localeUrl(l.dir)), `llms.txt must list the ${l.code} site URL`);
}
assert.doesNotMatch(llms, /@gmail\.com/i, "llms.txt must not publish a personal mailbox");

console.log(`[ok] munea.net SEO contract passed (${locales.length} locales)`);

require("./test-app-site-legal-localizations.js");
