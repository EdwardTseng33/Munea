#!/usr/bin/env node
/* 用藥紀錄：登入還沒確認的那幾秒，改紀錄的動作不可以寫進「上一個人」那份（2026-11-26）
 *
 * 背景：開 App 時登入狀態要幾秒才確認。為了狀態頁用藥卡不先寫「尚未服用」再跳成「都完成了」，
 * medication.js 這幾秒先讀「上次登入的人」那份（munea.medicationScope.last.v1）。
 * 讀可以；但這幾秒裡按「吃了／稍後／略過／取消」如果直接寫，萬一登入其實已經過期，
 * 這一筆就寫進上一個人的紀錄。所以這幾秒的寫入一律先收著，configure() 確認現在是誰之後才寫。
 *
 * 這支驗五件事：
 *   A. 這幾秒裡讀得到上一個人那份（狀態頁不跳的前提）
 *   B. 這幾秒裡按「吃了」（首頁、狀態頁、通知三種入口）都不寫進上一個人那份、也不送雲端
 *   C. 確認其實沒登入（configure 訪客）→ 收著的那筆寫進訪客那份，上一個人那份一筆都沒多
 *   D. 確認就是同一個人 → 收著的那筆寫進他那份、而且有送雲端
 *   E. 單純的訪客（沒有記著的上一個人）照舊立刻寫，不受影響
 *
 * 跑法：node scripts/test-medication-identity-hold.js（不需網路）
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'web', 'src', 'medication.js'), 'utf8');
const LAST_SCOPE_KEY = 'munea.medicationScope.last.v1';
const STORE_PREFIX = 'munea.medicationDoses.v1.';
const meds = [{ id: 'med-a', name: '血壓藥', time: '早餐後、晚餐後' }];

function boot(seed) {
  const values = new Map(Object.entries(seed || {}));
  const sandbox = {
    localStorage: {
      getItem: key => (values.has(key) ? values.get(key) : null),
      setItem: (key, value) => values.set(key, String(value)),
      removeItem: key => values.delete(key),
    },
    CustomEvent: function (name, options) { this.type = name; this.detail = options && options.detail; },
    console,
    Promise, Date, Object, Array, String, Number, Set, Map, JSON, Math, encodeURIComponent,
  };
  sandbox.window = sandbox;
  sandbox.dispatchEvent = () => {};
  sandbox.addEventListener = () => {};
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: 'medication.js' });
  return { M: sandbox.MuneaMedication, values };
}
function takenIn(values, scope) {
  let store = {};
  try { store = JSON.parse(values.get(STORE_PREFIX + encodeURIComponent(scope)) || '{}'); } catch (e) {}
  return Object.values(store).filter(e => e && e.status === 'taken').length;
}

(async () => {
  // ── A + B + C：上次是 person-a，這次登入其實過期（確認後是訪客） ──
  {
    const { M, values } = boot({ [LAST_SCOPE_KEY]: 'person-a' });
    assert.strictEqual(M.scope(), 'person-a', 'A：開 App 時要先讀上次那個人那份');
    assert.strictEqual(M.configured(), false);
    const today = M.dateKey();
    assert.ok(M.daySummary(today, meds), 'A：這幾秒要讀得到今天的用藥（狀態頁才畫得出來）');

    assert.strictEqual(M.markNext(meds, 'home'), null, 'B：首頁按「吃了」這幾秒不可以直接寫');
    M.toggleNext(meds, 'status');
    const dose = M.findDose(meds, '晚餐後|血壓藥', today);
    assert.ok(dose, 'B：通知那條要找得到這一劑');
    M.setStatus(dose, 'taken', 'notification');
    assert.strictEqual(takenIn(values, 'person-a'), 0, 'B：這幾秒按的「吃了」不可以寫進上一個人那份');
    assert.strictEqual(M.pendingWrites(), 3, 'B：三下都要先收著，不可以丟掉');

    await M.configure({ scope: 'guest', meds: () => meds });
    assert.strictEqual(takenIn(values, 'person-a'), 0, 'C：確認是訪客後，上一個人那份一筆都不能多');
    assert.ok(takenIn(values, 'guest') >= 1, 'C：收著的「吃了」要寫進訪客那份（現在用 App 的是訪客）');
    assert.strictEqual(M.pendingWrites(), 0, 'C：寫完要清空');
    assert.strictEqual(values.has(LAST_SCOPE_KEY), false, 'C：確認是訪客後不再記著上一個人');
  }

  // ── D：上次是 person-a，確認就是 person-a ──
  {
    const { M, values } = boot({ [LAST_SCOPE_KEY]: 'person-a' });
    const sent = [];
    M.markNext(meds, 'home');
    assert.strictEqual(takenIn(values, 'person-a'), 0, 'D：確認前不寫');
    assert.strictEqual(sent.length, 0, 'D：確認前不送雲端');
    await M.configure({ scope: 'person-a', meds: () => meds, post: body => { sent.push(body); return Promise.resolve({ ok: true, doses: [] }); } });
    assert.strictEqual(takenIn(values, 'person-a'), 1, 'D：確認是同一個人後，收著的那筆要寫進他那份');
    assert.ok(sent.some(b => b.action === 'save' && b.dose && b.dose.status === 'taken' && b.dose.personId === 'person-a'), 'D：而且要送雲端');
    assert.strictEqual(values.get(LAST_SCOPE_KEY), 'person-a');
    // 確認之後再按，照常立刻寫
    M.markNext(meds, 'home');
    assert.strictEqual(takenIn(values, 'person-a'), 2, 'D：確認之後照常立刻寫');
  }

  // ── E：單純的訪客（沒有記著的上一個人）照舊立刻寫 ──
  {
    const { M, values } = boot({});
    assert.strictEqual(M.scope(), 'guest');
    M.markNext(meds, 'home');
    assert.strictEqual(takenIn(values, 'guest'), 1, 'E：訪客按「吃了」要立刻寫，不可以被收著');
    assert.strictEqual(M.pendingWrites(), 0);
  }

  console.log('Medication identity hold PASS：登入確認前讀上一個人那份、寫入先收著；確認後寫進現在這個人那份（訪客／同一人／純訪客 3 種情境）');
})().catch(error => { console.error(error); process.exit(1); });
