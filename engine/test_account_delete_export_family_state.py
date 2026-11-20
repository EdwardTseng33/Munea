#!/usr/bin/env python3
"""刪帳號／下載資料副本 × 家人圈共用狀態（family_state_entries）的守門測試。

兩個對用戶的承諾：
  1. 隱私權政策：「刪除帳號時，雲端保存的健康紀錄會一併刪除」
  2. 設定頁：「對話摘要、提醒與紀錄都屬於你，可建立資料副本」

健康數字（vitals）、緊急聯絡人（safetyContacts）、家人圈名單（circle）存在
family_state_entries，整列掛在「家人圈建立者」的帳號底下，裡面再按 personId 分格。
被邀請進來的人刪自己的帳號時，資料庫的連動刪除只會刪「他帳號底下的列」跟「用外鍵指到他的列」，
摸不到別人那一列 JSON 裡屬於他的那一格——這支測試就是在守那一格。

做法：不連任何真資料庫。用一個記憶體假資料庫接住 SupabaseAdapter._request，
連動刪除規則直接從 supabase/sql/*.sql 的外鍵宣告讀出來（不是手抄），
所以「資料庫自己會刪什麼、不會刪什麼」跟程式庫裡的遷移檔一致。
⚠ 假資料庫不是真的 Postgres：只在假資料上驗過，沒有對真資料庫驗。
"""
import copy
import glob
import json
import os
import re
import sys
import unittest
import uuid

sys.path.insert(0, os.path.dirname(__file__))

from supabase_adapter import FamilyStateCleanupError, SupabaseAdapter, SupabaseRequestError

SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "supabase", "sql")

ACCOUNT_A = "a0000000-0000-4000-8000-00000000000a"   # 圈主 A 的帳號
ACCOUNT_B = "b0000000-0000-4000-8000-00000000000b"   # 被邀請者 B 的帳號
ACCOUNT_C = "c0000000-0000-4000-8000-00000000000c"   # 另一位圈主 C 的帳號
PERSON_A = "a1111111-1111-4111-8111-11111111111a"
PERSON_B = "b1111111-1111-4111-8111-11111111111b"
PERSON_C = "c1111111-1111-4111-8111-11111111111c"
AUTH_A = "a2222222-2222-4222-8222-22222222222a"
AUTH_B = "b2222222-2222-4222-8222-22222222222b"
AUTH_C = "c2222222-2222-4222-8222-22222222222c"
GROUP_A = "a3333333-3333-4333-8333-33333333333a"     # A 建的家人圈（B 被邀進來）
GROUP_B = "b3333333-3333-4333-8333-33333333333b"     # B 自己帳號的家人圈
GROUP_C = "c3333333-3333-4333-8333-33333333333c"     # C 建的家人圈

ENV = {
    "MUNEA_DATABASE_PROVIDER": "supabase",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
}

# 只會出現在 A／C 資料裡的記號，用來抓「B 的副本有沒有誤帶別人的資料」。
A_ONLY_MARKERS = ("圈主阿明", "A-ONLY-STEPS-4321", "A-ONLY-MED-脈優")
C_ONLY_MARKERS = ("圈主阿城", "C-ONLY-STEPS-1357")


def parse_foreign_keys():
    """從遷移檔讀出 {被指到的表: [(表, 欄位, 刪除時怎麼辦)]}。"""
    create_re = re.compile(r"create table if not exists public\.(\w+)\s*\((.*?)\n\);", re.S | re.I)
    column_re = re.compile(
        r"^\s*(\w+)\s+\w+[^,\n]*?references\s+public\.(\w+)\s*\(\s*\w+\s*\)(?:\s+on delete (cascade|set null|restrict))?",
        re.I | re.M,
    )
    alter_re = re.compile(
        r"alter table public\.(\w+)\s+add column if not exists\s+(\w+)\s+\w+[^;]*?references\s+public\.(\w+)\s*\(\s*\w+\s*\)"
        r"(?:\s+on delete (cascade|set null|restrict))?",
        re.I,
    )
    fks = {}
    for path in sorted(glob.glob(os.path.join(SQL_DIR, "*.sql"))):
        with open(path, encoding="utf-8") as handle:
            sql = handle.read()
        for table, body in create_re.findall(sql):
            for column, ref_table, action in column_re.findall(body):
                fks.setdefault(ref_table, set()).add((table, column, (action or "restrict").lower()))
        for table, column, ref_table, action in alter_re.findall(sql):
            fks.setdefault(ref_table, set()).add((table, column, (action or "restrict").lower()))
    return fks


