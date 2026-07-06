# Munea → Claude Design 上傳交接單（任何 session 照做即可）

> ✅ **已完成（2026-07-04 13:35）**：授權打通、專案已建、35 檔全數上架。
> projectId：`9f93deab-880f-4c6d-aa98-dcdf1e41ee2a`（已記入 config.json）
> 網址：https://claude.ai/design/p/9f93deab-880f-4c6d-aa98-dcdf1e41ee2a
> 下方步驟保留作日後「重構後重傳」參照。

> 狀態：素材包已 100% 建好並本機驗證過渲染，只差「設計檔上傳授權 + 實際上傳」。
> Edward 已在 claude.ai/design 設定把「Claude Code access」切到 On（2026-07-04）。

## 素材包位置

`E:\Claude\Munea\ds-bundle\`（約 787KB，圖片全部內嵌，零外連）

內容：
- `styles.css`（@import 字體 + `_ds_bundle.css`）
- `_ds_bundle.js`（window.MuneaDS：Home / Chat / Status / Family / Settings / BrandTokens）
- `components/screens/<Name>/`（Home、Chat、Status、Family、Settings 五張畫面卡，各含 .html/.jsx/.d.ts/.prompt.md，html 首行有 `<!-- @dsCard group="Screens" -->`）
- `components/brand/BrandTokens/`（12 色票 + 字級表 + 鐵則）
- `_preview/`、`README.md`（規範表頭）、`_ds_needs_recompile`
- 注意：**沒有 `_ds_sync.json`**（畫面卡非標準元件庫、誠實選擇不留同步錨點；下次同步全量重驗即正常）

## 上傳步驟（依 /design-sync 技能的 incremental 路徑）

1. `DesignSync list_projects` — 檢查名稱不撞（注意 Edward 帳號已有一個舊專案「…寧AI照護管家應用」，**不要動它**）
2. `DesignSync create_project` name=`Munea 沐寧`（會跳權限確認）
3. 把 projectId 寫進 `E:\Claude\Munea\.design-sync\config.json`（先 pin 再上傳）
4. `DesignSync finalize_plan`：
   - localDir: `E:\Claude\Munea\ds-bundle`
   - writes: `components/**`, `_preview/**`, `_ds_bundle.js`, `_ds_bundle.css`, `styles.css`, `README.md`, `_ds_needs_recompile`（有 fonts/ tokens/ 就加上）
   - deletes: `components/**`, `_preview/**`
5. 先寫 sentinel `_ds_needs_recompile` → 傳共用底檔 + 全部畫面卡（≤256 檔/次）→ 結尾再重寫一次 sentinel
6. 給 Edward 網址 `https://claude.ai/design/p/<projectId>`

## 已知阻塞（2026-07-04 中午）

- 本 session（桌面版）呼叫 DesignSync 一律回「需要 design-system 授權、/design-login 需互動終端機」
- Edward 把 Design 設定的 Claude Code access 切 On 後**仍然同錯**（可能：本 session 的通行證是開關打開前發的，需要新 session 重新連線才拿得到新權限）
- 終端機路線：桌面上藍色 claude 視窗停在第一次啟動選主題畫面；這台 CLI 從未登入（跟桌面版分開）。走完需要 Edward 本人在視窗按 Enter→Enter→瀏覽器 Authorize
- 蘇菲的電腦操作權限對終端機是「只能點不能打」，且安全機制擋掉全部預填法——不要再試繞路

## 重構注意

狀態頁＋家人頁正在照女巫重構規格書改（規格全文：session scratchpad `witch_blueprint.txt`）。重構完成後要**重新截圖五頁、重建 ds-bundle、再上傳一次**，Design 專案才會是新設計。
