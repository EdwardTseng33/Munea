'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {
  buildCurrentRequirements,
  compileEvidence,
} = require('./app-store-connect-i18n-evidence.js');

const ASC_ORIGIN = 'https://api.appstoreconnect.apple.com';
const ASC_AUDIENCE = 'appstoreconnect-v1';
const MAX_TOKEN_SECONDS = 20 * 60;
const TERRITORY_ALPHA3 = Object.freeze({
  TW: 'TWN',
  US: 'USA',
  JP: 'JPN',
  ES: 'ESP',
  MX: 'MEX',
});
const IAP_TYPE_MAP = Object.freeze({
  CONSUMABLE: 'consumable',
  NON_CONSUMABLE: 'non-consumable',
  NON_RENEWING_SUBSCRIPTION: 'non-renewing-subscription',
});

function base64url(value) {
  return Buffer.from(value).toString('base64url');
}

function createJwt({
  keyId,
  issuerId,
  privateKey,
  now = new Date(),
  lifetimeSeconds = 10 * 60,
}) {
  if (!keyId || !privateKey) {
    throw new Error('App Store Connect key ID and private key are required');
  }
  if (
    !Number.isSafeInteger(lifetimeSeconds)
    || lifetimeSeconds < 60
    || lifetimeSeconds > MAX_TOKEN_SECONDS
  ) {
    throw new Error('JWT lifetime must be between 60 and 1200 seconds');
  }
  const issuedAt = Math.floor(now.getTime() / 1000);
  const header = {
    alg: 'ES256',
    kid: keyId,
    typ: 'JWT',
  };
  const payload = {
    ...(issuerId ? { iss: issuerId } : { sub: 'user' }),
    iat: issuedAt,
    exp: issuedAt + lifetimeSeconds,
    aud: ASC_AUDIENCE,
  };
  const signingInput = [
    base64url(JSON.stringify(header)),
    base64url(JSON.stringify(payload)),
  ].join('.');
  const signature = crypto.sign(
    'sha256',
    Buffer.from(signingInput),
    {
      key: privateKey,
      dsaEncoding: 'ieee-p1363',
    },
  );
  return `${signingInput}.${base64url(signature)}`;
}

function checkedAscUrl(input) {
  const url = new URL(input, ASC_ORIGIN);
  if (
    url.origin !== ASC_ORIGIN
    || (!url.pathname.startsWith('/v1/') && !url.pathname.startsWith('/v2/'))
  ) {
    throw new Error(`Refusing non-App-Store-Connect URL: ${url.href}`);
  }
  return url;
}

function createReadOnlyClient({
  token,
  transport = globalThis.fetch,
}) {
  if (!token || typeof transport !== 'function') {
    throw new Error('A JWT and fetch-compatible transport are required');
  }

  async function request(input, { optional404 = false } = {}) {
    const url = checkedAscUrl(input);
    const response = await transport(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
    });
    if (optional404 && response.status === 404) return null;
    if (!response.ok) {
      let detail = '';
      try {
        const body = await response.json();
        detail = body.errors && body.errors[0] && body.errors[0].detail;
      } catch {
        detail = '';
      }
      throw new Error(
        `App Store Connect GET ${url.pathname} failed: HTTP ${response.status}`
        + (detail ? ` ${detail}` : ''),
      );
    }
    return response.json();
  }

  async function list(input) {
    let next = checkedAscUrl(input).href;
    const data = [];
    const included = [];
    while (next) {
      const body = await request(next);
      if (!body || !Array.isArray(body.data)) {
        throw new Error(`Expected a JSON:API list from ${next}`);
      }
      data.push(...body.data);
      if (Array.isArray(body.included)) included.push(...body.included);
      next = body.links && body.links.next
        ? checkedAscUrl(body.links.next).href
        : '';
    }
    return { data, included };
  }

  return { list, request };
}

function relationshipId(resource, name) {
  const data = resource
    && resource.relationships
    && resource.relationships[name]
    && resource.relationships[name].data;
  return data && !Array.isArray(data) ? data.id : '';
}

