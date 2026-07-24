# -*- coding: utf-8 -*-
"""FlashHead 上游 patch 靜態完整性測試（2026-07-23 卡西法，合批手術階段 1 / 方案 B）。

不需要網路、不需要 clone SoulX-FlashHead、不需要 GPU/torch——純粹解析
deploy/flashhead-patches/*.patch 這幾個檔案本身的文字內容，驗證：

  1. 每個 patch 都是合法的 unified diff（有 diff --git / --- / +++ 三行、
     --- 與 +++ 指向同一個檔案路徑）
  2. 每個 patch 只動一個檔案（不小心把兩個檔案的改動混進同一個 patch）
  3. 純 LF、無 CRLF（Windows 開發機若不小心把 CRLF 寫進 patch，Linux GPU
     機器上 git apply / patch -p1 會失敗——這是今晚實測踩過的真坑，見
     deploy/flashhead-patches/README.md）
  4. 0001-gate-profile-sync.patch 專屬「touched 行數對帳」：確認移除的
     8 行都是 torch.cuda.synchronize()、新增的對應 8 行都是
     _profile_sync()，且沒有動到其他任何一行程式碼（避免手改/腳本改動時
     不小心多刪/多加東西）

真的「套不套得上 commit 9bc03de 純淨 checkout」的複驗（需要網路 clone
上游 repo）另外放在 scripts/test_flashhead_patch_apply_live.py，不在這支
（避免 CI 因為連不到 GitHub 而誤判整條 test:launch 失敗）。

跑法：python scripts/test_flashhead_patch_integrity.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES_DIR = ROOT / "deploy" / "flashhead-patches"

DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>\S+) b/(?P<b>\S+)$")
MINUS_FILE_RE = re.compile(r"^--- a/(?P<path>\S+)$")
PLUS_FILE_RE = re.compile(r"^\+\+\+ b/(?P<path>\S+)$")


def _read_patch_text(path):
    raw = path.read_bytes()
    assert raw, "patch file must not be empty: %s" % path
    assert b"\r\n" not in raw, (
        "patch must be pure LF (no CRLF) or git apply/patch -p1 will fail on "
        "the Linux GPU box: %s" % path
    )
    return raw.decode("utf-8")


def _parse_single_file_diff(text, patch_path):
    lines = text.splitlines()
    diff_git_lines = [l for l in lines if l.startswith("diff --git ")]
    assert len(diff_git_lines) == 1, (
        "expected exactly one 'diff --git' header (one file per patch), got %d in %s"
        % (len(diff_git_lines), patch_path)
    )
    m = DIFF_GIT_RE.match(diff_git_lines[0])
    assert m, "malformed 'diff --git' header in %s: %r" % (patch_path, diff_git_lines[0])
    assert m.group("a") == m.group("b"), (
        "diff --git a/... b/... must reference the same path (not a rename) in %s"
        % patch_path
    )

    minus_lines = [l for l in lines if MINUS_FILE_RE.match(l)]
    plus_lines = [l for l in lines if PLUS_FILE_RE.match(l)]
    assert len(minus_lines) == 1 and len(plus_lines) == 1, (
        "expected exactly one --- and one +++ file header in %s" % patch_path
    )
    minus_path = MINUS_FILE_RE.match(minus_lines[0]).group("path")
    plus_path = PLUS_FILE_RE.match(plus_lines[0]).group("path")
    assert minus_path == plus_path == m.group("a"), (
        "--- / +++ / diff --git paths must all agree in %s (got %r / %r / %r)"
        % (patch_path, minus_path, plus_path, m.group("a"))
    )
    return m.group("a")


def _hunk_body_lines(text):
    """Return only the actual +/-/context lines that belong to hunks (skip the
    diff --git / index / --- / +++ / @@ header lines themselves)."""
    body = []
    in_hunk = False
    for line in text.splitlines():
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if line.startswith(("diff --git ", "index ", "--- ", "+++ ")):
            in_hunk = False
            continue
        if in_hunk:
            body.append(line)
    return body


def test_patches_dir_exists_and_has_at_least_one_patch():
    assert PATCHES_DIR.is_dir(), "missing deploy/flashhead-patches directory"
    patches = sorted(PATCHES_DIR.glob("*.patch"))
    assert len(patches) >= 1, "expected at least one *.patch file in %s" % PATCHES_DIR
    print("test_patches_dir_exists_and_has_at_least_one_patch: PASS (%d patch file(s))"
          % len(patches))


def test_every_patch_is_well_formed_single_file_unified_diff():
    patches = sorted(PATCHES_DIR.glob("*.patch"))
    for p in patches:
        text = _read_patch_text(p)
        touched = _parse_single_file_diff(text, p)
        assert touched, "empty touched path for %s" % p
        print("  %s touches exactly one file: %s" % (p.name, touched))
    print("test_every_patch_is_well_formed_single_file_unified_diff: PASS")


def test_0001_gate_profile_sync_touched_line_accounting():
    """"對 commit 9bc03de 套得上、touched 行數對帳" 的靜態版——不需要網路，
    直接數 patch 文字本身的 +/- 行，跟設計文件第 1.2 節聲稱的 8 處/8 處
    一一對帳，順便防手改/腳本改動時不小心動到其他行。"""
    p = PATCHES_DIR / "0001-gate-profile-sync.patch"
    assert p.is_file(), "expected patch file missing: %s" % p
    text = _read_patch_text(p)
    touched = _parse_single_file_diff(text, p)
    assert touched == "flash_head/src/pipeline/flash_head_pipeline.py", (
        "0001 patch must only touch flash_head_pipeline.py, got %r" % touched
    )

    body = _hunk_body_lines(text)
    removed = [l for l in body if l.startswith("-")]
    added = [l for l in body if l.startswith("+")]

    removed_sync_calls = [l for l in removed if l[1:].strip() == "torch.cuda.synchronize()"]
    added_profile_sync_calls = [l for l in added if l[1:].strip() == "_profile_sync()"]

    assert len(removed_sync_calls) == 8, (
        "expected exactly 8 removed 'torch.cuda.synchronize()' call sites, got %d"
        % len(removed_sync_calls)
    )
    assert len(added_profile_sync_calls) == 8, (
        "expected exactly 8 added '_profile_sync()' call sites, got %d"
        % len(added_profile_sync_calls)
    )

    # No other line may be removed -- every '-' line in this patch must be one
    # of the 8 sync-barrier call sites (protects against an accidental extra
    # deletion sneaking into a future re-generation of this patch).
    assert len(removed) == 8, (
        "expected the ONLY removed lines to be the 8 sync-barrier call sites, "
        "found %d removed lines total (extra unexpected removal!): %r"
        % (len(removed), [l for l in removed if l not in removed_sync_calls])
    )

    # The new module-level flag and helper function must be present exactly
    # once each (defaults preserve pre-patch behavior: PROFILE_SYNC = True).
    assert sum(1 for l in added if l[1:].strip() == "PROFILE_SYNC = True") == 1, (
        "expected exactly one added 'PROFILE_SYNC = True' default-on line"
    )
    assert sum(1 for l in added if l[1:].strip() == "def _profile_sync():") == 1, (
        "expected exactly one added '_profile_sync' helper definition"
    )
    assert sum(1 for l in added if "torch.cuda.synchronize()" in l[1:]) == 1, (
        "expected exactly one remaining torch.cuda.synchronize() call in the "
        "whole patch (inside the new _profile_sync() helper itself)"
    )

    print("test_0001_gate_profile_sync_touched_line_accounting: PASS "
          "(8 removed sync calls == 8 added _profile_sync() calls, no stray edits)")


def test_no_crlf_anywhere_in_patches_dir():
    for p in sorted(PATCHES_DIR.glob("*.patch")):
        raw = p.read_bytes()
        assert b"\r\n" not in raw, "CRLF found in %s (must be pure LF)" % p
    print("test_no_crlf_anywhere_in_patches_dir: PASS")


def main():
    test_patches_dir_exists_and_has_at_least_one_patch()
    test_every_patch_is_well_formed_single_file_unified_diff()
    test_0001_gate_profile_sync_touched_line_accounting()
    test_no_crlf_anywhere_in_patches_dir()
    print("FlashHead patch integrity test: ALL PASS")


if __name__ == "__main__":
    main()
