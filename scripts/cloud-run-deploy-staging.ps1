param(
  [string]$ProjectId = "gen-lang-client-0229303523",
  [string]$Region = "asia-east1",
  [string]$BrainService = "munea-brain-staging",
  [string]$VoiceService = "munea-voice-staging",
  [string]$GeminiSecret = "munea-gemini-key-staging",
  [string]$SupabaseSecret = "munea-supabase-service-staging",
  [string]$AdminSecret = "munea-admin-token-staging",
  [string]$AdminPasswordSecret = "munea-admin-password",
  [string]$AdminEmail = "edwardt0303@gmail.com",
  [string]$CallControlUrl = "https://munea-call-control-fiu65jd4da-de.a.run.app",
  [string]$GatewayAdminSecret = "munea-gateway-admin-key",
  [string]$CallTokenSecret = "munea-call-token-secret",
  [string]$VoiceShardId = "voice-asia-east1-primary",
  [switch]$IncludeVoice,
  [switch]$RequireCallControl,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Import-Module Microsoft.PowerShell.Management
Import-Module Microsoft.PowerShell.Utility
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($name) {
  Write-Host ""
  Write-Host "== $name ==" -ForegroundColor Cyan
}

function Pass($message) {
  Write-Host "PASS $message" -ForegroundColor Green
}

function Warn($message) {
  Write-Host "WARN $message" -ForegroundColor Yellow
}

function Resolve-Gcloud {
  $cmd = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }

  $cmd = Get-Command gcloud -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }

  $bundled = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
  if (Test-Path $bundled) {
    return $bundled
  }

  throw "gcloud was not found. Install Google Cloud SDK or add gcloud to PATH."
}

function Invoke-GcloudText($argsList) {
  $output = & $script:Gcloud @argsList 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw ($output -join "`n")
  }
  return ($output -join "`n").Trim()
}

function Test-SecretExists($name) {
  try {
    Invoke-GcloudText @("secrets", "describe", $name, "--project", $ProjectId, "--format=value(name)") | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Get-DeploymentValue($name) {
  $value = [Environment]::GetEnvironmentVariable($name)
  if (-not [string]::IsNullOrWhiteSpace($value)) {
    return $value.Trim()
  }

  $envPath = Join-Path $root "engine\.env.local"
  if (-not (Test-Path -LiteralPath $envPath)) {
    return $null
  }

  $escapedName = [regex]::Escape($name)
  foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match "^\s*$escapedName\s*=\s*(.*)$") {
      return $matches[1].Trim().Trim('"').Trim("'")
    }
  }
  return $null
}

function New-CleanSourceFromCommit($destination, $commit) {
  $zip = Join-Path ([System.IO.Path]::GetTempPath()) ("munea-cloudrun-source-{0}.zip" -f ([guid]::NewGuid().ToString("N")))
  try {
    & git archive --format=zip -o $zip $commit
    if ($LASTEXITCODE -ne 0) {
      throw "git archive failed"
    }
    Expand-Archive -LiteralPath $zip -DestinationPath $destination -Force
  } finally {
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
  }
}

function Invoke-RunDeploy($argsList) {
  if ($DryRun) {
    Write-Host ("gcloud " + ($argsList -join " "))
    return
  }
  & $script:Gcloud @argsList
  if ($LASTEXITCODE -ne 0) {
    throw "gcloud run deploy failed"
  }
}

$Gcloud = Resolve-Gcloud
$gitCommit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
  throw "Could not read git HEAD"
}
if ($gitCommit -notmatch '^[0-9a-fA-F]{40,64}$') {
  throw "Git HEAD is not a valid release commit"
}
$gitHead = $gitCommit.Substring(0, 12)

