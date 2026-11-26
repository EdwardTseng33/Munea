#!/usr/bin/env python3
"""家人圈共用分鐘＋每日／每週免費額度（2026-11-20 拍板；SQL 對應 034）。

跑法：python engine/test_family_shared_minutes.py
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "family-share-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import credit_allowance as ca
import server

UTC = timezone.utc
FUTURE = "2099-01-01T00:00:00Z"
PAID = {"activePlan": "plus", "subscription": {"status": "active", "expiresAt": FUTURE}}
EXPIRED = {"activePlan": "plus", "subscription": {"status": "expired", "expiresAt": "2026-01-01T00:00:00Z"}}


def utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def store_with(*wallets, transactions=None, account_id="acct"):
    return server.normalize_credits_store({
        "accountId": account_id,
        "wallets": list(wallets),
        "transactions": list(transactions or []),
    })


def monthly(balance, wallet_id="wallet_month", expires=FUTURE, period="2026-11-01T00:00Z/2099-01-01T00:00Z"):
    return {"id": wallet_id, "type": "included_monthly", "period": period, "balance": balance,
            "expiresAt": expires, "status": "active"}


def purchased(balance, wallet_id="wallet_purchased"):
    return {"id": wallet_id, "type": "purchased", "period": None, "balance": balance, "status": "active"}


class DisabledBackend:
    def enabled(self):
        return False


class FreeOnceTests(unittest.TestCase):
    """2026-11-26：免費＝註冊送一次 5 分鐘，沒有天數概念。"""

    NOW = utc("2026-11-26T05:00:00Z")

    def test_window_is_free_once_five_never_expires(self):
        self.assertEqual(ca.free_once_window(), {"mode": "free_once", "period": "free-once", "amount": 5.0, "expiresAt": None})

    def test_minutes_configurable_by_env(self):
        self.assertEqual(ca.free_once_minutes({"MUNEA_FREE_SIGNUP_MINUTES": "3"}), 3)
        self.assertEqual(ca.free_once_minutes({"MUNEA_FREE_SIGNUP_MINUTES": "x"}), 5)
        self.assertEqual(ca.free_once_minutes({}), 5)

    def test_received_by_new_wallet_or_legacy_signup(self):
        self.assertFalse(ca.free_once_received(store_with(), "a"))
        self.assertTrue(ca.free_once_received(store_with(
            {"id": "f", "type": "free_allowance", "period": "free-once", "balance": 0, "status": "active"}), "a"))
        legacy = store_with(purchased(2), transactions=[
            {"type": "grant", "walletId": "wallet_purchased", "amount": 5, "idempotencyKey": "free-signup-trial:a"}])
        self.assertTrue(ca.free_once_received(legacy, "a"))
        self.assertFalse(ca.free_once_received(legacy, "b"), "別的帳號的鍵不算")

    def test_daily_allowance_alone_does_not_count_as_received(self):
        daily = store_with({"id": "d", "type": "free_allowance", "period": "free-daily:2026-11-21", "balance": 0,
                            "status": "active"}, transactions=[
            {"type": "grant", "walletId": "d", "amount": 10, "idempotencyKey": "free-allowance:a:free-daily:2026-11-21"}])
        self.assertFalse(ca.free_once_received(daily, "a"))

    def test_remaining_caps_legacy_purchased_at_five(self):
        legacy = store_with(purchased(30), transactions=[
            {"type": "grant", "walletId": "wallet_purchased", "amount": 5, "reason": "free_signup_voice_avatar_trial"}])
        self.assertEqual(ca.free_once_remaining(legacy, self.NOW), 5)

    def test_allowance_block_shapes(self):
        once = store_with({"id": "f", "type": "free_allowance", "period": "free-once", "balance": 3, "status": "active",
                           "metadata": {"grant": 5}})
        self.assertEqual(ca.allowance_block(once, self.NOW), {"mode": "free_once", "grant": 5, "remaining": 3})
        self.assertEqual(ca.allowance_block(store_with(), self.NOW), {"mode": "free_once", "grant": 0, "remaining": 0})
        self.assertEqual(ca.allowance_block(once, self.NOW, paid_plan="plus", plan_resets_at="2026-12-20T00:00:00Z"),
                         {"mode": "plan", "plan": "plus", "resetsAt": "2026-12-20T00:00:00Z"})

    def test_close_periodic_wallets(self):
        store = store_with(
            {"id": "d", "type": "free_allowance", "period": "free-daily:2026-11-26", "balance": 4,
             "expiresAt": "2026-11-26T16:00:00Z", "status": "active"},
            {"id": "w", "type": "free_allowance", "period": "free-weekly:2026-11-23", "balance": 10,
             "expiresAt": "2026-11-30T16:00:00Z", "status": "active"},
            {"id": "f", "type": "free_allowance", "period": "free-once", "balance": 5, "status": "active"},
        )
        self.assertEqual(ca.close_periodic_free_wallets(store, self.NOW), 2)
        self.assertEqual(ca.close_periodic_free_wallets(store, self.NOW), 0, "重跑不再動")
        self.assertEqual(server.credit_wallet_summary(store)["freeAllowance"], 5, "只剩一次性那 5 分鐘")

    def test_paid_account_gets_no_free_wallet(self):
        store = store_with()
        window, created = server.ensure_free_allowance_in_store(store, account_id="a", created_at=None, paid_plan="pro")
        self.assertIsNone(window)
        self.assertFalse(created)


class SpendOrderTests(unittest.TestCase):
    NOW = utc("2026-11-20T05:00:00Z")

    def free(self, balance):
        return {"id": "free_today", "type": "free_allowance", "period": "free-daily:2026-11-20", "balance": balance,
                "expiresAt": "2026-11-20T16:00:00Z", "status": "active"}

    def test_member_uses_own_free_allowance_before_owner(self):
        own = store_with(self.free(2), account_id="mom")
        owner = store_with(monthly(100), account_id="kid")
        plan = ca.plan_spend(own, 1, self.NOW, owner_store=owner, caller_account_id="mom", owner_account_id="kid")
        self.assertEqual([(w["id"], take) for _, w, take in plan], [("free_today", 1)])

    def test_member_spills_into_owner_then_own_purchased(self):
        own = store_with(self.free(1), purchased(5), account_id="mom")
        owner = store_with(monthly(2), account_id="kid")
        plan = ca.plan_spend(own, 4, self.NOW, owner_store=owner, caller_account_id="mom", owner_account_id="kid")
        self.assertEqual([(w["id"], take) for _, w, take in plan],
                         [("free_today", 1), ("wallet_month", 2), ("wallet_purchased", 1)])
        self.assertIs(plan[1][0], owner)

    def test_owner_free_wallet_is_not_shared(self):
        own = store_with(account_id="mom")
        owner = store_with(self.free(10), account_id="kid")
        self.assertIsNone(ca.plan_spend(own, 1, self.NOW, owner_store=owner, caller_account_id="mom", owner_account_id="kid"))

    def test_without_owner_order_is_free_then_monthly_then_purchased(self):
        own = store_with(purchased(5), monthly(5), self.free(1))
        plan = ca.plan_spend(own, 3, self.NOW)
        self.assertEqual([w["id"] for _, w, _ in plan], ["free_today", "wallet_month"])

    def test_expired_free_wallet_is_skipped(self):
        own = store_with(self.free(10))
        self.assertIsNone(ca.plan_spend(own, 1, utc("2026-11-20T16:00:01Z")))


def share_state(owner_billing=PAID, owner_wallets=None, owner_transactions=None, memberships=None):
    return {
        "accounts": {
            "acct-kid": {
                "billing": owner_billing,
                "personId": "p-kid",
                "credits": {"accountId": "acct-kid", "wallets": owner_wallets if owner_wallets is not None else [monthly(100)],
                            "transactions": owner_transactions or []},
            },
        },
        "memberships": memberships if memberships is not None else [
            {"familyGroupId": "fg-kid", "ownerAccountId": "acct-kid", "memberAccountId": "acct-mom",
             "personId": "p-mom", "createdAt": "2026-11-01T00:00:00Z"},
        ],
    }


@patch.object(server, "FAMILY_SHARED_MINUTES", True)
class JsonFamilyShareTests(unittest.TestCase):
    """JSON 後備模式端到端：/credits/consume 與 /credits/balance（共用開著時的舊行為；2026-11-26 起預設關）。"""

    def setUp(self):
        self.own = server.default_credits_store()
        self.own["wallets"] = []
        self.state = share_state()
        self.saved_owner = {}
        self.profile = {"account": {"id": "acct-mom", "createdAt": "2026-07-01T00:00:00Z"},
                        "primaryCareRecipientId": "p-mom", "familyGroup": {"id": "fg-mom"}}
        self.billing = server.normalize_billing_store({})
        self.circle = {"fg-kid": {"circle": {"value": [
            {"name": "媽媽", "personId": "p-mom"}, {"name": "小明", "personId": "p-kid"},
            {"name": "aunt@example.com", "personId": "p-aunt"},
        ]}}}

    def patches(self):
        def load():
            return server.normalize_credits_store(self.own)

        def save(updated):
            self.own.clear()
            self.own.update(server.normalize_credits_store(updated))
            return server.normalize_credits_store(self.own)

        def save_owner(account_id, credits):
            normalized = server.normalize_credits_store(credits)
            self.state["accounts"][account_id]["credits"] = normalized
            self.saved_owner[account_id] = normalized
            return normalized

        return [
            patch.object(server, "data_backend", return_value=DisabledBackend()),
            patch.object(server, "data_backend_status", return_value={"provider": "json"}),
            patch.object(server, "ensure_current_monthly_allowance", return_value=None),
            patch.object(server, "load_credits_store", side_effect=load),
            patch.object(server, "save_credits_store", side_effect=save),
            patch.object(server, "load_billing_store", side_effect=lambda: self.billing),
            patch.object(server, "load_app_profile_store", side_effect=lambda: self.profile),
            patch.object(server, "json_credit_share_state", side_effect=lambda: self.state),
            patch.object(server, "save_json_credit_share_account", side_effect=save_owner),
            patch.object(server, "_family_state_json_all", side_effect=lambda: self.circle),
        ]

    def run_patched(self, fn):
        ps = self.patches()
        for p in ps:
            p.start()
        try:
            return fn()
        finally:
            for p in reversed(ps):
                p.stop()

    def owner_credits(self):
        return self.state["accounts"]["acct-kid"]["credits"]

    def test_member_first_spends_own_free_then_owner(self):
        def run():
            results = [server.credits_consume_response({"amount": 1, "idempotencyKey": f"call-1:minute:{i}"})
                       for i in range(1, 13)]
            return results
        results = self.run_patched(run)
        self.assertTrue(all(r["ok"] for r in results))
        own_free_spent = sum(tx["amount"] for tx in self.own["transactions"] if tx["type"] == "consume")
        self.assertEqual(own_free_spent, 5, "自己的一次性 5 分鐘先用完")
        owner_tx = [tx for tx in self.owner_credits()["transactions"] if tx["type"] == "consume"]
        self.assertEqual(sum(tx["amount"] for tx in owner_tx), 7, "超過的才扣圈主")
        self.assertTrue(all(tx["personId"] == "p-mom" for tx in owner_tx), "圈主帳上記來電者是誰")
        self.assertEqual(self.owner_credits()["wallets"][0]["balance"], 93)

    def test_owner_without_paid_plan_member_pays_self(self):
        self.state = share_state(owner_billing=EXPIRED)
        self.own["wallets"] = [purchased(3)]

        def run():
            return [server.credits_consume_response({"amount": 1, "idempotencyKey": f"c:{i}"}) for i in range(14)]
        results = self.run_patched(run)
        self.assertEqual(sum(1 for r in results if r["ok"]), 8, "一次性 5 免費＋自己 3 點，圈主沒付費不幫付")
        self.assertEqual(results[-1]["error"]["code"], "insufficient_credits")
        self.assertFalse(any(tx["type"] == "consume" for tx in self.owner_credits()["transactions"]))

    def test_owner_calls_use_own_wallet(self):
        self.profile = {"account": {"id": "acct-kid", "createdAt": "2026-07-01T00:00:00Z"},
                        "primaryCareRecipientId": "p-kid", "familyGroup": {"id": "fg-kid"}}
        self.billing = server.normalize_billing_store(PAID)
        self.own["wallets"] = [monthly(100)]
        result = self.run_patched(lambda: server.credits_consume_response({"amount": 1, "idempotencyKey": "k"}))
        self.assertTrue(result["ok"])
        self.assertEqual(server.credit_wallet_summary(self.own)["includedMonthly"], 99)
        self.assertFalse(any(w["type"] == "free_allowance" for w in self.own["wallets"]), "付費的人不發免費額度")
        self.assertEqual(self.saved_owner, {})

    def test_member_with_own_plan_is_not_covered(self):
        self.billing = server.normalize_billing_store(PAID)
        self.own["wallets"] = [monthly(5)]
        result = self.run_patched(lambda: server.credits_consume_response({"amount": 1, "idempotencyKey": "k"}))
        self.assertTrue(result["ok"])
        self.assertEqual(server.credit_wallet_summary(self.own)["includedMonthly"], 4)
        self.assertFalse(any(tx["type"] == "consume" for tx in self.owner_credits()["transactions"]))

    def test_member_balance_includes_owner_pool_and_shows_only_own_usage(self):
        self.state = share_state(owner_transactions=[
            {"type": "grant", "walletId": "wallet_month", "amount": 100, "createdAt": "2026-11-01T00:00:00Z"},
            {"type": "consume", "walletId": "wallet_month", "walletType": "included_monthly", "amount": 22,
             "personId": "p-mom", "createdAt": "2026-11-10T00:00:00Z"},
            {"type": "consume", "walletId": "wallet_month", "walletType": "included_monthly", "amount": 14,
             "personId": "p-kid", "createdAt": "2026-11-11T00:00:00Z"},
        ], owner_wallets=[monthly(64, expires="2026-11-30T16:00:00Z")])
        result = self.run_patched(lambda: server.credits_balance_response({}))
        summary = result["walletSummary"]
        self.assertEqual(summary["freeAllowance"], 5)
        self.assertEqual(summary["familyShared"], 64)
        self.assertEqual(summary["total"], 69, "App 用 total 判斷能不能撥，要含圈主的分鐘")
        self.assertEqual(result["allowance"], {"mode": "free_once", "grant": 5, "remaining": 5})
        share = result["familyShare"]
        self.assertEqual(share["shared"], True)
        self.assertEqual(share["role"], "member")
        self.assertEqual(share["plan"], "plus")
        self.assertEqual((share["monthGrant"], share["monthRemaining"]), (100, 64))
        self.assertEqual(share["renewsAt"], "2026-12-01", "台灣時間的日期")
        self.assertEqual(share["usageByPerson"], [{"personId": "p-mom", "name": "媽媽", "minutes": 22, "isMe": True}],
                         "成員只看得到自己那列")
        self.assertEqual(set(share), {"shared", "role", "plan", "monthGrant", "monthRemaining", "renewsAt", "usageByPerson"})

    def test_owner_sees_everyone_with_circle_names_never_email(self):
        self.profile = {"account": {"id": "acct-kid", "createdAt": "2026-07-01T00:00:00Z"},
                        "primaryCareRecipientId": "p-kid", "familyGroup": {"id": "fg-kid"}}
        self.billing = server.normalize_billing_store(PAID)
        self.own["wallets"] = [monthly(60, expires="2026-11-30T16:00:00Z")]
        self.own["transactions"] = [
            {"type": "consume", "walletId": "wallet_month", "walletType": "included_monthly", "amount": 22,
             "personId": "p-mom", "createdAt": "2026-11-10T00:00:00Z"},
            {"type": "consume", "walletId": "wallet_month", "walletType": "included_monthly", "amount": 10,
             "createdAt": "2026-11-11T00:00:00Z"},  # 圈主自己（舊交易沒有 personId）
            {"type": "consume", "walletId": "wallet_month", "walletType": "included_monthly", "amount": 8,
             "personId": "p-aunt", "createdAt": "2026-11-12T00:00:00Z"},
            {"type": "consume", "walletId": "wallet_month", "walletType": "included_monthly", "amount": 50,
             "personId": "p-mom", "createdAt": "2026-10-20T00:00:00Z"},  # 上一期，不算
        ]
        result = self.run_patched(lambda: server.credits_balance_response({}))
        share = result["familyShare"]
        self.assertEqual(share["role"], "owner")
        self.assertEqual(share["usageByPerson"], [
            {"personId": "p-mom", "name": "媽媽", "minutes": 22, "isMe": False},
            {"personId": "p-kid", "name": "小明", "minutes": 10, "isMe": True},
            {"personId": "p-aunt", "name": "", "minutes": 8, "isMe": False},
        ])
        self.assertEqual(result["allowance"]["mode"], "plan")
        self.assertNotIn("familyShared", result["walletSummary"], "圈主自己的錢包本來就在 total 裡")

    def test_new_member_gets_free_once_from_platform(self):
        self.profile["account"]["createdAt"] = server.utc_now()
        result = self.run_patched(lambda: server.credits_balance_response({}))
        self.assertEqual(result["allowance"], {"mode": "free_once", "grant": 5, "remaining": 5})
        self.assertEqual(result["familyShare"]["role"], "member")

    def test_free_account_not_in_any_circle_has_no_family_share(self):
        self.state = share_state(memberships=[])
        result = self.run_patched(lambda: server.credits_balance_response({}))
        self.assertIsNone(result["familyShare"])
        self.assertEqual(result["walletSummary"]["total"], 5)


@patch.object(server, "FAMILY_SHARED_MINUTES", True)
class SupabaseStatusTests(unittest.TestCase):
    """Supabase 模式：狀態來自 munea_credit_share_status，名字由後端從家人圈顯示名補（共用開著時）。"""

    class Backend:
        def __init__(self, statuses, circle=None):
            self.statuses = list(statuses)
            self.calls = 0
            self.circle = circle or []

        def enabled(self):
            return True

        def load_credit_share_status(self):
            self.calls += 1
            return self.statuses[min(self.calls, len(self.statuses)) - 1]

        def load_family_circle_unscoped(self, family_group_id):
            return self.circle

    def sql_status(self, role, remaining=64, usage=None):
        return {
            "allowance": {"mode": "free_daily", "trialDay": 3, "trialDays": 7, "todayGrant": 10, "todayRemaining": 8,
                          "weekGrant": None, "weekRemaining": None, "resetsAt": "2026-11-20T16:00:00+00:00"},
            "familyShare": {"shared": True, "role": role, "plan": "pro", "familyGroupId": "fg", "ownerAccountId": "o",
                            "ownerPersonId": "p-kid", "viewerPersonId": "p-mom", "monthGrant": 200,
                            "monthRemaining": remaining, "renewsAt": "2026-12-01",
                            "usage": usage if usage is not None else [{"personId": "p-mom", "minutes": 22}]},
            "sharedSpendable": 64 if role == "member" else 0,
        }

    def run_balance(self, backend, ensure_owner=None):
        own = server.normalize_credits_store({"wallets": [
            {"id": "w-free", "type": "free_allowance", "period": "free-daily:2026-11-20", "balance": 8,
             "expiresAt": FUTURE, "status": "active", "metadata": {"grant": 10}},
        ]})
        with patch.object(server, "data_backend", return_value=backend), \
             patch.object(server, "data_backend_status", return_value={"provider": "supabase"}), \
             patch.object(server, "ensure_current_monthly_allowance", return_value=None), \
             patch.object(server, "load_credits_store", return_value=own), \
             patch.object(server, "ensure_owner_monthly_allowance", side_effect=ensure_owner or (lambda share: False)):
            return server.credits_balance_response({})

    def test_member_total_and_names(self):
        backend = self.Backend([self.sql_status("member")], circle=[{"name": "媽媽", "personId": "p-mom"}])
        result = self.run_balance(backend)
        self.assertEqual(result["walletSummary"]["freeAllowance"], 8)
        self.assertEqual(result["walletSummary"]["total"], 72)
        self.assertEqual(result["allowance"]["todayRemaining"], 8)
        self.assertEqual(result["familyShare"]["usageByPerson"],
                         [{"personId": "p-mom", "name": "媽媽", "minutes": 22, "isMe": True}])
        self.assertNotIn("ownerAccountId", result["familyShare"], "不把圈主帳號編號給 App")

    def test_member_view_drops_other_rows_even_if_sql_returned_them(self):
        status = self.sql_status("member", usage=[{"personId": "p-mom", "minutes": 22}, {"personId": "p-kid", "minutes": 9}])
        result = self.run_balance(self.Backend([status]))
        self.assertEqual([r["personId"] for r in result["familyShare"]["usageByPerson"]], ["p-mom"])

    def test_missing_owner_month_wallet_is_minted_then_reloaded(self):
        seen = []
        backend = self.Backend([self.sql_status("member", remaining=None), self.sql_status("member", remaining=100)])
        result = self.run_balance(backend, ensure_owner=lambda share: seen.append(share["ownerAccountId"]) or True)
        self.assertEqual(seen, ["o"])
        self.assertEqual(backend.calls, 2)
        self.assertEqual(result["familyShare"]["monthRemaining"], 100)

    def test_status_unavailable_before_034_keeps_old_response(self):
        class Broken(self.Backend):
            def load_credit_share_status(self):
                raise RuntimeError("function munea_credit_share_status does not exist")
        result = self.run_balance(Broken([]))
        self.assertTrue(result["ok"])
        self.assertIsNone(result["familyShare"])
        self.assertIsNone(result["allowance"])
        self.assertEqual(result["walletSummary"]["total"], 8)


class EntitlementsCapabilityTests(unittest.TestCase):
    def test_capability_flag_for_frontend(self):
        with patch.object(server, "load_billing_store", return_value=server.normalize_billing_store({})):
            response = server.entitlements_response({})
        self.assertIs(response["capabilities"]["familySharedMinutes"], False, "2026-11-26 起分鐘各帳號各扣")
        self.assertIs(response["capabilities"]["freeOnce"], True, "App 讀 allowance.mode=free_once")


class PerAccountMinutesTests(unittest.TestCase):
    """2026-11-26 Edward：「每個帳號各扣各的分鐘 當然要」——預設（FAMILY_SHARED_MINUTES=False）的行為。"""

    def setUp(self):
        JsonFamilyShareTests.setUp(self)

    patches = JsonFamilyShareTests.patches
    run_patched = JsonFamilyShareTests.run_patched
    owner_credits = JsonFamilyShareTests.owner_credits

    def test_switch_is_off_by_default(self):
        self.assertIs(server.FAMILY_SHARED_MINUTES, False)

    def test_member_in_paid_circle_only_spends_own_minutes(self):
        def run():
            return [server.credits_consume_response({"amount": 1, "idempotencyKey": f"call-1:minute:{i}"})
                    for i in range(1, 13)]
        results = self.run_patched(run)
        self.assertEqual(sum(1 for r in results if r["ok"]), 5, "只有自己那一次性 5 分鐘")
        self.assertEqual(results[-1]["error"]["code"], "insufficient_credits")
        self.assertFalse(any(tx["type"] == "consume" for tx in self.owner_credits()["transactions"]), "不扣圈主")
        self.assertEqual(self.owner_credits()["wallets"][0]["balance"], 100)
        self.assertEqual(self.saved_owner, {})

    def test_member_balance_has_no_family_share_and_total_is_own(self):
        result = self.run_patched(lambda: server.credits_balance_response({}))
        self.assertIsNone(result["familyShare"])
        self.assertNotIn("familyShared", result["walletSummary"])
        self.assertEqual(result["walletSummary"]["total"], 5)
        self.assertEqual(result["allowance"], {"mode": "free_once", "grant": 5, "remaining": 5})

    def test_balance_after_free_used_up_is_zero_not_refilled(self):
        self.run_patched(lambda: [server.credits_consume_response({"amount": 1, "idempotencyKey": f"k{i}"}) for i in range(5)])
        result = self.run_patched(lambda: server.credits_balance_response({}))
        self.assertEqual(result["allowance"], {"mode": "free_once", "grant": 5, "remaining": 0})
        self.assertEqual(result["walletSummary"]["total"], 0)
        self.assertIsNone(result["familyShare"])

    def test_owner_spends_own_monthly_and_sees_plan_without_share(self):
        self.profile = {"account": {"id": "acct-kid", "createdAt": "2026-07-01T00:00:00Z"},
                        "primaryCareRecipientId": "p-kid", "familyGroup": {"id": "fg-kid"}}
        self.billing = server.normalize_billing_store(PAID)
        self.own["wallets"] = [monthly(100)]
        consumed = self.run_patched(lambda: server.credits_consume_response({"amount": 1, "idempotencyKey": "k"}))
        self.assertTrue(consumed["ok"])
        self.assertEqual(server.credit_wallet_summary(self.own)["includedMonthly"], 99)
        result = self.run_patched(lambda: server.credits_balance_response({}))
        self.assertIsNone(result["familyShare"])
        self.assertEqual(result["allowance"]["mode"], "plan")

    def test_supabase_status_from_db_before_035_is_not_passed_through(self):
        backend = SupabaseStatusTests.Backend([SupabaseStatusTests.sql_status(None, "member")])
        result = SupabaseStatusTests.run_balance(None, backend)
        self.assertIsNone(result["familyShare"], "035 還沒套用時，後端也不轉給 App")
        self.assertNotIn("familyShared", result["walletSummary"])
        self.assertEqual(result["walletSummary"]["total"], 8, "只有自己的 8 分鐘，不加圈主的 64")
        self.assertEqual(result["allowance"]["todayRemaining"], 8)

    def test_supabase_free_once_old_app_total_includes_one_time_minutes(self):
        """商店上的舊 App 不認得 free_once，會用 walletSummary.total 判斷能不能撥——total 要含一次性免費的剩餘。"""
        class Backend(SupabaseStatusTests.Backend):
            pass
        status = {"allowance": {"mode": "free_once", "grant": 5, "remaining": 3}, "familyShare": None, "sharedSpendable": 0}
        own = server.normalize_credits_store({"wallets": [
            {"id": "w-once", "type": "free_allowance", "period": "free-once", "balance": 3, "status": "active",
             "metadata": {"grant": 5}},
        ]})
        with patch.object(server, "data_backend", return_value=Backend([status])),              patch.object(server, "data_backend_status", return_value={"provider": "supabase"}),              patch.object(server, "ensure_current_monthly_allowance", return_value=None),              patch.object(server, "load_credits_store", return_value=own):
            result = server.credits_balance_response({})
        self.assertEqual(result["allowance"], {"mode": "free_once", "grant": 5, "remaining": 3})
        self.assertEqual((result["walletSummary"]["freeAllowance"], result["walletSummary"]["total"]), (3, 3))
        own["wallets"][0]["balance"] = 0
        with patch.object(server, "data_backend", return_value=Backend([{**status, "allowance": {**status["allowance"], "remaining": 0}}])),              patch.object(server, "data_backend_status", return_value={"provider": "supabase"}),              patch.object(server, "ensure_current_monthly_allowance", return_value=None),              patch.object(server, "load_credits_store", return_value=own):
            empty = server.credits_balance_response({})
        self.assertEqual(empty["walletSummary"]["total"], 0, "用完了舊 App 也撥不出去")


class AdapterWalletTypeTests(unittest.TestCase):
    def test_free_wallet_is_not_saved_as_purchased(self):
        import supabase_adapter
        adapter = supabase_adapter.SupabaseAdapter(env={}, identity={"accountId": "a", "personId": "p"})
        row = adapter.credit_wallet_to_row({"type": "free_allowance", "period": "free-daily:2026-11-20", "balance": 10})
        self.assertEqual(row["wallet_type"], "free_allowance")
        self.assertIsNone(row["person_id"], "免費錢包是帳號層級")


if __name__ == "__main__":
    unittest.main()
