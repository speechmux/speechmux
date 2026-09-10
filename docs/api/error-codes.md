# Error codes

Every failure that reaches a client carries an `ERR####` code. Codes are **permanently
assigned**: a code's meaning, gRPC status and HTTP status never change, and a retired
number is never reused. See
[ADR 0008](../decisions/0008-error-code-registry.md) for why.

Registry: `core/internal/errors/codes.go`.
Contract test: `core/internal/errors/contract_test.go` — it pins the gRPC and HTTP status
of every code, so an accidental change fails the build.

---

## Ranges

| Range | Category |
|-------|----------|
| `ERR1xxx` | Session / request validation, authentication |
| `ERR2xxx` | Decode pipeline |
| `ERR3xxx` | Internal server errors |
| `ERR4xxx` | Admin / HTTP |

## ERR1xxx — session and request validation

| Code | gRPC | HTTP | Message |
|------|------|------|---------|
| ERR1001 | InvalidArgument | 400 | `session_id` is required |
| ERR1002 | AlreadyExists | 409 | `session_id` already exists |
| ERR1003 | InvalidArgument | 400 | VAD config invalid |
| ERR1004 | Unauthenticated | 401 | `session_config` not sent |
| ERR1005 | PermissionDenied | 403 | session token invalid |
| ERR1006 | DeadlineExceeded | 504 | session timed out |
| ERR1007 | InvalidArgument | 400 | audio chunk too large |
| ERR1008 | ResourceExhausted | 503 | VAD capacity full |
| ERR1009 | Unauthenticated | 401 | API key required |
| ERR1010 | InvalidArgument | 400 | invalid decode options |
| ERR1011 | ResourceExhausted | 503 | max sessions exceeded |
| ERR1012 | ResourceExhausted | 429 | create-session rate limit |
| ERR1013 | Unavailable | 503 | server is shutting down |
| ERR1014 | Unauthenticated | 401 | authentication failed |
| ERR1015 | InvalidArgument | 400 | unsupported audio encoding |
| ERR1016 | InvalidArgument | 400 | first message must be `session_config` |
| ERR1017 | InvalidArgument | 400 | unsupported language code |
| ERR1018 | NotFound | 404 | session not found or expired |
| ERR1019 | PermissionDenied | 403 | resume token invalid or session already active |
| ERR1020 | InvalidArgument | 400 | engine does not support requested endpointing mode |
| ERR1021 | Unimplemented | 501 | hybrid endpointing is not supported in this release |

## ERR2xxx — decode pipeline

| Code | gRPC | HTTP | Message |
|------|------|------|---------|
| ERR2001 | DeadlineExceeded | 504 | decode timed out |
| ERR2002 | Internal | 500 | decode task failed |
| ERR2003 | ResourceExhausted | 429 | stream rate limit exceeded |
| ERR2004 | ResourceExhausted | 429 | stream audio budget exceeded |
| ERR2005 | Unavailable | 503 | no healthy inference plugin available |
| ERR2006 | Internal | 500 | result assembly failed |
| ERR2007 | DeadlineExceeded | 504 | partial decode timed out |
| ERR2008 | ResourceExhausted | 503 | global pending decode limit exceeded |

## ERR3xxx — internal

| Code | gRPC | HTTP | Message |
|------|------|------|---------|
| ERR3001 | Unknown | 500 | unexpected error creating session |
| ERR3002 | Unknown | 500 | unexpected error in stream processing (fallback for unclassified errors) |
| ERR3003 | Internal | 500 | codec conversion failed |
| ERR3004 | Internal | 500 | VAD stream connect failed (also: VAD frame timeout, watermark lag) |
| ERR3005 | Internal | 500 | audio ring buffer overflow |
| ERR3006 | Unavailable | 503 | streaming inference endpoint lost mid-session |
| ERR3007 | DeadlineExceeded | 504 | streaming engine response timeout |

## ERR4xxx — admin / HTTP

| Code | gRPC | HTTP | Message |
|------|------|------|---------|
| ERR4001 | Unimplemented | 501 | admin API disabled |
| ERR4002 | AlreadyExists | 409 | model already loaded |
| ERR4003 | FailedPrecondition | 400 | model unload failed |
| ERR4004 | Unauthenticated | 401 | admin token invalid |
| ERR4005 | PermissionDenied | 403 | model path forbidden |
| ERR4006 | Unauthenticated | 401 | observability token invalid |
| ERR4007 | ResourceExhausted | 429 | HTTP rate limit exceeded |
| ERR4008 | PermissionDenied | 403 | client IP blocked |
| ERR4009 | InvalidArgument | 400 | unknown model profile |

Some ERR4xxx codes (model load/unload, observability token, model profile) are registered
and contract-tested but have no live call site — they belong to admin surfaces that are not
implemented. Leave them registered; the numbers are spent either way.

`ERR5001` is **not** in the registry. It is a deliberate opaque literal returned by
`POST /admin/reload` on failure, so config-file paths and parse details are not leaked to
the caller.

---

## Plugin errors

Plugins report `common.v1.PluginErrorCode`; Core translates at the boundary. Plugins must
never emit `ERR####` themselves.

| Plugin error | Core code |
|--------------|-----------|
| `PLUGIN_ERROR_MODEL_LOADING` | ERR2005 |
| `PLUGIN_ERROR_MODEL_OOM` | ERR2005 |
| `PLUGIN_ERROR_INVALID_AUDIO` | ERR3003 |
| `PLUGIN_ERROR_INFERENCE_FAILED` | ERR2002 |
| `PLUGIN_ERROR_SESSION_NOT_FOUND` | ERR3004 |
| `PLUGIN_ERROR_CAPACITY_FULL` | ERR2008 |

---

## On the wire

**gRPC** — `STTError.ToGRPC()` produces a status whose message is
`"ERR#### <registered message>[: <detail>]"`. A `StreamError` frame is also sent before the
stream closes.

**WebSocket** — `{"type":"error","code":"ERR####","message":"…"}`.

**HTTP** — `{"code":"ERR####","message":"…"}` with the mapped status.

`retryable` is derived, not stored: it is `true` exactly when the gRPC code is `Unavailable`
or `ResourceExhausted`. On ERR3004 or ERR3005 a client should open a new stream and replay
the last ~2 s of audio so the unstable segment is not lost.

Any error that is not an `*STTError` is reported as **ERR3002**, and only the registered
message is sent — internal detail stays in the server log.

---

## Adding a code

Use the [`add-error-code`](../../.codex/skills/add-error-code/SKILL.md) skill. In short:
take the next free number in the right range, add the constant, add the `errorSpecs` entry,
add the `contract_test.go` entry, add a row to this file, and never touch an existing row.