class FakeSupabase:
    """記憶體假資料庫：只做這支測試用得到的 PostgREST 行為（eq／neq／in／is.null 篩選、
    新增、修改、刪除＋照外鍵連動）。遇到不認得的篩選語法直接報錯，不默默當成「全部符合」。"""

    IGNORED_QUERY_KEYS = {"select", "order", "limit", "on_conflict"}

    def __init__(self):
        self.tables = {}
        self.fks = parse_foreign_keys()
        self.log = []
        self.fail_on = None   # (method, table) → 模擬那一步失敗
        self.hooks = []       # hook(phase, method, table, query, payload)；phase＝"before"／"after"
        self._clock = 0

    def seed(self, table, *rows):
        for row in rows:
            row = copy.deepcopy(row)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("updated_at", self._tick())
            self.tables.setdefault(table, []).append(row)
        return self

    def rows(self, table, **equals):
        return [copy.deepcopy(r) for r in self.tables.get(table, []) if all(r.get(k) == v for k, v in equals.items())]

    def _tick(self):
        self._clock += 1
        return f"2026-11-17T00:00:{self._clock:02d}.000000+00:00"

    def _matches(self, row, query):
        for key, cond in (query or {}).items():
            if key in self.IGNORED_QUERY_KEYS:
                continue
            value = row.get(key)
            if cond.startswith("eq."):
                if str(value) != cond[3:]:
                    return False
            elif cond.startswith("neq."):
                if str(value) == cond[4:]:
                    return False
            elif cond.startswith("in.(") and cond.endswith(")"):
                if str(value) not in cond[4:-1].split(","):
                    return False
            elif cond == "is.null":
                if value is not None:
                    return False
            else:
                raise AssertionError(f"假資料庫不認得的篩選：{key}={cond}")
        return True

    def _delete_row(self, table, row):
        self.tables[table].remove(row)
        for child_table, column, action in sorted(self.fks.get(table, ())):
            for child in list(self.tables.get(child_table, [])):
                if child not in self.tables.get(child_table, []) or child.get(column) != row.get("id"):
                    continue
                if action == "cascade":
                    self._delete_row(child_table, child)
                elif action == "set null":
                    child[column] = None
                else:
                    raise AssertionError(f"{child_table}.{column} 擋住刪除 {table}")

    def other_device_writes(self, group_id, key, value):
        """模擬另一位家人的手機把整份 value 寫上來（資料庫的觸發器會跟著更新 updated_at）。不記進 log。"""
        for row in self.tables["family_state_entries"]:
            if row["family_group_id"] == group_id and row["state_key"] == key:
                row["value"] = copy.deepcopy(value)
                row["updated_at"] = self._tick()

    def request(self, method, table, query=None, payload=None, prefer=None):
        self.log.append((method, table, dict(query or {}), copy.deepcopy(payload)))
        if self.fail_on == (method, table):
            raise RuntimeError(f"simulated failure: {method} {table}")
        for hook in list(self.hooks):
            hook("before", method, table, dict(query or {}), copy.deepcopy(payload))
        result = self._apply(method, table, query, payload)
        for hook in list(self.hooks):
            hook("after", method, table, dict(query or {}), copy.deepcopy(payload))
        return result

    def _apply(self, method, table, query, payload):
        store = self.tables.setdefault(table, [])
        if method == "GET":
            found = [copy.deepcopy(r) for r in store if self._matches(r, query)]
            limit = (query or {}).get("limit")
            return found[: int(limit)] if limit else found
        if method == "POST":
            row = copy.deepcopy(payload)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", self._tick())
            store.append(row)
            return [copy.deepcopy(row)]
        if method == "PATCH":
            changed = []
            for row in store:
                if self._matches(row, query):
                    row.update(copy.deepcopy(payload))
                    row["updated_at"] = self._tick()
                    changed.append(copy.deepcopy(row))
            return changed
        if method == "DELETE":
            doomed = [r for r in store if self._matches(r, query)]
            for row in doomed:
                if row in store:
                    self._delete_row(table, row)
            return [copy.deepcopy(r) for r in doomed]
        raise AssertionError(f"假資料庫不認得的動作：{method}")

    def writes(self, table=None):
        return [(m, t, q, p) for m, t, q, p in self.log if m != "GET" and (table is None or t == table)]


class FakeBackedAdapter(SupabaseAdapter):
    def __init__(self, db, identity):
        super().__init__(env=ENV, identity=identity)
        self.db = db
        self.deleted_auth_users = []

    def _request(self, method, table, query=None, payload=None, prefer=None):
        return self.db.request(method, table, query=query, payload=payload, prefer=prefer)

    def _delete_auth_user(self, auth_user_id):
        self.deleted_auth_users.append(auth_user_id)


def vitals_cell(name, steps_marker, hr):
    return {
        "name": name, "nick": name[-2:], "day": "2026-11-16", "updatedAt": 1794873600000,
        "hr": hr, "steps": steps_marker,
        "log": {"2026-11-15": {"steps": 5000, "hr": hr - 1}, "2026-11-16": {"steps": steps_marker, "hr": hr}},
    }


A_VITALS = vitals_cell("圈主阿明", "A-ONLY-STEPS-4321", 61)
B_VITALS = vitals_cell("被邀請的小芳", "B-STEPS-8765", 88)
C_VITALS = vitals_cell("圈主阿城", "C-ONLY-STEPS-1357", 70)
A_ROSTER = {"name": "圈主阿明", "personId": PERSON_A, "relationship": "爸爸", "init": "明", "tint": "p-ama"}
B_ROSTER = {"name": "被邀請的小芳", "personId": PERSON_B, "relationship": "女兒", "init": "芳", "tint": "p-b"}
C_ROSTER = {"name": "圈主阿城", "personId": PERSON_C, "relationship": "舅舅", "init": "城", "tint": "p-c"}
GRANDPA_ROSTER = {"name": "阿公", "relationship": "阿公", "init": "公", "tint": "p-d"}   # 沒有帳號、只有名字的家人
SHARED_MEDS = [{"id": "med_1", "name": "A-ONLY-MED-脈優", "time": "早上", "days": "長期", "by": ""}]
SHARED_FEED = ["<b>圈主阿明</b>已記錄早上服藥"]


def state_row(account_id, group_id, key, value):
    return {"account_id": account_id, "family_group_id": group_id, "state_key": key, "value": value,
            "updated_by_person_id": None}


