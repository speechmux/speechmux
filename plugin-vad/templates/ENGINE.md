# ENGINE.md — <engine display name>

Engine-specific rules for `plugin-vad-<impl>`. The common rules for every VAD engine
adapter are in `AGENTS.md` beside this file; do not repeat them here. Write only what is
true of **this** engine and would surprise someone who has read `AGENTS.md`.

Delete this instruction block and every `<placeholder>` before committing.

---

## Role

<One paragraph: what model this wraps, which hardware it targets, why someone would pick
it.>

## Entry point and names

| Name | Value |
|------|-------|
| Entry-point name (`server.engine:`) | `<engine_name>` |
| Class | `speechmux_plugin_vad_<impl>.<module>:<ClassName>` |
| Config section | `engine.<engine_name>:` in `plugin-vad/config/vad.yaml` |

## Declared capabilities

```python
model_name = "<...>"
optimal_frame_ms = <n>
supported_sample_rates = [<...>]
max_concurrent_sessions = <n>
```

## Session state and isolation

<How `create_session_state` isolates sessions: model copy, per-session buffers, what is
shared read-only. What would break if two sessions shared state.>

## Frame handling

<The frame size the model needs, how chunks of another size are re-buffered, any cap on the
buffer and why.>

## Configuration

<Table of the keys `from_config` reads, with defaults. Note any key present in `vad.yaml`
that is accepted but not consumed.>

## Pitfalls

<Bugs found while building it and the invariant each one taught.>

## Test suite status

<Current state of `make test`, any real dependency the tests need, known failures with
cause and tracking link.>

## Do not

<Engine-specific prohibitions only.>
