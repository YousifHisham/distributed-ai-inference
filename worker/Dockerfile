# ── Stage 1: compile proto stubs ─────────────────────────────────────────────
FROM python:3.11-slim AS proto-builder

WORKDIR /build
COPY proto/ proto/
COPY common/generated/__init__.py common/generated/
RUN pip install grpcio-tools==1.68.0 --quiet && \
    python -m grpc_tools.protoc \
      -I proto \
      --python_out=common/generated \
      --grpc_python_out=common/generated \
      proto/inference.proto && \
    python - <<'EOF'
import re, pathlib
p = pathlib.Path("common/generated/inference_pb2_grpc.py")
text = p.read_text()
text = re.sub(r'^import inference_pb2 as', 'from common.generated import inference_pb2 as', text, flags=re.MULTILINE)
p.write_text(text)
EOF

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY worker/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ common/
COPY --from=proto-builder /build/common/generated/ common/generated/
COPY worker/ worker/

ENV MASTER_GRPC_URL=host.docker.internal:50051
ENV OLLAMA_URL=http://host.docker.internal:11434
ENV WORKER_MODEL=llama3.2:1b
ENV WORKER_MAX_CONCURRENT=4
ENV HEARTBEAT_INTERVAL=5
ENV WORKER_HTTP_PORT=8001
ENV WORKER_GRPC_PORT=50052

EXPOSE 8001 50052

CMD ["python3", "-m", "uvicorn", "worker.main:app", "--host", "0.0.0.0", "--port", "8001"]
