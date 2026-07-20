"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web", "admin.html"), "utf8");
const js = fs.readFileSync(path.join(root, "web", "src", "admin.js"), "utf8");
const css = fs.readFileSync(path.join(root, "web", "src", "admin.css"), "utf8");
const smoke = fs.readFileSync(path.join(root, "scripts", "admin-smoke.ps1"), "utf8");

function matches(text, pattern) {
  return Array.from(text.matchAll(pattern), (match) => match.groups.path);
}

const consolePaths = matches(js, /^\s+\w+:\s*\["(?<path>\/admin\/[^"?]+)"/gm);
const smokeBlock = smoke.match(/\$adminReadBodies\s*=\s*\[ordered\]@\{([\s\S]*?)\n\}/);
assert(smokeBlock, "admin smoke must declare adminReadBodies");
const smokePaths = matches(smokeBlock[1], /^\s+"(?<path>\/admin\/[^"?]+)"\s*=/gm);
assert.deepStrictEqual(smokePaths.sort(), consolePaths.sort(), "admin smoke must cover every EP_LIST endpoint exactly");

// 2026-07-20：「連線設定」概念移除後，狀態列不再有 statusPill／connectBanner，
// 改由 lastUpdated 常駐顯示「資料更新到 X」，未登入一律走帳密登入門。
for (const token of [
  'id="lastUpdated"',
  'aria-live="polite"',
  'id="refreshBtn"',
  'id="logoutBtn"',
  'class="skip-link"',
  'aria-label="主要功能"',
]) {
  assert(html.includes(token), `admin.html missing operational/accessibility contract: ${token}`);
}
for (const token of ['id="connectBanner"', 'id="statusPill"', 'id="currentPeriod"']) {
  assert(!html.includes(token), `admin.html must not reintroduce removed connection UI: ${token}`);
}

for (const token of [
  "REQUEST_TIMEOUT_MS",
  "normalizeAdminBaseUrl",
  "untrusted_admin_host",
  "MUNEA_ADMIN_APP_KEY",
  "window.MUNEA_ADMIN_ALLOWED_HOSTS",
  "sessionStorage,ADMIN_TOKEN_KEY",
  "aria-current",
  "aria-modal",
  "data-retry",
  "munea.admin-data-meta.v1",
  "dataAsOf",
  "metadata_missing",
  "dataQualityNoticeHTML",
]) {
  assert(js.includes(token), `admin.js missing health/security contract: ${token}`);
}

assert(!js.includes("localStorage,ADMIN_TOKEN_KEY"), "admin token must never be persisted in localStorage");
assert.strictEqual((js.match(/\bfetch\s*\(/g) || []).length, 1, "all admin network calls must go through timedFetch");
assert(smoke.includes("foreach ($entry in $adminReadBodies.GetEnumerator())"), "smoke must iterate the endpoint contract");
assert(smoke.includes("Expect-AdminHttpError $entry.Key"), "smoke must verify every console endpoint rejects missing admin auth");

for (const token of [":focus-visible", '.page[aria-busy="true"]', ".ops-notice.error", ".topbar-action"]) {
  assert(css.includes(token), `admin.css missing state/accessibility contract: ${token}`);
}

console.log(`Admin console contract OK (${consolePaths.length} endpoint(s))`);
