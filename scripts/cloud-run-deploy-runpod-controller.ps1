param(
  [string]$ProjectId = "gen-lang-client-0229303523",
  [string]$Region = "asia-east1",
  [string]$Service = "munea-runpod-controller",
  [string]$ServiceAccount = "munea-call-control@gen-lang-client-0229303523.iam.gserviceaccount.com",
  [string]$GatewayUrl = "https://munea-call-control-fiu65jd4da-de.a.run.app",
  [string]$RunPodSecret = "munea-runpod-api-key",
  [string]$GatewayAdminSecret = "munea-gateway-admin-key",
  [string]$AvatarAppKeySecret = "munea-avatar-app-key",
  [int]$SlotsPerPod = 2,
  [int]$MaxPods = 14,
  [int]$TargetConcurrentCalls = 30,
  [switch]$DryRun
)

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
  MUNEA_RUNPOD_MAX_SCALE_UP_PER_CYCLE = "4"
  MUNEA_TARGET_CONCURRENT_CALLS = [string]$TargetConcurrentCalls
  MUNEA_RUNPOD_SCALE_UP_UTILIZATION = "0.80"
  MUNEA_RUNPOD_FAILURE_THRESHOLD = "3"
  MUNEA_RUNPOD_IDLE_SECONDS = "900"
  MUNEA_RUNPOD_COOLDOWN_SECONDS = "300"
  MUNEA_RUNPOD_SCALE_UP_COOLDOWN_SECONDS = "15"
  MUNEA_RUNPOD_STARTUP_TIMEOUT_SECONDS = "420"
  MUNEA_RUNPOD_POLL_SECONDS = "15"
  MUNEA_RUNPOD_SCALE_DOWN_ACTION = "stop"
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
