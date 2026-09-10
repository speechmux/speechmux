# Skill: add-engine-plugin

Add a new STT or VAD engine to SpeechMux.

## When to use this

- Adding a new speech recognition backend (`plugin-stt-<impl>`).
- Adding a new voice activity detector (`plugin-vad-<impl>`).
- Wiring an engine repo that already exists into the workspace, Core and Docker.

**Do not** use this for changing an existing engine's behaviour, or for adding a
language/model to an engine that already exists — that is a config change only.

## Prerequisites

- Read [../../../AGENTS.md](../../../AGENTS.md) §10 and
  [docs/architecture/plugin-system.md](../../../docs/architecture/plugin-system.md).
- Workspace set up: `.venv` exists, `proto`, `core`, `plugin-stt`/`plugin-vad` cloned.
- Know which contract you are implementing:

| Engine kind | Protocol | Entry-point group | Capability it must report |
|-------------|----------|-------------------|---------------------------|
| STT, decodes a whole segment (Whisper family) | `InferenceEngine` | `speechmux.stt_engine` | `STREAMING_MODE_BATCH_ONLY` (the servicer sets this) |
| STT, decodes continuously | `StreamingInferenceEngine` | `speechmux.stt_engine` | `streaming_mode = NATIVE`, plus an honest `endpointing_capability` |
| VAD | `VADEngine` | `speechmux.vad_engine` | — |

Pick the closest existing engine as your reference: `plugin-stt-faster-whisper` (batch),
`plugin-stt-sherpa-onnx` (streaming), `plugin-vad-silero` (VAD).

---

## Steps

### 1. Create the engine repository

Create `github.com/speechmux/plugin-{stt,vad}-<impl>` and clone it into the workspace. The
layout is the same for every engine:

```
plugin-stt-<impl>/
├── AGENTS.md                 # cp plugin-stt/templates/AGENTS.md — do NOT edit the copy
├── CLAUDE.md                 # one line: @AGENTS.md
├── ENGINE.md                 # cp plugin-stt/templates/ENGINE.md, then fill it in
├── LICENSE
├── Makefile                  # copy verbatim from plugin-stt-faster-whisper
├── README.md
├── pyproject.toml
├── src/speechmux_plugin_stt_<impl>/
│   ├── __init__.py
│   └── engine.py
└── tests/
    └── test_<impl>_engine.py
```

Two files come straight from the host framework's `templates/` directory:

```bash
cp plugin-stt/templates/AGENTS.md plugin-stt-<impl>/AGENTS.md   # byte-identical, never edited here
cp plugin-stt/templates/ENGINE.md plugin-stt-<impl>/ENGINE.md   # fill in every <placeholder>
printf '@AGENTS.md\n' > plugin-stt-<impl>/CLAUDE.md           # import, not a copy
```

(`plugin-vad/templates/` for a VAD engine.) `AGENTS.md` holds the rules common to every
engine adapter and must stay identical across repos; everything specific to this engine —
capabilities, config keys, runtime quirks, pitfalls, test status — goes in `ENGINE.md`.

`Makefile` is identical across every engine repo (`install`, `test`, `lint`, `typecheck`,
`clean`, with `PYTHON ?= ../.venv/bin/python3`). Copy it rather than writing a new one.

### 2. `pyproject.toml`

Copy from the closest engine and change the name, the dependency and the entry point:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "speechmux-plugin-stt-<impl>"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "speechmux-plugin-stt>=0.0.0",   # or speechmux-plugin-vad
    "<the ML runtime>",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.4", "mypy>=1.10"]

[project.entry-points."speechmux.stt_engine"]
<engine_name> = "speechmux_plugin_stt_<impl>.engine:<ClassName>"

[tool.hatch.build.targets.wheel]
packages = ["src/speechmux_plugin_stt_<impl>"]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.10"
strict = true
```

`<engine_name>` is snake_case and is what goes in `server.engine:` in the YAML. Existing
names: `dummy`, `mlx_whisper`, `faster_whisper`, `sherpa_onnx_zipformer`, `silero`.

**Dependency rule:** depend on the host framework and your ML runtime, nothing else. Never
import Core, another engine, or gRPC server machinery.

### 3. Implement the engine

Subclass the Protocol explicitly and set every class attribute — the servicer reads them
directly to build `GetCapabilities`.

```python
from __future__ import annotations
from speechmux_plugin_stt.engine.base import InferenceEngine, TranscribeResult

class MyEngine(InferenceEngine):
    engine_name = "my_engine"
    model_size = "large-v3"
    device = "cpu"
    supported_languages = ["en", "ko"]
    max_concurrent_requests = 1
    supports_partial_decode = True

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "MyEngine":
        """Build the engine from the engine.<name> section of the plugin YAML."""
        return cls(model=config.get("model", "large-v3"), ...)

    def load(self) -> None:
        """Load weights. Called once before the gRPC server accepts requests."""

    def transcribe(self, audio_data, sample_rate, language_code, task,
                   decode_options, is_final, is_partial) -> TranscribeResult:
        ...
