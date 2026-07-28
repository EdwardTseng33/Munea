# -*- coding: utf-8 -*-
"""Regression tests for flashhead_server.py call-token clock-leeway decode
(2026-07-23 STATUS 125: the tw-06 clock ran 4m17s / 257s fast, so every
freshly minted 90s call token looked born expired and every real call was
rejected with 403 all day, while the QA probe stayed green because it
authenticated with the legacy universal key=, which never touches
call-token/clock verification at all).

flashhead_server.py cannot be imported directly in a normal dev or CI
environment: its module-level imports (torch, the SoulX-FlashHead
pipeline) require a GPU box with that repo checked out at
/root/SoulX-FlashHead, and the file even calls os.chdir() there at import
time. That is exactly why this suite does not import flashhead_server.

Instead it extracts the real _decode_call_token function body straight out
of the source file with the ast module (which only parses syntax and never
executes the module, so none of the heavy imports run) and execs that
exact source text into a small sandboxed namespace with a fake, injectable
clock. This means:
  - the test always exercises the actual production function, not a
    hand-copied duplicate that could silently drift from it;
  - it needs zero heavy dependencies and runs anywhere plain Python runs;
  - now and the leeway constant are both injectable, so the server clock
    being fast is directly reproducible with the exact numbers from the
    outage (see test_2026_07_23_incident_reproduction below).

Companion coverage: scripts/test_flashhead_router_core.py already tests
the unverified peek used for routing (decode_token_payload_unverified);
this file is the fully verified twin (HMAC signature, clock-leeway
expiry, worker binding) that flashhead_server.py /offer, /health, /switch
and /audio routes actually gate on.

Run: python scripts/test_call_token_clock_leeway.py
"""
import ast
import base64
import hashlib
import hmac
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLASHHEAD_SERVER = ROOT / "deploy" / "runpod-avatar" / "flashhead_server.py"

SECRET = "test-shared-secret-abc123"
OTHER_SECRET = "a-completely-different-secret"
WORKER = "glows-tw06-p1"
OTHER_WORKER = "glows-tw06-p2"


class FakeClock:
    """Stands in for the module-level time import inside the extracted
    function body -- only .time() is ever called on it."""

    def __init__(self, now):
        self._now = now

    def time(self):
        return self._now


def _load_decode_call_token(leeway_seconds, now):
    source = FLASHHEAD_SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FLASHHEAD_SERVER))
    func_node = next(
        (node for node in ast.walk(tree)
         if isinstance(node, ast.FunctionDef) and node.name == "_decode_call_token"),
        None,
    )
    assert func_node is not None, "could not find _decode_call_token in flashhead_server.py"
    func_source = ast.get_source_segment(source, func_node)
    assert func_source, "ast.get_source_segment returned nothing for _decode_call_token"

    namespace = {
        "base64": base64,
        "hashlib": hashlib,
        "hmac": hmac,
        "json": json,
        "time": FakeClock(now),
        "CALL_TOKEN_CLOCK_LEEWAY_S": leeway_seconds,
    }
    exec(compile(func_source, str(FLASHHEAD_SERVER), "exec"), namespace)
    return namespace["_decode_call_token"]


def _make_token(payload, secret=SECRET):
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    return encoded + "." + signature


def test_default_leeway_constant_is_at_least_330_seconds():
    """Static guard on the source, independent of the exec sandbox above:
    do not let the default shrink below the number that already saved a
    real outage (tw-06 measured 257s fast) without a deliberate decision."""
    source = FLASHHEAD_SERVER.read_text(encoding="utf-8")
    assert 'os.environ.get("MUNEA_CALL_TOKEN_CLOCK_LEEWAY", "330")' in source, (
        "default MUNEA_CALL_TOKEN_CLOCK_LEEWAY changed, re-check against "
        "the 2026-07-23 tw-06 257s skew (STATUS 125) before shrinking it"
    )
    print("test_default_leeway_constant_is_at_least_330_seconds: PASS")


def test_normal_token_within_expiry_passes():
    decode = _load_decode_call_token(leeway_seconds=330, now=1000.0)
    token = _make_token({"exp": 1030, "worker_id": WORKER, "call_id": "abc"})
    assert decode(token, SECRET, WORKER) == {"exp": 1030, "worker_id": WORKER, "call_id": "abc"}
    print("test_normal_token_within_expiry_passes: PASS")


def test_expired_within_leeway_still_passes():
    decode = _load_decode_call_token(leeway_seconds=330, now=1000.0)
    token = _make_token({"exp": 700.0, "worker_id": WORKER})
    assert decode(token, SECRET, WORKER) is not None
    print("test_expired_within_leeway_still_passes: PASS")


