#!/usr/bin/env python3
"""雲端回補工人契約（90 分路線 #2 · 2026-07-24）：
①欠帳有記（含身分）②雲端恢復自動補回③補前先探測防重複④重複鍵當已補上
⑤連線沒醒整輪先睡⑥重試到頂放棄＋告警（資料仍在本機備份）⑦三個寫入口不再往上丟 500。
規則被改壞這裡亮紅燈。"""
import os
import tempfile
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="munea-resync-test-")
os.environ["MUNEA_CLOUD_PENDING_PATH"] = os.path.join(_TMP, "pending.json")
os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import cloud_resync
import supabase_adapter

HERE = os.path.dirname(os.path.abspath(__file__))


class FakeAdapter:
    def __init__(self, probe_rows=None, request_error=None):
        self.probe_rows = probe_rows or []
        self.request_error = request_error
        self.select_calls = []
        self.insert_calls = []

    def enabled(self):
        return True

    def memory_item_to_row(self, item):
        return {"account_id": "acc", "person_id": "p", "memory_type": "t", "content": item.get("content", "")}

    def conversation_summary_to_row(self, item):
        return {"account_id": "acc", "person_id": "p", "summary": item.get("summary", "")}

    def wellbeing_signal_to_row(self, item):
        return {"account_id": "acc", "person_id": "p", "mood": item.get("mood", "")}

    def _select(self, table, query):
        self.select_calls.append((table, query))
        return self.probe_rows

    def _request(self, method, table, query=None, payload=None, prefer=None):
        self.insert_calls.append((method, table, payload))
        if self.request_error:
            raise self.request_error
        return [{"id": "new"}]


def _reset_queue():
    cloud_resync._write_pending([])


class RecordPendingTest(unittest.TestCase):
    def setUp(self):
        _reset_queue()

    def test_record_keeps_item_and_identity(self):
        cloud_resync.record_pending("memory_items", {"content": "他愛種花"}, identity={"personId": "p1"})
        entries = cloud_resync._read_pending()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["store"], "memory_items")
        self.assertEqual(entries[0]["identity"], {"personId": "p1"})
        self.assertEqual(entries[0]["attempts"], 0)

    def test_unknown_store_or_empty_item_is_ignored(self):
        cloud_resync.record_pending("not_a_store", {"x": 1})
        cloud_resync.record_pending("memory_items", None)
        self.assertEqual(cloud_resync.pending_count(), 0)

    def test_overflow_drops_oldest_and_alerts(self):
        alerts = []
        with mock.patch.object(cloud_resync, "_alert", side_effect=lambda w, d: alerts.append(w)):
            with mock.patch.object(cloud_resync, "MAX_PENDING", 3):
                for i in range(5):
                    cloud_resync.record_pending("memory_items", {"content": f"m{i}"})
        entries = cloud_resync._read_pending()
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["item"]["content"], "m2")  # 最舊的被丟
        self.assertTrue(alerts)


class DrainTest(unittest.TestCase):
    def setUp(self):
        _reset_queue()

    def test_replays_to_cloud_when_recovered(self):
        cloud_resync.record_pending("memory_items", {"content": "他愛種花"})
        fake = FakeAdapter()
        stats = cloud_resync.drain_once(adapter_factory=lambda _i: fake)
        self.assertEqual(stats["done"], 1)
        self.assertEqual(cloud_resync.pending_count(), 0)
        self.assertEqual(len(fake.insert_calls), 1)  # 真的補寫了

    def test_probe_hit_means_already_there_no_duplicate_insert(self):
        cloud_resync.record_pending("memory_items", {"content": "他愛種花"})
        fake = FakeAdapter(probe_rows=[{"id": "exists"}])
        stats = cloud_resync.drain_once(adapter_factory=lambda _i: fake)
        self.assertEqual(stats["done"], 1)
        self.assertEqual(len(fake.insert_calls), 0)  # 雲端已有＝不再疊一筆

    def test_duplicate_key_error_counts_as_done(self):
        cloud_resync.record_pending("wellbeing_signals", {"mood": "calm"})
        err = supabase_adapter.SupabaseRequestError("dup", error_kind="http_error", error_code="23505")
        fake = FakeAdapter(request_error=err)
        stats = cloud_resync.drain_once(adapter_factory=lambda _i: fake)
        self.assertEqual(stats["done"], 1)
        self.assertEqual(cloud_resync.pending_count(), 0)

    def test_unreachable_stops_round_and_keeps_entries(self):
        cloud_resync.record_pending("memory_items", {"content": "a"})
        cloud_resync.record_pending("memory_items", {"content": "b"})
        err = supabase_adapter.SupabaseRequestError("down", error_kind="unreachable")
        fake = FakeAdapter(request_error=err)
        stats = cloud_resync.drain_once(adapter_factory=lambda _i: fake)
        self.assertEqual(stats["done"], 0)
        self.assertEqual(cloud_resync.pending_count(), 2)  # 一筆都不丟、下輪再來
        self.assertEqual(len(fake.insert_calls), 1)  # 第一筆撞牆就整輪睡、沒逐筆硬撞

    def test_gives_up_after_max_attempts_with_alert(self):
        cloud_resync.record_pending("conversation_summaries", {"summary": "聊了種花"})
        err = supabase_adapter.SupabaseRequestError("perm", error_kind="permission")
        fake = FakeAdapter(request_error=err)
        alerts = []
        with mock.patch.object(cloud_resync, "_alert", side_effect=lambda w, d: alerts.append(w)), \
             mock.patch.object(cloud_resync, "MAX_ATTEMPTS", 2):
            cloud_resync.drain_once(adapter_factory=lambda _i: fake)   # attempts 1
            stats = cloud_resync.drain_once(adapter_factory=lambda _i: fake)  # attempts 2 → 放棄
        self.assertEqual(stats["gaveUp"], 1)
        self.assertEqual(cloud_resync.pending_count(), 0)
        self.assertIn("cloud resync give-up", alerts)


class WiringContractTest(unittest.TestCase):
    def test_three_append_paths_queue_pending_and_no_longer_raise(self):
        with open(os.path.join(HERE, "server.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('cloud_resync.record_pending_many("memory_items"', src)
        self.assertIn('cloud_resync.record_pending("conversation_summaries"', src)
        self.assertIn('cloud_resync.record_pending("wellbeing_signals"', src)
        # 三個純疊加寫入口不再把暫時性雲端錯誤往上丟 500（退本機＋告警＋待補）
        self.assertNotIn('if data_backend().enabled() and not is_missing_table_error(e):\n            raise e\n        log_cloud_write_fallback("append memory items', src)
        self.assertIn("cloud_resync.start_worker()", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
