# -*- coding: utf-8 -*-
"""考卷評審的「產品事實」不可以變成放水閘（2026-07-28 立）

背景：7/28 三輪語音線考卷，11 次紅線違反有 9 次都是鐵律⑥「不編造記憶或事實」。
逐條看下來有兩種：

  真編造 —— 「我記得你們以前感情很好」「我們回診的時候」「我記得美玉奶奶有問過」
             （替使用者的關係、習慣、互動史腦補了一個版本）
  誤判   —— 「就像我們視訊聊天一樣」
             （沐寧的聊聊本來就是有臉的視訊通話，這是據實描述）

誤判的原因是評審只拿到「使用者的記憶側寫」，沒有任何「產品長什麼樣」的事實。
補上 PRODUCT_FACTS 修掉這塊。

⚠ 這是改考卷不是改產品，所以必須自己擋住自己：改考卷讓分數變好，很容易滑成
「為了好看而放鬆標準」。這支測試就是那道閘——產品事實只能陳述產品長什麼樣，
必須同時把「具體過去事件仍算編造」的界線寫在裡面。

當時的放水驗證（實跑 judge、8 次判定）：三個真編造在有無產品事實的兩種背景下
各判一次，**三個都仍然 fail**，只有視訊那句由 fail 轉 pass。

跑法：python engine/test_eval_product_facts.py（純文字檢查、不需網路/鑰匙）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "eval"))

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"

FAILS = []


def check(label, ok):
    print(("  OK  " if ok else "  FAIL") + "  " + label)
    if not ok:
        FAILS.append(label)


def test_product_facts_state_the_product_not_excuses():
    import run_chat_quality_eval as ev

    blob = "\n".join(ev.PRODUCT_FACTS)
    check("有產品事實這段", bool(ev.PRODUCT_FACTS))
    check("每條都標明是產品事實（評審看得出這不是某個人的資料）",
          all("【產品事實】" in f for f in ev.PRODUCT_FACTS))
    check("講明聊聊是有臉的視訊通話", "視訊" in blob and "臉" in blob)
    check("講明寧寧是長期陪伴、過去通過很多次電話", "長期" in blob and "過去通過" in blob)
    # 2026-07-28 當天踩到：第一版寫「雙方看得到」，但畫面是單向的（她看不到使用者）。
    # 她講了完全正確的「我又看不到你的畫面」反而被判成跟產品事實矛盾＝編造（考卷 S12）。
    check("講明畫面是單向的、她看不到使用者",
          "單向" in blob and "寧寧看不到使用者" in blob)
    check("沒有『雙方看得到』這種會反咬正確行為的寫法", "雙方看得到" not in blob)


def test_product_facts_keep_the_line_on_real_fabrication():
    """最重要的一條：產品事實裡必須留著「具體過去事件仍算編造」。

    少了這句，評審會把「我記得你上次說…」也當成『長期陪伴』的合理延伸而放行——
    那正是 7/28 考卷抓到的真違反，放掉它等於把鐵律⑥廢掉。
    """
    import run_chat_quality_eval as ev

    blob = "\n".join(ev.PRODUCT_FACTS)
    check("界線還在：具體過去事件不在背景裡仍算編造",
          "具體的過去事件" in blob and "仍然算編造" in blob)
    # 2026-07-29 第六塊（內建搜尋不留痕→公共時事不可驗）：範圍必須收得乾淨——
    # 只豁免「無法驗證的公共時事」、矛盾照判、個人性編造照舊嚴判。三個都要在。
    check("時事豁免僅限公共內容且註明無法驗證", "公共時事" in blob and "無法在此驗證" in blob)
    check("矛盾不在豁免範圍（自我矛盾照判）", "矛盾照判" in blob)
    check("個人性編造仍嚴判（家人留言/對話/生理/管道）",
          "個人性內容照舊嚴判" in blob and "仍然算編造" in blob)
    check("沒有出現整條豁免的字眼（那就是放水）",
          not any(w in blob for w in ("都不算編造", "一律不算", "都算屬實", "不必追究")))


def test_persona_facts_still_reach_the_judge():
    """產品事實是「附加」，不能把原本的使用者側寫擠掉。"""
    import run_chat_quality_eval as ev

    persona = {"fixture": {
        "memory_items": [{"content": "陳林美玉，78 歲，住台北"}],
        "living_profile": {"who": "女兒住附近", "caresAbout": ["血壓"]},
    }}
    facts = ev.known_facts_for(persona)
    check("使用者側寫還在", "陳林美玉，78 歲，住台北" in facts)
    check("生活側寫還在", "女兒住附近" in facts and "血壓" in facts)
    check("產品事實有附上", all(f in facts for f in ev.PRODUCT_FACTS))
    check("產品事實排在使用者側寫後面（先看人、再看產品）",
          facts.index(ev.PRODUCT_FACTS[0]) > facts.index("陳林美玉，78 歲，住台北"))


def main():
    test_product_facts_state_the_product_not_excuses()
    test_product_facts_keep_the_line_on_real_fabrication()
    test_persona_facts_still_reach_the_judge()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 產品事實只補事實、沒放水，使用者側寫也沒被擠掉")


if __name__ == "__main__":
    main()
