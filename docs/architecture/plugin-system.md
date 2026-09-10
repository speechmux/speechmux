# Plugin system

Speech models run outside Core, in Python processes that speak gRPC. This document
describes the two layers of that system and how a new engine is plugged in.

Source: `plugin-vad/`, `plugin-stt/`, `plugin-vad-silero/`, `plugin-stt-*/`,
`core/internal/plugin/`.

---

## Two layers

**Host framework** — `plugin-vad` and `plugin-stt`. One per plugin *kind*. Owns:

- the `main.py` entry point (`python -m speechmux_plugin_{vad,stt}.main --config <yaml>`),
- YAML loading and validation,
- the gRPC server and servicer, including `GetCapabilities` and `HealthCheck`,
- the concurrency semaphore and thread-pool sizing,
- the engine `Protocol` definitions and the entry-point registry.

**Engine adapter** — `plugin-vad-silero`, `plugin-stt-mlx-whisper`,
`plugin-stt-faster-whisper`, `plugin-stt-sherpa-onnx`. One per model runtime. A thin
package that implements one Protocol and registers itself. It contains no gRPC code, no
server, and no config file loading of its own.

This split is why adding an engine never touches Core or the wire protocol
(see [../decisions/0003-entry-point-engine-registry.md](../decisions/0003-entry-point-engine-registry.md)).

---

## Engine discovery

Engines are found through Python entry points. There is no registry file to edit.

```toml
# plugin-stt-<impl>/pyproject.toml
[project.entry-points."speechmux.stt_engine"]
my_engine = "speechmux_plugin_stt_my_engine.engine:MyEngine"
```

| Plugin kind | Entry-point group | Registry |
|-------------|-------------------|----------|
| VAD | `speechmux.vad_engine` | `plugin-vad/src/speechmux_plugin_vad/engine/registry.py` |
| STT | `speechmux.stt_engine` | `plugin-stt/src/speechmux_plugin_stt/engine/registry.py` |

`get_engine(name, config)` looks the name up in the group, and — if the class exposes a
`from_config(cls, config)` classmethod — constructs it from the `engine.<name>` section of
the plugin YAML. Otherwise it calls `cls()`. `list_engines()` is used to produce a helpful
error when the name is not installed.

An engine is therefore selected purely by `server.engine: <entry-point name>` in the plugin
YAML. The `--config` flag is the *only* CLI argument; socket, engine and log level all come
from the file.

---

## Engine contracts

Protocols are `@runtime_checkable`, and identity attributes are **class attributes, not
methods** — the servicer reads them directly to build `GetCapabilities`.

### `VADEngine` — `plugin-vad/src/speechmux_plugin_vad/engine/base.py`

```python
model_name: str
optimal_frame_ms: int
supported_sample_rates: list[int]
max_concurrent_sessions: int

def create_session_state(threshold: float) -> object
def process_frame(session_state, pcm_data: bytes, sample_rate: int) -> tuple[bool, float, float]
```

The engine is stateless with respect to sessions: one instance serves many concurrent
streams, and all mutable state lives in the opaque object returned by
`create_session_state`. `process_frame` returns `(is_speech, speech_probability, chunk_rms)`.

### `InferenceEngine` (batch) — `plugin-stt/src/speechmux_plugin_stt/engine/base.py`

```python
engine_name: str
model_size: str
device: str
supported_languages: list[str]
max_concurrent_requests: int
supports_partial_decode: bool

def load() -> None
def transcribe(audio_data, sample_rate, language_code, task,
               decode_options, is_final, is_partial) -> TranscribeResult
```

`load()` is called once before the gRPC server starts accepting, so model weights are
resident before the first request. `transcribe` returns a `TranscribeResult` NamedTuple
(text, language, timings, segments, `no_speech_detected`).

### `StreamingInferenceEngine` (native streaming) — same module

```python
engine_name: str
supported_languages: list[str]
max_concurrent_sessions: int
streaming_mode: int             # inference_pb2.STREAMING_MODE_NATIVE
endpointing_capability: int     # ENDPOINTING_CAPABILITY_{NONE,DETECTION,AUTO_FINALIZE}

def load() -> None
def stream(request_iterator, session_config) -> Generator[StreamResponse, None, None]
```

The servicer has already consumed and validated the first `StreamStartConfig` before
calling `stream`; the iterator yields the remaining `AudioChunk` / `StreamControl`
messages. The generator must **return**, not raise, when the iterator is exhausted.

The servicer distinguishes the two STT protocols with `isinstance(engine,
StreamingInferenceEngine)` at construction time, and reports `STREAMING_MODE_BATCH_ONLY`
from `GetCapabilities` on the batch path.

