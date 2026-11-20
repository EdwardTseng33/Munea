"""Deterministic tests for phase-1 Gateway capacity monitoring."""

from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "deploy" / "gateway"
sys.path.insert(0, str(GATEWAY_DIR))

import monitor  # noqa: E402
import slack_notify  # noqa: E402


NOW = dt.datetime(2026, 7, 14, 8, 0, tzinfo=dt.timezone.utc).timestamp()


def healthy_result(**metric_overrides: float) -> monitor.PollResult:
    metrics = {
        "munea_call_queue_depth": 0.0,
        "munea_avatar_capacity": 10.0,
        "munea_avatar_active": 2.0,
        "munea_voice_capacity": 10.0,
        "munea_voice_active": 2.0,
    }
    metrics.update(metric_overrides)
    return monitor.PollResult(
        health={
            "ok": True,
            "mode": "durable",
            "durable_ready": True,
            "durable_error": "",
            "snapshot": {"workers": []},
        },
        metrics=metrics,
    )


class MetricsTests(unittest.TestCase):
    def test_parse_prometheus_metrics(self) -> None:
        parsed = monitor.parse_prometheus_metrics(
            "# HELP ignored comment\n"
            "munea_avatar_capacity 5\n"
            "munea_call_queue_depth{region=\"TW\"} 2\n"
        )
        self.assertEqual(parsed, {
            "munea_avatar_capacity": 5.0,
            "munea_call_queue_depth": 2.0,
        })

    def test_invalid_metric_value_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 1"):
            monitor.parse_prometheus_metrics("munea_avatar_capacity nope\n")


class Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self.body


class GatewayClientTests(unittest.TestCase):
    def test_poll_fetches_health_and_metrics_with_admin_bearer(self) -> None:
        requests: list[tuple[str, str, float]] = []

        def opener(request: object, *, timeout: float) -> Response:
            url = request.full_url
            requests.append((url, request.get_header("Authorization"), timeout))
            if url.endswith("/health"):
                return Response(b'{"ok":true,"mode":"durable","durable_ready":true}')
            return Response(b"munea_avatar_capacity 3")

        client = monitor.GatewayClient(
            "https://gateway.test/",
            admin_key="admin-secret",
            timeout_seconds=4.0,
            opener=opener,
        )
        result = client.poll()
        self.assertEqual(result.health["durable_ready"], True)
        self.assertEqual(result.metrics["munea_avatar_capacity"], 3.0)
        self.assertEqual(requests, [
            ("https://gateway.test/health", "Bearer admin-secret", 4.0),
            ("https://gateway.test/metrics", "Bearer admin-secret", 4.0),
        ])
        self.assertEqual(result.worker_clock_checks, {})

    def test_poll_skips_worker_clock_probing_without_a_configured_key(self) -> None:
        """STATUS 125 defense line 2 is opt-in: unset MUNEA_APP_KEY must
        leave this monitor byte-for-byte unchanged (no extra requests)."""
        requests: list[str] = []

        def opener(request: object, *, timeout: float) -> Response:
            requests.append(request.full_url)
            if request.full_url.endswith("/health"):
                return Response(json.dumps({
                    "ok": True,
                    "snapshot": {"workers": [
                        {"worker_id": "gpu-1", "url": "https://gpu-1.example"},
                    ]},
                }).encode("utf-8"))
            return Response(b"")

        client = monitor.GatewayClient(
            "https://gateway.test/", timeout_seconds=4.0, opener=opener,
        )
        result = client.poll()
        self.assertEqual(result.worker_clock_checks, {})
        self.assertEqual(requests, ["https://gateway.test/health", "https://gateway.test/metrics"])

    def test_poll_probes_each_worker_health_directly_for_clock_skew(self) -> None:
        """STATUS 125 defense line 2: when a worker health key IS
        configured, the monitor hits each worker's own /health (bypassing
        the Gateway) with the shared key= and diffs its self-reported
        server_time against the monitor's own clock."""
        calls: list[str] = []

        def opener(request: object, *, timeout: float) -> Response:
            calls.append(request.full_url)
            if request.full_url == "https://gateway.test/health":
                return Response(json.dumps({
                    "ok": True,
                    "snapshot": {"workers": [
                        {"worker_id": "gpu-1", "url": "https://gpu-1.example", "status": "ready"},
                        {"worker_id": "gpu-2", "url": "https://gpu-2.example", "status": "ready"},
                    ]},
                }).encode("utf-8"))
            if request.full_url == "https://gateway.test/metrics":
                return Response(b"")
            if request.full_url.startswith("https://gpu-1.example/health"):
                # tw-06-shaped incident: worker clock is 256s fast.
                return Response(json.dumps({"ok": True, "server_time": 743.0}).encode("utf-8"))
            if request.full_url.startswith("https://gpu-2.example/health"):
                return Response(json.dumps({"ok": True, "server_time": 999.5}).encode("utf-8"))
            raise AssertionError("unexpected URL: " + request.full_url)

        client = monitor.GatewayClient(
            "https://gateway.test/",
            timeout_seconds=4.0,
            opener=opener,
            worker_health_key="mnk_shared",
            clock=lambda: 1000.0,
        )
        result = client.poll()
        self.assertEqual(result.worker_clock_checks, {
            "gpu-1": {"skew_seconds": 257.0},
            "gpu-2": {"skew_seconds": 0.5},
        })
        self.assertIn("https://gpu-1.example/health?key=mnk_shared", calls)
        self.assertIn("https://gpu-2.example/health?key=mnk_shared", calls)

    def test_poll_records_worker_probe_failures_without_raising(self) -> None:
        def opener(request: object, *, timeout: float) -> Response:
            if request.full_url == "https://gateway.test/health":
                return Response(json.dumps({
                    "ok": True,
                    "snapshot": {"workers": [
                        {"worker_id": "gpu-down", "url": "https://gpu-down.example"},
                    ]},
                }).encode("utf-8"))
            if request.full_url == "https://gateway.test/metrics":
                return Response(b"")
            raise TimeoutError("worker unreachable")

        client = monitor.GatewayClient(
            "https://gateway.test/", timeout_seconds=4.0, opener=opener,
            worker_health_key="mnk_shared",
        )
        result = client.poll()
        self.assertEqual(result.worker_clock_checks, {"gpu-down": {"error": "worker unreachable"}})


