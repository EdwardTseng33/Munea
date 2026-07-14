#!/usr/bin/env python3
"""Verify legacy JWT and modern opaque Supabase service-key headers."""
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from supabase_adapter import SupabaseAdapter  # noqa: E402


modern = SupabaseAdapter({
    "MUNEA_DATABASE_PROVIDER": "supabase",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_modern",
})
modern_headers = modern._service_headers()
assert modern_headers["apikey"] == "sb_secret_modern"
assert "authorization" not in modern_headers

legacy = SupabaseAdapter({
    "MUNEA_DATABASE_PROVIDER": "supabase",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "legacy.jwt.service-role",
})
legacy_headers = legacy._service_headers()
assert legacy_headers["authorization"] == "Bearer legacy.jwt.service-role"
print("Supabase service-key headers: PASS")
