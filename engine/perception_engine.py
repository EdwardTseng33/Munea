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
    """今日簡報：抓真天氣＋真空品 → 一句人話（scoped 最小注入，不塞原始資料）。
    設計為清晨背景跑；回 dict（facts ＋ briefingLine ＋ careHints）。"""
    region = region or DEFAULT_REGION
    ctx = now_context()
    weather = fetch_weather(region)
    aqi = fetch_aqi(region)
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
    return {
        "date": ctx["date"],
        "weekday": ctx["weekday"],
        "region": region,
        "weather": weather,
        "aqi": aqi,
        "briefingLine": "，".join(parts) if parts else "",
        "careHints": hints,
        "sources": [s for s in {(weather or {}).get("source"), (aqi or {}).get("source")} if s],
    }


if __name__ == "__main__":
    print("時間感知：", json.dumps(now_context(), ensure_ascii=False))
    b = build_briefing()
    print("今日簡報：", json.dumps({k: b[k] for k in ("date", "weekday", "region", "briefingLine", "careHints", "sources")}, ensure_ascii=False, indent=2))