def build_db(with_circle_c=False):
    """A 建家人圈、B 被邀進來。B 另有自己帳號的家人圈（每個帳號都有一個）。"""
    db = FakeSupabase()
    db.seed("accounts", {"id": ACCOUNT_A, "name": "A"}, {"id": ACCOUNT_B, "name": "B"})
    db.seed("account_members",
            {"account_id": ACCOUNT_A, "user_id": AUTH_A, "role": "owner", "status": "active"},
            {"account_id": ACCOUNT_B, "user_id": AUTH_B, "role": "owner", "status": "active"})
    db.seed("persons",
            {"id": PERSON_A, "account_id": ACCOUNT_A, "display_name": "圈主阿明", "auth_user_id": AUTH_A},
            {"id": PERSON_B, "account_id": ACCOUNT_B, "display_name": "被邀請的小芳", "auth_user_id": AUTH_B})
    db.seed("family_groups",
            {"id": GROUP_A, "account_id": ACCOUNT_A, "name": "阿明家"},
            {"id": GROUP_B, "account_id": ACCOUNT_B, "name": "小芳家"})
    db.seed("family_memberships",
            {"account_id": ACCOUNT_A, "family_group_id": GROUP_A, "person_id": PERSON_A, "role": "primary_user"},
            {"account_id": ACCOUNT_A, "family_group_id": GROUP_A, "person_id": PERSON_B, "role": "family_contact"},
            {"account_id": ACCOUNT_B, "family_group_id": GROUP_B, "person_id": PERSON_B, "role": "primary_user"})
    # A 的家人圈：健康數字、緊急聯絡人各兩格（A、B 各一），名單三人，另有整家共用的吃藥清單與動態。
    db.seed("family_state_entries",
            state_row(ACCOUNT_A, GROUP_A, "vitals", {PERSON_A: A_VITALS, PERSON_B: B_VITALS}),
            state_row(ACCOUNT_A, GROUP_A, "safetyContacts", {PERSON_A: [PERSON_B], PERSON_B: [PERSON_A]}),
            state_row(ACCOUNT_A, GROUP_A, "circle", [A_ROSTER, B_ROSTER, GRANDPA_ROSTER]),
            state_row(ACCOUNT_A, GROUP_A, "meds", SHARED_MEDS),
            state_row(ACCOUNT_A, GROUP_A, "familyFeed", SHARED_FEED),
            # B 自己帳號的家人圈（加入 A 之前留下的舊數字）
            state_row(ACCOUNT_B, GROUP_B, "vitals", {PERSON_B: vitals_cell("被邀請的小芳", "B-OLD-STEPS-1111", 90)}))
    # 用外鍵指到 B 的資料：資料庫自己會連動刪。
    db.seed("wellbeing_signals", {"account_id": ACCOUNT_B, "person_id": PERSON_B, "family_group_id": GROUP_A, "mood": "steady"})
    db.seed("family_relay_messages",
            {"account_id": ACCOUNT_A, "family_group_id": GROUP_A, "sender_person_id": PERSON_B, "recipient_person_id": PERSON_A, "body": "記得吃藥"},
            {"account_id": ACCOUNT_A, "family_group_id": GROUP_A, "sender_person_id": PERSON_A, "recipient_person_id": PERSON_B, "body": "好"})
    db.seed("routine_reminders",
            {"account_id": ACCOUNT_B, "person_id": PERSON_B, "title": "B-MED-降血壓藥", "reminder_type": "medication"},
            {"account_id": ACCOUNT_A, "person_id": PERSON_A, "title": "A-ONLY-MED-脈優", "reminder_type": "medication"})
    db.seed("notification_settings", {"person_id": PERSON_B, "id": PERSON_B})
    if with_circle_c:
        db.seed("accounts", {"id": ACCOUNT_C, "name": "C"})
        db.seed("account_members", {"account_id": ACCOUNT_C, "user_id": AUTH_C, "role": "owner", "status": "active"})
        db.seed("persons", {"id": PERSON_C, "account_id": ACCOUNT_C, "display_name": "圈主阿城", "auth_user_id": AUTH_C})
        db.seed("family_groups", {"id": GROUP_C, "account_id": ACCOUNT_C, "name": "阿城家"})
        db.seed("family_memberships",
                {"account_id": ACCOUNT_C, "family_group_id": GROUP_C, "person_id": PERSON_C, "role": "primary_user"},
                {"account_id": ACCOUNT_C, "family_group_id": GROUP_C, "person_id": PERSON_B, "role": "family_contact"})
        db.seed("family_state_entries",
                state_row(ACCOUNT_C, GROUP_C, "vitals", {PERSON_C: C_VITALS, PERSON_B: vitals_cell("被邀請的小芳", "B-STEPS-IN-C-2468", 87)}),
                state_row(ACCOUNT_C, GROUP_C, "circle", [C_ROSTER, B_ROSTER]))
    return db


def adapter_for(db, who):
    identity = {
        "A": {"accountId": ACCOUNT_A, "personId": PERSON_A, "familyGroupId": GROUP_A, "authUserId": AUTH_A},
        "B": {"accountId": ACCOUNT_B, "personId": PERSON_B, "familyGroupId": GROUP_A, "authUserId": AUTH_B},
    }[who]
    return FakeBackedAdapter(db, identity)


def state_value(db, group_id, key):
    rows = db.rows("family_state_entries", family_group_id=group_id, state_key=key)
    return rows[0]["value"] if rows else None


def everything_left(db):
    return json.dumps(db.tables, ensure_ascii=False)


class FakeDatabaseSelfCheck(unittest.TestCase):
    """假資料庫自己先驗：外鍵規則真的從遷移檔讀到了，不然後面的結論都不可信。"""

    def test_foreign_keys_are_read_from_migrations(self):
        fks = parse_foreign_keys()
        self.assertIn(("persons", "account_id", "cascade"), fks["accounts"])
        self.assertIn(("family_memberships", "person_id", "cascade"), fks["persons"])
        self.assertIn(("wellbeing_signals", "person_id", "cascade"), fks["persons"])
        self.assertIn(("family_relay_messages", "sender_person_id", "cascade"), fks["persons"])
        self.assertIn(("family_state_entries", "updated_by_person_id", "set null"), fks["persons"])
        self.assertIn(("family_state_entries", "family_group_id", "cascade"), fks["family_groups"])

    def test_unknown_filter_is_rejected_not_ignored(self):
        db = build_db()
        with self.assertRaises(AssertionError):
            db.request("GET", "persons", query={"id": "like.*"})