function relatedUrl(resource, name) {
  return resource
    && resource.relationships
    && resource.relationships[name]
    && resource.relationships[name].links
    && resource.relationships[name].links.related;
}

function includedIndex(included = []) {
  return new Map(included.map((resource) => [
    `${resource.type}:${resource.id}`,
    resource,
  ]));
}

function requireSingle(resources, label, expectedId = '') {
  const matches = expectedId
    ? resources.filter(({ id }) => id === expectedId)
    : resources;
  if (matches.length !== 1) {
    throw new Error(
      expectedId
        ? `${label} ${expectedId} was not returned by App Store Connect`
        : `${label} is ambiguous; provide its explicit resource ID`,
    );
  }
  return matches[0];
}

function targetTerritoryIds(requirements) {
  return requirements.targets.map(({ territory }) => {
    const alpha3 = TERRITORY_ALPHA3[territory];
    if (!alpha3) throw new Error(`No App Store territory mapping for ${territory}`);
    return alpha3;
  });
}

function alpha2Territory(alpha3) {
  const entry = Object.entries(TERRITORY_ALPHA3)
    .find(([, candidate]) => candidate === alpha3);
  return entry ? entry[0] : '';
}

function localeForTerritory(requirements, territoryAlpha3) {
  const alpha2 = alpha2Territory(territoryAlpha3);
  const target = requirements.targets.find(({ territory }) => territory === alpha2);
  return target ? target.appStoreLocale : 'en-US';
}

function formatDisplayPrice(amount, currency, locale) {
  const numeric = Number(amount);
  if (!Number.isFinite(numeric) || !currency) return '';
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
  }).format(numeric);
}

function activePriceRows(data, referenceTime) {
  const now = referenceTime.getTime();
  return data.filter(({ attributes = {} }) => {
    const start = attributes.startDate ? Date.parse(attributes.startDate) : -Infinity;
    const end = attributes.endDate ? Date.parse(attributes.endDate) : Infinity;
    return start <= now && now < end;
  });
}

function normalizePrices(response, requirements, referenceTime) {
  const index = includedIndex(response.included);
  const normalized = {};
  for (const row of activePriceRows(response.data, referenceTime)) {
    const territoryId = relationshipId(row, 'territory');
    const pointId = relationshipId(row, 'subscriptionPricePoint')
      || relationshipId(row, 'inAppPurchasePricePoint');
    const territory = index.get(`territories:${territoryId}`);
    const point = index.get(`subscriptionPricePoints:${pointId}`)
      || index.get(`inAppPurchasePricePoints:${pointId}`);
    const currency = territory && territory.attributes && territory.attributes.currency;
    const customerPrice = point && point.attributes && point.attributes.customerPrice;
    const alpha2 = alpha2Territory(territoryId);
    if (!alpha2 || !requirements.targets.some(({ territory: id }) => id === alpha2)) {
      continue;
    }
    normalized[alpha2] = {
      currency,
      displayPrice: formatDisplayPrice(
        customerPrice,
        currency,
        localeForTerritory(requirements, territoryId),
      ),
      customerPrice: String(customerPrice),
      source: 'app-store-connect-api-customer-price',
    };
  }
  return normalized;
}

async function readAvailabilityTerritories(client, response, relationshipName) {
  const resource = response && response.data;
  const url = relatedUrl(resource, relationshipName);
  if (!url) return [];
  const related = await client.list(url);
  return related.data
    .filter((item) => item.type === 'territories'
      || (item.type === 'territoryAvailabilities'
        && item.attributes
        && item.attributes.available === true))
    .map((item) => (
      item.type === 'territories'
        ? item.id
        : relationshipId(item, 'territory')
    ))
    .filter(Boolean);
}

