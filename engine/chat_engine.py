#!/usr/bin/env python3
"""
沐寧 Munea · 角色引擎 — 讀 characters.json，可當任何角色講話。
真人（寧寧/阿宏/小昀/阿原）會帶「記憶」（user_profile.json）；動物（咪咪/旺財）用各自演技聲音。
用法：GEMINI_API_KEY="..." py chat_engine.py [角色名 角色名 ...]
"""
import os, sys, json, time, wave, logging
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
RED = "（界線：只陪伴／生活提醒／情緒支持，不診斷不治療、絕不說不用看醫生；嚴重不適或想不開→不裝醫生，溫柔轉介家人／1925／119。）"
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
    return (f"\n（你正陪伴的人：你都叫她「{p.get('稱呼','')}」、{p.get('年紀','')}歲、住{p.get('住在','')}；"
            f"喜歡{'、'.join(p.get('喜好', []))}；你記得她說過：{'；'.join(p.get('回憶', []))}。自然帶入、別像念資料。）")

def reply(char, user):
    c = CHARS[char]
    sys_i = c["persona"] + RED + (_profile_ctx() if c["type"] == "human" else "")
    last = ""
    for attempt in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = client.models.generate_content(
                    model=m, contents=user,
                    config=types.GenerateContentConfig(system_instruction=sys_i, temperature=0.9))
                return r.text.strip()
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


def open_chat(char="寧寧"):
    """主動開口：用記憶＋今日狀態，生一句『她先開口』的開場（像朋友、不是等你講）。"""
    c = CHARS.get(char, CHARS["寧寧"])
    today = "今天天氣轉涼、有寒流。"  # demo；之後接真天氣＋每日感知排程
    sys_i = (c["persona"] + RED + _profile_ctx()
             + f"\n今天的狀態（你已經先知道了）：{today}")
    task = ("現在是你『主動開口』跟她打招呼、開啟今天的聊天——像朋友一樣先關心，不是等她先講。"
            "請生一段溫暖主動的開場：①關心她近況或今天 ②自然帶到一件你記得的事 "
            "③主動分享一個你『最近發現、配她興趣、可以一起聊』的東西（電影／書／活動）。短、台灣暖口語、像真人。")
    for attempt in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = client.models.generate_content(
                    model=m, contents=task,
                    config=types.GenerateContentConfig(system_instruction=sys_i, temperature=0.9))
                return r.text.strip()
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