class MemberDeletesAccountTests(unittest.TestCase):
    """缺口 1：被邀進別人家人圈的人刪帳號。"""

    def delete_b(self, db):
        adapter = adapter_for(db, "B")
        result = adapter.delete_scoped_account(AUTH_B)
        self.assertTrue(result["accountDeleted"])
        self.assertEqual(adapter.deleted_auth_users, [AUTH_B])
        return result

    def test_rows_linked_by_foreign_key_are_already_cascaded(self):
        """成員資格、心情訊號、家人傳話、自己的吃藥提醒：資料庫外鍵本來就會連動刪（這部分缺口不成立）。"""
        db = build_db()
        self.delete_b(db)
        self.assertEqual(db.rows("accounts", id=ACCOUNT_B), [])
        self.assertEqual(db.rows("persons", id=PERSON_B), [])
        self.assertEqual(db.rows("family_memberships", person_id=PERSON_B), [])
        self.assertEqual(db.rows("wellbeing_signals", person_id=PERSON_B), [])
        self.assertEqual(db.rows("family_relay_messages", sender_person_id=PERSON_B), [])
        self.assertEqual(db.rows("family_relay_messages", recipient_person_id=PERSON_B), [])
        self.assertEqual(db.rows("routine_reminders", person_id=PERSON_B), [])
        self.assertEqual(db.rows("notification_settings", person_id=PERSON_B), [])
        self.assertEqual(db.rows("family_state_entries", family_group_id=GROUP_B), [])   # 自己帳號的家人圈整個連動刪

    def test_own_health_cell_is_removed_from_inviters_circle(self):
        """重現缺口：B 刪帳號後，A 的家人圈裡不該還留著 B 的健康數字。"""
        db = build_db()
        self.delete_b(db)
        self.assertNotIn(PERSON_B, state_value(db, GROUP_A, "vitals"))

    def test_own_safety_contact_list_is_removed_from_inviters_circle(self):
        db = build_db()
        self.delete_b(db)
        self.assertNotIn(PERSON_B, state_value(db, GROUP_A, "safetyContacts"))

    def test_own_roster_entry_is_removed_from_inviters_circle(self):
        db = build_db()
        self.delete_b(db)
        roster = state_value(db, GROUP_A, "circle")
        self.assertEqual([m for m in roster if m.get("personId") == PERSON_B], [])

    def test_no_health_data_of_the_deleted_person_is_left_anywhere(self):
        """整個資料庫掃一遍：B 的名字、健康數字、藥名一個字都不該剩。"""
        db = build_db(with_circle_c=True)
        self.delete_b(db)
        left = everything_left(db)
        for marker in ("被邀請的小芳", "B-STEPS-8765", "B-STEPS-IN-C-2468", "B-OLD-STEPS-1111", "B-MED-降血壓藥"):
            self.assertNotIn(marker, left)

    def test_other_members_data_is_untouched(self):
        """反向：A 的資料一格都沒少，整家共用的清單原封不動。"""
        db = build_db()
        before = {key: state_value(db, GROUP_A, key) for key in ("vitals", "safetyContacts", "circle", "meds", "familyFeed")}
        self.delete_b(db)
        self.assertEqual(state_value(db, GROUP_A, "vitals"), {PERSON_A: before["vitals"][PERSON_A]})
        self.assertEqual(state_value(db, GROUP_A, "vitals")[PERSON_A], A_VITALS)
        # A 自己選的緊急聯絡人名單是 A 的設定，不替他改（裡面那個 B 的編號已經對不到人，派送時本來就會濾掉）。
        self.assertEqual(state_value(db, GROUP_A, "safetyContacts"), {PERSON_A: [PERSON_B]})
        self.assertEqual(state_value(db, GROUP_A, "circle"), [A_ROSTER, GRANDPA_ROSTER])
        self.assertEqual(state_value(db, GROUP_A, "meds"), SHARED_MEDS)
        self.assertEqual(state_value(db, GROUP_A, "familyFeed"), SHARED_FEED)
        self.assertEqual(len(db.rows("family_state_entries", family_group_id=GROUP_A)), 5)   # 一列都沒被整列刪掉
        self.assertEqual(len(db.rows("persons", id=PERSON_A)), 1)
        self.assertEqual(len(db.rows("routine_reminders", person_id=PERSON_A)), 1)
        self.assertEqual(len(db.rows("family_memberships", person_id=PERSON_A)), 1)

    def test_only_value_column_of_touched_rows_is_written(self):
        """寫入範圍：只改「有他那一格」的那幾列的 value，一次只對一列（用列編號指定），不整列刪。"""
        db = build_db()
        touched_ids = {r["id"] for r in db.rows("family_state_entries", family_group_id=GROUP_A)
                       if r["state_key"] in ("vitals", "safetyContacts", "circle")}
        self.delete_b(db)
        writes = db.writes("family_state_entries")
        self.assertEqual(len(writes), 3)
        for method, _table, query, payload in writes:
            self.assertEqual(method, "PATCH")
            self.assertEqual(set(payload), {"value"})
            self.assertIn(query["id"][3:], touched_ids)
            self.assertTrue(query["id"].startswith("eq."))
            self.assertTrue(query["updated_at"].startswith("eq.2026-"))   # 寫回一定帶「我讀到的那一版」

    def test_entry_holding_only_this_person_is_emptied_not_broken(self):
        """別人家人圈裡某個條目只剩 B 一格：清成空的，其他條目照舊。"""
        db = build_db()
        for row in db.tables["family_state_entries"]:
            if row["family_group_id"] == GROUP_A and row["state_key"] == "vitals":
                row["value"] = {PERSON_B: B_VITALS}
        self.delete_b(db)
        self.assertEqual(state_value(db, GROUP_A, "vitals"), {})
        self.assertEqual(state_value(db, GROUP_A, "meds"), SHARED_MEDS)

    def test_member_of_two_circles_is_removed_from_both(self):
        db = build_db(with_circle_c=True)
        self.delete_b(db)
        self.assertEqual(state_value(db, GROUP_A, "vitals"), {PERSON_A: A_VITALS})
        self.assertEqual(state_value(db, GROUP_C, "vitals"), {PERSON_C: C_VITALS})
        self.assertEqual(state_value(db, GROUP_C, "circle"), [C_ROSTER])
        self.assertEqual(state_value(db, GROUP_A, "circle"), [A_ROSTER, GRANDPA_ROSTER])

    def test_unrecognised_shapes_are_left_alone(self):
        """形狀認不得（不是預期的物件／清單）就不動——寧可少刪。"""
        db = build_db()
        for row in db.tables["family_state_entries"]:
            if row["family_group_id"] == GROUP_A and row["state_key"] == "vitals":
                row["value"] = [PERSON_B, "不是預期的形狀"]
            if row["family_group_id"] == GROUP_A and row["state_key"] == "circle":
                row["value"] = {"members": [B_ROSTER]}
        self.delete_b(db)
        self.assertEqual(state_value(db, GROUP_A, "vitals"), [PERSON_B, "不是預期的形狀"])
        self.assertEqual(state_value(db, GROUP_A, "circle"), {"members": [B_ROSTER]})
        self.assertNotIn(PERSON_B, state_value(db, GROUP_A, "safetyContacts"))

    def test_cleanup_failure_stops_before_the_account_is_deleted(self):
        """清那一格失敗就整個停下來、帳號不刪——用戶可以再按一次，不會變成「帳號沒了、資料還留著」。"""
        db = build_db()
        db.fail_on = ("PATCH", "family_state_entries")
        adapter = adapter_for(db, "B")
        with self.assertRaises(RuntimeError):
            adapter.delete_scoped_account(AUTH_B)
        self.assertEqual(len(db.rows("accounts", id=ACCOUNT_B)), 1)
        self.assertEqual(adapter.deleted_auth_users, [])
        self.assertEqual([w for w in db.writes() if w[0] == "DELETE"], [])
        # 留痕只有一筆「清理失敗」，沒有「已確認刪除」。
        self.assertEqual([a["event_type"] for a in db.rows("audit_events")],
                         ["account_deletion_family_state_cleanup_failed"])

    def test_read_failure_also_stops_before_the_account_is_deleted(self):
        """連「他待過哪些家人圈、裡面有什麼」都讀不到：一樣停下來，不在看不見的情況下刪帳號。"""
        for table in ("family_memberships", "family_state_entries"):
            db = build_db()
            db.fail_on = ("GET", table)
            adapter = adapter_for(db, "B")
            with self.assertRaises(RuntimeError):
                adapter.delete_scoped_account(AUTH_B)
            self.assertEqual(len(db.rows("accounts", id=ACCOUNT_B)), 1, table)
            # 除了一筆「清理失敗」的留痕，什麼都沒寫。
            self.assertEqual([(m, t) for m, t, _q, _p in db.writes()], [("POST", "audit_events")], table)
            self.assertEqual(db.rows("audit_events")[0]["details"],
                             {"familyStateCellsRemoved": 0, "errorKind": "RuntimeError"}, table)

    def test_environment_without_the_table_can_still_delete(self):
        """舊環境還沒有 family_state_entries 這張表：沒有任何一格可清，刪帳號照常。"""
        db = build_db()
        del db.tables["family_state_entries"]
        original = db.request

        def request(method, table, query=None, payload=None, prefer=None):
            if table == "family_state_entries":
                raise SupabaseRequestError("missing", error_kind="missing_table", status_code=404, error_code="PGRST205")
            return original(method, table, query=query, payload=payload, prefer=prefer)

        db.request = request
        result = adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertTrue(result["accountDeleted"])
        self.assertEqual(result["familyStateCellsRemoved"], 0)
        self.assertEqual(db.rows("accounts", id=ACCOUNT_B), [])
        # 沒清就放行要留痕，不能無聲放行。
        self.assertEqual(result["familyStateCleanupSkipped"], "missing_table")
        self.assertEqual(db.rows("audit_events")[0]["details"]["familyStateCleanupSkipped"], "missing_table")

    def test_audit_record_counts_cells_without_naming_people(self):
        db = build_db(with_circle_c=True)
        result = self.delete_b(db)
        self.assertEqual(result["familyStateCellsRemoved"], 5)   # A 圈 3 格＋C 圈 2 格
        self.assertIsNone(result["familyStateCleanupSkipped"])
        audit = db.rows("audit_events")[0]
        self.assertEqual(audit["details"]["familyStateCellsRemoved"], 5)
        self.assertNotIn("familyStateCleanupSkipped", audit["details"])
        self.assertNotIn(PERSON_A, json.dumps(audit, ensure_ascii=False))
        self.assertNotIn(PERSON_C, json.dumps(audit, ensure_ascii=False))


