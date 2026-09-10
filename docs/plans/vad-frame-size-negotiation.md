# Use the VAD plugin's advertised `optimal_frame_ms`

Status: not started. Low priority — the current fixed value works with Silero.

## What is missing

`VADCapabilities.optimal_frame_ms` exists in the proto and the Silero engine reports 32 ms
(512 samples @ 16 kHz, which is what the model actually requires). Core never calls
`VADPlugin.GetCapabilities` and instead hardcodes:

```go
optFrameMs := 30 // default; updated by GetCapabilities in a future phase
```

`core/internal/stream/processor.go:386`, and the matching constant `batchFrameMs = 30` in
`batch_engine.go:37`.

The 2 ms mismatch is absorbed by the Silero engine, which re-buffers incoming audio into
512-sample frames itself. It is not currently causing a bug. The cost is that a VAD engine
with a materially different frame size cannot be used correctly.

## Why it is not a one-line change

`batchFrameMs` is not only the aggregation period. It is also the sequence-number → seconds
conversion factor:

```go
func seqToSec(seq uint64) float64 { return float64(seq) * float64(batchFrameMs) / 1000.0 }
```

so it determines `start_sec` / `end_sec` on every result. And `AudioRingBuffer` sizes
itself as `max_buffer_sec × 100` entries, which assumes ~10 ms per entry — changing the
frame size changes the effective buffer duration.

## Steps

1. Call `VADPlugin.GetCapabilities` once per endpoint at registration (mirroring
   `InferenceClient.FetchCapabilities`) and cache `optimal_frame_ms`. Treat `0` as 30 ms.
2. Thread the value into `SessionDecodeConfig` so `vadSendLoop` and the batch engine share
   one source instead of two constants.
3. Replace `batchFrameMs` with that per-session value in `seqToSec`, and add a test that
   `start_sec`/`end_sec` are correct at a non-30 ms frame size.
4. Derive `AudioRingBuffer` capacity from the frame size rather than the `× 100` constant,
   so `max_buffer_sec` means the same thing at any frame size.
5. Handle a mixed VAD pool: endpoints reporting different frame sizes must not share a
   session. Simplest correct answer is to read the value from the endpoint the session was
   actually assigned.

## Verification

- `frame_aggregator_test.go` at 20 / 30 / 32 ms.
- `batch_engine_test.go` asserting timestamps at a non-default frame size.
- `audio_buffer_test.go` asserting the capacity derivation.
- End to end with Silero: no change in observed behaviour, `optimal_frame_ms=32` in the log.

## Then

Update [../architecture/core-pipeline.md](../architecture/core-pipeline.md#frameaggregator)
and [../api/plugin-protocol.md](../api/plugin-protocol.md). Delete this file.
