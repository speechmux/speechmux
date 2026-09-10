# 0011 — Cross-session fair queueing in front of batch inference

Status: Accepted

## Context

Batch engines like mlx-whisper and faster-whisper process one request at a time internally.
When each session dispatched its own `Transcribe` calls independently, a session producing
frequent partials monopolised the engine and other sessions' finals waited behind them.
There was also no way to cancel a partial that a later final had already made irrelevant,
so stale work consumed the engine while the user waited for the result that mattered.

The in-flight gate was implicit — a consequence of how the per-session goroutines happened
to be sequenced — which made it easy to break.

## Decision

Introduce `FairDecodeDispatcher`: one instance shared by all batch sessions, created inside
`NewStreamProcessor` and shut down by the application's graceful shutdown.

- Per-session FIFO queues, dispatched round-robin across sessions.
- `fair_dispatch_max_concurrent` bounds simultaneous `Transcribe` RPCs across **all**
  sessions (default `1`).
- `fair_dispatch_max_partial_queue` caps queued partials per session; the oldest is dropped.
- Enqueuing a final cancels that session's stale partials.
- An explicit `inFlight` flag per session, not an emergent property of goroutine layout.

Six invariants are documented in
[../architecture/core-pipeline.md](../architecture/core-pipeline.md#fairdecodedispatcher)
and must survive any change: the in-flight gate and its `notify()` ordering; keeping the
slot when its queue empties; exactly one result per task; stale partials delivered before
the final; `CancelSession` before closing the queue; `collectorDone` before closing
`resultsCh`.

## Rationale

- Fairness has to be global, because the contended resource is global. A per-session
  scheduler cannot see the contention.
- `max_concurrent = 1` matches what single-process GPU engines actually do. Dispatching
  more only moves the queue from Core into the engine, where it cannot be reordered or
  cancelled.
- Dropping stale partials is free latency for the final result, and the final is the only
  output the user keeps.
- Making the gate explicit turned an invariant that was previously "true by accident" into
  one that can be tested (`fair_dispatch_test.go`).

## Consequences

- `fair_dispatch_max_concurrent` becomes the primary batch throughput knob and must be set
  to the engine's real parallelism. Too high adds queuing latency; too low idles the engine.
- Results complete out of order across sessions, so `batchDecodeEngine` keeps a FIFO of
  submitted tasks and drains it in submission order — `ResultAssembler` requires that.
- Ordering rules inside the dispatcher are subtle and easy to break in a way that
  deadlocks rather than fails. Read the invariants before touching it.
- `DecodeScheduler` was reduced to the streaming-slot semaphore; its `Submit()` path is
  gone. `decode.max_pending` no longer exists and any surviving mention is stale config.
- The streaming path does not use the dispatcher at all — it has its own semaphore
  ([ADR 0013](0013-separate-streaming-and-batch-pools.md)).
