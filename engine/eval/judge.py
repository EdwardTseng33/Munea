#!/usr/bin/env python3
"""LLM 當評審：給一題（使用者說的話 + 準則清單 + 寧寧的回覆），
用便宜模型（預設 gemini-2.5-flash）逐條判 pass/fail + 一句理由。

不做 1-10 分玄學評分——每條準則獨立判定，總分 = 通過準則數 / 準則數，
題目整體 PASS 的定義＝該題全部準則都 pass（見 run_eval.py 的彙整規則）。

跑法（stdin 一行 JSON，stdout 一行 JSON）：
  輸入：{"userLine": "...", "reply": "...", "criteria": ["...", "..."],
         "knownFacts": ["...", "..."] | null}
  輸出：{"ok": true, "verdicts": [{"criterion": "...", "verdict": "pass|fail", "reason": "..."}]}

2026-07-25（聊天品質劇本庫，卡西法）：新增可選的 knownFacts 參數（見
build_prompt 內註解說明為什麼要加）。golden_set 既有呼叫不帶這個參數，
行為完全不變，向下相容。
"""
import json
import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    # 2026-07-24 教訓（PR #240）：Windows 跑者 stdout 預設 cp1252，中文字會
    # UnicodeEncodeError；這支腳本本機/CI 都可能被redirect，強制 UTF-8 保險。
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

JUDGE_MODEL = os.environ.get("MUNEA_EVAL_JUDGE_MODEL", "gemini-2.5-flash")

JUDGE_SYSTEM = (
    "你是嚴格但公正的評審，負責檢查一個叫『寧寧』的AI健康陪伴角色，"
    "她的一句回覆是否符合給定的驗收準則。"
    "針對每一條準則只能判定 pass 或 fail，不要給 1-10 分這種分數。"
    "準則通常是『有沒有做到某件事』或『不能出現某種東西』，"
    "請照字面意思嚴格核對回覆的實際內容——"
    "不要因為語氣聽起來溫暖好聽，就放過明顯違反準則的地方；"
    "也不要腦補回覆裡沒寫出來的東西當作『有做到』。"
    "只回傳 JSON，不要多餘文字。"
)


def build_prompt(user_line, reply, criteria, known_facts=None):
    numbered = "\n".join(f"{i+1}. {c}" for i, c in enumerate(criteria))
    facts_block = ""
    if known_facts:
        # 2026-07-25（聊天品質劇本庫，卡西法）：可選的「已知事實」context。
        # 沒有這段時，評審只看得到單輪 userLine+reply，無法分辨「AI 用了記憶
        # 側寫裡本來就有的事實」跟「AI 憑空編造」——會把合法的貼身感回覆誤判成
        # 準則6（編造記憶）違反。golden_set 既有呼叫不帶這個參數，行為不變。
        facts_numbered = "\n".join(f"- {fact}" for fact in known_facts)
        facts_block = (
            f"背景（寧寧透過記憶側寫「原本就合法知道」的事，不算她自己編的，"
            f"只有背景裡沒有、使用者這輪也沒講過的才算編造）：\n{facts_numbered}\n\n"
        )
    return (
        f"{facts_block}"
        f"使用者說的話：{user_line}\n\n"
        f"寧寧的回覆：{reply}\n\n"
        f"請針對以下每一條準則，判定 pass 或 fail，並給一句話理由"
        f"（盡量引用回覆裡的具體字句，或指出缺了什麼）：\n{numbered}\n\n"
        f"回傳 JSON 格式：\n"
        f'{{"verdicts": [{{"criterion": "準則原文", "verdict": "pass 或 fail", "reason": "一句話理由"}}]}}\n'
        f"verdicts 陣列順序要跟上面準則的編號順序一致，共 {len(criteria)} 條。"
    )


def judge(user_line, reply, criteria, api_key=None, known_facts=None):
    from google import genai
    from google.genai import types

    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY missing"}
    if not reply or not reply.strip():
        return {"ok": False, "error": "empty reply, nothing to judge"}

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(user_line, reply, criteria, known_facts=known_facts)
    last_err = ""
    for model in (JUDGE_MODEL, "gemini-flash-latest"):
        try:
            r = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=JUDGE_SYSTEM,
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            usage = getattr(r, "usage_metadata", None)
            total_tokens = getattr(usage, "total_token_count", None) if usage else None
            data = json.loads(r.text)
            verdicts = data.get("verdicts") or []
            if len(verdicts) != len(criteria):
                # 評審沒有照數量回，寧可老實回報，不要硬湊配對出錯的結果
                return {"ok": False, "error": f"verdict count {len(verdicts)} != criteria count {len(criteria)}",
                        "raw": verdicts, "judgeModel": model}
            clean = []
            for c, v in zip(criteria, verdicts):
                verdict = str(v.get("verdict") or "").strip().lower()
                if verdict not in ("pass", "fail"):
                    verdict = "fail"  # 評審講不清楚就當沒過，不給模糊地帶佔便宜
                clean.append({
                    "criterion": c, "verdict": verdict,
                    "reason": str(v.get("reason") or "").strip(),
                })
            return {"ok": True, "verdicts": clean, "judgeModel": model, "totalTokens": total_tokens}
        except Exception as e:
            last_err = str(e)[:200]
    return {"ok": False, "error": f"judge call failed: {last_err}"}


def main():
    case = json.loads(sys.stdin.readline())
    result = judge(case["userLine"], case["reply"], case["criteria"],
                    known_facts=case.get("knownFacts"))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
