# speechmux/plugin-stt-mlx-whisper

[mlx-whisper](https://github.com/ml-explore/mlx-examples) STT engine plugin for SpeechMux. Depends on `speechmux-plugin-stt` for the `InferenceEngine` Protocol and `TranscribeResult` type. `MlxWhisperEngine` inherits from `InferenceEngine` and is registered via `entry_points` so the base server discovers it automatically when `server.engine: mlx_whisper` is set in the config YAML.

## Features

- **MLX-native inference** — leverages Apple Metal for GPU-accelerated Whisper on M1/M2/M3/M4
- **HuggingFace Hub integration** — loads MLX-format models directly (e.g. `mlx-community/whisper-large-v3-turbo`)
- **Anti-hallucination defaults** — suppresses segments by `no_speech_prob`, `avg_logprob`, and `compression_ratio_threshold`
- **Auto-registered** via `entry_points("speechmux.stt_engine")["mlx_whisper"]`

## Requirements

- Apple Silicon Mac (M1/M2/M3/M4)
- Python 3.10+
- `speechmux-plugin-stt` base package (required dependency)
- `mlx-whisper >= 0.3.0`

## Install

```bash
# Base package must be installed first
pip install speechmux-plugin-stt

# Install mlx-whisper engine
pip install -e ".[dev]"
```

## Run

Run from the workspace root (the config file lives in `plugin-stt/config/`):

```bash
python -m speechmux_plugin_stt.main --config plugin-stt/config/inference.yaml
```

Or from the `plugin-stt/` directory:

```bash
cd ../plugin-stt
python -m speechmux_plugin_stt.main --config config/inference.yaml
```

`server.engine: mlx_whisper` in `inference.yaml` triggers automatic discovery of this package via `entry_points`. The model is downloaded from HuggingFace Hub on first run and cached locally.

## Test

```bash
python -m pytest tests/ -v
```

## Configuration (inference.yaml)

```yaml
engine:
  mlx_whisper:
    model: mlx-community/whisper-large-v3-turbo  # HuggingFace model ID or local path.
    compute_type: float16                         # float16 (Metal fp16) | float32 (fallback).
    language: null                                # null = auto-detect per request.
    beam_size: 5                                  # Beam search width.
```

### Recommended Models

| Model | Size | Speed | Accuracy | Model ID |
|-------|------|-------|----------|----------|
| large-v3-turbo | ~1.5 GB | Fast | High | `mlx-community/whisper-large-v3-turbo` |
| large-v3 | ~3 GB | Moderate | Highest | `mlx-community/whisper-large-v3-mlx` |
| medium | ~1.5 GB | Fast | Good | `mlx-community/whisper-medium-mlx` |
| small | ~500 MB | Very fast | Fair | `mlx-community/whisper-small-mlx` |

## How It Works

1. On startup, the engine loads an MLX-format Whisper model into unified memory (shared CPU/GPU on Apple Silicon)
2. `Transcribe` RPC receives PCM audio from Core
3. Audio is converted to mel spectrogram and decoded using MLX operations on Metal
4. Returns transcription text, per-segment timestamps, and inference timing

## entry_points Registration

```toml
[project.entry-points."speechmux.stt_engine"]
mlx_whisper = "speechmux_plugin_stt_mlx_whisper.engine:MlxWhisperEngine"
```

## License

MIT
