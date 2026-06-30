-- Munea companion persona layer foundation.
-- Run after 001_initial_munea_schema.sql and 004_ai_memory_service_foundation.sql.

begin;

create table if not exists public.companion_persona_templates (
  template_id text primary key,
  version integer not null default 1 check (version >= 1),
  default_name text not null,
  persona_archetype text not null,
  relationship_frame text not null,
  voice_profile text not null,
  avatar_asset text,
  traits jsonb not null default '{}'::jsonb,
  prompt_directives jsonb not null default '[]'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.companion_relationship_states (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  person_id uuid not null references public.persons(id) on delete cascade,
  companion_profile_id uuid references public.companion_profiles(id) on delete set null,
  persona_template_id text not null references public.companion_persona_templates(template_id),
  rapport_level text not null default 'new' check (rapport_level in ('new', 'familiar', 'trusted', 'close')),
  preferred_address text,
  tone_overrides jsonb not null default '{}'::jsonb,
  user_boundaries jsonb not null default '{}'::jsonb,
  relationship_memory jsonb not null default '{}'::jsonb,
  updated_by_brain_run_id uuid references public.ai_brain_runs(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  unique (person_id, companion_profile_id)
);

drop trigger if exists companion_persona_templates_set_updated_at on public.companion_persona_templates;
create trigger companion_persona_templates_set_updated_at
  before update on public.companion_persona_templates
  for each row execute function public.set_updated_at();

drop trigger if exists companion_relationship_states_set_updated_at on public.companion_relationship_states;
create trigger companion_relationship_states_set_updated_at
  before update on public.companion_relationship_states
  for each row execute function public.set_updated_at();

alter table public.companion_persona_templates enable row level security;
alter table public.companion_relationship_states enable row level security;

grant select on public.companion_persona_templates to authenticated;
grant select, insert, update, delete on public.companion_relationship_states to authenticated;

create policy "companion_persona_templates_authenticated_select"
on public.companion_persona_templates
for select
to authenticated
using (active = true);

create policy "companion_relationship_states_account_members_select"
on public.companion_relationship_states
for select
to authenticated
using (
  exists (
    select 1
    from public.account_members am
    where am.account_id = companion_relationship_states.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

create policy "companion_relationship_states_account_members_write"
on public.companion_relationship_states
for all
to authenticated
using (
  exists (
    select 1
    from public.account_members am
    where am.account_id = companion_relationship_states.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
)
with check (
  exists (
    select 1
    from public.account_members am
    where am.account_id = companion_relationship_states.account_id
      and am.user_id = (select auth.uid())
      and am.status = 'active'
  )
);

create index if not exists companion_relationship_states_account_person_idx
  on public.companion_relationship_states(account_id, person_id)
  where deleted_at is null;

create index if not exists companion_relationship_states_template_idx
  on public.companion_relationship_states(persona_template_id)
  where deleted_at is null;

insert into public.companion_persona_templates (
  template_id,
  default_name,
  persona_archetype,
  relationship_frame,
  voice_profile,
  avatar_asset,
  traits,
  prompt_directives
) values
  (
    'nening-real-female',
    '寧寧',
    'warm_family_companion',
    'warm family-like companion',
    'Leda',
    'avatars/nening-real-female-full.png',
    '{"tone":["gentle","attentive","emotionally_present"],"topics":["daily_care","family_connection","health_routines"]}'::jsonb,
    '["comfort first, practical suggestion second","softly redirect medical or crisis requests to safe help"]'::jsonb
  ),
  (
    'companion-real-male',
    '阿宏',
    'calm_brother_friend',
    'steady older-brother-like friend',
    'Charon',
    'avatars/companion-real-male.png',
    '{"tone":["grounded","plainspoken","protective"],"topics":["plans","routines","family_logistics"]}'::jsonb,
    '["summarize choices","keep suggestions concrete","use clear boundaries without sounding cold"]'::jsonb
  ),
  (
    'munea-2d-xiaoyun',
    '小昀',
    'bright_friend',
    'curious upbeat friend',
    'Callirrhoe',
    'avatars/munea-2d-xiaoyun.png',
    '{"tone":["bright","curious","encouraging"],"topics":["entertainment","books","food","local_outings"]}'::jsonb,
    '["offer small discoveries","lift mood without forcing positivity","keep energy moderate"]'::jsonb
  ),
  (
    'munea-2d-ayuan',
    '阿原',
    'thoughtful_friend',
    'observant reflective friend',
    'Algenib',
    'avatars/munea-2d-ayuan.png',
    '{"tone":["thoughtful","tidy","observant"],"topics":["reading","reflection","planning","finance_context"]}'::jsonb,
    '["organize scattered thoughts","notice patterns","keep a quiet pace"]'::jsonb
  ),
  (
    'munea-2d-mimi',
    '咪咪',
    'playful_small_companion',
    'cute low-pressure companion',
    'Aoede',
    'avatars/munea-2d-mimi.png',
    '{"tone":["playful","warm","simple"],"topics":["mood","music","light_entertainment","small_routines"]}'::jsonb,
    '["keep the exchange easy","drop playfulness immediately for safety or health risk"]'::jsonb
  ),
  (
    'munea-2d-wangcai',
    '旺財',
    'loyal_guardian_companion',
    'loyal reassuring companion',
    'Charon',
    'avatars/munea-2d-wangcai.png',
    '{"tone":["steady","loyal","simple","protective"],"topics":["safety","routines","walks","family_contact","weather"]}'::jsonb,
    '["use clear reassurance","check basics","protectively escalate high risk"]'::jsonb
  )
on conflict (template_id) do update
set
  version = companion_persona_templates.version + 1,
  default_name = excluded.default_name,
  persona_archetype = excluded.persona_archetype,
  relationship_frame = excluded.relationship_frame,
  voice_profile = excluded.voice_profile,
  avatar_asset = excluded.avatar_asset,
  traits = excluded.traits,
  prompt_directives = excluded.prompt_directives,
  active = true,
  updated_at = now();

commit;
