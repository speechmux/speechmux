# Deployment

Two supported ways to run the stack: natively via the built-in `ctl` supervisor, and via
Docker Compose. Configuration keys are documented in
[configuration.md](configuration.md).

---

## Native — `speechmux-core ctl`

`ctl` is a subcommand of the Core binary, not a separate program
([ADR 0010](../decisions/0010-ctl-subcommand-process-manager.md)). It starts VAD, STT and
Core in the order declared in `workspace.yaml`, restarts on failure, and writes PID files
and per-process logs into `state_dir` (default `/tmp/speechmux`).

```bash
make up       # build + start everything
make status   # NAME / PID / STATUS table
make logs     # tail /tmp/speechmux/*.log
make down     # graceful stop
```

Or directly:

```bash
core/bin/speechmux-core ctl start  --workspace workspace.yaml --profile silero --profile sherpa-onnx
core/bin/speechmux-core ctl status --workspace workspace.yaml
core/bin/speechmux-core ctl stop   --workspace workspace.yaml
```

`ctl` flags: `--workspace`, `--profile` (repeatable), `--log-format` (`json`/`text`/`color`).

### Engine profiles

`workspace.yaml` defines profile templates per category and slot entries that name which
profiles may fill them. Only profiles passed with `--profile` start; entries without a
`profiles:` list (Core itself) always start.

```bash
make up                                       # default: silero sherpa-onnx mlx-whisper
make up PROFILES="silero sherpa-onnx"         # sherpa-onnx only
make up PROFILES="silero mlx-whisper"         # mlx-whisper only
```

Both STT engines are registered in `plugins.yaml`, so running them together is intentional —
clients select one with `engine_hint`, or the router balances between them.

Startup ordering is controlled by `startup_delay_ms`: the VAD profile waits 500 ms so its
socket exists, and the Core entry waits 1000 ms for the plugin sockets to bind.

### Notes

- `make up` refuses to start when ports 50051, 8090 or 8091 are already bound. Run
  `make down` first.
- `ctl status` scans PID files in `state_dir`, so it needs no `--profile` flags and works
  even from a different shell.
- `ctl stop` prefers sending SIGTERM to the manager PID over killing plugin processes
  directly, so the supervisor's own shutdown path runs. `make down` additionally frees the
  three Core ports as a safety net.
- Restart policy per process: `always`, `on-failure` (used everywhere today), `never`.

---

## Docker Compose

```bash
cp .env.example .env      # ports, MODELS_DIR, auth tokens, CORS

make docker-build         # default DOCKER_PROFILE="sherpa faster-whisper"
make docker-up
make docker-logs          # core + vad-silero + both STT services
make docker-logs-stt      # STT only
make docker-logs-vad      # VAD only
make docker-down
```

Select a single engine with `DOCKER_PROFILE`:

```bash
make docker-build DOCKER_PROFILE=sherpa
make docker-up    DOCKER_PROFILE=faster-whisper
```

### Services

| Service | Profile | Port | Notes |
|---------|---------|------|-------|
| `core` | always | 50051 / 8090 / 8091 | Waits for `vad-silero` to be healthy |
| `vad-silero` | always | 50060 (internal) | 60 s health-check start period — torch + Silero load slowly |
| `stt-sherpa` | `sherpa` | 50061 (internal) | Models mounted read-only from `MODELS_DIR` |
| `stt-faster-whisper` | `faster-whisper` | 50062 (internal) | Model auto-downloaded from HuggingFace; 90 s start period |
| `client-web-api` | always | 8000 | FastAPI WebSocket proxy |
| `client-web-front` | always | 3020 | Next.js UI |

Inside Compose, plugins are reached over **TCP** using service names
(`vad-silero:50060`, `stt-sherpa:50061`), configured in
`deploy/docker/plugins-docker.yaml`. Native runs use Unix domain sockets instead.

`core.depends_on` intentionally excludes the STT service: profile variants have different
service names and `depends_on` does not resolve network aliases. Core's health-check
interval plus the circuit breaker handles the startup race, and an unstarted profile's
endpoint simply stays circuit-open.