class EvaluationTests(unittest.TestCase):
    def test_healthy_capacity_produces_no_alerts(self) -> None:
        self.assertEqual(monitor.evaluate_alerts(healthy_result(), now=NOW), [])

    def test_durable_health_capacity_queue_and_worker_alerts(self) -> None:
        stale = dt.datetime.fromtimestamp(NOW - 121, dt.timezone.utc).isoformat()
        result = monitor.PollResult(
            health={
                "ok": False,
                "mode": "legacy-memory",
                "durable_ready": False,
                "durable_error": "database unavailable",
                "snapshot": {
                    "workers": [{
                        "worker_id": "gpu-1",
                        "status": "unhealthy",
                        "last_heartbeat_at": stale,
                    }],
                },
            },
            metrics={
                "munea_call_queue_depth": 1.0,
                "munea_avatar_capacity": 0.0,
                "munea_avatar_active": 0.0,
                "munea_voice_capacity": 0.0,
                "munea_voice_active": 0.0,
            },
        )
        keys = [alert.key for alert in monitor.evaluate_alerts(result, now=NOW)]
        self.assertEqual(keys, [
            "durable_not_ready",
            "gateway_unhealthy",
            "avatar_zero_capacity",
            "voice_zero_capacity",
            "queue_depth_nonzero",
            "worker_unhealthy:gpu-1",
            "worker_heartbeat_stale:gpu-1",
        ])

    def test_utilization_alerts_at_exactly_eighty_percent(self) -> None:
        result = healthy_result(
            munea_avatar_active=8.0,
            munea_voice_active=4.0,
            munea_voice_capacity=5.0,
        )
        keys = [alert.key for alert in monitor.evaluate_alerts(result, now=NOW)]
        self.assertEqual(keys, ["avatar_utilization_high", "voice_utilization_high"])

    def test_worker_clock_skew_beyond_threshold_alerts(self) -> None:
        """STATUS 125 defense line 2: a worker whose own clock has drifted
        past the threshold must alert even though nothing else about it
        looks unhealthy (fresh heartbeat, ready status, normal capacity)."""
        result = healthy_result()
        result.health["snapshot"]["workers"] = [
            {"worker_id": "tw-06", "status": "ready", "last_heartbeat_at": NOW},
        ]
        result = monitor.PollResult(
            health=result.health,
            metrics=result.metrics,
            worker_clock_checks={"tw-06": {"skew_seconds": 257.0}},
        )
        keys = [alert.key for alert in monitor.evaluate_alerts(result, now=NOW)]
        self.assertEqual(keys, ["worker_clock_skew:tw-06"])

    def test_worker_clock_skew_within_threshold_is_silent(self) -> None:
        result = healthy_result()
        result = monitor.PollResult(
            health=result.health,
            metrics=result.metrics,
            worker_clock_checks={"tw-06": {"skew_seconds": 45.0}},
        )
        self.assertEqual(monitor.evaluate_alerts(result, now=NOW), [])

    def test_worker_clock_skew_threshold_is_configurable(self) -> None:
        result = healthy_result()
        result = monitor.PollResult(
            health=result.health,
            metrics=result.metrics,
            worker_clock_checks={"tw-06": {"skew_seconds": 45.0}},
        )
        keys = [
            alert.key for alert in monitor.evaluate_alerts(
                result, now=NOW, clock_skew_threshold_seconds=30.0,
            )
        ]
        self.assertEqual(keys, ["worker_clock_skew:tw-06"])

    def test_worker_clock_probe_error_does_not_alert_on_its_own(self) -> None:
        """An unreachable-worker probe error is a reachability signal
        already covered by worker_unhealthy/worker_heartbeat_stale -- it
        must not raise a duplicate/confusing clock-skew alert by itself."""
        result = healthy_result()
        result = monitor.PollResult(
            health=result.health,
            metrics=result.metrics,
            worker_clock_checks={"tw-06": {"error": "timed out"}},
        )
        self.assertEqual(monitor.evaluate_alerts(result, now=NOW), [])

    def test_worker_clock_skew_negative_direction_also_alerts(self) -> None:
        """The alert must fire regardless of sign -- a worker clock that is
        slow is just as wrong as one that is fast."""
        result = healthy_result()
        result = monitor.PollResult(
            health=result.health,
            metrics=result.metrics,
            worker_clock_checks={"tw-06": {"skew_seconds": -200.0}},
        )
        keys = [alert.key for alert in monitor.evaluate_alerts(result, now=NOW)]
        self.assertEqual(keys, ["worker_clock_skew:tw-06"])

    def test_poll_failures_are_independent_alerts(self) -> None:
        result = monitor.PollResult(
            health_error="timeout",
            metrics_error="invalid response",
        )
        keys = [alert.key for alert in monitor.evaluate_alerts(result, now=NOW)]
        self.assertEqual(keys, ["health_poll_failed", "metrics_poll_failed"])

    def test_heartbeat_alert_requires_exposed_parseable_timestamp(self) -> None:
        result = healthy_result()
        result.health["snapshot"]["workers"] = [
            {"worker_id": "missing", "status": "ready"},
            {"worker_id": "invalid", "status": "ready", "last_heartbeat_at": "not-a-time"},
            {"worker_id": "fresh", "status": "ready", "last_heartbeat_at": NOW - 120},
            {"worker_id": "terminated", "status": "terminated", "last_heartbeat_at": NOW - 999},
            {"worker_id": "stopped", "status": "stopped", "last_heartbeat_at": NOW - 999},
        ]
        self.assertEqual(monitor.evaluate_alerts(result, now=NOW), [])

    def test_on_device_face_seat_never_raises_a_stale_heartbeat(self) -> None:
        # 2026-11-17：手機自己畫臉的虛擬座位不會有人替它回報心跳，不能當成失聯的臉機。
        result = healthy_result()
        result.health["snapshot"]["workers"] = [
            {"worker_id": "on-device-face", "status": "ready", "last_heartbeat_at": NOW - 19 * 86400},
            {"worker_id": "phone-seat-2", "provider": "on-device", "status": "ready",
             "last_heartbeat_at": NOW - 19 * 86400},
        ]
        self.assertEqual(monitor.evaluate_alerts(result, now=NOW), [])

    def test_real_worker_with_stale_heartbeat_still_alerts(self) -> None:
        result = healthy_result()
        result.health["snapshot"]["workers"] = [
            {"worker_id": "glows-tw07", "provider": "glows", "status": "ready",
             "last_heartbeat_at": NOW - 999},
        ]
        keys = [alert.key for alert in monitor.evaluate_alerts(result, now=NOW)]
        self.assertEqual(keys, ["worker_heartbeat_stale:glows-tw07"])


