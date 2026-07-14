-- Align the entitlement policy with the customer-visible Munea 1.0.2 plans.
-- Run after 012_production_security_hardening.sql.

begin;

update public.entitlement_policy_versions
set active = false
where policy_key = 'munea_app_store_v1';

insert into public.entitlement_policy_versions (
  policy_key, version, active, plan_order, policy, notes, activated_at
) values (
  'munea_app_store_v1',
  3,
  true,
  array['free', 'plus', 'pro'],
  '{
    "free": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "signupTrialCredits": 5,
      "creditMinutes": 1,
      "trialRenewal": "never",
      "familyMembersMax": 1
    },
    "plus": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "monthlyPoints": 150,
      "familyMembersMax": 4
    },
    "pro": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "monthlyPoints": 300,
      "familyMembersMax": 12
    }
  }'::jsonb,
  'Munea 1.0.2 plans: one-time 5-credit Free trial, Plus 150 monthly points, Pro 300 monthly points.',
  now()
)
on conflict (policy_key, version) do update
set active = excluded.active,
    plan_order = excluded.plan_order,
    policy = excluded.policy,
    notes = excluded.notes,
    activated_at = coalesce(entitlement_policy_versions.activated_at, excluded.activated_at);

commit;
