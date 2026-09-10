# Core session pipeline

How one client session is served, from the first byte of audio to the last result.
Source: `core/internal/stream/`, `core/internal/session/`, `core/internal/transport/`.

---

## Session lifecycle

1. **Transport accepts a connection.** gRPC (`transport/grpc_server.go`) requires the first
   `StreamingRecognizeRequest` to carry `session_config`; WebSocket
   (`transport/websocket_handler.go`) requires a first JSON frame of
   `{"type":"start"}` or `{"type":"resume"}`.
2. **`session.Manager.CreateSession`** authenticates (`session/auth.go`), applies rate
   limits and per-IP/per-key caps, resolves defaults into an immutable `SessionInfo`, and
   registers the `Session`. It fails with an `ERR1xxx` code before any plugin is touched.
3. **The transport confirms** with `session_created` / `{"type":"session"}`, echoing the
   negotiated audio, recognition and VAD settings.
4. **`StreamProcessor.ProcessSession` runs the pipeline** in its own goroutine while the
   transport's recv loop converts incoming audio (`codec.CodecConverter`) and pushes PCM
   S16LE into `sess.AudioInCh`.
5. **Results flow back** on `sess.ResultCh`; the transport serialises them to the client.
6. **Teardown.** `signal{is_last:true}` / `{"type":"end"}` closes `AudioInCh`, which
   cascades through the pipeline into a final decode. On an unexpected WebSocket drop the
   session can be *parked* for `resumable_session_timeout_sec` and picked up again with the
   resume token.

`Session` (`session/session.go`) owns the channels and the ordering guarantees:
`AudioInCh` (PCM in), `ResultCh` (results out), and `PipelineExitCh` (buffered 1) which
carries `ProcessSession`'s return value. `SignalPipelineExit` uses a `sync.Once` so the
error is always visible *before* `ResultCh` closes — the transport relies on that ordering
to send a `StreamError` frame rather than a clean `done`.

---

## Capability dispatch

`ProcessSession` (`stream/processor.go`) chooses the decode path before starting any
goroutine:

1. `PluginRouter.PinByHint(sessionID, engineHint)` pins the session to an endpoint. It
   honours `engine_hint` when that endpoint is healthy and otherwise falls back to normal
   routing. This is a single call by design — routing and reading capabilities from two
   different calls could disagree in a mixed pool.
2. `resolveEndpointingSource` validates `stream.endpointing_source` against the pinned
   engine's advertised capability. `engine` requires both `STREAMING_MODE_NATIVE` and
   `ENDPOINTING_CAPABILITY_AUTO_FINALIZE`, otherwise the session fails with **ERR1020**.
3. If `streaming_mode == STREAMING_MODE_NATIVE`: hold the pin for the session, acquire a
   streaming slot from `DecodeScheduler`, open a `TranscribeStream`, and build a
   `streamingDecodeEngine`.
4. Otherwise: release the pin immediately (the batch path routes per request) and build a
   `batchDecodeEngine` backed by the shared `FairDecodeDispatcher`.

Both implement the `DecodeEngine` interface (`stream/engine.go`), so the rest of the
pipeline is identical for either path.

---

## Goroutines per session

Started under one `errgroup`; the group's error terminates the session.

| # | Goroutine | Present when | Job |
|---|-----------|--------------|-----|
| 1 | `vadSendLoop` | always | `AudioInCh` → `FrameAggregator` → ring buffer + VAD plugin + `engine.FeedFrame` |
| 2 | `vadRecvLoop` | `src=core` | VAD plugin responses → `vadResultCh` |
| 3 | EPD loop (`EPDController.Run`) | `src=core` | Silence timing → `engine.OnSpeechStart/OnSpeechEnd/OnUtteranceEnd` |
| 4 | result forwarder | always | `engine.Results()` → `sess.ResultCh` |
| — | trim ticker | always | Every 5 s, `buf.Trim()` (or `TrimByAge` when `src=engine`) — deliberately **outside** the errgroup so it cannot fail the session |

