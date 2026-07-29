# -*- coding: utf-8 -*-
"""回音濾網（2026-07-16 · 聊聊事故夜病歷 a 快藥）

問題：同線模式下她的聲音從手機喇叭出來、被麥克風收回去、又被當成用戶輸入
→ 自說自話／像被自己打斷。手機系統的回音消除顧不到我們這條播放路（根治
另案：把播放路接回系統顧得到的位置），先在伺服器端止血：

伺服器百分之百知道自己何時在出聲。規則＝「出聲窗內（最後一塊輸出後 tail 毫秒內）、
能量低於門檻的上行音訊＝自己的回音 → 丟棄」。使用者嘴對手機直說、音量天生比
喇叭漏音大好幾倍，正常音量就穿得過門檻＝插話照樣可用、不必取捨。

可調可關：MUNEA_VOICE_ECHO_GUARD（預設開）／MUNEA_VOICE_ECHO_GUARD_RMS
（預設 1150 · 7/16 首晚實戰：700 攔到 10-12 塊/通但大聲外放的漏音仍穿過＝幽靈插話，
調高一級）／MUNEA_VOICE_ECHO_GUARD_TAIL_MS（預設 2500 · 同線播放落後出聲可達 2 秒、
1500 蓋不滿她話尾的回音）。
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
    return _env_int("MUNEA_VOICE_ECHO_GUARD_RMS", 1150)


def guard_tail_ms():
    return _env_int("MUNEA_VOICE_ECHO_GUARD_TAIL_MS", 2500)


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
    """她正在出聲、或最後一塊輸出還在殘響窗內。

    ⚠ 已知結構性弱點（2026-07-29 抓到、由 note_playout/playout_window 補上）：
    last_out 是「伺服器送出」的時間，但 Gemini 送資料比真實講話快——一句 10 秒的話
    伺服器 2 秒就送完，手機卻要播 10 秒。只用 last_out+tail 當窗，句子後半段的回音
    全落在窗外 → 被當成用戶講話 → 她回答自己（Edward 7/29 點名的「自問自答」）。
    保留此函式當後備（playout track 沒起來時仍有基本保護）。"""
    if not last_out:
        return False
    tail_ms = guard_tail_ms() if tail_ms is None else tail_ms
    return (now - last_out) * 1000.0 <= tail_ms


def playout_lead_s():
    """手機端起播前的緩衝（秒）。同線模式實際 0.6-1.1 秒、本地播放 0.2-0.9 秒，
    取 0.8 當預設、可調。窗寧可略寬（真人聲靠音量門檻分辨，不靠窗）。"""
    try:
        return float(os.environ.get("MUNEA_VOICE_PLAYOUT_LEAD_S", "0.8"))
    except (TypeError, ValueError):
        return 0.8


def note_playout(playout_head, now, chunk_bytes, rate=24000, width=2):
    """伺服器每送一塊聲音就推進「手機大概播到哪」的水位（鏡射 App 端 _notePlayout）。

    回傳新的 playout_head（monotonic 秒）：
    - 水位落後現在（上一句早播完）→ 從 now+起播緩衝 重新起算
    - 否則直接往上疊這塊的真實播放長度
    """
    dur = (chunk_bytes / float(rate * width))
    base = playout_head if (playout_head and playout_head > now) else (now + playout_lead_s())
    return base + dur


def in_playout_window(now, playout_head, tail_ms=None):
    """回音窗 v2：以「手機大概播到哪」為準——她的聲音還在（或剛播完殘響未散）都算窗內。"""
    if not playout_head:
        return False
    tail_ms = guard_tail_ms() if tail_ms is None else tail_ms
    return now <= playout_head + tail_ms / 1000.0


def should_drop_uplink_frame(now, last_out, rms, enabled=None, tail_ms=None, threshold=None):
    """出聲窗內、低於門檻＝回音 → True（丟棄）；其餘一律放行。"""
    enabled = guard_enabled() if enabled is None else enabled
    if not enabled:
        return False
    if not in_output_window(now, last_out, tail_ms=tail_ms):
        return False
    threshold = guard_rms_threshold() if threshold is None else threshold
    return rms < threshold
