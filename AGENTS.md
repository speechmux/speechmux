# AGENTS.md — SpeechMux workspace

Working instructions for AI agents in this repository. Read this first, then follow the
links below for the area you are changing.

`CLAUDE.md` contains only `@AGENTS.md`, which imports this file. Do not create a second copy of these rules.

---

## 1. What this project is

SpeechMux is a streaming speech-to-text gateway. A Go **Core** process owns sessions,
routing, end-point detection (EPD), backpressure and fault recovery. **VAD** and **STT
inference** run as separate Python gRPC plugin processes over Unix domain sockets (local)
or TCP (Docker). Clients speak gRPC (`StreamingRecognize`) or a JSON/binary WebSocket
protocol.

Two decode paths exist and are selected automatically from plugin capabilities:

| Path | Engines | How the utterance ends |
|------|---------|------------------------|
| **Batch** | mlx-whisper, faster-whisper | Core VAD + EPD cuts the segment out of the ring buffer and sends one unary `Transcribe` |
| **Streaming** | sherpa-onnx Zipformer | Audio flows continuously over `TranscribeStream`; finalization is driven by Core (`KIND_FINALIZE_UTTERANCE`) or by the engine itself |

Details: [docs/architecture/overview.md](docs/architecture/overview.md).

---

## 2. This repository is a workspace, not the code

This repo contains **only** the workspace glue: `Makefile`, `workspace.yaml`,
`docker-compose.yml`, `deploy/`, `scripts/`, `README.md`, `docs/`.

Every component lives in its own GitHub repository under `github.com/speechmux/` and is
cloned into this directory by `make clone-*`. All of those directories are **gitignored
here** — a change you make inside them is a change to *that* repo and must be committed
there, not here.

```
speechmux/                     ← this repo (workspace)
├── proto/                     ← github.com/speechmux/proto
├── core/                      ← github.com/speechmux/core
├── plugin-vad/                ← VAD plugin host framework
├── plugin-vad-silero/         ← Silero VAD engine
├── plugin-stt/                ← STT plugin host framework
├── plugin-stt-sherpa-onnx/    ← sherpa-onnx streaming engine
├── plugin-stt-mlx-whisper/    ← mlx-whisper batch engine
├── plugin-stt-faster-whisper/ ← faster-whisper batch engine
├── client-web/                ← Next.js frontend + FastAPI WS proxy
└── client-cli/                ← Python CLI client
```

**Before you start:** if the directory you need is missing, clone it
(`make clone-base`, `make clone-stt IMPL=<engine>`, `make clone-vad IMPL=<engine>`,
`make clone-web`, `make clone-cli`) rather than assuming the code does not exist.

Every component repo that has an `AGENTS.md` also has a one-line `CLAUDE.md` containing
`@AGENTS.md`, so Claude Code imports the same rules. `core/` has its own `AGENTS.md` with Core-specific invariants, test
conventions and the package map. Each `plugin-*` directory has one too. The two host frameworks (`plugin-vad`,
`plugin-stt`) have hand-written ones. Every **engine** repo (`plugin-vad-*`, `plugin-stt-*`)
carries a byte-identical `AGENTS.md` copied from `plugin-{vad,stt}/templates/AGENTS.md`,
and puts everything engine-specific in `ENGINE.md` beside it. Read the root file, then the
plugin's `AGENTS.md`, then `ENGINE.md` when working there.

---

## 3. Which document to read for which change

| You are changing | Read first |
|------------------|------------|
| Anything, first time | [docs/architecture/overview.md](docs/architecture/overview.md) |
| Core session pipeline, EPD, ring buffer, decode engines, dispatcher | [docs/architecture/core-pipeline.md](docs/architecture/core-pipeline.md) |
| Plugin host framework, engine adapters, engine registration | [docs/architecture/plugin-system.md](docs/architecture/plugin-system.md) |
| `.proto` files, gRPC/WebSocket wire format | [docs/api/client-protocol.md](docs/api/client-protocol.md), [docs/api/plugin-protocol.md](docs/api/plugin-protocol.md) |
| Error handling, new `ERR####` code | [docs/api/error-codes.md](docs/api/error-codes.md) |
| A YAML config key | [docs/operations/configuration.md](docs/operations/configuration.md) |
| Docker Compose, `ctl`, ports, remote access | [docs/operations/deployment.md](docs/operations/deployment.md) |
| Metrics, tracing, logging, `/health` | [docs/architecture/observability.md](docs/architecture/observability.md) |
| Build/test workflow, toolchain | [docs/development/workspace.md](docs/development/workspace.md) |
| Tests | [docs/development/testing.md](docs/development/testing.md) |
| "Why is it built this way?" | [docs/decisions/](docs/decisions/) (ADRs) |
| What still needs building | [docs/plans/roadmap.md](docs/plans/roadmap.md) |

