param(
  [string]$ManifestPath = "",
  [string]$GcloudPath = "",
  [switch]$Apply
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $ManifestPath) {
  $ManifestPath = Join-Path $root "deploy\monitoring\uptime-checks.json"
}
$ManifestPath = (Resolve-Path -LiteralPath $ManifestPath).Path
$manifest = Get-Content -Raw -Encoding utf8 -LiteralPath $ManifestPath | ConvertFrom-Json

if ($manifest.schema -ne "munea.cloud-monitoring.uptime.v1") {
  throw "Unsupported uptime manifest schema: $($manifest.schema)"
}
if ($manifest.project -ne "gen-lang-client-0229303523") {
  throw "Uptime manifest must stay pinned to gen-lang-client-0229303523"
}
if ($manifest.periodMinutes -ne 5) {
  throw "Uptime period must remain 5 minutes for the health evidence denominator"
}
if (@($manifest.regions).Count -lt 3) {
  throw "Cloud Monitoring uptime checks require at least three regions"
}

function Resolve-Gcloud {
  if ($GcloudPath) {
    return (Resolve-Path -LiteralPath $GcloudPath).Path
  }
  $command = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $command = Get-Command gcloud -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  if ($env:LOCALAPPDATA) {
    $bundled = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (Test-Path -LiteralPath $bundled) { return $bundled }
  }
  throw "gcloud was not found. Install Google Cloud SDK or add it to PATH."
}

function Invoke-Gcloud {
  param([string[]]$Arguments)
  $previousPreference = $ErrorActionPreference
  try {
    # Windows gcloud writes successful create/update notices to stderr.
    # Capture them, but decide failure exclusively from the native exit code.
    $ErrorActionPreference = "Continue"
    $output = & $script:Gcloud @Arguments 2>&1
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousPreference
  }
  if ($exitCode -ne 0) {
    throw "gcloud failed: $($output -join [Environment]::NewLine)"
  }
  return $output
}

function New-CreateArguments {
  param([object]$Target)
  $labels = "managed_by=munea_repo,component=service_slo,target_id=$($Target.id),environment=$($Target.environment)"
  $arguments = @(
    "monitoring", "uptime", "create", [string]$Target.displayName,
    "--project", [string]$manifest.project,
    "--resource-type", "uptime-url",
    "--resource-labels", "host=$($Target.host),project_id=$($manifest.project)",
    "--protocol", "https",
    "--port", "443",
    "--path", [string]$Target.path,
    "--request-method", "get",
    "--status-codes", (@($Target.statusCodes) -join ","),
    "--period", [string]$manifest.periodMinutes,
    "--timeout", [string]$manifest.timeoutSeconds,
    "--regions", (@($manifest.regions) -join ","),
    "--validate-ssl", "true",
    "--user-labels", $labels,
    "--format", "value(name)",
    "--quiet"
  )
  if ($Target.jsonOk -eq $true) {
    $arguments += @(
      "--matcher-type", "matches-json-path",
      "--matcher-content", "true",
      "--json-path", '$.ok',
      "--json-path-matcher-type", "exact-match"
    )
  }
  return $arguments
}

function New-UpdateArguments {
  param([object]$Target, [string]$CheckId)
  $arguments = @(
    "monitoring", "uptime", "update", $CheckId,
    "--project", [string]$manifest.project,
    "--display-name", [string]$Target.displayName,
    "--path", [string]$Target.path,
    "--port", "443",
    "--request-method", "get",
    "--set-status-codes", (@($Target.statusCodes) -join ","),
    "--period", [string]$manifest.periodMinutes,
    "--timeout", [string]$manifest.timeoutSeconds,
    "--set-regions", (@($manifest.regions) -join ","),
    "--validate-ssl", "true",
    "--format", "value(name)",
    "--quiet"
  )
  if ($Target.jsonOk -eq $true) {
    $arguments += @(
      "--matcher-type", "matches-json-path",
      "--matcher-content", "true",
      "--json-path", '$.ok',
      "--json-path-matcher-type", "exact-match"
    )
  }
  return $arguments
}

$Gcloud = Resolve-Gcloud
$currentJson = Invoke-Gcloud @(
  "monitoring", "uptime", "list-configs",
  "--project", [string]$manifest.project,
  "--format", "json"
)
$current = if (($currentJson -join "").Trim()) {
  @((($currentJson -join [Environment]::NewLine) | ConvertFrom-Json))
} else {
  @()
}

$seen = @{}
foreach ($target in @($manifest.targets)) {
  if (-not $target.id -or $seen.ContainsKey([string]$target.id)) {
    throw "Target ids must be non-empty and unique: $($target.id)"
  }
  $seen[[string]$target.id] = $true

  $matches = @($current | Where-Object {
    $_.userLabels.managed_by -eq "munea_repo" -and
    $_.userLabels.component -eq "service_slo" -and
    $_.userLabels.target_id -eq $target.id
  })
  if ($matches.Count -gt 1) {
    throw "Duplicate managed uptime checks found for target_id=$($target.id)"
  }

  if ($matches.Count -eq 1) {
    $existing = $matches[0]
    $existingHost = [string]$existing.monitoredResource.labels.host
    if ($existingHost -ne [string]$target.host) {
      throw "Host drift for $($target.id): existing=$existingHost desired=$($target.host). Recreate requires an explicit reviewed migration."
    }
    $checkId = ([string]$existing.name).Split("/")[-1]
    Write-Host ("ENSURE update {0} ({1})" -f $target.id, $checkId) -ForegroundColor Cyan
    if ($Apply) {
      Invoke-Gcloud (New-UpdateArguments -Target $target -CheckId $checkId) | Out-Null
    }
  } else {
    Write-Host ("ENSURE create {0} ({1}{2})" -f $target.id, $target.host, $target.path) -ForegroundColor Green
    if ($Apply) {
      Invoke-Gcloud (New-CreateArguments -Target $target) | Out-Null
    }
  }
}

$unexpected = @($current | Where-Object {
  $_.userLabels.managed_by -eq "munea_repo" -and
  $_.userLabels.component -eq "service_slo" -and
  -not $seen.ContainsKey([string]$_.userLabels.target_id)
})
if ($unexpected.Count) {
  Write-Warning ("Unexpected managed checks require manual review; nothing was deleted: {0}" -f (($unexpected | ForEach-Object { $_.displayName }) -join ", "))
}

if (-not $Apply) {
  Write-Host "PLAN ONLY: no Cloud Monitoring resources were changed. Re-run with -Apply after review." -ForegroundColor Yellow
} else {
  Write-Host ("APPLIED: ensured {0} uptime checks in {1}. No checks were deleted." -f @($manifest.targets).Count, $manifest.project) -ForegroundColor Green
}
