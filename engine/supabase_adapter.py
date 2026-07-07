"""
Supabase-ready data adapter for Munea.

This module is intentionally stdlib-only for the current prototype. It keeps
Supabase service credentials on the backend side and lets server.py keep a JSON
fallback until the cloud project, auth, and seeded account/person ids are ready.
"""
import json
import os
import re
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request


UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ── 雲端斷路器（跨 adapter 實例共用，因 data_backend() 每次重建 adapter）──
_CIRCUIT = {"open_until": 0.0}
_CIRCUIT_COOLDOWN = 20.0  # 秒：一次連線失敗後，這段時間內直接秒退走本地備份

# ── 缺表短記憶：某表回過 404(缺表) 就記著 30 秒，同批後續呼叫秒退不再白跑往返 ──
# 等 Codex 建好表、TTL 過期會自動重試恢復。
_MISSING_TABLES = {}
_MISSING_TTL = 30.0


def _circuit_open():
    return time.time() < _CIRCUIT["open_until"]


def _trip_circuit():
    _CIRCUIT["open_until"] = time.time() + _CIRCUIT_COOLDOWN


def _reset_circuit():
    _CIRCUIT["open_until"] = 0.0


def _table_known_missing(table):
    until = _MISSING_TABLES.get(table)
    return until is not None and time.time() < until


def _mark_table_missing(table):
    _MISSING_TABLES[table] = time.time() + _MISSING_TTL