---

## 4. Commands

Run everything from the workspace root unless stated otherwise. All commands below are
verified against the current tree; see
[docs/development/workspace.md](docs/development/workspace.md) for their exact status
and prerequisites.

### Setup

```bash
make clone-base                    # proto, core, plugin-vad, plugin-stt
make clone-stt IMPL=sherpa-onnx    # add an STT engine repo
make clone-vad IMPL=silero         # add a VAD engine repo
make setup                         # .venv (Python 3.13) + editable installs of every cloned repo
```

`make setup` installs the real ML runtimes (torch, mlx-whisper, faster-whisper,
sherpa-onnx). They are large. Every plugin test suite mocks its runtime, so for a
docs/test-only task you can install just the light packages instead:

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python3 -e proto/gen/python -e "plugin-vad[dev]" -e "plugin-stt[dev]" -e "client-cli[dev]" numpy
uv pip install --python .venv/bin/python3 --no-deps -e plugin-stt-sherpa-onnx -e plugin-stt-mlx-whisper -e plugin-stt-faster-whisper -e plugin-vad-silero
```

### Build

```bash
make build          # core/bin/speechmux-core (Go)
make proto          # regenerate Go + Python stubs, then reinstall the Python package
cd client-web/web && npm ci
```

### Test

```bash
make test                                   # Go tests + pytest for every cloned plugin and client-cli
cd core && go test ./...                    # Go only (add -race for the full check)
cd <plugin-dir> && ../.venv/bin/python3 -m pytest tests/ -q
```

`make test` currently **hangs** in `plugin-stt-sherpa-onnx`. See
[docs/development/testing.md](docs/development/testing.md#known-issues) before running it.

### Lint / format / typecheck

```bash
cd core && go vet ./...                     # passes
cd core && gofmt -l .                       # 29 pre-existing findings; do not mass-reformat
cd proto && buf lint                        # passes
cd <python-plugin> && ../.venv/bin/python3 -m ruff check src/
cd <python-plugin> && ../.venv/bin/python3 -m mypy src/
cd client-web/web && npx tsc --noEmit && npm run lint
```

Pre-existing lint/typecheck findings are catalogued in
[docs/development/testing.md](docs/development/testing.md#known-issues). Do not fold
unrelated lint cleanups into a feature change.

### Run

```bash
make up      # build + start VAD, STT and Core via `speechmux-core ctl` (workspace.yaml)
make status  # process table
make logs    # tail /tmp/speechmux/*.log
make down    # graceful stop

make docker-build && make docker-up && make docker-logs && make docker-down
```

Select engines with `PROFILES` (native) or `DOCKER_PROFILE` (Docker) — see
[docs/operations/deployment.md](docs/operations/deployment.md).

---

## 5. Core rules for code changes

1. **The code is the source of truth.** When a document and the code disagree, the code
   wins — then fix the document in the same change.
2. **Stay inside the repository you are changing.** A Core change and a plugin change are
   two commits in two repos. Never edit generated code to work around a proto change.
3. **Cross-repo changes go proto-first**: edit `.proto` → regenerate → update Go Core →
   update Python plugins → update clients. See the `change-proto` skill.
4. **Proto changes are additive only.** New fields, new RPCs, new enum values. Removing or
   renumbering a field, or changing a type, is forbidden; `reserved` the number and the
   name instead. Enforced by `buf breaking` in the proto repo's CI.
5. **`ERR####` codes are permanent.** Never change the meaning of an assigned code and
   never reuse a retired number.
6. **Match the surrounding style.** Go: `slog` structured logging, doc comments on every
   exported symbol, errors wrapped with `%w`. Python: `from __future__ import annotations`,
   full type annotations, Google-style docstrings with Args/Returns/Raises, 100-column
   lines. TypeScript: `strict: true`, no `any`, explicit return types on exports.
