#!/usr/bin/env python3
"""
沐寧 Munea · 本機 App 伺服器 — 跑真的 App（web/）＋ 接真的角色腦。
  GET  /                     → web/index.html（完整 App）
  GET  /<path>               → web/ 底下的靜態檔（js / css / 圖）
  POST /open  {char}         → 該角色「主動先開口」＋語音
  POST /chat  {history,char} → 該角色帶記憶回話＋語音
  POST /voice-session        → 回傳目前語音 provider 能力；之後接即時語音 session
  POST /companion-profile    → 讀寫陪伴角色 templateId/displayName
用法：GEMINI_API_KEY="..." py server.py  → 瀏覽器開 http://localhost:8200
"""
import os, sys, json, base64, io, wave, time, posixpath
from http.server import BaseHTTPRequestHandler, HTTPServer
import chat_engine as eng
from google.genai import types

if not os.environ.get("GEMINI_API_KEY"):
    sys.exit("需要 GEMINI_API_KEY")

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.normpath(os.path.join(HERE, "..", "web"))
DEFAULT_CHAR = "寧寧"
COMPANION_PROFILE_PATH = os.path.join(HERE, "companion_profile.json")
APP_PROFILE_STORE_PATH = os.path.join(HERE, "app_profile_store.json")
BILLING_STORE_PATH = os.path.join(HERE, "billing_store.json")
PRIMARY_CARE_RECIPIENT_ID = "local-person-self"
MAX_JSON_BODY_BYTES = 1_000_000
MAX_AUDIO_NOTE_BYTES = 12_000_000
ALLOWED_AUDIO_MIMES = {"audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}
COMPANION_TEMPLATES = {
    "nening-real-female": {"defaultName": "寧寧", "backendChar": "寧寧"},
    "companion-real-male": {"defaultName": "阿宏", "backendChar": "阿宏"},
    "munea-2d-xiaoyun": {"defaultName": "小昀", "backendChar": "小昀"},
    "munea-2d-ayuan": {"defaultName": "阿原", "backendChar": "阿原"},
    "munea-2d-mimi": {"defaultName": "咪咪", "backendChar": "咪咪"},
    "munea-2d-wangcai": {"defaultName": "旺財", "backendChar": "旺財"},
}
COMPANION_ALIASES = {
    "real-f": "nening-real-female",
    "real-m": "companion-real-male",
    "toon-f": "munea-2d-xiaoyun",
    "toon-m": "munea-2d-ayuan",
    "cat": "munea-2d-mimi",
    "dog": "munea-2d-wangcai",
}


def normalize_template_id(template_id):
    template_id = COMPANION_ALIASES.get(template_id, template_id)
    return template_id if template_id in COMPANION_TEMPLATES else "nening-real-female"


def normalize_companion_profile(data=None):
    data = data or {}
    template_id = normalize_template_id(data.get("templateId") or data.get("template_id"))
    default_name = COMPANION_TEMPLATES[template_id]["defaultName"]
    display_name = (data.get("displayName") or data.get("display_name") or default_name).strip()[:12] or default_name
    return {
        "templateId": template_id,
        "displayName": display_name,
        "nameTouched": bool(data.get("nameTouched") or data.get("name_touched")),
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def request_id():
    return "req_" + str(int(time.time() * 1000))


def read_json_file(path, fallback=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def write_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_legacy_companion_profile():
    return normalize_companion_profile(read_json_file(COMPANION_PROFILE_PATH, {}))


def default_app_profile_store(companion_profile=None):
    companion_profile = normalize_companion_profile(companion_profile)
    return {
        "schemaVersion": 1,
        "account": {
            "id": "local-demo-account",
            "locale": "zh-TW",
            "preferredLanguages": ["zh-TW", "en"],
            "createdAt": "2026-06-29T00:00:00Z",
        },
        "familyGroup": {
            "id": "local-demo-family",
            "name": "Munea Care Circle",
            "members": [
                {
                    "id": PRIMARY_CARE_RECIPIENT_ID,
                    "role": "primary_user",
                    "displayName": "Primary user",
                    "relationship": "self",
                },
                {
                    "id": "local-family-contact",
                    "role": "family_contact",
                    "displayName": "Family contact",
                    "relationship": "family",
                },
            ],
        },
        "primaryCareRecipientId": PRIMARY_CARE_RECIPIENT_ID,
        "companionProfiles": {
            PRIMARY_CARE_RECIPIENT_ID: companion_profile,
        },
        "updatedAt": companion_profile.get("updatedAt") or utc_now(),
    }


def normalize_family_member(member):
    member = member or {}
    member_id = str(member.get("id") or PRIMARY_CARE_RECIPIENT_ID)
    return {
        "id": member_id,
        "role": str(member.get("role") or ("primary_user" if member_id == PRIMARY_CARE_RECIPIENT_ID else "family_contact")),
        "displayName": str(member.get("displayName") or member.get("display_name") or "Member").strip()[:40] or "Member",
        "relationship": str(member.get("relationship") or "family"),
    }


def normalize_app_profile_store(data=None):
    data = data or {}
    primary_id = str(data.get("primaryCareRecipientId") or data.get("primary_care_recipient_id") or PRIMARY_CARE_RECIPIENT_ID)
    raw_profiles = data.get("companionProfiles") or data.get("companion_profiles") or {}
    if data.get("companionProfile") and primary_id not in raw_profiles:
        raw_profiles = {**raw_profiles, primary_id: data.get("companionProfile")}
    companion_profiles = {
        str(person_id): normalize_companion_profile(profile)
        for person_id, profile in raw_profiles.items()
    }
    companion_profiles.setdefault(primary_id, load_legacy_companion_profile())

    family_group = data.get("familyGroup") or data.get("family_group") or {}
    members = [normalize_family_member(m) for m in family_group.get("members", [])]
    if not any(m["id"] == primary_id for m in members):
        members.insert(0, normalize_family_member({
            "id": primary_id,
            "role": "primary_user",
            "displayName": "Primary user",
            "relationship": "self",
        }))

    account = data.get("account") or {}
    return {
        "schemaVersion": int(data.get("schemaVersion") or data.get("schema_version") or 1),
        "account": {
            "id": str(account.get("id") or "local-demo-account"),
            "locale": str(account.get("locale") or "zh-TW"),
            "preferredLanguages": account.get("preferredLanguages") or account.get("preferred_languages") or ["zh-TW", "en"],
            "createdAt": account.get("createdAt") or account.get("created_at") or "2026-06-29T00:00:00Z",
        },
        "familyGroup": {
            "id": str(family_group.get("id") or "local-demo-family"),
            "name": str(family_group.get("name") or "Munea Care Circle"),
            "members": members,
        },
        "primaryCareRecipientId": primary_id,
        "companionProfiles": companion_profiles,
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or utc_now(),
    }


def load_app_profile_store():
    raw = read_json_file(APP_PROFILE_STORE_PATH)
    if raw is None:
        return default_app_profile_store(load_legacy_companion_profile())
    return normalize_app_profile_store(raw)


def save_app_profile_store(data):
    store = normalize_app_profile_store({**data, "updatedAt": utc_now()})
    write_json_file(APP_PROFILE_STORE_PATH, store)
    return store


def active_companion_profile(store=None):
    store = store or load_app_profile_store()
    primary_id = store["primaryCareRecipientId"]
    return normalize_companion_profile(store["companionProfiles"].get(primary_id))


def load_companion_profile():
    return active_companion_profile(load_app_profile_store())


def save_companion_profile(data):
    profile = normalize_companion_profile({**data, "updatedAt": utc_now()})
    store = load_app_profile_store()
    store["companionProfiles"][store["primaryCareRecipientId"]] = profile
    save_app_profile_store(store)
    write_json_file(COMPANION_PROFILE_PATH, profile)
    return profile


def companion_profile_response(data):
    action = (data.get("action") or "load").lower()
    if action == "save":
        profile = save_companion_profile(data.get("profile") or data)
    else:
        profile = load_companion_profile()
    template = COMPANION_TEMPLATES[profile["templateId"]]
    return {"ok": True, "profile": profile, "backendChar": template["backendChar"]}


def app_profile_response(data):
    action = (data.get("action") or "load").lower()
    if action in ("save", "replace"):
        store = save_app_profile_store(data.get("store") or data.get("profileStore") or data)
    elif action in ("save-companion", "save_companion"):
        save_companion_profile(data.get("profile") or data.get("companionProfile") or data)
        store = load_app_profile_store()
    else:
        store = load_app_profile_store()
    return {"ok": True, "store": store, "activeCompanionProfile": active_companion_profile(store)}


def default_billing_store():
    return {
        "schemaVersion": 1,
        "accountId": "local-demo-account",
        "platform": "ios",
        "provider": "storekit2-or-revenuecat",
        "activePlan": "free",
        "subscription": {
            "status": "inactive",
            "productId": None,
            "originalTransactionId": None,
            "expiresAt": None,
            "willRenew": False,
            "lastVerifiedAt": None,
        },
        "entitlements": {
            "voiceCompanion": True,
            "familyDashboard": True,
            "routineReminders": True,
            "realtimeAvatar": False,
            "premiumAvatarMinutesMonthly": 0,
            "familyMembersMax": 2,
        },
        "usageLedger": {
            "period": time.strftime("%Y-%m"),
            "voiceMinutesUsed": 0,
            "avatarMinutesUsed": 0,
        },
        "serverVerificationRequired": True,
        "updatedAt": utc_now(),
    }


def normalize_billing_store(data=None):
    base = default_billing_store()
    data = data or {}
    subscription = {**base["subscription"], **(data.get("subscription") or {})}
    entitlements = {**base["entitlements"], **(data.get("entitlements") or {})}
    usage = {**base["usageLedger"], **(data.get("usageLedger") or data.get("usage_ledger") or {})}
    return {
        "schemaVersion": int(data.get("schemaVersion") or data.get("schema_version") or 1),
        "accountId": str(data.get("accountId") or data.get("account_id") or base["accountId"]),
        "platform": str(data.get("platform") or base["platform"]),
        "provider": str(data.get("provider") or base["provider"]),
        "activePlan": str(data.get("activePlan") or data.get("active_plan") or base["activePlan"]),
        "subscription": subscription,
        "entitlements": entitlements,
        "usageLedger": usage,
        "serverVerificationRequired": bool(data.get("serverVerificationRequired", base["serverVerificationRequired"])),
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or utc_now(),
    }


def load_billing_store():
    return normalize_billing_store(read_json_file(BILLING_STORE_PATH, {}))


def save_billing_store(data):
    store = normalize_billing_store({**data, "updatedAt": utc_now()})
    write_json_file(BILLING_STORE_PATH, store)
    return store


def entitlements_response(data):
    action = (data.get("action") or "load").lower()
    if action in ("save", "replace"):
        store = save_billing_store(data.get("store") or data.get("billingStore") or data)
    else:
        store = load_billing_store()
    return {
        "ok": True,
        "billing": store,
        "entitlements": store["entitlements"],
        "subscription": store["subscription"],
    }


def subscription_event_response(data):
    event = data.get("event") or {}
    if not isinstance(event, dict):
        return {"ok": False, "error": {"code": "invalid_subscription_event"}}
    store = load_billing_store()
    store["lastSubscriptionEvent"] = {
        "receivedAt": utc_now(),
        "provider": data.get("provider") or "apple-app-store-server-notifications-v2",
        "eventType": event.get("type") or event.get("notificationType") or "unknown",
        "requiresJwsVerification": True,
    }
    save_billing_store(store)
    return {
        "ok": True,
        "accepted": True,
        "serverVerificationRequired": True,
        "note": "Local prototype only. Production must verify Apple signedTransactionInfo / signedRenewalInfo server-side.",
    }


def _sys_for(char):
    """組這個角色的系統人格：人格 + 醫療界線 +（真人才帶）記憶側寫。"""
    c = eng.CHARS.get(char, eng.CHARS[DEFAULT_CHAR])
    base = c["persona"] + eng.RED + (eng._profile_ctx() if c["type"] == "human" else "")
    return base, c


def reply_conv(history, char=DEFAULT_CHAR):
    """帶完整對話脈絡，用該角色的腦＋記憶回話。"""
    base, _ = _sys_for(char)
    contents = [types.Content(role=h["role"], parts=[types.Part(text=h["text"])]) for h in history]
    for _ in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = eng.client.models.generate_content(
                    model=m, contents=contents,
                    config=types.GenerateContentConfig(system_instruction=base, temperature=0.85))
                return r.text.strip()
            except Exception:
                pass
        time.sleep(2)
    return "（不好意思，我這邊連線有點不順，等一下再陪你好不好？）"


def tts_b64(text, char=DEFAULT_CHAR):
    """用該角色的聲音（＋動物的演技開場白）把文字唸成語音，回 base64 wav。"""
    c = eng.CHARS.get(char, eng.CHARS[DEFAULT_CHAR])
    content = (c["style"] or "") + text
    for m in ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"):
        try:
            r = eng.client.models.generate_content(
                model=m, contents=content,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=c["voice"])))))
            pcm = r.candidates[0].content.parts[0].inline_data.data
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass
    return ""


