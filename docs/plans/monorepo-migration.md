# Monorepo migration

**Status: in progress on the `monorepo` branch. Steps 0–5 are done: all ten components are
imported with history and the documentation describes one repository. Not pushed.**

This is the hand-off for moving every SpeechMux component into this repository
(`speechmux/speechmux`). It is self-contained: an agent or developer who has not seen the
discussion that led here can finish the work from this file alone.

Delete this document when the migration has merged to `main` (step 8).

---

## Where things are

| What | Where |
|------|-------|
| Migration checkout (this clone) | `~/repo/speechmux`, branch `monorepo`, branched from `main` at `5dbe46c` |
| Previous multi-repo workspace | `~/src/speechmux` — leave it untouched; it is the reference and the rollback |
| Component repositories | `github.com/speechmux/<name>`, ten of them, listed below |

`AGENTS.md`, `README.md` and `docs/` already describe the merged layout (step 5). The
notice that used to sit at the top of `AGENTS.md` was removed in that step.

---

## Decision

All first-party code moves into one repository. The directory layout does not change:
each component lands at the path it already occupies in the workspace (`proto/`, `core/`,
`plugin-*/`, `client-*/`), so the `Makefile`, `docker-compose.yml`, the Dockerfiles and
every relative link in `docs/` keep working.

Why, in short (the full reasoning is in [ADR 0015](../decisions/0015-monorepo.md)):

- The components were never independently buildable. `core/go.mod` requires
  `github.com/speechmux/proto v0.0.0` with `replace … => ../proto`, and four Docker images
  build from the workspace root.
- No component repository has a tag, so nothing could pin a version anyway.
- One author; almost every recent change spanned two or more repositories.
- CI exists only in `proto`.

What the multi-repo layout was for, and how that goal is kept:

- **Third-party engine plugins remain a goal.** They depend on a versioned, published
  contract (`proto` + the host frameworks), not on where first-party code lives. Publishing
  that contract is separate, later work.
- **A hybrid layout is the intended end state** once the contract is published: one
  reference engine moves back out to its own repository and builds against published
  versions only. Extracting a directory with its history is cheap
  (`git filter-repo --subdirectory-filter`), so this can wait for a real consumer.
- **Customer deliveries that must contain only one STT engine** are a release-packaging
  concern, not a repository-layout one. If source must be delivered, export an allow-list
  of paths at release time. Do not use long-lived per-customer branches.

### Invariants that keep a later split cheap

These already hold. Keep them holding after the merge; ADR 0015 and `AGENTS.md` §2 state them:

1. Every engine keeps its own directory and its own `pyproject.toml`.
2. An engine uses only the host framework's public API — no imports of framework
   internals, no relative paths into a sibling directory.
3. Core and the host frameworks contain no engine-specific code; engines are identified
   only through entry points and `GetCapabilities`.

### Out of scope for this migration

- Changing Go module paths (`github.com/speechmux/core`, `github.com/speechmux/proto`).
  The local `replace` keeps working; renaming would touch ~80 Go files plus generated code.
- De-duplicating the byte-identical engine `AGENTS.md` copies.
- Tagging or publishing `proto` and the host frameworks.
- Moving any engine back out (the hybrid step).
- Any runtime behaviour change.

---

## Components to import

State on 2026-11-24, read from the local clones in `~/src/speechmux` (no `git fetch` was
run, so confirm against the remotes in step 1). Every repository had a clean working
tree, a single `main` branch and no tags.

| Path / repo | `main` commit | Root tree hash |
|-------------|---------------|----------------|
| `proto` | `2156e60` | `07e2fd6fd4cab40065c12acb8590f04ca496f9ab` |
| `core` | `a9b7bd4` | `0626c8a9196784a9c33515d2f1f78e5f5bbf2fc6` |
| `plugin-vad` | `64abd06` | `be38002b602596219c1070f466059e7a416a6328` |
| `plugin-vad-silero` | `73824ea` | `a32861a6862eff5452f1cd5d19f65f5d2d1281ab` |
| `plugin-stt` | `4fdb133` | `f7e67be7674b43fc2141d87595d2b82a5bf97c4c` |
| `plugin-stt-sherpa-onnx` | `5790892` | `6696c71d206c741545694f8751285a277d6606f1` |
| `plugin-stt-mlx-whisper` | `8b62909` | `3d0a79bc4a472597965c52edb71cc67d46268680` |
| `plugin-stt-faster-whisper` | `b06640d` | `95246cd47e42c8fb2af0a0da46ab36e1c13583fa` |
| `client-web` | `a0ef4d1` | `d2cd1e2062ff54d1e30f4a80df3223139a6f30ad` |
| `client-cli` | `db98488` | `9a76ff472e27c70db2319c181631b269fc87d601` |

