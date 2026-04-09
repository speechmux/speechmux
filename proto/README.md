# speechmux/proto

Single source of truth for all Protocol Buffer definitions. Contains `.proto` files and generated Go/Python code for distribution.

## Structure

```
proto/
├── common/v1/common.proto      # Shared enums (PluginState, PluginErrorCode)
├── client/v1/client.proto      # Client ↔ Core (StreamingRecognize)
├── vad/v1/vad.proto            # Core ↔ VAD Plugin (StreamVAD)
├── inference/v1/inference.proto # Core ↔ STT Plugin (Transcribe)
├── gen/
│   ├── go/                     # protoc-gen-go generated code
│   └── python/stt_proto/       # grpcio-tools generated code (pip-installable)
├── buf.yaml
└── Makefile
```

## Services

### `STTService` (client/v1) — Client ↔ Core

Single bidirectional streaming RPC following the Google Speech-to-Text pattern:

```protobuf
service STTService {
  rpc StreamingRecognize(stream StreamingRecognizeRequest) returns (stream StreamingRecognizeResponse);
}
```

**Protocol flow:**

1. Client sends `StreamingRecognizeRequest { session_config }` as the first message
2. Server responds with `StreamingRecognizeResponse { session_created }` (negotiated settings)
3. Client sends `StreamingRecognizeRequest { audio }` (raw PCM bytes) for each chunk
4. Server sends `StreamingRecognizeResponse { result }` with `committed_text` / `unstable_text`
5. Client sends `StreamingRecognizeRequest { signal { is_last: true } }` to end
6. Server sends final result and closes the stream

**Key messages:**

| Message | Purpose |
|---------|---------|
| `SessionConfig` | Language, audio encoding, VAD mode, decode profile, API key |
| `AudioConfig` | Encoding (PCM_S16LE, ALAW, MULAW, WAV, OGG_OPUS), sample rate, channels |
| `RecognitionConfig` | Language code, task (transcribe/translate), decode profile, engine hint |
| `VADConfig` | Mode (CONTINUE/AUTO_END), silence duration, threshold |
| `RecognitionResult` | `is_final`, `text`, `committed_text`, `unstable_text`, latency metadata |
| `StreamError` | `error_code` (ERR####), message, retryable flag |

### `VADPlugin` (vad/v1) — Core ↔ VAD Plugin

```protobuf
service VADPlugin {
  rpc StreamVAD(stream VADRequest) returns (stream VADResponse);
  rpc GetCapabilities(google.protobuf.Empty) returns (VADCapabilities);
  rpc HealthCheck(google.protobuf.Empty) returns (common.v1.PluginHealthStatus);
}
```

Each `StreamVAD` call is a per-session independent stream. The first message carries `SessionStart` (session ID + threshold); subsequent messages carry PCM audio frames with `sequence_number`. Core uses the echoed `sequence_number` in responses to match VAD results against the `AudioRingBuffer` for speech segment extraction.

**`VADCapabilities`** reports the engine's `model_name`, `optimal_frame_ms` (e.g. 32 ms for Silero), `max_concurrent_sessions`, and `supported_sample_rates`.

### `InferencePlugin` (inference/v1) — Core ↔ STT Plugin

```protobuf
service InferencePlugin {
  rpc Transcribe(TranscribeRequest) returns (TranscribeResponse);
  rpc GetCapabilities(google.protobuf.Empty) returns (InferenceCapabilities);
  rpc HealthCheck(google.protobuf.Empty) returns (common.v1.PluginHealthStatus);
}
```

Unary RPC. Core sends an audio segment (extracted from the ring buffer after EPD triggers) and receives the transcription. `TranscribeRequest` includes `is_final` / `is_partial` flags, `DecodeOptions` (beam size, temperature, etc.), and language code. `TranscribeResponse` includes `text`, `segments` with timestamps, `inference_sec`, and `real_time_factor`.

**`InferenceCapabilities`** reports `engine_name`, `model_size`, `device` (cpu/cuda/mps/mlx), `supported_languages`, `max_concurrent_requests`, and `supports_partial_decode`.

### Shared Enums (common/v1)

**`PluginState`** — lifecycle state of a plugin instance:

| Value | Meaning |
|-------|---------|
| `PLUGIN_STATE_LOADING` | Model loading in progress; Core waits |
| `PLUGIN_STATE_READY` | Accepting requests |
| `PLUGIN_STATE_DRAINING` | Shutdown in progress; rejecting new requests |
| `PLUGIN_STATE_ERROR` | Unrecoverable error; Core excludes from routing |

**`PluginErrorCode`** — error codes reported by plugins (translated to Core `ERR####` at boundary):

| Value | Core Mapping | Meaning |
|-------|-------------|---------|
| `PLUGIN_ERROR_MODEL_LOADING` | ERR2005 | Not yet ready |
| `PLUGIN_ERROR_MODEL_OOM` | ERR2005 | GPU/memory exhausted |
| `PLUGIN_ERROR_INVALID_AUDIO` | ERR3003 | Audio format/length issue |
| `PLUGIN_ERROR_INFERENCE_FAILED` | ERR2002 | Inference exception |
| `PLUGIN_ERROR_SESSION_NOT_FOUND` | ERR3004 | VAD session not found |
| `PLUGIN_ERROR_CAPACITY_FULL` | ERR2008 | Concurrency limit exceeded |

## Code Generation

```bash
make generate         # Generate Go + Python
make generate-go      # Go only
make generate-python  # Python only
make clean            # Remove gen/ directory
```

After regenerating Python stubs, reinstall the `speechmux-proto` package so the new code is picked up by plugins and the CLI:

```bash
# From the workspace root
uv pip install --python .venv/bin/python3 -e proto/gen/python
```

### Prerequisites

```bash
# Install protoc (Protocol Buffer compiler)
brew install protobuf          # macOS
# apt install protobuf-compiler  # Debian/Ubuntu

# Go plugins for protoc
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# Python plugin for protoc
pip install grpcio-tools
```

## Consuming

### Go (Core)

```go
// go.mod
require github.com/speechmux/proto v0.x.0

// import
import (
    clientpb   "github.com/speechmux/proto/gen/go/client/v1"
    vadpb      "github.com/speechmux/proto/gen/go/vad/v1"
    inferencepb "github.com/speechmux/proto/gen/go/inference/v1"
    commonpb   "github.com/speechmux/proto/gen/go/common/v1"
)
```

### Python (plugins, CLI)

```toml
# pyproject.toml
dependencies = [
    "speechmux-proto @ git+ssh://git@github.com/speechmux/proto.git@vX.Y.Z#subdirectory=gen/python",
]
```

```python
from stt_proto.vad.v1 import vad_pb2, vad_pb2_grpc
from stt_proto.inference.v1 import inference_pb2, inference_pb2_grpc
from stt_proto.common.v1 import common_pb2
```

## Compatibility Rules

- Changes must be **additive only** (new fields, new RPCs, new enum values)
- Deleting fields, changing types, or reusing field numbers is **forbidden**
- Removed fields must be `reserved` (like proto's reserved keyword)
- Breaking changes require a new version package (e.g. `client/v2/`)
- Error codes (`ERR####`) are permanently assigned and never reused

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Messages | PascalCase | `StreamingRecognizeRequest`, `PluginHealthStatus` |
| Fields | snake_case | `sequence_number`, `is_speech` |
| Enum values | UPPER_SNAKE_CASE with prefix | `PLUGIN_STATE_READY`, `PLUGIN_ERROR_MODEL_OOM` |
| RPC methods | PascalCase | `StreamVAD`, `Transcribe`, `HealthCheck` |

## License

MIT
