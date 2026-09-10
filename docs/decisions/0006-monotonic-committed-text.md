# 0006 — `committed_text` never shrinks within an utterance

Status: Accepted

## Context

Partial decodes of a growing audio segment are not monotone: given more context, Whisper
will revise earlier words — Korean particles ("나는" → "나를"), English articles,
punctuation. A UI that simply renders the latest hypothesis flickers as settled text
changes underneath the reader.

## Decision

`ResultAssembler` splits every result into `committed_text` (stable) and `unstable_text`
(may change). On each partial, the longest common prefix of the previous and current text
advances the commit boundary, snapped to a word boundary (space) or, for scripts without
inter-word spaces, to a punctuation boundary from `.,?!。、，！？…`. Comparison is at **rune**
granularity, never bytes. `committed_text` is monotonically non-decreasing within an
utterance. On `is_final` the full utterance text becomes committed, `unstable_text` is
emptied, and state resets for the next utterance.

Once `committed_so_far` exceeds `lcpWindowRunes` (200), only its tail is compared, bounding
the per-partial cost in long sessions.

## Rationale

- Flicker in already-settled text is a worse user experience than an occasionally wrong
  particle. This behaviour was validated in production in the predecessor Python server.
- Rune granularity is mandatory: a byte-level LCP can split a multi-byte UTF-8 character
  and emit invalid text. Korean, Japanese and Chinese are primary target languages.
- Word/punctuation snapping stops the client from receiving half-words. CJK text, which has
  no spaces, commits at the LCP boundary character by character.
- The window cap avoids an O(n) rune conversion on every partial once a session's committed
  text grows long.

## Consequences

- A wrong prefix committed early is permanent for that utterance. This is a deliberate
  trade-off, not an oversight.
- A future alternative, if operational data shows revisions are frequent enough to matter:
  add optional `replace_from_offset` / `replaced_text` fields to `RecognitionResult` so a
  server can retract a commit, with clients that ignore the fields keeping today's
  behaviour. Not implemented, and not scheduled.
- `ResultAssembler` is not safe for concurrent use; callers serialise access. In the batch
  path that is why results must be collected in submission order
  ([ADR 0011](0011-fair-decode-dispatcher.md)).
- Native-streaming engines may supply their own `committed_text`/`unstable_text` in
  `StreamHypothesis`; the fields are duplicated between the plugin and client protos for
  exactly that reason.
