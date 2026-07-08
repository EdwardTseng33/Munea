@echo off
chcp 65001 >nul
REM ============================================
REM  沐寧 · 聊聊實機 Demo 一鍵啟動
REM  跑起語音橋（含網頁）→ 自動開 Demo 頁
REM  手機體驗：同一個 Wi-Fi 開 http://<這台電腦IP>:8201/demo.html
REM ============================================
cd /d "%~dp0"

REM 從 engine\.env.local 載入 GEMINI_API_KEY（沒有就提示）
if not defined GEMINI_API_KEY (
  for /f "usebackq tokens=1,* delims==" %%a in ("engine\.env.local") do (
    if /i "%%a"=="GEMINI_API_KEY" set "GEMINI_API_KEY=%%b"
  )
)
if not defined GEMINI_API_KEY (
  echo [!] 找不到 GEMINI_API_KEY（engine\.env.local）
  pause & exit /b 1
)

echo.
echo   沐寧 · 聊聊實機 Demo
echo   ---------------------------------
echo   電腦體驗：http://localhost:8201/demo.html
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4"') do echo   手機體驗（同 Wi-Fi）：http://%%i:8201/demo.html
echo   關掉這個視窗＝結束 Demo
echo.

start "" "http://localhost:8201/demo.html"
python engine\live_voice_server.py
pause
