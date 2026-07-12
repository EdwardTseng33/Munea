"""沐寧感知引擎 · V1 地基（時間／天氣／空氣品質／今日簡報）

定案架構（docs/感知層-定案規劃-2026-07-02.md）：
- 清晨背景先備好 → 存 snapshot → 開場注入 → 通話中只讀已備好的、絕不臨時對外查。
- 天氣主源＝中央氣象署 CWA（要免費鑰匙 CWA_API_KEY）；沒鑰匙先用 Open-Meteo（免費免鑰匙）兜底，
  兩源都是「已核實真實值」——寧寧不憑感覺講天氣。
- 空品主源＝環境部 moenv（要免費鑰匙 MOENV_API_KEY）；兜底 Open-Meteo air-quality。
- 時間＝台灣固定 UTC+8（無日光節約），零依賴、即時算、不存。

單獨自測：python engine/perception_engine.py
"""

import os
import json
import datetime
import urllib.request
import urllib.parse

TW_TZ = datetime.timezone(datetime.timedelta(hours=8))  # 台灣無日光節約、固定 +8 安全

# 22 縣市 → 座標（Open-Meteo 兜底用）；CWA 直接吃縣市名
_COORDS = {
    "臺北市": (25.033, 121.565), "新北市": (25.017, 121.463), "基隆市": (25.128, 121.742),
    "桃園市": (24.994, 121.301), "新竹市": (24.804, 120.971), "新竹縣": (24.839, 121.008),
    "苗栗縣": (24.560, 120.821), "臺中市": (24.148, 120.674), "彰化縣": (24.052, 120.516),
    "南投縣": (23.961, 120.972), "雲林縣": (23.709, 120.431), "嘉義市": (23.480, 120.449),
    "嘉義縣": (23.452, 120.256), "臺南市": (22.999, 120.227), "高雄市": (22.627, 120.301),
    "屏東縣": (22.552, 120.549), "宜蘭縣": (24.702, 121.738), "花蓮縣": (23.977, 121.604),
    "臺東縣": (22.756, 121.144), "澎湖縣": (23.571, 119.579), "金門縣": (24.437, 118.318),
    "連江縣": (26.151, 119.929),
}

DEFAULT_REGION = os.environ.get("MUNEA_REGION") or "臺北市"

_PERIODS = [
    (5, 8, "清晨", "溫柔道早安，關心睡得好不好"),
    (8, 11, "早上", "精神好的時段，適合聊今天的計畫"),
    (11, 14, "中午", "可以關心吃飯了沒"),
    (14, 17, "下午", "悠閒時段，適合聊興趣話題"),
    (17, 19, "傍晚", "可以關心晚餐、今天過得如何"),
    (19, 22, "晚上", "放鬆時段，聊聊今天的事"),
    (22, 24, "深夜", "該休息了，語氣放輕、關心睡眠、不催不吵"),
    (0, 5, "深夜", "該休息了，語氣放輕、關心睡眠、不催不吵"),
]

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def now_context():
    """當地時間感知：日期／星期／時段／該時段的語氣提示。即時算、零依賴、不存。"""
    now = datetime.datetime.now(TW_TZ)
    period, hint = "白天", ""
    for start, end, name, h in _PERIODS:
        if start <= now.hour < end:
            period, hint = name, h
            break
    return {
        "date": now.strftime("%Y-%m-%d"),
        "weekday": _WEEKDAYS[now.weekday()],
        "time": now.strftime("%H:%M"),
        "hour": now.hour,
        "period": period,
        "toneHint": hint,
    }


