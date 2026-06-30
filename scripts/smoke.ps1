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
python -m py_compile engine\server.py engine\env_loader.py engine\supabase_adapter.py engine\model_router.py engine\chat_engine.py engine\nening_brain.py engine\characters_demo.py scripts\supabase_doctor.py
Pass "Python files compile"

Step "JSON parse"
@'
import json, pathlib
for p in ["engine/characters.json", "engine/user_profile.json", "engine/companion_profile.json", "engine/app_profile_store.json", "engine/billing_store.json", "engine/privacy_requests.json", "engine/memory_items.json", "engine/perception_snapshots.json"]:
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
        if table == "product_events":
            return [{**payload, "id": "product-event-1", "created_at": "2026-06-29T00:00:00Z"}]
        if table == "memory_items":
            rows = payload if isinstance(payload, list) else [payload]
            return [{**row, "id": f"memory-item-{idx}", "created_at": "2026-06-29T00:00:00Z", "updated_at": "2026-06-29T00:00:00Z"} for idx, row in enumerate(rows, start=1)]
        if table == "perception_snapshots":
            rows = payload if isinstance(payload, list) else [payload]
            return [{**row, "id": f"perception-snapshot-{idx}", "created_at": "2026-06-29T00:00:00Z"} for idx, row in enumerate(rows, start=1)]
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
        "product_events": [{
            "id": "product-event-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "family_group_id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"],
            "event_name": "voice_session_completed",
            "event_time": "2026-06-29T00:00:00Z",
            "source": "smoke",
            "session_id": "voice-session-1",
            "properties": {"durationMs": 90000},
            "created_at": "2026-06-29T00:00:00Z",
        }],
        "memory_items": [{
            "id": "memory-item-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "memory_type": "preference",
            "content": "Likes Korean dramas and Netflix series",
            "source": "conversation",
            "confidence": 0.8,
            "importance": 0.7,
            "sensitivity": "normal",
            "consent_scope": "user",
            "valid_from": "2026-06-29T00:00:00Z",
            "valid_until": None,
            "last_confirmed_at": None,
            "supersedes_memory_id": None,
            "metadata": {"topic": "video_entertainment"},
            "created_at": "2026-06-29T00:00:00Z",
            "updated_at": "2026-06-29T00:00:00Z",
        }],
        "perception_snapshots": [{
            "id": "perception-snapshot-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "snapshot_type": "media_context",
            "observed_at": "2026-06-29T00:00:00Z",
            "expires_at": "2026-06-30T00:00:00Z",
            "facts": {"domain": "video_entertainment", "sources": ["streaming_catalog", "regional_availability"]},
            "source": "smoke",
            "created_at": "2026-06-29T00:00:00Z",
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
event = adapter.append_product_event({"eventName": "voice_session_completed", "properties": {"durationMs": 90000}})
assert event["eventName"] == "voice_session_completed"
events = adapter.load_product_events(limit=10)
assert events[0]["eventName"] == "voice_session_completed"
memories = adapter.load_memory_items(limit=10)
assert memories[0]["type"] == "preference"
assert memories[0]["content"] == "Likes Korean dramas and Netflix series"
saved_memories = adapter.save_memory_items([{
    "personId": env["MUNEA_SUPABASE_PERSON_ID"],
    "type": "relationship",
    "content": "Daughter is Mei-Hua",
    "confidence": 0.9,
    "importance": 0.9,
    "sensitivity": "normal",
}])
assert saved_memories[0]["type"] == "relationship"
assert saved_memories[0]["accountId"] == env["MUNEA_SUPABASE_ACCOUNT_ID"]
snapshots = adapter.load_perception_snapshots({"snapshotType": "media_context"}, limit=10)
assert snapshots[0]["snapshotType"] == "media_context"
assert snapshots[0]["facts"]["domain"] == "video_entertainment"
saved_snapshots = adapter.save_perception_snapshots([{
    "personId": env["MUNEA_SUPABASE_PERSON_ID"],
    "snapshotType": "finance_context",
    "facts": {"symbols": ["SPY"], "freshness": "high"},
    "source": "smoke",
}])
assert saved_snapshots[0]["snapshotType"] == "finance_context"
assert saved_snapshots[0]["accountId"] == env["MUNEA_SUPABASE_ACCOUNT_ID"]

bootstrap_writes = []
bootstrap_adapter = supabase_adapter.make_adapter(env=env)
def fake_bootstrap_request(method, table, query=None, payload=None, prefer=None):
    if method == "GET" and table == "account_members":
        return []
    if method == "GET":
        fixtures = {
            "accounts": [{"id": bootstrap_adapter.account_id, "locale": "zh-TW", "preferred_languages": ["zh-TW", "en"]}],
            "persons": [{"id": bootstrap_adapter.person_id, "display_name": "Bootstrap User", "relationship": "self"}],
            "family_groups": [{"id": bootstrap_adapter.family_group_id, "name": "Munea Care Circle"}],
            "family_memberships": [{"person_id": bootstrap_adapter.person_id, "role": "primary_user"}],
            "companion_profiles": [{"person_id": bootstrap_adapter.person_id, "template_id": "nening-real-female", "display_name": "Munea", "name_touched": True}],
            "subscription_ledger": [{"account_id": bootstrap_adapter.account_id, "status": "inactive", "active_plan": "free", "entitlements": {}}],
            "usage_ledger": [],
        }
        return fixtures.get(table, [])
    bootstrap_writes.append(table)
    if table == "accounts":
        bootstrap_adapter.account_id = payload["id"]
    elif table == "persons":
        bootstrap_adapter.person_id = payload["id"]
    elif table == "family_groups":
        bootstrap_adapter.family_group_id = payload["id"]
    return [{**(payload or {}), "id": (payload or {}).get("id") or f"{table}-row"}]

bootstrap_adapter._request = fake_bootstrap_request
bootstrapped = bootstrap_adapter.bootstrap_account({
    "authUserId": "44444444-4444-4444-8444-444444444444",
    "displayName": "Bootstrap User",
})
for table in ["accounts", "account_members", "persons", "family_groups", "family_memberships", "companion_profiles", "subscription_ledger", "usage_ledger", "audit_events"]:
    assert table in bootstrap_writes, f"bootstrap did not write {table}"
assert bootstrapped["familyGroup"]["members"][0]["role"] == "primary_user"
print("supabase adapter", adapter.status()["enabled"])
'@ | python -
Pass "Supabase adapter supports profile, billing, usage, and privacy contracts"

Step "Account bootstrap contract"
@'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

with tempfile.TemporaryDirectory() as d:
    server.APP_PROFILE_STORE_PATH = str(Path(d) / "app_profile_store.json")
    server.COMPANION_PROFILE_PATH = str(Path(d) / "companion_profile.json")
    server.PRODUCT_EVENTS_PATH = str(Path(d) / "product_events.json")
    response = server.bootstrap_account_response({
        "displayName": "Test User",
        "companionProfile": {"templateId": "real-f", "displayName": "Munea", "nameTouched": True},
    })
    assert response["ok"] is True
    store = response["store"]
    assert store["account"]["id"].startswith("local-account-")
    assert store["familyGroup"]["members"][0]["displayName"] == "Test User"
    assert response["activeCompanionProfile"]["templateId"] == "nening-real-female"
    events = server.load_product_events(limit=10)
    assert events[0]["eventName"] == "account_bootstrapped"

    original_backend = server.data_backend
    class FakeSupabaseBackend:
        def enabled(self):
            return True
        def status(self):
            return {"provider": "supabase", "enabled": True, "missing": []}
    try:
        server.data_backend = lambda: FakeSupabaseBackend()
        auth_required = server.bootstrap_account_response({"action": "create"})
        assert auth_required["ok"] is False
        assert auth_required["error"]["code"] == "auth_user_required"
        assert auth_required["requiresAuth"] is True
    finally:
        server.data_backend = original_backend
print("account bootstrap OK")
'@ | python -
Pass "Account bootstrap creates local account/family/person/companion store"

Step "AI service brain and memory contract"
@'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import model_router
import server

status = model_router.brain_status_response()
assert status["ok"] is True
assert status["brains"]["reflex"]["interface"] == "MuneaVoiceProvider"
assert status["brains"]["butler"]["interface"] == "MuneaBrainRouter"
assert status["brains"]["guardian"]["interface"] == "MuneaBrainRouter"
assert status["effortProfiles"]["deep"]["effort"] == "high"
assert "books" in status["topicDomains"]
assert "finance" in status["topicDomains"]
assert "travel" in status["topicDomains"]
assert "video_entertainment" in status["topicDomains"]
plan = model_router.topic_perception_plan_response({"query": "I want books, travel, exercise, and finance ideas for this week"})
domains = {item["domain"] for item in plan["domains"]}
assert {"books", "travel", "exercise", "finance"}.issubset(domains)
assert plan["needsCurrentFacts"] is True
assert plan["antiFabricationPolicy"]["verifyRecommendationsWhenFreshnessIsHigh"] is True
video_plan = model_router.topic_perception_plan_response({"query": "Can we talk about Korean drama, Japanese drama, Taiwan drama, Netflix series, and documentaries?"})
video_domains = {item["domain"] for item in video_plan["domains"]}
assert "video_entertainment" in video_domains
assert "streaming_catalog" in video_plan["perceptionSources"]
assert "regional_availability" in video_plan["perceptionSources"]

with tempfile.TemporaryDirectory() as d:
    server.MEMORY_ITEMS_PATH = str(Path(d) / "memory_items.json")
    server.PERCEPTION_SNAPSHOTS_PATH = str(Path(d) / "perception_snapshots.json")
    server.PRODUCT_EVENTS_PATH = str(Path(d) / "product_events.json")
    extracted = server.memory_extract_response({
        "action": "store",
        "text": "I like Korean dramas on Netflix and often talk with my daughter Mei-Hua. Recently I feel lonely.",
    })
    assert extracted["ok"] is True
    assert extracted["stored"] >= 2
    types = {item["type"] for item in extracted["memoryItems"]}
    assert "preference" in types
    assert "relationship" in types
    retrieved = server.memory_retrieve_response({"query": "Korean drama Netflix daughter", "limit": 5})
    assert retrieved["ok"] is True
    assert retrieved["count"] >= 1

    stored_snapshot = server.perception_snapshot_response({
        "action": "store",
        "snapshotType": "finance_context",
        "facts": {"symbols": ["SPY"], "freshness": "high", "requiresDisclaimer": True},
        "source": "smoke",
    })
    assert stored_snapshot["ok"] is True
    assert stored_snapshot["stored"] == 1
    listed_snapshot = server.perception_snapshot_response({"snapshotType": "finance_context"})
    assert listed_snapshot["ok"] is True
    assert listed_snapshot["count"] == 1
    assert listed_snapshot["snapshots"][0]["facts"]["requiresDisclaimer"] is True

    guardian = server.guardian_evaluate_response({"text": "I may be having a heart attack"})
    assert guardian["ok"] is True
    assert guardian["risk"]["level"] == "high"
    assert guardian["risk"]["requiresHumanEscalation"] is True

print("ai service OK")
'@ | python -
Pass "AI service router, memory, and Guardian contracts are valid"

Step "Auth token verification contract"
@'
import os, sys
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

assert server.extract_bearer_token({"Authorization": "Bearer abc.def"}) == "abc.def"
assert server.verify_auth_context({})["code"] == "auth_token_missing"

os.environ["MUNEA_ENABLE_DEV_AUTH_BYPASS"] = "true"
dev_token = "dev-local-token-00000000-0000-4000-8000-000000000001"
dev = server.verify_auth_context({"Authorization": "Bearer " + dev_token})
assert dev["ok"] is True
assert dev["authUserId"] == "00000000-0000-4000-8000-000000000001"
assert dev["developerMode"] is True
status = server.auth_status_response({"Authorization": "Bearer " + dev_token})
assert status["ok"] is True
assert status["auth"]["provider"] == "dev-bypass"
del os.environ["MUNEA_ENABLE_DEV_AUTH_BYPASS"]

os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "public-test-key"
missing_remote = server.verify_auth_context({"Authorization": "Bearer fake-token"})
assert missing_remote["ok"] is False
assert missing_remote["code"] in {"invalid_auth_token", "auth_verification_unavailable"}
del os.environ["SUPABASE_URL"]
del os.environ["SUPABASE_ANON_KEY"]
print("auth verification OK")
'@ | python -
Pass "Auth token verification contract is valid"

Step "Product event and North Star contract"
@'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

with tempfile.TemporaryDirectory() as d:
    server.PRODUCT_EVENTS_PATH = str(Path(d) / "product_events.json")
    event = server.product_event_response({
        "eventName": "voice_session_completed",
        "personId": "local-person-self",
        "properties": {"durationMs": 90000, "turnCount": 5},
    })
    assert event["ok"] is True
    assert event["event"]["eventName"] == "voice_session_completed"
    summary = server.north_star_summary({"days": 7})
    assert summary["metric"] == "Weekly Meaningful Companion Days"
    assert summary["meaningfulCompanionDays"] == 1
    assert summary["voiceSessionsCompleted"] == 1
    assert summary["excludedEventCount"] == 0
    developer_event = server.product_event_response({
        "eventName": "voice_session_completed",
        "personId": "developer-person",
        "sessionId": "developer-session",
        "properties": {
            "durationMs": 120000,
            "turnCount": 10,
            "analyticsExcluded": True,
            "developerMode": True,
            "accountType": "developer",
        },
    })
    assert developer_event["ok"] is True
    summary = server.north_star_summary({"days": 7})
    assert summary["meaningfulCompanionDays"] == 1
    assert summary["voiceSessionsCompleted"] == 1
    assert summary["excludedEventCount"] == 1
    ok, code = server.admin_authorized({})
    assert ok is False
    assert code == "admin_token_not_configured"
    os.environ["MUNEA_ADMIN_API_TOKEN"] = "admin-smoke-token"
    ok, code = server.admin_authorized({"X-Munea-Admin-Token": "admin-smoke-token"})
    assert ok is True
    assert code is None
    del os.environ["MUNEA_ADMIN_API_TOKEN"]
print("north star OK")
'@ | python -
Pass "Product events produce North Star summary and admin gate is closed by default"

Step "Environment loader and Supabase doctor contract"
@'
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, "engine")
from env_loader import load_env_file

with tempfile.TemporaryDirectory() as d:
    env_path = Path(d) / ".env.local"
    env_path.write_text("""
# comment
MUNEA_DATABASE_PROVIDER=supabase
SUPABASE_URL="https://example.supabase.co"
SUPABASE_SERVICE_ROLE_KEY='secret-test-key'
""", encoding="utf-8")
    os.environ["SUPABASE_URL"] = "https://existing.supabase.co"
    loaded = load_env_file(str(env_path), override=False)
    assert "MUNEA_DATABASE_PROVIDER" in loaded
    assert "SUPABASE_SERVICE_ROLE_KEY" in loaded
    assert os.environ["SUPABASE_URL"] == "https://existing.supabase.co"
    loaded_override = load_env_file(str(env_path), override=True)
    assert "SUPABASE_URL" in loaded_override
    assert os.environ["SUPABASE_URL"] == "https://example.supabase.co"
print("env loader OK")
'@ | python -

$doctorJson = python scripts\supabase_doctor.py --allow-missing --json | ConvertFrom-Json
if (-not $doctorJson.tables -or $doctorJson.tables.Count -lt 5) { throw "Supabase doctor missing table status" }
if ($doctorJson.hasServiceRoleKey -and ($doctorJson | ConvertTo-Json -Compress) -match "secret-test-key") { throw "Supabase doctor leaked service key" }
Pass "Environment loader and Supabase doctor are safe"

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
analytics = Path("supabase/sql/003_analytics_admin_foundation.sql").read_text(encoding="utf-8").lower()
ai_memory = Path("supabase/sql/004_ai_memory_service_foundation.sql").read_text(encoding="utf-8").lower()
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
analytics_tables = [
    "product_events",
    "daily_user_metrics",
    "voice_session_metrics",
    "reminder_events",
    "family_interaction_events",
    "cost_ledger",
    "admin_notes",
]
for table in analytics_tables:
    if f"create table if not exists public.{table}" not in analytics:
        raise SystemExit("Missing analytics table: " + table)
    if f"alter table public.{table} enable row level security" not in analytics:
        raise SystemExit("Missing analytics RLS: " + table)
    if f"revoke all on public.{table} from anon" not in analytics:
        raise SystemExit("Missing analytics anon revoke: " + table)
ai_memory_tables = [
    "memory_items",
    "perception_snapshots",
    "ai_brain_runs",
]
for table in ai_memory_tables:
    if f"create table if not exists public.{table}" not in ai_memory:
        raise SystemExit("Missing AI memory table: " + table)
    if f"alter table public.{table} enable row level security" not in ai_memory:
        raise SystemExit("Missing AI memory RLS: " + table)
if "embedding vector(1536)" not in ai_memory:
    raise SystemExit("Missing memory embedding column")
if "supersedes_memory_id" not in ai_memory:
    raise SystemExit("Missing memory supersede support")
for snapshot_type in ["book_context", "travel_context", "exercise_context", "finance_context", "media_context", "food_context", "news_context", "wisdom_context"]:
    if snapshot_type not in ai_memory:
        raise SystemExit("Missing perception snapshot type: " + snapshot_type)
if "weekly meaningful companion days" not in Path("docs/BACKEND-ARCHITECTURE-v1.md").read_text(encoding="utf-8").lower():
    raise SystemExit("Backend architecture missing North Star definition")
print("supabase tables", len(required_tables))
'@ | python -
Pass "Supabase schema, analytics foundation, RLS, grants, and seed ids are present"

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

Step "Auth onboarding architecture document contract"
@'
from pathlib import Path

doc = Path("docs/AUTH-ONBOARDING-ARCHITECTURE-v1.md").read_text(encoding="utf-8").lower()
readme = Path("README.md").read_text(encoding="utf-8").lower()
setup = Path("docs/supabase/SETUP.md").read_text(encoding="utf-8").lower()
required = [
    "sign in with apple",
    "google",
    "email magic link",
    "guest mode",
    "developer mode",
    "web/src/auth.js",
    "bearer-token api headers",
    "analyticsexcluded",
    "munea_analytics_excluded_account_ids",
    "progressive account",
    "facebook",
    "not v1",
    "authorization: bearer",
    "account-bootstrap",
    "auth.users.id",
]
missing = [token for token in required if token not in doc]
if missing:
    raise SystemExit("Auth onboarding architecture doc missing tokens: " + ", ".join(missing))
for token in ["auth and onboarding", "docs/auth-onboarding-architecture-v1.md"]:
    if token not in readme:
        raise SystemExit("README missing auth architecture pointer: " + token)
for token in ["sign in with apple", "google", "email magic link/otp", "facebook", "developer mode", "analytics exclusion"]:
    if token not in setup:
        raise SystemExit("Supabase setup missing auth provider decision: " + token)
print("auth onboarding contract OK")
'@ | python -
Pass "Auth onboarding architecture is documented"

Step "AI service design document contract"
@'
from pathlib import Path

doc = Path("docs/AI-SERVICE-DESIGN-v1.md").read_text(encoding="utf-8").lower()
readme = Path("README.md").read_text(encoding="utf-8").lower()
required = [
    "reflex brain",
    "butler brain",
    "guardian brain",
    "model effort profiles",
    "long-term memory architecture",
    "perception layer",
    "wisdom lens",
    "memory_items",
    "perception_snapshots",
    "ai_brain_runs",
    "non-medical",
]
missing = [token for token in required if token not in doc]
if missing:
    raise SystemExit("AI service design missing: " + ", ".join(missing))
if "docs/ai-service-design-v1.md" not in readme:
    raise SystemExit("README missing AI service design link")
print("ai service design contract OK")
'@ | python -
Pass "AI service design is documented"

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
node --check web\src\auth.js
node --check web\src\auth-config.example.js
Pass "Frontend JavaScript parses"

Step "Frontend auth bridge contract"
@'
from pathlib import Path
auth = Path("web/src/auth.js").read_text(encoding="utf-8")
app = Path("web/src/app.js").read_text(encoding="utf-8")
index = Path("web/index.html").read_text(encoding="utf-8")
onboarding = Path("web/onboarding.html").read_text(encoding="utf-8")
config = Path("web/src/auth-config.example.js").read_text(encoding="utf-8")
required_auth_ui = [
    "authCard",
    "authSheet",
    "authSignInBtn",
    "authSignOutBtn",
    "authAppleBtn",
    "authGoogleBtn",
    "authEmailInput",
    "authEmailBtn",
    "authDeveloperBtn",
]
missing_auth_ui = [token for token in required_auth_ui if token not in index]
if missing_auth_ui:
    raise SystemExit("Missing auth UI tokens: " + ", ".join(missing_auth_ui))
required_auth = [
    "window.MuneaAuth",
    "signInWithApple",
    "signInWithGoogle",
    "signInWithEmail",
    "signInAsDeveloper",
    "signInWithOtp",
    "signInWithOAuth",
    "getAccessToken",
    "signOut",
    "developerMode",
    "guest",
    "apple",
    "google",
]
missing_auth = [token for token in required_auth if token not in auth]
if missing_auth:
    raise SystemExit("Missing auth bridge tokens: " + ", ".join(missing_auth))
for token in ["src/auth.js", "MuneaAuth"]:
    if token not in index and token == "src/auth.js":
        raise SystemExit("index.html missing auth runtime")
    if token not in onboarding:
        raise SystemExit("onboarding.html missing auth runtime/token: " + token)
for token in ["muneaAuthHeaders", "Authorization", "Bearer", "munea:auth-state"]:
    if token not in app:
        raise SystemExit("app.js missing auth API bridge: " + token)
for token in ["setupAuthControls", "updateAuthUI", "signInWithAuthProvider", "signInWithEmailLink", "signOutAuth"]:
    if token not in app:
        raise SystemExit("app.js missing auth UI controller: " + token)
for token in ["MUNEA_DEV_CONFIG", "skipOnboarding", "analyticsExcluded", "accountType", "developerMode"]:
    if token not in config and token not in app:
        raise SystemExit("Missing developer mode analytics token: " + token)
for forbidden in ["SERVICE_ROLE", "service_role"]:
    if forbidden in config or forbidden in auth:
        raise SystemExit("Auth browser files must not mention service role secret tokens")
print("frontend auth bridge OK")
'@ | python -
Pass "Frontend Auth bridge is present"

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
    "trackProductEvent",
    "/product-event",
    "voice_session_started",
    "voice_session_completed",
    "voice_turn_completed",
]
missing = [item for item in required if item not in js]
if missing:
    raise SystemExit("Missing voice provider contract pieces: " + ", ".join(missing))
