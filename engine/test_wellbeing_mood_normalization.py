# -*- coding: utf-8 -*-
"""心情 mood 中文→英文正規化＋舊帳救援（2026-07-20 · admin/mood-trend 上游資料缺口修復）

背景：AI 觀察（perception_engine.analyze_conversation_mood）與 App 手動打卡寫入的 mood 是中文六類
（開心／愉快／平穩／疲累／低落／煩躁），但 SupabaseAdapter._normalize_wellbeing_mood 舊版只認英文，
中文一律被寫成 unknown，讓 /admin/mood-trend 的正向/低落比例全部失真。原始中文有被留在
facts.originalMood，可以救。

這支測試涵蓋：
①中文各詞正確轉英文（寫入路徑）
②認不得的仍回 unknown
③舊資料 mood=unknown 但 facts.originalMood 有中文時，讀回會被正確歸類（後台聚合路徑）
④App 端六色編號（moodKey）行為未變、App 顯示用的中文 mood 文字也未被改壞
"""
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from supabase_adapter import SupabaseAdapter, recover_admin_wellbeing_mood  # noqa: E402


ACCOUNT = "11111111-1111-4111-8111-111111111111"
PERSON = "22222222-2222-4222-8222-222222222222"


class NormalizeWellbeingMoodChineseTests(unittest.TestCase):
    """① 中文各詞（AI 六類 + App 同義詞）寫入時要正確轉成英文 mood key。"""

    CASES = [
        ("開心", "happy"),
        ("愉快", "pleasant"),
        ("愉悅", "pleasant"),
        ("平穩", "steady"),
        ("平靜", "steady"),
        ("疲累", "tired"),
        ("低落", "low"),
        ("煩躁", "irritated"),
        ("焦慮", "irritated"),
        ("生氣", "irritated"),
        ("混合", "mixed"),
    ]

    def test_each_chinese_word_maps_to_expected_english_key(self):
        for zh, expected in self.CASES:
            with self.subTest(zh=zh):
                self.assertEqual(SupabaseAdapter._normalize_wellbeing_mood(zh), expected)

    def test_leading_trailing_whitespace_is_stripped_before_matching(self):
        self.assertEqual(SupabaseAdapter._normalize_wellbeing_mood("  開心 \n"), "happy")

    def test_already_english_values_pass_through_unchanged(self):
        for word in ("happy", "pleasant", "steady", "tired", "low", "irritated", "mixed"):
            with self.subTest(word=word):
                self.assertEqual(SupabaseAdapter._normalize_wellbeing_mood(word), word)

    def test_unrecognized_values_fall_back_to_unknown(self):
        for bad in ("孤單", "whatever", "", None, "  ", "生病"):
            with self.subTest(bad=bad):
                self.assertEqual(SupabaseAdapter._normalize_wellbeing_mood(bad), "unknown")

    def test_english_value_with_stray_whitespace_still_strips_and_matches(self):
        self.assertEqual(SupabaseAdapter._normalize_wellbeing_mood("happy "), "happy")


class WellbeingSignalToRowNormalizesChineseTests(unittest.TestCase):
    """寫入路徑整合測試：signal.mood 是中文時，實際寫進 row 的 mood 欄位要是英文，
    且中文原字要留在 facts.originalMood（給 App 顯示用，救舊帳也靠它）。"""

    def setUp(self):
        self.adapter = SupabaseAdapter(
            env={"MUNEA_DATABASE_PROVIDER": "json"},
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )

    def test_chinese_mood_normalized_to_english_row_and_kept_in_facts(self):
        row = self.adapter.wellbeing_signal_to_row({
            "accountId": ACCOUNT, "personId": PERSON, "mood": "低落", "level": 2,
        })
        self.assertEqual(row["mood"], "low")
        self.assertEqual(row["facts"]["originalMood"], "低落")


