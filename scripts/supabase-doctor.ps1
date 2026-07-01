param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$DoctorArgs
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Resolve-Python {
  $venvPython = Join-Path $root ".venv\Scripts\python.exe"
  if (Test-Path $venvPython) {
    return $venvPython
  }

  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCommand) {
    return $pythonCommand.Source
  }

  throw "Python runtime not found. Create .venv or add python to PATH."
}

$Python = Resolve-Python
& $Python scripts\supabase_doctor.py @DoctorArgs
