# 0013 — Streaming and batch are one `DecodeEngine` interface with separate capacity pools

Status: Accepted

## Context

Adding native streaming engines (sherpa-onnx) alongside batch engines (Whisper family)
could have been done by branching inside `StreamProcessor` on every step of the pipeline.
That would have doubled the number of paths through the most concurrency-sensitive code in
Core and put the existing, working batch pipeline at risk.

Streaming and batch sessions also consume capacity very differently: a streaming session
holds a connection for minutes, a batch decode occupies the engine for seconds.

## Decision

Define one `DecodeEngine` interface (`Start`, `FeedFrame`, `OnSpeechStart`, `OnSpeechEnd`,
`OnUtteranceEnd`, `Results`, `Close`) with two implementations, `batchDecodeEngine` and
`streamingDecodeEngine`. `StreamProcessor` selects one from the plugin's advertised
`streaming_mode` and is otherwise identical for both.

Capacity is tracked separately:

- `decode.max_streaming_sessions` — a semaphore in `DecodeScheduler`, acquired for the
  session lifetime.
- `stream.fair_dispatch_max_concurrent` — the batch RPC limit inside
  `FairDecodeDispatcher` ([ADR 0011](0011-fair-decode-dispatcher.md)).

These are two distinct channels, not one pool with a reservation scheme.

## Rationale

- An interface boundary meant the batch pipeline could be refactored behind it *first*,
  verified unchanged, and only then joined by a second implementation. The alternative
  would have interleaved new streaming logic with working batch logic in one change.
- The interface is small enough that both implementations are readable, and its lifecycle
  contract (`Start` once, then anything, then `Close` once, results channel closed by
  `Close`) is what lets `ProcessSession` treat them uniformly.
- One shared semaphore would let long-lived streaming sessions hold slots that batch
  decodes need, starving batch throughput. The two limits also have different natural
  units — sessions versus in-flight RPCs — so a single number could not express both.

## Consequences

- Every engine method must be safe to call from any goroutine; implementations serialise
  internally.
- Adding a field to `DecodeResult` requires a matching update in the result-forwarding
  goroutine in `ProcessSession`.
- Two capacity knobs must be tuned independently, and neither bounds the other. A host can
  be saturated by streaming sessions while the batch limit is untouched.
- `batchDecodeEngine` and `streamingDecodeEngine` have quite different internal goroutine
  layouts (submitter/collector/partial-timer versus recvLoop/watchdog), so a bug fix in one
  rarely transfers to the other.
