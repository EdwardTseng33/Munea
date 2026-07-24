# -*- coding: utf-8 -*-
"""RunPod 備援卡印象檔雙程序升級靜態/dry-run 驗證（2026-07-24 卡西法，
8-10人併發容量升級工程包1）。

不需要真 GPU、不需要真的開 RunPod 卡——只驗證：
1. Dockerfile.vocaframe 真的把 flashhead_router.py／flashhead_router_core.py
   烤進印象檔（否則 MUNEA_FH_PROCS>1 時開機會直接失敗，見 start-vocaframe.sh
   的檔案存在檢查）。
2. gpu-image/start-vocaframe.sh 的 --dry-run 輸出跟
   deploy/runpod-avatar/flashhead_router_core.py 的命名規則（process_port／
   process_worker_id）逐字一致——跟 scripts/test_flashhead_router_core.py 的
   test_launcher_dry_run_matches_core_module 同一種交叉驗證手法，只是這裡測
   的是 RunPod 版腳本（不依賴 runtime.env，直接吃環境變數）。
3. scripts/cloud-run-deploy-runpod-controller.ps1／
   deploy/runpod-avatar/runpod-backup.env.example 的容量參數已對齊「主卡2席
   + 備援4張x2席 = 10席」目標，且 SCALE_DOWN_ACTION 預設不再是會被 7/23
   實證推翻的 "stop"。

跑法：python scripts/test_runpod_gpu_image_dual_proc.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))
import flashhead_router_core as frc  # noqa: E402

DOCKERFILE = ROOT / "deploy" / "runpod-avatar" / "gpu-image" / "Dockerfile.vocaframe"
SCRIPT = ROOT / "deploy" / "runpod-avatar" / "gpu-image" / "start-vocaframe.sh"
DEPLOY_PS1 = ROOT / "scripts" / "cloud-run-deploy-runpod-controller.ps1"
ENV_EXAMPLE = ROOT / "deploy" / "runpod-avatar" / "runpod-backup.env.example"


def test_dockerfile_bakes_router_files():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "flashhead_router.py" in text
    assert "flashhead_router_core.py" in text
    assert "COPY gpu-image/start-vocaframe.sh /root/munea-service/start-vocaframe.sh" in text
    assert "EXPOSE 8188" in text
    assert 'CMD ["/root/munea-service/start-vocaframe.sh"]' in text
    assert "MUNEA_FH_IMAGE_BUILD" in text
    print("test_dockerfile_bakes_router_files: PASS")


def _run_dry_run(env_overrides):
    bash_bin = shutil.which("bash")
    if not bash_bin:
        return None
    import os
    env = {"PATH": os.environ.get("PATH", "")}
    env.update(env_overrides)
    result = subprocess.run(
        [bash_bin, str(SCRIPT), "--dry-run"],
        cwd=str(SCRIPT.parent),
        env=env,
        capture_output=True, text=True, timeout=15,
    )
    return result


def test_dry_run_default_is_two_procs():
    result = _run_dry_run({"MUNEA_WORKER_ID": "runpod-abc123"})
    if result is None:
        print("test_dry_run_default_is_two_procs: SKIP (no bash on PATH)")
        return
    assert result.returncode == 0, "dry-run must exit 0, stderr=%r" % result.stderr
    assert "PLAN mode=multi n_procs=2" in result.stdout
    lines = [l for l in result.stdout.splitlines() if l.startswith("PLAN i=")]
    assert len(lines) == 2, "default MUNEA_FH_PROCS must plan exactly 2 processes: %r" % result.stdout
    print("test_dry_run_default_is_two_procs: PASS")


def test_dry_run_matches_router_core_naming():
    base_port = 8188
    base_worker_id = "runpod-xyz789"
    n_procs = 3
    result = _run_dry_run({
        "MUNEA_WORKER_ID": base_worker_id,
        "MUNEA_FACE_PORT": str(base_port),
        "MUNEA_FH_PROCS": str(n_procs),
    })
    if result is None:
        print("test_dry_run_matches_router_core_naming: SKIP (no bash on PATH)")
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
    print("test_dry_run_matches_router_core_naming: PASS (bash launcher agrees with Python router core)")


def test_dry_run_single_process_fallback():
    result = _run_dry_run({"MUNEA_WORKER_ID": "runpod-single", "MUNEA_FH_PROCS": "1"})
    if result is None:
        print("test_dry_run_single_process_fallback: SKIP (no bash on PATH)")
        return
    assert result.returncode == 0, "dry-run must exit 0, stderr=%r" % result.stderr
    assert "PLAN mode=single port=8188 worker_id=runpod-single" in result.stdout
    print("test_dry_run_single_process_fallback: PASS")


def test_ps1_capacity_targets_ten_seats():
    text = DEPLOY_PS1.read_text(encoding="utf-8")
    assert '[int]$MaxPods = 4,' in text
    assert '[int]$TargetConcurrentCalls = 10,' in text
    assert 'MUNEA_RUNPOD_SCALE_DOWN_ACTION = "terminate"' in text
    assert 'MUNEA_RUNPOD_SCALE_DOWN_ACTION = "stop"' not in text, (
        "SCALE_DOWN_ACTION must never default back to stop -- 7/23 lesson: "
        "RunPod stop does not preserve the GPU, the paused pod can be taken by "
        "another renter"
    )
    print("test_ps1_capacity_targets_ten_seats: PASS")


def test_env_example_capacity_targets_ten_seats():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "MUNEA_RUNPOD_MAX_PODS=4" in text
    assert "MUNEA_TARGET_CONCURRENT_CALLS=10" in text
    assert "MUNEA_RUNPOD_SCALE_DOWN_ACTION=terminate" in text
    assert "MUNEA_RUNPOD_SCALE_DOWN_ACTION=stop" not in text
    print("test_env_example_capacity_targets_ten_seats: PASS")


def main():
    test_dockerfile_bakes_router_files()
    test_dry_run_default_is_two_procs()
    test_dry_run_matches_router_core_naming()
    test_dry_run_single_process_fallback()
    test_ps1_capacity_targets_ten_seats()
    test_env_example_capacity_targets_ten_seats()
    print("RunPod gpu-image dual-proc upgrade: ALL PASS")


if __name__ == "__main__":
    main()
