#!/bin/bash
# Enable Tailscale HTTPS access to the SpeechMux web client.
# Run after: make docker-up (or make up for native dev)
#
# Usage:
#   ./scripts/remote-access.sh          # start (default port 8444)
#   ./scripts/remote-access.sh stop     # stop

set -e

HTTPS_PORT=${HTTPS_PORT:-8444}
WEB_PORT=${WEB_PORT:-3020}

case "${1:-start}" in
  start)
    tailscale serve --bg --https "$HTTPS_PORT" "http://localhost:$WEB_PORT"
    echo "Remote access enabled: https://$(tailscale status --json | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["Self"]["DNSName"].rstrip("."))'):$HTTPS_PORT"
    ;;
  stop)
    tailscale serve --bg --https "$HTTPS_PORT" off
    echo "Remote access disabled."
    ;;
  *)
    echo "Usage: $0 [start|stop]"
    exit 1
    ;;
esac
