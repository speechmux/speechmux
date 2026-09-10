# Close the test and lint gaps

Status: not started. Each item is independent; the first is blocking.

Every item below was reproduced on the current tree. Details and exact error text:
[../development/testing.md](../development/testing.md#known-issues).

---

## 1. `plugin-stt-sherpa-onnx` test suite hangs — blocks `make test`

**Repo:** `plugin-stt-sherpa-onnx`. **Priority: highest** — it blocks the only
whole-workspace test command.

`tests/test_engine.py::test_force_finalize_emits_final` and `test_force_finalize_calls_reset`
build a bare `MagicMock()` recognizer without setting `is_ready.return_value`.
`_force_finalize()` loops on `while recognizer.is_ready(stream)`, a bare mock call result is
truthy, and the loop never terminates. The `_flush` tests in the same file set
`is_ready.return_value = False` and pass.

Fix: set `mock_recognizer.is_ready.return_value = False` in both tests. Consider a
`conftest` helper that builds a correctly-stubbed recognizer so this cannot recur, and add a
`pytest-timeout` default so a future hang fails instead of stalling.

## 2. `plugin-stt-sherpa-onnx` — 4 tests require a real `sherpa_onnx`

Same repo. `test_int16_to_float32_range`, `_zero_bytes`, `_shape_preserved`,
`_odd_bytes_truncated` import `speechmux_plugin_stt_sherpa_onnx.engine` inside the test body
without requesting the `mock_sherpa_onnx` fixture, so they fail with `ModuleNotFoundError`
when the real package is absent — contradicting the conftest's stated premise that
sherpa-onnx is not installed in CI.

Fix: take the fixture, or move `_int16_to_float32` into a module that does not import
`sherpa_onnx`.

## 3. `client-web/api` has no tests

**Repo:** `client-web`. There is no `tests/` directory, so any `pytest tests/` command for
it fails. Untested: the WebSocket relay in both directions, server-side API-key injection,
bearer-token and `?token=` auth, per-user session limiting, the heartbeat, and relay-error
propagation to the browser.

Add `client-web/api/tests/` with `pytest` + `pytest-asyncio` against FastAPI's
`TestClient`, with the Core WebSocket mocked.

## 4. `client-web/web` has no test runner

Same repo. `package.json` has no `test` script. The transcript merge logic in `page.tsx`
and `lib/speechmux-ws.ts` — baseline tracking, incremental extraction, the done-state gate,
line capping — is pure and easy to test.

Add Vitest and cover those functions. Separately, `npm run lint` warns that `next lint` is
removed in Next.js 16; migrate to the ESLint CLI
(`npx @next/codemod@canary next-lint-to-eslint-cli .`).

## 5. `plugin-vad` fails `mypy src/`

**Repo:** `plugin-vad`. One error:

```
service/vad_servicer.py:22: error: Class cannot subclass "VADPluginServicer" (has type "Any")
```

`plugin-stt/pyproject.toml` has a `[[tool.mypy.overrides]]` block setting
`ignore_missing_imports = true` for `grpc.*` / `stt_proto.*` / `google.protobuf.*`;
`plugin-vad` does not. Copy the block across.

## 6. `ruff check src/` fails in both plugin frameworks

**Repos:** `plugin-vad`, `plugin-stt`. Five findings each under ruff 0.16.5 — `UP037`
(quoted annotations), `I001` (import order), `RUF012` (mutable class-attribute default).
Both pin `ruff>=0.4` with no upper bound, so new rules arrive with new releases.

Fix: apply `ruff check --fix`, annotate the mutable defaults with `ClassVar`, and pin a
ruff upper bound (or a `[tool.ruff] required-version`) so lint results are reproducible.

## 7. Go formatting and lint

**Repo:** `core`. `gofmt -l .` reports 29 files, mostly hand-aligned struct-field and
const-block comments. `go vet ./...` is clean. `core/Makefile lint` calls `golangci-lint`,
which is not installed.

Do this as a **standalone commit**, never folded into a feature change: run `gofmt -w .`,
then add a `golangci-lint` config and install instructions so `make lint` is runnable.

## 8. Untested Core packages

**Repo:** `core`. `internal/tracing`, `internal/metrics` and `internal/health` have no test
files. Worth pinning: the metric names and label sets (a rename silently breaks
dashboards), the `ok`/`degraded`/`error`/`draining` aggregation rules, and that
`tracing.Init("")` installs the no-op provider.

## 9. `core/Makefile loadtest` help text is stale

**Repo:** `core`. It suggests `make -C .. run-dummy`, a workspace target that no longer
exists. Update it to name the dummy config files directly
(`plugin-vad/config/vad-dummy.yaml`, `plugin-stt/config/inference-dummy.yaml`,
`core/config/plugins-dummy.yaml`).
