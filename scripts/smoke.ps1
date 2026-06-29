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
python -m py_compile engine\server.py engine\supabase_adapter.py engine\chat_engine.py engine\nening_brain.py engine\characters_demo.py
Pass "Python files compile"

Step "JSON parse"
@'
import json, pathlib
for p in ["engine/characters.json", "engine/user_profile.json", "engine/companion_profile.json", "engine/app_profile_store.json", "engine/billing_store.json", "engine/privacy_requests.json"]:
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
try:
    server.decode_voice_note({"mime": "application/octet-stream", "audio": "dGVzdA=="})
    raise AssertionError("unsupported mime should fail")
except ValueError as e:
    assert str(e) == "unsupported_audio_mime"
print("voice note bytes", result["bytes"])
'@ | python -
Pass "Voice note payload decodes with safety guards"

Step "Companion profile contract"
@'
import os, sys
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

profile = server.normalize_companion_profile({
    "templateId": "cat",
    "displayName": " 小花 ",
    "nameTouched": True,
})
assert profile["templateId"] == "munea-2d-mimi"
assert profile["displayName"] == "小花"
assert profile["nameTouched"] is True

resp = server.companion_profile_response({"action": "load"})
assert resp["ok"] is True
assert "templateId" in resp["profile"]
assert resp["backend"]["fallback"] == "json"
store_resp = server.app_profile_response({"action": "load"})
assert store_resp["ok"] is True
assert store_resp["store"]["primaryCareRecipientId"] in store_resp["store"]["companionProfiles"]
assert store_resp["backend"]["fallback"] == "json"
normalized_store = server.normalize_app_profile_store({
    "companionProfile": {"templateId": "real-f", "displayName": "Munea", "nameTouched": True},
})
active = server.active_companion_profile(normalized_store)
assert active["templateId"] == "nening-real-female"
assert active["displayName"] == "Munea"
print("companion profile", profile["templateId"], profile["displayName"])
'@ | python -
Pass "Companion profile and app store contracts are valid"

Step "Supabase adapter contract"
@'
import os, sys
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import supabase_adapter

blank = supabase_adapter.make_adapter(env={})
assert blank.enabled() is False
assert "SUPABASE_URL" in blank.status()["missing"]

env = {
    "MUNEA_DATABASE_PROVIDER": "supabase",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
    "MUNEA_SUPABASE_ACCOUNT_ID": "11111111-1111-4111-8111-111111111111",
    "MUNEA_SUPABASE_PERSON_ID": "22222222-2222-4222-8222-222222222222",
    "MUNEA_SUPABASE_FAMILY_GROUP_ID": "33333333-3333-4333-8333-333333333333",
}
adapter = supabase_adapter.make_adapter(env=env)
assert adapter.enabled() is True
row = adapter.profile_to_companion_row({"templateId": "real-f", "displayName": "Munea", "nameTouched": True})
assert row["account_id"] == env["MUNEA_SUPABASE_ACCOUNT_ID"]
assert row["person_id"] == env["MUNEA_SUPABASE_PERSON_ID"]
assert row["template_id"] == "real-f"
profile = adapter.companion_row_to_profile({"template_id": "nening-real-female", "display_name": "Nening", "name_touched": True})
assert profile["templateId"] == "nening-real-female"
assert profile["displayName"] == "Nening"
assert profile["nameTouched"] is True

