'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const CATALOG_DIR = path.join(ROOT, 'web', 'src', 'i18n');
const LOCALES = Object.freeze(['zh-TW', 'en', 'ja', 'es']);
const SOURCE_LOCALE = 'zh-TW';

// These Japanese labels are legitimately written exactly like Traditional
// Chinese. Keeping the allowlist explicit means a newly copied Chinese string
// cannot silently pass as Japanese.
const JA_SHARED_SOURCE_KEYS = Object.freeze([
  'activity.kickerTitle',
  'activity.vote',
  'common.confirm',
  'demo.activity.doneShort',
  'visit.weekdaySun',
  'health.obsMetricSleep',
  'common.listSeparator',
  'familyCircle.you',
  'font.standard',
  'health.famSleepNote',
  'health.famStepsUnitWeeks',
  'report.periodLabel',
  'report.kSleep',
  'health.activityAmount',
  'profile.regionTier1State',
  'profile.countryJP',
  'health.normal',
  'health.notProvided',
  'health.unit.minutes',
  'health.sleep',
  'health.title',
  'medication.duration.longTerm',
  'settings.title',
  'status.activity',
  'status.weekNumber',
  'subscription.legalPeriod',
  'subscription.perMonthShort',
  'subscription.perYearShort',
  'subscription.planPlus',
  'subscription.planPro',
  'tab.settings',
  'version.subtitle',
  'weather.thunder',
  'voice.caption.label',
]);

function readCatalog(locale) {
  return fs.readFileSync(path.join(CATALOG_DIR, `${locale}.json`), 'utf8');
}

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, relativePath), 'utf8'));
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function placeholders(value) {
  return [...String(value).matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)]
    .map((match) => match[1])
    .sort();
}

function buildNativeReviewWorklist(localeFilter) {
  const locales = localeFilter ? [localeFilter] : [...LOCALES];
  for (const locale of locales) {
    if (!LOCALES.includes(locale)) {
      throw new Error(`Unsupported native review locale: ${locale}`);
    }
  }

  const reviewManifest = readJson('web/src/i18n/review-manifest.json');
  const sourceText = readCatalog(SOURCE_LOCALE);
  const sourceCatalog = JSON.parse(sourceText);
  const sourceKeys = Object.keys(sourceCatalog).sort();
  const entries = [];
  const catalogs = {};

  for (const locale of locales) {
    const catalogText = readCatalog(locale);
    const catalog = JSON.parse(catalogText);
    const keys = Object.keys(catalog).sort();
    if (JSON.stringify(keys) !== JSON.stringify(sourceKeys)) {
      throw new Error(`${locale} catalog key set differs from ${SOURCE_LOCALE}`);
    }
    catalogs[locale] = {
      catalog: `web/src/i18n/${locale}.json`,
      catalogSha256: sha256(catalogText),
      keyCount: keys.length,
      keysSha256: sha256(keys.join('\n')),
      contentVariant: reviewManifest.locales[locale].contentVariant,
    };

    for (const key of keys) {
      const source = sourceCatalog[key];
      const translation = catalog[key];
      const exactSourceMatch = locale !== SOURCE_LOCALE && translation === source;
      entries.push({
        sequence: entries.length + 1,
        locale,
        contentVariant: reviewManifest.locales[locale].contentVariant,
        key,
        sourceLocale: SOURCE_LOCALE,
        source,
        translation,
        sourceSha256: sha256(source),
        translationSha256: sha256(translation),
        placeholders: placeholders(source),
        exactSourceMatch,
        exactSourceMatchDisposition: exactSourceMatch
          ? (
            locale === 'ja' && JA_SHARED_SOURCE_KEYS.includes(key)
              ? 'approved-shared-japanese-term'
              : 'requires-review'
          )
          : 'not-applicable',
        result: 'pending',
        checks: {
          meaningPreserved: 'pending',
          grammarNatural: 'pending',
          toneAppropriate: 'pending',
          culturalContextAccepted: 'pending',
          placeholderContextAccepted: 'pending',
          spokenCopyReadAloud: 'pending',
        },
        reviewerNote: null,
      });
    }
  }

  return {
    schema: 'munea.i18n-native-review-worklist.v1',
    generatedFrom: [
      'web/src/i18n/review-manifest.json',
      ...locales.map((locale) => `web/src/i18n/${locale}.json`),
    ],
    sourceLocale: SOURCE_LOCALE,
    locales,
    catalogs,
    approvalPolicy: {
      automaticPassForbidden: true,
      nativeLanguageReviewerRequired: true,
      everyCatalogKeyRequired: true,
      catalogByteIdentityRequired: true,
      openIssuesMustBeZero: true,
    },
    entryCount: entries.length,
    entries,
  };
}

if (require.main === module) {
  const localeIndex = process.argv.indexOf('--locale');
  const locale = localeIndex >= 0 ? process.argv[localeIndex + 1] : null;
  process.stdout.write(`${JSON.stringify(buildNativeReviewWorklist(locale), null, 2)}\n`);
}

module.exports = {
  JA_SHARED_SOURCE_KEYS,
  LOCALES,
  SOURCE_LOCALE,
  buildNativeReviewWorklist,
  placeholders,
  sha256,
};
