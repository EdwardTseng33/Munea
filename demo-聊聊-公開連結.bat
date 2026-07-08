@echo off
chcp 65001 >nul
REM ============================================
REM  沐寧 · 聊聊 Demo 臨時公開連結（遠端提案／手機體驗用）
REM  用法：先跑「demo-聊聊.bat」把服務開著，再雙擊這支。
REM  看到 https://xxxx.trycloudflare.com 就是網址，後面加 /demo.html 給對方。
REM  注意：連結有效期間拿到的人都能講話（用你的 AI 額度）；示範完關掉這視窗，連結立刻失效。
REM ============================================

set "CFD=cloudflared"
where cloudflared >nul 2>nul
if not errorlevel 1 goto run
if exist "%ProgramFiles%\cloudflared\cloudflared.exe" (
  set "CFD=%ProgramFiles%\cloudflared\cloudflared.exe"
  goto run
)
if exist "%LocalAppData%\Microsoft\WinGet\Links\cloudflared.exe" (
  set "CFD=%LocalAppData%\Microsoft\WinGet\Links\cloudflared.exe"
  goto run
)

echo 還沒安裝 Cloudflare 官方連結工具（免費、一次性）。
choice /m "要現在安裝嗎"
if errorlevel 2 exit /b 0
winget install --id Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  echo [!] 安裝失敗，把這個視窗拍給蘇菲看。
  pause
  exit /b 1
)
if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CFD=%ProgramFiles%\cloudflared\cloudflared.exe"
if exist "%LocalAppData%\Microsoft\WinGet\Links\cloudflared.exe" set "CFD=%LocalAppData%\Microsoft\WinGet\Links\cloudflared.exe"

:run
netstat -an | findstr ":8201" | findstr "LISTENING" >nul 2>nul
if errorlevel 1 (
  echo [!] Demo 服務還沒開——先雙擊「demo-聊聊.bat」，再跑這支。
  pause
  exit /b 1
)
echo.
echo 正在建立臨時公開連結...
echo 看到 https://xxxx.trycloudflare.com 就是網址（記得後面加 /demo.html）
echo 關掉這個視窗＝連結失效。
echo.
"%CFD%" tunnel --no-autoupdate --url http://localhost:8201
pause
