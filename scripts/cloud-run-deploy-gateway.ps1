param(
  [string]$ProjectId = "gen-lang-client-0229303523",
  [string]$Region = "asia-east1",
  [string]$Service = "munea-call-control",
  [string]$ServiceAccount = "munea-call-control@gen-lang-client-0229303523.iam.gserviceaccount.com",
  [string]$SupabaseUrl = "https://uhmpmystjjdqqxlpsthc.supabase.co",
  [string]$SupabaseServiceSecret = "munea-supabase-service-staging",
  [string]$AdminKeySecret = "munea-gateway-admin-key",
  [string]$CallTokenSecret = "munea-call-token-secret",
  [string]$PrimaryAvatarUrl = "https://tw-07.access.glows.ai:26969",
  [string]$PrimaryWorkerId = "glows-rtx6000ada-tw07",
  [int]$PrimarySlots = 3,
  [switch]$AllowTraffic,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "deploy\gateway"

function Resolve-Gcloud {
  $command = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $command = Get-Command gcloud -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  throw "gcloud was not found"
}

function Require-Secret([string]$Name) {
  & $script:Gcloud secrets describe $Name --project $ProjectId --format="value(name)" 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Required Secret Manager secret is missing: $Name" }
}

function Get-LatestEnabledSecretVersion([string]$Name) {
  $version = (& $script:Gcloud secrets versions list $Name --project $ProjectId --filter="state=ENABLED" --sort-by="~createTime" --limit=1 --format="value(name)").Trim()
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) {
    throw "No enabled version found for secret: $Name"
  }
  return $version
}

$Gcloud = Resolve-Gcloud
Require-Secret $SupabaseServiceSecret
Require-Secret $AdminKeySecret
Require-Secret $CallTokenSecret
$supabaseSecretVersion = Get-LatestEnabledSecretVersion $SupabaseServiceSecret
$adminSecretVersion = Get-LatestEnabledSecretVersion $AdminKeySecret
$callTokenSecretVersion = Get-LatestEnabledSecretVersion $CallTokenSecret

$publishableKey = [Environment]::GetEnvironmentVariable("SUPABASE_PUBLISHABLE_KEY")
if ([string]::IsNullOrWhiteSpace($publishableKey)) {
  $envFile = Join-Path $root "engine\.env.local"
  if (Test-Path -LiteralPath $envFile) {
    $line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^\s*SUPABASE_PUBLISHABLE_KEY\s*=' } | Select-Object -First 1
    if ($line) { $publishableKey = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'") }
  }
}
if ([string]::IsNullOrWhiteSpace($publishableKey)) {
  throw "SUPABASE_PUBLISHABLE_KEY is required in the environment or engine/.env.local"
}

function ConvertTo-YamlScalar([string]$Value) {
  return "'" + $Value.Replace("'", "''") + "'"
}

$envFile = Join-Path ([IO.Path]::GetTempPath()) ("munea-gateway-env-{0}.yaml" -f ([guid]::NewGuid().ToString("N")))
$envValues = [ordered]@{
  SUPABASE_URL = $SupabaseUrl
  SUPABASE_ANON_KEY = $publishableKey
  MUNEA_GATEWAY_REQUIRE_DURABLE = "1"
  MUNEA_GATEWAY_QUEUE_MAX_DEPTH = "30"
  MUNEA_GATEWAY_VOICE_LIMIT = "30"
  MUNEA_PRIMARY_AVATAR_URL = $PrimaryAvatarUrl
  MUNEA_PRIMARY_WORKER_ID = $PrimaryWorkerId
  MUNEA_PRIMARY_AVATAR_SLOTS = [string]$PrimarySlots
  MUNEA_PRIMARY_AVATAR_REGION = "TW"
  MUNEA_GATEWAY_CORS_ORIGINS = "capacitor://localhost,ionic://localhost,http://localhost,https://localhost"
}
$envLines = foreach ($entry in $envValues.GetEnumerator()) {
  "{0}: {1}" -f $entry.Key, (ConvertTo-YamlScalar ([string]$entry.Value))
}
[IO.File]::WriteAllLines($envFile, $envLines, [Text.UTF8Encoding]::new($false))

$tag = "acceptance-" + (Get-Date -Format "MMdd-HHmm")
$argsList = @(
  "run", "deploy", $Service,
  "--source", $source,
  "--region", $Region,
  "--project", $ProjectId,
  "--service-account", $ServiceAccount,
  "--tag", $tag,
  "--update-secrets", "SUPABASE_SERVICE_ROLE_KEY=$($SupabaseServiceSecret):$supabaseSecretVersion,MUNEA_GATEWAY_ADMIN_KEY=$($AdminKeySecret):$adminSecretVersion,MUNEA_GATEWAY_KEY=$($AdminKeySecret):$adminSecretVersion,MUNEA_CALL_TOKEN_SECRET=$($CallTokenSecret):$callTokenSecretVersion",
  "--env-vars-file", $envFile,
  "--memory", "512Mi",
  "--cpu", "1",
  "--min-instances", "1",
  "--max-instances", "3",
  "--concurrency", "40",
  "--timeout", "60",
  "--allow-unauthenticated",
  "--quiet"
)
if (-not $AllowTraffic) { $argsList += "--no-traffic" }

Write-Host "Deploying $Service tag $tag (traffic=$([bool]$AllowTraffic))" -ForegroundColor Cyan
if ($DryRun) {
  Write-Host ("gcloud " + ($argsList -join " "))
  Remove-Item -LiteralPath $envFile -Force -ErrorAction SilentlyContinue
  exit 0
}

try {
  & $Gcloud @argsList
  if ($LASTEXITCODE -ne 0) { throw "Gateway deployment failed" }
} finally {
  Remove-Item -LiteralPath $envFile -Force -ErrorAction SilentlyContinue
}

$serviceUrl = (& $Gcloud run services describe $Service --project $ProjectId --region $Region --format="value(status.url)").Trim()
$hostName = $serviceUrl -replace '^https://', ''
$canaryUrl = "https://$tag---$hostName"
Write-Host "Canary: $canaryUrl" -ForegroundColor Green
Write-Host "The durable health gate must report ok=true before traffic promotion." -ForegroundColor Yellow
