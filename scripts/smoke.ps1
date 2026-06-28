param(
  [string]$BaseUrl = "http://127.0.0.1:8200",
  [switch]$SkipApi,
  [switch]$SkipVoice
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

Step "Python compile"
python -m py_compile engine\server.py engine\chat_engine.py engine\nening_brain.py engine\characters_demo.py
Pass "Python files compile"

Step "JSON parse"
@'
import json, pathlib
for p in ["engine/characters.json", "engine/user_profile.json"]:
    json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    print(f"{p} OK")
'@ | python -
Pass "JSON files parse"

Step "Frontend id references"
@'
from pathlib import Path
import re
html = Path("web/index.html").read_text(encoding="utf-8")
js = Path("web/src/app.js").read_text(encoding="utf-8")
ids = set(re.findall(r'id="([^"]+)"', html))
refs = set(re.findall(r"#([A-Za-z_][\w-]*)", js))
allowed = {"chat", "connect", "med"}
missing = sorted([r for r in refs if r not in ids and r not in allowed])
if missing:
    raise SystemExit("Missing id refs: " + ", ".join(missing))
print("index ids", len(ids))
'@ | python -
Pass "Frontend id refs are valid"

Step "Git diff check"
git diff --check
Pass "No whitespace errors"

if ($SkipApi) {
  Warn "API checks skipped"
  exit 0
}

Step "Engine reachability"
try {
  $html = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/" -TimeoutSec 10
  if ($html.Content -notmatch "<!DOCTYPE html>") {
    throw "Unexpected HTML response"
  }
  Pass "Engine serves web app at $BaseUrl"
} catch {
  Warn "Engine is not reachable at $BaseUrl. Start run-munea-app.bat or py engine/server.py, then rerun without -SkipApi."
  exit 0
}

Step "API /open"
$openBody = '{"char":"\u5be7\u5be7"}'
$open = Invoke-RestMethod -Uri "$BaseUrl/open" -Method Post -ContentType "application/json; charset=utf-8" -Body $openBody -TimeoutSec 90
if (-not $open.reply) { throw "/open returned no reply" }
if (-not $SkipVoice -and -not $open.audio) { throw "/open returned no audio" }
$openAudioStatus = if ($open.audio) { " + audio" } else { "" }
Pass ("/open returned reply" + $openAudioStatus)

Step "API /open unknown role fallback"
$fallback = Invoke-RestMethod -Uri "$BaseUrl/open" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"char":"__unknown__"}' -TimeoutSec 90
if (-not $fallback.reply) { throw "/open fallback returned no reply" }
if ($fallback.err) { throw "/open fallback returned err: $($fallback.err)" }
Pass "/open unknown role falls back cleanly"

Step "API /chat"
$chatBody = '{"char":"\u5be7\u5be7","history":[{"role":"user","text":"\u6211\u4eca\u5929\u60f3\u804a\u804a\u5065\u5eb7\u548c\u5bb6\u4eba"}]}'
$chat = Invoke-RestMethod -Uri "$BaseUrl/chat" -Method Post -ContentType "application/json; charset=utf-8" -Body $chatBody -TimeoutSec 120
if (-not $chat.reply) { throw "/chat returned no reply" }
if (-not $SkipVoice -and -not $chat.audio) { throw "/chat returned no audio" }
$chatAudioStatus = if ($chat.audio) { " + audio" } else { "" }
Pass ("/chat returned reply" + $chatAudioStatus)

Write-Host ""
Write-Host "Smoke test complete." -ForegroundColor Green