class RecoverAdminWellbeingMoodLegacyDataTests(unittest.TestCase):
    """③ 舊資料救援：row.mood 已是（污染出的）unknown，但 facts.originalMood 留著中文，
    讀回後台聚合用的 mood 要被正確換算，不再落到 other/unknown 桶。"""

    def test_load_admin_wellbeing_signals_recovers_mood_from_facts_original_mood(self):
        adapter = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )
        legacy_rows = [
            {
                "id": "wb-legacy-1", "account_id": ACCOUNT, "person_id": PERSON,
                "mood": "unknown", "level": 1, "signal_date": "2026-07-01",
                "observed_at": "2026-07-01T09:00:00Z",
                "facts": {"originalMood": "低落"},
            },
            {
                "id": "wb-legacy-2", "account_id": ACCOUNT, "person_id": PERSON,
                "mood": "unknown", "level": 5, "signal_date": "2026-07-02",
                "observed_at": "2026-07-02T09:00:00Z",
                "facts": {"originalMood": "開心"},
            },
            {
                # 真的認不得的舊資料（沒有 originalMood 可救）：仍應保持 unknown，不能亂猜
                "id": "wb-legacy-3", "account_id": ACCOUNT, "person_id": PERSON,
                "mood": "unknown", "level": 3, "signal_date": "2026-07-03",
                "observed_at": "2026-07-03T09:00:00Z",
                "facts": {},
            },
        ]
        with patch.object(adapter, "_select", return_value=legacy_rows):
            signals = adapter.load_admin_wellbeing_signals(since_iso="2026-06-01T00:00:00Z", limit=100)

        by_id = {s["id"]: s for s in signals}
        self.assertEqual(by_id["wb-legacy-1"]["mood"], "low")
        self.assertEqual(by_id["wb-legacy-2"]["mood"], "happy")
        self.assertEqual(by_id["wb-legacy-3"]["mood"], "unknown")

    def test_recover_admin_wellbeing_mood_shared_helper_checks_mood_then_facts(self):
        # signal.mood 本身就能換算（例如 JSON 備援路徑直接存中文原字）
        self.assertEqual(recover_admin_wellbeing_mood({"mood": "煩躁"}), "irritated")
        # signal.mood 是 unknown，退回 facts.originalMood
        self.assertEqual(
            recover_admin_wellbeing_mood({"mood": "unknown", "facts": {"originalMood": "疲累"}}),
            "tired",
        )
        # 兩邊都救不了，才回 unknown（不亂猜）
        self.assertEqual(recover_admin_wellbeing_mood({"mood": "unknown", "facts": {}}), "unknown")


class AppFacingBehaviorUnchangedTests(unittest.TestCase):
    """④ App 端六色編號（moodKey）行為未變；wellbeing_row_to_signal 給 App 顯示用的中文
    mood 文字也沒被這次修動壞（後台救援只發生在 load_admin_wellbeing_signals 這條路，
    不影響 App 走的 load_wellbeing_signals / wellbeing_row_to_signal 本身)。"""

    def test_wellbeing_row_to_signal_still_prefers_chinese_original_mood_for_app_display(self):
        row = {
            "mood": "happy",  # 正規化後存進 DB 的英文
            "facts": {"originalMood": "開心", "moodKey": 0},
            "level": 5,
        }
        signal = SupabaseAdapter.wellbeing_row_to_signal(row)
        self.assertEqual(signal["mood"], "開心")  # App 顯示用：中文原字，不是英文
        self.assertEqual(signal["moodKey"], 0)     # App 六色編號：不受這次修動影響

    def test_mood_key_lookup_by_row_mood_english_value_unaffected(self):
        row = {"mood": "irritated", "facts": {}, "level": 2}
        signal = SupabaseAdapter.wellbeing_row_to_signal(row)
        self.assertEqual(signal["moodKey"], 4)

    def test_admin_recovery_does_not_touch_app_facing_load_wellbeing_signals(self):
        adapter = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )
        rows = [{
            "id": "wb-app-1", "account_id": ACCOUNT, "person_id": PERSON,
            "mood": "unknown", "level": 2, "signal_date": "2026-07-01",
            "observed_at": "2026-07-01T09:00:00Z",
            "facts": {"originalMood": "低落"},
        }]
        with patch.object(adapter, "_select", return_value=rows):
            signals = adapter.load_wellbeing_signals(person_id=PERSON, limit=10)
        # App 端讀取路徑：mood 仍是中文原字，沒有被後台救援邏輯改成英文
        self.assertEqual(signals[0]["mood"], "低落")


if __name__ == "__main__":
    unittest.main()
