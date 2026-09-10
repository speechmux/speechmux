# 0005 — Ring-buffer trimming is watermark-based, and a full buffer is backpressure

Status: Accepted

## Context

The batch decode path cannot ask the STT plugin for a transcript until it knows where the
utterance ended, which it only learns from VAD. So Core must retain audio until VAD has
judged it. A naive time-based buffer ("keep the last 20 seconds") discards audio that VAD
has not yet seen whenever the plugin falls behind — losing exactly the audio the pending
utterance needs.

Separately, the buffer must have a bound, and hitting that bound means something different
for a live microphone than for a file upload.

## Decision

`AudioRingBuffer` indexes frames by sequence number and tracks a `confirmedWatermark`, the
highest sequence number VAD has acknowledged. `Trim()` evicts an entry only when **both**
`seq <= confirmedWatermark` **and** the entry is older than `max_buffer_sec`. Unconfirmed
audio is never evicted, at any age.

`Append()` returns `false` — not an error — when the buffer is at capacity. The caller
decides what that means, based on `StreamMode`:

| Mode | Policy |
|------|--------|
| `BATCH` | Wait 5 ms and retry. The transport stops reading, the HTTP/2 window fills, the sender throttles. |
| `REALTIME` | `DropOldest()` and continue, so the microphone never stalls. |

## Rationale

- Correctness first: an utterance is only extractable if every frame between its start and
  end sequence numbers is still resident.
- Returning a boolean rather than an error keeps the policy decision at the call site,
  where the stream mode is known. An error would have forced one policy on both cases.
- Losing the oldest audio in a live session is a smaller failure than stalling the
  microphone; losing audio from a file upload is unacceptable when the sender can simply be
  slowed down. Hence the split.

## Consequences

- A VAD plugin that hangs would grow the buffer without bound, so the watermark needs its
  own watchdogs: `vad_frame_timeout_sec` (no response at all → **ERR3004**) and
  `vad_watermark_lag_threshold_sec` (responding but far behind → ERR3004 in BATCH, a
  rate-limited warning in REALTIME).
- The lag watchdog ships **disabled** (`0`): file input arrives faster than real time and
  produces large lag that is not a fault. BATCH backpressure already bounds the damage.
  Enable it only for REALTIME-only deployments.
- When VAD is not running at all (`endpointing_source: engine`) the watermark never
  advances, so the trim ticker switches to `TrimByAge(maxSec)`.
- Capacity is `max_buffer_sec × 100` entries with a floor of 200, which assumes roughly
  10 ms per entry. Changing the frame size changes the effective buffer duration — see
  [../plans/vad-frame-size-negotiation.md](../plans/vad-frame-size-negotiation.md).
