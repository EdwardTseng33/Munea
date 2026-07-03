# 沐寧 Munea · 設計約定（給設計代理）

## 這個包是什麼
四張**完整畫面參考**（Home/Status/Family/Settings，`window.MuneaDS.*`）＋一張色票規範卡（BrandTokens）。畫面是唯讀 mockup——用來對齊版型、間距、卡片語彙；設計新畫面時**照著這套語彙用一般 HTML/CSS 組**，顏色一律用 `styles.css` 裡的變數。

## 色票變數（styles.css :root 為準）
`--teal #3AA8A0`(薄荷綠主色) `--btn-green #37A099`(主按鈕) `--teal-d/-dd`(深綠文字級)
`--coral #D98841`(暮色橘) `--coral-d`(暮橘深字) `--gold #E0B354`(限成就)
`--ink #3A352E`(石墨黑內文) `--muted`(說明灰) `--cream #F4F0E8`(頁底) `--mint/--mint-2`(薄荷霧面)
`--line #EAE3D6`(細線) `--deep #36423E`(石墨綠深卡模板) `--surface #FFF`

## 卡片語彙
白卡＋`1px solid var(--line)`＋極淡影(`--shadow-sm`)；圓角 `--radius(-sm/-md/-lg/-xl)`＝14/18/20/22/24。深色強調卡只用 `--deep`。行動入口列＝52px 高、左色章(薄荷霧底)＋標題＋右箭頭。

## 老闆鐵則（違反=退件）
不用左側/直立裝飾線；不用遮罩；不用照片角落狀態點；淡色字不配淡色底；能點的要像按鈕；省略號是保險不是設計（標籤≤4字、標題單行設計成放得下）；主按鈕薄荷綠實心白字、次按鈕白底描邊；「使用中」類狀態＝名稱旁輕盈描邊小籤；暖金限成就。

## 範例
```jsx
<div style={{background:'var(--surface)',border:'1px solid var(--line)',borderRadius:18,padding:16}}>
  <b style={{fontSize:16,color:'var(--ink)'}}>卡片標題</b>
  <p style={{fontSize:14,color:'var(--ink-2)'}}>內文…</p>
  <button style={{background:'var(--btn-green)',color:'#fff',border:'none',borderRadius:16,minHeight:50,fontWeight:800}}>主行動</button>
</div>
```