Engines add their own internal goroutines (below). With `endpointing_source: engine`, VAD
is not started at all: goroutines 2 and 3 do not exist and the ring buffer is trimmed by
age instead of by watermark.

Shutdown ordering in `ProcessSession`'s `defer` is load-bearing:
`engine.Close()` → `SignalPipelineExit(err)` → `close(ResultCh)` → `MarkProcessingDone()`.
The engine must finish draining and close `Results()` before the forwarder exits, and the
error must be signalled before the channel closes.

---

## AudioRingBuffer

`stream/audio_buffer.go`. Frames are stored by sequence number, not by time.

- Capacity is `max_buffer_sec × 100` entries (minimum 200). `Append` returns `false` when
  full — that is a **backpressure signal, not an error**.
- `Trim()` evicts an entry only when *both* `seq <= confirmedWatermark` (VAD has
  acknowledged it) **and** it is older than `max_buffer_sec`. Audio VAD has not yet seen is
  never evicted, however old it is. This is what makes utterance extraction safe when the
  VAD plugin lags.
- `TrimByAge(maxSec)` ignores the watermark and is used only when VAD is not running
  (`endpointing_source: engine`), where the watermark would never advance.
- `ExtractRange(startSeq, endSeq)` returns the concatenated PCM for an utterance.

**Backpressure policy** differs by `StreamMode`:

| Mode | On a full buffer |
|------|------------------|
| `STREAM_MODE_BATCH` (file upload) | `vadSendLoop` waits 5 ms and retries. The transport stops reading, the HTTP/2 flow-control window fills, and the sender is throttled. |
| `STREAM_MODE_REALTIME` (live mic) | `DropOldest()` and continue, so the microphone never stalls. |

---

## FrameAggregator

`stream/frame_aggregator.go` re-frames client chunks into fixed-size frames before sending
them to the VAD plugin, cutting IPC overhead when clients send small buffers. Each returned
frame is an independent copy; `Flush()` emits the trailing partial frame at end of audio.

The frame size is currently the hardcoded `optFrameMs = 30` in `vadSendLoop`, and the same
constant (`batchFrameMs = 30`) is used to convert sequence numbers to seconds in
`batch_engine.go`. `VADCapabilities.optimal_frame_ms` is advertised by the plugin (Silero
reports 32 ms) but is not yet read by Core — see
[../plans/vad-frame-size-negotiation.md](../plans/vad-frame-size-negotiation.md).

---

## EPDController

`stream/epd_controller.go` consumes `VADFrame`s and decides when an utterance has ended.

- A frame counts as speech only if VAD says so **and** its RMS is above
  `speech_rms_threshold`. Low-energy frames are forced to silence.
- The silence timer starts on the *first* non-speech frame after speech and is not reset by
  subsequent non-speech frames. When it reaches `vad_silence_sec`, the utterance-end
  callback fires with the `[startSeq, endSeq]` range.
- Callbacks: `SetSpeechStartCallback`, `SetSpeechEndCallback`, `SetWatermarkLagCallback`,
  plus the utterance-end function passed to `Run`.
- **Silent-hang defence**: no VAD response for `vad_frame_timeout_sec` returns
  `ErrVADFrameTimeout` → the session closes with **ERR3004**.
- **Watermark-lag defence**: if the gap between the newest buffered audio and the VAD
  watermark exceeds `vad_watermark_lag_threshold_sec`, BATCH mode returns
  `ErrVADWatermarkLag` (ERR3004) and REALTIME mode only logs, at most once per 30 s. The
  threshold defaults to `0` (disabled) because file input outruns real time and trips it
  spuriously.
- Per-frame logging is DEBUG only; a configurable heartbeat
  (`epd_heartbeat_interval_sec`) reports liveness during long silences.

---

## Batch decode engine

`stream/batch_engine.go`. Goroutines started by `Start`: `runPartialTimer`,
`runSubmitter`, `runResultCollector`.

**Final decode.** `OnUtteranceEnd(startSeq, endSeq)` extracts the range from the ring
buffer and queues a task with `is_final=true`.

