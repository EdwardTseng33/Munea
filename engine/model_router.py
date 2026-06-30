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


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def request_id():
    return "brain_" + uuid.uuid4().hex[:12]


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

    if any(k in text for k in ["喜歡", "愛看", "愛吃", "偏好"]) or "like" in lowered:
        candidates.append(make_candidate("preference", text, 0.72, 0.68, None))
    if any(k in text for k in ["不喜歡", "討厭", "不想要"]) or "dislike" in lowered:
        candidates.append(make_candidate("preference", text, 0.72, 0.7, None))
    if any(k in text for k in ["女兒", "兒子", "太太", "先生", "媽媽", "爸爸", "家人", "孫"]) or any(k in lowered for k in ["daughter", "son", "wife", "husband", "family"]):
        candidates.append(make_candidate("relationship", text, 0.75, 0.82, None))
    if any(k in text for k in ["吃藥", "服藥", "回診", "散步", "睡覺", "起床", "運動"]):
        candidates.append(make_candidate("routine", text, 0.7, 0.8, 90))
    if any(k in text for k in ["電影", "音樂", "新聞", "旅行", "股票", "烹飪", "書"]):
        candidates.append(make_candidate("topic_interest", text, 0.7, 0.6, None))
    if any(k in text for k in ["孤單", "難過", "焦慮", "害怕", "失眠", "心情"]):
        candidates.append(make_candidate("emotion", text, 0.66, 0.7, 30))
    if any(k in text for k in ["頭暈", "胸痛", "跌倒", "血壓", "疼痛", "發燒"]):
        candidates.append(make_candidate("health_context", text, 0.65, 0.78, 30))
    if any(k in text for k in ["今天", "明天", "下雨", "天氣", "等一下"]):
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
        "candidates": candidates,
        "storagePolicy": {
            "storeRawTranscriptByDefault": False,
            "requiresConsentForSensitive": True,
            "supportsUpdateAndSupersede": True,
        },
    }


def normalize_memory_item(candidate, person_id="local-person-self"):
    item = {
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
    }
    return item


def tokenize(text):
    return {t for t in re.split(r"[\s,.;:!?，。！？、]+", (text or "").lower()) if t}


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

    critical_terms = ["想死", "自殺", "不想活", "傷害自己", "kill myself", "suicide"]
    emergency_terms = ["胸痛", "喘不過氣", "昏倒", "跌倒起不來", "stroke", "heart attack"]
    medical_terms = ["診斷", "處方", "藥量", "停藥", "治療", "diagnose", "prescribe"]
    distress_terms = ["孤單", "難過", "焦慮", "失眠", "害怕", "panic", "depressed"]

    lowered = text.lower()
    if any(k in text or k in lowered for k in critical_terms):
        categories.append("self_harm_crisis")
        level = "critical"
        action = "interrupt_and_escalate"
    elif any(k in text or k in lowered for k in emergency_terms):
        categories.append("medical_emergency_signal")
        level = "high"
        action = "advise_emergency_help"
    elif any(k in text or k in lowered for k in medical_terms):
        categories.append("medical_boundary")
        level = "medium"
        action = "safe_completion_with_boundary"
    elif any(k in text or k in lowered for k in distress_terms):
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
