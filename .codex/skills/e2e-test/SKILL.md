# Skill: e2e-test

Run SpeechMux end to end — real audio in, transcript out — through the CLI and the web
client, against a running stack. Confirms that Core, VAD, at least one STT engine and the
clients actually work together, which no unit suite in this workspace does.

## When to use this

- Before declaring any change to Core, a plugin, a client or a Docker/config file complete.
- After `docker compose up`, `make up`, or rebuilding any image.
- When a user reports "no transcript" / "wrong text" — this reproduces the path they use.
- Whenever `docs/development/testing.md` or this skill's baseline needs re-verifying.

**Do not** treat unit tests as a substitute. Every E2E failure found so far (below) had a
green unit suite.

## Prerequisites

- A running stack. Either:
  - **Docker** (the usual case): `docker compose --profile sherpa --profile faster-whisper ps`
    shows `core`, `vad-silero`, `stt-*`, `client-web-api`, `client-web-front` up. Ports:
    gRPC 50051, HTTP 8090, WS 8091, web API 8000, web UI 3020.
  - **Native**: `make up PROFILES="silero sherpa-onnx"` (needs `make setup` + models), or the
    dummy engines (`plugin-vad/config/vad-dummy.yaml`, `plugin-stt/config/inference-dummy.yaml`,
    `core/config/plugins-dummy.yaml`) started by hand — they need no models and verify the
    protocol path only.
