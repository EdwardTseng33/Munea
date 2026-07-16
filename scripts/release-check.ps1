param(
  [string]$AuthBaseUrl = "http://127.0.0.1:8211",
  [switch]$SkipAuth
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

$envNames = @(
  "GEMINI_API_KEY",
  "MUNEA_SKIP_ENV_LOCAL",
  "MUNEA_DATABASE_PROVIDER"
)
$previousEnv = @{}
foreach ($name in $envNames) {
  $previousEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
  Step "Release consistency"
  & node scripts/test-release-consistency.js
  if ($LASTEXITCODE -ne 0) {
    throw "Release consistency tests failed with exit code $LASTEXITCODE"
  }
  & node scripts/check-release-consistency.js
  if ($LASTEXITCODE -ne 0) {
    throw "Release consistency failed with exit code $LASTEXITCODE"
  }
  Pass "Source metadata and iOS baseline are internally consistent"

  $env:GEMINI_API_KEY = $env:GEMINI_API_KEY
  if (-not $env:GEMINI_API_KEY) {
    $env:GEMINI_API_KEY = "smoke-test-key"
  }
  $env:MUNEA_SKIP_ENV_LOCAL = "1"
  Remove-Item Env:MUNEA_DATABASE_PROVIDER -ErrorAction SilentlyContinue

  Step "Static smoke"
  & powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1 -SkipApi
  if ($LASTEXITCODE -ne 0) {
    throw "Static smoke failed with exit code $LASTEXITCODE"
  }
  Pass "Static smoke passed"

  if (-not $SkipAuth) {
    Step "Auth gate smoke"
    & powershell -ExecutionPolicy Bypass -File scripts/auth-gate-smoke.ps1 -BaseUrl $AuthBaseUrl
    if ($LASTEXITCODE -ne 0) {
      throw "Auth gate smoke failed with exit code $LASTEXITCODE"
    }
    Pass "Auth gate smoke passed"
  }

  Step "Supabase doctor"
  & powershell -ExecutionPolicy Bypass -File scripts/supabase-doctor.ps1 --allow-missing
  if ($LASTEXITCODE -ne 0) {
    throw "Supabase doctor failed with exit code $LASTEXITCODE"
  }
  Pass "Supabase doctor passed"

  Write-Host ""
  Write-Host "Release check complete." -ForegroundColor Green
} finally {
  foreach ($name in $envNames) {
    [Environment]::SetEnvironmentVariable($name, $previousEnv[$name], "Process")
  }
}
