# Configuration

All configuration is YAML. Every key in every file carries an inline comment describing its
purpose and unit — that convention is mandatory when adding a key.

Adding a key: use the [`add-config-option`](../../.codex/skills/add-config-option/SKILL.md)
skill, which covers the Go struct, the default, all copies of the file, and this document.

---

## Files

### Native (local dev)

| File | Loaded by | Purpose |
|------|-----------|---------|
| `core/config/core.yaml` | `speechmux-core --config` | Ports, session limits, pipeline tuning, auth, TLS, OTel, decode profiles |
| `core/config/plugins.yaml` | `speechmux-core --plugins` | VAD and inference endpoint pools, routing mode, circuit breakers |
| `workspace.yaml` (repo root) | `speechmux-core ctl --workspace` | Process list and engine profiles for the supervisor |
| `plugin-vad/config/vad.yaml` | `speechmux_plugin_vad.main --config` | VAD socket, engine, log level, Silero tuning |
| `plugin-stt/config/inference-onnx.yaml` | `speechmux_plugin_stt.main --config` | sherpa-onnx endpoint and models |
| `plugin-stt/config/inference-mlx.yaml` | same | mlx-whisper endpoint and model |
| `plugin-stt-faster-whisper/config/inference-faster-whisper.yaml` | same | faster-whisper endpoint and model |
| `*-dummy.yaml`, `core/config/plugins-dummy.yaml` | same | No-model engines for load testing |

`core/config/workspace.yaml` also exists inside the core repo as a self-contained example.
The workspace supervisor uses the root `workspace.yaml`, which has the two-level profile
system.

### Docker

| File | Mounted at | Notes |
|------|-----------|-------|
| `deploy/docker/core-docker.yaml` | `/etc/speechmux/core.yaml` | Same schema as `core.yaml` |
| `deploy/docker/plugins-docker.yaml` | `/etc/speechmux/plugins.yaml` | Uses TCP `address` (Compose DNS) instead of UDS `socket` |
| `deploy/docker/vad-docker.yaml` | `/etc/speechmux/vad.yaml` | |
| `deploy/docker/inference-sherpa-docker.yaml` | `/etc/speechmux/inference.yaml` | Model paths under `/models` |
| `deploy/docker/inference-faster-whisper-docker.yaml` | `/etc/speechmux/inference.yaml` | Model auto-downloaded from HuggingFace |
| `.env` (from `.env.example`) | — | Host port bindings, `MODELS_DIR`, auth tokens, CORS |

**Every `core.yaml` key you add must be added to `deploy/docker/core-docker.yaml` too.**
The two files drift easily; they are currently out of sync (see the end of this page).

---

## `core.yaml`

Backing struct: `core/internal/config/config.go`. Defaults are applied by
`Config.Defaults()`; durations are converted and validated by `Config.Validate()`.

### `server`

| Key | Default | Meaning |
|-----|---------|---------|
| `grpc_port` | 50051 | `StreamingRecognize` |
| `http_port` | 8000 (file sets 8090) | `/health`, `/metrics`, `/admin` |
| `ws_port` | 8001 (file sets 8091) | Browser WebSocket |
| `max_sessions` | 50 (file sets 1000) | Concurrent session cap → ERR1011 |
| `session_timeout_sec` | 60 | Idle timeout; parked sessions are exempt |
| `shutdown_drain_sec` | 30 | Drain window in phase 2 of graceful shutdown |
| `resumable_session_timeout_sec` | 0 | Park-and-resume window. `0` disables resume; 30–60 suits mobile clients |
| `allowed_origins` | `[]` | WebSocket `Origin` allow-list. **Empty = allow all** |
| `http_read_timeout_sec` | 10 | Slow-loris protection |
| `http_write_timeout_sec` | 10 | Includes handler execution |
| `http_idle_timeout_sec` | 60 | Keep-alive idle |
| `http_shutdown_timeout_sec` | 5 | HTTP graceful shutdown |

Note the file values (8090/8091/1000) differ from the code defaults (8000/8001/50). The
code defaults only apply when a key is absent.

### `stream`