`NEXT_PUBLIC_API_PORT` is a **build arg**, not a runtime env var — Next.js bakes
`NEXT_PUBLIC_*` at build time. Changing `API_PORT` requires `make docker-build`, not just
`docker-up`.

### Editing configs and rebuilding

- `deploy/docker/*.yaml` are **single-file bind mounts**. Editing one on the host with an
  editor or `sed -i` creates a new inode that the running container does not see, so
  `POST /admin/reload` reloads the *old* file. After any edit: `docker compose up -d <service>`
  (recreates the container and the mount).
- Images do not rebuild themselves. `docker compose up -d` after a `git pull` in `core/` or a
  plugin repo still runs the old image. Check `docker compose images` (CREATED column) and
  `make docker-build` when in doubt — a stale `stt-*` image that predates the plugin
  framework's `STREAMING_MODE_BATCH_ONLY` fix is excluded from batch routing by a current
  Core and every decode fails with ERR2005.
- Verify a rebuilt stack with the [`e2e-test`](../../.codex/skills/e2e-test/SKILL.md) skill.

### Models

sherpa-onnx needs downloaded Zipformer checkpoints. `MODELS_DIR` (default
`./plugin-stt-sherpa-onnx/models`) is mounted read-only at `/models`:

```
plugin-stt-sherpa-onnx/models/
  ko-streaming/
    encoder-epoch-99-avg-1.int8.onnx
    decoder-epoch-99-avg-1.int8.onnx
    joiner-epoch-99-avg-1.int8.onnx
    tokens.txt
```

`make download-models` prints the expected layout and the upstream model index; it does not
download anything. `plugin-stt-sherpa-onnx/scripts/download_models.py` is the helper for
fetching checkpoints.

Only `ko` is configured today. Additional languages need a `languages.<code>:` entry in the
sherpa config — the `en`/`ja` entries are commented out pending available streaming
checkpoints.

---

## Remote access (Tailscale)

`scripts/remote-access.sh` publishes two Tailscale HTTPS routes:

| Tailscale port | Forwards to | Serves |
|----------------|-------------|--------|
| `HTTPS_PORT` (8444) | `WEB_PORT` (3020) | Next.js web client |
| `WS_PORT` (8000) | `CORE_WS_PORT` (8091) | Core WebSocket |

```bash
scripts/remote-access.sh          # start
scripts/remote-access.sh stop     # stop
```

Browser `getUserMedia` requires a secure context, which is the reason this exists for
anything other than `localhost`. Tailscale terminates TLS and forwards plaintext to Core,
so Core's own `tls.*` settings stay off in this setup. The Tailscale CLI must be installed
separately (`brew install tailscale`) even when the Tailscale app is present.

---

## Production checklist

- Set `auth.auth_secret` — it is also the admin token, and empty means the `/admin/*`
  routes are unauthenticated.
- Set `auth.auth_profile` to `api_key` or `signed_token`, or `require_api_key: true`.
- Set `server.allowed_origins` explicitly when the WebSocket port is reachable directly.
  An empty list allows every origin.
- Set `rate_limit.*` to real values. The shipped `core.yaml` uses load-test values
  (`create_session_rps: 1000`).
- Tune `server.max_sessions` and `stream.fair_dispatch_max_concurrent` to the hardware.
  `fair_dispatch_max_concurrent` should equal the engine's real parallelism (`1` for a
  single-process GPU engine).
- Terminate TLS at Core (`tls.*`) or at a trusted proxy. Certificate rotation requires a
  restart; the graceful drain keeps sessions alive across it.
- Point `otel.endpoint` at a collector if you want traces; leaving it empty is free.
- Scrape `/metrics`; use `/health` for both liveness and readiness.
- Set `server.log_transcription_text: false` in the plugin configs when transcripts must
  not appear in logs.
- Reload config without downtime: `kill -HUP <core-pid>` or
  `POST /admin/reload`. Port and TLS changes still need a restart.