```

Requirements:

- `from __future__ import annotations`, full type annotations, Google-style docstrings with
  Args/Returns/Raises, 100-column lines.
- `from_config` is the **only** way YAML reaches the engine. Never read a file yourself.
- `load()` must be eager. A lazy first-request load makes the first session time out.
- Catch `ImportError` on the ML runtime and re-raise with an install hint — a bare
  `ModuleNotFoundError` in a plugin process is opaque to the operator.
- Convert PCM S16LE to float32 in `[-1, 1]` (`samples.astype(np.float32) / 32768.0`).
- A **streaming** engine's `stream()` generator must **return**, not raise, when the request
  iterator is exhausted, and must honour `session_config.endpointing_source`: in `CORE`
  mode it must not auto-finalize on its own endpoint detection, only on
  `KIND_FINALIZE_UTTERANCE`.

### 4. Write tests that never load a model

Mock the runtime before importing the engine. Copy the pattern from the reference repo:

```python
import sys
from unittest.mock import MagicMock

@pytest.fixture()
def mock_runtime():
    sys.modules.pop("my_runtime", None)
    for key in [k for k in sys.modules if k.startswith("speechmux_plugin_stt_<impl>")]:
        sys.modules.pop(key)
    module = MagicMock()
    sys.modules["my_runtime"] = module
    yield module
    # purge again so the next test starts clean
```

Every test that touches the engine must request the fixture — including tests of module-level
helpers, if those live in a module that imports the runtime.

**Set every mock attribute the production code reads in a loop condition.** A bare
`MagicMock()` is truthy, so `while recognizer.is_ready(stream):` against one never
terminates. This is a live bug in `plugin-stt-sherpa-onnx`
([docs/development/testing.md](../../../docs/development/testing.md#known-issues)).

### 5. Add an engine section to the plugin config

In `plugin-stt/config/<a config file>.yaml` (or `plugin-vad/config/vad.yaml`), or a new file
in your own repo's `config/` if the engine needs its own (like
`plugin-stt-faster-whisper/config/inference-faster-whisper.yaml`):

```yaml
server:
  socket: /tmp/speechmux/stt-<impl>.sock  # UDS path. XOR with `address: "0.0.0.0:5006N"`.
  engine: <engine_name>                    # Entry-point name registered above.
  log_level: INFO                          # DEBUG | INFO | WARNING | ERROR.
  max_concurrent_sessions: 1               # Set to the engine's real parallelism.
  log_transcription_text: true             # false logs a character count instead.

engine:
  <engine_name>:
    model: ...        # Every key needs an inline comment: purpose and unit.
```

**Every key gets an inline comment.** This is a hard convention.

### 6. Register the endpoint with Core

`core/config/plugins.yaml`:

```yaml
inference:
  endpoints:
    - id: "<impl>"                            # This id is what clients pass as engine_hint.
      socket: "/tmp/speechmux/stt-<impl>.sock"  # Must match server.socket above.
      priority: 1                             # Higher = preferred under active_standby.
```

Only `id`, `socket`/`address` and `priority` go here. Engine name, device and capabilities
are discovered at runtime
([ADR 0007](../../../docs/decisions/0007-runtime-capability-discovery.md)).

### 7. Add a workspace profile

Root `workspace.yaml`, under the matching category in `profiles:`, and add the name to that
slot's `profiles:` list in `processes:`:

```yaml
profiles:
  stt-plugins:
    <impl>:
      command: .venv/bin/python3
      args: ["-m", "speechmux_plugin_stt.main", "--config", "plugin-stt/config/inference-<impl>.yaml"]
      working_directory: "."
      restart: on-failure
      startup_delay_ms: 0

processes:
  - name: stt-plugins
    profiles: [sherpa-onnx, mlx-whisper, <impl>]   # add here too
