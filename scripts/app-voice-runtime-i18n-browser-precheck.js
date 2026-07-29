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
const PORT = 4180;
const VIEWPORT = Object.freeze({ width: 390, height: 844 });
const LOCALES = Object.freeze([
  Object.freeze({ locale: 'zh-TW', htmlLang: 'zh-Hant-TW' }),
  Object.freeze({ locale: 'en', htmlLang: 'en' }),
  Object.freeze({ locale: 'ja', htmlLang: 'ja' }),
  Object.freeze({ locale: 'es', htmlLang: 'es' }),
]);
const HINTS = Object.freeze({
  playbackBlocked: 'voice.runtime.playbackBlocked',
  audioOnlyFallback: 'voice.runtime.audioOnlyFallback',
  microphoneTapToResume: 'voice.runtime.microphoneTapToResume',
  listening: 'voice.runtime.listening',
  reconnecting: 'voice.runtime.reconnecting',
  microphonePermission: 'voice.runtime.microphonePermission',
  heard: 'voice.runtime.heard',
  thinking: 'voice.runtime.thinking',
  didNotHear: 'voice.runtime.didNotHear',
  recordingTapWhenDone: 'voice.runtime.recordingTapWhenDone',
  microphoneMuted: 'voice.runtime.microphoneMuted',
  microphoneMutedHint: 'voice.runtime.microphoneMutedHint',
});
const CAPTIONS = Object.freeze({
  recovered: Object.freeze({
    title: 'voice.runtime.recoveredTitle',
    body: 'voice.runtime.recoveredBody',
  }),
  degraded: Object.freeze({
    title: 'voice.runtime.degradedTitle',
    body: 'voice.runtime.degradedBody',
  }),
});
const OUTPUT_DIR = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'voice-runtime-2026-07-29',
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
  const found = candidates.find(candidate => fs.existsSync(candidate));
  if (!found) throw new Error('Chrome executable was not found');
  return found;
}

