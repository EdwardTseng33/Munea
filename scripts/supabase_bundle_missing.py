#!/usr/bin/env python3
import argparse
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPT_DIR)

from supabase_doctor import SCHEMA_TABLES, doctor

DEFAULT_OUT = os.path.join(ROOT, "dist", "supabase", "munea_missing_foundations.sql")


def normalize_repo_path(path):
    return path.replace("\\", "/")


def read_sql(repo_path):
    full_path = os.path.join(ROOT, *repo_path.split("/"))
    with open(full_path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def foundation_files():
    return [path for path in SCHEMA_TABLES if not path.endswith("001_initial_munea_schema.sql")]


def build_bundle(files, live_result=None):
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "-- Munea Supabase missing foundation bundle",
        f"-- Generated at: {now}",
        "-- Purpose: paste this whole file into Supabase SQL Editor when live doctor reports missing tables.",
        "-- Safety: this file contains schema SQL only. It does not include secrets.",
        "-- After applying, run: npm run supabase:doctor:live",
        "",
    ]
    if live_result:
        lines.extend(
            [
                f"-- Live project URL: {live_result.get('supabaseUrl') or '(missing)'}",
                f"-- Table checks currently passing: {sum(1 for item in live_result.get('tableChecks', []) if item.get('ok'))}/{len(live_result.get('tableChecks', []))}",
                "",
            ]
        )
    for repo_path in files:
        lines.extend(
            [
                "",
                "-- =====================================================================",
                f"-- BEGIN {repo_path}",
                "-- =====================================================================",
                "",
                read_sql(repo_path),
                "",
                "-- =====================================================================",
                f"-- END {repo_path}",
                "-- =====================================================================",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Build a Supabase SQL bundle for currently missing Munea foundation tables.")
    parser.add_argument("--all-foundations", action="store_true", help="Bundle SQL 003-007 without calling the live doctor.")
    parser.add_argument("--out", default=DEFAULT_OUT, help=f"Output path. Default: {normalize_repo_path(DEFAULT_OUT)}")
    parser.add_argument("--print", action="store_true", help="Print the bundle to stdout instead of writing a file.")
    args = parser.parse_args()

    live_result = None
    if args.all_foundations:
        files = foundation_files()
    else:
        live_result = doctor(live=True)
        files = live_result.get("recommendedSqlFiles", [])

    if not files:
        print("No missing Supabase foundation SQL files were recommended by live doctor.")
        return 0

    bundle = build_bundle(files, live_result=live_result)
    if args.print:
        print(bundle, end="")
        return 0

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(bundle)

    print("Munea Supabase SQL bundle created")
    print(f"- output: {normalize_repo_path(out_path)}")
    print("- files:")
    for repo_path in files:
        print(f"  - {repo_path}")
    print("- next: paste the bundle into Supabase SQL Editor, then run npm run supabase:doctor:live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
