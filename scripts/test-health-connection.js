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
    'health.reconnectHelp': 'Open Health to turn Munea back on.',
  };
  window.MuneaI18n = {
    t: (key, values, fallback) => translated[key] || fallback,
  };
  MuneaHealth.renderConnectionState();
  assert.strictEqual(elements.cnHealthBtn.textContent, 'Connect');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, 'Not connected');
  assert.strictEqual(elements.cnHealthDetail.textContent, 'Available health data');
  assert.strictEqual(elements.cnHealthHelp.textContent, 'Open Health to turn Munea back on.',
    '斷線後已經問過授權，說明要走「帶你去健康 App」那句，不是第一次那句');

  window.MuneaI18n = null;   // 回到中文預設字，接著驗「讀不到資料」這條路

  // 使用者只有兩種狀態＋一個動作：未連接 / 已連接 / 解除連接。
  // 「已連接」＝真的讀得到資料；讀不到就是未連接，不另外發明狀態給使用者理解。
  const clickMain = () => elements.cnHealthBtn.listeners.click({ preventDefault() {}, stopImmediatePropagation() {} });

  // ① 連了卻一項都讀不到 → 對使用者就是「未連接」，按鍵維持「連接」
  emptySummary = true;
  const again = await MuneaHealth.connect();
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(again.empty, true, '一項都讀不到必須回報 empty');
  assert.strictEqual(MuneaHealth.uiState(), 'off', '讀不到就是未連接，不得多發明一種狀態');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '未連接');
  assert.strictEqual(elements.cnHealthBtn.textContent, '連接', '按鍵一律只有「連接」或「解除連接」兩種字');
  assert.strictEqual(elements.cnHealthBtn.dataset.action, 'openHealth',
    '授權視窗只跳一次，之後按「連接」要直接帶去健康 App');
  assert.ok(/健康/.test(elements.cnHealthHelp.textContent), '說明要講清楚去哪裡打開');
  assert.ok(!MuneaHealth.hasAnyValue({ available: true }), '空摘要不得算成有資料');
  assert.ok(
    Object.values(MuneaHealth.metricStates()).every(state => state === 'empty'),
    '讀不到時每一項都必須標成 empty，不得沿用舊值繼續宣稱',
  );
  assert.strictEqual(openedHealthApp, 0, '沒按按鍵之前不得自己跳去健康 App');
  clickMain();
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(openedHealthApp, 1, '按「連接」必須帶去健康 App');
  assert.ok(/一項都沒有/.test(elements.cnHealthReadState.textContent), '讀取實況要讓人確定到底讀到沒');

  // ② 讀得到 → 已連接，按鍵變「解除連接」，說明講明它不會收回 iPhone 授權
  emptySummary = false;
  await MuneaHealth.refresh({ force: true });
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(MuneaHealth.uiState(), 'on');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '已連接');
  assert.strictEqual(elements.cnHealthBtn.textContent, '解除連接');
  assert.strictEqual(elements.cnHealthBtn.dataset.action, 'disconnect');
  assert.ok(/授權還是開著/.test(elements.cnHealthHelp.textContent), '解除連接必須講明 iPhone 授權沒被收回');
  assert.ok(/步數/.test(elements.cnHealthReadState.textContent), '讀取實況要列出讀到哪幾項');

  // ③ 本來讀得好好的、這次讀失敗 → 維持「已連接」。
  //    連線狀態沒有變，只是這一次沒讀到；跳成「未連接」等於謊報。
  //    失敗原因只寫在實況行給我們查，不變成使用者要理解的第三種狀態。
  summaryThrows = '健康資料暫時無法取得';
  await MuneaHealth.refresh({ force: true });
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(MuneaHealth.uiState(), 'on', '偶發讀取失敗不得把已連接誤報成未連接');
  assert.strictEqual(elements.healthSettingsStateLabel.textContent, '已連接');
  assert.strictEqual(elements.cnHealthBtn.textContent, '解除連接');
  assert.ok(/健康資料暫時無法取得/.test(elements.cnHealthReadState.textContent), '失敗原因要留在實況行給我們查');

  // ④ 但「從頭到尾沒讀到過、而且讀失敗」→ 就是未連接（不能因為失敗過就宣稱已連接）
  MuneaHealth.disconnect();
  values.set('munea.devicesOn', '1');
  await MuneaHealth.refresh({ force: true });
  await new Promise(resolve => setTimeout(resolve, 1));
  assert.strictEqual(MuneaHealth.uiState(), 'off', '沒讀到過又讀失敗，必須是未連接');
  summaryThrows = '';

  // 2026-07-31 Edward 實測回報：健康 App 顯示已授權、沐寧卻說未連結。
