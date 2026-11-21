# 寧寧三層動畫素材產線（2026-10-26）

純色塊寧寧 → 身體／頭／五官三層＋嘴兩段＋閉眼＋桌子＋臉範圍遮罩，給 `web/src/companion-face.js` 用。

1. 底圖：`gen_gemini.py`（鑰匙讀 `engine/.env.local` 的 GEMINI_API_KEY）。距離感靠「縮小貼到同色背景＋桌子往下延伸」自己做，Gemini 不肯把人畫小。
2. 零件：對底圖做「只改嘴／只改眼」的修圖（提示詞要寫其他地方分毫不動）。
3. 拆層：`python build_rig.py <底圖> <零件資料夾> <輸出資料夾> rig-b-far.json`——印出 `rest-pose max diff 0` 才算拆對（不動時疊回去跟原圖一模一樣）。
4. 轉成 WebP 放 `web/avatars/ningning-rig/`。
5. 驗收影片：`NOHOME=1 node demo-video.js <本機網址> <輸出資料夾>` 逐格算畫面，再用 ffmpeg 配 `ning-story.wav`。

素材原圖在 `E:\Claude\image-assets\munea-ningning-rivestyle\far\s76\`。

## 表情與多嘴型（2026-11-21 草稿，待 Edward 看影片）

現役寧寧（盤髮米色外套）原圖在 `E:\Claude\image-assets\munea-ningning-rivestyle\lily\l2\base.png`（s76 是 10/26 的舊版短髮，別拿錯）。

1. 修圖：`python gen_gemini.py <輸出.png> <提示詞> --size 2K <l2/base.png>`——**一定要帶 `--size 2K`**，不帶會出半解析度（768×1376）。提示詞在 `lily/l2-expr/edit-*.txt`，一律「只改嘴／只改眼／只改眉，其他分毫不動」。
2. 切貼片：`python build_expr.py <l2/base.png> <l2-expr> ../../web/avatars/ningning-rig rig-updo.json`——每張印「範圍外改到 0 像素」才算對；檢查圖寫到 `l2-expr/_expr-check.jpg`。
3. 嘴形資料：`node expr-track.js <聲音.wav> <track.json>`（母音嘴型驅動器 `lipsync-driver.js`，從試驗室分支原樣搬來）。
4. 影片：本機開 `web/` 靜態伺服器，`MODE=new node expr-demo-video.js <網址> <輸出資料夾> <track.json>`；`MODE=current` 用主線原本的臉當對照。
