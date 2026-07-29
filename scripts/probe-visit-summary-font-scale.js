#!/usr/bin/env node
/* 就診摘要 · 字級放大實測探針（四語系 × standard/XL）
 *
 * 為什麼要有這支：2026-07-29 把 #reportModal 從 .modal 改成 .reader-page 之後，
 * applyFontScale 的選擇器就選不到它——使用者選「特大」卻完全沒變大，而這正是
 * 最需要放大的一頁。source-level 的契約（test-visit-summary-ui ①h）擋得住選擇器
 * 被改掉，但擋不住「選到了卻沒效果」，所以另外用真瀏覽器量一次。
 *
 * **注意 zoom 的量測陷阱**：CSS zoom 不會改變 computed font-size，量 font-size
 * 會得到 std 與 XL 一模一樣的數字、誤判成沒生效。要量的是 zoom 值本身，
 * 以及算繪後的 getBoundingClientRect() 高度。
 *
 * 同時驗 375px 的英文／西班牙文長字串不會橫向溢位（放大後最容易出事的組合）。
 *
 * 跑法（需本機 Chromium 與 Playwright，不連外網）：
 *   MUNEA_PLAYWRIGHT_PATH=... MUNEA_CHROME_PATH=... node scripts/probe-visit-summary-font-scale.js
 */
const { createFixtureServer } = require('./app-i18n-fixture-server.js');
const { chromium } = require(process.env.MUNEA_PLAYWRIGHT_PATH || 'playwright');
const PORT = 4377;
const CASES = [
  ['zh-TW', 390, 844], ['en', 375, 667], ['es', 375, 667], ['ja', 390, 844],
];
(async () => {
  const server = createFixtureServer({ port: PORT });
  await new Promise(r => server.listen(PORT, '127.0.0.1', r));
  const browser = await chromium.launch({
    executablePath: process.env.MUNEA_CHROME_PATH, headless: true });
  let bad = 0;
  for (const [locale, w, h] of CASES) {
    const row = {};
    for (const scale of ['std', 'xl']) {
      const page = await browser.newPage({ viewport: { width: w, height: h } });
      await page.goto(`http://127.0.0.1:${PORT}/?lang=${locale}`, { waitUntil: 'networkidle' });
      await page.evaluate(s => { try { localStorage.setItem('munea.fontScale', s); } catch (e) {} }, scale);
      await page.reload({ waitUntil: 'networkidle' });
      await page.waitForTimeout(900);
      row[scale] = await page.evaluate(() => {
        const p = document.getElementById('reportModal');
        p.classList.add('show'); p.setAttribute('aria-hidden', 'false');
        if (window.__muneaApplyFontScale) window.__muneaApplyFontScale();
        const t = p.querySelector('.nav-title');
        const px = el => el ? parseFloat(getComputedStyle(el).fontSize) : 0;
        return {
          zoom: getComputedStyle(p).zoom,
          navTitle: px(t),
          // computed font-size 不會被 zoom 改變——要證明「真的變大」必須量算繪後的方框
          navTitleRenderedH: t ? +(t.getBoundingClientRect().height).toFixed(1) : 0,
          bodyRenderedW: +(p.getBoundingClientRect().width).toFixed(1),
          // 有沒有東西橫向超出視窗（他們警告的 375px 英/西長文）
          overflow: Math.max(0, Math.ceil(
            document.documentElement.scrollWidth - document.documentElement.clientWidth)),
        };
      });
      await page.close();
    }
    const grew = parseFloat(row.xl.zoom) > parseFloat(row.std.zoom)
      && row.xl.navTitleRenderedH > row.std.navTitleRenderedH;
    const ok = grew && row.xl.overflow === 0 && row.std.overflow === 0;
    if (!ok) bad += 1;
    console.log(`${ok ? 'OK  ' : 'FAIL'} ${locale} ${w}x${h}  zoom ${row.std.zoom}→${row.xl.zoom}  navTitle computed ${row.std.navTitle}→${row.xl.navTitle}px · 算繪高 ${row.std.navTitleRenderedH}→${row.xl.navTitleRenderedH}px  溢位 std=${row.std.overflow} xl=${row.xl.overflow}`);
  }
  await browser.close(); server.close();
  console.log(bad ? `\n❌ ${bad} 個案例不合格` : '\n✅ 四語系放大生效、零橫向溢位');
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
