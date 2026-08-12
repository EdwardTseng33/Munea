# -*- coding: utf-8 -*-
"""RunPod backup capacity controller for Munea VocaFrame 640.

GLOWS stays the warm primary. This controller can open a bounded RunPod pool
when the primary is unavailable/full or callers are queued, waits for every
VocaFrame health gate, and only then registers those workers with the Gateway.
It drains and stops idle prepared backups so GPU billing ends safely.

The default mode is ``observe``. Set ``MUNEA_RUNPOD_AUTOMATION_MODE=active`` and
An existing stopped backup can be resumed without a template. Creating a new
backup still fails closed unless ``MUNEA_RUNPOD_TEMPLATE_ID`` is configured.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import podctl


HERE = Path(__file__).resolve().parent


class BackupControllerError(RuntimeError):
    pass


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise BackupControllerError(f"{name} must be numeric") from exc


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise BackupControllerError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Config:
    mode: str = "observe"
    gateway_url: str = "http://127.0.0.1:8199"
    gateway_admin_key: str = ""
    worker_key: str = ""
    pod_prefix: str = "munea-vocaframe-backup"
    slots: int = 2
    max_pods: int = 14
    max_scale_up_per_cycle: int = 4
    target_concurrent_calls: int = 30
    utilization_threshold: float = 0.80
    failure_threshold: int = 3
    idle_seconds: int = 900
    cooldown_seconds: int = 300
    scale_up_cooldown_seconds: int = 15
    startup_timeout_seconds: int = 420
    poll_seconds: int = 15
    scale_down_action: str = "stop"
    state_file: str = str(HERE / ".runpod-backup-state.json")
    lock_file: str = str(HERE / ".runpod-backup.lock")
    # 官網展示機（B2B）。它不是備援線的一員——名字不同、機房被那顆網路硬碟綁死在
    # US-IL-1、由 munea-b2b 的 /api/call-key 在訪客輸入密語時叫醒。
    #
    # 2026-08-10 Edward 追究「為什麼沒有人去關」時查出來的洞：官網那支**確實**有
    # TTL，但那段只有「下一個訪客來訪」才會跑到。一個客人看完就走、沒有下一個人來，
    # 機器就永遠開著——$0.74/hr ≈ 一個月 NT$17,000。備援線有這支管家每 15 秒巡，
    # 展示機完全沒人管。所以把它收進同一個管家：時間到就收，不必等誰來訪。
    demo_pod_name: str = "munea-flashhead-demo-768"
    demo_ttl_seconds: int = 1800   # 0 = 不管展示機

    @classmethod
    def from_env(cls) -> "Config":
        max_pods = _int("MUNEA_RUNPOD_MAX_PODS", 14)
        max_scale_up = _int("MUNEA_RUNPOD_MAX_SCALE_UP_PER_CYCLE", 4)
        # A per-cycle scale-up batch larger than the whole pool is harmless
        # intent, not a fatal error: you can never open more than max_pods at
        # once anyway. Clamp it (when max_pods is itself sane) with a warning so
        # an ops env like MAX_PODS=2 + MAX_SCALE_UP=4 self-heals instead of
        # crashing the controller on startup. Genuinely bad values (max_pods out
        # of range, batch < 1) are still rejected by validate().
        if max_pods >= 1 and max_scale_up > max_pods:
            print(
                "[runpod-backup] MUNEA_RUNPOD_MAX_SCALE_UP_PER_CYCLE "
                f"{max_scale_up} exceeds MUNEA_RUNPOD_MAX_PODS {max_pods}; "
                f"clamping batch to {max_pods}",
                flush=True,
            )
            max_scale_up = max_pods
        return cls(
            mode=os.environ.get("MUNEA_RUNPOD_AUTOMATION_MODE", "observe").lower(),
            gateway_url=os.environ.get("MUNEA_GATEWAY_URL", "http://127.0.0.1:8199").rstrip("/"),
            gateway_admin_key=os.environ.get("MUNEA_GATEWAY_ADMIN_KEY", ""),
            worker_key=os.environ.get("MUNEA_AVATAR_APP_KEY", ""),
            pod_prefix=os.environ.get("MUNEA_RUNPOD_POD_PREFIX", "munea-vocaframe-backup"),
            slots=_int("MUNEA_RUNPOD_SLOTS", 2),
            max_pods=max_pods,
            max_scale_up_per_cycle=max_scale_up,
            target_concurrent_calls=_int("MUNEA_TARGET_CONCURRENT_CALLS", 30),
            utilization_threshold=_float("MUNEA_RUNPOD_SCALE_UP_UTILIZATION", 0.80),
            failure_threshold=_int("MUNEA_RUNPOD_FAILURE_THRESHOLD", 3),
            idle_seconds=_int("MUNEA_RUNPOD_IDLE_SECONDS", 900),
            cooldown_seconds=_int("MUNEA_RUNPOD_COOLDOWN_SECONDS", 300),
            scale_up_cooldown_seconds=_int("MUNEA_RUNPOD_SCALE_UP_COOLDOWN_SECONDS", 15),
            startup_timeout_seconds=_int("MUNEA_RUNPOD_STARTUP_TIMEOUT_SECONDS", 420),
            poll_seconds=_int("MUNEA_RUNPOD_POLL_SECONDS", 15),
            scale_down_action=os.environ.get("MUNEA_RUNPOD_SCALE_DOWN_ACTION", "stop").lower(),
            state_file=os.environ.get("MUNEA_RUNPOD_STATE_FILE", str(HERE / ".runpod-backup-state.json")),
            lock_file=os.environ.get("MUNEA_RUNPOD_LOCK_FILE", str(HERE / ".runpod-backup.lock")),
            demo_pod_name=os.environ.get("MUNEA_DEMO_POD_NAME", "munea-flashhead-demo-768"),
            demo_ttl_seconds=_int("MUNEA_DEMO_POD_TTL_SECONDS", 1800),
        )

    def validate(self) -> None:
        if self.mode not in ("observe", "active"):
            raise BackupControllerError("automation mode must be observe or active")
        if self.scale_down_action not in ("stop", "terminate"):
            raise BackupControllerError("scale-down action must be stop or terminate")
        if not 0 < self.utilization_threshold <= 1:
            raise BackupControllerError("utilization threshold must be within (0, 1]")
        if self.slots < 1:
            raise BackupControllerError("RunPod slots must be positive")
        if not 1 <= self.max_pods <= 30:
            raise BackupControllerError("RunPod max pods must be within [1, 30]")
        if not 1 <= self.max_scale_up_per_cycle <= self.max_pods:
            raise BackupControllerError("RunPod scale-up batch must be within [1, max_pods]")
        if not 1 <= self.target_concurrent_calls <= 100:
            raise BackupControllerError("target concurrent calls must be within [1, 100]")
        if self.scale_up_cooldown_seconds < 0:
            raise BackupControllerError("RunPod scale-up cooldown must be non-negative")


class JsonState:
    def __init__(self, path: str):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "probe_failures": {}, "idle_since_by_worker": {}, "last_scale_ts": 0.0,
            }

    def save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)


class OperationLock:
    """Single-controller lock. Production multi-replica moves this to provider_operations."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.fd: int | None = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and time.time() - self.path.stat().st_mtime > 900:
            self.path.unlink()
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode("ascii"))
        except FileExistsError as exc:
            raise BackupControllerError("another RunPod backup operation is already running") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _http_json(method: str, url: str, body: dict[str, Any] | None = None,
               timeout: int = 10, headers: dict[str, str] | None = None) -> dict[str, Any]:
    # RunPod's public proxy sits behind Cloudflare and can reject urllib's
    # default Python user agent even while the same healthy endpoint works in
    # browsers. Identify the controller explicitly for reliable health gates.
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Munea-Capacity-Controller/1.0",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise BackupControllerError(f"HTTP {method} {url} failed: {exc}") from exc


