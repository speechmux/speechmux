#!/bin/bash
# Enable Tailscale HTTPS access to the SpeechMux web client and Core WebSocket.
# Run after: make docker-up (or make up for native dev)
#
# Two Tailscale HTTPS routes are registered:
#   HTTPS_PORT (8444) → Next.js web client (WEB_PORT, default 3020)
#   WS_PORT    (8000) → Core WebSocket server (CORE_WS_PORT, default 8091)
#
# The web client is built with NEXT_PUBLIC_API_PORT=8000, so browsers construct
# wss://<host>:8000/ws/stream. Tailscale terminates TLS and forwards to Core's
# plaintext ws://localhost:8091.
#
# Usage:
#   ./scripts/remote-access.sh          # start
#   ./scripts/remote-access.sh stop     # stop

set -e

HTTPS_PORT=${HTTPS_PORT:-8444}
WEB_PORT=${WEB_PORT:-3020}
WS_PORT=${WS_PORT:-8000}
CORE_WS_PORT=${CORE_WS_PORT:-8091}

case "${1:-start}" in
  start)
    tailscale serve --bg --https "$HTTPS_PORT" "http://localhost:$WEB_PORT"
    tailscale serve --bg --https "$WS_PORT" "http://localhost:$CORE_WS_PORT"
    HOSTNAME=$(tailscale status --json | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["Self"]["DNSName"].rstrip("."))')
    echo "Remote access enabled:"
    echo "  Web client : https://${HOSTNAME}:${HTTPS_PORT}"
    echo "  WebSocket  : wss://${HOSTNAME}:${WS_PORT}/ws/stream"
    ;;
  stop)
    tailscale serve --bg --https "$HTTPS_PORT" off 2>/dev/null || true
    tailscale serve --bg --https "$WS_PORT" off 2>/dev/null || true
    echo "Remote access disabled."
    ;;
  *)
    echo "Usage: $0 [start|stop]"
    exit 1
    ;;
esac
