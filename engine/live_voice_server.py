"""沐寧 · 即時語音橋接（stage 1）

瀏覽器 ⇄ 這個橋 ⇄ Gemini Live。讓長輩「開口就即時跟寧寧講電話」。
- 獨立的 async WebSocket 伺服器（:8201），不動 engine/server.py（那是 Codex 的地盤）。
- 把寧寧的人格＋非醫療界線＋長輩記憶（重用 chat_engine）當成 Live 的 system instruction，
  所以即時語音的寧寧也有個性、也記得使用者。

跑法：GEMINI_API_KEY=... python engine/live_voice_server.py
訊息協定（瀏覽器→橋）：
  - binary：麥克風 PCM16 @16kHz（即時串流）
  - {"type":"text","text":"..."}：純文字（測試/打字備援）
  - {"type":"audio_end"}：這段說完了
訊息協定（橋→瀏覽器）：
  - binary：寧寧的語音 PCM16 @24kHz
  - {"type":"caption","who":"nening|user","text":"..."}
  - {"type":"interrupted"} / {"type":"turn_complete"}
"""

import os
import sys
import json
import time
import datetime
import asyncio
import concurrent.futures
import uuid
import base64
import io
import wave
import hmac
import hashlib
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_loader import load_engine_env
from voice_echo_guard import frame_rms, in_output_window, should_drop_uplink_frame
load_engine_env()  # 跟 server.py 同款：自動吃 engine/.env.local 的鑰匙、環境變數優先
from service_metadata import build_service_metadata
import chat_engine as eng
import localization
import live_lookup
from call_control_client import post_internal, verify_call_token
from google import genai
from google.genai import types
import websockets
from websockets.http11 import Response
from websockets.datastructures import Headers

MODEL = "gemini-3.1-flash-live-preview"
TURN_END_SILENCE_MS = 180
TURN_END_SILENCE_PCM = b"\x00\x00" * int(24000 * TURN_END_SILENCE_MS / 1000)
LOOKUP_CUE_TAIL_MS = 80
LOOKUP_CUE_TAIL_PCM = b"\x00\x00" * int(24000 * LOOKUP_CUE_TAIL_MS / 1000)


def verify_family_relay_proof(relay):
    if not isinstance(relay, dict):
        return False
    secret = os.environ.get("MUNEA_FAMILY_RELAY_SIGNING_SECRET", "").strip()
    if not secret and os.environ.get("MUNEA_CALL_CONTROL_REQUIRED", "0") != "1":
        secret = "munea-local-family-relay"
    supplied = str(relay.get("relayProof") or "")
    if not secret or not supplied:
        return False
    material = "\n".join(str(relay.get(key) or "") for key in (
        "id", "recipientPersonId", "senderLabel", "content", "claimToken",
    ))
    expected = hmac.new(secret.encode("utf-8"), material.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)

# 多鑰匙分流（2026-07-12）：Gemini Live 對「同一把鑰匙的同時通話數」有配額上限——壓測壓到 30
# 人時撞的 APIError:1011 就是這個牆（不是我們容器塞爆）。備多把鑰匙（不同 Google 專案、各自
# 獨立配額），每通電話挑「現在最閒」的那把 → 同時人數上限 ≈ 單把上限 × 鑰匙數。
# 相容性：只給一把 GEMINI_API_KEY 時＝跟改動前完全一樣、零行為變化；要多把就用逗號分隔的 GEMINI_API_KEYS。
import threading
_raw_keys = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
if not KEYS:
    sys.exit("需要 GEMINI_API_KEY（或多把 GEMINI_API_KEYS，逗號分隔）")

_clients = [genai.Client(api_key=k) for k in KEYS]   # 每把鑰匙一個 client
_key_active = [0] * len(KEYS)                          # 每把鑰匙「現在幾通在用」
_key_lock = threading.Lock()

def _pick_client():
    """挑目前 active 最少的鑰匙開這通，回傳 (idx, client) 並把它的計數 +1。"""
    with _key_lock:
        idx = min(range(len(_key_active)), key=lambda i: _key_active[i])
        _key_active[idx] += 1
        return idx, _clients[idx]

def _release_client(idx):
    """這通結束→把該鑰匙計數 -1（放回空位給下一通）。"""
    with _key_lock:
        if 0 <= idx < len(_key_active) and _key_active[idx] > 0:
            _key_active[idx] -= 1

client = _clients[0]   # 向後相容：舊碼若引用單一 client，指到第一把

import mimetypes

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(HERE, "..", "web"))
VOICE_RELEASE_METADATA = build_service_metadata("munea-voice")


def _json_response(payload):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = Headers()
    headers["Content-Type"] = "application/json; charset=utf-8"
    headers["Cache-Control"] = "no-store"
    headers["Content-Length"] = str(len(body))
    return Response(200, "OK", headers, body)


def _file_response(rel):
    fp = os.path.normpath(os.path.join(WEB, rel))
    if not fp.startswith(WEB) or not os.path.isfile(fp):
        return Response(404, "Not Found", Headers({"Content-Length": "0"}), b"")
    with open(fp, "rb") as f:
        body = f.read()
    ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
    h = Headers()
    h["Content-Type"] = ctype + ("; charset=utf-8" if ctype.startswith("text/") else "")
    h["Content-Length"] = str(len(body))
    return Response(200, "OK", h, body)


def _chat_test_response():
    """Serve the full app with a local test-only developer session.

    This route is intentionally separate from the production entry point so
    normal App and web visitors keep their sign-in requirement.  The launcher
    only links to this route while a developer runs the local voice service.
    """
    fp = os.path.join(WEB, "index.html")
    try:
        with open(fp, "rb") as f:
            body = f.read()
    except OSError:
        return Response(404, "Not Found", Headers({"Content-Length": "0"}), b"")
    marker = b'<script src="src/auth.js'
    config = (
        b'<script>window.MUNEA_CHAT_TEST=true;window.MUNEA_DEV_CONFIG={enabled:true,'
        b'allowNonLocalhost:true,autoSignIn:true,skipOnboarding:true,analyticsExcluded:true,'
        b'authUserId:"00000000-0000-4000-8000-000000000001",'
        b'email:"chat-test@munea.local",displayName:"Chat Test"};'
        b'try{localStorage.setItem("munea.consent.crossborder","1");'
        b'localStorage.setItem("munea.interestsAsked","1");'
        b'localStorage.setItem("munea.plan","pro");}catch(e){}'
        b'window.addEventListener("munea:auth-state",function(e){if(e.detail&&e.detail.status==="signed-in")'
        b'setTimeout(function(){var b=document.getElementById("startCall");if(b)b.click();},150);},{once:true});</script>\n'
    )
    if marker not in body:
        return Response(500, "Internal Server Error", Headers({"Content-Length": "0"}), b"")
    body = body.replace(marker, config + marker, 1)
    h = Headers()
    h["Content-Type"] = "text/html; charset=utf-8"
    h["Content-Length"] = str(len(body))
    return Response(200, "OK", h, body)


def process_request(connection, request):
    """非 WebSocket 的請求就當靜態網站服務（測試頁＋臉圖等），讓網頁與語音走同一個門。"""
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None
    path = request.path.split("?")[0].lstrip("/")
    if path in ("version", "version/"):
        return _json_response({"ok": True, "release": VOICE_RELEASE_METADATA})
    if path in ("healthz", "healthz/"):
        return _json_response({
            "ok": True,
            "service": "munea-voice",
            "release": VOICE_RELEASE_METADATA,
            "runtime": {"transport": "websocket"},
        })
    if path in ("chat-test", "chat-test/"):
        return _chat_test_response()
    if path in ("app", "app/", "app.html"):
        path = "index.html"
    elif path in ("", "index.html"):
        path = "live-voice-test.html"
    return _file_response(path)


import server  # 重用文字聊天同一套「腦」組裝：人格層＋記憶層＋感知層＋守護腦，確保即時語音同步
import notify as guardian_notify  # 守護腦命中 high/critical 時的內部安全告警（Slack #沐寧-告警 kind=voice）；送不出去就默默記日誌，不影響通話
import perception_engine  # 守護腦第二層：拐彎危機語意判讀（Gemini Flash）——第一層沒抓到硬危機、但有軟訊號苗頭時才升級


# ============================================================================
# 守護腦接回語音線（batch 0 - 第二批 - 2026-07-12）
# ----------------------------------------------------------------------------
# 語音線是 Gemini Live 直接串流，沒有「先想好再回話」的餘裕，守護腦在這裡只能「並行盯字幕」：
#   - 用戶字幕（input_transcription）＋寧寧自己的字幕（output_transcription）一到就丟去背景看一眼
#   - 絕不擋音訊管線：關鍵字判讀（CPU-only）與記錄/告警（會打 Supabase/Slack，有網路 I/O）
#     一律用 asyncio.to_thread／asyncio.create_task 丟到背景，from_live() 主迴圈永遠先把這一包音訊送出去、
#     不等守護腦判完
#   - 命中 high/critical 才動作：一記一筆安全事件（沿用現有 audit/product event 機制，跟 /chat 文字線同一張表、
#     同一個 admin 後台看得到）二內部安全告警（Slack，不外洩內容，只送等級/類別）三排一句安全導引，等這一輪
#     自然講完（turn_complete）才送給寧寧，讓她「下一句」自然轉向轉介——不是插話攔截「這一句」（Live API
#     語意上做不到，中途硬插一個新 turn 會撞正在跑的即時音訊輪，行為未定義，比不做更危險）
#   - 誠實面對殘留風險：這是「事後極快監聽＋下一句補救」，不是「攔截阻止這一句」。用戶當下正在飛出去的那句話
#     擋不住；critical 情況下，寧寧本來就有 chat_engine.RED 當底線（session 開場就給了），這一層是加固、不是唯一防線。
# ============================================================================
_GUARDIAN_CUE_BY_CATEGORY = {
    "self_harm_crisis": (
        "使用者剛剛的話透露出可能想傷害自己／不想活的念頭。接下來這句要溫柔但堅定地接住這份情緒，"
        "不要說教、不要問「為什麼會這樣想」，改用一兩句安全確認（像是「你現在身邊有沒有人可以陪你」「你現在安全嗎」），"
        "自然帶到可以撥打安心專線 1925（24 小時）或找信任的家人陪伴；語氣沉穩、不要慌張、一次別講太多。"
    ),
    "harm_others_crisis": (
        "使用者剛剛的話透露出想傷害別人的念頭。接下來這句要保持冷靜、不批判，先關心他和對方現在是否安全、是否獨處，"
        "不要深究他為什麼這樣想，溫和引導找信任的人或撥打 110/119 協助，不要順著情緒火上加油。"
    ),
    "mental_state_abnormal": (
        "使用者剛剛的話聽起來像是有被監控／被害／幻聽這類感受。接下來這句不要確認也不要否定那件事是不是真的發生，"
        "先接住他的不安（像「這種感覺一定讓你很不安」），保持中立（像「我沒辦法確認這件事，但我相信你現在的害怕是真的」），"
        "再溫和拉回安全、鼓勵找信任的人或醫生一起看看；絕對不要追問細節、也不要說「你想太多了」。"
    ),
    "protection_event": (
        "使用者剛剛的話透露出可能被家暴／遺棄照護疏忽／財務剝削。接下來這句先穩穩接住、不追問細節，"
        "溫和問他現在是否安全、身邊有沒有讓他害怕的人，再告訴他有一支 24 小時保護專線 113 可以幫忙、也會保密，"
        "問他要不要陪他記下來；這件事先不要建議他去找家人幫忙（傷害他的人可能就是家人），改往 113 或其他信任的人。"
    ),
    "medical_emergency_signal": (
        "使用者剛剛的話像是身體出現緊急狀況（例如胸痛、喘不過氣、昏倒、中風徵兆）。接下來這句要立刻放下其他話題，"
        "用一兩句關切確認狀況，並堅定建議現在就打 119 或找人幫忙，不要拖、不要輕描淡寫。"
    ),
}


