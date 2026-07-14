param(
  [string]$GatewayUrl = "https://munea-call-control-491603544409.asia-east1.run.app",
  [string]$ProjectId = "gen-lang-client-0229303523",
  [string]$AdminSecret = "munea-gateway-admin-key",
  [string]$AvatarUrl = "https://tw-07.access.glows.ai:26969",
  [string]$AvatarWorkerId = "glows-rtx6000ada-tw07",
  [string]$VoiceUrl = "wss://munea-voice-staging-491603544409.asia-east1.run.app",
  [string]$VoiceShardId = "gemini-live-asia-east1-01",
  [int]$CommittedCapacity = 3
)

$ErrorActionPreference = "Stop"
$GatewayUrl = $GatewayUrl.TrimEnd("/")
if ($CommittedCapacity -lt 1 -or $CommittedCapacity -gt 3) {
  throw "Initial production commitment must stay between 1 and 3 until backup soak tests pass"
}

$adminToken = (& gcloud.cmd secrets versions access latest --secret=$AdminSecret --project=$ProjectId).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($adminToken)) {
  throw "Could not read Gateway admin secret"
}
$headers = @{ Authorization = "Bearer $adminToken" }

function Post-Json([string]$Path, [hashtable]$Body) {
  return Invoke-RestMethod -Method Post -Uri ($GatewayUrl + $Path) -Headers $headers `
    -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 8) -TimeoutSec 30
}

$health = Invoke-RestMethod -Uri ($GatewayUrl + "/health") -Headers $headers -TimeoutSec 30
if (-not $health.durable_ready) {
  throw "Gateway durable storage is not ready: $($health.durable_error)"
}

Post-Json "/v1/internal/workers" @{
  worker_id = $AvatarWorkerId
  provider_instance_id = "ins-1y27kl5g"
  url = $AvatarUrl
  provider = "glows"
  region = "TW-04"
  capacity = $CommittedCapacity
  status = "ready"
  hourly_cost = 2.42
  active_leases = 0
} | Out-Null

Post-Json "/v1/internal/voice-shards" @{
  shard_id = $VoiceShardId
  url = $VoiceUrl
  provider = "gemini-live"
  region = "asia-east1"
  capacity = $CommittedCapacity
  status = "ready"
} | Out-Null

$verified = Invoke-RestMethod -Uri ($GatewayUrl + "/health") -Headers $headers -TimeoutSec 30
if (-not $verified.ok -or -not $verified.durable_ready) {
  throw "Gateway health gate failed after capacity registration"
}
if ([int]$verified.snapshot.avatar_capacity -lt $CommittedCapacity) {
  throw "Avatar capacity registration did not reach $CommittedCapacity"
}
if ([int]$verified.snapshot.voice_capacity -lt $CommittedCapacity) {
  throw "Voice capacity registration did not reach $CommittedCapacity"
}

[ordered]@{
  ok = $true
  committed_capacity = $CommittedCapacity
  avatar_capacity = [int]$verified.snapshot.avatar_capacity
  voice_capacity = [int]$verified.snapshot.voice_capacity
  queue_depth = [int]$verified.snapshot.queue_depth
} | ConvertTo-Json
