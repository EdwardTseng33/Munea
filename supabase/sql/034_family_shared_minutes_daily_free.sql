-- Munea 家人圈共用分鐘＋免費額度改「前 7 天每天 10 分鐘、之後每週 10 分鐘」（2026-11-20 拍板）。
-- Run after 033_enterprise_seat_redeem_codes.sql（也需要 006 credit_wallets、010 通話總機、012 signup trial）。
--
-- 這份做三件事：
--   1. 家人圈共用分鐘：來電者是別人家人圈的「非圈主成員」（family_memberships 掛在
--      family_groups.account_id ≠ 自己帳號的那個圈），而且圈主帳號有有效付費方案（plus／pro），
--      通話分鐘就扣圈主的錢包；交易紀錄的 person_id 留來電者，才算得出「誰用了幾分鐘」。
--      圈主自己、自己有付費方案的人、或圈主沒付費時，照舊扣自己的。
--      扣的順序：自己的免費額度 → 圈主的錢包（月額度優先、再來購買點數）→ 自己其他錢包。
--   2. 免費額度：帳號建立那天（台灣時間）算第 1 天。第 1～7 天每天一個 10 點的免費錢包，
--      台灣時間午夜到期、用不完不累積；第 8 天起每週一（台灣時間）一個 10 點的錢包。
--      錢包在第一次需要時才建（開 App 查餘額、按撥通、通話每分鐘扣點都會補建），冪等。
--      有自己付費方案的帳號不發免費額度。舊的一次性 5 點錢包（purchased）不動，有餘額照用。
--   3. 總量護欄：本月（台灣時間）全平台免費額度消耗 ≥ free_allowance_settings.monthly_cap_minutes
--      （預設 1360）時，之後新發的「每日」額度改成 reduced_daily_minutes（預設 5）。每週額度不受影響。
--      調整：update public.free_allowance_settings set monthly_cap_minutes = 2000 where id = 1;
--
-- 函式簽名不變（gateway 不用改）：munea_call_request、munea_call_consume_credit、
-- munea_grant_free_signup_trial 用 create or replace 換掉內容；權限照 010／012 原樣 revoke/grant。
-- 冪等：重跑整份不會重複發點、不會重複建表。
--
-- 回退（照順序；第 3 步是永久刪除免費錢包資料列，要先確認）：
--   1. 重跑 010_realtime_call_control.sql 中 munea_call_consume_credit 與 munea_call_request 兩段
--      create or replace function（以及檔尾的 revoke/grant），恢復「各帳號各扣」。
--   2. 重跑 012_production_security_hardening.sql 的 munea_grant_free_signup_trial，恢復一次性 5 點。
--   3. delete from public.credit_wallets where wallet_type = 'free_allowance';
--      然後把 credit_wallets_wallet_type_check 改回 ('included_monthly','purchased')。
--   4. drop function public.munea_credit_share_status(uuid, uuid), public.munea_ensure_free_allowance(uuid),
--      public.munea_family_share_owner(uuid, uuid), public.munea_account_paid_plan(uuid),
--      public.munea_free_allowance_window(uuid, timestamptz), public.munea_free_allowance_month_used(timestamptz);
--      drop table public.free_allowance_settings;
--   5. update public.entitlement_policy_versions set active = (version = 4) where policy_key = 'munea_app_store_v1';

begin;

-- ── 1. 免費錢包型別與索引 ─────────────────────────────────────────────
alter table public.credit_wallets drop constraint if exists credit_wallets_wallet_type_check;
alter table public.credit_wallets
  add constraint credit_wallets_wallet_type_check
  check (wallet_type in ('included_monthly', 'purchased', 'free_allowance'));

-- unique (account_id, person_id, wallet_type, period) 在 person_id 為 null 時不會擋重複，
-- 免費錢包是帳號層級（person_id null），用部分唯一索引保證一個週期只有一個。
create unique index if not exists credit_wallets_free_allowance_period_uidx
  on public.credit_wallets(account_id, period)
  where wallet_type = 'free_allowance';

