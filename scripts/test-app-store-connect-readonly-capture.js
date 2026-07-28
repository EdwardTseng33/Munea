'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const {
  ASC_ORIGIN,
  captureSnapshot,
  checkedAscUrl,
  createJwt,
  createReadOnlyClient,
  formatDisplayPrice,
  normalizePrices,
} = require('./app-store-connect-readonly-capture.js');
const {
  buildCurrentRequirements,
  validateSnapshot,
} = require('./app-store-connect-i18n-evidence.js');

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return body;
    },
  };
}

const { privateKey } = crypto.generateKeyPairSync('ec', {
  namedCurve: 'prime256v1',
});
const token = createJwt({
  keyId: 'TESTKEY123',
  issuerId: '00000000-0000-0000-0000-000000000000',
  privateKey,
  now: new Date('2026-07-29T12:00:00Z'),
  lifetimeSeconds: 600,
});
const [headerPart, payloadPart, signaturePart] = token.split('.');
assert.deepEqual(
  JSON.parse(Buffer.from(headerPart, 'base64url').toString('utf8')),
  { alg: 'ES256', kid: 'TESTKEY123', typ: 'JWT' },
);
assert.equal(
  JSON.parse(Buffer.from(payloadPart, 'base64url').toString('utf8')).aud,
  'appstoreconnect-v1',
);
assert.equal(Buffer.from(signaturePart, 'base64url').length, 64);
assert.throws(
  () => createJwt({
    keyId: 'x',
    privateKey,
    lifetimeSeconds: 1201,
  }),
  /1200/,
);
assert.throws(
  () => checkedAscUrl('https://example.com/v1/apps'),
  /Refusing/,
);

const calls = [];
const pagedClient = createReadOnlyClient({
  token: 'test-token',
  transport: async (url, options) => {
    calls.push({ url: url.href, options });
    if (url.searchParams.get('cursor') === 'page2') {
      return jsonResponse({
        data: [{ type: 'apps', id: '2' }],
        links: {},
      });
    }
    return jsonResponse({
      data: [{ type: 'apps', id: '1' }],
      links: {
        next: `${ASC_ORIGIN}/v1/apps?cursor=page2`,
      },
    });
  },
});