class SlackNotifierTests(unittest.TestCase):
    def test_successful_send_is_deduplicated_for_ten_minutes(self) -> None:
        now = [1000.0]
        payloads: list[dict[str, str]] = []

        def transport(url: str, payload: bytes, timeout: float) -> None:
            self.assertEqual(url, "https://hooks.slack.test/a")
            self.assertEqual(timeout, 3.0)
            payloads.append(json.loads(payload))

        notifier = slack_notify.SlackNotifier(
            "https://hooks.slack.test/a",
            timeout_seconds=3.0,
            clock=lambda: now[0],
            transport=transport,
        )
        self.assertTrue(notifier.send("queue", "Queue alert", fields={"depth": 2}))
        now[0] += 599
        self.assertFalse(notifier.send("queue", "Queue alert"))
        now[0] += 1
        self.assertTrue(notifier.send("queue", "Queue alert"))
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[0]["text"], "Queue alert\ndepth: 2")

    def test_failed_send_does_not_start_dedup_window(self) -> None:
        attempts = [0]

        def transport(url: str, payload: bytes, timeout: float) -> None:
            attempts[0] += 1
            if attempts[0] == 1:
                raise slack_notify.SlackNotifyError("failed")

        notifier = slack_notify.SlackNotifier(
            "https://hooks.slack.test/a",
            clock=lambda: 1000.0,
            transport=transport,
        )
        with self.assertRaises(slack_notify.SlackNotifyError):
            notifier.send("capacity", "Capacity alert")
        self.assertTrue(notifier.send("capacity", "Capacity alert"))
        self.assertEqual(attempts[0], 2)

    def test_file_state_deduplicates_across_one_shot_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            state = Path(temporary_dir) / "alerts.json"
            sent: list[bytes] = []
            first = slack_notify.SlackNotifier(
                "https://hooks.slack.test/a",
                state_path=state,
                clock=lambda: 1000.0,
                transport=lambda url, payload, timeout: sent.append(payload),
            )
            self.assertTrue(first.send("durable", "Durable alert"))
            second = slack_notify.SlackNotifier(
                "https://hooks.slack.test/a",
                state_path=state,
                clock=lambda: 1200.0,
                transport=lambda url, payload, timeout: sent.append(payload),
            )
            self.assertFalse(second.send("durable", "Durable alert"))
            self.assertEqual(len(sent), 1)

    def test_clear_allows_immediate_recurrence(self) -> None:
        sent: list[bytes] = []
        notifier = slack_notify.SlackNotifier(
            "https://hooks.slack.test/a",
            clock=lambda: 1000.0,
            transport=lambda url, payload, timeout: sent.append(payload),
        )
        self.assertTrue(notifier.send("worker", "Worker alert"))
        notifier.clear("worker")
        self.assertTrue(notifier.send("worker", "Worker alert again"))
        self.assertEqual(len(sent), 2)


