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

## Findings from end-to-end testing

Surfaced by the [`e2e-test`](../../.codex/skills/e2e-test/SKILL.md) skill on 2026-09-11.
Reproduction steps are in that skill; none of these is covered by a unit test today.

| Item | Where | Detail |
|------|-------|--------|
| Pipeline errors reach clients as ERR3002 | `core` | `ProcessSession` returns `sttErr.ToGRPC()` (a gRPC status error); `transport` then calls `errors.ToErrorSpec(pipelineErr)`, whose `errors.As(*STTError)` fails, so an ERR3004 VAD failure is sent as ERR3002 with `retryable=false`. Return the `*STTError` and convert at the transport boundary, or parse the `ERR####` prefix in `ToErrorSpec` |
| Failed final decode looks like silence | `core` | When the batch final decode fails (ERR2005 in the run above), `batchDecodeEngine` logs a WARN and the session ends cleanly with zero results; the CLI prints "(no speech detected)". A decode failure must surface as an error result or `StreamError` |
| Streaming results carry no timestamps | `core` | WS/gRPC results from `streamingDecodeEngine` have `start_sec = end_sec = 0`; batch results have real values. Derive them from the audio position tracked in `audioRing` |
| `engine_name` missing on the batch path | `core` | `sess.SetEngineUsed` is called only in the streaming branch of `ProcessSession`; batch sessions send `engine_name=""` and the web client shows "auto". Set it from the routed client on the batch path too |
| CLI `--metrics` `text` holds only the last final | `client-cli` | `commands/_output.py` builds `text` from the last result, not the joined finals (`results: 2, text: " 오늘 날씨가 정말 좋네요"`) |
| Dummy engines are not a `workspace.yaml` profile | workspace | `make up` cannot start the no-model stack; the dummy configs exist but must be launched by hand. Add `dummy` profiles so the protocol-level E2E needs no models |
| Batch panel not covered end to end | `client-web` | The e2e skill exercises file and CLI paths; the multi-file Batch panel still needs a run |

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