-- 護欄要算「本月全平台免費消耗」，只掃 consume 交易。
create index if not exists credit_transactions_consume_created_idx
  on public.credit_transactions(created_at)
  where transaction_type = 'consume';

-- ── 2. 可調設定（一列） ───────────────────────────────────────────────
create table if not exists public.free_allowance_settings (
  id integer primary key default 1 check (id = 1),
  trial_days integer not null default 7 check (trial_days between 0 and 60),
  trial_daily_minutes numeric not null default 10 check (trial_daily_minutes >= 0),
  reduced_daily_minutes numeric not null default 5 check (reduced_daily_minutes >= 0),
  weekly_minutes numeric not null default 10 check (weekly_minutes >= 0),
  monthly_cap_minutes numeric not null default 1360 check (monthly_cap_minutes >= 0),
  updated_at timestamptz not null default now()
);

insert into public.free_allowance_settings (id) values (1)
on conflict (id) do nothing;

alter table public.free_allowance_settings enable row level security;
revoke all on public.free_allowance_settings from anon, authenticated;

-- ── 3. 小工具函式 ─────────────────────────────────────────────────────

-- 本月（台灣時間）全平台免費額度已消耗的分鐘數。
create or replace function public.munea_free_allowance_month_used(
  p_at timestamptz default now()
) returns numeric
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(sum(t.amount), 0)
  from public.credit_transactions t
  join public.credit_wallets w on w.id = t.wallet_id
  where t.transaction_type = 'consume'
    and w.wallet_type = 'free_allowance'
    and t.created_at >= (pg_catalog.date_trunc('month', p_at at time zone 'Asia/Taipei') at time zone 'Asia/Taipei');
$$;

-- 帳號目前有效的付費方案（plus／pro），沒有回 null。讀 subscription_ledger 最新一筆
-- （跟 App 與後台同一個排序欄位 updated_at）。
create or replace function public.munea_account_paid_plan(
  p_account_id uuid
) returns text
language sql
stable
security definer
set search_path = ''
as $$
  select case
    when pg_catalog.lower(s.active_plan) in ('plus', 'pro')
     and s.status in ('active', 'trial', 'grace_period')
     and (s.expires_at is null or s.expires_at > now())
    then pg_catalog.lower(s.active_plan)
    else null
  end
  from public.subscription_ledger s
  where s.account_id = p_account_id
  order by s.updated_at desc
  limit 1;
$$;

-- 這個帳號現在該領哪一個免費錢包：第幾天、週期鍵、點數、起訖時間。
create or replace function public.munea_free_allowance_window(
  p_account_id uuid,
  p_at timestamptz default now()
) returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_trial_days integer := 7;
  v_daily numeric := 10;
  v_reduced numeric := 5;
  v_weekly numeric := 10;
  v_cap numeric := 1360;
  v_created timestamptz;
  v_today date;
  v_day integer;
  v_start date;
  v_end date;
  v_amount numeric;
  v_mode text;
  v_used numeric := 0;
  v_cap_reached boolean := false;
