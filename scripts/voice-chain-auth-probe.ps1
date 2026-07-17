param(
  [string]$BrainUrl = "https://munea-brain-staging-491603544409.asia-east1.run.app",
  [string]$GatewayUrl = "https://munea-call-control-fiu65jd4da-de.a.run.app",
  [Parameter(Mandatory = $true)]
  [string]$VoiceCanaryUrl,
  [string]$SecretsEnvPath = "",
  [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"
Import-Module Microsoft.PowerShell.Management
Import-Module Microsoft.PowerShell.Utility

$root = Split-Path -Parent $PSScriptRoot
$previousLocation = Get-Location
Set-Location $root

function Step($name) {
  Write-Host ""
  Write-Host "== $name ==" -ForegroundColor Cyan
}

function Pass($message) {
  Write-Host "PASS $message" -ForegroundColor Green
}

function Resolve-SharedRoot {
  try {
    $commonDir = (& git rev-parse --git-common-dir 2>$null | Select-Object -First 1).Trim()
    if (-not $commonDir) { return $null }
    if (-not [System.IO.Path]::IsPathRooted($commonDir)) {
      $commonDir = Join-Path $root $commonDir
    }
    return Split-Path -Parent ([System.IO.Path]::GetFullPath($commonDir))
  } catch {
    return $null
  }
}

$envPaths = New-Object System.Collections.Generic.List[string]
if ($SecretsEnvPath) {
  $envPaths.Add([System.IO.Path]::GetFullPath($SecretsEnvPath))
} else {
  $envPaths.Add((Join-Path $root "engine\.env.local"))
  $sharedRoot = Resolve-SharedRoot
  if ($sharedRoot -and $sharedRoot -ne $root) {
    $envPaths.Add((Join-Path $sharedRoot "engine\.env.local"))
  }
}

function Get-LocalValue($name) {
  $value = [Environment]::GetEnvironmentVariable($name, "Process")
  if (-not [string]::IsNullOrWhiteSpace($value)) {
    return $value.Trim()
  }
  $escapedName = [regex]::Escape($name)
  foreach ($envPath in $envPaths) {
    if (-not (Test-Path -LiteralPath $envPath)) { continue }
    foreach ($line in Get-Content -LiteralPath $envPath) {
      if ($line -match "^\s*$escapedName\s*=\s*(.*)$") {
        return $matches[1].Trim().Trim('"').Trim("'")
      }
    }
  }
  return $null
}

function Resolve-AppKey {
  $value = Get-LocalValue "MUNEA_APP_KEY"
  if ($value) { return $value }
  $candidates = New-Object System.Collections.Generic.List[string]
  $candidates.Add((Join-Path $root "deploy\.munea-app-key"))
  $sharedRoot = Resolve-SharedRoot
  if ($sharedRoot -and $sharedRoot -ne $root) {
    $candidates.Add((Join-Path $sharedRoot "deploy\.munea-app-key"))
  }
  foreach ($path in $candidates) {
    if (Test-Path -LiteralPath $path) {
      return (Get-Content -LiteralPath $path -Raw).Trim()
    }
  }
  return $null
}

function Assert-ServiceUrl($value, $label, $allowedHosts) {
  try { $uri = [System.Uri]$value } catch { throw "$label is not a valid URL" }
  if ($uri.Scheme -ne "https" -or -not $uri.IsDefaultPort -or $uri.UserInfo -or
      $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -notin @("", "/") -or
      $uri.Host -notin $allowedHosts) {
    throw "$label must be a query-free HTTPS root URL for the approved Munea service"
  }
  return $value.TrimEnd("/")
}

function Assert-VoiceCanaryUrl($value) {
  try { $uri = [System.Uri]$value } catch { throw "VoiceCanaryUrl is not a valid URL" }
  $allowedSuffixes = @(
    "---munea-voice-staging-fiu65jd4da-de.a.run.app",
    "---munea-voice-staging-491603544409.asia-east1.run.app"
  )
  $allowedHost = $false
  foreach ($suffix in $allowedSuffixes) {
    if ($uri.Host.StartsWith("canary-") -and $uri.Host.EndsWith($suffix)) {
      $allowedHost = $true
      break
    }
  }
  if ($uri.Scheme -ne "wss" -or -not $uri.IsDefaultPort -or $uri.UserInfo -or
      $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -notin @("", "/") -or
      -not $allowedHost) {
    throw "VoiceCanaryUrl must be a query-free wss://canary-* tag for Munea staging Voice"
  }
  return $value.TrimEnd("/")
}

function Resolve-Python {
  foreach ($path in @(
    (Join-Path $root ".venv\Scripts\python.exe"),
    (Join-Path $root ".venv\bin\python")
  )) {
    if (Test-Path -LiteralPath $path) { return $path }
  }
  foreach ($candidate in @("python", "python3", "python.exe")) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
  }
  throw "Python runtime not found"
}

if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("MUNEA_ACCESS_TOKEN", "Process"))) {
  throw "Refusing to run while MUNEA_ACCESS_TOKEN is already set; this wrapper never reads or reuses a real user token"
}
if ($TimeoutSeconds -lt 5 -or $TimeoutSeconds -gt 60) {
  throw "TimeoutSeconds must be between 5 and 60"
}

