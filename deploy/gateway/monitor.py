"""Observe the durable Gateway capacity and alert Slack on production risks."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol

from slack_notify import DEDUP_SECONDS, SlackNotifier, default_state_path


DEFAULT_INTERVAL_SECONDS = 60.0
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_STALE_HEARTBEAT_SECONDS = 120.0
UTILIZATION_THRESHOLD = 0.80


class MonitorConfigError(ValueError):
    """Raised when monitor configuration is incomplete or invalid."""


class AlertNotifier(Protocol):
    def send(
        self,
        key: str,
        message: str,
        *,
        fields: Mapping[str, object] | None = None,
    ) -> bool: ...


class ObserveOnlyNotifier:
    """Record alert decisions in logs without contacting Slack."""

    def send(
        self,
        key: str,
        message: str,
        *,
        fields: Mapping[str, object] | None = None,
    ) -> bool:
        return False


@dataclass(frozen=True)
class Alert:
    key: str
    severity: str
    summary: str
    fields: Mapping[str, object] = field(default_factory=dict)

    def slack_message(self) -> str:
        return f"[Munea Gateway][{self.severity.upper()}] {self.summary}"


@dataclass(frozen=True)
class PollResult:
    health: Mapping[str, object] | None = None
    metrics: Mapping[str, float] | None = None
    health_error: str = ""
    metrics_error: str = ""


def parse_prometheus_metrics(body: str) -> dict[str, float]:
    """Parse the unlabeled gauges exposed by the Gateway metrics endpoint."""
    metrics: dict[str, float] = {}
    for line_number, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"invalid metrics line {line_number}")
        name = parts[0]
        if "{" in name:
            name = name.split("{", 1)[0]
        try:
            metrics[name] = float(parts[1])
        except ValueError as exc:
            raise ValueError(f"invalid metric value on line {line_number}") from exc
    return metrics


def _request(
    url: str,
    admin_key: str,
    timeout_seconds: float,
    opener: Callable[..., object],
) -> tuple[bytes, str]:
    headers = {"Accept": "application/json, text/plain", "User-Agent": "munea-gateway-monitor/1"}
    if admin_key:
        headers["Authorization"] = "Bearer " + admin_key
    request = urllib.request.Request(url, headers=headers, method="GET")
    with opener(request, timeout=timeout_seconds) as response:
        status = getattr(response, "status", response.getcode())
        if status < 200 or status >= 300:
            raise RuntimeError(f"HTTP {status}")
        content_type = response.headers.get("Content-Type", "")
        return response.read(), content_type


class GatewayClient:
    def __init__(
        self,
        base_url: str,
        *,
        admin_key: str = "",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        if not base_url.strip():
            raise MonitorConfigError("MUNEA_GATEWAY_URL is required")
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key.strip()
        self.timeout_seconds = timeout_seconds
        self.opener = opener

    def poll(self) -> PollResult:
        health: Mapping[str, object] | None = None
        metrics: Mapping[str, float] | None = None
        health_error = ""
        metrics_error = ""

        try:
            body, _ = _request(
                self.base_url + "/health", self.admin_key, self.timeout_seconds, self.opener
            )
            value = json.loads(body.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("health response is not a JSON object")
            health = value
        except Exception as exc:
            health_error = str(exc)

        try:
            body, _ = _request(
                self.base_url + "/metrics", self.admin_key, self.timeout_seconds, self.opener
            )
            metrics = parse_prometheus_metrics(body.decode("utf-8"))
        except Exception as exc:
            metrics_error = str(exc)

        return PollResult(
            health=health,
            metrics=metrics,
            health_error=health_error,
            metrics_error=metrics_error,
        )


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _signal(
    health: Mapping[str, object] | None,
    metrics: Mapping[str, float] | None,
    metric_name: str,
    snapshot_name: str,
) -> float | None:
    if metrics is not None and metric_name in metrics:
        return _number(metrics[metric_name])
    snapshot = health.get("snapshot") if health else None
    if isinstance(snapshot, dict):
        return _number(snapshot.get(snapshot_name))
    return None


def _timestamp(value: object) -> float | None:
    number = _number(value)
    if number is not None:
        return number
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


def evaluate_alerts(
    result: PollResult,
    *,
    now: float | None = None,
    stale_heartbeat_seconds: float = DEFAULT_STALE_HEARTBEAT_SECONDS,
) -> list[Alert]:
    current = time.time() if now is None else now
    health = result.health
    metrics = result.metrics
    alerts: list[Alert] = []

    if result.health_error:
        alerts.append(Alert("health_poll_failed", "critical", "Health endpoint poll failed", {
            "error": result.health_error,
        }))
    if result.metrics_error:
        alerts.append(Alert("metrics_poll_failed", "critical", "Metrics endpoint poll failed", {
            "error": result.metrics_error,
        }))

    if health is not None:
        if health.get("durable_ready") is not True or health.get("mode") != "durable":
            alerts.append(Alert("durable_not_ready", "critical", "Durable call control is not ready", {
                "durable_error": health.get("durable_error") or "",
                "mode": health.get("mode") or "unknown",
            }))
        if health.get("ok") is not True:
            alerts.append(Alert("gateway_unhealthy", "critical", "Gateway reports unhealthy", {
                "ok": health.get("ok"),
            }))

    avatar_capacity = _signal(health, metrics, "munea_avatar_capacity", "avatar_capacity")
    avatar_active = _signal(health, metrics, "munea_avatar_active", "avatar_active")
    voice_capacity = _signal(health, metrics, "munea_voice_capacity", "voice_capacity")
    voice_active = _signal(health, metrics, "munea_voice_active", "voice_active")
    queue_depth = _signal(health, metrics, "munea_call_queue_depth", "queue_depth")

    for resource, capacity in (("avatar", avatar_capacity), ("voice", voice_capacity)):
        if capacity is not None and capacity <= 0:
            alerts.append(Alert(
                f"{resource}_zero_capacity",
                "critical",
                f"{resource.capitalize()} capacity is zero",
                {"capacity": capacity},
            ))

    if queue_depth is not None and queue_depth > 0:
        alerts.append(Alert("queue_depth_nonzero", "warning", "Calls are waiting in the queue", {
            "queue_depth": queue_depth,
        }))

    for resource, active, capacity in (
        ("avatar", avatar_active, avatar_capacity),
        ("voice", voice_active, voice_capacity),
    ):
        if active is None or capacity is None or capacity <= 0:
            continue
        utilization = active / capacity
        if utilization >= UTILIZATION_THRESHOLD:
            alerts.append(Alert(
                f"{resource}_utilization_high",
                "warning",
                f"{resource.capitalize()} utilization is at least 80%",
                {
                    "active": active,
                    "capacity": capacity,
                    "utilization_pct": round(utilization * 100, 1),
                },
            ))

    snapshot = health.get("snapshot") if health else None
    workers = snapshot.get("workers") if isinstance(snapshot, dict) else None
    if isinstance(workers, list):
        for index, worker in enumerate(workers):
            if not isinstance(worker, dict):
                continue
            worker_id = str(worker.get("worker_id") or f"index-{index}")
            status = str(worker.get("status") or "unknown").lower()
            if status == "unhealthy":
                alerts.append(Alert(
                    f"worker_unhealthy:{worker_id}",
                    "critical",
                    f"GPU worker {worker_id} reports unhealthy",
                    {"status": status},
                ))
            heartbeat_value = worker.get("last_heartbeat_at")
            heartbeat = _timestamp(heartbeat_value)
            if status != "terminated" and heartbeat_value not in (None, "") and heartbeat is not None:
                age = max(0.0, current - heartbeat)
                if age > stale_heartbeat_seconds:
                    alerts.append(Alert(
                        f"worker_heartbeat_stale:{worker_id}",
                        "critical",
                        f"GPU worker {worker_id} heartbeat is stale",
                        {"age_seconds": round(age, 1), "status": status},
                    ))

    return alerts


class GatewayMonitor:
    def __init__(
        self,
        client: GatewayClient,
        notifier: AlertNotifier,
        *,
        stale_heartbeat_seconds: float = DEFAULT_STALE_HEARTBEAT_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.client = client
        self.notifier = notifier
        self.stale_heartbeat_seconds = stale_heartbeat_seconds
        self.clock = clock

    def run_once(self) -> dict[str, object]:
        result = self.client.poll()
        alerts = evaluate_alerts(
            result,
            now=self.clock(),
            stale_heartbeat_seconds=self.stale_heartbeat_seconds,
        )
        sent: list[str] = []
        suppressed: list[str] = []
        notification_errors: dict[str, str] = {}
        for alert in alerts:
            try:
                delivered = self.notifier.send(alert.key, alert.slack_message(), fields=alert.fields)
            except Exception as exc:
                notification_errors[alert.key] = str(exc)
                continue
            (sent if delivered else suppressed).append(alert.key)
        return {
            "alert_keys": [alert.key for alert in alerts],
            "notification_errors": notification_errors,
            "sent": sent,
            "suppressed": suppressed,
        }


def _positive_float(name: str, value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise MonitorConfigError(f"{name} must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise MonitorConfigError(f"{name} must be positive")
    return parsed


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_monitor_from_env() -> tuple[GatewayMonitor, float]:
    interval = _positive_float(
        "MUNEA_GATEWAY_MONITOR_INTERVAL_SECONDS",
        os.environ.get("MUNEA_GATEWAY_MONITOR_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS)),
    )
    timeout = _positive_float(
        "MUNEA_GATEWAY_MONITOR_HTTP_TIMEOUT_SECONDS",
        os.environ.get("MUNEA_GATEWAY_MONITOR_HTTP_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)),
    )
    stale = _positive_float(
        "MUNEA_GATEWAY_HEARTBEAT_STALE_SECONDS",
        os.environ.get("MUNEA_GATEWAY_HEARTBEAT_STALE_SECONDS", str(DEFAULT_STALE_HEARTBEAT_SECONDS)),
    )
    gateway_url = os.environ.get("MUNEA_GATEWAY_URL", "")
    notify = _env_bool("MUNEA_GATEWAY_MONITOR_NOTIFY")
    webhook_url = os.environ.get("MUNEA_SLACK_ALERT_WEBHOOK", "")
    if not gateway_url.strip():
        raise MonitorConfigError("MUNEA_GATEWAY_URL is required")
    if notify and not webhook_url.strip():
        raise MonitorConfigError("MUNEA_SLACK_ALERT_WEBHOOK is required")
    state_path = os.environ.get("MUNEA_GATEWAY_MONITOR_STATE_FILE", default_state_path()).strip()
    client = GatewayClient(
        gateway_url,
        admin_key=os.environ.get("MUNEA_GATEWAY_ADMIN_KEY", ""),
        timeout_seconds=timeout,
    )
    notifier: AlertNotifier
    if notify:
        notifier = SlackNotifier(
            webhook_url,
            timeout_seconds=timeout,
            state_path=state_path or None,
            dedup_seconds=DEDUP_SECONDS,
        )
    else:
        notifier = ObserveOnlyNotifier()
    return GatewayMonitor(client, notifier, stale_heartbeat_seconds=stale), interval


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Observe Munea Gateway production capacity")
    parser.add_argument(
        "--once",
        action="store_true",
        help="poll once and exit (also MUNEA_GATEWAY_MONITOR_ONCE=1)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        help="override MUNEA_GATEWAY_MONITOR_INTERVAL_SECONDS",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        monitor, interval = build_monitor_from_env()
        if args.interval is not None:
            interval = _positive_float("--interval", str(args.interval))
    except (MonitorConfigError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "monitor": "munea-gateway"}), file=sys.stderr)
        return 2

    once = args.once or _env_bool("MUNEA_GATEWAY_MONITOR_ONCE")
    while True:
        report = monitor.run_once()
        print(json.dumps(report, sort_keys=True), flush=True)
        if once:
            return 1 if report["notification_errors"] else 0
        time.sleep(interval)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
