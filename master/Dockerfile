# ── Stage 1: compile proto stubs ─────────────────────────────────────────────
FROM python:3.11-slim AS proto-builder

WORKDIR /build
COPY proto/ proto/
COPY common/generated/__init__.py common/generated/
RUN pip install grpcio-tools --quiet && \
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

COPY master/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=proto-builder /build/common/generated/ common/generated/
COPY common/ common/
COPY master/ master/

ENV MASTER_HTTP_PORT=8000
ENV MASTER_GRPC_PORT=50051
ENV SCHEDULING_STRATEGY=load_aware
ENV MAX_RETRIES=3
ENV TASK_TIMEOUT=120
ENV HEARTBEAT_TIMEOUT=15
ENV MAX_QUEUE_SIZE=5000

EXPOSE 8000 50051

CMD ["python3", "-m", "uvicorn", "master.main:app", "--host", "0.0.0.0", "--port", "8000"]
