#!/usr/bin/env python3
"""
企業席次三條鐵律 + 匯入五分類的單元測試（需求單 2.5、5.1、5A、3.2）。

刻意不 import server（避免拉進 GEMINI/google.genai 等重依賴）——enterprise_seats.py
本身是 stdlib-only（跟 supabase_adapter.py 同一個原則），直接測。

Supabase 在測試環境沒設定（enabled()==False），CRUD 走本地 JSON 檔備援；
三條鐵律需要的「請款單狀態」「個人現有訂閱」「grant_ref 是否已授予過」在停用模式下
沒有本地備援（設計上就是安全預設＝視為未付款／無個人衝突），所以用 FakeBackend
只覆寫這三個查詢方法，其餘 CRUD 仍走真本地 JSON 檔（貼近真實資料流）。
"""
import json
import os
import sys
import shutil
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

import enterprise_seats as es
import enterprise_billing as eb


class FakeBackend:
    """最小可控假後端：enabled()=False 讓沒被覆寫的方法自然回 None／落回本地 JSON 備援；
    三個鐵律相關查詢（請款單、個人訂閱、grant_ref 授予紀錄）用測試自己控制的回傳值。"""

    def __init__(self, invoices=None, ledger_row=None, grant_ref_row=None):
        self._invoices = invoices if invoices is not None else []
        self._ledger_row = ledger_row
        self._grant_ref_row = grant_ref_row
        self.insert_calls = []

    def enabled(self):
        return False

    def load_enterprise_invoices(self, client_id=None, limit=200):
        return list(self._invoices)

    def get_latest_subscription_ledger(self, account_id):
        return self._ledger_row

    def get_subscription_ledger_by_grant_ref(self, grant_ref):
        return self._grant_ref_row

    def insert_enterprise_subscription_grant(self, payload):
        self.insert_calls.append(payload)
        return {**payload, "id": str(uuid.uuid4()), "status": "active"}

    def find_auth_user_by_email(self, email):
        return None

    def resolve_auth_identity(self, auth_user_id):
        return None

    # 以下方法比照「真的 SupabaseAdapter 但 enabled()==False」時的行為（一律回 None，
    # 讓呼叫端乾淨地落回本地 JSON 備援）——不寫這些會變成 AttributeError 也能被
    # exception fallback 接住（因為 enabled()==False 不會 re-raise），但那樣測試輸出
    # 會充滿誤導性的『xxx failed』警告，這裡明確定義乾淨版本。
    def get_enterprise_client(self, client_id):
        return None

    def load_enterprise_clients(self, query=None, status=None):
        return None

    def save_enterprise_client(self, client):
        return None

    def get_enterprise_seat(self, seat_id):
        return None

    def load_enterprise_seats(self, client_id=None, status=None, account_id=None, invite_email=None):
        return None

    def create_enterprise_seat(self, seat):
        return None

    def update_enterprise_seat(self, seat_id, patch):
        return None

    def append_enterprise_seat_event(self, event):
        return None

    def load_enterprise_seat_events(self, seat_id=None, limit=500):
        return None


TEST_ACCOUNT_ID = "11111111-1111-4111-8111-111111111111"


class EnterpriseSeatsTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="munea-enterprise-seats-test-")
        self._orig = {
            "CLIENTS_PATH": es.CLIENTS_PATH,
            "SEATS_PATH": es.SEATS_PATH,
            "SEAT_EVENTS_PATH": es.SEAT_EVENTS_PATH,
            "LOCAL_GRANTS_PATH": es.LOCAL_GRANTS_PATH,
        }
        es.CLIENTS_PATH = os.path.join(self.tmp_dir, "clients.json")
        es.SEATS_PATH = os.path.join(self.tmp_dir, "seats.json")
        es.SEAT_EVENTS_PATH = os.path.join(self.tmp_dir, "seat_events.json")
        es.LOCAL_GRANTS_PATH = os.path.join(self.tmp_dir, "local_grants.json")

    def tearDown(self):
        for key, value in self._orig.items():
            setattr(es, key, value)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def make_client(self, plan_tier="plus", seat_quota=10):
        return es.upsert_client({
            "name": "測試公司",
            "planTier": plan_tier,
            "unitPriceTwd": 100,
            "seatQuota": seat_quota,
        })

    def make_active_seat(self, client_id, account_id=TEST_ACCOUNT_ID, email="person@example.com"):
        seat = es.create_pending_seat(client_id, email)
        return es.transition_seat(seat["id"], "active", actor="test", reason="test_bind", account_id=account_id)


