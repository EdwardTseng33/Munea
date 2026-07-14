-- Recipient-specific family messages spoken by the companion on the next call.

begin;

create table if not exists public.family_relay_messages (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  family_group_id uuid not null references public.family_groups(id) on delete cascade,
  sender_person_id uuid not null references public.persons(id) on delete cascade,
  recipient_person_id uuid not null references public.persons(id) on delete cascade,
  sender_label text not null,
  recipient_label text not null,
  content text not null check (char_length(content) between 2 and 240),
  status text not null default 'pending'
    check (status in ('pending', 'claimed', 'delivered', 'cancelled', 'reported', 'expired')),
  source text not null default 'voice-ai',
  claim_token uuid,
  claimed_at timestamptz,
  delivered_at timestamptz,
  cancelled_at timestamptz,
  expires_at timestamptz not null default (now() + interval '7 days'),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (sender_person_id <> recipient_person_id)
);

drop trigger if exists family_relay_messages_set_updated_at on public.family_relay_messages;
create trigger family_relay_messages_set_updated_at
  before update on public.family_relay_messages
  for each row execute function public.set_updated_at();

alter table public.family_relay_messages enable row level security;

drop policy if exists family_relay_messages_participant_select on public.family_relay_messages;
create policy family_relay_messages_participant_select
on public.family_relay_messages for select
to authenticated
using (
  exists (
    select 1 from public.persons p
    where p.auth_user_id = (select auth.uid())
      and p.id in (family_relay_messages.sender_person_id, family_relay_messages.recipient_person_id)
  )
);

revoke all on public.family_relay_messages from anon;
revoke insert, update, delete on public.family_relay_messages from authenticated;
grant select on public.family_relay_messages to authenticated;

create index if not exists family_relay_recipient_pending_idx
  on public.family_relay_messages(family_group_id, recipient_person_id, status, created_at)
  where status in ('pending', 'claimed');
create index if not exists family_relay_sender_idx
  on public.family_relay_messages(sender_person_id, created_at desc);

comment on table public.family_relay_messages is
  'Verified sender-attributed family relays; one pending message is claimed and spoken at the recipient next call.';

commit;