class ConcurrentWriteTests(unittest.TestCase):
    """別的家人的手機剛好也在寫同一列：不拿舊內容蓋掉人家的新值；清完被寫回來要抓得到。"""

    A_NEW_VITALS = vitals_cell("圈主阿明", "A-NEW-STEPS-9999", 64)

    @staticmethod
    def is_vitals_cleanup_write(method, table, payload):
        """我們對 A 家人圈健康數字那一列的寫回（value 是物件、A 那格是一整份健康數字）。"""
        value = (payload or {}).get("value")
        return (method == "PATCH" and table == "family_state_entries"
                and isinstance(value, dict) and isinstance(value.get(PERSON_A), dict))

    @staticmethod
    def is_roster_cleanup_write(method, table, payload):
        return method == "PATCH" and table == "family_state_entries" and isinstance((payload or {}).get("value"), list)

    def vitals_patches(self, db):
        vitals_id = db.rows("family_state_entries", family_group_id=GROUP_A, state_key="vitals")[0]["id"]
        return [w for w in db.writes("family_state_entries") if w[2]["id"] == f"eq.{vitals_id}"]

    def test_newer_value_written_by_another_member_is_not_overwritten(self):
        """我們先讀、A 的手機寫了新數字、我們才要寫回：寫不進去 → 重讀重算 → A 的新數字還在、B 那格沒了。"""
        db = build_db()
        fired = []

        def a_syncs_just_before_our_write(phase, method, table, query, payload):
            if phase == "before" and not fired and self.is_vitals_cleanup_write(method, table, payload):
                fired.append(True)
                db.other_device_writes(GROUP_A, "vitals", {PERSON_A: self.A_NEW_VITALS, PERSON_B: B_VITALS})

        db.hooks.append(a_syncs_just_before_our_write)
        result = adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertEqual(fired, [True])
        self.assertEqual(state_value(db, GROUP_A, "vitals"), {PERSON_A: self.A_NEW_VITALS})
        self.assertEqual(len(self.vitals_patches(db)), 2)        # 第一次寫不進去、重讀後第二次才寫進去
        self.assertEqual(result["familyStateCellsRemoved"], 3)   # 沒寫進去的那次不算
        self.assertEqual(db.rows("accounts", id=ACCOUNT_B), [])

    def test_cell_written_back_after_cleanup_is_caught_by_recheck(self):
        """A 的手機在我們清之前就讀了舊內容、等我們清完才整份寫回（B 被寫回來）：複查抓到、再清一輪。"""
        db = build_db()
        stale = {PERSON_A: A_VITALS, PERSON_B: B_VITALS}
        fired = []

        def a_writes_stale_copy_right_after_our_write(phase, method, table, query, payload):
            if phase == "after" and not fired and self.is_vitals_cleanup_write(method, table, payload):
                fired.append(True)
                db.other_device_writes(GROUP_A, "vitals", stale)

        db.hooks.append(a_writes_stale_copy_right_after_our_write)
        result = adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertEqual(fired, [True])
        self.assertEqual(state_value(db, GROUP_A, "vitals"), {PERSON_A: A_VITALS})
        self.assertEqual(result["familyStateCellsRemoved"], 4)   # 3 格＋被寫回來重清的 1 次
        self.assertEqual(db.rows("accounts", id=ACCOUNT_B), [])

    def test_roster_written_back_after_cleanup_is_caught_by_recheck(self):
        """圈主手機本機名單還有 B、整份上傳：名單那筆被寫回來，一樣要抓到。"""
        db = build_db()
        fired = []

        def a_uploads_old_roster(phase, method, table, query, payload):
            if phase == "after" and not fired and self.is_roster_cleanup_write(method, table, payload):
                fired.append(True)
                db.other_device_writes(GROUP_A, "circle", [A_ROSTER, B_ROSTER, GRANDPA_ROSTER])

        db.hooks.append(a_uploads_old_roster)
        adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertEqual(fired, [True])
        self.assertEqual(state_value(db, GROUP_A, "circle"), [A_ROSTER, GRANDPA_ROSTER])

    def test_keeps_coming_back_stops_the_deletion(self):
        """每清一次就被寫回來一次：清兩輪還複查得到他 → 停下來、帳號不刪、留一筆失敗紀錄。"""
        db = build_db()
        stale = {PERSON_A: A_VITALS, PERSON_B: B_VITALS}

        def always_written_back(phase, method, table, query, payload):
            if phase == "after" and self.is_vitals_cleanup_write(method, table, payload):
                db.other_device_writes(GROUP_A, "vitals", stale)

        db.hooks.append(always_written_back)
        adapter = adapter_for(db, "B")
        with self.assertRaises(FamilyStateCleanupError) as caught:
            adapter.delete_scoped_account(AUTH_B)
        self.assertEqual(caught.exception.error_kind, "still_present")
        self.assertEqual(len(db.rows("accounts", id=ACCOUNT_B)), 1)
        self.assertEqual(adapter.deleted_auth_users, [])
        self.assertEqual(len(self.vitals_patches(db)), 2)        # 只清兩輪，不無限重試
        audits = db.rows("audit_events")
        self.assertEqual([a["event_type"] for a in audits], ["account_deletion_family_state_cleanup_failed"])
        self.assertEqual(audits[0]["details"], {"familyStateCellsRemoved": 4, "errorKind": "still_present"})

    def test_row_that_never_stops_changing_gives_up_after_three_writes(self):
        """同一列一直有人搶在前面寫：試三次都寫不進去 → 停下來、帳號不刪，而且從頭到尾沒蓋掉人家的內容。"""
        db = build_db()
        counter = []

        def someone_always_writes_first(phase, method, table, query, payload):
            if phase == "before" and self.is_vitals_cleanup_write(method, table, payload):
                counter.append(True)
                newest = vitals_cell("圈主阿明", f"A-NEW-STEPS-{len(counter)}", 64)
                db.other_device_writes(GROUP_A, "vitals", {PERSON_A: newest, PERSON_B: B_VITALS})

        db.hooks.append(someone_always_writes_first)
        adapter = adapter_for(db, "B")
        with self.assertRaises(FamilyStateCleanupError) as caught:
            adapter.delete_scoped_account(AUTH_B)
        self.assertEqual(caught.exception.error_kind, "version_conflict")
        self.assertEqual(len(counter), 3)
        self.assertEqual(len(db.rows("accounts", id=ACCOUNT_B)), 1)
        self.assertEqual(state_value(db, GROUP_A, "vitals")[PERSON_A]["steps"], "A-NEW-STEPS-3")   # 人家最後寫的還在

    def test_row_deleted_while_cleaning_is_not_an_error(self):
        """要寫回時那一列已經不在了（例如圈主同時刪帳號）：沒有東西可清，照常往下。"""
        db = build_db()

        def owner_row_disappears(phase, method, table, query, payload):
            if phase == "before" and self.is_vitals_cleanup_write(method, table, payload):
                db.tables["family_state_entries"] = [
                    r for r in db.tables["family_state_entries"]
                    if not (r["family_group_id"] == GROUP_A and r["state_key"] == "vitals")]

        db.hooks.append(owner_row_disappears)
        result = adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertTrue(result["accountDeleted"])
        self.assertEqual(result["familyStateCellsRemoved"], 2)


