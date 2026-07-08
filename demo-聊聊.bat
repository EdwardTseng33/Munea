@echo off
chcp 65001 >nul
REM ============================================
REM  沐寧 · 聊聊 Live Avatar Demo 一鍵啟動（單角色 · 寧寧）
REM  會開兩個縮小視窗（語音服務＋影像引擎、關掉=結束）＋瀏覽器 Demo 頁
REM  日誌：demo-voice.log（語音）/ demo-avatar.log（影像）——出問題拍給蘇菲
REM ============================================
cd /d "%~dp0"

if not exist "engine\.env.local" (
  echo [!] 找不到 engine\.env.local（要有 GEMINI_API_KEY）
  pause
  exit /b 1
)
if not exist "E:\voice-poc\.venv\Scripts\python.exe" (
  echo [!] 找不到影像引擎環境 E:\voice-poc\.venv（對嘴引擎要用它）
  pause
  exit /b 1
)

REM --- 語音服務 :8201 ---
netstat -an | findstr ":8201" | findstr "LISTENING" >nul 2>nul
if errorlevel 1 (
  echo 啟動語音服務...
  start "沐寧Demo-語音服務(關掉=結束)" /min cmd /c "cd /d %~dp0 && python -u engine\live_voice_server.py > demo-voice.log 2>&1"
)

REM --- 影像引擎 :8188（載模型約 15 秒） ---
netstat -an | findstr ":8188" | findstr "LISTENING" >nul 2>nul
if errorlevel 1 (
  echo 啟動寧寧影像引擎（載模型約 15 秒）...
  start "沐寧Demo-影像引擎(關掉=結束)" /min cmd /c "cd /d %~dp0 && E:\voice-poc\.venv\Scripts\python.exe -u engine\avatar_live_server.py > demo-avatar.log 2>&1"
)

REM --- 等兩個門都開（最多 40 秒） ---
set /a tries=0
:waitloop
timeout /t 2 /nobreak >nul
set /a ok=0
netstat -an | findstr ":8201" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 set /a ok+=1
netstat -an | findstr ":8188" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 set /a ok+=1
if %ok%==2 goto ready
set /a tries+=1
if %tries% lss 20 goto waitloop
echo [!] 服務沒起來——看 demo-voice.log / demo-avatar.log（拍給蘇菲也行）。
pause
exit /b 1

:ready
echo.
echo   Demo 頁：http://localhost:8201/demo-live.html
echo   （六角色卡通版備用：http://localhost:8201/demo.html）
echo.
start "" "http://localhost:8201/demo-live.html"
timeout /t 3 /nobreak >nul
exit /b 0
