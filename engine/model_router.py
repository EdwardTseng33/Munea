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
DEFAULT_BUTLER_MODEL = "claude-sonnet-5"
DEFAULT_GUARDIAN_MODEL = "claude-sonnet-5"
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
        "voiceProfile": "Despina",
        "avatarAsset": "avatars/nening-real-female-full.jpg",
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
        "avatarAsset": "avatars/ahong.png",
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
        "avatarAsset": "avatars/xiaoyun-2d.png",
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
        "avatarAsset": "avatars/ayuan-2d.png",
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
    relationship_state = data.get("relationshipState") or data.get("relationship_state") or {}
    relationship_memory = relationship_state.get("relationshipMemory") or relationship_state.get("relationship_memory") or {}
    tone_overrides = relationship_state.get("toneOverrides") or relationship_state.get("tone_overrides") or {}
    user_boundaries = relationship_state.get("userBoundaries") or relationship_state.get("user_boundaries") or {}
    rapport_level = relationship_state.get("rapportLevel") or relationship_state.get("rapport_level") or "new"
    preferred_address = relationship_state.get("preferredAddress") or relationship_state.get("preferred_address")

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
            "speechFirst": bool(tone_overrides.get("speechFirst", True)),
            "visibleTranscriptDefault": False,
        },
        "relationshipState": {
            "rapportLevel": rapport_level,
            "preferredAddress": preferred_address,
            "toneOverrides": tone_overrides,
            "userBoundaries": user_boundaries,
            "relationshipMemory": relationship_memory,
            "updatedAt": relationship_state.get("updatedAt") or relationship_state.get("updated_at"),
        },
        "promptDirectives": [
            "Address the user through the selected display name only when natural.",
            "Express the same factual context through this persona's tone and relationship frame.",
            "Use memory only if scoped to the current person/account and relevant to the moment.",
            "Apply relationship state as delivery guidance: rapport, preferred address, tone overrides, and boundaries can shape phrasing but cannot invent facts.",
            "Use perception facts for current recommendations; say when current data is unavailable.",
            "Never invent schedules, prices, availability, weather, market data, or medical facts.",
            "Guardian safety policy overrides persona style.",
        ],
        "composition": {
            "formula": "reply = persona + memory + perception + current_conversation + safety + voice_avatar_limits",
            "sameFactsDifferentVoice": True,
            "personaOverridesSafety": False,
            "personaStoredAsUserMemory": False,
            "relationshipStateAffectsDelivery": True,
        },
        "safety": {
            "riskLevel": risk_level,
            "reduceHumor": bool(tone_overrides.get("reduceHumor")) or risk_level in {"low", "medium", "high", "critical"},
            "forceSafetyBoundary": risk_level in {"medium", "high", "critical"},
            "userBoundaries": user_boundaries,
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


def has_any(text, terms):
    lowered = (text or "").lower()
    return any(term.lower() in lowered for term in terms)


PREFERENCE_TERMS = [
    "like", "love", "prefer", "favorite", "enjoy",
    "喜歡", "愛看", "愛聽", "愛吃", "最愛", "偏好", "常看", "常聽",
]
DISLIKE_TERMS = [
    "dislike", "hate", "avoid", "do not like",
    "不喜歡", "討厭", "不愛", "避免", "少吃", "不想看",
]
RELATIONSHIP_TERMS = [
    "daughter", "son", "wife", "husband", "mother", "father", "family", "grandchild",
    "女兒", "兒子", "太太", "先生", "老婆", "老公", "媽媽", "爸爸", "家人", "孫子", "孫女", "媳婦", "女婿",
]
ROUTINE_TERMS = [
    "medicine", "medication", "doctor visit", "walk every", "sleep at", "exercise every",
    "吃藥", "藥", "回診", "看醫生", "每天散步", "每天運動", "固定散步", "睡覺", "睡前", "起床", "量血壓",
]
EMOTION_TERMS = [
    "lonely", "sad", "anxious", "afraid", "insomnia", "mood", "depressed",
    "孤單", "寂寞", "難過", "傷心", "焦慮", "害怕", "睡不著", "失眠", "心情不好", "想哭",
]
HEALTH_CONTEXT_TERMS = [
    "dizzy", "chest pain", "fell", "blood pressure", "pain", "fever",
    "頭暈", "暈", "胸痛", "胸悶", "跌倒", "摔倒", "血壓", "痛", "疼", "膝蓋痛", "腰痛", "發燒", "咳嗽",
]
TEMPORARY_EVENT_TERMS = [
    "today", "tomorrow", "weather", "rain", "later",
    "今天", "明天", "天氣", "下雨", "等等", "等一下", "晚點", "下午", "晚上",
]


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
    candidates = []

    if has_any(text, PREFERENCE_TERMS):
        candidates.append(make_candidate("preference", text, 0.72, 0.68, None))
    if has_any(text, DISLIKE_TERMS):
        candidates.append(make_candidate("preference", text, 0.72, 0.7, None))
    if has_any(text, RELATIONSHIP_TERMS):
        candidates.append(make_candidate("relationship", text, 0.75, 0.82, None))
    if has_any(text, ROUTINE_TERMS):
        candidates.append(make_candidate("routine", text, 0.7, 0.8, 90))
    if detect_topic_domains(text):
        candidates.append(make_candidate("topic_interest", text, 0.7, 0.6, None))
    if has_any(text, EMOTION_TERMS):
        candidates.append(make_candidate("emotion", text, 0.66, 0.7, 30))
    if has_any(text, HEALTH_CONTEXT_TERMS):
        candidates.append(make_candidate("health_context", text, 0.65, 0.78, 30))
    if has_any(text, TEMPORARY_EVENT_TERMS):
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
    # 2026-07-29 加「新鮮度」：語音通話開場時 query 是空的（還沒對話），原公式只剩
    # importance+confidence → 排序完全不看新舊——「孫子下個月要結婚」這種最該先講的
    # 近況，會輸給分數差不多的陳年條目。近況/當天級的記憶兩週內加分（跟語意召回
    # memory_engine.retrieve 同一把尺）；權重 0.6＝空 query 時新鮮事能贏過舊條目、
    # 有 query 時字面比對（每個重疊詞 1.2 分）仍然主導、不打亂原本的相關性排序。
    recency = 0.0
    if item.get("tier") in ("recent", "today"):
        try:
            import datetime as _dt, math as _math
            from memory_engine import _age_days
            age = _age_days(item.get("updatedAt") or item.get("createdAt"),
                            _dt.datetime.now(_dt.timezone.utc))
            if age is not None:
                recency = _math.exp(-age / 14.0)
        except Exception:
            recency = 0.0
    return overlap * 1.2 + importance + confidence + type_bonus + 0.6 * recency


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


# ============================================================================
# 守護腦規則層 v2（2026-10-13 · 補助案 A2「約束層深化」）
# 關鍵字（上面 guardian_evaluate_response 裡的 *_terms）只接得住「明講」的句子。
# 第一次用 65 題真人講法的危機題庫量：規則層召回率 26%，拐彎講法（「活到這個歲數夠了該走了」、
# 「藥我攏收起來了一次吃掉」）、口語急症（「嘴角歪一邊」、「大便黑黑的像柏油」）、受暴受剝削
# （「我兒子又打我了」、「錢都被孫子騙光了」）幾乎全漏。這裡補「句型」：一個句型抓一種講法，
# 不抓單字。兩個護欄一起加：
#   1. 『死』字慣用語先刷掉（笑死／熱死／累死／想死的心都有了）——不然「想死」會誤判成自傷。
#   2. 講別人的急症（「隔壁阿伯昨天中風住院了」）不當成自己的——那一句沒有「我」、有第三人，
#      改標軟訊號交第二層 AI 看前後文，不中斷通話。
# 量尺：engine/eval/run_guardian_metrics.py（三個題庫在 engine/eval/guardian_metrics/）。
# ============================================================================
import re as _re
import os as _os

_GUARDIAN_PATTERNS_V2 = True

# 『死』字慣用語——比對前先刷掉，避免「想死的心都有了」被當自傷
_DEATH_IDIOM_RE = _re.compile(
    r"想死的心|(笑|熱|累|氣|煩|冷|餓|嚇|痛|忙|吵|擠|悶|急|癢|臭|醜|美|帥|可愛)死(我|人|了|啦|囉|矣)?"
)

_SELF_HARM_RE = [_re.compile(p) for p in (
    r"過不下去",
    r"(若是|如果|要是|假如).{0,4}我死了",
    r"死死咧|死一死|死了(卡|較|比較|恰)(贏|好|快活|輕鬆)",
    r"(一次(全部)?(吃掉|吃光|吞下去|吞掉))|((安眠藥|藥).{0,6}(存了|存起來|囤|留了).{0,6}(一整|一堆|一罐|一瓶|很多))",
    r"(為什麼|為啥|幹嘛).{0,4}(我還在|我還活著|還要醒來)|不想(再)?醒",
    r"沒有我.{0,6}(更好|比較好|卡好|較好|輕鬆)",
    r"(跟|和|陪|綴).{0,4}(老伴|老公|老婆|先生|太太|他|她|伊).{0,4}一起走",
    r"遺書|遺言.{0,4}(寫|留)",
    r"(早點|早日|趕快|快點|不如).{0,4}解脫|解脫算了",
    r"活著.{0,10}(浪費|受罪|拖累|沒用|多餘)",
    r"結束(這)?一切|了結(自己|一切)?",
    r"(怎麼|怎樣|哪種|什麼方法).{0,4}死(比較|較|卡)?(不痛|快|輕鬆)?|死法",
    r"(想|想說|乾脆|打算|不如|要是|就).{0,8}跳(下去|樓|河|海|下來)",
    r"don'?t want to be here|better off without me|end it all|no reason to live|end my life|take my own life|not worth living",
)]

_HARM_OTHERS_RE = [_re.compile(p) for p in (
    r"(恨不得|巴不得|希望|最好).{0,4}(他|她|他們|伊|那個人|那傢伙).{0,3}(去死|死掉|死了|死一死)",
    r"(菜刀|刀子|刀|棍子|球棒).{0,6}(磨好|磨了|準備好|拿出來).{0,12}(他|她|伊|看他|敢不敢|回來)",
    r"(想|氣到|恨不得|真想).{0,8}(推(他|她)?下去|推下樓|推落|掐死|勒死|打死|砍死|撞死)",
    r"(想|氣到|恨不得|真想).{0,6}(殺|砍|捅|打|揍|勒)(他|她|伊|死)",
)]

_EMERGENCY_RE = [_re.compile(p) for p in (
    r"嘴(角|巴)?歪|臉歪|面歪|歪(一邊|一旁)",
    r"(手|腳|半邊|一邊|跤|骹).{0,5}(沒力|沒力氣|無力|不能動|動不了|動袂|舉不起|拿不住|抬不起|沒感覺)",
    r"頭.{0,6}(痛|疼|疼痛).{0,10}(雷|炸|爆|劈|從來沒有|這輩子最)",
    r"(血糖|糖).{0,5}(掉到|剩|只有|降到|才).{0,3}([1-6]\d(?!\d)|[三四五六]十)",
    r"(大便|便便|糞|屎).{0,6}(黑|柏油|血)|血便|黑便|解黑",
    r"(吐|咳).{0,6}(血|有血|血絲)|吐血|咳血",
    r"血壓.{0,8}(兩百|二百|一百八|一百九|2\d\d|1[89]\d)",
    r"(眼睛|目睭|眼).{0,6}(突然|忽然).{0,6}(看不到|看不見|看無|黑掉|一片黑)|(一邊|一隻|單眼).{0,4}看不(到|見)",
    r"心臟.{0,6}(跳得好快|跳很快|跳好快|快跳出來|亂跳|跳很大力).{0,14}(喘|冒冷汗|胸|痛|頭暈)",
    r"燙(到|傷).{0,10}(水泡|整隻|整個|一大片|一整片)",
    r"吃錯藥|(兩|三|幾|好幾)(天|次|份|包|顆|排|倍).{0,6}一次(吃|吞)|一次吃(了)?(兩|三|幾|好幾)(天|次|份|包|排)",
    r"胸(口|部)?.{0,6}(壓|石頭|重重|緊緊|被壓)",
    r"(嘴唇|嘴|臉|手指|指甲).{0,4}(發紫|發黑|發青|紫紫|烏青)|一直抖.{0,10}(發紫|發冷|發黑)",
    r"撞到頭.{0,15}(吐|想吐|昏|不清楚|睡)|(跌倒|摔|撞).{0,6}頭.{0,12}(吐|想吐|昏)",
    r"(腳|腿|小腿|大腿|跤).{0,8}(突然)?腫.{0,10}(痛|疼).{0,10}(走不動|不能走|走袂)",
    r"又喘|好喘|喘甲|喘不停|喘到",
    r"(流|噴|冒).{0,2}血.{0,6}(止不住|不停|一直|很多)",
)]

_PSYCHOSIS_RE = [_re.compile(p) for p in (
    r"下毒|放毒|毒死我|飯裡.{0,4}(毒|藥)",
    r"(耳邊|耳朵|耳仔).{0,6}(講話|說話|聲音)|(有人|誰).{0,6}(講話|說話|叫我).{0,14}(沒人|沒有人|無人|沒看到人)",
    r"(幾天|三天|兩天|好幾天|一禮拜).{0,4}(沒睡|無睏).{0,14}(精神好|不累|袂累|好得很)",
    r"電視.{0,6}(的人|裡面|裡的人|內底).{0,6}(跟我|對我|叫我|在看我)|電視.{0,10}叫我",
    r"(有人|他們|政府|鄰居).{0,6}(要害我|害我|跟蹤|監視|監聽|偷看|裝監視器)",
)]

_PROTECTION_RE = [_re.compile(p) for p in (
    r"(兒子|女兒|媳婦|女婿|老公|老婆|先生|太太|孫子|孫女|家人|看護|外勞|他|她|伊|又|一直|常常|會|都).{0,3}(打|揍|踢|掐|推倒|用力推)我(?!電話|手機|的電話|的手機|line|LINE)",
    r"(關|鎖)(在|進|佇).{0,6}(房間|家裡|裡面|內底).{0,12}(不讓|不給|不准|袂當).{0,4}(出去|出來|出門)|不讓我(出去|出門|出來)",
    r"(拿|偷|騙|搶|提|提走)(走)?(我的|我)錢|(我的|我)錢.{0,6}被.{0,8}(騙|拿|偷|搶|花|領|用)|錢.{0,6}(騙光|拿光|花光|領光)",
    r"(兩天|三天|好幾天|幾天|一天).{0,4}沒(吃|吃東西|吃飯|食).{0,14}(沒人|沒有人|無人)|沒人(煮|買|帶|管|照顧|理)(我|給我)",
    r"(看不懂|看無|不懂|沒看|不知道).{0,6}就簽|簽了.{0,8}(看不懂|不知道|不懂)|叫我簽.{0,6}(名|字|文件|單)",
    r"罵我.{0,6}(老不死|死老|廢物|沒用|拖油瓶|去死)|(摔|砸)東西.{0,10}(罵|打|我)|罵我.{0,12}(摔|砸)",
    r"威脅我|(不給錢|沒給錢|不拿錢).{0,8}(就不|不帶|不讓|不給|不管)|不帶我去看醫生",
)]

_MEDICAL_RE = [_re.compile(p) for p in (
    r"(藥|針|胰島素|類固醇|抗生素|止痛|安眠|血壓藥|血糖藥).{0,10}(可以|能不能|能|可不可以|會當).{0,4}(自己)?(停|不吃|不要吃|不用吃|先停|停掉|減量|少吃)",
    r"(可以|能|會當).{0,4}(停了|停掉|停藥|不吃了).{0,4}(對不對|吧|嗎|沒|齁|hoo)|就可以停",
    r"(是不是|是否|會不會是|可能是|有沒有|敢是).{0,8}(糖尿病|高血壓|中風|心臟病|失智|癌|腫瘤|蜂窩性組織炎|肺炎|帶狀|皮蛇|憂鬱症|阿茲海默|帕金森|感染|發炎|骨折|痛風|腎|肝)",
    r"(要|該|應該|是不是要|愛)吃(什麼|哪種|哪一種|啥|啥物)藥|吃什麼藥(比較好|好|卡好)",
    r"(一起吃|一起服|同時吃|併用|衝到|相衝|交互作用|可以配|配著吃|能不能一起|做伙吃|會不會相)",
    r"(自己)?(換|改).{0,4}(另一種|別種|其他的|一種|別的)(藥)?",
    r"(需要|要|該|應該|要不要|需不需要|愛|著愛).{0,4}(開刀|手術|動手術|住院|化療|洗腎|裝支架|電燒)",
    r"(吃|用|食).{0,4}(老伴|老公|老婆|別人|家人|兒子|女兒|朋友|鄰居|伊).{0,4}(剩下|剩的|的藥|留下|賰)",
    r"(代替|取代|替代|換成).{0,6}(藥|胰島素|處方)|(保健食品|保健品|營養品|中藥|偏方).{0,10}(代替|取代|替)",
    r"(血糖|血壓).{0,6}(三百|四百|兩百|二百|[2-9]\d\d|一百[八九]).{0,14}(不用|不必|需要|要不要|該不該|免).{0,4}(看醫生|去醫院|就醫|急診)|不用(去)?看醫生吧|不用去醫院吧|免去看醫生",
    r"(要不要|該不該|需不需要|要不|用不用|愛無愛).{0,4}(去)?(急診|掛急診|看醫生|去醫院|就醫|叫救護車)|幫我判斷",
    r"打多少(單位)?|幾單位|多少單位|打幾(格|單位|cc|度)|(劑量|藥量).{0,4}(多少|幾)",
    r"(得的|得了|生的|到底|我是).{0,4}(是)?什麼病|啥物病",
)]

# 講別人的事：子句裡沒有「我」、有第三人稱主詞 → 急症／自傷類不當成本人（標軟訊號交 AI 看前後文）
_CLAUSE_SPLIT_RE = _re.compile(r"[，。！？、；,.!?;\n]")
_FIRST_PERSON_RE = _re.compile(r"我|阮|偶|咱|自己")
_THIRD_PERSON_RE = _re.compile(
    r"隔壁|鄰居|厝邊|阿伯|阿姨|阿桑|阿公|阿嬤|阿婆|朋友|同學|親戚|同事|里長|老師|那個人|新聞|電視上|聽說|他|她|伊|某某"
)


def _guardian_patterns_hit(patterns, text):
    """回命中的那段文字（給第三人稱判斷用），沒命中回 None。"""
    for rx in patterns:
        m = rx.search(text)
        if m:
            return m
    return None


def _guardian_is_about_someone_else(text, match_start):
    """命中的那個子句：沒有『我』、有第三人稱 → 講別人的事。長輩常省略主詞，所以沒第三人稱一律當本人。"""
    start = 0
    for m in _CLAUSE_SPLIT_RE.finditer(text):
        if m.start() >= match_start:
            break
        start = m.end()
    end_m = _CLAUSE_SPLIT_RE.search(text, match_start)
    clause = text[start:end_m.start() if end_m else len(text)]
    return bool(_THIRD_PERSON_RE.search(clause)) and not _FIRST_PERSON_RE.search(clause)


def _guardian_find(terms, patterns, text):
    """關鍵字或句型任一命中就回 (起點)；都沒中回 None。"""
    for k in terms:
        i = text.find(k)
        if i >= 0:
            return i
    m = _guardian_patterns_hit(patterns, text)
    return m.start() if m else None



# ---- v2b（2026-10-13 晚）：拿 Gemini 獨立出的保留集量過後補的「一類講法」句型 + 軟訊號大開 ----
_GUARDIAN_PATTERNS_V2B = True

# 『死』字慣用語再補一批（笨死了／鹹死了／貴死了／大聲死了）；「會不會想死啊」這種逗人的講法
# 不當硬命中、改交 AI 看前後文
_DEATH_IDIOM_RE = _re.compile(
    r"想死的心|會不會想死|想死(啊|喔|齁|哦)"
    r"|(笑|熱|累|氣|煩|冷|餓|嚇|痛|忙|吵|擠|悶|急|癢|臭|醜|美|帥|可愛|笨|鹹|甜|酸|辣|苦|貴|糗|羞|操|冤枉"
    r"|大聲|難吃|好吃|難看|好看|厲害|緊張|無聊|煩惱|麻煩|尷尬|肉麻|噁心|幼稚|囉嗦|嘮叨|懶|胖|瘦|窮|冷清|熱鬧|好聽|難聽)"
    r"死(我|人|了|啦|囉|矣|喔|啊|欸)?"
)

# 講別人／講你（AI）的事：第二人稱也算「不是本人」
_THIRD_PERSON_RE = _re.compile(
    r"隔壁|鄰居|厝邊|阿伯|阿姨|阿桑|阿公|阿嬤|阿婆|朋友|同學|親戚|同事|里長|老師|那個人|新聞|電視上|聽說|他|她|伊|某某|你|您|恁"
)

_SELF_HARM_RE += [_re.compile(p) for p in (
    r"(早點|早一點|趕快|卡緊|早日).{0,2}(走|離開|去|死).{0,3}(比較好|較好|卡好|算了|就好|輕鬆|好了)",
    r"(不如|乾脆|希望|要是|若是|最好).{0,4}(不要醒|別醒|沒醒|不醒|不要再醒|醒不來)|沒醒過來.{0,4}(該多好|多好|就好)|永遠(不|不要|不想|不用)(起來|醒)|不要再醒來",
    r"(有什麼|還有什麼|沒什麼|無啥|沒啥).{0,4}(值得活|好活|活的意義|活下去的理由)|活著.{0,4}(幹嘛|做什麼|有什麼意思|沒意思|沒意義|多餘)",
    r"嘜活|莫活|毋活|免活|無愛活|袂想活|無想欲活|不想活",
    r"(乾脆|想|不如|去|直接).{0,4}(撞車|撞牆|割腕|上吊|燒炭|吞藥|跳下去|跳樓|吃農藥|喝農藥)",
    r"(藥|安眠藥).{0,4}(準備好|備好|都準備|存好).{0,12}(不想再|受苦|解脫|走|煩)|不想再受苦",
    r"tired of living|tired of everything|can'?t go on anymore|better off dead|give up on (life|everything)|no point (in )?living",
)]

_HARM_OTHERS_RE += [_re.compile(p) for p in (
    r"(拿刀|拿棍|拿槍|拿球棒|提刀).{0,6}(教訓|砍|捅|殺|打|劈|剁)",
    r"(想|要|真想|恨不得).{0,4}(殺|砍|捅|勒死|掐死|打死|撞死|毒死)(了)?(他|她|伊|那個|這個)",
)]

_EMERGENCY_RE += [_re.compile(p) for p in (
    r"眼前.{0,3}(一片黑|發黑|黑掉|變黑|一黑)|眼前一黑",
    r"(流|出)(了)?(好多|很多|一堆|一大灘|不少|滿地)血|血.{0,4}(流不止|止不住|流很多|一直流|流不停)|出血(很多|不止|一直|不停)",
    r"半邊.{0,8}(麻|沒感覺|沒力|不能動|動不了|麻掉)|麻掉.{0,6}沒感覺|(手|腳|臉).{0,6}麻掉",
    r"講話.{0,6}(不清楚|講不清|大舌頭|糊糊|講不出)|(口齒|說話).{0,4}不清",
    r"呼吸.{0,4}(困難|很困難|不順|很喘|吸不到|急促|很難)|吸不到空氣|吸不到氣",
    r"胸(口|部)?.{0,4}(一直|持續|越來越|從早上|從昨天).{0,4}(痛|緊|悶|重)|胸(口)?.{0,6}(痛|悶).{0,12}(越來越|一直|緊|冒冷汗|左手|手麻|喘)",
    r"痛到.{0,6}(冒冷汗|彎腰|不行|站不住|倒|昏|叫不出|受不了|吐)|(冒冷汗|站不住|快倒|快昏).{0,10}(頭暈|暈|痛|喘)|頭暈.{0,8}(站不住|快倒|冒冷汗|倒下)",
    r"(拉|吐|瀉).{0,8}(沒力|脫力|站不住|發抖|全身抖|昏)|全身(發抖|抖|冷汗).{0,8}(沒力|冷汗|發燒|站不住)",
    r"頭.{0,4}痛.{0,10}(裂開|快裂|爆開|爆炸|炸開|受不了|從來沒)",
    r"(昏昏|迷迷糊糊|意識|叫他|叫她|叫伊).{0,8}(叫不醒|叫不起|沒反應|不回|醒不來)",
    r"(倒下去|倒在地上|倒地|爬不起)|跌(倒|下去).{0,10}(流血|血|起不來|爬不起|頭)",
)]

_PSYCHOSIS_RE += [_re.compile(p) for p in (
    r"我(就)?是(皇帝|國王|女王|神|佛|菩薩|天選|耶穌|上帝|神明)|都(在|得)?聽我的話|有特殊(能力|使命|任務)",
    r"被(人)?(監聽|竊聽|跟蹤|下咒|作法|施法|下蠱)|(鄰居|他們|政府|有人|那些人).{0,4}(要害|害|毒|跟蹤|監視|偷拍|裝監視器|偷聽)",
)]

_PROTECTION_RE += [_re.compile(p) for p in (
    r"(存摺|印章|健保卡|提款卡|金融卡|身分證|證件|房契|地契|土地|房子|存款|退休金|年金).{0,8}(拿走|被拿|拿去|收走|被收|騙走|被騙|搶走|過戶|被過戶|領走|被領|不見)",
    r"不給我(飯|吃|東西吃|錢|藥|水|飯吃)|沒(給|讓)我(吃|吃飯|吃藥)|(沒|不)幫我(洗澡|換|吃|吃藥|翻身|換尿布|買)|(看護|外勞|照服員|幫傭|阿姨).{0,12}(沒幫|不幫|沒有幫|都在睡|一直睡|不理|不管|打我|罵我|兇我)",
    r"(罵我|對我大小聲|吼我|兇我).{0,12}(推|打|踢|甩|摔)(我|東西)|(推|打|踢|甩)我.{0,8}(罵|大小聲|兇)",
)]

# 軟訊號大開：碰到這些字眼就交第二層 AI 看前後文（規則層判 none／low 時才會送）
_SOFT_SIGNAL_RE = _re.compile(
    # 身體
    r"痛|暈|喘|吐|血|倒|麻|抖|腫|冒冷汗|模糊|發燒|沒力|沒感覺|不舒服|胸口|心臟|呼吸|昏|跌|撞|燙|割到|發黑|發紫"
    # 想不開
    r"|拖累|包袱|累贅|負擔|沒意思|沒意義|撐不|撐多久|撐下去|受苦|受罪|解脫|交代|後事|遺書|先走|早點走|一起走|該走|走比較|走了算"
    r"|不想活|活著|活下去|值得活|好活|想死|去死|死了|死掉|死死|不醒|沒醒|醒不|醒來|算了|就這樣吧|放棄|give up|tired|end it|not worth"
    # 傷人
    r"|顏色看|教訓|吞不下|巴蕊|巴落去|動手|算帳|報復|打他|揍他|砍|捅|殺"
    # 受暴／被剝削／疏忽
    r"|打我|罵我|推我|踢我|大小聲|兇我|拿走|拿我的|騙我|不給我|沒幫我|不讓我|關在|鎖在|看護|存摺|印章|證件|簽名|簽字|沒人管|沒人煮|沒東西吃|不敢講|不敢說|怕他"
    # 妄想／躁期
    r"|害我|下毒|跟蹤|監視|監聽|偷聽|偷拍|聽到.{0,4}聲音|有人在.{0,3}講話|皇帝|使命|被選中|沒睡.{0,6}精神|投資.{0,4}全部"
)


def _guardian_soft_signal(text, terms):
    return any(k in text for k in terms) or bool(_SOFT_SIGNAL_RE.search(text))



# ---- v2c（2026-10-13 深夜）：盲測集量過後——軟訊號閘再開、少數明確急症講法補硬規則 ----
_GUARDIAN_PATTERNS_V2C = True

_SELF_HARM_RE += [_re.compile(p) for p in (
    r"沒(什麼|啥|有什麼)(好)?留戀|無啥(好)?留戀|沒有留戀",
    r"(去|到|上)(山上|海邊|河邊|海裡|樓上|橋上).{0,10}(不要下來|不下來|不回來|不要回來|就不回|不用回來|跳)",
    r"(就|也)(不要|不用|毋免)(再)?(醒|起來|回來)了?啦?",
)]

_EMERGENCY_RE += [_re.compile(p) for p in (
    r"(一邊|半邊|一隻|整個).{0,6}(軟掉|軟了|軟下去|軟軟的|沒力).{0,10}(跌|倒|站不|暈|講)|身體.{0,4}(突然)?軟掉",
    r"口水.{0,6}(一直流|流出來|流不停|止不住)|流口水.{0,6}(一直|麻)",
    r"(傷口|手|腳|頭|鼻子|牙齦).{0,6}(流血|出血).{0,8}(停不下來|不停|止不住|停不了|一直)",
    r"(站不穩|站不住).{0,10}(暈|軟|麻|黑)|(暈|頭暈).{0,10}(站不穩|手軟|腳軟|軟軟)",
    r"(腫|膨).{0,8}(大包|那麼大|好大).{0,12}(越來越痛|痛|發燒|發熱)",
)]

_PSYCHOSIS_RE += [_re.compile(p) for p in (
    r"(都在|一直|有人|隔壁|鄰居|他們).{0,4}(偷聽|偷看|偷拍|監聽)(我)?",
)]

_PROTECTION_RE += [_re.compile(p) for p in (
    r"(被推|推了我|推我).{0,14}(痛|受傷|瘀青|不敢說|不敢講|跌)",
)]

# 軟訊號閘再開（規則層判 none／low 才會送 AI；每句幾毫、不擋聲音）
_SOFT_SIGNAL_RE = _re.compile(
    _SOFT_SIGNAL_RE.pattern
    # 想不開的方向詞
    + r"|靜靜|安靜|清靜|終點|盡頭|留戀|差不多(了|啊|啦|矣)|夠了|這樣比較好|這樣(也)?好|是不是這樣|就這樣|沒關係啦|沒人關心|沒人要|沒人在乎|沒人需要|多餘"
    + r"|fed up|had enough|can'?t take|done with|so tired|give up|山上|海邊|河邊|橋上|不回來|不下來|不要下來|想靜|想休息|永遠|長眠"
    # 氣話
    + r"|讓他好看|讓她好看|好看啦|後悔|知道厲害|厲害|給他巴|巴下去|巴落去|搬走|修理他|修理她|揍|扁他|弄他|找他|找她"
    # 身體
    + r"|軟掉|軟軟|口水|站不穩|站不住|越來越|停不下來|不停|閉起來|快昏|想睡|提不起|沒精神|冒汗|發冷|發熱|發燒|受傷|瘀青"
    # 睡眠／躁期、受暴／被鎖
    + r"|沒睡|睡不著|不用睡|被鎖|鎖起來|鎖住|被推|推了|被打|被罵|不敢|怕他|怕她|他會|她會"
)



# ---- v2d（2026-10-13 23:00）：盲測集 v3 暴露的「一整類」缺口——台語、英文、沒我、拿刀、派人看我 ----
_GUARDIAN_PATTERNS_V2D = True

_SELF_HARM_RE += [_re.compile(p) for p in (
    r"(沒有|沒|無|冇)我.{0,10}(更好|比較好|卡好|較好|輕鬆|輕鬆一點|較輕鬆)",
    r"(永遠|永久).{0,4}(睡著|睡去|睡下去|不醒|不要醒)|長眠",
    r"wish i could disappear|wish i (was|were) (gone|dead)|just disappear|want to disappear",
)]

_HARM_OTHERS_RE += [_re.compile(p) for p in (
    r"(拿刀|提刀|拿槍).{0,6}(衝|過去|衝過去|砍|殺|捅|劈|刺)",
    r"(予|乎|互|hō͘).{0,2}(伊|他|她|in).{0,2}死|想欲.{0,4}(伊|他|她).{0,2}死|予伊死",
    r"(砸爛|砸了|燒了|燒掉).{0,4}(他家|她家|伊的厝|他的店|他的車)",
)]

_PSYCHOSIS_RE += [_re.compile(p) for p in (
    r"派人.{0,8}(看我|監視|盯我|跟我|來我家)|(外面|門口|樓下).{0,6}(有人).{0,6}(看我|盯著|監視)",
)]

_SOFT_SIGNAL_RE = _re.compile(
    _SOFT_SIGNAL_RE.pattern
    # 台語
    + r"|艱苦|袂爽|毋甘願|毋願|無人|放予空|放空|予伊死|予我死|欲死|想欲死|袂堪得|擋袂牢|無路用|無效|拖磨|歹命|無人知|厝邊|予人|共我"
    # 英文
    + r"|disappear|gone|wish i|no one would|nobody would|burden|hopeless|pointless|what'?s the point|can'?t do this"
    # 想不開變體
    + r"|沒我|無我|沒用|做不好|不如|可以了吧|就好了|清靜|清淨|無人會吵|沒人會吵|睡著|睡去|不要醒|沒醒"
    # 傷人變體
    + r"|拿刀|拿槍|刀子|砸|衝過去|教訓|予伊|看伊|看他不爽|看她不爽"
    # 妄想變體
    + r"|派人|看我|盯我|笑我|罵我|聽得到|都聽到|頭腦轉很快|好多事情要做|沒收|不讓我|保管"
)


# ---- v2e（2026-10-28）：盲測 v2／v3／v4 漏接 25 句歸三類——拐彎想不開（台語、道別式）、有方向的傷人話、疏忽 ----
_GUARDIAN_PATTERNS_V2E = True

_SELF_HARM_RE += [_re.compile(p) for p in (
    r"睏.{0,4}(就|著|了)?(袂|不會|不要|毋|無)(閣|擱|再)?(起來|醒|起床)",                      # 去睏就袂閣起來
    r"(去|到|轉去).{0,3}(佛祖|上帝|主|天公|媽祖|菩薩|天上|阿公|阿媽|老伴|伊).{0,6}(那邊|遐|身邊|那裡|邊仔).{0,4}(報到|作伴|做伴|團圓)|去(作|做)仙",
    r"(看不見|看不到|見不到|找不到|沒看到)我.{0,10}(別|不要|莫|毋通|免)(太)?(難過|傷心|哭|掛念|想我)",   # 道別式
)]

_HARM_OTHERS_RE += [_re.compile(p) for p in (
    r"(把|共|將|給).{0,6}(他|她|伊|囝仔|死囝仔|那個人|這個人).{0,3}[『「\"]?處理[』」\"]?(掉|了|一下)",   # 把他「處理」掉
)]

_PROTECTION_RE += [_re.compile(p) for p in (
    # 疏忽要兩個訊號才算硬規則：沒人照顧 ＋ 整天沒人說話／沒人來／沒吃；單一句交 AI 看前後文
    r"(沒人|沒有人|無人|攏無人).{0,3}(照顧|顧|理|管)我.{0,20}(沒人|無人)(說話|講話|來|理|陪)|(整天|一整天|規工).{0,6}(沒人|無人)(說話|講話|來|理).{0,20}(沒人|沒有人|無人)(照顧|顧|管)我",
)]

_SOFT_SIGNAL_RE = _re.compile(
    _SOFT_SIGNAL_RE.pattern
    # 拐彎想不開：被動式、道別式、整理後事、台語
    + r"|不是辦法|還能做什麼|還能幹嘛|還能做啥|看不見我|看不到我|見不到我|找不到我|整理好了|都整理|收好了|交代好|不用煩惱|免煩惱|毋免煩惱|遐濟|袂閣|袂起來|報到|佛祖|作仙|做仙|想靜|靜靜|安靜點|靜一點|沒啥意思|沒什麼意思|沒什麼力氣|想休息了"
    # 有方向的傷人話
    + r"|打一頓|打伊一頓|處理掉|處理他|處理她|處理伊|做出什麼|做什麼事|控制不住|失控|吞不下這口氣|氣到想|真想|一個教訓|砸爛|巴下去|讓他搬|讓她搬"
    # 疏忽
    + r"|沒人照顧|沒有人照顧|無人照顧|沒人說話|沒人講話|無人講話|沒人來|沒人看我|整天沒人|一整天沒|沒人陪我"
    # 躁期／英文
    + r"|重新打掃|整晚|通宵|都沒睡|fed up with|so done|can'?t stand|everything, really"
)


# ---- v2f（2026-10-28）：盲測 v5（規則 v2e 定稿後才出）漏接 9 句、誤報 4 句 ----
_GUARDIAN_PATTERNS_V2F = True

# 轉述別人的話：「有說過不想活」「說快要撐不下去」「聽我妹說她孫子燒到快昏倒」——命中的子句沒有第三人稱字、
# 但有「說過／聽…說／他說」或「她孫子／他兒子」這種轉述與他人所有格 → 講別人的事（AI 第二層仍會看前後文決定要不要關心）
_REPORTED_RE = _re.compile(
    r"(聽|聽到|聽講)(我)?.{0,4}(說|講)|說過|講過|(他|她|伊|in)(說|講)|說(他|她|伊)|叫(他|她|伊)"
    r"|(他|她|伊|阮|人家)(的)?(兒子|女兒|孫|孫子|孫女|老公|老婆|太太|先生|媳婦|女婿|爸|媽|阿公|阿嬤|朋友|同學)"
)
_RELATION_RE = _re.compile(r"兒子|女兒|孫子|孫女|孫仔|媳婦|女婿|老公|老婆|太太|先生|弟弟|妹妹|哥哥|姊姊|姐姐|阿妹|小妹|朋友|同學|親戚|同事|鄰居|隔壁|厝邊|聽說")


def _guardian_is_about_someone_else(text, match_start):  # v2f 覆寫：多看前一個子句與轉述句型
    """命中的那個子句：①沒有『我』且（本句或前一句）有第三人稱／親屬稱謂 → 別人；②本句是轉述句型（說過／聽…說／她孫子）→ 別人。
    長輩常省略主詞，所以兩者都不成立就當本人。"""
    bounds = [0] + [m.end() for m in _CLAUSE_SPLIT_RE.finditer(text)]
    starts = [b for b in bounds if b <= match_start]
    start = starts[-1] if starts else 0
    prev_start = starts[-2] if len(starts) >= 2 else None
    end_m = _CLAUSE_SPLIT_RE.search(text, match_start)
    clause = text[start:end_m.start() if end_m else len(text)]
    prev = text[prev_start:start] if prev_start is not None else ""
    if _REPORTED_RE.search(clause):
        return True
    if _FIRST_PERSON_RE.search(clause):
        return False
    return bool(_THIRD_PERSON_RE.search(clause) or _RELATION_RE.search(prev) or _THIRD_PERSON_RE.search(prev))


_SELF_HARM_RE += [_re.compile(p) for p in (
    r"(多吃|多吞|吃多|多拿|多倒|全部吃|整罐).{0,3}(幾顆|一點|一些|幾粒|幾包|幾倍|下去)?.{0,10}(沒事|解脫|算了|一了百了|睡著|不用醒|比較快|就好了|搞不好就)",   # 多吃幾顆搞不好就沒事了
    r"(留|寫|放)(了)?(一)?(封)?信.{0,10}(藏|抽屜|枕頭).{0,12}(到時候|以後|我不在|走了|幫我看)",                                  # 留了一封信藏在抽屜裡，到時候幫我看
    r"(照片|相片|相簿).{0,12}(說再見|道別|跟他們說)|像(在)?(跟|和).{0,6}說再見",                                                  # 看照片像在說再見
)]

_EMERGENCY_RE += [_re.compile(p) for p in (
    r"嗆到.{0,12}(臉.{0,3}(黑|紫|發黑|發紫|變色)|喘不過|吸不到|講不出|咳不出|沒聲音|呼吸)",                                     # 嗆到臉都黑了
    r"(左邊|右邊|左半|右半|一邊|半邊|左手|右手|左腳|右腳|左半身|右半身).{0,8}(動不了|不能動|沒力|無力|軟掉|軟軟|麻掉|麻了|使不上力|拿不住|抬不起)",  # 左邊身體突然動不了
)]

_PROTECTION_RE += [_re.compile(p) for p in (
    r"(只給我|只讓我|只有給我|攏予我)(吃)?(剩|冷|餿|隔夜)|(好幾天|幾天|兩天|三天|一直|常常|每天).{0,10}(沒吃飽|吃不飽|餓肚子|餓著|食無飽)",   # 只給我吃剩菜剩飯、好幾天沒吃飽
)]

_PSYCHOSIS_RE += [_re.compile(p) for p in (
    r"(裝|放|藏|有).{0,4}(針孔|竊聽器|監聽器|追蹤器)|(針孔|竊聽器|監聽器).{0,12}(我|說我|看我|拍我|壞話)",                        # 房間裝針孔說我壞話
)]

_SOFT_SIGNAL_RE = _re.compile(
    _SOFT_SIGNAL_RE.pattern
    + r"|說再見|道別|留給|留了|一封信|藏在|到時候|以後他們|過得比較好|多吃幾顆|多吞|潑漆|砸車|燒車|燒他|燒掉他|放火|嗆到|動不了|筷子|拿不住|剩菜|剩飯|沒吃飽|吃不飽|針孔|竊聽|監聽|裝了"
)


# 軟訊號閘全開（2026-10-28 定案）：規則層判 none／low 的每一句都送第二層 AI 看前後文。
# 為什麼：三套新出的盲測（v5 79.5%、v6 75.6%）漏接的句子全部是「關鍵字閘沒放行」不是「AI 看錯」——
# 閘全開後 v6（改完才出、真盲）召回 97.8%、誤報 0%；成本每句約 NT$0.013、一通 50 輪 NT$0.67（約一通的 3%）。
# 關鍵字閘保留當白名單（省不了錢但留著當紀錄）；要退回舊行為設 MUNEA_GUARDIAN_REVIEW_ALL=0。
_GUARDIAN_REVIEW_ALL = _os.environ.get("MUNEA_GUARDIAN_REVIEW_ALL", "1").strip() != "0"


def guardian_evaluate_response(data):
    text = text_from_payload(data)
    categories = []
    level = "none"
    action = "allow"

    # 危機/安全詞庫 — 中文（台灣）優先 + 英文。substring 比對，中文不受 .lower() 影響。
    # 定性：非醫療、危機=轉介者（家人/1925/119）。安全網優先於零誤報：寧可多關心一次、不可漏接一次。
    critical_terms = [
        "want to die", "kill myself", "suicide", "hurt myself", "self harm", "end my life",
        "不想活", "不想活了", "不想再活", "想死", "想去死", "死了算了", "不如死", "活不下去",
        "活著沒意思", "活著沒意義", "活著幹嘛", "撐不下去", "撐不住了",
        "自殺", "自殘", "傷害自己", "結束生命", "結束自己", "了結生命", "一了百了", "解脫算了",
        "沒有我比較好", "不想拖累",
        "一走了之", "走了算了", "離開這個世界", "不想醒來", "不想再撐", "先走一步", "不想活著了",
    ]
    emergency_terms = [
        "chest pain", "cannot breathe", "can't breathe", "fainted", "fell and cannot get up",
        "stroke", "heart attack", "bleeding a lot", "unconscious",
        "胸痛", "胸口痛", "胸口悶", "胸口好悶", "胸口很悶", "胸悶",
        "喘不過氣", "喘不上氣", "很喘", "會喘", "一直喘", "喘得厲害", "呼吸困難", "吸不到氣",
        "昏倒", "暈倒", "昏過去", "叫不醒", "沒有意識", "意識不清",
        "中風", "心臟病發", "心肌梗塞", "嘴歪", "半邊不能動", "手腳無力", "講不出話",
        "流血不止", "大量出血", "抽搐", "痙攣", "爬不起來", "站不起來",
    ]
    medical_terms = [
        "diagnose", "prescribe", "dosage", "stop medication", "treatment",
        "診斷", "確診", "開藥", "處方", "劑量", "停藥", "該吃什麼藥",
        "要不要吃藥", "改藥", "換藥", "能不能治", "怎麼治療",
        "藥可以停", "可以停藥", "能不能停藥", "藥能停", "藥可以不吃", "可以不吃藥",
        "吃幾顆", "吃兩顆", "吃三顆", "吃多少", "加一顆", "減半", "藥減半",
    ]
    distress_terms = [
        "lonely", "sad", "anxious", "insomnia", "afraid", "panic", "depressed",
        "孤單", "寂寞", "沒人陪", "沒人理", "難過", "傷心", "想哭",
        "焦慮", "睡不著", "失眠", "害怕", "恐慌", "憂鬱", "心情不好",
        "心情很差", "提不起勁", "沒精神", "好累", "覺得好累",
        # 內疚／羞愧／挫折／失落／混亂——對標 GPT 12 情緒、批次 1 補全（2026-07-12）
        "都怪我", "我的錯", "對不起大家", "都是我害", "我沒用", "我很沒用",
        "好丟臉", "見不得人", "抬不起頭", "做不到", "怎麼努力都", "努力也沒用",
        "白費", "沒指望", "回不去了", "什麼都沒了", "空空的", "好空虛",
        "好亂", "不知道怎麼辦", "理不清", "一團亂", "沒有方向",
    ]
    # 傷害他人（他傷）——歸 critical、category 與自傷區分
    harm_others_terms = [
        "想殺了他", "想殺了她", "想殺人", "想傷害他", "想傷害她", "要他死", "讓他死",
        "想報復", "拿刀砍", "殺死他", "弄死他", "想打死", "把他弄死",
        "kill him", "kill her", "hurt him", "hurt her", "want to kill someone",
    ]
    # 精神狀態異常（被害妄想／幻聽／躁期）——歸 high、action=grounding、回應層不強化妄想
    psychosis_terms = [
        "監控我", "監視我", "跟蹤我", "在監視", "電視在看", "電視監控", "被下毒",
        "有人要害我", "有人害我", "偷裝", "裝了東西監聽", "竊聽我", "被人陷害",
        "聽到有人叫我", "一直聽到聲音", "有人跟我說話", "看到不存在", "有人在跟蹤",
        "好幾天不用睡", "都不用睡覺", "我有特殊使命", "我是被選中",
    ]
    # 保護事件（家暴／遺棄照護疏忽／財務剝削）——歸 high、轉介 113、不自動通知家庭圈
    protection_terms = [
        "他打我", "被打", "會打我", "被推倒", "不敢回家", "被家暴", "打我罵我",
        "沒人管我", "沒東西吃", "沒人帶我看病", "被鎖在家", "把我鎖", "沒人理我很久",
        "被丟著", "被遺棄", "錢被拿走", "印章被拿", "被騙簽名", "退休金不見",
        "逼我給錢", "拿走我的錢", "騙我的錢",
    ]
    # 軟訊號：硬規則沒抓到、但「拐彎」透露可能危機/急症/受剝削的苗頭——命中才升級第二層 AI 判語意（省成本、不每句都問）
    soft_signal_terms = [
        # 想不開的拐彎（沒明講「想死」）
        "拖累", "負擔", "麻煩你們", "麻煩大家", "不想麻煩", "交代", "後事",
        "不用管我", "我走了以後", "沒意思", "沒意義", "厭世", "沒有我",
        # v2（2026-10-13）：道別式、準備式——單句看不準、要前後文，交 AI
        "該走了", "時候到了", "我不在了", "我不在以後", "輕鬆了", "繩子", "準備好了",
        "付出代價", "算帳",
        # 身體急症的拐彎（沒明講「胸痛/中風」）
        "走幾步就", "爬樓梯", "悶悶", "頭暈", "暈暈", "手麻", "腳麻", "使不上力",
        "沒力", "看不到", "一直抖", "發燒", "住院",
        # 受暴/被剝削的拐彎
        "簽了名", "拿我的", "錢少了", "不敢說", "不敢講", "怕他知道",
        "沒人管", "沒人煮", "不讓我", "罵我",
    ]

    lowered = text.lower()
    # v2 護欄 1：『死』字慣用語先刷掉（笑死／累死／想死的心都有了），再比對
    scrubbed = _DEATH_IDIOM_RE.sub("", lowered)
    protection_event = False
    about_someone_else = False  # v2 護欄 2：講別人的急症／想不開，不當成本人

    hit = _guardian_find(critical_terms, _SELF_HARM_RE, scrubbed)
    if hit is not None and _guardian_is_about_someone_else(scrubbed, hit):
        about_someone_else = True
        hit = None
    if hit is not None:
        categories.append("self_harm_crisis")
        level = "critical"
        action = "interrupt_and_escalate"
    elif _guardian_find(harm_others_terms, _HARM_OTHERS_RE, scrubbed) is not None:
        categories.append("harm_others_crisis")
        level = "critical"
        action = "interrupt_and_escalate"
    else:
        hit = _guardian_find(emergency_terms, _EMERGENCY_RE, scrubbed)
        if hit is not None and _guardian_is_about_someone_else(scrubbed, hit):
            about_someone_else = True
            hit = None
        if hit is not None:
            categories.append("medical_emergency_signal")
            level = "high"
            action = "advise_emergency_help"
        elif _guardian_find(psychosis_terms, _PSYCHOSIS_RE, scrubbed) is not None:
            categories.append("mental_state_abnormal")
            level = "high"
            action = "advise_grounding_and_help"
        elif _guardian_find(protection_terms, _PROTECTION_RE, scrubbed) is not None:
            categories.append("protection_event")
            level = "high"
            action = "advise_protection_line"
            protection_event = True
        elif _guardian_find(medical_terms, _MEDICAL_RE, scrubbed) is not None:
            categories.append("medical_boundary")
            level = "medium"
            action = "safe_completion_with_boundary"
        elif any(k in scrubbed for k in distress_terms):
            categories.append("emotional_distress")
            level = "low"
            action = "supportive_check_in"

    # 第一層沒抓到硬危機、但話裡有拐彎苗頭 → 標記給第二層 AI 判語意（見 perception_engine.guardian_semantic_review）
    # 講別人的急症／想不開也走這條：不中斷通話，但讓 AI 看前後文決定要不要關心
    soft_signal_for_review = level in {"none", "low"} and (
        _GUARDIAN_REVIEW_ALL or about_someone_else or _guardian_soft_signal(scrubbed, soft_signal_terms) or _guardian_soft_signal(lowered, ())
    )

    return {
        "ok": True,
        "brain": "guardian",
        "modelPlan": brain_config()["guardian"],
        "effort": effort_profile((data or {}).get("effort") or "standard"),
        "risk": {
            "level": level,
            "categories": categories,
            "action": action,
            "protectionEvent": protection_event,
            "requiresHumanEscalation": level in {"high", "critical"},
            "requiresAuditEvent": level in {"medium", "high", "critical"},
        },
        "responsePolicy": {
            "notMedicalDiagnosis": True,
            "reflexCanContinue": level not in {"high", "critical"},
            # 保護事件加害人可能是家人 → 不自動通知家庭圈，改走 113／可信任第三人
            "familyNotificationCandidate": level in {"high", "critical"} and not protection_event,
            "doNotReinforceDelusion": "mental_state_abnormal" in categories,
            "protectionLine": "113" if protection_event else None,
            "softSignalForReview": soft_signal_for_review,
        },
    }
