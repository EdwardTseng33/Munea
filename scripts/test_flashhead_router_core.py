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


def test_session_route_table_record_and_lookup():
    table = frc.SessionRouteTable(ttl_s=3600, max_entries=10)
    assert table.lookup("s1") is None  # 沒記錄過 -> None
    table.record("s1", 0)
    table.record("s2", 1)
    assert table.lookup("s1") == 0
    assert table.lookup("s2") == 1
    assert len(table) == 2
    # 空字串/None session_id 一律當沒有，不寫進表也不查得到什麼
    table.record("", 0)
    table.record(None, 1)
    assert len(table) == 2
    assert table.lookup("") is None
    assert table.lookup(None) is None
    print("test_session_route_table_record_and_lookup: PASS")


def test_session_route_table_ttl_expiry():
    """TTL 到期要真的失效（查不到、也要從內部字典清掉，不是永遠留著）。"""
    table = frc.SessionRouteTable(ttl_s=10.0, max_entries=10)
    clock = [1000.0]
    original_time = frc.time.time
    frc.time.time = lambda: clock[0]
    try:
        table.record("s1", 0)
        assert table.lookup("s1") == 0
        clock[0] = 1005.0  # 還在 TTL 內
        assert table.lookup("s1") == 0
        clock[0] = 1011.0  # 超過 10 秒 TTL
        assert table.lookup("s1") is None
        assert len(table) == 0, "expired entry must actually be purged, not just hidden"
    finally:
        frc.time.time = original_time
    print("test_session_route_table_ttl_expiry: PASS")


def test_session_route_table_max_entries_evicts_oldest():
    """超過上限時要淘汰最舊的一筆，不能無限長大（防漏水）。"""
    table = frc.SessionRouteTable(ttl_s=3600, max_entries=3)
    clock = [1000.0]
    original_time = frc.time.time
    frc.time.time = lambda: clock[0]
    try:
        table.record("s1", 0)
        clock[0] = 1001.0
        table.record("s2", 1)
        clock[0] = 1002.0
        table.record("s3", 0)
        assert len(table) == 3
        clock[0] = 1003.0
        table.record("s4", 1)  # 第 4 筆進來，s1（最舊）要被淘汰
        assert len(table) == 3
        assert table.lookup("s1") is None, "oldest entry must be evicted once over max_entries"
        assert table.lookup("s2") == 1
        assert table.lookup("s3") == 0
        assert table.lookup("s4") == 1
        # 更新既有 session（不是新增）不該觸發淘汰、也不該讓長度超過上限
        clock[0] = 1004.0
        table.record("s2", 1)
        assert len(table) == 3
        assert table.lookup("s2") == 1
        assert table.lookup("s3") == 0
        assert table.lookup("s4") == 1
    finally:
        frc.time.time = original_time
    print("test_session_route_table_max_entries_evicts_oldest: PASS")


def test_session_route_table_rejects_bad_config():
    for bad_ttl in (0, -1):
        try:
            frc.SessionRouteTable(ttl_s=bad_ttl)
        except ValueError:
            pass
        else:
            raise AssertionError("ttl_s<=0 must be rejected")
    for bad_max in (0, -1):
        try:
            frc.SessionRouteTable(max_entries=bad_max)
        except ValueError:
            pass
        else:
            raise AssertionError("max_entries<1 must be rejected")
    print("test_session_route_table_rejects_bad_config: PASS")


def test_pick_backend_index_session_priority_beats_token_and_round_robin():
    """2026-07-24 熱修的核心斷言：session 一旦記錄過，優先權蓋過 token 的
    worker_id、也蓋過 round robin，不管呼叫幾次都要回同一個 process。"""
    session_table = frc.SessionRouteTable()
    session_table.record("session-A", 1)
    rr = frc.RoundRobinPicker(3)

    # 完全沒有 token 的請求，一樣要靠 session 命中，不落到 round robin
    for _ in range(3):
        assert frc.pick_backend_index("/audio", "", None, "glows-tw06", 3, rr,
                                       session="session-A", session_table=session_table) == 1

    # 帶了一個指向別的 process 的 token，session 命中還是優先蓋過去
    foreign_token = _make_token({"worker_id": "glows-tw06-p2"})
    idx = frc.pick_backend_index("/audio", foreign_token, None, "glows-tw06", 3, rr,
                                  session="session-A", session_table=session_table)
    assert idx == 1, "session hit must win over token's worker_id"
    print("test_pick_backend_index_session_priority_beats_token_and_round_robin: PASS")


