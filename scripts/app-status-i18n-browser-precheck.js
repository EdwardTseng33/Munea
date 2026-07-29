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
const PORT = 4177;
const VIEWPORT = Object.freeze({ width: 390, height: 844 });
const LOCALES = Object.freeze([
  Object.freeze({ locale: 'zh-TW', htmlLang: 'zh-Hant-TW' }),
  Object.freeze({ locale: 'en', htmlLang: 'en' }),
  Object.freeze({ locale: 'ja', htmlLang: 'ja' }),
  Object.freeze({ locale: 'es', htmlLang: 'es' }),
]);
const OUTPUT_DIR = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'status-2026-07-29',
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
      '今天的狀態',
      '過去 7 天的狀態',
      '過去 30 天的狀態',
      '情緒監測',
      '健康數據',
      '用藥狀態',
      '還沒設定用藥',
      '管理裝置',
    ];
    return sourceOnly.filter((value) => text.includes(value));
  }
  return [];
}

async function inspectPeriod(page, period) {
  await page.locator(`.st-seg [data-period="${period}"]`).click();
  await page.waitForFunction(
    (expected) => document.querySelector('.st-seg [data-period="' + expected + '"]').style.color === 'rgb(255, 255, 255)',
    period,
  );
  return page.evaluate(() => {
    const screen = document.getElementById('status');
    return {
      horizontalOverflowPixels: Math.max(
        0,
        Math.ceil(screen.scrollWidth - screen.clientWidth),
      ),
      pageTitle: document.getElementById('pageTitle').textContent.trim(),
      observationPeriod: document.getElementById('obsPeriod').textContent.trim(),
      observationText: document.getElementById('obsText').textContent.trim(),
    };
  });
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
    schema: 'munea.app-status-local-browser-precheck.v1',
    recordedAt: new Date().toISOString(),
    result: 'pending',
    releaseEvidence: false,
    sourceBaseCommit: sourceCommit(),
    sourceChangedFiles: sourceChangedFiles(),
    scope: {
      surface: 'screen:status',
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
      automation: 'Playwright local fallback after agent-browser CDP failure',
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
        ),
        expected,
      );
      await page.evaluate(() => {
        if (window.MMPLAN) window.MMPLAN.set('pro');
      });
      await page.locator('[data-view="status"]').click();
      await page.locator('#status.active').waitFor();

      const periods = {};
      for (const period of ['today', 'week', 'month']) {
        periods[period] = await inspectPeriod(page, period);
      }
      await page.locator('.st-seg [data-period="today"]').click();
      await page.evaluate(() => {
        window.scrollTo(0, 0);
        if (document.scrollingElement) document.scrollingElement.scrollTop = 0;
        document.getElementById('status').scrollTop = 0;
      });
      await page.waitForTimeout(450);

      const screenText = await page.locator('#status').innerText();
      const untranslatedSamples = unexpectedSourceCopy(expected.locale, screenText);
      const screenshotPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__status__iphone390x844.png`,
      );
      await page.screenshot({ path: screenshotPath });
      const screenshot = fs.statSync(screenshotPath);
      report.screens[expected.locale] = {
        resolvedLocale: await page.evaluate(() => window.MuneaI18n.current()),
        htmlLang: await page.evaluate(() => document.documentElement.lang),
        periods,
        horizontalOverflowPixels: Math.max(
          ...Object.values(periods).map((item) => item.horizontalOverflowPixels),
        ),
        untranslatedSamples,
        browserErrors,
        translationResult: untranslatedSamples.length ? 'fail' : 'pass',
        layoutResult: Object.values(periods).some(
          (item) => item.horizontalOverflowPixels > 0,
        ) ? 'fail' : 'pass',
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

  const reportPath = path.join(OUTPUT_DIR, 'status-local-browser-precheck.json');
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (report.result !== 'pass-local-precheck') process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
