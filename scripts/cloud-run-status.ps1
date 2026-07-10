param(
  [string]$ProjectId = "gen-lang-client-0229303523",
  [string]$Region = "asia-east1",
  [string[]]$Services = @("munea-brain-staging", "munea-voice-staging"),
  [string[]]$Secrets = @("munea-gemini-key-staging", "munea-supabase-service-staging"),
  [switch]$Readiness,
  [switch]$Strict,
  [switch]$StrictReadiness
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($name) {
  Write-Host ""
  Write-Host "== $name ==" -ForegroundColor Cyan
}

function Pass($message) {
  Write-Host "PASS $message" -ForegroundColor Green
}

function Warn($message) {
  Write-Host "WARN $message" -ForegroundColor Yellow
}

function Fail($message) {
  Write-Host "FAIL $message" -ForegroundColor Red
  $script:Failures += $message
}

function ReadinessIssue($message) {
  Write-Host "WARN $message" -ForegroundColor Yellow
  $script:ReadinessIssues += $message
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

  throw "gcloud was not found. Install Google Cloud SDK or add gcloud to PATH."
}

function Invoke-GcloudJson($argsList) {
  $output = & $script:Gcloud @argsList 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw ($output -join "`n")
  }

  $text = ($output -join "`n").Trim()
  if (-not $text) {
    return $null
  }

  return $text | ConvertFrom-Json
}

function Invoke-GcloudText($argsList) {
  $output = & $script:Gcloud @argsList 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw ($output -join "`n")
  }

  return ($output -join "`n").Trim()
}

function Get-GcloudIdentityToken {
  return Invoke-GcloudText @("auth", "print-identity-token")
}

function Get-ConditionStatus($service, $conditionType) {
  $condition = @($service.status.conditions | Where-Object { $_.type -eq $conditionType } | Select-Object -First 1)
  if ($condition) {
    return $condition.status
  }
  return ""
}

function Get-ServiceAccountName($service) {
  if ($service.spec.template.spec.serviceAccountName) {
    return $service.spec.template.spec.serviceAccountName
  }
  if ($service.template.serviceAccount) {
    return $service.template.serviceAccount
  }
  return ""
}

function Get-EnvNames($service) {
  $containers = @()
  if ($service.spec.template.spec.containers) {
    $containers = @($service.spec.template.spec.containers)
  } elseif ($service.template.containers) {
    $containers = @($service.template.containers)
  }

  $names = @()
  foreach ($container in $containers) {
    foreach ($envVar in @($container.env)) {
      if ($envVar.name) {
        $names += $envVar.name
      }
    }
  }

  return @($names | Sort-Object -Unique)
}

function Test-SecretAccessor($policy, $member) {
  foreach ($binding in @($policy.bindings)) {
    if ($binding.role -ne "roles/secretmanager.secretAccessor") {
      continue
    }
    if (@($binding.members) -contains $member) {
      return $true
    }
  }
  return $false
}

$Failures = @()
$ReadinessIssues = @()
$Gcloud = Resolve-Gcloud

Step "Google Cloud project"
$account = Invoke-GcloudText @("auth", "list", "--filter=status:ACTIVE", "--format=value(account)")
if ($account) {
  Pass "active gcloud account: $account"
} else {
  Fail "no active gcloud account"
}

$project = Invoke-GcloudJson @("projects", "describe", $ProjectId, "--format=json")
if ($project.projectId -eq $ProjectId) {
  Pass "project found: $ProjectId ($($project.projectNumber))"
} else {
  Fail "project not found: $ProjectId"
}

$defaultComputeMember = "serviceAccount:$($project.projectNumber)-compute@developer.gserviceaccount.com"

Step "Cloud Run services"
$serviceAccounts = @{}
$serviceEnvIndex = @{}
$serviceUrls = @{}
foreach ($serviceName in $Services) {
  try {
    $service = Invoke-GcloudJson @("run", "services", "describe", $serviceName, "--region", $Region, "--project", $ProjectId, "--format=json")
    $ready = Get-ConditionStatus $service "Ready"
    $url = $service.status.url
    $serviceAccount = Get-ServiceAccountName $service
    $envNames = Get-EnvNames $service
    $serviceEnvIndex[$serviceName] = @($envNames)
    $serviceUrls[$serviceName] = $url

    if ($ready -eq "True") {
      Pass "$serviceName ready in $Region"
    } else {
      Fail "$serviceName is not Ready (status=$ready)"
    }

    if ($url) {
      Write-Host "URL  $url"
    } else {
      Warn "$serviceName has no URL"
    }

    if ($serviceAccount) {
      Write-Host "SA   $serviceAccount"
      $serviceAccounts[$serviceAccount] = $true
    } else {
      Warn "$serviceName uses the default runtime service account"
      $serviceAccounts[$defaultComputeMember.Replace("serviceAccount:", "")] = $true
    }

    if ($envNames.Count -gt 0) {
      Write-Host "ENV  $($envNames -join ', ')"
    } else {
      Warn "$serviceName has no visible environment variable names"
    }
  } catch {
    Fail "$serviceName could not be described: $($_.Exception.Message)"
  }
}

