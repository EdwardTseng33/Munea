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
const PORT = 4181;
const VIEWPORT = Object.freeze({ width: 390, height: 844 });
const LOCALES = Object.freeze([
  Object.freeze({
    locale: 'zh-TW',
    htmlLang: 'zh-Hant-TW',
    medicationName: '脈優',
    sourceOnly: [],
  }),
  Object.freeze({
    locale: 'en',
    htmlLang: 'en',
    medicationName: 'Metformin',
    sourceOnly: [],
  }),
  Object.freeze({
    locale: 'ja',
    htmlLang: 'ja',
    medicationName: 'メトホルミン',
    sourceOnly: [
      '這個時段沒有藥',
      '什麼時候吃',
      '吃多久',
      '加入提醒',
      '我吃過了',
      '分鐘後再提醒',
      '配溫開水',
    ],
  }),
  Object.freeze({
    locale: 'es',
    htmlLang: 'es',
    medicationName: 'Metformina',
    sourceOnly: [],
  }),
]);
const OUTPUT_DIR = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'medication-2026-07-29',
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

function format(template, values) {
  return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key) => (
    Object.hasOwn(values, key) ? String(values[key]) : `{${key}}`
  ));
}

function screenshotEvidence(filePath) {
  const data = fs.readFileSync(filePath);
  return {
    path: path.relative(ROOT, filePath).replaceAll('\\', '/'),
    bytes: data.length,
    sha256: crypto.createHash('sha256').update(data).digest('hex'),
  };
}

function unexpectedSourceCopy(locale, sourceOnly, text) {
  if (locale === 'en' || locale === 'es') {
    return (text.match(/[\u3400-\u9fff\uf900-\ufaff]+/gu) || []).slice(0, 20);
  }
  return sourceOnly.filter(value => text.includes(value));
}

