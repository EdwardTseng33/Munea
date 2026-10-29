# 寧寧三層動畫素材產線（2026-10-26）

純色塊寧寧 → 身體／頭／五官三層＋嘴兩段＋閉眼＋桌子＋臉範圍遮罩，給 `web/src/companion-face.js` 用。

1. 底圖：`gen_gemini.py`（鑰匙讀 `engine/.env.local` 的 GEMINI_API_KEY）。距離感靠「縮小貼到同色背景＋桌子往下延伸」自己做，Gemini 不肯把人畫小。
2. 零件：對底圖做「只改嘴／只改眼」的修圖（提示詞要寫其他地方分毫不動）。
3. 拆層：`python build_rig.py <底圖> <零件資料夾> <輸出資料夾> rig-b-far.json`——印出 `rest-pose max diff 0` 才算拆對（不動時疊回去跟原圖一模一樣）。
4. 轉成 WebP 放 `web/avatars/ningning-rig/`。
5. 驗收影片：`NOHOME=1 node demo-video.js <本機網址> <輸出資料夾>` 逐格算畫面，再用 ffmpeg 配 `ning-story.wav`。

素材原圖在 `E:\Claude\image-assets\munea-ningning-rivestyle\far\s76\`。
