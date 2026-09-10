# Roadmap

What is not built yet. Each item was verified against the current tree — nothing here is
speculation, and nothing here is already done.

When an item ships, delete it. If it answers a "why is it like this" question, move the
reasoning to an ADR in [../decisions/](../decisions/) instead.

---

## Functional gaps in shipped features

| Item | Where | Detail |
|------|-------|--------|
| `decode_profile` and `task` never reach the STT plugin | `core` | [decode-options-and-task-passthrough.md](decode-options-and-task-passthrough.md) |
| VAD `optimal_frame_ms` is ignored; frame size is hardcoded to 30 ms | `core` | [vad-frame-size-negotiation.md](vad-frame-size-negotiation.md) |

## Client UX

[client-web-ux.md](client-web-ux.md) — what was fixed in the web client's UI review and
the items still open (profile naming, theme toggle placement, `lang`, logs panel, batch
export, session summary).

## Test and tooling gaps

[test-and-lint-gaps.md](test-and-lint-gaps.md) — nine items, from a suite that hangs and
blocks `make test` down to a stale Makefile help string.

## Configuration drift

Small, mechanical, but they mislead:

- `deploy/docker/core-docker.yaml` sets `decode.max_pending`, a key that no longer exists
  in `config.DecodeConfig`. The loader ignores it.
- `deploy/docker/core-docker.yaml` is missing `logging.format`,
  `stream.fair_dispatch_max_concurrent` and `stream.fair_dispatch_max_partial_queue`, so
  Docker silently runs the code defaults (`json`, `1`, `0`) rather than the values the
  native config sets.
- `core/config/plugins.yaml` comments reference
  `plugin-stt/config/inference-sherpa-onnx.yaml`; the file is `inference-onnx.yaml`.

A comparison script would prevent recurrence: diff the key sets of `core/config/core.yaml`
and `deploy/docker/core-docker.yaml` and fail when they diverge.

## Incomplete engine coverage

- **sherpa-onnx language models.** Only `ko` is configured. The `en` and `ja` entries are
  commented out in `plugin-stt/config/inference-onnx.yaml` pending available Zipformer2
  streaming checkpoints. Adding one is config plus a model download, no code.
- **`torch_whisper`.** `plugin-stt/config/inference-onnx.yaml` carries a `torch_whisper:`
  engine section, but no `plugin-stt-torch-whisper` repository exists. Either build the
  adapter or remove the dead config section.

## Deliberately unimplemented

Recorded so nobody re-derives them as bugs:

- **`hybrid` endpointing** — Core VAD and engine endpointing cooperating. Rejected at
  config load; **ERR1021** is already reserved for it.
  [ADR 0014](../decisions/0014-endpointing-source.md).
- **Retracting committed text** — an optional `replace_from_offset` / `replaced_text` pair
  on `RecognitionResult` would let the server withdraw a wrong commit. Not scheduled;
  revisit only if operational data shows revisions are frequent.
  [ADR 0006](../decisions/0006-monotonic-committed-text.md).
- **Cancelling in-flight GPU work.** CTranslate2, PyTorch and MLX offer no mid-inference
  cancellation, so a cancelled session's decode runs to completion and the result is
  discarded. Mitigated by `decode_timeout_sec` and `partial_decode_window_sec`. Revisit if
  an engine gains a cancellation token.
- **Kubernetes manifests / Helm chart.** Docker Compose is the deployment
  ([ADR 0012](../decisions/0012-docker-compose-profiles.md)). `/health`, `/metrics` and
  `/admin/reload` are already the endpoints such a manifest would need.
- **Several registered `ERR4xxx` codes have no call site** (model load/unload,
  observability token, model profile). Codes are permanent; leave them registered.
  [ADR 0008](../decisions/0008-error-code-registry.md).
