#!/usr/bin/env python3
"""子行程 worker：給一題黃金集案例，組出跟正式語音線同一套 system instruction，
呼叫真模型生一句寧寧的回覆，回傳 JSON 到 stdout。

為什麼要獨立子行程（不是同一個 process 迴圈跑 26 題）：
server.py / chat_engine.py 的資料檔路徑（MEMORY_ITEMS_PATH、LIVING_PROFILE_PATH…）
是 import 當下讀 env var 算出來的模組常數，同一個 process 裡先 import 過一次以後
再改 env var 沒有用（重進另一題的 fixture 會被前一題污染）。所以每題都開一個全新
python 行程，先設好 env、再 import，天生乾淨隔離，也跟這個 repo 其他 test_*.py
「一支腳本一個 process」的慣例一致，不引入新的資料層 hack。

輸入（stdin，一行 JSON）——兩種模式：
  舊模式（golden_set 單輪，語音線 system_instruction）：
    {"id": "...", "character": "寧寧", "userLine": "...",
     "fixture": {"memory_items": [...], "living_profile": {...}} | null,
     "tmpdir": "<這題專用的暫存資料夾，呼叫端已建好>"}
  新模式（聊天品質多輪，正式文字線 server.reply_conv，2026-07-25 新增）：
    上面欄位皆同，但多帶 "history"（本輪之前的對話，[{"role":"user"/"model","text":"..."}...]，
    第一輪可為空陣列）與 "newUserLine"（這一輪使用者說的話，取代 userLine）——
    只要 case 裡有 "history" 這個 key（即使是空陣列）就會走新模式。

輸出（stdout，一行 JSON）：
  {"ok": true, "reply": "...", "modelUsed": "gemini-2.5-flash"}
  {"ok": false, "error": "..."}
"""
import json
import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    # 2026-07-24 教訓（PR #240）：Windows 跑者 stdout 預設 cp1252，中文字會
    # UnicodeEncodeError；這支腳本本機/CI 都可能被redirect，強制 UTF-8 保險。
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))


def _injected_system_facts(context):
    """把正式線 build_reply_context() 真的注入給模型的『系統事實』攤平回傳，
    讓評審端（judge.py 鐵律6／dimension_judge.py 誠實度）拿到跟模型一模一樣的
    背景，才不會把『模型照系統給的真時間講出今天日期』誤判成編造。

    2026-07-25（評測骨架修繕，蘇菲）：對應第一輪基準第八節缺口——鐵律評審
    只餵 persona 記憶側寫、沒餵系統即時 context（時間/地點/今日簡報），S03/S06/
    S13 講出系統給的時間被誤殺。這裡回傳的三塊剛好對上正式線 reply_context_
    instruction() 注入的 time_line／location_line／brief_line。"""
    context = context or {}
    now = context.get("now") or {}
    location = str(context.get("location") or "").strip()
    briefing_facts = []
    brief = context.get("dailyBriefing") or {}
    if brief.get("briefingLine"):
        briefing_facts.append(str(brief["briefingLine"]))
    if brief.get("tomorrowLine"):
        briefing_facts.append("明天預告：" + str(brief["tomorrowLine"]))
    for hint in brief.get("careHints") or []:
        briefing_facts.append(str(hint))
    for sched in brief.get("scheduleToday") or []:
        briefing_facts.append("今天的重要日子：" + str(sched))
    for t in brief.get("topics") or []:
        if isinstance(t, dict) and t.get("line"):
            briefing_facts.append(str(t["line"]))
    if not briefing_facts and brief.get("newsLine"):  # 相容舊 snapshot
        briefing_facts.append(str(brief["newsLine"]))
    return {
        "now": {k: now.get(k) for k in ("date", "weekday", "time", "period") if now.get(k)},
        "location": location,
        "dailyBriefing": briefing_facts,
    }


def _set_isolated_paths(tmpdir, person_id):
    # 一律指到這題專屬的暫存資料夾，絕不動到 engine/ 底下真正的資料檔。
    os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
    os.environ["MUNEA_SUPABASE_PERSON_ID"] = person_id
    for key, filename in (
        ("MUNEA_MEMORY_ITEMS_PATH", "memory_items.json"),
        ("MUNEA_LIVING_PROFILE_PATH", "living_profile.json"),
        ("MUNEA_USER_PROFILE_PATH", "user_profile.json"),
        ("MUNEA_PERCEPTION_SNAPSHOTS_PATH", "perception_snapshots.json"),
        ("MUNEA_RELATIONSHIP_STATES_PATH", "relationship_states.json"),
        ("MUNEA_CONVERSATION_SUMMARIES_PATH", "conversation_summaries.json"),
        ("MUNEA_FAMILY_STATE_STORE_PATH", "family_state_store.json"),
        ("MUNEA_APP_PROFILE_STORE_PATH", "app_profile_store.json"),
        # 2026-07-29：個人資料卡也要隔離——正式線是從這裡的出生年推齡層的，
        # 沒有這個檔，考卷永遠驗不到「同一句話對不同齡層答案不同」。
        ("MUNEA_PERSON_PROFILE_PATH", "person_profile.json"),
    ):
        os.environ[key] = os.path.join(tmpdir, filename)


