param(
  [string]$ProjectId = "gen-lang-client-0229303523",
  [string]$Region = "asia-east1",
  [string]$Service = "munea-gateway-monitor",
  [string]$ServiceAccount = "munea-call-control@gen-lang-client-0229303523.iam.gserviceaccount.com",
  [string]$GatewayUrl = "https://munea-call-control-fiu65jd4da-de.a.run.app",
  [string]$AdminKeySecret = "munea-gateway-admin-key",
  [string]$SlackWebhookSecret = "munea-slack-alert-webhook",
  [int]$IntervalSeconds = 60,
  [switch]$Notify,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "deploy\gateway"

if ($IntervalSeconds -lt 30) {
  throw "IntervalSeconds must be at least 30 seconds"
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
$secretBindings = "MUNEA_GATEWAY_ADMIN_KEY=$($AdminKeySecret):latest"
if ($Notify) {
  $secretBindings += ",MUNEA_SLACK_ALERT_WEBHOOK=$($SlackWebhookSecret):latest"
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
  "--set-env-vars", "MUNEA_GATEWAY_URL=$GatewayUrl,MUNEA_GATEWAY_MONITOR_INTERVAL_SECONDS=$IntervalSeconds,MUNEA_GATEWAY_MONITOR_NOTIFY=$notifyValue",
  "--memory", "512Mi",
  "--cpu", "1",
  "--min-instances", "1",
  "--max-instances", "1",
  "--concurrency", "10",
  "--timeout", "30",
  "--no-cpu-throttling",
  "--no-allow-unauthenticated",
  "--quiet"
)
if (-not $Notify) {
  $argsList += @("--remove-secrets", "MUNEA_SLACK_ALERT_WEBHOOK")
}

Write-Host "Deploying $Service (notify=$notifyValue)" -ForegroundColor Cyan
if ($DryRun) {
  Write-Host ("gcloud " + ($argsList -join " "))
  exit 0
}

& $gcloud.Source @argsList
if ($LASTEXITCODE -ne 0) { throw "Gateway monitor deployment failed" }

& $gcloud.Source run services describe $Service --project $ProjectId --region $Region `
  --format="table(status.url,status.latestReadyRevisionName,spec.template.metadata.annotations.'autoscaling.knative.dev/minScale')"
