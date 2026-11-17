param(
  [string]$ProjectId = "gen-lang-client-0229303523",
  [string]$Region = "asia-east1",
  [string]$Service = "munea-gateway-monitor",
  [string]$ServiceAccount = "munea-call-control@gen-lang-client-0229303523.iam.gserviceaccount.com",
  [string]$GatewayUrl = "https://munea-call-control-fiu65jd4da-de.a.run.app",
  [string]$AdminKeySecret = "munea-gateway-admin-key",
  [string]$SlackWebhookSecret = "munea-slack-alert-webhook",
  # 2026-07-29: STATUS 125 defense line 2 (worker clock-skew probing) ships
  # armed by default -- monitor.py only probes each worker's /health for
  # clock skew when MUNEA_APP_KEY is bound. Pass -NoWorkerClockProbe to opt
  # out. (ASCII comment on purpose: non-ASCII inside param() breaks
  # Windows PowerShell 5.1 parsing of the defaults.)
  [string]$AvatarAppKeySecret = "munea-avatar-app-key",
  [switch]$NoWorkerClockProbe,
  # 2026-11-17: voice patrol. Every 30 minutes the monitor really opens one
  # Gemini Live connection through the voice service's own /selftest/live
  # door (light mode, next to free) and alerts after two failures in a row.
  # Uses the same MUNEA_APP_KEY binding as the worker clock probe. Pass
  # -NoVoicePatrol to opt out.
  [string]$VoiceSelftestUrl = "https://munea-voice-491603544409.asia-east1.run.app",
  [switch]$NoVoicePatrol,
  [int]$IntervalSeconds = 60,
  # 2026-11-17: scheduled mode is the default. Cloud Scheduler calls
  # POST /run-once every $TickMinutes minutes; the service bills per request
  # and scales to zero. Pass -AlwaysOn for the legacy background loop, which
  # needs one instance with CPU always allocated (the costly setup).
  [switch]$AlwaysOn,
  # Skip the build and deploy; only (re)apply the invoker grant and the
  # scheduler job, for example to change -TickMinutes.
  [switch]$ScheduleOnly,
  [int]$TickMinutes = 2,
  [string]$SchedulerJob = "munea-gateway-monitor-tick-production",
  [switch]$Notify,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "deploy\gateway"

if ($IntervalSeconds -lt 30) {
  throw "IntervalSeconds must be at least 30 seconds"
}
if ($TickMinutes -lt 1 -or $TickMinutes -gt 10) {
  # Longer than 10 minutes lets the instance go cold between ticks, which
  # resets the in-memory "already notified" state and repeats active alerts.
  throw "TickMinutes must be between 1 and 10"
}

$gcloud = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
if (-not $gcloud) { $gcloud = Get-Command gcloud -ErrorAction SilentlyContinue }
if (-not $gcloud) { throw "gcloud was not found" }

foreach ($secret in @($AdminKeySecret)) {
  & $gcloud.Source secrets describe $secret --project $ProjectId --format="value(name)" 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Required Secret Manager secret is missing: $secret" }
}
if ($Notify) {
  & $gcloud.Source secrets describe $SlackWebhookSecret --project $ProjectId --format="value(name)" 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Required Secret Manager secret is missing: $SlackWebhookSecret" }
}

$notifyValue = if ($Notify) { "1" } else { "0" }
if (-not $NoVoicePatrol -and $NoWorkerClockProbe) {
  throw "The voice patrol needs the MUNEA_APP_KEY binding; pass -NoVoicePatrol together with -NoWorkerClockProbe"
}
$envVars = "MUNEA_GATEWAY_URL=$GatewayUrl,MUNEA_GATEWAY_MONITOR_INTERVAL_SECONDS=$IntervalSeconds,MUNEA_GATEWAY_MONITOR_NOTIFY=$notifyValue"
$loopValue = if ($AlwaysOn) { "1" } else { "0" }
$minInstances = if ($AlwaysOn) { "1" } else { "0" }
$cpuFlag = if ($AlwaysOn) { "--no-cpu-throttling" } else { "--cpu-throttling" }
$envVars += ",MUNEA_GATEWAY_MONITOR_LOOP=$loopValue"
if (-not $NoVoicePatrol) { $envVars += ",MUNEA_VOICE_SELFTEST_URL=$VoiceSelftestUrl" }
$secretBindings = "MUNEA_GATEWAY_ADMIN_KEY=$($AdminKeySecret):latest"
if ($Notify) {
  $secretBindings += ",MUNEA_SLACK_ALERT_WEBHOOK=$($SlackWebhookSecret):latest"
}
if (-not $NoWorkerClockProbe) {
  & $gcloud.Source secrets describe $AvatarAppKeySecret --project $ProjectId --format="value(name)" 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Required Secret Manager secret is missing: $AvatarAppKeySecret" }
  $secretBindings += ",MUNEA_APP_KEY=$($AvatarAppKeySecret):latest"
}
$argsList = @(
  "run", "deploy", $Service,
  "--source", $source,
  "--region", $Region,
  "--project", $ProjectId,
  "--service-account", $ServiceAccount,
  "--command", "uvicorn",
  "--args", "monitor_service:app,--host,0.0.0.0,--port,8080",
  "--update-secrets", $secretBindings,
  "--set-env-vars", $envVars,
  "--memory", "512Mi",
  "--cpu", "1",
  "--min-instances", $minInstances,
  "--max-instances", "1",
  "--concurrency", "10",
  "--timeout", "60",
  $cpuFlag,
  "--no-allow-unauthenticated",
  "--quiet"
)
$removeSecrets = @()
if (-not $Notify) { $removeSecrets += "MUNEA_SLACK_ALERT_WEBHOOK" }
if ($NoWorkerClockProbe) { $removeSecrets += "MUNEA_APP_KEY" }
if ($removeSecrets.Count -gt 0) {
  $argsList += @("--remove-secrets", ($removeSecrets -join ","))
}

if ($ScheduleOnly -and $AlwaysOn) { throw "-ScheduleOnly does not apply to -AlwaysOn" }

# "Does this job exist" must not abort the script: under
# ErrorActionPreference=Stop, Windows PowerShell turns gcloud's NOT_FOUND on
# stderr into a terminating error even when stderr is redirected.
function Test-SchedulerJob([string]$Name) {
  $previous = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $gcloud.Source scheduler jobs describe $Name --project $ProjectId --location $Region --format="value(name)" 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
  } finally {
    $ErrorActionPreference = $previous
  }
}

