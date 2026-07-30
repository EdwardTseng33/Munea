"""企業席次到期自動處理（2026-07-30 Edward「到期自動會轉會員身分」）。

守三件事：
  ① 合約到期的公司，旗下席次進 30 天緩衝期（不是當天斷）
  ② 緩衝期跑完 → 釋出席次，並且真的把會員資格收回（這段以前完全沒做）
  ③ 等待中的席次到了個人訂閱到期日 → 換企業接手

外加一條最容易被漏掉的：收回之後 **App 那條路** 要真的看到「免費」。
App 讀的是 billing_rows_to_store，它舊版直接讀 active_plan、不看狀態——
所以就算流水帳補了 free/expired，只要那條路沒改，手機上還是付費會員。
"""
import importlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, __file__.rsplit("engine", 1)[0] + "engine")

import enterprise_seats  # noqa: E402
import supabase_adapter  # noqa: E402


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)
PAST = _iso(NOW - timedelta(days=1))
FUTURE = _iso(NOW + timedelta(days=10))


@pytest.fixture
def fake_world(monkeypatch):
    """用假的席次／公司資料跑巡檢，不碰真資料庫。"""
    state = {"clients": [], "seats": [], "transitions": [], "revocations": [], "grants": []}

    monkeypatch.setattr(enterprise_seats, "list_clients", lambda *a, **k: state["clients"])
    monkeypatch.setattr(enterprise_seats, "list_seats", lambda *a, **k: state["seats"])

    def fake_transition(seat_id, to_status, **kwargs):
        state["transitions"].append({"seatId": seat_id, "to": to_status, **kwargs})
        for seat in state["seats"]:
            if seat.get("id") == seat_id:
                seat["status"] = to_status
                return seat
        return {"id": seat_id, "status": to_status}

    def fake_revoke(seat_id, **kwargs):
        state["revocations"].append({"seatId": seat_id, **kwargs})
        return {"revoked": True, "seat": {"id": seat_id}}

    def fake_grant(seat_id, **kwargs):
        state["grants"].append({"seatId": seat_id, **kwargs})
        return {"granted": True, "waiting": False}

    monkeypatch.setattr(enterprise_seats, "transition_seat", fake_transition)
    monkeypatch.setattr(enterprise_seats, "revoke_enterprise_membership", fake_revoke)
    monkeypatch.setattr(enterprise_seats, "grant_enterprise_membership", fake_grant)
    return state


def _client(cid="c1", name="測試長照中心", contract_end=None):
    return {"id": cid, "name": name, "planTier": "pro", "contractEnd": contract_end}


def _seat(sid, status, **extra):
    seat = {"id": sid, "enterpriseClientId": "c1", "accountId": f"acct-{sid}", "status": status}
    seat.update(extra)
    return seat


# ── ① 合約到期 → 進緩衝期 ──────────────────────────────────────────────

def test_contract_ended_moves_active_seat_to_grace(fake_world):
    fake_world["clients"] = [_client(contract_end=PAST)]
    fake_world["seats"] = [_seat("s1", "active")]

    result = enterprise_seats.sweep_seat_lifecycle(dry_run=False, now=_iso(NOW))

    assert result["summary"]["toGrace"] == 1
    assert fake_world["transitions"] == [
        {"seatId": "s1", "to": "grace", "actor": "scheduler", "reason": "contract_ended"}
    ]


def test_contract_still_running_leaves_seat_alone(fake_world):
    fake_world["clients"] = [_client(contract_end=FUTURE)]
    fake_world["seats"] = [_seat("s1", "active")]

    result = enterprise_seats.sweep_seat_lifecycle(dry_run=False, now=_iso(NOW))

    assert result["summary"]["toGrace"] == 0
    assert fake_world["transitions"] == []


def test_missing_contract_end_is_treated_as_not_expired(fake_world):
    """合約到期日沒填就當作還沒到期——寧可晚收回，不要誤收長輩的付費資格。"""
    fake_world["clients"] = [_client(contract_end=None)]
    fake_world["seats"] = [_seat("s1", "active")]

    result = enterprise_seats.sweep_seat_lifecycle(dry_run=False, now=_iso(NOW))

    assert result["summary"]["toGrace"] == 0
    assert fake_world["transitions"] == []


# ── ② 緩衝期跑完 → 釋出 + 收回會員資格 ────────────────────────────────

def test_grace_ended_releases_seat_and_revokes_membership(fake_world):
    fake_world["clients"] = [_client()]
    fake_world["seats"] = [_seat("s1", "grace", graceUntil=PAST)]

    result = enterprise_seats.sweep_seat_lifecycle(dry_run=False, now=_iso(NOW))

    assert result["summary"]["toReleased"] == 1
    assert result["toReleased"][0]["membershipRevoked"] is True
    assert [r["seatId"] for r in fake_world["revocations"]] == ["s1"]
    assert fake_world["transitions"][0]["to"] == "released"
    assert fake_world["transitions"][0]["released_reason"] == "contract_end"


