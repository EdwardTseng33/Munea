#!/usr/bin/env python3
"""LLM 當評審：給一整條多輪劇本（人物側寫 + 逐輪使用者話/寧寧回覆），
在 7 個維度上各打 1-5 分＋一句理由。跟 judge.py（鐵律 0/1、逐句判定）分工：
這支是「整條劇本」評一次（不是逐輪），對應
docs/聊天品質測試-劇本庫與評分表-2026-07-25.md 三-3(b) 的評分指令草稿。

跑法（stdin 一行 JSON，stdout 一行 JSON）：
  輸入：{"scenario": "S04", "persona": "<人物簡述>",
         "turns": [{"user": "...", "reply": "...", "note": "..."}, ...],
         "dimensions": [{"name": "貼身度", "anchor1": "...", "anchor5": "..."}, ...]}
  輸出：{"ok": true, "scores": [{"dimension": "貼身度", "score": 1-5, "reason": "..."}]}
"""
import json
import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    # 沿用 judge.py／gen_reply.py 同一條 2026-07-24 教訓：Windows 跑者 stdout
    # 預設 cp1252，中文字會 UnicodeEncodeError，強制 UTF-8 保險。
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DIM_MODEL = os.environ.get("MUNEA_EVAL_JUDGE_MODEL", "gemini-2.5-flash")

DIM_SYSTEM = (
    "你是嚴格但公正的評審，負責替一個叫『寧寧』的AI健康陪伴角色的一段通話，"
    "在給定的 7 個維度上打 1-5 分（5 分最好），每維附一句話理由，並盡量引用"
    "逐輪回覆裡的具體字句作為判分依據。不要因為語氣聽起來溫暖好聽就整體打高分"
    "——每個維度獨立評分，不互相加分抵銷。若某個維度在這條劇本裡沒有明顯的正面"
    "或負面訊號，給 3 分（普通／不適用不代表滿分）並說明原因。只回傳 JSON，"
    "不要多餘文字。"
)


def build_prompt(scenario, persona, turns, dimensions):
    turns_text = []
    for i, t in enumerate(turns, 1):
        note = f"（情境備註：{t['note']}）" if t.get("note") else ""
        turns_text.append(f"第{i}輪 使用者：{t['user']}{note}\n第{i}輪 寧寧回覆：{t['reply']}")
    dims_text = []
    for d in dimensions:
        dims_text.append(
            f"- {d['name']}：1分範例「{d.get('anchor1', '')}」／5分範例「{d.get('anchor5', '')}」"
        )
    return (
        f"劇本代號：{scenario}\n"
        f"這次通話的使用者是：{persona}\n\n"
        f"完整逐輪對話：\n" + "\n\n".join(turns_text) + "\n\n"
        f"請針對以下 7 個維度各打 1-5 分（附錨點範例供校準，但要看這條劇本"
        f"實際的對話內容判分，不是套錨點字面）：\n" + "\n".join(dims_text) + "\n\n"
        f'回傳 JSON 格式：\n'
        f'{{"scores": [{{"dimension": "維度名稱", "score": 1-5, "reason": "一句話理由"}}]}}\n'
        f"scores 陣列順序要跟上面維度的列出順序一致，共 {len(dimensions)} 條。"
    )


def judge_dimensions(scenario, persona, turns, dimensions, api_key=None):
    from google import genai
    from google.genai import types

    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY missing"}
    if not turns:
        return {"ok": False, "error": "no turns to judge"}

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(scenario, persona, turns, dimensions)
    last_err = ""
    for model in (DIM_MODEL, "gemini-flash-latest"):
        try:
            r = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=DIM_SYSTEM,
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            usage = getattr(r, "usage_metadata", None)
            total_tokens = getattr(usage, "total_token_count", None) if usage else None
            data = json.loads(r.text)
            scores = data.get("scores") or []
            if len(scores) != len(dimensions):
                return {"ok": False, "error": f"score count {len(scores)} != dimension count {len(dimensions)}",
                        "raw": scores, "judgeModel": model}
            clean = []
            for d, s in zip(dimensions, scores):
                try:
                    score = int(s.get("score"))
                except (TypeError, ValueError):
                    score = None
                if score is None or score < 1 or score > 5:
                    # 評審給不出合法分數就老實記 None，讓報告看得出這題要人工複核，
                    # 不要硬夾一個 3 分假裝正常（那是在騙自己）。
                    score = None
                clean.append({
                    "dimension": d["name"], "score": score,
                    "reason": str(s.get("reason") or "").strip(),
                })
            return {"ok": True, "scores": clean, "judgeModel": model, "totalTokens": total_tokens}
        except Exception as e:
            last_err = str(e)[:200]
    return {"ok": False, "error": f"dimension judge call failed: {last_err}"}


def main():
    case = json.loads(sys.stdin.readline())
    result = judge_dimensions(
        case.get("scenario", ""), case.get("persona", ""),
        case.get("turns") or [], case.get("dimensions") or [],
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
