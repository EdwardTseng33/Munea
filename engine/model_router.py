#!/usr/bin/env python3
"""
Munea AI service router.

This module keeps product brain contracts separate from any one provider SDK.
The first implementation is deterministic so smoke tests can verify behavior
before Claude/Gemini/OpenAI credentials are wired into production adapters.
"""
import os
import re
import time
import uuid


DEFAULT_REFLEX_MODEL = "gemini-live-primary"
DEFAULT_BUTLER_MODEL = "claude-sonnet-4-6"
DEFAULT_GUARDIAN_MODEL = "claude-sonnet-4-6"
DEFAULT_MODERATION_MODEL = "omni-moderation-latest"

MEMORY_TYPES = {
    "identity",
    "preference",
    "relationship",
    "routine",
    "health_context",
    "emotion",
    "topic_interest",
    "temporary_event",
    "safety_signal",
}

SENSITIVE_TYPES = {"health_context", "emotion", "safety_signal"}

TOPIC_DOMAINS = {
    "books": {
        "keywords": ["book", "books", "novel", "reading", "author", "literature"],
        "freshness": "medium",
        "sources": ["book_catalog", "library_or_store_availability", "reviews"],
    },
    "travel": {
        "keywords": ["travel", "trip", "hotel", "flight", "vacation", "outing"],
        "freshness": "high",
        "sources": ["weather", "maps", "local_events", "transportation"],
    },
    "local_activities": {
        "keywords": ["activity", "event", "museum", "walk", "park", "restaurant", "outing"],
        "freshness": "high",
        "sources": ["weather", "local_events", "opening_hours", "maps"],
    },
    "exercise": {
        "keywords": ["exercise", "sport", "walk", "yoga", "swim", "gym", "run"],
        "freshness": "medium",
        "sources": ["weather", "routine", "health_boundary", "local_facilities"],
    },
    "finance": {
        "keywords": ["stock", "market", "finance", "invest", "economy", "etf", "fund"],
        "freshness": "high",
        "sources": ["market_data", "news", "risk_disclaimer"],
    },
    "video_entertainment": {
        "keywords": [
            "movie",
            "film",
            "series",
            "drama",
            "kdrama",
            "korean drama",
            "jdrama",
            "japanese drama",
            "cdrama",
            "chinese drama",
            "taiwan drama",
            "twdrama",
            "taiwanese drama",
            "netflix",
            "streaming",
            "cinema",
            "show",
            "variety",
            "anime",
            "documentary",
        ],
        "freshness": "high",
        "sources": ["streaming_catalog", "regional_availability", "showtimes", "reviews"],
    },
    "music_audio": {
        "keywords": ["music", "song", "singer", "album", "podcast", "concert"],
        "freshness": "medium",
        "sources": ["music_catalog", "events", "reviews"],
    },
    "food_cooking": {
        "keywords": ["food", "cook", "recipe", "restaurant", "tea", "coffee"],
        "freshness": "medium",
        "sources": ["preference_memory", "weather", "local_options"],
    },
    "news_current_affairs": {
        "keywords": ["news", "politics", "world", "current", "today"],
        "freshness": "high",
        "sources": ["trusted_news", "date_context"],
    },
    "spiritual_reflection": {
        "keywords": ["buddhism", "dao", "bible", "faith", "meaning", "life"],
        "freshness": "low",
        "sources": ["curated_wisdom_sources", "user_preference"],
    },
}


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def env_model(key, fallback):
    return os.environ.get(key) or fallback


def brain_config():
    return {
        "reflex": {
            "role": "real_time_voice_conversation",
            "provider": os.environ.get("MUNEA_REFLEX_PROVIDER") or "google",
            "model": env_model("MUNEA_REFLEX_MODEL", DEFAULT_REFLEX_MODEL),
            "interface": "MuneaVoiceProvider",
            "latencyTargetMs": 1200,
            "writesMemory": False,
        },
        "butler": {
            "role": "memory_summary_care_planning",
            "provider": os.environ.get("MUNEA_BUTLER_PROVIDER") or "anthropic",
            "model": env_model("MUNEA_BUTLER_MODEL", DEFAULT_BUTLER_MODEL),
            "interface": "MuneaBrainRouter",
            "writesMemory": True,
            "defaultEffort": "standard",
        },
        "guardian": {
            "role": "safety_boundary_risk_classification",
            "provider": os.environ.get("MUNEA_GUARDIAN_PROVIDER") or "anthropic",
            "model": env_model("MUNEA_GUARDIAN_MODEL", DEFAULT_GUARDIAN_MODEL),
            "moderationProvider": os.environ.get("MUNEA_MODERATION_PROVIDER") or "openai",
            "moderationModel": env_model("MUNEA_MODERATION_MODEL", DEFAULT_MODERATION_MODEL),
            "interface": "MuneaBrainRouter",
            "writesMemory": True,
            "defaultEffort": "standard",
        },
    }


