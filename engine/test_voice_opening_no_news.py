"""開場不准編新聞 · 守門測試（2026-08-01）。

Edward 7/31 深夜真機：她接起來第一句就說「你看新聞了嗎？這次奧運台灣選手表現超有精神」——
當天備好的資料裡一個奧運的字都沒有。查下來不是模型突然變壞，是**開場設計逼她編**：

  舊版開場路線第 2、4 條叫她「挑一個具體、輕鬆的小切口」「直接分享一句輕巧的話」，
  卻沒說材料從哪來；開場又要求短、要有內容、要立刻開口。手上沒東西 → 生一個聽起來
  很合理的。而「新聞只能講備好的」那條規則躺在一萬七千多字說明書的另一端。

這支測試守三件事（誰把它們改回去，這裡就會紅）：
  ① 每一條開場路線都帶著「開場不准提新聞時事」的鐵律
  ② 有興趣主題時只准「用問的」，不准講內容
  ③ 遞給她的今日資料不准出現內部叫法（簡報），而且要明講不准提來源
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import localization  # noqa: E402
import server  # noqa: E402


def test_every_opening_route_forbids_news():
    """輪到哪一條路線都一樣：開場那句不准提新聞、比賽、活動。"""
    for idx in range(8):
        text = localization.voice_opening_instruction(
            familiarity=idx, topics=["種花", "老歌"], location="臺北市")
        assert "開場這一句絕對不准提新聞" in text, f"route {idx} 少了開場鐵律"
        assert "只講一句招呼" in text, f"route {idx} 沒給「編不出來就只招呼」這條退路"


def test_every_route_greets_by_time_of_day():
    """Edward 8/1 拍板：開頭只要打招呼——每條路線都要照當下時間問候（早安／午安／晚安）。"""
    for idx in range(8):
        text = localization.voice_opening_instruction(familiarity=idx)
        assert ("照現在的時間自然問候" in text) or ("照時間問候" in text), f"route {idx} 沒有時段問候"


def test_interests_are_not_opening_material():
    """興趣只當「他先聊到才接」的方向，不准拿來當開場話題（8/1 拍板）。"""
    text = localization.voice_opening_instruction(familiarity=1, topics=["種花"])
    assert "種花" in text
    assert "不是開場素材" in text


def test_memory_route_only_uses_what_is_actually_written():
    """用記憶開場可以，但只准用上面真的寫著的事；沒有就退回純問候。"""
    text = localization.voice_opening_instruction(familiarity=2)
    assert "上面真的寫著" in text
    assert "上面沒寫的一律不准提" in text


def test_warmth_route_only_allows_what_is_true_right_now():
    """給情緒價值可以，但只准用此刻成立的話。

    「今天想到你」聽起來很暖，卻是在宣稱她這段時間有在想他——她沒有兩通之間的日子，
    那跟我們正在修的編新聞是同一家族（憑空生一個聽起來合理的內容）。
    """
    text = localization.voice_opening_instruction(familiarity=1)
    assert "此刻成立" in text
    assert "今天想到你" in text and "不准說" in text, "要明列這句是禁例，不是示範"
    assert "沒有兩通之間的日子" in text


def test_daily_facts_never_leak_the_internal_name():
    """遞給她的今日資料：不准出現「今日簡報」，而且要明講不准告訴長輩來源。"""
    seg = server.reply_context_instruction({
        "dailyBriefing": {
            "briefingLine": "臺北市今天26到35度、降雨機率50%",
            "tomorrowLine": "明天毛毛雨、26到35度",
            "careHints": ["天氣很熱，提醒多喝水"],
        },
    })
    assert "今日簡報" not in seg, "內部叫法漏到說明書裡了——她會說「我今天的簡報說…」"
    assert "絕對不要提起這些是哪裡來的" in seg
    assert "26到35度" in seg, "資料本身還是要給她"


def test_interests_line_never_tells_her_to_open_with_current_events():
    """最直接的推手：舊版興趣那段寫「開場可以搭今日簡報或最近的真時事更好」。

    她手上根本沒有「最近的時事」——那是要現查的。這行等於發一張編造許可證。
    """
    seg = server.reply_context_instruction({"interests": ["種花", "老歌"]})
    assert "最近的真時事" not in seg, "又把「用時事開場」寫回去了"
    assert "不准自己補上時事" in seg


def test_chat_topics_are_never_offered_as_an_opening():
    """萬一閒聊素材被打開，也只准他自己聊到才接，開場永遠不准用。"""
    seg = server.reply_context_instruction({
        "dailyBriefing": {
            "briefingLine": "臺北市今天26到35度",
            "topics": [{"line": "最近有個關懷長輩的暖新聞"}],
        },
    })
    assert "開場絕對不要用" in seg
    assert "不要當新聞報" in seg


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            passed += 1
            print(f"  PASS {name}")
    print(f"開場不編新聞守門測試 {passed} 項全過")
