#!/usr/bin/env bash
# End-to-end smoke test for a running SpeechMux stack (Docker Compose or native).
#
# Checks, in order:
#   1. /health is "ok"
#   2. every healthy inference endpoint reports an engine_name (GetCapabilities succeeded)
#   3. a Korean test WAV exists (generated with macOS `say` when missing)
#   4. `speechmux file` transcribes through EVERY inference endpoint, fast and real-time paced
#
# Usage (from the workspace root):
#   .codex/skills/e2e-test/scripts/smoke.sh
#
# Environment overrides:
#   SPEECHMUX_HTTP   default http://localhost:8090   Core HTTP (health/admin)
#   SPEECHMUX_GRPC   default localhost:50051         Core gRPC (used by the CLI)
#   SPEECHMUX_WAV    default /tmp/speechmux-e2e.wav  test audio (16 kHz mono PCM WAV)
#   SPEECHMUX_LANG   default ko
#   SPEECHMUX_TEXT   sentence to synthesise when the WAV is missing (macOS only)
#   ADMIN_TOKEN      Authorization header value for /admin when auth_secret is set
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
PY="$ROOT/.venv/bin/python3"
CLI="$ROOT/.venv/bin/speechmux"
HTTP=${SPEECHMUX_HTTP:-http://localhost:8090}
GRPC=${SPEECHMUX_GRPC:-localhost:50051}
WAV=${SPEECHMUX_WAV:-/tmp/speechmux-e2e.wav}
LANG_CODE=${SPEECHMUX_LANG:-ko}
TEXT=${SPEECHMUX_TEXT:-"안녕하세요. 스피치먹스 엔드 투 엔드 테스트입니다. 오늘 날씨가 정말 좋네요."}
AUTH=()
[ -n "${ADMIN_TOKEN:-}" ] && AUTH=(-H "Authorization: $ADMIN_TOKEN")

pass=0; fail=0
ok()   { echo "  ✅ $*"; pass=$((pass+1)); }
bad()  { echo "  ❌ $*"; fail=$((fail+1)); }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing tool: $1"; exit 2; }; }
need curl; [ -x "$PY" ] || { echo "no .venv — run the light setup in docs/development/workspace.md"; exit 2; }
[ -x "$CLI" ] || { echo "client-cli not installed: uv pip install --python .venv/bin/python3 -e 'client-cli[dev]'"; exit 2; }

echo "== 1. health ($HTTP/health)"
health=$(curl -sf "$HTTP/health" || true)
if [ -z "$health" ]; then bad "Core HTTP not reachable at $HTTP"; echo "$fail failure(s)"; exit 1; fi
status=$(printf '%s' "$health" | "$PY" -c 'import sys,json; print(json.load(sys.stdin)["status"])')
[ "$status" = "ok" ] && ok "status=ok" || bad "status=$status  ($health)"

echo "== 2. inference endpoints ($HTTP/admin/plugins)"
plugins=$(curl -sf ${AUTH[@]+"${AUTH[@]}"} "$HTTP/admin/plugins" || true)
if [ -z "$plugins" ]; then bad "/admin/plugins not reachable (auth_secret set? pass ADMIN_TOKEN)"; fi
endpoints=$(printf '%s' "$plugins" | "$PY" -c '
import sys, json
for e in json.load(sys.stdin).get("inference", []):
    print(e["id"], "1" if e.get("healthy") else "0", e.get("engine_name") or "-")' 2>/dev/null || true)
[ -n "$endpoints" ] || bad "no inference endpoints registered"
while read -r id healthy engine; do
  [ -z "${id:-}" ] && continue
  if [ "$healthy" != "1" ]; then bad "$id: not healthy"; continue; fi
  if [ "$engine" = "-" ]; then
    bad "$id: healthy but engine_name empty — GetCapabilities never succeeded (plugin image older than plugin-stt 16795d6, or Core older than the capability re-fetch). Rebuild the image; see SKILL.md"
  else ok "$id: engine=$engine"; fi
done <<< "$endpoints"

echo "== 3. test audio ($WAV)"
if [ ! -f "$WAV" ]; then
  if command -v say >/dev/null && command -v ffmpeg >/dev/null; then
    say -v Yuna "$TEXT" -o /tmp/speechmux-e2e.aiff && ffmpeg -y -loglevel error -i /tmp/speechmux-e2e.aiff -ar 16000 -ac 1 -sample_fmt s16 "$WAV"
    ok "generated with say/ffmpeg"
  else bad "no test WAV and cannot synthesise one (needs macOS say + ffmpeg); set SPEECHMUX_WAV"; fi
else ok "exists"; fi
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WAV" 2>/dev/null || echo "?")
echo "  duration_sec=$dur"

echo "== 4. CLI transcription per endpoint (gRPC $GRPC)"
run_cli() { # $1=id $2=extra flags
  local out; out=$("$CLI" --server "$GRPC" --session-timeout 120 file "$WAV" --lang "$LANG_CODE" --engine-hint "$1" $2 --metrics 2>&1 | grep '^{' | tail -1)
  if [ -z "$out" ]; then bad "$1 $2: no metrics line (CLI error)"; return; fi
  "$PY" - "$1" "$2" <<PY
import sys, json
d = json.loads('''$out'''); tag = " ".join(a for a in sys.argv[1:] if a)
if d["results"] > 0 and d["text"].strip():
    print(f"  ✅ {tag}: results={d['results']} rtf={d['rtf']} text={d['text']!r}")
else:
    print(f"  ❌ {tag}: results={d['results']} text={d['text']!r} — decode produced nothing (check Core log for ERR2005/ERR3004)"); sys.exit(1)
PY
  [ $? -eq 0 ] && pass=$((pass+1)) || fail=$((fail+1))
}
while read -r id healthy engine; do
  [ -z "${id:-}" ] || [ "$healthy" != "1" ] && continue
  run_cli "$id" ""
  run_cli "$id" "--realtime"
done <<< "$endpoints"

echo; echo "== summary: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