Step "Clean source"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("munea-cloudrun-source-{0}" -f ([guid]::NewGuid().ToString("N")))
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
try {
  New-CleanSourceFromCommit $tempRoot $gitCommit
  $releasePackage = Get-Content -Raw -LiteralPath (Join-Path $tempRoot "package.json") | ConvertFrom-Json
  $releaseVersion = ([string]$releasePackage.version).Trim()
  if ($releaseVersion -notmatch '^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$') {
    throw "Committed package.json has an invalid release version"
  }
  Pass "prepared committed release v$releaseVersion at $gitHead in $tempRoot"

  $adminSecretExists = Test-SecretExists $AdminSecret
  if ($adminSecretExists) {
    Pass "admin secret exists: $AdminSecret"
  } else {
    Warn "admin secret missing: $AdminSecret; staging admin reads will stay disabled until it is created"
  }

  $supabaseEnv = @{}
  foreach ($name in @(
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "MUNEA_SUPABASE_ACCOUNT_ID",
    "MUNEA_SUPABASE_PERSON_ID",
    "MUNEA_SUPABASE_FAMILY_GROUP_ID"
  )) {
    $value = Get-DeploymentValue $name
    if ([string]::IsNullOrWhiteSpace($value)) {
      throw "$name is required in the process environment or engine/.env.local before staging deploy"
    }
    $supabaseEnv[$name] = $value
  }
  Pass "Supabase staging URL and scoped ids are available"

  $adminPasswordSecretExists = Test-SecretExists $AdminPasswordSecret
  if ($adminPasswordSecretExists) {
    Pass "admin password secret exists: $AdminPasswordSecret"
  } else {
    Warn "admin password secret missing: $AdminPasswordSecret; email/password login stays disabled until it is created"
  }

  $brainSecrets = "GEMINI_API_KEY=$($GeminiSecret):latest,SUPABASE_SERVICE_ROLE_KEY=$($SupabaseSecret):latest"
  if ($adminSecretExists) {
    $brainSecrets += ",MUNEA_ADMIN_API_TOKEN=$($AdminSecret):latest"
  }
  if ($adminPasswordSecretExists) {
    $brainSecrets += ",MUNEA_ADMIN_PASSWORD=$($AdminPasswordSecret):latest"
  }
  $brainEnvVars = @(
    "MUNEA_DATABASE_PROVIDER=supabase",
    "MUNEA_ENV_NAME=staging",
    "MUNEA_RELEASE_VERSION=$releaseVersion",
    "MUNEA_RELEASE_COMMIT=$gitCommit",
    "MUNEA_REQUIRE_AUTH=1",
    "MUNEA_ENABLE_DEV_AUTH_BYPASS=false",
    "MUNEA_ADMIN_EMAIL=$AdminEmail",
    "SUPABASE_URL=$($supabaseEnv['SUPABASE_URL'])",
    "SUPABASE_PUBLISHABLE_KEY=$($supabaseEnv['SUPABASE_PUBLISHABLE_KEY'])",
    "MUNEA_SUPABASE_ACCOUNT_ID=$($supabaseEnv['MUNEA_SUPABASE_ACCOUNT_ID'])",
    "MUNEA_SUPABASE_PERSON_ID=$($supabaseEnv['MUNEA_SUPABASE_PERSON_ID'])",
    "MUNEA_SUPABASE_FAMILY_GROUP_ID=$($supabaseEnv['MUNEA_SUPABASE_FAMILY_GROUP_ID'])"
  ) -join ","

  Step "Deploy brain staging"
  # Keep Cloud Run public at the edge; MUNEA_REQUIRE_AUTH enforces app-level authentication.
  $brainArgs = @(
    "run", "deploy", $BrainService,
    "--source", $tempRoot,
    "--clear-base-image",
    "--region", $Region,
    "--project", $ProjectId,
    "--update-secrets", $brainSecrets,
    "--update-env-vars", $brainEnvVars,
    "--memory", "1Gi",
    "--min-instances", "0",
    "--max-instances", "2",
    "--concurrency", "40",
    "--allow-unauthenticated",
    "--quiet"
  )
  Invoke-RunDeploy $brainArgs

  if ($IncludeVoice) {
    Step "Deploy voice staging"
    foreach ($secretName in @($GatewayAdminSecret, $CallTokenSecret)) {
      if (-not (Test-SecretExists $secretName)) {
        throw "required voice secret is missing: $secretName"
      }
    }

    $callControlRequired = if ($RequireCallControl) { "1" } else { "0" }
    $voiceSecrets = @(
      "GEMINI_API_KEY=$($GeminiSecret):latest",
      "MUNEA_GATEWAY_ADMIN_KEY=$($GatewayAdminSecret):latest",
      "MUNEA_CALL_TOKEN_SECRET=$($CallTokenSecret):latest"
    ) -join ","
    $voiceEnvVars = @(
      "MUNEA_SERVICE=voice",
      "MUNEA_ENV_NAME=staging",
      "MUNEA_RELEASE_VERSION=$releaseVersion",
      "MUNEA_RELEASE_COMMIT=$gitCommit",
      "MUNEA_CALL_CONTROL_URL=$CallControlUrl",
      "MUNEA_CALL_CONTROL_REQUIRED=$callControlRequired",
      "MUNEA_VOICE_SHARD_ID=$VoiceShardId"
    ) -join ","

    # Voice needs the same public edge so the app can establish its session.
    # Keep Call Control optional during the old-App transition; require it only
    # after the Gateway-only build is distributed.
    $voiceArgs = @(
      "run", "deploy", $VoiceService,
      "--source", $tempRoot,
      "--clear-base-image",
      "--region", $Region,
      "--project", $ProjectId,
      "--update-secrets", $voiceSecrets,
      "--update-env-vars", $voiceEnvVars,
      "--timeout", "3600",
      "--session-affinity",
      "--memory", "1Gi",
      "--min-instances", "0",
      "--max-instances", "2",
      "--concurrency", "20",
      "--allow-unauthenticated",
      "--quiet"
    )
    Invoke-RunDeploy $voiceArgs
  } else {
    Warn "voice staging deploy skipped; pass -IncludeVoice when voice code or shared runtime changed"
  }

  if ($DryRun) {
    Write-Host ""
    Write-Host "Dry run complete. No Cloud Run service was changed." -ForegroundColor Yellow
  } else {
    Write-Host ""
    Write-Host "Cloud Run staging deploy complete." -ForegroundColor Green
  }
} finally {
  Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
