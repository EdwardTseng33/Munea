#!/usr/bin/env python3
"""衛教知識庫（B2・2026-07-24）：21 題策展題庫的觸發與注入。

設計拍板（7/24）＝混合式：
- 常駐：保命紅線（中風FAST／心梗／低血糖／急性譫妄）＋褪黑激素法規，由 chat_engine.RED 併入、
  文字線與語音線每一輪都在。
- 觸發：其餘 21 題按「長輩真實問法」關鍵字命中才注入（單次 +500-700 字）。
  否決全塞——21 題全進說明書會膨脹兩倍、把安全紅線淹沒在雜訊裡。

策展題庫、不是開放式 RAG（7/24 三路調研收斂）：內容全部出自已雙審的
docs/research/衛教題庫-21題完整劇本v1-2026-07-24.md，紅旗逐條回鏈官方來源；
這個模組只做關鍵字比對與文字組裝，不呼叫任何模型、不連網、不碰劑量與診斷。
"""
import json
import os

import health_followup
import health_selector
import health_i18n_layer as _i18n

HERE = os.path.dirname(os.path.abspath(__file__))
TOPICS_PATH = os.path.join(HERE, "health_topics.json")

with open(TOPICS_PATH, encoding="utf-8") as _f:
    _DOC = json.load(_f)

TOPICS = _DOC["topics"]
TOPIC_BY_ID = {t["id"]: t for t in TOPICS}

# 每通電話最多注入幾題：衛教是配菜、不是把通話變成衛教講座。
MAX_TOPICS_PER_CALL = 3
# 單輪最多同時注入幾題：兩題以上通常代表用戶一句話跨題，再多就淹沒重點。
MAX_TOPICS_PER_TURN = 2


def resident_rules(locale="zh-TW"):
    """常駐保命紅線（進 chat_engine.RED、所有線路每輪都在）。

    2026-07-31 人設書分國後收語系：急症判斷（中風／心肌梗塞／低血糖／譫妄）各國通用，
    但**法規那條各國不同**——褪黑激素在台灣是處方藥、在日本則是沒有核准上市，
    講錯等於給錯法律資訊。該語系沒有專屬版本就退回中文版（不會開天窗）。
    """
    key = f"resident_{locale.replace('-', '_')}"
    return _DOC.get(key) or _DOC["resident"]


def match_topics(text, limit=MAX_TOPICS_PER_TURN, exclude=None, locale=None):
    """關鍵字比對：回傳命中的 topic id 清單（命中字愈長愈優先＝愈specific愈可信）。
    純字串包含比對——ASR 字幕沒有標點、打字有錯字都吃得下最大公約數；不做模型呼叫。"""
    if not text:
        return []
    exclude = exclude or ()
    scored = []
    # 一國一庫（2026-07-31 Edward 拍板 B）：非中文語系用那一國疊層的觸發字；
    # 沒有疊層的題＝那一國不觸發（敗向安全——絕不拿中文字去比外語對話）。
    _ov_locale = _i18n.normalize(locale) if locale else _i18n.DEFAULT_LOCALE
    # 拉丁語系要忽略大小寫：使用者講「No puedo dormir」、疊層寫小寫，
    # 逐字比對就整個叫不出來（中文沒有大小寫，所以這個坑到出國才踩到）。
    _hay = text.lower()
    for t in TOPICS:
        if t["id"] in exclude:
            continue
        _kws = t["keywords"]
        if _ov_locale != _i18n.DEFAULT_LOCALE:
            _kws = _i18n.keywords_for(t["id"], _ov_locale) or []
        hit_len = sum(len(k) for k in _kws if health_selector.mentions(k, text))
        if hit_len:
            # 具體處境要壓過一般症狀（2026-07-29 加女性題時抓到）：
            # 「最近一直熱潮紅、晚上睡不好」原本被當成一般失眠——更年期的題才是
            # 在解釋那個睡不好。孕哺給最高分：懷孕的人問任何東西，安全圍籬都要先站出來。
            scored.append((t.get("specificity", 0), hit_len, t["id"]))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [tid for _, _, tid in scored[:limit]]


