#!/usr/bin/env python3
"""因人因時因地的方案挑選（2026-07-29 · Edward「同一題三個人要三種答案」）。

為什麼要有這一層：以前一題就一段固定的話，同一句「我睡不好」不管誰問、幾點問，
給的都差不多。Edward 點出核心——年齡、時間與工作壓力（要快還是願意慢慢調）、
活動量、能不能接受吃保健品，**答案應該截然不同**。

設計要點（詳 docs/research/因人因時因地-方案池與挑選邏輯-2026-07-29.md）：
- **選哪個方案交給程式算、不靠模型自覺**——可測、可稽核；說明書只管「怎麼講」。
- **安全先剔除、再排序**：禁忌命中就整個拿掉（不是降權）；L4/L5 不進推薦池、只走轉介。
- **正確但做不到的建議比不給更傷**：輪班的人拿到「固定時間起床」會覺得你不懂他的生活。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SOLUTIONS_PATH = os.environ.get("MUNEA_HEALTH_SOLUTIONS_PATH") or os.path.join(HERE, "health_solutions.json")

with open(SOLUTIONS_PATH, encoding="utf-8") as _f:
    _DOC = json.load(_f)

TOPICS = _DOC["topics"]

# 端幾個出去：主推 1＋備援 2。再多長輩記不住，也違反「講話要短」的鐵律。
MAX_SOLUTIONS = 3

# 急迫詞：講出這些就是「他要的是今晚能做的事」，不管幾點問
URGENCY_WORDS = ("受不了", "撐不住", "快瘋了", "好幾天沒睡", "三天沒睡", "整晚沒睡", "很嚴重", "急")
# 排斥藥丸的說法
PILL_AVERSE_WORDS = ("不想吃藥", "不要吃藥", "不敢吃藥", "藥吃太多", "不想再吃", "怕副作用")
# 偏好中醫
TCM_WORDS = ("中藥", "中醫", "轉骨", "四物", "藥膳")
# 代問偵測（2026-07-29 · 三齡層擴充時發現）：青少年的事多半是爸媽在問、不是本人；
# 長輩的事也常是子女在問。同一題對「本人」跟「替他問的人」要講完全不同的話——
# 對本人是「你可以怎麼做」，對家長是「先理解他不是故意的，你可以怎麼幫」。
PROXY_WORDS = ("我小孩", "我兒子", "我女兒", "我孫", "我家那個", "我兒", "小朋友",
               "我媽", "我爸", "我先生", "我太太", "我老公", "我老婆", "家裡老人家")


# 第一人稱抱怨：出現這些就代表主角是說話的人自己，即使他也提到了別人。
# （2026-07-29 實測抓到：照顧者說「**我媽**三點要起來上廁所，**我**根本睡不飽」——
#  提到媽媽只是原因、主角是她自己；判成代問會害她拿到給家長聽的話。）
SELF_COMPLAINT_WORDS = ("我根本", "我自己", "我都睡", "我睡", "我好累", "我很累", "我快",
                        "我最近", "我每天", "我沒辦法", "我撐", "我覺得",
                        # 2026-07-29 實測補：照顧者講自己的累常常是「照顧到好累」「顧到快撐不住」，
                        # 句子裡有「我媽」但主角是他自己——判成代問會給錯人聽的話。
                        "照顧到", "顧到", "到好累", "到快", "我照顧", "我顧")


def _asking_for_someone_else(user_text):
    text = user_text or ""
    if not any(w in text for w in PROXY_WORDS):
        return False
    # 也講了自己的不舒服 → 主角是他本人，不是代問
    return not any(w in text for w in SELF_COMPLAINT_WORDS)


def _is_urgent(user_text, hour=None):
    """急不急：語氣詞優先，其次看幾點問（半夜問通常就是睡不著本人）。"""
    text = user_text or ""
    if any(w in text for w in URGENCY_WORDS):
        return True
    if hour is not None and (hour >= 23 or hour <= 4):
        return True
    return False


def audience_from_birth_year(birth_year, this_year=2026):
    """從出生年推齡層。判不出來就回 None（不亂猜——猜錯比不猜更傷）。

    分界依 Edward 2026-07-29「高齡／中齡／青少齡」：
      13-19 → teen（青少齡；未滿 13 不做，兒科誤判代價太高）
      20-64 → worker（中齡；名字沿用既有標籤，涵蓋沒在上班的中年人）
      65+   → elder（高齡）
    """
    try:
        year = int(birth_year)
    except (TypeError, ValueError):
        return None
    age = this_year - year
    if age < 13 or age > 120:
        return None
    if age <= 19:
        return "teen"
    if age <= 64:
        return "worker"
    return "elder"


def _profile_flags(profile):
    """把這個人的狀況攤平成挑選要用的旗標。profile 缺欄位一律當「不知道」，不亂猜。"""
    p = profile or {}
    return {
        "audience": p.get("audience"),                       # elder / worker / caregiver / women
        # 挑選時比對用的齡層清單。多數情況就是他自己那一個；照顧者替家人問時
        # 會在 pick() 裡加上被照顧的那位（方案是要給媽媽用的、不是給他用的）。
        "audiences": [p.get("audience")] if p.get("audience") else [],
        "conditions": [str(c) for c in (p.get("conditions") or [])],   # 腎功能異常、低血壓…
        "constraints": [str(c) for c in (p.get("constraints") or [])], # 輪班工作、照顧者夜間需起身…
        "lowMobility": bool(p.get("lowMobility")),
        "pillAverse": bool(p.get("pillAverse")),
        # 這個人試過什麼、結果如何（health_followup.outcomes_for 給的）
        "outcomes": p.get("outcomes") or {},
    }


def _blocked_by_safety(sol, flags, user_text):
    """安全過濾（硬性、排序翻不了）。回傳 True＝整個方案剔除。"""
    if sol.get("blocked"):
        return True
    if sol.get("riskLevel") in ("L4", "L5"):
        return True          # 轉介類另外處理、不進一般推薦池
    for c in sol.get("contraindications") or []:
        if any(c in cond for cond in flags["conditions"]):
            return True      # 腎功能異常 → 鎂直接拿掉，不是降權
    return False


def _score(sol, flags, urgent, user_text):
    """依這個人排序。分數高的先端出去。"""
    score = 0.0
    time_to = sol.get("timeToEffect")

    # 急不急 → 決定時效檔位的權重
    if urgent:
        score += {"今晚": 4.0, "一週": 1.5, "慢養": 0.0}.get(time_to, 0)
    else:
        score += {"慢養": 3.0, "一週": 2.5, "今晚": 1.5}.get(time_to, 0)

    # 對不對這個人（沒標 audience 的方案＝通用，不加不減）
    auds = flags.get("audiences") or ([flags["audience"]] if flags["audience"] else [])
    sol_aud = sol.get("audience")
    if auds and sol_aud:
        if any(a in sol_aud for a in auds):
            # 專屬度：只針對這種處境設計的方案（例照顧者的「把睡眠切兩段」），
            # 要贏過人人適用的通用方案——不然照顧者拿到的主推會是「睡前手機放遠」，
            # 那對「我媽三點要起來」根本答非所問。
            score += 2.0 + (2.0 if len(sol_aud) <= 2 else 0.0)
        else:
            score -= 3.0

    # 做不做得到——正確但做不到的建議比不給更傷
    for c in sol.get("notFor") or []:
        if any(c in x for x in flags["constraints"]):
            score -= 5.0
    if flags["lowMobility"] and sol.get("solutionType") == "運動":
        score -= 2.5
    score += {"低": 1.0, "中": 0.0, "高": -1.0}.get(sol.get("effortCost"), 0)

    # 偏好——排斥藥丸的人不要一直推保健品
    text = user_text or ""
    pill_averse = flags["pillAverse"] or any(w in text for w in PILL_AVERSE_WORDS)
    if pill_averse and sol.get("solutionType") == "保健品":
        score -= 6.0
    if not any(w in text for w in TCM_WORDS) and sol.get("solutionType") == "中醫調理":
        # 他沒提中醫時，傳統經驗類不該壓過有實證的方案——留著（他問就給），但不主動帶頭。
        # 2026-07-29 實測：不壓的話按摩會把有 2025 研究的鎂、以及青少年專屬內容擠掉。
        score -= 2.0
    if any(w in text for w in TCM_WORDS):
        # 他自己提到中醫／中藥＝願意走調理路線：中醫類方案要真的浮上來（原本只加分給
        # 食補與作息，等於他問中醫、我們還是只給西方那套，答非所問）。
        if sol.get("solutionType") == "中醫調理":
            score += 3.0
        elif sol.get("solutionType") in ("食補", "行為調整"):
            score += 0.5

    # 證據強度：同分時已證實的排前面
    score += {"proven": 0.8, "emerging": 0.3, "traditional": 0.0}.get(sol.get("maturity"), 0)

    # 效果飛輪（2026-07-29）：上次推過、他回報過結果的，這次要不一樣——
    # 有效的先講（他信得過、也真的幫到他）、說沒效的別再端出來（再講一次很傷信任）、
    # 還沒試的輕輕加一點（可以再提一次，但不要壓過新方案）。
    outcome = (flags.get("outcomes") or {}).get(sol.get("id"))
    if outcome == "worked":
        score += 3.0
    elif outcome == "no_effect":
        score -= 8.0
    elif outcome == "not_tried":
        score += 0.5
    return score


_TOPIC_KEYWORDS = None


def health_kb_keywords(topic_id):
    """借 health_topics 那份觸發字判斷「他這輪有沒有也提到另一件事」。
    不另外造一份關鍵字——兩份會走鐘（7/29 已經被關鍵字漏洞咬過一次）。"""
    global _TOPIC_KEYWORDS
    if _TOPIC_KEYWORDS is None:
        try:
            with open(os.path.join(HERE, "health_topics.json"), encoding="utf-8") as f:
                doc = json.load(f)
            _TOPIC_KEYWORDS = {t["id"]: t.get("keywords") or [] for t in doc.get("topics") or []}
        except Exception:
            _TOPIC_KEYWORDS = {}
    return _TOPIC_KEYWORDS.get(topic_id) or []


def pick(topic_id, user_text="", profile=None, hour=None, limit=MAX_SOLUTIONS):
    """挑方案。回傳 dict：{"solutions": [...], "referral": {...}|None, "reframe": str|None, "urgent": bool}"""
    topic = TOPICS.get(topic_id)
    if not topic:
        return {"solutions": [], "referral": None, "reframe": None, "urgent": False}

    flags = _profile_flags(profile)
    urgent = _is_urgent(user_text, hour)
    proxy = _asking_for_someone_else(user_text)
    pool = topic.get("solutions") or []
    # 代問時只留「講給家長聽」的版本；本人問只留「講給本人聽」的版本；沒標的兩邊都給。
    pool = [s for s in pool if s.get("forWhom") in (None, "parent" if proxy else "self")]
    # 照顧者替家人問時，方案是要給**被照顧的那位**用的（2026-07-29 骨鬆題抓到）：
    # 「我媽有骨鬆，怕她跌倒」原本只比對 caregiver，結果專為長輩寫的「練肌力跟平衡」
    # 拿不到專屬度加分、被通用建議擠掉——防跌實證最明確的那條反而沒端出去。
    # 兩個齡層都算數：照顧者自己的方案（喘息、把睡眠切兩段）照樣浮得上來。
    if proxy and flags["audience"] == "caregiver":
        flags["audiences"] = ["caregiver", "elder"]

    # secondLine＝可以講、但永遠不准當第一個講的（2026-07-29 搬膝蓋題時抓到）：
    #   ① 證據偏弱的保健品（葡萄糖胺）——排在肌力訓練前面等於把最弱的當主力，
    #      「潑冷水同一句要帶更有效的替代」這個設計就整個反過來了
    #   ② 「這很普遍、不是你特別差」這類安慰話——是配菜、不該吃掉行動建議的位子
    # 用分數硬壓不可靠（差 0.3 分就翻盤），直接分兩層排：正規的先、陪襯的後。
    # 但他自己點名問的不算陪襯——「葡萄糖胺到底有沒有效」問的就是那個，
    # 這時候把答案壓到後面切掉，等於問了不答。
    def _demoted(s):
        if not s.get("secondLine"):
            return False
        return not any(w and w in (user_text or "") for w in (s.get("askedFor") or []))

    ranked = sorted(
        (s for s in pool if not _blocked_by_safety(s, flags, user_text)),
        key=lambda s: (_demoted(s), -_score(s, flags, urgent, user_text)),
    )
    # 類型多樣性：三個建議全是「行為調整」等於同一招講三次，長輩也記不住差別。
    # 挑的時候同類型最多兩個，把位置留給食補／運動／保健品這些不同路數的方案。
    picked, type_count = [], {}
    for s in ranked:
        t = s.get("solutionType")
        if len(picked) >= limit:
            break
        if type_count.get(t, 0) >= 2:
            continue
        picked.append(s)
        type_count[t] = type_count.get(t, 0) + 1
    if len(picked) < limit:   # 池子太小就照原排名補滿，不硬留空位
        for s in ranked:
            if len(picked) >= limit:
                break
            if s not in picked:
                picked.append(s)

    # 轉介卡：紅旗類永遠獨立帶著，不跟一般方案搶名額
    referral = next((s for s in pool if s.get("riskLevel") == "L5"), None)

    # 重新定義問題（例：照顧者不是失眠、是沒得睡）
    reframe = None
    for r in topic.get("reframe") or []:
        if r.get("forWhom") == "parent" and proxy:
            reframe = r["say"]
            break
        if r.get("forWhom") in (None, "self") and not proxy and flags["audience"] == "caregiver"                 and "照顧者" in r.get("when", ""):
            reframe = r["say"]
            break

    # 跨題連結（2026-07-29）：睡不好、血壓飄、心情悶常常是同一件事的不同面向。
    # 只在他這一輪自己也提到那件事時才連——不硬拉、不擴大話題。
    related = None
    for r in topic.get("relatedTopics") or []:
        cue = health_kb_keywords(r.get("topicId"))
        if cue and any(k in (user_text or "") for k in cue):
            related = r.get("say")
            break

    return {"solutions": picked, "referral": referral, "reframe": reframe,
            "urgent": urgent, "proxy": proxy, "related": related}


def render(topic_id, user_text="", profile=None, hour=None):
    """組成注入給模型的那段話。沒挑到東西就回空字串（不佔說明書）。"""
    res = pick(topic_id, user_text, profile, hour)
    if not res["solutions"]:
        return ""
    parts = []
    if res["reframe"]:
        parts.append("【先重新定義問題】" + res["reframe"])
    for i, s in enumerate(res["solutions"]):
        tag = "主推" if i == 0 else f"備援{i}"
        line = f"【{tag}·{s['timeToEffect']}檔·{s['solutionType']}】{s['say']}"
        if s.get("riskLevel") == "L3":
            # L3 三件事少講一件就不合格——這裡把上限與禁忌接在後面，確保她講得到
            line += f"（**這是保健品，同一段話一定要講到：一天上限{s.get('dailyCap','請問專業')}、"
            line += f"以及{'、'.join(s.get('contraindications') or [])}的人要先問醫師或營養師**）"
        parts.append(line)
    if res.get("related"):
        parts.append("【這兩件事可能有關】" + res["related"])
    if res["referral"]:
        parts.append("【什麼時候該看醫生】" + res["referral"]["say"])
    head = (
        "（因人挑選的方案・這一輪他聊到這個困擾，下面是**按他的狀況挑好的**方案，"
        "照順序講、主推先講，不要一次全講完；先接住情緒、保持一兩句短話、他想深入才展開。"
        "絕不推薦品牌、不做藥物判斷："
    )
    return head + "".join(parts) + "）"