function catalog(locale) {
  return JSON.parse(
    fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n', `${locale}.json`), 'utf8'),
  );
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

function screenshotEvidence(filePath) {
  const data = fs.readFileSync(filePath);
  return {
    path: path.relative(ROOT, filePath).replaceAll('\\', '/'),
    bytes: data.length,
    sha256: crypto.createHash('sha256').update(data).digest('hex'),
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
    schema: 'munea.app-voice-runtime-local-browser-precheck.v1',
    recordedAt: new Date().toISOString(),
    result: 'pending',
    releaseEvidence: false,
    sourceBaseCommit: sourceCommit(),
    sourceChangedFiles: sourceChangedFiles(),
    scope: {
      surfaces: [
        'chat:active/runtime-hints',
        'chat:active/recovered-caption',
        'chat:active/degraded-caption',
      ],
      environment: 'local-fixture-only',
      baseUrl: `http://${HOST}:${PORT}`,
      productionTouched: false,
      stagingTouched: false,
      appStoreConnectTouched: false,
      gatewayTouched: false,
      voiceTouched: false,
      avatarTouched: false,
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
    locales: {},
    limitations: [
      'This is a local browser precheck, not exact installed-iPhone visual QA.',
      'Hidden runtime hints were contract-checked programmatically; visible recovery captions were also screenshot-checked.',
      'No production, staging, Gateway, Voice, Avatar, Supabase, App Store Connect, or StoreKit service was exercised.',
    ],
  };

  try {
    for (const expected of LOCALES) {
      const copy = catalog(expected.locale);
      const context = await browser.newContext({ viewport: VIEWPORT });
      const page = await context.newPage();
      const browserErrors = [];
      page.on('pageerror', error => browserErrors.push(error.message));
      page.on('console', message => {
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
          && window.__ptsTest
          && typeof window.__ptsTest.showIdleChat === 'function'
          && typeof window.__ptsTest.showVoiceRuntimeHint === 'function'
          && typeof window.__ptsTest.showVoiceRuntimeCaption === 'function'
        ),
        expected,
      );
      await page.evaluate(() => window.__ptsTest.showIdleChat());

      const observedHints = {};
      for (const [state, key] of Object.entries(HINTS)) {
        const observed = await page.evaluate(
          runtimeState => window.__ptsTest.showVoiceRuntimeHint(runtimeState),
          state,
        );
        if (observed !== copy[key]) {
          throw new Error(
            `${expected.locale}:${state} hint mismatch: `
            + JSON.stringify({ expected: copy[key], observed }),
          );
        }
        observedHints[state] = observed;
      }

      const captionResults = {};
      for (const [state, keys] of Object.entries(CAPTIONS)) {
        await page.evaluate(
          runtimeState => window.__ptsTest.showVoiceRuntimeCaption(runtimeState),
          state,
        );
        const box = page.locator('.face-caption-box');
        await box.waitFor({ state: 'visible' });
        const observed = await box.evaluate((element) => {
          const rect = element.getBoundingClientRect();
          const small = element.querySelector('small');
          const titleNode = [...element.childNodes].find(node => node.nodeType === Node.TEXT_NODE);
          return {
            title: titleNode ? titleNode.textContent.trim() : '',
            body: small ? small.textContent.trim() : '',
            layout: {
              left: Math.floor(rect.left),
              right: Math.ceil(rect.right),
              top: Math.floor(rect.top),
              bottom: Math.ceil(rect.bottom),
              width: Math.ceil(rect.width),
              height: Math.ceil(rect.height),
              horizontalOverflowPixels: Math.max(
                0,
                Math.ceil(element.scrollWidth - element.clientWidth),
              ),
              verticalOverflowPixels: Math.max(
                0,
                Math.ceil(element.scrollHeight - element.clientHeight),
              ),
            },
          };
        });
        if (observed.title !== copy[keys.title] || observed.body !== copy[keys.body]) {
          throw new Error(
            `${expected.locale}:${state} caption mismatch: `
            + JSON.stringify({ expected: [copy[keys.title], copy[keys.body]], observed }),
          );
        }
        if (
          observed.layout.left < 0
          || observed.layout.right > VIEWPORT.width
          || observed.layout.top < 0
          || observed.layout.bottom > VIEWPORT.height
          || observed.layout.horizontalOverflowPixels > 0
          || observed.layout.verticalOverflowPixels > 0
        ) {
          throw new Error(
            `${expected.locale}:${state} caption overflow: ${JSON.stringify(observed.layout)}`,
          );
        }
        const screenshotPath = path.join(OUTPUT_DIR, `${expected.locale}-${state}.png`);
        await page.screenshot({ path: screenshotPath, fullPage: false });
        captionResults[state] = {
          expectedTitle: copy[keys.title],
          expectedBody: copy[keys.body],
          observed,
          screenshot: screenshotEvidence(screenshotPath),
        };
      }

      if (browserErrors.length) {
        throw new Error(`${expected.locale} browser errors: ${JSON.stringify(browserErrors)}`);
      }
      report.locales[expected.locale] = {
        htmlLang: expected.htmlLang,
        observedHints,
        captions: captionResults,
        browserErrors,
      };
      await context.close();
    }

    report.networkSafety.observedExternalRequests = [
      ...new Set(report.networkSafety.observedExternalRequests),
    ];
    if (report.networkSafety.observedExternalRequests.length) {
      throw new Error(
        `External requests were attempted: ${report.networkSafety.observedExternalRequests.join(', ')}`,
      );
    }
    report.result = 'pass-local-precheck';
  } catch (error) {
    report.result = 'fail-local-precheck';
    report.error = error.stack || String(error);
    throw error;
  } finally {
    report.completedAt = new Date().toISOString();
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'voice-runtime-local-browser-precheck.json'),
      `${JSON.stringify(report, null, 2)}\n`,
      'utf8',
    );
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }

  process.stdout.write(
    `Voice runtime i18n local browser precheck PASS: ${LOCALES.length} locales, `
    + `${Object.keys(HINTS).length} hidden hints and `
    + `${Object.keys(CAPTIONS).length * LOCALES.length} visible caption screenshots\n`,
  );
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
