param(
  [string]$BaseUrl = "http://127.0.0.1:8200"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Resolve-Python {
  $venvPython = Join-Path $root ".venv\Scripts\python.exe"
  if (Test-Path $venvPython) {
    & $venvPython --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return $venvPython
    }
  }

  $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($pythonCommand) {
    & $pythonCommand.Source --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return $pythonCommand.Source
    }
  }

  throw "Python runtime not found. Create .venv or add python to PATH."
}

function Step($name) {
  Write-Host ""
  Write-Host "== $name ==" -ForegroundColor Cyan
}

function Pass($message) {
  Write-Host "PASS $message" -ForegroundColor Green
}

function Invoke-JsonPost($path, $body, $headers = @{}) {
  $json = $body | ConvertTo-Json -Depth 20 -Compress
  Invoke-RestMethod -Uri "$BaseUrl$path" -Method Post -ContentType "application/json; charset=utf-8" -Headers $headers -Body $json -TimeoutSec 30
}

function Expect-HttpError($path, $body, $expectedStatus, $headers = @{}) {
  try {
    Invoke-JsonPost $path $body $headers | Out-Null
    throw "$path should have failed with HTTP $expectedStatus"
  } catch {
    $status = $_.Exception.Response.StatusCode.value__
    if ($status -ne $expectedStatus) {
      throw "$path returned HTTP $status, expected $expectedStatus"
    }
  }
}

Step "Preflight"
try {
  Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/healthz" -TimeoutSec 2 | Out-Null
  throw "A server is already running at $BaseUrl. Stop it before running auth-gate smoke."
} catch {
  if ($_.Exception.Message -like "A server is already running*") {
    throw
  }
}
Pass "$BaseUrl is free"

