-- 2026-07-22: 免費帳號 60 天未上線自動清理（Edward 拍板）。
-- Run after 023_test_account_flag.sql.
--
-- 政策：免費會員 60 天沒上線，系統自動刪除該會員資料（帳號連鎖刪除、同
-- 「本人按帳號刪除」走同一條連鎖路），並清 Supabase Auth 登入身分。
--
-- 「上線」的定義（取最近一次、不是只看正式登入事件）：
--   Supabase 的 last_sign_in_at 只在「重新登入」時更新；App 用既有登入證
--   續用好幾個月都不會產生新登入事件。只看它會誤刪活躍用戶，所以取多路
--   訊號的最大值：
--     1. accounts.last_seen_at        — App 每次開機 /account-bootstrap 蓋章（本遷移新增）
--     2. auth.users.last_sign_in_at   — 正式登入事件
--     3. push_devices.last_seen_at    — App 推播裝置登記（每次開 App 會刷）
--     4. voice_sessions.started_at    — 真的打過聊聊
--     5. credit_transactions.created_at — 錢包有動（含免費體驗扣點）
--     6. accounts.created_at          — 兜底（從沒上線過的帳號從建立日起算）
--
-- 五道排除（碰到任何一道就不刪、也不警示）：
--   A. 測試帳號（accounts.is_test_account 或成員 email @munea.net）
--   B. 有活訂閱（subscription_ledger status ∈ trial/active/grace_period）——付費會員
--   C. 購買點數餘額 > 0 —— 收過人家錢、東西不能拿走
--   D. 企業席次在身（enterprise_seats status 非 released）
--   E. 是別人家庭圈的成員（帳號成員在其他帳號有 active membership）——
--      刪他的帳號會把他從付費圈主的家庭圈踢掉
--
-- 兩段式（防「上線第一天大屠殺」＋留通知窗口）：
--   第 1 段 警示：閒置 ≥ (60 - 警示前置天數) 天 → 蓋 retention_warned_at
--                （通知管道好了之後可在這一步接推播／Email；用戶回來就清章）
--   第 2 段 刪除：閒置 ≥ 60 天 且 警示章蓋滿前置天數 → 刪 accounts（連鎖）
--                ＋回傳要清的 Auth user id 給 Brain 用既有 Auth 管理 API 刪
--
-- 護欄：dry-run 預設開、單輪刪除上限（預設 20）、閒置天數下限 30 天防手滑、
--       刪除前寫 audit_events（account_id 是 set null 外鍵、證據不隨帳號消失）。

begin;

alter table public.accounts
  add column if not exists last_seen_at timestamptz,
  add column if not exists retention_warned_at timestamptz;

comment on column public.accounts.last_seen_at is
  'App 每次開機 /account-bootstrap 蓋章的最近上線時間（閒置清理的主要訊號）';
comment on column public.accounts.retention_warned_at is
  '閒置清理第 1 段警示章；用戶回來上線就清空';