def _http_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _weather_cwa(region):
    """中央氣象署 F-C0032-001（今明 36 小時）。要免費鑰匙 CWA_API_KEY。"""
    key = os.environ.get("CWA_API_KEY")
    if not key:
        return None
    url = ("https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?"
           + urllib.parse.urlencode({"Authorization": key, "locationName": region}))
    data = _http_json(url)
    locs = (((data.get("records") or {}).get("location")) or [])
    if not locs:
        return None
    elems = {e.get("elementName"): e for e in (locs[0].get("weatherElement") or [])}

    def first(name, field="parameterName"):
        try:
            return elems[name]["time"][0]["parameter"][field]
        except (KeyError, IndexError, TypeError):
            return None

    return {
        "source": "cwa",
        "region": region,
        "desc": first("Wx"),
        "tempMin": _to_num(first("MinT")),
        "tempMax": _to_num(first("MaxT")),
        "rainProb": _to_num(first("PoP")),
    }


def _weather_openmeteo(region):
    """Open-Meteo 免費免鑰匙兜底（真實預報、非瞎編）。"""
    lat, lon = _COORDS.get(region, _COORDS[DEFAULT_REGION])
    url = ("https://api.open-meteo.com/v1/forecast?"
           + urllib.parse.urlencode({
               "latitude": lat, "longitude": lon,
               "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max",
               "timezone": "Asia/Taipei", "forecast_days": 1,
           }))
    data = _http_json(url)
    daily = data.get("daily") or {}

    def first(k):
        v = daily.get(k) or []
        return v[0] if v else None

    return {
        "source": "open-meteo",
        "region": region,
        "desc": None,
        "tempMin": first("temperature_2m_min"),
        "tempMax": first("temperature_2m_max"),
        "rainProb": first("precipitation_probability_max"),
    }


def fetch_weather(region=None):
    """今天的真天氣：CWA（有鑰匙）優先、Open-Meteo 兜底；都失敗回 None（寧寧就不提、不瞎編）。"""
    region = region or DEFAULT_REGION
    for fn in (_weather_cwa, _weather_openmeteo):
        try:
            w = fn(region)
            if w and (w.get("tempMax") is not None or w.get("desc")):
                return w
        except Exception:
            continue
    return None


_WMO_WEATHER_DESC = {
    0: "晴天", 1: "晴時多雲", 2: "多雲", 3: "陰天",
    45: "有霧", 48: "有霧",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨",
    56: "凍雨", 57: "凍雨",
    61: "有雨", 63: "有雨", 65: "大雨",
    66: "凍雨", 67: "凍雨",
    71: "下雪", 73: "下雪", 75: "大雪", 77: "陣雪",
    80: "陣雨", 81: "陣雨", 82: "強陣雨",
    85: "陣雪", 86: "強陣雪",
    95: "雷雨", 96: "雷雨", 99: "雷雨",
}


def _weathercode_desc(code):
    """WMO 天氣代碼（Open-Meteo 用）→ 中文一句描述；查不到回 None（不瞎猜）。"""
    try:
        return _WMO_WEATHER_DESC.get(int(code))
    except (TypeError, ValueError):
        return None


