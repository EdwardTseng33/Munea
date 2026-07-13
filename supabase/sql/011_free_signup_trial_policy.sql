-- Munea one-time signup trial policy.
-- Run after 006_billing_credits_foundation.sql.

begin;

update public.entitlement_policy_versions
set active = false
where policy_key = 'munea_app_store_v1';

insert into public.entitlement_policy_versions (
  policy_key, version, active, plan_order, policy, notes, activated_at
) values (
  'munea_app_store_v1',
  2,
  true,
  array['free', 'plus', 'premium', 'concierge'],
  '{
    "free": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "signupTrialCredits": 5,
      "creditMinutes": 1,
      "trialRenewal": "never",
      "familyMembersMax": 2
    },
    "plus": {"voiceCompanion": true, "realtimeAvatar": true, "familyMembersMax": 4},
    "premium": {"voiceCompanion": true, "realtimeAvatar": true, "familyMembersMax": 8},
    "concierge": {"voiceCompanion": true, "realtimeAvatar": true, "familyMembersMax": "custom"}
  }'::jsonb,
  'Free accounts receive one idempotent 5-credit Voice+Avatar trial. One credit is approximately one call minute.',
  now()
)
on conflict (policy_key, version) do update
set active = excluded.active,
    plan_order = excluded.plan_order,
    policy = excluded.policy,
    notes = excluded.notes,
    activated_at = coalesce(entitlement_policy_versions.activated_at, excluded.activated_at);

commit;
