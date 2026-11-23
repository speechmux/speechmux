# AGENTS.md — plugin-vad

VAD plugin **host framework**. Assumes the repository root `AGENTS.md`; only what is
specific to this package is here.

Root instructions: `../AGENTS.md` · Architecture:
`../docs/architecture/plugin-system.md` · Wire contract:
`../docs/api/plugin-protocol.md`

---

## Role

This package is the gRPC server, the config loader and the engine contract for voice activity
detection. It ships no real model — only a `dummy` engine for load testing. Actual
detection lives in engine adapter packages (`plugin-vad-silero`).

Changing anything here affects **every** VAD engine.

## Boundary with Core

Core opens one `StreamVAD` stream per session and never multiplexes
(`../docs/decisions/0004-per-session-vad-stream.md`). Two obligations this package must keep:

1. **Echo `sequence_number` unchanged** on every `VADResponse`. Core uses it to locate the
   speech segment in its ring buffer and to advance the trim watermark. Losing or
   reordering it silently breaks utterance extraction.
2. **Never emit `ERR####`.** Report a `common.v1.PluginErrorCode`; Core translates it.

The plugin owns concurrency. Over-capacity streams are refused here with
`RESOURCE_EXHAUSTED`, and Core does not second-guess the limit.

## Entry point

```bash
python -m speechmux_plugin_vad.main --config plugin-vad/config/vad.yaml
```

`--config` is the **only** CLI flag. Socket/address, engine name, log level and concurrency
all come from the file. Do not add flags — engine selection and tuning belong in YAML.

## Layout

| Path | Contains |
|------|----------|
| `src/speechmux_plugin_vad/main.py` | Arg parsing, YAML loading, engine construction, gRPC server, signal handling |
| `src/speechmux_plugin_vad/service/vad_servicer.py` | `StreamVAD`, `GetCapabilities`, `HealthCheck` |
| `src/speechmux_plugin_vad/engine/base.py` | The `VADEngine` Protocol — **public API for every engine package** |
| `src/speechmux_plugin_vad/engine/registry.py` | Entry-point lookup (`speechmux.vad_engine`) |
| `src/speechmux_plugin_vad/engine/dummy.py` | No-model engine for load testing |
| `src/speechmux_plugin_vad/state/session_state.py` | Shared per-session state helpers |
| `config/vad.yaml`, `config/vad-dummy.yaml` | Reference configs |
| `templates/AGENTS.md` | **Canonical `AGENTS.md` for every `plugin-vad-*` engine** — copied verbatim into each |
| `templates/ENGINE.md` | Skeleton for an engine's engine-specific document |

`engine/base.py` is the one file engine packages import. Treat it as a published API.

## Build, test, lint

```bash
make install     # uv pip install -e ".[dev]" into ../.venv
make test        # pytest tests/ -v          → 11 passing
make lint        # ruff check src/
make typecheck   # mypy src/
make run-dummy   # start with config/vad-dummy.yaml
```

Known baseline (do not report as regressions, and see
`../docs/plans/test-and-lint-gaps.md`):

- `make lint` reports 5 findings under ruff 0.16.5 (`UP037`, `I001`) — the pin is
  `ruff>=0.4` with no upper bound.
- `make typecheck` fails with one error: `Class cannot subclass "VADPluginServicer" (has
  type "Any")`. `plugin-stt/pyproject.toml` has a `[[tool.mypy.overrides]]` block with
  `ignore_missing_imports` for `grpc.*` / `stt_proto.*` that this package lacks. Copying it
  across is the fix.

## Engines share one `AGENTS.md`, owned here

Every `plugin-vad-*` directory carries a byte-identical `AGENTS.md` copied from
`templates/AGENTS.md`, plus its own `ENGINE.md` for engine-specific rules, plus a
`CLAUDE.md` containing only `@AGENTS.md`. A new engine author copies both templates, adds
that one-line file, and fills in `ENGINE.md` only.

When you change `templates/AGENTS.md`, re-copy it into **every** engine directory in the same
piece of work, and verify with:

```bash
for d in ../plugin-vad-*/; do cmp -s templates/AGENTS.md "$d/AGENTS.md" || echo "DRIFT: $d"; done
```

Never put something engine-specific in the template, and never put a common rule in an
engine's `ENGINE.md`.

## Dependencies

`grpcio`, `protobuf`, `pyyaml`, and `speechmux-proto`. That is the whole list and it should
stay that way — **no ML runtime here**. `numpy`, `torch` and friends belong in engine packages.

## Changing the `VADEngine` Protocol

Adding a required attribute or method breaks every engine adapter, in other packages,
at runtime rather than at build time. Before changing `engine/base.py`:

- Prefer an optional attribute with a framework-side default over a required one.
- Update `engine/dummy.py` and `plugin-vad-silero` in the same piece of work.
- The identity attributes (`model_name`, `optimal_frame_ms`, `supported_sample_rates`,
  `max_concurrent_sessions`) are **class attributes, not methods** — the servicer reads
  them directly to build `GetCapabilities`. Keep it that way.

## Concurrency

`max_workers = engine.max_concurrent_sessions + 4`. The `+ 4` is load-bearing: with
`workers == sessions`, a `HealthCheck` RPC starves behind occupied VAD streams and Core
concludes the plugin is dead. Do not "simplify" it away.

`server.max_concurrent_sessions` in YAML overrides the engine's own default and sizes both
the thread pool and the servicer semaphore.

## Logging

Per-frame VAD output is far too noisy for INFO. `StreamVAD` uses **streak-based debouncing**
for transition logs: 3 consecutive speech frames (~96 ms) before logging `speech_start`,
10 consecutive silence frames (~320 ms) before `speech_end`. These thresholds affect
logging only and must never influence the `VADResponse` returned to Core.

## Testing

`tests/test_vad_servicer.py` drives the servicer with a fake engine and a synthetic request
iterator. No model, no network, no real gRPC server.

When adding a test:

- Feed `session_start` first — audio frames before it are silently skipped by design.
- Assert the echoed `sequence_number` on every response. That is the contract.
- Cover the capacity-refusal path (`RESOURCE_EXHAUSTED` when `_active >= max_sessions`).
- Never import a real ML runtime.

## Do not

- Add a CLI flag other than `--config`.
- Add an ML dependency.
- Put engine-specific logic in the servicer — it belongs in the engine package.
- Emit `ERR####` codes.
- Drop or renumber `sequence_number`.
- Change `HealthCheck` state semantics without checking `core/internal/runtime/health.go`:
  OOM transitions to `ERROR`; ordinary per-request failures only set `last_error`.

## Related

- Adding an engine: `../.codex/skills/add-engine-plugin/SKILL.md`
- Proto changes: `../.codex/skills/change-proto/SKILL.md`
- Config keys: `../.codex/skills/add-config-option/SKILL.md`