begin
  select s.trial_days, s.trial_daily_minutes, s.reduced_daily_minutes, s.weekly_minutes, s.monthly_cap_minutes
    into v_trial_days, v_daily, v_reduced, v_weekly, v_cap
  from public.free_allowance_settings s
  where s.id = 1;
  if not found then
    v_trial_days := 7; v_daily := 10; v_reduced := 5; v_weekly := 10; v_cap := 1360;
  end if;

  select a.created_at into v_created
  from public.accounts a
  where a.id = p_account_id and a.deleted_at is null;
  if v_created is null then
    return null;
  end if;

  v_today := (p_at at time zone 'Asia/Taipei')::date;
  v_day := greatest(1, v_today - (v_created at time zone 'Asia/Taipei')::date + 1);

  if v_day <= v_trial_days then
    v_mode := 'free_daily';
    v_start := v_today;
    v_end := v_today + 1;
    v_used := public.munea_free_allowance_month_used(p_at);
    v_cap_reached := v_used >= v_cap;
    v_amount := case when v_cap_reached then v_reduced else v_daily end;
  else
    v_mode := 'free_weekly';
    v_start := v_today - (extract(isodow from v_today)::integer - 1);
    v_end := v_start + 7;
    v_amount := v_weekly;
  end if;

  return pg_catalog.jsonb_build_object(
    'mode', v_mode,
    'trialDay', case when v_mode = 'free_daily' then v_day else null end,
    'trialDays', v_trial_days,
    'period', case when v_mode = 'free_daily' then 'free-daily:' else 'free-weekly:' end
      || pg_catalog.to_char(v_start, 'YYYY-MM-DD'),
    'amount', v_amount,
    'startsAt', (v_start::timestamp at time zone 'Asia/Taipei'),
    'expiresAt', (v_end::timestamp at time zone 'Asia/Taipei'),
    'capReached', v_cap_reached
  );
end;
$$;

-- 補建這個週期的免費錢包（冪等）。有付費方案的帳號不發。
create or replace function public.munea_ensure_free_allowance(
  p_account_id uuid
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_plan text;
  v_window jsonb;
  v_period text;
  v_amount numeric;
  v_key text;
  v_wallet public.credit_wallets%rowtype;
  v_tx_id uuid;
begin
  if p_account_id is null or not exists (
    select 1 from public.accounts a where a.id = p_account_id
  ) then
    raise exception 'account_not_found';
  end if;

  v_plan := public.munea_account_paid_plan(p_account_id);
  if v_plan is not null then
    return pg_catalog.jsonb_build_object('ok', true, 'mode', 'plan', 'plan', v_plan, 'credits', 0, 'balance', 0);
  end if;

  v_window := public.munea_free_allowance_window(p_account_id, now());
  if v_window is null then
    raise exception 'account_not_found';
  end if;
  v_period := v_window->>'period';
  v_amount := (v_window->>'amount')::numeric;
  v_key := 'free-allowance:' || p_account_id::text || ':' || v_period;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_key, 0));

  select * into v_wallet from public.credit_wallets w
  where w.account_id = p_account_id and w.wallet_type = 'free_allowance' and w.period = v_period
  limit 1;
  if found then
    return pg_catalog.jsonb_build_object(
      'ok', true, 'idempotentReplay', true, 'mode', v_window->>'mode', 'period', v_period,
      'credits', coalesce((v_wallet.metadata->>'grant')::numeric, v_amount),
      'balance', v_wallet.balance, 'window', v_window
    );
  end if;

  if v_amount <= 0 then
    return pg_catalog.jsonb_build_object(
      'ok', true, 'idempotentReplay', false, 'mode', v_window->>'mode', 'period', v_period,
      'credits', 0, 'balance', 0, 'window', v_window
    );
  end if;

  insert into public.credit_wallets (
    account_id, person_id, wallet_type, period, balance, currency_code, status, expires_at, metadata
  ) values (
    p_account_id, null, 'free_allowance', v_period, v_amount, 'MUNEA_CREDIT', 'active',
    (v_window->>'expiresAt')::timestamptz,
    pg_catalog.jsonb_build_object('purpose', 'free_allowance', 'mode', v_window->>'mode',
      'grant', v_amount, 'capReached', (v_window->>'capReached')::boolean)
  )
  on conflict (account_id, period) where wallet_type = 'free_allowance' do nothing
  returning * into v_wallet;

  if v_wallet.id is null then
    select * into v_wallet from public.credit_wallets w
    where w.account_id = p_account_id and w.wallet_type = 'free_allowance' and w.period = v_period
    limit 1;
    return pg_catalog.jsonb_build_object(
      'ok', true, 'idempotentReplay', true, 'mode', v_window->>'mode', 'period', v_period,
      'credits', v_amount, 'balance', coalesce(v_wallet.balance, 0), 'window', v_window
    );
  end if;

  insert into public.credit_transactions (
    account_id, person_id, wallet_id, transaction_type, source, amount,
    balance_after, provider, idempotency_key, reason, metadata
  ) values (
    p_account_id, null, v_wallet.id, 'grant', 'promo', v_amount,
    v_amount, 'munea_free_allowance', v_key, 'free_allowance_' || (v_window->>'mode'),
    pg_catalog.jsonb_build_object('walletType', 'free_allowance', 'period', v_period,
      'capReached', (v_window->>'capReached')::boolean)
  )
  on conflict (idempotency_key) do nothing
  returning id into v_tx_id;

  if v_tx_id is not null then
    insert into public.credit_ledger (
      account_id, person_id, wallet_id, credit_transaction_id, event_type,
      amount, balance_after, feature, source_ref, metadata
    ) values (
      p_account_id, null, v_wallet.id, v_tx_id, 'included_allowance_granted',
      v_amount, v_amount, 'realtime_voice_avatar', v_key,
      pg_catalog.jsonb_build_object('walletType', 'free_allowance', 'period', v_period)
    );
  end if;

  return pg_catalog.jsonb_build_object(
    'ok', true, 'idempotentReplay', false, 'mode', v_window->>'mode', 'period', v_period,
    'credits', v_amount, 'balance', v_amount, 'window', v_window
  );
