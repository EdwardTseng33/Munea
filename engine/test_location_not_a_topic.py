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


def test_only_search_when_he_asks():
    inst = instructions_with_location()
    check("明令只有他自己開口問才查", "只有他自己開口問" in inst)
    check("要先問清楚是哪一家、不亂推", "哪一家" in inst)
    check("有點出長輩是要「確認」不是要「發現」", "確認" in inst and "發現" in inst)


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


# ---- 二、語音端：查詢工具的閘門 ----
def test_voice_tool_gate():
    import live_voice_server as lv
    inst = lv.system_instruction(char="寧寧", name="寧寧", location="臺北市大安區")
    check("查詢工具：要他真的問才查", "他自己開口問" in inst)
    check("查詢工具：明令她不要自己把話題帶過去再查", "不要把話題帶到那邊" in inst)
    check("查詢工具：明講「聊到」不算、要他真的問", "「聊到」不算" in inst)
    check("查詢工具：有講代價（查一次好幾秒、他在乾等）", "乾等" in inst)
    check("查詢工具：舊的鬆閘門不得復活",
          "聊到餐廳店家、景點旅遊（例如日本哪裡好玩、桃園有什麼好吃的）、" not in inst)


def main():
    test_location_is_background_not_topic()
    test_only_search_when_he_asks()
    test_no_unconditional_restaurant_nudge()
    test_no_location_no_line()
    test_location_still_reaches_her()
    test_voice_tool_gate()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 所在地防線全過（背景知識不是話題、他問才查、不再每輪推餐廳）")


if __name__ == "__main__":
    main()