def _weather_cwa_tomorrow(region):
    """明天天氣（CWA F-C0032-001 今明 36 小時預報、抓 startTime 落在明天日期的區段）。要 CWA_API_KEY。"""
    key = os.environ.get("CWA_API_KEY")
    if not key:
        return None
    url = ("https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?"
           + urllib.parse.urlencode({"Authorization": key, "locationName": region}))
    data = _http_json(url)
    locs = (((data.get("records") or {}).get("location")) or [])
    if not locs:
        return None
    elems = {e.get("elementName"): e for e in (locs[0].get("weatherElement") or [])}
    tomorrow = (datetime.datetime.now(TW_TZ) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    def value_for_tomorrow(name, field="parameterName"):
        try:
            for t in elems[name]["time"]:
                if str(t.get("startTime", "")).startswith(tomorrow):
                    return t["parameter"][field]
        except (KeyError, TypeError):
            pass
        return None

    desc = value_for_tomorrow("Wx")
    tmin = _to_num(value_for_tomorrow("MinT"))
    tmax = _to_num(value_for_tomorrow("MaxT"))
    rain = _to_num(value_for_tomorrow("PoP"))
    if desc is None and tmin is None and tmax is None:
        return None
    return {"source": "cwa", "region": region, "desc": desc, "tempMin": tmin, "tempMax": tmax, "rainProb": rain}


def _weather_openmeteo_tomorrow(region):
    """Open-Meteo 免費免鑰匙兜底：明天預報（forecast_days=2、取索引 1＝明天）。"""
    lat, lon = _COORDS.get(region, _COORDS[DEFAULT_REGION])
    url = ("https://api.open-meteo.com/v1/forecast?"
           + urllib.parse.urlencode({
               "latitude": lat, "longitude": lon,
               "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max,weathercode",
               "timezone": "Asia/Taipei", "forecast_days": 2,
           }))
    data = _http_json(url)
    daily = data.get("daily") or {}

    def at(k, i=1):
        v = daily.get(k) or []
        return v[i] if len(v) > i else None

    tmin = at("temperature_2m_min")
    tmax = at("temperature_2m_max")
    rain = at("precipitation_probability_max")
    code = at("weathercode")
    if tmin is None and tmax is None:
        return None
    return {"source": "open-meteo", "region": region, "desc": _weathercode_desc(code),
            "tempMin": tmin, "tempMax": tmax, "rainProb": rain}


def fetch_tomorrow_preview(region=None):
    """明天預告：CWA（有鑰匙）優先、Open-Meteo 兜底；都失敗回 None（寧寧就不先講、不瞎編）。
    給清晨簡報用——讓寧寧能自然說『明天會下雨、記得帶傘』。"""
    region = region or DEFAULT_REGION
    for fn in (_weather_cwa_tomorrow, _weather_openmeteo_tomorrow):
        try:
            w = fn(region)
            if w and (w.get("tempMax") is not None or w.get("desc")):
                return w
        except Exception:
            continue
    return None


def _aqi_moenv(region):
    """環境部 AQI（aqx_p_432）。要免費鑰匙 MOENV_API_KEY。"""
    key = os.environ.get("MOENV_API_KEY")
    if not key:
        return None
    url = ("https://data.moenv.gov.tw/api/v2/aqx_p_432?"
           + urllib.parse.urlencode({"api_key": key, "limit": 200, "format": "JSON"}))
    data = _http_json(url)
    best = None
    for rec in data.get("records") or []:
        if rec.get("county") == region:
            try:
                aqi = int(rec.get("aqi"))
            except (TypeError, ValueError):
                continue
            best = max(best, aqi) if best is not None else aqi
    return {"source": "moenv", "region": region, "aqi": best} if best is not None else None


def _aqi_openmeteo(region):
    lat, lon = _COORDS.get(region, _COORDS[DEFAULT_REGION])
    url = ("https://air-quality-api.open-meteo.com/v1/air-quality?"
           + urllib.parse.urlencode({"latitude": lat, "longitude": lon,
                                     "current": "us_aqi", "timezone": "Asia/Taipei"}))
    data = _http_json(url)
    aqi = (data.get("current") or {}).get("us_aqi")
    return {"source": "open-meteo", "region": region, "aqi": aqi} if aqi is not None else None


def fetch_aqi(region=None):
    region = region or DEFAULT_REGION
    for fn in (_aqi_moenv, _aqi_openmeteo):
        try:
            a = fn(region)
            if a and a.get("aqi") is not None:
                return a
        except Exception:
            continue
    return None


def _to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def care_hints(weather, aqi):
    """把數字翻成「關心提示」（餵守護腦/主動開口用）：寒流添衣、高溫防曬、下雨帶傘、空品差少出門。"""
    hints = []
    if weather:
        tmin, tmax, rain = weather.get("tempMin"), weather.get("tempMax"), weather.get("rainProb")
        if tmin is not None and tmin <= 14:
            hints.append("天冷，提醒添衣保暖、關節保暖")
        if tmax is not None and tmax >= 34:
            hints.append("天氣很熱，提醒多喝水、避免中午外出")
        if rain is not None and rain >= 60:
            hints.append("很可能下雨，出門記得帶傘、小心路滑")
    if aqi and aqi.get("aqi") is not None:
        if aqi["aqi"] >= 150:
            hints.append("空氣品質不好，建議少出門、出門戴口罩")
        elif aqi["aqi"] >= 100:
            hints.append("空氣品質普通偏差，敏感體質出門留意")
    return hints


def _aqi_label(aqi_value):
    if aqi_value is None:
        return None
    if aqi_value <= 50:
        return "良好"
    if aqi_value <= 100:
        return "普通"
    if aqi_value <= 150:
        return "對敏感族群不健康"
    return "不健康"


def build_briefing(region=None):
    """今日簡報：抓真天氣＋真空品＋明天預告 → 一句人話（scoped 最小注入，不塞原始資料）。
    設計為清晨背景跑；回 dict（facts ＋ briefingLine ＋ tomorrowLine ＋ careHints）。
    per-region（上線接法）：region 參數＝要備的縣市；目前試營運單一長輩（單一 MUNEA_REGION）。
    真帳號多人上線時＝每個長輩各自縣市各備一份：由呼叫端（run_daily_briefing.py／server.refresh_daily_briefing）
    迴圈每個長輩呼叫 build_briefing(該長輩的縣市) 再各自存各自 personId 的 snapshot，本函式簽章不用改。"""
    region = region or DEFAULT_REGION
    ctx = now_context()
    weather = fetch_weather(region)
    aqi = fetch_aqi(region)
    tomorrow = fetch_tomorrow_preview(region)
    parts = []
    if weather:
        seg = f"{region}今天"
        if weather.get("desc"):
            seg += weather["desc"] + "、"
        if weather.get("tempMin") is not None and weather.get("tempMax") is not None:
            seg += f"{round(weather['tempMin'])}到{round(weather['tempMax'])}度"
        if weather.get("rainProb") is not None:
            seg += f"、降雨機率{round(weather['rainProb'])}%"
        parts.append(seg)
    label = _aqi_label((aqi or {}).get("aqi"))
    if label:
        parts.append(f"空氣品質{label}")
    hints = care_hints(weather, aqi)
    tomorrow_line = ""
    if tomorrow:
        seg = "明天"
        if tomorrow.get("desc"):
            seg += tomorrow["desc"] + "、"
        if tomorrow.get("tempMin") is not None and tomorrow.get("tempMax") is not None:
            seg += f"{round(tomorrow['tempMin'])}到{round(tomorrow['tempMax'])}度"
        rain = tomorrow.get("rainProb")
        if rain is not None:
            seg += f"、降雨機率{round(rain)}%"
            if rain >= 60:
                seg += "，記得先準備傘"
        tomorrow_line = seg
    return {
        "date": ctx["date"],
        "weekday": ctx["weekday"],
        "region": region,
        "weather": weather,
        "aqi": aqi,
        "tomorrow": tomorrow,
        "briefingLine": "，".join(parts) if parts else "",
        "tomorrowLine": tomorrow_line,
        "careHints": hints,
        "sources": [s for s in {(weather or {}).get("source"), (aqi or {}).get("source"), (tomorrow or {}).get("source")} if s],
    }


_GENAI = None


def _genai_client():
    global _GENAI
    if _GENAI is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            return None
        from google import genai
        _GENAI = genai.Client(api_key=key)
    return _GENAI


_MOOD_SYS = """你是沐寧的心情觀察員（陪伴用，非醫療、絕不診斷）。讀「長輩（使用者）這輪對話說的話」，
從三個角度溫和觀察：語氣（怎麼說：有沒有精神、急促或低緩——由文字語感推測）、用語（慣用說法、話量、主動或簡短）、用詞（選了什麼字眼：正向/負向/身體/思念/火氣）。
只回 JSON：
{"mood":"開心|愉快|平穩|疲累|低落|煩躁",  // 六類擇一（心情圖譜）
 "level":1-5,  // 心情高低：5=很好 4=不錯 3=平平 2=偏低 1=很低（煩躁通常 1-2、疲累通常 2-3）
 "voiceObs":"聲音聽起來…（有精神/平穩/比較累，一短句）",
 "chatObs":"聊天狀態…（話匣子全開/平常/話比較少，一短句）",
 "wordObs":"用詞觀察一短句（例：提到開心的事居多／出現想念、疼痛字眼／講到某事有點火氣）",
 "topics":["聊到的話題1","2","3"],
 "positives":["提到的開心事"],
 "concerns":["提到的掛心事（身體不適/想念/煩惱/火氣的事），沒有就空"],
 "confidence":0-1}
規則：這是「觀察」不是「判定」；絕不用憂鬱/焦慮/失智等臨床字眼（火氣寫「有點火氣」、難過寫「比較低落」）；資訊不足時 mood 給平穩、level 給 3、confidence 給低。"""

MOOD_CATEGORIES = {
    "開心": {"colorKey": "coral", "bg": "#FBE7D2", "fg": "#C25716"},
    "愉快": {"colorKey": "apricot", "bg": "#F6ECD4", "fg": "#9A6E14"},
    "平穩": {"colorKey": "teal", "bg": "#E8F2EE", "fg": "#1E7169"},
    "疲累": {"colorKey": "grayGreen", "bg": "#EEEFEA", "fg": "#5F6A61"},
    "低落": {"colorKey": "grayBlue", "bg": "#E4EBF3", "fg": "#3F5F80"},
    "煩躁": {"colorKey": "plum", "bg": "#ECE1F0", "fg": "#6E4488"},
}


def analyze_conversation_mood(history):
    """聊完的心情觀察（語氣/用語/用詞三角度）→ 給趨勢庫與心情卡。非醫療、只觀察。"""
    client = _genai_client()
    user_text = "\n".join(h.get("text", "") for h in (history or [])
                          if h.get("role") == "user" and h.get("text"))
    if not client or not user_text.strip():
        return None
    from google.genai import types as gtypes
    try:
        r = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[gtypes.Content(role="user", parts=[gtypes.Part(text="長輩這輪說的話：\n" + user_text)])],
            config=gtypes.GenerateContentConfig(
                system_instruction=_MOOD_SYS, temperature=0.2, response_mime_type="application/json"),
        )
        m = json.loads(r.text)
    except Exception:
        return None
    if not isinstance(m, dict):
        return None
    level = m.get("level")
    try:
        level = max(1, min(5, int(level)))
    except (TypeError, ValueError):
        return None
    mood = m.get("mood") if m.get("mood") in MOOD_CATEGORIES else "平穩"
    return {
        "mood": mood,                                   # 六類心情圖譜
        "moodColor": MOOD_CATEGORIES[mood],             # 顯示層直接用（bg/fg/colorKey）
        "level": level,
        "levelLabel": mood,                             # 相容舊欄位：現在＝心情類別名
        "voiceObs": (m.get("voiceObs") or "").strip()[:60],
        "chatObs": (m.get("chatObs") or "").strip()[:60],
        "wordObs": (m.get("wordObs") or "").strip()[:60],
        "topics": [str(t).strip() for t in (m.get("topics") or []) if str(t).strip()][:5],
        "positives": [str(t).strip() for t in (m.get("positives") or []) if str(t).strip()][:3],
        "concerns": [str(t).strip() for t in (m.get("concerns") or []) if str(t).strip()][:3],
        "confidence": round(float(m.get("confidence", 0.5) or 0.5), 2),
    }