7. **Every YAML key carries an inline comment** explaining its purpose and unit. This is a
   hard convention across `core.yaml`, `plugins.yaml`, `workspace.yaml`, the plugin configs
   and `deploy/docker/*.yaml`.
8. **Do not change runtime behaviour while doing a documentation or test task.**

---

## 6. Testing rules

- New behaviour needs a test in the repo that owns it. Go code goes in `_test.go` beside
  the source; Python goes in that repo's `tests/`.
- **Plugin tests must never require a real model or ML runtime.** Every engine test mocks
  its backend (`sys.modules["sherpa_onnx"] = MagicMock()`, `patch("torch...")`, …) so the
  suite runs on any machine. Follow the existing pattern in the repo you are in.
- When mocking a recognizer/model, set every attribute the production code reads in a
  loop condition. A bare `MagicMock()` is truthy, and `while recognizer.is_ready(stream)`
  against a bare mock hangs forever — this is exactly the live bug described in
  [docs/development/testing.md](docs/development/testing.md#known-issues).
- Core integration tests use in-process Go stubs for the plugins
  (`core/internal/transport/pipeline_integration_test.go`,
  `core/internal/stream/*_integration_test.go`), never live Python processes.
- Run the affected repo's suite before finishing. State plainly what you ran and what
  failed.

---

## 7. API / proto change → documentation sync

Any change to a `.proto` file, the WebSocket JSON schema, the HTTP admin routes, or the
`ERR####` table **must** update the matching document in the same change:

| Change | Also update |
|--------|-------------|
| `client/v1/client.proto` | [docs/api/client-protocol.md](docs/api/client-protocol.md) |
| `vad/v1/vad.proto`, `inference/v1/inference.proto` | [docs/api/plugin-protocol.md](docs/api/plugin-protocol.md) |
| `common/v1/common.proto` enums | [docs/api/plugin-protocol.md](docs/api/plugin-protocol.md) and [docs/api/error-codes.md](docs/api/error-codes.md) |
| WebSocket JSON messages (`core/internal/transport/websocket_handler.go`) | [docs/api/client-protocol.md](docs/api/client-protocol.md) |
| HTTP routes (`core/internal/transport/http_server.go`, `admin_plugins.go`) | [docs/api/client-protocol.md](docs/api/client-protocol.md) |
| `errors/codes.go` | [docs/api/error-codes.md](docs/api/error-codes.md) |
| A YAML key anywhere | [docs/operations/configuration.md](docs/operations/configuration.md) **and** the inline comment in every copy of that file |

`proto/README.md` also documents the wire contract from the proto repo's own point of
view; keep the two consistent, and prefer linking over duplicating.

---

## 8. Architecture changes → where to record them

- **A structural change** (new component, new goroutine in the session pipeline, a
  different concurrency or lifecycle model, a new transport, a new decode path) updates
  [docs/architecture/](docs/architecture/) — usually `core-pipeline.md` or
  `plugin-system.md`.
- **A choice a future developer will question** ("why round-robin?", "why is the ring
  buffer watermark-based?", "why is `committed_text` monotonic?") gets a new ADR in
  [docs/decisions/](docs/decisions/), numbered sequentially, with Context / Decision /
  Rationale / Consequences. Do not write an ADR for a routine bug fix or a parameter tweak.
- **Superseding an existing ADR**: add the new one and mark the old one
  `Status: Superseded by NNNN`. Never silently rewrite history in an accepted ADR.
- **Work that is planned but not built** goes in [docs/plans/](docs/plans/). When it ships,
  delete the plan — move the rationale into an ADR only if it answers a "why" question.
  `docs/plans/` must never accumulate completed work.

---

## 9. Generated and hand-off-limits files

Never hand-edit:

| Path | Produced by |
|------|-------------|
| `proto/gen/go/**` | `cd proto && make generate-go` |
| `proto/gen/python/stt_proto/**` | `cd proto && make generate-python` |
| `proto/gen/python/pyproject.toml` | written by `make setup` if absent |
| `core/bin/**` | `make build` |
| `client-web/web/package-lock.json`, `*/uv.lock` | the package manager |
| `client-web/web/next-env.d.ts` | Next.js |

To change generated protobuf code, edit the `.proto` and regenerate. Regenerating with a
different `protoc`/`grpcio-tools` version produces large unrelated diffs — check the diff
and revert version churn that is not part of your change.

Do not edit `/tmp/speechmux/` state (PID files, logs) by hand; use `make down`.

---

## 10. Plugin work

The plugin system has two layers:

- **Host frameworks** — `plugin-vad`, `plugin-stt`. They own the gRPC servicer, the
  `--config` YAML loader, the concurrency semaphore, `HealthCheck`, `GetCapabilities` and
  the engine `Protocol` definitions. Changing these affects every engine.
- **Engine adapters** — `plugin-vad-silero`, `plugin-stt-mlx-whisper`,
  `plugin-stt-faster-whisper`, `plugin-stt-sherpa-onnx`. Each is a thin package that
  implements one Protocol and registers itself through a Python entry point.

Rules:

1. An engine adapter depends on its host framework (`speechmux-plugin-stt` /
   `speechmux-plugin-vad`) and on its own ML runtime. It must **not** depend on Core, on
   another engine, or import `grpc` server machinery.
2. Engines are discovered only via entry points — `speechmux.stt_engine` or
   `speechmux.vad_engine` in `pyproject.toml`. There is no registry file to edit.
3. Engine identity reaching Core comes from `GetCapabilities` at runtime, not from
   `plugins.yaml`. Advertise `streaming_mode` and `endpointing_capability` honestly;
   Core's routing and endpointing validation depend on them.
4. A new engine touches four places: the engine repo, the engine section in the plugin's
   `config/*.yaml`, an endpoint in `core/config/plugins.yaml` (and
   `deploy/docker/plugins-docker.yaml`), and a `workspace.yaml` profile. The
   `add-engine-plugin` skill walks all of them.
5. Engine repos all share one `AGENTS.md`, owned by the host framework at
   `plugin-{vad,stt}/templates/AGENTS.md`. Never edit the copy in an engine repo — change
   the template and re-copy it everywhere. Engine-specific rules go in that repo's
   `ENGINE.md`.
6. Follow the plugin's own `AGENTS.md` and `ENGINE.md` for repo-specific rules.

Background: [docs/architecture/plugin-system.md](docs/architecture/plugin-system.md).

---

## 11. Skills

Repeatable workflows live in `.codex/skills/<name>/SKILL.md`. Codex is the canonical
source; `.claude/skills` is a symlink to that directory, so there is exactly
one copy of each skill.

| Skill | Use when |
|-------|----------|
| [`add-engine-plugin`](.codex/skills/add-engine-plugin/SKILL.md) | Adding a new STT or VAD engine |
| [`change-proto`](.codex/skills/change-proto/SKILL.md) | Editing any `.proto` file |
| [`add-config-option`](.codex/skills/add-config-option/SKILL.md) | Adding a key to `core.yaml` or a plugin config |
| [`add-error-code`](.codex/skills/add-error-code/SKILL.md) | Introducing a new `ERR####` code |
| [`verify-workspace`](.codex/skills/verify-workspace/SKILL.md) | Running the full build/test/lint sweep before finishing |

Read the whole `SKILL.md` before starting; each lists prerequisites, the file list, the
verification step and the common mistakes. When a workflow you just performed is missing
a step the skill should have covered, update the skill.

---

## 12. Documentation upkeep

- `docs/` describes **what exists now**. It is not an archive.
- One topic, one document. If you are about to repeat an explanation, link instead.
- Do not create empty or placeholder documents.
- Do not document behaviour you have not verified in the code.
- When you delete or rename a document, fix every link to it —
  [docs/README.md](docs/README.md) is the index and must list every file under `docs/`.
- Commands written in a document must be commands you ran. If you could not run one, say
  why in the document.
- `README.md` stays user-facing (what it is, quick start, how to run, where the docs are).
  Agent-specific instructions belong here in `AGENTS.md`, not in `README.md`.

Some Core source comments reference "design doc §N". That document has been removed; the
behaviour it described is now in the code's own doc comments and in
[docs/architecture/core-pipeline.md](docs/architecture/core-pipeline.md).
