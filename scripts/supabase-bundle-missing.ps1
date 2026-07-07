param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$BundleArgs
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

$Python = Resolve-Python
& $Python scripts\supabase_bundle_missing.py @BundleArgs