class Rule1GrantRefRequiredTests(EnterpriseSeatsTestBase):
    """鐵律 1：非 Apple 來源的授予，grant_ref 必填。"""

    def test_non_apple_provider_without_grant_ref_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            es.validate_subscription_grant_ref("enterprise", None)
        self.assertEqual(str(ctx.exception), "grant_ref_required_for_non_apple_provider")

    def test_non_apple_provider_with_empty_string_grant_ref_is_rejected(self):
        with self.assertRaises(ValueError):
            es.validate_subscription_grant_ref("enterprise", "")

    def test_apple_provider_is_exempt(self):
        es.validate_subscription_grant_ref("apple", None)  # 不應丟例外

    def test_grant_enterprise_membership_always_writes_grant_ref(self):
        client = self.make_client()
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[{"status": "paid"}])
        with patch.object(es, "_backend", return_value=backend):
            result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])
        self.assertEqual(len(backend.insert_calls), 1)
        self.assertEqual(backend.insert_calls[0]["grant_ref"], seat["id"])
        self.assertTrue(backend.insert_calls[0]["grant_ref"])


class Rule2UnpaidInvoiceBlocksGrantTests(EnterpriseSeatsTestBase):
    """鐵律 2：未付款不得開通——沒有 paid/invoiced 狀態的請款單一律拒絕。"""

    def test_no_invoice_at_all_blocks_grant(self):
        client = self.make_client()
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[])
        with patch.object(es, "_backend", return_value=backend):
            with self.assertRaises(ValueError) as ctx:
                es.grant_enterprise_membership(seat["id"])
        self.assertEqual(str(ctx.exception), "enterprise_invoice_not_paid")
        self.assertEqual(backend.insert_calls, [])

    def test_draft_invoice_blocks_grant(self):
        client = self.make_client()
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[{"status": "draft"}])
        with patch.object(es, "_backend", return_value=backend):
            with self.assertRaises(ValueError):
                es.grant_enterprise_membership(seat["id"])
        self.assertEqual(backend.insert_calls, [])

    def test_issued_but_not_paid_invoice_blocks_grant(self):
        client = self.make_client()
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[{"status": "issued"}])
        with patch.object(es, "_backend", return_value=backend):
            with self.assertRaises(ValueError):
                es.grant_enterprise_membership(seat["id"])
        self.assertEqual(backend.insert_calls, [])

    def test_paid_invoice_allows_grant(self):
        client = self.make_client()
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[{"status": "paid"}])
        with patch.object(es, "_backend", return_value=backend):
            result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])
        self.assertEqual(len(backend.insert_calls), 1)

    def test_invoiced_status_also_allows_grant(self):
        client = self.make_client()
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[{"status": "invoiced"}])
        with patch.object(es, "_backend", return_value=backend):
            result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])

    def test_void_invoice_does_not_count_as_paid(self):
        client = self.make_client()
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[{"status": "void"}])
        with patch.object(es, "_backend", return_value=backend):
            with self.assertRaises(ValueError):
                es.grant_enterprise_membership(seat["id"])


