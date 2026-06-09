#!/usr/bin/env bash
# Generate Python protobuf bindings into python/gymbox_proto/.
# Requires: pip install grpcio-tools
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
python -m grpc_tools.protoc \
  -I "$HERE/proto" \
  --python_out="$HERE/python/gymbox_proto" \
  "$HERE/proto/gymbox.proto"
# protoc emits gymbox_pb2.py at the package root; fix the import if needed.
echo "Generated python/gymbox_proto/gymbox_pb2.py"
