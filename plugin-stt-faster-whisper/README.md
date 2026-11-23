# speechmux/plugin-stt-faster-whisper

[faster-whisper](https://github.com/SYSTRAN/faster-whisper) STT engine plugin for SpeechMux. Depends on `speechmux-plugin-stt` for the `InferenceEngine` Protocol and `TranscribeResult` type. `FasterWhisperEngine` satisfies the Protocol via structural subtyping (duck typing) — no class inheritance. It is registered via `entry_points` so the base server discovers it automatically with `server.engine: faster_whisper` in the config YAML.

## Features

- **CTranslate2 backend** — 4x faster than original Whisper with lower memory usage
- **CPU and CUDA support** — runs on any x86/ARM CPU or NVIDIA GPU
- **INT8/FP16 quantization** — reduced model size and faster inference
- **Auto-registered** via `entry_points("speechmux.stt_engine")["faster_whisper"]`

## Requirements

- Python 3.10+
- `speechmux-plugin-stt` base package (local: `../plugin-stt`)
- `faster-whisper >= 1.0.0`
- NVIDIA GPU + CUDA toolkit (optional, for GPU acceleration)

## Install

```bash
# From workspace root — installs plugin-stt base and faster-whisper adapter together:
cd plugin-stt && pip install -e .
cd ../plugin-stt-faster-whisper && pip install -e ".[dev]"
```

## Run

All configuration (socket path, engine selection, engine parameters) lives in the YAML config file.

```bash
# From workspace root:
python -m speechmux_plugin_stt.main \
    --config plugin-stt-faster-whisper/config/inference-faster-whisper.yaml
```

## Test

```bash
python -m pytest tests/ -v
ruff check src/
mypy src/
```

## Configuration (inference-faster-whisper.yaml)

```yaml
server:
  socket: /tmp/speechmux/stt-faster-whisper.sock  # Must match plugins.yaml endpoint socket.
  engine: faster_whisper
  log_level: INFO
  max_concurrent_sessions: 4
  log_transcription_text: true

engine:
  faster_whisper:
    model: large-v3       # Model size or HuggingFace ID.
    device: auto          # auto | cpu | cuda.
    compute_type: float16 # float16 (GPU) | int8_float16 (low-VRAM GPU) | int8 (CPU).
    language: null        # null = auto-detect per request.
    beam_size: 5
```

### Recommended Configurations

| Environment | `device` | `compute_type` | Notes |
|-------------|----------|----------------|-------|
| NVIDIA GPU (8+ GB VRAM) | `cuda` | `float16` | Best throughput |
| NVIDIA GPU (4 GB VRAM) | `cuda` | `int8_float16` | Reduced memory |
| CPU server | `cpu` | `int8` | Quantized for speed |

## Docker

```bash
# From workspace root (context must be workspace root for proto/ and plugin-stt/):
docker compose --profile faster-whisper up
```

Requires `nvidia-container-toolkit` on the host and a CUDA 12.4+ driver.
The model directory is mounted at `/models` via the `MODELS_DIR` env var (default: `./plugin-stt-faster-whisper/models`).

## entry_points Registration

```toml
[project.entry-points."speechmux.stt_engine"]
faster_whisper = "speechmux_plugin_stt_faster_whisper.engine:FasterWhisperEngine"
```

## License

MIT
