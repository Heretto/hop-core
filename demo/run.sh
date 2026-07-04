#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Helpers ───────────────────────────────────────────────────────────────────

die() { echo "Error: $*" >&2; exit 1; }

free_port() {
  local port=$1
  while lsof -i ":$port" &>/dev/null 2>&1; do
    port=$((port + 1))
  done
  echo "$port"
}

wait_for_http() {
  local url=$1 label=$2 tries=${3:-30}
  printf "  Waiting for %s" "$label"
  for _ in $(seq 1 "$tries"); do
    if curl -sf "$url" &>/dev/null; then printf " ✓\n"; return 0; fi
    printf "."
    sleep 1
  done
  printf " timed out\n"
  return 1
}

# ── Pre-flight ────────────────────────────────────────────────────────────────

command -v python3 &>/dev/null || die "python3 not found"
command -v uvicorn &>/dev/null || die "uvicorn not found — run: pip install uvicorn[standard]"
command -v node    &>/dev/null || die "node not found — install Node.js 18+"
command -v npx     &>/dev/null || die "npx not found"

# Verify hop_core resolves to this repo, not another install
HCPATH=$(python3 -c "import hop_core; print(hop_core.__file__)" 2>/dev/null || true)
if [[ "$HCPATH" != "$SCRIPT_DIR/../src/"* ]]; then
  echo "  hop_core not installed from this repo — installing..."
  pip install -e "$SCRIPT_DIR/.." -q
fi

# Generate .env if missing
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "  No .env found — generating secrets..."
  "$SCRIPT_DIR/scripts/setup.sh"
fi

# Install frontend deps if needed
if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
  echo "  Installing frontend dependencies..."
  (cd "$SCRIPT_DIR/frontend" && npm install --silent)
fi

# ── Pick free ports ───────────────────────────────────────────────────────────

BACKEND_PORT=$(free_port 8000)
FRONTEND_PORT=$(free_port 4200)

# ── Write a proxy config for the chosen backend port ─────────────────────────

PROXY_CONF=$(mktemp /tmp/hop-demo-proxy-XXXXXX.json)
cat > "$PROXY_CONF" <<EOF
{
  "/api": {
    "target": "http://127.0.0.1:${BACKEND_PORT}",
    "secure": false,
    "changeOrigin": true
  }
}
EOF

# ── Cleanup on exit ───────────────────────────────────────────────────────────

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "Shutting down..."
  [ -n "$BACKEND_PID"  ] && kill "$BACKEND_PID"  2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  rm -f "$PROXY_CONF"
}
trap cleanup EXIT INT TERM

# ── Start backend ─────────────────────────────────────────────────────────────

echo ""
echo "Starting hop-core demo"
echo "  Backend  → http://localhost:${BACKEND_PORT}"
echo "  Frontend → http://localhost:${FRONTEND_PORT}"
echo ""

(
  cd "$SCRIPT_DIR/backend"
  CORS_ORIGINS="http://localhost:${FRONTEND_PORT}" \
    exec uvicorn main:app \
      --host 127.0.0.1 \
      --port "$BACKEND_PORT" \
      --log-level warning
) &
BACKEND_PID=$!

wait_for_http "http://127.0.0.1:${BACKEND_PORT}/" "backend" 30 \
  || die "Backend did not start — check for errors above"

# ── Start frontend ────────────────────────────────────────────────────────────

(
  cd "$SCRIPT_DIR/frontend"
  # ng serve runs backgrounded with no interactive stdin — suppress any CLI
  # first-run prompts (analytics/autocompletion), which otherwise crash with
  # "User force closed the prompt".
  export NG_CLI_ANALYTICS=false
  export CI=1
  exec npx ng serve \
    --port "$FRONTEND_PORT" \
    --proxy-config "$PROXY_CONF" \
    --configuration development \
    --no-open
) &
FRONTEND_PID=$!

wait_for_http "http://localhost:${FRONTEND_PORT}/" "frontend" 90 \
  || die "Frontend did not start — check for errors above"

# ── Open browser ──────────────────────────────────────────────────────────────

URL="http://localhost:${FRONTEND_PORT}"
echo ""
echo "Demo is live → $URL"
echo "Press Ctrl+C to stop."
echo ""

if command -v open &>/dev/null; then
  open "$URL"
elif command -v xdg-open &>/dev/null; then
  xdg-open "$URL"
fi

# Keep running until either process exits or Ctrl+C
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 2
done
