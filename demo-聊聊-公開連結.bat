@echo off
chcp 65001 >nul
REM ============================================
REM  沐寧 · 聊聊 Demo 臨時公開連結（遠端提案用）
REM  先跑 demo-聊聊.bat 把服務開著，再跑這支。
REM  需要先裝 Cloudflare 官方工具（一次性、Edward 拍板後裝）：
REM    winget install --id Cloudflare.cloudflared
REM  產生的 https 網址（trycloudflare.com 結尾）＝對方點開就能講話。
REM  注意：連結有效期間任何拿到的人都能用，示範完關掉這視窗連結即失效。
REM ============================================
where cloudflared >nul 2>nul
if errorlevel 1 (
  echo [!] 還沒裝 cloudflared。請 Edward 確認要開公開連結後執行：
  echo     winget install --id Cloudflare.cloudflared
  pause & exit /b 1
)
echo 正在建立臨時公開連結（看到 https://xxxx.trycloudflare.com 就是網址，加 /demo.html）...
cloudflared tunnel --url http://localhost:8201
pause
