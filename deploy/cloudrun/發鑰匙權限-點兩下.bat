@echo off
chcp 65001 >nul
set LOG=%~dp0權限結果.log
echo ============================================
echo 沐寧搬家 · 發保險箱開箱權限（只讀 staging 鑰匙）
echo 執行結果會自動存檔，蘇菲會自己來看，你不用抄。
echo ============================================
call "%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" secrets add-iam-policy-binding munea-gemini-key-staging --member=serviceAccount:491603544409-compute@developer.gserviceaccount.com --role=roles/secretmanager.secretAccessor > "%LOG%" 2>&1
type "%LOG%"
echo.
echo （結果已存檔，跟蘇菲說「點好了」即可）
pause
