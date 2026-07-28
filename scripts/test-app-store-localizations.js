'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve('app-store/localizations');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8'));
const screenshotPlan = JSON.parse(
  fs.readFileSync(path.join(root, 'screenshot-plan.json'), 'utf8'),
);
const inventory = JSON.parse(fs.readFileSync('docs/I18N-SURFACE-INVENTORY.json', 'utf8'));
const localeKeys = ['zh-Hant', 'en-US', 'ja', 'es'];
const requiredMetadata = [
  'name',
  'subtitle',
  'promotionalText',
  'description',
  'keywords',
  'whatsNew',
  'privacyPolicyUrl',
  'supportUrl',
  'marketingUrl',
];
const bannedClaims = [
  /automatically switches? to (?:a )?free/i,
  /free basic companionship/i,
  /自動切換.*免費/,
  /不扣點.*基本陪伴/,
  /自動的?に無料/,
  /cambia automáticamente.*gratis/i,
  /\bdiagnoses?\b/i,
  /\btreats?\b/i,
  /診断します/,
  /治療します/,
  /diagnostica enfermedades/i,
  /trata enfermedades/i,
];

assert.equal(manifest.schemaVersion, 1, 'App Store localization manifest must use schema version 1');
assert.equal(manifest.authority, 'repository-draft-only', 'Repository metadata must not claim App Store authority');
assert.deepEqual(Object.keys(manifest.locales), localeKeys, 'The store pack must cover the four planned locales');
assert.equal(manifest.appAvailability.currentState, 'unverified');
assert.equal(manifest.appAvailability.changeAuthorized, false);
assert.equal(
  manifest.inAppPurchaseManifest,
  '../in-app-purchases/manifest.json',
  'IAP metadata and availability must have one independent source of truth',
);
assert(
  fs.existsSync(path.resolve(root, manifest.inAppPurchaseManifest)),
  'The referenced IAP localization manifest must exist',
);
assert.equal(screenshotPlan.schema, 'munea.app-store-screenshot-plan.v1');
assert.equal(screenshotPlan.authority, 'repository-draft-only');
assert.equal(screenshotPlan.status, 'draft');
assert.deepEqual(screenshotPlan.canvas, { width: 1242, height: 2688, format: 'png' });
assert.deepEqual(Object.keys(screenshotPlan.locales), localeKeys);

const appStates = new Set(
  inventory.surfaces.find((surface) => surface.id === 'app-webview').requiredStates,
);
const requiredFrameOrder = [
  'voice-companion',
  'daily-reminders',
  'family-circle',
  'conversation-memory',
  'wellbeing-records',
];
assert.deepEqual(screenshotPlan.frameOrder, requiredFrameOrder);