# 暖新聞選稿護欄已併入下方 _TOPICS_SYS（本週多元話題、含暖新聞這一類）——fetch_daily_news() 相容舊接口見下。
_TOPICS_SYS = """你是沐寧的話題選稿員，幫忙準備「這週適合跟台灣長輩聊天」的話題小卡。用搜尋找最近真實、
多元、對長輩有意義的內容，最多 3 則、類型盡量不重複：
- 暖新聞（溫馨社會、動物、運動賽事佳績、文化節慶、在地活動）
- 生活健康（非醫囑的養生小知識、當季飲食、節氣提醒）
- 懷舊文化（老歌老電影週年、傳統節慶由來、懷舊生活話題）
絕不准：政治、犯罪、詐騙、災難、疾病恐慌、爭議、任何會引發焦慮的內容。
找不到夠多真實內容就少給、寧可只給 1-2 則甚至 0 則，絕不編造。
只回 JSON：{"topics":[{"line":"一句話開場白（40字內、口語、適合當開話題）","topic":"分類標籤（暖新聞/生活健康/懷舊文化）"}]}
（沒有合適的就回 {"topics":[]}）"""

_NEWS_BANNED_WORDS = ("政治", "詐騙", "詐欺", "命案", "車禍", "地震", "疫情", "戰爭", "槍", "毒")


