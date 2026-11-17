"""舊版本白養待命機器的判斷規則（deploy/cloudrun/release_stale_warm.py）。

2026-11-17：正式線 4 台白養的待命機器是這個情境的實況；規則錯一格不是多花錢，
就是把還沒驗收的候選版本的 tag 拿掉（之後 promote 會找不到）。兩邊都要鎖住。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "cloudrun"))

import release_stale_warm as sweep  # noqa: E402


def revision(name: str, created: str, min_scale: int | None = 1) -> dict:
    annotations = {} if min_scale is None else {sweep.MIN_SCALE_KEY: str(min_scale)}
    return {"metadata": {"name": name, "creationTimestamp": created, "annotations": annotations}}


def service(*traffic: dict) -> dict:
    return {"status": {"traffic": list(traffic)}}


def entry(name: str, percent: int = 0, tag: str | None = None) -> dict:
    item = {"revisionName": name}
    if percent:
        item["percent"] = percent
    if tag:
        item["tag"] = tag
    return item


class StaleWarmTagTests(unittest.TestCase):
    def test_real_incident_shape_releases_only_the_superseded_warm_revisions(self) -> None:
        # 2026-11-17 munea-brain 實況：00198 在服務，00192／00194／00196 各白養一台。
        revisions = [
            revision("brain-00190", "2026-10-29T02:13:00Z", min_scale=None),  # 舊到還沒設待命
            revision("brain-00192", "2026-10-29T05:36:00Z"),
            revision("brain-00194", "2026-10-29T07:21:00Z"),
            revision("brain-00196", "2026-11-05T06:37:00Z"),
            revision("brain-00198", "2026-11-08T06:52:00Z"),
        ]
        svc = service(
            entry("brain-00190", tag="prod-1029-a"),
            entry("brain-00192", tag="prod-1029-b"),
            entry("brain-00194", tag="prod-1029-c"),
            entry("brain-00196", tag="prod-1105"),
            entry("brain-00198", percent=100, tag="prod-1108"),
        )
        stale = sweep.stale_warm_tags(svc, revisions)
        self.assertEqual([item["tag"] for item in stale], ["prod-1029-b", "prod-1029-c", "prod-1105"])
        self.assertEqual({item["revision"] for item in stale}, {"brain-00192", "brain-00194", "brain-00196"})

    def test_serving_revision_keeps_its_tag(self) -> None:
        revisions = [revision("r1", "2026-11-01T00:00:00Z")]
        self.assertEqual(sweep.stale_warm_tags(service(entry("r1", percent=100, tag="prod-a")), revisions), [])

    def test_newer_unpromoted_candidate_is_never_touched(self) -> None:
        # 等真機驗收的候選版本比正式版新；拿掉它的 tag，promote 就找不到它了。
        revisions = [
            revision("old", "2026-11-01T00:00:00Z"),
            revision("live", "2026-11-08T00:00:00Z"),
            revision("candidate", "2026-11-13T00:00:00Z"),
        ]
        svc = service(
            entry("old", tag="prod-old"),
            entry("live", percent=100, tag="prod-live"),
            entry("candidate", tag="prod-next"),
        )
        self.assertEqual([item["tag"] for item in sweep.stale_warm_tags(svc, revisions)], ["prod-old"])

    def test_revision_without_min_instances_costs_nothing_and_is_left_alone(self) -> None:
        revisions = [
            revision("voice-old", "2026-11-01T00:00:00Z", min_scale=0),
            revision("voice-older", "2026-10-01T00:00:00Z", min_scale=None),
            revision("voice-live", "2026-11-08T00:00:00Z", min_scale=0),
        ]
        svc = service(
            entry("voice-old", tag="t1"),
            entry("voice-older", tag="t2"),
            entry("voice-live", percent=100),
        )
        self.assertEqual(sweep.stale_warm_tags(svc, revisions), [])

    def test_split_traffic_uses_the_oldest_serving_revision_as_the_line(self) -> None:
        revisions = [
            revision("a", "2026-11-01T00:00:00Z"),
            revision("b", "2026-11-05T00:00:00Z"),
            revision("c", "2026-11-08T00:00:00Z"),
            revision("between", "2026-11-06T00:00:00Z"),
        ]
        svc = service(
            entry("a", tag="ta"),
            entry("b", percent=50, tag="tb"),
            entry("c", percent=50, tag="tc"),
            entry("between", tag="tm"),
        )
        # 「between」比其中一個正在服務的版本新——保守起見不碰。
        self.assertEqual([item["tag"] for item in sweep.stale_warm_tags(svc, revisions)], ["ta"])

    def test_unknown_live_state_touches_nothing(self) -> None:
        revisions = [revision("old", "2026-11-01T00:00:00Z")]
        # 沒有任何版本在服務（或正在服務的版本查不到資料）＝看不懂現況，一個都不動。
        self.assertEqual(sweep.stale_warm_tags(service(entry("old", tag="t")), revisions), [])
        self.assertEqual(
            sweep.stale_warm_tags(service(entry("old", tag="t"), entry("ghost", percent=100)), revisions), []
        )

    def test_garbage_min_scale_is_treated_as_zero(self) -> None:
        bad = revision("old", "2026-11-01T00:00:00Z")
        bad["metadata"]["annotations"][sweep.MIN_SCALE_KEY] = "many"
        revisions = [bad, revision("live", "2026-11-08T00:00:00Z")]
        svc = service(entry("old", tag="t"), entry("live", percent=100))
        self.assertEqual(sweep.stale_warm_tags(svc, revisions), [])


class PromoteHookTests(unittest.TestCase):
    """promote.sh 要在上線成功後叫它，而且叫失敗不能讓上線變成失敗。"""

    def test_promote_calls_the_sweep_after_success_and_never_fails_on_it(self) -> None:
        text = (ROOT / "deploy" / "cloudrun" / "promote.sh").read_text(encoding="utf-8")
        done = text.index("✅ DONE")
        hook = text.index("release_stale_warm.py")
        self.assertGreater(hook, done, "收待命機器要排在確認上線成功之後")
        tail = text[hook:hook + 400]
        self.assertIn("--apply", tail)
        self.assertIn("||", tail, "收不乾淨只能警告，不能讓這次上線報失敗")


if __name__ == "__main__":
    unittest.main(verbosity=2)
