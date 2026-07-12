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
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_loader import load_engine_env
load_engine_env()  # 跟 server.py 同款：自動吃 engine/.env.local 的鑰匙、環境變數優先
import chat_engine as eng
from google import genai
from google.genai import types
import websockets
from websockets.http11 import Response
from websockets.datastructures import Headers

MODEL = "gemini-3.1-flash-live-preview"
KEY = os.environ.get("GEMINI_API_KEY")
if not KEY:
    sys.exit("需要 GEMINI_API_KEY")

client = genai.Client(api_key=KEY)

import mimetypes

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(HERE, "..", "web"))


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


def process_request(connection, request):
    """非 WebSocket 的請求就當靜態網站服務（測試頁＋臉圖等），讓網頁與語音走同一個門。"""
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None
    path = request.path.split("?")[0].lstrip("/")
    if path in ("", "index.html"):
        path = "live-voice-test.html"
    return _file_response(path)


import server  # 重用文字聊天同一套「腦」組裝：人格層＋記憶層＋感知層＋守護腦，確保即時語音同步
import notify as guardian_notify  # 守護腦命中 high/critical 時的內部安全告警（Slack #沐寧-告警 kind=voice）；送不出去就默默記日誌，不影響通話


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


def system_instruction(char="寧寧", name=None, mood=None, topics=None, user=None, location=None, allow_reminders=False, fam=0):
    """跟 /chat 同一套腦：角色人格 + 非醫療界線 + 記憶層 + 感知層 + 守護腦。"""
    c = eng.CHARS.get(char) or eng.CHARS["寧寧"]
    # 共同底盤（管家身分＋專業邊界＋告警/情緒/調解能力）在最前面，角色性格疊在上面
    base = eng.CORE + c.get("persona", "") + eng.RED
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
    if c.get("type") == "animal" and c.get("style"):
        base += f"（你講話的聲音演技：{c['style']}）"
    base += (
        "（現在是即時語音通話。剛接起電話先用一句溫暖的話打招呼；不確定對方是誰時不要亂猜名字或稱呼；"
        "句子短、口語、一次一兩句、講完停下來等對方回應。）"
    )
    # 熟識度分寸貫穿整段對話（不只開場）：越不熟越收斂、越熟越自在（Edward 2026-07-12）
    if fam < 1:
        base += "（你們還不太熟，這是頭幾通電話：整段對話都要特別收斂——話少、溫和、讓他主導，不要熱情轟炸、不要一直找話題硬聊、不要連環問。他問你、或聊到他有興趣的才多說一點。）"
    elif fam < 3:
        base += "（你們聊過幾次、漸漸熟了：可以自在一點，但仍別長篇、別連環問、別硬炒氣氛。）"
    else:
        base += "（你們很熟了、像老朋友：自在、可主動一點，但一次還是一兩句、不長篇。）"
    base += (
        "（你有「即時查詢」工具，聊天時可以真的上網查。聊到餐廳店家、景點旅遊（例如日本哪裡好玩、桃園有什麼好吃的）、"
        "電影影劇、天氣預報、時事、活動檔期這類「講錯會誤導人」的具體話題——先安靜查一下再回，"
        "只講查到的真店名、真地點、真資訊；用「我聽很多人推薦…」「那邊最有名的是…」這種像自己去過或朋友推薦的口吻，"
        "自然分享一兩個亮點就好，順便帶一個有意思的小知識或典故更好。不要唸清單、不要報網址、不要像導覽機。"
        "查不到或不確定就老實說「這我不太確定，我幫你查查看」——寧可少講，絕對不可以自己編店名、地址、價格或營業時間。"
        "天氣要講就查當地真的預報再講。"
        "要查東西時，先自然講一句短的過場再查（例如「喔這我知道有個好地方，等我想一下」），"
        "別讓對方對著沒聲音的電話等好幾秒。）"
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
        base += (
            f"（很重要：稱呼對方一律用「{uv}」——這是他自己在個人資料裡填的稱呼，"
            f"優先於任何記憶或舊資料裡的名字；打招呼與整段對話都用「{uv}」稱呼他、不要叫他別的名字。）"
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
            "先用一句話問清楚再設，不要自己亂猜。設好之後用一句溫暖口語的話跟他確認你設了什麼"
            "（例如「好，我幫你記下明天下午四點台大骨科回診了」），讓他安心、也方便他去 App 裡的提醒清單看或改。）"
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
])