**Partial decode.** While speech is in progress, `runPartialTimer` periodically queues a
task with `is_partial=true` over the audio from `speechStartSeq` to now, capped at
`partial_decode_window_sec`. The interval adapts to the length of audio being re-decoded,
because Whisper attention is O(n²):

| Accumulated audio | Interval |
|---|---|
| `< 5 s` | `partial_decode_interval_sec` (default 1.5 s) |
| `5–10 s` | 3 s |
| `> 10 s` | 5 s |

**Ordering.** `runSubmitter` enqueues into the dispatcher and pushes the returned result
channel onto a FIFO; `runResultCollector` drains that FIFO, so the `ResultAssembler`
always sees results in submission order even when RPCs complete out of order.

`DecodeOptions` are currently sent as `nil` and `Task` is hardcoded to `TASK_TRANSCRIBE` —
a known gap, see
[../plans/decode-options-and-task-passthrough.md](../plans/decode-options-and-task-passthrough.md).

---

## FairDecodeDispatcher

`stream/fair_dispatch.go`. One instance is shared by every batch session (created inside
`NewStreamProcessor`, shut down by `Application.gracefulShutdown`). It exists because a
single-GPU engine processes one request at a time: without cross-session fairness, one busy
session starves the rest.

- Per-session FIFO queues, round-robin across sessions.
- `fair_dispatch_max_concurrent` bounds simultaneous `Transcribe` RPCs across *all*
  sessions. Set it to the engine's real parallelism — `1` for mlx-whisper or
  faster-whisper. Higher values only add queueing latency.
- `fair_dispatch_max_partial_queue` caps queued partials per session; the oldest is
  dropped when the cap is hit.
- Queuing a final cancels that session's stale partials — they are no longer useful.

Invariants that must survive any change here:

1. **In-flight gate.** `slot.inFlight == true` means exactly one dispatch goroutine is
   running for that session. `releaseInFlight` is called explicitly (never deferred) and
   calls `notify()` *last*, after the mutex is released — waking the dispatcher while the
   session is still marked in-flight skips it and no further notification arrives
   (liveness deadlock).
2. **In-flight with an empty queue.** When `popNext` takes a session's last task, the slot
   stays in `d.sessions` with `inFlight=true`. Deleting it would let a concurrent
   `Enqueue` create a fresh slot with `inFlight=false` and issue a second simultaneous RPC
   for the same session.
3. **Exactly one result per task.** Every `resultCh` receives exactly one `BatchResult` —
   from dispatch, stale-partial cancellation, queue trimming, or the shutdown drain.
   Result channels are never closed; callers always block on receive.
4. **Stale partials before the final.** Cancelled partials are written to before the final
   is appended, so `runResultCollector` sees them first.
5. **Close ordering.** `batchDecodeEngine.Close()` calls `CancelSession` before closing
   `decodeQueueCh`, so no task is enqueued after cancellation.
6. **`collectorDone` before `close(resultsCh)`.** This is the only thing preventing a
   "send on closed channel" panic in the result path.

---

## Streaming decode engine

`stream/streaming_engine.go`. Holds one `TranscribeStream` for the session lifetime.

- `FeedFrame` calls `SendAudio` synchronously — there is no separate send goroutine, so
  ordering is trivially preserved and backpressure propagates to `vadSendLoop`.
- `recvLoop` reads `StreamResponse`s, feeds hypotheses through the `ResultAssembler`, and
  **owns closing `resultsCh`**.
- `OnUtteranceEnd` sends `StreamControl{KIND_FINALIZE_UTTERANCE}` (only when `src=core`)
  and records `finalizeAt`. If `is_final` does not arrive within
  `streaming_finalize_timeout_sec`, the session ends with **ERR3007**.
- `engineWatchdog` runs only for `src=engine`: `engine_response_timeout_sec` guards against
  an engine that stops responding, and `max_utterance_sec` force-sends a finalize when the
  engine has produced no `is_final` for too long.