Step "Secret Manager"
$membersToCheck = @($defaultComputeMember)
foreach ($serviceAccount in $serviceAccounts.Keys) {
  if ($serviceAccount -and $serviceAccount.Contains("@")) {
    $membersToCheck += "serviceAccount:$serviceAccount"
  }
}
$membersToCheck = @($membersToCheck | Sort-Object -Unique)

foreach ($secretName in $Secrets) {
  try {
    $secret = Invoke-GcloudJson @("secrets", "describe", $secretName, "--project", $ProjectId, "--format=json")
    if ($secret.name) {
      Pass "$secretName exists"
    }

    $policy = Invoke-GcloudJson @("secrets", "get-iam-policy", $secretName, "--project", $ProjectId, "--format=json")
    $anyAccessor = $false
    foreach ($member in $membersToCheck) {
      if (Test-SecretAccessor $policy $member) {
        Pass "$secretName grants secretAccessor to $member"
        $anyAccessor = $true
      }
    }
    if (-not $anyAccessor) {
      Fail "$secretName has no secretAccessor binding for the checked Cloud Run service account(s)"
    }
  } catch {
    Fail "$secretName could not be checked: $($_.Exception.Message)"
  }
}

if ($Readiness) {
  Step "Staging readiness"

  $brainName = $Services | Where-Object { $_ -match "brain" } | Select-Object -First 1
  $voiceName = $Services | Where-Object { $_ -match "voice" } | Select-Object -First 1

  if ($brainName) {
    $brainEnv = @($serviceEnvIndex[$brainName])
    $requiredBrainEnv = @(
      "GEMINI_API_KEY",
      "MUNEA_DATABASE_PROVIDER",
      "MUNEA_ENV_NAME",
      "MUNEA_REQUIRE_AUTH",
      "MUNEA_ENABLE_DEV_AUTH_BYPASS",
      "MUNEA_ADMIN_API_TOKEN",
      "SUPABASE_URL",
      "SUPABASE_PUBLISHABLE_KEY",
      "SUPABASE_SERVICE_ROLE_KEY",
      "MUNEA_SUPABASE_ACCOUNT_ID",
      "MUNEA_SUPABASE_PERSON_ID",
      "MUNEA_SUPABASE_FAMILY_GROUP_ID"
    )
    foreach ($name in $requiredBrainEnv) {
      if ($brainEnv -contains $name) {
        Pass "$brainName env has $name"
      } else {
        ReadinessIssue "$brainName env missing $name"
      }
    }

    $brainUrl = $serviceUrls[$brainName]
    if ($brainUrl) {
      try {
        $identityToken = Get-GcloudIdentityToken
        $adminPage = Invoke-WebRequest -Uri "$brainUrl/admin.html" -Headers @{ Authorization = "Bearer $identityToken" } -UseBasicParsing -TimeoutSec 30
        if ($adminPage.StatusCode -eq 200 -and $adminPage.Content -match "Munea Admin") {
          Pass "$brainName serves /admin.html"
        } else {
          ReadinessIssue "$brainName /admin.html did not contain Munea Admin"
        }
      } catch {
        $status = ""
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
          $status = " HTTP $([int]$_.Exception.Response.StatusCode)"
        }
        ReadinessIssue "$brainName /admin.html is not ready$status"
      }
    } else {
      ReadinessIssue "$brainName has no URL for /admin.html check"
    }
  } else {
    ReadinessIssue "no brain service name found"
  }

  if ($voiceName) {
    $voiceEnv = @($serviceEnvIndex[$voiceName])
    foreach ($name in @("GEMINI_API_KEY", "MUNEA_SERVICE")) {
      if ($voiceEnv -contains $name) {
        Pass "$voiceName env has $name"
      } else {
        ReadinessIssue "$voiceName env missing $name"
      }
    }
  } else {
    ReadinessIssue "no voice service name found"
  }
}

Step "Summary"
if ($Failures.Count -eq 0 -and $ReadinessIssues.Count -eq 0) {
  Write-Host "Cloud Run status check complete." -ForegroundColor Green
  exit 0
}

if ($Failures.Count -gt 0) {
  Write-Host "Status issue(s):" -ForegroundColor Red
  foreach ($failure in $Failures) {
    Write-Host "- $failure" -ForegroundColor Red
  }
}

if ($Strict) {
  throw "Cloud Run status check failed with $($Failures.Count) issue(s)."
}

if ($ReadinessIssues.Count -gt 0) {
  Write-Host "Readiness issue(s):" -ForegroundColor Yellow
  foreach ($issue in $ReadinessIssues) {
    Write-Host "- $issue" -ForegroundColor Yellow
  }
  if ($StrictReadiness) {
    throw "Cloud Run readiness check failed with $($ReadinessIssues.Count) issue(s)."
  }
}

Warn "Cloud Run status check completed with $($Failures.Count) status issue(s) and $($ReadinessIssues.Count) readiness issue(s). Pass -Strict or -StrictReadiness to fail the command."
exit 0
