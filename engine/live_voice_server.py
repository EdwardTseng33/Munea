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
from voice_echo_guard import (frame_rms, in_output_window, should_drop_uplink_frame, hot_threshold,
                              note_playout, in_playout_window, guard_enabled, guard_rms_threshold,
                              normalized_rms_to_pcm16, sustained_voice_evidence,
                              barge_evidence_threshold)
load_engine_env()  # 跟 server.py 同款：自動吃 engine/.env.local 的鑰匙、環境變數優先
from service_metadata import build_service_metadata
import chat_engine as eng
import health_kb
import health_selector
import localization
import live_lookup
import voice_turn_semantics
import voice_tool_continuity
from voice_locale_session import VoiceLocaleSession
from call_control_client import post_internal, verify_call_token, CallControlError
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
import websockets
from websockets.http11 import Response
from websockets.datastructures import Headers

# 引擎選擇（2026-07-30 Edward 拍板「開始測試 2.5 正式版」）：預設 31＝現行、零改變。
# vertex25＝Google 雲正式版 2.5 原生語音（gemini-live-2.5-flash-native-audio @ us-central1）。
# 7/30 三關實測：吃 cmn-TW+Leda ✅、附和/主動接話開關存在 ✅、第一聲 750ms（僅比 3.1 慢 0.1 秒）。
# 7/25 否決三理由全數失效——但正式採用前仍要過 19 題考卷＋Edward 人耳。
VOICE_ENGINE = os.environ.get("MUNEA_VOICE_ENGINE", "31").strip().lower()
if VOICE_ENGINE in ("vertex25", "25", "native25"):
    MODEL = os.environ.get("MUNEA_VOICE_MODEL_OVERRIDE") or "gemini-live-2.5-flash-native-audio"
else:
    VOICE_ENGINE = "31"
    MODEL = "gemini-3.1-flash-live-preview"
TURN_END_SILENCE_MS = 180
TURN_END_SILENCE_PCM = b"\x00\x00" * int(24000 * TURN_END_SILENCE_MS / 1000)
# 通話延長（2026-07-25 · 治「講超過 10 分鐘被硬切斷」）：Gemini Live 對每個底層連線有
# 時間上限，快到的時候會先送 GoAway 預警（time_left）才真的斷線。GOAWAY_RECONNECT_MARGIN_S
# 是提早多少秒動手換線（留給重連握手的緩衝，別真的卡到 0 秒才動）；MAX_SESSION_RECONNECTS
# 是這通電話最多允許換幾次底層連線的安全閥（防禦性上限，不是預期會用到）。
GOAWAY_RECONNECT_MARGIN_S = float(os.environ.get("MUNEA_VOICE_GOAWAY_MARGIN_S", "3"))
MAX_SESSION_RECONNECTS = int(os.environ.get("MUNEA_VOICE_MAX_RECONNECTS", "8"))
LOOKUP_CUE_TAIL_MS = 80
LOOKUP_CUE_TAIL_PCM = b"\x00\x00" * int(24000 * LOOKUP_CUE_TAIL_MS / 1000)


# ── 兩支儀表的算法（2026-08-01 · Edward 7/31 深夜「變慢＋斷斷續續」查不到證據後重做）──
# 抽成純函式的理由：這兩個數字原本寫在通話迴圈裡，一個從頭到尾沒人驗算過，
# 結果兩支都在量別的東西（見各自註解），出事時反而讓人以為「數據顯示沒問題」。
# 抽出來就能用測試把「起點是什麼」釘死，之後誰改都會被守門測試擋下來。

def reply_latency_ms(now, last_voice_at=0.0, last_packet_at=None):
    """他講完到她出聲，幾毫秒。回 (毫秒, 起點是什麼)。

    起點必須是「最後一次真的聽到人聲」。舊版拿 last_packet_at（每一格麥克風封包都會
    刷新，包含全靜音），量到的永遠是一格封包的間隔（正式機實測 7-38 毫秒）＝根本沒在量。
    真的沒聽過人聲時（開場招呼、純文字輸入）才退回封包時間，並在回傳值標明。
    """
    if last_voice_at:
        return round((now - last_voice_at) * 1000), "user_voice"
    if last_packet_at is None:
        return None, "unknown"
    return round((now - last_packet_at) * 1000), "last_packet"


def note_turn_gap(now, turn_last_out, current_max_ms=0.0):
    """這一輪送聲音，相鄰兩塊之間最久的空檔（毫秒）。回 (新的最大值, 這一塊的空檔)。

    turn_last_out 是「這一輪」的上一塊，每輪開始必須歸零——舊版拿整通共用的
    last_out 比，於是每輪第一塊都量到「兩句話中間他在想事情」那段安靜
    （正式機報過 45,540 毫秒＝他想了 45 秒，被記成她卡了 45 秒）。
    """
    if turn_last_out is None:
        return current_max_ms, None
    gap = (now - turn_last_out) * 1000
    return (gap if gap > current_max_ms else current_max_ms), gap

# 送一塊聲音去雲端臉，最多等多久（2026-07-29）。
#
# 為什麼要有這個：同一份聲音要送兩個地方——手機（使用者在聽，必須）和雲端臉
# （臉會動，加分）。原本兩個都是直接 await，臉那條線一慢就會**回頭卡住聲音**：
# 下一塊聲音要等臉這塊送完才輪得到，使用者就聽到「卡一下／吃掉一個字」。
# 臉機是租來的 GPU、跨網路，慢是常態不是意外。
#
# 程式碼原本的註解寫著「連不上/斷了都不能拖累語音對話」——立意是對的，但只擋了
# 「斷掉」（例外），沒擋「變慢」（阻塞）。這個常數把「慢」也擋掉：超過就放掉臉那條線，
# 聲音永遠優先。150 毫秒的取法：正常送出遠小於此（寫進緩衝就回來），
# 又遠小於手機端 600 毫秒的播放水庫，就算真的等滿一次也不會被聽出來。
FACE_SEND_TIMEOUT_S = float(os.environ.get("MUNEA_VOICE_FACE_SEND_TIMEOUT_S", "0.15"))


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


def _make_client(key):
    """依引擎開一個連線客戶端。31＝原樣（開發者鑰匙）。vertex25＝Google 雲正式版：
    雲端機器（Cloud Run）內建身分、genai.Client(vertexai=True) 直接可用；
    本機測試沒有內建身分，退而用 gcloud 現領的短期通行證（MUNEA_VERTEX_ACCESS_TOKEN）。"""
    if VOICE_ENGINE != "vertex25":
        return genai.Client(api_key=key)
    project = os.environ.get("MUNEA_GCP_PROJECT", "gen-lang-client-0229303523")
    location = os.environ.get("MUNEA_VERTEX_LOCATION", "us-central1")
    tok = os.environ.get("MUNEA_VERTEX_ACCESS_TOKEN", "").strip()
    if tok:
        from google.oauth2.credentials import Credentials
        return genai.Client(vertexai=True, project=project, location=location,
                            credentials=Credentials(tok))
    return genai.Client(vertexai=True, project=project, location=location)


_clients = [_make_client(k) for k in KEYS]   # 每把鑰匙一個 client（vertex25 時鑰匙只當佔位、實際走雲端身分）
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

_CHAT_TEST_TRUE_VALUES = {"1", "true", "yes", "on"}
_CHAT_TEST_CLOUD_MARKERS = ("K_SERVICE", "K_REVISION", "K_CONFIGURATION")
_CHAT_TEST_BLOCKED_ENVIRONMENTS = {"production", "prod", "staging", "stage"}


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


def _chat_test_enabled(environ=None):
    """Allow the developer bootstrap only for an explicit non-cloud test run."""
    env = os.environ if environ is None else environ
    enabled = str(env.get("MUNEA_ENABLE_CHAT_TEST") or "").strip().lower()
    if enabled not in _CHAT_TEST_TRUE_VALUES:
        return False
    if any(str(env.get(marker) or "").strip() for marker in _CHAT_TEST_CLOUD_MARKERS):
        return False
    environment = str(
        env.get("MUNEA_ENV_NAME")
        or env.get("MUNEA_ENVIRONMENT")
        or env.get("ENVIRONMENT")
        or env.get("NODE_ENV")
        or ""
    ).strip().lower()
    return environment not in _CHAT_TEST_BLOCKED_ENVIRONMENTS


def _chat_test_not_found():
    headers = Headers()
    headers["Cache-Control"] = "no-store"
    headers["Content-Length"] = "0"
    return Response(404, "Not Found", headers, b"")


