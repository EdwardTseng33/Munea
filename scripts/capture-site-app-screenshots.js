'use strict';

/**
 * 官網功能區的 App 截圖（三語）：app-status.<lang>.jpg、app-family.<lang>.jpg
 * ------------------------------------------------------------------
 * 做法跟原本中文那兩張一樣：本機假資料伺服器（scripts/app-i18n-fixture-server.js）
 * 開「真的 App 網頁版」→ Chrome 手機尺寸 390×844、2 倍解析度 → 截 780×1688。
 * 畫面全是 App 自己的程式與翻譯畫出來的；只有「家人名字、活動」這些示範內容是我們放進
 * 手機本機儲存的假資料（跟開發者模式的 seedDeveloperFixtures 同一套欄位），換成當地自然的名字。
 *
 * 不碰正式／測試雲端：瀏覽器只准連 127.0.0.1，另外放行 Google Fonts（App 本來就從那裡載字型，
 * 不載的話截出來是系統字型、跟真機不像）。
 *
 * 用法：
 *   MUNEA_PLAYWRIGHT_PATH=<playwright-core 路徑> node scripts/capture-site-app-screenshots.js [--locales en,ja] [--out <資料夾>]
 *   預設輸出 app-site/assets/，三語都要：--locales zh,en,ja（中文輸出成 *.zh.jpg，不會蓋掉原本的中文圖）
 *
 * 西班牙文暫停（2026-11-20 Edward：只專注繁中／英／日），這支不產 es。
 */

const fs = require('node:fs');
const path = require('node:path');
const { createFixtureServer, listen } = require('./app-i18n-fixture-server.js');

const ROOT = path.resolve(__dirname, '..');
const HOST = '127.0.0.1';
const PORT = 4179;
const VIEWPORT = Object.freeze({ width: 390, height: 844 });
const FONT_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);

/** 每個語系的示範家人（名字沿用 App 翻譯檔 demo.family.* 那一組，讀起來是當地人家）。 */
const LOCALES = Object.freeze({
  zh: {
    appLocale: 'zh-TW',
    self: '雅婷',
    grandma: ['阿嬤', '嬤'], daughter: ['美華', '華'], son: ['志明', '明'], grandkid: ['小寶', '寶'],
  },
  en: {
    appLocale: 'en',
    self: 'Emma',
    grandma: ['Grandma', 'G'], daughter: ['Mary', 'M'], son: ['John', 'J'], grandkid: ['Ben', 'B'],
  },
  ja: {
    appLocale: 'ja',
    self: '由美',
    grandma: ['おばあちゃん', 'ばあ'], daughter: ['花子', '花'], son: ['健一', '健'], grandkid: ['たっくん', 'た'],
  },
});

function argValue(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

function playwrightApi() {
  const configured = process.env.MUNEA_PLAYWRIGHT_PATH;
  if (!configured) throw new Error('MUNEA_PLAYWRIGHT_PATH must point to a local playwright(-core) package');
  return require(path.resolve(configured));
}

function chromeExecutable() {
  if (process.env.MUNEA_CHROME_PATH) return process.env.MUNEA_CHROME_PATH;
  const found = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ].find((p) => fs.existsSync(p));
  if (!found) throw new Error('Chrome executable was not found (set MUNEA_CHROME_PATH)');
  return found;
}