| Key | Default | Meaning |
|-----|---------|---------|
| `vad_silence_sec` | 0.5 (file sets 0.2) | Trailing silence before EPD fires. 200–300 ms suits conversation; 400–500 ms suits deliberate monologue |
| `vad_threshold` | 0.5 | Speech probability threshold |
| `speech_rms_threshold` | 0.02 | RMS below this forces a frame to silence regardless of VAD |
| `partial_decode_interval_sec` | 1.5 | Base partial interval; auto-widens to 3 s (>5 s audio) and 5 s (>10 s) |
| `partial_decode_window_sec` | 10.0 | Max audio window per partial decode |
| `decode_timeout_sec` | — | Per-request STT timeout → ERR2001 |
| `max_buffer_sec` | 20 | Ring-buffer size in seconds |
| `buffer_overlap_sec` | 0.5 | Overlap retained at utterance start to avoid clipping |
| `emit_final_on_vad` | false | Emit a final on EPD without waiting for STT |
| `vad_frame_timeout_sec` | 3.0 | Silent-hang detection → ERR3004 |
| `epd_heartbeat_interval_sec` | — | Liveness log interval during silence; `0` disables |
| `vad_watermark_lag_threshold_sec` | 0 (disabled) | BATCH terminates with ERR3004; REALTIME warns only. Disabled by default because file input outruns real time |
| `endpointing_source` | `core` | `core` (VAD+EPD) or `engine` (engine auto-finalize). `hybrid` is rejected at load |
| `streaming_finalize_timeout_sec` | 3.0 | Wait for `is_final` after `FINALIZE_UTTERANCE` → ERR3007 |
| `engine_response_timeout_sec` | 5.0 | Lag watchdog for `endpointing_source: engine`; `0` disables |
| `max_utterance_sec` | 30.0 | Force finalize when the engine emits no `is_final`; `0` disables |
| `fair_dispatch_max_concurrent` | 1 | Parallel `Transcribe` RPCs across **all** sessions. `1` for single-GPU engines; `0` = unlimited |
| `fair_dispatch_max_partial_queue` | 0 (unlimited) | Per-session partial queue cap. A reasonable start is `ceil(session_timeout_sec / partial_decode_interval_sec)` ≈ 20; 4–6 to aggressively drop stale partials |

`fair_dispatch_max_concurrent` is the single most impactful knob for batch throughput.
Raising it above the engine's real parallelism only adds queueing latency.

### Other sections

| Section | Keys |
|---------|------|
| `decode` | `max_streaming_sessions` (16; `0` = unlimited) — streaming-session semaphore |
| `codec` | `target_sample_rate` (16000) — everything is resampled to this |
| `rate_limit` | `create_session_rps`, `create_session_burst`, `max_sessions_per_ip`, `max_sessions_per_api_key`, `http_rps`, `http_burst` |
| `auth` | `require_api_key`, `auth_profile` (`none`/`api_key`/`signed_token`), `auth_secret` (also the admin token), `auth_ttl_sec` |
| `storage` | `enabled`, `directory`, plus optional `max_bytes`, `max_files`, `max_age_days` (janitor limits, absent from the shipped file) |
| `logging` | `level` (`debug`/`info`/`warn`/`error`), `format` (`json`/`text`/`color`), optional `file` |
| `tls` | `tls_required`, `cert_file`, `key_file` |
| `otel` | `endpoint` (empty = tracing disabled), `service_name`, `sample_rate` |
| `decode_profiles` | Named hyperparameter sets (`realtime`, `accurate`) selected by `RecognitionConfig.decode_profile` |

`decode_profiles` are parsed, negotiated and echoed back to the client, but are **not yet
forwarded to the STT plugin** — see
[../plans/decode-options-and-task-passthrough.md](../plans/decode-options-and-task-passthrough.md).

---

## `plugins.yaml`

```yaml
vad:
  endpoints:
    - id: "vad-0"                        # Appears in health reports.
      socket: "/tmp/speechmux/vad.sock"  # UDS. Use `address: host:port` for TCP instead.
  health_check_interval_sec: 10
  circuit_breaker:
    failure_threshold: 5
    half_open_timeout_sec: 30

inference:
  routing_mode: "least_connections"      # round_robin | least_connections | active_standby
  endpoints:
    - id: "whisper-mlx"                  # This id is what clients pass as engine_hint.
      socket: "/tmp/speechmux/stt-mlx.sock"
      priority: 1                        # Higher = preferred under active_standby.
  health_check_interval_sec: 10
  health_probe_timeout_sec: 5
  circuit_breaker:
    failure_threshold: 5
    half_open_timeout_sec: 30
```

