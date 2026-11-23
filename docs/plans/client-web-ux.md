# client-web UX follow-ups

Status: open items only. The UI review's fixes have shipped in `client-web`; what the page
does now is described in `client-web/README.md`.

| Item | Where | Notes |
|------|-------|-------|
| Decode profile selector has no effect | `web/app/page.tsx` (Advanced) | Core does not forward `decode_profile` yet. The selector says so in its hint; delete the hint when [decode-options-and-task-passthrough.md](decode-options-and-task-passthrough.md) ships |
| Session summary lacks RTF and latency | `web/app/page.tsx`, `web/lib/speechmux-ws.ts` | The summary shows utterance count, audio length and engine. RTF needs `ResultMeta` on the WebSocket `result` message — a Core change |
| Silent Reconnect starts a new session | `web/lib/speechmux-ws.ts` | It reconnects with `start` and replays 2 s of audio, so the utterance in progress is cut in two. Core's WebSocket `resume` frame ([client-protocol.md](../api/client-protocol.md#session-resume)) could continue the same session instead; it is off by default (`server.resumable_session_timeout_sec: 0`) |
| Real microphone capture not verified end to end | `web/components/AudioCapture.tsx` | The E2E run fakes the capture API because headless Chrome cannot open an audio device. Run mic mode once on a machine with a microphone — see [testing.md](../development/testing.md#end-to-end) |
| Components have no unit tests | `web/app/page.tsx`, `web/components/` | Vitest covers `web/lib/` only; tracked in [test-and-lint-gaps.md](test-and-lint-gaps.md) |
| `next lint` deprecated in Next 16 | `web/package.json` | Migrate to the ESLint CLI |
