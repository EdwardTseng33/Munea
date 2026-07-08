@echo off
chcp 65001 >nul
echo ============================================
echo 沐寧搬家 · 發保險箱開箱權限（只讀 staging 鑰匙）
echo 給誰：跑沐寧引擎的那台雲端機器
echo 範圍：只能「讀」這一把測試鑰匙，不能改、不能讀別的
echo ============================================
"%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" secrets add-iam-policy-binding munea-gemini-key-staging --member=serviceAccount:491603544409-compute@developer.gserviceaccount.com --role=roles/secretmanager.secretAccessor
echo.
echo 上面若顯示 bindings / etag 字樣 = 成功。跟蘇菲說一聲「權限發了」。
pause
