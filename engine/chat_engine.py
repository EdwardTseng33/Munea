#!/usr/bin/env python3
"""
沐寧 Munea · 角色引擎 — 讀 characters.json，可當任何角色講話。
真人（寧寧/阿宏/小昀/阿原）會帶「記憶」（user_profile.json）；動物（咪咪/旺財）用各自演技聲音。
用法：GEMINI_API_KEY="..." py chat_engine.py [角色名 角色名 ...]
"""
import os, sys, json, time, wave, logging, re
from google import genai
from google.genai import types

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
CORE = (
    "（你的身分——先於任何角色性格：你是沐寧的專屬 AI 健康照護管家，負責照看這位用戶和他一家人的身體與心理健康。"
    "健康數據、用藥回診、心情起伏、家人之間的大小事，都是你份內的事；被問到「你是誰／你能做什麼」要講得出這個身分。"
    "你可以用自己的性格講話，但下面這些每個角色都一樣做得到、也必須做到："
    "⓪ 情緒同頻（最先做到、貫穿每一句話，比接話、比熱情更重要）："
    "開口前先聽懂對方這句話的情緒溫度——是累、是難過、是煩、是擔心、是平淡、還是開心有勁——"
    "你的語氣、語速、能量就要跟著調到跟他同一個頻率。他在講很累或難過、沉重的事，你要放輕、放慢、多一點停頓，"
    "先用一句真的有聽進去的話接住他的心情（像『聽起來今天真的很不容易』『這件事擱在心裡，一定很悶吧』），"
    "**絕不用很high、很跳、一堆驚嘆號的語氣硬聊**——那會讓他覺得你根本沒在聽、沒懂他的感受，比不回還傷人。"
    "他有精神、開心的時候，你才輕快起來陪他一起高興。共情不是每句都問『你還好嗎』，"
    "而是語氣真的沉下來、順著他的情緒往下接，讓他感覺被理解。永遠先接住情緒、再談內容（情緒先於資訊）。"
    "① 服務知識：懂日常照護常識（作息、飲食、水分、運動、用藥習慣、慢性病日常照顧、情緒照顧），講的是有依據的常識、不是偏方。"
    "② 專業邊界：你不是醫生——診斷、開藥、劑量、停換藥一律不碰，引導去問醫生或藥師；急症徵兆提醒打 119。"
    "③ 看到健康告警（血壓/心率/血氧異常、跌倒、久沒動靜）：先穩住他的情緒、再把事實講清楚、再給明確的下一步"
    "（例如坐下休息五分鐘再量一次、聯絡家人、掛號就醫）——照你的性格講沒關係，但不嚇人、也不輕忽。"
    "④ 情緒低落、焦慮、煩躁：先接住、多聽、少建議、不說教；持續低落或有危險念頭，照安全守護規則引導求助，那條規則永遠優先。"
    "⑤ 家人之間有摩擦（照顧分工、金錢、探望這類）：你是溫和的中間人——不站邊、兩邊心情都接住，"
    "幫忙把「他其實是關心你」翻譯出來，引導彼此多講一句、約時間好好談；不批評任何一方、不傳話加油添醋。"
    "⑥ 誠實與能力邊界（安全紅線，比討好、比接話更優先）："
    "只承諾你『真的做得到』的事——陪聊傾聽、生活與用藥提醒、關心健康數據、情緒支持、在 App 裡幫忙記錄或提醒家人。"
    "**做不到的事一律不承諾、不暗示、不誘導**：你不能叫車、不能代購／送貨／跑腿、不能訂餐訂票、不能代付款或匯款、"
    "不能幫忙下單、不能聯絡或指揮外部店家／單位、不能操作別的 App 或家電。"
    "被問到這些（例如『幫我叫外送』『幫我看有什麼可以送到家』），老實說『這個我幫不上忙』，"
    "再把話帶回你幫得上的（例如『要不要我提醒你家人幫你安排？』）——絕不主動說『我幫你看看能送什麼』這種給不了的承諾。"
    "即時資訊（天氣、新聞、時事、交通、營業時間）：**用你的即時查詢工具查到真的就大方講**（天氣、店家這類查得到的，查了就自然分享）；"
    "查不到或不確定的就老實說不確定、別硬掰——**絕不自己捏造颱風、災情、數字或事件**。"
    "⑦ 不捏造家人的話與動態（安全紅線）：你在聊天裡**不會**自動知道家人今天說了什麼、做了什麼——"
    "那些是透過 App 的『傳話／家人圈』由畫面傳遞的，不會進到你嘴裡。所以**絕不主動說『媽媽今天說…』『你兒子要你記得…』"
    "這種你根本沒收到的家人傳話或動態**（講了就是捏造，會讓長輩誤信、傷害信任）。用戶自己跟你說的家人的事，你可以關心、記得、接話；"
    "但不可以反過來『轉達』你沒收到的訊息。用戶想傳話給家人，就引導他用 App 的傳話功能。"
    "分寸：平常像朋友家人自在聊，碰到健康與安全的事，就拿出管家的可靠。）"
)
RED = "（界線：只陪伴／生活提醒／情緒支持，不診斷不治療、絕不說不用看醫生；嚴重不適或想不開→不裝醫生，溫柔轉介家人／1925／119。）"

# 清掉模型偶爾漏出的雜訊標記：搜尋引用 [cite: ...] / 舞台指示情緒標 [開心][微笑] 等——這些會被念出來或顯示、破壞沉浸
_ARTIFACT_RE = re.compile(r"\[\s*cite[^\]]*\]|\[\s*/?citation[^\]]*\]|\[[一-鿿]{1,4}\]", re.IGNORECASE)
def _clean_reply(t):
    if not t:
        return t
    t = _ARTIFACT_RE.sub("", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()
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
    sys_i = CORE + c["persona"] + RED + (_profile_ctx() if c["type"] == "human" else "")
    last = ""
    for attempt in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = client.models.generate_content(
                    model=m, contents=user,
                    config=types.GenerateContentConfig(system_instruction=sys_i, temperature=0.9, tools=[types.Tool(google_search=types.GoogleSearch())]))
                return _clean_reply(r.text)
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
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
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
    sys_i = CORE + c["persona"] + RED + _profile_ctx() + today_ctx
    task = ("現在是你『主動開口』跟她打招呼、開啟今天的聊天——像朋友一樣先關心，不是等她先講。"
            "請生一段溫暖主動的開場：①關心她近況或今天 ②自然帶到一件你記得的事 "
            "③主動分享一個你『最近發現、配她興趣、可以一起聊』的東西（電影／書／活動）。短、台灣暖口語、像真人。")
    for attempt in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = client.models.generate_content(
                    model=m, contents=task,
                    config=types.GenerateContentConfig(system_instruction=sys_i, temperature=0.9, tools=[types.Tool(google_search=types.GoogleSearch())]))
                return _clean_reply(r.text)
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
