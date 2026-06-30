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

PERSONA_TEMPLATES = {
    "nening-real-female": {
        "defaultName": "寧寧",
        "personaArchetype": "warm_family_companion",
        "relationshipFrame": "warm family-like companion",
        "toneProfile": ["gentle", "attentive", "emotionally present", "lightly proactive"],
        "conversationStyle": ["uses soft check-ins", "asks one natural follow-up", "avoids sounding clinical"],
        "emotionalStyle": "comfort first, practical suggestion second",
        "humorStyle": "small warmth, never teasing when risk is present",
        "wisdomStyle": "simple life reflection when invited",
        "topicBiases": ["daily care", "family connection", "health routines", "gentle interests"],
        "boundaryStyle": "softly redirects medical or crisis requests to safe help",
        "voiceProfile": "Leda",
        "avatarAsset": "avatars/nening-real-female-full.png",
    },
    "companion-real-male": {
        "defaultName": "阿宏",
        "personaArchetype": "calm_brother_friend",
        "relationshipFrame": "steady older-brother-like friend",
        "toneProfile": ["grounded", "plainspoken", "protective", "calm"],
        "conversationStyle": ["summarizes choices", "keeps suggestions concrete", "uses fewer decorations"],
        "emotionalStyle": "steady reassurance with practical next steps",
        "humorStyle": "dry and gentle only when the user is relaxed",
        "wisdomStyle": "practical lived-experience framing",
        "topicBiases": ["plans", "routines", "outings", "family logistics"],
        "boundaryStyle": "clear boundaries without sounding cold",
        "voiceProfile": "Charon",
        "avatarAsset": "avatars/companion-real-male.png",
    },
    "munea-2d-xiaoyun": {
        "defaultName": "小昀",
        "personaArchetype": "bright_friend",
        "relationshipFrame": "curious upbeat friend",
        "toneProfile": ["bright", "curious", "encouraging", "light"],
        "conversationStyle": ["offers small discoveries", "invites playful exploration", "keeps energy moderate"],
        "emotionalStyle": "lifts mood without forcing positivity",
        "humorStyle": "light and friendly",
        "wisdomStyle": "gentle questions and small reframes",
        "topicBiases": ["entertainment", "books", "food", "local outings", "creative topics"],
        "boundaryStyle": "turns risk into calm grounding and safe support",
        "voiceProfile": "Callirrhoe",
        "avatarAsset": "avatars/munea-2d-xiaoyun.png",
    },
    "munea-2d-ayuan": {
        "defaultName": "阿原",
        "personaArchetype": "thoughtful_friend",
        "relationshipFrame": "observant reflective friend",
        "toneProfile": ["thoughtful", "tidy", "observant", "warm"],
        "conversationStyle": ["organizes scattered thoughts", "notices patterns", "keeps a quiet pace"],
        "emotionalStyle": "validates, then helps name what matters",
        "humorStyle": "subtle and low-key",
        "wisdomStyle": "reflective and concise",
        "topicBiases": ["reading", "reflection", "planning", "finance context", "life stories"],
        "boundaryStyle": "uses calm clarity for sensitive topics",
        "voiceProfile": "Algenib",
        "avatarAsset": "avatars/munea-2d-ayuan.png",
    },
    "munea-2d-mimi": {
        "defaultName": "咪咪",
        "personaArchetype": "playful_small_companion",
        "relationshipFrame": "cute low-pressure companion",
        "toneProfile": ["playful", "warm", "simple", "lightly mischievous"],
        "conversationStyle": ["keeps the exchange easy", "uses short comforting phrases", "does not over-explain"],
        "emotionalStyle": "softens loneliness through light presence",
        "humorStyle": "cute, brief, never dismissive",
        "wisdomStyle": "simple comfort rather than heavy advice",
        "topicBiases": ["mood", "daily companionship", "music", "light entertainment", "small routines"],
        "boundaryStyle": "drops playfulness immediately for safety or health risk",
        "voiceProfile": "Aoede",
        "avatarAsset": "avatars/munea-2d-mimi.png",
    },
    "munea-2d-wangcai": {
        "defaultName": "旺財",
        "personaArchetype": "loyal_guardian_companion",
        "relationshipFrame": "loyal reassuring companion",
        "toneProfile": ["steady", "loyal", "simple", "protective"],
        "conversationStyle": ["uses clear reassurance", "checks basics", "keeps advice short"],
        "emotionalStyle": "reassurance through presence and routine",
        "humorStyle": "warm and simple",
        "wisdomStyle": "plain-hearted encouragement",
        "topicBiases": ["safety", "routines", "walks", "family contact", "weather"],
        "boundaryStyle": "protective escalation when risk is high",
        "voiceProfile": "Charon",
        "avatarAsset": "avatars/munea-2d-wangcai.png",
    },
}

