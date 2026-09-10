# Skill: add-config-option

Add a configuration key to `core.yaml`, `plugins.yaml` or a plugin YAML — in every copy that
exists.

## When to use this

- A value is hardcoded in Core or a plugin and needs to be operator-tunable.
- A new feature needs a knob.
- An existing key needs a new sub-key.

**Do not** use this to change a default. That is a one-line edit plus a note in
[docs/operations/configuration.md](../../../docs/operations/configuration.md).

## Should it be configuration at all?

Externalise a value when at least one is true:

- It differs by **hardware** (`fair_dispatch_max_concurrent`, `max_concurrent_sessions`).
- It differs by **deployment** (ports, sockets, TLS paths, allowed origins).
- It differs by **workload** (`vad_silence_sec` — conversation vs monologue).
- It is a **safety limit** an operator must be able to disable (`vad_watermark_lag_threshold_sec`).

Keep it a constant when it is an internal invariant (`lcpWindowRunes`, `batchFrameMs`,
`writerChanSize`) or when a wrong value would break correctness rather than tune it. Every
key added is a key someone must understand, document and keep in sync across five files.

## Prerequisites

Read the layout in
[docs/operations/configuration.md](../../../docs/operations/configuration.md).

---

## Steps for a `core.yaml` key

### 1. Add the struct field

`core/internal/config/config.go`, in the right section struct:

```go
type StreamConfig struct {
    ...
    MyNewOption float64 `yaml:"my_new_option"` // one-line purpose and unit
}
```

`time.Duration` cannot be unmarshalled from a plain integer, so durations use the
raw/parsed pair pattern already in `ServerConfig`:

```go
MyTimeout    time.Duration `yaml:"-"`
MyTimeoutRaw int           `yaml:"my_timeout_sec"`
```

and the conversion goes in `Config.Validate()`.

### 2. Add the default

`Config.Defaults()`:

```go
if c.Stream.MyNewOption == 0 {
    c.Stream.MyNewOption = 1.5
}
```

**Decide deliberately whether `0` means "unset" or "disabled".** Both conventions are in
use: `vad_watermark_lag_threshold_sec: 0` and `fair_dispatch_max_partial_queue: 0` mean
*disabled/unlimited* and are explicitly excluded from `Defaults()`, with a comment saying
so. If `0` is a meaningful value for your key, do not give it a default — say why in a
comment, as `VADWatermarkLagThresholdSec` does.

### 3. Validate if there are illegal values

`Config.Validate()` returns an error. Follow the `endpointing_source` precedent: reject
`hybrid` at load rather than failing later per session.

### 4. Add it to **every** YAML copy, with an inline comment

| File | Always |
|------|--------|
| `core/config/core.yaml` | yes |
| `deploy/docker/core-docker.yaml` | **yes — this is the step that gets forgotten** |

```yaml
stream:
  my_new_option: 1.5   # What it controls and in what unit. Say what 0 means if 0 is special.
```

The comment convention is mandatory. Say the unit, the range if bounded, and what the
extreme values mean. Look at `fair_dispatch_max_concurrent` in `core/config/core.yaml` for
the level of detail expected when the right value depends on hardware.

