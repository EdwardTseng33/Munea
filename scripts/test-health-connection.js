const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const values = new Map([['munea.health.last', '{"kept":true}']]);
global.localStorage = {
  getItem: key => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: key => values.delete(key),
};

function element(label) {
  const classes = new Set();
  return {
    textContent: label || '',
    dataset: {},
    attributes: {},
    listeners: {},
    classList: {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
      toggle: (name, on) => on ? classes.add(name) : classes.delete(name),
      contains: name => classes.has(name),
    },
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(name, handler) { this.listeners[name] = handler; },
  };
}

const elements = {
  cnHealthBtn: element('連接'),
  healthSettingsState: element(),
  healthSettingsStateLabel: element('未連接'),
  cnHealthDetail: element(),
  cnHealthHelp: element(),
  cnHealthOpenBtn: element(),
};
elements.cnHealthBtn.dataset.label = '連接';

let summaryReads = 0;
let historyReads = 0;
let emptySummary = false;   // 模擬「授權過了、但一項都讀不到」
let openedHealthApp = 0;
global.document = {
  getElementById: id => elements[id] || null,
  addEventListener: () => {},
  removeEventListener: () => {},
  visibilityState: 'visible',
};
global.CustomEvent = function (name, options) { this.type = name; this.detail = options.detail; };
global.window = global;
window.dispatchEvent = () => {};
window.addEventListener = () => {};
window.__muneaSetHealth = () => {};
window.__muneaSetSteps = () => {};
window.__muneaSetHealthHistory = () => {};
window.Capacitor = {
  isNativePlatform: () => true,
  Plugins: { Health: {
    requestAuthorization: async () => ({ granted: true, available: true }),
    getSummary: async () => { summaryReads += 1; return emptySummary ? { available: true } : { available: true, steps: 1234 }; },
    getHistory: async () => { historyReads += 1; return { available: true, days: [] }; },
    openHealthApp: async () => { openedHealthApp += 1; return { opened: true }; },
  } },
};

vm.runInThisContext(fs.readFileSync('web/src/health.js', 'utf8'), { filename: 'health.js' });

(async () => {
  assert.strictEqual(MuneaHealth.connected(), false);
  assert.strictEqual(elements.cnHealthBtn.textContent, '連接');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '未連接');

  const result = await MuneaHealth.connect();
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(result.ok, true);
  assert.strictEqual(MuneaHealth.connected(), true);
  assert.strictEqual(elements.cnHealthBtn.textContent, '解除連接');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '已連接');
  assert.strictEqual(summaryReads, 1);
  assert.strictEqual(historyReads, 1);

  await Promise.all([
    MuneaHealth.refresh({ force: true }),
    MuneaHealth.refresh({ force: true }),
    MuneaHealth.refresh({ force: true }),
  ]);
  assert.strictEqual(summaryReads, 2, 'concurrent HealthKit refreshes must share one native request');
  assert.strictEqual(historyReads, 2, 'concurrent HealthKit history reads must share one native request');
  await MuneaHealth.refresh();
  MuneaHealth.boot();
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(summaryReads, 2, 'cooldown must suppress repeated startup/auth refreshes');
  assert.strictEqual(historyReads, 2, 'cooldown must suppress repeated history reads');
  const savedHistory = values.get('munea.health.last');

  const click = elements.cnHealthBtn.listeners.click;
  const event = { preventDefault() {}, stopImmediatePropagation() {} };
  click(event);
  assert.strictEqual(elements.cnHealthBtn.textContent, '再按一次解除');
  click(event);
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(MuneaHealth.connected(), false);
  assert.strictEqual(elements.cnHealthBtn.textContent, '連接');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '未連接');
  assert.strictEqual(values.get('munea.health.last'), savedHistory);

  await MuneaHealth.refresh();
  assert.strictEqual(summaryReads, 2, 'disconnect must stop future HealthKit reads');

  const translated = {
    'health.connect': 'Connect',
    'health.notConnected': 'Not connected',
    'health.availableDetail': 'Available health data',
    'health.notConnectedHelp': 'Connect to sync new health data.',
  };
  window.MuneaI18n = {
    t: (key, values, fallback) => translated[key] || fallback,
  };
  MuneaHealth.renderConnectionState();
  assert.strictEqual(elements.cnHealthBtn.textContent, 'Connect');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, 'Not connected');
  assert.strictEqual(elements.cnHealthDetail.textContent, 'Available health data');
  assert.strictEqual(elements.cnHealthHelp.textContent, 'Connect to sync new health data.');

  window.MuneaI18n = null;   // 回到中文預設字，接著驗「讀不到資料」這條路

  // 蘋果不會告訴 App 讀取被拒絕，而且授權視窗一輩子只跳一次。
  // 所以「連了卻一項都讀不到」必須：照實說 + 給一顆真的按鍵送使用者去健康 App，
  // 不能繼續叫他重按「連接」（系統不會再跳，永遠不會有結果）。
  emptySummary = true;
  const again = await MuneaHealth.connect();
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(again.empty, true, '一項都讀不到必須回報 empty');
  assert.strictEqual(again.needsHealthApp, true, '問過之後再連接必須直接送去健康 App');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '讀不到資料');
  assert.strictEqual(elements.cnHealthOpenBtn.hidden, false, '讀不到資料時必須出現「打開健康 App」按鍵');
  assert.ok(elements.cnHealthHelp.textContent.includes('健康'), '說明必須告訴使用者去健康 App 打開項目');
  assert.ok(!MuneaHealth.hasAnyValue({ available: true }), '空摘要不得算成有資料');
  assert.ok(
    Object.values(MuneaHealth.metricStates()).every(state => state === 'empty'),
    '讀不到時每一項都必須標成 empty，不得沿用舊值繼續宣稱',
  );
  assert.strictEqual(openedHealthApp, 0, '沒按按鍵之前不得自己跳去健康 App');
  elements.cnHealthOpenBtn.listeners.click();
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(openedHealthApp, 1, '按下按鍵必須打開健康 App');

  // 有資料時按鍵要收起來，不要一直提醒
  emptySummary = false;
  await MuneaHealth.refresh({ force: true });
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(elements.cnHealthOpenBtn.hidden, true, '讀得到資料後就不該再顯示補救按鍵');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '已連接');

  console.log('Apple Health connection state: ALL PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
