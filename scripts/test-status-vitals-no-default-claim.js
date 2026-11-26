#!/usr/bin/env node
/* 狀態頁的血壓／心率：沒有數值，就不可以有任何判斷的字（2026-11-17）
 *
 * 查到的事：沒接任何健康裝置，血壓「—」底下寫著「正常範圍內」。
 * 兩個原因疊在一起——
 *   1. 畫面檔把「正常範圍內」「穩定」「正常」寫成預設字，還掛著翻譯標籤；
 *      程式寫的「接 Apple 健康帶入」一寫上去就被翻譯層蓋回預設字。
 *   2. 程式只要有血壓數字就一律寫「正常範圍內」，沒看數字是多少。
 *
 * 對長輩說一句沒有根據的「正常」，比不說嚴重得多。這支測試擋三件事：
 *   - 這四個位置在畫面檔裡不可以有預設字、不可以掛翻譯標籤；
 *   - 兩個標籤（穩定／偏高…）預設要藏著，有真數值才由程式點亮；
 *   - 程式裡「正常範圍內」只能出現在看過數值之後（偏高、偏低各有各的說法）。
 */
const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('web/index.html', 'utf8');

function element(id) {
  const match = html.match(new RegExp(`<([a-z0-9]+)\\b([^>]*\\bid="${id}"[^>]*)>([\\s\\S]*?)</\\1>`, 'i'));
  assert.ok(match, `畫面檔找不到 #${id}`);
  return { attributes: match[2], inner: match[3] };
}

for (const id of ['bpSub', 'hrSub', 'bpChip', 'hrChip']) {
  const { attributes, inner } = element(id);
  assert.strictEqual(
    inner.trim(), '',
    `#${id} 在畫面檔裡不可以有預設字（現在是「${inner.trim()}」）——沒有數值就不該有任何判斷`,
  );
  assert.ok(
    !/\bdata-i18n=/.test(attributes),
    `#${id} 不可以掛 data-i18n：它的字由程式依數值決定`,
  );
}
for (const id of ['bpChip', 'hrChip']) {
  assert.ok(
    /display\s*:\s*none/.test(element(id).attributes),
    `#${id} 預設要藏著（display:none），有真數值才由程式點亮`,
  );
}

// 程式：不可以再有「有數字就一律正常」的寫法
assert.ok(
  !/t\.bpSys\s*\?\s*window\.muneaUiT\('status\.normalRange'/.test(html),
  '狀態頁不可以「只要有血壓數字就寫正常範圍內」——要先看數值',
);
const vitals = html.slice(html.indexOf('function vitalsOf(){'), html.indexOf('function dataFor(period){'));
assert.ok(vitals.length > 200, '找不到 vitalsOf()，這支測試的偵測方式壞了');
const normalAt = vitals.indexOf("'health.bpNormalHint'");
const judgedAt = vitals.indexOf('sys>=140||dia>=90');
assert.ok(judgedAt > 0, 'vitalsOf() 要用收縮壓／舒張壓判斷偏高（門檻跟 app.js 的 __muneaSetHealth 同一組）');
assert.ok(
  normalAt > judgedAt,
  '「正常範圍內」只能寫在看過數值之後',
);
assert.ok(/sys>0\s*&&\s*dia>0/.test(vitals), '兩個數值都有才下判斷');

// 門檻要跟 app.js 那一份一致，不然同一個數字兩處說法不同
const app = fs.readFileSync('web/src/app.js', 'utf8');
assert.ok(
  /const hi = sys >= 140 \|\| dia >= 90, lo = sys < 90;/.test(app),
  'app.js 的血壓門檻變了——狀態頁 vitalsOf() 的門檻要一起改',
);
assert.ok(/var hi=sys>=140\|\|dia>=90, lo=sys<90;/.test(vitals), '狀態頁血壓門檻要跟 app.js 一致');
assert.ok(
  /const odd = hr < 50 \|\| hr > 100;/.test(app) && /var odd=hrN<50\|\|hrN>100;/.test(vitals),
  '狀態頁心率門檻要跟 app.js 一致',
);

/* 同一天查到的另一批：畫面檔裡寫死的「示範值」，蓋掉了程式算出來的真值。
 *   趨勢卡：不管真資料多少，永遠寫「日均 7.2 時」「日均 6,800 步」「7 天準時 6/7」
 *   吃藥提醒視窗：藥名永遠是「脈優」、說明永遠是「配溫開水就可以」、永遠「已連續完成 6 天」
 *   走路活動：滑桿怎麼拉都寫「84,000 步／3 人一起走」
 *   家人圈：不管什麼方案都寫「目前 Plus 方案 · 最多 4 人」
 *   觀察卡右上角：切到 7 天／30 天仍寫「今天」
 * 這些位置的字只能由程式寫：畫面檔不留預設字、不掛翻譯標籤。
 */
for (const id of [
  'obsPeriod', 'medTrendChip', 'sleepTrendChip', 'actChip',
  'medDueSay', 'medDueName', 'medDueDesc',
  'walkGoalVal', 'goalHint', 'invLimitNote', 'tuBuyBtn',
]) {
  const { attributes, inner } = element(id);
  assert.strictEqual(inner.trim(), '', `#${id} 在畫面檔裡不可以有預設字（現在是「${inner.trim()}」）`);
  assert.ok(!/\bdata-i18n=/.test(attributes), `#${id} 不可以掛 data-i18n：它的字由程式依真資料決定`);
}
assert.ok(
  /<div class="mpc-streak" hidden>/.test(html),
  '吃藥提醒視窗的「已連續完成 N 天」預設要藏著：程式還沒有真的算連續天數',
);
assert.ok(
  !/medicationReminder\.streak[\s\S]{0,160}format\(6\)/.test(app),
  '不可以再把「已連續完成 6 天」寫死',
);
// （「脈優」在新增用藥的輸入框提示裡當範例是可以的，所以不列在這裡；藥名那一格上面已經擋了）
for (const sample of ['日均 7.2', '6,800 步', '7 天準時 6/7', '84,000 步']) {
  assert.ok(!html.includes(sample), `畫面檔裡不該再有示範值「${sample}」`);
}

console.log('Status vitals guard PASS：沒有數值時不下判斷、有數值才照數值說話；示範值不再蓋掉真值');