def effort_profile(name):
    profiles = {
        "quick": {
            "effort": "low",
            "thinking": "adaptive_low",
            "maxOutputTokens": 1200,
            "useCases": ["short_summary", "tagging", "simple_memory_candidate"],
        },
        "standard": {
            "effort": "medium",
            "thinking": "adaptive_medium",
            "maxOutputTokens": 3000,
            "useCases": ["daily_summary", "care_context", "family_digest"],
        },
        "deep": {
            "effort": "high",
            "thinking": "adaptive_high",
            "maxOutputTokens": 8000,
            "useCases": ["weekly_memory_reconciliation", "complex_risk_review"],
        },
    }
    return profiles.get(name or "standard", profiles["standard"])


def brain_status_response():
    return {
        "ok": True,
        "service": "munea-ai-service",
        "version": 1,
        "brains": brain_config(),
        "topicDomains": topic_domain_catalog(),
        "effortProfiles": {
            "quick": effort_profile("quick"),
            "standard": effort_profile("standard"),
            "deep": effort_profile("deep"),
        },
        "contracts": [
            "brain-status",
            "memory-extract",
            "memory-retrieve",
            "guardian-evaluate",
            "topic-perception-plan",
        ],
    }


def text_from_payload(data):
    data = data or {}
    if isinstance(data.get("text"), str):
        return data["text"]
    history = data.get("history") or []
    parts = []
    for item in history:
        if isinstance(item, dict):
            value = item.get("text") or item.get("content") or ""
            if value:
                parts.append(str(value))
    return "\n".join(parts)


def tokenize(text):
    return {t for t in re.split(r"[\s,.;:!?，。！？、]+", (text or "").lower()) if t}


def topic_domain_catalog():
    return {
        key: {
            "freshness": value["freshness"],
            "sources": value["sources"],
        }
        for key, value in TOPIC_DOMAINS.items()
    }


def detect_topic_domains(text):
    tokens = tokenize(text)
    lowered = (text or "").lower()
    domains = []
    for domain, config in TOPIC_DOMAINS.items():
        matched = sorted({k for k in config["keywords"] if k in tokens or k in lowered})
        if matched:
            domains.append({
                "domain": domain,
                "matched": matched,
                "freshness": config["freshness"],
                "requiredSources": config["sources"],
            })
    return domains


def topic_perception_plan_response(data):
    data = data or {}
    text = data.get("topic") or data.get("query") or text_from_payload(data)
    domains = detect_topic_domains(text)
    needs_current_facts = any(d["freshness"] in {"medium", "high"} for d in domains)
    return {
        "ok": True,
        "brain": "butler",
        "query": text,
        "domains": domains,
        "needsCurrentFacts": needs_current_facts,
        "antiFabricationPolicy": {
            "doNotInventAvailability": True,
            "verifyRecommendationsWhenFreshnessIsHigh": True,
            "sayWhenCurrentDataIsUnavailable": True,
        },
        "perceptionSources": sorted({source for d in domains for source in d["requiredSources"]}),
        "supportedDomains": topic_domain_catalog(),
    }


def make_candidate(memory_type, content, confidence=0.7, importance=0.5, valid_days=None, source="conversation"):
    sensitivity = "sensitive" if memory_type in SENSITIVE_TYPES else "normal"
    return {
        "candidateId": "memcand_" + uuid.uuid4().hex[:10],
        "type": memory_type,
        "content": content.strip()[:500],
        "confidence": round(float(confidence), 2),
        "importance": round(float(importance), 2),
        "sensitivity": sensitivity,
        "validDays": valid_days,
        "source": source,
        "createdAt": utc_now(),
    }


def memory_extract_response(data):
    text = text_from_payload(data)
    lowered = text.lower()
    candidates = []

    if any(k in lowered for k in ["like", "love", "prefer", "favorite", "enjoy"]):
        candidates.append(make_candidate("preference", text, 0.72, 0.68, None))
    if any(k in lowered for k in ["dislike", "hate", "avoid", "do not like"]):
        candidates.append(make_candidate("preference", text, 0.72, 0.7, None))
    if any(k in lowered for k in ["daughter", "son", "wife", "husband", "mother", "father", "family", "grandchild"]):
        candidates.append(make_candidate("relationship", text, 0.75, 0.82, None))
    if any(k in lowered for k in ["medicine", "medication", "doctor visit", "walk every", "sleep at", "exercise every"]):
        candidates.append(make_candidate("routine", text, 0.7, 0.8, 90))
    if detect_topic_domains(text):
        candidates.append(make_candidate("topic_interest", text, 0.7, 0.6, None))
    if any(k in lowered for k in ["lonely", "sad", "anxious", "afraid", "insomnia", "mood", "depressed"]):
        candidates.append(make_candidate("emotion", text, 0.66, 0.7, 30))
    if any(k in lowered for k in ["dizzy", "chest pain", "fell", "blood pressure", "pain", "fever"]):
        candidates.append(make_candidate("health_context", text, 0.65, 0.78, 30))
    if any(k in lowered for k in ["today", "tomorrow", "weather", "rain", "later"]):
        candidates.append(make_candidate("temporary_event", text, 0.62, 0.35, 3))
    if guardian_evaluate_response({"text": text})["risk"]["level"] in {"medium", "high", "critical"}:
        candidates.append(make_candidate("safety_signal", text, 0.8, 1.0, 365, "guardian"))

    if not candidates and text.strip():
        candidates.append(make_candidate("temporary_event", text, 0.45, 0.25, 1))

    return {
        "ok": True,
        "brain": "butler",
        "modelPlan": brain_config()["butler"],
        "effort": effort_profile((data or {}).get("effort") or "quick"),
        "inputLength": len(text),
        "topicDomains": detect_topic_domains(text),
        "candidates": candidates,
        "storagePolicy": {
            "storeRawTranscriptByDefault": False,
            "requiresConsentForSensitive": True,
            "supportsUpdateAndSupersede": True,
        },
    }