create or replace function public.munea_run_free_account_retention(
  p_inactive_days integer default 60,
  p_warning_lead_days integer default 7,
  p_max_deletions integer default 20,
  p_dry_run boolean default true
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_inactive_days integer := greatest(coalesce(p_inactive_days, 60), 30);
  v_warning_lead integer := least(greatest(coalesce(p_warning_lead_days, 7), 0), 30);
  v_max_deletions integer := least(greatest(coalesce(p_max_deletions, 20), 0), 200);
  v_now timestamptz := now();
  v_delete_cutoff timestamptz;
  v_warn_cutoff timestamptz;
  v_scanned integer := 0;
  v_warned integer := 0;
  v_reset integer := 0;
  v_eligible integer := 0;
  v_deleted jsonb := '[]'::jsonb;
  v_warned_sample jsonb := '[]'::jsonb;
  v_auth_ids jsonb := '[]'::jsonb;
  rec record;
begin
  v_delete_cutoff := v_now - make_interval(days => v_inactive_days);
  v_warn_cutoff := v_now - make_interval(days => v_inactive_days - v_warning_lead);

  -- 候選＝目前是免費身分、且沒踩到任何一道排除的帳號，帶最近上線時間。
  create temp table if not exists _retention_candidates (
    account_id uuid primary key,
    account_name text,
    owner_email text,
    last_activity timestamptz,
    retention_warned_at timestamptz
  ) on commit drop;
  delete from _retention_candidates;

  insert into _retention_candidates
  select
    a.id,
    a.name,
    (
      select u.email from public.account_members am
      join auth.users u on u.id = am.user_id
      where am.account_id = a.id and am.role = 'owner'
      order by am.created_at asc limit 1
    ),
    greatest(
      a.created_at,
      coalesce(a.last_seen_at, a.created_at),
      coalesce((
        select max(u.last_sign_in_at) from public.account_members am
        join auth.users u on u.id = am.user_id
        where am.account_id = a.id
      ), a.created_at),
      coalesce((
        select max(d.last_seen_at) from public.push_devices d
        where d.account_id = a.id
      ), a.created_at),
      coalesce((select max(vs.started_at) from public.voice_sessions vs
                where vs.account_id = a.id), a.created_at),
      coalesce((select max(ct.created_at) from public.credit_transactions ct
                where ct.account_id = a.id), a.created_at)
    ),
    a.retention_warned_at
  from public.accounts a
  where a.deleted_at is null
    and a.is_test_account = false
    -- B. 付費會員不碰
    and not exists (
      select 1 from public.subscription_ledger sl
      where sl.account_id = a.id
        and sl.status in ('trial', 'active', 'grace_period')
    )
    -- C. 有買來的點數不碰
    and not exists (
      select 1 from public.credit_wallets w
      where w.account_id = a.id
        and w.wallet_type = 'purchased'
        and w.balance > 0
    )
    -- D. 企業席次在身不碰
    and not exists (
      select 1 from public.enterprise_seats es
      where es.account_id = a.id and es.status <> 'released'
    )
    -- E. 別人家庭圈的成員不碰
    and not exists (
      select 1 from public.account_members mine
      join public.account_members elsewhere
        on elsewhere.user_id = mine.user_id
       and elsewhere.account_id <> mine.account_id
       and elsewhere.status = 'active'
      where mine.account_id = a.id
    )
    -- A. 測試帳號（欄位或 email 網域雙保險）
    and not exists (
      select 1 from public.account_members am
      join auth.users u on u.id = am.user_id
      where am.account_id = a.id
        and u.email ilike '%@munea.net'
    );

  select count(*) into v_scanned from _retention_candidates;

  -- 回來上線的人清警示章
  for rec in
    select account_id from _retention_candidates
    where retention_warned_at is not null and last_activity >= v_warn_cutoff
  loop
    v_reset := v_reset + 1;
    if not p_dry_run then
      update public.accounts set retention_warned_at = null
      where id = rec.account_id;
    end if;
  end loop;

  -- 第 1 段：蓋警示章
  for rec in
    select account_id, owner_email, last_activity from _retention_candidates
    where retention_warned_at is null and last_activity < v_warn_cutoff
  loop
    v_warned := v_warned + 1;
    if jsonb_array_length(v_warned_sample) < 50 then
      v_warned_sample := v_warned_sample || jsonb_build_object(
        'accountId', rec.account_id,
        'ownerEmail', rec.owner_email,
        'lastActivityAt', rec.last_activity
      );
    end if;
    if not p_dry_run then
      update public.accounts set retention_warned_at = v_now
      where id = rec.account_id;
    end if;
  end loop;

  -- 第 2 段：刪除（閒置滿 60 天＋警示章蓋滿前置天數）
  for rec in
    select c.account_id, c.account_name, c.owner_email, c.last_activity,
           c.retention_warned_at,
           (
             -- 只清「除了這個帳號之外沒別的 active membership」的登入身分
             select coalesce(jsonb_agg(distinct am.user_id), '[]'::jsonb)
             from public.account_members am
             where am.account_id = c.account_id
               and not exists (
                 select 1 from public.account_members other
                 where other.user_id = am.user_id
                   and other.account_id <> c.account_id
                   and other.status = 'active'
               )
           ) as orphan_auth_ids
    from _retention_candidates c
    where c.last_activity < v_delete_cutoff
      and (
        v_warning_lead = 0
        or (c.retention_warned_at is not null
            and c.retention_warned_at <= v_now - make_interval(days => v_warning_lead))
      )
    order by c.last_activity asc
    limit v_max_deletions
  loop
    v_eligible := v_eligible + 1;
    v_deleted := v_deleted || jsonb_build_object(
      'accountId', rec.account_id,
      'accountName', rec.account_name,
      'ownerEmail', rec.owner_email,
      'lastActivityAt', rec.last_activity,
      'warnedAt', rec.retention_warned_at,
      'authUserIds', rec.orphan_auth_ids
    );
    v_auth_ids := v_auth_ids || rec.orphan_auth_ids;

    if not p_dry_run then
      -- 證據先落地（audit_events.account_id 是 on delete set null、不隨帳號消失）
      insert into public.audit_events (
        account_id, actor_user_id, event_type, target_table, target_id, details
      ) values (
        rec.account_id, null, 'retention_auto_delete', 'accounts', rec.account_id,
        jsonb_build_object(
          'policy', 'free_inactive_' || v_inactive_days || 'd',
          -- md5＝內建函式、不吃 pgcrypto 的 search_path；只是維運比對指紋、非安全用途
          'emailHash', md5(coalesce(rec.owner_email, '')),
          'lastActivityAt', rec.last_activity,
          'warnedAt', rec.retention_warned_at
        )
      );
      delete from public.accounts where id = rec.account_id;
    end if;
  end loop;

  return jsonb_build_object(
    'ok', true,
    'dryRun', p_dry_run,
    'inactiveDays', v_inactive_days,
    'warningLeadDays', v_warning_lead,
    'maxDeletions', v_max_deletions,
    'scannedFreeAccounts', v_scanned,
    'warnedCount', v_warned,
    'warnedSample', v_warned_sample,
    'warningResetCount', v_reset,
    'deletedCount', v_eligible,
    'deleted', v_deleted,
    'authUserIdsToCleanup', v_auth_ids,
    'ranAt', v_now
  );
end;
$$;

revoke all on function public.munea_run_free_account_retention(integer, integer, integer, boolean) from public;
revoke all on function public.munea_run_free_account_retention(integer, integer, integer, boolean) from anon;
revoke all on function public.munea_run_free_account_retention(integer, integer, integer, boolean) from authenticated;
grant execute on function public.munea_run_free_account_retention(integer, integer, integer, boolean) to service_role;

-- App 開機蓋上線章（Brain /account-bootstrap 走 service key 直接 update，
-- 不需要額外 RPC；這裡只留欄位與函式）。

commit;
