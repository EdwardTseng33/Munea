-- Munea 企業席次 — B2B 資料模型（企業席次·後台管理與月結 需求單 2.1–2.5）。
-- Run after 001_initial_munea_schema.sql（accounts / subscription_ledger）。
-- 命名、觸發器、grant/revoke、index 風格對齊 003_analytics_admin_foundation.sql。
--
-- 這四張表是「我們自己操作的後台」專用（企業客戶不登入我們系統、一切代操）：
-- 一般 authenticated 使用者一律不可讀寫——比 003 的 admin_notes 更嚴。admin_notes 還開放
-- 帳號 owner/admin 讀自己帳號的備註；這四張表連帳號擁有者都不開放，因為席次記錄本來就
-- 跨帳號、不屬於任何單一 account，不該讓任何前台使用者用自己的 JWT 查到。
-- 服務端一律用 service role（略過 RLS）存取，見 engine/supabase_adapter.py 的 enterprise_* 方法。

begin;

-- 2.1 enterprise_clients — 企業客戶
create table if not exists public.enterprise_clients (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  tax_id text,
  billing_address text,
  contact_name text,
  contact_email text,
  contact_phone text,
  plan_tier text not null default 'plus' check (plan_tier in ('plus', 'pro')),
  unit_price_twd numeric not null default 0 check (unit_price_twd >= 0),
  contract_start date,
  contract_end date,
  seat_quota integer not null default 0 check (seat_quota >= 0),
  status text not null default 'active' check (status in ('active', 'expiring', 'ended')),
  report_recipients text[] not null default '{}',
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2.2 enterprise_seats — 席次（歸屬記號的本體）
-- status 五種（2026-07-20 需求單 5A 修正版擴充，原 2.2 只有四種）：
--   pending（已匯入、還沒比對到帳號）
--   waiting（已比對到帳號，但該帳號個人已購買的等級 > 企業方案等級，暫不授予，等個人訂閱到期自動接手）
--   active（已綁定帳號，可授予／已授予會員資格）
--   grace（合約到期或被移除後的 30 天緩衝期）
--   released（正式釋出）
create table if not exists public.enterprise_seats (
  id uuid primary key default gen_random_uuid(),
  enterprise_client_id uuid not null references public.enterprise_clients(id) on delete cascade,
  invite_email text not null,
  account_id uuid references public.accounts(id) on delete set null,
  status text not null default 'pending' check (status in ('pending', 'waiting', 'active', 'grace', 'released')),
  activated_at timestamptz,
  -- waiting_until：情況 B（個人等級 > 企業等級）時，記下個人訂閱的到期日——
  -- 到期後由 grant_enterprise_membership() 自動把這個席次從 waiting 接手成 active，
  -- 用戶無需任何操作、無空窗（需求單 5A）。
  waiting_until timestamptz,
  grace_started_at timestamptz,
  grace_until timestamptz,
  released_at timestamptz,
  released_reason text check (released_reason is null or released_reason in ('contract_end', 'removed_by_client', 'converted_to_personal')),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2.3 enterprise_seat_events — 異動紀錄（收費爭議時的憑證：誰、何時、從什麼狀態到什麼狀態）
create table if not exists public.enterprise_seat_events (
  id uuid primary key default gen_random_uuid(),
  seat_id uuid not null references public.enterprise_seats(id) on delete cascade,
  from_status text,
  to_status text not null,
  actor text not null default 'admin',
  reason text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- 2.4 enterprise_invoices — 請款單（表本身在此建；月結產出／收款登記邏輯屬另一支
-- engine/enterprise_billing.py，不在本檔範圍。欄位含需求單 5.2 全部收款欄位——
-- 這張表的「已入帳」是 5.1 鐵律『錢沒到、帳號不開』唯一開關，
-- engine/enterprise_seats.py 的 assert_client_has_paid_invoice() 會讀 status 這欄做守門。）
create table if not exists public.enterprise_invoices (
  id uuid primary key default gen_random_uuid(),
  invoice_no text not null unique,
  enterprise_client_id uuid not null references public.enterprise_clients(id) on delete cascade,
  period_start date not null,
  period_end date not null,
  billable_seats integer not null default 0 check (billable_seats >= 0),
  unit_price_twd numeric not null default 0 check (unit_price_twd >= 0),
  subtotal_twd numeric not null default 0 check (subtotal_twd >= 0),
  tax_twd numeric not null default 0 check (tax_twd >= 0),
  total_twd numeric not null default 0 check (total_twd >= 0),
  -- 狀態流（需求單 5.2）：draft（系統算好，未放行）→ issued（人工確認後寄出）
  -- → paid（人工核對匯款後填 paid_at／paid_amount_twd）→ invoiced（發票已開立）→ void（作廢，任何階段都可能發生）
  status text not null default 'draft' check (status in ('draft', 'issued', 'paid', 'invoiced', 'void')),
  due_date date,
  seat_snapshot jsonb not null default '[]'::jsonb,
  report_ref text,
  -- 以下六欄＝需求單 5.2「收款紀錄欄位」：sent_at／due_date（上面已有）皆系統或人工填，
  -- paid_at 之後才是「已入帳」，是唯一開通開關；逾期天數／累計欠款由 due_date 與 paid_at 算，不落地存。
  sent_at timestamptz,
  paid_at timestamptz,
  paid_amount_twd numeric check (paid_amount_twd is null or paid_amount_twd >= 0),
  payment_note text,
  invoice_number text,
  invoice_issued_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2.1 補充（2026-07-20 二次需求 · 蘇菲協調後拍板）：client_code 讓請款單號
-- （MU-YYYYMM-<公司代碼>）更好認、可被人挑選（例如公司英文簡稱）。選填、非強制——
-- engine/enterprise_billing.py 的 derive_client_code() 目前仍預設用 client.id 前 8 碼
-- 當代碼（穩定、不必處理中文轉拼音），這欄留給之後要接手改成「優先讀這欄、沒有才退回
-- id 前 8 碼」時用，本次不強制耦合兩邊改動。
alter table public.enterprise_clients
  add column if not exists client_code text;
create unique index if not exists enterprise_clients_client_code_uidx
  on public.enterprise_clients(client_code) where client_code is not null;

-- 2.5 會員資格授予的來源標記：非 Apple 來源的授予必須指出處。
alter table public.subscription_ledger
  add column if not exists grant_ref uuid references public.enterprise_seats(id) on delete set null;

-- 鐵律的資料庫層防線（app 層也擋，見 engine/enterprise_seats.py 的
-- validate_subscription_grant_ref；這裡是 belt-and-suspenders，防止有人繞過 app 直接寫表）：
-- provider='enterprise' 的授予，grant_ref 一定要指到一筆席次，不能是 null。
alter table public.subscription_ledger drop constraint if exists subscription_ledger_enterprise_requires_grant_ref;
alter table public.subscription_ledger
  add constraint subscription_ledger_enterprise_requires_grant_ref
  check (provider <> 'enterprise' or grant_ref is not null);

drop trigger if exists enterprise_clients_set_updated_at on public.enterprise_clients;
create trigger enterprise_clients_set_updated_at
  before update on public.enterprise_clients
  for each row execute function public.set_updated_at();

drop trigger if exists enterprise_seats_set_updated_at on public.enterprise_seats;
create trigger enterprise_seats_set_updated_at
  before update on public.enterprise_seats
  for each row execute function public.set_updated_at();

drop trigger if exists enterprise_invoices_set_updated_at on public.enterprise_invoices;
create trigger enterprise_invoices_set_updated_at
  before update on public.enterprise_invoices
  for each row execute function public.set_updated_at();

alter table public.enterprise_clients enable row level security;
alter table public.enterprise_seats enable row level security;
alter table public.enterprise_seat_events enable row level security;
alter table public.enterprise_invoices enable row level security;

-- 後台專用表：不對 anon／authenticated 開任何 grant，也不建任何 RLS policy——
-- RLS 開著＋零 policy＝一律拒絕；只有 service role（略過 RLS）能存取。
revoke all on public.enterprise_clients from anon, authenticated;
revoke all on public.enterprise_seats from anon, authenticated;
revoke all on public.enterprise_seat_events from anon, authenticated;
revoke all on public.enterprise_invoices from anon, authenticated;

create index if not exists enterprise_clients_status_idx on public.enterprise_clients(status);
create index if not exists enterprise_seats_client_idx on public.enterprise_seats(enterprise_client_id);
create index if not exists enterprise_seats_account_idx on public.enterprise_seats(account_id);
create index if not exists enterprise_seats_status_idx on public.enterprise_seats(status);
create index if not exists enterprise_invoices_status_idx on public.enterprise_invoices(status);
-- 同一家公司底下 email 不可重複匯入兩次（大小寫視為同一人）；同時是「3.2 重複」預檢的資料庫防線。
create unique index if not exists enterprise_seats_client_email_uidx on public.enterprise_seats(enterprise_client_id, lower(invite_email));
-- 「這個 email 是否已屬於其他公司」的跨公司查詢用（3.2 預檢第 4 種情況）。
create index if not exists enterprise_seats_invite_email_idx on public.enterprise_seats(lower(invite_email));
create index if not exists enterprise_seat_events_seat_idx on public.enterprise_seat_events(seat_id, created_at desc);
create index if not exists enterprise_invoices_client_idx on public.enterprise_invoices(enterprise_client_id, period_start desc);
create index if not exists subscription_ledger_grant_ref_idx on public.subscription_ledger(grant_ref) where grant_ref is not null;

commit;
