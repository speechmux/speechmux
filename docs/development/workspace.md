# Working in this repository

How the components fit together and which commands actually work.

---

## Repository layout

The root holds the glue that ties the components together:

```
AGENTS.md  CLAUDE.md (@AGENTS.md)  README.md  LICENSE
Makefile  workspace.yaml  docker-compose.yml  .env.example
.dockerignore  .gitignore
.github/workflows/proto.yaml
deploy/docker/*.yaml
scripts/remote-access.sh
docs/
.codex/skills/   .claude/skills/
```

Every component is a directory beside it, with its own build definition, `Makefile`,
`.gitignore` and tests. They were separate repositories until
[ADR 0015](../decisions/0015-monorepo.md); their history was imported, so
`git log -- <dir>` goes back past the merge.

| Directory | Language | Contains |
|-----------|----------|----------|
| `proto/` | Protobuf | `.proto` files + generated Go and Python code, `buf` config |
| `core/` | Go | The Core server and `ctl` supervisor |
| `plugin-vad/` | Python | VAD plugin host framework + dummy engine |
| `plugin-vad-silero/` | Python | Silero VAD engine |
| `plugin-stt/` | Python | STT plugin host framework + dummy engine |
| `plugin-stt-sherpa-onnx/` | Python | sherpa-onnx Zipformer streaming engine |
| `plugin-stt-mlx-whisper/` | Python | mlx-whisper batch engine (Apple Silicon) |
| `plugin-stt-faster-whisper/` | Python | faster-whisper batch engine (CPU/CUDA) |
| `client-web/` | TS + Python | Next.js frontend + FastAPI WebSocket proxy |
| `client-cli/` | Python | `speechmux file \| batch \| mic` |

Only `proto` has CI (`.github/workflows/proto.yaml`, triggered by changes under `proto/`:
codegen verification, `buf lint`, `buf breaking` on PRs, and a tagged Python package
release). Everything else is verified locally.

---

## Toolchain

| Tool | Version used to verify |
|------|------------------------|
| Go | 1.26.1 (`go.mod` requires 1.25+) |
| Python | 3.13 via `uv` (`uv venv --python 3.13`) |
| `uv` | 0.10.2 |
| Node | 25.8 (README states 22+) |
| `protoc` | 34.0 (+ `protoc-gen-go`, `protoc-gen-go-grpc` on `$GOBIN`) |
| `grpcio-tools` | installed into `.venv` |
| `buf` | 1.67.0 |
| Docker | 29.4.0 |

The system `python3` may be older (3.9 on macOS). Always call the venv interpreter
explicitly: `.venv/bin/python3`. Every plugin `Makefile` defaults to `PYTHON ?= ../.venv/bin/python3`.

---

## Setup

```bash
git clone git@github.com:speechmux/speechmux.git && cd speechmux
make setup                          # .venv + editable installs of every plugin and client
```

`make setup` also writes `proto/gen/python/pyproject.toml` if it is missing, then installs
`speechmux-proto` and every plugin and client in editable mode. It pulls the real ML
runtimes (torch, mlx-whisper, faster-whisper, sherpa-onnx), which is a large download.

**Light setup.** Every plugin test suite mocks its ML runtime, so tests, lint and typecheck
run without them:

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python3 \
  -e proto/gen/python -e "plugin-vad[dev]" -e "plugin-stt[dev]" -e "client-cli[dev]" numpy
uv pip install --python .venv/bin/python3 --no-deps \
  -e plugin-stt-sherpa-onnx -e plugin-stt-mlx-whisper \
  -e plugin-stt-faster-whisper -e plugin-vad-silero
