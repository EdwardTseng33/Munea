"""展示機要有人收 · 守門測試（2026-08-10）。

Edward 追究「為什麼沒有人去關」時查出來的洞：

  官網那支 /api/call-key **確實**寫了 TTL，但那段只有「下一個訪客上門」才會跑到。
  一個客人看完就走、沒有下一個人來，展示機就永遠開著——$0.74/hr，一個月
  NT$17,000。備援線有 munea-runpod-controller 每 15 秒巡一次，展示機完全沒人管。

  同一天還查出第二件事：官網找的機器叫 munea-flashhead-demo-768-r6000ada，
  我們的工具開的叫 munea-flashhead-demo-768。**兩邊看不到彼此的機器**——已經有
  一台在跑，官網還會再開第二台，而且誰也收不掉誰。Edward 拍板不要再用帶顯卡型號
  的名字（實際開到哪張卡看主控台，名字寫死型號只會騙人）。

這支釘住修法：管家會按時間收展示機，而且比對條件不能鬆掉。
"""
import datetime
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "deploy", "runpod-avatar"))

import runpod_backup  # noqa: E402

CALL_KEY_JS = os.path.join(REPO, "munea-b2b", "api", "call-key.js")
DEMOCTL_PY = os.path.join(REPO, "deploy", "runpod-demo", "democtl.py")

NOW = datetime.datetime(2026, 8, 10, 10, 0, 0, tzinfo=datetime.timezone.utc).timestamp()


class _FakeProvider:
    def __init__(self, named):
        self._named = named
        self.listed_names = []

    def list_named(self, name):
        self.listed_names.append(name)
        return list(self._named)

    def list(self):
        return []


class PodAgeParsing(unittest.TestCase):
    def test_runpod_timestamp_shapes(self):
        self.assertAlmostEqual(
            runpod_backup.pod_age_seconds(
                {"lastStartedAt": "2026-08-10 09:00:00.000 +0000 UTC"}, NOW), 3600, delta=1)
        self.assertAlmostEqual(
            runpod_backup.pod_age_seconds(
                {"lastStartedAt": "2026-08-10T09:30:00+00:00"}, NOW), 1800, delta=1)

    def test_unreadable_time_is_none_not_zero(self):
        """看不懂時間要回「不知道」。回 0 會讓機器永遠不被收，
        回一個大數字會砍掉別人正在展示的機器——兩邊都不能猜。"""
        self.assertIsNone(runpod_backup.pod_age_seconds({}, NOW))
        self.assertIsNone(runpod_backup.pod_age_seconds({"lastStartedAt": "亂寫的"}, NOW))


class DemoReaper(unittest.TestCase):
    def _controller(self, pods, ttl=1800, mode="active"):
        config = runpod_backup.Config(
            mode=mode, demo_ttl_seconds=ttl, demo_pod_name="munea-flashhead-demo-768")
        controller = runpod_backup.BackupController.__new__(runpod_backup.BackupController)
        controller.config = config
        controller.provider = _FakeProvider(pods)
        return controller

    def test_old_demo_pod_is_terminated(self):
        killed = []
        old_terminate = runpod_backup.podctl.terminate_pod
        runpod_backup.podctl.terminate_pod = lambda pid: killed.append(pid)
        try:
            c = self._controller([{
                "id": "abc123", "name": "munea-flashhead-demo-768",
                "desiredStatus": "RUNNING",
                "lastStartedAt": "2026-08-10 09:00:00.000 +0000 UTC",  # 開了 1 小時
            }])
            event = c._reap_demo_pod(NOW)
        finally:
            runpod_backup.podctl.terminate_pod = old_terminate
        self.assertIsNotNone(event, "展示機開了一小時還沒被收")
        self.assertEqual(event["action"], "reaped_demo_pod")
        self.assertEqual(killed, ["abc123"])

    def test_young_demo_pod_is_left_alone(self):
        c = self._controller([{
            "id": "abc123", "name": "munea-flashhead-demo-768",
            "desiredStatus": "RUNNING",
            "lastStartedAt": "2026-08-10 09:55:00.000 +0000 UTC",  # 才 5 分鐘
        }])
        self.assertIsNone(c._reap_demo_pod(NOW), "剛開 5 分鐘就被砍——客人會斷在半路")

    def test_unknown_age_is_never_killed(self):
        """讀不出年紀就不動它。寧可多燒一輪，也不要砍掉正在展示的機器。"""
        c = self._controller([{
            "id": "abc123", "name": "munea-flashhead-demo-768",
            "desiredStatus": "RUNNING", "lastStartedAt": "",
        }])
        self.assertIsNone(c._reap_demo_pod(NOW))

    def test_matches_by_exact_name_not_prefix(self):
        """一定要用「名字完全相等」找展示機。用開頭比會咬到別條線的機器。"""
        c = self._controller([])
        c._reap_demo_pod(NOW)
        self.assertEqual(c.provider.listed_names, ["munea-flashhead-demo-768"])
        src = open(os.path.join(REPO, "deploy", "runpod-avatar", "runpod_backup.py"),
                   encoding="utf-8").read()
        at = src.index("def list_named")
        body = src[at:at + 500]
        self.assertIn('== name', body, "改成用開頭比對了——會誤刪別條線的機器")

    def test_observe_mode_never_kills(self):
        c = self._controller([{
            "id": "abc123", "name": "munea-flashhead-demo-768",
            "desiredStatus": "RUNNING",
            "lastStartedAt": "2026-08-10 09:00:00.000 +0000 UTC",
        }], mode="observe")
        self.assertIsNone(c._reap_demo_pod(NOW), "唯讀模式不可以真的動手刪機器")

    def test_reaper_runs_before_the_backup_logic(self):
        """展示機不該因為備援線今天沒事做就沒人管——收展示機要排在最前面。"""
        src = open(os.path.join(REPO, "deploy", "runpod-avatar", "runpod_backup.py"),
                   encoding="utf-8").read()
        at = src.index("def run_once")
        body = src[at:at + 900]
        self.assertLess(
            body.index("_reap_demo_pod"), body.index("self.gateway.snapshot()"),
            "收展示機被排到備援線邏輯後面了",
        )


