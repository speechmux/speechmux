# Observability

Core exposes three signals: Prometheus metrics, structured logs, and OpenTelemetry traces,
plus an aggregating `/health` endpoint. Source: `core/internal/metrics/`,
`core/internal/tracing/`, `core/internal/health/`, `core/internal/runtime/health.go`.

---

## Metrics

Served on the HTTP port: `/metrics` (Prometheus text) and `/metrics.json`. The registry is
private (`prometheus.NewRegistry()`), with the Go runtime and process collectors added.

Core code never imports Prometheus directly. `session` and `stream` take a
`metrics.MetricsObserver` interface, so tests inject `metrics.NopMetrics{}`.

| Metric | Type | Labels |
|--------|------|--------|
| `speechmux_active_sessions` | gauge | — |
| `speechmux_sessions_total` | counter | — |
| `speechmux_decode_latency_seconds` | histogram | `type` (`final`/`partial`), `engine` |
| `speechmux_decode_requests_total` | counter | `type`, `status` (`ok`/`error`), `engine` |
| `speechmux_vad_triggers_total` | counter | — |
| `speechmux_vad_watermark_lag_total` | counter | — |
| `speechmux_streaming_sessions_active` | gauge | `engine_name` |
| `speechmux_streaming_partial_latency_seconds` | histogram | `engine_name` |
| `speechmux_streaming_finalize_latency_seconds` | histogram | `engine_name` |
| `speechmux_streaming_session_terminations_total` | counter | `engine_name`, `reason` |
| `speechmux_engine_response_timeout_total` | counter | `engine_name` |
| `speechmux_fair_dispatch_queue_depth` | gauge | `session_id` |
| `speechmux_fair_dispatch_partial_cancelled_total` | counter | `reason` (`stale_final`/`queue_full`) |
| `speechmux_fair_dispatch_wait_sec` | histogram | `type` |

Notes:

- The `engine` / `engine_name` label is the runtime `engine_name` from `GetCapabilities`,
  not a configured string — so a dashboard slices by what actually served the request.
- `streaming_session_terminations_total.reason` is a **closed enum**. Adding a new
  termination path means adding a named reason, never an `"other"` bucket.
- All streaming latency histograms reuse the shared `decodeLatencyBuckets` so partial,
  finalize and decode latency are directly comparable.
- `fair_dispatch_queue_depth` is labelled by `session_id` and is therefore high-cardinality.
  It is intended for debugging a specific host, not for long-term storage.
- There is no per-partial span; partials are a metric, utterances are a span.

---

## Tracing

`tracing.Init(ctx, serviceName, endpoint, sampleRate)` installs an OTLP-gRPC exporter with
a `TraceIDRatioBased` sampler. **When `otel.endpoint` is empty a no-op provider is
installed**, so every `otel.Tracer(...)` call becomes zero-cost and tracing can stay
compiled in with no configuration. Spans are flushed with a 5 s deadline at shutdown.

| Span | Emitted by | Attributes |
|------|-----------|------------|
| `session.pipeline` | `StreamProcessor.ProcessSession` | `session.id`, `session.language`, `session.task` |
| `stt.decode` | `FairDecodeDispatcher` | covers the whole `Enqueue`→result path, including the queue wait |
| `stt.stream_session` | `streamingDecodeEngine.Start` | `session.id`, `engine.name`, `endpointing.source` |
| per-utterance child spans | `streamingDecodeEngine.recvLoop` | one per utterance |

`stt.decode` deliberately uses the caller's context for the span while the RPC runs on a
decoupled context, so a cancelled session still produces a complete span.

Configuration: `otel.endpoint`, `otel.service_name`, `otel.sample_rate` in `core.yaml`.

---

## Logging

`log/slog` throughout Core, configured from `logging.level` and `logging.format`:

| `logging.format` | Handler | Use |
|------------------|---------|-----|
| `json` | `slog.NewJSONHandler` | log collectors (default in Docker) |
| `text` | `slog.NewTextHandler` | plain key=value |
| `color` | `lmittmann/tint` | interactive terminals (default in `core/config/core.yaml`) |

Startup bootstraps at INFO with the JSON handler so configuration errors are visible, then
swaps the handler and level once `core.yaml` is parsed. `AddSource: true` is always on.

Volume control that matters in production:

- Per-frame EPD logging is DEBUG only. Liveness during silence comes from a heartbeat line
  every `epd_heartbeat_interval_sec` (`0` disables it).
- VAD speech/silence transitions are streak-debounced rather than logged per raw
  transition.
- Watermark-lag warnings in REALTIME mode are rate-limited to one per 30 s.
- Plugins honour `server.log_transcription_text`. Set it to `false` to log a character
  count instead of the transcript.

Under `ctl`, each supervised process writes to `/tmp/speechmux/<name>.log` (`make logs`).

---

## Health

`GET /health` returns `health.Status`:

```json
{
  "status": "ok",
  "plugins": [
    {"id": "vad-0", "plugin_state": "READY", "circuit_breaker": "closed"},
    {"id": "sherpa-onnx", "plugin_state": "READY", "circuit_breaker": "closed"}
  ]
}
```

`status` is one of `ok`, `degraded`, `draining`, `error`:

| Value | Meaning |
|-------|---------|
| `ok` | every probed plugin is `READY` |
| `degraded` | at least one plugin is `READY` and at least one is not |
| `error` | no plugin is `READY` |
| `draining` | graceful shutdown in progress (set before the plugin probes) |

Each `Check` probes plugins live with a 2 s deadline. Inference probers are read from
`PluginRouter` on **every** call, so endpoints added through the Admin API appear without a
restart. The endpoint is suitable as both a liveness and a readiness probe.

Separately, `PluginRouter.StartHealthProbe` runs on `inference.health_check_interval_sec`
with a `health_probe_timeout_sec` deadline per probe. It drives circuit-breaker recovery
and re-fetches capabilities from endpoints still reporting `STREAMING_MODE_UNSPECIFIED`.

---

## Load testing

`core/tools/loadtest` is a client-side driver that reports latency percentiles, complementing
the server-side histograms. Build it with `cd core && make loadtest`. Point it at Core
running the dummy VAD and dummy STT engines (`plugin-vad/config/vad-dummy.yaml`,
`plugin-stt/config/inference-dummy.yaml`, `core/config/plugins-dummy.yaml`), which simulate
configurable latency with no model weights.

The `make loadtest` target's help text still references a `run-dummy` target that the
workspace `Makefile` no longer has; start the dummy plugins manually. See
[../plans/roadmap.md](../plans/roadmap.md).