class MonitorCycleTests(unittest.TestCase):
    def test_run_once_reports_sent_then_suppressed(self) -> None:
        class Client:
            @staticmethod
            def poll() -> monitor.PollResult:
                return healthy_result(munea_call_queue_depth=2.0)

        delivered: list[bytes] = []
        notifier = slack_notify.SlackNotifier(
            "https://hooks.slack.test/a",
            clock=lambda: NOW,
            transport=lambda url, payload, timeout: delivered.append(payload),
        )
        gateway_monitor = monitor.GatewayMonitor(Client(), notifier, clock=lambda: NOW)
        first = gateway_monitor.run_once()
        second = gateway_monitor.run_once()
        self.assertEqual(first["sent"], ["queue_depth_nonzero"])
        self.assertEqual(second["suppressed"], ["queue_depth_nonzero"])
        self.assertEqual(len(delivered), 1)

    def test_alert_lifecycle_sends_problem_and_recovery_once(self) -> None:
        class Client:
            def __init__(self) -> None:
                self.queue_depth = 2.0

            def poll(self) -> monitor.PollResult:
                return healthy_result(munea_call_queue_depth=self.queue_depth)

        client = Client()
        delivered: list[dict[str, str]] = []
        notifier = slack_notify.SlackNotifier(
            "https://hooks.slack.test/a",
            clock=lambda: NOW,
            transport=lambda url, payload, timeout: delivered.append(json.loads(payload)),
        )
        gateway_monitor = monitor.GatewayMonitor(client, notifier, clock=lambda: NOW)

        first = gateway_monitor.run_once()
        second = gateway_monitor.run_once()
        client.queue_depth = 0.0
        recovery = gateway_monitor.run_once()
        after_recovery = gateway_monitor.run_once()
        client.queue_depth = 1.0
        recurrence = gateway_monitor.run_once()

        self.assertEqual(first["sent"], ["queue_depth_nonzero"])
        self.assertEqual(second["suppressed"], ["queue_depth_nonzero"])
        self.assertEqual(recovery["recovered"], ["recovered:queue_depth_nonzero"])
        self.assertEqual(after_recovery["recovered"], [])
        self.assertEqual(recurrence["sent"], ["queue_depth_nonzero"])
        self.assertEqual(len(delivered), 3)
        self.assertIn("已恢復", delivered[1]["text"])

    def test_lifecycle_state_survives_monitor_recreation(self) -> None:
        class Client:
            @staticmethod
            def poll() -> monitor.PollResult:
                return healthy_result(munea_call_queue_depth=2.0)

        with tempfile.TemporaryDirectory() as temporary_dir:
            lifecycle = Path(temporary_dir) / "lifecycle.json"
            delivered: list[bytes] = []
            notifier = slack_notify.SlackNotifier(
                "https://hooks.slack.test/a",
                clock=lambda: NOW,
                transport=lambda url, payload, timeout: delivered.append(payload),
            )
            first = monitor.GatewayMonitor(
                Client(), notifier, clock=lambda: NOW, lifecycle_state_path=lifecycle,
            )
            self.assertEqual(first.run_once()["sent"], ["queue_depth_nonzero"])
            second = monitor.GatewayMonitor(
                Client(), notifier, clock=lambda: NOW + 9999, lifecycle_state_path=lifecycle,
            )
            self.assertEqual(second.run_once()["suppressed"], ["queue_depth_nonzero"])
            self.assertEqual(len(delivered), 1)


