@echo off
chcp 65001 >nul
REM ============================================
REM  沐寧 · 聊聊實機 Demo 一鍵啟動
REM  會開兩個東西：黑色小視窗（語音服務、關掉=結束）＋瀏覽器 Demo 頁
REM  鑰匙：服務自動讀 engine\.env.local
REM ============================================
cd /d "%~dp0"

if not exist "engine\.env.local" (
  echo [!] 找不到 engine\.env.local（要有 GEMINI_API_KEY）
  pause
  exit /b 1
)

REM 已經有服務在跑（8201 有人聽）→ 直接開頁面就好
netstat -an | findstr ":8201" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo Demo 服務已經在跑了，直接打開頁面。
  start "" "http://localhost:8201/demo.html"
  timeout /t 3 /nobreak >nul
  exit /b 0
)

echo 正在啟動語音服務（會開一個黑色小視窗，關掉它=結束 Demo）...
start "沐寧聊聊Demo-語音服務" cmd /k "cd /d %~dp0 && python engine\live_voice_server.py"

REM 等服務起來再開瀏覽器（最多等 15 秒）
set /a tries=0
:waitloop
timeout /t 1 /nobreak >nul
netstat -an | findstr ":8201" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 goto ready
set /a tries+=1
if %tries% lss 15 goto waitloop
echo [!] 服務 15 秒內沒起來，看黑色小視窗的錯誤訊息。
pause
exit /b 1

:ready
echo.
echo   電腦體驗：http://localhost:8201/demo.html
echo   （手機要體驗請用「demo-聊聊-公開連結.bat」產生的 https 網址）
echo.
start "" "http://localhost:8201/demo.html"
timeout /t 3 /nobreak >nul
exit /b 0
