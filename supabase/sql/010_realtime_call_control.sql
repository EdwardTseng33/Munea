-- Munea realtime Voice + Avatar call-control foundation.
-- Run after 001_initial_munea_schema.sql and 006_billing_credits_foundation.sql.
-- The control plane is durable in Postgres; media still flows App <-> Voice/Avatar directly.

begin;

create table if not exists public.capacity_profiles (
  id uuid primary key default gen_random_uuid(),
  profile_key text not null unique,
  provider text not null,
  region text not null,
  gpu_model text not null,
  model_name text not null,
  model_commit text,
  resolution integer not null check (resolution = 640),
  compile_mode boolean not null default true,
  safe_slots integer not null check (safe_slots > 0),
  p50_ms numeric,
  p95_ms numeric,
  headroom_pct numeric,
  approved boolean not null default false,
  evidence_url text,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.gpu_workers (
  worker_id text primary key,
  provider_instance_id text,
  profile_id uuid references public.capacity_profiles(id) on delete restrict,
  url text not null,
  region text not null,
  provider text not null,
  status text not null check (status in ('starting','warming','ready','draining','unhealthy','terminated')),
  capacity integer not null check (capacity > 0),
  active_leases integer not null default 0 check (active_leases >= 0),
  last_heartbeat_at timestamptz,
  ready_at timestamptz,
  idle_since timestamptz,
  hourly_cost numeric,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.voice_shards (
  shard_id text primary key,
  url text not null,
  provider text not null default 'gemini-live',
  region text not null,
  status text not null check (status in ('ready','draining','unhealthy','disabled')),
  capacity integer not null check (capacity > 0),
  active_leases integer not null default 0 check (active_leases >= 0),
  last_heartbeat_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.call_leases (
  call_id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid references public.persons(id) on delete set null,
  user_id uuid not null references auth.users(id) on delete cascade,
  character_id text not null,
  state text not null check (state in ('reserved','connecting','active','ending','ended','failed')),
  voice_shard_id text not null references public.voice_shards(shard_id) on delete restrict,
  worker_id text not null references public.gpu_workers(worker_id) on delete restrict,
  slot_id integer not null check (slot_id > 0),
  lease_version integer not null default 1 check (lease_version > 0),
  idempotency_key text not null,
  lease_expires_at timestamptz not null,
  last_heartbeat_at timestamptz not null default now(),
  voice_ready_at timestamptz,
  avatar_ready_at timestamptz,
  active_at timestamptz,
  ended_at timestamptz,
  billable_seconds integer not null default 0 check (billable_seconds >= 0),
  billed_credits numeric not null default 0 check (billed_credits >= 0),
  end_reason text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (account_id, idempotency_key)
);

create unique index if not exists call_leases_worker_slot_live_idx
  on public.call_leases(worker_id, slot_id)
  where state in ('reserved','connecting','active','ending');

create table if not exists public.call_queue (
  call_id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid references public.persons(id) on delete set null,
  user_id uuid not null references auth.users(id) on delete cascade,
  character_id text not null,
  idempotency_key text not null,
  state text not null default 'queued' check (state in ('queued','cancelled','expired','promoted')),
  enqueued_at timestamptz not null default now(),
  last_heartbeat_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  unique (account_id, idempotency_key)
);

create table if not exists public.call_component_events (
  event_id text primary key,
  call_id uuid not null references public.call_leases(call_id) on delete cascade,
  component text not null check (component in ('app','voice','avatar','reaper','controller')),
  event_type text not null,
  lease_version integer not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.call_credit_holds (
  call_id uuid primary key references public.call_leases(call_id) on delete cascade,
  account_id uuid not null references public.accounts(id) on delete cascade,
  amount numeric not null check (amount > 0),
  state text not null default 'held' check (state in ('held','settled','released')),
  created_at timestamptz not null default now(),
  settled_at timestamptz
);

create table if not exists public.provider_operations (
  operation_id text primary key,
  provider text not null,
  operation_type text not null check (operation_type in ('start','create','warm','register','drain','stop','terminate')),
  target_id text,
  status text not null check (status in ('pending','running','succeeded','failed','cancelled')),
  attempts integer not null default 0,
  budget_limit numeric,
  error text,
  details jsonb not null default '{}'::jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists call_leases_state_expiry_idx on public.call_leases(state, lease_expires_at);
create index if not exists call_queue_live_idx on public.call_queue(state, enqueued_at);
create index if not exists gpu_workers_ready_idx on public.gpu_workers(status, active_leases, capacity);
create index if not exists voice_shards_ready_idx on public.voice_shards(status, active_leases, capacity);

alter table public.capacity_profiles enable row level security;
alter table public.gpu_workers enable row level security;
alter table public.voice_shards enable row level security;
alter table public.call_leases enable row level security;
alter table public.call_queue enable row level security;
alter table public.call_component_events enable row level security;
alter table public.call_credit_holds enable row level security;
alter table public.provider_operations enable row level security;

revoke all on public.capacity_profiles, public.gpu_workers, public.voice_shards,
  public.call_leases, public.call_queue, public.call_component_events,
  public.call_credit_holds, public.provider_operations from anon, authenticated;

create or replace function public.munea_call_consume_credit(
  p_call_id uuid,
  p_account_id uuid,
  p_person_id uuid,
  p_minute integer
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_wallet record;
  v_available numeric;
  v_holds numeric;
  v_remaining numeric := 1;
  v_take numeric;
  v_tx_id uuid;
begin
  if exists (
    select 1 from public.credit_transactions
    where idempotency_key like 'call:' || p_call_id::text || ':minute:' || p_minute::text || ':%'
  ) then
    return true;
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_account_id::text, 724338221)
  );
  perform 1
  from public.credit_wallets
  where account_id = p_account_id
    and status = 'active'
    and balance > 0
    and (expires_at is null or expires_at > now())
    and (person_id is null or p_person_id is null or person_id = p_person_id)
  order by id
  for update;

  select coalesce(sum(balance), 0) into v_available
  from public.credit_wallets
  where account_id = p_account_id
    and status = 'active'
    and balance > 0
    and (expires_at is null or expires_at > now())
    and (person_id is null or p_person_id is null or person_id = p_person_id);
  select coalesce(sum(amount), 0) into v_holds
  from public.call_credit_holds
  where account_id = p_account_id
    and state = 'held'
    and call_id <> p_call_id;
  if v_available - v_holds < 1 then
    raise exception 'insufficient_credits';
  end if;

  for v_wallet in
    select * from public.credit_wallets
    where account_id = p_account_id
      and status = 'active'
      and balance > 0
      and (expires_at is null or expires_at > now())
      and (person_id is null or p_person_id is null or person_id = p_person_id)
    order by case wallet_type when 'included_monthly' then 0 else 1 end,
      expires_at nulls last, id
    for update
  loop
    exit when v_remaining <= 0;
    v_take := least(v_wallet.balance, v_remaining);
    update public.credit_wallets
      set balance = balance - v_take, updated_at = now()
      where id = v_wallet.id;
    insert into public.credit_transactions (
      account_id, person_id, wallet_id, transaction_type, source, amount,
      balance_after, idempotency_key, reason, metadata
    ) values (
      p_account_id, p_person_id, v_wallet.id, 'consume', 'system', v_take,
      v_wallet.balance - v_take,
      'call:' || p_call_id::text || ':minute:' || p_minute::text || ':' || v_wallet.id::text,
      'realtime_voice_avatar_minute',
      pg_catalog.jsonb_build_object('callId', p_call_id, 'minute', p_minute)
    ) returning id into v_tx_id;
    insert into public.credit_ledger (
      account_id, person_id, wallet_id, credit_transaction_id, event_type,
      amount, balance_after, feature, source_ref, metadata
    ) values (
      p_account_id, p_person_id, v_wallet.id, v_tx_id, 'credits_consumed',
      -v_take, v_wallet.balance - v_take, 'realtime_voice_avatar', p_call_id::text,
      pg_catalog.jsonb_build_object('minute', p_minute)
    );
    v_remaining := v_remaining - v_take;
  end loop;

  if v_remaining > 0 then
    raise exception 'insufficient_credits';
  end if;
  return true;
exception when unique_violation then
  return true;
end;
$$;

create or replace function public.munea_call_reap_expired()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_row record;
  v_count integer := 0;
  v_seconds integer;
  v_target integer;
  v_billed integer;
  v_minute integer;
  v_billing_error text;
begin
  perform pg_catalog.pg_advisory_xact_lock(724338221);
  for v_row in
    select * from public.call_leases
    where state in ('reserved','connecting','active','ending')
      and lease_expires_at < now()
    for update skip locked
  loop
    v_seconds := case when v_row.active_at is null then 0
      else floor(greatest(0, extract(epoch from (now() - v_row.active_at))))::integer end;
    v_target := case when v_row.active_at is null then 0
      else greatest(1, ceil(greatest(0, extract(epoch from (now() - v_row.active_at))) / 60.0)::integer) end;
    v_billed := v_row.billed_credits::integer;
    v_billing_error := null;
    if v_target > v_billed then
      for v_minute in (v_billed + 1)..v_target loop
        begin
          perform public.munea_call_consume_credit(
            v_row.call_id, v_row.account_id, v_row.person_id, v_minute
          );
          v_billed := v_minute;
        exception when raise_exception then
          if sqlerrm <> 'insufficient_credits' then
            raise;
          end if;
          v_billing_error := sqlerrm;
          exit;
        end;
      end loop;
    end if;
    update public.gpu_workers
      set active_leases = greatest(0, active_leases - 1), updated_at = now()
      where worker_id = v_row.worker_id;
    update public.voice_shards
      set active_leases = greatest(0, active_leases - 1), updated_at = now()
      where shard_id = v_row.voice_shard_id;
    update public.call_credit_holds
      set state = case when v_row.active_at is null then 'released' else 'settled' end,
          settled_at = coalesce(settled_at, now())
      where call_id = v_row.call_id and state = 'held';
    update public.call_leases
      set state = 'failed', ended_at = now(), end_reason = 'lease_expired',
          billable_seconds = v_seconds,
          billed_credits = greatest(billed_credits, v_billed),
          metadata = case when v_billing_error is null then metadata else metadata ||
            pg_catalog.jsonb_build_object(
              'billing_error', v_billing_error,
              'unbilled_started_minutes', greatest(0, v_target - v_billed)
            ) end,
          updated_at = now()
      where call_id = v_row.call_id;
    v_count := v_count + 1;
  end loop;
  update public.call_queue
    set state = 'expired'
    where state = 'queued' and last_heartbeat_at < now() - interval '45 seconds';
  return v_count;
end;
$$;

create or replace function public.munea_call_request(
  p_user_id uuid,
  p_person_id uuid,
  p_character_id text,
  p_idempotency_key text,
  p_queue_max integer default 30
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_account_id uuid;
  v_lease public.call_leases%rowtype;
  v_queue public.call_queue%rowtype;
  v_worker public.gpu_workers%rowtype;
  v_voice public.voice_shards%rowtype;
  v_slot integer;
  v_available numeric;
  v_holds numeric;
  v_position integer;
  v_depth integer;
  v_call_id uuid;
begin
  if coalesce(trim(p_idempotency_key), '') = '' then
    return pg_catalog.jsonb_build_object('status','reject','reason','idempotency_key_required');
  end if;
  perform pg_catalog.pg_advisory_xact_lock(724338221);
  perform public.munea_call_reap_expired();

  select am.account_id into v_account_id
  from public.account_members am
  where am.user_id = p_user_id and am.status = 'active'
  order by case am.role when 'owner' then 0 when 'admin' then 1 else 2 end
  limit 1;
  if v_account_id is null then
    return pg_catalog.jsonb_build_object('status','reject','reason','account_not_ready');
  end if;
  if p_person_id is not null and not exists (
    select 1 from public.persons p where p.id = p_person_id and p.account_id = v_account_id and p.deleted_at is null
  ) then
    return pg_catalog.jsonb_build_object('status','reject','reason','person_not_owned');
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_account_id::text, 724338221)
  );

  select * into v_lease from public.call_leases
  where account_id = v_account_id and idempotency_key = p_idempotency_key
    and state in ('reserved','connecting','active','ending')
  limit 1;
  if found then
    return pg_catalog.jsonb_build_object(
      'status','connect','call_id',v_lease.call_id,'lease_version',v_lease.lease_version,
      'slot_id',v_lease.slot_id,'state',v_lease.state,
      'worker',(select pg_catalog.jsonb_build_object('worker_id',w.worker_id,'url',w.url) from public.gpu_workers w where w.worker_id=v_lease.worker_id),
      'voice',(select pg_catalog.jsonb_build_object('shard_id',s.shard_id,'url',s.url) from public.voice_shards s where s.shard_id=v_lease.voice_shard_id)
    );
  end if;

  select * into v_queue from public.call_queue
  where account_id = v_account_id and idempotency_key = p_idempotency_key and state = 'queued'
  limit 1;
  if found then
    update public.call_queue set last_heartbeat_at = now() where call_id = v_queue.call_id;
    select count(*)::integer into v_position from public.call_queue
      where state='queued' and enqueued_at <= v_queue.enqueued_at;
    if v_position > 1 then
      select count(*)::integer into v_depth from public.call_queue where state='queued';
      return pg_catalog.jsonb_build_object('status','queued','call_id',v_queue.call_id,
        'queue',pg_catalog.jsonb_build_object('position',v_position,'depth',v_depth,'eta_s',v_position*120));
    end if;
  end if;

  perform 1 from public.credit_wallets
  where account_id=v_account_id and status='active' and balance>0
    and (expires_at is null or expires_at > now())
    and (person_id is null or p_person_id is null or person_id=p_person_id)
  order by id
  for update;
  select coalesce(sum(balance),0) into v_available from public.credit_wallets
  where account_id=v_account_id and status='active' and balance>0
    and (expires_at is null or expires_at > now())
    and (person_id is null or p_person_id is null or person_id=p_person_id);
  select coalesce(sum(amount),0) into v_holds from public.call_credit_holds
  where account_id=v_account_id and state='held';
  if v_available - v_holds < 1 then
    if v_queue.call_id is not null then update public.call_queue set state='cancelled' where call_id=v_queue.call_id; end if;
    return pg_catalog.jsonb_build_object('status','reject','reason','insufficient_credits');
  end if;

  select * into v_voice from public.voice_shards
  where status='ready' and active_leases < capacity
  order by active_leases::numeric/capacity desc, shard_id
  for update skip locked limit 1;
  select * into v_worker from public.gpu_workers
  where status='ready' and active_leases < capacity
  order by active_leases::numeric/capacity desc, worker_id
  for update skip locked limit 1;

  if v_voice.shard_id is not null and v_worker.worker_id is not null then
    select s into v_slot from pg_catalog.generate_series(1,v_worker.capacity) s
    where not exists (
      select 1 from public.call_leases l where l.worker_id=v_worker.worker_id and l.slot_id=s
        and l.state in ('reserved','connecting','active','ending')
    ) order by s limit 1;
    if v_slot is not null then
      v_call_id := coalesce(v_queue.call_id, gen_random_uuid());
      if v_queue.call_id is not null then
        update public.call_queue set state='promoted' where call_id=v_queue.call_id;
      end if;
      insert into public.call_leases (
        call_id,account_id,person_id,user_id,character_id,state,voice_shard_id,worker_id,
        slot_id,lease_version,idempotency_key,lease_expires_at,last_heartbeat_at
      ) values (
        v_call_id,v_account_id,p_person_id,p_user_id,p_character_id,'reserved',v_voice.shard_id,
        v_worker.worker_id,v_slot,1,p_idempotency_key,now()+interval '60 seconds',now()
      );
      update public.voice_shards set active_leases=active_leases+1,updated_at=now() where shard_id=v_voice.shard_id;
      update public.gpu_workers set active_leases=active_leases+1,idle_since=null,updated_at=now() where worker_id=v_worker.worker_id;
      insert into public.call_credit_holds(call_id,account_id,amount) values(v_call_id,v_account_id,1);
      return pg_catalog.jsonb_build_object(
        'status','connect','call_id',v_call_id,'lease_version',1,'slot_id',v_slot,'state','reserved',
        'worker',pg_catalog.jsonb_build_object('worker_id',v_worker.worker_id,'url',v_worker.url),
        'voice',pg_catalog.jsonb_build_object('shard_id',v_voice.shard_id,'url',v_voice.url)
      );
    end if;
  end if;

  if v_queue.call_id is null then
    select count(*)::integer into v_depth from public.call_queue where state='queued';
    if v_depth >= greatest(1,least(p_queue_max,30)) then
      return pg_catalog.jsonb_build_object('status','reject','reason','queue_full');
    end if;
    insert into public.call_queue(account_id,person_id,user_id,character_id,idempotency_key)
      values(v_account_id,p_person_id,p_user_id,p_character_id,p_idempotency_key)
      returning * into v_queue;
  end if;
  select count(*)::integer into v_position from public.call_queue
    where state='queued' and enqueued_at <= v_queue.enqueued_at;
  select count(*)::integer into v_depth from public.call_queue where state='queued';
  return pg_catalog.jsonb_build_object('status','queued','call_id',v_queue.call_id,
    'queue',pg_catalog.jsonb_build_object('position',v_position,'depth',v_depth,'eta_s',v_position*120));
end;
$$;

create or replace function public.munea_call_ready(
  p_call_id uuid,
  p_lease_version integer,
  p_component text,
  p_event_id text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare v_call public.call_leases%rowtype;
begin
  if p_component not in ('voice','avatar') then return pg_catalog.jsonb_build_object('ok',false,'reason','invalid_component'); end if;
  insert into public.call_component_events(event_id,call_id,component,event_type,lease_version)
    values(p_event_id,p_call_id,p_component,'ready',p_lease_version)
    on conflict(event_id) do nothing;
  select * into v_call from public.call_leases where call_id=p_call_id for update;
  if not found or v_call.lease_version<>p_lease_version or v_call.state in ('ended','failed') then
    return pg_catalog.jsonb_build_object('ok',false,'reason','stale_lease');
  end if;
  update public.call_leases set
    voice_ready_at=case when p_component='voice' then coalesce(voice_ready_at,now()) else voice_ready_at end,
    avatar_ready_at=case when p_component='avatar' then coalesce(avatar_ready_at,now()) else avatar_ready_at end,
    state='connecting',last_heartbeat_at=now(),lease_expires_at=now()+interval '45 seconds',updated_at=now()
    where call_id=p_call_id;
  select * into v_call from public.call_leases where call_id=p_call_id for update;
  if v_call.voice_ready_at is not null and v_call.avatar_ready_at is not null and v_call.active_at is null then
    perform public.munea_call_consume_credit(v_call.call_id,v_call.account_id,v_call.person_id,1);
    update public.call_credit_holds set state='settled',settled_at=now() where call_id=p_call_id and state='held';
    update public.call_leases set state='active',active_at=now(),billed_credits=1,
      last_heartbeat_at=now(),lease_expires_at=now()+interval '45 seconds',updated_at=now()
      where call_id=p_call_id;
    return pg_catalog.jsonb_build_object('ok',true,'state','active','billable',true);
  end if;
  return pg_catalog.jsonb_build_object('ok',true,'state','connecting','billable',false);
exception when others then
  return pg_catalog.jsonb_build_object('ok',false,'reason',sqlerrm);
end;
$$;

create or replace function public.munea_call_cancel(
  p_call_id uuid,
  p_user_id uuid
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare v_queue public.call_queue%rowtype;
begin
  perform pg_catalog.pg_advisory_xact_lock(724338221);
  select * into v_queue from public.call_queue
    where call_id=p_call_id and user_id=p_user_id for update;
  if not found then
    return pg_catalog.jsonb_build_object('ok',true,'state','not_queued');
  end if;
  if v_queue.state='queued' then
    update public.call_queue set state='cancelled',last_heartbeat_at=now()
      where call_id=p_call_id;
  end if;
  return pg_catalog.jsonb_build_object('ok',true,'state','cancelled');
end;
$$;

create or replace function public.munea_call_claim(
  p_call_id uuid,
  p_lease_version integer,
  p_user_id uuid
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare v_call public.call_leases%rowtype;
begin
  select * into v_call from public.call_leases
    where call_id=p_call_id and lease_version=p_lease_version and user_id=p_user_id
      and state in ('reserved','connecting','active');
  if not found then
    return pg_catalog.jsonb_build_object('ok',false,'reason','stale_lease');
  end if;
  return pg_catalog.jsonb_build_object(
    'ok',true,'status','connect','call_id',v_call.call_id,
    'lease_version',v_call.lease_version,'slot_id',v_call.slot_id,'state',v_call.state,
    'worker',(select pg_catalog.jsonb_build_object('worker_id',w.worker_id,'url',w.url)
      from public.gpu_workers w where w.worker_id=v_call.worker_id),
    'voice',(select pg_catalog.jsonb_build_object('shard_id',s.shard_id,'url',s.url)
      from public.voice_shards s where s.shard_id=v_call.voice_shard_id)
  );
end;
$$;

create or replace function public.munea_call_heartbeat(
  p_call_id uuid,
  p_lease_version integer,
  p_component text,
  p_event_id text,
  p_user_id uuid default null
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare v_call public.call_leases%rowtype; v_target integer; v_minute integer;
begin
  insert into public.call_component_events(event_id,call_id,component,event_type,lease_version)
    values(p_event_id,p_call_id,p_component,'heartbeat',p_lease_version)
    on conflict(event_id) do nothing;
  select * into v_call from public.call_leases where call_id=p_call_id for update;
  if not found or v_call.lease_version<>p_lease_version or v_call.state in ('ended','failed') then
    return pg_catalog.jsonb_build_object('ok',false,'reason','stale_lease','should_end',true);
  end if;
  if p_user_id is not null and v_call.user_id<>p_user_id then
    return pg_catalog.jsonb_build_object('ok',false,'reason','call_not_owned','should_end',true);
  end if;
  if v_call.state='active' then
    v_target := greatest(1,ceil(extract(epoch from (now()-v_call.active_at))/60.0)::integer);
    if v_target > v_call.billed_credits then
      for v_minute in (v_call.billed_credits::integer+1)..v_target loop
        perform public.munea_call_consume_credit(v_call.call_id,v_call.account_id,v_call.person_id,v_minute);
      end loop;
      update public.call_leases set billed_credits=v_target where call_id=p_call_id;
    end if;
  end if;
  update public.call_leases set last_heartbeat_at=now(),lease_expires_at=now()+interval '45 seconds',updated_at=now()
    where call_id=p_call_id;
  return pg_catalog.jsonb_build_object('ok',true,'state',v_call.state,'should_end',false,'billed_credits',greatest(v_call.billed_credits,coalesce(v_target,0)));
exception when others then
  update public.call_leases set state='ending',end_reason='insufficient_credits',updated_at=now() where call_id=p_call_id;
  return pg_catalog.jsonb_build_object('ok',false,'reason',sqlerrm,'should_end',true);
end;
$$;

create or replace function public.munea_call_release(
  p_call_id uuid,
  p_lease_version integer,
  p_event_id text,
  p_reason text default 'completed',
  p_user_id uuid default null
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare v_call public.call_leases%rowtype; v_seconds integer; v_target integer; v_minute integer;
  v_billed integer; v_billing_error text;
begin
  perform pg_catalog.pg_advisory_xact_lock(724338221);
  select * into v_call from public.call_leases where call_id=p_call_id for update;
  if not found then return pg_catalog.jsonb_build_object('ok',false,'reason','unknown_call'); end if;
  if v_call.lease_version<>p_lease_version then return pg_catalog.jsonb_build_object('ok',false,'reason','stale_lease'); end if;
  if p_user_id is not null and v_call.user_id<>p_user_id then return pg_catalog.jsonb_build_object('ok',false,'reason','call_not_owned'); end if;
  if v_call.state in ('ended','failed') then
    return pg_catalog.jsonb_build_object('ok',true,'state',v_call.state,'idempotent',true,'billable_seconds',v_call.billable_seconds);
  end if;
  insert into public.call_component_events(event_id,call_id,component,event_type,lease_version,details)
    values(p_event_id,p_call_id,'controller','released',p_lease_version,pg_catalog.jsonb_build_object('reason',p_reason))
    on conflict(event_id) do nothing;
  v_seconds := case when v_call.active_at is null then 0
    else floor(greatest(0,extract(epoch from (now()-v_call.active_at))))::integer end;
  v_target := case when v_call.active_at is null then 0
    else greatest(1,ceil(greatest(0,extract(epoch from (now()-v_call.active_at)))/60.0)::integer) end;
  v_billed := v_call.billed_credits::integer;
  v_billing_error := null;
  if v_target > v_billed then
    for v_minute in (v_billed+1)..v_target loop
      begin
        perform public.munea_call_consume_credit(
          v_call.call_id,v_call.account_id,v_call.person_id,v_minute
        );
        v_billed := v_minute;
      exception when raise_exception then
        if sqlerrm <> 'insufficient_credits' then
          raise;
        end if;
        v_billing_error := sqlerrm;
        exit;
      end;
    end loop;
  end if;
  update public.gpu_workers set active_leases=greatest(0,active_leases-1),
    idle_since=case when active_leases<=1 then now() else idle_since end,updated_at=now() where worker_id=v_call.worker_id;
  update public.voice_shards set active_leases=greatest(0,active_leases-1),updated_at=now() where shard_id=v_call.voice_shard_id;
  update public.call_credit_holds
    set state=case when v_call.active_at is null then 'released' else 'settled' end,
        settled_at=coalesce(settled_at,now())
    where call_id=p_call_id and state='held';
  update public.call_leases set state='ended',ended_at=now(),end_reason=left(coalesce(p_reason,'completed'),120),
    billable_seconds=v_seconds,billed_credits=greatest(billed_credits,v_billed),
    metadata=case when v_billing_error is null then metadata else metadata ||
      pg_catalog.jsonb_build_object(
        'billing_error',v_billing_error,
        'unbilled_started_minutes',greatest(0,v_target-v_billed)
      ) end,
    updated_at=now()
    where call_id=p_call_id;
  return pg_catalog.jsonb_build_object(
    'ok',true,'state','ended','idempotent',false,'billable_seconds',v_seconds,
    'billed_credits',greatest(v_call.billed_credits,v_billed),
    'billing_error',v_billing_error
  );
exception when others then
  return pg_catalog.jsonb_build_object('ok',false,'reason',sqlerrm);
end;
$$;

create or replace function public.munea_call_snapshot()
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select pg_catalog.jsonb_build_object(
    'active_calls',(select count(*) from public.call_leases where state='active'),
    'connecting_calls',(select count(*) from public.call_leases where state in ('reserved','connecting')),
    'queue_depth',(select count(*) from public.call_queue where state='queued' and last_heartbeat_at>now()-interval '45 seconds'),
    'avatar_capacity',(select coalesce(sum(capacity),0) from public.gpu_workers where status='ready'),
    'avatar_active',(select coalesce(sum(active_leases),0) from public.gpu_workers where status='ready'),
    'voice_capacity',(select coalesce(sum(capacity),0) from public.voice_shards where status='ready'),
    'voice_active',(select coalesce(sum(active_leases),0) from public.voice_shards where status='ready'),
    'workers',(select coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
      'worker_id',worker_id,'url',url,'provider',provider,'region',region,'status',status,
      'capacity',capacity,'active',active_leases,'last_heartbeat_at',last_heartbeat_at
    ) order by worker_id),'[]'::jsonb) from public.gpu_workers)
  );
$$;

revoke all on function public.munea_call_consume_credit(uuid,uuid,uuid,integer) from public, anon, authenticated;
revoke all on function public.munea_call_reap_expired() from public, anon, authenticated;
revoke all on function public.munea_call_request(uuid,uuid,text,text,integer) from public, anon, authenticated;
revoke all on function public.munea_call_cancel(uuid,uuid) from public, anon, authenticated;
revoke all on function public.munea_call_claim(uuid,integer,uuid) from public, anon, authenticated;
revoke all on function public.munea_call_ready(uuid,integer,text,text) from public, anon, authenticated;
revoke all on function public.munea_call_heartbeat(uuid,integer,text,text,uuid) from public, anon, authenticated;
revoke all on function public.munea_call_release(uuid,integer,text,text,uuid) from public, anon, authenticated;
revoke all on function public.munea_call_snapshot() from public, anon, authenticated;
grant execute on function public.munea_call_reap_expired() to service_role;
grant execute on function public.munea_call_request(uuid,uuid,text,text,integer) to service_role;
grant execute on function public.munea_call_cancel(uuid,uuid) to service_role;
grant execute on function public.munea_call_claim(uuid,integer,uuid) to service_role;
grant execute on function public.munea_call_ready(uuid,integer,text,text) to service_role;
grant execute on function public.munea_call_heartbeat(uuid,integer,text,text,uuid) to service_role;
grant execute on function public.munea_call_release(uuid,integer,text,text,uuid) to service_role;
grant execute on function public.munea_call_snapshot() to service_role;

insert into public.capacity_profiles (
  profile_key,provider,region,gpu_model,model_name,resolution,compile_mode,safe_slots,
  p95_ms,headroom_pct,approved,evidence_url,approved_at
) values (
  'glows-tw-rtx6000ada-vocaframe-640-v1','glows','TW','RTX 6000 Ada','VocaFrame',640,true,3,
  735,23,true,'docs/高併發正式架構-640首發-2026-07-13.md',now()
) on conflict(profile_key) do update set
  safe_slots=excluded.safe_slots,p95_ms=excluded.p95_ms,headroom_pct=excluded.headroom_pct,
  approved=excluded.approved,approved_at=excluded.approved_at,updated_at=now();

commit;
