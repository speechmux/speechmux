# Plugin protocol (Core ↔ plugins)

The contract between Core and the Python plugin processes. Source of truth:
`proto/vad/v1/vad.proto`, `proto/inference/v1/inference.proto`,
`proto/common/v1/common.proto`.

Plugins are addressed over a Unix domain socket (`unix:///tmp/speechmux/*.sock`) locally or
TCP (`host:port`) in Docker. Exactly one of `socket` / `address` may be configured per
endpoint. Transport is plaintext gRPC — plugin sockets are not exposed outside the host or
the Compose network.

---

## `vad.v1.VADPlugin`

```protobuf
service VADPlugin {
  rpc StreamVAD(stream VADRequest) returns (stream VADResponse);
  rpc GetCapabilities(google.protobuf.Empty) returns (VADCapabilities);
  rpc HealthCheck(google.protobuf.Empty) returns (common.v1.PluginHealthStatus);
}
```

Core opens **one independent `StreamVAD` stream per session**. There is no session
multiplexing: the plugin's `ThreadPoolExecutor` assigns a dedicated worker per stream, so a
slow session cannot corrupt another's state
([ADR 0004](../decisions/0004-per-session-vad-stream.md)).

### Stream shape

| Position | Message |
|----------|---------|
| First | `VADRequest { session_start: { session_id, threshold, sample_rate } }` |
| Middle | `VADRequest { pcm_data, sample_rate, sequence_number }` |
| Last | `VADRequest { session_end: {} }`, then the client half-closes |

`sequence_number` is assigned by Core and matches the `AudioRingBuffer` entry for that
frame. **The plugin must echo it back unchanged** in `VADResponse.sequence_number` — Core
uses the echo to locate the speech segment in the ring buffer and to advance the trim
watermark. Losing or reordering sequence numbers breaks utterance extraction.

`VADResponse` carries `is_speech`, `speech_probability`, `chunk_rms`,
`chunk_duration_sec`, the echoed `sequence_number`, and `error_code` (non-zero only on a
recoverable per-frame error).

`VADCapabilities`: `model_name`, `max_concurrent_sessions`, `optimal_frame_ms` (Silero
reports 32 ms = 512 samples @ 16 kHz), `supported_sample_rates`. Core does not yet consume
`optimal_frame_ms` — see
[../plans/vad-frame-size-negotiation.md](../plans/vad-frame-size-negotiation.md).

---

## `inference.v1.InferencePlugin`

```protobuf
service InferencePlugin {
  rpc Transcribe(TranscribeRequest) returns (TranscribeResponse);
  rpc TranscribeStream(stream StreamRequest) returns (stream StreamResponse);
  rpc GetCapabilities(google.protobuf.Empty) returns (InferenceCapabilities);
  rpc HealthCheck(google.protobuf.Empty) returns (common.v1.PluginHealthStatus);
}
```

A plugin implements **one** of `Transcribe` or `TranscribeStream` and declares which
through `GetCapabilities`. Core never calls the wrong one: `RouteBatch()` filters to
`STREAMING_MODE_BATCH_ONLY` endpoints for unary dispatch, and the streaming path is only
taken for `STREAMING_MODE_NATIVE`.

### `Transcribe` — batch engines

Stateless unary RPC. Core owns all session state, scheduling and concurrency; the plugin
only runs inference.

Request: `request_id`, `session_id`, `audio_data` (PCM S16LE mono), `sample_rate`,
`language_code`, `task`, `decode_options`, `is_final`, `is_partial`.

Response: `text`, `language_code`, `inference_sec`, `audio_duration_sec`,
`real_time_factor`, `segments[]` (with `start_sec`/`end_sec`/`avg_log_prob`/
`no_speech_prob`), `no_speech_detected`, `error_code`.

`DecodeOptions` (`beam_size`, `best_of`, `temperature`, `length_penalty`,
`without_timestamps`, `compression_ratio_threshold`, `no_speech_threshold`,
`log_prob_threshold`) are converted by the host framework into a plain dict, and only
non-default fields are passed to the engine. **Core currently sends `decode_options` as
`nil` and hardcodes `task` to `TASK_TRANSCRIBE`** — see
[../plans/decode-options-and-task-passthrough.md](../plans/decode-options-and-task-passthrough.md).

### `TranscribeStream` — native streaming engines

Persistent bidi stream for the session lifetime.

| Position | `StreamRequest` payload |
|----------|-------------------------|
| First | `start: StreamStartConfig` — **required** |
| Middle | `audio: AudioChunk { sequence_number, audio_data }` |
| Any time | `control: StreamControl { kind }` |

`StreamStartConfig` carries `session_id`, `sample_rate`, `language_code`, `task`,
`decode_options`, and `endpointing_source`.

`StreamControl.Kind` is a nested enum: `KIND_FINALIZE_UTTERANCE` (emit a final hypothesis
for the current utterance and reset) and `KIND_CANCEL`.

