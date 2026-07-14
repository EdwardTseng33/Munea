# -*- coding: utf-8 -*-
"""Exercise Munea's primary-to-RunPod Voice+Avatar failover end to end.

The drill uses a temporary Supabase auth user/account and credit wallet. Calls
are reserved but never marked ready, so no credits are consumed. Cleanup runs
even after a failed assertion: leases are released, queued calls are cancelled,
the temporary account is deleted, Voice capacity is restored, and the backup
Pod is stopped.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "gateway"))
sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))

from call_control_store import SupabaseCallStore  # noqa: E402
import podctl  # noqa: E402
from runpod_backup import BackupController, Config, GatewayClient  # noqa: E402


class DrillError(RuntimeError):
    pass


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DrillError(f"{name} is required")
    return value


class Drill:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.store = SupabaseCallStore(
            require_env("SUPABASE_URL"), require_env("SUPABASE_SERVICE_ROLE_KEY")
        )
        self.gateway = GatewayClient(args.gateway_url, require_env("MUNEA_GATEWAY_ADMIN_KEY"))
        self.user_id = ""
        self.account_id = ""
        self.call_results: list[dict[str, Any]] = []
        self.voice_original: dict[str, Any] | None = None
        self.worker_id = "runpod-" + args.pod_id
        self.run_id = uuid.uuid4().hex[:12]
        self.state_path = Path(tempfile.gettempdir()) / f"munea-runpod-drill-{self.run_id}.json"
        self.lock_path = Path(tempfile.gettempdir()) / f"munea-runpod-drill-{self.run_id}.lock"

    def _service_headers(self, prefer: str = "") -> dict[str, str]:
        return self.store._service_headers(prefer)

    def _rest(self, method: str, table_and_query: str, body: Any = None,
              prefer: str = "") -> Any:
        return self.store._json(
            method,
            self.store.url + "/rest/v1/" + table_and_query,
            body=body,
            headers=self._service_headers(prefer),
        )

    def _gateway_voice(self, row: dict[str, Any]) -> None:
        from runpod_backup import _http_json

        result = _http_json(
            "POST",
            self.args.gateway_url.rstrip("/") + "/v1/internal/voice-shards",
            {
                "shard_id": row["shard_id"],
                "url": row["url"],
                "provider": row["provider"],
                "region": row["region"],
                "capacity": int(row["capacity"]),
                "status": row.get("status", "ready"),
            },
            headers={"Authorization": "Bearer " + require_env("MUNEA_GATEWAY_ADMIN_KEY")},
        )
        if not result.get("ok"):
            raise DrillError("Gateway refused Voice shard update")

    def create_synthetic_account(self) -> None:
        suffix = uuid.uuid4().hex
        auth = self.store._json(
            "POST",
            self.store.url + "/auth/v1/admin/users",
            body={
                "email": f"runpod-drill-{suffix}@example.invalid",
                "password": "Drill-" + uuid.uuid4().hex + "!9",
                "email_confirm": True,
                "user_metadata": {"purpose": "runpod-failover-drill", "run_id": self.run_id},
            },
            headers=self._service_headers(),
        )
        self.user_id = str((auth or {}).get("id") or "")
        if not self.user_id:
            raise DrillError("temporary auth user creation returned no id")

        accounts = self._rest(
            "POST",
            "accounts",
            {"name": "RunPod failover drill", "locale": "zh-TW"},
            "return=representation",
        )
        self.account_id = str((accounts or [{}])[0].get("id") or "")
        if not self.account_id:
            raise DrillError("temporary account creation returned no id")
        self._rest(
            "POST",
            "account_members",
            {
                "account_id": self.account_id,
                "user_id": self.user_id,
                "role": "owner",
                "status": "active",
            },
            "return=minimal",
        )
        self._rest(
            "POST",
            "credit_wallets",
            {
                "account_id": self.account_id,
                "wallet_type": "purchased",
                "period": "runpod-drill-" + self.run_id,
                "balance": 4,
                "status": "active",
                "metadata": {"purpose": "runpod-failover-drill"},
            },
            "return=minimal",
        )
        print("[1/7] isolated test account ready (4 non-billable reservation credits)")

    def prepare_capacity(self) -> None:
        rows = self._rest(
            "GET",
            "voice_shards?select=shard_id,url,provider,region,capacity,status"
            + "&shard_id=eq." + urllib.parse.quote(self.args.voice_shard_id),
        )
        if not rows:
            raise DrillError("Voice shard was not found")
        self.voice_original = dict(rows[0])
        drill_voice = dict(self.voice_original)
        drill_voice["capacity"] = max(5, int(drill_voice["capacity"]))
        self._gateway_voice(drill_voice)
        print(f"[2/7] Voice admission temporarily raised to {drill_voice['capacity']} for the drill")

    def fill_primary_and_queue_fourth(self) -> None:
        for index in range(1, 5):
            result = self.store.request_call(
                user_id=self.user_id,
                person_id=None,
                character_id="nening",
                idempotency_key=f"runpod-drill-{self.run_id}-{index}",
                queue_max=30,
            )
            self.call_results.append(result)
        first_workers = [
            str((item.get("worker") or {}).get("worker_id") or "")
            for item in self.call_results[:3]
        ]
        if any(item.get("status") != "connect" for item in self.call_results[:3]):
            raise DrillError("the first three calls did not reserve primary capacity")
        if len(set(first_workers)) != 1 or first_workers[0] != self.args.primary_worker_id:
            raise DrillError("the first three calls were not routed to the expected primary worker")
        if self.call_results[3].get("status") != "queued":
            raise DrillError("the fourth call did not enter the queue")
        print("[3/7] primary 3/3 full; fourth caller is queued")

    def controller(self) -> BackupController:
        config = Config(
            mode="active",
            gateway_url=self.args.gateway_url,
            gateway_admin_key=require_env("MUNEA_GATEWAY_ADMIN_KEY"),
            worker_key=require_env("MUNEA_AVATAR_APP_KEY"),
            pod_prefix=self.args.pod_prefix,
            slots=2,
            max_pods=1,
            max_scale_up_per_cycle=1,
            target_concurrent_calls=30,
            utilization_threshold=0.80,
            failure_threshold=1,
            idle_seconds=0,
            cooldown_seconds=0,
            scale_up_cooldown_seconds=0,
            startup_timeout_seconds=120,
            poll_seconds=5,
            scale_down_action="stop",
            state_file=str(self.state_path),
            lock_file=str(self.lock_path),
        )
        return BackupController(config)

    def register_backup(self) -> None:
        result = self.controller().run_once()
        if result.get("action") != "scaled_up" or self.args.pod_id not in result.get("pod_ids", []):
            raise DrillError("backup controller did not health-gate and register the expected Pod")
        snapshot = self.gateway.snapshot()
        worker = next(
            (item for item in snapshot.get("workers", []) if item.get("worker_id") == self.worker_id),
            None,
        )
        if not worker or worker.get("status") != "ready" or int(worker.get("capacity") or 0) != 2:
            raise DrillError("registered backup is not ready with two slots")
        print("[4/7] RunPod passed health gate and joined Gateway with 2 slots")

    def promote_fourth(self) -> None:
        result = self.store.request_call(
            user_id=self.user_id,
            person_id=None,
            character_id="nening",
            idempotency_key=f"runpod-drill-{self.run_id}-4",
            queue_max=30,
        )
        if result.get("status") != "connect":
            snapshot = self.gateway.snapshot()
            diagnostic = {
                "request_status": result.get("status"),
                "reason": result.get("reason"),
                "queue": result.get("queue"),
                "queue_depth": snapshot.get("queue_depth"),
                "voice_active": snapshot.get("voice_active"),
                "voice_capacity": snapshot.get("voice_capacity"),
                "workers": [
                    {
                        "worker_id": item.get("worker_id"),
                        "status": item.get("status"),
                        "active": item.get("active"),
                        "capacity": item.get("capacity"),
                    }
                    for item in snapshot.get("workers", [])
                ],
            }
            raise DrillError("queued fourth caller was not promoted: " + json.dumps(diagnostic))
        if str((result.get("worker") or {}).get("worker_id") or "") != self.worker_id:
            raise DrillError("fourth caller was not routed to the RunPod backup")
        self.call_results[3] = result
        print("[5/7] queued fourth caller promoted to RunPod backup")

    def release_calls(self) -> None:
        for result in self.call_results:
            if result.get("status") != "connect":
                continue
            released = self.store.release(
                call_id=str(result["call_id"]),
                lease_version=int(result.get("lease_version") or 1),
                event_id="runpod-drill-release-" + uuid.uuid4().hex,
                reason="runpod_failover_drill",
                user_id=self.user_id,
            )
            if not released.get("ok") or int(released.get("billed_credits") or 0) != 0:
                raise DrillError("a drill lease did not release cleanly at zero credits")
        print("[6/7] all four reservations released; billed credits = 0")

    def drain_and_stop(self) -> None:
        first = self.controller().run_once()
        second = self.controller().run_once()
        actions = {first.get("action"), second.get("action")}
        if "scaled_down" not in actions:
            raise DrillError("backup controller did not drain and stop the idle Pod")
        deadline = time.monotonic() + 90
        pod = podctl.get_pod(self.args.pod_id)
        while pod.get("desiredStatus") != "EXITED" and time.monotonic() < deadline:
            time.sleep(3)
            pod = podctl.get_pod(self.args.pod_id)
        if pod.get("desiredStatus") != "EXITED":
            raise DrillError("RunPod did not reach EXITED after scale-down")
        snapshot = self.gateway.snapshot()
        if any(item.get("worker_id") == self.worker_id and item.get("status") == "ready"
               for item in snapshot.get("workers", [])):
            raise DrillError("stopped RunPod worker is still ready in Gateway")
        print("[7/7] RunPod drained and stopped; GPU runtime rate = $0/hour")

    def cleanup(self) -> None:
        for result in self.call_results:
            call_id = str(result.get("call_id") or "")
            if not call_id:
                continue
            try:
                if result.get("status") == "connect":
                    self.store.release(
                        call_id=call_id,
                        lease_version=int(result.get("lease_version") or 1),
                        event_id="runpod-drill-cleanup-" + uuid.uuid4().hex,
                        reason="runpod_failover_drill_cleanup",
                        user_id=self.user_id or None,
                    )
                elif result.get("status") == "queued" and self.user_id:
                    self.store.cancel(call_id=call_id, user_id=self.user_id)
            except Exception as exc:
                print("[cleanup] call cleanup warning: " + str(exc), file=sys.stderr)
        if self.voice_original:
            try:
                self._gateway_voice(self.voice_original)
            except Exception as exc:
                print("[cleanup] Voice capacity restore warning: " + str(exc), file=sys.stderr)
        try:
            pod = podctl.get_pod(self.args.pod_id)
            if pod.get("desiredStatus") == "RUNNING":
                podctl.stop_pod(self.args.pod_id)
        except Exception as exc:
            print("[cleanup] Pod stop warning: " + str(exc), file=sys.stderr)
        try:
            self.gateway.unregister(self.worker_id)
        except Exception:
            pass
        if self.account_id:
            try:
                self._rest("DELETE", "accounts?id=eq." + urllib.parse.quote(self.account_id))
            except Exception as exc:
                print("[cleanup] temporary account deletion warning: " + str(exc), file=sys.stderr)
        if self.user_id:
            try:
                self.store._json(
                    "DELETE",
                    self.store.url + "/auth/v1/admin/users/" + urllib.parse.quote(self.user_id),
                    headers=self._service_headers(),
                )
            except Exception as exc:
                print("[cleanup] temporary auth user deletion warning: " + str(exc), file=sys.stderr)
        self.state_path.unlink(missing_ok=True)
        self.lock_path.unlink(missing_ok=True)

    def run(self) -> None:
        try:
            self.create_synthetic_account()
            self.prepare_capacity()
            self.fill_primary_and_queue_fourth()
            self.register_backup()
            self.promote_fourth()
            self.release_calls()
            self.drain_and_stop()
        finally:
            self.cleanup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pod-id", required=True)
    parser.add_argument(
        "--pod-prefix", default="munea-vocaframe-backup-drill-fallback"
    )
    parser.add_argument(
        "--gateway-url",
        default="https://munea-call-control-fiu65jd4da-de.a.run.app",
    )
    parser.add_argument("--primary-worker-id", default="glows-rtx6000ada-tw07")
    parser.add_argument("--voice-shard-id", default="gemini-live-asia-east1-01")
    return parser.parse_args()


if __name__ == "__main__":
    Drill(parse_args()).run()