class FailureHandlingTests(unittest.TestCase):
    """清到一半失敗：留痕、不夾個資、重按一次會清乾淨。"""

    def fail_on_nth_cleanup_write(self, db, nth, error):
        seen = []

        def hook(phase, method, table, query, payload):
            if phase == "before" and method == "PATCH" and table == "family_state_entries":
                seen.append(True)
                if len(seen) == nth:
                    raise error

        db.hooks.append(hook)
        return hook

    def test_partial_failure_then_retry_cleans_everything(self):
        """第 1 列清掉、第 2 列失敗 → 帳號還在、留痕記 1 格；重按一次 → 剩下 2 格清掉、帳號刪除。"""
        db = build_db()
        hook = self.fail_on_nth_cleanup_write(db, 2, RuntimeError("boom"))
        adapter = adapter_for(db, "B")
        with self.assertRaises(FamilyStateCleanupError) as caught:
            adapter.delete_scoped_account(AUTH_B)
        self.assertEqual(caught.exception.cells_removed, 1)
        self.assertEqual(len(db.rows("accounts", id=ACCOUNT_B)), 1)
        self.assertEqual(db.rows("audit_events")[0]["details"], {"familyStateCellsRemoved": 1, "errorKind": "RuntimeError"})
        left = [key for key in ("vitals", "safetyContacts", "circle")
                if SupabaseAdapter._split_person_from_family_state(key, state_value(db, GROUP_A, key), PERSON_B)[0]]
        self.assertEqual(len(left), 2)   # 真的只清掉了一列

        db.hooks.remove(hook)
        result = adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertTrue(result["accountDeleted"])
        self.assertEqual(result["familyStateCellsRemoved"], 2)   # 第一次已經清掉的那格不重複算
        self.assertEqual(state_value(db, GROUP_A, "vitals"), {PERSON_A: A_VITALS})
        self.assertEqual(state_value(db, GROUP_A, "safetyContacts"), {PERSON_A: [PERSON_B]})
        self.assertEqual(state_value(db, GROUP_A, "circle"), [A_ROSTER, GRANDPA_ROSTER])
        self.assertEqual([a["event_type"] for a in db.rows("audit_events")],
                         ["account_deletion_family_state_cleanup_failed", "account_deletion_confirmed"])
        self.assertEqual(db.rows("audit_events")[1]["details"]["familyStateCellsRemoved"], 2)

    def test_error_and_trail_never_carry_database_error_details(self):
        """資料庫回的錯誤細節可能夾整列健康數字（Failing row contains …）：往上丟的錯誤、留痕都不可以帶。"""
        leaky = SupabaseRequestError(
            "Supabase PATCH family_state_entries failed: 400 Failing row contains "
            "(圈主阿明, A-ONLY-STEPS-4321, 被邀請的小芳, B-STEPS-8765)",
            error_kind="http_error", status_code=400, error_code="23514",
        )
        for where in ("write", "read"):
            db = build_db()
            if where == "write":
                self.fail_on_nth_cleanup_write(db, 1, leaky)
            else:
                def hook(phase, method, table, query, payload, _leaky=leaky):
                    if phase == "before" and method == "GET" and table == "family_state_entries":
                        raise _leaky
                db.hooks.append(hook)
            with self.assertRaises(RuntimeError) as caught:
                adapter_for(db, "B").delete_scoped_account(AUTH_B)
            error = caught.exception
            self.assertEqual(str(error), "account_deletion_family_state_cleanup_failed", where)
            self.assertEqual(error.args, ("account_deletion_family_state_cleanup_failed",), where)
            self.assertIsNone(error.__cause__, where)
            self.assertTrue(error.__suppress_context__, where)     # 追蹤紀錄也不會把底層錯誤印出來
            audit = json.dumps(db.rows("audit_events"), ensure_ascii=False)
            for marker in ("圈主阿明", "A-ONLY-STEPS-4321", "被邀請的小芳", "B-STEPS-8765", "Failing row"):
                self.assertNotIn(marker, audit, where)
            self.assertEqual(db.rows("audit_events")[0]["details"],
                             {"familyStateCellsRemoved": 0, "errorKind": "http_error"}, where)

    def test_trail_write_failure_does_not_hide_the_cleanup_failure(self):
        db = build_db()
        self.fail_on_nth_cleanup_write(db, 1, RuntimeError("boom"))
        db.fail_on = ("POST", "audit_events")
        with self.assertRaises(FamilyStateCleanupError):
            adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertEqual(len(db.rows("accounts", id=ACCOUNT_B)), 1)

    def test_row_without_version_is_not_written_blind(self):
        """讀到的列沒有 updated_at（不該發生）：不做沒有版本比對的寫入，停下來。"""
        db = build_db()
        for row in db.tables["family_state_entries"]:
            row["updated_at"] = None
        with self.assertRaises(FamilyStateCleanupError) as caught:
            adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertEqual(caught.exception.error_kind, "row_unidentified")
        self.assertEqual(db.writes("family_state_entries"), [])


