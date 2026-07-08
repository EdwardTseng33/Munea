# 沐寧引擎 · 雲端主機打包配方（Google Cloud Run · 台灣機房 asia-east1）
# 一顆映像兩種跑法：
#   管家腦（預設）：HTTP 服務（聊天/記憶/簡報/守護）
#   語音橋：部署時覆蓋啟動指令 → python engine/live_voice_server.py（門牌自動吃 PORT）
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine/ engine/
COPY web/ web/

# 一顆映像兩種身分：MUNEA_SERVICE=voice → 語音橋；沒設 → 管家腦
CMD ["sh", "-c", "if [ \"$MUNEA_SERVICE\" = \"voice\" ]; then exec python engine/live_voice_server.py; else MUNEA_HOST=0.0.0.0 MUNEA_PORT=${PORT:-8200} exec python engine/server.py; fi"]