$Python = Resolve-Python
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("munea-auth-smoke-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir | Out-Null
$proc = $null

$envNames = @(
  "MUNEA_REQUIRE_AUTH",
  "MUNEA_ENABLE_DEV_AUTH_BYPASS",
  "MUNEA_PORT",
  "MUNEA_ADMIN_API_TOKEN",
  "MUNEA_PROVIDER_WEBHOOK_TOKEN",
  "MUNEA_COMPANION_PROFILE_PATH",
  "MUNEA_APP_PROFILE_STORE_PATH",
  "MUNEA_BILLING_STORE_PATH",
  "MUNEA_CREDITS_STORE_PATH",
  "MUNEA_PRIVACY_REQUESTS_PATH",
  "MUNEA_PRODUCT_EVENTS_PATH",
  "MUNEA_AUDIT_EVENTS_STORE_PATH",
  "MUNEA_MEMORY_ITEMS_PATH",
  "MUNEA_PERCEPTION_SNAPSHOTS_PATH",
  "MUNEA_RELATIONSHIP_STATES_PATH"
)
$previousEnv = @{}
foreach ($name in $envNames) {
  $previousEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
  Step "Start auth-required engine"
  $uri = [System.Uri]$BaseUrl
  $env:MUNEA_PORT = [string]$uri.Port
  $env:MUNEA_REQUIRE_AUTH = "1"
  $env:MUNEA_ENABLE_DEV_AUTH_BYPASS = "true"
  $env:MUNEA_ADMIN_API_TOKEN = "admin-smoke-token"
  $env:MUNEA_PROVIDER_WEBHOOK_TOKEN = "provider-smoke-token"
  $env:MUNEA_COMPANION_PROFILE_PATH = Join-Path $tempDir "companion_profile.json"
  $env:MUNEA_APP_PROFILE_STORE_PATH = Join-Path $tempDir "app_profile_store.json"
  $env:MUNEA_BILLING_STORE_PATH = Join-Path $tempDir "billing_store.json"
  $env:MUNEA_CREDITS_STORE_PATH = Join-Path $tempDir "credits_store.json"
  $env:MUNEA_PRIVACY_REQUESTS_PATH = Join-Path $tempDir "privacy_requests.json"
  $env:MUNEA_PRODUCT_EVENTS_PATH = Join-Path $tempDir "product_events.json"
  $env:MUNEA_AUDIT_EVENTS_STORE_PATH = Join-Path $tempDir "audit_events_store.json"
  $env:MUNEA_MEMORY_ITEMS_PATH = Join-Path $tempDir "memory_items.json"
  $env:MUNEA_PERCEPTION_SNAPSHOTS_PATH = Join-Path $tempDir "perception_snapshots.json"
  $env:MUNEA_RELATIONSHIP_STATES_PATH = Join-Path $tempDir "relationship_states.json"

  $stdout = Join-Path $tempDir "engine.out.log"
  $stderr = Join-Path $tempDir "engine.err.log"
  $proc = Start-Process -FilePath $Python -ArgumentList "engine\server.py" -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
      Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/healthz" -TimeoutSec 2 | Out-Null
      $ready = $true
      break
    } catch {}
  }
  if (-not $ready) {
    throw "Auth-required engine did not become ready on $BaseUrl"
  }
  Pass "Auth-required engine started"

  $devHeaders = @{ Authorization = "Bearer dev-local-token-00000000-0000-4000-8000-000000000001" }
  $adminHeaders = @{ "X-Munea-Admin-Token" = "admin-smoke-token" }
  $providerHeaders = @{ "X-Munea-Provider-Token" = "provider-smoke-token" }

  Step "Runtime marker"
  $health = Invoke-RestMethod -Uri "$BaseUrl/healthz" -Method Get -TimeoutSec 30
  if (-not $health.runtime.authRequired) {
    throw "/healthz did not report authRequired=true"
  }
  Pass "/healthz reports auth-required mode"

  Step "User bearer gate"
  Expect-HttpError "/credits/balance" @{} 401
  $balance = Invoke-JsonPost "/credits/balance" @{} $devHeaders
  if (-not $balance.ok) {
    throw "/credits/balance did not accept verified dev bearer"
  }
  Pass "User-scoped endpoint requires and accepts verified bearer"

  Step "Admin gate"
  Expect-HttpError "/admin/usage" @{ days = 7 } 403
  $usage = Invoke-JsonPost "/admin/usage" @{ days = 7 } $adminHeaders
  if (-not $usage.ok) {
    throw "/admin/usage did not accept admin token"
  }
  Pass "Admin endpoint requires admin token"

  Step "Privileged billing mutation gate"
  Expect-HttpError "/credits/grant" @{ amount = 1; walletType = "included_monthly"; source = "included_monthly"; reason = "auth smoke"; idempotencyKey = "auth-smoke-dev-denied" } 403 $devHeaders
  $grant = Invoke-JsonPost "/credits/grant" @{ amount = 1; walletType = "included_monthly"; source = "included_monthly"; reason = "auth smoke"; idempotencyKey = "auth-smoke-admin-grant" } $adminHeaders
  if (-not $grant.ok) {
    throw "/credits/grant did not accept admin token"
  }
  Pass "Credit grants reject user bearer and accept admin token"

  Step "Provider webhook gate"
  Expect-HttpError "/subscription-event" @{ provider = "revenuecat"; event = @{ type = "TEST" } } 403
  $sub = Invoke-JsonPost "/subscription-event" @{ provider = "revenuecat"; event = @{ type = "TEST"; status = "active" } } $providerHeaders
  if (-not $sub.ok) {
    throw "/subscription-event did not accept provider token"
  }
  Pass "Subscription event requires privileged provider/admin token"

  Step "Entitlement mutation gate"
  Expect-HttpError "/entitlements" @{ action = "save"; activePlan = "premium" } 403 $devHeaders
  $entitlements = Invoke-JsonPost "/entitlements" @{ action = "save"; activePlan = "premium"; entitlements = @{ realtimeAvatar = $true } } $adminHeaders
  if (-not $entitlements.ok) {
    throw "/entitlements save did not accept admin token"
  }
  Pass "Entitlement mutation rejects user bearer and accepts admin token"

  Write-Host ""
  Write-Host "Auth-gate smoke complete." -ForegroundColor Green
} finally {
  if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
  foreach ($name in $envNames) {
    [Environment]::SetEnvironmentVariable($name, $previousEnv[$name], "Process")
  }
  Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