def probe_worker(url: str, worker_key: str = "") -> dict[str, Any]:
    health_url = url.rstrip("/") + "/health"
    if worker_key:
        health_url += "?" + urllib.parse.urlencode({"key": worker_key})
    result = _http_json("GET", health_url, timeout=10)
    if not result.get("ok"):
        raise BackupControllerError("worker health returned ok=false")
    return result


class GatewayClient:
    def __init__(self, base_url: str, admin_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + self.admin_key} if self.admin_key else {}

    def snapshot(self) -> dict[str, Any]:
        result = _http_json("GET", self.base_url + "/health", headers=self._headers())
        if not result.get("ok") or not isinstance(result.get("snapshot"), dict):
            raise BackupControllerError("Gateway health response is not ready")
        return result["snapshot"]

    def register(self, worker_id: str, url: str, slots: int, region: str) -> None:
        result = _http_json("POST", self.base_url + "/v1/internal/workers", {
            "worker_id": worker_id, "url": url, "capacity": slots,
            "region": region, "provider": "runpod", "status": "ready",
        }, headers=self._headers())
        if not result.get("ok"):
            raise BackupControllerError("Gateway refused RunPod worker registration: " + str(result))

    def health(self, worker_id: str, healthy: bool, active: int | None = None) -> None:
        body: dict[str, Any] = {"healthy": healthy}
        if active is not None:
            body["active"] = active
        result = _http_json("POST", self.base_url + f"/v1/internal/workers/{worker_id}/health",
                            body, headers=self._headers())
        if not result.get("ok"):
            raise BackupControllerError("Gateway worker health update failed: " + str(result))

    def enabled(self, worker_id: str, enabled: bool) -> None:
        result = _http_json("POST", self.base_url + f"/v1/internal/workers/{worker_id}/state",
                            {"status": "ready" if enabled else "draining"}, headers=self._headers())
        if not result.get("ok"):
            raise BackupControllerError("Gateway worker drain update failed: " + str(result))

    def unregister(self, worker_id: str) -> None:
        result = _http_json("POST", self.base_url + f"/v1/internal/workers/{worker_id}/state",
                            {"status": "terminated"}, headers=self._headers())
        if not result.get("ok"):
            raise BackupControllerError("Gateway worker unregister failed: " + str(result))