def guardian_redirect_cue(categories, risk=None, policy=None):
    """使用者字幕命中 high/critical，排一句安全導引，讓寧寧下一句自然轉向轉介（不是插話攔截這一句）。"""
    lines = [_GUARDIAN_CUE_BY_CATEGORY[c] for c in categories if c in _GUARDIAN_CUE_BY_CATEGORY]
    if not lines:
        lines = ["使用者剛剛的話可能碰到需要謹慎處理的安全界線，接下來這句話要溫和、不批判、把話題帶回安全與尋求真人協助的方向。"]
    return (
        "（系統安全提示，絕對不要唸出這段、也不要提到「系統」「安全提示」「守護腦」這些詞：" + "".join(lines) +
        "這句提示只給你看，不要提到「提示」兩個字，用你自己的口吻自然接下去。）"
    )


def guardian_ai_correction_cue(categories, risk=None, policy=None):
    """寧寧自己講出來的字幕命中 high/critical，排一句自我校正，讓她下一句悄悄拉回安全（軟提醒，不硬認錯）。

    保守設計：字幕比對是關鍵字層級，寧寧為了同理而覆述使用者原話也可能誤觸，
    所以這句是「再次確認有做到安全原則」的溫和提醒，即使是誤觸也不會講出奇怪或委屈的話。
    """
    return (
        "（系統安全提示，絕對不要唸出這段：接下來這句話，請再次確認你有做到，不強化任何被監控或被害這類說法、"
        "不否定他的感受、不建議停藥或給醫療判斷、遇到受暴或被剝削的情況不要主張自己去告訴家人改講 113、"
        "把話題自然帶回安全與鼓勵尋求真人協助。如果你剛剛已經有做到，就自然接著聊，不用道歉、不用提起這件事。）"
    )


def guardian_scan_text(text):
    """純函式：一句字幕丟進去，回傳守護腦判讀結果。不做任何 I/O、不碰 session，方便單元測試/語音線模擬。"""
    try:
        return server.model_router.guardian_evaluate_response({"text": text, "effort": "quick"})
    except Exception:
        return None


def guardian_record_and_alert(who, cid, result, record_fn=None, alert_fn=None):
    """side effect 段（會打 Supabase/Slack，一律在背景執行緒跑）：
    一記一筆安全事件，沿用既有 audit/product event 機制（跟 /chat 文字線同一張表、同一個 admin 後台看得到），
    多帶 protectionEvent／familyNotificationCandidate／protectionLine／who／source 幾個欄位，
    方便未來做「真的推播家人」時直接查得到（現在還沒有主動推播家人的功能，這裡先把料記好）。
    二內部安全告警（Slack #沐寧-告警），只送等級/類別，不送逐字稿、不送個資。
    record_fn / alert_fn 可注入假函式做測試（語音線模擬），預設用 server.append_product_event / notify.alert。
    """
    risk = (result or {}).get("risk") or {}
    policy = (result or {}).get("responsePolicy") or {}
    level = risk.get("level") or "none"
    categories = risk.get("categories") or []
    if risk.get("requiresAuditEvent"):
        rec = record_fn or server.append_product_event
        try:
            rec({
                "eventName": "guardian_risk_evaluated",
                "source": "live_voice",
                "properties": {
                    "riskLevel": level,
                    "categories": categories,
                    "analyticsExcluded": True,
                    "source": "live_voice",
                    "who": who,
                    "protectionEvent": bool(risk.get("protectionEvent")),
                    "familyNotificationCandidate": bool(policy.get("familyNotificationCandidate")),
                    "protectionLine": policy.get("protectionLine"),
                },
            })
        except Exception as e:
            _diag(cid, "guardian.record_err", err="%s:%s" % (type(e).__name__, str(e)[:60]))
    if risk.get("requiresHumanEscalation"):
        al = alert_fn or guardian_notify.alert
        try:
            al(
                "voice",
                "guardian:%s" % ((categories or ["-"])[0]),
                "level=%s who=%s categories=%s protectionEvent=%s familyNotificationCandidate=%s" % (
                    level, who, ",".join(categories) or "-",
                    risk.get("protectionEvent"), policy.get("familyNotificationCandidate"),
                ),
            )
        except Exception as e:
            _diag(cid, "guardian.alert_err", err="%s:%s" % (type(e).__name__, str(e)[:60]))


async def guardian_watch(cid, who, text, st, session):
    """背景任務：非同步跑守護腦判讀 + 記錄/告警 +（high/critical）排隊安全導引。絕不擋音訊管線。"""
    try:
        result = await asyncio.to_thread(guardian_scan_text, text)
        if not result:
            return
        risk = (result or {}).get("risk") or {}
        level = risk.get("level") or "none"
        categories = tuple(risk.get("categories") or [])
        await asyncio.to_thread(guardian_record_and_alert, who, cid, result)
        if level not in ("high", "critical"):
            # 第二層：第一層沒抓到硬危機、但用戶的話有「拐彎苗頭」→ 升級便宜 AI 判語意（只判用戶說的、每通上限 5 次、背景跑不擋通話）
            policy0 = (result or {}).get("responsePolicy") or {}
            if who == "user" and policy0.get("softSignalForReview") and st.get("semantic_calls", 0) < 5:
                st["semantic_calls"] = st.get("semantic_calls", 0) + 1
                sem = await asyncio.to_thread(perception_engine.guardian_semantic_review, text, [st.get("user_buf", "")])
                if sem and sem.get("level") in ("high", "critical"):
                    _sem_cat_map = {"self_harm": "self_harm_crisis", "medical_emergency": "medical_emergency_signal",
                                    "protection": "protection_event", "mental_state": "mental_state_abnormal"}
                    scat = _sem_cat_map.get(sem.get("category"), sem.get("category") or "semantic")
                    is_protect = scat == "protection_event"
                    sem_result = {
                        "risk": {"level": sem["level"], "categories": [scat],
                                 "requiresAuditEvent": True, "requiresHumanEscalation": True,
                                 "protectionEvent": is_protect},
                        "responsePolicy": {"familyNotificationCandidate": (not is_protect),
                                           "protectionLine": "113" if is_protect else None},
                    }
                    _diag(cid, "guardian.semantic_hit", who=who, level=sem["level"], cat=scat, conf=sem.get("confidence"))
                    await asyncio.to_thread(guardian_record_and_alert, who, cid, sem_result)
                    key = ("semantic", scat)
                    if key not in st["user_flagged"]:
                        st["user_flagged"].add(key)
                        cue = guardian_redirect_cue((scat,), sem_result["risk"], sem_result["responsePolicy"])
                        if len(st["pending_cues"]) < 2:
                            st["pending_cues"].append(cue)
            return
        flagged = st["user_flagged"] if who == "user" else st["ai_flagged"]
        if categories in flagged:
            return
        flagged.add(categories)
        policy = (result or {}).get("responsePolicy") or {}
        _diag(cid, "guardian.hit", who=who, level=level, categories=",".join(categories) or "-",
              protection=risk.get("protectionEvent"), family=policy.get("familyNotificationCandidate"))
        cue = (guardian_ai_correction_cue if who == "ai" else guardian_redirect_cue)(categories, risk, policy)
        cues = st["pending_cues"]
        if len(cues) < 2:
            cues.append(cue)
    except Exception as e:
        _diag(cid, "guardian.watch_err", err="%s:%s" % (type(e).__name__, str(e)[:60]))


async def guardian_flush_pending_cue(cid, session, st):
    """在天然的輪替空檔（模型這一輪講完、turn_complete）送出排隊的安全導引，不是插話攔截正在講的這一句。"""
    pending = st.get("pending_cues") or []
    st["pending_cues"] = []
    if not pending:
        return
    try:
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="\n".join(pending))]),
            turn_complete=True,
        )
        _diag(cid, "guardian.cue_sent", count=len(pending))
    except Exception as e:
        _diag(cid, "guardian.cue_err", err="%s:%s" % (type(e).__name__, str(e)[:60]))


def _capture_call_turns(st, max_turns=120, max_chars=600):
    """把這一輪的雙方字幕（守護腦滑動窗）收進整通紀錄 call_turns。
    在每輪 turn_done 清緩衝前呼叫一次、收線時再補最後一輪；只留最近 max_turns 段防爆。"""
    for role, key in (("user", "user_buf"), ("assistant", "ai_buf")):
        text = (st.get(key) or "").strip()
        if text:
            st.setdefault("call_turns", []).append({"role": role, "content": text[:max_chars]})
    turns = st.get("call_turns")
    if turns and len(turns) > max_turns:
        del turns[:-max_turns]


