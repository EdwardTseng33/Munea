param(
  [string]$BaseUrl = "",
  [string]$SupabaseUrl = "",
  [string]$ServiceRoleKey = "",
  [string]$PublishableKey = "",
  [string]$AppKey = ""
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

function Get-LocalValue($name) {
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

if (-not $BaseUrl) {
  $BaseUrl = $env:MUNEA_STAGING_API_URL
}
if (-not $BaseUrl) {
  $BaseUrl = "https://munea-brain-staging-491603544409.asia-east1.run.app"
}
if (-not $SupabaseUrl) {
  $SupabaseUrl = Get-LocalValue "SUPABASE_URL"
}
if (-not $ServiceRoleKey) {
  $ServiceRoleKey = Get-LocalValue "SUPABASE_SERVICE_ROLE_KEY"
}
if (-not $PublishableKey) {
  $PublishableKey = Get-LocalValue "SUPABASE_PUBLISHABLE_KEY"
}
if (-not $AppKey) {
  $AppKey = Get-LocalValue "MUNEA_APP_KEY"
}
if (-not $AppKey) {
  $appKeyPath = Join-Path $root "deploy\.munea-app-key"
  if (Test-Path -LiteralPath $appKeyPath) {
    $AppKey = (Get-Content -LiteralPath $appKeyPath -Raw).Trim()
  }
}

foreach ($required in @{
  BaseUrl = $BaseUrl
  SupabaseUrl = $SupabaseUrl
  ServiceRoleKey = $ServiceRoleKey
  PublishableKey = $PublishableKey
  AppKey = $AppKey
}.GetEnumerator()) {
  if ([string]::IsNullOrWhiteSpace([string]$required.Value)) {
    throw "$($required.Key) is required for live staging auth smoke"
  }
}

$BaseUrl = $BaseUrl.TrimEnd("/")
$SupabaseUrl = $SupabaseUrl.TrimEnd("/")
$adminHeaders = @{
  apikey = $ServiceRoleKey
  "Content-Type" = "application/json; charset=utf-8"
}
if (-not $ServiceRoleKey.StartsWith("sb_secret_")) {
  $adminHeaders.Authorization = "Bearer $ServiceRoleKey"
}
$serverUserAgent = "Munea-Staging-Auth-Smoke/1.0"
$userId = $null

try {
  Step "Create temporary Supabase Auth user"
  $suffix = [guid]::NewGuid().ToString("N")
  $email = "munea-auth-smoke-$suffix@example.com"
  $password = "Munea-$suffix!Aa1"
  $createBody = @{
    email = $email
    password = $password
    email_confirm = $true
    user_metadata = @{
      munea_test_account = $true
      purpose = "staging_auth_smoke"
    }
  } | ConvertTo-Json -Depth 5 -Compress
  $created = Invoke-RestMethod -Uri "$SupabaseUrl/auth/v1/admin/users" -Method Post -Headers $adminHeaders -UserAgent $serverUserAgent -Body $createBody -TimeoutSec 30
  $createdUser = if ($created.user) { $created.user } else { $created }
  $userId = [string]$createdUser.id
  $parsedUserId = [guid]::Empty
  if (-not [guid]::TryParse($userId, [ref]$parsedUserId)) {
    throw "Supabase admin create did not return a valid user id"
  }
  Pass "temporary user created"

  Step "Create real Supabase session"
  $tokenBody = @{ email = $email; password = $password } | ConvertTo-Json -Compress
  $tokenResponse = Invoke-RestMethod `
    -Uri "$SupabaseUrl/auth/v1/token?grant_type=password" `
    -Method Post `
    -Headers @{ apikey = $PublishableKey; "Content-Type" = "application/json; charset=utf-8" } `
    -UserAgent $serverUserAgent `
    -Body $tokenBody `
    -TimeoutSec 30
  $accessToken = [string]$tokenResponse.access_token
  if ([string]::IsNullOrWhiteSpace($accessToken)) {
    throw "Supabase password grant did not return an access token"
  }
  Pass "real access token issued"

  $apiHeaders = @{
    Authorization = "Bearer $accessToken"
    "X-Munea-Key" = $AppKey
  }

  Step "Verify token through Munea backend"
  $authStatus = Invoke-RestMethod -Uri "$BaseUrl/auth-status" -Method Post -Headers $apiHeaders -ContentType "application/json; charset=utf-8" -Body "{}" -TimeoutSec 30
  if (-not $authStatus.ok -or -not $authStatus.auth.verified) {
    throw "Munea backend rejected the real Supabase access token"
  }
  if ([string]$authStatus.auth.authUserId -ne $userId) {
    throw "Munea backend did not derive the Supabase auth user id"
  }
  if ($authStatus.auth.developerMode) {
    throw "Live Supabase auth was incorrectly marked as developer mode"
  }
  Pass "backend verified the real Supabase session"

  Step "Verify account bootstrap identity bridge"
  $previewBody = @{
    action = "preview"
    displayName = "Staging Auth Smoke"
    companionProfile = @{
      templateId = "nening-real-female"
      displayName = "Munea"
      nameTouched = $true
    }
  } | ConvertTo-Json -Depth 5 -Compress
  $preview = Invoke-RestMethod -Uri "$BaseUrl/account-bootstrap" -Method Post -Headers $apiHeaders -ContentType "application/json; charset=utf-8" -Body $previewBody -TimeoutSec 30
  if (-not $preview.ok -or -not $preview.auth.verified) {
    throw "Account bootstrap preview did not preserve verified auth"
  }
  if ([string]$preview.auth.authUserId -ne $userId) {
    throw "Account bootstrap preview did not use token-derived identity"
  }
  Pass "account bootstrap uses token-derived identity without writing rows"
} finally {
  if ($userId) {
    Step "Delete temporary Supabase Auth user"
    Invoke-RestMethod -Uri "$SupabaseUrl/auth/v1/admin/users/$userId" -Method Delete -Headers $adminHeaders -UserAgent $serverUserAgent -TimeoutSec 30 | Out-Null
    Pass "temporary user deleted"
  }
}

Write-Host ""
Write-Host "Live staging auth smoke complete." -ForegroundColor Green
