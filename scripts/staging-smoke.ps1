param(
  [string]$BaseUrl = "",
  [string]$BearerToken = "",
  [string]$AdminToken = "",
  [string]$ProviderToken = "",
  [string]$AppKey = "",
  [string]$IdentityToken = "",
  [switch]$UseGcloudIdentityToken,
  [switch]$AllowHttp,
  [switch]$AllowJsonBackend,
  [switch]$AllowDeveloperBearer
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $BaseUrl) {
  $BaseUrl = $env:MUNEA_STAGING_API_URL
}

if (-not $BaseUrl) {
  throw "Set -BaseUrl or MUNEA_STAGING_API_URL before running staging smoke."
}

if (-not $AppKey) {
  $AppKey = $env:MUNEA_STAGING_APP_KEY
}
if (-not $AppKey) {
  $AppKey = $env:MUNEA_APP_KEY
}
if (-not $AppKey) {
  $appKeyPath = Join-Path $root "deploy\.munea-app-key"
  if (Test-Path -LiteralPath $appKeyPath) {
    $AppKey = (Get-Content -LiteralPath $appKeyPath -Raw).Trim()
  }
}

function Step($name) {
  Write-Host ""
  Write-Host "== $name ==" -ForegroundColor Cyan
}

function Pass($message) {
  Write-Host "PASS $message" -ForegroundColor Green
}

function Skip($message) {
  Write-Host "SKIP $message" -ForegroundColor Yellow
}

function Normalize-BaseUrl($url) {
  return $url.Trim().TrimEnd("/")
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

  throw "gcloud was not found. Install Google Cloud SDK or pass -IdentityToken."
}

function Get-GcloudIdentityToken {
  $gcloud = Resolve-Gcloud
  $output = & $gcloud auth print-identity-token 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw ($output -join "`n")
  }
  return (($output -join "`n").Trim())
}

function Get-StatusCode($errorRecord) {
  $response = $errorRecord.Exception.Response
  if ($response -and $response.StatusCode) {
    return [int]$response.StatusCode
  }
  throw $errorRecord
}

function Invoke-JsonPost($path, $body, $headers = @{}) {
  $json = $body | ConvertTo-Json -Depth 20 -Compress
  Invoke-RestMethod -Uri "$BaseUrl$path" -Method Post -ContentType "application/json; charset=utf-8" -Headers $headers -Body $json -TimeoutSec 30
}

function Merge-Headers($first, $second) {
  $merged = @{}
  foreach ($key in $first.Keys) {
    $merged[$key] = $first[$key]
  }
  foreach ($key in $second.Keys) {
    $merged[$key] = $second[$key]
  }
  return $merged
}

function Get-Health {
  foreach ($path in @("/healthz", "/healthz/")) {
    try {
      return Invoke-RestMethod -Uri "$BaseUrl$path" -Method Get -Headers $identityHeaders -TimeoutSec 30
    } catch {
      $status = Get-StatusCode $_
      if ($status -ne 404 -or $path -eq "/healthz/") {
        throw
      }
    }
  }
}

function Expect-HttpError($path, $body, $expectedStatus, $headers = @{}) {
  try {
    Invoke-JsonPost $path $body $headers | Out-Null
    throw "$path should have failed with HTTP $expectedStatus"
  } catch {
    $status = Get-StatusCode $_
    if ($status -ne $expectedStatus) {
      throw "$path returned HTTP $status, expected $expectedStatus"
    }
  }
}

$BaseUrl = Normalize-BaseUrl $BaseUrl
$uri = [System.Uri]$BaseUrl
$isLocal = $uri.Host -in @("localhost", "127.0.0.1", "::1")

if ($uri.Scheme -ne "https" -and -not $AllowHttp -and -not $isLocal) {
  throw "Staging smoke requires HTTPS for non-local URLs. Pass -AllowHttp only for local verification."
}

if ($UseGcloudIdentityToken -and -not $IdentityToken) {
  $IdentityToken = Get-GcloudIdentityToken
}

$identityHeaders = @{}
if ($IdentityToken) {
  $identityHeaders["X-Serverless-Authorization"] = "Bearer $IdentityToken"
}
if ($AppKey) {
  $identityHeaders["X-Munea-Key"] = $AppKey
}

$bearerHeaders = @{}
if ($BearerToken) {
  $bearerHeaders["Authorization"] = "Bearer $BearerToken"
}
$bearerHeaders = Merge-Headers $identityHeaders $bearerHeaders

