-- Munea 分鐘規則改回簡單版（2026-11-26 Edward 拍板兩件）：
--   「每個帳號各扣各的分鐘 當然要」、「沒有天數概念：註冊送一次 5 分鐘，用完就訂閱或加買」。
-- Run after 034_family_shared_minutes_daily_free.sql。
--
-- 這份做四件事：
--   1. 家人圈共用分鐘關掉：munea_family_share_owner 一律回 null → munea_call_request／
--      munea_call_consume_credit（034 版，函式內容不動）只找來電者自己的錢包。
--   2. 免費額度改成「註冊送一次 5 分鐘」：munea_ensure_free_allowance 只在帳號從來沒拿過
--      一次性 5 分鐘時發一次（free_allowance 錢包、period='free-once'、不會到期），之後不再每天／每週補。
--      「拿過」＝有 idempotency_key 'free-signup-trial:<帳號>' 的交易（11/20 以前 012 送的 5 點也是這個鍵）
--      或已經有 free-once 錢包。用掉的不回補。有付費方案的帳號這時不發（之後變回免費才補那一次）。
--      扣的順序（034 扣點函式本來就是）：自己的一次性免費 → 自己的方案月額度 → 自己的購買分鐘。
--   3. 11/20 起發的每日／每週免費錢包：還沒到期的，套用這份時就收掉（expires_at 設成現在；資料列與交易保留）。
--      沒有定時任務在發這些錢包（034 是撥號／查餘額時才補建），所以沒有排程要關。
--   4. /credits/balance 狀態（munea_credit_share_status）：
--      allowance＝{mode:'free_once', grant, remaining} 或 {mode:'plan', plan, resetsAt}；familyShare 一律 null、sharedSpendable 0。
--      方案說明 v6：註冊送一次 5 分鐘、familySharedMinutes=false。
--
-- 不動的：family_state 的 account_in_family_group 修正、034 的錢包型別與索引、交易紀錄。
-- 本月總量護欄（monthly_cap_minutes）不再用得到：免費成本上限＝新註冊帳號數 × 5 分鐘。
-- 冪等：重跑整份結果一樣（不會重複發 5 分鐘）。
--
-- 回退（恢復 034 的家人圈共用＋每日／每週免費）：重跑 034_family_shared_minutes_daily_free.sql 裡
--   munea_free_allowance_window、munea_ensure_free_allowance、munea_family_share_owner、munea_credit_share_status
--   四段 create or replace function，再
--   update public.entitlement_policy_versions set active = (version = 5) where policy_key = 'munea_app_store_v1';
--   第 3 步收掉的每日／每週錢包不會自己回來（下一次撥號會補建當期的）。

begin;

-- ── 1. 家人圈共用：一律沒有（簽名不變，呼叫它的扣點函式不用改） ─────────────
create or replace function public.munea_family_share_owner(
  p_account_id uuid,
  p_person_id uuid
) returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select null::jsonb;
$$;

-- ── 1b. 免費額度：註冊送一次 5 分鐘 ────────────────────────────────
alter table public.free_allowance_settings
  add column if not exists signup_once_minutes numeric not null default 5 check (signup_once_minutes >= 0);

-- 這個帳號的免費額度長什麼樣子（簽名不變；034 的呼叫者照用）。
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
  v_amount numeric;
begin
  if not exists (select 1 from public.accounts a where a.id = p_account_id and a.deleted_at is null) then
    return null;
  end if;
  select s.signup_once_minutes into v_amount from public.free_allowance_settings s where s.id = 1;
  return pg_catalog.jsonb_build_object(
    'mode', 'free_once',
    'trialDay', null,
    'trialDays', null,
    'period', 'free-once',
    'amount', coalesce(v_amount, 5),
    'startsAt', null,
    'expiresAt', null,
    'capReached', false
  );
end;
$$;