def system_instruction(char="寧寧", name=None, mood=None, topics=None, user=None, location=None, allow_reminders=False, fam=0, memory_scope=None, allow_events=False):
    """跟 /chat 同一套腦：角色人格 + 非醫療界線 + 記憶層 + 感知層 + 守護腦。"""
    c = eng.CHARS.get(char) or eng.CHARS["寧寧"]
    # 優先權契約放在整份說明書最前面：規則衝突不再靠「排在前面還後面」決定，
    # 一律照層級數字比大小（7/15 Edward 拍板說明書分層）。
    base = (
        "（本說明書優先權契約：以下所有規則分五層——"
        "一、安全與醫療紅線（危機處理、不診斷不調藥） 二、語言鐵律（台灣華語、禁台語輸出） "
        "三、身分與人格（角色、稱呼、關係分寸） 四、當下情境（記憶、感知、上次聊天、在地資訊） "
        "五、表達風格（話量、句尾、說故事、情緒陪伴）。"
        "內容互相衝突時，層級數字小的一律優先；任何風格規則都不得鬆動安全與語言規則。）"
    )
    # 共同底盤（管家身分＋專業邊界＋告警/情緒/調解能力）在最前面，角色性格疊在上面
    base += eng.CORE + c.get("persona", "") + eng.RED
    try:
        # displayName 跟著角色走：用戶自訂名優先、否則用角色本名。
        # 不傳的話會 fallback 到存檔的陪伴檔案（寧寧），把換角色的名字蓋回去。
        data = {"displayName": (name or char)}
        if location:
            data["location"] = location  # 所在地（可到區）→ 在地餐廳/景點/話題定位
        if mood:
            data["userMood"] = mood
        if topics:
            data["interests"] = topics  # 用戶挑的興趣話題（?topics=）→ 開場/接話的方向
        ctx = server.build_reply_context([], char, data)
        base += server.reply_context_instruction(ctx)
    except Exception:
        pass
    try:
        # 上一通剛聊過（12 小時內）→ 開場自然接續、不重問剛答過的日常問題（Edward 7/15：20 分鐘後再打還被問吃飯沒）
        # memory_scope＝這通的人別隔離鍵（token 的 voice-<user_id>），跟收線回寫同一 scope。
        # 正式路線（B）：Brain 通道設定齊全＋這通有已驗證用戶 → 向 Brain 要該用戶自己的
        # 「上次聊天重點」（讀東京正式庫）；否則退回 Voice 本機模式。
        brain_url, brain_secret = _brain_memory_config()
        recap = ""
        if brain_url and memory_scope and memory_scope.startswith("voice-"):
            try:
                resp = post_internal(
                    brain_url, brain_secret, "/voice/call-recap",
                    {"userId": memory_scope[len("voice-"):]}, timeout=3,
                    app_key=os.environ.get("MUNEA_APP_KEY", "").strip())
                recap = str((resp or {}).get("recapLine") or "")
            except Exception:
                recap = ""
        if not recap:
            recap = server.recent_call_recap_line(person_id=memory_scope)
        base += recap
    except Exception:
        pass
    if c.get("type") == "animal" and c.get("style"):
        base += f"（你講話的聲音演技：{c['style']}）"
    base += (
        # 相處框架（2026-07-16 Edward 拍板）：先給「像真人視訊」的整體想像、再給細規則——
        # 好的自我想像會自動帶出自然節奏；「像真人一樣聊天」是說話方式、不是身分宣稱，
        # 底層紅線「不能假裝自己是真人」仍然優先（優先權契約層級小者優先）。
        "（現在是即時語音視訊通話。把整通電話當成真實世界裡兩個人的視訊聊天來相處："
        "你的節奏、溫度、來回方式，都要像一個自然、有人味的人在跟他視訊——"
        "多數時候是他說、你接住；不是你表演、他觀看。"
        "剛接起電話先用一句溫暖的話打招呼；不確定對方是誰時不要亂猜名字或稱呼；"
        "句子短、口語、一次一兩句、講完停下來等對方回應。）"
        # 通用紅線（2026-07-16）：不管上面有沒有給「上次聊過」的提示，都不准虛構跨通記憶——
        # Gemini 沒拿到摘要也可能自己演「延續上一通」，這條對所有通話無條件生效。
        "（紅線：這是一通新接起的電話。系統沒有明確告訴你的事，一律不要宣稱記得——"
        "不准編造「我們剛剛聊到」「你上次跟我說」這類上一通的具體內容；"
        "對方主動提起時順著他說的接就好，自己不知道就誠實說想再聽他講一次。）"
        # 2026-07-16 Edward 抓到幻覺實例：AI 說「怎麼突然傳貼圖」——App 根本沒有貼圖功能。
        # 多模態模型聽到雜音/不明聲音時會拿「聊天軟體的常見情境」腦補，必須用現實邊界封死。
        "（現實邊界：這是純語音通話——對方只能用「說話的聲音」跟你互動，"
        "沒有貼圖、照片、文字訊息、影片、連結、按鈕可以傳給你，你也看不到他的畫面。"
        "絕對不要說「你傳了貼圖／照片／訊息」這類話；"
        "聽不清楚、或只聽到雜音時，就誠實說沒聽清楚、請他再說一次，不要猜測他做了什麼動作。）"
    )
    # 熟識度分寸貫穿整段對話（不只開場）：越不熟越收斂、越熟越自在（Edward 2026-07-12）
    if fam < 1:
        base += "（你們還不太熟，這是頭幾通電話：整段對話都要特別收斂——話少、溫和、讓他主導，不要熱情轟炸、不要一直找話題硬聊、不要連環問。他問你、或聊到他有興趣的才多說一點。）"
    elif fam < 3:
        base += "（你們聊過幾次、漸漸熟了：可以自在一點，但仍別長篇、別連環問、別硬炒氣氛。）"
    else:
        base += "（你們很熟了、像老朋友：自在、可主動一點，但一次還是一兩句、不長篇。）"
    base += (
        "（你有 search_current_information 即時查詢工具。聊到餐廳店家、景點旅遊（例如日本哪裡好玩、桃園有什麼好吃的）、"
        "電影影劇、天氣預報、時事、活動檔期這類「講錯會誤導人」的具體話題，直接呼叫工具；"
        "不要自己先說過場、也不要先生成答案，Voice 伺服器會先替你播放「我幫你查一下」，再執行查詢。工具回來後才回答，"
        "只講查到的真店名、真地點、真資訊；用「我聽很多人推薦…」「那邊最有名的是…」這種像自己去過或朋友推薦的口吻，"
        "自然分享一兩個亮點就好，順便帶一個有意思的小知識或典故更好。不要唸清單、不要報網址、不要像導覽機。"
        "查不到或不確定就老實說「這我不太確定，我幫你查查看」——寧可少講，絕對不可以自己編店名、地址、價格或營業時間。"
        "天氣要講就查當地真的預報再講。"
        "工具回覆 error 時只要簡短說現在沒查到，不可拿舊印象補答案；禁止先沉默查詢，也不要在還沒查完時假裝已經知道答案。）"
    )
    nm = (name or "").strip()
    if nm and nm not in ("寧寧", "沐寧", "munea", "Munea"):
        base += (
            f"（很重要：用戶把你的名字改成「{nm}」了。從現在起你就叫「{nm}」，"
            f"打招呼、自我介紹、自稱一律用「{nm}」，絕對不要再說自己叫寧寧。）"
        )
    # 稱呼對方＝個人資料的「家人稱呼／名稱」優先（7/9 Edward 拍板：不吃帳號、不吃舊示範檔）
    uv = (user or "").strip()
    if uv:
        # 2026-07-16 Edward「回話會一直叫用戶名稱、很詭異」：舊寫法要求全程以稱呼帶著講，
        # 被模型讀成「每句都要叫」→ 改成「名字要用對＋頻率像真人」兩件事分開講。
        base += (
            f"（稱呼規則：若要稱呼對方，唯一正確的稱呼是「{uv}」——這是他自己在個人資料裡填的，"
            f"優先於任何記憶或舊資料裡的名字、不要叫他別的名字。"
            "但頻率要像真人：打招呼時用一次就好，之後大多數回合直接說話、不加稱呼；"
            "只有安撫他、提醒重要事情、或隔很久重新開口時才偶爾再叫一次。"
            "每一句都叫他的名字非常不自然、禁止。）"
        )
    # 今天日期時間（台灣時間）——所有版本都給，讓「明天／今晚」算得準（2026-07-09 Edward）
    tw = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    wd = "一二三四五六日"[tw.weekday()]
    base += (
        f"（現在是台灣時間 {tw.year}-{tw.month:02d}-{tw.day:02d}（星期{wd}）{tw.hour:02d}:{tw.minute:02d}。"
        "算「明天／後天／今晚／下週三」這類日期時間時，一律以這個現在時間為準換算。）"
    )
    # 「幫你設提醒」工具說明——只給接得住的新版 App（能力握手 ?cap_rem=1），舊版不講、免得它亂試假成功
    if allow_reminders:
        base += (
            "（你可以「直接幫他把提醒設進 App」：他說要設看診／回診提醒，就呼叫 set_clinic_reminder；"
            "他說要設吃藥／用藥提醒，就呼叫 set_medication_reminder。呼叫前若日期、時間、藥名或科別沒聽清楚，"
            "先用一句話問清楚再設，不要自己亂猜。只有工具回覆 status=ok 才能說設好了；若回覆 error，誠實說沒有設成功並請他重試。"
            "他要傳話給家庭圈成員時，先用一句話複誦收件人與完整內容，得到確認後才呼叫 send_family_relay；不要自行添加、刪改或猜測內容。"
            "設好之後用一句溫暖口語的話跟他確認你設了什麼"
            "（例如「好，我幫你記下明天下午四點台大骨科回診了」），讓他安心、也方便他去 App 裡的提醒清單看或改。"
            "「分類鐵律」：看診提醒只能用在真的要去醫院、診所看醫生；用藥提醒只能用在吃藥。"
            "約會、聚餐、出遊、家人來訪這類行程「絕對不可以」設成看診或用藥提醒——分類錯了會讓 App 講出很奇怪的話。）"
        )
    if allow_events:
        base += (
            "（他說要記「約會、聚餐、出遊、活動、家人來訪」這類行程時，呼叫 set_personal_event 幫他記進 App 的家庭活動。"
            "時間換算成 24 小時制要用常識：吃飯、晚餐、約會講「7點」通常是晚上 19:00、不是早上；"
            "聽不出上午或晚上，就先用一句話問清楚再設。"
            "現在若是深夜或凌晨，他說「明天」時先跟他確認是「等天亮的那個白天」還是「再隔一天」，確認完再換算日期。"
            "呼叫前用一句話跟他確認日期、時間、名目；工具回 status=ok 才能說記好了。）"
        )
    elif allow_reminders:
        base += (
            "（這一版 App 還記不了約會、聚餐這類行程。他想記行程時，誠實說你這邊還記不了、"
            "請他到「家人」頁用「發起活動」自己建一個，千萬不要拿看診或用藥提醒充數。）"
        )
    # Keep this last so persona, memory, interests, and older examples can
    # never weaken the Mandarin-only launch rule.
    base += localization.taiwan_mandarin_launch_instruction("zh-TW")
    base += (
        "\n[即時語音話量上限]\n"
        "一般閒聊預設只回答一句、約十五到三十個中文字，講完就停。"
        "只有對方明確要求解釋、比較或提供做法時，才可以回答兩句；一次仍只談一個重點。"
        "不要把同理、回顧、建議和追問全部塞在同一輪，也不要為了延續聊天自行補第二個話題。"
        "危急安全導引與必要的工具操作確認不受句數限制，但仍要短而清楚。"
        "\n[即時語音能量]\n"
        "預設比對方穩一點、慢一點，像熟朋友自然說話；不要高亢、大聲熱場、連續驚嘆或用過多感嘆號。"
        "對方很有精神時才可以小幅跟上，開場仍保持沉穩。"
        # 開場升溫（2026-07-16 Edward：「用戶最剛開始聊話不要太多、太熱情」）——不分熟識度、每通無條件生效
        "\n[開場升溫]\n"
        "不管你們多熟，每通電話的開頭都從低溫起步：前三輪每輪最多一句話、先聽多講少，"
        "像老朋友接電話那種自然鬆弛；不要一接通就高能量歡迎、不要問候＋關心＋提問三連發、"
        "也不要自顧自鋪話題。對方聊開了，話量和溫度才跟著慢慢升。"
        "\n[句尾收法]\n"
        "不要每句話的結尾都反問或拋問題。大多數回合用溫暖的陳述句自然收尾，"
        "把說話權留給對方、讓他決定要不要接；真的想多了解他，隔幾輪才問一次、一次只問一個。"
        # 反問再收緊（2026-07-16 Edward：「回話少一點反問」）——給硬規矩，比「大多數」咬得住
        "硬規矩：不准連續兩輪都用問題收尾；想表達關心時，優先用陳述句把你聽到的說回去"
        "（像「這聽起來真的不容易」），而不是把球丟回去反問他。"
        "\n[說故事與在地內容]\n"
        "他想聽故事時，講一個「完整的小故事」：有開頭、有轉折，結尾一定要用一句話點出這個故事的意思（寓意），"
        "最好能輕輕連回他的生活；不要講一半沒收尾、也不要像報流水帳。"
        "故事、時事、文化、生活知識預設以台灣為主：台灣的人物、地方、節慶、俗諺，"
        "和老一輩熟悉的年代記憶（廟口、眷村、火車、割稻這類），用台灣人的講法講；"
        "講到外國的內容時，用台灣人熟悉的角度帶進來。不確定的史實先用即時查詢確認，不要編。"
        "\n[接住情緒與陪伴引導]\n"
        "聽出他情緒不對時，照三步走、不要跳步。"
        "第一步「接住」——先用他的話把感受說回去（例如「聽起來這件事讓你很委屈」），讓他知道你真的聽懂了；"
        "這一步絕對不給建議、不講道理。各種情緒的接法："
        "孤單→承認一個人的時間特別長，告訴他你在、想聽他說；"
        "低落→不打氣、不催他振作，陪他把「最重的那塊」說出來；"
        "焦慮→先放慢你自己的語速，帶他慢呼吸（吸四秒、吐六秒），等他穩一點再談內容；"
        "崩潰→句子放短、聲音放穩，告訴他「我在，不用急著講」，先陪、不先問；"
        "難過→讓他慢慢說完，不打斷、不急著安慰，他想哭就陪著；"
        "生氣→先認他的感受（「難怪你會氣」），不評對錯、不幫任何一方講話（尤其是家人），讓他把氣講完。"
        "\n第二步「找到問題所在」——等情緒緩一點，用開放的問題一次一個、輕輕往下問："
        "「什麼時候開始的？」「那天發生了什麼？」「最讓你難受的是哪一部分？」「你覺得是因為什麼？」。"
        "目標是讓他自己說出原因，不是你替他下結論；把「發生的事」「他怎麼解讀」「他的感受」當三件事分開聽，"
        "聽到他把某個解讀當成事實時，溫柔問一句「有沒有別的可能？」。問兩三個就好，不要像問卷。"
        "\n第三步「量身的建議與關懷」——建議必須連著第二步找到的原因，而且用他自己的生活來做："
        "他講過的家人、老朋友、興趣、住的地方、生活習慣。一次只給一個、小到今天或明天就做得到，"
        "給完問他「你覺得做得到嗎？」，他說難就一起調整、不硬塞。"
        "有時候他要的不是辦法、是陪伴——不確定就直接問：「你想要我幫你想想辦法，還是先聽你說就好？」"
        "\n整段禁止：「出去走走」「看看海」「想開一點」「加油」「不要想太多」「會過去的」"
        "這類一百個人講一百次的罐頭話單獨當建議；也不要說教、不要比慘（「別人更慘」）、不要還沒聽完就給答案。"
        "\n界線：低落持續兩週以上、開始影響吃飯睡覺，就溫柔建議找專業的人聊聊（1925 安心專線），"
        "說明這跟感冒去看醫生一樣自然；醫療紅線與危機處理規則永遠優先於本節。"
    )
    return base


