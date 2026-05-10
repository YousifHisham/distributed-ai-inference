# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY master/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ common/
COPY rag/ rag/
COPY master/ master/

ENV MASTER_HTTP_PORT=8000
ENV SCHEDULING_STRATEGY=load_aware
ENV MAX_RETRIES=3
ENV TASK_TIMEOUT=120
ENV HEARTBEAT_TIMEOUT=6
ENV HEALTH_CHECK_INTERVAL=1
ENV MAX_QUEUE_SIZE=5000
ENV RAG_ENABLED=true
ENV RAG_TOP_K=3
ENV RAG_DOCS_DIR=rag/knowledge_base
ENV RAG_DB_DIR=.chroma
ENV ANONYMIZED_TELEMETRY=False

EXPOSE 8000

CMD ["python3", "-m", "master.main"]
