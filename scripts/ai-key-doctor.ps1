param(
  [Alias("allow-missing")]
  [switch]$AllowMissing
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

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

function Warn($message) {
  Write-Host "WARN $message" -ForegroundColor Yellow
}

function Fail($message) {
  Write-Host "FAIL $message" -ForegroundColor Red
}

function Read-DotenvIndex($path) {
  $index = @{}
  if (-not (Test-Path $path)) {
    return $index
  }

  $lineNumber = 0
  foreach ($raw in Get-Content -LiteralPath $path -Encoding UTF8) {
    $lineNumber += 1
    $line = $raw.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
      continue
    }

    $equalsIndex = $line.IndexOf("=")
    $key = $line.Substring(0, $equalsIndex).Trim()
    $value = $line.Substring($equalsIndex + 1).Trim().Trim('"').Trim("'")
    if ($key -match "^[A-Za-z_][A-Za-z0-9_]*$") {
      $index[$key] = [pscustomobject]@{
        Present = -not [string]::IsNullOrWhiteSpace($value)
        Line = $lineNumber
      }
    }
  }

  return $index
}

function Test-SkipEnvLocal {
  $value = [Environment]::GetEnvironmentVariable("MUNEA_SKIP_ENV_LOCAL", "Process")
  return $value -in @("1", "true", "TRUE", "yes", "YES")
}

function Get-KeySource($name, $dotenvIndex, $skipEnvLocal) {
  $envValue = [Environment]::GetEnvironmentVariable($name, "Process")
  $envPresent = -not [string]::IsNullOrWhiteSpace($envValue)
  $filePresent = $dotenvIndex.ContainsKey($name) -and $dotenvIndex[$name].Present

  if ($envPresent) {
    if (-not $skipEnvLocal -and $filePresent) {
      return "environment (overrides engine/.env.local)"
    }
    return "environment"
  }

  if ($skipEnvLocal -and $filePresent) {
    return "blocked by MUNEA_SKIP_ENV_LOCAL"
  }

  if ($filePresent) {
    return "engine/.env.local"
  }

  return "missing"
}

function Show-KeyStatus($name, $required, $dotenvIndex, $skipEnvLocal) {
  $source = Get-KeySource $name $dotenvIndex $skipEnvLocal
  $label = if ($required) { "required" } else { "optional" }

  if ($source -eq "missing" -or $source -eq "blocked by MUNEA_SKIP_ENV_LOCAL") {
    if ($required) {
      Fail "$name ($label): $source"
    } else {
      Warn "$name ($label): $source"
    }
  } else {
    Pass "$name ($label): present via $source"
  }

  return [pscustomobject]@{
    Name = $name
    Required = $required
    Source = $source
    Ready = ($source -ne "missing" -and $source -ne "blocked by MUNEA_SKIP_ENV_LOCAL")
  }
}

$envFile = Join-Path $root "engine\.env.local"
$dotenvIndex = Read-DotenvIndex $envFile
$skipEnvLocal = Test-SkipEnvLocal

Step "AI key preflight"
if (Test-Path $envFile) {
  Pass "engine/.env.local exists; values will not be printed"
} else {
  Warn "engine/.env.local is missing"
}

if ($skipEnvLocal) {
  Warn "MUNEA_SKIP_ENV_LOCAL is enabled; engine/.env.local will not be loaded"
} else {
  Pass "engine/.env.local loading is enabled"
}

$required = @("GEMINI_API_KEY")
$optional = @(
  "MUNEA_REFLEX_PROVIDER",
  "MUNEA_REFLEX_MODEL",
  "MUNEA_BUTLER_PROVIDER",
  "MUNEA_BUTLER_MODEL",
  "MUNEA_GUARDIAN_PROVIDER",
  "MUNEA_GUARDIAN_MODEL",
  "MUNEA_MODERATION_PROVIDER",
  "MUNEA_MODERATION_MODEL",
  "CWA_API_KEY",
  "MOENV_API_KEY"
)

Step "Provider keys"
$statuses = @()
foreach ($name in $required) {
  $statuses += Show-KeyStatus $name $true $dotenvIndex $skipEnvLocal
}
foreach ($name in $optional) {
  $statuses += Show-KeyStatus $name $false $dotenvIndex $skipEnvLocal
}

Step "Brain routing config"
$Python = Resolve-Python
$configJson = & $Python -c "import json, sys; sys.path.insert(0, 'engine'); import env_loader; loaded = env_loader.load_engine_env(); import model_router; config = model_router.brain_config(); print(json.dumps({'loadedKeys': loaded, 'brains': {k: {'provider': v.get('provider'), 'model': v.get('model')} for k, v in config.items()}}, ensure_ascii=False))"
if ($LASTEXITCODE -ne 0) {
  throw "Could not inspect model routing config"
}

$config = $configJson | ConvertFrom-Json
$loadedCount = @($config.loadedKeys).Count
Pass "env_loader loaded $loadedCount key name(s) in this process"
foreach ($brainName in @("reflex", "butler", "guardian")) {
  $brain = $config.brains.$brainName
  if ($brain) {
    Write-Host ("{0}: provider={1}, model={2}" -f $brainName, $brain.provider, $brain.model)
  }
}

$missingRequired = @($statuses | Where-Object { $_.Required -and -not $_.Ready })
if ($missingRequired.Count -gt 0) {
  $names = ($missingRequired | ForEach-Object { $_.Name }) -join ", "
  if ($AllowMissing) {
    Warn "Required AI key(s) not ready: $names"
    Write-Host ""
    Write-Host "AI key doctor completed with warnings." -ForegroundColor Yellow
    exit 0
  }

  throw "Required AI key(s) not ready: $names"
}

Write-Host ""
Write-Host "AI key doctor complete." -ForegroundColor Green