# 「幫你設提醒」工具（Gemini Live 函式呼叫）→ 橋接層轉成 {type:action} 給 App 執行（2026-07-09 Edward）
_REMINDER_TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="set_clinic_reminder",
        description="使用者要設定看診／回診提醒時呼叫，把提醒建進 App 的看診提醒。",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "title": types.Schema(type=types.Type.STRING, description="看診名稱，例如「台大骨科回診」"),
                "date": types.Schema(type=types.Type.STRING, description="日期，格式 YYYY-MM-DD（把「明天」等相對日期換算成實際日期）"),
                "time": types.Schema(type=types.Type.STRING, description="時間，24 小時制 HH:MM，例如下午四點=16:00"),
            },
            required=["title", "date", "time"],
        ),
    ),
    types.FunctionDeclaration(
        name="set_medication_reminder",
        description="使用者要設定吃藥／用藥提醒時呼叫，把提醒建進 App 的用藥提醒。",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "name": types.Schema(type=types.Type.STRING, description="藥名，例如「止痛藥」「血壓藥」"),
                "slots": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="吃藥時段，只能從這四個挑最接近的：早餐後、午餐後、晚餐後、睡前（例如「晚上七點」對應「晚餐後」）。可多個。",
                ),
                "days": types.Schema(type=types.Type.STRING, description="頻率，例如「長期」（每天）或「一次」（只有這次）"),
            },
            required=["name", "slots"],
        ),
    ),
    types.FunctionDeclaration(
        name="send_family_relay",
        description="使用者明確確認要把一句話轉達給家庭圈中的指定成員後呼叫。必須保留原意，不可自行加油添醋。",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "recipientName": types.Schema(type=types.Type.STRING, description="家庭圈收件人的名稱或稱呼，例如「小宇」"),
                "message": types.Schema(type=types.Type.STRING, description="已向使用者複誦並確認的完整傳話內容，最多 240 字"),
            },
            required=["recipientName", "message"],
        ),
    ),
])

# 「幫你記行程」工具（2026-07-16 Edward：約吃飯被硬塞成看診提醒）→ App 寫進揪一攤活動帳本。
# 只給帶 ?cap_evt=1 的新版 App（能力握手），舊版不聲明、AI 也會被指示誠實說記不了。
_EVENT_TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="set_personal_event",
        description="使用者要記「約會、聚餐、出遊、活動、家人來訪」這類行程時呼叫，記進 App 的家庭活動。看診用 set_clinic_reminder、吃藥用 set_medication_reminder，不可混用。",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "title": types.Schema(type=types.Type.STRING, description="行程名目，例如「和老婆吃飯」「孫子來訪」"),
                "date": types.Schema(type=types.Type.STRING, description="日期，格式 YYYY-MM-DD（把「明天」等相對日期換算成實際日期；深夜凌晨要先跟使用者確認是哪一天）"),
                "time": types.Schema(type=types.Type.STRING, description="時間，24 小時制 HH:MM。用常識判斷：吃飯約會講「7點」通常是 19:00"),
                "place": types.Schema(type=types.Type.STRING, description="地點，沒講就留空"),
            },
            required=["title", "date", "time"],
        ),
    ),
])

_LIVE_LOOKUP_TOOL = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name=live_lookup.TOOL_NAME,
        description=(
            "查詢需要最新或精確外部資料的問題，例如餐廳店家、地點景點、天氣、交通、新聞、"
            "活動檔期、營業時間與近期影劇資訊。需要這些資料時：先用一句自然的話順著對方的"
            "話題回應（例如「南港喔，我幫你看看」），說完立刻呼叫本工具；不要自行編造答案。"
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(type=types.Type.STRING, description="要查證的完整問題，保留地名與條件"),
                "location": types.Schema(type=types.Type.STRING, description="問題相關地點；沒有就留空"),
            },
            required=["query"],
        ),
    ),
])


_ASR_PRODUCT_PHRASES = (
    "沐寧", "Munea", "寧寧", "阿宏", "小昀", "阿原", "咪咪", "旺財",
    "家人圈", "回診", "看診", "用藥提醒", "吃藥提醒", "血壓", "血糖",
    "血氧", "心率", "健康紀錄", "興趣", "濃醇",
)


def asr_adaptation_phrases(char=None, name=None, user=None, topics=None, location=None):
    """Build bounded Taiwan-Mandarin ASR hints from this call's real context."""
    # Put call-specific proper nouns first. Names are the hardest terms to
    # recover from homophones, while generic care vocabulary is easier for ASR.
    values = [
        user,
        f"我叫{user}" if user else None,
        f"我是{user}" if user else None,
        name,
        char,
        location,
        *(topics or []),
        *_ASR_PRODUCT_PHRASES,
    ]
    phrases = []
    seen = set()
    for raw in values:
        value = str(raw or "").strip()[:48]
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        phrases.append(value)
        if len(phrases) >= 28:
            break
    return phrases


def live_config(char="寧寧", name=None, mood=None, topics=None, user=None, location=None, allow_reminders=False, fam=0, memory_scope=None, allow_events=False):
    c = eng.CHARS.get(char) or eng.CHARS["寧寧"]
    voice = c.get("voice") or "Leda"
    # 即時查詢改成可攔截的函式：Voice 先播放過場，再用獨立 Google Search
    # 查證後把材料交回 Live。內建搜尋只有結果 metadata，無法保證搜尋前已出聲。
    tools = [_LIVE_LOOKUP_TOOL]
    if allow_reminders:
        tools.append(_REMINDER_TOOLS)
    if allow_events:
        tools.append(_EVENT_TOOLS)
    phrases = asr_adaptation_phrases(char, name, user, topics, location)
    transcription_config = types.AudioTranscriptionConfig(
        language_hints=types.LanguageHints(language_codes=["cmn-Hant-TW"]),
        adaptation_phrases=phrases,
    )
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=system_instruction(char, name, mood, topics, user, location, allow_reminders, fam, memory_scope, allow_events),
        tools=tools,
        output_audio_transcription=transcription_config,
        input_audio_transcription=transcription_config,
        speech_config=types.SpeechConfig(
            language_code="cmn-TW",   # 台灣華語（Edward 2026-07-12：沒設地區→通用華語=馬來腔/「自己」念成jì-jǐ；設 cmn-TW 講台灣腔）
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
        # 聽話靈敏度（Edward 2026-07-10「戶外雜音/旁人聊天被當成我在講」）：
        # 開口判定調「低靈敏」＝要更明確、對著手機講的人聲才算你在說話——背景雜音/遠處聊天不易誤觸、不再亂打斷她；
        # 結束判定同樣用低靈敏；尾端靜音窗 800ms＝長輩講話中間喘口氣不會被急著搶話。
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=300,
                silence_duration_ms=800,
            ),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        ),
    )


async def search_current_information(search_client, query, location=None):
    """Run one bounded, grounded lookup outside the Live session.

    2026-07-16 事故夜實測：gemini-2.5-flash 晚間尖峰整批回 503（客滿）＝「我幫你查一下」
    之後永遠沒下文。改成備胎鏈：主模型客滿/超時/查回來沒有真來源 → 立刻換下一顆；
    gemini-3.1-flash-lite 實測走同一套查詢流程 2-3 秒、帶真來源。每顆模型有自己的時限、
    總預算由 MUNEA_LOOKUP_TIMEOUT_SECONDS 管。"""
    clean_query = live_lookup.normalize_query(query)
    if not clean_query:
        raise ValueError("lookup query is empty")
    models = [m.strip() for m in os.environ.get(
        "MUNEA_LOOKUP_MODEL", "gemini-2.5-flash,gemini-3.1-flash-lite").split(",") if m.strip()]
    per_model_s = float(os.environ.get("MUNEA_LOOKUP_PER_MODEL_SECONDS", "6"))
    last_exc = None
    for model in models:
        try:
            response = await asyncio.wait_for(
                search_client.aio.models.generate_content(
                    model=model,
                    contents=live_lookup.build_request(clean_query, location),
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                    ),
                ),
                timeout=per_model_s,
            )
            return live_lookup.extract_result(response)
        except Exception as exc:
            last_exc = exc
            print(f"[diag] lookup_model_failover model={model} err={type(exc).__name__}:{str(exc)[:60]}", flush=True)
    raise last_exc if last_exc else RuntimeError("lookup_all_models_failed")


def _diag(cid, event, **kv):
    parts = " ".join(f"{k}={v}" for k, v in kv.items())
    print(f"[diag] c{cid} {event} {parts}".rstrip(), flush=True)


_CID = {"n": 0}
_HOKKIEN_FALLBACK_PCM = {}
_LOOKUP_CUE_PCM = {}
# 通話記憶回寫專用池：跟 to_thread 的共用池分開，收線的多秒萃取不排擠 session 建立。
_CALL_MEMORY_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="call-memory")
_VOICE_CUE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="voice-cue")


def _brain_memory_config():
    """Voice→Brain 通話記憶通道設定：(brain 網址, 內部密語)。兩個都設了才啟用；
    沒設就退回 Voice 本機模式（單人測試用、仍受 MUNEA_VOICE_CALL_MEMORY 總開關管）。"""
    url = os.environ.get("MUNEA_BRAIN_INTERNAL_URL", "").strip()
    secret = os.environ.get("MUNEA_VOICE_BRAIN_SECRET", "").strip()
    return (url, secret) if url and secret else (None, None)
_HOKKIEN_FALLBACK_LOCK = threading.Lock()
_LOOKUP_CUE_LOCK = threading.Lock()


