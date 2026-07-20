#!/usr/bin/env python3
"""企業席次月結測試（需求單 4：計費規則、請款單、ESG 成效月報、4.4 隱私鐵律、5.2 收款欄位）。
本檔跟 test_subscription_expiry.py 等既有測試同一套風格：unittest + 直接 import 目標模組。
大部分測試不接真的 Supabase——env 沒設 MUNEA_DATABASE_PROVIDER=supabase 時 configured()
就是 False，所有資料存取自動走本機 JSON 備援／或測試直接注入資料（seats/raw_metrics）。
唯一的例外是 InvoiceSupabaseFieldRoundTripTests：用一個假造的『已連線』backend
（FakeSupabaseBackend）驗證 5.2 六個收款欄位真的會被送進 payload、也真的讀得回來，
不是本地 JSON 備援那條路在幫忙掩護。"""
import copy
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
_TMP = tempfile.mkdtemp(prefix="munea-enterprise-billing-")
os.environ["MUNEA_ENTERPRISE_INVOICES_PATH"] = os.path.join(_TMP, "enterprise_invoices_store.json")
os.environ["MUNEA_ENTERPRISE_CLIENTS_PATH"] = os.path.join(_TMP, "enterprise_clients_store.json")
os.environ["MUNEA_ENTERPRISE_SEATS_PATH"] = os.path.join(_TMP, "enterprise_seats_store.json")
os.environ["MUNEA_ENTERPRISE_SEAT_EVENTS_PATH"] = os.path.join(_TMP, "enterprise_seat_events_store.json")
sys.path.insert(0, os.path.dirname(__file__))

import enterprise_billing as eb  # noqa: E402


CLIENT_ID = "11111111-1111-4111-8111-111111111111"


def make_client(**overrides):
    client = {
        "id": CLIENT_ID,
        "name": "測試股份有限公司",
        "taxId": "12345678",
        "billingAddress": "台北市信義區測試路 1 號",
        "contactName": "王小美",
        "contactEmail": "hr@example.com",
        "planTier": "plus",
        "unitPriceTwd": 3000,
        "seatQuota": 10,
        "status": "active",
    }
    client.update(overrides)
    return client


def make_seat(seat_id, status, activated_at=None, grace_started_at=None, account_id=None, **overrides):
    seat = {
        "id": seat_id,
        "enterpriseClientId": CLIENT_ID,
        "inviteEmail": f"{seat_id}@example.com",
        "accountId": account_id or f"acct-{seat_id}",
        "status": status,
        "activatedAt": activated_at,
        "graceStartedAt": grace_started_at,
        "graceUntil": None,
        "releasedAt": None,
        "releasedReason": None,
    }
    seat.update(overrides)
    return seat


JULY = eb.billing_period_for(2026, 7)  # (2026-07-01, 2026-07-31)


class BillingPeriodTests(unittest.TestCase):
    def test_billing_period_for_returns_first_and_last_day(self):
        start, end = eb.billing_period_for(2026, 2)
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))

    def test_compute_due_date_is_15th_of_next_month(self):
        _, period_end = eb.billing_period_for(2026, 7)
        self.assertEqual(eb.compute_due_date(period_end), date(2026, 8, 15))

    def test_compute_due_date_wraps_year_at_december(self):
        _, period_end = eb.billing_period_for(2026, 12)
        self.assertEqual(eb.compute_due_date(period_end), date(2027, 1, 15))


