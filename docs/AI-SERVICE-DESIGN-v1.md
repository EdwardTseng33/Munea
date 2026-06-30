# Munea AI Service Design v1

> Updated: 2026-06-30
> Scope: model/service design for Munea's three-brain AI companion architecture.

## Executive Decision

Munea should compete on AI service design, not on training a proprietary foundation model in v1.

The product moat is:

1. a speech-to-speech companion that feels present,
2. a long-term memory system that knows what should be remembered, updated, forgotten, or escalated,
3. a perception layer that knows time, weather, family context, user interests, and current facts,
4. a safety layer that prevents the companion from becoming unsafe medical, crisis, or therapeutic advice,
5. a data model that can survive App Store review, subscriptions, family permissions, privacy export, and deletion.

The current v1 recommendation:

| Brain | Primary v1 model/provider | Runtime profile | Responsibility |
|---|---|---|---|
| Reflex Brain | Gemini Live primary through `MuneaVoiceProvider` | low-latency real-time | speech-to-speech conversation, interruption, voice presence |
| Butler Brain | Claude Sonnet 4.6 through `MuneaBrainRouter` | `quick`, `standard`, `deep` effort profiles | memory extraction, summaries, care planning, topic preparation, family digest |
| Guardian Brain | deterministic safety rules + Claude Sonnet 4.6 + moderation/classifier layer | `standard` and `deep` for risk review | crisis detection, medical boundary, escalation, safety response policy |

Butler and Guardian may both use Claude Sonnet 4.6 at MVP, but they must remain separate product brains with separate prompts, inputs, output schemas, logs, and authority.

## Research Notes

Current model/provider direction was reviewed against official documentation and active 2026 agent-memory patterns:

- Google Gemini Live API: low-latency real-time audio/video interaction direction for Reflex Brain.
- Anthropic Claude model and extended-thinking documentation: suitable for long-context synthesis, structured reasoning, and adjustable thinking budgets for Butler and Guardian work.
- OpenAI Moderation / Realtime / reasoning-effort documentation: useful as safety classifier or alternate real-time provider, but not the sole Guardian authority.
- Mem0: open-source persistent memory direction for agent memory extraction and retrieval.
- Zep / Graphiti: temporal knowledge graph direction for time-aware memory updates.
- Letta and LangGraph memory patterns: memory as an explicit state layer, not a long prompt appendix.

Relevant source URLs:

- https://ai.google.dev/gemini-api/docs/live
- https://docs.anthropic.com/en/docs/about-claude/models/overview
- https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking
- https://platform.openai.com/docs/guides/moderation
- https://platform.openai.com/docs/guides/realtime
- https://platform.openai.com/docs/guides/reasoning
- https://docs.mem0.ai/
- https://help.getzep.com/graphiti/
- https://docs.letta.com/
- https://langchain-ai.github.io/langgraph/concepts/memory/

## Why Not One Model For Everything

One-model architecture is simpler, but it fails Munea's product needs:

- Reflex must be fast and voice-native.
- Butler must be accurate, contextual, and patient enough for background synthesis.
- Guardian must have authority to interrupt or constrain the experience.
- Memory must be auditable, deletable, scoped by account/person/family, and not hidden inside a provider's chat history.

Munea's architecture should therefore use model adapters plus product-owned state.

```text
User voice
  -> Reflex Brain: real-time conversation
  -> Guardian Brain: input/output safety gate
  -> Avatar Runtime: face, mouth, state, presence
  -> Butler Brain: post-session memory, summaries, care plans
  -> Supabase: structured memory, events, safety records, consent, audit
```

## Model Effort Profiles

MVP can keep Butler and Guardian on Sonnet first and tune effort/thinking before adding Haiku.

| Profile | Purpose | Example tasks |
|---|---|---|
| `quick` | low-cost extraction and labels | extract memory candidates, tag topic, rewrite reminder |
| `standard` | normal background reasoning | daily summary, family note, care context, safe suggestion |
| `deep` | high-stakes or long-horizon review | weekly memory reconciliation, repeated mood pattern, complex Guardian risk review |

Haiku remains a cost optimization option after usage is measurable. Do not begin by degrading care quality before the product loop is validated.

## Butler Brain Design

Butler Brain is the background care-and-context system.

It should not interrupt the live conversation. It prepares context before a session, extracts memory after a session, and produces family/care outputs when useful.

Butler tasks:

- memory candidate extraction,
- memory retrieval and ranking,
- daily check-in context,
- weekly care summary,
- family digest draft,
- reminder suggestions,
- topic preparation,
- interest graph updates,
- Wisdom Lens suggestions when appropriate.

Butler output must be structured:

```json
{
  "summary": "",
  "memoryCandidates": [],
  "careSignals": [],
  "familyShareCandidates": [],
  "topicSuggestions": [],
  "followUpQuestions": [],
  "safetyNotes": []
}
```

Butler must not:

- diagnose,
- prescribe,
- tell the user to change medication,
- retain raw transcripts by default,
- share sensitive content with family without consent policy.

## Guardian Brain Design

Guardian Brain is not a friendly co-host. It is a safety and boundary authority.

Guardian tasks:

- detect self-harm/crisis language,
- detect medical emergency signals,
- detect medical boundary requests,
- detect repeated distress patterns,
- classify whether family notification is a candidate,
- produce safe response policy for Reflex,
- create safety event/audit records.

Guardian pipeline:

```text
input text / transcript
  -> deterministic high-confidence rules
  -> model/classifier review for ambiguous cases
  -> policy decision
  -> Reflex instruction or escalation
  -> safety event if needed
```

Risk levels:

