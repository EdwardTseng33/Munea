#!/usr/bin/env python3
"""放掉舊版本白養的待命機器（Cloud Run 的 revision tag × min-instances 漏洞）。

背景（2026-11-17 查帳發現）：
正式部署會給每個新版本掛一個 tag，並設「至少一台待命」（--min-instances 1）。
切流量之後，舊版本的 tag 沒人拿掉——而 Cloud Run 只要版本還掛著 tag，就會替它
把那台待命機器一直開著、照樣計費，即使它一個客人都沒有。
11/17 當天有 4 台這樣白養的機器（其中一台從 8/10 養到現在），待命費用因此是
該有的 3 倍，而且每上線一次就多一台。

做法：只拿掉 tag，不刪版本、不動流量。版本還在，回滾照樣用版本名稱
（`--to-revisions <名稱>=100`），只是第一個請求要等它冷啟動幾秒。

只收「比現在正在服務的版本還舊」的：比它新的、還沒切過去的候選版本
（例如等真機驗收的 canary）一律不碰。

用法：
  python deploy/cloudrun/release_stale_warm.py munea-brain            # 只看，不動
  python deploy/cloudrun/release_stale_warm.py munea-brain --apply    # 真的收
  python deploy/cloudrun/release_stale_warm.py --all --apply          # 專案內每個服務
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from typing import Any, Iterable

DEFAULT_PROJECT = "gen-lang-client-0229303523"
DEFAULT_REGION = "asia-east1"
MIN_SCALE_KEY = "autoscaling.knative.dev/minScale"


def _min_scale(revision: dict[str, Any]) -> int:
    raw = (revision.get("metadata", {}).get("annotations", {}) or {}).get(MIN_SCALE_KEY, "0")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _created(revision: dict[str, Any]) -> str:
    # RFC 3339 UTC timestamps sort correctly as plain strings.
    return str(revision.get("metadata", {}).get("creationTimestamp") or "")


def stale_warm_tags(service: dict[str, Any], revisions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tags that keep an idle min-instance alive on a superseded revision.

    A tag is stale-and-warm when its revision (1) serves 0% traffic,
    (2) has min-instances > 0, and (3) is older than every revision that is
    currently serving. Returns [{"tag", "revision", "minScale", "created"}].
    """
    by_name = {str(r.get("metadata", {}).get("name") or ""): r for r in revisions}
    traffic = list(service.get("status", {}).get("traffic", []) or [])
    serving = {
        str(item.get("revisionName") or "")
        for item in traffic
        if int(item.get("percent") or 0) > 0
    }
    serving_created = [_created(by_name[name]) for name in serving if name in by_name]
    if not serving or len(serving_created) != len(serving) or not all(serving_created):
        # Cannot tell what is live: touch nothing.
        return []
    oldest_serving = min(serving_created)

    stale: list[dict[str, Any]] = []
    for item in traffic:
        tag = str(item.get("tag") or "")
        name = str(item.get("revisionName") or "")
        if not tag or not name or name in serving:
            continue
        if int(item.get("percent") or 0) > 0:
            continue
        revision = by_name.get(name)
        if revision is None:
            continue
        created = _created(revision)
        if _min_scale(revision) <= 0 or not created or created >= oldest_serving:
            continue
        stale.append({
            "tag": tag,
            "revision": name,
            "minScale": _min_scale(revision),
            "created": created,
        })
    return sorted(stale, key=lambda entry: entry["created"])


def _gcloud() -> str:
    for candidate in ("gcloud", "gcloud.cmd"):
        found = shutil.which(candidate)
        if found:
            return found
    raise SystemExit("找不到 gcloud；請先將 Google Cloud SDK 加入 PATH")


def _run_json(args: list[str]) -> Any:
    completed = subprocess.run([_gcloud(), *args, "--format=json"], capture_output=True, text=True, encoding="utf-8")
    if completed.returncode != 0:
        raise SystemExit(f"gcloud 失敗：{completed.stderr.strip()[:400]}")
    return json.loads(completed.stdout or "null")


def sweep(service_name: str, *, project: str, region: str, apply: bool) -> list[dict[str, Any]]:
    service = _run_json(["run", "services", "describe", service_name, "--project", project, "--region", region])
    revisions = _run_json([
        "run", "revisions", "list", "--service", service_name,
        "--project", project, "--region", region, "--limit", "1000",
    ]) or []
    stale = stale_warm_tags(service, revisions)
    for entry in stale:
        print(f"  {service_name}: {entry['revision']}（{entry['created'][:10]}）還掛著 {entry['tag']}、白養 {entry['minScale']} 台待命")
    if stale and apply:
        tags = ",".join(entry["tag"] for entry in stale)
        completed = subprocess.run(
            [_gcloud(), "run", "services", "update-traffic", service_name,
             "--project", project, "--region", region, "--remove-tags", tags, "--quiet"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if completed.returncode != 0:
            raise SystemExit(f"拿掉 tag 失敗：{completed.stderr.strip()[:400]}")
        print(f"  {service_name}: 已放掉 {len(stale)} 台白養的待命機器（版本還在、可回滾）")
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="放掉舊版本白養的 Cloud Run 待命機器")
    parser.add_argument("service", nargs="?", help="Cloud Run 服務名稱，例如 munea-brain")
    parser.add_argument("--all", action="store_true", help="專案內每個服務都看一遍")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--apply", action="store_true", help="真的拿掉 tag（沒加只列出來）")
    args = parser.parse_args(argv)
    if bool(args.service) == bool(args.all):
        parser.error("請指定一個服務名稱，或用 --all")

    if args.all:
        services = [
            item["metadata"]["name"]
            for item in _run_json(["run", "services", "list", "--project", args.project, "--region", args.region]) or []
        ]
    else:
        services = [args.service]

    total = 0
    for name in services:
        total += len(sweep(name, project=args.project, region=args.region, apply=args.apply))
    if total == 0:
        print("沒有白養的待命機器。")
    elif not args.apply:
        print(f"共 {total} 台白養的待命機器；加 --apply 才會真的放掉。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