class AutoRetireTests(unittest.TestCase):
    """Containment behind the alarm: dead rows get terminated, not re-alerted."""

    @staticmethod
    def _result_with_workers(workers: list[dict]) -> monitor.PollResult:
        return monitor.PollResult(
            health={
                "ok": True,
                "mode": "durable",
                "durable_ready": True,
                "snapshot": {"workers": workers},
            },
            metrics={},
        )

    def _monitor(self, workers, retired, fail=False, **kwargs):
        outer = self

        class Client:
            def poll(self) -> monitor.PollResult:
                return outer._result_with_workers(workers)

            def retire_worker(self, worker_id: str) -> None:
                if fail:
                    raise RuntimeError("HTTP 503")
                retired.append(worker_id)

        return monitor.GatewayMonitor(
            Client(), monitor.ObserveOnlyNotifier(), clock=lambda: NOW, **kwargs
        )

    def test_unhealthy_and_long_stale_worker_is_retired_once(self) -> None:
        stale_at = dt.datetime.fromtimestamp(NOW - 3600, dt.timezone.utc).isoformat()
        workers = [{
            "worker_id": "glows-old", "url": "https://old", "status": "unhealthy",
            "last_heartbeat_at": stale_at,
        }]
        retired: list[str] = []
        report = self._monitor(workers, retired).run_once()
        self.assertEqual(report["auto_retired"], ["glows-old"])
        self.assertEqual(retired, ["glows-old"])

    def test_ready_worker_is_never_retired_even_when_stale(self) -> None:
        stale_at = dt.datetime.fromtimestamp(NOW - 7200, dt.timezone.utc).isoformat()
        workers = [{
            "worker_id": "glows-main", "url": "https://main", "status": "ready",
            "last_heartbeat_at": stale_at,
        }]
        retired: list[str] = []
        report = self._monitor(workers, retired).run_once()
        self.assertEqual(report["auto_retired"], [])
        self.assertEqual(retired, [])

    def test_recently_unhealthy_worker_is_left_alone(self) -> None:
        recent = dt.datetime.fromtimestamp(NOW - 300, dt.timezone.utc).isoformat()
        workers = [{
            "worker_id": "glows-blip", "url": "https://blip", "status": "unhealthy",
            "last_heartbeat_at": recent,
        }]
        retired: list[str] = []
        report = self._monitor(workers, retired).run_once()
        self.assertEqual(report["auto_retired"], [])

    def test_disabled_by_non_positive_threshold(self) -> None:
        stale_at = dt.datetime.fromtimestamp(NOW - 7200, dt.timezone.utc).isoformat()
        workers = [{
            "worker_id": "glows-old", "url": "https://old", "status": "unhealthy",
            "last_heartbeat_at": stale_at,
        }]
        retired: list[str] = []
        report = self._monitor(workers, retired, auto_retire_seconds=0).run_once()
        self.assertEqual(report["auto_retired"], [])
        self.assertEqual(retired, [])

    def test_retire_failure_is_reported_not_raised(self) -> None:
        stale_at = dt.datetime.fromtimestamp(NOW - 7200, dt.timezone.utc).isoformat()
        workers = [{
            "worker_id": "glows-old", "url": "https://old", "status": "unhealthy",
            "last_heartbeat_at": stale_at,
        }]
        report = self._monitor(workers, [], fail=True).run_once()
        self.assertEqual(report["auto_retired"], [])
        self.assertIn("glows-old", report["auto_retire_errors"])


