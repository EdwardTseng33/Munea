#!/usr/bin/env python3
"""雲端寫入失敗告警契約（2026-07-24 架構體檢 90 分路線 #3）：
「記憶可能無聲消失」的洞——雲端寫入失敗退本機備份時，必須發功能告警（不再無聲）；
讀取（GET）連線瞬斷先重試一次；寫入不盲重試（逾時可能已寫入、重打會變兩筆）。
規則被改掉或誤刪，這裡亮紅燈。"""
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")
_TMP = tempfile.mkdtemp(prefix="munea-cloud-write-test-")
for _key, _name in (
    ("MUNEA_MEMORY_ITEMS_PATH", "memory_items.json"),
    ("MUNEA_LIVING_PROFILE_PATH", "living_profile.json"),
    ("MUNEA_USER_PROFILE_PATH", "user_profile.json"),
    ("MUNEA_PERCEPTION_SNAPSHOTS_PATH", "perception_snapshots.json"),
    ("MUNEA_RELATIONSHIP_STATES_PATH", "relationship_states.json"),
    ("MUNEA_CONVERSATION_SUMMARIES_PATH", "conversation_summaries.json"),
    ("MUNEA_FAMILY_STATE_STORE_PATH", "family_state_store.json"),
    ("MUNEA_APP_PROFILE_STORE_PATH", "app_profile_store.json"),
):
    os.environ.setdefault(_key, os.path.join(_TMP, _name))

import server
import supabase_adapter

HERE = os.path.dirname(os.path.abspath(__file__))


class CloudWriteFallbackAlertTest(unittest.TestCase):
    def test_write_fallback_sends_data_alert(self):
        calls = []
        with mock.patch.object(server.notify, "alert", side_effect=lambda *a, **k: calls.append(a)):
            server.log_cloud_write_fallback("append memory items to Supabase", RuntimeError("boom"))
        self.assertEqual(len(calls), 1)
        kind, where = calls[0][0], calls[0][1]
        self.assertEqual(kind, "data")
        self.assertIn("memory items", where)
        self.assertIn("退本機備份", calls[0][2])

    def test_alert_failure_never_breaks_fallback_path(self):
        with mock.patch.object(server.notify, "alert", side_effect=RuntimeError("slack down")):
            # 不能因為告警發不出去，就把原本好好的本機備份路徑弄炸
            server.log_cloud_write_fallback("append wellbeing signal to Supabase", RuntimeError("boom"))

    def test_all_write_sites_use_alerting_variant(self):
        """19 個雲端寫入退本機的點都要走告警版；讀取路徑維持一般警告（避免告警洗版）。"""
        with open(os.path.join(HERE, "server.py"), encoding="utf-8") as f:
            src = f.read()
        write_contexts = [
            "append memory items to Supabase",
            "append conversation summary to Supabase",
            "archive conversation summary in Supabase",
            "append wellbeing signal to Supabase",
            "save family state to Supabase",
            "create family invitation in Supabase",
            "update family invitation in Supabase",
            "complete family invitation exchange",
            "save family activity to Supabase",
            "save family activity participant to Supabase",
            "save routine reminder to Supabase",
            "update routine reminder in Supabase",
            "save medication dose to Supabase",
            "save notification settings",
            "save daily briefing snapshot",
            "append perception snapshots to Supabase",
            "upsert relationship state to Supabase",
            "save app profile to Supabase",
            "save family member to Supabase",
        ]
        for context in write_contexts:
            self.assertIn(f'log_cloud_write_fallback("{context}"', src, f"寫入點未走告警版：{context}")
        # 讀取點抽查：仍是一般警告、不進告警房
        for context in ("load memory items from Supabase", "load wellbeing signals from Supabase"):
            self.assertIn(f'log_fallback_exception("{context}"', src, f"讀取點不該改告警版：{context}")


class AdapterRetryTest(unittest.TestCase):
    def _adapter(self):
        return supabase_adapter.make_adapter(env={
            "SUPABASE_URL": "https://unit-test.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_unit_test",
            "MUNEA_DATABASE_PROVIDER": "supabase",
            "MUNEA_SUPABASE_ACCOUNT_ID": "11111111-1111-4111-8111-111111111111",
            "MUNEA_SUPABASE_PERSON_ID": "22222222-2222-4222-8222-222222222222",
        })

    def _run_counting(self, method):
        adapter = self._adapter()
        attempts = []

        def fake_urlopen(req, timeout=None):
            attempts.append(req.get_method())
            raise TimeoutError("simulated network blip")

        with mock.patch.object(supabase_adapter.urllib.request, "urlopen", side_effect=fake_urlopen), \
             mock.patch.object(supabase_adapter, "_circuit_open", return_value=False), \
             mock.patch.object(supabase_adapter, "_table_known_missing", return_value=False), \
             mock.patch.object(supabase_adapter.time, "sleep"):
            with self.assertRaises(supabase_adapter.SupabaseRequestError) as ctx:
                adapter._request(method, "memory_items", query={"limit": "1"},
                                 payload=None if method == "GET" else {"x": 1})
        self.assertEqual(ctx.exception.error_kind, "unreachable")
        return len(attempts)

    def test_get_retries_once_on_transient_failure(self):
        self.assertEqual(self._run_counting("GET"), 2)

    def test_write_never_blind_retries(self):
        """寫入逾時可能其實已寫入；盲重試會變兩筆——只准一次、失敗走本機備份＋告警。"""
        self.assertEqual(self._run_counting("POST"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
