# 0004 — One `StreamVAD` stream per session, not a multiplexed one

Status: Accepted

## Context

The VAD plugin must process frames for many concurrent sessions. Two shapes are possible:
one long-lived stream carrying frames tagged with a session ID and a server-side session
dictionary, or one independent stream per session.

## Decision

Core opens one `StreamVAD` bidi stream per session. The first message is
`SessionStart { session_id, threshold, sample_rate }`, then PCM frames, then `SessionEnd`
and a half-close. Per-session model state lives in the object returned by
`VADEngine.create_session_state(threshold)` and is passed back on every `process_frame`
call, so one engine instance serves every stream.

Core assigns a monotonic `sequence_number` to each frame and the plugin **echoes it back
unchanged**.

## Rationale

- gRPC's `ThreadPoolExecutor` gives each stream a dedicated worker, so session isolation is
  free — one slow or crashing session cannot corrupt another's state.
- No shared mutable dictionary in the plugin means no locking and no cleanup path for
  sessions whose stream died without a `SessionEnd`. Stream close *is* the cleanup.
- The echoed sequence number is what lets Core map a VAD verdict back to a ring-buffer
  entry, extract the exact speech segment, and advance the trim watermark
  ([ADR 0005](0005-watermark-ring-buffer.md)). A multiplexed stream would need the same
  tag anyway.
- Per-session state also lets each session use its own threshold.

## Consequences

- Thread-pool sizing matters. Workers are `max_concurrent_sessions + 4`: with
  `workers == sessions`, a `HealthCheck` RPC can starve behind occupied VAD streams and
  Core would conclude the plugin is dead.
- The plugin is bounded by threads, so `max_concurrent_sessions` must be tuned to the host,
  and over-capacity streams are rejected with `PLUGIN_ERROR_CAPACITY_FULL` → **ERR2008**.
- Losing or reordering sequence numbers silently breaks utterance extraction, so the echo
  is a hard requirement on any VAD plugin implementation.
- `VADClient.Close()` half-closes the send side and must **not** cancel the stream context,
  or the final in-flight VAD results — and with them the last utterance — are lost.
