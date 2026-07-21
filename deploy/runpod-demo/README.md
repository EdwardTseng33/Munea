# B2B Demo 專用 RunPod 線

這個資料夾只管理 `munea-b2b` 展示體驗，不管理 App 正式線或備援線。

## 固定邊界

- Pod 名稱：`munea-flashhead-demo-768-r6000ada`
- Network Volume：`7d3vqi99dm`（US-IL-1）
- 服務：8188、單槽、768×768、`a05d/a06d`
- 時限：由 B2B `/api/call-key` 維持 180 秒
- 不使用 `a05/a06`，不讀 App Key，不註冊 App Gateway

## 日常操作

```powershell
python deploy/runpod-demo/democtl.py status
python deploy/runpod-demo/democtl.py wake
```

Network Volume Pod 不能一般 Stop。要省 GPU 費用時，先確認沒有訪客，再用明確 Pod ID 釋放 GPU：

```powershell
python deploy/runpod-demo/democtl.py release --confirm-id <目前 Demo Pod ID>
```

`release` 只接受名稱完全相符且 ID 再確認的 Demo Pod；Network Volume 會保留。之後 `wake` 會重新建立並掛回同一個 Volume。不要對 App 或備援 Pod 使用本工具。

## 主機內服務

```bash
/workspace/munea-demo/current/manage-demo.sh status
/workspace/munea-demo/current/manage-demo.sh probe
/workspace/munea-demo/current/manage-demo.sh restart
```

部署時把本資料夾、`deploy/runpod-avatar/flashhead_server.py` 和 `flashhead_engine_core.py` 放入新的 release，再切換 `/workspace/munea-demo/current`。`runtime.env` 只留 Demo 密碼雜湊與模型路徑，不放 App/Gateway 金鑰。