/** App 自己的字型連結（從 web/index.html 讀，App 換字型這裡自動跟上）。假資料伺服器會把它們拿掉，這裡補回去。 */
function appFontLinks() {
  const html = fs.readFileSync(path.join(ROOT, 'web', 'index.html'), 'utf8');
  return (html.match(/<link\b[^>]*href="https:\/\/fonts\.googleapis\.com\/css2[^"]*"[^>]*>/g) || []).join('\n');
}

/** 在 App 程式跑之前，把這個語系的示範資料寫進手機本機儲存（欄位跟 seedDeveloperFixtures 一樣）。 */
function seedScript(spec, scene) {
  const data = { spec, scene };
  return `(() => {
    const { spec, scene } = ${JSON.stringify(data)};
    const pad = (n) => String(n).padStart(2, '0');
    const iso = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    const daysFromToday = (n) => { const d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() + n); return d; };
    const set = (k, v) => localStorage.setItem(k, typeof v === 'string' ? v : JSON.stringify(v));
    // 每次都從乾淨的狀態開始
    if (sessionStorage.getItem('munea.capture.seeded') === '1') return;
    localStorage.clear();
    sessionStorage.setItem('munea.capture.seeded', '1');

    set('munea.personProfile', { name: spec.self, nick: spec.self, birth: '', city: '', avatar: '' });
    set('munea.plan', 'pro');
    set('munea.ptsBought', '700');
    if (scene !== 'family') return;

    const fam = [
      [spec.grandma, 'p-ama', 3850, ['開心', 'happy']],
      [spec.daughter, 'p-mei', 8900, ['平靜', 'calm']],
      [spec.son, 'p-zhi', 7600, ['愉快', 'glad']],
      [spec.grandkid, 'p-bao', 8750, ['開心', 'happy']],
    ];
    set('munea.familyGroupId', 'fam-site-screenshot');
    set('munea.cloudPersonId', 'site-screenshot-self');
    set('munea.circleMembers', [{ name: spec.self, init: spec.self[0], tint: 'p-me', self: true }]
      .concat(fam.map(([[name, init], tint]) => ({ name, init, tint, self: false }))));
    const vitals = {};
    fam.forEach(([[name], , steps, mood], i) => {
      const log = {};
      for (let back = 6; back >= 0; back--) {
        log[iso(daysFromToday(-back))] = { steps: back ? 5200 + ((i + back) % 5) * 600 : steps, sleepHours: 7, hr: 70 + i, spo2: 97, bpSys: 118 + i, bpDia: 76 };
      }
      vitals['site-family-' + i] = { name, nick: name, day: '今天', updatedAt: Date.now(), mood: { label: mood[0], key: mood[1], date: iso(daysFromToday(0)) }, ...log[iso(daysFromToday(0))], log };
    });
    set('munea.famVitals', vitals);
    // 自己今天的步數（App 從 Apple 健康帶進來的那一格）
    set('munea.health.last', { s: { steps: 2400 }, at: Date.now() });

    // 一張「一起走路」活動卡；下面接著就是全家狀態（心情＋安好燈）＝功能 03「看見彼此的狀態，也一起玩」。
    // 沒放「揪一攤」卡：英文那張卡的說明句會露出 App 目前英文撇號的字型問題（Can’ t），不適合當官網門面。
    set('munea.activities', [{
      id: Date.now() - 1000, kind: 'walk', owner: spec.self,
      names: [spec.grandma[0], spec.daughter[0], spec.grandkid[0]],
      title: '', goal: 30000, startISO: iso(daysFromToday(0)), days: 2,
      dateISO: iso(daysFromToday(2)), dueTime: '20:00',
    }]);
  })();`;
}

/** 假資料伺服器回的 App 頁面：關掉示範資料重灌（我們自己放）、補回字型、CSP 放行 Google Fonts。 */
async function patchAppDocument(route) {
  const response = await route.fetch();
  let body = await response.text();
  body = body.replace(/seedFixtures: true/g, 'seedFixtures: false');
  body = body.replace('</head>', `${appFontLinks()}\n</head>`);
  const headers = { ...response.headers() };
  headers['content-security-policy'] = (headers['content-security-policy'] || '')
    .replace("font-src 'self' data:", "font-src 'self' data: https://fonts.gstatic.com")
    .replace("style-src 'self' 'unsafe-inline'", "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com");
  await route.fulfill({ response, body, headers });
}

const CJK = /[\u3400-\u9fff\uf900-\ufaff]/u;
const KANA = /[\u3040-\u30ff]/u;

async function capture(browser, code, scene, outDir) {
  const spec = LOCALES[code];
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2, locale: spec.appLocale });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));

  // App 的翻譯檔要比開機畫活動卡早到——真機上雲端同步一定比讀本機翻譯檔慢；
  // 本機假伺服器太快，活動卡會先用中文畫好就不再換（見回報）。這裡讓 app.js 等翻譯檔到了再開跑。
  let catalogDone;
  const catalogReady = new Promise((resolve) => { catalogDone = resolve; });
  page.on('requestfinished', (req) => {
    if (new URL(req.url()).pathname === `/src/i18n/${spec.appLocale}.json`) catalogDone();
  });
  setTimeout(() => catalogDone(), 6000);

  await page.addInitScript(seedScript(spec, scene));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (FONT_HOSTS.has(url.hostname)) return route.continue();
    if (url.hostname !== HOST) return route.abort('blockedbyclient');
    if (route.request().resourceType() === 'document') return patchAppDocument(route);
    if (url.pathname === '/src/auth-config.js') {
      const response = await route.fetch();
      return route.fulfill({ response, body: (await response.text()).replace(/seedFixtures: true/g, 'seedFixtures: false') });
    }
    if (url.pathname === '/src/app.js') {
      await catalogReady;
      await new Promise((r) => setTimeout(r, 250));
    }
    return route.continue();
  });

  await page.goto(`http://${HOST}:${PORT}/?lang=${encodeURIComponent(spec.appLocale)}`, { waitUntil: 'networkidle' });
  await page.waitForFunction((l) => window.MuneaI18n && window.MuneaI18n.initialized && window.MuneaI18n.current() === l, spec.appLocale);
  await page.evaluate(() => document.fonts.ready);
  await page.locator(`[data-view="${scene}"]`).click();
  await page.locator(`#${scene}.active`).waitFor();
  if (scene === 'status') await page.locator('.st-seg [data-period="today"]').click();
  await page.evaluate((id) => {
    window.scrollTo(0, 0);
    const el = document.getElementById(id);
    if (el) el.scrollTop = 0;
  }, scene);
  await page.waitForTimeout(900);

  const text = await page.locator(`#${scene}`).innerText();
  const leaks = [];
  if (code === 'en') leaks.push(...(text.match(new RegExp(CJK.source, 'gu')) || []));
  if (code === 'ja') {
    // 日文本來就有漢字；抓的是「只有中文才會出現」的句子
    for (const s of ['全家健康圈', '今天的狀態', '一起運動', '揪一攤', '大家一起走', '天內', '誰能到', '還沒記錄']) if (text.includes(s)) leaks.push(s);
  }
  const outFile = path.join(outDir, `app-${scene}.${code}.jpg`);
  await page.screenshot({ path: outFile, type: 'jpeg', quality: 86 });
  await context.close();
  return { file: path.relative(ROOT, outFile).replaceAll('\\', '/'), errors, leaks: [...new Set(leaks)].slice(0, 20), kana: KANA.test(text) };
}

async function main() {
  const codes = argValue('--locales', 'en,ja').split(',').map((s) => s.trim()).filter(Boolean);
  for (const c of codes) if (!LOCALES[c]) throw new Error(`unsupported locale: ${c}`);
  const outDir = path.resolve(argValue('--out', path.join(ROOT, 'app-site', 'assets')));
  fs.mkdirSync(outDir, { recursive: true });

  const server = createFixtureServer({ port: PORT });
  await listen(server, PORT);
  const { chromium } = playwrightApi();
  const browser = await chromium.launch({ executablePath: chromeExecutable(), headless: true });
  const results = [];
  try {
    for (const code of codes) {
      for (const scene of ['status', 'family']) results.push({ locale: code, scene, ...(await capture(browser, code, scene, outDir)) });
    }
  } finally {
    await browser.close();
    await new Promise((r) => server.close(r));
  }
  for (const r of results) console.log(`${r.leaks.length || r.errors.length ? '✗' : '✓'} ${r.file}${r.leaks.length ? '  漏翻：' + r.leaks.join(' ') : ''}${r.errors.length ? '  錯誤：' + r.errors.join(' | ') : ''}`);
  if (results.some((r) => r.leaks.length || r.errors.length)) process.exitCode = 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