---

## Plugin lifecycle

1. `main.py` parses `--config` and loads the YAML.
2. `server.socket` **xor** `server.address` must be set — UDS for local, TCP for Docker.
   Setting both is a startup error.
3. The engine is instantiated from `server.engine`; `server.max_concurrent_sessions`
   overrides the engine's own default when present.
4. `engine.load()` pulls model weights into memory (STT).
5. A synchronous `grpc.server(ThreadPoolExecutor(...))` is created. Worker count is
   `max_concurrent_sessions + 4` — with `workers == sessions`, a `HealthCheck` RPC can
   starve behind occupied VAD streams and Core would see a dead plugin.
6. The server binds `unix://<socket>` or `<host>:<port>` and starts.
7. SIGTERM/SIGINT call `server.stop(grace=5)`.

Concurrency is enforced by the **plugin**, with a `threading.Semaphore` acquired
non-blocking. Over-capacity requests are aborted with `RESOURCE_EXHAUSTED` /
`PLUGIN_ERROR_CAPACITY_FULL`, which Core maps to **ERR2008**. Core does not second-guess
this limit.

`HealthCheck` reports `PluginState` (`LOADING`/`READY`/`DRAINING`/`ERROR`), the active
count, and the last `PluginErrorCode`. Out-of-memory transitions the plugin to `ERROR`;
ordinary per-request failures only update `last_error`.

---

## How Core connects

`core/internal/plugin/`:

- **`Endpoint`** wraps one gRPC connection (UDS or TCP) plus a circuit breaker
  (`CLOSED → OPEN → HALF_OPEN`).
- **`VADClient`** opens one `StreamVAD` per session. `Close()` half-closes the send side
  and must **not** cancel the stream context, or in-flight VAD results are lost.
- **`InferenceClient`** wraps unary `Transcribe` and caches capabilities behind an
  `RWMutex`. `FetchCapabilities` runs at endpoint registration, not per session.
- **`InferenceStreamClient`** wraps one `TranscribeStream`. `Close()` half-closes send
  only; `CancelStream()` exists specifically to unblock a stuck `Recv`.
- **`PluginRouter`** holds the inference endpoint pool, implements the three routing modes,
  pins sessions to endpoints (`sync.Map`), and runs the background health probe.

**Engine identity is discovered, not declared.** `plugins.yaml` supplies only an `id`, a
socket or address, and a priority. `engine_name`, `model_size`, `device`, `streaming_mode`
and `endpointing_capability` all come from `GetCapabilities` at runtime, so what Core
reports in `/admin/plugins` and in `engine_name` on results is always what is actually
running. A failed capability fetch is non-fatal: the endpoint registers with empty fields
and a background retry plus the health probe fill them in once the plugin is ready.

### Routing modes (`inference.routing_mode`)

| Mode | Behaviour |
|------|-----------|
| `round_robin` | Cycle through healthy endpoints (atomic counter) |
| `least_connections` | Fewest in-flight RPCs wins |
| `active_standby` | Highest `priority` healthy endpoint; falls back on failure |

`RouteBatch()` filters to `STREAMING_MODE_BATCH_ONLY` endpoints so a unary `Transcribe` is
never sent to a native-streaming engine. `PinByHint(sessionID, hint)` honours the client's
`engine_hint` (which must match the endpoint **`id`** in `plugins.yaml`, e.g.
`whisper-mlx`, not the engine name `mlx_whisper`) and falls back to normal routing when the
hint is empty or that endpoint is unhealthy.

Endpoints can also be added and removed at runtime through the Admin API without restarting
Core — see [../api/client-protocol.md](../api/client-protocol.md#http-admin-api).

---

## Adding an engine

Four places change. The [`add-engine-plugin`](../../.codex/skills/add-engine-plugin/SKILL.md)
skill walks through them:

1. A new `plugin-{stt,vad}-<impl>` repo implementing the Protocol and declaring its entry
   point. Its `AGENTS.md` is a verbatim copy of `plugin-{stt,vad}/templates/AGENTS.md`;
   engine-specific rules go in `ENGINE.md`, started from `templates/ENGINE.md`.
2. An `engine.<name>:` section in the host plugin's `config/*.yaml` with a socket/address
   and every key commented.
3. An endpoint in `core/config/plugins.yaml` (and `deploy/docker/plugins-docker.yaml` for
   Docker).
4. A profile in `workspace.yaml` (and a service in `docker-compose.yml`).

Dependency rules: an engine adapter depends on its host framework and its ML runtime only.
It must never import Core, another engine, or gRPC server machinery.
