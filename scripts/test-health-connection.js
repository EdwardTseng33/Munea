const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const styles = fs.readFileSync('web/src/styles.css', 'utf8');

assert.match(
  styles,
  /html\[lang="en"\] #connect \.cn-row,\s*html\[lang="es"\] #connect \.cn-row\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*44px minmax\(0,\s*1fr\)/s,
  'English and Spanish health cards must preserve a readable copy column at App XL',
);
assert.match(
  styles,
  /html\[lang="en"\] #connect \.cn-row \.cn-btn,\s*html\[lang="es"\] #connect \.cn-row \.cn-btn\s*\{[^}]*grid-column:\s*2[^}]*justify-self:\s*start/s,
  'English and Spanish health connect buttons must move below expanded copy',
);

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
  cnHealthReadState: element(),
};
elements.cnHealthBtn.dataset.label = '連接';

let summaryReads = 0;
let historyReads = 0;
let emptySummary = false;   // 模擬「授權過了、但一項都讀不到」
let summaryThrows = '';     // 模擬讀取整個失敗（要跟「沒資料」分得開）
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
    getSummary: async () => { summaryReads += 1; if (summaryThrows) throw new Error(summaryThrows); return emptySummary ? { available: true, fields: [], errors: [] } : { available: true, steps: 1234, fields: ['steps'], errors: [] }; },
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

  // 整頁只有一顆按鍵，它做什麼由狀態決定。以下驗四種狀態各自的行為。
  const clickMain = () => elements.cnHealthBtn.listeners.click({ preventDefault() {}, stopImmediatePropagation() {} });

  // ① 連了卻一項都讀不到：照實說，而且那顆鍵要變成「去健康 App 打開項目」
  //    （不能還顯示「解除連接」——什麼都沒讀到，根本沒東西可解除）
  emptySummary = true;
  const again = await MuneaHealth.connect();
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(again.empty, true, '一項都讀不到必須回報 empty');
  assert.strictEqual(again.needsHealthApp, true, '問過之後再連接代表系統不會再跳視窗');
  assert.strictEqual(MuneaHealth.uiState(), 'empty');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '讀不到資料');
  assert.strictEqual(elements.cnHealthBtn.dataset.action, 'openHealth', '讀不到時主按鍵必須改成去健康 App');
  assert.ok(/健康/.test(elements.cnHealthBtn.textContent), '按鍵文字要講清楚是去健康 App');
  assert.ok(!MuneaHealth.hasAnyValue({ available: true }), '空摘要不得算成有資料');
  assert.ok(
    Object.values(MuneaHealth.metricStates()).every(state => state === 'empty'),
    '讀不到時每一項都必須標成 empty，不得沿用舊值繼續宣稱',
  );
  assert.strictEqual(openedHealthApp, 0, '沒按按鍵之前不得自己跳去健康 App');
  clickMain();
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(openedHealthApp, 1, '按下按鍵必須打開健康 App');
  assert.ok(/一項都沒有/.test(elements.cnHealthReadState.textContent), '要顯示讀取實況，讓人確定到底讀到沒');

  // ② 讀得到：按鍵才變回「解除連接」，並且說明要講明它不會收回 iPhone 的授權
  emptySummary = false;
  await MuneaHealth.refresh({ force: true });
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(MuneaHealth.uiState(), 'ok');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '已連接');
  assert.strictEqual(elements.cnHealthBtn.dataset.action, 'disconnect');
  assert.ok(/授權還是開著/.test(elements.cnHealthHelp.textContent), '解除連接必須講明 iPhone 授權沒被收回');
  assert.ok(/步數/.test(elements.cnHealthReadState.textContent), '讀取實況要列出讀到哪幾項');

  // ③ 讀取失敗：不可以跟「沒資料」混為一談，要講原因並給「再試一次」
  summaryThrows = '健康資料暫時無法取得';
  await MuneaHealth.refresh({ force: true });
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(MuneaHealth.uiState(), 'error', '讀取失敗必須自成一種狀態，不能算成沒資料');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '讀取失敗');
  assert.strictEqual(elements.cnHealthBtn.dataset.action, 'retry');
  assert.ok(/健康資料暫時無法取得/.test(elements.cnHealthReadState.textContent), '失敗原因必須看得到');
  summaryThrows = '';
  clickMain();
  await new Promise(resolve => setTimeout(resolve, 5));
  assert.strictEqual(MuneaHealth.uiState(), 'ok', '按再試一次要能救回來');

  console.log('Apple Health connection state: ALL PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