async function layoutFor(locator) {
  return locator.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const visibleChildren = [...element.querySelectorAll('*')].filter((child) => {
      const style = getComputedStyle(child);
      const childRect = child.getBoundingClientRect();
      return style.display !== 'none'
        && style.visibility !== 'hidden'
        && childRect.width > 0
        && childRect.height > 0;
    });
    return {
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
      overflowingChildren: visibleChildren
        .map((child) => {
          const childRect = child.getBoundingClientRect();
          return {
            className: child.className || '',
            id: child.id || '',
            left: Math.floor(childRect.left),
            right: Math.ceil(childRect.right),
          };
        })
        .filter(child => child.left < rect.left - 1 || child.right > rect.right + 1)
        .slice(0, 10),
      internallyOverflowingElements: visibleChildren
        .map(child => ({
          className: child.className || '',
          id: child.id || '',
          clientWidth: child.clientWidth,
          scrollWidth: child.scrollWidth,
          overflowPixels: Math.max(0, child.scrollWidth - child.clientWidth),
        }))
        .filter(child => child.overflowPixels > 0)
        .sort((a, b) => b.overflowPixels - a.overflowPixels)
        .slice(0, 12),
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
    schema: 'munea.app-medication-local-browser-precheck.v1',
    recordedAt: new Date().toISOString(),
    result: 'pending',
    releaseEvidence: false,
    sourceBaseCommit: sourceCommit(),
    sourceChangedFiles: sourceChangedFiles(),
    scope: {
      surfaces: [
        'modal:medication-manager/list',
        'modal:medication-manager/form',
        'modal:medication-reminder',
        'medication-reminder/spoken-copy',
      ],
      environment: 'local-fixture-only',
      baseUrl: `http://${HOST}:${PORT}`,
      productionTouched: false,
      stagingTouched: false,
      gatewayTouched: false,
      voiceTouched: false,
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
    locales: {},
    limitations: [
      'This is a local browser precheck, not exact installed-iPhone visual QA.',
      'Spoken reminder copy was evaluated as text only; no production Voice or audio synthesis was called.',
      'No production, staging, Gateway, Voice, Avatar, Supabase, StoreKit, or App Store Connect service was exercised.',
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
          && window.__medicationI18nTest
          && typeof window.__medicationI18nTest.showManager === 'function'
          && typeof window.__medicationI18nTest.showReminder === 'function'
          && typeof window.__medicationI18nTest.reminderSpeech === 'function'
          && typeof window.__medicationI18nTest.canonicalSlot === 'function'
          && typeof window.__medicationI18nTest.canonicalDuration === 'function'
        ),
        expected,
      );

      const voiceStorageContract = await page.evaluate(() => ({
        slots: [
          'after-breakfast',
          'After breakfast',
          '朝食後',
          'Después del desayuno',
        ].map(value => window.__medicationI18nTest.canonicalSlot(value)),
        oneDay: ['一次', 'once', '1回', 'una vez']
          .map(value => window.__medicationI18nTest.canonicalDuration(value)),
      }));
      if (
        voiceStorageContract.slots.some(value => value !== '早餐後')
        || voiceStorageContract.oneDay.some(value => value !== '1 天')
      ) {
        throw new Error(
          `${expected.locale} medication voice storage contract failed: `
          + JSON.stringify(voiceStorageContract),
        );
      }

      await page.evaluate(({ medicationName }) => {
        window.__medicationI18nTest.showManager({
          name: medicationName,
          time: '早餐後',
          days: '長期',
          photo: '',
        });
      }, expected);
      const managerModal = page.locator('#medMgrModal .modal');
      await managerModal.waitFor({ state: 'visible' });
      await managerModal.evaluate(element => { element.scrollTop = 0; });
      const managerText = await managerModal.innerText();
      const managerExpected = [
        copy['medication.title'],
        copy['medicationManager.subtitle'],
        copy['medicationManager.disclaimer'],
        copy['medicationManager.addMedicine'],
        copy['medicationManager.scheduleMultiple'],
        copy['medicationManager.duration'],
        copy['medicationManager.add'],
        copy['medication.slot.afterBreakfast'],
        copy['medication.slot.afterLunch'],
        copy['medication.slot.afterDinner'],
        copy['medication.slot.bedtime'],
        copy['medication.duration.longTerm'],
        copy['medicationManager.emptySlot'],
        expected.medicationName,
      ];
      const missingManagerCopy = managerExpected.filter(value => !managerText.includes(value));
      const untranslatedManagerCopy = unexpectedSourceCopy(
        expected.locale,
        expected.sourceOnly,
        managerText,
      );
      const managerLayout = await layoutFor(managerModal);
      const managerTopPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__medication-manager-list__iphone390x844.png`,
      );
      await page.screenshot({ path: managerTopPath, fullPage: false });

      await managerModal.evaluate(element => {
        element.scrollTop = element.scrollHeight;
      });
      await page.waitForTimeout(120);
      const managerFormPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__medication-manager-form__iphone390x844.png`,
      );
      await page.screenshot({ path: managerFormPath, fullPage: false });
      const formLabels = await page.evaluate(() => ({
        namePlaceholder: document.getElementById('medName')?.placeholder || '',
        photo: document.getElementById('medPhotoBtn')?.textContent.trim() || '',
        photoHint: document.querySelector('#medMgrModal .med-photo-hint')?.textContent.trim() || '',
        add: document.getElementById('medAddBtn')?.textContent.trim() || '',
        closeLabel: document.getElementById('medMgrClose')?.getAttribute('aria-label') || '',
        slots: [...document.querySelectorAll('#medTimeChips .mchip')]
          .map(element => element.textContent.trim()),
        durations: [...document.querySelectorAll('#medDayChips .mchip')]
          .map(element => element.textContent.trim()),
        timeDisplays: [...document.querySelectorAll('#medSlots .ms-time-display')]
          .map(element => element.textContent.trim()),
        timeInputLabels: [...document.querySelectorAll('#medSlots input.ms-time')]
          .map(element => element.getAttribute('aria-label') || ''),
      }));
      const invalidTimeDisplays = formLabels.timeDisplays.filter(
        value => !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value),
      );
      const invalidTimeLabels = formLabels.timeInputLabels.filter(
        value => value !== copy['medicationManager.reminderTime'],
      );
      const systemLocaleTimeFragments = (
        managerText.match(/(?:上午|下午|\bAM\b|\bPM\b)/g) || []
      );

      await page.evaluate(({ medicationName }) => {
        document.getElementById('medMgrModal')?.classList.remove('show');
        window.__medicationI18nTest.showReminder({
          name: medicationName,
          time: '早餐後',
        });
      }, expected);
      const reminderModal = page.locator('#medRemindModal .modal');
      await reminderModal.waitFor({ state: 'visible' });
      const reminderValues = await page.evaluate((medicationName) => ({
        dueSay: document.getElementById('medDueSay')?.textContent.trim() || '',
        name: document.getElementById('medDueName')?.textContent.trim() || '',
        description: document.getElementById('medDueDesc')?.textContent.trim() || '',
        streak: document.querySelector('#medRemindModal .mpc-streak')?.textContent.trim() || '',
        taken: document.getElementById('medTaken')?.textContent.trim() || '',
        snooze: document.getElementById('medSnooze')?.textContent.trim() || '',
        closeLabel: document.querySelector('#medRemindModal .mx-close')?.getAttribute('aria-label') || '',
        speech: window.__medicationI18nTest.reminderSpeech({
          name: medicationName,
          time: '早餐後',
        }),
      }), expected.medicationName);
      const reminderText = await reminderModal.innerText();
      const untranslatedReminderCopy = unexpectedSourceCopy(
        expected.locale,
        expected.sourceOnly,
        reminderText,
      );
      const reminderLayout = await layoutFor(reminderModal);
      const reminderPath = path.join(
        OUTPUT_DIR,
        `${expected.locale}__medication-reminder__iphone390x844.png`,
      );
      await page.screenshot({ path: reminderPath, fullPage: false });

      const slot = copy['medication.slot.afterBreakfast'];
      const formattedSix = new Intl.NumberFormat(expected.locale).format(6);
      const formattedTen = new Intl.NumberFormat(expected.locale).format(10);
      const expectedReminder = {
        dueSay: format(copy['medicationReminder.dueSay'], { slot }),
        name: expected.medicationName,
        description: format(copy['medicationReminder.description'], { slot }),
        streak: format(copy['medicationReminder.streak'], { days: formattedSix }),
        taken: copy['medicationReminder.taken'],
        snooze: format(copy['medicationReminder.snooze'], { minutes: formattedTen }),
        closeLabel: copy['common.close'],
        speech: format(copy['medicationReminder.speech'], {
          name: expected.medicationName,
          slot,
        }),
      };
      const reminderMismatch = Object.entries(expectedReminder)
        .filter(([key, value]) => reminderValues[key] !== value)
        .map(([key, value]) => ({ key, expected: value, observed: reminderValues[key] }));

      if (
        missingManagerCopy.length
        || untranslatedManagerCopy.length
        || untranslatedReminderCopy.length
        || reminderMismatch.length
        || invalidTimeDisplays.length
        || invalidTimeLabels.length
        || systemLocaleTimeFragments.length
        || managerLayout.horizontalOverflowPixels > 0
        || reminderLayout.horizontalOverflowPixels > 0
        || managerLayout.overflowingChildren.length
        || reminderLayout.overflowingChildren.length
        || browserErrors.length
      ) {
        throw new Error(
          `${expected.locale} medication precheck failed: `
          + JSON.stringify({
            missingManagerCopy,
            untranslatedManagerCopy,
            untranslatedReminderCopy,
            reminderMismatch,
            invalidTimeDisplays,
            invalidTimeLabels,
            systemLocaleTimeFragments,
            managerLayout,
            reminderLayout,
            browserErrors,
          }),
        );
      }

      report.locales[expected.locale] = {
        htmlLang: expected.htmlLang,
        medicationName: expected.medicationName,
        manager: {
          missingCopy: missingManagerCopy,
          untranslatedCopy: untranslatedManagerCopy,
          layout: managerLayout,
          formLabels,
          invalidTimeDisplays,
          invalidTimeLabels,
          systemLocaleTimeFragments,
          screenshots: {
            list: screenshotEvidence(managerTopPath),
            form: screenshotEvidence(managerFormPath),
          },
        },
        reminder: {
          values: reminderValues,
          expected: expectedReminder,
          mismatches: reminderMismatch,
          untranslatedCopy: untranslatedReminderCopy,
          layout: reminderLayout,
          screenshot: screenshotEvidence(reminderPath),
        },
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
      path.join(OUTPUT_DIR, 'medication-local-browser-precheck.json'),
      `${JSON.stringify(report, null, 2)}\n`,
      'utf8',
    );
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }

  process.stdout.write(
    `Medication i18n local browser precheck PASS: ${LOCALES.length} locales, `
    + `${LOCALES.length * 3} screenshots, localized visible and spoken reminders\n`,
  );
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