def test_membership_is_revoked_before_seat_is_released(fake_world):
    """順序不能反。席次一旦標成已釋出就不能再轉狀態，
    若先釋出、收回那步才失敗，這顆席次會永遠卡在「已釋出但人還是付費會員」。"""
    order = []
    fake_world["clients"] = [_client()]
    fake_world["seats"] = [_seat("s1", "grace", graceUntil=PAST)]

    def track_revoke(seat_id, **kwargs):
        order.append("revoke")
        return {"revoked": True}

    def track_transition(seat_id, to_status, **kwargs):
        order.append(f"transition:{to_status}")
        return {"id": seat_id, "status": to_status}

    enterprise_seats.revoke_enterprise_membership = track_revoke
    enterprise_seats.transition_seat = track_transition
    enterprise_seats.sweep_seat_lifecycle(dry_run=False, now=_iso(NOW))

    assert order == ["revoke", "transition:released"]


def test_grace_still_running_leaves_seat_alone(fake_world):
    fake_world["clients"] = [_client()]
    fake_world["seats"] = [_seat("s1", "grace", graceUntil=FUTURE)]

    result = enterprise_seats.sweep_seat_lifecycle(dry_run=False, now=_iso(NOW))

    assert result["summary"]["toReleased"] == 0
    assert fake_world["revocations"] == []


# ── ③ 等待中的席次 → 企業接手 ────────────────────────────────────────

def test_waiting_seat_is_handed_over_when_individual_plan_expires(fake_world):
    fake_world["clients"] = [_client()]
    fake_world["seats"] = [_seat("s1", "waiting", waitingUntil=PAST)]

    result = enterprise_seats.sweep_seat_lifecycle(dry_run=False, now=_iso(NOW))

    assert result["summary"]["handedOver"] == 1
    assert result["handedOver"][0]["granted"] is True
    assert [g["seatId"] for g in fake_world["grants"]] == ["s1"]


# ── 乾跑：只出報告、不動資料 ──────────────────────────────────────────

def test_dry_run_reports_without_touching_anything(fake_world):
    fake_world["clients"] = [_client(contract_end=PAST)]
    fake_world["seats"] = [
        _seat("s1", "active"),
        _seat("s2", "grace", graceUntil=PAST),
        _seat("s3", "waiting", waitingUntil=PAST),
    ]

    result = enterprise_seats.sweep_seat_lifecycle(dry_run=True, now=_iso(NOW))

    assert result["dryRun"] is True
    assert result["summary"] == {"toGrace": 1, "toReleased": 1, "handedOver": 1, "errors": 0}
    assert fake_world["transitions"] == []
    assert fake_world["revocations"] == []
    assert fake_world["grants"] == []


def test_one_broken_seat_does_not_stop_the_rest(fake_world):
    """單顆席次出錯不能擋住整輪巡檢，錯誤要回報出來、不是默默吞掉。"""
    fake_world["clients"] = [_client()]
    fake_world["seats"] = [
        _seat("bad", "grace", graceUntil=PAST),
        _seat("good", "grace", graceUntil=PAST),
    ]

    def flaky_revoke(seat_id, **kwargs):
        if seat_id == "bad":
            raise ValueError("boom")
        return {"revoked": True}

    enterprise_seats.revoke_enterprise_membership = flaky_revoke
    result = enterprise_seats.sweep_seat_lifecycle(dry_run=False, now=_iso(NOW))

    assert result["summary"]["errors"] == 1
    assert result["errors"][0]["seatId"] == "bad"
    assert result["summary"]["toReleased"] == 1  # good 那顆還是處理掉了


# ── 收回之後，App 那條路要真的看到免費 ────────────────────────────────

class _Adapter(supabase_adapter.SupabaseAdapter):
    def __init__(self):  # noqa: D107 - 只要 billing_rows_to_store，不需要真連線
        self.account_id = "acct-1"


@pytest.mark.parametrize("status,stored_plan,expected", [
    ("active", "pro", "pro"),
    ("trial", "plus", "plus"),
    ("grace_period", "pro", "pro"),
    ("expired", "free", "free"),
    # 關鍵三條：狀態已失效、方案欄還掛著付費 → 一律當免費。
    # 正式庫現在就有 21 筆這種紀錄（2026-07-30 查證）。
    ("expired", "pro", "free"),
    ("inactive", "pro", "free"),
    ("inactive", "premium", "free"),
])
def test_expired_subscription_reads_as_free_for_the_app(status, stored_plan, expected):
    store = _Adapter().billing_rows_to_store({"status": status, "active_plan": stored_plan})
    assert store["activePlan"] == expected
    # 原始狀態不能被改寫掉——訂閱到期日那塊畫面還要靠它判斷要不要顯示。
    assert store["subscription"]["status"] == status


def test_revocation_row_shape_is_what_both_readers_need():
    """收回時補的那筆流水帳，欄位要湊得出「免費 + 已過期 + 指得出是哪顆席次」。
    provider=enterprise 的紀錄少了出處，資料庫層的規則會直接擋下來。"""
    src = open(enterprise_seats.__file__, encoding="utf-8").read()
    body = src.split("def revoke_enterprise_membership", 1)[1].split("\ndef ", 1)[0]
    for needed in ('"status": "expired"', '"active_plan": "free"', '"grant_ref": seat["id"]'):
        assert needed in body, f"收回那筆流水帳少了 {needed}"


def test_module_still_imports_cleanly():
    importlib.reload(enterprise_seats)
