'use strict';

/**
 * 啟動頁品牌字守門（2026-08-10 立）
 *
 * 「Munea 沐寧」是標誌的一部分，四個語系都顯示同一組字——跟官網 app-site/warm.css
 * 的 .logo / .logo-word b / .logo-zh 完全一致。它不是待翻譯的文案：
 *
 *   - 綁 app.shortName 會炸：那個鍵在英日西是 "Munea"，接在 "Mu"+"nea" 後面會變成
 *     畫面上出現兩次 Munea。
 *   - 不綁任何鍵、又不入冊，i18n 搬遷守門會亮紅（新中文一律要有去處）。
 *
 * 所以它誠實登記在 docs/I18N-NON-USER-FACING-REVIEW.json 的 brand-proper-noun，
 * 由這支測試當證據，同時把最容易漏掉的那條規格釘死：**nea 是薄荷綠、不是墨綠**。
 */

const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('web/index.html', 'utf8');
const css = fs.readFileSync('web/src/styles.css', 'utf8');
const review = JSON.parse(fs.readFileSync('docs/I18N-NON-USER-FACING-REVIEW.json', 'utf8'));

// ① 結構：品牌字照官網的三段寫法，Mu／nea／沐寧 各自分開
const lockup = html.match(/<div class="boot-word">([\s\S]*?)<\/div>/);
assert(lockup, '啟動頁必須有 .boot-word 品牌字');
assert(
  /^Mu<b>nea<\/b><span class="boot-zh">沐寧<\/span>$/.test(lockup[1].trim()),
  '品牌字必須照官網寫法：Mu<b>nea</b><span class="boot-zh">沐寧</span>',
);

// ② 不得綁任何文案鍵——四語都顯示同一組字才是標誌
assert(
  !/class="boot-word"[^>]*data-i18n/.test(html) && !/class="boot-zh"[^>]*data-i18n/.test(html),
  '品牌字不得綁 data-i18n（綁 app.shortName 會讓英日西畫面出現兩次 Munea）',
);

// ③ 顏色規格：nea 是薄荷綠，這條最容易在改版時被抹平
assert(/\.boot-word b\s*\{[^}]*color:\s*var\(--teal\)/.test(css), '.boot-word b 必須是薄荷綠 var(--teal)');
assert(/\.boot-word\s*\{[^}]*color:\s*var\(--ink\)/.test(css), '.boot-word 整組必須是墨綠 var(--ink)');
assert(/\.boot-word\s*\{[^}]*font-family:\s*var\(--display\)/.test(css), '.boot-word 必須用 Poppins（var(--display)）');
assert(/\.boot-zh\s*\{[^}]*font-size:\s*\.78em/.test(css), '.boot-zh 必須是 0.78 倍字級（照官網 .logo-zh）');

// ④ 入冊紀錄要對得上，不然搬遷守門會亮紅
const entry = review.entries.find((e) => e.id === 'brand-lockup-boot-splash-zh');
assert(entry, 'docs/I18N-NON-USER-FACING-REVIEW.json 必須登記啟動頁品牌字');
assert.equal(entry.path, 'web/index.html');
assert.equal(entry.text, '沐寧');
assert.equal(entry.reasonCode, 'brand-proper-noun');
assert.equal(entry.evidence, 'scripts/test-brand-lockup-not-translated.js');

const occurrences = (lockup[1].match(/沐寧/g) || []).length;
assert.equal(
  entry.expectedOccurrences,
  occurrences,
  `入冊的次數(${entry.expectedOccurrences})要跟品牌字裡實際出現的次數(${occurrences})一致`,
);

console.log('PASS: brand lockup stays untranslated across all locales');
