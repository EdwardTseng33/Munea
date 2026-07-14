-- Munea family cloud state foundation.
-- Run after 001_initial_munea_schema.sql through 006_billing_credits_foundation.sql.
-- This is the Codex-owned 007 DDL bridge for family linking, consent, wellbeing,
-- and the current /family/state local JSON prototype.

begin;

alter table public.persons
  add column if not exists auth_user_id uuid references auth.users(id) on delete set null;

alter table public.persons
  add column if not exists region_code text;

alter table public.persons
  add column if not exists attributes jsonb not null default '{}'::jsonb;

create unique index if not exists persons_account_auth_user_idx
  on public.persons(account_id, auth_user_id)
  where auth_user_id is not null;

create index if not exists persons_auth_user_id_idx
  on public.persons(auth_user_id)
  where auth_user_id is not null;

create table if not exists public.family_invitations (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  family_group_id uuid not null references public.family_groups(id) on delete cascade,
  inviter_person_id uuid references public.persons(id) on delete set null,
  invitee_person_id uuid references public.persons(id) on delete set null,
  token_hash text not null unique,
  short_code text not null check (short_code ~ '^[0-9]{6}$'),
  delivery_hint text,
  elder_assisted boolean not null default false,
  status text not null default 'pending' check (status in ('pending', 'applied', 'accepted', 'rejected', 'revoked', 'expired')),
  expires_at timestamptz not null default (now() + interval '72 hours'),
  accepted_at timestamptz,
  revoked_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.consent_records (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid not null references public.persons(id) on delete cascade,
  family_group_id uuid references public.family_groups(id) on delete set null,
  consent_type text not null,
  consent_version text not null default 'v1',
  status text not null default 'granted' check (status in ('granted', 'revoked', 'expired')),
  granted_by_person_id uuid references public.persons(id) on delete set null,
  source text not null default 'munea-api',
  scope jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.wellbeing_signals (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid not null references public.persons(id) on delete cascade,
  family_group_id uuid references public.family_groups(id) on delete set null,
  signal_date date not null default current_date,
  signal_type text not null default 'mood',
  mood text check (mood is null or mood in ('happy', 'pleasant', 'steady', 'tired', 'low', 'irritated', 'mixed', 'unknown')),
  level numeric check (level is null or (level >= 1 and level <= 5)),
  visibility text not null default 'family_summary' check (visibility in ('self', 'family_summary', 'private')),
  facts jsonb not null default '{}'::jsonb,
  source text not null default 'munea-api',
  observed_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.family_state_entries (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  family_group_id uuid not null references public.family_groups(id) on delete cascade,
  state_key text not null check (state_key in ('circle', 'activities', 'familyFeed', 'meds', 'visit', 'routine', 'wallet')),
  value jsonb not null default '{}'::jsonb,
  updated_by_person_id uuid references public.persons(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (account_id, family_group_id, state_key)
);

create table if not exists public.family_activities (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  family_group_id uuid not null references public.family_groups(id) on delete cascade,
  owner_person_id uuid references public.persons(id) on delete set null,
  activity_type text not null default 'custom' check (activity_type in ('walk', 'quiz', 'event', 'vote', 'draw', 'custom')),
  title text not null,
  status text not null default 'draft' check (status in ('draft', 'active', 'completed', 'archived', 'cancelled')),
  starts_at timestamptz,
  ends_at timestamptz,
  payload jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);

create table if not exists public.family_activity_participants (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  family_activity_id uuid not null references public.family_activities(id) on delete cascade,
  person_id uuid not null references public.persons(id) on delete cascade,
  role text not null default 'participant' check (role in ('owner', 'participant', 'viewer')),
  status text not null default 'invited' check (status in ('invited', 'accepted', 'declined', 'completed')),
  contribution jsonb not null default '{}'::jsonb,
  response jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (family_activity_id, person_id)
);

drop trigger if exists family_invitations_set_updated_at on public.family_invitations;
create trigger family_invitations_set_updated_at
  before update on public.family_invitations
  for each row execute function public.set_updated_at();

drop trigger if exists family_state_entries_set_updated_at on public.family_state_entries;
create trigger family_state_entries_set_updated_at
  before update on public.family_state_entries
  for each row execute function public.set_updated_at();

drop trigger if exists family_activities_set_updated_at on public.family_activities;
create trigger family_activities_set_updated_at
  before update on public.family_activities
  for each row execute function public.set_updated_at();

drop trigger if exists family_activity_participants_set_updated_at on public.family_activity_participants;
create trigger family_activity_participants_set_updated_at
  before update on public.family_activity_participants
  for each row execute function public.set_updated_at();

alter table public.family_invitations enable row level security;
alter table public.consent_records enable row level security;
alter table public.wellbeing_signals enable row level security;
alter table public.family_state_entries enable row level security;
alter table public.family_activities enable row level security;
alter table public.family_activity_participants enable row level security;

revoke all on public.family_invitations from anon;
revoke all on public.consent_records from anon;
revoke all on public.wellbeing_signals from anon;
revoke all on public.family_state_entries from anon;
revoke all on public.family_activities from anon;
revoke all on public.family_activity_participants from anon;

grant select, insert, update, delete on public.family_invitations to authenticated;
grant select, insert, update, delete on public.consent_records to authenticated;
grant select, insert, update, delete on public.wellbeing_signals to authenticated;
grant select, insert, update, delete on public.family_state_entries to authenticated;
grant select, insert, update, delete on public.family_activities to authenticated;
grant select, insert, update, delete on public.family_activity_participants to authenticated;

drop policy if exists family_invitations_account_member_all on public.family_invitations;
create policy family_invitations_account_member_all
on public.family_invitations for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_invitations.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_invitations.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists consent_records_account_member_all on public.consent_records;
create policy consent_records_account_member_all
on public.consent_records for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = consent_records.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = consent_records.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists wellbeing_signals_account_member_all on public.wellbeing_signals;
create policy wellbeing_signals_account_member_all
on public.wellbeing_signals for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = wellbeing_signals.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = wellbeing_signals.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists family_state_entries_account_member_all on public.family_state_entries;
create policy family_state_entries_account_member_all
on public.family_state_entries for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_state_entries.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_state_entries.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists family_activities_account_member_all on public.family_activities;
create policy family_activities_account_member_all
on public.family_activities for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_activities.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_activities.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

drop policy if exists family_activity_participants_account_member_all on public.family_activity_participants;
create policy family_activity_participants_account_member_all
on public.family_activity_participants for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_activity_participants.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = family_activity_participants.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

create unique index if not exists family_invitations_pending_short_code_idx
  on public.family_invitations(family_group_id, short_code)
  where status = 'pending';

create index if not exists family_invitations_account_status_idx
  on public.family_invitations(account_id, status, expires_at);

create index if not exists consent_records_person_type_idx
  on public.consent_records(account_id, person_id, consent_type, status);

create index if not exists wellbeing_signals_person_date_idx
  on public.wellbeing_signals(account_id, person_id, signal_date desc);

create index if not exists family_state_entries_family_idx
  on public.family_state_entries(account_id, family_group_id, state_key);

create index if not exists family_activities_family_status_idx
  on public.family_activities(account_id, family_group_id, status, starts_at desc);

create index if not exists family_activity_participants_activity_idx
  on public.family_activity_participants(family_activity_id, status);

commit;
