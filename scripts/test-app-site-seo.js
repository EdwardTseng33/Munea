const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const appSite = path.join(root, "app-site");

function read(relativePath) {
  return fs.readFileSync(path.join(appSite, relativePath), "utf8");
}

function countMatches(value, pattern) {
  return [...value.matchAll(pattern)].length;
}

const verificationFile = "googleaa0c51d3d9781eb5.html";
const verificationToken = "google-site-verification: googleaa0c51d3d9781eb5.html";
assert.equal(read(verificationFile).trim(), verificationToken);

const vercelConfig = JSON.parse(read("vercel.json"));
assert.equal(
  Object.hasOwn(vercelConfig, "cleanUrls"),
  false,
  "cleanUrls redirects the exact Google verification file away from its .html URL",
);
assert.equal(vercelConfig.trailingSlash, false);

const publicPages = ["privacy", "terms", "support"];
for (const page of publicPages) {
  assert.ok(
    vercelConfig.redirects?.some(
      (route) =>
        route.source === `/${page}.html` &&
        route.destination === `/${page}` &&
        route.permanent === true,
    ),
    `Missing permanent redirect for /${page}.html`,
  );
  assert.ok(
    vercelConfig.rewrites?.some(
      (route) => route.source === `/${page}` && route.destination === `/${page}.html`,
    ),
    `Missing clean public route for /${page}`,
  );
}

const sitemap = read("sitemap.xml");
const sitemapUrls = [
  "https://app.munea.net/",
  "https://app.munea.net/privacy",
  "https://app.munea.net/terms",
  "https://app.munea.net/support",
];
for (const url of sitemapUrls) {
  assert.match(sitemap, new RegExp(`<loc>${url.replaceAll(".", "\\.")}</loc>`));
}
assert.equal(countMatches(sitemap, /<url>/g), sitemapUrls.length);

const robots = read("robots.txt");
assert.match(robots, /^User-agent:\s*\*/m);
assert.match(robots, /^Allow:\s*\/$/m);
assert.match(robots, /^Sitemap:\s*https:\/\/app\.munea\.net\/sitemap\.xml$/m);

const pages = [
  { file: "index.html", canonical: "https://app.munea.net/" },
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
}

console.log("[ok] app.munea.net SEO contract passed");
