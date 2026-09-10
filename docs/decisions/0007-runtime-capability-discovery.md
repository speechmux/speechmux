# 0007 — Engine identity comes from `GetCapabilities`, not from `plugins.yaml`

Status: Accepted

## Context

Core needs to know which engine is behind an endpoint: to label metrics and traces, to show
it in `/admin/plugins` and in the web client, and — critically — to decide whether the
session takes the batch or the streaming path.

The cheap option is to declare it in `plugins.yaml` next to the socket. That makes
configuration the source of truth for something configuration cannot actually know.

## Decision

`plugins.yaml` declares only `id`, `socket` **xor** `address`, and `priority`.
`engine_name`, `model_size`, `device`, `streaming_mode` and `endpointing_capability` come
from `InferencePlugin.GetCapabilities`, fetched by `PluginRouter.Add` at endpoint
registration and cached on the `InferenceClient` behind an `RWMutex`.

A failed fetch is **non-fatal**: the endpoint registers with empty fields, a background
goroutine retries, and the periodic health probe re-fetches from any endpoint still
reporting `STREAMING_MODE_UNSPECIFIED`.

Session routing then reads capabilities from the client the router actually pinned —
`PinByHint()` is a single call that both routes and pins, rather than a `Route()` followed
by a separate `PinByHint()`.

## Rationale

- Configuration cannot drift from reality. Swapping the model behind an endpoint needs no
  Core config change, and `/admin/plugins` always reports what is running.
- Capability-driven dispatch is only sound if the capabilities are the endpoint's own.
  Declaring `streaming_mode` in YAML and getting it wrong would send a unary `Transcribe`
  to a streaming-only engine.
- Fetching at registration rather than per session keeps the session hot path free of an
  extra round trip.
- Making the fetch non-fatal matters because plugins load models slowly. Core routinely
  starts before a plugin is ready; a fatal fetch would require a strict start order.
- Routing and reading capabilities in one call removes a real race: in a mixed pool,
  `Route()` and a later `PinByHint()` could select different endpoints, and the session
  would then be configured for the wrong engine.

## Consequences

- An engine that misreports its capabilities breaks routing in ways configuration cannot
  override. `streaming_mode` and `endpointing_capability` are part of the plugin contract.
- Both enums default to `UNSPECIFIED = 0`, read as `BATCH_ONLY` and `NONE`, so a plugin
  built before they existed still works.
- `RouteBatch()` filters strictly to `BATCH_ONLY`, so an endpoint whose capabilities have
  not been fetched yet is excluded from batch dispatch until the probe fills them in.
- `engine_hint` from a client must match the endpoint **`id`** (`whisper-mlx`), not the
  discovered engine name (`mlx_whisper`) — the id is the only thing configuration owns.
