#!/usr/bin/env python3
"""寧寧回答品質 · 輕量評測腳手架 v1（黃金集 + LLM 當評審）。

跑法：
  cd engine/eval && python run_eval.py                # 跑整份黃金集
  python engine/eval/run_eval.py --ids g06,g07,g19    # 只跑指定幾題（除錯/省錢用）
  python engine/eval/run_eval.py --limit 5             # 只跑前 5 題（快速煙霧測試）

需要 GEMINI_API_KEY（會呼叫真模型，不是 dummy 值）——這支不進 CI，是手動建基準用的，
見 engine/eval/README.md「為什麼先不進 CI」。

輸出：
  - stdout：一張趨勢可比的分數表（總分、每類分數、每題結果）
  - engine/eval/results/eval-<timestamp>.json：完整結果（含每條準則的判定與理由，供之後比對）
  - engine/eval/results/latest.json：永遠指向最新一輪（方便下一輪直接 diff）
"""
import argparse
import datetime
import json
import os
import subprocess
import tempfile
import sys
if hasattr(sys.stdout, "reconfigure"):
    # 2026-07-24 教訓（PR #240）：Windows 跑者 stdout 預設 cp1252，中文字會
    # UnicodeEncodeError；這支腳本本機/CI 都可能被redirect，強制 UTF-8 保險。
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(HERE)
GOLDEN_SET_PATH = os.path.join(HERE, "golden_set_v1.json")
RESULTS_DIR = os.path.join(HERE, "results")


def load_golden_set(path=GOLDEN_SET_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_subprocess_json(script_path, payload, cwd):
    proc = subprocess.run(
        [sys.executable, script_path],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8", cwd=cwd, timeout=90,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": f"subprocess exit {proc.returncode}: {proc.stderr[-500:]}"}
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return {"ok": False, "error": f"empty stdout; stderr={proc.stderr[-500:]}"}
    try:
        return json.loads(line[-1])
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"bad JSON from subprocess: {e}; raw={line[-1][:300]}"}


def run_case(item, tmp_root):
    case_dir = os.path.join(tmp_root, item["id"])
    os.makedirs(case_dir, exist_ok=True)
    gen_payload = {
        "id": item["id"], "character": item.get("character") or "寧寧",
        "userLine": item["userLine"], "fixture": item.get("fixture"),
        "tmpdir": case_dir,
    }
    gen_result = run_subprocess_json(os.path.join(HERE, "gen_reply.py"), gen_payload, cwd=ENGINE_DIR)
    if not gen_result.get("ok"):
        return {
            "id": item["id"], "categories": item["categories"], "status": "error",
            "error": f"gen_reply: {gen_result.get('error')}", "reply": None, "verdicts": [],
            "passRate": 0.0, "totalTokens": 0,
        }

    reply = gen_result["reply"]
    judge_payload = {"userLine": item["userLine"], "reply": reply, "criteria": item["criteria"]}
    judge_result = run_subprocess_json(os.path.join(HERE, "judge.py"), judge_payload, cwd=ENGINE_DIR)
    if not judge_result.get("ok"):
        return {
            "id": item["id"], "categories": item["categories"], "status": "error",
            "error": f"judge: {judge_result.get('error')}", "reply": reply, "verdicts": [],
            "passRate": 0.0, "totalTokens": gen_result.get("totalTokens") or 0,
        }

    verdicts = judge_result["verdicts"]
    passed = sum(1 for v in verdicts if v["verdict"] == "pass")
    total = len(verdicts)
    tokens = (gen_result.get("totalTokens") or 0) + (judge_result.get("totalTokens") or 0)
    return {
        "id": item["id"], "categories": item["categories"], "status": "ok",
        "userLine": item["userLine"], "reply": reply, "verdicts": verdicts,
        "passCount": passed, "criteriaCount": total,
        "passRate": (passed / total) if total else 0.0,
        "itemPass": passed == total,
        "totalTokens": tokens,
    }


def combine_repeat_runs(item, runs):
    """N 次多數決（7/24 教訓：單次跑 ±1 題＝噪聲不可判讀、關鍵驗收 N=3 過半才算數）。
    整題 PASS＝過半回合 PASS（跑出錯的回合算 FAIL 票、不算棄權）；
    代表回合＝第一個跟多數判定同向的成功回合（分數表與逐題理由看它、完整回合都存進結果檔）。"""
    votes = sum(1 for r in runs if r["status"] == "ok" and r.get("itemPass"))
    majority = votes * 2 > len(runs)
    rep = next((r for r in runs if r["status"] == "ok" and bool(r.get("itemPass")) == majority), runs[0])
    combined = dict(rep)
    combined["itemPass"] = majority
    combined["repeat"] = len(runs)
    combined["passVotes"] = votes
    combined["runs"] = [
        {"status": r["status"], "itemPass": r.get("itemPass"), "passCount": r.get("passCount"),
         "criteriaCount": r.get("criteriaCount"), "reply": r.get("reply"),
         "verdicts": r.get("verdicts"), "error": r.get("error")}
        for r in runs
    ]
    combined["totalTokens"] = sum(r.get("totalTokens") or 0 for r in runs)
    return combined


