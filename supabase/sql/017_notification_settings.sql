-- 通知中心設定（2026-07-15 Edward 定稿）：每人一筆——推播總開關＋四分類開關。
-- 預設關（push_enabled=false）：推播由用戶自己在 App 決定開啟。
create table if not exists public.notification_settings (
  person_id uuid primary key references public.persons(id) on delete cascade,
  push_enabled boolean not null default false,
  categories jsonb not null default '{"medication":true,"clinic":true,"family":true,"safety":true}'::jsonb,
  updated_at timestamptz not null default now()
);
alter table public.notification_settings enable row level security;
