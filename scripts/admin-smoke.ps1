param(
  [string]$BaseUrl = "",
  [string]$AdminToken = "",
  [string]$AppKey = "",
  [string]$IdentityToken = "",
  [switch]$UseGcloudIdentityToken,
  [switch]$AllowHttp
)

$ErrorActionPreference = "Stop"
Import-Module Microsoft.PowerShell.Management
Import-Module Microsoft.PowerShell.Utility
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
if ($AppKey) {
  $identityHeaders["X-Munea-Key"] = $AppKey
}

$adminHeaders = @{}
foreach ($key in $identityHeaders.Keys) {
  $adminHeaders[$key] = $identityHeaders[$key]
}
if ($AdminToken) {
  $adminHeaders["X-Munea-Admin-Token"] = $AdminToken
}

# Must stay in lockstep with EP_LIST in web/src/admin.js. The static comparison
# below makes a newly added console endpoint fail smoke until it is covered here.
$adminReadBodies = [ordered]@{
  "/admin/north-star" = @{ days = 30 }
  "/admin/usage" = @{ days = 30 }
  "/admin/accounts" = @{ limit = 5 }
  "/admin/subscription-metrics" = @{ days = 30 }
  "/admin/feedback" = @{ limit = 5 }
  "/admin/safety-events" = @{ days = 30; limit = 5 }
  "/admin/privacy-requests" = @{ limit = 5 }
  "/admin/conversation-summaries" = @{ limit = 5 }
  "/admin/audit-events" = @{ limit = 5 }
}

Step "Admin page"
$adminPage = Invoke-WebRequest -Uri "$BaseUrl/admin.html" -Headers $identityHeaders -UseBasicParsing -TimeoutSec 30
if ($adminPage.StatusCode -ne 200) {
  throw "/admin.html returned HTTP $($adminPage.StatusCode)"
}
foreach ($token in @("Munea", 'id="sideNav"', 'id="pageRoot"', 'id="statusPill"', 'id="refreshBtn"', 'aria-live="polite"', "src/admin.js", "src/admin.css")) {
  if ($adminPage.Content -notmatch [regex]::Escape($token)) {
    throw "/admin.html missing token: $token"
  }
}
$adminScript = Invoke-WebRequest -Uri "$BaseUrl/src/admin.js" -Headers $identityHeaders -UseBasicParsing -TimeoutSec 30
if ($adminScript.StatusCode -ne 200) {
  throw "/src/admin.js returned HTTP $($adminScript.StatusCode)"
}
foreach ($token in @("apiBaseUrl", "adminToken", "renderSubscription", "/admin/subscription-metrics", "pts-cell", "MUNEA_ADMIN_APP_KEY", "REQUEST_TIMEOUT_MS", "normalizeAdminBaseUrl")) {
  if ($adminScript.Content -notmatch [regex]::Escape($token)) {
    throw "/src/admin.js missing token: $token"
  }
}
$consolePaths = @([regex]::Matches($adminScript.Content, '(?m)^\s+\w+:\s*\["(?<path>/admin/[^"?]+)"') | ForEach-Object { $_.Groups["path"].Value })
$missingSmokeCoverage = @($consolePaths | Where-Object { -not $adminReadBodies.Contains($_) })
$staleSmokeCoverage = @($adminReadBodies.Keys | Where-Object { $_ -notin $consolePaths })
if ($missingSmokeCoverage.Count -or $staleSmokeCoverage.Count) {
  throw ("Admin endpoint coverage drift. missingInSmoke=[{0}] staleInSmoke=[{1}]" -f ($missingSmokeCoverage -join ","), ($staleSmokeCoverage -join ","))
}
Pass "/admin.html and its dynamic console are reachable"

Step "Admin gate"
foreach ($entry in $adminReadBodies.GetEnumerator()) {
  Expect-AdminHttpError $entry.Key $entry.Value 403 $identityHeaders
}
Pass "all console read endpoints reject requests without admin token"

if (-not $AdminToken) {
  Skip "Admin token not provided; skipped privileged admin read checks"
  Write-Host ""
  Write-Host "Admin smoke complete with admin-token checks skipped." -ForegroundColor Yellow
  exit 0
}

Step "Admin reads"
$adminResults = @{}
foreach ($entry in $adminReadBodies.GetEnumerator()) {
  $result = Invoke-AdminJson $entry.Key $entry.Value $adminHeaders
  if (-not $result.ok) {
    throw "$($entry.Key) did not return ok:true"
  }
  $adminResults[$entry.Key] = $result
}

$credits = Invoke-AdminJson "/admin/credits" @{ limit = 5 } $adminHeaders
if (-not $credits.ok) {
  throw "/admin/credits did not return ok:true"
}
$accounts = $adminResults["/admin/accounts"]
$usage = $adminResults["/admin/usage"]
$privacy = $adminResults["/admin/privacy-requests"]
$feedback = $adminResults["/admin/feedback"]
$safety = $adminResults["/admin/safety-events"]
$audit = $adminResults["/admin/audit-events"]

Pass ("admin reads ok: accounts={0}, events={1}, privacy={2}, feedback={3}, safety={4}, audit={5}" -f `
  $accounts.count, $usage.totals.events, $privacy.count, ($feedback.latest.Count), $safety.count, $audit.count)

Write-Host ""
Write-Host "Admin smoke complete." -ForegroundColor Green