-- 這個帳號拿過一次性 5 分鐘沒有（012 舊的註冊送點、或 035 起的 free-once 錢包）。
create or replace function public.munea_free_once_received(
  p_account_id uuid
) returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.credit_transactions t
    where t.idempotency_key = 'free-signup-trial:' || p_account_id::text
  ) or exists (
    select 1 from public.credit_wallets w
    where w.account_id = p_account_id and w.wallet_type = 'free_allowance' and w.period = 'free-once'
  );
$$;

-- 一次性免費現在還剩多少：free-once 錢包；11/20 以前的帳號那 5 點放在自己的購買錢包，最多算 5。
create or replace function public.munea_free_once_remaining(
  p_account_id uuid
) returns numeric
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce((
    select sum(w.balance) from public.credit_wallets w
    where w.account_id = p_account_id and w.wallet_type = 'free_allowance' and w.period = 'free-once'
      and w.status = 'active' and (w.expires_at is null or w.expires_at > now())
  ), case when exists (
    select 1 from public.credit_transactions t where t.idempotency_key = 'free-signup-trial:' || p_account_id::text
  ) then least(5::numeric, coalesce((
    select sum(w.balance) from public.credit_wallets w
    where w.account_id = p_account_id and w.wallet_type = 'purchased' and w.person_id is null and w.period is null
      and w.status = 'active'
  ), 0)) else 0 end);
$$;

-- 補發一次性 5 分鐘（冪等；簽名不變）。拿過就不再發；有付費方案的帳號這時不發。
create or replace function public.munea_ensure_free_allowance(
  p_account_id uuid
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_plan text;
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

  v_key := 'free-signup-trial:' || p_account_id::text;
  -- 跟 012 的 munea_grant_free_signup_trial 用同一把鎖，兩邊同時被叫也只發一次
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_key, 0));

  if public.munea_free_once_received(p_account_id) then
    return pg_catalog.jsonb_build_object(
      'ok', true, 'idempotentReplay', true, 'mode', 'free_once', 'period', 'free-once',
      'credits', 5, 'balance', public.munea_free_once_remaining(p_account_id)
    );
  end if;

  select s.signup_once_minutes into v_amount from public.free_allowance_settings s where s.id = 1;
  v_amount := coalesce(v_amount, 5);
  if v_amount <= 0 then
    return pg_catalog.jsonb_build_object('ok', true, 'idempotentReplay', false, 'mode', 'free_once',
      'period', 'free-once', 'credits', 0, 'balance', 0);
  end if;

  insert into public.credit_wallets (
    account_id, person_id, wallet_type, period, balance, currency_code, status, expires_at, metadata
  ) values (
    p_account_id, null, 'free_allowance', 'free-once', v_amount, 'MUNEA_CREDIT', 'active', null,
    pg_catalog.jsonb_build_object('purpose', 'free_allowance', 'mode', 'free_once', 'grant', v_amount)
  )
  on conflict (account_id, period) where wallet_type = 'free_allowance' do nothing
  returning * into v_wallet;

  if v_wallet.id is null then
    return pg_catalog.jsonb_build_object('ok', true, 'idempotentReplay', true, 'mode', 'free_once',
      'period', 'free-once', 'credits', v_amount, 'balance', public.munea_free_once_remaining(p_account_id));
  end if;

  insert into public.credit_transactions (
    account_id, person_id, wallet_id, transaction_type, source, amount,
    balance_after, provider, idempotency_key, reason, metadata
  ) values (
    p_account_id, null, v_wallet.id, 'grant', 'promo', v_amount,
    v_amount, 'munea_signup', v_key, 'free_signup_once',
    pg_catalog.jsonb_build_object('walletType', 'free_allowance', 'period', 'free-once', 'minutesApprox', v_amount)
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
      pg_catalog.jsonb_build_object('walletType', 'free_allowance', 'period', 'free-once', 'oneTime', true)
    );
  end if;

  return pg_catalog.jsonb_build_object(
    'ok', true, 'idempotentReplay', false, 'mode', 'free_once', 'period', 'free-once',
    'credits', v_amount, 'balance', v_amount
  );
