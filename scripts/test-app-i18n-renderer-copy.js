'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {
  createAppRendererCopy,
} = require('../web/src/i18n/app-renderer-copy.js');

const ROOT = path.resolve(__dirname, '..');
const LOCALES = ['zh-TW', 'en', 'ja', 'es'];
const LOCALIZED_PRICES = {
  'zh-TW': 'NT$599',
  en: '$19.99',
  ja: '¥3,000',
  es: '19,99 €',
};

function translator(locale) {
  const catalog = JSON.parse(fs.readFileSync(
    path.join(ROOT, 'web', 'src', 'i18n', `${locale}.json`),
    'utf8',
  ));
  return (key, values) => {
    assert.equal(typeof catalog[key], 'string', `${locale}:${key} is missing`);
    return catalog[key].replace(
      /\{([A-Za-z][A-Za-z0-9_]*)\}/g,
      (token, name) => (
        Object.prototype.hasOwnProperty.call(values || {}, name)
          ? String(values[name])
          : token
      ),
    );
  };
}

for (const locale of LOCALES) {
  const copy = createAppRendererCopy({ t: translator(locale) });
  const price = LOCALIZED_PRICES[locale];

  const preparing = copy.queueCard({
    mode: 'queued',
    position: 1,
    etaSeconds: 80,
    companion: 'Ning',
  });
  assert.equal(preparing.action, 'cancel');
  assert.equal(preparing.position, '');
  assert.equal(preparing.showTextFallback, false);
  assert.ok(preparing.title.includes('Ning'));

  const queued = copy.queueCard({
    mode: 'queued',
    position: 3,
    etaSeconds: 121,
    companion: 'Ning',
  });
  assert.ok(queued.position.includes('3'));
  assert.ok(queued.note.includes('3'));
  assert.ok(!/\{[A-Za-z][A-Za-z0-9_]*\}/.test(JSON.stringify(queued)));

  const full = copy.queueCard({ mode: 'full', companion: 'Ning' });
  assert.equal(full.action, 'dismiss');
  assert.equal(full.showTextFallback, true);
  assert.ok(full.note.includes('Ning'));

  assert.equal(copy.authMessage('idle'), '');
  assert.ok(copy.authMessage('inProgress'));
  assert.ok(copy.callHint('ready'));
  assert.ok(copy.callHint('speaking'));
  assert.ok(copy.callHint('not-a-state'));
  const callStatuses = [
    'accountPreparing',
    'activationPending',
    'authExpired',
    'disconnected',
    'microphoneHttps',
    'microphonePermission',
    'readinessPending',
    'serviceBusy',
    'serviceUpdating',
    'unavailable',
  ].map(state => copy.callStatus(state));
  for (const status of callStatuses) {
    assert.ok(status.title && status.note && status.button);
  }
  assert.equal(copy.callStatus('authExpired').action, 'reopen-auth');
  assert.equal(copy.callStatus('not-a-state').action, 'dismiss');

  const buy = copy.purchaseButton({ credits: 200, price, state: 'ready' });
  assert.ok(buy.includes('200'));
  assert.ok(buy.includes(price));
  assert.ok(!buy.includes('{price}'));

  const cta = copy.subscriptionCta({
    currentPlan: 'free',
    selectedPlan: 'plus',
    price,
  });
  assert.ok(cta.includes(price));
  assert.equal(
    copy.subscriptionCta({
      currentPlan: 'plus',
      selectedPlan: 'plus',
      price,
    }).includes(price),
    false,
  );

  const confirmation = copy.planConfirmation({
    plan: 'pro',
    price,
    credits: 1200,
    members: 6,
  });
  assert.ok(confirmation.title.includes(price));
  assert.ok(confirmation.facts.includes('1200'));
  assert.ok(confirmation.facts.includes('6'));

  const paidSummary = copy.planSummary({
    plan: 'plus',
    monthlyCredits: 300,
    minutes: 300,
  });
  assert.ok(paidSummary.name);
  assert.ok(paidSummary.note.includes('300'));
  const freeSummary = copy.planSummary({ plan: 'free', remainingCredits: 0 });
  assert.ok(freeSummary.note);
  // 免費會員的說明句要講「手上還剩多少點」（伺服器錢包），不是「歷史買過多少點」
  const leftoverSummary = copy.planSummary({ plan: 'free', remainingCredits: 80 });
  assert.ok(leftoverSummary.note.includes('80'));
  // 舊參數名留著相容，行為要一致（還沒改完的呼叫端不會突然掉字）
  assert.strictEqual(copy.planSummary({ plan: 'free', purchasedCredits: 80 }).note, leftoverSummary.note);

  const prompt = copy.profilePrompt();
  assert.ok(prompt.title && prompt.body && prompt.action);
  const labels = copy.careLabels();
  assert.ok(labels.acknowledge && labels.open && labels.remove && labels.report);

  assert.ok(copy.familyRelay({ from: 'Ana', body: 'Mensaje' }).title.includes('Ana'));
  assert.ok(copy.familyRelay({ companion: 'Ning' }).body.includes('Ning'));
  assert.ok(copy.walkActivity({ owner: 'Ana', gap: 5000 }).body.includes('5000'));
  assert.ok(copy.walkActivity({ owner: 'Ana', gap: 0 }).body);
  assert.ok(copy.familyActivity({ owner: 'Ana', title: 'Paseo' }).body.includes('Paseo'));
  assert.ok(copy.upcomingVisit({
    title: 'Consulta',
    date: '7/31',
    companion: 'Ning',
  }).body.includes('Ning'));

  const rendered = JSON.stringify({
    buy,
    confirmation,
    cta,
    full,
    callStatuses,
    paidSummary,
    preparing,
    queued,
  });
  assert.ok(!/\{[A-Za-z][A-Za-z0-9_]*\}/.test(rendered), `${locale} leaked placeholders`);
}

const source = fs.readFileSync(
  path.join(ROOT, 'web', 'src', 'i18n', 'app-renderer-copy.js'),
  'utf8',
);
assert.ok(
  !/(?:NT|US)\$|[$€¥]|\b(?:USD|TWD|JPY|EUR)\b/u.test(source),
  'Renderer copy must not hard-code currency or infer a country from UI language',
);
assert.ok(
  !/(?:safetyRegion|legalRegion|dataRegion|country)\s*=/.test(source),
  'Renderer copy must not mutate region or data policy',
);

console.log('App renderer copy PASS: 9 dynamic renderer families x 4 locales');
