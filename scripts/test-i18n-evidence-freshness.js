'use strict';

// ── 全套畫面證據「新鮮度」關卡（只在打包出貨前強制）─────────────────────────────
// 2026-07-30 Edward 拍板：平常開發不必每次改版重拍 456 張——動到哪個畫面，
// 用 capture 工具的 --states/--locales/--profiles 只截那幾張自行驗收即可。
// 但打包出貨前，留存的全套證據必須「跟得上目前的畫面原始碼」，也就是：
//   ① 證據是在乾淨工作區拍的（拍攝當下沒有未存檔的改動）
//   ② 拍攝的存檔點之後，畫面原始碼（web/）與拍攝工具都沒再變過
//   ③ 現在的工作區對這些路徑也是乾淨的
// 三條有任何一條不成立＝先重拍全套（node scripts/app-full-surface-i18n-browser-precheck.js）再打包。
// 本檔只掛在 package.json 的 test:launch（打包套餐）；test:ui-contracts 平常不會拉到它。

const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const REPORT_PATH = path.join(
  ROOT,
  'docs',
  'qa',
  'i18n',
  'local-browser-precheck',
  'full-surface-all-profiles-2026-07-29',
  'full-surface-all-profiles-local-browser-precheck.json',
);
const report = JSON.parse(fs.readFileSync(REPORT_PATH, 'utf8'));
const evidenceSourcePaths = [
  'web',
  'scripts/app-full-surface-i18n-browser-precheck.js',
  'scripts/app-i18n-fixture-server.js',
];

function gitLines(args) {
  return execFileSync('git', args, {
    cwd: ROOT,
    encoding: 'utf8',
  }).trim().split(/\r?\n/u).filter(Boolean);
}

assert.deepEqual(
  report.sourceChangedFiles,
  [],
  'Browser evidence captured from a dirty worktree cannot certify the App source',
);
assert.deepEqual(
  gitLines(['diff', '--name-only', report.sourceBaseCommit, '--', ...evidenceSourcePaths]),
  [],
  'Browser evidence is stale because shipping WebView or capture source changed — rerun the full capture before packaging',
);
assert.deepEqual(
  gitLines(['status', '--short', '--untracked-files=all', '--', ...evidenceSourcePaths]),
  [],
  'Browser evidence cannot pass with uncommitted shipping WebView or capture source changes',
);

process.stdout.write(
  `i18n evidence freshness PASS: full-surface evidence is current with ${report.sourceBaseCommit.slice(0, 8)}.\n`,
);