- `.venv` with `client-cli` installed (light setup in
  [docs/development/workspace.md](../../../docs/development/workspace.md#setup)).
- For synthesising test audio: macOS `say` + `ffmpeg`. Otherwise bring a 16 kHz mono WAV.
- For the web check: Chrome. `client-web/web` dev server if you are testing uncommitted UI.

Read [docs/development/testing.md](../../../docs/development/testing.md#end-to-end) for the
current baseline before starting.

---

## Steps

### 1. Confirm what is actually running

```bash
for p in 50051 8090 8091 8000 3020; do printf "%s: " $p; lsof -nP -iTCP:$p -sTCP:LISTEN -t | tr '\n' ' '; echo; done
docker compose --profile sherpa --profile faster-whisper ps
docker compose --profile sherpa --profile faster-whisper images   # look at CREATED
```

If the ports belong to OrbStack/Docker, the Compose stack is what you are testing — do not
start native plugins on top of it (Core will fail to bind and you will test the wrong thing).

**Image age matters.** Core and plugin images built before the current repo HEAD have bitten
twice already (see Pitfalls). If an image is older than the last commit in its repo, rebuild
it first:

```bash
docker compose --profile sherpa --profile faster-whisper build core stt-faster-whisper stt-sherpa vad-silero
docker compose --profile sherpa --profile faster-whisper up -d
```

### 2. Run the smoke script

```bash
.codex/skills/e2e-test/scripts/smoke.sh
```

It checks `/health`, verifies every healthy inference endpoint reports an `engine_name`,
synthesises `/tmp/speechmux-e2e.wav` if needed, and runs `speechmux file` through **every**
endpoint twice — fast and `--realtime`. All lines must be ✅. A ❌ on step 2 or 4 points at
a specific pitfall below.

### 3. Read the transcripts, not just the exit code

For the default sentence ("안녕하세요. 스피치먹스 엔드 투 엔드 테스트입니다. 오늘 날씨가 정말 좋네요.")
the known-good outputs look like this. `say` renders differ slightly between runs, so judge
shape (result count, tail present, no mid-word split), not exact spelling of the made-up word
"스피치먹스":

| Engine | Expected shape |
|--------|----------------|
| `sherpa-onnx` | ~14 partials then one final, ≈"안녕하세요. 스케치 박스 인데 그 앤드 캐스크입니다. 오늘 날씨가 정말 좋네요", RTF ≈ 0.06 fast / ≈ 1.0 realtime |
| `faster-whisper` | 2 finals with timestamps, ≈"안녕하세여 스피치먹스 앤드 투 앤드 테스트 입니다." + "오늘 날씨가 정말 좋네요", RTF ≈ 0.2 |

Truncated tails ("정말 좋" instead of "좋네요"), mid-word splits ("안녕하 / 세요"), or a
result count of 0 are failures even when the script is green — they mean an EPD, pacing or
audio-decode problem.

### 4. Web client

Against the Docker web UI (`http://localhost:3020`, WS via `:8000`), or a dev server for
uncommitted UI changes:

```bash
cd client-web/web && NEXT_PUBLIC_API_PORT=8000 npm run dev -- --port 3021
```

In Chrome (the Claude-in-Chrome tools work; put the test WAV in the session scratchpad so
`file_upload` may read it):

1. Mode switch (top of the setup card) → **Audio file**, choose the WAV, keep **Realtime
   pacing** on.
2. Engine → pick each engine in turn; also once on Auto.
3. **Send file**. Expect: the setup card folds into a one-line summary; Connection Ready →
   Transfer Sending, with the elapsed time and a progress bar in the bottom dock → partial
   lines → finals → Connection Done / Transfer Completed / Result Done and a "Session
   complete — N utterances …" line under the transcript, all within ≈ audio length + 2 s.
   Open **Logs** (collapsed by default): `Connecting to ws://…`, `Connected`, `Final: …`,
   `Session done.`
4. **Send file** again and press **Stop** (the same button) after ~2 s. Expect
   Transfer/Result "Finishing", the button disabled reading "Finishing…", then a final line
   and "Session done."
5. **Batch**: add two files, **Start**. Expect "2 of 2 done", then check the **JSON** and
   **TXT** downloads and one file's **Download SRT**.
6. Mic mode needs a machine with a microphone; the Chrome-MCP window has none, so expect the
   "No microphone was found" banner there — that is the correct behaviour, not a failure.

**Without the Chrome extension**, drive the system Chrome headless instead: `npm install
playwright-core` in the session scratchpad and launch with
`chromium.launch({ channel: "chrome" })`. The same expectations apply; `setInputFiles`
replaces `file_upload`. Two things this route can do that the extension cannot:

- **Mic path.** Headless Chrome cannot open an audio device — `getUserMedia` never settles,
  even with the fake-device flags, and the page waits at "Waiting for microphone…". To
  exercise everything downstream of capture, replace `AudioContext`, `AudioWorkletNode` and
  `navigator.mediaDevices.getUserMedia` in `page.addInitScript` with fakes whose worklet
  node posts the WAV's PCM to `port.onmessage` in 80 ms chunks. That is not a substitute
  for one run with a real microphone.
- **Silent Reconnect.** `page.routeWebSocket(/\/ws\/stream/, …)` with
  `ws.connectToServer()`, then `ws.close()` mid-session. Expect a "reconnecting (attempt 1
  of 3)" banner and `Reconnecting 1/3`, then Ready and new transcript lines; refuse three
  attempts in the route handler and expect the "connection was lost and could not be
  restored" banner.

Compare the web transcript with the CLI transcript for the same engine. They should match
word for word; a difference means the web audio path (decode/resample/pacing) is altering
the audio.

### 5. Record

Update the baseline in [docs/development/testing.md](../../../docs/development/testing.md#end-to-end)
if engines, versions or expected text changed. Anything that failed and was not fixed goes
in [docs/plans/roadmap.md](../../../docs/plans/roadmap.md).

---

## Pitfalls (each one has happened)

- **Stale Docker images.** A 4-month-old `core` image skipped the capability re-fetch, and a
  4-month-old `stt-faster-whisper` image reported `STREAMING_MODE_UNSPECIFIED`; the new
  Core's strict `RouteBatch()` then excluded it → every final decode failed with **ERR2005**
  and the CLI showed **"(no speech detected)"**. `make docker-build` / `docker compose build`
  before testing, and check `/admin/plugins` shows `engine_name` for every endpoint.
- **Editing a bind-mounted config does nothing until the container is recreated.** `sed -i`
  writes a new inode; the container keeps the old one. `POST /admin/reload` then reloads the
  old file. Use `docker compose up -d <service>` after editing anything under
  `deploy/docker/`.
- **`vad_watermark_lag_threshold_sec` > 0 kills every file upload.** File input arrives faster
  than real time, the lag exceeds the threshold, and Core aborts with **ERR3004** (which the
  CLI currently reports as ERR3002). Keep it `0` in `deploy/docker/core-docker.yaml`, as in
  `core/config/core.yaml`.
- **Port collisions.** OrbStack/Docker holds 50051/8090/8091/8000/3020 while the stack is up.
  A native `speechmux-core` will fail to bind, and a dev web server on 3020 will not start.
- **Background-tab timer throttling.** Chrome clamps `setTimeout` to ≥1 s in tabs that are not
  focused; a per-chunk sleep made a 5.6 s file take 67 s and the EPD split utterances. The
  web client now paces against the wall clock — if you see very slow uploads again, check
  that regression first.
- **Web audio decode at device rate.** Decoding a 16 kHz file in a default `AudioContext`
  (44.1/48 kHz) and box-filter downsampling changed the recognised text and dropped the last
  syllables. `decodeAudioFileToPcm16` now decodes at 16 kHz; verify with the CLI-vs-web
  comparison in step 4.
- **Chrome-MCP click quirks.** Clicking a dock button by `ref` sometimes does not fire the
  React handler; click by coordinates from a fresh screenshot instead. `form_input` on the
  Engine select can leave the control looking blank even though state was set.
- **Start and Stop are one button.** Presses less than 350 ms apart count as one, so a
  script that clicks Start and Stop back to back only starts. Wait between them.
- **Realtime pacing off loses utterances.** A long file sent unpaced comes back as its last
  sentence only, from the CLI as well — a Core issue on the batch path (roadmap), not a web
  regression. Judge the web client with pacing on, and keep Batch-panel test files short
  (the panel always sends unpaced).
- **One WebSocket message ≤ 32 768 bytes.** Core closes the connection on anything larger.
  This is what made the web client's reconnect loop forever before it replayed its 2 s
  overlap in 80 ms frames; suspect it whenever a session dies right after a large send.
- **VAD threshold defaults.** The web client's threshold must match Core's `vad_threshold`
  (0.5). A higher value classifies quiet syllables as silence and the EPD cuts mid-word.

---

## Done when

- [ ] `smoke.sh` exits 0 with every endpoint ✅ in both fast and `--realtime` runs.
- [ ] Transcripts match the expected shape above; no truncated tail, no mid-word split.
- [ ] Web file upload completes in ≈ audio length + 2 s and reaches Done; Stop → Finishing →
      Done works.
- [ ] Batch panel reaches "N of N done" and its JSON / TXT / SRT downloads open.
- [ ] Web transcript matches the CLI transcript for the same engine.
- [ ] `/admin/plugins` shows `engine_name` for every healthy endpoint.
- [ ] Anything that failed is either fixed or written into `docs/plans/roadmap.md`.