end;
$$;

-- 來電者是不是「別人家人圈的非圈主成員、而且圈主有付費」：是就回圈主帳號，不是回 null。
-- 圈主＝family_groups.account_id（建圈的帳號）；成員是 family_memberships 裡 person 屬於
-- 另一個帳號的那一列（加入邀請時寫的 role=family_contact）。自己有付費方案的人不被共用涵蓋。
-- 掛在好幾個圈時取最新加入的那一個（跟 resolve_auth_identity「最新的 membership 是現在的圈」一致）。
create or replace function public.munea_family_share_owner(
  p_account_id uuid,
  p_person_id uuid
) returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_group_id uuid;
  v_owner uuid;
  v_person uuid;
  v_plan text;
begin
  if p_account_id is null then
    return null;
  end if;
  if public.munea_account_paid_plan(p_account_id) is not null then
    return null;
  end if;

  select m.family_group_id, g.account_id, m.person_id
    into v_group_id, v_owner, v_person
  from public.family_memberships m
  join public.family_groups g on g.id = m.family_group_id and g.deleted_at is null
  join public.persons p on p.id = m.person_id and p.account_id = p_account_id and p.deleted_at is null
  where g.account_id <> p_account_id
    and (p_person_id is null or m.person_id = p_person_id)
  order by m.created_at desc
  limit 1;
  if v_owner is null then
    return null;
  end if;

  v_plan := public.munea_account_paid_plan(v_owner);
  if v_plan is null then
    return null;
  end if;

  return pg_catalog.jsonb_build_object(
    'ownerAccountId', v_owner,
    'familyGroupId', v_group_id,
    'personId', v_person,
    'plan', v_plan
  );
end;
$$;

