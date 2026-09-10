# Skill: change-proto

Change a `.proto` file and propagate it through Go Core, the Python plugins and the clients.

## When to use this

Any edit to `proto/client/v1/client.proto`, `proto/vad/v1/vad.proto`,
`proto/inference/v1/inference.proto` or `proto/common/v1/common.proto` — adding a field,
an RPC, an enum value, or a message.

**Do not** hand-edit anything under `proto/gen/`. It is generated.

## Prerequisites

- `proto` and `core` cloned; `.venv` with `grpcio-tools` installed.
- `protoc` plus `protoc-gen-go` and `protoc-gen-go-grpc` on `$GOBIN` (`~/go/bin`).
- `buf` installed (`brew install bufbuild/buf/buf`).
- Read [docs/api/plugin-protocol.md](../../../docs/api/plugin-protocol.md#compatibility-rules).

## The rule that governs everything

**Changes are additive only.** New fields, new RPCs, new enum values. You may not delete a
field, renumber it, change its type, or reuse a retired number. To remove a field, reserve
both the number and the name:

```protobuf
reserved 12;
reserved "old_field_name";
```

A genuinely breaking change requires a new version package (`client/v2/`). `buf breaking`
in the proto repo's CI enforces this against `main`.

---

## Steps

### 1. Edit the `.proto`

- Messages `PascalCase`, fields `snake_case`, enum values `UPPER_SNAKE_CASE` with the
  enum's prefix, RPCs `PascalCase`.
- A new enum needs `0 = <PREFIX>_UNSPECIFIED` with a meaning that is backward compatible
  for a peer that has never heard of the enum. `StreamingMode`, `EndpointingCapability` and
  `EndpointingSource` all do this.
- Comment the field. The proto is the contract; a bare field name is not a contract.
- Use `optional` when the zero value is a legitimate value that must be distinguishable
  from "unset" — as `VADConfig.threshold_override` does for `0.0`.

### 2. Lint before generating

```bash
cd proto && buf lint
```

`buf.yaml` waives four rules for the plugin protos, each with an inline reason. If your
change trips a *new* rule, fix the proto — do not widen the waiver list without recording
why in `buf.yaml`.

### 3. Generate

```bash
cd proto && make generate           # Go + Python
uv pip install --python ../.venv/bin/python3 -e gen/python
```

Or, from the workspace root, `make proto` does both.

`make generate-python` also runs `_fix-python-imports`, which rewrites the bare
`from common.v1 import …` that `grpcio-tools` emits into `from stt_proto.common.v1 import …`,
and `_ensure-python-inits`, which touches `__init__.py` in every generated directory.
Skipping either leaves the package unimportable.

**Reinstalling `speechmux-proto` is not optional.** Editable installs point at the source
tree, but the generated `_pb2.py` modules are only picked up after reinstall when the
package metadata changes.

### 4. Check the diff

`git -C proto diff --stat gen/` should show only files your change touches. A different
`protoc` or `grpcio-tools` version rewrites serialized descriptors and version strings
across every generated file. If you see churn unrelated to your change:

```bash
git -C proto checkout -- gen/          # discard everything
# then regenerate with the versions the repo was last generated with,
# or accept the churn as a deliberate, separate commit
```

Do not mix a toolchain upgrade into a feature commit.

### 5. Update Go Core

`core/go.mod` depends on the **published** `github.com/speechmux/proto` module, not the
local directory. To consume a new field before the proto repo is tagged, add a temporary
replace while iterating:

```
replace github.com/speechmux/proto => ../proto
```

Remove it before committing, and update `go.mod`/`go.sum` to the real tag once the proto
change is released.

Then:

```bash
cd core && go build ./... && go test ./...
```

Places a wire change usually reaches:

| Change | Look at |
|--------|---------|
| `client.proto` request/response | `internal/transport/grpc_server.go`, `internal/transport/websocket_handler.go`, `internal/session/manager.go` (`resolveInfo`) |
| `client.proto` result fields | `internal/stream/engine.go` (`DecodeResult`) and the result-forwarding goroutine in `internal/stream/processor.go` |
| `inference.proto` | `internal/plugin/inference_client.go`, `inference_stream_client.go`, `internal/stream/batch_engine.go`, `streaming_engine.go`, `internal/stream/fair_dispatch.go` (`BatchTask`) |
| `vad.proto` | `internal/plugin/vad_client.go`, `internal/stream/processor.go` |
| `common.proto` | `internal/errors/plugin_errors.go`, `internal/runtime/health.go` |
| New capability field | `internal/plugin/router.go` (routing filters), `internal/runtime/health.go` |

Adding a field to `DecodeResult` **requires** a matching update in the result-forwarding
goroutine in `ProcessSession`, or it is silently dropped.

### 6. Update the Python plugins

```bash
cd plugin-stt && ../.venv/bin/python3 -m pytest tests/ -q && ../.venv/bin/python3 -m mypy src/
cd plugin-vad && ../.venv/bin/python3 -m pytest tests/ -q
```

Typically `service/inference_servicer.py` or `service/vad_servicer.py`. If the change adds
something an engine must supply, it also changes the `Protocol` in `engine/base.py` — which
breaks every engine adapter. Give it a default where you can, and update each adapter and
its tests.

### 7. Update the clients

- `client-cli/speechmux_cli/client/grpc_client.py` and the `commands/` that expose the
  option.
- `client-web`: `web/lib/speechmux-ws.ts` and `api/speechmux_api/ws_proxy.py` if the
  WebSocket JSON shape changes. The WebSocket schema is defined in Go
  (`websocket_handler.go`), not in the proto — keep the two in step by hand.

### 8. Update the documentation

Mandatory, in the same change:

| Proto | Document |
|-------|----------|
| `client/v1/client.proto` | [docs/api/client-protocol.md](../../../docs/api/client-protocol.md) |
| `vad/v1`, `inference/v1` | [docs/api/plugin-protocol.md](../../../docs/api/plugin-protocol.md) |
| `common/v1` enums | [docs/api/plugin-protocol.md](../../../docs/api/plugin-protocol.md) and [docs/api/error-codes.md](../../../docs/api/error-codes.md) |

Also `proto/README.md`, which documents the contract from the proto repo's own point of
view.

---

## Verification

```bash
cd proto && buf lint && make generate
cd proto && buf breaking --against '.git#branch=main'   # what CI runs on PRs
cd core  && go build ./... && go test ./...
cd plugin-stt && ../.venv/bin/python3 -m pytest tests/ -q
cd plugin-vad && ../.venv/bin/python3 -m pytest tests/ -q
cd client-cli && ../.venv/bin/python3 -m pytest tests/ -q
cd client-web/web && npx tsc --noEmit
```

Then end to end: `make up` and a real transcription through both the CLI and the web client.

---

## Common mistakes

- **Editing `gen/`.** Every regeneration discards it.
- **Not reinstalling `speechmux-proto`.** Plugins keep importing the old stubs and fail with
  a confusing `AttributeError` on the new field.
- **Reusing a field number.** Silent, catastrophic misinterpretation on the wire. Old
  binaries decode the new field as the old one.
- **A new enum without `UNSPECIFIED = 0`.** Peers that predate the enum send `0`; if `0`
  has no safe meaning, they break.
- **Committing toolchain churn.** A `protoc` version bump rewrites every generated file and
  buries the real change.
- **Forgetting the WebSocket side.** It is hand-written Go, not generated, so a `client.proto`
  change does not propagate to it automatically.
- **Assuming a local `proto/` edit is visible to Core.** `core/go.mod` uses the published
  module. Without a `replace`, Go builds against the old version and you will chase a
  phantom compile error.
- **Changing an engine `Protocol` without updating every adapter.** They live in separate
  repos and will not fail your build — they fail at runtime.

---

## Done when

- [ ] `buf lint` and `buf breaking --against '.git#branch=main'` both pass.
- [ ] `make generate` produces a diff limited to your change.
- [ ] `speechmux-proto` reinstalled into `.venv`.
- [ ] Core builds and all Go tests pass.
- [ ] All plugin and client test suites pass.
- [ ] The matching API document is updated, along with `proto/README.md`.
- [ ] Committed per repository, proto first.
