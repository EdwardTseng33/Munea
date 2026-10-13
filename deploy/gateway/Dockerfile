FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 不用 root 跑（2026-10-13 弱點掃描 DS-0002）。監看狀態檔預設在 /tmp、/app 交給 munea，兩處都寫得了。
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin munea \
 && chown munea:munea /app

COPY --chown=munea:munea gateway_core.py gateway_server.py call_control_store.py locale_context_claims.py monitor.py monitor_service.py slack_notify.py ./

USER munea

CMD ["sh", "-c", "exec uvicorn gateway_server:app --host 0.0.0.0 --port ${PORT:-8080}"]