-- ── 4. 每分鐘扣點（簽名不變） ─────────────────────────────────────────
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
  v_share jsonb;
  v_owner uuid;
  v_person uuid;
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
  -- 跨過台灣時間午夜／週一的通話，下一分鐘就從新週期的免費錢包扣。補發失敗不擋付費分鐘。
  begin
    perform public.munea_ensure_free_allowance(p_account_id);
  exception when others then
    raise warning 'munea_ensure_free_allowance failed: %', sqlerrm;
  end;
  v_share := public.munea_family_share_owner(p_account_id, p_person_id);
  v_owner := nullif(v_share->>'ownerAccountId', '')::uuid;
  v_person := coalesce(p_person_id, nullif(v_share->>'personId', '')::uuid);
  if v_owner is not null then
    -- 鎖的順序固定「來電者 → 圈主」；圈主自己有付費、永遠不會再去鎖別人，不會互卡。
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(v_owner::text, 724338221)
    );
  end if;

  perform 1
  from public.credit_wallets w
  where w.status = 'active'
    and w.balance > 0
    and (w.expires_at is null or w.expires_at > now())
    and (
      (w.account_id = p_account_id and (w.person_id is null or p_person_id is null or w.person_id = p_person_id))
      or (v_owner is not null and w.account_id = v_owner and w.wallet_type <> 'free_allowance')
    )
  order by w.id
  for update;

  select coalesce(sum(w.balance), 0) into v_available
  from public.credit_wallets w
  where w.status = 'active'
    and w.balance > 0
    and (w.expires_at is null or w.expires_at > now())
    and (
      (w.account_id = p_account_id and (w.person_id is null or p_person_id is null or w.person_id = p_person_id))
      or (v_owner is not null and w.account_id = v_owner and w.wallet_type <> 'free_allowance')
    );
  select coalesce(sum(amount), 0) into v_holds
  from public.call_credit_holds
  where account_id = p_account_id
    and state = 'held'
    and call_id <> p_call_id;
  if v_available - v_holds < 1 then
    raise exception 'insufficient_credits';
  end if;

  for v_wallet in
    select w.* from public.credit_wallets w
    where w.status = 'active'
      and w.balance > 0
      and (w.expires_at is null or w.expires_at > now())
      and (
        (w.account_id = p_account_id and (w.person_id is null or p_person_id is null or w.person_id = p_person_id))
        or (v_owner is not null and w.account_id = v_owner and w.wallet_type <> 'free_allowance')
      )
    order by
      case
        when w.account_id = p_account_id and w.wallet_type = 'free_allowance' then 0
        when v_owner is not null and w.account_id = v_owner then 1
        else 2
      end,
      case w.wallet_type when 'included_monthly' then 0 else 1 end,
      w.expires_at nulls last, w.id
    for update
  loop
    exit when v_remaining <= 0;
    v_take := least(v_wallet.balance, v_remaining);
    update public.credit_wallets
      set balance = balance - v_take, updated_at = now()
      where id = v_wallet.id;
    -- account_id 跟著錢包走（扣圈主的錢包就記在圈主帳上），person_id 永遠是來電者。
    insert into public.credit_transactions (
      account_id, person_id, wallet_id, transaction_type, source, amount,
      balance_after, idempotency_key, reason, metadata
    ) values (
      v_wallet.account_id, v_person, v_wallet.id, 'consume', 'system', v_take,
      v_wallet.balance - v_take,
      'call:' || p_call_id::text || ':minute:' || p_minute::text || ':' || v_wallet.id::text,
      'realtime_voice_avatar_minute',
      pg_catalog.jsonb_build_object(
        'callId', p_call_id, 'minute', p_minute, 'walletType', v_wallet.wallet_type,
        'callerAccountId', p_account_id,
        'sharedFromAccountId', case when v_wallet.account_id <> p_account_id then v_wallet.account_id else null end,
        'familyGroupId', case when v_wallet.account_id <> p_account_id then v_share->>'familyGroupId' else null end
      )
    ) returning id into v_tx_id;
    insert into public.credit_ledger (
      account_id, person_id, wallet_id, credit_transaction_id, event_type,
      amount, balance_after, feature, source_ref, metadata
    ) values (
      v_wallet.account_id, v_person, v_wallet.id, v_tx_id, 'credits_consumed',
      -v_take, v_wallet.balance - v_take, 'realtime_voice_avatar', p_call_id::text,
      pg_catalog.jsonb_build_object('minute', p_minute, 'walletType', v_wallet.wallet_type,
        'callerAccountId', p_account_id)
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

-- ── 5. 按撥通（簽名不變；只換「夠不夠付第一分鐘」的算法） ─────────────
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
  v_share jsonb;
  v_owner uuid;
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

  -- 今天（或這週）的免費錢包在按撥通時補建；補發失敗不擋有點數的人。
  begin
    perform public.munea_ensure_free_allowance(v_account_id);
  exception when others then
    raise warning 'munea_ensure_free_allowance failed: %', sqlerrm;
  end;
  v_share := public.munea_family_share_owner(v_account_id, p_person_id);
  v_owner := nullif(v_share->>'ownerAccountId', '')::uuid;
  if v_owner is not null then
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(v_owner::text, 724338221)
    );
  end if;

  perform 1 from public.credit_wallets w
  where w.status='active' and w.balance>0
    and (w.expires_at is null or w.expires_at > now())
    and (
      (w.account_id=v_account_id and (w.person_id is null or p_person_id is null or w.person_id=p_person_id))
      or (v_owner is not null and w.account_id=v_owner and w.wallet_type<>'free_allowance')
    )
  order by w.id
  for update;
  select coalesce(sum(w.balance),0) into v_available from public.credit_wallets w
  where w.status='active' and w.balance>0
    and (w.expires_at is null or w.expires_at > now())
    and (
      (w.account_id=v_account_id and (w.person_id is null or p_person_id is null or w.person_id=p_person_id))
      or (v_owner is not null and w.account_id=v_owner and w.wallet_type<>'free_allowance')
    );
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