`socket` and `address` are mutually exclusive per endpoint: UDS locally, TCP in Docker.
The endpoint `id` is the routing identity — it is what `engine_hint` matches and what
appears in `/admin/plugins`. Engine name, model size and device are **not** configured
here; they come from `GetCapabilities` at runtime.

VAD sessions are assigned round-robin across the VAD endpoint pool.

---

## Plugin configs

Both plugin frameworks take exactly one CLI flag, `--config`. Everything else is in the file.

```yaml
server:
  socket: /tmp/speechmux/stt-mlx.sock   # XOR with `address: "0.0.0.0:50061"`
  engine: mlx_whisper                    # Entry-point name from the speechmux.stt_engine group
  log_level: INFO
  max_concurrent_sessions: 4             # Overrides the engine default; also sizes the thread pool (+4)
  log_transcription_text: true           # false logs a character count instead of the transcript

engine:
  mlx_whisper:                           # Only the section named by server.engine is read
    model: mlx-community/whisper-large-v3-turbo
    compute_type: float16
    language: null
    beam_size: 5
```

A config file may hold sections for engines that are not installed; only
`engine.<server.engine>` is read. The section keys map to the engine's `from_config`
classmethod, so they are engine-specific — see that engine's `AGENTS.md` and `README.md`.

`plugin-vad/config/vad.yaml` follows the same shape with a `silero:` section
(`threshold`, `min_speech_duration_ms`, `min_silence_duration_ms`, `optimal_frame_ms`).

---

## `workspace.yaml`

Consumed by `speechmux-core ctl`. Two levels:

- **`profiles:`** — a template library, grouped by category (`vad-plugins`, `stt-plugins`).
  Each named profile is a full process definition: `command`, `args`, `working_directory`,
  `restart` (`always`/`on-failure`/`never`), `startup_delay_ms`.
- **`processes:`** — the ordered start list. A *slot* entry has a `name` matching a category
  key plus a `profiles:` list of the profiles that may fill it; only those activated with
  `--profile` actually start. A *direct* entry (no `profiles:`) always starts.

`state_dir` (default `/tmp/speechmux`) holds PID files and process logs.
`ctl status` scans that directory, so it needs no `--profile` flags.

Activate profiles with `make up PROFILES="silero sherpa-onnx"` — see
[deployment.md](deployment.md).

---

## Hot reload

`core.yaml` reloads on `SIGHUP` or `POST /admin/reload`. Concurrent reloads are serialised
by a mutex, and readers see the new config through an `atomic.Pointer` swap.

| Takes effect | Keys |
|--------------|------|
| **Immediately** (next pipeline tick) | `stream.vad_silence_sec`, `stream.vad_threshold`, `stream.speech_rms_threshold`, `stream.decode_timeout_sec`, `stream.partial_decode_interval_sec` |
| **New sessions only** | `server.max_sessions`, `auth.*`, `codec.target_sample_rate`, `rate_limit.*`, `decode_profiles.*` |
| **Requires restart** | `server.grpc_port`, `server.http_port`, `server.ws_port`, `tls.*` |
| **Not reloaded at all** | `plugins.yaml` — use the Admin API to add/remove endpoints at runtime |

An engine snapshots `stream` config at session start, so a reload does not affect a session
already in flight.

---

## Known config drift

Verified by comparing key sets on the current tree:

- `deploy/docker/core-docker.yaml` still sets `decode.max_pending`, which no longer exists
  in `config.DecodeConfig` (it was removed with `DecodeScheduler.Submit()`). Unknown keys
  are ignored by the loader, so this is inert but misleading.
- `deploy/docker/core-docker.yaml` is missing `logging.format`,
  `stream.fair_dispatch_max_concurrent` and `stream.fair_dispatch_max_partial_queue`, so
  the Docker deployment silently takes the code defaults (`json`, `1`, `0`).
- `core/config/plugins.yaml` comments point at `plugin-stt/config/inference-sherpa-onnx.yaml`;
  the file is actually `inference-onnx.yaml`.

These are tracked in [../plans/roadmap.md](../plans/roadmap.md).