class SeatBillableRuleTests(unittest.TestCase):
    """需求單 4.1 五條規則，一條一個測試。"""

    def test_active_seat_from_earlier_month_is_billable(self):
        period_start, period_end = JULY
        seat = make_seat("s1", "active", activated_at="2026-05-10T00:00:00Z")
        self.assertTrue(eb.is_seat_billable(seat, period_start, period_end))

    def test_new_seat_activated_this_month_is_free(self):
        period_start, period_end = JULY
        seat = make_seat("s2", "active", activated_at="2026-07-15T00:00:00Z")
        self.assertFalse(eb.is_seat_billable(seat, period_start, period_end))

    def test_seat_removed_mid_month_is_still_billed(self):
        period_start, period_end = JULY
        seat = make_seat(
            "s3", "grace",
            activated_at="2026-03-01T00:00:00Z",
            grace_started_at="2026-07-20T00:00:00Z",
        )
        self.assertTrue(eb.is_seat_billable(seat, period_start, period_end))

    def test_seat_already_in_grace_before_this_month_is_not_billed(self):
        period_start, period_end = JULY
        seat = make_seat(
            "s4", "grace",
            activated_at="2026-01-01T00:00:00Z",
            grace_started_at="2026-06-10T00:00:00Z",
        )
        self.assertFalse(eb.is_seat_billable(seat, period_start, period_end))

    def test_waiting_seat_is_never_billed(self):
        period_start, period_end = JULY
        seat = make_seat("s5", "waiting", activated_at="2026-01-01T00:00:00Z")
        self.assertFalse(eb.is_seat_billable(seat, period_start, period_end))

    def test_pending_seat_is_never_billed(self):
        period_start, period_end = JULY
        seat = make_seat("s6", "pending")
        self.assertFalse(eb.is_seat_billable(seat, period_start, period_end))

    def test_released_seat_still_billed_if_grace_started_mid_month(self):
        period_start, period_end = JULY
        seat = make_seat(
            "s7", "released",
            activated_at="2026-02-01T00:00:00Z",
            grace_started_at="2026-07-05T00:00:00Z",
            released_at="2026-07-31T00:00:00Z",
            released_reason="removed_by_client",
        )
        self.assertTrue(eb.is_seat_billable(seat, period_start, period_end))

    def test_billable_seats_for_client_filters_injected_seats(self):
        period_start, period_end = JULY
        seats = [
            make_seat("a", "active", activated_at="2026-01-01T00:00:00Z"),
            make_seat("b", "active", activated_at="2026-07-10T00:00:00Z"),  # new this month
            make_seat("c", "waiting", activated_at="2026-01-01T00:00:00Z"),
            make_seat("d", "pending"),
        ]
        billable = eb.billable_seats_for_client(CLIENT_ID, period_start, period_end, seats=seats)
        self.assertEqual([s["id"] for s in billable], ["a"])



class InvoiceAmountTests(unittest.TestCase):
    def test_matches_acceptance_formula_seats_times_unit_price_times_1_05(self):
        amounts = eb.compute_invoice_amounts(45, 3000)
        self.assertEqual(amounts["subtotalTwd"], 135000)
        self.assertEqual(amounts["taxTwd"], 6750)
        self.assertEqual(amounts["totalTwd"], 141750)
        self.assertEqual(amounts["totalTwd"], round(45 * 3000 * 1.05))

    def test_subtotal_plus_tax_always_equals_total(self):
        for seats, price in ((1, 999), (7, 1250), (13, 3333), (0, 5000)):
            amounts = eb.compute_invoice_amounts(seats, price)
            self.assertEqual(amounts["subtotalTwd"] + amounts["taxTwd"], amounts["totalTwd"])

    def test_zero_billable_seats_yields_zero_total(self):
        amounts = eb.compute_invoice_amounts(0, 3000)
        self.assertEqual(amounts["totalTwd"], 0)


class InvoiceNoTests(unittest.TestCase):
    def test_format_is_MU_yyyymm_clientcode(self):
        client = make_client()
        period_start, _ = JULY
        invoice_no = eb.generate_invoice_no(client, period_start)
        expected_code = eb.derive_client_code(client)
        self.assertEqual(invoice_no, f"MU-202607-{expected_code}")
        self.assertTrue(invoice_no.startswith("MU-202607-"))


