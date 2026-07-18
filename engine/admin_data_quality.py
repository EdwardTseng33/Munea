"""Request-scoped provenance contract for the Munea operations console."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping


SCHEMA = "munea.admin-data-meta.v1"
_TRACE: ContextVar[list[dict[str, Any]] | None] = ContextVar("munea_admin_data_trace", default=None)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def latest_record_timestamp(
    records: Iterable[Mapping[str, Any]] | None,
    fields: tuple[str, ...] = ("updatedAt", "eventTime", "createdAt", "requestedAt"),
) -> str | None:
    latest: datetime | None = None
    for record in records or []:
        if not isinstance(record, Mapping):
            continue
        for field in fields:
            parsed = _parse_timestamp(record.get(field))
            if parsed is not None and (latest is None or parsed > latest):
                latest = parsed
    return latest.strftime("%Y-%m-%dT%H:%M:%SZ") if latest else None


def record_admin_data_source(
    dataset: str,
    provider: str,
    *,
    record_count: int | None,
    data_as_of: str | None = None,
    authority: str = "primary",
    degraded: bool = False,
    degradation_reason: str | None = None,
) -> None:
    trace = _TRACE.get()
    if trace is None:
        return
    trace.append({
        "dataset": str(dataset),
        "provider": str(provider),
        "authority": str(authority),
        "recordCount": max(0, int(record_count or 0)),
        "dataAsOf": data_as_of,
        "freshness": {
            "status": "unknown",
            "reason": "source_watermark_unavailable" if data_as_of else "no_record_timestamp",
        },
        "degraded": bool(degraded),
        "degradationReason": str(degradation_reason) if degradation_reason else None,
    })


def _merge_sources(sources: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    for source in sources:
        key = (
            str(source.get("dataset") or "unknown"),
            str(source.get("provider") or "unknown"),
            str(source.get("authority") or "unknown"),
            str(source.get("degradationReason")) if source.get("degradationReason") else None,
        )
        current = merged.get(key)
        if current is None:
            merged[key] = dict(source)
            continue
        current["recordCount"] = max(int(current.get("recordCount") or 0), int(source.get("recordCount") or 0))
        current_time = _parse_timestamp(current.get("dataAsOf"))
        candidate_time = _parse_timestamp(source.get("dataAsOf"))
        if candidate_time is not None and (current_time is None or candidate_time > current_time):
            current["dataAsOf"] = source.get("dataAsOf")
            current["freshness"] = dict(source.get("freshness") or {})
        current["degraded"] = bool(current.get("degraded") or source.get("degraded"))
    return sorted(merged.values(), key=lambda item: (item["dataset"], item["provider"], item["authority"]))


def build_admin_data_meta(metric_version: str, sources: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = _merge_sources(sources)
    degraded = any(source.get("degraded") for source in normalized)
    timestamps = [_parse_timestamp(source.get("dataAsOf")) for source in normalized]
    valid_timestamps = [value for value in timestamps if value is not None]
    data_as_of = max(valid_timestamps).strftime("%Y-%m-%dT%H:%M:%SZ") if valid_timestamps else None
    record_count = sum(int(source.get("recordCount") or 0) for source in normalized)
    reasons = sorted({
        str(source.get("degradationReason"))
        for source in normalized
        if source.get("degradationReason")
    })
    if not normalized:
        status = "unverified"
        degraded = True
        reasons = ["source_metadata_missing"]
    elif degraded:
        status = "degraded"
    elif record_count == 0:
        status = "empty"
    else:
        status = "unverified"
    return {
        "schema": SCHEMA,
        "metricVersion": str(metric_version),
        "generatedAt": utc_now(),
        "dataAsOf": data_as_of,
        "status": status,
        "degraded": degraded,
        "degradationReasons": reasons,
        "freshness": {
            "status": "unknown",
            "reason": "source_watermark_unavailable" if normalized else "source_metadata_missing",
        },
        "sources": normalized,
    }


def admin_contract_response(metric_version: str, producer: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    token = _TRACE.set([])
    try:
        payload = dict(producer() or {})
        sources = list(_TRACE.get() or [])
    finally:
        _TRACE.reset(token)
    payload["meta"] = build_admin_data_meta(metric_version, sources)
    return payload