def _hokkien_fallback_pcm(char):
    """Generate and cache exact Mandarin-only fallback audio for each companion."""
    cache_key = str(char or "")
    cached = _HOKKIEN_FALLBACK_PCM.get(cache_key)
    if cached is not None:
        return cached
    with _HOKKIEN_FALLBACK_LOCK:
        cached = _HOKKIEN_FALLBACK_PCM.get(cache_key)
        if cached is not None:
            return cached
        encoded = server.tts_b64(localization.TAIWANESE_HOKKIEN_FALLBACK, char, "zh-TW")
        if not encoded:
            _HOKKIEN_FALLBACK_PCM[cache_key] = b""
            return b""
        with wave.open(io.BytesIO(base64.b64decode(encoded)), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 24000:
                raise ValueError("unexpected Hokkien fallback audio format")
            pcm = wav.readframes(wav.getnframes())
        _HOKKIEN_FALLBACK_PCM[cache_key] = pcm
        return pcm


LOOKUP_WAIT_TEXT = "還在幫你找喔，再等我一下。"
_LOOKUP_WAIT_PCM = {}


def _lookup_wait_pcm(char):
    """查詢超過幾秒還沒回來時的安撫短句（每角色生成一次、之後用快取）。"""
    cache_key = str(char or "")
    cached = _LOOKUP_WAIT_PCM.get(cache_key)
    if cached is not None:
        return cached
    with _LOOKUP_CUE_LOCK:
        cached = _LOOKUP_WAIT_PCM.get(cache_key)
        if cached is not None:
            return cached
        same_voice = _gemini_tts_pcm(LOOKUP_WAIT_TEXT, char)
        if same_voice:
            _LOOKUP_WAIT_PCM[cache_key] = same_voice
            return same_voice
        encoded = server.tts_b64(LOOKUP_WAIT_TEXT, char, "zh-TW")
        if not encoded:
            _LOOKUP_WAIT_PCM[cache_key] = b""
            return b""
        with wave.open(io.BytesIO(base64.b64decode(encoded)), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 24000:
                raise ValueError("unexpected lookup wait audio format")
            pcm = wav.readframes(wav.getnframes())
        _LOOKUP_WAIT_PCM[cache_key] = pcm
        return pcm


def _char_voice_name(char):
    try:
        c = eng.CHARS.get(char) or eng.CHARS["寧寧"]
        return c.get("voice") or "Leda"
    except Exception:
        return "Leda"


def _gemini_tts_pcm(text, char):
    """用她本人的聲線唸一句話（同 voice_name 的官方配音通道 · 7/16 實測 24kHz 原生同規格）。
    失敗回空 bytes、呼叫端自動退回舊配音——聲線一致是體驗、不是可用性前提。"""
    try:
        _, cli = _pick_client()
        r = cli.models.generate_content(
            model=os.environ.get("MUNEA_CUE_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=_char_voice_name(char)))),
            ),
        )
        part = r.candidates[0].content.parts[0]
        blob = getattr(part, "inline_data", None)
        data = getattr(blob, "data", b"") or b""
        mime = str(getattr(blob, "mime_type", "") or "")
        if isinstance(data, str):
            data = base64.b64decode(data)
        if data and "rate=24000" in mime:
            return bytes(data)
        return b""
    except Exception:
        return b""


def _lookup_cue_pcm(char):
    """Generate once per companion so a lookup can acknowledge before network I/O."""
    cache_key = str(char or "")
    cached = _LOOKUP_CUE_PCM.get(cache_key)
    if cached is not None:
        return cached
    with _LOOKUP_CUE_LOCK:
        cached = _LOOKUP_CUE_PCM.get(cache_key)
        if cached is not None:
            return cached
        same_voice = _gemini_tts_pcm(live_lookup.CUE_TEXT, char)
        if same_voice:
            _LOOKUP_CUE_PCM[cache_key] = same_voice
            return same_voice
        encoded = server.tts_b64(live_lookup.CUE_TEXT, char, "zh-TW")
        if not encoded:
            _LOOKUP_CUE_PCM[cache_key] = b""
            return b""
        with wave.open(io.BytesIO(base64.b64decode(encoded)), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 24000:
                raise ValueError("unexpected lookup cue audio format")
            pcm = wav.readframes(wav.getnframes())
        _LOOKUP_CUE_PCM[cache_key] = pcm
        return pcm


async def handle(ws):
    char = "寧寧"
    # 從連線網址讀使用者改過的名字（?name=新名字），讓 AI 知道自己現在叫什麼
    name = None
    mood = None
    topics = None
    user = None
    location = None
    allow_reminders = False   # 只有帶 ?cap_rem=1 的新版 App 才開放「幫你設提醒」工具（防舊版假成功）
    allow_events = False      # 只有帶 ?cap_evt=1 的新版 App 才開放「幫你記行程」工具（2026-07-16）
    fam = 0                   # 熟識度（聊過幾通）：0=第一次見面；越大開場越簡短（Edward 2026-07-10）
    day_call = None           # 當日第幾通（0-based）：只負責開場路線去重，不改變關係熟識度
    gate_key = ""   # Legacy 1.0.1 transition only.
    call_token = ""
    call_payload = {}
    call_release_reason = ""
    _q = {}
    try:
        from urllib.parse import urlparse, parse_qs
        path = getattr(getattr(ws, "request", None), "path", None) or getattr(ws, "path", "") or ""
        _q = parse_qs(urlparse(path).query)
    except Exception:
        pass

    call_token = (_q.get("token") or [""])[0].strip()
    control_required = os.environ.get("MUNEA_CALL_CONTROL_REQUIRED", "0") == "1"
    if call_token or control_required:
        if not call_token:
            try:
                await ws.close(code=4403, reason="call token required")
            except Exception:
                pass
            return
        try:
            token_secret = os.environ.get("MUNEA_CALL_TOKEN_SECRET", "").strip()
            voice_shard_id = os.environ.get("MUNEA_VOICE_SHARD_ID", "").strip()
            call_payload = verify_call_token(call_token, token_secret, voice_shard_id=voice_shard_id)
        except Exception:
            try:
                await ws.close(code=4403, reason="invalid call token")
            except Exception:
                pass
            return

    try:
        # 薄門（正式上線 · 7/9 Edward 拍板）：環境設了 MUNEA_APP_KEY 就要對通行碼（?key=）。
        # App 自動帶、用戶無感；擋的是「拿到網址直接來撥」的陌生流量。本機沒設＝不啟用、行為不變。
        _gate = os.environ.get("MUNEA_APP_KEY", "").strip()
        gate_key = _gate   # 存起來給「聲音直接送去雲端臉」那條 server-to-server 連線用（同一把薄門鑰匙）
        if _gate and not call_payload:
            kvals = _q.get("key")
            if not kvals or kvals[0] != _gate:
                try:
                    await ws.close(code=4403, reason="key required")
                except Exception:
                    pass
                return
        vals = _q.get("name")
        if vals:
            name = vals[0]
        mvals = _q.get("mood")
        if mvals:
            mood = mvals[0]
        # ?char=咪咪：切換角色模板（人格＋聲音都跟 characters.json 走）；沒帶或帶錯就維持寧寧
        cvals = _q.get("char")
        if cvals and cvals[0] in eng.CHARS:
            char = cvals[0]
        # ?topics=旅遊景點,美食餐廳：用戶挑的興趣話題 → 開場方向＋接話素材（最多收 8 個、防亂塞）
        tvals = _q.get("topics")
        if tvals:
            topics = [t.strip() for t in tvals[0].split(",") if t.strip()][:8] or None
        # ?user=爸爸：個人資料的「家人稱呼／名稱」→ AI 對他的稱呼（優先於舊資料 · 7/9）
        uvals = _q.get("user")
        if uvals and uvals[0].strip():
            user = uvals[0].strip()[:12]
        # ?loc=台北市大安區：所在地（可到區）→ 在地餐廳/景點/話題定位（7/9 Edward）
        lvals = _q.get("loc")
        if lvals and lvals[0].strip():
            location = lvals[0].strip()[:24]
        # ?cap_rem=1：這版 App 接得住「AI 幫你設提醒」→ 才給設提醒工具（能力握手 · 2026-07-09 Edward）
        if _q.get("cap_rem") == ["1"]:
            allow_reminders = True
        # ?cap_evt=1：這版 App 接得住「AI 幫你記行程」→ 才給記行程工具（能力握手 · 2026-07-16 Edward「約吃飯被設成看診」）
        if _q.get("cap_evt") == ["1"]:
            allow_events = True
        # ?fam=N：聊過幾通（熟識度）→ 決定開場話量：越熟話越少（Edward 2026-07-10「隨熟識度思考語句量」）
        fvals = _q.get("fam")
        if fvals:
            try:
                fam = max(0, min(999, int(fvals[0])))
            except Exception:
                pass
        dvals = _q.get("day_call")
        if dvals:
            try:
                day_call = max(0, min(99, int(dvals[0])))
            except Exception:
                pass
    except Exception:
        pass
    _CID["n"] += 1
    cid = _CID["n"]
    t0 = time.monotonic()
    st = {"in": 0, "out": 0, "last_in": None, "last_out": None, "echo_dropped": 0, "await_first": True, "first_mic": False,
          "face_ws": None, "face_audio_url": None,   # 方案 B：聲音直接轉送去雲端臉的 server-to-server 連線狀態
          "user_buf": "", "ai_buf": "", "user_flagged": set(), "ai_flagged": set(),
          "pending_cues": [], "bg_tasks": [], "semantic_calls": 0,
          "action_results": {}, "relay_greet_id": None,
          "language_block": False, "language_block_source": None,
          "blocked_output_text": "", "language_retry_count": 0,
          "client_barge_in": False, "asr_turns": 0, "asr_chars": 0,
          "barge_in_count": 0, "language_block_count": 0,
          "greet_requested": False, "opening_voice_detected": False,
          "opening_window_complete": False,
          "user_turn_started_at": None,
          "lookup_count": 0, "lookup_sources": 0, "lookup_failures": 0,
          "lookup_requested_at": None, "lookup_result_at": None,
          "lookup_waiting_answer": False, "lookup_cue_task": None,
          "lookup_cue_at": 0.0, "lookup_fail_streak": 0, "lookup_block_until": 0.0,
          "call_turns": []}   # 守護腦接回語音線：字幕滾動視窗／這輪已處置類別／排隊中的安全導引／背景任務集／第二層 AI 判讀次數（每通上限）；call_turns＝整通逐輪字幕，收線時交聊後管線寫記憶
    _diag(cid, "connected", name=name or "-", char=char)
    _key_idx = None   # 多鑰匙分流：這通用哪把鑰匙（收線時據此把空位還回去）
    # 通話記憶的人別隔離鍵：Gateway 正式路徑的 call token 帶已驗證的 user_id；
    # 開發包直連沒 token → None（server 端落回主要照護對象）。收線回寫與開場接續共用同一 scope。
    memory_scope = None
    if call_payload and call_payload.get("user_id"):
        memory_scope = f"voice-{call_payload['user_id']}"
    try:
        # Start before the Live handshake. In normal calls the fixed spoken cue
        # is cached by the time the user can ask the first lookup question.
        lookup_cue_future = asyncio.get_running_loop().run_in_executor(
            _VOICE_CUE_EXECUTOR, _lookup_cue_pcm, char)
        st["lookup_cue_task"] = lookup_cue_future
        # 組 config 會呼叫 build_reply_context（內含對 Supabase 的同步阻塞查詢，最多 4 秒）——
        # 丟到背景執行緒，別卡住整條 async 事件主幹道、拖垮所有通話中的人（2026-07-12 卡西法壓測抓到 10 人斷崖真兇）
        cfg = await asyncio.to_thread(live_config, char, name, mood, topics, user, location, allow_reminders, fam, memory_scope, allow_events)
        asr_context_terms = [char, name, user, location, *(topics or [])]
        _key_idx, _cli = _pick_client()   # 挑現在最閒的一把鑰匙開這通（多鑰匙分流的核心）
        async with _cli.aio.live.connect(model=MODEL, config=cfg) as session:
            # 腦真正接上了才跟瀏覽器說 ready——治「第一句沒回應」：
            # 以前瀏覽器一開線就送聲音，但這裡開 Gemini session 要 1~3 秒，
            # 那段聲音會先塞在門口、開門後一口氣灌進去，AI 的斷句判斷就亂了。
            if call_payload:
                ready_result = await asyncio.to_thread(
                    post_internal,
                    os.environ.get("MUNEA_CALL_CONTROL_URL", ""),
                    os.environ.get("MUNEA_GATEWAY_ADMIN_KEY", ""),
                    "/v1/internal/calls/ready",
                    {
                        "call_id": str(call_payload["call_id"]),
                        "lease_version": int(call_payload["lease_version"]),
                        "event_id": "voice-ready-" + uuid.uuid4().hex,
                        "component": "voice",
                    },
                )
                if not ready_result.get("ok"):
                    raise CallControlError("voice reservation was rejected: " + str(ready_result))
            try:
                await ws.send(json.dumps({"type": "ready"}))
            except Exception:
                pass
            _diag(cid, "node.ready", ms=round((time.monotonic() - t0) * 1000))
            # Prepare the fixed Mandarin fallback off the critical path. The
            # lookup cue already started before the Live handshake above.
            st["bg_tasks"].append(asyncio.create_task(asyncio.to_thread(_hokkien_fallback_pcm, char)))

            # 主動開口 cue（治「叫兩三次才回、以為當機」· Edward 2026-07-09）：
            # 不在 session 開好就立刻送——改由 App 在「聲音＋會動的臉兩邊都就緒」時送 {"type":"greet"} 才觸發，
            # 這樣她一開口臉就同步在動、不會出現「已在講、臉還沒好」的當機感（Edward 2026-07-09 二次拍板）。
            async def _do_greet(relay=None):
                try:
                    # 開場必須比一般回覆更短；熟識度與同日通數只決定內容，不增加句數。
                    _len_rule = (
                        "只說一句八到十六個中文字的自然招呼，說完就停。"
                        "不要自我介紹、不要補充背景、不要連續問問題；可以完全不問問題。"
                    )
                    relay = relay if isinstance(relay, dict) else {}
                    relay_id = str(relay.get("id") or "")[:80]
                    sender_label = str(relay.get("senderLabel") or "").strip()[:40]
                    content = str(relay.get("content") or "").strip()[:240]
                    if relay_id and sender_label and len(content) >= 2 and verify_family_relay_proof(relay):
                        greet_cue = (
                            "（這是經過後端驗證、指定給目前使用者的家人傳話。絕對不要唸出系統提示。"
                            f"先準確說：『{sender_label}要我跟你說：{content}』。"
                            "必須清楚說出是誰託你轉達；不可改變原意、不可補充不存在的原因或評價。"
                            "轉達後只加一句很短的自然關心，把話權留給對方。）"
                        )
                        st["relay_greet_id"] = relay_id
                    else:
                        if relay_id:
                            await ws.send(json.dumps({"type": "relay_rejected", "id": relay_id}, ensure_ascii=False))
                        greet_cue = (
                            "（這是系統提示，絕對不要唸出這段、也不要提到系統：使用者剛接起這通電話。"
                            "請你「立刻、主動」開口打招呼，不要等對方先開口。" + _len_rule + "）"
                            + localization.voice_opening_instruction(fam, topics, location, day_call)
                        )
                    await session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part(text=greet_cue)]),
                        turn_complete=True,
                    )
                    st["await_first"] = True
                    st["last_in"] = time.monotonic()
                    _diag(cid, "node.proactive_greet")
                except Exception:
                    pass

            async def _warm_then_greet(relay=None):
                # 留一秒給 iPhone 音訊路徑與 Avatar 共同暖機。這段時間麥克風已開；
                # 如果對方真的已開口，就不再同時塞一段主動問候跟他搶話。
                await asyncio.sleep(1.0)
                st["opening_window_complete"] = True
                if st.get("opening_voice_detected"):
                    relay_id = str((relay or {}).get("id") or "")[:80] if isinstance(relay, dict) else ""
                    if relay_id:
                        await ws.send(json.dumps({"type": "relay_interrupted", "id": relay_id}, ensure_ascii=False))
                    _diag(cid, "node.proactive_greet_skipped", reason="user_spoke_during_warmup")
                    return
                await _do_greet(relay)

            # 省點提醒（Edward 2026-07-10）：通話開著但使用者一直沒講話 → 寧寧兩段式溫柔提醒、避免忘了關一直計費。
            # 語氣＝關心、不催不罵、不提「點數/系統」。level 1=關心還在嗎；level 2=提醒記得關通話。
            async def _do_nudge(level):
                try:
                    if level >= 2:
                        cue = (
                            "（系統提示，絕對不要唸出這段、也不要提到系統或點數：使用者還是沒說話。"
                            "請你用一句溫柔體貼的話提醒他——如果先去忙也沒關係，記得把我們的通話關掉喔，"
                            "不然會一直開著；想聊隨時再找你就好。語氣是關心、不是催促。）"
                        )
                    else:
                        cue = (
                            "（系統提示，絕對不要唸出這段、也不要提到系統或點數：使用者已經一小段沒說話了。"
                            "請你用一句溫柔、簡短、關心的話，輕輕問他是不是忙別的去了、你還在這裡陪他，"
                            "像老朋友那樣。不要責備、不要唸清單。）"
                        )
                    await session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part(text=cue)]),
                        turn_complete=True,
                    )
                    st["await_first"] = True
                    st["last_in"] = time.monotonic()
                    _diag(cid, "node.idle_nudge", level=level)
                except Exception:
                    pass

            async def _face_audio_close(w):
                # 背景關線，不擋主流程（送/收聲音永遠優先，關雲端臉連線失敗也不能拖累通話）
                try:
                    await w.close()
                except Exception:
                    pass

            async def _face_audio_off():
                fw = st.get("face_ws")
                st["face_ws"] = None
                st["face_audio_url"] = None
                if fw:
                    asyncio.create_task(_face_audio_close(fw))
                    _diag(cid, "node.faceaudio_off")

            async def _face_audio_on(url, session_id="", token=""):
                # App 說「聲音直接幫我送去雲端臉」（方案 B · 2026-07-10）：這裡開一條 server-to-server WS 去 Modal 的
                # /audio，之後 Gemini 吐回來的聲音同一份 byte 也送這條線——不必再繞手機行動網路上行一趟。
                # 連不上/斷了都不能拖累語音對話：任何失敗都吞掉，對話照常，只是臉那次不會動（等下一次 on 訊息重試）。
                url = (url or "").strip().rstrip("/")
                if not url:
                    return
                if st.get("face_ws") is not None and st.get("face_audio_url") == url:
                    return   # 同一顆網址已經開著，不重連（避免重複 on 事件疊連線）
                await _face_audio_off()   # 先收掉舊的（網址換了，或上一輪殘留）
                try:
                    ws_url = url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
                    query = {"session": session_id}
                    if token:
                        query["token"] = token
                    else:
                        query["key"] = gate_key
                    ws_url += "/audio?" + urlencode(query)
                    fw = await websockets.connect(ws_url, max_size=None, open_timeout=5)
                    st["face_ws"] = fw
                    st["face_audio_url"] = url
                    _diag(cid, "node.faceaudio_on", url=url)
                except Exception as e:
                    st["face_ws"] = None
                    st["face_audio_url"] = None
                    _diag(cid, "node.faceaudio_err", err=f"{type(e).__name__}:{str(e)[:60]}")

            async def _forward_audio(chunk):
                if not chunk:
                    return
                st["out"] += len(chunk)
                st["last_out"] = time.monotonic()
                await ws.send(chunk)
                fw = st.get("face_ws")
                if fw is not None:
                    try:
                        await fw.send(chunk)
                    except Exception:
                        st["face_ws"] = None

            async def _mark_first_audio(source):
                if not st.get("await_first") or st.get("last_in") is None:
                    return
                latency_ms = round((time.monotonic() - st["last_in"]) * 1000)
                st["await_first"] = False
                _diag(cid, "node.first_audio", latency_ms=latency_ms, source=source)
                try:
                    await ws.send(json.dumps({"type": "diag", "firstAudioMs": latency_ms}))
                except Exception:
                    pass

            async def _send_lookup_cue():
                cue_started = time.monotonic()
                await ws.send(json.dumps({
                    "type": "caption", "who": "nening", "text": live_lookup.CUE_TEXT,
                }, ensure_ascii=False))
                try:
                    cue_task = st.get("lookup_cue_task")
                    pcm = await cue_task if cue_task is not None else await asyncio.get_running_loop().run_in_executor(
                        _VOICE_CUE_EXECUTOR, _lookup_cue_pcm, char)
                except Exception as exc:
                    pcm = b""
                    _diag(cid, "node.lookup_cue_failed", err=f"{type(exc).__name__}:{str(exc)[:60]}")
                first_chunk = True
                for offset in range(0, len(pcm), 4800):
                    await _forward_audio(pcm[offset:offset + 4800])
                    if first_chunk:
                        first_chunk = False
                        await _mark_first_audio("lookup_cue")
                    else:
                        # 跟上說話速度慢慢送（0.1 秒的音、隔 0.08 秒送下一塊）：
                        # 一口氣灌爆會把同線的臉部聲畫節拍打亂＝Edward 聽到的「這句很卡」。
                        await asyncio.sleep(0.08)
                if pcm:
                    await _forward_audio(LOOKUP_CUE_TAIL_PCM)
                _diag(
                    cid, "node.lookup_cue_sent", audio=bool(pcm), out_bytes=len(pcm),
                    latency_ms=round((time.monotonic() - cue_started) * 1000),
                )
                return bool(pcm)

            async def _run_live_lookup(fargs, cue_already_spoken=False):
                query = live_lookup.normalize_query((fargs or {}).get("query"))
                lookup_location = str((fargs or {}).get("location") or location or "").strip()[:80]
                st["lookup_count"] += 1
                st["lookup_requested_at"] = time.monotonic()
                asr_started = st.get("user_turn_started_at")
                _diag(
                    cid, "node.lookup_requested", query_chars=len(query),
                    has_location=bool(lookup_location),
                    asr_to_lookup_ms=(round((st["lookup_requested_at"] - asr_started) * 1000)
                                      if asr_started else 0),
                )
                if not query:
                    st["lookup_failures"] += 1
                    st["lookup_result_at"] = time.monotonic()
                    st["lookup_waiting_answer"] = True
                    _diag(cid, "node.lookup_failed", reason="empty_query", latency_ms=0)
                    return {"status": "error", "error": "lookup_query_empty"}

                # 重試斷路器（7/16 深夜「一直重複我幫你查一下」事故）：查詢一直失敗時，
                # 模型會自動重試工具、每次重試又念一次過場句＝每 8 秒折磨一輪。
                # 連兩敗 → 120 秒冷卻：不查、不念、直接叫模型認錯收尾。
                _lk_now = time.monotonic()
                if st.get("lookup_block_until", 0) > _lk_now:
                    _diag(cid, "node.lookup_suppressed", cooldown_s=round(st["lookup_block_until"] - _lk_now))
                    return {
                        "status": "error", "error": "lookup_unavailable",
                        "instruction": "查詢服務暫時沒有回應。請直接用一句話跟用戶說現在查不到、"
                                       "建議晚點再問，然後繼續原本的聊天。不要再呼叫查詢工具。",
                    }

                if cue_already_spoken:
                    cue_audio = True
                    _diag(cid, "node.lookup_cue_sent", audio="model", out_bytes=0, latency_ms=0)
                elif _lk_now - st.get("lookup_cue_at", 0) < 30:
                    # 過場句 30 秒內不重播（重試時默默查、不再「我幫你查一下」轟炸）
                    cue_audio = False
                    _diag(cid, "node.lookup_cue_skipped", reason="recently_played")
                else:
                    st["lookup_cue_at"] = _lk_now
                    cue_audio = await _send_lookup_cue()
                network_started = time.monotonic()
                _diag(cid, "node.lookup_started", cue_audio=cue_audio)

                async def _send_wait_cue():
                    # 查太久（備胎鏈換手時）不讓長輩對著沉默等：5.5 秒還沒回來就先安撫一句
                    await asyncio.sleep(5.5)
                    try:
                        pcm = await asyncio.get_running_loop().run_in_executor(
                            _VOICE_CUE_EXECUTOR, _lookup_wait_pcm, char)
                    except Exception:
                        pcm = b""
                    if not pcm:
                        return
                    await ws.send(json.dumps({
                        "type": "caption", "who": "nening", "text": LOOKUP_WAIT_TEXT,
                    }, ensure_ascii=False))
                    first = True
                    for offset in range(0, len(pcm), 4800):
                        await _forward_audio(pcm[offset:offset + 4800])
                        if first:
                            first = False
                        else:
                            await asyncio.sleep(0.08)
                    _diag(cid, "node.lookup_wait_cue_sent", out_bytes=len(pcm))

                wait_cue_task = asyncio.create_task(_send_wait_cue())
                st["bg_tasks"].append(wait_cue_task)
                try:
                    result = await asyncio.wait_for(
                        search_current_information(_cli, query, lookup_location),
                        timeout=float(os.environ.get("MUNEA_LOOKUP_TIMEOUT_SECONDS", "13")),
                    )
                except asyncio.TimeoutError:
                    st["lookup_failures"] += 1
                    st["lookup_result_at"] = time.monotonic()
                    st["lookup_waiting_answer"] = True
                    _diag(
                        cid, "node.lookup_failed", reason="timeout",
                        latency_ms=round((time.monotonic() - network_started) * 1000),
                    )
                    st["lookup_fail_streak"] = st.get("lookup_fail_streak", 0) + 1
                    if st["lookup_fail_streak"] >= 2:
                        st["lookup_block_until"] = time.monotonic() + 120
                    return {
                        "status": "error", "error": "lookup_timeout",
                        "instruction": "查詢沒有回應。請用一句話跟用戶說現在查不到、之後再幫忙看，"
                                       "除非用戶再次主動要求，不要再呼叫查詢工具。",
                    }
                except Exception as exc:
                    st["lookup_failures"] += 1
                    st["lookup_result_at"] = time.monotonic()
                    st["lookup_waiting_answer"] = True
                    _diag(
                        cid, "node.lookup_failed", reason=type(exc).__name__,
                        latency_ms=round((time.monotonic() - network_started) * 1000),
                    )
                    st["lookup_fail_streak"] = st.get("lookup_fail_streak", 0) + 1
                    if st["lookup_fail_streak"] >= 2:
                        st["lookup_block_until"] = time.monotonic() + 120
                    return {
                        "status": "error", "error": "lookup_failed",
                        "instruction": "查詢出了點狀況。請用一句話跟用戶說現在查不到、之後再幫忙看，"
                                       "除非用戶再次主動要求，不要再呼叫查詢工具。",
                    }
                finally:
                    # 查詢一有結果（成功或失敗）就取消「還在找」安撫句——別讓它插在答案中間
                    wait_cue_task.cancel()

                st["lookup_fail_streak"] = 0
                st["lookup_block_until"] = 0.0
                st["lookup_sources"] += result["sources"]
                st["lookup_result_at"] = time.monotonic()
                st["lookup_waiting_answer"] = True
                _diag(
                    cid, "node.lookup_done", sources=result["sources"],
                    result_chars=len(result["text"]),
                    latency_ms=round((st["lookup_result_at"] - network_started) * 1000),
                )
                return {
                    "status": "ok",
                    "answerMaterial": result["text"],
                    "sourceCount": result["sources"],
                }

            async def _send_turn_tail():
                await _forward_audio(TURN_END_SILENCE_PCM)
                _diag(cid, "node.turn_tail", ms=TURN_END_SILENCE_MS)

            async def _send_hokkien_fallback(source):
                """Bypass the conversational model and speak one fixed Mandarin sentence."""
                caption = localization.TAIWANESE_HOKKIEN_FALLBACK
                await ws.send(json.dumps({"type": "caption", "who": "nening", "text": caption}))
                try:
                    pcm = await asyncio.to_thread(_hokkien_fallback_pcm, char)
                except Exception as e:
                    pcm = b""
                    _diag(cid, "node.language_fallback_tts_err", err=f"{type(e).__name__}:{str(e)[:60]}")
                if pcm:
                    for offset in range(0, len(pcm), 4800):
                        chunk = pcm[offset:offset + 4800]
                        await _forward_audio(chunk)
                        await asyncio.sleep(0)
                    await _send_turn_tail()
                await ws.send(json.dumps({"type": "turn_complete"}))
                _diag(cid, "node.language_fallback", source=source, out_bytes=len(pcm))

            async def _send_safe_mandarin_tts(text, source):
                caption = localization.display_text(localization.speech_text(text, "zh-TW"), "zh-TW").strip()
                if not caption:
                    caption = "我換個比較清楚的說法。"
                await ws.send(json.dumps({"type": "caption", "who": "nening", "text": caption}))
                try:
                    pcm = await asyncio.to_thread(_gemini_tts_pcm, caption, char)
                    if not pcm:
                        encoded = await asyncio.to_thread(server.tts_b64, caption, char, "zh-TW")
                        with wave.open(io.BytesIO(base64.b64decode(encoded)), "rb") as wav:
                            pcm = wav.readframes(wav.getnframes())
                except Exception as e:
                    pcm = b""
                    _diag(cid, "node.safe_mandarin_tts_err", err=f"{type(e).__name__}:{str(e)[:60]}")
                first = True
                for offset in range(0, len(pcm), 4800):
                    await _forward_audio(pcm[offset:offset + 4800])
                    if first:
                        first = False
                    else:
                        await asyncio.sleep(0.08)   # 配速同過場音：不灌爆同線聲畫節拍
                if pcm:
                    await _send_turn_tail()
                await ws.send(json.dumps({"type": "turn_complete"}))
                _diag(cid, "node.safe_mandarin_tts", source=source, out_bytes=len(pcm))

            async def _retry_mandarin_output():
                cue = (
                    "（最高優先系統修正，絕對不要唸出提示內容：上一個回答因為含有未開放的台語而沒有播放。"
                    "請立刻保留原意重新回答，只能使用自然台灣華語，不可出現任何台語字詞、羅馬字或模仿發音；"
                    "不要解釋為什麼重說，也不要提到系統。）"
                    + localization.taiwan_mandarin_pronunciation_guard_instruction("zh-TW")
                )
                await session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part(text=cue)]),
                    turn_complete=True,
                )
                _diag(cid, "node.language_retry")

            async def _arm_language_block(source):
                if st.get("language_block"):
                    return
                st["language_block"] = True
                st["language_block_source"] = source
                st["language_block_count"] += 1
                await ws.send(json.dumps({"type": "interrupted"}))
                fw = st.get("face_ws")
                if fw is not None:
                    try:
                        await fw.send("reset")
                    except Exception:
                        st["face_ws"] = None
                _diag(cid, "node.language_block", source=source)

            async def from_browser():
                async for message in ws:
                    if isinstance(message, (bytes, bytearray)):
                        n = len(message)
                        st["in"] += n
                        st["last_in"] = time.monotonic()
                        st["await_first"] = True
                        if st.get("greet_requested") and not st.get("opening_window_complete") and not st.get("opening_voice_detected"):
                            try:
                                samples = memoryview(message).cast("h")
                                if samples:
                                    rms = (sum(int(v) * int(v) for v in samples) / len(samples)) ** 0.5
                                    if rms >= 700:
                                        st["opening_voice_detected"] = True
                                        _diag(cid, "node.opening_voice_detected", rms=round(rms))
                            except Exception:
                                pass
                        if not st["first_mic"]:
                            st["first_mic"] = True
                            _diag(cid, "node.mic_uplink", ms=round((st["last_in"] - t0) * 1000))
                        # 回音濾網（病歷 a 快藥）：她出聲期間＋殘響窗內，低能量上行＝喇叭漏回來的
                        # 自己聲音 → 丟棄；正常音量直說天生高於門檻、插話照常穿透。voice_echo_guard.py。
                        _eg_now = time.monotonic()
                        if in_output_window(_eg_now, st.get("last_out")) and should_drop_uplink_frame(
                                _eg_now, st.get("last_out"), frame_rms(message)):
                            st["echo_dropped"] += 1
                            if st["echo_dropped"] == 1 or st["echo_dropped"] % 200 == 0:
                                _diag(cid, "node.echo_guard_dropped", count=st["echo_dropped"])
                            continue
                        await session.send_realtime_input(
                            audio=types.Blob(data=bytes(message), mime_type="audio/pcm;rate=16000")
                        )
                    else:
                        try:
                            obj = json.loads(message)
                        except Exception:
                            continue
                        t = obj.get("type")
                        if t == "greet":
                            # App 原本等第一個 AI 音訊封包才開麥，模型稍慢時會吃掉
                            # 使用者前幾句 Hello。先用既有事件解除收音門檻；接著生成的
                            # 招呼仍可被正常插話，不新增 App 協定也不碰正在施工的 app.js。
                            if st.get("greet_requested"):
                                _diag(cid, "node.proactive_greet_ignored", reason="duplicate_request")
                                continue
                            st["greet_requested"] = True
                            await ws.send(json.dumps({"type": "turn_complete", "phase": "greet_input_ready"}))
                            greet_task = asyncio.create_task(_warm_then_greet(obj.get("relay")))
                            st["bg_tasks"].append(greet_task)
                        elif t == "action_result":
                            action_id = str(obj.get("id") or "")
                            pending = st["action_results"].get(action_id)
                            if pending and not pending.done():
                                pending.set_result(obj)
                        elif t == "nudge":
                            await _do_nudge(int(obj.get("level", 1)))   # App 偵測到使用者一直沒講話 → 寧寧溫柔提醒（省點）
                        elif t == "text" and obj.get("text"):
                            st["last_in"] = time.monotonic()
                            st["await_first"] = True
                            if localization.requires_taiwanese_hokkien_fallback(obj["text"]):
                                await _send_hokkien_fallback("text_input")
                            else:
                                await session.send_client_content(
                                    turns=types.Content(role="user", parts=[types.Part(text=obj["text"])]),
                                    turn_complete=True,
                                )
                        elif t == "audio_end":
                            await session.send_realtime_input(audio_stream_end=True)
                        elif t == "barge_in":
                            st["client_barge_in"] = True
                            st["barge_in_count"] += 1
                            await ws.send(json.dumps({"type": "barge_in_ack"}))
                            fw = st.get("face_ws")
                            if fw is not None:
                                try:
                                    await fw.send("reset")
                                except Exception:
                                    st["face_ws"] = None
                            _diag(cid, "node.client_barge_in")
                        elif t == "faceaudio":
                            # {"type":"faceaudio","on":true,"url":"..."} 開＝伺服器對伺服器直送雲端臉；on:false 或掛斷＝收線
                            if obj.get("on"):
                                await _face_audio_on(
                                    obj.get("url") or "",
                                    obj.get("session") or "",
                                    obj.get("token") or call_token,
                                )
                            else:
                                await _face_audio_off()

            async def from_live():
                # session.receive() 每輪結束就收（SDK 行為）；外層 while 讓「一輪接完再等下一輪」＝多輪對話不斷
                while True:
                    turn_out = 0
                    got = False
                    async for msg in session.receive():
                        got = True
                        sc = getattr(msg, "server_content", None)
                        if sc:
                            it_pre = getattr(sc, "input_transcription", None)
                            if it_pre and getattr(it_pre, "text", None):
                                if st.get("user_turn_started_at") is None:
                                    st["user_turn_started_at"] = time.monotonic()
                                transcript = localization.reconcile_context_transcription(
                                    it_pre.text, asr_context_terms, "zh-TW"
                                )
                                st["asr_turns"] += 1
                                st["asr_chars"] += len(transcript)
                                if st.get("client_barge_in"):
                                    st["client_barge_in"] = False
                                    _diag(cid, "node.client_barge_in_heard")
                                is_hokkien = localization.requires_taiwanese_hokkien_fallback(transcript)
                                _diag(cid, "node.asr_input", chars=len(transcript), language_block=is_hokkien)
                                if is_hokkien:
                                    await _arm_language_block("audio_input")
                            ot_pre = getattr(sc, "output_transcription", None)
                            if ot_pre and getattr(ot_pre, "text", None):
                                output_text = localization.canonicalize_transcription(ot_pre.text, "zh-TW")
                                st["blocked_output_text"] = (st["blocked_output_text"] + output_text)[-600:]
                                if localization.looks_like_taiwanese_hokkien(output_text):
                                    await _arm_language_block("model_output")
                                elif localization.contains_unstable_mandarin_speech(output_text):
                                    await _arm_language_block("mandarin_pronunciation")
                        data = getattr(msg, "data", None)
                        if data and not st.get("language_block") and not st.get("client_barge_in"):
                            await _mark_first_audio("model")
                            if st.get("lookup_waiting_answer"):
                                now = time.monotonic()
                                requested_at = st.get("lookup_requested_at") or now
                                result_at = st.get("lookup_result_at") or now
                                _diag(
                                    cid, "node.lookup_answer_audio",
                                    total_ms=round((now - requested_at) * 1000),
                                    after_result_ms=round((now - result_at) * 1000),
                                )
                                st["lookup_waiting_answer"] = False
                            st["out"] += len(data)
                            turn_out += len(data)
                            st["last_out"] = time.monotonic()
                            await ws.send(data)
                            fw = st.get("face_ws")
                            if fw is not None:
                                try:
                                    await fw.send(data)   # 同一份聲音 bytes，server-to-server 直送雲端臉（方案 B）
                                except Exception as e:
                                    st["face_ws"] = None
                                    _diag(cid, "node.faceaudio_send_err", err=str(e)[:60])
                        elif data:
                            reason = "language" if st.get("language_block") else "barge_in"
                            _diag(cid, "node.audio_suppressed", reason=reason, out_bytes=len(data))
                        if sc:
                            ot = getattr(sc, "output_transcription", None)
                            if ot and getattr(ot, "text", None):
                                caption_text = localization.display_text(ot.text, "zh-TW")
                                if not st.get("language_block") and not st.get("client_barge_in"):
                                    await ws.send(json.dumps({"type": "caption", "who": "nening", "text": caption_text}))
                                    st["ai_buf"] = (st["ai_buf"] + caption_text)[-200:]
                                    st["bg_tasks"].append(asyncio.create_task(guardian_watch(cid, "ai", st["ai_buf"], st, session)))
                            it = getattr(sc, "input_transcription", None)
                            if it and getattr(it, "text", None):
                                user_text = localization.reconcile_context_transcription(
                                    it.text, asr_context_terms, "zh-TW"
                                )
                                await ws.send(json.dumps({"type": "caption", "who": "user", "text": user_text}))
                                st["user_buf"] = (st["user_buf"] + user_text)[-200:]
                                st["bg_tasks"].append(asyncio.create_task(guardian_watch(cid, "user", st["user_buf"], st, session)))
                            if getattr(sc, "interrupted", False) and not st.get("language_block"):
                                _diag(cid, "node.interrupted")
                                await ws.send(json.dumps({"type": "interrupted"}))
                                fw = st.get("face_ws")
                                if fw is not None:
                                    try:
                                        await fw.send("reset")   # 插話：雲端臉也停下舊句、回待機（伺服器直接送，不等瀏覽器繞一圈）
                                    except Exception:
                                        st["face_ws"] = None
                            if getattr(sc, "turn_complete", False):
                                ms = round(turn_out / (24000 * 2) * 1000)
                                _diag(cid, "node.turn_done", out_bytes=turn_out, audio_ms=ms)
                                barge_cancelled = bool(st.get("client_barge_in"))
                                completed_audio = bool(turn_out and not st.get("language_block") and not barge_cancelled)
                                if st.get("lookup_waiting_answer"):
                                    _diag(cid, "node.lookup_answer_missing", out_bytes=turn_out)
                                    st["lookup_waiting_answer"] = False
                                if turn_out and not st.get("language_block") and not st.get("client_barge_in"):
                                    await _send_turn_tail()
                                turn_out = 0
                                st["await_first"] = True
                                if st.get("language_block"):
                                    source = st.get("language_block_source") or "unknown"
                                    blocked_text = st.get("blocked_output_text") or ""
                                    st["language_block"] = False
                                    st["language_block_source"] = None
                                    st["blocked_output_text"] = ""
                                    # Clear the cancelled turn on the App before
                                    # sending a safe replacement turn.
                                    await ws.send(json.dumps({"type": "turn_complete"}))
                                    if barge_cancelled and source in ("model_output", "mandarin_pronunciation"):
                                        _diag(cid, "node.language_replacement_skipped", reason="barge_in", source=source)
                                    elif source in ("model_output", "mandarin_pronunciation") and st.get("language_retry_count", 0) < 1:
                                        # 病歷 d（聲線變）：先讓模型用「她自己的聲音」重講國語版；
                                        # 重講仍被攔才換安全配音（不同引擎、聲線不同＝最後手段）。
                                        st["language_retry_count"] = st.get("language_retry_count", 0) + 1
                                        await _retry_mandarin_output()
                                    elif source == "mandarin_pronunciation":
                                        await _send_safe_mandarin_tts(blocked_text, source)
                                    else:
                                        await _send_hokkien_fallback(source)
                                else:
                                    if st.get("relay_greet_id") and completed_audio:
                                        await ws.send(json.dumps({"type": "relay_spoken", "id": st.pop("relay_greet_id")}, ensure_ascii=False))
                                    elif st.get("relay_greet_id") and barge_cancelled:
                                        await ws.send(json.dumps({"type": "relay_interrupted", "id": st.pop("relay_greet_id")}, ensure_ascii=False))
                                    await ws.send(json.dumps({"type": "turn_complete"}))
                                    st["language_retry_count"] = 0
                                    st["blocked_output_text"] = ""
                                st["client_barge_in"] = False
                                st["user_turn_started_at"] = None
                                # 通話記憶：這一輪講完，先把雙方字幕收進整通紀錄再清緩衝（收線時交聊後管線）
                                _capture_call_turns(st)
                                # 守護腦：這一輪自然講完了、天然的輪替空檔，排隊中的安全導引在這裡送出（不是插話攔截剛剛那句）
                                st["user_buf"] = ""
                                st["ai_buf"] = ""
                                st["user_flagged"] = set()
                                st["ai_flagged"] = set()
                                if st.get("pending_cues"):
                                    st["bg_tasks"].append(asyncio.create_task(guardian_flush_pending_cue(cid, session, st)))
                        # 即時查詢由 Voice 自己執行；提醒／傳話才交給 App 寫入。
                        tc = getattr(msg, "tool_call", None)
                        if tc and getattr(tc, "function_calls", None):
                            responses = []
                            for fc in tc.function_calls:
                                try:
                                    fargs = dict(fc.args) if fc.args else {}
                                except Exception:
                                    fargs = {}
                                function_name = str(getattr(fc, "name", "") or "")
                                action_id = str(getattr(fc, "id", None) or uuid.uuid4().hex)
                                _diag(cid, "node.tool_call", name=function_name or "?", action_id=action_id)
                                if function_name == live_lookup.TOOL_NAME:
                                    response = await _run_live_lookup(fargs, cue_already_spoken=turn_out > 0)
                                else:
                                    future = asyncio.get_running_loop().create_future()
                                    st["action_results"][action_id] = future
                                    await ws.send(json.dumps({
                                        "type": "action", "id": action_id,
                                        "action": function_name, "args": fargs,
                                    }, ensure_ascii=False))
                                    try:
                                        app_result = await asyncio.wait_for(future, timeout=8)
                                        result = app_result.get("result") if isinstance(app_result.get("result"), dict) else {}
                                        response = {"status": "ok", **result} if app_result.get("ok") else {
                                            "status": "error", "error": str(app_result.get("error") or "app_write_failed")[:120]
                                        }
                                    except asyncio.TimeoutError:
                                        response = {"status": "error", "error": "app_write_timeout"}
                                    finally:
                                        st["action_results"].pop(action_id, None)
                                responses.append(types.FunctionResponse(id=getattr(fc, "id", None), name=fc.name, response=response))
                            try:
                                await session.send_tool_response(function_responses=responses)
                            except Exception as e:
                                _diag(cid, "node.tool_response_err", err=str(e)[:60])
                    if not got:
                        break   # receive() 立刻空 = session 真的結束 → 收線

            # 任一邊結束（使用者掛斷 or session 收）就取消另一邊，乾淨收線
            tasks = [asyncio.create_task(from_browser()), asyncio.create_task(from_live())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        call_release_reason = "voice_error"
        _diag(cid, "node.error", err=f"{type(e).__name__}:{str(e)[:80]}")
    finally:
        if call_payload and call_release_reason:
            try:
                await asyncio.to_thread(
                    post_internal,
                    os.environ.get("MUNEA_CALL_CONTROL_URL", ""),
                    os.environ.get("MUNEA_GATEWAY_ADMIN_KEY", ""),
                    f"/v1/internal/calls/{call_payload['call_id']}/release",
                    {
                        "lease_version": int(call_payload["lease_version"]),
                        "event_id": "voice-release-" + uuid.uuid4().hex,
                        "reason": call_release_reason,
                    },
                )
            except Exception as exc:
                _diag(cid, "node.control_release_err", err=f"{type(exc).__name__}:{str(exc)[:80]}")
        if _key_idx is not None:
            _release_client(_key_idx)   # 這通結束，把這把鑰匙的空位放回去給下一通
        for t in st.get("bg_tasks", []):
            if not t.done():
                t.cancel()
        fw = st.get("face_ws")
        if fw is not None:
            try:
                await fw.close()
            except Exception:
                pass
        # 通話記憶回寫：補收最後一輪字幕，把整通交給文字聊天同一套聊後管線
        # （對話摘要＋記憶萃取對帳＋心情訊號）。下一通開場才接得上這通聊過什麼。
        # 對方整通沒說話（ASR 全空）persist 會自動略過。執行方式的三個講究：
        # ①走「專用」執行緒池，不佔 to_thread 的共用池——共用池同時服務 session 建立
        #   （7/12 的 30 人斷崖就是主迴圈被卡出來的，不能讓收線的多秒萃取去排擠開新通）；
        # ②await 到存完才讓 handler 返回——Voice 的 Cloud Run 沒開 CPU 常駐，
        #   handler 一返回連線就關、CPU 會被節流，純背景 thread 可能餓死存不進去；
        # ③handler 被取消（服務關閉）時改用 executor.submit 收尾（非 daemon、關機前會跑完），
        #   這通才不會白聊。
        try:
            _capture_call_turns(st)
            # 啟用條件二擇一：本機模式總開關（MUNEA_VOICE_CALL_MEMORY）或
            # Brain 通道已設定（設定密語＝刻意啟用，不疊第二道旗標）。
            if st.get("call_turns") and (
                    server._voice_call_memory_enabled() or _brain_memory_config()[0]):
                turns_snapshot = list(st["call_turns"])

                def _persist_call_memory(turns=turns_snapshot, call_id=cid,
                                         call_char=char, scope=memory_scope):
                    # 正式路線（B）優先：交給 Brain 代存（進東京正式庫、認得用戶）；
                    # Brain 沒設定或這通沒有已驗證用戶 → 退回 Voice 本機模式；
                    # Brain 呼叫失敗也退回本機，這通至少不白聊。
                    brain_url, brain_secret = _brain_memory_config()
                    if brain_url and scope and scope.startswith("voice-"):
                        try:
                            resp = post_internal(
                                brain_url, brain_secret, "/voice/call-memory",
                                {"userId": scope[len("voice-"):], "turns": turns,
                                 "char": call_char, "voiceSessionId": f"live-{call_id}"},
                                app_key=os.environ.get("MUNEA_APP_KEY", "").strip())
                            _diag(call_id, "node.call_memory_saved", via="brain",
                                  turns=len(turns), stored=bool((resp or {}).get("stored")),
                                  identity=bool((resp or {}).get("identityResolved")))
                            return
                        except Exception as exc:
                            _diag(call_id, "node.call_memory_brain_err",
                                  err=f"{type(exc).__name__}:{str(exc)[:60]}")
                    try:
                        result = server.persist_voice_call_turns(
                            turns, call_char, f"live-{call_id}", person_id=scope)
                        _diag(call_id, "node.call_memory_saved", via="local",
                              turns=len(turns), stored=bool(result))
                    except Exception as exc:
                        _diag(call_id, "node.call_memory_err",
                              err=f"{type(exc).__name__}:{str(exc)[:60]}")

                # run_in_executor 一呼叫就已提交，函式一定會被池跑完
                # （非 daemon、直譯器關閉前會等）；就算這裡被取消也只是不等結果，
                # 不可以再 submit 一次，會存兩份。
                await asyncio.get_running_loop().run_in_executor(
                    _CALL_MEMORY_EXECUTOR, _persist_call_memory)
        except Exception as exc:
            _diag(cid, "node.call_memory_err", err=f"{type(exc).__name__}:{str(exc)[:60]}")
        _diag(
            cid, "closed", in_bytes=st["in"], out_bytes=st["out"], echo_dropped=st["echo_dropped"],
            asr_turns=st["asr_turns"], asr_chars=st["asr_chars"],
            barge_ins=st["barge_in_count"], language_blocks=st["language_block_count"],
            lookups=st["lookup_count"], lookup_sources=st["lookup_sources"],
            lookup_failures=st["lookup_failures"],
        )


async def main():
    # 綁 0.0.0.0＝同一個 Wi-Fi 的手機也連得到（真機測聊聊用）；純本機測試連 127.0.0.1 亦可。
    host = os.environ.get("LIVE_VOICE_HOST", "0.0.0.0")
    # 門牌：雲端主機（Cloud Run）會用 PORT 指定；本機沒設就照舊 8201
    port = int(os.environ.get("PORT") or os.environ.get("MUNEA_VOICE_PORT") or "8201")
    async with websockets.serve(handle, host, port, max_size=None, process_request=process_request):
        print(f"即時語音橋接已啟動：{host}:{port} （網頁＋語音同門，模型 {MODEL}）")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
