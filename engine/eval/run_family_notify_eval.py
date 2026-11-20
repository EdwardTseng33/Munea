#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「通知家人決定」實測（#717 第二張 · 2026-11-18）：通知家人前的 AI 裁判，在測試集的句子上判得對不對。

測試集：engine/eval/family_notify/family_notify_decision_v1.json（任務單點名的 12 句平常話＋6 句受暴說法，另加 13 句）。
每一題是一通電話裡長輩說的話（一定有一句急症，所以會排一則「通知家人」）：
  ① AI 裁判（perception_engine.guardian_abuse_review）真的打一次 Gemini，看它判「有沒有提到被家人／照顧的人傷害」對不對；
  ② 把 AI 的判定放回語音線真的決定流程（live_voice_server：關鍵字＋AI 裁判），看最後「發／不發」對不對；
  ③ 對照：AI 沒回（逾時、壞掉）時照關鍵字的決定（題庫的 fallback 欄）。
第二層 AI（guardian_semantic_review）這裡換成「沒抓到」，只量 AI 裁判本身；記錄、通知全部是假的，不碰資料庫、不發任何通知。

要 GEMINI_API_KEY（環境變數，或 engine/.env.local）；沒有就印一行跳過、正常結束。
跑法：
    python engine/eval/run_family_notify_eval.py
    python engine/eval/run_family_notify_eval.py --runs 3              # 同一題問三次，看穩不穩
    python engine/eval/run_family_notify_eval.py --out <檔案路徑>      # 另存結果（預設不寫檔，免得結果檔混進程式庫）