def aggregate(results, golden_doc):
    by_category = {}
    for r in results:
        for cat in r["categories"]:
            by_category.setdefault(cat, {"items": 0, "itemsPassed": 0, "criteria": 0, "criteriaPassed": 0})
            slot = by_category[cat]
            slot["items"] += 1
            slot["itemsPassed"] += 1 if r.get("itemPass") else 0
            slot["criteria"] += r.get("criteriaCount", 0)
            slot["criteriaPassed"] += r.get("passCount", 0)

    total_items = len(results)
    items_passed = sum(1 for r in results if r.get("itemPass"))
    total_criteria = sum(r.get("criteriaCount", 0) for r in results)
    criteria_passed = sum(r.get("passCount", 0) for r in results)
    total_tokens = sum(r.get("totalTokens", 0) for r in results)
    errors = [r for r in results if r["status"] == "error"]

    return {
        "runAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "goldenSetVersion": golden_doc.get("version"),
        "goldenSetSeedCount": golden_doc.get("seedCount"),
        "itemsRun": total_items,
        "itemsPassed": items_passed,
        "itemPassRate": round(items_passed / total_items, 3) if total_items else 0.0,
        "criteriaTotal": total_criteria,
        "criteriaPassed": criteria_passed,
        "criteriaPassRate": round(criteria_passed / total_criteria, 3) if total_criteria else 0.0,
        "errors": len(errors),
        "totalTokens": total_tokens,
        "byCategory": {
            cat: {
                **slot,
                "itemPassRate": round(slot["itemsPassed"] / slot["items"], 3) if slot["items"] else 0.0,
                "criteriaPassRate": round(slot["criteriaPassed"] / slot["criteria"], 3) if slot["criteria"] else 0.0,
            }
            for cat, slot in by_category.items()
        },
    }


def print_table(summary, results):
    print("=" * 72)
    print(f"寧寧回答品質評測 v1   跑於 {summary['runAt']}")
    print(f"黃金集版本：{summary['goldenSetVersion']}（種子 {summary['goldenSetSeedCount']} 題，本輪實跑 {summary['itemsRun']} 題）")
    if summary.get("repeat", 1) > 1:
        print(f"多數決模式：每題跑 {summary['repeat']} 次、過半才算整題 PASS")
    print("-" * 72)
    print(f"整題 PASS 率：{summary['itemsPassed']}/{summary['itemsRun']} = {summary['itemPassRate']*100:.1f}%")
    print(f"準則 PASS 率：{summary['criteriaPassed']}/{summary['criteriaTotal']} = {summary['criteriaPassRate']*100:.1f}%")
    if summary["errors"]:
        print(f"警告：有 {summary['errors']} 題跑不出結果（見下方 ERR）")
    print(f"本輪估計 token 用量：約 {summary['totalTokens']:,} tokens")
    print("-" * 72)
    print("分類別：")
    for cat, slot in sorted(summary["byCategory"].items()):
        print(f"  {cat:<20} 整題 {slot['itemsPassed']}/{slot['items']}"
              f"（{slot['itemPassRate']*100:5.1f}%）  準則 {slot['criteriaPassed']}/{slot['criteria']}"
              f"（{slot['criteriaPassRate']*100:5.1f}%）")
    print("-" * 72)
    print("逐題：")
    for r in results:
        if r["status"] == "error":
            print(f"  [ERR ] {r['id']:<5} {r['error']}")
            continue
        mark = "PASS" if r["itemPass"] else "FAIL"
        vote = f"  {r['passVotes']}/{r['repeat']}票" if r.get("repeat") else ""
        print(f"  [{mark}] {r['id']:<5} {r['passCount']}/{r['criteriaCount']}{vote}  {','.join(r['categories'])}")
        if mark == "FAIL":
            for v in r["verdicts"]:
                if v["verdict"] == "fail":
                    print(f"         x {v['criterion'][:40]}...  -> {v['reason']}")
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(description="ningning reply quality eval v1")
    parser.add_argument("--ids", help="comma separated case ids, e.g. g06,g07")
    parser.add_argument("--limit", type=int, help="only run first N cases (quick smoke)")
    parser.add_argument("--repeat", type=int, default=1,
                        help="每題跑 N 次、過半多數決（關鍵驗收用 N=3；單次 ±1 題＝噪聲不可判讀）")
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        sys.path.insert(0, ENGINE_DIR)
        import env_loader
        env_loader.load_engine_env()
    if not os.environ.get("GEMINI_API_KEY"):
        print("卡住了：環境裡沒有 GEMINI_API_KEY（engine/.env.local 也沒有），"
              "這支腳本要呼叫真模型，沒鑰匙跑不動。", file=sys.stderr)
        sys.exit(2)

    golden_doc = load_golden_set()
    items = golden_doc["items"]
    if args.ids:
        wanted = set(x.strip() for x in args.ids.split(","))
        items = [i for i in items if i["id"] in wanted]
    if args.limit:
        items = items[: args.limit]

    if not items:
        print("沒有題目可跑（--ids 或 --limit 篩到空了）", file=sys.stderr)
        sys.exit(2)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="munea-eval-") as tmp_root:
        results = []
        for i, item in enumerate(items, 1):
            print(f"[{i}/{len(items)}] running {item['id']}...", file=sys.stderr)
            if args.repeat <= 1:
                results.append(run_case(item, tmp_root))
                continue
            runs = []
            for n in range(args.repeat):
                print(f"    run {n + 1}/{args.repeat}", file=sys.stderr)
                runs.append(run_case(item, tmp_root))
            results.append(combine_repeat_runs(item, runs))

    summary = aggregate(results, golden_doc)
    summary["repeat"] = args.repeat
    print_table(summary, results)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(RESULTS_DIR, f"eval-{timestamp}.json")
    payload = {"summary": summary, "results": results}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    latest_path = os.path.join(RESULTS_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n完整結果存到：{out_path}\n（latest.json 也同步更新，方便下一輪直接對照）")


if __name__ == "__main__":
    main()
