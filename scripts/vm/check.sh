#!/usr/bin/env bash
# Checks the VM is ready for the bot. Run from the desktop session (a terminal
# opened inside the VM), not over SSH:  bash scripts/vm/check.sh
set -uo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"
exec "$REPO_DIR/.venv/bin/python" -m skillbot doctor "$@"