"""
import argparse
import asyncio
import io
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
sys.path.insert(0, ENGINE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
BANK = os.path.join(HERE, "family_notify", "family_notify_decision_v1.json")


def load_key():
    if os.environ.get("GEMINI_API_KEY"):
        return True
    try:
        from env_loader import load_engine_env
        load_engine_env()
    except Exception:  # noqa: BLE001
        pass
    return bool(os.environ.get("GEMINI_API_KEY"))


async def decide(voice, said, verdict):
    """語音線真的決定流程：字幕一輪一輪進來 → 守護腦第一層 → 排隊 → 掛斷 → AI 裁判（換成這次的判定）→ 發不發。"""
    notices = []
    voice.guardian_record_and_alert = lambda *a, **k: None
    voice.guardian_family_notify = lambda cid, pid, level, cats, **k: notices.append(level) or True
    voice.perception_engine.guardian_semantic_review = lambda *a, **k: None
    voice.perception_engine.guardian_abuse_review = lambda *a, **k: verdict
    st = voice._new_call_state()
    st["memory_scope"] = "voice-eval-only"
    for turn, text in enumerate(said, 1):
        voice._guardian_note_user_text(st, text)
        st["user_buf"] = (st["user_buf"] + text)[-200:]
        await voice.guardian_watch(0, "user", st["user_buf"], st, None, turn_id=turn, allow_cue=True)
        voice._capture_call_turns(st)
        st["user_buf"], st["ai_buf"] = "", ""
    await voice._guardian_drain_on_close(0, st)
    return "notify" if notices else "block"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1, help="同一題問幾次（看穩定度）")
    ap.add_argument("--out", help="另存結果 JSON 的路徑（預設不寫檔）")
    args = ap.parse_args()
    if not load_key():
        print("跳過：沒有 GEMINI_API_KEY（這支要真的問 Gemini；單元測試用假 AI 驗流程，見 test_voice_guardian_brain_route）")
        return 0
    os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
    os.environ["MUNEA_PRODUCT_EVENTS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="family-notify-eval-"), "pe.json")
    for k in ("MUNEA_BRAIN_INTERNAL_URL", "MUNEA_VOICE_BRAIN_SECRET", "MUNEA_SLACK_ALERT_WEBHOOK"):
        os.environ.pop(k, None)                       # 保險：就算本機設定檔有，也不送 Brain、不發告警
    import perception_engine
    import live_voice_server as voice
    real_review = perception_engine.guardian_abuse_review
    voice.GUARDIAN_FAMILY_HOLD_S = 0.05
    with io.open(BANK, encoding="utf-8") as f:
        bank = json.load(f)

    rows = []
    for item in bank["items"]:
        for run in range(args.runs):
            t0 = time.monotonic()
            verdict = real_review(item["said"])
            ms = int((time.monotonic() - t0) * 1000)
            decision = asyncio.run(decide(voice, item["said"], verdict))
            rows.append({
                "id": item["id"], "from": item["from"], "run": run + 1, "expect": item["expect"], "abuse": item["abuse"],
                "ai": None if verdict is None else verdict["abuse"], "confidence": None if verdict is None else verdict["confidence"],
                "ms": ms, "decision": decision, "fallback": item["fallback"],
                "error": None if verdict is not None else perception_engine.ABUSE_REVIEW_STATS.get("lastError"),
            })
            r = rows[-1]
            mark = "對" if r["decision"] == r["expect"] else ("誤擋" if r["expect"] == "notify" else "漏擋")
            print("%s #%d  該%s  AI=%s(%s) %5dms  決定=%s %s   沒 AI 時=%s   %s" % (
                r["id"], r["run"], "發" if r["expect"] == "notify" else "擋",
                "受暴" if r["ai"] else ("沒有" if r["ai"] is False else "沒回"), r["confidence"], r["ms"],
                "發" if decision == "notify" else "擋", mark,
                "發" if r["fallback"] == "notify" else "擋", "　".join(item["said"])))

    def stats(subset):
        n = len(subset)
        answered = [r for r in subset if r["ai"] is not None]
        return {
            "n": n,
            "aiAnswered": len(answered),
            "aiCorrect": sum(r["ai"] == r["abuse"] for r in answered),
            "decisionCorrect": sum(r["decision"] == r["expect"] for r in subset),
            "falseBlocks": sum(r["expect"] == "notify" and r["decision"] == "block" for r in subset),
            "misses": sum(r["expect"] == "block" and r["decision"] == "notify" for r in subset),
            "fallbackCorrect": sum(r["fallback"] == r["expect"] for r in subset),
            "medianMs": sorted(r["ms"] for r in subset)[n // 2] if n else None,
            "maxMs": max((r["ms"] for r in subset), default=None),
        }

    groups = sorted({r["from"] for r in rows})
    summary = {"model": perception_engine._abuse_review_model(), "runs": args.runs, "all": stats(rows),
               "byFrom": {g: stats([r for r in rows if r["from"] == g]) for g in groups},
               "reviewStats": dict(perception_engine.ABUSE_REVIEW_STATS)}
    print("=" * 72)
    for k in groups + ["all"]:
        s = summary["all"] if k == "all" else summary["byFrom"][k]
        print("%-8s %3d 題：AI 回了 %d、判對 %d｜最後決定對 %d（誤擋 %d、漏擋 %d）｜沒 AI 時照關鍵字對 %d｜中位 %sms、最慢 %sms" % (
            k, s["n"], s["aiAnswered"], s["aiCorrect"], s["decisionCorrect"], s["falseBlocks"], s["misses"],
            s["fallbackCorrect"], s["medianMs"], s["maxMs"]))
    print("模型：%s；呼叫 %d 次、失敗 %d、重問 %d" % (summary["model"], summary["reviewStats"]["calls"],
                                                summary["reviewStats"]["errors"], summary["reviewStats"]["retries"]))
    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2)
        print("結果另存：%s" % args.out)
    for ex in (voice._GUARDIAN_EVENT_EXECUTOR, voice._GUARDIAN_NOTIFY_EXECUTOR, voice._GUARDIAN_AI_EXECUTOR):
        ex.shutdown(wait=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