class SupabaseAdapter:
    def __init__(self, env=None):
        self.env = env or os.environ
        self.url = (self.env.get("SUPABASE_URL") or "").rstrip("/")
        self.service_key = self.env.get("SUPABASE_SERVICE_ROLE_KEY") or ""
        self.provider = (self.env.get("MUNEA_DATABASE_PROVIDER") or "json").lower()
        self.account_id = self.env.get("MUNEA_SUPABASE_ACCOUNT_ID") or ""
        self.person_id = self.env.get("MUNEA_SUPABASE_PERSON_ID") or ""
        self.family_group_id = self.env.get("MUNEA_SUPABASE_FAMILY_GROUP_ID") or ""

    def enabled(self):
        return (
            self.provider == "supabase"
            and bool(self.url)
            and bool(self.service_key)
            and self._is_uuid(self.account_id)
            and self._is_uuid(self.person_id)
        )

    def status(self):
        missing = []
        if self.provider != "supabase":
            missing.append("MUNEA_DATABASE_PROVIDER=supabase")
        if not self.url:
            missing.append("SUPABASE_URL")
        if not self.service_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if not self._is_uuid(self.account_id):
            missing.append("MUNEA_SUPABASE_ACCOUNT_ID")
        if not self._is_uuid(self.person_id):
            missing.append("MUNEA_SUPABASE_PERSON_ID")
        return {
            "provider": "supabase" if self.provider == "supabase" else "json",
            "enabled": self.enabled(),
            "missing": missing,
            "tables": [
                "accounts",
                "account_members",
                "persons",
                "family_groups",
                "family_memberships",
                "companion_profiles",
                "subscription_ledger",
                "usage_ledger",
                "privacy_requests",
                "product_events",
                "daily_user_metrics",
                "voice_session_metrics",
                "reminder_events",
                "family_interaction_events",
                "cost_ledger",
                "admin_notes",
                "memory_items",
                "perception_snapshots",
                "ai_brain_runs",
                "companion_persona_templates",
                "companion_relationship_states",
                "entitlement_policy_versions",
                "credit_wallets",
                "credit_transactions",
                "credit_ledger",
                "family_invitations",
                "consent_records",
                "wellbeing_signals",
                "family_state_entries",
                "family_activities",
                "family_activity_participants",
            ],
        }

    def check_table(self, table):
        if not self.enabled():
            return False
        select_columns = {
            "companion_persona_templates": "template_id",
            "entitlement_policy_versions": "policy_key",
        }
        column = select_columns.get(table, "id")
        self._request("GET", table, query={"select": column, "limit": "1"})
        return True

    def load_companion_profile(self):
        if not self.enabled():
            return None
        rows = self._select("companion_profiles", {"person_id": f"eq.{self.person_id}", "select": "*", "limit": "1"})
        if not rows:
            return None
        return self.companion_row_to_profile(rows[0])

    def load_app_profile_store(self):
        if not self.enabled():
            return None
        account = self._first("accounts", {"id": f"eq.{self.account_id}", "select": "*"})
        person = self._first("persons", {"id": f"eq.{self.person_id}", "select": "*"})
        family_group = self._load_family_group()
        members = self._load_family_members(family_group["id"] if family_group else None)
        companion = self.load_companion_profile() or {}
        return {
            "schemaVersion": 1,
            "account": {
                "id": self.account_id,
                "locale": (account or {}).get("locale") or "zh-TW",
                "preferredLanguages": (account or {}).get("preferred_languages") or ["zh-TW", "en"],
                "createdAt": (account or {}).get("created_at"),
            },
            "familyGroup": {
                "id": (family_group or {}).get("id") or self.family_group_id or "",
                "name": (family_group or {}).get("name") or "Munea Care Circle",
                "members": members or [self.person_row_to_member(person, role="primary_user")],
            },
            "primaryCareRecipientId": self.person_id,
            "companionProfiles": {
                self.person_id: companion,
            },
            "updatedAt": (account or {}).get("updated_at") or (person or {}).get("updated_at"),
        }

    def save_app_profile_store(self, store):
        if not self.enabled():
            return None
        store = store or {}
        profiles = store.get("companionProfiles") or store.get("companion_profiles") or {}
        active_profile = profiles.get(self.person_id) or store.get("companionProfile") or store.get("companion_profile")
        if active_profile:
            self.save_companion_profile(active_profile)
        return self.load_app_profile_store()

    def save_companion_profile(self, profile):
        if not self.enabled():
            return None
        payload = self.profile_to_companion_row(profile)
        rows = self._request(
            "PATCH",
            "companion_profiles",
            query={"person_id": f"eq.{self.person_id}", "select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        if not rows:
            rows = self._request(
                "POST",
                "companion_profiles",
                query={"select": "*"},
                payload=payload,
                prefer="return=representation",
        )
        return self.companion_row_to_profile(rows[0]) if rows else None

    def bootstrap_account(self, data=None):
        if not self.enabled():
            return None
        data = data or {}
        auth_user_id = data.get("authUserId") or data.get("auth_user_id") or data.get("userId") or data.get("user_id")
        if not self._is_uuid(auth_user_id):
            raise RuntimeError("Supabase account bootstrap requires a verified auth user id")

        existing_member = self._first(
            "account_members",
            {"user_id": f"eq.{auth_user_id}", "status": "eq.active", "select": "*"},
        )
        if existing_member:
            previous_account_id = self.account_id
            previous_person_id = self.person_id
            try:
                self.account_id = existing_member.get("account_id") or self.account_id
                person = self._first("persons", {"account_id": f"eq.{self.account_id}", "is_primary_care_recipient": "eq.true", "select": "*"})
                if person and person.get("id"):
                    self.person_id = person["id"]
                return self.load_app_profile_store()
            finally:
                self.account_id = previous_account_id
                self.person_id = previous_person_id

        account_id = str(uuid.uuid4())
        person_id = str(uuid.uuid4())
        family_group_id = str(uuid.uuid4())
        display_name = (data.get("displayName") or data.get("display_name") or "Munea user").strip()[:80] or "Munea user"
        companion = data.get("companionProfile") or data.get("companion_profile") or {}

        account = self._request(
            "POST",
            "accounts",
            query={"select": "*"},
            payload={
                "id": account_id,
                "name": data.get("accountName") or data.get("account_name") or "Munea account",
                "locale": data.get("locale") or "zh-TW",
                "preferred_languages": data.get("preferredLanguages") or data.get("preferred_languages") or ["zh-TW", "en"],
            },
            prefer="return=representation",
        )[0]
        self._request(
            "POST",
            "account_members",
            query={"select": "*"},
            payload={
                "account_id": account_id,
                "user_id": auth_user_id,
                "role": data.get("role") or "owner",
                "status": "active",
            },
            prefer="return=representation",
        )
        person = self._request(
            "POST",
            "persons",
            query={"select": "*"},
            payload={
                "id": person_id,
                "account_id": account_id,
                "display_name": display_name,
                "relationship": data.get("relationship") or "self",
                "locale": data.get("locale") or "zh-TW",
                "timezone": data.get("timezone") or "Asia/Taipei",
                "is_primary_care_recipient": True,
            },
            prefer="return=representation",
        )[0]
        family_group = self._request(
            "POST",
            "family_groups",
            query={"select": "*"},
            payload={
                "id": family_group_id,
                "account_id": account_id,
                "name": data.get("familyGroupName") or data.get("family_group_name") or "Munea Care Circle",
            },
            prefer="return=representation",
        )[0]
        self._request(
            "POST",
            "family_memberships",
            query={"select": "*"},
            payload={
                "account_id": account_id,
                "family_group_id": family_group_id,
                "person_id": person_id,
                "role": "primary_user",
                "permissions": {"manage_companion": True, "view_family_dashboard": True},
            },
            prefer="return=representation",
        )

        previous_account_id = self.account_id
        previous_person_id = self.person_id
        previous_family_group_id = self.family_group_id
        try:
            self.account_id = account_id
            self.person_id = person_id
            self.family_group_id = family_group_id
            self.save_companion_profile({
                "templateId": companion.get("templateId") or companion.get("template_id") or "nening-real-female",
                "displayName": companion.get("displayName") or companion.get("display_name") or "Munea",
                "nameTouched": bool(companion.get("nameTouched") or companion.get("name_touched")),
            })
            self.save_billing_store({
                "activePlan": "free",
                "platform": "ios",
                "provider": "bootstrap",
                "subscription": {"status": "inactive"},
                "entitlements": {
                    "voiceCompanion": True,
                    "familyDashboard": True,
                    "routineReminders": True,
                    "realtimeAvatar": False,
                    "premiumAvatarMinutesMonthly": 0,
                    "familyMembersMax": 2,
                },
                "usageLedger": {
                    "period": time.strftime("%Y-%m"),
                    "voiceMinutesUsed": 0,
                    "voiceMinutesGranted": 300,
                    "avatarMinutesUsed": 0,
                    "avatarMinutesGranted": 0,
                    "familyMembersUsed": 1,
                    "familyMembersGranted": 2,
                },
            })
            self._request(
                "POST",
                "audit_events",
                query={"select": "*"},
                payload={
                    "account_id": account_id,
                    "actor_user_id": auth_user_id,
                    "event_type": "account_bootstrapped",
                    "target_table": "accounts",
                    "target_id": account_id,
                    "details": {"source": "munea-api"},
                },
                prefer="return=representation",
            )
            return self.load_app_profile_store()
        finally:
            self.account_id = previous_account_id
            self.person_id = previous_person_id
            self.family_group_id = previous_family_group_id

    def load_billing_store(self):
        if not self.enabled():
            return None
        subscription_row = self._first(
            "subscription_ledger",
            {
                "account_id": f"eq.{self.account_id}",
                "select": "*",
                "order": "updated_at.desc",
            },
        )
        period = time.strftime("%Y-%m")
        usage_rows = self._select(
            "usage_ledger",
            {
                "account_id": f"eq.{self.account_id}",
                "period": f"eq.{period}",
                "select": "*",
            },
        )
        return self.billing_rows_to_store(subscription_row, usage_rows, period=period)

    def save_billing_store(self, store):
        if not self.enabled():
            return None
        store = store or {}
        self._request(
            "POST",
            "subscription_ledger",
            query={"select": "*"},
            payload=self.billing_store_to_subscription_row(store),
            prefer="return=representation",
        )

        usage = store.get("usageLedger") or store.get("usage_ledger") or {}
        period = usage.get("period") or time.strftime("%Y-%m")
        for metric, used_key in (
            ("voice_minutes", "voiceMinutesUsed"),
            ("avatar_minutes", "avatarMinutesUsed"),
            ("family_members", "familyMembersUsed"),
        ):
            if used_key not in usage:
                continue
            payload = {
                "account_id": self.account_id,
                "period": period,
                "metric": metric,
                "used": usage.get(used_key) or 0,
                "granted": usage.get(self._granted_key_for_metric(metric)) or 0,
                "source": "munea-api",
            }
            rows = self._request(
                "PATCH",
                "usage_ledger",
                query={
                    "account_id": f"eq.{self.account_id}",
                    "period": f"eq.{period}",
                    "metric": f"eq.{metric}",
                    "select": "*",
                },
                payload=payload,
                prefer="return=representation",
            )
            if not rows:
                self._request(
                    "POST",
                    "usage_ledger",
                    query={"select": "*"},
                    payload=payload,
                    prefer="return=representation",
                )
        return self.load_billing_store()

    def load_credits_store(self):
        if not self.enabled():
            return None
        wallets = self._select(
            "credit_wallets",
            {"account_id": f"eq.{self.account_id}", "select": "*", "order": "created_at.asc"},
        )
        transactions = self._select(
            "credit_transactions",
            {"account_id": f"eq.{self.account_id}", "select": "*", "order": "created_at.asc", "limit": "500"},
        )
        ledger = self._select(
            "credit_ledger",
            {"account_id": f"eq.{self.account_id}", "select": "*", "order": "created_at.asc", "limit": "500"},
        )
        return self.credits_rows_to_store(wallets, transactions, ledger)

    def save_credits_store(self, store):
        if not self.enabled():
            return None
        store = store or {}
        for wallet in store.get("wallets") or []:
            payload = self.credit_wallet_to_row(wallet)
            query = {
                "account_id": f"eq.{self.account_id}",
                "wallet_type": f"eq.{payload['wallet_type']}",
                "person_id": f"eq.{payload['person_id']}" if payload.get("person_id") else "is.null",
                "period": f"eq.{payload['period']}" if payload.get("period") else "is.null",
                "select": "*",
            }
            rows = self._request(
                "PATCH",
                "credit_wallets",
                query=query,
                payload=payload,
                prefer="return=representation",
            )
            if not rows:
                self._request(
                    "POST",
                    "credit_wallets",
                    query={"select": "*"},
                    payload=payload,
                    prefer="return=representation",
                )

        for tx in store.get("transactions") or []:
            payload = self.credit_transaction_to_row(tx)
            idempotency_key = payload.get("idempotency_key")
            if idempotency_key:
                existing = self._first(
                    "credit_transactions",
                    {"account_id": f"eq.{self.account_id}", "idempotency_key": f"eq.{idempotency_key}", "select": "*"},
                )
                if existing:
                    continue
            self._request(
                "POST",
                "credit_transactions",
                query={"select": "*"},
                payload=payload,
                prefer="return=representation",
            )

        for event in store.get("ledger") or []:
            payload = self.credit_ledger_to_row(event)
            source_ref = payload.get("source_ref")
            if source_ref:
                existing = self._first(
                    "credit_ledger",
                    {"account_id": f"eq.{self.account_id}", "source_ref": f"eq.{source_ref}", "select": "*"},
                )
                if existing:
                    continue
            self._request(
                "POST",
                "credit_ledger",
                query={"select": "*"},
                payload=payload,
                prefer="return=representation",
            )
        return self.load_credits_store()

    def load_privacy_requests_store(self):
        if not self.enabled():
            return None
        rows = self._select(
            "privacy_requests",
            {
                "account_id": f"eq.{self.account_id}",
                "select": "*",
                "order": "requested_at.asc",
            },
        )
        return {
            "schemaVersion": 1,
            "accountId": self.account_id,
            "requests": [self.privacy_row_to_request(row) for row in rows],
            "updatedAt": rows[-1].get("requested_at") if rows else None,
        }

    def append_privacy_request(self, req_type, data=None):
        if not self.enabled():
            return None
        data = data or {}
        payload = {
            "account_id": self.account_id,
            "request_type": req_type,
            "status": data.get("status") or "requested",
            "reason": (data.get("reason") or "")[:120],
            "requires_reauth": bool(data.get("requiresReauth", data.get("requires_reauth", True))),
            "subscription_notice_required": bool(
                data.get("subscriptionNoticeRequired", data.get("subscription_notice_required", req_type == "account_deletion"))
            ),
            "metadata": data.get("metadata") or {},
        }
        rows = self._request(
            "POST",
            "privacy_requests",
            query={"select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        return self.privacy_row_to_request(rows[0]) if rows else None

    def append_product_event(self, event):
        if not self.enabled():
            return None
        rows = self._request(
            "POST",
            "product_events",
            query={"select": "*"},
            payload=self.product_event_to_row(event),
            prefer="return=representation",
        )
        return self.product_event_row_to_event(rows[0]) if rows else None

    def append_audit_event(self, event):
        if not self.enabled():
            return None
        rows = self._request(
            "POST",
            "audit_events",
            query={"select": "*"},
            payload=self.audit_event_to_row(event),
            prefer="return=representation",
        )
        return self.audit_row_to_event(rows[0]) if rows else None

    def load_product_events(self, since_iso=None, limit=500):
        if not self.enabled():
            return None
        query = {
            "account_id": f"eq.{self.account_id}",
            "select": "*",
            "order": "event_time.desc",
            "limit": str(limit or 500),
        }
        if since_iso:
            query["event_time"] = f"gte.{since_iso}"
        rows = self._select("product_events", query)
        return [self.product_event_row_to_event(row) for row in rows]

    def load_memory_items(self, query=None, limit=200):
        if not self.enabled():
            return None
        query = query or {}
        filters = {
            "account_id": f"eq.{self.account_id}",
            "person_id": f"eq.{query.get('personId') or query.get('person_id') or self.person_id}",
            "deleted_at": "is.null",
            "select": "*",
            "order": "importance.desc,confidence.desc,updated_at.desc",
            "limit": str(limit or 200),
        }
        memory_type = query.get("type") or query.get("memoryType") or query.get("memory_type")
        if memory_type:
            filters["memory_type"] = f"eq.{memory_type}"
        rows = self._select("memory_items", filters)
        return [self.memory_row_to_item(row) for row in rows]

    def save_memory_items(self, items):
        if not self.enabled():
            return None
        rows_payload = [self.memory_item_to_row(item) for item in (items or [])]
        if not rows_payload:
            return []
        rows = self._request(
            "POST",
            "memory_items",
            query={"select": "*"},
            payload=rows_payload,
            prefer="return=representation",
        )
        return [self.memory_row_to_item(row) for row in rows]

    def soft_delete_memory_items(self, item_ids, deleted_at):
        """整理員用：把重複/低價值的記憶標記為隱藏（deleted_at），不真的抹掉、可還原。"""
        if not self.enabled():
            return None
        ids = [str(i) for i in (item_ids or []) if i]
        if not ids:
            return []
        id_list = ",".join(ids)
        return self._request(
            "PATCH",
            "memory_items",
            query={
                "id": f"in.({id_list})",
                "account_id": f"eq.{self.account_id}",
                "select": "id",
            },
            payload={"deleted_at": deleted_at},
            prefer="return=representation",
        )

    def load_perception_snapshots(self, query=None, limit=100):
        if not self.enabled():
            return None
        query = query or {}
        filters = {
            "account_id": f"eq.{self.account_id}",
            "select": "*",
            "order": "observed_at.desc",
            "limit": str(limit or 100),
        }
        person_id = query.get("personId") or query.get("person_id")
        if person_id:
            filters["person_id"] = f"eq.{person_id}"
        snapshot_type = query.get("snapshotType") or query.get("snapshot_type") or query.get("type")
        if snapshot_type:
            filters["snapshot_type"] = f"eq.{snapshot_type}"
        rows = self._select("perception_snapshots", filters)
        return [self.perception_row_to_snapshot(row) for row in rows]

    def save_perception_snapshots(self, snapshots):
        if not self.enabled():
            return None
        rows_payload = [self.perception_snapshot_to_row(snapshot) for snapshot in (snapshots or [])]
        if not rows_payload:
            return []
        rows = self._request(
            "POST",
            "perception_snapshots",
            query={"select": "*"},
            payload=rows_payload,
            prefer="return=representation",
        )
        return [self.perception_row_to_snapshot(row) for row in rows]

    def load_relationship_states(self, query=None, limit=100):
        if not self.enabled():
            return None
        query = query or {}
        filters = {
            "account_id": f"eq.{self.account_id}",
            "person_id": f"eq.{query.get('personId') or query.get('person_id') or self.person_id}",
            "deleted_at": "is.null",
            "select": "*",
            "order": "updated_at.desc",
            "limit": str(limit or 100),
        }
        template_id = query.get("personaTemplateId") or query.get("persona_template_id") or query.get("templateId")
        if template_id:
            filters["persona_template_id"] = f"eq.{template_id}"
        rows = self._select("companion_relationship_states", filters)
        return [self.relationship_row_to_state(row) for row in rows]

    def save_relationship_state(self, state):
        if not self.enabled():
            return None
        payload = self.relationship_state_to_row(state)
        query = {
            "person_id": f"eq.{payload['person_id']}",
            "persona_template_id": f"eq.{payload['persona_template_id']}",
            "select": "*",
        }
        rows = self._request(
            "PATCH",
            "companion_relationship_states",
            query=query,
            payload=payload,
            prefer="return=representation",
        )
        if not rows:
            rows = self._request(
                "POST",
                "companion_relationship_states",
                query={"select": "*"},
                payload=payload,
                prefer="return=representation",
        )
        return self.relationship_row_to_state(rows[0]) if rows else None

    def load_family_state_store(self, family_group_id=None):
        if not self.enabled():
            return None
        family_group_id = family_group_id or self.family_group_id
        rows = self._select(
            "family_state_entries",
            {
                "account_id": f"eq.{self.account_id}",
                "family_group_id": f"eq.{family_group_id}",
                "select": "*",
                "order": "updated_at.desc",
            },
        )
        return self.family_state_rows_to_store(rows)

    def save_family_state_entry(self, key, value, family_group_id=None, updated_by_person_id=None):
        if not self.enabled():
            return None
        payload = {
            "account_id": self.account_id,
            "family_group_id": family_group_id or self.family_group_id,
            "state_key": key,
            "value": value,
            "updated_by_person_id": updated_by_person_id or self.person_id,
        }
        query = {
            "account_id": f"eq.{payload['account_id']}",
            "family_group_id": f"eq.{payload['family_group_id']}",
            "state_key": f"eq.{payload['state_key']}",
            "select": "*",
        }
        rows = self._request(
            "PATCH",
            "family_state_entries",
            query=query,
            payload=payload,
            prefer="return=representation",
        )
        if not rows:
            rows = self._request(
                "POST",
                "family_state_entries",
                query={"select": "*"},
                payload=payload,
                prefer="return=representation",
            )
        return self.family_state_row_to_entry(rows[0]) if rows else None

    def load_wellbeing_signals(self, person_id=None, limit=200):
        if not self.enabled():
            return None
        person_id = person_id if self._is_uuid(person_id or "") else self.person_id
        query = {
            "account_id": f"eq.{self.account_id}",
            "select": "*",
            "order": "observed_at.desc",
            "limit": str(limit or 200),
        }
        query["person_id"] = f"eq.{person_id}"
        rows = self._select("wellbeing_signals", query)
        return [self.wellbeing_row_to_signal(row) for row in reversed(rows or [])]

    def append_wellbeing_signal(self, signal):
        if not self.enabled():
            return None
        payload = self.wellbeing_signal_to_row(signal)
        rows = self._request(
            "POST",
            "wellbeing_signals",
            query={"select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        return self.wellbeing_row_to_signal(rows[0]) if rows else None

    def _load_family_group(self):
        if self._is_uuid(self.family_group_id):
            return self._first("family_groups", {"id": f"eq.{self.family_group_id}", "select": "*"})
        return self._first("family_groups", {"account_id": f"eq.{self.account_id}", "select": "*", "limit": "1"})

    def _load_family_members(self, family_group_id):
        if not self._is_uuid(family_group_id):
            person = self._first("persons", {"id": f"eq.{self.person_id}", "select": "*"})
            return [self.person_row_to_member(person, role="primary_user")]
        memberships = self._select(
            "family_memberships",
            {"family_group_id": f"eq.{family_group_id}", "select": "*"},
        )
        members = []
        for membership in memberships:
            person = self._first("persons", {"id": f"eq.{membership.get('person_id')}", "select": "*"})
            members.append(self.person_row_to_member(person, role=membership.get("role")))
        return members

    def profile_to_companion_row(self, profile):
        profile = profile or {}
        return {
            "account_id": self.account_id,
            "person_id": self.person_id,
            "template_id": profile.get("templateId") or profile.get("template_id") or "nening-real-female",
            "display_name": profile.get("displayName") or profile.get("display_name") or "Nening",
            "name_touched": bool(profile.get("nameTouched") or profile.get("name_touched")),
        }

    @staticmethod
    def companion_row_to_profile(row):
        row = row or {}
        return {
            "templateId": row.get("template_id") or "nening-real-female",
            "displayName": row.get("display_name") or "Nening",
            "nameTouched": bool(row.get("name_touched")),
            "updatedAt": row.get("updated_at") or row.get("created_at"),
        }

    def person_row_to_member(self, row, role=None):
        row = row or {}
        person_id = row.get("id") or self.person_id
        return {
            "id": person_id,
            "role": role or ("primary_user" if person_id == self.person_id else "family_contact"),
            "displayName": row.get("display_name") or "Primary user",
            "relationship": row.get("relationship") or "self",
        }

    def billing_store_to_subscription_row(self, store):
        store = store or {}
        subscription = store.get("subscription") or {}
        return {
            "account_id": self.account_id,
            "platform": store.get("platform") or "ios",
            "provider": store.get("provider") or "storekit2-or-revenuecat",
            "product_id": subscription.get("productId") or subscription.get("product_id"),
            "original_transaction_id": subscription.get("originalTransactionId") or subscription.get("original_transaction_id"),
            "status": subscription.get("status") or "inactive",
            "active_plan": store.get("activePlan") or store.get("active_plan") or "free",
            "entitlements": store.get("entitlements") or {},
            "verified_at": subscription.get("lastVerifiedAt") or subscription.get("last_verified_at"),
            "expires_at": subscription.get("expiresAt") or subscription.get("expires_at"),
            "will_renew": bool(subscription.get("willRenew") or subscription.get("will_renew")),
            "raw_event_ref": store.get("rawEventRef") or store.get("raw_event_ref"),
        }

    def billing_rows_to_store(self, subscription_row=None, usage_rows=None, period=None):
        row = subscription_row or {}
        usage = self.usage_rows_to_usage_ledger(usage_rows or [], period=period)
        return {
            "schemaVersion": 1,
            "accountId": self.account_id,
            "platform": row.get("platform") or "ios",
            "provider": row.get("provider") or "storekit2-or-revenuecat",
            "activePlan": row.get("active_plan") or "free",
            "subscription": {
                "status": row.get("status") or "inactive",
                "productId": row.get("product_id"),
                "originalTransactionId": row.get("original_transaction_id"),
                "expiresAt": row.get("expires_at"),
                "willRenew": bool(row.get("will_renew")),
                "lastVerifiedAt": row.get("verified_at"),
            },
            "entitlements": row.get("entitlements") or {},
            "usageLedger": usage,
            "serverVerificationRequired": True,
            "updatedAt": row.get("updated_at") or row.get("created_at"),
        }

    @staticmethod
    def usage_rows_to_usage_ledger(rows, period=None):
        usage = {
            "period": period or time.strftime("%Y-%m"),
            "voiceMinutesUsed": 0,
            "avatarMinutesUsed": 0,
        }
        for row in rows:
            metric = row.get("metric")
            used = float(row.get("used") or 0)
            granted = float(row.get("granted") or 0)
            if metric == "voice_minutes":
                usage["voiceMinutesUsed"] = used
                usage["voiceMinutesGranted"] = granted
            elif metric == "avatar_minutes":
                usage["avatarMinutesUsed"] = used
                usage["avatarMinutesGranted"] = granted
            elif metric == "family_members":
                usage["familyMembersUsed"] = used
                usage["familyMembersGranted"] = granted
        return usage

    def credit_wallet_to_row(self, wallet):
        wallet = wallet or {}
        wallet_type = wallet.get("type") or wallet.get("walletType") or wallet.get("wallet_type") or "purchased"
        if wallet_type not in {"included_monthly", "purchased"}:
            wallet_type = "purchased"
        return {
            "account_id": self.account_id,
            "person_id": wallet.get("personId") or wallet.get("person_id") or (self.person_id if wallet_type == "included_monthly" else None),
            "wallet_type": wallet_type,
            "period": wallet.get("period"),
            "balance": wallet.get("balance") or 0,
            "currency_code": wallet.get("currencyCode") or wallet.get("currency_code") or "MUNEA_CREDIT",
            "status": wallet.get("status") or "active",
            "expires_at": wallet.get("expiresAt") or wallet.get("expires_at"),
            "metadata": wallet.get("metadata") or {},
        }

    def credit_transaction_to_row(self, tx):
        tx = tx or {}
        tx_type = tx.get("type") or tx.get("transactionType") or tx.get("transaction_type") or "adjustment"
        return {
            "account_id": tx.get("accountId") or tx.get("account_id") or self.account_id,
            "person_id": tx.get("personId") or tx.get("person_id") or self.person_id,
            "wallet_id": tx.get("walletUuid") or tx.get("wallet_uuid"),
            "transaction_type": tx_type,
            "source": tx.get("source") or "system",
            "amount": tx.get("amount") or 0,
            "balance_after": tx.get("balanceAfter") or tx.get("balance_after"),
            "provider": tx.get("provider"),
            "provider_transaction_id": tx.get("providerTransactionId") or tx.get("provider_transaction_id"),
            "idempotency_key": tx.get("idempotencyKey") or tx.get("idempotency_key") or tx.get("id") or f"local-{int(time.time() * 1000)}",
            "reason": tx.get("reason") or tx_type,
            "metadata": {
                "localWalletId": tx.get("walletId"),
                "walletType": tx.get("walletType"),
                "feature": tx.get("feature"),
            },
        }

    def credit_ledger_to_row(self, event):
        event = event or {}
        event_type = event.get("eventType") or event.get("event_type") or "admin_adjusted"
        if event_type == "credits_grant":
            event_type = "included_allowance_granted"
        elif event_type == "credits_consume":
            event_type = "credits_consumed"
        return {
            "account_id": event.get("accountId") or event.get("account_id") or self.account_id,
            "person_id": event.get("personId") or event.get("person_id") or self.person_id,
            "wallet_id": event.get("walletUuid") or event.get("wallet_uuid"),
            "credit_transaction_id": event.get("creditTransactionUuid") or event.get("credit_transaction_uuid"),
            "event_type": event_type,
            "amount": event.get("amount") or 0,
            "balance_after": event.get("balanceAfter") or event.get("balance_after"),
            "feature": event.get("feature"),
            "source_ref": event.get("sourceRef") or event.get("source_ref") or event.get("id"),
            "metadata": {"localWalletId": event.get("walletId")},
        }

    def credits_rows_to_store(self, wallet_rows=None, transaction_rows=None, ledger_rows=None):
        return {
            "schemaVersion": 1,
            "accountId": self.account_id,
            "personId": self.person_id,
            "currencyCode": "MUNEA_CREDIT",
            "wallets": [self.credit_wallet_row_to_wallet(row) for row in wallet_rows or []],
            "transactions": [self.credit_transaction_row_to_transaction(row) for row in transaction_rows or []],
            "ledger": [self.credit_ledger_row_to_event(row) for row in ledger_rows or []],
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    @staticmethod
    def credit_wallet_row_to_wallet(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "type": row.get("wallet_type") or "purchased",
            "period": row.get("period"),
            "balance": float(row.get("balance") or 0),
            "currencyCode": row.get("currency_code") or "MUNEA_CREDIT",
            "expiresAt": row.get("expires_at"),
            "status": row.get("status") or "active",
            "metadata": row.get("metadata") or {},
        }

    @staticmethod
    def credit_transaction_row_to_transaction(row):
        row = row or {}
        metadata = row.get("metadata") or {}
        return {
            "id": row.get("id") or "",
            "type": row.get("transaction_type") or "adjustment",
            "walletId": metadata.get("localWalletId") or row.get("wallet_id"),
            "walletType": metadata.get("walletType"),
            "amount": float(row.get("amount") or 0),
            "balanceAfter": float(row.get("balance_after") or 0),
            "source": row.get("source") or "system",
            "reason": row.get("reason") or "",
            "feature": metadata.get("feature"),
            "provider": row.get("provider"),
            "providerTransactionId": row.get("provider_transaction_id"),
            "idempotencyKey": row.get("idempotency_key"),
            "createdAt": row.get("created_at"),
        }

    @staticmethod
    def credit_ledger_row_to_event(row):
        row = row or {}
        metadata = row.get("metadata") or {}
        return {
            "id": row.get("id") or "",
            "eventType": row.get("event_type") or "admin_adjusted",
            "walletId": metadata.get("localWalletId") or row.get("wallet_id"),
            "amount": float(row.get("amount") or 0),
            "balanceAfter": float(row.get("balance_after") or 0),
            "feature": row.get("feature"),
            "sourceRef": row.get("source_ref"),
            "createdAt": row.get("created_at"),
        }

    @staticmethod
    def privacy_row_to_request(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "type": row.get("request_type") or "export",
            "status": row.get("status") or "requested",
            "accountId": row.get("account_id") or "",
            "requestedAt": row.get("requested_at"),
            "completedAt": row.get("completed_at"),
            "reason": row.get("reason") or "",
            "requiresReauth": bool(row.get("requires_reauth", True)),
            "subscriptionNoticeRequired": bool(row.get("subscription_notice_required")),
        }

    def product_event_to_row(self, event):
        event = event or {}
        return {
            "account_id": self.account_id,
            "person_id": event.get("personId") or event.get("person_id") or self.person_id,
            "family_group_id": event.get("familyGroupId") or event.get("family_group_id") or self.family_group_id or None,
            "event_name": event.get("eventName") or event.get("event_name") or "unknown_event",
            "event_time": event.get("eventTime") or event.get("event_time") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": event.get("source") or "munea-api",
            "session_id": event.get("sessionId") or event.get("session_id"),
            "properties": event.get("properties") or {},
        }

    def audit_event_to_row(self, event):
        event = event or {}
        target_id = event.get("targetId") or event.get("target_id")
        if not self._is_uuid(target_id):
            target_id = None
        actor_user_id = event.get("actorUserId") or event.get("actor_user_id")
        if not self._is_uuid(actor_user_id):
            actor_user_id = None
        return {
            "account_id": event.get("accountId") or event.get("account_id") or self.account_id,
            "actor_user_id": actor_user_id,
            "event_type": event.get("eventType") or event.get("event_type") or "unknown_event",
            "target_table": event.get("targetTable") or event.get("target_table"),
            "target_id": target_id,
            "details": event.get("details") or {},
        }

    @staticmethod
    def audit_row_to_event(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "actorUserId": row.get("actor_user_id"),
            "eventType": row.get("event_type") or "unknown_event",
            "targetTable": row.get("target_table"),
            "targetId": row.get("target_id"),
            "details": row.get("details") or {},
            "createdAt": row.get("created_at"),
        }

    @staticmethod
    def product_event_row_to_event(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "personId": row.get("person_id"),
            "familyGroupId": row.get("family_group_id"),
            "eventName": row.get("event_name") or "unknown_event",
            "eventTime": row.get("event_time") or row.get("created_at"),
            "source": row.get("source") or "munea-api",
            "sessionId": row.get("session_id"),
            "properties": row.get("properties") or {},
            "createdAt": row.get("created_at"),
        }

    def memory_item_to_row(self, item):
        item = item or {}
        memory_type = item.get("type") or item.get("memoryType") or item.get("memory_type") or "temporary_event"
        return {
            "account_id": item.get("accountId") or item.get("account_id") or self.account_id,
            "person_id": item.get("personId") or item.get("person_id") or self.person_id,
            "source_conversation_summary_id": item.get("sourceConversationSummaryId") or item.get("source_conversation_summary_id"),
            "memory_type": memory_type,
            "content": item.get("content") or "",
            "source": item.get("source") or "conversation",
            "confidence": item.get("confidence", 0.5),
            "importance": item.get("importance", 0.5),
            "sensitivity": item.get("sensitivity") or "normal",
            "consent_scope": item.get("consentScope") or item.get("consent_scope") or "user",
            "valid_from": item.get("validFrom") or item.get("valid_from") or item.get("createdAt") or item.get("created_at"),
            "valid_until": item.get("validUntil") or item.get("valid_until"),
            "last_confirmed_at": item.get("lastConfirmedAt") or item.get("last_confirmed_at"),
            "supersedes_memory_id": item.get("supersedesMemoryId") or item.get("supersedes_memory_id"),
            "metadata": item.get("metadata") or {},
        }

    @staticmethod
    def memory_row_to_item(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "personId": row.get("person_id") or "",
            "type": row.get("memory_type") or "temporary_event",
            "content": row.get("content") or "",
            "source": row.get("source") or "conversation",
            "confidence": float(row.get("confidence") or 0),
            "importance": float(row.get("importance") or 0),
            "sensitivity": row.get("sensitivity") or "normal",
            "consentScope": row.get("consent_scope") or "user",
            "validFrom": row.get("valid_from"),
            "validUntil": row.get("valid_until"),
            "lastConfirmedAt": row.get("last_confirmed_at"),
            "supersedesMemoryId": row.get("supersedes_memory_id"),
            "metadata": row.get("metadata") or {},
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    def perception_snapshot_to_row(self, snapshot):
        snapshot = snapshot or {}
        return {
            "account_id": snapshot.get("accountId") or snapshot.get("account_id") or self.account_id,
            "person_id": snapshot.get("personId") or snapshot.get("person_id") or self.person_id,
            "snapshot_type": snapshot.get("snapshotType") or snapshot.get("snapshot_type") or snapshot.get("type") or "current_topic",
            "observed_at": snapshot.get("observedAt") or snapshot.get("observed_at"),
            "expires_at": snapshot.get("expiresAt") or snapshot.get("expires_at"),
            "facts": snapshot.get("facts") or {},
            "source": snapshot.get("source") or "munea",
        }

    @staticmethod
    def perception_row_to_snapshot(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "personId": row.get("person_id"),
            "snapshotType": row.get("snapshot_type") or "current_topic",
            "observedAt": row.get("observed_at"),
            "expiresAt": row.get("expires_at"),
            "facts": row.get("facts") or {},
            "source": row.get("source") or "munea",
            "createdAt": row.get("created_at"),
        }

    def relationship_state_to_row(self, state):
        state = state or {}
        return {
            "account_id": state.get("accountId") or state.get("account_id") or self.account_id,
            "person_id": state.get("personId") or state.get("person_id") or self.person_id,
            "companion_profile_id": state.get("companionProfileId") or state.get("companion_profile_id"),
            "persona_template_id": state.get("personaTemplateId") or state.get("persona_template_id") or state.get("templateId") or "nening-real-female",
            "rapport_level": state.get("rapportLevel") or state.get("rapport_level") or "new",
            "preferred_address": state.get("preferredAddress") or state.get("preferred_address"),
            "tone_overrides": state.get("toneOverrides") or state.get("tone_overrides") or {},
            "user_boundaries": state.get("userBoundaries") or state.get("user_boundaries") or {},
            "relationship_memory": state.get("relationshipMemory") or state.get("relationship_memory") or {},
            "updated_by_brain_run_id": state.get("updatedByBrainRunId") or state.get("updated_by_brain_run_id"),
        }

    @staticmethod
    def relationship_row_to_state(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "personId": row.get("person_id") or "",
            "companionProfileId": row.get("companion_profile_id"),
            "personaTemplateId": row.get("persona_template_id") or "nening-real-female",
            "rapportLevel": row.get("rapport_level") or "new",
            "preferredAddress": row.get("preferred_address"),
            "toneOverrides": row.get("tone_overrides") or {},
            "userBoundaries": row.get("user_boundaries") or {},
            "relationshipMemory": row.get("relationship_memory") or {},
            "updatedByBrainRunId": row.get("updated_by_brain_run_id"),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
            "deletedAt": row.get("deleted_at"),
        }

    @staticmethod
    def family_state_row_to_entry(row):
        row = row or {}
        return {
            "key": row.get("state_key") or "",
            "value": row.get("value"),
            "updatedAt": row.get("updated_at") or row.get("created_at"),
            "updatedByPersonId": row.get("updated_by_person_id"),
            "familyGroupId": row.get("family_group_id"),
        }

    def family_state_rows_to_store(self, rows):
        store = {}
        for row in rows or []:
            entry = self.family_state_row_to_entry(row)
            key = entry.get("key")
            if key:
                store[key] = {
                    "value": entry.get("value"),
                    "updatedAt": entry.get("updatedAt"),
                    "updatedByPersonId": entry.get("updatedByPersonId"),
                    "familyGroupId": entry.get("familyGroupId"),
                }
        return store

    @staticmethod
    def _normalize_wellbeing_mood(mood):
        allowed = {"happy", "pleasant", "steady", "tired", "low", "irritated", "mixed", "unknown"}
        return mood if mood in allowed else "unknown"

    def wellbeing_signal_to_row(self, signal):
        signal = signal or {}
        mood = signal.get("mood")
        normalized_mood = self._normalize_wellbeing_mood(signal.get("moodKey") or signal.get("mood_key") or mood)
        facts = dict(signal.get("facts") or {})
        person_id = signal.get("personId") or signal.get("person_id") or self.person_id
        family_group_id = signal.get("familyGroupId") or signal.get("family_group_id") or self.family_group_id
        if person_id and not self._is_uuid(person_id):
            facts.setdefault("originalPersonId", person_id)
            person_id = self.person_id
        if family_group_id and not self._is_uuid(family_group_id):
            facts.setdefault("originalFamilyGroupId", family_group_id)
            family_group_id = self.family_group_id or None
        if mood and mood != normalized_mood:
            facts.setdefault("originalMood", mood)
        for source_key, facts_key in [
            ("moodKey", "moodKey"),
            ("moodColor", "moodColor"),
            ("levelLabel", "levelLabel"),
            ("confidence", "confidence"),
            ("modality", "modality"),
            ("isMedicalInference", "isMedicalInference"),
        ]:
            if source_key in signal and signal.get(source_key) is not None:
                facts[facts_key] = signal.get(source_key)
        return {
            "account_id": signal.get("accountId") or signal.get("account_id") or self.account_id,
            "person_id": person_id,
            "family_group_id": family_group_id or None,
            "signal_date": signal.get("date") or signal.get("signalDate") or signal.get("signal_date"),
            "signal_type": signal.get("signalType") or signal.get("signal_type") or "mood",
            "mood": normalized_mood,
            "level": signal.get("level"),
            "visibility": signal.get("visibility") or "family_summary",
            "facts": facts,
            "source": signal.get("source") or "munea-api",
            "observed_at": signal.get("observedAt") or signal.get("observed_at") or signal.get("createdAt") or signal.get("created_at"),
        }

    @staticmethod
    def wellbeing_row_to_signal(row):
        row = row or {}
        facts = row.get("facts") or {}
        mood = facts.get("originalMood") or row.get("mood") or "unknown"
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "personId": row.get("person_id") or "",
            "familyGroupId": row.get("family_group_id"),
            "date": row.get("signal_date"),
            "modality": facts.get("modality"),
            "signalType": row.get("signal_type") or "mood",
            "source": row.get("source") or "munea-api",
            "mood": mood,
            "moodKey": facts.get("moodKey") or row.get("mood"),
            "moodColor": facts.get("moodColor") or {},
            "level": row.get("level"),
            "levelLabel": facts.get("levelLabel") or mood,
            "confidence": facts.get("confidence", 1.0),
            "isMedicalInference": bool(facts.get("isMedicalInference", False)),
            "createdAt": row.get("created_at"),
            "observedAt": row.get("observed_at"),
            "visibility": row.get("visibility"),
            "facts": facts,
        }

    @staticmethod
    def _granted_key_for_metric(metric):
        return {
            "voice_minutes": "voiceMinutesGranted",
            "avatar_minutes": "avatarMinutesGranted",
            "family_members": "familyMembersGranted",
        }.get(metric, "granted")

    def _first(self, table, query):
        rows = self._select(table, {**(query or {}), "limit": (query or {}).get("limit", "1")})
        return rows[0] if rows else None

    def _select(self, table, query):
        return self._request("GET", table, query=query)

    def _request(self, method, table, query=None, payload=None, prefer=None):
        if not self.enabled():
            raise RuntimeError("Supabase adapter is not fully configured")
        # 斷路器：雲端連不上時，20 秒內同一波後續呼叫直接秒退（走本地備份），
        # 不再每次苦等 4 秒逾時。防「單一請求連問十幾次、累加成數分鐘卡死」。
        if _circuit_open():
            raise RuntimeError("Supabase circuit open: recent connection failure, using local fallback")
        if _table_known_missing(table):
            raise RuntimeError(f"Supabase table '{table}' known missing (PGRST205 cached), using local fallback")
        query_string = urllib.parse.urlencode(query or {})
        url = f"{self.url}/rest/v1/{table}"
        if query_string:
            url = f"{url}?{query_string}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "apikey": self.service_key,
            "authorization": f"Bearer {self.service_key}",
            "content-type": "application/json",
        }
        if prefer:
            headers["prefer"] = prefer
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                raw = resp.read().decode("utf-8")
                _reset_circuit()
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as e:
            # HTTP 層有明確快速回應（如缺表 404）：不觸發斷路器（本來就快），但視為連線成功可用
            _reset_circuit()
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 404 and "PGRST205" in detail:
                _mark_table_missing(table)  # 記著這張表缺，30 秒內同批呼叫秒退
            raise RuntimeError(f"Supabase {method} {table} failed: {e.code} {detail}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            # 連線層失敗（逾時 / 連不上 / 被重置）：開啟斷路器，讓同批後續呼叫秒退
            _trip_circuit()
            raise RuntimeError(f"Supabase {method} {table} unreachable: {type(e).__name__}") from e

    @staticmethod
    def _is_uuid(value):
        return bool(value and UUID_RE.match(value))


def make_adapter(env=None):
    return SupabaseAdapter(env=env)
