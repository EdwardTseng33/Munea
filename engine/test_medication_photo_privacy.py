#!/usr/bin/env python3
"""用藥照片不得離開使用者裝置。

隱私政策（https://app.munea.net/privacy）對外承諾：
「用藥照片…只儲存在你的裝置本機，不會上傳雲端，也不會與家人共享。」
App Store Connect 的 App Privacy 問卷亦據此填答。

2026-07-09 的隱私修正只補了 /family/state 那條路，漏掉 /routine-reminders，
照片仍持續上雲近一週無人發現。本測試守住伺服器端這道底線——
它擋的是「所有」客戶端，包含已經裝在使用者手機上、還會夾帶照片的舊版 App。
"""
import os
import sys
import unittest

os.environ.setdefault("GEMINI_API_KEY", "medication-photo-privacy-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402


TINY_JPEG_DATA_URL = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA=="


class MedicationPhotoPrivacyTests(unittest.TestCase):
    def test_photo_is_stripped_from_schedule(self):
        """舊版 App 夾帶的 base64 照片必須被剝除，不得落庫。"""
        result = server.normalize_routine_reminder({
            "id": "med_abc",
            "title": "降血壓藥",
            "type": "medication",
            "schedule": {
                "slotLabels": ["早上"],
                "days": "長期",
                "photo": TINY_JPEG_DATA_URL,
                "source": "munea-web",
            },
        })
        self.assertNotIn("photo", result["schedule"])

    def test_other_schedule_fields_survive(self):
        """只剝照片，其餘提醒欄位照常保留（別把功能剝壞）。"""
        result = server.normalize_routine_reminder({
            "id": "med_abc",
            "title": "降血壓藥",
            "type": "medication",
            "schedule": {
                "slotLabels": ["早上", "晚上"],
                "days": "長期",
                "by": "美華",
                "photo": TINY_JPEG_DATA_URL,
                "source": "munea-web",
            },
        })
        schedule = result["schedule"]
        self.assertEqual(schedule["slotLabels"], ["早上", "晚上"])
        self.assertEqual(schedule["days"], "長期")
        self.assertEqual(schedule["by"], "美華")
        self.assertEqual(schedule["source"], "munea-web")

    def test_reminder_without_photo_is_unaffected(self):
        """沒帶照片的提醒不受影響。"""
        result = server.normalize_routine_reminder({
            "id": "visit_1",
            "title": "回診",
            "type": "check_in",
            "schedule": {"date": "2026-08-01", "time": "09:30"},
        })
        self.assertNotIn("photo", result["schedule"])
        self.assertEqual(result["schedule"]["date"], "2026-08-01")

    def test_no_photo_anywhere_in_serialized_payload(self):
        """整包序列化後不得殘留任何 base64 影像——防止照片藏在別的欄位。"""
        import json
        result = server.normalize_routine_reminder({
            "id": "med_abc",
            "title": "降血壓藥",
            "type": "medication",
            "schedule": {"photo": TINY_JPEG_DATA_URL, "slotLabels": ["早上"]},
        })
        self.assertNotIn("data:image/", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