class IdentityFormatTests(unittest.TestCase):
    """本人編號格式不合法：刪帳號這條路要停（跟匯出一致），而且一個查詢都不送。"""

    def bad_identity(self):
        return {"accountId": ACCOUNT_B, "personId": "b1111111' or person_id=neq.x", "familyGroupId": GROUP_A, "authUserId": AUTH_B}

    def test_cleanup_refuses_malformed_person_id_before_any_query(self):
        db = build_db()
        adapter = FakeBackedAdapter(db, self.bad_identity())
        with self.assertRaisesRegex(PermissionError, "account_deletion_identity_mismatch"):
            adapter._remove_own_cells_from_other_family_circles()
        self.assertEqual(db.log, [])

    def test_deletion_stops_on_malformed_person_id(self):
        db = build_db()
        adapter = FakeBackedAdapter(db, self.bad_identity())
        with self.assertRaises((PermissionError, RuntimeError)):
            adapter.delete_scoped_account(AUTH_B)
        self.assertEqual(db.writes(), [])
        self.assertEqual(len(db.rows("accounts", id=ACCOUNT_B)), 1)

    def test_deletion_stops_even_if_the_outer_gate_is_ever_loosened(self):
        """現在最外層的 enabled() 已經會擋；假設哪天它放寬了，清理這一步自己還是要擋。"""
        db = build_db()

        class LooseGateAdapter(FakeBackedAdapter):
            def enabled(self):
                return True

        adapter = LooseGateAdapter(db, self.bad_identity())
        with self.assertRaisesRegex(PermissionError, "account_deletion_identity_mismatch"):
            adapter.delete_scoped_account(AUTH_B)
        self.assertEqual(db.writes(), [])
        self.assertEqual(len(db.rows("accounts", id=ACCOUNT_B)), 1)


class RosterShapeTests(unittest.TestCase):
    """名單那一筆的各種長相。"""

    ID_ONLY_ROSTER = {"name": "被邀請的小芳", "id": PERSON_B, "relationship": "女兒"}   # 只有 id、沒有 personId

    def set_roster(self, db, roster):
        for row in db.tables["family_state_entries"]:
            if row["family_group_id"] == GROUP_A and row["state_key"] == "circle":
                row["value"] = copy.deepcopy(roster)

    def test_roster_entry_with_only_id_is_removed_and_exported(self):
        db = build_db()
        self.set_roster(db, [A_ROSTER, self.ID_ONLY_ROSTER, GRANDPA_ROSTER])
        package = adapter_for(db, "B").export_scoped_personal_data()
        exported = [e["value"] for e in package["personalData"]["familyStateEntries"]
                    if e["familyGroupId"] == GROUP_A and e["stateKey"] == "circle"]
        self.assertEqual(exported, [[self.ID_ONLY_ROSTER]])
        adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertEqual(state_value(db, GROUP_A, "circle"), [A_ROSTER, GRANDPA_ROSTER])

    def test_duplicate_roster_entries_are_all_removed(self):
        db = build_db()
        self.set_roster(db, [B_ROSTER, A_ROSTER, self.ID_ONLY_ROSTER, GRANDPA_ROSTER])
        result = adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertEqual(state_value(db, GROUP_A, "circle"), [A_ROSTER, GRANDPA_ROSTER])
        self.assertEqual(result["familyStateCellsRemoved"], 3)   # 同一列兩筆算一格

    def test_same_name_without_person_id_is_not_touched(self):
        """同名但沒帶編號的那筆不比名字、不動——可能是別人。"""
        db = build_db()
        same_name = {"name": "被邀請的小芳", "relationship": "表妹"}
        self.set_roster(db, [A_ROSTER, B_ROSTER, same_name])
        adapter_for(db, "B").delete_scoped_account(AUTH_B)
        self.assertEqual(state_value(db, GROUP_A, "circle"), [A_ROSTER, same_name])