for forbidden in ["safeProperties.text", "safeProperties.transcript", "safeProperties.reply"]:
    if forbidden not in js:
        raise SystemExit("Product analytics must explicitly strip: " + forbidden)
print("voice provider contract OK")
'@ | python -
Pass "Voice provider contract is present"

Step "Account bootstrap frontend contract"
@'
from pathlib import Path
js = Path("web/src/app.js").read_text(encoding="utf-8")
onboarding = Path("web/onboarding.html").read_text(encoding="utf-8")
required_app = [
    "syncAccountBootstrap",
    "accountBootstrapPayload",
    "ACCOUNT_BOOTSTRAP_KEY",
    "ONBOARDING_COMPLETED_KEY",
    "/account-bootstrap",
    "auth_user_required",
    "onboarding_completed",
]
missing_app = [item for item in required_app if item not in js]
if missing_app:
    raise SystemExit("Missing app bootstrap contract pieces: " + ", ".join(missing_app))
required_onboarding = [
    "bootstrapAccount",
    "/account-bootstrap",
    "munea.onboardingCompleted.v1",
    "munea.accountBootstrapped.v1",
    "auth_user_required",
]
missing_onboarding = [item for item in required_onboarding if item not in onboarding]
if missing_onboarding:
    raise SystemExit("Missing onboarding bootstrap pieces: " + ", ".join(missing_onboarding))