def _chat_test_response():
    """Serve the full app with an explicitly enabled developer session.

    ``process_request`` must keep this route disabled in managed cloud
    environments and unless ``MUNEA_ENABLE_CHAT_TEST=1`` is present.
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
        if not _chat_test_enabled():
            return _chat_test_not_found()
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


def impossible_promise_cue(dropped):
    """語音線專用的自我更正提示（2026-07-29）。

    為什麼語音線不能只靠出口清洗：聲音是邊生邊播的，等字幕清乾淨時那句
    「我幫你打電話給你女兒」**已經唸出去、長輩已經聽到了**——他會坐下來等，
    等不到人也不會再想辦法求助。收不回聲音，但可以在下一個輪替空檔（通常兩三秒內）
    讓她自己自然地更正回來，趕在他真的去等之前。

    語氣要求：自然收回、不長篇道歉（一直道歉會讓長輩緊張、也顯得不可靠）。
    """
    said = (dropped or [""])[0][:40]
    return (
        "（系統提示，絕對不要唸出這段：你剛剛說了「%s」這類**你其實做不到**的事"
        "（你撥不了電話、發不了訊息、叫不了車、傳不了圖）。"
        "下一句請**自然地把它收回來，並馬上給他一個他自己做得到的替代**，"
        "像『欸不好意思，我沒辦法幫你撥電話，不過你現在打給她，我在這邊陪你等她接』。"
        "不要長篇道歉、不要解釋你是AI，一句帶過就好，重點放在他接下來可以怎麼做。）" % said
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


def _guardian_begin_real_user_turn(st):
    """Re-arm hidden safety follow-ups only after a new microphone turn."""
    turn_id = int(st.get("guardian_real_turn_id", 0)) + 1
    st["guardian_real_turn_id"] = turn_id
    st["guardian_internal_followup_active"] = False
    st["guardian_internal_followup_sources"] = ()
    for field in ("user_flagged", "ai_flagged"):
        current = st.setdefault(field, set())
        st[field] = {
            key for key in current
            if not (
                isinstance(key, tuple) and key and isinstance(key[0], int)
                and key[0] < turn_id - 1
            )
        }
    return turn_id


async def guardian_watch(cid, who, text, st, session, turn_id=None, allow_cue=None):
    """背景任務：非同步跑守護腦判讀 + 記錄/告警 +（high/critical）排隊安全導引。絕不擋音訊管線。"""
    try:
        if turn_id is None:
            turn_id = int(st.get("guardian_real_turn_id", 0))
        if allow_cue is None:
            allow_cue = not (who == "ai" and st.get("guardian_internal_followup_active"))
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
                    key = (turn_id, "semantic", scat)
                    if key not in st["user_flagged"]:
                        st["user_flagged"].add(key)
                        cue = guardian_redirect_cue((scat,), sem_result["risk"], sem_result["responsePolicy"])
                        if len(st["pending_cues"]) < 2:
                            st["pending_cues"].append(cue)
            return
        flagged = st["user_flagged"] if who == "user" else st["ai_flagged"]
        key = (turn_id, categories)
        if key in flagged:
            return
        flagged.add(key)
        policy = (result or {}).get("responsePolicy") or {}
        _diag(cid, "guardian.hit", who=who, level=level, categories=",".join(categories) or "-",
              protection=risk.get("protectionEvent"), family=policy.get("familyNotificationCandidate"))
        if not allow_cue:
            _diag(
                cid, "guardian.cue_suppressed",
                reason="hidden_followup_no_recursive_turn",
                turn=turn_id,
                sources=",".join(st.get("guardian_internal_followup_sources") or ()) or "-",
            )
            return
        cue = (
            guardian_ai_correction_cue(categories, risk, policy)
            if who == "ai"
            else guardian_redirect_cue(categories, risk, policy)
        )
        cues = st["pending_cues"]
        if len(cues) < 2:
            cues.append(cue)
    except Exception as e:
        _diag(cid, "guardian.watch_err", err="%s:%s" % (type(e).__name__, str(e)[:60]))


def _fetch_health_profile(memory_scope):
    """接通時跟 Brain 要一次「挑方案用側寫」（齡層＋人別鍵＋他試過什麼有沒有效）。

    跟要「上次聊天」「他的身體狀況」同一條內部通道、同一個認人規矩：Voice 這台
    沒有雲端鑰匙也認不出電話那頭是誰，一律由 Brain 認人。拿不到就回空——
    挑選層會退回通用方案，不亂猜齡層（猜錯比不猜更傷）。
    """
    brain_url, brain_secret = _brain_memory_config()
    if not (brain_url and memory_scope and str(memory_scope).startswith("voice-")):
        return {}
    try:
        resp = post_internal(
            brain_url, brain_secret, "/voice/health-context",
            {"userId": str(memory_scope)[len("voice-"):]}, timeout=3,
            app_key=os.environ.get("MUNEA_APP_KEY", "").strip())
    except Exception:
        return {}
    prof = (resp or {}).get("healthProfile")
    return prof if isinstance(prof, dict) else {}


def _start_health_profile_fetch(st, memory_scope):
    """背景去要側寫、拿到才填進 st——絕不放在接通那條路上等。

    這是個最多 3 秒的阻塞 HTTP；接通流程是 async 主幹道，在那裡等於把
    這台機器上「所有」通話一起卡住（2026-07-12 壓測抓過同一類真兇）。
    衛教提示要等用戶先講到相關的話才會用到，那是接通後好幾秒的事，
    背景填完全來得及；還沒填好就先當通用，不會出錯只會少一點個人化。
    """
    if not memory_scope:
        return

    def _fill():
        try:
            st["health_profile"] = _fetch_health_profile(memory_scope)
        except Exception:
            pass

    threading.Thread(target=_fill, daemon=True).start()


def _record_voice_recommendation(cid, st, topic_id, said, prof, hour):
    """把聊聊剛端出的方案回報給 Brain 記帳——飛輪的帳本只有一本，在 Brain 那台。

    背景執行緒送、失敗就算了：記不到帳最多是下次少一點個人化，
    絕不能為了記帳去卡住音訊管線（她講話卡住是用戶當場感覺得到的事）。
    """
    scope = st.get("memory_scope")
    if not (scope and prof.get("personId") and topic_id in health_selector.TOPICS):
        return
    try:
        chosen = health_selector.pick(topic_id, said, prof, hour)["solutions"]
    except Exception:
        return
    if not chosen:
        return
    brain_url, brain_secret = _brain_memory_config()
    if not brain_url:
        return

    def _send():
        try:
            post_internal(brain_url, brain_secret, "/voice/health-recommended",
                          {"userId": str(scope)[len("voice-"):], "topicId": topic_id,
                           "solutions": [{"id": s.get("id"), "label": s.get("label"),
                                          "timeToEffect": s.get("timeToEffect")} for s in chosen]},
                          timeout=3, app_key=os.environ.get("MUNEA_APP_KEY", "").strip())
        except Exception as e:
            _diag(cid, "healthkb.record_err", err="%s:%s" % (type(e).__name__, str(e)[:60]))

    threading.Thread(target=_send, daemon=True).start()


def health_watch_user_text(cid, st):
    """B2 衛教（2026-07-24）：用戶字幕命中策展題庫→排隊一條衛教提示，騎守護腦同一個
    「輪替空檔」送出機制。每題整通只注入一次、每通上限 health_kb.MAX_TOPICS_PER_CALL 題
    （衛教是配菜、不把通話變講座）。純關鍵字比對、同步、零模型呼叫——絕不擋音訊管線。"""
    try:
        sent = st.setdefault("health_topics_sent", set())
        if len(sent) >= health_kb.MAX_TOPICS_PER_CALL or st.get("pending_health_cue"):
            return
        said = st.get("user_buf") or ""
        # 2026-07-29：把「這個人是誰、現在幾點、上次哪個沒效」帶進來，聊聊也要因人因時
        # （聊聊是主戰場——長輩版跟青少年版不能混）。判不出齡層就傳 None、退回通用。
        #
        # ⚠ 這行原本讀 st["health_audience"]，但那個鍵從頭到尾沒有任何地方寫進去——
        # 語音線的因人分齡等於一直沒生效。改成接通時跟 Brain 要一次、存進這通的
        # 狀態裡（st 是每通獨立的；絕不做跨通的模組級快取，那會把 A 的資料端給 B）。
        _prof = st.get("health_profile") or {}
        # 一國一庫：用「這通實際講哪種語言」挑觸發字與說法（同人設書同一個來源）；
        # 那一國沒有疊層＝衛教不出手，安全話術絕不退回中文。
        _kb_locale = (st.get("voice_locale_profile") or {}).get("sessionLocale")
        _hour = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).hour
        ids = health_kb.match_topics(said, limit=1, exclude=sent, locale=_kb_locale)
        if not ids:
            return
        sent.add(ids[0])
        st["pending_health_cue"] = health_kb.voice_cue(ids[0], said, _prof, _hour, locale=_kb_locale)
        # 帳先備著、等這句真的送出去才記——提示是排在下一個輪替空檔送的，
        # 電話在那之前掛掉就等於她沒講過，記了下次會問「上次那個有試嗎」問空氣。
        st["pending_health_record"] = (ids[0], said, _prof, _hour)  # 記帳不分語系（帳本是機器鍵）
        _diag(cid, "healthkb.hit", topic=ids[0])
    except Exception as e:
        _diag(cid, "healthkb.err", err="%s:%s" % (type(e).__name__, str(e)[:60]))


async def guardian_flush_pending_cue(cid, session, st):
    """在天然的輪替空檔（模型這一輪講完、turn_complete）送出排隊的安全導引，不是插話攔截正在講的這一句。"""
    guardian_cues = list(st.get("pending_cues") or [])
    pending = list(guardian_cues)
    st["pending_cues"] = []
    health_cue = st.get("pending_health_cue")
    st["pending_health_cue"] = None
    st["pending_health_record"] = None
    promise_cue = st.get("pending_promise_cue")
    st["pending_promise_cue"] = None
    if promise_cue:
        # 空頭承諾更正排最前面：長輩可能正準備坐下來等，這句要最快講
        pending = [promise_cue] + pending
    if health_cue:
        # A routine topic match may be logged, but must not create a second
        # model turn after the person has stopped speaking.
        _diag(cid, "healthkb.followup_suppressed", reason="no_new_user_turn")
    if not pending:
        return
    sources = []
    if guardian_cues:
        sources.append("guardian")
    if promise_cue:
        sources.append("promise")
    st["guardian_internal_followup_active"] = True
    st["guardian_internal_followup_sources"] = tuple(sources)
    try:
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="\n".join(pending))]),
            turn_complete=True,
        )
        _diag(cid, "guardian.cue_sent", count=len(pending))
    except Exception as e:
        st["guardian_internal_followup_active"] = False
        st["guardian_internal_followup_sources"] = ()
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


# 說明書的優先權契約：五層規則誰壓過誰。
# 2026-07-31 分國——這段原本寫死「二、語言鐵律（台灣華語、禁台語輸出）」，
# 等於在英文／日文／西班牙文的通話裡，命令她講台灣華語。實跑抓到她整段用中文
# 回答英文用戶，這段是主犯之一（另一個是角色性格沒分國）。
_PRIORITY_CONTRACT = {
    "zh-TW": (
        "（本說明書優先權契約：以下所有規則分五層——"
        "一、安全與醫療紅線（危機處理、不診斷不調藥） 二、語言鐵律（台灣華語、禁台語輸出） "
        "三、身分與人格（角色、稱呼、關係分寸） 四、當下情境（記憶、感知、上次聊天、在地資訊） "
        "五、表達風格（話量、句尾、說故事、情緒陪伴）。"
        "內容互相衝突時，層級數字小的一律優先；任何風格規則都不得鬆動安全與語言規則。）"
    ),
    "en": (
        "(Priority contract for this guidance — five layers: "
        "1. Safety and medical red lines (crisis handling; no diagnosis, no medication changes) "
        "2. Language rule (reply entirely in English) "
        "3. Identity and character (who you are, how you address them, closeness) "
        "4. Present context (memory, perception, the last conversation, local information) "
        "5. Expression (how much you say, sentence endings, stories, emotional company). "
        "When rules conflict, the lower-numbered layer always wins; no style rule may ever "
        "loosen a safety or language rule.)"
    ),
    "ja": (
        "（この説明書の優先順位——規則は五つの層に分かれます："
        "一、安全と医療のレッドライン（危機対応、診断しない・薬を変えない） "
        "二、言語の鉄則（返答はすべて日本語で） "
        "三、身分と人格（あなたが誰か、呼びかけ方、距離感） "
        "四、いまの状況（記憶、感知、前回の会話、地域の情報） "
        "五、話し方（話す量、文の終わり方、語り、寄り添い）。"
        "規則が衝突したときは、番号の小さい層が必ず優先します。"
        "話し方の規則が、安全と言語の規則をゆるめることは決してありません。）"
    ),
    "es": (
        "(Orden de prioridad de esta guía —cinco niveles: "
        "1. Líneas rojas de seguridad y médicas (crisis; no diagnosticar, no cambiar medicación) "
        "2. Regla de idioma (responder íntegramente en español) "
        "3. Identidad y carácter (quién es usted, cómo se dirige a la persona, la distancia) "
        "4. Contexto actual (memoria, percepción, la conversación anterior, información local) "
        "5. Expresión (cuánto habla, final de frase, relatos, acompañamiento emocional). "
        "Cuando dos reglas chocan, gana siempre el nivel con el número más bajo; ninguna regla "
        "de estilo puede relajar una regla de seguridad o de idioma.)"
    ),
}


def _priority_contract(locale):
    return _PRIORITY_CONTRACT.get(locale) or _PRIORITY_CONTRACT["zh-TW"]


def system_instruction(char="寧寧", name=None, mood=None, topics=None, user=None, location=None, allow_reminders=False, fam=0, memory_scope=None, allow_events=False, demo_mode=False, allow_care_questions=False, locale_profile=None):
    """跟 /chat 同一套腦：角色人格 + 非醫療界線 + 記憶層 + 感知層 + 守護腦。"""
    # 2026-07-31：說明書與角色性格都照這通電話的語系拿。
    # sessionLocale＝這通實際講哪種語言（介面英文但講日文的人要拿日文書）。
    # 角色性格原本固定讀繁中版，於是英文說明書中間夾著中文個性描述——
    # 實跑抓到她整段用中文回答英文用戶。
    _book_locale = (locale_profile or {}).get("sessionLocale") or eng.DEFAULT_PERSONA_LOCALE
    _chars = eng.characters_for(_book_locale)
    c = _chars.get(char) or _chars["寧寧"]
    # 優先權契約放在整份說明書最前面：規則衝突不再靠「排在前面還後面」決定，
    # 一律照層級數字比大小（7/15 Edward 拍板說明書分層）。
    base = (
        _priority_contract(_book_locale)
    )
    # 共同底盤（管家身分＋專業邊界＋告警/情緒/調解能力）在最前面，角色性格疊在上面
    # 共同底盤依查詢模式組裝（2026-07-30）：開內建搜尋＝線上版查詢規則（不再跟
    # 「你不會自己上網查」同時出現＝不打架）；其餘模式＝離線版原行為。
    # 2026-07-31：說明書照這通電話的語系拿（locale_profile 已在上面解出來、是可信來源）
    # 說明書用「這通對話實際講哪種語言」（sessionLocale）決定，不是介面語言——
    # 介面英文但講日文的長輩，該拿到的是日文書。
    _core = eng.core_instruction(
        "online" if (native_search_enabled() and not demo_mode) else "offline",
        _book_locale,
    )
    base += _core + c.get("persona", "") + eng.red_lines(_book_locale)
    if native_search_enabled() and not demo_mode:
        # 2026-07-29：這通有內建搜尋（她可以自己查）——但共用說明書寫的是「你不會自己上網查」，
        # 兩邊會打架。這段把規矩講清楚，而且補上最重要的一條：**健康問題不准用搜尋回答**。
        # 為什麼：搜尋結果沒人審過（內容農場跟醫學會指引在她眼裡長一樣），
        # 而健康建議一旦講錯，長輩會照著做。7/24 三路調研已拍板「健康走策展題庫、不走現查」。
        # 2026-07-30 瘦身下半場：原本這段開頭在「覆蓋掉共用說明書那句『你不會自己上網查』」
        # ——那是補丁蓋補丁；現在共用底盤已依模式二選一（core_instruction），矛盾在源頭解掉，
        # 這裡只留它真正的貢獻＝健康除外條款（守門測試釘著原句、不得改寫）。
        base += (
            "（查詢的健康除外條款（硬規矩）：健康、身體、用藥、症狀、保健品這類問題，"
            "**絕對不准用查到的網路內容回答**——那些沒人審過，內容農場跟醫學會的說法在搜尋結果裡長得一樣。"
            "健康的事只能用系統給你的衛教資料回答（下面若有「因人挑選的方案」或「衛教資料庫」那段就是），"
            "沒有那段就老實說「這個我不太確定，你要不要問醫生或藥師」——**寧可說不知道，也不要拿網路上的東西當健康建議**。）"
        )
    if demo_mode:
        base += (
            "（最高優先：這是 B2B 網站的匿名訪客體驗，不是正式使用者會話。"
            "你不知道對方身分，也沒有任何使用者記憶、健康資料、家庭圈、提醒或行程權限。"
            "不得宣稱記得對方、看得到他的資料、已替他建立提醒或已通知任何人；"
            "不要主動詢問姓名、電話、地址、病歷或其他個人資料。"
            "簡短自我介紹後自然陪聊；若對方問正式功能，說明完整版本可在場域診斷中展示。）"
        )
    try:
        if demo_mode:
            raise RuntimeError("anonymous demo has no reply context")
        # displayName 跟著角色走：用戶自訂名優先、否則用角色本名。
        # 不傳的話會 fallback 到存檔的陪伴檔案（寧寧），把換角色的名字蓋回去。
        data = {"displayName": (name or char)}
        if location:
            data["location"] = location  # 所在地（可到區）→ 在地餐廳/景點/話題定位
        if mood:
            data["userMood"] = mood
        if topics:
            data["interests"] = topics  # 用戶挑的興趣話題（?topics=）→ 開場/接話的方向
        # 他自己的身體狀況：一定要在組說明書「之前」拿到，不然她那段會先印成「你什麼都看不到」。
        # 為什麼向 Brain 要而不自己撈：Voice 這台沒有雲端鑰匙、也認不出來電者是誰
        # （所有來電者會落到同一個預設身分）。健康資料最不能認錯人——把 A 的血壓講給 B 聽，
        # 比不講嚴重得多。所以 Brain 認人、Brain 撈，Voice 只拿結果。
        # 要不到就不塞：build_reply_context 撈不到 → 空的 → 圍籬告訴她「你看不到、不准編」。
        health_ctx = _brain_health_context(memory_scope)
        if health_ctx:
            data["healthContext"] = health_ctx
        ctx = server.build_reply_context([], char, data)
        base += server.reply_context_instruction(ctx)
    except Exception:
        pass
    try:
        if demo_mode:
            raise RuntimeError("anonymous demo has no prior-call recap")
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
    # 2026-08-06 GPT Live 對齊：即時互動只留一份短、分段、可執行的契約。
    # 醫療、安全、權限與來源紅線仍在共用人設書；這裡不再用多組例句重複同一規則。
    base += (
        "\n[即時通話互動契約]\n"
        "相處：現在是即時語音視訊通話。把它當成真實世界裡兩個人的視訊聊天；"
        "像一個自然、有人味的人接住對方，不是你表演、他觀看。剛接起先一句溫暖招呼，"
        "一次只推進一件事，講到這輪需要的程度就停。\n"
        "來源：這是一通新接起的電話。只使用對方這通親口說的內容與上面明確提供的可信資料；"
        "沒有來源的關係、過去、家人、習慣或眼前情境都不要補。想關心就改成中性問句，"
        "一次問一件；問句裡一樣不准塞他沒講過的細節。\n"
        "純語音的現實：你們之間只有「聲音」。他傳不了任何東西給你——沒有貼圖、照片、文字、"
        "影片或連結；你看不到畫面，也不要叫他「用指的給我看」「拿給我看」。"
        "聽不清楚部位、人名或東西，就說沒聽清、請他再說一次，不要猜他做了什麼。"
        "你也給不了他任何東西——不要說「我傳給你」「你看一下這張圖」「詳見某某網站」。"
        "查到的資料先消化成口語再講；一次最多三件事，每件之間留空，讓他消化或接話。）"
    )
    # 熟識度分寸貫穿整段對話（不只開場）：越不熟越收斂、越熟越自在（Edward 2026-07-12）
    if fam < 1:
        base += "（你們還不太熟，這是頭幾通電話：整段對話都要特別收斂——話少、溫和、讓他主導，不要熱情轟炸、不要一直找話題硬聊、不要連環問。他問你、或聊到他有興趣的才多說一點。）"
    elif fam < 3:
        base += (
            "（你們聊過幾次、漸漸熟了：可以自在一點，但對方沒要求時不要自顧自延伸"
            "第二個話題，也別連環問、別硬炒氣氛。）"
        )
    else:
        base += (
            "（你們很熟了、像老朋友：自在、可主動一點，但仍然一次只推進一件事；"
            "對方明確想深入、比較、聽完整說明或故事時再自然展開。）"
        )
    if native_search_enabled() and not demo_mode:
        # Gemini 內建搜尋：短契約取代重複的案例清單；健康除外條款仍由前面的硬規矩負責。
        base += (
            "\n[即時資訊｜內建搜尋]\n"
            "你可以自己上網查現在的資訊，但只在他明確問到店家、旅遊、天氣、時事、活動等"
            "會變動的具體資訊時查；不要自己帶話題再查。他問新聞時事就真的查，他沒問就不要主動報。"
            "查前先用一句很短的話告訴他你在查，整次只說一次；查後先講結論，再講一兩個有用重點。"
            "只講查到的內容；查不到就說沒查到，不准用印象補。不要唸網址、來源括號、編號清單，"
            "也不要把自己正在做的動作講出來。你查東西是上網查，不是「用眼睛看」；"
            "不要叫他把東西拿來給你看，只能請他唸給你聽。"
            "不要重複過場，也不要編店名、地址、價格或營業時間。）"
        )
    if live_lookup_enabled():
        if not demo_mode:
            base += (
            "（你有 search_current_information 即時查詢工具。**他自己開口問**餐廳店家、景點旅遊"
            "（例如日本哪裡好玩、桃園有什麼好吃的）、電影影劇、天氣預報、時事、活動檔期這類"
            "「講錯會誤導人」的具體事情時，才呼叫工具；"
            "**你自己不要把話題帶到那邊、再查給他看**——查一次要好幾秒，他在電話那頭乾等，"
            "沒人問你就跑去查，等於自己找話題還讓他等。「聊到」不算，**要他真的問**才算。"
            "不要自己先說過場、也不要先生成答案，Voice 伺服器會先替你播放「我幫你查一下」，再執行查詢。工具回來後才回答，"
            "只講查到的真店名、真地點、真資訊；用「我聽很多人推薦…」「那邊最有名的是…」這種像自己去過或朋友推薦的口吻，"
            "自然分享一兩個亮點就好，順便帶一個有意思的小知識或典故更好。不要唸清單、不要報網址、不要像導覽機。"
            "查不到或不確定就老實說「這我不太確定，我幫你查查看」——寧可少講，絕對不可以自己編店名、地址、價格或營業時間。"
            "天氣要講就查當地真的預報再講。"
            "工具回覆 error 時只要簡短說現在沒查到，不可拿舊印象補答案；禁止先沉默查詢，也不要在還沒查完時假裝已經知道答案。）"
            )
    if voice_search_mode() == SEARCH_MODE_OFF or demo_mode:
        # 即時查詢關掉時：她必須知道自己沒有這個能力，不然會亂承諾「我幫你查」然後查不了。
        # 2026-07-28 條件從 `not live_lookup_enabled()` 改成明確判 off——否則走 native
        # （她自己查）時這段會跟上面那段同時貼上去，變成「你可以查」＋「你沒辦法查」自相矛盾。
        # 這段的方向跟⑦「不捏造家人的話」、健康圍籬一樣：不知道就說不知道，絕不憑印象編。
        base += (
            "\n[即時資訊｜無搜尋]\n"
            "你沒有辦法上網查東西。絕對不要說「我幫你查一下」「我查查看」「我找找看」或「等我一下」；"
            "做不到還承諾是空頭支票，那是客服，不是朋友。"
            "可用的即時資訊只限上面「你今天已經知道的事」；可以自然講，但不要透露「今日簡報」、"
            "系統或資料來源。那段沒有的店家、新聞、價格、路況或數字就直接說不知道，"
            "像朋友一樣說「這我就不知道了欸」，可建議他打電話確認；"
            "寧可說不知道，絕對不可以憑印象編。）"
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
    else:
        # 2026-08-08 Edward 真機：個人資料沒填任何稱呼，她開口就叫他「伯伯」。
        # 舊寫法在這裡**什麼都不說**——不知道名字時，說明書對稱呼完全沉默，
        # 而開場指令卻要求「用他的稱呼開頭」，等於逼她自己生一個。
        # 沉默不是中立：模型會用最像樣的猜測填空（照年紀猜「伯伯」、照性別猜「先生」）。
        # 所以這裡要明講「不知道」＋給她一條照樣合格的路（不加稱呼直接說話）。
        base += (
            "（稱呼規則：**你不知道他叫什麼**——個人資料裡沒有填。"
            "所以整通電話都不要加稱呼，直接跟他說話就好；"
            "**絕對不准自己想一個**，包括照年紀或性別猜的「伯伯」「阿姨」「阿公」「阿嬤」"
            "「先生」「小姐」「大哥」「大姐」——你沒見過他，那是憑空猜的。"
            "沒有稱呼一點都不失禮，叫錯才傷人。"
            "他自己在對話中說了名字，之後才可以用他說的那個。）"
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
            # 傳話要「整理過再確認」而不是原句照送（Edward 2026-07-31）：
            # 他對你說的是「幫我跟他說他晚餐的藥忘記吃了」——那是講給你聽的第三人稱。
            # 原封不動送出去，收到的人會看到一句在講別人的話，很怪。
            # 但整理只能動說法、不能動意思，所以一定要唸回去讓他點頭，這是防走鐘的保險。
            "他要傳話給家庭圈成員時，先把那句話整理成「直接對收件人說」的口氣："
            "換成第二人稱、去掉贅字與口頭禪、把時間地點講清楚，讓對方一聽就懂。"
            "整理只能改說法，「絕對不可以」改變意思——不補他沒說的事、不刪他交代的細節、不猜他的用意、不加自己的評論。"
            "整理完先用一句話唸回去給他聽並問可不可以（例如「我跟他說『晚餐的藥還沒吃，記得去吃』，這樣可以嗎？」），"
            "他明確說可以才呼叫 send_family_relay；他說不對或要改，就照他的意思重整理、再唸一次確認，沒得到同意就不要送。"
            # 提前多久提醒（Edward 2026-08-01）：App 畫面上可以選，用講的也要能設。
            # 「沒講就問一下」是他要的，但問法要像人——問一次、給常用選項、
            # 他含糊帶過就用預設，不要追問到底。
            "設看診提醒時，他若沒說要提前多久提醒，用一句話問一下"
            "（例如「要我提前多久叫你？前一天、還是當天提早兩個小時？」）。"
            "他有講就填進 remindBefore；他說「都可以」「隨便」或答得含糊，就不要再追問，"
            "直接照預設的兩小時前設好，並在確認那句話裡告訴他（例如「那我提前兩個小時叫你」）。"
            "設好之後用一句溫暖口語的話跟他確認你設了什麼"
            "（例如「好，我幫你記下明天下午四點台大骨科回診，提前兩個小時叫你」），讓他安心、也方便他去 App 裡的提醒清單看或改。"
            "「分類鐵律」：看診提醒只能用在真的要去醫院、診所看醫生；用藥提醒只能用在吃藥。"
            "約會、聚餐、出遊、家人來訪這類行程「絕對不可以」設成看診或用藥提醒——分類錯了會讓 App 講出很奇怪的話。）"
        )
    if allow_events:
        base += (
            "（他說要記「約會、聚餐、出遊、活動、家人來訪」這類行程時，呼叫 set_personal_event 幫他記進 App 的家庭活動。"
            "時間換算成 24 小時制要用常識：吃飯、晚餐、約會講「7點」通常是晚上 19:00、不是早上；"
            "聽不出上午或晚上，就先用一句話問清楚再設。"
            "現在若是深夜或凌晨，他說「明天」時先跟他確認是「等天亮的那個白天」還是「再隔一天」，確認完再換算日期。"
            "呼叫前用一句話跟他確認日期、時間、名目；工具回 status=ok 才能說記好了。"
            # 家庭圈另外四種活動（Edward 2026-08-01）
            "他若說要「揪大家一起走路比賽／出題考大家／讓大家投票決定／辦抽獎」，"
            "改呼叫 create_family_activity，kind 分別填 walk／quiz／vote／draw。"
            "投票一定要先問到問題和至少兩個選項、抽獎一定要先問到獎品、"
            "運動和問答一定要先問到截止那天，缺了就用一句話問，不要自己編。"
            "工具若回 error，照它說的原因誠實告訴他還缺什麼，不要說已經發出去了。）"
        )
    elif allow_reminders:
        base += (
            "（這一版 App 還記不了約會、聚餐這類行程。他想記行程時，誠實說你這邊還記不了、"
            "請他到「家人」頁用「發起活動」自己建一個，千萬不要拿看診或用藥提醒充數。）"
        )
    # 口袋問題（M1 PR-3 · 2026-07-27）——只給接得住的新版 App（?cap_ask=1）。
    # 這條與 chat_engine.CORE ②-B 不對稱鐵則是一組：她不判斷嚴重度、不代替醫師回答，
    # 但可以把疑問接住、存起來、讓他帶去問。這是「秘書」不是「醫生」。
    if allow_care_questions:
        base += (
            "（他聊到身體上的疑問、或講出「這個不知道要不要問醫生」「我下次問醫生看看」這類話時，"
            "你可以幫他把這個問題記進 App 的「要問醫生」清單——呼叫 add_care_question，"
            "看診前 App 會把清單提醒他，讓他不會到了診間才發現忘記問。"
            "**要先用一句話跟他確認你要記的是什麼問題**（例如「那我幫你記下來：膝蓋痠兩個禮拜、上下樓會卡，"
            "下次問醫生要不要照 X 光，這樣對嗎？」），確認過再呼叫；工具回 status=ok 才能說記好了。"
            "「這個工具的分寸」：你是幫他**保管問題**、不是**回答問題**——"
            "記下來之後不要順口幫他判斷嚴重不嚴重、不要猜可能是什麼病、不要說「應該還好」，"
            "那些都是醫生看了才知道的事（照你的安全界線走）。"
            "他只是隨口抱怨、沒有想問醫生的意思，就不要硬記；一通電話最多記兩三個真正的疑問，不要把閒聊都記成問題。"
            "「清單滿了怎麼辦」：整份清單最多 10 題（醫生一次看得完的量）。滿了工具會回"
            "status=error、error=question_list_full——這時候**不要假裝記好了**，也不要自己決定"
            "刪掉哪一題，要老實跟他說清單滿了，問他要不要換掉其中一題（例如「你已經記了十題，"
            "醫生一次差不多就是看這些。要不要先把之前那題拿掉，換成這個？」）。"
            "他說要換，就請他自己在 App 的就診摘要裡刪掉那一題——你沒有刪除的工具，不要說你幫他刪了。）"
        )
    locale_profile = locale_profile or localization.voice_session_locale_profile()
    # 口語風格（話量上限／聲音溫度／開場升溫／句尾收法／說故事／接住情緒）照語系拿。
    # 2026-07-31 Edward 拍板「口語風格也要跟著國家調」後搬成檔案：
    # 日文要敬語距離與相づち、中文要台灣國語的自然口吻——同一份稿子翻譯過去會走味。
    # 沒授書的語系自動退回中文版（不開天窗）；正本在 engine/persona/voice-style.<語系>.txt。
    base += eng._persona_text("voice-style", _book_locale)
    # Keep verified language and region policy absolutely last. The long-lived
    # Taiwan persona prompt above remains useful for the current launch, but it
    # must not override a signed non-Taiwan call context.
    locale_context = locale_profile["localeContext"]
    # 每本人設書都是為「一個國家」寫的（日文書＝日本、英文書＝美國、西班牙文書＝西班牙），
    # 裡面的急難號碼、醫療體系、法規都是那一國的。但語言不等於國家：
    # 講西班牙文的人可能在墨西哥（急難是 911、不是 112），講英文的可能在英國（是 999）。
    # 2026-07-31：這段原本寫死「不是台灣就忽略台灣的內容」——那是只有一本台灣書的年代寫的。
    # 現在改成「不是這本書的母國，就忽略書裡的號碼，改用下面那句經過核定的當地指引」。
    _book_home_country = eng.PERSONA_BOOK_HOME_COUNTRY.get(_book_locale, "TW")
    _verified_region = locale_context["safetyRegion"]
    # 2026-08-01 說明書分章第 1 刀：底下那段「兩邊不一樣就忽略書裡的號碼」的長警告，
    # 只有在**人設書的母國 ≠ 這通核定的安全區**時才有意義（例如講西班牙文但人在墨西哥）。
    # 兩邊一樣時（台灣人用中文書＝絕大多數通話）它是純肥肉：每一輪都要重讀約 500 個字元的
    # 英文警告，卻永遠不會觸發。改成只在真的不一樣時才貼——警告一字未改、保護力不變。
    base += (
        "\n[Verified locale context]\n"
        f"Conversation locale: {locale_profile['sessionLocale']}. "
        f"Country: {locale_context['countryCode']}. "
        f"Timezone: {locale_context['timeZone']}. "
        f"Safety region: {_verified_region}. "
        "Use the verified country only for local examples and services. "
    )
    if _book_home_country != _verified_region:
        base += (
            f"The persona guidance above was written for {_book_home_country}. "
            f"The verified safety region for this call is {_verified_region}. "
            "**Those two differ, so every emergency number, hotline, healthcare "
            "system detail and legal statement written into the persona guidance "
            "above is wrong for this person — ignore all of them.** Use only the "
            "regional safety guidance that follows this block, and if you are not "
            "certain of a local number, say so and tell them to contact their local "
            "emergency service rather than naming a number you are unsure of. "
            "Cultural examples and hotline numbers tied to the guidance's home "
            "country must not be repeated."
        )
    base += locale_profile["replyLanguageInstruction"]
    base += locale_profile["regionalSafetyInstruction"]
    base += localization.live_voice_code_switch_instruction(
        locale_profile["sessionLocale"],
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
                "remindBefore": types.Schema(
                    type=types.Type.INTEGER,
                    description=(
                        "提前幾分鐘提醒。只能填這五個數字之一："
                        "0（看診時間到才提醒）、30、60（一小時前）、120（兩小時前）、1440（前一天）。"
                        "他講的時間若不在這五個裡面（例如「提前三小時」），選最接近的一個，"
                        "並且說出你實際設的是哪一個，不要說成他講的那個。"
                        "他沒提到就不要填——App 會用兩小時前。"
                    ),
                ),
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
        description=(
            "把一句話轉達給家庭圈中的指定成員。**只有在你已經把整理過的內容唸給使用者聽、"
            "而且他明確說可以之後**才呼叫；他還沒點頭、或說要改，就不要呼叫。"
            "整理只能改說法不能改意思：不補他沒說的、不刪他交代的、不加自己的評論。"
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "recipientName": types.Schema(type=types.Type.STRING, description="家庭圈收件人的名稱或稱呼，例如「小宇」"),
                "message": types.Schema(type=types.Type.STRING, description=(
                    "整理成「直接對收件人說」的口氣、並且已經唸給使用者聽過、他也同意的內容，最多 240 字。"
                    "例：他說「跟他說他晚餐的藥忘記吃了」→「晚餐的藥還沒吃，記得去吃喔」。"
                )),
            },
            required=["recipientName", "message"],
        ),
    ),
])

# 「幫你記下要問醫生的問題」工具（M1 PR-3 · 2026-07-27）——口袋問題。
# 只給帶 ?cap_ask=1 的新版 App（能力握手），舊版不聲明，免得她說「幫你記下來了」卻沒有地方記＝空頭承諾。
# 邊界：這是「幫他把疑問存起來、帶去問醫生」，不是替他回答、不是分級、不是判嚴重度（見 chat_engine.CORE ②-B）。
_CARE_QUESTION_TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="add_care_question",
        description=(
            "使用者提到某個身體狀況的疑問、或表示「下次要問醫生」時呼叫，"
            "把這個問題存進 App 的「要問醫生」清單，看診前會提醒他。"
            "只存問題本身，不做任何醫療判斷或嚴重度評估。"
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "question": types.Schema(
                    type=types.Type.STRING,
                    description="要問醫生的問題，用使用者自己的話寫成一句完整的問句，最多 60 字，例如「膝蓋痠兩個禮拜了，上下樓會卡，需不需要照 X 光？」",
                ),
            },
            required=["question"],
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
    # 家庭圈的另外四種活動（Edward 2026-08-01：所有家庭圈活動都要能用講的設）。
    # 「揪一攤」留給上面的 set_personal_event（已驗過的路，不動它）；
    # 這支負責一起運動／機智問答／投票／抽獎。
    types.FunctionDeclaration(
        name="create_family_activity",
        description=(
            "使用者要「揪家人一起」做這四件事時呼叫，發到家庭圈：一起運動、機智問答、投票、抽獎。"
            "純聚餐、出遊、家人來訪這類單純的行程用 set_personal_event，不要用這支。"
            "看診用 set_clinic_reminder、吃藥用 set_medication_reminder，都不可混用。"
            "每一種需要的東西不一樣，缺了就先用一句話問清楚再呼叫，不要自己編："
            "投票一定要問題本身和至少兩個選項；抽獎一定要至少一個獎品；"
            "一起運動和機智問答一定要截止的日期。"
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "kind": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "活動種類，只能填這四個之一："
                        "walk（一起運動、比走路）、quiz（機智問答）、vote（投票、讓大家選）、draw（抽獎）。"
                    ),
                ),
                "title": types.Schema(
                    type=types.Type.STRING,
                    description="投票就填「問題本身」（例如「中秋節去哪裡吃？」）；其他種類可以留空，App 會用預設名稱。",
                ),
                "date": types.Schema(
                    type=types.Type.STRING,
                    description="日期，格式 YYYY-MM-DD。運動／問答／投票＝截止那天；抽獎＝開獎那天。相對日期要換算成實際日期。",
                ),
                "time": types.Schema(type=types.Type.STRING, description="時間，24 小時制 HH:MM。沒講就填 20:00。"),
                "options": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="投票的選項，至少兩個、最多三個。只有 kind=vote 要填。",
                ),
                "prizes": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="抽獎的獎品，至少一個、最多三個。只有 kind=draw 要填。",
                ),
                "stepGoal": types.Schema(
                    type=types.Type.INTEGER,
                    description="一起運動要走幾步（全家合計），1000 到 200000 之間，沒講就不要填（App 會用 30000 步）。只有 kind=walk 要填。",
                ),
                "questionCount": types.Schema(
                    type=types.Type.INTEGER,
                    description="機智問答要出幾題，5 到 20 之間，沒講就不要填（App 會用 10 題）。只有 kind=quiz 要填。",
                ),
            },
            required=["kind", "date"],
        ),
    ),
])

SEARCH_MODE_NATIVE = "native"
SEARCH_MODE_BRIDGE = "bridge"
SEARCH_MODE_OFF = "off"


def voice_search_mode():
    """通話中「查即時資訊」走哪條路（2026-07-28 Edward 驗測後拍板改走 native）。

    native ＝ 把 Gemini 內建的 Google 搜尋直接掛在這條通話上。她自己查、自己講，
      從頭到尾只有一個嘴巴。7/28 實測 7 通：第一聲 1.2-1.7 秒、整段最長沉默 0.2 秒
      ——根本沒有空白要蓋，所以過場句／整包暖機／5.5 秒安撫句在這個模式下全部不跑。
      查不到時她自己就會說「查不到，要不你打電話問問」，誠實度不必我們額外把關。

    bridge ＝ 舊路（2026-07-17 ~ 07-28）：掛我們自己的查詢工具，她呼叫之後由我們繞去
      另一顆模型查（實測 5.1 秒）。那 5 秒空白得靠伺服器插播過場句蓋住——而那句是另一顆
      「唸稿子」模型配的音，聲線跟她本人對不上、又得人工控速，就是 Edward 7/28 聽到的
      「系統句聲音不一樣、很卡、還跟她自己講的重疊」。程式全留著，設
      MUNEA_VOICE_SEARCH_MODE=bridge 一個字退回去。

    off ＝ 完全不給查詢能力（她會老實說不知道，靠清晨備好的今日簡報回答天氣時事）。

    沒設 MUNEA_VOICE_SEARCH_MODE 時看舊開關 MUNEA_VOICE_LIVE_LOOKUP：=1 走 native
    （正式機不必改設定就吃到新路）、其他一律 off。
    """
    raw = os.environ.get("MUNEA_VOICE_SEARCH_MODE", "").strip().lower()
    if raw in (SEARCH_MODE_NATIVE, SEARCH_MODE_BRIDGE, SEARCH_MODE_OFF):
        return raw
    return SEARCH_MODE_NATIVE if os.environ.get("MUNEA_VOICE_LIVE_LOOKUP", "0").strip() == "1" else SEARCH_MODE_OFF


def native_search_enabled():
    return voice_search_mode() == SEARCH_MODE_NATIVE


def live_lookup_enabled():
    """舊的「橋接查詢」路是否啟用（她呼叫我們的工具、我們代查、伺服器插播過場句）。
    2026-07-28 起這只在 MUNEA_VOICE_SEARCH_MODE=bridge 時為真。"""
    return voice_search_mode() == SEARCH_MODE_BRIDGE


def _voice_session_extend_enabled():
    """通話延長總開關（GoAway 重連＋context window 壓縮）。預設開——這是治「講超過
    10 分鐘被切斷」的正式修法，不是實驗性功能；跟 live_lookup_enabled 反過來（那個
    預設關，這個預設開），因為這裡的「不開」才是會讓長輩通話中途斷線的那個選項。
    留一個環境變數當逃生閥：MUNEA_VOICE_SESSION_EXTEND=0 整台退回舊行為
    （單一 session、Live API 預設時間上限、遇到就直接斷）。"""
    return os.environ.get("MUNEA_VOICE_SESSION_EXTEND", "1").strip() != "0"


def _parse_duration_seconds(value, default=5.0):
    """把 Live API 的 Duration 字串（例如 '9.5s'）轉成秒數。任何看不懂的格式一律
    退回 default，不丟例外——解析 GoAway 的剩餘時間出錯，最壞只是提早或延後幾秒
    換線，絕不能因為解析失敗把整通電話炸掉。"""
    text = str(value or "").strip()
    if not text:
        return default
    if text.endswith("s"):
        text = text[:-1]
    try:
        return max(0.0, float(text))
    except (TypeError, ValueError):
        return default


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


def _voice_rhythm_param(explicit, env_name, default, cast=int):
    """語音打斷／收話節奏參數，三層 fallback：
    ①呼叫端明確帶值（保留給未來單通話／單一使用者覆蓋——例如連線參數之後可以帶入
      使用者自己的節奏偏好；這次先把介面開好，呼叫端目前一律傳 None，還沒真的接使用者資料）
    ②環境變數（目前整機一個值；測試機可先試新節奏，正式機不設＝零改變）
    ③內建預設（＝2026-07-10 對照戶外雜音調校過的現行值）。
    這是「按使用者說話節奏調的參數」，不是專屬長輩版——不同人語速、停頓習慣不同
    （例如有人停頓較長、有人語速較快），這裡不預設是誰在講電話。"""
    if explicit is not None:
        try:
            return cast(explicit)
        except (TypeError, ValueError):
            pass
    raw = os.environ.get(env_name, "").strip()
    if raw:
        try:
            return cast(raw)
        except (TypeError, ValueError):
            pass
    return default


_VOICE_PAUSE_PROFILES = {
    # 這三檔是可回退的 A/B 旋鈕，不是假裝成 semantic VAD：Gemini 目前仍用
    # AutomaticActivityDetection，只是讓候選版能用名字測「快接話 vs 多等一下」。
    "responsive": 650,
    "balanced": 800,
    "patient": 1100,
    "adaptive": 650,
}


def _voice_pause_profile(raw):
    """把單通話／環境設定收斂成有限的節奏檔位；未知值一律忽略。"""
    token = str(raw or "").strip().lower().replace("_", "-")
    return token if token in _VOICE_PAUSE_PROFILES else None


def _voice_silence_duration(explicit_ms=None, pause_profile=None):
    """解析 Gemini AAD 的尾端靜音窗，並防止錯誤設定把整通話卡死。

    優先權：單通話毫秒值 → 單通話節奏檔 → 環境毫秒值 → 環境節奏檔 → 650ms。
    毫秒值只接受 400~2000；超界或格式錯誤就退到下一層。這裡只做可控的
    pause patience，沒有宣稱能取代語意式 turn detection。
    """
    def _bounded_ms(raw):
        if raw is None or str(raw).strip() == "":
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if 400 <= value <= 2000 else None

    explicit_value = _bounded_ms(explicit_ms)
    if explicit_value is not None:
        return explicit_value

    explicit_profile = _voice_pause_profile(pause_profile)
    if explicit_profile:
        return _VOICE_PAUSE_PROFILES[explicit_profile]

    env_value = _bounded_ms(os.environ.get("MUNEA_VOICE_SILENCE_MS"))
    if env_value is not None:
        return env_value

    env_profile = _voice_pause_profile(os.environ.get("MUNEA_VOICE_PAUSE_PROFILE"))
    if env_profile:
        return _VOICE_PAUSE_PROFILES[env_profile]
    return _VOICE_PAUSE_PROFILES["adaptive"]


def _voice_sensitivity_param(explicit, env_name, default_value, high_value, low_value):
    """同 `_voice_rhythm_param` 的三層 fallback，給 HIGH/LOW 靈敏度枚舉值用。"""
    def _map(raw):
        token = str(raw).strip().upper()
        if token in ("HIGH", "START_SENSITIVITY_HIGH", "END_SENSITIVITY_HIGH"):
            return high_value
        if token in ("LOW", "START_SENSITIVITY_LOW", "END_SENSITIVITY_LOW"):
            return low_value
        raise ValueError(token)

    if explicit is not None:
        try:
            return _map(explicit)
        except ValueError:
            pass
    raw = os.environ.get(env_name, "").strip()
    if raw:
        try:
            return _map(raw)
        except ValueError:
            pass
    return default_value


_THINKING_LEVELS = {
    "MINIMAL": types.ThinkingLevel.MINIMAL,
    "LOW": types.ThinkingLevel.LOW,
    "MEDIUM": types.ThinkingLevel.MEDIUM,
    "HIGH": types.ThinkingLevel.HIGH,
}


def _voice_thinking_level(explicit=None):
    """語音腦的「思考深度」（2026-07-27 Edward 拍板 A 案：一次只轉一個旋鈕、實測比較）。

    為什麼要有這個旋鈕：`gemini-3.1-flash-live-preview` 的 thinking_level 出廠預設是
    `minimal`（Google 為「最低延遲」調的）。但 Google 自己拿去宣稱「複雜指令遵守領先」的
    Audio MultiChallenge 成績，發表文明寫是 with 'thinking' on 測出來的——也就是說，我們
    一直用最淺的思考模式，跑一個要記五層說明書（安全紅線／語言鐵律／人格／情境／風格）、
    還要判斷何時該呼叫提醒工具的角色。這是說明書照官方建議重排之前，唯一能單獨轉、
    又能單獨看出因果的旋鈕。

    為什麼預設不動：官方對「調深會慢多少毫秒」一個數字都沒給，而語音陪伴最怕慢半拍。
    所以三層 fallback 的最底層＝None＝完全不送這個欄位＝維持 Live API 出廠預設，
    正式機零改變；要比較時在測試機設 MUNEA_VOICE_THINKING_LEVEL=low，A/B 打幾通比
    「守不守規矩」與「慢多少」，比完再決定正式機跟不跟。
    看得懂的值：minimal / low / medium / high（大小寫皆可）；寫錯或留空一律當沒設。
    """
    for raw in (explicit, os.environ.get("MUNEA_VOICE_THINKING_LEVEL", "")):
        token = str(raw or "").strip().upper()
        if token:
            level = _THINKING_LEVELS.get(token)
            if level is not None:
                return level
    return None


def live_config(char="寧寧", name=None, mood=None, topics=None, user=None, location=None, allow_reminders=False, fam=0, memory_scope=None, allow_events=False, demo_mode=False,
                 allow_care_questions=False,
                 start_sensitivity=None, end_sensitivity=None, prefix_padding_ms=None, silence_duration_ms=None,
                 pause_profile=None, resumption_handle=None, thinking_level=None, locale_profile=None):
    c = eng.CHARS.get(char) or eng.CHARS["寧寧"]
    voice = c.get("voice") or "Leda"
    locale_profile = locale_profile or localization.voice_session_locale_profile()
    # 通話中即時查詢：預設關（2026-07-17 Edward 拍板）。
    #
    # 為什麼關：正式機紀錄實測，查一次 8-9 秒、還常 TimeoutError／查不到來源。
    # 為了蓋住那 9 秒空白，得先播一句「我幫你查一下」——那句是預錄的罐頭音檔
    # （每次都一模一樣的 75406 位元組），聲線跟她本人不同，長輩一聽就知道是機器。
    # 但真人不會這樣：你問朋友「巷口那家水餃店還開嗎」，他知道就答、不知道就說
    # 「我不知道欸」，不會說「我幫你查一下」然後消失 9 秒——那是客服。
    # 而她的說明書第一條就寫著「⓪-E 去掉 AI 客服腔」：我們一邊禁止客服腔，
    # 一邊蓋了一台客服機器給她。「我幫你查一下」+9 秒空白＝客服；「我不知道欸」＝朋友。
    #
    # 那天氣時事怎麼辦：清晨備料（今日簡報）已經備好天氣、明天預告、關心提示、
    # 本週話題，直接寫在說明書裡＝秒答、不用等（正式機實測可用）。
    # 備料沒有的（那家店還開不開），就老實說不知道。
    #
    # 取捨：她會變「笨」一點（臨時時事答不出來）。但對長輩來說，
    # 一個秒回的朋友，勝過一個要等 9 秒的百科全書。
    # 退回舊行為：MUNEA_VOICE_LIVE_LOOKUP=1（程式全留著、一個字就回去）。
    tools = []
    if native_search_enabled() and not demo_mode:
        # 她自己查（2026-07-28）：Google 搜尋在 Gemini 內部完成，不繞我們伺服器一趟。
        # 7/28 實測這顆內建工具跟我們自己的提醒／傳話工具可以並存（問天氣走搜尋、
        # 說「幫我設吃藥提醒」照樣正確呼叫提醒工具），所以下面兩個 append 不受影響。
        tools.append(types.Tool(google_search=types.GoogleSearch()))
    elif live_lookup_enabled():
        if not demo_mode:
            tools.append(_LIVE_LOOKUP_TOOL)
    if allow_reminders and not demo_mode:
        tools.append(_REMINDER_TOOLS)
    if allow_events and not demo_mode:
        tools.append(_EVENT_TOOLS)
    if allow_care_questions and not demo_mode:
        tools.append(_CARE_QUESTION_TOOLS)
    # vertex25 專屬配備（2026-07-30）：附和（affective）與主動接話判斷（proactive）。
    # 預設關＝先考「同條件品質」；開了之後她會自己決定該不該接話、語氣跟情緒走。
    # 只在 vertex25 引擎下送這兩個欄位（3.1 沒有、送了會被拒連）。
    extra_cfg = {}
    if VOICE_ENGINE == "vertex25":
        if os.environ.get("MUNEA_VOICE_PROACTIVE", "0").strip() == "1":
            extra_cfg["proactivity"] = types.ProactivityConfig(proactive_audio=True)
        if os.environ.get("MUNEA_VOICE_AFFECTIVE", "0").strip() == "1":
            extra_cfg["enable_affective_dialog"] = True
    resolved_thinking = _voice_thinking_level(thinking_level)
    thinking_config = (
        types.ThinkingConfig(thinking_level=resolved_thinking)
        if resolved_thinking is not None else None
    )
    phrases = asr_adaptation_phrases(char, name, user, topics, location)
    transcription_config = types.AudioTranscriptionConfig(
        language_hints=types.LanguageHints(
            language_codes=localization.asr_language_hints(
                locale_profile["sessionLocale"],
            ),
        ),
        adaptation_phrases=phrases,
    )
    return types.LiveConnectConfig(
        **extra_cfg,
        response_modalities=["AUDIO"],
        # locale_profile 與 allow_care_questions 一律用具名傳。
        # system_instruction 的參數順序是 ..., demo_mode, allow_care_questions, locale_profile，
        # 照位置排下去會讓 locale_profile 落進 allow_care_questions 那格。
        system_instruction=system_instruction(
            char, name, mood, topics, user, location, allow_reminders, fam,
            memory_scope, allow_events, demo_mode,
            allow_care_questions=allow_care_questions,
            locale_profile=locale_profile,
        ),
        tools=tools,
        output_audio_transcription=transcription_config,
        input_audio_transcription=transcription_config,
        speech_config=types.SpeechConfig(
            language_code=locale_profile["speechLanguageCode"],
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
        # 聽話節奏（Edward 2026-07-10「戶外雜音/旁人聊天被當成我在講」定的現行值，
        # 下方四個都是「零設定＝這四個現行值、行為不變」的預設）：
        # 開口判定「低靈敏」＝要更明確、對著手機講的人聲才算你在說話——背景雜音/遠處聊天不易誤觸；
        # 結束判定同樣低靈敏；尾端靜音窗 800ms＝講話中間喘口氣不會被急著搶話。
        # 2026-07-24：四個值都改走 `_voice_rhythm_param`／`_voice_sensitivity_param` 三層
        # fallback（呼叫端明確值→環境變數→這裡的現行值當預設）——這是「按使用者說話節奏調」
        # 的參數，不是長輩專屬版；不同人語速停頓不同，未來要接單一通話/單一使用者覆蓋時，
        # 介面已經開好，不用再改這段。蕪菁頭文獻調研：句中停頓較長的使用者，測試機可試
        # MUNEA_VOICE_SILENCE_MS=1000~1200 觀察搶話是否減少（正式機預設不動）。
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=_voice_sensitivity_param(
                    start_sensitivity, "MUNEA_VOICE_START_SENSITIVITY",
                    types.StartSensitivity.START_SENSITIVITY_LOW,
                    types.StartSensitivity.START_SENSITIVITY_HIGH,
                    types.StartSensitivity.START_SENSITIVITY_LOW,
                ),
                end_of_speech_sensitivity=_voice_sensitivity_param(
                    end_sensitivity, "MUNEA_VOICE_END_SENSITIVITY",
                    types.EndSensitivity.END_SENSITIVITY_LOW,
                    types.EndSensitivity.END_SENSITIVITY_HIGH,
                    types.EndSensitivity.END_SENSITIVITY_LOW,
                ),
                prefix_padding_ms=_voice_rhythm_param(
                    prefix_padding_ms, "MUNEA_VOICE_PREFIX_PADDING_MS", 300),
                silence_duration_ms=_voice_silence_duration(
                    silence_duration_ms, pause_profile),
            ),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        ),
        # 通話延長（2026-07-25）：session_resumption 帶 handle=None 起新的、帶上次收到的
        # handle 就是「接續同一通邏輯電話」；context_window_compression 用 sliding window
        # 避免長通話把上下文塞爆。resumption_handle 只有重連時才有值——正式機沒設
        # MUNEA_VOICE_SESSION_EXTEND=0 時零改變，第一次連線 handle 一律是 None。
        session_resumption=(
            types.SessionResumptionConfig(handle=resumption_handle)
            if _voice_session_extend_enabled() else None
        ),
        context_window_compression=(
            types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow())
            if _voice_session_extend_enabled() else None
        ),
        # 思考深度（2026-07-27）：None＝不送這個欄位＝Live API 出廠預設（minimal），
        # 正式機零改變；要 A/B 比「守規矩程度 vs 慢多少」時才設 MUNEA_VOICE_THINKING_LEVEL。
        thinking_config=thinking_config,
    )


async def search_current_information(search_client, query, location=None, locale="zh-TW"):
    """Run one bounded, grounded lookup outside the Live session.

    2026-07-16 事故夜實測：gemini-2.5-flash 晚間尖峰整批回 503（客滿）＝「我幫你查一下」
    之後永遠沒下文。改成備胎鏈：主模型客滿/超時/查回來沒有真來源 → 立刻換下一顆；
    每顆模型有自己的時限、總預算由 MUNEA_LOOKUP_TIMEOUT_SECONDS 管。

    2026-07-25 壓測夜二修（主備對調反悔）：#243 把 gemini-3.1-flash-lite 設成主力
    （單次測到 2-3 秒），但 staging 壓測 4 輪 21 次查詢重現：3.1-flash-lite **常常不
    呼叫 google_search 就直接用參數知識瞎答**（grounding_metadata=None、source_count=0），
    被 extract_result 的誠實檢查擋下（設計上正確——寧可拒答也不能講假店名/假天氣），
    但因此立刻掉到備援 gemini-2.5-flash，使用者反而要多等一輪，總耗時 9.6-11 秒。
    本機用真鑰匙對 5 種問題各測 5-8 次證實：3.1-flash-lite 只有 1/5～2/8 真的帶來源、
    2.5-flash 穩定 5/5、8/8 都帶來源。

    真正的根因不是「哪顆模型」，是 gemini-2.5-flash 預設會先「思考」再答（thinking），
    這段思考才是拖到 8-11 秒的主因——關掉它（thinking_budget=0）之後同一組問題實測
    median 4.29 秒、最慢 8.30 秒、grounding 仍 8/8 全過，速度逼近 3.1-flash-lite、
    可靠度維持 2.5-flash 原本的水準。google_search 是內建檢索工具、不是一般
    function-calling 工具，試過用 tool_config(function_calling_config=ANY) 強迫呼叫
    search 直接卡死逾時（已測試排除），thinking_budget=0 才是真正划算的修法。
    所以：主備對調回來（2.5-flash 當主、3.1-flash-lite 退回最後備援——它偶爾瞎答
    會被誠實檢查擋下，當真的斷網/滿載時至少還有一顆能答），兩顆都加 thinking_budget=0
    （3.1-flash-lite 本來就不是思考模型，帶這個參數不影響行為、實測不報錯）。
    沒評估「兩顆平行賽跑取先到者」：thinking_budget=0 後 2.5-flash 已經逼近 3-4 秒
    目標、平行賽跑要多付一倍 API 成本才換到少數情況下的 1-2 秒——不划算，先不做。"""
    clean_query = live_lookup.normalize_query(query)
    if not clean_query:
        raise ValueError("lookup query is empty")
    models = [m.strip() for m in os.environ.get(
        "MUNEA_LOOKUP_MODEL", "gemini-2.5-flash,gemini-3.1-flash-lite").split(",") if m.strip()]
    per_model_s = float(os.environ.get("MUNEA_LOOKUP_PER_MODEL_SECONDS", "8"))
    last_exc = None
    for model in models:
        try:
            response = await asyncio.wait_for(
                search_client.aio.models.generate_content(
                    model=model,
                    contents=live_lookup.build_request(clean_query, location, locale),
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        # 2026-07-25：關掉「思考」——查詢答案本來就不需要延伸推理，
                        # 思考耗時才是 gemini-2.5-flash 慢的主因（實測拿掉後 8-11s→4.3s
                        # 中位數，grounding 準確度不受影響）。
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
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


def _brain_health_context(memory_scope):
    """向 Brain 要「這位來電者自己的身體狀況」（跟要『上次聊天』同一條路）。

    memory_scope＝這通的人別隔離鍵（`voice-<已驗證的 user_id>`），跟收線回寫同一個。
    拿不到就回 None——不塞任何東西，讓她那段印成「你什麼都看不到、不准編」。
    失敗只能往「她不知道」倒，絕不能往「她以為自己看得到」倒。
    """
    brain_url, brain_secret = _brain_memory_config()
    if not (brain_url and memory_scope and str(memory_scope).startswith("voice-")):
        return None
    try:
        resp = post_internal(
            brain_url, brain_secret, "/voice/health-context",
            {"userId": str(memory_scope)[len("voice-"):]}, timeout=3,
            app_key=os.environ.get("MUNEA_APP_KEY", "").strip())
    except Exception:
        return None                       # Brain 不通 → 當作看不到（不是當作沒事）
    ctx = (resp or {}).get("healthContext")
    if not isinstance(ctx, dict) or not ctx.get("facts"):
        return None                       # 認不出人 / 沒資料 → 一樣走圍籬
    return ctx
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


LOOKUP_WAIT_TEXT = live_lookup.WAIT_PHRASES[0]  # 舊常數保留相容：預設安撫句（實際輪播見 live_lookup.wait_phrase）
_LOOKUP_WAIT_PCM = {}


def _lookup_wait_pcm(char, text=LOOKUP_WAIT_TEXT, locale="zh-TW"):
    """查詢超過幾秒還沒回來時的安撫短句（2026-07-25 去罐頭化：句庫輪替，
    2026-07-30 快取鍵加入 locale，避免同字串跨語系誤用音訊。"""
    normalized_locale = localization.normalize_locale(locale)
    cache_key = (str(char or ""), normalized_locale, text)
    cached = _LOOKUP_WAIT_PCM.get(cache_key)
    if cached is not None:
        return cached
    with _LOOKUP_CUE_LOCK:
        cached = _LOOKUP_WAIT_PCM.get(cache_key)
        if cached is not None:
            return cached
        same_voice = _gemini_tts_pcm(text, char, normalized_locale)
        if same_voice:
            _LOOKUP_WAIT_PCM[cache_key] = same_voice
            return same_voice
        encoded = server.tts_b64(text, char, normalized_locale)
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


def _gemini_tts_pcm(text, char, locale="zh-TW"):
    """用她本人的聲線唸一句話（同 voice_name 的官方配音通道 · 7/16 實測 24kHz 原生同規格）。
    失敗回空 bytes、呼叫端自動退回舊配音——聲線一致是體驗、不是可用性前提。
    2026-07-25：補上 language_code，避免繁中退回通用華語腔。
    2026-07-30：language_code 跟當輪 responseLocale 走，讓英文、日文、西文過場音
    不會拿 cmn-TW 合成。"""
    try:
        _, cli = _pick_client()
        r = cli.models.generate_content(
            model=os.environ.get("MUNEA_CUE_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    language_code=localization.speech_language_code(locale),
                    voice_config=types.VoiceConfig(
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


def _lookup_cue_pcm(char, text=live_lookup.CUE_TEXT, locale="zh-TW"):
    """Generate once per (companion, locale, phrase) so a lookup can acknowledge before
    network I/O. 2026-07-25：句庫去罐頭化後同一個角色會有好幾句過場，快取鍵改成
    (char, locale, text)——只有第一次講某語系的某一句才付真的 TTS 成本。"""
    normalized_locale = localization.normalize_locale(locale)
    cache_key = (str(char or ""), normalized_locale, text)
    cached = _LOOKUP_CUE_PCM.get(cache_key)
    if cached is not None:
        return cached
    with _LOOKUP_CUE_LOCK:
        cached = _LOOKUP_CUE_PCM.get(cache_key)
        if cached is not None:
            return cached
        same_voice = _gemini_tts_pcm(text, char, normalized_locale)
        if same_voice:
            _LOOKUP_CUE_PCM[cache_key] = same_voice
            return same_voice
        encoded = server.tts_b64(text, char, normalized_locale)
        if not encoded:
            _LOOKUP_CUE_PCM[cache_key] = b""
            return b""
        with wave.open(io.BytesIO(base64.b64decode(encoded)), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 24000:
                raise ValueError("unexpected lookup cue audio format")
            pcm = wav.readframes(wav.getnframes())
        _LOOKUP_CUE_PCM[cache_key] = pcm
        return pcm


def _warm_lookup_cue_pool(char, locale="zh-TW"):
    """在 Live handshake 空檔把這個角色所有過場／安撫句都先快取好，之後不管抽到哪一句
    都不用臨時付 TTS 成本；同一個角色第二通之後這裡全是快取命中，幾乎零成本
    （沿用原本「handshake 空檔先把固定成本付掉」的設計，只是從一句擴成整個句庫）。"""
    normalized_locale = localization.normalize_locale(locale)
    for pool in live_lookup.CUE_PHRASES_BY_LOCALE[normalized_locale].values():
        for phrase in pool:
            _lookup_cue_pcm(char, phrase, normalized_locale)
    for phrase in live_lookup.WAIT_PHRASES_BY_LOCALE[normalized_locale]:
        _lookup_wait_pcm(char, phrase, normalized_locale)


def _new_call_state():
    """一通電話的可變狀態（st）。2026-07-25 抽成獨立函式：①讓 handle() 讀起來清楚
    ②讓測試能直接造一份跟正式路一模一樣的 st，不用在測試裡手刻一份、容易漏欄位或跟正式
    定義兜不起來。"""
    return {"in": 0, "out": 0, "last_in": None, "last_out": None, "echo_dropped": 0, "playout_head": 0.0, "last_hot_voice_at": 0.0, "await_first": True, "first_mic": False,
          # last_voice_at＝最後一次「真的聽到人在講話」的時刻（音量過門檻的那一格）。
          # 2026-08-01 新增：first_audio 原本從 last_in（每一格麥克風封包都會刷新，
          # 包含全靜音）起算，量到的永遠是 7-38 毫秒＝等於沒在量。反應快慢要從
          # 「他講完」到「她出聲」，所以改用這個。
          "last_voice_at": 0.0,
          "provider_silence_ms": voice_turn_semantics.FAST_TURN_MS,
          "voice_turn_seq": 0, "voice_turn_id": 0,
          "voice_turn_vad_pending": False, "voice_turn_vad_stop_at": 0.0,
          "voice_turn_target_ms": voice_turn_semantics.NORMAL_TURN_MS,
          "face_ws": None, "face_audio_url": None, "face_audio_session": None,
          "face_audio_reader": None, "face_audio_enabled": False,
          "face_audio_ready": None, "face_audio_turn_started": False,
          # 方案 B：聲音直接轉送去雲端臉的 server-to-server 連線狀態
          "user_buf": "", "ai_buf": "", "user_flagged": set(), "ai_flagged": set(),
          "guardian_real_turn_id": 0, "guardian_internal_followup_active": False,
          "guardian_internal_followup_sources": (),
          "pending_cues": [], "bg_tasks": [], "semantic_calls": 0,
          "health_topics_sent": set(), "pending_health_cue": None, "pending_promise_cue": None,  # B2 衛教：整通已注入的題＋排隊中的衛教提示

          "action_results": {}, "relay_greet_id": None,
          "language_block": False, "language_block_source": None,
          # 唸不準只記次數、不攔話（2026-08-10）。留著數字是為了看她到底多常講到那幾個詞，
          # 若真的很頻繁，正解是回頭調說明書的用詞提醒，不是再把整段話攔下來。
          "mandarin_pronunciation_seen": 0,
          "blocked_output_text": "", "language_retry_count": 0,
          "client_barge_in": False, "pending_barge_in": None,
          "barge_in_rejected": 0, "barge_post_duck_accepted": 0,
          "barge_pre_duck_accepted": 0, "asr_turns": 0, "asr_chars": 0,
          "semantic_turn_text": "", "semantic_turn_shadow_total": 0,
          "semantic_turn_shadow_holds": 0,
          # Active semantic gate delays only the first audible reply chunk after
          # a high-confidence unfinished turn. Provider VAD and barge-in remain
          # authoritative; this is a bounded, per-call adaptive playout grace.
          "semantic_turn_policy": voice_turn_semantics.AdaptiveTurnPolicy(),
          "semantic_hold_until": 0.0, "semantic_hold_reason": None,
          "semantic_hold_started_at": 0.0, "semantic_hold_ms": 0,
          "semantic_hold_last_voice_at": 0.0,
          "semantic_hold_resumed": False, "semantic_hold_voice_ms": 0.0,
          "semantic_hold_outcome_recorded": False,
          "semantic_hold_adaptation_recorded": False,
          "semantic_turn_active_holds": 0, "semantic_turn_active_resumes": 0,
          "semantic_turn_active_releases": 0,
          "barge_in_count": 0, "language_block_count": 0,
          "greet_requested": False, "opening_voice_detected": False,
          "opening_window_complete": False,
          "user_turn_started_at": None,
          "lookup_count": 0, "lookup_sources": 0, "lookup_failures": 0,
          # 她自己查（native）的帳：這一輪有沒有真的去查、查了幾句、拿回幾個來源。
          "native_search_turns": 0, "native_search_queries": 0, "native_search_sources": 0,
          "lookup_requested_at": None, "lookup_result_at": None,
          "lookup_waiting_answer": False, "lookup_cue_task": None,
          "lookup_cue_at": 0.0, "lookup_fail_streak": 0, "lookup_block_until": 0.0,
          # A read-only lookup never outranks a person who resumes speaking.
          "tool_wait_active": False, "tool_wait_event": None,
          "tool_wait_voice_ms": 0.0, "tool_wait_interrupts": 0,
          "goaway_pending": False, "goaway_deadline": None, "resumption_handle": None,  # 通話延長：GoAway 預警狀態＋最新 session resumption handle（跨底層連線延續）
          "voice_locale_profile": None, "locale_user_transcript": "",
          "locale_resolved_text": "", "locale_reconnect_requested": False,
          "locale_persistence_requested": False,
          "call_turns": []}   # 守護腦接回語音線：字幕滾動視窗／這輪已處置類別／排隊中的安全導引／背景任務集／第二層 AI 判讀次數（每通上限）；call_turns＝整通逐輪字幕，收線時交聊後管線寫記憶


async def _run_voice_session(session, cli, ws, cid, t0, st, char, location, topics, fam, day_call,
                              call_payload, gate_key, call_token, asr_context_terms,
                              first_connect, resumption_handle, voice_locale_session,
                              user_name=None):
    """跑「一條底層 Gemini Live 連線」的完整生命週期（收麥克風、送她的聲音、查詢、字幕、
    守護腦、記憶）。2026-07-25 通話延長之前，這段是直接寫在 handle() 的 async with 區塊
    裡、整通電話只跑一次；現在拆成獨立函式，讓 handle() 能在 GoAway 換線時重複呼叫，
    同一個 st／ws 在多條底層連線之間延續，App／使用者感覺不到中斷。

    first_connect=True 才會送 call-control ready、跟瀏覽器說 ready、暖機台語安全配音——
    這些只在整通電話第一次接通時做一次；重連（first_connect=False）完全跳過，
    無縫接上同一通電話，不重播開場招呼。

    回傳 (call_ended, resumption_handle)：
    - call_ended=True  → 這通電話真的結束了（使用者掛斷／真的出錯／換線次數到頂）
    - call_ended=False → 這條底層連線該換了（GoAway 預警或保底逾時），resumption_handle
      帶著最新拿到的 handle，呼叫端用它開下一條底層連線接著講。
    """
    if first_connect:
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
    else:
        # 通話延長重連（2026-07-25）：這通電話還在繼續，只是換了一條底層連線——
        # 不重送 ready、不重播開場招呼、不重打 call-control ready（那個只在第一次
        # 接通時打一次），App／使用者完全無感。await_first／user_turn_started_at
        # 重置是為了避免拿舊底層連線留下的計時基準去算這條新連線的延遲診斷。
        st["await_first"] = False
        st["user_turn_started_at"] = None
        st["goaway_pending"] = False
        st["goaway_deadline"] = None
        _diag(cid, "node.session_reconnected", handle=bool(resumption_handle))

    call_ended = False   # 這條底層連線跑完之後，由下面的 wait/branch 邏輯決定要不要換線

    def _semantic_policy():
        policy = st.get("semantic_turn_policy")
        if policy is None:
            policy = voice_turn_semantics.AdaptiveTurnPolicy()
            st["semantic_turn_policy"] = policy
        return policy

    def _record_semantic_adaptation(continued, now=None):
        """Record low-cardinality timing once; never keep audio or transcript."""
        policy = _semantic_policy()
        if st.get("semantic_hold_adaptation_recorded"):
            return policy.snapshot()
        observed_at = now if now is not None else time.monotonic()
        delay_ms = None
        if continued:
            # Measure the caller's actual pause from their last audible voice,
            # not merely the post-VAD grace window.  The latter is at most
            # 450 ms, so it could never satisfy the 700 ms slow-caller rule.
            pause_started_at = (
                st.get("semantic_hold_last_voice_at", 0.0)
                or st.get("semantic_hold_started_at", 0.0)
            )
            if pause_started_at:
                delay_ms = max(0, round((observed_at - pause_started_at) * 1000))
            policy.observe_continuation(delay_ms or st.get("semantic_hold_ms") or 0)
        else:
            policy.observe_release()
        st["semantic_hold_adaptation_recorded"] = True
        snapshot = policy.snapshot()
        _diag(
            cid,
            "node.semantic_turn_adaptive_observed",
            outcome="continued" if continued else "released",
            reason=st.get("semantic_hold_reason") or "unknown",
            delay_ms=delay_ms,
            continuation_ewma_ms=snapshot["continuation_ewma_ms"],
            samples=snapshot["continuations"] + snapshot["releases"],
        )
        return snapshot

    def _clear_semantic_hold():
        st["semantic_hold_until"] = 0.0
        st["semantic_hold_reason"] = None
        st["semantic_hold_started_at"] = 0.0
        st["semantic_hold_ms"] = 0
        st["semantic_hold_last_voice_at"] = 0.0
        st["semantic_hold_resumed"] = False
        st["semantic_hold_voice_ms"] = 0.0

    async def _persist_confirmed_locale(persistence_request):
        if not persistence_request or st.get("locale_persistence_requested"):
            return
        st["locale_persistence_requested"] = True
        action_id = "locale-" + uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        st["action_results"][action_id] = future
        try:
            await ws.send(json.dumps({
                "type": "action",
                "id": action_id,
                "action": "update_conversation_locale",
                "args": {
                    "locale": persistence_request["localeContext"]["conversationLocale"],
                },
            }, ensure_ascii=False))
            result = await asyncio.wait_for(future, timeout=8)
            _diag(
                cid,
                "node.locale_preference_persisted",
                ok=bool(isinstance(result, dict) and result.get("ok")),
            )
        except Exception as exc:
            _diag(
                cid,
                "node.locale_preference_persist_failed",
                err=f"{type(exc).__name__}:{str(exc)[:60]}",
            )
        finally:
            st["action_results"].pop(action_id, None)
            st["locale_persistence_requested"] = False

    def _resolve_locale_turn(transcript):
        text = str(transcript or "").strip()
        if not text or text == st.get("locale_resolved_text"):
            return None
        st["locale_resolved_text"] = text
        turn = voice_locale_session.resolve_spoken_turn(
            text,
            detected_languages=localization.detect_supported_languages(text),
        )
        st["voice_locale_profile"] = turn["profile"]
        decision = turn["decision"]
        intent = turn["intent"]
        if decision["sessionChanged"]:
            st["locale_reconnect_requested"] = True
        if turn["persistenceRequest"]:
            st["bg_tasks"].append(asyncio.create_task(
                _persist_confirmed_locale(turn["persistenceRequest"]),
            ))
        _diag(
            cid,
            "node.locale_turn",
            response=turn["profile"]["responseLocale"],
            session=turn["profile"]["sessionLocale"],
            intent=intent["kind"],
            code_switch=decision["codeSwitchDetected"],
            reconnect=bool(st.get("locale_reconnect_requested")),
        )
        return turn

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
                active_profile = voice_locale_session.current_profile()
                if active_profile["sessionLocale"] == "zh-TW":
                    opening = localization.voice_opening_instruction(
                        fam, topics, location, day_call,
                        has_name=bool((user_name or "").strip()),
                    )
                else:
                    opening = active_profile["openingMessage"]
                greet_cue = (
                    "（這是系統提示，絕對不要唸出這段、也不要提到系統：使用者剛接起這通電話。"
                    "請你「立刻、主動」開口打招呼，不要等對方先開口。" + _len_rule + "）"
                    + opening
                    + active_profile["replyLanguageInstruction"]
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

    async def _face_audio_read(w):
        """Forward Avatar's first-PCM ACK to the App diagnostics channel."""
        try:
            async for message in w:
                if not isinstance(message, str):
                    continue
                try:
                    payload = json.loads(message)
                except Exception:
                    continue
                if payload.get("type") == "avatar_pcm_received":
                    await ws.send(message)
        except Exception:
            pass

    async def _face_audio_off():
        fw = st.get("face_ws")
        reader = st.get("face_audio_reader")
        ready = st.get("face_audio_ready")
        st["face_ws"] = None
        st["face_audio_url"] = None
        st["face_audio_session"] = None
        st["face_audio_reader"] = None
        st["face_audio_enabled"] = False
        st["face_audio_ready"] = None
        st["face_audio_turn_started"] = False
        if ready:
            ready.set()
        if reader:
            reader.cancel()
        if fw:
            asyncio.create_task(_face_audio_close(fw))
            _diag(cid, "node.faceaudio_off")

    async def _face_audio_on(url, session_id="", token=""):
        # App 說「聲音直接幫我送去雲端臉」（方案 B · 2026-07-10）：這裡開一條 server-to-server WS 去 Modal 的
        # /audio，之後 Gemini 吐回來的聲音同一份 byte 也送這條線——不必再繞手機行動網路上行一趟。
        # 連不上/斷了都不能拖累語音對話：任何失敗都吞掉，對話照常，只是臉那次不會動（等下一次 on 訊息重試）。
        url = (url or "").strip().rstrip("/")
        if not url:
            return False
        if (st.get("face_ws") is not None
                and st.get("face_audio_url") == url
                and st.get("face_audio_session") == session_id):
            return True   # 同一顆網址已經開著，不重連（避免重複 on 事件疊連線）
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
            st["face_audio_session"] = session_id
            st["face_audio_enabled"] = False
            st["face_audio_ready"] = asyncio.Event()
            st["face_audio_turn_started"] = False
            st["face_audio_reader"] = asyncio.create_task(_face_audio_read(fw))
            _diag(cid, "node.faceaudio_on", url=url)
            return True
        except Exception as e:
            st["face_ws"] = None
            st["face_audio_url"] = None
            st["face_audio_session"] = None
            st["face_audio_reader"] = None
            st["face_audio_enabled"] = False
            st["face_audio_ready"] = None
            st["face_audio_turn_started"] = False
            _diag(cid, "node.faceaudio_err", err=f"{type(e).__name__}:{str(e)[:60]}")
            return False

    async def _face_audio_failed(fw, reason):
        reader = st.get("face_audio_reader")
        ready = st.get("face_audio_ready")
        st["face_ws"] = None
        st["face_audio_url"] = None
        st["face_audio_session"] = None
        st["face_audio_reader"] = None
        st["face_audio_enabled"] = False
        st["face_audio_ready"] = None
        st["face_audio_turn_started"] = False
        if ready:
            ready.set()
        if reader:
            reader.cancel()
        asyncio.create_task(_face_audio_close(fw))
        try:
            await ws.send(json.dumps({
                "type": "faceaudio_status", "on": False, "reason": reason,
                "turn": int(st.get("voice_turn_id") or 0),
            }))
        except Exception:
            pass

    async def _finish_face_audio_turn():
        fw = st.get("face_ws")
        if (fw is None or not st.get("face_audio_enabled")
                or not st.get("face_audio_turn_started")):
            return
        try:
            await asyncio.wait_for(fw.send("finish"), timeout=FACE_SEND_TIMEOUT_S)
            st["face_audio_turn_started"] = False
        except asyncio.TimeoutError:
            _diag(cid, "node.faceaudio_slow_dropped", timeout_s=FACE_SEND_TIMEOUT_S,
                  path="finish")
            await _face_audio_failed(fw, "finish_timeout")
        except Exception:
            await _face_audio_failed(fw, "finish_error")

    async def _reset_face_audio_turn(reason):
        fw = st.get("face_ws")
        if fw is None or not st.get("face_audio_enabled"):
            st["face_audio_turn_started"] = False
            return
        try:
            await asyncio.wait_for(fw.send("reset"), timeout=FACE_SEND_TIMEOUT_S)
            st["face_audio_turn_started"] = False
        except asyncio.TimeoutError:
            _diag(cid, "node.faceaudio_slow_dropped", timeout_s=FACE_SEND_TIMEOUT_S,
                  path="reset", reason=reason)
            await _face_audio_failed(fw, "reset_timeout")
        except Exception:
            await _face_audio_failed(fw, "reset_error")

    async def _forward_audio(chunk):
        if not chunk:
            return
        st["out"] += len(chunk)
        _fa_now = time.monotonic()
        st["last_out"] = _fa_now
        st["playout_head"] = note_playout(st.get("playout_head"), _fa_now, len(chunk))
        fw = st.get("face_ws")
        ready = st.get("face_audio_ready")
        if fw is not None and ready is not None and not ready.is_set():
            try:
                await asyncio.wait_for(ready.wait(), timeout=FACE_SEND_TIMEOUT_S)
            except asyncio.TimeoutError:
                await _face_audio_failed(fw, "arm_timeout")
            fw = st.get("face_ws")
        if fw is not None and st.get("face_audio_enabled"):
            # Direct route sends to Avatar before publishing the same chunk to
            # the App. Normal websocket writes return immediately; if the face
            # route blocks for 150 ms, disable it and notify the App *before*
            # the binary chunk so that exact chunk is relayed by the phone.
            try:
                if not st.get("face_audio_turn_started"):
                    await asyncio.wait_for(fw.send("reset"), timeout=FACE_SEND_TIMEOUT_S)
                    turn_id = int(st.get("voice_turn_id") or 0)
                    if turn_id:
                        await asyncio.wait_for(
                            fw.send("turn:" + str(turn_id)), timeout=FACE_SEND_TIMEOUT_S,
                        )
                    st["face_audio_turn_started"] = True
                await asyncio.wait_for(fw.send(chunk), timeout=FACE_SEND_TIMEOUT_S)
            except asyncio.TimeoutError:
                _diag(cid, "node.faceaudio_slow_dropped", timeout_s=FACE_SEND_TIMEOUT_S, path="forward")
                await _face_audio_failed(fw, "forward_timeout")
            except Exception:
                await _face_audio_failed(fw, "forward_error")
        await ws.send(chunk)

    async def _mark_first_audio(source):
        if not st.get("await_first") or st.get("last_in") is None:
            return
        # 2026-08-01 量測修正：起點改成「最後一次真的聽到人聲」（算法與理由見 reply_latency_ms）。
        latency_ms, basis = reply_latency_ms(
            time.monotonic(), st.get("last_voice_at") or 0.0, st["last_in"])
        st["await_first"] = False
        now = time.monotonic()
        turn_id = int(st.get("voice_turn_id") or 0)
        vad_stop_at = float(st.get("voice_turn_vad_stop_at") or 0.0)
        after_vad_ms = round(max(0.0, now - vad_stop_at) * 1000) if vad_stop_at else None
        _diag(
            cid, "node.first_audio", latency_ms=latency_ms, source=source,
            basis=basis, turn=turn_id, after_vad_ms=after_vad_ms,
        )
        try:
            await ws.send(json.dumps({
                "type": "voice_turn_timing",
                "stage": "voice_first_pcm",
                "turn": turn_id,
                "afterLastVoiceMs": latency_ms,
                "afterVadMs": after_vad_ms,
                "basis": basis,
                "source": source,
            }))
        except Exception:
            pass

    async def _send_lookup_cue(category, locale):
        cue_started = time.monotonic()
        # 貼題輪替（2026-07-25 去罐頭化）：用這通已經查過幾次當index，
        # 同一類問題問第二次就換下一句，不會整通電話都聽到同一句。
        phrase = live_lookup.cue_phrase(
            category, st["lookup_count"], locale=locale,
        )
        await ws.send(json.dumps({
            "type": "caption", "who": "nening", "text": phrase,
        }, ensure_ascii=False))
        try:
            # 2026-07-25 修正：句庫去罐頭化前，st["lookup_cue_task"] 是「先幫忙生好這
            # 唯一一句」的預熱任務，等它等於等這句音檔，值得 await。去罐頭化後它變成
            # 「把整個句庫都先生好」的背景任務（十幾句 TTS，實測可能跑好幾秒到幾十秒）——
            # 這裡若繼續 await 它，會變成每次查詢都被整個句庫的暖機拖住，首次查詢反而比
            # 修改前更慢（本機真跑測到整通卡到 30 秒逾時）。改成不等它，直接拿「這一句」：
            # _lookup_cue_pcm 自己有鎖＋快取，暖機已經做完就秒回，還沒做完就它自己單獨
            # 補一句（跟原本沒有暖機時的成本一樣，不會比修改前更差）。
            pcm = await asyncio.get_running_loop().run_in_executor(
                _VOICE_CUE_EXECUTOR, _lookup_cue_pcm, char, phrase, locale)
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
            phrase=phrase, category=category, locale=locale,
            latency_ms=round((time.monotonic() - cue_started) * 1000),
        )
        return bool(pcm)

    async def _run_live_lookup(fargs, cue_already_spoken=False):
        query = live_lookup.normalize_query((fargs or {}).get("query"))
        lookup_location = str((fargs or {}).get("location") or location or "").strip()[:80]
        active_profile = voice_locale_session.current_profile()
        response_locale = active_profile["responseLocale"]
        category = live_lookup.classify_query_topic(
            query, locale=response_locale,
        )  # 貼題過場話用：天氣/新聞/店家景點/其他
        st["lookup_count"] += 1
        st["lookup_requested_at"] = time.monotonic()
        asr_started = st.get("user_turn_started_at")
        _diag(
            cid, "node.lookup_requested", query_chars=len(query),
            has_location=bool(lookup_location), locale=response_locale,
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
                "instruction": live_lookup.failure_instruction(
                    "unavailable", response_locale,
                ),
            }

        _tool_event = asyncio.Event()
        st["tool_wait_active"] = True
        st["tool_wait_event"] = _tool_event
        st["tool_wait_voice_ms"] = 0.0

        if cue_already_spoken:
            cue_audio = True
            _diag(cid, "node.lookup_cue_sent", audio="model", out_bytes=0, latency_ms=0, category=category)
        elif _lk_now - st.get("lookup_cue_at", 0) < 30:
            # 過場句 30 秒內不重播（重試時默默查、不再「我幫你查一下」轟炸）
            cue_audio = False
            _diag(cid, "node.lookup_cue_skipped", reason="recently_played")
        else:
            st["lookup_cue_at"] = _lk_now
            cue_audio = await _send_lookup_cue(category, response_locale)
        network_started = time.monotonic()
        _diag(cid, "node.lookup_started", cue_audio=cue_audio, category=category)

        async def _send_wait_cue():
            # 查太久（備胎鏈換手時）不讓長輩對著沉默等：5.5 秒還沒回來就先安撫一句
            # （2026-07-25 去罐頭化：句庫輪替，不再固定唸同一句）
            await asyncio.sleep(5.5)
            wait_text = live_lookup.wait_phrase(
                st["lookup_count"], locale=response_locale,
            )
            try:
                pcm = await asyncio.get_running_loop().run_in_executor(
                    _VOICE_CUE_EXECUTOR, _lookup_wait_pcm, char, wait_text,
                    response_locale)
            except Exception:
                pcm = b""
            if not pcm:
                return
            await ws.send(json.dumps({
                "type": "caption", "who": "nening", "text": wait_text,
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
            result = await voice_tool_continuity.run_interruptible(
                search_current_information(
                    cli, query, lookup_location, locale=response_locale,
                ),
                _tool_event,
                float(os.environ.get("MUNEA_LOOKUP_TIMEOUT_SECONDS", "13")),
            )
        except voice_tool_continuity.ToolWaitInterrupted:
            st["tool_wait_interrupts"] += 1
            st["lookup_result_at"] = time.monotonic()
            st["lookup_waiting_answer"] = False
            _diag(
                cid,
                "node.lookup_cancelled_user_resumed",
                latency_ms=round((st["lookup_result_at"] - network_started) * 1000),
            )
            return {
                "status": "cancelled",
                "error": "user_resumed",
                "instruction": live_lookup.user_resumed_instruction(response_locale),
            }
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
                "instruction": live_lookup.failure_instruction(
                    "timeout", response_locale,
                ),
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
                "instruction": live_lookup.failure_instruction(
                    "failed", response_locale,
                ),
            }
        finally:
            # 查詢一有結果（成功或失敗）就取消「還在找」安撫句——別讓它插在答案中間
            wait_cue_task.cancel()
            if st.get("tool_wait_event") is _tool_event:
                st["tool_wait_active"] = False
                st["tool_wait_event"] = None
                st["tool_wait_voice_ms"] = 0.0

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
            await _finish_face_audio_turn()
        await ws.send(json.dumps({"type": "turn_complete"}))
        _diag(cid, "node.language_fallback", source=source, out_bytes=len(pcm))

    # 2026-08-10 移除 _send_safe_mandarin_tts()：它是「唸不準就換一個安全配音把整段
    # 重唸一次」的最後手段，唯一呼叫點是 mandarin_pronunciation 那條路。那條路已經改成
    # 只記錄不攔（見下方 node.mandarin_pronunciation_seen），所以這支永遠不會再被呼叫。
    # 留著只會讓下一個讀的人以為系統還會換聲線——Edward 8/10 真機聽到的
    #「突然跳出一個不同聲音的人」就是它。台語輸出的收尾走 _send_hokkien_fallback()，不受影響。

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
        await _reset_face_audio_turn("language_block")
        _diag(cid, "node.language_block", source=source)

    async def from_browser():
        async for message in ws:
            if isinstance(message, (bytes, bytearray)):
                n = len(message)
                st["in"] += n
                st["last_in"] = time.monotonic()
                # 2026-08-01：原本這裡每收一格麥克風封包就重新舉手要量 first_audio，
                # 等於一輪內反覆量、而且起點永遠是「剛剛那一格」。改成只在真的聽到
                # 人聲時舉手（見下方門檻判斷），一輪一次、起點是他講的最後一聲。
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
                # v2：窗以「手機大概播到哪」為準（in_playout_window）；送出時間窗當後備。
                _eg_window = (in_playout_window(_eg_now, st.get("playout_head"))
                              or in_output_window(_eg_now, st.get("last_out")))
                # 2026-07-30 熱門檻：她講話中（水位在前方）要求更大聲才算真插話——
                # 治「喇叭開大→她自己的聲音被當插話→講到一半自己閉嘴」（telemetry 實錘）
                _eg_rms = frame_rms(message)
                _eg_hot = hot_threshold(_eg_now, st.get("playout_head"))
                _voice_frame_ms = len(message) / float(16000 * 2) * 1000.0
                _above_voice_threshold = _eg_rms >= _eg_hot

                # A semantic hold is only converted into a real continuation
                # after sustained microphone evidence. One loud frame is not
                # enough; that would turn a door knock into a cancelled reply.
                if (
                    st.get("semantic_hold_until", 0.0) > _eg_now
                    and not st.get("semantic_hold_resumed")
                ):
                    _hold_voice_ms, _hold_resumed = voice_tool_continuity.sustained_voice_ms(
                        st.get("semantic_hold_voice_ms", 0.0),
                        _above_voice_threshold,
                        _voice_frame_ms,
                        trigger_ms=120,
                    )
                    st["semantic_hold_voice_ms"] = _hold_voice_ms
                    if _hold_resumed:
                        st["semantic_hold_resumed"] = True
                        adaptive = _record_semantic_adaptation(True, _eg_now)
                        _diag(
                            cid,
                            "node.semantic_turn_active_resumed",
                            reason=st.get("semantic_hold_reason") or "unknown",
                            evidence_ms=round(_hold_voice_ms),
                            continuation_ewma_ms=adaptive["continuation_ewma_ms"],
                        )

                # Read-only lookup work is cancellable when the person resumes.
                # The event wakes the lookup coroutine; microphone streaming to
                # Gemini continues normally, so the latest utterance wins.
                _tool_event = st.get("tool_wait_event")
                if st.get("tool_wait_active") and _tool_event is not None and not _tool_event.is_set():
                    _tool_voice_ms, _tool_resumed = voice_tool_continuity.sustained_voice_ms(
                        st.get("tool_wait_voice_ms", 0.0),
                        _above_voice_threshold,
                        _voice_frame_ms,
                        trigger_ms=180,
                    )
                    st["tool_wait_voice_ms"] = _tool_voice_ms
                    if _tool_resumed:
                        _tool_event.set()
                        _diag(
                            cid,
                            "node.tool_wait_user_resumed",
                            evidence_ms=round(_tool_voice_ms),
                        )
                # Two-phase barge-in: after barge_in_start, retain a short copy of
                # the already-captured microphone onset. Do not forward or drop it
                # until the commit message arrives and the server has judged the
                # actual audio evidence. A stale start self-clears after one second.
                _pending_barge = st.get("pending_barge_in")
                if _pending_barge:
                    if _eg_now - _pending_barge.get("started_at", 0.0) <= 1.0:
                        _frame_ms = len(message) / float(16000 * 2) * 1000.0
                        _pending_barge["frames"].append((bytes(message), _eg_rms, _frame_ms))
                        if len(_pending_barge["frames"]) > 32:
                            del _pending_barge["frames"][:-32]
                        continue
                    st["pending_barge_in"] = None
                    _diag(cid, "node.barge_in_evidence_timeout")
                if _eg_window and _eg_rms >= _eg_hot:
                    st["last_hot_voice_at"] = _eg_now   # 窗內聽到真的夠大聲＝可信的人聲（插話裁判的依據）
                if _eg_rms >= _eg_hot:
                    # 2026-08-01 反應時間量測的起點：這一格夠大聲＝他正在講話。
                    # 他講整句的期間這裡會一直更新，所以停下來的那一刻就是「他講完」。
                    # （她講話中時 _eg_hot 是熱門檻、殘響不會誤算成人聲；她沒講話時就是原門檻。）
                    st["last_voice_at"] = _eg_now
                    st["await_first"] = True
                if _eg_window and guard_enabled() and _eg_rms < _eg_hot:
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
                    locale_turn = _resolve_locale_turn(obj["text"])
                    active_profile = (
                        locale_turn["profile"] if locale_turn
                        else voice_locale_session.current_profile()
                    )
                    if (
                        active_profile["responseLocale"] == "zh-TW"
                        and localization.requires_taiwanese_hokkien_fallback(obj["text"])
                    ):
                        await _send_hokkien_fallback("text_input")
                    else:
                        prompt = (
                            str(obj["text"])
                            + active_profile["replyLanguageInstruction"]
                            + active_profile["regionalSafetyInstruction"]
                        )
                        await session.send_client_content(
                            turns=types.Content(role="user", parts=[types.Part(text=prompt)]),
                            turn_complete=True,
                        )
                elif t == "audio_end":
                    await session.send_realtime_input(audio_stream_end=True)
                elif t == "barge_in_start":
                    # Buffer the ordered evidence frames that follow. Existing
                    # clients send pre-duck pre-roll only; fixed clients append a
                    # declared post-duck tail so the destructive decision can use
                    # fresh microphone evidence while retaining the first syllable.
                    _bi_started_at = time.monotonic()
                    try:
                        _post_duck_frames = min(12, max(0, int(obj.get("post_duck_frames") or 0)))
                    except (TypeError, ValueError):
                        _post_duck_frames = 0
                    try:
                        _post_duck_sustain_ms = min(120, max(60, int(obj.get("post_duck_sustain_ms") or 80)))
                    except (TypeError, ValueError):
                        _post_duck_sustain_ms = 80
                    st["pending_barge_in"] = {
                        "started_at": _bi_started_at,
                        "threshold_pcm": normalized_rms_to_pcm16(obj.get("threshold")),
                        "sustain_ms": obj.get("sustain_ms", 150),
                        "playout_active": in_playout_window(_bi_started_at, st.get("playout_head")),
                        "post_duck_frames": _post_duck_frames,
                        "post_duck_sustain_ms": _post_duck_sustain_ms,
                        "frames": [],
                    }
                    _diag(cid, "node.barge_in_evidence_started",
                          frames=obj.get("evidence_frames") or 0,
                          post_duck_frames=_post_duck_frames,
                          playout_active=st["pending_barge_in"]["playout_active"])
                elif t == "barge_in":
                    # 2026-07-30 插話裁判（治「喇叭開大→她自己的聲音觸發手機端插話→自己閉嘴」）：
                    # 手機端的插話偵測分不出「你在說話」跟「她自己的大聲回音」（退回手機播音
                    # 模式時系統回音消除顧不到那條路、7/16 已點名）。新 App 先送 start、
                    # 再送預捲音訊、最後 commit；伺服器用同一個持續人聲規則判斷，通過後才把
                    # 留住的開頭交給 Gemini。舊 App 沒有 start 時，保留 0.6 秒熱門檻判法。
                    _bi_now = time.monotonic()
                    _pending_barge = st.get("pending_barge_in")
                    st["pending_barge_in"] = None
                    _evidence_ms = 0.0
                    _onset_index = 0
                    _evidence_basis = "legacy"
                    _evidence_threshold = 0.0
                    if _pending_barge:
                        _levels = [(rms, frame_ms) for _, rms, frame_ms in _pending_barge["frames"]]
                        _client_threshold = _pending_barge["threshold_pcm"]
                        _post_duck_frames = min(
                            len(_levels),
                            max(0, int(_pending_barge.get("post_duck_frames") or 0)),
                        )
                        if _post_duck_frames:
                            # New clients keep collecting microphone frames after
                            # the speaker has been ducked.  Judge only that tail:
                            # real nearby speech continues, speaker echo collapses.
                            _decision_levels = _levels[-_post_duck_frames:]
                            _decision_sustain_ms = _pending_barge.get("post_duck_sustain_ms", 80)
                            _evidence_threshold = barge_evidence_threshold(
                                _client_threshold, playout_active=False,
                            )
                            _evidence_basis = "post_duck"
                            _minimum_evidence_ms = 60.0
                        else:
                            # Existing installed clients only send pre-duck
                            # pre-roll.  Their adaptive threshold is not safe for
                            # a destructive interruption while the assistant is
                            # playing, so apply the dedicated hot evidence gate.
                            _decision_levels = _levels
                            _decision_sustain_ms = _pending_barge["sustain_ms"]
                            _playout_active = bool(_pending_barge.get("playout_active"))
                            _evidence_threshold = barge_evidence_threshold(
                                _client_threshold, playout_active=_playout_active,
                            )
                            _evidence_basis = "pre_duck_hot" if _playout_active else "pre_duck_idle"
                            _minimum_evidence_ms = 120.0
                        _accepted, _evidence_ms, _onset_index = sustained_voice_evidence(
                            _decision_levels,
                            _evidence_threshold,
                            _decision_sustain_ms,
                            minimum_ms=_minimum_evidence_ms,
                        )
                        # Acceptance uses the safe decision slice above, but
                        # replay still starts at the original speech onset so a
                        # genuine interruption does not lose its first syllable.
                        _, _, _onset_index = sustained_voice_evidence(
                            _levels,
                            _client_threshold,
                            _pending_barge["sustain_ms"],
                        )
                    else:
                        _accepted = not (
                            in_playout_window(_bi_now, st.get("playout_head"))
                            and _bi_now - st.get("last_hot_voice_at", 0.0) > 0.6
                        )
                    if not _accepted:
                        st["barge_in_rejected"] = st.get("barge_in_rejected", 0) + 1
                        _diag(cid, "node.barge_in_rejected_echo",
                              count=st["barge_in_rejected"], evidence_ms=round(_evidence_ms),
                              evidence_basis=_evidence_basis,
                              threshold_pcm=round(_evidence_threshold))
                        try:
                            await ws.send(json.dumps({"type": "barge_in_ack", "accepted": False,
                                                      "reason": "echo", "evidence_ms": round(_evidence_ms),
                                                      "evidence_basis": _evidence_basis}))
                        except Exception:
                            pass
                        continue
                    st["playout_head"] = 0.0   # App 已清掉未播聲音，回音窗立刻收
                    st["client_barge_in"] = True
                    st["barge_in_count"] += 1
                    if _evidence_basis == "post_duck":
                        st["barge_post_duck_accepted"] += 1
                    elif _evidence_basis.startswith("pre_duck"):
                        st["barge_pre_duck_accepted"] += 1
                    st["last_voice_at"] = _bi_now
                    st["await_first"] = True
                    # Replay from one frame before the detected onset so the
                    # user's first consonant is not lost, without replaying the
                    # whole assistant-echo window.
                    if _pending_barge:
                        for _audio, _, _ in _pending_barge["frames"][max(0, _onset_index - 1):]:
                            await session.send_realtime_input(
                                audio=types.Blob(data=_audio, mime_type="audio/pcm;rate=16000")
                            )
                    await ws.send(json.dumps({"type": "barge_in_ack", "accepted": True,
                                              "evidence_ms": round(_evidence_ms),
                                              "evidence_basis": _evidence_basis}))
                    await _reset_face_audio_turn("client_barge_in")
                    _diag(cid, "node.client_barge_in", evidence_ms=round(_evidence_ms),
                          evidence_basis=_evidence_basis,
                          threshold_pcm=round(_evidence_threshold))
                elif t == "faceaudio":
                    # {"type":"faceaudio","on":true,"url":"..."} 開＝伺服器對伺服器直送雲端臉；on:false 或掛斷＝收線
                    if obj.get("on"):
                        direct_on = await _face_audio_on(
                            obj.get("url") or "",
                            obj.get("session") or "",
                            obj.get("token") or call_token,
                        )
                        await ws.send(json.dumps({
                            "type": "faceaudio_status", "on": bool(direct_on),
                            "reason": "ready" if direct_on else "connect_failed",
                        }))
                        st["face_audio_enabled"] = bool(direct_on)
                        ready = st.get("face_audio_ready")
                        if ready:
                            ready.set()
                    else:
                        await _face_audio_off()
                        await ws.send(json.dumps({
                            "type": "faceaudio_status", "on": False,
                            "reason": "client_disabled",
                        }))

    async def from_live():
        # session.receive() 每輪結束就收（SDK 行為）；外層 while 讓「一輪接完再等下一輪」＝多輪對話不斷。
        # 2026-07-25 通話延長：整段包一層 try/except——GoAway 預警後底層連線遲早會被
        # Gemini 收掉，這是「預期中的收線」，跟真的斷線／出錯要分開處理；回傳值
        # "reconnect" 交給外層換一條底層連線接著講，"ended" 才是這通真的結束了。
        try:
            while True:
                st["face_audio_turn_started"] = False
                turn_out = 0
                turn_max_gap_ms = 0.0   # 這一輪送聲音時，相鄰兩塊之間最久的一次空檔（抖動指標）
                turn_last_out = None    # 這一輪送出的上一塊聲音是幾點（2026-08-01：抖動只跟同一輪比）
                got = False
                async for msg in session.receive():
                    got = True
                    # 通話延長（2026-07-25）：GoAway＝伺服器預告「這條底層連線快到期了」
                    # （time_left 通常留了緩衝，不是馬上斷）；session_resumption_update
                    # 帶新的 handle，之後重連要帶著這個 handle 才能接上同一通邏輯電話。
                    # 這兩種訊息沒有 server_content，跟其他訊息並存在同一個 receive() 迴圈裡。
                    go_away = getattr(msg, "go_away", None)
                    if go_away is not None:
                        seconds = _parse_duration_seconds(getattr(go_away, "time_left", None))
                        st["goaway_pending"] = True
                        st["goaway_deadline"] = time.monotonic() + max(0.0, seconds - GOAWAY_RECONNECT_MARGIN_S)
                        _diag(cid, "node.goaway", time_left=getattr(go_away, "time_left", None) or "-")
                    sru = getattr(msg, "session_resumption_update", None)
                    if sru is not None and getattr(sru, "resumable", False) and getattr(sru, "new_handle", None):
                        st["resumption_handle"] = sru.new_handle
                        _diag(cid, "node.session_resumption_update")
                    sc = getattr(msg, "server_content", None)
                    if sc:
                        it_pre = getattr(sc, "input_transcription", None)
                        if it_pre and getattr(it_pre, "text", None):
                            if st.get("user_turn_started_at") is None:
                                st["user_turn_started_at"] = time.monotonic()
                                _guardian_begin_real_user_turn(st)
                            st["voice_turn_vad_pending"] = True
                            current_profile = (
                                st.get("voice_locale_profile")
                                or voice_locale_session.current_profile()
                            )
                            transcript = localization.reconcile_context_transcription(
                                it_pre.text,
                                asr_context_terms,
                                current_profile["sessionLocale"],
                            )
                            st["locale_user_transcript"] = (
                                st.get("locale_user_transcript", "") + transcript
                            )[-600:]
                            st["semantic_turn_text"] = (
                                st.get("semantic_turn_text", "") + transcript
                            )[-240:]
                            locale_turn = _resolve_locale_turn(
                                st["locale_user_transcript"],
                            )
                            if locale_turn:
                                current_profile = locale_turn["profile"]
                            st["asr_turns"] += 1
                            st["asr_chars"] += len(transcript)
                            if st.get("client_barge_in"):
                                st["client_barge_in"] = False
                                _diag(cid, "node.client_barge_in_heard")
                            is_hokkien = (
                                current_profile["responseLocale"] == "zh-TW"
                                and localization.requires_taiwanese_hokkien_fallback(transcript)
                            )
                            _diag(cid, "node.asr_input", chars=len(transcript), language_block=is_hokkien)
                            if is_hokkien:
                                await _arm_language_block("audio_input")
                        if (
                            it_pre
                            and getattr(it_pre, "finished", False)
                            and st.get("voice_turn_vad_pending")
                        ):
                            st["voice_turn_vad_pending"] = False
                            semantic_text = st.pop("semantic_turn_text", "")
                            st["semantic_turn_text"] = ""
                            vad_stop_at = time.monotonic()
                            st["voice_turn_seq"] = int(st.get("voice_turn_seq") or 0) + 1
                            st["voice_turn_id"] = st["voice_turn_seq"]
                            st["voice_turn_vad_stop_at"] = vad_stop_at
                            _semantic_shadow = voice_turn_semantics.semantic_turn_shadow_enabled()
                            _semantic_active = voice_turn_semantics.semantic_turn_active_enabled()
                            if _semantic_shadow or _semantic_active:
                                current_profile = (
                                    st.get("voice_locale_profile")
                                    or voice_locale_session.current_profile()
                                )
                                hint = voice_turn_semantics.classify_turn_end(
                                    semantic_text,
                                    current_profile["sessionLocale"],
                                )
                                if hint.supported:
                                    # A new provider-finished input means a
                                    # resumed thought reached its next boundary.
                                    # Retire the older hold so the answer to this
                                    # newer, complete utterance is not suppressed.
                                    if (
                                        st.get("semantic_hold_resumed")
                                        and st.get("semantic_hold_reason")
                                        and not st.get("semantic_hold_outcome_recorded")
                                    ):
                                        st["semantic_turn_active_resumes"] += 1
                                        st["semantic_hold_outcome_recorded"] = True
                                        _diag(
                                            cid,
                                            "node.semantic_turn_active_continued",
                                            reason=st.get("semantic_hold_reason"),
                                        )
                                        _clear_semantic_hold()
                                    if _semantic_shadow:
                                        st["semantic_turn_shadow_total"] += 1
                                        if hint.decision == "hold":
                                            st["semantic_turn_shadow_holds"] += 1
                                        _diag(
                                            cid,
                                            "node.semantic_turn_shadow",
                                            decision=hint.decision,
                                            reason=hint.reason,
                                            chars=len(semantic_text),
                                            provider_finished=True,
                                        )
                                    policy = _semantic_policy()
                                    provider_ms = int(
                                        st.get("provider_silence_ms")
                                        or voice_turn_semantics.FAST_TURN_MS
                                    )
                                    target_ms = policy.target_ms(hint)
                                    hold_ms = policy.hold_ms(hint, provider_ms)
                                    st["voice_turn_target_ms"] = target_ms
                                    last_voice_at = float(st.get("last_voice_at") or 0.0)
                                    after_last_voice_ms = (
                                        round(max(0.0, vad_stop_at - last_voice_at) * 1000)
                                        if last_voice_at else None
                                    )
                                    await ws.send(json.dumps({
                                        "type": "voice_turn_timing",
                                        "stage": "vad_stop",
                                        "turn": st["voice_turn_id"],
                                        "afterLastVoiceMs": after_last_voice_ms,
                                        "providerSilenceMs": provider_ms,
                                        "targetMs": target_ms,
                                        "class": hint.reason,
                                        "slowCaller": policy.is_slow_caller(),
                                    }))
                                    if hold_ms and _semantic_active:
                                        hold_started_at = time.monotonic()
                                        st["semantic_hold_until"] = hold_started_at + hold_ms / 1000.0
                                        st["semantic_hold_reason"] = hint.reason
                                        st["semantic_hold_started_at"] = hold_started_at
                                        st["semantic_hold_ms"] = hold_ms
                                        st["semantic_hold_last_voice_at"] = last_voice_at
                                        st["semantic_hold_resumed"] = False
                                        st["semantic_hold_voice_ms"] = 0.0
                                        st["semantic_hold_outcome_recorded"] = False
                                        st["semantic_hold_adaptation_recorded"] = False
                                        st["semantic_turn_active_holds"] += 1
                                        adaptive = policy.snapshot()
                                        _diag(
                                            cid,
                                            "node.semantic_turn_active_armed",
                                            reason=hint.reason,
                                            hold_ms=hold_ms,
                                            total_target_ms=target_ms,
                                            provider_silence_ms=provider_ms,
                                            adaptive_samples=(
                                                adaptive["continuations"] + adaptive["releases"]
                                            ),
                                            chars=len(semantic_text),
                                        )
                        # 她自己查（native）留下的憑證。2026-08-10 之前完全沒讀，
                        # 所以「她說我幫你查一下、結果憑印象亂講」跟「她真的查了」
                        # 在日誌上長得一模一樣——誠實紅線最需要證據的地方反而是空的。
                        # 這裡只記數量，不留查詢內容本身。
                        gm = getattr(sc, "grounding_metadata", None)
                        if gm is not None:
                            _queries = list(getattr(gm, "web_search_queries", None) or [])
                            _chunks = list(getattr(gm, "grounding_chunks", None) or [])
                            if _queries or _chunks:
                                st["native_search_turns"] += 1
                                st["native_search_queries"] += len(_queries)
                                st["native_search_sources"] += len(_chunks)
                                _diag(
                                    cid, "node.native_search",
                                    queries=len(_queries), sources=len(_chunks),
                                )

                        ot_pre = getattr(sc, "output_transcription", None)
                        if ot_pre and getattr(ot_pre, "text", None):
                            current_profile = (
                                st.get("voice_locale_profile")
                                or voice_locale_session.current_profile()
                            )
                            output_locale = current_profile["responseLocale"]
                            output_text = localization.canonicalize_transcription(
                                ot_pre.text,
                                output_locale,
                            )
                            st["blocked_output_text"] = (st["blocked_output_text"] + output_text)[-600:]
                            if (
                                output_locale == "zh-TW"
                                and localization.looks_like_taiwanese_hokkien_output(
                                    st["blocked_output_text"]
                                )
                            ):
                                await _arm_language_block("model_output")
                            elif (
                                output_locale == "zh-TW"
                                and localization.contains_unstable_mandarin_speech(output_text)
                            ):
                                # 2026-08-10：這裡以前跟台語走同一條路——攔下整段、
                                # 叫她重講、再用備用配音唸出來。Edward 真機問「最近有什麼
                                # 電影」踩到：她說「看你的興趣」就中招，結果
                                #   · 她的聲音被整包丟掉 77 次 ≈ 21.5 秒的話
                                #   · 系統叫她重講，一輪要重生 20 秒 → 第一聲等了 26 秒
                                #   · 備用配音（不是寧寧的聲音）把答案唸完 → 使用者聽到
                                #     「突然跳出一個不同聲音的人」
                                # 藥比病重太多：一個詞唸得怪，代價卻是整段話消失＋換人講話。
                                # 台語那道是產品規則（還沒開放）必須攔；唸不準只是好聽與否，
                                # 改成只記錄不攔。要她少用那幾個詞，靠說明書那句提醒就好。
                                st["mandarin_pronunciation_seen"] = (
                                    st.get("mandarin_pronunciation_seen", 0) + 1
                                )
                                _diag(
                                    cid, "node.mandarin_pronunciation_seen",
                                    count=st["mandarin_pronunciation_seen"],
                                )
                    data = getattr(msg, "data", None)
                    if data and not st.get("language_block") and not st.get("client_barge_in"):
                        _semantic_reason = st.get("semantic_hold_reason")
                        if _semantic_reason and not st.get("semantic_hold_outcome_recorded"):
                            _remaining = max(
                                0.0,
                                st.get("semantic_hold_until", 0.0) - time.monotonic(),
                            )
                            if _remaining and not st.get("semantic_hold_resumed"):
                                await asyncio.sleep(_remaining)
                            if st.get("semantic_hold_resumed"):
                                # The user continued before the old answer became
                                # audible. Suppress that answer exactly like a
                                # barge-in; provider AAD still receives the audio
                                # and owns the actual model interruption.
                                st["client_barge_in"] = True
                                st["semantic_turn_active_resumes"] += 1
                                _diag(
                                    cid,
                                    "node.semantic_turn_active_cancelled",
                                    reason=_semantic_reason,
                                )
                            else:
                                st["semantic_turn_active_releases"] += 1
                                _record_semantic_adaptation(False)
                                _diag(
                                    cid,
                                    "node.semantic_turn_active_released",
                                    reason=_semantic_reason,
                                )
                            st["semantic_hold_outcome_recorded"] = True
                            _clear_semantic_hold()
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
                        turn_out += len(data)
                        # 2026-07-29：量「送聲音的手抖不抖」。Edward 7/28 回報「句尾的最後一句
                        # 會卡其中某個字」，但體感沒有數字就查不動——這裡記下相鄰兩塊聲音之間
                        # 最久的一次空檔，收在 turn_done 一起報。手順的時候這個值很小；
                        # 一旦有東西在跟它搶（7/28 那包 76 秒的暖機就是），這裡會立刻看得出來。
                        # 2026-08-01 量測修正：空檔只跟「這一輪的上一塊」比（算法與理由見
                        # note_turn_gap）。st["last_out"] 仍要更新——回音濾網要用它。
                        _now_out = time.monotonic()
                        turn_max_gap_ms, _ = note_turn_gap(_now_out, turn_last_out, turn_max_gap_ms)
                        turn_last_out = _now_out
                        # 唯一音訊出口：先嘗試 Voice→Avatar 直送，再把同一塊送給 App 播放。
                        # 直送若逾時，_forward_audio 會先通知 App 切回 relay，確保這一塊不遺失。
                        await _forward_audio(data)
                    elif data:
                        reason = "language" if st.get("language_block") else "barge_in"
                        _diag(cid, "node.audio_suppressed", reason=reason, out_bytes=len(data))
                    if sc:
                        ot = getattr(sc, "output_transcription", None)
                        if ot and getattr(ot, "text", None):
                            # 2026-07-25（卡西法・三修③）：語音線字幕出口也要過同一道防禦性
                            # 清洗，剝掉可能漏出的 <thinking> 內部推理標記，跟文字線同一把關卡。
                            current_profile = (
                                st.get("voice_locale_profile")
                                or voice_locale_session.current_profile()
                            )
                            raw_caption = localization.display_text(
                                ot.text,
                                current_profile["responseLocale"],
                            )
                            caption_text = eng.clean_outgoing_reply(raw_caption)
                            # 語音線：字幕能清、聲音已經放出去了——排一句自我更正，
                            # 讓她在下一個輪替空檔（幾秒內）自然收回，趕在長輩真的坐著等之前。
                            _, _promised = eng.strip_impossible_promises(raw_caption)
                            if _promised and not st.get("pending_promise_cue"):
                                st["pending_promise_cue"] = impossible_promise_cue(_promised)
                                _diag(cid, "promise.cue_queued", said=_promised[0][:30])
                            if not st.get("language_block") and not st.get("client_barge_in"):
                                await ws.send(json.dumps({"type": "caption", "who": "nening", "text": caption_text}))
                                st["ai_buf"] = (st["ai_buf"] + caption_text)[-200:]
                                st["bg_tasks"].append(asyncio.create_task(guardian_watch(
                                    cid, "ai", st["ai_buf"], st, session,
                                    turn_id=st.get("guardian_real_turn_id", 0),
                                    allow_cue=not st.get("guardian_internal_followup_active"),
                                )))
                        it = getattr(sc, "input_transcription", None)
                        if it and getattr(it, "text", None):
                            user_text = localization.reconcile_context_transcription(
                                it.text,
                                asr_context_terms,
                                voice_locale_session.current_profile()["sessionLocale"],
                            )
                            await ws.send(json.dumps({"type": "caption", "who": "user", "text": user_text}))
                            st["user_buf"] = (st["user_buf"] + user_text)[-200:]
                            st["bg_tasks"].append(asyncio.create_task(guardian_watch(
                                cid, "user", st["user_buf"], st, session,
                                turn_id=st.get("guardian_real_turn_id", 0), allow_cue=True,
                            )))
                            health_watch_user_text(cid, st)  # B2 衛教：同一份字幕順手比對題庫（同步、零模型呼叫）
                        if getattr(sc, "interrupted", False) and not st.get("language_block"):
                            st["playout_head"] = 0.0   # 模型端插話：App 收到 interrupted 也會清播放
                            _diag(cid, "node.interrupted")
                            await ws.send(json.dumps({"type": "interrupted"}))
                            # 插話：雲端臉也停下舊句、回待機（伺服器直接送，不等瀏覽器繞一圈）。
                            await _reset_face_audio_turn("model_interrupted")
                        if getattr(sc, "turn_complete", False):
                            ms = round(turn_out / (24000 * 2) * 1000)
                            # max_gap_ms＝這一輪送聲音最久的一次空檔。Avatar 播放端現在只有
                            # 200-350 毫秒動態緩衝；持續衝到接近或超過緩衝，
                            # 就是使用者會聽到「卡一下／吃掉一個字」的那個瞬間，可以拿這個值追。
                            _diag(cid, "node.turn_done", out_bytes=turn_out, audio_ms=ms,
                                  max_gap_ms=round(turn_max_gap_ms))
                            _semantic_reason = st.get("semantic_hold_reason")
                            if _semantic_reason and not st.get("semantic_hold_outcome_recorded"):
                                if st.get("semantic_hold_resumed"):
                                    st["client_barge_in"] = True
                                    st["semantic_turn_active_resumes"] += 1
                                    _diag(
                                        cid,
                                        "node.semantic_turn_active_cancelled",
                                        reason=_semantic_reason,
                                        no_audio=True,
                                    )
                                else:
                                    st["semantic_turn_active_releases"] += 1
                                    _record_semantic_adaptation(False)
                                    _diag(
                                        cid,
                                        "node.semantic_turn_active_released",
                                        reason=_semantic_reason,
                                        no_audio=True,
                                    )
                                st["semantic_hold_outcome_recorded"] = True
                                _clear_semantic_hold()
                            barge_cancelled = bool(st.get("client_barge_in"))
                            completed_audio = bool(turn_out and not st.get("language_block") and not barge_cancelled)
                            if st.get("lookup_waiting_answer"):
                                _diag(cid, "node.lookup_answer_missing", out_bytes=turn_out)
                                st["lookup_waiting_answer"] = False
                            if turn_out and not st.get("language_block") and not st.get("client_barge_in"):
                                await _send_turn_tail()
                            await _finish_face_audio_turn()
                            turn_out = 0
                            # 2026-08-01：這兩個原本只在 while 外層歸零，同一條連線第二輪
                            # 以後會沿用上一輪的最大值＝越報越大、且永遠是舊帳。
                            turn_max_gap_ms = 0.0
                            turn_last_out = None
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
                                if barge_cancelled and source == "model_output":
                                    _diag(cid, "node.language_replacement_skipped", reason="barge_in", source=source)
                                elif source == "model_output" and st.get("language_retry_count", 0) < 1:
                                    # 病歷 d（聲線變）：先讓模型用「她自己的聲音」重講國語版。
                                    # 2026-08-10：mandarin_pronunciation 不再走到這裡（唸不準
                                    # 改成只記錄不攔），所以「重講仍被攔就換安全配音」那條
                                    # 分支也一併移除——台語輸出第二次仍被攔會落到下面的
                                    # 台語罐頭句，那本來就是對的收尾，不需要換一個陌生聲線。
                                    st["language_retry_count"] = st.get("language_retry_count", 0) + 1
                                    await _retry_mandarin_output()
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
                            st["locale_user_transcript"] = ""
                            st["locale_resolved_text"] = ""
                            # 通話記憶：這一輪講完，先把雙方字幕收進整通紀錄再清緩衝（收線時交聊後管線）
                            _capture_call_turns(st)
                            # 守護腦：這一輪自然講完了、天然的輪替空檔，排隊中的安全導引在這裡送出（不是插話攔截剛剛那句）
                            st["user_buf"] = ""
                            st["ai_buf"] = ""
                            st["guardian_internal_followup_active"] = False
                            st["guardian_internal_followup_sources"] = ()
                            if st.get("pending_cues") or st.get("pending_health_cue") or st.get("pending_promise_cue"):
                                st["bg_tasks"].append(asyncio.create_task(guardian_flush_pending_cue(cid, session, st)))
                            if st.get("locale_reconnect_requested"):
                                st["locale_reconnect_requested"] = False
                                st["voice_locale_profile"] = voice_locale_session.current_profile()
                                _diag(cid, "node.locale_reconnect_at_turn_boundary")
                                return "reconnect"
                            if _voice_session_extend_enabled() and st.get("goaway_pending"):
                                # GoAway 已經預警過、現在剛好是天然的輪替空檔（這一輪自然講完了）——
                                # 主動換線比乾等硬斷線好，App／使用者完全無感。
                                _diag(cid, "node.goaway_reconnect_at_turn_boundary")
                                return "reconnect"
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
                    break   # receive() 立刻空 = 這條底層連線真的結束 → 收線
            return "ended"
        except (genai_errors.APIError, websockets.ConnectionClosed) as exc:
            # 通話延長（2026-07-25）：GoAway 之後 Gemini 真的把這條底層連線收掉時，
            # SDK 會在這裡炸一個關線例外——這是預期中的關線，不是真的斷線／出錯，
            # 只有先前真的看過 GoAway 預警才當「換線」處理；沒看過 GoAway 就當真出錯，
            # 原樣往外丟，跟改動前的行為一致（外層照舊優雅收線）。
            if _voice_session_extend_enabled() and st.get("goaway_pending"):
                _diag(cid, "node.goaway_closed", err=f"{type(exc).__name__}:{str(exc)[:60]}")
                return "reconnect"
            raise

    async def _goaway_watchdog():
        # GoAway 保底：萬一遲遲沒有 turn_complete 這種天然空檔（例如對方講很長一段話、
        # 或整通都沒人開口），不要傻等硬斷線——時間一到就主動出手，逼外層換線。
        while True:
            await asyncio.sleep(0.5)
            deadline = st.get("goaway_deadline")
            if deadline and time.monotonic() >= deadline:
                return "reconnect_timeout"

    # 任一邊結束（使用者掛斷／這條底層連線該換了／session 收）就取消另一邊，乾淨收線或換線
    from_browser_task = asyncio.create_task(from_browser())
    from_live_task = asyncio.create_task(from_live())
    watchdog_task = asyncio.create_task(_goaway_watchdog())
    try:
        done, _pending = await asyncio.wait(
            [from_browser_task, from_live_task, watchdog_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if from_browser_task in done:
            call_ended = True   # 瀏覽器連線斷了／使用者掛斷，這才是真的收線
        elif watchdog_task in done and from_live_task not in done:
            # 一直沒等到天然空檔、GoAway 保底時間到了——強制換線（from_live_task 在
            # 下面的 finally 會被取消，session.receive() 中途取消是安全的）。
            _diag(cid, "node.goaway_forced_reconnect")
        elif from_live_task in done:
            status = from_live_task.result()
            if status != "reconnect":
                call_ended = True
    finally:
        for t in (from_browser_task, from_live_task, watchdog_task):
            if not t.done():
                t.cancel()
        for t in (from_browser_task, from_live_task, watchdog_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
    return call_ended, st.get("resumption_handle") or resumption_handle


def _defer_control_release_for_reconnect(reason, state):
    """Keep the lease alive when the App deliberately rebuilds a dead preflight socket.

    The installed App closes Voice after five seconds when its microphone
    pipeline has produced no packets.  That close is a reconnect request, not
    a user hang-up.  Releasing the whole call here makes the App's subsequent
    token refresh fail with ``stale_lease`` and presents a false busy line.
    The App remains the owner of an intentional release; the durable 45-second
    reaper is the final guard for a crashed client.
    """
    return (
        reason == "call_ended"
        and int((state or {}).get("in") or 0) == 0
        and int((state or {}).get("out") or 0) == 0
    )


async def handle(ws):
    char = "寧寧"
    # 從連線網址讀使用者改過的名字（?name=新名字），讓 AI 知道自己現在叫什麼
    name = None
    mood = None
    topics = None
    user = None
    location = None
    allow_reminders = False   # 只有帶 ?cap_rem=1 的新版 App 才開放「幫你設提醒」工具（防舊版假成功）
    allow_events = False
    allow_care_questions = False   # 只有帶 ?cap_ask=1 的新版 App 才開放口袋問題工具（M1 PR-3）      # 只有帶 ?cap_evt=1 的新版 App 才開放「幫你記行程」工具（2026-07-16）
    fam = 0                   # 熟識度（聊過幾通）：0=第一次見面；越大開場越簡短（Edward 2026-07-10）
    day_call = None           # 當日第幾通（0-based）：只負責開場路線去重，不改變關係熟識度
    pause_profile = None      # 單通話聽話耐心：responsive / balanced / patient（候選版 A/B）
    gate_key = ""   # Legacy 1.0.1 transition only.
    call_token = ""
    call_payload = {}
    voice_locale_session = None
    demo_mode = False
    # 收線時要告訴總機「這一席讓出來了」的原因。2026-07-28 修：這裡原本是空字串，而下面
    # finally 寫的是「有原因才通知總機」——結果只有『出錯』那條路會設值，**使用者正常講完
    # 掛斷反而不通知**，總機一直以為那席還占著。我們總共只有 2 席，於是第二通就撥不通／
    # 撥通了狀態也不對（Edward 7/28 回報「二度撥通很難、撥通後又沒辦法正常說話」）。
    # 改成一開始就有預設值＝不管走哪條路收線，席位一定還回去。
    call_release_reason = "call_ended"
    _q = {}
    try:
        from urllib.parse import urlparse, parse_qs
        path = getattr(getattr(ws, "request", None), "path", None) or getattr(ws, "path", "") or ""
        _q = parse_qs(urlparse(path).query)
    except Exception:
        pass

    demo_mode = _q.get("demo") == ["1"]

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
            voice_locale_session = VoiceLocaleSession.from_verified_call_payload(
                call_payload,
                allow_legacy=(
                    os.environ.get(
                        "MUNEA_VOICE_ALLOW_LEGACY_LOCALE_CONTEXT",
                        "1",
                    ) == "1"
                ),
            )
        except Exception:
            try:
                await ws.close(code=4403, reason="invalid call token")
            except Exception:
                pass
            return

    if voice_locale_session is None:
        # Developer-direct and legacy key sessions preserve today's Taiwan
        # behavior. Production call-control tokens above are the only path that
        # may supply non-default locale or regional policy.
        voice_locale_session = VoiceLocaleSession({})

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
        if _q.get("cap_rem") == ["1"] and not demo_mode:
            allow_reminders = True
        # ?cap_evt=1：這版 App 接得住「AI 幫你記行程」→ 才給記行程工具（能力握手 · 2026-07-16 Edward「約吃飯被設成看診」）
        if _q.get("cap_evt") == ["1"] and not demo_mode:
            allow_events = True
        # ?cap_ask=1：這版 App 接得住「AI 幫你記要問醫生的問題」（M1 PR-3）
        if _q.get("cap_ask") == ["1"] and not demo_mode:
            allow_care_questions = True
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
        # ?pause=patient：候選版可逐通 A/B「少搶話 vs 回得快」。只接受三個命名檔位，
        # 不讓任意 query 毫秒值進到底層；未帶時仍是現行 balanced=800ms。
        pvals = _q.get("pause")
        if pvals:
            pause_profile = _voice_pause_profile(pvals[0])
    except Exception:
        pass
    _CID["n"] += 1
    cid = _CID["n"]
    t0 = time.monotonic()
    st = _new_call_state()
    st["voice_locale_profile"] = voice_locale_session.current_profile()
    _diag(
        cid,
        "connected",
        name=name or "-",
        char=char,
        demo=demo_mode,
        locale=st["voice_locale_profile"]["sessionLocale"],
    )
    _key_idx = None   # 多鑰匙分流：這通用哪把鑰匙（收線時據此把空位還回去）
    # 通話記憶的人別隔離鍵：Gateway 正式路徑的 call token 帶已驗證的 user_id；
    # 開發包直連沒 token → None（server 端落回主要照護對象）。收線回寫與開場接續共用同一 scope。
    memory_scope = None
    if call_payload and call_payload.get("user_id"):
        memory_scope = f"voice-{call_payload['user_id']}"
    # 衛教方案要因人挑（齡層／他上次說哪個沒效），這些只有 Brain 知道。
    # 接通時要一次、存進這通的狀態；認不出人就是空的，挑選層退回通用方案。
    st["memory_scope"] = memory_scope
    st["health_profile"] = {}
    _start_health_profile_fetch(st, memory_scope)
    try:
        # 只有走舊的橋接查詢才需要暖機（那條路要靠伺服器插播過場句蓋住 5 秒空白，
        # 所以得先把整個句庫都配好音）。2026-07-28 起預設走 native＝她自己查、沒有過場句，
        # 這整包暖機不跑——它是 Edward 7/28 回報「前 5 分鐘講話卡卡」的主嫌：接通那一刻
        # 就把 15 句配音塞進只有 2 個工人的小隊列，一顆 CPU 上跟送聲音的主線搶，一搶就是好幾分鐘。
        if live_lookup_enabled():
            lookup_cue_future = asyncio.get_running_loop().run_in_executor(
                _VOICE_CUE_EXECUTOR, _warm_lookup_cue_pool, char,
                st["voice_locale_profile"]["sessionLocale"])
            st["lookup_cue_task"] = lookup_cue_future
        asr_context_terms = [char, name, user, location, *(topics or [])]
        # 通話延長（2026-07-25）：這通電話對 App／使用者永遠是「同一通」，但底層可能換過
        # 好幾條 Gemini Live 連線（GoAway 預警接續）。resumption_handle 帶著走；st 活在
        # 這個迴圈外面，所以字幕／記憶／查詢統計在換線前後完全連續，App 無感。
        resumption_handle = None
        first_connect = True
        reconnect_attempts = 0
        call_ended = False
        while not call_ended:
            # 組 config 會呼叫 build_reply_context（內含對 Supabase 的同步阻塞查詢，最多 4 秒）——
            # 丟到背景執行緒，別卡住整條 async 事件主幹道、拖垮所有通話中的人（2026-07-12 卡西法壓測抓到 10 人斷崖真兇）
            cfg = await asyncio.to_thread(
                live_config, char, name, mood, topics, user, location, allow_reminders, fam,
                memory_scope, allow_events, demo_mode,
                allow_care_questions=allow_care_questions,
                pause_profile=pause_profile,
                resumption_handle=resumption_handle,
                locale_profile=voice_locale_session.current_profile())
            aad = cfg.realtime_input_config.automatic_activity_detection
            st["provider_silence_ms"] = int(aad.silence_duration_ms)
            if first_connect:
                env_silence = os.environ.get("MUNEA_VOICE_SILENCE_MS", "").strip()
                env_profile = _voice_pause_profile(
                    os.environ.get("MUNEA_VOICE_PAUSE_PROFILE"))
                pause_label = pause_profile
                if not pause_label and env_silence == str(aad.silence_duration_ms):
                    pause_label = "custom"
                pause_label = pause_label or env_profile or "adaptive"
                _diag(
                    cid,
                    "turn_taking_config",
                    pause=pause_label,
                    silence_ms=aad.silence_duration_ms,
                )
            if first_connect and cfg.thinking_config is not None:
                # A/B 實測要有帳可查：這通到底跑在哪一段思考深度，直接寫進通話紀錄。
                # 沒設（正式機預設）時一個字都不印，日誌不變吵。
                _diag(cid, "thinking_level", level=cfg.thinking_config.thinking_level)
            _key_idx, _cli = _pick_client()   # 挑現在最閒的一把鑰匙開這條底層連線（多鑰匙分流的核心）
            try:
                async with _cli.aio.live.connect(model=MODEL, config=cfg) as session:
                    call_ended, resumption_handle = await _run_voice_session(
                        session, _cli, ws, cid, t0, st, char, location, topics, fam, day_call,
                        call_payload, gate_key, call_token, asr_context_terms,
                        first_connect, resumption_handle, voice_locale_session,
                        user_name=user,
                    )
            finally:
                if _key_idx is not None:
                    _release_client(_key_idx)   # 這條底層連線結束，把這把鑰匙的空位放回去
                    _key_idx = None
            if not call_ended:
                reconnect_attempts += 1
                if reconnect_attempts > MAX_SESSION_RECONNECTS:
                    _diag(cid, "node.reconnect_limit_reached", attempts=reconnect_attempts)
                    call_ended = True
                else:
                    first_connect = False
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        call_release_reason = "voice_error"
        _diag(cid, "node.error", err=f"{type(e).__name__}:{str(e)[:80]}")
    finally:
        if call_payload and call_release_reason:
            if _defer_control_release_for_reconnect(call_release_reason, st):
                _diag(cid, "node.control_release_deferred", reason="preflight_zero_audio_reconnect")
            else:
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
            if not demo_mode and st.get("call_turns") and (
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
        semantic_adaptive = st["semantic_turn_policy"].snapshot()
        _diag(
            cid, "closed", in_bytes=st["in"], out_bytes=st["out"], echo_dropped=st["echo_dropped"],
            asr_turns=st["asr_turns"], asr_chars=st["asr_chars"],
            semantic_turn_total=st["semantic_turn_shadow_total"],
            semantic_turn_holds=st["semantic_turn_shadow_holds"],
            semantic_turn_active_holds=st["semantic_turn_active_holds"],
            semantic_turn_active_resumes=st["semantic_turn_active_resumes"],
            semantic_turn_active_releases=st["semantic_turn_active_releases"],
            semantic_turn_adaptive_continuations=semantic_adaptive["continuations"],
            semantic_turn_adaptive_releases=semantic_adaptive["releases"],
            semantic_turn_adaptive_ewma_ms=semantic_adaptive["continuation_ewma_ms"],
            barge_ins=st["barge_in_count"],
            barge_rejected=st["barge_in_rejected"],
            barge_post_duck_accepted=st["barge_post_duck_accepted"],
            barge_pre_duck_accepted=st["barge_pre_duck_accepted"],
            language_blocks=st["language_block_count"],
            lookups=st["lookup_count"], lookup_sources=st["lookup_sources"],
            lookup_failures=st["lookup_failures"],
            tool_wait_interrupts=st["tool_wait_interrupts"],
            # 她自己查那條路的帳（2026-08-10）。上面的 lookups 只算「我們代查」那條，
            # 正式機走的是 native＝她自己查——以前這條完全沒有帳，所以
            #「她說我幫你查一下、然後憑印象亂講」跟「她真的查了」在日誌上長得一模一樣。
            native_searches=st["native_search_turns"],
            native_search_queries=st["native_search_queries"],
            native_search_sources=st["native_search_sources"],
            mandarin_pronunciation_seen=st["mandarin_pronunciation_seen"],
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
