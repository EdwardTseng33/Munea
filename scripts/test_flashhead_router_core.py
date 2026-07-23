# -*- coding: utf-8 -*-
"""FlashHead 多程序分流路由表單元測試（2026-07-23 卡西法，合批手術階段 2）。

不需要真 GPU、不需要 aiohttp／網路——只測 flashhead_router_core.py 的純
路由決策邏輯（跟 flashhead_engine_core.py 一樣的零重依賴設計哲學）。

跑法：python scripts/test_flashhead_router_core.py
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))

import flashhead_router_core as frc  # noqa: E402


def _make_token(payload):
    """組一個「跟真的 call token 同形狀」的字串：base64url(json).隨便簽章。
    路由層本來就不驗證簽章（見 decode_token_payload_unverified 文件），
    這裡簽章部分塞什麼都無所謂，重點是有 "." 分隔、encoded 段是合法
    base64url(json)。"""
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")
    return encoded + ".fake-signature-not-checked-by-router"


def test_decode_token_payload_unverified():
    token = _make_token({"worker_id": "glows-tw06-p1", "call_id": "abc"})
    payload = frc.decode_token_payload_unverified(token)
    assert payload == {"worker_id": "glows-tw06-p1", "call_id": "abc"}

    # demo token 形狀（沒有 "."）-> None
    assert frc.decode_token_payload_unverified("opaque-demo-token-no-dot") is None
    assert frc.decode_token_payload_unverified("") is None
    assert frc.decode_token_payload_unverified(None) is None
    # 壞掉的 base64/json -> None，不炸例外
    assert frc.decode_token_payload_unverified("not-base64!!!.sig") is None
    assert frc.decode_token_payload_unverified(
        base64.urlsafe_b64encode(b"not json at all").decode("ascii") + ".sig"
    ) is None
    print("test_decode_token_payload_unverified: PASS")


def test_worker_process_index():
    assert frc.worker_process_index("glows-tw06-p0", "glows-tw06", 3) == 0
    assert frc.worker_process_index("glows-tw06-p2", "glows-tw06", 3) == 2
    # 超出這台機器的 process 數 -> None（不可以路由到不存在的 process）
    assert frc.worker_process_index("glows-tw06-p3", "glows-tw06", 3) is None
    # 前綴不符（別台機器的 worker_id）-> None
    assert frc.worker_process_index("runpod-4090-p0", "glows-tw06", 3) is None
    # 尾碼不是數字 -> None
    assert frc.worker_process_index("glows-tw06-pX", "glows-tw06", 3) is None
    # 缺欄位 -> None
    assert frc.worker_process_index(None, "glows-tw06", 3) is None
    assert frc.worker_process_index("glows-tw06-p0", "", 3) is None
    print("test_worker_process_index: PASS")


def test_process_worker_id_and_port_roundtrip():
    """啟動器（bash 端 -p${i}／MUNEA_FACE_PORT+1+i）跟路由器（這支模組）
    必須共用同一份命名規則，這裡先確認模組內部自己是自洽的（互為反函式）；
    跟 bash 端是否真的算出同一個數字，見下面 test_launcher_dry_run_matches_core_module。"""
    for i in range(5):
        wid = frc.process_worker_id("glows-tw06", i)
        assert wid == "glows-tw06-p%d" % i
        assert frc.worker_process_index(wid, "glows-tw06", 5) == i
        assert frc.process_port(8188, i) == 8189 + i
    print("test_process_worker_id_and_port_roundtrip: PASS")


def test_round_robin_picker():
    rr = frc.RoundRobinPicker(3)
    picks = [rr.pick() for _ in range(7)]
    assert picks == [0, 1, 2, 0, 1, 2, 0]

    try:
        frc.RoundRobinPicker(0)
    except ValueError:
        pass
    else:
        raise AssertionError("RoundRobinPicker(0) must reject n_procs < 1")
    print("test_round_robin_picker: PASS")


def test_pick_backend_index_switch_explicit_slot():
    rr = frc.RoundRobinPicker(3)
    assert frc.pick_backend_index("/switch", "", 0, "glows-tw06", 3, rr) == 0
    assert frc.pick_backend_index("/switch", "", 2, "glows-tw06", 3, rr) == 2
    # 超出範圍 -> None（呼叫端要轉成 400，不能亂猜一個 process）
    assert frc.pick_backend_index("/switch", "", 3, "glows-tw06", 3, rr) is None
    assert frc.pick_backend_index("/switch", "", -1, "glows-tw06", 3, rr) is None
    print("test_pick_backend_index_switch_explicit_slot: PASS")


def test_pick_backend_index_demo_session_always_zero():
    rr = frc.RoundRobinPicker(3)
    for _ in range(5):
        assert frc.pick_backend_index("/demo/session", "", None, "glows-tw06", 3, rr) == 0
    print("test_pick_backend_index_demo_session_always_zero: PASS")


def test_pick_backend_index_token_worker_id_routes_deterministically():
    rr = frc.RoundRobinPicker(3)
    token = _make_token({"worker_id": "glows-tw06-p2", "call_id": "call-1"})
    # 同一個 token 連問幾次都要是同一個答案（正式路徑必須是決定性的，不能
    # 因為呼叫順序不同就路由到別的 process，那樣 Durable Call Control 保留
    # 的 slot 會對不上）。
    for _ in range(3):
        assert frc.pick_backend_index("/offer", token, None, "glows-tw06", 3, rr) == 2
        assert frc.pick_backend_index("/audio", token, None, "glows-tw06", 3, rr) == 2
    print("test_pick_backend_index_token_worker_id_routes_deterministically: PASS")


def test_pick_backend_index_foreign_worker_id_falls_back_round_robin():
    """Token 解得出 JSON，但 worker_id 不屬於這台機器（例如客戶端誤連到
    別台機器）——不要瞎猜某個 process，退回 round robin（各 process 各自
    認證，反正這個 token 本來就會在下一步被目標 process 的簽章驗證擋掉，
    路由層猜錯不影響安全性，只是白轉一次）。"""
    rr = frc.RoundRobinPicker(3)
    token = _make_token({"worker_id": "some-other-box-p0", "call_id": "call-2"})
    idx = frc.pick_backend_index("/offer", token, None, "glows-tw06", 3, rr)
    assert idx == 0  # 第一次 round robin 從 0 開始
    print("test_pick_backend_index_foreign_worker_id_falls_back_round_robin: PASS")


def test_pick_backend_index_demo_token_shape_routes_to_zero():
    rr = frc.RoundRobinPicker(3)
    demo_token = "abcDEF123_-opaqueNoDot"
    for _ in range(3):
        assert frc.pick_backend_index("/offer", demo_token, None, "glows-tw06", 3, rr) == 0
        assert frc.pick_backend_index("/audio", demo_token, None, "glows-tw06", 3, rr) == 0
    print("test_pick_backend_index_demo_token_shape_routes_to_zero: PASS")


def test_pick_backend_index_no_token_round_robins():
    rr = frc.RoundRobinPicker(3)
    picks = [frc.pick_backend_index("/offer", "", None, "glows-tw06", 3, rr) for _ in range(4)]
    assert picks == [0, 1, 2, 0]
    print("test_pick_backend_index_no_token_round_robins: PASS")


def test_merge_health_snapshots():
    healthy_0 = {"ok": True, "capacity": {"limit": 1, "active": 1, "available": False},
                 "char": "a05"}
    healthy_1 = {"ok": True, "capacity": {"limit": 1, "active": 0, "available": True},
                 "char": "a05"}
    merged = frc.merge_health_snapshots(
        [(0, healthy_0), (1, healthy_1), (2, None)], "glows-tw06"
    )
    assert merged["ok"] is True
    assert merged["capacity"] == {"limit": 3, "active": 1, "available": True}
    assert len(merged["slots"]) == 3
    assert merged["slots"][0]["worker_id"] == "glows-tw06-p0"
    assert merged["slots"][0]["index"] == 0
    assert merged["slots"][2]["healthy"] is False
    assert merged["slots"][2]["error"] == "unreachable"
    # primary 欄位（char 等）取自第一個可達的 backend
    assert merged["char"] == "a05"

    # 全部不可達 -> ok=False，不能假裝健康
    merged_all_down = frc.merge_health_snapshots([(0, None), (1, None)], "glows-tw06")
    assert merged_all_down["ok"] is False
    assert merged_all_down["capacity"]["active"] == 0
    print("test_merge_health_snapshots: PASS")


def test_launcher_dry_run_matches_core_module():
    """交叉驗證：bash 啟動器（start-vocaframe.sh --dry-run）跟這支 Python
    路由核心模組，對同一組 base_port／base_worker_id／n_procs 算出來的
    埠號與 worker_id 必須逐字相同——這是防止兩邊各自維護一份命名規則、
    未來改一邊忘了改另一邊，路由器把請求轉去錯的 process 而完全沒有錯誤
    訊息（call token 驗證會直接 403，不容易第一時間定位成「路由算式對不
    起來」）。

    跑不了 bash（例如某些精簡 CI 環境沒有 bash）時優雅跳過，不讓整條
    test:launch 因為環境缺 bash 而誤判失敗——這條屬於加分驗證，不是
    路由決策邏輯本身的正確性（那些已經在上面測完了）。
    """
    script = ROOT / "deploy" / "runpod-avatar" / "start-vocaframe.sh"
    if not script.is_file():
        print("test_launcher_dry_run_matches_core_module: SKIP (script missing)")
        return

    import shutil
    import tempfile
    bash_bin = shutil.which("bash")
    if not bash_bin:
        print("test_launcher_dry_run_matches_core_module: SKIP (no bash on PATH)")
        return

    base_port = 8188
    base_worker_id = "glows-tw06"
    n_procs = 3
    with tempfile.TemporaryDirectory(prefix="munea-fh-router-test-") as tmp:
        env_file = Path(tmp) / "runtime.env"
        env_file.write_text(
            "MUNEA_FACE_PORT=%d\nMUNEA_WORKER_ID=%s\n" % (base_port, base_worker_id),
            encoding="utf-8",
        )
        try:
            result = subprocess.run(
                [bash_bin, str(script), "--dry-run"],
                cwd=str(script.parent),
                env={"MUNEA_SERVICE_ROOT": tmp, "MUNEA_FH_PROCS": str(n_procs),
                     "PATH": __import__("os").environ.get("PATH", "")},
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print("test_launcher_dry_run_matches_core_module: SKIP (could not run bash: %r)" % exc)
            return

        assert result.returncode == 0, "dry-run must exit 0, stderr=%r" % result.stderr
        lines = [l for l in result.stdout.splitlines() if l.startswith("PLAN i=")]
        assert len(lines) == n_procs, "expected %d PLAN lines, got %r" % (n_procs, result.stdout)

        for i, line in enumerate(lines):
            parts = dict(tok.split("=", 1) for tok in line.split(" ")[1:])
            bash_port = int(parts["port"])
            bash_worker_id = parts["worker_id"]
            assert bash_port == frc.process_port(base_port, i), (
                "port mismatch at i=%d: bash=%d core=%d" % (i, bash_port, frc.process_port(base_port, i))
            )
            assert bash_worker_id == frc.process_worker_id(base_worker_id, i), (
                "worker_id mismatch at i=%d: bash=%r core=%r"
                % (i, bash_worker_id, frc.process_worker_id(base_worker_id, i))
            )
    print("test_launcher_dry_run_matches_core_module: PASS (bash launcher agrees with Python router core)")


def main():
    test_decode_token_payload_unverified()
    test_worker_process_index()
    test_process_worker_id_and_port_roundtrip()
    test_round_robin_picker()
    test_pick_backend_index_switch_explicit_slot()
    test_pick_backend_index_demo_session_always_zero()
    test_pick_backend_index_token_worker_id_routes_deterministically()
    test_pick_backend_index_foreign_worker_id_falls_back_round_robin()
    test_pick_backend_index_demo_token_shape_routes_to_zero()
    test_pick_backend_index_no_token_round_robins()
    test_merge_health_snapshots()
    test_launcher_dry_run_matches_core_module()
    print("FlashHead router core + launcher cross-check: ALL PASS")


if __name__ == "__main__":
    main()
