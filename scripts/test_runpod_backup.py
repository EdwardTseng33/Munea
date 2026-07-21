# -*- coding: utf-8 -*-
"""CPU-only tests for the RunPod backup controller. No API calls or GPU spend."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))

import podctl  # noqa: E402
import runpod_backup as rb  # noqa: E402


class Clock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value


def test_pod_status_redacts_secret_environment_values():
    source = {
        "id": "pod-1",
        "env": {
            "JUPYTER_PASSWORD": "do-not-print",
            "MUNEA_CALL_TOKEN_SECRET": "do-not-print-either",
            "MUNEA_FH_FRAME_SIZE": "768",
        },
    }
    safe = podctl.redact_pod_for_output(source)
    assert safe["env"]["JUPYTER_PASSWORD"] == "[redacted]"
    assert safe["env"]["MUNEA_CALL_TOKEN_SECRET"] == "[redacted]"
    assert safe["env"]["MUNEA_FH_FRAME_SIZE"] == "768"
    assert source["env"]["JUPYTER_PASSWORD"] == "do-not-print"


class FakeGateway:
    def __init__(self, workers, queue_depth=0):
        self.workers = [dict(worker) for worker in workers]
        self.queue_depth = queue_depth
        self.calls = []

    def snapshot(self):
        ready = [w for w in self.workers if w.get("healthy") and w.get("enabled")]
        return {
            "workers": {"workers": [dict(w) for w in self.workers]},
            "queue_depth": self.queue_depth,
            "joint_free": sum(max(0, w["slots"] - w["active"]) for w in ready),
        }

    def register(self, worker_id, url, slots, region):
        self.calls.append(("register", worker_id))
        self.workers.append({
            "worker_id": worker_id, "url": url, "slots": slots, "active": 0,
            "healthy": True, "enabled": True, "region": region, "kind": "runpod",
        })

    def health(self, worker_id, healthy, active=None):
        self.calls.append(("health", worker_id, healthy, active))
        for worker in self.workers:
            if worker["worker_id"] == worker_id:
                worker["healthy"] = healthy
                if active is not None:
                    worker["active"] = active

    def enabled(self, worker_id, enabled):
        self.calls.append(("enabled", worker_id, enabled))
        for worker in self.workers:
            if worker["worker_id"] == worker_id:
                worker["enabled"] = enabled

    def unregister(self, worker_id):
        self.calls.append(("unregister", worker_id))
        self.workers = [w for w in self.workers if w["worker_id"] != worker_id]


class FakeProvider:
    def __init__(self):
        self.ensure_calls = 0
        self.down_calls = []
        self.pods = []
        self.last_excluded = set()

    def list(self):
        return [dict(pod) for pod in self.pods]

    def ensure_ready_many(self, count, timeout_s, poll_s, exclude_ids=None):
        self.ensure_calls += count
        excluded = set(exclude_ids or ())
        self.last_excluded = excluded
        pods = []
        index = 1
        while len(pods) < count:
            pod_id = f"pod-{index}"
            index += 1
            if pod_id in excluded:
                continue
            pods.append({"id": pod_id, "machine": {"dataCenterId": "AP-JP-1"}})
        return pods

    def worker_url(self, pod_id):
        return f"https://{pod_id}-8188.proxy.runpod.net"

    def scale_down(self, pod_id, action):
        self.down_calls.append((pod_id, action))


def primary(active=0, healthy=True):
    return {
        "worker_id": "glows-main", "url": "https://glows", "slots": 3,
        "active": active, "healthy": healthy, "enabled": True,
        "region": "TW", "kind": "glows",
    }


def backup(active=0, index=1):
    return {
        "worker_id": f"runpod-pod-{index}", "url": f"https://runpod-{index}", "slots": 2,
        "active": active, "healthy": True, "enabled": True,
        "region": "AP-JP-1", "kind": "runpod",
    }


def make_config(tmp, mode="active", idle=10, cooldown=0, failures=3):
    return rb.Config(
        mode=mode, idle_seconds=idle, cooldown_seconds=cooldown,
        scale_up_cooldown_seconds=0,
        failure_threshold=failures,
        state_file=str(Path(tmp) / "state.json"), lock_file=str(Path(tmp) / "lock"),
    )


def probe_counts(primary_active=0, backup_active=0):
    def probe(url, key):
        active = primary_active if "glows" in url else backup_active
        return {"ok": True, "capacity": {"active": active}}
    return probe


def test_spec_requires_baked_template():
    old = os.environ.pop("MUNEA_RUNPOD_TEMPLATE_ID", None)
    try:
        try:
            podctl.build_pod_spec(require_template=True)
            raise AssertionError("missing template must fail closed")
        except podctl.RunPodError:
            pass
        spec = podctl.build_pod_spec(require_template=False)
        assert spec["gpuCount"] == 1
        assert spec["volumeInGb"] == 0
        assert spec["ports"] == ["8188/http", "22/tcp"]
    finally:
        if old is not None:
            os.environ["MUNEA_RUNPOD_TEMPLATE_ID"] = old


def test_manual_pod_can_be_adopted_by_backup_controller():
    spec = podctl.backup_update_spec()
    assert spec["name"].startswith("munea-vocaframe-backup")
    assert spec["ports"] == ["8188/http", "8888/http", "22/tcp"]
    assert spec["locked"] is False


def test_stopped_pod_without_host_is_recreated_from_template():
    calls = []
    provider = rb.RunPodProvider("munea-vocaframe-backup", now=Clock())
    provider.list = lambda: [{"id": "old-pod", "desiredStatus": "EXITED"}]
    originals = {
        "start": podctl.start_pod,
        "terminate": podctl.terminate_pod,
        "create": podctl.create_pod,
        "get": podctl.get_pod,
        "http": rb._http_json,
    }
    try:
        podctl.start_pod = lambda pod_id: (_ for _ in ()).throw(
            podctl.RunPodError("not enough free GPUs")
        )
        podctl.terminate_pod = lambda pod_id: calls.append(("terminate", pod_id)) or {}
        podctl.create_pod = lambda spec=None, require_template=True: {
            "id": "new-pod", "desiredStatus": "RUNNING"
        }
        podctl.get_pod = lambda pod_id: {"id": pod_id, "desiredStatus": "RUNNING"}
        rb._http_json = lambda method, url, timeout=10: {
            "ok": True, "capacity": {"ready": True}
        }
        result = provider.ensure_ready(timeout_s=5, poll_s=0)
        assert result["id"] == "new-pod"
        assert calls == [("terminate", "old-pod")]
    finally:
        podctl.start_pod = originals["start"]
        podctl.terminate_pod = originals["terminate"]
        podctl.create_pod = originals["create"]
        podctl.get_pod = originals["get"]
        rb._http_json = originals["http"]


def test_primary_free_does_not_open_backup():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = FakeGateway([primary(active=0)])
        provider = FakeProvider()
        controller = rb.BackupController(make_config(tmp), gateway, provider, Clock(),
                                         probe=lambda url, key: {"ok": True, "capacity": {"active": 0}})
        result = controller.run_once()
        assert result["action"] == "no_change"
        assert provider.ensure_calls == 0


def test_queue_opens_and_registers_one_backup():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = FakeGateway([primary(active=3)], queue_depth=1)
        provider = FakeProvider()
        controller = rb.BackupController(make_config(tmp), gateway, provider, Clock(),
                                         probe=probe_counts(primary_active=3))
        result = controller.run_once()
        assert result["action"] == "scaled_up"
        assert result["reason"] == "queue_waiting"
        assert provider.ensure_calls == 1
        assert gateway.calls[-1] == ("register", "runpod-pod-1")


def test_terminated_gateway_record_does_not_block_pod_reuse():
    with tempfile.TemporaryDirectory() as tmp:
        retired = backup(active=0)
        retired.update({"healthy": False, "enabled": False, "status": "terminated"})
        gateway = FakeGateway([primary(active=3), retired], queue_depth=1)
        provider = FakeProvider()
        controller = rb.BackupController(make_config(tmp), gateway, provider, Clock(),
                                         probe=probe_counts(primary_active=3))
        result = controller.run_once()
        assert result["action"] == "scaled_up"
        assert "pod-1" not in provider.last_excluded


def test_stopped_runpod_is_retired_without_health_probe():
    with tempfile.TemporaryDirectory() as tmp:
        stopped = backup(active=0)
        gateway = FakeGateway([primary(active=0), stopped])
        provider = FakeProvider()
        provider.pods = [{"id": "pod-1", "desiredStatus": "EXITED"}]
        probes = []
        controller = rb.BackupController(
            make_config(tmp), gateway, provider, Clock(),
            probe=lambda url, key: probes.append(url) or {
                "ok": True, "capacity": {"active": 0},
            },
        )
        result = controller.run_once()
        assert result["action"] == "no_change"
        assert probes == ["https://glows"]
        assert ("unregister", "runpod-pod-1") in gateway.calls
        assert not any(
            call[:3] == ("health", "runpod-pod-1", False)
            for call in gateway.calls
        )


def test_terminated_runpod_is_skipped_without_health_probe():
    with tempfile.TemporaryDirectory() as tmp:
        retired = backup(active=0)
        retired.update({"healthy": False, "enabled": False, "status": "terminated"})
        gateway = FakeGateway([primary(active=0), retired])
        provider = FakeProvider()
        probes = []
        controller = rb.BackupController(
            make_config(tmp), gateway, provider, Clock(),
            probe=lambda url, key: probes.append(url) or {
                "ok": True, "capacity": {"active": 0},
            },
        )
        result = controller.run_once()
        assert result["action"] == "no_change"
        assert probes == ["https://glows"]
        assert not any(call[0] == "health" and call[1] == "runpod-pod-1" for call in gateway.calls)


def test_running_runpod_is_still_health_checked():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = FakeGateway([primary(active=0), backup(active=0)])
        provider = FakeProvider()
        provider.pods = [{"id": "pod-1", "desiredStatus": "RUNNING"}]
        probes = []
        controller = rb.BackupController(
            make_config(tmp), gateway, provider, Clock(),
            probe=lambda url, key: probes.append(url) or {
                "ok": True, "capacity": {"active": 0},
            },
        )
        controller.run_once()
        assert probes == ["https://glows", "https://runpod-1"]
        assert ("health", "runpod-pod-1", True, 0) in gateway.calls


def test_observe_mode_never_spends():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = FakeGateway([primary(active=3)], queue_depth=1)
        provider = FakeProvider()
        controller = rb.BackupController(make_config(tmp, mode="observe"), gateway, provider, Clock(),
                                         probe=probe_counts(primary_active=3))
        result = controller.run_once()
        assert result["action"] == "would_scale_up"
        assert provider.ensure_calls == 0


def test_primary_outage_opens_backup():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = FakeGateway([primary(healthy=False)])
        provider = FakeProvider()
        controller = rb.BackupController(make_config(tmp, failures=1), gateway, provider, Clock(),
                                         probe=lambda url, key: (_ for _ in ()).throw(RuntimeError("down")))
        result = controller.run_once()
        assert result["action"] == "scaled_up"
        assert result["reason"] == "primary_unavailable"


def test_idle_backup_drains_then_stops():
    with tempfile.TemporaryDirectory() as tmp:
        clock = Clock()
        gateway = FakeGateway([primary(active=0), backup(active=0)])
        provider = FakeProvider()
        controller = rb.BackupController(make_config(tmp, idle=10), gateway, provider, clock,
                                         probe=lambda url, key: {"ok": True, "capacity": {
                                             "active": 1 if "runpod" in url and False else 0}})
        assert controller.run_once()["action"] == "idle_timers_started"
        clock.value += 11
        result = controller.run_once()
        assert result["action"] == "scaled_down"
        assert provider.down_calls == [("pod-1", "stop")]
        assert ("enabled", "runpod-pod-1", False) in gateway.calls
        assert ("unregister", "runpod-pod-1") in gateway.calls


def test_active_backup_is_never_scaled_down():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = FakeGateway([primary(active=0), backup(active=1)])
        provider = FakeProvider()
        controller = rb.BackupController(make_config(tmp, idle=0), gateway, provider, Clock(),
                                         probe=lambda url, key: {"ok": True, "capacity": {
                                             "active": 1 if "runpod" in url else 0}})
        assert controller.run_once()["action"] == "no_change"
        assert provider.down_calls == []


def test_orphan_managed_pod_is_stopped():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = FakeGateway([primary(active=0)])
        provider = FakeProvider()
        provider.pods = [{"id": "orphan-1", "desiredStatus": "RUNNING"}]
        controller = rb.BackupController(make_config(tmp), gateway, provider, Clock(),
                                         probe=lambda url, key: {"ok": True, "capacity": {"active": 0}})
        result = controller.run_once()
        assert result["action"] == "cleaned_orphan_pod"
        assert provider.down_calls == [("orphan-1", "stop")]


def test_gateway_registration_failure_terminates_new_pod():
    class BrokenGateway(FakeGateway):
        def register(self, worker_id, url, slots, region):
            raise RuntimeError("gateway unavailable")

    with tempfile.TemporaryDirectory() as tmp:
        gateway = BrokenGateway([primary(active=3)], queue_depth=1)
        provider = FakeProvider()
        controller = rb.BackupController(make_config(tmp), gateway, provider, Clock(),
                                         probe=probe_counts(primary_active=3))
        try:
            controller.run_once()
            raise AssertionError("registration failure must surface")
        except RuntimeError:
            pass
        assert provider.down_calls == [("pod-1", "stop")]


def test_durable_snapshot_normalization():
    snapshot = {
        "workers": [{
            "worker_id": "glows-main", "url": "https://glows",
            "provider": "glows", "status": "ready", "capacity": 3,
            "active_leases": 2,
        }],
        "avatar_active": 2,
        "queue_depth": 0,
    }
    workers = rb._workers(snapshot)
    assert workers[0]["kind"] == "glows"
    assert workers[0]["slots"] == 3
    assert workers[0]["active"] == 2
    assert workers[0]["healthy"] is True
    assert workers[0]["enabled"] is True


def test_capacity_plan_for_1_3_4_10_30_callers():
    with tempfile.TemporaryDirectory() as tmp:
        config = make_config(tmp)

        def planned(active, queued):
            gateway = FakeGateway([primary(active=active)], queue_depth=queued)
            return rb.desired_backup_pods(gateway.snapshot(), config)[0]

        assert planned(1, 0) == 0
        assert planned(3, 0) == 1  # warm before caller 4 is forced to wait
        assert planned(3, 1) == 1
        assert planned(3, 7) == 4
        assert planned(3, 27) == 14


def test_thirty_call_burst_scales_in_bounded_batches():
    with tempfile.TemporaryDirectory() as tmp:
        gateway = FakeGateway([primary(active=3)], queue_depth=27)
        provider = FakeProvider()
        controller = rb.BackupController(
            make_config(tmp), gateway, provider, Clock(),
            probe=probe_counts(primary_active=3),
        )
        first = controller.run_once()
        assert first["action"] == "scaled_up"
        assert first["desired_pods"] == 14
        assert first["scale_up_count"] == 4
        assert len(first["pod_ids"]) == 4

        second = controller.run_once()
        assert second["action"] == "scaled_up"
        assert second["desired_pods"] == 14
        assert second["scale_up_count"] == 4
        assert len(set(first["pod_ids"] + second["pod_ids"])) == 8


def test_scale_up_registration_failure_rolls_back_entire_batch():
    class BrokenGateway(FakeGateway):
        def register(self, worker_id, url, slots, region):
            if worker_id.endswith("pod-2"):
                raise RuntimeError("gateway unavailable")
            super().register(worker_id, url, slots, region)

    with tempfile.TemporaryDirectory() as tmp:
        gateway = BrokenGateway([primary(active=3)], queue_depth=7)
        provider = FakeProvider()
        controller = rb.BackupController(
            make_config(tmp), gateway, provider, Clock(),
            probe=probe_counts(primary_active=3),
        )
        try:
            controller.run_once()
            raise AssertionError("batch registration failure must surface")
        except RuntimeError:
            pass
        assert ("unregister", "runpod-pod-1") in gateway.calls
        assert provider.down_calls == [
            ("pod-1", "stop"), ("pod-2", "stop"),
            ("pod-3", "stop"), ("pod-4", "stop"),
        ]


def main():
    old = os.environ.get("MUNEA_RUNPOD_TEMPLATE_ID")
    os.environ["MUNEA_RUNPOD_TEMPLATE_ID"] = "tpl-test"
    try:
        tests = [
            test_pod_status_redacts_secret_environment_values,
            test_spec_requires_baked_template,
            test_manual_pod_can_be_adopted_by_backup_controller,
            test_stopped_pod_without_host_is_recreated_from_template,
            test_primary_free_does_not_open_backup,
            test_queue_opens_and_registers_one_backup,
            test_terminated_gateway_record_does_not_block_pod_reuse,
            test_stopped_runpod_is_retired_without_health_probe,
            test_terminated_runpod_is_skipped_without_health_probe,
            test_running_runpod_is_still_health_checked,
            test_observe_mode_never_spends,
            test_primary_outage_opens_backup,
            test_idle_backup_drains_then_stops,
            test_active_backup_is_never_scaled_down,
            test_orphan_managed_pod_is_stopped,
            test_gateway_registration_failure_terminates_new_pod,
            test_durable_snapshot_normalization,
            test_capacity_plan_for_1_3_4_10_30_callers,
            test_thirty_call_burst_scales_in_bounded_batches,
            test_scale_up_registration_failure_rolls_back_entire_batch,
        ]
        for test in tests:
            test()
            print(test.__name__ + ": PASS")
        print("RunPod backup controller tests: ALL PASS")
    finally:
        if old is None:
            os.environ.pop("MUNEA_RUNPOD_TEMPLATE_ID", None)
        else:
            os.environ["MUNEA_RUNPOD_TEMPLATE_ID"] = old


if __name__ == "__main__":
    main()
