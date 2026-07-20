param(
  [string]$BaseUrl = "http://127.0.0.1:8200",
  [switch]$SkipApi,
  [switch]$SkipVoice
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
if ($SkipApi) {
  $env:MUNEA_SKIP_ENV_LOCAL = "1"
  Remove-Item Env:MUNEA_DATABASE_PROVIDER -ErrorAction SilentlyContinue
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

$Python = Resolve-Python

function Invoke-PythonBlock {
  param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Code
  )

  $tempPath = Join-Path ([System.IO.Path]::GetTempPath()) ("munea-smoke-" + [System.Guid]::NewGuid().ToString("N") + ".py")
  try {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($tempPath, $Code, $utf8NoBom)
    & $Python $tempPath
    if ($LASTEXITCODE -ne 0) {
      throw "Python smoke block failed with exit code $LASTEXITCODE"
    }
  } finally {
    Remove-Item -LiteralPath $tempPath -ErrorAction SilentlyContinue
  }
}

Step "Python compile"
& $Python -m py_compile "engine/server.py" "engine/env_loader.py" "engine/supabase_adapter.py" "engine/model_router.py" "engine/chat_engine.py" "engine/nening_brain.py" "engine/characters_demo.py" "scripts/supabase_doctor.py"
if ($LASTEXITCODE -ne 0) {
  throw "Python compile failed with exit code $LASTEXITCODE"
}
Pass "Python files compile"

Step "JSON parse"
Invoke-PythonBlock @'
import json, pathlib
for p in ["engine/characters.json"]:
    json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    print(f"{p} OK")
'@
Pass "Static JSON files parse"

Step "Chat engine profile is local runtime data"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import chat_engine

with tempfile.TemporaryDirectory() as d:
    chat_engine.USER_PROFILE_PATH = str(Path(d) / "user_profile.json")
    profile = chat_engine._read_user_profile()
    assert profile["\u7a31\u547c"] == "\u4f7f\u7528\u8005"
    assert profile["\u56de\u61b6"] == []
    profile["\u56de\u61b6"].append("\u559c\u6b61\u65e9\u4e0a\u6563\u6b65")
    chat_engine._write_user_profile(profile)
    assert Path(chat_engine.USER_PROFILE_PATH).exists()
    loaded = chat_engine._read_user_profile()
    assert loaded["\u56de\u61b6"] == ["\u559c\u6b61\u65e9\u4e0a\u6563\u6b65"]
print("chat engine runtime profile OK")
'@
Pass "Chat engine user profile is runtime-local"

Step "Voice note payload decode"
Invoke-PythonBlock @'
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
'@
Pass "Voice note payload decodes with safety guards"

Step "Companion profile contract"
Invoke-PythonBlock @'
import os, sys
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

profile = server.normalize_companion_profile({
    "templateId": "cat",
    "displayName": " \u5c0f\u82b1 ",
    "nameTouched": True,
})
assert profile["templateId"] == "munea-2d-mimi"
assert profile["displayName"] == "\u5c0f\u82b1"
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
'@
Pass "Companion profile and app store contracts are valid"

Step "Supabase adapter contract"
Invoke-PythonBlock @'
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
    contact_person_id = "88888888-8888-4888-8888-888888888888"
    local_member_id = "local-family-daughter"
    if method == "DELETE":
        if table == "family_memberships":
            return [{
                "id": "family-membership-contact",
                "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
                "family_group_id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"],
                "person_id": contact_person_id,
                "role": "viewer",
                "permissions": {"originalMemberId": local_member_id, "receiveSafetyAlerts": False},
                "created_at": "2026-07-08T00:00:00Z",
                "updated_at": "2026-07-08T00:00:00Z",
            }]
    if method in ("POST", "PATCH"):
        if table == "persons":
            person_id = contact_person_id
            if query and str(query.get("id", "")).startswith("eq."):
                person_id = str(query["id"])[3:]
            return [{**payload, "id": payload.get("id") or person_id, "created_at": "2026-07-08T00:00:00Z", "updated_at": "2026-07-08T00:00:00Z"}]
        if table == "family_memberships":
            return [{
                **payload,
                "id": payload.get("id") or "family-membership-contact",
                "created_at": "2026-07-08T00:00:00Z",
                "updated_at": "2026-07-08T00:00:00Z",
            }]
        if table == "subscription_ledger":
            return [{**payload, "id": "sub-ledger-1", "updated_at": "2026-06-29T00:00:00Z"}]
        if table == "usage_ledger":
            return [{**payload, "id": "usage-ledger-1", "updated_at": "2026-06-29T00:00:00Z"}]
        if table == "privacy_requests":
            return [{**payload, "id": "privacy-request-1", "requested_at": "2026-06-29T00:00:00Z"}]
        if table == "routine_reminders":
            return [{**payload, "id": payload.get("id") or "77777777-7777-4777-8777-777777777777", "created_at": "2026-07-08T00:00:00Z", "updated_at": "2026-07-08T00:00:00Z"}]
        if table == "companion_profiles":
            return [{**payload, "updated_at": "2026-06-29T00:00:00Z"}]
        if table == "product_events":
            return [{**payload, "id": "product-event-1", "created_at": "2026-06-29T00:00:00Z"}]
        if table == "memory_items":
            rows = payload if isinstance(payload, list) else [payload]
            return [{**row, "id": f"memory-item-{idx}", "created_at": "2026-06-29T00:00:00Z", "updated_at": "2026-06-29T00:00:00Z"} for idx, row in enumerate(rows, start=1)]
        if table == "conversation_summaries":
            return [{**payload, "id": payload.get("id") or "99999999-9999-4999-8999-999999999999", "created_at": "2026-07-08T00:00:00Z", "deleted_at": payload.get("deleted_at")}]
        if table == "perception_snapshots":
            rows = payload if isinstance(payload, list) else [payload]
            return [{**row, "id": f"perception-snapshot-{idx}", "created_at": "2026-06-29T00:00:00Z"} for idx, row in enumerate(rows, start=1)]
        if table == "companion_relationship_states":
            return [{**payload, "id": "relationship-state-1", "created_at": "2026-06-29T00:00:00Z", "updated_at": "2026-06-29T00:00:00Z"}]
        if table == "credit_wallets":
            return [{**payload, "id": "credit-wallet-1", "created_at": "2026-06-29T00:00:00Z", "updated_at": "2026-06-29T00:00:00Z"}]
        if table == "credit_transactions":
            return [{**payload, "id": "credit-transaction-1", "created_at": "2026-06-29T00:00:00Z"}]
        if table == "credit_ledger":
            return [{**payload, "id": "credit-ledger-1", "created_at": "2026-06-29T00:00:00Z"}]
        if table == "audit_events":
            return [{**payload, "id": "audit-event-1", "created_at": "2026-06-29T00:00:00Z"}]
        if table == "family_state_entries":
            return [{**payload, "id": "family-state-entry-1", "created_at": "2026-06-29T00:00:00Z", "updated_at": "2026-06-29T00:00:00Z"}]
        if table == "family_invitations":
            return [{**payload, "id": payload.get("id") or "55555555-5555-4555-8555-555555555555", "created_at": "2026-07-08T00:00:00Z", "updated_at": "2026-07-08T00:00:00Z"}]
        if table == "consent_records":
            return [{**payload, "id": payload.get("id") or "66666666-6666-4666-8666-666666666666", "created_at": "2026-07-08T00:00:00Z"}]
        if table == "wellbeing_signals":
            return [{**payload, "id": "wellbeing-signal-1", "created_at": "2026-07-07T00:00:00Z", "observed_at": payload.get("observed_at") or "2026-07-07T00:00:00Z"}]
        if table == "family_activities":
            return [{**payload, "id": payload.get("id") or "44444444-4444-4444-8444-444444444444", "created_at": "2026-07-07T00:00:00Z", "updated_at": "2026-07-07T00:00:00Z"}]
        if table == "family_activity_participants":
            return [{**payload, "id": "family-activity-participant-1", "created_at": "2026-07-07T00:00:00Z", "updated_at": "2026-07-07T00:00:00Z"}]
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
            "id": contact_person_id if query and str(query.get("id", "")) == f"eq.{contact_person_id}" else env["MUNEA_SUPABASE_PERSON_ID"],
            "display_name": "Daughter" if query and str(query.get("id", "")) == f"eq.{contact_person_id}" else "Primary user",
            "relationship": "daughter" if query and str(query.get("id", "")) == f"eq.{contact_person_id}" else "self",
        }],
        "family_groups": [{
            "id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"] or "33333333-3333-4333-8333-333333333333",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "name": "Munea Care Circle",
        }],
        "family_memberships": [{
            "id": "family-membership-contact" if query and "permissions->>originalMemberId" in (query or {}) else "family-membership-primary",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "family_group_id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"],
            "person_id": contact_person_id if query and "permissions->>originalMemberId" in (query or {}) else env["MUNEA_SUPABASE_PERSON_ID"],
            "role": "viewer" if query and "permissions->>originalMemberId" in (query or {}) else "primary_user",
            "permissions": {"originalMemberId": local_member_id, "receiveSafetyAlerts": False} if query and "permissions->>originalMemberId" in (query or {}) else {"manageCompanion": True},
            "created_at": "2026-07-08T00:00:00Z",
            "updated_at": "2026-07-08T00:00:00Z",
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
            "product_id": "net.munea.app.pro.monthly",
            "original_transaction_id": "1000000000000001",
            "status": "active",
            "active_plan": "pro",
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
        "routine_reminders": [{
            "id": "77777777-7777-4777-8777-777777777777",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "title": "Vitamin D after breakfast",
            "reminder_type": "medication",
            "schedule": {"weekday": "Wednesday", "time": "09:00", "dosage": "1 tablet"},
            "status": "active",
            "created_at": "2026-07-08T00:00:00Z",
            "updated_at": "2026-07-08T00:00:00Z",
            "deleted_at": None,
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
        "conversation_summaries": [{
            "id": "99999999-9999-4999-8999-999999999999",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "voice_session_id": None,
            "summary": "User felt lonely but enjoyed talking about Korean dramas.",
            "memory_tags": ["emotion", "video_entertainment"],
            "safety_relevant": False,
            "created_at": "2026-07-08T00:00:00Z",
            "deleted_at": None,
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
        "companion_relationship_states": [{
            "id": "relationship-state-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "companion_profile_id": None,
            "persona_template_id": "nening-real-female",
            "rapport_level": "familiar",
            "preferred_address": None,
            "tone_overrides": {"speechFirst": True},
            "user_boundaries": {"noRawTranscriptRetention": True},
            "relationship_memory": {"lastTopicDomains": ["video_entertainment"]},
            "updated_by_brain_run_id": None,
            "created_at": "2026-06-29T00:00:00Z",
            "updated_at": "2026-06-29T00:00:00Z",
        }],
        "credit_wallets": [
            {
                "id": "credit-wallet-included",
                "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
                "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
                "wallet_type": "included_monthly",
                "period": "2026-07",
                "balance": 10,
                "currency_code": "MUNEA_CREDIT",
                "status": "active",
                "expires_at": "2026-07-31T23:59:59Z",
                "metadata": {},
                "created_at": "2026-06-29T00:00:00Z",
                "updated_at": "2026-06-29T00:00:00Z",
            },
            {
                "id": "credit-wallet-purchased",
                "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
                "person_id": None,
                "wallet_type": "purchased",
                "period": None,
                "balance": 5,
                "currency_code": "MUNEA_CREDIT",
                "status": "active",
                "expires_at": None,
                "metadata": {},
                "created_at": "2026-06-29T00:00:00Z",
                "updated_at": "2026-06-29T00:00:00Z",
            },
        ],
        "credit_transactions": [{
            "id": "credit-transaction-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "wallet_id": "credit-wallet-included",
            "transaction_type": "grant",
            "source": "included_monthly",
            "amount": 10,
            "balance_after": 10,
            "provider": None,
            "provider_transaction_id": None,
            "idempotency_key": "smoke-credit-grant-existing",
            "reason": "monthly allowance",
            "metadata": {"localWalletId": "wallet_included_monthly", "walletType": "included_monthly", "feature": "premium_avatar"},
            "created_at": "2026-06-29T00:00:00Z",
        }],
        "credit_ledger": [{
            "id": "credit-ledger-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "wallet_id": "credit-wallet-included",
            "credit_transaction_id": "credit-transaction-1",
            "event_type": "included_allowance_granted",
            "amount": 10,
            "balance_after": 10,
            "feature": "premium_avatar",
            "source_ref": "credit-transaction-1",
            "metadata": {"localWalletId": "wallet_included_monthly"},
            "created_at": "2026-06-29T00:00:00Z",
        }],
        "family_state_entries": [{
            "id": "family-state-entry-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "family_group_id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"],
            "state_key": "familyFeed",
            "value": [{"id": "feed-1", "text": "Medication checked"}],
            "updated_by_person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "created_at": "2026-06-29T00:00:00Z",
            "updated_at": "2026-06-29T00:00:00Z",
        }],
        "family_invitations": [{
            "id": "55555555-5555-4555-8555-555555555555",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "family_group_id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"],
            "inviter_person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "invitee_person_id": None,
            "token_hash": "hashed-token",
            "short_code": "123456",
            "delivery_hint": "line",
            "elder_assisted": True,
            "status": "pending",
            "expires_at": "2026-07-10T00:00:00Z",
            "accepted_at": None,
            "revoked_at": None,
            "metadata": {"relation": "daughter"},
            "created_at": "2026-07-08T00:00:00Z",
            "updated_at": "2026-07-08T00:00:00Z",
        }],
        "consent_records": [{
            "id": "66666666-6666-4666-8666-666666666666",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "family_group_id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"],
            "consent_type": "family_link",
            "consent_version": "v1",
            "status": "granted",
            "granted_by_person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "source": "smoke",
            "scope": {"shareMoodWeather": True},
            "evidence": {"method": "tap"},
            "granted_at": "2026-07-08T00:00:00Z",
            "revoked_at": None,
            "expires_at": None,
            "created_at": "2026-07-08T00:00:00Z",
        }],
        "wellbeing_signals": [{
            "id": "wellbeing-signal-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "family_group_id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"],
            "signal_date": "2026-07-07",
            "signal_type": "mood",
            "mood": "steady",
            "level": 4,
            "visibility": "family_summary",
            "facts": {
                "originalMood": "穩定",
                "moodKey": "steady",
                "moodColor": {"hex": "#3AA8A0"},
                "levelLabel": "穩定",
                "confidence": 1.0,
                "modality": "manual",
                "isMedicalInference": False,
            },
            "source": "self-report",
            "observed_at": "2026-07-07T00:00:00Z",
            "created_at": "2026-07-07T00:00:00Z",
        }],
        "family_activities": [{
            "id": "44444444-4444-4444-8444-444444444444",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "family_group_id": env["MUNEA_SUPABASE_FAMILY_GROUP_ID"],
            "owner_person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "activity_type": "walk",
            "title": "Evening walk",
            "status": "active",
            "starts_at": "2026-07-07T10:00:00Z",
            "ends_at": "2026-07-07T12:00:00Z",
            "payload": {"goalSteps": 5000, "originalActivityId": "local-walk-1"},
            "result": {"steps": 1200},
            "created_at": "2026-07-07T00:00:00Z",
            "updated_at": "2026-07-07T00:00:00Z",
            "archived_at": None,
        }],
        "family_activity_participants": [{
            "id": "family-activity-participant-1",
            "account_id": env["MUNEA_SUPABASE_ACCOUNT_ID"],
            "family_activity_id": "44444444-4444-4444-8444-444444444444",
            "person_id": env["MUNEA_SUPABASE_PERSON_ID"],
            "role": "owner",
            "status": "accepted",
            "contribution": {"steps": 1200},
            "response": {"note": "joined"},
            "created_at": "2026-07-07T00:00:00Z",
            "updated_at": "2026-07-07T00:00:00Z",
        }],
    }
    return fixtures[table]

adapter._request = fake_request
store = adapter.load_app_profile_store()
assert store["account"]["locale"] == "zh-TW"
assert store["familyGroup"]["members"][0]["role"] == "primary_user"
assert store["companionProfiles"][env["MUNEA_SUPABASE_PERSON_ID"]]["displayName"] == "Nening"
remote_billing = adapter.load_billing_store()
assert remote_billing["activePlan"] == "pro"
assert remote_billing["subscription"]["status"] == "active"
assert remote_billing["usageLedger"]["voiceMinutesUsed"] == 12
saved_billing = adapter.save_billing_store({
    "activePlan": "pro",
    "provider": "revenuecat",
    "subscription": {"status": "active", "productId": "net.munea.app.pro.monthly"},
    "entitlements": {"voiceCompanion": True, "realtimeAvatar": True},
    "usageLedger": {"period": "2026-06", "voiceMinutesUsed": 1, "avatarMinutesUsed": 1},
})
assert saved_billing["accountId"] == env["MUNEA_SUPABASE_ACCOUNT_ID"]
remote_credits = adapter.load_credits_store()
assert remote_credits["accountId"] == env["MUNEA_SUPABASE_ACCOUNT_ID"]
assert len(remote_credits["wallets"]) == 2
assert sum(w["balance"] for w in remote_credits["wallets"]) == 15
assert remote_credits["transactions"][0]["idempotencyKey"] == "smoke-credit-grant-existing"
saved_credits = adapter.save_credits_store({
    "wallets": [
        {"id": "wallet_included_monthly", "type": "included_monthly", "period": "2026-07", "balance": 8},
        {"id": "wallet_purchased", "type": "purchased", "balance": 4},
    ],
    "transactions": [{
        "id": "local-credit-transaction-1",
        "type": "consume",
        "walletId": "wallet_included_monthly",
        "walletType": "included_monthly",
        "amount": 2,
        "balanceAfter": 8,
        "source": "system",
        "reason": "premium_avatar_overage",
        "feature": "premium_avatar",
        "idempotencyKey": "smoke-credit-consume-new",
    }],
    "ledger": [{
        "id": "local-credit-ledger-1",
        "eventType": "credits_consumed",
        "walletId": "wallet_included_monthly",
        "amount": 2,
        "balanceAfter": 8,
        "feature": "premium_avatar",
        "sourceRef": "local-credit-transaction-1",
    }],
})
assert saved_credits["accountId"] == env["MUNEA_SUPABASE_ACCOUNT_ID"]
saved_audit = adapter.append_audit_event({
    "eventType": "credits_granted",
    "targetTable": "credit_transactions",
    "targetId": "not-a-uuid-local-transaction",
    "details": {"actorType": "admin", "amount": 1},
})
assert saved_audit["eventType"] == "credits_granted"
assert saved_audit["targetId"] is None
privacy_store = adapter.load_privacy_requests_store()
assert privacy_store["requests"][0]["type"] == "export"
privacy_req = adapter.append_privacy_request("account_deletion", {"reason": "test"})
assert privacy_req["type"] == "account_deletion"
assert privacy_req["subscriptionNoticeRequired"] is True
family_members = adapter.load_family_members(limit=10)
assert family_members[0]["role"] == "primary_user"
saved_member = adapter.save_family_member({
    "id": "local-family-daughter",
    "displayName": "Daughter",
    "relationship": "daughter",
    "role": "viewer",
    "permissions": {"receiveSafetyAlerts": False},
})
assert saved_member["id"] == "local-family-daughter"
assert saved_member["role"] == "viewer"
updated_member = adapter.update_family_member("local-family-daughter", {
    "role": "caregiver",
    "permissions": {"receiveSafetyAlerts": True, "manageReminders": True},
})
assert updated_member["role"] == "caregiver"
assert updated_member["permissions"]["originalMemberId"] == "local-family-daughter"
assert updated_member["permissions"]["manageReminders"] is True
removed_member = adapter.remove_family_member("local-family-daughter")
assert removed_member["id"] == "local-family-daughter"
routine_reminders = adapter.load_routine_reminders(status="active", limit=10)
assert routine_reminders[0]["title"] == "Vitamin D after breakfast"
assert routine_reminders[0]["type"] == "medication"
saved_routine = adapter.save_routine_reminder({
    "id": "local-med-1",
    "personId": "local-person-self",
    "title": "Blood pressure check",
    "type": "routine",
    "schedule": {"weekday": "Wednesday", "time": "20:00"},
})
assert saved_routine["title"] == "Blood pressure check"
assert saved_routine["schedule"]["originalReminderId"] == "local-med-1"
local_routine_row = adapter.routine_reminder_to_row({
    "id": "local-visit-1",
    "personId": "local-person-self",
    "title": "Clinic visit",
    "type": "check_in",
    "date": "2026-07-09",
})
assert local_routine_row["person_id"] == env["MUNEA_SUPABASE_PERSON_ID"]
assert local_routine_row["schedule"]["originalPersonId"] == "local-person-self"
archived_routine = adapter.update_routine_reminder("77777777-7777-4777-8777-777777777777", {"status": "archived"})
assert archived_routine["status"] == "archived"
rescheduled_routine = adapter.update_routine_reminder("77777777-7777-4777-8777-777777777777", {"schedule": {"time": "10:00"}})
assert rescheduled_routine["schedule"]["time"] == "10:00"
assert rescheduled_routine["schedule"]["dosage"] == "1 tablet"
archived_local_routine = adapter.update_routine_reminder("local-med-1", {"status": "archived"})
assert archived_local_routine["status"] == "archived"
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
conversation_summaries = adapter.load_conversation_summaries(limit=10)
assert conversation_summaries[0]["summary"].startswith("User felt lonely")
assert conversation_summaries[0]["privacy"]["storesRawTranscriptByDefault"] is False
saved_summary = adapter.save_conversation_summary({
    "personId": "local-person-self",
    "summary": "User enjoyed a short check-in and asked to remember Korean dramas.",
    "memoryTags": ["preference", "video_entertainment"],
})
assert saved_summary["summary"].startswith("User enjoyed")
assert saved_summary["accountId"] == env["MUNEA_SUPABASE_ACCOUNT_ID"]
assert saved_summary["memoryTags"] == ["preference", "video_entertainment"]
archived_summary = adapter.soft_delete_conversation_summary("99999999-9999-4999-8999-999999999999", "2026-07-08T01:00:00Z")
assert archived_summary["deletedAt"] == "2026-07-08T01:00:00Z"
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
relationships = adapter.load_relationship_states({"templateId": "nening-real-female"}, limit=10)
assert relationships[0]["rapportLevel"] == "familiar"
saved_relationship = adapter.save_relationship_state({
    "personId": env["MUNEA_SUPABASE_PERSON_ID"],
    "personaTemplateId": "companion-real-male",
    "rapportLevel": "trusted",
    "relationshipMemory": {"lastTopicDomains": ["travel"]},
})
assert saved_relationship["personaTemplateId"] == "companion-real-male"
assert saved_relationship["rapportLevel"] == "trusted"
family_state = adapter.load_family_state_store()
assert family_state["familyFeed"]["value"][0]["text"] == "Medication checked"
saved_family_state = adapter.save_family_state_entry("meds", [{"name": "Vitamin D"}])
assert saved_family_state["key"] == "meds"
assert saved_family_state["value"][0]["name"] == "Vitamin D"
invitations = adapter.load_family_invitations(status="pending", limit=10)
assert invitations[0]["shortCode"] == "123456"
assert invitations[0]["elderAssisted"] is True
saved_invitation = adapter.create_family_invitation({
    "familyGroupId": "local-family",
    "inviterPersonId": "local-person-self",
    "shortCode": "654321",
    "shareToken": "raw-token-once",
    "deliveryHint": "sms",
    "elderAssisted": True,
    "metadata": {"relation": "son"},
})
assert saved_invitation["shortCode"] == "654321"
assert "shareToken" not in saved_invitation
local_invitation_row = adapter.family_invitation_to_row({
    "familyGroupId": "local-family",
    "inviterPersonId": "local-person-self",
    "inviteePersonId": "local-person-child",
    "shortCode": "111222",
    "shareToken": "raw-token-once",
})
assert local_invitation_row["family_group_id"] == env["MUNEA_SUPABASE_FAMILY_GROUP_ID"]
assert local_invitation_row["inviter_person_id"] == env["MUNEA_SUPABASE_PERSON_ID"]
assert local_invitation_row["invitee_person_id"] is None
assert local_invitation_row["metadata"]["originalInviteePersonId"] == "local-person-child"
accepted_invitation = adapter.update_family_invitation("55555555-5555-4555-8555-555555555555", {"status": "accepted"})
assert accepted_invitation["status"] == "accepted"
consents = adapter.load_consent_records(consent_type="family_link", status="granted", limit=10)
assert consents[0]["consentType"] == "family_link"
assert consents[0]["scope"]["shareMoodWeather"] is True
saved_consent = adapter.append_consent_record({
    "personId": "local-person-self",
    "familyGroupId": "local-family",
    "consentType": "share_mood_weather",
    "grantedByPersonId": "local-person-child",
    "scope": {"visibility": "family_summary"},
    "evidence": {"method": "tap"},
    "source": "settings",
})
assert saved_consent["consentType"] == "share_mood_weather"
local_consent_row = adapter.consent_record_to_row({
    "personId": "local-person-self",
    "familyGroupId": "local-family",
    "grantedByPersonId": "local-person-child",
    "consentType": "capability:voice_emotion",
})
assert local_consent_row["person_id"] == env["MUNEA_SUPABASE_PERSON_ID"]
assert local_consent_row["family_group_id"] == env["MUNEA_SUPABASE_FAMILY_GROUP_ID"]
assert local_consent_row["scope"]["originalPersonId"] == "local-person-self"
assert local_consent_row["evidence"]["originalGrantedByPersonId"] == "local-person-child"
revoked_consent = adapter.revoke_consent_record("66666666-6666-4666-8666-666666666666", patch={"revokedByPersonId": "local-person-self"})
assert revoked_consent["status"] == "revoked"
wellbeing = adapter.load_wellbeing_signals(limit=10)
assert wellbeing[0]["mood"] == "穩定"
assert wellbeing[0]["moodKey"] == "steady"
saved_wellbeing = adapter.append_wellbeing_signal({
    "personId": env["MUNEA_SUPABASE_PERSON_ID"],
    "date": "2026-07-07",
    "mood": "開心",
    "moodKey": "happy",
    "level": 5,
    "source": "self-report",
    "createdAt": "2026-07-07T00:01:00Z",
})
assert saved_wellbeing["mood"] == "開心"
assert saved_wellbeing["moodKey"] == "happy"
local_wellbeing_row = adapter.wellbeing_signal_to_row({
    "personId": "local-person-self",
    "familyGroupId": "local-family",
    "date": "2026-07-07",
    "mood": "平穩",
    "moodKey": "steady",
})
assert local_wellbeing_row["person_id"] == env["MUNEA_SUPABASE_PERSON_ID"]
assert local_wellbeing_row["family_group_id"] == env["MUNEA_SUPABASE_FAMILY_GROUP_ID"]
assert local_wellbeing_row["facts"]["originalPersonId"] == "local-person-self"
assert local_wellbeing_row["facts"]["originalMood"] == "平穩"

activities = adapter.load_family_activities(status="active", limit=10)
assert activities[0]["title"] == "Evening walk"
assert activities[0]["participants"][0]["status"] == "accepted"
saved_activity = adapter.save_family_activity({
    "id": "local-walk-2",
    "familyGroupId": "local-family",
    "ownerPersonId": "local-person-self",
    "type": "walk",
    "title": "Morning walk",
    "status": "active",
    "payload": {"goalSteps": 3000},
    "participants": [{"personId": "local-person-self", "role": "owner", "status": "accepted"}],
})
assert saved_activity["title"] == "Morning walk"
assert saved_activity["payload"]["originalActivityId"] == "local-walk-2"
saved_participant = adapter.save_family_activity_participant("44444444-4444-4444-8444-444444444444", {
    "personId": "local-person-self",
    "status": "completed",
    "contribution": {"steps": 3000},
})
assert saved_participant["status"] == "completed"
assert saved_participant["contribution"]["originalPersonId"] == "local-person-self"

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
'@
Pass "Supabase adapter supports profile, billing, usage, and privacy contracts"

Step "Account bootstrap contract"
Invoke-PythonBlock @'
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
'@
Pass "Account bootstrap creates local account/family/person/companion store"

Step "Family state cloud bridge contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

test_group_id = "11111111-1111-4111-8111-111111111111"

class FakeFamilyStateBackend:
    account_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    def enabled(self):
        return True
    def family_group_account_id(self, family_group_id):
        assert family_group_id == test_group_id
        return self.account_id
    def load_billing_store(self):
        store = server.default_billing_store()
        store["accountId"] = self.account_id
        return store
    def load_family_state_store(self, family_group_id=None):
        assert family_group_id == test_group_id
        return {
            "familyFeed": {"value": [{"id": "feed-1", "text": "Cloud feed"}], "updatedAt": "2026-07-07T00:00:00Z"},
            "meds": {"value": [{"name": "Vitamin D"}], "updatedAt": "2026-07-07T00:00:00Z"},
        }
    def save_family_state_entry(self, key, value, family_group_id=None, updated_by_person_id=None):
        assert key == "wallet"
        assert value["points"] == 12
        assert family_group_id == test_group_id
        assert updated_by_person_id == "person-1"
        return {"key": key, "value": value, "updatedAt": "2026-07-07T00:00:00Z"}

original_backend = server.data_backend
try:
    server.data_backend = lambda: FakeFamilyStateBackend()
    loaded = server.family_state_response({"action": "load", "familyGroupId": test_group_id})
    assert loaded["ok"] is True
    assert loaded["backend"] == "supabase"
    assert loaded["state"]["familyFeed"][0]["text"] == "Cloud feed"
    saved = server.family_state_response({"action": "save", "key": "wallet", "value": {"points": 12}, "familyGroupId": test_group_id, "personId": "person-1"})
    assert saved["ok"] is True
    assert saved["backend"] == "supabase"
finally:
    server.data_backend = original_backend

class DisabledBackend:
    def enabled(self):
        return False
    def load_family_state_store(self, family_group_id=None):
        return None
    def save_family_state_entry(self, key, value, family_group_id=None, updated_by_person_id=None):
        return None

with tempfile.TemporaryDirectory() as d:
    server.FAMILY_STATE_STORE_PATH = str(Path(d) / "family_state_store.json")
    try:
        server.data_backend = lambda: DisabledBackend()
        saved = server.family_state_response({"action": "save", "key": "routine", "value": {"done": True}})
        assert saved["backend"] == "json"
        loaded = server.family_state_response({"action": "load"})
        assert loaded["state"]["routine"]["done"] is True
    finally:
        server.data_backend = original_backend
print("family state cloud bridge OK")
'@
Pass "Family state can use Supabase while preserving JSON fallback"

Step "Family invitation cloud bridge contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

class FakeFamilyInvitationBackend:
    request_scoped = True
    auth_user_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    person_id = "22222222-2222-4222-8222-222222222222"
    family_group_id = "33333333-3333-4333-8333-333333333333"
    def enabled(self):
        return True
    def is_account_owner(self):
        return True
    def load_billing_store(self):
        return {
            "activePlan": "plus",
            "serverVerificationRequired": False,
            "subscription": {"status": "active"},
        }
    def load_family_invitations(self, family_group_id=None, status=None, limit=100):
        assert family_group_id in (None, "family-1")
        assert status in (None, "pending")
        return [{
            "id": "invite-1",
            "familyGroupId": "family-1",
            "inviterPersonId": "person-1",
            "shortCode": "123456",
            "deliveryHint": "line",
            "elderAssisted": True,
            "status": "pending",
            "expiresAt": "2026-07-10T00:00:00Z",
            "metadata": {"relation": "daughter"},
        }]
    def create_family_invitation(self, invitation):
        assert invitation["familyGroupId"] == self.family_group_id
        assert invitation["inviterPersonId"] == self.person_id
        assert invitation["metadata"]["maxMembers"] == 4
        assert invitation["metadata"]["ownerAuthUserId"] == self.auth_user_id
        return {**invitation, "id": "invite-2"}
    def update_family_invitation(self, invitation_id, patch):
        assert invitation_id == "invite-2"
        assert patch["status"] == "accepted"
        return {
            "id": "invite-2",
            "familyGroupId": "family-1",
            "inviterPersonId": "person-1",
            "shortCode": "654321",
            "status": "accepted",
            "acceptedAt": "2026-07-08T00:00:00Z",
        }

original_backend = server.data_backend
try:
    backend = FakeFamilyInvitationBackend()
    server.data_backend = lambda: backend
    denied = server.family_invitations_response({"action": "create"})
    assert denied["error"] == "auth_required"
    created = server.family_invitations_response(
        {"action": "create", "familyGroupId": "forged-family", "inviterPersonId": "forged-person"},
        actor={"authUserId": backend.auth_user_id},
    )
    assert created["backend"] == "supabase"
    assert created["invitation"]["id"] == "invite-2"
finally:
    server.data_backend = original_backend

class DisabledBackend:
    request_scoped = False
    def enabled(self):
        return False
    def load_family_invitations(self, family_group_id=None, status=None, limit=100):
        return None
    def create_family_invitation(self, invitation):
        return None
    def update_family_invitation(self, invitation_id, patch):
        return None

with tempfile.TemporaryDirectory() as d:
    server.FAMILY_INVITATIONS_PATH = str(Path(d) / "family_invitations.json")
    try:
        server.data_backend = lambda: DisabledBackend()
        unavailable = server.family_invitations_response(
            {"action": "create"}, actor={"authUserId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}
        )
        assert unavailable["error"] == "family_cloud_identity_required"
    finally:
        server.data_backend = original_backend
print("family invitation cloud bridge OK")
'@
Pass "Family invitations require verified cloud identity and server entitlements"

Step "Family members cloud bridge contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

class FakeFamilyMembersBackend:
    def enabled(self):
        return True
    def load_family_members(self, family_group_id=None, limit=100):
        assert family_group_id in (None, "family-1")
        return [{
            "id": "member-1",
            "displayName": "Daughter",
            "relationship": "daughter",
            "role": "viewer",
            "permissions": {"receiveSafetyAlerts": False},
        }]
    def save_family_member(self, member, family_group_id=None):
        assert family_group_id == "family-1"
        assert member["displayName"] == "Son"
        return {**member, "id": "member-2"}
    def update_family_member(self, member_id, patch, family_group_id=None):
        assert member_id == "member-2"
        assert patch["role"] == "caregiver"
        return {
            "id": member_id,
            "displayName": "Son",
            "relationship": "son",
            "role": "caregiver",
            "permissions": patch.get("permissions") or {},
        }
    def remove_family_member(self, member_id, family_group_id=None):
        assert member_id == "member-2"
        return {
            "id": member_id,
            "displayName": "Son",
            "relationship": "son",
            "role": "caregiver",
            "permissions": {},
        }

original_backend = server.data_backend
try:
    server.data_backend = lambda: FakeFamilyMembersBackend()
    listed = server.family_members_response({"action": "list", "familyGroupId": "family-1"})
    assert listed["ok"] is True
    assert listed["members"][0]["role"] == "viewer"
    saved = server.family_members_response({"action": "save", "familyGroupId": "family-1", "member": {"displayName": "Son", "relationship": "son", "role": "viewer"}})
    assert saved["backend"] == "supabase"
    assert saved["member"]["id"] == "member-2"
    updated = server.family_members_response({"action": "update", "id": "member-2", "patch": {"role": "caregiver", "permissions": {"manageReminders": True}}})
    assert updated["backend"] == "supabase"
    assert updated["member"]["role"] == "caregiver"
    removed = server.family_members_response({"action": "remove", "id": "member-2"})
    assert removed["backend"] == "supabase"
finally:
    server.data_backend = original_backend

class DisabledBackend:
    def enabled(self):
        return False
    def load_family_members(self, family_group_id=None, limit=100):
        return None
    def save_family_member(self, member, family_group_id=None):
        return None
    def update_family_member(self, member_id, patch, family_group_id=None):
        return None
    def remove_family_member(self, member_id, family_group_id=None):
        return None
    def load_app_profile_store(self):
        return None
    def save_app_profile_store(self, store):
        return None

with tempfile.TemporaryDirectory() as d:
    server.APP_PROFILE_STORE_PATH = str(Path(d) / "app_profile_store.json")
    server.COMPANION_PROFILE_PATH = str(Path(d) / "companion_profile.json")
    try:
        server.data_backend = lambda: DisabledBackend()
        saved = server.family_members_response({"action": "save", "member": {"id": "local-son", "displayName": "Son", "relationship": "son", "role": "viewer"}})
        assert saved["backend"] == "json"
        listed = server.family_members_response({"action": "list"})
        assert any(m["id"] == "local-son" for m in listed["members"])
        updated = server.family_members_response({"action": "update", "id": "local-son", "patch": {"role": "caregiver", "permissions": {"manageReminders": True}}})
        assert updated["backend"] == "json"
        assert updated["member"]["role"] == "caregiver"
        assert updated["member"]["permissions"]["manageReminders"] is True
        removed = server.family_members_response({"action": "remove", "id": "local-son"})
        assert removed["backend"] == "json"
        after = server.family_members_response({"action": "list"})
        assert all(m["id"] != "local-son" for m in after["members"])
    finally:
        server.data_backend = original_backend
print("family members cloud bridge OK")
'@
Pass "Family members can use Supabase while preserving JSON fallback"

Step "Admin account lookup contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

class FakeAdminAccountsBackend:
    def enabled(self):
        return True
    def status(self):
        return {"provider": "supabase", "enabled": True, "missing": []}
    def load_admin_accounts(self, query=None, limit=50):
        return [{
            "accountId": "account-remote",
            "accountName": "Remote care account",
            "locale": "zh-TW",
            "preferredLanguages": ["zh-TW", "en"],
            "familyGroup": {"id": "family-remote", "name": "Remote family"},
            "primaryPerson": {"id": "person-remote", "displayName": "Auntie", "relationship": "self"},
            "companion": {"templateId": "nening-real-female", "displayName": "Munea", "nameTouched": False},
            "familyMembers": {"count": 2, "byRole": {"primary_user": 1, "caregiver": 1}},
        }]

class DisabledBackend:
    def enabled(self):
        return False
    def status(self):
        return {"provider": "json", "enabled": False, "missing": []}
    def load_admin_accounts(self, query=None, limit=50):
        return None
    def load_app_profile_store(self):
        return None
    def save_app_profile_store(self, store):
        return None

original_backend = server.data_backend
try:
    server.data_backend = lambda: FakeAdminAccountsBackend()
    remote = server.admin_accounts_summary({"query": "Remote"})
    assert remote["ok"] is True
    assert remote["count"] == 1
    assert remote["accounts"][0]["accountId"] == "account-remote"
    assert remote["accounts"][0]["familyMembers"]["byRole"]["caregiver"] == 1
    assert remote["privacy"]["rawTranscriptRecords"] == 0
finally:
    server.data_backend = original_backend

with tempfile.TemporaryDirectory() as d:
    server.APP_PROFILE_STORE_PATH = str(Path(d) / "app_profile_store.json")
    server.COMPANION_PROFILE_PATH = str(Path(d) / "companion_profile.json")
    server._APP_PROFILE_CACHE["store"] = None
    try:
        server.data_backend = lambda: DisabledBackend()
        server.save_app_profile_store({
            "account": {"id": "local-account-1", "name": "Local care account", "locale": "zh-TW"},
            "familyGroup": {
                "id": "family-local-1",
                "name": "Local family",
                "members": [
                    {"id": "person-local-1", "role": "primary_user", "displayName": "Edward", "relationship": "self"},
                    {"id": "person-local-2", "role": "caregiver", "displayName": "Daughter", "relationship": "daughter"},
                ],
            },
            "primaryCareRecipientId": "person-local-1",
            "companionProfiles": {"person-local-1": {"templateId": "nening-real-female", "displayName": "Ning"}},
        })
        local = server.admin_accounts_summary({"query": "Edward"})
        assert local["ok"] is True
        assert local["count"] == 1
        assert local["accounts"][0]["accountId"] == "local-account-1"
        assert local["accounts"][0]["familyGroup"]["id"] == "family-local-1"
        assert local["accounts"][0]["primaryPerson"]["displayName"] == "Edward"
        assert local["accounts"][0]["familyMembers"]["count"] == 2
        by_person = server.admin_accounts_summary({"personId": "person-local-1"})
        assert by_person["count"] == 1
    finally:
        server._APP_PROFILE_CACHE["store"] = None
        server.data_backend = original_backend
print("admin account lookup OK")
'@
Pass "Admin account lookup supports Supabase and JSON fallback"

Step "Consent records cloud bridge contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

class FakeConsentBackend:
    def enabled(self):
        return True
    def load_consent_records(self, person_id=None, consent_type=None, status=None, limit=100):
        assert person_id in (None, "person-1")
        assert consent_type in (None, "family_link")
        assert status in (None, "granted")
        return [{
            "id": "consent-1",
            "personId": "person-1",
            "familyGroupId": "family-1",
            "consentType": "family_link",
            "consentVersion": "v1",
            "status": "granted",
            "scope": {"familyLink": True},
            "evidence": {"method": "tap"},
            "grantedAt": "2026-07-08T00:00:00Z",
        }]
    def append_consent_record(self, record):
        assert record["consentType"] == "share_mood_weather"
        return {**record, "id": "consent-2"}
    def revoke_consent_record(self, record_id=None, person_id=None, consent_type=None, patch=None):
        assert record_id == "consent-2" or (person_id == "person-1" and consent_type == "share_mood_weather")
        return {
            "id": record_id or "consent-2",
            "personId": person_id or "person-1",
            "consentType": consent_type or "share_mood_weather",
            "status": "revoked",
            "revokedAt": "2026-07-08T00:01:00Z",
            "evidence": {"revokedByPersonId": "person-1"},
        }

original_backend = server.data_backend
try:
    server.data_backend = lambda: FakeConsentBackend()
    listed = server.consent_records_response({"action": "list", "personId": "person-1", "consentType": "family_link", "status": "granted"})
    assert listed["ok"] is True
    assert listed["records"][0]["consentType"] == "family_link"
    granted = server.consent_records_response({"action": "grant", "record": {"personId": "person-1", "consentType": "share_mood_weather", "scope": {"visibility": "family_summary"}}})
    assert granted["backend"] == "supabase"
    assert granted["record"]["id"] == "consent-2"
    revoked = server.consent_records_response({"action": "revoke", "id": "consent-2"})
    assert revoked["backend"] == "supabase"
    assert revoked["record"]["status"] == "revoked"
finally:
    server.data_backend = original_backend

class DisabledBackend:
    def enabled(self):
        return False
    def load_consent_records(self, person_id=None, consent_type=None, status=None, limit=100):
        return None
    def append_consent_record(self, record):
        return None
    def revoke_consent_record(self, record_id=None, person_id=None, consent_type=None, patch=None):
        return None

with tempfile.TemporaryDirectory() as d:
    server.CONSENT_RECORDS_PATH = str(Path(d) / "consent_records.json")
    try:
        server.data_backend = lambda: DisabledBackend()
        granted = server.consent_records_response({"action": "grant", "record": {"personId": "person-1", "consentType": "capability:voice_emotion"}})
        assert granted["backend"] == "json"
        listed = server.consent_records_response({"action": "list", "personId": "person-1"})
        assert listed["records"][0]["consentType"] == "capability:voice_emotion"
        revoked = server.consent_records_response({"action": "revoke", "personId": "person-1", "consentType": "capability:voice_emotion"})
        assert revoked["backend"] == "json"
        assert revoked["record"]["status"] == "revoked"
    finally:
        server.data_backend = original_backend
print("consent records cloud bridge OK")
'@
Pass "Consent records can use Supabase while preserving JSON fallback"

Step "Routine reminders cloud bridge contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

class FakeRoutineBackend:
    def enabled(self):
        return True
    def load_routine_reminders(self, person_id=None, status=None, limit=100):
        assert person_id in (None, "person-1")
        assert status in (None, "active")
        return [{
            "id": "reminder-1",
            "personId": "person-1",
            "title": "Take morning medicine",
            "type": "medication",
            "status": "active",
            "schedule": {"weekday": "Wednesday", "time": "09:00"},
            "createdAt": "2026-07-08T00:00:00Z",
        }]
    def save_routine_reminder(self, item):
        assert item["title"] == "Evening walk"
        return {**item, "id": "reminder-2"}
    def update_routine_reminder(self, reminder_id, patch):
        assert reminder_id == "reminder-2"
        assert patch["status"] in ("archived", "paused", "active")
        return {
            "id": reminder_id,
            "personId": "person-1",
            "title": "Evening walk",
            "type": "routine",
            "status": patch["status"],
            "schedule": {"weekday": "Wednesday"},
        }

original_backend = server.data_backend
try:
    server.data_backend = lambda: FakeRoutineBackend()
    listed = server.routine_reminders_response({"action": "list", "personId": "person-1", "status": "active"})
    assert listed["ok"] is True
    assert listed["reminders"][0]["title"] == "Take morning medicine"
    saved = server.routine_reminders_response({"action": "save", "reminder": {"personId": "person-1", "title": "Evening walk", "type": "routine", "weekday": "Wednesday"}})
    assert saved["backend"] == "supabase"
    assert saved["reminder"]["id"] == "reminder-2"
    archived = server.routine_reminders_response({"action": "archive", "id": "reminder-2"})
    assert archived["backend"] == "supabase"
    assert archived["reminder"]["status"] == "archived"
    care = server.care_schedule_response({"action": "list", "personId": "person-1"})
    assert care["items"][0]["label"] == "Take morning medicine"
finally:
    server.data_backend = original_backend

class DisabledBackend:
    def enabled(self):
        return False
    def load_routine_reminders(self, person_id=None, status=None, limit=100):
        return None
    def save_routine_reminder(self, item):
        return None
    def update_routine_reminder(self, reminder_id, patch):
        return None

with tempfile.TemporaryDirectory() as d:
    server.CARE_SCHEDULE_PATH = str(Path(d) / "care_schedule.json")
    try:
        server.data_backend = lambda: DisabledBackend()
        saved = server.routine_reminders_response({"action": "save", "reminder": {"personId": "person-1", "title": "Clinic visit", "type": "check_in", "date": "2026-07-09"}})
        assert saved["backend"] == "json"
        listed = server.routine_reminders_response({"action": "list", "personId": "person-1"})
        assert listed["reminders"][0]["title"] == "Clinic visit"
        care_added = server.care_schedule_response({"action": "add", "personId": "person-1", "label": "Drink water", "weekday": "Wednesday"})
        assert care_added["item"]["label"] == "Drink water"
        care_list = server.care_schedule_response({"action": "list", "personId": "person-1"})
        assert any(item["label"] == "Drink water" for item in care_list["items"])
        archived = server.routine_reminders_response({"action": "archive", "id": saved["reminder"]["id"]})
        assert archived["backend"] == "json"
        assert archived["reminder"]["status"] == "archived"
    finally:
        server.data_backend = original_backend
print("routine reminders cloud bridge OK")
'@
Pass "Routine reminders can use Supabase while preserving JSON fallback"

Step "Family activity cloud bridge contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

class FakeFamilyActivityBackend:
    def enabled(self):
        return True
    def load_family_activities(self, family_group_id=None, status=None, limit=100):
        assert family_group_id in (None, "family-1")
        assert status in (None, "active")
        return [{
            "id": "activity-1",
            "familyGroupId": "family-1",
            "ownerPersonId": "person-1",
            "type": "walk",
            "title": "Cloud walk",
            "status": "active",
            "payload": {"goalSteps": 5000},
            "participants": [{"personId": "person-1", "role": "owner", "status": "accepted"}],
            "createdAt": "2026-07-07T00:00:00Z",
            "updatedAt": "2026-07-07T00:00:00Z",
        }]
    def save_family_activity(self, activity):
        assert activity["title"] == "Cloud quiz"
        return {**activity, "id": "activity-2"}
    def save_family_activity_participant(self, activity_id, participant):
        assert activity_id == "activity-2"
        assert participant["status"] == "completed"
        return {**participant, "id": "participant-1"}

original_backend = server.data_backend
try:
    server.data_backend = lambda: FakeFamilyActivityBackend()
    listed = server.family_activity_response({"action": "list", "familyGroupId": "family-1", "status": "active"})
    assert listed["ok"] is True
    assert listed["activities"][0]["title"] == "Cloud walk"
    saved = server.family_activity_response({"action": "save", "activity": {"title": "Cloud quiz", "type": "quiz", "familyGroupId": "family-1", "ownerPersonId": "person-1"}})
    assert saved["backend"] == "supabase"
    assert saved["activity"]["id"] == "activity-2"
    participant = server.family_activity_response({"action": "participant", "activityId": "activity-2", "participant": {"personId": "person-1", "status": "completed"}})
    assert participant["backend"] == "supabase"
    assert participant["participant"]["status"] == "completed"
finally:
    server.data_backend = original_backend

class DisabledBackend:
    def enabled(self):
        return False
    def load_family_activities(self, family_group_id=None, status=None, limit=100):
        return None
    def save_family_activity(self, activity):
        return None
    def save_family_activity_participant(self, activity_id, participant):
        return None

with tempfile.TemporaryDirectory() as d:
    server.FAMILY_ACTIVITIES_PATH = str(Path(d) / "family_activities.json")
    try:
        server.data_backend = lambda: DisabledBackend()
        saved = server.family_activity_response({"action": "save", "activity": {"id": "local-act-1", "title": "Local walk", "type": "walk", "familyGroupId": "family-1"}})
        assert saved["backend"] == "json"
        participant = server.family_activity_response({"action": "participant", "activityId": "local-act-1", "participant": {"personId": "person-1", "status": "accepted"}})
        assert participant["backend"] == "json"
        listed = server.family_activity_response({"action": "list", "familyGroupId": "family-1"})
        assert listed["activities"][0]["participants"][0]["status"] == "accepted"
    finally:
        server.data_backend = original_backend
print("family activity cloud bridge OK")
'@
Pass "Family activities can use Supabase while preserving JSON fallback"

Step "Wellbeing cloud bridge contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

class FakeWellbeingBackend:
    def enabled(self):
        return True
    def load_wellbeing_signals(self, person_id=None, limit=200):
        assert person_id in (None, "person-1")
        return [{
            "id": "wellbeing-signal-1",
            "personId": "person-1",
            "date": "2026-07-07",
            "modality": "manual",
            "signalType": "mood",
            "source": "self-report",
            "mood": "穩定",
            "moodKey": "steady",
            "moodColor": {"hex": "#3AA8A0"},
            "level": 4,
            "levelLabel": "穩定",
            "confidence": 1.0,
            "isMedicalInference": False,
            "createdAt": "2026-07-07T00:00:00Z",
        }]
    def append_wellbeing_signal(self, signal):
        assert signal["personId"] == "person-1"
        assert signal["mood"] == "開心"
        return {**signal, "id": "wellbeing-signal-2", "backend": "supabase"}

original_backend = server.data_backend
try:
    server.data_backend = lambda: FakeWellbeingBackend()
    recent = server.wellbeing_recent_response({"personId": "person-1"})
    assert recent["ok"] is True
    assert recent["signals"][0]["mood"] == "穩定"
    saved = server.wellbeing_log_response({"personId": "person-1", "mood": "開心", "moodKey": "happy", "level": 5})
    assert saved["ok"] is True
    assert saved["signal"]["backend"] == "supabase"
    assert saved["signal"]["mood"] == "開心"
finally:
    server.data_backend = original_backend

class DisabledBackend:
    def enabled(self):
        return False
    def load_wellbeing_signals(self, person_id=None, limit=200):
        return None
    def append_wellbeing_signal(self, signal):
        return None

with tempfile.TemporaryDirectory() as d:
    server.WELLBEING_PATH = str(Path(d) / "wellbeing_signals.json")
    try:
        server.data_backend = lambda: DisabledBackend()
        saved = server.wellbeing_log_response({"personId": "person-1", "mood": "平穩", "moodKey": "steady", "level": 4})
        assert saved["signal"]["mood"] == "平穩"
        recent = server.wellbeing_recent_response({"personId": "person-1"})
        assert recent["signals"][0]["mood"] == "平穩"
    finally:
        server.data_backend = original_backend
print("wellbeing cloud bridge OK")
'@
Pass "Wellbeing can use Supabase while preserving JSON fallback"

Step "Feedback and NPS admin contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

with tempfile.TemporaryDirectory() as d:
    server.FEEDBACK_PATH = str(Path(d) / "feedback_store.json")
    bug = server.feedback_response({
        "type": "bug",
        "category": "voice",
        "text": "Voice stopped after one turn.",
        "appVersion": "1.2.9",
        "plan": "plus",
    })
    assert bug["ok"] is True
    promoter = server.feedback_response({"type": "nps", "score": 10, "text": "Very useful"})
    detractor = server.feedback_response({"type": "nps", "score": 4, "text": "Needs work"})
    assert promoter["ok"] is True
    assert detractor["ok"] is True
    bad = server.feedback_response({"type": "unknown"})
    assert bad["ok"] is False
    summary = server.admin_feedback_summary({"limit": 10})
    assert summary["ok"] is True
    assert summary["totals"]["bug"] == 1
    assert summary["totals"]["nps"] == 2
    assert summary["byCategory"]["voice"] == 1
    assert summary["nps"] == 0
    assert summary["npsCount"] == 2
    assert len(summary["latest"]) == 3
    only_nps = server.admin_feedback_summary({"type": "nps", "limit": 5})
    assert len(only_nps["latest"]) == 2
print("feedback admin OK")
'@
Pass "Feedback inbox and NPS summary contracts are valid"

Step "AI service brain and memory contract"
Invoke-PythonBlock @'
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
assert status["brains"]["butler"]["model"] == "claude-sonnet-5"
assert status["brains"]["guardian"]["model"] == "claude-sonnet-5"
assert status["personaLayer"]["isFourthBrain"] is False
assert status["personaLayer"]["templateCount"] == 6
assert "persona-context" in status["contracts"]
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
assert model_router.template_id_for_backend_char("\u963f\u5b8f") == "companion-real-male"
warm_persona = model_router.persona_context_response({
    "companionProfile": {"templateId": "nening-real-female", "displayName": "\u5c0f\u6674"},
    "text": "Can we talk about travel today?",
    "relationshipState": {
        "rapportLevel": "trusted",
        "toneOverrides": {"reduceHumor": True, "speechFirst": True},
        "relationshipMemory": {"lastTopicDomains": ["travel"]},
    },
})
steady_persona = model_router.persona_context_response({
    "companionProfile": {"templateId": "companion-real-male", "displayName": "\u963f\u5b8f"},
    "text": "Can we talk about travel today?",
})
assert warm_persona["ok"] is True
assert steady_persona["ok"] is True
assert warm_persona["displayName"] == "\u5c0f\u6674"
assert warm_persona["persona"]["personaArchetype"] != steady_persona["persona"]["personaArchetype"]
assert warm_persona["persona"]["toneProfile"] != steady_persona["persona"]["toneProfile"]
assert warm_persona["composition"]["sameFactsDifferentVoice"] is True
assert warm_persona["composition"]["personaOverridesSafety"] is False
assert warm_persona["composition"]["relationshipStateAffectsDelivery"] is True
assert warm_persona["relationshipState"]["rapportLevel"] == "trusted"
assert warm_persona["relationshipState"]["relationshipMemory"]["lastTopicDomains"] == ["travel"]
assert warm_persona["safety"]["reduceHumor"] is True

with tempfile.TemporaryDirectory() as d:
    server.APP_PROFILE_STORE_PATH = str(Path(d) / "app_profile_store.json")
    server.COMPANION_PROFILE_PATH = str(Path(d) / "companion_profile.json")
    server.MEMORY_ITEMS_PATH = str(Path(d) / "memory_items.json")
    server.CONVERSATION_SUMMARIES_PATH = str(Path(d) / "conversation_summaries.json")
    server.PERCEPTION_SNAPSHOTS_PATH = str(Path(d) / "perception_snapshots.json")
    server.PRODUCT_EVENTS_PATH = str(Path(d) / "product_events.json")
    server.RELATIONSHIP_STATES_PATH = str(Path(d) / "companion_relationship_states.json")
    voice_session = server.voice_session({
        "char": "\u963f\u5b8f",
        "companionProfile": {"templateId": "companion-real-male", "displayName": "\u963f\u5b8f"},
    })
    assert voice_session["ok"] is True
    assert voice_session["aiContext"]["personaLayer"]["templateId"] == "companion-real-male"
    assert voice_session["sessionContext"]["visibleTranscriptDefault"] is False
    extracted = server.memory_extract_response({
        "action": "store",
        "text": "I like Korean dramas on Netflix and often talk with my daughter Mei-Hua. Recently I feel lonely.",
    })
    assert extracted["ok"] is True
    assert extracted["stored"] >= 2
    types = {item["type"] for item in extracted["memoryItems"]}
    assert "preference" in types
    assert "relationship" in types
    zh_extracted = server.memory_extract_response({
        "action": "store",
        "text": "\u6211\u559c\u6b61\u770b\u97d3\u5287\uff0c\u5973\u5152\u7f8e\u83ef\u5e38\u5e38\u4f86\u627e\u6211\u804a\u5929\u3002\u6211\u6bcf\u5929\u6563\u6b65\uff0c\u6700\u8fd1\u819d\u84cb\u75db\uff0c\u665a\u4e0a\u7761\u4e0d\u8457\uff0c\u6709\u9ede\u5b64\u55ae\u3002",
    })
    assert zh_extracted["ok"] is True
    zh_types = {item["type"] for item in zh_extracted["memoryItems"]}
    assert "preference" in zh_types
    assert "relationship" in zh_types
    assert "routine" in zh_types
    assert "emotion" in zh_types
    assert "health_context" in zh_types
    retrieved = server.memory_retrieve_response({"query": "Korean drama Netflix daughter", "limit": 5})
    assert retrieved["ok"] is True
    assert retrieved["count"] >= 1
    missing_summary = server.conversation_summary_response({"action": "save", "history": [{"role": "user", "text": "raw turn"}]})
    assert missing_summary["ok"] is False
    assert missing_summary["error"] == "summary_required"
    saved_conversation_summary = server.conversation_summary_response({
        "action": "save",
        "summary": "User felt lonely and enjoyed discussing Korean dramas; no raw transcript retained.",
        "memoryTags": ["emotion", "video_entertainment"],
        "safetyRelevant": False,
    })
    assert saved_conversation_summary["ok"] is True
    assert saved_conversation_summary["summary"]["privacy"]["storesRawTranscriptByDefault"] is False
    listed_conversation_summaries = server.conversation_summary_response({"action": "list"})
    assert listed_conversation_summaries["count"] == 1
    summary_id = listed_conversation_summaries["summaries"][0]["id"]
    archived_conversation_summary = server.conversation_summary_response({"action": "archive", "summaryId": summary_id})
    assert archived_conversation_summary["ok"] is True
    assert archived_conversation_summary["summary"]["deletedAt"]
    assert server.conversation_summary_response({"action": "list"})["count"] == 0

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
    persona = server.persona_context_response({
        "companionProfile": {"templateId": "munea-2d-xiaoyun", "displayName": "\u6674\u6674"},
        "text": "I feel a little sad today.",
    })
    assert persona["ok"] is True
    assert persona["templateId"] == "munea-2d-xiaoyun"
    assert persona["safety"]["reduceHumor"] is True
    context = server.build_reply_context([
        {"role": "user", "text": "\u6211\u4eca\u5929\u60f3\u804a\u97d3\u5287\uff0c\u4e5f\u6709\u9ede\u5b64\u55ae\u3002"}
    ], "\u963f\u5b8f", {})
    assert context["persona"]["templateId"] == "companion-real-male"
    assert context["guardian"]["risk"]["level"] == "low"
    assert "emotional_distress" in context["guardian"]["risk"]["categories"]
    assert context["guardian"]["risk"]["requiresHumanEscalation"] is False
    assert context["perception"]["needsCurrentFacts"] is True
    instruction = server.reply_context_instruction(context)
    assert "\u89d2\u8272\u4eba\u683c" in instruction
    assert "\u4f7f\u7528\u8005\u8a18\u61b6" in instruction
    post_turn = server.butler_post_turn_response({
        "history": [
            {"role": "user", "text": "I like Korean dramas on Netflix and recently feel lonely."},
            {"role": "model", "text": "I am here with you."},
        ],
        "char": "\u963f\u5b8f",
        "companionProfile": {"templateId": "companion-real-male", "displayName": "\u963f\u5b8f"},
        "analyticsExcluded": True,
    })
    assert post_turn["ok"] is True
    assert post_turn["brain"] == "butler"
    assert post_turn["relationshipState"]["personaTemplateId"] == "companion-real-male"
    assert post_turn["privacy"]["storesRawTranscriptByDefault"] is False
    assert post_turn["conversationSummary"]["created"] is True
    assert post_turn["conversationSummary"]["summary"]["privacy"]["storesRawTranscriptByDefault"] is False
    post_turn_summary_id = post_turn["conversationSummary"]["summary"]["id"]
    assert post_turn["memory"]["sourceConversationSummaryId"] == post_turn_summary_id
    linked_memories = [item for item in server.load_memory_items(limit=20) if item.get("sourceConversationSummaryId") == post_turn_summary_id]
    assert linked_memories
    assert server.conversation_summary_response({"action": "list"})["count"] >= 1
    stored_relationships = server.load_relationship_states({"templateId": "companion-real-male"}, limit=5)
    assert stored_relationships[0]["personaTemplateId"] == "companion-real-male"
    next_persona = server.persona_context_response({
        "companionProfile": {"templateId": "companion-real-male", "displayName": "\u963f\u5b8f"},
        "text": "Can you remember how we talked last time?",
    })
    assert next_persona["relationshipState"]["personaTemplateId"] == "companion-real-male"
    assert next_persona["relationshipState"]["rapportLevel"] in {"familiar", "trusted", "close"}
    assert next_persona["relationshipState"]["relationshipMemory"]["lastMeaningfulTurnCount"] >= 1
    next_context = server.build_reply_context([
        {"role": "user", "text": "Can you remember our Korean drama chat?"}
    ], "\u963f\u5b8f", {})
    assert next_context["persona"]["relationshipState"]["personaTemplateId"] == "companion-real-male"
    assert next_context["persona"]["relationshipState"]["relationshipMemory"]["storedMemoryCount"] >= 1
    assert next_context["persona"]["composition"]["relationshipStateAffectsDelivery"] is True
    assert next_context["persona"]["safety"]["reduceHumor"] is True
    assert next_context["persona"]["voice"]["visibleTranscriptDefault"] is False
    assert next_context["persona"]["relationshipState"]["rapportLevel"] in {"familiar", "trusted", "close"}

print("ai service OK")
'@
Pass "AI service router, memory, and Guardian contracts are valid"

Step "Auth token verification contract"
Invoke-PythonBlock @'
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
os.environ["MUNEA_REQUIRE_AUTH"] = "1"
assert server.auth_required_for_path("/chat") is True
user_scoped_paths = [
    "/open",
    "/chat",
    "/voice-session",
    "/voice-note",
    "/avatar-session",
    "/product-event",
    "/ai/brain-status",
    "/persona/context",
    "/memory/extract",
    "/memory/retrieve",
    "/conversation-summary",
    "/butler/post-turn",
    "/guardian/evaluate",
    "/perception/snapshot",
    "/feedback",
    "/companion-profile",
    "/app-profile",
    "/entitlements",
    "/credits/balance",
    "/privacy-export",
    "/account-deletion",
]
for path in user_scoped_paths:
    assert server.auth_required_for_request(path, {}) is True, path
    missing = server.require_verified_auth({}, path, {})
    assert missing["ok"] is False, path
    assert missing["code"] == "auth_token_missing", path
    verified = server.require_verified_auth({"Authorization": "Bearer " + dev_token}, path, {})
    assert verified["ok"] is True, path
    assert verified["required"] is True, path
for path in ["/auth-status", "/account-bootstrap", "/admin/accounts", "/admin/north-star", "/admin/usage", "/admin/credits", "/admin/conversation-summaries", "/admin/privacy-requests", "/admin/feedback", "/admin/safety-events", "/admin/audit-events"]:
    assert server.auth_required_for_path(path) is False, path
    assert server.require_verified_auth({}, path, {})["ok"] is True, path
assert server.auth_required_for_request("/credits/grant", {}) is False
assert server.auth_required_for_request("/credits/consume", {}) is False
assert server.auth_required_for_request("/subscription-event", {}) is False
assert server.auth_required_for_request("/entitlements", {"action": "load"}) is True
assert server.auth_required_for_request("/entitlements", {"action": "save"}) is False
missing_gate = server.require_verified_auth({}, "/chat")
assert missing_gate["ok"] is False
assert missing_gate["code"] == "auth_token_missing"
verified_gate = server.require_verified_auth({"Authorization": "Bearer " + dev_token}, "/chat")
assert verified_gate["ok"] is True
assert verified_gate["required"] is True
assert server.auth_required_for_path("/auth-status") is False
assert server.auth_required_for_path("/admin/usage") is False
assert server.privileged_billing_write_authorized({}) == (False, "admin_token_not_configured")
os.environ["MUNEA_ADMIN_API_TOKEN"] = "admin-smoke-token"
assert server.privileged_billing_write_authorized({"Authorization": "Bearer " + dev_token}) == (False, "invalid_admin_token")
assert server.privileged_billing_write_authorized({"X-Munea-Admin-Token": "admin-smoke-token"}) == (True, None)
assert server.privileged_billing_write_authorized({"X-Munea-Admin-Token": "wrong"}) == (False, "invalid_admin_token")
del os.environ["MUNEA_ADMIN_API_TOKEN"]
os.environ["MUNEA_PROVIDER_WEBHOOK_TOKEN"] = "provider-smoke-token"
assert server.privileged_billing_write_authorized({"X-Munea-Provider-Token": "provider-smoke-token"}, allow_provider=True) == (True, None)
assert server.privileged_billing_write_authorized({"X-Munea-Provider-Token": "wrong"}, allow_provider=True) == (False, "invalid_provider_token")
del os.environ["MUNEA_PROVIDER_WEBHOOK_TOKEN"]
del os.environ["MUNEA_REQUIRE_AUTH"]
del os.environ["MUNEA_ENABLE_DEV_AUTH_BYPASS"]

os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "public-test-key"
missing_remote = server.verify_auth_context({"Authorization": "Bearer fake-token"})
assert missing_remote["ok"] is False
assert missing_remote["code"] in {"invalid_auth_token", "auth_verification_unavailable"}
del os.environ["SUPABASE_URL"]
del os.environ["SUPABASE_ANON_KEY"]
print("auth verification OK")
'@
Pass "Auth token verification contract is valid"

Step "Atomic JSON store writes"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

with tempfile.TemporaryDirectory() as d:
    path = Path(d) / "store.json"
    server.write_json_file(str(path), {"ok": True, "items": [1, 2, 3]})
    loaded = server.read_json_file(str(path), {})
    assert loaded["ok"] is True
    assert loaded["items"] == [1, 2, 3]
    leftovers = list(Path(d).glob("store.json.tmp.*"))
    assert leftovers == []
print("atomic json write OK")
'@
Pass "JSON fallback stores write atomically"

Step "Product event and North Star contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

with tempfile.TemporaryDirectory() as d:
    server.PRODUCT_EVENTS_PATH = str(Path(d) / "product_events.json")
    server.AUDIT_EVENTS_STORE_PATH = str(Path(d) / "audit_events_store.json")
    server.CONVERSATION_SUMMARIES_PATH = str(Path(d) / "conversation_summaries.json")
    server.PRIVACY_REQUESTS_PATH = str(Path(d) / "privacy_requests.json")
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
    usage = server.admin_usage_summary({"days": 7})
    assert usage["ok"] is True
    assert usage["totals"]["excludedEvents"] == 1
    assert usage["totals"]["voiceMinutes"] == 1.5
    credits = server.admin_credits_summary({"limit": 10})
    assert credits["ok"] is True
    assert credits["walletSummary"]["currencyCode"] == "MUNEA_CREDIT"
    server.conversation_summary_response({
        "action": "save",
        "summary": "Admin smoke summary about loneliness and Korean dramas.",
        "memoryTags": ["emotion", "video_entertainment"],
        "safetyRelevant": True,
    })
    server.conversation_summary_response({
        "action": "save",
        "summary": "Admin smoke summary about a routine reminder.",
        "memoryTags": ["routine"],
        "safetyRelevant": False,
    })
    conversation_admin = server.admin_conversation_summaries({"limit": 10})
    assert conversation_admin["ok"] is True
    assert conversation_admin["count"] == 2
    assert conversation_admin["totals"]["safetyRelevant"] == 1
    assert conversation_admin["totals"]["rawTranscriptRecords"] == 0
    assert conversation_admin["privacy"]["storesRawTranscriptByDefault"] is False
    assert conversation_admin["topTags"][0]["tag"] in {"emotion", "routine", "video_entertainment"}
    class FakePrivacyExportBackend:
        request_scoped = True
        def enabled(self): return True
        def export_scoped_personal_data(self):
            return {"schemaVersion": 1, "scope": "authenticated_person", "person": {"id": "smoke-person"}}
    with patch.object(server, "data_backend", return_value=FakePrivacyExportBackend()):
        export = server.privacy_export_response({"action": "request", "reason": "export smoke"})
    assert export["status"] == "completed"
    assert export["exportPackage"]["person"]["id"] == "smoke-person"
    server.account_deletion_response({"action": "request", "reason": "delete smoke"})
    privacy_admin = server.admin_privacy_requests_summary({"limit": 10})
    assert privacy_admin["ok"] is True
    assert privacy_admin["count"] == 2
    assert privacy_admin["totals"]["byType"]["export"] == 1
    assert privacy_admin["totals"]["byType"]["account_deletion"] == 1
    assert privacy_admin["totals"]["reauthRequired"] == 1
    assert privacy_admin["totals"]["subscriptionNoticeRequired"] == 1
    assert privacy_admin["privacy"]["rawTranscriptRecords"] == 0
    filtered_privacy_admin = server.admin_privacy_requests_summary({"type": "account_deletion"})
    assert filtered_privacy_admin["count"] == 1
    high_risk = server.guardian_evaluate_response({"text": "I may be having a heart attack"})
    assert high_risk["risk"]["level"] == "high"
    safety_admin = server.admin_safety_events_summary({"days": 7})
    assert safety_admin["ok"] is True
    assert safety_admin["count"] >= 2
    assert safety_admin["totals"]["byRiskLevel"]["high"] == 1
    assert safety_admin["totals"]["requiresHumanEscalation"] == 1
    assert safety_admin["totals"]["summaryReviewRecords"] == 1
    assert safety_admin["totals"]["rawTranscriptRecords"] == 0
    assert safety_admin["privacy"]["storesRawTranscriptByDefault"] is False
    filtered_safety_admin = server.admin_safety_events_summary({"level": "high"})
    assert filtered_safety_admin["count"] == 1
    audit = server.append_audit_event({
        "eventType": "credits_granted",
        "targetTable": "credit_transactions",
        "details": {"actorType": "admin", "amount": 1},
    })
    assert audit["eventType"] == "credits_granted"
    audit_store = server.read_json_file(server.AUDIT_EVENTS_STORE_PATH, {})
    assert audit_store["events"][0]["eventType"] == "credits_granted"
    audit_admin = server.admin_audit_events_summary({"limit": 10})
    assert audit_admin["ok"] is True
    assert audit_admin["count"] == 1
    assert audit_admin["totals"]["byEventType"]["credits_granted"] == 1
    assert audit_admin["totals"]["byActorType"]["admin"] == 1
    assert audit_admin["totals"]["byTargetTable"]["credit_transactions"] == 1
    assert audit_admin["privacy"]["rawTranscriptRecords"] == 0
    filtered_audit_admin = server.admin_audit_events_summary({"eventType": "credits_granted"})
    assert filtered_audit_admin["count"] == 1
    ok, code = server.admin_authorized({})
    assert ok is False
    assert code == "admin_token_not_configured"
    os.environ["MUNEA_ADMIN_API_TOKEN"] = "admin-smoke-token"
    ok, code = server.admin_authorized({"X-Munea-Admin-Token": "admin-smoke-token"})
    assert ok is True
    assert code is None
    del os.environ["MUNEA_ADMIN_API_TOKEN"]
print("north star OK")
'@
Pass "Product events produce North Star summary and admin gate is closed by default"

Step "Environment loader and Supabase doctor contract"
Invoke-PythonBlock @'
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
'@

$doctorJson = & $Python (Join-Path $root "scripts/supabase_doctor.py") --allow-missing --json | ConvertFrom-Json
if (-not $doctorJson.tables -or $doctorJson.tables.Count -lt 5) { throw "Supabase doctor missing table status" }
if ($doctorJson.tables -notcontains "family_state_entries") { throw "Supabase doctor missing 007 family table status" }
if ($null -eq $doctorJson.tableChecks) { throw "Supabase doctor missing live table check contract" }
if ($doctorJson.hasServiceRoleKey -and ($doctorJson | ConvertTo-Json -Compress) -match "secret-test-key") { throw "Supabase doctor leaked service key" }
Pass "Environment loader and Supabase doctor are safe"

& $Python -B (Join-Path $root "scripts/test_supabase_doctor.py")
if ($LASTEXITCODE -ne 0) {
  throw "Supabase doctor contract tests failed with exit code $LASTEXITCODE"
}
Pass "Supabase doctor error classification contract"

Step "Billing and entitlement contract"
Invoke-PythonBlock @'
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("GEMINI_API_KEY", "smoke-test-key")
sys.path.insert(0, "engine")
import server

billing = server.entitlements_response({"action": "load"})
assert billing["ok"] is True
assert billing["entitlements"]["voiceCompanion"] is True
assert billing["billing"]["serverVerificationRequired"] is True

normalized = server.normalize_billing_store({
    "activePlan": "pro",
    "subscription": {"status": "active", "productId": "net.munea.app.pro.monthly"},
    "entitlements": {"realtimeAvatar": True, "premiumAvatarMinutesMonthly": 120},
})
assert normalized["activePlan"] == "pro"
assert normalized["subscription"]["status"] == "active"
assert normalized["entitlements"]["realtimeAvatar"] is True
original_load = server.load_billing_store
fallback_store = server.normalize_billing_store({
    "activePlan": "free",
    "subscription": {"status": "inactive"},
    "entitlements": {"realtimeAvatar": False, "premiumAvatarMinutesMonthly": 0},
})
server.load_billing_store = lambda: fallback_store
fallback = server.avatar_session_response({"mode": "liveavatar", "estimatedDurationMs": 60000})
server.load_billing_store = original_load
assert fallback["ok"] is True
assert fallback["session"]["requestedMode"] == "liveavatar"
assert fallback["session"]["selectedMode"] == "2d-viseme"
assert fallback["session"]["fallbackReason"] == "premium_avatar_not_entitled"

original_save = server.save_billing_store
original_credits_path = server.CREDITS_STORE_PATH
with tempfile.TemporaryDirectory() as d:
    server.CREDITS_STORE_PATH = str(Path(d) / "credits_store.json")
    server.load_billing_store = lambda: server.default_billing_store()
    fallback = server.avatar_session_response({"mode": "liveavatar", "estimatedDurationMs": 60000})
    assert fallback["ok"] is True
    assert fallback["session"]["requestedMode"] == "liveavatar"
    assert fallback["session"]["selectedMode"] == "2d-viseme"
    assert fallback["session"]["fallbackReason"] == "premium_avatar_minutes_and_credits_exhausted"
server.CREDITS_STORE_PATH = original_credits_path
server.load_billing_store = original_load

premium_store = server.normalize_billing_store({
    "activePlan": "pro",
    "subscription": {"status": "active", "productId": "net.munea.app.pro.monthly"},
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
with tempfile.TemporaryDirectory() as d:
    original_credits_path = server.CREDITS_STORE_PATH
    server.CREDITS_STORE_PATH = str(Path(d) / "credits_store.json")
    premium_store.update(server.normalize_billing_store({
        "activePlan": "pro",
        "subscription": {"status": "active", "productId": "net.munea.app.pro.monthly"},
        "entitlements": {"realtimeAvatar": True, "premiumAvatarMinutesMonthly": 120},
        "usageLedger": {"period": "2026-06", "avatarMinutesUsed": 119},
    }))
    grant_avatar_credits = server.credits_grant_response({
        "amount": 3,
        "walletType": "purchased",
        "source": "promo",
        "idempotencyKey": "smoke-avatar-credit-grant",
    })
    assert grant_avatar_credits["ok"] is True
    overage = server.avatar_session_response({
        "action": "complete",
        "mode": "ditto",
        "durationMs": 120000,
        "sessionId": "smoke-avatar-overage-session",
    })
    assert overage["session"]["selectedMode"] == "ditto"
    assert overage["session"]["usageCommitted"] is True
    assert overage["session"]["creditsRequired"] == 1
    assert overage["session"]["creditsConsumed"]["ok"] is True
    assert overage["session"]["creditsConsumed"]["walletSummary"]["purchased"] == 2
    assert overage["usageLedger"]["avatarMinutesUsed"] == 121
    server.CREDITS_STORE_PATH = original_credits_path
server.load_billing_store = original_load
server.save_billing_store = original_save

with tempfile.TemporaryDirectory() as d:
    original_credits_path = server.CREDITS_STORE_PATH
    server.CREDITS_STORE_PATH = str(Path(d) / "credits_store.json")
    balance = server.credits_balance_response({})
    assert balance["ok"] is True
    assert balance["walletSummary"]["total"] == 0

    grant_included = server.credits_grant_response({
        "amount": 10,
        "walletType": "included_monthly",
        "source": "included_monthly",
        "reason": "smoke included grant",
        "idempotencyKey": "smoke-grant-included-1",
    })
    assert grant_included["ok"] is True
    assert grant_included["walletSummary"]["includedMonthly"] == 10

    grant_purchased = server.credits_grant_response({
        "amount": 5,
        "walletType": "purchased",
        "source": "promo",
        "reason": "smoke purchased grant",
        "idempotencyKey": "smoke-grant-purchased-1",
    })
    assert grant_purchased["ok"] is True
    assert grant_purchased["walletSummary"]["total"] == 15
    replay = server.credits_grant_response({
        "amount": 5,
        "walletType": "purchased",
        "source": "promo",
        "idempotencyKey": "smoke-grant-purchased-1",
    })
    assert replay["ok"] is True
    assert replay["idempotentReplay"] is True
    assert replay["walletSummary"]["total"] == 15

    consume = server.credits_consume_response({
        "amount": 12,
        "feature": "premium_avatar",
        "reason": "smoke avatar consume",
        "idempotencyKey": "smoke-consume-avatar-1",
    })
    assert consume["ok"] is True
    assert consume["walletSummary"]["includedMonthly"] == 0
    assert consume["walletSummary"]["purchased"] == 3
    consume_replay = server.credits_consume_response({
        "amount": 12,
        "feature": "premium_avatar",
        "idempotencyKey": "smoke-consume-avatar-1",
    })
    assert consume_replay["ok"] is True
    assert consume_replay["idempotentReplay"] is True
    assert consume_replay["walletSummary"]["purchased"] == 3

    insufficient = server.credits_consume_response({
        "amount": 99,
        "feature": "premium_avatar",
        "fallbackMode": "2d-viseme",
        "idempotencyKey": "smoke-consume-avatar-too-much",
    })
    assert insufficient["ok"] is False
    assert insufficient["error"]["code"] == "insufficient_credits"
    assert insufficient["fallbackMode"] == "2d-viseme"
    server.CREDITS_STORE_PATH = original_credits_path
print("billing plan", normalized["activePlan"])
'@
Pass "Billing entitlements and avatar session gates normalize correctly"

Step "Supabase schema contract"
Invoke-PythonBlock @'
from pathlib import Path

sql = Path("supabase/sql/001_initial_munea_schema.sql").read_text(encoding="utf-8").lower()
seed = Path("supabase/sql/002_demo_bootstrap.sql").read_text(encoding="utf-8").lower()
analytics = Path("supabase/sql/003_analytics_admin_foundation.sql").read_text(encoding="utf-8").lower()
ai_memory = Path("supabase/sql/004_ai_memory_service_foundation.sql").read_text(encoding="utf-8").lower()
persona_layer = Path("supabase/sql/005_companion_persona_layer.sql").read_text(encoding="utf-8").lower()
billing_credits = Path("supabase/sql/006_billing_credits_foundation.sql").read_text(encoding="utf-8").lower()
current_billing = Path("supabase/sql/019_pricing_plus100_pro200.sql").read_text(encoding="utf-8").lower()
family_cloud = Path("supabase/sql/007_family_cloud_state_foundation.sql").read_text(encoding="utf-8").lower()
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
persona_tables = [
    "companion_persona_templates",
    "companion_relationship_states",
]
for table in persona_tables:
    if f"create table if not exists public.{table}" not in persona_layer:
        raise SystemExit("Missing persona table: " + table)
    if f"alter table public.{table} enable row level security" not in persona_layer:
        raise SystemExit("Missing persona RLS: " + table)
for token in ["nening-real-female", "companion-real-male", "munea-2d-xiaoyun", "munea-2d-ayuan", "munea-2d-mimi", "munea-2d-wangcai"]:
    if token not in persona_layer:
        raise SystemExit("Missing persona template seed: " + token)
billing_credit_tables = [
    "entitlement_policy_versions",
    "credit_wallets",
    "credit_transactions",
    "credit_ledger",
]
for table in billing_credit_tables:
    if f"create table if not exists public.{table}" not in billing_credits:
        raise SystemExit("Missing billing credits table: " + table)
    if f"alter table public.{table} enable row level security" not in billing_credits:
        raise SystemExit("Missing billing credits RLS: " + table)
    if f"revoke all on public.{table} from anon" not in billing_credits:
        raise SystemExit("Missing billing credits anon revoke: " + table)
for token in [
    "plan_order text[]",
    "included_monthly",
    "purchased",
    "idempotency_key",
    "munea_app_store_v1",
    "refund_reversal",
]:
    if token not in billing_credits:
        raise SystemExit("Missing billing credits schema token: " + token)
for token in [
    "array['free', 'plus', 'pro']",
    '"monthlypoints": 100',
    '"monthlypoints": 200',
    '"familymembersmax": 12',
]:
    if token not in current_billing:
        raise SystemExit("Missing current billing policy token: " + token)
family_cloud_tables = [
    "family_invitations",
    "consent_records",
    "wellbeing_signals",
    "family_state_entries",
    "family_activities",
    "family_activity_participants",
]
for table in family_cloud_tables:
    if f"create table if not exists public.{table}" not in family_cloud:
        raise SystemExit("Missing family cloud table: " + table)
    if f"alter table public.{table} enable row level security" not in family_cloud:
        raise SystemExit("Missing family cloud RLS: " + table)
    if f"revoke all on public.{table} from anon" not in family_cloud:
        raise SystemExit("Missing family cloud anon revoke: " + table)
for token in [
    "auth_user_id",
    "region_code",
    "token_hash",
    "short_code",
    "elder_assisted",
    "'familyFeed'",
    "'wallet'",
]:
    if token.lower() not in family_cloud:
        raise SystemExit("Missing family cloud schema token: " + token)
if "weekly meaningful companion days" not in Path("docs/BACKEND-ARCHITECTURE-v1.md").read_text(encoding="utf-8").lower():
    raise SystemExit("Backend architecture missing North Star definition")
print("supabase tables", len(required_tables) + len(analytics_tables) + len(ai_memory_tables) + len(persona_tables) + len(billing_credit_tables) + len(family_cloud_tables))
'@
Pass "Supabase schema, analytics foundation, RLS, grants, and seed ids are present"

Step "Secret boundary contract"
Invoke-PythonBlock @'
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
'@
Pass "Service role references are not in web assets"

Step "Backend architecture document contract"
Invoke-PythonBlock @'
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
'@
Pass "Backend architecture document covers required sections"

Step "Auth onboarding architecture document contract"
Invoke-PythonBlock @'
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
'@
Pass "Auth onboarding architecture is documented"

Step "Billing credits entitlement document contract"
Invoke-PythonBlock @'
from pathlib import Path

doc = Path("docs/BILLING-CREDITS-ENTITLEMENT-v1.md").read_text(encoding="utf-8").lower()
readme = Path("README.md").read_text(encoding="utf-8").lower()
app_store = Path("docs/APP-STORE-PRODUCTION-READINESS.md").read_text(encoding="utf-8").lower()
current_plan = Path("docs/CURRENT-DEVELOPMENT-PLAN.md").read_text(encoding="utf-8").lower()
required = [
    "free -> plus -> pro",
    "munea free",
    "munea plus",
    "munea pro",
    "subscription = base access and trust",
    "credits = metered voice + avatar capacity",
    "purchase contract",
    "credits",
    "entitlement",
    "deduction order",
    "credit_wallets",
    "credit_ledger",
    "credit_transactions",
    "entitlement_policy_versions",
    "006_billing_credits_foundation.sql",
    "013_current_app_billing_policy.sql",
]
missing = [token for token in required if token not in doc]
if missing:
    raise SystemExit("Billing credits entitlement doc missing: " + ", ".join(missing))
for token in ["free / plus / pro", "billing-credits-entitlement-v1.md"]:
    if token not in readme:
        raise SystemExit("README missing billing plan pointer: " + token)
    if token not in current_plan:
        raise SystemExit("Current development plan missing billing plan pointer: " + token)
for token in ["free / plus / pro", "billing-credits-entitlement-v1.md"]:
    if token not in app_store:
        raise SystemExit("App Store readiness missing billing plan pointer: " + token)
for token in ["006_billing_credits_foundation.sql", "013_current_app_billing_policy.sql", "credit_wallets", "credit_transactions", "idempotent"]:
    if token not in Path("docs/supabase/SETUP.md").read_text(encoding="utf-8").lower():
        raise SystemExit("Supabase setup missing billing credits setup token: " + token)
print("billing credits entitlement OK")
'@
Pass "Billing credits entitlement ladder is documented"

Step "AI service design document contract"
Invoke-PythonBlock @'
from pathlib import Path

doc = Path("docs/AI-SERVICE-DESIGN-v1.md").read_text(encoding="utf-8").lower()
persona_doc = Path("docs/COMPANION-PERSONA-LAYER-v1.md").read_text(encoding="utf-8").lower()
readme = Path("README.md").read_text(encoding="utf-8").lower()
vision_path = next(
    p for p in Path("docs").iterdir()
    if "\u7522\u54c1\u9060\u666f" in p.name and "\u6838\u5fc3\u76ee\u6a19" in p.name
)
vision = vision_path.read_text(encoding="utf-8")
setup = Path("docs/supabase/SETUP.md").read_text(encoding="utf-8").lower()
required = [
    "reflex brain",
    "butler brain",
    "guardian brain",
    "companion persona layer",
    "final reply",
    "persona + memory + perception",
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
for token in ["companion persona layer", "six companions", "samefactsdifferentvoice", "companion_relationship_states"]:
    if token not in persona_doc:
        raise SystemExit("Companion persona design missing: " + token)
for token in ["companion-persona-layer-v1.md", "reply = persona + memory + perception"]:
    if token not in readme:
        raise SystemExit("README missing persona pointer: " + token)
for token in ["\u89d2\u8272\u4eba\u683c", "\u4f7f\u7528\u8005\u8a18\u61b6", "\u5373\u6642\u611f\u77e5", "\u5b89\u5168\u898f\u5247", "\u8a9e\u97f3\u8868\u9054\u9650\u5236"]:
    if token not in vision:
        raise SystemExit("Product vision missing reply formula token: " + token)
for token in ["005_companion_persona_layer.sql", "companion_persona_templates", "companion_relationship_states"]:
    if token not in setup:
        raise SystemExit("Supabase setup missing persona schema token: " + token)
print("ai service design contract OK")
'@
Pass "AI service design is documented"

Step "Repo-backed Codex skill contract"
Invoke-PythonBlock @'
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
'@
Pass "Repo-backed Codex skills are present and documented"

Step "Privacy data-rights contract"
Invoke-PythonBlock @'
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
assert export["status"] == "available"
assert export["requiresReauth"] is False
assert "exportPackage" not in export
assert "JSON" in export["message"]

deletion = server.account_deletion_response({"action": "status"})
assert deletion["ok"] is True
assert deletion["requiresReauth"] is True
print("privacy status", deletion["status"])
'@
Pass "Privacy export and account deletion contracts are valid"

Step "Backend fallback logging contract"
Invoke-PythonBlock @'
import ast
from pathlib import Path

for path in [Path("engine/server.py"), Path("engine/chat_engine.py")]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    silent_handlers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            silent_handlers.append(node.lineno)
    if silent_handlers:
        raise SystemExit(f"{path} still has silent except/pass handlers at lines: {silent_handlers}")

server = Path("engine/server.py").read_text(encoding="utf-8")
chat_engine = Path("engine/chat_engine.py").read_text(encoding="utf-8")
for token in [
    "log_fallback_exception",
    "load app profile from Supabase",
    "load memory items from Supabase",
    "generate chat reply with",
    "generate TTS audio with",
]:
    if token not in server:
        raise SystemExit("server.py missing fallback logging token: " + token)
for token in [
    "_log_fallback_exception",
    "read user profile",
    "extract long-term memories",
    "update interest weights",
]:
    if token not in chat_engine:
        raise SystemExit("chat_engine.py missing fallback logging token: " + token)
print("fallback logging contract OK")
'@
Pass "Backend fallback failures are logged"

Step "Frontend JavaScript syntax"
foreach ($scriptPath in @(
  "web/src/app.js",
  "web/src/companion-profile.js",
  "web/src/auth.js",
  "web/src/auth-config.example.js",
  "web/src/admin.js"
)) {
  node --check $scriptPath
  if ($LASTEXITCODE -ne 0) {
    throw "JavaScript syntax check failed for $scriptPath with exit code $LASTEXITCODE"
  }
}
Pass "Frontend JavaScript parses"

Step "Frontend AI provider consent contract"
Invoke-PythonBlock @'
from pathlib import Path
index = Path("web/index.html").read_text(encoding="utf-8")
onboarding = Path("web/onboarding.html").read_text(encoding="utf-8")
app = Path("web/src/app.js").read_text(encoding="utf-8")
css = Path("web/src/styles.css").read_text(encoding="utf-8")
privacy = Path("web/privacy.html").read_text(encoding="utf-8")

required_index = [
    "auth-terms",
    "privacy.html",
    "\u8a9e\u97f3",
    "AI",
    "\u5883\u5916",
    "119",
    "1925",
]
missing_index = [token for token in required_index if token not in index]
if missing_index:
    raise SystemExit("Missing in-app AI provider consent disclosure tokens: " + ", ".join(missing_index))

required_onboarding = [
    "aiProviderConsentSetup",
    "munea.aiProviderConsent.v1",
    "2026-07-02-ai-provider-v1",
    "privacy.html",
    "\u8a9e\u97f3",
    "AI",
    "\u5883\u5916",
]
missing_onboarding = [token for token in required_onboarding if token not in onboarding]
if missing_onboarding:
    raise SystemExit("Missing onboarding AI provider consent tokens: " + ", ".join(missing_onboarding))

required_app = [
    "AI_PROVIDER_CONSENT_KEY",
    "AI_PROVIDER_CONSENT_VERSION",
    "readAiProviderConsent",
    "saveAiProviderConsent",
    "setupAiProviderConsentControls",
    "MuneaAiProviderConsent",
    "ai_provider_consent_updated",
]
missing_app = [token for token in required_app if token not in app]
if missing_app:
    raise SystemExit("Missing app AI provider consent controller tokens: " + ", ".join(missing_app))

for token in ["provider-consent-card", "provider-consent-toggle", "provider-privacy-link"]:
    if token not in css:
        raise SystemExit("Missing AI provider consent CSS token: " + token)
for token in ["\u96b1\u79c1\u6b0a\u653f\u7b56", "\u8a9e\u97f3", "AI", "\u5883\u5916", "119", "1925", "\u8cc7\u6599\u532f\u51fa", "\u5e33\u865f\u522a\u9664"]:
    if token not in privacy:
        raise SystemExit("Privacy page missing token: " + token)
for forbidden in ["SERVICE_ROLE", "service_role", "SUPABASE_SERVICE_ROLE_KEY"]:
    if forbidden in privacy or forbidden in index or forbidden in onboarding:
        raise SystemExit("Frontend privacy/consent files must not mention service role secret tokens")
print("frontend AI provider consent OK")
'@
Pass "Frontend AI provider consent is present"

Step "Frontend auth bridge contract"
Invoke-PythonBlock @'
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
    "authDeveloperBtn",
]
missing_auth_ui = [token for token in required_auth_ui if token not in index]
if missing_auth_ui:
    raise SystemExit("Missing auth UI tokens: " + ", ".join(missing_auth_ui))
required_auth = [
    "window.MuneaAuth",
    "signInWithApple",
    "signInWithGoogle",
    "signInAsDeveloper",
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
for token in ["setupAuthControls", "updateAuthUI", "signInWithAuthProvider", "signOutAuth"]:
    if token not in app:
        raise SystemExit("app.js missing auth UI controller: " + token)
for token in ["MUNEA_DEV_CONFIG", "skipOnboarding", "analyticsExcluded", "accountType", "developerMode"]:
    if token not in config and token not in app:
        raise SystemExit("Missing developer mode analytics token: " + token)
for forbidden in ["SERVICE_ROLE", "service_role"]:
    if forbidden in config or forbidden in auth:
        raise SystemExit("Auth browser files must not mention service role secret tokens")
print("frontend auth bridge OK")
'@
Pass "Frontend Auth bridge is present"

Step "Admin console contract"
Invoke-PythonBlock @'
from pathlib import Path
html = Path("web/admin.html").read_text(encoding="utf-8")
js = Path("web/src/admin.js").read_text(encoding="utf-8")
css = Path("web/src/admin.css").read_text(encoding="utf-8")
script = Path("scripts/admin-smoke.ps1").read_text(encoding="utf-8")
package = Path("package.json").read_text(encoding="utf-8")
required_html = [
    "Munea",
    'id="sideNav"',
    'id="pageRoot"',
    'id="chartTip"',
    "src/admin.js",
    "src/admin.css",
]
missing_html = [token for token in required_html if token not in html]
if missing_html:
    raise SystemExit("Admin console missing HTML tokens: " + ", ".join(missing_html))
required_js = [
    "X-Munea-Admin-Token",
    "/admin/accounts",
    "/admin/north-star",
    "/admin/usage",
    "/admin/subscription-metrics",
    "/admin/conversation-summaries",
    "/admin/privacy-requests",
    "/admin/feedback",
    "/admin/safety-events",
    "/admin/audit-events",
    # 2026-07-20 擴充的營運指標接口
    "/admin/credits",
    "/admin/medication-adherence",
    "/admin/family-health",
    "/admin/mood-trend",
    "/admin/bond-depth",
    # 2026-07-21 擴充：成長與黏著（PMF 先行指標）
    "/admin/growth-metrics",
    "Promise.allSettled",
    "munea.admin-data-meta.v1",
    "dataQualityNoticeHTML",
    "metadata_missing",
    "renderOverview",
    "renderUsers",
    "renderSafety",
    "renderSubscription",
    "renderFeedback",
    "renderRecords",
    "renderCarePriority",
    "renderMedication",
    "renderFamilyHealth",
    "renderMoodTrend",
    "renderBondDepth",
    "renderGrowth",
    # 2026-07-20 起「連線設定」頁移除，入口一律走帳密登入門
    "loginGateHTML",
    "showLoginGate",
    "pts-cell",
]
forbidden_js_legacy = [
    "settingsHTML",
    'id="apiBaseUrl"',
    'id="adminToken"',
    "connectPromptHTML",
]
present_legacy = [token for token in forbidden_js_legacy if token in js]
if present_legacy:
    raise SystemExit("Admin console still exposes removed connection-settings UI: " + ", ".join(present_legacy))
missing_js = [token for token in required_js if token not in js]
if missing_js:
    raise SystemExit("Admin console missing JS tokens: " + ", ".join(missing_js))
for forbidden in [
    "MUNEA_ADMIN_API_TOKEN",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SERVICE_ROLE",
    "service_role",
    "admin-smoke-token",
    "provider-smoke-token",
]:
    if forbidden in html or forbidden in js or forbidden in css:
        raise SystemExit("Admin console must not embed secret token marker: " + forbidden)
if "localStorage.setItem(\"adminToken\"" in js or "localStorage.setItem('adminToken'" in js:
    raise SystemExit("Admin console must not persist admin token in localStorage")
for token in ["layout", "side-nav", "kpi-row", "table-wrap", "status-pill", "status-pill.warn", "error-item", "connect-prompt", "login-gate", "@media"]:
    if token not in css:
        raise SystemExit("Admin console CSS missing responsive token: " + token)
for token in ["UseGcloudIdentityToken", "MUNEA_ADMIN_API_URL", "MUNEA_STAGING_ADMIN_TOKEN", "MUNEA_STAGING_APP_KEY", "X-Munea-Key", ".munea-app-key", "/admin.html", "/admin/accounts", "/admin/feedback"]:
    if token not in script:
        raise SystemExit("Admin smoke missing token: " + token)
staging_smoke = Path("scripts/staging-smoke.ps1").read_text(encoding="utf-8")
for token in ["UseGcloudIdentityToken", "X-Serverless-Authorization", "MUNEA_STAGING_APP_KEY", "X-Munea-Key", ".munea-app-key", "/healthz/", "Merge-Headers"]:
    if token not in staging_smoke:
        raise SystemExit("Staging smoke missing Cloud Run token: " + token)
if '"smoke:admin"' not in package:
    raise SystemExit("package.json missing smoke:admin script")
cloudrun_status = Path("scripts/cloud-run-status.ps1").read_text(encoding="utf-8")
for token in ["Readiness", "StrictReadiness", "MUNEA_ADMIN_API_TOKEN", "MUNEA_REQUIRE_AUTH", "/admin.html"]:
    if token not in cloudrun_status:
        raise SystemExit("Cloud Run readiness missing token: " + token)
cloudrun_deploy = Path("scripts/cloud-run-deploy-staging.ps1").read_text(encoding="utf-8")
for token in ["git archive", "DryRun", "update-secrets", "Get-DeploymentValue", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "MUNEA_REQUIRE_AUTH=1", "MUNEA_ENABLE_DEV_AUTH_BYPASS=false", "munea-admin-token-staging"]:
    if token not in cloudrun_deploy:
        raise SystemExit("Cloud Run clean deploy missing token: " + token)
gcloudignore = Path(".gcloudignore").read_text(encoding="utf-8")
for token in ["avatar-candidates-9x16/", "avatar-candidates-9x16-final/", "deploy/cloud-run/"]:
    if token not in gcloudignore:
        raise SystemExit(".gcloudignore missing local draft exclusion: " + token)
if '"cloudrun:readiness"' not in package:
    raise SystemExit("package.json missing cloudrun:readiness script")
if '"cloudrun:deploy:staging"' not in package:
    raise SystemExit("package.json missing cloudrun:deploy:staging script")
auth_smoke = Path("scripts/staging-auth-smoke.ps1").read_text(encoding="utf-8")
for token in ["/auth/v1/admin/users", "grant_type=password", "X-Munea-Key", "/auth-status", "/account-bootstrap", "temporary user deleted"]:
    if token not in auth_smoke:
        raise SystemExit("Live staging auth smoke missing token: " + token)
if '"smoke:staging:auth"' not in package:
    raise SystemExit("package.json missing smoke:staging:auth script")
print("admin console contract OK")
'@
& python engine/test_admin_data_quality.py
if ($LASTEXITCODE -ne 0) {
  throw "Admin data quality contract tests failed with exit code $LASTEXITCODE"
}
& node scripts/test-admin-console.js
if ($LASTEXITCODE -ne 0) {
  throw "Admin console contract tests failed with exit code $LASTEXITCODE"
}
Pass "Admin console is present and keeps secrets out of static assets"

Step "Operational PowerShell script syntax"
foreach ($scriptPath in @("scripts/cloud-run-deploy-staging.ps1", "scripts/staging-auth-smoke.ps1")) {
  $parseTokens = $null
  $parseErrors = $null
  [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $scriptPath),
    [ref]$parseTokens,
    [ref]$parseErrors
  ) | Out-Null
  if ($parseErrors.Count -gt 0) {
    $details = ($parseErrors | ForEach-Object { "line $($_.Extent.StartLineNumber): $($_.Message)" }) -join "; "
    throw "$scriptPath has syntax errors: $details"
  }
}
Pass "Operational PowerShell scripts parse"

Step "Avatar runtime contract"
Invoke-PythonBlock @'
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
'@
Pass "Avatar runtime contract is present"

Step "Frontend avatar asset references"
Invoke-PythonBlock @'
from pathlib import Path
import re

files = [
    Path("web/index.html"),
    Path("web/landing.html"),
    Path("web/onboarding.html"),
    Path("web/src/companion-profile.js"),
    Path("engine/model_router.py"),
]
refs = []
for file_path in files:
    text = file_path.read_text(encoding="utf-8")
    for match in re.finditer(r"avatars/[A-Za-z0-9_.-]+", text):
        refs.append((file_path, match.group(0)))

missing = []
for file_path, ref in refs:
    asset_path = Path("web") / ref
    if not asset_path.exists():
        missing.append(f"{file_path}: {ref}")

if missing:
    raise SystemExit("Missing avatar assets:\n" + "\n".join(missing))
print("avatar asset refs", len(refs))
'@
Pass "Frontend avatar asset references exist"

Step "Voice provider contract"
Invoke-PythonBlock @'
from pathlib import Path
js = Path("web/src/app.js").read_text(encoding="utf-8")
required = [
    "window.MuneaVoiceProvider",
    "VOICE_PROVIDER_MODES",
    "connect(context",
    "sendText({ history, char })",
    "sendVoiceNote({ audio, mime, durationMs, char })",
    "postTurnReview",
    "/butler/post-turn",
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
'@
Pass "Voice provider contract is present"

Step "Frontend AI diagnostics contract"
Invoke-PythonBlock @'
from pathlib import Path
html = Path("web/index.html").read_text(encoding="utf-8")
js = Path("web/src/app.js").read_text(encoding="utf-8")
css = Path("web/src/styles.css").read_text(encoding="utf-8")
required_html = [
    "aiDevPanel",
    "aiDevRefresh",
    "aiDevPersona",
    "aiDevRapport",
    "aiDevGuardian",
    "aiDevMemory",
    "aiDevJson",
]
missing_html = [token for token in required_html if token not in html]
if missing_html:
    raise SystemExit("Missing AI diagnostics UI tokens: " + ", ".join(missing_html))
required_js = [
    "latestAiContext",
    "latestRelationshipState",
    "isAiDevDiagnosticsEnabled",
    "renderAiDiagnostics",
    "refreshAiDiagnostics",
    "setLatestAiContext",
    "/persona/context",
    "relationshipState",
    "toneOverrideKeys",
]
missing_js = [token for token in required_js if token not in js]
if missing_js:
    raise SystemExit("Missing AI diagnostics JS tokens: " + ", ".join(missing_js))
for token in ["ai-dev-panel", "ai-dev-grid", "ai-dev-json"]:
    if token not in css:
        raise SystemExit("Missing AI diagnostics CSS token: " + token)
print("frontend ai diagnostics OK")
'@
Pass "Frontend AI diagnostics are present"

Step "Account bootstrap frontend contract"
Invoke-PythonBlock @'
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
'@
Pass "Frontend onboarding can initialize account bootstrap"

Step "Frontend routine reminder bridge contract"
Invoke-PythonBlock @'
from pathlib import Path
js = Path("web/src/app.js").read_text(encoding="utf-8")
required = [
    "routineRemindersPost",
    "/routine-reminders",
    "refreshRoutineRemindersFromBackend",
    "syncMedicationReminder",
    "syncVisitReminder",
    "archiveRoutineReminder",
    "__muneaRoutineReminderSync",
    "stableReminderId",
    "routine_reminder_completed",
]
missing = [item for item in required if item not in js]
if missing:
    raise SystemExit("Missing frontend routine reminder bridge pieces: " + ", ".join(missing))
if js.count("syncMedicationReminder(") < 3:
    raise SystemExit("Medication reminder sync is not wired into add/chat/update flows")
if js.count("syncVisitReminder(") < 3:
    raise SystemExit("Visit reminder sync is not wired into add/chat/load flows")
print("frontend routine reminder bridge OK")
'@
Pass "Frontend can sync medication and visit reminders to backend"

Step "Frontend id references"
Invoke-PythonBlock @'
from pathlib import Path
import re
html = Path("web/index.html").read_text(encoding="utf-8")
js = Path("web/src/app.js").read_text(encoding="utf-8")
ids = set(re.findall(r'id="([^"]+)"', html))
raw_refs = set(re.findall(r"#([A-Za-z_][\w-]*)", js))
refs = {r for r in raw_refs if r.isascii() and not re.fullmatch(r"[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?(?:[0-9A-Fa-f]{2})?", r)}
allowed = {
    "chat",
    "connect",
    "famDots",
    "greetKicker",
    "historyEntry",
    "med",
    "medCountLabel",
    "medEntryStatus",
    "medTileBtn",
    "moodTrendBtn",
    "npsRow",
    "pillDots",
    "price",
    "reportBtn",
    "save",
    "srcStrip",
    "statPillHint",
    "statPillVal",
    "statusMonth",
    "statusSeg",
    "statusTitle",
    "statusToday",
    "statusWeek",
    "walkDaysVal",
}
missing = sorted([r for r in refs if r not in ids and r not in allowed])
if missing:
    raise SystemExit("Missing id refs: " + ", ".join(missing))
print("index ids", len(ids))
'@
Pass "Frontend id refs are valid"

Step "App Call Control contract"
& $Python "scripts/test_app_call_control_contract.py"
if ($LASTEXITCODE -ne 0) {
  throw "App Call Control contract failed with exit code $LASTEXITCODE"
}
Pass "App Call Control production and development paths are valid"

# Keep these auth-boundary tests in smoke:no-api so PR CI executes them.
Step "Voice chain probe security contract"
& $Python "scripts/test_voice_chain_probe.py"
if ($LASTEXITCODE -ne 0) {
  throw "Voice chain probe security contract failed with exit code $LASTEXITCODE"
}
Pass "Voice chain probe cleanup and credential boundaries are valid"

Step "Gateway HTTP auth surface contract"
& $Python "scripts/test_gateway_http.py"
if ($LASTEXITCODE -ne 0) {
  throw "Gateway HTTP auth surface contract failed with exit code $LASTEXITCODE"
}
Pass "Gateway user health redaction and admin boundaries are valid"

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
if (-not $voice.aiContext.personaLayer.templateId) { throw "/voice-note missing persona aiContext" }
Pass "/voice-note accepts captured audio payloads"

Step "API /voice-session"
$session = Invoke-RestMethod -Uri "$BaseUrl/voice-session" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"char":"\u5be7\u5be7","locale":"zh-TW"}' -TimeoutSec 30
if (-not $session.ok) { throw "/voice-session returned not ok" }
if ($session.provider -ne "stt-chat-tts") { throw "/voice-session provider unexpected: $($session.provider)" }
if (-not $session.capabilities.recordedVoiceNote) { throw "/voice-session missing recorded voice capability" }
if (-not $session.aiContext.personaLayer.templateId) { throw "/voice-session missing persona aiContext" }
if ($session.sessionContext.visibleTranscriptDefault) { throw "/voice-session should not default to transcript UI" }
Pass "/voice-session returns provider capabilities"

Step "API /companion-profile"
$profile = Invoke-RestMethod -Uri "$BaseUrl/companion-profile" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"action":"load"}' -TimeoutSec 30
if (-not $profile.ok) { throw "/companion-profile returned not ok" }
if (-not $profile.profile.templateId) { throw "/companion-profile missing templateId" }
Pass "/companion-profile returns saved companion profile"

Step "API /persona/context"
$personaBody = '{"companionProfile":{"templateId":"nening-real-female","displayName":"Munea"},"text":"I want to talk about today."}'
$persona = Invoke-RestMethod -Uri "$BaseUrl/persona/context" -Method Post -ContentType "application/json; charset=utf-8" -Body $personaBody -TimeoutSec 30
if (-not $persona.ok) { throw "/persona/context returned not ok" }
if ($persona.layer -ne "companion_persona") { throw "/persona/context unexpected layer: $($persona.layer)" }
if ($persona.composition.personaOverridesSafety) { throw "/persona/context persona should not override safety" }
Pass "/persona/context returns companion persona pack"

Step "API /conversation-summary"
$summaryBody = '{"action":"save","summary":"Smoke user enjoyed a short companion check-in; raw transcript is not retained.","memoryTags":["smoke","companion"],"safetyRelevant":false}'
$conversationSummary = Invoke-RestMethod -Uri "$BaseUrl/conversation-summary" -Method Post -ContentType "application/json; charset=utf-8" -Body $summaryBody -TimeoutSec 30
if (-not $conversationSummary.ok) { throw "/conversation-summary returned not ok" }
if ($conversationSummary.privacy.storesRawTranscriptByDefault) { throw "/conversation-summary should not retain raw transcript by default" }
$summaryList = Invoke-RestMethod -Uri "$BaseUrl/conversation-summary" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"action":"list","limit":5}' -TimeoutSec 30
if (-not $summaryList.ok) { throw "/conversation-summary list returned not ok" }
if ($summaryList.count -lt 1) { throw "/conversation-summary list returned no summaries" }
Pass "/conversation-summary stores summary-only conversation memory"

Step "API /butler/post-turn"
$postTurnBody = '{"char":"\u963f\u5b8f","companionProfile":{"templateId":"companion-real-male","displayName":"\u963f\u5b8f"},"analyticsExcluded":true,"history":[{"role":"user","text":"I like Korean dramas and feel lonely recently."},{"role":"model","text":"I am here with you."}]}'
$postTurn = Invoke-RestMethod -Uri "$BaseUrl/butler/post-turn" -Method Post -ContentType "application/json; charset=utf-8" -Body $postTurnBody -TimeoutSec 30
if (-not $postTurn.ok) { throw "/butler/post-turn returned not ok" }
if ($postTurn.brain -ne "butler") { throw "/butler/post-turn unexpected brain: $($postTurn.brain)" }
if ($postTurn.privacy.storesRawTranscriptByDefault) { throw "/butler/post-turn should not store raw transcript by default" }
if ($postTurn.relationshipState.personaTemplateId -ne "companion-real-male") { throw "/butler/post-turn wrong persona template" }
if (-not $postTurn.conversationSummary.created) { throw "/butler/post-turn did not create a conversation summary" }
if ($postTurn.conversationSummary.privacy.storesRawTranscriptByDefault) { throw "/butler/post-turn summary should not retain raw transcript" }
if (-not $postTurn.memory.sourceConversationSummaryId) { throw "/butler/post-turn missing summary linkage on memory" }
Pass "/butler/post-turn stores memory and relationship state"

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

Step "API /credits"
$creditsBalance = Invoke-RestMethod -Uri "$BaseUrl/credits/balance" -Method Post -ContentType "application/json; charset=utf-8" -Body '{}' -TimeoutSec 30
if (-not $creditsBalance.ok) { throw "/credits/balance returned not ok" }
if (-not $creditsBalance.walletSummary.currencyCode) { throw "/credits/balance missing currency" }
$creditGrantBody = '{"amount":1,"walletType":"included_monthly","source":"included_monthly","reason":"api smoke grant","idempotencyKey":"api-smoke-grant-1"}'
$creditGrant = Invoke-RestMethod -Uri "$BaseUrl/credits/grant" -Method Post -ContentType "application/json; charset=utf-8" -Body $creditGrantBody -TimeoutSec 30
if (-not $creditGrant.ok) { throw "/credits/grant returned not ok" }
$creditConsumeBody = '{"amount":1,"feature":"premium_avatar","reason":"api smoke consume","idempotencyKey":"api-smoke-consume-1"}'
$creditConsume = Invoke-RestMethod -Uri "$BaseUrl/credits/consume" -Method Post -ContentType "application/json; charset=utf-8" -Body $creditConsumeBody -TimeoutSec 30
if (-not $creditConsume.ok) { throw "/credits/consume returned not ok" }
Pass "/credits endpoints return wallet contracts"

Step "API /healthz"
$health = Invoke-RestMethod -Uri "$BaseUrl/healthz" -Method Get -TimeoutSec 30
if (-not $health.ok) { throw "/healthz returned not ok" }
if ($health.runtime.concurrency -ne "threading") { throw "/healthz missing threaded runtime marker" }
if ($health.runtime.jsonStoreWrites -ne "atomic") { throw "/healthz missing atomic JSON write marker" }
if ($null -eq $health.runtime.authRequired) { throw "/healthz missing authRequired runtime marker" }
if ($health.contracts -notcontains "auth-status") { throw "/healthz missing auth-status contract" }
if ($health.contracts -notcontains "account-bootstrap") { throw "/healthz missing account-bootstrap contract" }
if ($health.contracts -notcontains "entitlements") { throw "/healthz missing entitlements contract" }
if ($health.contracts -notcontains "credits-balance") { throw "/healthz missing credits-balance contract" }
if ($health.contracts -notcontains "credits-grant") { throw "/healthz missing credits-grant contract" }
if ($health.contracts -notcontains "credits-consume") { throw "/healthz missing credits-consume contract" }
if ($health.contracts -notcontains "avatar-session") { throw "/healthz missing avatar-session contract" }
if ($health.contracts -notcontains "ai-brain-status") { throw "/healthz missing ai-brain-status contract" }
if ($health.contracts -notcontains "persona-context") { throw "/healthz missing persona-context contract" }
if ($health.contracts -notcontains "memory-extract") { throw "/healthz missing memory-extract contract" }
if ($health.contracts -notcontains "memory-retrieve") { throw "/healthz missing memory-retrieve contract" }
if ($health.contracts -notcontains "conversation-summary") { throw "/healthz missing conversation-summary contract" }
if ($health.contracts -notcontains "butler-post-turn") { throw "/healthz missing butler-post-turn contract" }
if ($health.contracts -notcontains "guardian-evaluate") { throw "/healthz missing guardian-evaluate contract" }
if ($health.contracts -notcontains "perception-topic-plan") { throw "/healthz missing perception-topic-plan contract" }
if ($health.contracts -notcontains "perception-snapshot") { throw "/healthz missing perception-snapshot contract" }
if ($health.contracts -notcontains "product-event") { throw "/healthz missing product-event contract" }
if ($health.contracts -notcontains "feedback") { throw "/healthz missing feedback contract" }
if ($health.contracts -notcontains "admin-accounts") { throw "/healthz missing admin-accounts contract" }
if ($health.contracts -notcontains "admin-north-star") { throw "/healthz missing admin-north-star contract" }
if ($health.contracts -notcontains "admin-usage") { throw "/healthz missing admin-usage contract" }
if ($health.contracts -notcontains "admin-credits") { throw "/healthz missing admin-credits contract" }
if ($health.contracts -notcontains "admin-conversation-summaries") { throw "/healthz missing admin-conversation-summaries contract" }
if ($health.contracts -notcontains "admin-privacy-requests") { throw "/healthz missing admin-privacy-requests contract" }
if ($health.contracts -notcontains "admin-feedback") { throw "/healthz missing admin-feedback contract" }
if ($health.contracts -notcontains "admin-safety-events") { throw "/healthz missing admin-safety-events contract" }
if ($health.contracts -notcontains "admin-audit-events") { throw "/healthz missing admin-audit-events contract" }
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

Step "API /admin/accounts gate"
try {
  Invoke-RestMethod -Uri "$BaseUrl/admin/accounts" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"limit":5}' -TimeoutSec 30 | Out-Null
  throw "/admin/accounts should require admin token"
} catch {
  $message = $_.Exception.Message
  if ($message -notmatch "403" -and $message -notmatch "Forbidden") { throw }
}
Pass "/admin/accounts is closed without admin token"

Step "API /admin/north-star gate"
try {
  Invoke-RestMethod -Uri "$BaseUrl/admin/north-star" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"days":7}' -TimeoutSec 30 | Out-Null
  throw "/admin/north-star should require admin token"
} catch {
  $message = $_.Exception.Message
  if ($message -notmatch "403" -and $message -notmatch "Forbidden") { throw }
}
Pass "/admin/north-star is closed without admin token"

Step "API /admin/usage gate"
try {
  Invoke-RestMethod -Uri "$BaseUrl/admin/usage" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"days":7}' -TimeoutSec 30 | Out-Null
  throw "/admin/usage should require admin token"
} catch {
  $message = $_.Exception.Message
  if ($message -notmatch "403" -and $message -notmatch "Forbidden") { throw }
}
Pass "/admin/usage is closed without admin token"

