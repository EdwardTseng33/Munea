#!/usr/bin/env python3
"""後台名冊改批次查詢後的兩件事：來回次數不隨戶數成長、每一戶的資料不能串錯。

背景（2026-07-29）：原本每一戶各查四次（家庭圈／主要使用者／家人／陪伴角色），
12 戶就要 49 次來回、實測 6.7 秒；照這個斜率大約 30 戶起就會撞上後台前端 15 秒逾時、
整頁讀不出來。改成四張表各查一次、在記憶體裡歸戶。

這支測試最重要的不是「快」，是**快之後資料還是對的**——批次撈回來自己歸戶，
最容易犯的錯就是把 A 家的家人算到 B 家頭上。只打樁 _select／_first，不碰真網路。
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

import supabase_adapter


def make_adapter():
    env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
        "MUNEA_DATABASE_PROVIDER": "supabase",
        "MUNEA_SUPABASE_ACCOUNT_ID": "11111111-1111-4111-8111-111111111111",
        "MUNEA_SUPABASE_PERSON_ID": "22222222-2222-4222-8222-222222222222",
    }
    return supabase_adapter.SupabaseAdapter(env=env)


def build_fixture(house_count):
    """house_count 戶，每戶一個家庭圈、一位主要使用者、兩個家人、一個陪伴角色。"""
    accounts, groups, persons, memberships, companions = [], [], [], [], []
    for i in range(house_count):
        aid, gid, pid = f"acct-{i}", f"fg-{i}", f"person-{i}"
        accounts.append({"id": aid, "name": f"第 {i} 戶", "locale": "zh-TW"})
        groups.append({"id": gid, "account_id": aid, "name": f"{i} 號家庭圈"})
        persons.append({"id": pid, "account_id": aid, "display_name": f"角色{i}",
                        "profile_name": f"真人{i}", "is_primary_care_recipient": True})
        for m in range(2):
            memberships.append({"account_id": aid, "family_group_id": gid, "role": "family_contact"})
        # 混進一筆「舊家庭圈」的成員：批次歸戶後仍要被過濾掉，不能算進這一戶的人數
        memberships.append({"account_id": aid, "family_group_id": f"old-{i}", "role": "family_contact"})
        companions.append({"account_id": aid, "person_id": pid, "display_name": f"寧寧{i}"})
    return accounts, groups, persons, memberships, companions


class RosterBatchingTests(unittest.TestCase):
    def _run(self, house_count):
        adapter = make_adapter()
        accounts, groups, persons, memberships, companions = build_fixture(house_count)
        calls = []

        def fake_select(table, query=None):
            calls.append(table)
            return {"accounts": accounts, "family_groups": groups, "persons": persons,
                    "family_memberships": memberships, "companion_profiles": companions}.get(table, [])

        with patch.object(adapter, "_select", side_effect=fake_select), \
             patch.object(adapter, "_first", side_effect=AssertionError("不該再逐戶查單筆")), \
             patch.object(adapter, "resolve_test_account_signals",
                          return_value={"domainTestIds": set(), "manualTestIds": set(), "ownersByAccount": {}}):
            summaries = adapter.load_admin_accounts(limit=200)
        return summaries, calls

    def test_query_count_does_not_grow_with_houses(self):
        """3 戶跟 60 戶打的來回次數要一樣——這就是這次改動的重點。"""
        _, few = self._run(3)
        _, many = self._run(60)
        self.assertEqual(len(few), len(many))
        self.assertEqual(len(few), 5, f"預期 5 次（帳號＋四張表），實際 {few}")

    def test_each_house_gets_its_own_rows(self):
        """歸戶不能串錯：每一戶的家庭圈／主要使用者／陪伴角色都要是自己的。"""
        summaries, _ = self._run(5)
        self.assertEqual(len(summaries), 5)
        for i, summary in enumerate(summaries):
            self.assertEqual(summary["accountId"], f"acct-{i}")
            self.assertEqual(summary["familyGroup"]["name"], f"{i} 號家庭圈")
            self.assertEqual(summary["primaryPerson"]["id"], f"person-{i}")
            self.assertEqual(summary["primaryPerson"]["profileName"], f"真人{i}")
            self.assertEqual(summary["companion"]["displayName"], f"寧寧{i}")

    def test_members_of_other_family_groups_are_not_counted(self):
        """只算「目前這個家庭圈」的成員——舊家庭圈那筆不能混進人數。"""
        summaries, _ = self._run(4)
        for summary in summaries:
            self.assertEqual(summary["familyMembers"]["count"], 2)

    def test_house_without_family_or_person_still_listed(self):
        """演習腳本留下的孤兒帳號（沒有家庭圈也沒有個人資料）照樣要出現在名冊上。"""
        adapter = make_adapter()

        def fake_select(table, query=None):
            if table == "accounts":
                return [{"id": "orphan", "name": "Queue burst drill"}]
            return []

        with patch.object(adapter, "_select", side_effect=fake_select), \
             patch.object(adapter, "resolve_test_account_signals",
                          return_value={"domainTestIds": set(), "manualTestIds": set(), "ownersByAccount": {}}):
            summaries = adapter.load_admin_accounts(limit=50)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["accountName"], "Queue burst drill")
        self.assertEqual(summaries[0]["familyMembers"]["count"], 0)
        self.assertEqual(summaries[0]["primaryPerson"]["id"], "")

    def test_no_accounts_skips_the_batch_queries(self):
        """一戶都沒有時不必再打那四張表。"""
        adapter = make_adapter()
        calls = []

        def fake_select(table, query=None):
            calls.append(table)
            return []

        with patch.object(adapter, "_select", side_effect=fake_select), \
             patch.object(adapter, "resolve_test_account_signals",
                          return_value={"domainTestIds": set(), "manualTestIds": set(), "ownersByAccount": {}}):
            summaries = adapter.load_admin_accounts(limit=50)

        self.assertEqual(summaries, [])
        self.assertEqual(calls, ["accounts"])


if __name__ == "__main__":
    unittest.main()