$adminHeaders = @{}
if ($AdminToken) {
  $adminHeaders["X-Munea-Admin-Token"] = $AdminToken
}
$adminHeaders = Merge-Headers $identityHeaders $adminHeaders

$providerHeaders = @{}
if ($ProviderToken) {
  $providerHeaders["X-Munea-Provider-Token"] = $ProviderToken
}
$providerHeaders = Merge-Headers $identityHeaders $providerHeaders

Step "Health"
$health = Get-Health
if (-not $health.ok) {
  throw "/healthz did not return ok:true"
}
if (-not $health.runtime.authRequired) {
  throw "/healthz did not report runtime.authRequired=true"
}
if ($health.backend -and $health.backend.enabled -eq $false -and -not $AllowJsonBackend) {
  throw "/healthz reports backend.enabled=false; staging should not run on JSON fallback"
}
Pass "/healthz is reachable and auth-required"

Step "Unauthenticated user gate"
Expect-HttpError "/credits/balance" @{} 401 $identityHeaders
Expect-HttpError "/privacy-export" @{ action = "preview" } 401 $identityHeaders
Pass "User-scoped endpoints reject unauthenticated requests"

Step "Invalid auth token"
$invalidAuthHeaders = Merge-Headers $identityHeaders @{ Authorization = "Bearer invalid-staging-smoke-token" }
$invalidAuth = Invoke-JsonPost "/auth-status" @{} $invalidAuthHeaders
if ($invalidAuth.ok) {
  throw "/auth-status accepted an invalid bearer token"
}
Pass "/auth-status rejects invalid bearer tokens"

Step "Bearer session"
if ($BearerToken) {
  $auth = Invoke-JsonPost "/auth-status" @{} $bearerHeaders
  if (-not $auth.ok -or -not $auth.auth.verified) {
    throw "/auth-status did not accept the supplied bearer token"
  }
  if ($auth.auth.developerMode -and -not $AllowDeveloperBearer) {
    throw "Bearer token is a developer bypass token. Use a real Supabase Auth token for staging, or pass -AllowDeveloperBearer for local verification only."
  }
  $balance = Invoke-JsonPost "/credits/balance" @{} $bearerHeaders
  if (-not $balance.ok) {
    throw "/credits/balance did not accept the supplied bearer token"
  }
  $voice = Invoke-JsonPost "/voice-session" @{ locale = "zh-TW"; char = "nening" } $bearerHeaders
  if (-not $voice.ok) {
    throw "/voice-session did not return ok:true"
  }
  $privacy = Invoke-JsonPost "/privacy-export" @{ action = "preview" } $bearerHeaders
  if (-not $privacy.ok) {
    throw "/privacy-export did not return ok:true"
  }
  Pass "Bearer-auth session can reach user-scoped contracts"
} else {
  Skip "Bearer token not provided; skipped real session acceptance checks"
}

Step "Admin gate"
Expect-HttpError "/admin/usage" @{ days = 7 } 403 $identityHeaders
if ($AdminToken) {
  $usage = Invoke-JsonPost "/admin/usage" @{ days = 7 } $adminHeaders
  if (-not $usage.ok) {
    throw "/admin/usage did not accept admin token"
  }
  $entitlements = Invoke-JsonPost "/entitlements" @{ action = "save"; activePlan = "premium"; entitlements = @{ realtimeAvatar = $true } } $adminHeaders
  if (-not $entitlements.ok) {
    throw "/entitlements save did not accept admin token"
  }
  Pass "Admin token can reach admin and entitlement mutation contracts"
} else {
  Skip "Admin token not provided; checked rejection only"
}

Step "Provider webhook gate"
Expect-HttpError "/subscription-event" @{ provider = "revenuecat"; event = @{ type = "STAGING_SMOKE" } } 403 $identityHeaders
if ($ProviderToken) {
  $subscription = Invoke-JsonPost "/subscription-event" @{ provider = "revenuecat"; event = @{ type = "STAGING_SMOKE"; status = "active" } } $providerHeaders
  if (-not $subscription.ok) {
    throw "/subscription-event did not accept provider token"
  }
  Pass "Provider token can reach subscription event contract"
} else {
  Skip "Provider token not provided; checked rejection only"
}

Write-Host ""
Write-Host "Staging smoke complete." -ForegroundColor Green
