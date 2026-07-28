#!/usr/bin/env python3
"""開帳與個人資料重整（2026-07-24）——個人資料雲端同步接口的護欄測試。

涵蓋三層：
  1. normalize_person_profile() 純函式的邊界清洗（年份/月份範圍、字串裁切、空值）。
  2. person_profile_response()（server.py）在本機 JSON fallback 下的 save/load 迴圈。
  3. SupabaseAdapter 的 row<->profile 對應與 PATCH 目標（不打真網路，mock _request）。
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "person-profile-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402
from supabase_adapter import SupabaseAdapter  # noqa: E402


PERSON_A = "33333333-3333-4333-8333-333333333333"
FAMILY_A = "55555555-5555-4555-8555-555555555555"


def json_backend(person_id=PERSON_A):
    return SupabaseAdapter(
        env={"MUNEA_DATABASE_PROVIDER": "json"},
        identity={"personId": person_id, "familyGroupId": FAMILY_A},
    )


class NormalizePersonProfileTests(unittest.TestCase):
    def test_trims_and_limits_text_fields(self):
        profile = server.normalize_person_profile({
            "name": "  秀英  ",
            "nick": "阿嫉" * 30,
            "county": "台北市",
            "district": "大安區",
        })
        self.assertEqual(profile["name"], "秀英")
        self.assertEqual(len(profile["nick"]), 40)
        self.assertEqual(profile["county"], "台北市")
        self.assertEqual(profile["district"], "大安區")

    def test_birth_year_out_of_range_becomes_none(self):
        profile = server.normalize_person_profile({"birthYear": 1899})
        self.assertIsNone(profile["birthYear"])
        profile2 = server.normalize_person_profile({"birthYear": 2101})
        self.assertIsNone(profile2["birthYear"])
        profile3 = server.normalize_person_profile({"birthYear": 1954})
        self.assertEqual(profile3["birthYear"], 1954)

    def test_birth_month_out_of_range_becomes_none(self):
        self.assertIsNone(server.normalize_person_profile({"birthMonth": 0})["birthMonth"])
        self.assertIsNone(server.normalize_person_profile({"birthMonth": 13})["birthMonth"])
        self.assertEqual(server.normalize_person_profile({"birthMonth": 7})["birthMonth"], 7)

    def test_non_numeric_birth_fields_do_not_raise(self):
        profile = server.normalize_person_profile({"birthYear": "not-a-year", "birthMonth": "x"})
        self.assertIsNone(profile["birthYear"])
        self.assertIsNone(profile["birthMonth"])

    def test_empty_input_returns_blank_profile_with_timestamp(self):
        profile = server.normalize_person_profile({})
        self.assertEqual(profile["name"], "")
        self.assertEqual(profile["nick"], "")
        self.assertIsNone(profile["birthYear"])
        self.assertTrue(profile["updatedAt"])


class PersonProfileResponseJsonFallbackTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        handle.write(b"{}")
        handle.close()
        self.path = handle.name
        self.path_patch = patch.object(server, "PERSON_PROFILE_PATH", self.path)
        self.path_patch.start()
        self.backend_patch = patch.object(server, "data_backend", return_value=json_backend())
        self.backend_patch.start()

    def tearDown(self):
        self.backend_patch.stop()
        self.path_patch.stop()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_load_before_save_returns_blank_profile(self):
        result = server.person_profile_response({"action": "load"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["nick"], "")
        self.assertIsNone(result["profile"]["birthYear"])

    def test_save_then_load_round_trips(self):
        saved = server.person_profile_response({
            "action": "save",
            "profile": {
                "name": "陳秀英",
                "nick": "阿嫉",
                "birthYear": 1954,
                "birthMonth": 3,
                "county": "台南市",
                "district": "東區",
            },
        })
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["profile"]["nick"], "阿嫉")
        self.assertEqual(saved["profile"]["birthYear"], 1954)

        loaded = server.person_profile_response({"action": "load"})
        self.assertEqual(loaded["profile"]["name"], "陳秀英")
        self.assertEqual(loaded["profile"]["nick"], "阿嫉")
        self.assertEqual(loaded["profile"]["birthYear"], 1954)
        self.assertEqual(loaded["profile"]["birthMonth"], 3)
        self.assertEqual(loaded["profile"]["county"], "台南市")
        self.assertEqual(loaded["profile"]["district"], "東區")
        self.assertTrue(loaded["profile"]["updatedAt"])

    def test_save_updates_updated_at_each_time(self):
        first = server.person_profile_response({"action": "save", "profile": {"nick": "阿嫉"}})
        second = server.person_profile_response({"action": "save", "profile": {"nick": "阿公"}})
        self.assertEqual(second["profile"]["nick"], "阿公")
        self.assertTrue(second["profile"]["updatedAt"] >= first["profile"]["updatedAt"])


class SupabaseAdapterPersonProfileMappingTests(unittest.TestCase):
    def test_person_row_to_profile_maps_columns(self):
        profile = SupabaseAdapter.person_row_to_profile({
            "profile_name": "陳秀英",
            "nickname": "阿嫉",
            "birth_year": 1954,
            "birth_month": 3,
            "county": "台南市",
            "district": "東區",
            "updated_at": "2026-07-24T00:00:00Z",
        })
        self.assertEqual(profile["name"], "陳秀英")
        self.assertEqual(profile["nick"], "阿嫉")
        self.assertEqual(profile["birthYear"], 1954)
        self.assertEqual(profile["birthMonth"], 3)
        self.assertEqual(profile["county"], "台南市")
        self.assertEqual(profile["district"], "東區")

    def test_person_row_to_profile_handles_missing_row(self):
        profile = SupabaseAdapter.person_row_to_profile(None)
        self.assertEqual(profile["name"], "")
        self.assertEqual(profile["nick"], "")
        self.assertIsNone(profile["birthYear"])

    def test_profile_to_person_row_only_sends_provided_fields(self):
        row = SupabaseAdapter.profile_to_person_row({"nick": "阿嫉"})
        self.assertEqual(row, {"nickname": "阿嫉"})

    def test_profile_to_person_row_clears_with_explicit_empty_string(self):
        row = SupabaseAdapter.profile_to_person_row({"nick": ""})
        self.assertEqual(row, {"nickname": None})

    def test_profile_to_person_row_rejects_bad_year(self):
        row = SupabaseAdapter.profile_to_person_row({"birthYear": "not-a-year"})
        self.assertEqual(row, {"birth_year": None})

    def test_load_person_profile_disabled_backend_returns_none(self):
        backend = json_backend()
        self.assertFalse(backend.enabled())
        self.assertIsNone(backend.load_person_profile())
        self.assertIsNone(backend.save_person_profile({"nick": "阿嫉"}))

    def test_save_person_profile_patches_persons_by_person_id(self):
        backend = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
            },
            identity={"accountId": FAMILY_A, "personId": PERSON_A, "familyGroupId": FAMILY_A},
        )
        self.assertTrue(backend.enabled())
        with patch.object(backend, "_request", return_value=[{
            "id": PERSON_A,
            "profile_name": "陳秀英",
            "nickname": "阿嫉",
            "birth_year": 1954,
            "birth_month": 3,
            "county": "台南市",
            "district": "東區",
            "updated_at": "2026-07-24T00:00:00Z",
        }]) as mock_request:
            result = backend.save_person_profile({"nick": "阿嫉", "birthYear": 1954})
        self.assertEqual(result["nick"], "阿嫉")
        mock_request.assert_called_once_with(
            "PATCH",
            "persons",
            query={"id": f"eq.{PERSON_A}", "select": "*"},
            payload={"nickname": "阿嫉", "birth_year": 1954},
            prefer="return=representation",
        )

    def test_save_person_profile_with_no_fields_reads_current_row_instead_of_patching(self):
        backend = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
            },
            identity={"accountId": FAMILY_A, "personId": PERSON_A, "familyGroupId": FAMILY_A},
        )
        with patch.object(backend, "_first", return_value={"id": PERSON_A, "nickname": "阿嫉"}) as mock_first:
            with patch.object(backend, "_request") as mock_request:
                result = backend.save_person_profile({})
        mock_request.assert_not_called()
        mock_first.assert_called_once()
        self.assertEqual(result["nick"], "阿嫉")


if __name__ == "__main__":
    unittest.main()
