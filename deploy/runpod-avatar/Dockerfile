FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-controller.txt ./
RUN pip install --no-cache-dir -r requirements-controller.txt

# 不用 root 跑（2026-10-13 弱點掃描 DS-0002）。備援帳本預設寫在程式旁邊（/app/.runpod-backup-state.json），
# 所以 /app 交給 munea。
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin munea \
 && chown munea:munea /app

COPY --chown=munea:munea podctl.py runpod_backup.py controller_service.py ./

USER munea

CMD ["sh", "-c", "exec uvicorn controller_service:app --host 0.0.0.0 --port ${PORT:-8080}"]
