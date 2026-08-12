'use strict';
// 啟動頁接開場頁不准閃到 App 首頁 · 守門測試（2026-08-10）
//
// Edward 真機回報：「品牌啟動頁完成後應該會直接接上 onboarding 頁，
// 但是這中間會閃現 app 頁面才到 onboarding 頁。」
//
// 原因是兩件事湊在一起：
//   ① 開場頁等啟動頁「淡出跑完 500ms」才顯示 —— 那半秒底下露出來的就是 App 首頁
//   ② 兩層 z-index 都是 90，而開場頁在畫面檔裡排比較後面 —— 同高時後面的蓋前面，
//      所以就算提早顯示開場頁，它也會直接蓋掉還在淡出的啟動頁，動畫等於沒播
//
// 修法必須兩件一起：開場頁在「開始淡出之前」就鋪好，且啟動頁要墊高一階。
// 實測（無視窗 Chrome，在淡出中途抽問畫面）：
//   修之前 開場頁還藏著=true   ← 露出 App 首頁
//   修之後 開場頁還藏著=false  ← 露出開場頁
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const APP_JS = fs.readFileSync(path.join(ROOT, 'web', 'src', 'app.js'), 'utf8');
const CSS = fs.readFileSync(path.join(ROOT, 'web', 'src', 'styles.css'), 'utf8');
const HTML = fs.readFileSync(path.join(ROOT, 'web', 'index.html'), 'utf8');

let failed = 0;
function check(name, ok, hint) {
  if (ok) { console.log('  OK  ' + name); return; }
  failed += 1;
  console.error('  紅  ' + name + (hint ? '\n      ' + hint : ''));
}

// ── ① 開場頁要在淡出「之前」鋪好 ──────────────────────────────────────────
const bootFn = APP_JS.slice(APP_JS.indexOf('function runBootSplash'));
const body = bootFn.slice(0, bootFn.indexOf('\n}\n') + 3);
const posOpen = body.indexOf('openOnboardingIntro()');
const posLeave = body.indexOf("classList.add('is-leaving')");

check('開場頁在啟動頁開始淡出之前就顯示',
  posOpen !== -1 && posLeave !== -1 && posOpen < posLeave,
  '又改回「淡出跑完才顯示開場頁」了——那半秒會露出 App 首頁');

// 淡出結束的那個 setTimeout 裡不可以再有 openOnboardingIntro
const tail = body.slice(posLeave);
check('淡出結束後不再重複開一次開場頁',
  tail.indexOf('openOnboardingIntro()') === -1,
  '開場頁被開兩次，捲動位置會被重設');

// ── ② 啟動頁要疊在開場頁上面 ─────────────────────────────────────────────
function zIndexOf(selector) {
  // 抓「最後一次」宣告，後面的會覆蓋前面的
  const re = new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') +
    '[^{}]*\\{[^}]*?z-index:\\s*(\\d+)', 'g');
  let m, last = null;
  while ((m = re.exec(CSS)) !== null) last = Number(m[1]);
  return last;
}
const zSplash = zIndexOf('.boot-splash');
const zOnb = zIndexOf('.onb');
check('啟動頁層級比開場頁高',
  zSplash !== null && zOnb !== null && zSplash > zOnb,
  `啟動頁 z-index=${zSplash}、開場頁 z-index=${zOnb}；同高或更低的話，` +
  '排在後面的開場頁會直接蓋掉還在淡出的啟動頁');

// ── ③ 這個修法建立在「開場頁排在啟動頁後面」這件事上，順序換了要重想 ────────
check('畫面檔裡啟動頁仍排在開場頁前面',
  HTML.indexOf('id="bootSplash"') < HTML.indexOf('id="onboarding"'),
  '兩塊的前後順序被調換了——層級的假設要重新確認');

// ── ④ 開場頁預設仍要是藏起來的（不然一開 App 就擋住整個畫面）──────────────
check('開場頁在畫面檔裡預設是藏起來的',
  /<div class="onb" id="onboarding" hidden>/.test(HTML),
  '開場頁預設顯示會擋住整個 App，也會癱瘓截圖驗收工具');

console.log(failed ? `\n${failed} 項沒過` : '\n啟動頁 → 開場頁 · 守門全過');
process.exit(failed ? 1 : 0);
