# SpeechMux documentation

Every document here describes the system **as it is now**. Project overview and quick
start: [../README.md](../README.md). Working instructions for AI agents:
[../AGENTS.md](../AGENTS.md).

---

## Start here

New to the codebase? Read [architecture/overview.md](architecture/overview.md) first — it
covers the process layout, the two decode paths, and where each Core package sits.

---

## Architecture

| Document | Covers |
|----------|--------|
| [architecture/overview.md](architecture/overview.md) | Processes, batch vs streaming paths, Core packages, external dependencies |
| [architecture/core-pipeline.md](architecture/core-pipeline.md) | Session lifecycle, per-session goroutines, ring buffer, EPD, decode engines, fair dispatcher, result assembly, concurrency, shutdown |
| [architecture/plugin-system.md](architecture/plugin-system.md) | Host frameworks vs engine adapters, entry-point discovery, engine Protocols, plugin lifecycle, routing |
| [architecture/observability.md](architecture/observability.md) | Prometheus metrics, OpenTelemetry spans, logging, `/health`, load testing |

## API

| Document | Covers |
|----------|--------|
| [api/client-protocol.md](api/client-protocol.md) | gRPC `StreamingRecognize`, the WebSocket JSON protocol, HTTP + admin endpoints, auth, TLS |
| [api/plugin-protocol.md](api/plugin-protocol.md) | `VADPlugin` and `InferencePlugin` contracts, capabilities, shared enums, compatibility rules |
| [api/error-codes.md](api/error-codes.md) | The full `ERR####` registry and the plugin-error translation table |

## Operations

| Document | Covers |
|----------|--------|
| [operations/configuration.md](operations/configuration.md) | Every config file and key, hot-reload semantics, known drift |
| [operations/deployment.md](operations/deployment.md) | `ctl` native runs, Docker Compose, engine profiles, Tailscale, production checklist |

## Development

| Document | Covers |
|----------|--------|
| [development/workspace.md](development/workspace.md) | Repo layout, toolchain, setup, build, verified command status, cross-repo changes, conventions |
| [development/testing.md](development/testing.md) | Test strategy per layer, how to run each suite, known failures, how to write tests here |

## Decisions (ADR)

Why the system is shaped the way it is. Add a new ADR when a choice will provoke a "why is
this like this?" later; do not write one for a routine fix.

| ADR | Title |
|-----|-------|
| [0001](decisions/0001-multi-repo-workspace.md) | One repository per component, tied together by a workspace repo |
| [0002](decisions/0002-single-bidi-streaming-rpc.md) | One bidirectional RPC carries the whole session |
| [0003](decisions/0003-entry-point-engine-registry.md) | Engines register through Python entry points, behind a host framework |
| [0004](decisions/0004-per-session-vad-stream.md) | One `StreamVAD` stream per session, not a multiplexed one |
| [0005](decisions/0005-watermark-ring-buffer.md) | Ring-buffer trimming is watermark-based, and a full buffer is backpressure |
| [0006](decisions/0006-monotonic-committed-text.md) | `committed_text` never shrinks within an utterance |
| [0007](decisions/0007-runtime-capability-discovery.md) | Engine identity comes from `GetCapabilities`, not from `plugins.yaml` |
| [0008](decisions/0008-error-code-registry.md) | A permanent `ERR####` registry, translated at the plugin boundary |
| [0009](decisions/0009-shared-tls-config-restart-to-rotate.md) | One TLS config for all three ports, loaded once at startup |
| [0010](decisions/0010-ctl-subcommand-process-manager.md) | Process supervision is a `ctl` subcommand of the Core binary |
| [0011](decisions/0011-fair-decode-dispatcher.md) | Cross-session fair queueing in front of batch inference |
| [0012](decisions/0012-docker-compose-profiles.md) | Docker Compose with profiles for engine selection |
| [0013](decisions/0013-separate-streaming-and-batch-pools.md) | Streaming and batch are one `DecodeEngine` interface with separate capacity pools |
| [0014](decisions/0014-endpointing-source.md) | `endpointing_source` is a field on `StreamStartConfig` |

## Plans

Work that is **not yet built**. A plan is deleted when it ships.

| Document | Covers |
|----------|--------|
| [plans/roadmap.md](plans/roadmap.md) | Everything outstanding, plus what is deliberately unimplemented |
| [plans/decode-options-and-task-passthrough.md](plans/decode-options-and-task-passthrough.md) | `decode_profile` and `task` never reach the STT plugin |
| [plans/vad-frame-size-negotiation.md](plans/vad-frame-size-negotiation.md) | Core ignores the VAD plugin's `optimal_frame_ms` |
| [plans/test-and-lint-gaps.md](plans/test-and-lint-gaps.md) | Nine verified test and tooling gaps, including a suite that hangs |

---

## Skills

Repeatable workflows live in [`.codex/skills/`](../.codex/skills/); `.claude/skills` is a
symlink to that directory, so there is exactly one copy of each skill.

| Skill | Use when |
|-------|----------|
| [add-engine-plugin](../.codex/skills/add-engine-plugin/SKILL.md) | Adding a new STT or VAD engine |
| [change-proto](../.codex/skills/change-proto/SKILL.md) | Editing any `.proto` file |
| [add-config-option](../.codex/skills/add-config-option/SKILL.md) | Adding a YAML config key |
| [add-error-code](../.codex/skills/add-error-code/SKILL.md) | Introducing a new `ERR####` code |
| [verify-workspace](../.codex/skills/verify-workspace/SKILL.md) | Running the full build/test/lint sweep |

## Per-repository instructions

Each component repository carries an `AGENTS.md` that assumes the root
[../AGENTS.md](../AGENTS.md) and adds only what is specific to it, plus a
one-line `CLAUDE.md` containing `@AGENTS.md` so Claude Code imports the same file.

| Repo kind | `AGENTS.md` | Engine-specific rules |
|-----------|-------------|-----------------------|
| Core (`core/`) | Hand-written: package map, pipeline invariants, Go test conventions | — |
| Host frameworks (`plugin-vad/`, `plugin-stt/`) | Hand-written per repo | — |
| Engine adapters (`plugin-vad-*/`, `plugin-stt-*/`) | **Byte-identical copy** of `plugin-{vad,stt}/templates/AGENTS.md` | `ENGINE.md` beside it |

A new engine author copies `templates/AGENTS.md` verbatim and fills in `templates/ENGINE.md`.
The template is the only place the shared rules are edited.