def live_config(char="寧寧", name=None, mood=None, topics=None, user=None, location=None, allow_reminders=False, fam=0):
    c = eng.CHARS.get(char) or eng.CHARS["寧寧"]
    voice = c.get("voice") or "Leda"
    # 即時查詢（Google 搜尋）所有版本都有；幫你設提醒（函式呼叫）只給接得住的新版 App（?cap_rem=1）
    tools = [types.Tool(google_search=types.GoogleSearch())]
    if allow_reminders:
        tools.append(_REMINDER_TOOLS)
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=system_instruction(char, name, mood, topics, user, location, allow_reminders, fam),
        tools=tools,
        output_audio_transcription=types.AudioTranscriptionConfig(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
        # 聽話靈敏度（Edward 2026-07-10「戶外雜音/旁人聊天被當成我在講」）：
        # 開口判定調「低靈敏」＝要更明確、對著手機講的人聲才算你在說話——背景雜音/遠處聊天不易誤觸、不再亂打斷她；
        # 結束判定維持預設；尾端靜音窗 800ms＝長輩講話中間喘口氣不會被急著搶話。
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
                silence_duration_ms=800,
            )
        ),
    )


def _diag(cid, event, **kv):
    parts = " ".join(f"{k}={v}" for k, v in kv.items())
    print(f"[diag] c{cid} {event} {parts}".rstrip(), flush=True)


_CID = {"n": 0}


