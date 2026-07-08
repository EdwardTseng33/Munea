@echo off
chcp 65001 >nul
REM ============================================
REM  沐寧聊聊 Demo · 一鍵上 Vercel（永久連結）
REM  做兩件事：① 把 AI 鑰匙放進 Vercel 保險箱 ② 部署正式版
REM  跑完看到 https://munea-chat-demo-xxx.vercel.app 就是連結
REM ============================================
cd /d "%~dp0"

set "GKEY="
for /f "usebackq tokens=1,* delims==" %%a in ("..\engine\.env.local") do (
  if /i "%%a"=="GEMINI_API_KEY" set "GKEY=%%b"
)
if not defined GKEY (
  echo [!] 在 engine\.env.local 找不到 GEMINI_API_KEY
  pause
  exit /b 1
)

echo [1/2] 把 AI 鑰匙放進 Vercel（若顯示已存在，跳過即可）...
echo %GKEY%| call vercel env add GEMINI_API_KEY production

echo.
echo [2/2] 部署正式版...
call vercel deploy --prod --yes

echo.
echo 上面 Production 那行的 https:// 網址就是永久連結（手機電腦都能開口講話）。
echo 跑完跟蘇菲說一聲，她會幫你全線驗證＋把網址做成 QR 放進提案。
pause
