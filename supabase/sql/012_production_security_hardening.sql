-- Production security hardening for account membership and signup trial credits.
-- Run after 011_free_signup_trial_policy.sql.

begin;

-- Account membership is created only by the trusted backend or invitation RPCs.
-- A signed-in client must never be able to attach itself to an arbitrary account.
drop policy if exists account_members_insert_self_owner on public.account_members;
revoke insert, update, delete on public.account_members from authenticated;

-- NULL values do not collide in a normal UNIQUE constraint. This partial index
-- guarantees one account-level purchased wallet for server-side trial grants.
create unique index if not exists credit_wallets_account_purchased_default_uidx
  on public.credit_wallets(account_id, wallet_type)
  where person_id is null and period is null and wallet_type = 'purchased';

create or replace function public.munea_grant_free_signup_trial(
  p_account_id uuid,
  p_person_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_key text := 'free-signup-trial:' || p_account_id::text;
  v_wallet public.credit_wallets%rowtype;
  v_transaction_id uuid;
  v_balance numeric;
begin
  if p_account_id is null or not exists (
    select 1 from public.accounts where id = p_account_id
  ) then
    raise exception 'account_not_found';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(v_key, 0));

  select id, balance_after
    into v_transaction_id, v_balance
    from public.credit_transactions
   where idempotency_key = v_key
   limit 1;

  if v_transaction_id is not null then
    return jsonb_build_object(
      'ok', true,
      'idempotentReplay', true,
      'credits', 5,
      'balance', coalesce(v_balance, 0),
      'transactionId', v_transaction_id
    );
  end if;

  insert into public.credit_wallets (
    account_id, person_id, wallet_type, period, balance, currency_code,
    status, metadata
  ) values (
    p_account_id, null, 'purchased', null, 0, 'MUNEA_CREDIT',
    'active', jsonb_build_object('scope', 'account', 'purpose', 'signup_trial')
  )
  on conflict (account_id, wallet_type)
    where person_id is null and period is null and wallet_type = 'purchased'
  do update set status = 'active'
  returning * into v_wallet;

  update public.credit_wallets
     set balance = balance + 5,
         updated_at = now()
   where id = v_wallet.id
  returning balance into v_balance;

  insert into public.credit_transactions (
    account_id, person_id, wallet_id, transaction_type, source, amount,
    balance_after, provider, idempotency_key, reason, metadata
  ) values (
    p_account_id, p_person_id, v_wallet.id, 'grant', 'promo', 5,
    v_balance, 'munea_signup', v_key, 'free_signup_voice_avatar_trial',
    jsonb_build_object('minutesApprox', 5, 'voiceAvatarBound', true)
  )
  returning id into v_transaction_id;

  insert into public.credit_ledger (
    account_id, person_id, wallet_id, credit_transaction_id, event_type,
    amount, balance_after, feature, source_ref, metadata
  ) values (
    p_account_id, p_person_id, v_wallet.id, v_transaction_id,
    'included_allowance_granted', 5, v_balance, 'realtime_voice_avatar',
    v_key, jsonb_build_object('oneTime', true)
  );

  return jsonb_build_object(
    'ok', true,
    'idempotentReplay', false,
    'credits', 5,
    'balance', v_balance,
    'transactionId', v_transaction_id
  );
end;
$$;

revoke all on function public.munea_grant_free_signup_trial(uuid, uuid) from public;
revoke all on function public.munea_grant_free_signup_trial(uuid, uuid) from anon;
revoke all on function public.munea_grant_free_signup_trial(uuid, uuid) from authenticated;
grant execute on function public.munea_grant_free_signup_trial(uuid, uuid) to service_role;

commit;
