param(
  [string]$Commit = "",
  [string]$SmokeRun = "",
  [ValidateSet("json", "supabase-staging", "supabase-production", "static-shell")]
  [string]$BackendMode = "json",
  [string]$Risk = "none",
  [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $Commit) {
  $Commit = (git rev-parse --short HEAD).Trim()
}

$statusLines = @(git status --short)
$dirtyState = if ($statusLines.Count -gt 0) { "dirty" } else { "clean" }
$date = Get-Date -Format "yyyy-MM-dd HH:mm zzz"

$lines = @(
  "# Munea Release Record",
  "",
  "- Date: $date",
  "- Commit: $Commit",
  "- Working tree: $dirtyState",
  "- Smoke run: $SmokeRun",
  "- Backend mode: $BackendMode",
  "- Known risk: $Risk",
  "",
  "## Verification",
  "",
  "- [ ] npm run release:check",
  "- [ ] GitHub Smoke workflow is green",
  "- [ ] Secrets are not present in web or Capacitor assets",
  "- [ ] Backend mode matches the release target",
  "- [ ] Rollback path is known",
  "",
  "## Notes",
  "",
  $(if ($Notes) { $Notes } else { "- No additional notes." })
)

$lines -join [Environment]::NewLine
