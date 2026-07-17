@echo off
chcp 65001 >nul
echo [STOP] 這個舊 bootstrap 工具已退役，未修改 Secret Manager IAM。
echo        它使用共享 default compute service account，不符合目前最小權限要求。
echo        請由 Platform 依 deploy\cloudrun\SERVICE-TOPOLOGY.md 重新審核 service-specific 權限。
pause
exit /b 1

set LOG=%~dp0權限結果.log
echo ============================================
echo 沐寧搬家 · 發保險箱開箱權限（資料櫃鑰匙 · staging）
echo 給誰：跑沐寧引擎的那台雲端機器
echo 範圍：只能「讀」這一把測試用資料櫃鑰匙
echo ============================================
call "%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" secrets add-iam-policy-binding munea-supabase-service-staging --member=serviceAccount:491603544409-compute@developer.gserviceaccount.com --role=roles/secretmanager.secretAccessor > "%LOG%" 2>&1
type "%LOG%"
echo.
echo （結果已自動存檔，跟蘇菲說「點好了」即可）
pause
