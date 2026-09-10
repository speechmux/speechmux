# Testing

---

## Strategy

Each repository tests itself. There is no cross-repo test harness; correctness at the
boundaries is enforced by the proto contract, `buf breaking`, and the error-code contract
test.

| Layer | Where | Style |
|-------|-------|-------|
| Core units | `core/internal/*/*_test.go` | Table-driven Go tests, ~315 functions across 40 files |
| Core integration | `core/internal/stream/*_integration_test.go`, `core/internal/transport/pipeline_integration_test.go` | The real pipeline against **in-process Go stubs** for VAD and STT |
| Error contract | `core/internal/errors/contract_test.go` | Pins the gRPC + HTTP status of every `ERR####` |
| Plugin framework | `plugin-vad/tests/`, `plugin-stt/tests/` | pytest against the servicer with a dummy engine |
| Engine adapters | `plugin-*-<impl>/tests/` | pytest with the ML runtime mocked out |
| CLI | `client-cli/tests/` | pytest with the gRPC client mocked |
| Frontend | `client-web/web` | `tsc --noEmit` + ESLint only — no unit tests yet |

**Core integration tests never start a Python process.** They implement the plugin gRPC
servers in Go over `bufconn`, so the pipeline is exercised deterministically and the suite
has no ML dependencies.

**Engine tests never load a model.** Each mocks its backend before importing the engine:

| Repo | Mocking approach |
|------|------------------|
| `plugin-stt-sherpa-onnx` | `conftest.py` fixture injects `sys.modules["sherpa_onnx"] = MagicMock()` and purges cached plugin modules before and after each test |
| `plugin-stt-mlx-whisper` | `sys.modules` injection for `mlx_whisper` |
| `plugin-stt-faster-whisper` | `sys.modules` injection for `faster_whisper` |
| `plugin-vad-silero` | `unittest.mock.patch` over the torch/silero calls — but the test module still does a real `import torch` |

Follow the pattern already in the repo you are working in.

---

## Running

```bash
make test                 # everything (see the hang below)

cd core && go test ./...
cd core && go test -race ./...                         # what core/Makefile test runs
cd core && go test ./internal/stream/ -run TestFair -v

cd plugin-stt && ../.venv/bin/python3 -m pytest tests/ -q
cd client-cli && ../.venv/bin/python3 -m pytest tests/ -q

cd client-web/web && npx tsc --noEmit && npm run lint
```

