#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[proto] Installing grpcio-tools if needed..."
pip3 install grpcio-tools==1.68.0 --quiet

echo "[proto] Compiling proto/inference.proto..."
python3 -m grpc_tools.protoc \
  -I proto \
  --python_out=common/generated \
  --grpc_python_out=common/generated \
  proto/inference.proto

echo "[proto] Fixing generated import in inference_pb2_grpc.py..."
python3 - <<'PYEOF'
import re, pathlib
p = pathlib.Path("common/generated/inference_pb2_grpc.py")
text = p.read_text()
text = re.sub(
    r'^import inference_pb2 as',
    'from common.generated import inference_pb2 as',
    text, flags=re.MULTILINE
)
p.write_text(text)
PYEOF

echo "[proto] Done. Generated files:"
ls common/generated/
