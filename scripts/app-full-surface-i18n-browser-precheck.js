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
const PORT = 4189;
const LOCALES = Object.freeze([
  Object.freeze({ locale: 'zh-TW', htmlLang: 'zh-Hant-TW' }),
  Object.freeze({ locale: 'en', htmlLang: 'en' }),
  Object.freeze({ locale: 'ja', htmlLang: 'ja' }),
  Object.freeze({ locale: 'es', htmlLang: 'es' }),
]);
const CAPTURE_PROFILES = Object.freeze([
  Object.freeze({
    id: 'iphone-small-standard',
    viewport: Object.freeze({ width: 375, height: 667 }),
    appFontScale: 'std',
    fileSuffix: 'iphone375x667',
    emulation: 'Chrome viewport at 375x667 CSS pixels with the App standard font setting',
  }),
  Object.freeze({
    id: 'iphone-standard',
    viewport: Object.freeze({ width: 390, height: 844 }),
    appFontScale: 'std',
    fileSuffix: 'iphone390x844',
    emulation: 'Chrome viewport at 390x844 CSS pixels with the App standard font setting',
  }),
  Object.freeze({
    id: 'iphone-dynamic-type-large',
    viewport: Object.freeze({ width: 390, height: 844 }),
    appFontScale: 'xl',
    fileSuffix: 'iphone390x844-app-xl',
    emulation: 'Chrome viewport at 390x844 CSS pixels with the App extra-large font setting (1.14 zoom)',
  }),
]);
const OUTPUT_DIR = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'full-surface-all-profiles-2026-07-29',
);
const REPORT_PATH = path.join(OUTPUT_DIR, 'full-surface-all-profiles-local-browser-precheck.json');
const SURFACE_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'web', 'src', 'i18n', 'app-surface-manifest.json'), 'utf8'),
);
const manifestProfiles = SURFACE_MANIFEST.captureProfiles;
if (
  !Array.isArray(manifestProfiles)
  || manifestProfiles.join('\n') !== CAPTURE_PROFILES.map(({ id }) => id).join('\n')
) {
  throw new Error('Browser precheck profiles must match app-surface-manifest.json');
}

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

