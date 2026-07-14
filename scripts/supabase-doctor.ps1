param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$DoctorArgs
)

$ErrorActionPreference = "Stop"
Import-Module Microsoft.PowerShell.Management
Import-Module Microsoft.PowerShell.Utility
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
if (-not $env:PYTHONPYCACHEPREFIX) {
  $env:PYTHONPYCACHEPREFIX = Join-Path ([System.IO.Path]::GetTempPath()) "munea-pycache"
}

function Resolve-Python {
  $venvUnixPython = Join-Path $root ".venv/bin/python"
  if (Test-Path $venvUnixPython) {
    & $venvUnixPython --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return $venvUnixPython
    }
  }

  $venvPython = Join-Path $root ".venv\Scripts\python.exe"
  if (Test-Path $venvPython) {
    & $venvPython --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return $venvPython
    }
  }

  foreach ($candidate in @("python3", "python", "python.exe")) {
    $pythonCommand = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($pythonCommand) {
      & $pythonCommand.Source --version | Out-Null
      if ($LASTEXITCODE -eq 0) {
        return $pythonCommand.Source
      }
    }
  }

  throw "Python runtime not found. Create .venv or add python/python3 to PATH."
}

$Python = Resolve-Python
& $Python (Join-Path $root "scripts/supabase_doctor.py") @DoctorArgs