`StreamResponse` is either `hypothesis: StreamHypothesis { request_id, text,
committed_text, unstable_text, is_final, start_sec, end_sec, language_code }` or
`error: StreamError { code, message }`.

`committed_text` / `unstable_text` appear both here and in the client-facing
`RecognitionResult`. That duplication is deliberate — an engine with better internal
knowledge of stability may fill them in, and Core's `ResultAssembler` derives them
otherwise.

### `endpointing_source`

Tells the plugin who decides where an utterance ends.

| Value | Meaning |
|-------|---------|
| `ENDPOINTING_SOURCE_UNSPECIFIED` | Treated as `CORE` (backward compatible) |
| `ENDPOINTING_SOURCE_CORE` | Core's VAD + EPD sends `KIND_FINALIZE_UTTERANCE`. The engine must **not** auto-finalize on its own endpointing. |
| `ENDPOINTING_SOURCE_ENGINE` | The engine finalizes autonomously; Core runs no VAD at all. |

This is a field on `StreamStartConfig` rather than a separate negotiation round-trip
([ADR 0014](../decisions/0014-endpointing-source.md)). An engine that ignores it will
double-finalize in `core` mode.

### `InferenceCapabilities`

| Field | Notes |
|-------|-------|
| `engine_name`, `model_size`, `device` | Surfaced in `/admin/plugins` and in metric labels |
| `supported_languages` | BCP-47; empty = all |
| `max_concurrent_requests` | Informational; the plugin enforces its own limit |
| `supports_partial_decode` | Batch engines only |
| `streaming_mode` | `UNSPECIFIED` (→ `BATCH_ONLY`), `BATCH_ONLY`, `NATIVE` |
| `endpointing_capability` | `UNSPECIFIED` (→ `NONE`), `NONE`, `DETECTION`, `AUTO_FINALIZE` |

The two capability axes are independent: streaming ability and engine-side endpointing are
separate questions, not one combined enum. `endpointing_source: engine` requires **both**
`NATIVE` and `AUTO_FINALIZE`, otherwise the session fails with **ERR1020**.

Both new enums default to `UNSPECIFIED = 0` so a plugin built before they existed still
works. Core re-fetches capabilities on the health probe while an endpoint still reports
`UNSPECIFIED`, so a plugin that was still loading at Core startup is picked up
automatically.

---

## Shared enums (`common.v1`)

### `PluginState`

| Value | Core's reaction |
|-------|-----------------|
| `LOADING` | Not routed to; `/health` reports `degraded` |
| `READY` | Accepting requests |
| `DRAINING` | Shutting down; not routed to |
| `ERROR` | Unrecoverable; excluded from routing |

### `PluginErrorCode` → `ERR####`

Plugins never emit `ERR####` codes. They report a `PluginErrorCode`, and Core translates it
at the boundary ([ADR 0008](../decisions/0008-error-code-registry.md)):

| Plugin error | Core code | Meaning |
|--------------|-----------|---------|
| `PLUGIN_ERROR_MODEL_LOADING` | ERR2005 | Model not ready yet |
| `PLUGIN_ERROR_MODEL_OOM` | ERR2005 | GPU / memory exhausted |
| `PLUGIN_ERROR_INVALID_AUDIO` | ERR3003 | Bad audio format or length |
| `PLUGIN_ERROR_INFERENCE_FAILED` | ERR2002 | Exception during inference |
| `PLUGIN_ERROR_SESSION_NOT_FOUND` | ERR3004 | Unknown `session_id` |
| `PLUGIN_ERROR_CAPACITY_FULL` | ERR2008 | Concurrency limit reached |

`PluginHealthStatus` returns `state`, `active` (active VAD sessions or in-flight STT
requests), a human-readable `message`, and `last_error`.

---

## Compatibility rules

Enforced by `buf lint` and `buf breaking` in the proto repo's CI:

- **Additive only.** New fields, new RPCs, new enum values.
- Deleting a field, renumbering it, or changing its type is forbidden. `reserved` both the
  number and the name instead.
- New enums must keep `0 = UNSPECIFIED` with a backward-compatible meaning.
- A breaking change requires a new version package (`client/v2/`).
- `ERR####` codes are permanently assigned and never reused.

`buf.yaml` waives four standard lint rules for the plugin protos, with the reason recorded
inline: `ENUM_VALUE_PREFIX` (`PLUGIN_ERROR_` rather than `PLUGIN_ERROR_CODE_`),
`SERVICE_SUFFIX` (`VADPlugin`, not `VADPluginService`), and the
`RPC_REQUEST/RESPONSE_STANDARD_NAME` / `RPC_REQUEST_RESPONSE_UNIQUE` rules for `vad/v1`
and `inference/v1`.

Regeneration workflow: [`change-proto`](../../.codex/skills/change-proto/SKILL.md).