print("account bootstrap frontend contract OK")
'@ | python -
Pass "Frontend onboarding can initialize account bootstrap"

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
if ($health.contracts -notcontains "auth-status") { throw "/healthz missing auth-status contract" }
if ($health.contracts -notcontains "account-bootstrap") { throw "/healthz missing account-bootstrap contract" }
if ($health.contracts -notcontains "entitlements") { throw "/healthz missing entitlements contract" }
if ($health.contracts -notcontains "avatar-session") { throw "/healthz missing avatar-session contract" }
if ($health.contracts -notcontains "ai-brain-status") { throw "/healthz missing ai-brain-status contract" }
if ($health.contracts -notcontains "memory-extract") { throw "/healthz missing memory-extract contract" }
if ($health.contracts -notcontains "memory-retrieve") { throw "/healthz missing memory-retrieve contract" }
if ($health.contracts -notcontains "guardian-evaluate") { throw "/healthz missing guardian-evaluate contract" }
if ($health.contracts -notcontains "perception-topic-plan") { throw "/healthz missing perception-topic-plan contract" }
if ($health.contracts -notcontains "perception-snapshot") { throw "/healthz missing perception-snapshot contract" }
if ($health.contracts -notcontains "product-event") { throw "/healthz missing product-event contract" }
if ($health.contracts -notcontains "admin-north-star") { throw "/healthz missing admin-north-star contract" }
if ($health.contracts -notcontains "privacy-export") { throw "/healthz missing privacy-export contract" }
if ($health.contracts -notcontains "account-deletion") { throw "/healthz missing account-deletion contract" }
Pass "/healthz returns service contracts"

