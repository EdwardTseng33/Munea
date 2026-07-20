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