def main():
    case = json.loads(sys.stdin.readline())
    person_id = f"eval-{case['id']}"
    _set_isolated_paths(case["tmpdir"], person_id)

    sys.path.insert(0, os.path.join(HERE, os.pardir))  # engine/ 目錄

    import server
    import live_voice_server as lv

    fixture = case.get("fixture") or {}
    if fixture.get("memory_items"):
        server.save_memory_items(fixture["memory_items"])
    if fixture.get("person_profile"):
        server.save_person_profile(fixture["person_profile"])
    if fixture.get("living_profile"):
        profile = dict(fixture["living_profile"])
        profile["personId"] = person_id
        profile.setdefault("updatedAt", "2026-07-01T00:00:00+08:00")
        server.save_living_profile(profile)

    # 模擬「這通電話已驗證是這個人」——正式路徑是 auth middleware 設的，
    # 這裡直接設同一個 contextvar，不繞過任何邏輯、只是跳過真的登入。
    server.REQUEST_DATA_IDENTITY.set({"personId": person_id})

    # 2026-07-25（聊天品質多輪劇本，卡西法）：mode="conv" 是多輪文字通道路徑，
    # 直接借正式文字線的 server.reply_conv()（跟 App 文字聊天走同一支函式），
    # 而不是 lv.system_instruction() 那條（那是語音線單輪路徑，golden_set 用）。
    # 兩條路徑並存、互不影響：golden_set_v1.json 沒有 "history" 欄位，只會走
    # 下面舊的單輪分支；聊天品質劇本庫每一輪都帶 "history"，走這個新分支。
    if "history" in case:
        history = list(case.get("history") or [])
        history.append({"role": "user", "text": case["newUserLine"]})
        # 2026-07-31 考卷分國：劇本帶哪一國，這通就用那一國的人設說明書與安全規則。
        # 沒帶＝繁中（既有 30 題劇本一律沒有這個欄位，行為完全不變）。
        data = {"personId": person_id}
        if case.get("locale"):
            data["locale"] = case["locale"]
        try:
            context = server.build_reply_context(history, char=case.get("character") or "寧寧", data=data)
            reply_raw = server.reply_conv(history, char=case.get("character") or "寧寧", data=data, context=context)
            reply = server.localization.assistant_output_text(reply_raw, context.get("locale"))
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"reply_conv failed: {e}"}, ensure_ascii=False))
            return
        print(json.dumps({
            "ok": True, "reply": (reply or "").strip(),
            "modelUsed": "server.reply_conv (production text-line, gemini-2.5-flash 主/自動降級)",
            "systemContext": _injected_system_facts(context),
        }, ensure_ascii=False))
        return

    try:
        _profile = None
        if case.get("locale"):
            _profile = server.localization.voice_session_locale_profile(
                server.localization.build_locale_context({"conversationLocale": case["locale"],
                                                          "uiLocale": case["locale"]}))
        sys_instruction = lv.system_instruction(
            char=case.get("character") or "寧寧", locale_profile=_profile)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"system_instruction failed: {e}"}, ensure_ascii=False))
        return

    # B2 衛教（2026-07-24）：正式線會按用戶的話注入策展題庫（文字線在組說明書時、
    # 語音線在輪替空檔補提示）；評測比照正式線、用同一個模組同一份資料。
    import health_kb
    sys_instruction += health_kb.injection_for(case["userLine"])

    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(json.dumps({"ok": False, "error": "GEMINI_API_KEY missing"}, ensure_ascii=False))
        return

    client = genai.Client(api_key=api_key)
    last_err = ""
    for model in ("gemini-2.5-flash", "gemini-flash-latest"):
        try:
            r = client.models.generate_content(
                model=model,
                contents=case["userLine"],
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruction, temperature=0.7,
                ),
            )
            usage = getattr(r, "usage_metadata", None)
            total_tokens = getattr(usage, "total_token_count", None) if usage else None
            print(json.dumps({
                "ok": True, "reply": (r.text or "").strip(), "modelUsed": model,
                "systemInstructionChars": len(sys_instruction),
                "totalTokens": total_tokens,
            }, ensure_ascii=False))
            return
        except Exception as e:
            last_err = str(e)[:200]
    print(json.dumps({"ok": False, "error": f"generate_content failed: {last_err}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