class CircleOwnerDeletesAccountTests(unittest.TestCase):
    """帳號是家人圈建立者：現行行為（整個家人圈跟著帳號連動刪）維持不變，這次不多寫任何一列。"""

    def test_owner_deletion_keeps_existing_behaviour(self):
        db = build_db()
        adapter = adapter_for(db, "A")
        result = adapter.delete_scoped_account(AUTH_A)
        self.assertTrue(result["accountDeleted"])
        self.assertEqual(result["familyStateCellsRemoved"], 0)
        self.assertEqual(db.writes("family_state_entries"), [])
        self.assertEqual(db.rows("family_state_entries", family_group_id=GROUP_A), [])
        # B 的帳號、B 自己的家人圈都還在
        self.assertEqual(len(db.rows("accounts", id=ACCOUNT_B)), 1)
        self.assertEqual(len(db.rows("family_state_entries", family_group_id=GROUP_B)), 1)

    def test_solo_user_with_only_own_circle_writes_nothing_extra(self):
        """圈裡只有自己一個人（沒被邀進任何人的圈）：跟以前一樣，只有留痕＋刪帳號兩筆寫入。"""
        db = build_db()
        db.tables["family_memberships"] = [m for m in db.tables["family_memberships"]
                                           if not (m["person_id"] == PERSON_B and m["family_group_id"] == GROUP_A)]
        adapter = adapter_for(db, "B")
        adapter.delete_scoped_account(AUTH_B)
        self.assertEqual([(m, t) for m, t, _q, _p in db.writes()], [("POST", "audit_events"), ("DELETE", "accounts")])
        self.assertEqual(db.rows("family_state_entries", family_group_id=GROUP_B), [])


class MemberExportsDataTests(unittest.TestCase):
    """缺口 2：下載我的資料。"""

    def export_b(self, db):
        return adapter_for(db, "B").export_scoped_personal_data()

    def entries(self, package):
        return (package.get("personalData") or {}).get("familyStateEntries") or []

    def entry(self, package, group_id, key):
        found = [e for e in self.entries(package) if e.get("familyGroupId") == group_id and e.get("stateKey") == key]
        self.assertEqual(len(found), 1, f"{group_id} {key} 應該剛好一筆")
        return found[0]

    def test_export_contains_own_health_numbers(self):
        """重現缺口：B 的副本裡要有自己的健康數字。"""
        package = self.export_b(build_db())
        self.assertEqual(self.entry(package, GROUP_A, "vitals")["value"], B_VITALS)

    def test_export_contains_own_safety_contacts_and_roster_entry(self):
        package = self.export_b(build_db())
        self.assertEqual(self.entry(package, GROUP_A, "safetyContacts")["value"], [PERSON_A])
        self.assertEqual(self.entry(package, GROUP_A, "circle")["value"], [B_ROSTER])

    def test_export_contains_own_medication_reminders(self):
        """自己的吃藥提醒存在 routine_reminders（按人分列）：副本本來就有（這部分缺口不成立）。"""
        package = self.export_b(build_db())
        titles = [r["title"] for r in package["personalData"]["routineReminders"]]
        self.assertEqual(titles, ["B-MED-降血壓藥"])

    def test_export_never_carries_other_members_data(self):
        """反向：A、C 的健康數字、名字、藥名一個字都不能出現在 B 的副本。"""
        package = self.export_b(build_db(with_circle_c=True))
        dumped = json.dumps(package, ensure_ascii=False)
        for marker in A_ONLY_MARKERS + C_ONLY_MARKERS:
            self.assertNotIn(marker, dumped)
        for entry in self.entries(package):
            self.assertIn(entry["stateKey"], ("vitals", "safetyContacts", "circle"))   # 整家共用的清單不放

    def test_export_covers_every_circle_the_person_is_in(self):
        package = self.export_b(build_db(with_circle_c=True))
        self.assertEqual(self.entry(package, GROUP_A, "vitals")["value"]["steps"], "B-STEPS-8765")
        self.assertEqual(self.entry(package, GROUP_C, "vitals")["value"]["steps"], "B-STEPS-IN-C-2468")
        self.assertEqual(self.entry(package, GROUP_B, "vitals")["value"]["steps"], "B-OLD-STEPS-1111")
        self.assertEqual(self.entry(package, GROUP_C, "circle")["value"], [B_ROSTER])

    def test_export_for_solo_user_includes_own_circle_numbers(self):
        """圈裡只有自己：自己家人圈裡的健康數字也要在副本裡。"""
        db = build_db()
        db.tables["family_memberships"] = [m for m in db.tables["family_memberships"]
                                           if not (m["person_id"] == PERSON_B and m["family_group_id"] == GROUP_A)]
        package = self.export_b(db)
        self.assertEqual([(e["familyGroupId"], e["stateKey"]) for e in self.entries(package)], [(GROUP_B, "vitals")])

    def test_export_reads_only_and_skips_unrecognised_shapes(self):
        db = build_db()
        for row in db.tables["family_state_entries"]:
            if row["family_group_id"] == GROUP_A and row["state_key"] == "vitals":
                row["value"] = [PERSON_B, "不是預期的形狀"]
        package = self.export_b(db)
        self.assertEqual([e for e in self.entries(package) if e["familyGroupId"] == GROUP_A and e["stateKey"] == "vitals"], [])
        self.assertEqual(db.writes(), [])

    def test_owner_export_does_not_carry_invited_members_cells(self):
        """圈主 A 匯出：只有 A 自己那一格，不會因為整列掛在 A 帳號底下就把 B 的帶出去。"""
        package = adapter_for(build_db(), "A").export_scoped_personal_data()
        dumped = json.dumps(package, ensure_ascii=False)
        for marker in ("被邀請的小芳", "B-STEPS-8765", "B-MED-降血壓藥"):
            self.assertNotIn(marker, dumped)
        self.assertEqual(self.entry(package, GROUP_A, "vitals")["value"], A_VITALS)
        self.assertEqual(self.entry(package, GROUP_A, "safetyContacts")["value"], [PERSON_B])

    def test_export_survives_missing_family_state_table(self):
        """舊環境還沒有這張表：副本照樣建得出來，那一段是空的。"""
        db = build_db()
        original = db.request

        def request(method, table, query=None, payload=None, prefer=None):
            if table == "family_state_entries":
                raise RuntimeError("Supabase GET family_state_entries failed: 404 PGRST205")
            return original(method, table, query=query, payload=payload, prefer=prefer)

        db.request = request
        package = self.export_b(db)
        self.assertEqual(self.entries(package), [])
        self.assertEqual(package["person"]["id"], PERSON_B)


if __name__ == "__main__":
    unittest.main()
