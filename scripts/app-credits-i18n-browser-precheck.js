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
const PORT = 4179;
const VIEWPORT = Object.freeze({ width: 390, height: 844 });
const CREDIT_BALANCE = 1234;
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
  'credits-2026-07-29',
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

function catalog(locale) {
  return JSON.parse(
    fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n', `${locale}.json`), 'utf8'),
  );
}

function format(template, values) {
  return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key) => (
    Object.hasOwn(values, key) ? String(values[key]) : `{${key}}`
  ));
}

function screenshotEvidence(filePath) {
  const stat = fs.statSync(filePath);
  return {
    path: path.relative(ROOT, filePath).replaceAll('\\', '/'),
    bytes: stat.size,
    sha256: sha256(filePath),
  };
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
    schema: 'munea.app-credits-local-browser-precheck.v1',
    recordedAt: new Date().toISOString(),
    result: 'pending',
    releaseEvidence: false,
    sourceBaseCommit: sourceCommit(),
    sourceChangedFiles: sourceChangedFiles(),
    scope: {
      surfaces: ['chat:idle/credit-balance', 'modal:top-up/credits-exhausted'],
      environment: 'local-fixture-only',
      baseUrl: `http://${HOST}:${PORT}`,
      productionTouched: false,
      stagingTouched: false,
      appStoreConnectTouched: false,
      storeKitTouched: false,
      gatewayTouched: false,
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
      'No production, staging, StoreKit, Gateway, Voice, Avatar, Supabase, or App Store Connect service was exercised.',
    ],
  };

  try {
    for (const expected of LOCALES) {
      const copy = catalog(expected.locale);
      const formattedCredits = new Intl.NumberFormat(expected.locale).format(CREDIT_BALANCE);
      const expectedLabels = {
        balance: format(copy['settings.creditsBalance'], { credits: formattedCredits }),
        callStatus: copy['voice.call.offline'],
        callAction: copy['voice.call.start'],
        captions: copy['voice.caption.label'],
        microphone: copy['voice.microphone.label'],
        title: copy['credits.exhaustedTitle'],
        body: copy['credits.exhaustedBody'],
        primary: copy['settings.topUpCredits'],
        secondary: copy['common.notNow'],
      };
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
      const bootstrapState = await page.evaluate(() => ({
        readyState: document.readyState,
        hasI18n: Boolean(window.MuneaI18n),
        initialized: Boolean(window.MuneaI18n && window.MuneaI18n.initialized),
        locale: window.MuneaI18n ? window.MuneaI18n.current() : '',
        htmlLang: document.documentElement.lang,
        pointsTestReady: Boolean(
          window.__ptsTest
          && typeof window.__ptsTest.setRemaining === 'function'
          && typeof window.__ptsTest.showExhausted === 'function'
          && typeof window.__ptsTest.showIdleChat === 'function'
        ),
      }));
      if (
        !bootstrapState.initialized
        || bootstrapState.locale !== expected.locale
        || bootstrapState.htmlLang !== expected.htmlLang
        || bootstrapState.pointsTestReady !== true
      ) {
        throw new Error(
          `App bootstrap mismatch for ${expected.locale}: `
          + JSON.stringify({ bootstrapState, browserErrors }),
        );
      }
      await page.waitForFunction(
        ({ locale, htmlLang }) => (
          window.MuneaI18n
          && window.MuneaI18n.initialized
          && window.MuneaI18n.current() === locale
          && document.documentElement.lang === htmlLang
          && window.__ptsTest
          && typeof window.__ptsTest.setRemaining === 'function'
          && typeof window.__ptsTest.showExhausted === 'function'
          && typeof window.__ptsTest.showIdleChat === 'function'
        ),
        expected,
      );
      await page.evaluate((balance) => {
        window.__ptsTest.setRemaining(balance);
        window.__ptsTest.showIdleChat();
      }, CREDIT_BALANCE);
      await page.waitForFunction(
        (labels) => (
          document.querySelector('.hud-pill.pts')?.textContent.trim() === labels.balance
          && document.querySelector('.fn-status')?.textContent.trim() === labels.callStatus
          && document.getElementById('callToggleLabel')?.textContent.trim() === labels.callAction
          && document.querySelector('#captionToggle span')?.textContent.trim() === labels.captions
          && document.querySelector('#chatMic span')?.textContent.trim() === labels.microphone
        ),
        expectedLabels,
      );
      const balanceHud = page.locator('.face-hud');
      const balanceVisible = await balanceHud.isVisible();
      const balanceLayout = await balanceHud.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return {
          width: Math.ceil(rect.width),
          height: Math.ceil(rect.height),
          left: Math.floor(rect.left),
          right: Math.ceil(rect.right),
          top: Math.floor(rect.top),
          bottom: Math.ceil(rect.bottom),
          horizontalOverflowPixels: Math.max(
            0,
            Math.ceil(element.scrollWidth - element.clientWidth),
          ),
        };
      });
      const nameLayout = await page.locator('.face-name').evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return {
          left: Math.floor(rect.left),
          right: Math.ceil(rect.right),
          top: Math.floor(rect.top),
          bottom: Math.ceil(rect.bottom),
        };
      });
      const headerGapPixels = balanceLayout.left - nameLayout.right;
      await page.waitForTimeout(500);

      const balancePath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__credit-balance__iphone390x844.png`,
      );
      await page.screenshot({ path: balancePath });

      await page.evaluate(() => window.__ptsTest.showExhausted());
      await page.waitForSelector('#mm-pts');
      const popup = page.locator('#mm-pts');
      const labels = await popup.evaluate((element) => ({
        balance: document.querySelector('.hud-pill.pts')?.textContent.trim() || '',
        callStatus: document.querySelector('.fn-status')?.textContent.trim() || '',
        callAction: document.getElementById('callToggleLabel')?.textContent.trim() || '',
        captions: document.querySelector('#captionToggle span')?.textContent.trim() || '',
        microphone: document.querySelector('#chatMic span')?.textContent.trim() || '',
        title: element.querySelector('[data-points-copy="title"]')?.textContent.trim() || '',
        body: element.querySelector('[data-points-copy="body"]')?.textContent.trim() || '',
        primary: element.querySelector('[data-points-action="top-up"]')?.textContent.trim() || '',
        secondary: element.querySelector('[data-points-action="dismiss"]')?.textContent.trim() || '',
      }));
      const cardLayout = await popup.locator(':scope > div').evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return {
          width: Math.ceil(rect.width),
          height: Math.ceil(rect.height),
          left: Math.floor(rect.left),
          right: Math.ceil(rect.right),
          top: Math.floor(rect.top),
          bottom: Math.ceil(rect.bottom),
          horizontalOverflowPixels: Math.max(
            0,
            Math.ceil(element.scrollWidth - element.clientWidth),
          ),
          verticalOverflowPixels: Math.max(
            0,
            Math.ceil(element.scrollHeight - element.clientHeight),
          ),
        };
      });
      const pageState = await page.evaluate(() => ({
        bodyTextLength: document.body.innerText.trim().length,
        errorOverlay: Boolean(document.querySelector(
          '[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay',
        )),
        documentHorizontalOverflowPixels: Math.max(
          0,
          Math.ceil(document.documentElement.scrollWidth - document.documentElement.clientWidth),
        ),
      }));
      const popupPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__credits-exhausted__iphone390x844.png`,
      );
      await page.screenshot({ path: popupPath });

      const mismatches = Object.entries(expectedLabels)
        .filter(([key, value]) => labels[key] !== value)
        .map(([key, value]) => ({ key, expected: value, actual: labels[key] }));
      const cardInsideViewport = (
        cardLayout.left >= 0
        && cardLayout.right <= VIEWPORT.width
        && cardLayout.top >= 0
        && cardLayout.bottom <= VIEWPORT.height
      );
      report.screens[expected.locale] = {
        resolvedLocale: await page.evaluate(() => window.MuneaI18n.current()),
        htmlLang: await page.evaluate(() => document.documentElement.lang),
        labels,
        expectedLabels,
        mismatches,
        browserErrors,
        balanceVisible,
        balanceLayout,
        nameLayout,
        headerGapPixels,
        pageState,
        cardLayout,
        cardInsideViewport,
        translationResult: mismatches.length === 0 ? 'pass' : 'fail',
        layoutResult: (
          cardInsideViewport
          && balanceVisible
          && balanceLayout.left >= 0
          && balanceLayout.right <= VIEWPORT.width
          && balanceLayout.horizontalOverflowPixels === 0
          && headerGapPixels >= 8
          && cardLayout.horizontalOverflowPixels === 0
          && cardLayout.verticalOverflowPixels === 0
          && pageState.documentHorizontalOverflowPixels === 0
        ) ? 'pass' : 'fail',
        screenshots: {
          balance: screenshotEvidence(balancePath),
          exhausted: screenshotEvidence(popupPath),
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
      && screen.pageState.bodyTextLength > 0
      && screen.pageState.errorOverlay === false
    ))
  ) ? 'pass-local-precheck' : 'fail';

  const reportPath = path.join(OUTPUT_DIR, 'credits-local-browser-precheck.json');
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (report.result !== 'pass-local-precheck') process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
