#!/usr/bin/env python3
"""子行程 worker：把一整條劇本**真的當成一通電話**打過語音腦（Gemini Live），
回傳她每一輪講出來的字幕與反應時間。

為什麼要有這支（2026-07-27 · Edward 拍板 A 案的量尺）：
`gen_reply.py` 走的是打字線（server.reply_conv / generate_content），跟 App 裡
「聊聊」真正在跑的即時語音線**不是同一顆腦、也不是同一組設定**。所以既有的
19 條劇本考卷考不到語音線獨有的旋鈕——例如思考深度（thinking_level）只存在於
Live API。要比較「思考調深，她有沒有比較守規矩、慢多少」，量尺本身必須是語音線。

為什麼一支處理「整條劇本」而不是「一輪」（跟 gen_reply.py 的差別）：
Live API 不收 role="model" 的內容（實測回 1007 invalid argument）——也就是說，
沒辦法像打字線那樣「把上一輪她說過的話當歷史再餵回去」。這反而更貼近真實：
真實通話本來就是一條連續的線，她自己記得剛剛講過什麼。所以這支開一條連線、
把整條劇本的每一句依序講完，收完再一起回報。

用文字送、聽回音檔字幕：Live API 允許用文字餵進去，她照樣用同一份說明書、
同一顆語音模型回答，我們讀 output_audio_transcription 拿到她「講出來的那句話」。
這樣不必真人講話就能重複跑同一份考題。

多量一個數字：firstAudioMs＝送出去到聽見第一個聲音的毫秒數。這就是長輩感受到的
「她慢不慢」，跟守規矩程度一起看，才知道調深思考划不划算。

輸入（stdin，一行 JSON）：
  {"id","character","fixture","tmpdir","turns":["這輪使用者說的話", ...]}
輸出（stdout，一行 JSON）：
  {"ok":true,"modelUsed":"...","thinkingLevel":"LOW|default(minimal)",
   "systemInstructionChars":8883,
   "replies":[{"reply":"...","firstAudioMs":1234,"replyDoneMs":2345}, ...]}
  {"ok":false,"error":"...","replies":[...已經跑完的幾輪...]}
"""
import asyncio
import json
import os
import sys
import time
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gen_reply import _set_isolated_paths  # noqa: E402  （同一套 fixture 隔離，不另立一套）

# 一整通電話最多等多久（秒）。正常一輪一兩秒；超過就是這通壞了，寧可標 error，
# 也不要整場考試卡死在某一條劇本上。
CALL_TIMEOUT_S = float(os.environ.get("MUNEA_EVAL_LIVE_CALL_TIMEOUT", "180"))


