@echo off
chcp 65001 >nul
REM ============================================
REM  沐寧 · 聊聊實機 Demo 一鍵啟動
REM  會開：縮小的服務視窗（關掉=結束 Demo）＋瀏覽器 Demo 頁
REM  服務訊息寫在 demo-voice.log（出問題拍這個檔給蘇菲）
REM  ⚠ 服務輸出走日誌檔，就算滑鼠點到黑視窗也不會把服務卡住（Windows 選取模式老毛病）
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

echo 正在啟動語音服務（工作列會多一個縮小的視窗，關掉它=結束 Demo）...
start "沐寧聊聊Demo-語音服務(關掉=結束)" /min cmd /c "cd /d %~dp0 && python -u engine\live_voice_server.py > demo-voice.log 2>&1"

REM 等服務起來再開瀏覽器（最多等 15 秒）
set /a tries=0
:waitloop
timeout /t 1 /nobreak >nul
netstat -an | findstr ":8201" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 goto ready
set /a tries+=1
if %tries% lss 15 goto waitloop
echo [!] 服務 15 秒內沒起來——打開 demo-voice.log 看錯誤訊息（拍給蘇菲也行）。
pause
exit /b 1

:ready
echo.
echo   電腦體驗：http://localhost:8201/demo.html
echo   （手機／遠端要體驗：再雙擊「demo-聊聊-公開連結.bat」拿 https 網址）
echo.
start "" "http://localhost:8201/demo.html"
timeout /t 3 /nobreak >nul
exit /b 0
