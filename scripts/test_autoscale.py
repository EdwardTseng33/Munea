# -*- coding: utf-8 -*-
"""GLOWS 自動開卡/查詢/退卡 · 本機 mock 測試（2026-07-13 卡西法）。

不真打 GLOWS API、不真連 SSH、不真花錢——把 deploy/glows/glowsctl.py 的
create/get_status/release/list_instances 跟 deploy/glows/autoscale.py 的
_ssh_run/_http_get_json 整支換成假的，驗證 open_card() 那串「建->等 Running->
拿門牌->起服務->驗health->return」的流程邏輯、逾時/失敗會清理（release 半殘
機器）、close_card()/list_cards() 的行為，以及跟 deploy/gateway/ WorkerRegistry
的接線點。

跑法：python scripts/test_autoscale.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOWS_DIR = ROOT / "deploy" / "glows"
GATEWAY_DIR = ROOT / "deploy" / "gateway"

sys.path.insert(0, str(GLOWS_DIR))
sys.path.insert(0, str(GATEWAY_DIR))

import glowsctl as gc  # noqa: E402
import autoscale as asc  # noqa: E402
import gateway_core as gwc  # noqa: E402

_ORIG = {
    "create": gc.create,
    "get_status": gc.get_status,
    "release": gc.release,
    "list_instances": gc.list_instances,
    "_ssh_run": asc._ssh_run,
    "_http_get_json": asc._http_get_json,
}


def _restore():
    gc.create = _ORIG["create"]
    gc.get_status = _ORIG["get_status"]
    gc.release = _ORIG["release"]
    gc.list_instances = _ORIG["list_instances"]
    asc._ssh_run = _ORIG["_ssh_run"]
    asc._http_get_json = _ORIG["_http_get_json"]


def test_open_card_happy_path():
    calls = {"get_status": 0, "ssh": 0, "http": 0, "release": 0}

    def fake_create(from_snapshot_id=None, regions=None):
        assert from_snapshot_id == "snap-1", "should pass from_snapshot_id through to glowsctl.create"
        return {"instanceID": "ins-abc"}, "TW-03"

    def fake_get_status(instance_id):
        calls["get_status"] += 1
        if calls["get_status"] == 1:
            return {"status": "SchedQueued", "accesses": []}
        return {"status": "Running", "accesses": [
            {"protocol": "http", "listenPort": 8888, "url": "https://tw-03.access.glows.ai:25220"},
            {"protocol": "ssh", "listenPort": 25221, "url": "root@tw-03.access.glows.ai:25221"},
        ]}

    def fake_ssh_run(host, port, cmd, timeout=60):
        calls["ssh"] += 1
        assert host == "tw-03.access.glows.ai"
        assert port == 25221
        assert cmd == asc.RESTART_SCRIPT_REMOTE
        return "flashhead restarted"

    def fake_http_get_json(url, timeout=10):
        calls["http"] += 1
        assert url.endswith("/health")
        if calls["http"] == 1:
            return {"ok": False}
        return {"ok": True, "engine": "flashhead-lite-standalone"}

    def fake_release(instance_id):
        calls["release"] += 1
        return {"ok": True}

    gc.create = fake_create
    gc.get_status = fake_get_status
    gc.release = fake_release
    asc._ssh_run = fake_ssh_run
    asc._http_get_json = fake_http_get_json

    try:
        result = asc.open_card(from_snapshot_id="snap-1", poll_interval_s=0.01,
                                create_timeout_s=5, health_timeout_s=5,
                                ssh_attempts=2, ssh_retry_wait_s=0.01)
        assert result["instance_id"] == "ins-abc"
        assert result["ssh_host"] == "tw-03.access.glows.ai"
        assert result["ssh_port"] == 25221
        assert result["http_url"] == "https://tw-03.access.glows.ai:25220"
        assert result["region"] == "TW-03"
        assert result["ready_s"] >= 0
        assert calls["ssh"] == 1, "ssh should succeed on first attempt, no retry needed"
        assert calls["http"] == 2, "health check should poll until ok=True"
        assert calls["release"] == 0, "success path must not release the instance"
    finally:
        _restore()
    print("test_open_card_happy_path: PASS")


def test_open_card_create_timeout_cleans_up():
    calls = {"release": 0, "released_id": None}

    def fake_create(from_snapshot_id=None, regions=None):
        return {"instanceID": "ins-timeout"}, "TW-03"

    def fake_get_status(instance_id):
        return {"status": "SchedQueued", "accesses": []}  # 永遠不到 Running

    def fake_release(instance_id):
        calls["release"] += 1
        calls["released_id"] = instance_id
        return {"ok": True}

    gc.create = fake_create
    gc.get_status = fake_get_status
    gc.release = fake_release

    try:
        raised = False
        try:
            asc.open_card(create_timeout_s=0.05, poll_interval_s=0.01)
        except asc.OpenCardError:
            raised = True
        assert raised, "must raise OpenCardError when Running never arrives before timeout"
        assert calls["release"] == 1, "half-broken instance must be released, not left burning money"
        assert calls["released_id"] == "ins-timeout"
    finally:
        _restore()
    print("test_open_card_create_timeout_cleans_up: PASS")


def test_open_card_ssh_failure_cleans_up():
    calls = {"release": 0, "ssh": 0}

    def fake_create(from_snapshot_id=None, regions=None):
        return {"instanceID": "ins-ssh-fail"}, "TW-04"

    def fake_get_status(instance_id):
        return {"status": "Running", "accesses": [
            {"protocol": "http", "listenPort": 8888, "url": "https://tw-04.access.glows.ai:1"},
            {"protocol": "ssh", "listenPort": 2, "url": "root@tw-04.access.glows.ai:2"},
        ]}

    def fake_ssh_run(host, port, cmd, timeout=60):
        calls["ssh"] += 1
        raise RuntimeError("connection refused (ssh daemon not up yet)")

    def fake_release(instance_id):
        calls["release"] += 1
        return {"ok": True}

    gc.create = fake_create
    gc.get_status = fake_get_status
    gc.release = fake_release
    asc._ssh_run = fake_ssh_run

    try:
        raised = False
        try:
            asc.open_card(poll_interval_s=0.01, create_timeout_s=5,
                           ssh_attempts=3, ssh_retry_wait_s=0.01)
        except asc.OpenCardError:
            raised = True
        assert raised
        assert calls["ssh"] == 3, "must retry ssh_attempts times before giving up"
        assert calls["release"] == 1
    finally:
        _restore()
    print("test_open_card_ssh_failure_cleans_up: PASS")


def test_open_card_health_timeout_cleans_up():
    calls = {"release": 0, "http": 0}

    def fake_create(from_snapshot_id=None, regions=None):
        return {"instanceID": "ins-health-fail"}, "TW-03"

    def fake_get_status(instance_id):
        return {"status": "Running", "accesses": [
            {"protocol": "http", "listenPort": 8888, "url": "https://tw-03.access.glows.ai:9"},
            {"protocol": "ssh", "listenPort": 10, "url": "root@tw-03.access.glows.ai:10"},
        ]}

    def fake_ssh_run(host, port, cmd, timeout=60):
        return "ok"

    def fake_http_get_json(url, timeout=10):
        calls["http"] += 1
        raise RuntimeError("connection refused")

    def fake_release(instance_id):
        calls["release"] += 1
        return {"ok": True}

    gc.create = fake_create
    gc.get_status = fake_get_status
    gc.release = fake_release
    asc._ssh_run = fake_ssh_run
    asc._http_get_json = fake_http_get_json

    try:
        raised = False
        try:
            asc.open_card(poll_interval_s=0.01, create_timeout_s=5,
                           health_timeout_s=0.03, ssh_attempts=1)
        except asc.OpenCardError:
            raised = True
        assert raised
        assert calls["http"] >= 1
        assert calls["release"] == 1
    finally:
        _restore()
    print("test_open_card_health_timeout_cleans_up: PASS")


def test_open_card_missing_ssh_access_cleans_up():
    calls = {"release": 0}

    def fake_create(from_snapshot_id=None, regions=None):
        return {"instanceID": "ins-no-ssh"}, "TW-03"

    def fake_get_status(instance_id):
        return {"status": "Running", "accesses": [
            {"protocol": "http", "listenPort": 8888, "url": "https://tw-03.access.glows.ai:1"},
        ]}

    def fake_release(instance_id):
        calls["release"] += 1
        return {"ok": True}

    gc.create = fake_create
    gc.get_status = fake_get_status
    gc.release = fake_release

    try:
        raised = False
        try:
            asc.open_card(poll_interval_s=0.01, create_timeout_s=5)
        except asc.OpenCardError:
            raised = True
        assert raised
        assert calls["release"] == 1
    finally:
        _restore()
    print("test_open_card_missing_ssh_access_cleans_up: PASS")


def test_close_card_confirms_removed():
    calls = {"release": 0}

    def fake_release(instance_id):
        calls["release"] += 1
        return {"ok": True}

    gc.release = fake_release
    gc.list_instances = lambda: []
    try:
        result = asc.close_card("ins-xyz")
        assert result == {"instance_id": "ins-xyz", "released": True, "still_listed": False}
        assert calls["release"] == 1
    finally:
        _restore()

    # release API 回應成功但 list 裡還查得到（刪除延遲一致性）——still_listed 要老實回報
    gc.release = fake_release
    gc.list_instances = lambda: [{"instanceID": "ins-xyz", "status": "Terminating"}]
    try:
        result = asc.close_card("ins-xyz")
        assert result["still_listed"] is True
    finally:
        _restore()
    print("test_close_card_confirms_removed: PASS")


def test_list_cards_extracts_access_per_instance():
    def fake_list_instances():
        return [
            {"instanceID": "ins-1", "status": "Running", "regionName": "TW-03", "accesses": [
                {"protocol": "http", "listenPort": 8888, "url": "https://h1:1"},
                {"protocol": "ssh", "listenPort": 2, "url": "root@h1:2"},
            ]},
            {"instanceID": "ins-2", "status": "SchedQueued", "regionName": "TW-04", "accesses": []},
        ]

    gc.list_instances = fake_list_instances
    try:
        cards = asc.list_cards()
        assert len(cards) == 2
        assert cards[0]["instance_id"] == "ins-1"
        assert cards[0]["http_url"] == "https://h1:1"
        assert cards[0]["ssh_host"] == "h1"
        assert cards[0]["ssh_port"] == 2
        assert cards[1]["instance_id"] == "ins-2"
        assert cards[1]["http_url"] is None
    finally:
        _restore()
    print("test_list_cards_extracts_access_per_instance: PASS")


def test_parse_access_handles_multiple_shapes():
    shape_a = {"accesses": [
        {"protocol": "http", "listenPort": 8888, "url": "https://tw-03.access.glows.ai:1000?x=1"},
        {"protocol": "ssh", "listenPort": 2000, "url": "ssh://root@tw-03.access.glows.ai:2000"},
    ]}
    r = gc.parse_access(shape_a)
    assert r == {"http_url": "https://tw-03.access.glows.ai:1000",
                 "ssh_host": "tw-03.access.glows.ai", "ssh_port": 2000}

    shape_b = {"accesses": [
        {"innerPort": 8888, "url": "https://tw-04.access.glows.ai:3000"},
        {"innerPort": 22, "listenPort": 4000, "host": "tw-04.access.glows.ai"},
    ]}
    r2 = gc.parse_access(shape_b)
    assert r2 == {"http_url": "https://tw-04.access.glows.ai:3000",
                  "ssh_host": "tw-04.access.glows.ai", "ssh_port": 4000}

    empty = gc.parse_access({"accesses": []})
    assert empty == {"http_url": None, "ssh_host": None, "ssh_port": None}
    print("test_parse_access_handles_multiple_shapes: PASS")


def test_register_and_unregister_into_gateway_registry():
    registry = gwc.WorkerRegistry()
    card = {"instance_id": "ins-99", "http_url": "https://tw-03.access.glows.ai:5000", "region": "TW-03"}
    w = asc.register_card_into_registry(registry, card, slots=2)
    assert w.worker_id == "glows-ins-99"
    assert registry.get("glows-ins-99") is w
    assert w.url == card["http_url"]
    assert w.slots == 2
    assert w.kind == "glows"
    assert w.region == "TW-03"

    result = asc.unregister_card_from_registry(registry, "glows-ins-99")
    assert result == {"worker_id": "glows-ins-99", "unregistered": True}
    assert registry.get("glows-ins-99") is None
    print("test_register_and_unregister_into_gateway_registry: PASS")


def main():
    test_open_card_happy_path()
    test_open_card_create_timeout_cleans_up()
    test_open_card_ssh_failure_cleans_up()
    test_open_card_health_timeout_cleans_up()
    test_open_card_missing_ssh_access_cleans_up()
    test_close_card_confirms_removed()
    test_list_cards_extracts_access_per_instance()
    test_parse_access_handles_multiple_shapes()
    test_register_and_unregister_into_gateway_registry()
    print("GLOWS autoscale mock test: ALL PASS")


if __name__ == "__main__":
    main()
