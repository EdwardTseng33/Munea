-- 2026-11-09：緊急聯絡人通知（1.0.72）——family_state_entries 的 state_key 白名單加 'safetyContacts'。
-- 沿用既有 008/011 同一招（這把鑰匙本身不開新表，整家一筆、按長輩 personId 合併存在
-- value jsonb 裡：{elderPersonId: [contactPersonId, ...]}，跟 'vitals' 的「按人合併」同一套）。
-- Run after 031_fix_free_account_retention_delete.sql.
-- ⚠ 這份還沒在正式 Supabase 跑過——Edward 目前登不進正式庫（見 PR 說明）。沒跑之前，
-- save_family_state_entry 遇到 'safetyContacts' 這把鑰匙會撞 23514（check constraint 不認），
-- engine/server.py 的 family_state_response 既有機制會安靜接住、退本機 json 檔，不會噴錯給用戶。

begin;

alter table public.family_state_entries
  drop constraint if exists family_state_entries_state_key_check;

alter table public.family_state_entries
  add constraint family_state_entries_state_key_check
  check (state_key in ('circle', 'activities', 'familyFeed', 'meds', 'visit', 'routine', 'wallet', 'safetyContacts'));

commit;
