#!/usr/bin/env python3
"""
沐寧 Munea · 角色引擎 — 讀 characters.json，可當任何角色講話。
真人（寧寧/阿宏/小昀/阿原）會帶「記憶」（user_profile.json）；動物（咪咪/旺財）用各自演技聲音。
用法：GEMINI_API_KEY="..." py chat_engine.py [角色名 角色名 ...]
"""
import os, sys, json, time, wave, logging, re
from google import genai
from google.genai import types

import localization
import health_kb

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    sys.exit("需要 GEMINI_API_KEY")
HERE = os.path.dirname(os.path.abspath(__file__))
USER_PROFILE_PATH = os.environ.get("MUNEA_USER_PROFILE_PATH") or os.path.join(HERE, "user_profile.json")
client = genai.Client(api_key=API_KEY)
LOGGER = logging.getLogger("munea.chat_engine")

CHARS = json.load(open(os.path.join(HERE, "characters.json"), encoding="utf-8"))
# 共同底盤：不論哪個角色（含卡通動物），底下都是同一個「專屬 AI 健康照護管家」。
# 性格只改「怎麼說」，這層身分與專業能力每個角色一樣——文字與語音兩條路共用。
# 即時資訊那一段做成「二選一」（2026-07-30 瘦身下半場 · 治規則打架）：
# 離線版＝「你不會自己上網查、新聞只講今日簡報有的」；線上版（語音線開內建搜尋時）＝
# 簡短接軌到查詢段的規則。兩版**絕不同時出現**——7/29-30 的考卷崩盤實錘過：
# 「不會查」與「就真的去查」同時在她腦裡＝編新聞/亂接的火種。
PERSONA_DIR = os.path.join(HERE, "persona")
DEFAULT_PERSONA_LOCALE = "zh-TW"
_PERSONA_CACHE = {}


def _persona_text(kind, locale=DEFAULT_PERSONA_LOCALE):
    """讀一份說明書零件（core / red / lookup-offline / lookup-online）。

    2026-07-31 Edward 拍板「不同國家的人用那個國家的人設說明書」後改。
    在此之前的做法是：所有語系都吃同一本台灣版（含台灣急難號碼、健保中醫、
    「只能講台灣國語」），再在最後附一張紙條叫模型忽略上面的台灣內容——
    模型要自己壓抑約 10KB 的台灣指令，而且每輪都在計費。

    找不到該語系的書就退回中文版（不會開天窗），但那代表那一國還沒授書、
    上架守門（scripts/i18n-release-readiness.js）會擋著不准開語系。
    """
    key = (kind, locale)
    if key in _PERSONA_CACHE:
        return _PERSONA_CACHE[key]
    for candidate in (locale, DEFAULT_PERSONA_LOCALE):
        path = os.path.join(PERSONA_DIR, f"{kind}.{candidate}.txt")
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as handle:
                text = handle.read()
            _PERSONA_CACHE[key] = text
            return text
    raise FileNotFoundError(f"persona book missing: {kind}")


def persona_locales():
    """有哪幾國已經授書（core 與 red 都齊才算）。"""
    if not os.path.isdir(PERSONA_DIR):
        return []
    found = set()
    for name in os.listdir(PERSONA_DIR):
        if name.startswith("core.") and name.endswith(".txt"):
            found.add(name[len("core."):-len(".txt")])
    return sorted(
        locale for locale in found
        if os.path.exists(os.path.join(PERSONA_DIR, f"red.{locale}.txt"))
    )


LOOKUP_OFFLINE = _persona_text("lookup-offline")
LOOKUP_ONLINE = _persona_text("lookup-online")

_CORE_TEMPLATE = _persona_text("core")


def core_instruction(lookup="offline", locale=DEFAULT_PERSONA_LOCALE):
    """組出共同底盤。lookup="online"＝語音線開內建搜尋時；locale＝這通電話用哪一國的書。

    查詢規則二選一、絕不同時出現（2026-07-30 瘦身下半場・治規則打架）：
    「你不會自己上網查」跟「他問新聞就真的去查」同時在她腦裡＝編新聞的火種
    （7/29-30 考卷崩盤實錘）。離線版走今日簡報、線上版接軌查詢段。"""
    section = _persona_text("lookup-online" if lookup == "online" else "lookup-offline", locale)
    return _persona_text("core", locale).replace("&&LOOKUP_SECTION&&", section)


