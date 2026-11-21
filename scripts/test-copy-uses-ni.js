#!/usr/bin/env node
/* App 的繁中文案一律用「你」，不用「您」（2026-11-17）
 *
 * 全 App 的口吻規矩是「你」（像家人講話，不是客服）。設定頁「回診提醒」的小字
 * 一度寫成「就診當天提醒您」，跟其他幾百句不一致。
 *
 * 檢查範圍：繁中文案檔、App 主畫面、App 端程式裡寫死的中文。
 * 不檢查：法律條款頁（web/legal、terms、privacy）——正式條文的用字不歸這條規矩管。
 *
 * 跑法：node scripts/test-copy-uses-ni.js
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = relativePath => fs.readFileSync(path.join(root, relativePath), 'utf8');
const problems = [];

// 1) 繁中文案檔：逐鍵檢查
const zh = JSON.parse(read('web/src/i18n/zh-TW.json'));
let checkedKeys = 0;
for (const [key, value] of Object.entries(zh)) {
  if (typeof value !== 'string') continue;
  checkedKeys++;
  if (value.includes('您')) problems.push(`web/src/i18n/zh-TW.json「${key}」：${value}`);
}
assert(checkedKeys > 500, `zh-TW.json 只讀到 ${checkedKeys} 句，檔案格式可能變了`);
assert.strictEqual(zh['settings.appointmentRemindersSubtitle'], '就診當天提醒你');

// 2) App 主畫面與 App 端程式（含畫面上寫死的預設字）
const sources = ['web/index.html', 'web/onboarding.html'];
for (const dir of ['web/src', 'web/src/i18n']) {
  for (const name of fs.readdirSync(path.join(root, dir))) {
    if (!name.endsWith('.js')) continue;
    if (name === 'auth-config.js') continue;        // 產生檔、不入庫
    if (/^admin/.test(name)) continue;              // 後台主控台不是用戶畫面
    sources.push(`${dir}/${name}`);
  }
}
for (const relativePath of sources) {
  if (!fs.existsSync(path.join(root, relativePath))) continue;
  read(relativePath).split('\n').forEach((line, index) => {
    if (!line.includes('您')) return;
    const at = line.indexOf('您');
    problems.push(`${relativePath}:${index + 1}：…${line.slice(Math.max(0, at - 24), at + 12).trim()}…`);
  });
}

assert.deepStrictEqual(problems, [], `App 文案出現「您」（規矩是用「你」）：\n  ${problems.join('\n  ')}`);
console.log(`Copy tone OK: 繁中文案 ${checkedKeys} 句、${sources.length} 個 App 畫面與程式檔都沒有「您」（法律條款頁不在檢查範圍）`);
