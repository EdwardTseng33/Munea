# -*- coding: utf-8 -*-
"""所在地＝背景知識、不是話題（2026-07-17 · Edward 真機回報後立）

Edward 原話：「他對於用戶所在地點的聊天權重變得有點太高了，好比一直問在我設定的區域
晃晃了嗎、有什麼好餐廳嗎之類的。」

根因（正式機紀錄鐵證，非推測）：她**每一輪都真的去查在地資訊**——
  node.tool_call name=search_current_information
  node.lookup_requested has_location=True
  node.lookup_done latency_ms=9412      ← 一次 9 秒
  lookup_model_failover err=TimeoutError / lookup returned no grounded sources
長輩聽到的就是：卡、一直「我幫你查一下」、一直被問餐廳、最後「系統怪怪的」。

兩個推力：
  一、說明書那段所在地，是整份裡唯一一段「話題操作指南」（四行教她怎麼推薦餐廳），
      還無條件補「現在是X時段、推薦餐廳就挑這個時段吃得到的」＝每輪提醒她推餐廳。
  二、查詢工具寫「**聊到**餐廳店家…直接呼叫工具」——「聊到」太鬆，
      **她自己把話題帶過去也算聊到**，於是自己起頭、自己去查、讓長輩等 9 秒。

產品判斷（Edward 拍板）：幫長輩推薦餐廳多半是假需求——他在那裡住了幾十年、比 AI 熟；
長輩問在地問題多半要「確認」（那家店還開嗎）不是要「發現」。
所在地真正該做的事只有三件：聽懂他講的地名、把天氣講對、知道他要去哪。

跑法：python engine/test_location_not_a_topic.py（純文字檢查、不需網路/鑰匙）
"""
import os
import sys

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def instructions_with_location(loc="臺北市大安區"):
    ctx = server.build_reply_context([], "寧寧", {"displayName": "寧寧", "location": loc})
    return server.reply_context_instruction(ctx)


# ---- 一、所在地是背景知識、不是話題 ----
def test_location_is_background_not_topic():
    inst = instructions_with_location()
    check("有把所在地講成背景知識", "背景知識" in inst)
    check("明令不要拿它當話題起頭", "不要拿它當話題起頭" in inst)
    check("點名禁止「最近有去哪走走嗎」", "最近有去哪走走嗎" in inst)
    check("點名禁止「你們那邊有什麼好吃的」", "你們那邊有什麼好吃的" in inst)
    check("明令不要主動推薦餐廳景點", "不要主動推薦餐廳或景點" in inst)
    check("有講為什麼（長輩比她熟、行動不便、有固定的店）",
          "住了幾十年" in inst and "行動不便" in inst)
    check("有接回既有禁語原則（跟「出去走走」同一個錯）", "出去走走" in inst)


def test_he_asks_she_says_she_doesnt_know():
    """他問附近的事 → 她查不了 → 老實說不知道、把話丟回給他（不是硬掰一個店名）。"""
    inst = instructions_with_location()
    check("他問了 → 明令老實說查不了", "你查不了，就老實說" in inst)
    check("給了人話的說法（不知道欸、你要不要打去問問看）",
          "這我就不知道了欸" in inst and "打去問問看" in inst)
    check("有點出長輩是要「確認」不是要「發現」", "確認" in inst and "發現" in inst)
    check("引導他自己講（他比你熟）", "你都去哪一家" in inst)


def test_no_unconditional_restaurant_nudge():
    """舊版每輪補一句「現在是X時段、推薦餐廳就挑這個時段吃得到的」——這句是元凶之一，必須消失。"""
    inst = instructions_with_location()
    check("不再有無條件的時段推餐廳提醒", "推薦餐廳就挑這個時段" not in inst)
    check("整份說明書不再出現「再推薦」這種主動推銷語", "真實存在的店家/景點再推薦" not in inst)


def test_no_location_no_line():
    """沒設所在地 → 整段不出現（不要憑空生一個地方出來）。"""
    inst = server.reply_context_instruction(
        server.build_reply_context([], "寧寧", {"displayName": "寧寧"}))
    check("沒設所在地 → 不出現所在地那段", "背景知識、不是話題" not in inst)
    check("沒設所在地 → 不會編一個地名", "大安區" not in inst)