end;
$$;

-- ── 1c. 11/20 起發的每日／每週免費錢包：還沒到期的收掉（資料列與交易保留） ─────
update public.credit_wallets
set expires_at = now(),
    metadata = coalesce(metadata, '{}'::jsonb) || pg_catalog.jsonb_build_object('closedBy', '035_free_once')
where wallet_type = 'free_allowance'
  and (period like 'free-daily:%' or period like 'free-weekly:%')
  and (expires_at is null or expires_at > now());

-- ── 2. /credits/balance 狀態：只有自己的一次性免費／方案，沒有 familyShare ─────
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
  v_allowance jsonb;
  v_renews timestamptz;
  v_received boolean;
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
    v_received := public.munea_free_once_received(p_account_id);
    v_allowance := pg_catalog.jsonb_build_object(
      'mode', 'free_once',
      'grant', case when v_received then coalesce((
        select (w.metadata->>'grant')::numeric from public.credit_wallets w
        where w.account_id = p_account_id and w.wallet_type = 'free_allowance' and w.period = 'free-once' limit 1
      ), 5) else 0 end,
      'remaining', public.munea_free_once_remaining(p_account_id)
    );
  else
    select min(w.expires_at) into v_renews
    from public.credit_wallets w
    where w.account_id = p_account_id and w.wallet_type = 'included_monthly'
      and w.status = 'active' and (w.expires_at is null or w.expires_at > now());
    v_allowance := pg_catalog.jsonb_build_object('mode', 'plan', 'plan', v_plan, 'resetsAt', v_renews);
  end if;

  return pg_catalog.jsonb_build_object(
    'allowance', v_allowance,
    'familyShare', null,
    'sharedSpendable', 0
  );
end;
$$;

-- ── 3. 方案說明 v6（紀錄用；後端以程式為準） ─────────────────────────────
update public.entitlement_policy_versions
set active = false
where policy_key = 'munea_app_store_v1';

insert into public.entitlement_policy_versions (
  policy_key, version, active, plan_order, policy, notes, activated_at
) values (
  'munea_app_store_v1',
  6,
  true,
  array['free', 'plus', 'pro'],
  '{
    "free": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "signupTrialCredits": 5,
      "freeOnceMinutes": 5,
      "creditMinutes": 1,
      "familyMembersMax": 2
    },
    "plus": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "monthlyPoints": 100,
      "familySharedMinutes": false,
      "familyMembersMax": 4
    },
    "pro": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "monthlyPoints": 200,
      "familySharedMinutes": false,
      "familyMembersMax": 12
    }
  }'::jsonb,
  '2026-11-26: Free = one-time 5 minutes at sign-up (never refilled daily or weekly); when used up, subscribe or buy minutes. Minutes are per account (no family-circle sharing). Free vs paid differs only in features and minutes.',
  now()
)
on conflict (policy_key, version) do update
set active = excluded.active,
    plan_order = excluded.plan_order,
    policy = excluded.policy,
    notes = excluded.notes,
    activated_at = coalesce(entitlement_policy_versions.activated_at, excluded.activated_at);

-- ── 4. 權限（同 034：只給 service_role） ───────────────────────────────
revoke all on function public.munea_family_share_owner(uuid, uuid) from public, anon, authenticated;
revoke all on function public.munea_free_allowance_window(uuid, timestamptz) from public, anon, authenticated;
revoke all on function public.munea_free_once_received(uuid) from public, anon, authenticated;
revoke all on function public.munea_free_once_remaining(uuid) from public, anon, authenticated;
revoke all on function public.munea_ensure_free_allowance(uuid) from public, anon, authenticated;
grant execute on function public.munea_ensure_free_allowance(uuid) to service_role;
revoke all on function public.munea_credit_share_status(uuid, uuid) from public, anon, authenticated;
grant execute on function public.munea_credit_share_status(uuid, uuid) to service_role;

commit;
