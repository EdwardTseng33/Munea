#!/usr/bin/env python3
"""Probe the Munea call chain and name the first failing service stage.

This checks service readiness without pretending to replace the iPhone media
gate. The installed App's voice-call diagnostics cover microphone, WebRTC,
first frame, first audio, ASR, and playback stages with the same stage names.

For a zero-traffic Voice revision, use --profile production together with
--voice-canary-url. The probe still acquires a real Gateway lease and call token,
routes only the Voice WebSocket to the allowlisted tagged revision, then releases
the lease. It never treats that ready handshake as a real-device media PASS.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Stage:
    name: str
    status: str
    duration_ms: int
    detail: str = ""
    endpoint: str = ""


@dataclass
class ProbeReport:
    profile: str
    started_at: str
    stages: list[Stage] = field(default_factory=list)

    def add(self, name, status, started, detail="", endpoint=""):
        self.stages.append(Stage(
            name=name,
            status=status,
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
            detail=str(detail or "")[:160],
            endpoint=redact_endpoint(endpoint),
        ))

    @property
    def passed(self):
        required = ("voice_ready", "avatar_health") if self.profile == "development" else (
            "gateway_health", "gateway_lease", "voice_ready", "avatar_health", "gateway_release",
        )
        statuses = {stage.name: stage.status for stage in self.stages}
        return all(statuses.get(name) == "PASS" for name in required)

    @property
    def first_failure(self):
        return next((stage.name for stage in self.stages if stage.status == "FAIL"), "")

    @property
    def first_blocker(self):
        required = ("voice_ready", "avatar_health") if self.profile == "development" else (
            "gateway_health", "gateway_lease", "voice_ready", "avatar_health", "gateway_release",
        )
        statuses = {stage.name: stage.status for stage in self.stages}
        return next((name for name in required if statuses.get(name) != "PASS"), "")

    def payload(self):
        return {
            "ok": self.passed,
            "profile": self.profile,
            "startedAt": self.started_at,
            "firstFailure": self.first_failure,
            "firstBlocker": self.first_blocker,
            "stages": [asdict(stage) for stage in self.stages],
            "scope": {
                "serviceReadiness": True,
                "realDeviceMediaGate": False,
                "rawAudioStored": False,
                "credentialsStored": False,
            },
        }


def redact_endpoint(value):
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(str(value))
    if parsed.scheme and parsed.hostname:
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = hostname + (f":{parsed.port}" if parsed.port else "")
        return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))[:160]
    return str(value).split("?", 1)[0].split("#", 1)[0].split("@", 1)[-1][:160]


def _js_constant(source, name):
    match = re.search(r"(?:const|let|var)\s+" + re.escape(name) + r"\s*=\s*['\"]([^'\"]+)['\"]", source)
    return match.group(1) if match else ""


def load_repo_profile(profile="development", root=ROOT):
    app_source = (Path(root) / "web" / "src" / "app.js").read_text(encoding="utf-8")
    config = {
        "voice_url": _js_constant(app_source, "LIVE_VOICE_URL_DEFAULT"),
        "avatar_url": _js_constant(app_source, "FLASHHEAD_URL_DEFAULT"),
        "gateway_url": _js_constant(app_source, "CALL_CONTROL_URL_DEFAULT"),
        "app_key": _js_constant(app_source, "MUNEA_APP_KEY"),
    }
    if profile == "development":
        profile_source = (Path(root) / "scripts" / "enable-ios-development-profile.mjs").read_text(encoding="utf-8")
        dev_voice = re.search(r"voiceUrl:\s*['\"]([^'\"]+)['\"]", profile_source)
        if dev_voice:
            config["voice_url"] = dev_voice.group(1)
        config["gateway_url"] = ""
    return config


def with_query(url, **values):
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in values.items():
        if value and key not in query:
            query[key] = value
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))


def validate_voice_canary_url(value):
    """Allow a call token override only to this project's tagged Voice service."""
    value = str(value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    hostname = (parsed.hostname or "").lower()
    allowed_suffixes = (
        "---munea-voice-staging-fiu65jd4da-de.a.run.app",
        "---munea-voice-staging-491603544409.asia-east1.run.app",
    )
    safe = (
        parsed.scheme == "wss"
        and parsed.username is None
        and parsed.password is None
        and parsed.port is None
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment
        and hostname.startswith("canary-")
        and any(hostname.endswith(suffix) for suffix in allowed_suffixes)
    )
    if not safe:
        raise ValueError(
            "Voice canary URL must be a query-free wss://canary-* tag for this project's munea-voice-staging service"
        )
    return "wss://" + hostname


def get_json(url, timeout, bearer=""):
    headers = {"Accept": "application/json", "User-Agent": "munea-voice-chain-probe/1"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
        return response.status, body


def post_json(url, payload, timeout, bearer=""):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "munea-voice-chain-probe/1",
    }
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
        return response.status, body


async def probe_voice_ready(report, voice_url, app_key, timeout, call_token=""):
    started = time.monotonic()
    if not voice_url:
        report.add("voice_ready", "SKIP", started, "voice URL is not configured")
        return
    try:
        import websockets
        auth = {"token": call_token} if call_token else {"key": app_key}
        url = with_query(voice_url, **auth, char="寧寧", user="自動巡檢", fam="0")
        async with websockets.connect(url, open_timeout=timeout, close_timeout=2, max_size=None) as websocket:
            while True:
                message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                if not isinstance(message, str):
                    continue
                event = json.loads(message)
                if event.get("type") == "ready":
                    report.add("voice_ready", "PASS", started, "WebSocket opened and Voice reported ready", voice_url)
                    return
    except Exception as error:
        code = getattr(error, "code", "")
        reason = getattr(error, "reason", "")
        detail = type(error).__name__ + (f" code={code}" if code else "") + (f" reason={reason}" if reason else "")
        report.add("voice_ready", "FAIL", started, detail, voice_url)


def acquire_gateway_lease(report, gateway_url, access_token, timeout):
    started = time.monotonic()
    if not gateway_url:
        report.add("gateway_lease", "SKIP", started, "Gateway is not used by this profile")
        return None
    if not access_token:
        report.add("gateway_lease", "SKIP", started, "MUNEA_ACCESS_TOKEN is required for the production lease path", gateway_url)
        return None
    idempotency_key = "probe-" + str(uuid.uuid4())
    deadline = time.monotonic() + timeout
    pending_lease = None
    try:
        while time.monotonic() < deadline:
            _, lease = post_json(
                gateway_url.rstrip("/") + "/v1/calls",
                {"character_id": "寧寧", "idempotency_key": idempotency_key},
                min(timeout, 12),
                bearer=access_token,
            )
            if isinstance(lease, dict) and lease.get("call_id"):
                pending_lease = lease
            if not isinstance(lease, dict):
                report.add("gateway_lease", "FAIL", started, "Gateway returned a malformed lease payload", gateway_url)
                cleanup_failed_gateway_lease(report, gateway_url, access_token, pending_lease, timeout)
                return None
            if lease.get("status") == "connect":
                if not (lease.get("call_token") and (lease.get("voice") or {}).get("url") and (lease.get("worker") or {}).get("url")):
                    report.add("gateway_lease", "FAIL", started, "connect response is missing paired endpoints or call token", gateway_url)
                    cleanup_failed_gateway_lease(report, gateway_url, access_token, pending_lease, timeout)
                    return None
                report.add("gateway_lease", "PASS", started, "paired Voice and Avatar lease assigned", gateway_url)
                return lease
            if lease.get("status") != "queued":
                report.add("gateway_lease", "FAIL", started, lease.get("reason") or "unexpected Gateway response", gateway_url)
                cleanup_failed_gateway_lease(report, gateway_url, access_token, pending_lease, timeout)
                return None
            time.sleep(1.5)
        report.add("gateway_lease", "FAIL", started, "Gateway queue timed out", gateway_url)
        cleanup_failed_gateway_lease(report, gateway_url, access_token, pending_lease, timeout)
    except urllib.error.HTTPError as error:
        report.add("gateway_lease", "FAIL", started, f"HTTP {error.code}", gateway_url)
        cleanup_failed_gateway_lease(report, gateway_url, access_token, pending_lease, timeout)
    except Exception as error:
        report.add("gateway_lease", "FAIL", started, type(error).__name__, gateway_url)
        cleanup_failed_gateway_lease(report, gateway_url, access_token, pending_lease, timeout)
    return None


def cleanup_failed_gateway_lease(report, gateway_url, access_token, lease, timeout):
    """Best-effort cleanup for leases that cannot be returned to run_probe()."""
    if not isinstance(lease, dict) or not lease.get("call_id"):
        return False
    started = time.monotonic()
    call_id = urllib.parse.quote(str(lease["call_id"]))
    try:
        if lease.get("status") == "connect" and lease.get("lease_version") is not None:
            post_json(
                gateway_url.rstrip("/") + "/v1/calls/" + call_id + "/release",
                {
                    "lease_version": lease["lease_version"],
                    "event_id": "probe-abort-" + str(uuid.uuid4()),
                    "reason": "diagnostic_probe_invalid_response",
                },
                timeout,
                bearer=access_token,
            )
            detail = "partial connect lease released"
        else:
            post_json(
                gateway_url.rstrip("/") + "/v1/calls/" + call_id + "/cancel",
                {},
                timeout,
                bearer=access_token,
            )
            detail = "queued diagnostic lease cancelled"
        report.add("gateway_cleanup", "PASS", started, detail, gateway_url)
        return True
    except Exception as error:
        report.add("gateway_cleanup", "FAIL", started, type(error).__name__, gateway_url)
        return False


def release_gateway_lease(report, gateway_url, access_token, lease, timeout):
    started = time.monotonic()
    if not lease:
        return
    try:
        post_json(
            gateway_url.rstrip("/") + "/v1/calls/" + urllib.parse.quote(str(lease["call_id"])) + "/release",
            {
                "lease_version": lease["lease_version"],
                "event_id": "probe-release-" + str(uuid.uuid4()),
                "reason": "diagnostic_probe_complete",
            },
            timeout,
            bearer=access_token,
        )
        report.add("gateway_release", "PASS", started, "diagnostic lease released", gateway_url)
    except Exception as error:
        report.add("gateway_release", "FAIL", started, type(error).__name__, gateway_url)


def probe_http_health(report, name, base_url, app_key, timeout, durable=False, bearer=""):
    started = time.monotonic()
    if not base_url:
        report.add(name, "SKIP", started, "endpoint is not configured")
        return
    try:
        status, body = get_json(
            with_query(base_url.rstrip("/") + "/health", key=app_key), timeout, bearer=bearer
        )
        ok = status == 200 and body.get("ok") is True
        if durable:
            ok = ok and body.get("durable_ready") is True
        detail = "ok" if ok else str(body.get("error") or body.get("durable_error") or "health returned not-ready")
        report.add(name, "PASS" if ok else "FAIL", started, detail, base_url)
    except urllib.error.HTTPError as error:
        report.add(name, "FAIL", started, f"HTTP {error.code}", base_url)
    except Exception as error:
        report.add(name, "FAIL", started, type(error).__name__, base_url)


async def run_probe(args):
    config = load_repo_profile(args.profile, Path(args.root))
    voice_url = args.voice_url or os.environ.get("MUNEA_VOICE_URL") or config["voice_url"]
    avatar_url = args.avatar_url or os.environ.get("MUNEA_AVATAR_URL") or config["avatar_url"]
    gateway_url = args.gateway_url or os.environ.get("MUNEA_GATEWAY_URL") or config["gateway_url"]
    app_key = args.app_key or os.environ.get("MUNEA_APP_KEY") or config["app_key"]
    access_token = os.environ.get("MUNEA_ACCESS_TOKEN") or ""
    voice_canary_url = getattr(args, "voice_canary_url", "") or ""
    report = ProbeReport(args.profile, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    lease = None
    try:
        probe_http_health(
            report, "gateway_health", gateway_url, app_key, args.timeout,
            durable=True, bearer=access_token,
        )
        lease = acquire_gateway_lease(report, gateway_url, access_token, args.timeout) if args.profile == "production" else None
        if lease:
            voice_url = voice_canary_url or lease["voice"]["url"]
            avatar_url = lease["worker"]["url"]
            if voice_canary_url:
                started = time.monotonic()
                report.add("voice_route", "PASS", started, "Gateway call token routed to explicit 0% canary", voice_url)
            await probe_voice_ready(report, voice_url, app_key, args.timeout, call_token=lease["call_token"])
        elif args.profile == "development":
            await probe_voice_ready(report, voice_url, app_key, args.timeout)
        else:
            started = time.monotonic()
            report.add("voice_ready", "SKIP", started, "production Voice needs a Gateway call token")
        probe_http_health(report, "avatar_health", avatar_url, app_key, args.timeout)
        started = time.monotonic()
        report.add(
            "real_device_media_gate",
            "SKIP",
            started,
            "microphone, WebRTC offer, first frame/audio and ASR are recorded by the installed App trace",
        )
    finally:
        release_gateway_lease(report, gateway_url, access_token, lease, args.timeout)
    return report


def print_report(report):
    for stage in report.stages:
        endpoint = f" {stage.endpoint}" if stage.endpoint else ""
        detail = f" - {stage.detail}" if stage.detail else ""
        print(f"{stage.status} {stage.name} ({stage.duration_ms}ms){endpoint}{detail}")
    print(("PASS" if report.passed else "FAIL") + " voice chain service readiness")
    if report.first_failure:
        print("first_failure=" + report.first_failure)
    elif report.first_blocker:
        print("first_blocker=" + report.first_blocker)
    print("NOTE real-device media Gate remains separate")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("development", "production"), default="development")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--gateway-url", default="")
    parser.add_argument("--voice-url", default="")
    parser.add_argument(
        "--voice-canary-url",
        default=os.environ.get("MUNEA_VOICE_CANARY_URL", ""),
        help="Production-only tagged Voice canary URL; still obtains a real Gateway call token first",
    )
    parser.add_argument("--avatar-url", default="")
    parser.add_argument("--app-key", default="")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--json-output", default="")
    args = parser.parse_args()
    if args.voice_canary_url and args.profile != "production":
        parser.error("--voice-canary-url requires --profile production")
    try:
        args.voice_canary_url = validate_voice_canary_url(args.voice_canary_url)
    except ValueError as error:
        parser.error(str(error))
    report = asyncio.run(run_probe(args))
    print_report(report)
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report.payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
