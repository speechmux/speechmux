# Client-facing API

Three surfaces: gRPC `StreamingRecognize`, the WebSocket JSON protocol, and the HTTP
operations/admin endpoints. Source of truth: `proto/client/v1/client.proto` and
`core/internal/transport/`.

---

## gRPC — `client.v1.STTService`

Port `50051` by default (`server.grpc_port`).

```protobuf
service STTService {
  rpc StreamingRecognize(stream StreamingRecognizeRequest)
      returns (stream StreamingRecognizeResponse);
}
```

One bidirectional stream carries session creation, audio upload and results. There is no
separate `CreateSession` RPC
([ADR 0002](../decisions/0002-single-bidi-streaming-rpc.md)).

### Flow

| Step | Direction | Message |
|------|-----------|---------|
| 1 | client → server | `session_config` — **required first message** |
| 2 | server → client | `session_created` — negotiated settings |
| 3 | client → server | `audio` (bytes), repeated |
| 4 | server → client | `result`, repeated |
| 5 | client → server | `signal { is_last: true }` |
| 6 | server → client | final `result`, then the stream closes |

Any message other than `session_config` first fails with **ERR1016**. On a terminal error
the server sends `error { error_code, message, retryable }` and closes.

### `SessionConfig`

| Field | Notes |
|-------|-------|
| `session_id` | Client-provided or server-generated. Duplicate → ERR1002 |
| `attributes` | Free-form `map<string,string>` passed through |
| `audio_config` | `encoding`, `sample_rate`, `channels` (mono required) |
| `recognition_config` | `language_code` (BCP-47, empty = auto-detect), `task`, `decode_profile`, `engine_hint` |
| `vad_config` | `mode`, `silence_duration`, `threshold`, `threshold_override` |
| `api_key` | Optional if an interceptor handles auth |
| `stream_mode` | `REALTIME` or `BATCH` — selects the backpressure policy |

