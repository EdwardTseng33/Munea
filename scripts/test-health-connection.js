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
};
elements.cnHealthBtn.dataset.label = '連接';

let summaryReads = 0;
let historyReads = 0;
global.document = { getElementById: id => elements[id] || null };
global.CustomEvent = function (name, options) { this.type = name; this.detail = options.detail; };
global.window = global;
window.dispatchEvent = () => {};
window.__muneaSetHealth = () => {};
window.__muneaSetSteps = () => {};
window.__muneaSetHealthHistory = () => {};
window.Capacitor = {
  isNativePlatform: () => true,
  Plugins: { Health: {
    requestAuthorization: async () => ({ granted: true, available: true }),
    getSummary: async () => { summaryReads += 1; return { available: true, steps: 1234 }; },
    getHistory: async () => { historyReads += 1; return { available: true, days: [] }; },
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
  console.log('Apple Health connection state: ALL PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