An eleventh repository, `speechmux/plugin-stt-qwen3-asr` (private), also exists. Its local
clone has no commits and no files, and nothing in the workspace refers to it, so there is
nothing to import. Whether to keep it as an empty placeholder is the owner's call; the
engine, when it is written, is added as a new directory here.

The tree hash is the acceptance check for the import: after step 3,
`git rev-parse monorepo:<path>` must print exactly the hash in this table (or the hash of
the newer remote commit, if step 1 finds one).

---

## Steps

A ticked box was done as written unless a note says otherwise. Unticked boxes are still
the plan, not a record.

Three steps change something outside this machine and need the repository owner's
explicit go-ahead each time: pushing the branch (step 7), merging to `main` (step 7) and
archiving the old repositories (step 8).

### 0. Commit this hand-off

- [x] Commit this file together with the `AGENTS.md` notice, the `docs/README.md` row and
      the `docs/plans/roadmap.md` entry. The merges in step 3 need a clean working tree.

### 1. Prerequisites

- [x] Install `git-filter-repo` (`brew install git-filter-repo`). Already present at
      `/opt/homebrew/bin/git-filter-repo` when this step was run.
- [x] Clone the ten component repositories fresh into a scratch directory **outside**
      this checkout (`~/repo/speechmux-import/src-<name>`). Never run
      `filter-repo` on the clones in `~/src/speechmux`; it rewrites history in place.
- [x] For each fresh clone, compare `git rev-parse 'HEAD^{tree}'` with the table above. A
      different hash means something was pushed after 2026-11-24 — update the table.
      All ten matched.
- [x] Check each component repository for open issues and pull requests
      (`gh issue list -R speechmux/<name>`, `gh pr list -R speechmux/<name>`). None
      of the ten had an open issue or pull request.

### 2. Stop ignoring the component directories

- [x] In `.gitignore`, delete the block that ignores `proto/`, `core/`, `plugin-*/` and
      `client-*/` (and its two comment lines). Commit.

### 3. Import each repository with its history

```bash
REPOS="proto core plugin-vad plugin-vad-silero plugin-stt plugin-stt-sherpa-onnx \
plugin-stt-mlx-whisper plugin-stt-faster-whisper client-web client-cli"

# In the scratch directory (bash; zsh does not word-split $REPOS): rewrite every commit so its files sit under <name>/.
for r in $REPOS; do
  git -C src-$r filter-repo --to-subdirectory-filter $r
done

# In this checkout, on the monorepo branch:
for r in $REPOS; do
  git remote add $r ../speechmux-import/src-$r && git fetch --no-tags $r
  git merge --allow-unrelated-histories -m "chore: import $r history" $r/main
  git remote remove $r
done
```

- [x] Run the import. Commit hashes of imported commits change (paths are rewritten);
      `git log -- core/…` and `git blame` then follow the old history without `--follow`.
- [x] Verify every path: `git rev-parse monorepo:<path>` equals the tree hash in the table.
      All ten matched.
- [x] Confirm there is no nested `.git` (`find . -mindepth 2 -name .git`).

### 4. Make the tree self-consistent

- [x] `Makefile`: remove the `clone-base`, `clone-stt`, `clone-vad`, `clone-web`,
      `clone-cli` targets, the `_clone` macro and their `.PHONY` entries. The `setup` and
      `test` loops over `plugin-vad-* plugin-stt-*` stay as they are.
- [x] CI: GitHub Actions reads only the root `.github/workflows/`.
      `proto/.github/workflows/ci.yaml` is now `.github/workflows/proto.yaml`, with
      `working-directory: proto` and a `paths` filter on `proto/**`. The breaking check is
      `buf breaking --against "../.git#branch=<base>,subdir=proto"`, verified locally with
      buf 1.67.0. It needed one more step: `actions/checkout` leaves no local base branch
      for buf to clone, so the job fetches it first. The check cannot pass on the migration
      pull request itself, because `main` has no `proto/` yet (`Module "path: "proto"" had
      no .proto files`) — expect that one failure. The workflow has not run on GitHub.
      The `v*.*.*` tag trigger for the Python package artifact is unchanged; it is now a
      repository-wide tag pattern, to be revisited when `proto` is actually published.