async def run_call(case, person_id, replies):
    sys.path.insert(0, os.path.join(HERE, os.pardir))
    import server
    import live_voice_server as lv
    from google import genai
    from google.genai import types

    fixture = case.get("fixture") or {}
    if fixture.get("memory_items"):
        server.save_memory_items(fixture["memory_items"])
    # 2026-08-17：個人資料（住哪一區、稱呼、出生年）漏存了——文字線那支一直有存，
    # 只有語音線沒有。後果：她拿不到住哪裡，只好說「我還不知道你住在哪裡」，
    # 而評審手上有背景資料寫著台南，就判她跟已知事實矛盾。她沒錯，是考卷餵得不一樣。
    if fixture.get("person_profile"):
        server.save_person_profile(fixture["person_profile"])
    if fixture.get("living_profile"):
        profile = dict(fixture["living_profile"])
        profile["personId"] = person_id
        profile.setdefault("updatedAt", "2026-07-01T00:00:00+08:00")
        server.save_living_profile(profile)
    server.REQUEST_DATA_IDENTITY.set({"personId": person_id})

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing")

    char = case.get("character") or "寧寧"
    # 跟正式通話同一支組態函式＝同一份說明書、同一組聽話節奏、同一個思考深度旋鈕。
    # 2026-07-31 考卷分國：劇本帶哪一國，真通話就用那一國的說明書（沒帶＝繁中）
    _profile = None
    if case.get("locale"):
        import localization as _loc
        _profile = _loc.voice_session_locale_profile(
            _loc.build_locale_context({"conversationLocale": case["locale"],
                                       "uiLocale": case["locale"]}))
    # 2026-08-17：這通要不要給她工具（設提醒／記行程／要問醫生），照劇本說的來。
    # 在這之前一律不給——於是「設提醒的完整流程」「清單滿了怎麼辦」這類題目
    # 根本考不到，因為她手上根本沒有那些工具。跟 8/13 那個「漏傳語系」同一類：
    # 考卷跟正式線的設定沒對齊，題目看起來有跑、其實考的是另一件事。
    _caps = case.get("capabilities") or {}
    cfg = lv.live_config(
        char=char, name=char, locale_profile=_profile,
        allow_reminders=bool(_caps.get("reminders")),
        allow_events=bool(_caps.get("events")),
        allow_care_questions=bool(_caps.get("careQuestions")),
    )
    thinking = cfg.thinking_config.thinking_level if cfg.thinking_config else None

    # 2026-07-30 引擎開關：跟正式線同一套 _make_client——vertex25 走 Google 雲正式版、
    # 31 照舊走開發者鑰匙。考卷考的必須是「同一顆引擎」，不能自己另開一條。
    client = lv._make_client(api_key)
    async with client.aio.live.connect(model=lv.MODEL, config=cfg) as session:
        for line in case["turns"]:
            sent_at = time.monotonic()
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=line)]),
                turn_complete=True)
            parts, first_audio_ms, tool_calls = [], None, []
            async for msg in session.receive():
                if msg.data and first_audio_ms is None:
                    first_audio_ms = int((time.monotonic() - sent_at) * 1000)
                if msg.tool_call and msg.tool_call.function_calls:
                    # 正式機開著即時查詢／設提醒時，她這輪可能會伸手要工具。考卷不接真工具
                    # （會把外部查詢的快慢混進成績），但一定要回一句，不然她會一直等、整通卡死。
                    #
                    # 2026-08-17：以前一律回 error，於是工具題只考得到「失敗要怎麼講」，
                    # 「成功要怎麼講」永遠考不到——而那才是天天在發生的路徑。
                    # 現在劇本可以用 toolResponses 指定某個工具這通回成功（"ok"）；
                    # 沒指定的照舊回失敗，舊劇本行為不變。
                    _wanted = (case.get("toolResponses") or {})
                    responses = []
                    for fc in msg.tool_call.function_calls:
                        ok = str(_wanted.get(fc.name, "error")).lower() == "ok"
                        payload = {"status": "ok"} if ok else {
                            "status": "error", "error": "eval harness: tool not available"}
                        tool_calls.append({"name": fc.name, "result": payload["status"]})
                        responses.append(types.FunctionResponse(
                            id=fc.id, name=fc.name, response=payload))
                    await session.send_tool_response(function_responses=responses)
                    continue
                content = msg.server_content
                if not content:
                    continue
                if content.output_transcription and content.output_transcription.text:
                    parts.append(content.output_transcription.text)
                if content.turn_complete:
                    break
            replies.append({
                "reply": "".join(parts).strip(),
                "firstAudioMs": first_audio_ms,
                "replyDoneMs": int((time.monotonic() - sent_at) * 1000),
                "toolCalls": tool_calls,
            })

    # SDK 會把說明書字串包成 Content 物件，不能直接 len()——攤回純文字再數字數。
    instruction = cfg.system_instruction
    if not isinstance(instruction, str):
        instruction = "".join(
            (p.text or "") for p in (getattr(instruction, "parts", None) or []))

    return {
        "ok": True,
        "modelUsed": f"{lv.MODEL} (live voice line)",
        "thinkingLevel": str(thinking) if thinking else "default(minimal)",
        "systemInstructionChars": len(instruction),
        # 2026-07-29：把她這通實際拿到的「今日簡報」原文交回去給評審當已知事實。
        # 動機：評審不知道她真的有一份當天核實的簡報（天氣/明天預告/本週話題），
        # 把「簡報裡有提到天氣…」這種照資料講的話判成編造（考卷 S02/S19 誤判）。
        # 用「她實際拿到的原文」而不是一句籠統的「她有簡報」——這樣簡報裡沒有的
        # 假新聞仍然會被抓，不是放水。
        "briefingText": _extract_briefing(instruction),
        "replies": replies,
    }


def _extract_briefing(instruction):
    """從說明書裡切出「（今日簡報…）」整段。內含巢狀括號（「（已核實…）」），
    要數括號深度、不能傻找第一個右括號。"""
    start = instruction.find("（今日簡報")
    if start < 0:
        return ""
    depth = 0
    for i in range(start, min(len(instruction), start + 4000)):
        ch = instruction[i]
        if ch == "（":
            depth += 1
        elif ch == "）":
            depth -= 1
            if depth == 0:
                return instruction[start:i + 1]
    return ""


def main():
    case = json.loads(sys.stdin.readline())
    person_id = f"eval-{case['id']}"
    _set_isolated_paths(case["tmpdir"], person_id)
    replies = []            # 中途炸掉也把已經跑完的幾輪交出去，方便看是哪一輪壞的
    try:
        result = asyncio.run(
            asyncio.wait_for(run_call(case, person_id, replies), CALL_TIMEOUT_S))
    except asyncio.TimeoutError:
        result = {"ok": False, "error": f"live call timeout after {CALL_TIMEOUT_S}s",
                  "replies": replies}
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                  "replies": replies}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
