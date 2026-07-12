-- 009_perception_snapshot_daily_briefing.sql
-- 修 perception_snapshots.snapshot_type CHECK constraint 沒有 'daily_briefing'
--
-- ROOT CAUSE（2026-07-12 卡西法查出、讀 schema 定案，未動 prod）：
-- 004_ai_memory_service_foundation.sql 建表時，snapshot_type 的允許清單裡從來沒有
-- 'daily_briefing'，但 server.py 的 refresh_daily_briefing() 從清晨簡報功課上線那天起
-- 就一直在寫 snapshotType:'daily_briefing'——每次寫入都會被這條 Postgres CHECK constraint
-- 擋下（錯誤碼 23514 check_violation），寫入從未真的成功過。
--
-- 這正是「23514 失敗執行緒」的真正根因：不是單純併發風暴，是 schema 從一開始就沒開放這個值。
-- 去抖（commit 7e95e77）只讓失敗「頻率」降低（同時只一條、5 分鐘內不重試），沒有讓寫入「成功」——
-- 每次嘗試（不管清晨定時跑或通話中臨時補）都還是會 500。清晨定時任務要真的能用，這支 migration
-- 是必要條件，不是可選項。
--
-- 執行方式：Supabase Dashboard → SQL Editor 貼上執行（跟 001-008 同一套流程、SQL Editor-ready）。
-- 影響範圍：只新增一個允許值，對既有 15 種 snapshot_type 的資料與行為零影響（純 additive）。

begin;

do $$
declare
  con record;
begin
  for con in
    select conname
    from pg_constraint
    where conrelid = 'public.perception_snapshots'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%snapshot_type%'
  loop
    execute format('alter table public.perception_snapshots drop constraint %I', con.conname);
  end loop;
end $$;

alter table public.perception_snapshots
  add constraint perception_snapshots_snapshot_type_check
  check (snapshot_type in (
    'time',
    'weather',
    'calendar',
    'location',
    'current_topic',
    'book_context',
    'travel_context',
    'local_activity_context',
    'exercise_context',
    'finance_context',
    'media_context',
    'food_context',
    'news_context',
    'wisdom_context',
    'family_context',
    'interest_graph',
    'daily_briefing'   -- 新增：清晨定時簡報（天氣＋空品＋明天預告＋本週話題＋今天回診）
  ));

commit;
