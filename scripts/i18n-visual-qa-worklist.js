'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { buildLayoutRiskWorklist } = require('./i18n-layout-risk-worklist.js');

const ROOT = path.resolve(__dirname, '..');
const LOCALES = Object.freeze(['zh-TW', 'en', 'ja', 'es']);

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, relativePath), 'utf8'));
}

function stateSlug(state) {
  const slug = String(state || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  if (!slug) throw new Error(`Invalid visual QA state: ${state}`);
  return slug;
}

function layoutRiskByLocaleAndState() {
  const riskWorklist = buildLayoutRiskWorklist();
  const index = new Map();
  for (const entry of riskWorklist.entries) {
    for (const state of entry.states) {
      const id = `${entry.locale}:${state}`;
      if (!index.has(id)) index.set(id, []);
      index.get(id).push(entry);
    }
  }
  const result = new Map();
  for (const [id, entries] of index) {
    entries.sort((left, right) => right.score - left.score || left.key.localeCompare(right.key));
    const maxScore = entries[0]?.score || 0;
    result.set(id, {
      maxScore,
      severity: maxScore >= 45 ? 'high' : maxScore >= 25 ? 'medium' : 'low',
      highRiskKeyCount: entries.filter(({ severity }) => severity === 'high').length,
      mediumRiskKeyCount: entries.filter(({ severity }) => severity === 'medium').length,
      topRiskKeys: entries.slice(0, 5).map(({ key, score }) => ({ key, score })),
    });
  }
  return result;
}

function buildVisualQaWorklist(localeFilter) {
  const manifest = readJson('web/src/i18n/app-surface-manifest.json');
  const layoutRisks = layoutRiskByLocaleAndState();
  const locales = localeFilter ? [localeFilter] : [...LOCALES];
  for (const locale of locales) {
    if (!LOCALES.includes(locale)) throw new Error(`Unsupported visual QA locale: ${locale}`);
  }

  const slugs = manifest.surfaces.map(({ state }) => stateSlug(state));
  if (new Set(slugs).size !== slugs.length) {
    throw new Error('Visual QA state slugs must be unique');
  }

  const entries = [];
  for (const locale of locales) {
    for (const surface of manifest.surfaces) {
      const slug = stateSlug(surface.state);
      for (const profile of manifest.captureProfiles) {
        const screenshot = `visual/${slug}__${profile}.png`;
        entries.push({
          sequence: entries.length + 1,
          locale,
          state: surface.state,
          profile,
          captureMode: surface.captureMode,
          source: surface.source,
          anchorId: surface.anchorId,
          captureSource: 'exact-installed-iphone-app',
          staticRisk: layoutRisks.get(`${locale}:${surface.state}`),
          screenshot,
          workspacePath: `docs/qa/i18n/${locale}/${screenshot}`,
          result: 'pending',
          checks: {
            noOverflow: 'pending',
            noClipping: 'pending',
            noUntranslatedCopy: 'pending',
            layoutAccepted: 'pending',
          },
        });
      }
    }
  }

  return {
    schema: 'munea.i18n-visual-qa-worklist.v2',
    generatedFrom: [
      'web/src/i18n/app-surface-manifest.json',
      'scripts/i18n-layout-risk-worklist.js',
    ],
    locales,
    buildIdentity: {
      captureCommit: null,
      binarySha256: null,
      binaryBytes: null,
      appVersion: null,
      build: null,
    },
    approvalPolicy: {
      automaticPassForbidden: true,
      currentRunScreenshotsOnly: true,
      exactInstalledAppRequired: true,
      manualVisualReviewRequired: true,
      staticRiskCannotPassVisualQa: true,
    },
    entryCount: entries.length,
    entries,
  };
}

if (require.main === module) {
  const localeIndex = process.argv.indexOf('--locale');
  const locale = localeIndex >= 0 ? process.argv[localeIndex + 1] : null;
  process.stdout.write(`${JSON.stringify(buildVisualQaWorklist(locale), null, 2)}\n`);
}

module.exports = {
  LOCALES,
  buildVisualQaWorklist,
  layoutRiskByLocaleAndState,
  stateSlug,
};
