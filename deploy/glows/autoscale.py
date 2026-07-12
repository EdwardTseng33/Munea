# -*- coding: utf-8 -*-
"""沐寧 · Glows 自動開卡/查詢/退卡編排（2026-07-13 卡西法）

把 glowsctl.py 的 SDK 雛形串成一條「開卡 -> 起臉引擎 -> 驗健康 -> 交出門牌」的
完整流程，給 deploy/gateway/ 的閘道（WorkerRegistry）或未來的 monitor.py 呼叫。

這輪任務邊界：不真打 GLOWS API、不開真卡、不花錢（token 客服處理中）。程式要
寫好、mock 測過，token 一到就能真跑——見檔尾「token 到位後要做的事」清單。

流程（open_card）：
  1. glowsctl.create()（優先從快照開；兩區 TW-03/TW-04 fallback 已在 create() 內）
  2. 輪詢 glowsctl.get_status() 到 Running（含逾時）
  3. glowsctl.parse_access() 拿 SSH 埠 + HTTP 門牌
  4. SSH 進去跑 restart-flashhead.sh 起臉引擎（用 glows_ed25519，含重試——剛開機
     SSH daemon 可能還沒緒，屬正常瞬態）
  5. 輪詢 worker 的 /health 到 ready（body.ok is True）
  6. return {instance_id, ssh_host, ssh_port, http_url, region, ready_s}

任何一步失敗都會把半殘機器 release 掉再往外拋例外——不留著燒錢（GLOWS 是
DELETE-only、沒有 stop/pause，見 deploy/glows/README.md「已知眉角」）。
"""
import os
import subprocess
import time
import urllib.request

import glowsctl as gc

HERE = os.path.dirname(os.path.abspath(__file__))
SSH_KEY = os.path.join(HERE, "glows_ed25519")
RESTART_SCRIPT_REMOTE = "/root/restart-flashhead.sh"

# 逾時/輪詢預設值——都可在呼叫時覆蓋（mock 測試會用更短的值跑快一點）。
CREATE_TO_RUNNING_TIMEOUT_S = 240   # 估 1-3 分鐘 + 緩衝（見待實測清單第 1 項，仍是估的）
POLL_INTERVAL_S = 5
HEALTH_TIMEOUT_S = 60
SSH_ATTEMPTS = 5
SSH_RETRY_WAIT_S = 5


class OpenCardError(RuntimeError):
    """開卡流程任一步失敗都丟這個，訊息帶著失敗在哪一步，方便告警文案直接用。"""


def _now():
    return time.time()


def _ssh_run(ssh_host, ssh_port, remote_cmd, timeout=60):
    """跑一次 SSH 指令（真機用系統 ssh client；mock 測試整支被換掉，不真連機器）。"""
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
        "-i", SSH_KEY, "-p", str(ssh_port), "root@" + str(ssh_host), remote_cmd,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("ssh 指令失敗（exit " + str(proc.returncode) + "）: " + (proc.stderr or "")[:300])
    return proc.stdout


def _ssh_run_with_retry(ssh_host, ssh_port, remote_cmd, attempts=SSH_ATTEMPTS,
                         retry_wait_s=SSH_RETRY_WAIT_S, timeout=60):
    """剛開機 SSH daemon 可能還沒緒，屬正常瞬態——重試幾次再放棄。"""
    last_err = None
    for i in range(attempts):
        try:
            return _ssh_run(ssh_host, ssh_port, remote_cmd, timeout=timeout)
        except Exception as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(retry_wait_s)
    raise OpenCardError("SSH 重試 " + str(attempts) + " 次仍失敗：" + str(last_err))


def _http_get_json(url, timeout=10):
    """打一次 GET 拿 JSON（真機用 urllib；mock 測試整支被換掉，不真打網路）。"""
    import json as _json
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return _json.loads(r.read().decode("utf-8"))


def _safe_release(instance_id):
    """清理用：release 失敗只印一行、不再往外炸（避免清理過程本身又拋例外蓋掉
    原始錯誤，讓 Edward/告警看不到真正卡在哪一步）。"""
    try:
        gc.release(instance_id)
    except Exception as e:
        print("[autoscale] 清理失敗（release " + str(instance_id) +
              " 出錯，需要人工去主控台手動退）: " + str(e), flush=True)