class OverdueAndOutstandingTests(unittest.TestCase):
    def test_overdue_days_zero_when_paid(self):
        invoice = {"status": "issued", "dueDate": "2026-06-15", "paidAt": "2026-06-20T00:00:00Z", "totalTwd": 1000}
        self.assertEqual(eb.compute_overdue_days(invoice, today=date(2026, 7, 20)), 0)

    def test_overdue_days_zero_when_still_draft(self):
        invoice = {"status": "draft", "dueDate": "2026-06-15", "totalTwd": 1000}
        self.assertEqual(eb.compute_overdue_days(invoice, today=date(2026, 7, 20)), 0)

    def test_overdue_days_counts_from_due_date_when_unpaid_issued(self):
        invoice = {"status": "issued", "dueDate": "2026-06-15", "paidAt": None, "totalTwd": 1000}
        self.assertEqual(eb.compute_overdue_days(invoice, today=date(2026, 7, 20)), 35)

    def test_outstanding_total_sums_only_issued_unpaid(self):
        invoices = [
            {"status": "issued", "paidAt": None, "totalTwd": 1000},
            {"status": "issued", "paidAt": "2026-07-01T00:00:00Z", "totalTwd": 2000},
            {"status": "draft", "paidAt": None, "totalTwd": 5000},
            {"status": "issued", "paidAt": None, "totalTwd": 3000},
        ]
        self.assertEqual(eb.compute_outstanding_total(invoices), 4000)

    def test_client_overdue_days_takes_the_worst_unpaid_invoice(self):
        invoices = [
            {"status": "issued", "dueDate": "2026-07-10", "paidAt": None, "totalTwd": 1000},
            {"status": "issued", "dueDate": "2026-06-01", "paidAt": None, "totalTwd": 2000},
        ]
        self.assertEqual(eb.client_overdue_days(CLIENT_ID, invoices=invoices, today=date(2026, 7, 20)), 49)

    def test_is_client_blocked_for_report_at_7_days_boundary(self):
        exactly_7 = [{"status": "issued", "dueDate": "2026-07-13", "paidAt": None, "totalTwd": 1000}]
        under_7 = [{"status": "issued", "dueDate": "2026-07-14", "paidAt": None, "totalTwd": 1000}]
        self.assertTrue(eb.is_client_blocked_for_report(CLIENT_ID, invoices=exactly_7, today=date(2026, 7, 20)))
        self.assertFalse(eb.is_client_blocked_for_report(CLIENT_ID, invoices=under_7, today=date(2026, 7, 20)))


class InvoiceGenerationAndPersistenceTests(unittest.TestCase):
    def test_build_invoice_draft_only_counts_billable_seats(self):
        period_start, period_end = JULY
        client = make_client(unitPriceTwd=3000)
        seats = [
            make_seat("a", "active", activated_at="2026-01-01T00:00:00Z"),
            make_seat("b", "active", activated_at="2026-07-10T00:00:00Z"),
            make_seat("c", "waiting", activated_at="2026-01-01T00:00:00Z"),
        ]
        draft = eb.build_invoice_draft(client, seats, period_start, period_end)
        self.assertEqual(draft["billableSeats"], 1)
        self.assertEqual(draft["subtotalTwd"], 3000)
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["dueDate"], "2026-08-15")
        self.assertEqual(len(draft["seatSnapshot"]), 1)
        self.assertEqual(draft["seatSnapshot"][0]["seatId"], "a")
        # 去識別化：快照不准帶 email／姓名
        self.assertNotIn("inviteEmail", draft["seatSnapshot"][0])

    def test_generate_monthly_invoice_persists_and_is_retrievable(self):
        period_start, period_end = JULY
        client = make_client(unitPriceTwd=3000)
        seats = [make_seat("a", "active", activated_at="2026-01-01T00:00:00Z")]
        saved = eb.generate_monthly_invoice(client, seats, period_start, period_end)
        self.assertTrue(saved["id"])
        fetched = eb.get_invoice(saved["id"])
        self.assertEqual(fetched["invoiceNo"], saved["invoiceNo"])
        by_no = eb.get_invoice_by_no(saved["invoiceNo"])
        self.assertEqual(by_no["id"], saved["id"])

    def test_rerunning_monthly_close_same_period_does_not_duplicate_invoice(self):
        period_start, period_end = JULY
        client = make_client(unitPriceTwd=3000)
        seats = [make_seat("a", "active", activated_at="2026-01-01T00:00:00Z")]
        first = eb.generate_monthly_invoice(client, seats, period_start, period_end)
        second = eb.generate_monthly_invoice(client, seats, period_start, period_end)
        self.assertEqual(first["invoiceNo"], second["invoiceNo"])
        matches = [i for i in eb.list_invoices(client_id=CLIENT_ID) if i["invoiceNo"] == first["invoiceNo"]]
        self.assertEqual(len(matches), 1)



def six_active_seats():
    period_start, _ = JULY
    return [
        make_seat(f"seat{i}", "active", activated_at="2026-01-01T00:00:00Z", account_id=f"acct{i}")
        for i in range(6)
    ]