async def handle(ws):
    char = "寧寧"
    # 從連線網址讀使用者改過的名字（?name=新名字），讓 AI 知道自己現在叫什麼
    name = None
    mood = None
    topics = None
    user = None
    location = None
    allow_reminders = False   # 只有帶 ?cap_rem=1 的新版 App 才開放「幫你設提醒」工具（防舊版假成功）
    fam = 0                   # 熟識度（聊過幾通）：0=第一次見面；越大開場越簡短（Edward 2026-07-10）
    gate_key = ""   # 這通電話用的通行碼（跟 App 一致）；伺服器對伺服器接雲端臉時原封不動帶過去，不必客端再傳一次
    try:
        from urllib.parse import urlparse, parse_qs
        path = getattr(getattr(ws, "request", None), "path", None) or getattr(ws, "path", "") or ""
        _q = parse_qs(urlparse(path).query)
        # 薄門（正式上線 · 7/9 Edward 拍板）：環境設了 MUNEA_APP_KEY 就要對通行碼（?key=）。
        # App 自動帶、用戶無感；擋的是「拿到網址直接來撥」的陌生流量。本機沒設＝不啟用、行為不變。
        _gate = os.environ.get("MUNEA_APP_KEY", "").strip()
        gate_key = _gate   # 存起來給「聲音直接送去雲端臉」那條 server-to-server 連線用（同一把薄門鑰匙）
        if _gate:
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
        # ?fam=N：聊過幾通（熟識度）→ 決定開場話量：越熟話越少（Edward 2026-07-10「隨熟識度思考語句量」）
        fvals = _q.get("fam")
        if fvals:
            try:
                fam = max(0, min(999, int(fvals[0])))
            except Exception:
                pass
    except Exception:
        pass
    _CID["n"] += 1
    cid = _CID["n"]
    t0 = time.monotonic()
    st = {"in": 0, "out": 0, "last_in": None, "await_first": True, "first_mic": False,
          "face_ws": None, "face_audio_url": None,   # 方案 B：聲音直接轉送去雲端臉的 server-to-server 連線狀態
          "user_buf": "", "ai_buf": "", "user_flagged": set(), "ai_flagged": set(),
          "pending_cues": [], "bg_tasks": []}   # 守護腦接回語音線：字幕滾動視窗／這輪已處置類別／排隊中的安全導引／背景任務集
    _diag(cid, "connected", name=name or "-", char=char)
    try:
        # 組 config 會呼叫 build_reply_context（內含對 Supabase 的同步阻塞查詢，最多 4 秒）——
        # 丟到背景執行緒，別卡住整條 async 事件主幹道、拖垮所有通話中的人（2026-07-12 卡西法壓測抓到 10 人斷崖真兇）
        cfg = await asyncio.to_thread(live_config, char, name, mood, topics, user, location, allow_reminders, fam)
        async with client.aio.live.connect(model=MODEL, config=cfg) as session:
            # 腦真正接上了才跟瀏覽器說 ready——治「第一句沒回應」：
            # 以前瀏覽器一開線就送聲音，但這裡開 Gemini session 要 1~3 秒，
            # 那段聲音會先塞在門口、開門後一口氣灌進去，AI 的斷句判斷就亂了。
            try:
                await ws.send(json.dumps({"type": "ready"}))
            except Exception:
                pass
            _diag(cid, "node.ready", ms=round((time.monotonic() - t0) * 1000))

            # 主動開口 cue（治「叫兩三次才回、以為當機」· Edward 2026-07-09）：
            # 不在 session 開好就立刻送——改由 App 在「聲音＋會動的臉兩邊都就緒」時送 {"type":"greet"} 才觸發，
            # 這樣她一開口臉就同步在動、不會出現「已在講、臉還沒好」的當機感（Edward 2026-07-09 二次拍板）。
            async def _do_greet():
                try:
                    # 話量隨熟識度（Edward 2026-07-10「一開始話太多了」）：越熟越像老朋友、一句就好；
                    # 不論哪級都硬上限：最多兩句、不連環問、不長篇自我介紹。
                    if fam >= 3:
                        _len_rule = "你們已經聊過很多次、很熟了：一句自然的招呼就好（10 個字左右），像老朋友拿起電話那樣隨口，不要自我介紹、不要問超過一個問題。"
                    elif fam >= 1:
                        _len_rule = "你們聊過幾次了：一到兩句簡短招呼就好，不要重新自我介紹、不要一次問好幾個問題。"
                    else:
                        _len_rule = "這是第一次通話：用一句話說你是誰、再用一句話問候，總共最多兩句、40 個字以內，不要長篇自我介紹。"
                    greet_cue = (
                        "（這是系統提示，絕對不要唸出這段、也不要提到系統：使用者剛接起這通電話。"
                        "請你「立刻、主動」開口打招呼，不要等對方先開口。" + _len_rule + "）"
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

            async def _face_audio_on(url):
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
                    ws_url += "/audio?key=" + quote(gate_key, safe="")
                    fw = await websockets.connect(ws_url, max_size=None, open_timeout=5)
                    st["face_ws"] = fw
                    st["face_audio_url"] = url
                    _diag(cid, "node.faceaudio_on", url=url)
                except Exception as e:
                    st["face_ws"] = None
                    st["face_audio_url"] = None
                    _diag(cid, "node.faceaudio_err", err=f"{type(e).__name__}:{str(e)[:60]}")

            async def from_browser():
                async for message in ws:
                    if isinstance(message, (bytes, bytearray)):
                        n = len(message)
                        st["in"] += n
                        st["last_in"] = time.monotonic()
                        st["await_first"] = True
                        if not st["first_mic"]:
                            st["first_mic"] = True
                            _diag(cid, "node.mic_uplink", ms=round((st["last_in"] - t0) * 1000))
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
                            await _do_greet()   # App 說「兩邊都就緒了」→ 現在才請她主動開口（聲臉同步開場）
                        elif t == "nudge":
                            await _do_nudge(int(obj.get("level", 1)))   # App 偵測到使用者一直沒講話 → 寧寧溫柔提醒（省點）
                        elif t == "text" and obj.get("text"):
                            st["last_in"] = time.monotonic()
                            st["await_first"] = True
                            await session.send_client_content(
                                turns=types.Content(role="user", parts=[types.Part(text=obj["text"])]),
                                turn_complete=True,
                            )
                        elif t == "audio_end":
                            await session.send_realtime_input(audio_stream_end=True)
                        elif t == "faceaudio":
                            # {"type":"faceaudio","on":true,"url":"..."} 開＝伺服器對伺服器直送雲端臉；on:false 或掛斷＝收線
                            if obj.get("on"):
                                await _face_audio_on(obj.get("url") or "")
                            else:
                                await _face_audio_off()

            async def from_live():
                # session.receive() 每輪結束就收（SDK 行為）；外層 while 讓「一輪接完再等下一輪」＝多輪對話不斷
                while True:
                    turn_out = 0
                    got = False
                    async for msg in session.receive():
                        got = True
                        data = getattr(msg, "data", None)
                        if data:
                            if st["await_first"] and st["last_in"] is not None:
                                lat = round((time.monotonic() - st["last_in"]) * 1000)
                                st["await_first"] = False
                                _diag(cid, "node.first_audio", latency_ms=lat)
                                try:
                                    await ws.send(json.dumps({"type": "diag", "firstAudioMs": lat}))
                                except Exception:
                                    pass
                            st["out"] += len(data)
                            turn_out += len(data)
                            await ws.send(data)
                            fw = st.get("face_ws")
                            if fw is not None:
                                try:
                                    await fw.send(data)   # 同一份聲音 bytes，server-to-server 直送雲端臉（方案 B）
                                except Exception as e:
                                    st["face_ws"] = None
                                    _diag(cid, "node.faceaudio_send_err", err=str(e)[:60])
                        sc = getattr(msg, "server_content", None)
                        if sc:
                            ot = getattr(sc, "output_transcription", None)
                            if ot and getattr(ot, "text", None):
                                await ws.send(json.dumps({"type": "caption", "who": "nening", "text": ot.text}))
                                st["ai_buf"] = (st["ai_buf"] + ot.text)[-200:]
                                st["bg_tasks"].append(asyncio.create_task(guardian_watch(cid, "ai", st["ai_buf"], st, session)))
                            it = getattr(sc, "input_transcription", None)
                            if it and getattr(it, "text", None):
                                await ws.send(json.dumps({"type": "caption", "who": "user", "text": it.text}))
                                st["user_buf"] = (st["user_buf"] + it.text)[-200:]
                                st["bg_tasks"].append(asyncio.create_task(guardian_watch(cid, "user", st["user_buf"], st, session)))
                            if getattr(sc, "interrupted", False):
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
                                turn_out = 0
                                st["await_first"] = True
                                await ws.send(json.dumps({"type": "turn_complete"}))
                                # 守護腦：這一輪自然講完了、天然的輪替空檔，排隊中的安全導引在這裡送出（不是插話攔截剛剛那句）
                                st["user_buf"] = ""
                                st["ai_buf"] = ""
                                st["user_flagged"] = set()
                                st["ai_flagged"] = set()
                                if st.get("pending_cues"):
                                    st["bg_tasks"].append(asyncio.create_task(guardian_flush_pending_cue(cid, session, st)))
                        # AI 決定「幫你設提醒」→ 把指令送給 App 執行，並回覆 AI 讓她口頭確認
                        tc = getattr(msg, "tool_call", None)
                        if tc and getattr(tc, "function_calls", None):
                            responses = []
                            for fc in tc.function_calls:
                                try:
                                    fargs = dict(fc.args) if fc.args else {}
                                except Exception:
                                    fargs = {}
                                _diag(cid, "node.tool_call", name=getattr(fc, "name", "?"))
                                await ws.send(json.dumps({"type": "action", "action": fc.name, "args": fargs}, ensure_ascii=False))
                                responses.append(types.FunctionResponse(id=getattr(fc, "id", None), name=fc.name, response={"status": "ok"}))
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
        _diag(cid, "node.error", err=f"{type(e).__name__}:{str(e)[:80]}")
    finally:
        for t in st.get("bg_tasks", []):
            if not t.done():
                t.cancel()
        fw = st.get("face_ws")
        if fw is not None:
            try:
                await fw.close()
            except Exception:
                pass
        _diag(cid, "closed", in_bytes=st["in"], out_bytes=st["out"])


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