**`stream_mode`** is the field most often set wrongly. `REALTIME` drops the oldest buffered
audio when the ring buffer fills, so a live microphone never stalls. `BATCH` applies HTTP/2
flow-control backpressure to the sender, which is what a file upload wants. Details:
[../architecture/core-pipeline.md](../architecture/core-pipeline.md#audioringbuffer).

**`engine_hint`** must be the endpoint **`id`** from `plugins.yaml` (e.g. `whisper-mlx`),
not the engine name (`mlx_whisper`). An unmatched or unhealthy hint silently falls back to
normal routing.

`vad_config.threshold_override` is `optional double` specifically so that an explicit
`0.0` is distinguishable from "unset".

### Enums

| Enum | Values |
|------|--------|
| `AudioEncoding` | `PCM_S16LE` (default), `ALAW`, `MULAW`, `WAV`, `OGG_OPUS` |
| `Task` | `TRANSCRIBE`, `TRANSLATE` |
| `DecodeProfile` | `REALTIME` (beam 1), `ACCURATE` (beam 5) — named sets live in `core.yaml` |
| `VADMode` | `CONTINUE` (stay open), `AUTO_END` (close after one utterance) |
| `StreamMode` | `REALTIME`, `BATCH` |

`OGG_OPUS` is accepted by the proto but the pure-Go codec build returns **ERR1015** for it.

### `RecognitionResult`

| Field | Meaning |
|-------|---------|
| `is_final` | This result closes the utterance |
| `text` | Full transcript for the utterance when `is_final` |
| `committed_text` | Stable prefix — never shrinks within an utterance |
| `unstable_text` | Suffix that may change on the next partial |
| `audio_duration` | Seconds of audio decoded |
| `language_code` | Detected BCP-47 code |
| `start_sec` / `end_sec` | Session-relative utterance bounds |
| `meta` | `latency_sec`, `real_time_factor`, `utterance_index` |

Render `committed_text` as settled and `unstable_text` as in-flight. How they are computed:
[../architecture/core-pipeline.md](../architecture/core-pipeline.md#resultassembler).

---

## WebSocket

Port `8091` by default (`server.ws_port`), on paths `/ws` and `/ws/stream`. Text frames
carry JSON; binary frames carry raw audio in the session's configured encoding.

### Client → server

```jsonc
// Open a session (first frame)
{"type":"start","session_id":"…","sample_rate":16000,"encoding":"pcm_s16le",
 "task":"transcribe","language_code":"ko","decode_profile":"realtime",
 "engine_hint":"","vad_silence":0.2,"vad_threshold":0.5,
 "api_key":"…","attributes":{}}

// Resume a parked session (alternative first frame)
{"type":"resume","session_id":"…","resume_token":"…"}

// End of audio
{"type":"end"}
```

Then binary frames of audio. `encoding` accepts `pcm_s16le` (default), `alaw`, `mulaw`,
`wav`. `task` and `decode_profile` are matched case-insensitively against `translate` and
`accurate`; anything else falls back to `transcribe` / `realtime`.

### Server → client

```jsonc
{"type":"session","session_id":"…","language_code":"ko","task":"transcribe",
 "decode_profile":"realtime","vad_silence":0.2,"vad_threshold":0.5,
 "resume_token":"…"}                                  // resume_token only when resume is enabled

{"type":"result","is_final":false,"text":"…","committed_text":"…","unstable_text":"…",
 "language_code":"ko","engine_name":"sherpa_onnx_zipformer","start_sec":0.0,"end_sec":1.8}

{"type":"error","code":"ERR3004","message":"VAD stream connect failed"}
{"type":"done"}
```

`text` is kept for backward compatibility with older clients; new clients should use
`committed_text` + `unstable_text`. `engine_name` is the runtime engine that produced the
result — it has no gRPC counterpart and is WebSocket-only.

### Session resume

Enabled by `server.resumable_session_timeout_sec > 0` (default `0` = disabled). On an
*unexpected* disconnect the session is parked and kept alive for that window; a clean
`{"type":"end"}` closes it immediately. The `resume_token` is generated once at session
creation and never rotated. Parked sessions are skipped by the idle reaper. Failures:
**ERR1018** (unknown/expired session), **ERR1019** (bad token or session already active).

### Origin checking

`server.allowed_origins` gates the `Origin` header. An **empty list allows all origins**,
which is appropriate behind a trusted reverse proxy but should be set explicitly when the
WebSocket port is exposed directly. A missing `Origin` header is accepted so that
non-browser clients work.

---

## HTTP operations API

Port `8090` by default (`server.http_port`).

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | none | Aggregated plugin health — see [../architecture/observability.md](../architecture/observability.md#health) |
| GET | `/metrics` | none | Prometheus text format |
| GET | `/metrics.json` | none | Same metrics as JSON |
| POST | `/admin/reload` | admin token | Re-read `core.yaml` |
| GET | `/admin/plugins` | admin token | List VAD + inference endpoints with live engine metadata |
| POST | `/admin/plugins/inference` | admin token | Register an inference endpoint at runtime |
| DELETE | `/admin/plugins/inference/{id}` | admin token | Deregister an endpoint |

The admin token is `auth.auth_secret`, sent in the `Authorization` header. When
`auth_secret` is empty the admin routes are unauthenticated — set it before exposing the
HTTP port. HTTP endpoints are rate-limited by `rate_limit.http_rps` / `http_burst`.

### HTTP admin API

`POST /admin/plugins/inference` — `socket` and `address` are mutually exclusive and exactly
one is required. Endpoints added this way get priority `0` (lowest).

```bash
curl -X POST http://localhost:8090/admin/plugins/inference \
  -H "Authorization: $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"id":"stt-extra","address":"10.0.0.5:50061"}'
# 201 {"status":"registered","id":"stt-extra","address":"10.0.0.5:50061"}

curl -X DELETE http://localhost:8090/admin/plugins/inference/stt-extra \
  -H "Authorization: $ADMIN_TOKEN"
# 200 {"status":"removed","id":"stt-extra"}
```

`GET /admin/plugins` returns `EndpointSummary` objects: `id`, `socket` or `address`,
`healthy`, `circuit_breaker`, and the runtime `engine_name` / `model_size` / `device`. The
web client's `/api/engines` route uses this to show only healthy engines.

Error bodies are `{"code":"ERR####","message":"…"}`.

---

## Authentication

`auth.auth_profile` selects the mode:

| Profile | Requirement |
|---------|-------------|
| `none` | Nothing, unless `require_api_key: true`, which then demands a non-empty `api_key` |
| `api_key` | Non-empty `api_key`, else **ERR1009** |
| `signed_token` | HMAC-SHA256 over `"<session_id>:<unix_seconds>"` using `auth_secret` |

For `signed_token`, the timestamp comes from `x-stt-auth-ts` / `x-auth-ts` /
`x-auth-timestamp` and the signature from the signature metadata; a legacy
`authorization: <ts>:<sig>` form is also accepted. Millisecond epochs are detected and
converted. `auth_ttl_sec > 0` rejects timestamps outside that window (**ERR1014**).
Comparison uses `hmac.Equal`.

Profile names are normalised, so `off`/`false`/`0` all mean `none`, and
`signed`/`signature`/`hmac` all mean `signed_token`.

Browser clients that cannot set headers may pass the token as a `?token=` query parameter
to the `client-web` FastAPI proxy, which injects the Core API key server-side so the real
key never reaches the browser.

---

## TLS

One certificate (`tls.cert_file` / `tls.key_file`, TLS 1.2 minimum) is shared by all three
ports. It is loaded once at startup — a config reload does **not** re-read it, so rotate
certs by restarting with the graceful drain
([ADR 0009](../decisions/0009-shared-tls-config-restart-to-rotate.md)). Setting
`tls.tls_required: true` without a cert/key pair is a startup error.
