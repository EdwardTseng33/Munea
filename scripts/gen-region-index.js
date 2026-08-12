'use strict';
// 產生 engine/region_index.py：五國「地名 → 一級行政區＋經緯度」對照。
//
// 用途：長輩講話只會講地名，不會報座標——「我住南港區興南街」「世田谷区に住んでる」。
// 引擎要把這種話對回一個查得到天氣的地方（台灣走中央氣象署的縣市名、其他國家走經緯度）。
//
// 正本＝web/src/tw-districts.js 與 web/src/regions/*.js（App 那側原本就吃這幾份），
// 這裡只是翻成引擎讀得懂的樣子，免得兩邊各養一份、改了一邊忘了另一邊。
//
// 刻意不收「跨行政區同名」的地名（台北台中都有大安區、日本好幾個縣都有中央区）——
// 猜錯會讓她每天報成別的城市的天氣，而且長輩不會知道為什麼。寧可回 None、讓她開口問。
//
// 用法：node scripts/gen-region-index.js
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
global.window = {};
require(path.join(ROOT, 'web', 'src', 'tw-districts.js'));
for (const file of ['jp', 'es', 'us', 'gb']) {
  require(path.join(ROOT, 'web', 'src', 'regions', `${file}.js`));
}

const books = global.window.MUNEA_REGIONS;
const countries = Object.keys(books).sort();

const py = [
  '"""五國「地名 → 一級行政區＋經緯度」對照（自動產生、勿手改）。',
  '',
  '正本＝web/src/tw-districts.js 與 web/src/regions/*.js。',
  '長輩只會講地名，這張表把地名對回查得到天氣的地方；跨行政區同名的不收（猜錯＝報錯城市）。',
  '產生方式：node scripts/gen-region-index.js',
  '"""',
  '',
  'REGIONS = {',
];

let totalTier1 = 0;
let totalTier2 = 0;
let totalAmbiguous = 0;

for (const cc of countries) {
  const book = books[cc];
  const regions = book.regions;
  const tier1 = Object.keys(regions).sort();
  totalTier1 += tier1.length;

  // 二級地名 → 一級；跨一級同名的剔除
  const seen = {};
  const duplicated = new Set();
  for (const region of tier1) {
    for (const city of regions[region].cities || []) {
      if (seen[city] && seen[city] !== region) duplicated.add(city);
      else seen[city] = region;
    }
  }
  const cityIndex = {};
  for (const city of Object.keys(seen)) {
    if (!duplicated.has(city)) cityIndex[city] = seen[city];
  }
  totalTier2 += Object.keys(cityIndex).length;
  totalAmbiguous += duplicated.size;

  py.push(`    ${JSON.stringify(cc)}: {`);
  py.push('        "tier1": {');
  for (const region of tier1) {
    const coords = regions[region].coords;
    const value = coords ? `(${coords[0]}, ${coords[1]})` : 'None';
    py.push(`            ${JSON.stringify(region)}: ${value},`);
  }
  py.push('        },');
  py.push('        "tier2_to_tier1": {');
  for (const city of Object.keys(cityIndex).sort()) {
    py.push(`            ${JSON.stringify(city)}: ${JSON.stringify(cityIndex[city])},`);
  }
  py.push('        },');
  py.push('        "ambiguous": frozenset({'
    + [...duplicated].sort().map((c) => JSON.stringify(c)).join(', ')
    + '}),');
  py.push('    },');
}
py.push('}');
py.push('');

fs.writeFileSync(path.join(ROOT, 'engine', 'region_index.py'), py.join('\n'), 'utf8');
console.log(
  `region_index.py: ${countries.length} countries, ${totalTier1} tier-1, `
  + `${totalTier2} tier-2 (${totalAmbiguous} ambiguous names skipped)`,
);
