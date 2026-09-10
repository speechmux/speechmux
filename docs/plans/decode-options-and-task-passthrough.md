# Forward decode options and task to the STT plugin (batch path)

Status: not started. Confirmed against the current tree.

## What is broken

Two client-facing settings are accepted, validated, negotiated and echoed back — and then
dropped before they reach the engine.

**`decode_profile`.** `core.yaml` defines named profiles:

```yaml
decode_profiles:
  realtime:  { beam_size: 1, best_of: 1, temperature: 0.0, ... }
  accurate:  { beam_size: 5, best_of: 5, temperature: 0.0, ... }
```

They are parsed into `config.DecodeProfile`, resolved onto `SessionInfo.DecodeProfile`, and
returned in `SessionCreated.negotiated_recognition`. But `batch_engine.go` builds every
task with:

```go
DecodeOptions: nil, // TODO: forward from negotiated session config
```

`core/internal/stream/batch_engine.go:353`. The plugin therefore falls back to the
`beam_size` in its own YAML for every request. Choosing `realtime` versus `accurate` has no
effect on decoding.

**`task`.** `TASK_TRANSLATE` is accepted by both transports, stored on
`SessionInfo.Task`, exposed by `client-cli --task translate`, and echoed in
`SessionCreated` — but `batch_engine.go:352` hardcodes
`Task: inferencepb.Task_TASK_TRANSCRIBE`. Translation never happens.

Everything downstream already works: `TranscribeRequest` carries both fields, and
`plugin-stt`'s `_decode_options_to_dict` / `_task_name` convert them for the engine.

## Scope

Core (`core` repo) only. No proto change, no plugin change.

## Steps

1. Add `Task` and `DecodeOptions` to `stream.SessionDecodeConfig` (`stream/engine.go`).
2. In `processor.go`, resolve `sess.Info.DecodeProfile` against `cfg.DecodeProfiles`,
   convert to `*inferencepb.DecodeOptions`, and map `sess.Info.Task` to
   `inferencepb.Task`. Put the conversion in one helper — the streaming path needs it too
   for `StreamStartConfig`.
3. Pass both through in `batchDecodeEngine.runSubmitter`'s `BatchTask`.
4. Decide and document the partial-decode behaviour: a partial may warrant `realtime`
   parameters even when the session asked for `accurate`, since partials are discarded.
   Whatever is chosen, state it in `core.yaml`'s comment for `decode_profiles`.
5. Handle an unknown profile name. **ERR4009** (`unknown model profile`) is registered but
   unused and is the obvious candidate; alternatively fall back to `realtime` and log.
6. Fill `StreamStartConfig.decode_options` and `.task` on the streaming path too — they are
   currently unset there as well.

## Verification

- Unit test in `batch_engine_test.go` asserting the enqueued `BatchTask` carries the
  resolved beam size and task.
- Unit test for the profile → `DecodeOptions` conversion, including the unknown-name case.
- Manual: run with `--profile accurate`, confirm `beam_size=5` in the plugin log at DEBUG.

## Then

Update [../operations/configuration.md](../operations/configuration.md) (remove the "not
yet forwarded" note), [../api/plugin-protocol.md](../api/plugin-protocol.md), and
[../architecture/core-pipeline.md](../architecture/core-pipeline.md). Delete this file.
