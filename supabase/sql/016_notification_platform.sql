-- Durable notification inbox, APNs device registry and retryable delivery outbox.
-- Sensitive details stay in the event; public_title/public_body are safe for lock screens.

begin;

create table if not exists public.push_devices (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid not null references public.persons(id) on delete cascade,
  auth_user_id uuid not null,
  platform text not null default 'ios' check (platform in ('ios')),
  environment text not null check (environment in ('sandbox', 'production')),
  bundle_id text not null,
  token text not null,
  token_hash text not null,
  app_version text,
  locale text not null default 'zh-TW',
  timezone text not null default 'Asia/Taipei',
  permission_status text not null default 'not_determined'
    check (permission_status in ('not_determined', 'denied', 'authorized', 'provisional', 'ephemeral')),
  notifications_enabled boolean not null default false,
  show_sensitive_content boolean not null default false,
  last_seen_at timestamptz not null default now(),
  invalidated_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (token_hash, environment, bundle_id)
);

drop trigger if exists push_devices_set_updated_at on public.push_devices;
create trigger push_devices_set_updated_at
  before update on public.push_devices
  for each row execute function public.set_updated_at();

create index if not exists push_devices_recipient_active_idx
  on public.push_devices(person_id, notifications_enabled, invalidated_at);

alter table public.push_devices enable row level security;
revoke all on public.push_devices from anon, authenticated;

comment on table public.push_devices is
  'Backend-only APNs tokens. App clients receive sanitized device status and never read tokens directly.';


