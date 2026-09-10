# Skill: add-error-code

Add a new `ERR####` code to the Core error registry.

## When to use this

A failure needs to be distinguishable by clients — they will retry it, re-authenticate,
surface a specific message, or give up. If a client would treat it identically to an
existing code, reuse that code instead.

**Do not** use this to change an existing code. Codes are permanent: their meaning, gRPC
status and HTTP status never change, and a retired number is never reused. See
[ADR 0008](../../../docs/decisions/0008-error-code-registry.md).

## Prerequisites

- Read [docs/api/error-codes.md](../../../docs/api/error-codes.md) end to end. Several codes
  are registered but unused; one of them may already describe your case.
- Confirm this is a **Core** error. Plugin errors are `common.v1.PluginErrorCode` values
  translated at the boundary — a plugin must never emit `ERR####`.

## Pick the range

| Range | For |
|-------|-----|
| `ERR1xxx` | Client's fault: bad request, validation, auth, capacity refused at admission |
| `ERR2xxx` | Decode pipeline: timeouts, plugin unavailable, scheduler limits |
| `ERR3xxx` | Server's fault: internal failures, transport/plugin stream breakage |
| `ERR4xxx` | Admin / HTTP surfaces |

Take the **next unused number** in that range. Never fill a gap — a gap means a number was
spent and possibly shipped.

---

## Steps

### 1. Add the constant

`core/internal/errors/codes.go`, in the right block:

```go
const (
    ...
    ErrMyNewCondition ErrorCode = "ERR2009"
)
```

### 2. Add the `errorSpecs` entry

```go
ErrMyNewCondition: {ErrMyNewCondition, codes.ResourceExhausted, http.StatusServiceUnavailable,
    "short, stable, client-facing message"},
```

Choose the gRPC code carefully — **`retryable` is derived from it**, not stored. It is
`true` exactly when the code is `Unavailable` or `ResourceExhausted`. Picking `Internal`
for a transient condition tells every client not to retry.

| Situation | gRPC | HTTP |
|-----------|------|------|
| Bad input | `InvalidArgument` | 400 |
| Missing/failed auth | `Unauthenticated` | 401 |
| Authenticated but not permitted | `PermissionDenied` | 403 |
| Not found / expired | `NotFound` | 404 |
| Duplicate | `AlreadyExists` | 409 |
| Client rate limited | `ResourceExhausted` | 429 |
| Server at capacity (retryable) | `ResourceExhausted` | 503 |
| Dependency down (retryable) | `Unavailable` | 503 |
| Timeout | `DeadlineExceeded` | 504 |
| Server bug | `Internal` | 500 |
| Not built yet | `Unimplemented` | 501 |

The message is part of the contract. Keep it short, stable and free of internal detail —
paths, socket names and stack fragments belong in the log, not the wire. Pass those as the
`detail` argument to `New()`, which appears in the gRPC status message but never replaces
the registered message in `ToErrorSpec()`.

### 3. Add the contract-test entry

`core/internal/errors/contract_test.go`, in `errorCodeContract`:

```go
{sttErrors.ErrMyNewCondition, codes.ResourceExhausted, http.StatusServiceUnavailable},
```

The completeness test fails if a registered code has no contract entry. This is the
mechanism that makes "permanent" mean something.

### 4. Use it

```go
return sttErrors.New(sttErrors.ErrMyNewCondition, "detail for the log").ToGRPC()
```

For an error that must travel out of a goroutine and be classified later, return the
`*STTError` and let the caller do `errors.As` — `ProcessSession` already does this. Wrap
with `%w`, never `%v`, or `ToErrorSpec` will fall back to **ERR3002**.

### 5. Check the transports carry it

- gRPC: `ToGRPC()` in the return path, and a `StreamError` frame before the stream closes.
- WebSocket: `ToErrorSpec()` → `{"type":"error","code":...}`.
- HTTP: `{"code":"ERR####","message":"…"}` with the mapped status.

If your error arises inside the pipeline, verify it reaches the client rather than being
swallowed as a generic cancellation. The streaming engine stores terminal errors in
`terminalErr` *before* cancelling for exactly this reason.

### 6. Document it

Add a row to the right table in
[docs/api/error-codes.md](../../../docs/api/error-codes.md) with the code, gRPC status,
HTTP status and message. If a client is expected to react in a particular way (replay
audio, back off, re-authenticate), say so there.

---

## Files you will touch

| File | Always |
|------|--------|
| `core/internal/errors/codes.go` | yes — constant + `errorSpecs` |
| `core/internal/errors/contract_test.go` | yes |
| The Go file that raises it | yes |
| `docs/api/error-codes.md` | yes |
| A test asserting the code reaches the client | yes |

---

## Verification

```bash
cd core && go test ./internal/errors/     # contract + completeness
cd core && go test ./...
```

Then trigger the condition and confirm the code on the wire:

```bash
# gRPC
.venv/bin/speechmux file bad.wav 2>&1 | grep ERR

# WebSocket
websocat ws://localhost:8091/ws/stream    # then provoke the condition

# HTTP
curl -i localhost:8090/admin/plugins
```

---

## Common mistakes

- **Reusing a number.** Old clients silently misinterpret it. Always take the next unused
  number in the range.
- **Filling a gap.** A gap is a spent number.
- **Choosing `Internal` for a retryable condition.** `retryable` is derived from the gRPC
  code; the client will not retry.
- **Forgetting the contract-test entry.** The completeness test fails — but if you also
  skip running the tests, an unpinned mapping ships.
- **Putting internal detail in the registered message.** It goes to every client forever.
  Use the `detail` argument.
- **Wrapping with `%v`.** `errors.As` cannot find the `*STTError` and the client sees
  ERR3002.
- **Adding a code a plugin will emit.** Plugins report `PluginErrorCode`; extend that enum
  (a proto change) and the translation table instead.
- **Adding a code for something an existing one covers.** Check the unused ERR4xxx codes
  first.

---

## Done when

- [ ] The constant, the `errorSpecs` entry and the `contract_test.go` entry all exist and
      agree.
- [ ] `go test ./internal/errors/` passes.
- [ ] The code is raised at a real call site and reaches the client on the relevant
      transport, with a test proving it.
- [ ] A row is added to [docs/api/error-codes.md](../../../docs/api/error-codes.md).
- [ ] No existing row was modified.
