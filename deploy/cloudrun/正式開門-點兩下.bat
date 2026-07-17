@echo off
chcp 65001 >nul
echo [STOP] 這個舊雙擊工具已退役，未修改 Cloud Run IAM。
echo        staging / production 角色與公開邊界請看 deploy\cloudrun\SERVICE-TOPOLOGY.md。
echo        所有部署必須走 canary-deploy.sh 或 prod-deploy.sh。
pause
exit /b 1

REM ============================================
REM  沐寧 · 正式開門（7/9 Edward 拍板「正式上線方式推進」）
REM  做一件事：把雲端語音橋的大門打開（讓 App 直連、不用再帶 Google 通行證）
REM  安全：App 內建薄門通行碼——陌生人拿到網址也會被擋；費用警戒 NT$500 已設
REM ============================================
set "GCLOUD=%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"

echo == 開門（語音橋 munea-voice-staging）==
call "%GCLOUD%" run services add-iam-policy-binding munea-voice-staging --region=asia-east1 --member=allUsers --role=roles/run.invoker
if errorlevel 1 (
  echo [!] 開門失敗——把這個視窗拍照給蘇菲
  pause
  exit /b 1
)

echo == 驗門（應該回 200 或 426、不再是 403）==
curl -s -m 20 -o NUL -w "語音橋大門 -> %%{http_code}\n" "https://munea-voice-staging-491603544409.asia-east1.run.app/"

echo.
echo 完成！現在 App 打開就是完整雲端體驗（聲音＋會動的寧寧）。
pause