$BrainUrl = Assert-ServiceUrl $BrainUrl "BrainUrl" @(
  "munea-brain-staging-491603544409.asia-east1.run.app",
  "munea-brain-staging-fiu65jd4da-de.a.run.app"
)
$GatewayUrl = Assert-ServiceUrl $GatewayUrl "GatewayUrl" @(
  "munea-call-control-fiu65jd4da-de.a.run.app"
)
$VoiceCanaryUrl = Assert-VoiceCanaryUrl $VoiceCanaryUrl

$SupabaseUrl = Get-LocalValue "SUPABASE_URL"
$ServiceRoleKey = Get-LocalValue "SUPABASE_SERVICE_ROLE_KEY"
$PublishableKey = Get-LocalValue "SUPABASE_PUBLISHABLE_KEY"
$AppKey = Resolve-AppKey
foreach ($required in @{
  SupabaseUrl = $SupabaseUrl
  ServiceRoleKey = $ServiceRoleKey
  PublishableKey = $PublishableKey
  AppKey = $AppKey
}.GetEnumerator()) {
  if ([string]::IsNullOrWhiteSpace([string]$required.Value)) {
    throw "$($required.Key) is required in the process environment or local backend env file"
  }
}
$SupabaseUrl = Assert-ServiceUrl $SupabaseUrl "SupabaseUrl" @(
  "fespbkdwafueyonppzwq.supabase.co"
)

$adminHeaders = @{
  apikey = $ServiceRoleKey
  "Content-Type" = "application/json; charset=utf-8"
}
if (-not $ServiceRoleKey.StartsWith("sb_secret_")) {
  $adminHeaders.Authorization = "Bearer $ServiceRoleKey"
}
$deleteHeaders = $adminHeaders.Clone()
$deleteHeaders.Prefer = "return=minimal"
$serverUserAgent = "Munea-Voice-Chain-Auth-Probe/1.0"
$python = Resolve-Python

$previousServiceRoleEnv = [Environment]::GetEnvironmentVariable("SUPABASE_SERVICE_ROLE_KEY", "Process")
$previousGatewayAdminEnv = [Environment]::GetEnvironmentVariable("MUNEA_GATEWAY_ADMIN_KEY", "Process")
$previousGatewayUrlEnv = [Environment]::GetEnvironmentVariable("MUNEA_GATEWAY_URL", "Process")
$previousAppKeyEnv = [Environment]::GetEnvironmentVariable("MUNEA_APP_KEY", "Process")
$userId = ""
$accountId = ""
$probeMarker = ""
$expectedAccountName = ""
$accessToken = ""
$password = ""
$tokenResponse = $null
$mainError = $null
$cleanupFailures = New-Object System.Collections.Generic.List[string]