def fake_request(method, table, query=None, payload=None, prefer=None):
    if method in ("POST", "PATCH"):
        if table == "subscription_ledger":
            return [{**payload, "id": "sub-ledger-1", "updated_at": "2026-06-29T00:00:00Z"}]
        if table == "usage_ledger":
            return [{**payload, "id": "usage-ledger-1", "updated_at": "2026-06-29T00:00:00Z"}]
        if table == "privacy_requests":
            return [{**payload, "id": "privacy-request-1", "requested_at": "2026-06-29T00:00:00Z"}]
        if table == "companion_profiles":
            return [{**payload, "updated_at": "2026-06-29T00:00:00Z"}]
        raise AssertionError(f"Unexpected write table: {table}")

    assert method == "GET"
    fixtures = {
        "accounts": [{
            "id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "locale": "zh-TW",
            "preferred_languages": ["zh-TW", "en"],
            "created_at": "2026-06-29T00:00:00Z",
            "updated_at": "2026-06-29T00:00:00Z",
        }],
        "persons": [{
            "id": env["MUNEA_SUPABASE_PERSON_ID"],
            "display_name": "Primary user",
            "relationship": "self",
        }],
        "family_groups": [{
            "id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"] or "33333333-3333-4333-8333-333333333333",
            "name": "Munea Care Circle",
        }],
        "family_memberships": [{
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "role": "primary_user",
        }],
        "companion_profiles": [{
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "template_id": "nening-real-female",
            "display_name": "Nening",
            "name_touched": True,
            "updated_at": "2026-06-29T00:00:00Z",
        }],
        "subscription_ledger": [{
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "platform": "ios",
            "provider": "revenuecat",
            "product_id": "munea.premium.monthly",
            "original_transaction_id": "1000000000000001",
            "status": "active",
            "active_plan": "premium",
            "entitlements": {"voiceCompanion": True, "realtimeAvatar": True},
            "verified_at": "2026-06-29T00:00:00Z",
            "expires_at": "2026-07-29T00:00:00Z",
            "will_renew": True,
            "updated_at": "2026-06-29T00:00:00Z",
        }],
        "usage_ledger": [
            {"period": "2026-06", "metric": "voice_minutes", "used": 12, "granted": 300},
            {"period": "2026-06", "metric": "avatar_minutes", "used": 4, "granted": 60},
        ],
        "privacy_requests": [{
            "id": "privacy-request-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "request_type": "export",
            "status": "requested",
            "reason": "test",
            "requires_reauth": True,
            "subscription_notice_required": False,
            "requested_at": "2026-06-29T00:00:00Z",
        }],
    }
    return fixtures[table]

adapter._request = fake_request
store = adapter.load_app_profile_store()
assert store["account"]["locale"] == "zh-TW"
assert store["familyGroup"]["members"][0]["role"] == "primary_user"
assert store["companionProfiles"][env["MUNEA_SUPABASE_PERSON_ID"]]["displayName"] == "Nening"
remote_billing = adapter.load_billing_store()
assert remote_billing["activePlan"] == "premium"
assert remote_billing["subscription"]["status"] == "active"
assert remote_billing["usageLedger"]["voiceMinutesUsed"] == 12
saved_billing = adapter.save_billing_store({
    "activePlan": "premium",
    "provider": "revenuecat",
    "subscription": {"status": "active", "productId": "munea.premium.monthly"},
    "entitlements": {"voiceCompanion": True, "realtimeAvatar": True},
    "usageLedger": {"period": "2026-06", "voiceMinutesUsed": 1, "avatarMinutesUsed": 1},
})
assert saved_billing["accountId"] == env["MUNEA_SUPABASE_ACCOUNT_ID"]
privacy_store = adapter.load_privacy_requests_store()
assert privacy_store["requests"][0]["type"] == "export"
privacy_req = adapter.append_privacy_request("account_deletion", {"reason": "test"})
assert privacy_req["type"] == "account_deletion"
assert privacy_req["subscriptionNoticeRequired"] is True
print("supabase adapter", adapter.status()["enabled"])
'@ | python -
Pass "Supabase adapter supports profile, billing, usage, and privacy contracts"

Step "Billing and entitlement contract"
@'
import os, sys
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

billing = server.entitlements_response({"action": "load"})
assert billing["ok"] is True
assert billing["entitlements"]["voiceCompanion"] is True
assert billing["billing"]["serverVerificationRequired"] is True

normalized = server.normalize_billing_store({
    "activePlan": "premium",
    "subscription": {"status": "active", "productId": "munea.premium.monthly"},
    "entitlements": {"realtimeAvatar": True, "premiumAvatarMinutesMonthly": 120},
})
assert normalized["activePlan"] == "premium"
assert normalized["subscription"]["status"] == "active"
assert normalized["entitlements"]["realtimeAvatar"] is True
fallback = server.avatar_session_response({"mode": "liveavatar", "estimatedDurationMs": 60000})
assert fallback["ok"] is True
assert fallback["session"]["requestedMode"] == "liveavatar"
assert fallback["session"]["selectedMode"] == "2d-viseme"
assert fallback["session"]["fallbackReason"] == "premium_avatar_not_entitled"

