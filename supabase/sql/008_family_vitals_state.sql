-- 008 · 家人健康數據真同步（2026-07-09 Edward「用戶狀態數據要連動到家人手機」拍板）
-- 內容：family_state_entries 的 state_key 白名單加 'vitals'。
-- vitals 的 value 形狀＝{ personId: { name, nick, day, bpSys, bpDia, hr, spo2, sleepHours, steps, updatedAt } }
--（每人一份、引擎端按 personId 合併後整包存——沿用既有唯一鍵 (account_id, family_group_id, state_key)）
-- 套用方式：Supabase Dashboard SQL Editor 跑本檔（跟 001~007 同法）。

alter table public.family_state_entries
  drop constraint if exists family_state_entries_state_key_check;

alter table public.family_state_entries
  add constraint family_state_entries_state_key_check
  check (state_key in ('activities', 'familyFeed', 'meds', 'visit', 'routine', 'wallet', 'vitals'));