// 根因＝「已連結」看的是我們自己存在手機裡的旗子，重裝就被清掉；
// 但蘋果的授權還在（那個視窗一輩子只跳一次、補不回來）。
// 這幾條守住「自動接回」的三個分寸。
const healthSrc = fs.readFileSync('web/src/health.js', 'utf8');
assert.match(healthSrc, /relinkIfAlreadyAuthorized/, '缺少重裝後自動接回');
assert.match(healthSrc, /if \(connected\(\) \|\| relinkTried\) return false;/,
  '自動接回可能在已連線時、或同一次啟動裡重複執行');
assert.match(healthSrc, /munea\.health\.disconnectedAt[\s\S]{0,120}return false/,
  '他自己按過解除連接卻被自動接回——那是他的決定、不是重裝造成的失憶');
assert.match(healthSrc, /if \(!hasAnyValue\(s\)\) return false;/,
  '沒真的讀到值就把人標成已連線');

/* 2026-08-01 Edward 實機回報的三件事，各留一道門 */

const html = fs.readFileSync('web/index.html', 'utf8');

// ① 那行說明的文字是程式依狀態算出來的（四種說法）。掛了 data-i18n 之後，語言每次重新套用
//    就把它蓋回「目前未同步」——不管連沒連、讀到沒讀到，畫面永遠寫著同一句假話。
assert.match(html, /id="cnHealthHelp"(?![^>]*data-i18n)/,
  '健康說明那行不可以掛 data-i18n——翻譯層會把程式算出來的真話蓋成寫死的預設句');
assert.ok(!/data-i18n="health\.helpNotSynced"/.test(html),
  'health.helpNotSynced 是程式從來不用的死文案，不可以綁回畫面上');

// ② 使用者常常是自己從桌面開健康 App 改設定再切回來，那條路以前沒人在聽，
//    畫面就停在改之前的狀態，看起來像「我明明開了它還說沒連」。
assert.match(healthSrc, /visibilitychange[\s\S]{0,420}?refresh\(\{ force: true \}\)/,
  '切回 App 就要重讀一次，不能只在「從沐寧按連接跳出去」那一次才聽');
// 前景重讀不可以先擋 connected()：解除過或重裝過的人旗子是關的、但 iPhone 的授權還在，
// refresh() 開頭本來就會探一次。在這裡擋掉，他們在健康 App 開什麼都不會被讀到。
assert.ok(!/visibilitychange[\s\S]{0,300}?!connected\(\)[\s\S]{0,24}?return;/.test(healthSrc),
  '前景重讀不可以用 connected() 當前提——那會把「權限還在但旗子關著」的人永遠鎖在沒資料');
// 「幾點讀的、讀到哪幾項」是他自己判斷「是我沒開對還是 App 沒讀」的唯一線索，
// 綁在 connected() 上會剛好在讀不到的時候整行消失。
assert.ok(!/function readEvidence\(\)\s*\{\s*if \(!connected\(\)/.test(healthSrc),
  '讀取實況那行不可以綁 connected()——最需要它的時候它會不見');

// ③ 蘋果沒有任何一條路能直接開到「健康 → App 與服務 → 沐寧」，所以路要用文字寫清楚
//    （Strava／MyFitnessPal 都是這個做法）。只在讀不到、而且授權視窗不會再跳時出現。
assert.match(healthSrc, /function renderHealthSteps\(on, firstTime, view\)[\s\S]{0,200}?const show = !on && !firstTime && view !== 'checking'/,
  '找不到「接下來點這幾下」的指示卡，或它的出現條件不對');
['health.stepsTitle', 'health.step1', 'health.step2', 'health.step3', 'health.step4', 'health.stepsAlt']
  .forEach(key => assert.ok(
    JSON.parse(fs.readFileSync('web/src/i18n/zh-TW.json', 'utf8'))[key],
    `健康指示卡缺文案：${key}`,
  ));

console.log('Apple Health connection state: ALL PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