Step "API /admin/credits gate"
try {
  Invoke-RestMethod -Uri "$BaseUrl/admin/credits" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"limit":5}' -TimeoutSec 30 | Out-Null
  throw "/admin/credits should require admin token"
} catch {
  $message = $_.Exception.Message
  if ($message -notmatch "403" -and $message -notmatch "Forbidden") { throw }
}
Pass "/admin/credits is closed without admin token"

Step "API /admin/conversation-summaries gate"
try {
  Invoke-RestMethod -Uri "$BaseUrl/admin/conversation-summaries" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"limit":5}' -TimeoutSec 30 | Out-Null
  throw "/admin/conversation-summaries should require admin token"
} catch {
  $message = $_.Exception.Message
  if ($message -notmatch "403" -and $message -notmatch "Forbidden") { throw }
}
Pass "/admin/conversation-summaries is closed without admin token"

Step "API /admin/privacy-requests gate"
try {
  Invoke-RestMethod -Uri "$BaseUrl/admin/privacy-requests" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"limit":5}' -TimeoutSec 30 | Out-Null
  throw "/admin/privacy-requests should require admin token"
} catch {
  $message = $_.Exception.Message
  if ($message -notmatch "403" -and $message -notmatch "Forbidden") { throw }
}
Pass "/admin/privacy-requests is closed without admin token"

