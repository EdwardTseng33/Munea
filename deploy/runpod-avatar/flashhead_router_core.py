# -*- coding: utf-8 -*-
"""Munea FlashHead 多程序分流核心邏輯（2026-07-23 卡西法，合批手術階段 2）。

背景（今晚同卡 A/B 實測，見 docs/研究文件）：3 條 thread 在同一 process 內
共用 1 個 GIL，才是「3 路變超慢」的真正病灶（不是階段 1 猜測的 CUDA sync
屏障——那條路已經量過、無效）。3 個獨立 OS process（各自 1 個 GIL）p95
1183ms，比 3 thread 版 1920ms 快 1.6 倍、GPU 才真的吃到 100%/412W。

這支檔案只放「純路由決策邏輯」，零重依賴（跟 flashhead_engine_core.py 同一種
設計哲學——不 import aiohttp，讓決策邏輯本身可以完全離線單元測試）。真正把
決策接上網路轉發的是同目錄的 flashhead_router.py。

路由決策表（pick_backend_index 完整規則，對應設計書「對外門牌問題」章節）：

| 情境 | 依據 | 路由到 |
|---|---|---|
| POST /switch，帶明確 slot 參數 | 既有 0-based slot 參數（既有 admin 工具慣例，原樣保留） | index = slot |
| POST /demo/session | 無 token 可讀，demo token 固定在 process 0 記憶體裡核發 | index = 0（固定） |
| **有 session 參數、且 session 之前在 /offer 記錄過** | **2026-07-24 熱修：/offer 回應的 backend 若已記錄過這個 session，後續呼叫一律回那個 backend——優先權最高，蓋過 token/round robin** | **index = 記錄值（固定）** |
| 帶 token，token 可解出 JSON payload、payload.worker_id 符合本機 "-pN" 格式 | Durable Call Control 核發的正式 token（見 flashhead_server.py _decode_call_token） | index = N |
| 帶 token，但解不出 "." 分隔（demo token 是不透明亂數字串，沒有 "."） | demo token 的形狀特徵——demo token 只在 process 0 核發、驗證，必須固定路由到同一台 | index = 0（固定） |
| 帶 token，JSON 解得出來但 worker_id 對不上本機任何一個 "-pN" | 可能是別台機器核發的 token（誤連） | 保守退回 round robin，不猜 0 |
| 完全沒帶 token（MUNEA_ALLOW_LEGACY_APP_KEY 舊版 App 相容路） | 沒有任何路由信號 | round robin（各 process 各自認證，滿了各自回 429，跟現行行為一致） |

**故意不驗證 token 簽章**：這裡只是「偷看」token payload 裡的 worker_id 欄位
做路由決策，不驗證 HMAC、不需要密鑰——真正的權限驗證（簽章、過期時間、
worker_id 綁定）維持在被路由到的那個 flashhead_server process 裡各自做一次，
跟今天完全一樣，這支檔案的誤判/被偽造頂多路由錯 process（下一步驗證會失敗、
回 403），不會弱化任何安全性。

**2026-07-24 正式線上線後抓到的真 bug（session 黏性）**：key= 萬用鑰匙／任何
無 token 或 token 對不上本機 worker_id 的請求，走的是 round robin——`/offer` 分到
A 房建立 session，緊接著的 `/audio?session=X` 完全沒有路由信號可以決定性地推回
A 房，round robin 繼續往前轉、把它送去 B 房，B 房沒見過這個 session，403。
**token 正式路徑（Durable Call Control）不受影響**——那條本來就是靠 token 裡的
worker_id 決定性路由，跟 round robin 無關；受影響的只有走 key= 萬用鑰匙的驗收
工具與任何純 key-auth 客戶端（真實通話正常）。

修法：`SessionRouteTable`（見下）在 `/offer` 成功回應後記下
`session_id -> backend_index`，`/audio`／`/switch` 帶 `session` 參數時**優先**查這張表
（蓋過 token/round robin），查無才照舊 fallback。TTL + 上限雙重防漏水——
router 是長駐 process，這張表不能無限長大。
"""
import base64
import json
import time


def decode_token_payload_unverified(token):
    """偷看 call token 的 JSON payload、不驗證 HMAC 簽章（純路由用途）。

    對應 flashhead_server.py 的 _decode_call_token 前半段（base64 decode +
    json.loads），但省略後半段的 hmac.compare_digest 簽章驗證——那段驗證
    留給真正收到請求的 backend process 自己做，這支只是「猜猜看要轉去哪」。

    回傳 None 的情況：token 是空字串／沒有 "."（demo token 的不透明亂數
    字串、或任何非結構化字串）／base64 或 json 解碼失敗／解出來不是 dict。
    呼叫端看到 None 要自己決定退回哪種預設路由（demo 或 round robin），
    這支函式本身不做這個判斷。
    """
    if not token or "." not in token:
        return None
    encoded = token.split(".", 1)[0]
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def worker_process_index(worker_id, base_worker_id, n_procs):
    """"<base>-pN" -> N（限 0 <= N < n_procs），格式或範圍不符一律 None。"""
    if not worker_id or not base_worker_id:
        return None
    prefix = base_worker_id + "-p"
    if not worker_id.startswith(prefix):
        return None
    suffix = worker_id[len(prefix):]
    if not suffix.isdigit():
        return None
    idx = int(suffix)
    return idx if 0 <= idx < n_procs else None


def process_worker_id(base_worker_id, index):
    """跟 worker_process_index 互為反函式——啟動器與路由器共用同一條命名
    規則，兩邊各自算出來的字串必須逐字相同，否則路由表對不起來。"""
    return "%s-p%d" % (base_worker_id, index)


