# ENGINE.md — faster-whisper

Engine-specific rules for `plugin-stt-faster-whisper`. Common rules for every STT engine
adapter are in `AGENTS.md` beside this file.

---

## Role

Wraps `faster-whisper`, the CTranslate2 port of Whisper. **CPU anywhere, CUDA where a GPU
exists** — the portable Whisper option, in contrast to `plugin-stt-mlx-whisper`. It is a
**batch** engine (`InferenceEngine`).

## Entry point and names

| Name | Value |
|------|-------|
| Entry-point name (`server.engine:`) | `faster_whisper` |
| Class | `speechmux_plugin_stt_faster_whisper.engine:FasterWhisperEngine` |
| Core endpoint `id` (`engine_hint`) | `faster-whisper` (Docker `plugins-docker.yaml`) |
| Config file | `config/inference-faster-whisper.yaml` in **this** repo; Docker: `deploy/docker/inference-faster-whisper-docker.yaml` |

This is the one Whisper engine that ships its own config file rather than using one in
`plugin-stt/config/`.

## Declared capabilities

```python
engine_name = "faster_whisper"
device = "cpu"                  # class default; the instance follows config
max_concurrent_requests = 4     # CTranslate2 does support concurrent execution
supports_partial_decode = True
```

`4` is real concurrency, unlike mlx-whisper's `1` — but it still competes for one CPU or
GPU. Set `server.max_concurrent_sessions` and Core's `stream.fair_dispatch_max_concurrent`
to what the hardware sustains, not to 4 by reflex. The shipped Docker config uses `1`.

## Configuration

`from_config` reads from `engine.faster_whisper:`:

| Key | Default | Notes |
|-----|---------|-------|
| `model` | `small` | Size name (`tiny`…`large-v3`) or a HuggingFace ID |
| `device` | `cpu` | `cpu` \| `cuda` \| `auto` |
| `compute_type` | `int8` | `float16` \| `int8_float16` \| `int8` |

`device` + `compute_type` is the deployment knob: `int8` on CPU, `float16` on CUDA. A
mismatch (`float16` on CPU) either fails at load or silently falls back and runs slowly.
`language` and `beam_size` in the YAML section are not consumed at construction.

## Runtime specifics

**Batched inference.** A `BatchedInferencePipeline` is built alongside the model and used
only when a request carries `batch_size > 1`. `_build_opts` returns `(opts, batch_size)` as
a **pair** because `batch_size` is a pipeline-level argument, not a model argument — passing
it inside `opts` to `WhisperModel.transcribe` raises. `batch_size` is not in the proto
`DecodeOptions`, so today nothing sets it.

**Model download.** Weights come from HuggingFace on first `load()`; no `/models` mount is
needed. The Compose health check allows a 90 s `start_period` for that.

## Pitfalls

- Never merge `batch_size` into `opts`.
- `device: auto` must degrade to CPU without failing.

## Docker

`Dockerfile` is based on `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`. GPU execution needs
`nvidia-container-toolkit` and a CUDA 12.4+ driver on the host; the shipped Compose service
runs on CPU.

- Build context is the **workspace root**, not this directory — the Dockerfile needs
  `proto/` and `plugin-stt/`.
- It reuses `plugin-stt/uv.lock` instead of carrying its own lockfile, and copies
  `plugin-stt` to `/tmp/plugin-stt` so the `[tool.uv.sources]` path reference in
  `pyproject.toml` resolves. Changing the layout means changing both files.

## Test suite status

`make test` → 15 passing. `tests/test_faster_whisper_engine.py` injects
`sys.modules["faster_whisper"] = MagicMock()` before importing the engine; no CTranslate2 or
weights needed.

## Do not

- Pass `batch_size` through `opts`.
- Assume CUDA is present.
- Break the `[tool.uv.sources]` ↔ Dockerfile pairing.
