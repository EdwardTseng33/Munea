#!/usr/bin/env node
/* 家人名字畫到畫面上一定要跳脫（2026-11-18，資安預檢 D3）
 *
 * 家人名單的名字是每個人自己取的、從雲端同步到全家的手機上。
 * 以前「全家健康圈」視窗、家人頁頭像列、全家狀態清單都把名字直接接進 innerHTML——
 * 一個家人把名字取成一段 HTML，就能在其他家人的 App 裡執行程式（偷登入證、改畫面）。
 * 這支守門檢查三個畫名單的地方：名字與首字一律經過 muneaEscapeHtml。
 */
const assert = require('assert');
const fs = require('fs');

const app = fs.readFileSync('web/src/app.js', 'utf8');

function body(name) {
  const start = app.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `找不到 ${name}()`);
  const next = app.indexOf('\n  function ', start + 10);
  return app.slice(start, next > start ? next : start + 6000);
}

const roster = body('renderFcRoster');
assert.ok(!/'<b>'\s*\+\s*m\.name/.test(roster), 'renderFcRoster：名字不可以直接接進畫面');
assert.ok(!/data-name="\$\{m\.name\}"/.test(roster), 'renderFcRoster：data-name 也要跳脫');
assert.ok(/muneaEscapeHtml\(m\.name\)/.test(roster) && /muneaEscapeHtml\(m\.init\)/.test(roster),
  'renderFcRoster：名字與首字要經過 muneaEscapeHtml');

const fam = body('renderFamRoster');
for (const bad of [/data-person="'\s*\+\s*m\.name/, /'<span class="fs-name">'\s*\+\s*m\.name/, /'<div class="hr-name">'\s*\+\s*m\.name/, /'">'\s*\+\s*famInit\(m\)/]) {
  assert.ok(!bad.test(fam), `renderFamRoster：還有沒跳脫的名字（${bad}）`);
}
assert.ok((fam.match(/muneaEscapeHtml\(m\.name\)/g) || []).length >= 4, 'renderFamRoster：名字要經過 muneaEscapeHtml（頭像列＋全家狀態）');

console.log('Family names guard PASS：全家健康圈、家人頁頭像列、全家狀態清單的名字都有跳脫');
