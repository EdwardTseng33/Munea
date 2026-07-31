'use strict';
// 產生 engine/tw_district_index.py：台灣「區／鄉／鎮／市」→ 縣市 對照。
// 正本＝web/src/tw-districts.js（App 的選單也吃同一份），這裡只是把它翻成引擎讀得懂的樣子，
// 免得兩邊各養一份、日後改了一邊忘了另一邊（守門漂移的老病）。
// 用法：node scripts/gen-tw-district-index.js
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'web', 'src', 'tw-districts.js'));

const source = global.window.TW_DISTRICTS;
const seen = {};
const duplicated = new Set();
for (const county of Object.keys(source)) {
  for (const district of source[county]) {
    if (seen[district]) duplicated.add(district);
    else seen[district] = county;
  }
}
const unique = {};
for (const district of Object.keys(seen)) {
  if (!duplicated.has(district)) unique[district] = seen[district];
}

const dupList = [...duplicated].sort();
const lines = [
  '"""台灣「區／鄉／鎮／市」→ 縣市 對照（從 web/src/tw-districts.js 產生、勿手改）。',
  '',
  '用途：長輩講話常只講區不講縣市（「我住南港區興南街」），天氣要靠這張表補回縣市。',
  `刻意不收跨縣市同名的 ${dupList.length} 個（${dupList.join('、')}）——`,
  '那些猜了就可能報成別的城市的天氣，寧可回 None、讓她開口問清楚（誠實紅線）。',
  '產生方式：node scripts/gen-tw-district-index.js',
  '"""',
  '',
  'DISTRICT_TO_COUNTY = {',
];
for (const district of Object.keys(unique).sort()) {
  lines.push(`    ${JSON.stringify(district)}: ${JSON.stringify(unique[district])},`);
}
lines.push('}');
lines.push('');
lines.push(`AMBIGUOUS_DISTRICTS = frozenset({${dupList.map((d) => JSON.stringify(d)).join(', ')}})`);
lines.push('');

fs.writeFileSync(path.join(ROOT, 'engine', 'tw_district_index.py'), lines.join('\n'), 'utf8');
console.log(`tw_district_index.py: ${Object.keys(unique).length} unique districts, ${dupList.length} ambiguous`);