async function captureAppLocalizations(
  client,
  requirements,
  appInfoId,
  appStoreVersionId,
) {
  const info = await client.list(
    `/v1/appInfos/${encodeURIComponent(appInfoId)}/appInfoLocalizations`
    + '?fields[appInfoLocalizations]=locale,name,subtitle,privacyPolicyUrl&limit=200',
  );
  const version = await client.list(
    `/v1/appStoreVersions/${encodeURIComponent(appStoreVersionId)}`
    + '/appStoreVersionLocalizations'
    + '?fields[appStoreVersionLocalizations]='
    + 'locale,description,keywords,marketingUrl,promotionalText,supportUrl,whatsNew'
    + '&limit=200',
  );
  const infoByLocale = new Map(info.data.map((item) => [item.attributes.locale, item]));
  const versionByLocale = new Map(version.data.map((item) => [item.attributes.locale, item]));
  const localizations = {};
  for (const target of requirements.targets) {
    const appInfo = infoByLocale.get(target.appStoreLocale);
    const appVersion = versionByLocale.get(target.appStoreLocale);
    if (!appInfo || !appVersion) {
      throw new Error(`Missing App Store localization ${target.appStoreLocale}`);
    }
    const screenshotSets = await client.list(
      `/v1/appStoreVersionLocalizations/${encodeURIComponent(appVersion.id)}`
      + '/appScreenshotSets?include=appScreenshots&limit=200&limit[appScreenshots]=50',
    );
    const screenshotIds = new Set(
      screenshotSets.included
        .filter(({ type }) => type === 'appScreenshots')
        .map(({ id }) => id),
    );
    localizations[target.appStoreLocale] = {
      metadata: {
        name: appInfo.attributes.name,
        subtitle: appInfo.attributes.subtitle,
        promotionalText: appVersion.attributes.promotionalText,
        description: appVersion.attributes.description,
        keywords: appVersion.attributes.keywords,
        whatsNew: appVersion.attributes.whatsNew,
        privacyPolicyUrl: appInfo.attributes.privacyPolicyUrl,
        supportUrl: appVersion.attributes.supportUrl,
        marketingUrl: appVersion.attributes.marketingUrl,
      },
      screenshotCount: screenshotIds.size,
      appInfoLocalizationId: appInfo.id,
      appStoreVersionLocalizationId: appVersion.id,
    };
  }
  return localizations;
}

async function reviewScreenshotAttached(client, url) {
  const response = await client.request(url, { optional404: true });
  return Boolean(response && response.data && response.data.id);
}

async function productLocalizations(client, url) {
  const response = await client.list(url);
  return Object.fromEntries(response.data.map(({ attributes }) => [
    attributes.locale,
    {
      displayName: attributes.name,
      description: attributes.description,
    },
  ]));
}

async function captureConsumable(client, resource, requirements, referenceTime) {
  const id = resource.id;
  const availability = await client.request(
    `/v2/inAppPurchases/${encodeURIComponent(id)}/inAppPurchaseAvailability`,
  );
  const territories = await readAvailabilityTerritories(
    client,
    availability,
    'availableTerritories',
  );
  const targetIds = targetTerritoryIds(requirements).join(',');
  const [manual, automatic] = await Promise.all([
    client.list(
      `/v1/inAppPurchasePriceSchedules/${encodeURIComponent(id)}/manualPrices`
      + `?filter[territory]=${targetIds}`
      + '&include=territory,inAppPurchasePricePoint'
      + '&fields[territories]=currency'
      + '&fields[inAppPurchasePricePoints]=customerPrice,territory'
      + '&limit=200',
    ),
    client.list(
      `/v1/inAppPurchasePriceSchedules/${encodeURIComponent(id)}/automaticPrices`
      + `?filter[territory]=${targetIds}`
      + '&include=territory,inAppPurchasePricePoint'
      + '&fields[territories]=currency'
      + '&fields[inAppPurchasePricePoints]=customerPrice,territory'
      + '&limit=200',
    ),
  ]);
  return {
    productId: resource.attributes.productId,
    type: IAP_TYPE_MAP[resource.attributes.inAppPurchaseType]
      || resource.attributes.inAppPurchaseType,
    appStoreConnectProductId: id,
    reviewScreenshotAttached: await reviewScreenshotAttached(
      client,
      `/v2/inAppPurchases/${encodeURIComponent(id)}/appStoreReviewScreenshot`,
    ),
    availableTerritories: territories.map(alpha2Territory).filter(Boolean),
    localizations: await productLocalizations(
      client,
      `/v2/inAppPurchases/${encodeURIComponent(id)}`
      + '/inAppPurchaseLocalizations'
      + '?fields[inAppPurchaseLocalizations]=name,locale,description&limit=200',
    ),
    localizedPrices: normalizePrices({
      data: [...manual.data, ...automatic.data],
      included: [...manual.included, ...automatic.included],
    }, requirements, referenceTime),
  };
}

