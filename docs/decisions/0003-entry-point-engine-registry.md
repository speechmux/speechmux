# 0003 — Engines register through Python entry points, behind a host framework

Status: Accepted

## Context

Every speech model has its own runtime with heavy and mutually incompatible dependencies
(`torch`, `mlx`, `ctranslate2`, `onnxruntime`). All of them need the same surrounding
machinery: a gRPC server, config loading, a concurrency semaphore, `HealthCheck`,
`GetCapabilities`, graceful shutdown. Writing that per engine would triplicate subtle
behaviour; putting all engines in one package would force every user to install every
runtime.

## Decision

Split each plugin kind into two layers.

**Host framework** (`plugin-vad`, `plugin-stt`) owns the entry point
(`python -m speechmux_plugin_stt.main --config <yaml>`), the servicer, YAML loading, the
semaphore, thread-pool sizing, `HealthCheck` and `GetCapabilities`, and defines the engine
`Protocol`s.

**Engine adapter** (`plugin-stt-<impl>`) is a package implementing one Protocol and
declaring itself in `pyproject.toml`:

```toml
[project.entry-points."speechmux.stt_engine"]
sherpa_onnx_zipformer = "speechmux_plugin_stt_sherpa_onnx.engine:SherpaOnnxEngine"
```

The registry resolves `server.engine: <name>` against the entry-point group at startup and
constructs the class through `from_config(cls, config)` when present. Protocols are
`@runtime_checkable`, and the identity fields (`engine_name`, `device`, `streaming_mode`,
…) are **class attributes, not methods**, so the servicer can read them directly.

## Rationale

- Installing an engine is `pip install` — nothing in the framework or in Core changes. No
  registry file, no import list, no plugin manifest.
- Dependencies stay isolated per package.
- The servicer distinguishes batch from streaming engines with `isinstance(engine,
  StreamingInferenceEngine)` at construction, so one framework serves both `Transcribe`
  and `TranscribeStream` without configuration.
- Class attributes make `GetCapabilities` a straight field read, which is why Core can
  discover engine identity at runtime ([ADR 0007](0007-runtime-capability-discovery.md)).

## Consequences

- Engines must be *installed*, not merely present on disk. In the workspace that is
  `uv pip install -e plugin-stt-<impl>`; a missing install produces a `KeyError` listing
  the engines that are registered.
- The Protocol is a real contract. Adding a required attribute or method to
  `InferenceEngine` / `VADEngine` / `StreamingInferenceEngine` breaks every adapter and
  must be done deliberately, with defaults where possible.
- Because engines are separate distributions, `from_config` is the only sanctioned way
  YAML reaches them — an engine must not read a config file itself.
