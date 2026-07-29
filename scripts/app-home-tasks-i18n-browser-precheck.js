'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const {
  createFixtureServer,
  listen,
} = require('./app-i18n-fixture-server.js');

const ROOT = path.resolve(__dirname, '..');
const HOST = '127.0.0.1';
const PORT = 4178;
const VIEWPORT = Object.freeze({ width: 390, height: 844 });
const LOCALES = Object.freeze([
  Object.freeze({
    locale: 'zh-TW',
    htmlLang: 'zh-Hant-TW',
    medicationName: '維生素D',
    expected: ['吃維生素D', '早餐後', '回診', '和家人的約', '今天走了'],
  }),
  Object.freeze({
    locale: 'en',
    htmlLang: 'en',
    medicationName: 'Vitamin D',
    expected: ['Take Vitamin D', 'After breakfast', 'Follow-up visit', 'Time with family', 'You walked'],
  }),
  Object.freeze({
    locale: 'ja',
    htmlLang: 'ja',
    medicationName: 'ビタミンD',
    expected: ['ビタミンDを飲む', '朝食後', '通院', '家族との予定', '今日は'],
  }),
  Object.freeze({
    locale: 'es',
    htmlLang: 'es',
    medicationName: 'Vitamina D',
    expected: ['Tomar Vitamina D', 'Después del desayuno', 'Cita médica', 'Plan familiar', 'Hoy has dado'],
  }),
]);
const OUTPUT_DIR = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'home-tasks-2026-07-29',
);

function playwrightApi() {
  const configured = process.env.MUNEA_PLAYWRIGHT_PATH;
  if (!configured) {
    throw new Error('MUNEA_PLAYWRIGHT_PATH must point to a local Playwright package');
  }
  return require(path.resolve(configured));
}

function chromeExecutable() {
  const configured = process.env.MUNEA_CHROME_PATH;
  if (configured) return configured;
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error('Chrome executable was not found');
  return found;
}