(async () => {
  const pages = await pagedClient.list('/v1/apps?limit=1');
  assert.deepEqual(pages.data.map(({ id }) => id), ['1', '2']);
  assert(calls.every(({ options }) => options.method === 'GET'));
  assert(calls.every(({ options }) => options.headers.Authorization === 'Bearer test-token'));

  const requirements = buildCurrentRequirements({
    spanishVariants: ['es-ES'],
  });
  const capturedAt = new Date('2026-07-29T12:00:00Z');
  const appId = '1234567890';
  const appInfoId = 'app-info-next';
  const appStoreVersionId = 'version-next';
  const territory3 = {
    TW: 'TWN',
    US: 'USA',
    JP: 'JPN',
    ES: 'ESP',
  };
  const localeInfo = Object.fromEntries(requirements.targets.map((target, index) => [
    target.appStoreLocale,
    {
      infoId: `info-loc-${index}`,
      versionId: `version-loc-${index}`,
      target,
    },
  ]));
  const productResources = requirements.products.map((product, index) => ({
    type: product.type === 'auto-renewable-subscription'
      ? 'subscriptions'
      : 'inAppPurchases',
    id: String(9000000000 + index),
    attributes: {
      productId: product.productId,
      ...(product.type === 'consumable'
        ? { inAppPurchaseType: 'CONSUMABLE' }
        : {}),
    },
  }));

  function listResult(data, included = []) {
    return { data, included };
  }

  const mockClient = {
    async request(input) {
      const url = checkedAscUrl(input);
      if (url.pathname.endsWith('/appAvailabilityV2')) {
        return {
          data: {
            type: 'appAvailabilities',
            id: 'availability-app',
            relationships: {
              territoryAvailabilities: {
                links: { related: `${ASC_ORIGIN}/v1/appAvailabilities/availability-app/territoryAvailabilities` },
              },
            },
          },
        };
      }
      if (url.pathname.endsWith('/inAppPurchaseAvailability')) {
        const id = url.pathname.split('/')[3];
        return {
          data: {
            type: 'inAppPurchaseAvailabilities',
            id,
            relationships: {
              availableTerritories: {
                links: { related: `${ASC_ORIGIN}/v1/inAppPurchaseAvailabilities/${id}/availableTerritories` },
              },
            },
          },
        };
      }
      if (url.pathname.endsWith('/appStoreReviewScreenshot')) {
        return {
          data: {
            type: 'reviewScreenshots',
            id: `review-${url.pathname.split('/')[3]}`,
          },
        };
      }
      throw new Error(`Unexpected mock request ${url.href}`);
    },
    async list(input) {
      const url = checkedAscUrl(input);
      const pathname = url.pathname;
      if (pathname === '/v1/apps') {
        return listResult([{
          type: 'apps',
          id: appId,
          attributes: { bundleId: requirements.bundleIdentifier },
        }]);
      }
      if (pathname === `/v1/apps/${appId}/appInfos`) {
        return listResult([{
          type: 'appInfos',
          id: appInfoId,
          attributes: { appStoreState: 'PREPARE_FOR_SUBMISSION' },
        }]);
      }
      if (pathname === `/v1/apps/${appId}/appStoreVersions`) {
        return listResult([{
          type: 'appStoreVersions',
          id: appStoreVersionId,
          attributes: {
            platform: 'IOS',
            versionString: '1.0.44',
            appStoreState: 'PREPARE_FOR_SUBMISSION',
          },
        }]);
      }
      if (pathname.endsWith('/territoryAvailabilities')) {
        return listResult(requirements.targets.map((target) => ({
          type: 'territoryAvailabilities',
          id: `availability-${target.territory}`,
          attributes: { available: true },
          relationships: {
            territory: {
              data: {
                type: 'territories',
                id: territory3[target.territory],
              },
            },
          },
        })));
      }
      if (pathname.match(/\/(inAppPurchase|subscription)Availabilities\/[^/]+\/availableTerritories$/)) {
        return listResult(requirements.targets.map((target) => ({
          type: 'territories',
          id: territory3[target.territory],
          attributes: {
            currency: {
              TW: 'TWD',
              US: 'USD',
              JP: 'JPY',
              ES: 'EUR',
            }[target.territory],
          },
        })));
      }
      if (pathname.endsWith('/planAvailabilities')) {
        const id = pathname.split('/')[3];
        return listResult([{
          type: 'subscriptionPlanAvailabilities',
          id: `plan-${id}`,
          attributes: { planType: 'UPFRONT' },
          relationships: {
            availableTerritories: {
              links: {
                related: `${ASC_ORIGIN}/v1/subscriptionPlanAvailabilities/plan-${id}/availableTerritories`,
              },
            },
          },
        }]);
      }
      if (pathname.match(/\/subscriptionPlanAvailabilities\/[^/]+\/availableTerritories$/)) {
        return listResult(requirements.targets.map((target) => ({
          type: 'territories',
          id: territory3[target.territory],
        })));
      }
      if (pathname === `/v1/appInfos/${appInfoId}/appInfoLocalizations`) {
        return listResult(Object.values(localeInfo).map(({ infoId, target }) => ({
          type: 'appInfoLocalizations',
          id: infoId,
          attributes: {
            locale: target.appStoreLocale,
            name: target.metadata.name,
            subtitle: target.metadata.subtitle,
            privacyPolicyUrl: target.metadata.privacyPolicyUrl,
          },
        })));
      }
      if (pathname === `/v1/appStoreVersions/${appStoreVersionId}/appStoreVersionLocalizations`) {
        return listResult(Object.values(localeInfo).map(({ versionId, target }) => ({
          type: 'appStoreVersionLocalizations',
          id: versionId,
          attributes: {
            locale: target.appStoreLocale,
            promotionalText: target.metadata.promotionalText,
            description: target.metadata.description,
            keywords: target.metadata.keywords,
            whatsNew: target.metadata.whatsNew,
            supportUrl: target.metadata.supportUrl,
            marketingUrl: target.metadata.marketingUrl,
          },
        })));
      }
      if (pathname.match(/\/v1\/appStoreVersionLocalizations\/[^/]+\/appScreenshotSets/)) {
        const localizationId = pathname.split('/')[3];
        return listResult(
          [{ type: 'appScreenshotSets', id: `set-${localizationId}` }],
          Array.from({ length: 5 }, (_, index) => ({
            type: 'appScreenshots',
            id: `${localizationId}-screenshot-${index}`,
          })),
        );
      }
      if (pathname === `/v1/apps/${appId}/inAppPurchasesV2`) {
        return listResult(productResources.filter(({ type }) => type === 'inAppPurchases'));
      }
      if (pathname === `/v1/apps/${appId}/subscriptionGroups`) {
        return listResult(
          [{ type: 'subscriptionGroups', id: 'group-1' }],
          productResources.filter(({ type }) => type === 'subscriptions'),
        );
      }
      if (pathname.endsWith('/inAppPurchaseLocalizations')
        || pathname.endsWith('/subscriptionLocalizations')) {
        const id = pathname.split('/')[3];
        const product = productResources.find((item) => item.id === id);
        return listResult(requirements.targets.map((target, index) => ({
          type: pathname.includes('subscription')
            ? 'subscriptionLocalizations'
            : 'inAppPurchaseLocalizations',
          id: `${id}-copy-${index}`,
          attributes: {
            locale: target.appStoreLocale,
            name: target.iapCopy[product.attributes.productId].displayName,
            description: target.iapCopy[product.attributes.productId].description,
          },
        })));
      }
      if (pathname.endsWith('/prices')
        || pathname.endsWith('/manualPrices')
        || pathname.endsWith('/automaticPrices')) {
        if (pathname.endsWith('/automaticPrices')) return listResult([]);
        const isSubscription = pathname.endsWith('/prices');
        const pointType = isSubscription
          ? 'subscriptionPricePoints'
          : 'inAppPurchasePricePoints';
        const pointRelationship = isSubscription
          ? 'subscriptionPricePoint'
          : 'inAppPurchasePricePoint';
        const rows = [];
        const included = [];
        requirements.targets.forEach((target, index) => {
          const territoryId = territory3[target.territory];
          const pointId = `${pathname.split('/')[3]}-point-${territoryId}`;
          rows.push({
            type: isSubscription ? 'subscriptionPrices' : 'inAppPurchasePrices',
            id: `price-${pointId}`,
            attributes: { startDate: null, endDate: null },
            relationships: {
              territory: { data: { type: 'territories', id: territoryId } },
              [pointRelationship]: { data: { type: pointType, id: pointId } },
            },
          });
          included.push({
            type: 'territories',
            id: territoryId,
            attributes: {
              currency: {
                TW: 'TWD',
                US: 'USD',
                JP: 'JPY',
                ES: 'EUR',
              }[target.territory],
            },
          });
          included.push({
            type: pointType,
            id: pointId,
            attributes: { customerPrice: String(9.99 + index) },
          });
        });
        return listResult(rows, included);
      }
      throw new Error(`Unexpected mock list ${url.href}`);
    },
  };

  const snapshot = await captureSnapshot({
    client: mockClient,
    requirements,
    appInfoId,
    appStoreVersionId,
    capturedAt,
  });
  assert.equal(validateSnapshot(snapshot, requirements, capturedAt), true);
  assert.equal(snapshot.localizations['en-US'].screenshotCount, 5);
  assert.equal(snapshot.iapProducts.length, 8);
  assert.equal(snapshot.productionWritesPerformed, false);
  assert(snapshot.iapProducts.every(({ localizedPrices }) => localizedPrices.JP.currency === 'JPY'));

  const price = formatDisplayPrice('9.99', 'USD', 'en-US');
  assert.match(price, /\$9\.99/);
  const normalized = normalizePrices({
    data: [{
      type: 'subscriptionPrices',
      id: 'p',
      attributes: {},
      relationships: {
        territory: { data: { type: 'territories', id: 'USA' } },
        subscriptionPricePoint: {
          data: { type: 'subscriptionPricePoints', id: 'pp' },
        },
      },
    }],
    included: [
      { type: 'territories', id: 'USA', attributes: { currency: 'USD' } },
      {
        type: 'subscriptionPricePoints',
        id: 'pp',
        attributes: { customerPrice: '4.99' },
      },
    ],
  }, requirements, capturedAt);
  assert.equal(normalized.US.customerPrice, '4.99');
  assert.equal(normalized.US.source, 'app-store-connect-api-customer-price');

  console.log(
    'PASS: App Store Connect capture uses GET-only pagination and normalizes '
    + '4 locales, territories, screenshots, 8 products, copy, review assets, and prices',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