PERSONA_ALIASES = {
    "real-f": "nening-real-female",
    "real-m": "companion-real-male",
    "toon-f": "munea-2d-xiaoyun",
    "toon-m": "munea-2d-ayuan",
    "cat": "munea-2d-mimi",
    "dog": "munea-2d-wangcai",
}

BACKEND_CHAR_TO_TEMPLATE = {
    "寧寧": "nening-real-female",
    "阿宏": "companion-real-male",
    "小昀": "munea-2d-xiaoyun",
    "阿原": "munea-2d-ayuan",
    "咪咪": "munea-2d-mimi",
    "旺財": "munea-2d-wangcai",
}

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
        "keywords": ["book", "books", "novel", "reading", "author", "literature", "書", "小說", "閱讀", "作家", "文學"],
        "freshness": "medium",
        "sources": ["book_catalog", "library_or_store_availability", "reviews"],
    },
    "travel": {
        "keywords": ["travel", "trip", "hotel", "flight", "vacation", "outing", "旅遊", "旅行", "出國", "飯店", "機票", "行程"],
        "freshness": "high",
        "sources": ["weather", "maps", "local_events", "transportation"],
    },
    "local_activities": {
        "keywords": ["activity", "event", "museum", "walk", "park", "restaurant", "outing", "活動", "展覽", "博物館", "散步", "公園", "餐廳", "出去玩"],
        "freshness": "high",
        "sources": ["weather", "local_events", "opening_hours", "maps"],
    },
    "exercise": {
        "keywords": ["exercise", "sport", "walk", "yoga", "swim", "gym", "run", "運動", "健身", "散步", "瑜伽", "游泳", "跑步"],
        "freshness": "medium",
        "sources": ["weather", "routine", "health_boundary", "local_facilities"],
    },
    "finance": {
        "keywords": ["stock", "market", "finance", "invest", "economy", "etf", "fund", "股票", "股市", "財經", "投資", "經濟", "基金"],
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
            "電影",
            "影視",
            "劇",
            "韓劇",
            "日劇",
            "陸劇",
            "台劇",
            "大陸劇",
            "Netflix",
            "網飛",
            "串流",
            "影集",
            "紀錄片",
            "綜藝",
            "動漫",
        ],
        "freshness": "high",
        "sources": ["streaming_catalog", "regional_availability", "showtimes", "reviews"],
    },
    "music_audio": {
        "keywords": ["music", "song", "singer", "album", "podcast", "concert", "音樂", "歌曲", "歌手", "專輯", "Podcast", "演唱會"],
        "freshness": "medium",
        "sources": ["music_catalog", "events", "reviews"],
    },
    "food_cooking": {
        "keywords": ["food", "cook", "recipe", "restaurant", "tea", "coffee", "美食", "煮飯", "料理", "食譜", "餐廳", "茶", "咖啡"],
        "freshness": "medium",
        "sources": ["preference_memory", "weather", "local_options"],
    },
    "news_current_affairs": {
        "keywords": ["news", "politics", "world", "current", "today", "新聞", "時事", "政治", "國際", "今天"],
        "freshness": "high",
        "sources": ["trusted_news", "date_context"],
    },
    "spiritual_reflection": {
        "keywords": ["buddhism", "dao", "bible", "faith", "meaning", "life", "佛經", "道經", "聖經", "信仰", "人生", "意義"],
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
        "personaLayer": {
            "role": "expression_relationship_context",
            "isFourthBrain": False,
            "templateCount": len(PERSONA_TEMPLATES),
            "templates": persona_template_catalog(),
            "compositionFormula": "reply = persona + memory + perception + current_conversation + safety + voice_avatar_limits",
        },
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
            "persona-context",
        ],
    }