original_load = server.load_billing_store
original_save = server.save_billing_store
premium_store = server.normalize_billing_store({
    "activePlan": "premium",
    "subscription": {"status": "active", "productId": "munea.premium.monthly"},
    "entitlements": {"realtimeAvatar": True, "premiumAvatarMinutesMonthly": 120},
    "usageLedger": {"period": "2026-06", "avatarMinutesUsed": 10},
})
def fake_load():
    return premium_store
def fake_save(data):
    premium_store.update(server.normalize_billing_store(data))
    return premium_store
server.load_billing_store = fake_load
server.save_billing_store = fake_save
premium = server.avatar_session_response({"action": "complete", "mode": "ditto", "durationMs": 120000})
assert premium["session"]["selectedMode"] == "ditto"
assert premium["session"]["usageCommitted"] is True
assert premium["usageLedger"]["avatarMinutesUsed"] == 12
server.load_billing_store = original_load
server.save_billing_store = original_save
print("billing plan", normalized["activePlan"])
'@ | python -
Pass "Billing entitlements and avatar session gates normalize correctly"

Step "Supabase schema contract"
@'
from pathlib import Path

sql = Path("supabase/sql/001_initial_munea_schema.sql").read_text(encoding="utf-8").lower()
seed = Path("supabase/sql/002_demo_bootstrap.sql").read_text(encoding="utf-8").lower()
env_example = Path("docs/supabase/munea-env.example.txt").read_text(encoding="utf-8")
required_tables = [
    "accounts",
    "account_members",
    "persons",
    "family_groups",
    "family_memberships",
    "companion_profiles",
    "routine_reminders",
    "voice_sessions",
    "conversation_summaries",
    "safety_events",
    "subscription_ledger",
    "usage_ledger",
    "privacy_requests",
    "audit_events",
]
missing = [table for table in required_tables if f"create table if not exists public.{table}" not in sql]
if missing:
    raise SystemExit("Missing Supabase tables: " + ", ".join(missing))
for table in required_tables:
    token = f"alter table public.{table} enable row level security"
    if token not in sql:
        raise SystemExit("Missing RLS enablement: " + table)
if "revoke all on all tables in schema public from anon" not in sql:
    raise SystemExit("Missing anon revoke")
if "grant select, insert, update, delete on all tables in schema public to authenticated" not in sql:
    raise SystemExit("Missing authenticated grant")
if "auth.uid()" not in sql:
    raise SystemExit("Missing auth.uid RLS predicate")
required_seed_tokens = [
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "insert into public.accounts",
    "insert into public.persons",
    "insert into public.family_groups",
    "insert into public.family_memberships",
    "insert into public.companion_profiles",
    "insert into public.subscription_ledger",
    "insert into public.usage_ledger",
    "insert into public.audit_events",
    "demo_user_id uuid := null",
]
missing_seed = [token for token in required_seed_tokens if token not in seed]
if missing_seed:
    raise SystemExit("Missing Supabase seed tokens: " + ", ".join(missing_seed))
for key in ["MUNEA_SUPABASE_ACCOUNT_ID", "MUNEA_SUPABASE_PERSON_ID", "MUNEA_SUPABASE_FAMILY_GROUP_ID"]:
    if key not in env_example:
        raise SystemExit("Missing Supabase env example key: " + key)
print("supabase tables", len(required_tables))
'@ | python -
Pass "Supabase schema and demo bootstrap include tables, RLS, grants, and seed ids"

Step "Secret boundary contract"
@'
from pathlib import Path

