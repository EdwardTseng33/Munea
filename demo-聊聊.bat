@echo off
chcp 65001 >nul
REM ============================================
REM  沐寧 · 聊聊實機 Demo 一鍵啟動
REM  跑起語音橋（含網頁）→ 自動開 Demo 頁
REM  鑰匙：服務會自動讀 engine\.env.local（GEMINI_API_KEY）
REM  手機體驗：同一個 Wi-Fi 開 http://<下面列的IP>:8201/demo.html
REM ============================================
cd /d "%~dp0"

if not exist "engine\.env.local" (
  echo [!] 找不到 engine\.env.local（要有 GEMINI_API_KEY）
  pause & exit /b 1
)

echo.
echo   沐寧 · 聊聊實機 Demo
echo   ---------------------------------
echo   電腦體驗：http://localhost:8201/demo.html
for /f "tokens=2 delims=: " %%i in ('ipconfig ^| findstr /c:"IPv4"') do echo   手機體驗（同 Wi-Fi）：http://%%i:8201/demo.html
echo   關掉這個視窗＝結束 Demo
echo.

start "" "http://localhost:8201/demo.html"
python engine\live_voice_server.py
pause
