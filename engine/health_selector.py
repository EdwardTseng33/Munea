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
import health_i18n_layer as _i18n
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SOLUTIONS_PATH = os.environ.get("MUNEA_HEALTH_SOLUTIONS_PATH") or os.path.join(HERE, "health_solutions.json")

with open(SOLUTIONS_PATH, encoding="utf-8") as _f:
    _DOC = json.load(_f)

TOPICS = _DOC["topics"]

# 端幾個出去：主推 1＋備援 2。再多長輩記不住，也違反「講話要短」的鐵律。
MAX_SOLUTIONS = 3

# 急迫詞：講出這些就是「他要的是今晚能做的事」，不管幾點問
# 2026-07-29：audience 這欄混了兩種東西——齡層（從出生年推得出來）跟處境
# （照顧者、女性身體，推不出來）。正式機的齡層只可能是 teen/worker/elder，
# 所以 caregiver 與 women 從來沒出現過：掛這兩個標籤的方案不只拿不到專屬度加分，
# 還因為「對不上這個人」被倒扣 3 分——照顧者專屬內容（喘息、把睡眠切兩段）
# 跟整組女性題等於一直被壓在底下。分開之後：齡層對不上才扣分，處境標籤只加不扣。
AGE_AUDIENCES = ("teen", "worker", "elder")
SITUATION_AUDIENCES = ("caregiver", "women")
# 講到這些＝他正在照顧人（照顧者身分推不出來、只能從他怎麼講聽出來）
CAREGIVING_WORDS = ("照顧", "顧我媽", "顧我爸", "顧他", "看護", "臥床", "失智",
                    "長照", "喘息", "帶他去看", "我媽", "我爸", "婆婆", "公公",
                    "阿嬤", "阿公", "奶奶", "爺爺", "外婆", "外公")
URGENCY_WORDS = ("受不了", "撐不住", "快瘋了", "好幾天沒睡", "三天沒睡", "整晚沒睡", "很嚴重", "急",
                 # 2026-07-29 搬痛風題時補：正在發作＝現在就痛，「一週檔」的建議
                 # 排在「今晚先避開這幾樣」前面完全答非所問
                 "發作", "又痛起來", "腫起來", "痛到")
# 排斥藥丸的說法
PILL_AVERSE_WORDS = ("不想吃藥", "不要吃藥", "不敢吃藥", "藥吃太多", "不想再吃", "怕副作用")
# 偏好中醫
TCM_WORDS = ("中藥", "中醫", "轉骨", "四物", "藥膳")
# 「他問的是吃什麼」（2026-08-12）：不是問原因、不是問嚴不嚴重，是問**要拿什麼進嘴巴**。
# 這種問法要優先端得出東西的卡，不能只回「慢慢來最穩」「食物優先」這類原則。
WHAT_TO_TAKE_WORDS = ("吃什麼", "喝什麼", "買什麼", "補什麼", "吃啥", "有什麼可以吃",
                      "有沒有什麼可以", "保健品", "保健食品", "健康食品", "營養品",
                      "食療", "食補", "怎麼吃", "飲食", "什麼比較容易消", "菜單")
# 「可以吃嗎」這種問法**不算**問吃什麼——他多半是在問某樣特定的東西能不能碰
# （「餵母奶感冒可以吃藥嗎」「我在吃抗凝血的藥，可以吃當歸嗎」）。那種問法由
# askedFor 負責把該回答的那張叫出來；把它算成「問吃什麼」會讓食補卡蓋掉交互作用警告。
# 2026-08-12 第一版就是這樣咬到孕期題與中醫題，兩支守門當場抓出來。
MEDICATION_WORDS = ("藥", "藥物", "處方", "膠囊", "藥丸")
# 「講得出東西」＝點得出食物、成分或份量，不是只講方向。
# 這串是給挑選用的粗篩，不是內容規範；寫得寬一點沒關係，寧可多浮上來一張真的有用的。
NAMES_SOMETHING_CONCRETE = re.compile(
    r"[一二三四五六七八九十兩半0-9]+\s*(份|杯|顆|克|毫克|公克|茶匙|湯匙|分鐘|次|c\.?c\.?|毫升)|"
    r"洋車前子|燕麥|糙米|地瓜|豆漿|豆腐|優格|優酪|牛奶|雞胸|雞蛋|魚|鮭魚|鯖魚|堅果|芝麻|"
    r"深綠|青菜|蔬菜|水果|香蕉|奇異果|黑咖啡|無糖茶|綠茶|開水|喝水|燙過|汆燙|"
    r"魚油|鈣|維生素|維他命|鎂|鐵|鋅|葉酸|乳清|蛋白粉|益生菌|B\s?群|薑黃|紅麴|葡萄糖胺|"
    r"膠原|花青素|葉黃素|omega|Omega")