web_hits = []
for path in Path("web").rglob("*"):
    if path.is_file() and path.suffix.lower() in {".html", ".js", ".css", ".json"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "SUPABASE_SERVICE_ROLE_KEY" in text or "service_role" in text:
            web_hits.append(str(path))
if web_hits:
    raise SystemExit("Service role reference leaked into web files: " + ", ".join(web_hits))
print("service role stays backend-only")
'@ | python -
Pass "Service role references are not in web assets"

Step "Backend architecture document contract"
@'
from pathlib import Path

doc = Path("docs/BACKEND-ARCHITECTURE-v1.md").read_text(encoding="utf-8").lower()
required = [
    "api surface v1",
    "supabase data model v1",
    "rls and permission matrix",
    "north star metrics",
    "analytics event model",
    "admin console mvp",
    "subscription and entitlements",
    "data rights and trust",
    "development phases",
]
missing = [token for token in required if token not in doc]
if missing:
    raise SystemExit("Backend architecture doc missing sections: " + ", ".join(missing))
print("backend architecture sections", len(required))
'@ | python -
Pass "Backend architecture document covers required sections"

Step "Repo-backed Codex skill contract"
@'
from pathlib import Path

required = {
    "cto-context-architect": [
        "name: cto-context-architect",
        "description:",
        "Production Architecture Rules",
        "Munea Overlay",
    ],
    "munea-cto": [
        "name: munea-cto",
        "description:",
        "Backend Rules",
        "Voice And Avatar Rules",
    ],
}

for skill, tokens in required.items():
    path = Path("codex-skills") / skill / "SKILL.md"
    if not path.exists():
        raise SystemExit(f"Missing Codex skill: {path}")
    text = path.read_text(encoding="utf-8")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise SystemExit(f"{skill} missing tokens: {', '.join(missing)}")

setup_doc = Path("docs/CODEX-SKILLS-SETUP.md").read_text(encoding="utf-8")
if "Claude collaboration is unaffected" not in setup_doc:
    raise SystemExit("Codex skill setup doc must state Claude collaboration boundary")

print("codex skills", len(required))
'@ | python -
Pass "Repo-backed Codex skills are present and documented"

Step "Privacy data-rights contract"
@'
import os, sys
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

req = server.normalize_privacy_request({"requestType": "account_deletion", "reason": "test"})
assert req["type"] == "account_deletion"
assert req["requiresReauth"] is True
assert req["subscriptionNoticeRequired"] is True

export = server.privacy_export_response({"action": "preview"})
assert export["ok"] is True
assert export["request"]["status"] == "preview"
assert "billing" in export["exportPackage"]
assert "privacyRequests" in export["exportPackage"]

deletion = server.account_deletion_response({"action": "status"})
assert deletion["ok"] is True
assert deletion["requiresReauth"] is True
print("privacy status", deletion["status"])
'@ | python -
Pass "Privacy export and account deletion contracts are valid"

Step "Frontend JavaScript syntax"
node --check web\src\app.js
node --check web\src\companion-profile.js
Pass "Frontend JavaScript parses"

Step "Avatar runtime contract"
@'
from pathlib import Path
html = Path("web/index.html").read_text(encoding="utf-8")
js = Path("web/src/app.js").read_text(encoding="utf-8")
css = Path("web/src/styles.css").read_text(encoding="utf-8")
required_js = [
    "AVATAR_ENGINE_MODES",
    "STATIC_CSS",
    "TWO_D_VISEME",
    "DITTO",
    "LIVE_AVATAR",
    "MuneaAvatarRuntime",
    "setViseme",
    "startMockViseme",
    "avatarSessionApi",
    "applyAvatarSessionDecision",
    "recordAvatarUsage",
    "/avatar-session",
]
missing_js = [token for token in required_js if token not in js]
if missing_js:
    raise SystemExit("Missing avatar runtime tokens: " + ", ".join(missing_js))
if 'id="avatarMouth"' not in html:
    raise SystemExit("Missing avatar mouth layer")
if 'id="avatarDiagnostics"' not in html:
    raise SystemExit("Missing avatar diagnostics layer")
if 'data-avatar-mode="2d-viseme"' not in css:
    raise SystemExit("Missing 2d-viseme CSS mode selector")
print("avatar runtime contract OK")
'@ | python -
Pass "Avatar runtime contract is present"

Step "Voice provider contract"
@'
from pathlib import Path
js = Path("web/src/app.js").read_text(encoding="utf-8")
required = [
    "window.MuneaVoiceProvider",
    "VOICE_PROVIDER_MODES",
    "connect(context",
    "sendText({ history, char })",
    "sendVoiceNote({ audio, mime, durationMs, char })",
    "/voice-session",
]
missing = [item for item in required if item not in js]
if missing:
    raise SystemExit("Missing voice provider contract pieces: " + ", ".join(missing))
print("voice provider contract OK")
'@ | python -
Pass "Voice provider contract is present"

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

Step "API /voice-session"
$session = Invoke-RestMethod -Uri "$BaseUrl/voice-session" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"char":"\u5be7\u5be7","locale":"zh-TW"}' -TimeoutSec 30
if (-not $session.ok) { throw "/voice-session returned not ok" }
if ($session.provider -ne "stt-chat-tts") { throw "/voice-session provider unexpected: $($session.provider)" }
if (-not $session.capabilities.recordedVoiceNote) { throw "/voice-session missing recorded voice capability" }
Pass "/voice-session returns provider capabilities"