async function captureSubscription(client, resource, requirements, referenceTime) {
  const id = resource.id;
  const targetIds = targetTerritoryIds(requirements).join(',');
  const planAvailabilities = await client.list(
    `/v1/subscriptions/${encodeURIComponent(id)}/planAvailabilities`
    + '?fields[subscriptionPlanAvailabilities]='
    + 'availableInNewTerritories,planType,availableTerritories'
    + '&limit=200',
  );
  const territories = new Set();
  for (const plan of planAvailabilities.data) {
    const url = relatedUrl(plan, 'availableTerritories');
    if (!url) continue;
    const available = await client.list(url);
    available.data.forEach(({ id: territoryId }) => territories.add(territoryId));
  }
  const prices = await client.list(
    `/v1/subscriptions/${encodeURIComponent(id)}/prices`
    + `?filter[territory]=${targetIds}`
    + '&include=territory,subscriptionPricePoint'
    + '&fields[territories]=currency'
    + '&fields[subscriptionPricePoints]=customerPrice,territory'
    + '&limit=200',
  );
  return {
    productId: resource.attributes.productId,
    type: 'auto-renewable-subscription',
    appStoreConnectProductId: id,
    reviewScreenshotAttached: await reviewScreenshotAttached(
      client,
      `/v1/subscriptions/${encodeURIComponent(id)}/appStoreReviewScreenshot`,
    ),
    availableTerritories: [...territories].map(alpha2Territory).filter(Boolean),
    localizations: await productLocalizations(
      client,
      `/v1/subscriptions/${encodeURIComponent(id)}`
      + '/subscriptionLocalizations'
      + '?fields[subscriptionLocalizations]=name,locale,description&limit=200',
    ),
    localizedPrices: normalizePrices(prices, requirements, referenceTime),
  };
}

