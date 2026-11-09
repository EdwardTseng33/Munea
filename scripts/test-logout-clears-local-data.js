#!/usr/bin/env node
/* 登出／換帳號清本機資料——2026-11-08 個資漏洞修補
 *
 * 事故：原本登出或換另一個 Munea 帳號登入時，只清了方案（munea.plan）與邀請碼
 * （munea.inviteCode／inviteCodeAt），上一個人存在本機的健康紀錄、用藥、就診、緊急
 * 聯絡人、家人圈、個人資料、AI 使用同意紀錄……都還在：家裡共用一台平板換人登入，
 * 看得到前一個人的資料，新登入的人也不會再看到 AI 同意畫面（舊的同意記號還在）。
 *
 * 這支測試把 app.js 裡新的「帳號範圍清理」區塊抽出來，在沙盒裡真的執行（手法同
 * scripts/test-care-questions.js），驗三件事：
 *   A. 換成不同身分 -> 個人/健康/對話/家人/同意這些鍵全部清空，裝置偏好鍵都還在
 *   B. 同一個人重新整理（身分沒變）-> 完全不清，不造成資料遺失
 *   C. 登出（uid 變空字串）也要清；之後換第二人再次清
 *
 * 跑法：node scripts/test-logout-clears-local-data.js（不需網路、不需鑰匙）
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web', 'src', 'app.js'), 'utf8');

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

function extractUpTo(source, startMarker, stopMarker, label) {
  const start = source.indexOf(startMarker);
  expect(start >= 0, '抽取失敗：找不到 ' + label + ' 的起點');
  const stop = source.indexOf(stopMarker, start);
  expect(stop >= 0, '抽取失敗：找不到 ' + label + ' 的終點');
  return source.slice(start, stop);
}

const block = extractUpTo(
  app,
  'const ACCOUNT_SCOPE_KEEP_KEYS = new Set([',
  '\nfunction updateAuthUI() {',
  '帳號範圍本機清理區塊'
);

// 模擬 Web Storage：要支援 .length/.key(i)（clearAccountScopedLocalData 用 for 迴圈掃全部鍵），
// 也要支援 getItem/setItem/removeItem，鍵的走訪順序=插入順序（跟真實瀏覽器一致）。
function makeStorageMock() {
  const map = new Map();
  return {
    getItem: function (k) { return map.has(k) ? map.get(k) : null; },
    setItem: function (k, v) { map.set(k, String(v)); },
    removeItem: function (k) { map.delete(k); },
    key: function (i) { const ks = Array.from(map.keys()); return i < ks.length ? ks[i] : null; },
    get length() { return map.size; },
  };
}

function runScenario() {
  const localStorageMock = makeStorageMock();
  const sessionStorageMock = makeStorageMock();
  const notifySyncCalls = [];
  const sandbox = {
    localStorage: localStorageMock,
    sessionStorage: sessionStorageMock,
    MuneaNotify: { sync: function () { notifySyncCalls.push(Date.now()); } },
    console: console,
    Set: Set, Array: Array, Object: Object, String: String, Number: Number,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(block, sandbox, { filename: 'app.js#accountScopedCleanup' });
  return { sandbox: sandbox, localStorageMock: localStorageMock, sessionStorageMock: sessionStorageMock, notifySyncCalls: notifySyncCalls };
}

function seedPersonalData(localStorageMock, sessionStorageMock) {
  const personal = {
    'munea.personProfile': '{"nick":"阿嬤","city":"台北"}',
    'munea.safetyContacts': '["大女兒"]',
    'munea.familyGroupId': 'fam-123',
    'munea.circleMembers': '[{"name":"大女兒"}]',
    'munea.familyBook': '{"notes":"..."}',
    'munea.healthLog': '[{"bp":"120/80"}]',
    'munea.health.last': '{"t":123}',
    'munea.meds': '[{"name":"降血壓藥"}]',
    'munea.medStartDates.v1': '{"降血壓藥":"2026-01-01"}',
    'munea.visits': '[{"date":"2026-11-10"}]',
    'munea.careQuestions': '[{"text":"血壓藥能不能跟感冒藥一起吃"}]',
    'munea.consent.crossborder': '2026-01-01T00:00:00.000Z',
    'munea.aiProviderConsent.v1': '{"agreed":true}',
    'munea.cloudPersonId': 'person-aaa',
    'munea.accountBootstrapped.v1': 'true',
    'munea.accountBootstrappedUser.v1': 'user-a',
    'munea.myMoodToday': 'ok',
    'munea.voiceCallDiagnostics.v1': '[{"turn":1}]',
    'munea.companionProfile.v1': '{"name":"寧寧"}',
    'munea.medicationDoses.v1.person-aaa': '{"2026-11-08":{"早餐後":"taken"}}',
    'munea.medicationDoses.migrated.v1.person-aaa': '1',
    'munea.medDone.2026-11-08': '{"早餐後":true}',
  };
  const keys = Object.keys(personal);
  for (let i = 0; i < keys.length; i++) localStorageMock.setItem(keys[i], personal[keys[i]]);

  const devicePrefs = {
    'munea.fontScale': '2',
    'munea.captions': '1',
    'munea.debug': '1',
    'munea.deviceId': 'device-xyz',
    'munea.faceEngine': 'flashhead',
    'munea.onboardingCompleted.v1': 'true',
    'munea.onboardingIntroSeen.v1': 'true',
    'munea.wxCache': '{"text":"晴"}',
    'munea.reviewCoolOff': '1',
    'munea.store.processedTransactions.v1': '["tx1"]',
    'munea.reviewAsked.forever': '1',
    'munea.admin.token': 'should-never-exist-but-defensive',
  };
  const prefKeys = Object.keys(devicePrefs);
  for (let i = 0; i < prefKeys.length; i++) localStorageMock.setItem(prefKeys[i], devicePrefs[prefKeys[i]]);

  localStorageMock.setItem('someOtherAppKey', 'untouched');
  sessionStorageMock.setItem('munea.somePersonalSessionThing', 'should-be-cleared');
  sessionStorageMock.setItem('unrelatedSessionKey', 'untouched');

  return { personalKeys: keys, devicePrefKeys: prefKeys };
}

(function partA() {
  const r = runScenario();
  const seeded = seedPersonalData(r.localStorageMock, r.sessionStorageMock);
  r.localStorageMock.setItem('munea.lastAuthUser', 'user-a');

  r.sandbox.syncAccountScopedCaches({ authUserId: 'user-b' });

  for (let i = 0; i < seeded.personalKeys.length; i++) {
    const k = seeded.personalKeys[i];
    expect(r.localStorageMock.getItem(k) === null, 'A 個人資料鍵沒清掉：' + k);
  }
  for (let i = 0; i < seeded.devicePrefKeys.length; i++) {
    const k = seeded.devicePrefKeys[i];
    expect(r.localStorageMock.getItem(k) !== null, 'A 裝置偏好鍵被誤清：' + k);
  }
  expect(r.localStorageMock.getItem('someOtherAppKey') === 'untouched', 'A 非 munea. 鍵不該被動到');
  expect(r.sessionStorageMock.getItem('munea.somePersonalSessionThing') === null, 'A sessionStorage 的個人資料也要清');
  expect(r.sessionStorageMock.getItem('unrelatedSessionKey') === 'untouched', 'A sessionStorage 非 munea. 鍵不該被動到');
  expect(r.localStorageMock.getItem('munea.lastAuthUser') === 'user-b', 'A 身分記號要更新成新 uid');
  expect(r.notifySyncCalls.length === 1, 'A 應該觸發一次 MuneaNotify.sync() 去重排本機提醒');
  console.log('PASS A：換身分後，個人/健康/對話/家人/同意鍵全清空，裝置偏好鍵都還在');
})();

(function partB() {
  const r = runScenario();
  const seeded = seedPersonalData(r.localStorageMock, r.sessionStorageMock);
  r.localStorageMock.setItem('munea.lastAuthUser', 'user-a');
  r.notifySyncCalls.length = 0;

  r.sandbox.syncAccountScopedCaches({ authUserId: 'user-a' });

  for (let i = 0; i < seeded.personalKeys.length; i++) {
    const k = seeded.personalKeys[i];
    expect(r.localStorageMock.getItem(k) !== null, 'B 同一人重登不該清掉：' + k);
  }
  expect(r.notifySyncCalls.length === 0, 'B 身分沒變就不該觸發清理/重排提醒');
  console.log('PASS B：同一人重新登入/重整，個人資料完全保留');
})();

(function partC() {
  const r = runScenario();
  seedPersonalData(r.localStorageMock, r.sessionStorageMock);
  r.localStorageMock.setItem('munea.lastAuthUser', 'user-a');

  r.sandbox.syncAccountScopedCaches({ status: 'guest', event: 'SIGNED_OUT' });
  expect(r.localStorageMock.getItem('munea.personProfile') === null, 'C 登出要清掉個人資料');
  expect(r.localStorageMock.getItem('munea.consent.crossborder') === null, 'C 登出要清掉 AI 使用同意紀錄，下一個人要重新同意');
  expect(r.localStorageMock.getItem('munea.fontScale') !== null, 'C 登出不該動到字體大小這類裝置偏好');
  expect(r.localStorageMock.getItem('munea.lastAuthUser') === '__signed_out__', 'C 登出後身分記號要記成「已登出」');

  r.localStorageMock.setItem('munea.personProfile', '{"nick":"路人"}');
  r.sandbox.syncAccountScopedCaches({ authUserId: 'user-b' });
  expect(r.localStorageMock.getItem('munea.personProfile') === null, 'C 換第二個人登入一樣要清乾淨');
  console.log('PASS C：登出會清、換第二人登入也會再清一次');
})();

(function partD() {
  // 不是真的登出／換人，一律不准清（11/8 蘇菲審查補）：本人只存在手機上的紀錄會整批弄丟
  const cases = [
    ['D1 第一次記到身分（升級後／新裝）', null, { authUserId: 'user-a' }],
    ['D2 App 剛打開、登入狀態還沒讀出來', 'user-a', { status: 'guest' }],
    ['D3 網路不穩讀不到登入', 'user-a', { status: 'guest', event: 'SESSION_UNAVAILABLE' }],
    ['D4 登入過期被擋', 'user-a', { status: 'guest', event: 'SESSION_REJECTED' }],
  ];
  cases.forEach(([label, last, state]) => {
    const r = runScenario();
    const seeded = seedPersonalData(r.localStorageMock, r.sessionStorageMock);
    if (last) r.localStorageMock.setItem('munea.lastAuthUser', last);
    r.sandbox.syncAccountScopedCaches(state);
    for (let i = 0; i < seeded.personalKeys.length; i++) {
      expect(r.localStorageMock.getItem(seeded.personalKeys[i]) !== null, label + ' 不該清：' + seeded.personalKeys[i]);
    }
    expect(r.notifySyncCalls.length === 0, label + ' 不該重排提醒');
  });
  console.log('PASS D：剛開 App／網路不穩／登入過期／第一次記身分，都不清本人資料');
})();

console.log('ALL PASS：登出/換帳號本機資料清理（munea. 個人資料清空、裝置偏好保留、同人不誤清）');
