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
        self.assertIn("[RECOVERED]", delivered[1]["text"])

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


class ObserveModeTests(unittest.TestCase):
    def test_observe_only_notifier_never_delivers(self) -> None:
        notifier = monitor.ObserveOnlyNotifier()
        self.assertFalse(notifier.send("queue", "Queue alert", fields={"depth": 2}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
