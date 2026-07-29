'use strict';

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const LOCALES = Object.freeze(['zh-TW', 'en', 'ja', 'es']);
const CRITICAL_STATES = new Set([
  'screen:connect',
  'chat:error',
  'modal:safety',
  'modal:data',
  'reader:subscription',
  'modal:consent',
  'modal:medication-manager',
  'modal:auth',
  'page:notification-settings',
]);

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, relativePath), 'utf8'));
}

function graphemes(value) {
  return [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(value)]
    .map(({ segment }) => segment);
}

function estimatedWidthEm(value) {
  const placeholderPattern = /\{[A-Za-z][A-Za-z0-9_]*\}/g;
  const withoutPlaceholders = String(value).replace(placeholderPattern, '00000000');
  return Number(graphemes(withoutPlaceholders).reduce((width, character) => {
    if (/\s/u.test(character)) return width + 0.35;
    if (/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u.test(character)) {
      return width + 1;
    }
    if (/\p{Extended_Pictographic}/u.test(character)) return width + 1;
    if (/[A-Z0-9]/u.test(character)) return width + 0.62;
    if (/[a-záéíóúüñ¿¡]/iu.test(character)) return width + 0.55;
    return width + 0.42;
  }, 0).toFixed(2));
}

function statesByKey(copyManifest, catalogKeys) {
  const states = new Map(catalogKeys.map((key) => [key, new Set()]));
  for (const surface of copyManifest.surfaces) {
    for (const key of catalogKeys) {
      if (
        surface.requiredKeys.includes(key)
        || surface.keyPrefixes.some((prefix) => key.startsWith(prefix))
      ) {
        states.get(key).add(surface.state);
      }
    }
  }
  return states;
}

function riskSignals(value, referenceValue, states) {
  const widthEm = estimatedWidthEm(value);
  const referenceWidthEm = estimatedWidthEm(referenceValue);
  const expansionRatio = Number((widthEm / Math.max(referenceWidthEm, 1)).toFixed(2));
  const lineCount = String(value).split(/\r?\n/).length;
  const placeholderCount = (String(value).match(/\{[A-Za-z][A-Za-z0-9_]*\}/g) || []).length;
  const factors = [];
  let score = 0;

  if (widthEm >= 42) {
    factors.push('very-wide-copy');
    score += 35;
  } else if (widthEm >= 28) {
    factors.push('wide-copy');
    score += 22;
  } else if (widthEm >= 20) {
    factors.push('moderately-wide-copy');
    score += 10;
  }
  if (expansionRatio >= 2.2) {
    factors.push('very-high-expansion-vs-zh');
    score += 30;
  } else if (expansionRatio >= 1.6) {
    factors.push('high-expansion-vs-zh');
    score += 18;
  } else if (expansionRatio >= 1.3) {
    factors.push('moderate-expansion-vs-zh');
    score += 8;
  }
  if (lineCount > 1) {
    factors.push('explicit-multiline-copy');
    score += Math.min(18, (lineCount - 1) * 6);
  }
  if (placeholderCount > 0) {
    factors.push('dynamic-placeholder-width');
    score += Math.min(15, placeholderCount * 5);
  }
  if (states.some((state) => CRITICAL_STATES.has(state))) {
    factors.push('critical-flow-copy');
    score += 10;
  }

  return {
    widthEm,
    referenceWidthEm,
    expansionRatio,
    lineCount,
    placeholderCount,
    factors,
    score,
    severity: score >= 45 ? 'high' : score >= 25 ? 'medium' : 'low',
  };
}

function buildLayoutRiskWorklist() {
  const catalogs = Object.fromEntries(
    LOCALES.map((locale) => [locale, readJson(`web/src/i18n/${locale}.json`)]),
  );
  const copyManifest = readJson('web/src/i18n/app-surface-copy-manifest.json');
  const catalogKeys = Object.keys(catalogs['zh-TW']).sort();
  const keyStates = statesByKey(copyManifest, catalogKeys);
  const entries = [];

  for (const locale of LOCALES) {
    for (const key of catalogKeys) {
      const states = [...keyStates.get(key)].sort();
      const signals = riskSignals(catalogs[locale][key], catalogs['zh-TW'][key], states);
      entries.push({
        locale,
        key,
        value: catalogs[locale][key],
        states,
        ...signals,
        reviewStatus: 'pending',
        visualQaResult: 'pending',
      });
    }
  }
  entries.sort((left, right) => (
    right.score - left.score
    || left.locale.localeCompare(right.locale)
    || left.key.localeCompare(right.key)
  ));

  const bySeverity = { high: 0, medium: 0, low: 0 };
  const byLocale = Object.fromEntries(LOCALES.map((locale) => [
    locale,
    { high: 0, medium: 0, low: 0 },
  ]));
  for (const entry of entries) {
    bySeverity[entry.severity] += 1;
    byLocale[entry.locale][entry.severity] += 1;
  }

  return {
    schema: 'munea.i18n-layout-risk-worklist.v1',
    generatedFrom: [
      'web/src/i18n/app-surface-copy-manifest.json',
      ...LOCALES.map((locale) => `web/src/i18n/${locale}.json`),
    ],
    policy: {
      staticRiskOnly: true,
      automaticVisualAcceptanceForbidden: true,
      exactInstalledAppScreenshotsRequired: true,
      dynamicTypeProfilesRequired: true,
    },
    locales: [...LOCALES],
    catalogKeyCount: catalogKeys.length,
    entryCount: entries.length,
    summary: {
      bySeverity,
      byLocale,
    },
    entries,
  };
}

function formatSummary(worklist) {
  const lines = [
    `I18N layout risk worklist: ${worklist.entryCount} locale-key checks`,
    `High: ${worklist.summary.bySeverity.high}`,
    `Medium: ${worklist.summary.bySeverity.medium}`,
    `Low: ${worklist.summary.bySeverity.low}`,
    'Top static risks:',
  ];
  for (const entry of worklist.entries.slice(0, 15)) {
    lines.push(
      `- ${entry.locale}.${entry.key}: ${entry.score} `
      + `(${entry.factors.join(', ') || 'no-static-signal'})`,
    );
  }
  return lines.join('\n');
}

if (require.main === module) {
  const worklist = buildLayoutRiskWorklist();
  if (process.argv.includes('--json')) {
    process.stdout.write(`${JSON.stringify(worklist, null, 2)}\n`);
  } else {
    process.stdout.write(`${formatSummary(worklist)}\n`);
  }
}

module.exports = {
  LOCALES,
  buildLayoutRiskWorklist,
  estimatedWidthEm,
  formatSummary,
  riskSignals,
  statesByKey,
};
