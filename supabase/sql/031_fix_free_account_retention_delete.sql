-- 2026-11-08: 修 024 遺留的 bug——munea_run_free_account_retention() 清暫存表那句
-- `delete from _retention_candidates;` 沒有 WHERE 子句，正式庫每天 03:40 的
-- Cloud Scheduler（munea-account-retention-production）跑這支函式必定踩到
-- Postgres「DELETE requires a WHERE clause」規則而整支失敗（_retention_candidates
-- 是函式本體內建的 temp table，這句話的意圖本來就是「清空它」，只是沒有明確
-- 寫出 WHERE 子句）。Run after 031 的前一支遷移（029；030 已被另一張進行中的
-- PR 用掉——#640「機構端專區第 2 段」的 030_org_staff_consent.sql，本遷移改用 031
-- 避免識別碼撞號，兩者互不相關、可各自獨立套用）。
--
-- 背景：
--   024 的函式本體（五道排除、兩段式警示/刪除、審計落地）完全不變，只是
--   把「清空暫存表」那一句從無 WHERE 的 DELETE 改成 `where true`（明確表達
--   「真的要清空全部」，跟 TRUNCATE 效果相同，但留在同一張函式裡好讀、
--   也不需要額外的 TRUNCATE 權限）。
--
-- 回滾方式：
--   本遷移只是 `create or replace function`，沒有改動資料表結構／資料。
--   如需回滾，直接重跑 024（`create or replace function` 原樣覆蓋回舊版本）
--   即可；舊版本雖然會在下一次排程再度踩到同一個 bug，但不影響既有資料，
--   回滾本身沒有風險。

begin;

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
  delete from _retention_candidates where true;  -- 031 修：Postgres「DELETE requires a WHERE clause」規則擋下無 WHERE 的清空語句

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
    -- D. 企業席次在身不碰 → 拆到候選建好之後、用 to_regclass 條件刪
    --    （enterprise_seats 是較晚的遷移，某些環境還沒建表；直接在這裡
    --     靜態引用會讓整支函式在缺表環境無法執行。見下方 to_regclass 段）
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

  -- D. 企業席次在身不碰（表存在才查；缺表環境沒有企業客戶、跳過安全）。
  --    放在 if 分支內＝缺表時這條含 enterprise_seats 的語句不會被執行、
  --    PL/pgSQL 不 plan 未到達的語句，因此不會 42P01。
  if to_regclass('public.enterprise_seats') is not null then
    delete from _retention_candidates c
    where exists (
      select 1 from public.enterprise_seats es
      where es.account_id = c.account_id and es.status <> 'released'
    );
  end if;

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

commit;