def open_card(from_snapshot_id=None, regions=None,
              create_timeout_s=CREATE_TO_RUNNING_TIMEOUT_S,
              poll_interval_s=POLL_INTERVAL_S,
              ssh_attempts=SSH_ATTEMPTS, ssh_retry_wait_s=SSH_RETRY_WAIT_S,
              health_timeout_s=HEALTH_TIMEOUT_S):
    """開一張新卡、起臉引擎、驗 health、回傳門牌。失敗會清理（release）再往外拋。

    回傳：{"instance_id", "ssh_host", "ssh_port", "http_url", "region", "ready_s"}
    """
    t0 = _now()
    instance_id = None
    try:
        instance, region = gc.create(from_snapshot_id=from_snapshot_id, regions=regions)
        instance_id = instance.get("instanceID") or instance.get("instance_id")
        if not instance_id:
            raise OpenCardError("create 回應沒有 instanceID：" + str(instance))

        # ② 輪詢到 Running（含逾時）。create() 已經做過 TW-03/TW-04 兩區退避，
        # 這裡只管「開出來之後」等它真的跑起來。
        status = None
        deadline = _now() + create_timeout_s
        while _now() < deadline:
            status = gc.get_status(instance_id)
            state = str(status.get("status") or "").lower()
            if state == "running":
                break
            if state in ("failed", "error", "terminated", "released"):
                raise OpenCardError("instance " + instance_id + " 進入失敗狀態：" + state)
            time.sleep(poll_interval_s)
        else:
            raise OpenCardError("instance " + instance_id + " 等 Running 逾時（" +
                                 str(create_timeout_s) + "s）")

        # ③ 拿門牌
        access = gc.parse_access(status)
        ssh_host, ssh_port, http_url = access["ssh_host"], access["ssh_port"], access["http_url"]
        if not (ssh_host and ssh_port):
            raise OpenCardError("instance " + instance_id + " Running 但拿不到 SSH 門牌：" + str(access))

        # ④ SSH 進去起臉引擎（含重試）
        _ssh_run_with_retry(ssh_host, ssh_port, RESTART_SCRIPT_REMOTE,
                             attempts=ssh_attempts, retry_wait_s=ssh_retry_wait_s)

        # ⑤ 驗 /health 到 ready
        if not http_url:
            raise OpenCardError("instance " + instance_id + " 拿不到 HTTP 門牌，無法驗 health：" + str(access))
        health_deadline = _now() + health_timeout_s
        last_err = None
        ready = False
        while _now() < health_deadline:
            try:
                body = _http_get_json(http_url.rstrip("/") + "/health", timeout=10)
                if body.get("ok"):
                    ready = True
                    break
            except Exception as e:
                last_err = e
            time.sleep(poll_interval_s)
        if not ready:
            raise OpenCardError("instance " + instance_id + " 起了但 /health 一直沒綠燈（" +
                                 str(health_timeout_s) + "s）：" + str(last_err))

        # ⑥ 交出門牌
        return {
            "instance_id": instance_id,
            "ssh_host": ssh_host,
            "ssh_port": ssh_port,
            "http_url": http_url,
            "region": region,
            "ready_s": round(_now() - t0, 1),
        }
    except Exception:
        if instance_id:
            _safe_release(instance_id)
        raise


def close_card(instance_id):
    """退卡：release + 確認真的退掉了（list 裡查不到才算數，不是只看 release 呼叫
    有沒有丟例外——GLOWS 是 DELETE-only，退卡＝真的刪除整台）。"""
    gc.release(instance_id)
    remaining = [i for i in gc.list_instances()
                 if (i.get("instanceID") or i.get("instance_id")) == instance_id]
    return {"instance_id": instance_id, "released": True, "still_listed": bool(remaining)}


def list_cards():
    """現有機器 + 狀態 + 門牌，給閘道對帳用（形狀對照 gateway_core.WorkerRegistry.snapshot()）。"""
    out = []
    for i in gc.list_instances():
        access = gc.parse_access(i)
        out.append({
            "instance_id": i.get("instanceID") or i.get("instance_id"),
            "status": i.get("status"),
            "region": i.get("regionName") or i.get("region_name"),
            "http_url": access["http_url"],
            "ssh_host": access["ssh_host"],
            "ssh_port": access["ssh_port"],
        })
    return out


# ---------------------------------------------------------------------------
# 接 deploy/gateway/gateway_core.WorkerRegistry 的線——open_card() 開好卡後把
# 新門牌登記進 registry；close_card() 退卡後把它從 registry 移除。
#
# 刻意用鴨子定型（duck typing）接、不 import gateway_core：deploy/glows 跟
# deploy/gateway 是兩個各自獨立部署的服務（一個管 GPU 卡生死、一個是 CPU-only
# 控制面閘道），維持零耦合——呼叫端把自己的 WorkerRegistry 實例傳進來即可，
# 介面對齊 gateway_server.py 既有的 POST /v1/admin/worker/register 形狀
# （worker_id/url/slots/region/kind）。若 monitor.py 是另一個 process 在跑，
# 改成打 HTTP admin 端點即可，回傳形狀一樣。
# ---------------------------------------------------------------------------

def register_card_into_registry(registry, card, worker_id=None, slots=1):
    """card＝open_card() 或 list_cards() 其中一筆的回傳 dict。"""
    worker_id = worker_id or ("glows-" + str(card["instance_id"]))
    return registry.register(worker_id, card["http_url"], slots=slots,
                              region=card.get("region", ""), kind="glows")


def unregister_card_from_registry(registry, worker_id):
    registry.unregister(worker_id)
    return {"worker_id": worker_id, "unregistered": True}


if __name__ == "__main__":
    import sys as _sys
    _args = _sys.argv[1:]
    if not _args:
        print(__doc__)
    elif _args[0] == "open":
        print(open_card(from_snapshot_id=_args[1] if len(_args) > 1 else None))
    elif _args[0] == "close":
        print(close_card(_args[1]))
    elif _args[0] == "list":
        for _c in list_cards():
            print(_c)
    else:
        print(__doc__)
