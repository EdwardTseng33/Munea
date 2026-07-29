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
const LOCALES = Object.freeze([
  Object.freeze({ locale: 'zh-TW', htmlLang: 'zh-Hant-TW' }),
  Object.freeze({ locale: 'en', htmlLang: 'en' }),
  Object.freeze({ locale: 'ja', htmlLang: 'ja' }),
  Object.freeze({ locale: 'es', htmlLang: 'es' }),
]);
const EXPECTED_LEGAL_PATHS = Object.freeze({
  'zh-TW': Object.freeze({
    privacy: '/privacy.html',
    terms: '/terms.html',
  }),
  en: Object.freeze({
    privacy: '/legal/en/privacy.html',
    terms: '/legal/en/terms.html',
  }),
  ja: Object.freeze({
    privacy: '/legal/ja/privacy.html',
    terms: '/legal/ja/terms.html',
  }),
  es: Object.freeze({
    privacy: '/legal/es/privacy.html',
    terms: '/legal/es/terms.html',
  }),
});
const OUTPUT_DIR = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'legal-reader-2026-07-29',
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

function screenshotRecord(filePath) {
  const stat = fs.statSync(filePath);
  return {
    path: path.relative(ROOT, filePath).replaceAll('\\', '/'),
    bytes: stat.size,
    sha256: sha256(filePath),
  };
}

function catalog(locale) {
  return JSON.parse(
    fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n', `${locale}.json`), 'utf8'),
  );
}

function sourceLanguageLeaks(locale, text) {
  if (locale === 'zh-TW') return [];
  return [
    '隱私權政策',
    '服務條款',
    '內容載入中',
    '無法載入內容',
    '字幕已開啟',
    '請先使用 Google 或 Apple 登入',
    '標示完成',
  ].filter((sample) => text.includes(sample));
}

async function readerMetrics(page) {
  return page.locator('#readerPage').evaluate((element) => ({
    horizontalOverflowPixels: Math.max(
      0,
      Math.ceil(element.scrollWidth - element.clientWidth),
    ),
    title: document.getElementById('readerTitle').textContent.trim(),
    bodyText: document.getElementById('readerBody').innerText.trim(),
  }));
}

