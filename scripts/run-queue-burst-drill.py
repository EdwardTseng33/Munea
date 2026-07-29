# -*- coding: utf-8 -*-
"""Queue-burst drill: fill the primary, queue a third caller, and watch the
LIVE Cloud Run capacity controller open a fresh RunPod card end to end.

Unlike run-runpod-failover-drill.py (2026-07-15 topology: one 3-slot primary,
pre-created pod, controller run locally), this drill matches the 2026-07-29
production shape: primary = glows tw-06 p0/p1 (1 slot each), and the scale-up
is performed by the DEPLOYED munea-runpod-controller loop -- so a pass proves
the whole chain (queue -> controller -> per-DC template/mirror -> health gate
-> gateway registration -> queued caller promoted), not a lab replica.

Reservations are never marked ready, so no credits are consumed and no GPU
inference runs. Cleanup releases every lease, cancels queued calls, restores
the Voice shard, and deletes the temporary account. The RunPod card the live
controller opened is left to the controller's own idle timer (15 min) unless
--terminate-pod is passed; watching the auto-teardown is part of the drill.

Required env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, MUNEA_GATEWAY_ADMIN_KEY.
Optional: MUNEA_GATEWAY_URL (default production call-control URL).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "gateway"))
sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))

from call_control_store import SupabaseCallStore  # noqa: E402
from runpod_backup import GatewayClient, _http_json  # noqa: E402


class DrillError(RuntimeError):
    pass


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DrillError(f"{name} is required")
    return value


GCLOUD_SECRETS = {
    "SUPABASE_SERVICE_ROLE_KEY": "munea-supabase-service-staging",
    "MUNEA_GATEWAY_ADMIN_KEY": "munea-gateway-admin-key",
}
DEFAULT_SUPABASE_URL = "https://fespbkdwafueyonppzwq.supabase.co"


def fetch_secrets_from_gcloud(project: str) -> None:
    """Fill the required env vars straight from Secret Manager (values never
    touch a shell command line or the transcript)."""
    import shutil
    import subprocess

    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud:
        raise DrillError("gcloud is required for --fetch-secrets")
    os.environ.setdefault("SUPABASE_URL", DEFAULT_SUPABASE_URL)
    for env_name, secret in GCLOUD_SECRETS.items():
        if os.environ.get(env_name, "").strip():
            continue
        value = subprocess.run(
            [gcloud, "secrets", "versions", "access", "latest",
             "--secret=" + secret, "--project=" + project],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if not value:
            raise DrillError(f"secret {secret} came back empty")
        os.environ[env_name] = value


class Drill:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.store = SupabaseCallStore(
            require_env("SUPABASE_URL"), require_env("SUPABASE_SERVICE_ROLE_KEY")
        )
        self.gateway = GatewayClient(args.gateway_url, require_env("MUNEA_GATEWAY_ADMIN_KEY"))
        self.run_id = uuid.uuid4().hex[:12]
        self.user_id = ""
        self.account_id = ""
        self.calls: list[dict[str, Any]] = []
        self.voice_original: dict[str, Any] | None = None
        self.timeline: dict[str, float] = {}

    # -- plumbing -----------------------------------------------------------
    def _rest(self, method: str, table_and_query: str, body: Any = None,
              prefer: str = "") -> Any:
        return self.store._json(
            method, self.store.url + "/rest/v1/" + table_and_query,
            body=body, headers=self.store._service_headers(prefer),
        )

    def _gateway_voice(self, row: dict[str, Any]) -> None:
        result = _http_json(
            "POST", self.args.gateway_url.rstrip("/") + "/v1/internal/voice-shards",
            {
                "shard_id": row["shard_id"], "url": row["url"],
                "provider": row["provider"], "region": row["region"],
                "capacity": int(row["capacity"]), "status": row.get("status", "ready"),
            },
            headers={"Authorization": "Bearer " + require_env("MUNEA_GATEWAY_ADMIN_KEY")},
        )
        if not result.get("ok"):
            raise DrillError("Gateway refused Voice shard update")

    def _mark(self, key: str) -> None:
        self.timeline[key] = time.time()

    # -- steps --------------------------------------------------------------
    def create_synthetic_account(self) -> None:
        suffix = uuid.uuid4().hex
        auth = self.store._json(
            "POST", self.store.url + "/auth/v1/admin/users",
            body={
                "email": f"queue-drill-{suffix}@example.invalid",
                "password": "Drill-" + uuid.uuid4().hex + "!9",
                "email_confirm": True,
                "user_metadata": {"purpose": "queue-burst-drill", "run_id": self.run_id},
            },
            headers=self.store._service_headers(),
        )
        self.user_id = str((auth or {}).get("id") or "")
        if not self.user_id:
            raise DrillError("temporary auth user creation returned no id")
        accounts = self._rest("POST", "accounts",
                              {"name": "Queue burst drill", "locale": "zh-TW"},
                              "return=representation")
        self.account_id = str((accounts or [{}])[0].get("id") or "")
        if not self.account_id:
            raise DrillError("temporary account creation returned no id")
        self._rest("POST", "account_members", {
            "account_id": self.account_id, "user_id": self.user_id,
            "role": "owner", "status": "active",
        }, "return=minimal")
        self._rest("POST", "credit_wallets", {
            "account_id": self.account_id, "wallet_type": "purchased",
            "period": "queue-drill-" + self.run_id, "balance": 4,
            "status": "active", "metadata": {"purpose": "queue-burst-drill"},
        }, "return=minimal")
        print(f"[1/7] isolated drill account ready (run_id={self.run_id})")

    def raise_voice_admission(self) -> None:
        """Real users must not be voice-rejected while drill calls hold seats."""
        rows = self._rest(
            "GET",
            "voice_shards?select=shard_id,url,provider,region,capacity,status"
            "&status=eq.ready&order=capacity.desc&limit=1",
        )
        if not rows:
            raise DrillError("no ready Voice shard found")
        self.voice_original = dict(rows[0])
        raised = dict(self.voice_original)
        raised["capacity"] = int(self.voice_original["capacity"]) + 3
        self._gateway_voice(raised)
        print(f"[2/7] Voice admission {self.voice_original['capacity']} -> "
              f"{raised['capacity']} for the drill window")

    def occupy_primary_and_queue_third(self) -> None:
        for index in (1, 2, 3):
            result = self.store.request_call(
                user_id=self.user_id, person_id=None, character_id="nening",
                idempotency_key=f"queue-drill-{self.run_id}-{index}", queue_max=30,
            )
            self.calls.append(result)
        first_two = self.calls[:2]
        if any(item.get("status") != "connect" for item in first_two):
            raise DrillError("first two calls did not reserve primary seats: "
                             + json.dumps(first_two))
        seats = sorted(str((c.get("worker") or {}).get("worker_id") or "") for c in first_two)
        third = self.calls[2]
        if third.get("status") != "queued":
            raise DrillError("third call did not queue: " + json.dumps(third))
        self._mark("third_queued")
        print(f"[3/7] primary seats taken ({', '.join(seats)}); third caller queued "
              f"(position={((third.get('queue') or {}).get('position'))}, "
              f"eta_s={((third.get('queue') or {}).get('eta_s'))})")

    def keep_queueing_until_promoted(self) -> None:
        """Behave like the real App while the busy card is showing: re-issue
        the same call request every ~10s. That keepalive is load-bearing --
        a queued caller who stops asking is kicked after ~45s (lock-screen
        zombie protection), and an empty queue tells the controller nothing
        needs to happen (first drill run on 2026-07-29 proved exactly this).
        The same poll also detects promotion: once the live controller has
        opened and registered a backup card, the request flips to connect."""
        deadline = time.monotonic() + self.args.scale_up_timeout
        backup_seen = ""
        result: dict[str, Any] = {}
        while time.monotonic() < deadline:
            # Keep the two seat-holding reservations alive exactly like real
            # in-progress calls do: leases expire 45-60s without a heartbeat,
            # and each re-request below runs the reaper first -- round 2 on
            # 2026-07-29 watched its own poll sweep the expired occupiers out
            # and hand the "queued" caller a primary seat. Heartbeats on
            # connecting (never-active) leases bill nothing.
            for occupier in self.calls[:2]:
                if occupier.get("status") != "connect":
                    continue
                beat = self.store.heartbeat(
                    call_id=str(occupier["call_id"]),
                    lease_version=int(occupier.get("lease_version") or 1),
                    component="app",
                    event_id="queue-drill-hb-" + uuid.uuid4().hex,
                    user_id=self.user_id,
                )
                if not beat.get("ok"):
                    raise DrillError(
                        "a seat-holding reservation went stale mid-drill: "
                        + json.dumps(beat)
                    )
            if not backup_seen:
                snapshot = self.gateway.snapshot()
                for worker in snapshot.get("workers", []):
                    if (str(worker.get("provider") or "") == "runpod"
                            and str(worker.get("status") or "") == "ready"):
                        backup_seen = str(worker.get("worker_id"))
                        self._mark("backup_ready")
                        waited = self.timeline["backup_ready"] - self.timeline["third_queued"]
                        print(f"[4/7] live controller opened backup {backup_seen} "
                              f"(region={worker.get('region')}) in {waited:.0f}s "
                              "from queue signal")
                        break
            result = self.store.request_call(
                user_id=self.user_id, person_id=None, character_id="nening",
                idempotency_key=f"queue-drill-{self.run_id}-3", queue_max=30,
            )
            if result.get("status") == "connect":
                # Record the connect FIRST so cleanup() can always release it
                # -- round 2 raised before recording and the orphaned lease
                # outlived the drill account (phantom seat again).
                self.calls[2] = result
                routed = str((result.get("worker") or {}).get("worker_id") or "")
                if not routed.startswith("runpod-"):
                    raise DrillError(
                        f"third caller connected to {routed}, expected a runpod backup"
                    )
                self._mark("third_connected")
                waited = self.timeline["third_connected"] - self.timeline["third_queued"]
                print(f"[5/7] third caller promoted to the fresh backup card "
                      f"{routed} ({waited:.0f}s queue-to-connect)")
                return
            time.sleep(10)
        raise DrillError(
            "third caller was not promoted within "
            f"{self.args.scale_up_timeout}s (backup_seen={backup_seen or 'none'}, "
            f"last={json.dumps({'status': result.get('status'), 'queue': result.get('queue')})})"
            " -- check munea-runpod-controller logs"
        )

    def release_calls(self) -> None:
        billed_total = 0
        for result in self.calls:
            if result.get("status") != "connect":
                continue
            released = self.store.release(
                call_id=str(result["call_id"]),
                lease_version=int(result.get("lease_version") or 1),
                event_id="queue-drill-release-" + uuid.uuid4().hex,
                reason="queue_burst_drill", user_id=self.user_id,
            )
            if not released.get("ok"):
                raise DrillError("a drill lease did not release cleanly")
            billed_total += int(released.get("billed_credits") or 0)
        if billed_total != 0:
            raise DrillError(f"drill must never bill credits (got {billed_total})")
        print("[6/7] all reservations released; billed credits = 0")

    def cleanup(self) -> None:
        # Ordering is load-bearing: leases MUST be released before the drill
        # account is deleted. Deleting the account cascade-deletes the lease
        # rows, but gpu_workers/voice_shards.active_leases are counters that
        # only munea_call_release/cancel decrement -- delete first and the
        # seats stay phantom-occupied forever (first 2026-07-29 drill run
        # leaked both primary seats this way; recovered via the gateway
        # admin surface).
        for result in self.calls:
            status = result.get("status")
            try:
                if status == "connect":
                    self.store.release(
                        call_id=str(result["call_id"]),
                        lease_version=int(result.get("lease_version") or 1),
                        event_id="queue-drill-cleanup-" + uuid.uuid4().hex,
                        reason="queue_burst_drill_cleanup", user_id=self.user_id,
                    )
                elif status == "queued":
                    self.store.cancel(call_id=str(result.get("call_id") or ""),
                                      user_id=self.user_id)
            except Exception:
                pass
        if self.voice_original is not None:
            try:
                self._gateway_voice(self.voice_original)
                print("[7/7] Voice admission restored to "
                      f"{self.voice_original['capacity']}")
            except Exception as exc:
                print(f"[7/7] WARNING: Voice restore failed: {exc}")
        if self.user_id:
            try:
                self.store._json(
                    "DELETE", self.store.url + "/auth/v1/admin/users/" + self.user_id,
                    headers=self.store._service_headers(),
                )
                print("[7/7] temporary drill account deleted")
            except Exception as exc:
                print(f"[7/7] WARNING: account deletion failed: {exc}")

    def run(self) -> None:
        try:
            self.create_synthetic_account()
            self.raise_voice_admission()
            self.occupy_primary_and_queue_third()
            self.keep_queueing_until_promoted()
            self.release_calls()
            print(json.dumps({
                "drill": "queue-burst", "run_id": self.run_id, "result": "PASS",
                "queue_to_backup_ready_s": round(
                    self.timeline["backup_ready"] - self.timeline["third_queued"], 1),
                "queue_to_connect_s": round(
                    self.timeline["third_connected"] - self.timeline["third_queued"], 1),
                "note": "backup card is left for the live controller's idle "
                        "timer (15 min) -- watch it terminate to complete the "
                        "auto-teardown half of the drill",
            }, ensure_ascii=False))
        finally:
            self.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-url",
                        default=os.environ.get(
                            "MUNEA_GATEWAY_URL",
                            "https://munea-call-control-fiu65jd4da-de.a.run.app"))
    parser.add_argument("--scale-up-timeout", type=int, default=900,
                        help="seconds to wait for the live controller to open "
                             "and health-gate a backup card (default 900)")
    parser.add_argument("--fetch-secrets", action="store_true",
                        help="fill missing env vars from GCP Secret Manager")
    parser.add_argument("--gcp-project", default="gen-lang-client-0229303523")
    args = parser.parse_args()
    if args.fetch_secrets:
        fetch_secrets_from_gcloud(args.gcp_project)
    Drill(args).run()


if __name__ == "__main__":
    main()
