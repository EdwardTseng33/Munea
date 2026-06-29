-- Munea demo bootstrap seed.
-- Intended first use: run after 001_initial_munea_schema.sql in Supabase SQL Editor.
--
-- This creates deterministic demo rows for backend adapter testing.
-- It does not require an auth user. If you want to test authenticated RLS,
-- replace demo_user_id below with a real auth.users.id from Supabase Auth.
--
-- Backend env values created by this seed:
-- MUNEA_SUPABASE_ACCOUNT_ID=11111111-1111-4111-8111-111111111111
-- MUNEA_SUPABASE_PERSON_ID=22222222-2222-4222-8222-222222222222
-- MUNEA_SUPABASE_FAMILY_GROUP_ID=33333333-3333-4333-8333-333333333333

begin;

do $$
declare
  demo_account_id uuid := '11111111-1111-4111-8111-111111111111';
  demo_person_id uuid := '22222222-2222-4222-8222-222222222222';
  demo_family_group_id uuid := '33333333-3333-4333-8333-333333333333';
  demo_user_id uuid := null; -- Optional: replace with a real auth.users.id for authenticated RLS testing.
  demo_period text := to_char(now(), 'YYYY-MM');
begin
  insert into public.accounts (
    id,
    name,
    locale,
    preferred_languages
  )
  values (
    demo_account_id,
    'Munea demo account',
    'zh-TW',
    array['zh-TW', 'en']
  )
  on conflict (id) do update
  set
    name = excluded.name,
    locale = excluded.locale,
    preferred_languages = excluded.preferred_languages,
    updated_at = now(),
    deleted_at = null;

  insert into public.persons (
    id,
    account_id,
    display_name,
    relationship,
    locale,
    timezone,
    is_primary_care_recipient
  )
  values (
    demo_person_id,
    demo_account_id,
    'Primary user',
    'self',
    'zh-TW',
    'Asia/Taipei',
    true
  )
  on conflict (id) do update
  set
    display_name = excluded.display_name,
    relationship = excluded.relationship,
    locale = excluded.locale,
    timezone = excluded.timezone,
    is_primary_care_recipient = excluded.is_primary_care_recipient,
    updated_at = now(),
    deleted_at = null;

  insert into public.family_groups (
    id,
    account_id,
    name
  )
  values (
    demo_family_group_id,
    demo_account_id,
    'Munea Care Circle'
  )
  on conflict (id) do update
  set
    name = excluded.name,
    updated_at = now(),
    deleted_at = null;

  insert into public.family_memberships (
    account_id,
    family_group_id,
    person_id,
    role,
    permissions
  )
  values (
    demo_account_id,
    demo_family_group_id,
    demo_person_id,
    'primary_user',
    '{"manage_companion": true, "view_family_dashboard": true}'::jsonb
  )
  on conflict (family_group_id, person_id) do update
  set
    role = excluded.role,
    permissions = excluded.permissions,
    updated_at = now();

  insert into public.companion_profiles (
    account_id,
    person_id,
    template_id,
    display_name,
    name_touched,
    backend_char,
    avatar_asset,
    voice_profile
  )
  values (
    demo_account_id,
    demo_person_id,
    'nening-real-female',
    'Munea',
    true,
    'nening',
    'avatar-candidates/ig_07564354b2e2fc1e016a3f9ad488788191b28e4e29b51cd091.png',
    'zh-TW-primary-warm'
  )
  on conflict (person_id) do update
  set
    template_id = excluded.template_id,
    display_name = excluded.display_name,
    name_touched = excluded.name_touched,
    backend_char = excluded.backend_char,
    avatar_asset = excluded.avatar_asset,
    voice_profile = excluded.voice_profile,
    updated_at = now(),
    deleted_at = null;

  insert into public.subscription_ledger (
    account_id,
    platform,
    provider,
    product_id,
    original_transaction_id,
    status,
    active_plan,
    entitlements,
    verified_at,
    expires_at,
    will_renew,
    raw_event_ref
  )
  select
    demo_account_id,
    'ios',
    'demo-bootstrap',
    null,
    null,
    'inactive',
    'free',
    '{
      "voiceCompanion": true,
      "familyDashboard": true,
      "routineReminders": true,
      "realtimeAvatar": false,
      "premiumAvatarMinutesMonthly": 0,
      "familyMembersMax": 2
    }'::jsonb,
    null,
    null,
    false,
    'demo-bootstrap'
  where not exists (
    select 1
    from public.subscription_ledger
    where account_id = demo_account_id
      and raw_event_ref = 'demo-bootstrap'
  );

  insert into public.usage_ledger (
    account_id,
    period,
    metric,
    used,
    granted,
    source
  )
  values
    (demo_account_id, demo_period, 'voice_minutes', 0, 300, 'demo-bootstrap'),
    (demo_account_id, demo_period, 'avatar_minutes', 0, 0, 'demo-bootstrap'),
    (demo_account_id, demo_period, 'family_members', 1, 2, 'demo-bootstrap')
  on conflict (account_id, period, metric) do update
  set
    granted = excluded.granted,
    source = excluded.source,
    updated_at = now();

  insert into public.audit_events (
    account_id,
    actor_user_id,
    event_type,
    target_table,
    target_id,
    details
  )
  select
    demo_account_id,
    null,
    'demo_bootstrap_seeded',
    'accounts',
    demo_account_id,
    jsonb_build_object(
      'seed_file', 'supabase/sql/002_demo_bootstrap.sql',
      'person_id', demo_person_id,
      'family_group_id', demo_family_group_id
    )
  where not exists (
    select 1
    from public.audit_events
    where account_id = demo_account_id
      and event_type = 'demo_bootstrap_seeded'
  );

  if demo_user_id is not null then
    if exists (select 1 from auth.users where id = demo_user_id) then
      insert into public.account_members (
        account_id,
        user_id,
        role,
        status
      )
      values (
        demo_account_id,
        demo_user_id,
        'owner',
        'active'
      )
      on conflict (account_id, user_id) do update
      set
        role = excluded.role,
        status = excluded.status,
        updated_at = now();
    else
      raise notice 'demo_user_id % does not exist in auth.users; account_members was not seeded', demo_user_id;
    end if;
  end if;
end $$;

select
  'Munea demo bootstrap ready' as status,
  '11111111-1111-4111-8111-111111111111'::uuid as account_id,
  '22222222-2222-4222-8222-222222222222'::uuid as person_id,
  '33333333-3333-4333-8333-333333333333'::uuid as family_group_id;

commit;
