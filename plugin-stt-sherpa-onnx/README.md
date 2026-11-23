# speechmux/plugin-stt-sherpa-onnx

[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) Zipformer streaming STT engine plugin for SpeechMux. Depends on `speechmux-plugin-stt` for the `StreamingInferenceEngine` Protocol and gRPC servicer. `SherpaOnnxEngine` implements `StreamingInferenceEngine` and is registered via `entry_points` so the base server discovers it automatically when `server.engine: sherpa_onnx_zipformer` is set in the config YAML.

## Features

- **Native streaming inference** — Zipformer transducer runs frame-by-frame; no buffering until end-of-utterance
- **Built-in endpoint detection** — sherpa-onnx EPD fires utterance boundaries independently (no Core VAD dependency for segmentation)
- **Multi-language** — any number of language models loaded simultaneously; language selected per request from `language_code` (ko/en/ja shown as examples; any sherpa-onnx streaming Zipformer model can be configured)
- **CPU-compatible** — runs on any x86-64 or ARM64 host; no GPU required
- **Auto-registered** via `entry_points("speechmux.stt_engine")["sherpa_onnx_zipformer"]`

## Requirements

- Python 3.10+
- `speechmux-plugin-stt` base package (required dependency)
- `sherpa-onnx >= 1.12.39`
- ONNX model files downloaded locally (see [Download Models](#download-models))

## Install

```bash
# Base package must be installed first
pip install speechmux-plugin-stt

# Install sherpa-onnx engine
pip install -e ".[dev]"
```

## Download Models

Model files are not bundled. Download them with the provided script before starting the plugin.

```bash
# Korean only (most common)
python scripts/download_models.py --lang ko

# Multiple languages
python scripts/download_models.py --lang ko --lang en --lang ja

# All supported languages
python scripts/download_models.py --all

# Custom output directory (default: models/)
python scripts/download_models.py --lang ko --model-dir /data/models/sherpa
```

The script fetches int8-quantized Zipformer models from HuggingFace Hub:

| Language | HuggingFace Repo | Size (int8) |
|----------|-----------------|-------------|
| `ko` | `k2-fsa/sherpa-onnx-streaming-zipformer-korean-2024-06-16` | ~60 MB |
| `en` | `csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-06-26` | ~70 MB |
| `ja` | `reazon-research/reazonspeech-k2-v2` | ~90 MB |

> **Note:** The English model uses chunk/left-context filename suffixes that differ from the download script's defaults. If automatic download fails for `en`, download the files manually from the HuggingFace repo and update `config/inference.yaml` directly.

After downloading, update `config/inference.yaml` with the absolute paths shown by the script output.

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

`server.engine: sherpa_onnx_zipformer` in `inference.yaml` triggers automatic discovery of this package via `entry_points`. All language models listed under `models.languages` are loaded into memory at startup.

## Test

```bash
python -m pytest tests/ -v
```

## Configuration (inference.yaml)

```yaml
server:
  socket: /tmp/speechmux/stt-sherpa.sock  # UDS path; must match plugins.yaml endpoint socket.
  engine: sherpa_onnx_zipformer           # Activates this plugin.
  max_concurrent_sessions: 10            # Tune to available CPU cores.

engine:
  sherpa_onnx_zipformer:
    recognizer:
      num_threads: 2       # ONNX Runtime intra-op threads per recognizer. Increase on many-core hosts.
      sample_rate: 16000   # Hz; must match Core codec.target_sample_rate.
      feature_dim: 80      # Mel-filterbank bins; must match model training config (80 for Zipformer).

    endpoint_detection:
      rule1_min_trailing_silence: 2.4   # sec; silence after any speech.
      rule2_min_trailing_silence: 1.2   # sec; silence after ≥1.0 s of confirmed speech.
      rule3_min_utterance_length: 20.0  # sec; force-finalize regardless of silence.

    models:
      default_language: ko  # Fallback when session language_code is absent or unsupported.
      languages:
        ko:
          encoder: /path/to/models/ko/encoder-epoch-99-avg-1.int8.onnx
          decoder: /path/to/models/ko/decoder-epoch-99-avg-1.int8.onnx
          joiner:  /path/to/models/ko/joiner-epoch-99-avg-1.int8.onnx
          tokens:  /path/to/models/ko/tokens.txt
        en:
          encoder: /path/to/models/en/encoder-epoch-99-avg-1.int8.onnx
          decoder: /path/to/models/en/decoder-epoch-99-avg-1.int8.onnx
          joiner:  /path/to/models/en/joiner-epoch-99-avg-1.int8.onnx
          tokens:  /path/to/models/en/tokens.txt
        ja:
          encoder: /path/to/models/ja/encoder-epoch-99-avg-1.int8.onnx
          decoder: /path/to/models/ja/decoder-epoch-99-avg-1.int8.onnx
          joiner:  /path/to/models/ja/joiner-epoch-99-avg-1.int8.onnx
          tokens:  /path/to/models/ja/tokens.txt
```

Languages not listed under `models.languages` are not loaded. Remove unused language blocks to save memory.

## How It Works

1. On startup, one `OnlineRecognizer` is created per configured language and held for the process lifetime
2. `StreamTranscribe` RPC receives PCM S16LE audio frames from Core in a bidirectional stream
3. Each frame is converted to float32, fed into a per-session `OnlineStream`, and decoded in real time
4. sherpa-onnx EPD fires utterance-boundary signals; the engine emits `is_final=True` responses and resets the stream
5. Returns partial and final hypotheses with text as audio arrives — no wait for silence

## entry_points Registration

```toml
[project.entry-points."speechmux.stt_engine"]
sherpa_onnx_zipformer = "speechmux_plugin_stt_sherpa_onnx.engine:SherpaOnnxEngine"
```

## License

MIT