class Rule3NoDoubleGrantTests(EnterpriseSeatsTestBase):
    """鐵律 3：不得重複授予——企業等級 < 個人現有等級轉 waiting；同一席次重複授予要 idempotent。"""

    def test_individual_higher_plan_blocks_grant_and_sets_waiting(self):
        client = self.make_client(plan_tier="plus")
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(
            invoices=[{"status": "paid"}],
            ledger_row={
                "provider": "apple", "status": "active",
                "active_plan": "pro", "expires_at": "2026-12-31T00:00:00Z",
            },
        )
        with patch.object(es, "_backend", return_value=backend):
            result = es.grant_enterprise_membership(seat["id"])
        self.assertFalse(result["granted"])
        self.assertTrue(result["waiting"])
        self.assertEqual(result["reason"], "individual_plan_higher")
        self.assertEqual(result["seat"]["status"], "waiting")
        self.assertEqual(result["seat"]["waitingUntil"], "2026-12-31T00:00:00Z")
        self.assertEqual(backend.insert_calls, [])  # 完全沒有寫入 subscription_ledger

    def test_individual_equal_plan_allows_normal_grant(self):
        client = self.make_client(plan_tier="pro")
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(
            invoices=[{"status": "paid"}],
            ledger_row={"provider": "apple", "status": "active", "active_plan": "pro"},
        )
        with patch.object(es, "_backend", return_value=backend):
            result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])
        self.assertEqual(len(backend.insert_calls), 1)

    def test_individual_lower_plan_allows_normal_grant(self):
        client = self.make_client(plan_tier="pro")
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(
            invoices=[{"status": "paid"}],
            ledger_row={"provider": "apple", "status": "active", "active_plan": "plus"},
        )
        with patch.object(es, "_backend", return_value=backend):
            result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])
        self.assertEqual(len(backend.insert_calls), 1)

    def test_no_individual_subscription_allows_normal_grant(self):
        client = self.make_client(plan_tier="plus")
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[{"status": "paid"}], ledger_row=None)
        with patch.object(es, "_backend", return_value=backend):
            result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])

    def test_existing_enterprise_ledger_row_is_not_a_blocker(self):
        """個人現有訂閱本身就是企業來源（provider=enterprise）時不算『個人已購買』。"""
        client = self.make_client(plan_tier="plus")
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(
            invoices=[{"status": "paid"}],
            ledger_row={"provider": "enterprise", "status": "active", "active_plan": "pro"},
        )
        with patch.object(es, "_backend", return_value=backend):
            result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])

    def test_same_seat_granted_twice_is_idempotent_not_duplicated(self):
        client = self.make_client()
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[{"status": "paid"}])
        with patch.object(es, "_backend", return_value=backend):
            first = es.grant_enterprise_membership(seat["id"])
            backend._grant_ref_row = {**backend.insert_calls[0], "status": "active"}
            second = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(first["granted"])
        self.assertTrue(second["granted"])
        self.assertTrue(second.get("idempotent"))
        self.assertEqual(len(backend.insert_calls), 1)  # 只插入一次，鐵律 3 擋下第二次重插

    def test_waiting_seat_auto_handover_once_individual_plan_gone(self):
        client = self.make_client(plan_tier="pro")
        seat = self.make_active_seat(client["id"])
        backend = FakeBackend(invoices=[{"status": "paid"}])
        with patch.object(es, "_backend", return_value=backend):
            es.transition_seat(
                seat["id"], "waiting", actor="test", reason="setup",
                account_id=seat["accountId"], waiting_until="2020-01-01T00:00:00Z",
            )
            result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])
        self.assertEqual(result["seat"]["status"], "active")
        self.assertIsNone(result["seat"]["waitingUntil"])


