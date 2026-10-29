"use strict";
/*
 * 營運後台 14 頁無頭截圖（2026-10-28 UI/UX 調整時建立）
 *
 * 用法：
 *   node scripts/admin-i18n-fixture-server.js --port 4175      # 另一個視窗先開假資料伺服器
 *   node scripts/admin-screenshots.js --out .tmp/admin-shots [--port 4175] [--widths 1440,768,390] [--pages overview,users]
 *
 * 做什麼：
 *   1. 用系統 Chrome（playwright-core、不另外下載瀏覽器）開 admin.html
 *   2. 走一次登入門（假資料伺服器任何帳密都放行）→ 截登入頁
 *   3. 依 hash 路由逐頁切到 14 頁，每頁在每個寬度各截一張整頁圖
 *   4. 額外截三個狀態：登入頁、讀取中（aria-busy）、手機抽屜打開
 *
 * 不碰正式機、不帶任何鑰匙；只讀本機假資料。
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright-core");

const args = process.argv.slice(2);
function arg(name, fallback) {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
}
const port = Number(arg("port", "4175"));
const outDir = path.resolve(arg("out", ".tmp/admin-shots"));
const widths = arg("widths", "1440,768,390").split(",").map((w) => Number(w.trim())).filter(Boolean);
const PAGES = [
  "overview", "users", "safety", "medication", "familyHealth", "moodTrend", "bondDepth", "growth",
  "subscription", "enterpriseClients", "enterprisePayments", "enterpriseBillingSettings", "feedback", "records",
];
const pages = arg("pages", PAGES.join(",")).split(",").map((p) => p.trim()).filter(Boolean);
const colorScheme = arg("scheme", "light");

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
].filter(Boolean);
const executablePath = CHROME_CANDIDATES.find((p) => fs.existsSync(p));
if (!executablePath) {
  console.error("找不到系統 Chrome／Edge，請設 CHROME_PATH");
  process.exit(2);
}

fs.mkdirSync(outDir, { recursive: true });
const base = `http://127.0.0.1:${port}`;

async function waitRendered(page) {
  // 登入後首頁會先出現 KPI 卡；切頁後等 aria-busy 退掉、pageRoot 有內容
  await page.waitForFunction(() => {
    const root = document.getElementById("pageRoot");
    return root && root.getAttribute("aria-busy") !== "true" && root.children.length > 0;
  }, null, { timeout: 15000 });
  await page.waitForTimeout(250); // 字型／SVG 圖表最後一拍
}

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true });
  const taken = [];
  for (const width of widths) {
    const height = width >= 1200 ? 900 : width >= 700 ? 1024 : 844;
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, colorScheme, locale: "zh-TW" });
    const page = await context.newPage();
    page.on("pageerror", (e) => console.warn(`[${width}] pageerror`, e.message));
    await page.goto(`${base}/admin.html#overview`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#loginForm", { timeout: 15000 });
    await page.waitForTimeout(300);
    const loginShot = path.join(outDir, `login-${width}.png`);
    await page.screenshot({ path: loginShot, fullPage: false });
    taken.push(loginShot);

    await page.fill("#loginEmail", "ops@example.com");
    await page.fill("#loginPassword", "fixture");
    await page.click("#loginBtn");
    await page.waitForSelector(".kpi, .card", { timeout: 20000 });
    await waitRendered(page);

    for (const id of pages) {
      await page.evaluate((h) => { location.hash = "#" + h; }, id);
      await page.waitForTimeout(150);
      try { await waitRendered(page); } catch (e) { console.warn(`[${width}] ${id} 等不到渲染完成：${e.message}`); }
      const file = path.join(outDir, `${id}-${width}.png`);
      await page.screenshot({ path: file, fullPage: true });
      taken.push(file);
    }

    // 狀態圖：讀取中（手動掛 aria-busy）
    await page.evaluate(() => { location.hash = "#overview"; });
    await waitRendered(page);
    await page.evaluate(() => { document.getElementById("pageRoot").setAttribute("aria-busy", "true"); });
    await page.waitForTimeout(100);
    const busyShot = path.join(outDir, `state-loading-${width}.png`);
    await page.screenshot({ path: busyShot, fullPage: false });
    taken.push(busyShot);
    await page.evaluate(() => { document.getElementById("pageRoot").setAttribute("aria-busy", "false"); });

    // 手機抽屜打開
    if (width <= 880) {
      await page.click("#mobileNavBtn");
      await page.waitForTimeout(350);
      const drawerShot = path.join(outDir, `state-drawer-${width}.png`);
      await page.screenshot({ path: drawerShot, fullPage: false });
      taken.push(drawerShot);
    }
    await context.close();
  }
  await browser.close();
  console.log(`已截 ${taken.length} 張 → ${outDir}`);
})().catch((e) => { console.error(e); process.exit(1); });