def pod_age_seconds(pod: dict[str, Any], now: float) -> float | None:
    """這台機器開了多久。RunPod 的時間長相是 "2026-07-23 09:01:55.866 +0000 UTC"。

    解析不出來就回 None，呼叫端必須當成「不知道年紀」而**不是** 0 或無限大——
    這個數字唯一的用途是決定要不要刪機器，猜錯任一邊都不行。
    """
    raw = str(pod.get("lastStartedAt") or pod.get("createdAt") or "").strip()
    if not raw:
        return None
    text = raw.replace(" +0000 UTC", "+00:00").replace(" ", "T", 1)
    try:
        started = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=datetime.timezone.utc)
    return max(0.0, now - started.timestamp())


class RunPodProvider:
    def __init__(self, prefix: str, worker_key: str = "", now: Callable[[], float] = time.time):
        self.prefix = prefix
        self.worker_key = worker_key
        self.now = now

    def list(self) -> list[dict[str, Any]]:
        return podctl.managed_pods(self.prefix)

    def list_named(self, name: str) -> list[dict[str, Any]]:
        """名字**完全相等**的機器。展示機不帶備援線的字首，所以不能用 prefix 找；
        而且比對一定要用完全相等——用「開頭是」會咬到別條線的機器。"""
        if not name:
            return []
        return [p for p in podctl.list_pods() if str(p.get("name") or "") == name]

    def worker_url(self, pod_id: str) -> str:
        return podctl.proxy_url(pod_id, 8188)

    def _health_url(self, pod_id: str) -> str:
        url = self.worker_url(pod_id) + "/health"
        if self.worker_key:
            url += "?" + urllib.parse.urlencode({"key": self.worker_key})
        return url

    def _create_named(self, ordinal: int) -> dict[str, Any]:
        name = f"{self.prefix}-{int(self.now())}-{ordinal:02d}"
        mapping = podctl.template_map()
        if not mapping:
            spec = podctl.build_pod_spec(require_template=True)
            spec["name"] = name
            return podctl.create_pod(spec=spec, require_template=True)

        # Per-DC creation: each data center boots from the template whose
        # image sits in its nearest registry mirror (25GB cross-continent
        # pulls are what made 2026-07-23 cold starts take 9 minutes). A DC
        # with no GPU stock falls through to the next; when every listed DC
        # is dry, the optional global fallback trades a slower image pull
        # for actually getting a card at all.
        attempts: list[tuple[str, str | None]] = [
            (dc, mapping.get(dc)) for dc in podctl.data_centers()
        ]
        if os.environ.get("MUNEA_RUNPOD_GLOBAL_FALLBACK", "1").strip() != "0":
            attempts.append(("", None))
        last_error: Exception | None = None
        for data_center, template_id in attempts:
            spec = podctl.build_pod_spec(
                require_template=True, data_center=data_center, template_id=template_id
            )
            spec["name"] = name
            try:
                return podctl.create_pod(spec=spec, require_template=True)
            except podctl.RunPodError as exc:
                if not podctl.is_stockout_error(exc):
                    raise
                last_error = exc
        raise BackupControllerError(
            f"every configured RunPod data center is out of GPU stock for {name}: {last_error}"
        )

    def ensure_ready_many(self, count: int, timeout_s: int, poll_s: int,
                          exclude_ids: set[str] | None = None) -> list[dict[str, Any]]:
        """Start/create ``count`` Pods together and wait for all health gates.

        Existing managed Pods that are not already registered are reused first.
        New Pods are created in one batch so a 30-person burst does not wait for
        fourteen serial two-to-three-minute cold starts.
        """
        count = max(0, int(count))
        if count == 0:
            return []
        excluded = set(exclude_ids or ())
        candidates = [
            p for p in self.list()
            if str(p.get("id") or "") not in excluded
            and p.get("desiredStatus") in ("RUNNING", "EXITED")
        ]
        candidates.sort(key=lambda p: 0 if p.get("desiredStatus") == "RUNNING" else 1)
        selected: list[dict[str, Any]] = []

        for ordinal in range(1, count + 1):
            pod = candidates.pop(0) if candidates else None
            created_new = False
            resumed = False
            if pod is not None and pod.get("desiredStatus") == "EXITED":
                try:
                    podctl.start_pod(str(pod["id"]))
                    resumed = True
                except podctl.RunPodError:
                    if not os.environ.get("MUNEA_RUNPOD_TEMPLATE_ID", "").strip():
                        raise
                    podctl.terminate_pod(str(pod["id"]))
                    pod = self._create_named(ordinal)
                    created_new = True
            elif pod is None:
                pod = self._create_named(ordinal)
                created_new = True
            pod_id = str((pod or {}).get("id") or "")
            if not pod_id:
                raise BackupControllerError("RunPod create/start returned no Pod id")
            selected.append({
                "id": pod_id, "created_new": created_new, "resumed": resumed,
            })

        pending = {item["id"]: item for item in selected}
        ready: dict[str, dict[str, Any]] = {}
        deadline = time.monotonic() + timeout_s
        last_error = "waiting for Pods"
        try:
            while pending and time.monotonic() < deadline:
                for pod_id in list(pending):
                    current = podctl.get_pod(pod_id)
                    if current.get("desiredStatus") == "TERMINATED":
                        raise BackupControllerError(f"RunPod {pod_id} terminated during startup")
                    if current.get("desiredStatus") != "RUNNING":
                        continue
                    try:
                        health = _http_json("GET", self._health_url(pod_id), timeout=15)
                        capacity = health.get("capacity") or {}
                        if health.get("ok") and capacity.get("ready", True):
                            current["health"] = health
                            ready[pod_id] = current
                            pending.pop(pod_id, None)
                        else:
                            last_error = f"VocaFrame health gate is not ready for {pod_id}"
                    except BackupControllerError as exc:
                        last_error = str(exc)
                if pending:
                    time.sleep(poll_s)
            if pending:
                raise BackupControllerError(
                    "RunPod backup startup timed out for "
                    + ",".join(sorted(pending)) + ": " + last_error
                )
            return [ready[item["id"]] for item in selected]
        except Exception:
            for item in selected:
                try:
                    if item["created_new"]:
                        podctl.terminate_pod(item["id"])
                    elif item["resumed"]:
                        podctl.stop_pod(item["id"])
                except Exception as cleanup_error:
                    print("[runpod-backup] startup cleanup failed: " + str(cleanup_error), flush=True)
            raise

    def ensure_ready(self, timeout_s: int, poll_s: int) -> dict[str, Any]:
        return self.ensure_ready_many(1, timeout_s, poll_s)[0]

    def scale_down(self, pod_id: str, action: str) -> None:
        if action == "stop":
            podctl.stop_pod(pod_id)
        else:
            podctl.terminate_pod(pod_id)