The two files are currently out of sync
([docs/operations/configuration.md](../../../docs/operations/configuration.md#known-config-drift));
do not add to that.

### 5. Consume it

Read through the atomic pointer, never from a cached `*Config`:

```go
cfg := p.cfg.Load()
x := cfg.Stream.MyNewOption
```

Engines snapshot `config.StreamConfig` at `Start`, so a value read there is fixed for the
session's lifetime. That is correct for anything that must not change mid-session, and
wrong for anything that should respond to a reload.

### 6. Classify its reload behaviour

Decide which bucket it falls in and add it to the table in
[docs/operations/configuration.md](../../../docs/operations/configuration.md#hot-reload):

| Bucket | Test |
|--------|------|
| Immediate | Read from `cfg.Load()` on each pipeline tick |
| New sessions only | Read at `CreateSession` or `Start` |
| Requires restart | Bound at construction (ports, TLS, listeners) |

If it should be immediate, make sure nothing snapshots it.

### 7. Tests

`core/internal/config/loader_test.go`: the default is applied when the key is absent, the
file value wins when present, and an invalid value is rejected. Add a behaviour test in
whichever package consumes it.

### 8. Documentation

Add a row to the relevant table in
[docs/operations/configuration.md](../../../docs/operations/configuration.md) with the
default and the meaning. If it changes pipeline behaviour, also update
[docs/architecture/core-pipeline.md](../../../docs/architecture/core-pipeline.md).

---

## Steps for a plugin YAML key

Simpler — there is no Go struct.

1. Add it under `server:` (framework-level) or `engine.<name>:` (engine-level) in the
   plugin's `config/*.yaml`, with an inline comment.
2. `server:` keys are read in the framework's `main.py`; `engine.<name>:` keys reach the
   engine only through its `from_config(cls, config)` classmethod. Use
   `config.get("key", default)` so an older config file still starts.
3. Mirror it into `deploy/docker/<plugin>-docker.yaml`.
4. Add a test that `from_config` picks it up and that the default applies when absent.
5. Document it in the engine repo's `README.md` and, if it is framework-level, in
   [docs/operations/configuration.md](../../../docs/operations/configuration.md).

---

## Files you will touch

| File | When |
|------|------|
| `core/internal/config/config.go` | core key: struct + `Defaults()` + `Validate()` |
| `core/config/core.yaml` | core key |
| `deploy/docker/core-docker.yaml` | core key — always |
| `core/config/plugins.yaml`, `deploy/docker/plugins-docker.yaml` | plugin-endpoint key |
| `plugin-*/config/*.yaml`, `deploy/docker/*-docker.yaml` | plugin key |
| The consuming Go/Python source | always |
| `core/internal/config/loader_test.go` | core key |
| `docs/operations/configuration.md` | always |

---

## Verification

```bash
cd core && go test ./internal/config/ && go test ./...

# Default applies when the key is absent.
cp core/config/core.yaml /tmp/no-key.yaml && sed -i '' '/my_new_option/d' /tmp/no-key.yaml
core/bin/speechmux-core --config /tmp/no-key.yaml --plugins core/config/plugins.yaml

# The file value is actually read (set an extreme value and observe the effect).
# An invalid value is rejected at startup.

# The key sets match across native and Docker.
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

# Hot-reload behaves as classified.
kill -HUP $(pgrep -f speechmux-core)
```

---

## Common mistakes

- **Forgetting `deploy/docker/core-docker.yaml`.** The Docker deployment silently runs the
  code default. This is the single most common error here.
- **No inline comment.** Non-negotiable convention.
- **A default that collides with a meaningful `0`.** If `0` means "disabled", do not put
  the key in `Defaults()` — and leave a comment saying that is deliberate.
- **`time.Duration` with a plain `yaml:"..."` tag.** It will not unmarshal from an integer.
  Use the raw/parsed pair.
- **Claiming it is hot-reloadable when a snapshot is taken at session start.** Verify by
  actually sending SIGHUP mid-session.
- **Leaving a key behind after removing the feature.** `decode.max_pending` is still in
  `core-docker.yaml` with no struct field — inert, but it tells operators a lie.
- **Making it configurable when it is an invariant.** A knob that can only be set wrong is
  a bug waiting to be filed.

---

## Done when

- [ ] Struct field, default (or a documented reason for none), and validation are in place.
- [ ] The key exists with an inline comment in **every** copy of the file, native and Docker.
- [ ] The consuming code reads it through `cfg.Load()`.
- [ ] Config tests cover default, override and invalid value.
- [ ] The key-set comparison between native and Docker shows no new divergence.
- [ ] Its reload behaviour is classified and recorded in
      [docs/operations/configuration.md](../../../docs/operations/configuration.md).