# 「講得出動作」＝句子裡有做得到的事，不只是說明這是什麼病。
DOES_SOMETHING = re.compile(
    r"每天|每餐|每週|一週|睡前|起床後?|先吃|改成|換成|加一份|減一|走路|快走|練|抬|站|坐直|"
    r"泡|按|記錄|量血壓|量一下|放在|拿掉|戴|擦|洗|曬|問藥師|帶去|試試|先從")


def _asks_what_to_take(text):
    t = text or ""
    if any(w in t for w in MEDICATION_WORDS):
        return False          # 問的是藥能不能吃，不是問吃什麼——別讓食補卡蓋掉警告
    return any(w in t for w in WHAT_TO_TAKE_WORDS)
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


_CJK = re.compile(r"[぀-ヿ㐀-鿿豈-﫿]")
_WORD_START = {}


def mentions(needle, text):
    """這句話裡有沒有提到這個詞。**全庫唯一的比對規則**。

    中文日文用純包含比對（本來就沒有詞的空隙，「睡不好」要能在句中任何位置命中）。
    拉丁語系兩件事都要做：**忽略大小寫**（語音辨識會寫成「Plavix」「Ventolín」，
    我們的字典是小寫）、而且**從詞頭開始比**（西班牙版回報「tos（咳嗽）」被
    「hidra*tos*（醣類）」叫起來）。只綁詞頭、不綁詞尾，是為了留住詞根：
    「aliment」還是要能命中「alimentación」。

    2026-07-31：這支原本只長在觸發字那一邊，**點名字（askedFor）那一邊是生的**——
    大寫就比不到。剛好新的「他點名了才回答」機制整個靠 askedFor，出國就會失靈。
    兩邊改用同一支，以後不會再走鐘。
    """
    k = (needle or "").lower()
    if not k:
        return False
    hay = (text or "").lower()
    if _CJK.search(k) or not k[0].isalpha():
        return k in hay
    rx = _WORD_START.get(k)
    if rx is None:
        rx = _WORD_START[k] = re.compile(r"\b" + re.escape(k))
    return rx.search(hay) is not None


def _named(sol, user_text):
    """他自己把這樣東西講出來了嗎。"""
    return any(mentions(w, user_text) for w in (sol.get("askedFor") or []))


def _blocked_by_safety(sol, flags, user_text):
    """安全過濾（硬性、排序翻不了）。回傳 True＝整個方案剔除。"""
    if sol.get("blocked"):
        # blocked＝我們絕不主動端出去的（開刀、調藥、減肥針、通血路點滴）。
        # 但這批寫的每一張 blocked 卡，內容其實都是「他問了要怎麼答」的誠實回話。
        # 一律剔除的結果是：他指名問「通血路的點滴有效嗎」，我們寫好的答案永遠不出場，
        # 她只能拿通用模型自己接——最該講究措辭的那一句反而沒有稿。
        # 所以：他自己點名了就端出去，沒點名就繼續不主動提。
        # （2026-07-31 建慢性病三題時抓到；7 月的褪黑激素那次是同一個病，
        #   當時把單張卡改成不 blocked 繞過去，這次改成通則。）
        return not _named(sol, user_text)
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
    sol_aud = sol.get("audience") or []
    if auds and sol_aud:
        if any(a in sol_aud for a in auds):
            # 專屬度：只針對這種處境設計的方案（例照顧者的「把睡眠切兩段」），
            # 要贏過人人適用的通用方案——不然照顧者拿到的主推會是「睡前手機放遠」，
            # 那對「我媽三點要起來」根本答非所問。
            score += 2.0 + (2.0 if len(sol_aud) <= 2 else 0.0)
        elif any(a in AGE_AUDIENCES for a in sol_aud):
            score -= 3.0          # 這是寫給別的齡層的
        elif "caregiver" in sol_aud and "caregiver" not in auds:
            # 照顧者身分聽得出來（他會講「我媽…」「顧到…」），所以「沒聽到」是有意義的：
            # 16 歲說睡不好，不該拿到「喘息服務補眠」。
            score -= 3.0
        # 剩下的是 women 這種純身體標籤——我們根本無從得知，不知道就不罰。

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

    # 他問的是「吃什麼」，就要真的講得出東西（2026-08-12 · Edward 拿 ChatGPT 的
    # 內臟脂肪回答當對照後）：18 句真人問法實測，7 句我們一樣具體的東西都端不出來——
    # 但拆開看，多數題目**卡片其實寫了、只是沒被挑出來**（腎臟題的「菜先燙過」、
    # 血脂題的「燕麥與可溶性纖維」都在庫裡，卻輸給了原則型的卡）。
    # 他問「吃什麼」時，講得出食物與份量的那幾張本來就該排前面。
    if _asks_what_to_take(text):
        if sol.get("solutionType") == "食補":
            # 只要 +2：目的是把講得出東西的那張**擠進三張裡**，不是讓它永遠當第一句。
            # 第一版給 +3，膝蓋題的蛋白質卡就壓過了實證更明確的肌力訓練——守門抓到。
            score += 2.0
        elif sol.get("solutionType") == "保健品":
            score += 1.5          # 排斥藥丸的人前面已經扣 6 分，這裡蓋不過去
        if NAMES_SOMETHING_CONCRETE.search(sol.get("say") or ""):
            # 型別不是食補、但內容真的講得出東西的也算（例：腎臟題「蔬菜先燙過再炒」）
            score += 1.5

    # 他點名問的東西要浮上來（2026-07-29 中醫題抓到、已成通則）：
    # 「我在吃抗凝血的藥，可以吃當歸嗎」——最該回答的那條卻因為分數不夠沒被選中，
    # 端出去的是三句通用的話。askedFor 原本只用來解除陪襯層降級，不夠；
    # 他指名問的，本來就該排到前面，不然等於答非所問。
    if any(mentions(w, text) for w in (sol.get("askedFor") or [])):
        score += 5.0

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


