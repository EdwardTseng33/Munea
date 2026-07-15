"""Minimal Slack webhook notifications with keyed alert deduplication."""

from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Callable, Mapping


DEDUP_SECONDS = 10 * 60


class SlackNotifyError(RuntimeError):
    """Raised when a Slack notification cannot be delivered."""


def _post_json(webhook_url: str, payload: bytes, timeout_seconds: float) -> None:
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "munea-gateway-monitor/1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", response.getcode())
            if status < 200 or status >= 300:
                raise SlackNotifyError(f"Slack webhook returned HTTP {status}")
    except SlackNotifyError:
        raise
    except Exception as exc:
        raise SlackNotifyError(f"Slack webhook request failed: {exc}") from exc


class SlackNotifier:
    """Send Slack alerts while suppressing a key for ten minutes after success."""

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout_seconds: float = 10.0,
        state_path: str | os.PathLike[str] | None = None,
        clock: Callable[[], float] = time.time,
        transport: Callable[[str, bytes, float], None] = _post_json,
        dedup_seconds: float = DEDUP_SECONDS,
    ) -> None:
        if not webhook_url.strip():
            raise ValueError("MUNEA_SLACK_ALERT_WEBHOOK is required")
        if dedup_seconds <= 0:
            raise ValueError("dedup_seconds must be positive")
        self.webhook_url = webhook_url.strip()
        self.timeout_seconds = timeout_seconds
        self.state_path = Path(state_path) if state_path else None
        self.clock = clock
        self.transport = transport
        self.dedup_seconds = float(dedup_seconds)
        self._last_sent = self._load_state()

    def _load_state(self) -> dict[str, float]:
        if self.state_path is None:
            return {}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, float] = {}
        for key, value in raw.items():
            try:
                result[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return result

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=self.state_path.name + ".",
            suffix=".tmp",
            dir=str(self.state_path.parent),
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(self._last_sent, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
            os.replace(temporary_name, self.state_path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    def is_suppressed(self, key: str, *, now: float | None = None) -> bool:
        current = self.clock() if now is None else now
        previous = self._last_sent.get(key)
        return previous is not None and 0 <= current - previous < self.dedup_seconds

    def send(
        self,
        key: str,
        message: str,
        *,
        fields: Mapping[str, object] | None = None,
    ) -> bool:
        """Return True when sent and False when the key is deduplicated."""
        if not key:
            raise ValueError("alert key is required")
        now = self.clock()
        if self.is_suppressed(key, now=now):
            return False

        lines = [message]
        if fields:
            lines.extend(f"{name}: {fields[name]}" for name in sorted(fields))
        payload = json.dumps(
            {"text": "\n".join(lines)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.transport(self.webhook_url, payload, self.timeout_seconds)
        self._last_sent[key] = now
        try:
            self._save_state()
        except OSError as exc:
            raise SlackNotifyError(f"could not persist alert dedup state: {exc}") from exc
        return True

    def clear(self, key: str) -> None:
        """Forget a resolved key so a later recurrence can notify immediately."""
        if key in self._last_sent:
            self._last_sent.pop(key, None)
            try:
                self._save_state()
            except OSError as exc:
                raise SlackNotifyError(f"could not persist alert dedup state: {exc}") from exc


def default_state_path() -> str:
    return os.path.join(tempfile.gettempdir(), "munea-gateway-monitor-dedup.json")
