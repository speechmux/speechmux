# 0002 — One bidirectional RPC carries the whole session

Status: Accepted

## Context

A streaming STT session needs three things from the client: configuration, a continuous
audio feed, and an end-of-audio signal. The obvious design is a `CreateSession` unary RPC
that returns a session ID, followed by a streaming RPC that references it.

## Decision

`client.v1.STTService` exposes exactly one RPC:

```protobuf
rpc StreamingRecognize(stream StreamingRecognizeRequest)
    returns (stream StreamingRecognizeResponse);
```

The first request message **must** carry `session_config`; subsequent messages are `audio`
or `signal`. The first response is `session_created`; subsequent responses are `result` or
a terminal `error`. This mirrors the Google Speech-to-Text v2 pattern.

## Rationale

- Session lifetime becomes identical to stream lifetime. There is no window in which a
  session exists without a stream, so there are no orphaned sessions to reap and no
  session-ID handshake to secure.
- One round trip fewer before audio can start flowing.
- Backpressure works naturally: not reading from the stream fills the HTTP/2 flow-control
  window and throttles the sender. A separate unary create would have no such coupling.
- Errors have one delivery path — a `StreamError` frame followed by stream close.

## Consequences

- A malformed first message is a distinct failure (**ERR1016**) that every transport must
  handle.
- Reconnecting means opening a new stream, so a dropped connection loses in-flight audio.
  That gap is what the WebSocket park-and-resume mechanism
  (`server.resumable_session_timeout_sec`, `resume_token`) exists to close, and why the
  web client keeps `committed_text` locally and replays on reconnect.
- The WebSocket transport must reproduce the same lifecycle in JSON
  (`start`/`session`/`result`/`error`/`done`), including the ordering guarantee that a
  pipeline error is visible before the result channel closes.
