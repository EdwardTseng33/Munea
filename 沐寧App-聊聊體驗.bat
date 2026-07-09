@echo off
chcp 65001 >nul
REM ============================================
REM  沐寧 · App 聊聊一鍵體驗（寧寧會動的臉 · 雲端快照秒醒版 · 2026-07-09）
REM  做三件事：起語音服務(:8210) → 起 App(:8123) → 開瀏覽器進 App
REM  臉引擎在雲端全自動（進聊聊頁自動預醒、沒人用自動休眠）、不用開本機顯卡
REM  日誌：voice-8210.log（語音出問題拍給蘇菲）
REM ============================================
cd /d "%~dp0"

if not exist "engine\.env.local" (
  echo [!] 找不到 engine\.env.local（要有 GEMINI_API_KEY）
  pause
  exit /b 1
)

REM --- 語音服務 :8210（避開舊服務佔用的 8201）---
netstat -an | findstr ":8210" | findstr "LISTENING" >nul 2>nul
if errorlevel 1 (
  echo 啟動語音服務(:8210)...
  start "沐寧-語音服務(關掉=結束)" /min cmd /c "cd /d %~dp0 && set MUNEA_VOICE_PORT=8210&& python -u engine\live_voice_server.py > voice-8210.log 2>&1"
)

REM --- App 網頁 :8123 ---
netstat -an | findstr ":8123" | findstr "LISTENING" >nul 2>nul
if errorlevel 1 (
  echo 啟動 App(:8123)...
  start "沐寧-App網頁(關掉=結束)" /min cmd /c "cd /d %~dp0 && python -m http.server 8123 --directory web > app-8123.log 2>&1"
)

echo 等服務起來...
timeout /t 3 /nobreak >nul

echo 開瀏覽器（進去點「聊聊」→「開始通話」就能體驗會動的寧寧）
start "" "http://localhost:8123/index.html?voiceUrl=ws://localhost:8210"
exit /b 0