class DemoPodNameMustNotDrift(unittest.TestCase):
    """官網跟工具必須叫同一個名字，而且不准帶顯卡型號（Edward 2026-08-10 拍板）。"""

    EXPECTED = "munea-flashhead-demo-768"

    def _js(self):
        return open(CALL_KEY_JS, encoding="utf-8").read()

    def test_site_uses_the_neutral_name(self):
        src = self._js()
        m = re.search(r"const DEMO_POD_NAME = '([^']+)'", src)
        self.assertTrue(m, "官網那支找不到展示機名字的定義")
        self.assertEqual(m.group(1), self.EXPECTED)

    def test_no_gpu_model_in_any_pod_name(self):
        """名字帶型號會騙人——規格本來就允許 6000 Ada 或 4090，實際開到哪張看主控台。"""
        for path in (CALL_KEY_JS, DEMOCTL_PY,
                     os.path.join(REPO, "deploy", "runpod-avatar", "runpod_backup.py")):
            with self.subTest(path=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                # 只看「名字」那幾行，註解裡寫歷史沿革是允許的
                for line in src.splitlines():
                    if "POD_NAME" in line and "=" in line and not line.strip().startswith("#"):
                        self.assertNotRegex(
                            line, r"r6000ada|rtx4090|6000ada",
                            f"機器名字又帶回顯卡型號了：{line.strip()}",
                        )

    def test_democtl_uses_the_same_name(self):
        src = open(DEMOCTL_PY, encoding="utf-8").read()
        m = re.search(r'MUNEA_RUNPOD_DEMO_NAME", "([^"]+)"', src)
        self.assertTrue(m, "democtl 找不到展示機名字")
        self.assertEqual(m.group(1), self.EXPECTED,
                         "工具跟官網又叫不同名字了——兩邊會看不到彼此的機器")

    def test_controller_default_matches_too(self):
        self.assertEqual(runpod_backup.Config().demo_pod_name, self.EXPECTED)


class TtlMustStaySane(unittest.TestCase):
    def test_site_and_controller_share_the_same_ttl(self):
        js = open(CALL_KEY_JS, encoding="utf-8").read()
        m = re.search(r"const DEFAULT_TTL_SECONDS = (\d+)", js)
        self.assertTrue(m, "官網那支沒有預設 TTL")
        self.assertEqual(int(m.group(1)), runpod_backup.Config().demo_ttl_seconds,
                         "兩邊 TTL 不一樣——會出現一邊覺得該收、一邊覺得還早")

    def test_ttl_is_not_hours_long(self):
        """展示通話上限 180 秒。TTL 三小時等於一次展示要付 2.2 美金。"""
        self.assertLessEqual(runpod_backup.Config().demo_ttl_seconds, 3600)
        self.assertGreaterEqual(runpod_backup.Config().demo_ttl_seconds, 600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
