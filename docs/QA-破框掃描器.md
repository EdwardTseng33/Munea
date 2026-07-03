# QA 工具 · 破框掃描器（2026-07-03 立 · 天氣條破框事件後）
用途：在手機寬度下自動找出「文字被切 / 內容超出容器」的元素——取代肉眼掃描（肉眼在寬螢幕會漏）。
用法：preview_resize 到 mobile(375) 後，於各分頁執行；捲動容器（fam-switch/hscroll/chal-types/avatar-pick/tab-bar 與 overflow-x:auto 者）排除。
判定：el.scrollWidth - el.clientWidth > 2 且有文字 → 破框。含子元素的複合膠囊也要掃（勿加「無子元素」條件——第一版因此漏掉天氣條）。
片段：見本檔同名程式段（Sophie/女巫驗收共用）。
```js
const hits=[];const OK=['fam-switch','hscroll','chal-types','avatar-pick','tab-bar'];
document.querySelectorAll('.screen.active *').forEach(el=>{if(!el.offsetParent)return;const c=String(el.className);
if(OK.some(k=>c.includes(k)))return;const cs=getComputedStyle(el);if(/auto|scroll/.test(cs.overflowX))return;
if(el.scrollWidth-el.clientWidth>2&&el.textContent.trim())hits.push(c);});
```


## v3（2026-07-04 · 誤報修正）
- **略過「有管理自己溢出」的元素**：`overflow(-x): hidden/clip`＋`text-overflow: ellipsis` 或 `-webkit-line-clamp` 的元素，內容量本來就大於盒子（裁字加省略號是設計、不是破版）——掃描時跳過，改驗「畫面盒子是否超出父卡邊界」。
- **垂直破版也要掃**：輪播/疊格類容器，逐則切換、驗每則的實際畫面盒不高出卡片底、不疊到標題。
- **文字極值必測**：任何含用戶文字的元件，交付前塞「最長合理值」與「最短值」各驗一次（例：傳話 60 字/2 字）。