| Level | Meaning | Action |
|---|---|---|
| `none` | no relevant risk | allow |
| `low` | emotional distress or gentle concern | supportive check-in |
| `medium` | medical boundary or repeated concerning pattern | safe boundary response + audit candidate |
| `high` | possible emergency | advise urgent help + family notification candidate |
| `critical` | self-harm or imminent crisis | interrupt, crisis guidance, escalation |

Guardian must not rely on a generative answer alone. Rules and policy must have priority.

## Long-Term Memory Architecture

Munea memory must behave like a careful companion, not a transcript dump.

Memory lifecycle:

```text
conversation
  -> candidate extraction
  -> type/sensitivity classification
  -> confidence + importance score
  -> consent and retention policy
  -> structured storage
  -> retrieval before conversation
  -> update / confirm / supersede
  -> decay / archive / delete
```

Recommended MVP storage:

- Supabase Postgres for structured memory rows,
- `pgvector` for semantic retrieval after schema is applied,
- JSON fallback only for local prototype,
- later evaluate temporal graph memory using Graphiti/Zep or Mem0-style persistent memory.

Memory types:

| Type | Examples | Retention behavior |
|---|---|---|
| `identity` | name preference, locale, living region | durable, user-editable |
| `preference` | likes movies, dislikes noisy places | durable, confirm/update over time |
| `relationship` | daughter name, caregiver, spouse | durable, high permission sensitivity |
| `routine` | sleeps at 22:00, morning walk, medication reminder | durable but requires confirmation |
| `health_context` | blood pressure concern, dizziness mention | sensitive, time-bounded unless confirmed |
| `emotion` | lonely this week, anxious recently | decays unless repeated |
| `topic_interest` | movies, music, Buddhism, travel | durable but low sensitivity |
| `temporary_event` | tomorrow rains, dinner appointment | short TTL |
| `safety_signal` | crisis phrase, fall, emergency | high retention + audit policy |

Minimum memory row:

```text
id
account_id
person_id
type
content
source
confidence
importance
sensitivity
valid_from
valid_until
last_confirmed_at
supersedes_memory_id
consent_scope
created_at
updated_at
deleted_at
```

Retrieval rules:

- retrieve by person/account scope first,
- filter by consent and sensitivity,
- rank by importance, confidence, recency, topic overlap, and current context,
- never use memories from another family/account,
- show or export memories in privacy export,
- support deletion and correction.

## Perception Layer

Perception is how Munea avoids generic chatbot behavior.

Perception sources:

| Source | Use |
|---|---|
| time/timezone | morning/evening tone, rest windows, routine timing |
| weather | walk suggestions, rain/heat warnings, outdoor alternatives |
| location/region | local recommendations, Taiwan language/culture context |
| calendar/routines | reminders, check-ins, activity suggestions |
| family context | who can be notified, who visited recently |
| current retrieval | movie/news/event facts when user wants current topics |
| interest graph | what the person tends to enjoy |

Example flow:

```text
User wants to talk about movies
  -> read interest memories
  -> check region and language
  -> retrieve current movie facts if recommendation is requested
  -> avoid making up showtimes or availability
  -> respond through Reflex in warm conversation
```

Munea should distinguish between:

- companionship talk, where current facts are optional,
- recommendations, where current facts must be verified,
- health/safety claims, where advice must stay bounded.

## Wisdom Lens

Munea may use spiritual, literary, or life-experience framing, but only as a gentle companion layer.

Allowed lenses:

- Buddhist tone,
- Daoist tone,
- Christian tone,
- Taiwanese proverb/life experience,
- practical real-life example,
- simple reflective question.

Rules:

- do not fabricate exact scripture quotes,
- do not impose religion,
- use only if user preference or conversation context supports it,
- keep it supportive, not therapeutic or authoritarian,
- Guardian overrides Wisdom Lens on crisis/medical risk.

## Technical Framework In Repo

Current implementation anchors:

- `engine/model_router.py`
  - three-brain configuration,
  - effort profiles,
  - memory extraction contract,
  - memory retrieval contract,
  - Guardian risk evaluation contract.
- `POST /ai/brain-status`
  - returns current model/service plan.
- `POST /memory/extract`
  - returns memory candidates and can store structured memories when `action=store`.
  - writes to Supabase `memory_items` when backend env is configured, otherwise falls back to local JSON.
- `POST /memory/retrieve`
  - retrieves scoped memory from Supabase when configured, otherwise from local JSON.
- `POST /guardian/evaluate`
  - evaluates safety risk and emits a safety-related product event when audit is required.
- `engine/memory_items.json`
  - local prototype fallback only.

These endpoints are not the final AI provider integration. They are the durable contract that the provider integration must obey.

## MVP Implementation Order

1. Keep deterministic mock contracts green in smoke tests.
2. Add Supabase `memory_items`, `perception_snapshots`, and `ai_brain_runs` tables.
3. Wire Butler Brain to Claude Sonnet for `/memory/extract`.
4. Wire Guardian Brain to rules + Claude Sonnet + moderation classifier.
5. Add current-facts retrieval only for topics that need freshness, such as movies, weather, local events, or news.
6. Add privacy export/deletion coverage for memory items.
7. Add admin safety-event review surface.

## Definition Of Done For AI Service v1

- Three brains expose health/status endpoints.
- Butler can extract and retrieve memories without storing raw transcripts by default.
- Guardian can block or redirect unsafe outputs.
- Memory rows are account/person scoped.
- Sensitive memories have consent and retention policy.
- Current-topic recommendations use retrieval instead of fabrication.
- App Store trust requirements remain in scope: export, deletion, privacy labels, and non-medical positioning.