function sha256(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function sourceCommit() {
  return execFileSync('git', ['rev-parse', 'HEAD'], {
    cwd: ROOT,
    encoding: 'utf8',
  }).trim();
}

function sourceChangedFiles() {
  return execFileSync('git', ['status', '--short'], {
    cwd: ROOT,
    encoding: 'utf8',
  }).trim().split(/\r?\n/).filter(Boolean);
}

function unexpectedSourceCopy(locale, text) {
  if (locale === 'en' || locale === 'es') {
    return (text.match(/[\u3400-\u9fff\uf900-\ufaff]+/gu) || []).slice(0, 20);
  }
  if (locale === 'ja') {
    const sourceOnly = [
      '今天走了',
      '早餐後',
      '記得帶健保卡',
      '和家人的約',
      '記得準時赴約',
    ];
    return sourceOnly.filter((value) => text.includes(value));
  }
  return [];
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const server = createFixtureServer({ port: PORT });
  await listen(server, PORT);

  const { chromium } = playwrightApi();
  const browser = await chromium.launch({
    executablePath: chromeExecutable(),
    headless: true,
  });
  const report = {
    schema: 'munea.app-home-tasks-local-browser-precheck.v1',
    recordedAt: new Date().toISOString(),
    result: 'pending',
    releaseEvidence: false,
    sourceBaseCommit: sourceCommit(),
    sourceChangedFiles: sourceChangedFiles(),
    scope: {
      surface: 'screen:home/dynamic-daily-tasks',
      environment: 'local-fixture-only',
      baseUrl: `http://${HOST}:${PORT}`,
      productionTouched: false,
      stagingTouched: false,
      appStoreConnectTouched: false,
      installedAppUsed: false,
    },
    runtime: {
      browser: 'Google Chrome',
      viewport: VIEWPORT,
      fixtureServer: 'scripts/app-i18n-fixture-server.js',
      automation: 'Playwright local fallback after agent-browser executable was unavailable',
    },
    networkSafety: {
      loopbackBindOnly: true,
      allowedBrowserDomain: HOST,
      observedExternalRequests: [],
    },
    screens: {},
    limitations: [
      'This is a local browser precheck, not exact installed-iPhone visual QA.',
      'No Gateway, Live Voice, StoreKit, App Store Connect, Supabase, staging, or production service was exercised.',
    ],
  };

  try {
    for (const expected of LOCALES) {
      const context = await browser.newContext({ viewport: VIEWPORT });
      const page = await context.newPage();
      const browserErrors = [];
      page.on('pageerror', (error) => browserErrors.push(error.message));
      page.on('console', (message) => {
        if (message.type() === 'error') browserErrors.push(message.text());
      });
      await page.route('**/*', async (route) => {
        const requestUrl = new URL(route.request().url());
        if (requestUrl.hostname === HOST) {
          await route.continue();
          return;
        }
        report.networkSafety.observedExternalRequests.push(requestUrl.hostname);
        await route.abort('blockedbyclient');
      });

      await page.goto(
        `http://${HOST}:${PORT}/?lang=${encodeURIComponent(expected.locale)}`,
        { waitUntil: 'networkidle' },
      );
      await page.waitForFunction(
        ({ locale, htmlLang }) => (
          window.MuneaI18n
          && window.MuneaI18n.initialized
          && window.MuneaI18n.current() === locale
          && document.documentElement.lang === htmlLang
          && typeof window.__muneaRenderDailyTasks === 'function'
          && typeof window.__muneaSetSteps === 'function'
        ),
        expected,
      );

      await page.evaluate(({ medicationName }) => {
        const now = new Date();
        const today = [
          now.getFullYear(),
          String(now.getMonth() + 1).padStart(2, '0'),
          String(now.getDate()).padStart(2, '0'),
        ].join('-');
        localStorage.setItem('munea.meds', JSON.stringify([
          { name: medicationName, time: '早餐後', days: '每天' },
        ]));
        localStorage.setItem('munea.medDone.' + today, '{}');
        localStorage.setItem('munea.visits', JSON.stringify([
          { dateISO: today, time: '09:30', title: '', label: '' },
        ]));
        localStorage.setItem('munea.activities', JSON.stringify([
          { kind: 'event', dateISO: today, time: '14:00', title: '', place: '' },
        ]));
        window.MuneaMedication = null;
        window.__muneaRenderDailyTasks();
        window.__muneaSetSteps(321);
      }, expected);

      await page.waitForFunction(() => (
        document.getElementById('visitTask').style.display !== 'none'
        && document.getElementById('eventTask').style.display !== 'none'
        && document.getElementById('pillTitle').textContent.trim().length > 0
      ));

      const labels = await page.evaluate(() => ({
        pillTitle: document.getElementById('pillTitle').textContent.trim(),
        pillSub: document.getElementById('pillSub').textContent.trim(),
        visitTitle: document.getElementById('visitTaskTitle').textContent.trim(),
        visitSub: document.getElementById('visitTaskSub').textContent.trim(),
        visitTime: document.getElementById('visitTaskTime').textContent.trim(),
        eventTitle: document.getElementById('eventTaskTitle').textContent.trim(),
        eventSub: document.getElementById('eventTaskSub').textContent.trim(),
        eventTime: document.getElementById('eventTaskTime').textContent.trim(),
        walkSub: document.getElementById('walkSub').textContent.trim(),
        walkChip: document.getElementById('walkChip').textContent.trim(),
      }));
      const taskCard = page.locator('#taskCard');
      const screenText = await taskCard.innerText();
      const missingExpected = expected.expected.filter((value) => !screenText.includes(value));
      const untranslatedSamples = unexpectedSourceCopy(expected.locale, screenText);
      const layout = await taskCard.evaluate((element) => ({
        horizontalOverflowPixels: Math.max(
          0,
          Math.ceil(element.scrollWidth - element.clientWidth),
        ),
        visibleRows: [...element.querySelectorAll('.task-item')]
          .filter((item) => getComputedStyle(item).display !== 'none').length,
      }));
      const screenshotPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__home-dynamic-tasks__iphone390x844.png`,
      );
      await taskCard.screenshot({ path: screenshotPath });
      const screenshot = fs.statSync(screenshotPath);
      report.screens[expected.locale] = {
        resolvedLocale: await page.evaluate(() => window.MuneaI18n.current()),
        htmlLang: await page.evaluate(() => document.documentElement.lang),
        labels,
        missingExpected,
        untranslatedSamples,
        browserErrors,
        horizontalOverflowPixels: layout.horizontalOverflowPixels,
        visibleRows: layout.visibleRows,
        translationResult: (
          missingExpected.length === 0
          && untranslatedSamples.length === 0
        ) ? 'pass' : 'fail',
        layoutResult: (
          layout.horizontalOverflowPixels === 0
          && layout.visibleRows >= 4
        ) ? 'pass' : 'fail',
        screenshot: {
          path: path.relative(ROOT, screenshotPath).replaceAll('\\', '/'),
          bytes: screenshot.size,
          sha256: sha256(screenshotPath),
        },
      };
      await context.close();
    }
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  const screens = Object.values(report.screens);
  report.networkSafety.observedExternalRequests = [
    ...new Set(report.networkSafety.observedExternalRequests),
  ];
  report.result = (
    screens.length === LOCALES.length
    && report.networkSafety.observedExternalRequests.length === 0
    && screens.every((screen) => (
      screen.translationResult === 'pass'
      && screen.layoutResult === 'pass'
      && screen.browserErrors.length === 0
    ))
  ) ? 'pass-local-precheck' : 'fail';

  const reportPath = path.join(OUTPUT_DIR, 'home-tasks-local-browser-precheck.json');
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (report.result !== 'pass-local-precheck') process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
