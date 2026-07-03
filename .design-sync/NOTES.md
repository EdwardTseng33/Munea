# design-sync NOTES

- 本包為 off-script「畫面參考＋色票」同步（沐寧非零件庫、無 Storybook/dist；Edward 2026-07-04 拍板範圍）。
- 畫面 HTML 由跑起來的 App 實況擷取（engine /dev/page-capture、僅本機），圖片縮 128px 內嵌。
- 標準驗證器不適用於此形態；改以本機瀏覽器逐卡目測＋女巫複驗。無 _ds_sync.json（誠實無錨、重同步全量重驗）。
