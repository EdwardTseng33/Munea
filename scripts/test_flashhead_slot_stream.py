# -*- coding: utf-8 -*-
"""FlashHead 每槽獨立 CUDA stream 單元測試（2026-07-23 卡西法，合批手術階段 1 / 方案 B）。

不需要真 GPU、不需要安裝 torch——跟 flashhead_engine_core.py 既有的零重依賴
慣例一致（見 scripts/test_flashhead_multislot.py 開頭說明），這裡用一個假的
torch 替身（FakeTorch）驗證 make_slot_stream_run_pipeline() 的排程邏輯：

  1. 開關預設值：env_flag_enabled()／Slot.cuda_stream 預設 None、
     flashhead_server.py 裡兩個新環境變數的預設字串沒有被意外改掉
     （相容性鐵律——沒開＝跟改動前一字不差）
  2. stream 分配邏輯：run_pipeline 真的在指定的 stream context 裡執行、
     結果透過 wait_stream()（非阻塞、非另一個 device-wide synchronize()）
     交回呼叫端目前的 stream，且回傳值原封不動傳出去
  3. 例外傳播：run_pipeline 出錯時，wrapper 不吞例外、也不繞過 with 區塊

跑法：python scripts/test_flashhead_slot_stream.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))

import flashhead_engine_core as fec  # noqa: E402


# ---------------------------------------------------------------------------
# 假 torch 替身：只實作 make_slot_stream_run_pipeline 用得到的三個介面
# (torch.cuda.stream(stream) context manager / torch.cuda.current_stream() /
# .wait_stream(stream))，並且把每一步呼叫順序記進 self.log，讓測試可以斷言
# 「先進 stream context、跑完 run_pipeline、離開 context，才呼叫
# wait_stream」這個順序沒有被寫反（寫反等於又變回一個變相的 device-wide
# barrier，等於白做這個階段的優化）。
# ---------------------------------------------------------------------------
class FakeStream:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "FakeStream(%r)" % self.name


class FakeStreamContext:
    def __init__(self, torch_mod, stream):
        self.torch_mod = torch_mod
        self.stream = stream

    def __enter__(self):
        self.torch_mod.log.append(("enter_stream", self.stream))
        self.torch_mod.current = self.stream
        return self.stream

    def __exit__(self, exc_type, exc, tb):
        self.torch_mod.log.append(("exit_stream", self.stream, exc_type))
        self.torch_mod.current = self.torch_mod.default_stream
        return False  # never swallow exceptions


class FakeCurrentStreamHandle:
    def __init__(self, torch_mod):
        self.torch_mod = torch_mod

    def wait_stream(self, stream):
        self.torch_mod.log.append(("wait_stream", self.torch_mod.current, stream))


class FakeCuda:
    def __init__(self, torch_mod):
        self.torch_mod = torch_mod

    def stream(self, stream):
        return FakeStreamContext(self.torch_mod, stream)

    def current_stream(self):
        return FakeCurrentStreamHandle(self.torch_mod)


class FakeTorch:
    """流程紀錄器 -- 不是真的 CUDA，只是可以被 make_slot_stream_run_pipeline
    當成 torch_module 注入、忠實記錄呼叫順序的替身。"""
    def __init__(self):
        self.default_stream = FakeStream("default")
        self.current = self.default_stream
        self.log = []
        self.cuda = FakeCuda(self)


def test_env_flag_enabled_contract():
    """MUNEA_FH_SLOT_STREAM/未來 MUNEA_FH_BATCHING 共用的預設關規則：
    只有字面完全等於 "1" 才算開，其他一律關（含 None/""/"0"/"true" 這種
    容易誤植但不該生效的值）。"""
    assert fec.env_flag_enabled("1") is True
    for off_value in (None, "0", "", "true", "yes", "TRUE", "01", " 1"):
        assert fec.env_flag_enabled(off_value) is False, (
            "env_flag_enabled(%r) must be False (default-off contract)" % (off_value,)
        )
    print("test_env_flag_enabled_contract: PASS")


def test_slot_cuda_stream_defaults_to_none():
    slot = fec.Slot(0)
    assert slot.cuda_stream is None, (
        "Slot.cuda_stream must default to None -- MUNEA_FH_SLOT_STREAM=0/unset "
        "must behave byte-for-byte like the pre-patch single default-stream setup"
    )
    print("test_slot_cuda_stream_defaults_to_none: PASS")


def test_make_slot_stream_run_pipeline_order_and_passthrough():
    torch_mod = FakeTorch()
    my_stream = FakeStream("slot0")
    calls = []

    def fake_run_pipeline(pipeline, audio_embedding):
        # 呼叫的當下，目前 stream 必須已經是這個槽專屬的 stream（不是 default）
        assert torch_mod.current is my_stream, (
            "run_pipeline body must execute while the slot's own stream is current, got %r"
            % torch_mod.current
        )
        calls.append((pipeline, audio_embedding))
        return "FAKE_VIDEO_TENSOR"

    wrapped = fec.make_slot_stream_run_pipeline(fake_run_pipeline, my_stream, torch_mod)
    result = wrapped("fake-pipeline-obj", "fake-audio-embedding")

    assert result == "FAKE_VIDEO_TENSOR", "wrapper must pass the return value through unchanged"
    assert calls == [("fake-pipeline-obj", "fake-audio-embedding")], (
        "wrapper must call run_pipeline exactly once with the exact same args"
    )

    # 順序必須是：進 stream context -> 真的呼叫 run_pipeline（在上面 assert 過了）
    # -> 離開 stream context -> 呼叫 current_stream().wait_stream(my_stream)。
    kinds = [entry[0] for entry in torch_mod.log]
    assert kinds == ["enter_stream", "exit_stream", "wait_stream"], (
        "expected enter -> exit -> wait_stream order, got %r" % kinds
    )
    enter_stream = torch_mod.log[0][1]
    exit_stream = torch_mod.log[1][1]
    _, waiter_stream, waited_on_stream = torch_mod.log[2]
    assert enter_stream is my_stream and exit_stream is my_stream
    assert waited_on_stream is my_stream, "must wait on the slot's own stream"
    assert waiter_stream is torch_mod.default_stream, (
        "wait_stream must be issued from the caller's current stream (back to "
        "default after exiting the slot stream context), not from inside the "
        "slot stream itself"
    )
    assert not any("synchronize" in str(entry) for entry in torch_mod.log), (
        "wrapper must never reintroduce a device-wide synchronize() call"
    )
    print("test_make_slot_stream_run_pipeline_order_and_passthrough: PASS")


def test_make_slot_stream_run_pipeline_propagates_exceptions():
    torch_mod = FakeTorch()
    my_stream = FakeStream("slot1")

    def broken_run_pipeline(pipeline, audio_embedding):
        raise RuntimeError("simulated GPU fault")

    wrapped = fec.make_slot_stream_run_pipeline(broken_run_pipeline, my_stream, torch_mod)
    try:
        wrapped("pipeline", "emb")
    except RuntimeError as exc:
        assert "simulated GPU fault" in str(exc)
    else:
        raise AssertionError("wrapper must not swallow exceptions from run_pipeline")

    kinds = [entry[0] for entry in torch_mod.log]
    assert kinds == ["enter_stream", "exit_stream"], (
        "exception path must still exit the stream context, but must not call "
        "wait_stream (nothing to hand off): got %r" % kinds
    )
    assert torch_mod.current is torch_mod.default_stream, (
        "current stream must be restored to default even when run_pipeline raises"
    )
    print("test_make_slot_stream_run_pipeline_propagates_exceptions: PASS")


def test_flashhead_server_default_flag_values_unchanged():
    """相容性鐵律的靜態守門：flashhead_server.py 裡兩個新開關的預設字串
    (MUNEA_FH_SLOT_STREAM 預設關、MUNEA_FH_PROFILE_SYNC 預設開) 不能被未來
    的改動悄悄調換方向——調換方向等於現行行為在沒人明確選擇的情況下改變，
    直接違反設計文件第 3 節相容性鐵律。用原始碼文字檢查是因為這個檔案
    import torch/fastapi/aiortc，本機沒裝這些重依賴時沒辦法直接 import 它。"""
    server_path = ROOT / "deploy" / "runpod-avatar" / "flashhead_server.py"
    text = server_path.read_text(encoding="utf-8")

    slot_stream_line = 'SLOT_STREAM = env_flag_enabled(os.environ.get("MUNEA_FH_SLOT_STREAM", "0"))'
    profile_sync_line = '_fhp_mod.PROFILE_SYNC = os.environ.get("MUNEA_FH_PROFILE_SYNC", "1") == "1"'
    assert slot_stream_line in text, "MUNEA_FH_SLOT_STREAM default must stay off (\"0\")"
    assert profile_sync_line in text, "MUNEA_FH_PROFILE_SYNC default must stay on (\"1\")"
    print("test_flashhead_server_default_flag_values_unchanged: PASS")


def main():
    test_env_flag_enabled_contract()
    test_slot_cuda_stream_defaults_to_none()
    test_make_slot_stream_run_pipeline_order_and_passthrough()
    test_make_slot_stream_run_pipeline_propagates_exceptions()
    test_flashhead_server_default_flag_values_unchanged()
    print("FlashHead slot-stream unit test: ALL PASS")


if __name__ == "__main__":
    main()