def injection_for(text, exclude=None, profile=None, hour=None, recent_topic=None, locale=None):
    """文字線用：按這一句用戶的話組出注入段；沒命中回空字串（不佔說明書）。

    2026-07-29：命中的題目若已經有「方案池」（因人因時因地挑選），改用挑選層的結果——
    同一句「我睡不好」，上班族半夜問跟長輩早上問會拿到不同的方案。沒建方案池的題
    照舊走原本那段固定注入文，兩者並存、不必一次搬完 21 題。
    """
    ids = match_topics(text, exclude=exclude, locale=locale)
    # 2026-07-29（考卷實測抓到）：話題是連續的，關鍵字比對卻只看這一句。
    # 「我睡不好」→「吃鎂有用嗎，真的假的？」第二句命中的是謠言查證題，
    # 她就拿不到鎂的方案、只能講泛泛之談。上一輪在聊的那題要接得回來。
    if recent_topic and recent_topic in health_selector.TOPICS and recent_topic not in ids:
        ids = [recent_topic] + ids
    if not ids:
        return ""
    # 2026-07-29（三齡層擴充時抓到）：同一句話可能命中好幾題（青少年說「睡不飽」會同時
    # 命中成人失眠題與青少年睡眠題）。**要挑對這個人的那一題**——不然高中生會拿到
    # 「白天曬太陽對長輩特別有效」這種答非所問的建議。有標齡層的題優先。
    aud = (profile or {}).get("audience")
    if aud:
        def _serves_audience(tid):
            topic = health_selector.TOPICS.get(tid)
            if not topic:
                return False
            # 要「專門為這個齡層寫的方案」才算數（audience 清單短），不是隨便掛了名就算——
            # 2026-07-29 實測：按摩掛了五個齡層，害青少年被路由到成人失眠題、拿到長輩版建議。
            return any(aud in (s.get("audience") or []) and len(s.get("audience") or []) <= 2
                       for s in topic.get("solutions") or [])
        ids = sorted(ids, key=lambda t: (not _serves_audience(t),))
    for tid in ids:
        if tid in health_selector.TOPICS:
            picked = health_selector.render(tid, text, profile, hour, locale=locale)
            if picked:
                # 效果飛輪：把這次推了什麼記下來，幾天後她才問得出「後來有沒有好一點」。
                # 記不起來也不能擋住對話——這只是加分項，不是必要路徑。
                pid = (profile or {}).get("personId")
                if pid:
                    try:
                        chosen = health_selector.pick(tid, text, profile, hour, locale=locale)["solutions"]
                        health_followup.record_recommendation(pid, tid, chosen)
                    except Exception:
                        pass
                return picked
    parts = []
    for tid in ids:
        t = TOPIC_BY_ID[tid]
        parts.append(f"【{t['title']}】{t['inject']}（出處：{t['source']}）")
    return (
        "（衛教資料庫命中・這一輪他聊到相關話題，回應時自然運用下面已審核的衛教方向；"
        "先接住情緒，**話量你自己判斷**——他只是抱怨一句就短短接住，真的在問怎麼辦就先講結論、"
        "再講必要的重點；"
        "一輪講不完時的取捨順序：紅旗紅線＞更有效的替代方向＞證據誠實——"
        "潑冷水（說某保健品沒那麼神）時同一句要帶更有效的替代、不能只否定不給路；"
        "若其實不相關就忽略這段："
        + "".join(parts) + "）"
    )


def voice_cue(topic_id, user_text="", profile=None, hour=None, locale=None):
    """語音線用：在守護腦同一個「輪替空檔」機制排隊送出的衛教提示（每題整通只送一次）。

    2026-07-29：有方案池的題也走因人挑選——聊聊是主戰場，長輩版跟青少年版不能混。
    """
    if topic_id in health_selector.TOPICS:
        picked = health_selector.render(topic_id, user_text, profile, hour, locale=locale)
        if picked:
            return (
                "（系統衛教提示、不是用戶說的話——絕不把這段提示唸出來，"
                "自然運用下面按他狀況挑好的方案；先接住情緒，**話量你自己判斷**（他抱怨一句就短短接住，真的在問怎麼辦就先講結論再講重點、分小段、他插話就停）："
                + picked + "）"
            )
    t = TOPIC_BY_ID[topic_id]
    return (
        f"（系統衛教提示、不是用戶說的話——他剛聊到「{t['title']}」相關話題。"
        f"接下來回應時自然運用這份已審核的衛教方向、絕不把這段提示唸出來："
        f"{t['inject']}（出處：{t['source']}）"
        "先接住情緒，**話量你自己判斷**——短是預設，但他真的在問就把該講的講清楚。）"
    )