Step "API /admin/safety-events gate"
try {
  Invoke-RestMethod -Uri "$BaseUrl/admin/safety-events" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"days":7}' -TimeoutSec 30 | Out-Null
  throw "/admin/safety-events should require admin token"
} catch {
  $message = $_.Exception.Message
  if ($message -notmatch "403" -and $message -notmatch "Forbidden") { throw }
}
Pass "/admin/safety-events is closed without admin token"

Step "API /admin/audit-events gate"
try {
  Invoke-RestMethod -Uri "$BaseUrl/admin/audit-events" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"limit":5}' -TimeoutSec 30 | Out-Null
  throw "/admin/audit-events should require admin token"
} catch {
  $message = $_.Exception.Message
  if ($message -notmatch "403" -and $message -notmatch "Forbidden") { throw }
}
Pass "/admin/audit-events is closed without admin token"

Step "API /privacy-export"
$privacyExport = Invoke-RestMethod -Uri "$BaseUrl/privacy-export" -Method Post -ContentType "application/json; charset=utf-8" -Body '{"action":"preview"}' -TimeoutSec 30
if (-not $privacyExport.ok) { throw "/privacy-export returned not ok" }
if ($privacyExport.exportPackage) { throw "/privacy-export preview must not return personal data without a scoped identity" }
if ($privacyExport.requiresReauth) { throw "/privacy-export preview should direct signed-in users to immediate delivery" }
if ($privacyExport.status -ne "available") { throw "/privacy-export preview must advertise the available scoped export" }
Pass "/privacy-export preview advertises authenticated, immediate scoped delivery"

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
if (-not $chat.aiContext.personaLayer.templateId) { throw "/chat missing persona aiContext" }
if (-not $chat.aiContext.guardian.riskLevel) { throw "/chat missing guardian aiContext" }
$chatAudioStatus = if ($chat.audio) { " + audio" } else { "" }
Pass ("/chat returned reply" + $chatAudioStatus)

Write-Host ""
Write-Host "Smoke test complete." -ForegroundColor Green
