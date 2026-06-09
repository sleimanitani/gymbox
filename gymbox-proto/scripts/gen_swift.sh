#!/usr/bin/env bash
# Generate Swift protobuf bindings into swift/Sources/GymboxProto/.
# Requires: protoc + protoc-gen-swift on PATH
#   brew install protobuf swift-protobuf
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
protoc \
  -I "$HERE/proto" \
  --swift_out="$HERE/swift/Sources/GymboxProto" \
  "$HERE/proto/gymbox.proto"
echo "Generated swift/Sources/GymboxProto/gymbox.pb.swift"
