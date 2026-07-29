# 全站按鈕對比修正 · 前後證據（2026-07-24）

女巫 Gate 2 審 PR #246 時發現的兩個既有系統性問題（非該 PR 造成）的修正證據。

## 修正 1：主按鈕白字對比不足（WCAG AA 需 ≥ 4.5:1）

| 項目 | 修改前 | 修改後 |
|---|---|---|
| `--btn-green`（.video-btn / .modal-btn / .auth-primary / .seg-btn.on / .sub-cta / #topUpBtn 等全站主鈕） | `#37A099` → 白字 **3.16:1 ✗** | `#2A7E78` → 白字 **4.82:1 ✓** |
| `.consent-go` / `.auth-primary` / `.med-actions .taken`（原用 `--teal-d`） | `#2E8A83` → 白字 **4.13:1 ✗** | 統一改 `--btn-green` → **4.82:1 ✓** |

色相不變（H≈176°，同薄荷綠家族，介於 `--teal-d` 與 `--teal-dd` 之間），只加深明度。

## 修正 2：`#dataDeleteBtn` 破壞性動作樣式

- 修改前：掛著從未定義的 `.quiet`，渲染成與「匯出一份給我」相同的實心綠——破壞性動作與一般動作視覺同權。
- 修改後：新 `.modal-btn.danger`＝白底＋深紅字＋深紅描邊；按第一下的「再按一次確認」武裝態＝實心深紅白字。
- 新色票 `--danger-d: #B0392D`：白底紅字／紅底白字皆 **6.05:1 ✓**（原 `--danger #E55B4D` 只有 3.54:1，只夠大字級與圖示用）。
- 一併換用 `--danger-d`：`.cn-btn.disconnect`（中斷連結）、`.fc-leave`（退出家庭圈）兩顆小字級紅字按鈕。

## 截圖對照（390×844 @2x）

| 畫面 | 修改前 | 修改後 |
|---|---|---|
| 首頁「開始聊聊」 | home__before.png | home__after.png |
| 我的資料（匯出/刪除） | data-modal__before.png | data-modal__after.png |
| 刪除武裝態（再按一次確認） | data-modal-armed__before.png | data-modal-armed__after.png |
| 跨境同意「我知道了，開始聊」 | consent__before.png | consent__after.png |

對比值計算：WCAG 2.x relative luminance 公式（工具腳本見 PR 說明）。
