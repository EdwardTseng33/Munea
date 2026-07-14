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


class GatewayClientTests(unittest.TestCase):
    def test_poll_fetches_health_and_metrics_with_admin_bearer(self) -> None:
        requests: list[tuple[str, str, float]] = []

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

        def opener(request: object, *, timeout: float) -> Response:
            url = request.full_url
            requests.append((url, request.get_header("Authorization"), timeout))
            if url.endswith("/health"):
                return Response(b'{"ok":true,"mode":"durable","durable_ready":true}')
            return Response(b"munea_avatar_capacity 3\n")

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


class ObserveModeTests(unittest.TestCase):
    def test_observe_only_notifier_never_delivers(self) -> None:
        notifier = monitor.ObserveOnlyNotifier()
        self.assertFalse(notifier.send("queue", "Queue alert", fields={"depth": 2}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