def decode_voice_note(data):
    raw = data.get("audio") or ""
    if "," in raw:
        raw = raw.split(",", 1)[1]
    audio_bytes = base64.b64decode(raw) if raw else b""
    mime = data.get("mime") or "audio/webm"
    if mime not in ALLOWED_AUDIO_MIMES:
        raise ValueError("unsupported_audio_mime")
    if len(audio_bytes) > MAX_AUDIO_NOTE_BYTES:
        raise ValueError("audio_note_too_large")
    return {
        "ok": bool(audio_bytes),
        "bytes": len(audio_bytes),
        "mime": mime,
        "durationMs": max(0, min(int(data.get("durationMs") or 0), 180000)),
        "reply": "我收到你的語音了。下一步會把這段接到即時語音理解。",
    }


def voice_session(data):
    """回傳前端語音層能力；未來 Gemini Live / Interactions token 從這裡核發。"""
    return {
        "ok": True,
        "provider": "stt-chat-tts",
        "fallback": "typed-chat",
        "locale": data.get("locale") or "zh-TW",
        "char": data.get("char") or DEFAULT_CHAR,
        "capabilities": {
            "textChat": True,
            "recordedVoiceNote": True,
            "serverTts": True,
            "realtimeAudio": False,
            "interrupt": False,
            "visemeTiming": False,
        },
    }