def test_pick_backend_index_session_miss_falls_back_to_existing_rules():
    session_table = frc.SessionRouteTable()
    rr = frc.RoundRobinPicker(3)
    # session 給了但表裡沒有 -> 照舊 fallback 到 round robin（不是報錯、
    # 不是 None）
    idx = frc.pick_backend_index("/audio", "", None, "glows-tw06", 3, rr,
                                  session="never-seen-before", session_table=session_table)
    assert idx == 0  # round robin 第一次從 0 開始
    print("test_pick_backend_index_session_miss_falls_back_to_existing_rules: PASS")


def test_two_backends_two_interleaved_sessions_each_route_home():
    """正式線 bug 的正面回歸測試：key= 萬用鑰匙（無 token）情境下，兩個
    session 各自在不同 backend 建立，之後用交錯順序打 /audio，每一次都必須
    準確回到各自的 home process，不能被 round robin 繼續往前轉而打散
    （這正是 2026-07-24 那個「A 房 offer、B 房 403」的失敗模式）。"""
    session_table = frc.SessionRouteTable()
    rr = frc.RoundRobinPicker(2)

    # 模擬兩通電話先後 /offer（key= 萬用鑰匙、完全沒有 worker_id 信號，
    # 路由器只能 round robin），並各自記錄 backend 回應帶回來的 session。
    home_a = frc.pick_backend_index("/offer", "", None, "glows-tw06", 2, rr)
    session_table.record("session-A", home_a)
    home_b = frc.pick_backend_index("/offer", "", None, "glows-tw06", 2, rr)
    session_table.record("session-B", home_b)
    assert home_a != home_b, (
        "round robin 的頭兩次分派必須落在不同 process 才重現得出原本的 bug 場景"
    )

    # 交錯呼叫 /audio 多輪，round robin 內部指標持續往前轉，但 session 查表
    # 必須每次都精準蓋過去，回各自的 home，不受 round robin 轉動影響。
    call_order = ["session-A", "session-B", "session-B", "session-A",
                  "session-A", "session-B", "session-A"]
    homes = {"session-A": home_a, "session-B": home_b}
    for sid in call_order:
        got = frc.pick_backend_index("/audio", "", None, "glows-tw06", 2, rr,
                                      session=sid, session_table=session_table)
        assert got == homes[sid], (
            "%s must always route home to backend %d, got %d (round robin leaked through)"
            % (sid, homes[sid], got)
        )

    # /switch 帶 session 一樣要吃查表優先（防呆：即使目前 flashhead_server.py
    # 的 /switch 還沒真的送 session 參數，路由器這邊要先接得住）。
    for sid in ("session-A", "session-B"):
        got = frc.pick_backend_index("/switch", "", None, "glows-tw06", 2, rr,
                                      session=sid, session_table=session_table)
        assert got == homes[sid]

    print("test_two_backends_two_interleaved_sessions_each_route_home: PASS "
          "(session-A always -> p%d, session-B always -> p%d, round robin never leaked through)"
          % (home_a, home_b))


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
    test_session_route_table_record_and_lookup()
    test_session_route_table_ttl_expiry()
    test_session_route_table_max_entries_evicts_oldest()
    test_session_route_table_rejects_bad_config()
    test_pick_backend_index_session_priority_beats_token_and_round_robin()
    test_pick_backend_index_session_miss_falls_back_to_existing_rules()
    test_two_backends_two_interleaved_sessions_each_route_home()
    test_merge_health_snapshots()
    test_launcher_dry_run_matches_core_module()
    print("FlashHead router core + launcher cross-check: ALL PASS")


if __name__ == "__main__":
    main()
