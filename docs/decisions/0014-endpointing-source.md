# 0014 — `endpointing_source` is a field on `StreamStartConfig`

Status: Accepted

## Context

A native-streaming engine like sherpa-onnx has its own endpoint detection. Core also has
VAD plus an `EPDController`. If both run, the utterance is finalized twice and the
transcript is duplicated. Something must decide who owns the boundary, and the plugin has
to know the answer before it processes the first frame.

Streaming ability and engine-side endpointing are also not the same question: an engine can
stream without being able to finalize, and Core needs to distinguish "can detect an
endpoint" from "will finalize on its own".

## Decision

Two independent capability axes in `InferenceCapabilities`:

- `streaming_mode`: `BATCH_ONLY` | `NATIVE`
- `endpointing_capability`: `NONE` | `DETECTION` | `AUTO_FINALIZE`

And one runtime selector, `EndpointingSource`, carried as a field on `StreamStartConfig`:

| Value | Behaviour |
|-------|-----------|
| `CORE` (and `UNSPECIFIED`) | Core's VAD + EPD sends `KIND_FINALIZE_UTTERANCE`; the engine must not auto-finalize |
| `ENGINE` | The engine finalizes autonomously; Core starts no VAD at all |

`resolveEndpointingSource` validates the configured `stream.endpointing_source` against the
pinned engine's capabilities and fails the session with **ERR1020** when `engine` is asked
for without both `NATIVE` and `AUTO_FINALIZE`. A `hybrid` value is rejected at config load
(**ERR1021** is reserved for it).

## Rationale

- Putting it in `StreamStartConfig` means it arrives with the data the plugin needs it for,
  in the message it must already parse. A separate negotiation RPC would add a round trip
  and a state machine for no additional information.
- Two enums rather than one combined value keeps the questions separable; a combined enum
  would need a new value for every future pairing.
- Validating upfront turns a silently-duplicated transcript into a clear startup error.
- `UNSPECIFIED` meaning `CORE` keeps every pre-existing plugin working unchanged.

## Consequences

- An engine that ignores the field double-finalizes in `core` mode. sherpa-onnx explicitly
  does not call its own `is_endpoint()` in that mode — the check is removed, not gated on a
  text condition.
- With `ENGINE`, Core runs no VAD: `NewVADClient` is skipped, two goroutines are not
  started, and the ring buffer must be trimmed by age instead of by watermark
  ([ADR 0005](0005-watermark-ring-buffer.md)).
- `ENGINE` mode has no VAD-based liveness signal, so it needs its own watchdogs:
  `engine_response_timeout_sec` and `max_utterance_sec`, surfacing as **ERR3007**.
- `hybrid` — both sources cooperating — is unimplemented and rejected at load, with the
  error code already reserved.
