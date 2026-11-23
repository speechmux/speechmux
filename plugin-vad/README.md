# speechmux/plugin-vad

VAD (Voice Activity Detection) plugin base framework. Provides the gRPC servicer, the `VADEngine` Protocol (interface), a Dummy engine for load testing, and an `entry_points`-based engine auto-discovery system.

## Structure

```
plugin-vad/
├── src/speechmux_plugin_vad/
│   ├── main.py               # UDS gRPC server entry point
│   ├── service/
│   │   └── vad_servicer.py   # StreamVAD + GetCapabilities + HealthCheck
│   ├── engine/
│   │   ├── base.py           # VADEngine Protocol (interface)
│   │   ├── dummy.py          # DummyVADEngine (no model, fixed probability)
│   │   └── registry.py       # entry_points-based engine auto-discovery
│   └── state/
│       └── session_state.py  # SessionVADState wrapper
├── tests/
│   └── test_vad_servicer.py  # Protocol tests with Dummy engine
├── config/
│   ├── vad.yaml
│   └── vad-dummy.yaml
└── pyproject.toml
```

## Install

```bash
pip install -e ".[dev]"
```

## Run

All configuration — socket path, engine selection, and engine parameters — is read from the YAML config file. Run from the `plugin-vad/` directory:

```bash
# Silero engine (after installing plugin-vad-silero)
python -m speechmux_plugin_vad.main --config config/vad.yaml

# Dummy engine (load testing, no model required)
python -m speechmux_plugin_vad.main --config config/vad-dummy.yaml
```

Socket path and engine name are set in the config file under `server.socket` and `server.engine`.

## Test

```bash
python -m pytest tests/ -v
ruff check src/
mypy src/
```

## gRPC Services

### StreamVAD (bidirectional streaming)

One stream per session. gRPC's thread pool assigns a worker thread per stream, so sessions run concurrently without explicit multiplexing.

**Protocol:**

1. First message: `VADRequest { session_start { session_id, threshold } }`
2. Audio frames: `VADRequest { pcm_data, sample_rate, sequence_number }`
3. Server yields: `VADResponse { is_speech, speech_probability, chunk_rms, chunk_duration_sec, sequence_number }`
4. End: `VADRequest { session_end {} }` → stream closes

Core uses the echoed `sequence_number` to match VAD results against the `AudioRingBuffer` for accurate speech segment extraction.

### GetCapabilities

Returns `VADCapabilities`:
- `model_name` — engine identifier (e.g. `"silero_vad_v5"`, `"dummy_vad"`)
- `optimal_frame_ms` — preferred frame size (Core's `frameAggregator` aggregates to this)
- `max_concurrent_sessions` — declared capacity
- `supported_sample_rates` — list of supported rates

### HealthCheck

Returns `PluginHealthStatus` with `PluginState` (LOADING/READY/DRAINING/ERROR), active session count, and last error code. Core uses this for routing decisions and circuit breaker state.

## Configuration (vad.yaml)

```yaml
server:
  socket: /tmp/speechmux/vad.sock  # UDS path. Must match plugins.yaml endpoint socket.
  engine: silero                    # Engine entry-point name (speechmux.vad_engine group).
  log_level: INFO                   # DEBUG | INFO | WARNING | ERROR.
  max_concurrent_sessions: 50       # Max concurrent StreamVAD sessions.

engine:
  silero:
    threshold: 0.5             # Speech probability threshold (0.0–1.0).
    min_speech_duration_ms: 250
    min_silence_duration_ms: 100
    optimal_frame_ms: 32       # 32ms = 512 samples @ 16kHz.
```

## VADEngine Protocol

To implement a custom VAD engine:

```python
class MyVADEngine:
    model_name: str = "my_engine"
    optimal_frame_ms: int = 20
    supported_sample_rates: list[int] = [16000]
    max_concurrent_sessions: int = 100

    def create_session_state(self, threshold: float) -> MyState:
        """Create per-session state (model copy, buffers, etc.)."""
        ...

    def process_frame(
        self, session_state: object, pcm_data: bytes, sample_rate: int,
    ) -> tuple[bool, float, float]:
        """Process one audio frame. Returns (is_speech, probability, chunk_rms)."""
        # Protocol requires `object`; cast to your concrete state type inside.
        assert isinstance(session_state, MyState)
        ...
```

## Engine Plugin System

Register a new engine under the `speechmux.vad_engine` entry_points group:

```toml
[project.entry-points."speechmux.vad_engine"]
my_engine = "my_package:MyVADEngine"
```

After `pip install my-vad-engine`, set `server.engine: my_engine` in the config YAML. The registry discovers engines automatically via `importlib.metadata.entry_points()`.

## Dummy Engine

`DummyVADEngine` returns a fixed speech probability without loading any model. Supports two modes:

- **Fixed mode** (default): every frame returns `speech_prob`
- **Cycle mode** (`speech_ms > 0`): alternates between speech and silence windows, triggering EPD in the Core pipeline during load tests

Edit `config/vad-dummy.yaml` to set `speech_prob`, `latency_ms`, `speech_ms`, and `silence_ms`, then run:

```bash
python -m speechmux_plugin_vad.main --config config/vad-dummy.yaml
```

## Error Handling

Plugins report errors via `PluginErrorCode` enum (never Core's `ERR####` codes):

| Error | Meaning |
|-------|---------|
| `PLUGIN_ERROR_INFERENCE_FAILED` | `process_frame` exception — yielded in `VADResponse` |

Capacity limit (`max_concurrent_sessions` exceeded) is handled separately:
the servicer calls `context.abort(RESOURCE_EXHAUSTED)` directly, not via `PluginErrorCode`.

Core translates plugin errors to the appropriate `ERR####` code at the boundary.

## License

MIT
