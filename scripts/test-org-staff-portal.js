#!/usr/bin/env node
// 機構專區（照護人員登入版）守門測試 · 2026-11-18
// 跑法：node scripts/test-org-staff-portal.js（不需網路、不需瀏覽器：用假的畫面元件把 web/src/org.js 真的跑一遍）
//
// 盯的事：
//   一、用到的接口路徑都在，後端 engine/server.py 真的有接；角色假資料跟後端 capabilities_for 一致。
//   二、示範模式（?demo=1）完全不打網路、不載登入元件；正常模式絕不讀示範資料。
//   三、分頁只看 capabilities：照服員沒有提醒分頁、點不進週摘要；企業窗口只有總覽與月報；
//       「幾天沒聯絡才提醒」只有後端說 canEdit 的人才有儲存鈕。
//   四、判定與設定送出的 body 欄位剛好是後端要的；送不出去時視窗不關、內容不清空；每種錯誤都有白話。
//   五、後端字串一律當純文字：整支檔不用 innerHTML，塞了 <img onerror> 也只會變成字。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const read = rel => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const ORG_JS = read('web/src/org.js');
const ORG_HTML = read('web/org.html');
const ORG_CSS = read('web/src/org.css');
const SERVER = read('engine/server.py');
const APP_JS = read('web/src/app.js');

let passed = 0;
async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log('  ok  ' + name);
  } catch (err) {
    console.error('  FAIL ' + name);
    throw err;
  }
}

// ───────────────────────── 假的畫面元件（只做 org.js 用得到的那些） ─────────────────────────
class FakeNode {
  constructor(doc) {
    this.ownerDocument = doc;
    this.parentNode = null;
    this.childNodes = [];
  }
  get firstChild() { return this.childNodes[0] || null; }
  appendChild(child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.childNodes.push(child);
    this.ownerDocument._appended(child);
    return child;
  }
  insertBefore(child, ref) {
    if (!ref) return this.appendChild(child);
    if (child.parentNode) child.parentNode.removeChild(child);
    const i = this.childNodes.indexOf(ref);
    if (i < 0) throw new Error('insertBefore: reference is not a child');
    child.parentNode = this;
    this.childNodes.splice(i, 0, child);
    this.ownerDocument._appended(child);
    return child;
  }
  removeChild(child) {
    const i = this.childNodes.indexOf(child);
    if (i < 0) throw new Error('removeChild: not a child');
    this.childNodes.splice(i, 1);
    child.parentNode = null;
    return child;
  }
  replaceChild(next, old) {
    const i = this.childNodes.indexOf(old);
    if (i < 0) throw new Error('replaceChild: not a child');
    if (next.parentNode) next.parentNode.removeChild(next);
    this.childNodes[i] = next;
    next.parentNode = this;
    old.parentNode = null;
    this.ownerDocument._appended(next);
    return old;
  }
  get textContent() { return this.childNodes.map(c => c.textContent).join(''); }
  set textContent(value) {
    this.childNodes.forEach(c => { c.parentNode = null; });
    this.childNodes = [];
    const t = value === null || value === undefined ? '' : String(value);
    if (t) this.appendChild(new FakeText(this.ownerDocument, t));
  }
}

class FakeText extends FakeNode {
  constructor(doc, data) { super(doc); this.nodeType = 3; this.data = String(data); }
  get textContent() { return this.data; }
  set textContent(value) { this.data = String(value); }
}

class FakeElement extends FakeNode {
  constructor(doc, tag, ns) {
    super(doc);
    this.nodeType = 1;
    this.tagName = String(tag).toUpperCase();
    this.namespaceURI = ns || null;
    this.attributes = {};
    this.listeners = {};
    this.style = {};
    this.hidden = false;
    this.disabled = false;
    this.value = '';
  }
  get className() { return this.attributes.class || ''; }
  set className(v) { this.attributes.class = String(v); }
  get id() { return this.attributes.id || ''; }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attributes, k) ? this.attributes[k] : null; }
  removeAttribute(k) { delete this.attributes[k]; }
  hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attributes, k); }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] || []).filter(f => f !== fn); }
  focus() { this.ownerDocument.activeElement = this; }
  scrollIntoView() {}
  get children() { return this.childNodes.filter(n => n.nodeType === 1); }
  // 把字串當 HTML 塞進畫面的寫法一律不准用：一碰就記下來並直接炸掉
  set innerHTML(v) { this.ownerDocument.htmlWrites.push(String(v)); throw new Error('innerHTML write is not allowed'); }
  get innerHTML() { throw new Error('innerHTML read is not allowed'); }
  set outerHTML(v) { this.ownerDocument.htmlWrites.push(String(v)); throw new Error('outerHTML write is not allowed'); }
  insertAdjacentHTML(_pos, v) { this.ownerDocument.htmlWrites.push(String(v)); throw new Error('insertAdjacentHTML is not allowed'); }
}

