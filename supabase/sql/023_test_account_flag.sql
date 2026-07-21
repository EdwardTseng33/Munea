-- 2026-07-21: 帳號層測試帳號人工標記。
-- 用來把自己人的測試帳號（例如 qa-review@munea.net）跟真實用戶隔離：
--   - engine/server.py admin_accounts_summary 用它 + email @munea.net 網域判準，
--     決定用戶名冊要不要隱藏這個帳號（預設隱藏，後台可勾選「顯示測試帳號」）。
--   - engine/server.py test_account_id_set() 用同一個判準餵進 is_analytics_excluded_event，
--     讓北極星／活躍人數／訂閱指標等營運數據也一併把測試帳號排除，不會灌水。
-- 沒有 email 網域信號的帳號（例如本機測試種子帳號）可在後台用戶明細按「標記為測試帳號」
-- 手動勾選，寫進這個欄位（engine/supabase_adapter.py set_account_test_flag）。
-- Run after 022_enterprise_documents.sql.

begin;

alter table public.accounts
  add column if not exists is_test_account boolean not null default false;

create index if not exists accounts_is_test_account_idx
  on public.accounts (is_test_account)
  where is_test_account;

commit;
