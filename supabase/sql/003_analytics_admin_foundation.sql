-- Munea analytics and admin foundation.
-- Intended first use: run after 001_initial_munea_schema.sql and 002_demo_bootstrap.sql.

begin;

create table if not exists public.product_events (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid references public.persons(id) on delete set null,
  family_group_id uuid references public.family_groups(id) on delete set null,
  event_name text not null,
  event_time timestamptz not null default now(),
  source text not null default 'munea-api',
  session_id text,
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.daily_user_metrics (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid references public.persons(id) on delete set null,
  metric_date date not null,
  meaningful_companion_day boolean not null default false,
  voice_sessions integer not null default 0 check (voice_sessions >= 0),
  voice_minutes numeric not null default 0 check (voice_minutes >= 0),
  routine_completions integer not null default 0 check (routine_completions >= 0),
  family_interactions integer not null default 0 check (family_interactions >= 0),
  avatar_sessions integer not null default 0 check (avatar_sessions >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (account_id, person_id, metric_date)
);

create table if not exists public.voice_session_metrics (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid references public.persons(id) on delete set null,
  voice_session_id uuid references public.voice_sessions(id) on delete set null,
  provider text not null,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  duration_ms integer not null default 0 check (duration_ms >= 0),
  turn_count integer not null default 0 check (turn_count >= 0),
  fallback_used boolean not null default false,
  interruption_count integer not null default 0 check (interruption_count >= 0),
  success boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.reminder_events (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid references public.persons(id) on delete set null,
  routine_reminder_id uuid references public.routine_reminders(id) on delete set null,
  event_type text not null check (event_type in ('sent', 'acknowledged', 'completed', 'missed', 'snoozed')),
  event_time timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.family_interaction_events (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid references public.persons(id) on delete set null,
  family_group_id uuid references public.family_groups(id) on delete set null,
  actor_person_id uuid references public.persons(id) on delete set null,
  event_type text not null check (event_type in ('invite_sent', 'invite_accepted', 'dashboard_viewed', 'message_sent', 'message_viewed', 'safety_notification_sent')),
  event_time timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.cost_ledger (
  id uuid primary key default gen_random_uuid(),
  account_id uuid references public.accounts(id) on delete set null,
  person_id uuid references public.persons(id) on delete set null,
  cost_time timestamptz not null default now(),
  provider text not null,
  service text not null check (service in ('llm', 'tts', 'stt', 'avatar', 'storage', 'push', 'other')),
  units numeric not null default 0 check (units >= 0),
  unit_name text not null default 'unit',
  amount_usd numeric not null default 0 check (amount_usd >= 0),
  source_ref text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.admin_notes (
  id uuid primary key default gen_random_uuid(),
  account_id uuid references public.accounts(id) on delete set null,
  actor_user_id uuid references auth.users(id) on delete set null,
  note_type text not null default 'general',
  body text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  deleted_at timestamptz
);

drop trigger if exists daily_user_metrics_set_updated_at on public.daily_user_metrics;
create trigger daily_user_metrics_set_updated_at
  before update on public.daily_user_metrics
  for each row execute function public.set_updated_at();

alter table public.product_events enable row level security;
alter table public.daily_user_metrics enable row level security;
alter table public.voice_session_metrics enable row level security;
alter table public.reminder_events enable row level security;
alter table public.family_interaction_events enable row level security;
alter table public.cost_ledger enable row level security;
alter table public.admin_notes enable row level security;

revoke all on public.product_events from anon;
revoke all on public.daily_user_metrics from anon;
revoke all on public.voice_session_metrics from anon;
revoke all on public.reminder_events from anon;
revoke all on public.family_interaction_events from anon;
revoke all on public.cost_ledger from anon;
revoke all on public.admin_notes from anon;

grant select, insert, update, delete on public.product_events to authenticated;
grant select, insert, update, delete on public.daily_user_metrics to authenticated;
grant select, insert, update, delete on public.voice_session_metrics to authenticated;
grant select, insert, update, delete on public.reminder_events to authenticated;
grant select, insert, update, delete on public.family_interaction_events to authenticated;
grant select on public.cost_ledger to authenticated;
grant select on public.admin_notes to authenticated;

drop policy if exists product_events_account_member_all on public.product_events;
create policy product_events_account_member_all
on public.product_events for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = product_events.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = product_events.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists daily_user_metrics_account_member_select on public.daily_user_metrics;
create policy daily_user_metrics_account_member_select
on public.daily_user_metrics for select
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = daily_user_metrics.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists voice_session_metrics_account_member_select on public.voice_session_metrics;
create policy voice_session_metrics_account_member_select
on public.voice_session_metrics for select
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = voice_session_metrics.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists reminder_events_account_member_all on public.reminder_events;
create policy reminder_events_account_member_all
on public.reminder_events for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = reminder_events.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = reminder_events.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists family_interaction_events_account_member_all on public.family_interaction_events;
create policy family_interaction_events_account_member_all
on public.family_interaction_events for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_interaction_events.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_interaction_events.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists cost_ledger_account_member_select on public.cost_ledger;
create policy cost_ledger_account_member_select
on public.cost_ledger for select
to authenticated
using (
  account_id is not null
  and exists (
    select 1 from public.account_members am
    where am.account_id = cost_ledger.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists admin_notes_account_member_select on public.admin_notes;
create policy admin_notes_account_member_select
on public.admin_notes for select
to authenticated
using (
  account_id is not null
  and exists (
    select 1 from public.account_members am
    where am.account_id = admin_notes.account_id
      and am.user_id = (select auth.uid())
      and am.role in ('owner', 'admin')
      and am.status = 'active'
  )
);

create index if not exists product_events_account_time_idx on public.product_events(account_id, event_time desc);
create index if not exists product_events_name_time_idx on public.product_events(event_name, event_time desc);
create index if not exists product_events_person_time_idx on public.product_events(person_id, event_time desc);
create index if not exists daily_user_metrics_account_date_idx on public.daily_user_metrics(account_id, metric_date desc);
create index if not exists voice_session_metrics_account_time_idx on public.voice_session_metrics(account_id, started_at desc);
create index if not exists reminder_events_account_time_idx on public.reminder_events(account_id, event_time desc);
create index if not exists family_interaction_events_account_time_idx on public.family_interaction_events(account_id, event_time desc);
create index if not exists cost_ledger_account_time_idx on public.cost_ledger(account_id, cost_time desc);
create index if not exists admin_notes_account_time_idx on public.admin_notes(account_id, created_at desc);

commit;
