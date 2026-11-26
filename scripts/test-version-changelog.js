#!/usr/bin/env node
/* 「版本更新」畫面只能出現寫給用戶看的話（2026-11-17）
 *
 * 事故：web/src/version.js 的 changelog 會原樣顯示在 App「設定 → 版本更新」。
 * 發布小工具 scripts/appstore/set-ios-release-version.mjs 每次自動補一筆時，把
 * 「本筆由 iOS 發布流程自動建立以保持版號一致；完整更新內容請於合併前人工補上。」
 * 寫進 items——1.0.70、1.0.71 的用戶都看到了這句內部作業的話。同一支工具判斷
 * 「這個版號記過了沒」的規則又寫壞（永遠判定沒記過），1.0.71 因此重複出現兩筆。
 *
 * 這支守兩件事：
 *   A. version.js 現在的內容：用戶看得到的字沒有內部詞、同一版號只有一筆。
 *   B. 發布小工具：在暫存資料夾真的跑（有更新說明／沒有更新說明／同版號重跑），
 *      寫出來的東西一樣乾淨、不重複，而且版號一致性檢查照樣過。
 *
 * 跑法：node scripts/test-version-changelog.js（不需網路、不需鑰匙）
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');
const { spawnSync } = require('child_process');
const { inspectReleaseConsistency } = require('./check-release-consistency.js');

const root = path.resolve(__dirname, '..');
const tool = path.join(root, 'scripts', 'appstore', 'set-ios-release-version.mjs');

// 內部作業用語：出現在 title／items 就等於給用戶看到後台的話。
const INTERNAL_WORDS = /發布流程|發佈流程|合併前|人工補上|自動建立|最小紀錄|保持版號一致/;
// 發布小工具「新寫進去」的東西再多擋一層（Build 號、PR、單號、內部人名）。
// 這層先不套用到整份 version.js：7 月開發期的舊紀錄（v1.0.4–v1.0.11 等約 10 筆）還留著
// 「Build 16」「供 Edward 驗證」這類字眼，要不要整批改寫是文案決定，另案處理。
const INTERNAL_WORDS_FOR_NEW_ENTRIES = /發布流程|發佈流程|合併前|人工補上|自動建立|最小紀錄|保持版號一致|\bBuild\s*\d+|\bPR\b|#\d{2,}|Edward/i;

function loadVersion(source) {
  const sandbox = { window: {}, document: { readyState: 'complete', getElementById() { return null; }, addEventListener() {} } };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  assert(sandbox.window.MuneaVersion && Array.isArray(sandbox.window.MuneaVersion.changelog),
    'version.js 沒有掛出 window.MuneaVersion.changelog');
  return sandbox.window.MuneaVersion;
}

function assertUserFacingClean(version, label, pattern = INTERNAL_WORDS) {
  const seen = new Map();
  version.changelog.forEach((release, index) => {
    const where = `${label} 第 ${index + 1} 筆（v${release.version}）`;
    assert(typeof release.version === 'string' && /^\d+\.\d+\.\d+$/.test(release.version), `${where} 版號格式不對`);
    // 同一版號、同一標題出現兩次＝同一筆被重複寫入（1.0.71 的情況）。
    // 7 月的 v1.2.1 有兩筆「內容不同」的手寫紀錄，那不是重複，不擋。
    const identity = `${release.version}|${release.title || ''}`;
    assert(!seen.has(identity),
      `${label} 的 v${release.version} 同一筆重複出現（第 ${seen.get(identity)} 筆與第 ${index + 1} 筆）——同一筆只留一次`);
    seen.set(identity, index + 1);
    assert(Array.isArray(release.items), `${where} 的 items 必須是陣列`);
    const visible = [release.title || ''].concat(release.items);
    visible.forEach(text => {
      assert(typeof text === 'string', `${where} 有不是文字的項目`);
      const hit = text.match(pattern);
      assert(!hit, `${where} 把內部作業的話「${hit && hit[0]}」寫進用戶看得到的地方：${text}`);
    });
  });
  assert.strictEqual(version.changelog[0].version, version.current, `${label} 最上面那筆必須是目前版號 ${version.current}`);
}

// ---------- A. 現在的 version.js ----------
const liveVersion = loadVersion(fs.readFileSync(path.join(root, 'web', 'src', 'version.js'), 'utf8'));
assertUserFacingClean(liveVersion, 'web/src/version.js');

// ---------- B. 發布小工具實跑 ----------
function makeFixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'munea-version-changelog-'));
  fs.mkdirSync(path.join(dir, 'web', 'src'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'ios', 'App', 'App.xcodeproj'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'app-store', 'localizations'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'package.json'), JSON.stringify({ name: 'fixture', version: '1.0.0' }));
  fs.writeFileSync(path.join(dir, 'package-lock.json'), JSON.stringify({ version: '1.0.0', packages: { '': { version: '1.0.0' } } }));
  // 跟真檔同一種排版（冒號後有空格、單引號）——舊的判斷規則就是敗在這個空格上。
  fs.writeFileSync(path.join(dir, 'web', 'src', 'version.js'), [
    'window.MuneaVersion = {',
    "  current: '1.0.0',",
    '  changelog: [',
    '    {',
    "      version: '1.0.0',",
    "      date: '2026-07-06',",
    "      title: '第一個測試版',",
    "      items: ['寧寧可以真的開口'],",
    '    },',
    '  ],',
    '};',
    '',
  ].join('\n'));
  fs.writeFileSync(path.join(dir, 'ios', 'App', 'App.xcodeproj', 'project.pbxproj'),
    'MARKETING_VERSION = 1.0.0; CURRENT_PROJECT_VERSION = 1;\nMARKETING_VERSION = 1.0.0; CURRENT_PROJECT_VERSION = 1;\n');
  fs.writeFileSync(path.join(dir, 'app-store', 'localizations', 'zh-Hant.json'),
    JSON.stringify({ whatsNew: '通話更穩定；個人資料可以設定「希望 AI 怎麼叫你」。' }));
  return dir;
}

function runTool(dir, args) {
  const result = spawnSync(process.execPath, [tool, '--root', dir].concat(args), { encoding: 'utf8' });
  assert.strictEqual(result.status, 0, `發布小工具執行失敗：${result.stdout}\n${result.stderr}`);
  return loadVersion(fs.readFileSync(path.join(dir, 'web', 'src', 'version.js'), 'utf8'));
}

const fixture = makeFixture();
try {
  // 1) 有更新說明：新增一筆，標題＝更新說明，沒有內部詞
  let version = runTool(fixture, ['--version', '1.0.1', '--build', '2', '--whats-new-file', 'app-store/localizations/zh-Hant.json']);
  assertUserFacingClean(version, '小工具（有更新說明）', INTERNAL_WORDS_FOR_NEW_ENTRIES);
  assert.strictEqual(version.current, '1.0.1');
  assert.strictEqual(version.changelog.length, 2);
  assert.strictEqual(version.changelog[0].title, '通話更穩定；個人資料可以設定「希望 AI 怎麼叫你」。');
  assert.deepStrictEqual(Array.from(version.changelog[0].items), [], '自動建立的那筆不可以帶任何預設項目文字');

  // 2) 同一個版號再跑一次（重新打包、換 Build）：不可以再補一筆
  version = runTool(fixture, ['--version', '1.0.1', '--build', '3', '--whats-new-file', 'app-store/localizations/zh-Hant.json']);
  assertUserFacingClean(version, '小工具（同版號重跑）', INTERNAL_WORDS_FOR_NEW_ENTRIES);
  assert.strictEqual(version.changelog.filter(release => release.version === '1.0.1').length, 1,
    '同一個版號重跑發布小工具，changelog 又多了一筆（1.0.71 重複兩筆就是這樣來的）');

  // 3) 沒有更新說明：標題留空白，不拿內部的話墊檔
  version = runTool(fixture, ['--version', '1.0.2', '--build', '4']);
  assertUserFacingClean(version, '小工具（沒有更新說明）', INTERNAL_WORDS_FOR_NEW_ENTRIES);
  assert.strictEqual(version.changelog[0].version, '1.0.2');
  assert.strictEqual(version.changelog[0].title, '', '沒有更新說明時標題要留空白');

  // 4) 產出的檔案仍通過版號一致性檢查（發布流程下一步就是跑這個）
  const report = inspectReleaseConsistency({ root: fixture, strictIos: true });
  assert.strictEqual(report.ok, true, `版號一致性檢查沒過：${JSON.stringify(report.errors)}`);
  assert.strictEqual(report.sourceVersion, '1.0.2');
  assert.strictEqual(report.iosBuild, '4');

  // 5) 內部備註只能以註解形式存在（註解不會顯示在 App 裡）
  const written = fs.readFileSync(path.join(fixture, 'web', 'src', 'version.js'), 'utf8');
  written.split('\n').filter(line => INTERNAL_WORDS_FOR_NEW_ENTRIES.test(line)).forEach(line => {
    assert(/^\s*\/\//.test(line), `小工具把內部備註寫在註解以外的地方：${line.trim()}`);
  });
} finally {
  fs.rmSync(fixture, { recursive: true, force: true });
}

console.log(`Version changelog OK: web/src/version.js ${liveVersion.changelog.length} 筆更新紀錄沒有內部作業用語、沒有重複寫入的同一筆；` +
  '發布小工具實跑三種情況（有更新說明／同版號重跑／沒有更新說明）都不寫內部的話、不重複補筆，版號一致性檢查照過');