$modeLabel = if ($AlwaysOn) { "always-on loop" } else { "scheduled every $TickMinutes min" }
$patrolLabel = if ($NoVoicePatrol) { "off" } else { $VoiceSelftestUrl }
Write-Host "Deploying $Service (notify=$notifyValue, mode=$modeLabel, voice patrol=$patrolLabel)" -ForegroundColor Cyan
if ($DryRun) {
  Write-Host ("gcloud " + ($argsList -join " "))
  if (-not $AlwaysOn) {
    Write-Host "then: allow $ServiceAccount to invoke $Service, and create or update Cloud Scheduler job $SchedulerJob (*/$TickMinutes * * * *, POST /run-once, OIDC)"
  }
  exit 0
}

if (-not $ScheduleOnly) {
  & $gcloud.Source @argsList
  if ($LASTEXITCODE -ne 0) { throw "Gateway monitor deployment failed" }
}

if ($AlwaysOn) {
  # The loop does the polling; a leftover tick would only double the work.
  if (Test-SchedulerJob $SchedulerJob) {
    & $gcloud.Source scheduler jobs pause $SchedulerJob --project $ProjectId --location $Region --quiet | Out-Null
    Write-Host "Paused scheduler job $SchedulerJob (always-on mode)" -ForegroundColor Yellow
  }
} else {
  $serviceUrl = (& $gcloud.Source run services describe $Service --project $ProjectId --region $Region --format="value(status.url)").Trim()
  if (-not $serviceUrl) { throw "Could not read the $Service URL" }

  # The service stays private. Only this one service account may call it,
  # and only this one service.
  & $gcloud.Source run services add-iam-policy-binding $Service `
    --project $ProjectId --region $Region `
    --member "serviceAccount:$ServiceAccount" --role "roles/run.invoker" --quiet | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Could not allow $ServiceAccount to invoke $Service" }

  $jobArgs = @(
    "--project", $ProjectId, "--location", $Region,
    "--schedule", "*/$TickMinutes * * * *", "--time-zone", "Asia/Taipei",
    "--uri", "$serviceUrl/run-once", "--http-method", "POST",
    "--oidc-service-account-email", $ServiceAccount,
    "--oidc-token-audience", $serviceUrl,
    "--attempt-deadline", "60s",
    "--max-retry-attempts", "1", "--min-backoff", "20s"
  )
  if (Test-SchedulerJob $SchedulerJob) {
    & $gcloud.Source scheduler jobs update http $SchedulerJob @jobArgs --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not update scheduler job $SchedulerJob" }
    $state = (& $gcloud.Source scheduler jobs describe $SchedulerJob --project $ProjectId --location $Region --format="value(state)").Trim()
    if ($state -eq "PAUSED") {
      & $gcloud.Source scheduler jobs resume $SchedulerJob --project $ProjectId --location $Region --quiet | Out-Null
    }
  } else {
    & $gcloud.Source scheduler jobs create http $SchedulerJob @jobArgs --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not create scheduler job $SchedulerJob" }
  }
  Write-Host "Scheduler job $SchedulerJob calls $serviceUrl/run-once every $TickMinutes min" -ForegroundColor Green
}

& $gcloud.Source run services describe $Service --project $ProjectId --region $Region `
  --format="table(status.url,status.latestReadyRevisionName,spec.template.metadata.annotations.'autoscaling.knative.dev/minScale')"