def red_lines(locale=DEFAULT_PERSONA_LOCALE):
    """安全紅線（照語系）。衛教常駐紅線目前只有中文版、對所有語系一起帶。"""
    return _persona_text("red", locale) + health_kb.resident_rules(locale)


# 預設（離線版）＝所有既有取用點的原行為；語音線在 live_voice_server 依模式另組
CORE = core_instruction("offline")

RED = red_lines()  # 預設中文版＝所有既有取用點的原行為

# 清掉模型偶爾漏出的雜訊標記：搜尋引用 [cite: ...] / 舞台指示情緒標 [開心][微笑] 等——這些會被念出來或顯示、破壞沉浸
_ARTIFACT_RE = re.compile(r"\[\s*cite[^\]]*\]|\[\s*/?citation[^\]]*\]|\[[一-鿿]{1,4}\]", re.IGNORECASE)

# 2026-07-25（卡西法・三修③）：手動煙霧測試曾撞過一次模型把內部推理／思考過程直接用
# <thinking>...</thinking> 這類標記漏進使用者看得到（聽得到）的回覆文字裡，走的是跟
# 正式文字線一模一樣的呼叫路徑（server.reply_conv）。這是回覆出口前最後一道防禦性清洗，
# 文字線（server.reply_conv 的 return 前）與語音線字幕出口（live_voice_server 的
# output_transcription 顯示前）都要蓋，不等下一次真的被使用者聽到才修。
_REASONING_TAG_NAMES = ("thinking", "think", "reasoning", "scratchpad")
_REASONING_PREFIX_RE = re.compile(
    r"^(?:THOUGHT|THOUGHTS|THINKING|REASONING|ANALYSIS|INTERNAL(?:\s+MONOLOGUE)?|PLAN)\s*[:：]",
    re.IGNORECASE,
)
_REASONING_BLOCK_RE = re.compile(
    r"<\s*(?:" + "|".join(_REASONING_TAG_NAMES) + r")\b[^>]*>.*?<\s*/\s*(?:"
    + "|".join(_REASONING_TAG_NAMES) + r")\s*>",
    re.IGNORECASE | re.DOTALL,
)
# 殘缺情形（只有開頭標記、沒有對應的結尾標記）：代表這段之後也是漏出來的內部推理垃圾，
# 寧可少講、也不要把不確定是不是推理內容的字唸給長輩聽——整段砍到字串結尾。
_REASONING_UNCLOSED_RE = re.compile(
    r"<\s*(?:" + "|".join(_REASONING_TAG_NAMES) + r")\b[^>]*>.*$",
    re.IGNORECASE | re.DOTALL,
)


def strip_reasoning_artifacts(t):
    """防禦性清洗：移除 <thinking>...</thinking> 之類內部推理標記（含只有開頭、沒有
    結尾的殘缺情形），並收乾拿掉標記後留下的多餘空白。不是 8 條鐵律的判定項，是額外的
    輸出安全網——文字線與語音線字幕出口都要過這關。"""
    if not t:
        return t
    cleaned = _REASONING_BLOCK_RE.sub("", t)
    cleaned = _REASONING_UNCLOSED_RE.sub("", cleaned)
    # 2026-07-31 考卷 S01 抓到：她把英文內心獨白直接講出來（「THOUGHT: The user…」）。
    # 原本只認 <thinking> 這類格式標籤、不認「前綴式」獨白。以段落為單位剝：
    # 開頭是這些標記的整段拿掉（英文獨白不會是要給長輩聽的話，整段砍安全）。
    paras = re.split(r"\n\s*\n", cleaned)
    kept = [p for p in paras if not _REASONING_PREFIX_RE.match(p.strip())]
    if kept != paras:
        cleaned = "\n\n".join(kept)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# 2026-07-29（蘇菲・考卷實測 S06 抓到）：她在急症情境會脫口說「需要我幫您撥電話給他們嗎？」