Step "API /account-bootstrap"
$bootstrapBody = '{"action":"preview","displayName":"Smoke User","companionProfile":{"templateId":"real-f","displayName":"Munea","nameTouched":true}}'
$bootstrap = Invoke-RestMethod -Uri "$BaseUrl/account-bootstrap" -Method Post -ContentType "application/json; charset=utf-8" -Body $bootstrapBody -TimeoutSec 30
if (-not $bootstrap.ok) { throw "/account-bootstrap returned not ok" }
if (-not $bootstrap.store.account.id) { throw "/account-bootstrap missing account id" }
if (-not $bootstrap.activeCompanionProfile.templateId) { throw "/account-bootstrap missing active companion profile" }
Pass "/account-bootstrap previews account store"

Step "API /avatar-session"
$avatar = Invoke-RestMethod -Uri "$BaseUrl/avatar-session" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"mode":"liveavatar","estimatedDurationMs":60000}' -TimeoutSec 30
if (-not $avatar.ok) { throw "/avatar-session returned not ok" }
if ($avatar.session.requestedMode -ne "liveavatar") { throw "/avatar-session requested mode unexpected: $($avatar.session.requestedMode)" }
if (-not $avatar.session.selectedMode) { throw "/avatar-session missing selected mode" }
if (-not $avatar.usageLedger) { throw "/avatar-session missing usage ledger" }
Pass "/avatar-session returns entitlement-gated runtime decision"

Step "API /product-event"
$eventBody = '{"eventName":"voice_session_completed","personId":"local-person-self","properties":{"durationMs":90000,"turnCount":5}}'
$productEvent = Invoke-RestMethod -Uri "$BaseUrl/product-event" -Method Post -ContentType "application/json; charset=utf-8" -Body $eventBody -TimeoutSec 30
if (-not $productEvent.ok) { throw "/product-event returned not ok" }
if ($productEvent.northStar.meaningfulCompanionDays -lt 1) { throw "/product-event did not update North Star summary" }
Pass "/product-event records meaningful event"

Step "API /admin/north-star gate"
try {
  Invoke-RestMethod -Uri "$BaseUrl/admin/north-star" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"days":7}' -TimeoutSec 30 | Out-Null
  throw "/admin/north-star should require admin token"
} catch {
  $message = $_.Exception.Message
  if ($message -notmatch "403" -and $message -notmatch "Forbidden") { throw }
}
Pass "/admin/north-star is closed without admin token"

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