def raw_metrics_for(account_ids):
    daily_rows = []
    voice_rows = []
    for idx, aid in enumerate(account_ids):
        daily_rows.append({
            "account_id": aid, "metric_date": "2026-07-05",
            "meaningful_companion_day": idx % 2 == 0,
            "voice_sessions": 2, "voice_minutes": 20,
        })
        daily_rows.append({
            "account_id": aid, "metric_date": "2026-07-12",
            "meaningful_companion_day": True,
            "voice_sessions": 1, "voice_minutes": 8,
        })
        voice_rows.append({"account_id": aid, "started_at": "2026-07-05T10:00:00Z", "duration_ms": 600000})
    reminder_rows = []
    safety_rows = []
    family_rows = []
    if len(account_ids) > 0:
        reminder_rows.append({"account_id": account_ids[0], "event_type": "sent", "event_time": "2026-07-02T09:00:00Z"})
        reminder_rows.append({"account_id": account_ids[0], "event_type": "completed", "event_time": "2026-07-02T09:05:00Z"})
        safety_rows.append({"account_id": account_ids[0], "status": "resolved", "created_at": "2026-07-06T00:00:00Z"})
        family_rows.append({"account_id": account_ids[0], "event_type": "safety_notification_sent", "event_time": "2026-07-06T01:00:00Z"})
    if len(account_ids) > 1:
        reminder_rows.append({"account_id": account_ids[1], "event_type": "sent", "event_time": "2026-07-03T09:00:00Z"})
        reminder_rows.append({"account_id": account_ids[1], "event_type": "missed", "event_time": "2026-07-03T09:00:00Z"})
        safety_rows.append({"account_id": account_ids[1], "status": "notified", "created_at": "2026-07-07T00:00:00Z"})
        family_rows.append({"account_id": account_ids[1], "event_type": "safety_notification_sent", "event_time": "2026-07-07T01:00:00Z"})
    if len(account_ids) > 2:
        safety_rows.append({"account_id": account_ids[2], "status": "open", "created_at": "2026-07-08T00:00:00Z"})
        family_rows.append({"account_id": account_ids[2], "event_type": "message_sent", "event_time": "2026-07-08T01:00:00Z"})
    return {
        "dailyUserMetrics": daily_rows,
        "voiceSessionMetrics": voice_rows,
        "reminderEvents": reminder_rows,
        "familyInteractionEvents": family_rows,
        "safetyEvents": safety_rows,
    }


class ESGReportSuppressionTests(unittest.TestCase):
    def test_cohort_of_6_shows_real_numbers(self):
        period_start, period_end = JULY
        client = make_client(seatQuota=10)
        seats = six_active_seats()
        account_ids = [s["accountId"] for s in seats]
        report = eb.build_esg_report(
            client, seats, period_start, period_end,
            invoices=[], raw_metrics=raw_metrics_for(account_ids),
        )
        companionship = report["sections"]["companionship"]
        self.assertFalse(companionship["suppressed"])
        self.assertEqual(companionship["sampleSize"], 6)
        self.assertIsNotNone(companionship["avgWeeklyCallCount"])
        care = report["sections"]["care"]
        self.assertFalse(care["suppressed"])
        self.assertEqual(care["reminderCompletionRate"], 0.5)  # 1 completed / 2 sent
        self.assertEqual(care["anomaliesCaughtInTime"], 1)
        family = report["sections"]["familyValue"]
        self.assertFalse(family["suppressed"])
        self.assertEqual(family["familiesNotifiedRatio"], round(2 / 6, 4))
        coverage = report["sections"]["coverage"]
        self.assertEqual(coverage["activeSeats"], 6)
        self.assertFalse(coverage["lowUtilizationFlag"])  # 6/10 = 60% >= 50%

    def test_cohort_under_5_suppresses_behavioural_sections_but_keeps_coverage(self):
        period_start, period_end = JULY
        client = make_client(seatQuota=10)
        seats = [
            make_seat(f"seat{i}", "active", activated_at="2026-01-01T00:00:00Z", account_id=f"acct{i}")
            for i in range(3)
        ]
        account_ids = [s["accountId"] for s in seats]
        report = eb.build_esg_report(
            client, seats, period_start, period_end,
            invoices=[], raw_metrics=raw_metrics_for(account_ids),
        )
        for key in ("companionship", "care", "familyValue"):
            section = report["sections"][key]
            self.assertTrue(section["suppressed"], f"{key} should be suppressed with cohort<5")
            for field, value in section.items():
                if field in ("sampleSize", "suppressed"):
                    continue
                self.assertIsNone(value, f"{key}.{field} should be None when suppressed")
        # 涵蓋與參與是合約層級數字，即使 cohort < 5 仍然照常呈現（不受規則 3 限制）
        coverage = report["sections"]["coverage"]
        self.assertEqual(coverage["activeSeats"], 3)
        # 一個違反規則 3 的報告不該通過隱私鐵律；正確遮蔽過的報告要能通過
        eb.enforce_privacy_guard(report)

    def test_low_utilization_flag_below_50_percent(self):
        period_start, period_end = JULY
        client = make_client(seatQuota=10)
        seats = [
            make_seat(f"seat{i}", "active", activated_at="2026-01-01T00:00:00Z", account_id=f"acct{i}")
            for i in range(4)
        ]
        account_ids = [s["accountId"] for s in seats]
        report = eb.build_esg_report(
            client, seats, period_start, period_end,
            invoices=[], raw_metrics=raw_metrics_for(account_ids),
        )
        self.assertTrue(report["sections"]["coverage"]["lowUtilizationFlag"])  # 4/10 = 40%


