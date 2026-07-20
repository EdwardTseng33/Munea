-- Munea 企業席次 — 開票／收款設定（單列設定表）。
-- Run after 020_enterprise_seats.sql（enterprise_invoices 要用這份設定產請款單）。
--
-- 背景（2026-07-20 二次需求 · Edward 親提）：Edward 目前是一人公司，開發票要借用
-- 另一家公司的抬頭，抬頭／統編／收款銀行都不是寫死的常數，而且未來會換公司。
-- engine/enterprise_billing.py 原本用環境變數 MUNEA_ENTERPRISE_REMIT_INFO 頂著一個
-- 假字串（「戶名：沐寧股份有限公司（暫定）｜帳號：（待財務部提供）」），現在改成
-- 後台可填、可改的一列設定，讀取入口見 engine/enterprise_seats.py 的
-- get_billing_settings() / is_billing_settings_configured()。
--
-- 單列設計：singleton boolean primary key default true check(singleton) 是常見的
-- Postgres 單列表寫法——PK 唯一，任何第二筆 insert 都會撞 PK 違規，天生只能有一列，
-- 不必額外寫應用層鎖或 CHECK COUNT(*) 的 trigger。
--
-- 敏感等級：跟 enterprise_clients／enterprise_seats／enterprise_invoices 同一套
-- 鎖法——RLS 開著、零 policy、不對 anon/authenticated 開任何 grant，只有 service role
-- （略過 RLS）能存取。收款帳號欄位（bank_account_no）比照其他三張表的收款欄位同等
-- 敏感度處理，一般使用者完全讀不到；後台接口的稽核紀錄也只記遮罩後的末四碼
-- （見 engine/server.py 的 _mask_account_tail()），不把完整帳號複製進 audit_events。

begin;

create table if not exists public.enterprise_billing_settings (
  singleton boolean primary key default true check (singleton),
  -- 開票方（我方）資訊
  issuer_company_name text,
  issuer_tax_id text,
  issuer_address text,
  issuer_phone text,
  issuer_contact_name text,
  -- 收款銀行資訊
  bank_name text,
  bank_branch text,
  bank_account_name text,
  bank_account_no text,
  -- 付款期限天數：對應需求單 4.2「次月 15 日前」既有邏輯的預設值（PAYMENT_DUE_DAY=15），
  -- 這裡讓它可調——enterprise_billing.py 的 compute_due_date() 之後要改成讀這欄，
  -- 不再寫死常數（那支檔案的責任範圍，這裡只負責存這個值）。
  payment_terms_days integer not null default 15 check (payment_terms_days > 0),
  invoice_footer_note text,
  updated_at timestamptz not null default now(),
  updated_by text
);

drop trigger if exists enterprise_billing_settings_set_updated_at on public.enterprise_billing_settings;
create trigger enterprise_billing_settings_set_updated_at
  before update on public.enterprise_billing_settings
  for each row execute function public.set_updated_at();

alter table public.enterprise_billing_settings enable row level security;

-- 後台專用表：不對 anon／authenticated 開任何 grant，也不建任何 RLS policy——
-- RLS 開著＋零 policy＝一律拒絕；只有 service role（略過 RLS）能存取。
revoke all on public.enterprise_billing_settings from anon, authenticated;

commit;