async function captureSnapshot({
  client,
  requirements = buildCurrentRequirements(),
  appInfoId,
  appStoreVersionId,
  capturedAt = new Date(),
}) {
  if (!requirements.spanishMarketSelectionComplete) {
    throw new Error('Select and authorize an App Store Spanish market before capture');
  }
  if (!appInfoId || !appStoreVersionId) {
    throw new Error('Explicit App Info and App Store Version resource IDs are required');
  }
  const apps = await client.list(
    `/v1/apps?filter[bundleId]=${encodeURIComponent(requirements.bundleIdentifier)}`
    + '&fields[apps]=bundleId&limit=2',
  );
  const app = requireSingle(apps.data, 'Munea App Store Connect app');
  if (app.attributes.bundleId !== requirements.bundleIdentifier) {
    throw new Error('App Store Connect returned a different bundle identifier');
  }

  const appInfos = await client.list(
    `/v1/apps/${encodeURIComponent(app.id)}/appInfos`
    + '?fields[appInfos]=appStoreState&limit=200',
  );
  requireSingle(appInfos.data, 'App Info', appInfoId);
  const versions = await client.list(
    `/v1/apps/${encodeURIComponent(app.id)}/appStoreVersions`
    + '?filter[platform]=IOS'
    + '&fields[appStoreVersions]=platform,versionString,appStoreState&limit=200',
  );
  requireSingle(versions.data, 'App Store Version', appStoreVersionId);

  const availability = await client.request(
    `/v1/apps/${encodeURIComponent(app.id)}/appAvailabilityV2`,
  );
  const appTerritoryIds = await readAvailabilityTerritories(
    client,
    availability,
    'territoryAvailabilities',
  );
  const localizations = await captureAppLocalizations(
    client,
    requirements,
    appInfoId,
    appStoreVersionId,
  );

  const iap = await client.list(
    `/v1/apps/${encodeURIComponent(app.id)}/inAppPurchasesV2`
    + '?fields[inAppPurchases]=productId,inAppPurchaseType&limit=200',
  );
  const groups = await client.list(
    `/v1/apps/${encodeURIComponent(app.id)}/subscriptionGroups`
    + '?include=subscriptions'
    + '&fields[subscriptions]=productId'
    + '&limit=200&limit[subscriptions]=50',
  );
  const subscriptions = groups.included
    .filter(({ type }) => type === 'subscriptions');
  const products = [];
  for (const resource of iap.data) {
    products.push(await captureConsumable(client, resource, requirements, capturedAt));
  }
  for (const resource of subscriptions) {
    products.push(await captureSubscription(client, resource, requirements, capturedAt));
  }

  const timestamp = capturedAt.toISOString();
  return {
    schema: 'munea.app-store-connect-i18n-snapshot.v1',
    capturedAt: timestamp,
    captureMethod: requirements.captureMethod,
    evidenceReference: [
      'asc-readonly',
      app.id,
      appStoreVersionId,
      timestamp,
    ].join(':'),
    containsSecrets: false,
    productionWritesPerformed: false,
    bundleIdentifier: requirements.bundleIdentifier,
    appStoreConnectAppId: String(app.id),
    appInfoId,
    appStoreVersionId,
    appAvailability: {
      territories: appTerritoryIds.map(alpha2Territory).filter(Boolean),
    },
    localizations,
    iapProducts: products,
  };
}

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : '';
}

async function main() {
  const output = argument('--output');
  const auditOutput = argument('--audit-output');
  const appInfoId = argument('--app-info-id');
  const appStoreVersionId = argument('--app-store-version-id');
  const keyId = process.env.ASC_KEY_ID;
  const issuerId = process.env.ASC_ISSUER_ID;
  const privateKeyPath = process.env.ASC_PRIVATE_KEY_PATH;
  if (!output || !auditOutput || !appInfoId || !appStoreVersionId) {
    throw new Error(
      'usage: --app-info-id <id> --app-store-version-id <id> '
      + '--output <snapshot.json> --audit-output <audit.json>',
    );
  }
  if (!keyId || !privateKeyPath) {
    throw new Error('ASC_KEY_ID and ASC_PRIVATE_KEY_PATH are required');
  }
  const privateKey = fs.readFileSync(path.resolve(privateKeyPath), 'utf8');
  const token = createJwt({ keyId, issuerId, privateKey });
  const client = createReadOnlyClient({ token });
  const requirements = buildCurrentRequirements();
  const snapshot = await captureSnapshot({
    client,
    requirements,
    appInfoId,
    appStoreVersionId,
  });
  const audit = compileEvidence(snapshot);
  const outputPath = path.resolve(output);
  const auditPath = path.resolve(auditOutput);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.mkdirSync(path.dirname(auditPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(snapshot, null, 2)}\n`, 'utf8');
  fs.writeFileSync(auditPath, `${JSON.stringify(audit, null, 2)}\n`, 'utf8');
  process.stdout.write(
    `PASS: read-only App Store Connect capture verified ${audit.targetLocales.length} locales `
    + `and ${audit.productCount} products\n`,
  );
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`App Store Connect capture refused: ${error.message}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  ASC_ORIGIN,
  MAX_TOKEN_SECONDS,
  TERRITORY_ALPHA3,
  captureSnapshot,
  checkedAscUrl,
  createJwt,
  createReadOnlyClient,
  formatDisplayPrice,
  normalizePrices,
};
