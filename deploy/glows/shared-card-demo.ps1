[CmdletBinding()]
param(
  [ValidateSet('Deploy', 'Start', 'Stop', 'Restart', 'Status', 'Logs', 'Probe')]
  [string]$Action = 'Status',
  [string]$SshHost = 'tw-07.access.glows.ai',
  [int]$SshPort = 25680,
  [string]$SshUser = 'glows',
  [string]$KeyPath = '',
  [string]$PublicUrl = '',
  [int]$FrameSize = 768
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ([string]::IsNullOrWhiteSpace($KeyPath)) { $KeyPath = Join-Path $PSScriptRoot 'glows_ed25519' }
$RemoteRoot = '/home/glows/munea-demo'
$Target = "${SshUser}@${SshHost}"
$DemoPassword = [Environment]::GetEnvironmentVariable('MUNEA_DEMO_ACCESS_PASSWORD')

if (-not (Test-Path -LiteralPath $KeyPath)) {
  throw "Glows SSH key not found: $KeyPath"
}

function Assert-LastCommand([string]$Label) {
  if ($LASTEXITCODE -ne 0) { throw ('{0} failed with exit code {1}' -f $Label, $LASTEXITCODE) }
}

function Invoke-Remote([string]$Command) {
  & ssh -o StrictHostKeyChecking=accept-new -i $KeyPath -p $SshPort $Target $Command
  Assert-LastCommand 'Glows remote command'
}

function Invoke-Manager([string]$ManagerAction) {
  $RemoteCommand = 'MUNEA_DEMO_ROOT={0} bash {0}/manage-shared-demo.sh {1}' -f $RemoteRoot, $ManagerAction
  Invoke-Remote $RemoteCommand
}

if ($Action -eq 'Deploy') {
  if ([string]::IsNullOrWhiteSpace($DemoPassword)) {
    throw 'Set MUNEA_DEMO_ACCESS_PASSWORD first. The cleartext password is never written to disk.'
  }

  Invoke-Remote "install -d -m 700 $RemoteRoot $RemoteRoot/assets $RemoteRoot/portraits"

  $Uploads = @(
    @{ Local = (Join-Path $RepoRoot 'deploy\runpod-avatar\flashhead_server.py'); Remote = "$RemoteRoot/flashhead_server.py" },
    @{ Local = (Join-Path $RepoRoot 'deploy\runpod-avatar\flashhead_engine_core.py'); Remote = "$RemoteRoot/flashhead_engine_core.py" },
    @{ Local = (Join-Path $RepoRoot 'deploy\runpod-avatar\sync-face-assets.py'); Remote = "$RemoteRoot/sync-face-assets.py" },
    @{ Local = (Join-Path $PSScriptRoot 'manage-shared-demo.sh'); Remote = "$RemoteRoot/manage-shared-demo.sh" },
    @{ Local = (Join-Path $RepoRoot 'munea-b2b\flashhead\bg-a05.png'); Remote = "$RemoteRoot/portraits/bg-a05.png" },
    @{ Local = (Join-Path $RepoRoot 'munea-b2b\flashhead\bg-a06.png'); Remote = "$RemoteRoot/portraits/bg-a06.png" }
  )
  foreach ($Item in $Uploads) {
    & scp -q -o StrictHostKeyChecking=accept-new -i $KeyPath -P $SshPort $Item.Local "${Target}:$($Item.Remote)"
    Assert-LastCommand "Upload $($Item.Local)"
  }

  $Bytes = [Text.Encoding]::UTF8.GetBytes($DemoPassword.Replace(' ', '').ToLowerInvariant())
  $Hasher = [Security.Cryptography.SHA256]::Create()
  try { $HashBytes = $Hasher.ComputeHash($Bytes) } finally { $Hasher.Dispose() }
  $PasswordHash = ([BitConverter]::ToString($HashBytes)).Replace('-', '').ToLowerInvariant()
  $EnvText = @"
MUNEA_FH_REPO=/home/glows/SoulX-FlashHead
MUNEA_FH_MODEL_ROOT=/home/glows/models
MUNEA_FH_CHAR_A05D=$RemoteRoot/assets/char-a05B-demo.png
MUNEA_FH_CHAR_A06D=$RemoteRoot/assets/char-a06B-demo.png
MUNEA_FH_DEFAULT_CHAR=a05d
MUNEA_FH_ALLOWED_CHARS=a05d,a06d
MUNEA_FH_LANE=demo
MUNEA_FH_FRAME_SIZE=$FrameSize
MUNEA_FH_SLOTS=1
MUNEA_FH_COMPILE=0
MUNEA_FH_AUDIO_PREBUFFER_S=0.35
MUNEA_FH_OPENING_PREBUFFER_S=1.0
MUNEA_FACE_PORT=8188
MUNEA_WORKER_ID=glows-rtx6000ada-tw07-demo
MUNEA_DEMO_PASSWORD_SHA256=$PasswordHash
MUNEA_DEMO_TOKEN_TTL=300
MUNEA_WORKER_CORS_ORIGINS=https://munea-b2b.vercel.app,http://localhost,https://localhost
"@
  $EnvText | & ssh -o StrictHostKeyChecking=accept-new -i $KeyPath -p $SshPort $Target "umask 077; cat > $RemoteRoot/demo.env"
  Assert-LastCommand 'Write Demo configuration'

  Invoke-Remote "chmod 700 $RemoteRoot/manage-shared-demo.sh; /home/glows/miniconda3/envs/workenv/bin/python $RemoteRoot/sync-face-assets.py --source $RemoteRoot/portraits --target-dir $RemoteRoot/assets --lane demo --frame-size $FrameSize"
  Invoke-Manager 'restart'
  Write-Host "Demo started independently: ${FrameSize}x${FrameSize}, one slot. App was not restarted."
  exit 0
}

switch ($Action) {
  'Start'   { Invoke-Manager 'start' }
  'Stop'    { Invoke-Manager 'stop' }
  'Restart' { Invoke-Manager 'restart' }
  'Status'  {
    Invoke-Manager 'status'
    Invoke-Remote "printf 'app='; pgrep -af '/home/glows/flashhead_server.py' | grep -v pgrep || true; nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader"
  }
  'Logs'    { Invoke-Manager 'logs' }
  'Probe'   {
    if ([string]::IsNullOrWhiteSpace($PublicUrl)) { throw 'Probe requires -PublicUrl.' }
    if ([string]::IsNullOrWhiteSpace($DemoPassword)) { throw 'Probe requires MUNEA_DEMO_ACCESS_PASSWORD.' }
    $Base = $PublicUrl.TrimEnd('/')
    $Body = @{ password = $DemoPassword } | ConvertTo-Json -Compress
    $Session = Invoke-RestMethod -Method Post -Uri "$Base/demo/session" -ContentType 'application/json' -Body $Body -TimeoutSec 20
    $Health = Invoke-RestMethod -Method Get -Uri "$Base/health?token=$([Uri]::EscapeDataString($Session.token))" -TimeoutSec 20
    [pscustomobject]@{
      ok = $Health.ok
      lane = $Health.lane
      resolution = "$($Health.frame_size)x$($Health.frame_size)"
      character = $Health.char
      slots = $Health.capacity.limit
      active = $Health.capacity.active
    } | Format-List
  }
}
