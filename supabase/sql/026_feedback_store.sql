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
