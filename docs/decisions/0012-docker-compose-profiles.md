# 0012 — Docker Compose with profiles for engine selection

Status: Accepted

## Context

The stack is six processes with very different runtime needs, and the STT engine is the
part that varies: sherpa-onnx on CPU/ARM, faster-whisper on CPU/CUDA, mlx-whisper only on
Apple Silicon. A deployment wants one or two of them, not all. Kubernetes was considered
and is heavier than this deployment needs.

## Decision

A single `docker-compose.yml` at the workspace root. `core`, `vad-silero` and the two
`client-web` services are always active; each STT engine is behind a Compose profile
(`sherpa`, `faster-whisper`) and started with `--profile`. The `Makefile` wraps this as
`DOCKER_PROFILE`, defaulting to both.

Inside Compose, plugins are reached over **TCP** by service name
(`vad-silero:50060`, `stt-sherpa:50061`), configured in `deploy/docker/plugins-docker.yaml`,
rather than the Unix domain sockets used natively. Configuration is mounted read-only from
`deploy/docker/*.yaml`; host port bindings, `MODELS_DIR` and secrets come from `.env`.

`core.depends_on` lists `vad-silero` but **not** the STT service.

## Rationale

- Profiles express "pick an engine" without a separate Compose file per combination, and
  match the `--profile` model `ctl` already uses natively.
- TCP is required because containers cannot share a Unix socket path without a shared
  volume, and service-name DNS is simpler and more portable than a socket mount.
- The STT service is excluded from `depends_on` because profile variants have different
  service names and `depends_on` does not resolve network aliases. Core's health-check
  interval plus the circuit breaker already handles a plugin that is not up yet, so an
  inactive profile's endpoint simply stays circuit-open.
- Only host-side ports are parameterised in `.env`; container-internal ports stay fixed so
  the mounted configs do not have to be templated.

## Rationale for the config split

`deploy/docker/*.yaml` are separate files rather than overlays on the native configs
because the endpoint form differs fundamentally (`socket` vs `address`) and model paths
differ (`/models` vs a workspace-relative path).

## Consequences

- Every `core.yaml` key must be added to `deploy/docker/core-docker.yaml` too. They drift;
  the current divergence is recorded in
  [../operations/configuration.md](../operations/configuration.md#known-config-drift).
- `NEXT_PUBLIC_API_PORT` is a build arg, not runtime env, because Next.js bakes
  `NEXT_PUBLIC_*` at build time. Changing `API_PORT` requires a rebuild.
- Health-check `start_period` values are model-load times (60 s VAD, 60 s sherpa, 90 s
  faster-whisper). Slower hardware needs them raised.
- No Kubernetes manifests or Helm chart exist. If multi-node scheduling is needed later,
  the endpoints Core exposes (`/health`, `/metrics`, `/admin/reload`) are already what such
  a manifest would use.
