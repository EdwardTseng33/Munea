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
  'notification-2026-07-29',
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

function gitOutput(args) {
  return execFileSync('git', args, { cwd: ROOT, encoding: 'utf8' }).trim();
}

function unexpectedSourceCopy(locale, text) {
  if (locale === 'en' || locale === 'es') {
    return (text.match(/[\u3400-\u9fff\uf900-\ufaff]+/gu) || []).slice(0, 20);
  }
  if (locale === 'ja') {
    return [
      '通知中心',
      '提醒類型',
      '用藥提醒',
      '看診提醒',
      '家人消息',
      '正在載入通知',
      '請先登入',
    ].filter((value) => text.includes(value));
  }
  return [];
}

function screenshotRecord(filePath) {
  const stat = fs.statSync(filePath);
  return {
    path: path.relative(ROOT, filePath).replaceAll('\\', '/'),
    bytes: stat.size,
    sha256: sha256(filePath),
  };
}

async function surfaceMetrics(page, selector) {
  return page.locator(selector).evaluate((element) => ({
    horizontalOverflowPixels: Math.max(
      0,
      Math.ceil(element.scrollWidth - element.clientWidth),
    ),
    text: element.innerText.trim(),
  }));
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
    schema: 'munea.app-notification-local-browser-precheck.v1',
    recordedAt: new Date().toISOString(),
    result: 'pending',
    releaseEvidence: false,
    sourceBaseCommit: gitOutput(['rev-parse', 'HEAD']),
    sourceChangedFiles: gitOutput(['status', '--short']).split(/\r?\n/).filter(Boolean),
    scope: {
      surfaces: ['notification-settings', 'notification-inbox-signed-out'],
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
    locales: {},
    limitations: [
      'This is a local browser precheck, not exact installed-iPhone visual QA.',
      'Native iOS notification permission, APNs delivery, and notification taps were not exercised.',
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

      await page.locator('[data-view="settings"]').click();
      await page.locator('#settings.active').waitFor();
      await page.locator('#notificationCenterRow').waitFor();
      await page.locator('#notificationCenterRow').click();
      await page.locator('#notificationSettingsPage.show').waitFor();
      await page.waitForTimeout(250);
      const settingsMetrics = await surfaceMetrics(page, '#notificationSettingsPage');
      const settingsPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__notification-settings__iphone390x844.png`,
      );
      await page.screenshot({ path: settingsPath });

      await page.locator('#notificationSettingsBack').click();
      await page.evaluate(() => window.MuneaNotify.openInbox());
      await page.locator('#notificationInboxModal.show').waitFor();
      await page.waitForFunction(() => {
        const list = document.getElementById('notificationInboxList');
        return list && list.textContent.trim().length > 0;
      });
      await page.waitForTimeout(250);
      const inboxMetrics = await surfaceMetrics(page, '#notificationInboxModal');
      const inboxPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__notification-inbox__iphone390x844.png`,
      );
      await page.screenshot({ path: inboxPath });

      const untranslatedSamples = unexpectedSourceCopy(
        expected.locale,
        `${settingsMetrics.text}\n${inboxMetrics.text}`,
      );
      report.locales[expected.locale] = {
        resolvedLocale: await page.evaluate(() => window.MuneaI18n.current()),
        htmlLang: await page.evaluate(() => document.documentElement.lang),
        settings: {
          horizontalOverflowPixels: settingsMetrics.horizontalOverflowPixels,
          screenshot: screenshotRecord(settingsPath),
        },
        inbox: {
          horizontalOverflowPixels: inboxMetrics.horizontalOverflowPixels,
          screenshot: screenshotRecord(inboxPath),
        },
        untranslatedSamples,
        browserErrors,
        translationResult: untranslatedSamples.length ? 'fail' : 'pass',
        layoutResult: (
          settingsMetrics.horizontalOverflowPixels > 0
          || inboxMetrics.horizontalOverflowPixels > 0
        ) ? 'fail' : 'pass',
      };
      await context.close();
    }
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  const localeResults = Object.values(report.locales);
  report.networkSafety.observedExternalRequests = [
    ...new Set(report.networkSafety.observedExternalRequests),
  ];
  report.result = (
    localeResults.length === LOCALES.length
    && report.networkSafety.observedExternalRequests.length === 0
    && localeResults.every((result) => (
      result.translationResult === 'pass'
      && result.layoutResult === 'pass'
      && result.browserErrors.length === 0
    ))
  ) ? 'pass-local-precheck' : 'fail';

  const reportPath = path.join(
    OUTPUT_DIR,
    'notification-local-browser-precheck.json',
  );
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (report.result !== 'pass-local-precheck') process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