class ESGReportOverdueBlockTests(unittest.TestCase):
    def test_overdue_7_days_or_more_blocks_report_but_invoice_still_generated(self):
        period_start, period_end = JULY
        client = make_client(unitPriceTwd=3000)
        seats = [make_seat("a", "active", activated_at="2026-01-01T00:00:00Z")]
        overdue_invoices = [{"status": "issued", "dueDate": "2026-07-10", "paidAt": None, "totalTwd": 5000}]
        result = eb.run_monthly_close_for_client(
            client, seats, period_start, period_end,
            existing_invoices=overdue_invoices, today=date(2026, 7, 20), persist_invoice=False,
        )
        self.assertIsNotNone(result["invoice"])
        self.assertEqual(result["invoice"]["billableSeats"], 1)
        self.assertIsNone(result["report"])
        self.assertEqual(result["reportBlocked"]["reason"], "overdue")
        self.assertEqual(result["reportBlocked"]["overdueDays"], 10)

    def test_not_yet_overdue_produces_report_normally(self):
        period_start, period_end = JULY
        client = make_client(unitPriceTwd=3000, seatQuota=1)
        seats = [make_seat("a", "active", activated_at="2026-01-01T00:00:00Z")]
        recent_invoices = [{"status": "issued", "dueDate": "2026-07-18", "paidAt": None, "totalTwd": 5000}]
        result = eb.run_monthly_close_for_client(
            client, seats, period_start, period_end,
            existing_invoices=recent_invoices, today=date(2026, 7, 20), persist_invoice=False,
            raw_metrics=raw_metrics_for(["a"]),
        )
        self.assertIsNotNone(result["report"])
        self.assertIsNone(result["reportBlocked"])



def valid_report_fixture(cohort_size=6):
    period_start, period_end = JULY
    client = make_client(seatQuota=10)
    seats = [
        make_seat(f"seat{i}", "active", activated_at="2026-01-01T00:00:00Z", account_id=f"acct{i}")
        for i in range(cohort_size)
    ]
    account_ids = [s["accountId"] for s in seats]
    return eb.build_esg_report(
        client, seats, period_start, period_end,
        invoices=[], raw_metrics=raw_metrics_for(account_ids),
    )


class PrivacyGuardCleanPassTests(unittest.TestCase):
    """對照組：正確組出來的報告（不管有沒有觸發遮蔽）都應該順利通過，不誤殺。"""

    def test_well_formed_report_with_enough_cohort_passes(self):
        report = valid_report_fixture(cohort_size=6)
        self.assertTrue(eb.enforce_privacy_guard(report))

    def test_well_formed_report_with_small_cohort_passes(self):
        report = valid_report_fixture(cohort_size=2)
        self.assertTrue(eb.enforce_privacy_guard(report))


class PrivacyGuardRule1NameLeakTests(unittest.TestCase):
    """規則 1：不得含任何長輩姓名、帳號識別、聯絡方式——故意塞一個長輩姓名欄位，應被擋下。"""

    def test_resident_name_field_is_blocked(self):
        report = copy.deepcopy(valid_report_fixture())
        report["sections"]["coverage"]["residentName"] = "王小明"
        with self.assertRaises(eb.PrivacyViolationError) as ctx:
            eb.enforce_privacy_guard(report)
        self.assertIn("規則1", str(ctx.exception))

    def test_raw_account_id_leaked_into_wrong_field_is_blocked(self):
        report = copy.deepcopy(valid_report_fixture())
        # 把一個帳號 UUID 錯塞進不該放識別碼的欄位（不是 id 欄位）
        report["sections"]["companionship"]["debugAccountRef"] = "acct-11111111-1111-4111-8111-111111111111"
        with self.assertRaises(eb.PrivacyViolationError):
            eb.enforce_privacy_guard(report)