async function openLegalReader(page, kind) {
  const selector = kind === 'privacy' ? '#privacyPolicyRow' : '#termsRow';
  await page.locator(selector).click();
  await page.locator('#readerPage.show').waitFor();
  await page.waitForFunction(() => {
    const body = document.getElementById('readerBody');
    return body && body.querySelector('h4') && body.innerText.trim().length > 100;
  });
  await page.waitForTimeout(120);
  return readerMetrics(page);
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
    schema: 'munea.app-legal-reader-local-browser-precheck.v1',
    recordedAt: new Date().toISOString(),
    result: 'pending',
    releaseEvidence: false,
    sourceBaseCommit: gitOutput(['rev-parse', 'HEAD']),
    sourceChangedFiles: gitOutput(['status', '--short']).split(/\r?\n/).filter(Boolean),
    scope: {
      surfaces: [
        'reader:privacy',
        'reader:terms',
        'modal:auth-chat-gate',
        'chat:caption-feedback',
        'home:task-accessibility',
      ],
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
      automation: 'Playwright local fallback because agent-browser executable is unavailable',
    },
    networkSafety: {
      loopbackBindOnly: true,
      allowedBrowserDomain: HOST,
      observedExternalRequests: [],
    },
    locales: {},
    limitations: [
      'This is a local browser precheck, not exact installed-iPhone visual QA.',
      'Localized legal pages remain draft-only until qualified legal review and runtime release gates pass.',
      'No Gateway, Live Voice, StoreKit, App Store Connect, Supabase, staging, or production service was exercised.',
    ],
  };

  try {
    for (const expected of LOCALES) {
      const localeCatalog = catalog(expected.locale);
      const context = await browser.newContext({ viewport: VIEWPORT });
      const page = await context.newPage();
      const browserErrors = [];
      const observedLegalPaths = [];
      page.on('pageerror', (error) => browserErrors.push(error.message));
      page.on('console', (message) => {
        if (message.type() === 'error') browserErrors.push(message.text());
      });
      page.on('response', (response) => {
        const url = new URL(response.url());
        if (/\/(?:legal\/[^/]+\/)?(?:privacy|terms)\.html$/.test(url.pathname)) {
          observedLegalPaths.push(url.pathname);
        }
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
      const privacy = await openLegalReader(page, 'privacy');
      const privacyPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__privacy-reader__iphone390x844.png`,
      );
      await page.screenshot({ path: privacyPath });
      await page.locator('#readerBack').click();
      await page.locator('#readerPage').waitFor({ state: 'hidden' });

      const terms = await openLegalReader(page, 'terms');
      await page.locator('#readerBack').click();
      await page.locator('#readerPage').waitFor({ state: 'hidden' });

      await page.locator('[data-view="home"]').click();
      await page.locator('#home.active').waitFor();
      await page.locator('#startCall').click();
      await page.locator('#authSheet.show').waitFor();
      const authMessage = (await page.locator('#authMessage').innerText()).trim();
      const authTerms = (await page.locator('#authSheet .auth-terms').innerText()).trim();
      const authPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__chat-sign-in-gate__iphone390x844.png`,
      );
      await page.screenshot({ path: authPath });
      await page.locator('#authSheet .auth-close').click();
      await page.locator('#authSheet').waitFor({ state: 'hidden' });

      await page.evaluate(() => document.getElementById('captionToggle').click());
      await page.locator('#toast.show').waitFor();
      const captionToast = (await page.locator('#toast').innerText()).trim();
      const taskLabels = await page.locator('#taskCard .task-check')
        .evaluateAll((elements) => elements.map((element) => element.getAttribute('aria-label')));

      const checkedText = [
        privacy.title,
        privacy.bodyText,
        terms.title,
        terms.bodyText,
        authMessage,
        authTerms,
        captionToast,
        ...taskLabels,
      ].join('\n');
      const untranslatedSamples = sourceLanguageLeaks(expected.locale, checkedText);
      const expectedPaths = EXPECTED_LEGAL_PATHS[expected.locale];
      const expectedPathResult = (
        observedLegalPaths.includes(expectedPaths.privacy)
        && observedLegalPaths.includes(expectedPaths.terms)
      );
      const expectedTextResult = (
        privacy.title === localeCatalog['reader.privacyTitle']
        && terms.title === localeCatalog['reader.termsTitle']
        && authMessage === localeCatalog['auth.chatSignInRequired']
        && authTerms.includes(localeCatalog['auth.termsPrefix'])
        && authTerms.includes(localeCatalog['auth.termsLink'])
        && authTerms.includes(localeCatalog['auth.aiProcessingDisclosure'])
        && captionToast === localeCatalog['voice.caption.enabled']
        && taskLabels.length > 0
        && taskLabels.every((label) => label === localeCatalog['accessibility.markComplete'])
      );

      report.locales[expected.locale] = {
        resolvedLocale: await page.evaluate(() => window.MuneaI18n.current()),
        htmlLang: await page.evaluate(() => document.documentElement.lang),
        privacy: {
          title: privacy.title,
          bodyCharacters: privacy.bodyText.length,
          horizontalOverflowPixels: privacy.horizontalOverflowPixels,
          expectedPath: expectedPaths.privacy,
          screenshot: screenshotRecord(privacyPath),
        },
        terms: {
          title: terms.title,
          bodyCharacters: terms.bodyText.length,
          horizontalOverflowPixels: terms.horizontalOverflowPixels,
          expectedPath: expectedPaths.terms,
        },
        auth: {
          message: authMessage,
          terms: authTerms,
          screenshot: screenshotRecord(authPath),
        },
        captionToast,
        taskCompletionAriaLabels: [...new Set(taskLabels)],
        observedLegalPaths: [...new Set(observedLegalPaths)],
        untranslatedSamples,
        browserErrors,
        routeResult: expectedPathResult ? 'pass' : 'fail',
        translationResult: expectedTextResult && !untranslatedSamples.length ? 'pass' : 'fail',
        layoutResult: (
          privacy.horizontalOverflowPixels === 0
          && terms.horizontalOverflowPixels === 0
        ) ? 'pass' : 'fail',
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
      result.routeResult === 'pass'
      && result.translationResult === 'pass'
      && result.layoutResult === 'pass'
      && result.browserErrors.length === 0
    ))
  ) ? 'pass-local-precheck' : 'fail';

  const reportPath = path.join(OUTPUT_DIR, 'legal-reader-local-browser-precheck.json');
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (report.result !== 'pass-local-precheck') process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
