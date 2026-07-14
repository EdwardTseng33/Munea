param(
  [string]$Target = "$env:USERPROFILE\.codex\skills"
)

$ErrorActionPreference = "Stop"
Import-Module Microsoft.PowerShell.Management
Import-Module Microsoft.PowerShell.Utility

$repoRoot = Split-Path -Parent $PSScriptRoot
$skillsRoot = Join-Path $repoRoot "codex-skills"
$skills = @("cto-context-architect", "munea-cto")

New-Item -ItemType Directory -Force $Target | Out-Null

foreach ($skill in $skills) {
  $source = Join-Path $skillsRoot $skill
  if (-not (Test-Path $source)) {
    throw "Missing skill source: $source"
  }

  Copy-Item -Recurse -Force $source $Target
  Write-Host "Installed $skill"
}

Write-Host "Codex skills installed to $Target"
