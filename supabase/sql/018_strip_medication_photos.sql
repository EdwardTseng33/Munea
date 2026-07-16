-- 清除雲端殘留的用藥照片（2026-07-16 Edward 拍板）
--
-- 【為什麼要清】
--   隱私政策 https://app.munea.net/privacy 對用戶承諾：
--   「用藥照片…這些照片只儲存在你的裝置本機，不會上傳雲端，也不會與家人共享。」
--   但 2026-07-09 的隱私修正只補了 /family/state 那條路，漏掉 /routine-reminders——
--   照片持續隨 schedule 上傳、存進本表。程式端已於 PR #101 修好（前端不送、
--   伺服器端強制剝除），但「過去已經傳上來的」還躺在這裡。不清掉，那句承諾還是假的。
--
-- 【目標】東京正式專案 fespbkdwafueyonppzwq（不是雪梨 uhmpmystjjdqqxlpsthc）
-- 【怎麼跑】Supabase 後台 → SQL Editor → 一段一段跑，看完數字再跑下一段
-- 【動到什麼】只把 routine_reminders.schedule 裡的 photo 鍵拿掉。
--            不刪任何一筆提醒、不動任何其他欄位、不動任何其他表。
-- 【可重複跑】跑第二次第二段會顯示 0 筆，不會出錯。
--
-- ⚠ 本檔未經實機測試（Windows 這台沒有 psql／docker 可先試跑）。
--   請務必照順序一段一段跑、先看第 1 段數字，不要整包一次貼上執行。


-- ══════════════════════════════════════════════════════════════
-- 第 1 段 · 先看有多少（唯讀，不改任何東西）
-- ══════════════════════════════════════════════════════════════
select
  count(*)                                                        as 提醒總筆數,
  count(*) filter (where jsonb_exists(schedule, 'photo'))          as 夾帶照片的筆數,
  round(coalesce(sum(length(schedule->>'photo')), 0) / 1024.0, 1)  as 照片資料量KB,
  count(*) filter (where schedule::text like '%data:image/%')      as 含圖檔的筆數
from public.routine_reminders;

-- 若「夾帶照片的筆數」＝ 0 → 雲端本來就乾淨，到此為止、不用往下跑。
-- 若 > 0 → 記下這個數字，再跑第 2 段。


-- ══════════════════════════════════════════════════════════════
-- 第 2 段 · 把 photo 鍵拿掉（⚠ 不可逆：照片清掉就沒了，這正是目的）
-- ══════════════════════════════════════════════════════════════
-- 「schedule - 'photo'」= 從 jsonb 移除 photo 這個鍵，其餘鍵原封不動。
with cleaned as (
  update public.routine_reminders
     set schedule = schedule - 'photo'
   where jsonb_exists(schedule, 'photo')
  returning id
)
select count(*) as 這次清掉的筆數 from cleaned;

-- 這個數字應該等於第 1 段的「夾帶照片的筆數」。對不上就停下來回報。


-- ══════════════════════════════════════════════════════════════
-- 第 3 段 · 驗收（兩個數字都該是 0）
-- ══════════════════════════════════════════════════════════════
select
  count(*) filter (where jsonb_exists(schedule, 'photo'))      as 還有photo鍵的筆數,
  count(*) filter (where schedule::text like '%data:image/%')  as 仍夾帶圖檔的筆數,
  count(*)                                                     as 提醒總筆數_應與第1段相同
from public.routine_reminders;

-- 前兩欄＝0 且「提醒總筆數」與第 1 段相同 → 清乾淨了，而且沒誤刪任何提醒。
-- 「仍夾帶圖檔的筆數」若 > 0 → 表示照片藏在別的鍵裡，停下來回報蘇菲，不要自己猜著刪。


-- ══════════════════════════════════════════════════════════════
-- 跑完請回填
-- ══════════════════════════════════════════════════════════════
-- 把三段的數字回報，並回填 docs/App-Privacy-問卷填答表-2026-07-16.md 的阻擋項 A-1。
