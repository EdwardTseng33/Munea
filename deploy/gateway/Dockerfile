FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway_core.py gateway_server.py call_control_store.py monitor.py monitor_service.py slack_notify.py ./

CMD ["sh", "-c", "exec uvicorn gateway_server:app --host 0.0.0.0 --port ${PORT:-8080}"]