class PrivacyGuardRule2ConversationLeakTests(unittest.TestCase):
    """規則 2：不得含任何對話內容或摘要片段——故意塞一段對話摘要，應被擋下。"""

    def test_conversation_summary_field_is_blocked(self):
        report = copy.deepcopy(valid_report_fixture())
        report["sections"]["companionship"]["conversationSummary"] = "長輩今天說想念孫子，情緒穩定，聊了半小時。"
        with self.assertRaises(eb.PrivacyViolationError) as ctx:
            eb.enforce_privacy_guard(report)
        self.assertIn("規則2", str(ctx.exception))

    def test_long_free_text_in_unexpected_field_is_blocked(self):
        report = copy.deepcopy(valid_report_fixture())
        long_text = "這是一段超過一百個字的可疑文字內容，" * 10
        report["sections"]["care"]["extraDebugNote"] = long_text
        with self.assertRaises(eb.PrivacyViolationError):
            eb.enforce_privacy_guard(report)


class PrivacyGuardRule3SmallGroupTests(unittest.TestCase):
    """規則 3：分組人數 < 5 時不單獨呈現——故意讓一個小樣本區塊宣稱沒有被遮蔽，應被擋下。"""

    def test_small_sample_claimed_unsuppressed_is_blocked(self):
        report = copy.deepcopy(valid_report_fixture(cohort_size=6))
        report["sections"]["companionship"]["sampleSize"] = 3
        report["sections"]["companionship"]["suppressed"] = False
        with self.assertRaises(eb.PrivacyViolationError) as ctx:
            eb.enforce_privacy_guard(report)
        self.assertIn("規則3", str(ctx.exception))

    def test_correctly_suppressed_small_sample_passes(self):
        report = copy.deepcopy(valid_report_fixture(cohort_size=3))
        # build_esg_report 本來就會正確標記 suppressed=True，這裡只是再次確認守門有放行
        self.assertTrue(report["sections"]["companionship"]["suppressed"])
        self.assertTrue(eb.enforce_privacy_guard(report))


class PrivacyGuardRule4IndividualListTests(unittest.TestCase):
    """規則 4：只准彙總數字與比例——故意塞一份逐人清單，應被擋下。"""

    def test_per_person_breakdown_list_is_blocked(self):
        report = copy.deepcopy(valid_report_fixture())
        report["sections"]["care"]["perPersonBreakdown"] = [
            {"personRef": "p1", "completedCount": 3},
            {"personRef": "p2", "completedCount": 1},
        ]
        with self.assertRaises(eb.PrivacyViolationError) as ctx:
            eb.enforce_privacy_guard(report)
        self.assertIn("規則4", str(ctx.exception))



class HtmlRenderingTests(unittest.TestCase):
    def test_render_invoice_html_contains_key_figures(self):
        period_start, period_end = JULY
        client = make_client(unitPriceTwd=3000)
        seats = [make_seat("a", "active", activated_at="2026-01-01T00:00:00Z")]
        invoice = eb.build_invoice_draft(client, seats, period_start, period_end)
        rendered = eb.render_invoice_html(invoice, client)
        self.assertIn("<!DOCTYPE html>", rendered)
        self.assertIn(invoice["invoiceNo"], rendered)
        self.assertIn("測試股份有限公司", rendered)
        self.assertIn(eb._fmt_money(invoice["totalTwd"]), rendered)
        self.assertIn("草稿", rendered)  # draft 狀態要有標記，避免被誤當正式單據寄出

    def test_render_invoice_html_escapes_client_name(self):
        client = make_client(name="<script>alert(1)</script>")
        period_start, period_end = JULY
        seats = []
        invoice = eb.build_invoice_draft(client, seats, period_start, period_end)
        rendered = eb.render_invoice_html(invoice, client)
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_render_esg_report_html_runs_privacy_guard_and_renders(self):
        report = valid_report_fixture(cohort_size=6)
        rendered = eb.render_esg_report_html(report)
        self.assertIn("<!DOCTYPE html>", rendered)
        self.assertIn("測試股份有限公司", rendered)
        self.assertIn("ESG 成效月報", rendered)

    def test_render_esg_report_html_blocks_on_tampered_report(self):
        report = copy.deepcopy(valid_report_fixture(cohort_size=6))
        report["sections"]["coverage"]["residentName"] = "王小明"
        with self.assertRaises(eb.PrivacyViolationError):
            eb.render_esg_report_html(report)


