# -*- coding: utf-8 -*-
"""Munea「聊聊」分流閘道 · 核心邏輯層（2026-07-12 卡西法）

照 docs/多人併發容量架構-2026-07-12.md §2 + §5 施工：控制面（登記/配對/釋放/排隊決策）
跟媒體面（WebRTC）完全分開——這支檔案只做控制面決策，媒體流永遠是 App 與 worker
（flashhead_server.py）直連，不繞這裡。

方案選型（§2.2）：這輪照方案 B（自建閘道）的形狀寫——client 直連指定 worker，affinity
天生成立，不賭 Modal 平台未驗證的 session affinity 行為。方案 A（Modal 原生池）要先做
真卡 PoC 才能定案（§2.2 明講），這輪不碰真卡，介面留著、未來要換不必重寫呼叫端。

**刻意設計：零外部依賴**（不 import fastapi）——這樣本機不裝 fastapi/uvicorn 也能把
「聯合准入 min 邏輯」「fullest-first 配對」「FIFO 排隊 + 離線跳過遞補」這些容易出錯的
邏輯用單元測試攔在部署前（見 scripts/test_gateway.py）。gateway_server.py 是薄薄一層
FastAPI 外殼、接這裡的方法。
"""
import collections
import time


class GPUWorker:
    """一台已登記的顯卡 worker（RunPod pod / Glows instance / Modal container 都能登記）。
    slots 對應該台機器上 flashhead_server.py 的 MUNEA_FH_SLOTS 設定——閘道跟 worker
    各自維護一份帳本，active 由 /health 輪詢或事件回報更新（見 CLIENT-INTERFACE.md）。
    """
    def __init__(self, worker_id, url, slots=1, region="", kind="manual"):
        self.worker_id = worker_id
        self.url = url
        self.slots = slots
        self.active = 0
        self.region = region
        self.kind = kind          # manual | runpod | glows | modal
        self.healthy = True
        self.last_health_ts = 0.0
        self.enabled = True       # 手動下線用（維護模式）

    def free_slots(self):
        if not (self.healthy and self.enabled):
            return 0
        return max(0, self.slots - self.active)

    def load_ratio(self):
        return (self.active / self.slots) if self.slots else 1.0


class WorkerRegistry:
    """顯卡 worker 登記簿 + fullest-first 配對（§2.3）。"""
    def __init__(self):
        self._workers = {}

    def register(self, worker_id, url, slots=1, region="", kind="manual"):
        w = GPUWorker(worker_id, url, slots=slots, region=region, kind=kind)
        self._workers[worker_id] = w
        return w

    def unregister(self, worker_id):
        self._workers.pop(worker_id, None)

    def get(self, worker_id):
        return self._workers.get(worker_id)

    def mark_health(self, worker_id, healthy, active=None):
        w = self._workers.get(worker_id)
        if not w:
            return False
        w.healthy = healthy
        w.last_health_ts = time.time()
        if active is not None:
            w.active = active
        return True

    def set_enabled(self, worker_id, enabled):
        w = self._workers.get(worker_id)
        if w:
            w.enabled = enabled
            return True
        return False

    def total_free(self):
        return sum(w.free_slots() for w in self._workers.values())

    def total_capacity(self):
        return sum(w.slots for w in self._workers.values() if w.healthy and w.enabled)

    def pick_fullest_first(self):
        """§2.3 fullest-first bin packing：優先塞進「已經有人在用、還有空槽」的卡，
        而非空的新卡；讓部分卡盡量填滿、其餘卡盡量閒置好被 scale-to-zero 回收。
        全部都是空卡時（沒人在用任何一台），任一台皆可、取第一個（順序穩定即可，
        不影響正確性——這種情況通常也代表最需要開機的第一波流量）。
        """
        candidates = [w for w in self._workers.values() if w.free_slots() > 0]
        if not candidates:
            return None
        used = [w for w in candidates if w.active > 0]
        pool = used if used else candidates
        return max(pool, key=lambda w: w.load_ratio())

    def burst_threshold_hit(self, threshold=0.8):
        """§2.3 burst 開卡門檻：池使用率 > threshold 就該預開下一台
        （這裡只回報訊號，真的呼叫開卡 API 是 gateway_server.py 或維運腳本的事）。"""
        cap = self.total_capacity()
        if cap == 0:
            return True
        used = sum(w.active for w in self._workers.values() if w.healthy and w.enabled)
        return (used / cap) > threshold

    def snapshot(self):
        return {
            "workers": [
                {"worker_id": w.worker_id, "url": w.url, "slots": w.slots, "active": w.active,
                 "healthy": w.healthy, "enabled": w.enabled, "region": w.region, "kind": w.kind}
                for w in self._workers.values()
            ],
            "total_capacity": self.total_capacity(),
            "total_free": self.total_free(),
        }


