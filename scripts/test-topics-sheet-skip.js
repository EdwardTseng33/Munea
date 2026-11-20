#!/usr/bin/env node
// 「想聊的話題」那一頁不可以把人卡住（2026-11-17，iPhone 模擬器實跑抓到）。
//
// 病徵：新用戶按「開始通話」跳出這頁——
//   1. 「先跳過，直接開始聊」從來沒顯示過：樣式表把它預設成不顯示，程式卻寫空字串「交還樣式表」。
//   2. 按叉叉／往下拉關掉後沒記「問過了」，下一次按通話又跳出來，怎麼關都打不出去。
// 這支測試把 app.js 裡真正的那段開啟程式抽出來，用假畫面跑。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(ROOT, 'web', 'src', 'app.js'), 'utf8');
const css = fs.readFileSync(path.join(ROOT, 'web', 'src', 'styles.css'), 'utf8');

const startMarker = 'window.__muneaOpenInterests = function (fromCall) {';
const start = app.indexOf(startMarker);
assert.ok(start >= 0, 'app.js 找不到 window.__muneaOpenInterests');
const end = app.indexOf('\n  };', start);
assert.ok(end > start, '找不到 __muneaOpenInterests 的結尾');
const body = app.slice(start + startMarker.length, end);

function run(fromCall, { storageThrows = false } = {}) {
  const skip = { style: { display: 'unset-by-test' } };
  const modal = { shown: false, classList: { add(name) { if (name === 'show') modal.shown = true; } } };
  const store = new Map();
  const localStorage = {
    setItem(k, v) { if (storageThrows) throw new Error('storage blocked'); store.set(k, String(v)); },
    getItem(k) { return store.has(k) ? store.get(k) : null; },
  };
  const $ = sel => (sel === '#interestsSkip' ? skip : sel === '#interestsModal' ? modal : null);
  const state = { rendered: 0 };
  // eslint-disable-next-line no-new-func
  const fn = new Function(
    '$', 'localStorage', 'loadInterests', 'renderInterestPicks', 'fromCall',
    `let _intSel = []; let _intFromCall = false;\n${body}\nreturn { _intFromCall };`,
  );
  const out = fn($, localStorage, () => [], () => { state.rendered += 1; }, fromCall);
  return { skip, modal, store, out, state };
}

// 樣式表目前把連結預設成不顯示——所以程式一定要明講怎麼顯示。這個前提變了，這支測試要跟著重看。
const skipRule = /\.topic-skip\s*\{[^}]*\}/.exec(css);
assert.ok(skipRule, 'styles.css 找不到 .topic-skip');
const hiddenByDefault = /display\s*:\s*none/.test(skipRule[0]);

// 從「開始通話」打開：看得到「先跳過」、當下就記「問過了」、視窗有開。
{
  const r = run(true);
  assert.ok(r.modal.shown, '從通話打開時視窗沒有開');
  assert.notEqual(r.skip.style.display, 'none', '從通話打開時「先跳過」被藏起來');
  if (hiddenByDefault) {
    assert.notEqual(
      r.skip.style.display, '',
      '樣式表預設把「先跳過」藏起來，程式寫空字串等於永遠看不到——要明講 block',
    );
  }
  assert.equal(
    r.store.get('munea.interestsAsked'), '1',
    '從通話打開時沒有當下記「問過了」——按叉叉關掉後，下一次按通話又會跳出來',
  );
  assert.equal(r.out._intFromCall, true);
}

// 從設定頁打開：不需要「先跳過」，也不動「問過了」這個記號。
{
  const r = run(false);
  assert.ok(r.modal.shown, '從設定頁打開時視窗沒有開');
  assert.equal(r.skip.style.display, 'none', '從設定頁打開時不該出現「先跳過，直接開始聊」');
  assert.equal(r.store.has('munea.interestsAsked'), false, '從設定頁打開不該動「問過了」的記號');
}

// 手機不給存（隱私模式等）：照樣要開得起來，不可以整段壞掉。
{
  const r = run(true, { storageThrows: true });
  assert.ok(r.modal.shown, '存不進去時視窗沒有開');
  assert.notEqual(r.skip.style.display, 'none');
}

// 通話鈕那一關還是靠同一個記號決定要不要問——記號名字改了這裡要一起改。
assert.ok(
  /!localStorage\.getItem\('munea\.interestsAsked'\)[^\n]*__muneaOpenInterests\(true\)/.test(app),
  '通話鈕判斷「問過沒」的那一行變了，請確認記號名稱仍是 munea.interestsAsked',
);

console.log('Topics sheet OK: 從通話打開看得到「先跳過」、當下就記問過了（叉叉／下拉關掉不再重複跳）；從設定頁打開不受影響；存不進去也開得起來');