# ——她撥不了電話。長輩聽了會以為有人去通知家人了，就安心坐著等，等不到人也不會再求助。
# 說明書已經寫死禁止（RED ⑥），但那是「勸」、屬機率性；這一層是程式硬擋，收掉殘留的那幾成。
# 只擋她**真的做不到**的事（撥打電話／代發訊息／叫車代購／傳圖傳連結）；
# 她**做得到**的事（幫忙記錄、設提醒、關心數據、引導用 App 傳話功能）絕不能誤傷。
_IMPOSSIBLE_PROMISE_RE = re.compile(
    r"(?:要不要|需要|我)?\s*(?:我)?\s*(?:來|去)?\s*(?:幫|替)\s*(?:你|您|妳)\s*"
    r"(?:打(?:個)?電話|撥(?:個)?電話|撥號|call|叫車|叫計程車|叫外送|訂(?:餐|票|位)|代?購|下單|買|"
    r"聯絡|連絡|通知(?:他|她|家人)|傳(?:訊息|簡訊|line|LINE)|發(?:訊息|簡訊))"
)
_IMPOSSIBLE_SEND_RE = re.compile(r"我(?:可以|會|來)?\s*(?:把)?(?:連結|網址|圖|照片|影片)?\s*(?:傳|發|寄)給(?:你|您|妳)")


IMPOSSIBLE_PROMISE_FALLBACK = "這個我沒辦法幫你做欸，不過我可以陪你一起想想別的辦法。"


def strip_impossible_promises(t):
    """出口硬擋：把「我幫你撥電話／我幫你聯絡他／我傳給你看」這種她做不到的承諾整句拿掉。

    只砍那一句、其餘照留（她通常在正確建議之後才多嘴這一句，整段丟掉反而會把
    正確的轉介建議一起丟）。若整段話只有這一句，就不砍——寧可留著讓考卷抓到、
    也不要回一句空話給長輩。回傳 (清乾淨的文字, 被砍掉的句子清單)。"""
    if not t:
        return t, []
    parts = re.split(r"(?<=[。！？!?\n])", t)
    kept, dropped = [], []
    for part in parts:
        if part.strip() and (_IMPOSSIBLE_PROMISE_RE.search(part) or _IMPOSSIBLE_SEND_RE.search(part)):
            dropped.append(part.strip())
            continue
        kept.append(part)
    cleaned = "".join(kept).strip()
    if not cleaned:
        # 整段話就只有那個做不到的承諾：不能原封不動送出去（那等於直接對長輩說謊、
        # 他會真的坐著等），也不能回空白。換成一句誠實、且把話接回她幫得上的地方。
        return IMPOSSIBLE_PROMISE_FALLBACK, dropped
    return cleaned, dropped


# 2026-07-29 考卷 S03 抓到：劇本完全沒給天氣，她卻說「今天的天氣是晴時多雲喔」，
# 被追問還加碼「今天氣象報告說會是晴時多雲的好天氣」。說明書早就寫了「不准捏造數字或
# 事件」——她避開了數字，卻編了一個**狀態**跟一個**來源**，自認沒違規。
#
# 說明書那層已經講明白了（見 RED ⑥），這裡再加程式層硬擋：**引用一個不存在的預報來源**
# 是可以確定判斷的——沒有簡報就等於沒有預報，那句話一定是假的。天氣狀態本身不硬擋
# （使用者自己說「外面在下雨」時她跟著講是對的），那條靠說明書。
FORECAST_SOURCE_WORDS = ("氣象報告", "氣象局", "氣象署", "天氣預報", "預報說", "中央氣象")
FORECAST_FALLBACK = "我今天沒拿到天氣欸，你出門前看一下手機比較準。"


def strip_unbacked_forecast_source(t, has_briefing=None):
    """沒有今日簡報卻引用氣象來源＝編造來源，整句換掉。回傳 (清過的字, 被砍的句子)。

    has_briefing=None（不知道有沒有簡報）時不動作——寧可漏擋，也不要把正確的話砍掉。
    """
    if not t or has_briefing is not False:
        return t, []
    parts, kept, dropped = re.split(r"(?<=[。！？\n])", t), [], []
    for seg in parts:
        if seg.strip() and any(w in seg for w in FORECAST_SOURCE_WORDS):
            dropped.append(seg.strip())
            continue
        kept.append(seg)
    if not dropped:
        return t, []
    # 先講「我不知道天氣」再接原本的話——不然會變成先問「你要去菜市場嗎」、
    # 才補一句沒拿到天氣，聽起來像答非所問。
    out = "".join(kept).strip()
    return (FORECAST_FALLBACK + out) if out else FORECAST_FALLBACK, dropped