def pick(topic_id, user_text="", profile=None, hour=None, limit=MAX_SOLUTIONS, locale=None):
    """挑方案。回傳 dict：{"solutions": [...], "referral": {...}|None, "reframe": str|None, "urgent": bool}"""
    topic = TOPICS.get(topic_id)
    if not topic:
        return {"solutions": [], "referral": None, "reframe": None, "urgent": False}

    flags = _profile_flags(profile)
    urgent = _is_urgent(user_text, hour)
    proxy = _asking_for_someone_else(user_text)
    pool = topic.get("solutions") or []
    # 一國一庫：非中文語系先把說法換成那一國的（缺說法的方案剔除；
    # 轉介卡沒翻＝整題回空——安全話術絕不退回中文）。打分欄位語言中立、照常用。
    if locale:
        pool = _i18n.localized_solutions(topic_id, pool, locale)
        if not pool:
            return {"solutions": [], "referral": None, "reframe": None,
                    "urgent": False, "proxy": False, "related": None}
    # 代問時只留「講給家長聽」的版本；本人問只留「講給本人聽」的版本；沒標的兩邊都給。
    pool = [s for s in pool if s.get("forWhom") in (None, "parent" if proxy else "self")]
    # 照顧者替家人問時，方案是要給**被照顧的那位**用的（2026-07-29 骨鬆題抓到）：
    # 「我媽有骨鬆，怕她跌倒」原本只比對 caregiver，結果專為長輩寫的「練肌力跟平衡」
    # 拿不到專屬度加分、被通用建議擠掉——防跌實證最明確的那條反而沒端出去。
    # 兩個齡層都算數：照顧者自己的方案（喘息、把睡眠切兩段）照樣浮得上來。
    # 照顧者身分推不出來、只能聽出來：他講「我媽…」「顧到…」就是正在照顧人。
    # （原本只在 profile 已經是 caregiver 時才成立——但那個值正式機從來不會有。）
    text_now = user_text or ""
    caregiving = proxy or any(w in text_now for w in CAREGIVING_WORDS)
    if caregiving and "caregiver" not in flags["audiences"]:
        flags["audiences"] = list(flags["audiences"]) + ["caregiver"]
    if proxy and "elder" not in flags["audiences"]:
        # 代問的對象在這個產品裡絕大多數是長輩——方案要挑給被照顧的那位
        flags["audiences"] = list(flags["audiences"]) + ["elder"]

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
        return not _named(s, user_text)

    # leadWith＝陪襯層的反面（2026-07-29 加貧血題時抓到）：有些方案是「門檻」——
    # 不先做這件事，後面每一條都失去意義。貧血題的「先驗血、別盲補」就是，
    # 它靠分數永遠擠不進前三（食補又慢養又省力，分數天生高），可是把補鐵法
    # 講在驗血前面，等於教人盲補——鐵補過頭是會傷身體的。
    ranked = sorted(
        (s for s in pool if not _blocked_by_safety(s, flags, user_text)),
        key=lambda s: (not s.get("leadWith"), _demoted(s),
                       -_score(s, flags, urgent, user_text)),
    )
    # 類型多樣性：三個建議全是「行為調整」等於同一招講三次，長輩也記不住差別。
    # 挑的時候同類型最多兩個，把位置留給食補／運動／保健品這些不同路數的方案。
    picked, type_count = [], {}

    def _take(candidates, respect_type_cap):
        for s in candidates:
            if len(picked) >= limit:
                return
            if s in picked:
                continue
            t = s.get("solutionType")
            if respect_type_cap and type_count.get(t, 0) >= 2:
                continue
            picked.append(s)
            type_count[t] = type_count.get(t, 0) + 1

    blocked = [s for s in ranked if s.get("blocked")]        # 他點名了才會在這裡
    normal = [s for s in ranked if not s.get("blocked") and not _demoted(s)]
    demoted = [s for s in ranked if not s.get("blocked") and _demoted(s)]
    _take(normal, True)      # 先照多樣性挑正規方案
    _take(normal, False)     # 正規的還有就補滿——多樣性只是偏好，不該讓位給陪襯層
    _take(demoted, True)     # 真的不夠了才動陪襯層
    _take(demoted, False)

    # 他點名問的「不能建議」那類：一定要講到（不然等於問了不答），但不放第一句。
    # 「我感冒了，可以吃家裡的感冒藥嗎」——第一句該是「先問藥師會不會跟你的藥打架」
    # 這種做得到的事，「我不建議成藥」擺第二句才不會像在打發他。
    if blocked and limit >= 2:
        b = blocked[0]
        if b in picked:
            if picked.index(b) == 0:
                picked.insert(1, picked.pop(0))
        else:
            picked.insert(min(1, len(picked)), b)
            del picked[limit:]

    # 轉介卡：紅旗類永遠獨立帶著，不跟一般方案搶名額
    referral = next((s for s in pool if s.get("riskLevel") == "L5"), None)

    # 重新定義問題（例：照顧者不是失眠、是沒得睡）
    reframe = None
    for r in topic.get("reframe") or []:
        if r.get("forWhom") == "parent" and proxy:
            reframe = r["say"]
            break
        # 同一個病：這裡原本也看 flags["audience"] == "caregiver"，但正式機的齡層
        # 只可能是 teen/worker/elder——所以「你不是睡不著，是你根本沒得睡」這句
        # 從來沒有對任何一個真的照顧者講過。改看聽出來的處境。
        if r.get("forWhom") in (None, "self") and not proxy                 and "caregiver" in (flags.get("audiences") or [])                 and "照顧者" in r.get("when", ""):
            reframe = r["say"]
            break

    # 跨題連結（2026-07-29）：睡不好、血壓飄、心情悶常常是同一件事的不同面向。
    # 只在他這一輪自己也提到那件事時才連——不硬拉、不擴大話題。
    related = None
    for r in topic.get("relatedTopics") or []:
        cue = health_kb_keywords(r.get("topicId"))
        if cue and any(mentions(k, user_text) for k in cue):
            related = r.get("say")
            break

    return {"solutions": picked, "referral": referral, "reframe": reframe,
            "urgent": urgent, "proxy": proxy, "related": related}


def render(topic_id, user_text="", profile=None, hour=None, locale=None):
    """組成注入給模型的那段話。沒挑到東西就回空字串（不佔說明書）。"""
    res = pick(topic_id, user_text, profile, hour, locale=locale)
    if not res["solutions"]:
        return ""
    parts = []
    if res["reframe"]:
        parts.append("【先重新定義問題】" + res["reframe"])
    rank = 0
    for s in res["solutions"]:
        if s.get("blocked"):
            # 他自己點名問的「不能建議」那類（開刀、調藥、瘦瘦針、通血路點滴）。
            # 這不是推薦，所以不掛主推／備援的頭銜，也不套保健品那段上限話術
            # ——那會把一句「這個沒有用」講成在推薦保健品。
            parts.append("【他自己問到這個·照這個說法誠實回】" + s["say"])
            continue
        tag = "主推" if rank == 0 else f"備援{rank}"
        rank += 1
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