-- ── 6. 舊的註冊送點入口改成補發免費額度（舊版後端若還在呼叫，也不會再送一次性 5 點） ──
create or replace function public.munea_grant_free_signup_trial(
  p_account_id uuid,
  p_person_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_result jsonb;
begin
  v_result := public.munea_ensure_free_allowance(p_account_id);
  return v_result || pg_catalog.jsonb_build_object(
    'credits', coalesce((v_result->>'credits')::numeric, 0),
    'balance', coalesce((v_result->>'balance')::numeric, 0),
    'idempotentReplay', coalesce((v_result->>'idempotentReplay')::boolean, false)
  );
end;
$$;

-- ── 7. /credits/balance 要的狀態：免費額度、家人圈共用、誰用了幾分鐘 ──────────
-- usage 只回 personId 與分鐘數；名字由後端從家人圈顯示名補（不碰 email）。
-- 成員只拿得到自己那一列；圈主拿得到整個圈。
create or replace function public.munea_credit_share_status(
  p_account_id uuid,
  p_person_id uuid
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_plan text;
  v_window jsonb;
  v_free_balance numeric;
  v_free_grant numeric;
  v_allowance jsonb;
  v_share jsonb;
  v_owner uuid;
  v_group_id uuid;
  v_role text;
  v_share_plan text;
  v_month_grant numeric;
  v_month_remaining numeric;
  v_renews timestamptz;
  v_period_text text;
  v_period_start timestamptz;
  v_spendable numeric := 0;
  v_usage jsonb;
  v_owner_person uuid;
  v_viewer uuid;
begin
  if p_account_id is null then
    return null;
  end if;
  begin
    perform public.munea_ensure_free_allowance(p_account_id);
  exception when others then
    raise warning 'munea_ensure_free_allowance failed: %', sqlerrm;
  end;

  v_plan := public.munea_account_paid_plan(p_account_id);
  if v_plan is null then
    v_window := public.munea_free_allowance_window(p_account_id, now());
    select coalesce(sum(w.balance), 0), coalesce(sum((w.metadata->>'grant')::numeric), 0)
      into v_free_balance, v_free_grant
    from public.credit_wallets w
    where w.account_id = p_account_id and w.wallet_type = 'free_allowance'
      and w.status = 'active' and w.period = v_window->>'period'
      and (w.expires_at is null or w.expires_at > now());
    v_allowance := pg_catalog.jsonb_build_object(
      'mode', v_window->>'mode',
      'trialDay', (v_window->>'trialDay')::integer,
      'trialDays', (v_window->>'trialDays')::integer,
      'todayGrant', case when v_window->>'mode' = 'free_daily' then v_free_grant else null end,
      'todayRemaining', case when v_window->>'mode' = 'free_daily' then v_free_balance else null end,
      'weekGrant', case when v_window->>'mode' = 'free_weekly' then v_free_grant else null end,
      'weekRemaining', case when v_window->>'mode' = 'free_weekly' then v_free_balance else null end,
      'resetsAt', v_window->>'expiresAt'
    );
  end if;

  v_share := public.munea_family_share_owner(p_account_id, p_person_id);
  if v_share is not null then
    v_owner := (v_share->>'ownerAccountId')::uuid;
    v_group_id := (v_share->>'familyGroupId')::uuid;
    v_viewer := coalesce(p_person_id, (v_share->>'personId')::uuid);
    v_role := 'member';
    v_share_plan := v_share->>'plan';
  elsif v_plan is not null then
    select g.id into v_group_id from public.family_groups g
    where g.account_id = p_account_id and g.deleted_at is null
    order by g.created_at asc limit 1;
    if v_group_id is not null then
      v_owner := p_account_id;
      v_viewer := p_person_id;
      v_role := 'owner';
      v_share_plan := v_plan;
    end if;
  end if;

  if v_owner is not null then
    select coalesce(sum(w.balance), 0), min(w.expires_at), min(w.period)
      into v_month_remaining, v_renews, v_period_text
    from public.credit_wallets w
    where w.account_id = v_owner and w.wallet_type = 'included_monthly'
      and w.status = 'active' and (w.expires_at is null or w.expires_at > now());
    if v_period_text is null then
      v_month_remaining := null;
    end if;
    select coalesce(sum(t.amount), 0) into v_month_grant
    from public.credit_transactions t
    join public.credit_wallets w on w.id = t.wallet_id
    where w.account_id = v_owner and w.wallet_type = 'included_monthly'
      and w.status = 'active' and (w.expires_at is null or w.expires_at > now())
      and t.transaction_type = 'grant';
    if coalesce(v_month_grant, 0) <= 0 then
      v_month_grant := case v_share_plan when 'pro' then 200 when 'plus' then 100 else null end;
    end if;

    v_period_start := null;
    if v_period_text is not null and pg_catalog.strpos(v_period_text, '/') > 0 then
      begin
        v_period_start := pg_catalog.split_part(v_period_text, '/', 1)::timestamptz;
      exception when others then
        v_period_start := null;
      end;
    end if;
    if v_period_start is null then
      v_period_start := pg_catalog.date_trunc('month', now() at time zone 'Asia/Taipei') at time zone 'Asia/Taipei';
    end if;

    select p.id into v_owner_person from public.persons p
    where p.account_id = v_owner and p.deleted_at is null
    order by p.is_primary_care_recipient desc, p.created_at asc limit 1;

    select coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('personId', u.person_id, 'minutes', u.minutes)
             order by u.minutes desc), '[]'::jsonb)
      into v_usage
    from (
      select coalesce(t.person_id, v_owner_person) as person_id, sum(t.amount) as minutes
      from public.credit_transactions t
      join public.credit_wallets w on w.id = t.wallet_id
      where t.account_id = v_owner
        and t.transaction_type = 'consume'
        and w.wallet_type <> 'free_allowance'
        and t.created_at >= v_period_start
      group by coalesce(t.person_id, v_owner_person)
    ) u
    where v_role = 'owner' or u.person_id = v_viewer;

    if v_role = 'member' then
      select coalesce(sum(w.balance), 0) into v_spendable
      from public.credit_wallets w
      where w.account_id = v_owner and w.wallet_type <> 'free_allowance'
        and w.status = 'active' and w.balance > 0
        and (w.expires_at is null or w.expires_at > now());
    end if;
  end if;

  return pg_catalog.jsonb_build_object(
    'allowance', case when v_plan is not null
      then pg_catalog.jsonb_build_object('mode', 'plan', 'plan', v_plan, 'resetsAt',
        case when v_role = 'owner' then v_renews else null end)
      else v_allowance end,
    'familyShare', case when v_owner is null then null else pg_catalog.jsonb_build_object(
      'shared', true,
      'role', v_role,
      'plan', v_share_plan,
      'familyGroupId', v_group_id,
      'ownerAccountId', v_owner,
      'ownerPersonId', v_owner_person,
      'viewerPersonId', v_viewer,
      'monthGrant', v_month_grant,
      'monthRemaining', v_month_remaining,
      'renewsAt', case when v_renews is null then null
        else pg_catalog.to_char(v_renews at time zone 'Asia/Taipei', 'YYYY-MM-DD') end,
      'usage', coalesce(v_usage, '[]'::jsonb)
    ) end,
    'sharedSpendable', v_spendable
  );