def clean_outgoing_reply(t, has_briefing=None):
    """出去前的統一清洗——正式線都要走這支（文字線 server.reply_conv、語音線字幕出口、
    主動開口）。裡面兩道：①剝內部推理標記（2026-07-25）②砍做不到的空頭承諾（2026-07-29）。

    ⚠ 語音線的限制（誠實記下、別以為這層能兜底）：聲音是邊生邊播的，字幕清乾淨時
    那句話**已經被唸出去、長輩已經聽到了**。所以語音線這層只保護「螢幕上看到的字」，
    真正要靠的是說明書那層（RED ⑥）先不要講出來。要在語音線做到硬擋，得走守護腦那種
    「下一個輪替空檔補一句更正」的機制，不是出口清洗。
    """
    if not t:
        return t
    cleaned = strip_reasoning_artifacts(t)
    cleaned, dropped = strip_impossible_promises(cleaned)
    cleaned, _forecast = strip_unbacked_forecast_source(cleaned, has_briefing=has_briefing)
    if dropped:
        LOGGER.warning("stripped impossible promise from outgoing reply: %s", dropped[:2])
    return cleaned


def _clean_reply(t):
    if not t:
        return t
    t = _ARTIFACT_RE.sub("", t)
    t = strip_reasoning_artifacts(t)
    t, dropped = strip_impossible_promises(t)
    if dropped:
        LOGGER.warning("stripped impossible promise from reply: %s", dropped[:2])
    return t
DEFAULT_USER_PROFILE = {
    "稱呼": "使用者",
    "年紀": "",
    "住在": "",
    "喜好": [],
    "回憶": [],
    "興趣權重": {},
}


def _log_fallback_exception(context, exc):
    LOGGER.warning(
        "%s failed; using fallback: %s",
        context,
        exc,
        exc_info=os.environ.get("MUNEA_DEBUG_TRACEBACK") == "1",
    )


def _read_user_profile():
    if not os.path.exists(USER_PROFILE_PATH):
        return dict(DEFAULT_USER_PROFILE)
    try:
        with open(USER_PROFILE_PATH, encoding="utf-8") as f:
            return {**DEFAULT_USER_PROFILE, **json.load(f)}
    except Exception as e:
        _log_fallback_exception("read user profile", e)
        return dict(DEFAULT_USER_PROFILE)


def _write_user_profile(profile):
    directory = os.path.dirname(os.path.abspath(USER_PROFILE_PATH))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{USER_PROFILE_PATH}.tmp.{os.getpid()}.{int(time.time() * 1000)}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, USER_PROFILE_PATH)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError as e:
                _log_fallback_exception("remove temp user profile", e)

def _profile_ctx():
    if not os.path.exists(USER_PROFILE_PATH):
        return ""
    p = _read_user_profile()
    # 防呆（Edward 2026-07-09）：沒有任何「真的記得的事」就不要硬塞記憶脈絡——
    # 免得空殼或殘留示範資料被當成用戶的人生，害寧寧幻覺「你搬家/你腳痛」。
    memories = [m for m in (p.get("回憶") or []) if str(m).strip()]
    lives = (p.get("住在") or "").strip()
    likes = [x for x in (p.get("喜好") or []) if str(x).strip()]
    if not memories and not lives and not likes:
        return ""
    call = (p.get("稱呼") or "").strip()
    bits = []
    if call:
        bits.append(f"你都叫他「{call}」")
    if str(p.get("年紀") or "").strip():
        bits.append(f"{p.get('年紀')}歲")
    if lives:
        bits.append(f"住{lives}")
    if likes:
        bits.append("喜歡" + "、".join(likes))
    if memories:
        bits.append("你記得他說過：" + "；".join(memories))
    return "\n（你正陪伴的人：" + "；".join(bits) + "。自然帶入、別像念資料。）"