def process_port(base_port, index):
    """跟 process_worker_id 同一份共用規則：backend process 內部埠號 =
    base_port + 1 + index（router 自己保留 base_port 這個對外門牌）。"""
    return base_port + 1 + index


class RoundRobinPicker:
    """給「完全沒有路由信號」的請求（多半是舊版 App 走 legacy 免 token 相容
    路）用的保底分流——不是真正的負載感知，純粹輪流送出去，各 process 各自
    認證／各自在滿載時回 429（跟現行單一 process 的 429 語意一致，只是現在
    409 決策點提前到路由層做輪替，不是完全信任 gateway 端的 lease 分配）。
    """
    def __init__(self, n_procs):
        if n_procs < 1:
            raise ValueError("n_procs must be >= 1")
        self.n_procs = n_procs
        self._next = 0

    def pick(self):
        idx = self._next % self.n_procs
        self._next += 1
        return idx


class SessionRouteTable:
    """/offer 建立的 session_id -> backend index 對照表（2026-07-24 熱修）。

    backend process 之間完全不共享 in-memory 狀態（各自獨立 SlotPool），
    同一個 session 中途被路由到不同 process 就是 403 的根源——這張表就是
    「session 一旦落地某個 backend，後續呼叫一律回那個 backend」的唯一真相
    來源，供 pick_backend_index() 在算 token/round robin 之前優先查。

    TTL + 上限雙重防漏水：record() 每次呼叫都先清過期項，超過上限再淘汰
    最舊的一筆——router 是長駐 process，若 session 從沒收到明確的結束訊號
    （目前 WS 斷線只在 flashhead_router.py 那層關閉連線，不會主動來通知
    這張表清掉），只能靠 TTL 兜底，避免這個 dict 無限長大。
    """
    def __init__(self, ttl_s=3600.0, max_entries=500):
        if ttl_s <= 0:
            raise ValueError("ttl_s must be > 0")
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._table = {}  # session_id -> (index, recorded_at)

    def record(self, session_id, index):
        if not session_id:
            return
        now = time.time()
        self._purge_expired(now)
        if session_id not in self._table and len(self._table) >= self.max_entries:
            self._evict_oldest()
        self._table[session_id] = (index, now)

    def lookup(self, session_id):
        if not session_id:
            return None
        entry = self._table.get(session_id)
        if entry is None:
            return None
        index, recorded_at = entry
        if time.time() - recorded_at > self.ttl_s:
            self._table.pop(session_id, None)
            return None
        return index

    def _purge_expired(self, now):
        expired = [sid for sid, (_, ts) in self._table.items() if now - ts > self.ttl_s]
        for sid in expired:
            self._table.pop(sid, None)

    def _evict_oldest(self):
        if not self._table:
            return
        oldest_sid = min(self._table.items(), key=lambda kv: kv[1][1])[0]
        self._table.pop(oldest_sid, None)

    def __len__(self):
        return len(self._table)


def pick_backend_index(path, token, explicit_slot, base_worker_id, n_procs, round_robin,
                        session=None, session_table=None):
    """核心路由決策——見檔頭決策表。純函式（round_robin/session_table 兩個
    参数是唯一帶狀態的部分，狀態由呼叫端持有、注入進來，方便測試用固定/假的
    picker/table）。

    session/session_table 優先權最高（2026-07-24 熱修，見 SessionRouteTable
    文件）：只要這個 session 之前記錄過，不管 token/worker_id 講什麼，一律
    回當初真正建立 session 的那個 process；查無才落回下面既有規則。
    """
    if session and session_table is not None:
        idx = session_table.lookup(session)
        if idx is not None:
            return idx

    if path == "/switch" and explicit_slot is not None:
        return explicit_slot if 0 <= explicit_slot < n_procs else None

    if path == "/demo/session":
        return 0

    if token:
        payload = decode_token_payload_unverified(token)
        if payload is not None:
            idx = worker_process_index(payload.get("worker_id"), base_worker_id, n_procs)
            if idx is not None:
                return idx
            # JSON 解得出來但 worker_id 對不上本機任何一個 process -- 可能是
            # 別台機器核發的 token 誤連，不要猜 0，退回 round robin。
        else:
            # 沒有 "." 分隔 -- demo token 的形狀特徵，固定回 process 0
            # （demo token 只在那台 process 的記憶體裡核發／驗證過）。
            return 0

    return round_robin.pick()


def merge_health_snapshots(indexed_snapshots, base_worker_id):
    """把 N 個 backend 各自的 /health JSON 併成一份聚合視圖，形狀比照現行
    單一 process N 槽版 /health 的 "slots" 陣列（讓既有看這個欄位的
    dashboard/監控不用改）。indexed_snapshots: [(index, health_dict_or_None), ...]
    依 index 順序排列。"""
    reachable = [(i, h) for i, h in indexed_snapshots if h]
    limit = len(indexed_snapshots)
    active = sum(1 for _, h in reachable if h.get("capacity", {}).get("active"))
    slots = []
    for idx, h in indexed_snapshots:
        if h is None:
            slots.append({"index": idx, "worker_id": process_worker_id(base_worker_id, idx),
                          "healthy": False, "active": False, "error": "unreachable"})
            continue
        entry = dict(h)
        entry["index"] = idx
        entry["worker_id"] = process_worker_id(base_worker_id, idx)
        slots.append(entry)
    primary = reachable[0][1] if reachable else {}
    body = dict(primary)
    body.update({
        "ok": len(reachable) > 0,
        "engine": "flashhead-lite-multiproc-router",
        "capacity": {"limit": limit, "active": active, "available": active < limit},
        "slots": slots,
    })
    return body
