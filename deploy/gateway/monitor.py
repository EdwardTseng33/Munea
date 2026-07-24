"""Observe the durable Gateway capacity and alert Slack on production risks."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Protocol

from slack_notify import DEDUP_SECONDS, SlackNotifier, default_state_path


DEFAULT_INTERVAL_SECONDS = 60.0
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_STALE_HEARTBEAT_SECONDS = 120.0
# 2026-07-23 STATUS 125 defense line 2: a GPU worker's own clock can drift
# without ever going "unhealthy" or missing a heartbeat -- the Gateway only
# ever sees last_heartbeat_at stamped by ITS OWN clock at receipt time, so
# that signal cannot detect the worker's clock being wrong. tw-06 was
# measured 4m17s (257s) fast; keep the default threshold comfortably below
# that so a repeat trips this alarm well before a fresh 90s call token would
# start looking expired to the worker.
DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS = 90.0
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

    def clear(self, key: str) -> None: ...


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

    def clear(self, key: str) -> None:
        return None


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
    # worker_id -> {"skew_seconds": float} or {"error": str}. Populated by
    # GatewayClient.poll() only when a worker health key is configured
    # (STATUS 125 defense line 2); empty dict means "not probed", not
    # "clocks are fine" -- evaluate_alerts() never alerts on an empty dict.
    worker_clock_checks: Mapping[str, Mapping[str, object]] = field(default_factory=dict)


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
        worker_health_key: str = "",
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not base_url.strip():
            raise MonitorConfigError("MUNEA_GATEWAY_URL is required")
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key.strip()
        self.timeout_seconds = timeout_seconds
        self.opener = opener
        # STATUS 125 defense line 2: the same legacy universal key= that
        # App/probe scripts already use against a worker's own /health
        # (see scripts/voice_chain_probe.py, web/src/app.js MUNEA_APP_KEY).
        # Optional and off by default -- unset means "do not probe worker
        # clocks", not "clocks are fine" (see PollResult.worker_clock_checks).
        self.worker_health_key = worker_health_key.strip()
        self.clock = clock

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
            worker_clock_checks=self._probe_worker_clocks(health),
        )

    def _probe_worker_clocks(self, health: Mapping[str, object] | None) -> dict[str, dict[str, object]]:
        """Poll each GPU worker's own /health directly (bypassing the
        Gateway) for its self-reported server_time and diff it against this
        monitor's own clock (2026-07-23 STATUS 125 defense line 2).

        The Gateway's worker registry only ever stamps last_heartbeat_at
        with the GATEWAY's clock at receipt time -- a worker whose own
        clock is wrong looks perfectly fresh from there. Only a direct hit
        on the worker's /health (which now echoes its own wall clock, see
        flashhead_server.py) can surface this.
        """
        if not self.worker_health_key:
            return {}
        workers = None
        if isinstance(health, dict):
            snapshot = health.get("snapshot")
            if isinstance(snapshot, dict):
                workers = snapshot.get("workers")
        if not isinstance(workers, list):
            return {}
        checks: dict[str, dict[str, object]] = {}
        for worker in workers:
            if not isinstance(worker, dict):
                continue
            worker_id = str(worker.get("worker_id") or "").strip()
            url = str(worker.get("url") or "").strip()
            if not worker_id or not url:
                continue
            probe_url = (
                url.rstrip("/") + "/health?key=" + urllib.parse.quote(self.worker_health_key, safe="")
            )
            try:
                body, _ = _request(probe_url, "", self.timeout_seconds, self.opener)
                observed_at = self.clock()
                value = json.loads(body.decode("utf-8"))
                server_time = _number(value.get("server_time")) if isinstance(value, dict) else None
                if server_time is None:
                    checks[worker_id] = {"error": "server_time missing from worker /health"}
                    continue
                checks[worker_id] = {"skew_seconds": round(observed_at - server_time, 1)}
            except Exception as exc:
                checks[worker_id] = {"error": str(exc)}
        return checks


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
    clock_skew_threshold_seconds: float = DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS,
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
            terminal_statuses = {"terminated", "stopped", "exited", "disabled"}
            if status == "unhealthy":
                alerts.append(Alert(
                    f"worker_unhealthy:{worker_id}",
                    "critical",
                    f"GPU worker {worker_id} reports unhealthy",
                    {
                        "provider": worker.get("provider") or worker.get("kind") or "unknown",
                        "status": status,
                    },
                ))
            heartbeat_value = worker.get("last_heartbeat_at")
            heartbeat = _timestamp(heartbeat_value)
            if status not in terminal_statuses and heartbeat_value not in (None, "") and heartbeat is not None:
                age = max(0.0, current - heartbeat)
                if age > stale_heartbeat_seconds:
                    alerts.append(Alert(
                        f"worker_heartbeat_stale:{worker_id}",
                        "critical",
                        f"GPU worker {worker_id} heartbeat is stale",
                        {"age_seconds": round(age, 1), "status": status},
                    ))

    # 2026-07-23 STATUS 125 defense line 2: worker_clock_checks is only ever
    # non-empty when GatewayClient was configured with a worker health key
    # (opt-in). An "error" entry (unreachable, missing server_time on an
    # older build, etc.) is a reachability signal already covered by
    # worker_unhealthy/worker_heartbeat_stale above -- only a measured skew
    # past the threshold raises a new alert here, so this never duplicates
    # those.
    for worker_id, check in (result.worker_clock_checks or {}).items():
        if not isinstance(check, dict):
            continue
        skew = _number(check.get("skew_seconds"))
        if skew is not None and abs(skew) > clock_skew_threshold_seconds:
            alerts.append(Alert(
                f"worker_clock_skew:{worker_id}",
                "critical",
                f"GPU worker {worker_id} clock is off by more than {clock_skew_threshold_seconds:g}s",
                {"skew_seconds": skew, "threshold_seconds": clock_skew_threshold_seconds},
            ))

    return alerts


class GatewayMonitor:
    def __init__(
        self,
        client: GatewayClient,
        notifier: AlertNotifier,
        *,
        stale_heartbeat_seconds: float = DEFAULT_STALE_HEARTBEAT_SECONDS,
        clock_skew_threshold_seconds: float = DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS,
        clock: Callable[[], float] = time.time,
        lifecycle_state_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self.client = client
        self.notifier = notifier
        self.stale_heartbeat_seconds = stale_heartbeat_seconds
        self.clock_skew_threshold_seconds = clock_skew_threshold_seconds
        self.clock = clock
        self.lifecycle_state_path = Path(lifecycle_state_path) if lifecycle_state_path else None
        self._active_alerts = self._load_lifecycle_state()

    def _load_lifecycle_state(self) -> dict[str, dict[str, object]]:
        if self.lifecycle_state_path is None:
            return {}
        try:
            raw = json.loads(self.lifecycle_state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): dict(value)
            for key, value in raw.items()
            if isinstance(value, dict)
        }

    def _save_lifecycle_state(self) -> None:
        if self.lifecycle_state_path is None:
            return
        self.lifecycle_state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.lifecycle_state_path.with_suffix(
            self.lifecycle_state_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(self._active_alerts, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.lifecycle_state_path)

    def run_once(self) -> dict[str, object]:
        result = self.client.poll()
        alerts = evaluate_alerts(
            result,
            now=self.clock(),
            stale_heartbeat_seconds=self.stale_heartbeat_seconds,
            clock_skew_threshold_seconds=self.clock_skew_threshold_seconds,
        )
        sent: list[str] = []
        suppressed: list[str] = []
        recovered: list[str] = []
        notification_errors: dict[str, str] = {}
        next_active: dict[str, dict[str, object]] = {}
        for alert in alerts:
            previous = self._active_alerts.get(alert.key) or {}
            alert_state = {
                "severity": alert.severity,
                "summary": alert.summary,
                "fields": dict(alert.fields),
                "notified": bool(previous.get("notified")),
            }
            if alert_state["notified"]:
                suppressed.append(alert.key)
                next_active[alert.key] = alert_state
                continue
            try:
                delivered = self.notifier.send(alert.key, alert.slack_message(), fields=alert.fields)
            except Exception as exc:
                notification_errors[alert.key] = str(exc)
                next_active[alert.key] = alert_state
                continue
            (sent if delivered else suppressed).append(alert.key)
            alert_state["notified"] = True
            next_active[alert.key] = alert_state

        for key in sorted(set(self._active_alerts) - set(next_active)):
            previous = self._active_alerts[key]
            if not previous.get("notified"):
                continue
            recovery_key = "recovered:" + key
            recovery_fields = dict(previous.get("fields") or {})
            recovery_fields["previous_severity"] = previous.get("severity") or "unknown"
            try:
                delivered = self.notifier.send(
                    recovery_key,
                    f"[Munea Gateway][RECOVERED] {previous.get('summary') or key}",
                    fields=recovery_fields,
                )
                (recovered if delivered else suppressed).append(recovery_key)
                self.notifier.clear(key)
                self.notifier.clear(recovery_key)
            except Exception as exc:
                notification_errors[recovery_key] = str(exc)

        self._active_alerts = next_active
        self._save_lifecycle_state()
        return {
            "alert_keys": [alert.key for alert in alerts],
            "active_alert_keys": sorted(next_active),
            "notification_errors": notification_errors,
            "recovered": recovered,
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
    clock_skew_threshold = _positive_float(
        "MUNEA_WORKER_CLOCK_SKEW_THRESHOLD_SECONDS",
        os.environ.get(
            "MUNEA_WORKER_CLOCK_SKEW_THRESHOLD_SECONDS", str(DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS)
        ),
    )
    gateway_url = os.environ.get("MUNEA_GATEWAY_URL", "")
    notify = _env_bool("MUNEA_GATEWAY_MONITOR_NOTIFY")
    webhook_url = os.environ.get("MUNEA_SLACK_ALERT_WEBHOOK", "")
    if not gateway_url.strip():
        raise MonitorConfigError("MUNEA_GATEWAY_URL is required")
    if notify and not webhook_url.strip():
        raise MonitorConfigError("MUNEA_SLACK_ALERT_WEBHOOK is required")
    state_path = os.environ.get("MUNEA_GATEWAY_MONITOR_STATE_FILE", default_state_path()).strip()
    lifecycle_path = os.environ.get(
        "MUNEA_GATEWAY_MONITOR_LIFECYCLE_FILE",
        os.path.join(os.path.dirname(state_path), "munea-gateway-monitor-lifecycle.json"),
    ).strip()
    # STATUS 125 defense line 2: same shared client key the App and
    # scripts/voice_chain_probe.py already use (MUNEA_APP_KEY). Optional --
    # unset keeps this monitor byte-for-byte the same as before this change
    # (no worker clock probing, no new alerts).
    worker_health_key = os.environ.get("MUNEA_APP_KEY", "").strip()
    client = GatewayClient(
        gateway_url,
        admin_key=os.environ.get("MUNEA_GATEWAY_ADMIN_KEY", ""),
        timeout_seconds=timeout,
        worker_health_key=worker_health_key,
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
    return GatewayMonitor(
        client,
        notifier,
        stale_heartbeat_seconds=stale,
        clock_skew_threshold_seconds=clock_skew_threshold,
        lifecycle_state_path=lifecycle_path or None,
    ), interval


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