- [x] Search for anything else that assumes separate repositories:
      `grep -rnE 'make clone-|clone-base|git clone|gitignored|its own (GitHub )?repo' .`
      A wider search (`\brepos?\b|repositor|cloned`) found more in the component
      `AGENTS.md`/`ENGINE.md` files, four skills and several `docs/` pages; all fixed in
      step 5. Left as they are on purpose: ADR 0001 and one rationale line in ADR 0008
      (accepted ADRs are not rewritten), and the commented-out
      `git+ssh://…/proto.git` dependency lines in `plugin-{vad,stt}/pyproject.toml` and the
      "Consuming" section of `proto/README.md`, which describe publishing — out of scope.

### 5. Documentation

- [x] New ADR `docs/decisions/0015-monorepo.md` (Context / Decision / Rationale /
      Consequences) from the "Decision" section above, including the three invariants and
      the conditions for the later hybrid split.
- [x] Mark `docs/decisions/0001-multi-repo-workspace.md` as
      `Status: Superseded by 0015`. Do not rewrite its body.
- [x] `AGENTS.md`: rewrite §2 (the repository is no longer "a workspace, not the code"),
      §4 setup (no `clone-*`), §5 rules 2 and 3 (a cross-component change is one commit,
      still proto-first in order), §9 and §10 where they say "repo". Remove the migration
      notice at the top. §2 also lists the three invariants.
- [x] `README.md`, `docs/development/workspace.md`, `docs/README.md` ("Per-repository
      instructions" section and the ADR table).
- [x] Skills in `.codex/skills/`: `change-proto`, `add-engine-plugin` and
      `verify-workspace` describe per-repository commits; update them. Their
      `buf breaking` command is now `--against '../.git#branch=main,subdir=proto'`, which
      fails locally until `main` contains `proto/` (after step 7).
- [x] Component-level `AGENTS.md`, `README.md` and `ENGINE.md` files that refer to "this
      repo" or to cloning siblings. The engine `AGENTS.md` change was made in the two
      templates and re-copied; `cmp` shows no drift.

### 6. Verify

- [ ] `make setup` (or the light install in `AGENTS.md` §4), `make build`,
      `cd core && go test ./...`, `go vet ./...`, `cd proto && buf lint`.
- [ ] `pytest` in each plugin and in `client-cli`. `plugin-stt-sherpa-onnx` hangs for a
      reason that predates this work — see `docs/development/testing.md#known-issues`.
- [ ] `cd client-web/web && npm ci && npm test && npx tsc --noEmit && npm run lint`.
- [ ] `docker compose config`.
- [ ] The `e2e-test` skill against a running stack.
- [ ] State plainly what was run and what failed.

### 7. Publish — owner approval required

- [ ] Push `monorepo` to `origin`.
- [ ] Merge into `main` **with a merge commit or a fast-forward**
      (`git switch main && git merge --ff-only monorepo && git push`). Never "Squash and
      merge" or "Rebase and merge": both destroy the imported history.

### 8. Retire the old layout — owner approval required

- [ ] In each of the ten component repositories, add a README notice pointing to
      `speechmux/speechmux`, then **archive** the repository on GitHub. Do not delete:
      archiving is reversible and keeps old commit hashes and links resolvable.
- [ ] Make this checkout the working directory. Carry over the local, untracked files
      from `~/src/speechmux` listed below; rebuild `.venv` with `make setup` and
      `node_modules` with `npm ci` rather than copying them.
- [ ] Delete this document, its row in `docs/README.md` and its entry in
      `docs/plans/roadmap.md`.

### Local files to carry over

Checked in `~/src/speechmux` on 2026-11-24: there is no `.env`, no `models/` and no
`assets/` directory, and no component has untracked or ignored files other than build
output and caches (`core/bin/`, `client-web/web/tsconfig.tsbuildinfo`, `node_modules`,
`.venv`). Nothing needs copying. Re-check before deleting the old workspace, because model
files downloaded later (`make download-models`) would land in an ignored path.
