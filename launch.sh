#!/usr/bin/env bash
set -euo pipefail
keety_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export KEETY_BAR_MODE=1
exec "$keety_root/.venv/bin/python" "$keety_root/gui.py" "$@"
