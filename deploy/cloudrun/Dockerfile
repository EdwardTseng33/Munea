# 沐寧引擎 · 雲端主機打包配方（Google Cloud Run · 台灣機房 asia-east1）
# 一顆映像兩種跑法：
#   管家腦（預設）：HTTP 服務（聊天/記憶/簡報/守護）
#   語音橋：部署時覆蓋啟動指令 → python engine/live_voice_server.py（門牌自動吃 PORT）
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine/ engine/
COPY web/ web/

# 管家腦：Cloud Run 用 PORT 指定門牌 → 轉給 MUNEA_PORT
CMD ["sh", "-c", "MUNEA_PORT=${PORT:-8200} python engine/server.py"]
