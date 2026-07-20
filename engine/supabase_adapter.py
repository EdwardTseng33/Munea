"""
Supabase-ready data adapter for Munea.

This module is intentionally stdlib-only for the current prototype. It keeps
Supabase service credentials on the backend side and lets server.py keep a JSON
fallback until the cloud project, auth, and seeded account/person ids are ready.
"""
import json
import hashlib
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


class SupabaseRequestError(RuntimeError):
    """Structured REST failure without weakening existing RuntimeError callers."""

    def __init__(
        self,
        message,
        *,
        error_kind="http_error",
        status_code=None,
        error_code=None,
    ):
        super().__init__(message)
        self.error_kind = error_kind
        self.status_code = status_code
        self.error_code = error_code


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
    def __init__(self, env=None, identity=None):
        self.env = env or os.environ
        identity = identity or {}
        self.request_scoped = bool(identity)
        self.url = (self.env.get("SUPABASE_URL") or "").rstrip("/")
        self.service_key = self.env.get("SUPABASE_SERVICE_ROLE_KEY") or ""
        self.provider = (self.env.get("MUNEA_DATABASE_PROVIDER") or "json").lower()
        self.account_id = identity.get("accountId") or identity.get("account_id") or self.env.get("MUNEA_SUPABASE_ACCOUNT_ID") or ""
        self.person_id = identity.get("personId") or identity.get("person_id") or self.env.get("MUNEA_SUPABASE_PERSON_ID") or ""
        self.family_group_id = identity.get("familyGroupId") or identity.get("family_group_id") or self.env.get("MUNEA_SUPABASE_FAMILY_GROUP_ID") or ""
        self.auth_user_id = identity.get("authUserId") or identity.get("auth_user_id") or ""

    def configured(self):
        return self.provider == "supabase" and bool(self.url) and bool(self.service_key)

    def _service_headers(self):
        headers = {
            "apikey": self.service_key,
            "content-type": "application/json",
        }
        # New Supabase secret keys are opaque API keys. Legacy service_role
        # keys are JWTs and still require the bearer header.
        if not self.service_key.startswith("sb_secret_"):
            headers["authorization"] = f"Bearer {self.service_key}"
        return headers

    def payload_account_id(self, value=None):
        """Never trust a client-supplied tenant id on an authenticated request."""
        return self.account_id if self.request_scoped else (value or self.account_id)

    def owns_account_id(self, account_id):
        return bool(self.request_scoped and self._is_uuid(account_id) and account_id == self.account_id)

    def owns_person_id(self, person_id):
        if not self.request_scoped or not self._is_uuid(person_id):
            return False
        return bool(self._first(
            "persons",
            {"id": f"eq.{person_id}", "account_id": f"eq.{self.account_id}", "select": "id"},
        ))

    def owns_family_group_id(self, family_group_id):
        if not self.request_scoped or not self._is_uuid(family_group_id):
            return False
        # A member invited into another account's circle legitimately operates
        # on that circle while retaining their own billing account.
        if family_group_id == self.family_group_id:
            return True
        return bool(self._first(
            "family_groups",
            {"id": f"eq.{family_group_id}", "account_id": f"eq.{self.account_id}", "select": "id"},
        ))

    def is_account_owner(self):
        """Whether the authenticated, request-scoped user owns this account."""
        if not self.request_scoped or not self._is_uuid(self.auth_user_id):
            return False
        return bool(self._first(
            "account_members",
            {
                "account_id": f"eq.{self.account_id}",
                "user_id": f"eq.{self.auth_user_id}",
                "role": "eq.owner",
                "status": "eq.active",
                "select": "id",
            },
        ))

    def delete_scoped_account(self, auth_user_id):
        """Permanently delete an owner account and its Supabase Auth identity."""
        if not self.enabled() or not self.request_scoped:
            raise RuntimeError("Account deletion requires a request-scoped Supabase identity")
        if not self._is_uuid(auth_user_id) or auth_user_id != self.auth_user_id:
            raise PermissionError("account_deletion_identity_mismatch")

        owner = self._first(
            "account_members",
            {
                "account_id": f"eq.{self.account_id}",
                "user_id": f"eq.{auth_user_id}",
                "role": "eq.owner",
                "status": "eq.active",
                "select": "id",
            },
        )
        if not owner:
            raise PermissionError("account_deletion_owner_required")

        receipt_hash = hashlib.sha256(f"{self.account_id}:{auth_user_id}".encode("utf-8")).hexdigest()
        self._request(
            "POST",
            "audit_events",
            query={"select": "id"},
            payload={
                "account_id": self.account_id,
                "actor_user_id": auth_user_id,
                "event_type": "account_deletion_confirmed",
                "target_table": "accounts",
                "target_id": self.account_id,
                "details": {
                    "receiptHash": receipt_hash,
                    "scope": "account_and_cascading_personal_data",
                },
            },
            prefer="return=minimal",
        )
        deleted = self._request(
            "DELETE",
            "accounts",
            query={"id": f"eq.{self.account_id}", "select": "id"},
            prefer="return=representation",
        )
        if not deleted:
            raise RuntimeError("Supabase account deletion did not delete an account row")

        auth_deleted = False
        auth_error = None
        try:
            self._delete_auth_user(auth_user_id)
            auth_deleted = True
        except Exception as exc:
            # Personal tables are already gone. Surface cleanup state without
            # pretending the Auth identity was removed too.
            auth_error = type(exc).__name__

        return {
            "accountDeleted": True,
            "authUserDeleted": auth_deleted,
            "cleanupRequired": not auth_deleted,
            "receiptHash": receipt_hash,
            "authCleanupError": auth_error,
        }

    def export_scoped_personal_data(self):
        """Build a portable export for only the authenticated person's data."""
        if not self.enabled() or not self.request_scoped:
            raise RuntimeError("Personal export requires a request-scoped Supabase identity")
        if not self._is_uuid(self.auth_user_id) or not self._is_uuid(self.person_id):
            raise PermissionError("privacy_export_identity_mismatch")

        def rows(table, query):
            try:
                return self._select(table, {**query, "select": query.get("select") or "*"}) or []
            except Exception as exc:
                # Older environments may not have every additive migration yet.
                if getattr(exc, "code", None) == 404 or "404" in str(exc) or "does not exist" in str(exc):
                    return []
                raise

        account = rows("accounts", {
            "id": f"eq.{self.account_id}",
            "select": "id,name,locale,preferred_languages,created_at,updated_at",
        })
        membership = rows("account_members", {
            "account_id": f"eq.{self.account_id}",
            "user_id": f"eq.{self.auth_user_id}",
            "select": "id,account_id,user_id,role,status,created_at,updated_at",
        })
        person = rows("persons", {
            "id": f"eq.{self.person_id}",
            "account_id": f"eq.{self.account_id}",
            "select": "id,account_id,display_name,relationship,locale,timezone,is_primary_care_recipient,region_code,attributes,created_at,updated_at",
        })
        family_memberships = rows("family_memberships", {
            "person_id": f"eq.{self.person_id}",
            "select": "id,account_id,family_group_id,person_id,role,permissions,created_at,updated_at",
        })
        family_groups = []
        for group_id in sorted({row.get("family_group_id") for row in family_memberships if self._is_uuid(row.get("family_group_id") or "")}):
            family_groups.extend(rows("family_groups", {
                "id": f"eq.{group_id}",
                "select": "id,name,created_at,updated_at",
            }))

        person_tables = {
            "companionProfiles": ("companion_profiles", "*"),
            "routineReminders": ("routine_reminders", "*"),
            "medicationDoseEvents": ("medication_dose_events", "*"),
            "voiceSessions": ("voice_sessions", "*"),
            "conversationSummaries": ("conversation_summaries", "*"),
            "safetyEvents": ("safety_events", "*"),
            "productEvents": ("product_events", "*"),
            "dailyUserMetrics": ("daily_user_metrics", "*"),
            "voiceSessionMetrics": ("voice_session_metrics", "*"),
            "reminderEvents": ("reminder_events", "*"),
            "familyInteractionEvents": ("family_interaction_events", "*"),
            "memoryItems": ("memory_items", "id,account_id,person_id,source_conversation_summary_id,memory_type,content,source,confidence,importance,sensitivity,consent_scope,valid_from,valid_until,last_confirmed_at,supersedes_memory_id,metadata,created_at,updated_at"),
            "perceptionSnapshots": ("perception_snapshots", "*"),
            "wellbeingSignals": ("wellbeing_signals", "*"),
            "consentRecords": ("consent_records", "*"),
            "familyActivityParticipation": ("family_activity_participants", "*"),
        }
        personal = {
            key: rows(table, {
                "account_id": f"eq.{self.account_id}",
                "person_id": f"eq.{self.person_id}",
                "select": select,
                "order": "created_at.asc",
                "limit": "5000",
            })
            for key, (table, select) in person_tables.items()
        }
        account_tables = {
            "subscription": "subscription_ledger",
            "usage": "usage_ledger",
            "creditWallets": "credit_wallets",
            "creditTransactions": "credit_transactions",
            "creditLedger": "credit_ledger",
            "privacyRequests": "privacy_requests",
        }
        account_data = {
            key: rows(table, {
                "account_id": f"eq.{self.account_id}",
                "select": "*",
                "order": "created_at.asc",
                "limit": "5000",
            })
            for key, table in account_tables.items()
        }
        account_data["auditEvents"] = rows("audit_events", {
            "account_id": f"eq.{self.account_id}",
            "actor_user_id": f"eq.{self.auth_user_id}",
            "select": "id,event_type,target_table,target_id,details,created_at",
            "order": "created_at.asc",
            "limit": "5000",
        })
        return {
            "schemaVersion": 1,
            "scope": "authenticated_person_and_owned_billing_account",
            "account": account[0] if account else None,
            "accountMembership": membership[0] if membership else None,
            "person": person[0] if person else None,
            "familyMemberships": family_memberships,
            "familyGroups": family_groups,
            "personalData": personal,
            "billingAndPrivacy": account_data,
        }

    def _delete_auth_user(self, auth_user_id):
        if not self.configured() or not self._is_uuid(auth_user_id):
            raise RuntimeError("Supabase Auth admin deletion is not configured")
        url = f"{self.url}/auth/v1/admin/users/{urllib.parse.quote(auth_user_id)}?should_soft_delete=false"
        headers = self._service_headers()
        req = urllib.request.Request(url, headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status not in (200, 204):
                    raise RuntimeError(f"Supabase Auth user deletion failed: {resp.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Supabase Auth user deletion failed: {exc.code} {detail}") from exc

    def enabled(self):
        return (
            self.configured()
            and self._is_uuid(self.account_id)
            and self._is_uuid(self.person_id)
        )

    def resolve_auth_identity(self, auth_user_id):
        """Resolve an authenticated user to one account-scoped data identity."""
        if not self.configured():
            return None
        if not self._is_uuid(auth_user_id):
            raise RuntimeError("A valid auth user id is required for account scoping")

        member = self._first(
            "account_members",
            {"user_id": f"eq.{auth_user_id}", "status": "eq.active", "select": "*"},
        )
        account_id = (member or {}).get("account_id")
        if not self._is_uuid(account_id):
            return None

        person = self._first(
            "persons",
            {"account_id": f"eq.{account_id}", "auth_user_id": f"eq.{auth_user_id}", "select": "*"},
        )
        if not person:
            person = self._first(
                "persons",
                {"account_id": f"eq.{account_id}", "is_primary_care_recipient": "eq.true", "select": "*"},
            )
        person_id = (person or {}).get("id")
        if not self._is_uuid(person_id):
            return None

        # A person may retain their own subscription account while joining one
        # other family's circle.  The latest membership is the active circle;
        # the initial self-membership remains as the user's standalone fallback.
        membership = self._first(
            "family_memberships",
            {"person_id": f"eq.{person_id}", "select": "*", "order": "created_at.desc", "limit": "1"},
        )
        family_group_id = (membership or {}).get("family_group_id") or ""
        return {
            "accountId": account_id,
            "personId": person_id,
            "familyGroupId": family_group_id if self._is_uuid(family_group_id) else "",
            "authUserId": auth_user_id,
        }

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
                "medication_dose_events",
                "family_relay_messages",
                "push_devices",
                "notification_events",
                "notification_deliveries",
                "notification_settings",
                "enterprise_clients",
                "enterprise_seats",
                "enterprise_seat_events",
                "enterprise_invoices",
            ],
        }

    def check_table(self, table):
        if not self.enabled():
            return False
        select_columns = {
            "companion_persona_templates": "template_id",
            "entitlement_policy_versions": "policy_key",
            "notification_settings": "person_id",
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

    def load_admin_accounts(self, query=None, limit=50):
        if not self.enabled():
            return None
        query = (query or "").strip()
        limit = max(1, min(200, int(limit or 50)))
        filters = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
        if query:
            if self._is_uuid(query):
                filters["or"] = f"(id.eq.{query},name.ilike.*{query}*)"
            else:
                filters["name"] = f"ilike.*{query}*"
        rows = self._select("accounts", filters)
        summaries = []
        for account in rows or []:
            account_id = account.get("id")
            family_group = self._first("family_groups", {"account_id": f"eq.{account_id}", "select": "*", "limit": "1"})
            primary_person = self._first(
                "persons",
                {"account_id": f"eq.{account_id}", "is_primary_care_recipient": "eq.true", "select": "*", "limit": "1"},
            )
            memberships = []
            if family_group and family_group.get("id"):
                memberships = self._select(
                    "family_memberships",
                    {"account_id": f"eq.{account_id}", "family_group_id": f"eq.{family_group.get('id')}", "select": "*"},
                )
            companion = None
            if primary_person and primary_person.get("id"):
                companion = self._first(
                    "companion_profiles",
                    {"account_id": f"eq.{account_id}", "person_id": f"eq.{primary_person.get('id')}", "select": "*", "limit": "1"},
                )
            summaries.append(self.admin_account_rows_to_summary(account, family_group, primary_person, memberships, companion))
        return summaries

    def load_admin_medication_doses(self, since_date=None, limit=3000):
        """後台跨帳號用藥依從率：不依 account_id 篩選、service-role 全表查詢近 N 天服藥事件。"""
        if not self.enabled():
            return None
        limit = max(1, min(5000, int(limit or 3000)))
        filters = {
            "select": "*",
            "order": "scheduled_date.desc,updated_at.desc",
            "limit": str(limit),
        }
        if since_date:
            filters["scheduled_date"] = f"gte.{str(since_date)[:10]}"
        rows = self._select("medication_dose_events", filters)
        return [self.medication_dose_row_to_item(row) for row in rows or []]

    def load_admin_wellbeing_signals(self, since_iso=None, limit=5000):
        """後台跨帳號心情趨勢：不篩 account_id，service-role 全表查詢近 N 天心情訊號（wellbeing_signals）。
        只回全表列，不做內容過濾——聊天內容（facts 裡的 topics/positives/concerns 等）由呼叫端自行決定
        要不要用；後台心情趨勢頁只聚合次數與分數，不轉交任何原始對話文字。"""
        if not self.enabled():
            return None
        limit = max(1, min(10000, int(limit or 5000)))
        filters = {
            "select": "*",
            "order": "observed_at.desc",
            "limit": str(limit),
        }
        if since_iso:
            filters["observed_at"] = f"gte.{since_iso}"
        rows = self._select("wellbeing_signals", filters)
        signals = [self.wellbeing_row_to_signal(row) for row in rows or []]
        # 後台聚合用：mood 換成英文 key（App 顯示走 load_wellbeing_signals，不經這條，不受影響）。
        for signal in signals:
            signal["mood"] = self._recover_admin_wellbeing_mood(signal)
        return signals

    def load_persons_by_ids(self, person_ids):
        """後台名單顯示用：批次查 person display_name（只回顯示名，不含其他個資）。"""
        if not self.enabled():
            return None
        ids = sorted({str(pid) for pid in (person_ids or []) if pid and self._is_uuid(str(pid))})
        if not ids:
            return {}
        rows = self._select("persons", {
            "id": f"in.({','.join(ids)})",
            "select": "id,display_name",
            "limit": str(len(ids)),
        })
        return {row.get("id"): row.get("display_name") for row in rows or [] if row.get("id")}

    def load_admin_family_memberships(self, limit=5000):
        """後台跨帳號家庭圈成員名單：不篩 account_id，service-role 全表查詢角色（誰是長輩／誰是家人）。"""
        if not self.enabled():
            return None
        limit = max(1, min(10000, int(limit or 5000)))
        rows = self._select("family_memberships", {
            "select": "id,account_id,family_group_id,person_id,role,created_at,updated_at",
            "order": "family_group_id.asc,created_at.asc",
            "limit": str(limit),
        })
        return [{
            "id": row.get("id"),
            "accountId": row.get("account_id"),
            "familyGroupId": row.get("family_group_id"),
            "personId": row.get("person_id"),
            "role": row.get("role") or "family_contact",
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        } for row in rows or []]

    def load_admin_family_invitations(self, since_iso=None, limit=3000):
        """後台跨帳號邀請成效：不篩 account_id，service-role 全表查詢。"""
        if not self.enabled():
            return None
        limit = max(1, min(5000, int(limit or 3000)))
        filters = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
        if since_iso:
            filters["created_at"] = f"gte.{since_iso}"
        rows = self._select("family_invitations", filters)
        return [self.family_invitation_row_to_invitation(row) for row in rows or []]

    def load_admin_family_relay_messages(self, since_iso=None, limit=5000):
        """後台跨帳號家人傳話：不篩 account_id，service-role 全表查詢。"""
        if not self.enabled():
            return None
        limit = max(1, min(10000, int(limit or 5000)))
        filters = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
        if since_iso:
            filters["created_at"] = f"gte.{since_iso}"
        rows = self._select("family_relay_messages", filters)
        return [self.family_relay_row_to_relay(row) for row in rows or []]

    def load_admin_family_activities(self, since_iso=None, limit=3000):
        """後台跨帳號家庭活動：不篩 account_id，service-role 全表查詢。"""
        if not self.enabled():
            return None
        limit = max(1, min(5000, int(limit or 3000)))
        filters = {"select": "*", "order": "updated_at.desc", "limit": str(limit)}
        if since_iso:
            filters["updated_at"] = f"gte.{since_iso}"
        rows = self._select("family_activities", filters)
        return [self.family_activity_row_to_activity(row) for row in rows or []]

    def load_admin_family_activity_participants(self, since_iso=None, limit=5000):
        """後台跨帳號家庭活動參與者：不篩 account_id，service-role 全表查詢。"""
        if not self.enabled():
            return None
        limit = max(1, min(10000, int(limit or 5000)))
        filters = {"select": "*", "order": "updated_at.desc", "limit": str(limit)}
        if since_iso:
            filters["updated_at"] = f"gte.{since_iso}"
        rows = self._select("family_activity_participants", filters)
        return [self.family_activity_participant_row_to_participant(row) for row in rows or []]

    def load_admin_family_engagement_events(self, event_names, since_iso=None, limit=5000):
        """後台跨帳號『看家庭看板／看家人訊息』事件：不篩 account_id，service-role 全表查詢。"""
        if not self.enabled():
            return None
        names = [str(name) for name in (event_names or []) if name]
        if not names:
            return []
        limit = max(1, min(10000, int(limit or 5000)))
        filters = {
            "select": "*",
            "event_name": f"in.({','.join(names)})",
            "order": "event_time.desc",
            "limit": str(limit),
        }
        if since_iso:
            filters["event_time"] = f"gte.{since_iso}"
        rows = self._select("product_events", filters)
        return [self.product_event_row_to_event(row) for row in rows or []]

    def load_family_groups_by_ids(self, family_group_ids):
        """後台名單顯示用：批次查家庭圈名稱（只回名稱，不含其他個資）。"""
        if not self.enabled():
            return None
        ids = sorted({str(fid) for fid in (family_group_ids or []) if fid and self._is_uuid(str(fid))})
        if not ids:
            return {}
        rows = self._select("family_groups", {
            "id": f"in.({','.join(ids)})",
            "select": "id,name",
            "limit": str(len(ids)),
        })
        return {row.get("id"): row.get("name") for row in rows or [] if row.get("id")}

    def load_admin_family_last_action(self, family_group_ids, event_names, limit=1000):
        """『沒人顧』名單用：不限視窗，查這些家庭圈最後一次傳話／看家庭看板的時間，找最久沒人顧的家。"""
        if not self.enabled():
            return None
        ids = sorted({str(fid) for fid in (family_group_ids or []) if fid and self._is_uuid(str(fid))})
        if not ids:
            return {}
        id_list = ",".join(ids)
        limit = max(1, min(5000, int(limit or 1000)))
        last_seen = {}

        def _bump(fg, ts):
            if fg and ts and (fg not in last_seen or ts > last_seen[fg]):
                last_seen[fg] = ts

        relay_rows = self._select("family_relay_messages", {
            "family_group_id": f"in.({id_list})",
            "select": "family_group_id,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        }) or []
        for row in relay_rows:
            _bump(row.get("family_group_id"), row.get("created_at"))

        names = [str(name) for name in (event_names or []) if name]
        if names:
            event_rows = self._select("product_events", {
                "family_group_id": f"in.({id_list})",
                "event_name": f"in.({','.join(names)})",
                "select": "family_group_id,event_time",
                "order": "event_time.desc",
                "limit": str(limit),
            }) or []
            for row in event_rows:
                _bump(row.get("family_group_id"), row.get("event_time"))

        return last_seen

    def load_admin_relationship_states(self, limit=5000):
        """後台跨帳號關係深度：不篩 account_id，service-role 全表查詢目前關係狀態（現況快照，不分時間窗）。
        只取 person/account/等級/時間欄位，不取 tone_overrides／user_boundaries／relationship_memory
        （那些是內部運作用的狀態，不是後台該看的東西）。"""
        if not self.enabled():
            return None
        limit = max(1, min(10000, int(limit or 5000)))
        rows = self._select("companion_relationship_states", {
            "select": "person_id,account_id,rapport_level,created_at,updated_at",
            "deleted_at": "is.null",
            "order": "updated_at.desc",
            "limit": str(limit),
        })
        return [{
            "personId": row.get("person_id"),
            "accountId": row.get("account_id"),
            "rapportLevel": row.get("rapport_level") or "new",
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        } for row in rows or []]

    def load_admin_memory_item_counts(self, limit=20000):
        """後台跨帳號記憶筆數：不篩 account_id，service-role 全表查詢——只取 person/account/建立時間，
        絕不選 content／metadata／memory_type／source 任何一個欄位。後台『關係深度』頁只算幾筆記憶，
        記憶內容永遠不能透過這支查詢流出。"""
        if not self.enabled():
            return None
        limit = max(1, min(50000, int(limit or 20000)))
        rows = self._select("memory_items", {
            "select": "person_id,account_id,created_at",
            "deleted_at": "is.null",
            "order": "created_at.desc",
            "limit": str(limit),
        })
        return [{
            "personId": row.get("person_id"),
            "accountId": row.get("account_id"),
            "createdAt": row.get("created_at"),
        } for row in rows or []]

    def load_family_groups_by_account_ids(self, account_ids):
        """後台名單顯示用：批次查帳號對應的家庭圈名稱（只回名稱，不含其他個資）。"""
        if not self.enabled():
            return None
        ids = sorted({str(aid) for aid in (account_ids or []) if aid and self._is_uuid(str(aid))})
        if not ids:
            return {}
        rows = self._select("family_groups", {
            "account_id": f"in.({','.join(ids)})",
            "select": "account_id,name",
            "limit": str(len(ids)),
        })
        return {row.get("account_id"): row.get("name") for row in rows or [] if row.get("account_id")}

    # ── 企業席次（B2B）：企業席次·後台管理與月結 需求單 2.1–2.5 ──
    # 這四張表／grant_ref 欄位不屬於任何單一 account，不走 payload_account_id() 的
    # 「信任邊界」機制（那套是給一般使用者請求用的）。這裡全部是後台 service-role 操作，
    # 呼叫端（engine/enterprise_seats.py）本身就是唯一信任邊界。

    def find_auth_user_by_email(self, email):
        """GoTrue Admin API 用 email 精確比對找已註冊帳號（企業名單匯入預檢用：判斷「已註冊」）。
        只需要 URL + service key，不需要帳號／person 身分，跟 _delete_auth_user 同一個入口。"""
        email = str(email or "").strip().lower()
        if not self.configured() or not email:
            return None
        url = f"{self.url}/auth/v1/admin/users?email={urllib.parse.quote(email)}"
        req = urllib.request.Request(url, headers=self._service_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise SupabaseRequestError(
                f"Supabase admin user lookup failed: {exc.code} {detail}",
                error_kind="permission" if exc.code in (401, 403) else "http_error",
                status_code=exc.code,
            ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise SupabaseRequestError(
                f"Supabase admin user lookup unreachable: {type(exc).__name__}",
                error_kind="unreachable",
            ) from exc
        users = data.get("users") if isinstance(data, dict) else data
        for user in users or []:
            if str(user.get("email") or "").strip().lower() == email:
                return user
        return None

    def load_enterprise_clients(self, query=None, status=None, limit=200):
        """後台企業客戶列表：不篩 account_id（企業客戶本來就不屬於任何單一 account）。"""
        if not self.enabled():
            return None
        limit = max(1, min(500, int(limit or 200)))
        filters = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
        if status:
            filters["status"] = f"eq.{status}"
        query = str(query or "").strip()
        if query:
            filters["or"] = f"(name.ilike.*{query}*,tax_id.ilike.*{query}*,contact_email.ilike.*{query}*)"
        rows = self._select("enterprise_clients", filters)
        return [self.enterprise_client_row_to_item(row) for row in rows or []]

    def get_enterprise_client(self, client_id):
        if not self.enabled() or not self._is_uuid(client_id or ""):
            return None
        row = self._first("enterprise_clients", {"id": f"eq.{client_id}", "select": "*"})
        return self.enterprise_client_row_to_item(row) if row else None

    def save_enterprise_client(self, client):
        """依 id 是否存在做 upsert（先 PATCH，沒命中再 POST），跟 save_companion_profile 同一套寫法。"""
        if not self.enabled():
            return None
        payload = self.enterprise_client_to_row(client)
        client_id = (client or {}).get("id")
        rows = None
        if client_id and self._is_uuid(client_id):
            rows = self._request(
                "PATCH", "enterprise_clients",
                query={"id": f"eq.{client_id}", "select": "*"},
                payload=payload, prefer="return=representation",
            )
        if not rows:
            create_payload = dict(payload)
            if client_id and self._is_uuid(client_id):
                create_payload["id"] = client_id
            rows = self._request(
                "POST", "enterprise_clients",
                query={"select": "*"},
                payload=create_payload, prefer="return=representation",
            )
        return self.enterprise_client_row_to_item(rows[0]) if rows else None

    def enterprise_client_to_row(self, client):
        client = client or {}
        return {
            "name": str(client.get("name") or "").strip()[:200],
            "client_code": client.get("clientCode") or client.get("client_code"),
            "tax_id": client.get("taxId") or client.get("tax_id"),
            "billing_address": client.get("billingAddress") or client.get("billing_address"),
            "contact_name": client.get("contactName") or client.get("contact_name"),
            "contact_email": client.get("contactEmail") or client.get("contact_email"),
            "contact_phone": client.get("contactPhone") or client.get("contact_phone"),
            "plan_tier": client.get("planTier") or client.get("plan_tier") or "plus",
            "unit_price_twd": client.get("unitPriceTwd") if client.get("unitPriceTwd") is not None else (client.get("unit_price_twd") or 0),
            "contract_start": client.get("contractStart") or client.get("contract_start"),
            "contract_end": client.get("contractEnd") or client.get("contract_end"),
            "seat_quota": int(client.get("seatQuota") or client.get("seat_quota") or 0),
            "status": client.get("status") or "active",
            "report_recipients": client.get("reportRecipients") or client.get("report_recipients") or [],
            "notes": client.get("notes"),
        }

    @staticmethod
    def enterprise_client_row_to_item(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "name": row.get("name") or "",
            "clientCode": row.get("client_code"),
            "taxId": row.get("tax_id"),
            "billingAddress": row.get("billing_address"),
            "contactName": row.get("contact_name"),
            "contactEmail": row.get("contact_email"),
            "contactPhone": row.get("contact_phone"),
            "planTier": row.get("plan_tier") or "plus",
            "unitPriceTwd": row.get("unit_price_twd") or 0,
            "contractStart": row.get("contract_start"),
            "contractEnd": row.get("contract_end"),
            "seatQuota": row.get("seat_quota") or 0,
            "status": row.get("status") or "active",
            "reportRecipients": row.get("report_recipients") or [],
            "notes": row.get("notes"),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    def load_enterprise_seats(self, client_id=None, status=None, account_id=None, invite_email=None, limit=2000):
        if not self.enabled():
            return None
        limit = max(1, min(5000, int(limit or 2000)))
        filters = {"select": "*", "order": "created_at.asc", "limit": str(limit)}
        if client_id:
            filters["enterprise_client_id"] = f"eq.{client_id}"
        if status:
            filters["status"] = f"eq.{status}"
        if account_id:
            filters["account_id"] = f"eq.{account_id}"
        if invite_email:
            filters["invite_email"] = f"ilike.{invite_email}"
        rows = self._select("enterprise_seats", filters)
        return [self.enterprise_seat_row_to_item(row) for row in rows or []]

    def get_enterprise_seat(self, seat_id):
        if not self.enabled() or not self._is_uuid(seat_id or ""):
            return None
        row = self._first("enterprise_seats", {"id": f"eq.{seat_id}", "select": "*"})
        return self.enterprise_seat_row_to_item(row) if row else None

    def create_enterprise_seat(self, seat):
        if not self.enabled():
            return None
        payload = self.enterprise_seat_to_row(seat)
        rows = self._request("POST", "enterprise_seats", query={"select": "*"}, payload=payload, prefer="return=representation")
        return self.enterprise_seat_row_to_item(rows[0]) if rows else None

    def update_enterprise_seat(self, seat_id, patch):
        """局部更新一筆席次（狀態流轉／綁定帳號用）。patch 已是 snake_case 欄位，只送有值的欄位。"""
        if not self.enabled() or not seat_id:
            return None
        rows = self._request(
            "PATCH", "enterprise_seats",
            query={"id": f"eq.{seat_id}", "select": "*"},
            payload=patch, prefer="return=representation",
        )
        return self.enterprise_seat_row_to_item(rows[0]) if rows else None

    def enterprise_seat_to_row(self, seat):
        seat = seat or {}
        return {
            "enterprise_client_id": seat.get("enterpriseClientId") or seat.get("enterprise_client_id"),
            "invite_email": str(seat.get("inviteEmail") or seat.get("invite_email") or "").strip().lower(),
            "account_id": seat.get("accountId") or seat.get("account_id"),
            "status": seat.get("status") or "pending",
            "activated_at": seat.get("activatedAt") or seat.get("activated_at"),
            "waiting_until": seat.get("waitingUntil") or seat.get("waiting_until"),
            "grace_started_at": seat.get("graceStartedAt") or seat.get("grace_started_at"),
            "grace_until": seat.get("graceUntil") or seat.get("grace_until"),
            "released_at": seat.get("releasedAt") or seat.get("released_at"),
            "released_reason": seat.get("releasedReason") or seat.get("released_reason"),
            "notes": seat.get("notes"),
        }

    @staticmethod
    def enterprise_seat_row_to_item(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "enterpriseClientId": row.get("enterprise_client_id") or "",
            "inviteEmail": row.get("invite_email") or "",
            "accountId": row.get("account_id"),
            "status": row.get("status") or "pending",
            "activatedAt": row.get("activated_at"),
            "waitingUntil": row.get("waiting_until"),
            "graceStartedAt": row.get("grace_started_at"),
            "graceUntil": row.get("grace_until"),
            "releasedAt": row.get("released_at"),
            "releasedReason": row.get("released_reason"),
            "notes": row.get("notes"),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    def append_enterprise_seat_event(self, event):
        if not self.enabled():
            return None
        payload = self.enterprise_seat_event_to_row(event)
        rows = self._request("POST", "enterprise_seat_events", query={"select": "*"}, payload=payload, prefer="return=representation")
        return self.enterprise_seat_event_row_to_item(rows[0]) if rows else None

    def load_enterprise_seat_events(self, seat_id=None, limit=500):
        if not self.enabled():
            return None
        limit = max(1, min(2000, int(limit or 500)))
        filters = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
        if seat_id:
            filters["seat_id"] = f"eq.{seat_id}"
        rows = self._select("enterprise_seat_events", filters)
        return [self.enterprise_seat_event_row_to_item(row) for row in rows or []]

    def enterprise_seat_event_to_row(self, event):
        event = event or {}
        return {
            "seat_id": event.get("seatId") or event.get("seat_id"),
            "from_status": event.get("fromStatus") or event.get("from_status"),
            "to_status": event.get("toStatus") or event.get("to_status"),
            "actor": event.get("actor") or "admin",
            "reason": event.get("reason"),
            "metadata": event.get("metadata") or {},
        }

    @staticmethod
    def enterprise_seat_event_row_to_item(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "seatId": row.get("seat_id") or "",
            "fromStatus": row.get("from_status"),
            "toStatus": row.get("to_status") or "",
            "actor": row.get("actor") or "admin",
            "reason": row.get("reason"),
            "metadata": row.get("metadata") or {},
            "createdAt": row.get("created_at"),
        }

    def insert_enterprise_subscription_grant(self, payload):
        """企業席次授予會員資格：直接寫一筆 subscription_ledger（provider='enterprise'）。
        grant_ref 必填的鐵律由呼叫端 engine/enterprise_seats.py 的
        validate_subscription_grant_ref() 先擋，這裡只負責落地——資料庫另有
        subscription_ledger_enterprise_requires_grant_ref check constraint 當最後一道防線。"""
        if not self.enabled():
            return None
        rows = self._request(
            "POST", "subscription_ledger",
            query={"select": "*"},
            payload=payload, prefer="return=representation",
        )
        return rows[0] if rows else None

    def get_latest_subscription_ledger(self, account_id):
        """讀一個帳號目前最新一筆 subscription_ledger（依 updated_at desc 取第一筆）。
        不依賴 self.account_id／self.identity（呼叫端通常是後台操作某個席次綁定的帳號，
        不是目前這個 request 本人的帳號）。企業席次鐵律 3『不得重複授予』用這個判斷
        該帳號現有的個人（非企業）訂閱等級。"""
        if not self.enabled() or not self._is_uuid(account_id or ""):
            return None
        return self._first("subscription_ledger", {
            "account_id": f"eq.{account_id}",
            "select": "*",
            "order": "updated_at.desc",
        })

    def get_subscription_ledger_by_grant_ref(self, grant_ref):
        """依 grant_ref（= enterprise_seats.id）查是否已經授予過——避免同一席次重插兩筆
        subscription_ledger（鐵律 3『不得重複授予』的 idempotent 防線）。"""
        if not self.enabled() or not self._is_uuid(grant_ref or ""):
            return None
        return self._first("subscription_ledger", {
            "grant_ref": f"eq.{grant_ref}",
            "select": "*",
            "order": "updated_at.desc",
        })

    def load_enterprise_invoices(self, client_id=None, limit=200):
        """唯讀：企業請款單清單／單一公司請款單。寫入（產出請款單、標已寄出／已入帳）
        屬 engine/enterprise_billing.py 的責任，這裡只給 enterprise_seats.py 的鐵律 2
        『未付款不得開通』守門查詢用，以及後台『單一公司明細』顯示收款紀錄用。"""
        if not self.enabled():
            return None
        limit = max(1, min(500, int(limit or 200)))
        filters = {"select": "*", "order": "period_start.desc", "limit": str(limit)}
        if client_id:
            filters["enterprise_client_id"] = f"eq.{client_id}"
        rows = self._select("enterprise_invoices", filters)
        return [self.enterprise_invoice_row_to_item(row) for row in rows or []]

    @staticmethod
    def enterprise_invoice_row_to_item(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "invoiceNo": row.get("invoice_no") or "",
            "enterpriseClientId": row.get("enterprise_client_id") or "",
            "periodStart": row.get("period_start"),
            "periodEnd": row.get("period_end"),
            "billableSeats": row.get("billable_seats") or 0,
            "unitPriceTwd": row.get("unit_price_twd") or 0,
            "subtotalTwd": row.get("subtotal_twd") or 0,
            "taxTwd": row.get("tax_twd") or 0,
            "totalTwd": row.get("total_twd") or 0,
            "status": row.get("status") or "draft",
            "dueDate": row.get("due_date"),
            "seatSnapshot": row.get("seat_snapshot") or [],
            "reportRef": row.get("report_ref"),
            "sentAt": row.get("sent_at"),
            "paidAt": row.get("paid_at"),
            "paidAmountTwd": row.get("paid_amount_twd"),
            "paymentNote": row.get("payment_note"),
            "invoiceNumber": row.get("invoice_number"),
            "invoiceIssuedAt": row.get("invoice_issued_at"),
            # 2026-07-20 三次需求：請款單一旦寄出（issued）就把畫面凍結存這欄，
            # 之後重下載一律回這份原樣，不看之後改過的開票／收款設定
            # （見 engine/enterprise_billing.py 的 get_invoice_html() 決策理由）。
            "invoiceHtmlSnapshot": row.get("invoice_html_snapshot"),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    # ── ESG 成效月報存檔（2026-07-20 三次需求：接通「月報與請款單下載」）──
    # 讀寫入口見 engine/enterprise_billing.py 的 save_report()／list_reports()／
    # get_report()——這裡只是薄薄一層 row↔item 轉換，跟其餘 enterprise_* 方法同一個分層原則。
    # 月報一算完就整份凍結存檔（原始數據 jsonb ＋ 渲染好的 HTML 一起存），之後下載
    # 一律回這份存檔的原樣，不即時重算（理由見 enterprise_billing.py 的 save_report() docstring）。

    def load_enterprise_reports(self, client_id=None, limit=200):
        if not self.enabled():
            return None
        limit = max(1, min(500, int(limit or 200)))
        filters = {"select": "*", "order": "period_start.desc", "limit": str(limit)}
        if client_id:
            filters["enterprise_client_id"] = f"eq.{client_id}"
        rows = self._select("enterprise_reports", filters)
        return [self.enterprise_report_row_to_item(row) for row in rows or []]

    def get_enterprise_report(self, report_id):
        if not self.enabled() or not self._is_uuid(report_id or ""):
            return None
        row = self._first("enterprise_reports", {"id": f"eq.{report_id}", "select": "*"})
        return self.enterprise_report_row_to_item(row) if row else None

    def save_enterprise_report(self, item):
        """同一家公司同一帳單期間重跑月結＝覆蓋舊報告（on_conflict 對齊
        022_enterprise_documents.sql 的 enterprise_reports_client_period_uidx），
        不會累積出好幾份同期間的報告混淆下載清單。"""
        if not self.enabled():
            return None
        payload = self.enterprise_report_to_row(item)
        report_id = item.get("id")
        if report_id and self._is_uuid(report_id):
            payload["id"] = report_id
        rows = self._request(
            "POST", "enterprise_reports",
            query={"on_conflict": "enterprise_client_id,period_start", "select": "*"},
            payload=payload, prefer="resolution=merge-duplicates,return=representation",
        )
        return self.enterprise_report_row_to_item(rows[0]) if rows else None

    @staticmethod
    def enterprise_report_to_row(item):
        item = item or {}
        return {
            "enterprise_client_id": item.get("enterpriseClientId"),
            "invoice_id": item.get("invoiceId"),
            "period_start": item.get("periodStart"),
            "period_end": item.get("periodEnd"),
            "report_data": item.get("reportData") or {},
            "report_html": item.get("reportHtml") or "",
            "generated_at": item.get("generatedAt"),
        }

    @staticmethod
    def enterprise_report_row_to_item(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "enterpriseClientId": row.get("enterprise_client_id") or "",
            "invoiceId": row.get("invoice_id"),
            "periodStart": row.get("period_start"),
            "periodEnd": row.get("period_end"),
            "reportData": row.get("report_data") or {},
            "reportHtml": row.get("report_html") or "",
            "generatedAt": row.get("generated_at"),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    # ── 開票／收款設定（單列表 · 2026-07-20 二次需求）──
    # 讀取入口見 engine/enterprise_seats.py 的 get_billing_settings()／
    # save_billing_settings()；enterprise_billing.py 產請款單時要呼叫那兩個函式，
    # 不直接呼叫這裡（跟其餘 enterprise_* 方法同一個分層原則）。

    def get_enterprise_billing_settings(self):
        if not self.enabled():
            return None
        row = self._first("enterprise_billing_settings", {"select": "*", "limit": "1"})
        return self.enterprise_billing_settings_row_to_item(row) if row else {}

    def save_enterprise_billing_settings(self, settings):
        """單列表用 on_conflict=singleton 做 upsert——第一次寫是 insert，
        之後每次存都是同一列覆寫，不會累積多筆。"""
        if not self.enabled():
            return None
        payload = self.enterprise_billing_settings_to_row(settings)
        payload["singleton"] = True
        rows = self._request(
            "POST", "enterprise_billing_settings",
            query={"on_conflict": "singleton", "select": "*"},
            payload=payload, prefer="resolution=merge-duplicates,return=representation",
        )
        return self.enterprise_billing_settings_row_to_item(rows[0]) if rows else None

    @staticmethod
    def enterprise_billing_settings_to_row(settings):
        settings = settings or {}
        return {
            "issuer_company_name": settings.get("issuerCompanyName") or settings.get("issuer_company_name"),
            "issuer_tax_id": settings.get("issuerTaxId") or settings.get("issuer_tax_id"),
            "issuer_address": settings.get("issuerAddress") or settings.get("issuer_address"),
            "issuer_phone": settings.get("issuerPhone") or settings.get("issuer_phone"),
            "issuer_contact_name": settings.get("issuerContactName") or settings.get("issuer_contact_name"),
            "bank_name": settings.get("bankName") or settings.get("bank_name"),
            "bank_branch": settings.get("bankBranch") or settings.get("bank_branch"),
            "bank_account_name": settings.get("bankAccountName") or settings.get("bank_account_name"),
            "bank_account_no": settings.get("bankAccountNo") or settings.get("bank_account_no"),
            "payment_terms_days": int(settings.get("paymentTermsDays") or settings.get("payment_terms_days") or 15),
            "invoice_footer_note": settings.get("invoiceFooterNote") or settings.get("invoice_footer_note"),
            "updated_by": settings.get("updatedBy") or settings.get("updated_by"),
        }

    @staticmethod
    def enterprise_billing_settings_row_to_item(row):
        row = row or {}
        return {
            "issuerCompanyName": row.get("issuer_company_name"),
            "issuerTaxId": row.get("issuer_tax_id"),
            "issuerAddress": row.get("issuer_address"),
            "issuerPhone": row.get("issuer_phone"),
            "issuerContactName": row.get("issuer_contact_name"),
            "bankName": row.get("bank_name"),
            "bankBranch": row.get("bank_branch"),
            "bankAccountName": row.get("bank_account_name"),
            "bankAccountNo": row.get("bank_account_no"),
            "paymentTermsDays": row.get("payment_terms_days") or 15,
            "invoiceFooterNote": row.get("invoice_footer_note"),
            "updatedAt": row.get("updated_at"),
            "updatedBy": row.get("updated_by"),
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
                "auth_user_id": auth_user_id,
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
                    "realtimeAvatar": True,
                    "premiumAvatarMinutesMonthly": 0,
                    "familyMembersMax": 1,
                },
                "usageLedger": {
                    "period": time.strftime("%Y-%m"),
                    "voiceMinutesUsed": 0,
                    "voiceMinutesGranted": 5,
                    "avatarMinutesUsed": 0,
                    "avatarMinutesGranted": 0,
                    "familyMembersUsed": 1,
                    "familyMembersGranted": 1,
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

    def grant_free_signup_trial(self):
        """Atomically grant the one-time account signup trial in Postgres."""
        result = self._request(
            "POST",
            "rpc/munea_grant_free_signup_trial",
            payload={
                "p_account_id": self.account_id,
                "p_person_id": self.person_id if self._is_uuid(self.person_id) else None,
            },
        )
        return result or {}

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
        if payload["status"] == "completed":
            payload["completed_at"] = data.get("completedAt") or data.get("completed_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rows = self._request(
            "POST",
            "privacy_requests",
            query={"select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        return self.privacy_row_to_request(rows[0]) if rows else None

    def load_routine_reminders(self, person_id=None, status=None, limit=100):
        if not self.enabled():
            return None
        person_id = person_id if self._is_uuid(person_id or "") else self.person_id
        query = {
            "account_id": f"eq.{self.account_id}",
            "person_id": f"eq.{person_id}",
            "select": "*",
            "order": "updated_at.desc",
            "limit": str(limit or 100),
        }
        if status:
            query["status"] = f"eq.{status}"
        rows = self._select("routine_reminders", query)
        return [self.routine_reminder_row_to_item(row) for row in rows or []]

    def save_routine_reminder(self, item):
        if not self.enabled():
            return None
        payload = self.routine_reminder_to_row(item)
        reminder_id = (item or {}).get("id")
        rows = None
        if self._is_uuid(reminder_id or ""):
            rows = self._request(
                "PATCH",
                "routine_reminders",
                query={"id": f"eq.{reminder_id}", "select": "*"},
                payload=payload,
                prefer="return=representation",
            )
        elif reminder_id:
            rows = self._request(
                "PATCH",
                "routine_reminders",
                query={
                    "account_id": f"eq.{self.account_id}",
                    "schedule->>originalReminderId": f"eq.{reminder_id}",
                    "select": "*",
                },
                payload=payload,
                prefer="return=representation",
            )
        if not rows:
            rows = self._request(
                "POST",
                "routine_reminders",
                query={"select": "*"},
                payload=payload,
                prefer="return=representation",
            )
        return self.routine_reminder_row_to_item(rows[0]) if rows else None

    def update_routine_reminder(self, reminder_id, patch):
        if not self.enabled() or not reminder_id:
            return None
        query = {"id": f"eq.{reminder_id}", "select": "*"}
        if not self._is_uuid(reminder_id or ""):
            query = {
                "account_id": f"eq.{self.account_id}",
                "schedule->>originalReminderId": f"eq.{reminder_id}",
                "select": "*",
            }
        payload = self.routine_reminder_patch_to_row(patch)
        if not payload:
            return self.routine_reminder_row_to_item(
                self._first("routine_reminders", query)
            )
        if "schedule" in payload:
            current_query = {**query, "select": "schedule"}
            current = self._first("routine_reminders", current_query)
            payload["schedule"] = {**((current or {}).get("schedule") or {}), **(payload.get("schedule") or {})}
        rows = self._request(
            "PATCH",
            "routine_reminders",
            query=query,
            payload=payload,
            prefer="return=representation",
        )
        return self.routine_reminder_row_to_item(rows[0]) if rows else None

    def load_medication_doses(self, person_id=None, start_date=None, end_date=None, limit=1000):
        if not self.enabled():
            return None
        person_id = person_id if self._is_uuid(person_id or "") else self.person_id
        query = {
            "account_id": f"eq.{self.account_id}",
            "person_id": f"eq.{person_id}",
            "select": "*",
            "order": "scheduled_date.desc,updated_at.desc",
            "limit": str(max(1, min(5000, int(limit or 1000)))),
        }
        if start_date:
            query["scheduled_date"] = f"gte.{str(start_date)[:10]}"
        if end_date:
            # PostgREST cannot express both bounds with one dict key, so the
            # upper bound is applied after the account/person-scoped query.
            query["and"] = f"(scheduled_date.lte.{str(end_date)[:10]})"
        rows = self._select("medication_dose_events", query)
        return [self.medication_dose_row_to_item(row) for row in rows or []]

    def save_medication_dose(self, item):
        if not self.enabled():
            return None
        payload = self.medication_dose_to_row(item)
        rows = self._request(
            "POST",
            "medication_dose_events",
            query={"on_conflict": "account_id,person_id,dose_key", "select": "*"},
            payload=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        return self.medication_dose_row_to_item(rows[0]) if rows else None

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

    def load_audit_events(self, limit=100):
        if not self.enabled():
            return None
        rows = self._request(
            "GET",
            "audit_events",
            query={
                "account_id": f"eq.{self.account_id}",
                "select": "*",
                "order": "created_at.desc",
                "limit": str(limit or 100),
            },
        )
        return [self.audit_row_to_event(row) for row in rows or []]

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

    def load_conversation_summaries(self, query=None, limit=100):
        if not self.enabled():
            return None
        query = query or {}
        filters = {
            "account_id": f"eq.{self.account_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit or 100),
        }
        person_id = query.get("personId") or query.get("person_id")
        if person_id:
            person_id = person_id if self._is_uuid(person_id or "") else self.person_id
            filters["person_id"] = f"eq.{person_id}"
        if not (query.get("includeDeleted") or query.get("include_deleted")):
            filters["deleted_at"] = "is.null"
        rows = self._select("conversation_summaries", filters)
        return [self.conversation_summary_row_to_item(row) for row in rows]

    def save_conversation_summary(self, item):
        if not self.enabled():
            return None
        rows = self._request(
            "POST",
            "conversation_summaries",
            query={"select": "*"},
            payload=self.conversation_summary_to_row(item),
            prefer="return=representation",
        )
        return self.conversation_summary_row_to_item(rows[0]) if rows else None

    def soft_delete_conversation_summary(self, summary_id, deleted_at):
        if not self.enabled():
            return None
        rows = self._request(
            "PATCH",
            "conversation_summaries",
            query={
                "id": f"eq.{summary_id}",
                "account_id": f"eq.{self.account_id}",
                "select": "*",
            },
            payload={"deleted_at": deleted_at},
            prefer="return=representation",
        )
        return self.conversation_summary_row_to_item(rows[0]) if rows else None

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
                "family_group_id": f"eq.{family_group_id}",
                "select": "*",
                "order": "updated_at.desc",
            },
        )
        return self.family_state_rows_to_store(rows)

    def save_family_state_entry(self, key, value, family_group_id=None, updated_by_person_id=None):
        if not self.enabled():
            return None
        family_group_id = family_group_id or self.family_group_id
        family_account_id = self.family_group_account_id(family_group_id)
        if not self._is_uuid(family_account_id or ""):
            return None
        payload = {
            "account_id": family_account_id,
            "family_group_id": family_group_id,
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

    def family_group_account_id(self, family_group_id):
        if not self._is_uuid(family_group_id or ""):
            return None
        if family_group_id == self.family_group_id:
            row = self._first("family_groups", {"id": f"eq.{family_group_id}", "select": "account_id"})
        else:
            row = self._first("family_groups", {"id": f"eq.{family_group_id}", "select": "account_id"})
        return (row or {}).get("account_id")

    def load_family_invitations(self, family_group_id=None, status=None, limit=100):
        if not self.enabled():
            return None
        family_group_id = family_group_id if self._is_uuid(family_group_id or "") else self.family_group_id
        query = {
            "account_id": f"eq.{self.account_id}",
            "family_group_id": f"eq.{family_group_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit or 100),
        }
        if status:
            query["status"] = f"eq.{status}"
        rows = self._select("family_invitations", query)
        return [self.family_invitation_row_to_invitation(row) for row in rows or []]

    def find_pending_family_invitation_by_short_code(self, short_code):
        """Server-only lookup for the one-time join-code exchange.

        This deliberately does not use the caller's account scope: the applicant
        belongs to a different account until the exchange succeeds.  It returns
        only an exact, still-pending code and is called only after authentication
        and entitlement checks in server.py.
        """
        if not self.enabled() or not (len(str(short_code or "")) == 6 and str(short_code).isdigit()):
            return None
        rows = self._select("family_invitations", {
            "short_code": f"eq.{short_code}",
            "status": "eq.pending",
            "select": "*",
            "limit": "2",
        })
        if len(rows or []) != 1:
            return None
        return self.family_invitation_row_to_invitation(rows[0])

    def update_family_invitation_by_id_unscoped(self, invitation_id, patch):
        """Server-only mutation paired with exact-code lookup above."""
        if not self.enabled() or not self._is_uuid(invitation_id or ""):
            return None
        payload = self.family_invitation_patch_to_row(patch)
        if not payload:
            return self.family_invitation_row_to_invitation(
                self._first("family_invitations", {"id": f"eq.{invitation_id}", "select": "*"})
            )
        rows = self._request(
            "PATCH",
            "family_invitations",
            query={"id": f"eq.{invitation_id}", "select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        return self.family_invitation_row_to_invitation(rows[0]) if rows else None

    def load_family_circle_unscoped(self, family_group_id):
        """Read the server-owned member roster for a capacity check."""
        if not self.enabled() or not self._is_uuid(family_group_id or ""):
            return None
        rows = self._select("family_state_entries", {
            "family_group_id": f"eq.{family_group_id}",
            "state_key": "eq.circle",
            "select": "*",
            "limit": "1",
        })
        if not rows:
            return []
        value = rows[0].get("value")
        return value if isinstance(value, list) else []

    def count_family_members_unscoped(self, family_group_id):
        if not self.enabled() or not self._is_uuid(family_group_id or ""):
            return None
        rows = self._select("family_memberships", {
            "family_group_id": f"eq.{family_group_id}",
            "select": "id",
            "limit": "100",
        })
        return len(rows or [])

    def add_family_member_after_invitation_unscoped(self, family_group_id, person_id):
        """Attach the authenticated invitee to the inviter's group exactly once."""
        if not self.enabled() or not self._is_uuid(family_group_id or "") or not self._is_uuid(person_id or ""):
            return None
        group = self._first("family_groups", {"id": f"eq.{family_group_id}", "select": "account_id"}) or {}
        account_id = group.get("account_id")
        if not self._is_uuid(account_id or ""):
            return None
        existing = self._first("family_memberships", {
            "family_group_id": f"eq.{family_group_id}",
            "person_id": f"eq.{person_id}",
            "select": "*",
        })
        if existing:
            return self.family_membership_row_to_member(existing)
        rows = self._request(
            "POST",
            "family_memberships",
            query={"select": "*"},
            payload={
                "account_id": account_id,
                "family_group_id": family_group_id,
                "person_id": person_id,
                "role": "family_contact",
                "permissions": {"familyCircleMember": True, "view_family_dashboard": True},
            },
            prefer="return=representation",
        )
        return self.family_membership_row_to_member(rows[0]) if rows else None

    def remove_external_family_memberships_for_account_unscoped(self, account_id):
        """Remove an expired subscriber from circles owned by other accounts."""
        if not self.enabled() or not self._is_uuid(account_id or ""):
            return 0
        people = self._select("persons", {"account_id": f"eq.{account_id}", "select": "id"})
        removed = 0
        for person in people or []:
            person_id = person.get("id")
            if not self._is_uuid(person_id or ""):
                continue
            memberships = self._select("family_memberships", {"person_id": f"eq.{person_id}", "select": "*"})
            for membership in memberships or []:
                # Preserve the member's own circle.  Cross-account rows are
                # created only by the accepted-invitation flow.
                if membership.get("account_id") == account_id:
                    continue
                self._request(
                    "DELETE", "family_memberships",
                    query={"id": f"eq.{membership.get('id')}", "select": "id"},
                    prefer="return=representation",
                )
                removed += 1
        return removed

    def create_family_invitation(self, invitation):
        if not self.enabled():
            return None
        payload = self.family_invitation_to_row(invitation)
        rows = self._request(
            "POST",
            "family_invitations",
            query={"select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        return self.family_invitation_row_to_invitation(rows[0]) if rows else None

    def update_family_invitation(self, invitation_id, patch):
        if not self.enabled() or not self._is_uuid(invitation_id or ""):
            return None
        payload = self.family_invitation_patch_to_row(patch)
        if not payload:
            return self.family_invitation_row_to_invitation(
                self._first("family_invitations", {"id": f"eq.{invitation_id}", "select": "*"})
            )
        rows = self._request(
            "PATCH",
            "family_invitations",
            query={"id": f"eq.{invitation_id}", "select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        return self.family_invitation_row_to_invitation(rows[0]) if rows else None

    def load_consent_records(self, person_id=None, consent_type=None, status=None, limit=100):
        if not self.enabled():
            return None
        person_id = person_id if self._is_uuid(person_id or "") else self.person_id
        query = {
            "account_id": f"eq.{self.account_id}",
            "person_id": f"eq.{person_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit or 100),
        }
        if consent_type:
            query["consent_type"] = f"eq.{consent_type}"
        if status:
            query["status"] = f"eq.{status}"
        rows = self._select("consent_records", query)
        return [self.consent_record_row_to_record(row) for row in rows or []]

    def append_consent_record(self, record):
        if not self.enabled():
            return None
        payload = self.consent_record_to_row(record)
        rows = self._request(
            "POST",
            "consent_records",
            query={"select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        return self.consent_record_row_to_record(rows[0]) if rows else None

    def revoke_consent_record(self, record_id=None, person_id=None, consent_type=None, patch=None):
        if not self.enabled():
            return None
        target_id = record_id if self._is_uuid(record_id or "") else None
        if not target_id:
            lookup_person_id = person_id if self._is_uuid(person_id or "") else self.person_id
            query = {
                "account_id": f"eq.{self.account_id}",
                "person_id": f"eq.{lookup_person_id}",
                "status": "eq.granted",
                "select": "*",
                "order": "created_at.desc",
                "limit": "1",
            }
            if consent_type:
                query["consent_type"] = f"eq.{consent_type}"
            rows = self._select("consent_records", query)
            target_id = (rows[0] or {}).get("id") if rows else None
        if not target_id:
            return None
        payload = self.consent_record_revoke_patch_to_row(patch or {})
        rows = self._request(
            "PATCH",
            "consent_records",
            query={"id": f"eq.{target_id}", "select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        return self.consent_record_row_to_record(rows[0]) if rows else None

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

    def load_family_activities(self, family_group_id=None, status=None, limit=100):
        if not self.enabled():
            return None
        family_group_id = family_group_id if self._is_uuid(family_group_id or "") else self.family_group_id
        query = {
            "account_id": f"eq.{self.account_id}",
            "family_group_id": f"eq.{family_group_id}",
            "select": "*",
            "order": "updated_at.desc",
            "limit": str(limit or 100),
        }
        if status:
            query["status"] = f"eq.{status}"
        rows = self._select("family_activities", query)
        activities = []
        for row in rows or []:
            participants = self._select(
                "family_activity_participants",
                {
                    "account_id": f"eq.{self.account_id}",
                    "family_activity_id": f"eq.{row.get('id')}",
                    "select": "*",
                    "order": "updated_at.desc",
                },
            )
            activities.append(self.family_activity_row_to_activity(row, participants=participants))
        return activities

    def save_family_activity(self, activity):
        if not self.enabled():
            return None
        payload = self.family_activity_to_row(activity)
        activity_id = (activity or {}).get("id")
        rows = None
        if self._is_uuid(activity_id or ""):
            rows = self._request(
                "PATCH",
                "family_activities",
                query={"id": f"eq.{activity_id}", "select": "*"},
                payload=payload,
                prefer="return=representation",
            )
        if not rows:
            rows = self._request(
                "POST",
                "family_activities",
                query={"select": "*"},
                payload=payload,
                prefer="return=representation",
            )
        saved = self.family_activity_row_to_activity(rows[0]) if rows else None
        for participant in (activity or {}).get("participants") or []:
            self.save_family_activity_participant((saved or {}).get("id"), participant)
        if saved:
            saved["participants"] = self.load_family_activity_participants(saved["id"])
        return saved

    def load_family_activity_participants(self, activity_id):
        if not self.enabled() or not self._is_uuid(activity_id or ""):
            return []
        rows = self._select(
            "family_activity_participants",
            {
                "account_id": f"eq.{self.account_id}",
                "family_activity_id": f"eq.{activity_id}",
                "select": "*",
                "order": "updated_at.desc",
            },
        )
        return [self.family_activity_participant_row_to_participant(row) for row in rows or []]

    def save_family_activity_participant(self, activity_id, participant):
        if not self.enabled() or not self._is_uuid(activity_id or ""):
            return None
        payload = self.family_activity_participant_to_row(activity_id, participant)
        person_id = payload["person_id"]
        rows = self._request(
            "PATCH",
            "family_activity_participants",
            query={"family_activity_id": f"eq.{activity_id}", "person_id": f"eq.{person_id}", "select": "*"},
            payload=payload,
            prefer="return=representation",
        )
        if not rows:
            rows = self._request(
                "POST",
                "family_activity_participants",
                query={"select": "*"},
                payload=payload,
                prefer="return=representation",
            )
        return self.family_activity_participant_row_to_participant(rows[0]) if rows else None

    def load_family_members(self, family_group_id=None, limit=100):
        if not self.enabled():
            return None
        family_group_id = self._resolve_family_group_id(family_group_id)
        if not self._is_uuid(family_group_id or ""):
            return None
        rows = self._select(
            "family_memberships",
            {
                "family_group_id": f"eq.{family_group_id}",
                "select": "*",
                "order": "updated_at.desc",
                "limit": str(limit or 100),
            },
        )
        return [self.family_membership_row_to_member(row) for row in rows or []]

    def _family_member_exists(self, family_group_id, person_id):
        if not self._is_uuid(family_group_id or "") or not self._is_uuid(person_id or ""):
            return False
        return bool(self._first("family_memberships", {
            "family_group_id": f"eq.{family_group_id}",
            "person_id": f"eq.{person_id}",
            "select": "id",
        }))

    def create_family_relay(self, relay):
        if not self.enabled() or not self.request_scoped:
            return None
        relay = relay or {}
        family_group_id = self._resolve_family_group_id(relay.get("familyGroupId") or relay.get("family_group_id"))
        recipient_person_id = relay.get("recipientPersonId") or relay.get("recipient_person_id")
        if not self.owns_family_group_id(family_group_id):
            raise PermissionError("family_relay_group_forbidden")
        if not self._family_member_exists(family_group_id, self.person_id):
            raise PermissionError("family_relay_sender_not_member")
        if not self._family_member_exists(family_group_id, recipient_person_id):
            raise PermissionError("family_relay_recipient_not_member")
        if recipient_person_id == self.person_id:
            raise ValueError("family_relay_recipient_self")
        sender_person = self._first("persons", {"id": f"eq.{self.person_id}", "select": "display_name,relationship"}) or {}
        recipient_person = self._first("persons", {"id": f"eq.{recipient_person_id}", "select": "display_name,relationship"}) or {}
        payload = self.family_relay_to_row({
            **relay,
            "accountId": self.family_group_account_id(family_group_id),
            "familyGroupId": family_group_id,
            "senderPersonId": self.person_id,
            "senderLabel": sender_person.get("display_name") or sender_person.get("relationship") or "家人",
            "recipientLabel": recipient_person.get("display_name") or recipient_person.get("relationship") or "家人",
            "status": "pending",
        })
        rows = self._request(
            "POST", "family_relay_messages", query={"select": "*"},
            payload=payload, prefer="return=representation",
        )
        return self.family_relay_row_to_relay(rows[0]) if rows else None

    def load_family_relays(self, direction="received", status=None, limit=50):
        if not self.enabled() or not self.request_scoped:
            return None
        query = {
            "family_group_id": f"eq.{self.family_group_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(max(1, min(100, int(limit or 50)))),
        }
        if direction == "sent":
            query["sender_person_id"] = f"eq.{self.person_id}"
        else:
            query["recipient_person_id"] = f"eq.{self.person_id}"
        if status:
            query["status"] = f"eq.{status}"
        rows = self._select("family_relay_messages", query)
        return [self.family_relay_row_to_relay(row) for row in rows or []]

    def claim_next_family_relay(self):
        if not self.enabled() or not self.request_scoped:
            return None
        # A force-quit can prevent the App from sending release. Requeue only
        # this recipient's old claim so one crashed call cannot strand it.
        stale_before = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 600))
        self._request(
            "PATCH", "family_relay_messages",
            query={
                "family_group_id": f"eq.{self.family_group_id}",
                "recipient_person_id": f"eq.{self.person_id}",
                "status": "eq.claimed", "claimed_at": f"lt.{stale_before}",
            },
            payload={"status": "pending", "claim_token": None, "claimed_at": None},
        )
        pending = self._select("family_relay_messages", {
            "family_group_id": f"eq.{self.family_group_id}",
            "recipient_person_id": f"eq.{self.person_id}",
            "status": "eq.pending",
            "expires_at": f"gt.{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
            "select": "*",
            "order": "created_at.asc",
            "limit": "1",
        })
        if not pending:
            return None
        relay_id = pending[0].get("id")
        token = str(uuid.uuid4())
        rows = self._request(
            "PATCH", "family_relay_messages",
            query={"id": f"eq.{relay_id}", "recipient_person_id": f"eq.{self.person_id}", "status": "eq.pending", "select": "*"},
            payload={"status": "claimed", "claim_token": token, "claimed_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())},
            prefer="return=representation",
        )
        return self.family_relay_row_to_relay(rows[0]) if rows else None

    def update_family_relay_status(self, relay_id, action, claim_token=None):
        if not self.enabled() or not self.request_scoped or not self._is_uuid(relay_id or ""):
            return None
        current = self._first("family_relay_messages", {"id": f"eq.{relay_id}", "select": "*"})
        if not current:
            return None
        is_sender = current.get("sender_person_id") == self.person_id
        is_recipient = current.get("recipient_person_id") == self.person_id
        if action == "cancel":
            if not is_sender or current.get("status") not in ("pending", "claimed"):
                raise PermissionError("family_relay_cancel_forbidden")
            patch = {"status": "cancelled", "cancelled_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        elif action == "report":
            if not is_recipient:
                raise PermissionError("family_relay_report_forbidden")
            patch = {"status": "reported"}
        elif action in ("ack", "release"):
            if not is_recipient or current.get("status") != "claimed" or not claim_token or current.get("claim_token") != claim_token:
                raise PermissionError("family_relay_claim_forbidden")
            patch = ({"status": "delivered", "delivered_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
                     if action == "ack" else {"status": "pending", "claim_token": None, "claimed_at": None})
        else:
            raise ValueError("family_relay_action_invalid")
        rows = self._request(
            "PATCH", "family_relay_messages",
            query={"id": f"eq.{relay_id}", "select": "*"}, payload=patch, prefer="return=representation",
        )
        return self.family_relay_row_to_relay(rows[0]) if rows else None

    def load_notification_settings(self, person_id=None):
        """通知中心設定（migration 017）。沒存過回 None（上層套預設值）。"""
        if not self.enabled():
            return None
        person = person_id if self._is_uuid(person_id) else self.person_id
        if not self._is_uuid(person):
            return None
        row = self._first("notification_settings",
                          {"person_id": f"eq.{person}", "select": "*"})
        if not row:
            return None
        return {
            "personId": row.get("person_id"),
            "pushEnabled": bool(row.get("push_enabled")),
            "categories": row.get("categories") or {},
            "updatedAt": row.get("updated_at"),
        }

    def save_notification_settings(self, settings):
        if not self.enabled():
            return None
        settings = settings or {}
        person = settings.get("personId") or settings.get("person_id")
        if not self._is_uuid(person):
            person = self.person_id
        if not self._is_uuid(person):
            return None
        payload = {
            "person_id": person,
            "push_enabled": bool(settings.get("pushEnabled")),
            "categories": settings.get("categories") or {},
            "updated_at": settings.get("updatedAt")
            or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        rows = self._request(
            "POST", "notification_settings",
            query={"select": "*", "on_conflict": "person_id"},
            payload=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        row = rows[0] if rows else payload
        return {
            "personId": row.get("person_id"),
            "pushEnabled": bool(row.get("push_enabled")),
            "categories": row.get("categories") or {},
            "updatedAt": row.get("updated_at"),
        }

    def load_push_devices(self, include_invalid=False, limit=20):
        if not self.enabled() or not self.request_scoped:
            return None
        query = {
            "account_id": f"eq.{self.account_id}",
            "person_id": f"eq.{self.person_id}",
            "select": "*",
            "order": "last_seen_at.desc",
            "limit": str(max(1, min(int(limit or 20), 100))),
        }
        if not include_invalid:
            query["invalidated_at"] = "is.null"
        rows = self._select("push_devices", query)
        return [self.push_device_row_to_device(row) for row in rows or []]

    def upsert_push_device(self, device):
        if not self.enabled() or not self.request_scoped:
            return None
        payload = self.push_device_to_row(device)
        if not payload.get("token") or not payload.get("token_hash"):
            raise ValueError("push_token_invalid")
        existing = self._first("push_devices", {
            "token_hash": f"eq.{payload['token_hash']}",
            "environment": f"eq.{payload['environment']}",
            "bundle_id": f"eq.{payload['bundle_id']}",
            "select": "*",
        })
        rows = None
        if existing:
            rows = self._request(
                "PATCH", "push_devices",
                query={"id": f"eq.{existing.get('id')}", "select": "*"},
                payload={**payload, "invalidated_at": None},
                prefer="return=representation",
            )
        if not rows:
            rows = self._request(
                "POST", "push_devices", query={"select": "*"}, payload=payload,
                prefer="return=representation",
            )
        return self.push_device_row_to_device(rows[0]) if rows else None

    def disable_push_device(self, device_id=None, token_hash=None):
        if not self.enabled() or not self.request_scoped:
            return None
        query = {
            "account_id": f"eq.{self.account_id}",
            "person_id": f"eq.{self.person_id}",
            "select": "*",
        }
        if self._is_uuid(device_id or ""):
            query["id"] = f"eq.{device_id}"
        elif token_hash:
            query["token_hash"] = f"eq.{token_hash}"
        else:
            raise ValueError("push_device_id_required")
        rows = self._request(
            "PATCH", "push_devices", query=query,
            payload={
                "notifications_enabled": False,
                "invalidated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            },
            prefer="return=representation",
        )
        return self.push_device_row_to_device(rows[0]) if rows else None

    def enqueue_notification_event(self, event):
        if not self.enabled():
            return None
        payload = self.notification_event_to_rpc(event)
        rows = self._request(
            "POST", "rpc/enqueue_notification_event", payload=payload,
            prefer="return=representation",
        )
        if isinstance(rows, dict):
            return self.notification_event_row_to_event(rows)
        return self.notification_event_row_to_event(rows[0]) if rows else None

    def load_notification_events(self, unread_only=False, include_archived=False, event_type=None, limit=100):
        if not self.enabled() or not self.request_scoped:
            return None
        query = {
            "account_id": f"eq.{self.account_id}",
            "recipient_person_id": f"eq.{self.person_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(max(1, min(int(limit or 100), 500))),
        }
        if unread_only:
            query["read_at"] = "is.null"
        if not include_archived:
            query["archived_at"] = "is.null"
        if event_type:
            query["event_type"] = f"eq.{event_type}"
        rows = self._select("notification_events", query)
        return [self.notification_event_row_to_event(row) for row in rows or []]

    def mark_notification_event(self, event_id, action):
        if not self.enabled() or not self.request_scoped or not self._is_uuid(event_id or ""):
            return None
        current = self._first("notification_events", {
            "id": f"eq.{event_id}",
            "account_id": f"eq.{self.account_id}",
            "recipient_person_id": f"eq.{self.person_id}",
            "select": "*",
        })
        if not current:
            return None
        now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        if action == "read":
            patch = {"read_at": current.get("read_at") or now}
        elif action == "archive":
            patch = {"archived_at": current.get("archived_at") or now}
        elif action == "opened":
            patch = {"read_at": current.get("read_at") or now}
        elif action == "actioned":
            patch = {"read_at": current.get("read_at") or now, "acted_at": current.get("acted_at") or now}
        else:
            raise ValueError("notification_action_invalid")
        rows = self._request(
            "PATCH", "notification_events",
            query={"id": f"eq.{event_id}", "select": "*"},
            payload=patch, prefer="return=representation",
        )
        if action in ("opened", "actioned"):
            delivery_patch = {"status": action, f"{action}_at": now}
            self._request(
                "PATCH", "notification_deliveries",
                query={"event_id": f"eq.{event_id}"}, payload=delivery_patch,
                prefer="return=minimal",
            )
        return self.notification_event_row_to_event(rows[0]) if rows else None

    def claim_notification_deliveries(self, limit=50):
        if not self.enabled():
            return None
        rows = self._request(
            "POST", "rpc/claim_notification_deliveries",
            payload={"p_limit": max(1, min(int(limit or 50), 200))},
            prefer="return=representation",
        )
        return rows or []

    def complete_notification_delivery(self, delivery_id, status, apns_id=None,
                                       error_code=None, error_detail=None, retry_after_seconds=None):
        if not self.enabled() or not self._is_uuid(delivery_id or ""):
            return None
        payload = {
            "p_delivery_id": delivery_id,
            "p_status": status,
            "p_apns_id": apns_id,
            "p_error_code": error_code,
            "p_error_detail": error_detail,
            "p_retry_after_seconds": retry_after_seconds,
        }
        rows = self._request(
            "POST", "rpc/complete_notification_delivery", payload=payload,
            prefer="return=representation",
        )
        if isinstance(rows, dict):
            return rows
        return rows[0] if rows else None

    def save_family_member(self, member, family_group_id=None):
        if not self.enabled():
            return None
        member = member or {}
        family_group_id = self._resolve_family_group_id(family_group_id)
        if not self._is_uuid(family_group_id or ""):
            return None
        person_payload = self.family_member_to_person_row(member)
        member_id = member.get("id")
        existing = self._find_family_membership(member_id, family_group_id)
        person_id = (existing or {}).get("person_id") or (member_id if self._is_uuid(member_id or "") else None)
        if person_id:
            person_rows = self._request(
                "PATCH",
                "persons",
                query={"id": f"eq.{person_id}", "select": "*"},
                payload=person_payload,
                prefer="return=representation",
            )
            person = person_rows[0] if person_rows else self._first("persons", {"id": f"eq.{person_id}", "select": "*"})
        else:
            person_rows = self._request(
                "POST",
                "persons",
                query={"select": "*"},
                payload=person_payload,
                prefer="return=representation",
            )
            person = person_rows[0] if person_rows else None
            person_id = (person or {}).get("id")
        if not person_id:
            return None
        payload = self.family_member_to_membership_row(member, family_group_id, person_id)
        rows = None
        if existing:
            rows = self._request(
                "PATCH",
                "family_memberships",
                query={"id": f"eq.{existing.get('id')}", "select": "*"},
                payload=payload,
                prefer="return=representation",
            )
        if not rows:
            rows = self._request(
                "POST",
                "family_memberships",
                query={"select": "*"},
                payload=payload,
                prefer="return=representation",
            )
        return self.family_membership_row_to_member(rows[0], person=person) if rows else None

    def update_family_member(self, member_id, patch, family_group_id=None):
        if not self.enabled() or not member_id:
            return None
        family_group_id = self._resolve_family_group_id(family_group_id)
        existing = self._find_family_membership(member_id, family_group_id)
        if not existing:
            return None
        person_payload, membership_payload = self.family_member_patch_to_rows(patch)
        person = None
        if person_payload:
            person_rows = self._request(
                "PATCH",
                "persons",
                query={"id": f"eq.{existing.get('person_id')}", "select": "*"},
                payload=person_payload,
                prefer="return=representation",
            )
            person = person_rows[0] if person_rows else None
        if membership_payload:
            merged_permissions = {**(existing.get("permissions") or {}), **(membership_payload.get("permissions") or {})}
            membership_payload = {**membership_payload, "permissions": merged_permissions}
            rows = self._request(
                "PATCH",
                "family_memberships",
                query={"id": f"eq.{existing.get('id')}", "select": "*"},
                payload=membership_payload,
                prefer="return=representation",
            )
            existing = rows[0] if rows else existing
        return self.family_membership_row_to_member(existing, person=person)

    def remove_family_member(self, member_id, family_group_id=None):
        if not self.enabled() or not member_id:
            return None
        family_group_id = self._resolve_family_group_id(family_group_id)
        existing = self._find_family_membership(member_id, family_group_id)
        if not existing:
            return None
        person = self._first("persons", {"id": f"eq.{existing.get('person_id')}", "select": "*"})
        rows = self._request(
            "DELETE",
            "family_memberships",
            query={"id": f"eq.{existing.get('id')}", "select": "*"},
            prefer="return=representation",
        )
        return self.family_membership_row_to_member((rows or [existing])[0], person=person)

    def _resolve_family_group_id(self, family_group_id=None):
        if self._is_uuid(family_group_id or ""):
            return family_group_id
        if self._is_uuid(self.family_group_id or ""):
            return self.family_group_id
        family_group = self._load_family_group()
        return (family_group or {}).get("id")

    def _find_family_membership(self, member_id, family_group_id):
        if not self._is_uuid(family_group_id or "") or not member_id:
            return None
        query = {
            "account_id": f"eq.{self.account_id}",
            "family_group_id": f"eq.{family_group_id}",
            "select": "*",
            "limit": "1",
        }
        if self._is_uuid(member_id or ""):
            query["person_id"] = f"eq.{member_id}"
        else:
            query["permissions->>originalMemberId"] = f"eq.{member_id}"
        return self._first("family_memberships", query)

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
            members.append(self.family_membership_row_to_member(membership, person=person))
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

    def admin_account_rows_to_summary(self, account=None, family_group=None, primary_person=None, memberships=None, companion=None):
        account = account or {}
        family_group = family_group or {}
        primary_person = primary_person or {}
        memberships = memberships or []
        companion = companion or {}
        roles = {}
        for membership in memberships:
            role = membership.get("role") or "unknown"
            roles[role] = roles.get(role, 0) + 1
        return {
            "accountId": account.get("id") or "",
            "accountName": account.get("name") or "",
            "locale": account.get("locale") or "zh-TW",
            "preferredLanguages": account.get("preferred_languages") or ["zh-TW", "en"],
            "createdAt": account.get("created_at"),
            "updatedAt": account.get("updated_at"),
            "familyGroup": {
                "id": family_group.get("id") or "",
                "name": family_group.get("name") or "Munea Care Circle",
            },
            "primaryPerson": {
                "id": primary_person.get("id") or "",
                "displayName": primary_person.get("display_name") or "",
                "relationship": primary_person.get("relationship") or "self",
                "locale": primary_person.get("locale") or account.get("locale") or "zh-TW",
                "timezone": primary_person.get("timezone") or "Asia/Taipei",
            },
            "companion": {
                "templateId": companion.get("template_id") or "nening-real-female",
                "displayName": companion.get("display_name") or "Munea",
                "nameTouched": bool(companion.get("name_touched")),
            },
            "familyMembers": {
                "count": len(memberships),
                "byRole": dict(sorted(roles.items())),
            },
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

    @staticmethod
    def _normalize_family_member_role(role):
        allowed = {"primary_user", "family_contact", "caregiver", "viewer"}
        return role if role in allowed else "family_contact"

    def family_member_to_person_row(self, member):
        member = member or {}
        return {
            "account_id": self.payload_account_id(member.get("accountId") or member.get("account_id")),
            "display_name": (member.get("displayName") or member.get("display_name") or "Family member")[:80],
            "relationship": member.get("relationship") or "family",
            "locale": member.get("locale") or "zh-TW",
            "timezone": member.get("timezone") or "Asia/Taipei",
            "is_primary_care_recipient": bool(member.get("isPrimaryCareRecipient") or member.get("is_primary_care_recipient") or False),
        }

    def family_member_to_membership_row(self, member, family_group_id, person_id):
        member = member or {}
        permissions = dict(member.get("permissions") or {})
        member_id = member.get("id")
        if member_id and not self._is_uuid(member_id):
            permissions.setdefault("originalMemberId", member_id)
        return {
            "account_id": self.payload_account_id(member.get("accountId") or member.get("account_id")),
            "family_group_id": family_group_id,
            "person_id": person_id,
            "role": self._normalize_family_member_role(member.get("role")),
            "permissions": permissions,
        }

    def family_member_patch_to_rows(self, patch):
        patch = patch or {}
        person_payload = {}
        membership_payload = {}
        if any(key in patch for key in ("displayName", "display_name")):
            person_payload["display_name"] = (patch.get("displayName") or patch.get("display_name") or "Family member")[:80]
        if "relationship" in patch:
            person_payload["relationship"] = patch.get("relationship") or "family"
        if "role" in patch:
            membership_payload["role"] = self._normalize_family_member_role(patch.get("role"))
        if "permissions" in patch:
            membership_payload["permissions"] = patch.get("permissions") or {}
        return person_payload, membership_payload

    def family_membership_row_to_member(self, row, person=None):
        row = row or {}
        person = person or self._first("persons", {"id": f"eq.{row.get('person_id')}", "select": "*"}) or {}
        permissions = row.get("permissions") or {}
        return {
            "id": permissions.get("originalMemberId") or row.get("person_id") or person.get("id") or "",
            "personId": row.get("person_id") or person.get("id") or "",
            "role": row.get("role") or "family_contact",
            "displayName": person.get("display_name") or "Family member",
            "relationship": person.get("relationship") or "family",
            "permissions": permissions,
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    def family_relay_to_row(self, relay):
        relay = relay or {}
        return {
            "account_id": relay.get("accountId") or relay.get("account_id"),
            "family_group_id": relay.get("familyGroupId") or relay.get("family_group_id"),
            "sender_person_id": relay.get("senderPersonId") or relay.get("sender_person_id"),
            "recipient_person_id": relay.get("recipientPersonId") or relay.get("recipient_person_id"),
            "sender_label": str(relay.get("senderLabel") or relay.get("sender_label") or "家人")[:40],
            "recipient_label": str(relay.get("recipientLabel") or relay.get("recipient_label") or "家人")[:40],
            "content": str(relay.get("content") or "").strip()[:240],
            "status": relay.get("status") or "pending",
            "source": str(relay.get("source") or "voice-ai")[:40],
            "metadata": relay.get("metadata") if isinstance(relay.get("metadata"), dict) else {},
        }

    @staticmethod
    def family_relay_row_to_relay(row):
        row = row or {}
        return {
            "id": row.get("id"),
            "accountId": row.get("account_id"),
            "familyGroupId": row.get("family_group_id"),
            "senderPersonId": row.get("sender_person_id"),
            "recipientPersonId": row.get("recipient_person_id"),
            "senderLabel": row.get("sender_label") or "家人",
            "recipientLabel": row.get("recipient_label") or "家人",
            "content": row.get("content") or "",
            "status": row.get("status") or "pending",
            "source": row.get("source") or "voice-ai",
            "claimToken": row.get("claim_token"),
            "claimedAt": row.get("claimed_at"),
            "deliveredAt": row.get("delivered_at"),
            "expiresAt": row.get("expires_at"),
            "metadata": row.get("metadata") or {},
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    def push_device_to_row(self, device):
        device = device or {}
        token = str(device.get("token") or "").strip().replace(" ", "").replace("<", "").replace(">", "")
        token_hash = str(device.get("tokenHash") or device.get("token_hash") or "").strip()
        if token and not token_hash:
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        permission = device.get("permissionStatus") or device.get("permission_status") or "not_determined"
        environment = device.get("environment") if device.get("environment") in ("sandbox", "production") else "production"
        enabled = device.get("notificationsEnabled")
        if enabled is None:
            enabled = device.get("notifications_enabled", permission in ("authorized", "provisional"))
        return {
            "account_id": self.account_id,
            "person_id": self.person_id,
            "auth_user_id": self.auth_user_id,
            "platform": "ios",
            "environment": environment,
            "bundle_id": str(device.get("bundleId") or device.get("bundle_id") or "net.munea.app")[:160],
            "token": token,
            "token_hash": token_hash,
            "app_version": str(device.get("appVersion") or device.get("app_version") or "")[:40] or None,
            "locale": str(device.get("locale") or "zh-TW")[:40],
            "timezone": str(device.get("timezone") or "Asia/Taipei")[:80],
            "permission_status": permission,
            "notifications_enabled": bool(enabled),
            "show_sensitive_content": bool(device.get("showSensitiveContent") or device.get("show_sensitive_content")),
            "last_seen_at": device.get("lastSeenAt") or device.get("last_seen_at") or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "metadata": device.get("metadata") if isinstance(device.get("metadata"), dict) else {},
        }

    @staticmethod
    def push_device_row_to_device(row):
        row = row or {}
        return {
            "id": row.get("id"),
            "accountId": row.get("account_id"),
            "personId": row.get("person_id"),
            "authUserId": row.get("auth_user_id"),
            "platform": row.get("platform") or "ios",
            "environment": row.get("environment") or "production",
            "bundleId": row.get("bundle_id"),
            "token": row.get("token"),
            "tokenHash": row.get("token_hash"),
            "appVersion": row.get("app_version"),
            "locale": row.get("locale") or "zh-TW",
            "timezone": row.get("timezone") or "Asia/Taipei",
            "permissionStatus": row.get("permission_status") or "not_determined",
            "notificationsEnabled": bool(row.get("notifications_enabled")),
            "showSensitiveContent": bool(row.get("show_sensitive_content")),
            "lastSeenAt": row.get("last_seen_at"),
            "invalidatedAt": row.get("invalidated_at"),
            "metadata": row.get("metadata") or {},
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    @staticmethod
    def notification_event_to_rpc(event):
        event = event or {}
        return {
            "p_recipient_person_id": event.get("recipientPersonId") or event.get("recipient_person_id"),
            "p_event_type": event.get("eventType") or event.get("event_type"),
            "p_title": event.get("title"),
            "p_body": event.get("body"),
            "p_public_title": event.get("publicTitle") or event.get("public_title") or "沐寧提醒",
            "p_public_body": event.get("publicBody") or event.get("public_body") or "你的健康提醒到了，解鎖後查看。",
            "p_sensitivity": event.get("sensitivity") or "private",
            "p_deep_link": event.get("deepLink") or event.get("deep_link") or "munea://notifications",
            "p_actor_person_id": event.get("actorPersonId") or event.get("actor_person_id"),
            "p_family_group_id": event.get("familyGroupId") or event.get("family_group_id"),
            "p_resource_type": event.get("resourceType") or event.get("resource_type"),
            "p_resource_id": event.get("resourceId") or event.get("resource_id"),
            "p_dedupe_key": event.get("dedupeKey") or event.get("dedupe_key") or None,
            "p_metadata": event.get("metadata") if isinstance(event.get("metadata"), dict) else {},
            "p_expires_at": event.get("expiresAt") or event.get("expires_at"),
        }

    @staticmethod
    def notification_event_row_to_event(row):
        row = row or {}
        return {
            "id": row.get("id"),
            "accountId": row.get("account_id"),
            "recipientPersonId": row.get("recipient_person_id"),
            "actorPersonId": row.get("actor_person_id"),
            "familyGroupId": row.get("family_group_id"),
            "eventType": row.get("event_type"),
            "resourceType": row.get("resource_type"),
            "resourceId": row.get("resource_id"),
            "title": row.get("title") or "沐寧提醒",
            "body": row.get("body") or "",
            "publicTitle": row.get("public_title") or "沐寧提醒",
            "publicBody": row.get("public_body") or "你的健康提醒到了，解鎖後查看。",
            "sensitivity": row.get("sensitivity") or "private",
            "deepLink": row.get("deep_link") or "munea://notifications",
            "dedupeKey": row.get("dedupe_key"),
            "metadata": row.get("metadata") or {},
            "expiresAt": row.get("expires_at"),
            "readAt": row.get("read_at"),
            "archivedAt": row.get("archived_at"),
            "actedAt": row.get("acted_at"),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
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
            "serverVerificationRequired": not bool(row.get("verified_at")),
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
            "account_id": self.payload_account_id(tx.get("accountId") or tx.get("account_id")),
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
        elif event_type == "credits_expire":
            event_type = "credits_expired"
        return {
            "account_id": self.payload_account_id(event.get("accountId") or event.get("account_id")),
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
            "account_id": self.payload_account_id(event.get("accountId") or event.get("account_id")),
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
            "account_id": self.payload_account_id(item.get("accountId") or item.get("account_id")),
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

    def conversation_summary_to_row(self, item):
        item = item or {}
        person_id = item.get("personId") or item.get("person_id") or self.person_id
        if person_id and not self._is_uuid(person_id):
            person_id = self.person_id
        voice_session_id = item.get("voiceSessionId") or item.get("voice_session_id")
        if voice_session_id and not self._is_uuid(voice_session_id):
            voice_session_id = None
        return {
            "account_id": self.payload_account_id(item.get("accountId") or item.get("account_id")),
            "person_id": person_id or None,
            "voice_session_id": voice_session_id,
            "summary": item.get("summary") or "",
            "memory_tags": item.get("memoryTags") or item.get("memory_tags") or item.get("tags") or [],
            "safety_relevant": bool(item.get("safetyRelevant") or item.get("safety_relevant")),
        }

    @staticmethod
    def conversation_summary_row_to_item(row):
        row = row or {}
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "personId": row.get("person_id"),
            "voiceSessionId": row.get("voice_session_id"),
            "summary": row.get("summary") or "",
            "memoryTags": row.get("memory_tags") or [],
            "safetyRelevant": bool(row.get("safety_relevant")),
            "createdAt": row.get("created_at"),
            "deletedAt": row.get("deleted_at"),
            "privacy": {
                "storesRawTranscriptByDefault": False,
                "retainedRecord": "summary_only",
            },
        }

    def perception_snapshot_to_row(self, snapshot):
        snapshot = snapshot or {}
        return {
            "account_id": self.payload_account_id(snapshot.get("accountId") or snapshot.get("account_id")),
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
            "account_id": self.payload_account_id(state.get("accountId") or state.get("account_id")),
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
    def _normalize_family_invitation_status(status):
        allowed = {"pending", "applied", "accepted", "rejected", "revoked", "expired"}
        return status if status in allowed else "pending"

    @staticmethod
    def _hash_invitation_token(token):
        token = token or ("munea_" + uuid.uuid4().hex)
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def family_invitation_to_row(self, invitation):
        invitation = invitation or {}
        metadata = dict(invitation.get("metadata") or {})
        family_group_id = invitation.get("familyGroupId") or invitation.get("family_group_id") or self.family_group_id
        inviter_person_id = invitation.get("inviterPersonId") or invitation.get("inviter_person_id") or self.person_id
        invitee_person_id = invitation.get("inviteePersonId") or invitation.get("invitee_person_id")
        if family_group_id and not self._is_uuid(family_group_id):
            metadata.setdefault("originalFamilyGroupId", family_group_id)
            family_group_id = self.family_group_id
        if inviter_person_id and not self._is_uuid(inviter_person_id):
            metadata.setdefault("originalInviterPersonId", inviter_person_id)
            inviter_person_id = self.person_id
        if invitee_person_id and not self._is_uuid(invitee_person_id):
            metadata.setdefault("originalInviteePersonId", invitee_person_id)
            invitee_person_id = None
        short_code = str(invitation.get("shortCode") or invitation.get("short_code") or "").strip()
        if not (len(short_code) == 6 and short_code.isdigit()):
            short_code = str(uuid.uuid4().int % 1_000_000).zfill(6)
        token_hash = invitation.get("tokenHash") or invitation.get("token_hash")
        if not token_hash:
            token_hash = self._hash_invitation_token(
                invitation.get("shareToken") or invitation.get("share_token") or invitation.get("token")
            )
        return {
            "account_id": self.payload_account_id(invitation.get("accountId") or invitation.get("account_id")),
            "family_group_id": family_group_id,
            "inviter_person_id": inviter_person_id or None,
            "invitee_person_id": invitee_person_id or None,
            "token_hash": token_hash,
            "short_code": short_code,
            "delivery_hint": invitation.get("deliveryHint") or invitation.get("delivery_hint"),
            "elder_assisted": bool(invitation.get("elderAssisted") or invitation.get("elder_assisted") or False),
            "status": self._normalize_family_invitation_status(invitation.get("status")),
            "expires_at": invitation.get("expiresAt") or invitation.get("expires_at"),
            "accepted_at": invitation.get("acceptedAt") or invitation.get("accepted_at"),
            "revoked_at": invitation.get("revokedAt") or invitation.get("revoked_at"),
            "metadata": metadata,
        }

    def family_invitation_patch_to_row(self, patch):
        patch = patch or {}
        payload = {}
        if "status" in patch:
            payload["status"] = self._normalize_family_invitation_status(patch.get("status"))
            if payload["status"] == "accepted":
                payload["accepted_at"] = patch.get("acceptedAt") or patch.get("accepted_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if payload["status"] == "revoked":
                payload["revoked_at"] = patch.get("revokedAt") or patch.get("revoked_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if "inviteePersonId" in patch or "invitee_person_id" in patch:
            invitee_person_id = patch.get("inviteePersonId") or patch.get("invitee_person_id")
            payload["invitee_person_id"] = invitee_person_id if self._is_uuid(invitee_person_id or "") else None
        if "metadata" in patch:
            payload["metadata"] = patch.get("metadata") or {}
        if "deliveryHint" in patch or "delivery_hint" in patch:
            payload["delivery_hint"] = patch.get("deliveryHint") or patch.get("delivery_hint")
        return payload

    @staticmethod
    def family_invitation_row_to_invitation(row):
        row = row or {}
        metadata = row.get("metadata") or {}
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "familyGroupId": row.get("family_group_id") or metadata.get("originalFamilyGroupId"),
            "inviterPersonId": row.get("inviter_person_id") or metadata.get("originalInviterPersonId"),
            "inviteePersonId": row.get("invitee_person_id") or metadata.get("originalInviteePersonId"),
            "shortCode": row.get("short_code") or "",
            "deliveryHint": row.get("delivery_hint"),
            "elderAssisted": bool(row.get("elder_assisted", False)),
            "status": row.get("status") or "pending",
            "expiresAt": row.get("expires_at"),
            "acceptedAt": row.get("accepted_at"),
            "revokedAt": row.get("revoked_at"),
            "metadata": metadata,
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    @staticmethod
    def _normalize_consent_status(status):
        allowed = {"granted", "revoked", "expired"}
        return status if status in allowed else "granted"

    def consent_record_to_row(self, record):
        record = record or {}
        scope = dict(record.get("scope") or {})
        evidence = dict(record.get("evidence") or {})
        person_id = record.get("personId") or record.get("person_id") or self.person_id
        family_group_id = record.get("familyGroupId") or record.get("family_group_id") or self.family_group_id
        granted_by_person_id = record.get("grantedByPersonId") or record.get("granted_by_person_id") or self.person_id
        if person_id and not self._is_uuid(person_id):
            scope.setdefault("originalPersonId", person_id)
            person_id = self.person_id
        if family_group_id and not self._is_uuid(family_group_id):
            scope.setdefault("originalFamilyGroupId", family_group_id)
            family_group_id = self.family_group_id if self._is_uuid(self.family_group_id) else None
        if granted_by_person_id and not self._is_uuid(granted_by_person_id):
            evidence.setdefault("originalGrantedByPersonId", granted_by_person_id)
            granted_by_person_id = self.person_id
        return {
            "account_id": self.payload_account_id(record.get("accountId") or record.get("account_id")),
            "person_id": person_id,
            "family_group_id": family_group_id or None,
            "consent_type": record.get("consentType") or record.get("consent_type") or "ai_provider_processing",
            "consent_version": record.get("consentVersion") or record.get("consent_version") or "v1",
            "status": self._normalize_consent_status(record.get("status")),
            "granted_by_person_id": granted_by_person_id or None,
            "source": record.get("source") or "munea-api",
            "scope": scope,
            "evidence": evidence,
            "granted_at": record.get("grantedAt") or record.get("granted_at") or record.get("createdAt") or record.get("created_at"),
            "revoked_at": record.get("revokedAt") or record.get("revoked_at"),
            "expires_at": record.get("expiresAt") or record.get("expires_at"),
        }

    def consent_record_revoke_patch_to_row(self, patch):
        patch = patch or {}
        evidence = dict(patch.get("evidence") or {})
        revoked_by_person_id = patch.get("revokedByPersonId") or patch.get("revoked_by_person_id")
        if revoked_by_person_id and not self._is_uuid(revoked_by_person_id):
            evidence.setdefault("originalRevokedByPersonId", revoked_by_person_id)
        elif revoked_by_person_id:
            evidence.setdefault("revokedByPersonId", revoked_by_person_id)
        return {
            "status": "revoked",
            "revoked_at": patch.get("revokedAt") or patch.get("revoked_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "evidence": evidence,
        }

    @staticmethod
    def consent_record_row_to_record(row):
        row = row or {}
        scope = row.get("scope") or {}
        evidence = row.get("evidence") or {}
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "personId": row.get("person_id") or scope.get("originalPersonId"),
            "familyGroupId": row.get("family_group_id") or scope.get("originalFamilyGroupId"),
            "consentType": row.get("consent_type") or "ai_provider_processing",
            "consentVersion": row.get("consent_version") or "v1",
            "status": row.get("status") or "granted",
            "grantedByPersonId": row.get("granted_by_person_id") or evidence.get("originalGrantedByPersonId"),
            "source": row.get("source") or "munea-api",
            "scope": scope,
            "evidence": evidence,
            "grantedAt": row.get("granted_at"),
            "revokedAt": row.get("revoked_at"),
            "expiresAt": row.get("expires_at"),
            "createdAt": row.get("created_at"),
        }

    @staticmethod
    def _normalize_routine_reminder_type(reminder_type):
        allowed = {"medication", "routine", "check_in", "custom"}
        return reminder_type if reminder_type in allowed else "custom"

    @staticmethod
    def _normalize_routine_reminder_status(status):
        allowed = {"active", "paused", "archived"}
        return status if status in allowed else "active"

    def routine_reminder_to_row(self, item):
        item = item or {}
        schedule = dict(item.get("schedule") or {})
        reminder_id = item.get("id")
        person_id = item.get("personId") or item.get("person_id") or self.person_id
        if reminder_id and not self._is_uuid(reminder_id):
            schedule.setdefault("originalReminderId", reminder_id)
        if person_id and not self._is_uuid(person_id):
            schedule.setdefault("originalPersonId", person_id)
            person_id = self.person_id
        for key in ("date", "weekday", "time", "times", "dosage", "note", "repeat"):
            if key in item and item.get(key) is not None:
                schedule.setdefault(key, item.get(key))
        return {
            "account_id": self.payload_account_id(item.get("accountId") or item.get("account_id")),
            "person_id": person_id,
            "title": item.get("title") or item.get("label") or "Routine reminder",
            "reminder_type": self._normalize_routine_reminder_type(item.get("type") or item.get("reminderType") or item.get("reminder_type")),
            "schedule": schedule,
            "status": self._normalize_routine_reminder_status(item.get("status")),
            "deleted_at": item.get("deletedAt") or item.get("deleted_at"),
        }

    def routine_reminder_patch_to_row(self, patch):
        patch = patch or {}
        payload = {}
        if any(key in patch for key in ("title", "label")):
            payload["title"] = patch.get("title") or patch.get("label") or "Routine reminder"
        if any(key in patch for key in ("type", "reminderType", "reminder_type")):
            payload["reminder_type"] = self._normalize_routine_reminder_type(patch.get("type") or patch.get("reminderType") or patch.get("reminder_type"))
        if "status" in patch:
            payload["status"] = self._normalize_routine_reminder_status(patch.get("status"))
            if payload["status"] == "archived":
                payload["deleted_at"] = patch.get("deletedAt") or patch.get("deleted_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if "schedule" in patch:
            payload["schedule"] = patch.get("schedule") or {}
        return payload

    @staticmethod
    def routine_reminder_row_to_item(row):
        row = row or {}
        schedule = row.get("schedule") or {}
        return {
            "id": row.get("id") or schedule.get("originalReminderId") or "",
            "accountId": row.get("account_id") or "",
            "personId": row.get("person_id") or schedule.get("originalPersonId"),
            "title": row.get("title") or "Routine reminder",
            "type": row.get("reminder_type") or "routine",
            "status": row.get("status") or "active",
            "schedule": schedule,
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
            "deletedAt": row.get("deleted_at"),
        }

    @staticmethod
    def _normalize_medication_dose_status(status):
        allowed = {"scheduled", "taken", "snoozed", "skipped", "missed"}
        return status if status in allowed else "scheduled"

    def medication_dose_to_row(self, item):
        item = item or {}
        metadata = dict(item.get("metadata") or {})
        person_id = item.get("personId") or item.get("person_id") or self.person_id
        reminder_id = item.get("reminderId") or item.get("reminder_id")
        if person_id and not self._is_uuid(person_id):
            metadata.setdefault("originalPersonId", person_id)
            person_id = self.person_id
        if reminder_id and not self._is_uuid(reminder_id):
            metadata.setdefault("originalReminderId", reminder_id)
            reminder_id = None
        return {
            "account_id": self.payload_account_id(item.get("accountId") or item.get("account_id")),
            "person_id": person_id,
            "routine_reminder_id": reminder_id or None,
            "dose_key": str(item.get("doseKey") or item.get("dose_key") or "")[:240],
            "medication_name": str(item.get("medicationName") or item.get("medication_name") or "用藥")[:160],
            "slot_label": str(item.get("slot") or item.get("slotLabel") or item.get("slot_label") or "")[:80],
            "scheduled_date": item.get("scheduledDate") or item.get("scheduled_date"),
            "scheduled_at": item.get("scheduledAt") or item.get("scheduled_at"),
            "expected_count": max(0, min(100, int(item.get("expectedCount") or item.get("expected_count") or 0))),
            "status": self._normalize_medication_dose_status(item.get("status")),
            "taken_at": item.get("takenAt") or item.get("taken_at"),
            "source": str(item.get("source") or "munea-app")[:80],
            "timezone": str(item.get("timezone") or "Asia/Taipei")[:80],
            "metadata": metadata,
        }

    @staticmethod
    def medication_dose_row_to_item(row):
        row = row or {}
        metadata = row.get("metadata") or {}
        return {
            "id": row.get("id") or "",
            "accountId": row.get("account_id") or "",
            "personId": row.get("person_id") or metadata.get("originalPersonId"),
            "reminderId": row.get("routine_reminder_id") or metadata.get("originalReminderId"),
            "doseKey": row.get("dose_key") or "",
            "medicationName": row.get("medication_name") or "用藥",
            "slot": row.get("slot_label") or "",
            "scheduledDate": row.get("scheduled_date"),
            "scheduledAt": row.get("scheduled_at"),
            "expectedCount": row.get("expected_count") or 0,
            "status": row.get("status") or "scheduled",
            "takenAt": row.get("taken_at"),
            "source": row.get("source") or "munea-api",
            "timezone": row.get("timezone") or "Asia/Taipei",
            "metadata": metadata,
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    # 中文六類（AI 觀察 perception_engine.MOOD_CATEGORIES／App 手動打卡)→ 英文 mood key 對照。
    # 含常見同義詞（愉悅/平靜/焦慮/生氣，對齊 web/src/app.js FAM_MOOD_NAME 六色編號用字），
    # 寫入路徑（_normalize_wellbeing_mood）跟讀取救援路徑（_recover_admin_wellbeing_mood）共用同一張表，別各寫一份。
    _WELLBEING_MOOD_ENGLISH_KEYS = {"happy", "pleasant", "steady", "tired", "low", "irritated", "mixed"}
    _WELLBEING_MOOD_CHINESE_ALIASES = {
        "開心": "happy",
        "愉快": "pleasant",
        "愉悅": "pleasant",
        "平穩": "steady",
        "平靜": "steady",
        "疲累": "tired",
        "低落": "low",
        "煩躁": "irritated",
        "焦慮": "irritated",
        "生氣": "irritated",
        "混合": "mixed",
    }

    @classmethod
    def _wellbeing_mood_from_text(cls, text):
        """把任何原始 mood 字串（中文六類/同義詞，或已是英文 key）轉成英文 mood key；認不得回 None
        （呼叫端自行決定要不要退 unknown，別在這裡吞掉「換算不出來」這件事）。比對前先 strip()。"""
        t = str(text or "").strip()
        if not t:
            return None
        if t in cls._WELLBEING_MOOD_ENGLISH_KEYS:
            return t
        return cls._WELLBEING_MOOD_CHINESE_ALIASES.get(t)

    @classmethod
    def _normalize_wellbeing_mood(cls, mood):
        """寫入 wellbeing_signals.mood 前的正規化：中文／英文都收，認不得才回 unknown。
        2026-07-20 修：舊版只認英文，AI 寫入的中文一律變 unknown，把後台心情趨勢的資料源污染光了。"""
        return cls._wellbeing_mood_from_text(mood) or "unknown"

    @classmethod
    def _recover_admin_wellbeing_mood(cls, signal):
        """後台心情趨勢救舊帳：wellbeing_row_to_signal 回給 App 的 mood 可能是中文原字（那是對的、App 要
        顯示用，不要動它）；這裡只給後台聚合／_mood_bucket 用，換算成英文 mood key 才能正確歸桶。
        依序試 signal.mood（Supabase 正規化後的英文，或 JSON 備援路徑的中文原字）、
        facts.originalMood、facts.mood；都換算不出來才退 unknown。"""
        facts = signal.get("facts") or {}
        for candidate in (signal.get("mood"), facts.get("originalMood"), facts.get("mood")):
            mapped = cls._wellbeing_mood_from_text(candidate)
            if mapped:
                return mapped
        return "unknown"

    # 英文 mood 詞 → App 六色編號（0開心/1愉悅/2平靜/3低落/4焦慮/5生氣）；mixed/unknown 沒有安全對應、回 None
    _WELLBEING_MOOD_TO_KEY = {"happy": 0, "pleasant": 1, "steady": 2, "tired": 3, "low": 3, "irritated": 4}

    @classmethod
    def _wellbeing_mood_key(cls, facts, row):
        # moodKey=0（開心）是合法值：不能用 `or` 判斷、否則 0 被當成沒有值退回英文字，App 端會拿到字串編號
        key = (facts or {}).get("moodKey")
        if key is not None:
            return key
        return cls._WELLBEING_MOOD_TO_KEY.get((row or {}).get("mood"))

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
            "account_id": self.payload_account_id(signal.get("accountId") or signal.get("account_id")),
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
            "moodKey": SupabaseAdapter._wellbeing_mood_key(facts, row),
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
    def _normalize_family_activity_type(activity_type):
        allowed = {"walk", "quiz", "event", "vote", "draw", "custom"}
        return activity_type if activity_type in allowed else "custom"

    @staticmethod
    def _normalize_family_activity_status(status):
        allowed = {"draft", "active", "completed", "archived", "cancelled"}
        return status if status in allowed else "active"

    @staticmethod
    def _normalize_family_participant_status(status):
        allowed = {"invited", "accepted", "declined", "completed"}
        return status if status in allowed else "invited"

    def family_activity_to_row(self, activity):
        activity = activity or {}
        payload = dict(activity.get("payload") or {})
        activity_id = activity.get("id")
        owner_person_id = activity.get("ownerPersonId") or activity.get("owner_person_id") or self.person_id
        family_group_id = activity.get("familyGroupId") or activity.get("family_group_id") or self.family_group_id
        if activity_id and not self._is_uuid(activity_id):
            payload.setdefault("originalActivityId", activity_id)
        if owner_person_id and not self._is_uuid(owner_person_id):
            payload.setdefault("originalOwnerPersonId", owner_person_id)
            owner_person_id = self.person_id
        if family_group_id and not self._is_uuid(family_group_id):
            payload.setdefault("originalFamilyGroupId", family_group_id)
            family_group_id = self.family_group_id
        return {
            "account_id": self.payload_account_id(activity.get("accountId") or activity.get("account_id")),
            "family_group_id": family_group_id,
            "owner_person_id": owner_person_id or None,
            "activity_type": self._normalize_family_activity_type(activity.get("type") or activity.get("activityType") or activity.get("activity_type")),
            "title": activity.get("title") or "Family activity",
            "status": self._normalize_family_activity_status(activity.get("status")),
            "starts_at": activity.get("startsAt") or activity.get("starts_at"),
            "ends_at": activity.get("endsAt") or activity.get("ends_at"),
            "payload": payload,
            "result": activity.get("result") or {},
            "archived_at": activity.get("archivedAt") or activity.get("archived_at"),
        }

    def family_activity_row_to_activity(self, row, participants=None):
        row = row or {}
        payload = row.get("payload") or {}
        return {
            "id": row.get("id") or payload.get("originalActivityId") or "",
            "accountId": row.get("account_id") or "",
            "familyGroupId": row.get("family_group_id"),
            "ownerPersonId": row.get("owner_person_id"),
            "type": row.get("activity_type") or "custom",
            "title": row.get("title") or "Family activity",
            "status": row.get("status") or "active",
            "startsAt": row.get("starts_at"),
            "endsAt": row.get("ends_at"),
            "payload": payload,
            "result": row.get("result") or {},
            "participants": [self.family_activity_participant_row_to_participant(p) for p in (participants or [])],
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
            "archivedAt": row.get("archived_at"),
        }

    def family_activity_participant_to_row(self, activity_id, participant):
        participant = participant or {}
        contribution = dict(participant.get("contribution") or {})
        person_id = participant.get("personId") or participant.get("person_id") or self.person_id
        if person_id and not self._is_uuid(person_id):
            contribution.setdefault("originalPersonId", person_id)
            person_id = self.person_id
        return {
            "account_id": self.payload_account_id(participant.get("accountId") or participant.get("account_id")),
            "family_activity_id": activity_id,
            "person_id": person_id,
            "role": participant.get("role") or "participant",
            "status": self._normalize_family_participant_status(participant.get("status")),
            "contribution": contribution,
            "response": participant.get("response") or {},
        }

    @staticmethod
    def family_activity_participant_row_to_participant(row):
        row = row or {}
        contribution = row.get("contribution") or {}
        return {
            "id": row.get("id") or "",
            "activityId": row.get("family_activity_id"),
            "personId": row.get("person_id") or contribution.get("originalPersonId"),
            "role": row.get("role") or "participant",
            "status": row.get("status") or "invited",
            "contribution": contribution,
            "response": row.get("response") or {},
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
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
            raise SupabaseRequestError(
                "Supabase adapter is not fully configured",
                error_kind="configuration",
            )
        # 斷路器：雲端連不上時，20 秒內同一波後續呼叫直接秒退（走本地備份），
        # 不再每次苦等 4 秒逾時。防「單一請求連問十幾次、累加成數分鐘卡死」。
        if _circuit_open():
            raise SupabaseRequestError(
                "Supabase circuit open: recent connection failure, using local fallback",
                error_kind="unreachable",
            )
        if _table_known_missing(table):
            raise SupabaseRequestError(
                f"Supabase table '{table}' known missing (PGRST205 cached), using local fallback",
                error_kind="missing_table",
                status_code=404,
                error_code="PGRST205",
            )
        query_string = urllib.parse.urlencode(query or {})
        url = f"{self.url}/rest/v1/{table}"
        if query_string:
            url = f"{url}?{query_string}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = self._service_headers()
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
            error_code = None
            try:
                parsed_detail = json.loads(detail)
                if isinstance(parsed_detail, dict):
                    error_code = parsed_detail.get("code")
            except (TypeError, ValueError):
                pass
            if e.code == 404 and (error_code == "PGRST205" or "PGRST205" in detail):
                _mark_table_missing(table)  # 記著這張表缺，30 秒內同批呼叫秒退
                error_code = "PGRST205"
            if e.code == 401:
                error_kind = "configuration"
            elif e.code == 403:
                error_kind = "permission"
            elif e.code == 404 and error_code == "PGRST205":
                error_kind = "missing_table"
            elif error_code == "42501":
                error_kind = "permission"
            else:
                error_kind = "http_error"
            raise SupabaseRequestError(
                f"Supabase {method} {table} failed: {e.code} {detail}",
                error_kind=error_kind,
                status_code=e.code,
                error_code=error_code,
            ) from e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            # 連線層失敗（逾時 / 連不上 / 被重置）：開啟斷路器，讓同批後續呼叫秒退
            _trip_circuit()
            raise SupabaseRequestError(f"Supabase {method} {table} unreachable: {type(e).__name__}", error_kind="unreachable") from e

    @staticmethod
    def _is_uuid(value):
        return bool(value and UUID_RE.match(value))


def make_adapter(env=None, identity=None):
    return SupabaseAdapter(env=env, identity=identity)


def recover_admin_wellbeing_mood(item):
    """後台心情訊號 mood 救援共用入口（Supabase 與 JSON 備援兩條讀取路徑共用同一張中文→英文對照表，
    別各寫一份）。item：wellbeing signal dict（有 mood／facts 欄位即可，兩條路徑格式相容）。"""
    return SupabaseAdapter._recover_admin_wellbeing_mood(item)
