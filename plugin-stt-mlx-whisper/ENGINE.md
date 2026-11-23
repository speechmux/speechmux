# ENGINE.md — mlx-whisper

Engine-specific rules for `plugin-stt-mlx-whisper`. Common rules for every STT engine
adapter are in `AGENTS.md` beside this file.

---

## Role

Wraps `mlx-whisper`, Apple's MLX port of Whisper, running on Metal. **Apple Silicon only** —
there is no CPU fallback. It is a **batch** engine (`InferenceEngine`): Core's VAD and EPD
cut each utterance out of the ring buffer and send it as one `Transcribe` call
(`../docs/architecture/core-pipeline.md#batch-decode-engine`).

Pick it on an M-series Mac; pick `plugin-stt-faster-whisper` anywhere else.

## Entry point and names

| Name | Value |
|------|-------|
| Entry-point name (`server.engine:`) | `mlx_whisper` |
| Class | `speechmux_plugin_stt_mlx_whisper.engine:MlxWhisperEngine` |
| Core endpoint `id` (`engine_hint`) | `whisper-mlx` |
| Config file | `plugin-stt/config/inference-mlx.yaml` |

## Declared capabilities

```python
engine_name = "mlx_whisper"
device = "mlx"
max_concurrent_requests = 1     # MLX is single-threaded on the GPU
supports_partial_decode = True
```

`max_concurrent_requests = 1` is a hardware fact, not a tuning choice. When this is the only
engine, set `stream.fair_dispatch_max_concurrent: 1` in `core.yaml` to match — a higher
value only queues inside MLX, where Core can no longer cancel stale partials
(`../docs/decisions/0011-fair-decode-dispatcher.md`).

`model_size` is an instance attribute set from config, unlike the class-level identity
fields.

## Configuration

`from_config` reads from `engine.mlx_whisper:`:

| Key | Default | Notes |
|-----|---------|-------|
| `model` | `small` | Size alias (`tiny`…`large-v3-turbo`) or a full `mlx-community/...` repo path |
| `compute_type` | `float16` | `float16` / `fp16` / `half` → Metal fp16; anything else → float32 |

`language` and `beam_size` appear in the shipped YAML section but are **not consumed** by
`from_config`; language arrives per request, and `beam_size` is unsupported (below).

## Runtime specifics

**Eager loading.** `load()` calls `ModelHolder.get_model(repo, dtype)`. `_MODEL_REPO_MAP`
translates plain size names into `mlx-community/...` repo paths; a full path in config is
passed through unchanged.

**Anti-hallucination defaults** applied by `_build_options` on **every** request:

| Option | Value | Why |
|--------|-------|-----|
| `no_speech_threshold` | 0.6 | Suppress segments the model itself thinks are silence |
| `logprob_threshold` | -1.0 | Discard low-confidence segments |
| `compression_ratio_threshold` | 2.4 | Discard repetitive output (the classic Whisper loop) |
| `condition_on_previous_text` | `False` | Prevent one bad hypothesis poisoning every later partial |

`condition_on_previous_text = False` matters here specifically: Core re-decodes a growing
segment on every partial, so conditioning would cascade a hallucination through the whole
utterance. Segments whose `no_speech_prob` exceeds the threshold are also dropped after
decoding, with a log line.

Caller-supplied `decode_options` override the defaults, via the `key_map` in
`_build_options`. **`beam_size` and `best_of` are silently ignored** — mlx-whisper does not
expose them. Worth remembering when someone reports that `decode_profile: accurate` changes
nothing on this engine (it currently changes nothing on any engine —
`../docs/plans/decode-options-and-task-passthrough.md`).

## Pitfalls

- The entry-point name (`mlx_whisper`) and the Core endpoint id (`whisper-mlx`) differ.
  Clients pass the **id** as `engine_hint`. This is the most common support question.
- `ImportError` on `mlx_whisper` is caught and re-raised with an install hint. Keep it.

## Test suite status

`make test` → 10 passing. `tests/test_mlx_engine.py` injects
`sys.modules["mlx_whisper"] = MagicMock()` before importing the engine, so the suite runs on
non-Apple hardware with no model weights.

## Do not

- Enable `condition_on_previous_text`.
- Raise `max_concurrent_requests` above 1.
- Pretend `beam_size` has an effect.
