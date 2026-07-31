#!/usr/bin/env python3
"""部署「不倒退」檢查的守門（2026-07-31 · Edward 拍板「改成比內容、不比編號」）。

**這條保險在守什麼**：7/29 那晚拿自己的分支上正式，把別條線已經上線的安全功能
蓋掉 8 分鐘。所以部署前要確認「正式機現在跑的那份貨，我這版裡面有」。

**為什麼量法要改**：原本純比血緣——現跑的編號必須是 HEAD 的祖先。但 squash 合併
會換編號：別條線從還沒合併的分支上正式，等它的 PR 合併之後，main 上是**另一個編號**
的同一份貨，血緣就對不上了，於是誤擋（7/31 誤擋一次）。

**新的量法**：血緣對不上時再問一次 GitHub——那筆現跑的編號屬於哪個 PR、那個 PR
合進 main 了沒、合併後的編號在不在 HEAD 裡。三者都成立才放行。
**判不出來一律當作會倒退**（沒有 gh、沒網、那筆不屬於任何已合併的 PR）——
這條保險寧可誤擋，也不能放過真的倒退。

這支測的是**行為**（把那個函式抓出來、餵假的 gh 回應真的跑一次），不是比對程式碼
長什麼樣——後者守的是「這一版怎麼寫」、7 月已經被咬過五次。
"""
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "deploy", "cloudrun", "prod-deploy.sh")


def _source():
    with open(SCRIPT, encoding="utf-8") as f:
        return f.read()


def _function_body():
    """把 serving_work_already_merged 這支從部署腳本裡抓出來（不重寫一份、免得走鐘）。"""
    m = re.search(r"^serving_work_already_merged\(\) \{.*?^\}", _source(), re.S | re.M)
    assert m, "找不到 serving_work_already_merged——內容比對那一關被拿掉了？"
    return m.group(0)


def _bash():
    """找一支真的能跑的 bash。

    Windows 上 PATH 裡的 `bash` 常常是 WSL 的殼——沒裝 WSL 時它只會印一段
    「請去market安裝」然後回非零，看起來就像測試在紅。Git Bash 才是我們要的那支。
    """
    cands = [os.environ.get("MUNEA_BASH"),
             r"C:\Program Files\Git\bin\bash.exe",
             r"C:\Program Files (x86)\Git\bin\bash.exe",
             shutil.which("bash")]
    for c in cands:
        if not c or not os.path.exists(c):
            continue
        try:
            probe = subprocess.run([c, "-c", "echo ok"], capture_output=True, text=True, timeout=20)
        except Exception:
            continue
        if probe.returncode == 0 and probe.stdout.strip() == "ok":
            return c
    return None


BASH = _bash()


def _run(fake_gh_stdout, sha="HEAD", fake_gh_rc=0):
    """在真的程式庫裡跑那支函式，gh 用假的替身餵回應。"""
    script = "\n".join([
        "set -u",
        _function_body(),
        # command -v 看得到 shell function，所以這樣就能替換掉真的 gh
        "gh() { printf '%s' \"$FAKE_GH_OUT\"; return $FAKE_GH_RC; }",
        f'if out=$(serving_work_already_merged "{sha}"); then echo "PASS:$out"; else echo FAIL; fi',
    ])
    env = dict(os.environ, FAKE_GH_OUT=fake_gh_stdout, FAKE_GH_RC=str(fake_gh_rc))
    r = subprocess.run([BASH, "-c", script], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    return r.stdout.strip()


@unittest.skipIf(BASH is None, "這台沒有能跑的 bash（Windows 的 WSL 殼不算）")
class ContentCheckBehaviourTest(unittest.TestCase):
    def test_merged_elsewhere_and_present_in_head_passes(self):
        """squash 合併換了編號、但那份貨已經在 HEAD 裡——不該擋（7/31 誤擋的就是這種）。"""
        merged = subprocess.run(["git", "rev-parse", "HEAD~1"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip()
        self.assertTrue(merged)
        self.assertEqual(_run(merged), "PASS:" + merged)

    def test_no_merged_pr_is_blocked(self):
        """查不到那筆屬於任何已合併進 main 的 PR＝判不出來＝擋。"""
        self.assertEqual(_run("null"), "FAIL")
        self.assertEqual(_run(""), "FAIL")

    def test_a_sha_that_does_not_exist_here_is_blocked(self):
        """連那個編號都不在本機＝資訊不足＝擋。"""
        self.assertEqual(_run("0" * 40), "FAIL")

    def test_merge_commit_that_exists_but_is_not_in_head_is_blocked(self):
        """**這條才是真正的把關**：PR 合併了、那個編號本機也有，但**不在我這版的血緣裡**
        ——代表我手上這版比它舊，照樣會蓋掉。

        （造一個孤兒 commit 當替身：物件真的存在，但不是 HEAD 的祖先。
        用「不存在的編號」測不到這一關——那會先卡在「本機找不到」就回來了。）
        """
        tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
        orphan = subprocess.run(["git", "commit-tree", tree, "-m", "not-in-head"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip()
        self.assertTrue(orphan and len(orphan) >= 40)
        self.assertEqual(_run(orphan), "FAIL")

    def test_github_lookup_failure_is_blocked(self):
        """沒網／沒登入就查不出來——這種時候要擋，不是放行。"""
        self.assertEqual(_run("", fake_gh_rc=1), "FAIL")


class WiringTest(unittest.TestCase):
    """接線鎖：函式寫了但沒接進那道關卡＝白做。"""

    def test_the_fast_path_is_still_ancestry(self):
        """血緣對得上就直接過——第二關只是補救，不是取代。"""
        self.assertIn('git merge-base --is-ancestor "$SERVING_COMMIT" HEAD', _source())

    def test_the_content_check_sits_between_pass_and_fail(self):
        src = _source()
        self.assertIn('elif MERGED_AS=$(serving_work_already_merged "$SERVING_COMMIT"); then', src)
        # 血緣關 → 內容關 → 擋，順序不能顛倒
        self.assertLess(src.index("--is-ancestor \"$SERVING_COMMIT\""),
                        src.index("elif MERGED_AS="))
        self.assertLess(src.index("elif MERGED_AS="), src.index("不倒退檢查 FAIL"))

    def test_missing_gh_is_a_hard_stop_not_a_pass(self):
        self.assertIn("command -v gh >/dev/null 2>&1 || return 1", _source())

    def test_the_manual_override_still_exists(self):
        """緊急回退鏈還是要有得走，但必須是明示的。"""
        self.assertIn("MUNEA_DEPLOY_ALLOW_NONLINEAR", _source())


if __name__ == "__main__":
    unittest.main(verbosity=2)
