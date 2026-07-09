param(
  [string]$BaseUrl = "",
  [string]$AdminToken = "",
  [string]$IdentityToken = "",
  [switch]$UseGcloudIdentityToken,
  [switch]$AllowHttp
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $BaseUrl) {
  $BaseUrl = $env:MUNEA_ADMIN_API_URL
}
if (-not $BaseUrl) {
  $BaseUrl = $env:MUNEA_STAGING_API_URL
}
if (-not $AdminToken) {
  $AdminToken = $env:MUNEA_ADMIN_API_TOKEN
}
if (-not $AdminToken) {
  $AdminToken = $env:MUNEA_STAGING_ADMIN_TOKEN
}
if (-not $IdentityToken) {
  $IdentityToken = $env:MUNEA_CLOUDRUN_IDENTITY_TOKEN
}

if (-not $BaseUrl) {
  throw "Set -BaseUrl, MUNEA_ADMIN_API_URL, or MUNEA_STAGING_API_URL before running admin smoke."
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

function Invoke-AdminJson($path, $body, $headers = @{}) {
  $json = $body | ConvertTo-Json -Depth 20 -Compress
  Invoke-RestMethod -Uri "$BaseUrl$path" -Method Post -ContentType "application/json; charset=utf-8" -Headers $headers -Body $json -TimeoutSec 30
}

function Expect-AdminHttpError($path, $body, $expectedStatus, $headers = @{}) {
  try {
    Invoke-AdminJson $path $body $headers | Out-Null
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
  throw "Admin smoke requires HTTPS for non-local URLs. Pass -AllowHttp only for local verification."
}

if ($UseGcloudIdentityToken -and -not $IdentityToken) {
  $IdentityToken = Get-GcloudIdentityToken
}

$identityHeaders = @{}
if ($IdentityToken) {
  $identityHeaders["Authorization"] = "Bearer $IdentityToken"
}

$adminHeaders = @{}
foreach ($key in $identityHeaders.Keys) {
  $adminHeaders[$key] = $identityHeaders[$key]
}
if ($AdminToken) {
  $adminHeaders["X-Munea-Admin-Token"] = $AdminToken
}

Step "Admin page"
$adminPage = Invoke-WebRequest -Uri "$BaseUrl/admin.html" -Headers $identityHeaders -UseBasicParsing -TimeoutSec 30
if ($adminPage.StatusCode -ne 200) {
  throw "/admin.html returned HTTP $($adminPage.StatusCode)"
}
foreach ($token in @("Munea Admin", "apiBaseUrl", "adminToken", "refreshAdmin")) {
  if ($adminPage.Content -notmatch [regex]::Escape($token)) {
    throw "/admin.html missing token: $token"
  }
}
Pass "/admin.html is reachable"

Step "Admin gate"
Expect-AdminHttpError "/admin/accounts" @{ limit = 1 } 403 $identityHeaders
Pass "/admin/accounts rejects requests without admin token"

if (-not $AdminToken) {
  Skip "Admin token not provided; skipped privileged admin read checks"
  Write-Host ""
  Write-Host "Admin smoke complete with admin-token checks skipped." -ForegroundColor Yellow
  exit 0
}

Step "Admin reads"
$accounts = Invoke-AdminJson "/admin/accounts" @{ limit = 5 } $adminHeaders
if (-not $accounts.ok) {
  throw "/admin/accounts did not return ok:true"
}

$northStar = Invoke-AdminJson "/admin/north-star" @{ days = 30 } $adminHeaders
if (-not $northStar.ok) {
  throw "/admin/north-star did not return ok:true"
}

$usage = Invoke-AdminJson "/admin/usage" @{ days = 30 } $adminHeaders
if (-not $usage.ok) {
  throw "/admin/usage did not return ok:true"
}

$credits = Invoke-AdminJson "/admin/credits" @{ limit = 5 } $adminHeaders
if (-not $credits.ok) {
  throw "/admin/credits did not return ok:true"
}

$summaries = Invoke-AdminJson "/admin/conversation-summaries" @{ limit = 5 } $adminHeaders
if (-not $summaries.ok) {
  throw "/admin/conversation-summaries did not return ok:true"
}

$privacy = Invoke-AdminJson "/admin/privacy-requests" @{ limit = 5 } $adminHeaders
if (-not $privacy.ok) {
  throw "/admin/privacy-requests did not return ok:true"
}

$safety = Invoke-AdminJson "/admin/safety-events" @{ days = 30; limit = 5 } $adminHeaders
if (-not $safety.ok) {
  throw "/admin/safety-events did not return ok:true"
}

$audit = Invoke-AdminJson "/admin/audit-events" @{ limit = 5 } $adminHeaders
if (-not $audit.ok) {
  throw "/admin/audit-events did not return ok:true"
}

Pass ("admin reads ok: accounts={0}, events={1}, privacy={2}, safety={3}, audit={4}" -f `
  $accounts.count, $usage.totals.events, $privacy.count, $safety.count, $audit.count)

Write-Host ""
Write-Host "Admin smoke complete." -ForegroundColor Green