```

Optionally add it to the `Makefile`'s default `PROFILES`.

### 8. Add a Docker service (if it should run in Docker)

- `deploy/docker/inference-<impl>-docker.yaml` — same schema, but `address: "0.0.0.0:5006N"`
  instead of `socket:`, and container-internal model paths.
- `deploy/docker/plugins-docker.yaml` — an endpoint with `address: "stt-<impl>:5006N"`.
- `docker-compose.yml` — a service behind a `profiles: ["<impl>"]` label, with a
  `healthcheck` whose `start_period` covers the model load time.
- The `Makefile`'s `DOCKER_PROFILE` default and the `docker-logs*` targets.

---

## Files you will touch

| File | Repo |
|------|------|
| `plugin-{stt,vad}-<impl>/**` (new) | new repo |
| `plugin-{stt,vad}/config/*.yaml` or your own `config/` | plugin host or new repo |
| `core/config/plugins.yaml` | `core` |
| `workspace.yaml` | workspace |
| `Makefile` (`PROFILES`, `DOCKER_PROFILE`, `docker-logs*`) | workspace |
| `docker-compose.yml`, `deploy/docker/*.yaml` | workspace |
| `.env.example` (if it needs a `MODELS_DIR`) | workspace |
| `README.md` component table and clone instructions | workspace |
| `docs/architecture/plugin-system.md`, `docs/operations/deployment.md` | workspace |
| `plugin-{stt,vad}-<impl>/AGENTS.md` (verbatim template copy) and `ENGINE.md` (filled in) | new repo |

---

## Verification

```bash
# 1. Install and confirm the entry point registers.
uv pip install --python .venv/bin/python3 -e "plugin-stt-<impl>[dev]"
.venv/bin/python3 -c "from speechmux_plugin_stt.engine.registry import list_engines; print(list_engines())"
#   → your engine name must appear

# 2. Tests, lint, typecheck (must pass without the real ML runtime).
cd plugin-stt-<impl> && ../.venv/bin/python3 -m pytest tests/ -q
../.venv/bin/python3 -m ruff check src/
../.venv/bin/python3 -m mypy src/

# 3. The plugin starts and binds.
.venv/bin/python3 -m speechmux_plugin_stt.main --config plugin-stt/config/inference-<impl>.yaml
#   → "STT Plugin listening on unix:///tmp/speechmux/stt-<impl>.sock (engine=<name>)"

# 4. Core discovers it with the right capabilities.
make up PROFILES="silero <impl>"
curl -s -H "Authorization: $ADMIN_TOKEN" localhost:8090/admin/plugins | jq
#   → your endpoint, healthy:true, engine_name/model_size/device populated
curl -s localhost:8090/health | jq

# 5. End to end.
.venv/bin/speechmux file sample.wav --lang en --engine-hint <impl> --metrics
```

If step 4 shows empty `engine_name`, `GetCapabilities` failed — check the plugin log. Core
retries in the background, so wait one health-probe interval before concluding it is broken.

---

## Common mistakes

- **Forgetting to install the package.** Entry points only exist for installed
  distributions. `list_engines()` not showing your engine almost always means this.
- **`engine_hint` vs engine name.** Clients pass the endpoint `id` from `plugins.yaml`
  (`whisper-mlx`), not the entry-point name (`mlx_whisper`). Choosing confusingly different
  strings for the two is a recurring source of support questions.
- **Lazy model loading.** Not loading in `load()` means the first request pays the load
  cost and hits `decode_timeout_sec`.
- **Misreporting `streaming_mode`.** A `NATIVE` claim from an engine that only implements
  `transcribe()` makes Core open a `TranscribeStream` that nothing serves. A `BATCH_ONLY`
  claim from a streaming engine makes `RouteBatch()` send it unary requests.
- **Claiming `AUTO_FINALIZE` without honouring `endpointing_source`.** In `CORE` mode the
  engine must finalize *only* on `KIND_FINALIZE_UTTERANCE`. Auto-finalizing as well
  duplicates the transcript.
- **Tests that import the real runtime.** They pass on your machine and fail everywhere
  else. Mock before import, in every test that touches the engine module.
- **A bare `MagicMock()` in a loop condition.** It is truthy; the loop never ends and the
  suite hangs rather than fails.
- **Editing the copied `AGENTS.md`.** It must stay identical to the template. If a rule
  belongs to every engine, change the template and re-copy; if it belongs to this engine,
  it goes in `ENGINE.md`.
- **Uncommented YAML keys.** Every key needs an inline comment.
- **Editing only `plugins.yaml` and not `plugins-docker.yaml`.** The Docker deployment
  silently keeps running without your engine.
- **`max_concurrent_sessions` larger than the engine's real parallelism.** It does not add
  throughput; it adds queueing inside the engine, where Core can no longer reorder or
  cancel.

---

## Done when

- [ ] The engine repo exists with `pyproject.toml`, `Makefile`, `README.md`, `LICENSE`,
      `src/`, `tests/`.
- [ ] `AGENTS.md` is byte-identical to `plugin-{stt,vad}/templates/AGENTS.md`
      (`cmp` returns 0), `ENGINE.md` has no `<placeholder>` left, and `CLAUDE.md` contains
      exactly `@AGENTS.md`.
- [ ] `list_engines()` includes the engine name.
- [ ] `pytest`, `ruff check src/`, `mypy src/` all pass **without** the ML runtime installed.
- [ ] The plugin process starts and binds its socket/address.
- [ ] `/admin/plugins` reports the endpoint healthy with populated engine metadata.
- [ ] `/health` reports `ok`.
- [ ] A real transcription succeeds via `engine_hint`.
- [ ] `workspace.yaml`, `Makefile`, `core/config/plugins.yaml` are updated; Docker files too
      if applicable.
- [ ] `README.md`'s component table and
      [docs/architecture/plugin-system.md](../../../docs/architecture/plugin-system.md)
      list the new engine.
- [ ] Committed in each affected repository separately.
