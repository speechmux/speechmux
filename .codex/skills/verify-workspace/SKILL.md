# Skill: verify-workspace

Run the build, test and lint sweep across every repository in the workspace, and report what
actually happened.

## When to use this

- Before declaring any change complete.
- After cloning or setting up the workspace, to establish a baseline.
- When a command in a document needs to be confirmed still correct.

The workspace spans ten repositories with three toolchains and only one of them has CI, so
local verification is the only gate. Run the suites for the repos your change touched at
minimum; run everything before finishing a cross-repo change.

## Prerequisites

- Go 1.25+, Node 22+, `uv`, and a `.venv` (see
  [docs/development/workspace.md](../../../docs/development/workspace.md#setup)).
- Use `.venv/bin/python3` explicitly. The system `python3` on macOS is 3.9 and will fail.
- **Read the known issues** in
  [docs/development/testing.md](../../../docs/development/testing.md#known-issues) first.
  Several suites fail or hang for reasons that predate your change; do not spend time
  rediscovering them, and do not report them as your regressions.

---

## Steps

### 1. Establish what is present

```bash
cd /path/to/speechmux
ls -d proto core plugin-* client-* 2>/dev/null
```

Only cloned repos can be verified. A missing one is a gap in coverage, not a pass — say so.

### 2. Go: build, test, vet

```bash
make build                       # expect: builds core/bin/speechmux-core
cd core && go test ./...         # expect: every package ok
cd core && go test -race ./...   # slower; run for pipeline/concurrency changes
cd core && go vet ./...          # expect: clean
```

`go test ./internal/stream/` and `./internal/transport/` are the integration-heavy packages
and take longest. `-race` is what `core/Makefile test` runs and is worth the wait for
anything touching `stream`, `session` or `transport`.

Do **not** run `gofmt -w`. It reformats 29 pre-existing files and would bury your diff.
`gofmt -l .` reporting those files is the known baseline.

### 3. Proto

```bash
cd proto && buf lint                                    # expect: clean
cd proto && buf breaking --against '.git#branch=main'   # what CI runs on PRs
cd proto && make generate && git diff --stat gen/       # expect: empty if you changed no .proto
```

A non-empty `gen/` diff when you changed no `.proto` means your local `protoc`/
`grpcio-tools` differ from the versions the repo was generated with. Revert it
(`git checkout -- gen/`) rather than committing the churn.

### 4. Python

```bash
PY=$PWD/.venv/bin/python3

for d in plugin-vad plugin-stt plugin-stt-mlx-whisper plugin-stt-faster-whisper client-cli; do
  echo "=== $d"; (cd $d && $PY -m pytest tests/ -q)
done

for d in plugin-vad plugin-stt; do
  echo "=== $d lint"; (cd $d && $PY -m ruff check src/; $PY -m mypy src/)
done
```

Expected baseline on a clean tree: `plugin-vad` 11 passed, `plugin-stt` 38,
`plugin-stt-mlx-whisper` 10, `plugin-stt-faster-whisper` 15, `client-cli` 29.
`ruff check src/` reports 5 findings in each plugin framework and `mypy src/` reports one
error in `plugin-vad` — all pre-existing.

**`plugin-stt-sherpa-onnx` hangs.** Run only the part that terminates:

```bash
cd plugin-stt-sherpa-onnx && $PY -m pytest tests/test_stream.py -q   # 9 passed
```

`tests/test_engine.py` fails four tests and then hangs forever in
`test_force_finalize_emits_final`. Because of this, **`make test` never completes** — run
the suites individually until it is fixed
([docs/plans/test-and-lint-gaps.md](../../../docs/plans/test-and-lint-gaps.md)).

`plugin-vad-silero` needs a real `torch` install; skip it under the light setup and say you
skipped it.

### 5. Frontend

```bash
cd client-web/web && npx tsc --noEmit     # expect: clean
cd client-web/web && npm run lint         # expect: no warnings (plus a next-lint deprecation notice)
```

There is no `npm test` — no test runner is configured. `client-web/api` has no `tests/`
directory, so any pytest command for it will fail; that is a gap, not a regression.

### 6. Config and deployment

```bash
docker compose --profile sherpa --profile faster-whisper config --quiet   # expect: exit 0
core/bin/speechmux-core ctl status --workspace workspace.yaml             # expect: a table

# Native and Docker core configs should hold the same keys.
.venv/bin/python3 - <<'PY'
import yaml
def flat(d, p=""):
    out = set()
    for k, v in (d or {}).items():
        key = p + k
        out |= flat(v, key + ".") if isinstance(v, dict) else {key}
    return out
a = flat(yaml.safe_load(open("core/config/core.yaml")))
b = flat(yaml.safe_load(open("deploy/docker/core-docker.yaml")))
print("only native:", sorted(a - b))
print("only docker:", sorted(b - a))
PY
```

The known divergence is `decode.max_pending` (docker-only, dead) and `logging.format` /
`stream.fair_dispatch_max_*` (native-only). Anything beyond that is new.

### 7. Engine `AGENTS.md` template drift

Every engine repo's `AGENTS.md` must be byte-identical to its host framework's template:

```bash
for d in plugin-stt-*/; do cmp -s plugin-stt/templates/AGENTS.md "$d/AGENTS.md" || echo "DRIFT: $d"; done
for d in plugin-vad-*/; do cmp -s plugin-vad/templates/AGENTS.md "$d/AGENTS.md" || echo "DRIFT: $d"; done
grep -l '<placeholder>\|<engine_name>\|<impl>' plugin-*-*/ENGINE.md 2>/dev/null && echo "unfilled ENGINE.md above"
```

Expect no output. A `DRIFT` line means someone edited a copy instead of the template.

### 8. Runtime (when the change warrants it)

Needs real model weights and a full `make setup`:

```bash
make up PROFILES="silero sherpa-onnx"
make status
curl -s localhost:8090/health | jq
curl -s -H "Authorization: $ADMIN_TOKEN" localhost:8090/admin/plugins | jq
.venv/bin/speechmux file sample.wav --lang ko --metrics
make down
```

---

## Reporting

State plainly, per command: what you ran, whether it passed, and the actual output for
anything that failed.

- Separate **pre-existing** failures from **new** ones. The baseline is in
  [docs/development/testing.md](../../../docs/development/testing.md#known-issues).
- Say explicitly what you did **not** run and why (repo not cloned, needs `torch`, needs
  model weights, needs Docker images).
- Never report a suite as passing because it did not print an error — a hung suite prints
  nothing.
- "Tests pass" is not a report. Name the suites and the counts.

---

## Common mistakes

- **Running `make test` and waiting.** It hangs in `plugin-stt-sherpa-onnx`. Kill it and
  run the suites individually.
- **Using the system `python3`.** Python 3.9 on macOS; the packages are in `.venv`.
- **Reporting the pre-existing ruff/mypy/gofmt findings as your regressions.**
- **Running `gofmt -w` to make `gofmt -l` clean.** 29 unrelated files, diff buried.
- **Committing regenerated `proto/gen/` churn** from a different toolchain version.
- **Claiming an untested repository passed** because it was not cloned.
- **Skipping `-race`** on a change to `stream`, `session` or `transport`.

---

## Done when

- [ ] Every repository your change touched has had its suite run.
- [ ] `go vet`, `buf lint` and `tsc --noEmit` are clean.
- [ ] Every failure is classified as pre-existing (with a link) or new (with the output).
- [ ] Everything you could not run is listed with a reason.
- [ ] `proto/gen/` has no unintended diff.
- [ ] The native/Docker config key comparison shows no new divergence.
- [ ] No engine `AGENTS.md` has drifted from its template.