def normalize_template_id(template_id):
    template_id = template_id or "nening-real-female"
    return PERSONA_ALIASES.get(template_id, template_id if template_id in PERSONA_TEMPLATES else "nening-real-female")


def template_id_for_backend_char(char):
    return BACKEND_CHAR_TO_TEMPLATE.get(char or "")


def persona_template(template_id):
    return PERSONA_TEMPLATES[normalize_template_id(template_id)]


def persona_template_catalog():
    return {
        template_id: {
            "defaultName": value["defaultName"],
            "personaArchetype": value["personaArchetype"],
            "relationshipFrame": value["relationshipFrame"],
            "voiceProfile": value["voiceProfile"],
            "avatarAsset": value["avatarAsset"],
        }
        for template_id, value in PERSONA_TEMPLATES.items()
    }


def persona_context_response(data):
    data = data or {}
    profile = data.get("companionProfile") or data.get("companion_profile") or {}
    template_id = normalize_template_id(
        data.get("templateId")
        or profile.get("templateId")
        or profile.get("template_id")
        or template_id_for_backend_char(data.get("char"))
    )
    template = persona_template(template_id)
    display_name = (
        data.get("displayName")
        or profile.get("displayName")
        or profile.get("display_name")
        or template["defaultName"]
    )
    display_name = str(display_name).strip()[:24] or template["defaultName"]
    risk = guardian_evaluate_response(data).get("risk", {})
    risk_level = risk.get("level") or "none"

    return {
        "ok": True,
        "layer": "companion_persona",
        "templateId": template_id,
        "displayName": display_name,
        "defaultName": template["defaultName"],
        "persona": {
            "personaArchetype": template["personaArchetype"],
            "relationshipFrame": template["relationshipFrame"],
            "toneProfile": template["toneProfile"],
            "conversationStyle": template["conversationStyle"],
            "emotionalStyle": template["emotionalStyle"],
            "humorStyle": template["humorStyle"],
            "wisdomStyle": template["wisdomStyle"],
            "topicBiases": template["topicBiases"],
            "boundaryStyle": template["boundaryStyle"],
        },
        "voice": {
            "voiceProfile": template["voiceProfile"],
            "avatarAsset": template["avatarAsset"],
            "speechFirst": True,
            "visibleTranscriptDefault": False,
        },
        "promptDirectives": [
            "Address the user through the selected display name only when natural.",
            "Express the same factual context through this persona's tone and relationship frame.",
            "Use memory only if scoped to the current person/account and relevant to the moment.",
            "Use perception facts for current recommendations; say when current data is unavailable.",
            "Never invent schedules, prices, availability, weather, market data, or medical facts.",
            "Guardian safety policy overrides persona style.",
        ],
        "composition": {
            "formula": "reply = persona + memory + perception + current_conversation + safety + voice_avatar_limits",
            "sameFactsDifferentVoice": True,
            "personaOverridesSafety": False,
            "personaStoredAsUserMemory": False,
        },
        "safety": {
            "riskLevel": risk_level,
            "reduceHumor": risk_level in {"low", "medium", "high", "critical"},
            "forceSafetyBoundary": risk_level in {"medium", "high", "critical"},
        },
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