class VoicePool:
    """語音池空位（§2.3 聯合准入用）。首波先用一個簡單上限數字（6.3 節純語音壓測
    結果回填，還沒做那次壓測前，limit 先用保守值撐著）。之後若語音層真的多 GCP
    專案/多金鑰 sharding，可以把 set_active 換成多來源加總，介面不用變。"""
    def __init__(self, limit):
        self.limit = limit
        self.active = 0

    def free(self):
        return max(0, self.limit - self.active)

    def set_active(self, n):
        self.active = max(0, n)


class QueueEntry:
    def __init__(self, client_id):
        self.client_id = client_id
        self.enqueued_ts = time.time()
        self.online = True


class CallQueue:
    """§5.2 FIFO 排隊。等待時間預估＝近期滾動平均通話時長 × 排隊位置——不用精確保證，
    目的只是不讓人乾等沒訊息。佇列已滿＝唯一保留的真拒絕出口（§5.2 第4點）。"""
    def __init__(self, max_depth=20, avg_call_s_default=120.0):
        self.max_depth = max_depth
        self._q = collections.deque()
        self._by_client = {}
        self._recent_call_s = collections.deque(maxlen=30)
        self._avg_default = avg_call_s_default

    def record_call_duration(self, seconds):
        if seconds and seconds > 0:
            self._recent_call_s.append(seconds)

    def _avg_call_s(self):
        if not self._recent_call_s:
            return self._avg_default
        return sum(self._recent_call_s) / len(self._recent_call_s)

    def enqueue(self, client_id):
        if client_id in self._by_client:
            return self.status(client_id)
        if len(self._q) >= self.max_depth:
            return None  # 佇列滿，唯一真拒絕出口
        entry = QueueEntry(client_id)
        self._q.append(entry)
        self._by_client[client_id] = entry
        return self.status(client_id)

    def status(self, client_id):
        entry = self._by_client.get(client_id)
        if not entry:
            return None
        try:
            position = list(self._q).index(entry) + 1
        except ValueError:
            return None
        eta_s = round(position * self._avg_call_s(), 1)
        return {"position": position, "eta_s": eta_s, "depth": len(self._q)}

    def heartbeat(self, client_id):
        entry = self._by_client.get(client_id)
        if entry:
            entry.online = True
            return True
        return False

    def mark_offline(self, client_id):
        entry = self._by_client.get(client_id)
        if entry:
            entry.online = False

    def cancel(self, client_id):
        entry = self._by_client.pop(client_id, None)
        if entry:
            try:
                self._q.remove(entry)
            except ValueError:
                pass
            return True
        return False

    def pop_next_online(self):
        """有空位釋出時呼叫：依序 FIFO pop，離線者跳過並遞補下一位。"""
        while self._q:
            entry = self._q.popleft()
            self._by_client.pop(entry.client_id, None)
            if entry.online:
                return entry.client_id
        return None

    def depth(self):
        return len(self._q)


