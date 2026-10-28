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
  "/admin/credits" = @{ limit = 5 }
  "/admin/medication-adherence" = @{ days = 30; limit = 5 }
  "/admin/family-health" = @{ days = 30; limit = 5 }
  "/admin/mood-trend" = @{ days = 30; limit = 5 }
  "/admin/bond-depth" = @{ days = 30; limit = 5; stuckDays = 14 }
  "/admin/growth-metrics" = @{ days = 30 }
}

Step "Admin page"
$adminPage = Invoke-WebRequest -Uri "$BaseUrl/admin.html" -Headers $identityHeaders -UseBasicParsing -TimeoutSec 30
if ($adminPage.StatusCode -ne 200) {
  throw "/admin.html returned HTTP $($adminPage.StatusCode)"
}
$requiredSecurityHeaders = [ordered]@{
  "X-Content-Type-Options" = "nosniff"
  "X-Frame-Options" = "DENY"
  "Referrer-Policy" = "no-referrer"
}
foreach ($entry in $requiredSecurityHeaders.GetEnumerator()) {
  $actual = [string]$adminPage.Headers[$entry.Key]
  if ($actual -ne $entry.Value) {
    throw "/admin.html header $($entry.Key) was '$actual', expected '$($entry.Value)'"
  }
}
$contentSecurityPolicy = [string]$adminPage.Headers["Content-Security-Policy"]
foreach ($directive in @("default-src 'none'", "frame-ancestors 'none'", "script-src 'self'")) {
  if ($contentSecurityPolicy -notmatch [regex]::Escape($directive)) {
    throw "/admin.html Content-Security-Policy missing directive: $directive"
  }
}
# 2026-10-28: statusPill was removed in the 2026-07-20 console redesign (#204) and
# test-admin-console.js now forbids it, yet this list kept requiring it, so the smoke
# has failed on every real server since then. Require lastUpdated/logoutBtn instead.
foreach ($token in @("Munea", 'id="sideNav"', 'id="pageRoot"', 'id="lastUpdated"', 'id="refreshBtn"', 'id="logoutBtn"', 'aria-live="polite"', "src/admin.js", "src/admin.css")) {
  if ($adminPage.Content -notmatch [regex]::Escape($token)) {
    throw "/admin.html missing token: $token"
  }
}
$adminScript = Invoke-WebRequest -Uri "$BaseUrl/src/admin.js" -Headers $identityHeaders -UseBasicParsing -TimeoutSec 30
if ($adminScript.StatusCode -ne 200) {
  throw "/src/admin.js returned HTTP $($adminScript.StatusCode)"
}
foreach ($token in @("apiBaseUrl", "ADMIN_TOKEN_KEY", "renderSubscription", "/admin/subscription-metrics", "pts-cell", "MUNEA_ADMIN_APP_KEY", "REQUEST_TIMEOUT_MS", "normalizeAdminBaseUrl")) {
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

# 2026-10-28: enterprise console pages load on demand and are not in EP_LIST, so the
# contract above never covered them; the org portal link is a separate, admin-token-free
# door. Both were untested by smoke until now:
#   - enterprise endpoints must reject requests without the admin token (403, same rule as EP_LIST)
#   - the org portal summary must answer ok:false to a missing/forged link and leak no field at all
# scripts/test-admin-console.js asserts this block stays in place.
$enterpriseGateBodies = [ordered]@{
  "/admin/enterprise/clients" = @{}
  "/admin/enterprise/invoices" = @{}
  "/admin/enterprise/billing-settings" = @{}
  "/admin/enterprise/portal/issue-link" = @{ clientId = "smoke-no-such-client" }
}

Step "Enterprise gate"
foreach ($entry in $enterpriseGateBodies.GetEnumerator()) {
  Expect-AdminHttpError $entry.Key $entry.Value 403 $identityHeaders
}
Pass "enterprise endpoints reject requests without admin token"

Step "Org portal link gate"
$portalSummaryFields = @("org", "seats", "usage", "guardian", "reports", "generatedAt", "expiresAt")
foreach ($body in @(@{}, @{ token = "smoke-not-a-real-portal-token" })) {
  $portal = Invoke-AdminJson "/enterprise/portal/summary" $body $identityHeaders
  if ($portal.ok) {
    throw "/enterprise/portal/summary accepted a missing or forged link token"
  }
  if ([string]$portal.error -ne "invalid_token") {
    throw "/enterprise/portal/summary returned error '$($portal.error)', expected 'invalid_token'"
  }
  foreach ($field in $portalSummaryFields) {
    if ($portal.PSObject.Properties.Name -contains $field) {
      throw "/enterprise/portal/summary leaked '$field' without a valid link token"
    }
  }
}
Pass "org portal summary refuses missing/forged links without leaking any numbers"

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

Step "Enterprise reads"
foreach ($path in @("/admin/enterprise/clients", "/admin/enterprise/invoices", "/admin/enterprise/billing-settings")) {
  $result = Invoke-AdminJson $path @{} $adminHeaders
  if (-not $result.ok) {
    throw "$path did not return ok:true"
  }
}
Pass "enterprise read endpoints ok with admin token"
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
