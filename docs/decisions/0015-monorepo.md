# 0015 — One repository for every first-party component

Status: Accepted. Supersedes [0001](0001-multi-repo-workspace.md).

## Context

[ADR 0001](0001-multi-repo-workspace.md) gave every component its own GitHub repository and
kept only the glue (`Makefile`, `workspace.yaml`, `docker-compose.yml`, `deploy/`, `docs/`)
in a workspace repository that cloned the rest beside itself. The aim was independent
dependencies, independent releases of `proto`, and engines that could be added without
touching shared code.

In practice the repositories were never independent:

- `core/go.mod` requires `github.com/speechmux/proto v0.0.0` with a committed
  `replace github.com/speechmux/proto => ../proto`. Core does not build without the `proto`
  checkout beside it.
- Four Docker images (`core`, `plugin-vad`, `plugin-stt`, `plugin-stt-faster-whisper`) use
  the workspace root as their build context because they need sibling directories.
- No component repository ever had a tag, so nothing could pin a version of another.
- There is one author, and almost every recent change spanned two or more repositories —
  several commits for one logical change, with no way to make them atomic.
- CI existed only in `proto`.

## Decision

All first-party code lives in this repository. Each component sits at the path it already
occupied in the workspace (`proto/`, `core/`, `plugin-*/`, `client-*/`) and was imported
with its full history (`git filter-repo --to-subdirectory-filter`, then one merge per
component), so `git log -- <path>` and `git blame` reach back past the import.

Each component keeps its own build definition (`go.mod`, `pyproject.toml`,
`package.json`), its own `Makefile` and its own tests. Go module paths are unchanged
(`github.com/speechmux/core`, `github.com/speechmux/proto`); the local `replace` stays.

Three invariants keep a later split cheap. They held before the merge and are rules now:

1. Every engine keeps its own directory and its own `pyproject.toml`.
2. An engine uses only its host framework's public API — no imports of framework
   internals, no relative paths into a sibling directory.
3. Core and the host frameworks contain no engine-specific code. Engines are identified
   only through entry points and `GetCapabilities`
   ([0003](0003-entry-point-engine-registry.md),
   [0007](0007-runtime-capability-discovery.md)).

## Rationale

- A wire-format change, the Core change that uses it, the plugin change and the document
  update are one commit instead of four that must be kept compatible by hand.
- What 0001 wanted from separate repositories comes from separate *packages*, which are
  unchanged: a Core developer still never installs `torch`, and a `client-cli` user still
  never installs `sherpa-onnx`. Wiring is still by discovery — the `Makefile` globs
  `plugin-vad-*` and `plugin-stt-*`.
- Third-party engines remain a goal, but they depend on a versioned, published contract
  (`proto` plus the host frameworks), not on where first-party code is stored. Publishing
  that contract is separate work, and it is not harder from one repository.
- Shipping a customer a build with only one STT engine is a release-packaging concern:
  build only that image, or export an allow-list of paths at release time. Long-lived
  per-customer branches or repositories are not the tool for it.
- Extracting a directory with its history is cheap
  (`git filter-repo --subdirectory-filter <dir>`), so the decision is reversible per
  component for as long as the three invariants hold.

## Consequences

- A cross-component change is one commit, still worked proto-first.
- GitHub Actions reads only the root `.github/workflows/`. `proto`'s workflow moved there
  and is limited to changes under `proto/`; `buf breaking` compares against the `proto`
  subdirectory of the base branch.
- A tag now names the whole repository. Per-component versions, when `proto` and the host
  frameworks are published, need prefixed tags (`proto/v1.2.3`) or a registry.
- Cloning brings every engine's source. Their ML runtimes are still installed only on
  request (`make setup`, or the light install in [../development/workspace.md](../development/workspace.md)).
- The ten former repositories under `github.com/speechmux/` are archived, not deleted, so
  old commit hashes and links keep resolving. Hashes of imported commits differ from the
  originals because every path was rewritten.
- **Hybrid end state.** Once the contract is published and a real external consumer
  exists, one reference engine moves back out to its own repository and builds against
  published versions only — proof that the contract is sufficient. Until then nothing is
  split out.
