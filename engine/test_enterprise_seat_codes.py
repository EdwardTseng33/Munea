#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
機構席次開通碼（033 · 2026-11-17）。

要守住的事：
  1. 碼只有 8 位數字，長輩怎麼打（全形、夾橫線、夾空白）都認得；混進英文字母就是打錯，不放行。
  2. 一組碼只能綁一個帳號；同一個人重複輸入自己的碼不算錯；一個帳號不能佔兩席。
  3. 鐵律不變：機構還沒入帳，輸入開通碼只會「登記」、不會開會員資格。
  4. 舊的 email 名單流程一個字都不能壞。
  5. 開通碼、名冊稱呼、名冊手機不得出現在機構端的任何回應。
"""
import csv
import io
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "seat-code-test-key")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import enterprise_seats as es
import org_api
import org_portal
import supabase_adapter
from test_enterprise_seats import EnterpriseSeatsTestBase, FakeBackend, TEST_ACCOUNT_ID

OTHER_ACCOUNT_ID = "22222222-2222-4222-8222-222222222222"
PAID = [{"status": "paid"}]


class CodeBackend(FakeBackend):
    """FakeBackend 加上 033 的兩個方法，行為比照「真的 adapter 但沒啟用」：
    找不到回 None、認領回 False（＝後端沒開，請退本機備援）。"""

    def get_enterprise_seat_by_redeem_code(self, code):
        return None

    def claim_enterprise_seat(self, seat_id, account_id, now_iso):
        return False


class NormalizeCodeTests(unittest.TestCase):
    def test_plain_eight_digits(self):
        self.assertEqual(es.normalize_redeem_code("12345678"), "12345678")

    def test_card_format_with_dash_and_spaces(self):
        self.assertEqual(es.normalize_redeem_code(" 1234-5678 "), "12345678")
        self.assertEqual(es.normalize_redeem_code("1234 5678"), "12345678")

    def test_fullwidth_digits_from_chinese_keyboard(self):
        self.assertEqual(es.normalize_redeem_code("１２３４５６７８"), "12345678")
        self.assertEqual(es.normalize_redeem_code("１２３４－５６７８"), "12345678")

    def test_leading_zero_is_kept(self):
        self.assertEqual(es.normalize_redeem_code("00123456"), "00123456")

    def test_letters_are_a_typo_not_a_separator(self):
        # 不可以把字母濾掉後拿剩下的數字去比對——1234567a 不是 1234567
        self.assertEqual(es.normalize_redeem_code("1234567a"), "")
        self.assertEqual(es.normalize_redeem_code("a12345678"), "")

    def test_wrong_length(self):
        self.assertEqual(es.normalize_redeem_code("1234567"), "")
        self.assertEqual(es.normalize_redeem_code("123456789"), "")
        self.assertEqual(es.normalize_redeem_code(""), "")
        self.assertEqual(es.normalize_redeem_code(None), "")

    def test_non_ascii_digits_rejected(self):
        # 阿拉伯文數字 isdigit() 也是 True，但不是我們發出去的碼
        self.assertEqual(es.normalize_redeem_code("١٢٣٤٥٦٧٨"), "")

    def test_display_format(self):
        self.assertEqual(es.format_redeem_code("12345678"), "1234-5678")
        self.assertEqual(es.format_redeem_code(None), "")

    def test_generated_code_shape(self):
        for _ in range(50):
            code = es.generate_redeem_code()
            self.assertEqual(len(code), 8)
            self.assertTrue(code.isdigit())

    def test_member_phone_cleaning(self):
        self.assertEqual(es.clean_member_phone("0912-345 678"), "0912345678")
        self.assertEqual(es.clean_member_phone("+886 912 345 678"), "+886912345678")
        self.assertIsNone(es.clean_member_phone("沒有"))


class CreateCodeSeatsTests(EnterpriseSeatsTestBase):
    def test_count_creates_pending_seats_with_unique_codes_and_no_email(self):
        client = self.make_client(seat_quota=10)
        result = es.create_code_seats(client["id"], count=5)
        self.assertEqual(result["summary"]["createdCount"], 5)
        codes = [s["redeemCode"] for s in result["created"]]
        self.assertEqual(len(set(codes)), 5)
        for seat in result["created"]:
            self.assertEqual(seat["status"], "pending")
            self.assertEqual(seat["inviteEmail"], "")
            self.assertIsNone(seat.get("accountId"))
            self.assertEqual(es.normalize_redeem_code(seat["redeemCode"]), seat["redeemCode"])

    def test_rows_keep_roster_name_and_cleaned_phone(self):
        client = self.make_client()
        result = es.create_code_seats(client["id"], rows=[
            {"name": "王奶奶", "phone": "0912-345-678", "note": "A 棟"},
            {"姓名": "李爺爺", "手機": "0987 654 321"},
        ])
        first, second = result["created"]
        self.assertEqual((first["memberName"], first["memberPhone"], first["notes"]), ("王奶奶", "0912345678", "A 棟"))
        self.assertEqual((second["memberName"], second["memberPhone"]), ("李爺爺", "0987654321"))

    def test_over_quota_creates_nothing_until_confirmed(self):
        client = self.make_client(seat_quota=2)
        result = es.create_code_seats(client["id"], count=3)
        self.assertEqual(result["created"], [])
        self.assertEqual(result["overQuota"], {"quota": 2, "occupied": 0, "requested": 3, "overBy": 1})
        self.assertEqual(es.list_seats(client_id=client["id"]), [])
        confirmed = es.create_code_seats(client["id"], count=3, confirm_over_quota=True)
        self.assertEqual(confirmed["summary"]["createdCount"], 3)

    def test_quota_counts_existing_email_seats(self):
        client = self.make_client(seat_quota=2)
        es.create_pending_seat(client["id"], "a@example.com")
        result = es.create_code_seats(client["id"], count=2)
        self.assertEqual(result["overQuota"]["occupied"], 1)
        self.assertEqual(result["overQuota"]["overBy"], 1)

    def test_rejects_empty_unknown_client_ended_client_and_huge_batch(self):
        client = self.make_client()
        with self.assertRaises(ValueError) as ctx:
            es.create_code_seats(client["id"], count=0)
        self.assertEqual(str(ctx.exception), "code_seat_rows_required")
        with self.assertRaises(ValueError) as ctx:
            es.create_code_seats("no-such-client", count=1)
        self.assertEqual(str(ctx.exception), "enterprise_client_not_found")
        with self.assertRaises(ValueError) as ctx:
            es.create_code_seats(client["id"], count=es.CODE_SEATS_MAX_PER_CALL + 1)
        self.assertEqual(str(ctx.exception), "code_seat_batch_too_large")
        ended = es.upsert_client({**client, "status": "ended"})
        with self.assertRaises(ValueError) as ctx:
            es.create_code_seats(ended["id"], count=1)
        self.assertEqual(str(ctx.exception), "enterprise_client_ended")

    def test_code_collision_is_retried(self):
        client = self.make_client()
        first = es.create_code_seats(client["id"], count=1)["created"][0]
        with patch.object(es, "generate_redeem_code", side_effect=[first["redeemCode"], "87654321"]):
            second = es.create_code_seats(client["id"], count=1)["created"][0]
        self.assertEqual(second["redeemCode"], "87654321")

    def test_export_keeps_old_columns_and_appends_code_columns(self):
        client = self.make_client()
        es.create_pending_seat(client["id"], "old@example.com", note="舊流程")
        seat = es.create_code_seats(client["id"], rows=[{"name": "王奶奶", "phone": "0912345678"}])["created"][0]
        rows = list(csv.reader(io.StringIO(es.build_seat_export_csv(client_id=client["id"]))))
        self.assertEqual(rows[0][:8], ["email", "status", "account_id", "activated_at", "waiting_until",
                                       "grace_until", "released_at", "note"])
        self.assertEqual(rows[0][8:], ["member_name", "member_phone", "redeem_code", "redeemed_at"])
        self.assertEqual(rows[1][0], "old@example.com")
        self.assertEqual(rows[1][10], "")
        self.assertEqual(rows[2][0], "")
        self.assertEqual(rows[2][8:11], ["王奶奶", "0912345678", es.format_redeem_code(seat["redeemCode"])])


class RedeemCodeTests(EnterpriseSeatsTestBase):
    def code_seat(self, **client_kwargs):
        client = self.make_client(**client_kwargs)
        seat = es.create_code_seats(client["id"], count=1)["created"][0]
        return client, seat

    def redeem(self, code, account_id=TEST_ACCOUNT_ID, backend=None):
        backend = backend or CodeBackend()
        with patch.object(es, "_backend", return_value=backend):
            return es.redeem_seat_code(code, account_id), backend

    def test_unpaid_institution_only_registers_never_grants(self):
        """鐵律：錢沒到、帳號不開。開通碼不是繞過收款的後門。"""
        client, seat = self.code_seat()
        outcome, backend = self.redeem(seat["redeemCode"])
        self.assertEqual(outcome["result"], "registered")
        self.assertEqual(outcome["grantBlockedBy"], "enterprise_invoice_not_paid")
        self.assertEqual(backend.insert_calls, [])
        stored = es.get_seat(seat["id"])
        self.assertEqual(stored["status"], "active")
        self.assertEqual(stored["accountId"], TEST_ACCOUNT_ID)
        self.assertTrue(stored["redeemedAt"])

    def test_paid_institution_activates_with_grant_ref(self):
        client, seat = self.code_seat(plan_tier="pro")
        outcome, backend = self.redeem(es.format_redeem_code(seat["redeemCode"]), backend=CodeBackend(invoices=PAID))
        self.assertEqual(outcome["result"], "activated")
        self.assertEqual(len(backend.insert_calls), 1)
        grant = backend.insert_calls[0]
        self.assertEqual(grant["grant_ref"], seat["id"])
        self.assertEqual(grant["account_id"], TEST_ACCOUNT_ID)
        self.assertEqual(grant["active_plan"], "pro")
        self.assertEqual(grant["provider"], "enterprise")

    def test_individual_higher_plan_waits(self):
        client, seat = self.code_seat(plan_tier="plus")
        ledger = {"provider": "apple", "status": "active", "active_plan": "pro", "expires_at": "2027-01-01T00:00:00+00:00"}
        outcome, backend = self.redeem(seat["redeemCode"], backend=CodeBackend(invoices=PAID, ledger_row=ledger))
        self.assertEqual(outcome["result"], "waiting")
        self.assertEqual(backend.insert_calls, [])
        self.assertEqual(es.get_seat(seat["id"])["status"], "waiting")

    def test_redeem_writes_seat_event(self):
        client, seat = self.code_seat()
        self.redeem(seat["redeemCode"])
        reasons = [e["reason"] for e in es.load_seat_events(seat_id=seat["id"])]
        self.assertIn("seat_created_with_redeem_code", reasons)
        self.assertIn("redeem_code_claimed", reasons)

    def test_invalid_format_and_unknown_code(self):
        self.code_seat()
        for bad in ("", "1234", "abcdefgh", "1234567a"):
            with self.assertRaises(ValueError) as ctx:
                self.redeem(bad)
            self.assertEqual(str(ctx.exception), "invalid_code_format")
        with self.assertRaises(ValueError) as ctx:
            self.redeem("00000000")
        self.assertEqual(str(ctx.exception), "code_not_found")

    def test_code_used_by_someone_else(self):
        client, seat = self.code_seat()
        self.redeem(seat["redeemCode"], account_id=OTHER_ACCOUNT_ID)
        with self.assertRaises(ValueError) as ctx:
            self.redeem(seat["redeemCode"], account_id=TEST_ACCOUNT_ID)
        self.assertEqual(str(ctx.exception), "code_already_used")
        self.assertEqual(es.get_seat(seat["id"])["accountId"], OTHER_ACCOUNT_ID)

    def test_same_person_entering_own_code_again_is_not_an_error(self):
        client, seat = self.code_seat()
        self.redeem(seat["redeemCode"])
        events_before = len(es.load_seat_events(seat_id=seat["id"]))
        again, backend = self.redeem(seat["redeemCode"])
        self.assertTrue(again["alreadyYours"])
        self.assertEqual(again["result"], "registered")
        self.assertEqual(backend.insert_calls, [])
        self.assertEqual(len(es.load_seat_events(seat_id=seat["id"])), events_before)

    def test_own_code_again_reports_activated_once_granted(self):
        client, seat = self.code_seat()
        self.redeem(seat["redeemCode"], backend=CodeBackend(invoices=PAID))
        granted_backend = CodeBackend(invoices=PAID, grant_ref_row={"status": "active", "grant_ref": seat["id"]})
        again, _ = self.redeem(seat["redeemCode"], backend=granted_backend)
        self.assertEqual((again["result"], again["alreadyYours"]), ("activated", True))
        self.assertEqual(granted_backend.insert_calls, [])

    def test_one_account_cannot_hold_two_seats(self):
        client = self.make_client()
        first, second = es.create_code_seats(client["id"], count=2)["created"]
        self.redeem(first["redeemCode"])
        with self.assertRaises(ValueError) as ctx:
            self.redeem(second["redeemCode"])
        self.assertEqual(str(ctx.exception), "already_has_seat")
        untouched = es.get_seat(second["id"])
        self.assertEqual(untouched["status"], "pending")
        self.assertIsNone(untouched.get("accountId"))

    def test_existing_email_seat_also_blocks_a_second_seat(self):
        client = self.make_client()
        self.make_active_seat(client["id"], account_id=TEST_ACCOUNT_ID, email="me@example.com")
        code_seat = es.create_code_seats(client["id"], count=1)["created"][0]
        with self.assertRaises(ValueError) as ctx:
            self.redeem(code_seat["redeemCode"])
        self.assertEqual(str(ctx.exception), "already_has_seat")

    def test_released_seat_code_is_expired(self):
        client, seat = self.code_seat()
        es.transition_seat(seat["id"], "released", actor="test", reason="revoked", released_reason="removed_by_client")
        with self.assertRaises(ValueError) as ctx:
            self.redeem(seat["redeemCode"])
        self.assertEqual(str(ctx.exception), "code_expired")

    def test_ended_or_past_contract_is_expired(self):
        client, seat = self.code_seat()
        es.upsert_client({**client, "contractEnd": "2020-01-01"})
        with self.assertRaises(ValueError) as ctx:
            self.redeem(seat["redeemCode"])
        self.assertEqual(str(ctx.exception), "code_expired")
        es.upsert_client({**client, "contractEnd": None, "status": "ended"})
        with self.assertRaises(ValueError) as ctx:
            self.redeem(seat["redeemCode"])
        self.assertEqual(str(ctx.exception), "code_expired")
        self.assertEqual(es.get_seat(seat["id"])["status"], "pending")

    def test_losing_the_race_reports_already_used(self):
        """兩個人同時輸入同一組碼：資料庫只讓一個成功，另一個要看到「已被使用」而不是當成成功。"""
        client, seat = self.code_seat()
        with patch.object(es, "_claim_seat_for_account", return_value=None):
            with self.assertRaises(ValueError) as ctx:
                self.redeem(seat["redeemCode"])
        self.assertEqual(str(ctx.exception), "code_already_used")

    def test_requires_real_account_id(self):
        client, seat = self.code_seat()
        with self.assertRaises(ValueError) as ctx:
            self.redeem(seat["redeemCode"], account_id="not-a-uuid")
        self.assertEqual(str(ctx.exception), "valid_account_id_required_to_activate_seat")

    def test_old_email_flow_untouched(self):
        client = self.make_client()
        seat = es.create_pending_seat(client["id"], "Person@Example.com")
        self.assertEqual(seat["inviteEmail"], "person@example.com")
        self.assertIsNone(seat["redeemCode"])
        self.assertIsNone(es.find_seat_by_redeem_code("12345678"))


class AdapterShapeTests(unittest.TestCase):
    def adapter(self):
        return supabase_adapter.SupabaseAdapter.__new__(supabase_adapter.SupabaseAdapter)

    def test_code_seat_row_sends_null_email_not_empty_string(self):
        row = self.adapter().enterprise_seat_to_row({"enterpriseClientId": "c", "redeemCode": "12345678",
                                                    "memberName": "王奶奶", "memberPhone": "0912345678"})
        self.assertIsNone(row["invite_email"])
        self.assertEqual(row["redeem_code"], "12345678")
        self.assertEqual((row["member_name"], row["member_phone"]), ("王奶奶", "0912345678"))

    def test_email_seat_row_does_not_send_new_columns(self):
        """033 還沒套用到資料庫之前，舊的 email 匯入不能因為多送欄位而失敗。"""
        row = self.adapter().enterprise_seat_to_row({"enterpriseClientId": "c", "inviteEmail": "A@Example.com"})
        self.assertEqual(row["invite_email"], "a@example.com")
        for column in ("redeem_code", "member_name", "member_phone", "redeemed_at"):
            self.assertNotIn(column, row)

    def test_row_to_item_carries_code_fields(self):
        item = supabase_adapter.SupabaseAdapter.enterprise_seat_row_to_item({
            "id": "s", "redeem_code": "12345678", "member_name": "王奶奶", "member_phone": "0912345678",
            "redeemed_at": "2026-11-17T00:00:00+00:00", "invite_email": None,
        })
        self.assertEqual(item["redeemCode"], "12345678")
        self.assertEqual(item["inviteEmail"], "")
        self.assertEqual(item["redeemedAt"], "2026-11-17T00:00:00+00:00")

    def test_claim_is_one_conditional_update(self):
        adapter = self.adapter()
        calls = []

        def fake_request(method, table, query=None, payload=None, prefer=None):
            calls.append((method, table, query, payload))
            return []

        adapter.enabled = lambda: True
        adapter._request = fake_request
        result = adapter.claim_enterprise_seat(TEST_ACCOUNT_ID, OTHER_ACCOUNT_ID, "2026-11-17T00:00:00+00:00")
        self.assertIsNone(result)  # 沒有任何一列符合條件＝被別人搶先
        method, table, query, payload = calls[0]
        self.assertEqual((method, table), ("PATCH", "enterprise_seats"))
        self.assertEqual(query["account_id"], "is.null")
        self.assertEqual(query["status"], "eq.pending")
        self.assertEqual(payload["account_id"], OTHER_ACCOUNT_ID)
        self.assertEqual(payload["status"], "active")

    def test_claim_reports_backend_off_distinctly(self):
        adapter = self.adapter()
        adapter.enabled = lambda: False
        self.assertIs(adapter.claim_enterprise_seat(TEST_ACCOUNT_ID, OTHER_ACCOUNT_ID, "now"), False)


class InstitutionFacingPrivacyTests(unittest.TestCase):
    def test_code_and_roster_fields_are_forbidden_in_org_responses(self):
        for key in ("redeemcode", "redeem_code", "membername", "member_name", "memberphone", "member_phone"):
            self.assertIn(key, org_api.ORG_FORBIDDEN_KEYS)
            self.assertIn(key, org_portal.FORBIDDEN_KEYS)


class SqlMigrationTests(unittest.TestCase):
    def test_033_shape(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "supabase", "sql",
                            "033_enterprise_seat_redeem_codes.sql")
        with open(path, encoding="utf-8") as fh:
            sql = fh.read()
        self.assertIn("alter column invite_email drop not null", sql)
        self.assertIn("enterprise_seats_redeem_code_uidx", sql)
        self.assertIn("'^[0-9]{8}$'", sql)
        self.assertIn("enterprise_seats_identity_present", sql)
        # 碼的長度兩邊要一致：改了一邊忘了另一邊，就會產生資料庫不收的碼
        self.assertEqual(es.REDEEM_CODE_LENGTH, 8)


class ServerEntryPointTests(EnterpriseSeatsTestBase):
    """/enterprise/redeem-code 與 /admin/enterprise/seats/create-codes 的薄層。"""

    class Actor:
        def __init__(self, account_id=TEST_ACCOUNT_ID, auth_user_id="auth-user-1"):
            self.account_id = account_id
            self.auth_user_id = auth_user_id

    def setUp(self):
        super().setUp()
        import server
        self.server = server
        server._SEAT_CODE_ATTEMPTS.clear()
        self.audit = []
        self._patches = [
            patch.object(server, "append_audit_event", side_effect=lambda e: self.audit.append(e)),
            patch.object(es, "_backend", return_value=CodeBackend()),
        ]
        for item in self._patches:
            item.start()

    def tearDown(self):
        for item in self._patches:
            item.stop()
        self.server._SEAT_CODE_ATTEMPTS.clear()
        super().tearDown()

    def redeem(self, code, actor=None, client_ip="203.0.113.9", actor_error=None):
        actor = actor or self.Actor()
        backend = (None if actor_error else actor, actor_error)
        with patch.object(self.server, "family_actor_backend", return_value=backend):
            return self.server.enterprise_redeem_code_response(
                {"code": code}, client_ip=client_ip, actor={"authUserId": actor.auth_user_id})

    def test_paths_are_registered(self):
        self.assertIn("/admin/enterprise/seats/create-codes", self.server.ADMIN_POST_PATHS)
        self.assertNotIn("/enterprise/redeem-code", self.server.PUBLIC_POST_PATHS)
        with open(self.server.__file__, encoding="utf-8") as fh:
            source = fh.read()
        # 兌換一定要驗證過的登入身分——本機／示範模式也不放行沒登入的人
        needle = '"/family/invitations", "/family-relays", "/push/devices"'
        gate_line = next(line for line in source.splitlines() if needle in line)
        self.assertIn('"/enterprise/redeem-code"', gate_line)

    def test_success_returns_public_fields_only(self):
        client = self.make_client(plan_tier="plus")
        seat = es.create_code_seats(client["id"], rows=[{"name": "王奶奶", "phone": "0912345678"}])["created"][0]
        response = self.redeem(seat["redeemCode"])
        self.assertEqual(response, {"ok": True, "result": "registered", "alreadyYours": False,
                                    "organizationName": "測試公司", "planTier": "plus", "waitingUntil": None})
        self.assertEqual(len(self.audit), 1)
        self.assertEqual(self.audit[0]["eventType"], "enterprise_seat_code_redeemed")
        self.assertNotIn(seat["redeemCode"], repr(self.audit[0]))

    def test_identity_comes_from_login_not_request_body(self):
        client = self.make_client()
        seat = es.create_code_seats(client["id"], count=1)["created"][0]
        with patch.object(self.server, "family_actor_backend", return_value=(self.Actor(), None)):
            self.server.enterprise_redeem_code_response(
                {"code": seat["redeemCode"], "accountId": OTHER_ACCOUNT_ID}, client_ip="203.0.113.9", actor={})
        self.assertEqual(es.get_seat(seat["id"])["accountId"], TEST_ACCOUNT_ID)

    def test_not_signed_in_or_no_account(self):
        self.assertEqual(self.redeem("12345678", actor_error="auth_required"),
                         {"ok": False, "error": {"code": "auth_required"}})
        self.assertEqual(self.redeem("12345678", actor=self.Actor(account_id="")),
                         {"ok": False, "error": {"code": "account_required"}})

    def test_wrong_guesses_lock_the_user_out(self):
        client = self.make_client()
        seat = es.create_code_seats(client["id"], count=1)["created"][0]
        for _ in range(self.server.SEAT_CODE_MAX_FAILS_PER_USER):
            self.assertEqual(self.redeem("00000001")["error"]["code"], "code_not_found")
        locked = self.redeem(seat["redeemCode"])  # 就算這次輸對也要等
        self.assertEqual(locked["error"]["code"], "too_many_attempts")
        self.assertIsNone(es.get_seat(seat["id"]).get("accountId"))
        # 換一個人、換一個來源不受影響
        other = self.redeem(seat["redeemCode"], actor=self.Actor(OTHER_ACCOUNT_ID, "auth-user-2"),
                            client_ip="203.0.113.50")
        self.assertTrue(other["ok"])

    def test_shared_wifi_ip_has_a_wider_limit(self):
        self.make_client()
        for index in range(self.server.SEAT_CODE_MAX_FAILS_PER_IP):
            actor = self.Actor(TEST_ACCOUNT_ID, "auth-user-%d" % index)
            self.assertEqual(self.redeem("00000001", actor=actor)["error"]["code"], "code_not_found")
        fresh = self.Actor(TEST_ACCOUNT_ID, "auth-user-fresh")
        self.assertEqual(self.redeem("00000001", actor=fresh)["error"]["code"], "too_many_attempts")

    def test_having_a_seat_already_is_not_counted_as_a_guess(self):
        client = self.make_client()
        first, second = es.create_code_seats(client["id"], count=2)["created"]
        self.redeem(first["redeemCode"])
        for _ in range(self.server.SEAT_CODE_MAX_FAILS_PER_USER + 2):
            self.assertEqual(self.redeem(second["redeemCode"])["error"]["code"], "already_has_seat")

    def test_internal_errors_are_not_leaked(self):
        boom = ValueError("valid_account_id_required_to_activate_seat")
        with patch.object(es, "redeem_seat_code", side_effect=boom):
            self.assertEqual(self.redeem("12345678")["error"]["code"], "redeem_failed")

    def test_create_codes_response(self):
        client = self.make_client(seat_quota=2)
        self.assertEqual(self.server.enterprise_seats_create_codes_response({})["error"]["code"], "client_id_required")
        over = self.server.enterprise_seats_create_codes_response({"clientId": client["id"], "count": 3})
        self.assertEqual(over["error"], {"code": "over_quota", "quota": 2, "occupied": 0, "requested": 3, "overBy": 1})
        ok = self.server.enterprise_seats_create_codes_response(
            {"clientId": client["id"], "rows": [{"name": "王奶奶", "phone": "0912-345-678"}]})
        self.assertTrue(ok["ok"])
        seat = ok["seats"][0]
        self.assertEqual(seat["memberName"], "王奶奶")
        self.assertEqual(seat["redeemCodeDisplay"], es.format_redeem_code(seat["redeemCode"]))
        self.assertEqual(ok["summary"]["createdCount"], 1)

    def test_create_codes_explains_missing_migration(self):
        client = self.make_client()
        boom = RuntimeError('null value in column "invite_email" violates not-null constraint')
        with patch.object(es, "_create_code_seat", side_effect=boom):
            response = self.server.enterprise_seats_create_codes_response({"clientId": client["id"], "count": 1})
        self.assertEqual(response["error"]["code"], "code_seat_create_failed")
        self.assertIn("invite_email", response["error"]["detail"])


if __name__ == "__main__":
    unittest.main()