- Terminal errors are stored in `terminalErr` (`atomic.Pointer[error]`) *before* cancelling,
  and read by the forwarder after `resultsCh` closes, so the real cause reaches the client
  instead of a generic cancellation.
- `Close()` drains `recvLoop` before cancelling; the cancel func also calls
  `client.CancelStream()` so a blocked `Recv` is unblocked.

---

## ResultAssembler

`stream/result_assembler.go` converts successive decodes into `committed_text` (stable
prefix) and `unstable_text` (may still change).

- On each partial, the longest common prefix of the previous and current text advances the
  commit boundary, snapped to a word boundary (space) or, for scripts without spaces, to a
  punctuation boundary from `.,?!。、，！？…`.
- Comparison is at **rune** granularity, never bytes.
- Once `committed_so_far` exceeds `lcpWindowRunes` (200), only its tail is compared, so
  long sessions do not pay an O(n) rune conversion per partial.
- `committed_text` is monotonically non-decreasing within an utterance.
- On `is_final` the full utterance text becomes committed, `unstable_text` is emptied, and
  all state resets for the next utterance.

The monotonicity trade-off is deliberate — see
[../decisions/0006-monotonic-committed-text.md](../decisions/0006-monotonic-committed-text.md).

---

## Concurrency and capacity

| Limit | Config key | Enforced by |
|-------|-----------|-------------|
| Concurrent sessions | `server.max_sessions` | `session.Manager` |
| Sessions per IP / API key | `rate_limit.max_sessions_per_ip`, `..._per_api_key` | `session.Manager` |
| Session creation rate | `rate_limit.create_session_rps` / `_burst` | `ratelimit.Limiter` |
| Concurrent streaming sessions | `decode.max_streaming_sessions` | `DecodeScheduler.AcquireStreamingSlot` (ERR2008 on ctx cancel) |
| Concurrent batch `Transcribe` RPCs | `stream.fair_dispatch_max_concurrent` | `FairDecodeDispatcher` |
| Concurrent resampling conversions | — (`runtime.NumCPU()`) | `codec.resamplerSem` |
| Plugin-side concurrency | `server.max_concurrent_sessions` in the plugin YAML | the plugin's own semaphore |

Streaming and batch use **separate** semaphores. A single shared pool would let long-lived
streaming sessions starve batch throughput.

Config is read through `atomic.Pointer[config.Config]`, so a SIGHUP reload is lock-free for
readers. An engine snapshots `config.StreamConfig` at `Start`; a later reload does not
affect an already-running engine.

---

## Error handling

Every failure is an `*errors.STTError` carrying an `ERR####` code
(see [../api/error-codes.md](../api/error-codes.md)), converted to a gRPC status with
`ToGRPC()` or to a wire frame with `ToErrorSpec()`. Anything unrecognised falls back to
**ERR3002**. `retryable` is set for `Unavailable` and `ResourceExhausted` codes.

Plugin-reported `PluginErrorCode` values are translated to `ERR####` at the Core boundary —
plugins never emit `ERR####` themselves.

Endpoint failures are absorbed by a per-endpoint circuit breaker
(`plugin/endpoint.go`): `CLOSED → OPEN` after `failure_threshold` consecutive failures,
`OPEN → HALF_OPEN` after `half_open_timeout_sec`, and a background health probe
(`PluginRouter.StartHealthProbe`) closes or re-opens it. `probeAll` also re-fetches
capabilities from endpoints still reporting `STREAMING_MODE_UNSPECIFIED`, so a plugin that
was still loading when Core started is picked up without a restart.

---

## Graceful shutdown

`runtime.Application.gracefulShutdown`, on SIGTERM/SIGINT:

1. Set `draining` so `/health` reports `draining`; `Manager.StopAccepting()`;
   `grpc.GracefulStop()`.
2. `Manager.DrainAll(ctx)` with a `server.shutdown_drain_sec` deadline.
3. `grpc.Stop()` force-close, then `StreamProcessor.Close()` to shut the shared dispatcher
   down after all sessions have drained, then flush OpenTelemetry spans.
