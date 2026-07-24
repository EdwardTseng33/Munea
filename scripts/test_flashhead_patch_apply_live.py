# -*- coding: utf-8 -*-
"""FlashHead 上游 patch 真實套用複驗（2026-07-23 卡西法，合批手術階段 1 / 方案 B）。

**不在 npm run test:launch 鏈路裡**——這支腳本會對 GitHub 發一次網路 clone，
CI/離線環境跑會失敗，不該拖垮核心測試鏈。這是給有網路的人（今晚 session
已手動跑過兩次、git apply --check 與 patch -p1 --dry-run 皆過）隨時複驗用：

  python scripts/test_flashhead_patch_apply_live.py

會做的事：clone SoulX-FlashHead 到一個暫存資料夾、checkout 到
deploy/runpod-avatar/install-flashhead.sh 裡 MUNEA_FH_COMMIT 預設的那個
commit，依序對 deploy/flashhead-patches/*.patch 跑 `git apply --check`，
全部過才印 PASS；clone 完不管成功失敗都會清掉暫存資料夾。
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES_DIR = ROOT / "deploy" / "flashhead-patches"
UPSTREAM_URL = "https://github.com/Soul-AILab/SoulX-FlashHead.git"

DEFAULT_COMMIT_RE = re.compile(r'MUNEA_FH_COMMIT:-([0-9a-f]{40})')


def _pinned_commit():
    """讀 deploy/runpod-avatar/install-flashhead.sh 裡實際寫死的預設 commit，
    而不是在這支測試腳本裡另外硬編一份可能漂掉的複本。"""
    script = (ROOT / "deploy" / "runpod-avatar" / "install-flashhead.sh").read_text(encoding="utf-8")
    m = DEFAULT_COMMIT_RE.search(script)
    assert m, "could not find MUNEA_FH_COMMIT default in install-flashhead.sh"
    return m.group(1)


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def main():
    commit = _pinned_commit()
    patches = sorted(PATCHES_DIR.glob("*.patch"))
    assert patches, "no *.patch files found in %s" % PATCHES_DIR
    print("pinned commit:", commit)
    print("patches to verify:", [p.name for p in patches])

    tmp = Path(tempfile.mkdtemp(prefix="munea-fh-patch-verify-"))
    try:
        clone = _run(
            ["git", "-c", "core.autocrlf=false", "clone", "--quiet",
             "--filter=blob:none", UPSTREAM_URL, str(tmp / "src")],
            cwd=tmp,
        )
        if clone.returncode != 0:
            print("SKIPPED: could not clone upstream repo (no network?):", clone.stderr.strip())
            return 0

        src = tmp / "src"
        _run(["git", "config", "core.autocrlf", "false"], cwd=src)
        co = _run(["git", "checkout", "--quiet", "--detach", commit], cwd=src)
        assert co.returncode == 0, "checkout of pinned commit failed: %s" % co.stderr

        for p in patches:
            chk = _run(["git", "apply", "--check", str(p.resolve())], cwd=src)
            assert chk.returncode == 0, (
                "%s does NOT apply cleanly to a fresh checkout of %s:\n%s"
                % (p.name, commit, chk.stderr)
            )
            print("  %s applies cleanly to commit %s: PASS" % (p.name, commit))

        print("FlashHead patch live-apply verification: ALL PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