create table if not exists public.notification_events (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  recipient_person_id uuid not null references public.persons(id) on delete cascade,
  actor_person_id uuid references public.persons(id) on delete set null,
  family_group_id uuid references public.family_groups(id) on delete set null,
  event_type text not null check (event_type in (
    'family_relay',
    'invitation_applied',
    'invitation_decided',
    'medication_due',
    'medication_missed',
    'clinic_upcoming',
    'family_activity',
    'health_alert'
  )),
  resource_type text,
  resource_id text,
  title text not null,
  body text not null,
  public_title text not null default '沐寧提醒',
  public_body text not null default '你的健康提醒到了，解鎖後查看。',
  sensitivity text not null default 'private'
    check (sensitivity in ('public', 'private', 'health_sensitive')),
  deep_link text not null,
  dedupe_key text,
  metadata jsonb not null default '{}'::jsonb,
  expires_at timestamptz,
  read_at timestamptz,
  archived_at timestamptz,
  acted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists notification_events_set_updated_at on public.notification_events;
create trigger notification_events_set_updated_at
  before update on public.notification_events
  for each row execute function public.set_updated_at();

create unique index if not exists notification_events_recipient_dedupe_idx
  on public.notification_events(recipient_person_id, dedupe_key)
  where dedupe_key is not null;
create index if not exists notification_events_inbox_idx
  on public.notification_events(recipient_person_id, archived_at, created_at desc);

alter table public.notification_events enable row level security;

drop policy if exists notification_events_recipient_select on public.notification_events;
create policy notification_events_recipient_select
on public.notification_events for select
to authenticated
using (
  exists (
    select 1 from public.persons p
    where p.id = notification_events.recipient_person_id
      and p.auth_user_id = (select auth.uid())
  )
);

revoke all on public.notification_events from anon;
revoke insert, update, delete on public.notification_events from authenticated;
grant select on public.notification_events to authenticated;

comment on table public.notification_events is
  'Source of truth for the in-app notification inbox; push delivery is only a transport.';


create table if not exists public.notification_deliveries (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.notification_events(id) on delete cascade,
  device_id uuid not null references public.push_devices(id) on delete cascade,
  channel text not null default 'apns' check (channel in ('apns')),
  status text not null default 'queued'
    check (status in ('queued', 'sending', 'accepted', 'failed', 'invalid_token', 'opened', 'actioned', 'suppressed')),
  attempt_count integer not null default 0 check (attempt_count between 0 and 100),
  next_attempt_at timestamptz not null default now(),
  last_attempt_at timestamptz,
  accepted_at timestamptz,
  opened_at timestamptz,
  acted_at timestamptz,
  apns_id text,
  error_code text,
  error_detail text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (event_id, device_id, channel)
);

drop trigger if exists notification_deliveries_set_updated_at on public.notification_deliveries;
create trigger notification_deliveries_set_updated_at
  before update on public.notification_deliveries
  for each row execute function public.set_updated_at();

create index if not exists notification_deliveries_outbox_idx
  on public.notification_deliveries(status, next_attempt_at, created_at);

alter table public.notification_deliveries enable row level security;
revoke all on public.notification_deliveries from anon, authenticated;

comment on table public.notification_deliveries is
  'Retryable APNs outbox. accepted means APNs accepted the request, not that the device displayed it.';


create or replace function public.enqueue_notification_event(
  p_recipient_person_id uuid,
  p_event_type text,
  p_title text,
  p_body text,
  p_public_title text,
  p_public_body text,
  p_sensitivity text,
  p_deep_link text,
  p_actor_person_id uuid default null,
  p_family_group_id uuid default null,
  p_resource_type text default null,
  p_resource_id text default null,
  p_dedupe_key text default null,
  p_metadata jsonb default '{}'::jsonb,
  p_expires_at timestamptz default null
)
returns public.notification_events
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_account_id uuid;
  v_event public.notification_events;
begin
  select p.account_id into v_account_id
  from public.persons p
  where p.id = p_recipient_person_id;

  if v_account_id is null then
    raise exception 'notification_recipient_not_found';
  end if;

  if p_family_group_id is not null
     and p_event_type not in ('invitation_applied', 'invitation_decided') then
    if not exists (
      select 1 from public.family_memberships fm
      where fm.family_group_id = p_family_group_id
        and fm.person_id = p_recipient_person_id
    ) then
      raise exception 'notification_recipient_not_in_family';
    end if;
    if p_actor_person_id is not null and not exists (
      select 1 from public.family_memberships fm
      where fm.family_group_id = p_family_group_id
        and fm.person_id = p_actor_person_id
    ) then
      raise exception 'notification_actor_not_in_family';
    end if;
  end if;

  insert into public.notification_events (
    account_id, recipient_person_id, actor_person_id, family_group_id,
    event_type, resource_type, resource_id, title, body,
    public_title, public_body, sensitivity, deep_link, dedupe_key,
    metadata, expires_at
  ) values (
    v_account_id, p_recipient_person_id, p_actor_person_id, p_family_group_id,
    p_event_type, p_resource_type, p_resource_id, p_title, p_body,
    p_public_title, p_public_body, p_sensitivity, p_deep_link, p_dedupe_key,
    coalesce(p_metadata, '{}'::jsonb), p_expires_at
  )
  on conflict (recipient_person_id, dedupe_key) where dedupe_key is not null
  do update set updated_at = public.notification_events.updated_at
  returning * into v_event;

  insert into public.notification_deliveries (event_id, device_id)
  select v_event.id, d.id
  from public.push_devices d
  where d.person_id = p_recipient_person_id
    and d.notifications_enabled
    and d.permission_status in ('authorized', 'provisional')
    and d.invalidated_at is null
  on conflict (event_id, device_id, channel) do nothing;

  return v_event;
end;
$$;

revoke all on function public.enqueue_notification_event(
  uuid, text, text, text, text, text, text, text,
  uuid, uuid, text, text, text, jsonb, timestamptz
) from public, anon, authenticated;
grant execute on function public.enqueue_notification_event(
  uuid, text, text, text, text, text, text, text,
  uuid, uuid, text, text, text, jsonb, timestamptz
) to service_role;


create or replace function public.notify_family_relay_created()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform public.enqueue_notification_event(
    new.recipient_person_id,
    'family_relay',
    new.sender_label || '捎來一則話',
    new.content,
    '沐寧提醒',
    '家人捎來一則訊息，解鎖後收聽。',
    'private',
    'munea://relay/' || new.id::text,
    new.sender_person_id,
    new.family_group_id,
    'family_relay_message',
    new.id::text,
    'family-relay:' || new.id::text,
    jsonb_build_object('source', new.source),
    new.expires_at
  );
  return new;
end;
$$;

drop trigger if exists family_relay_messages_enqueue_notification on public.family_relay_messages;
create trigger family_relay_messages_enqueue_notification
  after insert on public.family_relay_messages
  for each row execute function public.notify_family_relay_created();

revoke all on function public.notify_family_relay_created() from public, anon, authenticated;


create or replace function public.notify_family_invitation_changed()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.status = 'applied'
     and new.status is distinct from old.status
     and new.inviter_person_id is not null
     and new.invitee_person_id is not null then
    perform public.enqueue_notification_event(
      new.inviter_person_id,
      'invitation_applied',
      '有人申請加入家庭照護圈',
      '請開啟沐寧查看並決定是否通過。',
      '沐寧提醒',
      '你有一則家庭照護圈通知。',
      'private',
      'munea://family/invitations/' || new.id::text,
      new.invitee_person_id,
      new.family_group_id,
      'family_invitation',
      new.id::text,
      'family-invitation-applied:' || new.id::text,
      '{}'::jsonb,
      new.expires_at
    );
  elsif new.status in ('accepted', 'rejected')
        and new.status is distinct from old.status
        and new.inviter_person_id is not null
        and new.invitee_person_id is not null then
    perform public.enqueue_notification_event(
      new.invitee_person_id,
      'invitation_decided',
      case when new.status = 'accepted' then '家庭照護圈申請已通過' else '家庭照護圈申請未通過' end,
      case when new.status = 'accepted' then '你現在可以在沐寧查看家庭照護圈。' else '請向邀請人確認或重新申請。' end,
      '沐寧提醒',
      '你的家庭照護圈申請有新進度。',
      'private',
      'munea://family/invitations/' || new.id::text,
      new.inviter_person_id,
      new.family_group_id,
      'family_invitation',
      new.id::text,
      'family-invitation-decided:' || new.id::text || ':' || new.status,
      jsonb_build_object('decision', new.status),
      new.expires_at
    );
  end if;
  return new;
end;
$$;

drop trigger if exists family_invitations_enqueue_notification on public.family_invitations;
create trigger family_invitations_enqueue_notification
  after update of status on public.family_invitations
  for each row execute function public.notify_family_invitation_changed();

revoke all on function public.notify_family_invitation_changed() from public, anon, authenticated;


create or replace function public.claim_notification_deliveries(p_limit integer default 50)
returns table (
  delivery_id uuid,
  event_id uuid,
  device_id uuid,
  token text,
  environment text,
  bundle_id text,
  show_sensitive_content boolean,
  event_type text,
  title text,
  body text,
  public_title text,
  public_body text,
  sensitivity text,
  deep_link text,
  resource_id text,
  metadata jsonb,
  attempt_count integer
)
language plpgsql
security definer
set search_path = ''
as $$
begin
  return query
  with candidates as (
    select d.id
    from public.notification_deliveries d
    where (
      (d.status in ('queued', 'failed') and d.next_attempt_at <= now())
      or (d.status = 'sending' and d.last_attempt_at < now() - interval '5 minutes')
    )
      and d.attempt_count < 10
    order by d.next_attempt_at, d.created_at
    for update skip locked
    limit greatest(1, least(coalesce(p_limit, 50), 200))
  ), claimed as (
    update public.notification_deliveries d
    set status = 'sending',
        attempt_count = d.attempt_count + 1,
        last_attempt_at = now(),
        error_code = null,
        error_detail = null
    from candidates c
    where d.id = c.id
    returning d.*
  )
  select
    c.id, c.event_id, c.device_id, pd.token, pd.environment, pd.bundle_id,
    pd.show_sensitive_content, ne.event_type, ne.title, ne.body,
    ne.public_title, ne.public_body, ne.sensitivity, ne.deep_link,
    ne.resource_id, ne.metadata, c.attempt_count
  from claimed c
  join public.push_devices pd on pd.id = c.device_id
  join public.notification_events ne on ne.id = c.event_id
  where pd.invalidated_at is null
    and pd.notifications_enabled
    and (ne.expires_at is null or ne.expires_at > now());
end;
$$;

revoke all on function public.claim_notification_deliveries(integer) from public, anon, authenticated;
grant execute on function public.claim_notification_deliveries(integer) to service_role;


create or replace function public.complete_notification_delivery(
  p_delivery_id uuid,
  p_status text,
  p_apns_id text default null,
  p_error_code text default null,
  p_error_detail text default null,
  p_retry_after_seconds integer default null
)
returns public.notification_deliveries
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_delivery public.notification_deliveries;
begin
  if p_status not in ('accepted', 'failed', 'invalid_token', 'suppressed') then
    raise exception 'notification_delivery_status_invalid';
  end if;

  update public.notification_deliveries d
  set status = p_status,
      apns_id = p_apns_id,
      error_code = p_error_code,
      error_detail = left(p_error_detail, 500),
      accepted_at = case when p_status = 'accepted' then now() else d.accepted_at end,
      next_attempt_at = case
        when p_status = 'failed' then now() + make_interval(secs => greatest(30, least(coalesce(p_retry_after_seconds, 60), 86400)))
        else d.next_attempt_at
      end
  where d.id = p_delivery_id
  returning * into v_delivery;

  if v_delivery.id is null then
    raise exception 'notification_delivery_not_found';
  end if;

  if p_status = 'invalid_token' then
    update public.push_devices
    set notifications_enabled = false, invalidated_at = now()
    where id = v_delivery.device_id;
  end if;

  return v_delivery;
end;
$$;

revoke all on function public.complete_notification_delivery(uuid, text, text, text, text, integer)
  from public, anon, authenticated;
grant execute on function public.complete_notification_delivery(uuid, text, text, text, text, integer)
  to service_role;

commit;
