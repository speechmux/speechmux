# 0008 — A permanent `ERR####` registry, translated at the plugin boundary

Status: Accepted

## Context

Errors reach clients over three transports (gRPC status, WebSocket JSON, HTTP JSON) and
originate in three places (Core, plugins, the transport layer itself). Clients need to
branch on failures — retry, re-authenticate, give up — which raw gRPC codes are too coarse
for: `Internal` covers both a codec failure and a dead VAD stream.

## Decision

A single registry in `core/internal/errors/codes.go` maps every `ErrorCode` to a gRPC code,
an HTTP status and a fixed message. Codes are grouped `ERR1xxx` (validation/auth),
`ERR2xxx` (decode pipeline), `ERR3xxx` (internal), `ERR4xxx` (admin/HTTP).

**Codes are permanent.** Once assigned, a code's meaning and its status mapping never
change, and a retired number is never reused. `contract_test.go` pins every mapping so an
accidental change fails the build.

Plugins never emit `ERR####`. They report a `common.v1.PluginErrorCode`, and Core
translates it at the boundary (`PLUGIN_ERROR_MODEL_OOM` → ERR2005, and so on).

`retryable` is derived rather than stored: it is `true` exactly when the gRPC code is
`Unavailable` or `ResourceExhausted`. Anything that is not an `*STTError` is reported as
**ERR3002** with only the registered message, so internals stay in the server log.

## Rationale

- Client branching needs a stable identifier, and stability only means something if it is
  enforced — hence the contract test.
- Deriving `retryable` from the status guarantees the two can never disagree.
- Translating plugin errors at the boundary keeps the numbering space owned by one repo.
  A plugin author cannot accidentally collide with a Core code, and adding an engine never
  touches the registry.
- The generic fallback means an unclassified Go error can never leak a file path, a socket
  path or a stack detail to a client.

## Consequences

- Renumbering is impossible, so gaps and unused codes are permanent. Several `ERR4xxx`
  codes (model load/unload, observability token, model profile) are registered and
  contract-tested but have no call site — the numbers are spent either way; leave them.
- Adding a code means four edits: the constant, the `errorSpecs` entry, the
  `contract_test.go` entry, and a row in [../api/error-codes.md](../api/error-codes.md).
  The completeness test fails if the contract entry is missing.
- `ERR5001` is deliberately **outside** the registry: `POST /admin/reload` returns it as an
  opaque literal so config paths and parse errors are not disclosed.
- The fixed messages are part of the contract too — changing wording changes what clients
  may be matching on.
