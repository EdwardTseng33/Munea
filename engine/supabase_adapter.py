"""
Supabase-ready data adapter for Munea.

This module is intentionally stdlib-only for the current prototype. It keeps
Supabase service credentials on the backend side and lets server.py keep a JSON
fallback until the cloud project, auth, and seeded account/person ids are ready.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request


UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


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
            "tables": ["accounts", "persons", "family_groups", "family_memberships", "companion_profiles"],
        }

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

    def _first(self, table, query):
        rows = self._select(table, {**(query or {}), "limit": (query or {}).get("limit", "1")})
        return rows[0] if rows else None

    def _select(self, table, query):
        return self._request("GET", table, query=query)

    def _request(self, method, table, query=None, payload=None, prefer=None):
        if not self.enabled():
            raise RuntimeError("Supabase adapter is not fully configured")
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
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Supabase {method} {table} failed: {e.code} {detail}") from e

    @staticmethod
    def _is_uuid(value):
        return bool(value and UUID_RE.match(value))


def make_adapter(env=None):
    return SupabaseAdapter(env=env)
