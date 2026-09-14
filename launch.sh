#!/usr/bin/env bash
set -euo pipefail
keety_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$keety_root/.venv/bin/python" "$keety_root/runtime.py" "$@"
