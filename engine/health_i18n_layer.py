# -*- coding: utf-8 -*-
"""衛教庫的一國一庫疊層（2026-07-31 · Edward 拍板「B 就是開始做」）。

主庫（health_topics.json / health_solutions.json）＝繁中正本，打分欄位語言中立。
每個語系一份疊層：engine/health_i18n/<locale>/topics.json
  { "topics": { "<topicId>": {
      "keywords": [...],                  # 那一國長輩真的會講的話（不是翻譯腔）
      "solutions": { "<solutionId>": {"say": "...", "label": "...", "dailyCap": "..."} }
  }}}
資源表：engine/health_i18n/<locale>/resources.json（查證過的號碼與制度詞）。

**敗向安全**：疊層缺哪一層，那一層就不出手——絕不退回中文。
轉介卡（L5）沒翻＝整題在那個語系不上（安全話術不能是外語）。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
I18N_DIR = os.path.join(HERE, "health_i18n")
DEFAULT_LOCALE = "zh-TW"

_cache = {}


def normalize(locale):
    raw = str(locale or "").strip()
    if not raw or raw.lower().startswith("zh"):
        return DEFAULT_LOCALE
    short = raw.split("-")[0].lower()
    return short if short in ("ja", "en", "es") else raw


def overlay(locale):
    """讀那一國的疊層；zh-TW＝主庫本身、回 None（走原路）。讀不到＝None（敗向安全）。"""
    loc = normalize(locale)
    if loc == DEFAULT_LOCALE:
        return None
    if loc not in _cache:
        try:
            with open(os.path.join(I18N_DIR, loc, "topics.json"), encoding="utf-8") as f:
                _cache[loc] = json.load(f)
        except Exception:
            _cache[loc] = {}
    data = _cache.get(loc) or {}
    return data.get("topics") or None


def resources(locale):
    loc = normalize(locale)
    try:
        with open(os.path.join(I18N_DIR, loc, "resources.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def keywords_for(topic_id, locale):
    """回傳該語系該題的觸發字；沒有疊層＝空清單（那一國不觸發這題）。"""
    ov = overlay(locale)
    if ov is None:
        return None                      # zh-TW：用主庫的 keywords
    entry = ov.get(topic_id) or {}
    return entry.get("keywords") or []


def localized_solutions(topic_id, solutions, locale):
    """把主庫方案換成該語系的說法。缺說法的方案剔除；轉介卡沒翻＝整題回空（敗向安全）。"""
    ov = overlay(locale)
    if ov is None:
        return solutions                 # zh-TW 原樣
    entry = (ov.get(topic_id) or {}).get("solutions") or {}
    out = []
    referral_ok = False
    for s in solutions:
        loc_s = entry.get(s.get("id"))
        if not (loc_s and loc_s.get("say")):
            continue                     # 沒翻的方案不端出來——絕不退回中文
        merged = dict(s)
        merged["say"] = loc_s["say"]
        for k in ("label", "dailyCap"):
            if loc_s.get(k):
                merged[k] = loc_s[k]
        # 點名觸發字也要在地化；疊層沒給就清空（中文點名字在外語對話裡永遠比對不到）
        merged["askedFor"] = loc_s.get("askedFor") or []
        out.append(merged)
        if merged.get("riskLevel") == "L5":
            referral_ok = True
    if not referral_ok:
        return []                        # 安全出口沒翻＝這題在這個語系不上
    return out
