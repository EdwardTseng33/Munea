-- ═══════════════════════════════════════════════════════════════
-- 沐寧 Munea · 正式資料庫補跑（2026-07-30 查證後產出）
--
-- 這一份要做什麼：正式庫少了四份設定沒跑，其中 026 是「用戶意見收不到」的直接原因。
--   020 021 022 = 企業席次／請款／報表這三塊的資料表（後台企業功能要用）
--   026        = 用戶意見收件箱（App 送出的意見目前寫在伺服器暫存檔、每次上線就被洗掉）
--
-- 怎麼用：
--   1. 打開 Supabase → 左側 SQL Editor → New query
--   2. 整份貼上（不要只貼一段，順序有相依）
--   3. 按 Run
--   4. 看到 Success 就完成；重複跑不會壞（每一段都是「已經有就跳過」的寫法）
--
-- 跑完會生效的事：App 的用戶意見會進資料庫，後台「用戶意見」那頁就收得到，
-- 而且以後上線不會再被洗掉。
-- ═══════════════════════════════════════════════════════════════


-- ───────── 第 1 段 / 共 4 段：020_enterprise_seats.sql ─────────

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


-- ───────── 第 2 段 / 共 4 段：021_enterprise_billing_settings.sql ─────────

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


-- ───────── 第 3 段 / 共 4 段：022_enterprise_documents.sql ─────────

-- Munea 企業席次 — 月報與請款單「可下載文件」補強。
-- Run after 020_enterprise_seats.sql、021_enterprise_billing_settings.sql。
--
-- 背景（2026-07-20 三次需求：接通後台「月報與請款單下載」最後一哩）：
-- 月結會同時產出請款單（enterprise_invoices，已建表）與 ESG 成效月報（原本只在
-- /admin/enterprise/monthly-close 回應裡曇花一現，沒有落地存檔，之後要重下載就沒東西）。
--
-- 兩份文件的「凍結時機」不同，是這次補強的核心決定（見 engine/enterprise_billing.py
-- 的 save_report()／get_invoice_html() docstring 詳細理由，這裡只記資料庫層面的落地）：
--   · 請款單：草稿階段（status=draft）沿用既有設計即時重繪最新開票／收款設定
--     （Edward 換開票公司後，舊草稿要立刻反映新抬頭）；一旦人工按「已寄出」轉 issued，
--     當下的畫面就此凍結存進 invoice_html_snapshot——之後不管收款設定再怎麼改，
--     這張已經寄出去的單重新下載時，看到的都是「當初真的印給客戶的那個版本」，
--     帳務對帳／爭議時才有一致的憑證。
--   · ESG 成效月報：一算完（不管有沒有正式寄出）就整份凍結存檔——月報沒有「草稿人工放行」
--     這種中間態，且底層事件表可能事後補資料，重算數字可能跟當初報表兜不起來；
--     稽核／ESG 揭露要看的是「當初真的算出來的那個版本」，所以在算完的當下就落地，
--     不是等到某個人工確認動作才凍結。

begin;

-- 請款單一旦寄出（status 從 draft 轉 issued），把當下渲染好的 HTML 整份凍結存進來——
-- draft 階段這欄是 null，前端／render_invoice_html() 那時仍即時重繪最新設定。
alter table public.enterprise_invoices
  add column if not exists invoice_html_snapshot text;

-- ESG 成效月報：一算完就整份落地（原始數據 jsonb ＋ 渲染好的 HTML 一起存），
-- 之後下載一律回這份存檔的原樣，不即時重算。
create table if not exists public.enterprise_reports (
  id uuid primary key default gen_random_uuid(),
  enterprise_client_id uuid not null references public.enterprise_clients(id) on delete cascade,
  invoice_id uuid references public.enterprise_invoices(id) on delete set null,
  period_start date not null,
  period_end date not null,
  report_data jsonb not null default '{}'::jsonb,
  report_html text not null default '',
  generated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 同一家公司同一期間重跑月結＝覆蓋舊報告（跟請款單同一期間會覆蓋草稿是同一個道理），
-- 不會累積出好幾份同期間的報告混淆下載清單。
create unique index if not exists enterprise_reports_client_period_uidx
  on public.enterprise_reports(enterprise_client_id, period_start);

drop trigger if exists enterprise_reports_set_updated_at on public.enterprise_reports;
create trigger enterprise_reports_set_updated_at
  before update on public.enterprise_reports
  for each row execute function public.set_updated_at();

alter table public.enterprise_reports enable row level security;

-- 跟其餘企業後台表同一套鎖法：RLS 開著＋零 policy＝一律拒絕；只有 service role 能存取。
revoke all on public.enterprise_reports from anon, authenticated;

create index if not exists enterprise_reports_client_idx
  on public.enterprise_reports(enterprise_client_id, period_start desc);

commit;


-- ───────── 第 4 段 / 共 4 段：026_feedback_store.sql ─────────

-- 2026-07-24：意見與建議收件箱上雲（feedback_items）。
-- engine/feedback_store.json 原本只寫容器本地檔——每次部署／多副本擴容就會被洗掉或分裂，
-- 後台『意見回饋』頁（admin_feedback_summary）看到的資料因此永遠不完整。
-- 沿用既有跨帳號後台頁模式（medication_dose_events／wellbeing_signals 等）：一般使用者只能
-- insert 自己帳號的意見，後台聚合改走 service-role 全表查詢，不經 RLS。
-- Run after 025_person_profile_fields.sql.

begin;

create table if not exists public.feedback_items (
  id text primary key,
  account_id uuid references public.accounts(id) on delete set null,
  person_id uuid references public.persons(id) on delete set null,
  type text not null check (type in ('bug', 'idea', 'praise', 'nps', 'survey')),
  category text,
  content text not null default '',
  score integer,
  app_version text,
  plan text,
  image_data_url text,
  created_at timestamptz not null default now()
);

alter table public.feedback_items enable row level security;

drop policy if exists feedback_items_account_member_insert on public.feedback_items;
create policy feedback_items_account_member_insert
on public.feedback_items for insert
to authenticated
with check (
  account_id is null
  or exists (
    select 1 from public.account_members am
    where am.account_id = feedback_items.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

revoke all on public.feedback_items from anon;
grant select, insert on public.feedback_items to authenticated;

create index if not exists feedback_items_created_at_idx
  on public.feedback_items(created_at desc);
create index if not exists feedback_items_type_idx
  on public.feedback_items(type, created_at desc);

comment on table public.feedback_items is
  'User feedback inbox (bug/idea/praise/nps/survey); read cross-account by admin via service-role, not exposed to authenticated select.';

commit;

