# 聊聊分流閘道（2026-07-12 卡西法 · 照 `docs/多人併發容量架構-2026-07-12.md` §2 施工）

CPU-only 控制面服務——只做「登記＋配對＋釋放＋排隊決策」，媒體流（WebRTC）永遠是
App 跟 avatar worker（`deploy/runpod-avatar/flashhead_server.py`）直連，不繞這裡。

## 元件

| 檔案 | 用途 |
|---|---|
| `gateway_core.py` | 核心邏輯（零依賴、不 import fastapi）——worker 登記簿 + fullest-first 配對 + 聯合准入 + FIFO 排隊。完整單元測試：`python scripts/test_gateway.py` |
| `gateway_server.py` | 薄薄一層 FastAPI 外殼，把 gateway_core 的方法接成 HTTP 端點。需要 `pip install fastapi "uvicorn[standard]"`（CPU-only 套件，不需要 GPU）。HTTP 層測試：`python scripts/test_gateway_http.py` |
| `CLIENT-INTERFACE.md` | Client 對接規格，給 Codex 接 app.js 排隊流程用 |

## 現況（2026-07-12）

**這輪只做出後端邏輯 + HTTP 外殼 + client 對接規格，還沒有真的部署到任何地方**（沒開
真卡、沒登記真的 worker、app.js 還沒接線）。照任務邊界：不開真卡、不花 GPU 錢、不碰
app.js。下一步（要真卡才能做）：

1. 真的把 `deploy/runpod-avatar/` 的 worker（RunPod / Glows）登記進閘道
   （`POST /v1/admin/worker/register`）
2. `flashhead_server.py` 通話結束時打 `/v1/call/release` webhook（這輪還沒接，見
   `CLIENT-INTERFACE.md` 「worker 端 webhook」段落）
3. Codex 照 `CLIENT-INTERFACE.md` 接 app.js 的排隊 UI + 輪詢邏輯
4. 6.3 節純語音壓測結果回填 `MUNEA_GATEWAY_VOICE_LIMIT`（現在是保守預設值 5，
   不是實測數字）
5. 上面都接好、測過排隊流程真的會觸發，才能拔掉 `web/src/app.js:3216-3222`
   那段「滿載退純語音」的舊邏輯

## 方案選型備忘

這輪照架構文件 §2.2 的「方案 B（自建閘道）」形狀寫——client 直連指定 worker，
affinity 天生成立，不賭 Modal 平台未驗證的 session affinity。「方案 A（Modal 原生池）」
要先做真卡 PoC 才能定案，介面留著沒寫死，之後要換不必重寫呼叫端。

## 跑法（本機測試用）

```bash
pip install fastapi "uvicorn[standard]"
MUNEA_GATEWAY_KEY=<通行碼> python deploy/gateway/gateway_server.py   # 門牌 8199
```