class FakeDocument extends FakeNode {
  constructor() {
    super(null);
    this.ownerDocument = this;
    this.listeners = {};
    this.htmlWrites = [];
    this.created = [];
    this.scripts = [];
    this.activeElement = null;
    this.title = '沐寧 Munea · 機構專區';
    this.onScript = null;
    this.documentElement = new FakeElement(this, 'html');
    this.head = new FakeElement(this, 'head');
    this.body = new FakeElement(this, 'body');
    this.documentElement.appendChild(this.head);
    this.documentElement.appendChild(this.body);
  }
  createElement(tag) { const el = new FakeElement(this, tag); this.created.push(el); return el; }
  createElementNS(ns, tag) { const el = new FakeElement(this, tag, ns); this.created.push(el); return el; }
  createTextNode(t) { return new FakeText(this, t); }
  getElementById(id) { return all(this.documentElement, el => el.getAttribute('id') === id)[0] || null; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  write(v) { this.htmlWrites.push(String(v)); throw new Error('document.write is not allowed'); }
  _appended(node) {
    if (node.tagName === 'SCRIPT') {
      this.scripts.push(node.getAttribute('src'));
      if (this.onScript) this.onScript(node);
    }
  }
}

function walk(node, fn) { fn(node); (node.childNodes || []).forEach(c => walk(c, fn)); }
function all(root, pred) { const out = []; walk(root, n => { if (n.nodeType === 1 && pred(n)) out.push(n); }); return out; }
function hasClass(el, c) { return (el.getAttribute('class') || '').split(/\s+/).includes(c); }
function byClass(root, c) { return all(root, el => hasClass(el, c)); }
function text(node) { return node.textContent.replace(/ /g, ' '); }
function visible(el) { for (let n = el; n; n = n.parentNode) { if (n.hidden) return false; } return true; }
function buttonsNamed(root, label) { return all(root, el => el.tagName === 'BUTTON' && text(el).trim() === label && visible(el)); }
async function settle(rounds = 40) { for (let i = 0; i < rounds; i += 1) await new Promise(r => setImmediate(r)); }
async function click(el) {
  assert.ok(el, '要點的東西不存在');
  for (const fn of el.listeners.click || []) await fn({ type: 'click', target: el, preventDefault() {}, stopPropagation() {} });
  await settle();
}
async function fire(el, type) {
  for (const fn of el.listeners[type] || []) await fn({ type, target: el, preventDefault() {}, stopPropagation() {} });
  await settle();
}
function tabLabels(doc) { return byClass(doc.body, 'tab').map(t => text(t).replace(/\d+$/, '').trim()); }
async function openTab(doc, label) { await click(byClass(doc.body, 'tab').find(t => text(t).replace(/\d+$/, '').trim() === label)); }

// ───────────────────────── 假後端（形狀照 engine/org_api.py、org_alerts.py） ─────────────────────────
const CAPS = {
  org_admin: { summary: true, elders: true, careWeek: true, reports: true, siteScoped: false, siteLabel: null, level: 'L2' },
  case_manager: { summary: true, elders: true, careWeek: true, reports: true, siteScoped: true, siteLabel: '北院', level: 'L2' },
  care_worker: { summary: true, elders: true, careWeek: false, reports: false, siteScoped: true, siteLabel: '北院', level: 'L1' },
  esg: { summary: true, elders: false, careWeek: false, reports: true, siteScoped: false, siteLabel: null, level: 'L0' },
};
const POISON = '<img src=x onerror="alert(1)">';
const SEAT_A = '6f1e2d3c-0000-4000-8000-00000000000a';
const SEAT_B = '7a2b3c4d-0000-4000-8000-00000000000b';

function meFor(role, poison) {
  const tag = poison ? POISON : '';
  return {
    ok: true,
    staff: { id: 'stf-1', displayName: '測試社工' + tag, role: role === 'esg' ? 'org_admin' : role, siteLabel: CAPS[role].siteLabel, status: 'active' },
    org: { id: 'org-1', name: '測試機構' + tag, clientKind: role === 'esg' ? 'esg' : 'care', planTier: 'plus', contractEnd: '2027-06-30' },
    capabilities: { ...CAPS[role] },
  };
}

function summary() {
  return {
    ok: true,
    org: { name: '測試機構', planTier: 'plus', contractStart: '2026-01-01', contractEnd: '2027-06-30' },
    seats: { quota: 20, active: 12, pending: 0, released: 0, unusedQuota: 8, utilization: 0.6 },
    period: { start: '2026-10-20', end: '2026-11-18', days: 30, previousStart: '2026-09-20' },
    usage: { enabledCount: 12, activeCount: 10, activeRate: 0.8333, retentionRate: 0.9, retentionBaseCount: 10, avgWeeklyInteractionsPerPerson: 4.6, smallSampleSuppressed: false },
    guardian: { highRiskEventCount: 3, followedUpCount: null, followUpTrackingAvailable: false, medicationCompletionRate: 0.92, medicationDecidedCount: 214, smallSampleSuppressed: false },
    reports: { count: 0, list: [] },
    privacy: { personalDataIncluded: false, smallSampleSuppressed: false, minGroupSize: 5, statement: '' },
    generatedAt: '2026-11-18T01:00:00Z',
    scope: { siteLabel: null, siteScoped: false },
    consent: { grantedSeats: 2 },
  };
}

function elders(poison) {
  return {
    ok: true,
    period: { start: '2026-11-12', end: '2026-11-18', days: 7 },
    scope: { siteLabel: null, siteScoped: false, level: 'L2' },
    count: 2,
    elders: [
      { seatId: SEAT_A, seatCode: '6F1E2D3C', label: '測試阿嬤' + (poison ? POISON : ''), siteLabel: '北院', flags: { noInteractionToday: true, lowMood: true, guardianLit: false }, anomalyTypes: ['mood_drop'], lastInteractionDate: '2026-11-17', partial: [] },
      { seatId: SEAT_B, seatCode: '7A2B3C4D', label: '測試阿公', siteLabel: '南院', flags: { noInteractionToday: false, lowMood: false, guardianLit: false }, anomalyTypes: [], lastInteractionDate: '2026-11-18', partial: [] },
    ],
    partial: [],
    privacy: { statement: '' },
  };
}

function careWeek(seatId) {
  return {
    ok: true, seatId, seatCode: seatId.slice(0, 8).toUpperCase(), label: '測試阿嬤', siteLabel: '北院',
    week: {
      period: { start: '2026-11-12', end: '2026-11-18', days: 7 },
      contact: { source: '系統紀錄', calls: 5, daysWithCall: ['2026-11-12', '2026-11-13', '2026-11-15', '2026-11-16', '2026-11-17'], longestGapDays: 1, lastCallDate: '2026-11-17', daysSinceLastCall: 1, empty: false },
      moodTrend: { source: '機器觀察（每次通話後由沐寧記錄的心情天氣，1–5 級）', daysWithChat: 3, daily: [{ date: '2026-11-15', level: 2, chats: 1 }, { date: '2026-11-16', level: 1, chats: 1 }, { date: '2026-11-17', level: 2, chats: 1 }], weekAverage: 1.7, baselineAverage: 3.6, baselineDays: 14, lowestDay: { date: '2026-11-16', level: 1 }, empty: false },
      spokenHealth: { source: '本人口述的掛心事，只給類別與次數（不含原句與短語；由記憶層歸類、不是臨床事實）', categories: [{ key: 'sleep', label: '睡不好', count: 2 }, { key: 'other', label: '心情或生活上的掛心事', count: 1 }], empty: false },
      safety: { source: '系統紀錄', counts: {}, highOrCritical: 0, empty: true },
      honesty: { allEmpty: false, note: '' },
      partial: [],
    },
    anomalies: [{ type: 'mood_drop', when: '2026-11-17', fact: '心情連續 3 天在 2 級以下（2026-11-15、2026-11-16、2026-11-17）。', suggestion: '打個電話問候；這是觀察，不是判定。' }],
    partial: [],
    privacy: { statement: '這一頁是事實排列不是判定。' },
  };
}

function alertView(id, status, poison) {
  const tag = poison ? POISON : '';
  const history = status === 'unmarked' ? [] : [{ result: status, resultLabel: { correct: '正確', false_alarm: '誤報', watching: '觀察中' }[status], isReal: 'yes', worthNotifying: null, remark: '先前的備註' + tag, markedAt: '2026-11-17T02:00:00Z', markedBy: '林主任' + tag, markedByRole: '機構管理者' }];
  const latest = history[history.length - 1] || null;
  return {
    alertId: id, seatId: SEAT_A, seatCode: '6F1E2D3C', label: '測試阿嬤' + tag, siteLabel: '北院', type: 'mood_drop', typeLabel: '心情下降',
    when: '2026-11-17', fact: '心情連續 3 次有紀錄都在 2 級以下（2026-11-12、2026-11-15、2026-11-17，中間幾天沒有紀錄）。' + tag, suggestion: '打個電話問候；這是觀察，不是判定。' + tag,
    raisedAt: '2026-11-18T00:05:00Z', status, statusLabel: latest ? latest.resultLabel : '還沒判定', lastMark: latest, markHistory: history,
  };
}

function alertsRes(poison) {
  const list = [alertView('ALR-20261117-AAAAAA', 'unmarked', poison), alertView('ALR-20261116-BBBBBB', 'correct', poison), alertView('ALR-20261115-CCCCCC', 'watching', poison)];
  return { ok: true, count: list.length, alerts: list, counts: { unmarked: 1, correct: 1, false_alarm: 0, watching: 1 },
    accuracy: { correct: 1, falseAlarm: 0, judged: 1, rate: 1, method: '' }, scope: { siteLabel: null, siteScoped: false }, canMark: true, lookbackDays: 90, partial: [], privacy: { statement: '' } };
}

function settingsRes(canEdit) {
  return { ok: true, settings: { noContactDays: 3, updatedAt: null }, canEdit, limits: { noContactDays: [1, 30] } };
}

function auditRes(poison) {
  return { ok: true, count: 1, lookbackDays: 90, items: [{ at: '2026-11-18T01:12:00Z', action: '看了週關懷摘要', eventType: 'org_care_week_read', actor: '測試社工' + (poison ? POISON : ''), actorRole: '社工／個管', seatCode: '6F1E2D3C', result: null }] };
}

function reportsRes(poison) {
  return { ok: true, reports: { count: 1, list: [{ id: 'rep-1', period: '2026年10月' + (poison ? POISON : ''), periodStart: '2026-10-01', periodEnd: '2026-10-31', generatedAt: '2026-11-03T01:00:00Z', available: true }] },
    downloadToken: 'tok.v1.sig', downloadPath: poison ? 'javascript:alert(1)//' : '/enterprise/portal/report' };
}

function backend(role, opts = {}) {
  return function respond(p, body) {
    const over = opts.override && opts.override(p, body);
    if (over !== undefined) return over;
    if (p === '/org/me') return meFor(role, opts.poison);
    if (p === '/org/summary') return summary();
    if (p === '/org/elders') return elders(opts.poison);
    if (p === '/org/elder/care-week') return careWeek(body.seatId);
    if (p === '/org/alerts') return alertsRes(opts.poison);
    if (p === '/org/settings') return settingsRes(role === 'org_admin');
    if (p === '/org/audit') return auditRes(opts.poison);
    if (p === '/org/reports') return reportsRes(opts.poison);
    return { ok: false, error: 'not_found' };
  };
}

function jsonResponse(data, status = 200) {
  return { status, ok: status >= 200 && status < 300, json: async () => data };
}

// ───────────────────────── 把 org.js 放進假世界跑 ─────────────────────────
async function boot(url, { respond = null, token = 'test-token', src = ORG_JS, signInResult = { ok: true }, recover = null } = {}) {
  const doc = new FakeDocument();
  const app = doc.createElement('div');
  app.setAttribute('id', 'app');
  doc.body.appendChild(app);
  doc.created.length = 0;
  const u = new URL(url);
  const location = { href: u.href, origin: u.origin, pathname: u.pathname, search: u.search, hash: u.hash };
  const history = {
    replaceState(_state, _title, next) {
      const n = new URL(next, location.href);
      Object.assign(location, { href: n.href, pathname: n.pathname, search: n.search, hash: n.hash });
    },
  };
  const calls = [];
  const authCalls = [];
  const win = { document: doc, location, history, console, setTimeout, clearTimeout, URLSearchParams, URL, AbortController, innerWidth: 1280 };
  win.window = win;
  let nextFetch = null; // 測試可以指定下一次 fetch 怎麼回（例如網路斷掉）
  win.fetch = async (p, init) => {
    const body = init && init.body ? JSON.parse(init.body) : null;
    calls.push({ path: p, init, body });
    if (nextFetch) { const f = nextFetch; nextFetch = null; return f(p, body); }
    if (!respond) throw new Error('network is not allowed here');
    const data = respond(p, body || {});
    if (data && data.__status) return jsonResponse(data.body, data.__status);
    return jsonResponse(data);
  };
  const auth = {
    init: async () => ({}),
    getAccessToken: async () => token,
    recoverRejectedSession: async () => { authCalls.push('recover'); return recover; },
    signInWithProvider: async provider => { authCalls.push('signIn:' + provider); return signInResult; },
    signOut: async () => { authCalls.push('signOut'); return { ok: true }; },
    state: () => ({ email: 'staff@example.org', status: token ? 'signed-in' : 'guest' }),
  };
  doc.onScript = node => {
    const s = node.getAttribute('src');
    setImmediate(() => {
      if (s === 'src/auth-config.js') win.MUNEA_SUPABASE_CONFIG = { url: 'https://example.supabase.co', publishableKey: 'sb_publishable_test', redirectTo: u.origin + '/index.html' };
      if (s === 'src/auth.js') win.MuneaAuth = auth;
      if (typeof node.onload === 'function') node.onload();
    });
  };
  vm.createContext(win);
  vm.runInContext(src, win, { filename: 'org.js' });
  await settle();
  return { win, doc, app, calls, authCalls, failNext(fn) { nextFetch = fn; } };
}

const pathsOf = calls => calls.map(c => c.path);

(async () => {
  console.log('機構專區（照護人員登入版）');

  // ── 一、靜態：檔案、接口、後端路由 ──
  await check('org.html 只載自己的樣式與程式，不預先載登入元件', () => {
    assert.match(ORG_HTML, /<html lang="zh-Hant">/);
    assert.match(ORG_HTML, /<meta name="robots" content="noindex, nofollow">/);
    assert.match(ORG_HTML, /<meta http-equiv="Content-Security-Policy"/);
    assert.match(ORG_HTML, /<link rel="stylesheet" href="src\/org\.css">/);
    assert.match(ORG_HTML, /<script src="src\/org\.js"><\/script>/);
    assert.doesNotMatch(ORG_HTML, /<script[^>]+auth(-config)?\.js/, '登入元件要等確定不是示範模式才載');
    assert.match(ORG_HTML, /id="app"/);
  });

  await check('用到的接口都在 org.js，而且 engine/server.py 真的有接', () => {
    const posts = ['/org/me', '/org/summary', '/org/elders', '/org/elder/care-week', '/org/alerts', '/org/alert/mark', '/org/audit', '/org/reports', '/org/settings', '/org/settings/save'];
    for (const p of posts) {
      assert.ok(ORG_JS.includes("'" + p + "'"), 'org.js 沒有用到 ' + p);
      assert.ok(SERVER.includes('self.path == "' + p + '"'), 'server.py 沒有接 ' + p);
    }
    assert.ok(ORG_JS.includes("'/enterprise/portal/report'"), 'org.js 沒有月報開啟路徑');
    assert.ok(SERVER.includes('if path == "/enterprise/portal/report"'), 'server.py 沒有月報開啟路由');
    assert.equal((ORG_JS.match(/\bfetch\(/g) || []).length, 1, '只准一個地方打網路（realCall）');
  });

  await check('整支 org.js 不把字串當 HTML 塞', () => {
    for (const bad of [/\.innerHTML\b/, /\.outerHTML\b/, /insertAdjacentHTML/, /document\.write/, /\beval\(/, /new Function\(/]) {
      assert.doesNotMatch(ORG_JS, bad, 'org.js 出現 ' + bad);
    }
  });

  await check('薄門碼跟 App 同一把；品牌色照規範', () => {
    const appKey = /const MUNEA_APP_KEY = '([^']+)'/.exec(APP_JS);
    assert.ok(appKey, 'app.js 找不到 MUNEA_APP_KEY');
    assert.ok(ORG_JS.includes("'" + appKey[1] + "'"), 'org.js 的薄門碼跟 App 不一樣');
    for (const token of ['#3AA8A0', '#37A099', '#F4A261']) assert.ok(ORG_CSS.includes(token), 'org.css 少了品牌色 ' + token);
    assert.doesNotMatch(ORG_CSS, /background[^;{}]*#236C66/i, '深綠 #236C66 只能當文字強調，不能當底色');
    assert.doesNotMatch(ORG_CSS, /border-left\s*:\s*[3-9]px/i, '不用左側直條裝飾線');
  });

  await check('角色假資料跟後端 capabilities_for 一致（本機有 python 才比）', () => {
    const code = [
      'import json, org_api',
      'out = {}',
      "for key, role, kind, site in [('org_admin','org_admin','care',None),('case_manager','case_manager','care','北院'),('care_worker','care_worker','care','北院'),('esg','org_admin','esg',None)]:",
      "    out[key] = org_api.capabilities_for({'role': role, 'siteLabel': site}, {'clientKind': kind})",
      'print(json.dumps(out, ensure_ascii=False))',
    ].join('\n');
    const run = spawnSync(process.env.PYTHON || 'python', ['-c', code], { cwd: path.join(ROOT, 'engine'), encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8', MUNEA_DATABASE_PROVIDER: 'json' }, timeout: 60000 });
    if (run.error || run.status !== 0) {
      console.log('       （略過：這台機器跑不了 python ' + String(run.error || run.stderr || '').split('\n')[0].slice(0, 80) + '）');
      return;
    }
    const lines = run.stdout.trim().split('\n');
    assert.deepEqual(JSON.parse(lines[lines.length - 1]), CAPS);
  });

  // ── 二、示範模式不打網路、不載登入元件 ──
  await check('示範模式：四種角色＋登入頁＋沒有權限，從頭點到尾都不打網路', async () => {
    for (const role of ['org_admin', 'case_manager', 'care_worker', 'esg', 'guest', 'none']) {
      const w = await boot('https://admin.munea.net/org.html?demo=1&role=' + role);
      assert.ok(byClass(w.doc.body, 'demo-badge').some(b => text(b) === '示範資料'), role + ' 畫面沒有「示範資料」標籤');
      if (role === 'guest') await click(buttonsNamed(w.doc.body, '用 Google 帳號登入')[0]);
      for (const label of tabLabels(w.doc)) {
        await openTab(w.doc, label);
        if (label === '長輩') {
          const row = all(w.doc.body, el => el.tagName === 'BUTTON' && hasClass(el, 'elder-row'))[0];
          if (row) await click(row);
        }
        if (label === '提醒') {
          const judge = buttonsNamed(w.doc.body, '判定')[0];
          await click(judge);
          await click(byClass(w.doc.body, 'result-btn')[0]);
          await click(buttonsNamed(w.doc.body, '送出判定')[0]);
          const sel = w.doc.getElementById('noContactDays');
          if (sel) { sel.value = '5'; await fire(sel, 'change'); await click(buttonsNamed(w.doc.body, '儲存')[0]); }
        }
      }
      assert.deepEqual(pathsOf(w.calls), [], role + ' 示範模式打了網路');
      assert.deepEqual(w.doc.scripts, [], role + ' 示範模式載了登入元件');
      assert.deepEqual(w.doc.htmlWrites, []);
    }
  });

  await check('示範模式的提醒匣可以判定（判完卡片更新、數字跟著變）', async () => {
    const w = await boot('https://admin.munea.net/org.html?demo=1&role=case_manager#alerts');
    const before = text(byClass(w.doc.body, 'alert-stats')[0]);
    await click(buttonsNamed(w.doc.body, '判定')[0]);
    await click(byClass(w.doc.body, 'result-btn')[1]);
    await click(buttonsNamed(w.doc.body, '送出判定')[0]);
    assert.equal(byClass(w.doc.body, 'modal').length, 0, '判定成功後視窗要關');
    assert.notEqual(text(byClass(w.doc.body, 'alert-stats')[0]), before, '判定後上方數字沒變');
    assert.ok(text(w.doc.body).includes('陳社工（社工／個管） 判為 誤報'), '判定歷程沒有列出誰判了什麼');
  });

  await check('畫面沒有內部用語：守護腦、高風險燈、機器觀察、記憶層、掛心事、旗標、留存…都換成白話', async () => {
    const seen = [];
    for (const role of ['org_admin', 'case_manager']) {
      const w = await boot('https://admin.munea.net/org.html?demo=1&role=' + role);
      for (const label of tabLabels(w.doc)) {
        await openTab(w.doc, label);
        if (label === '長輩') {
          const toggle = byClass(w.doc.body, 'legend-toggle')[0];
          assert.equal(toggle.getAttribute('aria-expanded'), 'false');
          await click(toggle);
          assert.equal(toggle.getAttribute('aria-expanded'), 'true', '圖例按了沒展開');
          assert.ok(hasClass(toggle.parentNode, 'open'));
          for (const row of all(w.doc.body, el => el.tagName === 'BUTTON' && hasClass(el, 'elder-row')).slice(0, 2)) {
            await click(row);
            seen.push(text(w.doc.body));
          }
        }
        seen.push(text(w.doc.body));
      }
    }
    const pageText = seen.join('\n');
    for (const bad of ['守護腦', '高風險燈', 'high×', '機器觀察', '記憶層', '掛心事', '旗標', '留存', '人數太少不顯示', '規則', '守護提醒', '守護亮燈']) {
      assert.ok(!pageText.includes(bad), '畫面還有內部用語：' + bad);
    }
    for (const good of ['需要關心', '需要關心的次數', '持續使用', '提醒多的排前面', '本人提到的煩惱', '沐寧從通話聽出來的心情', '由系統從通話整理',
      '系統每天檢查一次，有狀況會列在這裡（近 90 天）。請逐筆判定。', '這週通話中有 2 次提到需要馬上關心的事（緊急 1 次、高風險 1 次）。', '人數太少，為保護隱私先不顯示']) {
      assert.ok(pageText.includes(good), '畫面少了：' + good);
    }
    for (const keep of ['正確', '誤報', '觀察中', '判定', '再判一次', '準確率（參考）', '名額', '機構管理者']) {
      assert.ok(pageText.includes(keep), '這幾個字要留（補助案判定表對照用）：' + keep);
    }
  });

  // ── 三、分頁只看 capabilities ──
  await check('照服員：只有總覽與長輩；名單點不進去、不會去要週摘要或提醒', async () => {
    const w = await boot('https://admin.munea.net/org.html#alerts', { respond: backend('care_worker') });
    assert.deepEqual(tabLabels(w.doc), ['總覽', '長輩']);
    assert.ok(!pathsOf(w.calls).includes('/org/alerts'), '網址帶 #alerts 也不能去要提醒');
    await openTab(w.doc, '長輩');
    const rows = byClass(w.doc.body, 'elder-row');
    assert.equal(rows.length, 2);
    for (const row of rows) {
      assert.notEqual(row.tagName, 'BUTTON', '照服員的名單不能長得像按鈕');
      assert.equal((row.listeners.click || []).length, 0, '照服員的名單不能點');
    }
    assert.equal(byClass(w.doc.body, 'detail').length, 0, '照服員不該有週摘要面板');
    assert.ok(text(w.doc.body).includes('本週關懷摘要由社工或機構管理者查看'));
    for (const p of pathsOf(w.calls)) assert.ok(['/org/me', '/org/summary', '/org/elders'].includes(p), '照服員打了 ' + p);
  });

  await check('企業窗口：只有總覽與月報', async () => {
    const w = await boot('https://admin.munea.net/org.html', { respond: backend('esg') });
    assert.deepEqual(tabLabels(w.doc), ['總覽', '月報']);
    await openTab(w.doc, '月報');
    await openTab(w.doc, '總覽');
    for (const p of pathsOf(w.calls)) assert.ok(['/org/me', '/org/summary', '/org/reports'].includes(p), '企業窗口打了 ' + p);
    assert.equal(byClass(w.doc.body, 'privacy-line').length, 0, '企業窗口的頁尾已經講了，不重複');
  });

  await check('社工：沒有紀錄分頁；「幾天沒聯絡才提醒」只顯示、沒有儲存鈕', async () => {
    const w = await boot('https://admin.munea.net/org.html#alerts', { respond: backend('case_manager') });
    assert.deepEqual(tabLabels(w.doc), ['總覽', '長輩', '提醒', '月報']);
    const bar = byClass(w.doc.body, 'setting-bar')[0];
    assert.ok(text(bar).includes('幾天沒聯絡才提醒'));
    assert.ok(text(bar).includes('3') && text(bar).includes('由機構管理者設定'));
    assert.equal(all(bar, el => el.tagName === 'SELECT').length, 0, '社工不能改天數');
    assert.equal(buttonsNamed(w.doc.body, '儲存').length, 0, '社工看得到儲存鈕');
    assert.ok(!pathsOf(w.calls).includes('/org/audit') && !pathsOf(w.calls).includes('/org/settings/save'));
  });

  // ── 四、送出的 body、錯誤的白話、送不出去不清空 ──
  await check('機構管理者：五個分頁、每次請求都帶登入證與薄門碼', async () => {
    const w = await boot('https://admin.munea.net/org.html', { respond: backend('org_admin') });
    assert.deepEqual(tabLabels(w.doc), ['總覽', '長輩', '提醒', '紀錄', '月報']);
    assert.ok(w.calls.length >= 2);
    for (const c of w.calls) {
      assert.equal(c.init.method, 'POST');
      assert.equal(c.init.headers.Authorization, 'Bearer test-token');
      assert.ok(String(c.init.headers['X-Munea-Key'] || '').startsWith('mnk_'));
      assert.equal(c.init.headers['Content-Type'], 'application/json');
    }
    assert.ok(byClass(w.doc.body, 'tab-badge').some(b => !b.hidden && text(b) === '1'), '提醒分頁要標還沒判定的筆數');
    assert.equal(byClass(w.doc.body, 'demo-badge').length, 0, '正常模式不能出現「示範資料」標籤');
  });

  await check('提醒卡：還沒判定的「判定」是實心主按鈕、判過的「再判一次」不是；名額代號與編號在最底一行', async () => {
    const w = await boot('https://admin.munea.net/org.html#alerts', { respond: backend('org_admin') });
    const cards = byClass(w.doc.body, 'alert-card');
    assert.equal(cards.length, 3);
    const judge = all(cards[0], el => el.tagName === 'BUTTON' && text(el) === '判定')[0];
    assert.ok(judge && hasClass(judge, 'btn-primary'), '還沒判定的「判定」要是實心主按鈕');
    const again = all(cards[1], el => el.tagName === 'BUTTON' && text(el) === '再判一次')[0];
    assert.ok(again && !hasClass(again, 'btn-primary'), '「再判一次」維持次要樣式');
    assert.ok(!text(byClass(cards[0], 'alert-top')[0]).includes('名額代號'), '名額代號不要跟姓名擠同一行');
    const meta = text(byClass(cards[0], 'alert-meta')[0]);
    assert.ok(meta.includes('名額代號 6F1E2D3C') && meta.includes('編號 ALR-20261117-AAAAAA'), '最底一行要有名額代號與編號：' + meta);
    assert.ok(text(w.doc.body).includes('系統每天檢查一次，有狀況會列在這裡（近 90 天）。請逐筆判定。'));
  });

  await check('判定：送不出去時視窗不關、內容不清空；成功才更新卡片與數字', async () => {
    let markMode = 'not_recorded';
    const respond = backend('org_admin', {
      override(p, body) {
        if (p !== '/org/alert/mark') return undefined;
        if (markMode === 'not_recorded') return { ok: false, error: 'mark_not_recorded' };
        if (markMode === 'alerts_unavailable') return { ok: false, error: 'alerts_unavailable' };
        const v = alertView(body.alertId, body.result);
        v.markHistory = [{ result: body.result, resultLabel: '誤報', isReal: body.isReal || null, worthNotifying: body.worthNotifying || null, remark: body.remark || '', markedAt: '2026-11-18T03:00:00Z', markedBy: '測試社工', markedByRole: '機構管理者' }];
        v.lastMark = v.markHistory[0];
        v.statusLabel = '誤報';
        return { ok: true, alert: v };
      },
    });
    const w = await boot('https://admin.munea.net/org.html#alerts', { respond });
    await click(buttonsNamed(w.doc.body, '判定')[0]);
    const modal = () => byClass(w.doc.body, 'modal')[0];
    assert.ok(modal(), '按「判定」沒有跳出視窗');
    assert.ok(text(modal()).includes('判定送出後不能修改；想改就再判一次，以最後一次為準。'));
    assert.ok(text(modal()).includes('請不要寫長輩的全名、電話、身分證或病名'), '備註框下要提醒不要寫個資');
    const submit = buttonsNamed(modal(), '送出判定')[0];
    assert.equal(submit.disabled, true, '還沒選結果就能送出');
    await click(byClass(modal(), 'result-btn').find(b => text(b).startsWith('誤報')));
    const yn = all(modal(), el => el.tagName === 'BUTTON' && el.parentNode && hasClass(el.parentNode, 'yn'));
    await click(yn[1]); // 事情是真的嗎：否
    const remark = w.doc.getElementById('markRemark');
    remark.value = '  需要   再確認  ';
    await fire(remark, 'input');

    await click(submit);
    const sent = w.calls.filter(c => c.path === '/org/alert/mark');
    assert.equal(sent.length, 1);
    assert.deepEqual(sent[0].body, { alertId: 'ALR-20261117-AAAAAA', result: 'false_alarm', isReal: 'no', remark: '需要 再確認' });
    assert.ok(modal(), '寫不進紀錄時視窗不能關');
    assert.ok(text(modal()).includes('這筆判定沒有存進紀錄，所以還不算數'), '寫不進紀錄要講白話');
    assert.equal(byClass(modal(), 'result-btn').find(b => text(b).startsWith('誤報')).getAttribute('aria-pressed'), 'true', '選好的結果被清掉');
    assert.equal(yn[1].getAttribute('aria-pressed'), 'true', '選好的「否」被清掉');
    assert.equal(remark.value, '  需要   再確認  ', '備註被清掉');
    assert.equal(submit.disabled, false, '失敗後要能再按一次');

    w.failNext(() => { throw new TypeError('Failed to fetch'); });
    await click(submit);
    assert.ok(modal(), '沒網路時視窗不能關');
    assert.ok(text(modal()).includes('連不上沐寧，這筆判定還沒送出'), '沒網路要講白話');
    assert.equal(remark.value, '  需要   再確認  ');

    markMode = 'alerts_unavailable';
    await click(submit);
    assert.ok(modal(), '提醒讀不到時視窗不能關');
    assert.ok(text(modal()).includes('提醒暫時讀不到，這筆判定還沒送出'), '提醒讀不到要講白話');
    assert.equal(remark.value, '  需要   再確認  ');

    markMode = 'ok';
    await click(submit);
    assert.equal(byClass(w.doc.body, 'modal').length, 0, '成功後視窗要關');
    const card = byClass(w.doc.body, 'alert-card')[0];
    assert.ok(text(card).includes('誤報'), '卡片狀態沒更新');
    assert.ok(text(card).includes('測試社工（機構管理者） 判為 誤報'), '卡片沒有列出判定歷程');
    const stats = byClass(w.doc.body, 'alert-stats')[0];
    assert.ok(text(stats).includes('還沒判定0') && text(stats).includes('誤報1'), '上方數字沒跟著變：' + text(stats));
    assert.ok(byClass(w.doc.body, 'tab-badge').every(b => b.hidden), '全部判完，提醒分頁的數字要收起來');
  });

  await check('只選結果、其他都不填：body 只有 alertId 與 result（沒填的不送空字串）', async () => {
    const respond = backend('org_admin', { override: (p, body) => (p === '/org/alert/mark' ? { ok: true, alert: alertView(body.alertId, body.result) } : undefined) });
    const w = await boot('https://admin.munea.net/org.html#alerts', { respond });
    await click(buttonsNamed(w.doc.body, '判定')[0]);
    const modal = byClass(w.doc.body, 'modal')[0];
    const yn = all(modal, el => el.tagName === 'BUTTON' && el.parentNode && hasClass(el.parentNode, 'yn'));
    await click(yn[0]);
    await click(yn[0]); // 再按一次＝不填
    assert.equal(yn[0].getAttribute('aria-pressed'), 'false');
    await click(byClass(modal, 'result-btn').find(b => text(b).startsWith('正確')));
    await click(buttonsNamed(modal, '送出判定')[0]);
    const sent = w.calls.filter(c => c.path === '/org/alert/mark');
    assert.deepEqual(sent[0].body, { alertId: 'ALR-20261117-AAAAAA', result: 'correct' });
  });

  await check('判定的備註最多 200 字（照字數算、不是照位元組）', async () => {
    const w = await boot('https://admin.munea.net/org.html#alerts', { respond: backend('org_admin') });
    await click(buttonsNamed(w.doc.body, '判定')[0]);
    const remark = w.doc.getElementById('markRemark');
    remark.value = '字'.repeat(250);
    await fire(remark, 'input');
    assert.equal(Array.from(remark.value).length, 200);
    assert.ok(text(byClass(w.doc.body, 'counter')[0]).includes('還可以輸入 0 字'));
  });

  await check('幾天沒聯絡才提醒：管理者改成 5 天，body 剛好是 {noContactDays: 5}，存好重讀提醒匣；存不進去不改回', async () => {
    let saveMode = 'fail';
    const respond = backend('org_admin', {
      override(p) {
        if (p !== '/org/settings/save') return undefined;
        return saveMode === 'fail' ? { ok: false, error: 'settings_not_recorded' } : { ok: true, settings: { noContactDays: 5, updatedAt: '2026-11-18T03:00:00Z' } };
      },
    });
    const w = await boot('https://admin.munea.net/org.html#alerts', { respond });
    const sel = w.doc.getElementById('noContactDays');
    assert.ok(sel, '管理者要看得到天數選單');
    assert.equal(sel.value, '3');
    const save = buttonsNamed(w.doc.body, '儲存')[0];
    assert.equal(save.disabled, true, '沒改就能按儲存');
    sel.value = '5';
    await fire(sel, 'change');
    assert.equal(save.disabled, false);
    await click(save);
    assert.ok(text(byClass(w.doc.body, 'setting-bar')[0]).includes('設定沒有存進紀錄'), '存不進去要講白話');
    assert.equal(sel.value, '5', '存不進去時選好的天數被改回');
    const alertsBefore = pathsOf(w.calls).filter(p => p === '/org/alerts').length;
    saveMode = 'ok';
    await click(save);
    const saves = w.calls.filter(c => c.path === '/org/settings/save');
    assert.equal(saves.length, 2);
    assert.deepEqual(saves[1].body, { noContactDays: 5 });
    assert.equal(typeof saves[1].body.noContactDays, 'number');
    assert.ok(pathsOf(w.calls).filter(p => p === '/org/alerts').length > alertsBefore, '存好之後要重讀提醒匣');
  });

  await check('週關懷摘要：只帶 seatId；七格心情、四類煩惱、底下寫「這次查看已留下紀錄」；來源用白話', async () => {
    const w = await boot('https://admin.munea.net/org.html#elders', { respond: backend('org_admin') });
    await click(all(w.doc.body, el => el.tagName === 'BUTTON' && hasClass(el, 'elder-row'))[0]);
    const req = w.calls.filter(c => c.path === '/org/elder/care-week');
    assert.equal(req.length, 1);
    assert.deepEqual(req[0].body, { seatId: SEAT_A });
    const detail = byClass(w.doc.body, 'detail')[0];
    assert.equal(byClass(detail, 'mood-col').length, 7);
    assert.equal(byClass(detail, 'cat').length, 4);
    assert.ok(text(detail).includes('這次查看已留下紀錄'));
    assert.ok(text(detail).includes('睡不好2次'));
    assert.ok(text(detail).includes('心情或生活上的煩惱1次'), '類別名要用畫面的白話');
    for (const word of ['機器觀察', '記憶層', '掛心事']) assert.ok(!text(detail).includes(word), '週摘要出現內部用語：' + word);
    assert.ok(text(detail).includes('沐寧從通話聽出來的心情') && text(detail).includes('由系統從通話整理'));
  });

  await check('各種錯誤都有白話：提醒、紀錄、週摘要、登入、權限', async () => {
    let w = await boot('https://admin.munea.net/org.html#alerts', { respond: backend('org_admin', { override: p => (p === '/org/alerts' ? { ok: false, error: 'alerts_unavailable' } : undefined) }) });
    assert.ok(text(w.doc.body).includes('提醒暫時讀不到'));

    w = await boot('https://admin.munea.net/org.html#audit', { respond: backend('org_admin', { override: p => (p === '/org/audit' ? { ok: false, error: 'audit_unavailable' } : undefined) }) });
    assert.ok(text(w.doc.body).includes('紀錄暫時讀不到'));

    w = await boot('https://admin.munea.net/org.html#elders', { respond: backend('org_admin', { override: p => (p === '/org/elder/care-week' ? { ok: false, error: 'audit_unavailable' } : undefined) }) });
    await click(all(w.doc.body, el => el.tagName === 'BUTTON' && hasClass(el, 'elder-row'))[0]);
    assert.ok(text(w.doc.body).includes('查看紀錄暫時寫不進去'));

    w = await boot('https://admin.munea.net/org.html', { respond: backend('org_admin', { override: p => (p === '/org/me' ? { __status: 403, body: { ok: false, error: { code: 'app_key_required' } } } : undefined) }) });
    assert.ok(text(w.doc.body).includes('這個網址目前不能使用機構專區'));
  });

  await check('沒有機構權限：顯示要找誰開通＋登出鈕；登出後回登入頁', async () => {
    const w = await boot('https://admin.munea.net/org.html', { respond: backend('org_admin', { override: p => (p === '/org/me' ? { ok: false, error: 'not_found' } : undefined) }) });
    assert.ok(text(w.doc.body).includes('這個 Google 帳號還沒有機構專區的權限。請貴單位的沐寧聯絡窗口幫你開通。'));
    await click(buttonsNamed(w.doc.body, '登出')[0]);
    assert.ok(w.authCalls.includes('signOut'));
    assert.ok(buttonsNamed(w.doc.body, '用 Google 帳號登入').length === 1, '登出後要回登入頁');
  });

  await check('沒登入：顯示登入頁；按下去用 Google 登入、回跳網址是這一頁（不帶網址參數）', async () => {
    const w = await boot('https://admin.munea.net/org.html?from=mail#alerts', { respond: backend('org_admin'), token: null });
    assert.deepEqual(w.doc.scripts, ['src/auth-config.js', 'src/auth.js']);
    assert.ok(text(w.doc.body).includes('只有機構邀請過的帳號才能進來'));
    assert.equal(byClass(w.doc.body, 'demo-badge').length, 0, '正常模式的登入頁不能出現「示範資料」');
    assert.deepEqual(pathsOf(w.calls), [], '沒登入就打了接口');
    await click(buttonsNamed(w.doc.body, '用 Google 帳號登入')[0]);
    assert.deepEqual(w.authCalls, ['signIn:google']);
    assert.equal(w.win.MUNEA_SUPABASE_CONFIG.redirectTo, 'https://admin.munea.net/org.html');
  });

  await check('登入證被拒（401）：先試著續一次，續不了就回登入頁', async () => {
    const w = await boot('https://admin.munea.net/org.html', { respond: backend('org_admin', { override: p => (p === '/org/me' ? { __status: 401, body: { ok: false, error: { code: 'auth_token_invalid' } } } : undefined) }) });
    assert.ok(w.authCalls.includes('recover'));
    assert.ok(buttonsNamed(w.doc.body, '用 Google 帳號登入').length === 1);
  });

  await check('連不上：顯示「再試一次」，按了重新要 /org/me；正常模式絕不拿示範資料頂替', async () => {
    const w = await boot('https://admin.munea.net/org.html', { respond: () => { throw new TypeError('Failed to fetch'); } });
    const body = text(w.doc.body);
    assert.ok(body.includes('連不上沐寧'));
    for (const demoWord of ['示範', '王阿嬤', '林主任']) assert.ok(!body.includes(demoWord), '正常模式出現示範資料：' + demoWord);
    const before = pathsOf(w.calls).filter(p => p === '/org/me').length;
    await click(buttonsNamed(w.doc.body, '再試一次')[0]);
    assert.ok(pathsOf(w.calls).filter(p => p === '/org/me').length > before);
  });

  // ── 五、後端字串一律當純文字 ──
  await check('後端字串夾帶 <img onerror>：每一頁都只當字顯示，沒有多長出任何元素', async () => {
    const w = await boot('https://admin.munea.net/org.html', { respond: backend('org_admin', { poison: true }) });
    for (const label of tabLabels(w.doc)) {
      await openTab(w.doc, label);
      if (label === '長輩') await click(all(w.doc.body, el => el.tagName === 'BUTTON' && hasClass(el, 'elder-row'))[0]);
      if (label === '提醒') await click(buttonsNamed(w.doc.body, '判定')[0]);
    }
    assert.deepEqual(w.doc.htmlWrites, []);
    const imgs = w.doc.created.filter(el => el.tagName === 'IMG');
    assert.ok(imgs.length > 0);
    for (const img of imgs) assert.equal(img.getAttribute('src'), 'icons/munea-logo.png', '多長出一個不是 logo 的圖：' + img.getAttribute('src'));
    assert.ok(text(w.doc.body).includes(POISON), '夾帶的字應該原樣當字顯示');
    for (const el of w.doc.created) {
      for (const [k, v] of Object.entries(el.attributes)) {
        assert.ok(!/^on/i.test(k), '長出事件屬性 ' + k);
        if (k === 'href') assert.ok(v.startsWith('/enterprise/portal/report?t='), '連結不是月報：' + v);
      }
    }
  });

  console.log('機構專區：' + passed + ' 項全過');
})().catch(err => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