function sha256(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function screenshotEvidence(filePath) {
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

function sourceLanguageSamples(locale, text, leafTexts, zhCatalog) {
  if (locale === 'zh-TW') return [];
  if (locale === 'en' || locale === 'es') {
    return [...new Set(text.match(/[\u3400-\u9fff\uf900-\ufaff]+/gu) || [])].slice(0, 30);
  }
  const candidates = Object.values(zhCatalog)
    .filter((value) => (
      typeof value === 'string'
      && value.length >= 4
      && value.length <= 80
      && /[\u3400-\u9fff]/u.test(value)
      && !/[ぁ-んァ-ヶ]/u.test(value)
    ));
  const sourceOnlyLeaves = leafTexts.filter((value) => (
    /[\u3400-\u9fff]/u.test(value)
    && !/[ぁ-んァ-ヶ]/u.test(value)
  ));
  return [...new Set(candidates.filter((value) => (
    sourceOnlyLeaves.some((leaf) => leaf.includes(value))
  )))].slice(0, 30);
}

function fallbackLanguageSamples(locale, visibleTexts, catalogs) {
  if (locale === 'zh-TW' || locale === 'en') return [];
  const sourceCatalog = catalogs.en;
  const targetCatalog = catalogs[locale];
  const candidates = [];
  for (const [key, sourceTemplate] of Object.entries(sourceCatalog)) {
    const targetTemplate = targetCatalog[key];
    if (
      typeof sourceTemplate !== 'string'
      || typeof targetTemplate !== 'string'
      || sourceTemplate === targetTemplate
      || sourceTemplate.length < 4
      || !/[A-Za-z]{3}/u.test(sourceTemplate)
    ) continue;
    const sourceWords = sourceTemplate.toLocaleLowerCase('en')
      .match(/[a-z]{3,}/gu) || [];
    const targetWords = new Set(
      targetTemplate.toLocaleLowerCase('en').match(/[a-z]{3,}/gu) || [],
    );
    if (sourceWords.length && sourceWords.every((word) => targetWords.has(word))) continue;
    const parts = sourceTemplate.split(/\{[A-Za-z][A-Za-z0-9_]*\}/u);
    const pattern = parts
      .map((part) => part
        .replace(/[.*+?^${}()|[\]\\]/gu, '\\$&')
        .replace(/\s+/gu, '\\s+'))
      .join('.+?');
    const matcher = new RegExp(`^\\s*${pattern}\\s*$`, 'u');
    if (visibleTexts.some((value) => matcher.test(value))) {
      candidates.push(sourceTemplate);
    }
  }
  return [...new Set(candidates)].slice(0, 30);
}

function safeFilePart(value) {
  return value.replaceAll(':', '-').replaceAll('/', '-');
}

async function resetAndPrepareState(page, state) {
  await page.evaluate(async (requestedState) => {
    const $ = selector => document.querySelector(selector);
    const t = (key, fallback, values) => (
      window.MuneaI18n && typeof window.MuneaI18n.t === 'function'
        ? window.MuneaI18n.t(key, values, fallback)
        : fallback
    );
    const setScreen = (id) => {
      document.querySelectorAll('.screen').forEach((screen) => {
        screen.classList.toggle('active', screen.id === id);
        screen.scrollTop = 0;
      });
      document.querySelectorAll('.tab-btn').forEach((button) => {
        button.classList.toggle('active', button.dataset.view === id);
      });
      const tabBar = $('#tabBar');
      if (tabBar) tabBar.classList.toggle('hidden', id === 'connect');
    };
    const showModal = (id) => {
      const modal = document.getElementById(id);
      if (!modal) throw new Error(`Missing modal ${id}`);
      modal.classList.add('show');
      modal.setAttribute('aria-hidden', 'false');
      modal.scrollTop = 0;
      const body = modal.querySelector('.modal');
      if (body) body.scrollTop = 0;
      return modal;
    };

    document.querySelectorAll('.modal-mask.show').forEach((modal) => {
      modal.classList.remove('show');
      modal.setAttribute('aria-hidden', 'true');
    });
    document.querySelectorAll('.reader-page.show').forEach((reader) => {
      reader.classList.remove('show');
      reader.setAttribute('aria-hidden', 'true');
    });
    const toast = $('#toast');
    if (toast) toast.classList.remove('show');
    const busy = $('#busyCard');
    if (busy) busy.hidden = true;
    const textPanel = $('#textChatPanel');
    if (textPanel) textPanel.hidden = true;

    if (requestedState.startsWith('screen:')) {
      setScreen(requestedState.slice('screen:'.length));
      return;
    }

    if (requestedState.startsWith('chat:')) {
      if (!window.__ptsTest || typeof window.__ptsTest.showIdleChat !== 'function') {
        throw new Error('Chat visual test hook is unavailable');
      }
      window.__ptsTest.showIdleChat();
      const chat = $('#chat');
      const caption = $('#chatCaption');
      const callLabel = $('#callToggleLabel');
      const chatState = requestedState.slice('chat:'.length);
      chat.dataset.state = chatState === 'active' ? 'speaking' : chatState;
      if (chatState === 'connecting') {
        busy.hidden = false;
        $('#busyCardTitle').textContent = t(
          'voice.queue.preparingWithCompanion',
          'Preparing your call…',
          { companion: t('companion.defaultName', 'Munea') },
        );
        $('#busyCardPos').textContent = t('voice.queue.pending', 'Connecting…');
        $('#busyCardNote').textContent = t(
          'voice.queue.etaPreparingSoon',
          'This usually takes a moment.',
        );
        $('#busyCardBtn').textContent = t('voice.queue.cancel', 'Cancel');
      } else if (chatState === 'queued') {
        window.__ptsTest.showQueued();
      } else if (chatState === 'active') {
        caption.textContent = t('voice.runtime.listening', 'Listening');
        callLabel.textContent = t('voice.call.end', 'End call');
      } else if (chatState === 'text-fallback') {
        textPanel.hidden = false;
        const input = $('#textChatInput');
        input.placeholder = t('textChat.placeholder', 'Type what you would like to say');
        input.setAttribute('aria-label', input.placeholder);
        $('#textChatSend').textContent = t('textChat.send', 'Send');
        caption.textContent = t('textChat.title', 'Continue by text');
      } else if (chatState === 'error') {
        busy.hidden = false;
        $('#busyCardTitle').textContent = t('voice.call.unavailable', 'Calling is unavailable');
        $('#busyCardPos').textContent = '';
        $('#busyCardNote').textContent = t(
          'voice.call.retryLater',
          'Please try again in a moment.',
        );
        $('#busyCardBtn').textContent = t('common.retry', 'Retry');
      }
      return;
    }

    if (requestedState === 'cross-surface:error-and-empty') {
      setScreen('home');
      toast.textContent = t('error.generic', 'Something went wrong. Please try again.');
      toast.classList.add('show');
      return;
    }

    const modalIds = {
      'modal:quiz': 'quizModal',
      'modal:challenge': 'chalModal',
      'modal:activity-detail': 'actDetailModal',
      'modal:feedback': 'feedbackModal',
      'modal:interests': 'interestsModal',
      'modal:safety': 'safetyModal',
      'modal:companion': 'companionSheet',
      'modal:report': 'reportModal',
      'modal:font': 'fontModal',
      'modal:data': 'dataModal',
      'modal:profile': 'profileModal',
      'modal:family-circle': 'famCircleModal',
      'modal:invite-family': 'inviteFamModal',
      'modal:join-circle': 'joinCircleModal',
      'modal:top-up': 'topUpModal',
      'modal:appointment': 'visitModal',
      'modal:history': 'historyModal',
      'modal:consent': 'consentSheet',
      'modal:version': 'versionSheet',
      'modal:medication-reminder': 'medRemindModal',
      'modal:medication-manager': 'medMgrModal',
      'modal:auth': 'authSheet',
    };
    if (modalIds[requestedState]) {
      setScreen(requestedState === 'modal:report' ? 'status' : 'settings');
      if (requestedState === 'modal:activity-detail') {
        const body = $('#actDetailBody');
        body.replaceChildren();
        const title = document.createElement('h2');
        title.textContent = t('activity.detailTitle', 'Activity details');
        const participants = document.createElement('p');
        participants.className = 'modal-sub';
        participants.textContent = t('activity.noParticipants', 'No participants yet');
        const location = document.createElement('p');
        location.textContent = t('activity.location', 'Location');
        body.append(title, participants, location);
      }
      if (requestedState === 'modal:quiz') {
        $('#quizQ').textContent = t('quiz.question', 'Question');
        $('#quizProgress').textContent = t('quiz.progress', 'Question {current} of {total}', {
          current: 1,
          total: 5,
        });
      }
      if (requestedState === 'modal:version' && $('#versionRow')) {
        $('#versionRow').click();
      } else if (
        requestedState === 'modal:medication-reminder'
        && window.__muneaMedicationTest
        && typeof window.__muneaMedicationTest.showReminder === 'function'
      ) {
        window.__muneaMedicationTest.showReminder({
          name: t('medication.exampleName', 'Medication'),
          time: '08:00',
          slot: 'breakfast',
          streak: 6,
        });
        const medicationName = $('#medDueName');
        if (medicationName) {
          medicationName.textContent = t('medication.genericName', 'Medication');
        }
      } else {
        showModal(modalIds[requestedState]);
      }
      return;
    }

    if (requestedState === 'reader:subscription') {
      setScreen('settings');
      const reader = $('#planModal');
      reader.classList.add('show');
      reader.setAttribute('aria-hidden', 'false');
      reader.scrollTop = 0;
      return;
    }

    if (requestedState === 'reader:legal') {
      setScreen('settings');
      $('#privacyPolicyRow').click();
      return;
    }

    if (requestedState === 'page:notification-settings') {
      setScreen('settings');
      $('#notificationCenterRow').click();
      return;
    }

    if (requestedState === 'modal:notification-inbox') {
      setScreen('settings');
      await window.MuneaNotify.openInbox();
      return;
    }

    throw new Error(`No local visual-state preparer for ${requestedState}`);
  }, state);

  if (state === 'reader:legal') {
    await page.locator('#readerPage.show').waitFor();
    await page.waitForFunction(() => {
      const body = document.getElementById('readerBody');
      return body && body.innerText.trim().length > 100;
    });
  } else if (state === 'page:notification-settings') {
    await page.locator('#notificationSettingsPage.show').waitFor();
  } else if (state === 'modal:notification-inbox') {
    await page.locator('#notificationInboxModal.show').waitFor();
  }
  await page.waitForTimeout(80);
}

async function stateMetrics(page, surface, locale, catalogs) {
  const anchorSelector = `#${surface.anchorId}`;
  const metrics = await page.locator(anchorSelector).evaluate((element, state) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    const visibleText = element.innerText.trim();
    const viewportHeight = document.documentElement.clientHeight;
    const viewportWidth = document.documentElement.clientWidth;
    const isUserContent = (child) => (
      (state === 'screen:home' && child.closest('#careCard, #bcMsg'))
      || (state === 'modal:medication-reminder' && child.closest('#medDueName'))
      || (
        state === 'screen:family'
        && child.closest(
          '#famSwitch .fam-switch-item:not([data-person="all"]):not([data-person="invite"]), '
          + '#healthList .hr-name, #healthList .init-ava, #viewAll .quest-card, '
          + '.person-top .pt-name, .mc-obs',
        )
      )
      || child.closest('.auth-email')
      || (
        state === 'modal:family-circle'
        && child.closest('#fcRoster .rl > b, #fcRoster .init-ava')
      )
    );
    const visibleViewportLeafTexts = [...element.querySelectorAll('*')]
      .filter((child) => {
        const childStyle = getComputedStyle(child);
        if (
          childStyle.display === 'none'
          || childStyle.visibility === 'hidden'
          || Number(childStyle.opacity) === 0
        ) return false;
        const box = child.getBoundingClientRect();
        if (isUserContent(child)) return false;
        return (
          box.width > 0
          && box.height > 0
          && box.right > 0
          && box.left < viewportWidth
          && box.bottom > 0
          && box.top < viewportHeight
          && child.children.length === 0
        );
      })
      .map((child) => child.innerText || child.textContent || '')
      .map((text) => text.trim())
      .filter(Boolean);
    const visibleViewportTextNodes = [];
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let textNode = walker.nextNode();
    while (textNode) {
      const parent = textNode.parentElement;
      const text = textNode.textContent.trim();
      if (parent && text && !isUserContent(parent)) {
        const parentStyle = getComputedStyle(parent);
        const range = document.createRange();
        range.selectNodeContents(textNode);
        const box = range.getBoundingClientRect();
        if (
          parentStyle.display !== 'none'
          && parentStyle.visibility !== 'hidden'
          && Number(parentStyle.opacity) !== 0
          && box.width > 0
          && box.height > 0
          && box.right > 0
          && box.left < viewportWidth
          && box.bottom > 0
          && box.top < viewportHeight
        ) visibleViewportTextNodes.push(text);
      }
      textNode = walker.nextNode();
    }
    const visibleViewportText = visibleViewportTextNodes
      .join('\n')
      .trim();
    const visibleAttributeTexts = [...element.querySelectorAll('[placeholder], [aria-label], [title]')]
      .filter((child) => {
        if (isUserContent(child)) return false;
        const childStyle = getComputedStyle(child);
        const box = child.getBoundingClientRect();
        return (
          childStyle.display !== 'none'
          && childStyle.visibility !== 'hidden'
          && Number(childStyle.opacity) !== 0
          && box.width > 0
          && box.height > 0
          && box.right > 0
          && box.left < viewportWidth
          && box.bottom > 0
          && box.top < viewportHeight
        );
      })
      .flatMap((child) => ['placeholder', 'aria-label', 'title']
        .map((attribute) => child.getAttribute(attribute))
        .filter(Boolean));
    const overflowingChildren = [...element.querySelectorAll('*')]
      .filter((child) => {
        const childStyle = getComputedStyle(child);
        if (childStyle.display === 'none' || childStyle.visibility === 'hidden') return false;
        if (child.closest('.hscroll-wrap')) return false;
        const box = child.getBoundingClientRect();
        return (
          box.width > 0
          && box.bottom > 0
          && box.top < viewportHeight
          && (box.left < -2 || box.right > viewportWidth + 2)
        );
      })
      .slice(0, 12)
      .map((child) => ({
        tag: child.tagName.toLowerCase(),
        id: child.id || '',
        className: typeof child.className === 'string' ? child.className.slice(0, 100) : '',
        left: Math.round(child.getBoundingClientRect().left),
        right: Math.round(child.getBoundingClientRect().right),
      }));
    const truncatedTextElements = [...element.querySelectorAll('*')]
      .filter((child) => {
        if (isUserContent(child)) return false;
        const childStyle = getComputedStyle(child);
        if (
          childStyle.display === 'none'
          || childStyle.visibility === 'hidden'
          || childStyle.textOverflow !== 'ellipsis'
        ) return false;
        const box = child.getBoundingClientRect();
        return (
          box.width > 0
          && box.bottom > 0
          && box.top < viewportHeight
          && child.scrollWidth > child.clientWidth + 1
        );
      })
      .slice(0, 12)
      .map((child) => ({
        tag: child.tagName.toLowerCase(),
        id: child.id || '',
        className: typeof child.className === 'string' ? child.className.slice(0, 100) : '',
        text: (child.innerText || child.textContent || '').trim().slice(0, 160),
        clientWidth: Math.round(child.clientWidth),
        scrollWidth: Math.round(child.scrollWidth),
      }));
    return {
      display: style.display,
      visibility: style.visibility,
      rect: {
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        top: Math.round(rect.top),
        bottom: Math.round(rect.bottom),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      visibleText,
      visibleViewportText,
      visibleViewportLeafTexts,
      visibleViewportTextNodes,
      visibleAttributeTexts,
      visibleCharacters: visibleText.length,
      horizontalOverflowPixels: Math.max(
        0,
        Math.ceil(element.scrollWidth - element.clientWidth),
      ),
      overflowingChildren,
      truncatedTextElements,
      documentHorizontalOverflowPixels: Math.max(
        0,
        Math.ceil(document.documentElement.scrollWidth - document.documentElement.clientWidth),
      ),
    };
  }, surface.state);
  const sourceLeaks = sourceLanguageSamples(
    locale,
    `${metrics.visibleViewportText}\n${metrics.visibleAttributeTexts.join('\n')}`,
    [...metrics.visibleViewportTextNodes, ...metrics.visibleAttributeTexts],
    catalogs['zh-TW'],
  );
  const fallbackLeaks = fallbackLanguageSamples(
    locale,
    [...metrics.visibleViewportTextNodes, ...metrics.visibleAttributeTexts],
    catalogs,
  );
  const languageLeaks = [...new Set([...sourceLeaks, ...fallbackLeaks])];
  return {
    ...metrics,
    sourceLanguageSamples: languageLeaks,
    translationResult: languageLeaks.length ? 'fail-source-or-fallback-language-visible' : 'pass',
    layoutResult: (
      metrics.horizontalOverflowPixels === 0
      && metrics.documentHorizontalOverflowPixels === 0
      && metrics.overflowingChildren.length === 0
      && metrics.truncatedTextElements.length === 0
    ) ? 'pass' : 'fail-overflow-or-truncated-text',
    visibilityResult: (
      metrics.display !== 'none'
      && metrics.visibility !== 'hidden'
      && metrics.rect.width > 0
      && metrics.rect.height > 0
      && metrics.visibleCharacters > 0
    ) ? 'pass' : 'fail-not-visible-or-empty',
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
    schema: 'munea.app-full-surface-local-browser-precheck.v2',
    recordedAt: new Date().toISOString(),
    result: 'pending',
    releaseEvidence: false,
    sourceBaseCommit: sourceCommit(),
    sourceChangedFiles: sourceChangedFiles(),
    scope: {
      states: SURFACE_MANIFEST.surfaces.map(({ state }) => state),
      locales: LOCALES.map(({ locale }) => locale),
      captureProfiles: CAPTURE_PROFILES.map(({ id, viewport, appFontScale, emulation }) => ({
        id,
        viewport,
        appFontScale,
        emulation,
      })),
      expectedScreenshots: (
        SURFACE_MANIFEST.surfaces.length * LOCALES.length * CAPTURE_PROFILES.length
      ),
      environment: 'local-fixture-only',
      baseUrl: `http://${HOST}:${PORT}`,
      productionTouched: false,
      stagingTouched: false,
      appStoreConnectTouched: false,
      storeKitTouched: false,
      gatewayTouched: false,
      voiceTouched: false,
      avatarTouched: false,
      supabaseTouched: false,
      installedAppUsed: false,
    },
    runtime: {
      browser: 'Google Chrome',
      profiles: CAPTURE_PROFILES,
      fixtureServer: 'scripts/app-i18n-fixture-server.js',
      automation: 'Playwright bulk capture after an agent-browser loopback smoke check',
    },
    networkSafety: {
      loopbackBindOnly: true,
      allowedBrowserDomain: HOST,
      observedExternalRequests: [],
    },
    screens: [],
    failures: [],
    limitations: [
      'This is a 38-state x 4-locale x 3-profile local browser precheck, not exact installed-iPhone release evidence.',
      'The iphone-dynamic-type-large browser profile uses the App extra-large font setting; it does not certify native iOS Dynamic Type behavior.',
      'Native iOS controls, safe-area behavior, font rendering, and physical-device interaction remain part of the exact-build installed-iPhone 456-screenshot release gate.',
      'No production, staging, StoreKit, Gateway, Voice, Avatar, Supabase, or App Store Connect service was exercised.',
    ],
  };
  const catalogs = Object.fromEntries(
    LOCALES.map(({ locale }) => [locale, catalog(locale)]),
  );

  try {
    for (const profile of CAPTURE_PROFILES) {
      for (const expected of LOCALES) {
        const context = await browser.newContext({
          locale: expected.htmlLang,
          viewport: profile.viewport,
        });
        await context.addInitScript((fontScale) => {
          localStorage.setItem('munea.fontScale', fontScale);
        }, profile.appFontScale);
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
          ({ locale, htmlLang, appFontScale }) => (
            window.MuneaI18n
            && window.MuneaI18n.initialized
            && window.MuneaI18n.current() === locale
            && document.documentElement.lang === htmlLang
            && localStorage.getItem('munea.fontScale') === appFontScale
          ),
          { ...expected, appFontScale: profile.appFontScale },
        );

        for (const surface of SURFACE_MANIFEST.surfaces) {
          await resetAndPrepareState(page, surface.state);
          const metrics = await stateMetrics(page, surface, expected.locale, catalogs);
          const screenshotPath = path.join(
            OUTPUT_DIR,
            `${expected.locale}__${safeFilePart(surface.state)}__${profile.fileSuffix}.png`,
          );
          await page.screenshot({ path: screenshotPath, fullPage: false });
          const record = {
            profile: profile.id,
            viewport: profile.viewport,
            appFontScale: profile.appFontScale,
            locale: expected.locale,
            htmlLang: expected.htmlLang,
            state: surface.state,
            anchorId: surface.anchorId,
            ...metrics,
            browserErrors: [...browserErrors],
            screenshot: screenshotEvidence(screenshotPath),
          };
          report.screens.push(record);
          const failedChecks = [
            record.translationResult,
            record.layoutResult,
            record.visibilityResult,
            ...(record.browserErrors.length ? ['fail-browser-errors'] : []),
          ].filter((result) => result !== 'pass');
          if (failedChecks.length) {
            report.failures.push({
              profile: profile.id,
              locale: expected.locale,
              state: surface.state,
              failedChecks,
              sourceLanguageSamples: record.sourceLanguageSamples,
              overflowingChildren: record.overflowingChildren,
              truncatedTextElements: record.truncatedTextElements,
              browserErrors: record.browserErrors,
            });
          }
          browserErrors.length = 0;
        }
        await context.close();
      }
    }
    report.networkSafety.observedExternalRequests = [
      ...new Set(report.networkSafety.observedExternalRequests),
    ];
    if (report.networkSafety.observedExternalRequests.length) {
      report.failures.push({
        state: 'network-safety',
        failedChecks: ['fail-external-browser-request'],
        hosts: report.networkSafety.observedExternalRequests,
      });
    }
    report.result = report.failures.length ? 'fail-local-precheck' : 'pass-local-precheck';
    report.completedAt = new Date().toISOString();
    fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  if (report.result !== 'pass-local-precheck') {
    throw new Error(
      `Full-surface i18n local precheck found ${report.failures.length} failure(s). `
      + `See ${path.relative(ROOT, REPORT_PATH)}.`,
    );
  }
  process.stdout.write(
    `Full-surface App i18n local precheck PASS: ${report.screens.length} screenshots.\n`,
  );
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