class MonthlyCloseBatchTests(unittest.TestCase):
    def test_run_monthly_close_produces_invoice_and_report_per_client(self):
        client_a = make_client(id="aaaaaaaa-1111-4111-8111-111111111111", name="甲公司", unitPriceTwd=3000, seatQuota=10)
        client_b = make_client(id="bbbbbbbb-2222-4222-8222-222222222222", name="乙公司（逾期）", unitPriceTwd=2000, seatQuota=5)
        seats_by_client = {
            client_a["id"]: [
                make_seat(f"a{i}", "active", activated_at="2026-01-01T00:00:00Z", account_id=f"a-acct{i}")
                for i in range(6)
            ],
            client_b["id"]: [
                make_seat("b0", "active", activated_at="2026-01-01T00:00:00Z", account_id="b-acct0"),
            ],
        }

        def fake_list_seats(client_id=None, **kwargs):
            return seats_by_client.get(client_id, [])

        original_list_seats = eb.enterprise_seats.list_seats
        eb.enterprise_seats.list_seats = fake_list_seats
        try:
            for cid, seats in seats_by_client.items():
                for seat in seats:
                    eb.gather_esg_metrics  # sanity import touch (no-op)
            results = eb.run_monthly_close(
                period_start=JULY[0], period_end=JULY[1],
                clients=[client_a, client_b], persist_invoice=False,
            )
        finally:
            eb.enterprise_seats.list_seats = original_list_seats

        self.assertIn(client_a["id"], results)
        self.assertIn(client_b["id"], results)
        result_a = results[client_a["id"]]
        self.assertEqual(result_a["invoice"]["billableSeats"], 6)
        self.assertEqual(result_a["invoice"]["totalTwd"], round(6 * 3000 * 1.05))
        self.assertIsNotNone(result_a["report"])
        self.assertIsNone(result_a["reportBlocked"])

        result_b = results[client_b["id"]]
        self.assertEqual(result_b["invoice"]["billableSeats"], 1)
        # 乙公司沒有帶任何逾期發票資料進來（existing_invoices 沒給 → 內部會去查 list_invoices，
        # 在乾淨的本機 store 裡查不到任何 issued 單 → 視為未逾期），報告應正常產出。
        self.assertIsNotNone(result_b["report"])



class FakeSupabaseBackend:
    """假造一個『Supabase 已連線』的 backend，驗證 5.2 六個收款欄位真的會被送進
    payload（不是被 _invoice_item_to_supabase_row 過濾掉），也真的能從『回傳的 row』
    讀回來。不接真的網路，但走的是跟正式環境一樣的 save_invoice() → _upsert_invoice_remote()
    → backend._request() 這條路，不是本地 JSON 備援在幫忙掩護。"""

    def __init__(self):
        self._rows_by_invoice_no = {}
        self.last_payload = None

    def enabled(self):
        return True

    def _is_uuid(self, value):
        return isinstance(value, str) and len(value) == 36 and value.count("-") == 4

    def _request(self, method, table, query=None, payload=None, prefer=None):
        assert table == "enterprise_invoices"
        assert method == "POST"
        self.last_payload = dict(payload)
        row = dict(payload)
        row.setdefault("id", "99999999-9999-4999-8999-999999999999")
        row.setdefault("created_at", "2026-07-20T00:00:00Z")
        row["updated_at"] = "2026-07-20T00:00:00Z"
        self._rows_by_invoice_no[row["invoice_no"]] = row
        return [row]

    def _select(self, table, query):
        assert table == "enterprise_invoices"
        return list(self._rows_by_invoice_no.values())

    def _first(self, table, query):
        rows = self._select(table, query)
        return rows[0] if rows else None


