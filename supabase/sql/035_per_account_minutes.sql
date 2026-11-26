-- Munea 分鐘改回「每個帳號各扣各的」（2026-11-26 Edward 拍板：「每個帳號各扣各的分鐘 當然要」）。
-- Run after 034_family_shared_minutes_daily_free.sql。
--
-- 034 讓「別人家人圈的非圈主成員」通話時扣圈主的付費分鐘；這份把它關掉：
--   1. munea_family_share_owner 一律回 null → munea_call_request／munea_call_consume_credit
--      （034 版，函式內容不動）只會找來電者自己的錢包，扣的順序變成
--      自己的免費額度 → 自己的方案月額度 → 自己的購買分鐘。
--   2. munea_credit_share_status 不再回 familyShare、sharedSpendable 一律 0；
--      付費帳號的 allowance.resetsAt 改讀自己月額度錢包的到期日（不再要求「是圈主」）。
--   3. 方案說明 v6：familySharedMinutes=false（紀錄用；後端以程式為準）。
--
-- 不動的：034 的免費額度（前 7 天每天 10 分鐘、之後每週 10 分鐘、本月總量護欄）、
-- 免費錢包型別與索引、munea_account_paid_plan、family_state 的 account_in_family_group 修正。
-- 已經從圈主錢包扣掉的歷史交易不回補（交易紀錄保留）。
-- 冪等：重跑整份結果一樣。
--
-- 回退（恢復家人圈共用分鐘）：重跑 034_family_shared_minutes_daily_free.sql 的
--   munea_family_share_owner、munea_credit_share_status 兩段 create or replace function，
--   再 update public.entitlement_policy_versions set active = (version = 5) where policy_key = 'munea_app_store_v1';

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

-- ── 2. /credits/balance 狀態：只有自己的免費額度／方案，沒有 familyShare ─────
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
  v_renews timestamptz;
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
  '2026-11-26: Minutes are per account again (no family-circle sharing). Free = 10 minutes per Taipei day for the first 7 days, then 10 minutes per Taipei week (Monday reset); daily drops to 5 when the platform monthly free cap is reached.',
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
revoke all on function public.munea_credit_share_status(uuid, uuid) from public, anon, authenticated;
grant execute on function public.munea_credit_share_status(uuid, uuid) to service_role;

commit;
