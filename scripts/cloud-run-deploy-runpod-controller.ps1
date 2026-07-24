param(
  [string]$ProjectId = "gen-lang-client-0229303523",
  [string]$Region = "asia-east1",
  [string]$Service = "munea-runpod-controller",
  [string]$ServiceAccount = "munea-call-control@gen-lang-client-0229303523.iam.gserviceaccount.com",
  [string]$GatewayUrl = "https://munea-call-control-fiu65jd4da-de.a.run.app",
  [string]$RunPodSecret = "munea-runpod-api-key",
  [string]$GatewayAdminSecret = "munea-gateway-admin-key",
  [string]$AvatarAppKeySecret = "munea-avatar-app-key",
  # SlotsPerPod=2 只在備援卡印象檔已升級成雙程序版（deploy/runpod-avatar/
  # gpu-image/Dockerfile.vocaframe 帶 flashhead_router.py 那版）且已重新烤圖、
  # RunPod 私有模板已指到新映像之後才能跑這支腳本用這個值——若模板還是舊版
  # 單程序映像，這裡先手動覆蓋成 1（`-SlotsPerPod 1`），避免管家把只能撐 1
  # 通話的舊卡登記成 2 席容量、通話品質反而變差。取捨說明見
  # deploy/runpod-avatar/README.md「MUNEA_RUNPOD_SLOTS 1→2 切換」段。
  [int]$SlotsPerPod = 2,
  [int]$MaxPods = 4,
  [int]$TargetConcurrentCalls = 10,
  [switch]$DryRun
)

# 2026-07-24 8-10人併發容量升級工程包1（卡西法）：MaxPods/TargetConcurrentCalls
# 預設值改為對齊「主卡2席 + 備援4張x2席 = 10席」目標；SCALE_DOWN_ACTION 預設
# 從 "stop" 改成 "terminate"。
# ⚠ 7/23 教訓：SCALE_DOWN_ACTION="stop" 是死路——RunPod 的 Stop 只停計費碼錶、
# 不保留 GPU 資源，暫停中的卡隨時會被其他租客搶走，恢復時可能直接開不回來
# （見 deploy/runpod-avatar/README.md 成本紀錄「暫停⇄喚醒實測」：暫停3秒成功，
# 喚醒因原主機GPU被租走而失敗）。城堡規矩「用完刪」正是為此而立，未來若有人
# 想改回 "stop" 省錢，先重讀那段教訓再決定。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "deploy\runpod-avatar"

function Resolve-Gcloud {
  $command = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $command = Get-Command gcloud -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  throw "gcloud was not found"
}

$gcloud = Resolve-Gcloud
foreach ($secret in @($RunPodSecret, $GatewayAdminSecret, $AvatarAppKeySecret)) {
  & $gcloud secrets describe $secret --project $ProjectId --format="value(name)" 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Required Secret Manager secret is missing: $secret" }
}

$envFile = Join-Path ([IO.Path]::GetTempPath()) ("munea-runpod-controller-{0}.yaml" -f ([guid]::NewGuid().ToString("N")))
$envValues = [ordered]@{
  MUNEA_RUNPOD_AUTOMATION_MODE = "active"
  MUNEA_GATEWAY_URL = $GatewayUrl
  MUNEA_RUNPOD_POD_PREFIX = "munea-vocaframe-backup"
  MUNEA_RUNPOD_SLOTS = [string]$SlotsPerPod
  MUNEA_RUNPOD_MAX_PODS = [string]$MaxPods
  # 沿用既有值：MaxPods 升到 4 後，"4" 剛好等於新的 max_pods 上限，仍滿足
  # runpod_backup.Config.validate() 的「批次 <= 總量」限制（不需要跟著調整），
  # 語意等同「尖峰時一次把 4 張備援全開齊也可以」，跟 8-10 席目標的急迫性一致。
  MUNEA_RUNPOD_MAX_SCALE_UP_PER_CYCLE = "4"
  MUNEA_TARGET_CONCURRENT_CALLS = [string]$TargetConcurrentCalls
  MUNEA_RUNPOD_SCALE_UP_UTILIZATION = "0.80"
  MUNEA_RUNPOD_FAILURE_THRESHOLD = "3"
  MUNEA_RUNPOD_IDLE_SECONDS = "900"
  MUNEA_RUNPOD_COOLDOWN_SECONDS = "300"
  MUNEA_RUNPOD_SCALE_UP_COOLDOWN_SECONDS = "15"
  MUNEA_RUNPOD_STARTUP_TIMEOUT_SECONDS = "420"
  MUNEA_RUNPOD_POLL_SECONDS = "15"
  MUNEA_RUNPOD_SCALE_DOWN_ACTION = "terminate"
  MUNEA_RUNPOD_STATE_FILE = "/tmp/runpod-backup-state.json"
  MUNEA_RUNPOD_LOCK_FILE = "/tmp/runpod-backup.lock"
}
$lines = foreach ($entry in $envValues.GetEnumerator()) {
  $escaped = ([string]$entry.Value).Replace("'", "''")
  "{0}: '{1}'" -f $entry.Key, $escaped
}
[IO.File]::WriteAllLines($envFile, $lines, [Text.UTF8Encoding]::new($false))

$argsList = @(
  "run", "deploy", $Service,
  "--source", $source,
  "--project", $ProjectId,
  "--region", $Region,
  "--service-account", $ServiceAccount,
  "--update-secrets", "RUNPOD_API_KEY=$($RunPodSecret):latest,MUNEA_GATEWAY_ADMIN_KEY=$($GatewayAdminSecret):latest,MUNEA_AVATAR_APP_KEY=$($AvatarAppKeySecret):latest",
  "--env-vars-file", $envFile,
  "--cpu", "1",
  "--memory", "512Mi",
  "--min-instances", "1",
  "--max-instances", "1",
  "--concurrency", "1",
  "--no-cpu-throttling",
  "--timeout", "60",
  "--allow-unauthenticated",
  "--quiet"
)

try {
  if ($DryRun) {
    Write-Host ("gcloud " + ($argsList -join " "))
  } else {
    & $gcloud @argsList
    if ($LASTEXITCODE -ne 0) { throw "RunPod controller deployment failed" }
  }
} finally {
  Remove-Item -LiteralPath $envFile -Force -ErrorAction SilentlyContinue
}
