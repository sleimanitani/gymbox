# gymbox-proto

Shared wire format for gymbox: the **upload envelope** schema spoken by
`GymboxSDK` (Swift) and `gymbox` (Python).

**There is no gRPC service in MVP-α.** These message types describe the body of
`POST /sessions` only. A streaming service is reserved for Phase 1+ (fixed
cameras). See `architecture.md` §5, §8, §11.

## Layout

```
proto/gymbox.proto                  # source of truth
python/                             # Python bindings (pip-installable)
swift/                              # Swift package (SPM)
scripts/gen_python.sh               # protoc -> python
scripts/gen_swift.sh                # protoc -> swift
```

## Generating bindings

Generated code is **not** checked in. Generate it:

```bash
# Python
pip install grpcio-tools
./scripts/gen_python.sh

# Swift
brew install protobuf swift-protobuf
./scripts/gen_swift.sh
```

## Versioning

`gymbox-proto` is versioned independently; its major version is bound to the
SDK major version. New fields are non-breaking; removed/renumbered fields
require a major bump. `PoseFrame` field numbers 9–15 are **reserved** — do not
assign without a major bump (proto3 reused field numbers corrupt data silently).
