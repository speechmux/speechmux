# client-web UX follow-ups

Status: partially done. Verified against the current tree and in the browser (Chrome,
1280 px and 390 px, light and dark).

## Done (client-web, uncommitted at time of writing)

- Batch panel rewritten with `globals.css` classes — it was written in Tailwind utility
  classes while Tailwind was never wired into the build, so it rendered unstyled with the
  native file input exposed. Tailwind devDependencies removed; dead `StatusBar.tsx`
  deleted.
- `.error-banner` styled (it had no CSS rule); inline `Realtime pacing` checkbox layout;
  bottom dock constrained to the content column; mic level bar shown only while recording.
- Dev default WebSocket URL falls back to `:8000` on localhost when
  `NEXT_PUBLIC_API_PORT` is unset (previously pointed at the Next server itself and hung
  10 s). "Connecting to <url>" is logged.
- Transcript renders oldest → newest and follows the latest line only while the user is
  at the bottom; a "Jump to latest" pill appears otherwise. Per-line copy button is always
  visible on touch devices.
- Stop → `Finishing…` state until the server's `done`/`error`; Start disabled meanwhile.
  Clear no longer closes the connection. Stop during "Connecting" discards the client so a
  late connect failure does not raise a banner.
- Mic permission / device errors mapped to user-facing banner text.
- `suppressHydrationWarning` on `<html>` for the pre-hydration theme script.

## Remaining

| Item | Where | Notes |
|------|-------|-------|
| `Network profile` options `balanced` and `realtime` both map to `decode_profile: realtime`; and Core does not forward `decode_profile` at all yet | `page.tsx` `PROFILE_DECODE` | Reduce to two options or label "(no effect yet)" until [decode-options-and-task-passthrough.md](decode-options-and-task-passthrough.md) ships |
| Theme toggle lives inside the collapsible Advanced section of a card that disappears while running | `page.tsx` | Move to the hero header |
| Settings summary while running | `page.tsx` | Controls collapse entirely; show a one-line summary (input, language, engine, profile) |
| `<html lang="en">` fixed while the default UI language is Korean | `layout.tsx` | Set `document.documentElement.lang` from `languageCode` |
| Status boxes rely on colour alone | `globals.css` | Add a dot/icon per `data-state` |
| Engine list silently falls back to `FALLBACK_ENGINES` when Core is offline | `page.tsx`, `/api/engines` | Show a "server unreachable — default list" hint |
| Reconnecting shows only a yellow label | `page.tsx` | Show attempt N/3 and that audio is being buffered |
| Logs panel always expanded below Transcript | `page.tsx` | Collapse into `<details>` or move under Advanced |
| Batch export | `BatchPanel.tsx` | TXT/SRT alongside JSON (client-cli already generates SRT) |
| Session summary on done | `page.tsx` | Utterance count, audio length, engine; RTF needs `ResultMeta` on the WS result message (Core change) |
| No test runner | `web/` | Vitest for `extractIncremental`, `applyResult`, `applyDone`; tracked in [test-and-lint-gaps.md](test-and-lint-gaps.md) |
| `next lint` deprecated in Next 16 | `web/package.json` | Migrate to ESLint CLI |
