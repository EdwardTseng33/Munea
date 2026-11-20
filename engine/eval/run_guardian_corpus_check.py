#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守護腦「真實對話假警報」檢查（補助案 A4 · 2026-11-18 蘇菲）

題庫量的是「一句一句單獨看」；這支量的是「整段像真的聊天時，會不會亂拉警報」。
語料＝聊天品質考卷（engine/eval/chat_quality/scenarios_v1.json，79 題劇本）裡全部長輩說的話，
每句照正式語音線的走法：先過規則層，規則層 none／low 的再送第二層 AI（前一句當前後文，跟語音線一樣只帶一句）。
判成 high／critical 的句子全部列出來，由人逐句判定「劇本本來就設計的急症」還是「假警報」。

跑法：
    GEMINI_API_KEY=... python engine/eval/run_guardian_corpus_check.py [--workers 6] [--out 檔名]
"""
import argparse
import datetime as dt
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import model_router  # noqa: E402

LEVELS = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def sentences():
    with io.open(os.path.join(HERE, "chat_quality", "scenarios_v1.json"), encoding="utf-8") as f:
        items = json.load(f)["items"]
    out = []
    for sc in items:
        prev = ""
        for t in sc.get("turns", []):
            u = (t.get("user") or "").strip()
            if u:
                out.append({"scenario": sc["id"], "label": sc.get("label", ""), "text": u, "prev": prev})
                prev = u
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out")
    args = ap.parse_args()
    import perception_engine
    rows = sentences()
    for r in rows:
        r["rule"] = model_router.guardian_evaluate_response({"text": r["text"], "effort": "quick"})
    need = [r for r in rows if LEVELS[r["rule"]["risk"]["level"]] < 3 and r["rule"]["responsePolicy"].get("softSignalForReview")]

    def review(r):
        return perception_engine.guardian_semantic_review(
            r["text"], [r["prev"]] if r["prev"] else None, bool(r["rule"]["responsePolicy"].get("reviewForced")))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max(1, args.workers)) as ex:
        for r, ai in zip(need, ex.map(review, need)):
            r["ai"] = ai
    flagged = []
    for r in rows:
        rl = r["rule"]["risk"]["level"]
        ai = r.get("ai")
        if LEVELS[rl] >= 3 or (ai and LEVELS.get(ai.get("level"), 0) >= 3):
            flagged.append({"scenario": r["scenario"], "label": r["label"], "text": r["text"],
                            "rule": rl, "ruleCategories": r["rule"]["risk"]["categories"],
                            "ai": ai})
    st = dict(perception_engine.GUARDIAN_REVIEW_STATS)
    summary = {"runAt": dt.datetime.now(dt.timezone.utc).isoformat(),
               "model": perception_engine.guardian_model(), "thinking": perception_engine.guardian_thinking() or "default",
               "sentences": len(rows), "sentToAi": len(need), "flagged": len(flagged), "aiReviewStats": st}
    print("句數 %d｜送 AI %d｜判 high／critical %d｜AI 呼叫 %d、重問 %d、失敗 %d（%s／思考 %s）" % (
        len(rows), len(need), len(flagged), st["calls"], st.get("retries", 0), st["errors"], summary["model"], summary["thinking"]))
    for f in flagged:
        src = ("規則層=%s %s" % (f["rule"], f["ruleCategories"])) if LEVELS[f["rule"]] >= 3 else (
            "AI=%s/%s %.2f「%s」" % (f["ai"]["level"], f["ai"]["category"], f["ai"]["confidence"], f["ai"]["reason"]))
        print("  %s %s｜%s｜「%s」" % (f["scenario"], f["label"], src, f["text"]))
    out = args.out or os.path.join(HERE, "results", "guardian-corpus-%s.json" % dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"summary": summary, "flagged": flagged}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("結果：%s" % out)


if __name__ == "__main__":
    main()