try {
  Step "Create isolated Supabase Auth user"
  $suffix = [guid]::NewGuid().ToString("N")
  $probeMarker = "voice-chain-$suffix"
  $expectedAccountName = "Voice Chain Probe $probeMarker"
  $email = "munea-voice-chain-$suffix@example.com"
  $password = "Munea-$suffix!Aa1"
  $createBody = @{
    email = $email
    password = $password
    email_confirm = $true
    user_metadata = @{
      munea_test_account = $true
      purpose = "voice_chain_probe"
      probe_marker = $probeMarker
    }
  } | ConvertTo-Json -Depth 5 -Compress
  $created = Invoke-RestMethod -Uri "$SupabaseUrl/auth/v1/admin/users" -Method Post `
    -Headers $adminHeaders -UserAgent $serverUserAgent -Body $createBody -TimeoutSec 30
  $createdUser = if ($created.user) { $created.user } else { $created }
  $userId = [string]$createdUser.id
  $parsedUserId = [guid]::Empty
  if (-not [guid]::TryParse($userId, [ref]$parsedUserId)) {
    throw "Supabase admin create did not return a valid user id"
  }
  Pass "isolated Auth user created"

  Step "Issue disposable Supabase session"
  $tokenBody = @{ email = $email; password = $password } | ConvertTo-Json -Compress
  $tokenResponse = Invoke-RestMethod -Uri "$SupabaseUrl/auth/v1/token?grant_type=password" `
    -Method Post -Headers @{ apikey = $PublishableKey; "Content-Type" = "application/json; charset=utf-8" } `
    -UserAgent $serverUserAgent -Body $tokenBody -TimeoutSec 30
  $accessToken = [string]$tokenResponse.access_token
  if ([string]::IsNullOrWhiteSpace($accessToken)) {
    throw "Supabase password grant did not return an access token"
  }
  Pass "disposable session issued in memory"

  Step "Bootstrap isolated staging account"
  $apiHeaders = @{
    Authorization = "Bearer $accessToken"
    "X-Munea-Key" = $AppKey
  }
  $bootstrapBody = @{
    action = "create"
    accountName = $expectedAccountName
    displayName = $expectedAccountName
    locale = "zh-TW"
    companionProfile = @{
      templateId = "nening-real-female"
      displayName = "Munea"
      nameTouched = $true
    }
  } | ConvertTo-Json -Depth 6 -Compress
  $bootstrap = Invoke-RestMethod -Uri "$BrainUrl/account-bootstrap" -Method Post `
    -Headers $apiHeaders -ContentType "application/json; charset=utf-8" `
    -Body $bootstrapBody -TimeoutSec 30
  if (-not $bootstrap.ok -or -not $bootstrap.auth.verified) {
    throw "staging account bootstrap did not preserve verified auth"
  }
  $accountId = [string]$bootstrap.store.account.id
  $parsedAccountId = [guid]::Empty
  if (-not [guid]::TryParse($accountId, [ref]$parsedAccountId)) {
    throw "staging account bootstrap did not return a valid account id"
  }
  Pass "isolated account and trial wallet created"

  Step "Run production Gateway and staging Voice canary probe"
  [Environment]::SetEnvironmentVariable("SUPABASE_SERVICE_ROLE_KEY", $null, "Process")
  [Environment]::SetEnvironmentVariable("MUNEA_GATEWAY_ADMIN_KEY", $null, "Process")
  [Environment]::SetEnvironmentVariable("MUNEA_ACCESS_TOKEN", $accessToken, "Process")
  [Environment]::SetEnvironmentVariable("MUNEA_GATEWAY_URL", $GatewayUrl, "Process")
  [Environment]::SetEnvironmentVariable("MUNEA_APP_KEY", $AppKey, "Process")
  & $python (Join-Path $root "scripts\voice_chain_probe.py") `
    --profile production `
    --gateway-url $GatewayUrl `
    --voice-canary-url $VoiceCanaryUrl `
    --timeout $TimeoutSeconds
  if ($LASTEXITCODE -ne 0) {
    throw "Voice chain probe failed with exit code $LASTEXITCODE"
  }
  Pass "Gateway lease, Call Token and Voice canary handshake passed"
} catch {
  $mainError = $_
} finally {
  [Environment]::SetEnvironmentVariable("MUNEA_ACCESS_TOKEN", $null, "Process")
  [Environment]::SetEnvironmentVariable("SUPABASE_SERVICE_ROLE_KEY", $previousServiceRoleEnv, "Process")
  [Environment]::SetEnvironmentVariable("MUNEA_GATEWAY_ADMIN_KEY", $previousGatewayAdminEnv, "Process")
  [Environment]::SetEnvironmentVariable("MUNEA_GATEWAY_URL", $previousGatewayUrlEnv, "Process")
  [Environment]::SetEnvironmentVariable("MUNEA_APP_KEY", $previousAppKeyEnv, "Process")
  $accessToken = ""
  $password = ""
  $tokenResponse = $null

  if (-not $accountId -and $userId) {
    try {
      $membershipUri = "$SupabaseUrl/rest/v1/account_members?user_id=eq.$([uri]::EscapeDataString($userId))&select=account_id,user_id&limit=2"
      $memberships = @(Invoke-RestMethod -Uri $membershipUri -Method Get -Headers $adminHeaders `
        -UserAgent $serverUserAgent -TimeoutSec 30)
      if ($memberships.Count -eq 1 -and [string]$memberships[0].user_id -eq $userId) {
        $accountId = [string]$memberships[0].account_id
      } elseif ($memberships.Count -gt 1) {
        throw "temporary user resolved to multiple accounts"
      }
    } catch {
      $cleanupFailures.Add("temporary account lookup failed")
    }
  }

  $accountDeleteAuthorized = $false
  if ($accountId) {
    try {
      Step "Verify isolated account ownership before cleanup"
      if (-not $userId -or -not $probeMarker -or -not $expectedAccountName) {
        throw "temporary account cleanup markers are incomplete"
      }
      $accountIdFilter = [uri]::EscapeDataString($accountId)
      $userIdFilter = [uri]::EscapeDataString($userId)
      $membershipUri = "$SupabaseUrl/rest/v1/account_members?account_id=eq.$accountIdFilter&user_id=eq.$userIdFilter&select=account_id,user_id&limit=2"
      $memberships = @(Invoke-RestMethod -Uri $membershipUri -Method Get -Headers $adminHeaders `
        -UserAgent $serverUserAgent -TimeoutSec 30)
      if ($memberships.Count -ne 1 -or [string]$memberships[0].account_id -ne $accountId -or
          [string]$memberships[0].user_id -ne $userId) {
        throw "temporary account is not uniquely owned by the disposable Auth user"
      }

      $accountCheckUri = "$SupabaseUrl/rest/v1/accounts?id=eq.$accountIdFilter&select=id,name&limit=2"
      $accounts = @(Invoke-RestMethod -Uri $accountCheckUri -Method Get -Headers $adminHeaders `
        -UserAgent $serverUserAgent -TimeoutSec 30)
      if ($accounts.Count -ne 1 -or [string]$accounts[0].id -ne $accountId -or
          [string]$accounts[0].name -ne $expectedAccountName) {
        throw "temporary account marker did not match the disposable probe"
      }

      $authLookup = Invoke-RestMethod -Uri "$SupabaseUrl/auth/v1/admin/users/$userId" -Method Get `
        -Headers $adminHeaders -UserAgent $serverUserAgent -TimeoutSec 30
      $verifiedUser = if ($authLookup.user) { $authLookup.user } else { $authLookup }
      if ([string]$verifiedUser.id -ne $userId -or
          -not [bool]$verifiedUser.user_metadata.munea_test_account -or
          [string]$verifiedUser.user_metadata.purpose -ne "voice_chain_probe" -or
          [string]$verifiedUser.user_metadata.probe_marker -ne $probeMarker) {
        throw "temporary Auth user marker did not match the disposable probe"
      }
      $accountDeleteAuthorized = $true
      Pass "isolated account ownership and probe markers verified"
    } catch {
      $cleanupFailures.Add("temporary account ownership verification failed")
    }
  }

  if ($accountId -and $accountDeleteAuthorized) {
    try {
      Step "Delete isolated staging account"
      $accountUri = "$SupabaseUrl/rest/v1/accounts?id=eq.$([uri]::EscapeDataString($accountId))"
      Invoke-WebRequest -UseBasicParsing -Uri $accountUri -Method Delete -Headers $deleteHeaders `
        -UserAgent $serverUserAgent -TimeoutSec 30 | Out-Null
      Pass "isolated account deleted"
    } catch {
      $cleanupFailures.Add("temporary account deletion failed")
    }
  }

  if ($userId) {
    try {
      Step "Delete isolated Supabase Auth user"
      Invoke-WebRequest -UseBasicParsing -Uri "$SupabaseUrl/auth/v1/admin/users/$userId" `
        -Method Delete -Headers $adminHeaders -UserAgent $serverUserAgent -TimeoutSec 30 | Out-Null
      Pass "isolated Auth user deleted"
    } catch {
      $cleanupFailures.Add("temporary Auth user deletion failed")
    }
  }
  Set-Location $previousLocation
}

if ($cleanupFailures.Count -gt 0) {
  $detail = [string]::Join("; ", $cleanupFailures)
  if ($mainError) { $detail += "; probe error: " + $mainError.Exception.Message }
  throw "Voice chain probe cleanup failed: $detail"
}
if ($mainError) {
  throw $mainError
}

Write-Host ""
Write-Host "Disposable Voice chain auth probe complete." -ForegroundColor Green