for (const localeKey of localeKeys) {
  const locale = manifest.locales[localeKey];
  assert.equal(locale.promotionAuthorized, false, `${localeKey} must remain gated`);
  assert.notEqual(locale.metadataReview, 'approved', `${localeKey} metadata still needs review`);
  assert.equal(locale.expectedScreenshotCount, 5, `${localeKey} should preserve the five-screen story`);

  const filePath = path.join(root, locale.metadataFile);
  assert(fs.existsSync(filePath), `Missing App Store metadata for ${localeKey}`);
  const metadata = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  const screenshotLocale = screenshotPlan.locales[localeKey];
  assert(screenshotLocale, `Missing screenshot story for ${localeKey}`);
  assert.equal(screenshotLocale.catalogLocale, locale.catalogLocale);
  assert.notEqual(screenshotLocale.status, 'approved');
  assert.equal(screenshotLocale.frames.length, locale.expectedScreenshotCount);
  assert.deepEqual(
    screenshotLocale.frames.map((frame) => frame.id),
    requiredFrameOrder,
    `${localeKey} screenshot story must keep the approved five-frame order`,
  );
  for (const frame of screenshotLocale.frames) {
    assert(appStates.has(frame.appState), `${localeKey}.${frame.id} has unknown App state`);
    assert(frame.headline.trim(), `${localeKey}.${frame.id} needs a headline`);
    assert(frame.supportingText.trim(), `${localeKey}.${frame.id} needs supporting text`);
    assert([...frame.headline].length <= 48, `${localeKey}.${frame.id} headline is too long`);
    assert([...frame.supportingText].length <= 100, `${localeKey}.${frame.id} support text is too long`);
    assert(!/[\r\n<>]/.test(frame.headline), `${localeKey}.${frame.id} headline must be plain text`);
    assert(!/[\r\n<>]/.test(frame.supportingText), `${localeKey}.${frame.id} support text must be plain text`);
  }

  for (const field of requiredMetadata) {
    assert.equal(typeof metadata[field], 'string', `${localeKey}.${field} must be a string`);
    assert(metadata[field].trim(), `${localeKey}.${field} must not be empty`);
  }

  assert([...metadata.name].length <= 30, `${localeKey} name exceeds 30 characters`);
  assert([...metadata.subtitle].length <= 30, `${localeKey} subtitle exceeds 30 characters`);
  assert([...metadata.promotionalText].length <= 170, `${localeKey} promotional text exceeds 170 characters`);
  assert([...metadata.description].length <= 4000, `${localeKey} description exceeds 4000 characters`);
  assert(Buffer.byteLength(metadata.keywords, 'utf8') <= 100, `${localeKey} keywords exceed 100 UTF-8 bytes`);
  assert(!/<[^>]+>/.test(metadata.description), `${localeKey} description must remain plain text`);

  for (const urlField of ['privacyPolicyUrl', 'supportUrl', 'marketingUrl']) {
    const url = new URL(metadata[urlField]);
    assert.equal(url.protocol, 'https:', `${localeKey}.${urlField} must use HTTPS`);
    assert.equal(url.hostname, 'app.munea.net', `${localeKey}.${urlField} must use the controlled App domain`);
  }

  const searchableCopy = [
    metadata.name,
    metadata.subtitle,
    metadata.promotionalText,
    metadata.description,
    metadata.whatsNew,
  ].join('\n');
  for (const pattern of bannedClaims) {
    assert(!pattern.test(searchableCopy), `${localeKey} contains a banned or false store claim: ${pattern}`);
  }
}

assert(
  !/陪伴/.test(JSON.stringify(screenshotPlan.locales.ja))
    && !/陪伴/.test(JSON.stringify(JSON.parse(fs.readFileSync(path.join(root, 'ja.json'), 'utf8')))),
  'Japanese copy must not retain the Chinese-only term 陪伴',
);

const screenshotDirectory = path.resolve(root, manifest.locales['zh-Hant'].screenshotDirectory);
const primaryScreenshots = fs.readdirSync(screenshotDirectory).filter((name) => /\.png$/i.test(name));
assert.equal(primaryScreenshots.length, 5, 'The existing primary locale must have exactly five screenshot files');
for (const filename of primaryScreenshots) {
  const data = fs.readFileSync(path.join(screenshotDirectory, filename));
  assert.equal(data.readUInt32BE(16), 1242, `${filename} must be 1242 px wide`);
  assert.equal(data.readUInt32BE(20), 2688, `${filename} must be 2688 px high`);
}

assert.equal(manifest.locales['en-US'].screenshotStatus, 'missing');
assert.equal(manifest.locales.ja.screenshotStatus, 'missing');
assert.equal(manifest.locales.es.screenshotStatus, 'missing');
assert.equal(manifest.locales.es.appStoreLocale, null, 'Spanish App Store locale must wait for es-ES or es-MX choice');
assert.deepEqual(
  manifest.locales.es.candidateAppStoreLocales,
  ['es-ES', 'es-MX'],
  'Apple supports separate Spain and Mexico Spanish localizations',
);
assert.deepEqual(manifest.locales.es.targetTerritories, [], 'Spanish territories must stay closed before market choice');

console.log('PASS: App Store localization drafts, limits, screenshots, and availability gates');