class ObserveModeTests(unittest.TestCase):
    def test_observe_only_notifier_never_delivers(self) -> None:
        notifier = monitor.ObserveOnlyNotifier()
        self.assertFalse(notifier.send("queue", "Queue alert", fields={"depth": 2}))


class VoicePatrolTests(unittest.TestCase):
    """2026-11-17：語音線巡邏——定時真的接一次 Google，連兩次接不上才報。

    11/8–11/12 聊聊四天打不通、11/12 額度用完停兩小時，總機都是好的、巡邏全綠。
    """

    OK_BODY = b'{"ok":true,"mode":"light","model":"gemini-3.8-live","sdk":"2.34.0","first_audio_ms":656}'

    def _probe(self, responses, *, now, interval=1800.0):
        calls: list[tuple[str, str, float]] = []

        def opener(request: object, *, timeout: float):
            calls.append((request.full_url, request.get_header("X-munea-selftest-key"), timeout))
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return Response(item)

        probe = monitor.VoiceSelftestProbe(
            "https://voice.test/", key="thin-door-key", interval_seconds=interval,
            opener=opener, clock=lambda: now[0],
        )
        return probe, calls

    @staticmethod
    def _http_error(status: int, body: bytes) -> Exception:
        import io as _io
        import urllib.error

        return urllib.error.HTTPError("https://voice.test/selftest/live", status, "x", {}, _io.BytesIO(body))

    def test_success_hits_the_light_door_with_the_thin_key_then_waits_the_interval(self) -> None:
        now = [1000.0]
        probe, calls = self._probe([self.OK_BODY, self.OK_BODY], now=now)
        first = probe.check()
        self.assertTrue(first["ok"])
        self.assertTrue(first["fresh"])
        self.assertEqual(first["model"], "gemini-3.8-live")
        self.assertEqual(calls, [("https://voice.test/selftest/live?mode=light", "thin-door-key", 30.0)])

        now[0] += 120  # 下一輪看門狗（2 分鐘後）不該再燒一次
        again = probe.check()
        self.assertTrue(again["ok"])
        self.assertFalse(again["fresh"])
        self.assertEqual(len(calls), 1)

        now[0] += 1800
        self.assertTrue(probe.check()["fresh"])
        self.assertEqual(len(calls), 2)

    def test_one_failure_is_silent_and_rechecked_on_the_very_next_cycle(self) -> None:
        now = [1000.0]
        refused = self._http_error(503, b'{"ok":false,"error":"ClientError","detail":"connection refused"}')
        probe, calls = self._probe([refused, self.OK_BODY], now=now)
        first = probe.check()
        self.assertFalse(first["ok"])
        self.assertEqual(first["consecutive_failures"], 1)
        result = healthy_result()
        result = monitor.PollResult(health=result.health, metrics=result.metrics, voice_selftest=first)
        self.assertEqual(monitor.evaluate_alerts(result, now=NOW), [])  # 單次抖動不吵人

        now[0] += 120
        second = probe.check()
        self.assertEqual(len(calls), 2)  # 沒等半小時，下一輪就再確認
        self.assertTrue(second["ok"])
        self.assertEqual(second["consecutive_failures"], 0)

    def test_two_failures_in_a_row_raise_one_critical_alert_with_the_reason(self) -> None:
        now = [1000.0]
        refused = lambda: self._http_error(  # noqa: E731
            503, b'{"ok":false,"error":"ClientError","detail":"quota exhausted","model":"gemini-3.8-live","sdk":"2.34.0"}'
        )
        probe, _calls = self._probe([refused(), refused()], now=now)
        probe.check()
        now[0] += 120
        second = probe.check()
        self.assertEqual(second["consecutive_failures"], 2)
        base = healthy_result()
        result = monitor.PollResult(health=base.health, metrics=base.metrics, voice_selftest=second)
        alerts = monitor.evaluate_alerts(result, now=NOW)
        self.assertEqual([alert.key for alert in alerts], ["voice_live_selftest_failed"])
        self.assertEqual(alerts[0].severity, "critical")
        self.assertEqual(alerts[0].fields["原因"], "ClientError")
        self.assertEqual(alerts[0].fields["細節"], "quota exhausted")
        self.assertEqual(alerts[0].fields["連續失敗次數"], 2)

    def test_missing_door_or_rejected_key_is_named_plainly(self) -> None:
        now = [1000.0]
        probe, _calls = self._probe([self._http_error(404, b"")], now=now)
        outcome = probe.check()
        self.assertFalse(outcome["ok"])
        self.assertEqual(outcome["error"], "selftest_door_missing_or_key_rejected")

    def test_network_failure_counts_as_a_failure_not_a_crash(self) -> None:
        now = [1000.0]
        probe, _calls = self._probe([TimeoutError("timed out")], now=now)
        outcome = probe.check()
        self.assertFalse(outcome["ok"])
        self.assertEqual(outcome["error"], "TimeoutError")
        self.assertEqual(outcome["consecutive_failures"], 1)

    def test_a_200_that_does_not_say_ok_is_still_a_failure(self) -> None:
        now = [1000.0]
        probe, _calls = self._probe([b'{"ok":false,"error":"no_audio"}'], now=now)
        outcome = probe.check()
        self.assertFalse(outcome["ok"])
        self.assertEqual(outcome["error"], "no_audio")

    def test_not_patrolling_is_never_an_alert(self) -> None:
        self.assertEqual(monitor.evaluate_alerts(healthy_result(), now=NOW), [])

    def test_monitor_reports_the_patrol_result_and_alerts_through_the_normal_lifecycle(self) -> None:
        class Client:
            def poll(self) -> monitor.PollResult:
                return healthy_result()

            def retire_worker(self, worker_id: str) -> None:
                raise AssertionError("nothing should be retired")

        class Notifier:
            def __init__(self) -> None:
                self.sent: list[str] = []

            def send(self, key: str, text: str, *, fields=None) -> bool:
                self.sent.append(key)
                return True

            def clear(self, key: str) -> None:
                return None

        now = [1000.0]
        refused = lambda: self._http_error(503, b'{"ok":false,"error":"ClientError"}')  # noqa: E731
        probe, _calls = self._probe([refused(), refused(), self.OK_BODY], now=now)
        notifier = Notifier()
        watcher = monitor.GatewayMonitor(Client(), notifier, clock=lambda: NOW, voice_selftest=probe)

        first = watcher.run_once()
        self.assertEqual(first["alert_keys"], [])
        self.assertFalse(first["voice_selftest"]["ok"])
        now[0] += 120
        second = watcher.run_once()
        self.assertEqual(second["sent"], ["voice_live_selftest_failed"])
        now[0] += 120
        third = watcher.run_once()
        self.assertEqual(third["alert_keys"], [])
        self.assertEqual(third["recovered"], ["recovered:voice_live_selftest_failed"])
        self.assertEqual(notifier.sent, ["voice_live_selftest_failed", "recovered:voice_live_selftest_failed"])

    def test_env_wiring_is_off_by_default_and_strict_when_turned_on(self) -> None:
        import os
        from unittest import mock

        base = {"MUNEA_GATEWAY_URL": "https://gateway.test", "MUNEA_GATEWAY_MONITOR_NOTIFY": "0"}
        with tempfile.TemporaryDirectory() as folder:
            base["MUNEA_GATEWAY_MONITOR_STATE_FILE"] = str(Path(folder) / "state.json")
            with mock.patch.dict(os.environ, base, clear=True):
                watcher, _interval = monitor.build_monitor_from_env()
                self.assertIsNone(watcher.voice_selftest)  # 沒設網址＝跟以前一模一樣
            with mock.patch.dict(os.environ, {**base, "MUNEA_VOICE_SELFTEST_URL": "https://voice.test"}, clear=True):
                with self.assertRaises(monitor.MonitorConfigError):
                    monitor.build_monitor_from_env()  # 要巡卻沒鑰匙＝設定錯，不能靜靜不巡
            env = {**base, "MUNEA_VOICE_SELFTEST_URL": "https://voice.test", "MUNEA_APP_KEY": "thin-door-key",
                   "MUNEA_VOICE_SELFTEST_INTERVAL_SECONDS": "900"}
            with mock.patch.dict(os.environ, env, clear=True):
                watcher, _interval = monitor.build_monitor_from_env()
                self.assertEqual(watcher.voice_selftest.url, "https://voice.test/selftest/live?mode=light")
                self.assertEqual(watcher.voice_selftest.interval_seconds, 900.0)


