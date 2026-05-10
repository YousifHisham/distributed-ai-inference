# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY worker/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ common/
COPY worker/ worker/

ENV MASTER_HTTP_URL=http://host.docker.internal:8000
ENV OLLAMA_URL=http://host.docker.internal:11434
ENV WORKER_MODEL=llama3.2:1b
ENV HEARTBEAT_INTERVAL=2
ENV WORKER_HTTP_PORT=8001

EXPOSE 8001

CMD ["python3", "-m", "worker.main"]