end;
$$;

-- ── 8. 方案說明（紀錄用；後端以程式為準） ──────────────────────────────
update public.entitlement_policy_versions
set active = false
where policy_key = 'munea_app_store_v1';

insert into public.entitlement_policy_versions (
  policy_key, version, active, plan_order, policy, notes, activated_at
) values (
  'munea_app_store_v1',
  5,
  true,
  array['free', 'plus', 'pro'],
  '{
    "free": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "signupTrialCredits": 0,
      "freeTrialDays": 7,
      "freeTrialDailyMinutes": 10,
      "freeWeeklyMinutes": 10,
      "creditMinutes": 1,
      "familyMembersMax": 2
    },
    "plus": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "monthlyPoints": 100,
      "familySharedMinutes": true,
      "familyMembersMax": 4
    },
    "pro": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "monthlyPoints": 200,
      "familySharedMinutes": true,
      "familyMembersMax": 12
    }
  }'::jsonb,
  '2026-11-20: Free = 10 minutes per Taipei day for the first 7 days, then 10 minutes per Taipei week (Monday reset); daily drops to 5 when the platform monthly free cap is reached. Plus/Pro monthly points are shared with non-owner family-circle members.',
  now()
)
on conflict (policy_key, version) do update
set active = excluded.active,
    plan_order = excluded.plan_order,
    policy = excluded.policy,
    notes = excluded.notes,
    activated_at = coalesce(entitlement_policy_versions.activated_at, excluded.activated_at);