class ScheduledServiceTests(unittest.TestCase):
    """2026-11-17：監看服務改成「定時叫一次、查一次」，不再靠常駐迴圈。"""

    class _Monitor:
        def __init__(self, fail: bool = False) -> None:
            self.calls = 0
            self.fail = fail

        def run_once(self) -> dict[str, object]:
            self.calls += 1
            if self.fail:
                raise RuntimeError("gateway exploded")
            return {"alert_keys": [], "sent": [], "notification_errors": {}}

    def _client(self, monitor_stub):
        try:
            from fastapi.testclient import TestClient
            import monitor_service
        except ImportError as exc:  # fastapi/httpx are service-only dependencies
            self.skipTest(f"fastapi test client unavailable: {exc}")
        import os
        from unittest import mock

        env_patch = mock.patch.dict(os.environ, {}, clear=False)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        os.environ.pop("MUNEA_GATEWAY_MONITOR_LOOP", None)
        build_patch = mock.patch.object(
            monitor_service, "build_monitor_from_env", lambda: (monitor_stub, 3600.0)
        )
        build_patch.start()
        self.addCleanup(build_patch.stop)
        monitor_service.STATE.update(cycles=0, last_error="", last_report=None, last_cycle_at=0.0)
        client = TestClient(monitor_service.app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client, monitor_service

    def test_scheduled_mode_runs_no_background_loop(self) -> None:
        stub = self._Monitor()
        client, service = self._client(stub)
        self.assertEqual(stub.calls, 0)  # nothing runs until the scheduler ticks
        self.assertEqual(client.get("/health").json()["mode"], "scheduled")
        self.assertIsNone(service.app.state.monitor_task)

    def test_each_run_once_call_is_exactly_one_cycle(self) -> None:
        stub = self._Monitor()
        client, _service = self._client(stub)
        first = client.post("/run-once")
        second = client.post("/run-once")
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(stub.calls, 2)
        self.assertEqual(second.json()["cycles"], 2)
        self.assertTrue(second.json()["ok"])
        self.assertEqual(client.get("/health").json()["cycles"], 2)

    def test_failed_cycle_answers_500_so_the_scheduler_notices(self) -> None:
        stub = self._Monitor(fail=True)
        client, _service = self._client(stub)
        response = client.post("/run-once")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.json()["ok"])
        self.assertIn("gateway exploded", response.json()["last_error"])
        self.assertFalse(client.get("/health").json()["ok"])

    def test_loop_flag_is_opt_in(self) -> None:
        try:
            import monitor_service
        except ImportError as exc:
            self.skipTest(f"fastapi unavailable: {exc}")
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"MUNEA_GATEWAY_MONITOR_LOOP": "1"}):
            self.assertTrue(monitor_service.loop_enabled())
        with mock.patch.dict(os.environ, {"MUNEA_GATEWAY_MONITOR_LOOP": "0"}):
            self.assertFalse(monitor_service.loop_enabled())
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(monitor_service.loop_enabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
