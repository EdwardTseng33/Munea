-- Munea AI memory and brain-service foundation.
-- Run after 001_initial_munea_schema.sql and 003_analytics_admin_foundation.sql.

begin;

create extension if not exists vector;

create table if not exists public.memory_items (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid not null references public.persons(id) on delete cascade,
  source_conversation_summary_id uuid references public.conversation_summaries(id) on delete set null,
  memory_type text not null check (memory_type in (
    'identity',
    'preference',
    'relationship',
    'routine',
    'health_context',
    'emotion',
    'topic_interest',
    'temporary_event',
    'safety_signal'
  )),
  content text not null,
  source text not null default 'conversation',
  confidence numeric not null default 0.5 check (confidence >= 0 and confidence <= 1),
  importance numeric not null default 0.5 check (importance >= 0 and importance <= 1),
  sensitivity text not null default 'normal' check (sensitivity in ('normal', 'sensitive', 'restricted')),
  consent_scope text not null default 'user' check (consent_scope in ('user', 'family_shareable', 'care_team', 'private')),
  valid_from timestamptz not null default now(),
  valid_until timestamptz,
  last_confirmed_at timestamptz,
  supersedes_memory_id uuid references public.memory_items(id) on delete set null,
  embedding vector(1536),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table if not exists public.perception_snapshots (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid references public.persons(id) on delete set null,
  snapshot_type text not null check (snapshot_type in (
    'time',
    'weather',
    'calendar',
    'location',
    'current_topic',
    'family_context',
    'interest_graph'
  )),
  observed_at timestamptz not null default now(),
  expires_at timestamptz,
  facts jsonb not null default '{}'::jsonb,
  source text not null default 'munea',
  created_at timestamptz not null default now()
);

create table if not exists public.ai_brain_runs (
  id uuid primary key default gen_random_uuid(),
  account_id uuid references public.accounts(id) on delete set null,
  person_id uuid references public.persons(id) on delete set null,
  brain text not null check (brain in ('reflex', 'butler', 'guardian')),
  provider text not null,
  model text not null,
  effort_profile text not null default 'standard' check (effort_profile in ('quick', 'standard', 'deep')),
  purpose text not null,
  input_ref text,
  output_ref text,
  risk_level text check (risk_level in ('none', 'low', 'medium', 'high', 'critical')),
  latency_ms integer check (latency_ms is null or latency_ms >= 0),
  token_usage jsonb not null default '{}'::jsonb,
  cost_usd numeric,
  status text not null default 'completed' check (status in ('completed', 'failed', 'skipped')),
  error_code text,
  created_at timestamptz not null default now()
);

drop trigger if exists memory_items_set_updated_at on public.memory_items;
create trigger memory_items_set_updated_at
  before update on public.memory_items
  for each row execute function public.set_updated_at();

alter table public.memory_items enable row level security;
alter table public.perception_snapshots enable row level security;
alter table public.ai_brain_runs enable row level security;

grant select, insert, update, delete on public.memory_items to authenticated;
grant select, insert, update, delete on public.perception_snapshots to authenticated;
grant select, insert on public.ai_brain_runs to authenticated;

create policy "memory_items_account_members_select"
on public.memory_items
for select
to authenticated
using (
  exists (
    select 1
    from public.account_members am
    where am.account_id = memory_items.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

create policy "memory_items_account_members_write"
on public.memory_items
for all
to authenticated
using (
  exists (
    select 1
    from public.account_members am
    where am.account_id = memory_items.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1
    from public.account_members am
    where am.account_id = memory_items.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

create policy "perception_snapshots_account_members_select"
on public.perception_snapshots
for select
to authenticated
using (
  exists (
    select 1
    from public.account_members am
    where am.account_id = perception_snapshots.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

create policy "perception_snapshots_account_members_write"
on public.perception_snapshots
for all
to authenticated
using (
  exists (
    select 1
    from public.account_members am
    where am.account_id = perception_snapshots.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1
    from public.account_members am
    where am.account_id = perception_snapshots.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

create policy "ai_brain_runs_account_members_select"
on public.ai_brain_runs
for select
to authenticated
using (
  account_id is null
  or exists (
    select 1
    from public.account_members am
    where am.account_id = ai_brain_runs.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

create index if not exists memory_items_account_person_type_idx
  on public.memory_items(account_id, person_id, memory_type)
  where deleted_at is null;

create index if not exists memory_items_importance_idx
  on public.memory_items(account_id, importance desc, confidence desc)
  where deleted_at is null;

create index if not exists perception_snapshots_account_type_idx
  on public.perception_snapshots(account_id, snapshot_type, observed_at desc);

create index if not exists ai_brain_runs_account_brain_idx
  on public.ai_brain_runs(account_id, brain, created_at desc);

commit;