EXT = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
       ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
       ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
       ".svg": "image/svg+xml", ".ico": "image/x-icon", ".webp": "image/webp", ".wav": "audio/wav"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        self._send(200, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode())

    def _json_error(self, code, err_code, message="Request could not be processed", detail=None):
        rid = request_id()
        body = {"ok": False, "error": {"code": err_code, "message": message, "requestId": rid}}
        if detail and os.environ.get("MUNEA_DEBUG_API") == "1":
            body["error"]["detail"] = str(detail)[:160]
        self._send(code, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode())

    def _read_json_body(self):
        ln = int(self.headers.get("Content-Length", 0))
        if ln > MAX_JSON_BODY_BYTES:
            raise ValueError("payload_too_large")
        raw = self.rfile.read(ln).decode("utf-8", "replace") if ln else "{}"
        return json.loads(raw or "{}")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._json({
                "ok": True,
                "service": "munea-local-engine",
                "time": utc_now(),
                "contracts": ["app-profile", "companion-profile", "entitlements", "voice-session"],
            })
            return
        if path in ("/", ""):
            path = "/index.html"
        rel = posixpath.normpath(path).lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):   # 防目錄穿越 + 404
            self._send(404, "text/plain; charset=utf-8", b"404"); return
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            self._send(200, EXT.get(ext, "application/octet-stream"), f.read())

    def do_POST(self):
        try:
            data = self._read_json_body()
            char = data.get("char") or DEFAULT_CHAR
            if self.path == "/open":
                t = eng.open_chat(char)
                self._json({"reply": t, "audio": tts_b64(t, char)})
            elif self.path == "/chat":
                t = reply_conv(data.get("history", []), char)
                self._json({"reply": t, "audio": tts_b64(t, char)})
            elif self.path == "/voice-session":
                self._json(voice_session(data))
            elif self.path == "/voice-note":
                self._json(decode_voice_note(data))
            elif self.path == "/companion-profile":
                self._json(companion_profile_response(data))
            elif self.path == "/app-profile":
                self._json(app_profile_response(data))
            elif self.path == "/entitlements":
                self._json(entitlements_response(data))
            elif self.path == "/subscription-event":
                self._json(subscription_event_response(data))
            else:
                self._send(404, "text/plain; charset=utf-8", b"404")
        except json.JSONDecodeError as e:
            self._json_error(400, "invalid_json", "Request body must be valid JSON", e)
        except ValueError as e:
            if str(e) == "payload_too_large":
                self._json_error(413, "payload_too_large", "Request body is too large")
            elif str(e) == "audio_note_too_large":
                self._json_error(413, "audio_note_too_large", "Audio note is too large")
            elif str(e) == "unsupported_audio_mime":
                self._json_error(415, "unsupported_audio_mime", "Audio MIME type is not supported")
            else:
                self._json_error(400, "invalid_request", "Request could not be processed", e)
        except Exception as e:
            self._json_error(500, "internal_error", "Request could not be processed", e)


if __name__ == "__main__":
    print("沐寧 App 伺服器啟動 → http://localhost:8200  （Ctrl+C 結束）")
    HTTPServer(("127.0.0.1", 8200), H).serve_forever()