Step "API /companion-profile"
$profile = Invoke-RestMethod -Uri "$BaseUrl/companion-profile" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"action":"load"}' -TimeoutSec 30
if (-not $profile.ok) { throw "/companion-profile returned not ok" }
if (-not $profile.profile.templateId) { throw "/companion-profile missing templateId" }
Pass "/companion-profile returns saved companion profile"

Step "API /app-profile"
$appProfile = Invoke-RestMethod -Uri "$BaseUrl/app-profile" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"action":"load"}' -TimeoutSec 30
if (-not $appProfile.ok) { throw "/app-profile returned not ok" }
if (-not $appProfile.store.primaryCareRecipientId) { throw "/app-profile missing primaryCareRecipientId" }
if (-not $appProfile.activeCompanionProfile.templateId) { throw "/app-profile missing active companion profile" }
Pass "/app-profile returns account/family/companion store"

Step "API /entitlements"
$entitlements = Invoke-RestMethod -Uri "$BaseUrl/entitlements" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"action":"load"}' -TimeoutSec 30
if (-not $entitlements.ok) { throw "/entitlements returned not ok" }
if (-not $entitlements.entitlements.voiceCompanion) { throw "/entitlements missing voiceCompanion" }
if (-not $entitlements.billing.serverVerificationRequired) { throw "/entitlements should require server verification" }
Pass "/entitlements returns subscription gates"

Step "API /healthz"
$health = Invoke-RestMethod -Uri "$BaseUrl/healthz" -Method Get -TimeoutSec 30
if (-not $health.ok) { throw "/healthz returned not ok" }
if ($health.contracts -notcontains "entitlements") { throw "/healthz missing entitlements contract" }
if ($health.contracts -notcontains "avatar-session") { throw "/healthz missing avatar-session contract" }
if ($health.contracts -notcontains "privacy-export") { throw "/healthz missing privacy-export contract" }
if ($health.contracts -notcontains "account-deletion") { throw "/healthz missing account-deletion contract" }
Pass "/healthz returns service contracts"

Step "API /avatar-session"
$avatar = Invoke-RestMethod -Uri "$BaseUrl/avatar-session" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"mode":"liveavatar","estimatedDurationMs":60000}' -TimeoutSec 30
if (-not $avatar.ok) { throw "/avatar-session returned not ok" }
if ($avatar.session.requestedMode -ne "liveavatar") { throw "/avatar-session requested mode unexpected: $($avatar.session.requestedMode)" }
if (-not $avatar.session.selectedMode) { throw "/avatar-session missing selected mode" }
if (-not $avatar.usageLedger) { throw "/avatar-session missing usage ledger" }
Pass "/avatar-session returns entitlement-gated runtime decision"

Step "API /privacy-export"
$privacyExport = Invoke-RestMethod -Uri "$BaseUrl/privacy-export" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"action":"preview"}' -TimeoutSec 30
if (-not $privacyExport.ok) { throw "/privacy-export returned not ok" }
if (-not $privacyExport.exportPackage.billing) { throw "/privacy-export missing billing package" }
Pass "/privacy-export returns local export package"

Step "API /account-deletion"
$deletion = Invoke-RestMethod -Uri "$BaseUrl/account-deletion" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"action":"status"}' -TimeoutSec 30
if (-not $deletion.ok) { throw "/account-deletion returned not ok" }
if (-not $deletion.requiresReauth) { throw "/account-deletion should require reauth" }
Pass "/account-deletion returns deletion status contract"

Step "API /chat"
$chatBody = '{"char":"\u5be7\u5be7","history":[{"role":"user","text":"\u6211\u4eca\u5929\u60f3\u804a\u804a\u5065\u5eb7\u548c\u5bb6\u4eba"}]}'
$chat = Invoke-RestMethod -Uri "$BaseUrl/chat" -Method Post -ContentType "application/json; charset=utf-8" -Body $chatBody -TimeoutSec 120
if (-not $chat.reply) { throw "/chat returned no reply" }
if (-not $SkipVoice -and -not $chat.audio) { throw "/chat returned no audio" }
$chatAudioStatus = if ($chat.audio) { " + audio" } else { "" }
Pass ("/chat returned reply" + $chatAudioStatus)

Write-Host ""
Write-Host "Smoke test complete." -ForegroundColor Green