```

`--no-deps` still registers each engine's entry point, which is all the registry needs.
You cannot *run* an engine this way — only import and test it.

---

## Build

| Command | What it does |
|---------|--------------|
| `make build` | `go build -o core/bin/speechmux-core ./cmd/speechmux-core` |
| `make proto` | `cd proto && make generate`, then reinstall `speechmux-proto` |
| `cd core && make build` | Same as `make build`, from inside `core/` |
| `cd core && make loadtest` | Builds `core/bin/loadtest` |
| `cd client-web/web && npm ci` | Frontend dependencies |

`make proto` regenerates Go and Python stubs from the four proto packages, rewrites the
generated Python imports to be rooted under `stt_proto`, and touches `__init__.py` in every
generated subdirectory. Regenerating with a different `protoc`/`grpcio-tools` version
rewrites files unrelated to your change — inspect the diff and revert the version churn.

---

## Verified command status

Run on the current tree; see [testing.md](testing.md) for details and the failures.

| Command | Result |
|---------|--------|
| `make build` | ✅ builds |
| `cd core && go test ./...` | ✅ all packages pass |
| `cd core && go vet ./...` | ✅ clean |
| `cd core && gofmt -l .` | ⚠️ 29 files reported (pre-existing) |
| `cd core && make lint` | ❌ `golangci-lint` is not installed |
| `cd proto && make generate` | ✅ succeeds |
| `cd proto && buf lint` | ✅ clean |
| `cd plugin-vad && pytest tests/` | ✅ 11 passed |
| `cd plugin-stt && pytest tests/` | ✅ 38 passed |
| `cd plugin-stt-mlx-whisper && pytest tests/` | ✅ 10 passed |
| `cd plugin-stt-faster-whisper && pytest tests/` | ✅ 15 passed |
| `cd plugin-stt-sherpa-onnx && pytest tests/` | ❌ 4 fail, then the suite **hangs** |
| `cd plugin-vad-silero && pytest tests/` | ⏭️ not run — needs a real `torch` install |
| `cd client-cli && pytest tests/` | ✅ 29 passed |
| `cd client-web/web && npm test` | ✅ Vitest, all passing |
| `cd client-web/web && npx tsc --noEmit` | ✅ clean |
| `cd client-web/web && npm run lint` | ✅ no warnings (with a `next lint` deprecation notice) |
| `cd client-web/api && pytest tests/` | ❌ no `tests/` directory exists |
| `ruff check src/` (plugin-vad, plugin-stt) | ⚠️ 5 findings each under ruff 0.16.5 |
| `mypy src/` (plugin-stt) | ✅ clean |
| `mypy src/` (plugin-vad) | ❌ 1 error |
| `docker compose --profile sherpa --profile faster-whisper config` | ✅ valid |
| `speechmux-core ctl status --workspace workspace.yaml` | ✅ works |

`make test` runs the Go suite and every Python suite in sequence. Because it reaches
`plugin-stt-sherpa-onnx`, it currently hangs. Run the suites individually until that is
fixed.

Not verified end-to-end here: `make up`, `make docker-build`, `make docker-up`. They need
real model weights and a full ML install. `docker compose config` validates the Compose
files themselves.

---

## Running locally

```bash
make up      # ctl starts VAD, STT, Core per workspace.yaml
make status
make logs
make down
```

Or run the processes by hand:

```bash
.venv/bin/python3 -m speechmux_plugin_vad.main --config plugin-vad/config/vad.yaml &
.venv/bin/python3 -m speechmux_plugin_stt.main --config plugin-stt/config/inference-onnx.yaml &
core/bin/speechmux-core --config core/config/core.yaml --plugins core/config/plugins.yaml
```

Then transcribe:

```bash
.venv/bin/speechmux file audio.wav --lang ko --metrics
.venv/bin/speechmux batch ./audio_dir/ --lang ko --output ./results/
.venv/bin/speechmux mic --lang ko
```

Details for Docker and remote access: [../operations/deployment.md](../operations/deployment.md).

---

## Making a cross-component change

1. Decide which components are affected. A wire-format change is always proto-first.
2. `proto`: edit the `.proto`, `buf lint`, `make generate`, reinstall the Python package.
   Follow the [`change-proto`](../../.codex/skills/change-proto/SKILL.md) skill.
3. `core`: update the Go side, add tests, `go test ./...`.
4. Plugins: update the Python side, add tests, run each suite.
5. Clients: update `client-cli` and/or `client-web`.
6. Root: update `docs/`, and any config file or `docker-compose.yml` entry involved.
7. Commit it as **one** change. Do not split it per component.

`core/go.mod` carries a committed `replace github.com/speechmux/proto => ../proto`, so
Core builds against the sibling `proto/` directory. A regenerated `proto/gen/go` is
visible to Core immediately with no tag or `go.mod` change — and a half-regenerated one
breaks the Core build just as immediately.

---

## Conventions

**Go** — package-level doc comments; a doc comment on every exported symbol explaining
intent, not just restating the name; `slog` with key/value pairs; errors wrapped with `%w`;
non-obvious concurrency decisions explained in a comment at the site.

**Python** — `from __future__ import annotations`; full type annotations; Google-style
docstrings with Args/Returns/Raises; 100-column lines (`[tool.ruff] line-length = 100`);
`mypy` in `strict` mode.

**TypeScript** — `strict: true`, no `any`, no non-null `!`, explicit return types on
exported functions and components; styling through CSS variables in `globals.css`, no
Tailwind, no hardcoded colours.

**YAML** — every key gets an inline comment stating purpose and unit. This is checked by
review, not tooling, and applies to all copies of a file.

**Commits** — Conventional Commits with a scope, e.g.
`feat(ctl): two-level workspace profile system`, `fix(config): disable VAD watermark lag
check by default`, `docs(readme): add faster-whisper to component table`. Work commits
directly to `main`; there are no feature branches today.
