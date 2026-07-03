param(
  [string]$Repo = "",
  [string]$Branch = "",
  [string]$HeadSha = "",
  [int]$PerPage = 10,
  [switch]$Wait,
  [int]$TimeoutSeconds = 600,
  [int]$PollSeconds = 15
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Resolve-GitHubRepo {
  $remote = (git remote get-url origin).Trim()
  if ($remote -match "github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)(\.git)?$") {
    return "$($Matches.owner)/$($Matches.repo)"
  }
  throw "Could not infer GitHub repo from origin remote: $remote"
}

function Resolve-Branch {
  $name = (git rev-parse --abbrev-ref HEAD).Trim()
  if ($name -eq "HEAD" -or -not $name) {
    return "main"
  }
  return $name
}

function Get-SmokeRun {
  param(
    [string]$RepoName,
    [string]$BranchName,
    [string]$Sha,
    [int]$Limit
  )

  $headers = @{ "User-Agent" = "Munea smoke-status" }
  $uri = "https://api.github.com/repos/$RepoName/actions/runs?branch=$BranchName&per_page=$Limit"
  $runs = Invoke-RestMethod -Headers $headers -Uri $uri
  $items = @($runs.workflow_runs | Where-Object { $_.name -eq "Smoke" })
  if ($Sha) {
    $items = @($items | Where-Object { $_.head_sha -like "$Sha*" })
  }
  if ($items.Count -eq 0) {
    return $null
  }
  return $items[0]
}

if (-not $Repo) {
  $Repo = Resolve-GitHubRepo
}
if (-not $Branch) {
  $Branch = Resolve-Branch
}
if (-not $HeadSha) {
  $HeadSha = (git rev-parse --short HEAD).Trim()
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
  $run = Get-SmokeRun -RepoName $Repo -BranchName $Branch -Sha $HeadSha -Limit $PerPage
  if (-not $run) {
    Write-Host "No Smoke workflow run found for $Repo branch $Branch head $HeadSha." -ForegroundColor Yellow
    exit 2
  }

  $shortSha = $run.head_sha.Substring(0, [Math]::Min(7, $run.head_sha.Length))
  Write-Host "Smoke $($run.status) / $($run.conclusion) for $shortSha"
  Write-Host $run.html_url

  if ($run.status -eq "completed") {
    if ($run.conclusion -eq "success") {
      exit 0
    }
    exit 1
  }

  if (-not $Wait) {
    exit 2
  }

  if ((Get-Date) -ge $deadline) {
    Write-Host "Timed out waiting for Smoke workflow." -ForegroundColor Yellow
    exit 2
  }
  Start-Sleep -Seconds $PollSeconds
} while ($true)