class ImportPreviewFiveCategoriesTests(EnterpriseSeatsTestBase):
    """需求單 3.2：匯入預檢五種分類。"""

    def test_new_duplicate_and_owned_by_other_client(self):
        client_a = self.make_client()
        client_b = self.make_client()
        es.create_pending_seat(client_b["id"], "other-company@example.com")
        rows = [
            {"email": "new1@example.com"},
            {"email": "new1@example.com"},  # 批次內重複
            {"email": "other-company@example.com"},  # 屬於其他公司
        ]
        backend = FakeBackend()
        with patch.object(es, "_backend", return_value=backend):
            preview = es.import_preview(client_a["id"], rows)
        self.assertEqual([e["email"] for e in preview["newSeats"]], ["new1@example.com"])
        self.assertEqual(len(preview["duplicates"]), 1)
        self.assertEqual(len(preview["ownedByOtherClient"]), 1)
        self.assertEqual(preview["ownedByOtherClient"][0]["email"], "other-company@example.com")
        self.assertEqual(preview["alreadyRegistered"], [])
        self.assertEqual(preview["overQuota"], [])

    def test_already_existing_in_same_client_counts_as_duplicate(self):
        client = self.make_client()
        es.create_pending_seat(client["id"], "existing@example.com")
        backend = FakeBackend()
        with patch.object(es, "_backend", return_value=backend):
            preview = es.import_preview(client["id"], [{"email": "existing@example.com"}])
        self.assertEqual(len(preview["duplicates"]), 1)
        self.assertEqual(preview["newSeats"], [])

    def test_over_quota(self):
        client = self.make_client(seat_quota=1)
        rows = [{"email": "a@example.com"}, {"email": "b@example.com"}]
        backend = FakeBackend()
        with patch.object(es, "_backend", return_value=backend):
            preview = es.import_preview(client["id"], rows)
        self.assertEqual(len(preview["newSeats"]), 1)
        self.assertEqual(len(preview["overQuota"]), 1)
        self.assertEqual(preview["overQuota"][0]["email"], "b@example.com")

    def test_already_registered_when_email_matches_auth_user(self):
        client = self.make_client()

        class RegisteredBackend(FakeBackend):
            def find_auth_user_by_email(self, email):
                return {"id": "22222222-2222-4222-8222-222222222222", "email": email}

            def resolve_auth_identity(self, auth_user_id):
                return {"accountId": TEST_ACCOUNT_ID}

        backend = RegisteredBackend()
        with patch.object(es, "_backend", return_value=backend):
            preview = es.import_preview(client["id"], [{"email": "registered@example.com"}])
        self.assertEqual(len(preview["alreadyRegistered"]), 1)
        self.assertEqual(preview["alreadyRegistered"][0]["accountId"], TEST_ACCOUNT_ID)
        self.assertEqual(preview["newSeats"], [])

    def test_import_commit_binds_already_registered_directly_to_active(self):
        client = self.make_client()

        class RegisteredBackend(FakeBackend):
            def find_auth_user_by_email(self, email):
                if email == "registered@example.com":
                    return {"id": "22222222-2222-4222-8222-222222222222", "email": email}
                return None

            def resolve_auth_identity(self, auth_user_id):
                return {"accountId": TEST_ACCOUNT_ID}

        backend = RegisteredBackend()
        with patch.object(es, "_backend", return_value=backend):
            result = es.import_commit(client["id"], [{"email": "registered@example.com"}, {"email": "brandnew@example.com"}])
        self.assertEqual(result["summary"]["activatedCount"], 1)
        self.assertEqual(result["summary"]["createdCount"], 1)
        self.assertEqual(result["activated"][0]["status"], "active")
        self.assertEqual(result["created"][0]["status"], "pending")

    def test_import_commit_skips_over_quota_unless_confirmed(self):
        client = self.make_client(seat_quota=1)
        rows = [{"email": "a@example.com"}, {"email": "b@example.com"}]
        backend = FakeBackend()
        with patch.object(es, "_backend", return_value=backend):
            not_confirmed = es.import_commit(client["id"], rows, confirm_over_quota=False)
        self.assertEqual(not_confirmed["summary"]["createdCount"], 1)
        self.assertEqual(not_confirmed["summary"]["skippedCount"], 1)
        self.assertEqual(not_confirmed["skipped"][0]["skipReason"], "over_quota")

        # 重新開一家新公司＋換一組新 email 測「確認超額後照樣匯入」——
        # 沿用同一組 email 會踩到『屬他家公司』規則（client 已經先佔用了 a/b），
        # 那是規則本身的正確行為，不是這個測試要驗的東西，所以換組乾淨的 email。
        client2 = self.make_client(seat_quota=1)
        rows2 = [{"email": "c@example.com"}, {"email": "d@example.com"}]
        with patch.object(es, "_backend", return_value=backend):
            confirmed = es.import_commit(client2["id"], rows2, confirm_over_quota=True)
        self.assertEqual(confirmed["summary"]["createdCount"], 2)
        self.assertEqual(confirmed["summary"]["skippedCount"], 0)


if __name__ == "__main__":
    unittest.main()


