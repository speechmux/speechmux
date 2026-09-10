# 0001 — One repository per component, tied together by a workspace repo

Status: Accepted

## Context

SpeechMux is Go Core plus several Python plugins plus two clients plus a shared protobuf
contract. These have different toolchains (Go modules, `uv`/hatchling, npm), different
release cadences, and very different dependency weights: pulling `torch` in to build the
Go server, or CUDA wheels in to run the CLI, is unacceptable.

An engine adapter is also small — a few hundred lines around one ML runtime — and new ones
are expected to keep arriving.

## Decision

Every component is its own GitHub repository under `github.com/speechmux/`. A separate
repository, `speechmux` (this one), holds only the workspace glue: `Makefile`,
`workspace.yaml`, `docker-compose.yml`, `deploy/`, `scripts/` and `docs/`. Component
directories are cloned into the workspace by `make clone-*` and are gitignored there.

Wiring is by **discovery, not declaration**: the `Makefile` and `setup`/`test` targets glob
`plugin-vad-*`, `plugin-stt-*` and `client-*` and operate on whatever is present, so a new
engine repo needs no change to the workspace build.

## Rationale

- Each component installs only the dependencies it needs. A Core developer never installs
  `torch`; a `client-cli` user never installs `sherpa-onnx`.
- `proto` can be versioned and released independently, which is what makes the
  additive-only contract enforceable (`buf breaking` against the repo's own `main`).
- A new engine is a new repository, not a change to a shared one — no coordination cost and
  no risk to existing engines.
- The workspace repo stays small enough to be the obvious place for cross-cutting
  documentation and deployment.

## Consequences

- A single logical change can span several repositories and needs several commits, in
  proto-first order. There is no atomic cross-repo commit.
- `core/go.mod` pins `github.com/speechmux/proto v0.0.0` with a **committed**
  `replace github.com/speechmux/proto => ../proto`, so Core always builds against the
  sibling `proto/` checkout. A proto change is visible to Core immediately, and `proto/`
  must be cloned beside `core/` for Core to build at all — but there is no version pin
  between the two repos.
- Because component directories are gitignored in the workspace, files placed inside them —
  including their `AGENTS.md` — belong to those repos and must be committed there.
- Only `proto` has CI. Everything else is verified locally, which is why
  [../development/testing.md](../development/testing.md) records the exact command status.
