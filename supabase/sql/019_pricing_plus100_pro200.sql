-- 2026-07-17 Edward pricing decision: Plus 100 / Pro 200 monthly points
-- (prices unchanged: Plus NT$599, Pro NT$1,199; per-minute anchor NT$6).
-- Point packs become 100/300/600/1000 points (Apple product IDs unchanged).
-- Run after 018_strip_medication_photos.sql.

begin;

update public.entitlement_policy_versions
set active = false
where policy_key = 'munea_app_store_v1';

insert into public.entitlement_policy_versions (
  policy_key, version, active, plan_order, policy, notes, activated_at
) values (
  'munea_app_store_v1',
  4,
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
      "monthlyPoints": 100,
      "familyMembersMax": 4
    },
    "pro": {
      "voiceCompanion": true,
      "realtimeAvatar": true,
      "monthlyPoints": 200,
      "familyMembersMax": 12
    }
  }'::jsonb,
  'Munea 1.0.39 plans (2026-07-17): one-time 5-credit Free trial, Plus 100 monthly points, Pro 200 monthly points; packs 100/300/600/1000.',
  now()
)
on conflict (policy_key, version) do update
set active = excluded.active,
    plan_order = excluded.plan_order,
    policy = excluded.policy,
    notes = excluded.notes,
    activated_at = coalesce(entitlement_policy_versions.activated_at, excluded.activated_at);

commit;