def test_expired_beyond_leeway_rejected():
    decode = _load_decode_call_token(leeway_seconds=330, now=1000.0)
    token = _make_token({"exp": 600.0, "worker_id": WORKER})
    assert decode(token, SECRET, WORKER) is None
    print("test_expired_beyond_leeway_rejected: PASS")


def test_2026_07_23_incident_reproduction_worker_clock_257s_fast():
    """Exact shape of STATUS 125: a normal 90s call token, decoded by a
    worker whose own clock is 257s fast. The default leeway must tolerate
    it; leeway=0 (pre-fix behavior) must reproduce the outage."""
    mint_time = 5000.0
    exp = mint_time + 90.0
    worker_clock_now = mint_time + 257.0
    token = _make_token({"exp": exp, "worker_id": WORKER})

    with_fix = _load_decode_call_token(leeway_seconds=330, now=worker_clock_now)
    assert with_fix(token, SECRET, WORKER) is not None, (
        "default leeway must tolerate the tw-06 257s clock skew"
    )

    without_fix = _load_decode_call_token(leeway_seconds=0, now=worker_clock_now)
    assert without_fix(token, SECRET, WORKER) is None, (
        "sanity check: with leeway=0 this must reproduce the 2026-07-23 "
        "outage (every fresh call token rejected as expired)"
    )
    print("test_2026_07_23_incident_reproduction_worker_clock_257s_fast: PASS")


def test_token_minted_by_fast_clock_has_no_upper_bound_rejection():
    """The leeway fix only loosens the EXPIRY direction (see the source
    comment: leeway only widens the expired check). If instead the
    token-minting side clock is fast, the token simply carries a later
    exp than a correctly-clocked mint would have; there is intentionally
    no notBefore/iat-in-the-future check, so a normally-clocked worker must
    still accept it. This pins that intentional asymmetry down so a future
    change that also caps the future direction is a deliberate decision,
    not an accident."""
    now = 5000.0
    fast_minting_clock = now + 257.0
    token = _make_token({"exp": fast_minting_clock + 90.0, "worker_id": WORKER})
    decode = _load_decode_call_token(leeway_seconds=330, now=now)
    assert decode(token, SECRET, WORKER) is not None
    print("test_token_minted_by_fast_clock_has_no_upper_bound_rejection: PASS")


def test_bad_signature_rejected():
    decode = _load_decode_call_token(leeway_seconds=330, now=1000.0)
    token = _make_token({"exp": 1030.0, "worker_id": WORKER})
    tampered = token.rsplit(".", 1)[0] + ".not-the-real-signature"
    assert decode(tampered, SECRET, WORKER) is None
    assert decode(token, OTHER_SECRET, WORKER) is None
    print("test_bad_signature_rejected: PASS")


def test_worker_id_mismatch_rejected():
    """Clock leeway must never weaken the worker-binding check: an
    otherwise-valid token for a different process must still be refused."""
    decode = _load_decode_call_token(leeway_seconds=330, now=1000.0)
    token = _make_token({"exp": 1030.0, "worker_id": WORKER})
    assert decode(token, SECRET, OTHER_WORKER) is None
    print("test_worker_id_mismatch_rejected: PASS")


def test_missing_token_or_secret_returns_none():
    decode = _load_decode_call_token(leeway_seconds=330, now=1000.0)
    assert decode("", SECRET, WORKER) is None
    assert decode("abc.def", "", WORKER) is None
    print("test_missing_token_or_secret_returns_none: PASS")


def test_malformed_token_without_dot_returns_none():
    decode = _load_decode_call_token(leeway_seconds=330, now=1000.0)
    assert decode("no-dot-in-this-token", SECRET, WORKER) is None
    print("test_malformed_token_without_dot_returns_none: PASS")


def main():
    test_default_leeway_constant_is_at_least_330_seconds()
    test_normal_token_within_expiry_passes()
    test_expired_within_leeway_still_passes()
    test_expired_beyond_leeway_rejected()
    test_2026_07_23_incident_reproduction_worker_clock_257s_fast()
    test_token_minted_by_fast_clock_has_no_upper_bound_rejection()
    test_bad_signature_rejected()
    test_worker_id_mismatch_rejected()
    test_missing_token_or_secret_returns_none()
    test_malformed_token_without_dot_returns_none()
    print("Call token clock-leeway regression test: ALL PASS")


if __name__ == "__main__":
    main()