def normalize_memory_item(candidate, person_id="local-person-self"):
    return {
        "id": "mem_" + uuid.uuid4().hex[:12],
        "personId": person_id,
        "type": candidate.get("type") if candidate.get("type") in MEMORY_TYPES else "temporary_event",
        "content": candidate.get("content") or "",
        "confidence": candidate.get("confidence", 0.5),
        "importance": candidate.get("importance", 0.5),
        "sensitivity": candidate.get("sensitivity") or "normal",
        "validDays": candidate.get("validDays"),
        "source": candidate.get("source") or "conversation",
        "createdAt": candidate.get("createdAt") or utc_now(),
        "updatedAt": utc_now(),
        "lastConfirmedAt": None,
        "supersedesMemoryId": None,
        "consentScope": "user",
        "metadata": {
            "topicDomains": detect_topic_domains(candidate.get("content") or ""),
        },
    }


def score_memory(query, item):
    q = tokenize(query)
    content = item.get("content") or ""
    tokens = tokenize(content)
    overlap = len(q & tokens)
    importance = float(item.get("importance") or 0)
    confidence = float(item.get("confidence") or 0)
    type_bonus = 0.2 if item.get("type") in {"relationship", "routine", "preference"} else 0
    return overlap * 1.2 + importance + confidence + type_bonus


def memory_retrieve_response(data, memory_items=None):
    data = data or {}
    query = data.get("query") or text_from_payload(data)
    memory_items = memory_items or []
    ranked = sorted(memory_items, key=lambda item: score_memory(query, item), reverse=True)
    limit = int(data.get("limit") or 8)
    return {
        "ok": True,
        "brain": "butler",
        "query": query,
        "topicDomains": detect_topic_domains(query),
        "count": min(len(ranked), limit),
        "memories": ranked[:limit],
        "retrievalPolicy": {
            "usesStructuredFilters": True,
            "usesVectorSearchLater": True,
            "usesTemporalGraphLater": True,
        },
    }


def guardian_evaluate_response(data):
    text = text_from_payload(data)
    categories = []
    level = "none"
    action = "allow"

    critical_terms = ["want to die", "kill myself", "suicide", "hurt myself", "self harm"]
    emergency_terms = ["chest pain", "cannot breathe", "fainted", "fell and cannot get up", "stroke", "heart attack"]
    medical_terms = ["diagnose", "prescribe", "dosage", "stop medication", "treatment"]
    distress_terms = ["lonely", "sad", "anxious", "insomnia", "afraid", "panic", "depressed"]

    lowered = text.lower()
    if any(k in lowered for k in critical_terms):
        categories.append("self_harm_crisis")
        level = "critical"
        action = "interrupt_and_escalate"
    elif any(k in lowered for k in emergency_terms):
        categories.append("medical_emergency_signal")
        level = "high"
        action = "advise_emergency_help"
    elif any(k in lowered for k in medical_terms):
        categories.append("medical_boundary")
        level = "medium"
        action = "safe_completion_with_boundary"
    elif any(k in lowered for k in distress_terms):
        categories.append("emotional_distress")
        level = "low"
        action = "supportive_check_in"

    return {
        "ok": True,
        "brain": "guardian",
        "modelPlan": brain_config()["guardian"],
        "effort": effort_profile((data or {}).get("effort") or "standard"),
        "risk": {
            "level": level,
            "categories": categories,
            "action": action,
            "requiresHumanEscalation": level in {"high", "critical"},
            "requiresAuditEvent": level in {"medium", "high", "critical"},
        },
        "responsePolicy": {
            "notMedicalDiagnosis": True,
            "reflexCanContinue": level not in {"high", "critical"},
            "familyNotificationCandidate": level in {"high", "critical"},
        },
    }