def fetch_weekly_topics(count=3):
    """本週話題小卡（真搜尋、多元、有護欄）：暖新聞＋生活健康＋懷舊文化，最多 count 則。
    找不到夠多寧可少給、絕不編（沿用暖新聞同款 banned 過濾）。整合進清晨簡報、通話中當接話素材。"""
    client = _genai_client()
    if not client:
        return []
    from google.genai import types as gtypes
    try:
        r = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"請找最近適合台灣長輩聊天的話題，最多 {count} 則、類型盡量不同。",
            config=gtypes.GenerateContentConfig(
                system_instruction=_TOPICS_SYS, temperature=0.3,
                tools=[gtypes.Tool(google_search=gtypes.GoogleSearch())]),
        )
        text = r.text or ""
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start:end + 1]) if start >= 0 and end > start else {}
    except Exception:
        return []
    raw = data.get("topics") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        line = (item.get("line") or "").strip()
        if not line or len(line) > 60:
            continue
        if any(b in line for b in _NEWS_BANNED_WORDS):
            continue
        out.append({"line": line, "topic": (item.get("topic") or "").strip()[:12], "source": "search"})
        if len(out) >= count:
            break
    return out


def fetch_daily_news():
    """相容舊接口：回單一則暖新聞（沿用 fetch_weekly_topics 取第一則、同一套護欄）。
    新整合請改用 fetch_weekly_topics（備 2-3 則多元話題）。"""
    topics = fetch_weekly_topics(count=1)
    return topics[0] if topics else None