-- ── 9. 權限（010／012 原樣，加上新函式只給 service_role） ─────────────────
revoke all on function public.munea_free_allowance_month_used(timestamptz) from public, anon, authenticated;
revoke all on function public.munea_account_paid_plan(uuid) from public, anon, authenticated;
revoke all on function public.munea_free_allowance_window(uuid, timestamptz) from public, anon, authenticated;
revoke all on function public.munea_ensure_free_allowance(uuid) from public, anon, authenticated;
revoke all on function public.munea_family_share_owner(uuid, uuid) from public, anon, authenticated;
revoke all on function public.munea_credit_share_status(uuid, uuid) from public, anon, authenticated;
revoke all on function public.munea_call_consume_credit(uuid,uuid,uuid,integer) from public, anon, authenticated;
revoke all on function public.munea_call_request(uuid,uuid,text,text,integer) from public, anon, authenticated;
revoke all on function public.munea_grant_free_signup_trial(uuid, uuid) from public;
revoke all on function public.munea_grant_free_signup_trial(uuid, uuid) from anon;
revoke all on function public.munea_grant_free_signup_trial(uuid, uuid) from authenticated;
grant execute on function public.munea_ensure_free_allowance(uuid) to service_role;
grant execute on function public.munea_credit_share_status(uuid, uuid) to service_role;
grant execute on function public.munea_call_request(uuid,uuid,text,text,integer) to service_role;
grant execute on function public.munea_grant_free_signup_trial(uuid, uuid) to service_role;

commit;
