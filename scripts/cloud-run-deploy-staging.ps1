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
  [switch]$IncludeVoice,
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

function New-CleanSourceFromHead($destination) {
  $zip = Join-Path ([System.IO.Path]::GetTempPath()) ("munea-cloudrun-source-{0}.zip" -f ([guid]::NewGuid().ToString("N")))
  try {
    & git archive --format=zip -o $zip HEAD
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
$gitHead = (& git rev-parse --short HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
  throw "Could not read git HEAD"
}

Step "Clean source"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("munea-cloudrun-source-{0}" -f ([guid]::NewGuid().ToString("N")))
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
try {
  New-CleanSourceFromHead $tempRoot
  Pass "prepared committed git HEAD $gitHead at $tempRoot"

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
    # Voice needs the same public edge so the app can establish its session.
    $voiceArgs = @(
      "run", "deploy", $VoiceService,
      "--source", $tempRoot,
      "--clear-base-image",
      "--region", $Region,
      "--project", $ProjectId,
      "--update-secrets", "GEMINI_API_KEY=$($GeminiSecret):latest",
      "--update-env-vars", "MUNEA_SERVICE=voice,MUNEA_ENV_NAME=staging",
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