class Gateway:
    """整合：聯合准入（GPU∩語音）→ 有空位直配、沒空位進佇列（§2.3 + §5.2 + §5.4 決策樹）。

    request_call() 對應「按下撥通」；poll() 對應排隊中的心跳/輪詢；release_call()
    對應通話結束的 worker webhook（釋放槽位 + 記錄時長回饋 ETA 估算 + 嘗試把佇列往前推）。
    """
    def __init__(self, workers=None, voice=None, queue=None):
        self.workers = workers or WorkerRegistry()
        self.voice = voice or VoicePool(limit=5)
        self.queue = queue or CallQueue()
        self._assignments = {}   # client_id -> worker_id（已配對、等 client 去連的席位）

    def joint_free(self):
        """§2.3 聯合准入：min(顯卡池空位, 語音池空位)——不是只看顯卡，語音天花板
        現在比顯卡池小很多，兩者沒一起判斷，顯卡有空位也沒用、聲音接不上。"""
        return min(self.workers.total_free(), self.voice.free())

    def _connect_response(self, client_id):
        worker_id = self._assignments.get(client_id)
        w = self.workers.get(worker_id) if worker_id else None
        if w is None:
            self._assignments.pop(client_id, None)
            return None
        return {"status": "connect", "worker": {"worker_id": w.worker_id, "url": w.url}}

    def request_call(self, client_id):
        """§5.4 決策樹入口：已經配對過（重複請求）→ 回同一台；有空位 → 直接配 worker
        （樂觀佔位，避免下一輪重複配到同一台）；沒空位 → 進佇列；佇列滿 → 明確拒絕。
        """
        existing = self._connect_response(client_id)
        if existing is not None:
            return existing
        if self.joint_free() > 0:
            worker = self.workers.pick_fullest_first()
            if worker is not None:
                worker.active += 1
                self._assignments[client_id] = worker.worker_id
                return self._connect_response(client_id)
            # 語音有空位但顯卡臨時被搶走（競態）——退而求其次進佇列，不假裝成功
        return self._enqueue_or_reject(client_id)

    def _enqueue_or_reject(self, client_id):
        q = self.queue.enqueue(client_id)
        if q is None:
            return {"status": "reject", "reason": "queue_full"}
        return {"status": "queued", "queue": q}

    def poll(self, client_id):
        """排隊中 client 的心跳/輪詢：同時當心跳用（回報還在線），也回目前狀態。"""
        connect = self._connect_response(client_id)
        if connect is not None:
            return connect
        if self.queue.heartbeat(client_id):
            return {"status": "queued", "queue": self.queue.status(client_id)}
        return {"status": "unknown"}

    def cancel_call(self, client_id):
        """使用者主動取消：排隊中直接移除；已配對但還沒連上也一併放棄
        （這種情況呼叫端應同時打 /call/release 讓 worker 那格空出來，這裡只清帳本）。
        """
        cancelled_queue = self.queue.cancel(client_id)
        worker_id = self._assignments.pop(client_id, None)
        return {"cancelled_queue": cancelled_queue, "cancelled_assignment": worker_id is not None}

    def release_call(self, worker_id, duration_s=None):
        """通話結束 webhook：釋放 worker 一個槽 + 記錄時長（回饋 ETA 估算）+
        嘗試把佇列往前推一位。回傳被推進的配對結果（或 None）。"""
        w = self.workers.get(worker_id)
        if w is not None:
            w.active = max(0, w.active - 1)
        if duration_s:
            self.queue.record_call_duration(duration_s)
        return self.try_advance_queue()

    def try_advance_queue(self):
        """有空位就把佇列最前面的線上使用者接上（§5.2 第2點：有空位釋出時，依序
        FIFO pop，若該 client 仍在線→直接觸發連線；離線→跳過遞補下一位）。"""
        while self.joint_free() > 0:
            client_id = self.queue.pop_next_online()
            if client_id is None:
                return None
            worker = self.workers.pick_fullest_first()
            if worker is None:
                # 顯卡池瞬間沒位了（跟語音池數字不同步的競態）——把人放回佇列最前面
                # 而不是憑空丟掉，下一次 release_call/try_advance_queue 再試
                self.queue._q.appendleft(QueueEntry(client_id))
                self.queue._by_client[client_id] = self.queue._q[0]
                return None
            worker.active += 1
            self._assignments[client_id] = worker.worker_id
            return {"client_id": client_id, "worker": {"worker_id": worker.worker_id, "url": worker.url}}
        return None

    def snapshot(self):
        return {
            "joint_free": self.joint_free(),
            "workers": self.workers.snapshot(),
            "voice": {"limit": self.voice.limit, "active": self.voice.active, "free": self.voice.free()},
            "queue_depth": self.queue.depth(),
        }