def fetch_nearby_places(kind="pharmacy", region=None, limit=3):
    """在地感知（免鑰匙 OpenStreetMap）：找縣市中心附近的藥局/診所/公園。獨立呼叫、不進即時通話。"""
    region = region or DEFAULT_REGION
    lat, lon = _COORDS.get(region, _COORDS[DEFAULT_REGION])
    tags = {"pharmacy": '["amenity"="pharmacy"]', "clinic": '["amenity"="clinic"]', "park": '["leisure"="park"]'}
    tag = tags.get(kind, tags["pharmacy"])
    query = f'[out:json][timeout:8];nwr{tag}(around:4000,{lat},{lon});out center {max(limit * 4, 12)};'
    try:
        req = urllib.request.Request(
            "https://overpass-api.de/api/interpreter",
            data=urllib.parse.urlencode({"data": query}).encode(),
            headers={"accept": "application/json",
                     "user-agent": "Munea/1.0 (elder-care companion; contact: app@munea.tw)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = []
        for el in (data.get("elements") or []):
            name = (el.get("tags") or {}).get("name")
            if name and name not in out:
                out.append(name)
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


if __name__ == "__main__":
    print("時間感知：", json.dumps(now_context(), ensure_ascii=False))
    b = build_briefing()
    print("今日簡報：", json.dumps({k: b[k] for k in ("date", "weekday", "region", "briefingLine", "tomorrowLine", "careHints", "sources")}, ensure_ascii=False, indent=2))
    print("本週話題：", json.dumps(fetch_weekly_topics(count=3), ensure_ascii=False, indent=2))
