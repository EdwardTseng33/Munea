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

Step "Voice note payload decode"
@'
import os, sys
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server
payload = {"mime": "audio/webm", "durationMs": 1200, "audio": "dGVzdA=="}
result = server.decode_voice_note(payload)
assert result["ok"] is True
assert result["bytes"] == 4
assert result["durationMs"] == 1200
print("voice note bytes", result["bytes"])
'@ | python -
Pass "Voice note payload decodes"

Step "Frontend JavaScript syntax"
node --check web\src\app.js
Pass "Frontend JavaScript parses"

Step "Avatar runtime contract"
@'
from pathlib import Path
html = Path("web/index.html").read_text(encoding="utf-8")
js = Path("web/src/app.js").read_text(encoding="utf-8")
css = Path("web/src/styles.css").read_text(encoding="utf-8")
required_js = ["AVATAR_ENGINE_MODES", "STATIC_CSS", "TWO_D_VISEME", "DITTO", "LIVE_AVATAR", "MuneaAvatarRuntime", "setViseme", "startMockViseme"]
missing_js = [token for token in required_js if token not in js]
if missing_js:
    raise SystemExit("Missing avatar runtime tokens: " + ", ".join(missing_js))
if 'id="avatarMouth"' not in html:
    raise SystemExit("Missing avatar mouth layer")
if 'data-avatar-mode="2d-viseme"' not in css:
    raise SystemExit("Missing 2d-viseme CSS mode selector")
print("avatar runtime contract OK")
'@ | python -
Pass "Avatar runtime contract is present"

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

Step "API /voice-note"
$voiceBody = '{"char":"\u5be7\u5be7","mime":"audio/webm","durationMs":1200,"audio":"dGVzdA=="}'
$voice = Invoke-RestMethod -Uri "$BaseUrl/voice-note" -Method Post -ContentType "application/json; charset=utf-8" -Body $voiceBody -TimeoutSec 30
if (-not $voice.ok) { throw "/voice-note returned not ok" }
if ($voice.bytes -ne 4) { throw "/voice-note decoded unexpected byte length: $($voice.bytes)" }
Pass "/voice-note accepts captured audio payloads"

Step "API /chat"
$chatBody = '{"char":"\u5be7\u5be7","history":[{"role":"user","text":"\u6211\u4eca\u5929\u60f3\u804a\u804a\u5065\u5eb7\u548c\u5bb6\u4eba"}]}'
$chat = Invoke-RestMethod -Uri "$BaseUrl/chat" -Method Post -ContentType "application/json; charset=utf-8" -Body $chatBody -TimeoutSec 120
if (-not $chat.reply) { throw "/chat returned no reply" }
if (-not $SkipVoice -and -not $chat.audio) { throw "/chat returned no audio" }
$chatAudioStatus = if ($chat.audio) { " + audio" } else { "" }
Pass ("/chat returned reply" + $chatAudioStatus)

Write-Host ""
Write-Host "Smoke test complete." -ForegroundColor Green
