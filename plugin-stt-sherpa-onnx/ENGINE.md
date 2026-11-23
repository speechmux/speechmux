# ENGINE.md — sherpa-onnx Zipformer

Engine-specific rules for `plugin-stt-sherpa-onnx`. Common rules for every STT engine
adapter are in `AGENTS.md` beside this file.

---

## Role

Wraps `sherpa-onnx`'s streaming Zipformer transducer. The **only streaming engine**
(`StreamingInferenceEngine`) in the workspace: Core opens one `TranscribeStream` per session
and feeds audio continuously instead of cutting utterances out of the ring buffer
(`../docs/architecture/core-pipeline.md#streaming-decode-engine`). CPU/ARM, low latency;
this is the production path on non-Apple hardware.

It is also the engine Core's whole `endpointing_source` mechanism exists to coordinate.

## Entry point and names

| Name | Value |
|------|-------|
| Entry-point name (`server.engine:`) | `sherpa_onnx_zipformer` |
| Class | `speechmux_plugin_stt_sherpa_onnx.engine:SherpaOnnxEngine` |
| Core endpoint `id` (`engine_hint`) | `sherpa-onnx` |
| Config file | `plugin-stt/config/inference-onnx.yaml`; Docker: `deploy/docker/inference-sherpa-docker.yaml` |

## Layout

Unlike the Whisper engines this package has three source modules:

| Module | Contains |
|--------|----------|
| `engine.py` | `SherpaOnnxEngine.stream()`, `_force_finalize`, `_flush`, `_int16_to_float32`, `_warn_if_empty` |
| `recognizer.py` | `LanguageRecognizers` — one `OnlineRecognizer` per configured language, built at startup |
| `config.py` | Typed dataclasses parsed from the `engine.sherpa_onnx_zipformer` YAML section |

Plus `scripts/download_models.py`.

## Declared capabilities

```python
engine_name = "sherpa_onnx_zipformer"
streaming_mode = STREAMING_MODE_NATIVE
endpointing_capability = ENDPOINTING_CAPABILITY_AUTO_FINALIZE
```

`NATIVE` is what makes Core build a `streamingDecodeEngine` and bypass the
`FairDecodeDispatcher`; `AUTO_FINALIZE` is what makes `endpointing_source: engine` legal
(Core rejects it with **ERR1020** otherwise). Changing either changes Core's behaviour for
every session on this endpoint.

## Configuration

`from_config` parses the whole `engine.sherpa_onnx_zipformer:` section via
`load_config_from_dict`:

| Section | Keys |
|---------|------|
| `recognizer` | `num_threads`, `sample_rate` (must match Core `codec.target_sample_rate`), `feature_dim` |
| `endpoint_detection` | `rule1_min_trailing_silence` (2.4 s), `rule2_min_trailing_silence` (1.2 s), `rule3_min_utterance_length` (20 s) — **only matter in `ENGINE` mode** |
| `models` | `default_language`, `languages.<code>.{encoder,decoder,joiner,tokens}` |

**Only `ko` is configured today.** `en`/`ja` are commented out pending Zipformer2 streaming
checkpoints (`../docs/plans/roadmap.md`). Adding a language is config plus a download.
Paths are workspace-relative natively and `/models/...` in Docker.

## The endpointing contract — read before touching `stream()`

`session_config.endpointing_source` decides who ends an utterance
(`../docs/decisions/0014-endpointing-source.md`):

| Mode | This engine's behaviour |
|------|------------------------|
| `CORE` (and `UNSPECIFIED`) | `recognizer.is_endpoint()` is **not called at all**. Finalization happens only on `KIND_FINALIZE_UTTERANCE`. |
| `ENGINE` | `is_endpoint()` drives finalization; the engine emits `is_final` and resets itself. |

The call is guarded by `if engine_mode and ...` — *removed* from the core path, not gated
behind a text check. That came from fixing a real duplicate-transcript bug: calling it in
`CORE` mode makes both Core and the engine finalize the same utterance.

`is_endpoint()` returns `True` repeatedly on silent frames, so `ENGINE` mode must
`recognizer.reset()` immediately after emitting the final or it re-fires every frame.

## Finalization must flush the lookahead buffer

`_force_finalize` and `_flush` both call `stream.input_finished()` **before**
`get_result()`. Zipformer holds an attention-sink lookahead buffer; without the flush,
tokens still in the unstable region are silently dropped from the final — the "unstable tail
disappears at finalization" bug. Never remove the call or reorder it after `get_result()`.

`_force_finalize` always emits and resets; `_flush` emits only when text remains and runs
once at end-of-stream.

## Thread safety

`LanguageRecognizers` builds one `OnlineRecognizer` per language at startup and the dict is
**read-only afterwards**. Each session gets its own `OnlineStream`. ONNX Runtime's
`InferenceSession.Run()` is safe to call concurrently with different inputs, so concurrent
`decode_stream()` on the shared recognizer needs no lock. Do not create recognizers per
session (weights are large) and do not mutate the dict after startup.

## Runtime specifics

- Pinned to `sherpa-onnx>=1.12.39`: `get_result()` returns a **`str`**, not an object with
  `.text`, and the decode call is `decode_stream()`. Older online examples differ.
- `_warn_if_empty` logs a specific diagnostic when the model returns nothing after ≥0.5 s of
  audio: these models are trained on wideband (0–8 kHz) speech and produce empty output on
  narrowband/telephone audio. Keep it — it is the most common misconfiguration report.
- `stream()` catches any exception, logs it, and **returns** — never raises — so the host
  servicer sees a clean generator end.

## Pitfalls

- Calling `is_endpoint()` in `CORE` mode → duplicated finals.
- Dropping `input_finished()` → truncated finals.
- Forgetting `reset()` after an `ENGINE`-mode final → a final per silent frame.
- This package intentionally has **no `main.py` and no `config/`**; it reuses `plugin-stt`'s.

## Test suite status

**`make test` hangs and never finishes.** Details in
`../docs/development/testing.md#known-issues`, fix plan in
`../docs/plans/test-and-lint-gaps.md`.

- `tests/test_engine.py::test_force_finalize_emits_final` and
  `test_force_finalize_calls_reset` build a bare `MagicMock()` recognizer without
  `is_ready.return_value = False`; `_force_finalize`'s `while recognizer.is_ready(stream):`
  loops forever on a truthy mock. The `_flush` tests set it correctly and pass.
- The four `test_int16_to_float32_*` tests import the engine module without the
  `mock_sherpa_onnx` fixture and need a real `sherpa_onnx` install; they fail with
  `ModuleNotFoundError` otherwise.

Run `pytest tests/test_stream.py -q` (9 passing) meanwhile. Because the workspace
`make test` iterates every plugin, this hang blocks it for the whole workspace — fixing it is
the highest-value change in this package.

`conftest.py`'s `mock_sherpa_onnx` fixture purges cached plugin modules before and after
each test so the mock wins even with the real package installed. Every engine test must take
it.

## Do not

- Add a `main.py` or `config/`.
- Call `is_endpoint()` outside `ENGINE` mode.
- Remove or reorder `input_finished()`.
- Create per-session recognizers or mutate the recognizer dict after startup.
- Change `streaming_mode` / `endpointing_capability` without tracing the effect through
  `PluginRouter.RouteBatch` and `StreamProcessor.ProcessSession`.
