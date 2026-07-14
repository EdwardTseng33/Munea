-- Family-circle invitation integrity.
-- Run after 007_family_cloud_state_foundation.sql on existing projects.

begin;

alter table public.family_invitations
  drop constraint if exists family_invitations_status_check;
alter table public.family_invitations
  add constraint family_invitations_status_check
  check (status in ('pending', 'applied', 'accepted', 'rejected', 'revoked', 'expired'));

alter table public.family_state_entries
  drop constraint if exists family_state_entries_state_key_check;
alter table public.family_state_entries
  add constraint family_state_entries_state_key_check
  check (state_key in ('circle', 'activities', 'familyFeed', 'meds', 'visit', 'routine', 'wallet'));

commit;
