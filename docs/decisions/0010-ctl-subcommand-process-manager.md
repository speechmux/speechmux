# 0010 — Process supervision is a `ctl` subcommand of the Core binary

Status: Accepted

## Context

A native run needs three or more processes started in the right order: VAD, then STT, then
Core once the plugin sockets exist. Driving that from the `Makefile` was fragile — no
restart on crash, hardcoded venv paths, and a stop path that killed by port. On macOS there
is no systemd, and Docker is not always wanted for development.

## Decision

Add `start`, `status` and `stop` as subcommands of the existing `speechmux-core` binary,
dispatched by checking `os.Args[1] == "ctl"` before `flag.Parse()`. No separate
`speechmux-ctl` binary and no CLI framework.

Processes are declared in `workspace.yaml` with a two-level structure: `profiles:` is a
template library grouped by category, and `processes:` is the ordered start list where a
*slot* entry names a category plus the profiles that may fill it. `--profile` (repeatable)
selects which ones actually start; entries without a `profiles:` list always start.

Each process gets a dedicated watcher goroutine, a restart policy
(`always`/`on-failure`/`never`), a `startup_delay_ms`, and a PID file in `state_dir`.
`ctl status` reads those PID files rather than the profile list. `ctl stop` prefers sending
SIGTERM to the manager PID over killing plugins directly.

## Rationale

- One binary is simpler to distribute and deploy; `cobra` for three commands would be a
  dependency for nothing.
- A watcher goroutine per process avoids a double `cmd.Wait()` race between the restart
  logic and the shutdown path.
- Reading PID files for `status` means the command works from any shell with no flags, and
  reports what is actually running rather than what the config says should be.
- SIGTERM to the manager lets the supervisor's own shutdown ordering run, instead of
  leaving it to observe children vanishing.
- The two-level profile system is what lets one `workspace.yaml` describe every engine
  combination without duplicating process definitions per combination.

## Consequences

- `ctl` is a development and small-deployment tool, not an init system: no cgroups, no log
  rotation, no resource limits. Logs accumulate in `state_dir` (`/tmp/speechmux/*.log`).
- Ordering is expressed as sleeps (`startup_delay_ms`), not readiness probes. A slow model
  load can still let Core start first; the circuit breaker and capability re-fetch cover
  that ([ADR 0007](0007-runtime-capability-discovery.md)).
- If the subcommand set grows past roughly five commands or needs nested flags, adopting a
  CLI framework becomes worthwhile. It is not yet.
- Production deployment is Docker Compose ([ADR 0012](0012-docker-compose-profiles.md)),
  which supervises independently and does not use `ctl`.