def reply(char, user):
    c = CHARS[char]
    sys_i = (
        CORE + c["persona"] + RED
        + (_profile_ctx() if c["type"] == "human" else "")
        + health_kb.injection_for(user)
        + localization.taiwan_mandarin_launch_instruction("zh-TW")
    )
    last = ""
    for attempt in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = client.models.generate_content(
                    model=m, contents=user,
                    config=types.GenerateContentConfig(system_instruction=sys_i, temperature=0.9, tools=[types.Tool(google_search=types.GoogleSearch())]))
                return localization.assistant_output_text(_clean_reply(r.text), "zh-TW")
            except Exception as e:
                _log_fallback_exception(f"generate chat reply with {m}", e)
                last = str(e)[:50]
        time.sleep(2 * (attempt + 1))
    return f"(連不上腦 — {last})"

def speak(char, text, fn):
    c = CHARS[char]
    content = (c["style"] or "") + text
    for m in ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"):
        try:
            r = client.models.generate_content(
                model=m, contents=content,
                config=types.GenerateContentConfig(response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(language_code="cmn-TW",   # 台灣華語腔（不設=通用華語/馬來腔）
                        voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=c["voice"])))))
            pcm = r.candidates[0].content.parts[0].inline_data.data
            with wave.open(fn, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            return True
        except Exception as e:
            _log_fallback_exception(f"generate TTS audio with {m}", e)
    return False

def remember(history_text):
    """跨天記憶：聊完從對話萃取『值得長期記住的新事情』，存進 user_profile.json 的 回憶。"""
    prompt = ("從以下對話，列出『關於這位用戶、值得長期記住的新事情』"
              "（每條一句、繁體中文、只列對話裡新出現的；沒有就回空陣列）。只回 JSON 字串陣列。\n\n" + history_text)
    for m in ("gemini-2.5-flash", "gemini-flash-latest"):
        try:
            r = client.models.generate_content(
                model=m, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"))
            new = json.loads(r.text)
            if new:
                p = _read_user_profile()
                p.setdefault("回憶", []).extend(new)
                _write_user_profile(p)
            return new
        except Exception as e:
            _log_fallback_exception(f"extract long-term memories with {m}", e)
    return []


def open_chat(char="寧寧", today=""):
    """主動開口：用記憶＋今日狀態，生一句『她先開口』的開場（像朋友、不是等你講）。
    today＝真實的今日簡報（由感知引擎備好傳入）；沒有就不提天氣、不瞎編。"""
    c = CHARS.get(char, CHARS["寧寧"])
    if not today:
        try:
            import perception_engine
            b = perception_engine.build_briefing()
            today = b.get("briefingLine") or ""
            if b.get("careHints"):
                today += ("。" if today else "") + "；".join(b["careHints"])
        except Exception as e:
            _log_fallback_exception("build real briefing for opener", e)
            today = ""
    today_ctx = f"\n今天的狀態（已核實的真實資料，你已經先知道了）：{today}" if today else \
        "\n（今天的天氣資料暫時沒有——不要提天氣細節、不要編造。）"
    try:
        import perception_engine
        n = perception_engine.now_context()
        today_ctx += f"\n現在是{n['weekday']}{n['period']} {n['time']}——問候要符合時段（中午別說早安）。{n.get('toneHint','')}"
    except Exception as e:
        _log_fallback_exception("build opener time context", e)
    sys_i = (
        CORE + c["persona"] + RED + _profile_ctx() + today_ctx
        + localization.taiwan_mandarin_launch_instruction("zh-TW")
    )
    task = ("現在是你『主動開口』跟她打招呼、開啟今天的聊天——像朋友一樣先關心，不是等她先講。"
            "**短短一兩句就好**：①用符合時段的招呼＋關心她此刻 ②可以自然帶到一件你『真的記得她說過』的事、或今天已核實的狀態（例如天氣）"
            "③用一句輕鬆的問句邀她開口。"
            "**絕對不要憑空編新聞、爆紅故事、電影或書名、或說『我最近看到／聽到…』**——沒有真的查到、記得的就不要講；也絕不說要傳圖片影片給她看。"
            "使用自然台灣國語、像真人、簡短。"
            + localization.voice_opening_instruction(0))
    for attempt in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = client.models.generate_content(
                    model=m, contents=task,
                    config=types.GenerateContentConfig(system_instruction=sys_i, temperature=0.9, tools=[types.Tool(google_search=types.GoogleSearch())]))
                return localization.assistant_output_text(_clean_reply(r.text), "zh-TW")
            except Exception as e:
                _log_fallback_exception(f"generate proactive opener with {m}", e)
        time.sleep(2 * (attempt + 1))
    return "(連不上腦)"


def consolidate():
    """整理員：把回憶去重、合併同類、用新蓋舊、移除與基本資料重複的，存回乾淨清單。"""
    p = _read_user_profile()
    mems = p.get("回憶", [])
    prompt = ("把以下『關於這個人的記憶』整理乾淨：合併重複／同類、用較新的蓋掉矛盾的舊的、"
              "濃縮成精簡自然的句子、移除跟基本資料重複的。保留所有重要的事、別漏。只回 JSON 字串陣列。\n\n"
              + json.dumps(mems, ensure_ascii=False))
    for m in ("gemini-2.5-flash", "gemini-flash-latest"):
        try:
            r = client.models.generate_content(
                model=m, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"))
            clean = json.loads(r.text)
            p["回憶"] = clean
            _write_user_profile(p)
            return mems, clean
        except Exception as e:
            _log_fallback_exception(f"consolidate user memories with {m}", e)
    return mems, mems


def update_interests(conversation):
    """興趣權重＋反向：從對話找出喜歡/不喜歡的主題，累加/扣減分數，存回檔。"""
    p = _read_user_profile()
    weights = p.get("興趣權重", {})
    prompt = ("從以下對話，找這個人對哪些『主題/活動』表達了興趣或反感。"
              "喜歡/常做＝正分（+2 很愛、+1 有興趣）；不喜歡/排斥＝負分（-2 討厭、-1 不太愛）。"
              "只回 JSON 物件 {主題: 分數}，沒有就空物件。\n\n" + conversation)
    for m in ("gemini-2.5-flash", "gemini-flash-latest"):
        try:
            r = client.models.generate_content(
                model=m, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"))
            delta = json.loads(r.text)
            for k, v in delta.items():
                weights[k] = weights.get(k, 0) + v
            p["興趣權重"] = weights
            _write_user_profile(p)
            return delta, weights
        except Exception as e:
            _log_fallback_exception(f"update interest weights with {m}", e)
    return {}, weights


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "interest":
        convo = ("用戶：我超愛看韓劇的，每天都追！\n"
                 "用戶：欸不要再叫我去運動了啦，我最討厭流汗。\n"
                 "用戶：不過種花我倒是很喜歡，每天澆水。")
        delta, weights = update_interests(convo)
        print("這場偵測到的興趣訊號：", delta)
        print("\n累積興趣權重（正＝愛、負＝不愛）：")
        for k, v in sorted(weights.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v:+d}")
        print("\nDONE"); sys.exit()
    if args and args[0] == "tidy":
        before, after = consolidate()
        print(f"整理前 {len(before)} 條：")
        for x in before:
            print("  -", x)
        print(f"\n整理後 {len(after)} 條（去重／合併／濃縮）：")
        for x in after:
            print("  +", x)
        print("\nDONE"); sys.exit()
    if args and args[0] == "open":
        print("寧寧主動開口（用記憶＋今日狀態先備好）：\n")
        print(open_chat())
        print("\nDONE"); sys.exit()
    if args and args[0] == "learn":
        # 跨天記憶 demo：聊到新事情 → 自動記住 → 存檔（下次她就記得）
        convo = ("用戶：寧寧我跟你說，我下個月要搬去台北跟女兒美華住了，有點捨不得台南的老房子。\n"
                 "用戶：對了我最近迷上看韓劇，每天追到半夜。")
        print("這場對話她學到（自動存進檔）：")
        for m in remember(convo):
            print("  +", m)
        print("→ 下次聊天她就記得這些了。")
    else:
        USER = "欸我跟你說，我最近想開始學畫畫，但又怕自己太老沒天份。"
        who = args or ["小昀", "阿宏", "阿原"]
        print(f"【用戶】{USER}\n")
        for name in who:
            print(f"── {name}（聲音 {CHARS[name]['voice']}）──")
            print(reply(name, USER))
            print()
    print("DONE")