class InvoiceSupabaseFieldRoundTripTests(unittest.TestCase):
    """需求單 5.2：確認六個收款欄位真的能寫進 Supabase payload、也真的讀得回來。"""

    def test_invoice_status_enum_includes_invoiced(self):
        self.assertIn("invoiced", eb.INVOICE_STATUSES)

    def test_unset_payment_fields_send_null_not_zero_or_missing(self):
        period_start, period_end = JULY
        client = make_client(unitPriceTwd=3000)
        seats = [make_seat("a", "active", activated_at="2026-01-01T00:00:00Z")]
        draft = eb.build_invoice_draft(client, seats, period_start, period_end)
        row = eb._invoice_item_to_supabase_row(draft)
        for column in ("sent_at", "paid_at", "paid_amount_twd", "payment_note",
                       "invoice_number", "invoice_issued_at"):
            self.assertIn(column, row, f"{column} 不該從 payload 消失")
            self.assertIsNone(row[column], f"{column} 未設值時應送 null，不是 0 或空字串")

    def test_five_two_fields_round_trip_through_fake_supabase_backend(self):
        period_start, period_end = JULY
        client = make_client(unitPriceTwd=3000)
        seats = [make_seat("a", "active", activated_at="2026-01-01T00:00:00Z")]
        draft = eb.build_invoice_draft(client, seats, period_start, period_end)
        draft.update({
            "status": "paid",
            "sentAt": "2026-08-01T09:00:00Z",
            "paidAt": "2026-08-10T10:00:00Z",
            "paidAmountTwd": 3150,
            "paymentNote": "匯款帳號末五碼 12345",
            "invoiceNumber": "AB12345678",
            "invoiceIssuedAt": "2026-08-11T00:00:00Z",
        })

        fake_backend = FakeSupabaseBackend()
        with patch.object(eb, "_backend", return_value=fake_backend):
            saved = eb.save_invoice(draft)

            # 送出去的 payload 真的帶了六欄，型別／值都對得上
            self.assertEqual(fake_backend.last_payload["sent_at"], "2026-08-01T09:00:00Z")
            self.assertEqual(fake_backend.last_payload["paid_at"], "2026-08-10T10:00:00Z")
            self.assertEqual(fake_backend.last_payload["paid_amount_twd"], 3150)
            self.assertEqual(fake_backend.last_payload["payment_note"], "匯款帳號末五碼 12345")
            self.assertEqual(fake_backend.last_payload["invoice_number"], "AB12345678")
            self.assertEqual(fake_backend.last_payload["invoice_issued_at"], "2026-08-11T00:00:00Z")

            # save_invoice() 回傳值（已經過 _invoice_row_to_item 正規化）六欄都讀得回來
            self.assertEqual(saved["sentAt"], "2026-08-01T09:00:00Z")
            self.assertEqual(saved["paidAt"], "2026-08-10T10:00:00Z")
            self.assertEqual(saved["paidAmountTwd"], 3150)
            self.assertEqual(saved["paymentNote"], "匯款帳號末五碼 12345")
            self.assertEqual(saved["invoiceNumber"], "AB12345678")
            self.assertEqual(saved["invoiceIssuedAt"], "2026-08-11T00:00:00Z")
            self.assertEqual(saved["status"], "paid")

            # 再走一次 list_invoices()／get_invoice()（同一個假 backend），確認查詢路徑也讀得回來
            fetched = eb.get_invoice(saved["id"])
            self.assertEqual(fetched["paidAmountTwd"], 3150)
            self.assertEqual(fetched["invoiceNumber"], "AB12345678")
            listed = eb.list_invoices(client_id=CLIENT_ID)
            self.assertTrue(any(i["invoiceNo"] == draft["invoiceNo"] and i["paidAt"] == "2026-08-10T10:00:00Z" for i in listed))

    def test_zero_is_a_valid_paid_amount_and_is_not_confused_with_unset(self):
        """paid_amount_twd 的 check 是 >= 0，0 是合法值（例如全額折讓／贈送），
        不該被 item.get(...) or 0 這種寫法誤判成『沒填』。"""
        period_start, period_end = JULY
        client = make_client(unitPriceTwd=3000)
        seats = [make_seat("a", "active", activated_at="2026-01-01T00:00:00Z")]
        draft = eb.build_invoice_draft(client, seats, period_start, period_end)
        draft["paidAmountTwd"] = 0
        row = eb._invoice_item_to_supabase_row(draft)
        self.assertEqual(row["paid_amount_twd"], 0)
        self.assertIsNotNone(row["paid_amount_twd"])


if __name__ == "__main__":
    unittest.main()
