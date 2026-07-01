# Munea Companion Persona Layer v1

> Updated: 2026-06-30
> Scope: six companion characters, user naming, and how persona shapes AI replies without becoming an unsafe or fictional authority.

## Executive Decision

Munea needs a named **Companion Persona Layer** between app identity and the three AI brains.

This layer is not a fourth brain. It is the orchestration layer that determines how the selected companion sounds, relates, frames topics, and expresses care while Reflex, Butler, and Guardian keep their separate responsibilities.

```text
Final reply
  = companion persona
  + user memory
  + live perception
  + current conversation
  + safety rules
  + voice / avatar expression limits
```

The product promise is not "one generic AI with six skins." The six companions must feel meaningfully different while sharing the same factuality, privacy, and safety rules.

## Where It Sits

```text
User / account / family state
  -> Companion Persona Layer
       template_id
       display_name
       voice_profile
       avatar_asset
       relationship style
       tone and speaking rhythm
       character boundaries
  -> Reflex Brain
  -> Butler Brain
  -> Guardian Brain
  -> Voice Provider + Avatar Runtime
```

The persona layer shapes delivery. It must not override Guardian, invent facts, leak memory, or turn reminders into medical advice.

## Identity Split

Munea must keep these concepts separate:

| Field | Meaning | Example |
|---|---|---|
| `template_id` | Selected persona / visual / voice template | `nening-real-female` |
| `display_name` | User-given name | `小晴` |
| `default_name` | Starter name before user renames | `寧寧` |
| `persona_archetype` | Stable personality pattern | warm family companion |
| `voice_profile` | Voice and performance direction | `Leda` |
| `avatar_asset` | Face/body asset | `avatars/nening-real-female-full.png` |
| `relationship_state` | How this user and companion have grown together | trusted, playful, quieter in mornings |

Changing `display_name` should not change the face, voice, memory, or persona.

Changing `template_id` should change the persona expression, voice, and avatar, but the user's own memories and data rights remain intact.

## Six Persona Templates

The first six templates should be stable backend templates, not hard-coded UI labels only.

| Template | Default role | Primary style | Product purpose |
|---|---|---|---|
| `nening-real-female` | warm family companion | gentle, attentive, emotionally present | default trust-building companion |
| `companion-real-male` | calm brother / steady friend | grounded, practical, protective | users who prefer calmer directness |
| `munea-2d-xiaoyun` | bright friend | light, curious, encouraging | softer daily companionship |
| `munea-2d-ayuan` | thoughtful friend | observant, reflective, tidy | calmer topic and routine support |
| `munea-2d-mimi` | playful small companion | cute, warm, lightly mischievous | low-pressure companionship |
| `munea-2d-wangcai` | loyal guardian companion | steady, warm, simple | reassurance and routine support |

Each template must define:

- `persona_archetype`
- `relationship_frame`
- `tone_profile`
- `conversation_style`
- `emotional_style`
- `humor_style`
- `wisdom_style`
- `topic_biases`
- `boundary_style`
- `voice_profile`
- `avatar_asset`
- `prompt_directives`

## Reply Composition

The runtime should compose context in this order:

1. **Guardian pre-check**
   - classify crisis, medical boundary, emergency, or sensitive family sharing risk.
2. **Butler context pack**
   - retrieve relevant memory, today's perception, topic facts, and care context.
3. **Persona context pack**
   - selected template, user-given name, tone profile, speaking rhythm, relationship state.
4. **Reflex delivery**
   - low-latency spoken response, no transcript-first UX.
5. **Guardian output check**
   - prevent unsafe medical advice, fake certainty, over-sharing, or inappropriate escalation.
6. **Butler post-session update**
   - extract memory candidates, update relationship state, write summaries, and schedule follow-up.

## Memory Separation

Munea must separate memory into four concepts:

| Memory class | Owner | Purpose |
|---|---|---|
| User memory | person/account | facts, preferences, routines, family, emotions |
| Persona template | product/backend | stable character traits and voice |
| Relationship memory | person + companion profile | how this user prefers this companion to relate |
| Perception facts | time/location/topic snapshots | current reality used for timely conversation |

Do not mix persona fiction into user memory. A companion can have a light background and style, but it must not create false claims that affect care, family, or health decisions.

Production database path:

- `companion_persona_templates` stores the six product-owned persona templates.
- `companion_relationship_states` stores user + companion-specific relationship growth, tone overrides, preferred address, and boundaries.
- `memory_items` remains the source for user facts and interests.
- `perception_snapshots` remains the source for time, weather, topic, local, and current-fact context.

## Safety And Trust Rules

Persona is subordinate to safety:

- Guardian overrides persona.
- Health and medication remain reminders and boundaries, not diagnosis or dosage advice.
- Finance remains factual discussion, not personalized investment instruction.
- Current recommendations need current facts when freshness matters.
- Family sharing must respect consent.
- Raw transcripts are not the default retained record.

## 2026-06 Technical Direction Check

The current Munea architecture is directionally strong for June 2026:

- Real-time voice should stay behind `MuneaVoiceProvider`, with Gemini Live / Interactions as the first candidate because the official Live API direction supports low-latency voice/vision, barge-in, tool use, proactive audio, and affective dialog.
- Butler and Guardian should remain separate service contracts even if both start on Claude Sonnet 5. Claude's adaptive / extended thinking controls fit variable-depth background reasoning better than forcing one cheap model for all care decisions.
- Supabase Postgres + RLS remains a strong v1 source of truth for account/person/family-scoped memory, because RLS protects exposed tables and lets policies enforce `auth.uid()` ownership.
- Persona templates should be product-owned structured config, not only prompt text. This protects future provider swaps.

Recommended refinement:

```text
Reflex: voice-native and low-latency.
Butler: memory, perception, summaries, relationship updates.
Guardian: safety authority.
Persona Layer: expression, relationship style, character continuity.
Data Layer: Supabase-scoped, exportable, deletable.
```

## Definition Of Done

- `/ai/brain-status` exposes persona layer capability.
- `/persona/context` returns a structured persona context pack.
- `companion_profiles` keeps `template_id` and `display_name` separate.
- relationship state has a database path before production launch.
- smoke tests prove `sameFactsDifferentVoice`: the same memory/perception can produce different style directives for different companions.
- product docs state the final reply formula explicitly.
