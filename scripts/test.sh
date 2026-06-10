#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Pre-flight ────────────────────────────────────────────────────────────────

command -v python3 &>/dev/null || { echo "Error: python3 not found" >&2; exit 1; }

HCPATH=$(python3 -c "import hop_core; print(hop_core.__file__)" 2>/dev/null || true)
if [[ "$HCPATH" != "$REPO_ROOT/src/"* ]]; then
  echo "Installing hop-core from this repo..."
  pip install -e "$REPO_ROOT[dev]" -q
fi

# ── Run tests ─────────────────────────────────────────────────────────────────

cd "$REPO_ROOT"
exec python3 -m pytest "$@"
