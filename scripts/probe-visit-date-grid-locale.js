#!/usr/bin/env node
/* 就診日期格 · 四語系實測探針
 *
 * 為什麼需要另外一支：456 張捕捉的 harness 是用 showModal() 直接把 #visitModal
 * 加上 .show，**不會**點 #visitEntry，所以 buildCalGrid() 從來不會被觸發——
 * 那 14 格日期在整個 gate 裡是隱形的，寫死中文也沒有任何測試會發現。
 * 這支走使用者真正的路徑（點 #visitEntry）把格子建出來再驗。
 *
 * 跑法：MUNEA_PLAYWRIGHT_PATH=... MUNEA_CHROME_PATH=... node scripts/probe-visit-date-grid-locale.js
 */
const { createFixtureServer } = require('./app-i18n-fixture-server.js');
const { chromium } = require(process.env.MUNEA_PLAYWRIGHT_PATH || 'playwright');
const PORT = 4455;
(async () => {
  const server = createFixtureServer({ port: PORT });
  await new Promise(r => server.listen(PORT, '127.0.0.1', r));
  const browser = await chromium.launch({
    executablePath: process.env.MUNEA_CHROME_PATH, headless: true });
  let bad = 0;
  for (const locale of ['zh-TW', 'en', 'ja', 'es']) {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(`http://127.0.0.1:${PORT}/?lang=${locale}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(900);
    const r = await page.evaluate(() => {
      const entry = document.getElementById('visitEntry');
      if (entry) entry.click();               // 真的走使用者路徑，才會 buildCalGrid
      const cells = [...document.querySelectorAll('#visitDatePick .cal-cell small')]
        .map(e => e.textContent.trim());
      return { cells: cells.slice(0, 5), count: cells.length };
    });
    // 非中文語系不該出現中日韓字（ja 例外：日文本來就有漢字，只擋「週」這種中文寫法）
    const leak = (locale === 'en' || locale === 'es')
      ? r.cells.filter(c => /[㐀-鿿]/.test(c))
      : (locale === 'ja' ? r.cells.filter(c => c.includes('週')) : []);
    const ok = r.count > 0 && leak.length === 0;
    if (!ok) bad += 1;
    console.log(`${ok ? 'OK  ' : 'FAIL'} ${locale.padEnd(6)} ${r.count} 格  前五格: ${r.cells.join(' ')}${leak.length ? '  ← 漏字 ' + leak.join(',') : ''}`);
    await page.close();
  }
  await browser.close(); server.close();
  console.log(bad ? `\n❌ ${bad} 個語系不合格` : '\n✅ 就診日期格四語系正確');
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