def _workers(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw = snapshot.get("workers") or []
    if isinstance(raw, dict):
        raw = raw.get("workers") or []
    workers = list(raw) if isinstance(raw, list) else []
    for worker in workers:
        provider = str(worker.get("provider") or worker.get("kind") or "")
        status = str(worker.get("status") or "")
        if not worker.get("kind"):
            worker["kind"] = "runpod" if provider == "runpod" else (provider or "manual")
        if worker.get("slots") is None:
            worker["slots"] = int(worker.get("capacity") or 0)
        if worker.get("active") is None:
            worker["active"] = int(worker.get("active_leases") or 0)
        if worker.get("healthy") is None:
            worker["healthy"] = status == "ready" if status else True
        if worker.get("enabled") is None:
            worker["enabled"] = status == "ready" if status else True
    return workers


def scale_up_reason(snapshot: dict[str, Any], threshold: float) -> str | None:
    workers = _workers(snapshot)
    primary = [w for w in workers if w.get("kind") != "runpod"]
    ready = [w for w in primary if w.get("healthy") and w.get("enabled")]
    queue_depth = int(snapshot.get("queue_depth") or 0)
    if queue_depth > 0:
        return "queue_waiting"
    if not ready:
        return "primary_unavailable"
    capacity = sum(max(0, int(w.get("slots") or 0)) for w in ready)
    active = sum(max(0, int(w.get("active") or 0)) for w in ready)
    if capacity and (active / capacity) >= threshold:
        return "primary_capacity_threshold"
    return None


def desired_backup_pods(snapshot: dict[str, Any], config: Config) -> tuple[int, str | None]:
    """Return bounded RunPod count needed for current active+queued demand."""
    workers = _workers(snapshot)
    primary = [w for w in workers if w.get("kind") != "runpod"]
    ready_primary = [w for w in primary if w.get("healthy") and w.get("enabled")]
    primary_capacity = sum(max(0, int(w.get("slots") or 0)) for w in ready_primary)
    all_active = max(
        int(snapshot.get("avatar_active") or 0),
        sum(max(0, int(w.get("active") or 0)) for w in workers),
    )
    queue_depth = max(0, int(snapshot.get("queue_depth") or 0))
    demand = min(config.target_concurrent_calls, all_active + queue_depth)
    reason = scale_up_reason(snapshot, config.utilization_threshold)

    # 主力全掛的時候先開一台備援等著——但只在真的有人要用的時候
    # （Edward 2026-08-07：「本來就是備用會暫停，但為什麼會一直消耗？」）。
    #
    # 原本這裡無條件把需求墊到 1：主力一不健康就開一台預熱，好讓第一個打進來的人
    # 不用等開機。立意是好的，但主力掛著沒修的期間，備援會開了空等 15 分鐘、被收掉、
    # 再開一台，一整天循環燒錢，而且從頭到尾沒有半個使用者
    # （8/6-8/7 就是這樣：主力沒接上、備援一直補，直到 RunPod 餘額見底）。
    #
    # 改成：沒有人在用也沒有人排隊，就不開。第一個人一打進來（排隊 > 0）
    # 上面的 scale_up_reason 會回 queue_waiting，那時才開——寧可讓第一通等開機，
    # 也不要沒人用的時候整天燒。
    if not ready_primary and (all_active > 0 or queue_depth > 0):
        demand = max(1, demand)
    deficit = max(0, demand - primary_capacity)
    desired = (deficit + config.slots - 1) // config.slots

    # Pre-warm one additional Pod before the first caller is forced to queue.
    if reason == "primary_capacity_threshold" and queue_depth == 0:
        desired = max(desired, 1)
    return min(config.max_pods, desired), reason


class BackupController:
    def __init__(self, config: Config, gateway: GatewayClient | Any = None,
                 provider: RunPodProvider | Any = None,
                 now: Callable[[], float] = time.time,
                 probe: Callable[[str, str], dict[str, Any]] = probe_worker):
        config.validate()
        self.config = config
        self.gateway = gateway or GatewayClient(config.gateway_url, config.gateway_admin_key)
        self.provider = provider or RunPodProvider(config.pod_prefix, config.worker_key, now=now)
        self.now = now
        self.probe = probe
        self.state = JsonState(config.state_file)

    def _backup_workers(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        return [w for w in _workers(snapshot) if w.get("kind") == "runpod"]

    def _refresh_health(
        self,
        snapshot: dict[str, Any],
        state: dict[str, Any],
        managed_pods: list[dict[str, Any]] | None = None,
    ) -> None:
        failures = state.setdefault("probe_failures", {})
        pod_status = {
            str(pod.get("id") or ""): str(pod.get("desiredStatus") or "").upper()
            for pod in (managed_pods or [])
            if pod.get("id")
        }
        terminal_worker_statuses = {"terminated", "stopped", "exited", "disabled"}
        for worker in _workers(snapshot):
            worker_id = str(worker.get("worker_id") or "")
            url = str(worker.get("url") or "")
            if not worker_id or not url:
                continue
            worker_status = str(worker.get("status") or "").lower()
            if worker_status in terminal_worker_statuses:
                failures.pop(worker_id, None)
                continue
            if worker.get("kind") == "runpod" and managed_pods is not None:
                pod_id = worker_id.removeprefix("runpod-")
                desired_status = pod_status.get(pod_id)
                if desired_status and desired_status != "RUNNING":
                    failures.pop(worker_id, None)
                    worker.update({
                        "status": "terminated",
                        "healthy": False,
                        "enabled": False,
                        "active": 0,
                    })
                    if self.config.mode == "active":
                        self.gateway.unregister(worker_id)
                    continue
            try:
                health = self.probe(url, self.config.worker_key)
                failures[worker_id] = 0
                capacity = health.get("capacity") or {}
                active = capacity.get("active")
                worker["healthy"] = True
                if active is not None:
                    worker["active"] = int(active)
                if self.config.mode == "active":
                    self.gateway.health(worker_id, True, int(active) if active is not None else None)
            except Exception:
                failures[worker_id] = int(failures.get(worker_id) or 0) + 1
                if failures[worker_id] >= self.config.failure_threshold:
                    worker["healthy"] = False
                    if self.config.mode == "active":
                        self.gateway.health(worker_id, False)

    def _reap_demo_pod(self, now: float) -> dict[str, Any] | None:
        """展示機開太久就收掉。回傳事件（有收才回），沒事回 None。

        為什麼放在這支管家裡：官網那支 /api/call-key 也有一模一樣的 TTL，但那段
        **只有訪客上門才會跑到**。一個客人看完就走，沒有下一個人來，機器就永遠開著
        （2026-08-10 Edward 追究「為什麼沒有人去關」時查出來的）。這裡每 15 秒一輪，
        不必等誰來訪。兩邊用同一個 30 分鐘，誰先看到誰收。

        比對用「名字完全相等」——展示機不帶備援線的字首，用開頭比會咬到別條線。
        年紀讀不出來時**不刪**：寧可多燒一輪，也不要因為看不懂時間就砍掉別人正在
        展示的機器。
        """
        if self.config.mode != "active" or self.config.demo_ttl_seconds <= 0:
            return None
        lookup = getattr(self.provider, "list_named", None)
        if not callable(lookup):
            return None      # 舊的／測試用 provider 沒有這支：當成沒有展示機要收
        try:
            pods = lookup(self.config.demo_pod_name)
        except Exception as exc:
            # 查不到就這輪算了，下一輪（15 秒後）再說。
            # ⚠ 這裡**絕對不能**回傳一個事件——run_once 看到事件就會直接 return，
            # 等於展示機一出問題，備援線整輪不做事。備援線是通話容量的保命索，
            # 不可以被一個附帶功能拖著（2026-08-10 第一版就是這樣寫的，測試抓到）。
            print("[runpod-backup] demo reap lookup failed: " + str(exc)[:120], flush=True)
            return None
        for pod in pods:
            if str(pod.get("desiredStatus") or "").upper() != "RUNNING":
                continue
            age = pod_age_seconds(pod, now)
            if age is None or age <= self.config.demo_ttl_seconds:
                continue
            pod_id = str(pod.get("id") or "")
            if not pod_id:
                continue
            podctl.terminate_pod(pod_id)
            return {
                "action": "reaped_demo_pod", "pod_id": pod_id,
                "name": self.config.demo_pod_name,
                "age_seconds": round(age), "ttl_seconds": self.config.demo_ttl_seconds,
            }
        return None

    def run_once(self) -> dict[str, Any]:
        with OperationLock(self.config.lock_file):
            state = self.state.load()
            now = self.now()
            # 展示機先收——它跟備援線無關，不該因為備援線今天沒事做就沒人管它。
            # 收到就直接回報收工：外層每 15 秒還會再跑一輪，備援線不會因此漏一拍，
            # 而且這樣才會出現在 controller 的事件紀錄裡（no_change 不會被印出來）。
            demo_event = self._reap_demo_pod(now)
            if demo_event is not None:
                return {"mode": self.config.mode, **demo_event}
            snapshot = self.gateway.snapshot()
            managed_pods = self.provider.list() if self.config.mode == "active" else None
            self._refresh_health(snapshot, state, managed_pods)
            backups = self._backup_workers(snapshot)
            ready_backups = [w for w in backups if w.get("healthy") and w.get("enabled")]
            desired, reason = desired_backup_pods(snapshot, self.config)
            registered_ids = {
                str(w.get("worker_id") or "").removeprefix("runpod-")
                for w in backups
                if w.get("worker_id") and str(w.get("status") or "") != "terminated"
            }
            scale_up_ok = (
                now - float(state.get("last_scale_up_ts") or 0)
                >= self.config.scale_up_cooldown_seconds
            )
            scale_down_ok = (
                now - float(state.get("last_scale_down_ts") or 0)
                >= self.config.cooldown_seconds
            )

            missing = max(0, desired - len(ready_backups))
            if missing and scale_up_ok:
                count = min(
                    missing,
                    self.config.max_scale_up_per_cycle,
                    max(0, self.config.max_pods - len(ready_backups)),
                )
                if self.config.mode == "observe":
                    self.state.save(state)
                    return {
                        "mode": "observe", "action": "would_scale_up", "reason": reason,
                        "desired_pods": desired, "ready_pods": len(ready_backups),
                        "scale_up_count": count,
                    }
                pods = self.provider.ensure_ready_many(
                    count,
                    self.config.startup_timeout_seconds,
                    self.config.poll_seconds,
                    exclude_ids=registered_ids,
                )
                registered: list[tuple[str, str]] = []
                try:
                    for pod in pods:
                        pod_id = str(pod["id"])
                        worker_id = "runpod-" + pod_id
                        machine = pod.get("machine") or {}
                        region = str(
                            machine.get("dataCenterId") or machine.get("location") or "runpod"
                        )
                        self.gateway.register(
                            worker_id, self.provider.worker_url(pod_id), self.config.slots, region
                        )
                        registered.append((worker_id, pod_id))
                except Exception:
                    for worker_id, _ in registered:
                        try:
                            self.gateway.unregister(worker_id)
                        except Exception:
                            pass
                    for pod in pods:
                        try:
                            self.provider.scale_down(str(pod["id"]), self.config.scale_down_action)
                        except Exception:
                            pass
                    raise
                state["last_scale_up_ts"] = now
                self.state.save(state)
                return {
                    "mode": "active", "action": "scaled_up", "reason": reason,
                    "desired_pods": desired, "ready_pods_before": len(ready_backups),
                    "scale_up_count": len(registered),
                    "pod_ids": [pod_id for _, pod_id in registered],
                    "worker_ids": [worker_id for worker_id, _ in registered],
                }

            if desired <= len(ready_backups) and managed_pods:
                running_orphans = [
                    p for p in managed_pods
                    if p.get("desiredStatus") == "RUNNING"
                    and str(p.get("id") or "") not in registered_ids
                ]
                if running_orphans:
                    pod_id = str(running_orphans[0].get("id") or "")
                    if pod_id:
                        self.provider.scale_down(pod_id, self.config.scale_down_action)
                        state["last_scale_down_ts"] = now
                        self.state.save(state)
                        return {
                            "mode": "active", "action": "cleaned_orphan_pod",
                            "provider_action": self.config.scale_down_action, "pod_id": pod_id,
                        }

            excess = max(0, len(ready_backups) - desired)
            idle_map = state.setdefault("idle_since_by_worker", {})
            idle_candidates = sorted(
                [w for w in ready_backups if int(w.get("active") or 0) == 0],
                key=lambda w: str(w.get("worker_id") or ""),
                reverse=True,
            )[:excess]
            candidate_ids = {str(w.get("worker_id") or "") for w in idle_candidates}
            for worker_id in list(idle_map):
                if worker_id not in candidate_ids:
                    idle_map.pop(worker_id, None)
            started = []
            for worker in idle_candidates:
                worker_id = str(worker.get("worker_id") or "")
                if worker_id and worker_id not in idle_map:
                    idle_map[worker_id] = now
                    started.append(worker_id)
            if started:
                self.state.save(state)
                return {
                    "mode": self.config.mode, "action": "idle_timers_started",
                    "worker_ids": started, "desired_pods": desired,
                }

            matured = [
                w for w in idle_candidates
                if now - float(idle_map.get(str(w.get("worker_id") or ""), now))
                >= self.config.idle_seconds
            ]
            if matured and scale_down_ok:
                batch = matured[:self.config.max_scale_up_per_cycle]
                if self.config.mode == "observe":
                    self.state.save(state)
                    return {
                        "mode": "observe", "action": "would_scale_down",
                        "worker_ids": [w.get("worker_id") for w in batch],
                        "desired_pods": desired,
                    }
                stopped: list[str] = []
                aborted: list[str] = []
                for worker in batch:
                    worker_id = str(worker["worker_id"])
                    self.gateway.enabled(worker_id, False)
                    fresh = self.gateway.snapshot()
                    fresh_workers = _workers(fresh)
                    current = next(
                        (w for w in fresh_workers if w.get("worker_id") == worker_id), None
                    )
                    remaining_ready = sum(
                        1 for w in fresh_workers
                        if w.get("kind") == "runpod" and w.get("healthy") and w.get("enabled")
                    )
                    fresh_desired, _ = desired_backup_pods(fresh, self.config)
                    unsafe = (
                        current is None
                        or int(current.get("active") or 0) > 0
                        or int(fresh.get("queue_depth") or 0) > 0
                        or remaining_ready < fresh_desired
                    )
                    if unsafe:
                        if current is not None:
                            self.gateway.enabled(worker_id, True)
                        idle_map.pop(worker_id, None)
                        aborted.append(worker_id)
                        continue
                    pod_id = worker_id.removeprefix("runpod-")
                    try:
                        self.provider.scale_down(pod_id, self.config.scale_down_action)
                    except Exception:
                        self.gateway.enabled(worker_id, True)
                        raise
                    self.gateway.unregister(worker_id)
                    idle_map.pop(worker_id, None)
                    stopped.append(pod_id)
                if stopped:
                    state["last_scale_down_ts"] = now
                self.state.save(state)
                return {
                    "mode": "active",
                    "action": "scaled_down" if stopped else "scale_down_aborted",
                    "provider_action": self.config.scale_down_action,
                    "pod_ids": stopped, "aborted_worker_ids": aborted,
                }

            self.state.save(state)
            return {
                "mode": self.config.mode, "action": "no_change", "reason": reason,
                "desired_pods": desired, "ready_pods": len(ready_backups),
            }


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "once"
    config = Config.from_env()
    controller = BackupController(config)
    if command == "once":
        print(json.dumps(controller.run_once(), indent=2, ensure_ascii=False))
    elif command == "loop":
        while True:
            try:
                print(json.dumps(controller.run_once(), ensure_ascii=False), flush=True)
            except Exception as exc:
                print(json.dumps({"action": "error", "error": str(exc)}, ensure_ascii=False), flush=True)
            time.sleep(config.poll_seconds)
    else:
        raise SystemExit("Usage: runpod_backup.py once|loop")


if __name__ == "__main__":
    main()