The light install in [workspace.md](workspace.md#setup) is enough for every suite except
`plugin-vad-silero`.

---

## Known issues

Verified on the current tree. None of these are introduced by the documentation work; they
are recorded so nobody rediscovers them.

### `plugin-stt-sherpa-onnx` — suite hangs, 4 tests fail

`pytest tests/` never finishes.

**Hang.** `tests/test_engine.py::test_force_finalize_emits_final` and
`test_force_finalize_calls_reset` build a bare `MagicMock()` recognizer and never set
`is_ready.return_value`. `_force_finalize()` runs

```python
while recognizer.is_ready(stream):
    recognizer.decode_stream(stream)
```

and a bare `MagicMock` call result is always truthy, so the loop never exits. The sibling
`_flush` tests do set `mock_recognizer.is_ready.return_value = False` and pass. Fix:
set it in the `_force_finalize` tests too.

**Failures.** The four `test_int16_to_float32_*` tests import
`speechmux_plugin_stt_sherpa_onnx.engine` inside the test body **without** requesting the
`mock_sherpa_onnx` fixture, so they need a real `sherpa_onnx` install and fail with
`ModuleNotFoundError` otherwise — contradicting the conftest's own statement that
"sherpa-onnx is not installed in CI". Fix: take the fixture, or move the pure helper out of
the module that imports `sherpa_onnx`.

`tests/test_stream.py` (9 tests) passes on its own.

Because `make test` iterates every cloned `plugin-*`, this hang blocks the whole target.

### `client-web/api` has no tests

`client-web/api/` contains no `tests/` directory, so any documented
`cd client-web/api && pytest tests/` command cannot work. The WebSocket proxy
(`ws_proxy.py`), API-key injection and per-user session limiting are untested.

### `client-web/web` has no test runner

`package.json` defines `dev`, `build`, `start`, `lint`, `type-check` — no `test`. The
transcript-merging logic in `page.tsx` and `lib/speechmux-ws.ts` (baseline tracking,
incremental extraction, done-state gating) is exactly the kind of code that wants unit
tests. `npm run lint` also prints a deprecation notice: `next lint` is removed in Next.js
16 and should migrate to the ESLint CLI.

### `plugin-vad` — `mypy src/` fails

```
src/speechmux_plugin_vad/service/vad_servicer.py:22:
  error: Class cannot subclass "VADPluginServicer" (has type "Any")  [misc]
```

`plugin-stt/pyproject.toml` carries a `[[tool.mypy.overrides]]` block with
`ignore_missing_imports = true` for `grpc.*` / `stt_proto.*`; `plugin-vad/pyproject.toml`
does not. `plugin-stt` typechecks cleanly.

### `ruff check src/` — 5 findings in each plugin framework

Both repos pin `ruff>=0.4` with no upper bound, and ruff 0.16.5 enables rules that did not
exist when the code was written: `UP037` (quotes in annotations), `I001` (import sorting),
`RUF012` (mutable class-attribute default). Cosmetic, but `make lint` is not green.

### `gofmt -l core/` — 29 files

Mostly hand-aligned struct-field and const-block comments that `gofmt` would re-space.
`go vet ./...` is clean. Do **not** run `gofmt -w` across the tree as part of an unrelated
change; the diff would swamp it.

### `golangci-lint` is not installed

`core/Makefile`'s `lint` target calls it. Use `go vet ./...` until it is installed.

### `core/Makefile loadtest` help text is stale

It suggests `make -C .. run-dummy`, a target the workspace `Makefile` no longer has (it was
replaced by the `ctl`-based targets). Start the dummy plugins manually with
`plugin-vad/config/vad-dummy.yaml`, `plugin-stt/config/inference-dummy.yaml` and
`core/config/plugins-dummy.yaml`.

### Untested Core packages

`internal/tracing`, `internal/metrics` and `internal/health` have no test files. They are
thin wrappers, but the metrics label sets and the health-status aggregation rules are worth
pinning.

Tracked in [../plans/roadmap.md](../plans/roadmap.md) and
[../plans/test-and-lint-gaps.md](../plans/test-and-lint-gaps.md).

---

## Writing tests

- Put the test in the repo that owns the code.
- Go: table-driven, `t.Run` subtests, `t.Cleanup` for teardown. Use `-race` for anything
  touching the pipeline. `core/internal/session/testutil.go` and `export_test.go` expose
  the helpers you need for session construction.
- Python: pytest, mock the ML runtime, and **set every mock attribute the production code
  reads in a loop condition** — see the sherpa hang above.
- gRPC in Go tests: `bufconn` with `grpc.WithContextDialer`. The dialer must return a
  concrete `net.Conn`, not an anonymous interface, or the dial fails opaquely.
- Batch-path tests must *drain* results rather than assert on the first one: in-flight
  partials arrive before the final.
- Streaming integration tests need roughly 50 PCM frames before the EPD declares an
  utterance end at the default `vad_silence_sec`.
- Adding an `ERR####` code means adding a row to `contract_test.go` — the completeness test
  fails otherwise.

---

## End-to-end

No unit suite exercises Core + VAD + STT + a client together. The
[`e2e-test`](../../.codex/skills/e2e-test/SKILL.md) skill does, against a running stack, and
its `scripts/smoke.sh` automates the CLI half.

Baseline (2026-09-11, Docker Compose stack rebuilt from repo HEAD, Apple Silicon):

| Path | Engine | Result |
|------|--------|--------|
| CLI `speechmux file` fast | sherpa-onnx | ✅ 1 final, 14 partials, RTF ≈ 0.06 |
| CLI `speechmux file --realtime` | sherpa-onnx | ✅ same text, RTF ≈ 1.06 |
| CLI `speechmux file` fast | faster-whisper (small, cpu) | ✅ 2 finals with timestamps, RTF ≈ 0.2 |
| CLI `speechmux file --realtime` | faster-whisper | ✅ RTF ≈ 1.35 |
| Web file upload, realtime pacing | sherpa-onnx, faster-whisper, Auto | ✅ Done in ≈ audio + 2 s; Stop → Finishing → Done |
| Web microphone | — | ⏭️ not testable from the Chrome-MCP window (no mic device) |
| Batch panel | — | ⏭️ not exercised end to end yet |

What the first E2E run found — every one of these had a green unit suite:

- `deploy/docker/core-docker.yaml` had `vad_watermark_lag_threshold_sec: 5.0`, so **every**
  file upload died with ERR3004. Fixed to `0` (matches native).
- The running `core` image was 4 months old and the `stt-faster-whisper` image reported
  `STREAMING_MODE_UNSPECIFIED`; the current Core's strict `RouteBatch()` then excluded it and
  every final decode failed with ERR2005. Rebuilt both images.
- Web client: per-chunk `setTimeout` pacing collapsed to 1 s/chunk in a background tab
  (5.6 s file → 67 s) and the EPD split utterances mid-word; decoding the file in a
  device-rate `AudioContext` plus box-filter downsampling changed the recognised text and
  dropped the final syllables. Both fixed in `client-web`.

Open Core/CLI issues surfaced by E2E are tracked in
[../plans/roadmap.md](../plans/roadmap.md#findings-from-end-to-end-testing).
