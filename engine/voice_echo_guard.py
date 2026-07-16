# -*- coding: utf-8 -*-
"""回音濾網（2026-07-16 · 聊聊事故夜病歷 a 快藥）

問題：同線模式下她的聲音從手機喇叭出來、被麥克風收回去、又被當成用戶輸入
→ 自說自話／像被自己打斷。手機系統的回音消除顧不到我們這條播放路（根治
另案：把播放路接回系統顧得到的位置），先在伺服器端止血：

伺服器百分之百知道自己何時在出聲。規則＝「出聲窗內（最後一塊輸出後 tail 毫秒內）、
能量低於門檻的上行音訊＝自己的回音 → 丟棄」。使用者嘴對手機直說、音量天生比
喇叭漏音大好幾倍，正常音量就穿得過門檻＝插話照樣可用、不必取捨。

可調可關：MUNEA_VOICE_ECHO_GUARD（預設開）／MUNEA_VOICE_ECHO_GUARD_RMS
（預設 700、跟開場人聲偵測同一把尺）／MUNEA_VOICE_ECHO_GUARD_TAIL_MS（預設 1500，
蓋住同線播放落後伺服器出聲約 1 秒的殘響窗）。
"""
import os

try:
    import audioop  # C 實作、快；Python 3.13 起移除，屆時走下面的純 Python 後備
except Exception:  # pragma: no cover
    audioop = None


def _env_flag(name, default="1"):
    return os.environ.get(name, default).strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name, default):
    try:
        return int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def guard_enabled():
    return _env_flag("MUNEA_VOICE_ECHO_GUARD", "1")


def guard_rms_threshold():
    return _env_int("MUNEA_VOICE_ECHO_GUARD_RMS", 700)


def guard_tail_ms():
    return _env_int("MUNEA_VOICE_ECHO_GUARD_TAIL_MS", 1500)


def frame_rms(frame):
    """16-bit PCM 音量。壞資料回 0（寧可放行、不誤丟真人聲）。"""
    if not frame:
        return 0.0
    try:
        if audioop is not None:
            return float(audioop.rms(bytes(frame), 2))
        samples = memoryview(frame).cast("h")
        if not samples:
            return 0.0
        return (sum(int(v) * int(v) for v in samples) / len(samples)) ** 0.5
    except Exception:
        return 0.0


def in_output_window(now, last_out, tail_ms=None):
    """她正在出聲、或最後一塊輸出還在殘響窗內。"""
    if not last_out:
        return False
    tail_ms = guard_tail_ms() if tail_ms is None else tail_ms
    return (now - last_out) * 1000.0 <= tail_ms


def should_drop_uplink_frame(now, last_out, rms, enabled=None, tail_ms=None, threshold=None):
    """出聲窗內、低於門檻＝回音 → True（丟棄）；其餘一律放行。"""
    enabled = guard_enabled() if enabled is None else enabled
    if not enabled:
        return False
    if not in_output_window(now, last_out, tail_ms=tail_ms):
        return False
    threshold = guard_rms_threshold() if threshold is None else threshold
    return rms < threshold
