-- Durable medication dose occurrences for Home, Status, reminders and history.
-- Reminder definitions remain in routine_reminders; this table records each dose.

begin;

create table if not exists public.medication_dose_events (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid not null references public.persons(id) on delete cascade,
  routine_reminder_id uuid references public.routine_reminders(id) on delete set null,
  dose_key text not null,
  medication_name text not null,
  slot_label text,
  scheduled_date date not null,
  scheduled_at timestamptz,
  expected_count integer not null default 0 check (expected_count between 0 and 100),
  status text not null default 'scheduled'
    check (status in ('scheduled', 'taken', 'snoozed', 'skipped', 'missed')),
  taken_at timestamptz,
  source text not null default 'munea-app',
  timezone text not null default 'Asia/Taipei',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (account_id, person_id, dose_key)
);

drop trigger if exists medication_dose_events_set_updated_at on public.medication_dose_events;
create trigger medication_dose_events_set_updated_at
  before update on public.medication_dose_events
  for each row execute function public.set_updated_at();

alter table public.medication_dose_events enable row level security;

drop policy if exists medication_dose_events_account_member_all on public.medication_dose_events;
create policy medication_dose_events_account_member_all
on public.medication_dose_events for all
to authenticated
using (
  exists (
    select 1 from public.account_members am
    where am.account_id = medication_dose_events.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
  and exists (
    select 1 from public.persons p
    where p.id = medication_dose_events.person_id
      and p.account_id = medication_dose_events.account_id
  )
)
with check (
  exists (
    select 1 from public.account_members am
    where am.account_id = medication_dose_events.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
  and exists (
    select 1 from public.persons p
    where p.id = medication_dose_events.person_id
      and p.account_id = medication_dose_events.account_id
  )
);

revoke all on public.medication_dose_events from anon;
grant select, insert, update, delete on public.medication_dose_events to authenticated;

create index if not exists medication_dose_events_person_date_idx
  on public.medication_dose_events(account_id, person_id, scheduled_date desc);
create index if not exists medication_dose_events_status_idx
  on public.medication_dose_events(account_id, person_id, status, scheduled_date desc);

comment on table public.medication_dose_events is
  'One idempotent record per scheduled medication dose; independent from Apple Health.';

commit;