def test_location_still_reaches_her():
    """對照組：地點本身還是要讓她知道（不然天氣、聽懂地名都做不到）——不是把它拔掉。"""
    inst = instructions_with_location("高雄市左營區")
    check("對照組：她仍然知道他住哪（證明不是整段拔掉）", "高雄市左營區" in inst)
    check("對照組：仍講明地點是拿來把天氣講對的", "天氣講對" in inst)


# ---- 二、通話中不再即時查（2026-07-17 Edward 拍板拿掉）----
def test_live_lookup_off_by_default():
    """預設關：她手上根本沒有那個工具，就不會叫、也就不會播「我幫你查一下」、不會卡 9 秒。"""
    import live_voice_server as lv
    os.environ.pop("MUNEA_VOICE_LIVE_LOOKUP", None)
    check("預設就是關的", lv.live_lookup_enabled() is False)

    cfg = lv.live_config(char="寧寧", name="寧寧", location="臺北市大安區")
    names = [f.name for t in (cfg.tools or []) for f in (t.function_declarations or [])]
    check("她手上沒有即時查詢這個工具", "search_current_information" not in names)


def test_she_knows_she_cannot_search():
    """她必須知道自己查不了——不然會亂承諾「我幫你查一下」然後查不了、長輩一直等。"""
    import live_voice_server as lv
    os.environ.pop("MUNEA_VOICE_LIVE_LOOKUP", None)
    inst = lv.system_instruction(char="寧寧", name="寧寧", location="臺北市大安區")

    check("明講她沒辦法上網查", "你沒有辦法上網查東西" in inst)
    check("**點名禁止**講「我幫你查一下」", "我幫你查一下" in inst and "絕對不要說" in inst)
    check("禁止其他變體（我查查看／我找找看／等我一下）",
          all(w in inst for w in ["我查查看", "我找找看", "等我一下"]))
    check("有講為什麼禁（講了就是空頭支票、長輩會一直等）", "空頭支票" in inst)
    check("告訴她即時資訊唯一的來源＝今日簡報", "今日簡報" in inst)
    check("簡報沒有的 → 老實說不知道（給了人話說法）", "這我就不知道了欸" in inst)
    check("寧可不知道也不准憑印象編", "絕對不可以憑印象編" in inst)
    check("接回產品原則：那是客服、不是朋友", "那是客服" in inst)
    check("她看不到舊的工具說明（不會以為自己有工具）",
          "search_current_information" not in inst)


def test_lookup_can_be_switched_back():
    """對照組：一個字就能退回舊行為（程式沒被砍掉、Edward 覺得她太笨隨時可開）。"""
    import importlib
    import live_voice_server as lv
    os.environ["MUNEA_VOICE_LIVE_LOOKUP"] = "1"
    try:
        importlib.reload(lv)
        check("對照組：開關打開 → 工具回來", lv.live_lookup_enabled() is True)
        cfg = lv.live_config(char="寧寧", name="寧寧")
        names = [f.name for t in (cfg.tools or []) for f in (t.function_declarations or [])]
        check("對照組：工具真的回到她手上（證明不是砍掉、是關掉）",
              "search_current_information" in names)
        inst = lv.system_instruction(char="寧寧", name="寧寧")
        check("對照組：說明書也跟著回舊版", "你有 search_current_information" in inst)
    finally:
        os.environ.pop("MUNEA_VOICE_LIVE_LOOKUP", None)
        importlib.reload(lv)


def test_core_no_longer_claims_a_search_tool():
    """共同底盤（文字聊天也吃這份）不得再宣稱她有查詢工具——
    文字聊天那條路**從來就沒有給過工具**，那句話一直是假的。"""
    import chat_engine as ce
    check("共同底盤不再說「用你的即時查詢工具」", "用你的即時查詢工具" not in ce.CORE)
    check("共同底盤明講她不會自己上網查", "你不會自己上網查" in ce.CORE)
    check("共同底盤指向今日簡報當唯一來源", "今日簡報" in ce.CORE)
    check("捏造紅線還在（沒被我改掉）", "絕不自己捏造颱風、災情、數字或事件" in ce.CORE)


def main():
    test_location_is_background_not_topic()
    test_he_asks_she_says_she_doesnt_know()
    test_no_unconditional_restaurant_nudge()
    test_no_location_no_line()
    test_location_still_reaches_her()
    test_live_lookup_off_by_default()
    test_she_knows_she_cannot_search()
    test_lookup_can_be_switched_back()
    test_core_no_longer_claims_a_search_tool()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 所在地防線全過（背景知識不是話題、他問才查、不再每輪推餐廳）")


if __name__ == "__main__":
    main()