class CrossModuleInvoicePaidConsistencyTests(EnterpriseSeatsTestBase):
    """跨模組整合測試：走 enterprise_billing.py 真正的 mark-sent／mark-paid 流程
   （不經 server.py HTTP 層，直接呼叫兩支模組的公開函式），驗證
    enterprise_seats.assert_client_has_paid_invoice() 認得到 enterprise_billing.py
    寫進去的請款單狀態——這是蘇菲要求「兩邊認定的已付款狀態一致」的真實驗證，
    不是憑印象宣稱。兩邊在 Supabase 未啟用時都退本地 JSON 檔，這裡把兩支模組的
    INVOICES_PATH 指到同一個暫存檔，模擬本機／測試環境下真的共用同一份資料。"""

    def setUp(self):
        super().setUp()
        self._orig_billing_invoices_path = eb.INVOICES_PATH
        shared_invoices_path = os.path.join(self.tmp_dir, "invoices.json")
        eb.INVOICES_PATH = shared_invoices_path
        es.INVOICES_PATH = shared_invoices_path

    def tearDown(self):
        eb.INVOICES_PATH = self._orig_billing_invoices_path
        super().tearDown()

    def test_grant_blocked_until_billing_module_marks_invoice_paid(self):
        """故意不 mock _backend()——兩支模組都用真正的「Supabase 未啟用」退路徑
       （測試環境本來就沒設 Supabase），才是真的在驗證『兩邊本地備援讀寫同一份資料』，
        不是又造一個假後端自欺欺人。"""
        client = self.make_client(plan_tier="plus")
        seat = self.make_active_seat(client["id"])
        period_start, period_end = eb.billing_period_for(2026, 7)

        # 1) 月結產出 draft 請款單（enterprise_billing.py 真的函式，不重寫邏輯）
        invoice = eb.generate_monthly_invoice(client, [seat], period_start, period_end, persist=True)
        self.assertEqual(invoice["status"], "draft")

        # 2) draft 階段：授予應該被鐵律 2 擋下
        with self.assertRaises(ValueError) as ctx:
            es.grant_enterprise_membership(seat["id"])
        self.assertEqual(str(ctx.exception), "enterprise_invoice_not_paid")

        # 3) mark-sent：draft -> issued（比照 server.py enterprise_invoice_mark_sent_response 的邏輯）
        issued = dict(invoice)
        issued["status"] = "issued"
        issued["sentAt"] = "2026-08-01T00:00:00Z"
        eb.save_invoice(issued)

        # 4) issued 階段：仍未付款，還是要被擋下
        with self.assertRaises(ValueError):
            es.grant_enterprise_membership(seat["id"])

        # 5) mark-paid：issued -> paid（比照 server.py enterprise_invoice_mark_paid_response 的邏輯）
        paid = dict(issued)
        paid["status"] = "paid"
        paid["paidAt"] = "2026-08-05T00:00:00Z"
        paid["paidAmountTwd"] = paid.get("totalTwd")
        eb.save_invoice(paid)

        # 6) 已入帳：這次應該放行，且真的寫進本地備援的 subscription_ledger 紀錄
        result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])
        self.assertEqual(result["ledger"]["grantRef"], seat["id"])

    def test_invoiced_status_from_billing_module_also_unlocks_grant(self):
        """mark-paid 若同時帶發票號碼，enterprise_billing 那邊會把狀態落到 invoiced——
        鐵律 2 一樣要放行（PAID_INVOICE_STATUSES 含 invoiced）。"""
        client = self.make_client(plan_tier="plus")
        seat = self.make_active_seat(client["id"])
        period_start, period_end = eb.billing_period_for(2026, 7)

        invoice = eb.generate_monthly_invoice(client, [seat], period_start, period_end, persist=True)
        invoiced = dict(invoice)
        invoiced["status"] = "invoiced"
        invoiced["paidAt"] = "2026-08-05T00:00:00Z"
        invoiced["invoiceNumber"] = "AB12345678"
        invoiced["invoiceIssuedAt"] = "2026-08-06T00:00:00Z"
        eb.save_invoice(invoiced)

        result = es.grant_enterprise_membership(seat["id"])
        self.assertTrue(result["granted"])


class BillingSettingsTests(EnterpriseSeatsTestBase):
    """開票／收款設定（2026-07-20 二次需求）：讀寫走本地備援＋is_configured 判定。"""

    def setUp(self):
        super().setUp()
        self._orig_settings_path = es.BILLING_SETTINGS_PATH
        es.BILLING_SETTINGS_PATH = os.path.join(self.tmp_dir, "billing_settings.json")

    def tearDown(self):
        es.BILLING_SETTINGS_PATH = self._orig_settings_path
        super().tearDown()

    def test_unset_settings_is_not_configured_and_not_none(self):
        settings = es.get_billing_settings()
        self.assertIsNotNone(settings)
        self.assertIsNone(settings["issuerCompanyName"])
        self.assertFalse(es.is_billing_settings_configured(settings))
        self.assertFalse(es.is_billing_settings_configured())  # 不傳參數也要能自己查

    def test_save_then_read_round_trips_and_becomes_configured(self):
        saved = es.save_billing_settings({
            "issuerCompanyName": "測試股份有限公司",
            "issuerTaxId": "12345678",
            "bankName": "測試銀行",
            "bankAccountName": "測試股份有限公司",
            "bankAccountNo": "1234567890123",
        }, updated_by="edward@example.com")
        self.assertEqual(saved["issuerCompanyName"], "測試股份有限公司")
        self.assertEqual(saved["updatedBy"], "edward@example.com")
        self.assertIsNotNone(saved["updatedAt"])

        reloaded = es.get_billing_settings()
        self.assertEqual(reloaded["bankAccountNo"], "1234567890123")
        self.assertTrue(es.is_billing_settings_configured(reloaded))

    def test_partial_fields_still_not_configured(self):
        es.save_billing_settings({"issuerCompanyName": "只填了抬頭"})
        self.assertFalse(es.is_billing_settings_configured())

    def test_default_payment_terms_days_is_15(self):
        settings = es.get_billing_settings()
        self.assertEqual(settings["paymentTermsDays"], 15)

    def test_save_overwrites_single_row_not_appends(self):
        es.save_billing_settings({"issuerCompanyName": "第一次"})
        es.save_billing_settings({"issuerCompanyName": "第二次"})
        with open(es.BILLING_SETTINGS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        self.assertIsInstance(raw, dict)  # 單一物件，不是 list——不會累積多筆
        self.assertEqual(raw["issuerCompanyName"], "第二次")
