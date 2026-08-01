#!/usr/bin/env node
/* 心情從「他點下去」到「家人看得到」這條路上不可以被塞錯桶（Edward 2026-08-01）
 *
 * 情緒球送出的是使用者點的原字（開心／愉悅／平靜／低落／焦慮／生氣），雲端原樣存、原樣回。
 * 家人頁另有一套粗標籤（隱私線：家人只看得到「開心／平穩」這種詞，看不到聊了什麼）。
 * 兩套詞之間靠 MOOD_ZH2KEY 對照——對不上就 || 'calm'，於是他點焦慮、家人看到「平穩」。
 *
 * 這支測試把兩張表對一次，任何一個心情掉進 fallback 就紅。
 * 另外釘死「焦慮」與「生氣」必須分開：一個是他不安、一個是他被惹毛，
 * 對想關心他的家人來說是完全不同的訊號。
 */
const fs = require('fs');
const src = fs.readFileSync('web/src/app.js', 'utf8');
const html = fs.readFileSync('web/index.html', 'utf8');

// 情緒球實際送出去的六個詞（index.html 的 MOODS 表）
const orbWords = [...html.matchAll(/\{k:'([^']+)',c:'#/g)].map(m => m[1]);
// 家人頁的對照表
const mapBlock = src.match(/const MOOD_ZH2KEY = \{[\s\S]*?\};/)[0];
const map = {};
[...mapBlock.matchAll(/'([^']+)':\s*'([^']+)'/g)].forEach(m => { map[m[1]] = m[2]; });
// 家人頁認得的粗標籤
const moodsBlock = src.match(/const MOODS = \{[\s\S]*?\n\};/)[0];
const known = [...moodsBlock.matchAll(/^\s{2}(\w+):\s*\{/gm)].map(m => m[1]);

console.log('情緒球送出的詞：' + orbWords.join('、'));
console.log('家人頁的桶：' + known.join('、'));
console.log('');
let bad = 0;
orbWords.forEach(w => {
  const key = map[w];
  const ok = !!key && known.includes(key);
  if (!ok) bad++;
  console.log((ok ? 'OK   ' : '✗    ') + w + ' → ' + (key || '(對不上，會被當成 calm＝平穩)'));
});
console.log('');
/* 真正要守的是「家人看到的字」＝「他點的字」。
 * 只檢查桶不同是不夠的：把「生氣」丟進 upset 桶，桶還是不同，但家人看到的是「煩躁」。
 * 所以一路走到 famMoodFor 的標籤鍵，再回頭比對繁中文案表。 */
const famLabelBlock = src.match(/const moodKey = \{[\s\S]*?\}\[m\.key\];/)[0];
const famLabel = {};
[...famLabelBlock.matchAll(/(\w+):\s*'([^']+)'/g)].forEach(m => { famLabel[m[1]] = m[2]; });
const zh = JSON.parse(fs.readFileSync('web/src/i18n/zh-TW.json', 'utf8'));

orbWords.forEach(w => {
  const key = famLabel[map[w]];
  const shown = key ? zh[key] : undefined;
  const ok = shown === w;
  if (!ok) bad++;
  console.log((ok ? 'OK   ' : '✗    ') + '他點「' + w + '」→ 家人看到「' + (shown || '(對不上)') + '」');
});
process.exit(bad ? 1 : 0);
